"""Track 1g integration: CodingTaskRunner registers an AST-syntax
listener when ``coding.ast_metadata.enabled`` is True.

These tests construct a minimal runner with a stub bridge so we can
fire FILE_CHANGE events directly into the registered listener and
verify the audit-row contract.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

import pytest

from kenning.coding.bridge import (
    CodingBridge,
    EventKind,
    TaskEvent,
    TaskHandle,
    TaskRequest,
    TaskResult,
    TaskState,
)
from kenning.coding.runner import CodingTaskRunner
from kenning.config import (
    LLMConfig,
    set_config,
    KenningConfig,
)


# ---------------------------------------------------------------------------
# Stub bridge + handle so we can fire events into the registered listener
# without spawning AI coding agent.
# ---------------------------------------------------------------------------


class _StubHandle(TaskHandle):
    def __init__(self, request: TaskRequest) -> None:
        self._task_id = "stub-task-1"
        self._listeners: List[Callable[[TaskEvent], None]] = []
        self._state = TaskState(
            label=request.label or "test",
            task_prompt=request.task_prompt,
            cwd=request.cwd,
            started_at=time.time(),
        )
        self._cancelled = False

    def task_id(self) -> str:
        return self._task_id

    def state(self) -> TaskState:
        return self._state

    def add_listener(self, fn) -> None:
        self._listeners.append(fn)

    def cancel(self) -> None:
        self._cancelled = True
        self._state.is_cancelled = True

    def wait(self, timeout: Optional[float] = None) -> TaskResult:
        return TaskResult(
            success=True, exit_status=0, summary="",
            files_created=[], files_modified=[], files_deleted=[],
            duration_s=0.0,
        )

    def is_running(self) -> bool:
        return not (self._cancelled or self._state.is_complete)

    # Test helper -- fire an event into all registered listeners.
    def fire(self, event: TaskEvent) -> None:
        for fn in self._listeners:
            fn(event)


class _StubBridge(CodingBridge):
    def __init__(self) -> None:
        self.handle: Optional[_StubHandle] = None

    def submit(self, request: TaskRequest) -> TaskHandle:
        self.handle = _StubHandle(request)
        return self.handle

    def name(self) -> str:
        return "stub-bridge"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def runner_with_ast_enabled(tmp_path, monkeypatch):
    """Build a CodingTaskRunner with ast_metadata.enabled = True and
    a stub bridge attached. Captures audit log writes for inspection."""
    cfg = KenningConfig()
    cfg.coding.ast_metadata.enabled = True
    cfg.coding.ast_metadata.syntax_check_on_file_change = True
    cfg.coding.ast_metadata.attach_metadata_to_audit = True
    cfg.coding.sandbox_root = str(tmp_path / "sandbox")
    cfg.coding.audit_log_path = str(tmp_path / "logs" / "coding_tasks.jsonl")
    cfg.coding.session_audit_dir = str(tmp_path / "logs" / "sessions")
    set_config(cfg)
    try:
        bridge = _StubBridge()
        runner = CodingTaskRunner(bridge=bridge)
        audit_records: List[dict] = []

        def _capture(rec: dict) -> None:
            audit_records.append(rec)

        # Override _log_record so we can inspect audit-row emissions
        # without actually writing the file.
        runner._log_record = _capture  # type: ignore[assignment]

        yield runner, bridge, audit_records
    finally:
        # Reset config to defaults so other tests aren't affected.
        set_config(KenningConfig())


@pytest.fixture
def runner_with_ast_disabled(tmp_path):
    """Default: ast_metadata.enabled = False. Verifies the listener
    is NOT registered when the flag is off."""
    cfg = KenningConfig()
    cfg.coding.sandbox_root = str(tmp_path / "sandbox")
    cfg.coding.audit_log_path = str(tmp_path / "logs" / "coding_tasks.jsonl")
    cfg.coding.session_audit_dir = str(tmp_path / "logs" / "sessions")
    set_config(cfg)
    try:
        bridge = _StubBridge()
        runner = CodingTaskRunner(bridge=bridge)
        yield runner, bridge
    finally:
        set_config(KenningConfig())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ast_listener_emits_ok_audit_on_valid_python(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, audit = runner_with_ast_enabled

    # Write a valid Python file
    src = tmp_path / "valid.py"
    src.write_text("def hello(): return 'world'\n", encoding="utf-8")

    request = TaskRequest(
        task_prompt="write a hello function",
        cwd=tmp_path,
        model="haiku",
        timeout_s=30,
    )
    handle = runner.start_task(request)

    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src,
    ))

    syntax_ok = [r for r in audit if r.get("kind") == "ast_syntax_ok"]
    assert len(syntax_ok) == 1
    row = syntax_ok[0]
    assert row["path"] == str(src)
    assert row["syntax_valid"] is True
    assert row["functions_defined"] == ["hello"]


def test_ast_listener_emits_failure_audit_on_broken_python(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, audit = runner_with_ast_enabled
    src = tmp_path / "broken.py"
    src.write_text("def broken(:\n    pass\n", encoding="utf-8")

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    handle = runner.start_task(request)

    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src,
    ))

    failures = [r for r in audit if r.get("kind") == "ast_syntax_failure"]
    assert len(failures) == 1
    row = failures[0]
    assert row["syntax_valid"] is False
    assert "SyntaxError" in row["error"]


def test_ast_listener_skips_non_python_files(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, audit = runner_with_ast_enabled
    md = tmp_path / "notes.md"
    md.write_text("# Project notes\n", encoding="utf-8")

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    handle = runner.start_task(request)

    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=md,
    ))

    ast_rows = [r for r in audit if r.get("kind", "").startswith("ast_syntax")]
    assert ast_rows == []


def test_ast_listener_ignores_non_file_change_events(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, audit = runner_with_ast_enabled

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    handle = runner.start_task(request)

    bridge.handle.fire(TaskEvent(kind=EventKind.STATUS, stage="working"))
    bridge.handle.fire(TaskEvent(kind=EventKind.TEXT, text="hi"))

    ast_rows = [r for r in audit if r.get("kind", "").startswith("ast_syntax")]
    assert ast_rows == []


def test_ast_listener_does_not_cancel_task_on_syntax_failure(
    runner_with_ast_enabled, tmp_path,
):
    """The listener is informational only -- syntax failure should
    NOT cancel the task (the safety validator + canonical monitor are
    the cancellation paths)."""
    runner, bridge, audit = runner_with_ast_enabled

    src = tmp_path / "broken.py"
    src.write_text("def broken(:\n", encoding="utf-8")

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    handle = runner.start_task(request)
    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src,
    ))

    # Stub handle should NOT have been cancelled.
    assert bridge.handle.is_running() is True
    assert bridge.handle._cancelled is False


def test_ast_listener_not_registered_when_flag_off(
    runner_with_ast_disabled, tmp_path,
):
    """With ast_metadata.enabled=False (default), the listener is
    not registered -- no rows emitted on FILE_CHANGE."""
    runner, bridge = runner_with_ast_disabled
    src = tmp_path / "valid.py"
    src.write_text("def hello(): return 'world'\n", encoding="utf-8")

    audit: List[dict] = []
    runner._log_record = lambda rec: audit.append(rec)  # type: ignore[assignment]

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    handle = runner.start_task(request)
    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src,
    ))

    ast_rows = [r for r in audit if r.get("kind", "").startswith("ast_syntax")]
    assert ast_rows == []


def test_make_ast_listener_returns_none_when_disabled(
    runner_with_ast_disabled, tmp_path,
):
    """Direct test of the listener builder: returns None when flag
    is off."""
    runner, bridge = runner_with_ast_disabled
    # Pre-construct a fake handle so the listener builder has
    # something to bind against (the start_task call would normally
    # construct one for us).
    fake = _StubHandle(TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    ))
    listener = runner._make_ast_syntax_listener(fake)
    assert listener is None


def test_make_ast_listener_returns_callable_when_enabled(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, _audit = runner_with_ast_enabled
    fake = _StubHandle(TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    ))
    listener = runner._make_ast_syntax_listener(fake)
    assert listener is not None
    assert callable(listener)


def test_ast_listener_handles_missing_file_path(
    runner_with_ast_enabled, tmp_path,
):
    """FILE_CHANGE without a path attribute shouldn't crash."""
    runner, bridge, audit = runner_with_ast_enabled
    fake = _StubHandle(TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    ))
    listener = runner._make_ast_syntax_listener(fake)
    assert listener is not None
    # Fire an event with no path
    listener(TaskEvent(kind=EventKind.FILE_CHANGE))
    # No audit row emitted
    ast_rows = [r for r in audit if r.get("kind", "").startswith("ast_syntax")]
    assert ast_rows == []


