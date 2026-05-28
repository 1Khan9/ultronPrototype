"""Tests for ultron.evolution.skill_distiller -- the local autoDistill
pipeline. Hermetic: pure data; the one filesystem test uses tmp_path."""

from __future__ import annotations

from ultron.evolution import skill_distiller as D
from ultron.evolution.models import (
    DISTILLED_ID_PREFIX,
    REPAIR_DISTILLED_ID_PREFIX,
    Capsule,
    EvolutionCategory,
    Gene,
    GeneConstraints,
    Outcome,
    OutcomeStatus,
)


def _cap(i, *, gene="gene_perf", triggers=("perf_bottleneck",), summary="optimized the slow path", score=0.85, status="success"):
    return Capsule(
        id=f"capsule_{i}",
        gene=gene,
        trigger=list(triggers),
        summary=summary,
        confidence=score,
        outcome=Outcome(status=OutcomeStatus(status), score=score),
    )


def _successes(n=10, **kw):
    return [_cap(i, **kw) for i in range(n)]


# --- expand signals + hashing ----------------------------------------------


def test_expand_signals():
    out = D.expand_signals(["perf_bottleneck", "recurring_error"])
    assert "problem:performance" in out
    assert "action:optimize" in out
    assert "problem:reliability" in out


def test_compute_data_hash_order_independent():
    a = _successes(3)
    b = list(reversed(a))
    assert D.compute_data_hash(a) == D.compute_data_hash(b)
    assert D.compute_data_hash(a) != D.compute_data_hash(_successes(4))


# --- collect + analyze ------------------------------------------------------


def test_collect_filters_and_groups():
    caps = _successes(5) + [_cap(99, score=0.5)] + [_cap(98, status="failed", score=0.9)]
    data = D.collect_distillation_data(caps)
    assert len(data.success_capsules) == 5  # 0.5 score + failed excluded
    assert "gene_perf" in data.grouped
    grp = data.grouped["gene_perf"]
    assert grp.count == 5
    assert grp.triggers[0][0] == "perf_bottleneck"


def test_analyze_high_frequency_and_coverage_gaps():
    data = D.collect_distillation_data(_successes(6))
    analysis = D.analyze_patterns(data)
    assert "gene_perf" in analysis.high_frequency
    assert "perf_bottleneck" in analysis.coverage_gaps
    assert analysis.total_success == 6


def test_analyze_coverage_gap_excludes_covered_signals():
    data = D.collect_distillation_data(_successes(6))
    existing = [Gene(id="g_existing", category="optimize", signals_match=["perf_bottleneck"])]
    analysis = D.analyze_patterns(data, existing_genes=existing)
    assert "perf_bottleneck" not in analysis.coverage_gaps


def test_analyze_strategy_drift():
    caps = [
        _cap(0, summary="fixed the alpha module timing issue"),
        _cap(1, summary="adjusted retries"),
        _cap(2, summary="rewrote the omega cache layer entirely differently"),
    ]
    data = D.collect_distillation_data(caps)
    analysis = D.analyze_patterns(data)
    assert "gene_perf" in analysis.strategy_drift


# --- synthesis --------------------------------------------------------------


def test_synthesize_gene_from_patterns():
    data = D.collect_distillation_data(_successes(10))
    analysis = D.analyze_patterns(data)
    gene = D.synthesize_gene_from_patterns(data, analysis)
    assert gene is not None
    assert gene.id.startswith(DISTILLED_ID_PREFIX)
    assert "perf_bottleneck" in gene.signals_match
    assert "problem:performance" in gene.signals_match
    assert len(gene.strategy) >= D.MIN_STRATEGY_STEPS
    assert gene.category is EvolutionCategory.OPTIMIZE


def test_synthesize_category_inference_repair():
    caps = _successes(6, triggers=("recurring_error",), summary="repaired the failing path")
    data = D.collect_distillation_data(caps)
    gene = D.synthesize_gene_from_patterns(data, D.analyze_patterns(data))
    assert gene.category is EvolutionCategory.REPAIR


def test_synthesize_repair_gene_from_failures():
    failures = [
        {"gene": "gene_x", "trigger": ["log_error"], "reason_class": "validation", "learning_signals": ["risk:validation"]}
        for _ in range(5)
    ]
    gene = D.synthesize_repair_gene_from_failures(failures)
    assert gene is not None
    assert gene.id.startswith(REPAIR_DISTILLED_ID_PREFIX)
    assert gene.category is EvolutionCategory.REPAIR
    assert any("GUARD" in s for s in gene.strategy)


# --- sanitisation + validation ---------------------------------------------


def test_sanitize_signals_match():
    out = D.sanitize_signals_match(["perf_bottleneck", "1234567890123", "errsig:TypeError x", "node", "perf_bottleneck"])
    assert "perf_bottleneck" in out
    assert "errsig" in out  # payload stripped
    assert "node" not in out  # tool name dropped
    assert out.count("perf_bottleneck") == 1  # deduped


def test_validate_ok():
    gene = Gene(
        id=DISTILLED_ID_PREFIX + "perf-fix",
        category="optimize",
        signals_match=["perf_bottleneck"],
        strategy=["a", "b", "c"],
    )
    ok, errors, norm = D.validate_synthesized_gene(gene)
    assert ok is True
    assert errors == ()
    assert ".git" in norm.constraints.forbidden_paths
    assert "node_modules" in norm.constraints.forbidden_paths
    assert norm.constraints.max_files <= 12


def test_validate_too_few_strategy_steps():
    gene = Gene(id=DISTILLED_ID_PREFIX + "x", category="optimize", signals_match=["s"], strategy=["only one"])
    ok, errors, _ = D.validate_synthesized_gene(gene)
    assert ok is False
    assert any("strategy" in e for e in errors)


