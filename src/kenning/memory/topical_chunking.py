"""Topical chunking for conversation memory (2026-05-19, Track 1a).

Conversations cluster into topics organically -- you spend turns
12-28 on the voice swap, turns 29-35 on a coding interruption, turns
36-50 back on the voice swap. The base RAG retrieval treats every
turn as an independent atom, which fragments multi-turn topics
across the retrieval results ("what did we figure out about the
voice swap?" pulls three semi-related turn fragments instead of the
coherent span).

This module ships the inference-free side of the fix: a
:class:`TopicTracker` that maintains a running topic identifier and
detects topic boundaries via cosine similarity between consecutive
turn embeddings. When similarity drops below ``boundary_threshold``,
a new topic id is minted and the membership counter resets. Each
turn's payload carries the topic_id; later the ranking layer
(Track 1h) can weight candidates inside the query's topic higher.

Pure-function helpers (:func:`compute_topic_boundary`,
:func:`cosine_distance`) are exposed for tests + future consumers;
the stateful :class:`TopicTracker` glues them onto the write path.
All operations are O(1) per turn; no extra Qdrant round-trips, no
LLM calls, no GPU footprint.

Default-OFF via ``memory.topical_chunking.enabled`` -- the metadata
fields ship by default but the boundary detection only runs when
the flag is set. With the flag off, turns get a synthetic topic_id
of None (which Track 1h's ranking treats as "match any"), so the
legacy retrieval path is byte-for-byte unchanged.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Sequence


# Default cosine-similarity threshold below which two consecutive
# turns are considered to have crossed a topic boundary. Empirical
# starting point per the design conversation -- tune via the eval
# harness against referential-query rows. Values below this floor
# are below the practical noise level on bge-small INT8.
DEFAULT_BOUNDARY_SIMILARITY: float = 0.4

# Below this similarity, the current topic chunk is also considered
# stale enough that we drop into a "no prior" state. This handles
# session start, fresh-after-long-silence, etc. -- different from the
# topic-boundary detection but related.
DEFAULT_TOPIC_TIMEOUT_S: float = 300.0  # 5 minutes


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length float vectors.

    Returns 0.0 on zero / mismatched-length / NaN inputs. Duplicates
    the ranking.py helper so this module has no cross-package import.
    """
    if a is None or b is None:
        return 0.0
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        norm_a += float(x) * float(x)
        norm_b += float(y) * float(y)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    denom = math.sqrt(norm_a) * math.sqrt(norm_b)
    if denom == 0 or math.isnan(denom):
        return 0.0
    return dot / denom


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """``1 - cosine_similarity``. Useful when the caller prefers
    distance semantics for thresholding."""
    return 1.0 - cosine_similarity(a, b)


def compute_topic_boundary(
    prev_embedding: Optional[Sequence[float]],
    curr_embedding: Sequence[float],
    *,
    similarity_threshold: float = DEFAULT_BOUNDARY_SIMILARITY,
) -> bool:
    """True iff the current turn crosses a topic boundary.

    Returns True (start a new topic) when:
    * ``prev_embedding`` is None (no prior context to compare against)
    * The cosine similarity between ``prev_embedding`` and
      ``curr_embedding`` is below ``similarity_threshold``

    Returns False (same topic) otherwise. Pure function; no
    dependencies on TopicTracker state.
    """
    if prev_embedding is None:
        return True
    sim = cosine_similarity(prev_embedding, curr_embedding)
    return sim < similarity_threshold


@dataclass
class TopicObservation:
    """Outcome of a single turn's topic-boundary check.

    ``topic_id`` is the membership label for the turn; ``boundary_crossed``
    is True iff this turn opened a new topic (vs continued the prior).
    ``similarity_to_previous`` is exposed so audit logs can show the
    score that drove the decision.
    """

    topic_id: Optional[str]
    boundary_crossed: bool
    similarity_to_previous: float
    turn_index_within_topic: int


