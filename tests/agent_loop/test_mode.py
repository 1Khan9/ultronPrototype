"""Tests for kenning.agent_loop.mode."""

from __future__ import annotations

import pytest

from kenning.agent_loop import mode as md


class FakeClock:
    """Manually-advanced monotonic clock for deterministic TTL tests."""

    def __init__(self, *, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


# ---------------------------------------------------------------------------
# ModePolicy
# ---------------------------------------------------------------------------

class TestModePolicy:
    def test_default_act_policy_allows_tools(self) -> None:
        policy = md.DEFAULT_POLICIES[md.Mode.ACT]
        assert policy.allows_tool_side_effects is True
        assert policy.requires_confirmation is False
        assert policy.wrap_prefix_template == ""

    def test_default_plan_policy_gates_tools(self) -> None:
        policy = md.DEFAULT_POLICIES[md.Mode.PLAN]
        assert policy.allows_tool_side_effects is False
        assert policy.requires_confirmation is True
        assert "{plan}" in policy.wrap_prefix_template

    def test_wrap_response_substitutes_plan(self) -> None:
        policy = md.DEFAULT_POLICIES[md.Mode.PLAN]
        wrapped = policy.wrap_response("rewrite the README")
        assert "rewrite the README" in wrapped
        assert "do it" in wrapped.lower()

    def test_wrap_response_no_template_returns_unchanged(self) -> None:
        policy = md.ModePolicy(mode=md.Mode.ACT, wrap_prefix_template="")
        assert policy.wrap_response("hello") == "hello"

    def test_build_ack_returns_template_value(self) -> None:
        policy = md.DEFAULT_POLICIES[md.Mode.PLAN]
        assert policy.build_ack() == md.DEFAULT_PLAN_ACK


# ---------------------------------------------------------------------------
# ModeSession -- basic flips
# ---------------------------------------------------------------------------

class TestModeFlip:
    def test_initial_mode_is_act(self) -> None:
        session = md.ModeSession()
        assert session.mode is md.Mode.ACT

    def test_initial_mode_override(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        assert session.mode is md.Mode.PLAN

    def test_flip_changes_mode(self) -> None:
        session = md.ModeSession()
        result = session.flip(md.Mode.PLAN)
        assert result.was_change is True
        assert result.previous_mode is md.Mode.ACT
        assert result.new_mode is md.Mode.PLAN
        assert session.mode is md.Mode.PLAN

    def test_flip_to_same_mode_no_change(self) -> None:
        session = md.ModeSession()
        result = session.flip(md.Mode.ACT)
        assert result.was_change is False

    def test_flip_history_caps_at_32(self) -> None:
        session = md.ModeSession()
        session._flip_history_cap = 4  # noqa: SLF001
        for _ in range(10):
            session.flip(md.Mode.PLAN)
            session.flip(md.Mode.ACT)
        assert len(session.flip_history()) == 4


# ---------------------------------------------------------------------------
# Pending confirmations
# ---------------------------------------------------------------------------

class TestPendingConfirmations:
    def test_queue_plan_returns_confirmation(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        pending = session.queue_plan("plan body")
        assert pending.plan_body == "plan body"
        assert pending.mode is md.Mode.PLAN
        assert pending.confirmation_id

    def test_queue_uses_policy_timeout(self) -> None:
        clock = FakeClock()
        session = md.ModeSession(
            initial_mode=md.Mode.PLAN,
            clock=clock,
        )
        pending = session.queue_plan("p")
        # Default plan timeout is 30 s.
        assert pending.expires_at == 30.0

    def test_queue_timeout_override_takes_precedence(self) -> None:
        clock = FakeClock()
        session = md.ModeSession(initial_mode=md.Mode.PLAN, clock=clock)
        pending = session.queue_plan("p", timeout_override=5.0)
        assert pending.expires_at == 5.0

    def test_queue_timeout_zero_disables_expiry(self) -> None:
        clock = FakeClock()
        session = md.ModeSession(initial_mode=md.Mode.PLAN, clock=clock)
        pending = session.queue_plan("p", timeout_override=0.0)
        assert pending.expires_at == 0.0

    def test_consume_latest_returns_most_recent(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        session.queue_plan("first")
        second = session.queue_plan("second")
        consumed = session.consume_pending_confirmation()
        assert consumed is not None
        assert consumed.confirmation_id == second.confirmation_id

    def test_consume_by_id_matches(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        a = session.queue_plan("a")
        b = session.queue_plan("b")
        consumed = session.consume_pending_confirmation(a.confirmation_id)
        assert consumed is not None
        assert consumed.confirmation_id == a.confirmation_id
        # The other plan is still queued.
        remaining = session.peek_latest_pending()
        assert remaining is not None
        assert remaining.confirmation_id == b.confirmation_id

    def test_consume_missing_id_returns_none(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        assert session.consume_pending_confirmation("nope") is None

    def test_consume_wrong_topic_returns_plan_to_queue(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        pending = session.queue_plan("p", intent_topic="DESKTOP_AUTOMATION")
        consumed = session.consume_pending_confirmation(
            pending.confirmation_id, intent_topic_filter="GAMING_ENGAGE",
        )
        assert consumed is None
        # Still queued because the topic filter rejected it.
        assert session.pending_count() == 1

    def test_pending_expires_after_ttl(self) -> None:
        clock = FakeClock()
        session = md.ModeSession(initial_mode=md.Mode.PLAN, clock=clock)
        session.queue_plan("p", timeout_override=5.0)
        clock.advance(10.0)
        assert session.peek_latest_pending() is None
        assert session.pending_count() == 0

    def test_cancel_all_pending(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        session.queue_plan("a")
        session.queue_plan("b")
        cancelled = session.cancel_pending()
        assert len(cancelled) == 2
        assert session.pending_count() == 0

    def test_cancel_by_topic(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        a = session.queue_plan("a", intent_topic="GAMING")
        b = session.queue_plan("b", intent_topic="MEMORY")  # noqa: F841
        cancelled = session.cancel_pending(intent_topic_filter="GAMING")
        assert cancelled == (a.confirmation_id,)
        assert session.pending_count() == 1

    def test_flip_drops_pending_by_default(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        session.queue_plan("p")
        result = session.flip(md.Mode.ACT)
        assert len(result.invalidated_confirmations) == 1
        assert session.pending_count() == 0

    def test_flip_preserves_pending_when_opted_in(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        session.queue_plan("p")
        session.flip(md.Mode.ACT, invalidate_pending=False)
        assert session.pending_count() == 1

    def test_raw_plan_body_falls_back_to_plan_body(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        pending = session.queue_plan("wrapped: plan ack")
        assert pending.raw_plan_body == "wrapped: plan ack"

    def test_raw_plan_body_kept_when_supplied(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        pending = session.queue_plan(
            "wrapped: plan ack",
            raw_plan_body="here is my plan: rewrite the README",
        )
        assert pending.raw_plan_body.startswith("here is my plan")


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

class TestPolicyHelpers:
    def test_wrap_response_uses_current_mode(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        out = session.wrap_response("rewrite the README")
        assert "rewrite the README" in out
        assert "do it" in out.lower()

    def test_wrap_response_for_other_mode(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.ACT)
        out = session.wrap_response("plan body", mode=md.Mode.PLAN)
        assert "plan body" in out
        # ACT mode would have returned unwrapped.
        assert "do it" in out.lower()

    def test_should_execute_tools_act(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.ACT)
        assert session.should_execute_tools() is True

    def test_should_execute_tools_plan(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        assert session.should_execute_tools() is False

    def test_confirmation_required_plan(self) -> None:
        session = md.ModeSession(initial_mode=md.Mode.PLAN)
        assert session.confirmation_required() is True

    def test_set_policy_replaces_entry(self) -> None:
        session = md.ModeSession()
        new_policy = md.ModePolicy(mode=md.Mode.ACT, allows_tool_side_effects=False)
        session.set_policy(new_policy)
        assert session.should_execute_tools() is False


# ---------------------------------------------------------------------------
# Module-level registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def setup_method(self) -> None:
        md.reset_registry_for_testing()

    def teardown_method(self) -> None:
        md.reset_registry_for_testing()

    def test_get_creates_per_session(self) -> None:
        a = md.get_mode_session("s1")
        b = md.get_mode_session("s2")
        assert a is not b

    def test_get_returns_same_for_same_id(self) -> None:
        a = md.get_mode_session("s1")
        b = md.get_mode_session("s1")
        assert a is b

    def test_drop_removes(self) -> None:
        md.get_mode_session("s1")
        assert md.drop_mode_session("s1") is True
        assert md.drop_mode_session("s1") is False

    def test_clear_drops_pending_keeps_mode(self) -> None:
        session = md.get_mode_session("s")
        session.flip(md.Mode.PLAN)
        session.queue_plan("p")
        session.clear()
        assert session.pending_count() == 0
        # Mode is preserved (clear only nukes pending + history).
        assert session.mode is md.Mode.PLAN
