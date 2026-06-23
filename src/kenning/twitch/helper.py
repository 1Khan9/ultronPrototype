"""HelperClient — loopback sidecar client for the Qwen2.5 helper model.

The helper model is an OPTIONAL CPU-only GGUF sidecar that classifies
natural-language chat input into a CLOSED enum of safe action types (economy
commands only — moderation is unreachable by design). It is a thin ``urllib``
client (voice-process-safe, anticheat-clean) that talks to the sidecar at
``scripts/twitch_helper_sidecar.py``.

Fail-CLOSED: any error / timeout / unexpected response returns ``None``, which
the caller treats as "do not act". Chat text NEVER expands the action enum —
the ``choices`` list is caller-authoritative and is sent to the sidecar; the
sidecar response is validated against the same list before returning.

ANTICHEAT (BR-P1): stdlib only — urllib, json, logging.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger("kenning.twitch.helper")

__all__ = ["HelperClient", "HelperUnavailable"]


class HelperUnavailable(RuntimeError):
    """The helper sidecar could not be reached / errored / timed out.
    The caller fails CLOSED (return None, do not act)."""


class HelperClient:
    """Loopback client for the Qwen2.5 helper sidecar.

    :param url: base URL of the sidecar, e.g. ``"http://127.0.0.1:8776"``.
    :param timeout_s: per-request timeout in seconds (default 5.0).
    """

    def __init__(self, url: str, *, timeout_s: float = 5.0) -> None:
        self._base = url.rstrip("/")
        self._timeout = float(timeout_s)

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        url = f"{self._base}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read()
                if resp.status != 200:
                    raise HelperUnavailable(f"helper {path} -> HTTP {resp.status}")
                return json.loads(body or b"{}")
        except HelperUnavailable:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise HelperUnavailable(f"helper {path} unreachable: {exc}") from exc

    def classify(self, text: str, choices: list[str]) -> Optional[str]:
        """Classify ``text`` into one of ``choices`` using the helper model.

        Returns one of the ``choices`` strings, or ``None`` on any failure
        (timeout / sidecar down / response not in choices). The ``choices``
        list is caller-authoritative — the sidecar response is validated
        against it before returning so chat text can never inject new actions.

        :param text: the raw chat message to classify.
        :param choices: the closed set of allowed action strings.
        """
        if not choices:
            logger.warning("HelperClient.classify: empty choices list -> None")
            return None
        if not text or not text.strip():
            return None
        try:
            data = self._request("POST", "/classify", {"text": text, "choices": choices})
        except HelperUnavailable as exc:
            logger.warning("HelperClient: unavailable: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("HelperClient: unexpected error: %s", exc)
            return None

        action = data.get("action")
        if action is None:
            logger.warning("HelperClient: response missing 'action' field -> None")
            return None
        if action not in choices:
            logger.warning(
                "HelperClient: response %r not in choices %r -> None (fail-CLOSED)",
                action, choices,
            )
            return None
        return action

    def health(self) -> bool:
        """True if the sidecar is reachable and reports ready=True."""
        try:
            d = self._request("GET", "/healthz")
            return bool(d.get("ready"))
        except Exception:  # noqa: BLE001
            return False
