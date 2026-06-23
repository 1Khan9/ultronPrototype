"""S12 — channel-point REDEEM ROUTER (redeem -> game -> announce + overlay).

The read sidecar (``scripts/twitch_read_sidecar.py``) subscribes to channel-point
redemptions and buffers them as ``{"type":"redeem",...}`` events alongside the
``{"type":"chat",...}`` chat events, each wrapped as ``{"seq","ts","event":{...}}``
in the rolling buffer (drained over loopback via ``GET /buffer?since=N``). This
module is the SECOND, independent consumer of that same buffer: it tracks its OWN
in-memory cursor and NEVER POSTs ``/ack`` (mirroring
``kenning.twitch.service.make_read_drain_fn``), so it can read the very same buffer
the chat-mode drain reads without either consumer stealing the other's events.

When a redeemed reward's title maps to a game (spin the wheel / slots / heist /
duel / trivia / raffle) the router RUNS that game from a freshly-minted
provably-fair round and surfaces the outcome two ways:

  * ``announce_fn(line)``     -- a short in-character spoken line (the orchestrator
                                 passes its Kokoro TTS speak), and
  * ``overlay_emit(event)``   -- a JSON-serializable overlay event the dumb overlay
                                 renderer shows.

ANTICHEAT (BR-P1): stdlib only (``json`` / ``urllib`` / ``logging`` / ``threading``
/ ``collections`` / ``dataclasses`` / ``typing``) + ``kenning.twitch.economy.*``.
The ONLY network is :func:`make_redeem_drain_fn`'s loopback ``urllib`` GET against
the local read sidecar -- the same class as the existing chat drain. No
``requests`` / ``aiohttp`` / ``websockets`` / model libs ever load here.

Everything is fail-safe: a drain error skips the tick (returns ``[]``); a single
bad redeem is logged and skipped without breaking the rest of the tick; a game
that raises is caught and that one redeem is dropped. Outcomes are deterministic
for a given injected RNG.
"""
from __future__ import annotations

import json
import logging
import threading
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from kenning.twitch.economy.games import (
    Duel,
    Heist,
    Raffle,
    Slots,
    SpinTheWheel,
    Trivia,
    WheelSegment,
)
from kenning.twitch.economy.rng import ProvablyFairRNG

logger = logging.getLogger("kenning.twitch.redeem_router")

__all__ = [
    "make_redeem_drain_fn",
    "DEFAULT_REWARD_MAP",
    "RedeemRouter",
]


# --------------------------------------------------------------------------- #
# Reward-title -> game action map
# --------------------------------------------------------------------------- #
# Lowercased reward titles -> a game action key. The router lowercases + strips
# the incoming reward title before lookup, so the keys here are all lowercase.
DEFAULT_REWARD_MAP: dict[str, str] = {
    "spin the wheel": "wheel",
    "spin": "wheel",
    "wheel": "wheel",
    "slots": "slots",
    "slot machine": "slots",
    "heist": "heist",
    "duel": "duel",
    "trivia": "trivia",
    "raffle": "raffle",
}


