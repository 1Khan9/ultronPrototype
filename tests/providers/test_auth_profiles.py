"""Tests for the T6 provider auth-profile store + failover taxonomy + rotation."""

from __future__ import annotations

import pytest

from kenning.providers.auth_profiles import (
    AuthProfile,
    AuthProfileState,
    AuthProfileStore,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MAX_TRANSIENT_RETRIES,
    MAX_FAILURE_COUNT,
    get_profile_store,
    reset_profile_store_for_testing,
    set_profile_store,
)
from kenning.providers.failover_policy import (
    FAILOVER_PROBE_REASONS,
    FAILOVER_TRANSIENT_SLOT_REASONS,
    FailoverReason,
    should_allow_cooldown_probe,
    should_use_transient_cooldown_slot,
)
from kenning.providers.rotation import (
    DEFAULT_TRANSIENT_DELAY_SECONDS,
    RotationOutcome,
    classify_provider_error,
    execute_with_rotation,
)


@pytest.fixture(autouse=True)
def _isolate_singleton() -> None:
    reset_profile_store_for_testing()
    yield
    reset_profile_store_for_testing()


# ----------------------------------------------------------------------
# Failover taxonomy


def test_taxonomy_has_13_reasons() -> None:
    assert len(FailoverReason) == 13


def test_rate_limit_is_probe_and_transient() -> None:
    assert should_allow_cooldown_probe(FailoverReason.RATE_LIMIT) is True
    assert should_use_transient_cooldown_slot(FailoverReason.RATE_LIMIT) is True


def test_billing_is_probe_but_not_transient() -> None:
    assert should_allow_cooldown_probe(FailoverReason.BILLING) is True
    assert should_use_transient_cooldown_slot(FailoverReason.BILLING) is False


def test_auth_is_neither() -> None:
    assert should_allow_cooldown_probe(FailoverReason.AUTH) is False
    assert should_use_transient_cooldown_slot(FailoverReason.AUTH) is False


def test_session_expired_is_neither() -> None:
    assert should_allow_cooldown_probe(FailoverReason.SESSION_EXPIRED) is False


def test_model_not_found_is_neither() -> None:
    assert should_allow_cooldown_probe(FailoverReason.MODEL_NOT_FOUND) is False


def test_format_is_neither() -> None:
    assert should_allow_cooldown_probe(FailoverReason.FORMAT) is False


def test_unknown_is_transient_friendly() -> None:
    assert should_allow_cooldown_probe(FailoverReason.UNKNOWN) is True
    assert should_use_transient_cooldown_slot(FailoverReason.UNKNOWN) is True


def test_probe_set_size_matches_doc() -> None:
    # 8 transient-friendly reasons.
    assert len(FAILOVER_PROBE_REASONS) == 8


def test_transient_slot_set_size_matches_doc() -> None:
    # 7 reasons (billing excluded).
    assert len(FAILOVER_TRANSIENT_SLOT_REASONS) == 7


# ----------------------------------------------------------------------
# classify_provider_error


def test_classify_rate_limit_text() -> None:
    err = RuntimeError("HTTP 429 too many requests")
    assert classify_provider_error(err) == FailoverReason.RATE_LIMIT


def test_classify_timeout_text() -> None:
    err = TimeoutError("operation timed out")
    assert classify_provider_error(err) == FailoverReason.TIMEOUT


def test_classify_auth_text() -> None:
    err = RuntimeError("HTTP 401 unauthorized")
    assert classify_provider_error(err) == FailoverReason.AUTH


def test_classify_billing_text() -> None:
    err = RuntimeError("billing: quota exceeded")
    assert classify_provider_error(err) == FailoverReason.BILLING


def test_classify_overloaded_text() -> None:
    err = RuntimeError("service overloaded; retry")
    assert classify_provider_error(err) == FailoverReason.OVERLOADED


def test_classify_model_not_found() -> None:
    err = RuntimeError("model 'gpt-99' not found")
    assert classify_provider_error(err) == FailoverReason.MODEL_NOT_FOUND


def test_classify_empty_response() -> None:
    err = RuntimeError("got an empty response from upstream")
    assert classify_provider_error(err) == FailoverReason.EMPTY_RESPONSE


def test_classify_unknown_text_falls_through_to_unclassified() -> None:
    err = RuntimeError("something else weird happened")
    assert classify_provider_error(err) == FailoverReason.UNCLASSIFIED


