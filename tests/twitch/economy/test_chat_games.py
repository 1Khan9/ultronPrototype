"""Gap-c — tests for the chat-command economy dispatcher (chat_games.py).

Fully offline: a :memory: Ledger, an injected drain (canned ChatEvents), and a
controllable FakeRNG so win/loss is deterministic. Covers the drain + flat-buffer
parse, the bet flow (debit-first, payout credit, leg-distinct idempotency),
insufficient funds, min/max bet, 'all', the per-stream loss cap, the per-user
cooldown, EventSub-replay dedup idempotency, watch-time earning, the
delete-moderation message-id index, and the RTP house-edge math.
"""
from __future__ import annotations

import json
import re
import types

import pytest

from kenning.twitch.economy.chat_games import (
    ChatGameRouter,
    DEFAULT_SLOT_SYMBOLS,
    chat_event_from_buffer,
    make_chat_command_drain_fn,
)
from kenning.twitch.economy.ledger import Ledger
from kenning.twitch.economy.rng import ProvablyFairRNG


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _flat(text, *, uid="u1", login="alice", mid=None, mod=False):
    """The read sidecar's FLAT buffered chat dict."""
    d = {"type": "chat", "message_id": mid or text, "chatter_user_id": uid,
         "chatter_login": login, "chatter_name": login, "text": text}
    if mod:
        d["badges"] = [{"set_id": "moderator", "id": "1"}]
    return d


def _ev(text, *, uid="u1", login="alice", mid=None, mod=False):
    return chat_event_from_buffer(_flat(text, uid=uid, login=login, mid=mid, mod=mod))


class FakeRNG:
    """A ProvablyFairRNG stand-in with controllable outcomes. ``uniform`` drives
    !gamble (a win is uniform < 0.5); ``slots_win`` forces a slots win (all reels
    symbol 0) or a guaranteed loss (each reel a distinct symbol)."""

    def __init__(self, *, uniform=0.99, slots_win=False):
        self._real = ProvablyFairRNG(default_client_seed="test")
        self._uniform = uniform
        self._slots_win = slots_win

    @property
    def default_client_seed(self):
        return self._real.default_client_seed

    def new_round(self):
        return self._real.new_round()

    def commit_for(self, server_seed):
        return self._real.commit_for(server_seed)

    def uniform_unit(self, server_seed, client_seed, nonce):
        return self._uniform

    def outcome(self, server_seed, client_seed, nonce, n):
        if self._slots_win:
            return 0
        m = re.search(r"reel(\d+)", str(client_seed))
        return (int(m.group(1)) if m else 0) % n

    def weighted_choice(self, server_seed, client_seed, nonce, weights):
        # delegate to the real RNG (the !wheel free-spin uses a weighted draw)
        return self._real.weighted_choice(server_seed, client_seed, nonce, weights)


def _cfg(**over):
    base = dict(earn_per_minute=10, gamble_rtp=0.90, per_stream_loss_cap=5000,
                currency_name="cores", command_cooldown_seconds=0, min_bet=1, max_bet=10000)
    base.update(over)
    return types.SimpleNamespace(**base)


def _router(events, *, ledger=None, rng=None, cfg=None, replies=None, now=None, epoch=None):
    ledger = ledger or Ledger(":memory:")
    replies = replies if replies is not None else []
    kw = {}
    if now is not None:
        kw["now_fn"] = now
    if epoch is not None:
        kw["epoch_fn"] = epoch
    r = ChatGameRouter(lambda: list(events), ledger=ledger, cfg=cfg or _cfg(),
                       rng=rng or FakeRNG(), announce_fn=replies.append, **kw)
    return r, ledger, replies


