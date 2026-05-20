"""2026-05-19 Issue 7 fix: second-person adjustment patterns.

Live session 2026-05-19: after the PNG-to-JPEG converter coding task
generated code, the user said 'edit it and add a tkinter GUI' to
extend the work. The legacy ``_ADJUSTMENT_PATTERNS`` regex required
third-person phrasing ('have him X', 'tell him to Y') and missed the
natural second-person form, so the utterance fell through to
``_CODE_TRIGGERS`` -- which classified it as a NEW coding task and
the voice handler refused because a task was already running (or
would have scaffolded a fresh project instead of continuing the
existing one).

The extended regex catches the natural follow-up vocabulary
("add a tkinter GUI", "now include error handling", "change the
database to postgres", etc.) when ``has_active_task=True`` (which
in voice.py is True for active task OR active project session).
"""

from __future__ import annotations

import pytest

from ultron.coding.intent import (
    CodingIntent,
    CodingIntentKind,
    classify,
)


# ---------------------------------------------------------------------------
# Second-person follow-up imperatives must classify as MID_SESSION_ADJUSTMENT
# when a coding task / session is active.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "add a tkinter GUI",
    "edit it and add a tkinter GUI",
    "now add error handling",
    "also include a CLI argument",
    "please add type hints",
    "can you add a logging module",
    "could you include better docstrings",
    "would you fix the broken test",
    "go ahead and add a progress bar",
    "I want you to refactor the parser",
    "I'd like to extend the converter",
    "change the database to postgres",
    "rename main to entry_point",
    "fix the bug in the parser",
    "refactor the entire module",
    "remove the deprecated helper",
    "delete the broken test",
    "drop the legacy adapter",
    "replace requests with httpx",
    "swap the json parser for orjson",
    "migrate the script to async",
    "convert it to use typing",
    "port the function to typescript",
    "rename get_data to fetch_payload",
    "move the helper into utils.py",
    "wire the metrics into prometheus",
    "hook up the new endpoint",
    "plug in the validator",
    "integrate the rate limiter",
    "connect the cache layer",
    "enable verbose logging",
    "disable the retry path",
    "toggle the debug flag",
    "expose a public api method",
    "hide the internal helper",
    "optimise the inner loop",
    "harden the input parser",
    "polish the error messages",
    "clean up the imports",
    "tighten the regex",
    "format the output as JSON",
    "document the public functions",
    "comment the tricky regex",
    "annotate the parameters with types",
    "give it a window",
    "give the script a CLI",
    "give the project a README",
    "make it support multiple files",
    "make the code handle empty input",
    "make the app return JSON",
    "put in a docstring",
    "throw in a docstring",
    "build in a sanity check",
])
def test_second_person_adjustment_fires_with_active_task(utterance):
    intent = classify(utterance, has_active_task=True)
    assert intent.kind == CodingIntentKind.MID_SESSION_ADJUSTMENT, (
        f"expected MID_SESSION_ADJUSTMENT for {utterance!r}, "
        f"got {intent.kind.value} (reason: {intent.reason})"
    )


# ---------------------------------------------------------------------------
# Without an active task / session, adjustment patterns DO NOT fire.
# The user is talking conversationally; coding patterns shouldn't hijack.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "add a tkinter GUI",
    "change the database",
    "fix the bug",
    "refactor the module",
    "include a CLI",
])
def test_adjustment_does_not_fire_without_active_task(utterance):
    intent = classify(utterance, has_active_task=False)
    # The utterance should resolve to NONE or CODE_TASK -- never to
    # MID_SESSION_ADJUSTMENT (which requires an active task by contract).
    assert intent.kind != CodingIntentKind.MID_SESSION_ADJUSTMENT


# ---------------------------------------------------------------------------
# Legacy third-person patterns still fire (regression coverage).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("utterance", [
    "actually have him use postgres",
    "tell him to add logging",
    "have him use sqlite",
    "make him add tests",
    "actually change the approach",
    "change that to use kafka",
    "forget that approach",
    "on second thought have him pivot",
])
def test_legacy_third_person_adjustment_still_fires(utterance):
    intent = classify(utterance, has_active_task=True)
    assert intent.kind == CodingIntentKind.MID_SESSION_ADJUSTMENT, (
        f"regressed legacy pattern {utterance!r}"
    )


# ---------------------------------------------------------------------------
# Cancel / progress patterns still win when applicable.
# ---------------------------------------------------------------------------


def test_cancel_pattern_wins_over_adjustment():
    """'cancel the task' must classify as CANCEL even though 'cancel'
    isn't in the adjustment verb list (regression cover)."""
    intent = classify("cancel the task", has_active_task=True)
    assert intent.kind == CodingIntentKind.CANCEL


def test_progress_pattern_wins_over_adjustment():
    """'how is the project going' must classify as PROGRESS_QUERY,
    not adjustment, even though it contains task-related words."""
    intent = classify("how is the project going", has_active_task=True)
    assert intent.kind == CodingIntentKind.PROGRESS_QUERY


# ---------------------------------------------------------------------------
# CODE_TASK (new project) still wins when there's no active task and the
# user says "write me a new program" -- the adjustment patterns gate
# correctly on has_active_task=False.
# ---------------------------------------------------------------------------


def test_new_code_task_still_fires_without_active_task():
    intent = classify(
        "write me a new program that calculates pi",
        has_active_task=False,
    )
    assert intent.kind == CodingIntentKind.CODE_TASK


# ---------------------------------------------------------------------------
# The specific live-session utterance.
# ---------------------------------------------------------------------------


def test_live_session_2026_05_19_edit_and_add_tkinter_gui():
    """The exact utterance from the live session that didn't route
    correctly. Pin it so a future regression in the regex shows up
    immediately."""
    intent = classify(
        "edit it and add a tkinter GUI",
        has_active_task=True,
    )
    assert intent.kind == CodingIntentKind.MID_SESSION_ADJUSTMENT
