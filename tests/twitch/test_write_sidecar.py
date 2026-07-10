"""S11 — tests for the Twitch WRITE / Helix moderation sidecar
(``scripts/twitch_write_sidecar.py``).

Fully offline: a FAKE :class:`ModerationService` is injected into ``build_server``
and an ephemeral-port (``port=0``) ``SingletonThreadingHTTPServer`` is driven with
``urllib`` over loopback. No live Twitch connection, no creds, no models.

Covered:
  * GET /healthz reports ok + ready + broadcaster_id.
  * POST /prepare on an OK proposal returns a token + the proposal fields.
  * POST /prepare on a not-a-command returns {"ok":false,"not_a_command":true}.
  * POST /prepare on a not-ok proposal returns ok=false + NO token + the block reason.
  * POST /confirm with the prepared token CALLS service.confirm and returns its result.
  * POST /confirm with an unknown/already-consumed token returns {"error":"expired"}.
  * the token round-trip: prepare mints a token, confirm consumes it (single use).
  * POST /cancel drops the pending token (a subsequent confirm is "expired").
  * an unknown route -> 404; a bad/oversized body -> 400.
  * the ProposalStore is bounded + TTL'd.
  * the server binds 127.0.0.1 ONLY (not 0.0.0.0).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

# --------------------------------------------------------------------------- #
# Load the sidecar module by path (scripts/ is not an importable package).
# --------------------------------------------------------------------------- #
_ROOT = Path(__file__).resolve().parents[2]
_SIDECAR_PATH = _ROOT / "scripts" / "twitch_write_sidecar.py"


def _load_sidecar():
    spec = importlib.util.spec_from_file_location("twitch_write_sidecar", _SIDECAR_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("twitch_write_sidecar", mod)
    spec.loader.exec_module(mod)
    return mod


sidecar = _load_sidecar()


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeCommand:
    def __init__(self, action: str) -> None:
        self.action = action


class FakeProposal:
    """A ModProposal-shaped stand-in (only the attrs the handler reads)."""

    def __init__(
        self,
        *,
        action: str = "ban",
        ok: bool = True,
        readback: str = "",
        reason_blocked: str = "",
        candidates=None,
        resolved_name: str = "",
    ) -> None:
        self.command = FakeCommand(action)
        self.ok = ok
        self.readback = readback
        self.reason_blocked = reason_blocked
        self.candidates = candidates or []
        self.resolved_name = resolved_name


class FakeService:
    """A recording stand-in for ModerationService.

    ``prepare`` returns whatever proposal was queued for the given text (or a
    default keyed on the leading verb), recording the call. ``confirm`` records
    the proposal it received and returns a canned result dict.
    """

    def __init__(self) -> None:
        self.prepare_calls: list[str] = []
        self.confirm_calls: list[FakeProposal] = []
        self._scripted: dict[str, object] = {}

    def script(self, text: str, proposal) -> None:
        self._scripted[text] = proposal

    def prepare(self, text):
        self.prepare_calls.append(text)
        if text in self._scripted:
            return self._scripted[text]
        # Default: not a moderation command.
        return None

    def confirm(self, proposal):
        self.confirm_calls.append(proposal)
        return {
            "ok": True,
            "action": proposal.command.action,
            "target": proposal.resolved_name,
            "detail": {"idempotent": False, "status": 200},
        }

    def apply_chat_settings(self, cmd):
        self.chat_settings_calls = getattr(self, "chat_settings_calls", [])
        self.chat_settings_calls.append(cmd)
        return {"ok": True, "readback": getattr(cmd, "readback", "")}


# --------------------------------------------------------------------------- #
# HTTP harness
# --------------------------------------------------------------------------- #
class _Served:
    """Context manager: a built write sidecar serving on a background thread."""

    def __init__(self, service=None, **kw):
        self.server, self.store = sidecar.build_server(service, port=0, **kw)
        self.host, self.port = self.server.server_address[:2]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=3.0)

    @property
    def base(self) -> str:
        return f"http://{self.host}:{self.port}"


def _get(url: str) -> tuple[int, dict]:
    with urlopen(url, timeout=5) as resp:  # noqa: S310 — loopback only
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _post(url: str, body, *, raw: bool = False) -> tuple[int, object]:
    data = body if raw else json.dumps(body).encode("utf-8")
    if isinstance(data, str):
        data = data.encode("utf-8")
    req = Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:  # noqa: S310 — loopback only
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(payload)
        except (ValueError, TypeError):
            return exc.code, payload


# --------------------------------------------------------------------------- #
# Tests — /healthz
# --------------------------------------------------------------------------- #
def test_healthz_ready_true() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="12345") as s:
        status, body = _get(f"{s.base}/healthz")
    assert status == 200
    # chat_send_error + remint_* (2026-07-08): "" = healthy; set live when
    # sends fail / a self-service re-auth is pending, so the boot canary and
    # the token watcher can surface a dead/revoked bot token.
    assert body == {"ok": True, "ready": True, "broadcaster_id": "12345",
                    "chat_send_error": "",
                    "remint_user_code": "", "remint_uri": "",
                    # pinboard health (2026-07-09): "" = healthy/never used
                    "pin_error": ""}


def test_healthz_not_ready_when_no_service() -> None:
    # A None service serves a not-ready surface (the creds-absent case).
    with _Served(None) as s:
        status, body = _get(f"{s.base}/healthz")
    assert status == 200
    assert body["ok"] is True
    assert body["ready"] is False
    assert body["broadcaster_id"] == ""


# --------------------------------------------------------------------------- #
# Tests — /prepare
# --------------------------------------------------------------------------- #
def test_prepare_ok_proposal_returns_token_and_fields() -> None:
    svc = FakeService()
    svc.script(
        "ban troll123",
        FakeProposal(
            action="ban", ok=True, readback="Ban viewer troll123. Confirm?",
            resolved_name="troll123",
        ),
    )
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/prepare", {"text": "ban troll123"})
    assert status == 200
    assert body["ok"] is True
    assert body["token"]  # a non-empty token was minted
    assert body["readback"] == "Ban viewer troll123. Confirm?"
    assert body["action"] == "ban"
    assert body["target"] == "troll123"
    assert body["reason_blocked"] == ""
    assert body["candidates"] == []
    assert svc.prepare_calls == ["ban troll123"]


def test_prepare_not_a_command() -> None:
    svc = FakeService()  # nothing scripted -> prepare returns None
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/prepare", {"text": "what's the weather"})
    assert status == 200
    assert body == {"ok": False, "not_a_command": True}


def test_prepare_not_ok_proposal_returns_no_token() -> None:
    svc = FakeService()
    svc.script(
        "ban ghost",
        FakeProposal(
            action="ban", ok=False, reason_blocked="not_found",
            readback="No recent chatter named ghost. Nothing done.",
            resolved_name="ghost",
        ),
    )
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/prepare", {"text": "ban ghost"})
    assert status == 200
    assert body["ok"] is False
    assert body["token"] == ""  # NO token minted for a blocked proposal
    assert body["reason_blocked"] == "not_found"
    assert body["action"] == "ban"


def test_prepare_ambiguous_surfaces_candidates() -> None:
    svc = FakeService()
    cands = [
        {"user_id": "1", "login": "bob", "display_name": "Bob", "score": 92.0},
        {"user_id": "2", "login": "bobby", "display_name": "Bobby", "score": 90.0},
    ]
    svc.script(
        "ban bob",
        FakeProposal(action="ban", ok=False, reason_blocked="ambiguous", candidates=cands),
    )
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/prepare", {"text": "ban bob"})
    assert status == 200
    assert body["ok"] is False
    assert body["reason_blocked"] == "ambiguous"
    assert body["candidates"] == cands
    assert body["token"] == ""


def test_prepare_text_must_be_string() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/prepare", {"text": 42})
    assert status == 400
    assert body["ok"] is False


# --------------------------------------------------------------------------- #
# Tests — /confirm + the token round-trip
# --------------------------------------------------------------------------- #
def test_confirm_consumes_token_and_calls_service() -> None:
    svc = FakeService()
    prop = FakeProposal(action="timeout", ok=True, resolved_name="rascal")
    svc.script("timeout rascal", prop)
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        _, prep = _post(f"{s.base}/prepare", {"text": "timeout rascal"})
        token = prep["token"]
        assert token

        status, body = _post(f"{s.base}/confirm", {"token": token})
        assert status == 200
        assert body["ok"] is True
        assert body["action"] == "timeout"
        assert body["target"] == "rascal"
        # confirm was handed the SAME proposal object prepare stored.
        assert svc.confirm_calls == [prop]

        # The token is single-use: a second confirm is "expired".
        status2, body2 = _post(f"{s.base}/confirm", {"token": token})
        assert status2 == 200
        assert body2 == {"ok": False, "error": "expired"}


def test_confirm_unknown_token_is_expired() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/confirm", {"token": "nope-not-a-real-token"})
    assert status == 200
    assert body == {"ok": False, "error": "expired"}
    assert svc.confirm_calls == []  # no write attempted


def test_confirm_requires_token_string() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/confirm", {"token": ""})
    assert status == 400
    assert body["ok"] is False


# --------------------------------------------------------------------------- #
# Tests — /cancel
# --------------------------------------------------------------------------- #
def test_cancel_drops_pending_token() -> None:
    svc = FakeService()
    prop = FakeProposal(action="ban", ok=True, resolved_name="troll")
    svc.script("ban troll", prop)
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        _, prep = _post(f"{s.base}/prepare", {"text": "ban troll"})
        token = prep["token"]

        status, body = _post(f"{s.base}/cancel", {"token": token})
        assert status == 200
        assert body == {"ok": True}

        # After cancel the token is gone -> confirm is "expired", no write.
        status2, body2 = _post(f"{s.base}/confirm", {"token": token})
        assert body2 == {"ok": False, "error": "expired"}
        assert svc.confirm_calls == []


def test_cancel_unknown_token_is_ok() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/cancel", {"token": "ghost"})
    assert status == 200
    assert body == {"ok": True}


# --------------------------------------------------------------------------- #
# Tests — routing + hostile input
# --------------------------------------------------------------------------- #
def test_unknown_route_404() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/nope", {"x": 1})
    assert status == 404
    assert body["ok"] is False


def test_unknown_get_route_404() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        try:
            with urlopen(f"{s.base}/whatever", timeout=5):  # noqa: S310
                code = 200
        except HTTPError as exc:
            code = exc.code
    assert code == 404


def test_bad_body_400() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        status, body = _post(f"{s.base}/prepare", b"{not json", raw=True)
    assert status == 400
    assert body["ok"] is False


def test_oversized_body_400() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        url = f"{s.base}/prepare"
        # Send a Content-Length way above the 1 MiB cap; the handler rejects on
        # the header before reading the body.
        req = Request(url, data=b"{}", method="POST")
        req.add_header("Content-Length", str((1 << 20) + 1))
        try:
            with urlopen(req, timeout=5) as resp:  # noqa: S310
                status = resp.status
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            status = exc.code
            payload = json.loads(exc.read().decode("utf-8"))
    assert status == 400
    assert payload["ok"] is False


# --------------------------------------------------------------------------- #
# Tests — ProposalStore unit behaviour
# --------------------------------------------------------------------------- #
def test_proposal_store_cap_evicts_oldest() -> None:
    store = sidecar.ProposalStore(cap=2)
    t1 = store.put("p1")
    t2 = store.put("p2")
    t3 = store.put("p3")  # evicts t1 (oldest)
    assert store.pop(t1) is None
    assert store.pop(t2) == "p2"
    assert store.pop(t3) == "p3"


def test_proposal_store_ttl_expires() -> None:
    clock = {"t": 1000.0}
    store = sidecar.ProposalStore(ttl_s=10.0, monotonic=lambda: clock["t"])
    tok = store.put("prop")
    clock["t"] += 11.0  # past the TTL
    assert store.pop(tok) is None


def test_proposal_store_pop_is_single_use() -> None:
    store = sidecar.ProposalStore()
    tok = store.put("only-once")
    assert store.pop(tok) == "only-once"
    assert store.pop(tok) is None


# --------------------------------------------------------------------------- #
# Tests — loopback bind invariant + roster cache
# --------------------------------------------------------------------------- #
def test_binds_loopback_only() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="1") as s:
        assert s.host == "127.0.0.1"  # NEVER 0.0.0.0


def test_roster_cache_harvests_chat_events_most_recent_wins() -> None:
    def fake_opener(url: str) -> bytes:
        assert url.endswith("/buffer?since=0")
        payload = {
            "events": [
                {"seq": 1, "ts": 1.0, "event": {"type": "chat", "chatter_login": "Alice", "chatter_user_id": "10"}},
                {"seq": 2, "ts": 2.0, "event": {"type": "chat", "chatter_login": "bob", "chatter_user_id": "20"}},
                {"seq": 3, "ts": 3.0, "event": {"type": "redeem", "chatter_login": "carol", "chatter_user_id": "30"}},
                # A later alice with a new id -> most-recent wins.
                {"seq": 4, "ts": 4.0, "event": {"type": "chat", "chatter_login": "alice", "chatter_user_id": "11"}},
            ],
            "cursor": 4,
        }
        return json.dumps(payload).encode("utf-8")

    cache = sidecar.RosterCache("http://127.0.0.1:8773", opener=fake_opener)
    roster = cache()
    assert roster == {"alice": "11", "bob": "20"}  # redeem ignored; alice updated


def test_roster_cache_failsafe_on_down_sidecar() -> None:
    def boom(url: str) -> bytes:
        raise OSError("connection refused")

    cache = sidecar.RosterCache("http://127.0.0.1:8773", opener=boom)
    # A down read sidecar leaves an empty roster (never raises).
    assert cache() == {}


def test_parent_watchdog_check_alive_for_unset_pid() -> None:
    assert sidecar.parent_watchdog_check(0) == "alive"
    assert sidecar.parent_watchdog_check(-1) == "alive"


# --------------------------------------------------------------------------- #
# /say — bot chat-send (the commands-panel poster)
# --------------------------------------------------------------------------- #
def test_say_sends_via_chat_send() -> None:
    sent = []
    with _Served(FakeService(), ready=True, broadcaster_id="B",
                 chat_send=lambda t: (sent.append(t) or True)) as s:
        status, body = _post(f"{s.base}/say", {"text": "hello chat"})
    assert status == 200 and body == {"ok": True}
    assert sent == ["hello chat"]


def test_say_without_chat_send_reports_unavailable() -> None:
    with _Served(FakeService(), ready=True, broadcaster_id="B") as s:   # no chat_send wired
        status, body = _post(f"{s.base}/say", {"text": "hi"})
    assert status == 200 and body["ok"] is False and body["error"] == "chat_send_unavailable"


def test_say_rejects_empty_text() -> None:
    with _Served(FakeService(), ready=True, broadcaster_id="B", chat_send=lambda t: True) as s:
        status, body = _post(f"{s.base}/say", {"text": "   "})
    assert status == 400 and body["ok"] is False


def test_chat_settings_applies_recognized_command() -> None:
    svc = FakeService()
    with _Served(svc, ready=True, broadcaster_id="B") as s:
        status, body = _post(f"{s.base}/chat_settings", {"text": "slow mode on"})
    assert status == 200 and body["ok"] is True
    assert getattr(svc, "chat_settings_calls", [])  # the parsed command reached the service


def test_chat_settings_non_command_is_not_a_command() -> None:
    with _Served(FakeService(), ready=True, broadcaster_id="B") as s:
        status, body = _post(f"{s.base}/chat_settings", {"text": "rush B now"})
    assert status == 200 and body.get("not_a_command") is True


# --------------------------------------------------------------------------- #
# 2026-07-08 — self-service re-auth for a REVOKED bot token
# --------------------------------------------------------------------------- #
class _FakeDevice:
    user_code = "ABCD-1234"
    verification_uri = "https://www.twitch.tv/activate"
    device_code = "devcode"
    interval = 1
    expires_in = 900


class _FakeStore:
    def __init__(self, prior=None):
        self._tokens = dict(prior or {"access_token": "dead", "refresh_token": "dead"})
        self.saves: list = []

    def load(self):
        return dict(self._tokens)

    def save(self, tokens):
        self.saves.append(dict(tokens))
        self._tokens = dict(tokens)


class _FakeAuth:
    """start_device_flow -> code; poll -> minted tokens; validate -> a login."""

    def __init__(self, minted_login: str):
        self._login = minted_login

    def start_device_flow(self):
        return _FakeDevice()

    def poll_device_token(self, device_code, *, interval=1, timeout=0.0):
        # The REAL poll persists via the store before identity can be checked;
        # the worker under test rolls back on mismatch, so persistence details
        # here don't matter — return the minted dict like the real one does.
        return {"access_token": "newtok", "refresh_token": "newref"}

    def validate(self, access_token):
        return {"login": self._login}


def test_auto_remint_accepts_the_right_bot_identity() -> None:
    state = {"user_code": "", "verification_uri": "", "active": False}
    health = {"error": "bot-token refresh failed (RevokedError)"}
    store = _FakeStore()
    ok = sidecar._auto_remint_once(
        _FakeAuth("ultron_kenning"), store, "Ultron_Kenning",
        state=state, health=health, timeout=1.0)
    assert ok is True
    assert health["error"] == ""                    # healed
    assert state["user_code"] == "" and state["active"] is False
    assert store.saves == []                        # no rollback happened


def test_auto_remint_discards_a_wrong_account_approval() -> None:
    """A viewer racing the public code must never become the bot: the minted
    token is validated against the expected login and rolled back on mismatch."""
    state = {"user_code": "", "verification_uri": "", "active": False}
    health = {"error": "bot-token refresh failed (RevokedError)"}
    prior = {"access_token": "dead", "refresh_token": "dead"}
    store = _FakeStore(prior)
    ok = sidecar._auto_remint_once(
        _FakeAuth("some_viewer"), store, "ultron_kenning",
        state=state, health=health, timeout=1.0)
    assert ok is False
    assert health["error"]                          # still degraded
    assert store.saves and store.saves[-1] == prior  # rolled back to the prior dict


def test_auto_remint_publishes_the_code_while_polling() -> None:
    seen = {}

    class _WatchingAuth(_FakeAuth):
        def __init__(self, state):
            super().__init__("ultron_kenning")
            self._state = state

        def poll_device_token(self, device_code, *, interval=1, timeout=0.0):
            seen.update(self._state)                # snapshot mid-poll
            return {"access_token": "newtok"}

    state = {"user_code": "", "verification_uri": "", "active": False}
    sidecar._auto_remint_once(
        _WatchingAuth(state), _FakeStore(), "ultron_kenning",
        state=state, health={"error": "x"}, timeout=1.0)
    assert seen["user_code"] == "ABCD-1234"         # surfaced during the poll
    assert seen["active"] is True
    assert state["user_code"] == ""                 # cleared after


def test_healthz_surfaces_remint_code() -> None:
    sidecar.REMINT_STATE["user_code"] = "WXYZ-9876"
    sidecar.REMINT_STATE["verification_uri"] = "https://www.twitch.tv/activate"
    try:
        with _Served(FakeService(), ready=True, broadcaster_id="B") as s:
            status, body = _get(f"{s.base}/healthz")
    finally:
        sidecar.REMINT_STATE["user_code"] = ""
        sidecar.REMINT_STATE["verification_uri"] = ""
    assert status == 200
    assert body["remint_user_code"] == "WXYZ-9876"
    assert body["remint_uri"].endswith("/activate")


def test_orchestrator_token_watch_is_wired() -> None:
    from kenning.pipeline.orchestrator import Orchestrator
    import inspect
    src = inspect.getsource(Orchestrator._start_twitch_sidecars)
    assert "remint_user_code" in src
    assert "TWITCH RE-AUTH REQUIRED" in src
    assert "twitch-token-watch" in src


# --------------------------------------------------------------------------- #
# 2026-07-08 — STARTUP bot-token test that auto-starts the device flow
# --------------------------------------------------------------------------- #
def _boot_env(monkeypatch, *, tokens, validate, refresh):
    """Patch the auth module's TokenStore + TwitchAuth for _boot_check_bot_token,
    and spy on _start_auto_remint. Returns the spy's call list."""
    import kenning.twitch.auth as auth_mod

    class _Store:
        def __init__(self, _path):
            self._t = dict(tokens)

        def load(self):
            return dict(self._t)

        def save(self, t):
            self._t = dict(t)

    class _Auth:
        def __init__(self, *a, **k):
            pass

        def validate(self, _access):
            return validate

        def refresh(self, _rt):
            return refresh() if callable(refresh) else refresh

    monkeypatch.setattr(auth_mod, "TokenStore", _Store)
    monkeypatch.setattr(auth_mod, "TwitchAuth", _Auth)
    calls: list = []
    monkeypatch.setattr(sidecar, "_start_auto_remint",
                        lambda *a, **k: calls.append(a))
    sidecar.CHAT_SEND_HEALTH["error"] = ""
    return calls