# --------------------------------------------------------------------------- #
# drain + flat-buffer parse
# --------------------------------------------------------------------------- #
def test_chat_event_from_buffer_maps_flat_fields():
    ev = chat_event_from_buffer(_flat("!points", uid="42", login="Bob", mid="m9"))
    assert ev is not None
    assert ev.text == "!points" and ev.chatter_user_id == "42"
    assert ev.chatter_login == "Bob" and ev.message_id == "m9"
    # a non-chat dict -> None
    assert chat_event_from_buffer({"type": "redeem"}) is None


def test_drain_filters_to_chat_and_advances_cursor():
    payloads = [
        json.dumps({"cursor": 5, "events": [
            {"seq": 1, "ts": 1.0, "event": _flat("!points", mid="a")},
            {"seq": 2, "ts": 1.0, "event": {"type": "redeem", "redemption_id": "r"}},
        ]}).encode(),
        json.dumps({"cursor": 5, "events": []}).encode(),
    ]
    calls = []

    def http_get(url, timeout):
        calls.append(url)
        return payloads[min(len(calls) - 1, len(payloads) - 1)]

    drain = make_chat_command_drain_fn("http://x", http_get=http_get)
    out = drain()
    assert len(out) == 1 and out[0].text == "!points"   # redeem filtered out
    assert "since=0" in calls[0]
    drain()
    assert "since=5" in calls[1]                          # cursor advanced


def test_drain_fail_safe_on_bad_body():
    drain = make_chat_command_drain_fn("http://x", http_get=lambda u, t: b"not json")
    assert drain() == []


# --------------------------------------------------------------------------- #
# read commands
# --------------------------------------------------------------------------- #
def test_points_reports_balance():
    led = Ledger(":memory:")
    led.credit("u1", 250, "seed", "seed")
    r, led, replies = _router([_ev("!points")], ledger=led)
    r.tick()
    assert replies == ["@alice you have 250 cores."]


def test_help_and_unknown():
    r, _led, replies = _router([_ev("!help", mid="h"), _ev("!frobnicate", mid="u")])
    r.tick()
    assert any("Commands:" in x for x in replies)
    assert any("unknown command" in x for x in replies)


def test_leaderboard_lists_top_balances():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "s1")
    led.credit("u2", 500, "s", "s2")
    # The caller (default uid u1) chats as login "z", so the leaderboard renders
    # u1 by its known display login "z"; u2 (never seen this session) shows its raw
    # uid. Top balance first.
    r, led, replies = _router([_ev("!leaderboard", login="z")], ledger=led)
    r.tick()
    assert replies and "u2 (500)" in replies[0] and "z (100)" in replies[0]
    assert replies[0].index("u2") < replies[0].index("z (100)")


# --------------------------------------------------------------------------- #
# bet flow — gamble + slots
# --------------------------------------------------------------------------- #
def test_gamble_win_credits_multiplier_and_keys_legs():
    led = Ledger(":memory:")
    led.credit("u1", 1000, "seed", "seed")
    r, led, replies = _router([_ev("!gamble 100", mid="m2")], ledger=led, rng=FakeRNG(uniform=0.1))
    r.tick()
    # win pays floor(100 * 0.9 / 0.5) = 180 gross; net +80
    assert led.balance("u1") == 1000 - 100 + 180
    keys = {e.idempotency_key for e in led.history("u1", limit=10)}
    assert "gamble:m2:bet" in keys and "gamble:m2:win" in keys
    assert any("WON 180" in x for x in replies)


def test_gamble_loss_debits_only():
    led = Ledger(":memory:")
    led.credit("u1", 1000, "seed", "seed")
    r, led, replies = _router([_ev("!gamble 100", mid="m2")], ledger=led, rng=FakeRNG(uniform=0.9))
    r.tick()
    assert led.balance("u1") == 900
    keys = {e.idempotency_key for e in led.history("u1", limit=10)}
    assert "gamble:m2:bet" in keys and "gamble:m2:win" not in keys
    assert any("lost 100" in x for x in replies)


