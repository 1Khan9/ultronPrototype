"""Stable-identity alias graph: rename / merge / transfer / reservation (T6).

T6 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Closes the "rename breaks references" gap for every namespace ultron
exposes. The marketplace pattern boils down to three operations
plus a soft-delete + reservation window, all driven through a
persistent + tamper-evident graph the resolver walks at every
lookup.

Operations (mirroring the upstream contract):

* :meth:`AliasGraph.rename` — slug A renamed to slug B. B becomes
  canonical; A becomes a forever-redirect to B.
* :meth:`AliasGraph.merge` — slug A merged into B. A stops appearing
  publicly; A redirects to B.
* :meth:`AliasGraph.transfer` — ownership of a slug moves from one
  owner to another. The slug stays canonical (no redirect created);
  the entry's owner field updates and the transfer is audit-logged.
* :meth:`AliasGraph.soft_delete` — owner deletes slug; slug enters a
  reservation state for :data:`DEFAULT_RESERVATION_DAYS` days during
  which only the original owner can re-register. After expiry the
  slug is claimable.
* :meth:`AliasGraph.hard_delete` — moderator / admin deletes slug; no
  reservation, immediately claimable, audit-logged.

Resolution (:meth:`AliasGraph.resolve`) walks the redirect chain,
detects cycles (caps depth at :data:`MAX_REDIRECT_DEPTH`), and returns
the terminal canonical name plus the metadata along the chain.

Persistence: a JSONL append-only audit log at
``data/identity/aliases.jsonl`` (configurable). Each row is one
:class:`AliasGraphEvent` envelope with a SHA-256 hash chain linking
it to the previous row (mirrors :mod:`ultron.safety.audit`). The
in-memory state is a derived projection; a hash-chain verifier can
replay the log to detect tampering.

Slug shape (:func:`validate_slug`): lowercase alphanumeric with dots,
hyphens, underscores; optional ``@scope/`` namespace prefix; 1-128
chars. Reserved names (admin / api / settings / etc.) refuse via
:class:`SlugReservedError`.

This module is the primitive; consumers compose it (the skill
registry asks the alias graph what canonical slug to load when a
user calls a renamed skill; the sandbox project store does the same
for project directories; etc.).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Optional

LOGGER = logging.getLogger(__name__)

#: Slug validation regex. Optional ``@scope/`` prefix; body is
#: lowercase alphanumeric + dot, underscore, hyphen. 1-128 chars
#: total (matches the upstream package-name pattern; ultron's slugs
#: reuse the shape).
SLUG_PATTERN: re.Pattern[str] = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]{0,62}/)?[a-z0-9][a-z0-9._-]{0,127}$"
)

#: Hard cap on resolve chain length. Above this -> cycle assumed.
MAX_REDIRECT_DEPTH: int = 32

#: Default reservation window after a soft-delete.
DEFAULT_RESERVATION_DAYS: int = 30

#: Hardcoded reserved slugs that can never be claimed by any owner.
#: Mirrors the upstream pattern but tailored to ultron's namespaces
#: (skills, intents, sandbox projects, voicepacks).
RESERVED_SLUGS: frozenset[str] = frozenset({
    # Generic platform reservations
    "admin",
    "api",
    "auth",
    "config",
    "console",
    "dashboard",
    "docs",
    "help",
    "internal",
    "login",
    "logout",
    "ops",
    "public",
    "root",
    "settings",
    "support",
    "system",
    "ultron",
    "user",
    "users",
    "well-known",
    # Ultron-protected slugs
    "soul",
    "identity",
    "persona",
    "voicepack",
    "voice",
    "safety",
    "validator",
    "audit",
    "k-category",
    "k_category",
})


class AliasOperation(str, Enum):
    """Discriminator for the audit-log envelope's ``op`` field."""

    REGISTER = "register"
    RENAME = "rename"
    MERGE = "merge"
    TRANSFER = "transfer"
    SOFT_DELETE = "soft_delete"
    HARD_DELETE = "hard_delete"
    RESERVE = "reserve"
    RELEASE = "release"


