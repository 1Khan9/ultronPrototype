"""Tests for the non-blocking receive path added for the live sidecar drain.

Covers ``RFC6455Client.recv_json_ready`` + the opt-in ``FakeSocket.block_on_empty``
mode. All offline via synthetic frames + the fake socket. The existing blocking
``recv()``/``recv_json()`` semantics are exercised by ``test_eventsub.py`` and are
unchanged here.
"""
from __future__ import annotations

import json
import struct

import pytest

from kenning.twitch.clients.eventsub import (
    OPCODE_CLOSE,
    OPCODE_PING,
    FakeSocket,
    RFC6455Client,
    WebSocketClosed,
)

# Reuse the server-side (unmasked) frame builder shape used by the main suite.
from tests.twitch.clients.test_eventsub import server_frame, text_frame


# --------------------------------------------------------------------------- #
# FakeSocket block_on_empty
# --------------------------------------------------------------------------- #
def test_fakesocket_default_eof_unchanged():
    # Default mode: an exhausted buffer returns b"" (EOF) — existing behaviour.
    sock = FakeSocket(b"")
    assert sock.recv(64) == b""


def test_fakesocket_block_on_empty_raises_timeout():
    import socket as _socket

    sock = FakeSocket(b"", block_on_empty=True)
    with pytest.raises(_socket.timeout):
        sock.recv(64)
    # Once fed, it returns the data; then times out again when re-exhausted.
    sock.feed(b"abc")
    assert sock.recv(64) == b"abc"
    with pytest.raises(_socket.timeout):
        sock.recv(64)


# --------------------------------------------------------------------------- #
# recv_json_ready
# --------------------------------------------------------------------------- #
def test_recv_json_ready_returns_ready_message():
    obj = {"metadata": {"message_type": "session_keepalive"}, "payload": {}}
    sock = FakeSocket(text_frame(json.dumps(obj)), block_on_empty=True)
    client = RFC6455Client(sock=sock)
    assert client.recv_json_ready(0.05) == obj
    # No more data -> clean None (no close).
    assert client.recv_json_ready(0.05) is None
    assert sock.closed is False


def test_recv_json_ready_none_on_timeout_no_close():
    sock = FakeSocket(b"", block_on_empty=True)
    client = RFC6455Client(sock=sock)
    assert client.recv_json_ready(0.01) is None
    assert client.recv_json_ready(0.01) is None  # idempotent, still no close
    assert sock.closed is False
    # The socket timeout was applied.
    assert sock.timeout == 0.01


def test_recv_json_ready_eof_raises_closed():
    # An EOF (b"" while NOT in block_on_empty mode) is a real close.
    sock = FakeSocket(b"")  # default -> b"" means EOF
    client = RFC6455Client(sock=sock)
    with pytest.raises(WebSocketClosed) as ei:
        client.recv_json_ready(0.05)
    assert ei.value.code == 1006


def test_recv_json_ready_close_frame_raises_closed():
    close_payload = struct.pack(">H", 1000) + b"bye"
    sock = FakeSocket(server_frame(OPCODE_CLOSE, close_payload), block_on_empty=True)
    client = RFC6455Client(sock=sock)
    with pytest.raises(WebSocketClosed) as ei:
        client.recv_json_ready(0.05)
    assert ei.value.code == 1000


def test_recv_json_ready_handles_ping_then_message():
    ping = server_frame(OPCODE_PING, b"hb")
    msg = text_frame(json.dumps({"metadata": {"message_type": "notification"}}))
    sock = FakeSocket(ping + msg, block_on_empty=True)
    client = RFC6455Client(sock=sock)
    out = client.recv_json_ready(0.05)
    assert out == {"metadata": {"message_type": "notification"}}
    # The PING was answered with a PONG.
    from kenning.twitch.clients.eventsub import OPCODE_PONG

    parsed = RFC6455Client._parse_frame(bytes(sock.sent))
    assert parsed is not None and parsed[0] == OPCODE_PONG


def test_recv_json_ready_non_object_yields_empty():
    sock = FakeSocket(text_frame("[1,2,3]"), block_on_empty=True)
    client = RFC6455Client(sock=sock)
    assert client.recv_json_ready(0.05) == {}


def test_recv_json_ready_partial_frame_then_completes():
    # A message split so the first recv() yields only a partial frame and the
    # next (after a timeout cycle) completes it. recv_json_ready returns None on
    # the partial cycle, then the full object once the rest arrives.
    full = text_frame(json.dumps({"k": "v"}))
    head, tail = full[: len(full) // 2], full[len(full) // 2 :]
    sock = FakeSocket(head, block_on_empty=True)
    client = RFC6455Client(sock=sock)
    # First call: only the head is available -> partial -> None, no close.
    assert client.recv_json_ready(0.01) is None
    assert sock.closed is False
    # Feed the tail; next call completes the message.
    sock.feed(tail)
    assert client.recv_json_ready(0.01) == {"k": "v"}
