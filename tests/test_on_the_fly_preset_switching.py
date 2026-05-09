"""4B optimization plan — tests for the on-the-fly preset-switching
infrastructure: ULTRON_LLM_PRESET env var, preset-aware check_vram.py,
and swap_llm_preset.py rewriter.

The goal: switching the active LLM should be a single action — one env
var, one config-file line, or one CLI command — not a multi-line YAML
edit. These tests lock down each path.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ultron.config import load_config


# ---------------------------------------------------------------------------
# ULTRON_LLM_PRESET env var override
# ---------------------------------------------------------------------------


def _write_yaml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_env_var_overrides_yaml_preset(tmp_path: Path) -> None:
    """ULTRON_LLM_PRESET=qwen3.5-4b on a YAML pinned to 9b ⇒ 4b wins."""
    cfg_path = _write_yaml(tmp_path, """
version: "1.0"
llm:
  preset: "qwen3.5-9b"
""")
    with patch.dict(os.environ, {"ULTRON_LLM_PRESET": "qwen3.5-4b"}, clear=False):
        cfg = load_config(cfg_path)
    assert cfg.llm.preset == "qwen3.5-4b"
    assert cfg.llm.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"
    assert cfg.llm.n_ctx == 16384
    assert cfg.llm.draft_model_path == "models/Qwen3.5-0.8B-Q4_K_M.gguf"


def test_env_var_clears_yaml_overrides_by_default(tmp_path: Path) -> None:
    """When YAML pins explicit model_path/n_ctx and the env var picks a
    different preset, the YAML overrides are CLEARED so the preset
    table wins. This is what makes the env var a true one-shot
    switch."""
    cfg_path = _write_yaml(tmp_path, """
version: "1.0"
llm:
  preset: "qwen3.5-9b"
  model_path: "models/Qwen3.5-9B-Q4_K_M.gguf"
  n_ctx: 8192
""")
    with patch.dict(os.environ, {"ULTRON_LLM_PRESET": "qwen3.5-4b"}, clear=False):
        cfg = load_config(cfg_path)
    assert cfg.llm.preset == "qwen3.5-4b"
    assert cfg.llm.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"  # preset wins
    assert cfg.llm.n_ctx == 16384


def test_env_var_keep_overrides_flag(tmp_path: Path) -> None:
    """ULTRON_LLM_PRESET_KEEP_OVERRIDES=1 lets explicit YAML values
    survive the env-var preset switch (advanced/debug use)."""
    cfg_path = _write_yaml(tmp_path, """
version: "1.0"
llm:
  preset: "qwen3.5-9b"
  model_path: "/tmp/my-custom.gguf"
  n_ctx: 4096
""")
    env = {
        "ULTRON_LLM_PRESET": "qwen3.5-4b",
        "ULTRON_LLM_PRESET_KEEP_OVERRIDES": "1",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = load_config(cfg_path)
    assert cfg.llm.preset == "qwen3.5-4b"
    # YAML overrides preserved
    assert cfg.llm.model_path == "/tmp/my-custom.gguf"
    assert cfg.llm.n_ctx == 4096


def test_env_var_unset_uses_yaml_preset(tmp_path: Path) -> None:
    """No env var ⇒ YAML preset wins (back-compat)."""
    cfg_path = _write_yaml(tmp_path, """
version: "1.0"
llm:
  preset: "qwen3.5-4b"
""")
    # Ensure env var is absent
    env_clean = {k: v for k, v in os.environ.items() if k != "ULTRON_LLM_PRESET"}
    with patch.dict(os.environ, env_clean, clear=True):
        cfg = load_config(cfg_path)
    assert cfg.llm.preset == "qwen3.5-4b"


def test_minimal_yaml_with_just_preset(tmp_path: Path) -> None:
    """A YAML config that ONLY specifies preset (no model_path,
    n_ctx, draft_model_path) must produce a complete, valid config —
    that's the on-the-fly switch's foundation. Stage A's
    _apply_preset validator does the heavy lifting."""
    cfg_path = _write_yaml(tmp_path, """
version: "1.0"
llm:
  preset: "qwen3.5-4b"