class InvalidSlugError(ValueError):
    """Raised when a slug fails :func:`validate_slug`."""

    def __init__(self, slug: str, reason: str) -> None:
        super().__init__(f"Invalid slug {slug!r}: {reason}")
        self.slug = slug
        self.reason = reason


class SlugReservedError(RuntimeError):
    """Raised when a slug is reserved or in its post-soft-delete window."""

    def __init__(self, slug: str, *, until: Optional[datetime] = None) -> None:
        suffix = f" until {until.isoformat()}" if until else " (hardcoded reservation)"
        super().__init__(f"Slug {slug!r} is reserved{suffix}")
        self.slug = slug
        self.until = until


class AliasResolveError(RuntimeError):
    """Raised when :meth:`AliasGraph.resolve` detects a cycle or unknown slug."""

    def __init__(self, slug: str, reason: str) -> None:
        super().__init__(f"Cannot resolve {slug!r}: {reason}")
        self.slug = slug
        self.reason = reason


def normalize_slug(slug: str) -> str:
    """Return the canonical lowercase form of ``slug``.

    Strips leading ``@`` repetitions (matches the upstream handle
    normaliser), case-folds, and strips outer whitespace. Does NOT
    enforce the validation regex; pair with :func:`validate_slug`
    when validation is required.
    """
    if slug is None:
        return ""
    cleaned = slug.strip()
    # Collapse leading @ duplicates ("@@@foo/bar" -> "@foo/bar").
    while cleaned.startswith("@@"):
        cleaned = cleaned[1:]
    return cleaned.casefold()


def validate_slug(slug: str) -> str:
    """Return ``normalize_slug(slug)`` after enforcing shape + reservation.

    Raises:
        :class:`InvalidSlugError` if the slug fails the shape regex.
        :class:`SlugReservedError` if the slug is in
            :data:`RESERVED_SLUGS`.
    """
    normalised = normalize_slug(slug)
    if not normalised:
        raise InvalidSlugError(slug, "empty after normalisation")
    if not SLUG_PATTERN.match(normalised):
        raise InvalidSlugError(slug, "does not match slug pattern")
    # Reservation check is against the un-scoped tail when present.
    # @scope/admin is allowed (the @scope binds it to the publisher);
    # bare admin is not.
    if "/" not in normalised and normalised in RESERVED_SLUGS:
        raise SlugReservedError(normalised)
    return normalised


@dataclass(frozen=True)
class AliasGraphEntry:
    """One alias-graph node.

    Fields:
        canonical: the canonical slug (what resolves to lookups).
            For redirects this is the target; for live entries this
            is the slug itself.
        owner: opaque owner identifier (handle / user id). Empty
            string for unowned entries (e.g. raw reservations).
        redirect_target: when set, this entry is a redirect to the
            named canonical. ``resolve`` walks the chain.
        reserved_until: timestamp after which the slug becomes
            claimable. None for active or hard-deleted entries.
        original_owner: the owner who held the slug when soft-deleted
            (so first-refusal can be honored). Empty otherwise.
        hidden: True for merged / soft-deleted entries that should
            not appear in public listings.
        last_event_at: timestamp of the most recent state-change.
        metadata: free-form opaque dict (callers attach
            consumer-specific metadata).
    """

    canonical: str
    owner: str = ""
    redirect_target: Optional[str] = None
    reserved_until: Optional[datetime] = None
    original_owner: str = ""
    hidden: bool = False
    last_event_at: Optional[datetime] = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "canonical": self.canonical,
            "owner": self.owner,
            "hidden": self.hidden,
        }
        if self.redirect_target:
            out["redirect_target"] = self.redirect_target
        if self.reserved_until is not None:
            out["reserved_until"] = self.reserved_until.isoformat()
        if self.original_owner:
            out["original_owner"] = self.original_owner
        if self.last_event_at is not None:
            out["last_event_at"] = self.last_event_at.isoformat()
        if self.metadata:
            out["metadata"] = dict(self.metadata)
        return out

    def is_redirect(self) -> bool:
        return self.redirect_target is not None

    def is_active(self, *, now: Optional[datetime] = None) -> bool:
        """Return True iff the entry is live (not hidden, not reserved)."""
        if self.hidden:
            return False
        if self.reserved_until is None:
            return True
        reference = now or datetime.now(timezone.utc)
        return reference >= self.reserved_until


