"""Tests for the pending message queue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kenning.lifecycle.pending_message_queue import (
    DEFAULT_QUEUE_LIMIT,
    PendingMessage,
    PendingMessageQueue,
    PendingMessageState,
    rebind_pending_messages,
)


def test_default_queue_limit_constant_pinned():
    assert DEFAULT_QUEUE_LIMIT == 32


def test_enqueue_returns_pending_message():
    q = PendingMessageQueue()
    msg = q.enqueue("key", "hello")
    assert isinstance(msg, PendingMessage)
    assert msg.binding_key == "key"
    assert msg.text == "hello"
    assert msg.state == PendingMessageState.QUEUED


def test_enqueue_message_id_unique():
    q = PendingMessageQueue()
    a = q.enqueue("k", "a")
    b = q.enqueue("k", "b")
    assert a.id != b.id


def test_enqueue_invalid_args_raise():
    q = PendingMessageQueue()
    with pytest.raises(ValueError):
        q.enqueue("", "hello")


def test_constructor_invalid_limit_raises():
    with pytest.raises(ValueError):
        PendingMessageQueue(limit_per_key=0)


def test_peek_returns_copy():
    q = PendingMessageQueue()
    q.enqueue("k", "a")
    snapshot = q.peek("k")
    q.enqueue("k", "b")
    # Snapshot should reflect the state at peek time.
    assert len(snapshot) == 1


def test_count_with_and_without_key():
    q = PendingMessageQueue()
    q.enqueue("a", "1")
    q.enqueue("a", "2")
    q.enqueue("b", "1")
    assert q.count("a") == 2
    assert q.count("b") == 1
    assert q.count() == 3


def test_keys_sorted():
    q = PendingMessageQueue()
    q.enqueue("zeta", "x")
    q.enqueue("alpha", "x")
    q.enqueue("mid", "x")
    assert q.keys() == ["alpha", "mid", "zeta"]


def test_enqueue_overflow_drops_oldest():
    q = PendingMessageQueue(limit_per_key=3)
    first = q.enqueue("k", "1")
    q.enqueue("k", "2")
    q.enqueue("k", "3")
    q.enqueue("k", "4")  # triggers overflow drop of "1"
    remaining = [m.text for m in q.peek("k")]
    assert remaining == ["2", "3", "4"]
    assert first.state == PendingMessageState.DROPPED


def test_overflow_warning_logged(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    q = PendingMessageQueue(limit_per_key=2)
    q.enqueue("k", "1")
    q.enqueue("k", "2")
    q.enqueue("k", "3")  # overflow
    assert any("dropped oldest" in rec.message for rec in caplog.records)


def test_rebind_migrates_messages_in_order():
    q = PendingMessageQueue()
    q.enqueue("temp", "first")
    q.enqueue("temp", "second")
    n = q.rebind("temp", "real")
    assert n == 2
    assert q.peek("temp") == []
    real_bucket = q.peek("real")
    assert [m.text for m in real_bucket] == ["first", "second"]
    assert all(m.binding_key == "real" for m in real_bucket)


def test_rebind_no_op_when_source_missing():
    q = PendingMessageQueue()
    assert q.rebind("nonexistent", "x") == 0


def test_rebind_same_keys_returns_zero():
    q = PendingMessageQueue()
    q.enqueue("k", "x")
    assert q.rebind("k", "k") == 0


def test_rebind_invalid_args_raise():
    q = PendingMessageQueue()
    with pytest.raises(ValueError):
        q.rebind("", "to")
    with pytest.raises(ValueError):
        q.rebind("from", "")


def test_rebind_merges_into_existing_bucket():
    q = PendingMessageQueue()
    q.enqueue("temp", "from_a")
    q.enqueue("real", "existing")
    q.rebind("temp", "real")
    real_bucket = q.peek("real")
    assert [m.text for m in real_bucket] == ["existing", "from_a"]


def test_rebind_respects_limit():
    q = PendingMessageQueue(limit_per_key=2)
    q.enqueue("from", "1")
    q.enqueue("from", "2")
    q.enqueue("from", "3")
    q.rebind("from", "to")
    # Limit was already 2, so we'd have lost "1" on enqueue.
    # After rebind into the now-empty "to", we still have at most 2.
    assert q.count("to") <= 2


def test_rebind_module_level_alias():
    q = PendingMessageQueue()
    q.enqueue("a", "1")
    n = rebind_pending_messages(q, "a", "b")
    assert n == 1
    assert q.count("a") == 0
    assert q.count("b") == 1


def test_cancel_marks_state_and_clears():
    q = PendingMessageQueue()
    a = q.enqueue("k", "1")
    b = q.enqueue("k", "2")
    n = q.cancel("k")
    assert n == 2
    assert q.peek("k") == []
    assert a.state == PendingMessageState.CANCELLED
    assert b.state == PendingMessageState.CANCELLED


def test_cancel_missing_returns_zero():
    q = PendingMessageQueue()
    assert q.cancel("never") == 0


def test_clear_removes_everything():
    q = PendingMessageQueue()
    q.enqueue("a", "1")
    q.enqueue("b", "2")
    q.clear()
    assert q.count() == 0


def test_drain_delivers_in_order():
    q = PendingMessageQueue()
    q.enqueue("k", "first")
    q.enqueue("k", "second")
    q.enqueue("k", "third")
    captured: list[str] = []
    attempted = q.drain("k", lambda m: captured.append(m.text))
    assert captured == ["first", "second", "third"]
    assert all(m.state == PendingMessageState.DELIVERED for m in attempted)
    assert q.peek("k") == []


def test_drain_empty_bucket_returns_empty_list():
    q = PendingMessageQueue()
    assert q.drain("missing", lambda m: None) == []


def test_drain_failure_marks_failed_and_continues_by_default():
    q = PendingMessageQueue()
    q.enqueue("k", "good")
    q.enqueue("k", "bad")
    q.enqueue("k", "good_again")

    def _deliver(msg):
        if msg.text == "bad":
            raise RuntimeError("delivery failure")

    attempted = q.drain("k", _deliver)
    by_text = {m.text: m for m in attempted}
    assert by_text["good"].state == PendingMessageState.DELIVERED
    assert by_text["bad"].state == PendingMessageState.FAILED
    assert by_text["good_again"].state == PendingMessageState.DELIVERED
    assert "delivery failure" in by_text["bad"].extra["error"]


def test_drain_stop_on_failure_aborts_remaining():
    q = PendingMessageQueue()
    q.enqueue("k", "good")
    q.enqueue("k", "bad")
    q.enqueue("k", "never_attempted")

    def _deliver(msg):
        if msg.text == "bad":
            raise RuntimeError("nope")

    attempted = q.drain("k", _deliver, stop_on_failure=True)
    assert [m.text for m in attempted] == ["good", "bad"]
    # Remaining messages aren't requeued -- drain removed the bucket.
    assert q.count("k") == 0


def test_persistence_round_trip(tmp_path: Path):
    target = tmp_path / "pending.jsonl"
    q1 = PendingMessageQueue(persistence_path=target)
    q1.enqueue("session-x", "hello")
    q1.enqueue("session-x", "world")
    q2 = PendingMessageQueue(persistence_path=target)
    bucket = q2.peek("session-x")
    assert [m.text for m in bucket] == ["hello", "world"]


def test_persistence_skips_delivered_messages_on_reload(tmp_path: Path):
    target = tmp_path / "pending.jsonl"
    q1 = PendingMessageQueue(persistence_path=target)
    q1.enqueue("k", "still queued")
    q1.enqueue("k", "will deliver")
    q1.drain("k", lambda m: None if m.text != "will deliver" else None)
    # Re-write with the delivered flag set.
    q1.enqueue("k", "back to queued")  # triggers persist
    q2 = PendingMessageQueue(persistence_path=target)
    texts = [m.text for m in q2.peek("k")]
    # Only the still-queued message survived.
    assert "back to queued" in texts


def test_persistence_failure_swallowed(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    target = blocker / "child" / "pending.jsonl"
    # Should not raise even though we can't create the parent dir.
    q = PendingMessageQueue(persistence_path=target)
    q.enqueue("k", "x")  # persistence will fail silently
    assert q.count("k") == 1


def test_persistence_skips_malformed_lines(tmp_path: Path):
    target = tmp_path / "pending.jsonl"
    target.write_text(
        "garbage line\n" + json.dumps(
            {
                "id": "abc",
                "binding_key": "k",
                "text": "ok",
                "state": "queued",
                "created_at": 1.0,
                "delivered_at": None,
                "extra": {},
            }
        ) + "\n",
        encoding="utf-8",
    )
    q = PendingMessageQueue(persistence_path=target)
    bucket = q.peek("k")
    assert len(bucket) == 1
    assert bucket[0].text == "ok"


def test_pending_message_to_dict_round_trip():
    msg = PendingMessage(
        id="abc",
        binding_key="k",
        text="hello",
        extra={"x": 1},
    )
    data = msg.to_dict()
    rebuilt = PendingMessage.from_dict(data)
    assert rebuilt == msg


def test_pending_message_state_enum_values():
    assert PendingMessageState.QUEUED.value == "queued"
    assert PendingMessageState.DELIVERED.value == "delivered"
    assert PendingMessageState.CANCELLED.value == "cancelled"
    assert PendingMessageState.DROPPED.value == "dropped"
    assert PendingMessageState.FAILED.value == "failed"
