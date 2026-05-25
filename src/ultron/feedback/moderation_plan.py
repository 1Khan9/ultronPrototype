"""Universal pre-act moderation-plan preview (T12 part 2).

T12 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
The catalog's moderation-plan preview lifted into a generic
pre-act surface every voice command with irreversible impact
routes through. Instead of a flat "blocked" / "executed" voice
line, the user (or operator) sees:

* The **subject** the action targets ("@user/example-skill",
  "turn 42 of the current session", "voicepack ultron").
* The **outcome** the action produces ("hide from skill registry",
  "regenerate", "remove from memory").
* An ordered list of concrete **impacts** ("Will mark 3 future
  install attempts as refused", "Will exclude turn from future
  RAG retrieval", "Will rotate Kokoro voicepack hash pin").
* A **requires_confirmation** flag + the **confirm_prompt**
  voice will speak ("Allow once? Say 'yes' or 'no'").

The plan flows through :mod:`ultron.safety.two_phase_approval`
(T2 from the OpenClaw port) so the user explicitly confirms
before the action lands. The audit-log row (when one is recorded)
references the plan id so reviewers can replay both the
preview AND the user's response.

This module ships the preview shape + the rendering helpers;
the actual triage / install-block / memory-purge driver lives at
each consumer's site (skill registry, install pipeline, memory
forget, etc.) and is gated through the same approval channel.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence

LOGGER = logging.getLogger(__name__)


class ImpactSeverity(str, Enum):
    """How impactful one :class:`PlanImpact` is.

    Drives voice narration tone (CRITICAL impacts get a louder
    pre-act warning) and the audit-log severity column.
    """

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class PlanOutcome(str, Enum):
    """High-level outcome class of a moderation plan.

    Mirrors the upstream marketplace's outcome enum extended with
    ultron-specific destructive actions.
    """

    NONE = "none"            # preview-only / no state change
    NARRATE = "narrate"      # speak a one-liner; no state change
    HIDE = "hide"            # mark hidden from listings but keep on disk
    QUARANTINE = "quarantine"  # block install + mark as untrusted
    REVOKE = "revoke"        # remove + reservation
    PURGE = "purge"          # remove + no reservation
    OVERRIDE = "override"    # explicit-intent override of a safety block


@dataclass(frozen=True)
class PlanImpact:
    """One impact line in a :class:`ModerationPlan`.

    Fields:
        message: short voice-ready sentence describing what
            happens. Always begins with a verb ("Will mark the
            skill as quarantined."). End-with-period.
        severity: :class:`ImpactSeverity`.
        reversible: True iff the impact can be reversed via a
            follow-up command without user data loss. Drives the
            "this is permanent" warning surface.
    """

    message: str
    severity: ImpactSeverity = ImpactSeverity.WARN
    reversible: bool = True


@dataclass(frozen=True)
class ModerationPlan:
    """Preview envelope.

    Fields:
        plan_id: short identifier (UUID4 hex; first 12 chars by
            default) used for audit-log cross-reference.
        subject: human-readable description of the target
            ("voicepack:ultron", "@user/example-skill").
        outcome: :class:`PlanOutcome`.
        impacts: ordered tuple of :class:`PlanImpact`.
        requires_confirmation: True iff the action should NOT
            proceed without explicit voice confirmation.
        confirm_prompt: the exact phrase voice will speak to
            elicit the confirmation. Pre-rendered with
            :func:`render_plan_for_voice` so the same string lands
            in audit + speech surfaces.
        actor: who's requesting (voice user / coding agent /
            operator / cron).
        metadata: free-form attachment for the consumer subsystem
            (e.g. a triage triple {report_id, status, note}).
    """

    plan_id: str
    subject: str
    outcome: PlanOutcome
    impacts: tuple[PlanImpact, ...] = ()
    requires_confirmation: bool = True
    confirm_prompt: str = ""
    actor: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)


def _short_id(value: Optional[str] = None) -> str:
    """Return a short plan_id (12-char hex)."""
    if value:
        return value
    return uuid.uuid4().hex[:12]


def build_plan(
    *,
    subject: str,
    outcome: PlanOutcome,
    impacts: Sequence[PlanImpact],
    actor: str = "",
    plan_id: Optional[str] = None,
    metadata: Optional[Mapping[str, object]] = None,
    confirm_prompt: Optional[str] = None,
    force_confirmation: Optional[bool] = None,
) -> ModerationPlan:
    """Construct a :class:`ModerationPlan` with derived defaults.

    The default :func:`requires_confirmation` predicate is True iff
    the outcome is not NONE / NARRATE AND any impact is non-
    reversible OR any impact is CRITICAL. Callers override via
    ``force_confirmation``.

    ``confirm_prompt`` defaults to the one-line
    :func:`render_plan_for_voice` output.
    """
    impacts_tuple = tuple(impacts)
    derived_confirmation = requires_confirmation(outcome, impacts_tuple)
    needs_confirm = (
        force_confirmation if force_confirmation is not None else derived_confirmation
    )

    plan_id_value = _short_id(plan_id)
    if confirm_prompt is None:
        rendered = render_plan_for_voice(
            subject=subject,
            outcome=outcome,
            impacts=impacts_tuple,
            requires_confirmation=needs_confirm,
        )
    else:
        rendered = confirm_prompt

    return ModerationPlan(
        plan_id=plan_id_value,
        subject=subject,
        outcome=outcome,
        impacts=impacts_tuple,
        requires_confirmation=needs_confirm,
        confirm_prompt=rendered,
        actor=actor,
        metadata=dict(metadata or {}),
    )


def requires_confirmation(
    outcome: PlanOutcome,
    impacts: Iterable[PlanImpact],
) -> bool:
    """Return True iff this combination should force a confirmation prompt.

    Default policy:

    1. Outcomes NONE / NARRATE never force confirmation.
    2. Outcomes PURGE / REVOKE / QUARANTINE always force confirmation.
    3. Otherwise force confirmation iff any impact is CRITICAL or
       any impact is non-reversible.
    """
    if outcome in (PlanOutcome.NONE, PlanOutcome.NARRATE):
        return False
    if outcome in (PlanOutcome.PURGE, PlanOutcome.REVOKE, PlanOutcome.QUARANTINE):
        return True
    for impact in impacts:
        if impact.severity is ImpactSeverity.CRITICAL:
            return True
        if not impact.reversible:
            return True
    return False


def render_plan_for_voice(
    *,
    subject: str,
    outcome: PlanOutcome,
    impacts: Sequence[PlanImpact],
    requires_confirmation: bool,
) -> str:
    """Return a one-line TTS-safe summary of the plan.

    Shape:

    > "Plan for <subject>: <outcome verb>. <N>: <impact 1>; <impact 2>; ...
    >  Allow? Say yes or no."

    Long impact lists are truncated to the first 3 with
    "(+N more)" suffix. The verb mapping mirrors the catalog's
    canonical phrasing (quarantined / revoked / etc.) so audit
    consumers see the same text users hear.
    """
    verb_map = {
        PlanOutcome.NONE: "no state change",
        PlanOutcome.NARRATE: "narration only",
        PlanOutcome.HIDE: "hide from listings",
        PlanOutcome.QUARANTINE: "quarantine and refuse future installs",
        PlanOutcome.REVOKE: "revoke and reserve the slug",
        PlanOutcome.PURGE: "purge from disk",
        PlanOutcome.OVERRIDE: "override the existing block",
    }
    verb = verb_map.get(outcome, outcome.value)

    impact_msgs = [impact.message.rstrip(". ") for impact in impacts[:3]]
    overflow = max(0, len(impacts) - 3)
    if impact_msgs:
        impacts_text = "; ".join(impact_msgs)
        if overflow > 0:
            impacts_text += f" (+{overflow} more)"
        impacts_part = f" Effects: {impacts_text}."
    else:
        impacts_part = ""

    confirmation_part = " Allow? Say yes or no." if requires_confirmation else ""

    body = f"Plan for {subject}: {verb}.{impacts_part}{confirmation_part}"
    return body


__all__ = [
    "ImpactSeverity",
    "ModerationPlan",
    "PlanImpact",
    "PlanOutcome",
    "build_plan",
    "render_plan_for_voice",
    "requires_confirmation",
]
