"""Tests for topical chunking (Track 1a, 2026-05-19).

Verifies the inference-free topic-boundary detector: cosine
similarity between consecutive turn embeddings determines whether a
new topic id is minted. Pure helpers (compute_topic_boundary,
cosine_similarity) plus the stateful TopicTracker.
"""

from __future__ import annotations

from typing import List

import pytest

from ultron.memory.topical_chunking import (
    DEFAULT_BOUNDARY_SIMILARITY,
    DEFAULT_TOPIC_TIMEOUT_S,
    TopicObservation,
    TopicTracker,
    compute_topic_boundary,
    cosine_distance,
    cosine_similarity,
)


# ---------------------------------------------------------------------------
# cosine_similarity / cosine_distance
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical_vectors_is_one():
    v = [1.0, 2.0, 3.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal_is_zero():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_opposite_vectors_is_minus_one():
    a = [1.0, 2.0, 3.0]
    b = [-1.0, -2.0, -3.0]
    assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6


def test_cosine_similarity_zero_vector_returns_zero():
    assert cosine_similarity([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_similarity_mismatched_lengths_returns_zero():
    assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_similarity_none_inputs_returns_zero():
    assert cosine_similarity(None, [1.0]) == 0.0
    assert cosine_similarity([1.0], None) == 0.0


def test_cosine_distance_inverse_of_similarity():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert abs(cosine_distance(a, b)) < 1e-6
    c = [0.0, 1.0, 0.0]
    assert abs(cosine_distance(a, c) - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# compute_topic_boundary
# ---------------------------------------------------------------------------


def test_boundary_when_no_prior_embedding():
    """First call always crosses a boundary (no prior = new topic)."""
    assert compute_topic_boundary(None, [1.0, 0.0, 0.0]) is True


def test_no_boundary_on_similar_vectors():
    """Two highly-similar consecutive turns stay in the same topic."""
    a = [1.0, 0.0, 0.0]
    b = [0.95, 0.05, 0.0]  # near-parallel
    assert compute_topic_boundary(a, b, similarity_threshold=0.4) is False


def test_boundary_on_dissimilar_vectors():
    """Two orthogonal turns cross a topic boundary."""
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]  # orthogonal -> sim=0
    assert compute_topic_boundary(a, b, similarity_threshold=0.4) is True


def test_boundary_respects_custom_threshold():
    """A higher threshold means more boundaries; lower means fewer."""
    a = [1.0, 0.0, 0.0]
    b = [0.6, 0.4, 0.0]  # sim ~ 0.83
    # threshold 0.9 -> boundary (0.83 < 0.9)
    assert compute_topic_boundary(a, b, similarity_threshold=0.9) is True
    # threshold 0.5 -> no boundary (0.83 > 0.5)
    assert compute_topic_boundary(a, b, similarity_threshold=0.5) is False


# ---------------------------------------------------------------------------
# TopicTracker -- state machine
# ---------------------------------------------------------------------------


def test_tracker_initial_state_returns_none():
    tracker = TopicTracker()
    assert tracker.current_topic_id is None


def test_tracker_first_observe_mints_topic():
    tracker = TopicTracker()
    obs = tracker.observe([1.0, 0.0, 0.0])
    assert obs.topic_id is not None
    assert obs.boundary_crossed is True
    assert obs.turn_index_within_topic == 0
    assert obs.similarity_to_previous == 0.0


def test_tracker_consecutive_similar_turns_same_topic():
    tracker = TopicTracker(similarity_threshold=0.4)
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    obs2 = tracker.observe([0.98, 0.02, 0.0])
    obs3 = tracker.observe([0.95, 0.05, 0.05])
    assert obs1.topic_id == obs2.topic_id == obs3.topic_id
    # turn_index increments without crossing boundaries
    assert obs2.boundary_crossed is False
    assert obs3.boundary_crossed is False
    assert obs2.turn_index_within_topic == 1
    assert obs3.turn_index_within_topic == 2


def test_tracker_orthogonal_turn_starts_new_topic():
    tracker = TopicTracker(similarity_threshold=0.4)
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    obs2 = tracker.observe([0.0, 1.0, 0.0])  # orthogonal
    assert obs1.topic_id != obs2.topic_id
    assert obs2.boundary_crossed is True
    assert obs2.turn_index_within_topic == 0


def test_tracker_back_to_first_topic_mints_third_topic():
    """A pivot back to the original topic gets a NEW topic id --
    the tracker is not bidirectional; once we leave a topic it's
    closed. The ranking layer (Track 1h) will surface the prior
    topic via embedding similarity at retrieval time, but for the
    write-side tagging each contiguous span gets its own id."""
    tracker = TopicTracker(similarity_threshold=0.4)
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    obs2 = tracker.observe([0.0, 1.0, 0.0])  # new topic
    obs3 = tracker.observe([1.0, 0.0, 0.0])  # similar to obs1 but new topic
    assert obs1.topic_id != obs3.topic_id
    assert obs2.topic_id != obs3.topic_id
    assert obs3.boundary_crossed is True


def test_tracker_reset_starts_fresh():
    tracker = TopicTracker(similarity_threshold=0.4)
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    obs2 = tracker.observe([0.98, 0.02, 0.0])
    assert obs1.topic_id == obs2.topic_id
    tracker.reset()
    assert tracker.current_topic_id is None
    obs3 = tracker.observe([0.95, 0.05, 0.0])  # would have been same topic
    assert obs3.topic_id != obs1.topic_id  # but reset forced new topic
    assert obs3.boundary_crossed is True


def test_tracker_empty_embedding_returns_state_unchanged():
    tracker = TopicTracker()
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    obs_empty = tracker.observe([])
    obs_none = tracker.observe(None)  # type: ignore[arg-type]
    # Empty/None doesn't advance the state machine
    assert obs_empty.topic_id == obs1.topic_id
    assert obs_empty.boundary_crossed is False
    assert obs_none.topic_id == obs1.topic_id


def test_tracker_idle_timeout_starts_new_topic():
    """If the gap between two observations exceeds the timeout,
    the next turn opens a new topic even if it's semantically
    identical to the prior turn."""
    fake_time = [0.0]

    def now():
        return fake_time[0]

    tracker = TopicTracker(
        similarity_threshold=0.4,
        timeout_seconds=60.0,
        now_provider=now,
    )
    fake_time[0] = 100.0
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    fake_time[0] = 200.0  # 100 s gap > 60 s timeout
    obs2 = tracker.observe([0.99, 0.01, 0.0])  # similar but timed out
    assert obs1.topic_id != obs2.topic_id
    assert obs2.boundary_crossed is True


def test_tracker_zero_timeout_disables_timer():
    """``timeout_seconds=0`` should never timeout even on huge gaps."""
    fake_time = [0.0]

    def now():
        return fake_time[0]

    tracker = TopicTracker(
        similarity_threshold=0.4,
        timeout_seconds=0.0,
        now_provider=now,
    )
    fake_time[0] = 100.0
    obs1 = tracker.observe([1.0, 0.0, 0.0])
    fake_time[0] = 1_000_000.0  # 10 days
    obs2 = tracker.observe([0.99, 0.01, 0.0])
    # Same topic despite huge gap
    assert obs1.topic_id == obs2.topic_id


def test_tracker_topic_ids_are_short_hex():
    """Topic ids should be 12 hex characters -- short enough to keep
    payloads compact, long enough for collision avoidance."""
    tracker = TopicTracker()
    obs = tracker.observe([1.0, 0.0, 0.0])
    assert obs.topic_id is not None
    assert len(obs.topic_id) == 12
    int(obs.topic_id, 16)  # raises if not valid hex


def test_tracker_records_similarity_score():
    """The similarity_to_previous field carries the cosine value that
    drove the boundary decision -- useful for audit / tuning logs."""
    tracker = TopicTracker(similarity_threshold=0.4)
    tracker.observe([1.0, 0.0, 0.0])
    obs2 = tracker.observe([0.98, 0.02, 0.0])
    # Should be in (0.4, 1.0] range
    assert 0.4 < obs2.similarity_to_previous <= 1.0


def test_tracker_thread_safety_smoke(monkeypatch):
    """Multiple threads observing concurrently shouldn't corrupt the
    state machine -- topic IDs should remain consistent within a
    contiguous similar-vector run."""
    import threading

    tracker = TopicTracker(similarity_threshold=0.4)
    results: List[TopicObservation] = []
    results_lock = threading.Lock()

    def worker(vec):
        obs = tracker.observe(vec)
        with results_lock:
            results.append(obs)

    threads = []
    # Mix of similar + orthogonal vectors across threads.
    # Just verifying no crash + every observation gets a topic_id.
    for _ in range(5):
        for vec in ([1.0, 0.0, 0.0], [0.98, 0.02, 0.0], [0.0, 1.0, 0.0]):
            t = threading.Thread(target=worker, args=(vec,))
            threads.append(t)
            t.start()
    for t in threads:
        t.join()
    assert len(results) == 15
    for obs in results:
        assert obs.topic_id is not None


def test_default_threshold_constant():
    """Track 1a default is 0.4. Documented as starting point; tune
    via eval harness against referential queries."""
    assert DEFAULT_BOUNDARY_SIMILARITY == 0.4
    assert DEFAULT_TOPIC_TIMEOUT_S == 300.0
