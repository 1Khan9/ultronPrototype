"""Tests for the pre-edit snapshot wiring in DirectClaudeCodeBridge
(SWE-Agent T1 + T14 wiring).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_handle(tmp_path: Path, session_id: str = "test-session-abc"):
    """Construct a DirectTaskHandle in launch-suppressed mode.

    The handle wires up _record_tool_use which is what we test.
    """
    from kenning.coding.bridge import TaskRequest
    from kenning.coding.direct_bridge import DirectTaskHandle
    import threading

    request = TaskRequest(
        task_prompt="test",
        cwd=tmp_path,
        model="haiku",
    )
    # Build the handle directly without going through submit() so we
    # skip the subprocess spawn -- _launch() does the Popen which we
    # don't want in tests.
    handle = DirectTaskHandle.__new__(DirectTaskHandle)
    handle._argv = ["echo", "stub"]
    handle._cwd = tmp_path
    handle._request = request
    handle._claude_session_id = session_id
    handle.claude_session_id = session_id
    handle._is_new_session = True
    handle._proc = None
    handle._stdout_thread = None
    handle._stderr_thread = None
    handle._wait_thread = None
    handle._listeners = []
    handle._listeners_lock = threading.RLock()
    handle._completion_event = threading.Event()
    handle._cancel_requested = False
    handle._final_exit_status = None
    handle._final_exit_code = None
    handle._final_duration_s = 0.0

    # Minimal state with mutate() shim.
    class _State:
        def __init__(self):
            self.text_chars_emitted = 0
            self.last_text_snippet = ""
            self.tool_use_count = 0
            self.last_tool_use = None
            self.current_step = ""
            self.completed_steps: list = []
            self.files_created: list = []
            self.files_modified: list = []

        def mutate(self, fn):
            fn(self)

    handle._state = _State()
    handle._token_usage = {
        "input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
    }
    handle._cumulative_text_chars = 0
    return handle


def _reset_file_history_singleton():
    """Clear the FileHistory module-level cache between tests."""
    from kenning.coding import file_history

    # The accessor uses a module-level dict cache; clear it.
    if hasattr(file_history, "_FILE_HISTORY_CACHE"):
        file_history._FILE_HISTORY_CACHE.clear()
    if hasattr(file_history, "_FILE_HISTORY_INSTANCES"):
        file_history._FILE_HISTORY_INSTANCES.clear()


@pytest.fixture(autouse=True)
def reset_history():
    _reset_file_history_singleton()
    yield
    _reset_file_history_singleton()


# ---------------------------------------------------------------------------
# Pre-edit snapshot on file-touching tools
# ---------------------------------------------------------------------------


def test_record_pre_edit_captures_existing_content_on_edit(tmp_path, monkeypatch):
    target = tmp_path / "file_to_edit.py"
    target.write_text("# original content\nprint('hello')\n", encoding="utf-8")

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Edit",
        {
            "path": str(target),
            "old_str": "hello",
            "new_str": "goodbye",
        },
        raw={"type": "tool_use", "name": "Edit"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target))
    assert last is not None
    assert last.content == "# original content\nprint('hello')\n"
    assert "Edit" in (last.narration or "")


def test_record_pre_edit_captures_for_write(tmp_path):
    target = tmp_path / "to_overwrite.py"
    target.write_text("BEFORE", encoding="utf-8")

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Write",
        {"file_path": str(target), "content": "AFTER"},
        raw={"type": "tool_use", "name": "Write"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target))
    assert last is not None
    assert last.content == "BEFORE"


def test_record_pre_edit_captures_none_for_new_file_write(tmp_path):
    """When Write targets a missing file, FileHistory records content=None
    so undo_last can delete the file."""
    target = tmp_path / "brand_new.py"
    assert not target.exists()

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Write",
        {"file_path": str(target), "content": "new code"},
        raw={"type": "tool_use", "name": "Write"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target))
    assert last is not None
    # The FileHistory.record_pre_edit contract: missing file -> content=None
    # so undo_last knows to delete the file.
    assert last.content is None


def test_record_pre_edit_captures_for_multiedit(tmp_path):
    target = tmp_path / "multi.py"
    target.write_text("multi-edit baseline", encoding="utf-8")

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "MultiEdit",
        {
            "file_path": str(target),
            "edits": [
                {"old_str": "multi-edit", "new_str": "edited"},
                {"old_str": "baseline", "new_str": "newline"},
            ],
        },
        raw={"type": "tool_use", "name": "MultiEdit"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target))
    assert last is not None
    assert last.content == "multi-edit baseline"


def test_record_pre_edit_skips_for_non_file_tools(tmp_path):
    """Read / Bash / Glob / etc. don't touch files -- no snapshot."""
    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Read",
        {"file_path": str(tmp_path / "foo.txt")},
        raw={"type": "tool_use", "name": "Read"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    # No snapshot recorded.
    last = history.peek_last(str(tmp_path / "foo.txt"))
    assert last is None


def test_record_pre_edit_relative_path_resolves_against_cwd(tmp_path):
    target = tmp_path / "rel.py"
    target.write_text("rel content", encoding="utf-8")

    handle = _build_handle(tmp_path)
    # Pass a relative path that requires cwd resolution.
    handle._record_tool_use(
        "Edit",
        {"path": "rel.py", "old_str": "rel", "new_str": "abs"},
        raw={"type": "tool_use", "name": "Edit"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target.resolve()))
    assert last is not None
    assert last.content == "rel content"


def test_record_pre_edit_swallows_read_errors(tmp_path, caplog, monkeypatch):
    """A read failure inside record_pre_edit must NOT abort the
    bridge -- the FILE_CHANGE event must still emit normally."""
    handle = _build_handle(tmp_path)

    # Patch FileHistory.record_pre_edit to raise.
    class _BrokenHistory:
        def record_pre_edit(self, *a, **kw):
            raise RuntimeError("disk fault")

    monkeypatch.setattr(
        "kenning.coding.file_history.get_file_history",
        lambda session_id: _BrokenHistory(),
    )

    captured = []
    handle.add_listener(lambda ev: captured.append(ev))

    target = tmp_path / "broken.py"
    target.write_text("x", encoding="utf-8")
    handle._record_tool_use(
        "Edit",
        {"path": str(target), "old_str": "x", "new_str": "y"},
        raw={"type": "tool_use", "name": "Edit"},
    )

    # FILE_CHANGE + TOOL_USE events should still fire.
    kinds = [getattr(ev, "kind", None) for ev in captured]
    from kenning.coding.bridge import EventKind
    assert EventKind.FILE_CHANGE in kinds
    assert EventKind.TOOL_USE in kinds


def test_record_pre_edit_disabled_via_config(tmp_path, monkeypatch):
    """When ``coding.pre_edit_snapshot.enabled=False``, the snapshot
    branch is bypassed entirely."""
    from kenning.config import get_config
    cfg = get_config().coding
    monkeypatch.setattr(cfg.pre_edit_snapshot, "enabled", False)

    target = tmp_path / "noop.py"
    target.write_text("baseline", encoding="utf-8")

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Edit",
        {"path": str(target), "old_str": "baseline", "new_str": "edited"},
        raw={"type": "tool_use", "name": "Edit"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target.resolve()))
    assert last is None


