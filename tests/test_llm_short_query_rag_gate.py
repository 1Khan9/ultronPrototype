"""2026-05-19 Issue 2 fix: short-conversational-query RAG suppressor.

A 'Say hello.' utterance went all the way to the LLM with a RAG block
containing a stale Salesforce-pricing snippet, producing a wildly off-
topic response. The fix adds a pre-retrieval gate
(:func:`kenning.llm.inference._is_short_conversational_query`) that
returns True for greetings + acks + very short non-factual utterances;
:meth:`LLMEngine._retrieve_rag_snippets` checks the gate and short-
circuits to ``[]`` when it fires.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

import pytest

from kenning.config import MemoryRetrievalConfig
from kenning.llm.inference import (
    LLMEngine,
    _is_short_conversational_query,
)


# ---------------------------------------------------------------------------
# Pure helper: _is_short_conversational_query
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", [
    "hi",
    "hello",
    "Hello!",
    "Hello there",
    "hey",
    "good morning",
    "Good evening, Kenning",
    "say hello",
    "Say something.",
    "say anything",
    "howdy",
    "aloha",
])
def test_greeting_queries_classified_as_short_conversational(query):
    assert _is_short_conversational_query(query) is True


@pytest.mark.parametrize("query", [
    "thanks",
    "Thanks!",
    "thank you",
    "ok",
    "Okay.",
    "sure",
    "yes",
    "no",
    "yeah",
    "yep",
    "nope",
    "cool",
    "nice",
    "got it",
    "sounds good",
    "alright",
    "right",
    "fine",
    "perfect",
    "great",
    "awesome",
    "mhm",
    "hmm",
])
def test_ack_queries_classified_as_short_conversational(query):
    assert _is_short_conversational_query(query) is True


@pytest.mark.parametrize("query", [
    "what time is it",
    "what time is it?",
    "how much does a duck weigh",
    "who invented the telephone",
    "when was the moon landing",
    "where is the nearest store",
    "why is the sky blue",
    "which planet is the largest",
    "tell me about quantum physics",
    "explain entropy",
    "describe the process of photosynthesis",
    "show me a picture of a chicken",
    "give me the steps to bake a cake",
    "list the planets in the solar system",
    "find the nearest cafe",
    "search for python tutorials",
    "open Chrome on my main monitor",
    "play music on Spotify",
    "switch to the 4B model",
    "fix the bug in my code",
    "write me a program that does X",
    "is it raining outside",
    "are there clouds today",
    "can you help me",
    "should I bring an umbrella",
    "would that be possible",
])
def test_factual_questions_not_classified_as_short(query):
    assert _is_short_conversational_query(query) is False


def test_short_generic_non_factual_classified_as_short():
    """Very short utterances without a factual stem still suppress
    RAG -- they have so little semantic signal that RAG is a coin
    flip for relevance."""
    assert _is_short_conversational_query("any update") is True
    assert _is_short_conversational_query("never mind") is True
    assert _is_short_conversational_query("not really") is True


def test_long_query_not_classified_as_short_even_without_factual_stem():
    """Multi-clause queries get retrieval regardless -- a 6+ token
    utterance probably carries enough signal to land on-topic."""
    query = "the duck I mentioned earlier should be cooked at 350 degrees"
    assert _is_short_conversational_query(query) is False


def test_empty_query_classified_as_short():
    assert _is_short_conversational_query("") is True
    assert _is_short_conversational_query("   ") is True


def test_none_query_classified_as_short():
    assert _is_short_conversational_query(None) is True


# ---------------------------------------------------------------------------
# LLMEngine._retrieve_rag_snippets short-circuits on the gate
# ---------------------------------------------------------------------------


class _SpyMemory:
    """Records every retrieve() call so we can assert short-circuit
    behaviour."""

    def __init__(self, snippets=None):
        self._snippets = list(snippets or [])
        self.retrieve_calls = 0
        self.retrieve_for_query_calls = 0

    def retrieve(self, query, k=5, exclude_recent=20):
        self.retrieve_calls += 1
        return list(self._snippets[:k])

    def retrieve_for_query(self, query, gate_verdict, *, k=5, exclude_recent=20):
        self.retrieve_for_query_calls += 1
        return list(self._snippets[:k])


def _make_engine_with_memory(memory) -> LLMEngine:
    eng = object.__new__(LLMEngine)
    eng._memory = memory
    eng._history = []
    eng._runtime = "in_process"
    return eng


def test_retrieve_short_circuits_on_greeting():
    spy = _SpyMemory([SimpleNamespace(role="user", content="old note")])
    eng = _make_engine_with_memory(spy)
    out = eng._retrieve_rag_snippets("Say hello.")
    assert out == []
    assert spy.retrieve_calls == 0
    assert spy.retrieve_for_query_calls == 0


def test_retrieve_short_circuits_on_ack():
    spy = _SpyMemory([SimpleNamespace(role="user", content="old note")])
    eng = _make_engine_with_memory(spy)
    out = eng._retrieve_rag_snippets("thanks")
    assert out == []
    assert spy.retrieve_calls == 0


def test_retrieve_proceeds_on_factual_question():
    snippets = [SimpleNamespace(role="user", content="relevant note")]
    spy = _SpyMemory(snippets)
    eng = _make_engine_with_memory(spy)
    out = eng._retrieve_rag_snippets("what time is it?")
    # Memory WAS consulted (the short-query gate didn't fire).
    assert spy.retrieve_calls == 1
    assert out == snippets


def test_retrieve_proceeds_on_long_query():
    snippets = [SimpleNamespace(role="user", content="relevant note")]
    spy = _SpyMemory(snippets)
    eng = _make_engine_with_memory(spy)
    out = eng._retrieve_rag_snippets(
        "tell me everything you know about the history of jazz music"
    )
    assert spy.retrieve_calls == 1
    assert out == snippets


def test_retrieve_short_circuits_when_memory_is_none():
    """Defensive: no memory installed -> empty list regardless."""
    eng = _make_engine_with_memory(None)
    assert eng._retrieve_rag_snippets("anything") == []


def test_skip_rag_for_short_queries_disabled_via_config(monkeypatch):
    """When the config knob is False, even greetings hit retrieve --
    legacy behaviour preserved for operators who want the old way."""
    from kenning import config as _cfg_module

    snippets = [SimpleNamespace(role="user", content="legacy hit")]
    spy = _SpyMemory(snippets)
    eng = _make_engine_with_memory(spy)

    # Build a config with the knob flipped off.
    cfg = _cfg_module.KenningConfig()
    cfg.memory.retrieval.skip_rag_for_short_queries = False
    monkeypatch.setattr(_cfg_module, "get_config", lambda: cfg)
    monkeypatch.setattr(
        "kenning.llm.inference.get_config", lambda: cfg,
    )

    out = eng._retrieve_rag_snippets("hi")
    assert spy.retrieve_calls == 1
    assert out == snippets


# ---------------------------------------------------------------------------
# Config schema sanity
# ---------------------------------------------------------------------------


def test_retrieval_config_default_skip_rag_for_short_queries_is_true():
    cfg = MemoryRetrievalConfig()
    assert cfg.skip_rag_for_short_queries is True


def test_retrieval_config_skip_rag_for_short_queries_round_trips():
    cfg = MemoryRetrievalConfig(skip_rag_for_short_queries=False)
    assert cfg.skip_rag_for_short_queries is False