# --------------------------------------------------------------------------- #
# Independent redeem drain (own cursor, never acks)
# --------------------------------------------------------------------------- #
def make_redeem_drain_fn(
    read_endpoint: str,
    *,
    timeout: float = 1.0,
    http_get: Callable[[str, float], bytes] | None = None,
) -> Callable[[], list[dict]]:
    """Build a drain callable that pulls NEW redeem events from the read sidecar.

    GETs ``{read_endpoint}/buffer?since=<own cursor>``, advances its OWN in-memory
    cursor from the returned ``cursor`` (NEVER POSTs ``/ack`` -- so this second
    consumer never steals events from the chat-mode drain), unwraps each
    ``{"seq","ts","event":{...}}`` wrapper and returns ONLY the inner event dicts
    whose ``"type" == "redeem"``.

    Fail-safe: any error (sidecar down, bad JSON, hostile body) returns ``[]`` so
    the caller simply skips the tick.

    :param read_endpoint: base URL of the read sidecar (e.g. ``http://127.0.0.1:8773``).
    :param timeout: per-request urllib timeout in seconds.
    :param http_get: optional injected transport ``(url, timeout) -> bytes`` for
        offline testing; defaults to a loopback ``urllib`` GET.
    """
    base = read_endpoint.rstrip("/")
    cursor = {"v": 0}

    def _urllib_get(url: str, to: float) -> bytes:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=to) as r:  # nosec B310 - loopback only
            return r.read() or b"{}"

    fetch = http_get if http_get is not None else _urllib_get

    def drain() -> list[dict]:
        try:
            raw = fetch(f"{base}/buffer?since={cursor['v']}", timeout)
            data = json.loads(raw or b"{}")
        except Exception as exc:  # noqa: BLE001 — sidecar down / bad body -> skip tick
            logger.debug("redeem-sidecar drain failed: %s", exc)
            return []
        if not isinstance(data, dict):
            return []
        try:
            cursor["v"] = int(data.get("cursor", cursor["v"]) or cursor["v"])
        except (TypeError, ValueError):
            pass
        out: list[dict] = []
        for wrapped in data.get("events", []) or []:
            try:
                if not isinstance(wrapped, dict):
                    continue
                event = wrapped.get("event")
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "redeem":
                    out.append(event)
            except Exception:  # noqa: BLE001 — skip a malformed wrapper, never crash
                continue
        return out

    return drain


# --------------------------------------------------------------------------- #
# Default game-segment libraries
# --------------------------------------------------------------------------- #
def _default_wheel_segments() -> list[WheelSegment]:
    """Six fun, all-positive wheel segments (no LOSE_ALL -> safe by default)."""
    return [
        WheelSegment("DOUBLE", weight=1.0, payout=200),
        WheelSegment("TRIPLE", weight=0.5, payout=300),
        WheelSegment("NOTHING", weight=2.0, payout=0),
        WheelSegment("SMALL WIN", weight=2.0, payout=50),
        WheelSegment("JACKPOT", weight=0.25, payout=1000),
        WheelSegment("REFUND", weight=1.5, payout=100),
    ]


_DEFAULT_SLOT_SYMBOLS = ("cherry", "lemon", "bell", "star", "seven", "skull")


# --------------------------------------------------------------------------- #
# Bounded LRU dedup set (redemption_id -> seen)
# --------------------------------------------------------------------------- #
class _LRUSet:
    """A bounded, insertion-ordered set used for redemption_id dedup.

    ``add`` returns True the FIRST time an id is seen and False thereafter; the
    oldest ids are evicted once ``maxlen`` is exceeded. Thread-safe so ``tick``
    can be called from a background loop while another caller introspects."""

    def __init__(self, maxlen: int) -> None:
        self._maxlen = max(1, int(maxlen))
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, key: str) -> bool:
        with self._lock:
            if key in self._seen:
                self._seen.move_to_end(key)
                return False
            self._seen[key] = None
            if len(self._seen) > self._maxlen:
                self._seen.popitem(last=False)
            return True

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._seen

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)


