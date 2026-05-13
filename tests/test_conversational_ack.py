"""Tests for the conversational filler-ack source + gate.

Covers the 2026-05-12 filler-ack: masks the perceived gap between
Whisper completing and the LLM's first TTS chunk on the no-search
conversational branch.

Gate semantics:
- Pending coding-task clarification suppresses the ack (avoids
  double-ack on top of the orchestrator's clarification narration).
- Very short utterances suppress the ack (would feel over-eager).
- Empty input suppresses the ack.
- Otherwise the ack fires.

Source semantics:
- Shuffled cycle over the phrase pool (every phrase appears once
  per cycle).
- No immediate repeats.
- Thread-safe (inherited from AcknowledgmentSource).
"""

from __future__ import annotations

import pytest

from ultron.conversational_ack import (
    ConversationalAckSource,
    _CONVERSATIONAL_PHRASES,
    is_conversational_ack_eligible,
)


# ---------------------------------------------------------------------------
# Gate function
# ---------------------------------------------------------------------------


def test_is_conversational_ack_eligible_fires_on_normal_question():
    assert is_conversational_ack_eligible("What is the capital of France?")


def test_is_conversational_ack_eligible_fires_on_multi_word_request():
    assert is_conversational_ack_eligible("Tell me about the planet Mars")


def test_is_conversational_ack_eligible_skips_empty():
    assert is_conversational_ack_eligible("") is False
    assert is_conversational_ack_eligible("   ") is False


def test_is_conversational_ack_eligible_skips_short_chars():
    """An utterance under the min-chars threshold gets no ack.

    The perceived gap on a short reply is small; an ack would
    feel over-eager. 'yes', 'no', 'thanks', 'ok', 'sure' all fall
    under this gate."""
    assert is_conversational_ack_eligible("yes") is False
    assert is_conversational_ack_eligible("no") is False
    assert is_conversational_ack_eligible("thanks") is False
    assert is_conversational_ack_eligible("ok") is False
    assert is_conversational_ack_eligible("sure") is False


def test_is_conversational_ack_eligible_skips_short_words():
    """Utterances that ARE long enough in chars but only 1-3 words
    still get gated (interjection-length)."""
    assert is_conversational_ack_eligible("yeah definitely") is False
    assert is_conversational_ack_eligible("sounds good") is False


def test_is_conversational_ack_eligible_skips_pending_clarification():
    """During a coding-task clarification dialogue, the orchestrator
    has its own narration flow -- the ack would double up."""
    assert is_conversational_ack_eligible(
        "What is the capital of France?",
        has_pending_clarification=True,
    ) is False


def test_is_conversational_ack_eligible_strips_whitespace_for_gate():
    """Whitespace on either side shouldn't accidentally let through
    a short utterance."""
    assert is_conversational_ack_eligible("   yes   ") is False
    assert is_conversational_ack_eligible("   ok ok ok   ") is False


