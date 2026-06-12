"""Lightweight HTTP / CDP health-check pre-flight.

Catalog 11 (clawhub-browser-agent) T4 -- generic clean-room
re-implementation.

The upstream plugin confirms Chrome is alive before opening an
(expensive) CDP WebSocket by issuing a cheap ``GET /json/list`` to the
DevTools HTTP endpoint -- a ~5 ms round-trip that returns the open-tab
list and distinguishes "Chrome isn't listening" from "Chrome is up but
the page errored". This module generalises that into two fail-open
primitives:

* :func:`http_health_check` -- a generic "is this local HTTP endpoint
  answering?" probe used as a pre-flight before any expensive operation
  that depends on a local service (the Parakeet STT server, the
  OpenClaw bridge, a SearxNG container, a future direct-CDP path). Far
  cheaper than spawning a subprocess or opening a socket only to time
  out.
* :func:`cdp_health_check` -- the Chrome-DevTools-specific variant that
  hits ``/json/list`` and reports how many tabs (and how many
  ``type=="page"`` tabs) are open. Used only on the
  attach-to-existing-Chrome path (``connect`` / ``connect_profile``);
  the headless ``browser-use`` daemon has no fixed CDP port to probe.

Both are **fail-open**: any failure (connection refused, timeout, bad
status, non-JSON body) returns a result with ``reachable=False`` and a
populated ``error`` -- they NEVER raise. The transport is injectable
(``get_fn``) so tests exercise every branch without a real network call
(test-sweep binding rule R4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ultron.utils.logging import get_logger

logger = get_logger("utils.health_check")


# Default probe timeout. A health check that takes longer than this is
# itself a signal the service is unhealthy; keep it short so the probe
# stays cheap relative to the operation it guards.
DEFAULT_HEALTH_CHECK_TIMEOUT_S: float = 2.0

# Default Chrome DevTools host. CDP debug endpoints only ever listen on
# loopback in ultron's model (exposing CDP to a routable interface is a
# security hazard the catalog + the upstream docs both warn against).
DEFAULT_CDP_HOST: str = "127.0.0.1"


# A minimal structural contract for the object ``get_fn`` returns: a
# ``status_code`` int and a ``json()`` method. ``requests.Response``
# satisfies it; tests provide a tiny stand-in.
ResponseLike = Any
GetFn = Callable[[str, float], ResponseLike]


@dataclass(frozen=True)
class HealthCheckResult:
    """Outcome of an :func:`http_health_check`.

    Attributes:
        reachable: True iff the endpoint answered with the expected
            status within the timeout.
        url: the probed URL (echoed for the audit / dashboard).
        status_code: the HTTP status, or ``None`` when the request
            never completed (connection refused / timeout).
        elapsed_ms: wall-clock duration of the probe.
        error: short failure reason, or ``None`` on success.
    """

    reachable: bool
    url: str
    status_code: Optional[int] = None
    elapsed_ms: float = 0.0
    error: Optional[str] = None


@dataclass(frozen=True)
class CdpHealthResult:
    """Outcome of a :func:`cdp_health_check`.

    Attributes:
        reachable: True iff ``/json/list`` answered 200 with a JSON
            array body.
        endpoint: the probed ``/json/list`` URL.
        tab_count: total targets the endpoint reported.
        page_tab_count: subset whose ``type`` is ``"page"`` (the
            attachable browser tabs).
        elapsed_ms: wall-clock duration of the probe.
        error: short failure reason, or ``None`` on success.
    """

    reachable: bool
    endpoint: str
    tab_count: int = 0
    page_tab_count: int = 0
    elapsed_ms: float = 0.0
    error: Optional[str] = None


def _default_get(url: str, timeout: float) -> ResponseLike:
    """Default transport: a lazy ``requests.get``.

    Lazy-imported so importing this module never hard-requires
    ``requests`` (it is a core dep, but the lazy import keeps the
    fail-open contract clean if the environment is ever stripped down).
    """
    import requests  # local import: keep module import side-effect free

    return requests.get(url, timeout=timeout)


def http_health_check(
    url: str,
    *,
    timeout_s: float = DEFAULT_HEALTH_CHECK_TIMEOUT_S,
    expected_status: Optional[int] = 200,
    get_fn: Optional[GetFn] = None,
) -> HealthCheckResult:
    """Probe ``url`` with a cheap GET and report reachability.

    Args:
        url: the endpoint to probe (e.g. ``http://127.0.0.1:8771/healthz``).
        timeout_s: per-request timeout. Must be positive.
        expected_status: the status that counts as healthy. ``200`` by
            default; pass ``None`` to accept any 2xx response.
        get_fn: injectable transport ``(url, timeout) -> response``.
            Defaults to :func:`_default_get` (``requests.get``). Tests
            inject a stub so no real network call happens.

    Returns:
        :class:`HealthCheckResult`. Never raises -- any failure is
        reported via ``reachable=False`` + ``error``.
    """
    url = (url or "").strip()
    if not url:
        return HealthCheckResult(
            reachable=False, url=url, error="empty url"
        )
    if timeout_s <= 0:
        return HealthCheckResult(
            reachable=False,
            url=url,
            error=f"timeout_s must be positive, got {timeout_s!r}",
        )
    fn = get_fn if get_fn is not None else _default_get
    start = time.monotonic()
    try:
        response = fn(url, timeout_s)
    except Exception as exc:  # noqa: BLE001 -- fail-open probe never raises
        elapsed = (time.monotonic() - start) * 1000.0
        logger.debug("http_health_check(%s) failed: %s", url, exc)
        return HealthCheckResult(
            reachable=False,
            url=url,
            elapsed_ms=elapsed,
            error=f"{type(exc).__name__}: {exc}",
        )
    elapsed = (time.monotonic() - start) * 1000.0
    status = getattr(response, "status_code", None)
    if not isinstance(status, int):
        return HealthCheckResult(
            reachable=False,
            url=url,
            status_code=None,
            elapsed_ms=elapsed,
            error="response had no integer status_code",
        )
    if expected_status is None:
        healthy = 200 <= status < 300
    else:
        healthy = status == expected_status
    return HealthCheckResult(
        reachable=healthy,
        url=url,
        status_code=status,
        elapsed_ms=elapsed,
        error=None if healthy else f"unexpected status {status}",
    )


def cdp_health_check(
    port: int,
    *,
    host: str = DEFAULT_CDP_HOST,
    timeout_s: float = DEFAULT_HEALTH_CHECK_TIMEOUT_S,
    get_fn: Optional[GetFn] = None,
) -> CdpHealthResult:
    """Probe a Chrome DevTools ``/json/list`` endpoint.

    Confirms Chrome is alive on ``host:port`` and reports the open-tab
    counts WITHOUT opening a WebSocket -- the cheap pre-flight before an
    expensive ``connect`` / ``connect_profile`` attach.

    Args:
        port: the CDP remote-debugging port.
        host: bind host. Defaults to loopback; callers should not point
            this at a routable interface.
        timeout_s: per-request timeout.
        get_fn: injectable transport (see :func:`http_health_check`).

    Returns:
        :class:`CdpHealthResult`. Never raises.
    """
    if not isinstance(port, int) or port <= 0 or port > 65535:
        return CdpHealthResult(
            reachable=False,
            endpoint="",
            error=f"port must be in 1..65535, got {port!r}",
        )
    endpoint = f"http://{host}:{port}/json/list"
    if timeout_s <= 0:
        return CdpHealthResult(
            reachable=False,
            endpoint=endpoint,
            error=f"timeout_s must be positive, got {timeout_s!r}",
        )
    fn = get_fn if get_fn is not None else _default_get
    start = time.monotonic()
    try:
        response = fn(endpoint, timeout_s)
    except Exception as exc:  # noqa: BLE001 -- fail-open
        elapsed = (time.monotonic() - start) * 1000.0
        logger.debug("cdp_health_check(%s) failed: %s", endpoint, exc)
        return CdpHealthResult(
            reachable=False,
            endpoint=endpoint,
            elapsed_ms=elapsed,
            error=f"{type(exc).__name__}: {exc}",
        )
    elapsed = (time.monotonic() - start) * 1000.0
    status = getattr(response, "status_code", None)
    if status != 200:
        return CdpHealthResult(
            reachable=False,
            endpoint=endpoint,
            elapsed_ms=elapsed,
            error=f"unexpected status {status}",
        )
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 -- malformed body is a soft failure
        return CdpHealthResult(
            reachable=False,
            endpoint=endpoint,
            elapsed_ms=elapsed,
            error=f"json parse failed: {type(exc).__name__}",
        )
    if not isinstance(payload, list):
        return CdpHealthResult(
            reachable=False,
            endpoint=endpoint,
            elapsed_ms=elapsed,
            error="response body was not a JSON array",
        )
    page_tabs = sum(
        1
        for t in payload
        if isinstance(t, dict) and t.get("type") == "page"
    )
    return CdpHealthResult(
        reachable=True,
        endpoint=endpoint,
        tab_count=len(payload),
        page_tab_count=page_tabs,
        elapsed_ms=elapsed,
        error=None,
    )


__all__ = [
    "DEFAULT_CDP_HOST",
    "DEFAULT_HEALTH_CHECK_TIMEOUT_S",
    "CdpHealthResult",
    "GetFn",
    "HealthCheckResult",
    "cdp_health_check",
    "http_health_check",
]
