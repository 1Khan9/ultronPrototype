"""Brave API failure modes: timeout / 5xx / 429 / malformed JSON, plus
circuit breaker open + reset semantics.

Validates: system doesn't crash; failures log to errors.jsonl with the
right shape; subsequent calls continue normally; the circuit breaker
trips after threshold and short-circuits while OPEN; HALF_OPEN probe
+ success closes the breaker again.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
import requests

from ultron.resilience import CircuitOpenError, CircuitState
from ultron.web_search.brave import BraveSearchClient
from ultron.web_search import brave as brave_mod


def _make_client():
    """Constructed with a dummy API key so the constructor doesn't reject us."""
    return BraveSearchClient(
        api_key="test-key",
        rate_limit_s=0.0,
        timeout_s=1.0,
        endpoint="http://invalid.example/",
    )


# ---------------------------------------------------------------------------
# Single-call failure modes
# ---------------------------------------------------------------------------


@patch("requests.get")
def test_brave_timeout_logs_and_returns_empty(mock_get, errors_log, read_errors):
    mock_get.side_effect = requests.exceptions.Timeout("simulated timeout")

    client = _make_client()
    out = client.search("anything")

    assert out == []
    records = read_errors()
    assert len(records) == 1
    rec = records[0]
    assert rec["dependency"] == "brave_api"
    assert rec["error_type"] == "BraveAPIError"
    assert "timed out" in rec["message"]
    assert rec["context"]["query"] == "anything"
    assert "falls back" in rec["recovery"]


@patch("requests.get")
def test_brave_5xx_logs_and_returns_empty(mock_get, errors_log, read_errors):
    resp = MagicMock()
    resp.status_code = 503
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    mock_get.return_value = resp

    out = _make_client().search("foo")

    assert out == []
    records = read_errors()
    assert len(records) == 1
    assert records[0]["error_type"] == "BraveAPIError"
    assert records[0]["context"]["status_code"] == 503


@patch("requests.get")
def test_brave_rate_limit_429_logs_and_returns_empty(
    mock_get, errors_log, read_errors,
):
    resp = MagicMock()
    resp.status_code = 429
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    mock_get.return_value = resp

    out = _make_client().search("rate-limited query")
    assert out == []
    records = read_errors()
    assert records[0]["context"]["status_code"] == 429


@patch("requests.get")
def test_brave_malformed_json_logs_and_returns_empty(
    mock_get, errors_log, read_errors,
):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not JSON")
    mock_get.return_value = resp

    out = _make_client().search("malformed")
    assert out == []
    records = read_errors()
    assert "malformed JSON" in records[0]["message"]


@patch("requests.get")
def test_brave_subsequent_call_works_after_failure(
    mock_get, errors_log, read_errors,
):
    """One failure does not poison subsequent calls (until threshold)."""
    # First call fails with timeout
    mock_get.side_effect = [
        requests.exceptions.Timeout("first"),
        # Second call succeeds with valid response
        _ok_response([{"url": "http://a", "title": "A", "description": "snippet"}]),
    ]

    client = _make_client()
    assert client.search("first") == []
    out = client.search("second")
    assert len(out) == 1
    assert out[0].url == "http://a"


def _ok_response(rows):
    """Build a MagicMock that mimics a successful Brave response."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"web": {"results": rows}}
    return resp


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


@patch("requests.get")
def test_brave_circuit_opens_after_threshold(mock_get, errors_log, read_errors):
    """Three failures in a row trip the breaker; subsequent calls
    short-circuit with CircuitOpenError, log a circuit-open record, and
    return [] without invoking the underlying request."""
    mock_get.side_effect = requests.exceptions.Timeout("repeated")

    client = _make_client()
    breaker = brave_mod._BRAVE_BREAKER

    # Threshold is 3 (set in brave.py); fire 3 failures.
    for i in range(3):
        assert client.search(f"q{i}") == []

    assert breaker.state == CircuitState.OPEN

    # Next call should short-circuit; mock should NOT be called again.
    pre_call_count = mock_get.call_count
    out = client.search("post-trip")
    assert out == []
    assert mock_get.call_count == pre_call_count, (
        "circuit was open but requests.get was still invoked"
    )

    # Last record should be the circuit-open log entry.
    records = read_errors()
    last = records[-1]
    assert "circuit open" in last["message"]
    assert "short-circuited" in last["recovery"]


def test_brave_circuit_half_open_then_closes_on_success(
    errors_log, read_errors,
):
    """After cooldown the breaker enters HALF_OPEN; a successful probe
    closes it back to CLOSED with empty failure window."""
    breaker = brave_mod._BRAVE_BREAKER
    breaker.reset()

    # Synthetic OPEN state: trip via direct API
    for _ in range(breaker.failure_threshold):
        breaker._record_failure()
    assert breaker.state == CircuitState.OPEN

    # Force cooldown elapsed by mutating internal timestamp.
    import time
    breaker._opened_at = time.monotonic() - breaker.cooldown_seconds - 1
    assert breaker.state == CircuitState.HALF_OPEN

    # Probe: a no-op call that succeeds.
    result = breaker.call(lambda: "probe-ok")
    assert result == "probe-ok"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


def test_brave_circuit_half_open_failure_reopens(errors_log):
    """If the HALF_OPEN probe fails, the breaker reopens immediately
    (does not require another threshold worth of failures)."""
    breaker = brave_mod._BRAVE_BREAKER
    breaker.reset()
    for _ in range(breaker.failure_threshold):
        breaker._record_failure()

    import time
    breaker._opened_at = time.monotonic() - breaker.cooldown_seconds - 1
    assert breaker.state == CircuitState.HALF_OPEN

    from ultron.errors import BraveAPIError

    def _failing():
        raise BraveAPIError("probe failure")

    with pytest.raises(BraveAPIError):
        breaker.call(_failing)
    assert breaker.state == CircuitState.OPEN
