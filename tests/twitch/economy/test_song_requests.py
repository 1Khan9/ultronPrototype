"""S14 — tests for the paid Spotify queue requests (!song / !album).

Fully offline: a :memory: Ledger, canned ChatEvents through the REAL parse/
dedup/dispatch path, an injected fake ``song_request_fn`` (and a synchronous
``defer_fn`` so the deferred worker + visual-leads-vocal announce run inline),
plus a hermetic SpotifyClient with an injected ``request_fn`` for the search/
queue service methods. Covers: the closed-grammar parse (query variants,
control-strip, length cap), debit-first + refund-on-failure with leg-distinct
idempotency, the unavailable/disabled/insufficient paths, the overlay card
payload (accepted by the overlay validator), the spoken confirmation, EventSub
replay dedup, the "X by Y" precision search with raw-text fallback, and album
pagination + the track cap.
"""
from __future__ import annotations

import types

from kenning.twitch.commands import CommandKind, parse_command
from kenning.twitch.economy.chat_games import ChatGameRouter, chat_event_from_buffer
from kenning.twitch.economy.ledger import Ledger


# --------------------------------------------------------------------------- #
# helpers (mirror tests/twitch/economy/test_chat_games.py)
# --------------------------------------------------------------------------- #
def _flat(text, *, uid="u1", login="alice", mid=None):
    return {"type": "chat", "message_id": mid or text, "chatter_user_id": uid,
            "chatter_login": login, "chatter_name": login, "text": text}


def _ev(text, *, uid="u1", login="alice", mid=None):
    return chat_event_from_buffer(_flat(text, uid=uid, login=login, mid=mid))


def _cfg(**over):
    # song_request_cooldown_seconds defaults to 0 HERE so the single-request
    # tests aren't throttled; the dedicated cooldown tests pass it explicitly.
    base = dict(earn_per_minute=0, gamble_rtp=0.90, per_stream_loss_cap=0,
                currency_name="Credits", command_cooldown_seconds=0,
                min_bet=1, max_bet=10000,
                defer_points_gamble_to_streamelements=False,
                trivia_auto_interval_minutes=0,
                song_requests_enabled=True, song_request_cooldown_seconds=0,
                song_request_cost=1000, album_request_cost=5000)
    base.update(over)
    return types.SimpleNamespace(**base)


def _router(events, *, cfg=None, song_fn=None, ledger=None, now=None):
    """Router with song support: synchronous defer, captured replies/overlay/speech."""
    ledger = ledger or Ledger(":memory:")
    replies: list[str] = []
    cards: list[dict] = []
    spoken: list[str] = []
    kw = {"now_fn": now} if now is not None else {}
    r = ChatGameRouter(
        lambda: list(events), ledger=ledger, cfg=cfg or _cfg(),
        announce_fn=replies.append,
        overlay_emit=cards.append,
        defer_fn=lambda _delay, fn: fn(),          # run deferred work inline
        song_request_fn=song_fn,
        speak_fn=spoken.append,
        **kw,
    )
    return r, ledger, replies, cards, spoken


def _seed(ledger, uid="u1", amount=10_000):
    ledger.credit(uid, amount, "seed", f"seed:{uid}")


# --------------------------------------------------------------------------- #
# 1. the closed-grammar parse
# --------------------------------------------------------------------------- #
def test_parse_song_query_variants():
    for text, want in [
        ("!song Dance Dance by cage the elephant", "Dance Dance by cage the elephant"),
        ("!song Dance Dance cage the elephant", "Dance Dance cage the elephant"),
        ("!song Dance Dance", "Dance Dance"),
    ]:
        cmd = parse_command(_ev(text))
        assert cmd is not None and cmd.kind is CommandKind.SONG
        assert cmd.args["query"] == want


def test_parse_album_query():
    cmd = parse_command(_ev("!album Social Cues by cage the elephant"))
    assert cmd is not None and cmd.kind is CommandKind.ALBUM
    assert cmd.args["query"] == "Social Cues by cage the elephant"