class TopicTracker:
    """Stateful tracker that classifies incoming turns into topics.

    Maintains the previous turn's embedding + the current topic_id
    + the index within that topic. Each call to :meth:`observe`
    computes the boundary decision, advances state, and returns a
    :class:`TopicObservation`.

    Thread-safe: a single lock guards the state update. The lock is
    held only for the duration of the cosine math + state mutation
    (microseconds), so contention is negligible.

    Time-out semantics: if more than ``timeout_seconds`` have passed
    since the last observe call, the next turn is treated as a fresh
    topic regardless of similarity. Set ``timeout_seconds=0`` to
    disable the timer-based reset.

    Args:
        similarity_threshold: cosine-similarity floor below which two
            consecutive turns are different topics.
        timeout_seconds: idle window after which the next turn opens
            a new topic regardless of similarity.
        now_provider: injectable clock for tests; defaults to
            :func:`time.monotonic`.
    """

    def __init__(
        self,
        *,
        similarity_threshold: float = DEFAULT_BOUNDARY_SIMILARITY,
        timeout_seconds: float = DEFAULT_TOPIC_TIMEOUT_S,
        now_provider=time.monotonic,
    ) -> None:
        self._similarity_threshold = float(similarity_threshold)
        self._timeout_seconds = float(timeout_seconds)
        self._now = now_provider
        self._lock = threading.Lock()
        self._prev_embedding: Optional[Sequence[float]] = None
        self._current_topic_id: Optional[str] = None
        self._turn_index_within_topic: int = 0
        self._last_observe_time: float = 0.0

    # ------------------------------------------------------------------

    @property
    def current_topic_id(self) -> Optional[str]:
        """Read-only current topic id (None before the first observe)."""
        with self._lock:
            return self._current_topic_id

    def reset(self) -> None:
        """Force the next observe to mint a fresh topic.

        Useful for session start, explicit user "new topic" markers,
        or any caller that wants to discard the prior chain.
        """
        with self._lock:
            self._prev_embedding = None
            self._current_topic_id = None
            self._turn_index_within_topic = 0
            self._last_observe_time = 0.0

    def observe(
        self, embedding: Sequence[float],
    ) -> TopicObservation:
        """Classify ``embedding`` as a continuation or a new topic.

        Returns a :class:`TopicObservation` carrying the topic_id the
        caller should attach to the turn's payload, whether this
        observation crossed a boundary, and the similarity score
        that drove the decision.

        Empty / None embedding returns the current state without
        advancing it (defensive against degenerate write-side
        embeddings). ``None`` is returned as ``topic_id`` if the
        tracker has never observed a real embedding.
        """
        if embedding is None or len(embedding) == 0:
            with self._lock:
                return TopicObservation(
                    topic_id=self._current_topic_id,
                    boundary_crossed=False,
                    similarity_to_previous=0.0,
                    turn_index_within_topic=self._turn_index_within_topic,
                )

        with self._lock:
            now = self._now()
            timed_out = (
                self._timeout_seconds > 0
                and self._last_observe_time > 0
                and (now - self._last_observe_time) > self._timeout_seconds
            )
            sim = (
                cosine_similarity(self._prev_embedding, embedding)
                if self._prev_embedding is not None
                else 0.0
            )

            if (
                self._prev_embedding is None
                or timed_out
                or sim < self._similarity_threshold
            ):
                self._current_topic_id = self._mint_topic_id()
                self._turn_index_within_topic = 0
                boundary_crossed = True
            else:
                self._turn_index_within_topic += 1
                boundary_crossed = False

            self._prev_embedding = list(embedding)
            self._last_observe_time = now

            return TopicObservation(
                topic_id=self._current_topic_id,
                boundary_crossed=boundary_crossed,
                similarity_to_previous=float(sim),
                turn_index_within_topic=self._turn_index_within_topic,
            )

    # ------------------------------------------------------------------

    @staticmethod
    def _mint_topic_id() -> str:
        """Generate a short, sortable topic id.

        Uses ``uuid4`` truncated to 12 hex chars -- enough entropy
        for collision avoidance over a single Kenning lifetime, short
        enough to keep payload size manageable.
        """
        return uuid.uuid4().hex[:12]


__all__ = [
    "DEFAULT_BOUNDARY_SIMILARITY",
    "DEFAULT_TOPIC_TIMEOUT_S",
    "TopicObservation",
    "TopicTracker",
    "compute_topic_boundary",
    "cosine_distance",
    "cosine_similarity",
]
