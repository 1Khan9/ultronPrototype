"""Tests for :mod:`ultron.utils.relative_indent`."""

from __future__ import annotations

import pytest

from ultron.utils.relative_indent import (
    RelativeIndenter,
    absolute_indent,
    relative_indent,
)


def test_marker_chosen_when_not_in_input():
    ind = RelativeIndenter(["plain ascii text"])
    assert ind.marker == "←"


def test_marker_collision_picks_high_codepoint():
    # Input contains the default marker; constructor should pick a
    # different codepoint.
    ind = RelativeIndenter(["a ← b"])
    assert ind.marker != "←"
    assert ord(ind.marker) >= 0x10000


def test_explicit_marker_override():
    ind = RelativeIndenter(["abc"], marker="◊")
    assert ind.marker == "◊"


def test_explicit_marker_collision_raises():
    with pytest.raises(ValueError):
        RelativeIndenter(["a◊b"], marker="◊")


def test_explicit_marker_must_be_single_char():
    with pytest.raises(ValueError):
        RelativeIndenter(["abc"], marker="ab")


def test_roundtrip_simple():
    src = "def foo():\n    pass\n"
    ind = RelativeIndenter([src])
    encoded = ind.make_relative(src)
    decoded = ind.make_absolute(encoded)
    assert decoded == src


def test_roundtrip_with_outdent():
    src = "if x:\n    a\n    b\n        c\n    d\nelse:\n    e\n"
    ind = RelativeIndenter([src])
    encoded = ind.make_relative(src)
    decoded = ind.make_absolute(encoded)
    assert decoded == src


def test_roundtrip_with_blank_lines():
    src = "def foo():\n    a\n\n    b\n"
    ind = RelativeIndenter([src])
    encoded = ind.make_relative(src)
    decoded = ind.make_absolute(encoded)
    assert decoded == src


def test_roundtrip_empty_string():
    src = ""
    ind = RelativeIndenter([src])
    encoded = ind.make_relative(src)
    assert encoded == ""
    assert ind.make_absolute(encoded) == ""


def test_two_blocks_identical_after_normalization():
    """The headline use case: two blocks that differ ONLY in absolute
    indent produce identical relative-indent output from the second
    line onward."""
    block_at_root = (
        "def helper():\n"
        "    a = 1\n"
        "    b = 2\n"
    )
    block_in_class = (
        "    def helper():\n"
        "        a = 1\n"
        "        b = 2\n"
    )
    ind = RelativeIndenter([block_at_root, block_in_class])
    rel_root = ind.make_relative(block_at_root)
    rel_class = ind.make_relative(block_in_class)
    # After the first line's leading indent, both encodings should be
    # identical (the relative deltas line up).
    rel_root_tail = rel_root.split("\n", 2)[1:]
    rel_class_tail = rel_class.split("\n", 2)[1:]
    assert rel_root_tail == rel_class_tail


def test_make_relative_rejects_text_with_marker():
    src = "hello"
    ind = RelativeIndenter([src])
    contaminated = src + ind.marker + "world"
    with pytest.raises(ValueError):
        ind.make_relative(contaminated)


def test_make_absolute_rejects_odd_line_count():
    src = "def foo():\n    pass\n"
    ind = RelativeIndenter([src])
    encoded = ind.make_relative(src)
    # Strip a line to make it odd.
    bad = encoded + "extra\n"
    with pytest.raises(ValueError):
        ind.make_absolute(bad)


def test_one_shot_convenience():
    src = "def foo():\n    pass\n"
    encoded = relative_indent(src)
    decoded = absolute_indent(encoded)
    assert decoded == src


def test_decoder_rejects_corrupt_outdent_indicator():
    # Manually construct a malformed stream that mixes marker with letters.
    bad = "←x\nhello\n"
    ind = RelativeIndenter([], marker="←")
    with pytest.raises(ValueError):
        ind.make_absolute(bad)


def test_decoder_rejects_outdent_below_zero():
    # Construct a relative-indent stream that tries to outdent past column 0.
    bad = "←←\nhello\n"  # 2-char outdent but we're already at column 0
    ind = RelativeIndenter([], marker="←")
    with pytest.raises(ValueError):
        ind.make_absolute(bad)
