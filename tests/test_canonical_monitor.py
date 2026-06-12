"""4B optimization plan Item 7 — canonical-path monitor tests.

Verifies that ``CanonicalPathMonitor`` correctly tracks tool-call
sequences, identifies off-canonical calls, and signals abort only when
the threshold is crossed inside the early window. Off-by-default flag
gating means none of these tests change live behaviour.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kenning.coding.canonical_monitor import (
    CODE_TASK_CANONICAL_TOOLS,
    CanonicalPathMonitor,
    MonitorVerdict,
    build_default_monitor,
)


# ---------------------------------------------------------------------------
# Tool-set
# ---------------------------------------------------------------------------


def test_canonical_set_includes_standard_coding_tools() -> None:
    """Lock down the canonical set — these are the tools the standard
    coding workflow uses. Anything outside is off-canonical for
    CODE_TASK sessions."""
    standard = {"READ", "WRITE", "EDIT", "GLOB", "GREP", "BASH", "TODOWRITE"}
    assert standard.issubset(CODE_TASK_CANONICAL_TOOLS)


def test_canonical_set_includes_mcp_callbacks() -> None:
    """MCP callbacks (worker → orchestrator) are canonical too."""
    mcp = {
        "REPORT_PROGRESS",
        "REQUEST_CLARIFICATION",
        "REPORT_TEST_RESULTS",
        "DECLARE_COMPLETE",
    }
    assert mcp.issubset(CODE_TASK_CANONICAL_TOOLS)


# ---------------------------------------------------------------------------
# Pure observe-flow tests — drive with simple dicts (TaskEvent-shaped)
# ---------------------------------------------------------------------------


def _tool_use(name: str) -> dict:
    return {"kind": "tool_use", "tool_name": name}


def _other_event(kind: str) -> dict:
    return {"kind": kind, "tool_name": None}


def test_canonical_calls_do_not_trigger_abort() -> None:
    m = CanonicalPathMonitor()
    for tool in ["Read", "Edit", "Bash", "Write", "Grep"]:
        v = m.observe(_tool_use(tool))
    assert v.should_abort is False
    assert v.off_canonical_count == 0
    assert v.total_tool_calls == 5


def test_threshold_not_reached_does_not_abort() -> None:
    m = CanonicalPathMonitor(off_canonical_threshold=3, early_window_calls=10)
    for tool in ["weird_tool_a", "weird_tool_b"]:  # 2 < threshold 3
        v = m.observe(_tool_use(tool))
    assert v.should_abort is False
    assert v.off_canonical_count == 2


def test_threshold_reached_within_window_aborts() -> None:
    m = CanonicalPathMonitor(off_canonical_threshold=3, early_window_calls=10)
    for tool in ["weird_a", "weird_b", "weird_c"]:
        v = m.observe(_tool_use(tool))
    assert v.should_abort is True
    assert "off-canonical" in v.reason
    assert v.off_canonical_count == 3


def test_threshold_reached_outside_window_does_not_abort() -> None:
    """Three off-canonical calls AFTER the early window has closed
    should not trigger — by then the session is too far in to benefit
    from a restart."""
    m = CanonicalPathMonitor(off_canonical_threshold=3, early_window_calls=5)
    # First 5 are canonical
    for _ in range(5):
        m.observe(_tool_use("Read"))
    # Then 3 off-canonical — late in the run
    for tool in ["weird_a", "weird_b", "weird_c"]:
        v = m.observe(_tool_use(tool))
    assert v.should_abort is False
    assert v.off_canonical_count == 3
    assert v.total_tool_calls == 8


def test_abort_latches_after_first_trigger() -> None:
    """Once aborted, the verdict stays aborted even if subsequent calls
    are canonical."""
    m = CanonicalPathMonitor(off_canonical_threshold=2, early_window_calls=10)
    m.observe(_tool_use("weird_a"))
    v = m.observe(_tool_use("weird_b"))
    assert v.should_abort is True
    # Continue with canonical
    v = m.observe(_tool_use("Read"))
    assert v.should_abort is True


def test_reset_clears_state() -> None:
    m = CanonicalPathMonitor(off_canonical_threshold=2, early_window_calls=10)
    m.observe(_tool_use("weird_a"))
    m.observe(_tool_use("weird_b"))
    assert m.observe(_tool_use("Read")).should_abort is True

    m.reset()
    v = m.observe(_tool_use("Read"))
    assert v.should_abort is False
    assert v.total_tool_calls == 1
    assert v.off_canonical_count == 0


def test_non_tool_use_events_ignored() -> None:
    m = CanonicalPathMonitor()
    for kind in ["status", "text", "complete", "error", "usage", "file_change"]:
        v = m.observe(_other_event(kind))
    assert v.total_tool_calls == 0


def test_tool_use_with_empty_name_ignored() -> None:
    m = CanonicalPathMonitor()
    v = m.observe({"kind": "tool_use", "tool_name": ""})
    assert v.total_tool_calls == 0
    v = m.observe({"kind": "tool_use", "tool_name": None})
    assert v.total_tool_calls == 0


def test_case_insensitive_tool_match() -> None:
    m = CanonicalPathMonitor()
    for variant in ["read", "Read", "READ", "REaD"]:
        v = m.observe(_tool_use(variant))
    assert v.off_canonical_count == 0
    assert v.total_tool_calls == 4


def test_observe_accepts_object_with_attrs() -> None:
    """Real ``TaskEvent`` is a dataclass; the monitor must accept
    objects with attributes, not only dicts."""

    class FakeEvent:
        def __init__(self, kind, tool_name):
            self.kind = kind
            self.tool_name = tool_name

    m = CanonicalPathMonitor()
    v = m.observe(FakeEvent("tool_use", "Read"))
    assert v.total_tool_calls == 1
    assert v.off_canonical_count == 0


def test_custom_canonical_set_overrides_default() -> None:
    m = CanonicalPathMonitor(canonical_tools={"DoStuff", "Read"})
    # Read is in the custom set
    assert m.observe(_tool_use("Read")).off_canonical_count == 0
    # Bash is in the DEFAULT set but NOT the custom one — counts as off
    assert m.observe(_tool_use("Bash")).off_canonical_count == 1


# ---------------------------------------------------------------------------
# Verdict shape
# ---------------------------------------------------------------------------


def test_verdict_lists_off_canonical_tools() -> None:
    m = CanonicalPathMonitor(off_canonical_threshold=3, early_window_calls=10)
    for tool in ["weird_a", "weird_b", "weird_c"]:
        v = m.observe(_tool_use(tool))
    assert v.off_canonical_tools == ["weird_a", "weird_b", "weird_c"]


def test_verdict_immutable_across_observes() -> None:
    """Each call returns a fresh verdict — modifying one doesn't
    affect later calls."""
    m = CanonicalPathMonitor()
    v1 = m.observe(_tool_use("weird_a"))
    v1.off_canonical_tools.append("INTRUDER")
    v2 = m.observe(_tool_use("weird_b"))
    assert "INTRUDER" not in v2.off_canonical_tools


# ---------------------------------------------------------------------------
# Factory — config gate
# ---------------------------------------------------------------------------


def test_build_default_monitor_disabled_returns_none() -> None:
    cfg = MagicMock()
    cfg.coding.canonical_monitor.enabled = False
    assert build_default_monitor(cfg=cfg) is None


def test_build_default_monitor_enabled_returns_instance() -> None:
    cfg = MagicMock()
    cfg.coding.canonical_monitor.enabled = True
    cfg.coding.canonical_monitor.off_canonical_threshold = 5
    cfg.coding.canonical_monitor.early_window_calls = 20
    m = build_default_monitor(cfg=cfg)
    assert isinstance(m, CanonicalPathMonitor)
    assert m._threshold == 5  # noqa: SLF001
    assert m._window == 20  # noqa: SLF001
