"""ultron's clean-room autonomous self-improvement package.

Catalog 13 (clawhub-capability-evolver) clean-room synthesis. This
package gives ultron a **bounded, human-gated, data-only** self-improvement
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

* :mod:`~ultron.evolution.models` -- the GEP data model (Gene / Capsule /
  EvolutionEvent / PersonalityState + supporting records + hashing).
* :mod:`~ultron.evolution.signals` -- the 17-signal taxonomy + local
  detection + history-aware post-processing.
* :mod:`~ultron.evolution.blast_radius` -- the change-size policy spine
  (severity levels, hollow-commit guard, ethics block, command allowlist).
* :mod:`~ultron.evolution.skill_distiller` -- turns accumulated successes
  into a new ``skills/*.md`` proposal.
* :mod:`~ultron.evolution.guardrails` -- the regression detectors + the
  auto-revert trigger + the rollback-frequency audit.
* :mod:`~ultron.evolution.autonomy` -- the tiered-autonomy controller +
  the per-surface trust-graduation ladder.
* :mod:`~ultron.evolution.personality` -- adaptive response temperament.
* :mod:`~ultron.evolution.evolution_loop` -- the bounded loop that ties it
  all together.
"""

from __future__ import annotations

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
    verify_asset_id,
)

__all__ = [
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
]
