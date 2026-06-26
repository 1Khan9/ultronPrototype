"""4B optimization plan Stage F -- enable_thinking parameter tests.

2026-05-14 second-pass rewrite: the historical Stage F approach passed
``chat_template_kwargs={"enable_thinking": ...}`` to llama-cpp-python's
``create_chat_completion``. The pinned version in this venv (0.3.22)
does NOT accept that kwarg -- the call raises TypeError. Live runs
showed every screen-context query and every web-search preflight
hitting this path and failing.

The mechanism has been swapped to inject Qwen3's ``/no_think`` user-
message marker at the prompt layer (see
``LLMEngine._apply_no_think_marker``). The HTTP runtime keeps the
``chat_template_kwargs`` payload because llama-cpp-server (separate
binary, separate codebase) does accept it -- so the HTTP tests below
are unchanged. Only the in-process tests are rewritten.

Mocks the underlying Llama / requests so no GPU or network is needed.
"""
from __future__ import annotations

from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest

from kenning.llm.inference import LLMEngine


# ---------------------------------------------------------------------------
# Pure helper test -- _chat_completion_kwargs (in-process kwargs)
# ---------------------------------------------------------------------------


class _LLMCfg:
    default_temperature = 0.7
    default_top_p = 0.9
    default_max_tokens = 512
    default_repeat_penalty = 1.1


def test_chat_completion_kwargs_default() -> None:
    """No enable_thinking, no streaming -> the four sampling params only.
    Must never include chat_template_kwargs after the 2026-05-14 fix
    because llama-cpp-python 0.3.22 rejects it."""
    kw = LLMEngine._chat_completion_kwargs(_LLMCfg(), None, stream=False)
    assert "chat_template_kwargs" not in kw
    assert kw["temperature"] == 0.7
    assert kw["top_p"] == 0.9
    assert kw["max_tokens"] == 512
    assert kw["repeat_penalty"] == 1.1
    assert "stream" not in kw


def test_chat_completion_kwargs_streaming_flag() -> None:
    kw = LLMEngine._chat_completion_kwargs(_LLMCfg(), None, stream=True)
    assert kw["stream"] is True


def test_chat_completion_kwargs_never_emits_chat_template_kwargs() -> None:
    """Pinned regression: even with enable_thinking=False/True the
    kwargs dict must NOT include chat_template_kwargs in the in-process
    path. The thinking-mode toggle is applied to the user message via
    /no_think, not to the LLM kwargs."""
    for et in (None, True, False):
        for stream in (False, True):
            kw = LLMEngine._chat_completion_kwargs(_LLMCfg(), et, stream=stream)
            assert "chat_template_kwargs" not in kw, (
                f"unexpected chat_template_kwargs for "
                f"enable_thinking={et} stream={stream}"
            )


# ---------------------------------------------------------------------------
# _apply_no_think_marker -- instance method (2026-06-15: now reads the
# LIVE-loaded ``self.model_path`` so the QWEN-only marker is never appended on
# the llama-3.2-3b gaming preset, which parroted it aloud as "No think.").
# ---------------------------------------------------------------------------


def _qwen_engine() -> LLMEngine:
    """Bare engine whose LIVE model is a Qwen GGUF (marker SHOULD apply)."""
    eng = LLMEngine.__new__(LLMEngine)
    eng.model_path = "C:/models/qwen3-8b-instruct.gguf"
    return eng


def _llama_engine() -> LLMEngine:
    """Bare engine whose LIVE model is the llama gaming preset (NO marker)."""
    eng = LLMEngine.__new__(LLMEngine)
    eng.model_path = "C:/models/llama-3.2-3b-abliterated.gguf"
    return eng


def test_apply_no_think_marker_appends_when_false() -> None:
    msgs = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "what is X?"},
    ]
    out = _qwen_engine()._apply_no_think_marker(msgs, False)
    assert out[-1]["content"].endswith("/no_think")
    # Original list untouched
    assert msgs[-1]["content"] == "what is X?"


