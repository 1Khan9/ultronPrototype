"""Tests for the voice-summoned log-viewer matcher (match_logs_command).

The overlay itself is GUI (tkinter daemon thread) and not unit-tested here; the
matcher is the pure-logic surface that gates it.
"""
import pytest

from kenning.audio.log_viewer import match_logs_command


@pytest.mark.parametrize("text,expected", [
    ("show me the logs", "open"),
    ("pull up the logs", "open"),
    ("open the logs", "open"),
    ("bring up the log window", "open"),
    ("show the terminal logs", "open"),
    ("let me see the logs", "open"),
    ("pull up the log viewer", "open"),
    ("ultron, show me the logs", "open"),
    ("display the console output", "open"),
    ("close the logs", "close"),
    ("hide the log window", "close"),
    ("dismiss the logs", "close"),
])
def test_logs_command_hits(text, expected):
    assert match_logs_command(text) == expected


@pytest.mark.parametrize("text", [
    "",
    "rush B",
    "they have no smokes",
    "what's in the logs",                       # question -> LLM
    "are there any logs",                       # question
    "i checked the logs earlier",               # narration (leads with "i")
    "tell my team to log on",                   # relay, not a log-window command
    "the enemy is logging in mid",              # not a command
    "show me the stop button",                  # a different window command
    "what does the log show about the last round and the whole economy",  # too long
])
def test_logs_command_misses(text):
    assert match_logs_command(text) is None
