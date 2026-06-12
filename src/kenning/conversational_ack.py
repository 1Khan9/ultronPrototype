"""Conversational filler-acknowledgment source.

The web-search path already yields a "Verifying against the network."
style acknowledgment so the user isn't stuck in silence while Brave +
Jina + the LLM cycle. The conversational (no-search) path historically
had no such acknowledgment, so on a typical turn the user faces:

    VAD silence wait (1200 ms)
    Whisper transcribe (~890 ms)
    LLM TTFT (~79 ms)
    TTS synth first chunk (~350 ms)
    ----
    ~2.5 s of silence before Kenning speaks

That's a long perceived gap. Filler-ack masks it: yield a short
thinking-noise phrase (``Mm.``, ``Right.``, etc.) BEFORE the LLM
stream so the TTS pipeline starts speaking within ~200 ms of Whisper
completing. End-to-end latency is unchanged but perceived latency
drops sharply.

Heuristic gate keeps it from firing where it would feel weird:

- Very short utterances ("yes", "no", "thanks") get no ack -- the gap
  is small anyway and an ack on an interjection-length reply sounds
  over-eager.
- Pending coding-task clarifications get no ack -- the orchestrator
  has its own narration flow for those and a double-ack is confusing.

The phrase pool is intentionally tiny and tonally non-committal --
they read as Kenning pausing to consider, not Kenning narrating
external activity. Voice-quality lock preserved: no SOUL.md change,
no persona change; this is a per-call additive token like the
web-search ack.
"""

from __future__ import annotations

from typing import List, Optional

from kenning.web_search.acknowledgments import AcknowledgmentSource


# Conversational filler-acks. Short, in-character thinking noises.
# Distinct from the web-search ack pool (which describes external
# activity); these read as Kenning deliberating. Keep the pool small
# so the user doesn't notice the same phrase too often -- the
# shuffled-cycle in AcknowledgmentSource ensures no immediate repeats.
_CONVERSATIONAL_PHRASES: List[str] = [
    "Mm.",
    "Right.",
    "Hm.",
    "Considering.",
    "Let me think.",
    "Noted.",
    "Processing.",
    "Working on it.",
]


# Heuristic thresholds for the gate function. Exposed as module
# constants (not config) so tests can override them with monkeypatch
# without going through pydantic. If real-world tuning ever wants a
# config knob, lifting these is one PR.
_MIN_CHARS = 11   # "what is x?" = 10 chars -> NO ack
_MIN_WORDS = 4    # "tell me about" = 3 words -> NO ack


def is_conversational_ack_eligible(
    user_text: str,
    *,
    has_pending_clarification: bool = False,
) -> bool:
    """Decide whether to yield a filler-ack on the conversational path.

    Args:
        user_text: The transcribed utterance (post-Whisper, pre-LLM).
        has_pending_clarification: True if the orchestrator is in the
            middle of a coding-task clarification dialogue; suppresses
            the ack to avoid stepping on the clarification narration.

    Returns:
        True iff the gate lets the ack fire. The caller is responsible
        for actually pulling a phrase from the pool when this returns
        True.

    Logic:
        - Empty/whitespace input -> False (nothing to ack).
        - Pending clarification -> False (avoid double-ack).
        - Very short utterance (<= MIN_CHARS chars OR <= MIN_WORDS
          words after strip) -> False (perceived gap is small on
          short replies; ack would feel over-eager).
        - Otherwise True.
    """
    stripped = (user_text or "").strip()
    if not stripped:
        return False
    if has_pending_clarification:
        return False
    if len(stripped) < _MIN_CHARS:
        return False
    if len(stripped.split()) < _MIN_WORDS:
        return False
    return True


class ConversationalAckSource:
    """Shuffled-cycle phrase generator for the conversational filler-ack.

    Thin wrapper around :class:`AcknowledgmentSource` with the
    conversational phrase pool baked in. Holding it as a distinct
    class type makes the orchestrator's intent obvious at call sites
    (and keeps the web-search ack source's cycle state separate so
    the two pools rotate independently).
    """

    def __init__(self, phrases: Optional[List[str]] = None) -> None:
        # ``None`` -> use the default pool. An explicit empty list is
        # forwarded to the underlying AcknowledgmentSource so its own
        # validation rejects it (vs silently swapping to the default,
        # which would mask configuration errors).
        if phrases is None:
            phrases = _CONVERSATIONAL_PHRASES
        self._source = AcknowledgmentSource(phrases)

    def next_phrase(self) -> str:
        """Return the next phrase from the shuffled cycle.

        Same contract as :meth:`AcknowledgmentSource.next_phrase` --
        every phrase appears once per cycle, no immediate repeats.
        Thread-safe via the wrapped source's lock.
        """
        return self._source.next_phrase()
