"""Phase 5: translate preflight uncertainty signals into response behavior.

The preflight pass (in :mod:`ultron.web_search.gating`) already produces
three signals on every gate verdict:

  * ``knowledge_confidence``: high / medium / low / None
  * ``knowledge_source``: weights / retrieved_memory / retrieved_facts /
    web_search_needed / unknown / None
  * ``has_temporal_dependency``: bool / None

This module turns those into two outputs the orchestrator can act on:

  1. **Search upgrade**: a NO_SEARCH verdict with low confidence on a
     temporally-dependent query is upgraded to SEARCH, since the LLM
     would otherwise guess at fresh facts.
  2. **Per-call user-message addendum**: a one-line hint prepended to
     the user's text that primes the LLM to match its answer style to
     the actual confidence level. The permanent system prompt already
     instructs Ultron to handle uncertainty correctly; the per-call
     addendum just nudges it on this specific query.

Hard-rule verdicts (no preflight) carry no uncertainty signals -- this
module is a no-op for them.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Tuple

from ultron.utils.logging import get_logger
from ultron.web_search.gating import GateDecision, GateVerdict

logger = get_logger("uncertainty")


# Tuned to be terse and instructional, not chatty -- Piper would otherwise
# read these out if they leaked into the response. They never do today
# (the LLM treats them as system instruction, not text to repeat) but
# we keep them short anyway.
_ADDENDUM_MEDIUM = (
    "[Confidence: medium. Qualify briefly if you're not fully sure.]"
)
_ADDENDUM_LOW_NON_TEMPORAL = (
    "[Confidence: low. If you don't know for certain, say so plainly. "
    "Do not guess as if certain.]"
)
_ADDENDUM_LOW_TEMPORAL = (
    "[Confidence: low and the answer may have changed. Acknowledge that "
    "you may not be current; do not fabricate fresh facts.]"
)


def apply(verdict: GateVerdict, user_text: str) -> Tuple[GateVerdict, str]:
    """Apply Phase 5 transforms.

    Returns ``(possibly_upgraded_verdict, possibly_augmented_user_text)``.

    Behavior:
      * Verdict from a hard-rule firing (``source == "rule"``) is left
        alone -- rules don't carry confidence signals worth acting on.
      * Verdict with ``knowledge_confidence == "low"`` AND a temporal
        dependency AND a current NO_SEARCH decision is upgraded to
        SEARCH. The original user text becomes the search query.
      * The user text gets a leading ``[Confidence: ...]`` addendum based
        on ``knowledge_confidence`` when present.
    """
    if verdict.source == "rule":
        return verdict, user_text

    upgraded = verdict
    confidence = verdict.knowledge_confidence
    temporal = bool(verdict.has_temporal_dependency)

    # Upgrade rule: low confidence + temporal => search proactively.
    if (
        verdict.decision == GateDecision.NO_SEARCH
        and confidence == "low"
        and temporal
    ):
        upgraded = replace(
            verdict,
            decision=GateDecision.SEARCH,
            confidence="medium",
            source="phase5_low_temporal_upgrade",
            reason=(
                "low knowledge confidence on a temporal claim; "
                "searching rather than guessing"
            ),
            search_queries=verdict.search_queries or [user_text.strip()],
        )
        logger.info(
            "phase5: upgrading NO_SEARCH -> SEARCH (low confidence + temporal): %r",
            user_text[:60],
        )

    # Addendum based on the FINAL confidence + temporal signals.
    final_confidence = upgraded.knowledge_confidence
    final_temporal = bool(upgraded.has_temporal_dependency)
    addendum: str = ""
    if final_confidence == "medium":
        addendum = _ADDENDUM_MEDIUM
    elif final_confidence == "low":
        addendum = (
            _ADDENDUM_LOW_TEMPORAL if final_temporal else _ADDENDUM_LOW_NON_TEMPORAL
        )

    if not addendum:
        return upgraded, user_text

    augmented = f"{addendum}\n\n{user_text}"
    return upgraded, augmented
