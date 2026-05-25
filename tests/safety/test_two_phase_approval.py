"""Tests for the T2 two-phase exec approval registry."""

from __future__ import annotations

import threading
import time

import pytest

from ultron.safety.two_phase_approval import (
    ApprovalDecision,
    ApprovalHandle,
    ApprovalOutcome,
    ApprovalRegistry,
    ApprovalRequest,
    DEFAULT_APPROVAL_TIMEOUT_SECONDS,
    MAX_APPROVAL_TIMEOUT_SECONDS,
    get_approval_registry,
    reset_approval_registry_for_testing,
    set_approval_registry,
)


@pytest.fixture(autouse=True)
def _isolate_singleton() -> None:
    reset_approval_registry_for_testing()
    yield
    reset_approval_registry_for_testing()


@pytest.fixture
def registry() -> ApprovalRegistry:
    return ApprovalRegistry(default_timeout_seconds=2.0)


# ----------------------------------------------------------------------
# register


def test_register_returns_handle_with_unique_id(registry: ApprovalRegistry) -> None:
    handle_a = registry.register(ApprovalRequest(kind="voice"))
    handle_b = registry.register(ApprovalRequest(kind="voice"))
    assert handle_a.approval_id != handle_b.approval_id


def test_register_sets_expires_in_future(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="voice", timeout_seconds=5.0))
    assert handle.expires_at_seconds > time.monotonic()


def test_register_echoes_request_in_handle(registry: ApprovalRegistry) -> None:
    request = ApprovalRequest(kind="voice", prompt="Confirm?", actor="orchestrator")
    handle = registry.register(request)
    assert handle.request is request


def test_register_pre_resolver_returns_cached_decision() -> None:
    def resolver(req: ApprovalRequest) -> ApprovalDecision:
        return ApprovalDecision(outcome=ApprovalOutcome.ALLOW, reason="auto-allow")

    registry = ApprovalRegistry(pre_resolver=resolver)
    handle = registry.register(ApprovalRequest(kind="x"))
    assert handle.pre_resolved is not None
    assert handle.pre_resolved.allowed


def test_register_pre_resolver_returning_none_is_unresolved() -> None:
    def resolver(_: ApprovalRequest):
        return None

    registry = ApprovalRegistry(pre_resolver=resolver)
    handle = registry.register(ApprovalRequest(kind="x"))
    assert handle.pre_resolved is None


def test_register_pre_resolver_exception_treated_as_no_cache() -> None:
    def resolver(_: ApprovalRequest):
        raise RuntimeError("policy bug")

    registry = ApprovalRegistry(pre_resolver=resolver)
    handle = registry.register(ApprovalRequest(kind="x"))
    assert handle.pre_resolved is None


# ----------------------------------------------------------------------
# record_decision + wait_for_decision


def test_wait_returns_decision_when_recorded_first(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="x", timeout_seconds=10))
    registry.record_allow(handle.approval_id, decider="auto_test")
    decision = registry.wait_for_decision(handle.approval_id)
    assert decision.allowed
    assert decision.decider == "auto_test"


def test_wait_returns_expired_after_timeout() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=0.05)
    handle = registry.register(ApprovalRequest(kind="x"))
    decision = registry.wait_for_decision(handle.approval_id)
    assert decision.outcome == ApprovalOutcome.EXPIRED


def test_wait_returns_not_found_for_unknown_id(registry: ApprovalRegistry) -> None:
    decision = registry.wait_for_decision("missing-id")
    assert decision.outcome == ApprovalOutcome.NOT_FOUND


def test_wait_wakes_when_decision_recorded_during_wait() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=5.0)
    handle = registry.register(ApprovalRequest(kind="x"))
    result: list = []

    def waiter():
        result.append(registry.wait_for_decision(handle.approval_id))

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)
    registry.record_allow(handle.approval_id)
    t.join(timeout=2.0)
    assert result and result[0].allowed


def test_record_decision_idempotent_first_wins(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="x", timeout_seconds=5))
    assert registry.record_allow(handle.approval_id, decider="first") is True
    # Second record is ignored.
    assert registry.record_deny(handle.approval_id, decider="second") is False
    decision = registry.wait_for_decision(handle.approval_id)
    assert decision.allowed
    assert decision.decider == "first"


def test_record_decision_unknown_id_returns_false(registry: ApprovalRegistry) -> None:
    assert registry.record_allow("nope") is False


def test_record_deny_path(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="x", timeout_seconds=5))
    registry.record_deny(handle.approval_id, reason="user declined", decider="voice")
    decision = registry.wait_for_decision(handle.approval_id)
    assert decision.outcome == ApprovalOutcome.DENY
    assert decision.reason == "user declined"


