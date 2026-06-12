"""Lifecycle primitives -- start-task state machine + pending-message queue.

Pattern lineage attributed in ``THIRD_PARTY_NOTICES.md``.

Two related building blocks:

* :mod:`kenning.lifecycle.start_task` -- typed status state machine
  modelled as an async generator. Callers ``async for`` over a
  long-running start path and receive intermediate
  :class:`StartTaskStatus` transitions (e.g. ``LOADING_LLM`` ->
  ``LOADING_STT`` -> ``READY``) so the voice path can speak short
  status acks during a multi-second reconfigure instead of dead air.
* :mod:`kenning.lifecycle.pending_message_queue` -- queue captured
  utterances + transcripts that arrive BEFORE a task reaches READY,
  then flush in order once the task transitions. The cold-start UX
  win: the user feels heard immediately even when the LLM isn't
  loaded yet.
"""

from kenning.lifecycle.start_task import (
    DEFAULT_START_TASK_TIMEOUT_SECONDS,
    StartTask,
    StartTaskError,
    StartTaskRecorder,
    StartTaskStatus,
    create_start_task,
    drive_start_task,
    is_terminal_status,
)
from kenning.lifecycle.pending_message_queue import (
    DEFAULT_QUEUE_LIMIT,
    PendingMessage,
    PendingMessageQueue,
    PendingMessageState,
    rebind_pending_messages,
)

__all__ = [
    "DEFAULT_QUEUE_LIMIT",
    "DEFAULT_START_TASK_TIMEOUT_SECONDS",
    "PendingMessage",
    "PendingMessageQueue",
    "PendingMessageState",
    "StartTask",
    "StartTaskError",
    "StartTaskRecorder",
    "StartTaskStatus",
    "create_start_task",
    "drive_start_task",
    "is_terminal_status",
    "rebind_pending_messages",
]
