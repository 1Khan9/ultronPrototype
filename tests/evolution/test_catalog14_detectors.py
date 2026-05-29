"""Catalog 14 -- qualitative conversation-event detectors (evolution/signals.py).

Correction / knowledge-gap / feature-request / command-failure detection, the
topic helper, and the opportunity-signal recognition. Hermetic + pure.
"""

from __future__ import annotations

from ultron.evolution import signals as S
from ultron.evolution.models import (
    CommandFailureSignal,
    CorrectionCapsule,
    FeatureRequestCapsule,
    KnowledgeGapCapsule,
)

# -- correction --------------------------------------------------------------


def test_correction_requires_prior_response():
    assert S.extract_correction("no that is wrong", prior_response="") is None
    assert S.extract_correction("", prior_response="x") is None


def test_correction_strong_phrase_fires():
    c = S.extract_correction(
        "No, that's wrong, fixtures are function scoped.",
        prior_response="They are session scoped.",
    )
    assert isinstance(c, CorrectionCapsule)
    assert c.topic_area
    assert c.prior_agent_claim_summary  # carries the prior agent claim


def test_correction_weak_opener_fires_without_praise():
    c = S.extract_correction("Actually it's pnpm not npm here.", prior_response="Run npm install.")
    assert isinstance(c, CorrectionCapsule)


def test_correction_praise_is_not_a_correction():
    assert (
        S.extract_correction("actually that is a great idea, thanks", prior_response="Here's the plan.")
        is None
    )
    assert S.extract_correction("no, that's perfect, you're right", prior_response="x") is None


def test_correction_strong_wins_over_praise():
    c = S.extract_correction("That's wrong, but thanks for trying.", prior_response="x")
    assert isinstance(c, CorrectionCapsule)


# -- knowledge gap -----------------------------------------------------------


def test_knowledge_gap_fires():
    g = S.extract_knowledge_gap("FYI this project uses pnpm")
    assert isinstance(g, KnowledgeGapCapsule)
    assert "pnpm" in g.gap_description


def test_knowledge_gap_none_on_plain_text():
    assert S.extract_knowledge_gap("what time is it") is None


# -- feature request ---------------------------------------------------------


def test_feature_request_fires_and_estimates_complexity():
    f = S.extract_feature_request("I wish you could just toggle dark mode")
    assert isinstance(f, FeatureRequestCapsule)
    assert f.complexity_hint.value == "simple"  # "just" / "toggle"
    f2 = S.extract_feature_request("can you integrate a real-time pipeline for this")
    assert f2.complexity_hint.value == "complex"


def test_feature_request_none_on_plain_text():
    assert S.extract_feature_request("the weather is nice today") is None


def test_feature_request_pattern_key_keys_on_capability_not_filler():
    f = S.extract_feature_request("I wish you could export the report to CSV")
    assert "export" in f.pattern_key and "wish" not in f.pattern_key


# -- command failure ---------------------------------------------------------


def test_command_failure_fires_on_token_or_nonzero():
    s = S.extract_command_failure(
        "Traceback (most recent call last):\nboom", command="python x.py", exit_code=1
    )
    assert isinstance(s, CommandFailureSignal)
    assert s.exit_code == 1
    s2 = S.extract_command_failure("all output looked normal", command="pytest", exit_code=2)
    assert isinstance(s2, CommandFailureSignal)  # nonzero exit alone trips it


def test_command_failure_none_on_clean_output():
    assert S.extract_command_failure("3 passed in 1s", command="pytest", exit_code=0) is None
    assert S.extract_command_failure("", command="pytest") is None


# -- topic + opportunity recognition -----------------------------------------


def test_derive_topic_area_strips_stopwords():
    t = S.derive_topic_area("the search felt really slow today")
    assert "the" not in t.split() and "really" not in t.split()
    assert "search" in t


def test_has_opportunity_signal_recognises_qualitative():
    assert S.has_opportunity_signal(["user_correction"]) is True
    assert S.has_opportunity_signal(["knowledge_gap"]) is True
    assert S.has_opportunity_signal(["command_failure"]) is True
    assert S.has_opportunity_signal(["stable_success_plateau"]) is False


def test_taxonomy_count_unchanged():
    # The qualitative signals are kept SEPARATE so the documented 17-signal
    # taxonomy count is unchanged.
    assert len(S.OPPORTUNITY_SIGNALS) == 17
    assert set(S.QUALITATIVE_CAPTURE_SIGNALS) == {"user_correction", "knowledge_gap", "command_failure"}
