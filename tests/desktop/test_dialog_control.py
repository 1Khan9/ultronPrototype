"""Tests for kenning.desktop.dialog_control (catalog 08 T1)."""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from kenning.desktop.dialog_control import (
    DEFAULT_WAIT_INTERVAL_S,
    DEFAULT_WAIT_TIMEOUT_S,
    DIALOG_CLASSES,
    DIALOG_CONTROL_TYPES,
    DIALOG_TITLE_KEYWORDS,
    DISMISS_BUTTONS,
    DialogActionResult,
    DialogButton,
    DialogCheckbox,
    DialogContent,
    DialogField,
    DialogInfo,
    _center_of_rect,
    _coerce_hwnd,
    _matches_dialog,
    click_dialog_button,
    dismiss_dialog,
    find_dialogs,
    read_dialog,
    type_into_dialog_field,
    wait_for_dialog,
)
from kenning.desktop.windows import WindowInfo


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _wi(
    *,
    hwnd: int = 1,
    title: str = "Save As",
    class_name: str = "#32770",
    process: str = "explorer.exe",
) -> WindowInfo:
    return WindowInfo(
        hwnd=hwnd, title=title, class_name=class_name,
        process_name=process, pid=4242,
        rect=(0, 0, 400, 200), monitor_index=0,
        is_minimized=False, is_foreground=True,
    )


class _Rect:
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class _ElementInfo:
    def __init__(self, *, control_type: str = "", class_name: str = "") -> None:
        self.control_type = control_type
        self.class_name = class_name


class _DialogNode:
    """pywinauto-style element stand-in for dialog tests."""

    def __init__(
        self,
        *,
        text: str = "",
        control_type: str = "",
        class_name: str = "",
        enabled: bool = True,
        rect: tuple[int, int, int, int] = (0, 0, 0, 0),
        value: Optional[str] = None,
        selected: Optional[str] = None,
        checked: Optional[bool] = None,
    ) -> None:
        self._text = text
        self.element_info = _ElementInfo(
            control_type=control_type, class_name=class_name,
        )
        self._enabled = enabled
        self._rect = _Rect(*rect)
        self._value = value
        self._selected = selected
        self._checked = checked
        self.clicked = 0
        self.set_text_calls: list[str] = []
        self.type_keys_calls: list[str] = []
        self.focused = 0

    def window_text(self) -> str:
        return self._text

    def is_enabled(self) -> bool:
        return self._enabled

    def rectangle(self) -> _Rect:
        return self._rect

    def click_input(self) -> None:
        self.clicked += 1

    def set_focus(self) -> None:
        self.focused += 1

    def set_text(self, text: str) -> None:
        self.set_text_calls.append(text)

    def type_keys(self, text: str, with_spaces: bool = False) -> None:  # noqa: ARG002
        self.type_keys_calls.append(text)

    def get_value(self) -> str:
        return self._value or ""

    def selected_text(self) -> str:
        return self._selected or ""

    def is_checked(self) -> Optional[bool]:
        return self._checked


class _FakeSpec:
    """Stand-in for pywinauto's WindowSpecification."""

    def __init__(self, *, title: str, descendants: list[_DialogNode]) -> None:
        self._title = title
        self._descendants = descendants
        self.type_keys_calls: list[str] = []

    def window_text(self) -> str:
        return self._title

    def descendants(self) -> list[_DialogNode]:
        return list(self._descendants)

    def type_keys(self, text: str) -> None:
        self.type_keys_calls.append(text)


def _make_spec(title: str = "Save As", descendants: Optional[list[_DialogNode]] = None) -> _FakeSpec:
    return _FakeSpec(title=title, descendants=list(descendants or []))


def _patch_connect(monkeypatch, spec: Optional[object]) -> None:
    monkeypatch.setattr(
        "kenning.desktop.dialog_control._connect_to_window",
        lambda hwnd: spec,
    )


