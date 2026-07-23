"""Remote (two-PC) push-to-talk: wire protocol, client backend, agent, wiring.

Covers the 2026-07-23 machine-move feature: Valorant + the USB-HID PTT device
live on a second PC, so Ultron forwards the existing D/U/H device protocol over
authenticated UDP to ``scripts/ptt_agent.py``.

All hermetic -- no sockets are opened against the network, no HID device is
touched. The client's socket and the agent's backend are both injected.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from kenning.ptt import netproto
from kenning.ptt.backends import NetworkPttBackend, NullPttBackend
from kenning.ptt.controller import build_ptt_controller

TOKEN = "shared-lan-secret"

_AGENT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ptt_agent.py"


def _load_agent():
    """Load the agent script by path (it is a script, not an importable pkg)."""
    spec = importlib.util.spec_from_file_location("ptt_agent_under_test", _AGENT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSocket:
    """Records datagrams instead of sending them."""

    def __init__(self, reply: bytes | None = None) -> None:
        self.sent: list[tuple[bytes, tuple]] = []
        self._reply = reply
        self.closed = False

    def sendto(self, data, addr):
        self.sent.append((data, addr))
        return len(data)

    def recv(self, _n):
        if self._reply is None:
            raise TimeoutError("no reply")
        return self._reply

    def settimeout(self, _t):
        pass

    def close(self):
        self.closed = True


class _RecordingBackend:
    """Stands in for RawHidPttBackend on the agent side."""

    available = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    def press(self):
        self.calls.append("press")

    def release(self):
        self.calls.append("release")

    def heartbeat(self):
        self.calls.append("heartbeat")

    def close(self):
        self.calls.append("close")


# ---------------------------------------------------------------------------
# Wire protocol
# ---------------------------------------------------------------------------


def test_frame_roundtrip_preserves_counter_and_command():
    frame = netproto.build_frame(42, netproto.CMD_DOWN, TOKEN)
    assert len(frame) == netproto.FRAME_LEN
    assert netproto.parse_frame(frame, TOKEN, min_counter=41) == (42, netproto.CMD_DOWN)


def test_frame_under_a_different_token_is_rejected():
    """The LAN secret is what stops a stranger keying the streamer's mic."""
    frame = netproto.build_frame(7, netproto.CMD_DOWN, "attacker-guess")
    with pytest.raises(netproto.ProtocolError, match="authentication"):
        netproto.parse_frame(frame, TOKEN)


def test_replayed_counter_is_rejected():
    """A sniffed DOWN must not be replayable later to open the mic."""
    frame = netproto.build_frame(100, netproto.CMD_DOWN, TOKEN)
    assert netproto.parse_frame(frame, TOKEN, min_counter=99)
    with pytest.raises(netproto.ProtocolError, match="replay"):
        netproto.parse_frame(frame, TOKEN, min_counter=100)


@pytest.mark.parametrize(
    "corrupt",
    [b"", b"short", b"x" * (netproto.FRAME_LEN - 1), b"y" * (netproto.FRAME_LEN + 1)],
)
def test_malformed_datagrams_are_rejected_not_crashed(corrupt):
    with pytest.raises(netproto.ProtocolError):
        netproto.parse_frame(corrupt, TOKEN)


def test_bad_magic_is_rejected():
    frame = netproto.build_frame(5, netproto.CMD_UP, TOKEN)
    with pytest.raises(netproto.ProtocolError):
        netproto.parse_frame(b"XXXXX" + frame[5:], TOKEN)


def test_build_frame_refuses_unknown_command_and_empty_token():
    with pytest.raises(ValueError, match="unknown command"):
        netproto.build_frame(1, b"Z", TOKEN)
    with pytest.raises(ValueError, match="token"):
        netproto.build_frame(1, netproto.CMD_DOWN, "")


# ---------------------------------------------------------------------------
# Client backend
# ---------------------------------------------------------------------------


