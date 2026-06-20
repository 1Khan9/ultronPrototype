"""Ultron 1.0 M5b -- always-listening intent-gate WIRING.

The 4-class gate itself is covered by ``tests/audio/test_intent_gate.py``. These tests pin the
ORCHESTRATOR wiring: ``Orchestrator._classify_always_listening`` delegates to ``classify_scenario``,
escalates the undecided band via ``self.llm`` (``resolve_with_llm``), fail-opens to IGNORE, and the
``run()`` always-listening branch + perpetual-arm (wake bypass) + the DEFAULT-OFF config field all
stay in place. Hermetic: strict-matcher / addressing-rule cases need no embedder sidecar.
"""
from __future__ import annotations

import inspect

import pytest

from kenning.audio.intent_gate import Scenario
from kenning.pipeline.orchestrator import Orchestrator


def _bare(llm=None):
    """A bare Orchestrator (no __init__) with just the attrs the helper reads."""
    o = Orchestrator.__new__(Orchestrator)
    o.llm = llm
    return o


class _StubLLM:
    """generate_stream returns one canned token (mirrors test_intent_gate)."""

    def __init__(self, reply: str):
        self._reply = reply
        self.calls = 0

    def generate_stream(self, *a, **k):
        self.calls += 1
        return [self._reply]


_UNDECIDED = "the rotations feel pretty clean this map"  # no relay/command/addressing signal


# --- helper: scenario mapping (decided cheaply, no 8B escalation) ---------------------

def test_helper_relay():
    o = _bare(llm=_StubLLM("PRIVATE"))
    v = o._classify_always_listening("tell my team to rush B", 999.0)
    assert v.scenario is Scenario.RELAY_TO_TEAM
    assert o.llm.calls == 0  # strict matcher decided it; the 8B was never consulted


def test_helper_command_local():
    o = _bare(llm=_StubLLM("PRIVATE"))
    v = o._classify_always_listening("flavor off", 999.0)
    assert v.scenario is Scenario.COMMAND_LOCAL
    assert o.llm.calls == 0


def test_helper_private_with_wake():
    o = _bare(llm=_StubLLM("PRIVATE"))
    v = o._classify_always_listening("ultron, what map is this", 999.0)
    assert v.scenario is Scenario.PRIVATE_REPLY
    assert o.llm.calls == 0  # leading wake word is decisive on its own


# Sidecar-INDEPENDENT IGNORE cases: these reach the addressing NO-rules (the
# relay-signal layer returns None for them in both lexical-only and embedder
# modes), so the wiring test never depends on the embedder sidecar being up.
# (The relay-intent gate's accuracy on borderline phrases is exercised in
# tests/audio/test_intent_gate.py, not here -- that is out of M5b's wiring scope.)
@pytest.mark.parametrize("text", [
    "oh shit",                            # interjection -> confident NO
    "I'm talking to him right now",       # third-party narrative -> confident NO
])
def test_helper_ignore_addressing_no(text):
    o = _bare(llm=_StubLLM("PRIVATE"))
    v = o._classify_always_listening(text, 999.0)
    assert v.scenario is Scenario.IGNORE
    assert o.llm.calls == 0  # a confident addressing-NO needs no escalation


# --- helper: undecided band escalates via self.llm (resolve_with_llm) -----------------

def test_helper_undecided_escalates_private():
    o = _bare(llm=_StubLLM("PRIVATE"))
    v = o._classify_always_listening(_UNDECIDED, 999.0)
    assert v.scenario is Scenario.PRIVATE_REPLY
    assert o.llm.calls == 1  # the 8B band escalation fired


def test_helper_undecided_escalates_ignore_failclosed():
    o = _bare(llm=_StubLLM("uhh maybe not sure"))
    v = o._classify_always_listening(_UNDECIDED, 999.0)
    assert v.scenario is Scenario.IGNORE  # non-PRIVATE token -> fail closed
    assert o.llm.calls == 1


def test_helper_undecided_llm_none_stays_ignore():
    o = _bare(llm=None)  # lean / bare boot: no LLM available
    v = o._classify_always_listening(_UNDECIDED, 999.0)
    assert v.scenario is Scenario.IGNORE  # resolve_with_llm no-ops when llm is None


# --- helper: fail-open to IGNORE on any internal error --------------------------------

def test_helper_fail_open_on_error(monkeypatch):
    import kenning.audio.intent_gate as ig

    def _boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ig, "classify_scenario", _boom)
    o = _bare()
    v = o._classify_always_listening("tell my team to rush B", 999.0)
    assert v.scenario is Scenario.IGNORE
    assert "gate error" in v.reason


# --- config: always-listening is DEFAULT OFF (BR-11.2) --------------------------------

def test_config_default_off():
    from kenning.config import AddressingConfig
    assert AddressingConfig().always_listening is False


def test_config_yaml_default_off():
    from kenning.config import load_config
    assert load_config().addressing.always_listening is False


# --- run-loop wiring (source pins; driving run() needs live audio) --------------------

def test_run_loop_wires_always_listening():
    src = inspect.getsource(Orchestrator.run)
    assert "_always_listening = bool(getattr(_addr_cfg" in src        # captured once
    assert "if _always_listening and follow_up_until is None:" in src  # perpetual-arm / wake bypass
    assert "_addr_cfg.follow_up_enabled or _always_listening" in src   # follow-up branch admits it
    assert "elif _always_listening:" in src                            # the 4-class gate branch
    assert "_classify_always_listening(user_text, seconds_since)" in src
    assert "self._last_scenario = sv.scenario" in src                  # stashed for M6b
    assert "KENNING_ALWAYS_LISTENING" in src                           # env override enabler


def test_flag_off_path_keeps_binary_classifier():
    # The OFF path still calls the binary AddressingClassifier (byte-identical behaviour).
    src = inspect.getsource(Orchestrator.run)
    assert "self.addressing.classify(" in src
