"""Tests for the HTTP rate-limit envelope parser + backoff helpers (T14).

Covers:

* :func:`parse_retry_after` for numeric, HTTP-date, and large-epoch
  inputs.
* :func:`parse_rate_limit_headers` for the seven recognised headers
  plus the preferred-fallback order across families.
* :class:`RateLimitState` accessors (is_exhausted, time_to_reset,
  server_supplied_retry).
* :func:`compute_backoff` exponential growth + jitter + server-hint
  override.
* :func:`sleep_for_backoff` injected-sleeper contract.
* :class:`RateLimitTracker` cooldown + 429-counter + skip semantics.
* :func:`get_global_tracker` singleton reset.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from kenning.web_search.rate_limit import (
    BackoffConfig,
    DEFAULT_BACKOFF_CONFIG,
    DEFAULT_BACKOFF_JITTER_SECONDS,
    DEFAULT_MAX_RETRIES,
    RATELIMIT_LIMIT,
    RATELIMIT_REMAINING,
    RATELIMIT_RESET,
    RETRY_AFTER,
    RETRY_AFTER_EPOCH_THRESHOLD_SECONDS,
    RateLimitState,
    RateLimitTracker,
    X_RATELIMIT_LIMIT,
    X_RATELIMIT_REMAINING,
    X_RATELIMIT_RESET,
    compute_backoff,
    get_global_tracker,
    known_header_names,
    parse_rate_limit_headers,
    parse_retry_after,
    reset_global_tracker_for_testing,
    sleep_for_backoff,
)


@pytest.fixture(autouse=True)
def _reset_global_tracker() -> None:
    """Ensure each test starts with a fresh global tracker."""
    reset_global_tracker_for_testing()
    yield
    reset_global_tracker_for_testing()


REFERENCE_NOW = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# parse_retry_after


def test_parse_retry_after_numeric_seconds() -> None:
    assert parse_retry_after("30", now=REFERENCE_NOW) == 30.0


def test_parse_retry_after_zero() -> None:
    assert parse_retry_after("0", now=REFERENCE_NOW) == 0.0


def test_parse_retry_after_negative_returns_none() -> None:
    assert parse_retry_after("-5", now=REFERENCE_NOW) is None


def test_parse_retry_after_empty_returns_none() -> None:
    assert parse_retry_after("", now=REFERENCE_NOW) is None
    assert parse_retry_after("   ", now=REFERENCE_NOW) is None


def test_parse_retry_after_http_date() -> None:
    future = REFERENCE_NOW + timedelta(seconds=60)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    delay = parse_retry_after(http_date, now=REFERENCE_NOW)
    assert delay is not None
    assert 59.0 <= delay <= 61.0


def test_parse_retry_after_past_http_date_returns_zero() -> None:
    past = REFERENCE_NOW - timedelta(seconds=60)
    http_date = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
    delay = parse_retry_after(http_date, now=REFERENCE_NOW)
    assert delay == 0.0


def test_parse_retry_after_large_value_treated_as_epoch() -> None:
    # A value at or above the threshold should be interpreted as
    # absolute Unix epoch.
    epoch = REFERENCE_NOW.timestamp() + 600
    assert epoch > RETRY_AFTER_EPOCH_THRESHOLD_SECONDS
    delay = parse_retry_after(str(int(epoch)), now=REFERENCE_NOW)
    assert delay is not None
    assert 599.0 <= delay <= 601.0


def test_parse_retry_after_garbage_returns_none() -> None:
    assert parse_retry_after("not-a-thing", now=REFERENCE_NOW) is None


# ---------------------------------------------------------------------------
# parse_rate_limit_headers


def test_parse_no_recognised_headers_returns_none() -> None:
    assert parse_rate_limit_headers({"X-Other": "value"}, now=REFERENCE_NOW) is None


def test_parse_legacy_only() -> None:
    headers = {
        X_RATELIMIT_LIMIT: "100",
        X_RATELIMIT_REMAINING: "42",
        X_RATELIMIT_RESET: str(int(REFERENCE_NOW.timestamp() + 60)),
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    assert state.limit == 100
    assert state.remaining == 42
    assert state.reset_at is not None
    delay = state.time_to_reset(now=REFERENCE_NOW)
    assert delay is not None
    assert 59.0 <= delay <= 61.0
    assert X_RATELIMIT_RESET in state.parsed_from


def test_parse_standard_only() -> None:
    headers = {
        RATELIMIT_LIMIT: "200",
        RATELIMIT_REMAINING: "100",
        RATELIMIT_RESET: "45",
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    assert state.limit == 200
    assert state.remaining == 100
    delay = state.time_to_reset(now=REFERENCE_NOW)
    assert delay == 45.0
    assert RATELIMIT_RESET in state.parsed_from


def test_parse_retry_after_wins_over_reset() -> None:
    headers = {
        RATELIMIT_RESET: "100",
        RETRY_AFTER: "10",
        X_RATELIMIT_RESET: str(int(REFERENCE_NOW.timestamp() + 500)),
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    # Retry-After should win; reset_at should reflect ~10s
    delay = state.time_to_reset(now=REFERENCE_NOW)
    assert delay is not None
    assert 9.0 <= delay <= 11.0
    assert state.parsed_from[0] == RETRY_AFTER


def test_parse_standard_wins_over_legacy() -> None:
    headers = {
        RATELIMIT_LIMIT: "999",
        X_RATELIMIT_LIMIT: "1",
        RATELIMIT_REMAINING: "111",
        X_RATELIMIT_REMAINING: "0",
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    assert state.limit == 999
    assert state.remaining == 111


def test_parse_falls_back_to_legacy_reset() -> None:
    # No Retry-After, no RateLimit-Reset; only X-RateLimit-Reset
    headers = {
        X_RATELIMIT_RESET: str(int(REFERENCE_NOW.timestamp() + 30)),
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    delay = state.time_to_reset(now=REFERENCE_NOW)
    assert delay is not None
    assert 29.0 <= delay <= 31.0
    assert state.parsed_from == (X_RATELIMIT_RESET,)


def test_parse_invalid_numeric_falls_through() -> None:
    headers = {
        RATELIMIT_LIMIT: "not-a-number",
        RETRY_AFTER: "20",
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    assert state.limit is None
    assert state.retry_after_seconds == 20.0


def test_parse_case_insensitive_keys() -> None:
    headers = {
        "x-ratelimit-limit": "10",
        "X-RATELIMIT-REMAINING": "5",
        "Retry-After": "7",
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    assert state is not None
    assert state.limit == 10
    assert state.remaining == 5
    assert state.retry_after_seconds == 7.0


def test_known_header_names_returns_seven_canonical() -> None:
    names = list(known_header_names())
    assert len(names) == 7
    assert RETRY_AFTER in names
    assert RATELIMIT_LIMIT in names
    assert X_RATELIMIT_LIMIT in names


# ---------------------------------------------------------------------------
# RateLimitState accessors


def test_is_exhausted_zero_remaining() -> None:
    state = RateLimitState(remaining=0)
    assert state.is_exhausted


def test_is_exhausted_unknown_remaining() -> None:
    state = RateLimitState(remaining=None)
    assert not state.is_exhausted


def test_is_exhausted_positive_remaining() -> None:
    state = RateLimitState(remaining=5)
    assert not state.is_exhausted


def test_server_supplied_retry_prefers_retry_after() -> None:
    state = RateLimitState(
        retry_after_seconds=10.0,
        reset_at=REFERENCE_NOW + timedelta(seconds=100),
        observed_at=REFERENCE_NOW,
    )
    assert state.server_supplied_retry() == 10.0


def test_server_supplied_retry_falls_back_to_reset() -> None:
    state = RateLimitState(
        reset_at=REFERENCE_NOW + timedelta(seconds=42),
        observed_at=REFERENCE_NOW,
    )
    delay = state.server_supplied_retry()
    assert delay is not None
    # time_to_reset is computed against datetime.now(), not the
    # state's observed_at, so we just sanity-check non-None.
    assert delay >= 0.0


def test_server_supplied_retry_none_when_no_hints() -> None:
    assert RateLimitState().server_supplied_retry() is None


def test_time_to_reset_clamped_to_zero_in_past() -> None:
    state = RateLimitState(reset_at=REFERENCE_NOW - timedelta(seconds=10))
    delay = state.time_to_reset(now=REFERENCE_NOW)
    assert delay == 0.0


# ---------------------------------------------------------------------------
# compute_backoff


def test_backoff_uses_server_hint_when_available() -> None:
    state = RateLimitState(retry_after_seconds=5.0)
    # Zero jitter for determinism.
    config = BackoffConfig(
        base_seconds=0.3, cap_seconds=5.0, jitter_seconds=0.0
    )
    delay = compute_backoff(state, attempt=1, config=config)
    assert delay == 5.0


def test_backoff_exponential_without_state() -> None:
    config = BackoffConfig(
        base_seconds=0.3, cap_seconds=5.0, jitter_seconds=0.0
    )
    assert compute_backoff(None, attempt=1, config=config) == pytest.approx(0.3)
    assert compute_backoff(None, attempt=2, config=config) == pytest.approx(0.6)
    assert compute_backoff(None, attempt=3, config=config) == pytest.approx(1.2)
    assert compute_backoff(None, attempt=4, config=config) == pytest.approx(2.4)
    # Cap kicks in.
    assert compute_backoff(None, attempt=10, config=config) == pytest.approx(5.0)


def test_backoff_attempt_below_one_treated_as_one() -> None:
    config = BackoffConfig(
        base_seconds=0.3, cap_seconds=5.0, jitter_seconds=0.0
    )
    assert compute_backoff(None, attempt=0, config=config) == pytest.approx(0.3)
    assert compute_backoff(None, attempt=-5, config=config) == pytest.approx(0.3)


def test_backoff_jitter_within_bounds() -> None:
    rng = random.Random(42)
    config = BackoffConfig(
        base_seconds=0.5, cap_seconds=5.0, jitter_seconds=0.3
    )
    samples = [
        compute_backoff(None, attempt=2, config=config, rng=rng)
        for _ in range(40)
    ]
    for value in samples:
        assert 1.0 <= value <= 1.3  # 1.0 base * 2 = 1.0... actually 0.5 * 2 = 1.0
    # ensure jitter spread is not zero
    assert max(samples) - min(samples) > 0.0


def test_backoff_no_state_no_jitter_deterministic() -> None:
    config = BackoffConfig(
        base_seconds=0.4, cap_seconds=5.0, jitter_seconds=0.0
    )
    assert compute_backoff(None, attempt=2, config=config) == pytest.approx(0.8)


def test_backoff_config_rejects_negative_base() -> None:
    with pytest.raises(ValueError):
        BackoffConfig(base_seconds=-0.1)


def test_backoff_config_rejects_cap_below_base() -> None:
    with pytest.raises(ValueError):
        BackoffConfig(base_seconds=2.0, cap_seconds=1.0)


def test_backoff_config_rejects_negative_jitter() -> None:
    with pytest.raises(ValueError):
        BackoffConfig(jitter_seconds=-0.1)


# ---------------------------------------------------------------------------
# sleep_for_backoff (injected sleeper)


def test_sleep_for_backoff_calls_sleeper_with_computed_delay() -> None:
    sleeps: list[float] = []
    state = RateLimitState(retry_after_seconds=2.0)
    config = BackoffConfig(
        base_seconds=0.3, cap_seconds=5.0, jitter_seconds=0.0
    )
    delay = sleep_for_backoff(
        state, attempt=1, config=config, sleeper=sleeps.append
    )
    assert delay == 2.0
    assert sleeps == [2.0]


def test_sleep_for_backoff_default_sleeper_is_time_sleep(monkeypatch) -> None:
    # Verify the default sleeper path uses time.sleep. We monkeypatch
    # time.sleep so the test runs instantly.
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("time.sleep", fake_sleep)
    config = BackoffConfig(
        base_seconds=0.1, cap_seconds=1.0, jitter_seconds=0.0
    )
    delay = sleep_for_backoff(None, attempt=1, config=config)
    assert delay == pytest.approx(0.1)
    assert sleeps == [pytest.approx(0.1)]


# ---------------------------------------------------------------------------
# RateLimitTracker


def test_tracker_initial_state_no_skip() -> None:
    tracker = RateLimitTracker()
    assert not tracker.should_skip("brave")
    assert tracker.consecutive_429("brave") == 0
    assert tracker.state("brave") is None
    assert tracker.known_providers() == ()


def test_tracker_record_429_sets_cooldown() -> None:
    tracker = RateLimitTracker()
    state = RateLimitState(retry_after_seconds=30.0)
    tracker.record("brave", state, was_429=True, now=REFERENCE_NOW)
    assert tracker.should_skip("brave", now=REFERENCE_NOW)
    # After cooldown elapses, no skip.
    future = REFERENCE_NOW + timedelta(seconds=31)
    assert not tracker.should_skip("brave", now=future)


def test_tracker_record_success_clears_counter() -> None:
    tracker = RateLimitTracker()
    tracker.record(
        "brave",
        RateLimitState(retry_after_seconds=30.0),
        was_429=True,
        now=REFERENCE_NOW,
    )
    tracker.record("brave", RateLimitState(remaining=100), now=REFERENCE_NOW)
    assert not tracker.should_skip("brave", now=REFERENCE_NOW)
    assert tracker.consecutive_429("brave") == 0


def test_tracker_consecutive_429_counter() -> None:
    tracker = RateLimitTracker()
    for _ in range(3):
        tracker.record(
            "brave",
            RateLimitState(retry_after_seconds=1.0),
            was_429=True,
            now=REFERENCE_NOW,
        )
    assert tracker.consecutive_429("brave") == 3


def test_tracker_exhausted_state_implies_skip_until_reset() -> None:
    tracker = RateLimitTracker()
    state = RateLimitState(
        remaining=0,
        reset_at=REFERENCE_NOW + timedelta(seconds=60),
        observed_at=REFERENCE_NOW,
    )
    tracker.record("brave", state, was_429=False, now=REFERENCE_NOW)
    assert tracker.should_skip("brave", now=REFERENCE_NOW)
    after = REFERENCE_NOW + timedelta(seconds=61)
    assert not tracker.should_skip("brave", now=after)


def test_tracker_reset_single_provider() -> None:
    tracker = RateLimitTracker()
    tracker.record(
        "brave",
        RateLimitState(retry_after_seconds=30.0),
        was_429=True,
        now=REFERENCE_NOW,
    )
    tracker.record(
        "ddg",
        RateLimitState(retry_after_seconds=30.0),
        was_429=True,
        now=REFERENCE_NOW,
    )
    tracker.reset("brave")
    assert not tracker.should_skip("brave", now=REFERENCE_NOW)
    assert tracker.should_skip("ddg", now=REFERENCE_NOW)


def test_tracker_reset_all() -> None:
    tracker = RateLimitTracker()
    tracker.record(
        "brave",
        RateLimitState(retry_after_seconds=30.0),
        was_429=True,
        now=REFERENCE_NOW,
    )
    tracker.reset()
    assert not tracker.should_skip("brave", now=REFERENCE_NOW)
    assert tracker.known_providers() == ()


def test_tracker_max_retries_rejects_negative() -> None:
    with pytest.raises(ValueError):
        RateLimitTracker(max_retries=-1)


def test_tracker_default_max_retries() -> None:
    tracker = RateLimitTracker()
    assert tracker.max_retries == DEFAULT_MAX_RETRIES


# ---------------------------------------------------------------------------
# Global tracker singleton


def test_global_tracker_singleton() -> None:
    tracker_a = get_global_tracker()
    tracker_b = get_global_tracker()
    assert tracker_a is tracker_b


def test_global_tracker_reset_for_testing() -> None:
    first = get_global_tracker()
    reset_global_tracker_for_testing()
    second = get_global_tracker()
    assert first is not second


# ---------------------------------------------------------------------------
# Integration: parse + tracker round-trip


def test_integration_parse_and_track_429() -> None:
    tracker = RateLimitTracker()
    headers = {
        X_RATELIMIT_LIMIT: "300",
        X_RATELIMIT_REMAINING: "0",
        RETRY_AFTER: "15",
    }
    state = parse_rate_limit_headers(headers, now=REFERENCE_NOW)
    tracker.record("brave", state, was_429=True, now=REFERENCE_NOW)
    assert tracker.should_skip("brave", now=REFERENCE_NOW)
    assert state is not None
    assert state.is_exhausted
    assert state.retry_after_seconds == 15.0
