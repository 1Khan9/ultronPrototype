"""Tests for the Twitch mod-action confirmation window.

These run HEADLESS-SAFE and deterministically on any box: no REAL Tk window is
built. Matching the rest of the suite (e.g. ``tests/audio/test_log_viewer.py``,
which never spins up the real overlay), the window's daemon UI thread is either
forced off via the ``KENNING_MOD_GUI_HEADLESS`` env flag (the no-op / fail-open
path) or stubbed so the ``available=True`` code path runs without ever creating
a Tk root. Rapidly creating + destroying many real Tk interpreters in one
process is fragile on Windows ('Tcl_AsyncDelete: ... wrong thread') and is NOT
what this contract is about.

The contract under test: import, construction and every public method
(``prompt`` / ``update_match`` / ``hide`` / ``close``) NEVER raise -- whether or
not a display exists.
"""

from __future__ import annotations

import time

import pytest

import kenning.twitch.moderation_gui as mod_gui
from kenning.twitch.moderation_gui import ModerationConfirmGUI


@pytest.fixture(autouse=True)
def _force_headless(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the fail-open / no-window path for every test so no real Tk root is
    created. This makes the suite pass identically whether or not a display
    exists, and never leaks a Tk thread into the rest of the sweep."""
    monkeypatch.setenv(mod_gui._HEADLESS_ENV, "1")


def _settle() -> None:
    # Even in the headless path nothing blocks, but a tiny settle keeps the
    # tests structurally identical to the with-display flow.
    time.sleep(0.01)


def test_import_and_construct_never_raise() -> None:
    gui = ModerationConfirmGUI()
    assert isinstance(gui.available, bool)
    assert gui.available is False  # forced headless
    assert gui.shown is False
    gui.close()


def test_prompt_never_raises() -> None:
    gui = ModerationConfirmGUI()
    results: list[str] = []
    gui.prompt(
        "TIMEOUT 10m",
        "cool_viewer_42",
        ["cool_viewer", "kool_viewer_42", "coolviewer42"],
        lambda r: results.append(r),
    )
    _settle()
    gui.close()


def test_update_match_never_raises() -> None:
    gui = ModerationConfirmGUI()
    gui.prompt("BAN", "spammer", ["spammer1", "spammer_x"], lambda _r: None)
    _settle()
    gui.update_match("spammer_x", ["spammerx", "the_spammer"])
    _settle()
    gui.close()


def test_hide_never_raises() -> None:
    gui = ModerationConfirmGUI()
    gui.hide()  # before any prompt
    gui.prompt("UNBAN", "redeemed_user", [], lambda _r: None)
    _settle()
    gui.hide()
    _settle()
    gui.close()


def test_all_action_headers_accepted() -> None:
    gui = ModerationConfirmGUI()
    for action in ("TIMEOUT 10m", "BAN", "UNBAN", "UNTIMEOUT",
                   "DELETE LAST MSG"):
        gui.prompt(action, "someuser", ["alt1", "alt2"], lambda _r: None)
        _settle()
    gui.close()


def test_methods_tolerate_none_and_empty_inputs() -> None:
    gui = ModerationConfirmGUI()
    gui.prompt("", "", [], lambda _r: None)
    _settle()
    gui.update_match("", [])
    _settle()
    # A non-callable on_result must still be tolerated (stored as no callback).
    gui.prompt("BAN", "x", ["y"], None)  # type: ignore[arg-type]
    _settle()
    gui.hide()
    gui.close()


def test_double_construction_is_independent() -> None:
    a = ModerationConfirmGUI(width=300, height=200)
    b = ModerationConfirmGUI(width=420, height=320)
    a.prompt("BAN", "u1", ["a"], lambda _r: None)
    b.prompt("UNBAN", "u2", ["b"], lambda _r: None)
    _settle()
    a.close()
    b.close()


def test_headless_methods_are_true_noops() -> None:
    # Forced headless: no UI thread is ever started, regardless of the calls.
    gui = ModerationConfirmGUI()
    gui.prompt("BAN", "u", ["a", "b"], lambda _r: None)
    gui.update_match("u2", ["c"])
    gui.hide()
    _settle()
    assert gui.shown is False
    gui.close()
    assert gui.shown is False


# ---------------------------------------------------------------------------
# available=True code path -- exercised WITHOUT a real Tk root by stubbing the
# UI thread target. Proves prompt/update_match/hide/_fire never raise when a
# window WOULD be built, while staying deterministic + headless-safe.
# ---------------------------------------------------------------------------


def test_available_path_methods_never_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pretend a display exists, but neuter the real Tk loop so no root is built.
    monkeypatch.setattr(ModerationConfirmGUI, "_probe_tk_available",
                        staticmethod(lambda: True))
    monkeypatch.setattr(ModerationConfirmGUI, "_ui_loop", lambda self: None)

    gui = ModerationConfirmGUI()
    assert gui.available is True
    got: list[str] = []
    # prompt() starts the (stubbed) UI thread and enqueues a render request.
    gui.prompt("TIMEOUT 10m", "matched_user",
               ["alt_a", "alt_b"], lambda r: got.append(r))
    gui.update_match("matched_user2", ["alt_c"])
    gui.hide()
    # Drain the queued requests on THIS thread (the stubbed loop never does);
    # the render path no-ops gracefully because no widgets were built.
    gui._drain_requests()
    gui.close()


def test_fire_emits_result_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # The click handler's contract: emit exactly once, suppress a re-fire, and
    # never raise even if the callback throws.
    monkeypatch.setattr(ModerationConfirmGUI, "_probe_tk_available",
                        staticmethod(lambda: True))
    monkeypatch.setattr(ModerationConfirmGUI, "_ui_loop", lambda self: None)

    gui = ModerationConfirmGUI()
    got: list[str] = []
    gui._on_result = lambda r: got.append(r)
    gui._result_sent = False
    gui._fire("yes")
    gui._fire("no")  # suppressed -- a result was already sent
    assert got == ["yes"]

    # An invalid token is ignored.
    gui._result_sent = False
    got.clear()
    gui._fire("bogus")
    assert got == []

    # A throwing callback must not propagate out of the click handler.
    def _boom(_r: str) -> None:
        raise RuntimeError("kaboom")

    gui._on_result = _boom
    gui._result_sent = False
    gui._fire("cancel")  # must not raise
    gui.close()