@dataclass(frozen=True)
class AliasGraphEvent:
    """One audit-log event envelope (mirrors :mod:`ultron.safety.audit`).

    Each row carries an ``op`` discriminator, a payload (typed per
    op kind), the actor identifier, the timestamp, and a hash chain
    link to the previous row. Persisting the events as JSONL gives
    a tamper-evident replayable history.
    """

    op: AliasOperation
    slug: str
    actor: str
    at: datetime
    payload: Mapping[str, object] = field(default_factory=dict)
    prev_hash: str = ""

    def canonical_payload(self) -> str:
        """Return the canonical-JSON payload used for hash chaining.

        Sorted keys + ISO timestamps so the same logical event
        produces the same string across processes.
        """
        record = {
            "op": self.op.value,
            "slug": self.slug,
            "actor": self.actor,
            "at": self.at.isoformat(),
            "payload": dict(self.payload),
            "prev_hash": self.prev_hash,
        }
        return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)

    def hash(self) -> str:
        """Return SHA-256 of the canonical payload."""
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()

    def to_jsonl_line(self) -> str:
        """Return the line to append to the JSONL audit log."""
        record: dict[str, object] = {
            "op": self.op.value,
            "slug": self.slug,
            "actor": self.actor,
            "at": self.at.isoformat(),
            "payload": dict(self.payload),
            "prev_hash": self.prev_hash,
            "hash": self.hash(),
        }
        return json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)


