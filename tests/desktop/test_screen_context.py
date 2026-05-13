"""Tests for ultron.desktop.screen_context."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest

from ultron.desktop.capture import Screenshot
from ultron.desktop.monitors import Monitor
from ultron.desktop.screen_context import (
    ScreenContextCache,
    ScreenContextSnapshot,
    build_screen_context,
    capture_and_cache,
    get_screen_context_cache,
    get_vlm_describe,
    set_screen_context_cache,
    set_vlm_describe,
)
from ultron.desktop.windows import WindowInfo


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _mon(idx=0, primary=True) -> Monitor:
    return Monitor(
        index=idx, name=f"D{idx}",
        x=0, y=0, width=1920, height=1080,
        work_x=0, work_y=0, work_width=1920, work_height=1040,
        is_primary=primary,
    )


def _win(title="Some App", proc="some.exe", mon=0, fg=False, hwnd=1) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd, title=title, class_name="C",
        process_name=proc, pid=0,
        rect=(0, 0, 800, 600),
        monitor_index=mon, is_minimized=False, is_foreground=fg,
    )


def _shot() -> Screenshot:
    return Screenshot(
        image_bytes=b"\x89PNG_DUMMY", monitor_index=0,
        width=1920, height=1080, timestamp=0.0,
        origin_x=0, origin_y=0,
    )


# ---------------------------------------------------------------------------
# ScreenContextSnapshot.render_for_llm
# ---------------------------------------------------------------------------


def test_render_for_llm_no_foreground():
    snap = ScreenContextSnapshot(
        timestamp=0.0, monitors=(), foreground=None,
        windows=(), ui_text=(), screenshot=None,
        vlm_description=None, elapsed_ms=0.0,
    )
    out = snap.render_for_llm()
    assert "Visual context" in out
    assert "No window is currently focused" in out
    assert "End visual context" in out


def test_render_for_llm_with_foreground_and_ui_text():
    snap = ScreenContextSnapshot(
        timestamp=0.0,
        monitors=(_mon(), _mon(idx=1, primary=False)),
        foreground=_win(title="main.py - Cursor", proc="Cursor.exe", mon=0, fg=True),
        windows=(_win(title="Chrome", proc="chrome.exe", mon=1),),
        ui_text=("File", "Edit", "View", "def hello():\n    pass"),
        screenshot=_shot(),
        vlm_description=None,
        elapsed_ms=42.0,
    )
    out = snap.render_for_llm()
    assert "Cursor.exe" in out
    assert "main.py - Cursor" in out
    assert "def hello" in out
    assert "Other visible apps: chrome.exe" in out


def test_render_for_llm_with_vlm_description():
    snap = ScreenContextSnapshot(
        timestamp=0.0, monitors=(), foreground=None, windows=(),
        ui_text=(),
        screenshot=_shot(),
        vlm_description="A code editor showing a Python function definition.",
        elapsed_ms=0.0,
    )
    out = snap.render_for_llm()
    assert "Visual description" in out
    assert "Python function definition" in out


def test_render_for_llm_truncates_long_ui_text():
    long = "x" * 500
    snap = ScreenContextSnapshot(
        timestamp=0.0, monitors=(), foreground=None, windows=(),
        ui_text=(long,),
        screenshot=None,
        vlm_description=None,
        elapsed_ms=0.0,
    )
    out = snap.render_for_llm()
    # Truncated to 197 + "..."
    assert "..." in out
    assert long not in out


def test_render_for_llm_caps_ui_text_count():
    items = tuple(f"item_{i}" for i in range(100))
    snap = ScreenContextSnapshot(
        timestamp=0.0, monitors=(), foreground=None, windows=(),
        ui_text=items, screenshot=None, vlm_description=None, elapsed_ms=0.0,
    )
    out = snap.render_for_llm(max_ui_text=5)
    # First 5 are present, 6th isn't.
    for i in range(5):
        assert f"item_{i}" in out
    assert "item_5" not in out


# ---------------------------------------------------------------------------
# build_screen_context with all components mocked out
# ---------------------------------------------------------------------------


def test_build_screen_context_no_capture_no_uia(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows",
        lambda: [_win(title="Chrome", proc="chrome.exe", hwnd=2)],
    )
    snap = build_screen_context(capture=False, include_uia=False)
    assert snap.monitors == (_mon(),)
    assert snap.foreground is not None
    assert snap.foreground.is_foreground
    assert snap.screenshot is None
    assert snap.ui_text == ()
    assert snap.vlm_description is None


def test_build_screen_context_with_capture(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True, mon=0),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.collect_window_text",
        lambda *a, **kw: ["UI text 1", "UI text 2"],
    )
    fake_cap = MagicMock()
    fake_cap.capture_monitor.return_value = _shot()
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_screen_capture", lambda: fake_cap,
    )
    snap = build_screen_context(capture=True, include_uia=True)
    assert snap.screenshot is not None
    assert snap.ui_text == ("UI text 1", "UI text 2")
    fake_cap.capture_monitor.assert_called_once_with(0)


def test_build_screen_context_handles_uia_failure(monkeypatch):
    """collect_window_text raising mustn't abort the whole snapshot."""
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )

    def boom(*a, **kw):
        raise RuntimeError("simulated UIA failure")

    monkeypatch.setattr(
        "ultron.desktop.screen_context.collect_window_text", boom,
    )
    snap = build_screen_context(capture=False, include_uia=True)
    # ui_text is empty but snapshot still assembled.
    assert snap.ui_text == ()
    assert snap.foreground is not None


