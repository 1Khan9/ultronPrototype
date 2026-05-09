"""4B optimization plan Stage A — preset resolution tests.

Verifies ``LLMConfig.preset`` behaviour:
- Default preset ``qwen3.5-9b`` resolves to today's exact config
  (back-compat — every existing test must keep passing).
- ``qwen3.5-4b`` resolves to the 4B GGUF + 0.8B draft + n_ctx=8192.
  (n_ctx pinned to match the 9B-era voice-path TTFT baseline; users
  who want a larger context override n_ctx explicitly in YAML.)
- ``custom`` does not touch any field; raw user values pass through.
- Explicit user fields always win over preset defaults (mixed mode).

These tests construct ``LLMConfig`` directly and load YAML fragments
through ``load_config``, so they cover both call paths.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ultron.config import LLM_PRESETS, LLMConfig, load_config


def test_default_preset_is_9b() -> None:
    cfg = LLMConfig()
    assert cfg.preset == "qwen3.5-9b"
    assert cfg.model_path == "models/Qwen3.5-9B-Q4_K_M.gguf"
    assert cfg.n_ctx == 8192
    assert cfg.draft_model_path is None


def test_4b_preset_resolves_paths_and_ctx() -> None:
    cfg = LLMConfig(preset="qwen3.5-4b")
    assert cfg.preset == "qwen3.5-4b"
    assert cfg.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"
    assert cfg.n_ctx == 8192
    assert cfg.draft_model_path == "models/Qwen3.5-0.8B-Q4_K_M.gguf"


def test_custom_preset_passes_through_raw_fields() -> None:
    cfg = LLMConfig(
        preset="custom",
        model_path="models/some-other.gguf",
        n_ctx=4096,
        draft_model_path=None,
    )
    assert cfg.preset == "custom"
    assert cfg.model_path == "models/some-other.gguf"
    assert cfg.n_ctx == 4096
    assert cfg.draft_model_path is None


def test_explicit_model_path_overrides_4b_preset() -> None:
    """Mixed mode — preset gives n_ctx + draft, user pins model_path."""
    cfg = LLMConfig(preset="qwen3.5-4b", model_path="models/custom-4b.gguf")
    assert cfg.model_path == "models/custom-4b.gguf"  # user wins
    assert cfg.n_ctx == 8192  # preset still applies to non-overridden
    assert cfg.draft_model_path == "models/Qwen3.5-0.8B-Q4_K_M.gguf"


def test_explicit_n_ctx_overrides_preset() -> None:
    cfg = LLMConfig(preset="qwen3.5-4b", n_ctx=8192)
    assert cfg.n_ctx == 8192
    assert cfg.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"  # preset still applies


def test_explicit_draft_model_path_overrides_preset() -> None:
    cfg = LLMConfig(preset="qwen3.5-4b", draft_model_path=None)
    assert cfg.draft_model_path is None  # explicit None wins
    assert cfg.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"


def test_9b_preset_does_not_set_draft() -> None:
    """9B explicitly has draft_model_path=None — switching from 4B back to
    9B in the same process must not retain a stale draft path."""
    cfg = LLMConfig(preset="qwen3.5-9b")
    assert cfg.draft_model_path is None


def test_custom_preset_with_default_model_path_is_legal() -> None:
    """custom preset doesn't auto-resolve, but the field has a default
    ('models/Qwen3.5-9B-Q4_K_M.gguf'), so this is allowed."""
    cfg = LLMConfig(preset="custom")
    assert cfg.preset == "custom"
    assert cfg.model_path == "models/Qwen3.5-9B-Q4_K_M.gguf"


def test_preset_table_contents() -> None:
    """The preset table is the contract that the launcher + 4B plan
    docs depend on. Lock it down."""
    assert set(LLM_PRESETS.keys()) == {"qwen3.5-9b", "qwen3.5-4b"}
    nine = LLM_PRESETS["qwen3.5-9b"]
    four = LLM_PRESETS["qwen3.5-4b"]
    assert nine["model_path"].endswith("Qwen3.5-9B-Q4_K_M.gguf")
    assert nine["draft_model_path"] is None
    assert nine["n_ctx"] == 8192
    assert four["model_path"].endswith("Qwen3.5-4B-Q4_K_M.gguf")
    assert four["draft_model_path"].endswith("Qwen3.5-0.8B-Q4_K_M.gguf")
    assert four["n_ctx"] == 8192


def test_yaml_load_with_4b_preset(tmp_path: Path) -> None:
    """End-to-end: YAML config with preset key loads cleanly through
    the real loader and resolves the same way."""
    yaml_text = """
version: "1.0"
llm:
  preset: "qwen3.5-4b"
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.llm.preset == "qwen3.5-4b"
    assert cfg.llm.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"
    assert cfg.llm.n_ctx == 8192
    assert cfg.llm.draft_model_path == "models/Qwen3.5-0.8B-Q4_K_M.gguf"


def test_yaml_load_default_preset_back_compat(tmp_path: Path) -> None:
    """A YAML config that doesn't mention preset at all must produce
    the legacy 9B configuration (key back-compat guarantee)."""
    yaml_text = """
version: "1.0"
llm:
  n_ctx: 8192
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.llm.preset == "qwen3.5-9b"
    assert cfg.llm.model_path == "models/Qwen3.5-9B-Q4_K_M.gguf"
    assert cfg.llm.n_ctx == 8192
    assert cfg.llm.draft_model_path is None


def test_yaml_load_custom_preset_with_explicit_paths(tmp_path: Path) -> None:
    yaml_text = """
version: "1.0"
llm:
  preset: "custom"
  model_path: "models/something-bespoke.gguf"
  n_ctx: 4096
  draft_model_path: "models/tiny-draft.gguf"
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.llm.preset == "custom"
    assert cfg.llm.model_path == "models/something-bespoke.gguf"
    assert cfg.llm.n_ctx == 4096
    assert cfg.llm.draft_model_path == "models/tiny-draft.gguf"


def test_invalid_preset_rejected() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        LLMConfig(preset="qwen2-7b")  # not in Literal
