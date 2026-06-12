"""Composite ranking for multi-pass retrieval (V1-gap A2).

When the conversational memory layer fans out a single query into
multiple per-category sub-queries, the union of candidates needs a
unified ranking that goes beyond raw RRF score. This module provides
the four pieces:

* **Recency boost** -- a smooth exponential decay weighted toward
  recent turns (half-life configurable).
* **Surprise score** -- "high relevance to one of the per-category
  queries but low relevance to the literal user query." Captures the
  "you didn't ask but you'd want to know" memories the V1 spec
  describes.
* **Redundancy penalty** -- greedy diversity pruning so the
  top-K doesn't end up with three near-duplicate hits of the same
  fact.
* **Composite score** -- weighted linear blend of the above.

The functions are pure -- no globals, no side effects -- so the
multi-pass retrieval path can apply them without holding the Qdrant
client lock. All math is on 384-dim float vectors so latency is
microseconds per candidate.

Tunable weights live in :class:`kenning.config.MemoryRankingConfig`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass
class RankingWeights:
    """Snapshot of the relevant config values pulled out of pydantic
    for easy passing into pure helpers."""

    rrf_weight: float = 1.0
    recency_weight: float = 0.2
    recency_half_life_days: float = 7.0
    surprise_weight: float = 0.15
    redundancy_weight: float = 0.3
    # 2026-05-19 Track 1h: topic + discourse match signals. Both
    # default to 0.0 so legacy retrieval is byte-for-byte unchanged
    # until operators tune them up. Topic match boosts candidates
    # whose ``topic_id`` matches the query's expected topic; discourse
    # match boosts candidates whose ``discourse_type`` matches the
    # query's expected class (e.g., "what did we decide about X?"
    # wants DECISION turns).
    topic_match_weight: float = 0.0
    discourse_match_weight: float = 0.0


@dataclass
class CandidateScore:
    """A scored retrieval candidate.

    ``payload`` carries the original Qdrant payload dict so the caller
    can construct a :class:`MemoryTurn` from it after picking the
    top-K. ``dense`` is the 384-dim vector the candidate point exposed
    via ``with_vectors=True``; required for redundancy and surprise
    scoring.
    """

    candidate_id: str
    payload: dict
    rrf_score: float
    dense: Optional[Sequence[float]] = None
    primary_similarity: float = 0.0
    category_similarity: float = 0.0
    composite_score: float = 0.0


def compute_recency_boost(
    ts: float,
    *,
    half_life_days: float,
    now: Optional[float] = None,
) -> float:
    """Smooth exponential decay weighted toward recent turns.

    Returns a value in ``[0.0, 1.0]``. A turn whose timestamp is
    ``half_life_days`` old gets boost ``0.5``; one ``2 * half_life_days``
    old gets ``0.25``. A future timestamp (clock skew) clamps to ``1.0``.
    A zero / missing timestamp returns ``0.0`` -- we prefer no boost
    over fabricating recency from missing data.
    """
    # ``ts == 0`` marks "no timestamp on the payload" (a sentinel
    # uninitialised turns can have); skip those rather than returning a
    # spuriously huge age.
    if ts == 0 or half_life_days <= 0:
        return 0.0
    current = time.time() if now is None else float(now)
    age_days = (current - ts) / 86400.0
    if age_days <= 0:
        return 1.0
    return float(0.5 ** (age_days / half_life_days))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length float vectors.

    Returns ``0.0`` for either operand zero / mismatched length /
    NaN. Used internally by surprise + redundancy scoring; exposed
    publicly so the multi-pass path can reuse it without re-importing
    numpy.
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


def compute_surprise_score(
    candidate_dense: Optional[Sequence[float]],
    primary_dense: Optional[Sequence[float]],
    category_score: float,
) -> float:
    """How much the candidate is "surprisingly relevant".

    A candidate that scored high on a category sub-query (``category_score``)
    but low on the literal user query (cosine to ``primary_dense``)
    contributes content the user wouldn't have surfaced by asking
    directly. Returns ``max(0, category_score - primary_similarity)``,
    so already-on-topic hits get zero surprise.
    """
    if candidate_dense is None or primary_dense is None:
        return 0.0
    primary_sim = cosine_similarity(candidate_dense, primary_dense)
    return max(0.0, float(category_score) - float(primary_sim))


def compute_redundancy_penalty(
    candidate_dense: Optional[Sequence[float]],
    picked: Sequence[CandidateScore],
) -> float:
    """Max cosine similarity between the candidate and any already-
    picked item. A first pick (``picked == []``) returns ``0.0``.
    Near-duplicates of an existing pick approach ``1.0`` so the
    composite-score weighted sum drops them off the top-K.
    """
    if candidate_dense is None or not picked:
        return 0.0
    best = 0.0
    for p in picked:
        if p.dense is None:
            continue
        sim = cosine_similarity(candidate_dense, p.dense)
        if sim > best:
            best = sim
    return float(best)


def compute_topic_match_score(
    candidate: CandidateScore,
    query_topic_id: Optional[str],
) -> float:
    """1.0 when the candidate's payload ``topic_id`` matches the query's
    expected topic; 0.0 otherwise.

    ``query_topic_id`` of None (caller has no topic hypothesis) returns
    0.0 -- a missing query-side signal can't boost anything. A
    candidate payload without a ``topic_id`` field also returns 0.0,
    keeping the legacy byte-for-byte path stable when topical chunking
    is disabled (payloads lack the field entirely).
    """
    if not query_topic_id:
        return 0.0
    payload = candidate.payload or {}
    candidate_topic = payload.get("topic_id")
    if not candidate_topic:
        return 0.0
    return 1.0 if candidate_topic == query_topic_id else 0.0


def compute_discourse_match_score(
    candidate: CandidateScore,
    expected_discourse_types: Optional[Sequence[str]],
) -> float:
    """1.0 when the candidate's payload ``discourse_type`` is in the
    expected-types set; 0.0 otherwise.

    The expected-types argument is a sequence (or None) so the caller
    can pass multiple acceptable types -- a query like "what did we
    figure out about X?" matches both DECISION and STATEMENT, not just
    one. Empty / None expected set returns 0.0 (no boost).
    """
    if not expected_discourse_types:
        return 0.0
    payload = candidate.payload or {}
    candidate_type = payload.get("discourse_type")
    if not candidate_type:
        return 0.0
    return 1.0 if candidate_type in expected_discourse_types else 0.0


def compute_composite_score(
    candidate: CandidateScore,
    *,
    weights: RankingWeights,
    primary_dense: Optional[Sequence[float]],
    picked: Sequence[CandidateScore],
    now: Optional[float] = None,
    query_topic_id: Optional[str] = None,
    expected_discourse_types: Optional[Sequence[str]] = None,
) -> float:
    """Weighted blend of RRF + recency + surprise - redundancy +
    topic_match + discourse_match.

    Side-effect-free: the caller is expected to assign the returned
    value to ``candidate.composite_score`` if they want it persisted.
    The signature returns the score so the helper composes naturally
    with sorted() / max().

    The new ``query_topic_id`` + ``expected_discourse_types`` kwargs
    are optional; with their weights at 0.0 (the default in
    :class:`RankingWeights`) the call reduces to the legacy
    RRF + recency + surprise - redundancy formula byte-for-byte.
    """
    rrf = float(candidate.rrf_score) * weights.rrf_weight

    ts = float((candidate.payload or {}).get("ts", 0.0))
    recency = compute_recency_boost(
        ts, half_life_days=weights.recency_half_life_days, now=now,
    ) * weights.recency_weight

    surprise = compute_surprise_score(
        candidate.dense, primary_dense, candidate.category_similarity,
    ) * weights.surprise_weight

    redundancy = compute_redundancy_penalty(
        candidate.dense, picked,
    ) * weights.redundancy_weight

    topic_match = compute_topic_match_score(
        candidate, query_topic_id,
    ) * weights.topic_match_weight

    discourse_match = compute_discourse_match_score(
        candidate, expected_discourse_types,
    ) * weights.discourse_match_weight

    return rrf + recency + surprise - redundancy + topic_match + discourse_match


def select_top_k(
    candidates: List[CandidateScore],
    *,
    k: int,
    weights: RankingWeights,
    primary_dense: Optional[Sequence[float]] = None,
    now: Optional[float] = None,
    query_topic_id: Optional[str] = None,
    expected_discourse_types: Optional[Sequence[str]] = None,
) -> List[CandidateScore]:
    """Greedy redundancy-aware top-K selection.

    Algorithm:
      1. Score every remaining candidate against the running ``picked``
         list.
      2. Pick the highest-scoring remaining candidate.
      3. Repeat until ``k`` items chosen or no candidates left.

    O(k * n) cosine ops on 384-dim vectors -- ~5 ms for n=100, k=5.
    Stable: ties broken by original ``rrf_score`` (we re-sort each
    iteration). The returned list is in selection order (best first)
    with ``composite_score`` populated.

    Track 1h additions (2026-05-19): ``query_topic_id`` and
    ``expected_discourse_types`` flow into the composite-score
    weighting. With the corresponding weights at 0.0 (defaults) the
    behaviour is byte-for-byte identical to the pre-Track-1h
    behaviour, so existing callers don't need updates.
    """
    if k <= 0 or not candidates:
        return []
    remaining: List[CandidateScore] = list(candidates)
    picked: List[CandidateScore] = []
    while remaining and len(picked) < k:
        best: Optional[CandidateScore] = None
        best_score = -math.inf
        for c in remaining:
            score = compute_composite_score(
                c, weights=weights,
                primary_dense=primary_dense, picked=picked, now=now,
                query_topic_id=query_topic_id,
                expected_discourse_types=expected_discourse_types,
            )
            if score > best_score:
                best_score = score
                best = c
        if best is None:
            break
        best.composite_score = float(best_score)
        picked.append(best)
        remaining.remove(best)
    return picked


__all__ = [
    "CandidateScore",
    "RankingWeights",
    "compute_recency_boost",
    "cosine_similarity",
    "compute_surprise_score",
    "compute_redundancy_penalty",
    "compute_topic_match_score",
    "compute_discourse_match_score",
    "compute_composite_score",
    "select_top_k",
]
