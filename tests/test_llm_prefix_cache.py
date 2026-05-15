"""Schema + plumbing tests for the LLM prefix KV cache config knob.

2026-05-16 latency pass 2: added ``prefix_cache_ram_bytes`` to
``LLMConfig``. When > 0, ``_build_llama`` attaches a
``LlamaRAMCache(capacity_bytes=prefix_cache_ram_bytes)`` so completed
session KV state is stored in host RAM keyed by the longest-common-
prefix of the token sequence. Subsequent calls with a shared prefix
(every voice turn -- the stable system prompt + prior turns) restore
the cached state instead of re-evaluating those tokens.

These tests verify the schema, the round-trip, the wiring into
``_build_llama``, and the fail-open contract when ``LlamaRAMCache``
isn't importable.

No real GGUF load happens here -- ``Llama`` and ``LlamaRAMCache`` are
mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ultron.config import LLMConfig, UltronConfig


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_prefix_cache_ram_bytes_default_is_zero():
    """Default 0 (disabled) after live bench showed ~15 ms TTFT
    regression vs cache-off on the production 4B model. The knob
    stays in place for operators whose workload benefits."""
    cfg = LLMConfig(model_path="x.gguf", preset="custom")
    assert cfg.prefix_cache_ram_bytes == 0


def test_prefix_cache_ram_bytes_accepts_zero_to_disable():
    """0 = legacy re-eval behaviour. Explicit opt-out for operators
    who want to A/B against the legacy path."""
    cfg = LLMConfig(
        model_path="x.gguf", preset="custom",
        prefix_cache_ram_bytes=0,
    )
    assert cfg.prefix_cache_ram_bytes == 0


def test_prefix_cache_ram_bytes_accepts_large_value():
    cfg = LLMConfig(
        model_path="x.gguf", preset="custom",
        prefix_cache_ram_bytes=4 * 1024 * 1024 * 1024,
    )
    assert cfg.prefix_cache_ram_bytes == 4 * 1024 * 1024 * 1024


def test_prefix_cache_ram_bytes_rejects_negative():
    """Negative bytes don't make sense; reject at schema validation."""
    with pytest.raises(Exception):
        LLMConfig(
            model_path="x.gguf", preset="custom",
            prefix_cache_ram_bytes=-1,
        )


def test_prefix_cache_ram_bytes_round_trip():
    cfg = LLMConfig(
        model_path="x.gguf", preset="custom",
        prefix_cache_ram_bytes=512 * 1024 * 1024,
    )
    cfg2 = LLMConfig.model_validate(cfg.model_dump())
    assert cfg2.prefix_cache_ram_bytes == 512 * 1024 * 1024


# ---------------------------------------------------------------------------
# _build_llama wiring
# ---------------------------------------------------------------------------


def _stub_engine_for_build_llama() -> object:
    """Build a partial LLMEngine skeleton just for _build_llama call."""
    from ultron.llm.inference import LLMEngine
    eng = object.__new__(LLMEngine)
    eng._memory = None
    return eng


def _stub_cfg(*, prefix_cache_ram_bytes=2 * 1024 * 1024 * 1024) -> object:
    """Build a minimal cfg-like object for _build_llama."""
    return SimpleNamespace(
        flash_attn=True,
        kv_cache_type=8,
        gpu_layers=-1,
        n_ctx=8192,
        model_path="dummy.gguf",
        n_batch=None,
        n_ubatch=None,
        prefix_cache_ram_bytes=prefix_cache_ram_bytes,
    )


def test_build_llama_attaches_ram_cache_when_enabled(tmp_path, monkeypatch):
    """The default path (prefix_cache_ram_bytes > 0) should attach a
    LlamaRAMCache with the configured capacity to the constructed
    Llama instance."""
    gguf = tmp_path / "fake.gguf"
    gguf.write_bytes(b"dummy")
    mock_llama_instance = MagicMock()
    mock_llama_cls = MagicMock(return_value=mock_llama_instance)
    monkeypatch.setattr("llama_cpp.Llama", mock_llama_cls)
    mock_cache_cls = MagicMock()
    mock_cache_instance = MagicMock()
    mock_cache_cls.return_value = mock_cache_instance
    monkeypatch.setattr("llama_cpp.LlamaRAMCache", mock_cache_cls)

    eng = _stub_engine_for_build_llama()
    cfg = _stub_cfg(prefix_cache_ram_bytes=1 * 1024 * 1024 * 1024)
    eng._build_llama(cfg, gguf, 4096, -1)

    mock_cache_cls.assert_called_once_with(capacity_bytes=1 * 1024 * 1024 * 1024)
    mock_llama_instance.set_cache.assert_called_once_with(mock_cache_instance)


