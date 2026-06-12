"""Tests for the 5-detector loop-detection suite (T1)."""

from __future__ import annotations

import pytest

from kenning.agent_loop.loop_detection_extended import (
    CRITICAL_THRESHOLD,
    DEFAULT_POLL_TOOLS,
    GLOBAL_CIRCUIT_BREAKER_THRESHOLD,
    GlobalCircuitBreakerDetector,
    KnownPollNoProgressDetector,
    LoopDetectionManager,
    OutcomeKind,
    PingPongDetector,
    TOOL_CALL_HISTORY_SIZE,
    ToolCallRecord,
    UNKNOWN_TOOL_THRESHOLD,
    UnknownToolRepeatDetector,
    WARNING_THRESHOLD,
    hash_outcome,
    hash_tool_call,
)


# ----------------------------------------------------------------------
# hash helpers


def test_hash_tool_call_stable_for_identical_inputs() -> None:
    a = hash_tool_call("foo", {"x": 1, "y": 2})
    b = hash_tool_call("foo", {"y": 2, "x": 1})
    assert a == b


def test_hash_tool_call_differs_for_different_params() -> None:
    a = hash_tool_call("foo", {"x": 1})
    b = hash_tool_call("foo", {"x": 2})
    assert a != b


def test_hash_outcome_distinguishes_error_from_success() -> None:
    success = hash_outcome(ToolCallRecord(tool_name="t", outcome_kind=OutcomeKind.SUCCESS))
    error = hash_outcome(
        ToolCallRecord(tool_name="t", outcome_kind=OutcomeKind.ERROR, error_message="boom"),
    )
    assert success != error


def test_hash_outcome_running_constant() -> None:
    a = hash_outcome(ToolCallRecord(tool_name="t1", outcome_kind=OutcomeKind.RUNNING))
    b = hash_outcome(ToolCallRecord(tool_name="t2", outcome_kind=OutcomeKind.RUNNING))
    # Running hash is independent of tool name (it's just "running").
    assert a == b


# ----------------------------------------------------------------------
# Constants


def test_constants_match_openclaw_defaults() -> None:
    assert TOOL_CALL_HISTORY_SIZE == 30
    assert WARNING_THRESHOLD == 10
    assert CRITICAL_THRESHOLD == 20
    assert GLOBAL_CIRCUIT_BREAKER_THRESHOLD == 30
    assert UNKNOWN_TOOL_THRESHOLD == 10


def test_default_poll_tools_includes_command_status() -> None:
    assert "command_status" in DEFAULT_POLL_TOOLS


# ----------------------------------------------------------------------
# UnknownToolRepeatDetector


def test_unknown_tool_no_match_returns_zero_count() -> None:
    detector = UnknownToolRepeatDetector()
    record = ToolCallRecord(
        tool_name="t",
        outcome_kind=OutcomeKind.ERROR,
        error_message="some other error",
    )
    verdict = detector.observe(record)
    assert verdict.count == 0


def test_unknown_tool_success_does_not_count() -> None:
    detector = UnknownToolRepeatDetector()
    verdict = detector.observe(ToolCallRecord(tool_name="ok", outcome_kind=OutcomeKind.SUCCESS))
    assert verdict.count == 0


def test_unknown_tool_critical_after_threshold_repeats() -> None:
    detector = UnknownToolRepeatDetector()
    last_verdict = None
    for _ in range(UNKNOWN_TOOL_THRESHOLD):
        last_verdict = detector.observe(
            ToolCallRecord(
                tool_name="t",
                outcome_kind=OutcomeKind.ERROR,
                error_message="Unknown tool: ghost_tool",
            )
        )
    assert last_verdict.hard_escalation is not None
    assert "ghost_tool" in last_verdict.signature
    assert detector.halted is True


def test_unknown_tool_different_names_dont_accumulate() -> None:
    detector = UnknownToolRepeatDetector(critical_threshold=3)
    for name in ("alpha", "beta", "gamma"):
        verdict = detector.observe(
            ToolCallRecord(
                tool_name="t",
                outcome_kind=OutcomeKind.ERROR,
                error_message=f"Unknown tool: {name}",
            )
        )
    # Each unknown name should be counted independently; nothing trips.
    assert verdict.hard_escalation is None


