"""2026-05-19 round 5: greeting / ack rule pre-empts the LLM preflight.

Live session bhoza25go.output: 'Ultron say hello' triggered a SEARCH
preflight that produced "The query requires confirming Ultron's
established character traits" and fired Brave + Jina on Marvel
character info. The preflight LLM is over-eager on these obvious
cases; the rule layer should short-circuit them at NO_SEARCH (high).
"""

from __future__ import annotations

import pytest

from ultron.web_search.gating import (
    GateDecision,
    classify_by_rules,
)


# ---------------------------------------------------------------------------
# Greetings + acks classify as NO_SEARCH (high) -- never reach preflight
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    # Bare greetings
    "hi",
    "Hi.",
    "hello",
    "Hello!",
    "hey",
    "yo",
    "sup",
    "hola",
    "greetings",
    "howdy",
    "aloha",
    "good morning",
    "Good morning.",
    "good afternoon",
    "Good evening",
    "good night",
    # Prefixed with "ultron"
    "Ultron, hi",
    "ultron hello",
    "Hey ultron, good morning",
    "okay ultron, hi",
    # Polite acks / closures
    "thanks",
    "Thanks.",
    "thank you",
    "Thank you very much",
    "ok",
    "Okay.",
    "alright",
    "sure",
    "yes",
    "yeah",
    "yep",
    "no",
    "nope",
    "cool",
    "Cool.",
    "nice",
    "great",
    "awesome",
    "perfect",
    "fine",
    "got it",
    "Got it.",
    "sounds good",
    "mhm",
    "hmm",
    "mmm",
    "uh huh",
    "never mind",
    "nevermind",
    "no worries",
    "all good",
    # "Say hello" command variants
    "say hello",
    "Say hello.",
    "say hi",
    "tell hi",
    "say something",
    "say anything",
    # Whisper-mangled with leading "and"
    "and say hello",
    "and thanks",
    "and ok",
    # Mid-utterance fillers that often appear alone after Whisper cuts
    "right",
    "got that",
    "noted",
    "understood",
])
def test_greeting_or_ack_classifies_no_search_high(utterance):
    verdict = classify_by_rules(utterance)
    assert verdict is not None, f"expected rule to fire for {utterance!r}"
    assert verdict.decision == GateDecision.NO_SEARCH
    assert verdict.confidence == "high"
    assert verdict.source == "rule"
    assert "greeting" in verdict.reason or "ack" in verdict.reason


# ---------------------------------------------------------------------------
# Non-greeting questions still escalate (return None -> caller hits preflight)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "what's the population of Tokyo",
    "how much does a duck weigh",
    "tell me about jazz music",
    "open Chrome on my left monitor",     # APP_LAUNCH not a greeting
    "write me a script that converts PNG to JPEG",
    "explain entropy in three sentences",
    "give me a recipe for cake",
    "switch to the gemma model",
])
def test_substantive_queries_do_not_trigger_greeting_rule(utterance):
    verdict = classify_by_rules(utterance)
    # Either returns a non-greeting verdict OR returns None for the
    # preflight to handle -- but never returns a greeting/ack verdict.
    if verdict is not None:
        assert "greeting" not in (verdict.reason or "")
        assert "ack" not in (verdict.reason or "")


# ---------------------------------------------------------------------------
# Greeting + extra content does NOT match (still escalates)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "thanks, what's the weather",            # ack + new question
    "hello, what time is it",                # greeting + question
    "ok now tell me the date",               # ack + command
    "good morning, switch to gemma",         # greeting + command
])
def test_greeting_with_extra_content_does_not_match(utterance):
    """The pattern is anchored at sentence start AND end (after
    optional punctuation). Multi-clause utterances pass through to
    the normal classify path so the extra clause gets its own
    handling."""
    verdict = classify_by_rules(utterance)
    if verdict is not None:
        assert "greeting" not in (verdict.reason or "")
        assert "ack" not in (verdict.reason or "")


# ---------------------------------------------------------------------------
# Specific live-session regressions
# ---------------------------------------------------------------------------


def test_ultron_say_hello_live_regression():
    """The exact phrase that triggered the bad SEARCH on 2026-05-19."""
    v = classify_by_rules("Ultron say hello")
    assert v is not None
    assert v.decision == GateDecision.NO_SEARCH


def test_ultron_and_say_hello_live_regression():
    """Whisper-mangled "Ultron, and say hello." variant."""
    v = classify_by_rules("Ultron and say hello.")
    assert v is not None
    assert v.decision == GateDecision.NO_SEARCH


def test_good_morning_live_regression():
    """'Good morning' was hitting preflight + producing 'Open Chrome.'"""
    v = classify_by_rules("Good morning.")
    assert v is not None
    assert v.decision == GateDecision.NO_SEARCH


def test_thanks_live_regression():
    """'Thanks.' was leaking into the LLM context."""
    v = classify_by_rules("Thanks.")
    assert v is not None
    assert v.decision == GateDecision.NO_SEARCH
