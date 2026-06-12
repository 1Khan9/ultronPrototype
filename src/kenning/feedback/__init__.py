"""Feedback primitives: structured reports + moderation-plan preview.

Public surface for user-initiated quality feedback (file a concern
against a turn / response / skill / provider / memory entry) plus
the universal pre-act moderation-plan preview that every irreversible
action routes through.

This package ships:

* :mod:`kenning.feedback.report_queue` — :class:`Report` +
  :class:`ReportQueue` with append-only JSONL persistence + SHA-256
  hash chain (mirrors :mod:`kenning.safety.audit`).
* :mod:`kenning.feedback.moderation_plan` — :class:`ModerationPlan`
  preview shape + :func:`render_plan_for_voice` + the gate decision
  predicate.
"""

from kenning.feedback.moderation_plan import (
    ImpactSeverity,
    ModerationPlan,
    PlanImpact,
    PlanOutcome,
    build_plan,
    render_plan_for_voice,
    requires_confirmation,
)
from kenning.feedback.report_queue import (
    FinalAction,
    Report,
    ReportQueue,
    ReportStatus,
    ReportTargetKind,
    new_report_id,
)

__all__ = [
    "FinalAction",
    "ImpactSeverity",
    "ModerationPlan",
    "PlanImpact",
    "PlanOutcome",
    "Report",
    "ReportQueue",
    "ReportStatus",
    "ReportTargetKind",
    "build_plan",
    "new_report_id",
    "render_plan_for_voice",
    "requires_confirmation",
]
