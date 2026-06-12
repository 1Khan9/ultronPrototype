"""Tests for kenning.desktop.capture."""

from __future__ import annotations

import sys

import pytest

from kenning.desktop.capture import (
    ScreenCapture,
    ScreenCaptureError,
    Screenshot,
    _bgra_to_png_bytes,
    get_screen_capture,
    set_screen_capture,
)
from kenning.safety.taint import TaintTracker, set_taint_tracker


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_bgra_to_png_bytes_round_trip():
    # 2x2 BGRA buffer (16 bytes). Each pixel: B, G, R, X.
    raw = bytes([
        255,   0,   0, 0,   # pixel (0,0): blue
          0, 255,   0, 0,   # pixel (1,0): green
          0,   0, 255, 0,   # pixel (0,1): red
        255, 255, 255, 0,   # pixel (1,1): white
    ])
    png = _bgra_to_png_bytes(raw, 2, 2)
    assert png.startswith(b"\x89PNG\r\n\x1a\n"), "PNG magic header"
    assert len(png) > 16, "PNG should be larger than raw input"


def test_screenshot_is_frozen():
    s = Screenshot(
        image_bytes=b"", monitor_index=0,
        width=10, height=10, timestamp=0.0,
        origin_x=0, origin_y=0,
    )
    with pytest.raises(Exception):
        s.width = 100


# ---------------------------------------------------------------------------
# ScreenCapture lifecycle
# ---------------------------------------------------------------------------


def test_screen_capture_closed_flag():
    cap = ScreenCapture()
    assert cap.closed is False
    cap.close()
    assert cap.closed is True


def test_screen_capture_close_is_idempotent():
    cap = ScreenCapture()
    cap.close()
    cap.close()  # second call must not raise
    assert cap.closed is True


def test_screen_capture_raises_after_close():
    cap = ScreenCapture()
    cap.close()
    with pytest.raises(ScreenCaptureError):
        cap._sct()


def test_capture_region_rejects_nonpositive_size():
    cap = ScreenCapture(record_taint=False)
    assert cap.capture_region(x=0, y=0, width=0, height=100) is None
    assert cap.capture_region(x=0, y=0, width=100, height=0) is None
    assert cap.capture_region(x=0, y=0, width=-10, height=100) is None


def test_capture_monitor_out_of_range_returns_none(monkeypatch):
    monkeypatch.setattr(
        "kenning.desktop.capture.enumerate_monitors", lambda: [],
    )
    cap = ScreenCapture(record_taint=False)
    assert cap.capture_monitor(0) is None
    assert cap.capture_monitor(99) is None


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


def test_get_screen_capture_singleton_caches():
    set_screen_capture(None)
    try:
        a = get_screen_capture()
        b = get_screen_capture()
        assert a is b
    finally:
        set_screen_capture(None)


def test_set_screen_capture_swaps():
    custom = ScreenCapture(record_taint=False)
    try:
        set_screen_capture(custom)
        assert get_screen_capture() is custom
    finally:
        set_screen_capture(None)


# ---------------------------------------------------------------------------
# Taint integration (no live capture needed — exercises the import path)
# ---------------------------------------------------------------------------


def test_record_taint_safe_records_under_screen_context_capability():
    """The capture pipeline must stamp bytes as capability=screen_context
    so the safety validator's outflow gate can match exfil attempts.
    """
    from kenning.desktop.capture import _record_taint_safe

    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        _record_taint_safe(b"fake_png_bytes_xyz")
        hit = tracker.has_taint(data=b"fake_png_bytes_xyz")
        assert hit is not None
        assert hit.capability == "screen_context"
    finally:
        set_taint_tracker(None)


def test_record_taint_safe_skips_empty():
    from kenning.desktop.capture import _record_taint_safe

    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        _record_taint_safe(b"")
        assert tracker.size == 0
    finally:
        set_taint_tracker(None)


