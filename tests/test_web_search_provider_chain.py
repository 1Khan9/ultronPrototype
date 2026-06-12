"""Web-search provider-chain tests (frontier 2026-05-21).

Tests for the local-first search ladder:
    SearxNG (local meta-search) -> Brave (API) -> DuckDuckGo (HTML fallback).

No real network calls -- all provider HTTP clients are mocked. The
chain logic is tested in isolation from the underlying providers so
we can verify:
- Config schema accepts the new fields with sane defaults.
- Chain construction with valid + invalid provider IDs.
- First-non-empty-wins ordering (SearxNG returns -> Brave + DDG NOT called).
- Empty falls through (SearxNG empty -> Brave called).
- Provider construction failure is silently skipped.
- Provider exception (vs returning []) is silently skipped + logged.
- Empty query short-circuits to [].
- All providers empty -> chain returns [].
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kenning.config import (
    DuckDuckGoConfig,
    SearxNGConfig,
    KenningConfig,
    WebSearchConfig,
)
from kenning.web_search.brave import SearchResult


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------


def test_searxng_config_defaults():
    cfg = SearxNGConfig()
    assert cfg.base_url == "http://localhost:8888"
    assert cfg.timeout_seconds == 3.0
    assert cfg.count == 5
    assert cfg.categories == ""
    assert cfg.engines == ""


def test_searxng_config_validates():
    with pytest.raises(Exception):                                       # noqa: PT011
        SearxNGConfig(timeout_seconds=-1.0)
    with pytest.raises(Exception):                                       # noqa: PT011
        SearxNGConfig(count=0)
    with pytest.raises(Exception):                                       # noqa: PT011
        SearxNGConfig(count=25)


def test_duckduckgo_config_defaults():
    cfg = DuckDuckGoConfig()
    assert cfg.timeout_seconds == 5.0
    assert cfg.region == "us-en"
    assert cfg.safesearch == "moderate"


def test_duckduckgo_config_validates_safesearch():
    DuckDuckGoConfig(safesearch="strict")
    DuckDuckGoConfig(safesearch="off")
    with pytest.raises(Exception):                                       # noqa: PT011
        DuckDuckGoConfig(safesearch="bogus")


def test_web_search_default_providers():
    """The new default provider list (local-first ladder)."""
    cfg = WebSearchConfig()
    assert cfg.providers == ["searxng", "brave", "duckduckgo"]


def test_web_search_full_config_round_trip():
    cfg = KenningConfig.model_validate({
        "web_search": {
            "providers": ["searxng", "duckduckgo"],
            "searxng": {"base_url": "http://localhost:9999"},
            "duckduckgo": {"safesearch": "off"},
        }
    })
    assert cfg.web_search.providers == ["searxng", "duckduckgo"]
    assert cfg.web_search.searxng.base_url == "http://localhost:9999"
    assert cfg.web_search.duckduckgo.safesearch == "off"


# ---------------------------------------------------------------------------
# Chain construction
# ---------------------------------------------------------------------------


def test_chain_default_construction():
    from kenning.web_search.provider_chain import SearchProviderChain
    chain = SearchProviderChain()
    assert chain.provider_ids == ["searxng", "brave", "duckduckgo"]


def test_chain_custom_construction():
    from kenning.web_search.provider_chain import SearchProviderChain
    chain = SearchProviderChain(["duckduckgo"])
    assert chain.provider_ids == ["duckduckgo"]


def test_chain_rejects_empty_list():
    from kenning.web_search.provider_chain import SearchProviderChain
    with pytest.raises(ValueError):
        SearchProviderChain([])


def test_chain_rejects_unknown_provider():
    from kenning.web_search.provider_chain import SearchProviderChain
    with pytest.raises(ValueError) as exc_info:
        SearchProviderChain(["bing"])
    assert "Unknown" in str(exc_info.value) or "bing" in str(exc_info.value).lower()


def test_chain_normalises_provider_case():
    from kenning.web_search.provider_chain import SearchProviderChain
    chain = SearchProviderChain(["SEARXNG", "Brave", "duckduckgo"])
    assert chain.provider_ids == ["searxng", "brave", "duckduckgo"]


# ---------------------------------------------------------------------------
# Chain behaviour with mocked providers
# ---------------------------------------------------------------------------


def _stub_provider(results):
    """Build a mock provider whose .search(query, count) returns
    ``results``."""
    p = MagicMock()
    p.search.return_value = results
    return p


def _result(url, rank=0):
    return SearchResult(url=url, title="t", snippet="s", rank=rank)


def test_chain_first_non_empty_wins(monkeypatch):
    """When SearxNG returns results, Brave + DDG are never called."""
    from kenning.web_search.provider_chain import SearchProviderChain
    sxng = _stub_provider([_result("https://a.test")])
    brave = _stub_provider([_result("https://b.test")])
    ddg = _stub_provider([_result("https://c.test")])
    chain = SearchProviderChain(["searxng", "brave", "duckduckgo"])
    chain._clients = {"searxng": sxng, "brave": brave, "duckduckgo": ddg}

    out = chain.search("hello")
    assert len(out) == 1
    assert out[0].url == "https://a.test"
    sxng.search.assert_called_once()
    brave.search.assert_not_called()
    ddg.search.assert_not_called()


def test_chain_falls_through_on_empty(monkeypatch):
    """SearxNG returns [] -> Brave called -> Brave returns [] -> DDG called."""
    from kenning.web_search.provider_chain import SearchProviderChain
    sxng = _stub_provider([])
    brave = _stub_provider([])
    ddg = _stub_provider([_result("https://ddg.test")])
    chain = SearchProviderChain(["searxng", "brave", "duckduckgo"])
    chain._clients = {"searxng": sxng, "brave": brave, "duckduckgo": ddg}

    out = chain.search("hello")
    assert len(out) == 1
    assert out[0].url == "https://ddg.test"
    sxng.search.assert_called_once()
    brave.search.assert_called_once()
    ddg.search.assert_called_once()


def test_chain_falls_through_on_exception(monkeypatch):
    """A provider that RAISES (vs returning []) is also caught and the
    chain falls through to the next one."""
    from kenning.web_search.provider_chain import SearchProviderChain
    sxng = MagicMock()
    sxng.search.side_effect = RuntimeError("simulated provider crash")
    brave = _stub_provider([_result("https://b.test")])
    ddg = _stub_provider([_result("https://c.test")])
    chain = SearchProviderChain(["searxng", "brave", "duckduckgo"])
    chain._clients = {"searxng": sxng, "brave": brave, "duckduckgo": ddg}

    out = chain.search("hello")
    assert len(out) == 1
    assert out[0].url == "https://b.test"
    brave.search.assert_called_once()


def test_chain_skips_unconstructable_provider(monkeypatch):
    """If a provider's factory raises at construction (e.g., missing
    Brave key), the chain skips it without crashing.

    Uses ``monkeypatch.setattr`` so the original ``_PROVIDER_FACTORIES``
    is restored at teardown — direct class-level assignment would
    permanently mutate state and break later tests.
    """
    from kenning.web_search import provider_chain as pc_module

    monkeypatch.setattr(
        pc_module.SearchProviderChain,
        "_PROVIDER_FACTORIES",
        {
            # 2026-05-26 T14 wiring: factories now take a recorder
            # callable. Tests that ignore the recorder still work --
            # the callback is just never invoked.
            "searxng": lambda _recorder: _stub_provider([]),
            "brave": lambda _recorder: (_ for _ in ()).throw(
                ValueError("Brave API key missing"),
            ),
            "duckduckgo": lambda _recorder: _stub_provider(
                [_result("https://ddg.test")],
            ),
        },
    )
    chain = pc_module.SearchProviderChain(["searxng", "brave", "duckduckgo"])
    out = chain.search("hello")
    assert len(out) == 1
    assert out[0].url == "https://ddg.test"


def test_chain_all_empty_returns_empty():
    from kenning.web_search.provider_chain import SearchProviderChain
    chain = SearchProviderChain(["searxng", "brave", "duckduckgo"])
    chain._clients = {
        "searxng": _stub_provider([]),
        "brave": _stub_provider([]),
        "duckduckgo": _stub_provider([]),
    }
    assert chain.search("hello") == []


def test_chain_empty_query_short_circuits():
    from kenning.web_search.provider_chain import SearchProviderChain
    chain = SearchProviderChain(["searxng"])
    p = _stub_provider([_result("https://a.test")])
    chain._clients = {"searxng": p}
    assert chain.search("") == []
    assert chain.search("   ") == []
    p.search.assert_not_called()


# ---------------------------------------------------------------------------
# SearxNG + DuckDuckGo client smoke tests (no real network)
# ---------------------------------------------------------------------------


def test_searxng_client_imports():
    from kenning.web_search.searxng import SearxNGSearchClient
    client = SearxNGSearchClient()
    assert client.base_url == "http://localhost:8888"


def test_searxng_search_empty_query_returns_empty():
    from kenning.web_search.searxng import SearxNGSearchClient
    client = SearxNGSearchClient()
    assert client.search("") == []
    assert client.search("   ") == []


def test_searxng_is_reachable_false_when_not_running():
    """The default localhost:8888 isn't running in the test env --
    is_reachable() should return False without raising."""
    from kenning.web_search.searxng import SearxNGSearchClient
    client = SearxNGSearchClient(base_url="http://localhost:65500")
    assert client.is_reachable() is False


def test_duckduckgo_client_imports():
    from kenning.web_search.duckduckgo import DuckDuckGoSearchClient
    client = DuckDuckGoSearchClient()
    assert client.region == "us-en"
    assert client.safesearch == "moderate"


def test_duckduckgo_search_empty_query_returns_empty():
    from kenning.web_search.duckduckgo import DuckDuckGoSearchClient
    client = DuckDuckGoSearchClient()
    assert client.search("") == []


# ---------------------------------------------------------------------------
# T14 rate-limit tracker integration
# ---------------------------------------------------------------------------


def test_chain_construction_attaches_tracker():
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import RateLimitTracker
    chain = SearchProviderChain(["searxng"])
    assert isinstance(chain.tracker, RateLimitTracker)


def test_chain_uses_injected_tracker():
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import RateLimitTracker
    custom = RateLimitTracker()
    chain = SearchProviderChain(["searxng"], tracker=custom)
    assert chain.tracker is custom


def test_chain_should_skip_passes_through_to_tracker():
    """SearchProviderChain.should_skip mirrors the tracker's verdict."""
    from datetime import datetime, timezone
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import RateLimitState, RateLimitTracker

    custom = RateLimitTracker()
    chain = SearchProviderChain(["searxng", "brave"], tracker=custom)
    assert not chain.should_skip("searxng")
    custom.record(
        "searxng",
        RateLimitState(retry_after_seconds=60.0),
        was_429=True,
        now=datetime.now(timezone.utc),
    )
    assert chain.should_skip("searxng")


