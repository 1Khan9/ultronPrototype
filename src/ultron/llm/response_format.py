"""Structured response templates for LLM-facing and user-facing messages.

This module centralises every "agent emits a structured notice to the LLM
or user" template so the LLM learns ONE error/notice shape and can
self-correct reliably. Adapted from cline's ``responses.ts`` pattern
(Apache 2.0; see ``THIRD_PARTY_NOTICES.md``).

Design philosophy:

* Consistent tagging — every notice uses the same XML-ish wrapper
  conventions (``<error>``, ``<feedback>``, ``<note>``, ``<final_file_content>``)
  so the LLM can parse intent without ambiguity.
* Progressive escalation — repeated-failure templates ramp up severity
  (tier 1 = suggestion, tier 2 = directive, tier 3 = forbid-and-pivot).
* Voice-friendly variants — every template that may be spoken via TTS
  exposes a ``*_voice`` companion that is terse, in-character, and TTS-safe.
* Single emit surface — subsystems import from this module rather than
  string-concatenating their own error prose; refactors only happen in
  one place.

Every template is a pure function returning ``str``. There is no module
state. Voice variants are explicitly suffixed; the default form is the
LLM-facing form. Templates that need data substitute via f-strings; all
caller-supplied content is wrapped (escaping is the caller's responsibility
when the content might contain XML-ish markers).
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Threshold (percent) above which the context-window warning is appended
#: to write-style retries. Mirrors cline's 50 % gate.
CONTEXT_WINDOW_WARNING_THRESHOLD_PERCENT: int = 50

#: Visual marker for ignored-by-policy entries in file lists. The lock
#: glyph is preserved in audit logs but stripped to ``[LOCKED]`` text in
#: TTS-bound output per the no-emoji-in-spoken-output rule.
LOCK_TEXT_SYMBOL: str = "\U0001F512"
LOCK_TEXT_SYMBOL_TTS: str = "[LOCKED]"

#: Default escalation thresholds for repeated-failure templates.
WRITE_RETRY_TIER_2: int = 2
WRITE_RETRY_TIER_3: int = 3

#: Default reusable boilerplate hint appended to several errors so the
#: LLM is reminded how Ultron's tool-call protocol expects parameters.
TOOL_USE_REMINDER: str = (
    "Reminder: ultron expects each tool call to carry every required "
    "parameter named in its schema. Re-issue the call with the missing "
    "field included."
)


# ---------------------------------------------------------------------------
# Generic tool errors
# ---------------------------------------------------------------------------

def tool_denied() -> str:
    """User denied this tool call via the auto-approve gate.

    Returns:
        Short LLM-facing message describing the denial without prescribing
        an alternative (the LLM picks the next move).
    """
    return (
        "The user denied this tool call. Do not retry the same call; "
        "explain or ask what they want instead."
    )


def tool_denied_voice() -> str:
    """Voice-friendly variant of :func:`tool_denied`."""
    return "Permission denied for that one."


def tool_error(detail: Optional[str] = None) -> str:
    """Generic tool-call failure with structured ``<error>`` wrapper.

    Args:
        detail: optional error string; truncated to ~600 chars for prompt
            economy.

    Returns:
        LLM-facing message wrapping the detail in an ``<error>`` block so
        the LLM can parse + reason about recovery.
    """
    body = (detail or "no detail provided").strip()
    if len(body) > 600:
        body = body[:600] + "... (truncated)"
    return (
        "Tool execution failed. Recovery depends on the cause; consider an "
        "alternative tool or ask the user.\n"
        f"<error>{body}</error>"
    )


def tool_error_voice(detail: Optional[str] = None) -> str:
    """Voice-friendly variant of :func:`tool_error` — single short sentence."""
    if detail:
        head = detail.strip().split("\n", 1)[0]
        if len(head) > 80:
            head = head[:80] + "..."
        return f"That failed: {head}"
    return "That tool call failed."


def tool_already_used(tool_name: str) -> str:
    """Enforce the one-tool-per-message rule.

    Args:
        tool_name: name of the tool that was called a second time.

    Returns:
        LLM-facing message instructing the LLM to assess the prior result
        before issuing another tool call.
    """
    return (
        f"You already issued '{tool_name}' this turn. Assess its result "
        "before invoking another tool. Continue with reasoning or end the "
        "turn cleanly."
    )


def no_tools_used(using_native_tool_calls: bool = False) -> str:
    """LLM produced no tool call when one was expected.

    Args:
        using_native_tool_calls: True when the API supports native tool
            calling (e.g. function-calling); False for XML-tagged tool use.

    Returns:
        LLM-facing message offering three explicit next-step paths.
    """
    reminder = "" if using_native_tool_calls else f"\n\n{TOOL_USE_REMINDER}"
    return (
        "ERROR: no tool was used in your last response.\n"
        "Next steps:\n"
        "  1) Issue the tool call needed to advance the task.\n"
        "  2) If the task is complete, signal completion explicitly.\n"
        "  3) If you need direction, ask a single clarifying question."
        f"{reminder}"
    )


def too_many_mistakes(feedback: Optional[str] = None) -> str:
    """Repeated-error escalation with user feedback wrapper.

    Args:
        feedback: optional user-supplied feedback to inject.

    Returns:
        LLM-facing message wrapping feedback in ``<feedback>`` tags.
    """
    if feedback:
        return (
            "You are looping or repeating mistakes. Stop and incorporate "
            "the user's feedback before any further action.\n"
            f"<feedback>{feedback.strip()}</feedback>"
        )
    return (
        "You are looping or repeating mistakes. Stop and ask the user how "
        "they want you to proceed."
    )


def too_many_mistakes_voice() -> str:
    """Voice-friendly variant of :func:`too_many_mistakes`."""
    return "I keep tripping on this. Let me know how you want to proceed."


def missing_tool_parameter_error(param_name: str) -> str:
    """Required tool-call parameter is missing.

    Args:
        param_name: name of the missing parameter.

    Returns:
        LLM-facing message naming the parameter and reissuing the format
        reminder.
    """
    return (
        f"Missing required parameter '{param_name}'. Re-issue the tool "
        f"call with that field populated.\n\n{TOOL_USE_REMINDER}"
    )


def repeated_tool_call(tool_name: str, count: int) -> str:
    """Loop-detection escalation for identical repeated tool calls.

    Args:
        tool_name: name of the tool being repeated.
        count: number of consecutive identical invocations.

    Returns:
        LLM-facing message instructing the LLM to vary arguments or pivot.
    """
    return (
        f"You issued '{tool_name}' {count} times in a row with identical "
        "arguments and made no progress. Try a different tool, vary the "
        "arguments materially, or end the turn and ask the user."
    )


def invalid_mcp_tool_argument_error(server_name: str, tool_name: str) -> str:
    """MCP tool argument failed JSON-shape validation.

    Args:
        server_name: MCP server short key.
        tool_name: MCP tool name.

    Returns:
        LLM-facing message asking for a retry with valid JSON.
    """
    return (
        f"Invalid JSON arguments for MCP tool '{tool_name}' on server "
        f"'{server_name}'. Re-issue with a valid JSON object matching the "
        "tool's input schema."
    )


def permission_denied_error(reason: str) -> str:
    """Safety / policy gate blocked the command.

    Args:
        reason: structured reason string from the safety validator.

    Returns:
        LLM-facing message naming the reason and suggesting alternatives.
    """
    return (
        "The user's safety policy blocked that command.\n"
        f"<reason>{reason.strip()}</reason>\n"
        "Either choose an alternative approach or ask the user to override."
    )


# ---------------------------------------------------------------------------
# Path / ignore violations
# ---------------------------------------------------------------------------

def ignore_path_error(path: str) -> str:
    """The path is blocked by ``.ultronignore`` policy.

    Args:
        path: workspace-relative or absolute path that was blocked.

    Returns:
        LLM-facing message describing the block and suggesting an
        alternative or user confirmation.
    """
    return (
        "Access denied: that path is blocked by the user's .ultronignore "
        "rules.\n"
        f"<path>{path}</path>\n"
        "Pick a different file or ask the user to update their ignore list."
    )


def ignore_path_error_voice(path: str) -> str:
    """Voice-friendly variant of :func:`ignore_path_error`."""
    short = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return f"{short} is on your ignore list; pick a different file."


# ---------------------------------------------------------------------------
# Write / edit cascades (progressive escalation)
# ---------------------------------------------------------------------------

def write_to_file_missing_content_error(
    rel_path: str,
    consecutive_failures: int,
    context_usage_percent: Optional[float] = None,
) -> str:
    """Progressive escalation for missing-content write failures.

    Args:
        rel_path: relative path to the file being written.
        consecutive_failures: count of identical failures so far. Drives
            the escalation tier:

              * 1 = soft suggestion (chunking, skeletons).
              * 2 = directive with numbered strategies.
              * 3+ = CRITICAL: forbid retry, mandate alternative.
        context_usage_percent: optional 0-100 reading of context-window
            usage. When > :data:`CONTEXT_WINDOW_WARNING_THRESHOLD_PERCENT`
            the response appends a context-fullness warning.

    Returns:
        LLM-facing message tuned to the escalation tier.
    """
    if consecutive_failures >= WRITE_RETRY_TIER_3:
        head = (
            f"CRITICAL: write to '{rel_path}' has failed {consecutive_failures} "
            "times in a row. Do NOT retry write_to_file with the same approach.\n"
            "Mandatory alternative: write a skeleton, then use the diff/replace "
            "tool to fill in each section iteratively. If the file is large, "
            "split into smaller modules."
        )
    elif consecutive_failures >= WRITE_RETRY_TIER_2:
        head = (
            f"Repeated failure writing '{rel_path}'. Strategies:\n"
            "  1) Reduce the payload size per write.\n"
            "  2) Write a minimal skeleton first, then patch incrementally.\n"
            "  3) Re-read the existing file before re-issuing the write."
        )
    else:
        head = (
            f"Write to '{rel_path}' came back without content. Try one of:\n"
            "  - Smaller chunked writes.\n"
            "  - A skeleton plus patch passes.\n"
            "  - Re-reading the file first if you are mid-edit."
        )

    if (
        context_usage_percent is not None
        and context_usage_percent >= CONTEXT_WINDOW_WARNING_THRESHOLD_PERCENT
    ):
        head += (
            "\n\nNote: context window is "
            f"{int(context_usage_percent)}% full; consider summarising or "
            "checkpointing before continuing."
        )
    return head


def replace_in_file_missing_diff_error(rel_path: str) -> str:
    """Replace-in-file received a malformed diff payload.

    Args:
        rel_path: relative path of the target file.

    Returns:
        LLM-facing message explaining the SEARCH/REPLACE block contract.
    """
    return (
        f"replace_in_file for '{rel_path}' rejected the diff payload.\n"
        "Format rules:\n"
        "  - Each hunk uses SEARCH and REPLACE delimiter blocks.\n"
        "  - SEARCH content must match the file byte-for-byte (whitespace, "
        "trailing newline, indentation).\n"
        "  - You may issue multiple hunks per call.\n"
        "  - If you are unsure of current content, read the file first, "
        "then re-issue with verified SEARCH text."
    )


def execute_command_missing_command_error() -> str:
    """An execute_command tool call had no command string.

    Returns:
        LLM-facing message instructing the LLM to populate the command field.
    """
    return (
        "execute_command received an empty command. Populate the 'command' "
        "field with a single shell-runnable string; do not omit it."
    )


def file_edit_with_user_changes(
    rel_path: str,
    user_edits: str,
    auto_formatting_edits: Optional[str] = None,
    final_content: Optional[str] = None,
    new_problems_message: Optional[str] = None,
) -> str:
    """The user manually edited the file mid-edit; here is the new baseline.

    Args:
        rel_path: relative path of the edited file.
        user_edits: summary of what the user changed.
        auto_formatting_edits: optional summary of auto-formatter changes.
        final_content: optional full final file content for the LLM to
            treat as the new baseline.
        new_problems_message: optional lint / diagnostic delta.

    Returns:
        LLM-facing message instructing the LLM to adopt the final content
        as the new ground truth for subsequent edits.
    """
    sections = [f"User edited '{rel_path}' before your write landed."]
    sections.append(f"<user_edits>{user_edits.strip()}</user_edits>")
    if auto_formatting_edits:
        sections.append(
            f"<auto_format>{auto_formatting_edits.strip()}</auto_format>"
        )
    if final_content:
        sections.append(
            "<final_file_content>\n"
            f"{final_content}\n"
            "</final_file_content>"
        )
    if new_problems_message:
        sections.append(
            f"<diagnostics>{new_problems_message.strip()}</diagnostics>"
        )
    sections.append(
        "Treat <final_file_content> as the authoritative baseline. Do not "
        "re-write the file wholesale; if you need further edits, base them "
        "on this version."
    )
    return "\n\n".join(sections)


def file_edit_without_user_changes(
    rel_path: str,
    auto_formatting_edits: Optional[str] = None,
    final_content: Optional[str] = None,
    new_problems_message: Optional[str] = None,
) -> str:
    """Edit succeeded without user intervention; here is the new baseline.

    Args:
        rel_path: relative path of the edited file.
        auto_formatting_edits: optional auto-formatter summary.
        final_content: optional full final file content.
        new_problems_message: optional lint / diagnostic delta.

    Returns:
        LLM-facing message confirming the write and binding the baseline.
    """
    sections = [f"Edit to '{rel_path}' applied successfully."]
    if auto_formatting_edits:
        sections.append(
            f"<auto_format>{auto_formatting_edits.strip()}</auto_format>"
        )
    if final_content:
        sections.append(
            "<final_file_content>\n"
            f"{final_content}\n"
            "</final_file_content>"
        )
    if new_problems_message:
        sections.append(
            f"<diagnostics>{new_problems_message.strip()}</diagnostics>"
        )
    sections.append(
        "Use <final_file_content> as the reference for any future SEARCH/"
        "REPLACE in this file."
    )
    return "\n\n".join(sections)


def diff_error(rel_path: str, original_content: Optional[str] = None) -> str:
    """SEARCH/REPLACE diff application failed.

    Args:
        rel_path: relative path of the target file.
        original_content: optional pre-edit content so the LLM can re-align.

    Returns:
        LLM-facing message explaining likely causes and the recovery path.
    """
    sections = [
        f"Diff application to '{rel_path}' failed. Likely causes:",
        "  - SEARCH text does not match the current file byte-for-byte.",
        "  - Hunks were applied out of order, or one hunk depended on a "
        "prior hunk that did not match.",
        "  - The file was modified externally since the last read.",
    ]
    if original_content:
        sections.append(
            "<reverted_content>\n"
            f"{original_content}\n"
            "</reverted_content>"
        )
    sections.append(
        "Recovery: re-read the file, recompute SEARCH text against the "
        "fresh content, and re-issue smaller hunks. If three diff attempts "
        "fail in a row, fall back to a full rewrite via write_to_file."
    )
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Context lifecycle notices
# ---------------------------------------------------------------------------

def context_truncation_notice() -> str:
    """Standalone notice surfacing context history truncation to the LLM.

    Returns:
        LLM-facing string explaining that history was compacted, original
        task intent and latest user messages are intact.
    """
    return (
        "[Note] Older conversation turns were truncated to free context. "
        "The original task intent and the user's most recent messages are "
        "preserved; do not invent context from missing turns."
    )


def duplicate_file_read_notice(rel_path: str, prior_timestamp: str) -> str:
    """File was previously read this session; the duplicate is elided.

    Args:
        rel_path: file that was re-read.
        prior_timestamp: ISO-ish timestamp of the prior read.

    Returns:
        Short bracket notice the dedup pass injects in place of the
        duplicate read.
    """
    return (
        f"[Note] '{rel_path}' was previously read at {prior_timestamp}; "
        "duplicate content elided. Refer to the earlier read."
    )


def duplicate_payload_notice(label: str, prior_timestamp: str) -> str:
    """Generalised duplicate-payload elision notice.

    Args:
        label: descriptor of the elided payload (e.g. ``"RAG snippet 'X'"``
            or ``"nvidia-smi output"``).
        prior_timestamp: ISO-ish timestamp of the prior emission.

    Returns:
        Short bracket notice for the dedup pass.
    """
    return (
        f"[Note] {label} duplicate elided (previously emitted "
        f"{prior_timestamp})."
    )


def cached_read_notice(rel_path: str, read_count: int) -> str:
    """Cache-hit notice for short-circuited file-read calls.

    Args:
        rel_path: file whose read was served from cache.
        read_count: number of times this file has been read in the session.

    Returns:
        Short bracket notice for the file-read cache.
    """
    return (
        f"[Note] '{rel_path}' served from per-session cache (read "
        f"{read_count} times; mtime unchanged)."
    )


def condense_resume_notice() -> str:
    """Notice emitted after structured summarisation; warns LLM not to assume.

    Returns:
        LLM-facing message instructing the LLM to ask before assuming the
        next action.
    """
    return (
        "The conversation was summarised. Do NOT assume the user's next "
        "action; if the summary leaves any ambiguity, ask explicitly what "
        "to work on next."
    )


def file_context_warning(edited_files: Sequence[str]) -> str:
    """Files were externally modified; LLM must re-read before editing.

    Args:
        edited_files: list of relative paths that were modified outside
            Ultron since the last read.

    Returns:
        LLM-facing ``<explicit_instructions>`` block forcing a re-read.
    """
    if not edited_files:
        return ""
    lines = "\n".join(f"  - {p}" for p in edited_files)
    return (
        "<explicit_instructions>\n"
        f"CRITICAL: {len(edited_files)} file(s) were modified outside of "
        "Ultron since you last read them. Re-read each before any further "
        "edit; cached content is stale.\n"
        f"{lines}\n"
        "After you read a file once, you do not need to re-read it again "
        "during subsequent edits in this turn.\n"
        "</explicit_instructions>"
    )


def loop_soft_warning(signature: str, count: int) -> str:
    """Soft warning injected when the loop detector hits its first threshold.

    Args:
        signature: canonical signature of the repeated event.
        count: consecutive-identical count.

    Returns:
        Short hint that the LLM may use to self-correct.
    """
    return (
        f"[Hint] You have repeated the action '{signature}' {count} times "
        "without progress. Try a different approach or end the turn."
    )


def loop_hard_escalation(signature: str, count: int) -> str:
    """Hard escalation when the loop detector exceeds its kill threshold.

    Args:
        signature: canonical signature of the repeated event.
        count: consecutive-identical count.

    Returns:
        Message the orchestrator presents to the user when the agent is
        stuck.
    """
    return (
        f"Ultron has repeated '{signature}' {count} times without making "
        "progress and stopped automatically. Tell me what you want to do "
        "differently."
    )


# ---------------------------------------------------------------------------
# Resumption / mode
# ---------------------------------------------------------------------------

def task_resumption(
    mode: str,
    ago_text: str,
    cwd: str,
    *,
    was_recent: bool,
    response_text: Optional[str] = None,
    has_pending_file_context_warnings: bool = False,
) -> tuple[str, str]:
    """Resume a previously-interrupted task with mode-specific guardrails.

    Args:
        mode: ``"plan"`` or ``"act"`` resumption mode.
        ago_text: human-readable elapsed-time hint (``"5 minutes ago"``).
        cwd: working directory of the resumed task.
        was_recent: whether the interruption was recent enough that the
            workspace probably has not drifted.
        response_text: optional user message that triggered the resume.
        has_pending_file_context_warnings: True when an externally-edited
            file warning must be raised before continuing.

    Returns:
        Two strings: ``(resumption_context, user_response)``. The
        orchestrator typically prepends the first to the system context
        and uses the second as the next user message.
    """
    sections = [
        f"Resuming task in '{cwd}' ({ago_text}).",
        "Mode: " + ("plan" if mode == "plan" else "act") + ".",
    ]
    if not was_recent:
        sections.append(
            "Time has passed; treat the workspace as potentially modified. "
            "Verify the state of any file you intend to edit before doing so."
        )
    if has_pending_file_context_warnings:
        sections.append(
            "Pending file-context warnings exist; address them before any "
            "further edits."
        )
    if mode == "plan":
        sections.append(
            "Plan-mode constraints apply: information gathering and "
            "planning only. Ask before executing mutating actions."
        )
    resumption = "\n".join(sections)

    if response_text:
        user = response_text.strip()
    elif mode == "plan":
        user = (
            "(no message; please describe what you want to plan or "
            "continue investigating)"
        )
    else:
        user = "(no message; continue the previously-described task)"
    return resumption, user


def plan_mode_instructions() -> str:
    """System instructions injected when the orchestrator is in plan mode.

    Returns:
        LLM-facing instructions describing the plan-mode contract: no
        mutating actions, structured plan output, ask for mode flip.
    """
    return (
        "You are in PLAN MODE. Do not execute any mutating action this "
        "turn. Use the available read-only tools to gather information. "
        "When you are ready, produce a structured plan with:\n"
        "  1) the goal in one sentence,\n"
        "  2) a numbered list of steps,\n"
        "  3) any files / commands / external calls each step would issue.\n"
        "Then ask the user to confirm and switch to ACT mode before acting."
    )


# ---------------------------------------------------------------------------
# File listings
# ---------------------------------------------------------------------------

def format_files_list(
    absolute_path: str,
    files: Sequence[str],
    *,
    did_hit_limit: bool,
    ignore_predicate: Optional[callable] = None,
    voice_safe: bool = False,
) -> str:
    """Render a file listing with optional ignore-marker decoration.

    Args:
        absolute_path: directory the listing was taken from.
        files: paths to render (already resolved, in display order).
        did_hit_limit: whether the listing was truncated.
        ignore_predicate: optional callable mapping path -> bool. True
            means the path is ignored by policy; the line gets the lock
            symbol prefix.
        voice_safe: when True, swap the lock glyph for ``[LOCKED]``.

    Returns:
        Newline-delimited string suitable for prompt injection or TTS.
    """
    lock = LOCK_TEXT_SYMBOL_TTS if voice_safe else LOCK_TEXT_SYMBOL
    out_lines: list[str] = [f"Listing of {absolute_path}:"]
    for path in files:
        marker = ""
        if ignore_predicate is not None:
            try:
                if ignore_predicate(path):
                    marker = f"{lock} "
            except Exception:  # noqa: BLE001 - fail-open on predicate errors
                marker = ""
        out_lines.append(f"  {marker}{path}")
    if did_hit_limit:
        out_lines.append(
            "[Note] Listing was truncated; narrow with a glob filter or "
            "ask for a specific subdirectory."
        )
    return "\n".join(out_lines)


def create_pretty_patch(
    filename: str,
    old_str: Optional[str],
    new_str: Optional[str],
) -> str:
    """Produce a compact unified-diff for display.

    Args:
        filename: filename header for the patch (informational).
        old_str: prior file content (empty string when creating).
        new_str: new file content (empty string when deleting).

    Returns:
        Unified-diff string with the standard file headers omitted (the
        caller already knows the filename).
    """
    import difflib

    a = (old_str or "").splitlines()
    b = (new_str or "").splitlines()
    diff_lines = list(
        difflib.unified_diff(
            a,
            b,
            fromfile=filename,
            tofile=filename,
            lineterm="",
        )
    )
    # Drop the standard 4-line header (file metadata) for compactness.
    if len(diff_lines) >= 4:
        diff_lines = diff_lines[3:]
    return "\n".join(diff_lines)


# ---------------------------------------------------------------------------
# Voice / orchestrator-facing notices
# ---------------------------------------------------------------------------

def voice_search_unavailable_voice() -> str:
    """User-facing TTS message when every search provider has tripped."""
    return "I can't reach search right now."


def voice_memory_unavailable_voice() -> str:
    """User-facing TTS message when the memory store is unreachable."""
    return "Memory's offline; I'll keep going without prior context."


def voice_gaming_mode_locked_voice(action: str) -> str:
    """Notice spoken when a gaming-mode policy denies an action.

    Args:
        action: brief description of the denied action.
    """
    return f"Gaming mode's blocking {action}; flip it off if you really want it."


def voice_clarify_voice(question: str) -> str:
    """Wrap a clarifying question in the canonical Ultron cadence."""
    return question.strip().rstrip("?") + "?"


# ---------------------------------------------------------------------------
# Helpers for callers
# ---------------------------------------------------------------------------

def render_iterable_as_lines(items: Iterable[str], *, indent: str = "  - ") -> str:
    """Render an iterable as ``indent``-prefixed lines (used in templates).

    Args:
        items: items to render.
        indent: per-line prefix.

    Returns:
        Newline-joined string.
    """
    return "\n".join(f"{indent}{item}" for item in items)


__all__ = [
    "CONTEXT_WINDOW_WARNING_THRESHOLD_PERCENT",
    "LOCK_TEXT_SYMBOL",
    "LOCK_TEXT_SYMBOL_TTS",
    "TOOL_USE_REMINDER",
    "WRITE_RETRY_TIER_2",
    "WRITE_RETRY_TIER_3",
    "cached_read_notice",
    "condense_resume_notice",
    "context_truncation_notice",
    "create_pretty_patch",
    "diff_error",
    "duplicate_file_read_notice",
    "duplicate_payload_notice",
    "execute_command_missing_command_error",
    "file_context_warning",
    "file_edit_with_user_changes",
    "file_edit_without_user_changes",
    "format_files_list",
    "ignore_path_error",
    "ignore_path_error_voice",
    "invalid_mcp_tool_argument_error",
    "loop_hard_escalation",
    "loop_soft_warning",
    "missing_tool_parameter_error",
    "no_tools_used",
    "permission_denied_error",
    "plan_mode_instructions",
    "render_iterable_as_lines",
    "repeated_tool_call",
    "replace_in_file_missing_diff_error",
    "task_resumption",
    "too_many_mistakes",
    "too_many_mistakes_voice",
    "tool_already_used",
    "tool_denied",
    "tool_denied_voice",
    "tool_error",
    "tool_error_voice",
    "voice_clarify_voice",
    "voice_gaming_mode_locked_voice",
    "voice_memory_unavailable_voice",
    "voice_search_unavailable_voice",
    "write_to_file_missing_content_error",
]
