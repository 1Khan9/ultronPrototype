"""Tests for :mod:`ultron.utils.health_check` (catalog 11 T4).

All transport is injected via ``get_fn`` -- no real network call is
ever made (binding rule R4). Each branch (healthy, wrong status,
connection error, timeout, malformed body) is exercised with a stub.
"""

from __future__ import annotations

import pytest

from ultron.utils.health_check import (
    CdpHealthResult,
    HealthCheckResult,
    cdp_health_check,
    http_health_check,
)


class _FakeResponse:
    """Minimal ``requests.Response`` stand-in: status_code + json()."""

    def __init__(self, status_code, json_payload=None, json_raises=False):
        self.status_code = status_code
        self._json_payload = json_payload
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("not json")
        return self._json_payload


def _ok_getter(status_code, json_payload=None, json_raises=False):
    """Build a get_fn that returns a fixed fake response."""

    def _get(url, timeout):  # noqa: ARG001
        return _FakeResponse(status_code, json_payload, json_raises)

    return _get


def _raising_getter(exc):
    def _get(url, timeout):  # noqa: ARG001
        raise exc

    return _get


# --- http_health_check ----------------------------------------------------


def test_http_healthy_200():
    result = http_health_check(
        "http://127.0.0.1:8771/healthz", get_fn=_ok_getter(200)
    )
    assert isinstance(result, HealthCheckResult)
    assert result.reachable is True
    assert result.status_code == 200
    assert result.error is None


def test_http_wrong_status_not_reachable():
    result = http_health_check(
        "http://127.0.0.1:8771/healthz", get_fn=_ok_getter(503)
    )
    assert result.reachable is False
    assert result.status_code == 503
    assert "503" in (result.error or "")


def test_http_expected_status_none_accepts_any_2xx():
    for code in (200, 204, 299):
        result = http_health_check(
            "http://x/health", expected_status=None, get_fn=_ok_getter(code)
        )
        assert result.reachable is True, code
    # 3xx is not 2xx -> not reachable
    result = http_health_check(
        "http://x/health", expected_status=None, get_fn=_ok_getter(301)
    )
    assert result.reachable is False


def test_http_connection_error_fails_open():
    result = http_health_check(
        "http://127.0.0.1:9/health",
        get_fn=_raising_getter(ConnectionError("refused")),
    )
    assert result.reachable is False
    assert result.status_code is None
    assert "ConnectionError" in (result.error or "")


def test_http_timeout_fails_open():
    result = http_health_check(
        "http://127.0.0.1:9/health",
        get_fn=_raising_getter(TimeoutError("slow")),
    )
    assert result.reachable is False
    assert "TimeoutError" in (result.error or "")


def test_http_empty_url_rejected():
    result = http_health_check("   ", get_fn=_ok_getter(200))
    assert result.reachable is False
    assert "empty url" in (result.error or "")


def test_http_nonpositive_timeout_rejected():
    result = http_health_check(
        "http://x/health", timeout_s=0, get_fn=_ok_getter(200)
    )
    assert result.reachable is False
    assert "timeout_s" in (result.error or "")


def test_http_response_without_status_code():
    class _NoStatus:
        pass

    def _get(url, timeout):  # noqa: ARG001
        return _NoStatus()

    result = http_health_check("http://x/health", get_fn=_get)
    assert result.reachable is False
    assert "status_code" in (result.error or "")


# --- cdp_health_check -----------------------------------------------------


def test_cdp_healthy_counts_page_tabs():
    payload = [
        {"type": "page", "url": "https://a"},
        {"type": "page", "url": "https://b"},
        {"type": "background_page", "url": "chrome-extension://x"},
        {"type": "service_worker"},
    ]
    result = cdp_health_check(18800, get_fn=_ok_getter(200, payload))
    assert isinstance(result, CdpHealthResult)
    assert result.reachable is True
    assert result.tab_count == 4
    assert result.page_tab_count == 2
    assert result.endpoint == "http://127.0.0.1:18800/json/list"
    assert result.error is None


def test_cdp_non_list_body_not_reachable():
    result = cdp_health_check(18800, get_fn=_ok_getter(200, {"not": "a list"}))
    assert result.reachable is False
    assert "array" in (result.error or "")


def test_cdp_bad_status_not_reachable():
    result = cdp_health_check(18800, get_fn=_ok_getter(403))
    assert result.reachable is False
    assert "403" in (result.error or "")


def test_cdp_malformed_json_fails_open():
    result = cdp_health_check(
        18800, get_fn=_ok_getter(200, json_raises=True)
    )
    assert result.reachable is False
    assert "json parse failed" in (result.error or "")


def test_cdp_connection_error_fails_open():
    result = cdp_health_check(
        18800, get_fn=_raising_getter(ConnectionError("refused"))
    )
    assert result.reachable is False
    assert "ConnectionError" in (result.error or "")


@pytest.mark.parametrize("bad_port", [0, -1, 70000, "9222"])
def test_cdp_invalid_port_rejected(bad_port):
    result = cdp_health_check(bad_port, get_fn=_ok_getter(200, []))
    assert result.reachable is False
    assert "port" in (result.error or "")


def test_cdp_custom_host_in_endpoint():
    result = cdp_health_check(
        9222, host="localhost", get_fn=_ok_getter(200, [])
    )
    assert result.endpoint == "http://localhost:9222/json/list"
    assert result.reachable is True
    assert result.tab_count == 0
