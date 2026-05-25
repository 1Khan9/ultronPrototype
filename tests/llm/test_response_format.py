"""Tests for ultron.llm.response_format."""

from __future__ import annotations

import pytest

from ultron.llm import response_format as rf


# ---------------------------------------------------------------------------
# Generic tool errors
# ---------------------------------------------------------------------------

def test_tool_denied_returns_non_empty_string() -> None:
    out = rf.tool_denied()
    assert isinstance(out, str)
    assert out.strip()
    assert "deny" in out.lower() or "denied" in out.lower()


def test_tool_denied_voice_is_short() -> None:
    out = rf.tool_denied_voice()
    # Voice variants should be at most a short sentence.
    assert len(out) <= 80


def test_tool_error_wraps_detail_in_error_tag() -> None:
    out = rf.tool_error("filesystem timeout")
    assert "<error>filesystem timeout</error>" in out


def test_tool_error_truncates_long_detail() -> None:
    detail = "Q" * 1200  # Q is absent from every static template token.
    out = rf.tool_error(detail)
    assert "(truncated)" in out
    # The body should be capped at 600 + truncation suffix.
    body = out.split("<error>", 1)[1].split("</error>", 1)[0]
    assert body.count("Q") == 600
    assert body.endswith("... (truncated)")


def test_tool_error_with_no_detail() -> None:
    out = rf.tool_error()
    assert "<error>" in out and "</error>" in out


def test_tool_error_voice_caps_first_line() -> None:
    out = rf.tool_error_voice("first\nsecond\nthird")
    assert "second" not in out
    assert "first" in out


def test_tool_error_voice_no_detail() -> None:
    out = rf.tool_error_voice()
    assert isinstance(out, str) and len(out) <= 80


def test_tool_already_used_names_tool() -> None:
    out = rf.tool_already_used("read_file")
    assert "'read_file'" in out


def test_no_tools_used_includes_next_steps() -> None:
    out = rf.no_tools_used()
    assert "Next steps" in out
    assert "1)" in out and "2)" in out and "3)" in out


def test_no_tools_used_native_omits_reminder() -> None:
    native = rf.no_tools_used(using_native_tool_calls=True)
    legacy = rf.no_tools_used(using_native_tool_calls=False)
    assert rf.TOOL_USE_REMINDER not in native
    assert rf.TOOL_USE_REMINDER in legacy


def test_too_many_mistakes_wraps_feedback() -> None:
    out = rf.too_many_mistakes("use the smaller model")
    assert "<feedback>use the smaller model</feedback>" in out


def test_too_many_mistakes_without_feedback_asks_user() -> None:
    out = rf.too_many_mistakes()
    assert "ask" in out.lower()


def test_missing_tool_parameter_error_names_param() -> None:
    out = rf.missing_tool_parameter_error("path")
    assert "'path'" in out
    assert rf.TOOL_USE_REMINDER in out


def test_repeated_tool_call_includes_count_and_name() -> None:
    out = rf.repeated_tool_call("search", 4)
    assert "'search'" in out
    assert "4 times" in out


def test_invalid_mcp_tool_argument_error_names_both_targets() -> None:
    out = rf.invalid_mcp_tool_argument_error("notion", "search_notes")
    assert "'search_notes'" in out and "'notion'" in out


def test_permission_denied_error_includes_reason() -> None:
    out = rf.permission_denied_error("Cap-3 NEEDS_EXPLICIT_INTENT")
    assert "<reason>Cap-3 NEEDS_EXPLICIT_INTENT</reason>" in out


# ---------------------------------------------------------------------------
# Path / ignore violations
# ---------------------------------------------------------------------------

def test_ignore_path_error_wraps_path() -> None:
    out = rf.ignore_path_error("data/secrets/api.key")
    assert "<path>data/secrets/api.key</path>" in out


def test_ignore_path_error_voice_uses_leaf_name() -> None:
    out = rf.ignore_path_error_voice("C:/foo/bar/baz.key")
    assert "baz.key" in out


def test_ignore_path_error_voice_handles_backslashes() -> None:
    out = rf.ignore_path_error_voice("C:\\foo\\bar\\file.txt")
    assert "file.txt" in out


# ---------------------------------------------------------------------------
# Write / edit cascades (progressive escalation)
# ---------------------------------------------------------------------------

def test_write_to_file_tier_1_is_suggestion() -> None:
    out = rf.write_to_file_missing_content_error("a.py", 1)
    assert "CRITICAL" not in out
    assert "Try one of" in out or "Strategies" in out or "Try a different" in out


def test_write_to_file_tier_2_is_directive() -> None:
    out = rf.write_to_file_missing_content_error("a.py", 2)
    assert "Strategies" in out
    assert "1)" in out


def test_write_to_file_tier_3_is_critical_and_forbids() -> None:
    out = rf.write_to_file_missing_content_error("a.py", 3)
    assert "CRITICAL" in out
    assert "Mandatory alternative" in out