def test_classify_no_text_returns_no_error_details() -> None:
    err = RuntimeError("error")
    assert classify_provider_error(err) == FailoverReason.NO_ERROR_DETAILS


# ----------------------------------------------------------------------
# AuthProfileStore


def test_register_and_get() -> None:
    store = AuthProfileStore()
    profile = AuthProfile(profile_id="p1", provider="brave")
    store.register(profile)
    assert store.get("p1") is profile


def test_register_empty_profile_id_rejected() -> None:
    store = AuthProfileStore()
    with pytest.raises(ValueError):
        store.register(AuthProfile(profile_id="", provider="brave"))


def test_register_empty_provider_rejected() -> None:
    store = AuthProfileStore()
    with pytest.raises(ValueError):
        store.register(AuthProfile(profile_id="p1", provider=""))


def test_list_for_provider_sorts_by_priority() -> None:
    store = AuthProfileStore()
    store.register(AuthProfile(profile_id="b", provider="brave", priority=2))
    store.register(AuthProfile(profile_id="a", provider="brave", priority=1))
    out = store.list_for_provider("brave")
    assert [p.profile_id for p in out] == ["a", "b"]


def test_list_eligible_excludes_disabled() -> None:
    store = AuthProfileStore()
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    store.record_failure("p1", FailoverReason.AUTH)
    # AUTH disables immediately.
    assert store.list_eligible("brave") == ()


def test_list_eligible_excludes_cooling_down_within_window() -> None:
    clock_value = {"t": 100.0}

    def clock() -> float:
        return clock_value["t"]

    store = AuthProfileStore(clock=clock, default_cooldown_seconds=60)
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    store.record_failure("p1", FailoverReason.RATE_LIMIT)
    assert store.list_eligible("brave") == ()


def test_list_eligible_promotes_cooled_down_back_to_ready() -> None:
    clock_value = {"t": 100.0}

    def clock() -> float:
        return clock_value["t"]

    store = AuthProfileStore(clock=clock, default_cooldown_seconds=60)
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    store.record_failure("p1", FailoverReason.RATE_LIMIT)
    clock_value["t"] = 200.0  # past cooldown
    out = store.list_eligible("brave")
    assert len(out) == 1
    assert out[0].state == AuthProfileState.READY


def test_record_success_clears_failure_state() -> None:
    store = AuthProfileStore()
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    store.record_failure("p1", FailoverReason.RATE_LIMIT)
    store.record_success("p1")
    profile = store.get("p1")
    assert profile.state == AuthProfileState.READY
    assert profile.failure_count == 0
    assert profile.last_failure_reason is None
    assert profile.transient_slots_remaining == DEFAULT_MAX_TRANSIENT_RETRIES


def test_record_failure_disables_after_max_count() -> None:
    store = AuthProfileStore(max_failure_count=3)
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    for _ in range(2):
        store.record_failure("p1", FailoverReason.RATE_LIMIT)
    assert store.get("p1").state != AuthProfileState.DISABLED
    store.record_failure("p1", FailoverReason.RATE_LIMIT)
    assert store.get("p1").state == AuthProfileState.DISABLED


def test_record_failure_permanent_disables_immediately() -> None:
    store = AuthProfileStore(max_failure_count=10)
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    state = store.record_failure("p1", FailoverReason.AUTH_PERMANENT)
    assert state == AuthProfileState.DISABLED


def test_consume_transient_slot_decrements() -> None:
    store = AuthProfileStore(default_transient_slots=3)
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    remaining = store.consume_transient_slot("p1")
    assert remaining == 2


def test_consume_transient_slot_unknown_returns_zero() -> None:
    store = AuthProfileStore()
    assert store.consume_transient_slot("missing") == 0


def test_reset_profile_returns_to_ready() -> None:
    store = AuthProfileStore()
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    store.record_failure("p1", FailoverReason.AUTH)
    assert store.reset_profile("p1") is True
    profile = store.get("p1")
    assert profile.state == AuthProfileState.READY


def test_reset_profile_unknown_returns_false() -> None:
    store = AuthProfileStore()
    assert store.reset_profile("missing") is False


# ----------------------------------------------------------------------
# Singleton


def test_get_profile_store_singleton() -> None:
    a = get_profile_store()
    b = get_profile_store()
    assert a is b


def test_set_profile_store_replaces() -> None:
    custom = AuthProfileStore()
    set_profile_store(custom)
    assert get_profile_store() is custom


