"""Tests for the T11 hierarchical sandbox tool policy."""

from __future__ import annotations

import pytest

from ultron.safety.hierarchical_policy import (
    PolicySource,
    ResolvedSandboxToolPolicy,
    SandboxToolPolicy,
    explain,
    filter_tools,
    make_policy,
    resolve_sandbox_tool_policy,
)


# ----------------------------------------------------------------------
# make_policy + SandboxToolPolicy


def test_make_policy_strips_empty_and_dedupes() -> None:
    policy = make_policy(allow=["", "a", " ", "a", "b"])
    assert policy.allow == ("a", "b")


def test_make_policy_none_inputs_stay_none() -> None:
    policy = make_policy()
    assert policy.allow is None
    assert policy.deny is None


def test_make_policy_empty_list_stays_empty() -> None:
    # Empty allow signals "allow all" — distinguish from None.
    policy = make_policy(allow=[])
    assert policy.allow == ()


# ----------------------------------------------------------------------
# resolve_sandbox_tool_policy — precedence


def test_resolve_agent_wins_over_global_over_default() -> None:
    default = make_policy(allow=["d1"])
    glob = make_policy(allow=["g1"])
    agent = make_policy(allow=["a1"])
    resolved = resolve_sandbox_tool_policy(
        agent=agent, global_scope=glob, default=default,
    )
    assert resolved.allow == frozenset({"a1"})
    assert resolved.sources["a1"] == PolicySource.AGENT


def test_resolve_global_wins_when_agent_unset() -> None:
    default = make_policy(allow=["d1"])
    glob = make_policy(allow=["g1"])
    resolved = resolve_sandbox_tool_policy(global_scope=glob, default=default)
    assert resolved.allow == frozenset({"g1"})
    assert resolved.sources["g1"] == PolicySource.GLOBAL


def test_resolve_default_when_others_unset() -> None:
    default = make_policy(allow=["d1"])
    resolved = resolve_sandbox_tool_policy(default=default)
    assert resolved.allow == frozenset({"d1"})
    assert resolved.sources["d1"] == PolicySource.DEFAULT


def test_resolve_no_sources_returns_empty() -> None:
    resolved = resolve_sandbox_tool_policy()
    assert resolved.allow == frozenset()
    assert resolved.deny == frozenset()


# ----------------------------------------------------------------------
# allow: [] special case ("allow all")


def test_resolve_allow_empty_marks_unrestricted() -> None:
    resolved = resolve_sandbox_tool_policy(agent=make_policy(allow=[]))
    assert resolved.allow_is_empty_meaning_unrestricted is True
    assert resolved.allow == frozenset()


def test_unrestricted_allows_any_non_denied_tool() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(allow=[], deny=["forbidden"]),
    )
    assert resolved.is_permitted("anything") is True
    assert resolved.is_permitted("forbidden") is False


def test_non_empty_allow_switches_to_allowlist_only() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(allow=["one", "two"]),
    )
    assert resolved.allow_is_empty_meaning_unrestricted is False
    assert resolved.is_permitted("one") is True
    assert resolved.is_permitted("three") is False


# ----------------------------------------------------------------------
# also_allow — "extends without replacing"


def test_also_allow_extends_allow_set() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(allow=["one"], also_allow=["two"]),
    )
    assert resolved.is_permitted("one") is True
    assert resolved.is_permitted("two") is True
    assert resolved.is_permitted("three") is False


def test_also_allow_works_with_empty_allow_set() -> None:
    # When allow is unset (None) AND also_allow has values, those
    # values are permitted but the policy stays in unrestricted mode
    # (any non-denied tool is allowed).
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(also_allow=["extra"]),
    )
    assert resolved.allow == frozenset()
    assert resolved.also_allow == frozenset({"extra"})
    # No allow set -> unrestricted (every non-denied tool passes).
    assert resolved.is_permitted("arbitrary") is True


def test_also_allow_tagged_with_agent_source() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(also_allow=["aa"]),
    )
    assert resolved.sources["aa"] == PolicySource.AGENT


# ----------------------------------------------------------------------
# deny precedence


def test_deny_is_terminal() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(allow=["x"], deny=["x"]),
    )
    # Even though x is in allow, deny wins.
    assert resolved.is_permitted("x") is False


def test_deny_from_global_when_agent_unset() -> None:
    resolved = resolve_sandbox_tool_policy(
        global_scope=make_policy(deny=["blocked"]),
    )
    assert resolved.is_permitted("blocked") is False
    assert resolved.sources["blocked"] == PolicySource.GLOBAL


# ----------------------------------------------------------------------
# filter_tools


def test_filter_tools_preserves_order() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(deny=["bad"]),
    )
    out = filter_tools(["a", "bad", "b", "c"], resolved)
    assert out == ("a", "b", "c")


def test_filter_tools_empty_input() -> None:
    resolved = resolve_sandbox_tool_policy()
    assert filter_tools([], resolved) == ()


def test_filter_tools_allowlist_only_mode() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(allow=["one", "two"]),
    )
    out = filter_tools(["one", "two", "three"], resolved)
    assert out == ("one", "two")


# ----------------------------------------------------------------------
# explain


def test_explain_deny_includes_source() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(deny=["x"]),
    )
    assert "deny" in explain("x", resolved).lower()
    assert "agent" in explain("x", resolved).lower()


def test_explain_allow_includes_source() -> None:
    resolved = resolve_sandbox_tool_policy(
        global_scope=make_policy(allow=["x"]),
    )
    assert "allow" in explain("x", resolved).lower()
    assert "global" in explain("x", resolved).lower()


def test_explain_implicit_deny_in_allowlist_mode() -> None:
    resolved = resolve_sandbox_tool_policy(
        agent=make_policy(allow=["one"]),
    )
    assert "implicit" in explain("two", resolved).lower()


def test_explain_allow_all_special_case() -> None:
    resolved = resolve_sandbox_tool_policy(agent=make_policy(allow=[]))
    assert "allow_all" in explain("any_tool", resolved).lower()


def test_explain_default_allow_when_no_allow_set() -> None:
    resolved = resolve_sandbox_tool_policy()
    assert "default_allow" in explain("free", resolved).lower()
