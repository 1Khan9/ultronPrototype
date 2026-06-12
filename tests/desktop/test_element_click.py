"""Tests for kenning.desktop.element_click (catalog 08 T3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

from kenning.desktop.element_click import (
    CLICKABLE_TYPES,
    DEFAULT_MAX_ELEMENTS_PER_WINDOW,
    DEFAULT_MAX_GLOBAL_WINDOWS,
    ClickResult,
    TextMatch,
    UIElementMatch,
    _center_of,
    _resolve_allowed_types,
    click_element_by_name,
    find_elements_by_name,
    find_text_in_window,
)
from kenning.desktop.windows import WindowInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wi(
    *,
    hwnd: int = 1,
    title: str = "Notepad",
    class_name: str = "Notepad",
    process: str = "notepad.exe",
) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd, title=title, class_name=class_name,
        process_name=process, pid=42,
        rect=(0, 0, 600, 400), monitor_index=0,
        is_minimized=False, is_foreground=False,
    )


class _Rect:
    def __init__(self, l: int, t: int, r: int, b: int) -> None:
        self.left = l
        self.top = t
        self.right = r
        self.bottom = b


class _ElInfo:
    def __init__(self, *, control_type: str = "", automation_id: str = "") -> None:
        self.control_type = control_type
        self.automation_id = automation_id


class _Node:
    """pywinauto-style descendant stand-in."""

    def __init__(
        self,
        *,
        text: str = "",
        control_type: str = "",
        automation_id: str = "",
        enabled: bool = True,
        rect: tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> None:
        self._text = text
        self.element_info = _ElInfo(
            control_type=control_type, automation_id=automation_id,
        )
        self._enabled = enabled
        self._rect = _Rect(*rect)

    def window_text(self) -> str:
        return self._text

    def is_enabled(self) -> bool:
        return self._enabled

    def rectangle(self) -> _Rect:
        return self._rect


class _Spec:
    def __init__(self, descendants: list[_Node]) -> None:
        self._descendants = list(descendants)

    def descendants(self) -> list[_Node]:
        return list(self._descendants)


def _patch_windows_and_specs(
    monkeypatch,
    pairs: list[tuple[WindowInfo, _Spec]],
) -> None:
    """Wire enumerate_windows + _connect_to_window for cross-window tests."""
    windows = [w for w, _ in pairs]
    spec_by_hwnd = {w.hwnd: s for w, s in pairs}

    monkeypatch.setattr(
        "kenning.desktop.element_click.enumerate_windows",
        lambda **kw: list(windows),
    )
    monkeypatch.setattr(
        "kenning.desktop.element_click._connect_to_window",
        lambda hwnd: spec_by_hwnd.get(int(hwnd)),
    )


# ---------------------------------------------------------------------------
# Constants + helpers
# ---------------------------------------------------------------------------


def test_clickable_types_includes_button_hyperlink_menu():
    assert "Button" in CLICKABLE_TYPES
    assert "Hyperlink" in CLICKABLE_TYPES
    assert "MenuItem" in CLICKABLE_TYPES
    assert "TabItem" in CLICKABLE_TYPES
    assert "CheckBox" in CLICKABLE_TYPES


def test_default_caps_set():
    assert DEFAULT_MAX_GLOBAL_WINDOWS >= 1
    assert DEFAULT_MAX_ELEMENTS_PER_WINDOW >= 50


def test_center_of_rect():
    assert _center_of((10, 20, 30, 40)) == (20, 30)


def test_resolve_allowed_types_none_returns_default():
    out = _resolve_allowed_types(None)
    assert "button" in out
    assert "hyperlink" in out


def test_resolve_allowed_types_empty_returns_default():
    out = _resolve_allowed_types([])
    assert "button" in out


def test_resolve_allowed_types_normalises_case():
    out = _resolve_allowed_types(["Button", "HYPERLINK"])
    assert out == {"button", "hyperlink"}


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


def test_ui_element_match_is_frozen():
    win = _wi()
    m = UIElementMatch(
        name="Save", control_type="Button", automation_id="",
        enabled=True, rect=(0, 0, 10, 10), center=(5, 5), window=win,
    )
    with pytest.raises(Exception):
        m.name = "Cancel"


def test_text_match_is_frozen():
    win = _wi()
    t = TextMatch(
        name="hello", control_type="Text",
        rect=(0, 0, 10, 10), center=(5, 5), window=win,
    )
    with pytest.raises(Exception):
        t.name = "world"


def test_click_result_defaults():
    r = ClickResult(success=True)
    assert r.element_name == ""
    assert r.method == ""
    assert r.candidates == 0
    assert r.error is None


# ---------------------------------------------------------------------------
# find_elements_by_name
# ---------------------------------------------------------------------------


def test_find_elements_returns_empty_on_empty_name():
    assert find_elements_by_name("") == []
    assert find_elements_by_name("   ") == []


def test_find_elements_fail_open_on_enumerate_exception(monkeypatch):
    def _raise(**kw):
        raise RuntimeError("enum failure")

    monkeypatch.setattr(
        "kenning.desktop.element_click.enumerate_windows", _raise,
    )
    assert find_elements_by_name("Save") == []


def test_find_elements_returns_empty_when_no_match(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="Cancel", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    assert find_elements_by_name("Save") == []


def test_find_elements_substring_match(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(text="Save and Close", control_type="Button", rect=(0, 0, 100, 30)),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("save")
    assert len(matches) == 1
    assert matches[0].name == "Save and Close"
    assert matches[0].center == (50, 15)
    assert matches[0].is_exact is False


def test_find_elements_exact_only(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(text="Save and Close", control_type="Button"),
        _Node(text="Save", control_type="Button"),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("Save", exact=True)
    assert len(matches) == 1
    assert matches[0].name == "Save"
    assert matches[0].is_exact is True


def test_find_elements_exact_match_promoted_over_substring(monkeypatch):
    win = _wi()
    # Substring match listed first in tree-walk order, exact match later.
    spec = _Spec([
        _Node(text="Save and Close", control_type="Button"),
        _Node(text="Save", control_type="Button"),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("Save", exact=False)
    assert len(matches) == 2
    # Exact match must come first despite later tree-walk position.
    assert matches[0].name == "Save"
    assert matches[0].is_exact is True
    assert matches[1].name == "Save and Close"
    assert matches[1].is_exact is False


def test_find_elements_case_insensitive_by_default(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="SUBMIT", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("submit")
    assert len(matches) == 1


def test_find_elements_filters_by_control_type(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(text="File", control_type="MenuItem"),
        _Node(text="File", control_type="TabItem"),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name(
        "File", control_types=["MenuItem"],
    )
    assert len(matches) == 1
    assert matches[0].control_type == "MenuItem"


def test_find_elements_drops_disabled_by_default(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(text="Save", control_type="Button", enabled=False),
        _Node(text="Save", control_type="Button", enabled=True),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("Save")
    assert len(matches) == 1
    assert matches[0].enabled is True


def test_find_elements_keeps_disabled_when_requested(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(text="Save", control_type="Button", enabled=False),
        _Node(text="Save", control_type="Button", enabled=True),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("Save", enabled_only=False)
    assert len(matches) == 2


def test_find_elements_window_title_filter(monkeypatch):
    chrome = _wi(hwnd=1, title="Browser - Chrome")
    notepad = _wi(hwnd=2, title="Notepad - file.txt")
    chrome_spec = _Spec([_Node(text="OK", control_type="Button")])
    notepad_spec = _Spec([_Node(text="OK", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(chrome, chrome_spec), (notepad, notepad_spec)])
    matches = find_elements_by_name("OK", window_title="notepad")
    assert len(matches) == 1
    assert matches[0].window.title == "Notepad - file.txt"


def test_find_elements_skips_broken_descendant(monkeypatch):
    class _Bad(_Node):
        def window_text(self):
            raise RuntimeError("simulated UIA failure")

    win = _wi()
    spec = _Spec([
        _Bad(control_type="Button"),
        _Node(text="OK", control_type="Button"),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("OK")
    names = {m.name for m in matches}
    assert "OK" in names


def test_find_elements_respects_per_window_cap(monkeypatch):
    win = _wi()
    descendants = [
        _Node(text=f"OK_{i}", control_type="Button")
        for i in range(50)
    ]
    spec = _Spec(descendants)
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_elements_by_name("OK", max_elements_per_window=5)
    # Cap visits at 5, so at most 5 matches.
    assert len(matches) <= 5


def test_find_elements_respects_max_windows_when_no_title(monkeypatch):
    pairs = []
    for i in range(20):
        w = _wi(hwnd=i, title=f"Window {i}")
        s = _Spec([_Node(text="OK", control_type="Button")])
        pairs.append((w, s))
    _patch_windows_and_specs(monkeypatch, pairs)
    matches = find_elements_by_name("OK", max_windows=3)
    assert len(matches) == 3


def test_find_elements_returns_empty_when_pywinauto_returns_none(monkeypatch):
    win = _wi()
    monkeypatch.setattr(
        "kenning.desktop.element_click.enumerate_windows",
        lambda **kw: [win],
    )
    monkeypatch.setattr(
        "kenning.desktop.element_click._connect_to_window",
        lambda hwnd: None,
    )
    assert find_elements_by_name("OK") == []


# ---------------------------------------------------------------------------
# click_element_by_name
# ---------------------------------------------------------------------------


@dataclass
class _FakeControllerResult:
    success: bool
    action: str = "click"
    error: Optional[str] = None


class _RecordingController:
    def __init__(self, *, success: bool = True, error: Optional[str] = None) -> None:
        self.calls: list[dict] = []
        self._success = success
        self._error = error

    def click(self, **kwargs) -> _FakeControllerResult:
        self.calls.append(dict(kwargs))
        return _FakeControllerResult(
            success=self._success, error=self._error,
        )


def test_click_element_no_match(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="Cancel", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    ctrl = _RecordingController()
    result = click_element_by_name("Save", controller=ctrl)
    assert result.success is False
    assert result.candidates == 0
    assert "no enabled element" in (result.error or "")
    assert ctrl.calls == []


def test_click_element_picks_first_candidate_and_clicks_via_controller(monkeypatch):
    win = _wi(hwnd=42, title="Notepad")
    spec = _Spec([
        _Node(text="Save", control_type="Button", rect=(20, 40, 120, 80)),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    ctrl = _RecordingController(success=True)
    result = click_element_by_name(
        "Save", controller=ctrl, user_text="save my document",
    )
    assert result.success is True
    assert result.method == "controller_click"
    assert result.element_name == "Save"
    assert result.center == (70, 60)
    assert result.candidates == 1
    assert result.is_exact is True
    assert ctrl.calls[0]["x"] == 70
    assert ctrl.calls[0]["y"] == 60
    assert ctrl.calls[0]["user_text"] == "save my document"


def test_click_element_propagates_controller_failure(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="Submit", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    ctrl = _RecordingController(success=False, error="safety: cap-3 verb-click")
    result = click_element_by_name("Submit", controller=ctrl)
    assert result.success is False
    assert result.method == "controller_click"
    assert "cap-3" in (result.error or "")


def test_click_element_returns_failure_when_controller_raises(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="OK", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])

    class _Broken:
        def click(self, **kwargs):
            raise RuntimeError("controller blew up")

    result = click_element_by_name("OK", controller=_Broken())
    assert result.success is False
    assert "blew up" in (result.error or "")


def test_click_element_resolves_default_controller(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="OK", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    captured: list[_RecordingController] = []

    def _get_controller():
        c = _RecordingController(success=True)
        captured.append(c)
        return c

    monkeypatch.setattr(
        "kenning.desktop.input_control.get_input_controller", _get_controller,
    )
    result = click_element_by_name("OK")
    assert result.success is True
    assert len(captured) == 1
    assert captured[0].calls != []


def test_click_element_controller_resolution_failure(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="OK", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])

    def _boom():
        raise RuntimeError("singleton broken")

    monkeypatch.setattr(
        "kenning.desktop.input_control.get_input_controller", _boom,
    )
    result = click_element_by_name("OK")
    assert result.success is False
    assert "input controller unavailable" in (result.error or "")


def test_click_element_control_type_filter_narrows(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(text="File", control_type="MenuItem", rect=(0, 0, 50, 20)),
        _Node(text="File", control_type="TabItem", rect=(100, 0, 200, 20)),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    ctrl = _RecordingController()
    result = click_element_by_name(
        "File", control_type="MenuItem", controller=ctrl,
    )
    assert result.success is True
    assert result.control_type == "MenuItem"
    assert ctrl.calls[0]["x"] == 25  # centre of (0,0,50,20)


def test_click_element_exact_only_no_match(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="Save All", control_type="Button")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    ctrl = _RecordingController()
    result = click_element_by_name("Save", exact=True, controller=ctrl)
    assert result.success is False
    assert ctrl.calls == []


# ---------------------------------------------------------------------------
# find_text_in_window
# ---------------------------------------------------------------------------


def test_find_text_empty_needle_returns_empty():
    assert find_text_in_window("") == []


def test_find_text_no_match_returns_empty(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="something else", control_type="Text")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    assert find_text_in_window("missing") == []


def test_find_text_substring_match(monkeypatch):
    win = _wi()
    spec = _Spec([
        _Node(
            text="Welcome to kenning",
            control_type="Text",
            rect=(0, 0, 200, 30),
        ),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_text_in_window("welcome")
    assert len(matches) == 1
    assert matches[0].name == "Welcome to kenning"
    assert matches[0].center == (100, 15)


def test_find_text_case_sensitive_when_disabled(monkeypatch):
    win = _wi()
    spec = _Spec([_Node(text="Welcome", control_type="Text")])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_text_in_window("welcome", case_insensitive=False)
    assert matches == []


def test_find_text_window_title_filter(monkeypatch):
    chrome = _wi(hwnd=1, title="Browser - Chrome")
    notepad = _wi(hwnd=2, title="Notepad")
    chrome_spec = _Spec([_Node(text="Find me", control_type="Text")])
    notepad_spec = _Spec([_Node(text="Find me", control_type="Text")])
    _patch_windows_and_specs(monkeypatch, [(chrome, chrome_spec), (notepad, notepad_spec)])
    matches = find_text_in_window("find", window_title="notepad")
    assert len(matches) == 1
    assert matches[0].window.title == "Notepad"


def test_find_text_returns_empty_on_enumerate_exception(monkeypatch):
    def _raise(**kw):
        raise RuntimeError("simulated")

    monkeypatch.setattr(
        "kenning.desktop.element_click.enumerate_windows", _raise,
    )
    assert find_text_in_window("x") == []


def test_find_text_respects_per_window_cap(monkeypatch):
    win = _wi()
    descendants = [
        _Node(text=f"hit {i}", control_type="Text") for i in range(20)
    ]
    spec = _Spec(descendants)
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_text_in_window("hit", max_elements_per_window=5)
    assert len(matches) <= 5


def test_find_text_skips_broken_descendant(monkeypatch):
    class _Bad(_Node):
        def window_text(self):
            raise RuntimeError("simulated UIA failure")

    win = _wi()
    spec = _Spec([
        _Bad(control_type="Text"),
        _Node(text="visible text", control_type="Text"),
    ])
    _patch_windows_and_specs(monkeypatch, [(win, spec)])
    matches = find_text_in_window("visible")
    assert len(matches) == 1
