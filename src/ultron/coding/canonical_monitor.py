"""Canonical-path monitor for coding sessions.

Per the long-horizon-reliability paper:

    Each off-canonical tool call raises the probability that the next
    call is also off-canonical by 22.7 percentage points... A simple
    monitor that restarts the bottom tercile of runs based on
    mid-trajectory canonical adherence lifts success rates by +8.8 pp.

This module is the monitor. Off by default (``coding.canonical_monitor.enabled``)
so existing tests + live runs are byte-for-byte unchanged. When
enabled, the monitor watches the ``TaskEvent`` stream from a coding
session and signals abort when too many off-canonical tool calls land
inside an early window — a cheap restart at that point costs less than
running a flailing session to verification failure.

"Canonical" is heuristic: the standard set of tools we expect in a
coding session. Anything outside that set counts as off-canonical.
The expected sets are defined per task type:

- ``CODE_TASK``: Read / Write / Edit / Glob / Grep / Bash / TodoWrite
  / NotebookEdit / Task / WebFetch (rare but legitimate for docs lookup)

Tuning is conservative on purpose — the cost of a false-positive abort
(a healthy session restarted) is real. Defaults can be overridden via
``coding.canonical_monitor.off_canonical_threshold`` (default 3) and
``early_window_calls`` (default 10).

Voice path is unaffected — the monitor runs on the coding pipeline
listener thread and never touches LLM inference latency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

from ultron.utils.logging import get_logger

logger = get_logger("coding.canonical_monitor")


# Canonical tool set for CODE_TASK sessions. Conservative — any tool
# the standard coding workflow uses lands here. The set is uppercase
# for case-insensitive comparison.
CODE_TASK_CANONICAL_TOOLS: Set[str] = {
    "READ",
    "WRITE",
    "EDIT",
    "GLOB",
    "GREP",
    "BASH",
    "TODOWRITE",
    "NOTEBOOKEDIT",
    "TASK",
    "WEBFETCH",  # legitimate for docs lookup mid-task
    "WEBSEARCH",  # ditto
    "POWERSHELL",  # Windows shell parity with Bash
    # MCP tools that the in-process MCP server exposes are also
    # canonical (the worker calls back to Ultron via SSE).
    "REPORT_PROGRESS",
    "REQUEST_CLARIFICATION",
    "REPORT_TEST_RESULTS",
    "DECLARE_COMPLETE",
    "ABANDON_TASK",
    "RECORD_FILE_CHANGE",
}


@dataclass
class MonitorVerdict:
    """The monitor's decision after observing the latest event.

    ``should_abort`` becomes True when the off-canonical count crosses
    the threshold inside the early window. Once True, it stays True
    for the rest of the session. ``reason`` is a human-readable
    explanation suitable for routing-log audit + voice narration.
    ``off_canonical_count`` and ``total_tool_calls`` are exposed for
    structured logging.
    """

    should_abort: bool
    reason: str = ""
    off_canonical_count: int = 0
    total_tool_calls: int = 0
    off_canonical_tools: List[str] = field(default_factory=list)


class CanonicalPathMonitor:
    """Tracks tool-call sequences for one coding session.

    The monitor is created per-session by the coding runner. The
    intent type drives which canonical set applies.

    Usage::

        monitor = CanonicalPathMonitor(
            intent_type="CODE_TASK",
            off_canonical_threshold=3,
            early_window_calls=10,
        )
        for event in session_event_stream:
            verdict = monitor.observe(event)
            if verdict.should_abort:
                runner.cancel_active(reason=verdict.reason)
                break
    """

    def __init__(
        self,
        *,
        intent_type: str = "CODE_TASK",
        off_canonical_threshold: int = 3,
        early_window_calls: int = 10,
        canonical_tools: Optional[Set[str]] = None,
    ) -> None:
        self._intent_type = intent_type.upper()
        self._threshold = max(1, int(off_canonical_threshold))
        self._window = max(1, int(early_window_calls))
        self._canonical = (
            {t.upper() for t in canonical_tools}
            if canonical_tools is not None
            else self._default_canonical_set(self._intent_type)
        )
        self._tool_calls: List[str] = []
        self._off_canonical: List[str] = []
        # Latched: once we've decided to abort we don't unlatch even if
        # subsequent calls are canonical.
        self._latched_abort = False
        self._latched_reason = ""

    @staticmethod
    def _default_canonical_set(intent_type: str) -> Set[str]:
        if intent_type == "CODE_TASK":
            return set(CODE_TASK_CANONICAL_TOOLS)
        # Fall back to the CODE_TASK set for unknown intents. Caller can
        # always pass a custom ``canonical_tools=`` set for non-coding
        # sessions.
        return set(CODE_TASK_CANONICAL_TOOLS)

    def observe(self, event: Any) -> MonitorVerdict:
        """Update internal state for ``event`` and return the current verdict.

        ``event`` is duck-typed — anything with a ``kind`` attribute /
        key that equals ``"tool_use"`` (case-insensitive) and a
        ``tool_name`` field is processed; everything else is ignored.
        Mirrors the existing ``TaskEvent`` shape without importing it
        (so tests can drive simple dicts).
        """
        kind = self._read(event, "kind", "")
        if str(kind).lower() != "tool_use":
            return self._verdict()
        tool_name = self._read(event, "tool_name", "") or ""
        if not tool_name:
            return self._verdict()

        self._tool_calls.append(tool_name)
        if not self._is_canonical(tool_name):
            self._off_canonical.append(tool_name)

        # Decision: only fires within the early window so a long run
        # that drifts late doesn't trigger a restart (other mechanisms —
        # verification — handle the late case).
        if (
            not self._latched_abort
            and len(self._tool_calls) <= self._window
            and len(self._off_canonical) >= self._threshold
        ):
            self._latched_abort = True
            self._latched_reason = (
                f"{len(self._off_canonical)} off-canonical tool calls "
                f"({', '.join(self._off_canonical)}) in the first "
                f"{len(self._tool_calls)} of {self._window}; restarting "
                f"the session usually beats running it through to "
                f"verification failure."
            )
            logger.info(
                "CanonicalPathMonitor: abort signaled (%s)",
                self._latched_reason,
            )

        return self._verdict()

    def reset(self) -> None:
        """Clear state. Used when the runner restarts the session
        post-abort with a cleaner prompt."""
        self._tool_calls.clear()
        self._off_canonical.clear()
        self._latched_abort = False
        self._latched_reason = ""

    def _is_canonical(self, tool_name: str) -> bool:
        return tool_name.upper() in self._canonical

    def _verdict(self) -> MonitorVerdict:
        return MonitorVerdict(
            should_abort=self._latched_abort,
            reason=self._latched_reason,
            off_canonical_count=len(self._off_canonical),
            total_tool_calls=len(self._tool_calls),
            off_canonical_tools=list(self._off_canonical),
        )

    @staticmethod
    def _read(obj: Any, key: str, default: Any) -> Any:
        if hasattr(obj, key):
            return getattr(obj, key)
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default


def build_default_monitor(intent_type: str = "CODE_TASK", cfg: Any = None) -> Optional[CanonicalPathMonitor]:
    """Construct the monitor only if enabled in config; else ``None``.

    Returns ``None`` when ``coding.canonical_monitor.enabled`` is False
    so callers can use the result as a truthy short-circuit.
    """
    if cfg is None:
        from ultron.config import get_config
        cfg = get_config()
    cm_cfg = cfg.coding.canonical_monitor
    if not cm_cfg.enabled:
        return None
    return CanonicalPathMonitor(
        intent_type=intent_type,
        off_canonical_threshold=cm_cfg.off_canonical_threshold,
        early_window_calls=cm_cfg.early_window_calls,
    )


__all__ = [
    "CanonicalPathMonitor",
    "MonitorVerdict",
    "CODE_TASK_CANONICAL_TOOLS",
    "build_default_monitor",
]
