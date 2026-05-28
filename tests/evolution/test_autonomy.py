"""Tests for ultron.evolution.autonomy -- the tiered-autonomy controller +
trust graduation + rollback demotion. All hermetic."""

from __future__ import annotations

from ultron.evolution.autonomy import (
    AutonomyMode,
    AutonomyTier,
    TieredAutonomyController,
)


def _ctrl(**kw):
    return TieredAutonomyController(**kw)


# --- tier + mode resolution -------------------------------------------------


def test_base_tiers():
    c = _ctrl()
    assert c.base_tier("personality") is AutonomyTier.PARAM
    assert c.base_tier("skills") is AutonomyTier.SKILL
    assert c.base_tier("safety_rules") is AutonomyTier.GATED
    assert c.base_tier("safety_validator") is AutonomyTier.WALL
    assert c.base_tier("totally_unknown") is AutonomyTier.GATED  # conservative default


def test_mode_for_defaults():
    c = _ctrl()
    assert c.mode_for("personality") is AutonomyMode.AUTONOMOUS  # tier 0
    assert c.mode_for("skills") is AutonomyMode.AUTONOMOUS  # tier 1
    assert c.mode_for("safety_rules") is AutonomyMode.GATED  # tier 2 ungraduated
    assert c.mode_for("safety_validator") is AutonomyMode.WALLED  # tier 3


def test_predicates():
    c = _ctrl()
    assert c.can_auto_apply("skills") is True
    assert c.requires_approval("safety_rules") is True
    assert c.is_walled("evolution_engine") is True
    assert c.is_blocked("evolution_engine") is True
    assert c.is_blocked("skills") is False


# --- walled surfaces never record -------------------------------------------


def test_walled_surface_never_records():
    c = _ctrl()
    t = c.record_outcome("category_k", reverted=False)
    assert t is None
    assert c.state("category_k").applied == 0


# --- graduation -------------------------------------------------------------


def test_tier2_graduates_after_strong_record():
    c = _ctrl()
    transition = None
    for _ in range(20):
        transition = c.record_outcome("safety_rules", reverted=False)
    assert transition is not None
    assert transition.kind == "graduated"
    assert c.mode_for("safety_rules") is AutonomyMode.AUTONOMOUS
    assert c.can_auto_apply("safety_rules") is True


def test_tier2_does_not_graduate_early():
    c = _ctrl()
    for _ in range(19):
        t = c.record_outcome("safety_rules", reverted=False)
        assert t is None
    assert c.mode_for("safety_rules") is AutonomyMode.GATED


def test_tier2_does_not_graduate_with_hard_trip():
    c = _ctrl()
    for i in range(20):
        c.record_outcome("safety_rules", reverted=False, hard_guardrail_trip=(i == 0))
    assert c.mode_for("safety_rules") is AutonomyMode.GATED  # one hard trip blocks graduation


def test_tier2_does_not_graduate_with_high_revert_rate():
    c = _ctrl()
    # 18 kept + 2 reverted = 0.10 revert rate (not < 0.10)
    for _ in range(18):
        c.record_outcome("safety_rules", reverted=False)
    for _ in range(2):
        c.record_outcome("safety_rules", reverted=True)
    assert c.mode_for("safety_rules") is AutonomyMode.GATED


# --- demotion ---------------------------------------------------------------


def test_autonomous_surface_demotes_on_high_rollback():
    c = _ctrl()
    transition = None
    for _ in range(5):
        transition = c.record_outcome("skills", reverted=True)
    assert transition is not None
    assert transition.kind == "demoted"
    assert c.mode_for("skills") is AutonomyMode.GATED


def test_demote_with_pause_option():
    c = _ctrl(pause_on_demote=True)
    transition = None
    for _ in range(5):
        transition = c.record_outcome("skills", reverted=True)
    assert transition.kind == "paused"
    assert c.mode_for("skills") is AutonomyMode.PAUSED
    assert c.is_blocked("skills") is True


def test_graduated_surface_can_later_demote():
    c = _ctrl()
    for _ in range(20):
        c.record_outcome("safety_rules", reverted=False)
    assert c.mode_for("safety_rules") is AutonomyMode.AUTONOMOUS
    # now flood with reverts -> >30% of the window -> demote
    demoted = False
    for _ in range(8):
        t = c.record_outcome("safety_rules", reverted=True)
        if t and t.kind == "demoted":
            demoted = True
    assert demoted is True
    assert c.mode_for("safety_rules") is AutonomyMode.GATED


# --- manual controls --------------------------------------------------------


def test_manual_pause_resume_reset():
    c = _ctrl()
    c.pause("skills")
    assert c.mode_for("skills") is AutonomyMode.PAUSED
    c.resume("skills")
    assert c.mode_for("skills") is AutonomyMode.AUTONOMOUS
    c.record_outcome("skills", reverted=True)
    assert c.state("skills").applied == 1
    c.reset("skills")
    assert c.state("skills").applied == 0


def test_cannot_pause_walled():
    c = _ctrl()
    c.pause("safety_validator")
    assert c.mode_for("safety_validator") is AutonomyMode.WALLED


# --- introspection ----------------------------------------------------------


def test_state_snapshot():
    c = _ctrl()
    c.record_outcome("skills", reverted=False)
    c.record_outcome("skills", reverted=True)
    st = c.state("skills")
    assert st.applied == 2 and st.kept == 1 and st.reverted == 1
    assert st.base_tier is AutonomyTier.SKILL


def test_digest():
    c = _ctrl()
    assert "no autonomous changes yet" in c.digest()
    c.record_outcome("skills", reverted=False)
    d = c.digest()
    assert "skills" in d
    assert "autonomous" in d
