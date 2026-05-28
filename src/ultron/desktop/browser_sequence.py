"""Browser sequence runner with per-step screenshot bracketing.

Catalog 10 batch 8 (creative extension). The browser-domain analog
of :class:`ultron.desktop.sequence.DesktopSequenceRunner` (catalog 09
T5): runs a list of browser steps with a before/after screenshot
bracket per step + optional VLM verification + fail-fast contract.

Where the desktop runner captures frames via mss
(:class:`ultron.desktop.capture.ScreenCapture`), this runner captures
via :meth:`ultron.desktop.browser_use.BrowserUseTool.screenshot` in
base64 mode -- so the page is captured headlessly WITHOUT occupying
the user's display. That is the headline difference + the reason a
browser sequence is worth a distinct runner: a multi-step web
automation ("log in, navigate, fill the form, submit, read the
confirmation") gets a visual audit trail + per-step VLM "did it
work?" verification without ever flashing a window at the user.

Architecture mirrors the desktop runner:

* Each step is a :class:`BrowserSequenceStep` -- a description + a
  zero-arg callable + optional anchor coords + soft timeout.
* The runner brackets each step's action between two
  ``tool.screenshot(user_text=...)`` captures (base64 mode, bytes
  discarded post-VLM per analyze-and-discard).
* When ``verify_with_vlm=True`` and a ``vlm_describe`` callable is
  wired, the after-frame is routed through the VLM with a
  confirmation-keyword prompt identical to the desktop runner's.
* On the first step failure (action falsy / raised / VLM rejected),
  the runner aborts -- remaining steps are NOT executed.
* Auto-pass radius: steps whose anchor coords fall within
  :data:`SEQUENCE_AUTO_PASS_RADIUS_PX` of the prior confirmed anchor
  skip the redundant VLM round-trip.

The shared :class:`SequenceStatus` / :class:`StepOutcome` /
:class:`VlmVerdict` enums are re-used from
:mod:`ultron.desktop.sequence` so consumers handle one taxonomy
across desktop + browser sequences.

Things deliberately NOT ported from the upstream browser-use recipe
docs (matching the desktop runner's posture):

* No natural-language step planner -- ultron's LLM intent router is
  more capable; the runner takes an explicit step list.
* No blocking ``input()`` approval between steps -- incompatible
  with the voice-first model. Risky individual actions (eval /
  cookies / cdp_python) carry their OWN two-phase approval inside
  the action callable; the sequence runner adds the visual bracket,
  not a second approval layer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from ultron.desktop.sequence import (
    SEQUENCE_AUTO_PASS_RADIUS_PX,
    SequenceStatus,
    StepOutcome,
    VlmVerdict,
)
from ultron.utils.logging import get_logger

logger = get_logger("desktop.browser_sequence")


# ---------------------------------------------------------------------------
# Step + result types (browser-specific; enums reused from desktop.sequence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowserSequenceStep:
    """One step in a browser sequence.

    Attributes:
        description: human-readable description spoken to the VLM
            ("Click sign in", "Fill the email field") AND surfaced in
            the audit log.
        action: zero-arg callable invoked between captures. Its return
            value is recorded under ``action_result``. Truthy (or an
            object with ``success=True``) means the step's own
            contract succeeded; falsy / ``success=False`` means it
            failed. Wrap gated BrowserUseTool calls here.
        target_x / target_y: optional anchor coords (e.g. a bbox
            centre) for the auto-pass-radius check across consecutive
            same-region steps.
        timeout_s: per-step soft timeout, recorded for audit; the
            action owns its own blocking semantics.
    """

    description: str
    action: Callable[[], Any]
    target_x: Optional[int] = None
    target_y: Optional[int] = None
    timeout_s: Optional[float] = None


@dataclass(frozen=True)
class BrowserScreenshotRef:
    """Pointer to one bracketed browser screenshot.

    Mirrors :class:`ultron.desktop.sequence.ScreenshotRef` but the
    source is the headless browser screenshot, not a monitor capture.
    """

    step: int
    when: str  # "before" / "after"
    width: int = 0
    height: int = 0
    byte_length: int = 0
    timestamp: float = 0.0
    bytes_discarded: bool = True
    error: Optional[str] = None


@dataclass(frozen=True)
class BrowserStepResult:
    """Outcome of one step in a browser sequence."""

    step_index: int
    description: str
    outcome: StepOutcome
    action_result: Any = None
    error: Optional[str] = None
    before: Optional[BrowserScreenshotRef] = None
    after: Optional[BrowserScreenshotRef] = None
    vlm_verdict: VlmVerdict = VlmVerdict.SKIPPED
    vlm_message: str = ""
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class BrowserSequenceResult:
    """Outcome of a full browser sequence run.

    Schema mirrors :class:`ultron.desktop.sequence.SequenceResult`:
    ``task / status / success / steps / screenshots / failed_at_step
    / error / elapsed_s``.
    """

    task: str
    status: SequenceStatus
    success: bool
    steps: tuple[BrowserStepResult, ...]
    screenshots: tuple[tuple[BrowserScreenshotRef, BrowserScreenshotRef], ...]
    failed_at_step: Optional[int] = None
    error: Optional[str] = None
    elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class BrowserSequenceRunner:
    """Run a list of browser steps with before/after screenshot
    bracketing.

    Args:
        tool: the :class:`BrowserUseTool` used for screenshot capture.
            ``None`` (or a tool whose binary is missing) degrades to
            empty :class:`BrowserScreenshotRef` entries -- steps still
            run, but with no visual bracket.
        vlm_describe: injected ``(png_bytes, prompt) -> str`` callable
            for after-frame verification. Wire from the existing
            click_preview / Moondream2 holder so the same VLM session
            is reused.
        bracket_screenshots: capture before/after frames per step.
        verify_with_vlm: route after-frames through the VLM.
        auto_pass_radius_px: anchor-radius for skipping redundant VLM
            calls on consecutive same-region steps.
        confirmation_keyword: VLM "success" token (default "yes").
        full_page: capture full scrollable page (vs viewport).
        clock_fn: time source for tests.
    """

    def __init__(
        self,
        *,
        tool: Optional[Any] = None,
        vlm_describe: Optional[Callable[[bytes, str], str]] = None,
        bracket_screenshots: bool = True,
        verify_with_vlm: bool = False,
        auto_pass_radius_px: int = SEQUENCE_AUTO_PASS_RADIUS_PX,
        confirmation_keyword: str = "yes",
        full_page: bool = False,
        clock_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self._tool = tool
        self._vlm_describe = vlm_describe
        self._bracket = bool(bracket_screenshots)
        self._verify = bool(verify_with_vlm)
        self._auto_pass = max(0, int(auto_pass_radius_px))
        self._keyword = str(confirmation_keyword).lower().strip() or "yes"
        self._full_page = bool(full_page)
        self._clock = clock_fn if callable(clock_fn) else time.time

    def _resolve_tool(self) -> Optional[Any]:
        if self._tool is not None:
            return self._tool
        try:
            from ultron.desktop.browser_use import get_browser_use_tool

            return get_browser_use_tool()
        except Exception as exc:  # noqa: BLE001 -- defensive
            logger.debug("BrowserSequenceRunner: no tool available: %s", exc)
            return None

    def _capture(
        self, step_index: int, when: str
    ) -> tuple[BrowserScreenshotRef, Optional[bytes]]:
        """Capture a browser frame for the bracket via
        ``tool.screenshot()`` base64 mode."""
        if not self._bracket:
            return (
                BrowserScreenshotRef(
                    step=step_index, when=when, bytes_discarded=False
                ),
                None,
            )
        tool = self._resolve_tool()
        if tool is None:
            return (
                BrowserScreenshotRef(
                    step=step_index, when=when,
                    error="no browser tool wired", bytes_discarded=False,
                ),
                None,
            )
        try:
            shot = tool.screenshot(
                full_page=self._full_page,
                user_text=f"sequence step {step_index} {when}",
            )
        except Exception as exc:  # noqa: BLE001 -- defensive
            logger.debug(
                "BrowserSequenceRunner capture %s failed at step %d: %s",
                when, step_index, exc,
            )
            return (
                BrowserScreenshotRef(
                    step=step_index, when=when,
                    error=f"screenshot exception: {exc}",
                    bytes_discarded=False,
                ),
                None,
            )
        if shot is None or not getattr(shot, "success", False):
            err = getattr(shot, "error", None) or "screenshot failed"
            return (
                BrowserScreenshotRef(
                    step=step_index, when=when, error=err,
                    bytes_discarded=False,
                ),
                None,
            )
        png = getattr(shot, "image_bytes", None)
        ref = BrowserScreenshotRef(
            step=step_index,
            when=when,
            byte_length=len(png) if png else 0,
            timestamp=self._clock(),
            bytes_discarded=True,
        )
        return ref, png

    def _within_auto_pass(
        self,
        step: BrowserSequenceStep,
        last_confirmed: Optional[tuple[int, int]],
    ) -> bool:
        if last_confirmed is None or self._auto_pass <= 0:
            return False
        if step.target_x is None or step.target_y is None:
            return False
        dx = int(step.target_x) - last_confirmed[0]
        dy = int(step.target_y) - last_confirmed[1]
        return (dx * dx + dy * dy) <= (self._auto_pass * self._auto_pass)

    def _vlm_verdict(
        self,
        *,
        step: BrowserSequenceStep,
        after_png: Optional[bytes],
    ) -> tuple[VlmVerdict, str]:
        if not self._verify or self._vlm_describe is None:
            return VlmVerdict.SKIPPED, ""
        if after_png is None:
            return VlmVerdict.DEGRADED, "no after-frame to verify"
        prompt = (
            f"Did this browser step succeed: '{step.description}'? "
            f"Reply '{self._keyword}' if yes, otherwise describe what "
            "is wrong in one sentence."
        )
        try:
            response = self._vlm_describe(after_png, prompt)
        except Exception as exc:  # noqa: BLE001 -- defensive
            logger.debug("VLM verify raised at step %s: %s", step.description, exc)
            return VlmVerdict.DEGRADED, f"vlm exception: {exc}"
        text = (response or "").strip().lower()
        if not text:
            return VlmVerdict.DEGRADED, "vlm returned empty response"
        if self._keyword in text.split() or text.startswith(self._keyword):
            return VlmVerdict.SUCCEEDED, response
        return VlmVerdict.FAILED, response

    def _coerce_outcome(
        self, result: Any
    ) -> tuple[StepOutcome, Optional[str]]:
        if hasattr(result, "success"):
            if result.success:
                return StepOutcome.OK, None
            return (
                StepOutcome.FAILED,
                getattr(result, "error", None) or "action returned failure",
            )
        if result is None or result is False:
            return StepOutcome.FAILED, "action returned falsy"
        return StepOutcome.OK, None

    def run(
        self,
        task: str,
        steps: Sequence[BrowserSequenceStep],
    ) -> BrowserSequenceResult:
        """Execute ``steps`` in order with before/after bracketing.

        Fail-fast: the first failing step aborts the run. Returns the
        prefix of executed steps + their screenshot pairs.
        """
        start = self._clock()
        executed: list[BrowserStepResult] = []
        pairs: list[tuple[BrowserScreenshotRef, BrowserScreenshotRef]] = []
        last_confirmed: Optional[tuple[int, int]] = None

        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, BrowserSequenceStep):
                return BrowserSequenceResult(
                    task=task,
                    status=SequenceStatus.ERROR,
                    success=False,
                    steps=tuple(executed),
                    screenshots=tuple(pairs),
                    failed_at_step=idx,
                    error=(
                        f"step {idx}: not a BrowserSequenceStep "
                        f"({type(step).__name__})"
                    ),
                    elapsed_s=self._clock() - start,
                )
            step_start = self._clock()
            before_ref, _ = self._capture(idx, "before")
            try:
                action_result = step.action()
                outcome, action_error = self._coerce_outcome(action_result)
            except Exception as exc:  # noqa: BLE001 -- defensive
                after_ref, _ = self._capture(idx, "after")
                executed.append(
                    BrowserStepResult(
                        step_index=idx,
                        description=step.description,
                        outcome=StepOutcome.EXCEPTION,
                        error=str(exc)[:300],
                        before=before_ref,
                        after=after_ref,
                        elapsed_s=self._clock() - step_start,
                    )
                )
                pairs.append((before_ref, after_ref))
                return BrowserSequenceResult(
                    task=task,
                    status=SequenceStatus.FAILED,
                    success=False,
                    steps=tuple(executed),
                    screenshots=tuple(pairs),
                    failed_at_step=idx,
                    error=str(exc)[:300],
                    elapsed_s=self._clock() - start,
                )

            after_ref, after_png = self._capture(idx, "after")
            if self._within_auto_pass(step, last_confirmed):
                verdict, vlm_msg = VlmVerdict.AUTO_PASSED, ""
            else:
                verdict, vlm_msg = self._vlm_verdict(
                    step=step, after_png=after_png
                )
            if outcome is StepOutcome.OK and verdict is VlmVerdict.FAILED:
                outcome = StepOutcome.FAILED
                action_error = action_error or f"vlm rejected: {vlm_msg[:160]}"

            executed.append(
                BrowserStepResult(
                    step_index=idx,
                    description=step.description,
                    outcome=outcome,
                    action_result=action_result,
                    error=action_error,
                    before=before_ref,
                    after=after_ref,
                    vlm_verdict=verdict,
                    vlm_message=vlm_msg,
                    elapsed_s=self._clock() - step_start,
                )
            )
            pairs.append((before_ref, after_ref))

            if outcome is not StepOutcome.OK:
                return BrowserSequenceResult(
                    task=task,
                    status=SequenceStatus.FAILED,
                    success=False,
                    steps=tuple(executed),
                    screenshots=tuple(pairs),
                    failed_at_step=idx,
                    error=action_error,
                    elapsed_s=self._clock() - start,
                )

            if (
                verdict in (VlmVerdict.SUCCEEDED, VlmVerdict.AUTO_PASSED)
                and step.target_x is not None
                and step.target_y is not None
            ):
                last_confirmed = (int(step.target_x), int(step.target_y))

        return BrowserSequenceResult(
            task=task,
            status=SequenceStatus.COMPLETED,
            success=True,
            steps=tuple(executed),
            screenshots=tuple(pairs),
            failed_at_step=None,
            error=None,
            elapsed_s=self._clock() - start,
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_runner_singleton: Optional[BrowserSequenceRunner] = None


def get_browser_sequence_runner() -> BrowserSequenceRunner:
    """Module-level singleton accessor."""
    global _runner_singleton
    if _runner_singleton is None:
        _runner_singleton = BrowserSequenceRunner()
    return _runner_singleton


def set_browser_sequence_runner(
    runner: Optional[BrowserSequenceRunner],
) -> None:
    """Test / orchestrator hook -- swap the singleton."""
    global _runner_singleton
    _runner_singleton = runner


__all__ = [
    "BrowserScreenshotRef",
    "BrowserSequenceResult",
    "BrowserSequenceRunner",
    "BrowserSequenceStep",
    "BrowserStepResult",
    "get_browser_sequence_runner",
    "set_browser_sequence_runner",
]
