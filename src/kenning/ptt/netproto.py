"""Wire protocol for the REMOTE push-to-talk hop (two-PC setup).

Read the anticheat boundary in :mod:`kenning.ptt` before touching this file.

Topology this exists for: Ultron runs on the AI/stream PC, while Valorant *and*
the USB-HID PTT microcontroller live on a second PC, the two joined by a LAN.
The relay audio already crosses via VBAN; only the key assertion needs a hop.
This module carries the EXISTING one-byte device protocol (``D``/``U``/``H``,
see :mod:`kenning.ptt.backends`) over one UDP datagram per command, so the host
side of the boundary is unchanged: bytes go to a peripheral, the peripheral
presses a real USB key. Nothing here performs synthetic input, and the agent on
the game PC can assert exactly ONE key -- the one compiled into the firmware --
so even a fully compromised token cannot type arbitrary input.

WHY UDP (and why loss is safe here). The firmware makes every command
idempotent and self-healing, so reliable delivery buys nothing worth its
latency and reconnect state:

  * a lost ``D`` is recovered by the very next heartbeat -- the firmware does
    ``if (cmd == 'H') { if (!holding) pressKey(); }`` -- so at most one
    heartbeat interval (50 ms) of extra lead;
  * a lost ``U`` is recovered by the 200 ms hardware deadman, because the
    heartbeats stop too. A network partition mid-hold therefore FAILS SAFE
    (mic closes) rather than jamming the channel open.

Frame (30 bytes, fixed)::

    MAGIC(5) | counter(8, big-endian) | cmd(1) | mac(16)

``mac`` is HMAC-SHA256 over ``MAGIC || counter || cmd`` under the shared token,
truncated to 16 bytes and compared with :func:`hmac.compare_digest`. The token
authenticates the LAN peer; ``counter`` must strictly increase, so a passive
sniffer cannot replay a captured ``D`` later to open the mic. Clients derive it
from ``time.time_ns()`` so it keeps increasing across client restarts.
"""

from __future__ import annotations

import hmac
import struct
from hashlib import sha256

MAGIC = b"KPTT1"
MAC_LEN = 16
_HEADER = struct.Struct(">5sQc")
FRAME_LEN = _HEADER.size + MAC_LEN

# Commands carried on the wire. D/U/H are the device protocol verbatim
# (kenning.ptt.backends.CMD_*); PING/PONG exist only so the client can report
# at boot whether the remote agent is actually reachable -- without it a
# misconfigured host would look "enabled" while silently never keying the mic.
CMD_DOWN = b"D"
CMD_UP = b"U"
CMD_HEARTBEAT = b"H"
CMD_PING = b"P"
CMD_PONG = b"O"

_VALID_COMMANDS = frozenset({CMD_DOWN, CMD_UP, CMD_HEARTBEAT, CMD_PING, CMD_PONG})


class ProtocolError(ValueError):
    """A datagram was malformed, unauthenticated, or replayed."""


def _token_bytes(token: str | bytes) -> bytes:
    if isinstance(token, str):
        token = token.encode("utf-8")
    if not token:
        raise ValueError("ptt netproto: token must not be empty")
    return token


def build_frame(counter: int, cmd: bytes, token: str | bytes) -> bytes:
    """Serialise one authenticated command datagram.

    Raises ``ValueError`` on an unknown command, an out-of-range counter, or an
    empty token -- all programming errors, surfaced loudly rather than sent as
    a frame the peer would silently drop.
    """
    if cmd not in _VALID_COMMANDS:
        raise ValueError(f"ptt netproto: unknown command {cmd!r}")
    if not 0 <= counter <= 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError(f"ptt netproto: counter out of range: {counter}")
    head = _HEADER.pack(MAGIC, counter, cmd)
    mac = hmac.new(_token_bytes(token), head, sha256).digest()[:MAC_LEN]
    return head + mac


def parse_frame(
    datagram: bytes,
    token: str | bytes,
    *,
    min_counter: int = 0,
) -> tuple[int, bytes]:
    """Authenticate and decode one datagram -> ``(counter, cmd)``.

    ``min_counter`` is the highest counter already accepted from this peer;
    anything at or below it is rejected as a replay. Every rejection raises
    :class:`ProtocolError` -- the caller drops the datagram and keeps serving,
    so a hostile or corrupt packet can never take the agent down.
    """
    if len(datagram) != FRAME_LEN:
        raise ProtocolError(f"bad length {len(datagram)} (want {FRAME_LEN})")
    head, mac = datagram[: _HEADER.size], datagram[_HEADER.size :]
    magic, counter, cmd = _HEADER.unpack(head)
    if magic != MAGIC:
        raise ProtocolError(f"bad magic {magic!r}")
    expected = hmac.new(_token_bytes(token), head, sha256).digest()[:MAC_LEN]
    # Constant-time: never leak how much of the MAC matched.
    if not hmac.compare_digest(mac, expected):
        raise ProtocolError("bad authentication tag")
    # Authenticate BEFORE trusting any field, so replay/command checks can
    # never be driven by an unauthenticated packet.
    if cmd not in _VALID_COMMANDS:
        raise ProtocolError(f"unknown command {cmd!r}")
    if counter <= min_counter:
        raise ProtocolError(f"replayed counter {counter} <= {min_counter}")
    return counter, cmd
