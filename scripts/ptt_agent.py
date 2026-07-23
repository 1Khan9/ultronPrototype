"""Remote push-to-talk agent -- runs on the GAME PC in a two-PC Ultron setup.

Topology this serves: Ultron runs on the AI/stream PC; Valorant, Vanguard and
the USB-HID PTT microcontroller live on THIS machine, joined by a LAN. The relay
audio already crosses via VBAN; this agent carries the key assertion. Ultron
sends the existing one-byte device protocol (``D``/``U``/``H``) as authenticated
UDP datagrams; this process writes them to the local HID device, which presses a
real USB key.

ANTICHEAT POSTURE (read ``src/kenning/ptt/__init__.py`` first). This process does
strictly LESS on the game PC than the full Ultron that used to run here:

  * it writes HID OUTPUT REPORTS to a peripheral -- device I/O, not synthetic
    input. No SendInput/keybd_event/pyautogui/pynput/keyboard/interception, not
    even as a fallback: if the device is missing, PTT simply does not fire;
  * it imports ONLY stdlib + hidapi. It deliberately does NOT import the
    ``kenning`` package (whose ``__init__`` pulls torch in for CUDA DLL
    discovery) -- the two leaf modules are loaded by file path instead, so the
    device protocol still has exactly one implementation;
  * it reads nothing about the game: no screen capture, no process/memory
    inspection, no input hooks. It is a socket and a serial-shaped write.

CONTAINMENT. The only capability exposed on the network is "toggle the one key
compiled into the firmware". Even a fully compromised token cannot type
arbitrary input, read anything, or run anything. Datagrams are authenticated
with HMAC-SHA256 under a shared token and replay-guarded by a strictly
increasing counter; unauthenticated packets are counted and dropped.

Usage on the game PC (PowerShell)::

    $env:KENNING_PTT_NETWORK_TOKEN = "<the same secret Ultron uses>"
    python scripts\\ptt_agent.py --bind 0.0.0.0 --port 8778 --allow-peer 192.168.1.50

Then on the Ultron PC set ``push_to_talk.backend: "network"`` +
``network_host: "<this PC's LAN IP>"`` and export the same token.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger("ptt_agent")

# Belt-and-braces above the 200 ms FIRMWARE deadman: if the stream of commands
# stops while the key is held (Ultron crashed, cable pulled, LAN died), release
# locally too rather than trusting a single layer. Must exceed the client's
# heartbeat cadence (50 ms) with margin.
DEFAULT_WATCHDOG_MS = 250


def _load_leaf_module(name: str, path: Path):
    """Import a single module BY PATH, without importing its parent package.

    ``kenning/__init__.py`` pulls torch in for CUDA DLL discovery, which this
    agent must not carry onto the game PC. ``netproto`` and ``backends`` are
    leaves (stdlib-only imports), so loading them directly is safe and keeps
    the wire + device protocol single-sourced with the Ultron side.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so a module referencing its own name still resolves.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_PTT_DIR = Path(__file__).resolve().parent.parent / "src" / "kenning" / "ptt"


