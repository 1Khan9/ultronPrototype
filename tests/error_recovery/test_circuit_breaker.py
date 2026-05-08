"""Direct unit tests for the CircuitBreaker primitive.

The Brave-failure tests exercise this through the Brave wrapper; these
test the breaker's behavior in isolation: state transitions, threshold,
window, cooldown, and the contract that it counts only the configured
exception types.
"""

from __future__ import annotations

import time

import pytest

from ultron.resilience import CircuitBreaker, CircuitOpenError, CircuitState


def test_starts_closed():
    cb = CircuitBreaker("test")
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_call_returns_result_when_closed():
    cb = CircuitBreaker("test")
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state == CircuitState.CLOSED


def test_call_propagates_exception_and_counts_failure():
    cb = CircuitBreaker("test", failure_threshold=2)
    def bad():
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        cb.call(bad)
    assert cb.failure_count == 1
    assert cb.state == CircuitState.CLOSED  # below threshold


def test_opens_at_threshold():
    cb = CircuitBreaker("test", failure_threshold=3)
    def bad():
        raise RuntimeError("boom")
    for _ in range(3):
        with pytest.raises(RuntimeError):
            cb.call(bad)
    assert cb.state == CircuitState.OPEN


def test_open_short_circuits():
    cb = CircuitBreaker("test", failure_threshold=2)
    def bad():
        raise RuntimeError("boom")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(bad)

    # While OPEN, calls fail fast with CircuitOpenError WITHOUT invoking func.
    invoked = {"count": 0}
    def victim():
        invoked["count"] += 1
        return "should not run"
    with pytest.raises(CircuitOpenError):
        cb.call(victim)
    assert invoked["count"] == 0


def test_half_open_after_cooldown_then_close_on_success():
    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=0.5)
    def bad():
        raise RuntimeError("boom")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(bad)
    assert cb.state == CircuitState.OPEN

    # Force cooldown elapsed.
    cb._opened_at = time.monotonic() - cb.cooldown_seconds - 1
    assert cb.state == CircuitState.HALF_OPEN

    result = cb.call(lambda: "probe-ok")
    assert result == "probe-ok"
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_half_open_failure_reopens_immediately():
    cb = CircuitBreaker("test", failure_threshold=2, cooldown_seconds=0.5)
    def bad():
        raise RuntimeError("boom")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(bad)

    cb._opened_at = time.monotonic() - cb.cooldown_seconds - 1
    assert cb.state == CircuitState.HALF_OPEN

    with pytest.raises(RuntimeError):
        cb.call(bad)
    assert cb.state == CircuitState.OPEN


def test_only_expected_exceptions_count():
    """Programming bugs (TypeError) shouldn't trip the breaker."""
    cb = CircuitBreaker(
        "test",
        failure_threshold=2,
        expected_exceptions=(ValueError,),
    )
    def type_error():
        raise TypeError("bug, not a dependency failure")
    for _ in range(5):
        with pytest.raises(TypeError):
            cb.call(type_error)
    assert cb.state == CircuitState.CLOSED  # didn't trip
    assert cb.failure_count == 0


def test_reset_returns_to_closed_with_empty_window():
    cb = CircuitBreaker("test", failure_threshold=2)
    def bad():
        raise RuntimeError("boom")
    # Trip the breaker with exactly threshold failures.
    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(bad)
    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


def test_window_evicts_old_failures():
    """Failures outside the rolling window don't count toward threshold."""
    cb = CircuitBreaker("test", failure_threshold=3, window_seconds=0.1)
    def bad():
        raise RuntimeError("boom")
    with pytest.raises(RuntimeError):
        cb.call(bad)
    with pytest.raises(RuntimeError):
        cb.call(bad)
    # Wait past the window.
    time.sleep(0.15)
    # Old failures should be gone now.
    assert cb.failure_count == 0
    # One more failure shouldn't trip (was 2 before window expired; now 1).
    with pytest.raises(RuntimeError):
        cb.call(bad)
    assert cb.state == CircuitState.CLOSED


def test_invalid_construction_raises():
    with pytest.raises(ValueError):
        CircuitBreaker("test", failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker("test", window_seconds=0)
    with pytest.raises(ValueError):
        CircuitBreaker("test", cooldown_seconds=-1)
