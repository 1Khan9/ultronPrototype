"""Tests for Track 1h ranking signals (2026-05-19).

Covers ``compute_topic_match_score``, ``compute_discourse_match_score``,
and their integration into ``compute_composite_score`` /
``select_top_k``. The headline invariant is that with the new weights
at 0.0 (defaults), behaviour is byte-for-byte identical to the
pre-Track-1h composite-score path.
"""

from __future__ import annotations

from typing import List

import pytest

from ultron.memory.ranking import (
    CandidateScore,
    RankingWeights,
    compute_composite_score,
    compute_discourse_match_score,
    compute_topic_match_score,
    select_top_k,
)


# ---------------------------------------------------------------------------
# compute_topic_match_score
# ---------------------------------------------------------------------------


def test_topic_match_returns_one_on_exact_match():
    c = CandidateScore(
        candidate_id="c1",
        payload={"topic_id": "topic-abc", "ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_topic_match_score(c, "topic-abc") == 1.0


def test_topic_match_returns_zero_on_mismatch():
    c = CandidateScore(
        candidate_id="c1",
        payload={"topic_id": "topic-abc", "ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_topic_match_score(c, "topic-xyz") == 0.0


def test_topic_match_returns_zero_when_query_topic_is_none():
    """Caller has no topic hypothesis -- no boost can be applied."""
    c = CandidateScore(
        candidate_id="c1",
        payload={"topic_id": "topic-abc", "ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_topic_match_score(c, None) == 0.0
    assert compute_topic_match_score(c, "") == 0.0


def test_topic_match_returns_zero_when_candidate_has_no_topic_id():
    """Legacy payloads (pre-Track-1a) lack the field; no boost."""
    c = CandidateScore(
        candidate_id="c1",
        payload={"ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_topic_match_score(c, "topic-abc") == 0.0


def test_topic_match_returns_zero_on_empty_payload():
    c = CandidateScore(
        candidate_id="c1", payload={}, rrf_score=0.5,
    )
    assert compute_topic_match_score(c, "topic-abc") == 0.0


# ---------------------------------------------------------------------------
# compute_discourse_match_score
# ---------------------------------------------------------------------------


def test_discourse_match_returns_one_on_member_of_expected_set():
    c = CandidateScore(
        candidate_id="c1",
        payload={"discourse_type": "decision", "ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_discourse_match_score(c, ["decision"]) == 1.0
    assert compute_discourse_match_score(c, ["decision", "statement"]) == 1.0


def test_discourse_match_returns_zero_on_non_member():
    c = CandidateScore(
        candidate_id="c1",
        payload={"discourse_type": "question", "ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_discourse_match_score(c, ["decision"]) == 0.0
    assert compute_discourse_match_score(c, ["decision", "statement"]) == 0.0


def test_discourse_match_returns_zero_when_expected_is_none_or_empty():
    c = CandidateScore(
        candidate_id="c1",
        payload={"discourse_type": "decision", "ts": 0.0},
        rrf_score=0.5,
    )
    assert compute_discourse_match_score(c, None) == 0.0
    assert compute_discourse_match_score(c, []) == 0.0


def test_discourse_match_returns_zero_when_candidate_has_no_type():
    c = CandidateScore(
        candidate_id="c1", payload={"ts": 0.0}, rrf_score=0.5,
    )
    assert compute_discourse_match_score(c, ["decision"]) == 0.0


# ---------------------------------------------------------------------------
# compute_composite_score with the new signals
# ---------------------------------------------------------------------------


def test_composite_score_unchanged_when_new_weights_zero():
    """Track 1h byte-for-byte invariant: with topic_match_weight = 0
    and discourse_match_weight = 0 (defaults), the composite_score is
    identical to what the pre-Track-1h formula would have computed."""
    weights_legacy = RankingWeights()  # defaults: topic + discourse = 0
    c = CandidateScore(
        candidate_id="c1",
        payload={
            "topic_id": "topic-abc",
            "discourse_type": "decision",
            "ts": 1_700_000_000.0,
        },
        rrf_score=0.5,
        category_similarity=0.0,
    )
    # Call without new kwargs (legacy signature).
    legacy_score = compute_composite_score(
        c, weights=weights_legacy,
        primary_dense=None, picked=[],
    )
    # Call WITH new kwargs but defaults.
    new_score = compute_composite_score(
        c, weights=weights_legacy,
        primary_dense=None, picked=[],
        query_topic_id="topic-abc",          # match
        expected_discourse_types=["decision"],  # match
    )
    # Identical because both weights are 0.
    assert legacy_score == new_score


def test_composite_score_boosts_topic_match_when_weight_set():
    weights = RankingWeights(topic_match_weight=0.5)
    c_match = CandidateScore(
        candidate_id="c1",
        payload={"topic_id": "topic-abc", "ts": 0.0},
        rrf_score=0.5,
    )
    c_mismatch = CandidateScore(
        candidate_id="c2",
        payload={"topic_id": "topic-xyz", "ts": 0.0},
        rrf_score=0.5,
    )
    match_score = compute_composite_score(
        c_match, weights=weights,
        primary_dense=None, picked=[],
        query_topic_id="topic-abc",
    )
    mismatch_score = compute_composite_score(
        c_mismatch, weights=weights,
        primary_dense=None, picked=[],
        query_topic_id="topic-abc",
    )
    assert match_score > mismatch_score
    # Boost is exactly the weight (1.0 * weight) since both share rrf=0.5.
    assert abs((match_score - mismatch_score) - 0.5) < 1e-6


def test_composite_score_boosts_discourse_match_when_weight_set():
    weights = RankingWeights(discourse_match_weight=0.3)
    c_match = CandidateScore(
        candidate_id="c1",
        payload={"discourse_type": "decision", "ts": 0.0},
        rrf_score=0.5,
    )
    c_mismatch = CandidateScore(
        candidate_id="c2",
        payload={"discourse_type": "question", "ts": 0.0},
        rrf_score=0.5,
    )
    match_score = compute_composite_score(
        c_match, weights=weights,
        primary_dense=None, picked=[],
        expected_discourse_types=["decision"],
    )
    mismatch_score = compute_composite_score(
        c_mismatch, weights=weights,
        primary_dense=None, picked=[],
        expected_discourse_types=["decision"],
    )
    assert match_score > mismatch_score
    assert abs((match_score - mismatch_score) - 0.3) < 1e-6


def test_composite_score_combines_topic_and_discourse_boosts():
    """Both boosts apply additively when both match."""
    weights = RankingWeights(
        topic_match_weight=0.4,
        discourse_match_weight=0.2,
    )
    c_both = CandidateScore(
        candidate_id="c1",
        payload={
            "topic_id": "topic-abc",
            "discourse_type": "decision",
            "ts": 0.0,
        },
        rrf_score=0.5,
    )
    c_neither = CandidateScore(
        candidate_id="c2",
        payload={
            "topic_id": "topic-xyz",
            "discourse_type": "question",
            "ts": 0.0,
        },
        rrf_score=0.5,
    )
    both = compute_composite_score(
        c_both, weights=weights,
        primary_dense=None, picked=[],
        query_topic_id="topic-abc",
        expected_discourse_types=["decision"],
    )
    neither = compute_composite_score(
        c_neither, weights=weights,
        primary_dense=None, picked=[],
        query_topic_id="topic-abc",
        expected_discourse_types=["decision"],
    )
    # Combined boost is 0.4 + 0.2 = 0.6.
    assert abs((both - neither) - 0.6) < 1e-6


# ---------------------------------------------------------------------------
# select_top_k threading of the new kwargs
# ---------------------------------------------------------------------------


def test_select_top_k_threads_topic_match_kwarg():
    """With ``topic_match_weight=1.0`` and a query_topic_id set, the
    matching candidate ranks ahead of the non-matcher even though
    their RRF scores are equal."""
    weights = RankingWeights(topic_match_weight=1.0)
    matching = CandidateScore(
        candidate_id="match",
        payload={"topic_id": "topic-abc", "ts": 0.0},
        rrf_score=0.5,
    )
    nonmatching = CandidateScore(
        candidate_id="nonmatch",
        payload={"topic_id": "topic-xyz", "ts": 0.0},
        rrf_score=0.5,
    )
    picked = select_top_k(
        [nonmatching, matching],  # nonmatch listed first
        k=2,
        weights=weights,
        query_topic_id="topic-abc",
    )
    # Topic-match comes first despite being listed second.
    assert picked[0].candidate_id == "match"


def test_select_top_k_threads_discourse_match_kwarg():
    weights = RankingWeights(discourse_match_weight=1.0)
    decision = CandidateScore(
        candidate_id="decision-c",
        payload={"discourse_type": "decision", "ts": 0.0},
        rrf_score=0.5,
    )
    question = CandidateScore(
        candidate_id="question-c",
        payload={"discourse_type": "question", "ts": 0.0},
        rrf_score=0.5,
    )
    picked = select_top_k(
        [question, decision],
        k=2,
        weights=weights,
        expected_discourse_types=["decision"],
    )
    assert picked[0].candidate_id == "decision-c"


def test_select_top_k_defaults_match_legacy_ordering():
    """Without the new kwargs (default behaviour), select_top_k
    orders identically to the pre-Track-1h logic."""
    weights = RankingWeights()  # all new weights = 0
    c1 = CandidateScore(
        candidate_id="c1",
        payload={"ts": 1_700_000_000.0},
        rrf_score=0.9,
    )
    c2 = CandidateScore(
        candidate_id="c2",
        payload={"ts": 1_700_000_000.0},
        rrf_score=0.4,
    )
    picked = select_top_k([c2, c1], k=2, weights=weights)
    # Higher RRF wins.
    assert picked[0].candidate_id == "c1"
    assert picked[1].candidate_id == "c2"
