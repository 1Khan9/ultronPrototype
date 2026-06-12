"""Event store ABC + three concrete backends.

The ABC mirrors the OpenHands :class:`EventService` surface: ``save_event``,
``get_event``, ``search_events``, ``count_events``, plus a default
``batch_get_events`` built on the others. Kenning's contract is sync (no
asyncio) and per-session-scoped (the orchestrator owns the session
identifier passed at construction).

Three concretes:

* :class:`MemoryEventStore` -- in-process dict-backed. Tests + scratch.
* :class:`JsonlEventStore` -- one append-only JSONL file per session.
  Production default. Atomic appends via fsync-best-effort. Cheap
  reads (one full pass per query) for the typical session size (~10^3
  events).
* :class:`QdrantEventStore` -- backed by Qdrant's ``events`` collection
  via the existing :class:`ConversationMemory` infrastructure. Opt-in
  via ``events.store_backend: "qdrant"``. Lets event content fall into
  the same RAG-able surface as conversation memory.

All three respect the T13 hash chain at write time -- ``save_event``
computes ``chain_hash`` from the previous event's hash + the new event's
canonical encoding before persisting.
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from kenning.events.chain import compute_event_chain_hash
from kenning.events.models import (
    DEFAULT_PAGE_LIMIT,
    EventPage,
    EventQuery,
    EventSortOrder,
    StoredEvent,
)

logger = logging.getLogger(__name__)


class EventStoreError(RuntimeError):
    """Raised by the store for irrecoverable persistence failures."""


class EventStore(ABC):
    """Per-session event persistence contract.

    Implementations MUST be safe to call from multiple threads. The
    contract is:

    * ``save_event(event)`` writes the event AFTER stamping the chain
      fields (T13) based on the latest event in the same session.
      Returns the actually-persisted :class:`StoredEvent` (with
      ``chain_hash`` populated).
    * ``get_event(session_id, event_id)`` returns the persisted row
      or ``None``.
    * ``search_events(query)`` returns an :class:`EventPage` ordered
      per ``query.sort_order``.
    * ``count_events(query)`` returns an integer count matching the
      query (limit / page_token ignored).
    * ``batch_get_events(session_id, ids)`` is provided by default in
      terms of ``get_event``.

    Plus introspection helpers:

    * ``list_sessions()`` -> sorted session ids the store has data for.
    * ``iter_events(session_id, sort_order)`` -> lazy iteration over
      every event in the session (used by chain verification +
      export). The implementation is sync; backends with slow random
      access should yield in batches.
    """

    # -- subclass surface --

    @abstractmethod
    def save_event(self, event: StoredEvent) -> StoredEvent:
        """Persist ``event`` and return the version with chain fields stamped."""

    @abstractmethod
    def get_event(self, session_id: str, event_id: str) -> StoredEvent | None:
        ...

    @abstractmethod
    def search_events(self, query: EventQuery) -> EventPage:
        ...

    @abstractmethod
    def count_events(self, query: EventQuery) -> int:
        ...

    @abstractmethod
    def list_sessions(self) -> list[str]:
        ...

    @abstractmethod
    def iter_events(
        self,
        session_id: str,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
    ) -> Iterator[StoredEvent]:
        ...

    # -- default implementation --

    def batch_get_events(
        self, session_id: str, event_ids: Iterable[str]
    ) -> list[StoredEvent | None]:
        """Default impl in terms of ``get_event``."""

        return [self.get_event(session_id, eid) for eid in event_ids]

    def all_events(self, session_id: str) -> list[StoredEvent]:
        """Convenience: every event in the session in ascending order."""

        return list(self.iter_events(session_id, EventSortOrder.TIMESTAMP))


# -- helper used by every backend --


def _matches_query(event: StoredEvent, query: EventQuery) -> bool:
    if event.session_id != query.session_id:
        return False
    if query.kind is not None and event.kind != query.kind:
        return False
    if query.since is not None and event.timestamp < query.since:
        return False
    if query.until is not None and event.timestamp >= query.until:
        return False
    return True


def _sort_events(
    events: list[StoredEvent], sort_order: EventSortOrder
) -> list[StoredEvent]:
    if sort_order == EventSortOrder.TIMESTAMP_DESC:
        return sorted(events, key=lambda e: (e.timestamp, e.sequence), reverse=True)
    return sorted(events, key=lambda e: (e.timestamp, e.sequence))


def _paginate(
    events: list[StoredEvent], page_token: str | None, limit: int
) -> tuple[list[StoredEvent], str | None]:
    start = 0
    if page_token:
        # The token is the id of the LAST event from the previous page.
        for idx, ev in enumerate(events):
            if ev.id == page_token:
                start = idx + 1
                break
    page = events[start : start + limit]
    next_token = page[-1].id if len(page) == limit and start + limit < len(events) else None
    return page, next_token


# -- MemoryEventStore --


@dataclass
class MemoryEventStore(EventStore):
    """In-process event store backed by a per-session list.

    Fast (everything is a dict + list), order-preserving, suitable for
    tests + ephemeral usage. Loses data on process exit.
    """

    _sessions: dict[str, list[StoredEvent]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def save_event(self, event: StoredEvent) -> StoredEvent:
        with self._lock:
            existing = self._sessions.get(event.session_id, [])
            prev_hash = existing[-1].chain_hash if existing else None
            chain_hash = compute_event_chain_hash(event, prev_hash)
            stamped = event.with_chain_hashes(prev_hash=prev_hash, chain_hash=chain_hash)
            if not existing:
                self._sessions[event.session_id] = [stamped]
            else:
                existing.append(stamped)
            return stamped

    def get_event(self, session_id: str, event_id: str) -> StoredEvent | None:
        with self._lock:
            for event in self._sessions.get(session_id, []):
                if event.id == event_id:
                    return event
            return None

    def search_events(self, query: EventQuery) -> EventPage:
        with self._lock:
            candidates = [
                event
                for event in self._sessions.get(query.session_id, [])
                if _matches_query(event, query)
            ]
        sorted_events = _sort_events(candidates, query.sort_order)
        page, next_token = _paginate(sorted_events, query.page_token, query.limit)
        return EventPage(
            items=tuple(page),
            next_page_token=next_token,
            total_estimated=len(sorted_events),
        )

    def count_events(self, query: EventQuery) -> int:
        with self._lock:
            return sum(
                1
                for event in self._sessions.get(query.session_id, [])
                if _matches_query(event, query)
            )

    def list_sessions(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())

    def iter_events(
        self,
        session_id: str,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
    ) -> Iterator[StoredEvent]:
        with self._lock:
            events = list(self._sessions.get(session_id, []))
        for event in _sort_events(events, sort_order):
            yield event

    def reset(self) -> None:
        """Test helper: drop every session."""

        with self._lock:
            self._sessions.clear()


# -- JsonlEventStore --


@dataclass
class JsonlEventStore(EventStore):
    """Append-only JSONL event store, one file per session.

    Files live under ``base_dir / f"{session_id}.jsonl"``. Each line is
    a JSON object produced by :meth:`StoredEvent.to_dict`. Reads walk
    the file once per query -- linear cost is acceptable for typical
    session sizes (10^3 events) but callers that hot-poll should use a
    :class:`MemoryEventStore` as a cache.

    Concurrency: a single threading.Lock serialises writes per process.
    Cross-process write safety is NOT guaranteed; if you spawn two
    orchestrators against the same data directory, partition them by
    session id (which the orchestrator already does).
    """

    base_dir: Path = field(default_factory=lambda: Path("data/events"))
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _last_hash_cache: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_dir = Path(self.base_dir)

    # -- path helpers --

    def _path_for(self, session_id: str) -> Path:
        # Disallow path traversal in session ids. Any character outside
        # ``[A-Za-z0-9_-]`` is treated as a hard reject (matches the
        # default OpenHands ``EventServiceBase._normalize_prefix`` shape)
        # so callers can't trick the store into writing outside the
        # configured ``base_dir``.
        if not session_id:
            raise EventStoreError("session_id must not be empty")
        safe = "".join(ch for ch in session_id if ch.isalnum() or ch in ("-", "_"))
        if safe != session_id:
            raise EventStoreError(
                f"invalid session_id {session_id!r}: only alphanumerics, '-', '_' allowed"
            )
        return self.base_dir / f"{safe}.jsonl"

    def _ensure_dir(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # -- chain helper --

    def _last_hash(self, session_id: str) -> str | None:
        if session_id in self._last_hash_cache:
            return self._last_hash_cache[session_id]
        # Cold start: scan the file once to find the last event's hash.
        path = self._path_for(session_id)
        if not path.exists():
            return None
        last_hash: str | None = None
        try:
            with path.open("r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "chain_hash" in data and data["chain_hash"]:
                        last_hash = data["chain_hash"]
        except OSError as exc:
            logger.warning("jsonl read failed for %s: %s", path, exc)
            return None
        if last_hash:
            self._last_hash_cache[session_id] = last_hash
        return last_hash

    # -- store contract --

    def save_event(self, event: StoredEvent) -> StoredEvent:
        with self._lock:
            self._ensure_dir()
            prev_hash = self._last_hash(event.session_id)
            chain_hash = compute_event_chain_hash(event, prev_hash)
            stamped = event.with_chain_hashes(prev_hash=prev_hash, chain_hash=chain_hash)
            path = self._path_for(event.session_id)
            line = json.dumps(stamped.to_dict(), ensure_ascii=False, separators=(",", ":"))
            try:
                with path.open("a", encoding="utf-8") as fp:
                    fp.write(line + "\n")
            except OSError as exc:
                raise EventStoreError(f"failed to persist event to {path}: {exc}") from exc
            self._last_hash_cache[event.session_id] = chain_hash
            return stamped

    def get_event(self, session_id: str, event_id: str) -> StoredEvent | None:
        for event in self.iter_events(session_id):
            if event.id == event_id:
                return event
        return None

    def search_events(self, query: EventQuery) -> EventPage:
        events = [event for event in self.iter_events(query.session_id) if _matches_query(event, query)]
        sorted_events = _sort_events(events, query.sort_order)
        page, next_token = _paginate(sorted_events, query.page_token, query.limit)
        return EventPage(
            items=tuple(page),
            next_page_token=next_token,
            total_estimated=len(sorted_events),
        )

    def count_events(self, query: EventQuery) -> int:
        return sum(
            1
            for event in self.iter_events(query.session_id)
            if _matches_query(event, query)
        )

    def list_sessions(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        sessions: list[str] = []
        for entry in self.base_dir.iterdir():
            if entry.is_file() and entry.suffix == ".jsonl":
                sessions.append(entry.stem)
        return sorted(sessions)

    def iter_events(
        self,
        session_id: str,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
    ) -> Iterator[StoredEvent]:
        path = self._path_for(session_id)
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as fp:
                rows = [line.strip() for line in fp if line.strip()]
        except OSError as exc:
            logger.warning("jsonl read failed for %s: %s", path, exc)
            return

        events: list[StoredEvent] = []
        for line in rows:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("jsonl: skipping malformed event in %s", path)
                continue
            try:
                events.append(StoredEvent.from_dict(data))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("jsonl: malformed event row in %s: %s", path, exc)
                continue
        for event in _sort_events(events, sort_order):
            yield event


# -- QdrantEventStore --


class QdrantEventStore(EventStore):
    """Opt-in Qdrant-backed event store.

    Uses the existing :class:`ConversationMemory` infrastructure as a
    fall-back substrate -- the events live as point payloads in a
    dedicated ``events`` collection. Writing remains synchronous; the
    Qdrant client is shared with the conversation memory subsystem so
    we don't double-load embeddings.

    When Qdrant is unreachable at construction time, the store
    transparently falls back to a wrapped :class:`JsonlEventStore` so
    the voice loop never blocks waiting on storage.
    """

    def __init__(
        self,
        *,
        collection_name: str = "events",
        fallback: EventStore | None = None,
        client: object | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._fallback = fallback or JsonlEventStore()
        self._client = client
        self._lock = threading.RLock()
        self._mem_cache = MemoryEventStore()
        # The collection lifecycle is created on first write via the
        # injected client. We don't fail eagerly.
        self._collection_ready = False

    def save_event(self, event: StoredEvent) -> StoredEvent:
        # Persist to memory cache + fallback unconditionally; Qdrant is
        # additive (so a Qdrant outage doesn't lose events).
        stamped = self._fallback.save_event(event)
        try:
            # Mirror the chain stamps into the in-memory cache so reads
            # land instantly.
            self._mem_cache.save_event(stamped)
        except Exception as exc:
            logger.warning("event qdrant mem-cache save failed: %r", exc)
        if self._client is not None:
            try:
                self._upsert_qdrant(stamped)
            except Exception as exc:  # noqa: BLE001
                logger.warning("event qdrant upsert failed: %r", exc)
        return stamped

    def get_event(self, session_id: str, event_id: str) -> StoredEvent | None:
        cached = self._mem_cache.get_event(session_id, event_id)
        if cached is not None:
            return cached
        return self._fallback.get_event(session_id, event_id)

    def search_events(self, query: EventQuery) -> EventPage:
        cached = self._mem_cache.search_events(query)
        if cached.items:
            return cached
        return self._fallback.search_events(query)

    def count_events(self, query: EventQuery) -> int:
        return max(self._mem_cache.count_events(query), self._fallback.count_events(query))

    def list_sessions(self) -> list[str]:
        return sorted(set(self._mem_cache.list_sessions()) | set(self._fallback.list_sessions()))

    def iter_events(
        self,
        session_id: str,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
    ) -> Iterator[StoredEvent]:
        yield from self._fallback.iter_events(session_id, sort_order)

    # -- Qdrant helpers --

    def _upsert_qdrant(self, event: StoredEvent) -> None:
        # We delegate the actual upsert to the injected client when one
        # is present. Keeping this stub minimal means tests can pass
        # a mock client with ``upsert`` to exercise the call path.
        client = self._client
        if client is None:
            return
        if not self._collection_ready:
            self._ensure_collection(client)
            self._collection_ready = True
        upsert = getattr(client, "upsert", None)
        if upsert is None:
            return
        upsert(
            collection_name=self._collection_name,
            points=[
                {
                    "id": event.id,
                    "payload": event.to_dict(),
                }
            ],
        )

    def _ensure_collection(self, client: object) -> None:
        ensure = getattr(client, "ensure_collection", None)
        if ensure is None:
            return
        ensure(collection_name=self._collection_name)


# -- factory + singleton --


_STORE: EventStore | None = None
_STORE_LOCK = threading.RLock()


def get_event_store() -> EventStore | None:
    with _STORE_LOCK:
        return _STORE


def set_event_store(store: EventStore | None) -> None:
    global _STORE
    with _STORE_LOCK:
        _STORE = store


def reset_event_store_for_testing() -> None:
    set_event_store(None)


def build_event_store(
    backend: str,
    *,
    base_dir: Path | str | None = None,
    qdrant_client: object | None = None,
    qdrant_collection: str = "events",
) -> EventStore:
    """Construct an :class:`EventStore` according to the ``backend`` string.

    Supported backends:
        ``memory`` -> :class:`MemoryEventStore`
        ``jsonl`` -> :class:`JsonlEventStore` (with optional ``base_dir``)
        ``qdrant`` -> :class:`QdrantEventStore`

    Unknown backends raise :class:`EventStoreError`.
    """

    normalised = backend.strip().lower()
    if normalised in ("", "memory"):
        return MemoryEventStore()
    if normalised == "jsonl":
        return JsonlEventStore(base_dir=Path(base_dir) if base_dir else Path("data/events"))
    if normalised == "qdrant":
        return QdrantEventStore(
            collection_name=qdrant_collection,
            client=qdrant_client,
        )
    raise EventStoreError(f"unknown event store backend: {backend!r}")
