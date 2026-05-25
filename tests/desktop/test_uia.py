"""Tests for ultron.desktop.uia."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from ultron.desktop.uia import (
    UIAActionResult,
    UIAElement,
    _resolve_hwnd,
    _validate_uia_action,
    click_element,
    collect_window_text,
    find_element,
    type_text_into_element,
)
from ultron.desktop.windows import WindowInfo


# ---------------------------------------------------------------------------
# Result dataclass shapes
# ---------------------------------------------------------------------------


def test_uia_element_defaults():
    e = UIAElement(name="OK")
    assert e.name == "OK"
    assert e.control_type == ""
    assert e.automation_id == ""
    assert e.rect == (0, 0, 0, 0)
    assert e.is_enabled is True
    assert e.is_visible is True


def test_uia_element_is_frozen():
    e = UIAElement(name="OK")
    with pytest.raises(Exception):
        e.name = "Modified"


def test_uia_action_result_defaults():
    r = UIAActionResult(success=True)
    assert r.success is True
    assert r.element_name == ""
    assert r.error is None


# ---------------------------------------------------------------------------
# _resolve_hwnd accepts WindowInfo or int
# ---------------------------------------------------------------------------


def test_resolve_hwnd_from_int():
    assert _resolve_hwnd(12345) == 12345


def test_resolve_hwnd_from_window_info():
    w = WindowInfo(
        hwnd=99999, title="t", class_name="c", process_name="p", pid=0,
        rect=(0, 0, 10, 10), monitor_index=0,
        is_minimized=False, is_foreground=False,
    )
    assert _resolve_hwnd(w) == 99999


# ---------------------------------------------------------------------------
# Safety hook fail-open
# ---------------------------------------------------------------------------


def test_validate_uia_action_returns_allow_when_validator_unavailable(monkeypatch):
    """When the validator import fails, the helper must return an ALLOW
    verdict so the caller can decide what to do (fail-open philosophy).
    """
    def broken_validator_call(*a, **kw):
        raise RuntimeError("validator module missing")
    monkeypatch.setattr(
        "ultron.safety.validator.get_validator", broken_validator_call,
    )
    v = _validate_uia_action(
        action="click", window_title="X", element_query="Y",
    )
    assert v.is_allowed


def test_validate_uia_action_blocks_when_validator_blocks(monkeypatch):
    from ultron.safety.validator import ValidatorVerdict, Verdict

    blocked = ValidatorVerdict(
        verdict=Verdict.BLOCK_HARD, reason="test block",
        triggered_rule_id="test", user_message="refused",
    )
    monkeypatch.setattr(
        "ultron.safety.validator.get_validator",
        lambda: type("V", (), {"check": lambda self, ctx: blocked})(),
    )
    v = _validate_uia_action(
        action="click", window_title="X", element_query="Submit",
    )
    assert not v.is_allowed


# ---------------------------------------------------------------------------
# collect_window_text fail-open paths
# ---------------------------------------------------------------------------


def test_collect_window_text_returns_empty_when_pywinauto_missing(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.uia._import_pywinauto", lambda: None,
    )
    assert collect_window_text(0) == []


def test_collect_window_text_returns_empty_when_connect_fails(monkeypatch):
    """When _connect_window returns None (bad hwnd / pywinauto failure),
    callers get an empty list rather than an exception.
    """
    monkeypatch.setattr(
        "ultron.desktop.uia._connect_window", lambda hwnd: None,
    )
    assert collect_window_text(99999999) == []


def test_collect_window_text_respects_max_elements(monkeypatch):
    """With a synthetic tree of 50 elements but cap=10, only 10 are visited."""

    class FakeNode:
        def __init__(self, name, children=()):
            self.name = name
            self._children = list(children)
        def children(self):
            return self._children

    # Build a wide tree: root with 50 direct children.
    root = FakeNode("root", [FakeNode(f"label_{i}") for i in range(50)])

    fake_spec = MagicMock()
    fake_spec.element_info = root
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)

    out = collect_window_text(0, max_elements=10)
    assert 0 < len(out) <= 10
    assert "root" in out


def test_collect_window_text_dedupes_and_filters_short(monkeypatch):
    class FakeNode:
        def __init__(self, name, children=()):
            self.name = name
            self._children = list(children)
        def children(self):
            return self._children

    root = FakeNode("", [
        FakeNode("OK"),
        FakeNode("OK"),     # duplicate
        FakeNode("X"),      # too short with min_length=2
        FakeNode("Submit"),
        FakeNode("  "),     # whitespace
    ])
    fake_spec = MagicMock()
    fake_spec.element_info = root
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)

    out = collect_window_text(0, min_length=2)
    assert "OK" in out
    assert "Submit" in out
    assert out.count("OK") == 1  # dedup
    assert "X" not in out


def test_collect_window_text_skips_broken_children(monkeypatch):
    """A node whose children() raises should not abort the walk."""

    class GoodNode:
        def __init__(self, name, children=()):
            self.name = name
            self._children = list(children)
        def children(self):
            return self._children

    class BrokenNode:
        name = "BROKEN_PARENT"
        def children(self):
            raise RuntimeError("simulated UIA error")

    root = GoodNode("root", [BrokenNode(), GoodNode("Healthy")])
    fake_spec = MagicMock()
    fake_spec.element_info = root
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)

    out = collect_window_text(0)
    assert "root" in out
    assert "Healthy" in out
    assert "BROKEN_PARENT" in out


# ---------------------------------------------------------------------------
# find_element fail-open paths
# ---------------------------------------------------------------------------


def test_find_element_returns_none_when_pywinauto_missing(monkeypatch):
    monkeypatch.setattr("ultron.desktop.uia._import_pywinauto", lambda: None)
    assert find_element(0, query="Submit") is None


def test_find_element_returns_none_when_connect_fails(monkeypatch):
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: None)
    assert find_element(0, query="Submit") is None


def test_find_element_empty_query_and_no_automation_id_returns_none(monkeypatch):
    fake_spec = MagicMock()
    fake_spec.element_info = MagicMock()
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)
    assert find_element(0, query="") is None
    assert find_element(0, query="   ") is None


# ---------------------------------------------------------------------------
# click_element / type_text_into_element fail-open paths
# ---------------------------------------------------------------------------


def test_click_element_returns_error_when_no_connection(monkeypatch):
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: None)
    r = click_element(0, "Submit")
    assert r.success is False
    assert r.error and "connect" in r.error


def test_click_element_short_circuits_on_validator_block(monkeypatch):
    from ultron.safety.validator import ValidatorVerdict, Verdict

    fake_spec = MagicMock()
    fake_spec.window_text = lambda: "Some window"
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)
    monkeypatch.setattr(
        "ultron.desktop.uia._validate_uia_action",
        lambda **kw: ValidatorVerdict(
            verdict=Verdict.BLOCK_HARD, reason="test policy block",
            triggered_rule_id="test", user_message="refused",
        ),
    )
    r = click_element(0, "Submit")
    assert r.success is False
    assert "safety" in (r.error or "")


def test_click_element_returns_error_when_element_not_found(monkeypatch):
    fake_spec = MagicMock()
    fake_spec.window_text = lambda: "Some window"
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)
    monkeypatch.setattr(
        "ultron.desktop.uia._validate_uia_action",
        lambda **kw: __import__(
            "ultron.safety.validator", fromlist=["ValidatorVerdict", "Verdict"],
        ).ValidatorVerdict(
            verdict=__import__(
                "ultron.safety.validator", fromlist=["Verdict"],
            ).Verdict.ALLOW,
            reason="ok",
        ),
    )
    monkeypatch.setattr(
        "ultron.desktop.uia.find_element", lambda *a, **kw: None,
    )
    r = click_element(0, "NonexistentButton")
    assert r.success is False
    assert "no element" in (r.error or "")


def test_type_text_into_element_short_circuits_on_validator_block(monkeypatch):
    from ultron.safety.validator import ValidatorVerdict, Verdict

    fake_spec = MagicMock()
    fake_spec.window_text = lambda: "Bank login"
    monkeypatch.setattr("ultron.desktop.uia._connect_window", lambda hwnd: fake_spec)
    monkeypatch.setattr(
        "ultron.desktop.uia._validate_uia_action",
        lambda **kw: ValidatorVerdict(
            verdict=Verdict.BLOCK_HARD, reason="payment domain typing blocked",
            triggered_rule_id="Cap-3.payment-domain", user_message="refused",
        ),
    )
    r = type_text_into_element(0, "password_field", "secretpw")
    assert r.success is False
    assert "safety" in (r.error or "")


# ---------------------------------------------------------------------------
# Live integration (Windows only)
# ---------------------------------------------------------------------------


pytestmark_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only (pywinauto UIA backend)",
)


@pytestmark_windows
def test_collect_window_text_live_on_foreground():
    """Smoke test: collecting text from the foreground window doesn't crash
    and returns a list (may be empty for canvas-rendered apps).
    """
    from ultron.desktop.windows import get_foreground_window

    fg = get_foreground_window()
    if fg is None:
        pytest.skip("no foreground window")
    out = collect_window_text(fg, max_elements=30, max_depth=4)
    assert isinstance(out, list)
    assert all(isinstance(s, str) for s in out)


# ---------------------------------------------------------------------------
# T5: DPI-aware coordinate helpers
# ---------------------------------------------------------------------------


from ultron.desktop.uia import (  # noqa: E402  -- intentional below test imports
    dpi_aware_click_at_element_center,
    physical_center_of_element,
    physical_rect_of_element,
)


def _elem_with_rect(left=100, top=200, right=300, bottom=400, **kwargs):
    return UIAElement(
        name=kwargs.pop("name", "Submit"),
        rect=(left, top, right, bottom),
        **kwargs,
    )


class TestPhysicalCenterOfElement:

    def test_identity_default(self):
        elem = _elem_with_rect(100, 200, 300, 400)
        # Default assume_logical=False is the identity (centre of rect).
        assert physical_center_of_element(elem) == (200, 300)

    def test_assume_logical_applies_dpi(self, monkeypatch):
        elem = _elem_with_rect(100, 200, 300, 400)
        # Stub logical_to_physical so the test stays hermetic.
        monkeypatch.setattr(
            "ultron.desktop.win32_helpers.logical_to_physical",
            lambda x, y, **_: (x * 2, y * 2),
        )
        assert physical_center_of_element(elem, assume_logical=True) == (400, 600)

    def test_assume_logical_falls_back_on_import_error(self, monkeypatch):
        elem = _elem_with_rect(100, 200, 300, 400)
        import sys as _sys

        # Force the lazy import to fail so the helper falls back to
        # the identity centre.
        monkeypatch.setitem(_sys.modules, "ultron.desktop.win32_helpers", None)
        assert physical_center_of_element(elem, assume_logical=True) == (200, 300)

    def test_zero_rect_returns_origin(self):
        elem = UIAElement(name="N/A", rect=(0, 0, 0, 0))
        assert physical_center_of_element(elem) == (0, 0)


class TestPhysicalRectOfElement:

    def test_identity_default(self):
        elem = _elem_with_rect(10, 20, 110, 220)
        assert physical_rect_of_element(elem) == (10, 20, 110, 220)

    def test_assume_logical_uses_centre_reference(self, monkeypatch):
        elem = _elem_with_rect(100, 100, 200, 200)
        # Spy: record the reference_x/y values passed in.
        captured: list[dict] = []

        def _stub(x, y, *, reference_x=None, reference_y=None):
            captured.append({"x": x, "y": y, "ref_x": reference_x, "ref_y": reference_y})
            return x * 2, y * 2

        monkeypatch.setattr(
            "ultron.desktop.win32_helpers.logical_to_physical", _stub,
        )
        result = physical_rect_of_element(elem, assume_logical=True)
        assert result == (200, 200, 400, 400)
        # Both corners look up DPI at the rect's centre.
        assert {c["ref_x"] for c in captured} == {150}
        assert {c["ref_y"] for c in captured} == {150}


class _FakeController:
    """Captures InputController.click calls."""

    def __init__(self, *, success: bool = True, error: str = "") -> None:
        self.success = success
        self.error = error
        self.calls: list[dict] = []

    def click(self, *, x, y, button="left", clicks=1, user_text=""):
        self.calls.append({
            "x": x, "y": y, "button": button,
            "clicks": clicks, "user_text": user_text,
        })

        class _R:
            def __init__(self, ok, err):
                self.success = ok
                self.error = err
        return _R(self.success, self.error)


class TestDpiAwareClickAtElementCenter:

    def test_happy_path_calls_controller_with_physical_coords(self):
        elem = _elem_with_rect(100, 200, 300, 400)
        ctrl = _FakeController(success=True)
        result = dpi_aware_click_at_element_center(elem, controller=ctrl)
        assert isinstance(result, UIAActionResult)
        assert result.success is True
        assert result.element_name == "Submit"
        assert len(ctrl.calls) == 1
        assert ctrl.calls[0]["x"] == 200
        assert ctrl.calls[0]["y"] == 300

    def test_disabled_element_refused_before_click(self):
        elem = _elem_with_rect(is_enabled=False)
        ctrl = _FakeController()
        result = dpi_aware_click_at_element_center(elem, controller=ctrl)
        assert result.success is False
        assert "disabled" in (result.error or "")
        assert ctrl.calls == []

    def test_zero_rect_refused_before_click(self):
        elem = UIAElement(name="N/A", rect=(0, 0, 0, 0))
        ctrl = _FakeController()
        result = dpi_aware_click_at_element_center(elem, controller=ctrl)
        assert result.success is False
        assert "no measurable rect" in (result.error or "")
        assert ctrl.calls == []

    def test_controller_failure_propagates_error(self):
        elem = _elem_with_rect()
        ctrl = _FakeController(success=False, error="rate limit exceeded")
        result = dpi_aware_click_at_element_center(elem, controller=ctrl)
        assert result.success is False
        assert "rate limit exceeded" in (result.error or "")

    def test_controller_raises_propagates(self):
        elem = _elem_with_rect()

        class _BoomController:
            def click(self, **_):
                raise RuntimeError("boom")

        result = dpi_aware_click_at_element_center(elem, controller=_BoomController())
        assert result.success is False
        assert "boom" in (result.error or "")

    def test_passes_button_and_clicks(self):
        elem = _elem_with_rect()
        ctrl = _FakeController(success=True)
        dpi_aware_click_at_element_center(
            elem, controller=ctrl, button="right", clicks=2,
            user_text="please double-click submit",
        )
        assert ctrl.calls[0]["button"] == "right"
        assert ctrl.calls[0]["clicks"] == 2
        assert ctrl.calls[0]["user_text"] == "please double-click submit"

    def test_assume_logical_applies_conversion(self, monkeypatch):
        elem = _elem_with_rect(100, 100, 300, 300)
        ctrl = _FakeController(success=True)
        monkeypatch.setattr(
            "ultron.desktop.win32_helpers.logical_to_physical",
            lambda x, y, **_: (x * 2, y * 2),
        )
        dpi_aware_click_at_element_center(
            elem, controller=ctrl, assume_logical=True,
        )
        # Centre of (100,100,300,300) is (200,200); doubled -> (400,400).
        assert ctrl.calls[0]["x"] == 400
        assert ctrl.calls[0]["y"] == 400

    def test_default_controller_resolved_from_module(self, monkeypatch):
        elem = _elem_with_rect()
        ctrl = _FakeController(success=True)
        monkeypatch.setattr(
            "ultron.desktop.input_control.get_input_controller",
            lambda: ctrl,
        )
        result = dpi_aware_click_at_element_center(elem)
        assert result.success is True
        assert len(ctrl.calls) == 1

    def test_default_controller_resolution_failure_reported(self, monkeypatch):
        elem = _elem_with_rect()

        def _boom():
            raise RuntimeError("singleton broken")

        monkeypatch.setattr(
            "ultron.desktop.input_control.get_input_controller",
            _boom,
        )
        result = dpi_aware_click_at_element_center(elem)
        assert result.success is False
        assert "input controller unavailable" in (result.error or "")
