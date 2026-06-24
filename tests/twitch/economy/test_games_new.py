"""Tests for new provably-fair games: Heist, Duel, Trivia, Raffle."""
from __future__ import annotations

import math
import time

import pytest

from kenning.twitch.economy.games import (
    Duel,
    DuelResult,
    GameError,
    Heist,
    HeistOutcome,
    HeistResult,
    Raffle,
    RaffleResult,
    Trivia,
    TriviaQuestion,
    TriviaResult,
    _TRIVIA_POOL,
)
from kenning.twitch.economy.rng import ProvablyFairRNG

FIXED_SEED = "deadbeef" * 8  # 64 hex chars


@pytest.fixture()
def rng():
    return ProvablyFairRNG(default_client_seed="ultron")


# ===========================================================================
# HEIST
# ===========================================================================

class TestHeist:
    def test_win_outcome_deterministic(self, rng):
        h = Heist(rng=rng, win_threshold=0.60, partial_threshold=0.30)
        r1 = h.resolve(FIXED_SEED, ["alice", "bob"], 1000, "client", 0)
        r2 = h.resolve(FIXED_SEED, ["alice", "bob"], 1000, "client", 0)
        assert r1.outcome == r2.outcome
        assert r1.payout_per_head == r2.payout_per_head

    def test_all_outcomes_reachable(self, rng):
        """Over many nonces all three outcomes must appear."""
        h = Heist(rng=rng, win_threshold=0.60, partial_threshold=0.30)
        outcomes = set()
        for nonce in range(300):
            r = h.resolve(FIXED_SEED, ["alice"], 100, "client", nonce)
            outcomes.add(r.outcome)
        assert HeistOutcome.WIN in outcomes
        assert HeistOutcome.PARTIAL in outcomes
        assert HeistOutcome.FAIL in outcomes

    def test_win_pays_full_pot(self, rng):
        """Force a WIN by using a seed that produces draw >= win_threshold."""
        h = Heist(rng=rng, win_threshold=0.01, partial_threshold=0.005)
        r = h.resolve(FIXED_SEED, ["alice", "bob"], 100, "client", 0)
        assert r.outcome == HeistOutcome.WIN
        assert r.payout_per_head == 50  # 100 // 2

    def test_house_bonus_makes_a_win_profit(self, rng):
        # No bonus (default): a 2-player WIN splits the pot back -> break-even.
        plain = Heist(rng=rng, win_threshold=0.01, partial_threshold=0.005)
        assert plain.house_bonus_pct == 0.0
        assert plain.resolve(FIXED_SEED, ["alice", "bob"], 100, "client", 0).payout_per_head == 50
        # +50% house bonus: pot 100 -> 150, per_head 75 > the 50 each staked.
        bonused = Heist(rng=rng, win_threshold=0.01, partial_threshold=0.005,
                        house_bonus_pct=0.5)
        r = bonused.resolve(FIXED_SEED, ["alice", "bob"], 100, "client", 0)
        assert r.outcome == HeistOutcome.WIN and r.payout_per_head == 75
        assert bonused.house_bonus_pct == 0.5

    def test_partial_pays_fraction(self, rng):
        h = Heist(rng=rng, win_threshold=0.99, partial_threshold=0.01,
                  partial_fraction=0.50)
        # With win_threshold=0.99, almost all draws -> PARTIAL or FAIL.
        # Find a PARTIAL nonce.
        partial_found = False
        for nonce in range(500):
            r = h.resolve(FIXED_SEED, ["alice"], 200, "client", nonce)
            if r.outcome == HeistOutcome.PARTIAL:
                assert r.payout_per_head == 100  # int(200 * 0.5) // 1
                partial_found = True
                break
        assert partial_found, "expected at least one PARTIAL in 500 nonces"

    def test_fail_pays_zero(self, rng):
        h = Heist(rng=rng, win_threshold=0.999, partial_threshold=0.998)
        fail_found = False
        for nonce in range(500):
            r = h.resolve(FIXED_SEED, ["alice"], 100, "client", nonce)
            if r.outcome == HeistOutcome.FAIL:
                assert r.payout_per_head == 0
                fail_found = True
                break
        assert fail_found

    def test_all_in_wipe_off_by_default(self, rng):
        h = Heist(rng=rng, win_threshold=0.999, partial_threshold=0.998)
        for nonce in range(200):
            r = h.resolve(FIXED_SEED, ["alice"], 100, "client", nonce)
            if r.outcome == HeistOutcome.FAIL:
                assert r.all_in_wipe is False
                break

    def test_all_in_wipe_fires_when_enabled(self, rng):
        h = Heist(rng=rng, win_threshold=0.999, partial_threshold=0.998,
                  allow_lose_all=True)
        fail_with_wipe = False
        for nonce in range(500):
            r = h.resolve(FIXED_SEED, ["alice"], 100, "client", nonce)
            if r.outcome == HeistOutcome.FAIL:
                assert r.all_in_wipe is True
                fail_with_wipe = True
                break
        assert fail_with_wipe

    def test_allow_lose_all_property(self, rng):
        assert Heist(rng=rng).allow_lose_all is False
        assert Heist(rng=rng, allow_lose_all=True).allow_lose_all is True

    def test_provenance_verifies(self, rng):
        h = Heist(rng=rng)
        r = h.resolve(FIXED_SEED, ["alice"], 100, "client", 0)
        assert rng.verify(r.provenance.commit, r.provenance.server_seed)
        assert r.provenance.game == "heist"

    def test_participants_preserved(self, rng):
        h = Heist(rng=rng)
        r = h.resolve(FIXED_SEED, ["alice", "bob", "carol"], 300, "client", 0)
        assert set(r.participants) == {"alice", "bob", "carol"}

    def test_rejects_empty_participants(self, rng):
        h = Heist(rng=rng)
        with pytest.raises(GameError):
            h.resolve(FIXED_SEED, [], 100)

    def test_rejects_negative_pot(self, rng):
        h = Heist(rng=rng)
        with pytest.raises(GameError):
            h.resolve(FIXED_SEED, ["alice"], -1)

    def test_rejects_bad_thresholds(self, rng):
        with pytest.raises(GameError):
            Heist(rng=rng, win_threshold=0.2, partial_threshold=0.5)  # partial > win
        with pytest.raises(GameError):
            Heist(rng=rng, win_threshold=0.0, partial_threshold=0.0)

    def test_rejects_bad_partial_fraction(self, rng):
        with pytest.raises(GameError):
            Heist(rng=rng, partial_fraction=0.0)
        with pytest.raises(GameError):
            Heist(rng=rng, partial_fraction=1.5)

    def test_uses_default_client_seed(self, rng):
        h = Heist(rng=rng)
        r = h.resolve(FIXED_SEED, ["alice"], 100, nonce=0)
        assert r.provenance.client_seed == "ultron"


