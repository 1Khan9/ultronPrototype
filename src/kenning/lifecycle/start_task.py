"""Typed start-task state machine streamed as an async iterator.

Adopts the OpenHands ``AppConversationStartTask`` shape (yielded
intermediate status values driving the UI poll endpoint) for kenning's
multi-step start paths -- gaming-mode engage, cold-start LLM/STT/TTS
load, coding-session bootstrap.

Each start function is an ``AsyncGenerator[StartTask, None]``: callers
``async for`` over it and the consumer receives the latest task
snapshot at each transition. The state machine is enforced
client-side (callers update ``task.status`` then ``yield task``),
which keeps the helper free of any orchestration policy.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
)

logger = logging.getLogger(__name__)


DEFAULT_START_TASK_TIMEOUT_SECONDS = 60.0
"""Default soft cap on a single start task before the driver logs WARN."""


class StartTaskStatus(str, Enum):
    """Lifecycle states for a single start task.

    Mirrors the OpenHands status set but is a flat enum rather than a
    nested model. Adding new statuses is additive -- consumers should
    ignore unknown values (forward compatibility).
    """

    # Generic states
    WORKING = "working"
    READY = "ready"
    ERROR = "error"
    CANCELLED = "cancelled"

    # Voice / orchestrator cold-start states
    LOADING_LLM = "loading_llm"
    LOADING_STT = "loading_stt"
    LOADING_TTS = "loading_tts"
    LOADING_MEMORY = "loading_memory"
    LOADING_INTENT = "loading_intent"
    LOADING_SKILLS = "loading_skills"

    # Gaming-mode engage states
    STOPPING_PARAKEET = "stopping_parakeet"
    SWAPPING_LLM = "swapping_llm"
    MOVING_KOKORO = "moving_kokoro"
    UNLOADING_VLM = "unloading_vlm"
    DISABLING_PLUGINS = "disabling_plugins"

    # Coding session bootstrap states
    INDEXING_PROJECT = "indexing_project"
    BUILDING_DIGEST = "building_digest"
    RESOLVING_MENTIONS = "resolving_mentions"


_TERMINAL_STATES: frozenset[StartTaskStatus] = frozenset(
    {StartTaskStatus.READY, StartTaskStatus.ERROR, StartTaskStatus.CANCELLED}
)


def is_terminal_status(status: StartTaskStatus) -> bool:
    """``True`` iff the task should not yield any more transitions."""

    return status in _TERMINAL_STATES


class StartTaskError(RuntimeError):
    """Raised by :func:`drive_start_task` on irrecoverable failure."""


@dataclass
class StartTask:
    """Mutable status snapshot streamed by start generators.

    Attributes:
        id: Stable UUID4 hex for the task.
        name: Short label identifying the start path (``"voice_cold_start"``,
            ``"gaming_engage"``, ``"coding_bootstrap"``).
        status: Current :class:`StartTaskStatus`.
        detail: Free-form text describing the current substep (used by
            the voice path to generate short status acks).
        started_at: Unix epoch seconds when the task was created.
        updated_at: Unix epoch seconds of the most recent transition.
        progress: Optional 0-1 fractional progress (None when unknown).
        error: Populated when ``status == StartTaskStatus.ERROR``.
        extra: Free-form metadata (session id, target device, etc.).
        history: List of ``(status, detail, timestamp)`` recorded by
            :meth:`advance`. Useful for post-mortem audit / event store
            rows.
    """

    id: str
    name: str
    status: StartTaskStatus = StartTaskStatus.WORKING
    detail: str | None = None
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress: float | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    history: list[tuple[str, str | None, float]] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.updated_at - self.started_at)

    @property
    def is_terminal(self) -> bool:
        return is_terminal_status(self.status)

    def advance(
        self,
        status: StartTaskStatus,
        *,
        detail: str | None = None,
        progress: float | None = None,
        error: str | None = None,
    ) -> "StartTask":
        """Mutate to ``status`` and append a history row.

        Returns ``self`` so callers can chain ``yield task.advance(...)``.
        """

        self.status = status
        if detail is not None:
            self.detail = detail
        if progress is not None:
            self.progress = max(0.0, min(1.0, progress))
        if error is not None:
            self.error = error
        self.updated_at = time.time()
        self.history.append((status.value, self.detail, self.updated_at))
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "progress": self.progress,
            "error": self.error,
            "extra": dict(self.extra),
            "history": [list(row) for row in self.history],
        }


def create_start_task(
    name: str,
    *,
    task_id: str | None = None,
    initial_status: StartTaskStatus = StartTaskStatus.WORKING,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> StartTask:
    """Construct a :class:`StartTask` with sensible defaults."""

    return StartTask(
        id=task_id or uuid.uuid4().hex,
        name=name,
        status=initial_status,
        detail=detail,
        extra=dict(extra or {}),
        history=[(initial_status.value, detail, time.time())],
    )


@dataclass
class StartTaskRecorder:
    """Persist start-task snapshots into an optional event store.

    The OpenHands V1 server records every yielded ``AppConversationStartTask``
    to a SQL table so a frontend poll endpoint can return the latest task by
    id. Kenning's version mirrors that pattern using the optional event store
    (batch 3): every transition produces a ``LifecycleStatusEvent`` row.

    When :attr:`event_store` is ``None`` the recorder is a no-op (the
    caller can still drive the iterator + speak status acks).
    """

    event_store: Any = None  # kenning.events.EventStore | None (avoid hard import)
    session_id: str = "default"
    source: str = "lifecycle"

    def record(self, task: StartTask) -> None:
        if self.event_store is None:
            return
        try:
            from kenning.events.models import StoredEvent

            event = StoredEvent.make(
                self.session_id,
                kind=f"StartTaskStatus.{task.name}",
                payload={
                    "task_id": task.id,
                    "name": task.name,
                    "status": task.status.value,
                    "detail": task.detail,
                    "progress": task.progress,
                    "error": task.error,
                    "elapsed_seconds": task.elapsed_seconds,
                    "extra": dict(task.extra),
                },
                source=self.source,
            )
            self.event_store.save_event(event)
        except Exception as exc:                                # noqa: BLE001
            logger.warning("StartTaskRecorder.record failed: %r", exc)


async def drive_start_task(
    iterator: AsyncIterator[StartTask],
    *,
    on_transition: Callable[[StartTask], Awaitable[None] | None] | None = None,
    on_error: Callable[[StartTask, BaseException], Awaitable[None] | None] | None = None,
    recorder: StartTaskRecorder | None = None,
    timeout_seconds: float = DEFAULT_START_TASK_TIMEOUT_SECONDS,
) -> StartTask:
    """Drive an :class:`AsyncIterator[StartTask]` to its terminal state.

    Args:
        iterator: The start generator. Typically built by an
            ``async def`` function decorated as a generator.
        on_transition: Optional async callback fired on every yielded
            task. The recorder is invoked separately.
        on_error: Optional callback fired when the generator raises;
            the task is marked ERROR before this fires.
        recorder: Optional :class:`StartTaskRecorder` that persists
            every transition.
        timeout_seconds: Soft cap; when exceeded, logs WARN. The
            iterator itself is NOT cancelled -- callers wrap in
            ``asyncio.wait_for`` if a hard cap is required.

    Returns:
        The final :class:`StartTask` instance.
    """

    last_task: StartTask | None = None
    start_time = time.time()
    try:
        async for task in iterator:
            last_task = task
            if recorder is not None:
                recorder.record(task)
            if on_transition is not None:
                outcome = on_transition(task)
                if asyncio.iscoroutine(outcome):
                    await outcome
            if task.is_terminal:
                break
            if time.time() - start_time > timeout_seconds:
                logger.warning(
                    "start task %s exceeded %.0fs (status=%s)",
                    task.name,
                    timeout_seconds,
                    task.status.value,
                )
    except StopAsyncIteration:
        # The generator finished without yielding READY. Treat as ERROR.
        if last_task is None:
            raise StartTaskError("start task generator yielded nothing") from None
        last_task.advance(StartTaskStatus.ERROR, error="generator exited without READY")
        return last_task
    except Exception as exc:                                    # noqa: BLE001
        if last_task is None:
            raise StartTaskError(f"start task raised before first yield: {exc!r}") from exc
        last_task.advance(StartTaskStatus.ERROR, error=f"{type(exc).__name__}: {exc}")
        if recorder is not None:
            recorder.record(last_task)
        if on_error is not None:
            outcome = on_error(last_task, exc)
            if asyncio.iscoroutine(outcome):
                await outcome
        raise StartTaskError(str(exc)) from exc

    if last_task is None:
        raise StartTaskError("start task generator yielded nothing")
    if not last_task.is_terminal:
        last_task.advance(
            StartTaskStatus.ERROR,
            error="generator exited without reaching a terminal state",
        )
        if recorder is not None:
            recorder.record(last_task)
    return last_task