# ----------------------------------------------------------------------
# peek


def test_peek_returns_pending_before_decision(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="x", timeout_seconds=10))
    assert registry.peek(handle.approval_id) == ApprovalOutcome.PENDING


def test_peek_returns_allow_after_decision(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="x", timeout_seconds=10))
    registry.record_allow(handle.approval_id)
    assert registry.peek(handle.approval_id) == ApprovalOutcome.ALLOW


def test_peek_returns_expired_after_deadline() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=0.05)
    handle = registry.register(ApprovalRequest(kind="x"))
    time.sleep(0.1)
    assert registry.peek(handle.approval_id) == ApprovalOutcome.EXPIRED


def test_peek_returns_not_found_for_unknown(registry: ApprovalRegistry) -> None:
    assert registry.peek("missing") == ApprovalOutcome.NOT_FOUND


# ----------------------------------------------------------------------
# list_pending


def test_list_pending_returns_pending_only(registry: ApprovalRegistry) -> None:
    a = registry.register(ApprovalRequest(kind="x", scope_key="s1", timeout_seconds=5))
    b = registry.register(ApprovalRequest(kind="x", scope_key="s2", timeout_seconds=5))
    registry.record_allow(a.approval_id)
    pending = registry.list_pending()
    assert {p.approval_id for p in pending} == {b.approval_id}


def test_list_pending_filters_by_scope(registry: ApprovalRegistry) -> None:
    registry.register(ApprovalRequest(kind="x", scope_key="alpha", timeout_seconds=5))
    registry.register(ApprovalRequest(kind="x", scope_key="beta", timeout_seconds=5))
    out = registry.list_pending(scope_key="alpha")
    assert all(h.request.scope_key == "alpha" for h in out)


def test_list_pending_excludes_expired() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=0.05)
    registry.register(ApprovalRequest(kind="x"))
    time.sleep(0.1)
    assert registry.list_pending() == ()


# ----------------------------------------------------------------------
# cancel + clear


def test_cancel_records_deny(registry: ApprovalRegistry) -> None:
    handle = registry.register(ApprovalRequest(kind="x", timeout_seconds=10))
    assert registry.cancel(handle.approval_id, reason="user pressed escape") is True
    decision = registry.wait_for_decision(handle.approval_id)
    assert decision.outcome == ApprovalOutcome.DENY


def test_clear_wakes_waiters() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=10)
    handle = registry.register(ApprovalRequest(kind="x"))
    result: list = []

    def waiter():
        result.append(registry.wait_for_decision(handle.approval_id))

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)
    registry.clear()
    t.join(timeout=2.0)
    assert result and result[0].outcome == ApprovalOutcome.EXPIRED


# ----------------------------------------------------------------------
# request_decision (composite)


def test_request_decision_returns_pre_resolved_without_wait() -> None:
    def resolver(_: ApprovalRequest):
        return ApprovalDecision(outcome=ApprovalOutcome.ALLOW)

    registry = ApprovalRegistry(pre_resolver=resolver, default_timeout_seconds=10)
    decision = registry.request_decision(ApprovalRequest(kind="x"))
    assert decision.allowed


def test_request_decision_waits_when_no_pre_resolved() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=0.05)
    decision = registry.request_decision(ApprovalRequest(kind="x"))
    # Will time out since no record_allow is called.
    assert decision.outcome == ApprovalOutcome.EXPIRED


# ----------------------------------------------------------------------
# Constants


def test_default_timeout_is_60_seconds() -> None:
    assert DEFAULT_APPROVAL_TIMEOUT_SECONDS == 60.0


def test_max_timeout_clamps_to_ten_minutes() -> None:
    assert MAX_APPROVAL_TIMEOUT_SECONDS == 600.0


def test_timeout_clamp_for_huge_value() -> None:
    registry = ApprovalRegistry(default_timeout_seconds=99999)
    handle = registry.register(ApprovalRequest(kind="x"))
    # Expires within MAX_APPROVAL_TIMEOUT_SECONDS of now.
    assert handle.expires_at_seconds - time.monotonic() <= MAX_APPROVAL_TIMEOUT_SECONDS + 1


# ----------------------------------------------------------------------
# Singleton


def test_get_approval_registry_singleton() -> None:
    a = get_approval_registry()
    b = get_approval_registry()
    assert a is b


def test_set_approval_registry_replaces() -> None:
    custom = ApprovalRegistry()
    set_approval_registry(custom)
    assert get_approval_registry() is custom
