"""Tests for the event-store value types."""

from __future__ import annotations

import pytest

from ultron.events.models import (
    DEFAULT_PAGE_LIMIT,
    DEFAULT_SEARCH_SORT,
    EventKind,
    EventPage,
    EventQuery,
    EventSortOrder,
    StoredEvent,
    canonical_event_json,
    kinds_in,
    new_event_id,
)


def test_new_event_id_is_unique():
    ids = {new_event_id() for _ in range(64)}
    assert len(ids) == 64
    # UUID4 hex is 32 lowercase chars.
    assert all(len(i) == 32 for i in ids)


def test_stored_event_make_defaults():
    event = StoredEvent.make("sess", EventKind.TURN_STARTED)
    assert event.session_id == "sess"
    assert event.kind == EventKind.TURN_STARTED
    assert event.payload == {}
    assert event.chain_hash is None
    assert event.chain_prev_hash is None
    assert event.sequence == 0
    assert event.source is None
    assert isinstance(event.timestamp, float)
    assert event.timestamp > 0


def test_stored_event_with_chain_hashes_returns_copy():
    event = StoredEvent.make("s", "K")
    stamped = event.with_chain_hashes(prev_hash="aa", chain_hash="bb")
    # Originals untouched.
    assert event.chain_prev_hash is None
    assert event.chain_hash is None
    # Stamped copy carries the new values.
    assert stamped.chain_prev_hash == "aa"
    assert stamped.chain_hash == "bb"
    assert stamped.id == event.id


def test_stored_event_round_trip():
    event = StoredEvent.make(
        "sess",
        "TestKind",
        payload={"a": 1, "b": [1, 2, 3]},
        source="bus",
        extra={"trace": "1234"},
        sequence=7,
    )
    stamped = event.with_chain_hashes(prev_hash="prev", chain_hash="chash")
    rebuilt = StoredEvent.from_dict(stamped.to_dict())
    assert rebuilt == stamped


def test_stored_event_from_dict_tolerates_missing_optionals():
    rebuilt = StoredEvent.from_dict(
        {
            "id": "abc",
            "session_id": "s",
            "kind": "K",
            "timestamp": 1.0,
        }
    )
    assert rebuilt.payload == {}
    assert rebuilt.source is None
    assert rebuilt.chain_prev_hash is None
    assert rebuilt.chain_hash is None
    assert rebuilt.sequence == 0
    assert rebuilt.extra == {}


def test_stored_event_is_frozen():
    event = StoredEvent.make("s", "K")
    with pytest.raises(Exception):
        event.kind = "Other"  # type: ignore[misc]


def test_canonical_event_json_is_stable():
    event = StoredEvent(
        id="abc",
        session_id="sess",
        kind="K",
        timestamp=1.234567,
        payload={"b": 2, "a": 1},
        source="bus",
        sequence=3,
        extra={"k": "v"},
    )
    one = canonical_event_json(event)
    two = canonical_event_json(event)
    assert one == two
    # Sorted keys means {"a": 1, "b": 2} not {"b": 2, "a": 1}.
    assert one.index("\"a\":") < one.index("\"b\":")


def test_canonical_event_json_excludes_chain_hash():
    a = StoredEvent.make("s", "K", payload={"x": 1})
    b = a.with_chain_hashes(prev_hash="p", chain_hash="hash")
    # The canonical encoding ignores chain_hash so flipping it
    # doesn't perturb the hash input.
    assert canonical_event_json(a) == canonical_event_json(b)


def test_canonical_event_json_rounds_timestamp():
    event = StoredEvent(
        id="i",
        session_id="s",
        kind="K",
        timestamp=1.1234567890123456789,
        payload={},
    )
    encoded = canonical_event_json(event)
    # Should round to 6 decimal places (microsecond-ish stability).
    assert "1.123457" in encoded


def test_default_search_constants():
    assert DEFAULT_PAGE_LIMIT == 100
    assert DEFAULT_SEARCH_SORT == EventSortOrder.TIMESTAMP


def test_event_page_holds_immutable_tuple():
    page = EventPage(items=(), next_page_token=None, total_estimated=0)
    with pytest.raises(Exception):
        page.items = (1, 2, 3)  # type: ignore[misc]


def test_event_query_with_overrides_returns_copy():
    query = EventQuery(session_id="s")
    new = query.with_overrides(kind="K", limit=10)
    assert query.kind is None
    assert new.kind == "K"
    assert new.limit == 10
    assert new.session_id == "s"


def test_event_kind_namespace_has_canonical_strings():
    assert EventKind.TURN_STARTED == "TurnStarted"
    assert EventKind.SAFETY_VIOLATED == "SafetyViolated"
    assert EventKind.GAMING_ENGAGED == "GamingEngaged"


def test_kinds_in_returns_sorted_unique():
    events = [
        StoredEvent.make("s", "Beta"),
        StoredEvent.make("s", "Alpha"),
        StoredEvent.make("s", "Beta"),
    ]
    assert kinds_in(events) == ["Alpha", "Beta"]
