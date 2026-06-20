"""Ultron 1.0 M6b -- PRIVATE_REPLY (me-only) routing.

``Orchestrator._maybe_handle_private_reply``: when the always-listening gate (M5b)
classified the turn PRIVATE_REPLY AND ``KENNING_U1_LLM_ROUTE`` is on, answer via the
lean ``ultron_prompt.build_private_prompt`` on the DESKTOP channel (``self._speak`` --
never the team mic / no PTT) and short-circuit the generic ``_respond``. Strict no-op
otherwise (wake path / flag OFF / no llm / empty output) + fail-open.
"""
from __future__ import annotations

import inspect

import pytest

from kenning.audio import relay_speech as rs
from kenning.audio.intent_gate import Scenario
from kenning.audio.ultron_prompt import PRIVATE_SYSTEM
from kenning.pipeline.orchestrator import Orchestrator


@pytest.fixture
def route_on():
    prev = rs.u1_llm_route_enabled()
    rs.set_u1_llm_route_enabled(True)
    try:
        yield
    finally:
        rs.set_u1_llm_route_enabled(prev)


@pytest.fixture
def route_off():
    prev = rs.u1_llm_route_enabled()
    rs.set_u1_llm_route_enabled(False)
    try:
        yield
    finally:
        rs.set_u1_llm_route_enabled(prev)


class _StubLLM:
    def __init__(self, reply="Adapt or be deleted."):
        self.reply = reply
        self.last_system = None
        self.last_kwargs = None
        self.calls = 0

    def generate_stream(self, user_message, **kw):
        self.calls += 1
        self.last_system = kw.get("system_prompt")
        self.last_kwargs = kw
        return [self.reply]


def _orch(*, scenario, llm):
    """A bare Orchestrator with just the attrs/seams the M6b helper touches."""
    o = Orchestrator.__new__(Orchestrator)
    o.llm = llm
    o._last_scenario = scenario
    o._spoken = []
    o._speak = lambda t: o._spoken.append(t)        # capture desktop-channel speech
    o._trace_turn_flow = lambda **k: None           # no-op trace seam
    return o


def test_handles_private_reply_on_desktop(route_on):
    llm = _StubLLM("Adapt or be deleted.")
    o = _orch(scenario=Scenario.PRIVATE_REPLY, llm=llm)
    assert o._maybe_handle_private_reply("what's the play here") is True
    assert o._spoken == ["Adapt or be deleted."]      # spoke on the DESKTOP channel
    assert llm.calls == 1
    assert llm.last_system == PRIVATE_SYSTEM           # used the ME-ONLY prompt
    assert llm.last_kwargs.get("record_history") is False
    assert llm.last_kwargs.get("enable_thinking") is False
    assert llm.last_kwargs.get("suppress_memory_context") is True


@pytest.mark.parametrize("scenario", [
    None, Scenario.RELAY_TO_TEAM, Scenario.COMMAND_LOCAL, Scenario.IGNORE,
])
def test_noop_when_not_private(route_on, scenario):
    llm = _StubLLM()
    o = _orch(scenario=scenario, llm=llm)
    assert o._maybe_handle_private_reply("anything") is False
    assert o._spoken == [] and llm.calls == 0


def test_noop_when_route_off(route_off):
    llm = _StubLLM()
    o = _orch(scenario=Scenario.PRIVATE_REPLY, llm=llm)
    assert o._maybe_handle_private_reply("hello") is False  # flag OFF -> _respond handles it
    assert llm.calls == 0


def test_noop_when_no_llm(route_on):
    o = _orch(scenario=Scenario.PRIVATE_REPLY, llm=None)
    assert o._maybe_handle_private_reply("hello") is False


def test_empty_output_falls_through(route_on):
    llm = _StubLLM("")          # empty / think-only output
    o = _orch(scenario=Scenario.PRIVATE_REPLY, llm=llm)
    assert o._maybe_handle_private_reply("hello") is False
    assert o._spoken == []      # never speaks an empty line; _respond takes over


def test_fail_open_on_llm_error(route_on):
    class _BoomLLM:
        def generate_stream(self, *a, **k):
            raise RuntimeError("boom")

    o = _orch(scenario=Scenario.PRIVATE_REPLY, llm=_BoomLLM())
    assert o._maybe_handle_private_reply("hello") is False  # error -> _respond still runs


# --- run-loop wiring (source pin) -----------------------------------------------------

def test_run_loop_wires_private_reply():
    src = inspect.getsource(Orchestrator.run)
    assert "if self._maybe_handle_private_reply(user_text):" in src   # intercept before _respond
    assert 'via="private_reply"' in src
