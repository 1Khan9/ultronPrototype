"""S11 — ModerationRemote: the orchestrator-side loopback client for the Twitch
WRITE / Helix moderation sidecar (``scripts/twitch_write_sidecar.py`` on
127.0.0.1:8777).

ALL Twitch network I/O lives in the SEPARATE write sidecar process (BR-P1); the
anticheat-pinned orchestrator keeps ONLY this thin ``urllib`` client. It speaks
the sidecar's tiny JSON HTTP surface:

    available()        -> GET  /healthz   -> True iff the sidecar reports ready
    prepare(text)      -> POST /prepare   -> the confirmable proposal dict
    confirm(token)     -> POST /confirm   -> the executed-write result dict
    cancel(token)      -> POST /cancel    -> best-effort drop (no return)

Every method is FAIL-SAFE: a transport fault (sidecar down, timeout, malformed
body) never raises into the caller — it degrades to a structured
``{"ok": False, "error": ...}`` (or ``False`` / no-op) and logs at WARNING/DEBUG.
A misheard moderation command must never crash the voice loop, and a dead sidecar
must never block speech.

The HTTP transport is INJECTED (mirrors ``HelixEventSubClient``) so the unit tests
run fully offline against a mock — no live sidecar, no socket.

ANTICHEAT (BR-P1): stdlib + ``urllib`` only. No ``requests`` / ``aiohttp`` /
``websockets`` / desktop-input/screen libs, no model.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

logger = logging.getLogger("kenning.twitch.moderation.remote")

__all__ = ["ModerationRemote", "Transport"]

# The injected transport: (method, url, body_bytes) -> (status, body_bytes).
# A non-2xx HTTP status must NOT raise — it is returned so the client can branch;
# a genuine connection-level failure (DNS / socket / timeout) MAY raise (the
# client catches it and fails safe).
Transport = Callable[[str, str, Optional[bytes]], "tuple[int, bytes]"]


def _default_transport(timeout: float) -> Transport:
    """The real ``urllib`` transport: stdlib only (BR-P1). Loopback only.

    Returns ``(status, body_bytes)``. A non-2xx HTTP status does NOT raise (the
    body is returned so the caller can read an error envelope); genuine transport
    failures (refused connection / timeout / socket reset) propagate as the
    underlying ``urllib``/``OSError`` exception, which every public method catches.
    """

    def _transport(method: str, url: str, body: Optional[bytes]) -> "tuple[int, bytes]":
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            url, data=body, headers=headers, method=(method or "GET").upper()
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — loopback only
                status = int(getattr(resp, "status", resp.getcode()) or 0)
                return status, resp.read()
        except urllib.error.HTTPError as exc:
            # Non-2xx — read the body so a caller can branch; do NOT raise.
            try:
                raw = exc.read()
            except Exception:  # noqa: BLE001 — body read on an error response is best-effort
                raw = b""
            return int(exc.code), raw

    return _transport


class ModerationRemote:
    """Thin loopback client for the Twitch write/moderation sidecar.

    Args:
        endpoint: the sidecar base URL (default ``http://127.0.0.1:8777``).
        timeout: per-request timeout in seconds (default 4.0).
        transport: an injected HTTP transport (see :data:`Transport`); defaults to
            a small ``urllib`` loopback implementation.

    Every method is fail-safe and never raises into the caller.
    """

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8777",
        *,
        timeout: float = 4.0,
        transport: Optional[Transport] = None,
    ) -> None:
        self._endpoint = (endpoint or "http://127.0.0.1:8777").rstrip("/")
        self._timeout = max(0.1, float(timeout))
        self._transport: Transport = transport or _default_transport(self._timeout)

    # ------------------------------------------------------------------ #
    # transport helpers (fail-safe)
    # ------------------------------------------------------------------ #
    def _request(
        self, method: str, path: str, payload: Optional[dict] = None
    ) -> "Optional[tuple[int, Any]]":
        """Issue one request. Returns ``(status, parsed_json_or_None)`` or ``None``
        on a transport-level failure (sidecar down / timeout). Never raises."""
        url = f"{self._endpoint}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        try:
            status, raw = self._transport(method, url, body)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            logger.debug("moderation remote %s %s transport error: %s", method, path, type(exc).__name__)
            return None
        except Exception as exc:  # noqa: BLE001 — never raise into the voice loop
            logger.warning("moderation remote %s %s unexpected transport error: %s", method, path, type(exc).__name__)
            return None
        return status, self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: Any) -> Any:
        if isinstance(raw, (bytes, bytearray)):
            text = raw.decode("utf-8", "replace").strip()
        else:
            text = str(raw or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def available(self) -> bool:
        """GET /healthz; True iff the sidecar is reachable AND reports ``ready``."""
        got = self._request("GET", "/healthz")
        if got is None:
            return False
        status, body = got
        if status < 200 or status >= 300 or not isinstance(body, dict):
            return False
        return bool(body.get("ready"))

    def prepare(self, text: str) -> dict:
        """POST /prepare ``{"text": text}`` -> the proposal dict.

        On a transport failure returns ``{"ok": False, "error": "unavailable"}``;
        on a non-2xx / unparseable body returns ``{"ok": False, "error": ...}``.
        Otherwise returns the sidecar's proposal dict verbatim (carrying ``token``,
        ``readback``, ``reason_blocked``, ``candidates``, ``action``, ``target`` —
        or ``not_a_command`` when the text is not a moderation command)."""
        got = self._request("POST", "/prepare", {"text": text})
        if got is None:
            return {"ok": False, "error": "unavailable"}
        status, body = got
        if status < 200 or status >= 300:
            return {"ok": False, "error": f"http_{status}"}
        if not isinstance(body, dict):
            return {"ok": False, "error": "bad_response"}
        return body

    def confirm(self, token: str) -> dict:
        """POST /confirm ``{"token": token}`` -> the executed-write result dict.

        Fail-safe like :meth:`prepare`. The returned dict is the sidecar's
        confirm result (``{"ok", "action", "target", ...}``) or
        ``{"ok": False, "error": "expired"}`` for an unknown/expired token."""
        got = self._request("POST", "/confirm", {"token": token})
        if got is None:
            return {"ok": False, "error": "unavailable"}
        status, body = got
        if status < 200 or status >= 300:
            return {"ok": False, "error": f"http_{status}"}
        if not isinstance(body, dict):
            return {"ok": False, "error": "bad_response"}
        return body

    def cancel(self, token: str) -> None:
        """POST /cancel ``{"token": token}`` — best-effort drop of a pending
        proposal. Never raises and ignores the result (a missing token is a no-op
        on the sidecar)."""
        self._request("POST", "/cancel", {"token": token})
