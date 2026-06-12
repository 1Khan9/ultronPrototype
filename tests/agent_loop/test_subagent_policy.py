"""Tests for the depth-aware subagent tool-policy denylist (T7)."""

from __future__ import annotations

import pytest

from kenning.agent_loop.subagent_policy import (
    DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH,
    PolicySource,
    SUBAGENT_TOOL_DENY_ALWAYS,
    SUBAGENT_TOOL_DENY_LEAF,
    SubagentPolicyConfig,
    filter_tools_by_policy,
    is_leaf,
    resolve_subagent_tool_policy,
)


# ----------------------------------------------------------------------
# Constants


def test_default_max_spawn_depth_is_one() -> None:
    assert DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH == 1


def test_deny_always_includes_gateway_and_tts() -> None:
    # OpenClaw direct ports.
    for name in ("gateway", "agents_list", "session_status", "cron", "sessions_send"):
        assert name in SUBAGENT_TOOL_DENY_ALWAYS
    # Kenning extensions.
    for name in ("tts_speak", "kokoro_speak", "gaming_mode_engage", "set_validator"):
        assert name in SUBAGENT_TOOL_DENY_ALWAYS


def test_deny_leaf_includes_spawn_management() -> None:
    for name in ("subagents", "sessions_list", "sessions_history", "sessions_spawn"):
        assert name in SUBAGENT_TOOL_DENY_LEAF
    # Kenning extensions.
    for name in ("mcp_add_server", "mcp_remove_server"):
        assert name in SUBAGENT_TOOL_DENY_LEAF


# ----------------------------------------------------------------------
# is_leaf


def test_is_leaf_at_default_depth_one_is_leaf() -> None:
    assert is_leaf(1) is True


def test_is_leaf_at_depth_zero_not_leaf() -> None:
    assert is_leaf(0) is False


def test_is_leaf_at_higher_depth_is_leaf() -> None:
    assert is_leaf(5) is True


def test_is_leaf_respects_custom_max_spawn() -> None:
    assert is_leaf(1, max_spawn_depth=3) is False
    assert is_leaf(3, max_spawn_depth=3) is True


def test_is_leaf_clamps_invalid_max() -> None:
    # max < 1 is normalised to 1 so depth=1 always leaf.
    assert is_leaf(1, max_spawn_depth=0) is True


# ----------------------------------------------------------------------
# resolve_subagent_tool_policy default depth


def test_default_policy_at_depth_one_is_leaf() -> None:
    policy = resolve_subagent_tool_policy()
    assert policy.is_leaf is True
    assert policy.depth == 1


def test_default_policy_denies_always_set() -> None:
    policy = resolve_subagent_tool_policy()
    for name in SUBAGENT_TOOL_DENY_ALWAYS:
        assert name in policy.deny


def test_default_policy_denies_leaf_set_at_leaf_depth() -> None:
    policy = resolve_subagent_tool_policy(depth=1)
    for name in SUBAGENT_TOOL_DENY_LEAF:
        assert name in policy.deny


def test_default_policy_does_not_deny_leaf_at_intermediate_depth() -> None:
    cfg = SubagentPolicyConfig(max_spawn_depth=3)
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert policy.is_leaf is False
    for name in SUBAGENT_TOOL_DENY_LEAF:
        assert name not in policy.deny


# ----------------------------------------------------------------------
# Policy decisions: is_permitted


def test_deny_always_tool_rejected_at_any_depth() -> None:
    for depth in (1, 2, 5):
        policy = resolve_subagent_tool_policy(
            depth=depth,
            config=SubagentPolicyConfig(max_spawn_depth=5),
        )
        assert policy.is_permitted("gateway") is False
        assert policy.is_permitted("tts_speak") is False


def test_leaf_deny_tool_permitted_at_intermediate_depth() -> None:
    cfg = SubagentPolicyConfig(max_spawn_depth=3)
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert policy.is_permitted("sessions_spawn") is True


def test_leaf_deny_tool_rejected_at_leaf_depth() -> None:
    cfg = SubagentPolicyConfig(max_spawn_depth=3)
    policy = resolve_subagent_tool_policy(depth=3, config=cfg)
    assert policy.is_permitted("sessions_spawn") is False