def test_boot_check_valid_token_does_nothing(monkeypatch) -> None:
    calls = _boot_env(
        monkeypatch,
        tokens={"access_token": "live", "refresh_token": "r"},
        validate={"login": "ultron_kenning"},   # valid
        refresh=AssertionError("must not refresh a valid token"))
    ok = sidecar._boot_check_bot_token("p", "cid", "ultron_kenning")
    assert ok is True
    assert calls == []
    assert sidecar.CHAT_SEND_HEALTH["error"] == ""


def test_boot_check_revoked_token_starts_device_flow(monkeypatch) -> None:
    from kenning.twitch.auth import RevokedError

    def _refresh():
        raise RevokedError("revoked")

    calls = _boot_env(
        monkeypatch,
        tokens={"access_token": "dead", "refresh_token": "r"},
        validate=None,          # invalid -> probe the refresh
        refresh=_refresh)       # revoked
    ok = sidecar._boot_check_bot_token("p", "cid", "ultron_kenning")
    assert ok is False
    assert calls and calls[0] == ("cid", "p", "ultron_kenning")
    assert "revoked" in sidecar.CHAT_SEND_HEALTH["error"]
    sidecar.CHAT_SEND_HEALTH["error"] = ""


def test_boot_check_transient_fault_does_not_false_trigger(monkeypatch) -> None:
    def _refresh():
        raise RuntimeError("network down")   # NOT a RevokedError

    calls = _boot_env(
        monkeypatch,
        tokens={"access_token": "x", "refresh_token": "r"},
        validate=None,          # invalid (maybe just a validate hiccup)
        refresh=_refresh)       # transient
    ok = sidecar._boot_check_bot_token("p", "cid", "ultron_kenning")
    assert ok is True           # left alone
    assert calls == []          # NO device flow
    assert sidecar.CHAT_SEND_HEALTH["error"] == ""


