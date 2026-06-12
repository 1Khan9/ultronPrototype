"""ultron's clean-room autonomous self-improvement package.

Catalog 13 (clawhub-capability-evolver) clean-room synthesis. This
package gives ultron a **bounded, autonomous, data-only** self-improvement
loop: it notices an unmet need (a *signal*), proposes a new *skill*
(markdown data, never executable code), pre-flights the proposal through
the existing safety stack (static scan + capability tags + blast-radius +
ethics + hollow-commit, fail-closed), checkpoints the workspace, applies
the change, monitors the voice/quality guardrails for a few turns, and
keeps the change only if it improved things -- otherwise it auto-reverts.

It is capability evolution as **context-injection**, NOT self-modification.
Every guarantee that makes this safe is enforced here, never assumed:

* **data-only** -- proposals are ``skills/*.md`` data files or in-range
  config values, NEVER generated Python, NEVER ``src/ultron/``, NEVER a
  Category-K protected file;
* **zero network** -- no HTTP / sockets / remote hub / phone-home;
* **bounded** -- the loop is an :class:`ultron.agent_loop.base.AgentLoop`
  subclass, so ``max_steps`` + loop-detection cap every run;
* **reversible** -- every change is checkpointed before it lands and the
  guardrails trigger an automatic rollback on any regression;
* **tier-walled** -- the agent's own safety validator, audit log, this
  evolution engine, and Category-K files are a hard architectural wall
  the loop can never autonomously rewrite.

The modules:

* :mod:`~ultron.evolution.models` -- the GEP data model.
* :mod:`~ultron.evolution.signals` -- the 17-signal taxonomy + local
  detection + history-aware post-processing.
* :mod:`~ultron.evolution.blast_radius` -- the change-size policy spine.
* :mod:`~ultron.evolution.skill_distiller` -- successes -> a ``skills/*.md``
  proposal.
* :mod:`~ultron.evolution.guardrails` -- regression detectors + auto-revert
  + the rollback-frequency audit.
* :mod:`~ultron.evolution.autonomy` -- the tiered-autonomy controller +
  trust-graduation ladder.
* :mod:`~ultron.evolution.personality` -- adaptive response temperament.
* :mod:`~ultron.evolution.evolution_loop` -- the bounded loop tying it all
  together.
"""

from __future__ import annotations

from ultron.evolution.autonomy import (
    DEFAULT_SURFACE_TIERS,
    AutonomyMode,
    AutonomyTier,
    AutonomyTransition,
    SurfaceState,
    TieredAutonomyController,
)
from ultron.evolution.blast_radius import (
    BLAST_RADIUS_HARD_CAP_FILES,
    BLAST_RADIUS_HARD_CAP_LINES,
    BlastComputation,
    BlastSeverity,
    ConstraintCheckResult,
    CountedFilePolicy,
    FailureMode,
    check_constraints,
    classify_blast_severity,
    classify_failure_mode,
    compute_blast_radius,
    detect_ethics_violations,
    is_critical_protected_path,
    is_validation_command_allowed,
    proposal_policy,
)
from ultron.evolution.evolution_loop import (
    ApplyResult,
    ApplyStatus,
    CheckpointHook,
    EvolutionLoop,
    EvolutionLoopConfig,
    EvolutionState,
)
from ultron.evolution.guardrails import (
    GuardrailBaseline,
    GuardrailConfig,
    GuardrailSample,
    GuardrailVerdict,
    RollbackAudit,
    RollbackRecord,
    evaluate_guardrails,
)
from ultron.evolution.models import (
    DEFAULT_FORBIDDEN_PATHS,
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
    new_record_id,
    verify_asset_id,
    # catalog 14 -- qualitative conversation-event capture
    DEFAULT_FRAGMENT_MAX_CHARS,
    PATTERN_KEY_MAX_TOKENS,
    CommandFailureSignal,
    ComplexityHint,
    CorrectionCapsule,
    FeatureRequestCapsule,
    FeatureRequestStatus,
    KnowledgeGapCapsule,
    KnowledgeSource,
    bump_recurrence,
    derive_pattern_key,
    redact_fragment,
)
from ultron.evolution.personality import (
    PersonalityFeedback,
    PersonalityTuner,
    apply_temperament,
    temperament_hint,
)
from ultron.evolution.signals import (
    OPPORTUNITY_SIGNALS,
    RecentHistoryAnalysis,
    analyze_recent_history,
    extract_signals,
    has_opportunity_signal,
    signal_base,
)
from ultron.evolution.skill_distiller import (
    DistillResult,
    SkillProposal,
    auto_distill,
    auto_distill_from_failures,
    gene_to_skill_proposal,
    should_distill,
)

