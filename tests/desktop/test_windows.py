"""Tests for ultron.desktop.windows."""

from __future__ import annotations

import sys

import pytest

from ultron.desktop.monitors import Monitor
from ultron.desktop.windows import (
    WindowInfo,
    _monitor_index_for_rect,
    enumerate_windows,
    find_window,
    get_foreground_window,
)


# ---------------------------------------------------------------------------
# WindowInfo dataclass shape
# ---------------------------------------------------------------------------


def test_window_info_helpers():
    w = WindowInfo(
        hwnd=12345, title="My App", class_name="Cls",
        process_name="app.exe", pid=999,
        rect=(100, 200, 300, 500),
        monitor_index=0, is_minimized=False, is_foreground=True,
    )
    assert w.width == 200
    assert w.height == 300
    assert w.center == (200, 350)


def test_window_info_handles_inverted_rect():
    """Rects from minimized windows can have right<left. width/height clamp to 0."""
    w = WindowInfo(
        hwnd=1, title="t", class_name="c", process_name="p", pid=1,
        rect=(500, 500, 100, 100),
        monitor_index=None, is_minimized=True, is_foreground=False,
    )
    assert w.width == 0
    assert w.height == 0


# ---------------------------------------------------------------------------
# _monitor_index_for_rect logic
# ---------------------------------------------------------------------------


def _three_mons() -> list[Monitor]:
    return [
        Monitor(  # 0 = primary, (0,0)..(2048,1152)
            index=0, name="D1",
            x=0, y=0, width=2048, height=1152,
            work_x=0, work_y=0, work_width=2048, work_height=1112,
            is_primary=True,
        ),
        Monitor(  # 1 = left, (-1920,186)..(0,1266)
            index=1, name="D3",
            x=-1920, y=186, width=1920, height=1080,
            work_x=-1920, work_y=186, work_width=1920, work_height=1040,
            is_primary=False,
        ),
        Monitor(  # 2 = right, (2560,106)..(4480,1186)
            index=2, name="D2",
            x=2560, y=106, width=1920, height=1080,
            work_x=2560, work_y=106, work_width=1920, work_height=1040,
            is_primary=False,
        ),
    ]


def test_monitor_index_for_rect_fully_inside_primary():
    mons = _three_mons()
    assert _monitor_index_for_rect((100, 100, 500, 500), mons) == 0


def test_monitor_index_for_rect_left_monitor():
    mons = _three_mons()
    assert _monitor_index_for_rect((-1500, 300, -100, 800), mons) == 1


def test_monitor_index_for_rect_right_monitor():
    mons = _three_mons()
    assert _monitor_index_for_rect((3000, 200, 4000, 800), mons) == 2


def test_monitor_index_for_rect_straddles_picks_greatest_overlap():
    mons = _three_mons()
    # Window straddles primary (mostly) and right monitor (a sliver).
    # Primary overlap: x ∈ (1000..2048) = 1048 wide × y 100..500 = 400 tall = 419200
    # Right overlap:   x ∈ (2560..3100) = 540  wide × y 100..500 = 400 tall = 216000  (no — y on right starts at 106)
    # Right overlap actually: x∈(2560..3100)=540 × y∈(106..500)=394 = 212760
    # So primary wins.
    assert _monitor_index_for_rect((1000, 100, 3100, 500), mons) == 0


def test_monitor_index_for_rect_no_overlap_returns_none():
    mons = _three_mons()
    # Above all monitors
    assert _monitor_index_for_rect((100, -1000, 500, -500), mons) is None


def test_monitor_index_for_rect_degenerate_rect_returns_none():
    mons = _three_mons()
    assert _monitor_index_for_rect((100, 100, 100, 100), mons) is None
    assert _monitor_index_for_rect((500, 500, 400, 400), mons) is None


def test_monitor_index_for_rect_empty_monitors():
    assert _monitor_index_for_rect((0, 0, 100, 100), []) is None


# ---------------------------------------------------------------------------
# find_window scoring with synthetic candidate list
# ---------------------------------------------------------------------------


def _mk(title, proc, *, fg=False, mon=0, hwnd=0):
    return WindowInfo(
        hwnd=hwnd or hash((title, proc)) & 0xFFFFFFFF,
        title=title,
        class_name="Cls",
        process_name=proc,
        pid=0,
        rect=(0, 0, 100, 100),
        monitor_index=mon,
        is_minimized=False,
        is_foreground=fg,
    )


