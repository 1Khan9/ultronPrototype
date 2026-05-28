"""Tiered-autonomy controller + per-surface trust-graduation ladder.

Catalog 13 (clawhub-capability-evolver) clean-room synthesis. ultron's
self-improvement is **genuinely autonomous within a bounded envelope** --
it self-improves and earns more autonomy over time; the user sets the
trust envelope once and is kept informed via a periodic digest, never
interrupted per change. Autonomy is tiered PER SURFACE:

* **Tier 0 (param self-tuning)** -- response verbosity, RAG thresholds,
  ack-pool selection, retrieval profiles, gaming resource profiles,
  personality traits, STT bias terms, search query-rules. Fully
  autonomous: auto-apply + auto-revert on regression + audit.
* **Tier 1 (reversible data changes)** -- new skills + reversible
  behaviour changes (markdown data). Fully autonomous, checkpointed.
* **Tier 2 (capability expansion)** -- new safety-validator rules,
  capability-envelope expansions, anything touching executable code
  paths. Starts GATED (propose -> voice approval) and **graduates** to
  autonomous once the surface earns it (a strong ledger).
* **Tier 3 (the wall)** -- the agent's own safety validator, the audit
  log, the evolution engine itself, and Category-K protected files. A
  hard architectural wall, NEVER autonomously rewritten.

Two feedback loops move a surface between modes:

* **trust graduation** -- a Tier-2 surface with >= 20 changes, < 10%
  recent rollback rate, and zero hard-guardrail trips graduates to
  autonomous;
* **rollback demotion** -- any autonomous surface whose recent rollback
  rate exceeds 30% is demoted back to gated (and optionally paused), the
  negative-feedback brake on a miscalibrated proposal generator.

This module is the stateful policy controller; the actual approval call
(for a GATED surface) and the audit/checkpoint are done by the loop. It
depends only on :mod:`ultron.evolution.guardrails`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Mapping, Optional

from ultron.evolution.guardrails import (
    ROLLBACK_DEMOTE_THRESHOLD,
    ROLLBACK_MIN_SAMPLES,
    RollbackAudit,
    RollbackRecord,
)

# --- graduation criteria ----------------------------------------------------

GRADUATION_MIN_CHANGES: int = 20
GRADUATION_MAX_REVERT_RATE: float = 0.10
GRADUATION_MAX_HARD_TRIPS: int = 0


class AutonomyTier(IntEnum):
    """A surface's inherent autonomy classification (lower = more
    autonomous by default)."""

    PARAM = 0  # Tier 0: param self-tuning
    SKILL = 1  # Tier 1: reversible data (skills) changes
    GATED = 2  # Tier 2: capability expansion -- gated, can graduate
    WALL = 3  # Tier 3: never autonomously modified


class AutonomyMode(str, Enum):
    """The effective autonomy mode of a surface right now."""

    AUTONOMOUS = "autonomous"  # auto-apply (+ auto-revert on regression)
    GATED = "gated"  # propose -> requires approval
    WALLED = "walled"  # never modified
    PAUSED = "paused"  # autonomy suspended after a demotion


#: Default per-surface tier classification across ultron's subsystems.
DEFAULT_SURFACE_TIERS: dict[str, AutonomyTier] = {
    # Tier 0 -- parameter self-tuning
    "personality": AutonomyTier.PARAM,
    "response_style": AutonomyTier.PARAM,
    "memory_profile": AutonomyTier.PARAM,
    "search_rules": AutonomyTier.PARAM,
    "gaming_profile": AutonomyTier.PARAM,
    "stt_bias": AutonomyTier.PARAM,
    "ack_pool": AutonomyTier.PARAM,
    # Tier 1 -- reversible data (skills) changes
    "skills": AutonomyTier.SKILL,
    "desktop_selectors": AutonomyTier.SKILL,
    "coding_checklists": AutonomyTier.SKILL,
    # Tier 2 -- capability expansion, gated until graduated
    "safety_rules": AutonomyTier.GATED,
    "capability_expansion": AutonomyTier.GATED,
    # Tier 3 -- the hard wall
    "safety_validator": AutonomyTier.WALL,
    "audit_log": AutonomyTier.WALL,
    "evolution_engine": AutonomyTier.WALL,
    "category_k": AutonomyTier.WALL,
}


@dataclass(frozen=True)
class SurfaceState:
    """An immutable snapshot of a surface's autonomy state."""

    surface: str
    base_tier: AutonomyTier
    mode: AutonomyMode
    applied: int
    kept: int
    reverted: int
    hard_trips: int
    rollback_rate: float
    graduated: bool
    demoted: bool
    paused: bool


@dataclass(frozen=True)
class AutonomyTransition:
    """A mode change that just occurred (surfaced in the digest + audit)."""

    surface: str
    kind: str  # "graduated" | "demoted" | "paused"
    from_mode: AutonomyMode
    to_mode: AutonomyMode
    reason: str = ""


