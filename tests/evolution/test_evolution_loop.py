"""Integration tests for kenning.evolution.evolution_loop -- the bounded
auto-apply + auto-revert cycle. Driven with fakes; writes only to tmp_path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kenning.evolution.autonomy import AutonomyMode, TieredAutonomyController
from kenning.evolution.blast_radius import BlastComputation
from kenning.evolution.evolution_loop import (
    ApplyStatus,
    CheckpointHook,
    EvolutionLoop,
    EvolutionLoopConfig,
    EvolutionState,
)
from kenning.evolution.guardrails import GuardrailSample
from kenning.evolution.models import (
    Capsule,
    EvolutionCategory,
    Gene,
    Outcome,
    OutcomeStatus,
)
from kenning.evolution.skill_distiller import gene_to_skill_proposal


def _caps(n=10):
    return [
        Capsule(
            id=f"capsule_{i}",
            gene="gene_perf",
            trigger=["perf_bottleneck"],
            summary="optimized the slow path",
            confidence=0.85,
            outcome=Outcome(status=OutcomeStatus.SUCCESS, score=0.85),
        )
        for i in range(n)
    ]


class _FakeCheckpoint:
    def __init__(self):
        self.taken = 0
        self.restored = []

    def take(self):
        self.taken += 1
        return f"ck{self.taken}"

    def restore(self, token):
        self.restored.append(token)
        return True


class _FakeApproval:
    def __init__(self, allow):
        self.allow = allow
        self.requests = []

    def request_decision(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allow)


def _make_loop(tmp_path, *, surface="skills", caps=None, sampler=None, approval=None, blast_provider=None, autonomy=None, state=None):
    fc = _FakeCheckpoint()
    sinks = {"capsules": [], "events": [], "failures": []}
    loop = EvolutionLoop(
        repo_root=tmp_path,
        proposal_dir=tmp_path / "data" / "evolution" / "skills",
        capsules_provider=lambda: (caps if caps is not None else _caps(10)),
        autonomy=autonomy or TieredAutonomyController(),
        guardrail_sampler=sampler or (lambda: GuardrailSample()),
        checkpoint=CheckpointHook(take=fc.take, restore=fc.restore),
        approval=approval,
        audit_sink=sinks["events"].append,
        capsule_sink=sinks["capsules"].append,
        failure_sink=sinks["failures"].append,
        blast_provider=blast_provider,
        state=state or EvolutionState(),
        config=EvolutionLoopConfig(surface=surface),
    )
    return loop, fc, sinks


# --- keep path --------------------------------------------------------------


def test_autonomous_keep(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path)
    result = loop.run_once()
    assert result is not None
    assert result.status is ApplyStatus.KEPT
    target = tmp_path / "data" / "evolution" / "skills" / result.proposal.filename
    assert target.exists()
    assert len(sinks["capsules"]) == 1
    assert len(sinks["events"]) == 1
    assert sinks["events"][0].outcome.status is OutcomeStatus.SUCCESS
    assert fc.taken >= 1
    assert loop._autonomy.state("skills").kept == 1


# --- revert paths -----------------------------------------------------------


def test_guardrail_revert(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path, sampler=lambda: GuardrailSample(ttfa_ms=999))
    result = loop.run_once()
    assert result.status is ApplyStatus.REVERTED
    assert "latency" in (result.guardrail.tripped_guards if result.guardrail else ())
    target = tmp_path / "data" / "evolution" / "skills" / result.proposal.filename
    assert not target.exists()  # reverted
    assert fc.restored  # checkpoint restored
    assert len(sinks["failures"]) == 1
    assert loop._autonomy.state("skills").reverted == 1


def test_constraint_revert_on_hollow_commit(tmp_path):
    # blast_provider claims a hollow commit (changed files but none counted)
    hollow = BlastComputation(
        files=0, lines=0, changed_files=(), ignored_files=("data/cache/x.jsonl",), all_changed_files=("data/cache/x.jsonl",)
    )
    loop, fc, sinks = _make_loop(tmp_path, blast_provider=lambda p: hollow)
    result = loop.run_once()
    assert result.status is ApplyStatus.REVERTED
    assert any("hollow_commit" in r for r in result.reasons)
    assert loop._autonomy.state("skills").reverted == 1


# --- pre-flight blocks ------------------------------------------------------


def _bad_proposal(strategy, summary="auto skill"):
    gene = Gene(
        id="gene_distilled_bad",
        category=EvolutionCategory.OPTIMIZE,
        signals_match=["perf_bottleneck"],
        strategy=strategy,
        summary=summary,
    )
    return gene_to_skill_proposal(gene, source_capsule_count=10, data_hash="h")


def test_preflight_blocks_ethics(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path)
    proposal = _bad_proposal(["bypass the safety validator to proceed", "b", "c"], summary="bypass safety guardrail")
    result = loop.act(proposal)
    assert result.status is ApplyStatus.BLOCKED
    assert any("ethics" in r for r in result.reasons)
    # nothing written, nothing recorded
    assert fc.taken == 0
    assert loop._autonomy.state("skills").applied == 0


def test_preflight_blocks_dangerous_code(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path)
    proposal = _bad_proposal(["run os.system('rm -rf /') now", "exec(user_input)", "eval(payload)"])
    result = loop.act(proposal)
    assert result.status is ApplyStatus.BLOCKED


# --- tier-3 wall ------------------------------------------------------------


def test_walled_surface_blocked(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path, surface="evolution_engine")
    result = loop.run_once()
    assert result.status is ApplyStatus.BLOCKED
    assert any("wall" in r for r in result.reasons)
    assert fc.taken == 0  # never reached checkpoint


# --- gated tier-2 -----------------------------------------------------------


def test_gated_no_channel(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path, surface="safety_rules", approval=None)
    result = loop.run_once()
    assert result.status is ApplyStatus.GATED_NO_CHANNEL


def test_gated_approved(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path, surface="safety_rules", approval=_FakeApproval(allow=True))
    result = loop.run_once()
    assert result.status is ApplyStatus.KEPT


def test_gated_denied(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path, surface="safety_rules", approval=_FakeApproval(allow=False))
    result = loop.run_once()
    assert result.status is ApplyStatus.REJECTED
    target = tmp_path / "data" / "evolution" / "skills" / result.proposal.filename
    assert not target.exists()  # never written


# --- no proposal + idempotency ---------------------------------------------


def test_no_proposal_when_insufficient(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path, caps=_caps(3))
    assert loop.run_once() is None


def test_idempotent_second_run(tmp_path):
    state = EvolutionState()
    caps = _caps(10)
    loop, fc, sinks = _make_loop(tmp_path, caps=caps, state=state)
    first = loop.run_once()
    assert first.status is ApplyStatus.KEPT
    # second run with the SAME capsules -> data hash unchanged -> idempotent skip
    second = loop.run_once()
    assert second is None


def test_loop_result_is_bounded(tmp_path):
    loop, fc, sinks = _make_loop(tmp_path)
    lr = loop.run()
    # one proposal per run; loop completes within max_steps
    assert lr.final_step <= loop.max_steps
    assert lr.status.value in ("completed", "max_steps_exhausted")