def _backend(reply=None, **kw):
    sock = _FakeSocket(reply)
    be = NetworkPttBackend("10.0.0.9", 8778, TOKEN, open_socket=lambda: sock, **kw)
    return be, sock


def test_press_release_heartbeat_emit_the_device_protocol():
    be, sock = _backend(probe=False)
    be.press()
    be.release()
    be.heartbeat()
    cmds = [netproto.parse_frame(d, TOKEN)[1] for d, _ in sock.sent]
    assert cmds == [netproto.CMD_DOWN, netproto.CMD_UP, netproto.CMD_HEARTBEAT]
    assert all(addr == ("10.0.0.9", 8778) for _, addr in sock.sent)


def test_counters_strictly_increase_so_the_agent_never_sees_a_replay():
    be, sock = _backend(probe=False)
    for _ in range(6):
        be.heartbeat()
    counters = [netproto.parse_frame(d, TOKEN)[0] for d, _ in sock.sent]
    assert counters == sorted(set(counters)), "counters must strictly increase"


def test_empty_token_refuses_to_arm():
    """Never send unauthenticated frames -- go inert instead."""
    be = NetworkPttBackend("10.0.0.9", 8778, "", open_socket=lambda: _FakeSocket())
    assert be.available is False


def test_send_failure_disables_the_backend_and_never_raises():
    """Same fail-safe contract as the HID backend."""

    class _Broken(_FakeSocket):
        def sendto(self, data, addr):
            raise OSError("network unreachable")

    sock = _Broken()
    be = NetworkPttBackend("10.0.0.9", 8778, TOKEN, open_socket=lambda: sock, probe=False)
    assert be.available is True
    be.press()  # must not raise
    assert be.available is False


def test_probe_marks_available_only_on_a_valid_pong():
    pong = netproto.build_frame(1, netproto.CMD_PONG, TOKEN)
    be, _ = _backend(reply=pong, probe=True)
    assert be.available is True


def test_probe_failure_leaves_backend_unavailable():
    """A typo'd host must NOT look armed -- that is the silent-failure trap."""
    be, _ = _backend(reply=None, probe=True)  # recv raises timeout
    assert be.available is False


def test_probe_rejects_a_pong_signed_with_the_wrong_token():
    be, _ = _backend(reply=netproto.build_frame(1, netproto.CMD_PONG, "wrong"), probe=True)
    assert be.available is False


def test_close_releases_before_dropping_the_socket():
    """Never leave the far-side mic held open on shutdown."""
    be, sock = _backend(probe=False)
    be.press()
    be.close()
    cmds = [netproto.parse_frame(d, TOKEN)[1] for d, _ in sock.sent]
    assert cmds[-1] == netproto.CMD_UP
    assert sock.closed is True
    assert be.available is False


# ---------------------------------------------------------------------------
# Agent (game-PC side)
# ---------------------------------------------------------------------------


def _agent(backend, **kw):
    mod = _load_agent()
    return mod.PttAgent(backend, netproto, TOKEN, **kw), mod


def test_agent_applies_commands_to_the_local_device():
    be = _RecordingBackend()
    agent, _ = _agent(be)
    sock = _FakeSocket()
    for cmd in (netproto.CMD_DOWN, netproto.CMD_HEARTBEAT, netproto.CMD_UP):
        agent._handle(sock, netproto.build_frame(_next(), cmd, TOKEN), ("10.0.0.5", 5))
    assert be.calls == ["press", "heartbeat", "release"]


def test_agent_answers_ping_with_an_authenticated_pong():
    agent, _ = _agent(_RecordingBackend())
    sock = _FakeSocket()
    agent._handle(sock, netproto.build_frame(_next(), netproto.CMD_PING, TOKEN), ("10.0.0.5", 5))
    assert len(sock.sent) == 1
    _, cmd = netproto.parse_frame(sock.sent[0][0], TOKEN)
    assert cmd == netproto.CMD_PONG