def test_validate_adds_prefix_to_bare_id():
    gene = Gene(id="bare_id", category="optimize", signals_match=["perf_bottleneck"], strategy=["a", "b", "c"])
    _, _, norm = D.validate_synthesized_gene(gene)
    assert norm.id.startswith(DISTILLED_ID_PREFIX)


def test_validate_dedupes_duplicate_id():
    existing = [Gene(id=DISTILLED_ID_PREFIX + "perf-fix", category="optimize", signals_match=["other"])]
    gene = Gene(id=DISTILLED_ID_PREFIX + "perf-fix", category="optimize", signals_match=["perf_bottleneck"], strategy=["a", "b", "c"])
    _, _, norm = D.validate_synthesized_gene(gene, existing_genes=existing)
    assert norm.id != existing[0].id


def test_validate_rejects_full_overlap():
    existing = [Gene(id="g_e", category="optimize", signals_match=["perf_bottleneck"])]
    gene = Gene(id=DISTILLED_ID_PREFIX + "x", category="optimize", signals_match=["perf_bottleneck"], strategy=["a", "b", "c"])
    ok, errors, _ = D.validate_synthesized_gene(gene, existing_genes=existing)
    assert ok is False
    assert any("overlap" in e for e in errors)


# --- slug + triggers --------------------------------------------------------


def test_sanitize_skill_slug():
    assert D.sanitize_skill_slug(DISTILLED_ID_PREFIX + "perf_fix_1700000000000") == "perf-fix"
    fallback = D.sanitize_skill_slug("gene_distilled_99999999999999", signals=["perf_bottleneck"], summary="speed")
    assert fallback and not fallback.isdigit()
    tool = D.sanitize_skill_slug("gene_distilled_cursor", signals=["perf_bottleneck"], summary="speed")
    assert tool != "cursor"


def test_derive_triggers_non_empty():
    gene = Gene(id=DISTILLED_ID_PREFIX + "x", category="optimize", signals_match=["perf_bottleneck"], summary="speed up rendering")
    triggers = D.derive_triggers(gene)
    assert triggers
    assert all(len(t) >= 3 for t in triggers)


# --- rendering --------------------------------------------------------------


def test_render_skill_markdown_has_frontmatter():
    md = D.render_skill_markdown(
        slug="perf-fix",
        title="Perf Fix",
        description="Speed up the slow path.",
        triggers=["perf", "slow"],
        strategy=["step a", "step b", "step c"],
        category=EvolutionCategory.OPTIMIZE,
        signals_match=["perf_bottleneck"],
        source_capsule_count=10,
        data_hash="abc123",
    )
    assert md.startswith("---\n")
    assert "name: perf-fix" in md
    assert "type: knowledge" in md
    assert "auto_distilled: true" in md
    assert "- " in md  # trigger list


# --- gates ------------------------------------------------------------------


def test_should_distill_insufficient():
    ok, reason = D.should_distill(capsules=_successes(5))
    assert ok is False and reason == "insufficient_successes"


def test_should_distill_low_recent_rate():
    caps = _successes(10) + [_cap(i, status="failed", score=0.0) for i in range(100, 110)]
    ok, reason = D.should_distill(capsules=caps)
    assert ok is False and reason == "low_recent_success_rate"


def test_should_distill_too_recent():
    caps = _successes(10)
    ok, reason = D.should_distill(capsules=caps, last_distillation_at=1000.0, now=1000.0 + 3600)
    assert ok is False and reason == "too_recent"


def test_should_distill_idempotent():
    caps = _successes(10)
    h = D.collect_distillation_data(caps).data_hash
    ok, reason = D.should_distill(capsules=caps, last_data_hash=h)
    assert ok is False and reason == "idempotent_skip"


def test_should_distill_ok():
    ok, reason = D.should_distill(capsules=_successes(10))
    assert ok is True and reason == "ok"


def test_should_distill_disabled():
    ok, reason = D.should_distill(capsules=_successes(10), enabled=False)
    assert ok is False and reason == "disabled"


def test_should_distill_from_failures():
    failures = [{"gene": "g", "reason_class": "validation"} for _ in range(5)]
    assert D.should_distill_from_failures(failures=failures)[0] is True
    assert D.should_distill_from_failures(failures=failures[:2])[0] is False


# --- end-to-end + loader round-trip ----------------------------------------


def test_auto_distill_produces_proposal():
    result = D.auto_distill(_successes(10))
    assert result.ok is True
    assert result.proposal is not None
    assert result.proposal.filename.endswith(".md")
    assert result.proposal.markdown


def test_auto_distill_blocked_when_insufficient():
    result = D.auto_distill(_successes(3))
    assert result.ok is False
    assert result.proposal is None


def test_auto_distill_from_failures_end_to_end():
    failures = [
        {"gene": "gene_x", "trigger": ["log_error"], "reason_class": "validation"} for _ in range(5)
    ]
    result = D.auto_distill_from_failures(failures)
    assert result.ok is True
    assert result.proposal is not None


def test_generated_skill_loads_via_ultron_loader(tmp_path):
    """The headline integration test: a distilled proposal's markdown must
    be loadable by ultron's real skill loader."""
    from ultron.skills.loader import load_skill_from_path

    result = D.auto_distill(_successes(10))
    assert result.ok and result.proposal is not None
    path = tmp_path / result.proposal.filename
    path.write_text(result.proposal.markdown, encoding="utf-8")
    skill = load_skill_from_path(path)
    assert skill is not None
    assert skill.name == result.proposal.slug