def test_write_to_file_appends_context_warning_above_threshold() -> None:
    out = rf.write_to_file_missing_content_error(
        "a.py", 1, context_usage_percent=75,
    )
    assert "context window" in out.lower()


def test_write_to_file_omits_context_warning_below_threshold() -> None:
    out = rf.write_to_file_missing_content_error(
        "a.py", 1, context_usage_percent=10,
    )
    assert "context window" not in out.lower()


def test_replace_in_file_missing_diff_lists_rules() -> None:
    out = rf.replace_in_file_missing_diff_error("foo.py")
    assert "'foo.py'" in out
    assert "SEARCH" in out and "REPLACE" in out


def test_execute_command_missing_command_error_is_concrete() -> None:
    out = rf.execute_command_missing_command_error()
    assert "'command'" in out


def test_file_edit_with_user_changes_includes_final_content() -> None:
    out = rf.file_edit_with_user_changes(
        "src/a.py",
        "renamed foo to bar",
        final_content="def bar(): pass",
    )
    assert "<final_file_content>" in out
    assert "def bar(): pass" in out
    assert "renamed foo to bar" in out


def test_file_edit_with_user_changes_minimal() -> None:
    out = rf.file_edit_with_user_changes("a.py", "no-op")
    assert "<user_edits>no-op</user_edits>" in out
    # The instructional footer mentions <final_file_content> as a token;
    # the test guards against the data-wrapper form being emitted.
    assert "<final_file_content>\n" not in out
    assert "</final_file_content>" not in out
    assert "<diagnostics>" not in out


def test_file_edit_without_user_changes_optional_sections() -> None:
    out = rf.file_edit_without_user_changes("a.py")
    assert "Edit to 'a.py' applied successfully" in out
    assert "<auto_format>" not in out
    assert "<diagnostics>" not in out


def test_file_edit_without_user_changes_with_diagnostics() -> None:
    out = rf.file_edit_without_user_changes(
        "a.py",
        new_problems_message="3 lint warnings",
    )
    assert "<diagnostics>3 lint warnings</diagnostics>" in out


def test_diff_error_includes_reverted_content_when_provided() -> None:
    out = rf.diff_error("a.py", original_content="def a(): pass")
    assert "<reverted_content>" in out
    assert "def a(): pass" in out


def test_diff_error_without_reverted_content() -> None:
    out = rf.diff_error("a.py")
    assert "<reverted_content>" not in out


# ---------------------------------------------------------------------------
# Context lifecycle notices
# ---------------------------------------------------------------------------

def test_context_truncation_notice_is_self_contained() -> None:
    out = rf.context_truncation_notice()
    assert out.startswith("[Note]")
    assert "truncated" in out.lower()


def test_duplicate_file_read_notice_includes_path_and_ts() -> None:
    out = rf.duplicate_file_read_notice("README.md", "2026-05-24T12:00:00Z")
    assert "'README.md'" in out
    assert "2026-05-24T12:00:00Z" in out


def test_duplicate_payload_notice_general() -> None:
    out = rf.duplicate_payload_notice("nvidia-smi output", "2026-05-24T12:00:00Z")
    assert "nvidia-smi output" in out


def test_cached_read_notice_includes_count() -> None:
    out = rf.cached_read_notice("a.py", 3)
    assert "'a.py'" in out
    assert "3 times" in out


def test_condense_resume_notice_warns_against_assumption() -> None:
    out = rf.condense_resume_notice()
    assert "ask" in out.lower()
    assert "not" in out.lower()


def test_file_context_warning_empty_returns_empty() -> None:
    assert rf.file_context_warning([]) == ""


def test_file_context_warning_lists_files() -> None:
    out = rf.file_context_warning(["a.py", "b.py"])
    assert "<explicit_instructions>" in out
    assert "  - a.py" in out and "  - b.py" in out
    assert "2 file" in out


def test_loop_soft_warning_includes_signature_and_count() -> None:
    out = rf.loop_soft_warning("read_file:a.py", 3)
    assert "[Hint]" in out
    assert "'read_file:a.py'" in out
    assert "3 times" in out


def test_loop_hard_escalation_is_user_facing() -> None:
    out = rf.loop_hard_escalation("read_file:a.py", 5)
    assert "stopped" in out.lower()


# ---------------------------------------------------------------------------
# Resumption / mode
# ---------------------------------------------------------------------------

def test_task_resumption_returns_two_strings() -> None:
    context, user = rf.task_resumption(
        "act", "5 minutes ago", "/tmp/proj", was_recent=True,
    )
    assert isinstance(context, str) and isinstance(user, str)
    assert "act" in context.lower()


def test_task_resumption_plan_no_message_prompts_user() -> None:
    _ctx, user = rf.task_resumption(
        "plan", "1 hour ago", "/tmp/proj", was_recent=False,
    )
    assert "describe" in user.lower()


def test_task_resumption_with_response_text_passes_through() -> None:
    _ctx, user = rf.task_resumption(
        "act", "1 min ago", "/tmp/proj", was_recent=True,
        response_text="  continue please  ",
    )
    assert user == "continue please"


