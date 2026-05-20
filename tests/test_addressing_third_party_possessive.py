"""2026-05-19 Issue 6 fix: third-party possessive question guard.

Live session 2026-05-19: 'Where's his sandbar?' (Whisper-mangled
'where's his sandbox' said by the user to another human while a
coding task ran) was ADDRESSED at conf 0.85 because the factual-
question-stem rule matched "where's". Ultron then fired a SEARCH
gate and synthesised an unrelated reply. The new
:data:`_THIRD_PARTY_POSSESSIVE_QUESTION` guard runs BEFORE the
factual-stem rule and pre-empts these utterances.
"""

from __future__ import annotations

import pytest

from ultron.addressing.rules import (
    AddressingDecision,
    classify as classify_by_rules,
)


# ---------------------------------------------------------------------------
# New guard: "where's his X?" / "what's her Y?" -> NOT_ADDRESSED
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "Where's his sandbox?",
    "where's his sandbar?",            # live-session Whisper mangle
    "Where is his project?",
    "What's her name?",
    "what is her opinion",
    "When is their meeting?",
    "How are their plans?",
    "Why is his code broken?",
    "where's their pizza?",
    "What was his answer?",
    "Where were their tickets?",
])
def test_third_party_possessive_question_not_addressed(utterance):
    hit = classify_by_rules(utterance)
    assert hit is not None
    assert hit.decision == AddressingDecision.NOT_ADDRESSED
    assert "third-party" in hit.reason


# ---------------------------------------------------------------------------
# Regression: questions to Ultron (no third-party pronoun) still
# classify as ADDRESSED via the factual-stem rule.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "what time is it?",
    "Where are my keys?",
    "What is your name?",
    "How does that work?",
    "Where is the nearest cafe?",
    "When is the meeting?",
    "Why is the sky blue?",
    "What's my next task?",
])
def test_legit_question_to_ultron_still_addressed(utterance):
    hit = classify_by_rules(utterance)
    assert hit is not None
    assert hit.decision == AddressingDecision.ADDRESSED


def test_continuation_of_third_party_narrative_running_him():
    """The extended _THIRD_PARTY_NARRATIVE pattern also catches
    'I'm running him through his paces' style live-session phrases
    that previously slipped through the rule layer (and only got
    NOT_ADDRESSED via the zero-shot conf-band gate)."""
    hit = classify_by_rules("I'm running him through his paces right now")
    assert hit is not None
    assert hit.decision == AddressingDecision.NOT_ADDRESSED
    assert "narrating" in hit.reason or "third" in hit.reason


def test_first_person_verb_him_pattern_variants():
    for phrase in [
        "I'm showing him the new features",
        "I am testing him on the script",
        "I'm debugging her right now",
        "I'm introducing it to the team",
        "I'm demoing him to a friend",
    ]:
        hit = classify_by_rules(phrase)
        assert hit is not None
        assert hit.decision == AddressingDecision.NOT_ADDRESSED, (
            f"expected NOT_ADDRESSED for {phrase!r}, got {hit.decision}"
        )
