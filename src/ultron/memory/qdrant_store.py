"""Qdrant-backed conversation memory with hybrid search.

Architecture (per spec):
- Three collections: ``conversations`` (turn-level), ``facts`` (durable
  extracted statements), ``web_results`` (cached URL fetches, populated by
  Phase 4).
- Each conversation point carries a 384-dim dense bge-small vector + a BM25
  sparse vector. Hybrid retrieval issues a single Qdrant ``query_points``
  call with prefetch on both vectors and Reciprocal Rank Fusion.
- Hot-path write path: append to in-process recent-turns cache + push to a
  background queue. The writer thread embeds + upserts; failures log and
  drop. Worst-case <1 ms on the hot path.
- Hot-path read path: ``recent()`` reads the in-process cache; ``retrieve()``
  hits Qdrant + the embedder (~150 ms cold).

The public surface (``ConversationMemory.add / recent / retrieve / close``)
matches the legacy JSONL store so callers (LLMEngine, orchestrator) don't
need to change.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from config import settings
from ultron.memory.embedder import HybridEmbedder, _SparseVec
from ultron.utils.logging import get_logger

logger = get_logger("memory.qdrant_store")


# ---------------------------------------------------------------------------
# Public data class -- a "turn" returned to callers. We keep the legacy field
# names (id, ts, role, content) so existing call sites don't break, plus the
# Phase 3 fields populated by the maintenance script (summary, entities,
# topic_tags, cluster_id).
# ---------------------------------------------------------------------------


@dataclass
class MemoryTurn:
    id: int
    ts: float
    role: str  # "user" | "assistant"
    content: str
    session_id: str = ""
    summary: str = ""
    entities: List[str] = field(default_factory=list)
    topic_tags: List[str] = field(default_factory=list)
    cluster_id: Optional[int] = None


# ---------------------------------------------------------------------------
# ConversationMemory: same surface as the JSONL store, Qdrant under the hood.
# ---------------------------------------------------------------------------


class ConversationMemory:
    """Qdrant-backed conversation memory.

    Args:
        path: directory for the embedded Qdrant store. Created if missing.
        embedder: a :class:`HybridEmbedder`. Required for write + retrieve.
        recent_cache_size: how many recent turns to keep in process. Default
            big enough that ``recent(MEMORY_RECENT_TURNS)`` always serves
            from cache; older turns are still searchable via ``retrieve()``.
        session_id: tag for the current run. Lets ``retrieve()`` exclude
            current-session turns from RAG hits if desired.
    """

    def __init__(
        self,
        path: Path = settings.MEMORY_QDRANT_PATH,
        embedder: Optional[HybridEmbedder] = None,
        recent_cache_size: int = 100,
        session_id: Optional[str] = None,
    ) -> None:
        if embedder is None:
            raise ValueError(
                "ConversationMemory needs a HybridEmbedder. Pass embedder=HybridEmbedder()."
            )
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder
        self._recent_cache_size = recent_cache_size
        self.session_id = session_id or _new_session_id()

        # Lazy-imported here so a missing qdrant-client install doesn't crash
        # at module import time -- the orchestrator's _load_memory_if_enabled
        # catches the resulting ValueError and disables memory gracefully.
        from qdrant_client import QdrantClient

        self._client = QdrantClient(path=str(self.path))
        self._lock = threading.RLock()

        self._ensure_collections()

        # Recent-turn cache + next-id tracking are warmed from Qdrant.
        self._recent: List[MemoryTurn] = []
        self._next_id: int = 0
        self._load_recent_cache_from_qdrant()

        # Async writer.
        self._write_queue: "queue.Queue[Optional[MemoryTurn]]" = queue.Queue(
            maxsize=settings.MEMORY_WRITE_QUEUE_MAXSIZE
        )
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="memory-writer"
        )
        self._writer_thread.start()

        logger.info(
            "ConversationMemory ready: %d recent turns cached, session=%s, path=%s",
            len(self._recent), self.session_id, self.path,
        )

    # --- collection bootstrap -----------------------------------------------

    def _ensure_collections(self) -> None:
        """Create the three collections on first run; no-op afterward."""
        from qdrant_client.models import (
            Distance,
            SparseVectorParams,
            VectorParams,
        )

        names = {c.name for c in self._client.get_collections().collections}

        common_dense = {"dense": VectorParams(size=self._embedder.dim, distance=Distance.COSINE)}
        common_sparse = {"bm25": SparseVectorParams()}

        if settings.MEMORY_QDRANT_CONVERSATIONS not in names:
            self._client.create_collection(
                collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
                vectors_config=common_dense,
                sparse_vectors_config=common_sparse,
            )
            logger.info("Created Qdrant collection %s", settings.MEMORY_QDRANT_CONVERSATIONS)
        if settings.MEMORY_QDRANT_FACTS not in names:
            self._client.create_collection(
                collection_name=settings.MEMORY_QDRANT_FACTS,
                vectors_config=common_dense,
                sparse_vectors_config=common_sparse,
            )
            logger.info("Created Qdrant collection %s", settings.MEMORY_QDRANT_FACTS)
        if settings.MEMORY_QDRANT_WEB_RESULTS not in names:
            self._client.create_collection(
                collection_name=settings.MEMORY_QDRANT_WEB_RESULTS,
                vectors_config=common_dense,
                sparse_vectors_config=common_sparse,
            )
            logger.info("Created Qdrant collection %s", settings.MEMORY_QDRANT_WEB_RESULTS)

    def _load_recent_cache_from_qdrant(self) -> None:
        """Pull the most-recent N turns into the in-process cache + set next id.

        Avoids loading the entire history. Uses Qdrant's ``scroll`` API with
        ordering by id descending, then reverses to chronological order.
        """
        from qdrant_client.models import OrderBy, Direction

        try:
            # Newest-first scan, capped at recent_cache_size. The integer
            # turn-id we store in payload is the source of ordering.
            points, _ = self._client.scroll(
                collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
                limit=self._recent_cache_size,
                with_payload=True,
                with_vectors=False,
                order_by=OrderBy(key="turn_id", direction=Direction.DESC),
            )
        except Exception as e:
            # An empty / fresh collection can sometimes raise on the
            # ordered-scroll path; fall back to a plain scroll.
            logger.debug("Ordered scroll failed (%s); falling back", e)
            try:
                points, _ = self._client.scroll(
                    collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
                    limit=self._recent_cache_size,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception:
                points = []

        turns = []
        max_id = -1
        for pt in points:
            payload = pt.payload or {}
            turn_id = int(payload.get("turn_id", 0))
            if turn_id > max_id:
                max_id = turn_id
            turns.append(_payload_to_turn(payload))
        # Sort chronologically (ascending id).
        turns.sort(key=lambda t: t.id)
        self._recent = turns[-self._recent_cache_size:]
        self._next_id = max_id + 1 if max_id >= 0 else 0

    # --- write path ---------------------------------------------------------

    def add(self, role: str, content: str) -> MemoryTurn:
        """Append a turn, return immediately. Persistence is async.

        The hot path:
          * stamps a turn id + timestamp,
          * appends to the in-process recent cache,
          * enqueues the turn for the writer thread.

        On queue overflow we log and drop the new turn rather than block --
        the spec gives us a hard "must not regress latency" budget.
        """
        with self._lock:
            turn = MemoryTurn(
                id=self._next_id,
                ts=time.time(),
                role=role,
                content=content,
                session_id=self.session_id,
            )
            self._next_id += 1
            self._recent.append(turn)
            if len(self._recent) > self._recent_cache_size:
                # Drop oldest entries -- they remain in Qdrant and are still
                # retrievable via the RAG path.
                self._recent = self._recent[-self._recent_cache_size:]
        try:
            self._write_queue.put_nowait(turn)
        except queue.Full:
            logger.warning(
                "Memory writer queue full (%d) -- dropping turn %d. "
                "Hot path stays responsive but this turn won't be RAG-indexed.",
                self._write_queue.maxsize, turn.id,
            )
        return turn

    def _writer_loop(self) -> None:
        """Background thread: drain the queue, embed, upsert into Qdrant."""
        while True:
            try:
                turn = self._write_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if turn is None:  # shutdown sentinel
                return
            try:
                self._upsert_turn(turn)
            except Exception as e:
                logger.warning("Async upsert failed for turn %d: %s", turn.id, e)
            finally:
                self._write_queue.task_done()

    def _upsert_turn(self, turn: MemoryTurn) -> None:
        from qdrant_client.models import PointStruct, SparseVector

        # Embed content as both dense + sparse. The role prefix is identical
        # to the legacy embedder (preserves retrieval behavior) but stripped
        # for BM25 since it'd act as a noisy stop-token.
        text_dense = f"{turn.role}: {turn.content}"
        dvec = self._embedder.encode_dense(text_dense)
        svec = self._embedder.encode_sparse(turn.content)[0]

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector={
                "dense": dvec.tolist(),
                "bm25": SparseVector(indices=svec.indices, values=svec.values),
            },
            payload={
                "turn_id": turn.id,
                "ts": turn.ts,
                "role": turn.role,
                "content": turn.content,
                "session_id": turn.session_id,
                "summary": turn.summary,
                "entities": turn.entities,
                "topic_tags": turn.topic_tags,
                "cluster_id": turn.cluster_id,
            },
        )
        self._client.upsert(
            collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
            points=[point],
        )

    # --- read path ----------------------------------------------------------

    def recent(self, n: int) -> List[MemoryTurn]:
        """Return the last ``n`` turns chronologically, served from cache."""
        if n <= 0:
            return []
        with self._lock:
            return list(self._recent[-n:])

    def retrieve(
        self,
        query: str,
        k: int = settings.MEMORY_RAG_TOP_K,
        exclude_recent: int = settings.MEMORY_RAG_EXCLUDE_RECENT,
    ) -> List[MemoryTurn]:
        """Top-``k`` turns by hybrid (dense + BM25, RRF-fused), excluding the
        last ``exclude_recent`` turn ids (the recent window the LLM already sees).

        Returns ``[]`` for empty query, empty store, or when everything is in
        the recent window.
        """
        if not query.strip():
            return []
        with self._lock:
            cutoff_id = max(0, self._next_id - exclude_recent)
        if cutoff_id <= 0:
            # Nothing older than the recent window yet.
            return []

        from qdrant_client.models import (
            FieldCondition,
            Filter,
            Fusion,
            FusionQuery,
            Prefetch,
            Range,
            SparseVector,
        )

        try:
            qdv = self._embedder.encode_query_dense(query)
            qsv: _SparseVec = self._embedder.encode_query_sparse(query)
        except Exception as e:
            logger.warning("Query embedding failed: %s", e)
            return []

        # Filter to turn_id < cutoff (the older-than-recent window).
        recency_filter = Filter(
            must=[FieldCondition(key="turn_id", range=Range(lt=cutoff_id))]
        )

        try:
            response = self._client.query_points(
                collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
                prefetch=[
                    Prefetch(
                        query=qdv.tolist(),
                        using="dense",
                        filter=recency_filter,
                        limit=max(k * 4, 20),
                    ),
                    Prefetch(
                        query=SparseVector(
                            indices=qsv.indices, values=qsv.values
                        ),
                        using="bm25",
                        filter=recency_filter,
                        limit=max(k * 4, 20),
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=max(1, k),
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            logger.warning("Qdrant hybrid search failed: %s", e)
            return []

        return [_payload_to_turn(pt.payload or {}) for pt in response.points]

    # --- introspection ------------------------------------------------------

    def __len__(self) -> int:
        try:
            return self._client.count(
                collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
                exact=False,
            ).count
        except Exception:
            return len(self._recent)

    def close(self) -> None:
        """Drain the writer queue and close the Qdrant client."""
        try:
            # Wait for in-flight writes to complete (~ms each, capped).
            self._write_queue.join()
        except Exception:
            pass
        try:
            self._write_queue.put_nowait(None)
        except queue.Full:
            pass
        self._writer_thread.join(timeout=2.0)
        try:
            self._client.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def _payload_to_turn(payload: dict) -> MemoryTurn:
    return MemoryTurn(
        id=int(payload.get("turn_id", 0)),
        ts=float(payload.get("ts", 0.0)),
        role=str(payload.get("role", "")),
        content=str(payload.get("content", "")),
        session_id=str(payload.get("session_id", "")),
        summary=str(payload.get("summary", "")),
        entities=list(payload.get("entities") or []),
        topic_tags=list(payload.get("topic_tags") or []),
        cluster_id=payload.get("cluster_id"),
    )
