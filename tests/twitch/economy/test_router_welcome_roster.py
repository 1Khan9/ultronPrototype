"""Spec 12 — ChatGameRouter roster/welcomer hooks (2026-07-09).

Fully offline: canned ChatEvents through the REAL tick path. Pins: the shared
UserRoster is fed login + REAL display name per event; the FirstTimeWelcomer's
text is posted via the normal reply channel exactly once per login; both hooks
default None (byte-identical legacy construction); a raising hook never breaks
the tick; the broadcaster is excluded end-to-end.
"""
from __future__ import annotations

import types

from kenning.twitch.economy.chat_games import ChatGameRouter, chat_event_from_buffer
from kenning.twitch.economy.ledger import Ledger
from kenning.twitch.user_roster import UserRoster
from kenning.twitch.welcome import FirstTimeWelcomer


def _flat(text, *, uid="u1", login="alice", name=None, bid="b0", mid=None):
    return {"type": "chat", "message_id": mid or f"{login}:{text}",
            "broadcaster_user_id": bid, "chatter_user_id": uid,
            "chatter_login": login, "chatter_name": name or login, "text": text}


def _ev(text, **kw):
    return chat_event_from_buffer(_flat(text, **kw))


def _cfg():
    return types.SimpleNamespace(
        earn_per_minute=0, gamble_rtp=0.90, per_stream_loss_cap=0,
        currency_name="Credits", command_cooldown_seconds=0,
        min_bet=1, max_bet=10000,
        defer_points_gamble_to_streamelements=False,
        trivia_auto_interval_minutes=0)


def _router(events, *, roster=None, welcomer=None, defer=None, chat_cfg=None):
    """Router with a SYNCHRONOUS defer by default (the ban-guard defers the
    welcome post; tests fire it inline unless a capturing ``defer`` is given)."""
    replies: list[str] = []
    r = ChatGameRouter(
        lambda: list(events), ledger=Ledger(":memory:"), cfg=_cfg(),
        announce_fn=replies.append,
        defer_fn=defer or (lambda _delay, fn: fn()),
        chat_cfg=chat_cfg,
        roster=roster, welcomer=welcomer)
    return r, replies


def _welcomer(**kw):
    defaults = dict(
        template="@{name} welcome — delay {delay}.",
        template_no_delay="@{name} welcome.",
        delay_fn=lambda: 40)
    defaults.update(kw)
    return FirstTimeWelcomer(**defaults)


# ------------------------------------------------------------------- roster
def test_roster_fed_login_and_display_name_per_event():
    roster = UserRoster()
    r, _ = _router([
        _ev("hello", uid="u1", login="xx_sniper_xx", name="xX_Sniper_Xx"),
        _ev("gg", uid="u2", login="bob", name="BobTheGreat"),
    ], roster=roster)
    r.tick()
    assert "xx_sniper_xx" in roster
    assert roster.display_of("xx_sniper_xx") == "xX_Sniper_Xx"
    assert roster.display_of("bob") == "BobTheGreat"


def test_roster_error_never_breaks_tick():
    class Boom:
        def observe(self, *_a, **_k):
            raise RuntimeError("roster down")

    r, replies = _router([_ev("!points", login="alice")], roster=Boom())
    r.tick()                                   # must not raise
    # the command path still ran (points reply for a zero-balance viewer)
    assert replies, "tick must keep dispatching after a roster error"


# ------------------------------------------------------------------ welcome
def test_first_time_welcome_posted_once_per_login():
    r, replies = _router([
        _ev("hi", uid="u1", login="newbie", name="Newbie"),
        _ev("hi again", uid="u1", login="newbie", name="Newbie", mid="m2"),
        _ev("yo", uid="u2", login="second", name="Second"),
    ], welcomer=_welcomer())
    r.tick()
    welcomes = [t for t in replies if "welcome" in t]
    assert welcomes == [
        "@Newbie welcome — delay 40 seconds.",
        "@Second welcome — delay 40 seconds.",
    ]


def test_broadcaster_not_welcomed_end_to_end():
    r, replies = _router(
        [_ev("hi chat", uid="b0", login="streamer", bid="b0")],
        welcomer=_welcomer())
    r.tick()
    assert not any("welcome" in t for t in replies)


