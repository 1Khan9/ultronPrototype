"""Tests for the discourse-type classifier (Track 1b, 2026-05-19).

Two layers covered:

* Rule layer (``classify_by_rules``) -- regex dispatch. Tight
  patterns; should hit 60-70% of turns at high accuracy.
* Embedding-centroid fallback (``DiscourseClassifier.classify``) --
  uses a stub embedder so tests stay CPU-only and deterministic.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import pytest

from ultron.memory.discourse import (
    DiscourseClassifier,
    DiscourseType,
    classify_by_rules,
)


# ---------------------------------------------------------------------------
# Rule layer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Got it.",
        "yeah",
        "Sounds good!",
        "Thanks.",
        "Cool",
        "mhm",
        "uh-huh",
        "Mm.",
        "noted",
        "Roger that.",
        "Agreed.",
        "Exactly.",
    ],
)
def test_rule_classifies_acknowledgments(text):
    assert classify_by_rules(text) == DiscourseType.ACKNOWLEDGMENT


@pytest.mark.parametrize(
    "text",
    [
        "Anyway, what about the Gemma swap?",
        "Moving on -- let's discuss latency.",
        "Different question, where did we land on Whisper?",
        "Changing the subject, how is the build going?",
        "Actually let's switch to the Kokoro plan.",
        "By the way, did the tests pass?",
        "On a different note, what about the VRAM budget?",
        "Unrelated, but how does the embedder warm up?",
    ],
)
def test_rule_classifies_topic_shifts(text):
    assert classify_by_rules(text) == DiscourseType.TOPIC_SHIFT


@pytest.mark.parametrize(
    "text",
    [
        "Let's go with the Llama 3.2 preset.",
        "I'll use Postgres for this.",
        "We'll ship on Friday.",
        "I'm gonna take the Gemma path.",
        "Going with React.",
        "Decided to skip the Kokoro fine-tune.",
        "Sticking with the in-process runtime.",
        "Locked in -- wire up the swap.",
    ],
)
def test_rule_classifies_decisions(text):
    assert classify_by_rules(text) == DiscourseType.DECISION


@pytest.mark.parametrize(
    "text",
    [
        "Wait what?",
        "What do you mean by that?",
        "Can you say that again?",
        "Could you rephrase?",
        "I don't follow.",
        "Sorry, I'm lost.",
        "Can you clarify the part about embeddings?",
        "Please clarify what you meant by 'topic'.",
        "I'm not understanding the second piece.",
    ],
)
def test_rule_classifies_clarification_requests(text):
    assert classify_by_rules(text) == DiscourseType.CLARIFICATION_REQUEST


@pytest.mark.parametrize(
    "text",
    [
        "What is the boiling point of water?",
        "How does TLS work?",
        "Why is the sky blue?",
        "When did WW2 end?",
        "Where is the kitchen?",
        "Who invented the telephone?",
        "Which model is fastest on the 4070 Ti?",
        "Will the build pass?",
        "Are you ready?",
        "Can you check the logs?",
    ],
)
def test_rule_classifies_questions(text):
    assert classify_by_rules(text) == DiscourseType.QUESTION


def test_rule_returns_none_on_plain_statement():
    """Plain factual / observational statements have no rule -- they
    fall through to the embedding-centroid fallback."""
    samples = [
        "The kitchen is on the second floor.",
        "Most software bugs come from null references.",
        "The car needs an oil change.",
        "I just finished the build.",
    ]
    for s in samples:
        assert classify_by_rules(s) is None, f"expected None: {s!r}"


def test_rule_returns_none_on_empty_or_whitespace():
    assert classify_by_rules("") is None
    assert classify_by_rules("   ") is None
    assert classify_by_rules("\n\t\n") is None
    assert classify_by_rules(None) is None  # type: ignore[arg-type]


def test_rule_dispatch_order_clarification_beats_question():
    """A clarification ending with ? would match BOTH the
    clarification + question rules. The dispatcher tries
    clarification first so the more-specific class wins."""
    assert classify_by_rules("What do you mean?") == \
        DiscourseType.CLARIFICATION_REQUEST


def test_rule_dispatch_order_decision_beats_question():
    """Decisions phrased as questions ("Should we go with X?")
    classify as QUESTION (no decision-rule match). Decisions
    are committal in form -- "I'll go with X", not "should we"."""
    # ``Should we go with X?`` is a question (no decision verb in
    # the committal form). Verify both classes route correctly.
    assert classify_by_rules("Should we go with the Llama preset?") == \
        DiscourseType.QUESTION
    assert classify_by_rules("Let's go with the Llama preset.") == \
        DiscourseType.DECISION


# ---------------------------------------------------------------------------
# Embedding-centroid classifier
# ---------------------------------------------------------------------------


def _make_stub_embedder(routing: Dict[str, List[float]]):
    """Build an embedder_fn that returns a known vector for known
    strings and a zero-vector for unknown. Lets the test pin
    centroid behaviour without needing the real bge model loaded."""
    def _embed(text: str) -> Sequence[float]:
        return routing.get(text.strip().lower(), [0.0, 0.0, 0.0])
    return _embed


def test_centroid_fallback_returns_none_without_embedder():
    """When no embedder is wired, classify() returns None on inputs
    the rule layer doesn't handle."""
    classifier = DiscourseClassifier(embedder_fn=None)
    # Plain statement -- no rule match.
    assert classifier.classify("Pandas are native to China.") is None