# ===========================================================================
# DUEL
# ===========================================================================

class TestDuel:
    def test_deterministic(self, rng):
        d = Duel(rng=rng)
        r1 = d.resolve(FIXED_SEED, "alice", "bob", 100, "client", 0)
        r2 = d.resolve(FIXED_SEED, "alice", "bob", 100, "client", 0)
        assert r1.winner == r2.winner
        assert r1.loser == r2.loser

    def test_winner_and_loser_are_participants(self, rng):
        d = Duel(rng=rng)
        for nonce in range(50):
            r = d.resolve(FIXED_SEED, "alice", "bob", 50, "client", nonce)
            assert r.winner in ("alice", "bob")
            assert r.loser in ("alice", "bob")
            assert r.winner != r.loser

    def test_challenger_and_target_preserved(self, rng):
        d = Duel(rng=rng)
        r = d.resolve(FIXED_SEED, "alice", "bob", 100, "client", 0)
        assert r.challenger == "alice"
        assert r.target == "bob"

    def test_wager_preserved(self, rng):
        d = Duel(rng=rng)
        r = d.resolve(FIXED_SEED, "alice", "bob", 250, "client", 0)
        assert r.wager == 250

    def test_both_sides_can_win(self, rng):
        d = Duel(rng=rng, win_bias=0.5)
        alice_wins = bob_wins = 0
        for nonce in range(400):
            r = d.resolve(FIXED_SEED, "alice", "bob", 10, "client", nonce)
            if r.winner == "alice":
                alice_wins += 1
            else:
                bob_wins += 1
        # Both must win at least once across 400 nonces with fair bias.
        assert alice_wins > 0
        assert bob_wins > 0

    def test_win_bias_skews_outcome(self, rng):
        # bias=0.9 means challenger wins 90% of the time.
        d = Duel(rng=rng, win_bias=0.9)
        challenger_wins = sum(
            1 for n in range(1000)
            if d.resolve(FIXED_SEED, "alice", "bob", 10, "client", n).winner == "alice"
        )
        assert challenger_wins > 800, challenger_wins

    def test_provenance_verifies(self, rng):
        d = Duel(rng=rng)
        r = d.resolve(FIXED_SEED, "alice", "bob", 100, "client", 0)
        assert rng.verify(r.provenance.commit, r.provenance.server_seed)
        assert r.provenance.game == "duel"

    def test_rejects_same_challenger_and_target(self, rng):
        d = Duel(rng=rng)
        with pytest.raises(GameError):
            d.resolve(FIXED_SEED, "alice", "alice", 100)

    def test_rejects_empty_participants(self, rng):
        d = Duel(rng=rng)
        with pytest.raises(GameError):
            d.resolve(FIXED_SEED, "", "bob", 100)
        with pytest.raises(GameError):
            d.resolve(FIXED_SEED, "alice", "", 100)

    def test_rejects_negative_wager(self, rng):
        d = Duel(rng=rng)
        with pytest.raises(GameError):
            d.resolve(FIXED_SEED, "alice", "bob", -1)

    def test_rejects_bad_win_bias(self, rng):
        with pytest.raises(GameError):
            Duel(rng=rng, win_bias=0.0)
        with pytest.raises(GameError):
            Duel(rng=rng, win_bias=1.0)

    def test_uses_default_client_seed(self, rng):
        d = Duel(rng=rng)
        r = d.resolve(FIXED_SEED, "alice", "bob", 10, nonce=0)
        assert r.provenance.client_seed == "ultron"


