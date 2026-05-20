"""Tests for ``LLMEngine.generate_isolated`` (2026-05-19, Tracks 1c-1e).

The isolated path is the call surface the BackgroundSummarizer (and
future structured-extraction callers) use. It MUST:
  * skip the SOUL.md persona injection that ``generate`` performs,
  * skip history recording so background passes don't pollute the
    user-visible conversation,
  * fail-open (return ``""`` on any exception).

Stubs the underlying ``Llama`` instance so the tests run without GPU.
"""

from __future__ import annotations

import pytest

from ultron.llm.inference import LLMEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubLlama:
    """Records every call to ``create_chat_completion`` for inspection."""

    def __init__(self, response_text: str = "stub response") -> None:
        self.response_text = response_text
        self.calls = []
        self.raise_with = None  # if set, .create_chat_completion raises this

    def create_chat_completion(self, *, messages, **kwargs):
        self.calls.append({"messages": list(messages), "kwargs": dict(kwargs)})
        if self.raise_with is not None:
            raise self.raise_with
        return {
            "choices": [
                {"message": {"content": self.response_text}}
            ],
            "usage": {"completion_tokens": 5},
        }


def _make_engine_no_load(llm_response: str = "stub response") -> LLMEngine:
    """Build an LLMEngine that doesn't load a GGUF; stubs the Llama call."""
    eng = object.__new__(LLMEngine)
    eng._memory = None
    eng._history = []
    eng._explicit_system_prompt = "You are Ultron persona text."
    eng._persona_loader = None
    eng._static_system_prompt = "You are Ultron persona text."
    eng.system_prompt = "You are Ultron persona text."
    eng._logged_initial_persona = True
    eng._runtime = "in_process"
    eng._llm = _StubLlama(response_text=llm_response)
    return eng


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_generate_isolated_returns_text():
    eng = _make_engine_no_load("hello world")
    out = eng.generate_isolated(
        system_prompt="You are a summarizer worker.",
        user_prompt="Summarise the conversation.",
    )
    assert out == "hello world"


def test_generate_isolated_passes_system_prompt_not_soul():
    """The system message sent to the Llama instance must be the
    caller-provided summarizer prompt, NOT the orchestrator persona.
    This is the load-bearing invariant: background passes must not
    have SOUL.md leaking into their structured-output task."""
    eng = _make_engine_no_load()
    eng.generate_isolated(
        system_prompt="You are a summarizer worker.",
        user_prompt="Summarise.",
    )
    call = eng._llm.calls[0]
    msgs = call["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "You are a summarizer worker."
    assert "Ultron persona text" not in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "Summarise."


def test_generate_isolated_does_not_record_history():
    """The exchange must not land in the persisted history -- the
    summarizer is a background worker, not a user-visible turn."""
    eng = _make_engine_no_load()
    assert eng._history == []
    eng.generate_isolated(
        system_prompt="sys",
        user_prompt="user prompt",
    )
    assert eng._history == [], (
        "generate_isolated leaked into conversation history"
    )


def test_generate_isolated_empty_prompt_returns_empty():
    eng = _make_engine_no_load()
    assert eng.generate_isolated(system_prompt="sys", user_prompt="") == ""
    assert eng.generate_isolated(system_prompt="sys", user_prompt="   ") == ""
    # The Llama instance was not called.
    assert eng._llm.calls == []


def test_generate_isolated_fail_open_on_llama_exception():
    eng = _make_engine_no_load()
    eng._llm.raise_with = RuntimeError("llama on fire")
    out = eng.generate_isolated(system_prompt="sys", user_prompt="hi")
    assert out == ""
    # Call WAS attempted (so we know it tripped on the engine call,
    # not on input validation).
    assert len(eng._llm.calls) == 1


def test_generate_isolated_fail_open_on_unexpected_response_shape():
    eng = _make_engine_no_load()

    def _weird_create(*, messages, **kwargs):
        return {"unexpected": "shape"}

    eng._llm.create_chat_completion = _weird_create  # type: ignore[assignment]
    out = eng.generate_isolated(system_prompt="sys", user_prompt="hi")
    assert out == ""


def test_generate_isolated_strips_think_blocks():
    """Defensive: if the model emits a <think>...</think> block, the
    isolated path must strip it before returning (same contract as
    the foreground generate)."""
    eng = _make_engine_no_load(
        "<think>I should produce JSON.</think>{\"summary\": \"ok\"}"
    )
    out = eng.generate_isolated(system_prompt="sys", user_prompt="hi")
    assert "<think>" not in out
    assert "I should produce JSON" not in out
    assert '"summary": "ok"' in out


def test_generate_isolated_respects_sampling_kwargs():
    eng = _make_engine_no_load()
    eng.generate_isolated(
        system_prompt="sys",
        user_prompt="hi",
        max_tokens=128,
        temperature=0.9,
        top_p=0.5,
    )
    kwargs = eng._llm.calls[0]["kwargs"]
    assert kwargs["max_tokens"] == 128
    assert kwargs["temperature"] == pytest.approx(0.9)
    assert kwargs["top_p"] == pytest.approx(0.5)
