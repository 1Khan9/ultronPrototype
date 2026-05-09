"""Block-and-revise validator for OpenClaw tool calls.

Per the runtime-verifier-mediation paper, a pre-flight check that asks
the LLM "does this tool call advance the user's stated goal?" can
intercept misdirected calls before they execute, triggering a
block-and-revise loop. Same shape as Ultron's existing coding-side
verification (six checks before the worker is allowed to declare
complete), but for the automation side.

This module is the validator. **Off by default** (per
``openclaw.block_and_revise.enabled``) so the dispatcher path is
byte-for-byte unchanged unless the user opts in. The OpenClawDispatcher
is itself currently stubbed (Phase 5), so the validator wraps the stub
shape — when the dispatcher is wired to a real Gateway in a later
phase the validator's interface stays the same.

Failure mode: **fail open.** If the LLM call errors or the verdict is
unparseable, the validator returns ``allow=True`` so a transient LLM
issue can't paralyse the automation pipeline. Better an occasional
borderline allowance than a hard block on a flaky LLM.

Voice path is unaffected — this validator runs only on automation
dispatch, not on conversational generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from ultron.utils.logging import get_logger

logger = get_logger("openclaw_routing.block_and_revise")


_VALIDATE_PROMPT = """\
The user's stated goal: "{goal}"

Proposed tool call: {tool_call}

Does this tool call directly advance the user's goal?
- ALLOW if the tool call is a reasonable step toward the goal.
- BLOCK if the tool call would be wasted, misdirected, or risky given the goal.

Output exactly one of: ALLOW | BLOCK
On the next line, give a one-sentence reason in the user's voice.

Format:
VERDICT
reason
"""


@dataclass
class ValidationResult:
    """Outcome of a block-and-revise check.

    ``allow`` is the dispatch decision. ``reason`` is human-readable
    audit text + voice narration when blocked. ``verdict`` is the raw
    label the LLM emitted (or ``""`` on parse failure /
    fail-open).
    """

    allow: bool
    reason: str = ""
    verdict: str = ""
    raw_response: str = ""


class ToolCallValidator:
    """Pre-flight LLM gate on OpenClaw tool calls.

    Args:
        llm: an :class:`LLMEngine`-like object with a ``generate`` method.
            None is acceptable; the validator falls open in that case
            (test/standalone scenarios).
    """

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    def validate(
        self, *, goal: str, tool_name: str, tool_args: Optional[dict] = None,
    ) -> ValidationResult:
        if self._llm is None:
            # No LLM wired — fail open.
            return ValidationResult(
                allow=True,
                reason="no validator LLM wired; fail-open",
                verdict="",
            )

        tool_call = _format_tool_call(tool_name, tool_args)
        prompt = _VALIDATE_PROMPT.format(
            goal=goal.replace('"', "'"), tool_call=tool_call,
        )
        try:
            raw = self._llm.generate(prompt) or ""
        except Exception as e:
            logger.warning("ToolCallValidator LLM call failed: %s", e)
            return ValidationResult(
                allow=True,
                reason=f"validator LLM call failed: {e}; fail-open",
                verdict="",
            )

        verdict, reason = _parse_verdict(raw)
        if verdict == "ALLOW":
            return ValidationResult(
                allow=True, reason=reason or "advances the goal",
                verdict="ALLOW", raw_response=raw,
            )
        if verdict == "BLOCK":
            return ValidationResult(
                allow=False,
                reason=reason or "tool call doesn't directly advance the goal",
                verdict="BLOCK",
                raw_response=raw,
            )
        # Unparseable -> fail-open with a note.
        return ValidationResult(
            allow=True,
            reason="validator response unparseable; fail-open",
            verdict="",
            raw_response=raw,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_VERDICT_RE = re.compile(r"\b(ALLOW|BLOCK)\b", re.IGNORECASE)


def _format_tool_call(tool_name: str, tool_args: Optional[dict]) -> str:
    """Render a tool call as a single line for the validator prompt.

    Uses repr() on the args so quotes are escaped consistently. Args
    are truncated at 200 chars per value to keep the prompt small.
    """
    if not tool_args:
        return tool_name
    args_str = ", ".join(
        f"{k}={_truncate_repr(v)}" for k, v in tool_args.items()
    )
    return f"{tool_name}({args_str})"


def _truncate_repr(value: Any, max_chars: int = 200) -> str:
    s = repr(value)
    if len(s) > max_chars:
        return s[:max_chars - 3] + "..."
    return s


def _parse_verdict(text: str) -> "tuple[str, str]":
    """Pull (VERDICT, reason) out of the LLM response."""
    if not text:
        return ("", "")
    text = _THINK_RE.sub("", text).strip()
    m = _VERDICT_RE.search(text)
    if not m:
        return ("", "")
    verdict = m.group(1).upper()
    rest = text[m.end():].strip()
    reason = ""
    if rest:
        # First non-empty line; strip list / quote markers.
        for line in rest.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^[\-*>\"']\s*", "", line).strip()
            if line:
                reason = line
                break
    return (verdict, reason)


def is_enabled(cfg: Any = None) -> bool:
    """Read the live config gate. Centralised so callers don't repeat
    the path-following logic."""
    if cfg is None:
        from ultron.config import get_config
        cfg = get_config()
    return bool(cfg.openclaw.block_and_revise.enabled)


__all__ = [
    "ToolCallValidator",
    "ValidationResult",
    "is_enabled",
]