# ----------------------------------------------------------------------
# execute_with_rotation


def test_execute_with_rotation_success_first_profile() -> None:
    store = AuthProfileStore()
    store.register(AuthProfile(profile_id="p1", provider="brave", priority=1))
    store.register(AuthProfile(profile_id="p2", provider="brave", priority=2))
    calls = []

    def op(profile: AuthProfile) -> str:
        calls.append(profile.profile_id)
        return f"hi from {profile.profile_id}"

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        delay_fn=lambda _: None,
    )
    assert result.outcome == RotationOutcome.SUCCESS
    assert result.value == "hi from p1"
    assert calls == ["p1"]


def test_execute_with_rotation_rotates_on_rate_limit() -> None:
    store = AuthProfileStore(default_cooldown_seconds=60)
    store.register(AuthProfile(profile_id="p1", provider="brave", priority=1))
    store.register(AuthProfile(profile_id="p2", provider="brave", priority=2))

    def op(profile: AuthProfile) -> str:
        if profile.profile_id == "p1":
            raise RuntimeError("HTTP 429 rate limit hit")
        return "ok from p2"

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        delay_fn=lambda _: None,
    )
    assert result.succeeded
    assert result.value == "ok from p2"


def test_execute_with_rotation_transient_retry_same_profile() -> None:
    store = AuthProfileStore(default_transient_slots=3)
    store.register(AuthProfile(profile_id="p1", provider="brave"))
    state = {"attempts": 0}

    def op(profile: AuthProfile) -> str:
        state["attempts"] += 1
        if state["attempts"] < 3:
            raise TimeoutError("timed out")
        return "ok"

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        delay_fn=lambda _: None,
    )
    assert result.succeeded
    assert state["attempts"] == 3


def test_execute_with_rotation_exhausts_when_all_fail() -> None:
    store = AuthProfileStore(default_transient_slots=1)
    store.register(AuthProfile(profile_id="p1", provider="brave", priority=1))
    store.register(AuthProfile(profile_id="p2", provider="brave", priority=2))

    def op(profile: AuthProfile) -> str:
        raise TimeoutError("operation timed out")

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        delay_fn=lambda _: None,
    )
    assert result.outcome == RotationOutcome.EXHAUSTED
    assert result.last_reason == FailoverReason.TIMEOUT


def test_execute_with_rotation_disabled_all_when_no_profiles() -> None:
    store = AuthProfileStore()
    result = execute_with_rotation(
        provider="missing",
        operation=lambda _: "x",
        store=store,
        delay_fn=lambda _: None,
    )
    assert result.outcome == RotationOutcome.DISABLED_ALL


def test_execute_with_rotation_records_attempts() -> None:
    store = AuthProfileStore(default_transient_slots=2)
    store.register(AuthProfile(profile_id="p1", provider="brave"))

    def op(profile: AuthProfile) -> str:
        return "ok"

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        delay_fn=lambda _: None,
    )
    assert len(result.attempts) == 1
    assert result.attempts[0].succeeded


def test_execute_with_rotation_billing_does_not_consume_transient_slot() -> None:
    store = AuthProfileStore(default_transient_slots=2)
    store.register(AuthProfile(profile_id="p1", provider="brave", priority=1))
    store.register(AuthProfile(profile_id="p2", provider="brave", priority=2))

    def op(profile: AuthProfile) -> str:
        if profile.profile_id == "p1":
            raise RuntimeError("billing: quota exceeded")
        return "p2 ok"

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        delay_fn=lambda _: None,
    )
    # billing rotates to next profile (no transient retry consumed).
    assert result.succeeded
    # p1 transient slot should be unchanged.
    assert store.get("p1").transient_slots_remaining == DEFAULT_MAX_TRANSIENT_RETRIES


def test_execute_with_rotation_custom_classifier() -> None:
    store = AuthProfileStore()
    store.register(AuthProfile(profile_id="p1", provider="brave"))

    def my_classifier(error: BaseException) -> FailoverReason:
        return FailoverReason.RATE_LIMIT  # force rate-limit interpretation

    def op(profile: AuthProfile) -> str:
        raise RuntimeError("something")

    result = execute_with_rotation(
        provider="brave",
        operation=op,
        store=store,
        classifier=my_classifier,
        delay_fn=lambda _: None,
    )
    assert result.last_reason == FailoverReason.RATE_LIMIT
