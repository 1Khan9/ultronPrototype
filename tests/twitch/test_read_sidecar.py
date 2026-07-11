"""S1 — tests for the Twitch chat READ sidecar (scripts/twitch_read_sidecar.py).

Fully offline: a ``FakeSource`` feeds the rolling buffer and an ephemeral-port
(``port=0``) ``ThreadingHTTPServer`` is driven with ``urllib`` over loopback. No
live Twitch connection, no creds, no models.

Covered:
  * GET /healthz reports ok + buffered + cursor + source name.
  * /buffer drains injected events and the returned cursor advances.
  * ?since=N filters to events strictly after N.
  * POST /ack advances the consumer cursor and prunes acked events.
  * the rolling buffer respects maxlen (oldest-first eviction, dropped count).
  * the rolling buffer respects the TTL (time-expired events pruned).
  * the parent-watchdog helper returns 'dead' for a bogus pid (mocked) and
    'alive' for a live/unset pid (so it would NOT self-kill on doubt).
  * the server binds 127.0.0.1 ONLY (not 0.0.0.0).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

# --------------------------------------------------------------------------- #
# Load the sidecar module by path (scripts/ is not an importable package).
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parents[2]
_SIDECAR_PATH = _ROOT / "scripts" / "twitch_read_sidecar.py"


def _load_sidecar():
    spec = importlib.util.spec_from_file_location("twitch_read_sidecar", _SIDECAR_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("twitch_read_sidecar", mod)
    spec.loader.exec_module(mod)
    return mod


sidecar = _load_sidecar()


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
class _Served:
    """Context manager: a built sidecar server serving on a background thread."""

    def __init__(self, source=None, **kw):
        # Tests pump the poll loop manually -> start_poll=False for determinism,
        # except where a test explicitly wants the live thread.
        kw.setdefault("start_poll", False)
        self.server, self.buffer, self.poll_loop = sidecar.build_server(source, port=0, **kw)
        self.host, self.port = self.server.server_address[:2]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.poll_loop.stop()
        self._thread.join(timeout=3.0)

    @property
    def base(self) -> str:
        return f"http://{self.host}:{self.port}"


def _get(url: str) -> dict:
    with urlopen(url, timeout=5) as resp:  # noqa: S310 — loopback only
        assert resp.status == 200
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=5) as resp:  # noqa: S310 — loopback only
        assert resp.status == 200
        return json.loads(resp.read().decode("utf-8"))


def _chat(login: str, text: str, mid: str) -> dict:
    return {"type": "chat", "message_id": mid, "chatter_login": login, "text": text}


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_healthz_reports_state() -> None:
    src = sidecar.FakeSource()
    with _Served(src) as s:
        body = _get(f"{s.base}/healthz")
    assert body["ok"] is True
    assert body["buffered"] == 0
    assert body["cursor"] == 0
    assert body["source"] == "fake"
    # poll loop not started in this fixture -> running False
    assert body["running"] is False
    # 2026-07-08: a source WITHOUT subscription state (FakeSource) reports
    # subscribed + clean so tests/flag-off boots never read as degraded.
    assert body["chat_subscribed"] is True
    assert body["subscribe_error"] == ""


def test_healthz_surfaces_dead_chat_subscription() -> None:
    """2026-07-08 revoked-bot-token incident: healthz said ok=true while the
    chat subscription was dead. The subscription state must be visible so the
    boot canary can print the re-mint remedy."""
    src = sidecar.FakeSource()
    src._subscribed = False
    src.last_subscribe_error = (
        "helix id resolution failed (broadcaster=False bot=False) -- bot "
        "token invalid/expired/revoked? re-mint via scripts/twitch_setup.py "
        "--identity bot")
    with _Served(src) as s:
        body = _get(f"{s.base}/healthz")
    assert body["ok"] is True                      # the HTTP server IS up
    assert body["chat_subscribed"] is False        # ...but chat is dead
    assert "re-mint" in body["subscribe_error"]


def test_buffer_drain_returns_injected_events_and_advances_cursor() -> None:
    src = sidecar.FakeSource()
    with _Served(src) as s:
        src.push(_chat("alice", "hello", "m1"), _chat("bob", "gg", "m2"))
        appended = s.poll_loop.run_once()
        assert appended == 2

        body = _get(f"{s.base}/buffer")
        events = body["events"]
        assert [e["event"]["message_id"] for e in events] == ["m1", "m2"]
        assert [e["event"]["text"] for e in events] == ["hello", "gg"]
        # every event carries a monotonically increasing seq + ts
        assert [e["seq"] for e in events] == [1, 2]
        assert all(isinstance(e["ts"], (int, float)) for e in events)
        # cursor returned is the high-water mark of what was drained
        assert body["cursor"] == 2

        # healthz now reflects the 2 buffered events
        h = _get(f"{s.base}/healthz")
        assert h["buffered"] == 2
        assert h["cursor"] == 0  # not acked yet


def test_last_message_route_returns_latest_message_id() -> None:
    src = sidecar.FakeSource()
    with _Served(src) as s:
        src.push(_chat("Alice", "hi", "m1"), _chat("bob", "gg", "m2"),
                 _chat("alice", "wp", "m3"))
        s.poll_loop.run_once()
        # case-insensitive; the MOST-RECENT message for a login wins
        assert _get(f"{s.base}/last_message?login=alice")["message_id"] == "m3"
        assert _get(f"{s.base}/last_message?login=BOB")["message_id"] == "m2"
        # unknown login -> null; missing login -> null, never a crash
        assert _get(f"{s.base}/last_message?login=ghost")["message_id"] is None
        assert _get(f"{s.base}/last_message")["message_id"] is None


def test_since_cursor_filters() -> None:
    src = sidecar.FakeSource()
    with _Served(src) as s:
        src.push(_chat("a", "1", "m1"), _chat("b", "2", "m2"), _chat("c", "3", "m3"))
        s.poll_loop.run_once()

        # ?since=1 -> only seq 2 and 3
        body = _get(f"{s.base}/buffer?since=1")
        assert [e["seq"] for e in body["events"]] == [2, 3]
        assert body["cursor"] == 3

        # ?since=3 -> nothing newer; cursor stays at the floor
        body = _get(f"{s.base}/buffer?since=3")
        assert body["events"] == []
        assert body["cursor"] == 3

        # garbage ?since -> falls back to the consumer cursor (0) -> all events
        body = _get(f"{s.base}/buffer?since=not_a_number")
        assert [e["seq"] for e in body["events"]] == [1, 2, 3]


def test_ack_advances_cursor_and_prunes() -> None:
    src = sidecar.FakeSource()
    with _Served(src) as s:
        src.push(_chat("a", "1", "m1"), _chat("b", "2", "m2"), _chat("c", "3", "m3"))
        s.poll_loop.run_once()

        # ack up to seq 2 -> events m1,m2 pruned, only m3 remains
        ack = _post(f"{s.base}/ack", {"cursor": 2})
        assert ack["ok"] is True
        assert ack["cursor"] == 2

        h = _get(f"{s.base}/healthz")
        assert h["cursor"] == 2
        assert h["buffered"] == 1  # only m3 left

        # /buffer with no ?since now uses the consumer cursor (2) -> only m3
        body = _get(f"{s.base}/buffer")
        assert [e["seq"] for e in body["events"]] == [3]

        # ack cannot regress the cursor
        ack2 = _post(f"{s.base}/ack", {"cursor": 1})
        assert ack2["cursor"] == 2


def test_rolling_buffer_respects_maxlen() -> None:
    buf = sidecar.RollingBuffer(maxlen=3, ttl_seconds=0)  # ttl off -> isolate maxlen
    for i in range(5):
        buf.append({"message_id": f"m{i}"})
    # only the last 3 survive (oldest-first eviction)
    events, cursor = buf.drain(since=0)
    assert [e["event"]["message_id"] for e in events] == ["m2", "m3", "m4"]
    assert [e["seq"] for e in events] == [3, 4, 5]
    assert cursor == 5
    # two events (m0, m1) were evicted unacked -> counted as drops
    assert buf.dropped_total == 2
    assert len(buf) == 3


def test_rolling_buffer_respects_ttl() -> None:
    buf = sidecar.RollingBuffer(maxlen=100, ttl_seconds=10.0)
    base = 1000.0
    buf.append({"message_id": "old"}, now=base)
    buf.append({"message_id": "fresh"}, now=base + 9.0)
    # at base+11: "old" (age 11s) is expired, "fresh" (age 2s) survives
    events, _cursor = buf.drain(since=0, now=base + 11.0)
    assert [e["event"]["message_id"] for e in events] == ["fresh"]
    assert len(buf) == 1
    # the expired, unacked event counts as a drop
    assert buf.dropped_total == 1


def test_parent_watchdog_dead_for_bogus_pid(monkeypatch) -> None:
    # A bogus pid that _pid_alive reports as gone -> watchdog says 'dead'
    # (the loop would then os._exit). We mock _pid_alive so we never depend on a
    # real OS pid table and never actually exit.
    monkeypatch.setattr(sidecar, "_pid_alive", lambda pid: False)
    assert sidecar.parent_watchdog_check(999_999_999) == "dead"

    # A pid reported alive -> 'alive' (never self-kill).
    monkeypatch.setattr(sidecar, "_pid_alive", lambda pid: True)
    assert sidecar.parent_watchdog_check(4321) == "alive"

    # An unset/invalid pid -> 'alive' (fail-safe: never self-kill on doubt),
    # WITHOUT consulting _pid_alive.
    def _boom(pid):  # pragma: no cover - must not be called
        raise AssertionError("_pid_alive should not be consulted for pid<=0")

    monkeypatch.setattr(sidecar, "_pid_alive", _boom)
    assert sidecar.parent_watchdog_check(0) == "alive"
    assert sidecar.parent_watchdog_check(-1) == "alive"


def test_pid_alive_failsafe_on_indeterminate(monkeypatch) -> None:
    # If psutil is absent and the OS probe raises, _pid_alive must fail SAFE (True)
    # so the watchdog never self-kills on an indeterminate result.
    import builtins

    real_import = builtins.__import__

    def _no_psutil(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("psutil intentionally absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_psutil)
    # pid<=0 short-circuits to True before any probe.
    assert sidecar._pid_alive(0) is True


def test_server_binds_loopback_only() -> None:
    with _Served(sidecar.FakeSource()) as s:
        # bound host must be the loopback address, never 0.0.0.0 / a routable iface
        assert s.host == "127.0.0.1"
        assert s.host != "0.0.0.0"
        # and it actually answers on loopback
        body = _get(f"{s.base}/healthz")
        assert body["ok"] is True


def test_unknown_route_404() -> None:
    import urllib.error

    with _Served(sidecar.FakeSource()) as s:
        with pytest.raises(urllib.error.HTTPError) as ei:
            _get(f"{s.base}/nope")
        assert ei.value.code == 404


def test_default_source_serves_empty_buffer() -> None:
    # build_server with no source -> empty FakeSource -> empty buffer (the
    # documented flag-off behaviour: run directly, serve nothing).
    with _Served() as s:
        s.poll_loop.run_once()  # nothing queued
        body = _get(f"{s.base}/buffer")
        assert body["events"] == []
        h = _get(f"{s.base}/healthz")
        assert h["buffered"] == 0
        assert h["source"] == "fake"


def test_poll_loop_thread_pumps_live(monkeypatch) -> None:
    # Exercise the real background thread (start_poll=True) end-to-end.
    src = sidecar.FakeSource()
    server, buffer, poll_loop = sidecar.build_server(
        src, port=0, poll_interval=0.01, start_poll=True
    )
    host, port = server.server_address[:2]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        assert poll_loop.running is True
        src.push(_chat("live", "from the thread", "live1"))
        # wait for the poll thread to pick it up
        deadline = time.time() + 3.0
        events = []
        while time.time() < deadline:
            body = _get(f"http://{host}:{port}/buffer?since=0")
            events = body["events"]
            if events:
                break
            time.sleep(0.02)
        assert [e["event"]["message_id"] for e in events] == ["live1"]
    finally:
        server.shutdown()
        server.server_close()
        poll_loop.stop()
        t.join(timeout=3.0)
    assert poll_loop.running is False
    assert src.closed is True  # stop() closed the source


def test_source_poll_raise_is_swallowed() -> None:
    # A source that raises on poll() must not crash the poll loop.
    class _Boom:
        name = "boom"

        def poll(self):
            raise RuntimeError("source exploded")

    buffer = sidecar.RollingBuffer()
    loop = sidecar.PollLoop(_Boom(), buffer, interval=0.01)
    assert loop.run_once() == 0  # swallowed, zero appended
    assert len(buffer) == 0


# --------------------------------------------------------------------------- #
# Live EventSubChatSource (injected fake WS + fake Helix; no network/creds)
# --------------------------------------------------------------------------- #
class _FakeWSClient:
    """A fake EventSub WS client exposing ``recv_json_ready`` + ``close``.

    Queued dicts are returned one-per-call; ``None`` means "no data this cycle".
    A queued ``"__CLOSE__"`` sentinel raises ``WebSocketClosed`` (to drive the
    reconnect path). ``recv_timeout`` is recorded but unused (offline)."""

    def __init__(self, messages):
        self._queue = list(messages)
        self.closed = False
        self.recv_calls = 0

    def recv_json_ready(self, timeout):
        self.recv_calls += 1
        from kenning.twitch.clients.eventsub import WebSocketClosed

        if not self._queue:
            return None
        item = self._queue.pop(0)
        if item == "__CLOSE__":
            raise WebSocketClosed(1006, "test close")
        return item

    def feed(self, *messages):
        self._queue.extend(messages)

    def close(self):
        self.closed = True


class _FakeHelix:
    """A fake Helix client: canned login->id map + records subscription calls."""

    def __init__(self, id_map=None):
        self._ids = id_map or {"streamer": "B-100", "ultronbot": "U-200"}
        self.chat_subs = []
        self.clear_subs = []
        self.redeem_subs = []

    def get_user_id(self, login, *, token):
        return self._ids.get(login)

    def create_chat_subscription(self, *, broadcaster_id, bot_user_id, session_id, token):
        self.chat_subs.append((broadcaster_id, bot_user_id, session_id, token))
        return True

    def create_chat_clear_subscription(self, *, broadcaster_id, bot_user_id, session_id, token):
        # Ban/timeout signals for the welcome ban-guard (2026-07-10).
        self.clear_subs.append((broadcaster_id, bot_user_id, session_id, token))
        return True

    def create_redeem_subscription(self, *, broadcaster_id, session_id, token):
        self.redeem_subs.append((broadcaster_id, session_id, token))
        return True


def _welcome(session_id: str = "sess-1") -> dict:
    return {
        "metadata": {"message_type": "session_welcome"},
        "payload": {"session": {"id": session_id, "status": "connected",
                                "keepalive_timeout_seconds": 10}},
    }


def _chat_notification(mid: str, login: str = "viewer", text: str = "hi") -> dict:
    return {
        "metadata": {"message_type": "notification", "subscription_type": "channel.chat.message"},
        "payload": {
            "subscription": {"type": "channel.chat.message"},
            "event": {
                "broadcaster_user_id": "B-100",
                "chatter_user_id": "V-9",
                "chatter_user_login": login,
                "chatter_user_name": login.title(),
                "message_id": mid,
                "message": {"text": text, "fragments": [], "message_type": "text"},
            },
        },
    }


def _redeem_notification(rid: str, reward_title: str = "Spin", user_input: str = "go") -> dict:
    return {
        "metadata": {
            "message_type": "notification",
            "subscription_type": "channel.channel_points_custom_reward_redemption.add",
        },
        "payload": {
            "subscription": {"type": "channel.channel_points_custom_reward_redemption.add"},
            "event": {
                "id": rid,
                "broadcaster_user_id": "B-100",
                "user_id": "V-9",
                "user_login": "viewer",
                "user_name": "Viewer",
                "user_input": user_input,
                "status": "unfulfilled",
                "reward": {"id": "rw-1", "title": reward_title, "cost": 100},
            },
        },
    }


def _patch_tokens(monkeypatch) -> None:
    """Make TokenStore(path).load() return a usable access token (no real file)."""
    import kenning.twitch.auth as auth_mod

    class _Store:
        def __init__(self, path=None):
            self.path = path

        def load(self):
            return {"access_token": "tok-" + str(self.path)}

    monkeypatch.setattr(auth_mod, "TokenStore", _Store)


def test_eventsub_source_subscribes_and_maps_chat(monkeypatch) -> None:
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    ws = _FakeWSClient([_welcome("sess-1"), _chat_notification("c1", "alice", "gg")])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws",
        client_id="cid",
        broadcaster_login="streamer",
        bot_login="ultronbot",
        connect_factory=lambda url: ws,
        helix_factory=lambda: helix,
    )
    out = src.poll()
    # The chat notification mapped to the consumer shape (2026-07-09: extended
    # with message_type + broadcaster_user_id — previously parsed then dropped).
    chats = [e for e in out if e["type"] == "chat"]
    assert chats == [
        {
            "type": "chat",
            "message_id": "c1",
            "chatter_login": "alice",
            "chatter_name": "Alice",
            "chatter_user_id": "V-9",
            "text": "gg",
            # badges carry mod/broadcaster provenance for chat-command authz
            # (empty here -- the source event has no badges).
            "badges": [],
            "message_type": "text",
            "broadcaster_user_id": "B-100",
            # 2026-07-11: reply relationship + typed fragments now forwarded
            # (None / [] for a plain non-reply message).
            "reply_parent_user_id": None,
            "fragments": [],
        }
    ]
    # The chat subscription was created with the RESOLVED ids + the session id.
    assert helix.chat_subs == [("B-100", "U-200", "sess-1", "tok-~/.kenning/twitch_bot.json")]
    # Redeems off by default -> no redeem subscription.
    assert helix.redeem_subs == []


def test_eventsub_source_subscribes_redeems_on_separate_session(monkeypatch) -> None:
    # The redeem subscription lives on a SEPARATE websocket session (broadcaster
    # token) from the chat sub (bot token): Twitch rejects two users' subs on one
    # session ("subscriptions created by different users"). Two isolated connections.
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    chat_ws = _FakeWSClient([_welcome("sess-chat")])
    redeem_ws = _FakeWSClient([_welcome("sess-redeem"),
                               _redeem_notification("r1", "Spin the Wheel", "spin!")])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws",
        client_id="cid",
        broadcaster_login="streamer",
        bot_login="ultronbot",
        subscribe_redeems=True,
        connect_factory=lambda url: chat_ws,
        redeem_connect_factory=lambda url: redeem_ws,
        helix_factory=lambda: helix,
    )
    out = src.poll()
    redeems = [e for e in out if e["type"] == "redeem"]
    assert redeems == [
        {
            "type": "redeem",
            "redemption_id": "r1",
            "reward_id": "rw-1",
            "reward_title": "Spin the Wheel",
            "user_input": "spin!",
            "chatter_login": "viewer",
            "chatter_name": "Viewer",
            "chatter_user_id": "V-9",
            "status": "unfulfilled",
        }
    ]
    # Chat sub on its OWN session (bot token); redeem sub on a SEPARATE session
    # (broadcaster token) -> no cross-user 400.
    assert helix.chat_subs and helix.chat_subs[0][:3] == ("B-100", "U-200", "sess-chat")
    assert helix.redeem_subs == [("B-100", "sess-redeem", "tok-~/.kenning/twitch.json")]


def test_eventsub_source_dedups_chat_and_redeem(monkeypatch) -> None:
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    ws = _FakeWSClient(
        [
            _welcome("s"),
            _chat_notification("dup", "a", "1"),
            _chat_notification("dup", "a", "1"),  # same message_id -> dropped
            _redeem_notification("rdup"),
            _redeem_notification("rdup"),  # same redemption id -> dropped
        ]
    )
    src = sidecar.EventSubChatSource(
        url="wss://test/ws",
        client_id="cid",
        broadcaster_login="streamer",
        bot_login="ultronbot",
        subscribe_redeems=True,
        connect_factory=lambda url: ws,
        helix_factory=lambda: helix,
    )
    out = src.poll()
    assert [e["message_id"] for e in out if e["type"] == "chat"] == ["dup"]
    assert [e["redemption_id"] for e in out if e["type"] == "redeem"] == ["rdup"]


def test_eventsub_source_subscribes_once_per_session(monkeypatch) -> None:
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    ws = _FakeWSClient([_welcome("s"), _chat_notification("c1")])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="cid",
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=lambda url: ws, helix_factory=lambda: helix,
    )
    src.poll()
    # A second welcome on the SAME live client must not re-subscribe.
    ws.feed(_welcome("s"), _chat_notification("c2"))
    src.poll()
    assert len(helix.chat_subs) == 1


def test_eventsub_source_reconnect_resubscribes(monkeypatch) -> None:
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    first = _FakeWSClient([_welcome("sess-A"), _chat_notification("a1")])
    second = _FakeWSClient([_welcome("sess-B"), _chat_notification("b1")])
    made = []

    def connect(url):
        made.append(url)
        # The first connect returns `first`; after a close the source reconnects
        # to the SAME _url (no reconnect message here) -> hand out `second`.
        return first if len(made) == 1 else second

    ws_close_msg = "__CLOSE__"
    first.feed(ws_close_msg)  # after a1, the socket closes -> reconnect next poll

    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="cid",
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=connect, helix_factory=lambda: helix,
    )
    out1 = src.poll()  # welcome + a1, then close raises -> client reset
    assert [e["message_id"] for e in out1 if e["type"] == "chat"] == ["a1"]
    assert first.closed is True
    out2 = src.poll()  # reconnect -> welcome(sess-B) + b1, re-subscribe
    assert [e["message_id"] for e in out2 if e["type"] == "chat"] == ["b1"]
    # Re-subscribed against the NEW session id.
    assert [s[2] for s in helix.chat_subs] == ["sess-A", "sess-B"]


def test_eventsub_source_handles_session_reconnect_url(monkeypatch) -> None:
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    new_client = _FakeWSClient([_welcome("sess-new"), _chat_notification("n1")])
    dialed = []

    def connect(url):
        dialed.append(url)
        if url == "wss://test/ws":
            return _FakeWSClient(
                [
                    _welcome("sess-old"),
                    {
                        "metadata": {"message_type": "session_reconnect"},
                        "payload": {"session": {"id": "sess-old",
                                                "reconnect_url": "wss://test/ws?new"}},
                    },
                ]
            )
        return new_client

    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="cid",
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=connect, helix_factory=lambda: helix,
    )
    src.poll()  # welcome(old) -> subscribe; reconnect -> dial new url
    out = src.poll()  # new client: welcome(new) -> re-subscribe + n1
    assert [e["message_id"] for e in out if e["type"] == "chat"] == ["n1"]
    assert "wss://test/ws?new" in dialed
    assert [s[2] for s in helix.chat_subs] == ["sess-old", "sess-new"]


def test_eventsub_source_no_client_id_never_subscribes(monkeypatch) -> None:
    # No client id -> connects but NEVER subscribes (the flag-off/no-creds path).
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    ws = _FakeWSClient([_welcome("s"), _chat_notification("c1")])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="",  # <- no creds
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=lambda url: ws, helix_factory=lambda: helix,
    )
    out = src.poll()
    # Chat notifications still parse (if Twitch sent any), but NO subscription was
    # created -> in practice Twitch sends none; the contract we assert is "never
    # subscribes without a client id".
    assert helix.chat_subs == []
    assert helix.redeem_subs == []
    # The welcome is consumed without error; any chat in the queue is still mapped
    # (harmless), proving the no-creds path does not crash.
    assert all(e["type"] in ("chat", "redeem") for e in out)


def test_eventsub_source_poll_never_raises(monkeypatch) -> None:
    # A WS client whose recv_json_ready raises a non-close error must be swallowed
    # and the client reset (fail-quiet).
    _patch_tokens(monkeypatch)

    class _Exploding:
        def __init__(self):
            self.closed = False

        def recv_json_ready(self, timeout):
            raise RuntimeError("kaboom")

        def close(self):
            self.closed = True

    exploding = _Exploding()
    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="cid",
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=lambda url: exploding, helix_factory=lambda: _FakeHelix(),
    )
    assert src.poll() == []  # swallowed
    assert exploding.closed is True  # reset for next poll


def test_eventsub_source_carries_native_message_type(monkeypatch) -> None:
    """2026-07-09: the EventSub message_type survives the flat-dict boundary —
    a user_intro (Twitch's native introduce-yourself class) is visible to
    main-process consumers instead of being dropped at the sidecar."""
    _patch_tokens(monkeypatch)
    notif = _chat_notification("c2", "newbie", "hi everyone")
    notif["payload"]["event"]["message"]["message_type"] = "user_intro"
    ws = _FakeWSClient([_welcome("sess-1"), notif])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws",
        client_id="cid",
        broadcaster_login="streamer",
        bot_login="ultronbot",
        connect_factory=lambda url: ws,
        helix_factory=lambda: _FakeHelix(),
    )
    chats = [e for e in src.poll() if e["type"] == "chat"]
    assert len(chats) == 1
    assert chats[0]["message_type"] == "user_intro"
    assert chats[0]["broadcaster_user_id"] == "B-100"


def test_eventsub_source_forwards_reply_parent_and_fragments(monkeypatch) -> None:
    """2026-07-11: the reply relationship + typed mention fragments survive the
    flat-dict boundary (both were parsed by from_eventsub then DROPPED here, so
    the addressing classifier could not tell a reply-to-Ultron from a reply-to-
    another-chatter -> the live over-addressing on quoted replies)."""
    _patch_tokens(monkeypatch)
    notif = _chat_notification("c3", "replier", "is that even true")
    notif["payload"]["event"]["reply"] = {"parent_user_id": "P-42"}
    notif["payload"]["event"]["message"]["fragments"] = [
        {"type": "mention", "text": "@ultronbot",
         "mention": {"user_id": "U-200", "user_login": "ultronbot"}},
    ]
    ws = _FakeWSClient([_welcome("sess-1"), notif])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws",
        client_id="cid",
        broadcaster_login="streamer",
        bot_login="ultronbot",
        connect_factory=lambda url: ws,
        helix_factory=lambda: _FakeHelix(),
    )
    chats = [e for e in src.poll() if e["type"] == "chat"]
    assert len(chats) == 1
    assert chats[0]["reply_parent_user_id"] == "P-42"
    assert chats[0]["fragments"] and chats[0]["fragments"][0]["type"] == "mention"


def _clear_notification(target_login: str = "spambot", target_id: str = "S-666") -> dict:
    return {
        "metadata": {"message_type": "notification",
                     "subscription_type": "channel.chat.clear_user_messages"},
        "payload": {
            "subscription": {"type": "channel.chat.clear_user_messages"},
            "event": {
                "broadcaster_user_id": "B-100",
                "target_user_id": target_id,
                "target_user_login": target_login,
                "target_user_name": target_login.title(),
            },
        },
    }


def test_eventsub_source_subscribes_chat_clear(monkeypatch) -> None:
    """2026-07-10: the ban-signal sub (channel.chat.clear_user_messages) rides
    the SAME bot session/token as the chat sub — no new scope."""
    _patch_tokens(monkeypatch)
    helix = _FakeHelix()
    ws = _FakeWSClient([_welcome("sess-1")])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="cid",
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=lambda url: ws, helix_factory=lambda: helix,
    )
    src.poll()
    assert helix.clear_subs == [
        ("B-100", "U-200", "sess-1", "tok-~/.kenning/twitch_bot.json")]


def test_eventsub_maps_chat_clear_user(monkeypatch) -> None:
    """A clear-user notification becomes a flat ban signal the main process
    can consume (the welcome ban-guard)."""
    _patch_tokens(monkeypatch)
    ws = _FakeWSClient([_welcome("sess-1"),
                        _clear_notification("AdBot9000", "S-1")])
    src = sidecar.EventSubChatSource(
        url="wss://test/ws", client_id="cid",
        broadcaster_login="streamer", bot_login="ultronbot",
        connect_factory=lambda url: ws, helix_factory=lambda: _FakeHelix(),
    )
    out = src.poll()
    clears = [e for e in out if e["type"] == "chat_clear_user"]
    assert clears == [{"type": "chat_clear_user",
                       "target_login": "adbot9000",   # canonicalized lower
                       "target_user_id": "S-1"}]
