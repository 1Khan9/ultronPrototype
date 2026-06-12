"""Catalog 12 (felo-search T4): search-strategy transparency.

Pure-function coverage of the strategy-line helper, the optional
``strategy_queries`` param on both source formatters, and the
``SearchPayload.queries`` field. No network / model / mocking needed.
"""

from __future__ import annotations

from kenning.web_search.search import (
    SearchPayload,
    SearchSource,
    _format_strategy_line,
    format_sources_for_prompt,
    format_sources_for_transcript,
)


def _src(i: int) -> SearchSource:
    return SearchSource(
        url=f"https://example.com/{i}",
        title=f"Title {i}",
        snippet=f"snippet {i}",
        full_text=None,
        rank=i,
    )


# ---------------------------------------------------------------------------
# _format_strategy_line
# ---------------------------------------------------------------------------


def test_strategy_line_none_and_empty():
    assert _format_strategy_line(None) == ""
    assert _format_strategy_line([]) == ""


def test_strategy_line_single_query_suppressed():
    # A single query is just the user's question -- no "strategy" to show.
    assert _format_strategy_line(["python tutorial"]) == ""


def test_strategy_line_multiple_joined():
    assert _format_strategy_line(["a", "b", "c"]) == "a | b | c"


def test_strategy_line_strips_blanks_then_checks_count():
    # Blanks dropped first; the remaining single real query is suppressed.
    assert _format_strategy_line(["only", "  ", ""]) == ""
    assert _format_strategy_line(["x", "  ", "y"]) == "x | y"


# ---------------------------------------------------------------------------
# format_sources_for_prompt
# ---------------------------------------------------------------------------


def test_prompt_without_strategy_has_no_strategy_line():
    out = format_sources_for_prompt([_src(1), _src(2)])
    assert "Search strategy" not in out


def test_prompt_with_multi_strategy_appends_line():
    out = format_sources_for_prompt(
        [_src(1)], strategy_queries=["python perf", "asyncio vs threads"]
    )
    assert out.rstrip().endswith("[Search strategy: python perf | asyncio vs threads]")


def test_prompt_with_single_strategy_query_suppressed():
    out = format_sources_for_prompt([_src(1)], strategy_queries=["just one"])
    assert "Search strategy" not in out


def test_prompt_no_sources_passthrough():
    assert format_sources_for_prompt([]) == "(no sources)"


# ---------------------------------------------------------------------------
# format_sources_for_transcript
# ---------------------------------------------------------------------------


def test_transcript_without_strategy_has_no_strategy_line():
    out = format_sources_for_transcript([_src(1), _src(2)])
    assert "strategy:" not in out
    assert "sources:" in out


def test_transcript_with_multi_strategy_appends_line():
    out = format_sources_for_transcript(
        [_src(1)], strategy_queries=["q one", "q two"]
    )
    assert "  strategy: q one | q two" in out.splitlines()


def test_transcript_single_strategy_query_suppressed():
    out = format_sources_for_transcript([_src(1)], strategy_queries=["solo"])
    assert "strategy:" not in out


def test_transcript_empty_sources_returns_blank():
    assert format_sources_for_transcript([]) == ""


# ---------------------------------------------------------------------------
# SearchPayload.queries field
# ---------------------------------------------------------------------------


def test_search_payload_queries_defaults_empty():
    p = SearchPayload(query="q", sources=[], cache_hit=False, elapsed_ms=0.0)
    assert p.queries == []


def test_search_payload_queries_roundtrip():
    p = SearchPayload(
        query="q",
        sources=[_src(1)],
        cache_hit=False,
        elapsed_ms=1.0,
        queries=["q", "q variant"],
    )
    assert p.queries == ["q", "q variant"]