def test_record_taint_safe_fail_open(monkeypatch):
    """A broken taint tracker must not break capture."""
    from kenning.desktop.capture import _record_taint_safe

    def boom():
        raise RuntimeError("taint module unavailable")

    monkeypatch.setattr("kenning.safety.taint.get_taint_tracker", boom)
    # Must not raise.
    _record_taint_safe(b"some bytes")


# ---------------------------------------------------------------------------
# Live integration (Windows + display)
# ---------------------------------------------------------------------------


pytestmark_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only (mss + Win32 desktop)",
)


@pytestmark_windows
def test_capture_monitor_live_returns_png():
    from kenning.desktop.monitors import enumerate_monitors

    mons = enumerate_monitors()
    if not mons:
        pytest.skip("no monitors detected (headless session?)")
    cap = ScreenCapture(record_taint=False)
    try:
        shot = cap.capture_monitor(0)
    finally:
        cap.close()
    assert shot is not None
    assert shot.image_bytes.startswith(b"\x89PNG"), "PNG header expected"
    assert shot.width == mons[0].width
    assert shot.height == mons[0].height
    assert shot.monitor_index == 0


@pytestmark_windows
def test_capture_all_monitors_live():
    from kenning.desktop.monitors import enumerate_monitors

    mons = enumerate_monitors()
    if not mons:
        pytest.skip("no monitors detected")
    cap = ScreenCapture(record_taint=False)
    try:
        shots = cap.capture_all_monitors()
    finally:
        cap.close()
    assert len(shots) == len(mons)
    for shot, mon in zip(shots, mons):
        assert shot.image_bytes.startswith(b"\x89PNG")
        assert shot.monitor_index == mon.index


@pytestmark_windows
def test_capture_records_taint_when_enabled():
    from kenning.desktop.monitors import enumerate_monitors

    if not enumerate_monitors():
        pytest.skip("no monitors detected")

    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        cap = ScreenCapture(record_taint=True)
        try:
            shot = cap.capture_monitor(0)
        finally:
            cap.close()
        assert shot is not None
        # Capture bytes must match a recent taint entry.
        hit = tracker.has_taint(data=shot.image_bytes)
        assert hit is not None
        assert hit.capability == "screen_context"
    finally:
        set_taint_tracker(None)


@pytestmark_windows
def test_capture_skips_taint_when_disabled():
    from kenning.desktop.monitors import enumerate_monitors

    if not enumerate_monitors():
        pytest.skip("no monitors detected")

    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        cap = ScreenCapture(record_taint=False)
        try:
            cap.capture_monitor(0)
        finally:
            cap.close()
        assert tracker.size == 0
    finally:
        set_taint_tracker(None)


# ---------------------------------------------------------------------------
# Catalog 09 T2: get_pixel_color probe
# ---------------------------------------------------------------------------


def test_get_pixel_color_passes_coords_to_pyautogui(monkeypatch):
    """The probe is a thin wrapper around pyautogui.pixel; coords are
    forwarded as integers and the RGB tuple is returned."""
    import types

    from kenning.desktop import capture as capture_mod
    fake = types.SimpleNamespace(pixel=lambda x, y: (10, 20, 30))
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    rgb = capture_mod.get_pixel_color(123, 456)
    assert rgb == (10, 20, 30)


def test_get_pixel_color_normalises_floats(monkeypatch):
    """pyautogui occasionally returns numpy-like floats; the probe
    coerces every channel to a plain Python int."""
    import types

    from kenning.desktop import capture as capture_mod
    fake = types.SimpleNamespace(pixel=lambda x, y: (255.0, 128.0, 0.0))
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    rgb = capture_mod.get_pixel_color(0, 0)
    assert rgb == (255, 128, 0)
    assert all(isinstance(c, int) for c in rgb)


def test_get_pixel_color_returns_none_on_exception(monkeypatch):
    """Fail-open: any exception from pyautogui yields None instead of
    propagating. The polling-loop caller simply continues."""
    import types

    from kenning.desktop import capture as capture_mod

    def _boom(x, y):
        raise RuntimeError("display gone")
    fake = types.SimpleNamespace(pixel=_boom)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.get_pixel_color(0, 0) is None