def test_build_screen_context_handles_capture_failure(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True, mon=0),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )
    fake_cap = MagicMock()
    fake_cap.capture_monitor.side_effect = RuntimeError("simulated capture failure")
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_screen_capture", lambda: fake_cap,
    )
    snap = build_screen_context(capture=True, include_uia=False)
    assert snap.screenshot is None


def test_build_screen_context_handles_window_enum_failure(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window", lambda: None,
    )

    def boom():
        raise RuntimeError("simulated enum failure")

    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", boom,
    )
    snap = build_screen_context(capture=False, include_uia=False)
    assert snap.windows == ()
    assert snap.foreground is None


def test_build_screen_context_caps_window_list(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window", lambda: None,
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows",
        lambda: [_win(hwnd=i, title=f"app_{i}", proc=f"app_{i}.exe") for i in range(50)],
    )
    snap = build_screen_context(capture=False, include_uia=False, window_list_cap=5)
    assert len(snap.windows) == 5


# ---------------------------------------------------------------------------
# VLM hook
# ---------------------------------------------------------------------------


def test_vlm_hook_starts_unset():
    set_vlm_describe(None)
    assert get_vlm_describe() is None


def test_vlm_hook_can_be_set_and_cleared():
    set_vlm_describe(None)
    try:
        def fake(img_bytes: bytes) -> str:
            return "test description"
        set_vlm_describe(fake)
        assert get_vlm_describe() is fake
        set_vlm_describe(None)
        assert get_vlm_describe() is None
    finally:
        set_vlm_describe(None)


def test_build_screen_context_includes_vlm_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )
    fake_cap = MagicMock()
    fake_cap.capture_monitor.return_value = _shot()
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_screen_capture", lambda: fake_cap,
    )

    set_vlm_describe(lambda img: "Test VLM description")
    try:
        snap = build_screen_context(
            capture=True, include_uia=False, include_vlm=True,
        )
        assert snap.vlm_description == "Test VLM description"
    finally:
        set_vlm_describe(None)


def test_build_screen_context_vlm_disabled_by_default(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )
    fake_cap = MagicMock()
    fake_cap.capture_monitor.return_value = _shot()
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_screen_capture", lambda: fake_cap,
    )
    vlm_calls = []

    def vlm(img):
        vlm_calls.append(img)
        return "should not be called"

    set_vlm_describe(vlm)
    try:
        snap = build_screen_context(capture=True, include_vlm=False)
        assert snap.vlm_description is None
        assert vlm_calls == []
    finally:
        set_vlm_describe(None)


