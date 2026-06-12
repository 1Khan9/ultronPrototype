"""Tests for kenning.hooks.lifecycle."""

from __future__ import annotations

from kenning.hooks import lifecycle as lc


class TestHookKind:
    def test_canonical_names_in_enum(self) -> None:
        for name in (
            "TaskStart", "TaskResume", "TaskCancel", "TaskComplete",
            "UserPromptSubmit", "PreToolUse", "PostToolUse",
            "PreCompact", "Notification",
        ):
            assert name in {k.value for k in lc.HookKind}

    def test_kenning_specific_extensions(self) -> None:
        for name in (
            "PreLLMRequest", "PreMemoryWrite", "PreGamingEngage",
            "PreDesktopAction", "WakeWordTriggered",
        ):
            assert name in {k.value for k in lc.HookKind}


class TestHookPayload:
    def test_to_json_minimal(self) -> None:
        payload = lc.HookPayload(kind=lc.HookKind.TASK_START)
        out = payload.to_json()
        assert out["kind"] == "TaskStart"
        assert out["session_id"] == ""
        assert out["extra"] == {}

    def test_to_json_full(self) -> None:
        payload = lc.HookPayload(
            kind=lc.HookKind.PRE_TOOL_USE,
            session_id="s-1",
            turn_id="t-2",
            actor="voice",
            extra={"tool": "read_file", "path": "src/a.py"},
        )
        out = payload.to_json()
        assert out["kind"] == "PreToolUse"
        assert out["session_id"] == "s-1"
        assert out["extra"]["tool"] == "read_file"


class TestHookOutcome:
    def test_defaults(self) -> None:
        outcome = lc.HookOutcome()
        assert outcome.cancel is False
        assert outcome.context_modification == ""
        assert outcome.error_message == ""

    def test_construction(self) -> None:
        outcome = lc.HookOutcome(
            cancel=True,
            context_modification="hello",
            error_message="blocked",
            extra={"detail": "x"},
        )
        assert outcome.cancel is True
        assert outcome.context_modification == "hello"
        assert outcome.extra["detail"] == "x"


class TestConstants:
    def test_timeout_default(self) -> None:
        assert lc.DEFAULT_HOOK_TIMEOUT_SECONDS == 10.0

    def test_context_cap_default(self) -> None:
        assert lc.DEFAULT_CONTEXT_MOD_CAP_CHARS == 8 * 1024
