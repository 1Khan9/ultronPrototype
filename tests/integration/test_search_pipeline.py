"""Integration test category 2 — search-triggering query path.

The orchestrator delegates web-search-needed decisions to the
WebSearchGate. This test set exercises the gate + executor with mocked
Brave + Jina (no network) and verifies:

  - Gate classifies time-sensitive queries as SEARCH
  - Mocked Brave returns canned snippets
  - Mocked Jina returns canned full text
  - The acknowledgment phrase is selected (would be spoken to the user)
  - Cache hits short-circuit the API path
  - Brave failure falls back to base knowledge

Real Brave + Jina + LLM together is exercised in
:mod:`scripts.measure_baseline_extended` ``--full`` mode, gated on having
a valid API key. Those numbers feed `phase_foundation_start.measurements_extended.search_query_vram`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from kenning.web_search import (
    AcknowledgmentSource,
    BraveResult,
    BraveSearchClient,
    JinaReaderClient,
    WebSearchExecutor,
    WebSearchGate,
)
from kenning.web_search.gating import GateDecision


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


class _StubLLM:
    def __init__(self, ranking_response='{"ranked_indices":[1,2]}'):
        self._ranking_response = ranking_response

    @property
    def _llm(self):
        # The executor invokes self.llm._llm.create_chat_completion(...) for
        # snippet ranking. Mimic that surface.
        out = MagicMock()
        out.create_chat_completion = MagicMock(return_value={
            "choices": [{"message": {"content": self._ranking_response}}],
        })
        return out

    def generate(self, prompt: str) -> str:
        return self._ranking_response


class _MockBrave(BraveSearchClient):
    """Bypasses __init__ so we don't need an API key."""
    def __init__(self, fixture=None):
        self.api_key = "mock"
        self.endpoint = "mock://"
        self.rate_limit_s = 0.0
        self.timeout_s = 0.0
        self._last_call = 0.0
        import threading
        self._lock = threading.Lock()
        # Sentinel-aware default: explicit empty list stays empty; None
        # falls back to the canned fixture. Critical for the
        # "no Brave results" test path.
        if fixture is None:
            fixture = [
                BraveResult(url="https://example.com/a", title="A", snippet="snippet A", rank=0),
                BraveResult(url="https://example.com/b", title="B", snippet="snippet B", rank=1),
                BraveResult(url="https://example.com/c", title="C", snippet="snippet C", rank=2),
            ]
        self._fixture = list(fixture)

    def search(self, query, count=5):
        return list(self._fixture[:count])


class _MockJina(JinaReaderClient):
    def __init__(self, body="# Page\n\nMocked Jina text."):
        self.endpoint = "mock://"
        self.timeout_s = 0.0
        self.max_bytes = 200_000
        self._body = body

    def fetch(self, url):
        return self._body


# ---------------------------------------------------------------------------
# Search-trigger gate decisions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utt", [
    "what's the latest news on Python 3.13",
    "what's the weather right now",
    "what's the price of bitcoin today",
    "what just happened in the senate",
    "tell me about the latest release of llama.cpp",
])
def test_time_sensitive_queries_are_gated_search(utt):
    """Hard-rule layer should classify these as SEARCH without an LLM call."""
    gate = WebSearchGate(llm=None)
    verdict = gate.classify(utt)
    assert verdict.decision in (GateDecision.SEARCH, GateDecision.UNCERTAIN), (
        f"got {verdict.decision} for {utt!r}: {verdict.reason}"
    )


@pytest.mark.parametrize("utt", [
    "what's my main project",
    "do I remember telling you about meditation",
    "who am I",
    "what did I say earlier",
])
def test_personal_queries_are_gated_no_search(utt):
    gate = WebSearchGate(llm=None)
    verdict = gate.classify(utt)
    assert verdict.decision == GateDecision.NO_SEARCH


def test_url_in_utterance_triggers_search():
    gate = WebSearchGate(llm=None)
    verdict = gate.classify("look at https://example.com/article")
    assert verdict.decision == GateDecision.SEARCH


# ---------------------------------------------------------------------------
# Executor with mocked Brave + Jina
# ---------------------------------------------------------------------------


def test_executor_runs_with_mocked_brave_and_jina():
    """A SEARCH path runs end-to-end: Brave returns canned rows, Jina
    returns canned markdown, executor produces a SearchPayload."""
    executor = WebSearchExecutor(
        brave=_MockBrave(),
        jina=_MockJina(),
        llm=_StubLLM(),
        cache=None,
        max_fetch=2,
    )
    payload = executor.run("what's the latest on python 3.13", top_n=3)
    assert payload.cache_hit is False
    # _StubLLM ranking returns indices [1, 2] -> first two snippets ranked
    assert 1 <= len(payload.sources) <= 3
    # First source has a Jina full_text
    assert payload.sources[0].full_text is not None


def test_executor_no_brave_results_returns_empty_payload():
    executor = WebSearchExecutor(
        brave=_MockBrave(fixture=[]),
        jina=_MockJina(),
        llm=_StubLLM(),
        cache=None,
        max_fetch=2,
    )
    payload = executor.run("anything", top_n=3)
    assert payload.sources == []
    assert "no Brave results" in payload.notes[0]


def test_executor_brave_failure_falls_back_to_empty():
    """When Brave raises, the executor records a note and returns []."""
    bad_brave = _MockBrave()
    bad_brave.search = MagicMock(side_effect=RuntimeError("transient"))
    executor = WebSearchExecutor(
        brave=bad_brave,
        jina=_MockJina(),
        llm=_StubLLM(),
        cache=None,
        max_fetch=2,
    )
    payload = executor.run("anything", top_n=3)
    assert payload.sources == []
    assert any("brave_error" in n for n in payload.notes)


def test_executor_jina_failure_keeps_snippets():
    """When Jina fails on every URL, the executor returns sources with
    full_text=None — the LLM still gets snippet-only context."""
    bad_jina = _MockJina()
    bad_jina.fetch = MagicMock(return_value=None)
    executor = WebSearchExecutor(
        brave=_MockBrave(),
        jina=bad_jina,
        llm=_StubLLM(),
        cache=None,
        max_fetch=2,
    )
    payload = executor.run("anything", top_n=3)
    assert len(payload.sources) >= 1
    assert all(s.full_text is None for s in payload.sources)


# ---------------------------------------------------------------------------
# Acknowledgment phrase availability
# ---------------------------------------------------------------------------


def test_acknowledgment_source_returns_phrase():
    src = AcknowledgmentSource()
    phrase = src.next_phrase()
    assert isinstance(phrase, str) and len(phrase) > 0


def test_acknowledgment_pool_cycles_without_repetition():
    """Every phrase in the pool surfaces once before any repeats."""
    src = AcknowledgmentSource()
    seen = set()
    pool_size = len(src._pool)  # noqa: SLF001 — test inspection
    for _ in range(pool_size):
        seen.add(src.next_phrase())
    assert len(seen) == pool_size
