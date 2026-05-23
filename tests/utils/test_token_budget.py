"""Tests for :mod:`ultron.utils.token_budget`."""

from __future__ import annotations

import pytest

from ultron.utils.token_budget import (
    BudgetTooSmallError,
    PackResult,
    char_count_tokens,
    pack_to_budget,
)


def _render_first_k(items):
    """Render helper that just concatenates the items as strings."""
    return "".join(str(x) for x in items)


def test_empty_items_returns_zero():
    result = pack_to_budget([], _render_first_k, char_count_tokens, max_tokens=100)
    assert result.k == 0
    assert result.token_count == 0


def test_zero_budget_returns_zero():
    result = pack_to_budget(["a", "b"], _render_first_k, char_count_tokens, max_tokens=0)
    assert result.k == 0


def test_all_items_fit_returns_n():
    items = ["aaaa"] * 5  # 20 chars total ≈ 5 tokens
    result = pack_to_budget(
        items, _render_first_k, char_count_tokens, max_tokens=100
    )
    assert result.k == 5
    assert result.token_count > 0


def test_single_item_too_big_strict_raises():
    items = ["x" * 1000]  # >> budget
    with pytest.raises(BudgetTooSmallError):
        pack_to_budget(items, _render_first_k, char_count_tokens, max_tokens=10, strict=True)


def test_single_item_too_big_non_strict_returns_zero():
    items = ["x" * 1000]
    result = pack_to_budget(items, _render_first_k, char_count_tokens, max_tokens=10)
    assert result.k == 0
    assert result.terminated_early is True


def test_negative_budget_raises():
    with pytest.raises(ValueError):
        pack_to_budget(["a"], _render_first_k, char_count_tokens, max_tokens=-1)


def test_tolerance_out_of_range_raises():
    with pytest.raises(ValueError):
        pack_to_budget(
            ["a"], _render_first_k, char_count_tokens, max_tokens=10, tolerance=1.5
        )
    with pytest.raises(ValueError):
        pack_to_budget(
            ["a"], _render_first_k, char_count_tokens, max_tokens=10, tolerance=-0.1
        )


def test_max_iterations_must_be_positive():
    with pytest.raises(ValueError):
        pack_to_budget(
            ["a"], _render_first_k, char_count_tokens, max_tokens=10, max_iterations=0
        )


def test_binary_search_picks_largest_fitting_prefix():
    # 50 items of 4 chars each; budget admits roughly 10 items.
    items = ["abcd"] * 50
    max_tokens = 11  # 11 tokens × 4 chars-per-token = ~44 chars total
    result = pack_to_budget(items, _render_first_k, char_count_tokens, max_tokens=max_tokens)
    # The rendered count of items[:k] must not exceed budget.
    used = char_count_tokens(_render_first_k(items[: result.k]))
    assert used <= max_tokens
    # And items[:k+1] should exceed the budget (else we left value on the table).
    if result.k < len(items):
        over = char_count_tokens(_render_first_k(items[: result.k + 1]))
        assert over > max_tokens or result.terminated_early


def test_tolerance_terminates_early():
    items = ["aaaa"] * 200
    # With a wide tolerance, the loop should terminate before exhausting iterations.
    result = pack_to_budget(
        items,
        _render_first_k,
        char_count_tokens,
        max_tokens=80,
        tolerance=0.30,
    )
    assert result.iterations < 30
    assert result.k > 0


def test_iteration_count_capped():
    items = ["aaaa"] * 1000
    result = pack_to_budget(
        items,
        _render_first_k,
        char_count_tokens,
        max_tokens=50,
        tolerance=0.0,
        max_iterations=5,
    )
    assert result.iterations <= 5


def test_pack_result_is_frozen():
    r = PackResult(k=1, token_count=2, iterations=3, terminated_early=False)
    with pytest.raises(Exception):
        r.k = 99  # type: ignore[misc]


def test_char_count_tokens_simple():
    assert char_count_tokens("") == 0
    assert char_count_tokens("abcd") == 1
    assert char_count_tokens("a" * 40) == 10
