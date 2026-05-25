"""Tests for the T12 moderation-plan preview surface."""

from __future__ import annotations

import pytest

from ultron.feedback.moderation_plan import (
    ImpactSeverity,
    ModerationPlan,
    PlanImpact,
    PlanOutcome,
    build_plan,
    render_plan_for_voice,
    requires_confirmation,
)


# ---------------------------------------------------------------------------
# requires_confirmation


def test_requires_confirmation_none_outcome_skips() -> None:
    assert not requires_confirmation(
        PlanOutcome.NONE,
        [PlanImpact(message="x", severity=ImpactSeverity.CRITICAL)],
    )


def test_requires_confirmation_narrate_skips() -> None:
    assert not requires_confirmation(
        PlanOutcome.NARRATE,
        [PlanImpact(message="x")],
    )


def test_requires_confirmation_purge_always_true() -> None:
    assert requires_confirmation(
        PlanOutcome.PURGE,
        [],
    )


def test_requires_confirmation_revoke_always_true() -> None:
    assert requires_confirmation(PlanOutcome.REVOKE, [])


def test_requires_confirmation_quarantine_always_true() -> None:
    assert requires_confirmation(PlanOutcome.QUARANTINE, [])


def test_requires_confirmation_critical_impact_triggers() -> None:
    assert requires_confirmation(
        PlanOutcome.HIDE,
        [PlanImpact(message="warn impact", severity=ImpactSeverity.CRITICAL)],
    )


def test_requires_confirmation_non_reversible_triggers() -> None:
    assert requires_confirmation(
        PlanOutcome.HIDE,
        [PlanImpact(message="ireversible", reversible=False)],
    )


def test_requires_confirmation_reversible_low_severity_skips() -> None:
    assert not requires_confirmation(
        PlanOutcome.HIDE,
        [PlanImpact(
            message="reversible warn",
            severity=ImpactSeverity.WARN,
            reversible=True,
        )],
    )


# ---------------------------------------------------------------------------
# render_plan_for_voice


def test_render_basic() -> None:
    text = render_plan_for_voice(
        subject="@user/example",
        outcome=PlanOutcome.HIDE,
        impacts=[PlanImpact(message="Hide from listings.")],
        requires_confirmation=True,
    )
    assert "Plan for @user/example:" in text
    assert "hide from listings" in text
    assert "Effects: Hide from listings" in text
    assert "Allow? Say yes or no." in text


def test_render_no_impacts() -> None:
    text = render_plan_for_voice(
        subject="x",
        outcome=PlanOutcome.NARRATE,
        impacts=[],
        requires_confirmation=False,
    )
    assert "Plan for x: narration only." == text


def test_render_truncates_long_impact_list() -> None:
    impacts = [PlanImpact(message=f"Step {i}.") for i in range(7)]
    text = render_plan_for_voice(
        subject="x",
        outcome=PlanOutcome.PURGE,
        impacts=impacts,
        requires_confirmation=True,
    )
    assert "(+4 more)" in text
    assert "Step 0" in text
    assert "Step 1" in text
    assert "Step 2" in text


def test_render_skips_confirm_prompt_when_not_required() -> None:
    text = render_plan_for_voice(
        subject="x",
        outcome=PlanOutcome.HIDE,
        impacts=[PlanImpact(message="ok.")],
        requires_confirmation=False,
    )
    assert "Allow?" not in text


# ---------------------------------------------------------------------------
# build_plan


def test_build_plan_basic() -> None:
    plan = build_plan(
        subject="voicepack:ultron",
        outcome=PlanOutcome.QUARANTINE,
        impacts=[PlanImpact(message="Stop loading the voicepack.")],
        actor="voice-user",
    )
    assert plan.subject == "voicepack:ultron"
    assert plan.outcome is PlanOutcome.QUARANTINE
    assert plan.actor == "voice-user"
    assert plan.requires_confirmation is True
    assert "Plan for voicepack:ultron" in plan.confirm_prompt
    assert len(plan.plan_id) == 12


def test_build_plan_force_confirmation_override() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.NARRATE,
        impacts=[],
        force_confirmation=True,
    )
    assert plan.requires_confirmation is True
    assert "Allow?" in plan.confirm_prompt


def test_build_plan_custom_confirm_prompt() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.HIDE,
        impacts=[],
        confirm_prompt="Say 'do it' to proceed.",
    )
    assert plan.confirm_prompt == "Say 'do it' to proceed."


def test_build_plan_explicit_plan_id() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.HIDE,
        impacts=[],
        plan_id="custom-id-xyz",
    )
    assert plan.plan_id == "custom-id-xyz"


def test_build_plan_metadata_pass_through() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.HIDE,
        impacts=[],
        metadata={"report_id": "r-1", "channel": "voice"},
    )
    assert plan.metadata["report_id"] == "r-1"


def test_build_plan_default_skips_confirmation_for_narrate() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.NARRATE,
        impacts=[PlanImpact(message="ok")],
    )
    assert plan.requires_confirmation is False


def test_build_plan_critical_impact_forces_confirmation() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.HIDE,
        impacts=[PlanImpact(message="big deal", severity=ImpactSeverity.CRITICAL)],
    )
    assert plan.requires_confirmation is True


# ---------------------------------------------------------------------------
# ModerationPlan dataclass invariants


def test_plan_is_frozen() -> None:
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.NONE,
        impacts=[],
    )
    with pytest.raises(Exception):
        plan.outcome = PlanOutcome.PURGE  # type: ignore[misc]


def test_impacts_tuple_persists_order() -> None:
    impacts = [
        PlanImpact(message="first"),
        PlanImpact(message="second"),
        PlanImpact(message="third"),
    ]
    plan = build_plan(
        subject="x",
        outcome=PlanOutcome.HIDE,
        impacts=impacts,
    )
    assert [i.message for i in plan.impacts] == ["first", "second", "third"]
