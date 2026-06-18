"""GUI-action drain cadence + no-double-fire (2026-06-18).

The settings panel is a detached subprocess; it appends one JSON line per action
to data/gui_action.jsonl. The orchestrator drains that file in _wait_for_wake_word.

ROOT-CAUSE FIX: the drain used to run ONLY in the rare `chunk is None` (capture
stall) branch, so a quick action (esp. the speaker MUTE/UNMUTE buttons) could lag
up to a minute. It now runs every loop iteration (monotonic-throttled). This test
guards the safety property that letting it run far more often does NOT re-fire an
already-consumed action -- the byte-offset cursor must consume each appended line
EXACTLY once regardless of call frequency.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kenning.pipeline.orchestrator import Orchestrator


def _bare_orchestrator():
    """An Orchestrator shell with only what _drain_gui_actions touches."""
    o = Orchestrator.__new__(Orchestrator)
    calls = []
    o._apply_gui_action = lambda action, value: calls.append((action, value))
    return o, calls


def test_drain_consumes_each_action_exactly_once(monkeypatch, tmp_path):
    import kenning.config as cfg
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    action_file = data / "gui_action.jsonl"
    action_file.write_text("", encoding="utf-8")

    o, calls = _bare_orchestrator()

    # First sight: existing content is skipped (a stale file never replays).
    action_file.write_text('{"action": "stale", "value": 1}\n', encoding="utf-8")
    o._drain_gui_actions()
    assert calls == [], "first-sight must skip pre-existing history"

    # Append one real action, then drain MANY times rapidly (the new cadence).
    with action_file.open("a", encoding="utf-8") as f:
        f.write('{"action": "speaker_mute", "value": true}\n')
    for _ in range(50):
        o._drain_gui_actions()
    assert calls == [("speaker_mute", True)], (
        "an appended action must fire EXACTLY once no matter how often we drain"
    )

    # A second action appends and fires exactly once more.
    with action_file.open("a", encoding="utf-8") as f:
        f.write('{"action": "speaker_mute", "value": false}\n')
    for _ in range(50):
        o._drain_gui_actions()
    assert calls == [("speaker_mute", True), ("speaker_mute", False)]


def test_drain_no_file_is_noop(monkeypatch, tmp_path):
    import kenning.config as cfg
    monkeypatch.setattr(cfg, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    o, calls = _bare_orchestrator()
    # No action file at all -> must not raise, must do nothing.
    o._drain_gui_actions()
    assert calls == []
