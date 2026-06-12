"""Tests for kenning.desktop.sequence (catalog 09 T5)."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from kenning.desktop.sequence import (
    DesktopSequenceRunner,
    SequenceStatus,
    SequenceStep,
    StepOutcome,
    VlmVerdict,
    get_sequence_runner,
    set_sequence_runner,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_capture(*, monitor_index=0, png_bytes=b"\x89PNG_FAKE"):
    """Return a capture stub whose capture_monitor returns a Screenshot."""
    from kenning.desktop.capture import Screenshot

    class _Cap:
        captures = 0

        def capture_monitor(self, idx):
            type(self).captures += 1
            return Screenshot(
                image_bytes=png_bytes,
                monitor_index=monitor_index,
                width=1920, height=1080,
                timestamp=1.0, origin_x=0, origin_y=0,
            )

    return _Cap()


def _ok_step(name: str = "step") -> SequenceStep:
    return SequenceStep(description=name, action=lambda: True)


def _fail_step(name: str = "step") -> SequenceStep:
    return SequenceStep(description=name, action=lambda: None)


def _raise_step(name: str = "boom") -> SequenceStep:
    def _boom():
        raise RuntimeError("explosion")
    return SequenceStep(description=name, action=_boom)


# ---------------------------------------------------------------------------
# Singleton + dataclass invariants
# ---------------------------------------------------------------------------


def test_singleton_caches_and_can_be_swapped():
    set_sequence_runner(None)
    try:
        a = get_sequence_runner()
        b = get_sequence_runner()
        assert a is b
        custom = DesktopSequenceRunner()
        set_sequence_runner(custom)
        assert get_sequence_runner() is custom
    finally:
        set_sequence_runner(None)


def test_sequence_result_is_frozen():
    from kenning.desktop.sequence import SequenceResult
    r = SequenceResult(
        task="x", status=SequenceStatus.COMPLETED, success=True,
        steps=(), screenshots=(),
    )
    with pytest.raises(Exception):
        r.success = False  # type: ignore[misc]


def test_sequence_step_is_frozen():
    step = SequenceStep(description="x", action=lambda: True)
    with pytest.raises(Exception):
        step.description = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Empty / trivial sequence
# ---------------------------------------------------------------------------


def test_empty_sequence_completes_successfully():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap, bracket_screenshots=False)
    result = runner.run("nothing", steps=[])
    assert result.status is SequenceStatus.COMPLETED
    assert result.success is True
    assert result.steps == ()
    assert result.screenshots == ()


def test_single_ok_step_completes():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap)
    result = runner.run("hello", steps=[_ok_step("only step")])
    assert result.status is SequenceStatus.COMPLETED
    assert result.success is True
    assert len(result.steps) == 1
    assert result.steps[0].outcome is StepOutcome.OK
    assert result.steps[0].description == "only step"
    assert result.steps[0].step_index == 1


# ---------------------------------------------------------------------------
# Bracket screenshots
# ---------------------------------------------------------------------------


def test_bracket_screenshots_captures_before_and_after_per_step():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap, bracket_screenshots=True)
    result = runner.run("two", steps=[_ok_step("a"), _ok_step("b")])
    assert result.success is True
    assert len(result.screenshots) == 2
    before1, after1 = result.screenshots[0]
    assert before1.step == 1 and before1.when == "before"
    assert after1.step == 1 and after1.when == "after"
    before2, after2 = result.screenshots[1]
    assert before2.step == 2 and after2.step == 2
    # capture_monitor called once per before and once per after.
    assert type(cap).captures == 4


def test_screenshot_refs_record_dimensions_and_monitor_index():
    cap = _fake_capture(monitor_index=1)
    runner = DesktopSequenceRunner(capture=cap, monitor_index=1)
    result = runner.run("dim", steps=[_ok_step()])
    before, after = result.screenshots[0]
    assert before.width == 1920
    assert before.height == 1080
    assert before.monitor_index == 1
    assert after.monitor_index == 1
    assert before.bytes_discarded is True  # analyze-and-discard default
    assert after.bytes_discarded is True


def test_bracket_screenshots_disabled_skips_capture():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(
        capture=cap, bracket_screenshots=False,
    )
    result = runner.run("no-bracket", steps=[_ok_step(), _ok_step()])
    assert result.success is True
    # capture_monitor should never have been called.
    assert type(cap).captures == 0
    # ScreenshotRef objects still exist (empty width/height) so the
    # result schema is uniform.
    assert len(result.screenshots) == 2


def test_capture_exception_records_error_but_step_still_runs():
    class _BrokenCap:
        called = 0

        def capture_monitor(self, idx):
            type(self).called += 1
            raise RuntimeError("mss died")

    runner = DesktopSequenceRunner(capture=_BrokenCap())
    seen = []
    step = SequenceStep(
        description="recover", action=lambda: seen.append("ran") or True,
    )
    result = runner.run("recover", steps=[step])
    assert seen == ["ran"]
    assert result.success is True
    before, after = result.screenshots[0]
    assert "capture exception" in (before.error or "")
    assert "capture exception" in (after.error or "")


def test_capture_returns_none_records_capture_failed():
    class _NoneCap:
        def capture_monitor(self, idx):
            return None

    runner = DesktopSequenceRunner(capture=_NoneCap())
    result = runner.run("none-cap", steps=[_ok_step()])
    assert result.success is True
    before, after = result.screenshots[0]
    assert before.error == "capture returned None"
    assert after.error == "capture returned None"


def test_no_capture_wired_records_no_capture():
    runner = DesktopSequenceRunner(capture=None, bracket_screenshots=True)
    # The fallback path tries to resolve get_screen_capture; in test
    # context that succeeds and returns a real ScreenCapture instance
    # which itself may succeed or fail per environment. To exercise
    # the explicit "no capture" branch, force the resolver to return None.
    runner._capture = None
    # Monkey-patching the fallback is the only way to deterministically
    # exercise this branch:
    import kenning.desktop.capture as cap_mod
    original = cap_mod.get_screen_capture
    cap_mod.get_screen_capture = lambda: None  # type: ignore[assignment]
    try:
        result = runner.run("nocap", steps=[_ok_step()])
        before, after = result.screenshots[0]
        assert before.error == "no capture wired"
        assert after.error == "no capture wired"
    finally:
        cap_mod.get_screen_capture = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Failure semantics
# ---------------------------------------------------------------------------


def test_failed_action_aborts_remaining_steps():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap)
    executed = []
    s1 = SequenceStep(
        description="first",
        action=lambda: executed.append(1) or True,
    )
    s2 = _fail_step("second")
    s3 = SequenceStep(
        description="third",
        action=lambda: executed.append(3) or True,
    )
    result = runner.run("fail-mid", steps=[s1, s2, s3])
    assert result.status is SequenceStatus.FAILED
    assert result.success is False
    assert result.failed_at_step == 2
    assert executed == [1]  # s3 never ran
    assert len(result.steps) == 2  # s1 + s2 recorded
    assert result.steps[1].outcome is StepOutcome.FAILED


def test_exception_in_action_aborts_with_status_failed():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap)
    result = runner.run("boom", steps=[_ok_step(), _raise_step("uh oh")])
    assert result.status is SequenceStatus.FAILED
    assert result.success is False
    assert result.failed_at_step == 2
    assert "explosion" in (result.error or "")
    assert result.steps[1].outcome is StepOutcome.EXCEPTION


def test_non_step_in_list_returns_error_status():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap)
    result = runner.run("bad", steps=["not a step"])  # type: ignore[list-item]
    assert result.status is SequenceStatus.ERROR
    assert result.success is False
    assert result.failed_at_step == 1


def test_action_returning_result_with_success_flag_is_honoured():
    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap)
    from kenning.desktop.input_control import InputControlResult
    s1 = SequenceStep(
        description="result-shape ok",
        action=lambda: InputControlResult(success=True, action="click"),
    )
    s2 = SequenceStep(
        description="result-shape fail",
        action=lambda: InputControlResult(
            success=False, action="click", error="safety: blocked",
        ),
    )
    result = runner.run("result-shape", steps=[s1, s2])
    assert result.status is SequenceStatus.FAILED
    assert result.failed_at_step == 2
    assert result.steps[0].outcome is StepOutcome.OK
    assert result.steps[1].outcome is StepOutcome.FAILED
    assert "blocked" in (result.steps[1].error or "")


# ---------------------------------------------------------------------------
# VLM verification
# ---------------------------------------------------------------------------


def test_vlm_verification_succeeds_on_yes_response():
    cap = _fake_capture()
    vlm = MagicMock(return_value="yes")
    runner = DesktopSequenceRunner(
        capture=cap, vlm_describe=vlm,
        verify_with_vlm=True,
    )
    result = runner.run("verify", steps=[_ok_step("click submit")])
    assert result.success is True
    assert result.steps[0].vlm_verdict is VlmVerdict.SUCCEEDED
    vlm.assert_called_once()


def test_vlm_failure_downgrades_step_to_failed():
    cap = _fake_capture()
    vlm = MagicMock(return_value="no the dialog is still open")
    runner = DesktopSequenceRunner(
        capture=cap, vlm_describe=vlm,
        verify_with_vlm=True,
    )
    result = runner.run("vlm-fail", steps=[_ok_step()])
    assert result.status is SequenceStatus.FAILED
    assert result.steps[0].outcome is StepOutcome.FAILED
    assert result.steps[0].vlm_verdict is VlmVerdict.FAILED


def test_vlm_exception_is_degraded_not_fatal():
    cap = _fake_capture()

    def _boom(_img, _prompt):
        raise RuntimeError("vlm gone")

    runner = DesktopSequenceRunner(
        capture=cap, vlm_describe=_boom,
        verify_with_vlm=True,
    )
    result = runner.run("vlm-degraded", steps=[_ok_step()])
    # DEGRADED does NOT downgrade an OK action.
    assert result.success is True
    assert result.steps[0].vlm_verdict is VlmVerdict.DEGRADED
    assert "vlm exception" in (result.steps[0].vlm_message or "")


def test_verify_disabled_skips_vlm():
    cap = _fake_capture()
    vlm = MagicMock(return_value="anything")
    runner = DesktopSequenceRunner(
        capture=cap, vlm_describe=vlm,
        verify_with_vlm=False,
    )
    result = runner.run("noverify", steps=[_ok_step(), _ok_step()])
    assert result.success is True
    assert all(s.vlm_verdict is VlmVerdict.SKIPPED for s in result.steps)
    vlm.assert_not_called()


def test_auto_pass_skips_vlm_for_nearby_subsequent_steps():
    cap = _fake_capture()
    vlm = MagicMock(return_value="yes")
    runner = DesktopSequenceRunner(
        capture=cap, vlm_describe=vlm,
        verify_with_vlm=True,
        auto_pass_radius_px=100,
    )
    # First step anchors at (500, 500) -> confirmed.
    # Second step at (510, 505) -> within 100 px -> AUTO_PASSED.
    # Third step at (1000, 1000) -> outside radius -> VLM called.
    s1 = SequenceStep(
        description="click panel A",
        action=lambda: True,
        target_x=500, target_y=500,
    )
    s2 = SequenceStep(
        description="click panel A (nearby)",
        action=lambda: True,
        target_x=510, target_y=505,
    )
    s3 = SequenceStep(
        description="click panel B (far)",
        action=lambda: True,
        target_x=1000, target_y=1000,
    )
    result = runner.run("autopass", steps=[s1, s2, s3])
    assert result.success is True
    assert result.steps[0].vlm_verdict is VlmVerdict.SUCCEEDED
    assert result.steps[1].vlm_verdict is VlmVerdict.AUTO_PASSED
    assert result.steps[2].vlm_verdict is VlmVerdict.SUCCEEDED
    # VLM called for s1 and s3, NOT s2.
    assert vlm.call_count == 2


def test_auto_pass_requires_target_coordinates():
    cap = _fake_capture()
    vlm = MagicMock(return_value="yes")
    runner = DesktopSequenceRunner(
        capture=cap, vlm_describe=vlm,
        verify_with_vlm=True,
    )
    # Step without target_x/target_y can never auto-pass.
    s1 = SequenceStep(
        description="anchor", action=lambda: True,
        target_x=100, target_y=100,
    )
    s2 = SequenceStep(description="no-target", action=lambda: True)
    runner.run("no-anchor", steps=[s1, s2])
    # VLM called for both -- s2 has no target to compare against.
    assert vlm.call_count == 2


# ---------------------------------------------------------------------------
# Singleton + JSON-serialisability sanity
# ---------------------------------------------------------------------------


def test_result_dataclasses_are_dict_serialisable():
    """Each frozen dataclass field is a primitive / dataclass / enum,
    so the result can flow through bus events and audit log via
    json.dumps (which handles tuples + lists identically)."""
    import json
    from dataclasses import asdict

    cap = _fake_capture()
    runner = DesktopSequenceRunner(capture=cap, bracket_screenshots=False)
    result = runner.run("serialise", steps=[_ok_step()])
    d = asdict(result)
    assert d["task"] == "serialise"
    assert d["status"] == "completed"
    assert d["success"] is True
    # asdict preserves tuples; json round-trip flattens to lists.
    encoded = json.dumps(d, default=str)
    decoded = json.loads(encoded)
    assert isinstance(decoded["steps"], list)
    assert decoded["steps"][0]["description"] == "step"
