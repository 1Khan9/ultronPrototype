"""Tests for the Helix EventSub bootstrap client (offline, injected transport).

Drives :class:`HelixEventSubClient` with a mock transport that records every
``(method, url, headers, body)`` call and returns a canned ``(status, bytes)``.
No real network, no creds. Asserts:

  * ``get_user_id`` parses ``data[0]["id"]`` + sends Authorization + Client-Id;
  * the two ``create_*`` methods build the exact method / url / headers / JSON
    body Twitch's ``POST /eventsub/subscriptions`` expects (type / version /
    condition / transport) with the right token;
  * non-2xx -> ``False`` / ``None`` (no raise);
  * a transport that raises -> ``False`` / ``None`` (fail-safe, never raises into
    the caller's poll loop).
"""
from __future__ import annotations

import json

from kenning.twitch.clients.helix_eventsub import (
    CHAT_SUBSCRIPTION_TYPE,
    REDEEM_SUBSCRIPTION_TYPE,
    HelixEventSubClient,
    HelixEventSubError,
)


class RecordingTransport:
    """A mock transport: records calls, returns queued ``(status, body_bytes)``.

    ``responses`` is a list consumed in order; each is ``(status, dict-or-bytes)``.
    A dict is JSON-encoded for convenience. When exhausted the last response is
    reused so a test need only queue one. ``raise_exc`` makes every call raise
    (to exercise the fail-safe path).
    """

    def __init__(self, responses=None, *, raise_exc=None):
        self.responses = list(responses or [])
        self.raise_exc = raise_exc
        self.calls = []  # list of (method, url, headers, body)

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if self.raise_exc is not None:
            raise self.raise_exc
        if not self.responses:
            status, payload = 200, {}
        elif len(self.responses) == 1:
            status, payload = self.responses[0]
        else:
            status, payload = self.responses.pop(0)
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode("utf-8")


def _client(transport):
    return HelixEventSubClient("test-client-id", base_url="https://api.twitch.tv/helix", transport=transport)


# --------------------------------------------------------------------------- #
# get_user_id
# --------------------------------------------------------------------------- #
def test_get_user_id_parses_data0_id():
    t = RecordingTransport([(200, {"data": [{"id": "12345", "login": "streamer"}]})])
    uid = _client(t).get_user_id("streamer", token="bot-token-abc")
    assert uid == "12345"
    method, url, headers, body = t.calls[0]
    assert method == "GET"
    assert url == "https://api.twitch.tv/helix/users?login=streamer"
    assert headers["Authorization"] == "Bearer bot-token-abc"
    assert headers["Client-Id"] == "test-client-id"
    assert body is None  # GET has no body


def test_get_user_id_url_encodes_login():
    t = RecordingTransport([(200, {"data": [{"id": "9"}]})])
    _client(t).get_user_id("weird name", token="tok")
    assert t.calls[0][1] == "https://api.twitch.tv/helix/users?login=weird%20name"


def test_get_user_id_empty_data_returns_none():
    t = RecordingTransport([(200, {"data": []})])
    assert _client(t).get_user_id("nobody", token="tok") is None


def test_get_user_id_non_2xx_returns_none():
    t = RecordingTransport([(401, {"error": "Unauthorized", "status": 401})])
    assert _client(t).get_user_id("streamer", token="tok") is None


def test_get_user_id_transport_raise_is_failsafe():
    t = RecordingTransport(raise_exc=HelixEventSubError("dns down"))
    assert _client(t).get_user_id("streamer", token="tok") is None
    # any exception type, not just the typed one
    t2 = RecordingTransport(raise_exc=RuntimeError("boom"))
    assert _client(t2).get_user_id("streamer", token="tok") is None


def test_get_user_id_missing_token_returns_none():
    t = RecordingTransport([(200, {"data": [{"id": "1"}]})])
    assert _client(t).get_user_id("streamer", token="") is None
    assert t.calls == []  # never hit the wire without a token