def test_is_conversational_ack_eligible_handles_none_as_empty():
    """None input shouldn't crash -- treat as empty."""
    assert is_conversational_ack_eligible(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ConversationalAckSource
# ---------------------------------------------------------------------------


def test_conversational_ack_source_cycles_without_immediate_repeats():
    """Shuffled-cycle invariant: in any window of pool-size, every
    phrase appears exactly once. The cycle is randomised so we don't
    assert a fixed order, just the no-repeat invariant."""
    pool_size = len(_CONVERSATIONAL_PHRASES)
    source = ConversationalAckSource()
    cycle = [source.next_phrase() for _ in range(pool_size)]
    assert sorted(cycle) == sorted(_CONVERSATIONAL_PHRASES)
    # Second cycle should also cover every phrase exactly once.
    cycle2 = [source.next_phrase() for _ in range(pool_size)]
    assert sorted(cycle2) == sorted(_CONVERSATIONAL_PHRASES)


def test_conversational_ack_source_returns_phrases_from_pool():
    """Every phrase returned must come from the configured pool."""
    source = ConversationalAckSource()
    for _ in range(20):
        assert source.next_phrase() in _CONVERSATIONAL_PHRASES


def test_conversational_ack_source_accepts_custom_pool():
    """Custom phrase pool overrides the default. Useful for tests
    and operator tuning."""
    custom = ["Test phrase A.", "Test phrase B."]
    source = ConversationalAckSource(phrases=custom)
    cycle = {source.next_phrase() for _ in range(20)}
    assert cycle == set(custom)


def test_conversational_ack_source_rejects_empty_pool():
    """An empty pool would deadlock the shuffled-cycle. Catch it
    at construction time."""
    with pytest.raises(ValueError):
        ConversationalAckSource(phrases=[])


# ---------------------------------------------------------------------------
# Phrase pool sanity
# ---------------------------------------------------------------------------


def test_conversational_phrases_pool_is_in_character():
    """Phrases are short thinking-noises, not external-activity
    descriptions (those live in the web-search ack pool). The web-
    search pool's phrases should NOT appear here -- the two pools
    are intentionally distinct in tone."""
    from ultron.web_search.acknowledgments import _PHRASES as web_phrases
    for p in _CONVERSATIONAL_PHRASES:
        assert p not in web_phrases
        # Short: a thinking noise, not a sentence.
        assert len(p) <= 20
        # Period-terminated so the TTS pipeline flushes them as
        # complete sentences (matches the web-ack convention).
        assert p.endswith(".")


def test_conversational_phrases_pool_no_duplicates():
    """No duplicate phrases -- they'd skew the shuffle distribution."""
    assert len(_CONVERSATIONAL_PHRASES) == len(set(_CONVERSATIONAL_PHRASES))


def test_conversational_phrases_pool_non_empty():
    """Empty pool would break the source at construction time."""
    assert len(_CONVERSATIONAL_PHRASES) > 0


# ---------------------------------------------------------------------------
# Orchestrator wiring (uses Orchestrator.__new__ to skip heavy init)
# ---------------------------------------------------------------------------


class _StubCodingVoice:
    """Mimics CapabilityVoiceController.has_pending_clarification()."""
    def __init__(self, pending: bool = False) -> None:
        self._pending = pending

    def has_pending_clarification(self) -> bool:
        return self._pending


def _make_orch_for_ack(*, coding_voice=None, source=None):
    """Build a partially-initialised Orchestrator that exposes only
    what ``_maybe_conversational_ack`` touches."""
    from ultron.pipeline.orchestrator import Orchestrator
    o = Orchestrator.__new__(Orchestrator)
    o.coding_voice = coding_voice
    o.conv_ack_source = source or ConversationalAckSource()
    return o


def test_orchestrator_maybe_ack_returns_phrase_on_normal_query():
    """Plain conversational query with no clarification pending ->
    returns one of the configured phrases."""
    o = _make_orch_for_ack(coding_voice=None)
    phrase = o._maybe_conversational_ack("What is the capital of France?")
    assert phrase is not None
    assert phrase in _CONVERSATIONAL_PHRASES


def test_orchestrator_maybe_ack_returns_none_on_short_utterance():
    o = _make_orch_for_ack(coding_voice=None)
    assert o._maybe_conversational_ack("yes") is None
    assert o._maybe_conversational_ack("ok") is None


def test_orchestrator_maybe_ack_returns_none_during_clarification():
    """has_pending_clarification=True suppresses the ack via the gate."""
    stub = _StubCodingVoice(pending=True)
    o = _make_orch_for_ack(coding_voice=stub)
    assert o._maybe_conversational_ack("What is the capital of France?") is None


def test_orchestrator_maybe_ack_handles_missing_coding_voice():
    """coding_voice=None must not crash -- pending defaults to False
    and the gate decides on the text alone."""
    o = _make_orch_for_ack(coding_voice=None)
    # Long enough utterance -> ack fires.
    phrase = o._maybe_conversational_ack("Tell me about the planet Mars")
    assert phrase is not None


def test_orchestrator_maybe_ack_swallows_clarification_check_exception():
    """If coding_voice.has_pending_clarification raises, treat as
    not-pending and let the ack fire. Fail-open on the perceived-
    latency mask -- we never want a flaky coding subsystem to break
    the voice path."""
    class _Boom:
        def has_pending_clarification(self):
            raise RuntimeError("boom")
    o = _make_orch_for_ack(coding_voice=_Boom())
    phrase = o._maybe_conversational_ack("What's the weather today?")
    assert phrase is not None


def test_orchestrator_maybe_ack_swallows_source_exception():
    """If the ack source fails for any reason, return None so the
    orchestrator falls back to silent (legacy) behaviour."""
    class _BrokenSource:
        def next_phrase(self):
            raise RuntimeError("source crashed")
    o = _make_orch_for_ack(coding_voice=None, source=_BrokenSource())
    assert o._maybe_conversational_ack("What's the weather today?") is None


def test_orchestrator_build_response_stream_prepends_ack_on_no_gate(monkeypatch):
    """When web_gate is None, the conversational fallthrough yields
    an ack token before the LLM stream tokens. End-to-end token-order
    contract: the TTS pipeline must see the ack first so it can start
    speaking before the LLM finishes its first chunk."""
    from ultron.pipeline.orchestrator import Orchestrator

    o = Orchestrator.__new__(Orchestrator)
    o.coding_voice = None
    o.conv_ack_source = ConversationalAckSource()
    o.web_gate = None
    o.web_executor = None

    class _FakeLLM:
        def generate_stream(self, text, **kwargs):
            yield "Hello, "
            yield "Doctor."

    o.llm = _FakeLLM()

    tokens = list(o._build_response_stream("What's the weather today?"))
    assert len(tokens) >= 3  # ack + " " marker + 2 LLM tokens
    # First token must be the ack (with trailing space appended).
    first = tokens[0]
    assert first.rstrip() in _CONVERSATIONAL_PHRASES
    assert first.endswith(" "), "ack should have trailing space for sentence flush"
    # LLM tokens follow.
    assert "Hello, " in tokens
    assert "Doctor." in tokens


def test_orchestrator_build_response_stream_no_ack_on_short_utterance(monkeypatch):
    """Short utterances skip the ack -- the LLM tokens come first."""
    from ultron.pipeline.orchestrator import Orchestrator

    o = Orchestrator.__new__(Orchestrator)
    o.coding_voice = None
    o.conv_ack_source = ConversationalAckSource()
    o.web_gate = None
    o.web_executor = None

    class _FakeLLM:
        def generate_stream(self, text, **kwargs):
            yield "OK."

    o.llm = _FakeLLM()

    tokens = list(o._build_response_stream("yes"))
    assert tokens == ["OK."]


def test_orchestrator_build_response_stream_no_ack_during_clarification():
    """Pending coding-clarification suppresses the ack across all
    three no-search branches."""
    from ultron.pipeline.orchestrator import Orchestrator

    o = Orchestrator.__new__(Orchestrator)
    o.coding_voice = _StubCodingVoice(pending=True)
    o.conv_ack_source = ConversationalAckSource()
    o.web_gate = None
    o.web_executor = None

    class _FakeLLM:
        def generate_stream(self, text, **kwargs):
            yield "Alpha."

    o.llm = _FakeLLM()

    tokens = list(o._build_response_stream("What was your last suggestion?"))
    # First token is the LLM token, not an ack phrase.
    assert tokens[0] == "Alpha."