def test_slots_win_and_loss():
    led = Ledger(":memory:")
    led.credit("u1", 1000, "seed", "seed")
    r, led, _ = _router([_ev("!slots 10", mid="w")], ledger=led, rng=FakeRNG(slots_win=True))
    r.tick()
    s = len(DEFAULT_SLOT_SYMBOLS)
    mult = int(0.90 * s * s)
    assert led.balance("u1") == 1000 - 10 + 10 * mult
    # loss
    led2 = Ledger(":memory:")
    led2.credit("u1", 1000, "seed", "seed")
    r2, led2, _ = _router([_ev("!slots 10", mid="l")], ledger=led2, rng=FakeRNG(slots_win=False))
    r2.tick()
    assert led2.balance("u1") == 990


def test_insufficient_funds_refuses_no_debit():
    led = Ledger(":memory:")
    led.credit("u1", 30, "seed", "seed")
    r, led, replies = _router([_ev("!gamble 100", mid="m")], ledger=led)
    r.tick()
    assert led.balance("u1") == 30  # untouched
    assert any("you only have 30" in x for x in replies)


def test_min_and_max_bet_enforced():
    led = Ledger(":memory:")
    led.credit("u1", 100000, "seed", "seed")
    r, led, replies = _router(
        [_ev("!gamble 0", mid="a"), _ev("!gamble 50000", mid="b")],
        ledger=led, cfg=_cfg(min_bet=5, max_bet=10000))
    r.tick()
    # '!gamble 0' is rejected by the PARSER (amount must be positive) -> error reply
    assert any("positive" in x or "minimum" in x for x in replies)
    assert any("maximum bet is 10000" in x for x in replies)
    assert led.balance("u1") == 100000


def test_all_in_bets_whole_balance():
    led = Ledger(":memory:")
    led.credit("u1", 77, "seed", "seed")
    r, led, _ = _router([_ev("!gamble all", mid="m")], ledger=led, rng=FakeRNG(uniform=0.9))
    r.tick()
    assert led.balance("u1") == 0  # lost all 77


def test_per_stream_loss_cap_refuses_past_ceiling():
    led = Ledger(":memory:")
    led.credit("u1", 100000, "seed", "seed")
    # cap=150: first 100 loss ok (net loss 100), second 100 would push to 200 > 150 -> refused
    r, led, replies = _router(
        [_ev("!gamble 100", mid="a"), _ev("!gamble 100", mid="b")],
        ledger=led, cfg=_cfg(per_stream_loss_cap=150, command_cooldown_seconds=0),
        rng=FakeRNG(uniform=0.9))
    r.tick()
    assert led.balance("u1") == 100000 - 100   # only the first bet went through
    assert any("loss cap" in x for x in replies)


def test_cooldown_throttles_second_bet():
    led = Ledger(":memory:")
    led.credit("u1", 10000, "seed", "seed")
    clock = {"t": 0.0}
    r, led, replies = _router(
        [_ev("!gamble 100", mid="a"), _ev("!gamble 100", mid="b")],
        ledger=led, cfg=_cfg(command_cooldown_seconds=5), rng=FakeRNG(uniform=0.9),
        now=lambda: clock["t"])
    r.tick()  # both in the same tick at t=0 -> the second is within cooldown -> silently dropped
    # exactly one bet event
    bets = [e for e in led.history("u1", limit=20) if e.reason == "gamble bet"]
    assert len(bets) == 1


# --------------------------------------------------------------------------- #
# replay dedup + earn + message-id
# --------------------------------------------------------------------------- #
def test_replay_is_idempotent():
    led = Ledger(":memory:")
    led.credit("u1", 1000, "seed", "seed")
    events = [_ev("!gamble 100", mid="m2")]
    r, led, _ = _router(events, ledger=led, rng=FakeRNG(uniform=0.1))
    r.tick()
    bal = led.balance("u1")
    r.tick()  # same message_id -> dedup -> no second apply
    assert led.balance("u1") == bal


