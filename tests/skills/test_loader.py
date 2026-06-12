"""Tests for the skill loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.skills.loader import (
    SkillLoadStats,
    load_skill_from_path,
    load_skills_from_directory,
)
from kenning.skills.models import (
    KeywordTrigger,
    SkillSource,
    SkillType,
    TaskTrigger,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_load_skill_keyword_trigger(tmp_path: Path):
    target = tmp_path / "gaming.md"
    _write(
        target,
        "---\nname: gaming\ntype: knowledge\ntriggers:\n  - valorant\n  - csgo\n---\nBody for gaming.",
    )
    skill = load_skill_from_path(target, source=SkillSource.PUBLIC)
    assert skill is not None
    assert skill.name == "gaming"
    assert skill.type == SkillType.KNOWLEDGE
    assert isinstance(skill.trigger, KeywordTrigger)
    assert skill.trigger.keywords == ("valorant", "csgo")
    assert skill.source == SkillSource.PUBLIC
    assert skill.content.strip() == "Body for gaming."


def test_load_skill_task_trigger(tmp_path: Path):
    target = tmp_path / "onboard.md"
    _write(
        target,
        "---\nname: onboard\ntype: task\ntriggers:\n  - /onboard\n---\nOnboarding instructions.",
    )
    skill = load_skill_from_path(target, source=SkillSource.PUBLIC)
    assert skill is not None
    assert skill.type == SkillType.TASK
    assert isinstance(skill.trigger, TaskTrigger)
    assert skill.trigger.commands == ("/onboard",)


def test_load_skill_always_on_when_no_triggers(tmp_path: Path):
    target = tmp_path / "core.md"
    _write(
        target,
        "---\nname: core\n---\nAlways injected.",
    )
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.trigger is None
    assert skill.is_always_on is True
    assert skill.type == SkillType.ALWAYS_ON


def test_load_skill_filename_stem_fallback(tmp_path: Path):
    target = tmp_path / "filename-fallback.md"
    _write(target, "No frontmatter here, just body text.")
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.name == "filename-fallback"
    assert skill.is_always_on is True


def test_load_skill_missing_name_uses_stem(tmp_path: Path):
    target = tmp_path / "namedfile.md"
    _write(target, "---\ntype: knowledge\n---\nBody")
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.name == "namedfile"


def test_load_skill_mixed_triggers_becomes_task(tmp_path: Path):
    """Catalog convention: any /-prefixed trigger flips the whole list to task."""

    target = tmp_path / "mixed.md"
    _write(
        target,
        "---\nname: mixed\ntriggers:\n  - normal\n  - /slash\n---\nBody",
    )
    skill = load_skill_from_path(target)
    assert skill is not None
    assert isinstance(skill.trigger, TaskTrigger)


def test_load_skill_non_list_triggers_treated_as_always_on(tmp_path: Path):
    target = tmp_path / "bad.md"
    _write(
        target,
        "---\nname: bad\ntriggers: 42\n---\nBody",
    )
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.trigger is None


def test_load_skill_min_user_text_chars_override(tmp_path: Path):
    target = tmp_path / "with_min.md"
    _write(
        target,
        "---\nname: with_min\nmin_user_text_chars: 12\ntriggers:\n  - ssh\n---\nBody",
    )
    skill = load_skill_from_path(target, default_min_user_text_chars=4)
    assert skill is not None
    assert isinstance(skill.trigger, KeywordTrigger)
    assert skill.trigger.min_user_text_chars == 12


def test_load_skill_uses_default_min_user_text_chars(tmp_path: Path):
    target = tmp_path / "no_min.md"
    _write(
        target,
        "---\nname: no_min\ntriggers:\n  - ssh\n---\nBody",
    )
    skill = load_skill_from_path(target, default_min_user_text_chars=8)
    assert skill is not None
    assert isinstance(skill.trigger, KeywordTrigger)
    assert skill.trigger.min_user_text_chars == 8


def test_load_skill_passes_through_extra_keys(tmp_path: Path):
    target = tmp_path / "extras.md"
    _write(
        target,
        "---\nname: extras\nagent: CodeActAgent\ncustom: pickle\n---\nBody",
    )
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.extra["agent"] == "CodeActAgent"
    assert skill.extra["custom"] == "pickle"


def test_load_skill_description_and_version(tmp_path: Path):
    target = tmp_path / "doc.md"
    _write(
        target,
        "---\nname: doc\ndescription: helpful intro\nversion: 1.2.0\n---\nBody",
    )
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.description == "helpful intro"
    assert skill.version == "1.2.0"


def test_load_skills_from_directory_walks(tmp_path: Path):
    _write(
        tmp_path / "a.md",
        "---\nname: a\n---\nbody",
    )
    _write(
        tmp_path / "sub" / "b.md",
        "---\nname: b\n---\nbody",
    )
    _write(tmp_path / "README.md", "skipped")
    _write(tmp_path / "ignored.txt", "skipped")

    skills, stats = load_skills_from_directory(tmp_path, source=SkillSource.PUBLIC)
    names = sorted(s.name for s in skills)
    assert names == ["a", "b"]
    assert stats.files_scanned == 2
    assert stats.skills_loaded == 2


def test_load_skills_from_directory_missing_returns_empty(tmp_path: Path):
    skills, stats = load_skills_from_directory(tmp_path / "absent")
    assert skills == []
    assert isinstance(stats, SkillLoadStats)
    assert stats.files_scanned == 0


def test_load_skills_swallows_per_file_error(tmp_path: Path):
    _write(
        tmp_path / "bad.md",
        "---\nname: bad\ntriggers: : : invalid\n---\nbody",
    )
    _write(
        tmp_path / "good.md",
        "---\nname: good\n---\nbody",
    )
    skills, stats = load_skills_from_directory(tmp_path)
    names = sorted(s.name for s in skills)
    # bad.md has invalid YAML; the loader falls back to using the file stem
    # so the file shows up as an always-on skill with the error recorded.
    assert "good" in names
    # Files-scanned counts both even though one had a parse warning.
    assert stats.files_scanned == 2


def test_load_skills_from_directory_non_recursive(tmp_path: Path):
    _write(tmp_path / "top.md", "---\nname: top\n---\nbody")
    _write(tmp_path / "deep" / "inside.md", "---\nname: inside\n---\nbody")
    skills, _ = load_skills_from_directory(tmp_path, recursive=False)
    assert [s.name for s in skills] == ["top"]


def test_load_skills_unknown_type_defaults_to_knowledge(tmp_path: Path):
    target = tmp_path / "x.md"
    _write(target, "---\nname: x\ntype: bizarre\ntriggers:\n  - foo\n---\nbody")
    skill = load_skill_from_path(target)
    assert skill is not None
    assert skill.type == SkillType.KNOWLEDGE