def test_record_pre_edit_session_id_keys_history(tmp_path):
    """Snapshots from different sessions live in separate histories."""
    target = tmp_path / "shared.py"
    target.write_text("shared", encoding="utf-8")

    handle_a = _build_handle(tmp_path, session_id="session-A")
    handle_b = _build_handle(tmp_path, session_id="session-B")

    handle_a._record_tool_use(
        "Edit",
        {"path": str(target), "old_str": "shared", "new_str": "a"},
        raw={"type": "tool_use", "name": "Edit"},
    )
    handle_b._record_tool_use(
        "Edit",
        {"path": str(target), "old_str": "shared", "new_str": "b"},
        raw={"type": "tool_use", "name": "Edit"},
    )

    from kenning.coding.file_history import get_file_history
    ha = get_file_history("session-A")
    hb = get_file_history("session-B")
    assert ha is not hb
    assert ha.peek_last(str(target.resolve())) is not None
    assert hb.peek_last(str(target.resolve())) is not None


def test_record_pre_edit_undo_round_trip(tmp_path):
    """End-to-end: snapshot + undo restores the pre-edit content."""
    target = tmp_path / "round_trip.py"
    target.write_text("ORIGINAL", encoding="utf-8")

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Edit",
        {"path": str(target), "old_str": "ORIGINAL", "new_str": "MUTATED"},
        raw={"type": "tool_use", "name": "Edit"},
    )

    # Simulate the CLI's tool executor writing the new content.
    target.write_text("MUTATED", encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "MUTATED"

    # Undo via FileHistory should restore.
    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    result = history.undo_last(str(target.resolve()))
    assert result.applied is True
    assert target.read_text(encoding="utf-8") == "ORIGINAL"


def test_record_pre_edit_narration_carries_tool_name(tmp_path):
    target = tmp_path / "narr.py"
    target.write_text("orig", encoding="utf-8")

    handle = _build_handle(tmp_path)
    handle._record_tool_use(
        "Write",
        {"file_path": str(target), "content": "totally new content"},
        raw={"type": "tool_use", "name": "Write"},
    )

    from kenning.coding.file_history import get_file_history
    history = get_file_history(handle.claude_session_id)
    last = history.peek_last(str(target.resolve()))
    assert last is not None
    assert "Write" in (last.narration or "")