def test_watch_time_earn_credits_active_viewers_once_per_minute():
    led = Ledger(":memory:")
    clock = {"mono": 0.0, "epoch": 0.0}
    r, led, _ = _router([_ev("!points", uid="u1", login="alice", mid="m")], ledger=led,
                        cfg=_cfg(earn_per_minute=10),
                        now=lambda: clock["mono"], epoch=lambda: clock["epoch"])
    r.tick()                       # arms the earn clock (minute 0), no payout yet
    assert led.balance("u1") == 0
    clock["epoch"] = 60.0          # advance one minute; u1 still active (mono unchanged)
    r.tick()
    assert led.balance("u1") == 10
    r.tick()                       # same minute -> idempotent, no double credit
    assert led.balance("u1") == 10


def test_last_message_id_index_for_delete():
    r, _led, _ = _router([_ev("hello", login="Bob", mid="m1"),
                          _ev("world", login="Bob", mid="m2")])
    r.tick()
    assert r.last_message_id("bob") == "m2"   # latest, case-insensitive
    assert r.last_message_id("nobody") is None


# --------------------------------------------------------------------------- #
# economy invariants
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# !give — viewer -> viewer transfer (gated transfers_enabled)
# --------------------------------------------------------------------------- #
def test_give_disabled_by_default():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "s1")
    evs = [_ev("hi", uid="ub", login="bob", mid="b0"),
           _ev("!give @bob 40", uid="u1", login="alice", mid="g1")]
    r, led, replies = _router(evs, ledger=led, cfg=_cfg(transfers_enabled=False, earn_per_minute=0))
    r.tick()
    assert any("transfers are disabled" in x for x in replies)
    assert led.balance("u1") == 100 and led.balance("ub") == 0


def test_give_transfers_when_enabled_and_is_replay_idempotent():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "s1")
    evs = [_ev("hi", uid="ub", login="bob", mid="b0"),
           _ev("!give @bob 40", uid="u1", login="alice", mid="g1")]
    r, led, replies = _router(evs, ledger=led, cfg=_cfg(transfers_enabled=True, earn_per_minute=0))
    r.tick()
    assert led.balance("u1") == 60 and led.balance("ub") == 40
    r.tick()   # EventSub replay of the same message_id -> deduped, no double-move
    assert led.balance("u1") == 60 and led.balance("ub") == 40


def test_give_rejects_unknown_recipient_and_self():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "s1")
    evs = [_ev("!give @ghost 10", uid="u1", login="alice", mid="g1"),
           _ev("!give @alice 10", uid="u1", login="alice", mid="g2")]
    r, led, replies = _router(evs, ledger=led, cfg=_cfg(transfers_enabled=True, earn_per_minute=0))
    r.tick()
    assert any("don't know" in x for x in replies)
    assert any("can't give to yourself" in x for x in replies)
    assert led.balance("u1") == 100


# --------------------------------------------------------------------------- #
# !wheel — free spin (per-stream cap, house-funded payout)
# --------------------------------------------------------------------------- #
def test_wheel_free_spin_credits_and_caps_per_stream():
    led = Ledger(":memory:")
    evs = [_ev("!wheel", uid="u1", login="alice", mid="w1"),
           _ev("!wheel", uid="u1", login="alice", mid="w2")]
    r, led, replies = _router(evs, ledger=led, cfg=_cfg(wheel_free_per_stream=1, earn_per_minute=0))
    r.tick()
    assert led.balance("u1") > 0                          # first spin paid out
    assert any("no free spins left" in x for x in replies)  # second capped


def test_wheel_disabled_when_cap_zero():
    led = Ledger(":memory:")
    r, led, replies = _router([_ev("!wheel", uid="u1", login="alice", mid="w1")],
                              ledger=led, cfg=_cfg(wheel_free_per_stream=0, earn_per_minute=0))
    r.tick()
    assert led.balance("u1") == 0 and any("disabled" in x for x in replies)


