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
