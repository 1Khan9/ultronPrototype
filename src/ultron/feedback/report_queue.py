"""User-initiated report queue with append-only audit chain (T12 part 1).

T12 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Single-user ultron's adaptation of the marketplace's report-queue
+ appeal workflow. The upstream pattern is "community files
concerns against a published artifact + moderator triages"; the
ultron adaptation is "voice user files concerns against a turn /
response / skill / provider / memory entry + the same voice user
(or a future operator review pass) triages them later".

Three architectural pieces:

1. **Filing.** :meth:`ReportQueue.file_report(target, reason)` adds
   one :class:`Report` row with status OPEN. Voice intent
   ("ultron, log a concern that the last response was wrong")
   triggers this; the orchestrator wires the target metadata
   (turn id, response text id, etc.) before persisting.

2. **Triaging.** :meth:`ReportQueue.triage(report_id, status,
   note, final_action)` updates the row to CONFIRMED or DISMISSED
   with an optional ``final_action`` (NONE / HIDE / QUARANTINE /
   REVOKE). Per the catalog's YELLOW gating, every triage call
   that changes state is paired with a :mod:`ultron.safety.two_phase_approval`
   handle so a compromised in-process LLM cannot dismiss real
   reports as a covert channel.

3. **Persistence + audit.** Reports live in an append-only JSONL
   file with the same SHA-256 hash chain shape as
   :mod:`ultron.safety.audit` so the log is tamper-evident.
   :meth:`replay_from_log` rebuilds the in-memory state on
   startup; :meth:`verify_log_chain` returns False on tampered
   rows.

The catalog's "moderation plan preview" pattern (universal pre-
act surface for every voice command with irreversible impact) is
implemented in :mod:`ultron.feedback.moderation_plan` and consumed
by triage flows before they call :meth:`ReportQueue.triage`.

The single-user model means there's no "appeal workflow" in the
strict marketplace sense -- the user IS the reporter and the
triager. The structured shape is preserved so future operator
review sessions (or a deployed multi-user variant) inherit the
same audit trail.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Optional

LOGGER = logging.getLogger(__name__)


class ReportStatus(str, Enum):
    """Lifecycle state of a :class:`Report`."""

    OPEN = "open"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class FinalAction(str, Enum):
    """The action taken when the report's triage resolves to CONFIRMED."""

    NONE = "none"
    HIDE = "hide"
    QUARANTINE = "quarantine"
    REVOKE = "revoke"


class ReportTargetKind(str, Enum):
    """Discriminator for what a report concerns.

    Ultron-specific extension of the upstream marketplace's
    skill/package target kinds. Each kind picks a different audit-
    reviewer path (a turn-quality report goes to offline LLM-drift
    review; a memory-quality report goes to the topical-cleanup
    pass; a provider-health report goes to the auth-profile-rotation
    audit).
    """

    TURN = "turn"
    RESPONSE = "response"
    SKILL = "skill"
    PROVIDER = "provider"
    MEMORY = "memory"
    INTENT = "intent"
    PERSONA = "persona"
    OTHER = "other"