# --------------------------------------------------------------------------- #
# !heist — group pooled bet, join window, house bonus
# --------------------------------------------------------------------------- #
def test_heist_win_pays_house_bonus_split():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "a")
    led.credit("u2", 100, "s", "b")
    clock = [0.0]
    evs = [_ev("!heist 100", uid="u1", login="alice", mid="h1"),
           _ev("!heist 100", uid="u2", login="bob", mid="h2")]
    r, led, replies = _router(
        evs, ledger=led,
        cfg=_cfg(heist_window_seconds=30, heist_house_bonus_pct=0.5,
                 heist_min_players=1, earn_per_minute=0, command_cooldown_seconds=0),
        rng=FakeRNG(uniform=0.9),   # draw 0.9 >= win_threshold 0.6 -> WIN
        now=lambda: clock[0])
    r.tick()
    assert led.balance("u1") == 0 and led.balance("u2") == 0   # both staked
    evs.clear()
    clock[0] = 31.0
    r.tick()   # deadline -> resolve. pot 200, +50% bonus = 300, per_head 150
    assert led.balance("u1") == 150 and led.balance("u2") == 150
    assert any("HEIST WIN" in x for x in replies)


def test_heist_fail_loses_stakes():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "a")
    clock = [0.0]
    evs = [_ev("!heist 100", uid="u1", login="alice", mid="h1")]
    r, led, replies = _router(
        evs, ledger=led,
        cfg=_cfg(heist_window_seconds=30, heist_min_players=1, earn_per_minute=0),
        rng=FakeRNG(uniform=0.1),   # draw 0.1 < partial_threshold 0.3 -> FAIL
        now=lambda: clock[0])
    r.tick()
    evs.clear()
    clock[0] = 31.0
    r.tick()
    assert led.balance("u1") == 0 and any("HEIST FAILED" in x for x in replies)


def test_heist_refunds_when_below_min_players():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "a")
    clock = [0.0]
    evs = [_ev("!heist 100", uid="u1", login="alice", mid="h1")]
    r, led, replies = _router(
        evs, ledger=led,
        cfg=_cfg(heist_window_seconds=30, heist_min_players=3, earn_per_minute=0),
        now=lambda: clock[0])
    r.tick()
    evs.clear()
    clock[0] = 31.0
    r.tick()
    assert led.balance("u1") == 100 and any("refunded" in x for x in replies)


# --------------------------------------------------------------------------- #
# !duel + !accept — 1v1 escrow challenge
# --------------------------------------------------------------------------- #
def test_duel_challenge_accept_settles_to_winner():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "a")
    led.credit("u2", 100, "s", "b")
    evs = [_ev("hi", uid="u2", login="bob", mid="b0"),
           _ev("!duel @bob 50", uid="u1", login="alice", mid="d1"),
           _ev("!accept", uid="u2", login="bob", mid="d2")]
    r, led, replies = _router(
        evs, ledger=led, cfg=_cfg(earn_per_minute=0, duel_window_seconds=60),
        rng=FakeRNG(uniform=0.1))   # draw 0.1 < win_bias 0.5 -> challenger (alice) wins
    r.tick()
    assert led.balance("u1") == 150 and led.balance("u2") == 50
    assert any("DUEL" in x and "alice" in x for x in replies)


def test_duel_expires_and_refunds_challenger():
    led = Ledger(":memory:")
    led.credit("u1", 100, "s", "a")
    clock = [0.0]
    evs = [_ev("hi", uid="u2", login="bob", mid="b0"),
           _ev("!duel @bob 50", uid="u1", login="alice", mid="d1")]
    r, led, replies = _router(
        evs, ledger=led, cfg=_cfg(earn_per_minute=0, duel_window_seconds=60),
        now=lambda: clock[0])
    r.tick()
    assert led.balance("u1") == 50            # escrowed
    evs.clear()
    clock[0] = 61.0
    r.tick()
    assert led.balance("u1") == 100 and any("expired" in x for x in replies)


