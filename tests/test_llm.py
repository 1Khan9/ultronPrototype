"""LLM inference tests.

Slow + GPU-gated; exercise both blocking and streaming generation.
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
    reason="set PYTEST_RUN_GPU_TESTS=1 to load the LLM",
)
def test_llm_generate_returns_text():
    from kenning.llm import LLMEngine

    with LLMEngine() as llm:
        out = llm.generate("Reply with the single word: ready.")
        assert isinstance(out, str)
        assert len(out) > 0


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
    reason="set PYTEST_RUN_GPU_TESTS=1 to load the LLM",
)
def test_llm_stream_yields_tokens():
    from kenning.llm import LLMEngine

    with LLMEngine() as llm:
        tokens = list(llm.generate_stream("Count to three."))
        assert len(tokens) > 1
        assert all(isinstance(t, str) for t in tokens)
        assert "".join(tokens).strip() != ""