""")
    cfg = load_config(cfg_path)
    assert cfg.llm.model_path == "models/Qwen3.5-4B-Q4_K_M.gguf"
    assert cfg.llm.n_ctx == 16384
    assert cfg.llm.draft_model_path == "models/Qwen3.5-0.8B-Q4_K_M.gguf"


# ---------------------------------------------------------------------------
# check_vram.py — preset-aware target
# ---------------------------------------------------------------------------


_CHECK_VRAM_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "check_vram.py"
)


def _load_check_vram():
    spec = importlib.util.spec_from_file_location("check_vram", _CHECK_VRAM_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def check_vram():
    return _load_check_vram()


def test_check_vram_target_table(check_vram) -> None:
    assert check_vram.TARGET_MB_BY_PRESET["qwen3.5-9b"] == 9216
    assert check_vram.TARGET_MB_BY_PRESET["qwen3.5-4b"] == 6700
    assert check_vram.DEFAULT_TARGET_MB == 9216


def test_check_vram_explicit_preset_override_4b(check_vram) -> None:
    target, label = check_vram._resolve_target_mb("qwen3.5-4b")
    assert target == 6700
    assert label == "qwen3.5-4b"


def test_check_vram_explicit_preset_override_9b(check_vram) -> None:
    target, label = check_vram._resolve_target_mb("qwen3.5-9b")
    assert target == 9216
    assert label == "qwen3.5-9b"


def test_check_vram_unknown_preset_falls_back_to_default(check_vram) -> None:
    target, label = check_vram._resolve_target_mb("definitely-not-a-preset")
    assert target == 9216
    assert label == "definitely-not-a-preset"


def test_check_vram_env_var_picks_target(check_vram) -> None:
    with patch.dict(os.environ, {"ULTRON_LLM_PRESET": "qwen3.5-4b"}, clear=False):
        target, label = check_vram._resolve_target_mb(None)
    assert target == 6700
    assert label == "qwen3.5-4b"


def test_format_line_includes_preset_label(check_vram) -> None:
    line = check_vram._format_line(7000, 12000, target_mb=6700, preset_label="qwen3.5-4b")
    assert "target 6700 MB (qwen3.5-4b)" in line
    assert "above target" in line  # 7000 > 6700


def test_format_line_under_target_says_ok(check_vram) -> None:
    line = check_vram._format_line(5000, 12000, target_mb=6700, preset_label="qwen3.5-4b")
    assert "[OK]" in line


# ---------------------------------------------------------------------------
# scripts/swap_llm_preset.py — rewrite logic
# ---------------------------------------------------------------------------


_SWAP_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "swap_llm_preset.py"
)


def _load_swap():
    spec = importlib.util.spec_from_file_location("swap_llm_preset", _SWAP_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def swap():
    return _load_swap()


def test_rewrite_preset_basic(swap) -> None:
    text = """
llm:
  preset: "qwen3.5-9b"
  n_ctx: 8192
"""
    new_text, old = swap._rewrite_preset(text, "qwen3.5-4b")
    assert old == "qwen3.5-9b"
    assert 'preset: "qwen3.5-4b"' in new_text
    assert 'preset: "qwen3.5-9b"' not in new_text
    # n_ctx line preserved
    assert "n_ctx: 8192" in new_text


def test_rewrite_preset_preserves_inline_comment(swap) -> None:
    text = '  preset: "qwen3.5-9b"  # current default\n'
    new_text, old = swap._rewrite_preset(text, "qwen3.5-4b")
    assert old == "qwen3.5-9b"
    assert 'preset: "qwen3.5-4b"' in new_text
    assert "# current default" in new_text


def test_rewrite_preset_only_first_match(swap) -> None:
    """If something else further down also has 'preset:' (e.g. a
    plugin block), only the first occurrence is rewritten. The user
    can re-run for additional matches if needed."""
    text = """
llm:
  preset: "qwen3.5-9b"
plugins:
  preset: "ignore-me"
"""
    new_text, old = swap._rewrite_preset(text, "qwen3.5-4b")
    assert old == "qwen3.5-9b"
    assert 'preset: "qwen3.5-4b"' in new_text
    # Second occurrence untouched
    assert 'preset: "ignore-me"' in new_text


def test_rewrite_preset_missing_raises(swap) -> None:
    text = "version: \"1.0\"\nfoo: bar\n"
    with pytest.raises(ValueError):
        swap._rewrite_preset(text, "qwen3.5-4b")