def test_boot_check_no_refresh_token_starts_device_flow(monkeypatch) -> None:
    calls = _boot_env(
        monkeypatch,
        tokens={"access_token": "dead"},   # no refresh_token at all
        validate=None,
        refresh=AssertionError("no refresh token to use"))
    ok = sidecar._boot_check_bot_token("p", "cid", "ultron_kenning")
    assert ok is False
    assert calls and calls[0] == ("cid", "p", "ultron_kenning")
    sidecar.CHAT_SEND_HEALTH["error"] = ""


def test_boot_check_is_wired_into_chat_send_startup() -> None:
    import inspect
    src = inspect.getsource(sidecar.build_service_state)
    assert "_boot_check_bot_token(bot_token_path, client_id, bot_login)" in src


def test_token_watch_first_check_is_prompt() -> None:
    from kenning.pipeline.orchestrator import Orchestrator
    import inspect
    src = inspect.getsource(Orchestrator._start_twitch_sidecars)
    # The watcher checks soon after boot (not only every 45s) so a boot-time
    # re-auth code reaches the console quickly.
    assert "12.0 if _first else 45.0" in src


# --------------------------------------------------------------------------- #
# /pin — the pinboard (2026-07-09): send-as-bot + pin-as-broadcaster
# --------------------------------------------------------------------------- #
def test_pin_posts_and_pins() -> None:
    calls: list[str] = []

    def fake_pin(text: str) -> dict:
        calls.append(text)
        return {"ok": True, "message_id": "m77", "pinned": True}

    with _Served(FakeService(), ready=True, pin=fake_pin) as s:
        status, body = _post(f"{s.base}/pin", {"text": "📌 commands"})
    assert status == 200
    assert body == {"ok": True, "message_id": "m77", "pinned": True}
    assert calls == ["📌 commands"]


