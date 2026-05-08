"""Jina Reader failure modes: timeout / 4xx / 5xx / generic request error.

Validates fetch returns None on failure, errors.jsonl receives a JinaReaderError,
recovery is recorded as "snippet-only fallback".
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import requests

from ultron.web_search.jina import JinaReaderClient


def _client():
    return JinaReaderClient(
        endpoint="http://invalid.example/",
        timeout_s=1.0,
        max_bytes=10000,
    )


@patch("requests.get")
def test_jina_timeout_logs_and_returns_none(mock_get, errors_log, read_errors):
    mock_get.side_effect = requests.exceptions.Timeout("simulated")
    out = _client().fetch("http://example.com/page")
    assert out is None
    records = read_errors()
    assert len(records) == 1
    rec = records[0]
    assert rec["dependency"] == "jina"
    assert rec["error_type"] == "JinaReaderError"
    assert "timed out" in rec["message"]
    assert "snippet-only" in rec["recovery"]


@patch("requests.get")
def test_jina_404_logs_and_returns_none(mock_get, errors_log, read_errors):
    resp = MagicMock()
    resp.status_code = 404
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    mock_get.return_value = resp

    out = _client().fetch("http://example.com/missing")
    assert out is None
    records = read_errors()
    assert records[0]["context"]["status_code"] == 404


@patch("requests.get")
def test_jina_5xx_logs_and_returns_none(mock_get, errors_log, read_errors):
    resp = MagicMock()
    resp.status_code = 502
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=resp)
    mock_get.return_value = resp

    out = _client().fetch("http://example.com/page")
    assert out is None
    records = read_errors()
    assert records[0]["context"]["status_code"] == 502


@patch("requests.get")
def test_jina_request_exception_logs_and_returns_none(
    mock_get, errors_log, read_errors,
):
    mock_get.side_effect = requests.exceptions.ConnectionError("DNS fail")
    out = _client().fetch("http://example.com/page")
    assert out is None
    records = read_errors()
    assert records[0]["error_type"] == "JinaReaderError"


@patch("requests.get")
def test_jina_subsequent_call_works_after_failure(
    mock_get, errors_log, read_errors,
):
    """One Jina failure does not disable subsequent calls (until threshold)."""
    ok = MagicMock()
    ok.raise_for_status.return_value = None
    ok.text = "# clean markdown\n\nbody."

    mock_get.side_effect = [
        requests.exceptions.Timeout("first"),
        ok,
    ]
    client = _client()
    assert client.fetch("http://example.com/a") is None
    assert client.fetch("http://example.com/b") == "# clean markdown\n\nbody."
