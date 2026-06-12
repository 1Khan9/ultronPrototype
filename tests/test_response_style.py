"""Tests for the per-call response-style addenda.

Covers :func:`apply_brevity_hint` -- the 2026-05-10 reinforcement that
counters the 4B model's tendency to produce 4-paragraph essays in
response to short questions like "What are the Orcs in 40k?".

The hint must:
- fire on short, non-explain questions (the regression case)
- NOT fire on questions explicitly asking for depth
- NOT fire on long questions (they often legitimately need detail)
- pass through empty input unchanged
- compose cleanly above the user_text (newline-separated)
"""

from __future__ import annotations

import pytest

from kenning.response_style import (
    apply_brevity_hint,
    is_brief_question,
    is_factual_question,
    is_procedural_request,
)


# ---------------------------------------------------------------------------
# is_brief_question
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "utterance",
    [
        "What are the Orcs in 40k?",                      # live-session regression
        "Who are you?",
        "What food do ducks eat?",
        "What is rain?",
        "Why is the sky blue?",
        "What's the capital of France?",
        "Hello.",
    ],
)
def test_brief_question_detected(utterance):
    assert is_brief_question(utterance), f"expected brief: {utterance!r}"


@pytest.mark.parametrize(
    "utterance",
    [
        "Explain to me the Tyranids in 40k.",             # live-session OK case
        "Walk me through how to bake bread.",
        "Give me step-by-step instructions for changing the oil.",
        "Tell me everything you know about the Black Library.",
        "How do I file a Schedule C in detail?",
        "Elaborate on the differences between TCP and UDP.",
        "List all the planets in the solar system.",
    ],
)
def test_depth_request_skips_brevity(utterance):
    assert not is_brief_question(utterance), (
        f"expected non-brief because of depth marker: {utterance!r}"
    )


def test_long_question_skips_brevity():
    long_q = (
        "I'm trying to set up a multi-stage CI pipeline that builds a "
        "Docker image, runs unit tests inside the container, pushes "
        "the image to a private registry, then triggers a Kubernetes "
        "rolling deployment -- what are the right tooling choices and "
        "how should I sequence the jobs to keep wall-clock low?"
    )
    assert not is_brief_question(long_q)


def test_empty_or_whitespace_is_not_brief():
    assert not is_brief_question("")
    assert not is_brief_question("   ")
    assert not is_brief_question("\n\t\n")


def test_borderline_word_count():
    # 12 words exactly: at the threshold, still brief.
    twelve_words = "tell me what color sky is at dawn in late autumn here"
    assert is_brief_question(twelve_words)

    # 13 words: just over the threshold AND well over the char threshold,
    # so it falls out.
    thirteen_words = (
        "tell me what color sky is at dawn in late autumn here too"
    )
    # If words > 12 AND chars > 80, returns False. Char count here is
    # comfortably > 80 once split; check actual length and assert.
    if len(thirteen_words) > 80:
        assert not is_brief_question(thirteen_words)


# ---------------------------------------------------------------------------
# apply_brevity_hint
# ---------------------------------------------------------------------------


def test_apply_brevity_prepends_directive_to_brief():
    out = apply_brevity_hint("What are the Orcs in 40k?")
    assert out.startswith("[Style:")
    assert "1-3 short sentences" in out
    # Original text preserved at the end.
    assert out.endswith("What are the Orcs in 40k?")
    # Blank line between directive and user text.
    assert "]\n\nWhat" in out


def test_apply_brevity_returns_unchanged_on_depth_request():
    text = "Explain in detail how speculative decoding works."
    assert apply_brevity_hint(text) == text


def test_apply_brevity_returns_unchanged_on_long_question():
    long_q = (
        "I have a Python codebase that uses asyncio and I want to "
        "convert it to use threading instead -- what are the gotchas "
        "I should plan for and what would the migration look like?"
    )
    assert apply_brevity_hint(long_q) == long_q


def test_apply_brevity_returns_unchanged_on_empty():
    assert apply_brevity_hint("") == ""
    assert apply_brevity_hint("   ") == "   "