def test_apply_no_think_marker_skips_when_none_or_true() -> None:
    msgs = [{"role": "user", "content": "what is X?"}]
    for et in (None, True):
        out = _qwen_engine()._apply_no_think_marker(msgs, et)
        assert "/no_think" not in out[-1]["content"]


def test_apply_no_think_marker_skips_for_non_qwen_live_model() -> None:
    """2026-06-15: the llama-3.2-3b gaming preset does NOT consume the Qwen
    marker -- it parrots it ("No think."). The live model_path is authoritative,
    so even with enable_thinking=False the marker must NOT be appended."""
    msgs = [{"role": "user", "content": "economy."}]
    out = _llama_engine()._apply_no_think_marker(msgs, False)
    assert "/no_think" not in out[-1]["content"]


def test_apply_no_think_marker_idempotent_when_already_present() -> None:
    msgs = [{"role": "user", "content": "what is X? /no_think"}]
    out = _qwen_engine()._apply_no_think_marker(msgs, False)
    # Must not append a second marker.
    assert out[-1]["content"].count("/no_think") == 1


def test_apply_no_think_marker_targets_last_user_only() -> None:
    """Multiple user turns -> only the last user message gets the
    marker (that's the one we're about to answer)."""
    msgs = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "second turn"},
    ]
    out = _qwen_engine()._apply_no_think_marker(msgs, False)
    assert "/no_think" not in out[0]["content"]
    assert "/no_think" in out[2]["content"]


def test_apply_no_think_marker_empty_messages() -> None:
    assert _qwen_engine()._apply_no_think_marker([], False) == []


# ---------------------------------------------------------------------------
# In-process runtime -- verify the no_think marker reaches the user message
# ---------------------------------------------------------------------------


def _make_engine_with_mock_llm() -> LLMEngine:
    """Construct an LLMEngine with the in_process llama mocked out.

    Avoids actual GGUF loading; lets us assert what create_chat_completion
    is called with."""
    eng = LLMEngine.__new__(LLMEngine)
    eng._runtime = "in_process"
    # 2026-06-15: the marker check now reads the LIVE model_path; a Qwen GGUF
    # means the /no_think marker still applies on the in-process path.
    eng.model_path = "C:/models/qwen3-8b-instruct.gguf"
    eng._llm = MagicMock()
    eng._cancel = __import__("threading").Event()
    eng._history = __import__("collections").deque()
    eng._memory = None
    eng._history_turns = 6
    eng._cfg = MagicMock()
    eng._system_prompt = "test prompt"

    def _build(user_message, **kwargs):
        return [
            {"role": "system", "content": "test prompt"},
            {"role": "user", "content": user_message},
        ]
    eng._build_messages = _build  # type: ignore
    eng._record_turn = MagicMock()
    return eng


def test_in_process_generate_injects_no_think_when_false() -> None:
    eng = _make_engine_with_mock_llm()
    eng._llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "hi"}}],
        "usage": {"completion_tokens": 1},
    }
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = _LLMCfg()
        eng.generate("hello", enable_thinking=False)
    call_kwargs = eng._llm.create_chat_completion.call_args.kwargs
    assert "chat_template_kwargs" not in call_kwargs
    msgs = call_kwargs["messages"]
    assert msgs[-1]["content"].endswith("/no_think")


def test_in_process_generate_no_marker_when_true_or_default() -> None:
    """enable_thinking=True and the default (None) must NOT inject
    the marker -- letting the chat template's default behaviour apply
    (which is thinking-on for Qwen3 / Qwen3.5)."""
    for et in (None, True):
        eng = _make_engine_with_mock_llm()
        eng._llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {},
        }
        with patch("kenning.llm.inference.get_config") as gc:
            gc.return_value.llm = _LLMCfg()
            eng.generate("hello", enable_thinking=et)
        call_kwargs = eng._llm.create_chat_completion.call_args.kwargs
        assert "chat_template_kwargs" not in call_kwargs
        msgs = call_kwargs["messages"]
        assert "/no_think" not in msgs[-1]["content"], (
            f"unexpected marker for enable_thinking={et}"
        )


