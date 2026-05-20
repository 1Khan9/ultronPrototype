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

from ultron.coding.bridge import (
    CodingBridge,
    EventKind,
    TaskEvent,
    TaskHandle,
    TaskRequest,
    TaskResult,
    TaskState,
)
from ultron.coding.runner import CodingTaskRunner
from ultron.config import (
    LLMConfig,
    set_config,
    UltronConfig,
)


# ---------------------------------------------------------------------------
# Stub bridge + handle so we can fire events into the registered listener
# without spawning Claude Code.
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
    cfg = UltronConfig()
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
        set_config(UltronConfig())


@pytest.fixture
def runner_with_ast_disabled(tmp_path):
    """Default: ast_metadata.enabled = False. Verifies the listener
    is NOT registered when the flag is off."""
    cfg = UltronConfig()
    cfg.coding.sandbox_root = str(tmp_path / "sandbox")
    cfg.coding.audit_log_path = str(tmp_path / "logs" / "coding_tasks.jsonl")
    cfg.coding.session_audit_dir = str(tmp_path / "logs" / "sessions")
    set_config(cfg)
    try:
        bridge = _StubBridge()
        runner = CodingTaskRunner(bridge=bridge)
        yield runner, bridge
    finally:
        set_config(UltronConfig())


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
