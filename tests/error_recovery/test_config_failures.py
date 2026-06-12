"""Configuration loader failure modes.

Validates that load_config raises typed ConfigurationError (subclass of
KenningError, NOT a generic ValueError or FileNotFoundError) for:
  - missing file
  - invalid YAML
  - schema validation failure (unknown key, wrong type, out-of-range)
  - environment-variable reference that resolves empty (acceptable; doesn't raise)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kenning.config import load_config
from kenning.errors import ConfigurationError


def _good_yaml() -> str:
    return "version: '1.0'\n"


def test_missing_file_raises_typed_configuration_error(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ConfigurationError) as excinfo:
        load_config(missing)
    assert "not found" in excinfo.value.message
    assert excinfo.value.context.get("path") == str(missing)


def test_invalid_yaml_raises_typed_configuration_error(tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("version: '1.0'\nthis is: : not valid yaml\n  - mismatch", encoding="utf-8")
    with pytest.raises(ConfigurationError) as excinfo:
        load_config(bad)
    assert "not valid YAML" in excinfo.value.message


def test_unknown_top_level_key_raises_typed_configuration_error(tmp_path):
    """`extra='forbid'` on the schema turns unknown keys into typed errors."""
    bad = tmp_path / "config.yaml"
    bad.write_text(
        "version: '1.0'\nthis_key_is_not_in_schema: 42\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError) as excinfo:
        load_config(bad)
    assert "validation failed" in excinfo.value.message


def test_out_of_range_value_raises_typed_configuration_error(tmp_path):
    """`vad.threshold` is bounded [0.0, 1.0]. A value of 5.0 must be rejected."""
    bad = tmp_path / "config.yaml"
    bad.write_text(
        "version: '1.0'\n"
        "vad:\n"
        "  threshold: 5.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError) as excinfo:
        load_config(bad)
    assert "validation failed" in excinfo.value.message


def test_env_var_reference_with_unset_variable_resolves_empty(tmp_path):
    """${UNSET_VAR_XYZ123} references DO NOT raise — they resolve to empty
    string. Consuming subsystems handle empty values explicitly (e.g. Brave
    raises a clear error when API key is empty).

    Note: only uppercase env-var names are recognized by the substitution
    regex, matching POSIX convention."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "version: '1.0'\n"
        "coding:\n"
        "  claude_cli: '${UNSET_VAR_XYZ123}/claude.cmd'\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    # The reference resolved to empty string; the rest of the path stayed.
    assert cfg.coding.claude_cli == "/claude.cmd"


def test_load_config_accepts_explicit_path_arg(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(_good_yaml(), encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.version == "1.0"


def test_configuration_error_carries_path_in_context(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("not: valid: : :\n  - here", encoding="utf-8")
    with pytest.raises(ConfigurationError) as excinfo:
        load_config(cfg_path)
    assert excinfo.value.context.get("path") == str(cfg_path)