def test_welcomer_error_never_breaks_tick():
    class Boom:
        def observe(self, *_a, **_k):
            raise RuntimeError("welcomer down")

    r, replies = _router([_ev("!points", login="alice")], welcomer=Boom())
    r.tick()                                   # must not raise
    assert replies, "tick must keep dispatching after a welcomer error"


def test_hooks_default_none_is_legacy_behaviour():
    r, replies = _router([_ev("hello", login="alice")])
    handled = r.tick()
    assert handled == 0
    assert replies == []


# ------------------------------------------------------- ban guard (2026-07-10)
def test_welcome_suppressed_when_banned_within_delay_window():
    """The live complaint: Sery_bot bans an advertising bot within seconds but
    Ultron had already welcomed it. The post is now DEFERRED and re-checked —
    a ban signal arriving in the window kills the welcome."""
    pending: list = []
    w = _welcomer()
    r, replies = _router(
        [_ev("buy followers at spam.example", uid="u9", login="adbot9000",
             name="AdBot9000")],
        welcomer=w, defer=lambda _delay, fn: pending.append(fn))
    r.tick()
    assert replies == []                      # deferred, nothing posted yet
    assert len(pending) == 1
    w.mark_banned("adbot9000")                # Sery_bot bans within the window
    pending[0]()                              # the delay elapses
    assert replies == []                      # welcome suppressed


def test_welcome_fires_after_delay_when_not_banned():
    pending: list = []
    w = _welcomer()
    r, replies = _router(
        [_ev("hi all", uid="u2", login="newbie", name="Newbie")],
        welcomer=w, defer=lambda _delay, fn: pending.append(fn))
    r.tick()
    assert replies == []
    pending[0]()                              # window passes, no ban
    assert replies == ["@Newbie welcome — delay 40 seconds."]


def test_zero_delay_posts_immediately_but_still_ban_checked():
    import types as _t

    w = _welcomer()
    w.mark_banned("adbot9000")                # banned BEFORE their first msg
    r, replies = _router(
        [_ev("spam", uid="u9", login="adbot9000", name="AdBot9000"),
         _ev("hi", uid="u2", login="newbie", name="Newbie")],
        welcomer=w,
        chat_cfg=_t.SimpleNamespace(first_time_welcome_delay_seconds=0))
    r.tick()
    assert replies == ["@Newbie welcome — delay 40 seconds."]


def test_drain_on_clear_callback_and_no_chatevent_emitted():
    import json as _json

    from kenning.twitch.economy.chat_games import make_chat_command_drain_fn

    payload = {"cursor": 2, "events": [
        {"seq": 1, "ts": 0.0,
         "event": {"type": "chat_clear_user", "target_login": "adbot9000",
                   "target_user_id": "9"}},
        {"seq": 2, "ts": 0.0, "event": _flat("hello", login="alice")},
    ]}
    calls: list[str] = []
    drain = make_chat_command_drain_fn(
        "http://127.0.0.1:1",
        http_get=lambda _url, _to: _json.dumps(payload).encode("utf-8"),
        on_clear=calls.append)
    out = drain()
    assert calls == ["adbot9000"]             # ban signal delivered
    assert [e.chatter_login for e in out] == ["alice"]   # clear emitted no event


def test_drain_on_clear_error_never_breaks_drain():
    import json as _json

    from kenning.twitch.economy.chat_games import make_chat_command_drain_fn

    payload = {"cursor": 1, "events": [
        {"seq": 1, "ts": 0.0,
         "event": {"type": "chat_clear_user", "target_login": "x"}},
        {"seq": 2, "ts": 0.0, "event": _flat("hi", login="bob")},
    ]}

    def boom(_login: str) -> None:
        raise RuntimeError("welcomer gone")

    drain = make_chat_command_drain_fn(
        "http://127.0.0.1:1",
        http_get=lambda _url, _to: _json.dumps(payload).encode("utf-8"),
        on_clear=boom)
    out = drain()                             # no raise
    assert [e.chatter_login for e in out] == ["bob"]
