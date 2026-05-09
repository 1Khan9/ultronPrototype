"""4B optimization plan Item 6 — self-consistency wired into web_gating preflight.

The decomposer site landed in Item 6's first commit; this is the
second site from the original plan ("pre-flight uncertainty when
initial confidence is borderline"). Mocked LLM throughout — no GPU.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ultron.web_search.gating import GateDecision, classify_by_preflight


@pytest.fixture
def cfg_mock():
    cfg = MagicMock()
    cfg.llm.self_consistency.enabled = False
    cfg.llm.self_consistency.disabled_sites = []
    cfg.llm.self_consistency.n = 3
    cfg.llm.self_consistency.temperature = 0.8
    return cfg


def _llm_returning(*responses):
    """Build a mock LLMEngine whose ``_llm.create_chat_completion`` returns
    each response from ``responses`` in turn (cycling)."""
    llm = MagicMock()
    iterator = iter(responses) if len(responses) > 1 else None
    if iterator is None:
        llm._llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": responses[0]}}],
        }
    else:
        responses_list = list(responses)
        idx = {"i": 0}

        def _next(*a, **kw):
            r = responses_list[idx["i"] % len(responses_list)]
            idx["i"] += 1
            return {"choices": [{"message": {"content": r}}]}

        llm._llm.create_chat_completion.side_effect = _next
    return llm


# ---------------------------------------------------------------------------
# Default OFF — single greedy call with temperature 0.0 (back-compat)
# ---------------------------------------------------------------------------


def test_preflight_default_uses_single_call_temp_zero(cfg_mock) -> None:
    llm = _llm_returning(
        '{"needs_search": true, "knowledge_confidence": "low", '
        '"search_queries": ["q1"], "reason": "current data needed"}'
    )
    with patch("ultron.config.get_config", return_value=cfg_mock):
        verdict = classify_by_preflight(llm, "what's the latest x?")
    # Exactly one LLM call
    assert llm._llm.create_chat_completion.call_count == 1
    # Temperature was 0.0
    args = llm._llm.create_chat_completion.call_args
    assert args.kwargs["temperature"] == 0.0
    assert verdict.decision == GateDecision.SEARCH


def test_preflight_default_no_search_back_compat(cfg_mock) -> None:
    llm = _llm_returning(
        '{"needs_search": false, "knowledge_confidence": "high", '
        '"search_queries": [], "reason": "in weights"}'
    )
    with patch("ultron.config.get_config", return_value=cfg_mock):
        verdict = classify_by_preflight(llm, "boiling point of water?")
    assert verdict.decision == GateDecision.NO_SEARCH
    assert llm._llm.create_chat_completion.call_count == 1


# ---------------------------------------------------------------------------
# Self-consistency ON — N samples, majority wins
# ---------------------------------------------------------------------------


def test_preflight_self_consistency_calls_n_times(cfg_mock) -> None:
    cfg_mock.llm.self_consistency.enabled = True
    cfg_mock.llm.self_consistency.n = 3
    llm = _llm_returning(
        '{"needs_search": true, "knowledge_confidence": "low", '
        '"search_queries": ["q1"], "reason": "r"}'
    )
    with patch("ultron.config.get_config", return_value=cfg_mock):
        verdict = classify_by_preflight(llm, "u")
    assert llm._llm.create_chat_completion.call_count == 3
    assert verdict.decision == GateDecision.SEARCH


def test_preflight_self_consistency_uses_configured_temperature(cfg_mock) -> None:
    """When self-consistency is on, calls must use the configured (non-
    zero) temperature so samples are diverse — temperature 0.0 would
    defeat the point."""
    cfg_mock.llm.self_consistency.enabled = True
    cfg_mock.llm.self_consistency.temperature = 0.85
    llm = _llm_returning(
        '{"needs_search": false, "knowledge_confidence": "high", '
        '"search_queries": [], "reason": "r"}'
    )
    with patch("ultron.config.get_config", return_value=cfg_mock):
        classify_by_preflight(llm, "u")
    # All three calls should use temperature 0.85
    for call in llm._llm.create_chat_completion.call_args_list:
        assert call.kwargs["temperature"] == 0.85


def test_preflight_self_consistency_majority_wins(cfg_mock) -> None:
    """Two SEARCH samples + one NO_SEARCH ⇒ SEARCH wins."""
    cfg_mock.llm.self_consistency.enabled = True
    cfg_mock.llm.self_consistency.n = 3
    search_resp = (
        '{"needs_search": true, "knowledge_confidence": "low", '
        '"search_queries": ["q1"], "reason": "r"}'
    )
    no_search_resp = (
        '{"needs_search": false, "knowledge_confidence": "high", '
        '"search_queries": [], "reason": "r"}'
    )
    llm = _llm_returning(search_resp, search_resp, no_search_resp)
    with patch("ultron.config.get_config", return_value=cfg_mock):
        verdict = classify_by_preflight(llm, "u")
    assert verdict.decision == GateDecision.SEARCH


def test_preflight_self_consistency_per_site_disabled(cfg_mock) -> None:
    """Even with global flag on, ``web_gating_preflight`` in the
    disabled_sites list bypasses self-consistency."""
    cfg_mock.llm.self_consistency.enabled = True
    cfg_mock.llm.self_consistency.disabled_sites = ["web_gating_preflight"]
    llm = _llm_returning(
        '{"needs_search": false, "knowledge_confidence": "high", '
        '"search_queries": [], "reason": "r"}'
    )
    with patch("ultron.config.get_config", return_value=cfg_mock):
        classify_by_preflight(llm, "u")
    # Single call (back-compat) and temp 0.0
    assert llm._llm.create_chat_completion.call_count == 1
    args = llm._llm.create_chat_completion.call_args
    assert args.kwargs["temperature"] == 0.0


def test_preflight_self_consistency_unparseable_falls_back(cfg_mock) -> None:
    """All samples unparseable ⇒ NO_SEARCH default (the safer side)."""
    cfg_mock.llm.self_consistency.enabled = True
    llm = _llm_returning("garbage")
    with patch("ultron.config.get_config", return_value=cfg_mock):
        verdict = classify_by_preflight(llm, "u")
    assert verdict.decision == GateDecision.NO_SEARCH


def test_preflight_llm_exception_returns_no_search(cfg_mock) -> None:
    """LLM crash ⇒ default NO_SEARCH; never raises out of the gate."""
    llm = MagicMock()
    llm._llm.create_chat_completion.side_effect = RuntimeError("boom")
    with patch("ultron.config.get_config", return_value=cfg_mock):
        verdict = classify_by_preflight(llm, "u")
    assert verdict.decision == GateDecision.NO_SEARCH
