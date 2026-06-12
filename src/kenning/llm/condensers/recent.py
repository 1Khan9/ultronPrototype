"""Keep the first ``keep_first`` + the last ``max_events - keep_first`` turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ultron.llm.condensers.base import (
    CondenseResult,
    Condenser,
    CondenserError,
    Turn,
    char_count_tokens_for_turns,
)


@dataclass
class RecentCondenser(Condenser):
    """Drop the middle of the history, keeping the head + the tail.

    Args:
        keep_first: Number of leading turns to always preserve. Usually
            1-2 -- enough to keep the task instruction in front of the
            model.
        max_events: Upper bound on the returned turn count. Includes
            ``keep_first`` in the budget; the tail length is
            ``max_events - keep_first``.
    """

    kind: str = "recent"
    keep_first: int = 1
    max_events: int = 20

    def __post_init__(self) -> None:
        if self.keep_first < 0:
            raise CondenserError("keep_first must be >= 0")
        if self.max_events < self.keep_first:
            raise CondenserError("max_events must be >= keep_first")

    def condense(
        self,
        turns: Sequence[Turn],
        *,
        context: dict[str, Any] | None = None,
    ) -> CondenseResult:
        tokens_before = char_count_tokens_for_turns(turns)
        n = len(turns)
        if n <= self.max_events:
            return CondenseResult(
                turns=tuple(turns),
                dropped_turn_count=0,
                token_estimate_before=tokens_before,
                token_estimate_after=tokens_before,
            )

        head = list(turns[: self.keep_first])
        tail_budget = self.max_events - self.keep_first
        tail = list(turns[n - tail_budget :]) if tail_budget > 0 else []
        dropped = n - (len(head) + len(tail))
        result_turns = head + tail
        tokens_after = char_count_tokens_for_turns(result_turns)
        return CondenseResult(
            turns=tuple(result_turns),
            dropped_turn_count=dropped,
            token_estimate_before=tokens_before,
            token_estimate_after=tokens_after,
            notes=(f"kept head={len(head)} tail={len(tail)} dropped={dropped}",),
        )
