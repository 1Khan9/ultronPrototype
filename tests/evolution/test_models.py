"""Tests for kenning.evolution.models -- the GEP data model.

All hermetic: pure data, no IO, no network, no voice stack.
"""

from __future__ import annotations

import math

import pytest

from kenning.evolution.models import (
    DEFAULT_GENE_MAX_FILES,
    DISTILLED_GENE_MAX_FILES,
    DISTILLED_ID_PREFIX,
    EVOLUTION_SCHEMA_VERSION,
    REPAIR_DISTILLED_ID_PREFIX,
    AntiPatternEntry,
    BlastRadius,
    Capsule,
    EnvFingerprint,
    EvolutionCategory,
    EvolutionEvent,
    Gene,
    GeneConstraints,
    LearningHistoryEntry,
    Mutation,
    Outcome,
    OutcomeStatus,
    PersonalityState,
    RiskLevel,
    canonicalize,
    clamp01,
    compute_asset_id,
    new_capsule_id,
    new_event_id,
    new_gene_id,
    new_mutation_id,
    verify_asset_id,
)


# --- enums ------------------------------------------------------------------


def test_evolution_category_members():
    assert EvolutionCategory.REPAIR.value == "repair"
    assert EvolutionCategory.OPTIMIZE.value == "optimize"
    assert EvolutionCategory.INNOVATE.value == "innovate"
    assert {c.value for c in EvolutionCategory} == {"repair", "optimize", "innovate"}


def test_destroy_is_not_a_valid_category():
    with pytest.raises(ValueError):
        EvolutionCategory("destroy")


def test_outcome_and_risk_members():
    assert {o.value for o in OutcomeStatus} == {"success", "failed"}
    assert {r.value for r in RiskLevel} == {"low", "medium", "high"}


# --- clamp01 ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0.5, 0.5),
        (0.0, 0.0),
        (1.0, 1.0),
        (-1.0, 0.0),
        (2.0, 1.0),
        (None, 0.0),
        ("not a number", 0.0),
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (float("-inf"), 0.0),
        (1, 1.0),
        ("0.25", 0.25),
    ],
)
def test_clamp01(raw, expected):
    assert clamp01(raw) == expected


# --- canonicalize -----------------------------------------------------------


