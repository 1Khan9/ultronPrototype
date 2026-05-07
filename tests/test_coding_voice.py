"""Tests for :class:`CodingVoiceController` against a fake bridge."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List, Optional

import pytest

from ultron.coding.bridge import (
    CodingBridge,
    EventKind,
    EventListener,
    FileChangeKind,
    TaskEvent,
    TaskHandle,
    TaskRequest,
    TaskResult,
    TaskState,
)
from ultron.coding.projects import (
    Project,
    ProjectRegistry,
    ProjectResolver,
    new_sandbox_project,
)
from ultron.coding.runner import CodingTaskRunner
from ultron.coding.voice import CodingVoiceController


# ---------------------------------------------------------------------------
# Reuse the fake bridge from the runner tests (kept inline here so this
# file stands alone if test_coding_runner.py is reorganized later).
# ---------------------------------------------------------------------------


class _FakeHandle(TaskHandle):
    def __init__(self, request: TaskRequest):
        self._request = request
        self._listeners: List[EventListener] = []
        self._state = TaskState(
            label=request.label or "test",
            task_prompt=request.task_prompt,
            cwd=request.cwd,
            started_at=time.time(),
        )
        self._done = threading.Event()
        self._result: Optional[TaskResult] = None
        self._task_id = "fake"

    def task_id(self) -> str:
        return self._task_id

    def state(self) -> TaskState:
        from dataclasses import replace
        return replace(
            self._state,
            completed_steps=list(self._state.completed_steps),
            files_created=list(self._state.files_created),
            files_modified=list(self._state.files_modified),
            files_deleted=list(self._state.files_deleted),
        )

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def cancel(self) -> None:
        self._state.is_cancelled = True

    def wait(self, timeout=None) -> TaskResult:
        self._done.wait(timeout=timeout)
        return self._result  # type: ignore[return-value]

    def is_running(self) -> bool:
        return not self._done.is_set()

    def finish(self, success: bool = True, summary: str = "ok") -> None:
        self._result = TaskResult(
            success=success,
            exit_status=0 if success else 1,
            summary=summary,
            duration_s=time.time() - self._state.started_at,
            files_created=list(self._state.files_created),
            files_modified=list(self._state.files_modified),
        )
        self._state.is_complete = True
        self._state.success = success
        self._state.duration_s = self._result.duration_s
        self._state.final_summary = summary
        self._done.set()


class _FakeBridge(CodingBridge):
    def __init__(self):
        self.last: Optional[_FakeHandle] = None
        self.last_request: Optional[TaskRequest] = None

    def submit(self, request: TaskRequest) -> TaskHandle:
        h = _FakeHandle(request)
        self.last = h
        self.last_request = request
        return h

    def name(self) -> str:
        return "fake"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def setup(tmp_path: Path):
    """Build a fully-configured CodingVoiceController over fake plumbing."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    registry = ProjectRegistry(path=tmp_path / "projects.json")
    resolver = ProjectResolver(registry, embedder=None)
    bridge = _FakeBridge()
    runner = CodingTaskRunner(bridge=bridge, log_path=tmp_path / "log.jsonl")
    controller = CodingVoiceController(
        runner=runner,
        registry=registry,
        resolver=resolver,
        sandbox_root=sandbox,
    )
    return {
        "sandbox": sandbox,
        "registry": registry,
        "bridge": bridge,
        "runner": runner,
        "controller": controller,
    }


# ---------------------------------------------------------------------------
# Non-coding utterances pass through.
# ---------------------------------------------------------------------------


def test_non_coding_utterance_returns_none(setup):
    out = setup["controller"].handle_utterance("What's the weather today?")
    assert out is None


def test_empty_utterance_returns_none(setup):
    assert setup["controller"].handle_utterance("") is None
    assert setup["controller"].handle_utterance("   ") is None


# ---------------------------------------------------------------------------
# New-project flow.
# ---------------------------------------------------------------------------


def test_new_project_creates_sandbox_and_submits_task(setup):
    out = setup["controller"].handle_utterance(
        "Create a Python script called weather_fetcher that pulls forecasts."
    )
    assert out is not None and out.handled
    assert "weather_fetcher" in out.text.lower()
    # Project registered.
    assert setup["registry"].get("weather_fetcher") is not None
    # Sandbox folder created.
    project = setup["registry"].get("weather_fetcher")
    assert Path(project.path).is_dir()
    # Bridge got a submit with the project as cwd.
    request = setup["bridge"].last_request
    assert request is not None
    assert request.cwd == Path(project.path).resolve() or request.cwd == Path(project.path)


def test_new_project_concurrent_request_is_refused(setup):
    setup["controller"].handle_utterance(
        "Create a python script to convert tab files to csv."
    )
    out = setup["controller"].handle_utterance(
        "Make another quick python tool to do something else."
    )
    assert out is not None
    assert "already running" in out.text.lower()


# ---------------------------------------------------------------------------
# Existing-project flow.
# ---------------------------------------------------------------------------


def test_existing_project_routes_via_resolver(setup, tmp_path: Path):
    # Pre-register a project on disk.
    proj_dir = setup["sandbox"] / "calculator"
    proj_dir.mkdir()
    setup["registry"].add(Project(
        name="Calculator",
        path=str(proj_dir),
        aliases=["calc", "calculator project"],
        language="python",
        description="basic math helpers",
    ))

    out = setup["controller"].handle_utterance(
        "Add a subtract function to my calculator project."
    )
    assert out is not None and out.handled
    assert "calculator" in out.text.lower()
    request = setup["bridge"].last_request
    assert request is not None
    # Resolved to the existing folder, not a new sandbox subdir.
    assert Path(request.cwd) == proj_dir


def test_missing_directory_for_registered_project_aborts(setup):
    """If the registry points at a path that doesn't exist on disk, the
    voice layer must refuse to launch a task there."""
    setup["registry"].add(Project(
        name="Ghost",
        path=str(setup["sandbox"] / "ghost-not-on-disk"),
        aliases=["the ghost project"],
    ))
    out = setup["controller"].handle_utterance(
        "Add a feature to my ghost project."
    )
    assert out is not None
    assert "missing" in out.text.lower() or "ghost" in out.text.lower()
    # No submit happened.
    assert setup["bridge"].last_request is None


# ---------------------------------------------------------------------------
# Progress query + cancel + completion push.
# ---------------------------------------------------------------------------


def test_progress_query_during_active_task(setup):
    setup["controller"].handle_utterance(
        "Create a python script that prints hello."
    )
    out = setup["controller"].handle_utterance("How's it going?")
    assert out is not None and out.handled
    assert "currently" in out.text.lower() or "task" in out.text.lower()


def test_cancel_during_active_task(setup):
    setup["controller"].handle_utterance(
        "Create a python script that prints hello."
    )
    out = setup["controller"].handle_utterance("Stop the task.")
    assert out is not None and out.cancelled
    assert "cancelled" in out.text.lower()


def test_pending_completion_returns_none_until_transition(setup):
    assert setup["controller"].pending_completion() is None
    setup["controller"].handle_utterance(
        "Create a python script that prints hello."
    )
    # While running, no completion.
    assert setup["controller"].pending_completion() is None
    # Finish the task on the fake bridge.
    setup["bridge"].last.finish(success=True, summary="all good")
    # Wait a tick so the runner's internal accounting has settled.
    time.sleep(0.1)
    narration = setup["controller"].pending_completion()
    assert narration is not None
    assert "Done." in narration or "complete" in narration.lower()
    # Subsequent calls return None (consumed).
    assert setup["controller"].pending_completion() is None
