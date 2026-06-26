"""StreamElements loyalty-points backend for the Twitch economy (2026-06-26).

Ties the chat-game / redeem economy to the channel's ONE StreamElements points
balance instead of a separate internal ledger, so viewers' ``!points`` are their
real SE loyalty points. Two pieces:

* :class:`SEPointsClient` -- a thin urllib client over the SE points REST API
  (``GET``/``PUT https://api.streamelements.com/kappa/v2/points/{ch}/{login}[/{delta}]``,
  ``Authorization: Bearer <JWT>``). Verified live (read + write, net-zero spike).
* :class:`StreamElementsLedger` -- a drop-in for
  :class:`~kenning.twitch.economy.ledger.Ledger` (same ``balance``/``credit``/
  ``debit`` signatures + ``InsufficientFunds``) backed by the SE API. Because the
  economy keys by twitch **user_id** but SE keys by **login/username**, it keeps a
  durable ``uid -> login`` map (populated via :meth:`register`, which the routers
  call per chat/redeem event). Because the SE API is NOT replay-safe (a raw
  ``PUT`` add/subtract), it keeps a local **idempotency table**: a credit/debit
  with a previously-seen ``idempotency_key`` is a no-op that returns the recorded
  balance -- mirroring the keyed-leg guarantee the SQLite ledger gives, so an
  EventSub replay never double-charges.

ANTICHEAT: stdlib + urllib only (no heavy ML, no desktop). Fail-soft: a network
error raises :class:`SEPointsError` so the caller (the chat-game loop, OFF the
voice path) handles it; it never silently corrupts a balance. Flag-gated
default-OFF (``twitch.economy.streamelements_enabled``).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from kenning.twitch.economy.ledger import InsufficientFunds

logger = logging.getLogger(__name__)

_SE_BASE = "https://api.streamelements.com/kappa/v2"


class SEPointsError(RuntimeError):
    """A StreamElements points API call failed (network / auth / HTTP)."""


def load_se_creds(path: str = "~/.kenning/streamelements.json") -> tuple[str, str]:
    """Return ``(jwt, channel_id)`` from the local creds file. Raises
    :class:`SEPointsError` if the file is missing or malformed. The JWT is a
    SECRET -- never logged."""
    p = Path(os.path.expanduser(path))
    if not p.is_file():
        raise SEPointsError(f"StreamElements creds file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        jwt = str(data["jwt"]).strip()
        channel_id = str(data["channel_id"]).strip()
    except Exception as e:  # noqa: BLE001
        raise SEPointsError(f"malformed StreamElements creds {p}: {e}") from e
    if not jwt or not channel_id:
        raise SEPointsError(f"StreamElements creds {p} missing jwt/channel_id")
    return jwt, channel_id


class SEPointsClient:
    """Minimal StreamElements points REST client (urllib). One channel."""

    def __init__(
        self, jwt: str, channel_id: str, *,
        base_url: str = _SE_BASE, timeout: float = 8.0, retries: int = 1,
    ) -> None:
        self._jwt = jwt
        self._ch = urllib.parse.quote(str(channel_id), safe="")
        self._base = base_url.rstrip("/")
        self._timeout = float(timeout)
        self._retries = max(0, int(retries))

    def _request(self, method: str, path: str) -> dict:
        url = f"{self._base}{path}"
        last: Optional[Exception] = None
        for attempt in range(self._retries + 1):
            req = urllib.request.Request(
                url, method=method,
                headers={"Authorization": f"Bearer {self._jwt}",
                         "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as r:
                    body = r.read(2048).decode("utf-8", "replace")
                return json.loads(body) if body.strip() else {}
            except urllib.error.HTTPError as e:
                # 404 = the viewer has no points record yet -> treat as zero, not
                # an error (the caller maps it). 401 = the JWT expired/invalid ->
                # log LOUDLY (it must be re-minted from the SE dashboard).
                if e.code == 404:
                    return {"_status": 404}
                if e.code == 401:
                    logger.error(
                        "StreamElements 401 UNAUTHORIZED -- the JWT is expired or "
                        "invalid. Re-copy it from the SE dashboard (Account -> Show "
                        "secrets) into ~/.kenning/streamelements.json and reboot.")
                last = SEPointsError(f"SE {method} {path} -> HTTP {e.code}")
            except Exception as e:  # noqa: BLE001
                last = SEPointsError(f"SE {method} {path} -> {e}")
            if attempt < self._retries:
                time.sleep(0.4 * (attempt + 1))
        raise last if last else SEPointsError(f"SE {method} {path} failed")

    def get_points(self, login: str) -> int:
        """Current SE points for ``login`` (0 if no record / 404)."""
        lo = urllib.parse.quote(str(login).strip().lower(), safe="")
        data = self._request("GET", f"/points/{self._ch}/{lo}")
        if data.get("_status") == 404:
            return 0
        return int(data.get("points", 0))

    def add_points(self, login: str, delta: int) -> int:
        """Add ``delta`` (may be negative) to ``login``; returns the new balance.
        Creates the record if missing."""
        lo = urllib.parse.quote(str(login).strip().lower(), safe="")
        data = self._request("PUT", f"/points/{self._ch}/{lo}/{int(delta)}")
        if "newAmount" in data:
            return int(data["newAmount"])
        # PUT should always return newAmount; fall back to a read.
        return self.get_points(login)

    def top(self, limit: int = 100) -> list[tuple[str, int]]:
        """Top viewers by points, highest first: ``[(login, points), ...]``."""
        data = self._request("GET", f"/points/{self._ch}/top?limit={int(limit)}")
        out: list[tuple[str, int]] = []
        for u in data.get("users") or []:
            login = str(u.get("username", "")).strip().lower()
            if login:
                out.append((login, int(u.get("points", 0))))
        return out


class StreamElementsLedger:
    """Drop-in for :class:`~kenning.twitch.economy.ledger.Ledger`, backed by the
    StreamElements points API + a local SQLite for the ``uid -> login`` map and
    the idempotency table (replay-safety the SE API lacks)."""

    def __init__(self, client: SEPointsClient, db_path: str) -> None:
        self._client = client
        self._lock = threading.RLock()
        self._reg_cache: dict[str, str] = {}   # uid -> login, to skip redundant writes
        Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(Path(db_path).expanduser()), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS uid_login(uid TEXT PRIMARY KEY, login TEXT NOT NULL)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS se_applied("
            "key TEXT PRIMARY KEY, balance_after INTEGER NOT NULL, ts REAL NOT NULL)")
        self._conn.commit()

    # -- uid <-> login -------------------------------------------------------
    def register(self, user_id: str, login: str) -> None:
        """Record a ``uid -> login`` mapping (SE is keyed by login; the economy
        by uid). The routers call this per chat/redeem event. Idempotent."""
        uid = str(user_id).strip()
        lo = str(login).strip().lower()
        if not uid or not lo:
            return
        with self._lock:
            if self._reg_cache.get(uid) == lo:
                return                              # unchanged -> skip the DB write
            self._conn.execute(
                "INSERT INTO uid_login(uid, login) VALUES(?,?) "
                "ON CONFLICT(uid) DO UPDATE SET login=excluded.login", (uid, lo))
            self._conn.commit()
            self._reg_cache[uid] = lo

    def _login(self, user_id: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT login FROM uid_login WHERE uid=?", (str(user_id).strip(),)
        ).fetchone()
        return row[0] if row else None

    def _seen(self, key: str) -> Optional[int]:
        row = self._conn.execute(
            "SELECT balance_after FROM se_applied WHERE key=?", (key,)).fetchone()
        return int(row[0]) if row else None

    def _record(self, key: str, balance_after: int) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO se_applied(key, balance_after, ts) VALUES(?,?,?)",
            (key, int(balance_after), time.time()))
        self._conn.commit()

    # -- Ledger-compatible API ----------------------------------------------
    def balance(self, user_id: str) -> int:
        with self._lock:
            login = self._login(user_id)
            if not login:
                return 0
            return self._client.get_points(login)

    def credit(self, user_id: str, amount: int, reason: str,
               idempotency_key: str) -> int:
        amt = int(amount)
        if amt <= 0:
            raise ValueError(f"credit amount must be > 0, got {amount!r}")
        with self._lock:
            seen = self._seen(idempotency_key)
            if seen is not None:
                return seen
            login = self._require_login(user_id)
            new = self._client.add_points(login, amt)
            self._record(idempotency_key, new)
            return new

    def debit(self, user_id: str, amount: int, reason: str,
              idempotency_key: str) -> int:
        amt = int(amount)
        if amt <= 0:
            raise ValueError(f"debit amount must be > 0, got {amount!r}")
        with self._lock:
            seen = self._seen(idempotency_key)
            if seen is not None:
                return seen
            login = self._require_login(user_id)
            bal = self._client.get_points(login)
            if bal < amt:
                raise InsufficientFunds(str(user_id), bal, amt)
            new = self._client.add_points(login, -amt)
            self._record(idempotency_key, new)
            return new

    def _require_login(self, user_id: str) -> str:
        login = self._login(user_id)
        if not login:
            # A credit/debit before the uid was register()ed -- the routers
            # register on every event, so this is a real wiring bug, not a viewer
            # with no points. Surface it (the chat-game loop catches + replies).
            raise SEPointsError(
                f"no SE login mapped for uid {user_id!r}; call register() first")
        return login

    # -- compatibility shims (the SQLite ledger surface the routers may touch) --
    def rebuild_balances(self) -> dict:
        """SE owns the balances; surface its leaderboard (login -> points) so the
        chat-game ``!leaderboard`` renders. Keyed by LOGIN (SE has no bulk per-uid
        read); the leaderboard displays logins, so this is correct."""
        try:
            return {login: pts for login, pts in self._client.top(100)}
        except Exception:  # noqa: BLE001 — leaderboard must never break the loop
            return {}

    def history(self, user_id: str, *, limit: int = 100) -> list:
        """No local event log (SE owns the points history)."""
        return []

    def total_events(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM se_applied").fetchone()
            return int(row[0]) if row else 0

    def checkpoint(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass


def build_se_ledger(creds_path: str, idempotency_db_path: str,
                    *, timeout: float = 8.0) -> StreamElementsLedger:
    """Construct a :class:`StreamElementsLedger` from the creds file. Raises
    :class:`SEPointsError` on missing/invalid creds (the caller falls back to the
    local SQLite ledger or disables the economy)."""
    jwt, channel_id = load_se_creds(creds_path)
    client = SEPointsClient(jwt, channel_id, timeout=timeout)
    return StreamElementsLedger(client, idempotency_db_path)
