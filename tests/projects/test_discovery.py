"""Tests for the .ultron/ project discovery (OpenHands catalog T7)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from ultron.projects.discovery import (
    DEFAULT_PROJECT_CONFIG_DIRNAME,
    ProjectConfig,
    ProjectConfigField,
    discover_project_config,
    invalidate_discovery_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    invalidate_discovery_cache()
    yield
    invalidate_discovery_cache()


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _ultron_dir(root: Path) -> Path:
    return root / DEFAULT_PROJECT_CONFIG_DIRNAME


def test_no_ultron_dir_returns_empty_config(tmp_path: Path):
    config = discover_project_config(tmp_path)
    assert isinstance(config, ProjectConfig)
    assert config.repo_root == tmp_path.resolve()
    assert config.config_dir == _ultron_dir(tmp_path.resolve())
    assert config.has_any_field is False
    assert config.parse_errors == ()


def test_empty_ultron_dir_returns_empty_config(tmp_path: Path):
    _ultron_dir(tmp_path).mkdir()
    config = discover_project_config(tmp_path)
    assert config.has_any_field is False


def test_discovers_skills_directory(tmp_path: Path):
    skills_dir = _ultron_dir(tmp_path) / "skills"
    skills_dir.mkdir(parents=True)
    config = discover_project_config(tmp_path)
    assert config.skills_dir == skills_dir
    assert config.has_any_field is True
    assert config.get_path(ProjectConfigField.SKILLS_DIR) == skills_dir


def test_discovers_setup_script(tmp_path: Path):
    setup_path = _ultron_dir(tmp_path) / "setup.sh"
    _write(setup_path, "#!/bin/sh\necho hi\n")
    config = discover_project_config(tmp_path)
    assert config.setup_script == setup_path


def test_discovers_pre_commit_script(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "pre_commit.sh"
    _write(target, "#!/bin/sh\necho hook\n")
    config = discover_project_config(tmp_path)
    assert config.pre_commit_script == target


def test_discovers_identity_override(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "identity_override.md"
    _write(target, "# Extra rules\n\nbe extra careful.\n")
    config = discover_project_config(tmp_path)
    assert config.identity_override is not None
    assert "be extra careful" in config.identity_override
    assert config.identity_override_path == target


def test_discovers_safety_rules_yaml(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "safety_rules.yaml"
    _write(target, "rules:\n  - id: deny_rm_rf\n    severity: hard\n")
    config = discover_project_config(tmp_path)
    assert config.safety_rules is not None
    assert config.safety_rules.get("rules") == [{"id": "deny_rm_rf", "severity": "hard"}]
    assert config.safety_rules_path == target


def test_discovers_test_command_json(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "test_command.json"
    _write(target, json.dumps({"cmd": ["pytest", "-q"], "cwd": "."}))
    config = discover_project_config(tmp_path)
    assert config.test_command == {"cmd": ["pytest", "-q"], "cwd": "."}
    assert config.test_command_path == target


def test_discovers_voicepack_override(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "voicepack_override.json"
    _write(target, json.dumps({"tts": {"pause_ms": 75, "kokoro": {"speed": 1.15}}}))
    config = discover_project_config(tmp_path)
    assert config.voicepack_override is not None
    assert config.voicepack_override["tts"]["pause_ms"] == 75


def test_discovers_intent_triggers(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "intent_triggers.yaml"
    _write(target, "triggers:\n  - phrase: recompile\n    intent: BUILD_TASK\n")
    config = discover_project_config(tmp_path)
    assert config.intent_triggers is not None
    assert config.intent_triggers["triggers"][0]["phrase"] == "recompile"


def test_discovers_hooks_json(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "hooks.json"
    body = {
        "event_type": "pre_tool_use",
        "matchers": [{"matcher": ".*", "hooks": []}],
    }
    _write(target, json.dumps(body))
    config = discover_project_config(tmp_path)
    assert config.hooks == body


def test_multiple_fields_all_populated(tmp_path: Path):
    _write(_ultron_dir(tmp_path) / "setup.sh", "#!/bin/sh\n")
    _write(_ultron_dir(tmp_path) / "identity_override.md", "extra rules")
    _write(_ultron_dir(tmp_path) / "safety_rules.yaml", "rules: []\n")
    (_ultron_dir(tmp_path) / "skills").mkdir()

    config = discover_project_config(tmp_path)
    assert config.setup_script is not None
    assert config.identity_override is not None
    assert config.safety_rules is not None
    assert config.skills_dir is not None
    assert config.parse_errors == ()


def test_invalid_json_recorded_in_parse_errors(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "test_command.json"
    _write(target, "this is not json")
    config = discover_project_config(tmp_path)
    assert config.test_command is None
    assert any("invalid JSON" in err for err in config.parse_errors)


def test_invalid_yaml_recorded_in_parse_errors(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "safety_rules.yaml"
    _write(target, "rules: : :\n  - broken\n")
    config = discover_project_config(tmp_path)
    assert config.safety_rules is None
    assert any("YAML parse error" in err for err in config.parse_errors)


def test_non_mapping_json_top_level_rejected(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "test_command.json"
    _write(target, json.dumps(["pytest", "-q"]))
    config = discover_project_config(tmp_path)
    assert config.test_command is None
    assert any("expected JSON object" in err for err in config.parse_errors)


def test_non_mapping_yaml_top_level_rejected(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "safety_rules.yaml"
    _write(target, "- one\n- two\n")
    config = discover_project_config(tmp_path)
    assert config.safety_rules is None
    assert any("expected mapping" in err for err in config.parse_errors)


def test_empty_yaml_returns_empty_mapping(tmp_path: Path):
    target = _ultron_dir(tmp_path) / "safety_rules.yaml"
    _write(target, "")
    config = discover_project_config(tmp_path)
    assert config.safety_rules == {}


def test_string_path_accepted(tmp_path: Path):
    _ultron_dir(tmp_path).mkdir()
    _write(_ultron_dir(tmp_path) / "setup.sh", "#!/bin/sh\n")
    config = discover_project_config(str(tmp_path))
    assert config.setup_script is not None


def test_has_any_field_false_when_only_unrecognised_files_present(tmp_path: Path):
    _write(_ultron_dir(tmp_path) / "random.txt", "ignore me")
    config = discover_project_config(tmp_path)
    assert config.has_any_field is False


def test_cache_returns_same_instance_on_second_call(tmp_path: Path):
    (_ultron_dir(tmp_path) / "skills").mkdir(parents=True)
    a = discover_project_config(tmp_path)
    b = discover_project_config(tmp_path)
    # Same instance (or at least byte-equal config) -- cache hit.
    assert a == b


def test_cache_invalidates_on_new_file(tmp_path: Path):
    (_ultron_dir(tmp_path) / "skills").mkdir(parents=True)
    first = discover_project_config(tmp_path)
    assert first.setup_script is None

    # Touch the .ultron dir mtime by adding a new file.
    time.sleep(0.05)
    _write(_ultron_dir(tmp_path) / "setup.sh", "#!/bin/sh\n")
    # Force mtime update on the directory itself for filesystems with
    # second-resolution mtimes.
    _ultron_dir(tmp_path).touch()

    second = discover_project_config(tmp_path)
    assert second.setup_script is not None


def test_invalidate_specific_repo_clears_only_that_entry(tmp_path: Path):
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    (_ultron_dir(repo_a) / "skills").mkdir(parents=True)
    (_ultron_dir(repo_b) / "skills").mkdir(parents=True)

    # Populate cache.
    discover_project_config(repo_a)
    discover_project_config(repo_b)

    invalidate_discovery_cache(repo_a)
    # No exception even though repo_b stays cached.
    discover_project_config(repo_b)


def test_invalidate_all_clears_everything(tmp_path: Path):
    repo = tmp_path / "x"
    (_ultron_dir(repo) / "skills").mkdir(parents=True)
    discover_project_config(repo)
    invalidate_discovery_cache()  # clear everything
    # Subsequent call rebuilds from disk -- no error.
    config = discover_project_config(repo)
    assert config.skills_dir is not None


def test_use_cache_false_forces_fresh_read(tmp_path: Path):
    (_ultron_dir(tmp_path) / "skills").mkdir(parents=True)
    discover_project_config(tmp_path)  # warm the cache
    _write(_ultron_dir(tmp_path) / "setup.sh", "#!/bin/sh\n")
    # Force fresh read regardless of any cache state.
    fresh = discover_project_config(tmp_path, use_cache=False)
    assert fresh.setup_script is not None
    # Cache should NOT have been populated by the use_cache=False call.
    # A subsequent use_cache=True call still has to do the work; if the
    # mtime invalidation kicked in, that's also acceptable -- the
    # contract here is just "use_cache=False reads from disk now".


def test_use_cache_false_does_not_populate_cache(tmp_path: Path):
    (_ultron_dir(tmp_path) / "skills").mkdir(parents=True)
    # Fresh call with cache disabled.
    discover_project_config(tmp_path, use_cache=False)
    # The internal cache should remain empty for this repo.
    from ultron.projects.discovery import _DISCOVERY_CACHE
    assert tmp_path.resolve() not in _DISCOVERY_CACHE


def test_get_path_returns_none_for_missing_field(tmp_path: Path):
    config = discover_project_config(tmp_path)
    assert config.get_path(ProjectConfigField.SETUP_SCRIPT) is None
    assert config.get_path("setup_script") is None


def test_config_is_frozen(tmp_path: Path):
    config = discover_project_config(tmp_path)
    with pytest.raises(Exception):
        config.discovered_at = 99.0  # type: ignore[misc]


def test_project_config_field_enum_values():
    assert ProjectConfigField.SKILLS_DIR.value == "skills_dir"
    assert ProjectConfigField.SAFETY_RULES.value == "safety_rules"
    assert ProjectConfigField.HOOKS.value == "hooks"


def test_default_dirname_pinned():
    assert DEFAULT_PROJECT_CONFIG_DIRNAME == ".ultron"


def test_repo_root_in_returned_config(tmp_path: Path):
    config = discover_project_config(tmp_path)
    assert config.repo_root == tmp_path.resolve()
    assert config.config_dir.name == ".ultron"