def test_agent_drops_unauthenticated_datagrams_without_touching_the_device():
    be = _RecordingBackend()
    agent, _ = _agent(be)
    agent._handle(_FakeSocket(), netproto.build_frame(_next(), netproto.CMD_DOWN, "attacker"), ("10.0.0.5", 5))
    assert be.calls == [], "an unauthenticated packet must never press the key"
    assert agent._rejected == 1


def test_agent_drops_datagrams_from_unlisted_peers():
    be = _RecordingBackend()
    agent, _ = _agent(be, allow_peers=frozenset({"10.0.0.5"}))
    agent._handle(_FakeSocket(), netproto.build_frame(_next(), netproto.CMD_DOWN, TOKEN), ("10.0.0.99", 5))
    assert be.calls == []
    assert agent._rejected == 1


def test_agent_rejects_a_replayed_datagram():
    be = _RecordingBackend()
    agent, _ = _agent(be)
    frame = netproto.build_frame(_next(), netproto.CMD_DOWN, TOKEN)
    agent._handle(_FakeSocket(), frame, ("10.0.0.5", 5))
    agent._handle(_FakeSocket(), frame, ("10.0.0.5", 5))  # same frame again
    assert be.calls == ["press"], "replay must not re-press"
    assert agent._rejected == 1


_counter = [0]


def _next() -> int:
    _counter[0] += 1
    return _counter[0]


# ---------------------------------------------------------------------------
# Controller wiring
# ---------------------------------------------------------------------------


class _Cfg:
    def __init__(self, **kw):
        self.enabled = True
        self.backend = "network"
        self.network_host = "10.0.0.9"
        self.network_port = 8778
        self.network_token = TOKEN
        self.network_probe_timeout = 0.1
        self.heartbeat_ms = 50
        self.release_tail_ms = 300
        self.lead_ms = 80
        self.release_jitter_ms = 0
        self.max_hold_seconds = 8.0
        self.__dict__.update(kw)


def test_network_backend_without_a_host_stays_inert(monkeypatch):
    """An unconfigured remote host must be a no-op, never a half-armed PTT."""
    monkeypatch.delenv("KENNING_PTT_NETWORK_TOKEN", raising=False)
    cfg = type("C", (), {"push_to_talk": _Cfg(network_host="")})()
    ctl = build_ptt_controller(cfg)
    assert isinstance(ctl._backend, NullPttBackend)
    assert ctl.available is False


def test_auto_backend_never_silently_picks_the_network_hop(monkeypatch):
    """A remote hop is an explicit topology choice, not an 'auto' fallback."""
    monkeypatch.delenv("KENNING_PTT_NETWORK_TOKEN", raising=False)
    import kenning.ptt.controller as ctl_mod

    monkeypatch.setattr(ctl_mod, "RawHidPttBackend", lambda *a, **k: NullPttBackend())
    monkeypatch.setattr(ctl_mod, "find_arduino_port", lambda *a, **k: None)
    cfg = type("C", (), {"push_to_talk": _Cfg(backend="auto")})()
    ctl = build_ptt_controller(cfg)
    assert isinstance(ctl._backend, NullPttBackend)


def test_env_token_overrides_config_token(monkeypatch):
    """Secrets come from the env first (settings.py convention)."""
    monkeypatch.setenv("KENNING_PTT_NETWORK_TOKEN", "env-wins")
    captured = {}

    import kenning.ptt.controller as ctl_mod

    class _Spy(NullPttBackend):
        def __init__(self, host, port, token, **kw):
            captured["token"] = token
            super().__init__()

    monkeypatch.setattr(ctl_mod, "NetworkPttBackend", _Spy)
    cfg = type("C", (), {"push_to_talk": _Cfg()})()
    build_ptt_controller(cfg)
    assert captured["token"] == "env-wins"
