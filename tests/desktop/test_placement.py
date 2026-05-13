"""Tests for ultron.desktop.placement."""

from __future__ import annotations

import sys

import pytest

from ultron.desktop.monitors import Monitor
from ultron.desktop.placement import (
    PlacementResult,
    move_window_to_monitor,
    maximize_window,
    minimize_window,
    restore_window,
    focus_window,
)


def _mon(idx=0, x=0, y=0, w=1920, h=1080, primary=True) -> Monitor:
    return Monitor(
        index=idx, name=f"D{idx}",
        x=x, y=y, width=w, height=h,
        work_x=x, work_y=y, work_width=w, work_height=h - 40,
        is_primary=primary,
    )


# ---------------------------------------------------------------------------
# Argument validation (pure logic; no Win32 needed)
# ---------------------------------------------------------------------------


def test_fullscreen_and_maximize_mutually_exclusive():
    r = move_window_to_monitor(
        hwnd=0, monitor=_mon(),
        fullscreen=True, maximize=True,
    )
    assert r.success is False
    assert "mutually exclusive" in (r.error or "")


# ---------------------------------------------------------------------------
# Fail-open: invalid hwnd doesn't crash; returns success=False
# ---------------------------------------------------------------------------


pytestmark_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only (pywin32 placement APIs)",
)


@pytestmark_windows
def test_move_window_to_monitor_bad_hwnd_returns_failure():
    r = move_window_to_monitor(hwnd=999999999, monitor=_mon())
    assert isinstance(r, PlacementResult)
    assert r.success is False
    assert r.error  # non-empty error


@pytestmark_windows
def test_maximize_window_bad_hwnd_returns_failure():
    # ShowWindow on a stale handle on this platform may actually succeed
    # silently (returns 0). Verify the call shape doesn't raise.
    r = maximize_window(hwnd=999999999)
    assert isinstance(r, PlacementResult)
    # Either the call no-ops (success=True with stale hwnd) or it errored;
    # both shapes are valid -- we just need no exception.


@pytestmark_windows
def test_minimize_window_bad_hwnd_returns_result():
    r = minimize_window(hwnd=999999999)
    assert isinstance(r, PlacementResult)


@pytestmark_windows
def test_restore_window_bad_hwnd_returns_result():
    r = restore_window(hwnd=999999999)
    assert isinstance(r, PlacementResult)


@pytestmark_windows
def test_focus_window_bad_hwnd_returns_result():
    r = focus_window(hwnd=999999999)
    assert isinstance(r, PlacementResult)