def test_parse_empty_query_is_usage_error():
    cmd = parse_command(_ev("!song"))
    assert cmd.kind is CommandKind.SONG
    assert "query" not in cmd.args and "usage" in cmd.args["error"]


def test_parse_query_control_stripped_and_capped():
    cmd = parse_command(_ev("!song Dance\x00\x1b Dance " + "x" * 500))
    q = cmd.args["query"]
    assert "\x00" not in q and "\x1b" not in q
    assert len(q) <= 200
    assert q.startswith("Dance Dance")


# --------------------------------------------------------------------------- #
# 2. the paid flow — success
# --------------------------------------------------------------------------- #
def _track_result(_kind, _query):
    return {"kind": "track", "name": "Dance Dance",
            "artists": "Cage the Elephant", "album": "Social Cues"}


def test_song_success_debits_confirms_speaks_and_cards():
    r, ledger, replies, cards, spoken = _router(
        [_ev("!song dance dance", login="alice")], song_fn=_track_result)
    _seed(ledger)
    assert r.tick() == 1
    assert ledger.balance("u1") == 9_000                      # 1000 debited, kept
    assert len(replies) == 1
    assert "alice" in replies[0] and "Dance Dance" in replies[0]
    assert "Cage the Elephant" in replies[0]
    assert len(spoken) == 1 and "alice" in spoken[0] and "Dance Dance" in spoken[0]
    assert len(cards) == 1
    card = cards[0]
    assert card["type"] == "chat_game" and card["game"] == "song"
    assert card["title"] == "SONG REQUEST" and card["won"] is True
    assert card["viewer"] == "alice" and "Dance Dance" in card["outcome"]


def test_album_success_uses_album_cost_and_track_count():
    def album_fn(kind, _q):
        assert kind == "album"
        return {"kind": "album", "name": "Social Cues",
                "artists": "Cage the Elephant", "track_count": 13}

    r, ledger, replies, cards, spoken = _router(
        [_ev("!album social cues", login="bob", uid="u2")], song_fn=album_fn)
    _seed(ledger, uid="u2")
    assert r.tick() == 1
    assert ledger.balance("u2") == 5_000                      # 5000 debited
    assert "Social Cues" in replies[0] and "13 tracks" in replies[0]
    assert cards[0]["game"] == "album" and cards[0]["title"] == "ALBUM REQUEST"
    assert "13 tracks" in cards[0]["outcome"]
    assert "Social Cues" in spoken[0]


def test_song_and_album_cards_pass_the_overlay_validator():
    # validate_event returns a NEW normalized dict or raises OverlayError; both
    # new game discriminators must be accepted (fail-closed schema).
    from kenning.twitch.overlay.server import validate_event
    r, ledger, _replies, cards, _spoken = _router(
        [_ev("!song dance dance")], song_fn=_track_result)
    _seed(ledger)
    r.tick()
    out = validate_event(cards[0])
    assert out["type"] == "chat_game" and out["game"] == "song"
    out2 = validate_event(dict(cards[0], game="album"))
    assert out2["game"] == "album"


# --------------------------------------------------------------------------- #
# 3. refunds — not found / spotify error
# --------------------------------------------------------------------------- #
def test_not_found_refunds_and_replies():
    r, ledger, replies, cards, spoken = _router(
        [_ev("!song gibberish zz")], song_fn=lambda _k, _q: None)
    _seed(ledger)
    assert r.tick() == 1
    assert ledger.balance("u1") == 10_000                    # fully refunded
    assert "refunded" in replies[0] and "gibberish zz" in replies[0]
    assert cards == [] and spoken == []                       # no card on failure


def test_spotify_error_refunds_with_distinct_message():
    def boom(_k, _q):
        raise RuntimeError("spotify down")

    r, ledger, replies, cards, _spoken = _router(
        [_ev("!song dance dance")], song_fn=boom)
    _seed(ledger)
    assert r.tick() == 1
    assert ledger.balance("u1") == 10_000
    assert "refunded" in replies[0]
    assert cards == []


