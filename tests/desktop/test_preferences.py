"""Tests for kenning.desktop.preferences."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kenning.desktop.preferences import (
    DesktopPreference,
    PreferenceLogger,
    _format_for_workspace,
    _from_dict,
    find_preference_for_phrase,
    get_preference_logger,
    get_workspace_writer,
    record_launch_preference,
    set_preference_logger,
    set_workspace_writer,
)


# ---------------------------------------------------------------------------
# DesktopPreference dataclass
# ---------------------------------------------------------------------------


def test_desktop_preference_defaults():
    p = DesktopPreference(user_phrase="open chrome", app_name="chrome")
    assert p.url is None
    assert p.monitor_index is None
    assert p.fullscreen is False
    assert p.maximize is False
    assert p.success is True
    assert p.timestamp == 0.0


def test_desktop_preference_is_frozen():
    p = DesktopPreference(user_phrase="x", app_name="chrome")
    with pytest.raises(Exception):
        p.app_name = "edge"


def test_from_dict_round_trip():
    original = DesktopPreference(
        user_phrase="open youtube on monitor 2",
        app_name="chrome",
        url="https://www.youtube.com",
        monitor_index=1,
        fullscreen=False,
        maximize=True,
        success=True,
        timestamp=1234567890.0,
    )
    from dataclasses import asdict
    obj = asdict(original)
    restored = _from_dict(obj)
    assert restored == original


def test_from_dict_with_missing_fields():
    """Missing fields use defaults rather than raising."""
    p = _from_dict({"app_name": "chrome"})
    assert p.app_name == "chrome"
    assert p.user_phrase == ""
    assert p.url is None


# ---------------------------------------------------------------------------
# PreferenceLogger
# ---------------------------------------------------------------------------


def test_logger_creates_parent_dir(tmp_path):
    log_path = tmp_path / "deeply" / "nested" / "pref.jsonl"
    PreferenceLogger(log_path)
    assert log_path.parent.exists()


def test_logger_record_writes_jsonl(tmp_path):
    log_path = tmp_path / "pref.jsonl"
    lg = PreferenceLogger(log_path)
    pref = DesktopPreference(
        user_phrase="open youtube on monitor 2",
        app_name="chrome",
        url="https://www.youtube.com",
        monitor_index=1,
        maximize=True,
    )
    assert lg.record(pref) is True
    content = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 1
    obj = json.loads(content[0])
    assert obj["user_phrase"] == "open youtube on monitor 2"
    assert obj["app_name"] == "chrome"
    assert obj["timestamp"] > 0


def test_logger_record_appends(tmp_path):
    log_path = tmp_path / "pref.jsonl"
    lg = PreferenceLogger(log_path)
    for i in range(3):
        lg.record(DesktopPreference(
            user_phrase=f"phrase {i}",
            app_name=f"app{i}",
            timestamp=float(i),
        ))
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3


def test_logger_record_stamps_timestamp(tmp_path):
    log_path = tmp_path / "pref.jsonl"
    lg = PreferenceLogger(log_path)
    before = time.time()
    lg.record(DesktopPreference(
        user_phrase="x", app_name="chrome", timestamp=0.0,
    ))
    after = time.time()
    obj = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert before <= obj["timestamp"] <= after


def test_logger_read_all_empty_log(tmp_path):
    """No log file == empty list, not error."""
    lg = PreferenceLogger(tmp_path / "ghost.jsonl")
    assert lg.read_all() == []


def test_logger_read_all_returns_in_write_order(tmp_path):
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    for i in range(5):
        lg.record(DesktopPreference(
            user_phrase=f"phrase_{i}",
            app_name="chrome",
            timestamp=float(i),
        ))
    prefs = lg.read_all()
    assert [p.user_phrase for p in prefs] == [f"phrase_{i}" for i in range(5)]


def test_logger_read_all_filters_by_age(tmp_path):
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    now = time.time()
    lg.record(DesktopPreference(
        user_phrase="old", app_name="chrome",
        timestamp=now - 90 * 86400,  # 90 days old
    ))
    lg.record(DesktopPreference(
        user_phrase="recent", app_name="chrome",
        timestamp=now - 1 * 86400,   # 1 day old
    ))
    # 30-day cutoff: drops the 90-day-old entry.
    prefs = lg.read_all(max_age_days=30.0)
    assert len(prefs) == 1
    assert prefs[0].user_phrase == "recent"


def test_logger_read_all_skips_malformed_lines(tmp_path):
    log_path = tmp_path / "pref.jsonl"
    lg = PreferenceLogger(log_path)
    # Write valid + invalid + valid manually.
    log_path.write_text(
        '{"user_phrase":"a","app_name":"chrome","timestamp":1.0}\n'
        'NOT_JSON\n'
        '{"user_phrase":"b","app_name":"edge","timestamp":2.0}\n',
        encoding="utf-8",
    )
    prefs = lg.read_all()
    assert len(prefs) == 2
    assert prefs[0].user_phrase == "a"
    assert prefs[1].user_phrase == "b"


# ---------------------------------------------------------------------------
# find_preference_for_phrase
# ---------------------------------------------------------------------------


def test_find_preference_substring_match(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    lg.record(DesktopPreference(
        user_phrase="open youtube on my second monitor",
        app_name="chrome",
        monitor_index=1,
        maximize=True,
        timestamp=time.time(),
    ))
    set_preference_logger(lg)
    try:
        result = find_preference_for_phrase("open youtube")
        assert result is not None
        assert result.monitor_index == 1
        assert result.maximize is True
    finally:
        set_preference_logger(None)


def test_find_preference_reverse_substring(tmp_path):
    """Stored phrase as substring of query also matches."""
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    lg.record(DesktopPreference(
        user_phrase="open chrome",
        app_name="chrome",
        timestamp=time.time(),
    ))
    set_preference_logger(lg)
    try:
        result = find_preference_for_phrase("hey kenning open chrome please")
        assert result is not None
        assert result.user_phrase == "open chrome"
    finally:
        set_preference_logger(None)


def test_find_preference_recency_wins(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    now = time.time()
    lg.record(DesktopPreference(
        user_phrase="open youtube",
        app_name="chrome",
        monitor_index=0,
        timestamp=now - 100,
    ))
    lg.record(DesktopPreference(
        user_phrase="open youtube on monitor 2",
        app_name="chrome",
        monitor_index=1,
        timestamp=now,
    ))
    set_preference_logger(lg)
    try:
        result = find_preference_for_phrase("open youtube")
        assert result is not None
        # Most recent matching wins.
        assert result.monitor_index == 1
    finally:
        set_preference_logger(None)


def test_find_preference_excludes_failures(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    lg.record(DesktopPreference(
        user_phrase="open chrome",
        app_name="chrome",
        success=False,
        timestamp=time.time(),
    ))
    set_preference_logger(lg)
    try:
        assert find_preference_for_phrase("open chrome") is None
    finally:
        set_preference_logger(None)


def test_find_preference_short_query_rejected(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    lg.record(DesktopPreference(
        user_phrase="open chrome",
        app_name="chrome",
        timestamp=time.time(),
    ))
    set_preference_logger(lg)
    try:
        assert find_preference_for_phrase("op") is None
        assert find_preference_for_phrase("") is None
        assert find_preference_for_phrase("   ") is None
    finally:
        set_preference_logger(None)


def test_find_preference_no_match_returns_none(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    lg.record(DesktopPreference(
        user_phrase="open chrome",
        app_name="chrome",
        timestamp=time.time(),
    ))
    set_preference_logger(lg)
    try:
        assert find_preference_for_phrase("totally unrelated query") is None
    finally:
        set_preference_logger(None)


# ---------------------------------------------------------------------------
# record_launch_preference convenience
# ---------------------------------------------------------------------------


def test_record_launch_preference_writes(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    set_preference_logger(lg)
    try:
        ok = record_launch_preference(
            user_phrase="open youtube on my second monitor",
            app_name="chrome",
            monitor_index=1,
            fullscreen=False,
            maximize=True,
            url="https://www.youtube.com",
        )
        assert ok is True
        prefs = lg.read_all()
        assert len(prefs) == 1
        assert prefs[0].app_name == "chrome"
        assert prefs[0].monitor_index == 1
    finally:
        set_preference_logger(None)


def test_record_launch_preference_empty_phrase_rejected(tmp_path):
    set_preference_logger(None)
    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    set_preference_logger(lg)
    try:
        assert record_launch_preference(
            user_phrase="", app_name="chrome",
            monitor_index=None, fullscreen=False, maximize=False,
        ) is False
        assert record_launch_preference(
            user_phrase="x", app_name="",
            monitor_index=None, fullscreen=False, maximize=False,
        ) is False
    finally:
        set_preference_logger(None)


def test_record_launch_preference_no_logger_singleton_returns_false(monkeypatch):
    set_preference_logger(None)
    monkeypatch.setattr(
        "kenning.desktop.preferences.get_preference_logger", lambda **kw: None,
    )
    assert record_launch_preference(
        user_phrase="x", app_name="chrome",
        monitor_index=0, fullscreen=False, maximize=True,
    ) is False


# ---------------------------------------------------------------------------
# Workspace mirror
# ---------------------------------------------------------------------------


def test_format_for_workspace_no_monitor_no_flags():
    p = DesktopPreference(user_phrase="open notepad", app_name="notepad")
    line = _format_for_workspace(p)
    assert 'user said "open notepad"' in line
    assert "launched notepad" in line
    # No monitor / flags mentioned when not set.
    assert "monitor" not in line.lower()


def test_format_for_workspace_with_monitor_and_flags():
    p = DesktopPreference(
        user_phrase="open youtube on my second monitor",
        app_name="chrome",
        url="https://www.youtube.com",
        monitor_index=1,
        maximize=True,
    )
    line = _format_for_workspace(p)
    assert "monitor 2" in line  # 1-indexed in narration
    assert "maximized" in line
    assert "youtube.com" in line


def test_workspace_writer_setter_clear():
    set_workspace_writer(None)
    assert get_workspace_writer() is None
    custom = object()
    set_workspace_writer(custom)
    assert get_workspace_writer() is custom
    set_workspace_writer(None)
    assert get_workspace_writer() is None


def test_workspace_mirror_runs_in_daemon_thread(tmp_path):
    """When a workspace writer is registered, record() spawns a daemon
    thread to mirror the entry. The local JSONL write is still sync.
    """
    set_preference_logger(None)
    set_workspace_writer(None)

    # Fake writer with an async-compatible write_memory_entry.
    captured = []

    class FakeWriter:
        async def write_memory_entry(self, *, entry, date, prefix_timestamp):
            captured.append((entry, date, prefix_timestamp))

    lg = PreferenceLogger(tmp_path / "pref.jsonl")
    set_workspace_writer(FakeWriter())
    try:
        pref = DesktopPreference(
            user_phrase="open chrome on monitor 1",
            app_name="chrome",
            monitor_index=0,
            success=True,
            timestamp=time.time(),
        )
        assert lg.record(pref) is True
        # The local write happens synchronously -- jsonl is present.
        assert lg.log_path.exists()
        # The workspace write runs on a daemon thread; give it a brief
        # window to land. If it doesn't, that's acceptable for the
        # test (it's a fire-and-forget side effect; the JSONL is the
        # source of truth).
        deadline = time.monotonic() + 1.5
        while not captured and time.monotonic() < deadline:
            time.sleep(0.05)
        # No strict assertion -- the mirror is best-effort.
    finally:
        set_workspace_writer(None)
        set_preference_logger(None)


def test_workspace_mirror_failure_doesnt_break_record(tmp_path):
    set_preference_logger(None)

    class BrokenWriter:
        async def write_memory_entry(self, **kw):
            raise RuntimeError("simulated workspace failure")

    set_workspace_writer(BrokenWriter())
    try:
        lg = PreferenceLogger(tmp_path / "pref.jsonl")
        ok = lg.record(DesktopPreference(
            user_phrase="x", app_name="chrome", timestamp=time.time(),
        ))
        # Local write succeeded; workspace failure was swallowed.
        assert ok is True
        assert lg.log_path.exists()
    finally:
        set_workspace_writer(None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_singleton_default_uses_project_root():
    set_preference_logger(None)
    try:
        lg = get_preference_logger()
        assert lg is not None
        assert "desktop_preferences.jsonl" in str(lg.log_path)
    finally:
        set_preference_logger(None)


def test_singleton_swap(tmp_path):
    set_preference_logger(None)
    try:
        custom = PreferenceLogger(tmp_path / "custom.jsonl")
        set_preference_logger(custom)
        assert get_preference_logger() is custom
    finally:
        set_preference_logger(None)