def new_report_id() -> str:
    """Return a fresh 32-char hex UUID4 report identifier."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class Report:
    """One filed concern.

    Fields:
        id: 32-char hex UUID4 (:func:`new_report_id`).
        target_kind: which subsystem the concern is about.
        target_id: opaque identifier of the targeted item (turn
            UUID, skill slug, provider name, etc.).
        reason: free-form text from the reporter explaining the
            concern. May be empty for "thumbs-down on the last
            turn" style reports where the voice handler doesn't
            collect a follow-up.
        status: current :class:`ReportStatus`.
        version: optional version string (when the target is a
            versioned artifact like a skill).
        reporter_voice_session: opaque session id of the voice
            session that filed the report (empty when filed
            outside a voice session).
        created_at: ISO-8601 timestamp.
        triaged_at: ISO-8601 timestamp of the most recent triage
            decision (empty when status is OPEN).
        triage_note: free-form note from the triager.
        final_action: applied action when status is CONFIRMED.
        extras: free-form opaque metadata.
    """

    id: str
    target_kind: ReportTargetKind
    target_id: str
    reason: str = ""
    status: ReportStatus = ReportStatus.OPEN
    version: str = ""
    reporter_voice_session: str = ""
    created_at: str = ""
    triaged_at: str = ""
    triage_note: str = ""
    final_action: FinalAction = FinalAction.NONE
    extras: Mapping[str, object] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "id": self.id,
            "target_kind": self.target_kind.value,
            "target_id": self.target_id,
            "reason": self.reason,
            "status": self.status.value,
            "version": self.version,
            "reporter_voice_session": self.reporter_voice_session,
            "created_at": self.created_at,
            "triaged_at": self.triaged_at,
            "triage_note": self.triage_note,
            "final_action": self.final_action.value,
        }
        if self.extras:
            out["extras"] = dict(self.extras)
        return out

    @classmethod
    def from_json_dict(cls, raw: Mapping[str, object]) -> "Report":
        try:
            kind = ReportTargetKind(str(raw.get("target_kind") or "other"))
        except ValueError:
            kind = ReportTargetKind.OTHER
        try:
            status = ReportStatus(str(raw.get("status") or "open"))
        except ValueError:
            status = ReportStatus.OPEN
        try:
            final_action = FinalAction(str(raw.get("final_action") or "none"))
        except ValueError:
            final_action = FinalAction.NONE
        extras_raw = raw.get("extras")
        return cls(
            id=str(raw.get("id") or ""),
            target_kind=kind,
            target_id=str(raw.get("target_id") or ""),
            reason=str(raw.get("reason") or ""),
            status=status,
            version=str(raw.get("version") or ""),
            reporter_voice_session=str(raw.get("reporter_voice_session") or ""),
            created_at=str(raw.get("created_at") or ""),
            triaged_at=str(raw.get("triaged_at") or ""),
            triage_note=str(raw.get("triage_note") or ""),
            final_action=final_action,
            extras=dict(extras_raw) if isinstance(extras_raw, Mapping) else {},
        )


@dataclass(frozen=True)
class _ReportEvent:
    """Internal: one audit-log event for a report mutation."""

    op: str  # "file" / "triage"
    report_id: str
    timestamp: str
    payload: Mapping[str, object]
    prev_hash: str

    def canonical_payload(self) -> str:
        record = {
            "op": self.op,
            "report_id": self.report_id,
            "ts": self.timestamp,
            "payload": dict(self.payload),
            "prev_hash": self.prev_hash,
        }
        return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)

    def hash(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()

    def to_jsonl_line(self) -> str:
        record: dict[str, object] = {
            "op": self.op,
            "report_id": self.report_id,
            "ts": self.timestamp,
            "payload": dict(self.payload),
            "prev_hash": self.prev_hash,
            "hash": self.hash(),
        }
        return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


class ReportQueueError(RuntimeError):
    """Base class for report-queue mutations that violate the contract."""


class UnknownReportError(ReportQueueError):
    """Raised when a triage targets a report id that doesn't exist."""


class IllegalTriageError(ReportQueueError):
    """Raised when a triage attempts to move a confirmed/dismissed report."""