def test_task_resumption_old_session_warns_about_drift() -> None:
    ctx, _ = rf.task_resumption(
        "act", "2 hours ago", "/tmp/proj", was_recent=False,
    )
    assert "verify" in ctx.lower() or "modified" in ctx.lower()


def test_task_resumption_pending_warnings_surfaced() -> None:
    ctx, _ = rf.task_resumption(
        "act", "1 min ago", "/tmp/proj", was_recent=True,
        has_pending_file_context_warnings=True,
    )
    assert "pending" in ctx.lower()


def test_plan_mode_instructions_forbids_mutation() -> None:
    out = rf.plan_mode_instructions()
    assert "PLAN MODE" in out
    assert "Do not execute" in out


# ---------------------------------------------------------------------------
# File listings
# ---------------------------------------------------------------------------

def test_format_files_list_basic() -> None:
    out = rf.format_files_list(
        "/tmp/proj", ["a.py", "b.py"], did_hit_limit=False,
    )
    assert "/tmp/proj" in out
    assert "a.py" in out and "b.py" in out


def test_format_files_list_with_ignore_predicate_marks_ignored() -> None:
    def predicate(path: str) -> bool:
        return path.endswith(".key")

    out = rf.format_files_list(
        "/tmp/proj", ["a.py", "secret.key"], did_hit_limit=False,
        ignore_predicate=predicate,
    )
    assert rf.LOCK_TEXT_SYMBOL in out
    # The lock should attach to secret.key, not a.py.
    lines = [ln for ln in out.splitlines() if "secret.key" in ln]
    assert lines and rf.LOCK_TEXT_SYMBOL in lines[0]


def test_format_files_list_voice_safe_uses_textual_lock() -> None:
    out = rf.format_files_list(
        "/tmp/proj", ["secret.key"], did_hit_limit=False,
        ignore_predicate=lambda p: True,
        voice_safe=True,
    )
    assert rf.LOCK_TEXT_SYMBOL_TTS in out
    assert rf.LOCK_TEXT_SYMBOL not in out


def test_format_files_list_truncation_notice_appended() -> None:
    out = rf.format_files_list(
        "/tmp/proj", ["a.py"], did_hit_limit=True,
    )
    assert "truncated" in out.lower()


def test_format_files_list_predicate_failure_does_not_break() -> None:
    def predicate(_: str) -> bool:
        raise RuntimeError("boom")

    out = rf.format_files_list(
        "/tmp/proj", ["a.py"], did_hit_limit=False,
        ignore_predicate=predicate,
    )
    # Should still render the file line even when the predicate fails.
    assert "a.py" in out


def test_create_pretty_patch_returns_diff_lines() -> None:
    patch = rf.create_pretty_patch("a.py", "x = 1\n", "x = 2\n")
    assert "-x = 1" in patch
    assert "+x = 2" in patch


def test_create_pretty_patch_handles_create() -> None:
    patch = rf.create_pretty_patch("a.py", "", "x = 1\n")
    assert "+x = 1" in patch


def test_create_pretty_patch_handles_delete() -> None:
    patch = rf.create_pretty_patch("a.py", "x = 1\n", "")
    assert "-x = 1" in patch


# ---------------------------------------------------------------------------
# Voice / orchestrator-facing notices
# ---------------------------------------------------------------------------

def test_voice_search_unavailable_voice_is_short() -> None:
    out = rf.voice_search_unavailable_voice()
    assert len(out) <= 80
    assert "search" in out.lower()


def test_voice_memory_unavailable_voice_is_short() -> None:
    out = rf.voice_memory_unavailable_voice()
    assert len(out) <= 100
    assert "memory" in out.lower() or "offline" in out.lower()


def test_voice_gaming_mode_locked_voice_includes_action() -> None:
    out = rf.voice_gaming_mode_locked_voice("desktop input")
    assert "desktop input" in out


def test_voice_clarify_voice_ensures_single_question_mark() -> None:
    out = rf.voice_clarify_voice("Do you mean Discord")
    assert out.endswith("?")
    out2 = rf.voice_clarify_voice("Do you mean Discord?")
    assert out2.endswith("?") and out2.count("?") == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_render_iterable_as_lines_default_indent() -> None:
    out = rf.render_iterable_as_lines(["a", "b", "c"])
    assert out == "  - a\n  - b\n  - c"


def test_render_iterable_as_lines_custom_indent() -> None:
    out = rf.render_iterable_as_lines(["a", "b"], indent="* ")
    assert out == "* a\n* b"


def test_constants_match_documented_thresholds() -> None:
    assert rf.WRITE_RETRY_TIER_2 == 2
    assert rf.WRITE_RETRY_TIER_3 == 3
    assert rf.CONTEXT_WINDOW_WARNING_THRESHOLD_PERCENT == 50


def test_all_module_public_names_are_callable_or_constant() -> None:
    # Sanity guard against export drift.
    for name in rf.__all__:
        attr = getattr(rf, name)
        assert attr is not None
        # Functions or simple constants only — no nested objects.
        assert callable(attr) or isinstance(attr, (str, int, float))
