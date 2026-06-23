"""Tests for HelperClient — mocked HTTP, fail-CLOSED behaviour."""
from __future__ import annotations

import pytest

from kenning.twitch.helper import HelperClient, HelperUnavailable


def _client():
    return HelperClient("http://127.0.0.1:65535", timeout_s=0.5)


# --- classify: happy path ----------------------------------------------------

def test_classify_returns_valid_choice():
    c = _client()
    c._request = lambda m, p, payload=None: {"action": "heist"}
    assert c.classify("let's do a heist", ["heist", "duel", "raffle"]) == "heist"


def test_classify_returns_none_on_unavailable():
    c = _client()

    def boom(m, p, payload=None):
        raise HelperUnavailable("down")

    c._request = boom
    assert c.classify("do something", ["heist"]) is None


def test_classify_returns_none_when_action_not_in_choices():
    """Response outside the caller-supplied choices is rejected (fail-CLOSED)."""
    c = _client()
    c._request = lambda m, p, payload=None: {"action": "ban_user"}
    assert c.classify("ban that person", ["heist", "duel"]) is None


def test_classify_returns_none_when_action_field_missing():
    c = _client()
    c._request = lambda m, p, payload=None: {}
    assert c.classify("anything", ["heist"]) is None


def test_classify_returns_none_on_empty_choices():
    c = _client()
    # Even with a valid _request, empty choices -> None immediately.
    c._request = lambda m, p, payload=None: {"action": "heist"}
    assert c.classify("join the heist", []) is None


def test_classify_returns_none_on_empty_text():
    c = _client()
    c._request = lambda m, p, payload=None: {"action": "heist"}
    assert c.classify("", ["heist"]) is None
    assert c.classify("   ", ["heist"]) is None


def test_classify_returns_none_on_unexpected_exception():
    c = _client()

    def boom(m, p, payload=None):
        raise RuntimeError("unexpected")

    c._request = boom
    assert c.classify("anything", ["heist"]) is None


# --- classify: choices validation is caller-authoritative --------------------

def test_classify_only_returns_from_supplied_choices():
    """The sidecar response is validated against the caller's list — chat text
    can never inject new actions."""
    c = _client()
    # Sidecar returns something outside the caller's list.
    c._request = lambda m, p, payload=None: {"action": "moderation_ban"}
    result = c.classify("can you ban speedrunner42", ["heist", "duel", "slots"])
    assert result is None


def test_classify_all_valid_choices_are_returnable():
    choices = ["heist", "duel", "trivia", "raffle", "slots"]
    c = _client()
    for choice in choices:
        c._request = lambda m, p, payload=None, _ch=choice: {"action": _ch}
        assert c.classify("some text", choices) == choice


# --- health ------------------------------------------------------------------

def test_health_true_when_ready():
    c = _client()
    c._request = lambda m, p, payload=None: {"ready": True}
    assert c.health() is True


def test_health_false_when_not_ready():
    c = _client()
    c._request = lambda m, p, payload=None: {"ready": False}
    assert c.health() is False


def test_health_false_on_error():
    c = _client()

    def boom(m, p, payload=None):
        raise HelperUnavailable("down")

    c._request = boom
    assert c.health() is False


# --- _request: sends correct payload -----------------------------------------

def test_classify_sends_text_and_choices_in_payload():
    c = _client()
    captured = {}

    def fake_request(method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"action": "heist"}

    c._request = fake_request
    c.classify("join the heist", ["heist", "duel"])
    assert captured["method"] == "POST"
    assert captured["path"] == "/classify"
    assert captured["payload"]["text"] == "join the heist"
    assert captured["payload"]["choices"] == ["heist", "duel"]


def test_health_sends_get_to_healthz():
    c = _client()
    captured = {}

    def fake_request(method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        return {"ready": True}

    c._request = fake_request
    c.health()
    assert captured["method"] == "GET"
    assert captured["path"] == "/healthz"


# --- HelperUnavailable on real unreachable port ------------------------------

def test_request_raises_helper_unavailable_on_connection_refused():
    """A real HTTP call to a closed port must raise HelperUnavailable."""
    c = _client()  # port 65535 — nothing listening
    with pytest.raises(HelperUnavailable):
        c._request("GET", "/healthz")