class ReportQueue:
    """Thread-safe report queue with append-only JSONL audit chain.

    Constructor:
        audit_log_path: optional :class:`Path` for JSONL persistence.
            None -> in-memory only.
        now_fn: clock-injectable for hermetic tests (returns
            :class:`datetime` in UTC).

    Methods:
        file_report(target_kind, target_id, reason, ...)
            -> :class:`Report` newly added with status OPEN.
        triage(report_id, status, note, final_action)
            -> the mutated :class:`Report`. Raises
            :class:`UnknownReportError` / :class:`IllegalTriageError`.
        list_reports(status, target_kind, target_id)
            -> tuple[Report, ...] filtered by any combination.
        get(report_id) -> Optional[:class:`Report`].
        replay_from_log() -> int.
        verify_log_chain() -> bool.
    """

    def __init__(
        self,
        *,
        audit_log_path: Optional[Path] = None,
        now_fn: Optional["object"] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._reports: dict[str, Report] = {}
        self._last_hash: str = ""
        self._audit_log_path: Optional[Path] = (
            Path(audit_log_path) if audit_log_path else None
        )
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        if self._audit_log_path and self._audit_log_path.is_file():
            self.replay_from_log()

    def _now(self) -> datetime:
        result = self._now_fn()
        if isinstance(result, datetime):
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        return datetime.fromtimestamp(float(result), tz=timezone.utc)

    def _append_audit(self, event: _ReportEvent) -> None:
        if self._audit_log_path is None:
            return
        try:
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(event.to_jsonl_line() + "\n")
        except OSError as exc:
            LOGGER.warning(
                "Cannot append report-queue audit row to %s: %s",
                self._audit_log_path,
                exc,
            )

    def file_report(
        self,
        *,
        target_kind: ReportTargetKind,
        target_id: str,
        reason: str = "",
        version: str = "",
        reporter_voice_session: str = "",
        extras: Optional[Mapping[str, object]] = None,
    ) -> Report:
        """Append a new OPEN report.

        Returns the newly created :class:`Report`.
        """
        if not target_id:
            raise ValueError("target_id is required")
        with self._lock:
            now = self._now()
            ts = now.isoformat()
            report = Report(
                id=new_report_id(),
                target_kind=target_kind,
                target_id=target_id,
                reason=reason,
                version=version,
                reporter_voice_session=reporter_voice_session,
                created_at=ts,
                extras=dict(extras or {}),
            )
            event = _ReportEvent(
                op="file",
                report_id=report.id,
                timestamp=ts,
                payload=report.to_json_dict(),
                prev_hash=self._last_hash,
            )
            self._reports[report.id] = report
            self._last_hash = event.hash()
            self._append_audit(event)
            return report

    def triage(
        self,
        report_id: str,
        *,
        status: ReportStatus,
        note: str = "",
        final_action: FinalAction = FinalAction.NONE,
    ) -> Report:
        """Update ``report_id`` to ``status`` with optional metadata.

        Raises:
            :class:`UnknownReportError` if no report with the id
                exists.
            :class:`IllegalTriageError` if the report is already
                closed (CONFIRMED / DISMISSED) -- callers must
                explicitly re-open via a separate mutation if
                supported by the caller policy (single-user
                ultron currently does not).
            ValueError if status is OPEN (triage moves to a closed
                state; staying open is a no-op).
        """
        if status is ReportStatus.OPEN:
            raise ValueError("triage() cannot move a report back to OPEN")
        with self._lock:
            existing = self._reports.get(report_id)
            if existing is None:
                raise UnknownReportError(f"unknown report id {report_id!r}")
            if existing.status is not ReportStatus.OPEN:
                raise IllegalTriageError(
                    f"report {report_id!r} is already {existing.status.value}"
                )
            now = self._now()
            ts = now.isoformat()
            updated = Report(
                id=existing.id,
                target_kind=existing.target_kind,
                target_id=existing.target_id,
                reason=existing.reason,
                status=status,
                version=existing.version,
                reporter_voice_session=existing.reporter_voice_session,
                created_at=existing.created_at,
                triaged_at=ts,
                triage_note=note,
                final_action=final_action,
                extras=existing.extras,
            )
            event = _ReportEvent(
                op="triage",
                report_id=report_id,
                timestamp=ts,
                payload={
                    "status": status.value,
                    "note": note,
                    "final_action": final_action.value,
                },
                prev_hash=self._last_hash,
            )
            self._reports[report_id] = updated
            self._last_hash = event.hash()
            self._append_audit(event)
            return updated

    def get(self, report_id: str) -> Optional[Report]:
        """Return the :class:`Report` with id ``report_id`` or None."""
        with self._lock:
            return self._reports.get(report_id)

    def list_reports(
        self,
        *,
        status: Optional[ReportStatus] = None,
        target_kind: Optional[ReportTargetKind] = None,
        target_id: Optional[str] = None,
    ) -> tuple[Report, ...]:
        """Return all reports matching the (optional) filters."""
        with self._lock:
            out: list[Report] = []
            for report in self._reports.values():
                if status is not None and report.status is not status:
                    continue
                if target_kind is not None and report.target_kind is not target_kind:
                    continue
                if target_id is not None and report.target_id != target_id:
                    continue
                out.append(report)
            out.sort(key=lambda r: r.created_at)
            return tuple(out)

    def count(self, *, status: Optional[ReportStatus] = None) -> int:
        """Return the count of reports matching the (optional) status filter."""
        with self._lock:
            if status is None:
                return len(self._reports)
            return sum(
                1 for r in self._reports.values() if r.status is status
            )

    def replay_from_log(self) -> int:
        """Rebuild the in-memory state by replaying the audit log.

        Returns the number of events applied. Useful for tests and
        for the orchestrator-startup integrity check (verify the
        live state matches a fresh log replay).
        """
        if self._audit_log_path is None:
            return 0
        with self._lock:
            self._reports.clear()
            self._last_hash = ""
            applied = 0
            try:
                with self._audit_log_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        text = line.strip()
                        if not text:
                            continue
                        try:
                            record = json.loads(text)
                        except json.JSONDecodeError:
                            LOGGER.warning(
                                "Skipping malformed report-queue log row"
                            )
                            continue
                        op = str(record.get("op", ""))
                        report_id = str(record.get("report_id", ""))
                        payload = record.get("payload") or {}
                        if op == "file":
                            if isinstance(payload, Mapping):
                                report = Report.from_json_dict(payload)
                                self._reports[report.id] = report
                                self._last_hash = str(record.get("hash", ""))
                                applied += 1
                        elif op == "triage":
                            existing = self._reports.get(report_id)
                            if existing is None:
                                continue
                            try:
                                status = ReportStatus(
                                    str(payload.get("status", "open"))
                                )
                            except (ValueError, TypeError):
                                status = ReportStatus.OPEN
                            try:
                                final_action = FinalAction(
                                    str(payload.get("final_action", "none"))
                                )
                            except (ValueError, TypeError):
                                final_action = FinalAction.NONE
                            updated = Report(
                                id=existing.id,
                                target_kind=existing.target_kind,
                                target_id=existing.target_id,
                                reason=existing.reason,
                                status=status,
                                version=existing.version,
                                reporter_voice_session=existing.reporter_voice_session,
                                created_at=existing.created_at,
                                triaged_at=str(record.get("ts", "")),
                                triage_note=str(payload.get("note", "")),
                                final_action=final_action,
                                extras=existing.extras,
                            )
                            self._reports[report_id] = updated
                            self._last_hash = str(record.get("hash", ""))
                            applied += 1
            except FileNotFoundError:
                return 0
            return applied

    def verify_log_chain(self) -> bool:
        """Return True iff every audit-log row's ``prev_hash`` matches.

        Replays the log and recomputes each event's hash + chain
        linkage. Returns False on any mismatch / parse failure.
        """
        if self._audit_log_path is None or not self._audit_log_path.is_file():
            return True
        prev_hash = ""
        try:
            with self._audit_log_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        record = json.loads(text)
                    except json.JSONDecodeError:
                        return False
                    declared_prev = str(record.get("prev_hash", ""))
                    declared_hash = str(record.get("hash", ""))
                    if declared_prev != prev_hash:
                        return False
                    event = _ReportEvent(
                        op=str(record.get("op", "")),
                        report_id=str(record.get("report_id", "")),
                        timestamp=str(record.get("ts", "")),
                        payload=record.get("payload") or {},
                        prev_hash=declared_prev,
                    )
                    if event.hash() != declared_hash:
                        return False
                    prev_hash = declared_hash
        except OSError:
            return False
        return True


__all__ = [
    "FinalAction",
    "IllegalTriageError",
    "Report",
    "ReportQueue",
    "ReportQueueError",
    "ReportStatus",
    "ReportTargetKind",
    "UnknownReportError",
    "new_report_id",
]
