"""Queue captured utterances that arrive BEFORE a system reaches READY.

The OpenHands V1 server queues UI messages in a SQL ``pending_messages``
table keyed by ``task_id`` (``task-{uuid}``); when the conversation
transitions to READY, ``update_conversation_id`` rekeys the rows to the
real conversation id and ``_process_pending_messages`` delivers each
message in order.

Ultron's adaptation is in-process and optionally disk-persisted. The
classic use case is the cold-start UX win documented in the catalog:
the user wakes ultron and immediately starts speaking before the LLM
has finished loading; STT captures the audio + transcript and queues
it under the cold-start task id; once the LLM is READY, the queue
flushes in order so the user gets the answer with a small delay
instead of feeling missed.

Other applications:

* Gaming-mode swap (the LLM is mid-swap and the user keeps talking).
* Coding-session bootstrap (the user requests "refactor this" before
  the supervisor has finished indexing the project).
* Wake-during-TTS (the user barges in while ultron is still speaking;
  the queue captures the new utterance for after barge-in completes).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)


DEFAULT_QUEUE_LIMIT = 32
"""Default maximum pending-message backlog per binding key.

When the backlog exceeds this cap, the oldest message is dropped + a
WARN is logged. Tuned for typical voice cold-start (a user produces
at most a handful of utterances in the ~3 s window before LLM ready);
higher values risk masking a real "ultron is stuck" symptom.
"""


class PendingMessageState(str, Enum):
    """Lifecycle of a queued message."""

    QUEUED = "queued"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    DROPPED = "dropped"
    FAILED = "failed"


@dataclass
class PendingMessage:
    """One queued utterance or message body."""

    id: str
    binding_key: str
    text: str
    created_at: float = field(default_factory=time.time)
    state: PendingMessageState = PendingMessageState.QUEUED
    delivered_at: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "binding_key": self.binding_key,
            "text": self.text,
            "created_at": self.created_at,
            "state": self.state.value,
            "delivered_at": self.delivered_at,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PendingMessage":
        return cls(
            id=str(data["id"]),
            binding_key=str(data["binding_key"]),
            text=str(data["text"]),
            created_at=float(data.get("created_at", time.time())),
            state=PendingMessageState(data.get("state", "queued")),
            delivered_at=data.get("delivered_at"),
            extra=dict(data.get("extra") or {}),
        )


class PendingMessageQueue:
    """Thread-safe in-memory queue with optional JSONL persistence.

    The queue is keyed by a free-form ``binding_key`` (mirrors the
    OpenHands ``task_id``). Callers ``enqueue(binding_key, text, ...)``
    while the system is in a transient state, then call
    :meth:`rebind` to swap the temporary key to a stable one once the
    consumer is ready (e.g. ``"start-task-{uuid}"`` ->
    ``"session-{uuid}"``), then :meth:`drain` to deliver in order.

    Errors during delivery don't drop messages -- the failed message
    is marked :attr:`PendingMessageState.FAILED` so callers can retry
    or inspect.
    """

    def __init__(
        self,
        *,
        limit_per_key: int = DEFAULT_QUEUE_LIMIT,
        persistence_path: Path | str | None = None,
    ) -> None:
        if limit_per_key <= 0:
            raise ValueError("limit_per_key must be > 0")
        self._lock = threading.RLock()
        self._messages: dict[str, list[PendingMessage]] = {}
        self._limit = limit_per_key
        self._persistence_path = Path(persistence_path) if persistence_path else None
        self._maybe_load_from_disk()

    @property
    def persistence_path(self) -> Path | None:
        return self._persistence_path

    # -- mutation --

    def enqueue(
        self,
        binding_key: str,
        text: str,
        *,
        message_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> PendingMessage:
        """Add a message to the back of the queue for ``binding_key``."""

        if not binding_key:
            raise ValueError("binding_key must be non-empty")
        if text is None:
            raise ValueError("text must be a string")
        msg = PendingMessage(
            id=message_id or uuid.uuid4().hex,
            binding_key=binding_key,
            text=str(text),
            extra=dict(extra or {}),
        )
        with self._lock:
            bucket = self._messages.setdefault(binding_key, [])
            bucket.append(msg)
            if len(bucket) > self._limit:
                dropped = bucket.pop(0)
                dropped.state = PendingMessageState.DROPPED
                logger.warning(
                    "pending_message_queue: backlog for %s > %d; dropped oldest (%s)",
                    binding_key, self._limit, dropped.id,
                )
            self._maybe_persist_locked()
        return msg

    def rebind(self, from_key: str, to_key: str) -> int:
        """Migrate every message keyed by ``from_key`` to ``to_key``.

        Returns the number of migrated messages. Preserves order;
        appends to the existing ``to_key`` bucket if one exists.
        """

        if not from_key or not to_key:
            raise ValueError("from_key and to_key must be non-empty")
        if from_key == to_key:
            return 0
        with self._lock:
            from_bucket = self._messages.pop(from_key, [])
            if not from_bucket:
                return 0
            to_bucket = self._messages.setdefault(to_key, [])
            migrated_count = 0
            for msg in from_bucket:
                msg.binding_key = to_key
                to_bucket.append(msg)
                migrated_count += 1
            # Trim if over limit AFTER rebind.
            while len(to_bucket) > self._limit:
                dropped = to_bucket.pop(0)
                dropped.state = PendingMessageState.DROPPED
                logger.warning(
                    "pending_message_queue: rebind overflow for %s; dropped %s",
                    to_key, dropped.id,
                )
            self._maybe_persist_locked()
            return migrated_count

    def cancel(self, binding_key: str) -> int:
        """Mark every queued message under ``binding_key`` as CANCELLED + remove.

        Returns the number of messages cancelled.
        """

        with self._lock:
            bucket = self._messages.pop(binding_key, [])
            for msg in bucket:
                msg.state = PendingMessageState.CANCELLED
            self._maybe_persist_locked()
            return len(bucket)

    def clear(self) -> None:
        """Drop every message in every bucket."""

        with self._lock:
            self._messages.clear()
            self._maybe_persist_locked()

    # -- inspection --

    def peek(self, binding_key: str) -> list[PendingMessage]:
        with self._lock:
            return list(self._messages.get(binding_key, []))

    def keys(self) -> list[str]:
        with self._lock:
            return sorted(self._messages.keys())

    def count(self, binding_key: str | None = None) -> int:
        with self._lock:
            if binding_key is None:
                return sum(len(b) for b in self._messages.values())
            return len(self._messages.get(binding_key, []))

    # -- drain --

    def drain(
        self,
        binding_key: str,
        deliver_fn: Callable[[PendingMessage], Any],
        *,
        stop_on_failure: bool = False,
    ) -> list[PendingMessage]:
        """Deliver every queued message under ``binding_key`` in order.

        Args:
            binding_key: Bucket to drain.
            deliver_fn: Called once per message. Return value is
                ignored; raising marks the message FAILED.
            stop_on_failure: When True, the drain aborts on the first
                FAILED message, leaving subsequent messages in the
                queue. Default False (continue best-effort).

        Returns:
            The list of :class:`PendingMessage` rows the drain
            attempted (in delivery order). Inspect each row's
            ``state`` to see whether it succeeded.
        """

        with self._lock:
            bucket = self._messages.pop(binding_key, [])

        attempted: list[PendingMessage] = []
        for msg in bucket:
            try:
                deliver_fn(msg)
            except Exception as exc:                            # noqa: BLE001
                msg.state = PendingMessageState.FAILED
                msg.extra.setdefault("error", repr(exc))
                attempted.append(msg)
                logger.warning(
                    "pending_message_queue: deliver_fn raised for %s: %r",
                    msg.id, exc,
                )
                if stop_on_failure:
                    break
                continue
            msg.state = PendingMessageState.DELIVERED
            msg.delivered_at = time.time()
            attempted.append(msg)

        with self._lock:
            self._maybe_persist_locked()
        return attempted

    # -- persistence --

    def _maybe_load_from_disk(self) -> None:
        if self._persistence_path is None or not self._persistence_path.exists():
            return
        try:
            text = self._persistence_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("pending_message_queue load failed: %s", exc)
            return
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg = PendingMessage.from_dict(data)
            except Exception:                                  # noqa: BLE001
                logger.warning("pending_message_queue: skipping malformed line")
                continue
            if msg.state != PendingMessageState.QUEUED:
                # Skip non-queued (already-delivered / cancelled).
                continue
            self._messages.setdefault(msg.binding_key, []).append(msg)

    def _maybe_persist_locked(self) -> None:
        path = self._persistence_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            rows: list[str] = []
            for bucket in self._messages.values():
                for msg in bucket:
                    rows.append(json.dumps(msg.to_dict(), ensure_ascii=False))
            text = "\n".join(rows)
            path.write_text(text + ("\n" if text else ""), encoding="utf-8")
        except OSError as exc:
            logger.warning("pending_message_queue persist failed: %s", exc)


def rebind_pending_messages(
    queue: PendingMessageQueue,
    from_key: str,
    to_key: str,
) -> int:
    """Module-level convenience equivalent of :meth:`PendingMessageQueue.rebind`."""

    return queue.rebind(from_key, to_key)
