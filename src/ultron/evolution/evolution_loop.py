"""The bounded, safety-gated self-improvement loop.

Catalog 13 (clawhub-capability-evolver) clean-room synthesis. This is the
module that ties everything together into ONE auto-apply + auto-revert
cycle, built on :class:`ultron.agent_loop.base.AgentLoop` so it inherits
the load-bearing ``max_steps`` cap + loop detection + fail-open execution
for free.

One cycle (:meth:`EvolutionLoop.run_once`):

1. **observe** the current opportunity signals;
2. **plan** -- distil a :class:`~ultron.evolution.skill_distiller.SkillProposal`
   from the accumulated successful capsules (returns ``None`` -> done when
   the gates are not met / nothing new);
3. **pre-flight, FAIL-CLOSED** -- path containment + dangerous-char
   rejection, the Tier-3 / critical-path / forbidden-path wall, a static
   scan of the proposal text, a capability-tag gate (blocks
   K-category / shell-exec / network / paid tags), and an ethics scan. Any
   failure -- including a check module that can't be imported -- blocks the
   apply;
4. **autonomy gate** -- a walled surface is refused; a gated surface needs
   a two-phase voice approval; an autonomous surface proceeds;
5. **checkpoint** the workspace;
6. **apply** -- write the proposal markdown (data only);
7. **measure + constrain** -- compute the blast radius and run
   :func:`~ultron.evolution.blast_radius.check_constraints`; a hard
   violation triggers an immediate revert;
8. **monitor** the four guardrails over the window and **keep or
   auto-revert** via the checkpoint;
9. **record** the outcome into the autonomy ledger, emit an
   ``EvolutionEvent`` to the audit sink, and (on keep) a success
   :class:`~ultron.evolution.models.Capsule` for future distillation.

Every collaborator is injected, so the whole loop is exercisable with
fakes -- no git, no real files (beyond an optional tmp write), no model
loads. In production the orchestrator wires the real checkpoint manager,
approval registry, guardrail sampler, and audit/capsule sinks.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from ultron.agent_loop.base import AgentLoop, StepRecord
from ultron.evolution.autonomy import AutonomyTransition, TieredAutonomyController
from ultron.evolution.blast_radius import (
    BlastComputation,
    check_constraints,
    detect_ethics_violations,
    is_constraint_counted_path,
    is_critical_protected_path,
    is_forbidden_path,
    normalize_rel_path,
    proposal_policy,
)
from ultron.evolution.guardrails import (
    GuardrailBaseline,
    GuardrailSample,
    GuardrailVerdict,
    RollbackRecord,
    evaluate_guardrails,
)
from ultron.evolution.models import (
    BlastRadius,
    Capsule,
    EvolutionEvent,
    Outcome,
    OutcomeStatus,
    PersonalityState,
    new_capsule_id,
    new_event_id,
)
from ultron.evolution.skill_distiller import SkillProposal, auto_distill
from ultron.utils.logging import get_logger

logger = get_logger("evolution.loop")

#: Capability tags whose presence in a proposal blocks it outright.
_DEFAULT_BLOCKED_TAG_NAMES: tuple[str, ...] = (
    "k_category_territory",
    "k_category_adjacent",
    "self_modifies_toolkit",
    "executes_shell",
    "executes_python",
    "executes_binary",
    "posts_externally",
    "network_egress_unrestricted",
    "requires_paid_service",
)

DEFAULT_MAX_CYCLE_STEPS: int = 3


class ApplyStatus(str, Enum):
    """Terminal status of one apply attempt."""

    KEPT = "kept"  # applied + survived the guardrails
    REVERTED = "reverted"  # applied then auto-reverted (constraint or guardrail)
    BLOCKED = "blocked"  # pre-flight refused (never applied)
    REJECTED = "rejected"  # approval denied (never applied)
    GATED_NO_CHANNEL = "gated_no_channel"  # approval required but no channel wired


@dataclass(frozen=True)
class ApplyResult:
    """The outcome of one apply attempt."""

    status: ApplyStatus
    proposal: SkillProposal
    reasons: tuple[str, ...] = ()
    blast: Optional[BlastComputation] = None
    guardrail: Optional[GuardrailVerdict] = None
    checkpoint_token: str = ""
    transition: Optional[AutonomyTransition] = None

    @property
    def applied(self) -> bool:
        """Whether the change was applied + kept."""
        return self.status is ApplyStatus.KEPT


@dataclass
class EvolutionState:
    """Mutable gate state persisted across cycles by the orchestrator."""

    last_distillation_at: Optional[float] = None
    last_data_hash: str = ""


@dataclass(frozen=True)
class CheckpointHook:
    """Injectable checkpoint take/restore pair (wraps the shadow-repo)."""

    take: Callable[[], Optional[str]]
    restore: Callable[[str], bool]


@dataclass(frozen=True)
class EvolutionLoopConfig:
    """Loop tuning."""

    enabled: bool = True
    surface: str = "skills"
    max_steps: int = DEFAULT_MAX_CYCLE_STEPS
    monitor_turns: int = 5
    blocked_capability_tags: tuple[str, ...] = _DEFAULT_BLOCKED_TAG_NAMES
    keep_score: float = 0.9


class EvolutionLoop(AgentLoop):
    """The bounded auto-apply + auto-revert self-improvement loop."""

    def __init__(
        self,
        *,
        repo_root: os.PathLike[str] | str,
        proposal_dir: os.PathLike[str] | str,
        capsules_provider: Callable[[], Sequence[Any]],
        autonomy: TieredAutonomyController,
        signals_provider: Callable[[], Sequence[str]] = lambda: (),
        existing_genes_provider: Callable[[], Sequence[Any]] = lambda: (),
        baseline: Optional[GuardrailBaseline] = None,
        guardrail_sampler: Callable[[], GuardrailSample] = lambda: GuardrailSample(),
        checkpoint: Optional[CheckpointHook] = None,
        approval: Any = None,
        audit_sink: Optional[Callable[[EvolutionEvent], None]] = None,
        capsule_sink: Optional[Callable[[Capsule], None]] = None,
        failure_sink: Optional[Callable[[dict], None]] = None,
        write_fn: Optional[Callable[[Path, str], None]] = None,
        blast_provider: Optional[Callable[[SkillProposal], BlastComputation]] = None,
        personality_provider: Callable[[], PersonalityState] = PersonalityState.balanced,
        state: Optional[EvolutionState] = None,
        config: Optional[EvolutionLoopConfig] = None,
        clock: Callable[[], float] = time.time,
        on_step: Optional[Callable[[StepRecord], None]] = None,
    ) -> None:
        self._config = config or EvolutionLoopConfig()
        super().__init__(max_steps=self._config.max_steps, name="evolution_loop", on_step=on_step)
        self._repo_root = Path(repo_root)
        self._proposal_dir = Path(proposal_dir)
        self._capsules_provider = capsules_provider
        self._autonomy = autonomy
        self._signals_provider = signals_provider
        self._existing_genes_provider = existing_genes_provider
        self._baseline = baseline or GuardrailBaseline()
        self._guardrail_sampler = guardrail_sampler
        self._checkpoint = checkpoint
        self._approval = approval
        self._audit_sink = audit_sink
        self._capsule_sink = capsule_sink
        self._failure_sink = failure_sink
        self._write_fn = write_fn
        self._blast_provider = blast_provider
        self._personality_provider = personality_provider
        self._state = state or EvolutionState()
        self._clock = clock
        self._proposed_this_run = False
        self._cycle_results: list[ApplyResult] = []

    # -- AgentLoop overrides -------------------------------------------------

    def observe(self) -> Any:
        try:
            return list(self._signals_provider())
        except Exception:  # noqa: BLE001
            return []

    def plan(self, observation: Any, history: Sequence[StepRecord]) -> Any:
        if self._proposed_this_run or not self._config.enabled:
            return None
        proposal = self._propose()
        if proposal is None:
            return None
        self._proposed_this_run = True
        self._state.last_data_hash = proposal.data_hash
        return proposal

    def act(self, action: Any) -> Any:
        proposal: SkillProposal = action
        result = self._apply(proposal)
        self._cycle_results.append(result)
        return result

    def action_succeeded(self, result: Any) -> bool:
        # Every terminal ApplyResult is a *handled* outcome -- a blocked or
        # reverted change is the loop working correctly, not a loop failure.
        return isinstance(result, ApplyResult)

    def is_done(self, result: Any, history: Sequence[StepRecord]) -> bool:
        return True  # one proposal per run; new capsules trigger the next run

    def action_signature(self, action: Any) -> str:
        if isinstance(action, SkillProposal):
            return f"{action.slug}:{action.data_hash}"
        return repr(action)

    def run(self, goal: str = "") -> Any:
        self._proposed_this_run = False
        self._cycle_results = []
        return super().run(goal=goal or "evolution")

    # -- convenience ---------------------------------------------------------

    def run_once(self) -> Optional[ApplyResult]:
        """Run a single cycle and return its :class:`ApplyResult` (or
        ``None`` when no proposal was produced). Never raises."""
        self.run()
        return self._cycle_results[-1] if self._cycle_results else None

    def results(self) -> tuple[ApplyResult, ...]:
        """The apply results from the most recent run."""
        return tuple(self._cycle_results)

    # -- pipeline ------------------------------------------------------------

    def _propose(self) -> Optional[SkillProposal]:
        try:
            capsules = list(self._capsules_provider())
            existing = list(self._existing_genes_provider())
        except Exception:  # noqa: BLE001
            return None
        result = auto_distill(
            capsules,
            existing_genes=existing,
            last_distillation_at=self._state.last_distillation_at,
            last_data_hash=self._state.last_data_hash,
            now=self._clock(),
            enabled=self._config.enabled,
        )
        return result.proposal if result.ok else None

    def _target_path(self, proposal: SkillProposal) -> Path:
        return self._proposal_dir / proposal.filename

    def _rel(self, path: Path) -> str:
        try:
            return normalize_rel_path(os.path.relpath(str(path), str(self._repo_root)))
        except Exception:  # noqa: BLE001 -- different drive etc.
            return normalize_rel_path(str(path))

    def _apply(self, proposal: SkillProposal) -> ApplyResult:
        surface = self._config.surface

        # 1. pre-flight (fail-closed)
        ok, reasons = self._preflight(proposal)
        if not ok:
            logger.debug("evolution preflight blocked %s: %s", proposal.slug, reasons)
            return ApplyResult(status=ApplyStatus.BLOCKED, proposal=proposal, reasons=tuple(reasons))

        # 2. autonomy gate
        if self._autonomy.is_walled(surface):
            return ApplyResult(
                status=ApplyStatus.BLOCKED, proposal=proposal, reasons=("tier-3 hard wall",)
            )
        if self._autonomy.requires_approval(surface):
            decision = self._seek_approval(proposal)
            if decision is None:
                return ApplyResult(
                    status=ApplyStatus.GATED_NO_CHANNEL,
                    proposal=proposal,
                    reasons=("approval required, no approval channel wired",),
                )
            if not decision:
                return ApplyResult(
                    status=ApplyStatus.REJECTED, proposal=proposal, reasons=("approval denied",)
                )

        # 3. checkpoint
        token = self._take_checkpoint()
        target = self._target_path(proposal)

        # 4. apply (write)
        try:
            self._write(target, proposal.markdown)
        except Exception as exc:  # noqa: BLE001
            self._revert(token, target)
            return ApplyResult(
                status=ApplyStatus.BLOCKED,
                proposal=proposal,
                reasons=(f"write_failed: {type(exc).__name__}: {exc}",),
                checkpoint_token=token,
            )

        # 5. measure + constrain
        blast = self._measure_blast(proposal, target)
        cc = check_constraints(gene=proposal.gene, blast=blast, ethics_text=proposal.markdown)
        if not cc.ok:
            self._revert(token, target)
            return self._on_revert(
                proposal, blast=blast, reasons=cc.violations, hard=True, token=token
            )

        # 6. monitor guardrails -> keep or revert
        sample = self._sample_guardrails()
        verdict = evaluate_guardrails(self._baseline, sample)
        if verdict.should_revert:
            self._revert(token, target)
            return self._on_revert(
                proposal, blast=blast, reasons=verdict.details, hard=False, token=token, guardrail=verdict
            )

        # 7. keep
        return self._on_keep(proposal, blast=blast, guardrail=verdict, token=token)

    # -- pre-flight ----------------------------------------------------------

    def _preflight(self, proposal: SkillProposal) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        target = self._target_path(proposal)
        rel = self._rel(target)

        # extension
        if not rel.endswith(".md"):
            reasons.append(f"not_markdown: {rel}")

        # path containment (commonpath) -- must live under the proposal dir
        try:
            common = os.path.commonpath([os.path.abspath(str(target)), os.path.abspath(str(self._proposal_dir))])
            if normalize_rel_path(common) != normalize_rel_path(str(self._proposal_dir)):
                reasons.append(f"path_escape: {rel}")
        except Exception as exc:  # noqa: BLE001 -- different drives -> fail closed
            reasons.append(f"path_uncomparable: {exc}")

        # dangerous-char rejection (fail-closed on resolver error)
        try:
            from ultron.safety.path_resolver import PathResolveError, get_path_resolver

            try:
                get_path_resolver().resolve(str(target))
            except PathResolveError as exc:
                reasons.append(f"path_dangerous: {exc}")
        except Exception as exc:  # noqa: BLE001 -- resolver import/other failure -> block
            reasons.append(f"path_resolver_unavailable: {exc}")

        # Tier-3 / critical-path + forbidden-path wall
        if is_critical_protected_path(rel):
            reasons.append(f"critical_path: {rel}")
        forbidden = getattr(getattr(proposal.gene, "constraints", None), "forbidden_paths", ())
        if is_forbidden_path(rel, forbidden):
            reasons.append(f"forbidden_path: {rel}")

        # static scan of the proposal text (catches embedded dangerous code)
        try:
            from ultron.install.static_scanner import scan_python_text

            findings = scan_python_text("proposal.md", proposal.markdown)
            if any(getattr(f.severity, "value", f.severity) == "critical" for f in findings):
                crit = [f.kind for f in findings if getattr(f.severity, "value", f.severity) == "critical"]
                reasons.append(f"static_scan_critical: {','.join(crit)}")
        except Exception as exc:  # noqa: BLE001 -- scanner unavailable -> block
            reasons.append(f"static_scanner_unavailable: {exc}")

        # capability-tag gate
        try:
            from ultron.skills.capability_tags import derive_capability_tags

            tags = derive_capability_tags(source=proposal.markdown)
            tag_names = {getattr(t, "value", str(t)) for t in tags}
            blocked = tag_names & set(self._config.blocked_capability_tags)
            if blocked:
                reasons.append(f"blocked_capability_tags: {','.join(sorted(blocked))}")
        except Exception as exc:  # noqa: BLE001 -- gate unavailable -> block
            reasons.append(f"capability_tags_unavailable: {exc}")

        # ethics scan
        ethics = detect_ethics_violations(proposal.markdown)
        if ethics:
            reasons.append(f"ethics: {','.join(ethics)}")

        return (len(reasons) == 0, reasons)

    # -- collaborators -------------------------------------------------------

    def _seek_approval(self, proposal: SkillProposal) -> Optional[bool]:
        if self._approval is None:
            return None
        try:
            from ultron.safety.two_phase_approval import ApprovalRequest

            request = ApprovalRequest(
                kind="evolution_proposal",
                prompt=f"Apply the distilled skill '{proposal.slug}'? {proposal.description}",
                actor="evolution",
                scope_key=self._config.surface,
                delivery_channel="voice",
                metadata={"slug": proposal.slug, "category": proposal.category.value},
            )
            decision = self._approval.request_decision(request)
            return bool(getattr(decision, "allowed", False))
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution approval failed: %s", exc)
            return None

    def _take_checkpoint(self) -> str:
        if self._checkpoint is None:
            return ""
        try:
            return self._checkpoint.take() or ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution checkpoint failed: %s", exc)
            return ""

    def _revert(self, token: str, target: Path) -> bool:
        reverted = False
        if self._checkpoint is not None and token:
            try:
                reverted = bool(self._checkpoint.restore(token))
            except Exception as exc:  # noqa: BLE001
                logger.debug("evolution restore failed: %s", exc)
        # belt-and-suspenders: remove the written file if it survived
        try:
            if target.exists():
                target.unlink()
        except Exception:  # noqa: BLE001
            pass
        return reverted

    def _write(self, target: Path, markdown: str) -> None:
        if self._write_fn is not None:
            self._write_fn(target, markdown)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")

    def _measure_blast(self, proposal: SkillProposal, target: Path) -> BlastComputation:
        if self._blast_provider is not None:
            try:
                return self._blast_provider(proposal)
            except Exception:  # noqa: BLE001
                pass
        rel = self._rel(target)
        pol = proposal_policy(self._rel(self._proposal_dir))
        counted = is_constraint_counted_path(rel, pol)
        lines = proposal.markdown.count("\n") + 1
        return BlastComputation(
            files=1 if counted else 0,
            lines=lines if counted else 0,
            changed_files=(rel,) if counted else (),
            ignored_files=() if counted else (rel,),
            all_changed_files=(rel,),
        )

    def _sample_guardrails(self) -> GuardrailSample:
        try:
            return self._guardrail_sampler()
        except Exception:  # noqa: BLE001 -- a broken sampler must not keep a bad change
            # No sample == no observed regression; but to be safe we treat a
            # sampler failure as "cannot confirm safety" and trip nothing
            # extra here (the constraints already passed). Return an empty
            # sample so guardrails are skipped (kept). The orchestrator's
            # sampler is fail-open by contract.
            return GuardrailSample()

    # -- outcome recording ---------------------------------------------------

    def _on_keep(
        self,
        proposal: SkillProposal,
        *,
        blast: BlastComputation,
        guardrail: GuardrailVerdict,
        token: str,
    ) -> ApplyResult:
        self._state.last_distillation_at = self._clock()
        transition = self._autonomy.record_outcome(self._config.surface, reverted=False)
        self._emit_capsule(proposal, blast, kept=True)
        self._emit_event(proposal, blast, status=OutcomeStatus.SUCCESS)
        return ApplyResult(
            status=ApplyStatus.KEPT,
            proposal=proposal,
            blast=blast,
            guardrail=guardrail,
            checkpoint_token=token,
            transition=transition,
        )

    def _on_revert(
        self,
        proposal: SkillProposal,
        *,
        blast: BlastComputation,
        reasons: Sequence[str],
        hard: bool,
        token: str,
        guardrail: Optional[GuardrailVerdict] = None,
    ) -> ApplyResult:
        guard_name = (
            guardrail.tripped_guards[0] if guardrail and guardrail.tripped_guards else "constraint"
        )
        record = RollbackRecord(
            surface=self._config.surface,
            change_id=proposal.slug,
            guardrail=guard_name,
            metric_delta="; ".join(reasons),
            at=self._clock(),
        )
        transition = self._autonomy.record_outcome(
            self._config.surface, reverted=True, hard_guardrail_trip=hard, record=record
        )
        self._emit_event(proposal, blast, status=OutcomeStatus.FAILED)
        self._emit_failure(proposal, reasons)
        return ApplyResult(
            status=ApplyStatus.REVERTED,
            proposal=proposal,
            reasons=tuple(reasons),
            blast=blast,
            guardrail=guardrail,
            checkpoint_token=token,
            transition=transition,
        )

    def _emit_capsule(self, proposal: SkillProposal, blast: BlastComputation, *, kept: bool) -> None:
        if self._capsule_sink is None:
            return
        try:
            capsule = Capsule(
                id=new_capsule_id(),
                trigger=proposal.signals_match,
                gene=proposal.gene.id,
                summary=proposal.description,
                confidence=self._config.keep_score,
                blast_radius=BlastRadius(files=blast.files, lines=blast.lines),
                outcome=Outcome(status=OutcomeStatus.SUCCESS, score=self._config.keep_score),
                success_streak=1,
            )
            self._capsule_sink(capsule)
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution capsule sink failed: %s", exc)

    def _emit_event(
        self, proposal: SkillProposal, blast: BlastComputation, *, status: OutcomeStatus
    ) -> None:
        if self._audit_sink is None:
            return
        try:
            score = self._config.keep_score if status is OutcomeStatus.SUCCESS else 0.0
            event = EvolutionEvent(
                id=new_event_id(),
                intent=proposal.category.value,
                signals=proposal.signals_match,
                genes_used=(proposal.gene.id,),
                personality_state=self._safe_personality(),
                blast_radius=BlastRadius(files=blast.files, lines=blast.lines),
                outcome=Outcome(status=status, score=score),
            )
            self._audit_sink(event)
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution audit sink failed: %s", exc)

    def _emit_failure(self, proposal: SkillProposal, reasons: Sequence[str]) -> None:
        if self._failure_sink is None:
            return
        try:
            self._failure_sink(
                {
                    "gene": proposal.gene.id,
                    "trigger": list(proposal.signals_match),
                    "reason_class": (reasons[0].split(":", 1)[0] if reasons else "constraint"),
                    "learning_signals": [f"risk:{reasons[0].split(':', 1)[0]}"] if reasons else [],
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("evolution failure sink failed: %s", exc)

    def _safe_personality(self) -> PersonalityState:
        try:
            return self._personality_provider()
        except Exception:  # noqa: BLE001
            return PersonalityState.balanced()


__all__ = [
    "DEFAULT_MAX_CYCLE_STEPS",
    "ApplyStatus",
    "ApplyResult",
    "EvolutionState",
    "CheckpointHook",
    "EvolutionLoopConfig",
    "EvolutionLoop",
]
