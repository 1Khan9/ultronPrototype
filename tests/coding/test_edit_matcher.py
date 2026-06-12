"""Tests for :mod:`kenning.coding.edit_matcher`."""

from __future__ import annotations

import pytest

from kenning.coding.edit_matcher import (
    DEFAULT_SIMILARITY_THRESHOLD,
    EditResult,
    Strategy,
    apply_edit,
    apply_edit_to_files,
    find_similar_lines,
)


# ---------------------------------------------------------------------------
# Strategy 1: perfect match
# ---------------------------------------------------------------------------


def test_perfect_match_unique():
    original = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    result = apply_edit(
        original,
        "def foo():\n    return 1\n",
        "def foo():\n    return 42\n",
    )
    assert result.success
    assert result.strategy == "perfect"
    assert "return 42" in result.new_text
    assert "return 1" not in result.new_text


def test_perfect_match_ambiguous_falls_through():
    """SEARCH appears twice -> perfect strategy refuses; cascade
    moves on (and fails too in this case)."""
    original = "x = 1\nx = 1\n"
    result = apply_edit(original, "x = 1\n", "x = 2\n")
    assert not result.success


def test_empty_original_returns_failure():
    result = apply_edit("", "search", "replace")
    assert not result.success
    assert "empty" in result.error


def test_empty_search_returns_failure():
    result = apply_edit("original text", "", "replace")
    assert not result.success
    assert "empty" in result.error


# ---------------------------------------------------------------------------
# Strategy 2: skip leading blank line
# ---------------------------------------------------------------------------


def test_skip_leading_blank_line():
    original = "def foo():\n    return 1\n"
    # LLM emits an extra leading blank line in SEARCH.
    search = "\ndef foo():\n    return 1\n"
    replace = "\ndef foo():\n    return 99\n"
    result = apply_edit(original, search, replace)
    assert result.success
    assert result.strategy in {"skip_leading_blank", "perfect"}
    assert "return 99" in result.new_text


# ---------------------------------------------------------------------------
# Strategy 3: whitespace-tolerant
# ---------------------------------------------------------------------------


def test_whitespace_tolerant_extra_indent_in_file():
    """The LLM's SEARCH is at column 0 but the actual file has the
    block nested inside a class (extra 4-space indent)."""
    original = (
        "class C:\n"
        "    def foo(self):\n"
        "        return 1\n"
    )
    search = (
        "def foo(self):\n"
        "    return 1\n"
    )
    replace = (
        "def foo(self):\n"
        "    return 99\n"
    )
    result = apply_edit(original, search, replace)
    assert result.success
    assert "return 99" in result.new_text


# ---------------------------------------------------------------------------
# Strategy 4: dots elision
# ---------------------------------------------------------------------------


def test_dots_elision_basic():
    """SEARCH uses ``...`` to elide unchanged middles."""
    original = (
        "def foo():\n"
        "    x = 1\n"
        "    y = 2\n"
        "    z = 3\n"
        "    return x + y + z\n"
    )
    search = (
        "def foo():\n"
        "    x = 1\n"
        "...\n"
        "    return x + y + z\n"
    )
    replace = (
        "def foo():\n"
        "    x = 42\n"
        "...\n"
        "    return x + y + z\n"
    )
    result = apply_edit(original, search, replace)
    assert result.success
    assert "x = 42" in result.new_text
    # The elided middle is preserved.
    assert "y = 2" in result.new_text
    assert "z = 3" in result.new_text


def test_dots_elision_mismatch_falls_through():
    """Search has dots, replace doesn't -> can't pair chunks."""
    original = "a\nb\nc\nd\n"
    result = apply_edit(
        original,
        "a\n...\nd\n",
        "X\n",
    )
    assert not result.success


# ---------------------------------------------------------------------------
# Strategy 5: relative-indent wrap
# ---------------------------------------------------------------------------


def test_relative_indent_wrap_succeeds_when_perfect_fails():
    """An edge case where the whitespace-tolerant strategy can't find
    a clean offset but the relative-indent transform makes both
    blocks structurally identical."""
    original = "    if x:\n        a = 1\n        b = 2\n"
    search = "if x:\n    a = 1\n    b = 2\n"
    replace = "if x:\n    a = 99\n    b = 2\n"
    result = apply_edit(original, search, replace)
    # Whichever tier matches, the substitution must happen.
    assert result.success
    assert "99" in result.new_text