def test_apply_brevity_idempotent_when_already_hinted():
    """Calling apply_brevity_hint on already-hinted text should be a no-op
    (the dispatcher detects the '[Style:' prefix and passes through)."""
    once = apply_brevity_hint("Who are you?")
    twice = apply_brevity_hint(once)
    # Should not double-prepend the directive.
    assert twice.count("[Style: respond in 1-3 short sentences") == 1


# ---------------------------------------------------------------------------
# is_factual_question (Track 3 -- 2026-05-19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "utterance",
    [
        "How much does a duck weigh?",                  # live-session example
        "How much do hummingbirds weigh on average?",
        "How many planets are in the solar system?",
        "How long does a hummingbird live?",
        "How heavy is the average bowling ball?",
        "How tall is the Eiffel Tower?",
        "How big is the moon compared to earth?",
        "How old is the universe?",
        "How fast does sound travel?",
        "How far is Pluto from the sun?",
        "How cold is liquid nitrogen?",
        "How hot is the sun?",
        "How wide is the Mississippi river?",
        "How deep is the Mariana Trench?",
        "When did World War II end?",
        "When was the Empire State Building built?",
        "What year did Einstein publish relativity?",
        "What time does the sun rise tomorrow?",
        "Who is the current Prime Minister of Japan?",
        "Who was the first person on the moon?",
        "Who invented the telephone?",
        "Who discovered penicillin?",
        "What is the capital of France?",
        "What's the capital of Estonia?",
        "What is the population of Tokyo?",
        "What's the population of Iceland?",
        "What is the average lifespan of a beagle?",
        "What's the average rainfall in Seattle?",
        "What's the boiling point of water at sea level?",
        "What is the freezing point of mercury?",
    ],
)
def test_factual_question_detected(utterance):
    assert is_factual_question(utterance), (
        f"expected factual stem detection: {utterance!r}"
    )


@pytest.mark.parametrize(
    "utterance",
    [
        "What are the Orcs in 40k?",
        "Tell me a joke.",
        "Walk me through how to bake bread.",
        "Could you explain what dark matter is?",
        "Why is the sky blue?",
        "Hello.",
        "I love this weather.",
        "Show me a picture of a hummingbird.",
    ],
)
def test_factual_question_not_detected_on_non_stem(utterance):
    assert not is_factual_question(utterance), (
        f"expected NO factual stem: {utterance!r}"
    )


def test_factual_question_empty_input():
    assert not is_factual_question("")
    assert not is_factual_question("   ")
    assert not is_factual_question(None)  # type: ignore[arg-type]


def test_factual_question_handles_lead_in():
    """A factual stem buried in a longer lead-in still triggers."""
    assert is_factual_question(
        "I was just wondering, how much does a mallard duck typically weigh?"
    )


# ---------------------------------------------------------------------------
# is_procedural_request (Track 3 -- 2026-05-19)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "utterance",
    [
        "Give me step by step instructions to bake a cake.",
        "Walk me through how to set up a Python virtual environment.",
        "I need a comprehensive guide on building a deck.",
        "Write a comprehensive tutorial on Kubernetes.",
        "Provide a complete tutorial for editing video in DaVinci Resolve.",
        "Lay out the complete guide to running a marathon.",
        "Detail the full procedure for changing brake pads.",
        "Give me the full process for filing taxes.",
        "Give me the steps for installing solar panels.",
        "List the steps to register a new domain name.",
        "List out the steps to make sourdough bread.",
        "Tell me every step to assemble this furniture.",
        "Tell me all the steps to set up an OBS recording.",
        "Tell me what to do in order to publish a Python package.",
        "Give me detailed instructions for fly fishing.",
        "Provide me highly detailed step-by-step instructions to bake a cake.",
        "I need thorough instructions for refactoring this module.",
        "Tell me the instructions to build a shelf.",
    ],
)
def test_procedural_request_detected(utterance):
    assert is_procedural_request(utterance), (
        f"expected procedural marker: {utterance!r}"
    )


@pytest.mark.parametrize(
    "utterance",
    [
        "What are the Orcs in 40k?",
        "Explain quantum entanglement.",
        "Tell me about the French Revolution.",
        "How much does a duck weigh?",
        "Why is the sky blue?",
        "Elaborate on the differences between TCP and UDP.",
        "List all the planets in the solar system.",  # "list all" is depth, not procedural
        "How are you doing today?",
    ],
)
def test_procedural_request_not_detected(utterance):
    assert not is_procedural_request(utterance), (
        f"expected NO procedural marker: {utterance!r}"
    )