# --------------------------------------------------------------------------- #
# 4. guard rails — funds / disabled / unwired / empty query / replay
# --------------------------------------------------------------------------- #
def test_insufficient_balance_never_calls_spotify():
    calls = []
    r, ledger, replies, _cards, _spoken = _router(
        [_ev("!song dance dance")],
        song_fn=lambda k, q: calls.append((k, q)))
    _seed(ledger, amount=100)                                 # < 1000
    r.tick()
    assert calls == []
    assert ledger.balance("u1") == 100                        # untouched
    assert "costs 1000" in replies[0]


def test_disabled_config_answers_unavailable_without_charge():
    r, ledger, replies, _c, _s = _router(
        [_ev("!song dance dance")],
        cfg=_cfg(song_requests_enabled=False), song_fn=_track_result)
    _seed(ledger)
    r.tick()
    assert ledger.balance("u1") == 10_000
    assert "aren't available" in replies[0]


def test_unwired_song_fn_answers_unavailable():
    r, ledger, replies, _c, _s = _router([_ev("!song dance dance")], song_fn=None)
    _seed(ledger)
    r.tick()
    assert ledger.balance("u1") == 10_000
    assert "aren't available" in replies[0]


def test_empty_query_replies_usage_without_charge():
    r, ledger, replies, _c, _s = _router([_ev("!song")], song_fn=_track_result)
    _seed(ledger)
    r.tick()
    assert ledger.balance("u1") == 10_000
    assert "usage" in replies[0]


def test_eventsub_replay_charges_once():
    ev = _ev("!song dance dance", mid="fixed-mid")
    r, ledger, replies, _c, _s = _router([ev, ev], song_fn=_track_result)
    _seed(ledger)
    r.tick()
    assert ledger.balance("u1") == 9_000                      # one debit only
    assert len(replies) == 1


# --------------------------------------------------------------------------- #
# 5. command listings advertise the commands
# --------------------------------------------------------------------------- #
def test_help_lists_song_and_album_with_costs():
    r, ledger, replies, _c, _s = _router([_ev("!help")], song_fn=_track_result)
    r.tick()
    assert "!song" in replies[0] and "1000" in replies[0]
    assert "!album" in replies[0] and "5000" in replies[0]


def test_panel_text_lists_song_and_album():
    from kenning.twitch.panel import build_commands_panel_text, MAX_CHAT_CHARS
    t = build_commands_panel_text(
        types.SimpleNamespace(commands_panel_doc_url="https://docs.example/g"))
    assert "!song" in t and "!album" in t
    assert len(t) <= MAX_CHAT_CHARS


# --------------------------------------------------------------------------- #
# 6. the Spotify service methods (hermetic client, injected request_fn)
# --------------------------------------------------------------------------- #
class _FakeAuth:
    authorized = True

    def access_token(self):
        return "tok"


class _Resp:
    def __init__(self, code=200, body=None):
        self.status_code = code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def _mk_client(request_log, *, search_body_fn, album_tracks_body=None):
    from kenning.spotify.client import SpotifyClient

    def request_fn(method, url, *, headers=None, params=None, json=None, timeout=0):
        request_log.append((method, url, dict(params or {})))
        if url.endswith("/search"):
            return _Resp(200, search_body_fn(params or {}))
        if "/albums/" in url and url.endswith("/tracks"):
            return _Resp(200, album_tracks_body or {"items": [], "next": None})
        if url.endswith("/me/player/queue"):
            return _Resp(204)
        if url.endswith("/me/player/devices"):
            return _Resp(200, {"devices": [
                {"id": "d1", "name": "PC", "is_active": True, "type": "Computer"}]})
        return _Resp(204)

    return SpotifyClient(_FakeAuth(), request_fn=request_fn)


