"""2026-06-11 live-dogfood fix: cross-session RAG content floor + the
possibly-stale memories header (context-corruption guard).

Observed live: a contextless STT fragment retrieved a month-old
"Moscow is 48°F" exchange as 'relevant earlier context' and the model
recited it as current weather.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ultron.llm.inference import LLMEngine, _rag_query_has_min_content


@pytest.mark.parametrize("query,expected", [
    ("How he was initially,", False),          # the live incident
    ("hi", False),
    ("", False),
    (None, False),
    ("what about the", False),
    ("What is the capital of France?", True),
    ("tell me about the project we discussed", True),
])
def test_rag_query_min_content_floor(query, expected) -> None:
    assert _rag_query_has_min_content(query) is expected


def test_rag_block_header_marks_memories_as_possibly_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Bypass the optional compression pass (it legitimately rewrites
    # wording); this test pins the UNCOMPRESSED header contract.
    import ultron.llm.compression as compression

    monkeypatch.setattr(compression, "maybe_compress",
                        lambda block, surface: block)
    snippets = [SimpleNamespace(role="assistant",
                                content="Moscow is currently 48 F.")]
    block = LLMEngine._format_rag_block(snippets)
    assert "PAST conversations" in block
    assert "never present time-sensitive facts" in block
    assert "Moscow is currently 48 F." in block
    # The old header (which read as live context) is gone.
    assert "Relevant earlier context" not in block


def test_rag_block_empty_snippets_stay_empty() -> None:
    assert LLMEngine._format_rag_block([]) == ""
