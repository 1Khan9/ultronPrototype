""".kenningignore enforcement rule (Category U).

Wires the :mod:`kenning.safety.ignore` controller (cline ``ClineIgnoreController``
port) into the tool-call validator. A tool call that reads OR writes a path
matched by a ``.kenningignore`` layer (global ``~/.kenning/.kenningignore``,
project, or workspace) is blocked -- the canonical use is keeping secrets
(``.env``, ``secrets/``, key material) out of reach of automated file ops AND
of file-reading shell commands (``cat``/``Get-Content``/``grep`` ...).

Default-SAFE: when no ``.kenningignore`` exists the controller matches nothing,
so the rule is a no-op and behaviour is unchanged. Fail-open: a controller
error never blocks a call (the rule returns ALLOW + logs at debug). Operators
disable it via ``config.yaml:safety.rules.U1: false``.
"""

from __future__ import annotations

from kenning.safety.rules.base import Rule
from kenning.utils.logging import get_logger

logger = get_logger("safety.rules.ignore")

#: Argument keys the rule treats as a shell command to validate.
_COMMAND_ARG_KEYS = ("command", "cmd", "shell_command")


class KenningIgnoreRule(Rule):
    """Block tool calls touching ``.kenningignore``'d paths (read or write)."""

    rule_id = "U1"
    description = ".kenningignore path/command block"
    category = "U"

    def evaluate(self, ctx, *, policy, resolver):  # noqa: ARG002
        from kenning.safety.validator import RuleResult, Verdict

        try:
            from kenning.safety.ignore import get_ignore_controller
            # Pass the active project root so the project + workspace
            # .kenningignore layers actually resolve. Without it the controller
            # keys on "__global__" and ONLY ~/.kenning/.kenningignore is ever
            # consulted -- the project/workspace layers are silently skipped.
            workspace_root = (
                getattr(resolver, "project_root", None)
                if resolver is not None else None
            )
            controller = get_ignore_controller(workspace_root=workspace_root)
        except Exception as e:  # noqa: BLE001
            logger.debug("ignore controller unavailable (%s); allowing", e)
            return RuleResult(
                rule_id=self.rule_id, verdict=Verdict.ALLOW,
                reason="ignore controller unavailable",
            )

        # 1) Any candidate path matched by an ignore layer -> block (read OR
        #    write; ignored paths are secrets, so both directions are denied).
        for raw in ctx.paths:
            try:
                verdict = controller.check_path(str(raw))
            except Exception as e:  # noqa: BLE001
                logger.debug("check_path(%s) raised (%s); skipping", raw, e)
                continue
            if getattr(verdict, "ignored", False):
                return RuleResult(
                    rule_id=self.rule_id,
                    verdict=Verdict.BLOCK_HARD,
                    reason=(
                        f".kenningignore blocks access to {raw} "
                        f"(layer={getattr(verdict, 'matched_layer', '?')})"
                    ),
                    context={
                        "path": str(raw),
                        "matched_layer": getattr(verdict, "matched_layer", ""),
                        "matched_pattern": getattr(verdict, "matched_pattern", ""),
                    },
                )

        # 2) File-reading shell commands whose path argument is ignored.
        for key in _COMMAND_ARG_KEYS:
            cmd = ctx.arguments.get(key)
            if not isinstance(cmd, str) or not cmd.strip():
                continue
            try:
                cv = controller.validate_command(cmd)
            except Exception as e:  # noqa: BLE001
                logger.debug("validate_command raised (%s); skipping", e)
                continue
            denied = getattr(cv, "denied_path", None)
            if denied:
                return RuleResult(
                    rule_id=self.rule_id,
                    verdict=Verdict.BLOCK_HARD,
                    reason=f".kenningignore blocks command reading {denied}",
                    context={"command": cmd[:200], "denied_path": str(denied)},
                )

        return RuleResult(
            rule_id=self.rule_id, verdict=Verdict.ALLOW,
            reason="no .kenningignore match",
        )


def build_ignore_rules() -> list:
    """Return the Category U rule list (the .kenningignore enforcement rule)."""
    return [KenningIgnoreRule()]


__all__ = ["KenningIgnoreRule", "build_ignore_rules"]