def test_search_and_queue_track_by_artist_uses_filtered_query_first():
    log = []

    def search_body(params):
        return {"tracks": {"items": [{
            "uri": "spotify:track:t1", "name": "Dance Dance",
            "artists": [{"name": "Cage the Elephant"}],
            "album": {"name": "Social Cues"}}]}}

    c = _mk_client(log, search_body_fn=search_body)
    out = c.search_and_queue_track("Dance Dance by cage the elephant")
    assert out == {"kind": "track", "name": "Dance Dance",
                   "artists": "Cage the Elephant", "album": "Social Cues"}
    searches = [p for (m, u, p) in log if u.endswith("/search")]
    assert searches[0]["q"] == 'track:"Dance Dance" artist:"cage the elephant"'
    queued = [(m, u, p) for (m, u, p) in log if u.endswith("/me/player/queue")]
    assert queued == [("POST", "https://api.spotify.com/v1/me/player/queue",
                       {"uri": "spotify:track:t1"})]


def test_search_falls_back_to_raw_text_for_titles_containing_by():
    log = []
    hits = {"count": 0}

    def search_body(params):
        # The FILTERED pass finds nothing ("Stand" by "Me" is not a real split);
        # the raw-text fallback matches.
        hits["count"] += 1
        if params["q"].startswith("track:"):
            return {"tracks": {"items": []}}
        return {"tracks": {"items": [{
            "uri": "spotify:track:t2", "name": "Stand By Me",
            "artists": [{"name": "Ben E. King"}], "album": {}}]}}

    c = _mk_client(log, search_body_fn=search_body)
    out = c.search_and_queue_track("Stand by Me")
    assert out is not None and out["name"] == "Stand By Me"
    assert hits["count"] == 2                                  # filtered, then raw


def test_search_and_queue_track_not_found_returns_none():
    c = _mk_client([], search_body_fn=lambda p: {"tracks": {"items": []}})
    assert c.search_and_queue_track("zzz") is None


def test_search_and_queue_album_queues_every_track_capped():
    log = []
    tracks = {"items": [{"uri": f"spotify:track:a{i}"} for i in range(13)],
              "next": None}

    def search_body(params):
        return {"albums": {"items": [{
            "id": "alb1", "uri": "spotify:album:alb1", "name": "Social Cues",
            "artists": [{"name": "Cage the Elephant"}]}]}}

    c = _mk_client(log, search_body_fn=search_body, album_tracks_body=tracks)
    out = c.search_and_queue_album("Social Cues by cage the elephant",
                                   max_tracks=10)
    assert out == {"kind": "album", "name": "Social Cues",
                   "artists": "Cage the Elephant", "track_count": 10}
    queued = [p["uri"] for (m, u, p) in log if u.endswith("/me/player/queue")]
    assert queued == [f"spotify:track:a{i}" for i in range(10)]  # capped, in order


# --------------------------------------------------------------------------- #
# 7. chat persona enrichment is ADDITIVE (base verbatim + enrichment + safety)
# --------------------------------------------------------------------------- #
def test_chat_persona_is_additive_and_keeps_safety_last():
    from kenning.twitch.reply import TWITCH_CHAT_SYSTEM, _CHAT_ENRICHMENT
    base_open = "You are Ultron: a cold, precise, supremely confident machine"
    assert TWITCH_CHAT_SYSTEM.startswith(base_open)            # base unchanged, first
    assert _CHAT_ENRICHMENT in TWITCH_CHAT_SYSTEM              # enrichment layered in
    # The anti-injection DATA framing must come AFTER the enrichment so the
    # safety/output rules stay the last instructions the small model reads.
    assert (TWITCH_CHAT_SYSTEM.index(_CHAT_ENRICHMENT)
            < TWITCH_CHAT_SYSTEM.index("VIEWER MESSAGES"))
    assert "Kenning" not in _CHAT_ENRICHMENT
    assert "assistant" not in _CHAT_ENRICHMENT.lower()


# --------------------------------------------------------------------------- #
# 8. config defaults
# --------------------------------------------------------------------------- #
def test_config_defaults_for_song_requests_and_hint():
    from kenning.config import TwitchChatConfig, TwitchEconomyConfig
    e = TwitchEconomyConfig()
    assert e.song_requests_enabled is True
    assert e.song_request_cost == 1000 and e.album_request_cost == 5000
    # 2026-07-08: albums queue only the first 5 tracks; 5-min request cooldown.
    assert e.album_queue_max_tracks == 5
    assert e.song_request_cooldown_seconds == 300
    c = TwitchChatConfig()
    assert c.song_hint_enabled is True
    assert c.song_hint_interval_minutes == 15
    assert "!song" in c.song_hint_text and "!album" in c.song_hint_text


