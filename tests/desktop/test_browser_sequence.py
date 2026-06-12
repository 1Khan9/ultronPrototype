"""Tests for the browser sequence runner (catalog 10 batch 8).

All dependencies injected; no real ``browser-use`` binary, no real
VLM, no network. Per ``docs/test_sweep_binding_rules.md``: R1
(injection only), R4 (no network), R7 (order-independent), R11 (no
voice stack), R12 (deterministic injected clock; no sleeps).
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from kenning.desktop import browser_sequence as bseq
from kenning.desktop.sequence import SequenceStatus, StepOutcome, VlmVerdict


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeScreenshotResult:
    def __init__(
        self, *, success: bool = True, image_bytes: Optional[bytes] = b"PNGDATA" * 4
    ) -> None:
        self.success = success
        self.image_bytes = image_bytes
        self.error = None if success else "screenshot failed"


class _FakeTool:
    """Records screenshot calls; yields scripted results."""

    def __init__(self, *, screenshot_succeeds: bool = True) -> None:
        self.screenshot_calls = 0
        self._screenshot_succeeds = screenshot_succeeds

    def screenshot(
        self, *, full_page: bool = False, user_text: str = ""
    ) -> Any:
        self.screenshot_calls += 1
        return _FakeScreenshotResult(success=self._screenshot_succeeds)


class _ActionResult:
    """Stand-in for a BrowserUseTool result with a success flag."""

    def __init__(self, success: bool, error: Optional[str] = None) -> None:
        self.success = success
        self.error = error


def _clock_factory() -> Any:
    counter = {"t": 0.0}

    def clock() -> float:
        counter["t"] += 1.0
        return counter["t"]

    return clock


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    bseq.set_browser_sequence_runner(None)
    yield
    bseq.set_browser_sequence_runner(None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRunHappyPath:
    def test_all_steps_succeed(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        calls: list[str] = []
        steps = [
            bseq.BrowserSequenceStep(
                "open", lambda: calls.append("open") or _ActionResult(True)
            ),
            bseq.BrowserSequenceStep(
                "click", lambda: calls.append("click") or _ActionResult(True)
            ),
        ]
        result = runner.run("login flow", steps)
        assert result.status is SequenceStatus.COMPLETED
        assert result.success is True
        assert len(result.steps) == 2
        assert result.failed_at_step is None
        assert calls == ["open", "click"]
        # 2 steps x 2 captures (before + after) = 4 screenshots.
        assert tool.screenshot_calls == 4
        assert len(result.screenshots) == 2

    def test_truthy_non_result_action(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: "done")],
        )
        assert result.success is True
        assert result.steps[0].outcome is StepOutcome.OK

    def test_screenshot_refs_carry_byte_length(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        before, after = result.screenshots[0]
        assert before.byte_length > 0
        assert after.byte_length > 0
        assert before.bytes_discarded is True


# ---------------------------------------------------------------------------
# Fail-fast
# ---------------------------------------------------------------------------


class TestFailFast:
    def test_falsy_action_aborts(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        executed: list[str] = []
        steps = [
            bseq.BrowserSequenceStep(
                "a", lambda: executed.append("a") or _ActionResult(True)
            ),
            bseq.BrowserSequenceStep(
                "b", lambda: executed.append("b") or _ActionResult(False, "nope")
            ),
            bseq.BrowserSequenceStep(
                "c", lambda: executed.append("c") or _ActionResult(True)
            ),
        ]
        result = runner.run("task", steps)
        assert result.status is SequenceStatus.FAILED
        assert result.success is False
        assert result.failed_at_step == 2
        # Step c must NOT have run.
        assert executed == ["a", "b"]
        assert len(result.steps) == 2

    def test_exception_aborts(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())

        def boom() -> Any:
            raise RuntimeError("kaboom")

        result = runner.run(
            "task",
            [
                bseq.BrowserSequenceStep("ok", lambda: _ActionResult(True)),
                bseq.BrowserSequenceStep("boom", boom),
            ],
        )
        assert result.status is SequenceStatus.FAILED
        assert result.failed_at_step == 2
        assert result.steps[1].outcome is StepOutcome.EXCEPTION
        assert "kaboom" in (result.error or "")

    def test_none_falsy(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: None)],
        )
        assert result.success is False
        assert result.steps[0].outcome is StepOutcome.FAILED

    def test_non_step_is_error(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        result = runner.run("task", ["not a step"])  # type: ignore[list-item]
        assert result.status is SequenceStatus.ERROR
        assert result.failed_at_step == 1


# ---------------------------------------------------------------------------
# VLM verification
# ---------------------------------------------------------------------------


class TestVlmVerification:
    def test_vlm_success(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(
            tool=tool,
            vlm_describe=lambda png, prompt: "yes",
            verify_with_vlm=True,
            clock_fn=_clock_factory(),
        )
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        assert result.success is True
        assert result.steps[0].vlm_verdict is VlmVerdict.SUCCEEDED

    def test_vlm_rejects_downgrades_to_failed(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(
            tool=tool,
            vlm_describe=lambda png, prompt: "the page shows an error",
            verify_with_vlm=True,
            clock_fn=_clock_factory(),
        )
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        # Action succeeded but VLM rejected -> FAILED.
        assert result.success is False
        assert result.steps[0].outcome is StepOutcome.FAILED
        assert result.steps[0].vlm_verdict is VlmVerdict.FAILED

    def test_vlm_disabled_is_skipped(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        assert result.steps[0].vlm_verdict is VlmVerdict.SKIPPED

    def test_vlm_exception_is_degraded(self) -> None:
        tool = _FakeTool()

        def boom_vlm(png: bytes, prompt: str) -> str:
            raise RuntimeError("vlm down")

        runner = bseq.BrowserSequenceRunner(
            tool=tool,
            vlm_describe=boom_vlm,
            verify_with_vlm=True,
            clock_fn=_clock_factory(),
        )
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        # Degraded VLM does not downgrade the action's own success.
        assert result.success is True
        assert result.steps[0].vlm_verdict is VlmVerdict.DEGRADED

    def test_auto_pass_within_radius(self) -> None:
        tool = _FakeTool()
        vlm_calls: list[str] = []
        runner = bseq.BrowserSequenceRunner(
            tool=tool,
            vlm_describe=lambda png, prompt: vlm_calls.append(prompt) or "yes",
            verify_with_vlm=True,
            auto_pass_radius_px=150,
            clock_fn=_clock_factory(),
        )
        steps = [
            bseq.BrowserSequenceStep(
                "first", lambda: _ActionResult(True), target_x=100, target_y=100
            ),
            bseq.BrowserSequenceStep(
                "near", lambda: _ActionResult(True), target_x=120, target_y=120
            ),
        ]
        result = runner.run("task", steps)
        assert result.success is True
        # First step calls VLM; second is within radius -> auto-passed.
        assert result.steps[0].vlm_verdict is VlmVerdict.SUCCEEDED
        assert result.steps[1].vlm_verdict is VlmVerdict.AUTO_PASSED
        assert len(vlm_calls) == 1


# ---------------------------------------------------------------------------
# Screenshot bracket degradation
# ---------------------------------------------------------------------------


class TestScreenshotDegradation:
    def test_no_tool_still_runs_steps(self) -> None:
        runner = bseq.BrowserSequenceRunner(tool=None, clock_fn=_clock_factory())
        # No singleton wired either.
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        assert result.success is True
        before, after = result.screenshots[0]
        assert before.error is not None

    def test_screenshot_failure_does_not_abort(self) -> None:
        tool = _FakeTool(screenshot_succeeds=False)
        runner = bseq.BrowserSequenceRunner(tool=tool, clock_fn=_clock_factory())
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        # The step still succeeds; the bracket just records the error.
        assert result.success is True
        assert result.screenshots[0][0].error is not None

    def test_bracket_disabled(self) -> None:
        tool = _FakeTool()
        runner = bseq.BrowserSequenceRunner(
            tool=tool, bracket_screenshots=False, clock_fn=_clock_factory()
        )
        result = runner.run(
            "task",
            [bseq.BrowserSequenceStep("x", lambda: _ActionResult(True))],
        )
        # No screenshots taken.
        assert tool.screenshot_calls == 0
        assert result.success is True


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_default_constructs(self) -> None:
        r = bseq.get_browser_sequence_runner()
        assert isinstance(r, bseq.BrowserSequenceRunner)

    def test_set_overrides(self) -> None:
        custom = bseq.BrowserSequenceRunner()
        bseq.set_browser_sequence_runner(custom)
        assert bseq.get_browser_sequence_runner() is custom

    def test_all_exports_present(self) -> None:
        for name in bseq.__all__:
            assert hasattr(bseq, name)