class PttAgent:
    """UDP server: authenticated D/U/H -> local HID device."""

    def __init__(
        self,
        backend,
        netproto,
        token: str,
        *,
        allow_peers: frozenset[str] = frozenset(),
        watchdog_ms: int = DEFAULT_WATCHDOG_MS,
    ) -> None:
        self._backend = backend
        self._np = netproto
        self._token = token
        self._allow = allow_peers
        self._watchdog_s = max(watchdog_ms, 1) / 1000.0
        self._lock = threading.Lock()
        self._holding = False
        self._last_cmd_at = 0.0
        self._counters: dict[str, int] = {}
        self._rejected = 0
        self._stop = threading.Event()

    # -- command handling -------------------------------------------------
    def _apply(self, cmd: bytes) -> None:
        """Drive the device. Every call is fail-safe inside the backend."""
        if cmd == self._np.CMD_DOWN:
            self._backend.press()
            with self._lock:
                self._holding = True
        elif cmd == self._np.CMD_UP:
            self._backend.release()
            with self._lock:
                self._holding = False
        elif cmd == self._np.CMD_HEARTBEAT:
            self._backend.heartbeat()
            # The firmware recovers a missed DOWN on a heartbeat; mirror that
            # here so the local watchdog agrees with the device's real state.
            with self._lock:
                self._holding = True
        with self._lock:
            self._last_cmd_at = time.monotonic()

    def _watchdog(self) -> None:
        """Release locally if the command stream dies mid-hold."""
        while not self._stop.wait(self._watchdog_s / 2.0):
            with self._lock:
                stale = (
                    self._holding
                    and (time.monotonic() - self._last_cmd_at) > self._watchdog_s
                )
            if stale:
                logger.warning(
                    "watchdog: no command for >%dms while holding -- releasing "
                    "(client or link died)", int(self._watchdog_s * 1000),
                )
                try:
                    self._backend.release()
                except Exception as e:  # noqa: BLE001 - never kill the watchdog
                    logger.warning("watchdog release failed: %s", e)
                with self._lock:
                    self._holding = False

    # -- server -----------------------------------------------------------
    def serve(self, bind: str, port: int) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((bind, port))
        except OSError as e:
            logger.error("cannot bind %s:%d -- %s", bind, port, e)
            return 2
        sock.settimeout(0.5)
        wd = threading.Thread(target=self._watchdog, name="ptt-watchdog", daemon=True)
        wd.start()
        logger.info(
            "PTT agent listening on %s:%d (peers=%s, watchdog=%dms)",
            bind, port, ", ".join(sorted(self._allow)) or "any",
            int(self._watchdog_s * 1000),
        )
        try:
            while not self._stop.is_set():
                try:
                    data, peer = sock.recvfrom(self._np.FRAME_LEN + 64)
                except TimeoutError:
                    continue
                except OSError as e:
                    if self._stop.is_set():
                        break
                    logger.warning("recv failed: %s", e)
                    continue
                self._handle(sock, data, peer)
        except KeyboardInterrupt:
            logger.info("interrupted")
        finally:
            self._stop.set()
            # Never leave the far-side mic held open on shutdown.
            try:
                self._backend.release()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._backend.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass
            logger.info("PTT agent stopped (%d datagram(s) rejected)", self._rejected)
        return 0

    def _handle(self, sock, data: bytes, peer) -> None:
        host = peer[0]
        if self._allow and host not in self._allow:
            self._rejected += 1
            logger.warning("dropped datagram from unlisted peer %s", host)
            return
        try:
            counter, cmd = self._np.parse_frame(
                data, self._token, min_counter=self._counters.get(host, 0),
            )
        except Exception as e:  # noqa: BLE001 - a bad packet must never stop us
            self._rejected += 1
            logger.warning("rejected datagram from %s: %s", host, e)
            return
        self._counters[host] = counter
        if cmd == self._np.CMD_PING:
            try:
                sock.sendto(
                    self._np.build_frame(counter, self._np.CMD_PONG, self._token),
                    peer,
                )
            except OSError as e:
                logger.warning("pong to %s failed: %s", host, e)
            return
        if cmd == self._np.CMD_PONG:
            return  # we never initiate a ping; ignore stray replies
        self._apply(cmd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Remote PTT agent (game PC side)")
    ap.add_argument("--bind", default="0.0.0.0",
                    help="interface to listen on (default: all)")
    ap.add_argument("--port", type=int, default=8778)
    ap.add_argument("--token", default="",
                    help="shared secret; prefer env KENNING_PTT_NETWORK_TOKEN")
    ap.add_argument("--allow-peer", action="append", default=[],
                    metavar="IP",
                    help="only accept datagrams from this IP (repeatable). "
                         "Strongly recommended: pin it to the Ultron PC.")
    ap.add_argument("--vid", type=lambda s: int(s, 0), default=0x1209,
                    help="HID vendor id of the PTT device (default 0x1209)")
    ap.add_argument("--usage-page", type=lambda s: int(s, 0), default=0xFFC0,
                    help="vendor Raw-HID usage page (default 0xFFC0)")
    ap.add_argument("--watchdog-ms", type=int, default=DEFAULT_WATCHDOG_MS)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | ptt_agent | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    token = (os.environ.get("KENNING_PTT_NETWORK_TOKEN", "") or args.token).strip()
    if not token:
        logger.error(
            "no shared token -- refusing to start. Set KENNING_PTT_NETWORK_TOKEN "
            "(or --token) to the same secret the Ultron PC uses."
        )
        return 2
    if not args.allow_peer:
        logger.warning(
            "no --allow-peer given: ANY host on this network that knows the "
            "token can key the PTT. Pin it to the Ultron PC's IP."
        )

    try:
        netproto = _load_leaf_module("kptt_netproto", _PTT_DIR / "netproto.py")
        backends = _load_leaf_module("kptt_backends", _PTT_DIR / "backends.py")
    except Exception as e:  # noqa: BLE001
        logger.error("cannot load the PTT modules from %s: %s", _PTT_DIR, e)
        return 2

    backend = backends.RawHidPttBackend(args.vid, args.usage_page)
    if not backend.available:
        logger.error(
            "no PTT HID device found (vid=%#06x usage_page=%#06x) -- is the "
            "dongle plugged into THIS PC? Refusing to start rather than "
            "pretending to be armed.", args.vid, args.usage_page,
        )
        return 3

    agent = PttAgent(
        backend, netproto, token,
        allow_peers=frozenset(args.allow_peer),
        watchdog_ms=args.watchdog_ms,
    )

    def _shutdown(_signum, _frame):
        logger.info("signal received -- shutting down")
        agent._stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):  # not on the main thread / unsupported
            pass

    return agent.serve(args.bind, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
