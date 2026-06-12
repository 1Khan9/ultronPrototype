"""Runtime service that drives kenning's evolution loop end-to-end.

Catalog 13 clean-room. This bundles the engine modules into a single
orchestrator-facing surface so the orchestrator's own wiring stays tiny +
obviously fail-open:

* :class:`EvolutionStore` -- lock-guarded, append-only JSONL persistence
  under ``data/evolution/`` (success capsules, failure records, a
  hash-chained audit ledger, the gate state, the personality profile);
* :class:`EvolutionService` -- holds the autonomy controller + personality
  tuner + the :class:`~kenning.evolution.evolution_loop.EvolutionLoop`,
  records per-turn satisfaction + success capsules, runs cycles
  single-flight (on a daemon thread for the autonomous trigger), and
  exposes the temperament hint + the periodic digest.

Everything is fail-open: a construction or runtime failure degrades to a
disabled service / a no-op, never to a crashed voice path. Zero network.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from kenning.evolution.autonomy import TieredAutonomyController
from kenning.evolution.evolution_loop import (
    ApplyStatus,
    CheckpointHook,
    EvolutionLoop,
    EvolutionLoopConfig,
    EvolutionState,
)
from kenning.evolution.guardrails import (
    GuardrailBaseline,
    GuardrailSample,
    RollbackRecord,
    evaluate_guardrails,
)
from kenning.evolution.models import (
    BlastRadius,
    Capsule,
    CommandFailureSignal,
    CorrectionCapsule,
    EvolutionEvent,
    FeatureRequestCapsule,
    KnowledgeGapCapsule,
    Outcome,
    OutcomeStatus,
    PersonalityState,
    canonicalize,
    derive_pattern_key,
    new_capsule_id,
    new_event_id,
)
from kenning.evolution.personality import (
    PersonalityFeedback,
    PersonalityTuner,
    apply_temperament,
)
from kenning.evolution.signals import (
    COSMETIC_SIGNALS,
    extract_command_failure,
    extract_correction,
    extract_feature_request,
    extract_knowledge_gap,
    has_opportunity_signal,
    signal_base,
)
from kenning.utils.logging import get_logger

logger = get_logger("evolution.service")

_GENESIS_HASH = "0" * 64
DEFAULT_CAPSULE_LOAD_LIMIT = 400
DEFAULT_CYCLE_CHECK_INTERVAL_TURNS = 25
DEFAULT_TURN_CAPSULE_SCORE = 0.8
PERSONALITY_SAVE_EVERY_TURNS = 10
DEFAULT_RECURRENCE_THRESHOLD = 3
DEFAULT_PRE_TURN_NUDGE_MAX_CHARS = 240
# Guardrail auto-revert brake (#15+#65): how many further turns a KEPT
# proposal is monitored before the post-apply re-check, and the (smaller)
# minimum-sample floors used over that short post-apply window. The
# pre-apply snapshot uses the sampler's own (larger) floors.
DEFAULT_POST_APPLY_MONITOR_TURNS = 8
POST_APPLY_MIN_LATENCY_SAMPLES = 3
POST_APPLY_MIN_RATE_SAMPLES = 5


def _now_iso() -> str:
    """Current UTC time as an ISO-8601 string (matches models._now_iso)."""
    return datetime.now(timezone.utc).isoformat()


class EvolutionStore:
    """Lock-guarded append-only JSONL persistence under ``data/evolution/``."""

    def __init__(self, data_dir: Path | str) -> None:
        self._dir = Path(data_dir)
        self._lock = threading.RLock()
        self.capsules_path = self._dir / "capsules.jsonl"
        self.failed_path = self._dir / "failed_capsules.jsonl"
        self.events_path = self._dir / "events.jsonl"
        self.state_path = self._dir / "state.json"
        self.personality_path = self._dir / "personality.json"
        # Catalog 14 -- qualitative conversation-event ledgers.
        self.corrections_path = self._dir / "corrections.jsonl"
        self.knowledge_gaps_path = self._dir / "knowledge_gaps.jsonl"
        self.command_failures_path = self._dir / "command_failures.jsonl"
        self.feature_requests_path = self._dir / "feature_requests.jsonl"

    def _append(self, path: Path, line: str) -> None:
        with self._lock:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution store append failed (%s): %s", path.name, exc)

    def _read_lines(self, path: Path) -> list[str]:
        with self._lock:
            try:
                if not path.exists():
                    return []
                with open(path, encoding="utf-8") as fh:
                    return fh.readlines()
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution store read failed (%s): %s", path.name, exc)
                return []

    # -- capsules -----------------------------------------------------------

    def append_capsule(self, capsule: Capsule) -> None:
        self._append(self.capsules_path, canonicalize(capsule))

    def load_recent_capsules(self, limit: int = DEFAULT_CAPSULE_LOAD_LIMIT) -> list[dict]:
        return self._parse_jsonl(self.capsules_path, limit)

    def count_capsules(self) -> int:
        return len([ln for ln in self._read_lines(self.capsules_path) if ln.strip()])

    # -- failures -----------------------------------------------------------

    def append_failure(self, failure: dict) -> None:
        self._append(self.failed_path, json.dumps(failure, ensure_ascii=False))

    def load_failures(self, limit: int = DEFAULT_CAPSULE_LOAD_LIMIT) -> list[dict]:
        return self._parse_jsonl(self.failed_path, limit)

    def _parse_jsonl(self, path: Path, limit: int) -> list[dict]:
        out: list[dict] = []
        for ln in self._read_lines(path)[-limit:]:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:  # noqa: BLE001 -- skip a torn / malformed tail line
                continue
        return out

    def _count_lines(self, path: Path) -> int:
        return len([ln for ln in self._read_lines(path) if ln.strip()])

    # -- catalog 14 qualitative ledgers -------------------------------------

    def append_correction(self, record: Any) -> None:
        self._append(self.corrections_path, canonicalize(record))

    def load_corrections(self, limit: int = DEFAULT_CAPSULE_LOAD_LIMIT) -> list[dict]:
        return self._parse_jsonl(self.corrections_path, limit)

    def count_corrections(self) -> int:
        return self._count_lines(self.corrections_path)

    def append_knowledge_gap(self, record: Any) -> None:
        self._append(self.knowledge_gaps_path, canonicalize(record))

    def load_knowledge_gaps(self, limit: int = DEFAULT_CAPSULE_LOAD_LIMIT) -> list[dict]:
        return self._parse_jsonl(self.knowledge_gaps_path, limit)

    def append_command_failure(self, record: Any) -> None:
        self._append(self.command_failures_path, canonicalize(record))

    def load_command_failures(self, limit: int = DEFAULT_CAPSULE_LOAD_LIMIT) -> list[dict]:
        return self._parse_jsonl(self.command_failures_path, limit)

    def append_feature_request(self, record: Any) -> None:
        self._append(self.feature_requests_path, canonicalize(record))

    def load_feature_requests(self, limit: int = DEFAULT_CAPSULE_LOAD_LIMIT) -> list[dict]:
        return self._parse_jsonl(self.feature_requests_path, limit)

    def count_feature_requests(self) -> int:
        return self._count_lines(self.feature_requests_path)

    # -- hash-chained audit ledger ------------------------------------------

    def append_event(self, event: Any) -> None:
        with self._lock:
            prev = self._last_event_hash()
            body = canonicalize(event)
            digest = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
            try:
                row = json.dumps(
                    {"hash": digest, "prev": prev, "event": json.loads(body)}, ensure_ascii=False
                )
            except Exception:  # noqa: BLE001
                return
            self._append(self.events_path, row)

    def _last_event_hash(self) -> str:
        for ln in reversed(self._read_lines(self.events_path)):
            ln = ln.strip()
            if not ln:
                continue
            try:
                return str(json.loads(ln).get("hash", _GENESIS_HASH))
            except Exception:  # noqa: BLE001
                continue
        return _GENESIS_HASH

    def verify_event_chain(self) -> tuple[bool, Optional[int]]:
        """Re-walk the audit ledger; return ``(ok, first_break_index)``."""
        prev = _GENESIS_HASH
        for idx, ln in enumerate(self._read_lines(self.events_path)):
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
                body = canonicalize(row.get("event", {}))
                expected = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
            except Exception:  # noqa: BLE001
                return (False, idx)
            if row.get("prev") != prev or row.get("hash") != expected:
                return (False, idx)
            prev = expected
        return (True, None)

    # -- state + personality ------------------------------------------------

    def load_state(self) -> EvolutionState:
        with self._lock:
            try:
                if self.state_path.exists():
                    data = json.loads(self.state_path.read_text(encoding="utf-8"))
                    return EvolutionState(
                        last_distillation_at=data.get("last_distillation_at"),
                        last_data_hash=str(data.get("last_data_hash", "")),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution state load failed: %s", exc)
        return EvolutionState()

    def save_state(self, state: EvolutionState) -> None:
        with self._lock:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                self.state_path.write_text(
                    json.dumps(
                        {
                            "last_distillation_at": state.last_distillation_at,
                            "last_data_hash": state.last_data_hash,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution state save failed: %s", exc)

    def load_personality(self) -> dict:
        with self._lock:
            try:
                if self.personality_path.exists():
                    return json.loads(self.personality_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution personality load failed: %s", exc)
        return {}

    def save_personality(self, data: dict) -> None:
        with self._lock:
            try:
                self._dir.mkdir(parents=True, exist_ok=True)
                self.personality_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution personality save failed: %s", exc)


def _build_checkpoint(data_dir: Path, proposal_dir: Path) -> Optional[CheckpointHook]:
    """Build a shadow-repo checkpoint over the proposal directory, or
    ``None`` (the loop falls back to delete-revert)."""
    try:
        from kenning.checkpoints.registry import CheckpointRegistry

        registry = CheckpointRegistry(checkpoints_root=data_dir.parent / "checkpoints")
        manager = registry.get_or_create("evolution-skills", workspace_path=proposal_dir)

        def _take() -> str:
            commit = manager.on_event("evolution", force=True)
            return commit.commit_hash if commit is not None else ""

        def _restore(token: str) -> bool:
            if not token:
                return False
            plan = manager.plan_workspace_rewind(target_commit_hash=token)
            outcome = manager.restore(plan)
            return bool(outcome.workspace_reset_succeeded)

        return CheckpointHook(take=_take, restore=_restore)
    except Exception as exc:  # noqa: BLE001
        logger.debug("evolution checkpoint unavailable (delete-revert fallback): %s", exc)
        return None


def _maybe_get_approval() -> Any:
    try:
        from kenning.safety.two_phase_approval import get_approval_registry

        return get_approval_registry()
    except Exception:  # noqa: BLE001
        return None


class EvolutionService:
    """The orchestrator-facing evolution runtime."""

    def __init__(
        self,
        *,
        config: Any,
        store: EvolutionStore,
        autonomy: TieredAutonomyController,
        personality: PersonalityTuner,
        loop: EvolutionLoop,
        state: EvolutionState,
        proposal_dir: Path,
        registry_reloader: Optional[Callable[[], None]] = None,
        turn_metrics: Any = None,
        guardrail_sampler: Optional[Callable[[], GuardrailSample]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._store = store
        self._autonomy = autonomy
        self._personality = personality
        self._loop = loop
        self._state = state
        self._proposal_dir = proposal_dir
        self._registry_reloader = registry_reloader
        # Guardrail brake (#15+#65): the per-turn metrics ring (fed with
        # quality flags from record_turn) + the sampler the post-apply
        # watcher uses. Both optional -- None degrades to the brakeless
        # legacy behaviour (guardrails skipped, never tripped).
        self._turn_metrics = turn_metrics
        self._guardrail_sampler = guardrail_sampler
        self._watch_lock = threading.Lock()
        self._post_apply_watch: Optional[dict] = None
        self._pending_narration: Optional[str] = None
        self._clock = clock
        self._cycle_lock = threading.Lock()
        self._turns_since_check = 0
        self._closed = False
        # Catalog 14: in-memory recurrence + pending counters, rebuilt once
        # from the persisted ledgers (zero per-turn IO thereafter).
        self._pattern_recurrence: dict[str, int] = {}
        self._pattern_first_seen: dict[str, str] = {}
        self._pending_feature_requests: int = 0
        self._pending_corrections: int = 0
        self._load_capture_state()

    @classmethod
    def from_config(
        cls,
        config: Any,
        *,
        project_root: Path | str,
        registry_reloader: Optional[Callable[[], None]] = None,
        guardrail_sampler: Optional[Callable[[], GuardrailSample]] = None,
        approval: Any = None,
        clock: Callable[[], float] = time.time,
    ) -> Optional["EvolutionService"]:
        """Build the full service from config, or ``None`` when evolution is
        disabled / construction fails (fail-open)."""
        ev = getattr(config, "evolution", None)
        if ev is None or not getattr(ev, "enabled", False):
            return None
        try:
            data_dir = Path(project_root) / "data" / "evolution"
            proposal_dir = data_dir / "skills"
            proposal_dir.mkdir(parents=True, exist_ok=True)
            store = EvolutionStore(data_dir)
            state = store.load_state()
            autonomy = TieredAutonomyController(
                pause_on_demote=bool(getattr(ev, "pause_on_demote", False))
            )
            personality = PersonalityTuner.from_dict(store.load_personality())
            checkpoint = _build_checkpoint(data_dir, proposal_dir)
            # Guardrail brake (#15+#65): when monitoring is enabled and no
            # explicit sampler was injected, build the per-turn metrics ring
            # + sampler here so the loop's guardrails see REAL data. The
            # orchestrator feeds the ring (TTFT + error flags); record_turn
            # feeds the quality flags. Fail-open: any construction error
            # falls back to the brakeless empty sampler.
            turn_metrics = None
            sampler = guardrail_sampler
            if sampler is None and bool(getattr(ev, "guardrail_monitoring_enabled", True)):
                try:
                    from kenning.evolution.turn_metrics import (
                        TurnMetricsRing,
                        build_guardrail_sampler,
                    )

                    turn_metrics = TurnMetricsRing(
                        window=int(getattr(ev, "guardrail_window_turns", 40))
                    )
                    sampler = build_guardrail_sampler(
                        turn_metrics,
                        min_latency_samples=int(
                            getattr(ev, "guardrail_min_latency_samples", 5)
                        ),
                        min_rate_samples=int(
                            getattr(ev, "guardrail_min_rate_samples", 10)
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("guardrail metrics ring unavailable: %s", exc)
                    turn_metrics = None
                    sampler = None
            if sampler is None:
                sampler = lambda: GuardrailSample()  # noqa: E731 -- brakeless fallback
            approval_registry = approval if approval is not None else _maybe_get_approval()
            loop = EvolutionLoop(
                repo_root=Path(project_root),
                proposal_dir=proposal_dir,
                capsules_provider=store.load_recent_capsules,
                failures_provider=store.load_failures,
                autonomy=autonomy,
                baseline=GuardrailBaseline(),
                guardrail_sampler=sampler,
                checkpoint=checkpoint,
                approval=approval_registry,
                audit_sink=store.append_event,
                capsule_sink=None,  # capsules come from real turns, not from keeping a proposal
                failure_sink=store.append_failure,
                personality_provider=lambda: personality.state,
                state=state,
                config=EvolutionLoopConfig(
                    surface="skills",
                    enabled=True,
                    max_steps=int(getattr(ev, "max_steps", 3)),
                ),
                clock=clock,
            )
            return cls(
                config=ev,
                store=store,
                autonomy=autonomy,
                personality=personality,
                loop=loop,
                state=state,
                proposal_dir=proposal_dir,
                registry_reloader=registry_reloader,
                turn_metrics=turn_metrics,
                guardrail_sampler=sampler,
                clock=clock,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("evolution service construction failed: %s", exc)
            return None

    # -- per-turn -----------------------------------------------------------

    def record_turn(
        self,
        *,
        user_text: str = "",
        signals: Sequence[str] = (),
        corrected: bool = False,
        re_asked: bool = False,
        barged_in: bool = False,
        response_summary: str = "",
        prior_response: str = "",
    ) -> None:
        """Record a turn's satisfaction signals (tune the temperament), the
        catalog-14 qualitative capture events (corrections / knowledge gaps /
        feature requests detected from the utterance + the PRIOR response),
        and -- on a successfully-handled opportunity -- a success capsule that
        feeds future distillation. Fail-open."""
        if self._closed:
            return
        try:
            # Catalog 14 (T1/T2): qualitative conversation-event capture. A
            # detected correction also flips ``corrected`` so the temperament
            # tuner reacts (raise rigor / lower risk) even when the caller did
            # not pre-classify the turn.
            detected_correction = self._maybe_capture_correction(user_text, prior_response)
            self._maybe_capture_knowledge_gap(user_text, prior_response)
            self._maybe_capture_feature_request(user_text)
            corrected = corrected or detected_correction

            # Guardrail brake (#15+#65): feed the quality flags into the
            # per-turn metrics ring (the correction/re-ask/barge-in rate is
            # the "quality" guardrail's signal) and advance the post-apply
            # watch for any recently-kept proposal. Both fail-open.
            if self._turn_metrics is not None:
                try:
                    self._turn_metrics.note_quality(
                        corrected=corrected, re_asked=re_asked, barged_in=barged_in
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("turn-metrics quality note failed: %s", exc)
            self._tick_post_apply_watch()

            feedback = PersonalityFeedback(corrected=corrected, re_asked=re_asked, barged_in=barged_in)
            self._personality.record_feedback(feedback)
            self._personality.record_outcome(1.0 if feedback.satisfied else 0.0)
            if feedback.satisfied and has_opportunity_signal(signals):
                opportunity = [s for s in signals if has_opportunity_signal([s])]
                trigger = opportunity or list(signals)
                capsule = Capsule(
                    id=new_capsule_id(),
                    trigger=trigger,
                    gene="ad_hoc",
                    summary=(response_summary or user_text)[:200],
                    confidence=DEFAULT_TURN_CAPSULE_SCORE,
                    outcome=Outcome(status=OutcomeStatus.SUCCESS, score=DEFAULT_TURN_CAPSULE_SCORE),
                    success_streak=1,
                    pattern_key=derive_pattern_key(signals=trigger, gene="ad_hoc", kind="capsule"),
                )
                capsule = self._stamp_recurrence(capsule)
                self._store.append_capsule(capsule)
            self._turns_since_check += 1
            if self._turns_since_check % PERSONALITY_SAVE_EVERY_TURNS == 0:
                self._store.save_personality(self._personality.to_dict())
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution record_turn failed: %s", exc)

    # -- catalog 14: qualitative capture + recurrence -----------------------

    def _recurrence_threshold(self) -> int:
        """The configured pattern recurrence threshold (>=2; default 3)."""
        try:
            return max(2, int(getattr(self._config, "recurrence_threshold", DEFAULT_RECURRENCE_THRESHOLD)))
        except (TypeError, ValueError):
            return DEFAULT_RECURRENCE_THRESHOLD

    def _load_capture_state(self) -> None:
        """Rebuild the in-memory recurrence + pending counters from the
        persisted ledgers (one-time, at construction). Fail-open."""
        try:
            rows: list[dict] = []
            rows.extend(self._store.load_recent_capsules())
            rows.extend(self._store.load_corrections())
            rows.extend(self._store.load_knowledge_gaps())
            rows.extend(self._store.load_command_failures())
            frs = self._store.load_feature_requests()
            rows.extend(frs)
            for row in rows:
                pk = str(row.get("pattern_key", "") or "")
                if not pk:
                    continue
                self._pattern_recurrence[pk] = self._pattern_recurrence.get(pk, 0) + 1
                if pk not in self._pattern_first_seen:
                    fs = str(row.get("first_seen", "") or row.get("created_at", "") or "")
                    if fs:
                        self._pattern_first_seen[pk] = fs
            self._pending_feature_requests = len(frs)
            self._pending_corrections = self._store.count_corrections()
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution capture-state load failed: %s", exc)

    def _stamp_recurrence(self, record: Any) -> Any:
        """Stamp a fresh record with the cumulative recurrence_count +
        first/last-seen for its pattern_key (tracked in-memory). A record with
        no pattern_key is returned unchanged. Fail-open."""
        try:
            pk = getattr(record, "pattern_key", "") or ""
            if not pk:
                return record
            occurred = getattr(record, "created_at", "") or _now_iso()
            first = self._pattern_first_seen.setdefault(pk, occurred)
            count = self._pattern_recurrence.get(pk, 0) + 1
            self._pattern_recurrence[pk] = count
            return replace(
                record, recurrence_count=count, first_seen=first, last_seen=occurred, asset_id=""
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution recurrence stamp failed: %s", exc)
            return record

    def _maybe_capture_correction(self, user_text: str, prior_response: str) -> bool:
        """Detect + persist a user correction and feed the repair-distillation
        path. Returns True iff a correction was captured. Fail-open."""
        if not getattr(self._config, "correction_detection_enabled", True):
            return False
        try:
            cap = extract_correction(user_text, prior_response=prior_response)
            if cap is None:
                return False
            cap = self._stamp_recurrence(cap)
            self._store.append_correction(cap)
            self._store.append_failure(cap.to_failure_record())
            self._pending_corrections += 1
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution correction capture failed: %s", exc)
            return False

    def _maybe_capture_knowledge_gap(self, user_text: str, prior_response: str) -> None:
        """Detect + persist a knowledge gap and feed the repair-distillation
        path (gated under correction detection). Fail-open."""
        if not getattr(self._config, "correction_detection_enabled", True):
            return
        try:
            gap = extract_knowledge_gap(user_text, prior_response=prior_response)
            if gap is None:
                return
            gap = self._stamp_recurrence(gap)
            self._store.append_knowledge_gap(gap)
            self._store.append_failure(gap.to_failure_record())
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution knowledge-gap capture failed: %s", exc)

    def _maybe_capture_feature_request(self, user_text: str) -> None:
        """Detect + persist a feature request (NEVER distilled; surfaced in
        the digest). Fail-open."""
        if not getattr(self._config, "feature_request_capture_enabled", True):
            return
        try:
            fr = extract_feature_request(user_text)
            if fr is None:
                return
            fr = self._stamp_recurrence(fr)
            self._store.append_feature_request(fr)
            self._pending_feature_requests += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution feature-request capture failed: %s", exc)

    def record_command_failure(
        self, command: str = "", output: str = "", *, exit_code: Optional[int] = None
    ) -> None:
        """Observe command / tool output (catalog 14, T1). On a detected
        failure, persist a CommandFailureSignal + feed the repair-distillation
        path. Gated, fail-open, zero-cost when nothing failed. Public so the
        orchestrator can route coding-task ERROR / failed-tool events here."""
        if self._closed or not getattr(self._config, "command_failure_capture_enabled", True):
            return
        try:
            sig = extract_command_failure(output, command=command, exit_code=exit_code)
            if sig is None:
                return
            sig = self._stamp_recurrence(sig)
            self._store.append_command_failure(sig)
            self._store.append_failure(sig.to_failure_record())
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution command-failure capture failed: %s", exc)

    def maybe_run_autonomous_cycle(self) -> None:
        """If enough turns have elapsed and no cycle is running, run one on a
        daemon thread (single-flight, off the hot path). Fail-open."""
        if self._closed:
            return
        try:
            interval = int(getattr(self._config, "cycle_check_interval_turns", DEFAULT_CYCLE_CHECK_INTERVAL_TURNS))
            if self._turns_since_check < interval:
                return
            self._turns_since_check = 0
            if not self._cycle_lock.acquire(blocking=False):
                return  # a cycle is already running

            def _bg() -> None:
                try:
                    self._do_cycle()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("evolution autonomous cycle failed: %s", exc)
                finally:
                    self._cycle_lock.release()

            try:
                threading.Thread(target=_bg, name="evolution-cycle", daemon=True).start()
            except Exception:  # noqa: BLE001
                self._cycle_lock.release()
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution maybe_run_autonomous_cycle failed: %s", exc)

    # -- cycle --------------------------------------------------------------

    def run_cycle(self) -> dict:
        """Run a single evolution cycle now (the voice-command entry point).
        Single-flight: returns ``{"status": "busy"}`` if a cycle is already
        running. Never raises."""
        if self._closed:
            return {"status": "disabled"}
        if not self._cycle_lock.acquire(blocking=False):
            return {"status": "busy"}
        try:
            return self._do_cycle()
        finally:
            self._cycle_lock.release()

    def _do_cycle(self) -> dict:
        try:
            result = self._loop.run_once()
        except Exception as exc:  # noqa: BLE001
            logger.warning("evolution loop run failed: %s", exc)
            return {"status": "error", "error": str(exc)}
        try:
            self._store.save_state(self._state)
        except Exception:  # noqa: BLE001
            pass
        if result is None:
            return {"status": "no_proposal"}
        if result.status is ApplyStatus.KEPT and self._registry_reloader is not None:
            try:
                self._registry_reloader()
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution registry reload failed: %s", exc)
        if result.status is ApplyStatus.KEPT:
            self._arm_post_apply_watch(result)
        return {
            "status": result.status.value,
            "slug": result.proposal.slug,
            "reasons": list(result.reasons),
        }

    # -- guardrail brake: post-apply monitoring (#15+#65) --------------------

    def _arm_post_apply_watch(self, result: Any) -> None:
        """Snapshot pre-apply metrics + start the post-apply countdown for a
        KEPT proposal. Single-slot: a newer KEPT proposal replaces an armed
        watch (the 24h distill cooldown makes overlap practically
        impossible). Fail-open -- a failure here leaves the proposal kept
        but unwatched (the legacy behaviour)."""
        if not bool(getattr(self._config, "guardrail_monitoring_enabled", True)):
            return
        if self._guardrail_sampler is None or self._turn_metrics is None:
            return
        try:
            turns = int(
                getattr(
                    self._config,
                    "post_apply_monitor_turns",
                    DEFAULT_POST_APPLY_MONITOR_TURNS,
                )
            )
            pre_sample = self._guardrail_sampler()
            with self._watch_lock:
                if self._post_apply_watch is not None:
                    logger.debug(
                        "post-apply watch replaced (%s superseded by %s)",
                        self._post_apply_watch.get("slug", "?"),
                        result.proposal.slug,
                    )
                self._post_apply_watch = {
                    "slug": result.proposal.slug,
                    "filename": result.proposal.filename,
                    "gene": getattr(result.proposal.gene, "id", ""),
                    "pre_sample": pre_sample,
                    "markers": self._turn_metrics.totals(),
                    "turns_remaining": max(1, turns),
                }
            logger.info(
                "evolution: watching kept skill '%s' for %d turns "
                "(post-apply guardrail re-check)",
                result.proposal.slug,
                max(1, turns),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-apply watch arm failed: %s", exc)

    def _tick_post_apply_watch(self) -> None:
        """Advance the armed watch by one turn; at expiry, evaluate on a
        daemon thread (the evaluation may probe VRAM via subprocess, so it
        must stay off the voice hot path). Fail-open."""
        try:
            with self._watch_lock:
                watch = self._post_apply_watch
                if watch is None:
                    return
                watch["turns_remaining"] = int(watch.get("turns_remaining", 1)) - 1
                if watch["turns_remaining"] > 0:
                    return
                self._post_apply_watch = None
            threading.Thread(
                target=self._evaluate_post_apply_watch,
                args=(watch,),
                name="evolution-postapply",
                daemon=True,
            ).start()
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-apply watch tick failed: %s", exc)

    def _evaluate_post_apply_watch(self, watch: dict) -> None:
        """Compare post-apply behaviour to the pre-apply snapshot; on a
        guardrail regression, auto-revert the kept skill (data-only file
        delete + registry reload) and record the rollback. Runs on a daemon
        thread. RELATIVE comparison: the baseline is built from the
        pre-apply snapshot, so the check is like-for-like by construction;
        any pre-apply field that was unobserved disables its check (a
        ``0`` baseline skips the latency detector; rate baselines default
        to ``0.0`` which is the conservative direction). Never raises."""
        try:
            pre: GuardrailSample = watch.get("pre_sample") or GuardrailSample()
            post = self._turn_metrics.sample(
                min_latency_samples=POST_APPLY_MIN_LATENCY_SAMPLES,
                min_rate_samples=POST_APPLY_MIN_RATE_SAMPLES,
                vram_probe=self._post_apply_vram_probe(),
                since=watch.get("markers"),
            )
            rel_baseline = GuardrailBaseline(
                ttfa_ms=0.0,  # never observed at runtime -> check skipped
                ttft_ms=pre.ttft_ms if pre.ttft_ms is not None else 0.0,
                tts_ms=0.0,  # never observed at runtime -> check skipped
                correction_rate=pre.correction_rate if pre.correction_rate is not None else 0.0,
                error_rate=pre.error_rate if pre.error_rate is not None else 0.0,
            )
            verdict = evaluate_guardrails(rel_baseline, post)
            slug = str(watch.get("slug", ""))
            if not verdict.should_revert:
                logger.info(
                    "evolution: kept skill '%s' passed the post-apply "
                    "guardrail re-check (%d post-apply turns observed)",
                    slug,
                    post.turns_observed,
                )
                return
            self._revert_kept_proposal(watch, verdict)
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-apply watch evaluation failed: %s", exc)

    def _post_apply_vram_probe(self):
        """The VRAM probe for the post-apply sample (safe on this daemon
        thread), or ``None`` when unavailable. Fail-open."""
        try:
            from kenning.evolution.turn_metrics import probe_vram_mb

            return probe_vram_mb
        except Exception:  # noqa: BLE001
            return None

    def _revert_kept_proposal(self, watch: dict, verdict: Any) -> None:
        """Auto-revert a kept-then-regressed skill: delete the proposal file
        (containment-checked), reload the skill registry, record the
        rollback in the autonomy ledger + audit chain + failure feed, and
        queue a one-line voice narration. Data-only; never raises."""
        import os as _os

        slug = str(watch.get("slug", ""))
        filename = str(watch.get("filename", ""))
        reasons = "; ".join(getattr(verdict, "details", ()) or ())
        target = self._proposal_dir / filename if filename else None
        removed = False
        if target is not None:
            try:
                common = _os.path.commonpath(
                    [_os.path.abspath(str(target)), _os.path.abspath(str(self._proposal_dir))]
                )
                contained = _os.path.normcase(common) == _os.path.normcase(
                    _os.path.abspath(str(self._proposal_dir))
                )
                if contained and target.exists():
                    target.unlink()
                    removed = True
            except Exception as exc:  # noqa: BLE001
                logger.debug("post-apply revert unlink failed: %s", exc)
        if self._registry_reloader is not None:
            try:
                self._registry_reloader()
            except Exception as exc:  # noqa: BLE001
                logger.debug("post-apply revert registry reload failed: %s", exc)
        guard = (
            verdict.tripped_guards[0]
            if getattr(verdict, "tripped_guards", ())
            else "guardrail"
        )
        try:
            self._autonomy.record_outcome(
                "skills",
                reverted=True,
                record=RollbackRecord(
                    surface="skills",
                    change_id=slug,
                    guardrail=guard,
                    metric_delta=reasons,
                    at=self._clock(),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-apply revert autonomy record failed: %s", exc)
        try:
            self._store.append_event(
                EvolutionEvent(
                    id=new_event_id(),
                    intent="post_apply_revert",
                    signals=(guard,),
                    genes_used=(str(watch.get("gene", "")),),
                    personality_state=self._personality.state,
                    blast_radius=BlastRadius(files=1, lines=0),
                    outcome=Outcome(status=OutcomeStatus.FAILED, score=0.0),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-apply revert audit event failed: %s", exc)
        try:
            self._store.append_failure(
                {
                    "gene": str(watch.get("gene", "")),
                    "trigger": [slug],
                    "reason_class": "post_apply_guardrail",
                    "learning_signals": [f"guardrail:{guard}"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("post-apply revert failure record failed: %s", exc)
        self._pending_narration = (
            "I rolled back my most recent self-improvement; it regressed "
            f"my {guard} checks."
        )
        logger.warning(
            "evolution: auto-reverted kept skill '%s' after the post-apply "
            "re-check tripped the %s guardrail (file removed: %s) -- %s",
            slug,
            guard,
            removed,
            reasons or "no detail",
        )

    def pop_pending_narration(self) -> Optional[str]:
        """Return + clear the queued one-line voice narration (e.g. the
        post-apply auto-revert notice), or ``None``. Never raises."""
        line = self._pending_narration
        self._pending_narration = None
        return line

    @property
    def turn_metrics(self) -> Any:
        """The per-turn metrics ring (or ``None`` when monitoring is off).
        The orchestrator feeds it response-side observations (TTFT +
        error flag) at the end of each turn."""
        return self._turn_metrics

    # -- temperament --------------------------------------------------------

    def temperament_hint(self) -> str:
        """The current response-shaping hint (``""`` when balanced)."""
        try:
            return self._personality.current_hint()
        except Exception:  # noqa: BLE001
            return ""

    def apply_temperament(self, user_text: str) -> str:
        """Prepend the current temperament hint to ``user_text`` (fail-open)."""
        if self._closed or not getattr(self._config, "apply_temperament", True):
            return user_text
        try:
            return apply_temperament(user_text, self._personality.state)
        except Exception:  # noqa: BLE001
            return user_text

    def pre_turn_system_hint(self) -> str:
        """The combined per-turn SYSTEM-prompt hint pushed through the LLM's
        existing ``set_temperament_hint`` seam (catalog 14, T3): the learned
        ``[Tone: ...]`` temperament directive plus, when the pending-capsule
        queue is non-empty, a bounded ``[Evolution: ...]`` self-evaluation
        nudge. System-layer only -- NEVER the user text, so the web-gate /
        local-clock raw-text detectors are unaffected. Token-capped +
        fail-open; ``""`` when both are empty (prompt byte-identical)."""
        if self._closed:
            return ""
        try:
            tone = self.temperament_hint() if getattr(self._config, "apply_temperament", True) else ""
            nudge = self._pre_turn_nudge()
            return " ".join(p for p in (tone, nudge) if p)
        except Exception:  # noqa: BLE001
            return ""

    def _pre_turn_nudge(self) -> str:
        """The bounded ``[Evolution: ...]`` nudge (or ``""``). Fires only when
        a recurring pattern is distill-ready OR a feature request is pending;
        char-capped so it stays well under ~50 tokens."""
        if not getattr(self._config, "pre_turn_nudge_enabled", True):
            return ""
        threshold = self._recurrence_threshold()
        recurring = sum(1 for v in self._pattern_recurrence.values() if v >= threshold)
        feats = self._pending_feature_requests
        if recurring <= 0 and feats <= 0:
            return ""
        bits: list[str] = []
        if recurring > 0:
            bits.append(f"{recurring} recurring pattern{'s' if recurring != 1 else ''} ready to distill")
        if feats > 0:
            bits.append(f"{feats} feature request{'s' if feats != 1 else ''} logged")
        nudge = "[Evolution: " + "; ".join(bits) + ". Note any correction the user makes.]"
        cap = int(getattr(self._config, "pre_turn_nudge_max_chars", DEFAULT_PRE_TURN_NUDGE_MAX_CHARS) or 0)
        if cap > 0 and len(nudge) > cap:
            nudge = nudge[:cap].rstrip()
        return nudge

    # -- reporting ----------------------------------------------------------

    def digest(self) -> str:
        """The multi-line periodic digest (autonomy + personality ranking +
        the catalog-14 qualitative-capture summary)."""
        try:
            base = f"{self._autonomy.digest()}\n{self._personality.report()}"
            extra = self._capture_digest()
            return f"{base}\n{extra}" if extra else base
        except Exception:  # noqa: BLE001
            return "Evolution digest unavailable."

    def _capture_digest(self) -> str:
        """A short summary of pending feature requests + recurring patterns +
        corrections (catalog 14). Reads the ledgers on demand (not per turn)."""
        lines: list[str] = []
        try:
            from collections import Counter

            frs = self._store.load_feature_requests()
            if frs:
                counts: Counter[str] = Counter()
                for row in frs:
                    cap = str(row.get("requested_capability", "") or "").strip()
                    if cap:
                        counts[cap] += 1
                top = counts.most_common(3)
                if top:
                    lines.append("Feature requests:")
                    for cap, n in top:
                        times = f"{n}x " if n > 1 else ""
                        lines.append(f"  - {times}{cap}")
            threshold = self._recurrence_threshold()
            recurring = sorted(pk for pk, v in self._pattern_recurrence.items() if v >= threshold)
            if recurring:
                lines.append(f"Recurring patterns at/over the distill threshold: {len(recurring)}")
            if self._pending_corrections:
                lines.append(f"User corrections recorded: {self._pending_corrections}")
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution capture digest failed: %s", exc)
        return "\n".join(lines)

    def status_line(self) -> str:
        """A short, TTS-safe one-line status for a voice query."""
        try:
            surfaces = [
                self._autonomy.state(s)
                for s in self._autonomy.known_surfaces()
                if self._autonomy.state(s).applied > 0
            ]
            kept = sum(s.kept for s in surfaces)
            reverted = sum(s.reverted for s in surfaces)
            capsules = self._store.count_capsules()
            msg = (
                f"I've recorded {capsules} learning samples; "
                f"kept {kept} self-improvements and auto-reverted {reverted}."
            )
            try:
                feats = self._store.count_feature_requests()
                if feats:
                    msg += f" {feats} feature request{'s' if feats != 1 else ''} logged."
            except Exception:  # noqa: BLE001
                pass
            return msg
        except Exception:  # noqa: BLE001
            return "Evolution is active."

    @property
    def autonomy(self) -> TieredAutonomyController:
        return self._autonomy

    @property
    def personality(self) -> PersonalityTuner:
        return self._personality

    @property
    def store(self) -> EvolutionStore:
        return self._store

    def shutdown(self) -> None:
        """Persist state + personality and stop accepting work."""
        try:
            self._store.save_state(self._state)
            self._store.save_personality(self._personality.to_dict())
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution shutdown persist failed: %s", exc)
        self._closed = True


__all__ = [
    "EvolutionStore",
    "EvolutionService",
]
