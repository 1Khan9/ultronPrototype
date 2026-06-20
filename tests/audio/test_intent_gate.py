"""Tests for the Ultron 1.0 always-listening 3-way (4-class) intent gate (src/kenning/audio/intent_gate.py).

Hermetic: uses relay cases caught by the strict matcher / complete-tactical-callout (no embedder
sidecar needed) and name-agnostic addressing NO-rules. Validates the cost-asymmetric, fail-closed
classification + the ASR pre-reject + the 8B band escalation (with a stub llm).
"""
import pytest

from kenning.audio import intent_gate as ig
from kenning.audio.intent_gate import Scenario


@pytest.mark.parametrize("text", [
    "tell my team to rush B",
    "sova hit 84 on A main",
    "two on A site one rotating",
])
def test_relay_to_team(text):
    v = ig.classify_scenario(text)
    assert v.scenario is Scenario.RELAY_TO_TEAM, (text, v)


@pytest.mark.parametrize("text", [
    "flavor off",
    "no flavor",
    "thinking mode on",
    "switch to the GPU",
    "stop",
    "ultron stop",
])
def test_command_local(text):
    v = ig.classify_scenario(text)
    assert v.scenario is Scenario.COMMAND_LOCAL, (text, v)


def test_private_reply_with_wake():
    v = ig.classify_scenario("ultron, what map is this")
    assert v.scenario is Scenario.PRIVATE_REPLY


def test_private_reply_factual_question_no_wake():
    # A clear factual question addressed to the assistant (addressing rule YES >= tau).
    v = ig.classify_scenario("what time is it right now")
    assert v.scenario is Scenario.PRIVATE_REPLY


@pytest.mark.parametrize("text", [
    "hey mom how are you doing today",   # phone opener -> NO
    "oh shit",                            # interjection -> NO
    "I'm talking to him right now",       # third-party narrative -> NO
])
def test_ignore_addressing_no(text):
    v = ig.classify_scenario(text)
    assert v.scenario is Scenario.IGNORE, (text, v)


def test_asr_pre_reject_no_speech():
    v = ig.classify_scenario("let's go team", no_speech_prob=0.9)
    assert v.scenario is Scenario.IGNORE and "no_speech" in v.reason


def test_asr_pre_reject_low_logprob():
    v = ig.classify_scenario("garbled audio here", avg_logprob=-2.5)
    assert v.scenario is Scenario.IGNORE and "avg_logprob" in v.reason


def test_undecided_is_failclosed_ignore_with_llm_flag():
    # An ambiguous statement with no relay/command/addressing signal -> fail-closed IGNORE, needs_llm.
    v = ig.classify_scenario("the rotations feel pretty clean this map")
    assert v.scenario is Scenario.IGNORE
    assert v.needs_llm is True


def test_empty():
    assert ig.classify_scenario("").scenario is Scenario.IGNORE
    assert ig.classify_scenario("   ").scenario is Scenario.IGNORE


class _StubLLM:
    def __init__(self, reply):
        self._reply = reply

    def generate_stream(self, *a, **k):
        return [self._reply]


def test_resolve_with_llm_private():
    v = ig.classify_scenario("the rotations feel pretty clean this map")  # needs_llm
    out = ig.resolve_with_llm(v, "the rotations feel pretty clean this map", _StubLLM("PRIVATE"))
    assert out.scenario is Scenario.PRIVATE_REPLY


def test_resolve_with_llm_failclosed_on_garbage():
    v = ig.classify_scenario("the rotations feel pretty clean this map")
    out = ig.resolve_with_llm(v, "...", _StubLLM("uhh I think maybe"))
    assert out.scenario is Scenario.IGNORE  # non-PRIVATE token -> fail closed


def test_resolve_with_llm_noop_when_not_needed():
    v = ig.classify_scenario("tell my team to rush B")   # RELAY, needs_llm False
    out = ig.resolve_with_llm(v, "tell my team to rush B", _StubLLM("PRIVATE"))
    assert out.scenario is Scenario.RELAY_TO_TEAM        # unchanged
