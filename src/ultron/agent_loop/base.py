"""Unified, safety-instrumented agent-loop base class.

Catalog 11 (clawhub-browser-agent) meta-pattern -- clean-room synthesis.

clawhub-browser-agent does NOT itself implement an agent loop (it is a
thin CDP primitives wrapper). The catalog's genuine intellectual
contribution is the observation that ultron already repeats an
agent-loop shape in several independent places --
:class:`ultron.desktop.browser_sequence.BrowserSequenceRunner`,
:class:`ultron.desktop.sequence.DesktopSequenceRunner`,
:class:`ultron.coding.runner.CodingTaskRunner`, and the gaming-engage
state machine -- each with its own ad-hoc step memory, termination
condition, and failure handling, with no shared safety floor.

This module factors that shape into ONE base class that captures the
invariants every autonomous loop should have:

* **``max_steps`` cap** -- the load-bearing safety property. No loop
  built on this base can take more than ``max_steps`` autonomous steps
  without returning control. This is the prerequisite the later
  capability-evolver / self-improving-agent catalogs (13-14) require: a
  self-modifying loop with no step cap has unbounded autonomy, which is
  the K-category concern. Establishing the cap now means those
  techniques arrive into a bounded, instrumented framework rather than
  a vacuum.
* **Step memory** -- every step is recorded (:class:`StepRecord`) so a
  loop can reason over its own history and an audit can reconstruct
  exactly what happened.
* **Built-in loop detection** -- an action whose canonical signature
  repeats more than ``loop_repeat_cap`` consecutive times halts the
  loop (the same "stuck doing the same thing" guard the cline / OpenClaw
  loop detectors provide, expressed at the base-class level).
* **Per-step verification hook** -- subclasses can confirm an action
  actually achieved its effect (the before/after VLM bracket the
  sequence runners already use) and abort on a failed verification.
* **Fail-open execution** -- an exception raised by any phase
  (observe / plan / act / verify / is_done) is caught, recorded, and
  terminates the loop with :attr:`LoopStatus.ERROR`. The loop NEVER
  propagates an exception to the orchestrator.

The base is **purely additive**: it does not import or modify any
existing runner. New multi-step flows subclass it to inherit the
safety floor for free; existing runners can migrate incrementally in a
future pass (deliberately out of scope here -- rewriting load-bearing
runners would risk regressing shipped behaviour).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional, Sequence

from ultron.utils.logging import get_logger

logger = get_logger("agent_loop.base")


# Default hard cap on autonomous steps. Browser / desktop loops are
# short; coding loops naturally iterate more (a subclass raises it).
DEFAULT_MAX_STEPS: int = 20

# Default consecutive-repeat cap before the built-in loop detector
# halts. Matches the cline LoopDetector hard threshold.
DEFAULT_LOOP_REPEAT_CAP: int = 5

# Cap on the per-field summary strings stored in a StepRecord so a
# verbose observation / action can never bloat the audit log.
_SUMMARY_CAP: int = 200


class LoopStatus(str, Enum):
    """Terminal status of an :meth:`AgentLoop.run`."""

    COMPLETED = "completed"  # plan signalled done OR is_done() returned True
    MAX_STEPS_EXHAUSTED = "max_steps_exhausted"
    LOOP_DETECTED = "loop_detected"
    ABORTED = "aborted"  # an action failed or verification failed
    ERROR = "error"  # a phase raised; loop caught it


class StepOutcome(str, Enum):
    """Outcome of a single executed step."""

    OK = "ok"
    FAILED = "failed"  # the action returned falsy
    VERIFY_FAILED = "verify_failed"  # action ran but verification rejected it
    LOOP_DETECTED = "loop_detected"  # action's signature repeated past the cap


class AgentLoopError(RuntimeError):
    """Raised only for programmer error at construction (e.g. a
    non-positive ``max_steps``). Runtime failures never raise -- they
    surface as :attr:`LoopStatus.ERROR`."""


@dataclass(frozen=True)
class StepRecord:
    """Immutable record of one loop step.

    Attributes:
        index: 1-based step number.
        observation_summary: capped string summary of the observation.
        action_summary: capped string summary of the planned action.
        outcome: :class:`StepOutcome`.
        error: short failure reason, or empty on success.
        elapsed_s: wall-clock duration of the step.
    """

    index: int
    observation_summary: str
    action_summary: str
    outcome: StepOutcome
    error: str = ""
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class LoopResult:
    """Immutable outcome of an :meth:`AgentLoop.run`.

    Attributes:
        goal: the goal string the loop was driven with.
        status: terminal :class:`LoopStatus`.
        success: convenience -- True iff ``status`` is COMPLETED.
        steps: tuple of every :class:`StepRecord` produced.
        final_step: the last step index reached (0 if none ran).
        error: terminal failure reason, or empty.
        elapsed_s: total wall-clock duration.
    """

    goal: str
    status: LoopStatus
    success: bool
    steps: tuple[StepRecord, ...] = ()
    final_step: int = 0
    error: str = ""
    elapsed_s: float = 0.0


def _summarise(value: Any) -> str:
    """Render any value to a capped single-line summary for the record."""
    try:
        text = value if isinstance(value, str) else repr(value)
    except Exception:  # noqa: BLE001 -- a broken __repr__ must not break the loop
        text = "<unrepresentable>"
    text = " ".join(text.split())
    if len(text) > _SUMMARY_CAP:
        return text[: _SUMMARY_CAP - 1] + "…"
    return text


class AgentLoop(ABC):
    """Base class for a bounded, instrumented observe -> plan -> act ->
    verify loop.

    Minimal subclass contract: implement :meth:`plan` and :meth:`act`.
    Override :meth:`observe` / :meth:`verify` / :meth:`is_done` /
    :meth:`action_signature` / :meth:`action_succeeded` as needed.

    Args:
        max_steps: hard cap on autonomous steps. Must be positive.
        name: label for logs + the loop-detection signature space.
        loop_repeat_cap: consecutive identical action signatures that
            trip the built-in loop detector. Must be positive.
        on_step: optional callback invoked with each :class:`StepRecord`
            as it is produced (fail-open -- a raising callback is
            swallowed). Useful for live narration / bus events.
        clock: monotonic time source; injectable for tests.
    """

    def __init__(
        self,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        name: str = "agent_loop",
        loop_repeat_cap: int = DEFAULT_LOOP_REPEAT_CAP,
        on_step: Optional[Callable[[StepRecord], None]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_steps <= 0:
            raise AgentLoopError(f"max_steps must be positive, got {max_steps!r}")
        if loop_repeat_cap <= 0:
            raise AgentLoopError(
                f"loop_repeat_cap must be positive, got {loop_repeat_cap!r}"
            )
        self._max_steps = int(max_steps)
        self._name = name or "agent_loop"
        self._loop_repeat_cap = int(loop_repeat_cap)
        self._on_step = on_step
        self._clock = clock

    # -- subclass contract --------------------------------------------

    def observe(self) -> Any:
        """Capture the current environment state. Default: ``None``."""
        return None

    @abstractmethod
    def plan(self, observation: Any, history: Sequence[StepRecord]) -> Any:
        """Choose the next action from the observation + step history.

        Return ``None`` to signal the loop is done (nothing left to do);
        any other value is treated as an action to execute.
        """

    @abstractmethod
    def act(self, action: Any) -> Any:
        """Execute ``action``. The return value is passed to
        :meth:`action_succeeded` + :meth:`verify` + :meth:`is_done`."""

    def verify(self, observation: Any, action: Any, result: Any) -> bool:
        """Confirm the action achieved its intended effect. Default:
        ``True`` (no verification). Return ``False`` to abort the loop
        with :attr:`LoopStatus.ABORTED`."""
        return True

    def is_done(self, result: Any, history: Sequence[StepRecord]) -> bool:
        """Post-action completion predicate. Default: ``False``."""
        return False

    def action_succeeded(self, result: Any) -> bool:
        """Whether an action result counts as success. Default:
        ``bool(result)`` (a falsy result aborts, matching the existing
        sequence runners' fail-fast contract). Override when an action
        legitimately returns ``None`` on success."""
        return bool(result)

    def action_signature(self, action: Any) -> str:
        """Canonical signature used for loop detection. Default:
        ``repr(action)``. Override to normalise away noise fields (turn
        ids, timestamps) so genuine repeats are detected."""
        return _summarise(action)

    # -- driver --------------------------------------------------------

    def run(self, goal: str = "") -> LoopResult:
        """Drive the loop to a terminal state. Never raises.

        Returns a :class:`LoopResult` whose ``status`` records exactly
        how the loop ended.
        """
        started = self._clock()
        steps: list[StepRecord] = []
        recent_sig: Optional[str] = None
        recent_sig_count = 0
        status = LoopStatus.COMPLETED
        error = ""
        final_step = 0

        try:
            for step_index in range(1, self._max_steps + 1):
                final_step = step_index
                step_started = self._clock()

                observation = self.observe()
                action = self.plan(observation, tuple(steps))
                if action is None:
                    status = LoopStatus.COMPLETED
                    break

                # Built-in loop detection: same canonical signature
                # repeating past the cap halts the loop.
                signature = self.action_signature(action)
                if signature == recent_sig:
                    recent_sig_count += 1
                else:
                    recent_sig = signature
                    recent_sig_count = 1
                if recent_sig_count > self._loop_repeat_cap:
                    steps.append(
                        StepRecord(
                            index=step_index,
                            observation_summary=_summarise(observation),
                            action_summary=_summarise(action),
                            outcome=StepOutcome.LOOP_DETECTED,
                            error=(
                                f"action signature repeated "
                                f"{recent_sig_count} times (cap "
                                f"{self._loop_repeat_cap})"
                            ),
                            elapsed_s=self._clock() - step_started,
                        )
                    )
                    self._emit_step(steps[-1])
                    status = LoopStatus.LOOP_DETECTED
                    error = "loop detected: repeated action signature"
                    break

                result = self.act(action)
                ok = self.action_succeeded(result)
                verified = self.verify(observation, action, result) if ok else False

                if ok and verified:
                    outcome = StepOutcome.OK
                    step_error = ""
                elif ok and not verified:
                    outcome = StepOutcome.VERIFY_FAILED
                    step_error = "verification rejected the action result"
                else:
                    outcome = StepOutcome.FAILED
                    step_error = "action returned a falsy result"

                record = StepRecord(
                    index=step_index,
                    observation_summary=_summarise(observation),
                    action_summary=_summarise(action),
                    outcome=outcome,
                    error=step_error,
                    elapsed_s=self._clock() - step_started,
                )
                steps.append(record)
                self._emit_step(record)

                if outcome is StepOutcome.FAILED:
                    status = LoopStatus.ABORTED
                    error = "action failed"
                    break
                if outcome is StepOutcome.VERIFY_FAILED:
                    status = LoopStatus.ABORTED
                    error = "verification failed"
                    break
                if self.is_done(result, tuple(steps)):
                    status = LoopStatus.COMPLETED
                    break
            else:
                # for-else: ran every step without breaking -> exhausted.
                status = LoopStatus.MAX_STEPS_EXHAUSTED
                error = f"reached max_steps={self._max_steps} without completing"
        except BaseException as exc:  # noqa: BLE001 -- loop never propagates
            status = LoopStatus.ERROR
            error = f"{type(exc).__name__}: {exc}"
            logger.debug("agent_loop %r raised in a phase: %s", self._name, exc)

        return LoopResult(
            goal=goal,
            status=status,
            success=status is LoopStatus.COMPLETED,
            steps=tuple(steps),
            final_step=final_step,
            error=error,
            elapsed_s=self._clock() - started,
        )

    # -- internals -----------------------------------------------------

    def _emit_step(self, record: StepRecord) -> None:
        """Fire the on_step callback fail-open."""
        if self._on_step is None:
            return
        try:
            self._on_step(record)
        except Exception as exc:  # noqa: BLE001 -- broken callback must not break the loop
            logger.debug(
                "agent_loop %r on_step callback raised: %s", self._name, exc
            )

    @property
    def max_steps(self) -> int:
        return self._max_steps


__all__ = [
    "DEFAULT_LOOP_REPEAT_CAP",
    "DEFAULT_MAX_STEPS",
    "AgentLoop",
    "AgentLoopError",
    "LoopResult",
    "LoopStatus",
    "StepOutcome",
    "StepRecord",
]