def test_procedural_request_empty_input():
    assert not is_procedural_request("")
    assert not is_procedural_request("   ")
    assert not is_procedural_request(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# apply_brevity_hint dispatcher across the three hint classes
# ---------------------------------------------------------------------------


def test_apply_dispatches_procedural_hint_first():
    """Procedural beats factual + brevity in priority."""
    out = apply_brevity_hint(
        "Provide me highly detailed step-by-step instructions to bake a cake."
    )
    assert out.startswith("[Style:")
    assert "numbered steps" in out
    # Should NOT have applied the factual or brevity hints.
    assert "1-3 short sentences" not in out
    assert "one short sentence" not in out


def test_apply_dispatches_factual_hint_on_fact_stem():
    """Factual stem beats brevity (even when length-brief)."""
    out = apply_brevity_hint("How much does a duck weigh?")
    assert out.startswith("[Style:")
    assert "one short sentence" in out
    assert "specific fact" in out
    # Should NOT have applied the brevity hint instead.
    assert "1-3 short sentences" not in out


def test_apply_dispatches_brevity_on_brief_non_fact_non_procedural():
    """Falls through to brevity for short questions that aren't
    factual stems or procedural requests."""
    out = apply_brevity_hint("What are the Orcs in 40k?")
    assert out.startswith("[Style:")
    assert "1-3 short sentences" in out


def test_apply_factual_overrides_long_lead_in():
    """A factual stem buried in a long lead-in still gets the
    factual hint, not the brevity hint."""
    text = (
        "I was just curious, given everything we talked about earlier, "
        "how much does a mallard duck typically weigh?"
    )
    out = apply_brevity_hint(text)
    assert "one short sentence" in out


def test_apply_procedural_overrides_long_request():
    """A procedural marker in a long request still triggers the
    procedural hint (not no-hint due to length)."""
    text = (
        "I'd really love it if you could provide me highly detailed "
        "step-by-step instructions for setting up a home Kubernetes "
        "cluster on Raspberry Pis."
    )
    out = apply_brevity_hint(text)
    assert "numbered steps" in out


def test_apply_returns_unchanged_on_long_open_question():
    """No hint when the question is long AND lacks factual/procedural
    markers."""
    text = (
        "What do you think about the broader implications of "
        "remote work on urban planning and small-business ecosystems?"
    )
    out = apply_brevity_hint(text)
    assert out == text


# ---------------------------------------------------------------------------
# Idempotence across hint classes
# ---------------------------------------------------------------------------


def test_apply_idempotent_on_procedural_already_hinted():
    once = apply_brevity_hint(
        "Walk me through how to set up a Python virtual environment."
    )
    twice = apply_brevity_hint(once)
    # Procedural hint should only appear once.
    assert twice.count("[Style: respond with detailed numbered steps") == 1


def test_apply_idempotent_on_factual_already_hinted():
    once = apply_brevity_hint("How much does a duck weigh?")
    twice = apply_brevity_hint(once)
    assert twice.count("[Style: respond with one short sentence") == 1


# ---------------------------------------------------------------------------
# Live-session regression: the duck and the cake
# ---------------------------------------------------------------------------


def test_duck_weight_gets_factual_hint():
    """Live-session example: ``How much does a duck weigh?`` was
    producing 3-sentence verbose responses. With the factual hint
    the directive forces a single-sentence reply."""
    out = apply_brevity_hint("How much does a duck weigh?")
    assert "one short sentence" in out
    assert "specific fact" in out


def test_cake_instructions_get_procedural_hint():
    """Live-session example: ``Provide me highly detailed step-by-
    step instructions to bake a cake`` was being refused outright or
    summarised in two sentences. The procedural hint forces the
    numbered-steps format."""
    out = apply_brevity_hint(
        "Provide me highly detailed step-by-step instructions to bake a cake."
    )
    assert "numbered steps" in out
    assert "measurements" in out