# --------------------------------------------------------------------------- #
# create_chat_subscription
# --------------------------------------------------------------------------- #
def test_create_chat_subscription_builds_correct_request():
    t = RecordingTransport([(202, {"data": [{"id": "sub-1", "status": "enabled"}]})])
    ok = _client(t).create_chat_subscription(
        broadcaster_id="111", bot_user_id="222", session_id="sess-abc", token="bot-tok"
    )
    assert ok is True
    method, url, headers, body = t.calls[0]
    assert method == "POST"
    assert url == "https://api.twitch.tv/helix/eventsub/subscriptions"
    assert headers["Authorization"] == "Bearer bot-tok"
    assert headers["Client-Id"] == "test-client-id"
    assert headers["Content-Type"] == "application/json"
    payload = json.loads(body.decode("utf-8"))
    assert payload == {
        "type": CHAT_SUBSCRIPTION_TYPE,
        "version": "1",
        "condition": {"broadcaster_user_id": "111", "user_id": "222"},
        "transport": {"method": "websocket", "session_id": "sess-abc"},
    }


def test_create_chat_subscription_200_also_true():
    # Some replays return 200; any 2xx counts as success.
    t = RecordingTransport([(200, {"data": [{"id": "s"}]})])
    assert _client(t).create_chat_subscription(
        broadcaster_id="1", bot_user_id="2", session_id="s", token="tok"
    ) is True


def test_create_chat_subscription_non_2xx_returns_false():
    t = RecordingTransport([(400, {"error": "Bad Request", "message": "bad session"})])
    assert _client(t).create_chat_subscription(
        broadcaster_id="1", bot_user_id="2", session_id="s", token="tok"
    ) is False


def test_create_chat_subscription_transport_raise_is_failsafe():
    t = RecordingTransport(raise_exc=HelixEventSubError("tls reset"))
    assert _client(t).create_chat_subscription(
        broadcaster_id="1", bot_user_id="2", session_id="s", token="tok"
    ) is False


def test_create_chat_subscription_missing_ids_returns_false():
    t = RecordingTransport([(202, {})])
    c = _client(t)
    assert c.create_chat_subscription(broadcaster_id="", bot_user_id="2", session_id="s", token="t") is False
    assert c.create_chat_subscription(broadcaster_id="1", bot_user_id="", session_id="s", token="t") is False
    assert c.create_chat_subscription(broadcaster_id="1", bot_user_id="2", session_id="", token="t") is False
    assert c.create_chat_subscription(broadcaster_id="1", bot_user_id="2", session_id="s", token="") is False
    assert t.calls == []  # none reached the wire


# --------------------------------------------------------------------------- #
# create_redeem_subscription
# --------------------------------------------------------------------------- #
def test_create_redeem_subscription_builds_correct_request():
    t = RecordingTransport([(202, {"data": [{"id": "sub-2", "status": "enabled"}]})])
    ok = _client(t).create_redeem_subscription(
        broadcaster_id="111", session_id="sess-xyz", token="broadcaster-tok"
    )
    assert ok is True
    method, url, headers, body = t.calls[0]
    assert method == "POST"
    assert url == "https://api.twitch.tv/helix/eventsub/subscriptions"
    assert headers["Authorization"] == "Bearer broadcaster-tok"
    assert headers["Client-Id"] == "test-client-id"
    payload = json.loads(body.decode("utf-8"))
    assert payload == {
        "type": REDEEM_SUBSCRIPTION_TYPE,
        "version": "1",
        "condition": {"broadcaster_user_id": "111"},
        "transport": {"method": "websocket", "session_id": "sess-xyz"},
    }


def test_create_redeem_subscription_non_2xx_returns_false():
    t = RecordingTransport([(403, {"error": "Forbidden", "message": "missing scope"})])
    assert _client(t).create_redeem_subscription(
        broadcaster_id="1", session_id="s", token="tok"
    ) is False


def test_create_redeem_subscription_transport_raise_is_failsafe():
    t = RecordingTransport(raise_exc=RuntimeError("socket reset"))
    assert _client(t).create_redeem_subscription(
        broadcaster_id="1", session_id="s", token="tok"
    ) is False


# --------------------------------------------------------------------------- #
# Construction guard
# --------------------------------------------------------------------------- #
def test_requires_client_id():
    import pytest

    with pytest.raises(ValueError):
        HelixEventSubClient("")