@dataclass
class _LedgerEntry:
    """Mutable per-surface ledger (internal)."""

    applied: int = 0
    kept: int = 0
    reverted: int = 0
    hard_trips: int = 0
    graduated: bool = False
    demoted: bool = False
    paused: bool = False


class TieredAutonomyController:
    """Owns per-surface autonomy state + the graduation / demotion logic.

    Args:
        surface_tiers: per-surface base-tier map (defaults to
            :data:`DEFAULT_SURFACE_TIERS`).
        default_tier: tier for an unknown surface (conservative GATED).
        rollback_audit: the shared :class:`RollbackAudit` (created if not
            given).
        pause_on_demote: whether a demotion also pauses the surface.
        graduation_min_changes / graduation_max_revert_rate /
        graduation_max_hard_trips: the trust-graduation criteria.
    """

    def __init__(
        self,
        *,
        surface_tiers: Optional[Mapping[str, AutonomyTier]] = None,
        default_tier: AutonomyTier = AutonomyTier.GATED,
        rollback_audit: Optional[RollbackAudit] = None,
        pause_on_demote: bool = False,
        graduation_min_changes: int = GRADUATION_MIN_CHANGES,
        graduation_max_revert_rate: float = GRADUATION_MAX_REVERT_RATE,
        graduation_max_hard_trips: int = GRADUATION_MAX_HARD_TRIPS,
        demote_threshold: float = ROLLBACK_DEMOTE_THRESHOLD,
        demote_min_samples: int = ROLLBACK_MIN_SAMPLES,
    ) -> None:
        self._tiers: dict[str, AutonomyTier] = dict(surface_tiers or DEFAULT_SURFACE_TIERS)
        self._default_tier = default_tier
        self._rollback = rollback_audit if rollback_audit is not None else RollbackAudit()
        self._pause_on_demote = pause_on_demote
        self._grad_min = graduation_min_changes
        self._grad_max_revert = graduation_max_revert_rate
        self._grad_max_hard = graduation_max_hard_trips
        self._demote_threshold = demote_threshold
        self._demote_min_samples = demote_min_samples
        self._ledger: dict[str, _LedgerEntry] = {}

    # -- tier / mode lookup -------------------------------------------------

    def base_tier(self, surface: str) -> AutonomyTier:
        """The inherent tier of ``surface``."""
        return self._tiers.get(surface, self._default_tier)

    def _entry(self, surface: str) -> _LedgerEntry:
        return self._ledger.setdefault(surface, _LedgerEntry())

    def mode_for(self, surface: str) -> AutonomyMode:
        """The effective autonomy mode of ``surface`` right now."""
        tier = self.base_tier(surface)
        if tier is AutonomyTier.WALL:
            return AutonomyMode.WALLED
        entry = self._ledger.get(surface)
        if entry is not None and entry.paused:
            return AutonomyMode.PAUSED
        if entry is not None and entry.demoted:
            return AutonomyMode.GATED
        if tier in (AutonomyTier.PARAM, AutonomyTier.SKILL):
            return AutonomyMode.AUTONOMOUS
        # Tier 2
        if entry is not None and entry.graduated:
            return AutonomyMode.AUTONOMOUS
        return AutonomyMode.GATED

    def can_auto_apply(self, surface: str) -> bool:
        """Whether a change to ``surface`` may be applied without approval."""
        return self.mode_for(surface) is AutonomyMode.AUTONOMOUS

    def requires_approval(self, surface: str) -> bool:
        """Whether a change to ``surface`` must be voice-approved first."""
        return self.mode_for(surface) is AutonomyMode.GATED

    def is_walled(self, surface: str) -> bool:
        """Whether ``surface`` is a Tier-3 hard wall (never modified)."""
        return self.base_tier(surface) is AutonomyTier.WALL

    def is_blocked(self, surface: str) -> bool:
        """Whether a change to ``surface`` is currently blocked outright
        (walled or paused)."""
        return self.mode_for(surface) in (AutonomyMode.WALLED, AutonomyMode.PAUSED)

    # -- outcome recording + transitions ------------------------------------

    def record_outcome(
        self,
        surface: str,
        *,
        reverted: bool,
        hard_guardrail_trip: bool = False,
        record: Optional[RollbackRecord] = None,
    ) -> Optional[AutonomyTransition]:
        """Record the outcome of one applied change and re-evaluate the
        surface's mode.

        Returns an :class:`AutonomyTransition` if the surface just graduated
        or was demoted/paused, else ``None``. Walled surfaces never record
        (they are never modified)."""
        if self.is_walled(surface):
            return None
        entry = self._entry(surface)
        mode_before = self.mode_for(surface)
        entry.applied += 1
        if reverted:
            entry.reverted += 1
        else:
            entry.kept += 1
        if hard_guardrail_trip:
            entry.hard_trips += 1
        self._rollback.note_outcome(surface, reverted=reverted, record=record)

        # Demotion check first (applies to any currently-autonomous surface).
        if mode_before is AutonomyMode.AUTONOMOUS and self._rollback.should_demote(
            surface, threshold=self._demote_threshold, min_samples=self._demote_min_samples
        ):
            entry.demoted = True
            reason = (
                f"rollback rate {self._rollback.rollback_rate(surface):.0%} exceeded "
                f"{self._demote_threshold:.0%}"
            )
            if self._pause_on_demote:
                entry.paused = True
                return AutonomyTransition(
                    surface=surface,
                    kind="paused",
                    from_mode=mode_before,
                    to_mode=AutonomyMode.PAUSED,
                    reason=reason,
                )
            return AutonomyTransition(
                surface=surface,
                kind="demoted",
                from_mode=mode_before,
                to_mode=AutonomyMode.GATED,
                reason=reason,
            )

        # Graduation check (Tier-2, gated, not yet graduated).
        if (
            self.base_tier(surface) is AutonomyTier.GATED
            and not entry.graduated
            and not entry.demoted
            and self._is_graduation_eligible(surface, entry)
        ):
            entry.graduated = True
            return AutonomyTransition(
                surface=surface,
                kind="graduated",
                from_mode=AutonomyMode.GATED,
                to_mode=AutonomyMode.AUTONOMOUS,
                reason=(
                    f"earned autonomy: {entry.applied} changes, "
                    f"{self._rollback.rollback_rate(surface):.0%} rollback, "
                    f"{entry.hard_trips} hard trips"
                ),
            )
        return None

    def _is_graduation_eligible(self, surface: str, entry: _LedgerEntry) -> bool:
        return (
            entry.applied >= self._grad_min
            and self._rollback.rollback_rate(surface) < self._grad_max_revert
            and entry.hard_trips <= self._grad_max_hard
        )

    # -- manual controls ----------------------------------------------------

    def pause(self, surface: str) -> None:
        """Manually suspend a surface's autonomy."""
        if not self.is_walled(surface):
            self._entry(surface).paused = True

    def resume(self, surface: str) -> None:
        """Resume a paused surface (clears pause + demotion)."""
        entry = self._ledger.get(surface)
        if entry is not None:
            entry.paused = False
            entry.demoted = False

    def reset(self, surface: str) -> None:
        """Drop a surface's accumulated ledger (fresh start)."""
        self._ledger.pop(surface, None)

    # -- introspection ------------------------------------------------------

    def state(self, surface: str) -> SurfaceState:
        """An immutable snapshot of ``surface``'s current state."""
        entry = self._ledger.get(surface) or _LedgerEntry()
        return SurfaceState(
            surface=surface,
            base_tier=self.base_tier(surface),
            mode=self.mode_for(surface),
            applied=entry.applied,
            kept=entry.kept,
            reverted=entry.reverted,
            hard_trips=entry.hard_trips,
            rollback_rate=self._rollback.rollback_rate(surface),
            graduated=entry.graduated,
            demoted=entry.demoted,
            paused=entry.paused,
        )

    def known_surfaces(self) -> tuple[str, ...]:
        """Every surface the controller has a tier or ledger for."""
        return tuple(sorted(set(self._tiers) | set(self._ledger)))

    @property
    def rollback_audit(self) -> RollbackAudit:
        """The shared rollback audit (for digest rendering)."""
        return self._rollback

    def digest(self) -> str:
        """A multi-line human summary of every active surface, for the
        periodic digest."""
        lines = ["Evolution autonomy digest:"]
        for surface in self.known_surfaces():
            entry = self._ledger.get(surface)
            if entry is None or entry.applied == 0:
                continue
            st = self.state(surface)
            lines.append(
                f"  - {surface}: {st.mode.value} (tier {int(st.base_tier)}); "
                f"{st.applied} changes, {st.kept} kept, {st.reverted} reverted "
                f"({st.rollback_rate:.0%})"
                + (" [graduated]" if st.graduated else "")
                + (" [demoted]" if st.demoted else "")
                + (" [paused]" if st.paused else "")
            )
        if len(lines) == 1:
            lines.append("  (no autonomous changes yet)")
        return "\n".join(lines)


__all__ = [
    "GRADUATION_MIN_CHANGES",
    "GRADUATION_MAX_REVERT_RATE",
    "GRADUATION_MAX_HARD_TRIPS",
    "AutonomyTier",
    "AutonomyMode",
    "DEFAULT_SURFACE_TIERS",
    "SurfaceState",
    "AutonomyTransition",
    "TieredAutonomyController",
]