def test_unknown_tool_reset_clears_state() -> None:
    detector = UnknownToolRepeatDetector(critical_threshold=2)
    for _ in range(2):
        detector.observe(
            ToolCallRecord(
                tool_name="t",
                outcome_kind=OutcomeKind.ERROR,
                error_message="unknown tool: ghost",
            )
        )
    assert detector.halted is True
    detector.reset()
    assert detector.halted is False


# ----------------------------------------------------------------------
# KnownPollNoProgressDetector


def test_known_poll_command_status_repeating_warns() -> None:
    detector = KnownPollNoProgressDetector(warning_threshold=3, critical_threshold=5)
    verdict = None
    for _ in range(3):
        verdict = detector.observe(
            ToolCallRecord(
                tool_name="command_status",
                params={"job_id": "abc"},
                outcome_kind=OutcomeKind.SUCCESS,
                result_summary={"status": "running", "tail": "..."},
            )
        )
    assert verdict.soft_warning is not None


def test_known_poll_critical_halts() -> None:
    detector = KnownPollNoProgressDetector(warning_threshold=3, critical_threshold=5)
    verdict = None
    for _ in range(5):
        verdict = detector.observe(
            ToolCallRecord(
                tool_name="command_status",
                params={"job_id": "abc"},
                outcome_kind=OutcomeKind.SUCCESS,
                result_summary={"status": "running", "tail": "..."},
            )
        )
    assert verdict.hard_escalation is not None
    assert detector.halted


def test_known_poll_progress_change_resets_count() -> None:
    detector = KnownPollNoProgressDetector(warning_threshold=3, critical_threshold=5)
    for _ in range(2):
        detector.observe(
            ToolCallRecord(
                tool_name="command_status",
                params={"job_id": "abc"},
                outcome_kind=OutcomeKind.SUCCESS,
                result_summary={"status": "running"},
            )
        )
    # Progress changes; outcome_hash differs.
    verdict = detector.observe(
        ToolCallRecord(
            tool_name="command_status",
            params={"job_id": "abc"},
            outcome_kind=OutcomeKind.SUCCESS,
            result_summary={"status": "running", "tail": "new output"},
        )
    )
    assert verdict.count == 1


def test_known_poll_non_poll_tool_ignored() -> None:
    detector = KnownPollNoProgressDetector(warning_threshold=3, critical_threshold=5)
    verdict = None
    for _ in range(10):
        verdict = detector.observe(
            ToolCallRecord(tool_name="not_a_poll", outcome_kind=OutcomeKind.SUCCESS)
        )
    assert verdict.count == 0


def test_known_poll_process_with_poll_action_counts() -> None:
    detector = KnownPollNoProgressDetector(warning_threshold=2, critical_threshold=4)
    verdict = None
    for _ in range(2):
        verdict = detector.observe(
            ToolCallRecord(
                tool_name="process",
                params={"action": "poll", "pid": 123},
                outcome_kind=OutcomeKind.SUCCESS,
                result_summary={"status": "running"},
            )
        )
    assert verdict.soft_warning is not None


# ----------------------------------------------------------------------
# PingPongDetector


def test_ping_pong_alternating_warns() -> None:
    detector = PingPongDetector(warning_threshold=4, critical_threshold=8)
    last_verdict = None
    for i in range(4):
        tool = "alpha" if i % 2 == 0 else "beta"
        last_verdict = detector.observe(
            ToolCallRecord(tool_name=tool, outcome_kind=OutcomeKind.SUCCESS)
        )
    assert last_verdict.soft_warning is not None


def test_ping_pong_critical_halts() -> None:
    detector = PingPongDetector(warning_threshold=4, critical_threshold=8)
    last_verdict = None
    for i in range(8):
        tool = "alpha" if i % 2 == 0 else "beta"
        last_verdict = detector.observe(
            ToolCallRecord(tool_name=tool, outcome_kind=OutcomeKind.SUCCESS)
        )
    assert last_verdict.hard_escalation is not None
    assert detector.halted


def test_ping_pong_steady_state_does_not_trigger() -> None:
    detector = PingPongDetector(warning_threshold=3, critical_threshold=5)
    last_verdict = None
    for _ in range(10):
        last_verdict = detector.observe(
            ToolCallRecord(tool_name="alpha", outcome_kind=OutcomeKind.SUCCESS)
        )
    # Steady same-signature is generic repeat; ping-pong should NOT fire.
    assert last_verdict.count == 0


