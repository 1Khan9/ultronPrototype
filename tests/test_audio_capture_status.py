"""Tests for AudioCapture's 2026-06-12 status-flag + drop accounting.

The live "Audio status flag: input overflow" warnings were emitted at
most ONCE per process (warn-once latch), hiding recurrence. The fix:
per-session counters, a throttled warning (1st + every Nth), and a
silently-counted queue-full drop path reported from drain().

Hermetic: the callback is driven directly (no stream / device is ever
opened); start() is exercised with a fake InputStream.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest

from ultron.audio.capture import AudioCapture


class _FakeStatus:
    """Truthy sounddevice CallbackFlags stand-in."""

    def __bool__(self) -> bool:
        return True

    def __str__(self) -> str:
        return "input overflow"


def _mk(max_queue_size: int = 4) -> AudioCapture:
    # input_gain_db=0.0 skips the config read; start() is never called
    # so no stream/device is opened.
    return AudioCapture(input_gain_db=0.0, max_queue_size=max_queue_size)


def _block(value: float = 0.0, n: int = 256) -> np.ndarray:
    return np.full((n, 1), value, dtype=np.float32)


def test_status_flag_warns_first_occurrence_only(caplog):
    # Only the FIRST occurrence may log from the audio thread --
    # logging does handler I/O under the process-wide logging lock,
    # which must never recur on the PortAudio callback.
    mic = _mk()
    with caplog.at_level(logging.WARNING, logger="ultron.audio.capture"):
        for _ in range(50):
            mic._callback(_block(), 256, None, _FakeStatus())
    records = [
        r for r in caplog.records if "input overflow" in r.getMessage()
    ]
    assert len(records) == 1
    assert mic.status_flag_count == 50


def test_drain_reports_status_flag_recurrence(caplog):
    mic = _mk()
    for _ in range(7):
        mic._callback(_block(), 256, None, _FakeStatus())
    with caplog.at_level(logging.WARNING, logger="ultron.audio.capture"):
        mic.drain()
        mic.drain()  # second drain: nothing new to report
    records = [
        r for r in caplog.records
        if "status flags recurred" in r.getMessage()
    ]
    assert len(records) == 1
    assert "7 occurrences" in records[0].getMessage()


def test_drain_does_not_report_single_occurrence(caplog):
    # One occurrence already warned inline; drain must stay silent.
    mic = _mk()
    mic._callback(_block(), 256, None, _FakeStatus())
    with caplog.at_level(logging.WARNING, logger="ultron.audio.capture"):
        mic.drain()
    assert not [
        r for r in caplog.records
        if "status flags recurred" in r.getMessage()
    ]


def test_falsy_status_no_warning_no_count(caplog):
    mic = _mk()
    with caplog.at_level(logging.WARNING, logger="ultron.audio.capture"):
        mic._callback(_block(), 256, None, None)
    assert not [
        r for r in caplog.records if "status flag" in r.getMessage().lower()
    ]
    assert mic.status_flag_count == 0


def test_queue_full_drops_oldest_and_counts(caplog):
    mic = _mk(max_queue_size=4)
    with caplog.at_level(logging.DEBUG, logger="ultron.audio.capture"):
        for i in range(6):
            mic._callback(_block(value=float(i)), 256, None, None)
    assert mic.qsize() == 4
    # Oldest two were dropped: the retained chunks are blocks 2..5.
    retained = [mic.get_chunk(timeout=0.1)[0] for _ in range(4)]
    assert retained == [2.0, 3.0, 4.0, 5.0]
    assert mic.dropped_blocks == 2
    # The audio-thread path itself stays silent.
    assert not [
        r for r in caplog.records if "dropped" in r.getMessage()
    ]


def test_drain_reports_drops_once(caplog):
    mic = _mk(max_queue_size=4)
    for i in range(6):
        mic._callback(_block(value=float(i)), 256, None, None)
    with caplog.at_level(logging.DEBUG, logger="ultron.audio.capture"):
        mic.drain()
        mic.drain()  # second drain: nothing new to report
    records = [
        r for r in caplog.records if "dropped 2 oldest blocks" in r.getMessage()
    ]
    assert len(records) == 1
    assert mic.qsize() == 0


def test_start_resets_counters(monkeypatch):
    import ultron.audio.capture as capture_mod

    class _FakeStream:
        def __init__(self, *a, **kw) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(capture_mod.sd, "InputStream", _FakeStream)
    monkeypatch.setattr(
        capture_mod, "resolve_device", lambda configured, kind: 0,
    )
    mic = _mk()
    mic._status_flag_count = 7
    mic._status_reported = 7
    mic._dropped_blocks = 3
    mic._dropped_reported = 3
    mic.start()
    try:
        assert mic.status_flag_count == 0
        assert mic.dropped_blocks == 0
        assert mic._status_reported == 0
        assert mic._dropped_reported == 0
    finally:
        mic.stop()