# ===========================================================================
# TRIVIA
# ===========================================================================

class TestTrivia:
    def test_pool_has_at_least_10_questions(self):
        assert len(_TRIVIA_POOL) >= 10

    def test_draw_question_deterministic(self, rng):
        t = Trivia(rng=rng)
        q1, i1, _ = t.draw_question(FIXED_SEED, "client", 0)
        q2, i2, _ = t.draw_question(FIXED_SEED, "client", 0)
        assert q1 == q2
        assert i1 == i2

    def test_draw_question_index_in_range(self, rng):
        t = Trivia(rng=rng)
        for nonce in range(100):
            _, idx, _ = t.draw_question(FIXED_SEED, "client", nonce)
            assert 0 <= idx < len(t.pool)

    def test_check_answer_case_insensitive(self, rng):
        t = Trivia(rng=rng)
        q = TriviaQuestion("How many?", "thirteen")
        assert t.check_answer(q, "Thirteen") is True
        assert t.check_answer(q, "THIRTEEN") is True
        assert t.check_answer(q, "thirteen") is True
        assert t.check_answer(q, "twelve") is False

    def test_check_answer_strips_whitespace(self, rng):
        t = Trivia(rng=rng)
        q = TriviaQuestion("How many?", "13")
        assert t.check_answer(q, "  13  ") is True

    def test_resolve_with_winner(self, rng):
        t = Trivia(rng=rng)
        r = t.resolve(FIXED_SEED, "alice", 500, "client", 0)
        assert isinstance(r, TriviaResult)
        assert r.winner == "alice"
        assert r.pot == 500
        assert isinstance(r.question, TriviaQuestion)

    def test_resolve_no_winner_on_timeout(self, rng):
        t = Trivia(rng=rng)
        r = t.resolve(FIXED_SEED, None, 0, "client", 0)
        assert r.winner is None
        assert r.pot == 0

    def test_provenance_verifies(self, rng):
        t = Trivia(rng=rng)
        r = t.resolve(FIXED_SEED, "alice", 100, "client", 0)
        assert rng.verify(r.provenance.commit, r.provenance.server_seed)
        assert r.provenance.game == "trivia"

    def test_custom_pool(self, rng):
        pool = [
            TriviaQuestion("2+2?", "4"),
            TriviaQuestion("3+3?", "6"),
        ]
        t = Trivia(rng=rng, pool=pool)
        assert len(t.pool) == 2
        _, idx, _ = t.draw_question(FIXED_SEED, "client", 0)
        assert idx in (0, 1)

    def test_rejects_empty_pool(self, rng):
        with pytest.raises(GameError):
            Trivia(rng=rng, pool=[])

    def test_rejects_non_question_in_pool(self, rng):
        with pytest.raises(GameError):
            Trivia(rng=rng, pool=["not a TriviaQuestion"])

    def test_uses_default_client_seed(self, rng):
        t = Trivia(rng=rng)
        r = t.resolve(FIXED_SEED, "alice", 100, nonce=0)
        assert r.provenance.client_seed == "ultron"

    def test_all_pool_questions_reachable(self, rng):
        """Every question index must appear across enough nonces."""
        t = Trivia(rng=rng)
        seen = set()
        for nonce in range(len(t.pool) * 20):
            _, idx, _ = t.draw_question(FIXED_SEED, "client", nonce)
            seen.add(idx)
        assert seen == set(range(len(t.pool)))


