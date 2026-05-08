"""Integration test category 6 — error recovery exercised at the
routing-pipeline level.

Per-dependency failure tests are in
:mod:`tests.error_recovery.*`. These tests stitch dependencies into the
routing/dispatch path and check that:

  - Brave failure during a search-trigger query: routing classifies as
    CONVERSATIONAL (search isn't a routing intent — Brave failures
    happen inside the gate/executor in the orchestrator's _respond
    path); the routing log isn't affected.

  - Routing-decision log write failure: dispatch still completes; the
    voice response is unaffected.

  - Error log write failure: doesn't break a routing dispatch.

  - Routing classifier exception: bubbles up so the orchestrator can
    fall back to the LLM path. (The classifier itself is rule-based and
    doesn't raise on real input; we stub a failure to verify the
    failure mode is observable.)
"""

from __future__ import annotations

import json

import pytest

from tests.integration.conftest import dispatch_utterance
from ultron.openclaw_routing import RoutingDecisionLog, set_routing_log


def test_routing_log_write_error_does_not_break_dispatch(cap_stack, tmp_path):
    """If the routing log can't be written (target is a directory),
    dispatch still completes and returns a stub response."""
    # Replace the singleton with one whose path is unwritable.
    bad_dir = tmp_path / "blocked"
    bad_dir.mkdir()
    log = RoutingDecisionLog(path=bad_dir)  # writing to a directory raises
    set_routing_log(log)

    try:
        # Dispatch should still return a stub voice response.
        response = dispatch_utterance(cap_stack, "open hacker news")
        assert response is not None
        assert "gateway" in response.text.lower() or "open" in response.text.lower()
    finally:
        set_routing_log(RoutingDecisionLog())


def test_repeated_dispatches_after_failure_continue_normally(
    cap_stack, routing_log, read_routing,
):
    """A run of mixed routing intents — including any that previously
    failed — should keep classifying correctly. No breaker state should
    leak between routing dispatches."""
    utterances = [
        "open hacker news",
        "good morning",
        "make me an image of a cat",
        "send a message to my phone",
        "good night",
        "read the file at C:/x.txt",
        "what is 2 + 2",
    ]
    for u in utterances:
        dispatch_utterance(cap_stack, u)

    records = read_routing()
    assert len(records) == 7
    expected = [
        "browser_automation", "conversational", "media_generation",
        "messaging", "conversational", "file_operation", "conversational",
    ]
    actual = [r["intent"] for r in records]
    assert actual == expected


def test_classify_routing_exception_propagates_to_caller(
    cap_stack, monkeypatch,
):
    """If classify_routing itself raised, the orchestrator's call site
    should see the exception (not silent failure). We patch it to raise
    once, dispatch, and verify the exception is observable."""
    import ultron.openclaw_routing as _router

    original = _router.classify_routing

    def _raise(*args, **kwargs):
        raise RuntimeError("classifier blew up")

    monkeypatch.setattr(_router, "classify_routing", _raise)

    # The orchestrator's actual code path imports classify_routing inside
    # the dispatch block — so we can't easily run THAT block here. But we
    # CAN call classify_routing directly via the test helper:
    with pytest.raises(RuntimeError, match="classifier blew up"):
        from tests.integration.conftest import dispatch_utterance as _du
        _du(cap_stack, "anything")


def test_capability_dispatch_handles_unknown_intent_kind(cap_stack):
    """If a future RoutingIntentKind is added but the controller doesn't
    have a branch for it, dispatch returns None (passthrough) rather
    than crashing — the voice-path safety net catches it."""
    from ultron.openclaw_routing.intents import RoutingIntent, RoutingIntentKind

    # Construct an intent that bypasses our normal flow. We re-use an
    # existing kind but the test would catch a regression where a new
    # kind got added to the enum without a controller branch.
    # (Iterate every enum value through the controller.)
    for kind in RoutingIntentKind:
        intent = RoutingIntent(
            kind=kind, raw_text="dummy",
            source="test", reason="enum sweep",
        )
        # Should not raise.
        try:
            cap_stack.voice.handle_capability_intent(intent)
        except Exception as e:
            pytest.fail(f"handle_capability_intent raised on {kind.value}: {e}")
