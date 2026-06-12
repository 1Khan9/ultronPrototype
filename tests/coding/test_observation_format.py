"""Tests for observation-stream formatters (catalog T10 + T19)."""

from __future__ import annotations

import pytest

from kenning.coding.observation_format import (
    COMPACT_MAX_OBSERVATION_CHARS,
    DEFAULT_MAX_OBSERVATION_CHARS,
    EMPTY_OUTPUT_MESSAGE,
    SUPPRESSED_OUTPUT_MESSAGE,
    format_observation,
    truncate_observation,
    wrap_empty_observation,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_default_cap_is_ten_thousand_chars():
    assert DEFAULT_MAX_OBSERVATION_CHARS == 10_000


def test_compact_cap_is_smaller_than_default():
    assert COMPACT_MAX_OBSERVATION_CHARS < DEFAULT_MAX_OBSERVATION_CHARS


def test_empty_message_is_full_sentence():
    assert EMPTY_OUTPUT_MESSAGE.endswith(".")
    assert "successfully" in EMPTY_OUTPUT_MESSAGE
    assert "did not produce" in EMPTY_OUTPUT_MESSAGE


def test_suppressed_message_distinguishes_from_empty():
    assert SUPPRESSED_OUTPUT_MESSAGE != EMPTY_OUTPUT_MESSAGE
    assert SUPPRESSED_OUTPUT_MESSAGE.endswith(".")


# ---------------------------------------------------------------------------
# truncate_observation
# ---------------------------------------------------------------------------


def test_truncate_short_input_returns_unchanged():
    text = "short output"
    r = truncate_observation(text)
    assert r.truncated is False
    assert r.text == text
    assert r.original_chars == len(text)
    assert r.kept_chars == len(text)
    assert r.elided_chars == 0


def test_truncate_exactly_at_cap_returns_unchanged():
    text = "x" * 100
    r = truncate_observation(text, max_chars=100)
    assert r.truncated is False
    assert r.text == text


def test_truncate_over_cap_keeps_head_and_tail():
    head_chars = "H" * 200
    middle_chars = "M" * 800
    tail_chars = "T" * 200
    text = head_chars + middle_chars + tail_chars  # 1200 chars
    r = truncate_observation(text, max_chars=400)
    assert r.truncated is True
    assert r.original_chars == 1200
    # max_chars=400 -> 200 head + 200 tail
    assert "H" * 200 in r.text
    assert "T" * 200 in r.text
    assert "M" not in r.text  # the middle is fully elided
    assert "characters elided" in r.text
    assert "800 characters elided" in r.text


def test_truncate_includes_head_and_tail_blocks():
    text = "A" * 1000 + "MIDDLE" + "B" * 1000
    r = truncate_observation(text, max_chars=100)
    assert "<observation_head>" in r.text
    assert "<observation_tail>" in r.text
    assert "<elided_chars>" in r.text
    assert "<warning>" in r.text


def test_truncate_reports_correct_elided_count():
    text = "Q" * 5000
    r = truncate_observation(text, max_chars=500)
    expected_elided = 5000 - 500
    assert r.elided_chars == expected_elided
    assert f"{expected_elided} characters elided" in r.text


def test_truncate_includes_max_chars_in_warning():
    text = "y" * 200
    r = truncate_observation(text, max_chars=100)
    assert "100-character cap" in r.text


def test_truncate_handles_none_as_empty():
    r = truncate_observation(None)  # type: ignore[arg-type]
    assert r.truncated is False
    assert r.text == ""
    assert r.original_chars == 0


def test_truncate_rejects_too_small_cap():
    with pytest.raises(ValueError):
        truncate_observation("x" * 1000, max_chars=5)


def test_truncate_with_custom_template():
    template = "HEAD={head} TAIL={tail} ELIDED={elided} TOTAL={total_chars} MAX={max_chars}"
    text = "x" * 100 + "y" * 100
    r = truncate_observation(text, max_chars=20, template=template)
    assert r.truncated is True
    assert "HEAD=" in r.text
    assert "TAIL=" in r.text
    # Halves of cap=20 -> 10 head + 10 tail
    assert "ELIDED=180" in r.text
    assert "TOTAL=200" in r.text
    assert "MAX=20" in r.text


def test_truncate_kept_chars_equals_head_plus_tail_size():
    text = "x" * 1000
    r = truncate_observation(text, max_chars=200)
    assert r.kept_chars == 200  # 100 head + 100 tail


def test_truncate_preserves_unicode_characters_at_boundary():
    # Non-ASCII chars in the head/tail should pass through cleanly.
    head = "α" * 50
    body = "β" * 200
    tail = "γ" * 50
    text = head + body + tail
    r = truncate_observation(text, max_chars=100)
    assert r.truncated is True
    # Slices on str are by code point so the head/tail keep cleanly.
    assert "α" in r.text
    assert "γ" in r.text


def test_truncate_pytest_failure_summary_survives():
    # Realistic shape: huge per-test output up front, terse summary at end.
    bulk = "test_x.py::test_passed\n" * 1000
    summary = "===== 3 failed, 1500 passed in 12.34s ====="
    text = bulk + summary
    r = truncate_observation(text, max_chars=2_000)
    assert r.truncated is True
    # The pass/fail summary lives in the tail -- it MUST survive.
    assert "3 failed" in r.text
    assert "1500 passed" in r.text


# ---------------------------------------------------------------------------
# wrap_empty_observation
# ---------------------------------------------------------------------------


def test_wrap_empty_observation_none_returns_message():
    assert wrap_empty_observation(None) == EMPTY_OUTPUT_MESSAGE


def test_wrap_empty_observation_empty_string_returns_message():
    assert wrap_empty_observation("") == EMPTY_OUTPUT_MESSAGE


def test_wrap_empty_observation_whitespace_only_returns_message():
    assert wrap_empty_observation("   \n\t  ") == EMPTY_OUTPUT_MESSAGE


def test_wrap_empty_observation_non_empty_passthrough():
    text = "actual output"
    assert wrap_empty_observation(text) == text


def test_wrap_empty_observation_suppressed_returns_suppressed_message():
    assert wrap_empty_observation("", suppressed=True) == SUPPRESSED_OUTPUT_MESSAGE


def test_wrap_empty_observation_suppressed_with_text_returns_text():
    text = "actual output"
    assert wrap_empty_observation(text, suppressed=True) == text


def test_wrap_empty_observation_custom_messages():
    assert wrap_empty_observation("", empty_message="EMPTY!") == "EMPTY!"
    assert (
        wrap_empty_observation("", suppressed=True, suppressed_message="HIDDEN!")
        == "HIDDEN!"
    )


# ---------------------------------------------------------------------------
# format_observation (end-to-end)
# ---------------------------------------------------------------------------


def test_format_observation_empty_returns_message():
    assert format_observation("") == EMPTY_OUTPUT_MESSAGE
    assert format_observation(None) == EMPTY_OUTPUT_MESSAGE


def test_format_observation_short_returns_unchanged():
    text = "the output"
    assert format_observation(text) == text


def test_format_observation_long_triggers_truncation():
    text = "x" * (DEFAULT_MAX_OBSERVATION_CHARS + 100)
    out = format_observation(text)
    assert "<observation_head>" in out
    assert "<elided_chars>" in out


def test_format_observation_suppressed_yields_suppressed_message():
    assert format_observation("", suppressed=True) == SUPPRESSED_OUTPUT_MESSAGE


def test_format_observation_custom_cap_respected():
    text = "y" * 500
    out = format_observation(text, max_chars=100)
    assert "<observation_head>" in out
    assert "<observation_tail>" in out
