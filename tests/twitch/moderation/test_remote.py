"""S11 — tests for :class:`kenning.twitch.moderation.remote.ModerationRemote`.

Fully offline: an injected mock transport stands in for the loopback write
sidecar, so the orchestrator-side client is exercised without a live sidecar or a
socket. Covered:

  * available() -> True only on a 2xx /healthz with ready=true; False otherwise
    (not-ready, non-2xx, transport down, bad body).
  * prepare()/confirm() POST the right url + JSON body and parse the response.
  * cancel() POSTs /cancel best-effort and never raises.
  * a transport-level failure degrades to a fail-safe {"ok":False,"error":...}
    (never raises).
"""
from __future__ import annotations

import json

from kenning.twitch.moderation.remote import ModerationRemote


class MockTransport:
    """Records (method, url, parsed_body) and replays scripted responses.

    ``responses`` maps ``"METHOD /path"`` -> ``(status, body_dict)``. A ``raises``
    set of the same keys makes that call raise an OSError (a down sidecar).
    """

    def __init__(self, responses=None, raises=None) -> None:
        self.calls: list[dict] = []
        self._responses = responses or {}
        self._raises = raises or set()

    def __call__(self, method: str, url: str, body):
        parsed = None
        if body is not None:
            parsed = json.loads(body.decode("utf-8"))
        path = url.split("8777", 1)[-1] if "8777" in url else url
        key = f"{method} {path}"
        self.calls.append({"method": method, "url": url, "path": path, "body": parsed})
        if key in self._raises:
            raise OSError("connection refused")
        status, payload = self._responses.get(key, (404, {"ok": False, "error": "not found"}))
        return status, json.dumps(payload).encode("utf-8")


# --------------------------------------------------------------------------- #
# available()
# --------------------------------------------------------------------------- #
def test_available_true_when_ready() -> None:
    tx = MockTransport({"GET /healthz": (200, {"ok": True, "ready": True, "broadcaster_id": "1"})})
    remote = ModerationRemote(transport=tx)
    assert remote.available() is True
    assert tx.calls[0]["method"] == "GET"
    assert tx.calls[0]["path"] == "/healthz"


def test_available_false_when_not_ready() -> None:
    tx = MockTransport({"GET /healthz": (200, {"ok": True, "ready": False, "broadcaster_id": ""})})
    assert ModerationRemote(transport=tx).available() is False


def test_available_false_on_non_2xx() -> None:
    tx = MockTransport({"GET /healthz": (503, {"ok": False})})
    assert ModerationRemote(transport=tx).available() is False


def test_available_false_when_sidecar_down() -> None:
    tx = MockTransport(raises={"GET /healthz"})
    # A down sidecar never raises -> just False.
    assert ModerationRemote(transport=tx).available() is False


def test_available_false_on_bad_body() -> None:
    class BadBody(MockTransport):
        def __call__(self, method, url, body):
            self.calls.append({"method": method, "url": url})
            return 200, b"<<<not json>>>"

    assert ModerationRemote(transport=BadBody()).available() is False


# --------------------------------------------------------------------------- #
# prepare()
# --------------------------------------------------------------------------- #
def test_prepare_posts_text_and_parses_proposal() -> None:
    proposal = {
        "ok": True,
        "token": "tok-abc",
        "readback": "Ban viewer troll. Confirm?",
        "reason_blocked": "",
        "candidates": [],
        "action": "ban",
        "target": "troll",
    }
    tx = MockTransport({"POST /prepare": (200, proposal)})
    remote = ModerationRemote(transport=tx)
    out = remote.prepare("ban troll")
    assert out == proposal
    call = tx.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/prepare"
    assert call["body"] == {"text": "ban troll"}


def test_prepare_passes_through_not_a_command() -> None:
    tx = MockTransport({"POST /prepare": (200, {"ok": False, "not_a_command": True})})
    out = ModerationRemote(transport=tx).prepare("hello there")
    assert out == {"ok": False, "not_a_command": True}


def test_prepare_failsafe_when_sidecar_down() -> None:
    tx = MockTransport(raises={"POST /prepare"})
    out = ModerationRemote(transport=tx).prepare("ban troll")
    assert out == {"ok": False, "error": "unavailable"}


def test_prepare_failsafe_on_non_2xx() -> None:
    tx = MockTransport({"POST /prepare": (500, {"ok": False})})
    out = ModerationRemote(transport=tx).prepare("ban troll")
    assert out == {"ok": False, "error": "http_500"}


# --------------------------------------------------------------------------- #
# confirm()
# --------------------------------------------------------------------------- #
def test_confirm_posts_token_and_parses_result() -> None:
    result = {"ok": True, "action": "ban", "target": "troll", "detail": {"status": 200}}
    tx = MockTransport({"POST /confirm": (200, result)})
    remote = ModerationRemote(transport=tx)
    out = remote.confirm("tok-abc")
    assert out == result
    call = tx.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/confirm"
    assert call["body"] == {"token": "tok-abc"}


def test_confirm_passes_through_expired() -> None:
    tx = MockTransport({"POST /confirm": (200, {"ok": False, "error": "expired"})})
    out = ModerationRemote(transport=tx).confirm("stale")
    assert out == {"ok": False, "error": "expired"}


def test_confirm_failsafe_when_sidecar_down() -> None:
    tx = MockTransport(raises={"POST /confirm"})
    out = ModerationRemote(transport=tx).confirm("tok-abc")
    assert out == {"ok": False, "error": "unavailable"}


# --------------------------------------------------------------------------- #
# cancel()
# --------------------------------------------------------------------------- #
def test_cancel_posts_token_best_effort() -> None:
    tx = MockTransport({"POST /cancel": (200, {"ok": True})})
    remote = ModerationRemote(transport=tx)
    assert remote.cancel("tok-abc") is None
    call = tx.calls[0]
    assert call["path"] == "/cancel"
    assert call["body"] == {"token": "tok-abc"}


def test_cancel_never_raises_when_sidecar_down() -> None:
    tx = MockTransport(raises={"POST /cancel"})
    # Must not raise.
    assert ModerationRemote(transport=tx).cancel("tok-abc") is None


# --------------------------------------------------------------------------- #
# endpoint wiring
# --------------------------------------------------------------------------- #
def test_endpoint_default_and_strip() -> None:
    seen = {}

    def tx(method, url, body):
        seen["url"] = url
        return 200, json.dumps({"ok": True, "ready": True}).encode("utf-8")

    ModerationRemote(transport=tx).available()
    assert seen["url"] == "http://127.0.0.1:8777/healthz"

    seen.clear()
    ModerationRemote("http://127.0.0.1:9999/", transport=tx).available()
    assert seen["url"] == "http://127.0.0.1:9999/healthz"
