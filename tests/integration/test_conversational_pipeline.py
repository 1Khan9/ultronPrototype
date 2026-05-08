"""Integration test category 1 — conversational queries.

These utterances should classify as CONVERSATIONAL and pass through
the controller (return None) so the orchestrator's normal LLM/TTS path
handles them.

We don't load the LLM here — the routing layer is what's under test.
LLM-driven behavior on these prompts is covered in
:mod:`scripts.measure_baseline_extended` (per-query latency + content)
and the existing voice-path baseline runs.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import dispatch_utterance


# ---------------------------------------------------------------------------
# 20 representative conversational utterances per the spec
# ---------------------------------------------------------------------------


_CONVERSATIONAL = [
    # Greetings / pleasantries
    "good morning",
    "hello",
    "hey ultron",
    "thanks",
    "good night",
    # Quick factual
    "what's two plus two",
    "what's the boiling point of water",
    "what time is it",
    # Personal context
    "what's my main project",
    "do I remember telling you about the prototype",
    # Multi-turn pieces
    "what did we talk about yesterday",
    "go on",
    "actually never mind",
    # Refusals territory
    "tell me a joke",
    "explain quantum entanglement",
    # Long-response asks
    "explain how photosynthesis works",
    "walk me through how a transistor works",
    # Affect
    "I'm tired",
    "what do you think about meditation",
    # Continuation
    "and what about the mariana trench",
]


@pytest.mark.parametrize("utt", _CONVERSATIONAL)
def test_conversational_utterance_routes_through(
    cap_stack, routing_log, read_routing, utt,
):
    """All these classify as CONVERSATIONAL; controller returns None;
    routing log records a passthrough entry."""
    response = dispatch_utterance(cap_stack, utt)
    assert response is None, (
        f"expected None for {utt!r}, got: {response}"
    )
    rec = read_routing()[-1]
    assert rec["intent"] == "conversational", (
        f"got {rec['intent']} for {utt!r}; reason={rec['reason']}"
    )
    assert rec["outcome"] == "passthrough"
    assert rec["handler"] == "voice.respond"


def test_conversational_does_not_record_stub(cap_stack, routing_log, read_routing):
    """Conversational dispatch never produces a stub-shaped record — only
    automation kinds do that."""
    dispatch_utterance(cap_stack, "good morning")
    rec = read_routing()[-1]
    assert rec.get("stub_reason") is None