def test_ping_pong_three_distinct_signatures_does_not_trigger() -> None:
    detector = PingPongDetector(warning_threshold=3, critical_threshold=5)
    last_verdict = None
    for i in range(6):
        tool = ["a", "b", "c"][i % 3]
        last_verdict = detector.observe(
            ToolCallRecord(tool_name=tool, outcome_kind=OutcomeKind.SUCCESS)
        )
    # Three-way rotation is NOT alternation; count should be 1 (the
    # last entry alternates with the prior one but the one before
    # that breaks the pattern).
    assert last_verdict.hard_escalation is None


def test_ping_pong_with_only_one_entry_returns_zero() -> None:
    detector = PingPongDetector()
    verdict = detector.observe(ToolCallRecord(tool_name="solo"))
    assert verdict.count == 0


# ----------------------------------------------------------------------
# GlobalCircuitBreakerDetector


def test_global_circuit_breaker_at_threshold_halts() -> None:
    detector = GlobalCircuitBreakerDetector(critical_threshold=5)
    last_verdict = None
    for _ in range(5):
        last_verdict = detector.observe(
            ToolCallRecord(tool_name="t", outcome_kind=OutcomeKind.SUCCESS)
        )
    assert last_verdict.hard_escalation is not None
    assert detector.halted


def test_global_circuit_breaker_below_threshold_does_not_halt() -> None:
    detector = GlobalCircuitBreakerDetector(critical_threshold=5)
    last_verdict = None
    for _ in range(4):
        last_verdict = detector.observe(
            ToolCallRecord(tool_name="t", outcome_kind=OutcomeKind.SUCCESS)
        )
    assert last_verdict.hard_escalation is None


def test_global_circuit_breaker_history_size_caps_count() -> None:
    detector = GlobalCircuitBreakerDetector(history_size=3, critical_threshold=10)
    last_verdict = None
    for _ in range(20):
        last_verdict = detector.observe(
            ToolCallRecord(tool_name="t", outcome_kind=OutcomeKind.SUCCESS)
        )
    # History buffer caps at 3, so count tops out at 3.
    assert last_verdict.count <= 3
    assert last_verdict.hard_escalation is None


# ----------------------------------------------------------------------
# LoopDetectionManager


def test_manager_default_enabled_detectors() -> None:
    manager = LoopDetectionManager()
    assert set(manager.detector_names) == {
        "unknown_tool",
        "known_poll",
        "ping_pong",
        "global_circuit_breaker",
    }


def test_manager_can_disable_detectors() -> None:
    manager = LoopDetectionManager(enabled_detectors={"ping_pong"})
    assert manager.detector_names == ("ping_pong",)


def test_manager_unknown_detector_name_rejected() -> None:
    with pytest.raises(ValueError):
        LoopDetectionManager(enabled_detectors={"nonexistent"})


def test_manager_observe_returns_dominant_verdict() -> None:
    manager = LoopDetectionManager(
        enabled_detectors={"global_circuit_breaker"},
        global_circuit_breaker_threshold=3,
    )
    last = None
    for _ in range(3):
        last, per = manager.observe(ToolCallRecord(tool_name="t"))
    assert last.hard_escalation is not None
    assert "global_circuit_breaker" in per


def test_manager_observe_returns_per_detector_map() -> None:
    manager = LoopDetectionManager()
    _, per = manager.observe(ToolCallRecord(tool_name="t"))
    assert set(per.keys()) == {
        "unknown_tool",
        "known_poll",
        "ping_pong",
        "global_circuit_breaker",
    }


def test_manager_reset_clears_all_detectors() -> None:
    manager = LoopDetectionManager(
        enabled_detectors={"global_circuit_breaker"},
        global_circuit_breaker_threshold=2,
    )
    for _ in range(2):
        manager.observe(ToolCallRecord(tool_name="t"))
    assert manager.halted
    manager.reset()
    assert not manager.halted


def test_manager_with_no_active_loop_returns_benign_signature() -> None:
    manager = LoopDetectionManager()
    verdict, _ = manager.observe(ToolCallRecord(tool_name="ok"))
    assert verdict.hard_escalation is None
    assert verdict.soft_warning is None
    assert verdict.signature.startswith("ok:") or verdict.signature.startswith("global:") or verdict.signature.startswith("pingpong:") or verdict.signature.startswith("poll:") or verdict.signature.startswith("unknown")
