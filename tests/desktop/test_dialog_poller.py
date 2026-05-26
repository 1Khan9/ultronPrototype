"""Tests for ultron.desktop.dialog_poller."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

from ultron.bus import reset_bus_for_testing, subscribe
from ultron.bus.events import DialogAppearedEvent, DialogResolvedEvent
from ultron.desktop.dialog_poller import (
    DEFAULT_POLL_INTERVAL_S,
    MAX_TRACKED_DIALOGS,
    DialogPoller,
    get_dialog_poller,
    set_dialog_poller,
)


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeWindow:
    process_name: str = ""
    monitor_index: int = 0


@dataclass
class _FakeDialog:
    hwnd: int
    title: str = "Save As"
    class_name: str = "#32770"
    matched_by: str = "class"
    window: Optional[_FakeWindow] = None


def _fake_dialog(hwnd: int, title: str = "Save As") -> _FakeDialog:
    return _FakeDialog(
        hwnd=hwnd,
        title=title,
        class_name="#32770",
        matched_by="class",
        window=_FakeWindow(process_name="notepad.exe", monitor_index=1),
    )


@pytest.fixture
def fresh_bus(monkeypatch):
    """Reset the bus + recorder around each test."""
    reset_bus_for_testing()
    yield
    reset_bus_for_testing()


# ---------------------------------------------------------------------------
# Singleton + lifecycle
# ---------------------------------------------------------------------------


def test_default_poll_interval_constant():
    assert DEFAULT_POLL_INTERVAL_S == 0.75
    assert MAX_TRACKED_DIALOGS == 64


def test_get_dialog_poller_singleton_caches():
    set_dialog_poller(None)
    try:
        a = get_dialog_poller()
        b = get_dialog_poller()
        assert a is b
    finally:
        set_dialog_poller(None)


def test_set_dialog_poller_swaps():
    set_dialog_poller(None)
    custom = DialogPoller()
    try:
        set_dialog_poller(custom)
        assert get_dialog_poller() is custom
    finally:
        set_dialog_poller(None)


def test_poller_not_running_after_construction():
    p = DialogPoller()
    assert p.running is False
    assert p.tick_count() == 0


def test_start_then_stop_is_clean():
    p = DialogPoller(
        find_dialogs_fn=lambda: [],
        publish_fn=lambda ev, props: None,
        poll_interval_s=0.05,
    )
    p.start()
    try:
        # Give the thread a brief moment to enter its loop.
        for _ in range(20):
            if p.running:
                break
            time.sleep(0.01)
        assert p.running is True
    finally:
        p.stop(wait_s=1.0)
    assert p.running is False


def test_start_is_idempotent():
    p = DialogPoller(
        find_dialogs_fn=lambda: [],
        publish_fn=lambda ev, props: None,
        poll_interval_s=0.05,
    )
    try:
        p.start()
        first_thread = p._thread
        p.start()
        assert p._thread is first_thread
    finally:
        p.stop(wait_s=1.0)


def test_stop_is_idempotent():
    p = DialogPoller(
        find_dialogs_fn=lambda: [],
        publish_fn=lambda ev, props: None,
    )
    p.stop()  # never started -- must not raise
    p.stop()  # double stop -- must not raise


# ---------------------------------------------------------------------------
# Tick-based detection
# ---------------------------------------------------------------------------


def test_appeared_event_fires_on_first_sighting():
    seen = []
    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(101, "Save As")],
        publish_fn=lambda ev, props: seen.append((ev, props)),
    )
    p.tick_once()
    assert len(seen) == 1
    event_def, payload = seen[0]
    assert event_def is DialogAppearedEvent
    assert payload["hwnd"] == 101
    assert payload["title"] == "Save As"
    assert payload["class_name"] == "#32770"
    assert payload["matched_by"] == "class"
    assert payload["process_name"] == "notepad.exe"
    assert payload["monitor_index"] == 1
    assert isinstance(payload["first_seen_at"], float)


def test_appeared_event_does_not_repeat_for_known_hwnd():
    seen = []
    dialogs = [_fake_dialog(101)]
    p = DialogPoller(
        find_dialogs_fn=lambda: dialogs,
        publish_fn=lambda ev, props: seen.append((ev, props)),
    )
    p.tick_once()
    p.tick_once()
    p.tick_once()
    # Only one APPEARED event despite the dialog persisting.
    assert len([e for e in seen if e[0] is DialogAppearedEvent]) == 1


def test_multiple_new_dialogs_announce_separately():
    seen = []
    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(101), _fake_dialog(202, "Open")],
        publish_fn=lambda ev, props: seen.append((ev, props)),
    )
    p.tick_once()
    appeared = [e for e in seen if e[0] is DialogAppearedEvent]
    assert len(appeared) == 2
    hwnds = {p["hwnd"] for _, p in appeared}
    assert hwnds == {101, 202}


def test_resolved_event_fires_when_dialog_disappears():
    seen = []
    # Tick 1: dialog present.
    # Tick 2: dialog gone -> missing_ticks = 1 (under threshold).
    # Tick 3: dialog still gone -> missing_ticks = 2 (== default threshold) -> resolved.
    state = {"calls": 0}

    def _finder():
        state["calls"] += 1
        if state["calls"] == 1:
            return [_fake_dialog(303, "Confirm")]
        return []

    p = DialogPoller(
        find_dialogs_fn=_finder,
        publish_fn=lambda ev, props: seen.append((ev, props)),
        stale_after_ticks=2,
    )
    p.tick_once()  # appeared
    p.tick_once()  # missing 1
    p.tick_once()  # missing 2 -> resolved
    resolved = [e for e in seen if e[0] is DialogResolvedEvent]
    assert len(resolved) == 1
    _, payload = resolved[0]
    assert payload["hwnd"] == 303
    assert payload["resolution"] == "stale"
    assert payload["lifetime_ms"] >= 0


def test_resolved_threshold_is_respected():
    seen = []
    state = {"calls": 0}

    def _finder():
        state["calls"] += 1
        # Present at tick 1, gone tick 2, back at tick 3.
        if state["calls"] in (1, 3):
            return [_fake_dialog(303)]
        return []

    p = DialogPoller(
        find_dialogs_fn=_finder,
        publish_fn=lambda ev, props: seen.append((ev, props)),
        stale_after_ticks=2,
    )
    p.tick_once()  # appeared
    p.tick_once()  # missing 1 (below threshold 2)
    p.tick_once()  # back again -> missing counter resets
    resolved = [e for e in seen if e[0] is DialogResolvedEvent]
    assert len(resolved) == 0
    appeared = [e for e in seen if e[0] is DialogAppearedEvent]
    # Re-appearance during the missing window doesn't fire a duplicate
    # APPEARED -- still treated as the same hwnd.
    assert len(appeared) == 1


def test_explicit_resolution_fires_with_chosen_label():
    seen = []
    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(401)],
        publish_fn=lambda ev, props: seen.append((ev, props)),
    )
    p.tick_once()
    seen.clear()
    ok = p.announce_explicit_resolution(401, "dismissed")
    assert ok is True
    assert len(seen) == 1
    event_def, payload = seen[0]
    assert event_def is DialogResolvedEvent
    assert payload["hwnd"] == 401
    assert payload["resolution"] == "dismissed"


def test_explicit_resolution_returns_false_for_untracked_hwnd():
    p = DialogPoller(
        find_dialogs_fn=lambda: [],
        publish_fn=lambda ev, props: None,
    )
    assert p.announce_explicit_resolution(99999, "dismissed") is False


def test_tracked_hwnds_reflects_state():
    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(11), _fake_dialog(22)],
        publish_fn=lambda ev, props: None,
    )
    p.tick_once()
    assert set(p.tracked_hwnds()) == {11, 22}


def test_tick_count_increments():
    p = DialogPoller(
        find_dialogs_fn=lambda: [],
        publish_fn=lambda ev, props: None,
    )
    p.tick_once()
    p.tick_once()
    p.tick_once()
    assert p.tick_count() == 3


# ---------------------------------------------------------------------------
# Fail-open semantics
# ---------------------------------------------------------------------------


def test_find_dialogs_exception_is_swallowed():
    def _boom():
        raise RuntimeError("uia layer gone")

    seen = []
    p = DialogPoller(
        find_dialogs_fn=_boom,
        publish_fn=lambda ev, props: seen.append(("e", props)),
    )
    # Must not raise.
    p.tick_once()
    p.tick_once()
    # No publish should have fired (no dialogs found).
    assert seen == []


def test_publish_exception_is_swallowed():
    def _boom(ev, props):
        raise RuntimeError("subscriber went haywire")

    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(501)],
        publish_fn=_boom,
    )
    # Must not raise even though the publish hook explodes.
    p.tick_once()


def test_malformed_dialog_entries_are_skipped():
    class _Broken:
        def __getattr__(self, name):
            raise RuntimeError(f"attr {name} broken")

    seen = []
    p = DialogPoller(
        find_dialogs_fn=lambda: [_Broken(), _fake_dialog(601)],
        publish_fn=lambda ev, props: seen.append(("e", props)),
    )
    p.tick_once()
    # Only the good entry produces an event.
    assert len(seen) == 1
    assert seen[0][1]["hwnd"] == 601


def test_zero_hwnd_skipped():
    seen = []
    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(0, "ghost")],
        publish_fn=lambda ev, props: seen.append(("e", props)),
    )
    p.tick_once()
    assert seen == []


# ---------------------------------------------------------------------------
# Bounded memory
# ---------------------------------------------------------------------------


def test_tracked_dialogs_are_capped():
    state = {"calls": 0}

    def _finder():
        state["calls"] += 1
        # Each tick presents a fresh hwnd so the tracker grows.
        return [_fake_dialog(1000 + state["calls"])]

    p = DialogPoller(
        find_dialogs_fn=_finder,
        publish_fn=lambda ev, props: None,
        # Don't resolve them via the absent-tick path -- we want all
        # entries to stick so the cap fires.
        stale_after_ticks=10_000,
    )
    for _ in range(MAX_TRACKED_DIALOGS + 5):
        p.tick_once()
    # Cap is enforced by oldest-out.
    assert len(p.tracked_hwnds()) <= MAX_TRACKED_DIALOGS


# ---------------------------------------------------------------------------
# Bus integration end-to-end
# ---------------------------------------------------------------------------


def test_default_publish_goes_through_real_bus(fresh_bus):
    """When no publish_fn is injected, events flow through the real bus."""
    seen_appeared = []
    unsub = subscribe(
        DialogAppearedEvent,
        lambda payload: seen_appeared.append(payload),
    )
    try:
        p = DialogPoller(
            find_dialogs_fn=lambda: [_fake_dialog(701)],
        )
        p.tick_once()
        assert len(seen_appeared) == 1
        envelope = seen_appeared[0]
        # EventPayload.properties carries the dict we published.
        props = envelope.properties
        assert props["hwnd"] == 701
        assert props["title"] == "Save As"
    finally:
        unsub()


def test_default_publish_resolved_through_real_bus(fresh_bus):
    seen_resolved = []
    unsub = subscribe(
        DialogResolvedEvent,
        lambda payload: seen_resolved.append(payload),
    )
    try:
        state = {"calls": 0}

        def _finder():
            state["calls"] += 1
            return [_fake_dialog(801)] if state["calls"] == 1 else []

        p = DialogPoller(
            find_dialogs_fn=_finder,
            stale_after_ticks=2,
        )
        p.tick_once()  # appeared
        p.tick_once()  # missing 1
        p.tick_once()  # missing 2 -> resolved
        assert len(seen_resolved) == 1
        props = seen_resolved[0].properties
        assert props["hwnd"] == 801
        assert props["resolution"] == "stale"
    finally:
        unsub()


# ---------------------------------------------------------------------------
# Daemon-thread integration
# ---------------------------------------------------------------------------


def test_daemon_thread_publishes_appeared_event():
    """The poller's daemon thread fires events without manual ticks."""
    seen = []
    seen_lock = threading.Lock()
    seen_event = threading.Event()

    def _publish(ev, props):
        with seen_lock:
            seen.append((ev, props))
        seen_event.set()

    p = DialogPoller(
        find_dialogs_fn=lambda: [_fake_dialog(901)],
        publish_fn=_publish,
        poll_interval_s=0.05,
    )
    p.start()
    try:
        assert seen_event.wait(timeout=2.0), "appeared event never fired"
    finally:
        p.stop(wait_s=1.0)
    assert len(seen) >= 1
    assert seen[0][1]["hwnd"] == 901
