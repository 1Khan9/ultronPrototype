"""Tests for :mod:`ultron.utils.heartbeat` (catalog 11 T2).

Hermetic + deterministic: targets signal a :class:`threading.Event` so
the test waits on the actual beat rather than sleeping a guessed
duration (binding rule R12). Every :class:`HeartbeatThread` is stopped
in a ``finally`` so no daemon thread leaks past the test (binding rule
R2).
"""

from __future__ import annotations

import threading

import pytest

from ultron.utils.heartbeat import (
    DEFAULT_HEARTBEAT_INTERVAL_S,
    HeartbeatStats,
    HeartbeatThread,
)

# Short interval so the beat-per-interval loop fires quickly. Well under
# the 0.5 s bare-sleep ceiling; we still synchronise on an Event rather
# than asserting on wall-clock time.
_FAST_INTERVAL = 0.01
# Generous bound for "the worker should have done X by now" waits. A
# failure here means the worker never ran, not that it was slow.
_WAIT_TIMEOUT = 2.0


def test_invalid_interval_rejected():
    with pytest.raises(ValueError):
        HeartbeatThread(lambda: None, interval_s=0)
    with pytest.raises(ValueError):
        HeartbeatThread(lambda: None, interval_s=-1.0)


def test_default_interval_matches_upstream():
    # The upstream CDP keep-alive is 60 s; the generalised default
    # preserves it.
    assert DEFAULT_HEARTBEAT_INTERVAL_S == 60.0


def test_beats_fire_then_stop_cleanly():
    fired = threading.Event()
    calls = {"n": 0}

    def target():
        calls["n"] += 1
        fired.set()

    hb = HeartbeatThread(target, interval_s=_FAST_INTERVAL, name="test-hb")
    try:
        hb.start()
        assert fired.wait(_WAIT_TIMEOUT), "heartbeat target never fired"
        assert hb.is_alive()
    finally:
        hb.stop(timeout=_WAIT_TIMEOUT)
    assert not hb.is_alive()
    # At least one beat landed; counter is non-zero.
    assert calls["n"] >= 1
    assert hb.stats().beats_sent >= 1


def test_run_immediately_beats_before_first_interval():
    fired = threading.Event()
    # A deliberately long interval: if the immediate beat did NOT fire,
    # the test would time out waiting because the first interval-based
    # beat would be 30 s away.
    hb = HeartbeatThread(
        lambda: fired.set(),
        interval_s=30.0,
        run_immediately=True,
        name="test-immediate",
    )
    try:
        hb.start()
        assert fired.wait(_WAIT_TIMEOUT), "immediate beat did not fire"
    finally:
        hb.stop(timeout=_WAIT_TIMEOUT)


def test_target_exception_is_swallowed_and_counted():
    seen = threading.Event()
    captured: list[BaseException] = []

    def boom():
        captured.append(RuntimeError("kaboom"))
        seen.set()
        raise RuntimeError("kaboom")

    errors_seen: list[BaseException] = []
    hb = HeartbeatThread(
        boom,
        interval_s=_FAST_INTERVAL,
        on_error=errors_seen.append,
        name="test-boom",
    )
    try:
        hb.start()
        assert seen.wait(_WAIT_TIMEOUT)
        # Give the loop a moment to record the error + invoke on_error
        # by waiting for the stats to reflect it.
        _wait_until(lambda: hb.stats().errors >= 1, _WAIT_TIMEOUT)
    finally:
        hb.stop(timeout=_WAIT_TIMEOUT)
    stats = hb.stats()
    assert stats.errors >= 1
    assert "kaboom" in stats.last_error
    assert errors_seen, "on_error callback never fired"
    # The worker survived the exception (it kept running until stop).
    assert not hb.is_alive()


def test_on_error_exception_does_not_break_loop():
    beats = threading.Event()
    count = {"target": 0}

    def target():
        count["target"] += 1
        if count["target"] >= 2:
            beats.set()
        raise ValueError("target fails")

    def broken_handler(_exc: BaseException) -> None:
        raise RuntimeError("handler also fails")

    hb = HeartbeatThread(
        target,
        interval_s=_FAST_INTERVAL,
        on_error=broken_handler,
        name="test-broken-handler",
    )
    try:
        hb.start()
        # The loop must survive BOTH the target raising AND the on_error
        # handler raising -- it should keep beating (>=2 target calls).
        assert beats.wait(_WAIT_TIMEOUT), "loop died after handler raised"
    finally:
        hb.stop(timeout=_WAIT_TIMEOUT)
    assert hb.stats().errors >= 2


def test_stop_is_idempotent_and_safe_when_never_started():
    hb = HeartbeatThread(lambda: None, interval_s=_FAST_INTERVAL)
    # Never started -> stop must not raise.
    hb.stop(timeout=0.1)
    assert not hb.is_alive()
    # Double-stop is a no-op.
    hb.stop(timeout=0.1)
    assert not hb.is_alive()


def test_start_is_idempotent_while_running():
    fired = threading.Event()
    hb = HeartbeatThread(
        lambda: fired.set(), interval_s=_FAST_INTERVAL, name="test-double-start"
    )
    try:
        hb.start()
        assert fired.wait(_WAIT_TIMEOUT)
        # Second start while alive is a no-op (does not spawn a 2nd
        # thread); the active-thread count for this name stays 1.
        hb.start()
        live = [t for t in threading.enumerate() if t.name == "test-double-start"]
        assert len(live) == 1
    finally:
        hb.stop(timeout=_WAIT_TIMEOUT)


def test_restart_after_stop():
    fired1 = threading.Event()
    fired2 = threading.Event()
    state = {"event": fired1}

    def target():
        state["event"].set()

    hb = HeartbeatThread(target, interval_s=_FAST_INTERVAL, name="test-restart")
    try:
        hb.start()
        assert fired1.wait(_WAIT_TIMEOUT)
        hb.stop(timeout=_WAIT_TIMEOUT)
        assert not hb.is_alive()
        # Resume: a fresh worker should spawn and beat again.
        state["event"] = fired2
        hb.start()
        assert fired2.wait(_WAIT_TIMEOUT), "heartbeat did not resume after stop"
    finally:
        hb.stop(timeout=_WAIT_TIMEOUT)


def test_stats_shape_before_start():
    hb = HeartbeatThread(lambda: None, interval_s=_FAST_INTERVAL)
    stats = hb.stats()
    assert isinstance(stats, HeartbeatStats)
    assert stats.running is False
    assert stats.beats_sent == 0
    assert stats.errors == 0
    assert stats.last_error == ""
    assert stats.started_at == 0.0


def _wait_until(predicate, timeout: float) -> None:
    """Poll ``predicate`` via short Event waits until True or timeout.

    Uses a private :class:`threading.Event` wait (never a bare
    ``time.sleep``) so the binding R12 rule holds even in the helper.
    """
    deadline_evt = threading.Event()
    waited = 0.0
    step = 0.01
    while waited < timeout:
        if predicate():
            return
        deadline_evt.wait(step)
        waited += step
    # One last check so a predicate that became true on the final tick
    # is not reported as a timeout.
    assert predicate(), "condition not met within timeout"
