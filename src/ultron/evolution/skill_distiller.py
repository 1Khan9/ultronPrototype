"""Skill distillation: turn accumulated outcomes into a new skill proposal.

Catalog 13 (clawhub-capability-evolver) clean-room synthesis -- the
``autoDistill`` pipeline, which the catalog called the single best
clean-room candidate. It observes ultron's local capsule history (records
of past evolution attempts + their outcomes) and, when enough evidence
has accumulated, synthesises a NEW reusable strategy and materialises it
as an **ultron-compatible ``skills/*.md`` proposal** -- a markdown DATA
file, never generated code, never a JSON gene that drives execution.

The fully-local pipeline (no LLM, no hub):

1. :func:`collect_distillation_data` -- read capsules, keep successes with
   score >= 0.7, group by the gene that produced them, hash the corpus.
2. :func:`analyze_patterns` -- find high-frequency genes (5+ successes),
   strategy drift (diverging summaries), and coverage gaps (frequent
   signals no gene covers).
3. :func:`synthesize_gene_from_patterns` -- pick the strongest group and
   derive a :class:`~ultron.evolution.models.Gene` (signals + category +
   strategy), OR :func:`synthesize_repair_gene_from_failures` for the
   defensive failure path.
4. :func:`validate_synthesized_gene` -- enforce the id prefix, >=3 strategy
   steps, forbidden-paths + max-files caps, and the validation-command
   allowlist; reject duplicates / full-overlap genes.
5. :func:`gene_to_skill_proposal` + :func:`render_skill_markdown` -- render
   the gene as a loadable ultron skill markdown file.

The gates (:func:`should_distill`) require a minimum corpus, a healthy
recent success rate, a cooldown interval, and data-hash idempotency so the
same evidence never re-distils.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from ultron.evolution.blast_radius import filter_validation_commands
from ultron.evolution.models import (
    DISTILLED_GENE_MAX_FILES,
    DISTILLED_ID_PREFIX,
    REPAIR_DISTILLED_ID_PREFIX,
    EvolutionCategory,
    Gene,
    GeneConstraints,
    OutcomeStatus,
)

# --- gate constants (ultron-calibrated) -------------------------------------

DISTILLER_MIN_CAPSULES: int = 10  # total successes before distilling
DISTILLER_RECENT_WINDOW: int = 10
DISTILLER_MIN_RECENT_SUCCESS: int = 7  # of the last DISTILLER_RECENT_WINDOW
DISTILLER_INTERVAL_HOURS: float = 24.0
DISTILLER_MIN_SUCCESS_SCORE: float = 0.7

FAILURE_DISTILLER_MIN_CAPSULES: int = 5
FAILURE_DISTILLER_INTERVAL_HOURS: float = 12.0

MIN_STRATEGY_STEPS: int = 3
HIGH_FREQUENCY_THRESHOLD: int = 5
#: Catalog 14 (T4): a pattern_key whose summed recurrence reaches this is
#: "promotion-worthy" -- the explicit, auditable form of the upstream's
#: "Recurrence-Count >= 3 across 2+ tasks" promote rule.
RECURRENCE_PROMOTE_THRESHOLD: int = 3
STRATEGY_DRIFT_JACCARD: float = 0.6
COVERAGE_GAP_MIN_OCCURRENCES: int = 3
MAX_TRIGGERS_PER_SKILL: int = 6
MAX_SIGNALS_PER_GENE: int = 7
SLUG_MAX_CHARS: int = 48
SUMMARY_MIN_CHARS: int = 30
SUMMARY_MAX_CHARS: int = 200

#: Generic tool / runtime names that must never become a skill slug on
#: their own (a slug should describe a CAPABILITY, not an editor / runtime).
_TOOL_NAME_SLUGS: frozenset[str] = frozenset(
    {"vscode", "vim", "emacs", "nano", "node", "npm", "pip", "git", "shell", "terminal"}
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "your",
        "you",
        "are",
        "was",
        "has",
        "have",
        "when",
        "what",
        "which",
        "their",
        "them",
        "they",
        "will",
        "would",
        "should",
        "could",
        "about",
        "over",
        "than",
        "then",
        "some",
        "more",
        "most",
        "such",
        "only",
        "also",
        "very",
    }
)

#: Maps a signal base name to the structured learning tags it implies
#: (the ``expandSignals`` pattern). Used to enrich a synthesised gene's
#: ``signals_match`` so future cycles can match on the abstract problem.
_SIGNAL_EXPANSION: dict[str, tuple[str, ...]] = {
    "perf_bottleneck": ("problem:performance", "action:optimize"),
    "capability_gap": ("problem:capability", "action:add_capability"),
    "stable_success_plateau": ("problem:stagnation",),
    "recurring_error": ("problem:reliability", "action:repair"),
    "log_error": ("problem:reliability", "action:repair"),
    "user_feature_request": ("problem:capability", "action:add_feature"),
    "user_improvement_suggestion": ("action:improve",),
    "unsupported_input_type": ("problem:capability", "area:input_handling"),
    "evolution_stagnation_detected": ("problem:stagnation",),
    "tool_bypass": ("problem:reliability", "area:tooling"),
}

_CATEGORY_KEYWORDS = {
    EvolutionCategory.REPAIR: ("error", "fail", "reliability", "repair", "bug", "crash"),
    EvolutionCategory.INNOVATE: (
        "feature",
        "capability",
        "stagnation",
        "innovate",
        "add",
        "new",
        "explore",
    ),
}


# --- dataclasses ------------------------------------------------------------


@dataclass(frozen=True)
class GeneGroup:
    """Aggregated successful capsules that share a gene."""

    gene_id: str
    count: int
    total_score: float
    avg_score: float
    triggers: tuple[tuple[str, int], ...] = ()  # (signal, frequency), desc
    summaries: tuple[str, ...] = ()
    dominant_pattern_key: str = ""  # catalog 14 T4: most-common pattern_key among members
    pattern_recurrence: int = 0  # catalog 14 T4: summed recurrence for the dominant key


@dataclass(frozen=True)
class DistillationData:
    """The collected corpus for a distillation run."""

    success_capsules: tuple[Any, ...] = ()
    all_capsules: tuple[Any, ...] = ()
    grouped: Mapping[str, GeneGroup] = field(default_factory=dict)
    data_hash: str = ""
    pattern_recurrence: Mapping[str, int] = field(default_factory=dict)  # catalog 14 T4


@dataclass(frozen=True)
class PatternAnalysis:
    """Patterns found across the success corpus."""

    high_frequency: tuple[str, ...] = ()  # gene ids with HIGH_FREQUENCY_THRESHOLD+
    strategy_drift: tuple[str, ...] = ()  # gene ids whose summaries diverged
    coverage_gaps: tuple[str, ...] = ()  # frequent signals no gene covers
    total_success: int = 0
    recurring_patterns: tuple[str, ...] = ()  # catalog 14 T4: pattern_keys >= RECURRENCE_PROMOTE_THRESHOLD


@dataclass(frozen=True)
class SkillProposal:
    """A fully-rendered, loadable skill-markdown proposal.

    ``markdown`` is written to ``<proposal dir>/<filename>`` by the
    evolution loop -- the data-only output of the whole pipeline.
    """

    slug: str
    title: str
    description: str
    triggers: tuple[str, ...]
    strategy: tuple[str, ...]
    category: EvolutionCategory
    signals_match: tuple[str, ...]
    source_capsule_count: int
    gene: Gene
    markdown: str
    filename: str
    data_hash: str = ""


@dataclass(frozen=True)
class DistillResult:
    """The outcome of an :func:`auto_distill` run."""

    ok: bool
    reason: str
    proposal: Optional[SkillProposal] = None


# --- capsule accessors ------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _capsule_id(c: Any) -> str:
    return str(_get(c, "id", "") or "")


def _capsule_gene(c: Any) -> str:
    g = _get(c, "gene", "") or "ad_hoc"
    return str(g)


def _capsule_triggers(c: Any) -> tuple[str, ...]:
    t = _get(c, "trigger") or _get(c, "triggers") or ()
    if isinstance(t, str):
        return (t,)
    return tuple(str(x) for x in t)


def _capsule_summary(c: Any) -> str:
    return str(_get(c, "summary", "") or "")


def _capsule_status(c: Any) -> str:
    outcome = _get(c, "outcome")
    if isinstance(outcome, str):
        return outcome.lower()
    status = _get(outcome, "status", "") if outcome is not None else ""
    status = getattr(status, "value", status)
    return str(status).lower() if status else ""


def _capsule_score(c: Any) -> float:
    outcome = _get(c, "outcome")
    score = _get(outcome, "score", 0.0) if outcome is not None else 0.0
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _capsule_pattern_key(c: Any) -> str:
    """The stable recurrence key on a capsule (``""`` when absent)."""
    return str(_get(c, "pattern_key", "") or "")


def _capsule_recurrence(c: Any) -> int:
    """The recurrence count on a capsule (>=1; defaults to 1 when absent)."""
    try:
        return max(1, int(_get(c, "recurrence_count", 1) or 1))
    except (TypeError, ValueError):
        return 1


# --- pattern-key recurrence (catalog 14, T4) --------------------------------


@dataclass(frozen=True)
class MergedPattern:
    """Capsules collapsed by their shared ``pattern_key`` (catalog 14, T4).

    The explicit, auditable form of "this pattern recurred N times" -- used
    by the distiller's recurrence gate + the service digest.
    """

    pattern_key: str
    capsule_count: int
    total_recurrence: int
    triggers: tuple[tuple[str, int], ...] = ()
    first_seen: str = ""
    last_seen: str = ""
    representative_summary: str = ""


def merge_capsules_by_pattern_key(capsules: Sequence[Any]) -> dict[str, "MergedPattern"]:
    """Collapse capsules sharing a non-empty ``pattern_key`` into one
    :class:`MergedPattern` each (summing recurrence, unioning triggers,
    tracking first / last seen). Capsules with no pattern_key are skipped
    so each stays distinct -- back-compatible with the legacy capsule log."""
    groups: dict[str, list[Any]] = {}
    for c in capsules:
        pk = _capsule_pattern_key(c)
        if pk:
            groups.setdefault(pk, []).append(c)
    out: dict[str, MergedPattern] = {}
    for pk, members in groups.items():
        trig: Counter[str] = Counter()
        for m in members:
            for t in _capsule_triggers(m):
                trig[t] += 1
        firsts = [s for s in (str(_get(m, "first_seen", "") or "") for m in members) if s]
        lasts = [s for s in (str(_get(m, "last_seen", "") or "") for m in members) if s]
        summaries = [_capsule_summary(m) for m in members if _capsule_summary(m)]
        out[pk] = MergedPattern(
            pattern_key=pk,
            capsule_count=len(members),
            # Recurrence = number of recorded occurrences (rows) of this
            # pattern. Robust regardless of whether a row's recurrence_count
            # field is per-occurrence (1) or cumulative -- the service appends
            # one row per occurrence, so the row count is the true frequency.
            total_recurrence=len(members),
            triggers=tuple(trig.most_common()),
            first_seen=min(firsts) if firsts else "",
            last_seen=max(lasts) if lasts else "",
            representative_summary=_best_summary(summaries),
        )
    return out


# --- expand signals ---------------------------------------------------------


def expand_signals(signals: Sequence[str]) -> tuple[str, ...]:
    """Expand weak signals into structured learning tags (``problem:*`` /
    ``action:*`` / ``area:*``)."""
    out: list[str] = []
    for s in signals:
        base = s.split(":", 1)[0]
        out.extend(_SIGNAL_EXPANSION.get(base, ()))
    return _dedupe(out)


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return tuple(out)


# --- collect + analyze ------------------------------------------------------


def compute_data_hash(capsules: Sequence[Any]) -> str:
    """A stable hash of a capsule set (order-independent) for idempotency."""
    ids = sorted(_capsule_id(c) for c in capsules if _capsule_id(c))
    payload = "|".join(ids)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def collect_distillation_data(
    capsules: Sequence[Any],
    *,
    min_score: float = DISTILLER_MIN_SUCCESS_SCORE,
) -> DistillationData:
    """Read + dedup capsules, filter to successes >= ``min_score``, group by
    gene, and hash the success corpus."""
    deduped: dict[str, Any] = {}
    for c in capsules:
        cid = _capsule_id(c)
        if cid:
            deduped[cid] = c
    all_capsules = tuple(deduped.values())
    successes = tuple(
        c
        for c in all_capsules
        if _capsule_status(c) == "success" and _capsule_score(c) >= min_score
    )

    # catalog 14 T4: summed recurrence per non-empty pattern_key (auditable).
    pattern_recurrence = {
        pk: mp.total_recurrence for pk, mp in merge_capsules_by_pattern_key(successes).items()
    }

    by_gene: dict[str, list[Any]] = {}
    for c in successes:
        by_gene.setdefault(_capsule_gene(c), []).append(c)

    grouped: dict[str, GeneGroup] = {}
    for gene_id, members in by_gene.items():
        count = len(members)
        total = sum(_capsule_score(m) for m in members)
        trig_counter: Counter[str] = Counter()
        pk_counter: Counter[str] = Counter()
        for m in members:
            for t in _capsule_triggers(m):
                trig_counter[t] += 1
            pk = _capsule_pattern_key(m)
            if pk:
                pk_counter[pk] += 1  # row count == recurrence (see merge_capsules_by_pattern_key)
        summaries = tuple(_capsule_summary(m) for m in members if _capsule_summary(m))
        dom_pk, dom_rec = pk_counter.most_common(1)[0] if pk_counter else ("", 0)
        grouped[gene_id] = GeneGroup(
            gene_id=gene_id,
            count=count,
            total_score=total,
            avg_score=(total / count) if count else 0.0,
            triggers=tuple(trig_counter.most_common()),
            summaries=summaries,
            dominant_pattern_key=dom_pk,
            pattern_recurrence=dom_rec,
        )

    return DistillationData(
        success_capsules=successes,
        all_capsules=all_capsules,
        grouped=grouped,
        data_hash=compute_data_hash(successes),
        pattern_recurrence=pattern_recurrence,
    )


def _jaccard(a: str, b: str) -> float:
    wa = {w for w in re.findall(r"[a-z0-9]+", a.lower()) if len(w) > 2}
    wb = {w for w in re.findall(r"[a-z0-9]+", b.lower()) if len(w) > 2}
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def analyze_patterns(
    data: DistillationData,
    *,
    existing_genes: Sequence[Gene] = (),
) -> PatternAnalysis:
    """Find high-frequency genes, strategy drift, and coverage gaps."""
    high_freq = tuple(
        gid for gid, grp in data.grouped.items() if grp.count >= HIGH_FREQUENCY_THRESHOLD
    )

    drift: list[str] = []
    for gid, grp in data.grouped.items():
        if len(grp.summaries) >= 3:
            if _jaccard(grp.summaries[0], grp.summaries[-1]) < STRATEGY_DRIFT_JACCARD:
                drift.append(gid)

    # coverage gaps: signals seen COVERAGE_GAP_MIN_OCCURRENCES+ across all
    # success triggers that no existing gene matches.
    covered: set[str] = set()
    for g in existing_genes:
        for s in getattr(g, "signals_match", ()):
            covered.add(s.split(":", 1)[0])
    sig_counter: Counter[str] = Counter()
    for grp in data.grouped.values():
        for sig, freq in grp.triggers:
            sig_counter[sig.split(":", 1)[0]] += freq
    gaps = tuple(
        sig
        for sig, n in sig_counter.most_common()
        if n >= COVERAGE_GAP_MIN_OCCURRENCES and sig not in covered
    )

    # catalog 14 T4: pattern_keys whose summed recurrence is promotion-worthy.
    recurring = tuple(
        sorted(
            pk
            for pk, total in data.pattern_recurrence.items()
            if total >= RECURRENCE_PROMOTE_THRESHOLD
        )
    )

    return PatternAnalysis(
        high_frequency=high_freq,
        strategy_drift=tuple(drift),
        coverage_gaps=gaps,
        total_success=len(data.success_capsules),
        recurring_patterns=recurring,
    )


# --- synthesis --------------------------------------------------------------


def _infer_category(signals: Sequence[str]) -> EvolutionCategory:
    """Infer a gene category from its signal keywords."""
    blob = " ".join(signals).lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(k in blob for k in keywords):
            return category
    return EvolutionCategory.OPTIMIZE


def _best_summary(summaries: Sequence[str]) -> str:
    """Pick a representative summary (the most common, else the longest)."""
    summaries = [s for s in summaries if s.strip()]
    if not summaries:
        return ""
    counts = Counter(summaries)
    top, n = counts.most_common(1)[0]
    if n > 1:
        return top
    return max(summaries, key=len)


def _clip_summary(text: str, fallback: str) -> str:
    text = " ".join(text.split())
    if len(text) < SUMMARY_MIN_CHARS:
        text = (text + " " + fallback).strip()
    return text[:SUMMARY_MAX_CHARS]


def _default_success_strategy(category: EvolutionCategory) -> tuple[str, ...]:
    """The 4-step default strategy for a distilled success gene."""
    return (
        "Identify the recurring pattern these signals represent.",
        "Apply the smallest change that addresses it.",
        "Run the narrowest validation that confirms the change.",
        "Roll back automatically if any guardrail regresses.",
    )


def synthesize_gene_from_patterns(
    data: DistillationData,
    analysis: PatternAnalysis,
    *,
    existing_genes: Sequence[Gene] = (),
) -> Optional[Gene]:
    """Algorithmically synthesise a gene from the strongest success group.

    Picks the group maximising ``count * 2 + avg_score``, derives its
    signals (top triggers + expansion tags), infers a category, and builds
    a default strategy. Returns ``None`` when there is no usable group.
    """
    if not data.grouped:
        return None

    def _group_score(gid: str) -> float:
        grp = data.grouped[gid]
        # catalog 14 T4: a strongly-recurring pattern (by pattern_key) is
        # preferred. Capsules without a pattern_key contribute 0 here, so the
        # legacy ``count * 2 + avg_score`` ordering is byte-identical when no
        # capsule carries recurrence metadata.
        recurrence_bonus = min(grp.pattern_recurrence, 10) * 0.5
        return grp.count * 2 + grp.avg_score + recurrence_bonus

    best_id = max(data.grouped, key=_group_score)
    group = data.grouped[best_id]
    if group.count <= 0:
        return None

    top_signals = [sig for sig, _ in group.triggers[:MAX_SIGNALS_PER_GENE]]
    signals_match = _dedupe([*top_signals, *expand_signals(top_signals)])[:MAX_SIGNALS_PER_GENE]
    if not signals_match:
        signals_match = ("stable_success_plateau",)
    category = _infer_category(signals_match)
    summary = _clip_summary(
        _best_summary(group.summaries),
        fallback=f"Reusable {category.value} strategy distilled from {group.count} successes.",
    )
    slug = _derive_slug_from_signals(signals_match, summary)
    gene = Gene(
        id=DISTILLED_ID_PREFIX + slug,
        category=category,
        signals_match=signals_match,
        strategy=_default_success_strategy(category),
        preconditions=(f"Signals contain one of: {', '.join(signals_match[:3])}.",),
        constraints=GeneConstraints(max_files=DISTILLED_GENE_MAX_FILES),
        summary=summary,
    )
    return gene


def synthesize_repair_gene_from_failures(
    failures: Sequence[Any],
    *,
    existing_genes: Sequence[Gene] = (),
) -> Optional[Gene]:
    """Synthesise a DEFENSIVE repair gene from the dominant failure pattern.

    ``failures`` are failure records (mappings/objects) with ``gene`` /
    ``trigger`` / ``reason_class`` (or ``failure_reason``) /
    ``learning_signals`` fields. Builds a GUARD/APPLY/VERIFY/ROLLBACK
    strategy. Returns ``None`` when there is nothing to learn from.
    """
    if not failures:
        return None
    groups: dict[str, list[Any]] = {}
    for f in failures:
        reason = str(_get(f, "reason_class", "") or _get(f, "failure_reason", "") or "unknown")
        gene_id = str(_get(f, "gene", "") or "ad_hoc")
        groups.setdefault(f"{gene_id}::{reason}", []).append(f)
    top_key = max(groups, key=lambda k: len(groups[k]))
    members = groups[top_key]

    trig_counter: Counter[str] = Counter()
    learning: Counter[str] = Counter()
    for m in members:
        for t in _capsule_triggers(m):
            trig_counter[t] += 1
        for s in _get(m, "learning_signals", ()) or ():
            learning[str(s)] += 1
    top_signals = [s for s, _ in trig_counter.most_common(MAX_SIGNALS_PER_GENE)]
    signals_match = _dedupe(
        [*top_signals, *[s for s, _ in learning.most_common(3)], *expand_signals(top_signals)]
    )[:MAX_SIGNALS_PER_GENE]
    if not signals_match:
        signals_match = ("recurring_error",)
    reason = top_key.split("::", 1)[-1]
    summary = _clip_summary(
        f"Defensive repair for repeated {reason} failures.",
        fallback="Guards a known failure mode before retrying.",
    )
    slug = _derive_slug_from_signals(signals_match, summary)
    gene = Gene(
        id=REPAIR_DISTILLED_ID_PREFIX + slug,
        category=EvolutionCategory.REPAIR,
        signals_match=signals_match,
        strategy=(
            "GUARD: check the precondition that previously failed before acting.",
            "APPLY: make the minimal corrective change.",
            "VERIFY: confirm the failing condition is resolved.",
            "ROLLBACK: revert immediately if verification still fails.",
            "RECORD: note the guard so the failure does not recur.",
        ),
        preconditions=(f"A {reason} failure has been observed before.",),
        constraints=GeneConstraints(max_files=DISTILLED_GENE_MAX_FILES),
        summary=summary,
    )
    return gene


# --- validation -------------------------------------------------------------

_TIMESTAMP_RE = re.compile(r"\d{10,}")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _sanitize_signal(sig: str) -> str:
    """Strip a timestamp / random suffix off a dynamic signal, keeping the
    base + any structured prefix tag."""
    base = sig.split(":", 1)[0]
    if base in ("errsig", "recurring_errsig", "ban_gene", "high_tool_usage"):
        return base
    return sig


def sanitize_signals_match(signals: Sequence[str]) -> tuple[str, ...]:
    """Sanitise + dedup a gene's signal list (drop timestamps / pure
    numerics / tool names)."""
    out: list[str] = []
    for s in signals:
        s = _sanitize_signal(s.strip())
        if not s or _TIMESTAMP_RE.fullmatch(s) or s.isdigit():
            continue
        if s.split(":", 1)[0] in _TOOL_NAME_SLUGS:
            continue
        out.append(s)
    return _dedupe(out)


def validate_synthesized_gene(
    gene: Gene,
    *,
    existing_genes: Sequence[Gene] = (),
) -> tuple[bool, tuple[str, ...], Gene]:
    """Normalise + validate a synthesised gene.

    Enforces the distilled id prefix, sanitises signals, requires >=3
    strategy steps, ensures ``.git`` + ``node_modules`` are forbidden and
    ``max_files`` <= the distilled cap, filters validation commands through
    the allowlist, de-duplicates the id against existing genes, and rejects
    a gene whose signals fully overlap an existing one. Returns
    ``(ok, errors, normalised_gene)``.
    """
    from dataclasses import replace

    errors: list[str] = []

    gene_id = gene.id
    if not (gene_id.startswith(DISTILLED_ID_PREFIX) or gene_id.startswith(REPAIR_DISTILLED_ID_PREFIX)):
        gene_id = DISTILLED_ID_PREFIX + sanitize_skill_slug(gene_id, gene.signals_match, gene.summary)

    signals = sanitize_signals_match(gene.signals_match)
    if not signals:
        errors.append("no usable signals after sanitisation")

    strategy = tuple(s for s in gene.strategy if s and s.strip())
    if len(strategy) < MIN_STRATEGY_STEPS:
        errors.append(f"strategy has {len(strategy)} steps, need >= {MIN_STRATEGY_STEPS}")

    forbidden = tuple(_dedupe([*gene.constraints.forbidden_paths, ".git", "node_modules"]))
    max_files = min(gene.constraints.max_files, DISTILLED_GENE_MAX_FILES)
    validation = filter_validation_commands(gene.validation)

    # duplicate-id suffix
    existing_ids = {g.id for g in existing_genes}
    if gene_id in existing_ids:
        gene_id = f"{gene_id}_{int(time.time() * 1000) % 100000:05d}"

    # full-overlap rejection
    new_sig_set = {s.split(':', 1)[0] for s in signals}
    for g in existing_genes:
        existing_set = {s.split(':', 1)[0] for s in getattr(g, "signals_match", ())}
        if new_sig_set and existing_set and new_sig_set == existing_set and g.category == gene.category:
            errors.append(f"signals fully overlap existing gene {g.id}")
            break

    normalised = replace(
        gene,
        id=gene_id,
        signals_match=signals,
        strategy=strategy,
        constraints=GeneConstraints(max_files=max_files, forbidden_paths=forbidden),
        validation=validation,
    )
    return (len(errors) == 0, tuple(errors), normalised)


# --- slug + trigger derivation ----------------------------------------------


def _words_from(*texts: str) -> list[str]:
    words: list[str] = []
    for t in texts:
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            if len(w) >= 3 and w not in _STOPWORDS and not w.isdigit():
                words.append(w)
    return words


def _derive_slug_from_signals(signals: Sequence[str], summary: str) -> str:
    """Build a short descriptive slug from signal tags + summary words."""
    tokens: list[str] = []
    for s in signals:
        # take the part after a structured prefix, else the base
        part = s.split(":", 1)[-1] if ":" in s else s
        tokens.extend(re.findall(r"[a-z0-9]+", part.lower()))
    tokens.extend(_words_from(summary))
    tokens = [t for t in tokens if len(t) >= 3 and t not in _STOPWORDS][:4]
    slug = "-".join(tokens) if tokens else "evolved-skill"
    slug = _NON_SLUG_RE.sub("-", slug).strip("-")
    return slug[:SLUG_MAX_CHARS] or "evolved-skill"


def sanitize_skill_slug(raw: str, signals: Sequence[str] = (), summary: str = "") -> str:
    """Sanitise a raw id into a clean skill slug.

    Strips the distilled prefixes + embedded timestamps, kebab-cases, and
    falls back to a signal/summary-derived slug when the result is empty,
    pure-numeric, or just a tool name.
    """
    s = raw
    for prefix in (REPAIR_DISTILLED_ID_PREFIX, DISTILLED_ID_PREFIX, "gene_"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
            break
    s = _TIMESTAMP_RE.sub("", s)
    s = _NON_SLUG_RE.sub("-", s.lower()).strip("-")
    while "--" in s:
        s = s.replace("--", "-")
    if not s or s.isdigit() or s in _TOOL_NAME_SLUGS:
        s = _derive_slug_from_signals(signals, summary)
    return s[:SLUG_MAX_CHARS] or "evolved-skill"


def derive_triggers(gene: Gene) -> tuple[str, ...]:
    """Derive human-readable trigger keywords for the skill frontmatter.

    Pulls content words out of the gene's signals + summary so the
    distilled skill actually fires on relevant user text. Always returns at
    least one trigger (so the skill is keyword-gated, never always-on)."""
    candidates: list[str] = []
    for s in gene.signals_match:
        part = s.split(":", 1)[-1] if ":" in s else s
        candidates.extend(re.findall(r"[a-z0-9]+", part.lower()))
    candidates.extend(_words_from(gene.summary))
    triggers = _dedupe([c for c in candidates if len(c) >= 3 and c not in _STOPWORDS])
    triggers = triggers[:MAX_TRIGGERS_PER_SKILL]
    if not triggers:
        triggers = tuple(p for p in sanitize_skill_slug(gene.id).split("-") if p)[:MAX_TRIGGERS_PER_SKILL]
    return tuple(triggers) or ("evolved",)


# --- proposal rendering -----------------------------------------------------


def _yaml_scalar(value: str) -> str:
    """Render a string as a YAML-safe double-quoted scalar (JSON is valid
    YAML for scalars)."""
    import json

    return json.dumps(value, ensure_ascii=False)


def render_skill_markdown(
    *,
    slug: str,
    title: str,
    description: str,
    triggers: Sequence[str],
    strategy: Sequence[str],
    category: EvolutionCategory,
    signals_match: Sequence[str],
    source_capsule_count: int,
    data_hash: str,
) -> str:
    """Render an ultron-loadable knowledge-skill markdown file.

    The frontmatter matches the schema ``skills/loader.py`` parses (name /
    type / version / description / triggers / min_user_text_chars, plus
    provenance keys that pass through to ``Skill.extra``). The body is the
    knowledge injected into the system prompt when a trigger matches.
    """
    lines: list[str] = ["---"]
    lines.append(f"name: {slug}")
    lines.append("type: knowledge")
    lines.append("version: 1.0.0")
    lines.append(f"description: {_yaml_scalar(description)}")
    lines.append("min_user_text_chars: 8")
    lines.append("auto_distilled: true")
    lines.append(f"source_capsule_count: {int(source_capsule_count)}")
    lines.append(f"evolution_data_hash: {_yaml_scalar(data_hash)}")
    lines.append("triggers:")
    for t in triggers:
        lines.append(f"  - {_yaml_scalar(t)}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(description)
    lines.append("")
    lines.append("## When this applies")
    for sig in signals_match[:6]:
        lines.append(f"- Signal: `{sig}`")
    lines.append("")
    lines.append("## Approach")
    for i, step in enumerate(strategy, 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    lines.append("## Provenance")
    lines.append(f"- Category: `{category.value}`")
    lines.append(
        f"- Auto-distilled by ultron's evolution loop from {int(source_capsule_count)} "
        "successful outcome(s)."
    )
    lines.append(
        "- Generated data. Safe to delete, or promote to the curated `skills/` "
        "directory to keep it permanently."
    )
    lines.append("")
    return "\n".join(lines)


def gene_to_skill_proposal(
    gene: Gene,
    *,
    source_capsule_count: int,
    data_hash: str = "",
) -> SkillProposal:
    """Convert a validated gene into a rendered :class:`SkillProposal`."""
    slug = sanitize_skill_slug(gene.id, gene.signals_match, gene.summary)
    title = " ".join(w.capitalize() for w in slug.split("-")) or "Evolved Skill"
    description = gene.summary or f"A {gene.category.value} strategy ultron distilled from experience."
    triggers = derive_triggers(gene)
    markdown = render_skill_markdown(
        slug=slug,
        title=title,
        description=description,
        triggers=triggers,
        strategy=gene.strategy,
        category=gene.category,
        signals_match=gene.signals_match,
        source_capsule_count=source_capsule_count,
        data_hash=data_hash,
    )
    return SkillProposal(
        slug=slug,
        title=title,
        description=description,
        triggers=triggers,
        strategy=gene.strategy,
        category=gene.category,
        signals_match=gene.signals_match,
        source_capsule_count=source_capsule_count,
        gene=gene,
        markdown=markdown,
        filename=f"{slug}.md",
        data_hash=data_hash,
    )


# --- gates ------------------------------------------------------------------


def should_distill(
    *,
    capsules: Sequence[Any],
    last_distillation_at: Optional[float] = None,
    last_data_hash: str = "",
    now: Optional[float] = None,
    enabled: bool = True,
) -> tuple[bool, str]:
    """Decide whether a success distillation should run.

    Requires the feature enabled, >= :data:`DISTILLER_MIN_CAPSULES` total
    successes, >= :data:`DISTILLER_MIN_RECENT_SUCCESS` of the last
    :data:`DISTILLER_RECENT_WINDOW` capsules successful, the cooldown
    interval elapsed, and a corpus hash different from the last run.
    Returns ``(ok, reason)``.
    """
    if not enabled:
        return (False, "disabled")
    now = now if now is not None else time.time()
    data = collect_distillation_data(capsules)
    if len(data.success_capsules) < DISTILLER_MIN_CAPSULES:
        return (False, "insufficient_successes")
    recent = list(capsules)[-DISTILLER_RECENT_WINDOW:]
    recent_success = sum(1 for c in recent if _capsule_status(c) == "success")
    if recent_success < DISTILLER_MIN_RECENT_SUCCESS:
        return (False, "low_recent_success_rate")
    if last_distillation_at is not None and (now - last_distillation_at) < DISTILLER_INTERVAL_HOURS * 3600:
        return (False, "too_recent")
    if last_data_hash and data.data_hash == last_data_hash:
        return (False, "idempotent_skip")
    return (True, "ok")


def should_distill_from_failures(
    *,
    failures: Sequence[Any],
    last_distillation_at: Optional[float] = None,
    now: Optional[float] = None,
    enabled: bool = True,
) -> tuple[bool, str]:
    """Decide whether a failure (repair) distillation should run."""
    if not enabled:
        return (False, "disabled")
    now = now if now is not None else time.time()
    if len(failures) < FAILURE_DISTILLER_MIN_CAPSULES:
        return (False, "insufficient_failures")
    if (
        last_distillation_at is not None
        and (now - last_distillation_at) < FAILURE_DISTILLER_INTERVAL_HOURS * 3600
    ):
        return (False, "too_recent")
    return (True, "ok")


# --- top-level auto-distill -------------------------------------------------


def auto_distill(
    capsules: Sequence[Any],
    *,
    existing_genes: Sequence[Gene] = (),
    last_distillation_at: Optional[float] = None,
    last_data_hash: str = "",
    now: Optional[float] = None,
    enabled: bool = True,
) -> DistillResult:
    """Run the full local success-distillation pipeline. Never raises."""
    ok, reason = should_distill(
        capsules=capsules,
        last_distillation_at=last_distillation_at,
        last_data_hash=last_data_hash,
        now=now,
        enabled=enabled,
    )
    if not ok:
        return DistillResult(ok=False, reason=reason)
    try:
        data = collect_distillation_data(capsules)
        analysis = analyze_patterns(data, existing_genes=existing_genes)
        gene = synthesize_gene_from_patterns(data, analysis, existing_genes=existing_genes)
        if gene is None:
            return DistillResult(ok=False, reason="no_synthesizable_pattern")
        valid, errors, gene = validate_synthesized_gene(gene, existing_genes=existing_genes)
        if not valid:
            return DistillResult(ok=False, reason="; ".join(errors))
        proposal = gene_to_skill_proposal(
            gene,
            source_capsule_count=len(data.success_capsules),
            data_hash=data.data_hash,
        )
        return DistillResult(ok=True, reason="distilled", proposal=proposal)
    except Exception as exc:  # noqa: BLE001 -- distillation never crashes the loop
        return DistillResult(ok=False, reason=f"error: {type(exc).__name__}: {exc}")


def auto_distill_from_failures(
    failures: Sequence[Any],
    *,
    existing_genes: Sequence[Gene] = (),
    last_distillation_at: Optional[float] = None,
    now: Optional[float] = None,
    enabled: bool = True,
) -> DistillResult:
    """Run the full local failure (repair) distillation pipeline. Never
    raises."""
    ok, reason = should_distill_from_failures(
        failures=failures, last_distillation_at=last_distillation_at, now=now, enabled=enabled
    )
    if not ok:
        return DistillResult(ok=False, reason=reason)
    try:
        gene = synthesize_repair_gene_from_failures(failures, existing_genes=existing_genes)
        if gene is None:
            return DistillResult(ok=False, reason="no_synthesizable_pattern")
        valid, errors, gene = validate_synthesized_gene(gene, existing_genes=existing_genes)
        if not valid:
            return DistillResult(ok=False, reason="; ".join(errors))
        proposal = gene_to_skill_proposal(
            gene, source_capsule_count=len(failures), data_hash=compute_data_hash(failures)
        )
        return DistillResult(ok=True, reason="distilled", proposal=proposal)
    except Exception as exc:  # noqa: BLE001
        return DistillResult(ok=False, reason=f"error: {type(exc).__name__}: {exc}")


__all__ = [
    "DISTILLER_MIN_CAPSULES",
    "DISTILLER_RECENT_WINDOW",
    "DISTILLER_MIN_RECENT_SUCCESS",
    "DISTILLER_INTERVAL_HOURS",
    "DISTILLER_MIN_SUCCESS_SCORE",
    "FAILURE_DISTILLER_MIN_CAPSULES",
    "FAILURE_DISTILLER_INTERVAL_HOURS",
    "MIN_STRATEGY_STEPS",
    "HIGH_FREQUENCY_THRESHOLD",
    "RECURRENCE_PROMOTE_THRESHOLD",
    "GeneGroup",
    "MergedPattern",
    "DistillationData",
    "PatternAnalysis",
    "SkillProposal",
    "DistillResult",
    "expand_signals",
    "compute_data_hash",
    "merge_capsules_by_pattern_key",
    "collect_distillation_data",
    "analyze_patterns",
    "synthesize_gene_from_patterns",
    "synthesize_repair_gene_from_failures",
    "sanitize_signals_match",
    "validate_synthesized_gene",
    "sanitize_skill_slug",
    "derive_triggers",
    "render_skill_markdown",
    "gene_to_skill_proposal",
    "should_distill",
    "should_distill_from_failures",
    "auto_distill",
    "auto_distill_from_failures",
]
