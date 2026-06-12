"""Extended loop detectors (T1): unknown-tool / known-poll / ping-pong / global circuit breaker.

T1 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). The
existing :mod:`kenning.agent_loop.loop_detection` ships a single
generic-repeat detector (counts consecutive identical signatures).
The four detectors here cover the cases the generic primitive
cannot:

* :class:`UnknownToolRepeatDetector` — the model hallucinates a
  function-call name that doesn't exist (a common Qwen 3.5 4B
  failure mode). Counts errors matching ``unknown tool.*<name>``
  regex; warning + critical thresholds let the orchestrator
  coach the model and eventually halt.
* :class:`KnownPollNoProgressDetector` — explicit list of
  known-polling tools (``command_status`` / ``process(action=poll)``
  / ``process(action=log)``) get a separate, more permissive
  threshold. Legitimate polling should not trip generic loop
  detection.
* :class:`PingPongDetector` — alternating ``A,B,A,B,A,B`` patterns
  where both sides have stable outcomes (no progress on either
  side). Applies to memory.retrieve <-> LLM "I don't know" cycles
  and supervisor plan-execute oscillation.
* :class:`GlobalCircuitBreakerDetector` — emergency stop at 30
  identical no-progress repeats regardless of the per-detector
  thresholds. Last line of defence when the per-detector tiers
  haven't fired.

Constants default to OpenClaw's values
(``TOOL_CALL_HISTORY_SIZE=30``, ``WARNING_THRESHOLD=10``,
``CRITICAL_THRESHOLD=20``, ``GLOBAL_CIRCUIT_BREAKER_THRESHOLD=30``,
``UNKNOWN_TOOL_THRESHOLD=10``). The hash scheme is SHA-256 of the
canonical-JSON signature already used by
:func:`kenning.agent_loop.loop_detection.tool_call_signature` so the
detectors stay compatible with the existing primitive's signature
contract.

Each detector exposes :meth:`observe(record) -> LoopVerdict`. The
caller picks which detectors to run per dispatch and aggregates
verdicts via the orchestrator (most-restrictive wins). A future
"loop detection manager" could fan-out, but the primitive is
intentionally independent so callers can opt in / out without
touching the others.
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

from kenning.agent_loop.loop_detection import LoopVerdict, tool_call_signature
from kenning.llm.response_format import loop_hard_escalation, loop_soft_warning

#: Sliding history window the detectors maintain. Mirrors OpenClaw.
TOOL_CALL_HISTORY_SIZE: int = 30

#: First-tier alert; rule is still permissive but counter trips a WARN.
WARNING_THRESHOLD: int = 10

#: Second-tier alert; the per-detector verdict surfaces a hard escalation.
CRITICAL_THRESHOLD: int = 20

#: Emergency catch-all when the per-detector logic missed the loop.
GLOBAL_CIRCUIT_BREAKER_THRESHOLD: int = 30

#: Critical-only threshold for unknown-tool repeats (no separate WARN
#: tier — the agent is calling a tool that doesn't exist; once is fine,
#: ten times is the stop).
UNKNOWN_TOOL_THRESHOLD: int = 10

#: Default poll-shaped tools whose repeats are legitimate. The match is
#: ``tool_name == "command_status"`` OR ``tool_name == "process" AND
#: action in {"poll", "log"}``. Extend per-deployment as needed.
DEFAULT_POLL_TOOLS: frozenset[str] = frozenset({"command_status"})


class OutcomeKind(str, Enum):
    """Coarse outcome classification for hashing.

    Determines the kind of result hash a detector computes. Different
    detectors care about different fields (``exec`` discriminates by
    ``status``; ``process(action=poll)`` discriminates by
    ``aggregated`` + ``tail``).
    """

    SUCCESS = "success"
    ERROR = "error"
    RUNNING = "running"
    APPROVAL_PENDING = "approval_pending"


@dataclass(frozen=True)
class ToolCallRecord:
    """One observed tool call + outcome.

    Detectors consume records from a shared history buffer; each
    detector hashes the fields it cares about.

    Attributes:
        tool_name: canonical tool identifier (e.g. ``"command_status"``).
        params: arguments mapping (signed via canonical JSON).
        outcome_kind: coarse status (success / error / running / etc.).
        result_summary: tool-specific result summary used in the result
            hash (e.g. ``{"exit_code": 0, "tail": "..."}`` for ``exec``).
        error_message: error text when ``outcome_kind == ERROR``;
            empty otherwise. The :class:`UnknownToolRepeatDetector`
            scans this for the unknown-tool pattern.
    """

    tool_name: str
    params: Mapping[str, Any] = field(default_factory=dict)
    outcome_kind: OutcomeKind = OutcomeKind.SUCCESS
    result_summary: Mapping[str, Any] = field(default_factory=dict)
    error_message: str = ""


def _canonical_json(value: Any) -> str:
    """Stable JSON serialisation for hashing."""
    import json
    try:
        return json.dumps(_normalise(value), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(value)


def _normalise(value: Any) -> Any:
    """Recursively coerce ``value`` into JSON-serialisable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {k: _normalise(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return repr(value)


def hash_tool_call(tool_name: str, params: Mapping[str, Any]) -> str:
    """SHA-256 of ``tool_name:canonical_json(params)``.

    Used by every detector for the call-identity hash. Mirrors the
    signature scheme from :func:`tool_call_signature` but with SHA-256
    digest instead of plain canonical text — the digest gives O(1)
    equality checks for large param objects.
    """
    body = f"{tool_name}:{_canonical_json(params)}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def hash_outcome(record: ToolCallRecord) -> str:
    """SHA-256 of the outcome summary, discriminated by ``outcome_kind``.

    Errors hash the error message; running-state hashes only the
    ``outcome_kind`` (so a long-running command doesn't trigger
    no-progress until output stops changing); successes hash the
    result summary.
    """
    if record.outcome_kind == OutcomeKind.ERROR:
        body = f"error:{record.error_message}"
    elif record.outcome_kind == OutcomeKind.RUNNING:
        body = "running"
    elif record.outcome_kind == OutcomeKind.APPROVAL_PENDING:
        body = "approval_pending"
    else:
        body = f"success:{_canonical_json(record.result_summary)}"
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class _CallEntry:
    """Internal history-buffer entry."""

    tool_name: str
    call_hash: str
    outcome_hash: str
    is_poll: bool
    is_error: bool
    error_message: str


class _BaseDetector:
    """Shared scaffolding for the four detectors."""

    def __init__(
        self,
        *,
        history_size: int = TOOL_CALL_HISTORY_SIZE,
        warning_threshold: int = WARNING_THRESHOLD,
        critical_threshold: int = CRITICAL_THRESHOLD,
    ) -> None:
        if warning_threshold > critical_threshold:
            raise ValueError("warning_threshold must not exceed critical_threshold")
        self._history: deque[_CallEntry] = deque(maxlen=history_size)
        self._warn = warning_threshold
        self._crit = critical_threshold
        self._halted = False

    @property
    def halted(self) -> bool:
        """Once a detector fires critical, it stays halted."""
        return self._halted

    def reset(self) -> None:
        """Clear history and halt state (e.g. on stream end)."""
        self._history.clear()
        self._halted = False

    def _record_entry(
        self,
        record: ToolCallRecord,
        *,
        poll_tools: Optional[frozenset[str]] = None,
    ) -> _CallEntry:
        is_poll = self._is_poll_call(record, poll_tools=poll_tools)
        entry = _CallEntry(
            tool_name=record.tool_name,
            call_hash=hash_tool_call(record.tool_name, record.params),
            outcome_hash=hash_outcome(record),
            is_poll=is_poll,
            is_error=record.outcome_kind == OutcomeKind.ERROR,
            error_message=record.error_message,
        )
        self._history.append(entry)
        return entry

    @staticmethod
    def _is_poll_call(
        record: ToolCallRecord,
        *,
        poll_tools: Optional[frozenset[str]] = None,
    ) -> bool:
        """True when ``record`` is one of the catalogued poll-shaped calls."""
        poll = poll_tools or DEFAULT_POLL_TOOLS
        if record.tool_name in poll:
            return True
        if record.tool_name == "process":
            action = record.params.get("action") if record.params else None
            if action in ("poll", "log"):
                return True
        return False


class UnknownToolRepeatDetector(_BaseDetector):
    """Detect the model repeatedly calling tools that don't exist.

    Counts errors whose ``error_message`` matches
    ``unknown tool.*<name>`` (case-insensitive). When the count
    exceeds :data:`UNKNOWN_TOOL_THRESHOLD`, fires a hard escalation
    naming the unknown tool. The orchestrator can use the extracted
    name to coach the model: ``"You called <tool>; the available
    tools are X, Y, Z. Pick one."``

    There is no separate warn tier — the agent calling a non-existent
    tool once is fine; ten times is a halt.

    Constructor accepts a tighter ``critical_threshold`` (default
    :data:`UNKNOWN_TOOL_THRESHOLD`) than the base detector default.
    """

    _UNKNOWN_TOOL_RE = re.compile(
        r"unknown\s+tool\s*[:\-]?\s*['\"`]?(?P<name>[A-Za-z0-9_.\-]+)['\"`]?",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *,
        history_size: int = TOOL_CALL_HISTORY_SIZE,
        critical_threshold: int = UNKNOWN_TOOL_THRESHOLD,
    ) -> None:
        super().__init__(
            history_size=history_size,
            warning_threshold=critical_threshold,
            critical_threshold=critical_threshold,
        )

    def observe(self, record: ToolCallRecord) -> LoopVerdict:
        """Record one tool-call and return the verdict."""
        entry = self._record_entry(record)
        signature = f"unknown:{entry.tool_name}"
        if not entry.is_error:
            return LoopVerdict(signature=signature, count=0)
        match = self._UNKNOWN_TOOL_RE.search(entry.error_message)
        if not match:
            return LoopVerdict(signature=signature, count=0)
        unknown_name = match.group("name")
        # Count history entries whose error mentions the same unknown name.
        matching = sum(
            1 for e in self._history
            if e.is_error
            and self._UNKNOWN_TOOL_RE.search(e.error_message) is not None
            and (m := self._UNKNOWN_TOOL_RE.search(e.error_message))
            and m.group("name") == unknown_name
        )
        if matching >= self._crit:
            self._halted = True
            return LoopVerdict(
                signature=f"unknown_tool:{unknown_name}",
                count=matching,
                hard_escalation=loop_hard_escalation(
                    f"unknown_tool:{unknown_name}", matching,
                ),
            )
        return LoopVerdict(signature=f"unknown_tool:{unknown_name}", count=matching)


class KnownPollNoProgressDetector(_BaseDetector):
    """Detect poll-shaped tools repeating with no result change.

    Long-running ``command_status`` polls and ``process(action=poll)``
    legitimately repeat. The generic detector would flag them; this
    detector raises a separate, more permissive threshold so the
    operator gets a warn at 10 and a critical at 20 specifically when
    the result hash stops changing.
    """

    def __init__(
        self,
        *,
        history_size: int = TOOL_CALL_HISTORY_SIZE,
        warning_threshold: int = WARNING_THRESHOLD,
        critical_threshold: int = CRITICAL_THRESHOLD,
        poll_tools: Optional[frozenset[str]] = None,
    ) -> None:
        super().__init__(
            history_size=history_size,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
        )
        self._poll_tools = poll_tools or DEFAULT_POLL_TOOLS

    def observe(self, record: ToolCallRecord) -> LoopVerdict:
        entry = self._record_entry(record, poll_tools=self._poll_tools)
        signature = f"poll:{entry.tool_name}:{entry.call_hash[:8]}:{entry.outcome_hash[:8]}"
        if not entry.is_poll:
            return LoopVerdict(signature=signature, count=0)
        # Walk history backwards; count consecutive same call+outcome.
        count = 0
        for past in reversed(self._history):
            if (
                past.is_poll
                and past.call_hash == entry.call_hash
                and past.outcome_hash == entry.outcome_hash
            ):
                count += 1
            else:
                break
        verdict = LoopVerdict(signature=signature, count=count)
        if count >= self._crit:
            verdict.hard_escalation = loop_hard_escalation(signature, count)
            self._halted = True
        elif count >= self._warn:
            verdict.soft_warning = loop_soft_warning(signature, count)
        return verdict


class PingPongDetector(_BaseDetector):
    """Detect ``A,B,A,B,...`` alternation with stable outcomes on both sides.

    Useful for the model -> supervisor -> model -> supervisor cycle
    where neither side advances. Counts the longest alternating tail
    in the history; warns at :data:`WARNING_THRESHOLD` half-cycles,
    halts at :data:`CRITICAL_THRESHOLD`.

    A "half-cycle" is one A or one B; ``A,B,A,B`` = 4 half-cycles =
    2 round-trips.
    """

    def observe(self, record: ToolCallRecord) -> LoopVerdict:
        entry = self._record_entry(record)
        # Walk backwards finding the alternating-pair signature.
        # Requires at least 2 distinct entries in the tail.
        if len(self._history) < 2:
            return LoopVerdict(signature=f"pingpong:{entry.call_hash[:8]}", count=0)
        h = list(self._history)
        # Identify the alternation pair by looking at the tail two
        # entries: they must differ (otherwise it's a generic-repeat).
        most_recent = h[-1]
        prev = h[-2]
        if (most_recent.call_hash == prev.call_hash
                and most_recent.outcome_hash == prev.outcome_hash):
            return LoopVerdict(signature=f"pingpong:{most_recent.call_hash[:8]}", count=0)
        a_sig = (most_recent.call_hash, most_recent.outcome_hash)
        b_sig = (prev.call_hash, prev.outcome_hash)
        canonical = "|".join(sorted([f"{a_sig[0]}:{a_sig[1]}", f"{b_sig[0]}:{b_sig[1]}"]))
        signature = f"pingpong:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
        # Count tail alternations.
        count = 0
        expected_a = True
        for past in reversed(h):
            sig = (past.call_hash, past.outcome_hash)
            target = a_sig if expected_a else b_sig
            if sig == target:
                count += 1
                expected_a = not expected_a
            else:
                break
        verdict = LoopVerdict(signature=signature, count=count)
        if count >= self._crit:
            verdict.hard_escalation = loop_hard_escalation(signature, count)
            self._halted = True
        elif count >= self._warn:
            verdict.soft_warning = loop_soft_warning(signature, count)
        return verdict


class GlobalCircuitBreakerDetector(_BaseDetector):
    """Catch-all emergency stop after :data:`GLOBAL_CIRCUIT_BREAKER_THRESHOLD`.

    Last line of defence: any tool repeating with identical outcomes
    that many times bypasses the per-detector tiers and forces a hard
    halt. The signature is just ``tool:outcome_hash`` — args are
    NOT considered, so even mildly-varying arg shapes still trip the
    breaker once the outcome stops changing.

    Per the catalog: ``GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30``.
    """

    def __init__(
        self,
        *,
        history_size: int = TOOL_CALL_HISTORY_SIZE,
        critical_threshold: int = GLOBAL_CIRCUIT_BREAKER_THRESHOLD,
    ) -> None:
        super().__init__(
            history_size=history_size,
            warning_threshold=critical_threshold,
            critical_threshold=critical_threshold,
        )

    def observe(self, record: ToolCallRecord) -> LoopVerdict:
        entry = self._record_entry(record)
        signature = f"global:{entry.tool_name}:{entry.outcome_hash[:8]}"
        # Count history entries with same tool + outcome hash.
        count = sum(
            1 for past in self._history
            if past.tool_name == entry.tool_name and past.outcome_hash == entry.outcome_hash
        )
        verdict = LoopVerdict(signature=signature, count=count)
        if count >= self._crit:
            verdict.hard_escalation = loop_hard_escalation(signature, count)
            self._halted = True
        return verdict


class LoopDetectionManager:
    """Aggregate the four extended detectors into a single per-stream surface.

    Caller invokes :meth:`observe(record)` once per dispatch and
    receives the most-restrictive verdict across all configured
    detectors. Set ``enabled_detectors`` to limit which detectors
    participate per-deployment.
    """

    def __init__(
        self,
        *,
        enabled_detectors: Optional[set[str]] = None,
        history_size: int = TOOL_CALL_HISTORY_SIZE,
        warning_threshold: int = WARNING_THRESHOLD,
        critical_threshold: int = CRITICAL_THRESHOLD,
        unknown_tool_threshold: int = UNKNOWN_TOOL_THRESHOLD,
        global_circuit_breaker_threshold: int = GLOBAL_CIRCUIT_BREAKER_THRESHOLD,
        poll_tools: Optional[frozenset[str]] = None,
    ) -> None:
        all_names = {"unknown_tool", "known_poll", "ping_pong", "global_circuit_breaker"}
        self._enabled = enabled_detectors if enabled_detectors is not None else all_names
        invalid = self._enabled - all_names
        if invalid:
            raise ValueError(f"unknown detector names: {sorted(invalid)}")
        self._detectors: dict[str, _BaseDetector] = {}
        if "unknown_tool" in self._enabled:
            self._detectors["unknown_tool"] = UnknownToolRepeatDetector(
                history_size=history_size,
                critical_threshold=unknown_tool_threshold,
            )
        if "known_poll" in self._enabled:
            self._detectors["known_poll"] = KnownPollNoProgressDetector(
                history_size=history_size,
                warning_threshold=warning_threshold,
                critical_threshold=critical_threshold,
                poll_tools=poll_tools,
            )
        if "ping_pong" in self._enabled:
            self._detectors["ping_pong"] = PingPongDetector(
                history_size=history_size,
                warning_threshold=warning_threshold,
                critical_threshold=critical_threshold,
            )
        if "global_circuit_breaker" in self._enabled:
            self._detectors["global_circuit_breaker"] = GlobalCircuitBreakerDetector(
                history_size=history_size,
                critical_threshold=global_circuit_breaker_threshold,
            )

    @property
    def detector_names(self) -> tuple[str, ...]:
        return tuple(self._detectors.keys())

    @property
    def halted(self) -> bool:
        return any(d.halted for d in self._detectors.values())

    def reset(self) -> None:
        for d in self._detectors.values():
            d.reset()

    def observe(self, record: ToolCallRecord) -> tuple[LoopVerdict, dict[str, LoopVerdict]]:
        """Run every detector against ``record``.

        Returns:
            ``(dominant, per_detector)`` — the most-restrictive verdict
            across all detectors plus the per-detector verdict map for
            audit / debug.
        """
        per_detector: dict[str, LoopVerdict] = {}
        dominant: Optional[LoopVerdict] = None
        for name, detector in self._detectors.items():
            verdict = detector.observe(record)
            per_detector[name] = verdict
            if verdict.hard_escalation is not None:
                if dominant is None or dominant.hard_escalation is None:
                    dominant = verdict
            elif verdict.soft_warning is not None:
                if dominant is None or (
                    dominant.hard_escalation is None and dominant.soft_warning is None
                ):
                    dominant = verdict
        if dominant is None:
            # No detector flagged anything; return a benign signature
            # derived from the tool name so callers always have a value.
            dominant = LoopVerdict(signature=f"ok:{record.tool_name}", count=0)
        return dominant, per_detector


__all__ = [
    "CRITICAL_THRESHOLD",
    "DEFAULT_POLL_TOOLS",
    "GLOBAL_CIRCUIT_BREAKER_THRESHOLD",
    "GlobalCircuitBreakerDetector",
    "KnownPollNoProgressDetector",
    "LoopDetectionManager",
    "OutcomeKind",
    "PingPongDetector",
    "TOOL_CALL_HISTORY_SIZE",
    "ToolCallRecord",
    "UNKNOWN_TOOL_THRESHOLD",
    "UnknownToolRepeatDetector",
    "WARNING_THRESHOLD",
    "hash_outcome",
    "hash_tool_call",
]