def test_accept_with_no_pending_duel():
    led = Ledger(":memory:")
    r, led, replies = _router([_ev("!accept", uid="u1", login="alice", mid="a1")],
                              ledger=led, cfg=_cfg(earn_per_minute=0))
    r.tick()
    assert any("no duel to accept" in x for x in replies)


# --------------------------------------------------------------------------- #
# !raffle — mod-opened entry window, house prize
# --------------------------------------------------------------------------- #
def test_raffle_mod_opens_then_draws_winner():
    led = Ledger(":memory:")
    clock = [0.0]
    evs = [_ev("!raffle", uid="um", login="mod", mid="r0", mod=True),
           _ev("!raffle", uid="u1", login="alice", mid="r1"),
           _ev("!enter", uid="u2", login="bob", mid="r2")]
    r, led, replies = _router(
        evs, ledger=led,
        cfg=_cfg(earn_per_minute=0, raffle_window_seconds=30, raffle_prize=500),
        now=lambda: clock[0])
    r.tick()
    assert any("RAFFLE open" in x for x in replies)
    assert any("entered the raffle" in x for x in replies)
    evs.clear()
    clock[0] = 31.0
    r.tick()   # FakeRNG.outcome -> 0 -> first entrant (alice) wins
    assert led.balance("u1") == 500 and any("RAFFLE winner" in x for x in replies)


def test_raffle_non_mod_cannot_open():
    led = Ledger(":memory:")
    r, led, replies = _router([_ev("!raffle", uid="u1", login="alice", mid="r1")],
                              ledger=led, cfg=_cfg(earn_per_minute=0))
    r.tick()
    assert any("no raffle is running" in x for x in replies)


def test_empty_message_id_bet_is_replay_idempotent():
    # A (malformed/synthetic) chat event with NO message_id must NOT double-spend on
    # replay: the stable content-hash surrogate (_event_key) dedups it AND keys its
    # ledger legs, so re-delivery applies the stake exactly once.
    led = Ledger(":memory:")
    led.credit("u1", 1000, "s", "s1")
    flat = {"type": "chat", "message_id": "", "chatter_user_id": "u1",
            "chatter_login": "alice", "chatter_name": "alice", "text": "!gamble 100"}
    ev = chat_event_from_buffer(flat)
    assert ev is not None and ev.message_id == ""
    events = [ev]
    r, led, _replies = _router(events, ledger=led, cfg=_cfg(earn_per_minute=0),
                               rng=FakeRNG(uniform=0.99))   # draw >= 0.5 -> loss
    r.tick()
    assert led.balance("u1") == 900           # one 100 stake debited, lost
    r.tick()                                   # SAME id-less event re-delivered
    assert led.balance("u1") == 900           # deduped -> NOT 800, no double-spend


def test_gamble_rtp_is_net_negative_over_many_rounds():
    # Real RNG, many rounds at a fixed stake: the house edge means the player's
    # expected return is ~rtp (< 1). Statistical, with a generous band.
    led = Ledger(":memory:")
    led.credit("u1", 10_000_000, "seed", "seed")
    rng = ProvablyFairRNG(default_client_seed="ev")
    cfg = _cfg(command_cooldown_seconds=0, max_bet=0)
    replies = []
    start = led.balance("u1")
    rounds = 2000
    evs = [_ev("!gamble 100", mid=f"g{i}") for i in range(rounds)]
    r = ChatGameRouter(lambda: evs, ledger=led, cfg=cfg, rng=rng, announce_fn=replies.append)
    r.tick()
    wagered = rounds * 100
    returned = (led.balance("u1") - start) + wagered   # net change + stakes = gross returned
    rtp_observed = returned / wagered
    assert 0.75 < rtp_observed < 1.05, rtp_observed   # centered on ~0.90


def test_config_defaults_off():
    from kenning.config import TwitchEconomyConfig
    c = TwitchEconomyConfig()
    assert c.chat_commands_enabled is False
    assert c.command_cooldown_seconds == 5
    assert c.min_bet == 1 and c.max_bet == 10000