__all__ = [
    # models
    "EVOLUTION_SCHEMA_VERSION",
    "DEFAULT_GENE_MAX_FILES",
    "DISTILLED_GENE_MAX_FILES",
    "DEFAULT_FORBIDDEN_PATHS",
    "DISTILLED_ID_PREFIX",
    "REPAIR_DISTILLED_ID_PREFIX",
    "EvolutionCategory",
    "OutcomeStatus",
    "RiskLevel",
    "clamp01",
    "canonicalize",
    "compute_asset_id",
    "verify_asset_id",
    "new_event_id",
    "new_capsule_id",
    "new_mutation_id",
    "new_gene_id",
    "EnvFingerprint",
    "BlastRadius",
    "Outcome",
    "GeneConstraints",
    "LearningHistoryEntry",
    "AntiPatternEntry",
    "PersonalityState",
    "Gene",
    "Mutation",
    "Capsule",
    "EvolutionEvent",
    # models -- catalog 14 qualitative capture
    "KnowledgeSource",
    "ComplexityHint",
    "FeatureRequestStatus",
    "CorrectionCapsule",
    "KnowledgeGapCapsule",
    "CommandFailureSignal",
    "FeatureRequestCapsule",
    "new_record_id",
    "redact_fragment",
    "derive_pattern_key",
    "bump_recurrence",
    "DEFAULT_FRAGMENT_MAX_CHARS",
    "PATTERN_KEY_MAX_TOKENS",
    # signals
    "OPPORTUNITY_SIGNALS",
    "RecentHistoryAnalysis",
    "analyze_recent_history",
    "extract_signals",
    "has_opportunity_signal",
    "signal_base",
    # blast_radius
    "BLAST_RADIUS_HARD_CAP_FILES",
    "BLAST_RADIUS_HARD_CAP_LINES",
    "BlastComputation",
    "BlastSeverity",
    "ConstraintCheckResult",
    "CountedFilePolicy",
    "FailureMode",
    "check_constraints",
    "classify_blast_severity",
    "classify_failure_mode",
    "compute_blast_radius",
    "detect_ethics_violations",
    "is_critical_protected_path",
    "is_validation_command_allowed",
    "proposal_policy",
    # skill_distiller
    "DistillResult",
    "SkillProposal",
    "auto_distill",
    "auto_distill_from_failures",
    "gene_to_skill_proposal",
    "should_distill",
    # guardrails
    "GuardrailBaseline",
    "GuardrailConfig",
    "GuardrailSample",
    "GuardrailVerdict",
    "RollbackAudit",
    "RollbackRecord",
    "evaluate_guardrails",
    # autonomy
    "DEFAULT_SURFACE_TIERS",
    "AutonomyMode",
    "AutonomyTier",
    "AutonomyTransition",
    "SurfaceState",
    "TieredAutonomyController",
    # personality
    "PersonalityFeedback",
    "PersonalityTuner",
    "apply_temperament",
    "temperament_hint",
    # evolution_loop
    "ApplyResult",
    "ApplyStatus",
    "CheckpointHook",
    "EvolutionLoop",
    "EvolutionLoopConfig",
    "EvolutionState",
]
