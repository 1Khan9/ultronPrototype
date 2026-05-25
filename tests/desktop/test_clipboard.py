"""Tests for ultron.desktop.clipboard (catalog 09 T4)."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

from ultron.desktop.clipboard import (
    ClipboardManager,
    ClipboardResult,
    get_clipboard_manager,
    set_clipboard_manager,
)
from ultron.safety.taint import TaintTracker, set_taint_tracker


# ---------------------------------------------------------------------------
# Result dataclass + singleton
# ---------------------------------------------------------------------------


def test_clipboard_result_is_frozen():
    r = ClipboardResult(success=True, action="read", text="x")
    with pytest.raises(Exception):
        r.success = False


def test_get_clipboard_manager_singleton_caches():
    set_clipboard_manager(None)
    try:
        a = get_clipboard_manager()
        b = get_clipboard_manager()
        assert a is b
    finally:
        set_clipboard_manager(None)


def test_set_clipboard_manager_swaps():
    set_clipboard_manager(None)
    custom = ClipboardManager(record_taint=False)
    try:
        set_clipboard_manager(custom)
        assert get_clipboard_manager() is custom
    finally:
        set_clipboard_manager(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _allow_validator(monkeypatch):
    """Force the validator to ALLOW so we exercise the pyperclip path."""
    from ultron.safety.validator import ValidatorVerdict, Verdict
    monkeypatch.setattr(
        "ultron.desktop.clipboard._validate_clipboard_action",
        lambda **kw: ValidatorVerdict(verdict=Verdict.ALLOW, reason="ok"),
    )


def _deny_validator(monkeypatch, reason: str = "Cap-3 denied"):
    """Force the validator to BLOCK_HARD so we exercise the early-exit path."""
    from ultron.safety.validator import ValidatorVerdict, Verdict
    monkeypatch.setattr(
        "ultron.desktop.clipboard._validate_clipboard_action",
        lambda **kw: ValidatorVerdict(verdict=Verdict.BLOCK_HARD, reason=reason),
    )


def _install_fake_pyperclip(monkeypatch, *, copy=None, paste=None):
    """Install a fake pyperclip module in sys.modules so the lazy
    import path inside the clipboard module picks it up."""
    fake = types.SimpleNamespace(
        copy=copy if copy is not None else (lambda text: None),
        paste=paste if paste is not None else (lambda: ""),
    )
    monkeypatch.setitem(sys.modules, "pyperclip", fake)
    return fake


# ---------------------------------------------------------------------------
# read_text -- happy paths
# ---------------------------------------------------------------------------


def test_read_text_returns_clipboard_content(monkeypatch):
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(monkeypatch, paste=lambda: "the clipboard says hi")
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text()
    assert r.success is True
    assert r.action == "read"
    assert r.text == "the clipboard says hi"
    assert r.error is None


def test_read_text_empty_clipboard_is_success(monkeypatch):
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(monkeypatch, paste=lambda: "")
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text()
    assert r.success is True
    assert r.text == ""
    assert r.tainted is False  # empty bytes never tracked


def test_read_text_none_treated_as_empty(monkeypatch):
    """Some pyperclip backends return None on an empty clipboard."""
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(monkeypatch, paste=lambda: None)
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text()
    assert r.success is True
    assert r.text == ""


def test_read_text_caps_oversize_content(monkeypatch):
    _allow_validator(monkeypatch)
    big = "x" * 1_000_000
    _install_fake_pyperclip(monkeypatch, paste=lambda: big)
    mgr = ClipboardManager(record_taint=False, max_read_chars=1000)
    r = mgr.read_text()
    assert r.success is True
    assert r.text is not None
    assert len(r.text) == 1000


# ---------------------------------------------------------------------------
# read_text -- failure paths
# ---------------------------------------------------------------------------


def test_read_text_validator_deny_short_circuits(monkeypatch):
    """A validator DENY must skip the pyperclip call entirely."""
    _deny_validator(monkeypatch, reason="clipboard read blocked by Cap-2")
    fake = _install_fake_pyperclip(
        monkeypatch, paste=MagicMock(return_value="secret"),
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text(user_text="read it")
    assert r.success is False
    assert "Cap-2" in (r.error or "")
    fake.paste.assert_not_called()


def test_read_text_pyperclip_missing(monkeypatch):
    _allow_validator(monkeypatch)
    # Force the lazy import to fail.
    monkeypatch.setattr(
        "ultron.desktop.clipboard._import_pyperclip", lambda: None,
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text()
    assert r.success is False
    assert "pyperclip unavailable" in (r.error or "")


def test_read_text_pyperclip_raises(monkeypatch):
    _allow_validator(monkeypatch)
    def _boom():
        raise RuntimeError("clipboard backend gone")
    _install_fake_pyperclip(monkeypatch, paste=_boom)
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text()
    assert r.success is False
    assert "clipboard backend gone" in (r.error or "")


def test_read_text_non_string_coerced(monkeypatch):
    """Bytes-like or numeric clipboard contents (rare backend quirks)
    are coerced to str."""
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(monkeypatch, paste=lambda: 12345)
    mgr = ClipboardManager(record_taint=False)
    r = mgr.read_text()
    assert r.success is True
    assert r.text == "12345"


# ---------------------------------------------------------------------------
# write_text -- happy paths
# ---------------------------------------------------------------------------


def test_write_text_invokes_pyperclip(monkeypatch):
    _allow_validator(monkeypatch)
    fake = _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.write_text("prepared payload")
    assert r.success is True
    assert r.action == "write"
    fake.copy.assert_called_once_with("prepared payload")


def test_write_text_empty_string_is_valid(monkeypatch):
    """Writing empty string clears the clipboard -- accepted."""
    _allow_validator(monkeypatch)
    fake = _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.write_text("")
    assert r.success is True
    fake.copy.assert_called_once_with("")
    assert r.tainted is False  # empty bytes not tracked


def test_write_text_coerces_non_string(monkeypatch):
    _allow_validator(monkeypatch)
    fake = _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.write_text(42)  # type: ignore[arg-type]
    assert r.success is True
    fake.copy.assert_called_once_with("42")


# ---------------------------------------------------------------------------
# write_text -- failure paths
# ---------------------------------------------------------------------------


def test_write_text_validator_deny_short_circuits(monkeypatch):
    _deny_validator(monkeypatch, reason="payload contains credential")
    fake = _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.write_text("my password is hunter2", user_text="copy this")
    assert r.success is False
    assert "credential" in (r.error or "")
    fake.copy.assert_not_called()


def test_write_text_pyperclip_missing(monkeypatch):
    _allow_validator(monkeypatch)
    monkeypatch.setattr(
        "ultron.desktop.clipboard._import_pyperclip", lambda: None,
    )
    mgr = ClipboardManager(record_taint=False)
    r = mgr.write_text("anything")
    assert r.success is False
    assert "pyperclip unavailable" in (r.error or "")


def test_write_text_pyperclip_raises(monkeypatch):
    _allow_validator(monkeypatch)
    def _boom(text):
        raise PermissionError("clipboard locked")
    _install_fake_pyperclip(monkeypatch, copy=_boom)
    mgr = ClipboardManager(record_taint=False)
    r = mgr.write_text("anything")
    assert r.success is False
    assert "clipboard locked" in (r.error or "")


def test_write_text_oversize_rejected(monkeypatch):
    _allow_validator(monkeypatch)
    fake = _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    mgr = ClipboardManager(record_taint=False, max_write_chars=100)
    r = mgr.write_text("x" * 200)
    assert r.success is False
    assert "exceeds max_write_chars" in (r.error or "")
    fake.copy.assert_not_called()


def test_write_text_validator_payload_preview_under_cap(monkeypatch):
    """Validator must receive a payload preview no larger than 2 KB
    even for very large writes."""
    seen: dict = {}
    def _spy(**kw):
        seen.update(kw)
        from ultron.safety.validator import ValidatorVerdict, Verdict
        return ValidatorVerdict(verdict=Verdict.ALLOW, reason="ok")

    monkeypatch.setattr(
        "ultron.desktop.clipboard._validate_clipboard_action", _spy,
    )
    _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    big = "y" * 10_000
    mgr = ClipboardManager(record_taint=False)
    mgr.write_text(big)
    preview = (seen.get("arguments") or {}).get("text_preview", "")
    assert len(preview) <= 2048
    # The reported total length must reflect the unreduced payload.
    assert (seen.get("arguments") or {}).get("length") == 10_000


# ---------------------------------------------------------------------------
# Taint tracking integration
# ---------------------------------------------------------------------------


def test_read_records_taint_when_enabled(monkeypatch):
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(monkeypatch, paste=lambda: "private data")
    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        mgr = ClipboardManager(record_taint=True)
        r = mgr.read_text()
        assert r.success is True
        assert r.tainted is True
        hit = tracker.has_taint(data=b"private data")
        assert hit is not None
        assert hit.capability == "clipboard_read"
    finally:
        set_taint_tracker(None)


def test_read_skips_taint_when_disabled(monkeypatch):
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(monkeypatch, paste=lambda: "private data")
    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        mgr = ClipboardManager(record_taint=False)
        r = mgr.read_text()
        assert r.success is True
        assert r.tainted is False
        assert tracker.size == 0
    finally:
        set_taint_tracker(None)


def test_write_records_taint_when_enabled(monkeypatch):
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        mgr = ClipboardManager(record_taint=True)
        r = mgr.write_text("payload-A")
        assert r.success is True
        assert r.tainted is True
        hit = tracker.has_taint(data=b"payload-A")
        assert hit is not None
        assert hit.capability == "clipboard_write"
    finally:
        set_taint_tracker(None)


def test_write_skips_taint_when_disabled(monkeypatch):
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    tracker = TaintTracker()
    set_taint_tracker(tracker)
    try:
        mgr = ClipboardManager(record_taint=False)
        r = mgr.write_text("payload-B")
        assert r.success is True
        assert r.tainted is False
        assert tracker.size == 0
    finally:
        set_taint_tracker(None)


def test_taint_record_failure_falls_open(monkeypatch):
    """A broken taint tracker must NOT break the clipboard operation."""
    _allow_validator(monkeypatch)
    _install_fake_pyperclip(
        monkeypatch, copy=MagicMock(return_value=None),
    )
    def _boom():
        raise RuntimeError("taint module broken")
    monkeypatch.setattr("ultron.safety.taint.get_taint_tracker", _boom)
    mgr = ClipboardManager(record_taint=True)
    r = mgr.write_text("anything")
    assert r.success is True  # write still succeeds
    assert r.tainted is False  # but tainted flag is False
