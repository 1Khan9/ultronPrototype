"""Category IT (Interactive Tools) -- block hang-prone interactive commands.

Direct port of SWE-Agent's ``sweagent/tools/tools.py:ToolFilterConfig``
blocklist pattern (MIT, Yang et al. 2024). The pattern: the supervisor
+ orchestrator are one bad shell subprocess away from hanging. ``vim``,
``less``, ``tail -f``, bare ``python``, ``make`` etc. either drop into
an interactive prompt (waiting for input the LLM can't provide) or
follow output indefinitely. Catching these BEFORE spawn makes the
common failure mode impossible.

Three rule types in this category:

* :class:`IT1InteractivePrefixRule` -- block commands STARTING WITH a
  prefix (``vim ...``, ``python -m venv ...``, ``tail -f ...``, etc).
* :class:`IT2InteractiveStandaloneRule` -- block commands that are EXACT
  matches with no arguments (bare ``python``, bare ``bash``, etc).
  Distinguishes ``python script.py`` (allowed) from ``python`` alone
  (blocked).
* :class:`IT3InteractiveUnlessRegexRule` -- block command name UNLESS
  the full command matches an allow-regex (e.g. ``radare2`` is blocked
  unless invoked with ``-c``).

The blocklists are loaded from ``Policy.interactive_tools`` (with
sensible SWE-Agent-mirrored defaults). Operators can override per-rule
via ``config.yaml:safety.rules.IT1: false`` to disable a specific
rule, or extend the lists via ``config.yaml:safety.interactive_tools.*``.
"""

from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from kenning.safety.rules.base import Rule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default blocklists (verbatim from SWE-Agent)
# ---------------------------------------------------------------------------

#: Commands blocked when they appear as a PREFIX of the shell line.
#: Verbatim from `ToolFilterConfig.blocklist`.
DEFAULT_PREFIX_BLOCKLIST: tuple[str, ...] = (
    "vim",
    "vi",
    "emacs",
    "nano",
    "nohup",
    "gdb",
    "less",
    "tail -f",
    "python -m venv",
    "make",
)

#: Commands blocked when they're the ENTIRE command (no arguments).
#: Verbatim from `ToolFilterConfig.blocklist_standalone`.
DEFAULT_STANDALONE_BLOCKLIST: tuple[str, ...] = (
    "python",
    "python3",
    "ipython",
    "bash",
    "sh",
    "/bin/bash",
    "/bin/sh",
    "nohup",
    "vi",
    "vim",
    "emacs",
    "nano",
    "su",
)

#: Commands whose NAME triggers a check but the full command is allowed
#: when it matches the regex. Verbatim from `ToolFilterConfig.block_unless_regex`.
DEFAULT_UNLESS_REGEX: dict[str, str] = {
    "radare2": r"\b(?:radare2)\b.*\s+-c\s+.*",
    "r2": r"\b(?:r2)\b.*\s+-c\s+.*",
}


# ---------------------------------------------------------------------------
# Default error message
# ---------------------------------------------------------------------------

#: Mirrors SWE-Agent's `blocklist_error_template`.
DEFAULT_BLOCK_MESSAGE: str = (
    "Operation '{action}' is not supported by this environment."
)


# ---------------------------------------------------------------------------
# Configuration container
# ---------------------------------------------------------------------------


@dataclass
class InteractiveToolsConfig:
    """Per-rule configuration for the IT category."""

    enabled: bool = True
    prefix_blocklist: list[str] = field(
        default_factory=lambda: list(DEFAULT_PREFIX_BLOCKLIST)
    )
    standalone_blocklist: list[str] = field(
        default_factory=lambda: list(DEFAULT_STANDALONE_BLOCKLIST)
    )
    unless_regex: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_UNLESS_REGEX)
    )
    block_message: str = DEFAULT_BLOCK_MESSAGE


# ---------------------------------------------------------------------------
# Command extraction
# ---------------------------------------------------------------------------


_SHELL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "bash",
        "sh",
        "shell",
        "cmd",
        "exec",
        "run",
        "shell_exec",
        "bash_exec",
        "run_command",
        "execute",
    }
)

