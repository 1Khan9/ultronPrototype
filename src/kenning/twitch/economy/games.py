"""Provably-fair games — SpinTheWheel + Slots + Heist + Duel + Trivia + Raffle.

The OBS overlay is a DUMB RENDERER (MASTER.md SLICE 9): the winning segment and
the exact target angle are computed HERE, server-side, from the
:class:`~kenning.twitch.economy.rng.ProvablyFairRNG` draw — BEFORE any animation.
The overlay merely tweens the wheel to ``target_angle`` and lands on the segment
the server already chose; ``!verify`` re-derives the same result from the
revealed seed.

Wheel geometry: segment ``i`` occupies an arc proportional to its weight. Arc
``i`` spans ``[start_i, start_i + span_i)`` degrees clockwise from 0. The chosen
segment's ``target_angle`` is a deterministic point *strictly inside* that arc
(derived from a second nonce draw, with a small margin from the arc edges so the
pointer never lands on a boundary).

The ``lose ALL points`` consequence is AT-4-class: a segment whose
``consequence == LOSE_ALL`` is INERT unless the wheel was constructed with
``allow_lose_all=True``. With the flag off, such a segment can never be selected
(its effective weight is zeroed for selection) — a structural guarantee, not a
runtime check the caller can forget.

Similarly, Heist's all-in wipe is AT-4-gated: ``allow_lose_all=True`` must be
passed to :class:`Heist` explicitly (default OFF).

ANTICHEAT (BR-P1): stdlib only. No randomness except via the injected RNG.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Optional

from kenning.twitch.economy.rng import ProvablyFairRNG

logger = logging.getLogger("kenning.twitch.economy.games")

__all__ = [
    "WheelSegment",
    "SegmentResult",
    "SpinTheWheel",
    "Slots",
    "SlotsResult",
    "GameResult",
    "GameError",
    "LOSE_ALL",
    # New games
    "HeistOutcome",
    "HeistResult",
    "Heist",
    "DuelResult",
    "Duel",
    "TriviaQuestion",
    "TriviaResult",
    "Trivia",
    "RaffleResult",
    "Raffle",
]

# Sentinel consequence: clears the bettor's entire balance. AT-4 — OFF unless
# the wheel is explicitly constructed with allow_lose_all=True.
LOSE_ALL = "lose_all"

_FULL_TURN = 360.0
# Keep the pointer this fraction of the arc away from each edge so a render
# rounding error can't tip it into a neighbour segment.
_EDGE_MARGIN_FRAC = 0.10


class GameError(Exception):
    """Invalid game configuration or spin parameters."""


@dataclass(frozen=True)
class WheelSegment:
    """One wheel segment.

    :param label: display string (the overlay HTML-escapes it; we keep raw here).
    :param weight: relative probability weight (>= 0).
    :param payout: an opaque payout/consequence token the caller interprets
        (e.g. an int point delta, or :data:`LOSE_ALL` for the clear-all segment).
    """

    label: str
    weight: float
    payout: object = 0

    @property
    def consequence(self) -> str | None:
        return LOSE_ALL if self.payout == LOSE_ALL else None


@dataclass(frozen=True)
class GameResult:
    """Common provenance shared by every game result (for ``!verify``)."""

    game: str
    server_seed: str
    client_seed: str
    nonce: int
    commit: str  # sha256(server_seed) — what was published before the round


@dataclass(frozen=True)
class SegmentResult:
    """The outcome of one wheel spin."""

    index: int
    segment: WheelSegment
    target_angle: float          # degrees in [0,360); overlay tweens here
    arc_start: float             # degrees; chosen arc's clockwise start
    arc_span: float              # degrees; chosen arc's width (∝ weight)
    provenance: GameResult


def _arc_layout(weights: Sequence[float]) -> list[tuple[float, float]]:
    """Return ``[(start_deg, span_deg), ...]`` proportional to weights, summing
    to 360. Zero-weight segments get a zero-width arc (never landable)."""
    total = float(sum(weights))
    if total <= 0:
        raise GameError("sum of segment weights must be > 0")
    arcs: list[tuple[float, float]] = []
    cursor = 0.0
    for w in weights:
        span = (float(w) / total) * _FULL_TURN
        arcs.append((cursor, span))
        cursor += span
    return arcs


class SpinTheWheel:
    """A provably-fair weighted wheel.

    :param segments: list of :class:`WheelSegment`. Order is the visual order on
        the overlay (arc i starts where arc i-1 ended).
    :param rng: the shared :class:`ProvablyFairRNG`.
    :param allow_lose_all: gate for the AT-4 ``lose ALL points`` consequence. When
        ``False`` (default) any ``LOSE_ALL`` segment is excluded from selection
        (effective weight 0) — it can render on the wheel but can never be won.
    """

    def __init__(
        self,
        segments: Sequence[WheelSegment],
        *,
        rng: ProvablyFairRNG | None = None,
        allow_lose_all: bool = False,
    ) -> None:
        segs = self._coerce_segments(segments)
        self._segments: list[WheelSegment] = segs
        self._rng = rng or ProvablyFairRNG()
        self._allow_lose_all = bool(allow_lose_all)

        # Visual arcs use the DECLARED weights (so the wheel looks right);
        # SELECTION uses the effective weights (LOSE_ALL zeroed when gated off).
        self._visual_arcs = _arc_layout([s.weight for s in self._segments])
        self._selection_weights = self._effective_weights()
        if sum(self._selection_weights) <= 0:
            raise GameError(
                "no selectable segment (all zero-weight, or only LOSE_ALL with "
                "allow_lose_all=False)"
            )
        if not self._allow_lose_all and any(
            s.consequence == LOSE_ALL for s in self._segments
        ):
            logger.info(
                "SpinTheWheel: LOSE_ALL segment present but GATED OFF "
                "(allow_lose_all=False) — not selectable"
            )

    @staticmethod
    def _coerce_segments(segments: Sequence[WheelSegment]) -> list[WheelSegment]:
        if segments is None or len(segments) == 0:
            raise GameError("segments must be a non-empty sequence")
        out: list[WheelSegment] = []
        for i, s in enumerate(segments):
            if not isinstance(s, WheelSegment):
                raise GameError(f"segment[{i}] must be a WheelSegment")
            if isinstance(s.weight, bool) or not isinstance(s.weight, (int, float)):
                raise GameError(f"segment[{i}].weight must be a number")
            wf = float(s.weight)
            if wf != wf or wf in (float("inf"), float("-inf")) or wf < 0:
                raise GameError(f"segment[{i}].weight must be finite and >= 0")
            out.append(s)
        return out

    def _effective_weights(self) -> list[float]:
        eff: list[float] = []
        for s in self._segments:
            if s.consequence == LOSE_ALL and not self._allow_lose_all:
                eff.append(0.0)  # structurally unselectable while gated
            else:
                eff.append(float(s.weight))
        return eff

    @property
    def segments(self) -> tuple[WheelSegment, ...]:
        return tuple(self._segments)

    @property
    def allow_lose_all(self) -> bool:
        return self._allow_lose_all

    def spin(
        self,
        server_seed: str,
        client_seed: str | None = None,
        nonce: int = 0,
    ) -> SegmentResult:
        """Decide the winning segment + target angle, server-side.

        The winner is ``rng.weighted_choice`` over the EFFECTIVE weights; the
        target angle is a deterministic point strictly inside the winner's
        VISUAL arc (so the overlay lands on the segment as drawn). Deterministic
        for fixed (server_seed, client_seed, nonce); ``!verify``-reproducible.
        """
        cseed = client_seed if client_seed is not None else self._rng.default_client_seed
        index = self._rng.weighted_choice(
            server_seed, cseed, nonce, self._selection_weights
        )
        seg = self._segments[index]
        arc_start, arc_span = self._visual_arcs[index]

        # Second, independent draw (nonce+1 offset via a distinct client tag) for
        # the within-arc position so the angle isn't correlated with the index
        # draw. Keep a margin from both edges.
        pos = self._rng.uniform_unit(server_seed, f"{cseed}:angle", nonce)
        usable_span = arc_span * (1.0 - 2.0 * _EDGE_MARGIN_FRAC)
        if usable_span <= 0:
            # Degenerate tiny arc — land at its centre.
            target = (arc_start + arc_span / 2.0) % _FULL_TURN
        else:
            offset = arc_span * _EDGE_MARGIN_FRAC + pos * usable_span
            target = (arc_start + offset) % _FULL_TURN

        provenance = GameResult(
            game="spin_the_wheel",
            server_seed=server_seed,
            client_seed=cseed,
            nonce=nonce,
            commit=self._rng.commit_for(server_seed),
        )
        result = SegmentResult(
            index=index,
            segment=seg,
            target_angle=target,
            arc_start=arc_start,
            arc_span=arc_span,
            provenance=provenance,
        )
        logger.info(
            "wheel spin nonce=%d -> index=%d label=%r target=%.3f° "
            "arc=[%.3f,%.3f) lose_all=%s",
            nonce, index, seg.label, target, arc_start, arc_start + arc_span,
            seg.consequence == LOSE_ALL,
        )
        return result

    def angle_in_chosen_arc(self, result: SegmentResult) -> bool:
        """True iff ``target_angle`` lies within the chosen segment's arc
        (the overlay invariant; asserted in tests)."""
        start = result.arc_start
        end = result.arc_start + result.arc_span
        ang = result.target_angle
        # Normalize for the wrap-around case (arc straddling 360->0).
        if end <= _FULL_TURN:
            return start <= ang < end or (ang == start)
        # Wrapped arc.
        return ang >= start or ang < (end - _FULL_TURN)


@dataclass(frozen=True)
class SlotsResult:
    """The outcome of one slots pull."""

    reels: tuple[str, ...]       # the symbol landed on each reel
    indices: tuple[int, ...]     # the chosen index per reel
    is_win: bool                 # all reels equal
    win_symbol: str | None    # the matched symbol when is_win, else None
    provenance: GameResult


class Slots:
    """A simple N-reel slot machine over a shared symbol set.

    Each reel independently draws a symbol from ``symbols`` via a distinct nonce
    derived from the base nonce and the reel index, so all three reels come from
    ONE provably-fair seed/round. A win is all reels showing the same symbol.
    """

    def __init__(
        self,
        symbols: Sequence[str],
        *,
        reels: int = 3,
        rng: ProvablyFairRNG | None = None,
    ) -> None:
        if symbols is None or len(symbols) < 2:
            raise GameError("symbols must have >= 2 entries")
        syms: list[str] = []
        for i, s in enumerate(symbols):
            if not isinstance(s, str) or not s:
                raise GameError(f"symbol[{i}] must be a non-empty str")
            syms.append(s)
        if isinstance(reels, bool) or not isinstance(reels, int) or reels < 1:
            raise GameError("reels must be a positive int")
        self._symbols = syms
        self._reels = int(reels)
        self._rng = rng or ProvablyFairRNG()

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._symbols)

    @property
    def reels(self) -> int:
        return self._reels

    def pull(
        self,
        server_seed: str,
        client_seed: str | None = None,
        nonce: int = 0,
    ) -> SlotsResult:
        """Spin every reel from the one provably-fair round. Deterministic for
        fixed inputs; ``!verify``-reproducible. Each reel uses a distinct
        derived client tag so reels are independent yet reproducible."""
        cseed = client_seed if client_seed is not None else self._rng.default_client_seed
        n = len(self._symbols)
        indices: list[int] = []
        landed: list[str] = []
        for r in range(self._reels):
            # Distinct, reproducible per-reel draw: tag the client seed with the
            # reel index so reel r's outcome is independent of reel r-1.
            reel_client = f"{cseed}:reel{r}"
            idx = self._rng.outcome(server_seed, reel_client, nonce, n)
            indices.append(idx)
            landed.append(self._symbols[idx])

        is_win = len(set(landed)) == 1
        win_symbol = landed[0] if is_win else None
        provenance = GameResult(
            game="slots",
            server_seed=server_seed,
            client_seed=cseed,
            nonce=nonce,
            commit=self._rng.commit_for(server_seed),
        )
        logger.info(
            "slots pull nonce=%d -> reels=%s win=%s symbol=%s",
            nonce, tuple(landed), is_win, win_symbol,
        )
        return SlotsResult(
            reels=tuple(landed),
            indices=tuple(indices),
            is_win=is_win,
            win_symbol=win_symbol,
            provenance=provenance,
        )


# ---------------------------------------------------------------------------
# HEIST — group pooled bet, provably-fair win/partial/fail outcome
# ---------------------------------------------------------------------------

class HeistOutcome(str):
    """Heist result tier."""
    WIN = "win"          # full share of the pot
    PARTIAL = "partial"  # partial payout (configurable fraction)
    FAIL = "fail"        # lose the wager


@dataclass(frozen=True)
class HeistResult:
    """The resolved outcome of one heist round."""

    outcome: str                  # HeistOutcome.WIN / PARTIAL / FAIL
    participants: tuple[str, ...]  # login names that joined
    pot: int                       # total wager pooled
    payout_per_head: int           # coins each participant receives (0 on fail)
    all_in_wipe: bool              # True iff the AT-4 all-in wipe fired
    provenance: GameResult


class Heist:
    """Group pooled bet with provably-fair three-way outcome.

    Thresholds (win_threshold, partial_threshold) are draw values in [0,1);
    a draw >= win_threshold -> WIN, >= partial_threshold -> PARTIAL, else FAIL.
    Default win_threshold=0.60, partial_threshold=0.30.

    allow_lose_all=False (AT-4 default): the all-in wipe path is structurally
    inert — FAIL still returns payout_per_head=0 but no balance-wipe signal.
    allow_lose_all=True: a FAIL also sets all_in_wipe=True so the caller can
    zero every participant's balance (the caller controls ledger writes).

    RNG is injected; no randomness in this class.
    """

    def __init__(
        self,
        *,
        rng: Optional[ProvablyFairRNG] = None,
        win_threshold: float = 0.60,
        partial_threshold: float = 0.30,
        partial_fraction: float = 0.50,
        house_bonus_pct: float = 0.0,
        allow_lose_all: bool = False,
    ) -> None:
        if not (0.0 < partial_threshold < win_threshold <= 1.0):
            raise GameError(
                "thresholds must satisfy 0 < partial_threshold < win_threshold <= 1"
            )
        if not (0.0 < partial_fraction <= 1.0):
            raise GameError("partial_fraction must be in (0, 1]")
        if house_bonus_pct < 0.0 or house_bonus_pct != house_bonus_pct:
            raise GameError("house_bonus_pct must be a finite value >= 0")
        self._rng = rng or ProvablyFairRNG()
        self._win_threshold = float(win_threshold)
        self._partial_threshold = float(partial_threshold)
        self._partial_fraction = float(partial_fraction)
        # The house tops the pot up by this fraction BEFORE the per-head split on a
        # WIN/PARTIAL, so a win pays more than a player's own stake (a pure
        # sum-of-stakes pot splits back to break-even). Default 0.0 keeps every
        # existing caller (the redeem router, tests) byte-identical.
        self._house_bonus_pct = float(house_bonus_pct)
        self._allow_lose_all = bool(allow_lose_all)

    @property
    def allow_lose_all(self) -> bool:
        return self._allow_lose_all

    @property
    def house_bonus_pct(self) -> float:
        return self._house_bonus_pct

    def resolve(
        self,
        server_seed: str,
        participants: Sequence[str],
        pot: int,
        client_seed: Optional[str] = None,
        nonce: int = 0,
    ) -> HeistResult:
        """Resolve the heist for the given participants and pot.

        :param server_seed: the round's secret seed (hex).
        :param participants: login names of chatters who joined.
        :param pot: total points wagered.
        :param client_seed: viewer-supplied seed (optional).
        :param nonce: per-round nonce.
        """
        if not participants:
            raise GameError("heist needs at least one participant")
        if pot < 0:
            raise GameError("pot must be >= 0")

        cseed = client_seed if client_seed is not None else self._rng.default_client_seed
        draw = self._rng.uniform_unit(server_seed, cseed, nonce)

        # The house tops the pot up before the per-head split so a WIN pays out
        # more than a player's own stake (a pure sum-of-stakes pot is break-even).
        bonused_pot = int(pot * (1.0 + self._house_bonus_pct))

        if draw >= self._win_threshold:
            outcome = HeistOutcome.WIN
            per_head = bonused_pot // max(len(participants), 1)
            all_in_wipe = False
        elif draw >= self._partial_threshold:
            outcome = HeistOutcome.PARTIAL
            partial_pot = int(bonused_pot * self._partial_fraction)
            per_head = partial_pot // max(len(participants), 1)
            all_in_wipe = False
        else:
            outcome = HeistOutcome.FAIL
            per_head = 0
            all_in_wipe = self._allow_lose_all

        provenance = GameResult(
            game="heist",
            server_seed=server_seed,
            client_seed=cseed,
            nonce=nonce,
            commit=self._rng.commit_for(server_seed),
        )
        logger.info(
            "heist nonce=%d draw=%.4f outcome=%s participants=%d pot=%d "
            "per_head=%d all_in_wipe=%s",
            nonce, draw, outcome, len(participants), pot, per_head, all_in_wipe,
        )
        return HeistResult(
            outcome=outcome,
            participants=tuple(participants),
            pot=pot,
            payout_per_head=per_head,
            all_in_wipe=all_in_wipe,
            provenance=provenance,
        )


# ---------------------------------------------------------------------------
# DUEL — 1v1 challenge, RNG winner, loser pays challenger
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DuelResult:
    """The resolved outcome of one duel."""

    winner: str            # login name of the winner
    loser: str             # login name of the loser
    wager: int             # points transferred loser -> winner
    challenger: str        # who issued the challenge
    target: str            # who was challenged
    provenance: GameResult


class Duel:
    """1v1 provably-fair duel.

    The challenger bets ``wager`` points against the target. A single RNG
    draw in [0, 1) decides the winner: draw < 0.5 -> challenger wins,
    else target wins. (Equal probability; adjust win_bias to shift odds.)

    RNG is injected; no state stored between duels.
    """

    def __init__(
        self,
        *,
        rng: Optional[ProvablyFairRNG] = None,
        win_bias: float = 0.5,
    ) -> None:
        if not (0.0 < win_bias < 1.0):
            raise GameError("win_bias must be in (0, 1) exclusive")
        self._rng = rng or ProvablyFairRNG()
        self._win_bias = float(win_bias)

    def resolve(
        self,
        server_seed: str,
        challenger: str,
        target: str,
        wager: int,
        client_seed: Optional[str] = None,
        nonce: int = 0,
    ) -> DuelResult:
        """Resolve a duel between challenger and target.

        :param server_seed: the round's secret seed (hex).
        :param challenger: login of the chatter who issued ``!duel <target>``.
        :param target: login of the challenged chatter.
        :param wager: points at stake.
        """
        if not challenger or not target:
            raise GameError("challenger and target must be non-empty strings")
        if challenger == target:
            raise GameError("challenger and target must be different users")
        if wager < 0:
            raise GameError("wager must be >= 0")

        cseed = client_seed if client_seed is not None else self._rng.default_client_seed
        draw = self._rng.uniform_unit(server_seed, cseed, nonce)

        if draw < self._win_bias:
            winner, loser = challenger, target
        else:
            winner, loser = target, challenger

        provenance = GameResult(
            game="duel",
            server_seed=server_seed,
            client_seed=cseed,
            nonce=nonce,
            commit=self._rng.commit_for(server_seed),
        )
        logger.info(
            "duel nonce=%d draw=%.4f winner=%r loser=%r wager=%d",
            nonce, draw, winner, loser, wager,
        )
        return DuelResult(
            winner=winner,
            loser=loser,
            wager=wager,
            challenger=challenger,
            target=target,
            provenance=provenance,
        )


# ---------------------------------------------------------------------------
# TRIVIA — curated Q&A pool, first correct answer wins
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TriviaQuestion:
    """One trivia question + answer."""

    question: str
    answer: str          # casefolded, stripped — compared via casefold+strip


# Curated Valorant/gaming trivia pool (at least 10 questions, baked in).
_TRIVIA_POOL: tuple[TriviaQuestion, ...] = (
    TriviaQuestion("How many rounds does it take to win a standard Valorant match?", "13"),
    TriviaQuestion("What is the name of Jett's ultimate ability?", "blade storm"),
    TriviaQuestion("Which agent can resurrect a fallen ally?", "sage"),
    TriviaQuestion("What is the buy phase timer in Valorant (in seconds)?", "30"),
    TriviaQuestion("What is the name of Omen's ultimate ability?", "from the shadows"),
    TriviaQuestion("Which Valorant map is set in Morocco?", "pearl"),
    TriviaQuestion("How many agents are in each team during a match?", "5"),
    TriviaQuestion("What is the name of Reyna's heal ability?", "devour"),
    TriviaQuestion("What weapon fires the most bullets per second in Valorant?", "stinger"),
    TriviaQuestion("Which agent uses a drone for scouting?", "sova"),
    TriviaQuestion("What is the default plant time for the Spike in seconds?", "4"),
    TriviaQuestion("Which map was the first to be added after the game launched?", "icebox"),
)


@dataclass(frozen=True)
class TriviaResult:
    """The outcome of one trivia question."""

    winner: Optional[str]      # login of the first correct answerer, or None (timed out)
    question: TriviaQuestion
    question_index: int        # index into the pool (provably-fair draw)
    pot: int                   # points won
    provenance: GameResult


class Trivia:
    """Ultron asks a question drawn from the curated pool; first correct answer wins.

    Answer matching uses casefold+strip (no fuzzy — answers are short keywords).
    The question is selected via a provably-fair draw from the pool.
    """

    def __init__(
        self,
        *,
        rng: Optional[ProvablyFairRNG] = None,
        pool: Optional[Sequence[TriviaQuestion]] = None,
    ) -> None:
        loaded = list(pool) if pool is not None else list(_TRIVIA_POOL)
        if len(loaded) < 1:
            raise GameError("trivia pool must have at least 1 question")
        for i, q in enumerate(loaded):
            if not isinstance(q, TriviaQuestion):
                raise GameError(f"pool[{i}] must be a TriviaQuestion")
        self._pool = loaded
        self._rng = rng or ProvablyFairRNG()

    @property
    def pool(self) -> tuple[TriviaQuestion, ...]:
        return tuple(self._pool)

    def draw_question(
        self,
        server_seed: str,
        client_seed: Optional[str] = None,
        nonce: int = 0,
    ) -> tuple[TriviaQuestion, int, GameResult]:
        """Select a question provably-fairly. Returns (question, index, provenance)."""
        cseed = client_seed if client_seed is not None else self._rng.default_client_seed
        idx = self._rng.outcome(server_seed, cseed, nonce, len(self._pool))
        prov = GameResult(
            game="trivia",
            server_seed=server_seed,
            client_seed=cseed,
            nonce=nonce,
            commit=self._rng.commit_for(server_seed),
        )
        return self._pool[idx], idx, prov

    def check_answer(self, question: TriviaQuestion, answer: str) -> bool:
        """True iff answer matches (casefold+strip)."""
        return question.answer.casefold().strip() == answer.casefold().strip()

    def resolve(
        self,
        server_seed: str,
        winner_login: Optional[str],
        pot: int,
        client_seed: Optional[str] = None,
        nonce: int = 0,
    ) -> TriviaResult:
        """Build the final TriviaResult once the winner (or timeout) is known.

        :param winner_login: login of the first correct answerer, or None on timeout.
        :param pot: points awarded to the winner (0 on timeout).
        """
        question, idx, prov = self.draw_question(server_seed, client_seed, nonce)
        logger.info(
            "trivia nonce=%d question_idx=%d winner=%r pot=%d",
            nonce, idx, winner_login, pot,
        )
        return TriviaResult(
            winner=winner_login,
            question=question,
            question_index=idx,
            pot=pot,
            provenance=prov,
        )


# ---------------------------------------------------------------------------
# RAFFLE — timed entry window, provably-fair winner draw
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RaffleResult:
    """The outcome of one raffle draw."""

    winner: Optional[str]       # login of the winner, or None if no entries
    entrants: tuple[str, ...]   # all unique entrants at close time
    provenance: GameResult


class Raffle:
    """Timed entry window raffle with provably-fair winner draw.

    Chatters call ``!raffle`` (or ``!enter``) to join. After the window closes,
    :meth:`draw` selects one winner uniformly from unique entrants.

    The Raffle object is stateful: open a round with :meth:`open`, add entrants
    with :meth:`enter`, close with :meth:`draw` (which also resets state).
    """

    def __init__(
        self,
        *,
        rng: Optional[ProvablyFairRNG] = None,
        window_s: float = 60.0,
    ) -> None:
        if window_s <= 0:
            raise GameError("window_s must be > 0")
        self._rng = rng or ProvablyFairRNG()
        self._window_s = float(window_s)
        self._entrants: list[str] = []
        self._open: bool = False
        self._deadline: float = 0.0

    @property
    def is_open(self) -> bool:
        """True if the entry window is currently open."""
        return self._open and time.monotonic() < self._deadline

    @property
    def entrants(self) -> tuple[str, ...]:
        return tuple(self._entrants)

    def open(self, *, window_s: Optional[float] = None) -> float:
        """Open a new raffle entry window. Returns the deadline (monotonic)."""
        if self._open:
            raise GameError("a raffle is already open; draw first")
        self._entrants = []
        self._open = True
        self._deadline = time.monotonic() + (window_s if window_s is not None else self._window_s)
        logger.info("raffle opened window_s=%.1f deadline=%.3f", self._window_s, self._deadline)
        return self._deadline

    def enter(self, login: str) -> bool:
        """Add a chatter to the raffle. Returns True if added (False if duplicate
        or window closed). Duplicate entries are silently de-duped."""
        if not self.is_open:
            return False
        if not login or not isinstance(login, str):
            return False
        low = login.casefold().strip()
        if not low:
            return False
        if low not in self._entrants:
            self._entrants.append(low)
            return True
        return False  # already entered — silent no-op

    def draw(
        self,
        server_seed: str,
        client_seed: Optional[str] = None,
        nonce: int = 0,
    ) -> RaffleResult:
        """Close the window and draw a winner. Resets the raffle for the next round.

        Returns a RaffleResult with winner=None if no entrants.
        """
        self._open = False
        entrants = list(self._entrants)
        self._entrants = []
        self._deadline = 0.0

        cseed = client_seed if client_seed is not None else self._rng.default_client_seed
        prov = GameResult(
            game="raffle",
            server_seed=server_seed,
            client_seed=cseed,
            nonce=nonce,
            commit=self._rng.commit_for(server_seed),
        )

        if not entrants:
            logger.info("raffle nonce=%d draw -> no entrants", nonce)
            return RaffleResult(winner=None, entrants=(), provenance=prov)

        idx = self._rng.outcome(server_seed, cseed, nonce, len(entrants))
        winner = entrants[idx]
        logger.info(
            "raffle nonce=%d entrants=%d winner=%r",
            nonce, len(entrants), winner,
        )
        return RaffleResult(
            winner=winner,
            entrants=tuple(entrants),
            provenance=prov,
        )
