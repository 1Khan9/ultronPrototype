"""Tests for the skill registry: dedup, mtime invalidation, matching, rendering."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ultron.skills.models import (
    KeywordTrigger,
    Skill,
    SkillMatch,
    SkillSource,
    TaskTrigger,
)
from ultron.skills.registry import (
    DEFAULT_KEYWORD_MIN_USER_TEXT_CHARS,
    SkillRegistry,
    build_default_registry,
    format_skills_block,
    get_skill_registry,
    reset_skill_registry_for_testing,
    set_skill_registry,
)
from ultron.skills.registry import _SourceSpec  # type: ignore[attr-defined]


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_skill_registry_for_testing()
    yield
    reset_skill_registry_for_testing()


# -- basic load + match --


def test_registry_loads_lazily(tmp_path: Path):
    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nbody",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    assert registry.loaded_at == 0.0
    # First match call triggers a lazy load.
    matches = registry.matching_skills("playing valorant tonight")
    assert registry.loaded_at > 0
    assert any(m.skill.name == "gaming" for m in matches)


def test_registry_always_on_skills_emitted_unconditionally(tmp_path: Path):
    _write(tmp_path / "core.md", "---\nname: core\n---\nalways here")
    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nbody",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    matches = registry.matching_skills("totally unrelated weather query")
    names = [m.skill.name for m in matches]
    assert "core" in names
    assert "gaming" not in names


def test_registry_keyword_match_population(tmp_path: Path):
    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n  - csgo\n---\nbody",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    matches = registry.matching_skills("playing valorant tonight")
    assert len(matches) == 1
    assert matches[0].matched_terms == ("valorant",)


def test_registry_task_trigger_matches_slash(tmp_path: Path):
    _write(
        tmp_path / "onboard.md",
        "---\nname: onboard\ntype: task\ntriggers:\n  - /onboard\n---\nbody",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    matches = registry.matching_skills("/onboard please")
    assert len(matches) == 1
    assert matches[0].skill.name == "onboard"


def test_registry_disabled_skills_filtered(tmp_path: Path):
    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nbody",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)],
        disabled_skills=["gaming"],
    )
    matches = registry.matching_skills("playing valorant tonight")
    assert matches == []


def test_registry_set_disabled_skills_runtime(tmp_path: Path):
    _write(tmp_path / "core.md", "---\nname: core\n---\nbody")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    assert registry.matching_skills("hi") != []
    registry.set_disabled_skills(["core"])
    assert registry.matching_skills("hi") == []


# -- precedence + dedup --


def test_registry_project_overrides_public(tmp_path: Path):
    public_dir = tmp_path / "public"
    project_dir = tmp_path / "project"
    _write(
        public_dir / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nPUBLIC body",
    )
    _write(
        project_dir / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nPROJECT body",
    )
    registry = SkillRegistry(
        [
            _SourceSpec(directory=public_dir, source=SkillSource.PUBLIC),
            _SourceSpec(directory=project_dir, source=SkillSource.PROJECT),
        ]
    )
    matches = registry.matching_skills("about valorant")
    assert len(matches) == 1
    assert matches[0].skill.source == SkillSource.PROJECT
    assert "PROJECT body" in matches[0].content


def test_registry_max_matches_cap(tmp_path: Path):
    for idx in range(8):
        _write(
            tmp_path / f"skill_{idx}.md",
            f"---\nname: skill_{idx}\ntriggers:\n  - foo{idx}\n---\nbody",
        )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)],
        max_matches_per_turn=3,
    )
    text = " ".join(f"foo{i}" for i in range(8))
    matches = registry.matching_skills(text)
    # Only triggered matches are subject to the cap; no always-on skills exist here.
    assert len(matches) == 3


def test_registry_always_on_only_drops_triggered(tmp_path: Path):
    _write(tmp_path / "core.md", "---\nname: core\n---\nalways")
    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nbody",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)],
        always_on_only=True,
    )
    names = [m.skill.name for m in registry.matching_skills("playing valorant")]
    assert names == ["core"]


# -- mtime invalidation --


def test_registry_invalidates_on_new_file(tmp_path: Path):
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    # Trigger initial load.
    assert registry.matching_skills("hello") == []
    # Add a skill on disk after the registry was loaded.
    _write(tmp_path / "later.md", "---\nname: later\n---\nbody")
    # Ensure mtime moves visibly forward on coarse-resolution filesystems.
    time.sleep(0.01)
    (tmp_path / "later.md").touch()
    matches = registry.matching_skills("hello")
    assert any(m.skill.name == "later" for m in matches)


def test_registry_invalidates_on_file_modification(tmp_path: Path):
    target = tmp_path / "evolving.md"
    _write(target, "---\nname: evolving\n---\nfirst body")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    initial = registry.matching_skills("hello")
    assert "first body" in initial[0].content

    time.sleep(0.01)
    _write(target, "---\nname: evolving\n---\nsecond body")
    target.touch()
    later = registry.matching_skills("hello")
    assert any("second body" in m.content for m in later)


def test_registry_invalidates_on_file_removal(tmp_path: Path):
    target = tmp_path / "going_away.md"
    _write(target, "---\nname: going_away\n---\nfirst body")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    assert registry.matching_skills("hi") != []

    target.unlink()
    time.sleep(0.01)
    assert registry.matching_skills("hi") == []


def test_registry_reload_replaces_catalog(tmp_path: Path):
    target = tmp_path / "x.md"
    _write(target, "---\nname: x\n---\nbody")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    assert {s.name for s in registry.all_skills()} == {"x"}
    target.unlink()
    _write(tmp_path / "y.md", "---\nname: y\n---\nbody")
    registry.reload()
    assert {s.name for s in registry.all_skills()} == {"y"}


def test_registry_add_source_runtime(tmp_path: Path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    _write(a_dir / "skill_a.md", "---\nname: skill_a\n---\nbody")
    _write(b_dir / "skill_b.md", "---\nname: skill_b\n---\nbody")
    registry = SkillRegistry(
        [_SourceSpec(directory=a_dir, source=SkillSource.PUBLIC)]
    )
    assert {s.name for s in registry.all_skills()} == {"skill_a"}
    registry.add_source(b_dir, source=SkillSource.PROJECT)
    assert {s.name for s in registry.all_skills()} == {"skill_a", "skill_b"}


# -- introspection --


def test_registry_list_skill_names_sorted(tmp_path: Path):
    _write(tmp_path / "b.md", "---\nname: bravo\n---\n")
    _write(tmp_path / "a.md", "---\nname: alpha\n---\n")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    assert registry.list_skill_names() == ["alpha", "bravo"]


def test_registry_load_stats_populated(tmp_path: Path):
    _write(tmp_path / "x.md", "---\nname: x\n---\nbody")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    registry.reload()
    stats = registry.last_load_stats
    assert len(stats) == 1
    assert stats[0].skills_loaded == 1
    assert stats[0].files_scanned == 1


# -- rendering --


def test_format_skills_block_empty():
    assert format_skills_block([]) == ""


def test_format_skills_block_basic():
    skill = Skill(name="gaming", content="Valorant tips here.\n")
    text = format_skills_block([SkillMatch(skill=skill, matched_terms=("valorant",))])
    assert "[Skills: gaming]" in text
    assert "# gaming" in text
    assert "Valorant tips here." in text
    assert text.endswith("\n")


def test_format_skills_block_multi():
    a = Skill(name="alpha", content="A body")
    b = Skill(name="bravo", content="B body")
    text = format_skills_block(
        [SkillMatch(skill=a, matched_terms=()), SkillMatch(skill=b, matched_terms=())]
    )
    assert "[Skills: alpha, bravo]" in text
    assert text.index("# alpha") < text.index("# bravo")


def test_format_skills_block_truncates():
    long_body = "x" * 10_000
    skill = Skill(name="big", content=long_body)
    truncated = format_skills_block(
        [SkillMatch(skill=skill, matched_terms=())], max_chars=200
    )
    assert len(truncated) <= 250
    assert "skills truncated" in truncated


def test_format_skills_block_descriptions_included():
    skill = Skill(name="gaming", content="body", description="game brain")
    text = format_skills_block(
        [SkillMatch(skill=skill, matched_terms=())], include_descriptions=True
    )
    assert "game brain" in text


# -- singleton accessor --


def test_set_and_get_singleton(tmp_path: Path):
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    set_skill_registry(registry)
    assert get_skill_registry() is registry


def test_reset_singleton_clears(tmp_path: Path):
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)]
    )
    set_skill_registry(registry)
    reset_skill_registry_for_testing()
    assert get_skill_registry() is None


# -- default-registry factory --


def test_build_default_registry_includes_three_sources(tmp_path: Path):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    registry = build_default_registry(project_root=project, user_home=home)
    sources = registry.sources
    assert project / "skills" in sources
    assert home / ".ultron" / "skills" in sources
    assert project / ".ultron" / "skills" in sources


def test_build_default_registry_extra_dirs(tmp_path: Path):
    project = tmp_path / "project"
    extra = tmp_path / "shared_skills"
    project.mkdir()
    extra.mkdir()
    registry = build_default_registry(
        project_root=project,
        user_home=tmp_path,
        extra_project_dirs=[extra],
    )
    assert extra in registry.sources


def test_default_min_user_text_chars_pinned():
    assert DEFAULT_KEYWORD_MIN_USER_TEXT_CHARS == 8