def test_in_process_generate_stream_injects_no_think_when_false() -> None:
    eng = _make_engine_with_mock_llm()

    def _fake_stream() -> Iterator[dict]:
        yield {"choices": [{"delta": {"content": "ok"}}]}
    eng._llm.create_chat_completion.return_value = _fake_stream()
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = _LLMCfg()
        list(eng.generate_stream("hi", enable_thinking=False))
    call_kwargs = eng._llm.create_chat_completion.call_args.kwargs
    assert "chat_template_kwargs" not in call_kwargs
    assert call_kwargs["stream"] is True
    msgs = call_kwargs["messages"]
    assert msgs[-1]["content"].endswith("/no_think")


def test_in_process_generate_stream_default_no_marker() -> None:
    eng = _make_engine_with_mock_llm()

    def _fake_stream() -> Iterator[dict]:
        yield {"choices": [{"delta": {"content": "ok"}}]}
    eng._llm.create_chat_completion.return_value = _fake_stream()
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = _LLMCfg()
        list(eng.generate_stream("hi"))
    call_kwargs = eng._llm.create_chat_completion.call_args.kwargs
    assert "chat_template_kwargs" not in call_kwargs
    msgs = call_kwargs["messages"]
    assert "/no_think" not in msgs[-1]["content"]


def test_in_process_generate_does_not_crash_with_real_llamacpp_signature() -> None:
    """Regression for the 2026-05-14 live-session crash. The previous
    implementation passed chat_template_kwargs to a mock that accepted
    anything; against the real llama-cpp-python 0.3.22 it raised
    TypeError. This test asserts the call ONLY uses kwargs that the
    real 0.3.22 signature accepts."""
    import inspect
    try:
        import llama_cpp  # type: ignore
    except Exception:
        pytest.skip("llama_cpp not importable (CUDA DLL?)")
    real_params = set(
        inspect.signature(llama_cpp.Llama.create_chat_completion).parameters
    )
    real_params.discard("self")

    eng = _make_engine_with_mock_llm()
    eng._llm.create_chat_completion.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {},
    }
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = _LLMCfg()
        eng.generate("hello", enable_thinking=False)
    call_kwargs = set(eng._llm.create_chat_completion.call_args.kwargs)
    bad = call_kwargs - real_params
    assert not bad, (
        f"in-process generate() passed kwargs not in "
        f"llama_cpp.Llama.create_chat_completion signature: {bad}"
    )


# ---------------------------------------------------------------------------
# HTTP runtime -- llama-cpp-server DOES support chat_template_kwargs so
# the payload still carries it. Tests below preserved bit-for-bit.
# ---------------------------------------------------------------------------


def _make_http_engine() -> LLMEngine:
    eng = LLMEngine.__new__(LLMEngine)
    eng._runtime = "http_server"
    eng._http_base_url = "http://localhost:9999/v1"
    eng._http_api_key = "test-key"
    eng._http_model_alias = "qwen-test"
    eng._http_timeout = 5.0
    eng._cancel = __import__("threading").Event()
    eng._history = __import__("collections").deque()
    eng._memory = None
    eng._history_turns = 6
    eng._system_prompt = "test"
    eng._build_messages = lambda u, **kwargs: [
        {"role": "system", "content": "test"},
        {"role": "user", "content": u},
    ]
    eng._record_turn = MagicMock()
    return eng


def test_http_payload_includes_enable_thinking_false() -> None:
    eng = _make_http_engine()
    captured: dict[str, Any] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }
        resp.raise_for_status = MagicMock()
        return resp

    with patch("kenning.llm.inference.get_config") as gc, \
         patch("requests.post", side_effect=fake_post):
        gc.return_value.llm = _LLMCfg()
        eng.generate("hello", enable_thinking=False)
    assert captured["payload"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_http_payload_omits_when_default() -> None:
    eng = _make_http_engine()
    captured: dict[str, Any] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }
        resp.raise_for_status = MagicMock()
        return resp

    with patch("kenning.llm.inference.get_config") as gc, \
         patch("requests.post", side_effect=fake_post):
        gc.return_value.llm = _LLMCfg()
        eng.generate("hello")
    assert "chat_template_kwargs" not in captured["payload"]
