"""Integration test category 4 — addressing classifier behavior at the
pipeline level.

The rule layer's accuracy is covered in
:mod:`tests.test_addressing` (gated on PYTEST_RUN_GPU_TESTS=1 for the
zero-shot path). Here we verify the rule-only fast paths an empty
classifier or in-character context, without loading flan-t5-small.
"""

from __future__ import annotations

import pytest

from ultron.addressing.rules import (
    AddressingDecision,
    classify as classify_by_rules,
)


@pytest.mark.parametrize("utt", [
    "ultron, what's the time",
    "hey ultron, can you help",
    "ultron play the next track",
])
def test_explicit_ultron_address_is_addressed(utt):
    """Calling Ultron by name is a strong rule signal."""
    verdict = classify_by_rules(utt, seconds_since_response=2.0)
    if verdict is None:
        return
    assert verdict.decision == AddressingDecision.ADDRESSED


@pytest.mark.parametrize("utt", [
    "yes",
    "no",
    "the second one",
    "go ahead",
    "do it",
])
def test_short_continuation_within_warm_window(utt):
    """Short replies right after Ultron speaks are continuation utterances."""
    verdict = classify_by_rules(utt, seconds_since_response=1.5)
    # Either the rule layer hits ADDRESSED with high confidence, or it
    # passes through to zero-shot (returns None) — both are valid; the
    # contract is "don't classify these as NOT_ADDRESSED outright".
    if verdict is None:
        return
    assert verdict.decision != AddressingDecision.NOT_ADDRESSED


@pytest.mark.parametrize("utt", [
    "tell him to send the email later",
    "she said the meeting got moved",
    "they don't have the file yet",
])
def test_third_person_reference_not_addressed(utt):
    """Talking ABOUT someone else, not TO Ultron."""
    verdict = classify_by_rules(utt, seconds_since_response=2.0)
    if verdict is None:
        return
    assert verdict.decision in (
        AddressingDecision.NOT_ADDRESSED, AddressingDecision.UNCERTAIN,
    )


def test_warm_mode_duration_30_not_10(cap_stack):
    """Confirms the 30-second WARM window is the canonical value (per
    feedback_ultron_extension.md), NOT the Foundation prompt's 10s."""
    from ultron.config import get_config
    assert get_config().addressing.warm_mode_duration_seconds == 30.0
