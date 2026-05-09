"""4B optimization plan Item 8 — block-and-revise validator tests.

Verifies that the ``ToolCallValidator`` parses LLM verdicts correctly,
fails open on parse / call errors (so flaky LLM never blocks
legitimate work), and returns the expected ``ValidationResult`` shape
for both ALLOW and BLOCK verdicts.

Mocked LLM throughout — no GPU needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ultron.openclaw_routing.block_and_revise import (
    ToolCallValidator,
    ValidationResult,
    is_enabled,
)


# ---------------------------------------------------------------------------
# Allow / block parsing
# ---------------------------------------------------------------------------


def test_validator_allow_verdict() -> None:
    llm = MagicMock()
    llm.generate.return_value = "ALLOW\nthis advances the user's goal of opening the page"
    v = ToolCallValidator(llm)
    result = v.validate(
        goal="open hacker news",
        tool_name="navigate",
        tool_args={"url": "https://news.ycombinator.com"},
    )
    assert isinstance(result, ValidationResult)
    assert result.allow is True
    assert result.verdict == "ALLOW"
    assert "advances" in result.reason


def test_validator_block_verdict() -> None:
    llm = MagicMock()
    llm.generate.return_value = "BLOCK\nthe tool call would delete the wrong file"
    v = ToolCallValidator(llm)
    result = v.validate(
        goal="rename a file in downloads",
        tool_name="delete_file",
        tool_args={"path": "C:/important.txt"},
    )
    assert result.allow is False
    assert result.verdict == "BLOCK"
    assert "delete the wrong file" in result.reason


def test_validator_strips_thinking_block() -> None:
    """Qwen3 emits ``<think>...</think>`` blocks before the answer."""
    llm = MagicMock()
    llm.generate.return_value = (
        "<think>let me consider...</think>\nALLOW\nlooks fine"
    )
    v = ToolCallValidator(llm)
    result = v.validate(goal="g", tool_name="t")
    assert result.allow is True
    assert result.verdict == "ALLOW"


def test_validator_case_insensitive() -> None:
    llm = MagicMock()
    llm.generate.return_value = "block\nbad idea"
    v = ToolCallValidator(llm)
    result = v.validate(goal="g", tool_name="t")
    assert result.verdict == "BLOCK"
    assert result.allow is False


# ---------------------------------------------------------------------------
# Fail-open semantics
# ---------------------------------------------------------------------------


def test_validator_no_llm_wired_fails_open() -> None:
    v = ToolCallValidator(None)
    result = v.validate(goal="g", tool_name="t")
    assert result.allow is True
    assert "fail-open" in result.reason


def test_validator_llm_exception_fails_open() -> None:
    llm = MagicMock()
    llm.generate.side_effect = RuntimeError("model crashed")
    v = ToolCallValidator(llm)
    result = v.validate(goal="g", tool_name="t")
    assert result.allow is True
    assert "validator LLM call failed" in result.reason


def test_validator_unparseable_response_fails_open() -> None:
    llm = MagicMock()
    llm.generate.return_value = "I'm not sure what to do here."
    v = ToolCallValidator(llm)
    result = v.validate(goal="g", tool_name="t")
    assert result.allow is True
    assert "unparseable" in result.reason


def test_validator_empty_response_fails_open() -> None:
    llm = MagicMock()
    llm.generate.return_value = ""
    v = ToolCallValidator(llm)
    result = v.validate(goal="g", tool_name="t")
    assert result.allow is True


# ---------------------------------------------------------------------------
# Tool-call rendering
# ---------------------------------------------------------------------------


def test_validator_includes_tool_name_in_prompt() -> None:
    llm = MagicMock()
    llm.generate.return_value = "ALLOW"
    v = ToolCallValidator(llm)
    v.validate(goal="open the page", tool_name="navigate")
    sent = llm.generate.call_args.args[0]
    assert "Proposed tool call: navigate" in sent
    assert 'goal: "open the page"' in sent


def test_validator_includes_tool_args_in_prompt() -> None:
    llm = MagicMock()
    llm.generate.return_value = "ALLOW"
    v = ToolCallValidator(llm)
    v.validate(
        goal="g", tool_name="navigate",
        tool_args={"url": "https://example.com"},
    )
    sent = llm.generate.call_args.args[0]
    assert "navigate(url='https://example.com')" in sent


def test_validator_truncates_long_args() -> None:
    llm = MagicMock()
    llm.generate.return_value = "ALLOW"
    v = ToolCallValidator(llm)
    long = "x" * 500
    v.validate(goal="g", tool_name="write", tool_args={"content": long})
    sent = llm.generate.call_args.args[0]
    # Truncated to 200 chars + "..."
    assert "..." in sent
    assert "x" * 500 not in sent


def test_validator_escapes_quotes_in_goal() -> None:
    llm = MagicMock()
    llm.generate.return_value = "ALLOW"
    v = ToolCallValidator(llm)
    v.validate(goal='find "specific" docs', tool_name="search")
    sent = llm.generate.call_args.args[0]
    # The double quotes inside the goal must be normalised so the
    # outer template's quoted slot isn't broken.
    assert 'goal: "find \'specific\' docs"' in sent


# ---------------------------------------------------------------------------
# Config gate
# ---------------------------------------------------------------------------


def test_is_enabled_default_off() -> None:
    cfg = MagicMock()
    cfg.openclaw.block_and_revise.enabled = False
    assert is_enabled(cfg) is False


def test_is_enabled_when_on() -> None:
    cfg = MagicMock()
    cfg.openclaw.block_and_revise.enabled = True
    assert is_enabled(cfg) is True
