"""Tests for the start-task state machine."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from ultron.lifecycle.start_task import (
    StartTask,
    StartTaskError,
    StartTaskRecorder,
    StartTaskStatus,
    create_start_task,
    drive_start_task,
    is_terminal_status,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_create_start_task_defaults():
    task = create_start_task("voice_cold_start")
    assert task.name == "voice_cold_start"
    assert task.status == StartTaskStatus.WORKING
    assert task.id
    assert len(task.id) == 32
    assert task.detail is None
    assert task.is_terminal is False
    assert len(task.history) == 1


def test_create_start_task_with_overrides():
    task = create_start_task(
        "x",
        task_id="abc",
        initial_status=StartTaskStatus.LOADING_LLM,
        detail="loading",
        extra={"session": "s1"},
    )
    assert task.id == "abc"
    assert task.status == StartTaskStatus.LOADING_LLM
    assert task.detail == "loading"
    assert task.extra == {"session": "s1"}


def test_is_terminal_status():
    assert is_terminal_status(StartTaskStatus.READY) is True
    assert is_terminal_status(StartTaskStatus.ERROR) is True
    assert is_terminal_status(StartTaskStatus.CANCELLED) is True
    assert is_terminal_status(StartTaskStatus.WORKING) is False
    assert is_terminal_status(StartTaskStatus.LOADING_LLM) is False


def test_advance_appends_history():
    task = create_start_task("x")
    task.advance(StartTaskStatus.LOADING_LLM, detail="loading model")
    assert task.status == StartTaskStatus.LOADING_LLM
    assert task.detail == "loading model"
    assert len(task.history) == 2
    assert task.history[-1][0] == "loading_llm"
    assert task.history[-1][1] == "loading model"


def test_advance_progress_clamped():
    task = create_start_task("x")
    task.advance(StartTaskStatus.LOADING_LLM, progress=1.5)
    assert task.progress == 1.0
    task.advance(StartTaskStatus.LOADING_LLM, progress=-0.1)
    assert task.progress == 0.0


def test_advance_returns_self_for_chaining():
    task = create_start_task("x")
    result = task.advance(StartTaskStatus.READY)
    assert result is task


def test_task_to_dict_round_trip():
    task = create_start_task("x", detail="d")
    task.advance(StartTaskStatus.LOADING_LLM, progress=0.5)
    task.advance(StartTaskStatus.READY)
    data = task.to_dict()
    assert data["name"] == "x"
    assert data["status"] == "ready"
    assert data["progress"] == 0.5
    assert len(data["history"]) == 3


def test_elapsed_seconds_non_negative():
    task = create_start_task("x")
    assert task.elapsed_seconds >= 0.0


async def _simple_gen() -> AsyncIterator[StartTask]:
    task = create_start_task("simple")
    task.advance(StartTaskStatus.LOADING_LLM, detail="model")
    yield task
    task.advance(StartTaskStatus.LOADING_STT, detail="stt")
    yield task
    task.advance(StartTaskStatus.READY, detail="all loaded")
    yield task


def test_drive_start_task_reaches_ready():
    task = _run(drive_start_task(_simple_gen()))
    assert task.status == StartTaskStatus.READY
    assert task.detail == "all loaded"


def test_drive_start_task_records_each_transition():
    seen: list[StartTaskStatus] = []

    async def _on_transition(task: StartTask) -> None:
        seen.append(task.status)

    _run(drive_start_task(_simple_gen(), on_transition=_on_transition))
    assert seen == [
        StartTaskStatus.LOADING_LLM,
        StartTaskStatus.LOADING_STT,
        StartTaskStatus.READY,
    ]


def test_drive_start_task_sync_on_transition_supported():
    seen: list[StartTaskStatus] = []

    def _on_transition(task: StartTask) -> None:
        seen.append(task.status)

    _run(drive_start_task(_simple_gen(), on_transition=_on_transition))
    assert seen == [
        StartTaskStatus.LOADING_LLM,
        StartTaskStatus.LOADING_STT,
        StartTaskStatus.READY,
    ]


async def _raising_gen() -> AsyncIterator[StartTask]:
    task = create_start_task("raising")
    task.advance(StartTaskStatus.LOADING_LLM)
    yield task
    raise RuntimeError("network down")


def test_drive_start_task_propagates_error():
    with pytest.raises(StartTaskError):
        _run(drive_start_task(_raising_gen()))


def test_drive_start_task_marks_error_status():
    captured: list[StartTask] = []

    async def _on_error(task: StartTask, exc: BaseException) -> None:
        captured.append(task)

    with pytest.raises(StartTaskError):
        _run(drive_start_task(_raising_gen(), on_error=_on_error))
    assert len(captured) == 1
    assert captured[0].status == StartTaskStatus.ERROR
    assert "network down" in (captured[0].error or "")


async def _empty_gen() -> AsyncIterator[StartTask]:
    if False:                                                    # pragma: no cover
        yield create_start_task("never")


def test_drive_start_task_empty_generator_raises():
    with pytest.raises(StartTaskError):
        _run(drive_start_task(_empty_gen()))


async def _non_terminal_gen() -> AsyncIterator[StartTask]:
    task = create_start_task("never_ready")
    task.advance(StartTaskStatus.LOADING_LLM)
    yield task
    # Generator exits without ever reaching READY.


def test_drive_start_task_non_terminal_exit_marks_error():
    task = _run(drive_start_task(_non_terminal_gen()))
    assert task.status == StartTaskStatus.ERROR
    assert "without reaching a terminal state" in (task.error or "")


async def _slow_gen(yields: int = 4) -> AsyncIterator[StartTask]:
    task = create_start_task("slow")
    for i in range(yields):
        task.advance(StartTaskStatus.LOADING_LLM, detail=f"step {i}")
        yield task
        await asyncio.sleep(0.01)
    task.advance(StartTaskStatus.READY)
    yield task


def test_drive_start_task_timeout_warning(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    # Force a tight timeout so the warning fires.
    _run(drive_start_task(_slow_gen(4), timeout_seconds=0.001))
    assert any("exceeded" in rec.message for rec in caplog.records)


# -- StartTaskRecorder --


class _FakeStore:
    def __init__(self):
        self.saved: list = []

    def save_event(self, event):
        self.saved.append(event)


def test_recorder_writes_to_store():
    store = _FakeStore()
    recorder = StartTaskRecorder(event_store=store, session_id="sess")
    task = create_start_task("voice", task_id="abc")
    recorder.record(task)
    assert len(store.saved) == 1
    event = store.saved[0]
    assert event.session_id == "sess"
    assert "voice" in event.kind
    assert event.payload["task_id"] == "abc"


def test_recorder_with_no_store_is_noop():
    recorder = StartTaskRecorder(event_store=None)
    recorder.record(create_start_task("x"))  # should not raise


def test_recorder_swallows_store_exception(caplog):
    import logging
    caplog.set_level(logging.WARNING)

    class _BrokenStore:
        def save_event(self, event):
            raise RuntimeError("disk full")

    recorder = StartTaskRecorder(event_store=_BrokenStore())
    recorder.record(create_start_task("x"))
    assert any("StartTaskRecorder.record failed" in rec.message for rec in caplog.records)


def test_drive_start_task_calls_recorder():
    store = _FakeStore()
    recorder = StartTaskRecorder(event_store=store, session_id="sess")
    _run(drive_start_task(_simple_gen(), recorder=recorder))
    assert len(store.saved) == 3


def test_start_task_status_enum_values():
    """Sanity: every defined enum has the right string value."""
    assert StartTaskStatus.WORKING.value == "working"
    assert StartTaskStatus.READY.value == "ready"
    assert StartTaskStatus.ERROR.value == "error"
    assert StartTaskStatus.LOADING_LLM.value == "loading_llm"
    assert StartTaskStatus.SWAPPING_LLM.value == "swapping_llm"
    assert StartTaskStatus.INDEXING_PROJECT.value == "indexing_project"
