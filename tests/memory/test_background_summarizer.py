"""Tests for the BackgroundSummarizer (Tracks 1c + 1d + 1e).

Covers:
* JSON parsing -- happy path, fenced markdown, brace-balanced extraction
* SummaryResult shape -- empty-state detection
* Gating -- idle threshold, cadence, min_turns, in-flight guard
* Cancellation -- mid-call abort
* Storage hook -- success + failure paths
* render_summary_prompt -- pure function
"""

from __future__ import annotations

import json
import time
from typing import Callable, List

import pytest

from ultron.memory.background_summarizer import (
    BackgroundSummarizer,
    DecisionEntry,
    FactEntry,
    PreferenceEntry,
    SummaryResult,
    TurnSnapshot,
    parse_summary_response,
    render_summary_prompt,
)


# ---------------------------------------------------------------------------
# render_summary_prompt
# ---------------------------------------------------------------------------


def test_render_prompt_contains_each_turn():
    turns = [
        TurnSnapshot(turn_id=0, ts=0.0, role="user", content="Hi"),
        TurnSnapshot(turn_id=1, ts=1.0, role="assistant", content="Hello."),
    ]
    out = render_summary_prompt(turns)
    assert "[user] Hi" in out
    assert "[assistant] Hello." in out
    assert "VALID JSON" in out
    assert "summary" in out


def test_render_prompt_empty_turns():
    out = render_summary_prompt([])
    assert "VALID JSON" in out
    # Conversation section exists even when empty.
    assert "--- Conversation ---" in out


# ---------------------------------------------------------------------------
# parse_summary_response
# ---------------------------------------------------------------------------


def test_parse_clean_json():
    raw = json.dumps({
        "summary": "Discussed Llama vs Gemma swap.",
        "facts": [
            {"subject": "Gemma 3 4B", "predicate": "has", "object": "IFEval 90.2"},
        ],
        "decisions": [
            {"topic": "LLM swap", "outcome": "Try Gemma", "status": "pending"},
        ],
        "preferences": [
            {"topic": "verbosity", "value": "shorter for factual queries"},
        ],
    })
    result = parse_summary_response(raw, turn_id_start=10, turn_id_end=20)
    assert result is not None
    assert "Llama vs Gemma" in result.summary
    assert len(result.facts) == 1
    assert result.facts[0].subject == "Gemma 3 4B"
    assert len(result.decisions) == 1
    assert result.decisions[0].topic == "LLM swap"
    assert result.decisions[0].status == "pending"
    assert len(result.preferences) == 1
    assert result.turn_id_start == 10
    assert result.turn_id_end == 20


def test_parse_fenced_markdown_json():
    """Small models sometimes wrap JSON in markdown fences."""
    raw = (
        "Here is the summary:\n\n```json\n"
        + json.dumps({"summary": "Brief.", "facts": [], "decisions": [], "preferences": []})
        + "\n```\n"
    )
    result = parse_summary_response(raw)
    assert result is not None
    assert result.summary == "Brief."


def test_parse_brace_balanced_fallback():
    """Trailing prose after the JSON should be discarded."""
    raw = (
        '{"summary": "Brief.", "facts": []}\n\n'
        "(End of summary.) Hope that helps!"
    )
    result = parse_summary_response(raw)
    assert result is not None
    assert result.summary == "Brief."


def test_parse_unparseable_returns_none():
    assert parse_summary_response("totally not json") is None
    assert parse_summary_response("") is None
    assert parse_summary_response("{ broken: }") is None


def test_parse_missing_keys_defaults_to_empty():
    raw = json.dumps({"summary": "Only summary, no other fields."})
    result = parse_summary_response(raw)
    assert result is not None
    assert result.facts == []
    assert result.decisions == []
    assert result.preferences == []


def test_parse_skips_malformed_entries():
    """Individual broken entries don't abort the whole parse."""
    raw = json.dumps({
        "summary": "Mixed.",
        "facts": [
            {"subject": "X", "predicate": "is", "object": "Y"},  # good
            "not a dict",                                          # bad
            {"subject": "", "predicate": "", "object": ""},       # empty
            {"subject": "Z", "predicate": "was", "object": "W"},  # good
        ],
        "decisions": "not a list",  # wrong type
        "preferences": [],
    })
    result = parse_summary_response(raw)
    assert result is not None
    assert len(result.facts) == 2
    assert result.decisions == []


def test_parse_normalises_decision_status():
    raw = json.dumps({
        "summary": "Mixed statuses.",
        "decisions": [
            {"topic": "A", "outcome": "...", "status": "considering"},
            {"topic": "B", "outcome": "...", "status": "decided"},
            {"topic": "C", "outcome": "...", "status": "rolled back"},
            {"topic": "D", "outcome": "...", "status": "made"},
            {"topic": "E", "outcome": "...", "status": ""},
        ],
    })
    result = parse_summary_response(raw)
    statuses = [d.status for d in result.decisions]
    assert "pending" in statuses
    assert "made" in statuses
    assert "reversed" in statuses


def test_summary_result_is_empty():
    empty = SummaryResult(summary="", facts=[], decisions=[], preferences=[])
    assert empty.is_empty
    not_empty = SummaryResult(
        summary="something", facts=[], decisions=[], preferences=[]
    )
    assert not not_empty.is_empty


