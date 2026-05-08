"""IntentDisambiguator tests.

The disambiguator asks the LLM CODING / AUTOMATION / HYBRID / UNCLEAR
and returns a parsed verdict + optional clarifying question.
"""

from __future__ import annotations

import pytest

from ultron.openclaw_routing.disambiguator import (
    DisambiguationResult,
    IntentDisambiguator,
)
from ultron.openclaw_routing.intents import RoutingIntentKind


class _StubLLM:
    def __init__(self, response: str = ""):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _run(coro):
    import asyncio
    return asyncio.run(coro)


@pytest.mark.parametrize("verdict_word,expected_kind", [
    ("CODING", RoutingIntentKind.CODE_TASK),
    ("AUTOMATION", RoutingIntentKind.CONVERSATIONAL),  # falls through
    ("HYBRID", RoutingIntentKind.HYBRID_TASK),
])
def test_clean_verdicts_parse(verdict_word, expected_kind):
    d = IntentDisambiguator(_StubLLM(response=verdict_word))
    result = _run(d.disambiguate("do something with this file"))
    assert isinstance(result, DisambiguationResult)
    assert result.kind == expected_kind
    assert result.raw_verdict == verdict_word


def test_unclear_with_question():
    response = (
        "UNCLEAR\n"
        "Did you want me to write code, or to control an existing app?"
    )
    d = IntentDisambiguator(_StubLLM(response=response))
    result = _run(d.disambiguate("make me a tool for this"))
    assert result.kind is None
    assert result.clarification_question == (
        "Did you want me to write code, or to control an existing app?"
    )


def test_unclear_without_question_uses_default():
    """When the model says UNCLEAR but doesn't supply a question, the
    disambiguator falls back to a generic clarification."""
    d = IntentDisambiguator(_StubLLM(response="UNCLEAR"))
    result = _run(d.disambiguate("some ambiguous utterance"))
    assert result.kind is None
    assert result.clarification_question is not None
    assert "coding task" in result.clarification_question.lower()


def test_thinking_block_stripped_before_parse():
    response = "<think>let me think</think>\nCODING"
    d = IntentDisambiguator(_StubLLM(response=response))
    result = _run(d.disambiguate("write a flask app"))
    assert result.kind == RoutingIntentKind.CODE_TASK


def test_garbage_response_falls_back_to_unclear():
    d = IntentDisambiguator(_StubLLM(response="lkasjdflkjasdf"))
    result = _run(d.disambiguate("anything"))
    assert result.kind is None
    assert result.clarification_question is not None


def test_empty_response_falls_back_to_unclear():
    d = IntentDisambiguator(_StubLLM(response=""))
    result = _run(d.disambiguate("anything"))
    assert result.kind is None


def test_llm_exception_falls_back_to_unclear():
    class _ThrowingLLM:
        def generate(self, prompt: str) -> str:
            raise RuntimeError("LLM crashed")
    d = IntentDisambiguator(_ThrowingLLM())
    result = _run(d.disambiguate("anything"))
    assert result.kind is None


def test_disambiguator_disabled_in_config_short_circuits(monkeypatch):
    """When config.routing.llm_disambiguation_enabled is False, the
    disambiguator returns UNCLEAR without calling the LLM."""
    llm = _StubLLM(response="CODING")
    from ultron.config import get_config
    cfg = get_config()
    monkeypatch.setattr(cfg.routing, "llm_disambiguation_enabled", False)
    d = IntentDisambiguator(llm)
    result = _run(d.disambiguate("anything"))
    assert result.kind is None
    assert len(llm.prompts) == 0  # LLM never called


# ---------------------------------------------------------------------------
# Specific ambiguous test cases — 15 utterances per the spec.
# We don't actually run an LLM here; we feed a stub response per case.
# Real LLM correctness lives in the live e2e suite.
# ---------------------------------------------------------------------------


_AMBIGUOUS_CASES = [
    ("do something with this file", "UNCLEAR"),
    ("make me a tool for this", "UNCLEAR"),
    ("handle this for me", "UNCLEAR"),
    ("can you set that up", "UNCLEAR"),
    ("script the whole thing", "CODING"),
    ("automate this task", "AUTOMATION"),
    ("write something to grab the data", "HYBRID"),
    ("get me an answer about the file", "AUTOMATION"),
    ("just run it", "AUTOMATION"),
    ("debug it for me", "CODING"),
    ("look this up and write it down", "HYBRID"),
    ("send this off", "AUTOMATION"),
    ("do this", "UNCLEAR"),
    ("build something", "UNCLEAR"),
    ("show me", "UNCLEAR"),
]


@pytest.mark.parametrize("utt,verdict", _AMBIGUOUS_CASES)
def test_disambiguator_round_trips_15_cases(utt, verdict):
    """Stub the LLM with each canonical verdict per case and confirm
    the disambiguator parses + routes correctly."""
    d = IntentDisambiguator(_StubLLM(response=verdict))
    result = _run(d.disambiguate(utt))
    if verdict == "CODING":
        assert result.kind == RoutingIntentKind.CODE_TASK
    elif verdict == "AUTOMATION":
        assert result.kind == RoutingIntentKind.CONVERSATIONAL
    elif verdict == "HYBRID":
        assert result.kind == RoutingIntentKind.HYBRID_TASK
    else:
        assert result.kind is None
        assert result.clarification_question is not None
