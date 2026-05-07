"""Phase 3 verification tests for the Qdrant-backed memory store.

Verifies:
  - ConversationMemory creates the three collections on first use.
  - add() returns within a tight budget on the hot path (writes are async).
  - retrieve() returns sensible hybrid hits within the spec's read budget.
  - Schema fields (turn_id, role, content, summary, entities, topic_tags)
    round-trip correctly.

Tests load the FastEmbed dense + BM25 sparse models on first use
(~3 s download, cached afterward). They run on CPU only -- zero VRAM.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List

import pytest


@pytest.fixture(scope="module")
def embedder():
    from ultron.memory import HybridEmbedder
    return HybridEmbedder(eager=True)


@pytest.fixture
def memory(tmp_path: Path, embedder):
    from ultron.memory import ConversationMemory

    mem = ConversationMemory(
        path=tmp_path / "qdrant",
        embedder=embedder,
        recent_cache_size=50,
    )
    yield mem
    mem.close()


def _wait_for_writes(memory, expected_count: int, timeout_s: float = 5.0) -> None:
    """Spin until the Qdrant store reports >= ``expected_count`` points."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if len(memory) >= expected_count:
            return
        time.sleep(0.05)
    pytest.fail(
        f"Async writes never landed: expected {expected_count}, "
        f"have {len(memory)} after {timeout_s}s"
    )


# ---------------------------------------------------------------------------
# Schema / lifecycle
# ---------------------------------------------------------------------------


def test_creates_collections_on_construction(memory, tmp_path):
    """Three collections (conversations, facts, web_results) come up empty."""
    from config import settings

    client = memory._client  # noqa: SLF001 -- tests look at the underlying handle
    names = {c.name for c in client.get_collections().collections}
    assert settings.MEMORY_QDRANT_CONVERSATIONS in names
    assert settings.MEMORY_QDRANT_FACTS in names
    assert settings.MEMORY_QDRANT_WEB_RESULTS in names
    assert len(memory) == 0


# ---------------------------------------------------------------------------
# Hot-path latency (the spec's <10 ms write budget).
# ---------------------------------------------------------------------------


def test_add_returns_within_hot_path_budget(memory):
    """Hot-path enqueue must clear the spec's <10 ms write budget by a wide
    margin -- writes are async, so add() should be ~microseconds."""
    latencies_ms: List[float] = []
    for i in range(20):
        t0 = time.monotonic()
        memory.add("user", f"turn {i} content -- some moderate length text")
        latencies_ms.append((time.monotonic() - t0) * 1000)
    median = sorted(latencies_ms)[len(latencies_ms) // 2]
    p95 = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]
    print(f"\n  add() latency: median={median:.2f} ms  p95={p95:.2f} ms  max={max(latencies_ms):.2f} ms")
    assert max(latencies_ms) < 10.0, (
        f"hot-path write exceeded 10 ms budget: {max(latencies_ms):.2f} ms"
    )


def test_add_persists_asynchronously(memory):
    """Writes don't block the hot path but must still land in Qdrant."""
    for i in range(5):
        memory.add("user", f"persist test {i}")
    _wait_for_writes(memory, 5)
    assert len(memory) == 5


# ---------------------------------------------------------------------------
# recent() / retrieve() correctness.
# ---------------------------------------------------------------------------


def test_recent_returns_chronological_order(memory):
    memory.add("user", "first")
    memory.add("assistant", "first reply")
    memory.add("user", "second")
    memory.add("assistant", "second reply")
    recent = memory.recent(3)
    assert [t.content for t in recent] == ["first reply", "second", "second reply"]


def test_retrieve_returns_semantic_hits(memory):
    """Hybrid retrieval should surface a turn even when the query and the
    stored content share no keywords. The dense vector carries that."""
    memory.add("user", "we decided to use sqlite for the cache")
    memory.add("assistant", "noted")
    memory.add("user", "lets refactor the auth module")
    memory.add("assistant", "okay, what specifically")
    memory.add("user", "whats the weather today")
    memory.add("assistant", "i dont have a sensor for that")
    # Pad with extra turns so the auth turn is older than `exclude_recent=2`.
    for i in range(5):
        memory.add("user", f"unrelated turn {i}")
    _wait_for_writes(memory, 11)

    hits = memory.retrieve("rewrite the login flow", k=3, exclude_recent=2)
    contents = [h.content for h in hits]
    print(f"\n  hits: {contents}")
    assert any("auth" in c or "login" in c for c in contents), (
        f"expected an auth/login hit in top-3, got: {contents}"
    )


def test_retrieve_respects_exclude_recent(memory):
    """Turns inside the recent window must NOT appear in retrieve results."""
    for i in range(15):
        memory.add("user", f"turn number {i} about widgets")
    _wait_for_writes(memory, 15)

    # exclude_recent=15 means everything is in the recent window -> empty.
    hits = memory.retrieve("widgets", k=5, exclude_recent=15)
    assert hits == []

    # exclude_recent=5 means turns 0..9 are searchable.
    hits = memory.retrieve("widgets", k=5, exclude_recent=5)
    assert all(h.id < 10 for h in hits), [h.id for h in hits]


def test_retrieve_meets_read_budget(memory):
    """Retrieval (embedding + Qdrant query) must complete within 200 ms."""
    for i in range(50):
        memory.add("user", f"some content about topic {i}")
    _wait_for_writes(memory, 50)

    # Warmup -- first query loads FastEmbed query encoders if not already.
    memory.retrieve("warmup query", k=5, exclude_recent=10)

    latencies_ms: List[float] = []
    for q in (
        "tell me about widgets",
        "how does this work",
        "find the recipe",
        "what is the deadline",
        "any updates",
    ):
        t0 = time.monotonic()
        memory.retrieve(q, k=5, exclude_recent=10)
        latencies_ms.append((time.monotonic() - t0) * 1000)
    median = sorted(latencies_ms)[len(latencies_ms) // 2]
    print(f"\n  retrieve(): median={median:.0f} ms  max={max(latencies_ms):.0f} ms")
    assert median < 200.0, f"retrieve median {median:.0f} ms exceeds 200 ms budget"


# ---------------------------------------------------------------------------
# Schema round-trip.
# ---------------------------------------------------------------------------


def test_payload_round_trip(memory):
    """Phase 3 fields (summary, entities, topic_tags, cluster_id) must
    survive a write/read cycle so the maintenance script can populate them."""
    memory.add("user", "hello")
    _wait_for_writes(memory, 1)

    # Fetch from Qdrant directly, set the metadata fields, read back via
    # the public retrieve() to confirm they appear on MemoryTurn.
    from config import settings

    points, _ = memory._client.scroll(  # noqa: SLF001
        collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    assert points
    pid = points[0].id
    memory._client.set_payload(  # noqa: SLF001
        collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
        payload={
            "summary": "user said hello",
            "entities": ["greeting"],
            "topic_tags": ["smalltalk"],
            "cluster_id": 7,
        },
        points=[pid],
    )

    # Pad so retrieve() doesn't filter out the only turn as 'recent'.
    for i in range(25):
        memory.add("user", f"padding turn {i}")
    _wait_for_writes(memory, 26)

    hits = memory.retrieve("hello", k=10, exclude_recent=20)
    matched = [h for h in hits if h.summary == "user said hello"]
    assert matched, "the seeded turn didn't survive retrieval"
    h = matched[0]
    assert h.entities == ["greeting"]
    assert h.topic_tags == ["smalltalk"]
    assert h.cluster_id == 7