def test_pin_rejects_empty_text() -> None:
    with _Served(FakeService(), ready=True, pin=lambda t: {"ok": True}) as s:
        status, body = _post(f"{s.base}/pin", {"text": "   "})
    assert status == 400
    assert body["ok"] is False


def test_pin_unavailable_when_not_wired() -> None:
    with _Served(FakeService(), ready=True) as s:
        status, body = _post(f"{s.base}/pin", {"text": "hi"})
    assert status == 200
    assert body == {"ok": False, "error": "pin_unavailable"}


def test_pin_fn_error_becomes_500_not_stack_trace() -> None:
    def boom(_t: str) -> dict:
        raise RuntimeError("helix down")

    with _Served(FakeService(), ready=True, pin=boom) as s:
        status, body = _post(f"{s.base}/pin", {"text": "hi"})
    assert status == 500
    assert body == {"ok": False, "error": "pin_failed"}


def test_pin_state_get_active_and_unreadable() -> None:
    with _Served(FakeService(), ready=True,
                 pin_state=lambda: {"ok": True, "active": True,
                                    "readable": True}) as s:
        status, body = _get(f"{s.base}/pin")
    assert status == 200 and body["active"] is True
    # unreadable state (open-beta endpoint failed): active=None survives JSON
    with _Served(FakeService(), ready=True,
                 pin_state=lambda: {"ok": True, "active": None,
                                    "readable": False}) as s:
        status, body = _get(f"{s.base}/pin")
    assert status == 200
    assert body["active"] is None and body["readable"] is False


def test_pin_state_unavailable_when_not_wired() -> None:
    with _Served(FakeService(), ready=True) as s:
        status, body = _get(f"{s.base}/pin")
    assert status == 200
    assert body == {"ok": False, "error": "pin_unavailable"}
