"""Tests for the T3 36-event hook lifecycle + HookDecision shape."""

from __future__ import annotations

import pytest

from kenning.hooks.lifecycle import (
    HOOK_DECISION_SEVERITY,
    HookDecision,
    HookKind,
    HookOutcome,
    HookOutcomeKind,
    HookPayload,
    make_block,
    make_pass,
    merge_hook_decisions,
    resolve_block_message,
)


# ----------------------------------------------------------------------
# HookKind expansion


def test_hookkind_contains_expected_event_count() -> None:
    # 9 cline-derived + 5 kenning voice + 29 T3 OpenClaw additions = 43.
    # (The OpenClaw catalog itself ships 36 events; kenning's superset
    # adds voice-specific lifecycle points beyond OpenClaw's set.)
    assert len(HookKind) == 9 + 5 + 29


def test_hookkind_includes_t3_additions() -> None:
    expected = {
        "BeforeModelResolve", "BeforePromptBuild", "AgentTurnPrepare",
        "BeforeAgentReply", "ModelCallStarted", "ModelCallEnded",
        "LlmInput", "LlmOutput", "BeforeAgentFinalize", "AgentEnd",
        "BeforeAgentRun", "AfterCompaction", "BeforeReset",
        "InboundClaim", "MessageReceived", "MessageSending", "MessageSent",
        "BeforeMessageWrite", "ToolResultPersist",
        "SessionStart", "SessionEnd",
        "SubagentSpawning", "SubagentSpawned", "SubagentEnded",
        "SubagentDeliveryTarget", "GatewayStart", "GatewayStop",
        "HeartbeatPromptContribution", "CronChanged",
    }
    actual = {h.value for h in HookKind}
    missing = expected - actual
    assert not missing, f"missing T3 hooks: {missing}"


def test_hookkind_preserves_original_events() -> None:
    # Original 14 must still be enumerable so existing callers don't break.
    for name in (
        "TaskStart", "TaskResume", "TaskCancel", "TaskComplete",
        "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact",
        "Notification", "PreLLMRequest", "PreMemoryWrite",
        "PreGamingEngage", "PreDesktopAction", "WakeWordTriggered",
    ):
        assert any(h.value == name for h in HookKind), f"missing legacy hook: {name}"


def test_hookpayload_to_json_serialises() -> None:
    payload = HookPayload(
        kind=HookKind.BEFORE_TOOL_USE if hasattr(HookKind, "BEFORE_TOOL_USE") else HookKind.PRE_TOOL_USE,
        session_id="s1",
        turn_id="t1",
        actor="voice",
        extra={"tool": "memory.write"},
    )
    body = payload.to_json()
    assert body["session_id"] == "s1"
    assert body["extra"] == {"tool": "memory.write"}


# ----------------------------------------------------------------------
# HookDecision discriminator


def test_hookdecision_severity_block_beats_pass() -> None:
    assert HOOK_DECISION_SEVERITY[HookOutcomeKind.BLOCK] > HOOK_DECISION_SEVERITY[HookOutcomeKind.PASS]


def test_make_pass_returns_pass_outcome() -> None:
    decision = make_pass()
    assert decision.outcome == HookOutcomeKind.PASS
    assert decision.blocked is False
    assert decision.severity == 0


def test_make_pass_with_message_preserves_message() -> None:
    decision = make_pass("ok with you")
    assert decision.message == "ok with you"


def test_make_block_requires_reason() -> None:
    with pytest.raises(ValueError):
        make_block("")


def test_make_block_returns_block_outcome() -> None:
    decision = make_block("matched pii regex /email/")
    assert decision.outcome == HookOutcomeKind.BLOCK
    assert decision.blocked is True
    assert decision.severity == 2


def test_make_block_accepts_optional_fields() -> None:
    decision = make_block(
        "matched cost limit",
        message="that would cost more than you want",
        category="cost_limit",
        metadata={"estimate": 12000},
    )
    assert decision.message == "that would cost more than you want"
    assert decision.category == "cost_limit"
    assert decision.metadata == {"estimate": 12000}


# ----------------------------------------------------------------------
# merge_hook_decisions


def test_merge_none_first_returns_second() -> None:
    result = merge_hook_decisions(None, make_pass())
    assert result.outcome == HookOutcomeKind.PASS


def test_merge_block_beats_pass() -> None:
    result = merge_hook_decisions(make_pass(), make_block("nope"))
    assert result.blocked


def test_merge_pass_does_not_beat_block() -> None:
    result = merge_hook_decisions(make_block("nope"), make_pass())
    assert result.blocked


def test_merge_two_passes_returns_first() -> None:
    a = make_pass("first")
    b = make_pass("second")
    result = merge_hook_decisions(a, b)
    assert result.message == "first"


def test_merge_two_blocks_preserves_first() -> None:
    a = make_block("first block", category="pii")
    b = make_block("second block", category="cost")
    result = merge_hook_decisions(a, b)
    assert result.category == "pii"


# ----------------------------------------------------------------------
# resolve_block_message


def test_resolve_block_message_empty_for_pass() -> None:
    assert resolve_block_message(make_pass()) == ""


def test_resolve_block_message_uses_message_when_present() -> None:
    decision = make_block("internal", message="please rephrase")
    assert resolve_block_message(decision) == "please rephrase"


def test_resolve_block_message_uses_fallback_when_no_message() -> None:
    decision = make_block("internal")
    rendered = resolve_block_message(decision, fallback_prefix="Sorry, not that")
    assert rendered == "Sorry, not that"


def test_resolve_block_message_appends_blocked_by() -> None:
    decision = make_block("internal", message="please rephrase")
    rendered = resolve_block_message(decision, blocked_by="pii_policy")
    assert "(blocked by pii_policy)" in rendered


# ----------------------------------------------------------------------
# HookOutcome (cline-derived subprocess shape) untouched by T3


def test_hookoutcome_defaults() -> None:
    out = HookOutcome()
    assert out.cancel is False
    assert out.context_modification == ""
    assert out.error_message == ""
    assert out.extra == {}
