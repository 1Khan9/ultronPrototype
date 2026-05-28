"""Tests for :mod:`ultron.agent_loop.base` (catalog 11 meta-pattern).

A single configurable concrete subclass (:class:`_ScriptedLoop`) drives
every terminal path: completion, max-steps exhaustion, loop detection,
action failure, verification failure, and fail-open on a phase
exception.
"""

from __future__ import annotations

import pytest

from ultron.agent_loop.base import (
    AgentLoop,
    AgentLoopError,
    LoopResult,
    LoopStatus,
    StepOutcome,
    StepRecord,
)


class _ScriptedLoop(AgentLoop):
    """Deterministic loop driven by injected scripts.

    * ``plan`` yields successive items from ``plan_script`` (``None``
      stops).
    * ``act`` yields successive items from ``act_script`` (default
      ``True``).
    * ``verify`` yields successive items from ``verify_script``
      (default ``True``).
    * ``is_done`` returns True once ``len(history) >= done_at_step``.
    * ``raise_in`` makes the named phase raise.
    * ``signature_const`` (when set) forces a constant action signature
      to exercise loop detection regardless of action identity.
    """

    def __init__(
        self,
        *,
        plan_script,
        act_script=None,
        verify_script=None,
        done_at_step=None,
        raise_in=None,
        signature_const=None,
        **kw,
    ):
        super().__init__(**kw)
        self._plan_script = list(plan_script)
        self._act_script = list(act_script) if act_script is not None else None
        self._verify_script = (
            list(verify_script) if verify_script is not None else None
        )
        self._done_at_step = done_at_step
        self._raise_in = raise_in
        self._signature_const = signature_const
        self._plan_i = 0
        self._act_i = 0
        self._verify_i = 0
        self.observe_calls = 0
        self.act_calls = 0

    def observe(self):
        self.observe_calls += 1
        if self._raise_in == "observe":
            raise RuntimeError("observe boom")
        return {"obs": self.observe_calls}

    def plan(self, observation, history):
        if self._raise_in == "plan":
            raise RuntimeError("plan boom")
        if self._plan_i >= len(self._plan_script):
            return None
        action = self._plan_script[self._plan_i]
        self._plan_i += 1
        return action

    def act(self, action):
        self.act_calls += 1
        if self._raise_in == "act":
            raise RuntimeError("act boom")
        if self._act_script is None:
            return True
        result = self._act_script[self._act_i] if self._act_i < len(self._act_script) else True
        self._act_i += 1
        return result

    def verify(self, observation, action, result):
        if self._verify_script is None:
            return True
        v = self._verify_script[self._verify_i] if self._verify_i < len(self._verify_script) else True
        self._verify_i += 1
        return v

    def is_done(self, result, history):
        if self._done_at_step is None:
            return False
        return len(history) >= self._done_at_step

    def action_signature(self, action):
        if self._signature_const is not None:
            return self._signature_const
        return super().action_signature(action)


# --- construction guards --------------------------------------------------


def test_max_steps_must_be_positive():
    with pytest.raises(AgentLoopError):
        _ScriptedLoop(plan_script=[], max_steps=0)


def test_loop_repeat_cap_must_be_positive():
    with pytest.raises(AgentLoopError):
        _ScriptedLoop(plan_script=[], loop_repeat_cap=0)


def test_max_steps_property():
    loop = _ScriptedLoop(plan_script=[], max_steps=7)
    assert loop.max_steps == 7


# --- completion paths -----------------------------------------------------


def test_completes_when_plan_returns_none_immediately():
    loop = _ScriptedLoop(plan_script=[])
    result = loop.run(goal="nothing to do")
    assert isinstance(result, LoopResult)
    assert result.status is LoopStatus.COMPLETED
    assert result.success is True
    assert result.steps == ()
    assert result.goal == "nothing to do"


def test_completes_when_plan_exhausts():
    loop = _ScriptedLoop(plan_script=["a", "b"])
    result = loop.run()
    assert result.status is LoopStatus.COMPLETED
    assert result.success is True
    assert len(result.steps) == 2
    assert all(s.outcome is StepOutcome.OK for s in result.steps)