class AliasGraph:
    """In-memory alias graph with optional JSONL audit-log persistence.

    The graph is keyed by :func:`normalize_slug` form so case + leading-@
    variants resolve uniformly. Operations acquire an internal
    :class:`threading.RLock`; concurrent callers (the orchestrator's
    skill registry + voice intent dispatcher both read the same
    graph) get consistent snapshots.

    Persistence: when ``audit_log_path`` is supplied at construction,
    every mutation appends a :class:`AliasGraphEvent` to the JSONL
    log atomically. The file is opened lazily on first write. The
    in-memory state is read-through from the log at construction
    time via :meth:`replay_from_log`. A missing log file is
    treated as an empty graph.
    """

    def __init__(
        self,
        *,
        audit_log_path: Optional[Path] = None,
        now_fn: Optional["object"] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, AliasGraphEntry] = {}
        self._last_hash: str = ""
        self._audit_log_path: Optional[Path] = (
            Path(audit_log_path) if audit_log_path else None
        )
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        if self._audit_log_path and self._audit_log_path.is_file():
            self.replay_from_log()

    # ----- private helpers -------------------------------------------------

    def _now(self) -> datetime:
        result = self._now_fn()
        if isinstance(result, datetime):
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        # tolerate Unix-epoch seconds callers
        return datetime.fromtimestamp(float(result), tz=timezone.utc)

    def _record(
        self,
        op: AliasOperation,
        slug: str,
        actor: str,
        payload: Mapping[str, object],
    ) -> AliasGraphEvent:
        event = AliasGraphEvent(
            op=op,
            slug=slug,
            actor=actor or "",
            at=self._now(),
            payload=payload,
            prev_hash=self._last_hash,
        )
        self._last_hash = event.hash()
        self._append_audit(event)
        return event

    def _append_audit(self, event: AliasGraphEvent) -> None:
        if self._audit_log_path is None:
            return
        try:
            self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_log_path.open("a", encoding="utf-8") as handle:
                handle.write(event.to_jsonl_line() + "\n")
        except OSError as exc:
            LOGGER.warning(
                "Cannot append alias-graph audit row to %s: %s",
                self._audit_log_path,
                exc,
            )

    def _apply_event_to_state(self, event: AliasGraphEvent) -> None:
        """Mutate ``self._entries`` to reflect ``event``.

        Used both by live operations and by :meth:`replay_from_log`.
        Each branch matches the operation's payload contract; unknown
        operations log a WARN and are silently skipped (so log replay
        survives future schema additions).
        """
        slug = event.slug
        payload = event.payload
        op = event.op
        if op is AliasOperation.REGISTER:
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner=str(payload.get("owner", "")),
                last_event_at=event.at,
                metadata=dict(payload.get("metadata") or {}),
            )
            return
        if op is AliasOperation.RENAME:
            new_slug = str(payload["new_slug"])
            existing = self._entries.get(slug)
            owner = existing.owner if existing else str(payload.get("owner", ""))
            # New canonical entry inherits the owner.
            self._entries[new_slug] = AliasGraphEntry(
                canonical=new_slug,
                owner=owner,
                last_event_at=event.at,
                metadata=dict(existing.metadata) if existing else {},
            )
            # Old slug becomes a redirect to new.
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner=owner,
                redirect_target=new_slug,
                hidden=False,
                last_event_at=event.at,
            )
            return
        if op is AliasOperation.MERGE:
            target = str(payload["target"])
            existing = self._entries.get(slug)
            owner = existing.owner if existing else ""
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner=owner,
                redirect_target=target,
                hidden=True,
                last_event_at=event.at,
            )
            return
        if op is AliasOperation.TRANSFER:
            new_owner = str(payload["to_owner"])
            existing = self._entries.get(slug)
            if existing is None:
                # transfer-of-unknown is a register implicit
                self._entries[slug] = AliasGraphEntry(
                    canonical=slug,
                    owner=new_owner,
                    last_event_at=event.at,
                )
                return
            self._entries[slug] = AliasGraphEntry(
                canonical=existing.canonical,
                owner=new_owner,
                redirect_target=existing.redirect_target,
                reserved_until=existing.reserved_until,
                original_owner=existing.original_owner,
                hidden=existing.hidden,
                last_event_at=event.at,
                metadata=existing.metadata,
            )
            return
        if op is AliasOperation.SOFT_DELETE:
            days_raw = payload.get("reservation_days", DEFAULT_RESERVATION_DAYS)
            try:
                days = int(days_raw)
            except (TypeError, ValueError):
                days = DEFAULT_RESERVATION_DAYS
            reserved_until = event.at + timedelta(days=max(0, days))
            existing = self._entries.get(slug)
            owner = existing.owner if existing else ""
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner=owner,
                redirect_target=None,
                reserved_until=reserved_until,
                original_owner=owner,
                hidden=True,
                last_event_at=event.at,
            )
            return
        if op is AliasOperation.HARD_DELETE:
            existing = self._entries.get(slug)
            if existing is None:
                return
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner="",
                redirect_target=None,
                reserved_until=None,
                original_owner="",
                hidden=True,
                last_event_at=event.at,
            )
            return
        if op is AliasOperation.RESERVE:
            until_raw = payload.get("until")
            if isinstance(until_raw, str):
                try:
                    until = datetime.fromisoformat(until_raw)
                    if until.tzinfo is None:
                        until = until.replace(tzinfo=timezone.utc)
                except ValueError:
                    until = event.at + timedelta(days=DEFAULT_RESERVATION_DAYS)
            else:
                until = event.at + timedelta(days=DEFAULT_RESERVATION_DAYS)
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner=str(payload.get("original_owner", "")),
                redirect_target=None,
                reserved_until=until,
                original_owner=str(payload.get("original_owner", "")),
                hidden=True,
                last_event_at=event.at,
            )
            return
        if op is AliasOperation.RELEASE:
            existing = self._entries.get(slug)
            if existing is None:
                return
            self._entries[slug] = AliasGraphEntry(
                canonical=slug,
                owner="",
                redirect_target=None,
                reserved_until=None,
                original_owner="",
                hidden=True,
                last_event_at=event.at,
            )
            return
        LOGGER.warning(
            "Skipping alias-graph event with unknown op %r at %s",
            op,
            event.at,
        )

    # ----- public operations -----------------------------------------------

    def register(
        self,
        slug: str,
        *,
        owner: str = "",
        metadata: Optional[Mapping[str, object]] = None,
        actor: str = "",
    ) -> AliasGraphEntry:
        """Register ``slug`` as canonical with no redirect.

        Raises :class:`InvalidSlugError` / :class:`SlugReservedError`
        on shape / reservation violations. If the slug is already
        registered and not in a reservation/redirect state, returns
        the existing entry (idempotent).
        """
        normalised = validate_slug(slug)
        with self._lock:
            existing = self._entries.get(normalised)
            if existing is not None and existing.is_active(now=self._now()):
                return existing
            if existing is not None and existing.reserved_until is not None:
                # Reserved -- only original owner may re-register.
                now = self._now()
                if existing.reserved_until > now and existing.original_owner != owner:
                    raise SlugReservedError(normalised, until=existing.reserved_until)
            payload: dict[str, object] = {"owner": owner}
            if metadata:
                payload["metadata"] = dict(metadata)
            event = self._record(AliasOperation.REGISTER, normalised, actor, payload)
            self._apply_event_to_state(event)
            return self._entries[normalised]

    def rename(
        self,
        old: str,
        new: str,
        *,
        actor: str = "",
    ) -> tuple[AliasGraphEntry, AliasGraphEntry]:
        """Rename ``old`` to ``new``. ``new`` becomes canonical; ``old`` redirects.

        Returns ``(new_entry, old_entry_as_redirect)``.

        Raises:
            :class:`AliasResolveError` if ``old`` doesn't resolve to
                a live entry.
            :class:`InvalidSlugError` on shape failures.
            :class:`SlugReservedError` if ``new`` is reserved or
                hardcoded.
        """
        old_n = validate_slug(old)
        new_n = validate_slug(new)
        if old_n == new_n:
            raise InvalidSlugError(new, "rename target must differ from source")
        with self._lock:
            current = self._entries.get(old_n)
            if current is None or current.is_redirect() or current.hidden:
                raise AliasResolveError(old, "no live entry to rename")
            # Refuse if new is already taken AND not the source.
            target_existing = self._entries.get(new_n)
            if target_existing is not None and target_existing.is_active(now=self._now()):
                raise InvalidSlugError(new, "target slug already taken")
            event = self._record(
                AliasOperation.RENAME,
                old_n,
                actor,
                {"new_slug": new_n, "owner": current.owner},
            )
            self._apply_event_to_state(event)
            return (self._entries[new_n], self._entries[old_n])

    def merge(self, source: str, target: str, *, actor: str = "") -> AliasGraphEntry:
        """Merge ``source`` into ``target``. ``source`` becomes a hidden redirect.

        Both slugs must validate. ``target`` must be a live canonical
        entry. ``source`` becomes ``hidden=True`` and redirects to
        the target's terminal canonical.
        """
        source_n = validate_slug(source)
        target_n = validate_slug(target)
        if source_n == target_n:
            raise InvalidSlugError(target, "merge target must differ from source")
        with self._lock:
            target_entry = self._entries.get(target_n)
            if target_entry is None:
                raise AliasResolveError(target, "merge target does not exist")
            terminal = self.resolve(target_n)
            event = self._record(
                AliasOperation.MERGE,
                source_n,
                actor,
                {"target": terminal.canonical},
            )
            self._apply_event_to_state(event)
            return self._entries[source_n]

    def transfer(
        self,
        slug: str,
        to_owner: str,
        *,
        actor: str = "",
    ) -> AliasGraphEntry:
        """Transfer ownership of ``slug`` to ``to_owner``. No redirect created."""
        slug_n = validate_slug(slug)
        if not to_owner:
            raise ValueError("transfer requires a non-empty to_owner")
        with self._lock:
            existing = self._entries.get(slug_n)
            if existing is None:
                raise AliasResolveError(slug, "cannot transfer unknown slug")
            event = self._record(
                AliasOperation.TRANSFER,
                slug_n,
                actor,
                {
                    "to_owner": to_owner,
                    "from_owner": existing.owner,
                },
            )
            self._apply_event_to_state(event)
            return self._entries[slug_n]

    def soft_delete(
        self,
        slug: str,
        *,
        reservation_days: int = DEFAULT_RESERVATION_DAYS,
        actor: str = "",
    ) -> AliasGraphEntry:
        """Soft-delete ``slug`` with a ``reservation_days``-day reservation.

        The slug enters ``hidden=True`` + ``reserved_until=now+days``.
        Only the original owner may re-register inside the window;
        after expiry the slug becomes claimable by anyone via
        :meth:`register`.
        """
        slug_n = validate_slug(slug)
        if reservation_days < 0:
            raise ValueError("reservation_days must be >= 0")
        with self._lock:
            event = self._record(
                AliasOperation.SOFT_DELETE,
                slug_n,
                actor,
                {"reservation_days": reservation_days},
            )
            self._apply_event_to_state(event)
            return self._entries[slug_n]

    def hard_delete(self, slug: str, *, actor: str = "") -> AliasGraphEntry:
        """Hard-delete ``slug`` with no reservation (admin / moderator only).

        The entry becomes ``hidden=True`` immediately and the slug is
        claimable by anyone on the next :meth:`register`.
        """
        slug_n = validate_slug(slug)
        with self._lock:
            event = self._record(
                AliasOperation.HARD_DELETE,
                slug_n,
                actor,
                {},
            )
            self._apply_event_to_state(event)
            return self._entries[slug_n]

    def resolve(self, slug: str) -> AliasGraphEntry:
        """Resolve ``slug`` through the redirect chain to its canonical entry.

        Walks at most :data:`MAX_REDIRECT_DEPTH` hops. A cycle (or
        depth-overflow) raises :class:`AliasResolveError`. An unknown
        slug also raises :class:`AliasResolveError`.
        """
        normalised = normalize_slug(slug)
        with self._lock:
            visited: list[str] = [normalised]
            current = normalised
            for _ in range(MAX_REDIRECT_DEPTH):
                entry = self._entries.get(current)
                if entry is None:
                    raise AliasResolveError(slug, "unknown slug")
                if entry.redirect_target is None:
                    return entry
                next_slug = entry.redirect_target
                if next_slug in visited:
                    raise AliasResolveError(
                        slug,
                        f"cycle in redirect chain ({' -> '.join(visited)} -> {next_slug})",
                    )
                visited.append(next_slug)
                current = next_slug
            raise AliasResolveError(slug, "redirect chain exceeded MAX_REDIRECT_DEPTH")

    def get(self, slug: str) -> Optional[AliasGraphEntry]:
        """Return the raw entry for ``slug`` (no chain walk). None if absent."""
        normalised = normalize_slug(slug)
        with self._lock:
            return self._entries.get(normalised)

    def is_claimable(self, slug: str, *, by_owner: Optional[str] = None) -> bool:
        """Return True iff ``slug`` is currently claimable by ``by_owner``.

        A slug is claimable if (a) no entry exists, OR (b) the entry
        is reserved and the reservation has lapsed, OR (c) the entry
        is reserved AND ``by_owner`` matches the original owner.
        """
        try:
            normalised = validate_slug(slug)
        except (InvalidSlugError, SlugReservedError):
            return False
        with self._lock:
            entry = self._entries.get(normalised)
            if entry is None:
                return True
            if entry.is_active(now=self._now()):
                return False
            if entry.reserved_until is None:
                # hidden but not reserved (hard-deleted) -> claimable
                return True
            now = self._now()
            if entry.reserved_until <= now:
                return True
            if by_owner and by_owner == entry.original_owner:
                return True
            return False

    def list_active(self) -> tuple[AliasGraphEntry, ...]:
        """Return the entries currently live (canonical, not redirect / hidden / reserved)."""
        with self._lock:
            now = self._now()
            return tuple(
                e for e in self._entries.values()
                if not e.is_redirect() and e.is_active(now=now)
            )

    def list_redirects(self) -> tuple[AliasGraphEntry, ...]:
        """Return the entries acting as redirects."""
        with self._lock:
            return tuple(e for e in self._entries.values() if e.is_redirect())

    def list_reserved(self) -> tuple[AliasGraphEntry, ...]:
        """Return the entries currently in their reservation window."""
        with self._lock:
            now = self._now()
            return tuple(
                e for e in self._entries.values()
                if e.reserved_until is not None and e.reserved_until > now
            )

    # ----- log replay + verification ---------------------------------------

    def replay_from_log(self) -> int:
        """Re-derive in-memory state by re-reading the audit log.

        Returns the number of events applied. Useful for tests + for
        the orchestrator-startup integrity check (verify the live
        in-memory state matches a fresh log replay).
        """
        if self._audit_log_path is None:
            return 0
        with self._lock:
            self._entries.clear()
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
                        except json.JSONDecodeError as exc:
                            LOGGER.warning(
                                "Skipping malformed alias-graph log row: %s",
                                exc,
                            )
                            continue
                        try:
                            op = AliasOperation(record["op"])
                            at_raw = record["at"]
                            at = datetime.fromisoformat(at_raw)
                            if at.tzinfo is None:
                                at = at.replace(tzinfo=timezone.utc)
                            event = AliasGraphEvent(
                                op=op,
                                slug=str(record["slug"]),
                                actor=str(record.get("actor", "")),
                                at=at,
                                payload=record.get("payload") or {},
                                prev_hash=str(record.get("prev_hash", "")),
                            )
                        except (KeyError, ValueError) as exc:
                            LOGGER.warning(
                                "Skipping alias-graph log row missing fields: %s",
                                exc,
                            )
                            continue
                        self._apply_event_to_state(event)
                        self._last_hash = event.hash()
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
                    try:
                        event = AliasGraphEvent(
                            op=AliasOperation(record["op"]),
                            slug=str(record["slug"]),
                            actor=str(record.get("actor", "")),
                            at=datetime.fromisoformat(record["at"]).replace(
                                tzinfo=timezone.utc
                            )
                            if "T" in str(record["at"]) and "+" not in str(record["at"])
                            and "Z" not in str(record["at"])
                            else datetime.fromisoformat(record["at"]),
                            payload=record.get("payload") or {},
                            prev_hash=declared_prev,
                        )
                    except (KeyError, ValueError):
                        return False
                    if event.hash() != declared_hash:
                        return False
                    prev_hash = declared_hash
        except OSError:
            return False
        return True


def _iter_entries(graph: AliasGraph) -> Iterable[tuple[str, AliasGraphEntry]]:
    """Yield ``(slug, entry)`` pairs from ``graph`` (for tests + introspection)."""
    with graph._lock:                                                       # noqa: SLF001
        return tuple(graph._entries.items())                                # noqa: SLF001


__all__ = [
    "SLUG_PATTERN",
    "MAX_REDIRECT_DEPTH",
    "DEFAULT_RESERVATION_DAYS",
    "RESERVED_SLUGS",
    "AliasOperation",
    "AliasGraphEntry",
    "AliasGraphEvent",
    "AliasGraph",
    "InvalidSlugError",
    "SlugReservedError",
    "AliasResolveError",
    "normalize_slug",
    "validate_slug",
]