def test_find_window_substring_match(monkeypatch):
    candidates = [
        _mk("Cursor - main.py", "Cursor.exe"),
        _mk("Discord", "Discord.exe"),
    ]
    monkeypatch.setattr("ultron.desktop.windows.enumerate_windows", lambda: candidates)
    w = find_window("cursor")
    assert w is not None
    assert w.process_name == "Cursor.exe"


def test_find_window_by_process_name(monkeypatch):
    candidates = [
        _mk("My Document - Word", "WINWORD.EXE"),
    ]
    monkeypatch.setattr("ultron.desktop.windows.enumerate_windows", lambda: candidates)
    w = find_window("winword")
    assert w is not None
    assert w.process_name == "WINWORD.EXE"


def test_find_window_exact_title_outranks_substring(monkeypatch):
    candidates = [
        _mk("My Project - Cursor", "Cursor.exe"),
        _mk("cursor", "Cursor.exe"),  # exact-match (case-insensitive)
    ]
    monkeypatch.setattr("ultron.desktop.windows.enumerate_windows", lambda: candidates)
    w = find_window("cursor")
    assert w is not None
    # exact title match (after lower()) ranks ahead of partial title
    assert w.title == "cursor"


def test_find_window_foreground_breaks_tie(monkeypatch):
    candidates = [
        _mk("chrome.exe", "chrome.exe", fg=False, hwnd=1),
        _mk("chrome.exe", "chrome.exe", fg=True, hwnd=2),
    ]
    monkeypatch.setattr("ultron.desktop.windows.enumerate_windows", lambda: candidates)
    w = find_window("chrome", prefer_foreground=True)
    assert w.is_foreground


def test_find_window_monitor_preference_breaks_tie(monkeypatch):
    candidates = [
        _mk("chrome - tab 1", "chrome.exe", mon=0, hwnd=1),
        _mk("chrome - tab 2", "chrome.exe", mon=2, hwnd=2),
    ]
    monkeypatch.setattr("ultron.desktop.windows.enumerate_windows", lambda: candidates)
    w = find_window("chrome", prefer_monitor=2)
    assert w.monitor_index == 2


def test_find_window_empty_query(monkeypatch):
    monkeypatch.setattr("ultron.desktop.windows.enumerate_windows", lambda: [])
    assert find_window("") is None
    assert find_window("   ") is None


def test_find_window_no_match(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.windows.enumerate_windows",
        lambda: [_mk("Cursor", "Cursor.exe")],
    )
    assert find_window("nonexistent") is None


def test_find_window_disable_process_match(monkeypatch):
    candidates = [_mk("My Document", "WINWORD.EXE")]
    monkeypatch.setattr(
        "ultron.desktop.windows.enumerate_windows", lambda: candidates,
    )
    # With by_process=False, "winword" doesn't match title.
    assert find_window("winword", by_process=False) is None
    # ... but matches when by_process=True (the default).
    assert find_window("winword", by_process=True) is not None


# ---------------------------------------------------------------------------
# Live integration (Windows only)
# ---------------------------------------------------------------------------


pytestmark_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only (pywin32 window enumeration)",
)


@pytestmark_windows
def test_enumerate_windows_live_returns_some():
    wins = enumerate_windows()
    assert len(wins) >= 1, "expected at least one visible window"


@pytestmark_windows
def test_enumerate_windows_live_all_have_titles_by_default():
    wins = enumerate_windows()
    assert all(w.title.strip() for w in wins), "require_title=True drops empty"


@pytestmark_windows
def test_enumerate_windows_live_monitor_indices_valid():
    from ultron.desktop.monitors import enumerate_monitors

    mon_count = len(enumerate_monitors())
    if mon_count == 0:
        pytest.skip("no monitors detected")
    wins = enumerate_windows()
    for w in wins:
        if w.monitor_index is not None:
            assert 0 <= w.monitor_index < mon_count


@pytestmark_windows
def test_get_foreground_window_live():
    fg = get_foreground_window()
    # In an interactive session there's always SOME foreground window; in
    # weird CI states there may not be. Skip if so.
    if fg is None:
        pytest.skip("no foreground window in current session")
    assert fg.is_foreground
    assert fg.hwnd > 0