def test_completes_via_is_done():
    loop = _ScriptedLoop(plan_script=["a", "b", "c", "d"], done_at_step=2)
    result = loop.run()
    assert result.status is LoopStatus.COMPLETED
    assert len(result.steps) == 2


# --- bounded autonomy -----------------------------------------------------


def test_max_steps_exhausted():
    # Distinct actions so loop detection does not trip first.
    loop = _ScriptedLoop(plan_script=["a", "b", "c", "d", "e"], max_steps=3)
    result = loop.run()
    assert result.status is LoopStatus.MAX_STEPS_EXHAUSTED
    assert result.success is False
    assert result.final_step == 3
    assert len(result.steps) == 3
    assert "max_steps=3" in result.error


def test_loop_detected_on_repeated_signature():
    loop = _ScriptedLoop(
        plan_script=["same"] * 10, loop_repeat_cap=2, max_steps=20
    )
    result = loop.run()
    assert result.status is LoopStatus.LOOP_DETECTED
    assert result.success is False
    assert result.steps[-1].outcome is StepOutcome.LOOP_DETECTED
    # 2 OK steps executed before the 3rd repeat tripped the cap.
    assert loop.act_calls == 2


def test_loop_detection_via_constant_signature_override():
    # Distinct actions but a constant signature -> still detected.
    loop = _ScriptedLoop(
        plan_script=["a", "b", "c", "d"],
        signature_const="X",
        loop_repeat_cap=2,
        max_steps=20,
    )
    result = loop.run()
    assert result.status is LoopStatus.LOOP_DETECTED


# --- failure paths --------------------------------------------------------


def test_action_failure_aborts():
    loop = _ScriptedLoop(plan_script=["a", "b", "c"], act_script=[True, False])
    result = loop.run()
    assert result.status is LoopStatus.ABORTED
    assert result.steps[-1].outcome is StepOutcome.FAILED
    assert len(result.steps) == 2


def test_verify_failure_aborts():
    loop = _ScriptedLoop(
        plan_script=["a", "b", "c"],
        act_script=[True, True],
        verify_script=[True, False],
    )
    result = loop.run()
    assert result.status is LoopStatus.ABORTED
    assert result.steps[-1].outcome is StepOutcome.VERIFY_FAILED


@pytest.mark.parametrize("phase", ["observe", "plan", "act"])
def test_phase_exception_is_caught_as_error(phase):
    loop = _ScriptedLoop(plan_script=["a", "b"], raise_in=phase)
    result = loop.run()
    assert result.status is LoopStatus.ERROR
    assert result.success is False
    assert f"{phase} boom" in result.error
    # The exception never propagates out of run().


# --- observability --------------------------------------------------------


def test_on_step_callback_fires_per_step():
    seen: list[StepRecord] = []
    loop = _ScriptedLoop(plan_script=["a", "b"], on_step=seen.append)
    loop.run()
    assert len(seen) == 2
    assert [r.index for r in seen] == [1, 2]


def test_on_step_callback_failure_does_not_break_loop():
    def boom(_record):
        raise RuntimeError("callback boom")

    loop = _ScriptedLoop(plan_script=["a", "b"], on_step=boom)
    result = loop.run()
    # Loop completed despite the callback raising on every step.
    assert result.status is LoopStatus.COMPLETED
    assert len(result.steps) == 2


def test_step_records_carry_summaries():
    loop = _ScriptedLoop(plan_script=["click #submit"])
    result = loop.run()
    assert len(result.steps) == 1
    rec = result.steps[0]
    assert rec.index == 1
    assert "click #submit" in rec.action_summary
    assert rec.observation_summary  # non-empty


def test_default_action_succeeded_is_truthiness():
    # An action whose result is None counts as a falsy -> failed step.
    loop = _ScriptedLoop(plan_script=["a", "b"], act_script=[None])
    result = loop.run()
    assert result.status is LoopStatus.ABORTED
    assert result.steps[0].outcome is StepOutcome.FAILED
