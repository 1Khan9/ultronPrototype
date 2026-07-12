"""FirstTimeWelcomer — greet each first-time-this-run chatter once (spec 12).

The streamer runs a large stream delay (~40 s): a new arrival who types is
answered on-air long after they spoke, which reads as being ignored. The first
time a login chats this run, Ultron posts ONE chat welcome naming them and
stating the CURRENT delay (a live read — the streamer commits the value on the
stop-button DELAY field mid-stream), apologizing on the streamer's behalf.

Design:

* **Durable welcomed-set (2026-07-09).** Twitch's chat-window "first time
  chatter" highlight rides IRC's ``first-msg`` tag, which EventSub (our
  transport) does NOT expose — confirmed against the live 2026
  ``channel.chat.message`` schema (no first-time field) + the dev-forum
  guidance to track it client-side. The faithful equivalent of Twitch's
  "first message EVER in the channel" semantics is the injected
  :class:`WelcomedStore`: a login is welcomed once EVER (persisted in
  SQLite across restarts), so a reboot never re-greets the room. Only an
  actually-RENDERED welcome is marked durably — a burst-guard overflow is
  suppressed for this run only, so that chatter can still be welcomed on a
  later stream.
* **Per-run seen-set.** Still the first line of defense: a login is marked
  seen BEFORE any budget/exclusion decision, so an EventSub replay, an
  excluded chatter, or an over-budget arrival is never greeted later in the
  same run (and the durable store is consulted at most once per login).
* **Burst guard.** Welcomes are capped per rolling minute (default 4): a raid
  dumping 50 new chatters must not trigger a greeting flood. Overflow logins
  are marked seen silently. (The raid path has its own dedicated welcome.)
* **Excluded identities.** The broadcaster and the bot never welcome
  themselves; EventSub delivers their messages like anyone else's.
* **Fail-open.** A bad user-edited template (unknown placeholder) logs and
  skips — a welcome must never break chat ingest.
* **Thread-safe.** One lock guards the seen-set + budget window; ``observe``
  may be called from any router thread.

ANTICHEAT (BR-P1): stdlib only (``sqlite3``/``re``/``time``/``threading``/
``collections``); no network, no models.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger("kenning.twitch.welcome")

__all__ = ["BanTracker", "FirstTimeWelcomer", "WelcomedStore", "format_delay"]

# Hard bound on the per-run seen-set: far above any real stream's unique-chatter
# count; only bounds memory against a pathological flood of fresh logins. When
# reached, new logins are no longer tracked (and thus no longer welcomed).
_MAX_SEEN = 20000

_BUDGET_WINDOW_S = 60.0


def format_delay(seconds: int) -> str:
    """Render a delay in spoken-English units: ``40`` -> "40 seconds",
    ``60`` -> "1 minute", ``80`` -> "1 minute 20 seconds", ``1`` -> "1 second"."""
    s = max(0, int(seconds))
    mins, secs = divmod(s, 60)
    parts: list[str] = []
    if mins:
        parts.append(f"{mins} minute" + ("s" if mins != 1 else ""))
    if secs or not parts:
        parts.append(f"{secs} second" + ("s" if secs != 1 else ""))
    return " ".join(parts)


class WelcomedStore:
    """Durable set of already-welcomed logins (SQLite; survives restarts).

    One row per login ever welcomed — tiny forever (a login is <=25 chars).
    Every method is FAIL-OPEN and never raises: a broken/unwritable store
    degrades the welcomer to its per-run behaviour (the pre-persistence
    contract), never breaks chat ingest. ``seen`` fails toward False (a rare
    duplicate welcome beats silently never welcoming anyone again).

    Thread-safety: one connection guarded by a lock (the router tick thread is
    the only caller today; the lock keeps a future second reader safe).
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS welcomed ("
                "login TEXT PRIMARY KEY, ts REAL NOT NULL)")
            self._conn.commit()
            logger.info("welcomed-store ready at %s", self._path)
        except Exception as e:  # noqa: BLE001 — degrade to per-run behaviour
            logger.warning("welcomed-store unavailable (%s); first-time "
                           "welcomes fall back to once-per-run", e)
            self._conn = None

    @staticmethod
    def _key(login: object) -> Optional[str]:
        if not isinstance(login, str):
            return None
        key = login.strip().lower()
        return key or None

    def seen(self, login: str) -> bool:
        """True iff ``login`` was durably welcomed before. Errors -> False."""
        key = self._key(login)
        if key is None or self._conn is None:
            return False
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT 1 FROM welcomed WHERE login = ?", (key,)).fetchone()
            return row is not None
        except Exception as e:  # noqa: BLE001
            logger.debug("welcomed-store read failed for %s: %s", key, e)
            return False

    def mark(self, login: str) -> None:
        """Durably record ``login`` as welcomed. Errors are logged, not raised."""
        key = self._key(login)
        if key is None or self._conn is None:
            return
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO welcomed (login, ts) VALUES (?, ?)",
                    (key, time.time()))
                self._conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("welcomed-store write failed for %s: %s", key, e)

    def __len__(self) -> int:
        if self._conn is None:
            return 0
        try:
            with self._lock:
                row = self._conn.execute("SELECT COUNT(*) FROM welcomed").fetchone()
            return int(row[0]) if row else 0
        except Exception:  # noqa: BLE001
            return 0