def _patch_validator_allow(monkeypatch) -> None:
    from kenning.safety.validator import ValidatorVerdict, Verdict

    monkeypatch.setattr(
        "kenning.safety.validator.get_validator",
        lambda: type(
            "V", (), {"check": lambda self, ctx: ValidatorVerdict(
                verdict=Verdict.ALLOW, reason="ok",
            )},
        )(),
    )


def _patch_validator_block(monkeypatch, reason: str = "blocked") -> None:
    from kenning.safety.validator import ValidatorVerdict, Verdict

    blocked = ValidatorVerdict(
        verdict=Verdict.BLOCK_HARD, reason=reason,
        triggered_rule_id="test_block", user_message="refused",
    )
    monkeypatch.setattr(
        "kenning.safety.validator.get_validator",
        lambda: type("V", (), {"check": lambda self, ctx: blocked})(),
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_dialog_classes_includes_32770():
    assert "#32770" in DIALOG_CLASSES


def test_dialog_title_keywords_contains_common():
    assert "save" in DIALOG_TITLE_KEYWORDS
    assert "confirm" in DIALOG_TITLE_KEYWORDS
    assert "warning" in DIALOG_TITLE_KEYWORDS


def test_dismiss_buttons_start_with_safe_options():
    # OK / Close / Cancel sit first because they're least destructive.
    assert DISMISS_BUTTONS[0] == "OK"
    assert "Close" in DISMISS_BUTTONS
    assert "Cancel" in DISMISS_BUTTONS


def test_default_wait_constants():
    assert DEFAULT_WAIT_TIMEOUT_S == 30.0
    assert DEFAULT_WAIT_INTERVAL_S == 0.5


def test_dialog_control_types_includes_window_dialog_pane():
    assert "Window" in DIALOG_CONTROL_TYPES
    assert "Dialog" in DIALOG_CONTROL_TYPES
    assert "Pane" in DIALOG_CONTROL_TYPES


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


def test_dialog_info_helpers():
    win = _wi(hwnd=42, title="A Dialog")
    info = DialogInfo(window=win, class_name="#32770", matched_by="class")
    assert info.hwnd == 42
    assert info.title == "A Dialog"


def test_dialog_info_is_frozen():
    win = _wi()
    info = DialogInfo(window=win, class_name="#32770", matched_by="class")
    with pytest.raises(Exception):
        info.matched_by = "title_keyword"


def test_dialog_button_defaults():
    b = DialogButton(name="OK")
    assert b.name == "OK"
    assert b.enabled is True
    assert b.rect == (0, 0, 0, 0)
    assert b.center == (0, 0)


def test_dialog_field_defaults():
    f = DialogField(name="filename")
    assert f.control_type == "Edit"
    assert f.value == ""


def test_dialog_checkbox_defaults():
    c = DialogCheckbox(name="Remember me")
    assert c.control_type == "CheckBox"
    assert c.checked is None


def test_dialog_content_defaults():
    content = DialogContent(title="X")
    assert content.title == "X"
    assert content.message == ()
    assert content.buttons == ()


def test_dialog_action_result_defaults():
    r = DialogActionResult(success=True, action="click_button")
    assert r.action == "click_button"
    assert r.method == ""
    assert r.error is None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_center_of_rect():
    assert _center_of_rect((10, 20, 30, 40)) == (20, 30)


def test_coerce_hwnd_int():
    assert _coerce_hwnd(99) == 99


def test_coerce_hwnd_window_info():
    win = _wi(hwnd=12345)
    assert _coerce_hwnd(win) == 12345


def test_coerce_hwnd_dialog_info():
    info = DialogInfo(window=_wi(hwnd=77), class_name="c", matched_by="class")
    assert _coerce_hwnd(info) == 77


def test_matches_dialog_by_class():
    win = _wi(class_name="#32770")
    assert _matches_dialog(win) == "class"


def test_matches_dialog_by_title_keyword():
    win = _wi(class_name="SomeCustomClass", title="Confirm Action")
    assert _matches_dialog(win) == "title_keyword"


def test_matches_dialog_none_for_regular_window():
    win = _wi(class_name="Notepad", title="Untitled.txt")
    assert _matches_dialog(win) is None


# ---------------------------------------------------------------------------
# find_dialogs
# ---------------------------------------------------------------------------


def test_find_dialogs_returns_empty_when_no_dialogs(monkeypatch):
    monkeypatch.setattr(
        "kenning.desktop.dialog_control.enumerate_windows",
        lambda **kw: [
            _wi(hwnd=1, class_name="Chrome_WidgetWin_1", title="Browser"),
        ],
    )
    assert find_dialogs() == []


def test_find_dialogs_matches_standard_dialog_class(monkeypatch):
    target = _wi(hwnd=99, class_name="#32770", title="Save As")
    monkeypatch.setattr(
        "kenning.desktop.dialog_control.enumerate_windows",
        lambda **kw: [target],
    )
    dialogs = find_dialogs()
    assert len(dialogs) == 1
    assert dialogs[0].hwnd == 99
    assert dialogs[0].matched_by == "class"


def test_find_dialogs_matches_title_keyword(monkeypatch):
    target = _wi(hwnd=99, class_name="CustomDialog", title="Confirm Delete")
    monkeypatch.setattr(
        "kenning.desktop.dialog_control.enumerate_windows",
        lambda **kw: [target],
    )
    dialogs = find_dialogs()
    assert len(dialogs) == 1
    assert dialogs[0].matched_by in ("class", "title_keyword")


def test_find_dialogs_respects_title_filter(monkeypatch):
    save_dialog = _wi(hwnd=1, class_name="#32770", title="Save As")
    open_dialog = _wi(hwnd=2, class_name="#32770", title="Open File")
    monkeypatch.setattr(
        "kenning.desktop.dialog_control.enumerate_windows",
        lambda **kw: [save_dialog, open_dialog],
    )
    dialogs = find_dialogs(partial_title_filter="save")
    assert len(dialogs) == 1
    assert dialogs[0].title == "Save As"


def test_find_dialogs_fail_open_on_enumerate_exception(monkeypatch):
    def _raise(**kw):
        raise RuntimeError("simulated enum failure")

    monkeypatch.setattr(
        "kenning.desktop.dialog_control.enumerate_windows", _raise,
    )
    assert find_dialogs() == []


# ---------------------------------------------------------------------------
# read_dialog
# ---------------------------------------------------------------------------


def test_read_dialog_returns_none_when_connect_fails(monkeypatch):
    _patch_connect(monkeypatch, None)
    win = _wi()
    assert read_dialog(win) is None


def test_read_dialog_captures_buttons_text_fields_checkboxes(monkeypatch):
    spec = _make_spec(
        title="Confirm",
        descendants=[
            _DialogNode(text="Save changes?", control_type="Text"),
            _DialogNode(
                text="Save",
                control_type="Button",
                rect=(10, 30, 110, 60),
                enabled=True,
            ),
            _DialogNode(
                text="Don't Save",
                control_type="Button",
                rect=(120, 30, 250, 60),
                enabled=True,
            ),
            _DialogNode(
                text="Cancel",
                control_type="Button",
                rect=(260, 30, 360, 60),
                enabled=True,
            ),
            _DialogNode(
                text="Filename",
                control_type="Edit",
                value="report.docx",
                rect=(10, 100, 360, 130),
            ),
            _DialogNode(
                text="Remember choice",
                control_type="CheckBox",
                checked=True,
            ),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi())
    assert content is not None
    assert content.title == "Confirm"
    assert "Save changes?" in content.message
    assert len(content.buttons) == 3
    button_names = {b.name for b in content.buttons}
    assert {"Save", "Don't Save", "Cancel"} == button_names
    save_button = next(b for b in content.buttons if b.name == "Save")
    assert save_button.center == (60, 45)
    assert save_button.enabled is True
    assert len(content.text_fields) == 1
    assert content.text_fields[0].value == "report.docx"
    assert content.text_fields[0].name == "Filename"
    assert len(content.checkboxes) == 1
    assert content.checkboxes[0].checked is True


def test_read_dialog_captures_dropdowns_with_selected_text(monkeypatch):
    spec = _make_spec(
        title="Settings",
        descendants=[
            _DialogNode(
                text="Encoding",
                control_type="ComboBox",
                selected="UTF-8",
            ),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi())
    assert content is not None
    assert len(content.dropdowns) == 1
    assert content.dropdowns[0].value == "UTF-8"


def test_read_dialog_captures_list_items(monkeypatch):
    spec = _make_spec(
        title="Choose File",
        descendants=[
            _DialogNode(text="report.docx", control_type="ListItem"),
            _DialogNode(text="resume.pdf", control_type="ListItem"),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi())
    assert content is not None
    assert "report.docx" in content.list_items
    assert "resume.pdf" in content.list_items


def test_read_dialog_deduplicates_messages(monkeypatch):
    spec = _make_spec(
        title="Warning",
        descendants=[
            _DialogNode(text="File already exists", control_type="Text"),
            _DialogNode(text="File already exists", control_type="Text"),
            _DialogNode(text="Overwrite?", control_type="Static"),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi())
    assert content is not None
    # Each unique message string appears once.
    assert content.message.count("File already exists") == 1
    assert "Overwrite?" in content.message


def test_read_dialog_caps_messages_at_message_max(monkeypatch):
    spec = _make_spec(
        title="Verbose",
        descendants=[
            _DialogNode(text=f"line {i}", control_type="Text")
            for i in range(20)
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi(), message_max=5)
    assert content is not None
    assert len(content.message) == 5


def test_read_dialog_skips_unnamed_buttons(monkeypatch):
    spec = _make_spec(
        title="X",
        descendants=[
            _DialogNode(text="", control_type="Button"),
            _DialogNode(text="OK", control_type="Button"),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi())
    assert content is not None
    assert len(content.buttons) == 1
    assert content.buttons[0].name == "OK"


def test_read_dialog_truncates_long_strings(monkeypatch):
    long_text = "x" * 2000
    spec = _make_spec(
        title="Long",
        descendants=[
            _DialogNode(text=long_text, control_type="Text"),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi(), text_truncate=100)
    assert content is not None
    assert len(content.message[0]) == 100


def test_read_dialog_skips_broken_descendant(monkeypatch):
    class _BrokenNode(_DialogNode):
        def window_text(self) -> str:
            raise RuntimeError("simulated UIA error")

    spec = _make_spec(
        title="Mixed",
        descendants=[
            _BrokenNode(control_type="Button"),
            _DialogNode(text="OK", control_type="Button"),
        ],
    )
    _patch_connect(monkeypatch, spec)
    content = read_dialog(_wi())
    assert content is not None
    button_names = {b.name for b in content.buttons}
    assert "OK" in button_names


# ---------------------------------------------------------------------------
# click_dialog_button
# ---------------------------------------------------------------------------


def test_click_dialog_button_rejects_empty_name(monkeypatch):
    r = click_dialog_button(_wi(), "")
    assert r.success is False
    assert "empty" in (r.error or "")


def test_click_dialog_button_returns_failure_when_connect_fails(monkeypatch):
    _patch_connect(monkeypatch, None)
    r = click_dialog_button(_wi(), "OK")
    assert r.success is False
    assert "couldn't connect" in (r.error or "")


def test_click_dialog_button_blocked_by_validator(monkeypatch):
    spec = _make_spec(descendants=[_DialogNode(text="Pay", control_type="Button")])
    _patch_connect(monkeypatch, spec)
    _patch_validator_block(monkeypatch, reason="cap-3 verb-click")
    r = click_dialog_button(_wi(), "Pay", user_text="just hello")
    assert r.success is False
    assert "safety" in (r.error or "")


def test_click_dialog_button_substring_match(monkeypatch):
    btn = _DialogNode(text="Save and Close", control_type="Button")
    spec = _make_spec(descendants=[btn])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = click_dialog_button(_wi(), "save")
    assert r.success is True
    assert btn.clicked == 1
    assert r.method == "click"


def test_click_dialog_button_exact_only(monkeypatch):
    spec = _make_spec(
        descendants=[
            _DialogNode(text="OK Cancel Maybe", control_type="Button"),
        ],
    )
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = click_dialog_button(_wi(), "OK", exact=True)
    assert r.success is False  # title is OK Cancel Maybe; exact "OK" doesn't match
    assert "no enabled button" in (r.error or "")


def test_click_dialog_button_skips_disabled(monkeypatch):
    disabled = _DialogNode(text="Apply", control_type="Button", enabled=False)
    enabled = _DialogNode(text="Apply", control_type="Button", enabled=True)
    spec = _make_spec(descendants=[disabled, enabled])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = click_dialog_button(_wi(), "Apply")
    assert r.success is True
    assert disabled.clicked == 0
    assert enabled.clicked == 1


def test_click_dialog_button_no_match_returns_failure(monkeypatch):
    spec = _make_spec(
        descendants=[_DialogNode(text="OK", control_type="Button")],
    )
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = click_dialog_button(_wi(), "Submit")
    assert r.success is False
    assert "no enabled button" in (r.error or "")


def test_click_dialog_button_click_exception(monkeypatch):
    class _Throws(_DialogNode):
        def click_input(self) -> None:
            raise RuntimeError("synthetic input refused")

    spec = _make_spec(descendants=[_Throws(text="OK", control_type="Button")])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = click_dialog_button(_wi(), "OK")
    assert r.success is False
    assert "click failed" in (r.error or "")


# ---------------------------------------------------------------------------
# type_into_dialog_field
# ---------------------------------------------------------------------------


def test_type_into_dialog_field_rejects_negative_index():
    r = type_into_dialog_field(_wi(), "text", field_index=-1)
    assert r.success is False
    assert "negative" in (r.error or "")


def test_type_into_dialog_field_returns_failure_when_no_fields(monkeypatch):
    spec = _make_spec(descendants=[_DialogNode(text="OK", control_type="Button")])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = type_into_dialog_field(_wi(), "hello")
    assert r.success is False
    assert "no enabled text fields" in (r.error or "")


def test_type_into_dialog_field_uses_set_text_preferred(monkeypatch):
    field = _DialogNode(text="filename", control_type="Edit")
    spec = _make_spec(descendants=[field])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = type_into_dialog_field(_wi(), "report.docx")
    assert r.success is True
    assert r.method == "set_text"
    assert field.set_text_calls == ["report.docx"]
    assert field.focused == 1


def test_type_into_dialog_field_field_index_disambiguates(monkeypatch):
    f1 = _DialogNode(text="user", control_type="Edit")
    f2 = _DialogNode(text="pass", control_type="Edit")
    spec = _make_spec(descendants=[f1, f2])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = type_into_dialog_field(_wi(), "value", field_index=1)
    assert r.success is True
    assert f2.set_text_calls == ["value"]
    assert f1.set_text_calls == []


def test_type_into_dialog_field_field_index_out_of_range(monkeypatch):
    field = _DialogNode(text="filename", control_type="Edit")
    spec = _make_spec(descendants=[field])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = type_into_dialog_field(_wi(), "x", field_index=5)
    assert r.success is False
    assert "out of range" in (r.error or "")


def test_type_into_dialog_field_blocked_by_validator(monkeypatch):
    field = _DialogNode(text="search", control_type="Edit")
    spec = _make_spec(descendants=[field])
    _patch_connect(monkeypatch, spec)
    _patch_validator_block(monkeypatch, reason="credential pattern")
    r = type_into_dialog_field(_wi(), "secret")
    assert r.success is False
    assert "safety" in (r.error or "")
    assert field.set_text_calls == []


def test_type_into_dialog_field_falls_back_to_type_keys(monkeypatch):
    class _NoSetText:
        """An Edit-like node without set_text; only type_keys."""

        def __init__(self) -> None:
            self.element_info = _ElementInfo(control_type="Edit")
            self._rect = _Rect(0, 0, 100, 20)
            self.type_keys_calls: list[str] = []
            self.set_focus_calls = 0

        def window_text(self) -> str:
            return ""

        def is_enabled(self) -> bool:
            return True

        def rectangle(self) -> _Rect:
            return self._rect

        def set_focus(self) -> None:
            self.set_focus_calls += 1

        def type_keys(self, text: str, with_spaces: bool = False) -> None:  # noqa: ARG002
            self.type_keys_calls.append(text)

    field = _NoSetText()
    spec = _FakeSpec(title="X", descendants=[field])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = type_into_dialog_field(_wi(), "hello")
    assert r.success is True
    assert r.method == "type_keys"
    assert field.type_keys_calls == ["hello"]


# ---------------------------------------------------------------------------
# dismiss_dialog
# ---------------------------------------------------------------------------


def test_dismiss_dialog_clicks_first_match(monkeypatch):
    ok = _DialogNode(text="OK", control_type="Button")
    cancel = _DialogNode(text="Cancel", control_type="Button")
    spec = _make_spec(descendants=[ok, cancel])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = dismiss_dialog(_wi())
    assert r.success is True
    assert r.target == "OK"
    assert r.method == "click"
    assert ok.clicked == 1
    assert cancel.clicked == 0


def test_dismiss_dialog_falls_through_to_next_when_first_missing(monkeypatch):
    cancel = _DialogNode(text="Cancel", control_type="Button")
    spec = _make_spec(descendants=[cancel])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = dismiss_dialog(_wi())
    assert r.success is True
    assert r.target == "Cancel"
    assert cancel.clicked == 1


def test_dismiss_dialog_falls_back_to_escape(monkeypatch):
    """When no dismiss button exists, send {ESC} on the dialog root."""
    spec = _make_spec(descendants=[])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = dismiss_dialog(_wi())
    assert r.success is True
    assert r.method == "escape"
    assert spec.type_keys_calls == ["{ESC}"]


def test_dismiss_dialog_preferred_buttons_overrides_default_order(monkeypatch):
    skip = _DialogNode(text="Skip", control_type="Button")
    ok = _DialogNode(text="OK", control_type="Button")
    spec = _make_spec(descendants=[ok, skip])
    _patch_connect(monkeypatch, spec)
    _patch_validator_allow(monkeypatch)
    r = dismiss_dialog(_wi(), preferred_buttons=("Skip", "OK"))
    assert r.success is True
    assert r.target == "Skip"
    assert skip.clicked == 1
    assert ok.clicked == 0


def test_dismiss_dialog_skips_validator_blocked_candidate(monkeypatch):
    """If the validator blocks a specific candidate (e.g. Pay), we fall
    through to the next candidate rather than aborting."""
    from kenning.safety.validator import ValidatorVerdict, Verdict

    pay = _DialogNode(text="Pay", control_type="Button")
    ok = _DialogNode(text="OK", control_type="Button")
    spec = _make_spec(descendants=[pay, ok])
    _patch_connect(monkeypatch, spec)

    def _check(self, ctx):  # noqa: ARG001
        # Block clicks on the "Pay" candidate only.
        if "Pay" in str(ctx.arguments.get("element", "")):
            return ValidatorVerdict(
                verdict=Verdict.BLOCK_HARD, reason="cap-3",
                triggered_rule_id="t", user_message="refused",
            )
        return ValidatorVerdict(verdict=Verdict.ALLOW, reason="ok")

    monkeypatch.setattr(
        "kenning.safety.validator.get_validator",
        lambda: type("V", (), {"check": _check})(),
    )
    # Use preferred buttons so "Pay" gets considered before "OK".
    r = dismiss_dialog(
        _wi(), preferred_buttons=("Pay", "OK"),
    )
    assert r.success is True
    assert r.target == "OK"
    assert pay.clicked == 0
    assert ok.clicked == 1


def test_dismiss_dialog_returns_failure_when_connect_fails(monkeypatch):
    _patch_connect(monkeypatch, None)
    r = dismiss_dialog(_wi())
    assert r.success is False
    assert "couldn't connect" in (r.error or "")


# ---------------------------------------------------------------------------
# wait_for_dialog
# ---------------------------------------------------------------------------


class _FakeClock:
    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


def test_wait_for_dialog_returns_none_on_zero_timeout(monkeypatch):
    consulted = [0]

    def _no_call(**kw):
        consulted[0] += 1
        return []

    monkeypatch.setattr(
        "kenning.desktop.dialog_control.find_dialogs", _no_call,
    )
    assert wait_for_dialog(timeout_s=0.0) is None
    assert consulted[0] == 0


def test_wait_for_dialog_found_on_first_poll(monkeypatch):
    target = DialogInfo(
        window=_wi(hwnd=42), class_name="#32770", matched_by="class",
    )
    monkeypatch.setattr(
        "kenning.desktop.dialog_control.find_dialogs",
        lambda **kw: [target],
    )
    slept: list[float] = []
    r = wait_for_dialog(
        timeout_s=5.0, interval_s=0.5,
        sleep_fn=lambda s: slept.append(s),
        clock_fn=_FakeClock(),
    )
    assert r is target
    assert slept == []


def test_wait_for_dialog_appears_on_third_poll(monkeypatch):
    calls = [0]
    target = DialogInfo(
        window=_wi(hwnd=99), class_name="#32770", matched_by="class",
    )

    def _appear(**kw):
        calls[0] += 1
        return [target] if calls[0] >= 3 else []

    monkeypatch.setattr(
        "kenning.desktop.dialog_control.find_dialogs", _appear,
    )
    clock = _FakeClock()

    def _sleep(dt: float) -> None:
        clock.advance(dt)

    r = wait_for_dialog(
        timeout_s=5.0, interval_s=0.1,
        sleep_fn=_sleep,
        clock_fn=clock,
    )
    assert r is target
    assert calls[0] == 3


def test_wait_for_dialog_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(
        "kenning.desktop.dialog_control.find_dialogs",
        lambda **kw: [],
    )
    clock = _FakeClock()
    sleeps: list[float] = []

    def _sleep(dt: float) -> None:
        sleeps.append(dt)
        clock.advance(dt)

    r = wait_for_dialog(
        timeout_s=1.0, interval_s=0.25,
        sleep_fn=_sleep,
        clock_fn=clock,
    )
    assert r is None
    assert 3 <= len(sleeps) <= 5


def test_wait_for_dialog_passes_title_filter(monkeypatch):
    captured: dict = {}

    def _capture(**kw):
        captured.update(kw)
        return [DialogInfo(
            window=_wi(), class_name="#32770", matched_by="class",
        )]

    monkeypatch.setattr(
        "kenning.desktop.dialog_control.find_dialogs", _capture,
    )
    wait_for_dialog(
        partial_title="save",
        timeout_s=1.0, interval_s=0.1,
        sleep_fn=lambda s: None,
        clock_fn=_FakeClock(),
    )
    assert captured["partial_title_filter"] == "save"


def test_wait_for_dialog_fail_open_on_find_exception(monkeypatch):
    raised = [0]

    def _raise(**kw):
        raised[0] += 1
        raise RuntimeError("simulated find_dialogs failure")

    monkeypatch.setattr(
        "kenning.desktop.dialog_control.find_dialogs", _raise,
    )
    clock = _FakeClock()

    def _sleep(dt: float) -> None:
        clock.advance(dt)

    r = wait_for_dialog(
        timeout_s=1.0, interval_s=0.25,
        sleep_fn=_sleep,
        clock_fn=clock,
    )
    assert r is None
    assert raised[0] >= 1
