"""Tests for the T15 activation planner."""

from __future__ import annotations

import pytest

from kenning.skills.activation import (
    ActivationCandidate,
    ActivationContext,
    ActivationResult,
    ActivationTriggers,
    auto_enable_for_configured_providers,
    evaluate_activation,
    make_triggers,
    plan_activation,
)


# ----------------------------------------------------------------------
# make_triggers + ActivationTriggers


def test_make_triggers_strips_empty_strings() -> None:
    triggers = make_triggers(on_commands=["", "search", " ", "rag"])
    assert triggers.on_commands == ("search", "rag")


def test_make_triggers_dedupes() -> None:
    triggers = make_triggers(on_capabilities=["voice", "voice", "coding"])
    assert triggers.on_capabilities == ("voice", "coding")


def test_triggers_has_any_false_when_all_empty() -> None:
    triggers = ActivationTriggers()
    assert triggers.has_any is False


def test_triggers_has_any_true_for_on_startup() -> None:
    triggers = ActivationTriggers(on_startup=True)
    assert triggers.has_any is True


def test_triggers_has_any_true_for_non_empty_axis() -> None:
    triggers = make_triggers(on_capabilities=["voice"])
    assert triggers.has_any is True


# ----------------------------------------------------------------------
# evaluate_activation


def test_evaluate_no_triggers_no_activation() -> None:
    triggers = ActivationTriggers()
    context = ActivationContext(is_startup=True)
    result = evaluate_activation(triggers, context)
    assert result.activated is False


def test_evaluate_on_startup_match() -> None:
    triggers = make_triggers(on_startup=True)
    context = ActivationContext(is_startup=True)
    result = evaluate_activation(triggers, context)
    assert result.activated is True
    assert "on_startup" in result.matched_axes


def test_evaluate_on_startup_not_at_startup_no_match() -> None:
    triggers = make_triggers(on_startup=True)
    context = ActivationContext(is_startup=False)
    result = evaluate_activation(triggers, context)
    assert result.activated is False


def test_evaluate_capability_intersection() -> None:
    triggers = make_triggers(on_capabilities=["voice", "coding"])
    context = ActivationContext(capabilities=frozenset({"voice"}))
    result = evaluate_activation(triggers, context)
    assert result.activated is True
    assert result.matched_values["on_capabilities"] == ("voice",)


def test_evaluate_command_intersection() -> None:
    triggers = make_triggers(on_commands=["search", "rag"])
    context = ActivationContext(commands=frozenset({"search"}))
    result = evaluate_activation(triggers, context)
    assert result.activated is True


def test_evaluate_no_intersection_no_match() -> None:
    triggers = make_triggers(on_capabilities=["desktop"])
    context = ActivationContext(capabilities=frozenset({"voice"}))
    result = evaluate_activation(triggers, context)
    assert result.activated is False


def test_evaluate_multiple_axes_match() -> None:
    triggers = make_triggers(
        on_startup=True,
        on_capabilities=["voice"],
    )
    context = ActivationContext(
        is_startup=True,
        capabilities=frozenset({"voice"}),
    )
    result = evaluate_activation(triggers, context)
    assert "on_startup" in result.matched_axes
    assert "on_capabilities" in result.matched_axes


def test_evaluate_provider_intersection() -> None:
    triggers = make_triggers(on_providers=["brave", "searxng"])
    context = ActivationContext(providers=frozenset({"brave"}))
    result = evaluate_activation(triggers, context)
    assert result.activated is True


def test_evaluate_routes_intersection() -> None:
    triggers = make_triggers(on_routes=["WEB_SEARCH"])
    context = ActivationContext(routes=frozenset({"WEB_SEARCH", "CONVERSATIONAL"}))
    result = evaluate_activation(triggers, context)
    assert result.activated is True


def test_evaluate_config_paths_intersection() -> None:
    triggers = make_triggers(on_config_paths=["web_search.enabled"])
    context = ActivationContext(config_paths_set=frozenset({"web_search.enabled"}))
    result = evaluate_activation(triggers, context)
    assert result.activated is True


# ----------------------------------------------------------------------
# plan_activation


def test_plan_activation_classifies_all_candidates() -> None:
    candidates = [
        ActivationCandidate(identifier="a", triggers=make_triggers(on_startup=True)),
        ActivationCandidate(identifier="b", triggers=make_triggers(on_capabilities=["voice"])),
        ActivationCandidate(identifier="c", triggers=make_triggers(on_capabilities=["desktop"])),
    ]
    context = ActivationContext(is_startup=True, capabilities=frozenset({"voice"}))
    plan = plan_activation(candidates, context)
    assert set(plan.activated) == {"a", "b"}
    assert plan.skipped == ("c",)


def test_plan_activation_skips_no_trigger_manifests() -> None:
    candidates = [
        ActivationCandidate(identifier="empty", triggers=ActivationTriggers()),
    ]
    context = ActivationContext(is_startup=True)
    plan = plan_activation(candidates, context)
    assert plan.activated == ()
    assert plan.skipped == ("empty",)


def test_plan_activation_preserves_order_in_activated() -> None:
    candidates = [
        ActivationCandidate(identifier=f"c{i}", triggers=make_triggers(on_startup=True))
        for i in range(5)
    ]
    context = ActivationContext(is_startup=True)
    plan = plan_activation(candidates, context)
    assert plan.activated == ("c0", "c1", "c2", "c3", "c4")


def test_plan_activation_empty_input() -> None:
    plan = plan_activation([], ActivationContext())
    assert plan.activated == ()
    assert plan.skipped == ()


# ----------------------------------------------------------------------
# auto_enable_for_configured_providers


def test_auto_enable_for_configured_providers_matches() -> None:
    candidates = [
        ActivationCandidate(identifier="brave", triggers=make_triggers(on_providers=["brave"])),
        ActivationCandidate(identifier="jina", triggers=make_triggers(on_providers=["jina"])),
    ]
    configured = frozenset({"brave"})
    out = auto_enable_for_configured_providers(candidates, configured)
    assert out == ("brave",)


def test_auto_enable_skips_candidates_without_on_providers() -> None:
    candidates = [
        ActivationCandidate(identifier="x", triggers=make_triggers(on_capabilities=["voice"])),
    ]
    out = auto_enable_for_configured_providers(candidates, frozenset({"brave"}))
    assert out == ()
