"""Summarise the dropped middle of the history via an injected LLM call.

The most aggressive strategy in the catalogue. When the history
exceeds :attr:`max_size`, the condenser asks the injected
``summarize_fn`` to compress the dropped-middle turns into a single
synthesised summary turn, then returns ``[head, summary, tail]``.

The condenser does NOT load an LLM; the caller supplies a
``summarize_fn(text) -> str`` callable. This keeps the strategy
free of the in-process llama dependency and lets the orchestrator
choose where the summary call lands (foreground / background / off
to a smaller model).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from ultron.llm.condensers.base import (
    CondenseResult,
    Condenser,
    CondenserError,
    Turn,
    char_count_tokens_for_turns,
    turn_text,
)

logger = logging.getLogger(__name__)


def _default_summary_preamble() -> str:
    return (
        "Summary of earlier conversation -- key decisions, open questions, "
        "and ongoing context. Use this in place of the elided turns."
    )


@dataclass
class LLMSummarizingCondenser(Condenser):
    """Fold the dropped middle into one synthesised summary turn.

    Args:
        summarize_fn: A callable accepting a string and returning a
            string. The caller owns the LLM lifecycle.
        max_size: Trigger threshold; when ``len(turns) > max_size`` the
            condenser fires.
        keep_first: Leading turns always preserved (e.g. the task
            statement).
        keep_last: Trailing turns always preserved.
        summary_role: Role assigned to the synthesised summary turn.
        summary_preamble: Prefix prepended to the summary body so the
            model knows what it's reading.
    """

    kind: str = "llm_summarizing"
    summarize_fn: Callable[[str], str] | None = None
    max_size: int = 240
    keep_first: int = 2
    keep_last: int = 30
    summary_role: str = "system"
    summary_preamble: str = ""

    def __post_init__(self) -> None:
        if self.keep_first < 0 or self.keep_last < 0:
            raise CondenserError("keep_first / keep_last must be >= 0")
        if self.max_size <= self.keep_first + self.keep_last:
            # Trigger never fires; degenerates to NoOp. Allowed but worth a note.
            logger.debug(
                "LLMSummarizingCondenser: max_size=%d below keep_first+keep_last=%d; "
                "condenser will never compress",
                self.max_size,
                self.keep_first + self.keep_last,
            )
        if not self.summary_preamble:
            self.summary_preamble = _default_summary_preamble()

    def condense(
        self,
        turns: Sequence[Turn],
        *,
        context: dict[str, Any] | None = None,
    ) -> CondenseResult:
        tokens_before = char_count_tokens_for_turns(turns)
        n = len(turns)
        if n <= self.max_size:
            return CondenseResult(
                turns=tuple(turns),
                dropped_turn_count=0,
                token_estimate_before=tokens_before,
                token_estimate_after=tokens_before,
            )

        head = list(turns[: self.keep_first])
        tail = list(turns[n - self.keep_last :]) if self.keep_last > 0 else []
        middle = list(turns[self.keep_first : n - self.keep_last])

        if not middle or self.summarize_fn is None:
            # No summariser wired OR nothing to summarise. Degrade to
            # a Recent-style drop with no summary turn.
            return CondenseResult(
                turns=tuple(head + tail),
                dropped_turn_count=len(middle),
                summary_inserted=False,
                token_estimate_before=tokens_before,
                token_estimate_after=char_count_tokens_for_turns(head + tail),
                notes=("no summarize_fn; head+tail emitted without summary",),
                error="summarize_fn missing" if self.summarize_fn is None else None,
            )

        middle_text = "\n".join(
            f"[{turn[0] if isinstance(turn, tuple) and turn else 'unknown'}] "
            f"{turn_text(turn)}"
            for turn in middle
        )
        try:
            summary_body = self.summarize_fn(middle_text)
        except Exception as exc:                                # noqa: BLE001
            logger.warning("LLMSummarizingCondenser: summarize_fn raised %r", exc)
            return CondenseResult(
                turns=tuple(head + tail),
                dropped_turn_count=len(middle),
                summary_inserted=False,
                token_estimate_before=tokens_before,
                token_estimate_after=char_count_tokens_for_turns(head + tail),
                notes=("summarize_fn raised; head+tail emitted",),
                error=f"summarize_fn raised: {type(exc).__name__}: {exc}",
            )
        if not isinstance(summary_body, str) or not summary_body.strip():
            # Empty / non-string summary -- treat as failure, fall back.
            return CondenseResult(
                turns=tuple(head + tail),
                dropped_turn_count=len(middle),
                summary_inserted=False,
                token_estimate_before=tokens_before,
                token_estimate_after=char_count_tokens_for_turns(head + tail),
                notes=("summarize_fn returned empty; head+tail emitted",),
                error="summarize_fn returned empty",
            )

        synthesised = f"{self.summary_preamble}\n\n{summary_body.strip()}"
        result = head + [(self.summary_role, synthesised)] + tail
        tokens_after = char_count_tokens_for_turns(result)
        return CondenseResult(
            turns=tuple(result),
            dropped_turn_count=len(middle),
            summary_inserted=True,
            token_estimate_before=tokens_before,
            token_estimate_after=tokens_after,
            notes=(
                f"summarised={len(middle)} head={len(head)} tail={len(tail)} "
                f"summary_chars={len(synthesised)}",
            ),
        )
