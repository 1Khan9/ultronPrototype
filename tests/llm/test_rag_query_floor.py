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


# ---------------------------------------------------------------------------
# 2026-06-11 live fix: /no_think is Qwen-template-specific -- other
# presets parrot it and TTS speaks "No think" aloud.
# ---------------------------------------------------------------------------


def test_no_think_marker_only_for_qwen_presets(monkeypatch) -> None:
    import ultron.config as config_mod

    msgs = [{"role": "user", "content": "hello there"}]

    monkeypatch.setattr(
        config_mod, "get_config",
        lambda: SimpleNamespace(llm=SimpleNamespace(
            preset="qwen3.5-4b", model_path="models/Qwen3.5-4B-Q4_K_M.gguf",
        )),
    )
    out = LLMEngine._apply_no_think_marker(msgs, False)
    assert out[-1]["content"].endswith("/no_think")

    monkeypatch.setattr(
        config_mod, "get_config",
        lambda: SimpleNamespace(llm=SimpleNamespace(
            preset="llama-3.2-3b-abliterated",
            model_path="models/Llama-3.2-3B-Instruct-abliterated.Q4_K_M.gguf",
        )),
    )
    out = LLMEngine._apply_no_think_marker(msgs, False)
    assert "/no_think" not in out[-1]["content"]

    # enable_thinking None/True: never appended regardless of preset.
    out = LLMEngine._apply_no_think_marker(msgs, None)
    assert "/no_think" not in out[-1]["content"]
