"""Phase 2 additions to the coding intent classifier.

Pre-existing intent tests live in :mod:`tests.test_coding_intent`. This
file covers only the Phase 2 additions: ``MID_SESSION_ADJUSTMENT`` and
``CLARIFICATION_RESPONSE``.

The 20-case adjustment test set the spec asks for is parametrized below
(15 positives + 5 negatives that must NOT classify as adjustments).
"""

from __future__ import annotations

import pytest

from kenning.coding.intent import classify, CodingIntentKind


# ---------------------------------------------------------------------------
# MID_SESSION_ADJUSTMENT
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "Actually, have him use Postgres instead of SQLite.",
    "Tell him to add logging to the auth module.",
    "Have claude switch to FastAPI.",
    "Make him use httpx instead of requests.",
    "Change that to use TOML configuration.",
    "Instead of YAML, have him use JSON.",
    "Have him remove the auth dependency for now.",
    "Make claude focus on the database layer first.",
    "Tell claude to drop the email feature.",
    "On second thought, have him write integration tests too.",
    "Don't have him use Postgres.",
    "Hold on, change that to a single-file approach.",
    "Forget the migration approach -- have him do raw SQL.",
    "Have him use the existing Logger module.",
    "Tell him to add type hints everywhere.",
])
def test_adjustment_phrases_classify_when_active(utterance):
    intent = classify(utterance, has_active_task=True)
    assert intent.kind == CodingIntentKind.MID_SESSION_ADJUSTMENT, (
        f"unexpected kind on {utterance!r}: {intent.kind} ({intent.reason})"
    )
    assert intent.task_text == utterance


@pytest.mark.parametrize("utterance", [
    "What time is it?",
    "Tell me a joke.",
    "Play some music.",
    "How tall is Mount Everest?",
    "Cancel my reminder for tomorrow.",
])
def test_adjustment_phrases_dont_misfire_on_unrelated_speech(utterance):
    intent = classify(utterance, has_active_task=True)
    assert intent.kind != CodingIntentKind.MID_SESSION_ADJUSTMENT, (
        f"adjustment misfired on {utterance!r}: {intent.kind}"
    )


def test_adjustment_does_not_fire_when_no_active_task():
    """Without an active session, "have him use postgres" is meaningless;
    fall through to the regular LLM path."""
    intent = classify(
        "Actually, have him use postgres.", has_active_task=False,
    )
    assert intent.kind == CodingIntentKind.NONE


def test_cancel_takes_priority_over_adjustment():
    """If the user says "stop the task" while a task is running it should
    cancel, not be interpreted as an adjustment."""
    intent = classify("Stop the task.", has_active_task=True)
    assert intent.kind == CodingIntentKind.CANCEL


# ---------------------------------------------------------------------------
# CLARIFICATION_RESPONSE
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "Use SQLite.",
    "Yes, write a history file.",
    "Plain text is fine.",
    "Go with FastAPI.",
    "Three retries.",
    "Skip auth for now.",
    "JSON.",
    "I prefer Postgres for that.",
])
def test_clarification_response_routes_when_pending(utterance):
    intent = classify(
        utterance,
        has_active_task=True,
        has_pending_clarification=True,
    )
    assert intent.kind == CodingIntentKind.CLARIFICATION_RESPONSE


def test_clarification_response_does_not_hijack_coding_commands():
    """Even with a clarification pending, "create a flask app" is a fresh
    coding task -- not the user answering Claude's question."""
    intent = classify(
        "Create a flask app called inventory.",
        has_active_task=True, has_pending_clarification=True,
    )
    assert intent.kind == CodingIntentKind.CODE_TASK


def test_clarification_response_does_not_fire_without_pending():
    """If no clarification is pending, a short answer-shaped utterance
    is just regular speech."""
    intent = classify("yes", has_active_task=True, has_pending_clarification=False)
    assert intent.kind != CodingIntentKind.CLARIFICATION_RESPONSE
