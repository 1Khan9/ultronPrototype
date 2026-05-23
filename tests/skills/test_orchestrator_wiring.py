"""Integration tests for the LLMEngine -> SkillRegistry wiring.

These tests exercise the seam between :func:`maybe_get_skills_block`
and :meth:`LLMEngine._build_messages` to make sure:

* When no registry is set, the system prompt is unchanged.
* When a registry is set and a skill matches, the block is prepended.
* When the registry raises, the system prompt is still safe.
"""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ultron.skills.models import KeywordTrigger, Skill, SkillSource
from ultron.skills.registry import (
    SkillRegistry,
    reset_skill_registry_for_testing,
    set_skill_registry,
)
from ultron.skills.registry import _SourceSpec  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _isolate_registry():
    reset_skill_registry_for_testing()
    yield
    reset_skill_registry_for_testing()


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _make_engine_stub(system_prompt: str):
    """Return a stand-in for LLMEngine that just exercises _build_messages.

    We avoid pulling the real engine in here because it loads llama-cpp;
    the goal is to test ONLY the skills-injection branch.
    """

    from ultron.llm.inference import LLMEngine

    engine = LLMEngine.__new__(LLMEngine)
    engine._explicit_system_prompt = system_prompt  # type: ignore[attr-defined]
    engine._static_system_prompt = system_prompt  # type: ignore[attr-defined]
    engine._persona_loader = None  # type: ignore[attr-defined]
    engine._logged_initial_persona = True  # type: ignore[attr-defined]
    engine.system_prompt = system_prompt
    engine._history = []  # type: ignore[attr-defined]
    # Avoid touching real memory.
    engine._memory = None  # type: ignore[attr-defined]
    # `_retrieve_rag_snippets` is called from _build_messages but only
    # when memory is non-None; with memory=None we get an empty rag block.
    engine._cfg = MagicMock()  # type: ignore[attr-defined]
    engine._cfg.history_turns_for_llm = 0
    # Avoid the in-process llama path.
    engine._sampling_params_for_request = lambda *a, **kw: {}  # type: ignore[attr-defined]
    return engine


def test_no_registry_means_no_skills_block(monkeypatch):
    """When no registry is set, the system prompt is unchanged."""

    from ultron.llm import inference as inference_mod

    engine = _make_engine_stub("BASE SYSTEM PROMPT")

    # Make sure get_config().llm.rag.position resolves; we don't care
    # about its value for this test, only that the call doesn't blow up.
    fake_cfg = MagicMock()
    fake_cfg.llm.rag.position = "recency"
    monkeypatch.setattr(inference_mod, "get_config", lambda: fake_cfg)

    msgs = engine._build_messages("just a normal question")
    system_msg = next(m for m in msgs if m["role"] == "system")
    assert system_msg["content"].startswith("BASE SYSTEM PROMPT")
    assert "[Skills:" not in system_msg["content"]


def test_registry_match_injects_block(tmp_path: Path, monkeypatch):
    """When a registry returns matches, the block is prepended to the system prompt."""

    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nGaming context body.",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)],
        default_min_user_text_chars=0,
    )
    set_skill_registry(registry)

    from ultron.llm import inference as inference_mod

    engine = _make_engine_stub("BASE SYSTEM PROMPT")
    fake_cfg = MagicMock()
    fake_cfg.llm.rag.position = "recency"
    monkeypatch.setattr(inference_mod, "get_config", lambda: fake_cfg)

    msgs = engine._build_messages("about valorant tonight")
    system_msg = next(m for m in msgs if m["role"] == "system")
    assert "BASE SYSTEM PROMPT" in system_msg["content"]
    assert "[Skills: gaming]" in system_msg["content"]
    assert "Gaming context body." in system_msg["content"]


def test_registry_no_match_leaves_prompt_alone(tmp_path: Path, monkeypatch):
    _write(
        tmp_path / "gaming.md",
        "---\nname: gaming\ntriggers:\n  - valorant\n---\nGaming context body.",
    )
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)],
        default_min_user_text_chars=0,
    )
    set_skill_registry(registry)

    from ultron.llm import inference as inference_mod

    engine = _make_engine_stub("BASE SYSTEM PROMPT")
    fake_cfg = MagicMock()
    fake_cfg.llm.rag.position = "recency"
    monkeypatch.setattr(inference_mod, "get_config", lambda: fake_cfg)

    msgs = engine._build_messages("a completely unrelated query about weather")
    system_msg = next(m for m in msgs if m["role"] == "system")
    assert system_msg["content"] == "BASE SYSTEM PROMPT"


def test_registry_exception_is_swallowed(monkeypatch):
    """A broken registry must not break _build_messages."""

    class _Broken(SkillRegistry):
        def matching_skills(self, user_text):
            raise RuntimeError("broken")

    broken = _Broken([])
    set_skill_registry(broken)

    from ultron.llm import inference as inference_mod

    engine = _make_engine_stub("BASE SYSTEM PROMPT")
    fake_cfg = MagicMock()
    fake_cfg.llm.rag.position = "recency"
    monkeypatch.setattr(inference_mod, "get_config", lambda: fake_cfg)

    # Should not raise; the skills block is just empty.
    msgs = engine._build_messages("about valorant tonight")
    system_msg = next(m for m in msgs if m["role"] == "system")
    assert system_msg["content"] == "BASE SYSTEM PROMPT"


def test_always_on_skill_injected_regardless_of_text(tmp_path: Path, monkeypatch):
    _write(tmp_path / "core.md", "---\nname: core\n---\nCore always-on body.")
    registry = SkillRegistry(
        [_SourceSpec(directory=tmp_path, source=SkillSource.PUBLIC)],
    )
    set_skill_registry(registry)

    from ultron.llm import inference as inference_mod

    engine = _make_engine_stub("BASE SYSTEM PROMPT")
    fake_cfg = MagicMock()
    fake_cfg.llm.rag.position = "recency"
    monkeypatch.setattr(inference_mod, "get_config", lambda: fake_cfg)

    msgs = engine._build_messages("anything goes here")
    system_msg = next(m for m in msgs if m["role"] == "system")
    assert "[Skills: core]" in system_msg["content"]
    assert "Core always-on body." in system_msg["content"]
