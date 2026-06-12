"""Passthrough condenser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from kenning.llm.condensers.base import (
    CondenseResult,
    Condenser,
    Turn,
    char_count_tokens_for_turns,
)


@dataclass
class NoOpCondenser(Condenser):
    """Return the input history unchanged.

    Useful as the voice-path default + a baseline against which other
    strategies can be benchmarked. Always returns ``dropped_turn_count=0``.
    """

    kind: str = "noop"

    def condense(
        self,
        turns: Sequence[Turn],
        *,
        context: dict[str, Any] | None = None,
    ) -> CondenseResult:
        tokens = char_count_tokens_for_turns(turns)
        return CondenseResult(
            turns=tuple(turns),
            dropped_turn_count=0,
            summary_inserted=False,
            token_estimate_before=tokens,
            token_estimate_after=tokens,
        )
