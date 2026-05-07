"""Tests for the maintenance script's pure helpers.

The LLM-touching paths (run_backfill_metadata, run_extract_facts,
run_cluster_conversations) are exercised via manual end-to-end runs;
they're too slow + non-deterministic to land in pytest. The JSON parser
that ingests their LLM output is the brittlest piece, so we cover it
here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ isn't a package; add it to sys.path so the maintenance module
# imports cleanly.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import maintenance  # noqa: E402


# ---------------------------------------------------------------------------
# _strip_thinking
# ---------------------------------------------------------------------------


def test_strip_thinking_removes_single_block():
    out = maintenance._strip_thinking(
        "<think>Let me reason about this.</think>actual answer"
    )
    assert out == "actual answer"


def test_strip_thinking_removes_multiple_blocks():
    out = maintenance._strip_thinking(
        "<think>step one</think>partial<think>step two</think>final"
    )
    assert out == "partialfinal"


def test_strip_thinking_passes_through_clean_text():
    assert maintenance._strip_thinking("just an answer") == "just an answer"


def test_strip_thinking_handles_multiline_block():
    raw = """<think>
Multiple
lines of
reasoning
</think>The answer."""
    assert maintenance._strip_thinking(raw) == "The answer."


# ---------------------------------------------------------------------------
# _extract_json_payload
# ---------------------------------------------------------------------------


def test_extract_json_payload_plain_list():
    out = maintenance._extract_json_payload('[{"a": 1}, {"a": 2}]')
    assert out == [{"a": 1}, {"a": 2}]


def test_extract_json_payload_with_thinking_prefix():
    raw = '<think>I should return a list of two objects.</think>\n[{"a": 1}, {"a": 2}]'
    assert maintenance._extract_json_payload(raw) == [{"a": 1}, {"a": 2}]


def test_extract_json_payload_inside_markdown_fence():
    raw = 'Here is the answer:\n```json\n[{"a": 1}]\n```\nDone.'
    assert maintenance._extract_json_payload(raw) == [{"a": 1}]


def test_extract_json_payload_inside_unlabeled_fence():
    raw = "```\n{\"x\": true}\n```"
    assert maintenance._extract_json_payload(raw) == {"x": True}


def test_extract_json_payload_balanced_span_inside_prose():
    raw = (
        'The system found these facts: [{"fact": "X", "confidence": 0.9}]. '
        "That's all."
    )
    assert maintenance._extract_json_payload(raw) == [
        {"fact": "X", "confidence": 0.9}
    ]


def test_extract_json_payload_raises_on_garbage():
    with pytest.raises(ValueError):
        maintenance._extract_json_payload("totally not json")


def test_extract_json_payload_handles_thinking_plus_fence():
    raw = (
        "<think>Need a JSON list of one item.</think>\n"
        "Here:\n```json\n[{\"fact\": \"hello\", \"confidence\": 0.5}]\n```"
    )
    assert maintenance._extract_json_payload(raw) == [
        {"fact": "hello", "confidence": 0.5}
    ]
