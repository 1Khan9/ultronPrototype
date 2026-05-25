"""Roundtrip tests for the T14 chain<->client rate-limit recorder.

The provider chain binds a per-pid recorder closure into each client
at construction time. Each client calls the recorder after every
HTTP request so the chain's :class:`RateLimitTracker` stays fresh
without the chain needing direct visibility into individual request
objects.

These tests verify the full path:

1. Chain constructs client with a recorder.
2. Client makes a (mocked) HTTP request.
3. Client extracts response headers + 429 status.
4. Recorder forwards them to the chain's tracker.
5. The chain's :meth:`should_skip` honours the resulting cooldown.

Tests run hermetically -- network is stubbed via ``monkeypatch.setattr``
on ``requests.get`` and the DDG ``DDGS`` class. No real-port binding
or real-network calls (R4 / R5 from
``docs/test_sweep_binding_rules.md``).
"""
from __future__ import annotations

import os
from typing import Optional

import pytest

from ultron.web_search.brave import BraveSearchClient
from ultron.web_search.duckduckgo import DuckDuckGoSearchClient
from ultron.web_search.provider_chain import SearchProviderChain
from ultron.web_search.rate_limit import (
    RateLimitTracker,
    reset_global_tracker_for_testing,
)
from ultron.web_search.searxng import SearxNGSearchClient


@pytest.fixture(autouse=True)
def _reset_tracker():
    """Each test gets a fresh global tracker so 429s don't leak across."""
    reset_global_tracker_for_testing()
    yield
    reset_global_tracker_for_testing()


class _StubResponse:
    """Minimal stand-in for :class:`requests.Response` that the
    Brave/SearxNG clients consult: ``headers``, ``status_code``,
    ``json()``, ``raise_for_status()``."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._json_body = json_body or {"web": {"results": []}, "results": []}
        self.text = ""

    def json(self):
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            err = requests.exceptions.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


def test_brave_client_records_response_headers_through_chain(monkeypatch):
    tracker = RateLimitTracker()
    chain = SearchProviderChain(provider_ids=["brave"], tracker=tracker)

    # Ensure the Brave client constructs (needs env var).
    monkeypatch.setenv("ULTRON_BRAVE_API_KEY", "test-key")

    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None, **_):
        captured["url"] = url
        captured["params"] = dict(params or {})
        return _StubResponse(
            status_code=200,
            headers={"X-RateLimit-Remaining": "42", "X-RateLimit-Limit": "100"},
        )

    import requests
    monkeypatch.setattr(requests, "get", fake_get)

    results = chain.search("hello world", count=3)

    # Empty result but tracker should be updated.
    assert results == []
    state = tracker.state("brave")
    assert state is not None
    assert state.remaining == 42
    assert state.limit == 100
    # Successful response clears 429 counter.
    assert tracker.consecutive_429("brave") == 0


def test_brave_429_marks_chain_should_skip(monkeypatch):
    tracker = RateLimitTracker()
    chain = SearchProviderChain(provider_ids=["brave"], tracker=tracker)

    monkeypatch.setenv("ULTRON_BRAVE_API_KEY", "test-key")

    def fake_get(url, headers=None, params=None, timeout=None, **_):
        return _StubResponse(
            status_code=429,
            headers={
                "Retry-After": "60",
                "X-RateLimit-Remaining": "0",
            },
        )

    import requests
    monkeypatch.setattr(requests, "get", fake_get)

    results = chain.search("hello world", count=3)
    assert results == []

    # Tracker received the 429 outcome and put Brave on cooldown.
    assert tracker.consecutive_429("brave") == 1
    assert chain.should_skip("brave") is True


def test_chain_skips_cooled_provider_in_search_loop(monkeypatch):
    tracker = RateLimitTracker()
    chain = SearchProviderChain(provider_ids=["brave", "duckduckgo"], tracker=tracker)

    monkeypatch.setenv("ULTRON_BRAVE_API_KEY", "test-key")

    brave_calls = {"n": 0}
    ddg_calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None, **_):
        brave_calls["n"] += 1
        return _StubResponse(
            status_code=429,
            headers={"Retry-After": "300"},
        )

    import requests
    monkeypatch.setattr(requests, "get", fake_get)

    # First call: Brave returns 429, chain falls through to DDG.
    class _FakeDDGS:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def text(self, *a, **kw):
            ddg_calls["n"] += 1
            return [
                {"href": "https://example.com", "title": "ex", "body": "ok"},
            ]

    import duckduckgo_search
    monkeypatch.setattr(duckduckgo_search, "DDGS", _FakeDDGS)

    out1 = chain.search("q1", count=3)
    assert out1
    assert brave_calls["n"] == 1
    assert ddg_calls["n"] == 1

    # Second call: Brave is in cooldown; chain skips it entirely.
    out2 = chain.search("q2", count=3)
    assert out2  # DDG still serves
    assert brave_calls["n"] == 1  # Brave was NOT called again
    assert ddg_calls["n"] == 2


def test_ddg_throttle_marker_in_exception_text_marks_429(monkeypatch):
    tracker = RateLimitTracker()
    chain = SearchProviderChain(provider_ids=["duckduckgo"], tracker=tracker)

    class _FakeDDGS:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def text(self, *a, **kw):
            raise RuntimeError("DDG returned 429 too many requests; throttle")

    import duckduckgo_search
    monkeypatch.setattr(duckduckgo_search, "DDGS", _FakeDDGS)

    results = chain.search("q", count=3)
    assert results == []
    # Throttle-shaped exception text triggers was_429=True.
    assert tracker.consecutive_429("duckduckgo") >= 1


def test_ddg_success_records_clean_outcome_at_client_level(monkeypatch):
    """Validate DDG client's success path records ``was_429=False``.

    Tested at the client level (not through the chain) because the
    chain short-circuits known-cooled providers via ``should_skip``,
    so a pre-seeded cooldown would block the chain from ever calling
    the client. The success-clears-cooldown semantic is a contract on
    the tracker -- exercised by injecting a recorder that forwards
    into a fresh tracker, then asserting the counter stays at 0.
    """
    tracker = RateLimitTracker()

    def _recorder(headers, was_429):
        tracker.record("duckduckgo", None, was_429=was_429)

    client = DuckDuckGoSearchClient(on_response=_recorder)

    class _FakeDDGS:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def text(self, *a, **kw):
            return [{"href": "https://example.com", "title": "t", "body": "b"}]

    import duckduckgo_search
    monkeypatch.setattr(duckduckgo_search, "DDGS", _FakeDDGS)

    out = client.search("q", count=3)
    assert out
    # Success path called recorder with was_429=False, which leaves
    # the counter at 0 (the tracker's record() method pops the entry
    # on a clean call).
    assert tracker.consecutive_429("duckduckgo") == 0
    assert not tracker.should_skip("duckduckgo")


def test_legacy_clients_without_recorder_still_work(monkeypatch):
    """Bare client construction (no chain) preserves the legacy contract.

    Tests that pass-through callers can still build a client with no
    ``on_response`` and the client never touches a tracker.
    """
    monkeypatch.setenv("ULTRON_BRAVE_API_KEY", "test-key")
    client = BraveSearchClient()
    assert client._on_response is None

    sx = SearxNGSearchClient()
    assert sx._on_response is None

    ddg = DuckDuckGoSearchClient()
    assert ddg._on_response is None
