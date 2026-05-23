"""Condenser ABC + shared types + token-count helpers.

A :class:`Turn` is a thin ``(role, content)`` value type matching the
existing ``ultron.llm.inference.Turn`` shape. Sticking with the same
tuple-shaped record means call sites can pass their existing history
list to a condenser without copying.

The :class:`Condenser` ABC has a single method ``condense(turns,
*, context=None) -> CondenseResult``. Concrete strategies subclass and
implement. The contract:

* The result's ``turns`` is the new (possibly shorter) history.
* ``dropped_turn_count`` tells the caller how many turns the
  condenser removed (useful for diagnostics).
* ``summary_inserted`` is True when the condenser folded the dropped
  turns into a synthesised summary turn (only LLMSummarizing does this
  today).
* ``error`` is populated only on partial failure; failures preferably
  raise :class:`CondenserError` so callers can fall back to the raw
  history.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)


# The ultron history representation is a plain ``(role, content)`` tuple
# (see ``ultron.llm.inference.Turn``). We mirror that here so condensers
# can be slotted into ``_build_messages`` without a value-type rewrite.
Turn = tuple[str, str]


class CondenserError(RuntimeError):
    """Raised when a condenser fails irrecoverably.

    Callers wrap ``condense`` in try/except and fall back to the raw
    history on this exception (matches the OpenHands fail-open posture).
    """


@dataclass(frozen=True)
class CondenseResult:
    """Outcome of a single ``condense`` call.

    Attributes:
        turns: The new history. May be shorter than the input.
        dropped_turn_count: Number of turns removed from the original.
        summary_inserted: ``True`` when the condenser folded the
            dropped middle into a synthesised summary turn.
        token_estimate_before: Optional char-based token estimate for
            the original history.
        token_estimate_after: Optional char-based token estimate for
            the returned history.
        notes: Free-form per-strategy diagnostics.
        error: Optional non-fatal error description; on hard failures
            the condenser should raise :class:`CondenserError` instead.
    """

    turns: tuple[Turn, ...]
    dropped_turn_count: int = 0
    summary_inserted: bool = False
    token_estimate_before: int | None = None
    token_estimate_after: int | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Condenser(ABC):
    """Pluggable history-compression strategy."""

    #: Short identifier used by the factory + audit logs.
    kind: str = "abstract"

    @abstractmethod
    def condense(
        self,
        turns: Sequence[Turn],
        *,
        context: dict[str, Any] | None = None,
    ) -> CondenseResult:
        """Return a possibly-shorter history.

        ``context`` is a free-form dict the caller may pass through
        (active intent, current user text, etc.). Strategies that don't
        need it ignore it.
        """

    @property
    def label(self) -> str:
        return f"{self.__class__.__name__}({self.kind})"


def turn_text(turn: Turn) -> str:
    """Extract the user-visible content from a :class:`Turn`."""

    if isinstance(turn, tuple) and len(turn) >= 2:
        return str(turn[1])
    return str(turn)


def char_count_tokens_for_turns(turns: Iterable[Turn]) -> int:
    """Cheap char-based token estimate (~4 chars/token English heuristic).

    Matches the :func:`ultron.utils.token_budget.char_count_tokens` shape
    so the condensers can share the same budgeting primitive used by
    the repo-map and snippet packing code.
    """

    total = 0
    for turn in turns:
        total += len(turn_text(turn))
    # ~4 chars per English token.
    return max(0, total // 4)