# ---------------------------------------------------------------------------
# Track 1g voice-loop integration: completion_narration mentions AST
# failures discovered during the task.
# ---------------------------------------------------------------------------


def _mark_task_complete(handle: _StubHandle, *, files_created=None) -> None:
    """Test helper: flip the stub handle's state into a successful
    completion so ``completion_narration`` walks the success branch."""
    handle._state.is_complete = True
    handle._state.success = True
    handle._state.files_created = list(files_created or [])


def test_completion_narration_mentions_single_ast_failure(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, _audit = runner_with_ast_enabled
    src = tmp_path / "broken.py"
    src.write_text("def broken(:\n    pass\n", encoding="utf-8")

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    runner.start_task(request)
    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src,
    ))
    _mark_task_complete(bridge.handle, files_created=[src])

    narration = runner.completion_narration()
    assert "syntax error" in narration.lower()
    assert "broken.py" in narration
    # TTS-safe: no absolute paths, no backslashes
    assert str(src) not in narration
    assert "\\" not in narration


def test_completion_narration_mentions_multiple_ast_failures(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, _audit = runner_with_ast_enabled
    files = []
    for i, name in enumerate(["a.py", "b.py"]):
        src = tmp_path / name
        src.write_text(f"def x_{i}(:\n", encoding="utf-8")
        files.append(src)

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    runner.start_task(request)
    for src in files:
        bridge.handle.fire(TaskEvent(
            kind=EventKind.FILE_CHANGE,
            file_path=src,
        ))
    _mark_task_complete(bridge.handle, files_created=files)

    narration = runner.completion_narration()
    assert "2 files have syntax errors" in narration
    assert "a.py" in narration
    assert "b.py" in narration


def test_completion_narration_caps_at_three_filenames_with_remainder(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, _audit = runner_with_ast_enabled
    names = [f"f{i}.py" for i in range(5)]
    files = []
    for i, name in enumerate(names):
        src = tmp_path / name
        src.write_text(f"def x_{i}(:\n", encoding="utf-8")
        files.append(src)

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    runner.start_task(request)
    for src in files:
        bridge.handle.fire(TaskEvent(
            kind=EventKind.FILE_CHANGE,
            file_path=src,
        ))
    _mark_task_complete(bridge.handle, files_created=files)

    narration = runner.completion_narration()
    assert "5 files have syntax errors" in narration
    # First three should appear; the last two should be folded into
    # "and 2 more"
    assert "f0.py" in narration
    assert "f1.py" in narration
    assert "f2.py" in narration
    assert "and 2 more" in narration
    # f3 / f4 are explicitly absent from the spoken list
    assert "f3.py" not in narration
    assert "f4.py" not in narration


def test_completion_narration_no_however_when_no_ast_failures(
    runner_with_ast_enabled, tmp_path,
):
    runner, bridge, _audit = runner_with_ast_enabled
    src = tmp_path / "ok.py"
    src.write_text("def ok(): return 1\n", encoding="utf-8")

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    runner.start_task(request)
    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src,
    ))
    _mark_task_complete(bridge.handle, files_created=[src])

    narration = runner.completion_narration()
    assert "however" not in narration.lower()
    assert "syntax error" not in narration.lower()


