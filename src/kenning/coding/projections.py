"""Phase C / Phase 1 — context projections for Qwen.

The supervisor (Qwen) operates with a tight context window: ~4-5k tokens
of headroom for coding state once system prompt, tools, RAG, and
response budget are subtracted. Sending Qwen a full :class:`ProjectSession`
on a long-running task overflows that budget on its own.

This module makes the budget contract explicit. The MCP server holds
full state internally; Qwen only ever receives **decision-specific
projections** -- small dataclasses computed on demand, each with a hard
token budget that the projection function enforces.

Five projections, one per decision Qwen makes:

  * :func:`project_clarification_context` (1500 tok) -- when Qwen
    decides how to answer Claude's clarification request.
  * :func:`project_status_delta`         (600 tok)  -- when Qwen
    generates a "how's it going?" narration.
  * :func:`project_adjustment_context`   (1200 tok) -- when Qwen
    processes a mid-session user adjustment.
  * :func:`project_correction_context`   (1500 tok) -- when Qwen
    formulates a corrective prompt after verification failure.
  * :func:`project_completion_context`   (800 tok)  -- when Qwen
    generates the final completion narration.

Each function returns a :class:`ProjectionResult` containing the
structured projection (dataclass), the rendered text Qwen sees, the
token count, and a list of any truncations the function had to apply.

Token counting uses ``tiktoken`` with the ``cl100k_base`` encoding -- a
defensible approximation of Qwen's tokenizer, per the spec. Switching
to the actual Qwen tokenizer is a one-line change to ``_encoding()``.

Projections are pure functions of state. Given the same session, the
same projection function returns the same result.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import tiktoken

from config import settings
from kenning.coding.session import (
    ClarificationRequest,
    CompletionClaim,
    FileRecord,
    ProjectSession,
    SessionStatus,
    StageRecord,
)
from kenning.utils.logging import get_logger

logger = get_logger("coding.projections")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


_ENCODING = None


def _encoding():
    """Lazy-init the tiktoken encoder; cached for the process lifetime."""
    global _ENCODING
    if _ENCODING is None:
        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def count_tokens(text: str) -> int:
    """Token count via ``cl100k_base``. Used for budget enforcement.

    A defensible proxy for Qwen's tokenizer -- both produce comparable
    counts on English prose; if anything cl100k slightly overestimates,
    which is the safe direction for a budget cap.
    """
    if not text:
        return 0
    return len(_encoding().encode(text))


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ProjectionResult:
    """Output of every projection function."""

    projection: Any  # the structured dataclass (one of the *Projection types below)
    text: str  # the rendered text representation Qwen actually sees
    token_count: int
    budget: int
    truncations_applied: List[str] = field(default_factory=list)
    truncation_warning: Optional[str] = None  # set when budget unreachable

    @property
    def fits_budget(self) -> bool:
        return self.token_count <= self.budget

    def as_dict(self) -> Dict[str, Any]:
        return {
            "projection": asdict(self.projection) if self.projection else None,
            "text": self.text,
            "token_count": self.token_count,
            "budget": self.budget,
            "truncations_applied": list(self.truncations_applied),
            "truncation_warning": self.truncation_warning,
        }


def _finalize_projection(
    proj: Any, text: str, token_count: int, budget: int,
    truncations: List[str],
) -> ProjectionResult:
    """Common end-of-projection handling: log truncations, populate
    ``truncation_warning`` when the budget is unreachable, and warn when
    the result lands above ``truncation_warning_threshold * budget``
    (close-call signal).

    Reads its behavior from ``config.projections``:
      * ``log_truncations`` — gates the INFO log when truncations apply
      * ``truncation_warning_threshold`` — fraction of budget above which
        we emit a WARNING even if we technically fit
    """
    from kenning.config import get_config

    truncation_warning: Optional[str] = None
    proj_name = type(proj).__name__
    cfg = get_config().projections

    if token_count > budget:
        truncation_warning = (
            f"projection over budget after exhaustive trimming: "
            f"{token_count}/{budget} tokens "
            f"(over by {token_count - budget})"
        )
        logger.error(
            "projection over budget: name=%s tokens=%d budget=%d (over by %d); "
            "truncations applied: %s",
            proj_name, token_count, budget, token_count - budget,
            truncations,
        )
    else:
        if truncations and cfg.log_truncations:
            logger.info(
                "projection truncations applied: name=%s tokens=%d/%d count=%d items=%s",
                proj_name, token_count, budget, len(truncations),
                truncations[:5],
            )
        # Close-call warning: even though we fit, we landed above the
        # threshold. Useful signal that the budget is tight in practice.
        if (
            cfg.log_truncations
            and budget > 0
            and token_count >= cfg.truncation_warning_threshold * budget
        ):
            logger.warning(
                "projection near budget cap: name=%s tokens=%d/%d (%.0f%% of budget)",
                proj_name, token_count, budget,
                100.0 * token_count / budget,
            )

    return ProjectionResult(
        projection=proj, text=text, token_count=token_count,
        budget=budget, truncations_applied=truncations,
        truncation_warning=truncation_warning,
    )


# ---------------------------------------------------------------------------
# Truncation primitives
# ---------------------------------------------------------------------------


def _truncate_to_tokens(text: str, max_tokens: int, suffix: str = "...") -> str:
    """Truncate ``text`` to fit within ``max_tokens`` tokens. Adds a
    suffix to signal truncation when it actually trims."""
    if not text:
        return ""
    enc = _encoding()
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # Reserve a small budget for the suffix.
    suffix_tokens = enc.encode(suffix)
    if len(suffix_tokens) >= max_tokens:
        return enc.decode(tokens[:max_tokens])
    keep = max_tokens - len(suffix_tokens)
    return enc.decode(tokens[:keep]) + suffix


# ---------------------------------------------------------------------------
# Projection 1 — clarification_context (1500 tok)
# ---------------------------------------------------------------------------


@dataclass
class ClarificationContextProjection:
    user_intent: str
    refined_goal: str
    clarification_question: str
    options: List[str]
    current_stage: Optional[str]
    relevant_facts: List[str]            # top 5
    recent_adjustments: List[str]        # max 2 most recent, label-level

    BUDGET_TOKENS: int = 1500


def project_clarification_context(
    session: ProjectSession,
    *,
    clarification_question: str,
    options: Optional[List[str]] = None,
    facts_lookup: Optional[Callable[[str], List[str]]] = None,
) -> ProjectionResult:
    """Build the context Qwen needs to decide how to answer Claude's
    clarification question.

    Critical fields (never truncated): user_intent, refined_goal,
    clarification_question. Less critical fields (facts, adjustments,
    current_stage description) are trimmed first if the projection
    overflows the budget.

    ``facts_lookup`` is the optional Qdrant facts query -- when None,
    the projection ships with no facts. The coordinator wires this in
    when memory is enabled.
    """
    budget = ClarificationContextProjection.BUDGET_TOKENS
    truncations: List[str] = []

    user_intent = (session.user_intent or "").strip()
    refined_goal = (session.refined_goal or session.user_intent or "").strip()
    if user_intent == refined_goal:
        # Don't double-print the same string.
        refined_goal = ""

    # Per spec: truncate intent / refined goal at ~200 tokens each.
    user_intent_trim = _truncate_to_tokens(user_intent, 200)
    if user_intent_trim != user_intent:
        truncations.append("user_intent")
    refined_goal_trim = _truncate_to_tokens(refined_goal, 200)
    if refined_goal_trim != refined_goal:
        truncations.append("refined_goal")

    current_stage = session.current_stage or None

    # Recent adjustments: max 2 most recent, label-level (text only).
    adj_records = session.user_adjustments[-2:]
    recent_adjustments = [
        _truncate_to_tokens(a.text or "", 60) for a in adj_records
    ]

    # Facts lookup is best-effort.
    facts: List[str] = []
    if facts_lookup is not None:
        try:
            raw = facts_lookup(clarification_question or "") or []
        except Exception as e:
            logger.debug("facts_lookup failed: %s", e)
            raw = []
        facts = [str(f)[:200] for f in raw[:5]]

    # Options: cap count at 8 and each option at 200 chars. Pathological
    # inputs (20 huge options) would otherwise blow the budget out of
    # the water -- options ARE critical, but unbounded options are
    # useless to Qwen.
    options_in = list(options or [])
    options_capped = [str(o)[:200] for o in options_in[:8]]
    if len(options_in) > 8:
        truncations.append("options:trimmed_to_8")
    if any(len(str(o)) > 200 for o in options_in):
        truncations.append("options:per_option_200char_cap")

    proj = ClarificationContextProjection(
        user_intent=user_intent_trim,
        refined_goal=refined_goal_trim,
        clarification_question=(clarification_question or "").strip(),
        options=options_capped,
        current_stage=current_stage,
        relevant_facts=facts,
        recent_adjustments=recent_adjustments,
    )

    text = _render_clarification_context(proj)
    token_count = count_tokens(text)

    # Trim less-critical fields if over budget.
    while token_count > budget:
        if proj.relevant_facts:
            proj.relevant_facts.pop()
            truncations.append("relevant_facts:tail")
        elif proj.recent_adjustments:
            proj.recent_adjustments.pop(0)
            truncations.append("recent_adjustments:oldest")
        elif proj.current_stage:
            proj.current_stage = None
            truncations.append("current_stage")
        elif proj.refined_goal:
            proj.refined_goal = ""
            truncations.append("refined_goal:dropped")
        elif len(proj.options) > 2:
            # Drop options if there are more than 2 left -- keep a
            # representative pair so Qwen can see the kind of choice.
            proj.options = proj.options[:2]
            truncations.append("options:trimmed_to_2")
        else:
            # Last resort: trim the user intent itself. Critical but
            # better than overflow.
            new_intent = _truncate_to_tokens(proj.user_intent, max(100, len(proj.user_intent.split()) // 2))
            if new_intent == proj.user_intent:
                break
            proj.user_intent = new_intent
            truncations.append("user_intent:hard_trim")
        text = _render_clarification_context(proj)
        token_count = count_tokens(text)

    return _finalize_projection(proj, text, token_count, budget, truncations)


def _render_clarification_context(p: ClarificationContextProjection) -> str:
    lines = ["# Clarification request from Claude", ""]
    lines.append(f"User's original goal: {p.user_intent}")
    if p.refined_goal:
        lines.append(f"Refined goal: {p.refined_goal}")
    if p.current_stage:
        lines.append(f"Currently at stage: {p.current_stage}")
    lines.append("")
    lines.append("Claude is asking:")
    lines.append(p.clarification_question)
    if p.options:
        lines.append("")
        lines.append("Options Claude offered:")
        for o in p.options:
            lines.append(f"  - {o}")
    if p.relevant_facts:
        lines.append("")
        lines.append("Relevant stored facts:")
        for f in p.relevant_facts:
            lines.append(f"  - {f}")
    if p.recent_adjustments:
        lines.append("")
        lines.append("Recent user adjustments to this session:")
        for a in p.recent_adjustments:
            lines.append(f"  - {a}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Projection 2 — status_delta (600 tok)
# ---------------------------------------------------------------------------


@dataclass
class StatusDeltaProjection:
    current_stage: Optional[str]
    elapsed_seconds: float
    is_first_query: bool
    recent_stages: List[str]                 # max 5 stage labels
    new_files_created_count: int
    new_files_created_paths: List[str]       # only populated when count < 5
    new_files_modified_count: int
    new_files_modified_paths: List[str]
    test_passing: int
    test_failing: int
    pending_clarification_question: Optional[str]
    in_correction_loop: bool
    active_model: str

    BUDGET_TOKENS: int = 600


def project_status_delta(session: ProjectSession) -> ProjectionResult:
    """Build the small delta-status projection for "how's it going?"
    narration. Reads ``session.last_user_status_query`` to compute what's
    new since the last poll."""
    budget = StatusDeltaProjection.BUDGET_TOKENS
    truncations: List[str] = []

    last = session.last_user_status_query
    is_first = last is None
    elapsed = max(0.0, time.time() - session.started_at)

    # Stage selection: most recent 5, optionally filtered to "since last".
    stages_iter = (
        session.stages_completed if is_first
        else [s for s in session.stages_completed if s.timestamp > last]
    )
    recent_stages = [s.stage for s in stages_iter[-5:]]

    # File deltas. Spec: only include paths if count < 5; otherwise just count.
    if is_first:
        new_created = list(session.files_created)
        new_modified = list(session.files_modified)
    else:
        new_created = [f for f in session.files_created if f.first_seen > last]
        new_modified = [f for f in session.files_modified if f.first_seen > last]
    n_created = len(new_created)
    n_modified = len(new_modified)
    created_paths = [f.path for f in new_created] if n_created < 5 else []
    modified_paths = [f.path for f in new_modified] if n_modified < 5 else []

    # Tests since last query.
    if (
        session.test_status.last_updated is not None
        and (is_first or session.test_status.last_updated > last)
    ):
        passing = session.test_status.passing
        failing = session.test_status.failing
    else:
        passing = 0
        failing = 0

    pending_clar = (
        session.pending_clarification.question[:200]
        if session.pending_clarification else None
    )

    in_correction = session.status == SessionStatus.CORRECTING

    active_model = (
        settings.CODING_ESCALATION_MODEL
        if session.model_escalation_count >= 1
        else (session.model or settings.CODING_DEFAULT_MODEL)
    )

    proj = StatusDeltaProjection(
        current_stage=session.current_stage or None,
        elapsed_seconds=elapsed,
        is_first_query=is_first,
        recent_stages=recent_stages,
        new_files_created_count=n_created,
        new_files_created_paths=created_paths,
        new_files_modified_count=n_modified,
        new_files_modified_paths=modified_paths,
        test_passing=passing,
        test_failing=failing,
        pending_clarification_question=pending_clar,
        in_correction_loop=in_correction,
        active_model=active_model,
    )

    text = _render_status_delta(proj)
    token_count = count_tokens(text)

    # If over budget, drop file-path lists first (paths are nice-to-have;
    # counts are critical).
    while token_count > budget:
        if proj.new_files_created_paths:
            proj.new_files_created_paths = []
            truncations.append("new_files_created_paths")
        elif proj.new_files_modified_paths:
            proj.new_files_modified_paths = []
            truncations.append("new_files_modified_paths")
        elif len(proj.recent_stages) > 1:
            proj.recent_stages = proj.recent_stages[-1:]
            truncations.append("recent_stages:trimmed_to_one")
        elif proj.pending_clarification_question and len(proj.pending_clarification_question) > 60:
            proj.pending_clarification_question = (
                proj.pending_clarification_question[:60] + "..."
            )
            truncations.append("pending_clarification_question:hard_trim")
        else:
            break
        text = _render_status_delta(proj)
        token_count = count_tokens(text)

    return _finalize_projection(proj, text, token_count, budget, truncations)


def _render_status_delta(p: StatusDeltaProjection) -> str:
    lines = ["# Coding session status"]
    lines.append(f"Currently: {p.current_stage or 'getting started'}")
    lines.append(f"Elapsed: {int(p.elapsed_seconds)}s")
    lines.append(f"Active model: {p.active_model}")
    if p.is_first_query:
        lines.append("(First status query for this session)")
    if p.in_correction_loop:
        lines.append("In correction loop after verification failure.")
    if p.pending_clarification_question:
        lines.append("")
        lines.append(f"Pending clarification: {p.pending_clarification_question}")
    if p.recent_stages:
        lines.append("")
        lines.append(
            f"Stages {'completed so far' if p.is_first_query else 'since last query'}: "
            + ", ".join(p.recent_stages)
        )
    if p.new_files_created_count or p.new_files_modified_count:
        lines.append("")
        bits = []
        if p.new_files_created_count:
            bits.append(f"{p.new_files_created_count} new file(s) created")
        if p.new_files_modified_count:
            bits.append(f"{p.new_files_modified_count} modified")
        lines.append("File changes: " + ", ".join(bits))
        if p.new_files_created_paths:
            lines.append("  created: " + ", ".join(p.new_files_created_paths))
        if p.new_files_modified_paths:
            lines.append("  modified: " + ", ".join(p.new_files_modified_paths))
    if p.test_passing or p.test_failing:
        lines.append("")
        lines.append(
            f"Tests since last query: {p.test_passing} passing, "
            f"{p.test_failing} failing"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Projection 3 — adjustment_context (1200 tok)
# ---------------------------------------------------------------------------


@dataclass
class AdjustmentContextProjection:
    user_intent: str
    refined_goal: str
    adjustment_text: str
    current_stage_description: str
    completed_stages: List[str]              # max 10, label-level
    conflicts_with_completed: bool
    conflict_reason: str
    relevant_facts: List[str]                # top 3

    BUDGET_TOKENS: int = 1200


def project_adjustment_context(
    session: ProjectSession,
    *,
    adjustment_text: str,
    facts_lookup: Optional[Callable[[str], List[str]]] = None,
    conflict_detector: Optional[Callable[[ProjectSession, str], Dict[str, Any]]] = None,
) -> ProjectionResult:
    """Project the context Qwen needs for a mid-session adjustment.

    Critical fields: user_intent, adjustment_text, conflicts_with_completed.
    Less critical: completed stages list, relevant facts.
    """
    budget = AdjustmentContextProjection.BUDGET_TOKENS
    truncations: List[str] = []

    user_intent = _truncate_to_tokens((session.user_intent or "").strip(), 200)
    refined_goal_raw = (session.refined_goal or "").strip()
    refined_goal = (
        _truncate_to_tokens(refined_goal_raw, 200)
        if refined_goal_raw and refined_goal_raw != session.user_intent else ""
    )

    # Current stage with summary -> one-sentence description.
    if session.stages_completed:
        last_stage = session.stages_completed[-1]
        current_stage_description = (
            f"{last_stage.stage}: {last_stage.summary}"
        )
        current_stage_description = _truncate_to_tokens(current_stage_description, 80)
    else:
        current_stage_description = session.current_stage or "starting"

    completed_stages = [s.stage for s in session.stages_completed[-10:]]

    # Conflict detection is optional (LLM-driven in Phase 2 coordinator).
    conflicts = False
    conflict_reason = ""
    if conflict_detector is not None:
        try:
            verdict = conflict_detector(session, adjustment_text) or {}
            conflicts = bool(verdict.get("is_conflict"))
            conflict_reason = str(verdict.get("reason") or "")[:200]
        except Exception as e:
            logger.debug("conflict_detector failed: %s", e)

    facts: List[str] = []
    if facts_lookup is not None:
        try:
            raw = facts_lookup(adjustment_text or "") or []
            facts = [str(f)[:200] for f in raw[:3]]
        except Exception as e:
            logger.debug("facts_lookup failed: %s", e)

    proj = AdjustmentContextProjection(
        user_intent=user_intent,
        refined_goal=refined_goal,
        adjustment_text=(adjustment_text or "").strip(),
        current_stage_description=current_stage_description,
        completed_stages=completed_stages,
        conflicts_with_completed=conflicts,
        conflict_reason=conflict_reason,
        relevant_facts=facts,
    )

    text = _render_adjustment_context(proj)
    token_count = count_tokens(text)

    while token_count > budget:
        if proj.relevant_facts:
            proj.relevant_facts.pop()
            truncations.append("relevant_facts:tail")
        elif len(proj.completed_stages) > 3:
            proj.completed_stages = proj.completed_stages[-3:]
            truncations.append("completed_stages:trim_to_3")
        elif proj.refined_goal:
            proj.refined_goal = ""
            truncations.append("refined_goal:dropped")
        elif proj.conflict_reason:
            proj.conflict_reason = ""
            truncations.append("conflict_reason:dropped")
        elif proj.current_stage_description:
            proj.current_stage_description = ""
            truncations.append("current_stage_description:dropped")
        else:
            break
        text = _render_adjustment_context(proj)
        token_count = count_tokens(text)

    return _finalize_projection(proj, text, token_count, budget, truncations)


def _render_adjustment_context(p: AdjustmentContextProjection) -> str:
    lines = ["# Mid-session adjustment", ""]
    lines.append(f"User's original goal: {p.user_intent}")
    if p.refined_goal:
        lines.append(f"Refined goal: {p.refined_goal}")
    if p.current_stage_description:
        lines.append(f"Currently: {p.current_stage_description}")
    lines.append("")
    lines.append("User's adjustment:")
    lines.append(p.adjustment_text)
    if p.completed_stages:
        lines.append("")
        lines.append(
            "Stages completed (newest last): " + ", ".join(p.completed_stages)
        )
    if p.conflicts_with_completed:
        lines.append("")
        lines.append(f"Conflict detected: {p.conflict_reason or 'with prior work'}")
    if p.relevant_facts:
        lines.append("")
        lines.append("Relevant stored facts:")
        for f in p.relevant_facts:
            lines.append(f"  - {f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Projection 4 — correction_context (1500 tok)
# ---------------------------------------------------------------------------


@dataclass
class FailingCheckSummary:
    check: str
    detail: str  # truncated
    hint: str = ""


@dataclass
class CorrectionContextProjection:
    original_goal: str
    failing_checks: List[FailingCheckSummary]
    failed_test_names: List[str]
    failed_test_messages: str           # truncated to 1000 tokens
    stage_at_completion: Optional[str]
    claimed_files_created: List[str]
    claimed_files_modified: List[str]
    prior_correction_attempts: int

    BUDGET_TOKENS: int = 1500


def project_correction_context(
    session: ProjectSession,
    *,
    failures: List[Dict[str, Any]],
    failed_test_names: Optional[List[str]] = None,
    failed_test_messages: str = "",
) -> ProjectionResult:
    """Project the context Qwen needs to render a correction prompt.

    The verifier supplies ``failures`` (one dict per failing check with
    ``check``, ``detail``, optional ``hint``). The coordinator extracts
    test names + messages from the verifier's per-check detail when the
    check is the test runner.
    """
    budget = CorrectionContextProjection.BUDGET_TOKENS
    truncations: List[str] = []

    goal = _truncate_to_tokens((session.user_intent or "").strip(), 200)

    failing_checks = [
        FailingCheckSummary(
            check=str(f.get("check", "")),
            detail=_truncate_to_tokens(str(f.get("detail") or ""), 200),
            hint=_truncate_to_tokens(str(f.get("hint") or ""), 80),
        )
        for f in (failures or [])[:6]
    ]

    test_msgs_trimmed = _truncate_to_tokens(failed_test_messages or "", 1000)
    if test_msgs_trimmed != (failed_test_messages or ""):
        truncations.append("failed_test_messages:1000tok_cap")

    claim = session.completion_claim
    claimed_created = list(claim.files_created) if claim else []
    claimed_modified = list(claim.files_modified) if claim else []
    stage_at_completion = (
        session.stages_completed[-1].stage if session.stages_completed else None
    )

    proj = CorrectionContextProjection(
        original_goal=goal,
        failing_checks=failing_checks,
        failed_test_names=list(failed_test_names or [])[:20],
        failed_test_messages=test_msgs_trimmed,
        stage_at_completion=stage_at_completion,
        claimed_files_created=claimed_created[:20],
        claimed_files_modified=claimed_modified[:20],
        prior_correction_attempts=int(session.verification_failures),
    )

    text = _render_correction_context(proj)
    token_count = count_tokens(text)

    while token_count > budget:
        # Trim less-critical first.
        if len(proj.claimed_files_modified) > 5:
            proj.claimed_files_modified = proj.claimed_files_modified[:5]
            truncations.append("claimed_files_modified:trim_to_5")
        elif len(proj.claimed_files_created) > 5:
            proj.claimed_files_created = proj.claimed_files_created[:5]
            truncations.append("claimed_files_created:trim_to_5")
        elif len(proj.failed_test_names) > 5:
            proj.failed_test_names = proj.failed_test_names[:5]
            truncations.append("failed_test_names:trim_to_5")
        elif proj.failed_test_messages and count_tokens(proj.failed_test_messages) > 200:
            proj.failed_test_messages = _truncate_to_tokens(proj.failed_test_messages, 200)
            truncations.append("failed_test_messages:hard_trim")
        elif len(proj.failing_checks) > 1:
            proj.failing_checks = proj.failing_checks[:1]
            truncations.append("failing_checks:keep_first_only")
        else:
            break
        text = _render_correction_context(proj)
        token_count = count_tokens(text)

    return _finalize_projection(proj, text, token_count, budget, truncations)


def _render_correction_context(p: CorrectionContextProjection) -> str:
    lines = ["# Verification failed; correction needed", ""]
    lines.append(f"Original goal: {p.original_goal}")
    if p.stage_at_completion:
        lines.append(f"Stage Claude believed it completed at: {p.stage_at_completion}")
    if p.prior_correction_attempts:
        lines.append(f"Prior correction attempts: {p.prior_correction_attempts}")
    lines.append("")
    lines.append("Failing checks:")
    for c in p.failing_checks:
        lines.append(f"  - [{c.check}] {c.detail}")
        if c.hint:
            lines.append(f"      hint: {c.hint}")
    if p.failed_test_names:
        lines.append("")
        lines.append("Failing tests: " + ", ".join(p.failed_test_names))
    if p.failed_test_messages:
        lines.append("")
        lines.append("Test failure detail:")
        lines.append(p.failed_test_messages)
    if p.claimed_files_created:
        lines.append("")
        lines.append(
            "Claude claimed these files were created: "
            + ", ".join(p.claimed_files_created)
        )
    if p.claimed_files_modified:
        lines.append(
            "Claimed modified: " + ", ".join(p.claimed_files_modified)
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Projection 5 — completion_context (800 tok)
# ---------------------------------------------------------------------------


@dataclass
class CompletionContextProjection:
    user_intent: str
    final_summary: str
    entry_point: Optional[str]
    run_command: Optional[str]
    files_created_count: int
    files_created_paths: Optional[List[str]]
    files_modified_count: int
    files_modified_paths: Optional[List[str]]
    test_passing: int
    notable_decisions: List[str]
    duration_seconds: float

    BUDGET_TOKENS: int = 800


def project_completion_context(session: ProjectSession) -> ProjectionResult:
    """Project the final completion narration context. Uses the
    completion_claim recorded by Claude and any 'notable decisions'
    captured during the session (resolved clarifications + applied
    adjustments)."""
    budget = CompletionContextProjection.BUDGET_TOKENS
    truncations: List[str] = []

    intent = _truncate_to_tokens((session.user_intent or "").strip(), 200)

    claim = session.completion_claim
    summary = _truncate_to_tokens(
        (claim.summary if claim else "").strip(), 240,
    )
    entry_point = (claim.entry_point if claim else None) or None
    run_command = (claim.run_command if claim else None) or None

    n_created = len(session.files_created)
    n_modified = len(session.files_modified)
    created_paths = (
        [f.path for f in session.files_created] if n_created < 10 else None
    )
    modified_paths = (
        [f.path for f in session.files_modified] if n_modified < 10 else None
    )

    # Notable decisions: resolved clarifications where Qwen picked an
    # answer (decision_path != "user_answer") + applied adjustments.
    decisions: List[str] = []
    for adj in session.user_adjustments:
        decisions.append(f"adjustment: {adj.text[:80]}")
    decisions = decisions[:5]

    duration = (
        (session.completed_at or time.time()) - session.started_at
    )

    proj = CompletionContextProjection(
        user_intent=intent,
        final_summary=summary,
        entry_point=entry_point,
        run_command=run_command,
        files_created_count=n_created,
        files_created_paths=created_paths,
        files_modified_count=n_modified,
        files_modified_paths=modified_paths,
        test_passing=session.test_status.passing,
        notable_decisions=decisions,
        duration_seconds=duration,
    )

    text = _render_completion_context(proj)
    token_count = count_tokens(text)

    while token_count > budget:
        if proj.files_modified_paths:
            proj.files_modified_paths = None
            truncations.append("files_modified_paths:dropped_to_count")
        elif proj.files_created_paths:
            proj.files_created_paths = None
            truncations.append("files_created_paths:dropped_to_count")
        elif proj.notable_decisions:
            proj.notable_decisions.pop()
            truncations.append("notable_decisions:tail")
        elif proj.run_command:
            proj.run_command = None
            truncations.append("run_command:dropped")
        elif proj.entry_point:
            proj.entry_point = None
            truncations.append("entry_point:dropped")
        elif proj.final_summary:
            proj.final_summary = _truncate_to_tokens(proj.final_summary, 80)
            truncations.append("final_summary:hard_trim")
        else:
            break
        text = _render_completion_context(proj)
        token_count = count_tokens(text)

    return _finalize_projection(proj, text, token_count, budget, truncations)


def _render_completion_context(p: CompletionContextProjection) -> str:
    lines = ["# Coding task complete", ""]
    lines.append(f"User's request: {p.user_intent}")
    lines.append(f"Duration: {int(p.duration_seconds)}s")
    if p.final_summary:
        lines.append("")
        lines.append(f"Claude's summary: {p.final_summary}")
    if p.entry_point:
        lines.append(f"Entry point: {p.entry_point}")
    if p.run_command:
        lines.append(f"Run with: {p.run_command}")
    lines.append("")
    if p.files_created_paths:
        lines.append(
            f"Files created ({p.files_created_count}): "
            + ", ".join(p.files_created_paths)
        )
    else:
        lines.append(f"Files created: {p.files_created_count}")
    if p.files_modified_paths:
        lines.append(
            f"Files modified ({p.files_modified_count}): "
            + ", ".join(p.files_modified_paths)
        )
    elif p.files_modified_count:
        lines.append(f"Files modified: {p.files_modified_count}")
    if p.test_passing:
        lines.append(f"Tests passing: {p.test_passing}")
    if p.notable_decisions:
        lines.append("")
        lines.append("Notable decisions during the session:")
        for d in p.notable_decisions:
            lines.append(f"  - {d}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


__all__ = [
    "ProjectionResult",
    "ClarificationContextProjection",
    "StatusDeltaProjection",
    "AdjustmentContextProjection",
    "CorrectionContextProjection",
    "CompletionContextProjection",
    "FailingCheckSummary",
    "project_clarification_context",
    "project_status_delta",
    "project_adjustment_context",
    "project_correction_context",
    "project_completion_context",
    "count_tokens",
]
