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


def _router(events, *, roster=None, welcomer=None):
    replies: list[str] = []
    r = ChatGameRouter(
        lambda: list(events), ledger=Ledger(":memory:"), cfg=_cfg(),
        announce_fn=replies.append,
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