_COMMAND_ARG_KEYS: tuple[str, ...] = (
    "command",
    "cmd",
    "shell",
    "shell_command",
    "script",
    "args",
    "argv",
    "argument",
)


def extract_command(ctx) -> Optional[str]:
    """Return the shell command in ``ctx``, or ``None`` if the call
    isn't a shell invocation.

    Heuristics:

    1. If ``ctx.tool_name`` matches a shell-style name AND
       ``ctx.arguments`` carries a known command key, return that
       value.
    2. If ``ctx.tool_name`` itself looks like a shell command
       (contains a space, or matches a known interpreter), return
       the tool name.
    3. Otherwise return ``None`` -- the rule no-ops on non-shell tool
       calls.
    """
    tool_name = getattr(ctx, "tool_name", "")
    args = getattr(ctx, "arguments", {}) or {}
    lower = tool_name.lower().strip()
    if lower in _SHELL_TOOL_NAMES:
        for key in _COMMAND_ARG_KEYS:
            if key in args:
                value = args[key]
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, (list, tuple)):
                    return " ".join(str(v) for v in value).strip()
        return None
    # Tool name looks like a command (e.g. "vim", "bash -c ...")?
    stripped = tool_name.strip()
    if not stripped:
        return None
    if " " in stripped or any(
        stripped == name or stripped.startswith(name + " ")
        for name in (
            "vim",
            "vi",
            "emacs",
            "nano",
            "python",
            "python3",
            "bash",
            "sh",
            "ipython",
            "less",
            "tail",
            "make",
            "gdb",
            "su",
            "radare2",
            "r2",
        )
    ):
        return stripped
    return None


def _first_token(command: str) -> str:
    """Return the first token of ``command`` (without arguments)."""
    if not command:
        return ""
    try:
        toks = shlex.split(command, posix=True)
    except ValueError:
        # Unparseable shell; fall back to whitespace split.
        toks = command.split()
    return toks[0] if toks else ""


def _matches_prefix(command: str, prefix: str) -> bool:
    """True if ``command`` starts with ``prefix`` followed by EOL,
    whitespace, or a shell separator.

    Avoids matching ``vim_extension`` against ``vim``: the prefix
    only counts if the next char is whitespace, a redirect, a pipe,
    or end-of-string.
    """
    if not command.startswith(prefix):
        return False
    if len(command) == len(prefix):
        return True
    nxt = command[len(prefix)]
    return nxt in " \t|&;<>"


# ---------------------------------------------------------------------------
# Rule classes
# ---------------------------------------------------------------------------


def _block_result(rule_id: str, description: str, message: str, command: str):
    from kenning.safety.validator import RuleResult, Verdict

    rendered = message.format(action=command)
    return RuleResult(
        rule_id=rule_id,
        verdict=Verdict.BLOCK_HARD,
        reason=f"{description}: {rendered}",
        context={"command": command, "blocked_message": rendered},
    )


def _allow_result(rule_id: str, reason: str):
    from kenning.safety.validator import RuleResult, Verdict

    return RuleResult(rule_id=rule_id, verdict=Verdict.ALLOW, reason=reason)


class IT1InteractivePrefixRule(Rule):
    """Block commands whose first token + prefix match a blocked entry.

    Example: ``vim foo.py`` matches ``vim``; ``tail -f log.txt`` matches
    ``tail -f``; ``python -m venv .venv`` matches ``python -m venv``.
    """

    rule_id = "IT1"
    description = "block hang-prone interactive command prefixes"
    category = "IT"

    def __init__(self, *, prefixes: Sequence[str], message: str) -> None:
        self._prefixes = tuple(p.strip() for p in prefixes if p and p.strip())
        # Sort longest-first so ``python -m venv`` wins over ``python``
        # in the standalone matcher's prefix tier (defensive even though
        # standalone is a separate rule).
        self._prefixes = tuple(sorted(self._prefixes, key=len, reverse=True))
        self._message = message

    def evaluate(self, ctx, *, policy, resolver):  # noqa: ARG002
        if not self._prefixes:
            return _allow_result(self.rule_id, "no prefixes configured")
        command = extract_command(ctx)
        if command is None:
            return _allow_result(self.rule_id, "not a shell command")
        for prefix in self._prefixes:
            if _matches_prefix(command, prefix):
                return _block_result(
                    self.rule_id, self.description, self._message, command
                )
        return _allow_result(self.rule_id, "no prefix match")