def test_get_pixel_color_returns_none_on_malformed_result(monkeypatch):
    """A non-tuple / wrong-length result is treated as failure."""
    import types

    from kenning.desktop import capture as capture_mod
    fake = types.SimpleNamespace(pixel=lambda x, y: (255,))  # too short
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.get_pixel_color(0, 0) is None


def test_get_pixel_color_returns_none_when_pyautogui_returns_none(monkeypatch):
    import types

    from kenning.desktop import capture as capture_mod
    fake = types.SimpleNamespace(pixel=lambda x, y: None)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.get_pixel_color(0, 0) is None


def test_get_pixel_color_does_not_record_taint(monkeypatch):
    """RGB tuples are ephemeral and never go through the taint tracker --
    only durable image bytes do."""
    import types

    from kenning.desktop import capture as capture_mod

    fake = types.SimpleNamespace(pixel=lambda x, y: (1, 2, 3))
    monkeypatch.setitem(sys.modules, "pyautogui", fake)

    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        for _ in range(5):
            capture_mod.get_pixel_color(0, 0)
        assert tracker.size == 0
    finally:
        set_taint_tracker(None)


# ---------------------------------------------------------------------------
# Catalog 09 T6: find_image_on_screen template matching
# ---------------------------------------------------------------------------


def _allow_path_resolver(monkeypatch):
    """Force the path resolver to return the input path unchanged."""
    from pathlib import Path

    class _Fake:
        def safe_realpath(self, raw):
            return Path(str(raw))

    monkeypatch.setattr(
        "kenning.safety.path_resolver.get_path_resolver", lambda: _Fake(),
    )


def _reject_path_resolver(monkeypatch):
    """Force the path resolver to reject all paths (simulates an evasion
    pattern or path traversal attempt)."""
    class _Fake:
        def safe_realpath(self, raw):
            return None

    monkeypatch.setattr(
        "kenning.safety.path_resolver.get_path_resolver", lambda: _Fake(),
    )


def test_find_image_returns_match_on_success(monkeypatch):
    """Happy path: pyautogui.locateOnScreen returns a Box-like tuple;
    we wrap it in TemplateMatch with computed centre."""
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    fake = types.SimpleNamespace(
        locateOnScreen=lambda path, **kw: (100, 200, 50, 40),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    match = capture_mod.find_image_on_screen("template.png")
    assert match is not None
    assert match.left == 100
    assert match.top == 200
    assert match.width == 50
    assert match.height == 40
    assert match.center_x == 125
    assert match.center_y == 220
    assert match.confidence == 0.8


def test_find_image_default_confidence_is_zero_point_eight(monkeypatch):
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    seen = {}

    def _fake(path, **kw):
        seen.update(kw)
        return (0, 0, 10, 10)

    fake = types.SimpleNamespace(locateOnScreen=_fake)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    capture_mod.find_image_on_screen("t.png")
    assert seen["confidence"] == 0.8


def test_find_image_custom_confidence_forwarded(monkeypatch):
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    seen = {}

    def _fake(path, **kw):
        seen.update(kw)
        return None  # treat as no-match

    fake = types.SimpleNamespace(locateOnScreen=_fake)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    capture_mod.find_image_on_screen("t.png", confidence=0.95)
    assert seen["confidence"] == 0.95


def test_find_image_region_forwarded(monkeypatch):
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    seen = {}

    def _fake(path, **kw):
        seen.update(kw)
        return None

    fake = types.SimpleNamespace(locateOnScreen=_fake)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    capture_mod.find_image_on_screen("t.png", region=(100, 200, 300, 400))
    assert seen["region"] == (100, 200, 300, 400)


def test_find_image_no_match_returns_none(monkeypatch):
    """pyautogui returning None (no match found) maps to None."""
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    fake = types.SimpleNamespace(locateOnScreen=lambda p, **kw: None)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.find_image_on_screen("missing.png") is None


def test_find_image_opencv_missing_returns_none(monkeypatch):
    """pyautogui.locateOnScreen raises when opencv-python is absent.
    The wrapper catches and returns None (fail-open contract)."""
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)

    def _boom(path, **kw):
        raise ImportError("opencv-python is required for confidence")

    fake = types.SimpleNamespace(locateOnScreen=_boom)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.find_image_on_screen("t.png") is None