# ===========================================================================
# RAFFLE
# ===========================================================================

class TestRaffle:
    def test_open_and_draw_single_entrant(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        r.enter("alice")
        result = r.draw(FIXED_SEED, "client", 0)
        assert result.winner == "alice"
        assert result.entrants == ("alice",)

    def test_draw_no_entrants_returns_none_winner(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        result = r.draw(FIXED_SEED, "client", 0)
        assert result.winner is None
        assert result.entrants == ()

    def test_all_entrants_eligible(self, rng):
        logins = ["alice", "bob", "carol", "dave", "eve"]
        raffle = Raffle(rng=rng)
        winners = set()
        # Draw many times with different nonces to check all can win.
        for nonce in range(200):
            raffle.open(window_s=3600)
            for login in logins:
                raffle.enter(login)
            result = raffle.draw(FIXED_SEED, "client", nonce)
            winners.add(result.winner)
        assert winners == set(logins)

    def test_duplicate_entries_deduped(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        assert r.enter("alice") is True
        assert r.enter("alice") is False  # duplicate
        assert r.enter("alice") is False
        result = r.draw(FIXED_SEED, "client", 0)
        assert result.entrants == ("alice",)  # counted once

    def test_enter_after_window_closes_rejected(self, rng, monkeypatch):
        import kenning.twitch.economy.games as games_mod
        now = [time.monotonic()]
        monkeypatch.setattr(games_mod.time, "monotonic", lambda: now[0])

        r = Raffle(rng=rng, window_s=1.0)
        r.open(window_s=1.0)
        assert r.enter("alice") is True

        now[0] += 5.0  # past deadline
        assert r.is_open is False
        assert r.enter("bob") is False

    def test_draw_resets_state_for_next_round(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        r.enter("alice")
        r.draw(FIXED_SEED, "client", 0)

        # Now open again.
        r.open(window_s=3600)
        assert r.entrants == ()
        r.enter("bob")
        result = r.draw(FIXED_SEED, "client", 1)
        assert result.winner == "bob"

    def test_open_twice_raises(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        with pytest.raises(GameError):
            r.open(window_s=3600)

    def test_provenance_verifies(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        r.enter("alice")
        result = r.draw(FIXED_SEED, "client", 0)
        assert rng.verify(result.provenance.commit, result.provenance.server_seed)
        assert result.provenance.game == "raffle"

    def test_deterministic_winner(self, rng):
        """Same seed + entrants + nonce must pick the same winner."""
        def _run():
            r = Raffle(rng=rng)
            r.open(window_s=3600)
            for login in ["alice", "bob", "carol"]:
                r.enter(login)
            return r.draw(FIXED_SEED, "client", 42).winner

        assert _run() == _run()

    def test_rejects_bad_window_s(self, rng):
        with pytest.raises(GameError):
            Raffle(rng=rng, window_s=0)
        with pytest.raises(GameError):
            Raffle(rng=rng, window_s=-10)

    def test_enter_empty_login_rejected(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        assert r.enter("") is False
        assert r.enter("   ") is False

    def test_uses_default_client_seed(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        r.enter("alice")
        result = r.draw(FIXED_SEED, nonce=0)
        assert result.provenance.client_seed == "ultron"

    def test_is_open_false_before_open(self, rng):
        r = Raffle(rng=rng)
        assert r.is_open is False

    def test_is_open_true_after_open(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        assert r.is_open is True

    def test_is_open_false_after_draw(self, rng):
        r = Raffle(rng=rng)
        r.open(window_s=3600)
        r.draw(FIXED_SEED, "client", 0)
        assert r.is_open is False
