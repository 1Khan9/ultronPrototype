"""Tests for the bus -> event store sink."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from kenning.events.bus_sink import (
    BusEventSink,
    get_bus_event_sink,
    install_bus_event_sink,
    uninstall_bus_event_sink,
)
from kenning.events.models import StoredEvent
from kenning.events.store import MemoryEventStore


@pytest.fixture(autouse=True)
def _isolate_sink():
    uninstall_bus_event_sink()
    yield
    uninstall_bus_event_sink()


def _envelope(kind: str, properties: dict, session_id: str | None = None):
    """Build a minimal envelope shape the sink understands."""

    payload = dict(properties)
    if session_id is not None:
        payload["session_id"] = session_id
    return SimpleNamespace(
        event_def=SimpleNamespace(type=kind),
        properties=payload,
    )


def test_sink_install_uninstall_lifecycle():
    store = MemoryEventStore()
    sink = install_bus_event_sink(store)
    assert get_bus_event_sink() is sink
    uninstall_bus_event_sink()
    assert get_bus_event_sink() is None


def test_sink_install_idempotent():
    store = MemoryEventStore()
    first = install_bus_event_sink(store)
    second = install_bus_event_sink(store)
    assert get_bus_event_sink() is second
    assert first is not second  # the second install replaces the first


def test_envelope_to_stored_event_extracts_kind_and_session():
    store = MemoryEventStore()
    sink = BusEventSink(store)
    envelope = _envelope("DemoEvent", {"x": 1}, session_id="sess_a")
    event = sink._envelope_to_stored_event(envelope)
    assert event is not None
    assert event.kind == "DemoEvent"
    assert event.session_id == "sess_a"
    assert event.payload == {"x": 1}
    assert event.source == "bus"


def test_envelope_without_session_id_falls_back():
    store = MemoryEventStore()
    sink = BusEventSink(store, default_session_id="fallback_sess")
    envelope = _envelope("K", {"x": 1})
    event = sink._envelope_to_stored_event(envelope)
    assert event is not None
    assert event.session_id == "fallback_sess"


def test_envelope_class_name_fallback_for_kind():
    class WidgetEvent:
        properties = {"session_id": "s", "a": 1}

    sink = BusEventSink(MemoryEventStore())
    event = sink._envelope_to_stored_event(WidgetEvent())
    assert event is not None
    assert event.kind == "WidgetEvent"


def test_envelope_uses_kind_attribute_when_no_event_def():
    envelope = SimpleNamespace(
        kind="DirectKind",
        properties={"session_id": "s"},
    )
    sink = BusEventSink(MemoryEventStore())
    event = sink._envelope_to_stored_event(envelope)
    assert event is not None
    assert event.kind == "DirectKind"


def test_envelope_strips_session_id_from_payload():
    sink = BusEventSink(MemoryEventStore())
    envelope = _envelope("K", {"session_id": "s", "a": 1, "b": 2})
    event = sink._envelope_to_stored_event(envelope)
    assert event is not None
    assert "session_id" not in event.payload
    assert event.payload == {"a": 1, "b": 2}


def test_envelope_timestamp_extracted():
    sink = BusEventSink(MemoryEventStore())
    envelope = _envelope("K", {"timestamp": 99.0, "session_id": "s"})
    event = sink._envelope_to_stored_event(envelope)
    assert event is not None
    assert event.timestamp == 99.0


def test_envelope_invalid_timestamp_falls_back_to_now():
    sink = BusEventSink(MemoryEventStore())
    envelope = _envelope("K", {"timestamp": "bogus", "session_id": "s"})
    before = time.time() - 0.5
    event = sink._envelope_to_stored_event(envelope)
    after = time.time() + 0.5
    assert event is not None
    assert before <= event.timestamp <= after


def test_sink_dispatches_to_store():
    store = MemoryEventStore()
    sink = BusEventSink(store)
    sink._on_event(_envelope("DemoEvent", {"x": 1}, session_id="sess"))
    sink._on_event(_envelope("DemoEvent", {"x": 2}, session_id="sess"))
    events = store.all_events("sess")
    assert len(events) == 2
    assert sink.dispatched == 2
    assert sink.errors == 0


def test_sink_swallows_store_exceptions(caplog):
    import logging
    caplog.set_level(logging.WARNING)

    class _BrokenStore(MemoryEventStore):
        def save_event(self, event):
            raise RuntimeError("broken")

    sink = BusEventSink(_BrokenStore())
    sink._on_event(_envelope("Demo", {"session_id": "s"}))
    assert sink.errors == 1
    assert sink.dispatched == 0


def test_sink_sequence_counter_increments_per_session():
    store = MemoryEventStore()
    sink = BusEventSink(store)
    sink._on_event(_envelope("K", {"session_id": "a"}))
    sink._on_event(_envelope("K", {"session_id": "a"}))
    sink._on_event(_envelope("K", {"session_id": "b"}))
    sequences_a = [e.sequence for e in store.all_events("a")]
    sequences_b = [e.sequence for e in store.all_events("b")]
    assert sequences_a == [0, 1]
    assert sequences_b == [0]