def test_entry_to_text_helpers():
    f = FactEntry(subject="duck", predicate="weighs", object="3 pounds")
    assert f.to_text() == "duck weighs 3 pounds"
    d = DecisionEntry(topic="LLM swap", outcome="Use Gemma", status="pending")
    assert "LLM swap" in d.to_text()
    p = PreferenceEntry(topic="brevity", value="prefer short answers")
    assert "User preference" in p.to_text()


# ---------------------------------------------------------------------------
# BackgroundSummarizer gating
# ---------------------------------------------------------------------------


def _make_turns(n: int, start_id: int = 0) -> List[TurnSnapshot]:
    return [
        TurnSnapshot(
            turn_id=start_id + i,
            ts=start_id + i,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Turn {start_id + i}",
        )
        for i in range(n)
    ]


def test_summarizer_skips_when_idle_threshold_not_met():
    """The summarizer must not fire when recent foreground activity
    is within the idle threshold."""
    turns = _make_turns(15)
    fake_now = [1000.0]
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: pytest.fail("LLM should not have been called"),
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=30.0,
        now_provider=lambda: fake_now[0],
    )
    # Activity 10 s ago -- below 30 s threshold.
    result = summarizer.maybe_summarize(last_activity_monotonic=fake_now[0] - 10.0)
    assert result is None


def test_summarizer_skips_when_too_few_new_turns():
    """Below ``min_turns`` new turns -> skip."""
    turns = _make_turns(2)
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: pytest.fail("LLM should not have been called"),
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=5,
        min_turns=3,
    )
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is None


def test_summarizer_skips_when_below_cadence():
    """Above min_turns but below cadence -> wait."""
    turns = _make_turns(4)
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: pytest.fail("LLM should not have been called"),
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is None


def test_summarizer_fires_when_all_gates_pass():
    turns = _make_turns(12)
    response = json.dumps({
        "summary": "Twelve-turn conversation summarised.",
        "facts": [],
        "decisions": [],
        "preferences": [],
    })
    captured: List[SummaryResult] = []
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: response,
        store_fn=lambda r: captured.append(r),
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is not None
    assert "Twelve-turn" in result.summary
    assert len(captured) == 1
    assert summarizer.last_summarized_turn_id == 11  # last turn id


def test_summarizer_does_not_double_summarize_same_span():
    """After a successful pass, the watermark advances so a second
    call with the same turns short-circuits."""
    turns = _make_turns(12)
    response = json.dumps({"summary": "ok", "facts": [], "decisions": [], "preferences": []})
    call_count = [0]

    def gen(_):
        call_count[0] += 1
        return response

    summarizer = BackgroundSummarizer(
        generate_fn=gen,
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    summarizer.maybe_summarize(last_activity_monotonic=0.0)
    summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert call_count[0] == 1


def test_summarizer_handles_llm_exception():
    """LLM exception is swallowed; the call returns None and the
    watermark does NOT advance."""
    turns = _make_turns(12)

    def gen(_):
        raise RuntimeError("LLM is on fire")

    summarizer = BackgroundSummarizer(
        generate_fn=gen,
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is None
    assert summarizer.last_summarized_turn_id == -1


def test_summarizer_handles_unparseable_response():
    """LLM returns garbage JSON; result is None; watermark stays put."""
    turns = _make_turns(12)
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: "I'm afraid I cannot do that.",
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is None
    assert summarizer.last_summarized_turn_id == -1


def test_summarizer_cancellation_aborts_run():
    """A cancel flag set before _run skips the LLM call entirely."""
    turns = _make_turns(12)

    def gen(_):
        pytest.fail("LLM should not have been called after cancel")

    summarizer = BackgroundSummarizer(
        generate_fn=gen,
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    summarizer.cancel()
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is None


def test_summarizer_store_failure_does_not_break_pass():
    """The result is still returned even if the store hook raises."""
    turns = _make_turns(12)
    response = json.dumps({
        "summary": "Done.", "facts": [], "decisions": [], "preferences": [],
    })

    def broken_store(_r):
        raise RuntimeError("Qdrant is down")

    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: response,
        store_fn=broken_store,
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is not None
    # Watermark advanced even though store failed (don't replay
    # already-paid tokens).
    assert summarizer.last_summarized_turn_id == 11


def test_summarizer_force_run_bypasses_gates():
    """``force_run`` ignores idle / cadence / min_turns gates."""
    turns = _make_turns(2)  # too few for normal cadence
    response = json.dumps({
        "summary": "Two turns.", "facts": [], "decisions": [], "preferences": [],
    })
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: response,
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=999.0,
        cadence_turns=999,
        min_turns=999,
    )
    result = summarizer.force_run(turns)
    assert result is not None
    assert "Two turns" in result.summary


def test_summarizer_in_flight_guard():
    """A second concurrent call returns None (lock guards in_flight)."""
    turns = _make_turns(12)
    response = json.dumps({"summary": "ok", "facts": [], "decisions": [], "preferences": []})
    summarizer = BackgroundSummarizer(
        generate_fn=lambda _: response,
        recent_turns_fn=lambda: turns,
        idle_threshold_seconds=0.0,
        cadence_turns=10,
        min_turns=3,
    )
    # Manually flip the guard.
    summarizer._in_flight = True
    result = summarizer.maybe_summarize(last_activity_monotonic=0.0)
    assert result is None
    summarizer._in_flight = False
