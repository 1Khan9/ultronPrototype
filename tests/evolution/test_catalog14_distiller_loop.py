"""Catalog 14 -- pattern_key recurrence (skill_distiller) + repair distillation
wired into the bounded EvolutionLoop. Hermetic (fake collaborators, tmp_path).
"""

from __future__ import annotations

from kenning.evolution import skill_distiller as D
from kenning.evolution.autonomy import TieredAutonomyController
from kenning.evolution.evolution_loop import (
    ApplyStatus,
    EvolutionLoop,
    EvolutionLoopConfig,
)
from kenning.evolution.guardrails import GuardrailSample
from kenning.evolution.models import (
    REPAIR_DISTILLED_ID_PREFIX,
    Capsule,
    Outcome,
    OutcomeStatus,
)


def _cap(i, *, pk="", rec=1, gene="ad_hoc", trig=("perf_bottleneck",), score=0.85, first="", last=""):
    return Capsule(
        id=f"c{i}",
        gene=gene,
        trigger=list(trig),
        summary="optimized the slow path",
        confidence=score,
        outcome=Outcome(status=OutcomeStatus.SUCCESS, score=score),
        pattern_key=pk,
        recurrence_count=rec,
        first_seen=first,
        last_seen=last,
    )


# -- pattern_key recurrence (T4) ---------------------------------------------


def test_merge_by_pattern_key_counts_rows_and_tracks_seen():
    caps = [
        _cap(0, pk="capsule:perf", first="2026-01-01", last="2026-01-01"),
        _cap(1, pk="capsule:perf", first="2026-01-02", last="2026-01-03"),
        _cap(2, pk="capsule:other"),
    ]
    merged = D.merge_capsules_by_pattern_key(caps)
    assert set(merged) == {"capsule:perf", "capsule:other"}
    perf = merged["capsule:perf"]
    assert perf.total_recurrence == 2 and perf.capsule_count == 2
    assert perf.first_seen == "2026-01-01" and perf.last_seen == "2026-01-03"


def test_collect_and_analyze_surface_recurrence():
    caps = [_cap(i, pk="capsule:perf") for i in range(12)]
    data = D.collect_distillation_data(caps)
    assert data.pattern_recurrence == {"capsule:perf": 12}
    assert data.grouped["ad_hoc"].dominant_pattern_key == "capsule:perf"
    assert data.grouped["ad_hoc"].pattern_recurrence == 12
    analysis = D.analyze_patterns(data)
    assert "capsule:perf" in analysis.recurring_patterns  # >= RECURRENCE_PROMOTE_THRESHOLD


def test_back_compat_empty_pattern_key():
    caps = [_cap(i, pk="", gene="gene_perf") for i in range(10)]
    data = D.collect_distillation_data(caps)
    assert dict(data.pattern_recurrence) == {}  # nothing keyed
    assert data.grouped["gene_perf"].count == 10
    assert data.grouped["gene_perf"].dominant_pattern_key == ""
    assert D.auto_distill(caps).ok is True  # legacy success distillation unaffected


def test_recurrence_threshold_constant():
    assert D.RECURRENCE_PROMOTE_THRESHOLD == 3


# -- repair distillation wired into the loop (T1) ----------------------------


def _failure(i, *, area="pytest"):
    return {
        "gene": "ad_hoc",
        "trigger": ["user_correction", f"area:{area}"],
        "reason_class": "user_correction",
        "learning_signals": [f"area:{area}", "problem:reliability", "action:repair"],
        "pattern_key": f"correction:{area}",
    }


def _loop(tmp_path, *, capsules, failures):
    return EvolutionLoop(
        repo_root=tmp_path,
        proposal_dir=tmp_path / "data" / "evolution" / "skills",
        capsules_provider=lambda: capsules,
        failures_provider=lambda: failures,
        autonomy=TieredAutonomyController(),
        guardrail_sampler=lambda: GuardrailSample(),
        config=EvolutionLoopConfig(surface="skills"),
    )


def test_loop_falls_back_to_repair_distillation(tmp_path):
    # No success capsules -> success distillation yields nothing -> the loop
    # distils a DEFENSIVE repair gene from the accumulated failures.
    loop = _loop(tmp_path, capsules=[], failures=[_failure(i) for i in range(6)])
    result = loop.run_once()
    assert result is not None
    assert result.proposal.gene.id.startswith(REPAIR_DISTILLED_ID_PREFIX)
    assert result.status is ApplyStatus.KEPT
    assert (tmp_path / "data" / "evolution" / "skills" / result.proposal.filename).exists()


def test_loop_no_proposal_without_capsules_or_failures(tmp_path):
    loop = _loop(tmp_path, capsules=[], failures=[])
    assert loop.run_once() is None


def test_loop_default_failures_provider_is_noop(tmp_path):
    # Omitting failures_provider entirely keeps the legacy success-only path.
    loop = EvolutionLoop(
        repo_root=tmp_path,
        proposal_dir=tmp_path / "data" / "evolution" / "skills",
        capsules_provider=lambda: [],
        autonomy=TieredAutonomyController(),
        guardrail_sampler=lambda: GuardrailSample(),
        config=EvolutionLoopConfig(surface="skills"),
    )
    assert loop.run_once() is None