def test_completion_narration_dedupes_ast_failures_by_leaf(
    runner_with_ast_enabled, tmp_path,
):
    """Claude often rewrites the same file multiple times during a
    task. The voice-loop tracker dedupes by leaf so the user hears
    one mention per broken file even after many rewrite cycles."""
    runner, bridge, _audit = runner_with_ast_enabled
    src = tmp_path / "thrash.py"

    request = TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    )
    runner.start_task(request)
    for variant in ("def x(:\n", "def y(:\n", "def z(:\n"):
        src.write_text(variant, encoding="utf-8")
        bridge.handle.fire(TaskEvent(
            kind=EventKind.FILE_CHANGE,
            file_path=src,
        ))
    _mark_task_complete(bridge.handle, files_created=[src])

    narration = runner.completion_narration()
    assert "one file has syntax errors" in narration
    assert narration.count("thrash.py") == 1


def test_ast_failures_reset_on_new_task_start(
    runner_with_ast_enabled, tmp_path,
):
    """A second start_task() should clear failures from the first
    task so the new narration starts from a clean tracker."""
    runner, bridge, _audit = runner_with_ast_enabled

    # Task 1: broken file
    src1 = tmp_path / "first.py"
    src1.write_text("def x(:\n", encoding="utf-8")
    runner.start_task(TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    ))
    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src1,
    ))
    _mark_task_complete(bridge.handle, files_created=[src1])
    first_narration = runner.completion_narration()
    assert "first.py" in first_narration

    # Task 2: clean file. Task 1's broken file must NOT appear.
    src2 = tmp_path / "second.py"
    src2.write_text("def ok(): return 1\n", encoding="utf-8")
    runner.start_task(TaskRequest(
        task_prompt="...", cwd=tmp_path, model="haiku", timeout_s=30,
    ))
    bridge.handle.fire(TaskEvent(
        kind=EventKind.FILE_CHANGE,
        file_path=src2,
    ))
    _mark_task_complete(bridge.handle, files_created=[src2])
    second_narration = runner.completion_narration()
    assert "first.py" not in second_narration
    assert "syntax error" not in second_narration.lower()
