"""Mask older tool/observation content while preserving turn structure."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from kenning.llm.condensers.base import (
    CondenseResult,
    Condenser,
    CondenserError,
    Turn,
    char_count_tokens_for_turns,
    turn_text,
)

DEFAULT_MASK_TEMPLATE = "[Earlier observation elided -- {chars} chars]"
"""Default replacement string when a turn is masked."""


@dataclass
class ObservationMaskingCondenser(Condenser):
    """Keep the conversation skeleton but blank old tool outputs.

    Strategy:
        * Newest ``attention_window`` turns are passed through unchanged.
        * Older turns retain their ``role`` but the content is replaced
          with :attr:`mask_template`'s rendered form. The model still
          sees that "X tool ran" but doesn't re-pay for the tool's
          stdout.

    The catalog's specific behaviour mentions "older observations" --
    we generalise to any turn whose role matches :attr:`mask_roles`
    (default: tool / system). Override per-call if a different role
    set should be masked.
    """

    kind: str = "observation_masking"
    attention_window: int = 6
    mask_roles: frozenset[str] = frozenset({"tool", "system", "observation"})
    mask_template: str = DEFAULT_MASK_TEMPLATE
    masked_role_label: str | None = None  # if set, replaces the role on masked turns

    def __post_init__(self) -> None:
        if self.attention_window < 0:
            raise CondenserError("attention_window must be >= 0")

    def condense(
        self,
        turns: Sequence[Turn],
        *,
        context: dict[str, Any] | None = None,
    ) -> CondenseResult:
        tokens_before = char_count_tokens_for_turns(turns)
        n = len(turns)
        if n <= self.attention_window:
            return CondenseResult(
                turns=tuple(turns),
                dropped_turn_count=0,
                token_estimate_before=tokens_before,
                token_estimate_after=tokens_before,
            )

        window_start = n - self.attention_window
        result: list[Turn] = []
        masked_count = 0
        for index, turn in enumerate(turns):
            role = turn[0] if isinstance(turn, tuple) and turn else ""
            if index >= window_start or role not in self.mask_roles:
                result.append(turn)
                continue
            original = turn_text(turn)
            masked_role = self.masked_role_label or role
            masked_text = self.mask_template.format(
                chars=len(original),
                role=role,
            )
            result.append((masked_role, masked_text))
            masked_count += 1

        tokens_after = char_count_tokens_for_turns(result)
        return CondenseResult(
            turns=tuple(result),
            dropped_turn_count=0,
            token_estimate_before=tokens_before,
            token_estimate_after=tokens_after,
            notes=(f"masked={masked_count} window={self.attention_window}",),
        )