def test_centroid_fallback_classifies_statement_via_embedding():
    """With a stub embedder routing the query to the STATEMENT
    centroid, the classifier should return STATEMENT for a plain
    statement that the rule layer doesn't catch."""
    # Stub: every centroid example for STATEMENT maps to a known
    # vector; the query also maps to that vector. Other classes get
    # orthogonal vectors so the cosine-similarity ranking is clean.
    routing = {
        "the kitchen is on the second floor.": [1.0, 0.0, 0.0],
        "i think the new design is better than the old one.": [1.0, 0.0, 0.0],
        "pandas are native to china.": [1.0, 0.0, 0.0],
        "most software bugs are caused by null references.": [1.0, 0.0, 0.0],
        "it's raining outside today.": [1.0, 0.0, 0.0],
        "the build passed all tests on the first try.": [1.0, 0.0, 0.0],
        "i just got back from the store.": [1.0, 0.0, 0.0],
        "the car needs an oil change.": [1.0, 0.0, 0.0],
        "that documentary was really well made.": [1.0, 0.0, 0.0],
        # Question centroid examples -> orthogonal to statement
        "what is the boiling point of water?": [0.0, 1.0, 0.0],
        "how does tls handshake work?": [0.0, 1.0, 0.0],
        "why is the sky blue?": [0.0, 1.0, 0.0],
        "when did world war 2 end?": [0.0, 1.0, 0.0],
        "where is the kitchen?": [0.0, 1.0, 0.0],
        "who invented the telephone?": [0.0, 1.0, 0.0],
        "which model should i use for this?": [0.0, 1.0, 0.0],
        "can you tell me what time it is?": [0.0, 1.0, 0.0],
        "what's the difference between tcp and udp?": [0.0, 1.0, 0.0],
        # Query -> statement direction.
        "the moon orbits the earth.": [1.0, 0.0, 0.0],
    }
    classifier = DiscourseClassifier(
        embedder_fn=_make_stub_embedder(routing),
        confidence_floor=0.2,
    )
    # Plain statement, no rule match -> falls to centroid -> STATEMENT
    assert classifier.classify("The moon orbits the Earth.") == \
        DiscourseType.STATEMENT


def test_centroid_fallback_below_confidence_floor_returns_none():
    """Low-confidence centroid match returns None -- caller treats as
    'no classification' rather than fabricating one."""
    # Stub routes the query to a different orthogonal direction so
    # cosine sim to any centroid is 0.0.
    routing = {
        "the kitchen is on the second floor.": [1.0, 0.0, 0.0],
        "moon orbits earth.": [0.0, 0.0, 1.0],  # third axis -- 0 sim to anything else
    }
    classifier = DiscourseClassifier(
        embedder_fn=_make_stub_embedder(routing),
        confidence_floor=0.5,  # high floor
    )
    assert classifier.classify("Moon orbits earth.") is None


def test_centroid_fallback_handles_embedder_exception():
    """If the embedder raises, classify() returns None rather than
    propagating -- the rule layer + missing-metadata are graceful
    degradation paths."""
    def _broken(_text: str) -> Sequence[float]:
        raise RuntimeError("embedder is on fire")
    classifier = DiscourseClassifier(embedder_fn=_broken)
    # Statement that the rule layer doesn't match -> centroid path
    # exception -> None.
    assert classifier.classify("The kitchen is on the second floor.") is None


def test_full_classifier_prefers_rule_over_centroid():
    """When the rule layer matches, the centroid fallback is not
    consulted (verified by giving the centroid an embedder that
    would raise -- proves the rule path returned before centroid
    layer ran)."""
    def _broken(_text: str) -> Sequence[float]:
        raise AssertionError("centroid should not have been called")
    classifier = DiscourseClassifier(embedder_fn=_broken)
    # Rule layer matches "yeah" as ACKNOWLEDGMENT.
    assert classifier.classify("yeah") == DiscourseType.ACKNOWLEDGMENT


def test_full_classifier_empty_input_returns_none():
    classifier = DiscourseClassifier(embedder_fn=None)
    assert classifier.classify("") is None
    assert classifier.classify(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Discourse types are stable enum values (locked contract)
# ---------------------------------------------------------------------------


def test_discourse_type_values_are_locked():
    """The string values for DiscourseType are persisted in Qdrant
    payloads. Don't change them without a migration."""
    assert DiscourseType.QUESTION.value == "question"
    assert DiscourseType.STATEMENT.value == "statement"
    assert DiscourseType.DECISION.value == "decision"
    assert DiscourseType.CLARIFICATION_REQUEST.value == "clarification_request"
    assert DiscourseType.ACKNOWLEDGMENT.value == "acknowledgment"
    assert DiscourseType.TOPIC_SHIFT.value == "topic_shift"
