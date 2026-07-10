"""HelixClient pin_message / get_pinned_message (the pinboard, 2026-07-09).

Hermetic ScriptedTransport (mirrors test_moderation.py). Pins: the flat-body
first attempt, the ONE nested-data retry on a 400 that names "data" (open-beta
schema tolerance — never a blind retry), loud failure otherwise, and the
read path's no-pin vs cannot-read distinction the keeper depends on.
"""
from __future__ import annotations

import json

import pytest

from kenning.twitch.moderation.helix import (
    HelixClient,
    HelixError,
    RateGovernor,
    TransportResponse,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


class ScriptedTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._queue: list[TransportResponse] = []
        self.default = TransportResponse(status=200, body=json.dumps({"data": []}))

    def queue(self, *responses: TransportResponse) -> "ScriptedTransport":
        self._queue.extend(responses)
        return self

    def __call__(self, method, url, headers, body):
        self.calls.append({
            "method": method, "url": url, "headers": dict(headers),
            "body": json.loads(body.decode()) if body else None,
        })
        if self._queue:
            return self._queue.pop(0)
        return self.default


def make_client(transport, clock=None) -> HelixClient:
    clock = clock or FakeClock()
    gov = RateGovernor(rate=1000.0, burst=1000,
                       monotonic=clock.monotonic, sleep=clock.sleep)
    return HelixClient(client_id="cid", get_token=lambda: "tok",
                       transport=transport, rate_governor=gov,
                       monotonic=clock.monotonic, sleep=clock.sleep,
                       base_backoff_s=1.0, max_backoff_s=8.0)


# ----------------------------------------------------------------- pin write
# Endpoint verified 2026-07-10: POST /chat/pins with ALL fields in the JSON
# body (the docs-summary path /chat/pinned_messages 404'd live).
_PIN_BODY = {"broadcaster_id": "B1", "moderator_id": "B1", "message_id": "m1"}


def test_pin_message_flat_body_success():
    tr = ScriptedTransport().queue(
        TransportResponse(status=200, body=json.dumps({"data": [{"message_id": "m1"}]})))
    res = make_client(tr).pin_message("B1", "B1", "m1")
    assert res.ok is True and res.action == "pin_message"
    assert len(tr.calls) == 1
    call = tr.calls[0]
    assert call["method"] == "POST"
    assert "/chat/pins" in call["url"]
    assert "pinned_messages" not in call["url"]          # the 404 path is gone
    assert call["body"] == _PIN_BODY                     # ALL fields in body


def test_pin_message_retries_nested_once_on_schema_400():
    tr = ScriptedTransport().queue(
        TransportResponse(status=400, body='{"message":"Missing required parameter \\"data\\""}'),
        TransportResponse(status=200, body=json.dumps({"data": [{"message_id": "m1"}]})),
    )
    res = make_client(tr).pin_message("B1", "B1", "m1")
    assert res.ok is True
    assert len(tr.calls) == 2
    assert tr.calls[0]["body"] == _PIN_BODY
    assert tr.calls[1]["body"] == {"data": _PIN_BODY}    # nested retry


def test_pin_message_400_without_data_hint_fails_loud_no_retry():
    tr = ScriptedTransport().queue(
        TransportResponse(status=400, body='{"message":"message too old to pin"}'))
    with pytest.raises(HelixError):
        make_client(tr).pin_message("B1", "B1", "m1")
    assert len(tr.calls) == 1                            # never blind-retried


def test_pin_message_permission_failure_is_loud():
    tr = ScriptedTransport().queue(
        TransportResponse(status=403, body='{"message":"missing scope"}'))
    with pytest.raises(HelixError) as ei:
        make_client(tr).pin_message("B1", "B1", "m1")
    assert ei.value.status == 403


def test_pin_message_validates_inputs():
    with pytest.raises(ValueError):
        make_client(ScriptedTransport()).pin_message("", "B1", "m1")
    with pytest.raises(ValueError):
        make_client(ScriptedTransport()).pin_message("B1", "B1", "")


# ------------------------------------------------------------------ pin read
def test_get_pinned_message_active_pin():
    tr = ScriptedTransport().queue(TransportResponse(
        status=200,
        body=json.dumps({"data": [{"message_id": "m9", "content": "cmds"}]})))
    res = make_client(tr).get_pinned_message("B1")
    assert res.ok is True
    assert res.data["data"][0]["message_id"] == "m9"
    assert tr.calls[0]["method"] == "GET"
    assert tr.calls[0]["body"] is None
    assert "/chat/pins" in tr.calls[0]["url"]
    # moderator_id is REQUIRED on the GET (defaults to the broadcaster)
    assert "broadcaster_id=B1" in tr.calls[0]["url"]
    assert "moderator_id=B1" in tr.calls[0]["url"]


def test_get_pinned_message_no_pin_is_ok_with_empty_data():
    tr = ScriptedTransport().queue(
        TransportResponse(status=200, body=json.dumps({"data": []})))
    res = make_client(tr).get_pinned_message("B1")
    assert res.ok is True and res.data == {"data": []}


def test_get_pinned_message_cannot_read_raises():
    """The keeper needs 'no pin' (ok, empty) distinct from 'cannot read'
    (raise) — an unreadable state must NOT be treated as unpinned, else the
    keeper would re-post blind and re-create the flood."""
    tr = ScriptedTransport().queue(
        TransportResponse(status=500, body='{"message":"internal"}'))
    with pytest.raises(HelixError):
        make_client(tr).get_pinned_message("B1")
    with pytest.raises(ValueError):
        make_client(ScriptedTransport()).get_pinned_message("")
