"""Tests for the EventStore backends + factory + singleton."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultron.events.chain import verify_chain
from ultron.events.models import (
    EventKind,
    EventQuery,
    EventSortOrder,
    StoredEvent,
)
from ultron.events.store import (
    EventStoreError,
    JsonlEventStore,
    MemoryEventStore,
    QdrantEventStore,
    build_event_store,
    get_event_store,
    reset_event_store_for_testing,
    set_event_store,
)


@pytest.fixture(autouse=True)
def _isolate_singleton():
    reset_event_store_for_testing()
    yield
    reset_event_store_for_testing()


def _make_event(session_id: str, kind: str, ts: float = 1.0, **payload) -> StoredEvent:
    return StoredEvent.make(session_id, kind, payload=payload, timestamp=ts)


# -- MemoryEventStore --


def test_memory_save_stamps_chain():
    store = MemoryEventStore()
    a = store.save_event(_make_event("s1", "A", ts=1.0))
    b = store.save_event(_make_event("s1", "B", ts=2.0))
    assert a.chain_prev_hash is None
    assert a.chain_hash is not None
    assert b.chain_prev_hash == a.chain_hash
    assert b.chain_hash != a.chain_hash


def test_memory_chain_verifies_across_session():
    store = MemoryEventStore()
    for i in range(5):
        store.save_event(_make_event("sess", f"K{i}", ts=float(i)))
    events = store.all_events("sess")
    result = verify_chain(events)
    assert result.ok is True
    assert result.events_checked == 5


def test_memory_search_by_kind():
    store = MemoryEventStore()
    store.save_event(_make_event("s", "Alpha", ts=1.0))
    store.save_event(_make_event("s", "Beta", ts=2.0))
    store.save_event(_make_event("s", "Alpha", ts=3.0))
    page = store.search_events(EventQuery(session_id="s", kind="Alpha"))
    assert len(page.items) == 2
    assert all(e.kind == "Alpha" for e in page.items)


def test_memory_search_by_time_window():
    store = MemoryEventStore()
    store.save_event(_make_event("s", "K", ts=1.0))
    store.save_event(_make_event("s", "K", ts=5.0))
    store.save_event(_make_event("s", "K", ts=10.0))
    page = store.search_events(EventQuery(session_id="s", since=2.0, until=9.0))
    assert len(page.items) == 1
    assert page.items[0].timestamp == 5.0


def test_memory_search_sort_order():
    store = MemoryEventStore()
    store.save_event(_make_event("s", "K", ts=1.0))
    store.save_event(_make_event("s", "K", ts=3.0))
    store.save_event(_make_event("s", "K", ts=2.0))
    asc_page = store.search_events(EventQuery(session_id="s"))
    desc_page = store.search_events(
        EventQuery(session_id="s", sort_order=EventSortOrder.TIMESTAMP_DESC)
    )
    assert [e.timestamp for e in asc_page.items] == [1.0, 2.0, 3.0]
    assert [e.timestamp for e in desc_page.items] == [3.0, 2.0, 1.0]


def test_memory_pagination():
    store = MemoryEventStore()
    for i in range(10):
        store.save_event(_make_event("s", "K", ts=float(i)))
    first = store.search_events(EventQuery(session_id="s", limit=4))
    assert len(first.items) == 4
    assert first.next_page_token is not None
    second = store.search_events(
        EventQuery(session_id="s", limit=4, page_token=first.next_page_token)
    )
    assert len(second.items) == 4
    assert second.items[0].timestamp == 4.0


def test_memory_count_events():
    store = MemoryEventStore()
    store.save_event(_make_event("s", "A"))
    store.save_event(_make_event("s", "B"))
    store.save_event(_make_event("s", "A"))
    assert store.count_events(EventQuery(session_id="s")) == 3
    assert store.count_events(EventQuery(session_id="s", kind="A")) == 2
    assert store.count_events(EventQuery(session_id="missing")) == 0


def test_memory_get_event_returns_persisted_row():
    store = MemoryEventStore()
    saved = store.save_event(_make_event("s", "A"))
    fetched = store.get_event("s", saved.id)
    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.chain_hash == saved.chain_hash


def test_memory_get_event_missing_returns_none():
    store = MemoryEventStore()
    assert store.get_event("missing", "id") is None


def test_memory_batch_get_events():
    store = MemoryEventStore()
    a = store.save_event(_make_event("s", "A"))
    b = store.save_event(_make_event("s", "B"))
    result = store.batch_get_events("s", [a.id, "nonexistent", b.id])
    assert result[0].id == a.id  # type: ignore[union-attr]
    assert result[1] is None
    assert result[2].id == b.id  # type: ignore[union-attr]


def test_memory_list_sessions():
    store = MemoryEventStore()
    store.save_event(_make_event("session_b", "K"))
    store.save_event(_make_event("session_a", "K"))
    assert store.list_sessions() == ["session_a", "session_b"]


def test_memory_session_isolation():
    store = MemoryEventStore()
    store.save_event(_make_event("s1", "K"))
    store.save_event(_make_event("s2", "K"))
    assert store.count_events(EventQuery(session_id="s1")) == 1
    assert store.count_events(EventQuery(session_id="s2")) == 1


# -- JsonlEventStore --


def test_jsonl_persists_and_reloads(tmp_path: Path):
    store = JsonlEventStore(base_dir=tmp_path)
    saved = store.save_event(_make_event("s1", "A", ts=1.0))
    # Re-open the store and read.
    fresh = JsonlEventStore(base_dir=tmp_path)
    fetched = fresh.get_event("s1", saved.id)
    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.kind == "A"
    assert fetched.chain_hash == saved.chain_hash


def test_jsonl_chain_continues_across_reopen(tmp_path: Path):
    store_a = JsonlEventStore(base_dir=tmp_path)
    a = store_a.save_event(_make_event("s", "A", ts=1.0))
    # Reopen + write another event; the chain should continue cleanly.
    store_b = JsonlEventStore(base_dir=tmp_path)
    b = store_b.save_event(_make_event("s", "B", ts=2.0))
    assert b.chain_prev_hash == a.chain_hash
    events = store_b.all_events("s")
    assert verify_chain(events).ok is True


def test_jsonl_list_sessions(tmp_path: Path):
    store = JsonlEventStore(base_dir=tmp_path)
    store.save_event(_make_event("alpha", "K"))
    store.save_event(_make_event("bravo", "K"))
    assert store.list_sessions() == ["alpha", "bravo"]


def test_jsonl_rejects_invalid_session_id(tmp_path: Path):
    store = JsonlEventStore(base_dir=tmp_path)
    with pytest.raises(EventStoreError):
        store.save_event(_make_event("../bad", "K"))


def test_jsonl_skips_malformed_lines(tmp_path: Path, caplog):
    import logging
    caplog.set_level(logging.WARNING)
    store = JsonlEventStore(base_dir=tmp_path)
    valid = store.save_event(_make_event("s", "K"))

    target = tmp_path / "s.jsonl"
    with target.open("a", encoding="utf-8") as fp:
        fp.write("this is not json\n")
        fp.write("{\"id\": \"id2\"}\n")  # missing required fields

    events = store.all_events("s")
    # Only the valid event survives.
    assert [e.id for e in events] == [valid.id]


def test_jsonl_search_and_count(tmp_path: Path):
    store = JsonlEventStore(base_dir=tmp_path)
    for kind in ("Alpha", "Beta", "Alpha", "Gamma"):
        store.save_event(_make_event("s", kind))
    page = store.search_events(EventQuery(session_id="s", kind="Alpha"))
    assert len(page.items) == 2
    assert store.count_events(EventQuery(session_id="s", kind="Beta")) == 1


def test_jsonl_missing_session_returns_empty(tmp_path: Path):
    store = JsonlEventStore(base_dir=tmp_path)
    page = store.search_events(EventQuery(session_id="never_existed"))
    assert page.items == ()
    assert store.count_events(EventQuery(session_id="never_existed")) == 0
    assert list(store.iter_events("never_existed")) == []


# -- QdrantEventStore --


def test_qdrant_save_falls_back_to_jsonl(tmp_path: Path):
    fallback = JsonlEventStore(base_dir=tmp_path)
    store = QdrantEventStore(fallback=fallback)
    saved = store.save_event(_make_event("s", "A"))
    # The fallback persists the row even without a Qdrant client.
    fetched = fallback.get_event("s", saved.id)
    assert fetched is not None


def test_qdrant_save_invokes_client_upsert():
    calls: list[dict] = []

    class _MockClient:
        def upsert(self, *, collection_name, points):
            calls.append({"collection_name": collection_name, "points": points})

    store = QdrantEventStore(client=_MockClient(), fallback=MemoryEventStore())
    store.save_event(_make_event("sess", "K"))
    assert len(calls) == 1
    assert calls[0]["collection_name"] == "events"
    assert calls[0]["points"][0]["payload"]["kind"] == "K"


def test_qdrant_client_exception_swallowed(caplog):
    import logging
    caplog.set_level(logging.WARNING)

    class _BrokenClient:
        def upsert(self, **kwargs):
            raise RuntimeError("network down")

    store = QdrantEventStore(client=_BrokenClient(), fallback=MemoryEventStore())
    # Should NOT raise even though the client blew up.
    saved = store.save_event(_make_event("s", "K"))
    assert saved.id


def test_qdrant_ensure_collection_called_once():
    init_counts: list[int] = []

    class _Client:
        def __init__(self):
            self._init = 0

        def ensure_collection(self, *, collection_name):
            self._init += 1
            init_counts.append(self._init)

        def upsert(self, **kwargs):
            pass

    client = _Client()
    store = QdrantEventStore(client=client, fallback=MemoryEventStore())
    store.save_event(_make_event("s", "A"))
    store.save_event(_make_event("s", "B"))
    # Only one ensure_collection call across multiple saves.
    assert init_counts == [1]


# -- factory --


def test_build_event_store_memory():
    store = build_event_store("memory")
    assert isinstance(store, MemoryEventStore)


def test_build_event_store_jsonl(tmp_path: Path):
    store = build_event_store("jsonl", base_dir=tmp_path)
    assert isinstance(store, JsonlEventStore)
    assert store.base_dir == tmp_path


def test_build_event_store_qdrant():
    store = build_event_store("qdrant")
    assert isinstance(store, QdrantEventStore)


def test_build_event_store_unknown_raises():
    with pytest.raises(EventStoreError):
        build_event_store("invalid_backend")


def test_build_event_store_empty_string_defaults_to_memory():
    store = build_event_store("")
    assert isinstance(store, MemoryEventStore)


# -- singleton --


def test_set_and_get_singleton():
    store = MemoryEventStore()
    set_event_store(store)
    assert get_event_store() is store


def test_reset_singleton_clears():
    set_event_store(MemoryEventStore())
    reset_event_store_for_testing()
    assert get_event_store() is None
