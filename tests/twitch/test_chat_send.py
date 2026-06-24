"""Tests for the bot chat-SEND client + the periodic commands-panel text.

Fully offline: the Helix transport is injected (no network); the panel builder is
pure. Covers the send happy-path, a Twitch ``is_sent=false`` drop, a missing token,
empty text, a non-2xx, the 500-char trim, and the panel text with/without a guide
URL.
"""
from __future__ import annotations

import json
import types

from kenning.twitch.clients.chat_send import MAX_MESSAGE_CHARS, ChatSendClient
from kenning.twitch.panel import MAX_CHAT_CHARS, build_commands_panel_text


def _ok_transport(record=None):
    def t(method, url, headers, body):
        if record is not None:
            record.append((method, url, dict(headers), json.loads(body)))
        return 200, json.dumps({"data": [{"is_sent": True}]}).encode()
    return t


def test_chat_send_posts_and_reports_sent():
    rec = []
    c = ChatSendClient("cid", get_token=lambda: "tok", transport=_ok_transport(rec))
    assert c.send("B1", "U1", "hello chat") is True
    method, url, headers, body = rec[0]
    assert method == "POST" and url.endswith("/chat/messages")
    assert body == {"broadcaster_id": "B1", "sender_id": "U1", "message": "hello chat"}
    assert headers["Authorization"] == "Bearer tok" and headers["Client-Id"] == "cid"


def test_chat_send_dropped_by_twitch_returns_false():
    def t(method, url, headers, body):
        return 200, json.dumps({"data": [{"is_sent": False, "drop_reason": {"code": "x"}}]}).encode()
    c = ChatSendClient("cid", get_token=lambda: "tok", transport=t)
    assert c.send("B1", "U1", "x") is False


def test_chat_send_requires_token_and_nonempty_text():
    c = ChatSendClient("cid", get_token=lambda: "", transport=_ok_transport())
    assert c.send("B1", "U1", "x") is False                    # no token
    c2 = ChatSendClient("cid", get_token=lambda: "tok", transport=_ok_transport())
    assert c2.send("B1", "U1", "   ") is False                  # empty text
    assert c2.send("", "U1", "hi") is False                     # no broadcaster id


def test_chat_send_non_2xx_is_false():
    c = ChatSendClient("cid", get_token=lambda: "tok",
                       transport=lambda *a: (401, b'{"message":"unauthorized"}'))
    assert c.send("B1", "U1", "x") is False


def test_chat_send_transport_raise_is_false():
    def boom(*a):
        raise RuntimeError("dns")
    c = ChatSendClient("cid", get_token=lambda: "tok", transport=boom)
    assert c.send("B1", "U1", "x") is False


def test_chat_send_trims_to_500():
    captured = {}

    def t(method, url, headers, body):
        captured["msg"] = json.loads(body)["message"]
        return 200, b'{"data":[{"is_sent":true}]}'
    c = ChatSendClient("cid", get_token=lambda: "tok", transport=t)
    c.send("B1", "U1", "x" * 600)
    assert len(captured["msg"]) == MAX_MESSAGE_CHARS == 500


def test_panel_text_without_url():
    t = build_commands_panel_text(types.SimpleNamespace(commands_panel_doc_url=""))
    assert "!gamble" in t and "!help" in t and "!heist" in t
    assert "Full guide" not in t and len(t) <= MAX_CHAT_CHARS


def test_panel_text_with_url_and_length_cap():
    t = build_commands_panel_text(types.SimpleNamespace(commands_panel_doc_url="https://docs.example/g"))
    assert "Full guide" in t and "https://docs.example/g" in t
    assert len(t) <= MAX_CHAT_CHARS
