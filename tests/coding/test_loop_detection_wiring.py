"""Tests for the coding-runner loop-detection listener (T1).

CodingTaskRunner._make_loop_detection_listener builds a per-task listener that
runs the 5-detector LoopDetectionManager over the TOOL_RESULT stream and queues
a single spoken heads-up when a hard escalation fires. It logs + narrates only
-- never cancels. These tests exercise the listener via a __new__ stub runner
(the method only touches the loop-alert queue + config, not the full runner).
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from kenning.coding.bridge import EventKind
from kenning.coding.runner import CodingTaskRunner


def _runner():
    r = CodingTaskRunner.__new__(CodingTaskRunner)
    r._pending_loop_alerts = []
    r._loop_alert_lock = threading.Lock()
    return r


def _tool_result(tool_name: str, *, success: bool, brief: str):
    return SimpleNamespace(
        kind=EventKind.TOOL_RESULT,
        tool_name=tool_name,
        tool_success=success,
        tool_brief=brief,
    )


def test_identical_failures_trip_hard_escalation_and_queue_one_alert():
    r = _runner()
    listener = r._make_loop_detection_listener(handle=None)
    assert listener is not None

    # The global circuit breaker fires at 30 identical tool+outcome repeats.
    for _ in range(35):
        listener(_tool_result("frobnicate", success=False, brief="boom"))

    alert = r.pop_loop_alert()
    assert alert is not None
    assert "repeated the same step" in alert
    # Narrated at most once per task -- the queue holds a single line.
    assert r.pop_loop_alert() is None


def test_few_repeats_do_not_alert():
    r = _runner()
    listener = r._make_loop_detection_listener(handle=None)
    for _ in range(5):
        listener(_tool_result("frobnicate", success=False, brief="boom"))
    assert r.pop_loop_alert() is None


def test_distinct_successful_tools_no_false_positive():
    r = _runner()
    listener = r._make_loop_detection_listener(handle=None)
    for i in range(40):
        listener(_tool_result(f"tool_{i}", success=True, brief=f"ok {i}"))
    assert r.pop_loop_alert() is None


def test_non_tool_result_events_ignored():
    r = _runner()
    listener = r._make_loop_detection_listener(handle=None)
    for _ in range(40):
        listener(SimpleNamespace(kind=EventKind.TEXT, text="thinking..."))
    assert r.pop_loop_alert() is None


def test_listener_never_raises_on_malformed_event():
    r = _runner()
    listener = r._make_loop_detection_listener(handle=None)
    # Missing attributes / wrong shapes must be swallowed (fail-open).
    listener(SimpleNamespace())
    listener(object())
    listener(None)
    assert r.pop_loop_alert() is None


def test_disabled_via_config_returns_no_listener(monkeypatch):
    from kenning.config import get_config

    cfg = get_config()
    monkeypatch.setattr(cfg.coding, "loop_detection_enabled", False)
    r = _runner()
    assert r._make_loop_detection_listener(handle=None) is None
