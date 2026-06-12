"""Tests for the generalised two-phase voice approval (T2).

CapabilityVoiceController.request_voice_confirmation registers an approval +
defers an action to the user's spoken yes/no; consume_voice_approval (reached
via the WINDOW_CLOSE_CONFIRMATION yes/no classifier path) records the decision
and runs the on_approve / on_deny callback. This is the reusable "ask instead
of silently refuse" layer above the (still fail-closed) safety validator.
"""

from __future__ import annotations

import threading

import pytest

from kenning.coding.voice import CapabilityVoiceController
from kenning.safety.two_phase_approval import ApprovalRegistry, set_approval_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    set_approval_registry(ApprovalRegistry())
    yield
    set_approval_registry(ApprovalRegistry())


def _controller():
    c = CapabilityVoiceController.__new__(CapabilityVoiceController)
    c._pending_voice_approval = None
    c._pending_close_approval = None
    c._pending_completion = None
    c._lock = threading.RLock()
    return c


def test_request_then_approve_runs_on_approve():
    c = _controller()
    ran: list[str] = []

    prompt = c.request_voice_confirmation(
        "Delete the file? Say yes or no.",
        on_approve=lambda: (ran.append("approved"), "Deleted it.")[1],
        on_deny=lambda: (ran.append("denied"), "Left it alone.")[1],
        scope_key="delete-file",
    )

    assert prompt == "Delete the file? Say yes or no."
    assert c.has_pending_voice_approval() is True

    narration = c.consume_voice_approval("yes")
    assert narration == "Deleted it."
    assert ran == ["approved"]
    assert c.has_pending_voice_approval() is False


def test_request_then_deny_runs_on_deny():
    c = _controller()
    ran: list[str] = []

    c.request_voice_confirmation(
        "Proceed? yes or no.",
        on_approve=lambda: (ran.append("approved"), "Done.")[1],
        on_deny=lambda: (ran.append("denied"), "Cancelled.")[1],
    )
    narration = c.consume_voice_approval("no")

    assert narration == "Cancelled."
    assert ran == ["denied"]
    assert c.has_pending_voice_approval() is False


def test_consume_with_no_pending_returns_none():
    c = _controller()
    assert c.consume_voice_approval("yes") is None


def test_second_request_supersedes_first():
    c = _controller()
    first_ran: list[str] = []
    second_ran: list[str] = []
    c.request_voice_confirmation(
        "First?", on_approve=lambda: (first_ran.append("x"), "first")[1],
    )
    c.request_voice_confirmation(
        "Second?", on_approve=lambda: (second_ran.append("x"), "second")[1],
    )
    # The latest pending wins; the spoken yes resolves the SECOND action.
    narration = c.consume_voice_approval("yes")
    assert narration == "second"
    assert first_ran == []
    assert second_ran == ["x"]


def test_handler_consumes_general_voice_approval(monkeypatch):
    """The WINDOW_CLOSE_CONFIRMATION yes/no handler consumes a GENERAL voice
    approval when no window-close approval is pending."""
    from types import SimpleNamespace

    import kenning.openclaw_routing as ocr

    # The handler audit-logs via get_routing_log().record(intent, ...) which
    # reads many RoutingIntent fields; stub it so the test uses a thin intent.
    monkeypatch.setattr(
        ocr, "get_routing_log",
        lambda: SimpleNamespace(record=lambda *a, **k: None),
    )

    c = _controller()
    ran: list[str] = []
    c.request_voice_confirmation(
        "Run the thing? yes or no.",
        on_approve=lambda: (ran.append("go"), "Running it.")[1],
    )

    routing_intent = SimpleNamespace(
        window_close_confirmation_intent=SimpleNamespace(decision="yes"),
    )
    response = c._handle_window_close_confirmation(routing_intent)

    assert response.handled is True
    assert response.text == "Running it."
    assert ran == ["go"]
    assert c.has_pending_voice_approval() is False
