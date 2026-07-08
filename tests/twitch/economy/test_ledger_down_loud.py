"""2026-07-08 live incident — a points-backend outage must be LOUD in chat.

A stale StreamElements JWT 401'd every ledger call during the live test and
the games went SILENT: !heist produced no reply and no card, and !leaderboard
swallowed the 401 into "{}" and announced "No one has any Credits yet".
These pin the corrected contract: every generic debit failure and a
leaderboard backend failure answer with the shared "isn't responding" notice
(nothing charged), distinct from insufficient funds and from a genuinely
empty board.
"""
from __future__ import annotations

import types

import pytest

from kenning.twitch.economy.chat_games import ChatGameRouter, chat_event_from_buffer
from kenning.twitch.economy.ledger import Ledger


def _ev(text, *, uid="u1", login="alice", mid=None):
    return chat_event_from_buffer(
        {"type": "chat", "message_id": mid or text, "chatter_user_id": uid,
         "chatter_login": login, "chatter_name": login, "text": text})


def _cfg(**over):
    base = dict(earn_per_minute=0, gamble_rtp=0.90, per_stream_loss_cap=0,
                currency_name="Credits", command_cooldown_seconds=0,
                min_bet=1, max_bet=10000,
                defer_points_gamble_to_streamelements=False,
                trivia_auto_interval_minutes=0,
                transfers_enabled=True,
                song_requests_enabled=True,
                song_request_cost=1000, album_request_cost=5000)
    base.update(over)
    return types.SimpleNamespace(**base)


class _DownLedger(Ledger):
    """A :memory: ledger whose backend 'goes down' for debits / the leaderboard
    (the stale-JWT failure shape: balance reads fine, mutations 401)."""

    def __init__(self):
        super().__init__(":memory:")

    def balance(self, user_id):
        return 10_000

    def debit(self, user_id, amount, reason, key):
        raise RuntimeError("SE PUT /points -> HTTP 401")

    def rebuild_balances(self):
        raise RuntimeError("SE GET /points/top -> HTTP 401")


def _router(events, *, ledger):
    replies: list[str] = []
    r = ChatGameRouter(
        lambda: list(events), ledger=ledger, cfg=_cfg(),
        announce_fn=replies.append,
        defer_fn=lambda _d, fn: fn(),
        song_request_fn=lambda k, q: {"kind": "track", "name": "X", "artists": "Y"},
    )
    return r, replies


@pytest.mark.parametrize("command", [
    "!slots 100",
    "!heist 100",
    "!song dance dance",
    "!give @bob 100",
])
def test_debit_backend_failure_replies_loudly(command):
    ledger = _DownLedger()
    if command.startswith("!give"):
        # !give needs the target resolvable: seed presence for bob first.
        r, replies = _router(
            [_ev("hi", uid="u2", login="bob"), _ev(command)], ledger=ledger)
    else:
        r, replies = _router([_ev(command)], ledger=ledger)
    r.tick()
    assert replies, f"{command} must not fail silently"
    assert "isn't responding" in replies[-1]
    assert "nothing was charged" in replies[-1]


def test_leaderboard_backend_failure_is_distinct_from_empty():
    r, replies = _router([_ev("!leaderboard")], ledger=_DownLedger())
    r.tick()
    assert replies and "isn't responding" in replies[-1]
    assert "No one has any" not in replies[-1]


def test_leaderboard_empty_board_still_reads_empty():
    r, replies = _router([_ev("!leaderboard")], ledger=Ledger(":memory:"))
    r.tick()
    assert replies and "No one has any Credits yet" in replies[0]


def test_se_ledger_rebuild_raises_instead_of_swallowing():
    from kenning.twitch.economy.streamelements import StreamElementsLedger

    class _DeadClient:
        def top(self, limit=100):
            raise RuntimeError("HTTP 401")

    led = StreamElementsLedger(_DeadClient(), ":memory:")
    with pytest.raises(Exception):
        led.rebuild_balances()


def test_se_ledger_rebuild_surfaces_top_logins():
    from kenning.twitch.economy.streamelements import StreamElementsLedger

    class _Client:
        def top(self, limit=100):
            return [("alice", 5000), ("bob", 1200)]

    led = StreamElementsLedger(_Client(), ":memory:")
    assert led.rebuild_balances() == {"alice": 5000, "bob": 1200}