# --------------------------------------------------------------------------- #
# 9. per-viewer 5-minute request cooldown (2026-07-08)
# --------------------------------------------------------------------------- #
def test_second_request_within_cooldown_is_blocked_with_remaining():
    clock = {"t": 1000.0}
    r, ledger, replies, cards, _spoken = _router(
        [_ev("!song dance dance", login="alice")],
        cfg=_cfg(song_request_cooldown_seconds=300),
        song_fn=_track_result, now=lambda: clock["t"])
    _seed(ledger)
    r.tick()
    assert ledger.balance("u1") == 9_000            # first one charged
    assert len(replies) == 1

    # 120s later, a second request: blocked, told the remaining time, NOT charged.
    clock["t"] += 120.0
    r._drain = lambda: [_ev("!song another", login="alice", mid="m2")]
    r.tick()
    assert ledger.balance("u1") == 9_000            # no second charge
    assert "you can request another song in" in replies[-1]
    assert "3m" in replies[-1]                       # 300 - 120 = 180s = 3m
    assert len(cards) == 1                           # no second card


def test_request_allowed_after_cooldown_elapses():
    clock = {"t": 0.0}
    r, ledger, replies, _c, _s = _router(
        [_ev("!song one", login="bob", uid="u2")],
        cfg=_cfg(song_request_cooldown_seconds=300),
        song_fn=_track_result, now=lambda: clock["t"])
    _seed(ledger, uid="u2")
    r.tick()
    clock["t"] += 301.0                              # past the window
    r._drain = lambda: [_ev("!song two", login="bob", uid="u2", mid="m2")]
    r.tick()
    assert ledger.balance("u2") == 8_000            # both charged (2 x 1000)


def test_missed_request_does_not_burn_the_cooldown():
    # A not-found request is refunded AND clears the cooldown, so the viewer can
    # immediately try again without waiting.
    clock = {"t": 500.0}
    r, ledger, replies, _c, _s = _router(
        [_ev("!song gibberish", login="cara", uid="u3")],
        cfg=_cfg(song_request_cooldown_seconds=300),
        song_fn=lambda _k, _q: None, now=lambda: clock["t"])
    _seed(ledger, uid="u3")
    r.tick()
    assert ledger.balance("u3") == 10_000           # refunded
    assert "refunded" in replies[-1]
    # immediately retry (5s later) -> allowed (cooldown was cleared by the miss).
    clock["t"] += 5.0
    r._drain = lambda: [_ev("!song real one", login="cara", uid="u3", mid="m2")]
    r.tick()
    assert ledger.balance("u3") == 10_000           # miss #2 also refunded, no block
    assert "you can request another" not in " ".join(replies)


def test_album_cooldown_shares_the_song_window():
    # !album and !song share ONE per-viewer cooldown.
    clock = {"t": 0.0}

    def album_fn(_k, _q):
        return {"kind": "album", "name": "X", "artists": "Y", "track_count": 5}

    r, ledger, replies, _c, _s = _router(
        [_ev("!album x", login="dan", uid="u4")],
        cfg=_cfg(song_request_cooldown_seconds=300),
        song_fn=album_fn, now=lambda: clock["t"])
    _seed(ledger, uid="u4", amount=20_000)
    r.tick()
    clock["t"] += 10.0
    r._drain = lambda: [_ev("!song y", login="dan", uid="u4", mid="m2")]
    r.tick()
    assert "you can request another song in" in replies[-1]


def test_fmt_cooldown_phrasing():
    from kenning.twitch.economy.chat_games import _fmt_cooldown
    assert _fmt_cooldown(300) == "5m"
    assert _fmt_cooldown(214) == "3m 34s"
    assert _fmt_cooldown(45) == "45s"
    assert _fmt_cooldown(0) == "0s"