# --------------------------------------------------------------------------- #
# The router
# --------------------------------------------------------------------------- #
class RedeemRouter:
    """Drain redeem events, run the mapped game, announce + emit the outcome.

    Construct ONE at boot (the orchestrator wires ``announce_fn`` to its TTS speak
    and ``overlay_emit`` to the overlay sidecar publish), then call :meth:`tick`
    from the idle/background loop alongside the chat-mode tick. ``tick`` is fully
    fail-safe; it never raises into the loop.
    """

    def __init__(
        self,
        drain_fn: Callable[[], list[dict]],
        *,
        rng: ProvablyFairRNG | None = None,
        reward_map: dict[str, str] | None = None,
        announce_fn: Callable[[str], Any] | None = None,
        overlay_emit: Callable[[dict], Any] | None = None,
        games: dict[str, Any] | None = None,
        dedup_max: int = 2048,
    ) -> None:
        self._drain = drain_fn
        self._rng = rng if rng is not None else ProvablyFairRNG()
        # Lowercase the reward map keys defensively (callers may pass mixed case).
        rmap = reward_map if reward_map is not None else DEFAULT_REWARD_MAP
        self._reward_map = {str(k).strip().lower(): str(v) for k, v in rmap.items()}
        self._announce = announce_fn
        self._overlay = overlay_emit
        self._games: dict[str, Any] = dict(games) if games else {}
        self._dedup = _LRUSet(dedup_max)
        # Per-action nonce so every redeem of the same game advances the round
        # (still deterministic for a fixed rng + sequence).
        self._nonce: dict[str, int] = {}

    # -- game accessors (lazy defaults) ---------------------------------- #
    def _next_nonce(self, action: str) -> int:
        n = self._nonce.get(action, 0)
        self._nonce[action] = n + 1
        return n

    def _wheel(self) -> SpinTheWheel:
        g = self._games.get("wheel")
        if g is None:
            g = SpinTheWheel(_default_wheel_segments(), rng=self._rng)
            self._games["wheel"] = g
        return g

    def _slots(self) -> Slots:
        g = self._games.get("slots")
        if g is None:
            g = Slots(_DEFAULT_SLOT_SYMBOLS, reels=3, rng=self._rng)
            self._games["slots"] = g
        return g

    def _heist(self) -> Heist:
        g = self._games.get("heist")
        if g is None:
            g = Heist(rng=self._rng)
            self._games["heist"] = g
        return g

    def _duel(self) -> Duel:
        g = self._games.get("duel")
        if g is None:
            g = Duel(rng=self._rng)
            self._games["duel"] = g
        return g

    def _trivia(self) -> Trivia:
        g = self._games.get("trivia")
        if g is None:
            g = Trivia(rng=self._rng)
            self._games["trivia"] = g
        return g

    def _raffle(self) -> Raffle:
        g = self._games.get("raffle")
        if g is None:
            g = Raffle(rng=self._rng)
            self._games["raffle"] = g
        return g

    # -- public tick ----------------------------------------------------- #
    def tick(self) -> list[dict]:
        """Drain + process every NEW redeem this cycle. Returns the list of
        outcome dicts processed (for tests + logging). Fail-safe end-to-end."""
        try:
            events = self._drain()
        except Exception as exc:  # noqa: BLE001 — drain must never crash the loop
            logger.warning("redeem drain raised: %s", exc)
            return []
        if not events:
            return []
        outcomes: list[dict] = []
        for ev in events:
            try:
                outcome = self._process_one(ev)
            except Exception as exc:  # noqa: BLE001 — one bad redeem never breaks the tick
                logger.warning(
                    "redeem processing failed redemption_id=%r: %s",
                    (ev or {}).get("redemption_id") if isinstance(ev, dict) else None,
                    exc,
                )
                continue
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    # -- per-redeem -------------------------------------------------------- #
    def _process_one(self, ev: dict) -> dict | None:
        if not isinstance(ev, dict):
            return None
        redemption_id = str(ev.get("redemption_id") or "")
        # Dedup on the redemption id (bounded LRU). A redeem with no id is still
        # processed (the sidecar always supplies one for a real redemption; a
        # missing id just bypasses dedup rather than blocking the game).
        if redemption_id and not self._dedup.add(redemption_id):
            logger.debug("redeem dedup skip redemption_id=%s", redemption_id)
            return None

        title = str(ev.get("reward_title") or "")
        viewer = str(ev.get("chatter_login") or ev.get("chatter_name") or "")
        user_input = str(ev.get("user_input") or "")
        action = self._reward_map.get(title.strip().lower())

        if action is None:
            # Not a game reward -> still emit a generic overlay event so the
            # overlay can show the redemption; no game, no spoken line.
            generic = {"type": "redeem", "reward": title, "viewer": viewer}
            self._emit(generic)
            logger.info("redeem (non-game) reward=%r viewer=%r", title, viewer)
            return None

        runner = self._RUNNERS.get(action)
        if runner is None:
            # A mapped action with no runner (a misconfigured map) -> treat as a
            # generic redeem rather than crashing.
            generic = {"type": "redeem", "reward": title, "viewer": viewer}
            self._emit(generic)
            logger.warning("redeem action %r has no runner; emitted generic", action)
            return None

        line, event = runner(self, viewer or "someone", user_input, redemption_id)
        if line:
            self._announce_safe(line)
        self._emit(event)
        logger.info(
            "redeem game=%s viewer=%r outcome=%r", action, viewer, event.get("outcome")
        )
        return event

    # -- per-game runners ------------------------------------------------- #
    # Each runner returns (spoken_line, overlay_event). The overlay event shape is
    # {"type":"redeem_result","game":<action>,"viewer":<login>,"outcome":<label>,
    #  "detail":{...provably-fair provenance + game specifics...}}.
    def _round(self) -> Any:
        """Mint a fresh provably-fair round (server_seed + commit)."""
        return self._rng.new_round()

    def _run_wheel(self, viewer: str, user_input: str, rid: str) -> tuple[str, dict]:
        rnd = self._round()
        nonce = self._next_nonce("wheel")
        res = self._wheel().spin(rnd.server_seed, nonce=nonce)
        label = res.segment.label
        line = f"Wheel landed on {label} for {viewer}."
        event = {
            "type": "redeem_result",
            "game": "wheel",
            "viewer": viewer,
            "outcome": label,
            "detail": {
                "index": res.index,
                "payout": res.segment.payout,
                "target_angle": res.target_angle,
                "commit": rnd.commit,
                "server_seed": rnd.server_seed,
                "nonce": nonce,
            },
        }
        return line, event

    def _run_slots(self, viewer: str, user_input: str, rid: str) -> tuple[str, dict]:
        rnd = self._round()
        nonce = self._next_nonce("slots")
        res = self._slots().pull(rnd.server_seed, nonce=nonce)
        reels = " | ".join(res.reels)
        if res.is_win:
            line = f"Slots hit triple {res.win_symbol} for {viewer}. Jackpot."
            outcome = f"WIN:{res.win_symbol}"
        else:
            line = f"Slots landed {reels} for {viewer}. No match."
            outcome = "LOSS"
        event = {
            "type": "redeem_result",
            "game": "slots",
            "viewer": viewer,
            "outcome": outcome,
            "detail": {
                "reels": list(res.reels),
                "is_win": res.is_win,
                "win_symbol": res.win_symbol,
                "commit": rnd.commit,
                "server_seed": rnd.server_seed,
                "nonce": nonce,
            },
        }
        return line, event

    def _run_heist(self, viewer: str, user_input: str, rid: str) -> tuple[str, dict]:
        rnd = self._round()
        nonce = self._next_nonce("heist")
        # Single-redeem heist: the redeemer is the lone participant with a fixed
        # token pot, resolved immediately (the simplest meaningful behaviour).
        pot = 100
        res = self._heist().resolve(rnd.server_seed, [viewer], pot, nonce=nonce)
        line = (
            f"Heist {res.outcome} for {viewer}. Payout {res.payout_per_head}."
        )
        event = {
            "type": "redeem_result",
            "game": "heist",
            "viewer": viewer,
            "outcome": res.outcome,
            "detail": {
                "participants": list(res.participants),
                "pot": res.pot,
                "payout_per_head": res.payout_per_head,
                "commit": rnd.commit,
                "server_seed": rnd.server_seed,
                "nonce": nonce,
            },
        }
        return line, event

    def _run_duel(self, viewer: str, user_input: str, rid: str) -> tuple[str, dict]:
        rnd = self._round()
        nonce = self._next_nonce("duel")
        # Single-redeem duel: the redeemer challenges "the house". A distinct,
        # non-equal target keeps Duel.resolve happy and is deterministic.
        target = "the_house" if viewer != "the_house" else "the_challenger"
        wager = 100
        res = self._duel().resolve(
            rnd.server_seed, viewer, target, wager, nonce=nonce
        )
        won = res.winner == viewer
        line = (
            f"{viewer} won the duel against the house."
            if won
            else f"{viewer} lost the duel to the house."
        )
        event = {
            "type": "redeem_result",
            "game": "duel",
            "viewer": viewer,
            "outcome": "WIN" if won else "LOSS",
            "detail": {
                "winner": res.winner,
                "loser": res.loser,
                "wager": res.wager,
                "challenger": res.challenger,
                "target": res.target,
                "commit": rnd.commit,
                "server_seed": rnd.server_seed,
                "nonce": nonce,
            },
        }
        return line, event

    def _run_trivia(self, viewer: str, user_input: str, rid: str) -> tuple[str, dict]:
        rnd = self._round()
        nonce = self._next_nonce("trivia")
        # Single-redeem trivia: draw + announce a question (chat answers it later;
        # the router's job is to surface the prompt deterministically).
        question, idx, prov = self._trivia().draw_question(rnd.server_seed, nonce=nonce)
        line = f"Trivia for {viewer}: {question.question}"
        event = {
            "type": "redeem_result",
            "game": "trivia",
            "viewer": viewer,
            "outcome": question.question,
            "detail": {
                "question": question.question,
                "question_index": idx,
                "commit": prov.commit,
                "server_seed": prov.server_seed,
                "nonce": nonce,
            },
        }
        return line, event

    def _run_raffle(self, viewer: str, user_input: str, rid: str) -> tuple[str, dict]:
        rnd = self._round()
        nonce = self._next_nonce("raffle")
        raffle = self._raffle()
        # Single-redeem raffle: open a window if none is live, then enter the
        # viewer. Entry is the meaningful single-redeem behaviour; the streamer
        # draws the winner separately when the window closes.
        if not raffle.is_open:
            raffle.open()
        entered = raffle.enter(viewer)
        outcome = "entered" if entered else "already_entered"
        line = (
            f"{viewer} is in the raffle."
            if entered
            else f"{viewer} is already in the raffle."
        )
        event = {
            "type": "redeem_result",
            "game": "raffle",
            "viewer": viewer,
            "outcome": outcome,
            "detail": {
                "entered": entered,
                "entrants": list(raffle.entrants),
                "commit": rnd.commit,
                "server_seed": rnd.server_seed,
                "nonce": nonce,
            },
        }
        return line, event

    # Action key -> bound runner. Defined once at class scope.
    _RUNNERS: dict[str, Callable[[RedeemRouter, str, str, str], tuple[str, dict]]] = {
        "wheel": _run_wheel,
        "slots": _run_slots,
        "heist": _run_heist,
        "duel": _run_duel,
        "trivia": _run_trivia,
        "raffle": _run_raffle,
    }

    # -- sinks (fail-safe) ------------------------------------------------- #
    def _announce_safe(self, line: str) -> None:
        if self._announce is None:
            return
        try:
            self._announce(line)
        except Exception as exc:  # noqa: BLE001 — a TTS hiccup never breaks the tick
            logger.warning("redeem announce failed: %s", exc)

    @staticmethod
    def _to_overlay_event(event: dict) -> dict | None:
        """Translate an internal redeem / redeem_result event into one the dumb
        overlay actually accepts (overlay.server.ALLOWED_EVENT_TYPES = {wheel,
        alert, ticker}). A wheel spin animates the wheel to its server-decided
        target angle; every other game + the generic non-game redeem render as an
        alert banner. Returns None if it can't be mapped (the overlay then shows
        nothing rather than erroring). This is the adapter that makes redeem
        outcomes visible on stream (the router's own event shape is kept for the
        spoken line + the outcomes log)."""
        etype = str(event.get("type") or "")
        viewer = str(event.get("viewer") or "someone")
        if etype == "redeem_result":
            game = str(event.get("game") or "game")
            outcome = str(event.get("outcome") or "")
            if game == "wheel":
                detail = event.get("detail") or {}
                try:
                    angle = float(detail.get("target_angle", 0.0))
                except (TypeError, ValueError):
                    angle = 0.0
                return {"type": "wheel", "angle": angle, "label": outcome[:200]}
            return {
                "type": "alert",
                "title": f"{game.title()} · {viewer}"[:200],
                "body": outcome[:500],
            }
        if etype == "redeem":
            reward = str(event.get("reward") or "Redemption")
            return {
                "type": "alert",
                "title": reward[:200],
                "body": f"Redeemed by {viewer}"[:500],
            }
        return None

    def _emit(self, event: dict) -> None:
        if self._overlay is None:
            return
        overlay_event = self._to_overlay_event(event)
        if overlay_event is None:
            return
        try:
            self._overlay(overlay_event)
        except Exception as exc:  # noqa: BLE001 — overlay down never breaks the tick
            logger.warning("redeem overlay emit failed: %s", exc)
