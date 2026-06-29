"""Minimal Helix chat-SEND client (urllib) — posts a chat message AS THE BOT.

The periodic commands-panel poster (and any future bot chat output) sends through
``POST /helix/chat/messages``, which requires the BOT's user access token
(``user:write:chat`` + ``user:bot``) and the bot's ``sender_id``. This is the ONLY
chat-WRITE in the system (chat REPLIES are spoken via TTS, never posted), so it
lives in its own tiny, fail-safe client used only inside the write sidecar.

ANTICHEAT (BR-P1): stdlib + ``urllib`` only. No ``requests``/``aiohttp``/
``websockets``/``transformers``/``torch`` and no desktop/input/screen libs. The
HTTP transport is INJECTED so unit tests run fully offline::

    transport(method, url, headers: dict, body: Optional[bytes]) -> (status: int, body_bytes: bytes)

A bearer token is sent only in the ``Authorization`` header and is NEVER logged.
Every public method is fail-safe: a transport raise / non-2xx / malformed body /
a Twitch ``is_sent=false`` drop becomes a logged ``False`` — it never raises into
the sidecar's request handler.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Callable, Optional, Tuple

logger = logging.getLogger("kenning.twitch.clients.chat_send")

__all__ = ["ChatSendClient", "ChatSendError", "HELIX_BASE"]

HELIX_BASE = "https://api.twitch.tv/helix"
_DEFAULT_TIMEOUT = 10.0
# Twitch hard-caps a chat message at 500 characters; we trim defensively so a
# long panel never 400s.
MAX_MESSAGE_CHARS = 500

# (method, url, headers, body) -> (status, body_bytes).
Transport = Callable[[str, str, dict, Optional[bytes]], Tuple[int, bytes]]


class ChatSendError(Exception):
    """A genuine connection-level fault from the default transport (DNS/TLS/timeout).
    Public methods CATCH it (and anything else) and return ``False``."""


def _default_transport(timeout: float = _DEFAULT_TIMEOUT) -> Transport:
    def _transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> Tuple[int, bytes]:
        req = urllib.request.Request(url, data=body, headers=dict(headers or {}),
                                     method=(method or "POST").upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — Twitch API over HTTPS
                return int(getattr(resp, "status", resp.getcode()) or 0), resp.read()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:  # noqa: BLE001
                raw = b""
            return int(exc.code), raw
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ChatSendError(f"chat-send transport error contacting Twitch: {exc}") from exc

    return _transport


class ChatSendClient:
    """Posts a chat message as the bot via Helix. Fail-safe: ``send`` returns
    ``True`` only on a confirmed send, ``False`` on any error / drop."""

    def __init__(
        self,
        client_id: str,
        get_token: Callable[[], str],
        *,
        base_url: str = HELIX_BASE,
        transport: Optional[Transport] = None,
        timeout: float = _DEFAULT_TIMEOUT,
        on_unauthorized: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        if not client_id or not isinstance(client_id, str):
            raise ValueError("client_id is required")
        if not callable(get_token):
            raise ValueError("get_token must be callable")
        self._client_id = client_id
        self._get_token = get_token
        self._base = (base_url or HELIX_BASE).rstrip("/")
        self._transport: Transport = transport or _default_transport(float(timeout))
        # Reactive refresh-on-401: the bot user token lapses ~every 4h. When set,
        # a 401 from a send triggers ONE refresh (this callback returns a fresh
        # access token, or "" / None when the grant is dead) and ONE retry, so a
        # long-running sidecar self-heals instead of 401ing until restart. When
        # None (the default) send() is byte-identical to before.
        self._on_unauthorized = on_unauthorized if callable(on_unauthorized) else None

    def send(self, broadcaster_id: str, sender_id: str, message: str) -> bool:
        """POST one chat message (``sender_id`` is the bot). ``True`` iff Twitch
        confirms ``is_sent``. Fail-safe — never raises."""
        if not broadcaster_id or not sender_id:
            logger.warning("chat-send: missing broadcaster/sender id")
            return False
        text = (message or "").strip()
        if not text:
            return False
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[:MAX_MESSAGE_CHARS]
        token = self._get_token() or ""
        if not token:
            logger.warning("chat-send: no bot access token")
            return False
        body = json.dumps({
            "broadcaster_id": str(broadcaster_id),
            "sender_id": str(sender_id),
            "message": text,
        }).encode("utf-8")

        def _post(tok: str) -> Tuple[int, bytes]:
            headers = {
                "Authorization": f"Bearer {tok}",
                "Client-Id": self._client_id,
                "Content-Type": "application/json",
            }
            return self._transport("POST", f"{self._base}/chat/messages", headers, body)

        try:
            status, raw = _post(token)
        except Exception as exc:  # noqa: BLE001 — fail-safe
            logger.warning("chat-send transport failed: %s", type(exc).__name__)
            return False
        # A 401 means the bot user token lapsed mid-session. Refresh ONCE and
        # retry ONCE so chat output self-heals (without this it 401s on every
        # send until the sidecar is restarted -- ~1.5h of dead chat was observed).
        if status == 401 and self._on_unauthorized is not None:
            try:
                fresh = self._on_unauthorized() or ""
            except Exception as exc:  # noqa: BLE001 — never raise into the handler
                logger.warning("chat-send token refresh raised: %s", type(exc).__name__)
                fresh = ""
            if fresh and fresh != token:
                logger.info("chat-send 401 -> refreshed bot token, retrying once")
                try:
                    status, raw = _post(fresh)
                except Exception as exc:  # noqa: BLE001 — fail-safe
                    logger.warning("chat-send transport failed on retry: %s", type(exc).__name__)
                    return False
        if not (200 <= status < 300):
            logger.warning("chat-send non-2xx status=%s body=%s", status, _preview(raw))
            return False
        # Twitch returns data[0].is_sent (+ drop_reason when dropped).
        try:
            data = json.loads(raw.decode("utf-8", "replace")) if raw else {}
            row = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
        except (ValueError, TypeError, IndexError):
            row = {}
        is_sent = bool(row.get("is_sent", True))  # absent -> assume sent (2xx)
        if not is_sent:
            logger.warning("chat-send dropped by Twitch: %s", row.get("drop_reason"))
        return is_sent


def _preview(raw: bytes, limit: int = 200) -> str:
    try:
        return raw.decode("utf-8", "replace")[:limit]
    except Exception:  # noqa: BLE001
        return repr(raw[:limit])
