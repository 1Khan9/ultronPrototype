"""Chat-activity sound alert — ping the streamer's speakers when a REAL viewer
types, so they can glance over at chat.

Filtered to ACTUAL users (the whole point — the streamer only wants to hear a
real person, not bots/system messages):
  * EXCLUDED logins never ping — the bot (ultron_kenning), StreamElements,
    Sery_bot, the broadcaster, and any other configured bot login.
  * A COOLDOWN (default 20 s) stops a fast-moving chat from constantly pinging —
    at most one ping per window.
  * A short BAN-GRACE defer (default 500 ms) + a re-check suppresses the
    advertising-spam bots that Sery_bot auto-bans within seconds: the ping is
    scheduled, and just before it fires we confirm the login was NOT banned/
    timed-out in the window (the SAME ``channel.chat.clear_user_messages`` ->
    ``is_banned`` guard the first-time welcome uses). A bot banned in the grace
    window is silently skipped AND does not consume the cooldown.

Pure logic: the actual audio playback is an injected ``play_fn``, so this module
imports ONLY stdlib and never touches the anticheat-pinned audio path (BR-P1) —
the orchestrator owns the sounddevice playback and injects it here.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable, Optional

logger = logging.getLogger("kenning.twitch.chat_alert")

__all__ = ["ChatAlertPlayer"]


def _norm(login: str) -> str:
    """Comparable login form: lowercase, stripped, no leading '@'."""
    return (login or "").strip().lstrip("@").strip().lower()


class ChatAlertPlayer:
    """Decides WHEN to play the new-message alert sound and fires the injected
    ``play_fn``. All timing state is guarded by a lock (``observe`` runs on the
    chat-tick thread; the deferred fire runs on a timer/scheduler thread)."""

    def __init__(
        self,
        *,
        play_fn: Callable[[], None],
        is_banned_fn: Optional[Callable[[str], bool]] = None,
        defer_fn: Optional[Callable[[float, Callable[[], None]], object]] = None,
        exclude_logins: Iterable[str] = (),
        cooldown_seconds: float = 20.0,
        defer_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._play = play_fn
        self._is_banned = is_banned_fn
        self._defer_fn = defer_fn
        self._exclude = {_norm(x) for x in (exclude_logins or ()) if _norm(x)}
        self._cooldown = max(0.0, float(cooldown_seconds))
        self._defer_s = max(0.0, float(defer_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        # Far in the past so the very first eligible message always pings.
        self._last_play = float("-inf")
        self._pending = False

    def observe(self, login: str) -> None:
        """Consider a chat message from ``login`` for an alert ping.

        Short-circuits (no schedule) when: the login is excluded, a ban-grace
        defer is already in flight, or the cooldown window is still open.
        Fail-safe: never raises into the chat tick."""
        try:
            lg = _norm(login)
            if not lg or lg in self._exclude:
                return
            now = self._clock()
            with self._lock:
                if self._pending:
                    return                      # one grace defer already in flight
                if (now - self._last_play) < self._cooldown:
                    return                      # still cooling down
                self._pending = True            # claim the window
            self._schedule(lg)
        except Exception as exc:  # noqa: BLE001 — an alert must never break ingest
            logger.debug("chat alert observe failed for %r: %s", login, exc)
            with self._lock:
                self._pending = False

    def _schedule(self, login: str) -> None:
        if self._defer_s <= 0:
            self._fire(login)
            return
        if self._defer_fn is not None:
            try:
                self._defer_fn(self._defer_s, lambda: self._fire(login))
                return
            except Exception as exc:  # noqa: BLE001 — bad scheduler -> fire inline
                logger.debug("chat alert defer_fn failed (%s); firing inline", exc)
                self._fire(login)
                return
        try:
            t = threading.Timer(self._defer_s, self._fire, args=(login,))
            t.daemon = True
            t.start()
        except Exception as exc:  # noqa: BLE001 — timer failure -> fire inline
            logger.debug("chat alert timer failed (%s); firing inline", exc)
            self._fire(login)

    def _fire(self, login: str) -> None:
        """Ban-grace re-check, then play. Runs on the defer/timer thread (or the
        caller's thread when ``defer_seconds<=0``)."""
        try:
            banned = False
            if self._is_banned is not None:
                try:
                    banned = bool(self._is_banned(login))
                except Exception:  # noqa: BLE001 — fail TOWARD playing (real user)
                    banned = False
            if banned:
                logger.info("chat alert for %s suppressed (banned/timed out "
                            "within the grace window)", login)
                with self._lock:
                    self._pending = False       # a banned bot never arms cooldown
                return
            # Arm the cooldown at ping START (so it measures from the ping, not
            # from when playback finishes) and keep ``_pending`` set across the
            # play so a concurrent message can't double-fire.
            with self._lock:
                self._last_play = self._clock()
            try:
                self._play()
            finally:
                with self._lock:
                    self._pending = False
        except Exception as exc:  # noqa: BLE001
            logger.debug("chat alert fire failed for %s: %s", login, exc)
            with self._lock:
                self._pending = False