def test_build_llama_skips_ram_cache_when_zero(tmp_path, monkeypatch):
    """prefix_cache_ram_bytes=0 disables the cache: no LlamaRAMCache
    constructed, no set_cache call on the Llama instance."""
    gguf = tmp_path / "fake.gguf"
    gguf.write_bytes(b"dummy")
    mock_llama_instance = MagicMock()
    mock_llama_cls = MagicMock(return_value=mock_llama_instance)
    monkeypatch.setattr("llama_cpp.Llama", mock_llama_cls)
    mock_cache_cls = MagicMock()
    monkeypatch.setattr("llama_cpp.LlamaRAMCache", mock_cache_cls)

    eng = _stub_engine_for_build_llama()
    cfg = _stub_cfg(prefix_cache_ram_bytes=0)
    eng._build_llama(cfg, gguf, 4096, -1)

    mock_cache_cls.assert_not_called()
    mock_llama_instance.set_cache.assert_not_called()


def test_build_llama_fails_open_on_cache_import_error(tmp_path, monkeypatch):
    """Older llama-cpp-python builds without LlamaRAMCache must NOT
    crash the engine. The Llama instance is still constructed; only
    the cache attach is skipped."""
    gguf = tmp_path / "fake.gguf"
    gguf.write_bytes(b"dummy")
    mock_llama_instance = MagicMock()
    mock_llama_cls = MagicMock(return_value=mock_llama_instance)
    monkeypatch.setattr("llama_cpp.Llama", mock_llama_cls)

    # Force the LlamaRAMCache import to raise inside _build_llama.
    import llama_cpp
    monkeypatch.delattr(llama_cpp, "LlamaRAMCache", raising=False)

    eng = _stub_engine_for_build_llama()
    cfg = _stub_cfg(prefix_cache_ram_bytes=1024)
    # Must not raise.
    llama, _ = eng._build_llama(cfg, gguf, 4096, -1)
    assert llama is mock_llama_instance
    # set_cache was never called because import failed.
    mock_llama_instance.set_cache.assert_not_called()


def test_build_llama_fails_open_on_set_cache_error(tmp_path, monkeypatch):
    """set_cache itself raising (transient runtime issue) must not
    crash construction. The engine returns the Llama instance
    unconfigured for caching; legacy re-eval behaviour applies."""
    gguf = tmp_path / "fake.gguf"
    gguf.write_bytes(b"dummy")
    mock_llama_instance = MagicMock()
    mock_llama_instance.set_cache.side_effect = RuntimeError("attach failed")
    mock_llama_cls = MagicMock(return_value=mock_llama_instance)
    monkeypatch.setattr("llama_cpp.Llama", mock_llama_cls)
    mock_cache_cls = MagicMock()
    monkeypatch.setattr("llama_cpp.LlamaRAMCache", mock_cache_cls)

    eng = _stub_engine_for_build_llama()
    cfg = _stub_cfg(prefix_cache_ram_bytes=1024)
    llama, _ = eng._build_llama(cfg, gguf, 4096, -1)
    assert llama is mock_llama_instance


# ---------------------------------------------------------------------------
# Top-level UltronConfig round-trip
# ---------------------------------------------------------------------------


def test_full_config_default_keeps_prefix_cache_at_zero():
    cfg = UltronConfig()
    assert cfg.llm.prefix_cache_ram_bytes == 0


def test_full_config_accepts_prefix_cache_override():
    cfg = UltronConfig.model_validate({
        "llm": {"preset": "custom", "model_path": "x.gguf",
                "prefix_cache_ram_bytes": 2 * 1024 * 1024 * 1024},
    })
    assert cfg.llm.prefix_cache_ram_bytes == 2 * 1024 * 1024 * 1024