def test_find_image_generic_exception_returns_none(monkeypatch):
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)

    def _boom(path, **kw):
        raise RuntimeError("display gone")

    fake = types.SimpleNamespace(locateOnScreen=_boom)
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.find_image_on_screen("t.png") is None


def test_find_image_rejects_empty_path():
    from kenning.desktop import capture as capture_mod
    assert capture_mod.find_image_on_screen("") is None


def test_find_image_rejects_non_string_path():
    from kenning.desktop import capture as capture_mod
    assert capture_mod.find_image_on_screen(None) is None  # type: ignore[arg-type]
    assert capture_mod.find_image_on_screen(42) is None  # type: ignore[arg-type]


def test_find_image_rejects_out_of_range_confidence(monkeypatch):
    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    # locateOnScreen must not be called; install a sentinel that would
    # fail if invoked.
    import types

    def _should_not_be_called(*a, **kw):
        raise AssertionError("locateOnScreen called despite invalid confidence")

    monkeypatch.setitem(
        sys.modules, "pyautogui",
        types.SimpleNamespace(locateOnScreen=_should_not_be_called),
    )
    assert capture_mod.find_image_on_screen("t.png", confidence=0.0) is None
    assert capture_mod.find_image_on_screen("t.png", confidence=-0.1) is None
    assert capture_mod.find_image_on_screen("t.png", confidence=1.5) is None


def test_find_image_rejects_malformed_region(monkeypatch):
    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    import types

    def _should_not_be_called(*a, **kw):
        raise AssertionError("locateOnScreen called despite bad region")

    monkeypatch.setitem(
        sys.modules, "pyautogui",
        types.SimpleNamespace(locateOnScreen=_should_not_be_called),
    )
    # too-short tuple
    assert capture_mod.find_image_on_screen("t.png", region=(1, 2)) is None  # type: ignore[arg-type]
    # non-positive width/height
    assert capture_mod.find_image_on_screen("t.png", region=(0, 0, 0, 100)) is None


def test_find_image_path_resolver_reject_returns_none(monkeypatch):
    """Path resolver returning None (evasion pattern, broken symlink,
    etc.) short-circuits before pyautogui is even imported."""
    import types

    from kenning.desktop import capture as capture_mod
    _reject_path_resolver(monkeypatch)

    def _should_not_be_called(*a, **kw):
        raise AssertionError("locateOnScreen called despite rejected path")

    monkeypatch.setitem(
        sys.modules, "pyautogui",
        types.SimpleNamespace(locateOnScreen=_should_not_be_called),
    )
    assert capture_mod.find_image_on_screen("evil/../../etc/passwd") is None


def test_find_image_malformed_box_returns_none(monkeypatch):
    """If locateOnScreen returns something we can't unpack into a box,
    we map it to None."""
    import types

    from kenning.desktop import capture as capture_mod
    _allow_path_resolver(monkeypatch)
    fake = types.SimpleNamespace(
        locateOnScreen=lambda p, **kw: "not a box",
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    assert capture_mod.find_image_on_screen("t.png") is None


def test_find_image_template_match_is_frozen():
    from kenning.desktop.capture import TemplateMatch

    m = TemplateMatch(
        left=0, top=0, width=10, height=10,
        center_x=5, center_y=5, confidence=0.8,
    )
    with pytest.raises(Exception):
        m.left = 100  # type: ignore[misc]