# ---------------------------------------------------------------------------
# Cascade ordering + strategies arg
# ---------------------------------------------------------------------------


def test_strategy_restricted_list():
    """Limiting to PERFECT only — ambiguous case still falls through."""
    original = "def foo():\n    return 1\n"
    result = apply_edit(
        original,
        "def foo():\n    return 1\n",
        "def foo():\n    return 99\n",
        strategies=[Strategy.PERFECT],
    )
    assert result.success
    assert result.strategy == "perfect"
    assert result.attempts == 1


def test_strategy_disable_perfect_forces_lower_tier():
    """Without PERFECT, the cascade jumps to the next strategy that fits."""
    original = "def foo():\n    return 1\n"
    search = "\ndef foo():\n    return 1\n"
    replace = "\ndef foo():\n    return 99\n"
    result = apply_edit(
        original,
        search,
        replace,
        strategies=[Strategy.SKIP_LEADING_BLANK],
    )
    assert result.success
    assert result.strategy == "skip_leading_blank"


# ---------------------------------------------------------------------------
# Cross-file fallback
# ---------------------------------------------------------------------------


def test_apply_edit_to_files_finds_right_file():
    files = [
        ("a.py", "def alpha(): return 1\n"),
        ("b.py", "def beta(): return 2\n"),
    ]
    matched, result = apply_edit_to_files(
        files,
        "def beta(): return 2\n",
        "def beta(): return 99\n",
    )
    assert matched == "b.py"
    assert result.success
    assert "return 99" in result.new_text


def test_apply_edit_to_files_primary_first():
    """Primary filename is tried first even when listed last."""
    files = [
        ("a.py", "def x(): pass\n"),
        ("b.py", "def x(): pass\n"),
    ]
    # Both files have identical content — primary picks the winner.
    matched, result = apply_edit_to_files(
        files,
        "def x(): pass\n",
        "def x(): return 1\n",
        primary_filename="b.py",
    )
    assert matched == "b.py"


def test_apply_edit_to_files_no_match():
    files = [("a.py", "def x(): pass\n")]
    matched, result = apply_edit_to_files(
        files,
        "def NOT_THERE(): pass\n",
        "def NOT_THERE(): return 1\n",
    )
    assert matched is None
    assert not result.success


def test_apply_edit_to_files_empty_list():
    matched, result = apply_edit_to_files([], "search", "replace")
    assert matched is None
    assert "no files" in result.error


# ---------------------------------------------------------------------------
# find_similar_lines
# ---------------------------------------------------------------------------


def test_find_similar_lines_returns_close_match():
    original = (
        "import os\n"
        "import sys\n"
        "\n"
        "def foo():\n"
        "    return 42\n"
        "\n"
        "def bar():\n"
        "    return 7\n"
    )
    # SEARCH has the wrong return value but otherwise matches.
    search = "def foo():\n    return 99\n"
    similar = find_similar_lines(search, original)
    assert similar
    assert "Closest match" in similar
    assert "def foo()" in similar


def test_find_similar_lines_below_threshold_returns_empty():
    """When nothing in the file is remotely similar, return ''."""
    original = "completely unrelated text\nmore unrelated text\n"
    similar = find_similar_lines(
        "totally different content here",
        original,
        threshold=0.95,
    )
    assert similar == ""


def test_find_similar_lines_empty_inputs():
    assert find_similar_lines("", "original") == ""
    assert find_similar_lines("search", "") == ""


def test_find_similar_lines_marker_on_matched_lines():
    original = "a\nb\nc\nd\n"
    search = "b\nc\n"
    similar = find_similar_lines(search, original, context_lines=1)
    # Lines b and c are the matched window; should have the `>` marker.
    matched_lines = [
        ln for ln in similar.splitlines() if ln.startswith(">")
    ]
    assert len(matched_lines) == 2


def test_default_similarity_threshold_is_sane():
    assert 0.4 <= DEFAULT_SIMILARITY_THRESHOLD <= 0.9


def test_edit_result_is_frozen():
    r = EditResult(new_text="", success=False)
    with pytest.raises(Exception):
        r.new_text = "y"  # type: ignore[misc]