def test_chain_record_outcome_parses_and_records():
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import RateLimitTracker

    custom = RateLimitTracker()
    chain = SearchProviderChain(["brave"], tracker=custom)
    state = chain.record_provider_outcome(
        "brave",
        {"Retry-After": "30", "RateLimit-Limit": "3000"},
        was_429=True,
    )
    assert state is not None
    assert state.retry_after_seconds == 30.0
    assert state.limit == 3000
    assert custom.should_skip("brave")


def test_chain_record_outcome_none_headers_clears_tracker_on_success():
    """A success after a 429 with no rate-limit headers clears the cooldown."""
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import RateLimitTracker

    custom = RateLimitTracker()
    chain = SearchProviderChain(["brave"], tracker=custom)
    chain.record_provider_outcome(
        "brave", {"Retry-After": "30"}, was_429=True,
    )
    assert custom.should_skip("brave")
    chain.record_provider_outcome("brave", None, was_429=False)
    assert not custom.should_skip("brave")


def test_chain_skips_provider_in_cooldown():
    """A provider in cooldown is skipped without invoking its client."""
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import RateLimitTracker

    custom = RateLimitTracker()
    sxng = _stub_provider([])
    brave = _stub_provider([_result("https://brave.test")])
    chain = SearchProviderChain(["searxng", "brave"], tracker=custom)
    chain._clients = {"searxng": sxng, "brave": brave}

    # Cool down searxng.
    chain.record_provider_outcome(
        "searxng",
        {"Retry-After": "120"},
        was_429=True,
    )
    out = chain.search("hello")
    assert len(out) == 1
    assert out[0].url == "https://brave.test"
    sxng.search.assert_not_called()
    brave.search.assert_called_once()


def test_chain_tracker_isolated_from_global_when_injected():
    """A test-local tracker doesn't leak into the global singleton."""
    from kenning.web_search.provider_chain import SearchProviderChain
    from kenning.web_search.rate_limit import (
        RateLimitTracker,
        get_global_tracker,
        reset_global_tracker_for_testing,
    )

    reset_global_tracker_for_testing()
    custom = RateLimitTracker()
    chain = SearchProviderChain(["brave"], tracker=custom)
    chain.record_provider_outcome(
        "brave", {"Retry-After": "30"}, was_429=True,
    )
    # Custom tracker has the cooldown.
    assert custom.should_skip("brave")
    # Global tracker is untouched.
    assert not get_global_tracker().should_skip("brave")