class IT2InteractiveStandaloneRule(Rule):
    """Block commands that are EXACT matches with no arguments.

    Example: bare ``python`` (drops into REPL) is blocked; ``python
    script.py`` is allowed. The SWE-Agent distinction is critical --
    we want the LLM to run scripts but not drop into interactive
    sessions.
    """

    rule_id = "IT2"
    description = "block bare interactive interpreters"
    category = "IT"

    def __init__(self, *, names: Sequence[str], message: str) -> None:
        self._names = frozenset(n.strip() for n in names if n and n.strip())
        self._message = message

    def evaluate(self, ctx, *, policy, resolver):  # noqa: ARG002
        if not self._names:
            return _allow_result(self.rule_id, "no standalone names configured")
        command = extract_command(ctx)
        if command is None:
            return _allow_result(self.rule_id, "not a shell command")
        if command in self._names:
            return _block_result(
                self.rule_id, self.description, self._message, command
            )
        return _allow_result(self.rule_id, "command has args or is unknown")


class IT3InteractiveUnlessRegexRule(Rule):
    """Block commands whose name is listed UNLESS the full command
    matches the allow regex.

    Example: ``radare2`` is blocked unless invoked with ``-c
    "command"`` (non-interactive script mode). ``radare2 binary.elf``
    drops to interactive shell -> BLOCK; ``radare2 -c "afl" binary.elf``
    -> allowed.
    """

    rule_id = "IT3"
    description = "block interactive tools unless invoked non-interactively"
    category = "IT"

    def __init__(
        self,
        *,
        name_to_regex: dict[str, str],
        message: str,
    ) -> None:
        self._compiled: dict[str, re.Pattern[str]] = {}
        for name, pattern in name_to_regex.items():
            name = name.strip()
            if not name or not pattern:
                continue
            try:
                self._compiled[name] = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                logger.warning(
                    "IT3 regex for %r failed to compile: %s; rule skipped",
                    name,
                    exc,
                )
        self._message = message

    def evaluate(self, ctx, *, policy, resolver):  # noqa: ARG002
        if not self._compiled:
            return _allow_result(self.rule_id, "no regex rules configured")
        command = extract_command(ctx)
        if command is None:
            return _allow_result(self.rule_id, "not a shell command")
        first = _first_token(command)
        if not first:
            return _allow_result(self.rule_id, "empty command")
        regex = self._compiled.get(first)
        if regex is None:
            return _allow_result(self.rule_id, "command not in regex set")
        if regex.search(command):
            return _allow_result(
                self.rule_id, f"allowed by regex {regex.pattern!r}"
            )
        return _block_result(
            self.rule_id, self.description, self._message, command
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_category_it_rules(
    config: Optional[InteractiveToolsConfig] = None,
) -> list[Rule]:
    """Build the IT category rule list from ``config`` (or defaults).

    Returns three rule instances in order: IT1 prefix, IT2 standalone,
    IT3 conditional. Callers integrate them into the validator's rule
    list via :func:`build_validator_from_config`.
    """
    cfg = config or InteractiveToolsConfig()
    if not cfg.enabled:
        return []
    return [
        IT1InteractivePrefixRule(
            prefixes=cfg.prefix_blocklist,
            message=cfg.block_message,
        ),
        IT2InteractiveStandaloneRule(
            names=cfg.standalone_blocklist,
            message=cfg.block_message,
        ),
        IT3InteractiveUnlessRegexRule(
            name_to_regex=cfg.unless_regex,
            message=cfg.block_message,
        ),
    ]


__all__ = [
    "DEFAULT_BLOCK_MESSAGE",
    "DEFAULT_PREFIX_BLOCKLIST",
    "DEFAULT_STANDALONE_BLOCKLIST",
    "DEFAULT_UNLESS_REGEX",
    "IT1InteractivePrefixRule",
    "IT2InteractiveStandaloneRule",
    "IT3InteractiveUnlessRegexRule",
    "InteractiveToolsConfig",
    "build_category_it_rules",
    "extract_command",
]