def _trivia_router(led, *, prize=100, window=30.0, clock=None):
    cfg = _cfg(trivia_prize=prize, trivia_window_seconds=window)
    replies, batch = [], []
    kw = {"now_fn": (lambda: clock["t"])} if clock is not None else {}
    r = ChatGameRouter(lambda: list(batch), ledger=led, cfg=cfg,
                       rng=ProvablyFairRNG(default_client_seed="t"),
                       announce_fn=replies.append, **kw)
    return r, batch, replies


def test_trivia_mod_starts_first_correct_wins_and_closes():
    led = Ledger(":memory:")
    r, batch, replies = _trivia_router(led, prize=100)
    batch[:] = [_ev("!trivia", login="modder", mod=True, mid="t1")]
    r.tick()
    assert r._trivia is not None and any("TRIVIA" in x for x in replies)
    answer = r._trivia["question"].answer   # whatever was drawn
    batch[:] = [_ev(answer, uid="u2", login="bob", mid="a1")]
    r.tick()
    assert led.balance("u2") == 100
    assert r._trivia is None and any("got it" in x for x in replies)
    # a replayed / second correct answer does NOT double-award (round already closed)
    batch[:] = [_ev(answer, uid="u2", login="bob", mid="a2")]
    r.tick()
    assert led.balance("u2") == 100


def test_trivia_non_mod_cannot_start():
    led = Ledger(":memory:")
    r, batch, replies = _trivia_router(led)
    batch[:] = [_ev("!trivia", login="rando", mod=False, mid="t")]
    r.tick()
    assert r._trivia is None and any("only mods" in x for x in replies)


def test_trivia_wrong_answer_keeps_round_open():
    led = Ledger(":memory:")
    r, batch, _ = _trivia_router(led)
    batch[:] = [_ev("!trivia", mod=True, login="m", mid="t")]
    r.tick()
    batch[:] = [_ev("definitely not the trivia answer xyz", uid="u2", mid="w")]
    r.tick()
    assert r._trivia is not None and led.balance("u2") == 0


def test_trivia_times_out():
    led = Ledger(":memory:")
    clock = {"t": 0.0}
    r, batch, replies = _trivia_router(led, window=10.0, clock=clock)
    batch[:] = [_ev("!trivia", mod=True, login="m", mid="t")]
    r.tick()
    clock["t"] = 20.0      # past the 10s window
    batch[:] = []
    r.tick()
    assert r._trivia is None and any("timed out" in x for x in replies)


def test_trivia_already_running():
    led = Ledger(":memory:")
    r, batch, replies = _trivia_router(led)
    batch[:] = [_ev("!trivia", mod=True, login="m", mid="t1")]
    r.tick()
    batch[:] = [_ev("!trivia", mod=True, login="m", mid="t2")]
    r.tick()
    assert any("already running" in x for x in replies)


def test_orchestrator_wires_chat_games_gated_and_closes_ledger():
    import inspect
    from kenning.pipeline.orchestrator import Orchestrator
    hook = inspect.getsource(Orchestrator._start_twitch_chat_mode)
    assert "ChatGameRouter" in hook and "make_chat_command_drain_fn" in hook
    assert "chat_commands_enabled" in hook          # gated default-OFF
    assert "_twitch_chat_game_router" in hook and "_twitch_ledger" in hook
    # the economy ledger is checkpointed/closed somewhere in the orchestrator shutdown
    full = inspect.getsource(Orchestrator)
    assert "_twitch_ledger" in full and "_ledger.close()" in full


def test_no_banned_imports():
    import kenning.twitch.economy.chat_games as m
    src = m.__file__
    import ast
    tree = ast.parse(open(src, encoding="utf-8").read())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    banned = {"pyautogui", "mss", "pynput", "keyboard", "mouse", "win32api", "torch"}
    assert not (roots & banned), roots & banned
