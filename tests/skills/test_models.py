"""Tests for skill / trigger value types."""

from __future__ import annotations

import pytest

from kenning.skills.models import (
    KeywordTrigger,
    Skill,
    SkillMatch,
    SkillSource,
    SkillType,
    TaskTrigger,
    find_matched_commands,
    find_matched_keywords,
    matches_text,
)


# -- KeywordTrigger --


def test_keyword_trigger_whole_word_match():
    trigger = KeywordTrigger(keywords=("ssh",))
    assert trigger.matches("please ssh into the box") is True


def test_keyword_trigger_partial_word_rejected():
    trigger = KeywordTrigger(keywords=("ssh",))
    assert trigger.matches("sshd_config is read at startup") is False


def test_keyword_trigger_case_insensitive():
    trigger = KeywordTrigger(keywords=("GitHub",))
    assert trigger.matches("open the github page") is True


def test_keyword_trigger_min_chars_blocks_short_utterances():
    trigger = KeywordTrigger(keywords=("ssh",), min_user_text_chars=8)
    assert trigger.matches("ssh") is False
    assert trigger.matches("can you ssh in") is True


def test_keyword_trigger_empty_text_rejected():
    trigger = KeywordTrigger(keywords=("foo",))
    assert trigger.matches("") is False
    assert trigger.matches("   ") is False


def test_keyword_trigger_multiword_substring_match():
    trigger = KeywordTrigger(keywords=("agent computer interface",))
    assert trigger.matches("we use an agent computer interface here") is True
    assert trigger.matches("agent computer is partial") is False


# -- TaskTrigger --


def test_task_trigger_leading_slash_match():
    trigger = TaskTrigger(commands=("/onboard",))
    assert trigger.matches("/onboard") is True
    assert trigger.matches("/onboard please") is True


def test_task_trigger_natural_preamble_match():
    trigger = TaskTrigger(commands=("/onboard",))
    assert trigger.matches("can you /onboard me") is True


def test_task_trigger_no_match_when_command_absent():
    trigger = TaskTrigger(commands=("/onboard",))
    assert trigger.matches("just chatting about onboarding") is False


def test_task_trigger_handles_missing_leading_slash_in_config():
    trigger = TaskTrigger(commands=("onboard",))
    assert trigger.matches("/onboard now") is True
    assert trigger.matches("we should onboard the user") is False


def test_task_trigger_empty_text_rejected():
    trigger = TaskTrigger(commands=("/x",))
    assert trigger.matches("") is False


def test_task_trigger_trailing_punctuation_ok():
    trigger = TaskTrigger(commands=("/onboard",))
    assert trigger.matches("can we run /onboard, please?") is True


# -- matches_text helper --


def test_matches_text_short_circuits_empty():
    assert matches_text("", ("foo",)) is False
    assert matches_text("foo", ()) is False


def test_matches_text_token_match_only():
    assert matches_text("foo bar baz", ("bar",)) is True
    assert matches_text("foobarbaz", ("bar",)) is False


def test_find_matched_keywords_subset():
    matched = find_matched_keywords("we love valorant and csgo", ("valorant", "csgo", "minecraft"))
    assert set(matched) == {"valorant", "csgo"}


def test_find_matched_commands_subset():
    matched = find_matched_commands("/refactor please /lint", ("/refactor", "/lint", "/test"))
    assert set(matched) == {"/refactor", "/lint"}


# -- SkillSource precedence --


def test_skill_source_precedence_ordering():
    assert SkillSource.PROJECT.precedence > SkillSource.USER.precedence
    assert SkillSource.USER.precedence > SkillSource.PUBLIC.precedence


# -- Skill --


def test_skill_is_always_on_when_no_trigger():
    skill = Skill(name="x", content="body")
    assert skill.is_always_on is True
    assert skill.matches("anything") is True


def test_skill_matches_when_trigger_matches():
    skill = Skill(
        name="gaming",
        content="body",
        trigger=KeywordTrigger(keywords=("valorant",)),
    )
    assert skill.matches("playing valorant tonight") is True
    assert skill.matches("playing the piano") is False


def test_skill_matches_swallows_trigger_exception():
    class _Broken:
        def matches(self, text):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    # Note: dataclass frozen=True still allows constructor injection.
    skill = Skill(
        name="x",
        content="body",
        trigger=_Broken(),  # type: ignore[arg-type]
    )
    # Should fail-open to False rather than propagate.
    assert skill.matches("foo") is False


def test_skill_match_attributes_proxy_skill():
    skill = Skill(name="gaming", content="hello")
    match = SkillMatch(skill=skill, matched_terms=("hi",))
    assert match.name == "gaming"
    assert match.content == "hello"


def test_skill_is_frozen():
    skill = Skill(name="x", content="body")
    with pytest.raises(Exception):
        skill.name = "y"  # type: ignore[misc]


def test_skill_type_defaults_to_knowledge():
    skill = Skill(name="x", content="body")
    assert skill.type == SkillType.KNOWLEDGE