class BanTracker:
    """Standalone recently-banned/timed-out login set, fed from EventSub
    ``channel.chat.clear_user_messages``. Extracted so the ban-grace guard can be
    SHARED by consumers that need it independently of the first-time welcome —
    e.g. the new-message sound alert must suppress ad-spam bots even when the
    welcome feature is disabled (the welcomer is then never built). Bounded,
    lock-guarded, fail-quiet (called from the chat drain hot path)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._banned: set[str] = set()

    def mark_banned(self, login: str) -> None:
        try:
            key = (login or "").strip().lower() if isinstance(login, str) else ""
            if not key:
                return
            with self._lock:
                if len(self._banned) < _MAX_SEEN:
                    self._banned.add(key)
        except Exception:  # noqa: BLE001 — must never break chat ingest
            pass

    def is_banned(self, login: str) -> bool:
        try:
            key = (login or "").strip().lower() if isinstance(login, str) else ""
            if not key:
                return False
            with self._lock:
                return key in self._banned
        except Exception:  # noqa: BLE001
            return False


class FirstTimeWelcomer:
    """Decide, once per login per run, whether to post a first-time welcome.

    Parameters
    ----------
    template:
        The welcome line; ``{name}`` + ``{delay}`` placeholders.
    template_no_delay:
        The variant used while the live delay is ``<= 0``; ``{name}`` only.
    delay_fn:
        Zero-arg live read of the CURRENT stream delay in seconds (the
        stop-button DELAY field's committed value). Read per welcome — a new
        value applies immediately, no restart.
    exclude_uids / exclude_logins:
        Identities never welcomed (the broadcaster + the bot).
    max_per_minute:
        Rolling-minute welcome budget (overflow marked seen silently).
    now_fn:
        Injectable monotonic clock for deterministic tests.
    store:
        Optional :class:`WelcomedStore` (or any object with ``seen(login)`` /
        ``mark(login)``). When given, a login is welcomed once EVER — durably
        across restarts — instead of once per run. Only a rendered welcome is
        marked; a burst-overflow suppression stays per-run.
    """

    def __init__(
        self,
        *,
        template: str,
        template_no_delay: str,
        delay_fn: Callable[[], object],
        exclude_uids: Iterable[str] = (),
        exclude_logins: Iterable[str] = (),
        max_per_minute: int = 4,
        now_fn: Callable[[], float] = time.monotonic,
        store: Optional[object] = None,
    ) -> None:
        self._template = str(template or "")
        self._template_no_delay = str(template_no_delay or "")
        self._delay_fn = delay_fn
        self._exclude_uids = {str(u).strip() for u in (exclude_uids or ()) if str(u).strip()}
        self._exclude_logins = {
            str(lg).strip().lower() for lg in (exclude_logins or ()) if str(lg).strip()
        }
        self._max_per_minute = max(1, int(max_per_minute))
        self._now = now_fn
        self._store = store
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        self._recent: deque[float] = deque()
        # Recently banned/timed-out logins (2026-07-10): fed from EventSub
        # channel.chat.clear_user_messages so a DELAYED welcome can be
        # suppressed when a mod bot (Sery_bot) bans an advertising bot within
        # the delay window. Bounded by _MAX_SEEN like the seen-set.
        self._banned: set[str] = set()

    # ------------------------------------------------------------------ core
    def observe(
        self,
        login: str,
        *,
        display_name: str = "",
        chatter_uid: str = "",
        broadcaster_uid: str = "",
    ) -> Optional[str]:
        """Record one chat sighting; return the formatted welcome text exactly
        once for a new, non-excluded, in-budget login — else None. Never raises."""
        try:
            key = (login or "").strip().lower() if isinstance(login, str) else ""
            if not key:
                return None
            uid = str(chatter_uid or "").strip()
            now = float(self._now())
            with self._lock:
                if key in self._seen:
                    return None
                if len(self._seen) >= _MAX_SEEN:
                    return None            # flood bound: stop tracking, stop greeting
                # Mark seen FIRST: an excluded / over-budget / replayed arrival
                # must never be greeted by a later message.
                self._seen.add(key)
                if key in self._exclude_logins or (uid and uid in self._exclude_uids):
                    return None
                if uid and broadcaster_uid and uid == str(broadcaster_uid).strip():
                    return None            # the streamer chatting in his own channel
                # Durable welcomed-set: greeted on a PRIOR run -> never again
                # (Twitch "first message ever" semantics). Consulted at most
                # once per login per run (the seen-set above short-circuits),
                # so the SQLite hit is off the per-message hot path. Fail-open:
                # a store error means "not seen" (per-run behaviour).
                if self._store is not None:
                    try:
                        if self._store.seen(key):
                            return None
                    except Exception as e:  # noqa: BLE001
                        logger.debug("welcomed-store seen() failed: %s", e)
                # Rolling-minute burst guard. In-memory suppression ONLY — an
                # overflow login is NOT durably marked, so a later stream can
                # still welcome them.
                while self._recent and now - self._recent[0] > _BUDGET_WINDOW_S:
                    self._recent.popleft()
                if len(self._recent) >= self._max_per_minute:
                    logger.info("first-time welcome for %s skipped (burst guard)", key)
                    return None
                self._recent.append(now)
            text = self._render(
                display_name.strip() if isinstance(display_name, str) else "", key)
            if text and self._store is not None:
                # Mark ONLY a rendered welcome (the router posts it right
                # after; a dead announce channel already logs loudly).
                try:
                    self._store.mark(key)
                except Exception as e:  # noqa: BLE001
                    logger.warning("welcomed-store mark() failed: %s", e)
            return text
        except Exception as e:  # noqa: BLE001 — a welcome must never break ingest
            logger.warning("first-time welcome failed for %r: %s", login, e)
            return None

    def seen_count(self) -> int:
        """How many distinct logins have chatted this run (introspection)."""
        with self._lock:
            return len(self._seen)

    # -------------------------------------------------------------- ban guard
    def mark_banned(self, login: str) -> None:
        """Record a ban/timeout signal (channel.chat.clear_user_messages) so a
        pending DELAYED welcome for this login is suppressed at fire time.
        Fail-quiet; bounded; never raises (called from the drain hot path)."""
        try:
            key = (login or "").strip().lower() if isinstance(login, str) else ""
            if not key:
                return
            with self._lock:
                if len(self._banned) < _MAX_SEEN:
                    self._banned.add(key)
        except Exception:  # noqa: BLE001 — must never break chat ingest
            pass

    def is_banned(self, login: str) -> bool:
        """True iff a ban/timeout signal was seen for ``login`` this run."""
        try:
            key = (login or "").strip().lower() if isinstance(login, str) else ""
            if not key:
                return False
            with self._lock:
                return key in self._banned
        except Exception:  # noqa: BLE001
            return False

    # ----------------------------------------------------------------- helpers
    def _render(self, display_name: str, login: str) -> Optional[str]:
        name = display_name or login
        try:
            delay = int(self._delay_fn() or 0)
        except Exception as e:  # noqa: BLE001 — a broken delay read -> no-delay form
            logger.debug("welcome delay_fn failed (%s); using no-delay template", e)
            delay = 0
        try:
            if delay > 0:
                text = self._template.format(name=name, delay=format_delay(delay))
            else:
                text = self._template_no_delay.format(name=name)
        except (KeyError, IndexError, ValueError) as e:
            # A user-edited template with a bad placeholder: log loudly, skip.
            logger.warning("first-time welcome template invalid (%s); welcome skipped", e)
            return None
        text = text.strip()
        return text or None