def test_arbitrary_tool_permitted_when_not_in_deny() -> None:
    policy = resolve_subagent_tool_policy()
    assert policy.is_permitted("file_read") is True


# ----------------------------------------------------------------------
# Custom allow + also_allow


def test_explicit_allow_overrides_deny() -> None:
    cfg = SubagentPolicyConfig(allow=frozenset({"sessions_spawn"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "sessions_spawn" not in policy.deny
    assert policy.is_permitted("sessions_spawn") is True


def test_also_allow_overrides_deny_without_switching_to_allowlist_mode() -> None:
    cfg = SubagentPolicyConfig(also_allow=frozenset({"sessions_spawn"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "sessions_spawn" not in policy.deny
    # also_allow stays additive; arbitrary tools still allowed.
    assert policy.is_permitted("file_read") is True


def test_allow_set_switches_to_allowlist_only() -> None:
    cfg = SubagentPolicyConfig(allow=frozenset({"file_read"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    # file_read explicitly allowed.
    assert policy.is_permitted("file_read") is True
    # An arbitrary tool not in allow set is implicitly denied.
    assert policy.is_permitted("list_files") is False


def test_extra_deny_added() -> None:
    cfg = SubagentPolicyConfig(extra_deny=frozenset({"custom_tool"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "custom_tool" in policy.deny
    assert policy.sources["custom_tool"] == PolicySource.AGENT


def test_extra_deny_leaf_only_applies_at_leaf() -> None:
    cfg = SubagentPolicyConfig(
        max_spawn_depth=3,
        extra_deny_leaf=frozenset({"only_at_leaf"}),
    )
    intermediate = resolve_subagent_tool_policy(depth=1, config=cfg)
    leaf = resolve_subagent_tool_policy(depth=3, config=cfg)
    assert "only_at_leaf" not in intermediate.deny
    assert "only_at_leaf" in leaf.deny


def test_clear_default_deny_always_drops_defaults() -> None:
    cfg = SubagentPolicyConfig(clear_default_deny_always=True)
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "gateway" not in policy.deny
    assert "tts_speak" not in policy.deny


def test_clear_default_deny_leaf_drops_leaf_defaults() -> None:
    cfg = SubagentPolicyConfig(clear_default_deny_leaf=True)
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "sessions_spawn" not in policy.deny
    # DENY_ALWAYS still applies.
    assert "gateway" in policy.deny


# ----------------------------------------------------------------------
# filter_tools_by_policy


def test_filter_returns_only_permitted_tools_in_order() -> None:
    policy = resolve_subagent_tool_policy()
    tools = ["file_read", "gateway", "list_files", "tts_speak", "search"]
    filtered = filter_tools_by_policy(tools, policy)
    assert filtered == ("file_read", "list_files", "search")


def test_filter_empty_input_returns_empty() -> None:
    policy = resolve_subagent_tool_policy()
    assert filter_tools_by_policy([], policy) == ()


def test_filter_allowlist_mode() -> None:
    cfg = SubagentPolicyConfig(allow=frozenset({"file_read", "search"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    filtered = filter_tools_by_policy(
        ["file_read", "list_files", "search", "rag_query"], policy,
    )
    assert filtered == ("file_read", "search")


# ----------------------------------------------------------------------
# explain helper


def test_explain_for_deny_default() -> None:
    policy = resolve_subagent_tool_policy()
    assert "deny" in policy.explain("gateway").lower()


def test_explain_for_default_allow() -> None:
    policy = resolve_subagent_tool_policy()
    assert "default" in policy.explain("file_read").lower()


def test_explain_for_explicit_allow() -> None:
    cfg = SubagentPolicyConfig(allow=frozenset({"file_read"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "allow" in policy.explain("file_read").lower()


def test_explain_for_implicit_deny_in_allowlist_mode() -> None:
    cfg = SubagentPolicyConfig(allow=frozenset({"file_read"}))
    policy = resolve_subagent_tool_policy(depth=1, config=cfg)
    assert "implicit" in policy.explain("list_files").lower()
