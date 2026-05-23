"""Intelligent forgetting without an LLM call."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ultron.llm.condensers.base import (
    CondenseResult,
    Condenser,
    CondenserError,
    Turn,
    char_count_tokens_for_turns,
    turn_text,
)


@dataclass
class AmortizedCondenser(Condenser):
    """Forget turns past ``max_size`` using decision-boundary scoring.

    The strategy walks the history newest-first and keeps each turn
    until the running token budget exceeds ``max_size``. Turns whose
    content matches one of the :attr:`pin_role` roles (e.g. system /
    instruction) are always preserved regardless of position. Among
    "ordinary" turns, the keeper rule prefers user turns over
    assistant turns at equal budget (the catalog's "user intent stays
    longest" heuristic).

    No LLM call -- the entire pass is local + sub-millisecond. The
    return order matches the original chronological order.
    """

    kind: str = "amortized"
    keep_first: int = 1
    max_size: int = 100
    max_tokens: int = 4000
    pin_role: frozenset[str] = frozenset({"system"})
    prefer_role: frozenset[str] = frozenset({"user"})

    def __post_init__(self) -> None:
        if self.keep_first < 0:
            raise CondenserError("keep_first must be >= 0")
        if self.max_size < self.keep_first:
            raise CondenserError("max_size must be >= keep_first")
        if self.max_tokens < 0:
            raise CondenserError("max_tokens must be >= 0")

    def condense(
        self,
        turns: Sequence[Turn],
        *,
        context: dict[str, Any] | None = None,
    ) -> CondenseResult:
        tokens_before = char_count_tokens_for_turns(turns)
        n = len(turns)
        head = list(turns[: self.keep_first])

        if n <= self.max_size:
            return CondenseResult(
                turns=tuple(turns),
                dropped_turn_count=0,
                token_estimate_before=tokens_before,
                token_estimate_after=tokens_before,
            )

        # Process the remainder newest-first, preserving budget.
        remainder = list(turns[self.keep_first :])
        kept_indices: set[int] = set()
        running_tokens = 0
        # Score each turn: pin > user > assistant.
        scored = []
        for offset, turn in enumerate(remainder):
            role = turn[0] if isinstance(turn, tuple) and turn else ""
            score = 0
            if role in self.pin_role:
                score = 3
            elif role in self.prefer_role:
                score = 2
            else:
                score = 1
            # Original chronological position so we can rebuild order.
            scored.append((offset, score, turn))

        # Always-pin: preserve everything in pin_role.
        for offset, score, turn in scored:
            if score == 3:
                kept_indices.add(offset)
                running_tokens += max(1, len(turn_text(turn)) // 4)

        # Then prefer recent + preferred-role until budget runs out.
        # Iterate newest-first within the ordinary set.
        ordinary = [(offset, score, turn) for offset, score, turn in scored if score < 3]
        ordinary.sort(key=lambda item: (-item[0], -item[1]))
        for offset, score, turn in ordinary:
            if len(kept_indices) + len(head) >= self.max_size:
                break
            cost = max(1, len(turn_text(turn)) // 4)
            if running_tokens + cost > self.max_tokens:
                continue
            kept_indices.add(offset)
            running_tokens += cost

        kept_indices_sorted = sorted(kept_indices)
        result_turns = head + [remainder[i] for i in kept_indices_sorted]
        dropped = n - len(result_turns)
        tokens_after = char_count_tokens_for_turns(result_turns)
        return CondenseResult(
            turns=tuple(result_turns),
            dropped_turn_count=dropped,
            token_estimate_before=tokens_before,
            token_estimate_after=tokens_after,
            notes=(
                f"kept_head={len(head)} kept_body={len(kept_indices)} "
                f"dropped={dropped} budget_tokens<={self.max_tokens}",
            ),
        )
