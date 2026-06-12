"""Binary-search prefix packing under a token budget.

Pattern lifted in spirit (not in source) from aider's repomap binary
search loop. Apache 2.0 attribution lives in ``THIRD_PARTY_NOTICES.md``.

Given a ranked list of items plus a function that renders the first
``k`` of them to text, find the largest ``k`` such that the rendered
text's token count fits inside ``max_tokens``. Useful anywhere kenning
packs ranked items into an LLM prompt: repo-map symbols, RAG snippets,
recent-turn history, search results.

Why binary search rather than rendering once: items vary wildly in
render cost (a one-line constant vs. a long function header with
docstring). Greedy "add one at a time, count tokens" is correct but
O(n^2) on the token counter, which dominates wall time for long lists.
Binary search is O(log n) calls to the counter — typically 8-10
iterations to converge within the tolerance band, against a 1000-item
list that greedy would have rendered all 1000 times.

The catalog also calls out a 15 % tolerance band: stop when the result
fits in ``[max_tokens * (1 - tol), max_tokens]``. Saves iterations once
the answer is "close enough" — the alternative is bouncing one item
either side of the budget on every call.

Public surface:

  * :func:`pack_to_budget` — returns the chosen ``k``.
  * :class:`PackResult` — frozen dataclass with ``k`` plus telemetry
    (iterations, final token count, terminated_early).
  * :class:`BudgetTooSmallError` — when even one item exceeds budget
    AND the caller asked for ``strict=True``. Non-strict simply
    returns ``k=0``.

Thread safety: pure function, no shared state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Optional, Sequence, TypeVar


T = TypeVar("T")


class BudgetTooSmallError(Exception):
    """Raised in strict mode when no items fit at all."""


@dataclass(frozen=True)
class PackResult:
    """Outcome of one :func:`pack_to_budget` call.

    Attributes:
        k: Number of items the caller should use (``items[:k]``).
        token_count: Tokens used by the final rendering. 0 when ``k==0``.
        iterations: Binary search iterations executed.
        terminated_early: True when the tolerance band was hit before
            the search exhausted ``max_iterations``.
    """

    k: int
    token_count: int
    iterations: int
    terminated_early: bool


def pack_to_budget(
    items: Sequence[T],
    render: Callable[[Sequence[T]], str],
    count_tokens: Callable[[str], int],
    max_tokens: int,
    *,
    tolerance: float = 0.15,
    max_iterations: int = 30,
    strict: bool = False,
) -> PackResult:
    """Binary-search the largest prefix of ``items`` that fits in
    ``max_tokens`` when rendered.

    Args:
        items: Ranked sequence to prefix-select from. Item at index 0
            is highest priority.
        render: Callable ``(prefix) -> str``. Must be deterministic on
            the same prefix. Receives a slice of ``items`` (length
            ``k``).
        count_tokens: Callable ``(str) -> int``. Tokens used by the
            rendering. Caller's responsibility to provide a fast
            counter (a model tokenizer call is fine; per-call cost is
            paid ``iterations`` times).
        max_tokens: Hard ceiling on the token count of the rendered
            prefix.
        tolerance: Fractional band below ``max_tokens`` at which the
            search terminates early. ``0.15`` accepts anything in
            ``[max_tokens * 0.85, max_tokens]``. Set to ``0`` to
            insist on the exact maximum (more iterations).
        max_iterations: Hard cap on search iterations regardless of
            convergence. Defaults to 30 — empirically enough for
            millions of items.
        strict: When True, raise :class:`BudgetTooSmallError` if not
            even one item fits. When False (default), return ``k=0``.

    Returns:
        A :class:`PackResult` describing the chosen prefix.

    Raises:
        BudgetTooSmallError: only when ``strict=True`` and item 0
            already exceeds ``max_tokens``.
        ValueError: when arguments are out of range (negative budget,
            tolerance outside ``[0, 1)``).
    """
    if max_tokens < 0:
        raise ValueError(f"max_tokens must be >= 0, got {max_tokens}")
    if not (0 <= tolerance < 1):
        raise ValueError(
            f"tolerance must be in [0, 1), got {tolerance}"
        )
    if max_iterations < 1:
        raise ValueError(
            f"max_iterations must be >= 1, got {max_iterations}"
        )

    n = len(items)
    if n == 0 or max_tokens == 0:
        return PackResult(k=0, token_count=0, iterations=0, terminated_early=False)

    lower_band = int(max_tokens * (1.0 - tolerance))

    # Quick check: does even item 0 fit? If not, strict caller raises;
    # non-strict returns k=0 immediately.
    smallest = count_tokens(render(items[:1]))
    if smallest > max_tokens:
        if strict:
            raise BudgetTooSmallError(
                f"Item 0 alone uses {smallest} tokens, exceeds budget {max_tokens}"
            )
        return PackResult(
            k=0,
            token_count=0,
            iterations=1,
            terminated_early=True,
        )

    # Best-known fitting k and its measured count. Initialised with the
    # single-item probe we just measured.
    best_k = 1
    best_tokens = smallest

    # If everything fits, no search needed.
    if n == 1:
        return PackResult(
            k=1,
            token_count=smallest,
            iterations=1,
            terminated_early=False,
        )

    full = count_tokens(render(items))
    iterations = 2
    if full <= max_tokens:
        return PackResult(
            k=n,
            token_count=full,
            iterations=iterations,
            terminated_early=False,
        )

    # Standard binary search on [1, n).
    lo, hi = 1, n
    while lo < hi - 1 and iterations < max_iterations:
        mid = (lo + hi) // 2
        rendered = render(items[:mid])
        used = count_tokens(rendered)
        iterations += 1
        if used <= max_tokens:
            best_k = mid
            best_tokens = used
            lo = mid
            if used >= lower_band:
                # Inside the tolerance band; stop early.
                return PackResult(
                    k=best_k,
                    token_count=best_tokens,
                    iterations=iterations,
                    terminated_early=True,
                )
        else:
            hi = mid

    return PackResult(
        k=best_k,
        token_count=best_tokens,
        iterations=iterations,
        terminated_early=False,
    )


def char_count_tokens(text: str) -> int:
    """Cheap default token counter: characters / 4 (English heuristic).

    Provided for unit tests and for callers that don't have a real
    tokenizer wired up. Real callers should pass their LLM's actual
    tokenizer.
    """
    return max(1, len(text) // 4) if text else 0