def test_canonicalize_sorts_keys():
    assert canonicalize({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonicalize_non_finite_becomes_null():
    out = canonicalize({"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": 1.5})
    assert out == '{"a":null,"b":null,"c":null,"d":1.5}'


def test_canonicalize_is_deterministic_across_equal_objects():
    a = Gene(id="g1", category="repair", signals_match=["x", "y"])
    b = Gene(id="g1", category=EvolutionCategory.REPAIR, signals_match=("x", "y"))
    assert canonicalize(a) == canonicalize(b)


def test_canonicalize_enum_renders_value():
    assert '"repair"' in canonicalize({"cat": EvolutionCategory.REPAIR})


# --- compute_asset_id / verify_asset_id ------------------------------------


def test_compute_asset_id_is_stable_and_prefixed():
    g = Gene(id="g1", category="optimize", strategy=["a", "b"])
    aid = compute_asset_id(g)
    assert aid.startswith("sha256:")
    assert compute_asset_id(g) == aid  # stable


def test_compute_asset_id_changes_with_content():
    a = Gene(id="g1", category="optimize", strategy=["a"])
    b = Gene(id="g1", category="optimize", strategy=["a", "b"])
    assert compute_asset_id(a) != compute_asset_id(b)


def test_compute_asset_id_excludes_asset_id_field():
    one = {"x": 1, "asset_id": "old"}
    two = {"x": 1, "asset_id": "totally-different"}
    assert compute_asset_id(one) == compute_asset_id(two)


def test_verify_asset_id_true_for_self_hashed_capsule():
    c = Capsule(id=new_capsule_id(), gene="g1")
    assert c.asset_id.startswith("sha256:")
    assert verify_asset_id(c) is True


def test_verify_asset_id_false_when_tampered():
    import dataclasses

    c = Capsule(id="capsule_1", gene="g1", summary="orig")
    tampered = dataclasses.replace(c, summary="changed")  # asset_id carried, not recomputed
    assert verify_asset_id(tampered) is False


def test_verify_asset_id_false_without_id():
    assert verify_asset_id({"x": 1}) is False
    assert verify_asset_id(42) is False


# --- id generators ----------------------------------------------------------


def test_id_generators_shapes():
    assert new_event_id().startswith("evt_")
    assert new_capsule_id().startswith("capsule_")
    assert new_mutation_id().startswith("mut_")
    assert new_gene_id().startswith("gene_")
    assert new_gene_id(DISTILLED_ID_PREFIX).startswith(DISTILLED_ID_PREFIX)
    # uniqueness across calls
    assert new_event_id() != new_event_id()


# --- EnvFingerprint ---------------------------------------------------------


def test_env_fingerprint_capture_is_non_identifying():
    fp = EnvFingerprint.capture()
    assert fp.platform
    assert fp.python_version
    assert fp.captured_at
    # No device id / hostname / mac fields exist on the dataclass at all.
    field_names = {f for f in EnvFingerprint.__dataclass_fields__}
    assert field_names == {"platform", "python_version", "captured_at"}


# --- BlastRadius / Outcome / GeneConstraints --------------------------------


def test_blast_radius_clamps_negative_to_zero():
    br = BlastRadius(files=-3, lines=-1)
    assert br.files == 0 and br.lines == 0


def test_outcome_coerces_status_and_clamps_score():
    oc = Outcome(status="success", score=2.0)
    assert oc.status is OutcomeStatus.SUCCESS
    assert oc.score == 1.0
    assert oc.succeeded is True
    assert Outcome(status="failed", score=-1).succeeded is False


def test_gene_constraints_defaults_and_coerce():
    gc = GeneConstraints()
    assert gc.max_files == DEFAULT_GENE_MAX_FILES
    assert ".git" in gc.forbidden_paths
    from_map = GeneConstraints.coerce({"max_files": 5, "forbidden_paths": ["a", "b"]})
    assert from_map.max_files == 5
    assert from_map.forbidden_paths == ("a", "b")
    assert GeneConstraints.coerce(None).max_files == DEFAULT_GENE_MAX_FILES
    assert GeneConstraints.coerce(gc) is gc


def test_gene_constraints_min_files_floor():
    assert GeneConstraints(max_files=0).max_files == 1


# --- PersonalityState -------------------------------------------------------


def test_personality_clamps_all_traits():
    ps = PersonalityState(rigor=2.0, creativity=-1.0, verbosity=float("nan"), risk_tolerance=0.3, obedience=0.9)
    assert ps.rigor == 1.0
    assert ps.creativity == 0.0
    assert ps.verbosity == 0.0
    assert ps.risk_tolerance == 0.3
    assert ps.obedience == 0.9


def test_personality_balanced_default():
    ps = PersonalityState.balanced()
    assert ps.rigor == ps.creativity == ps.verbosity == ps.risk_tolerance == ps.obedience == 0.5


def test_personality_is_high_risk():
    assert PersonalityState(rigor=0.3).is_high_risk() is True
    assert PersonalityState(risk_tolerance=0.7).is_high_risk() is True
    assert PersonalityState(rigor=0.5, risk_tolerance=0.5).is_high_risk() is False


def test_personality_allows_high_risk_mutation():
    assert PersonalityState(rigor=0.6, risk_tolerance=0.5).allows_high_risk_mutation() is True
    assert PersonalityState(rigor=0.6, risk_tolerance=0.6).allows_high_risk_mutation() is False
    assert PersonalityState(rigor=0.5, risk_tolerance=0.5).allows_high_risk_mutation() is False


def test_personality_with_trait():
    ps = PersonalityState.balanced().with_trait("verbosity", 0.9)
    assert ps.verbosity == 0.9
    assert ps.rigor == 0.5  # others unchanged
    with pytest.raises(ValueError):
        ps.with_trait("nope", 0.5)


# --- Gene -------------------------------------------------------------------


def test_gene_coerces_category_and_sequences():
    g = Gene(
        id="g1",
        category="innovate",
        signals_match=["a", "b"],
        strategy=["step1"],
        validation=["python -m pytest"],
        constraints={"max_files": 7, "forbidden_paths": [".git"]},
    )
    assert g.category is EvolutionCategory.INNOVATE
    assert g.signals_match == ("a", "b")
    assert g.strategy == ("step1",)
    assert isinstance(g.constraints, GeneConstraints)
    assert g.constraints.max_files == 7
    assert g.schema_version == EVOLUTION_SCHEMA_VERSION
    assert g.type == "Gene"


def test_gene_is_inplace_and_is_distilled():
    assert Gene(id="g", category="repair", execution_mode="inplace").is_inplace is True
    assert Gene(id="g", category="repair").is_inplace is False
    assert Gene(id=DISTILLED_ID_PREFIX + "x", category="repair").is_distilled is True
    assert Gene(id=REPAIR_DISTILLED_ID_PREFIX + "x", category="repair").is_distilled is True
    assert Gene(id="gene_handwritten", category="repair").is_distilled is False


def test_gene_with_learning_success_adds_problem_and_area_tags_only():
    g = Gene(id="g1", category="optimize", signals_match=["base"])
    adapted = g.with_learning(
        outcome=OutcomeStatus.SUCCESS,
        learning_signals=["problem:performance", "area:memory", "action:optimize"],
    )
    assert "base" in adapted.signals_match
    assert "problem:performance" in adapted.signals_match
    assert "area:memory" in adapted.signals_match
    assert "action:optimize" not in adapted.signals_match  # action:* not added
    assert len(adapted.learning_history) == 1
    assert adapted.learning_history[0].outcome is OutcomeStatus.SUCCESS
    # original untouched (frozen / functional)
    assert g.signals_match == ("base",)
    assert g.learning_history == ()


def test_gene_with_learning_failure_records_anti_pattern_without_extending_signals():
    g = Gene(id="g1", category="optimize", signals_match=["base"])
    adapted = g.with_learning(
        outcome=OutcomeStatus.FAILED,
        learning_signals=["problem:x"],
        mode="hard",
    )
    assert adapted.signals_match == ("base",)  # NOT extended on failure
    assert len(adapted.anti_patterns) == 1
    assert adapted.anti_patterns[0].mode == "hard"
    assert adapted.anti_patterns[0].learning_signals == ("problem:x",)
    assert adapted.learning_history[0].outcome is OutcomeStatus.FAILED


# --- Mutation ---------------------------------------------------------------


def test_mutation_coercion():
    m = Mutation(
        id=new_mutation_id(),
        category="repair",
        trigger_signals=["log_error"],
        risk_level="medium",
    )
    assert m.category is EvolutionCategory.REPAIR
    assert m.risk_level is RiskLevel.MEDIUM
    assert m.trigger_signals == ("log_error",)
    assert m.type == "Mutation"


# --- Capsule ----------------------------------------------------------------


def test_capsule_auto_computes_asset_id_and_coerces_nested_dicts():
    c = Capsule(
        id="capsule_1",
        trigger=["sig"],
        gene="g1",
        confidence=1.5,
        blast_radius={"files": 2, "lines": 9},
        outcome={"status": "success", "score": 0.85},
        success_streak=-2,
    )
    assert c.asset_id.startswith("sha256:")
    assert c.confidence == 1.0  # clamped
    assert isinstance(c.blast_radius, BlastRadius) and c.blast_radius.files == 2
    assert isinstance(c.outcome, Outcome) and c.outcome.score == 0.85
    assert c.success_streak == 0  # clamped
    assert isinstance(c.env_fingerprint, EnvFingerprint)


def test_capsule_explicit_asset_id_preserved():
    c = Capsule(id="c", gene="g", asset_id="sha256:preset")
    assert c.asset_id == "sha256:preset"


# --- EvolutionEvent ---------------------------------------------------------


def test_evolution_event_defaults_and_auto_hash():
    ev = EvolutionEvent(
        id=new_event_id(),
        intent="repair",
        signals=["log_error"],
        genes_used=["g1"],
        mutation_id="mut_x",
        personality_state={"rigor": 0.7},
        outcome={"status": "failed", "score": 0.1},
    )
    assert ev.created_at  # auto-filled
    assert ev.asset_id.startswith("sha256:")
    assert isinstance(ev.personality_state, PersonalityState)
    assert ev.personality_state.rigor == 0.7
    assert ev.outcome.status is OutcomeStatus.FAILED
    assert ev.type == "EvolutionEvent"


def test_distilled_max_files_constant_is_tighter():
    assert DISTILLED_GENE_MAX_FILES < DEFAULT_GENE_MAX_FILES