def test_build_screen_context_vlm_exception_handled(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [_mon()],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window",
        lambda: _win(fg=True),
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )
    fake_cap = MagicMock()
    fake_cap.capture_monitor.return_value = _shot()
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_screen_capture", lambda: fake_cap,
    )

    def boom(img):
        raise RuntimeError("simulated VLM failure")

    set_vlm_describe(boom)
    try:
        snap = build_screen_context(capture=True, include_vlm=True)
        assert snap.vlm_description is None  # fail-open
    finally:
        set_vlm_describe(None)


# ---------------------------------------------------------------------------
# ScreenContextCache
# ---------------------------------------------------------------------------


def test_cache_stores_and_retrieves():
    cache = ScreenContextCache(ring_size=3)
    snap = ScreenContextSnapshot(
        timestamp=time.time(), monitors=(), foreground=None,
        windows=(), ui_text=(), screenshot=None,
        vlm_description=None, elapsed_ms=0.0,
    )
    cache.store(snap)
    assert cache.size == 1
    assert cache.latest() is snap


def test_cache_evicts_old_entries():
    cache = ScreenContextCache(ring_size=2)
    for i in range(5):
        cache.store(ScreenContextSnapshot(
            timestamp=float(i), monitors=(), foreground=None,
            windows=(), ui_text=(), screenshot=None,
            vlm_description=None, elapsed_ms=0.0,
        ))
    assert cache.size == 2
    # Newest first
    snaps = cache.all()
    assert snaps[-1].timestamp == 4.0


def test_cache_latest_fresh_respects_max_age():
    cache = ScreenContextCache(ring_size=3, max_age_seconds=0.05)
    old = ScreenContextSnapshot(
        timestamp=time.time() - 1.0,  # 1 s ago
        monitors=(), foreground=None, windows=(), ui_text=(),
        screenshot=None, vlm_description=None, elapsed_ms=0.0,
    )
    cache.store(old)
    assert cache.latest() is old  # latest ignores age
    assert cache.latest_fresh() is None  # but latest_fresh respects max_age


def test_cache_clear():
    cache = ScreenContextCache()
    cache.store(ScreenContextSnapshot(
        timestamp=time.time(), monitors=(), foreground=None,
        windows=(), ui_text=(), screenshot=None,
        vlm_description=None, elapsed_ms=0.0,
    ))
    cache.clear()
    assert cache.size == 0
    assert cache.latest() is None


def test_singleton_cache_swap():
    set_screen_context_cache(None)
    try:
        a = get_screen_context_cache()
        b = get_screen_context_cache()
        assert a is b
        custom = ScreenContextCache()
        set_screen_context_cache(custom)
        assert get_screen_context_cache() is custom
    finally:
        set_screen_context_cache(None)


# ---------------------------------------------------------------------------
# capture_and_cache convenience
# ---------------------------------------------------------------------------


def test_capture_and_cache_stores_snapshot(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_monitors", lambda: [],
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.get_foreground_window", lambda: None,
    )
    monkeypatch.setattr(
        "ultron.desktop.screen_context.enumerate_windows", lambda: [],
    )
    set_screen_context_cache(ScreenContextCache())
    try:
        snap = capture_and_cache(capture=False, include_uia=False)
        cache = get_screen_context_cache()
        assert cache.size == 1
        assert cache.latest() is snap
    finally:
        set_screen_context_cache(None)


# ---------------------------------------------------------------------------
# Live integration (Windows only)
# ---------------------------------------------------------------------------


pytestmark_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only (full screen-context assembly)",
)


@pytestmark_windows
def test_build_screen_context_live_succeeds():
    snap = build_screen_context(capture=True, include_uia=True, include_vlm=False)
    assert isinstance(snap, ScreenContextSnapshot)
    assert snap.elapsed_ms > 0
    # On a live desktop session there should be at least one monitor.
    assert len(snap.monitors) >= 1


@pytestmark_windows
def test_render_for_llm_live_produces_readable_output():
    snap = build_screen_context(capture=False, include_uia=True, include_vlm=False)
    out = snap.render_for_llm()
    assert "Visual context" in out
    assert "End visual context" in out
