"""Wiring tests for T12 ProcessRegistry + T23 ZombieKiller integration at
the real subprocess spawn/stop sites.

These verify the *glue* added by the catalog-port wiring pass -- that the
daemon servers (Parakeet, XTTS) and the coding-bridge subprocess register
with / unregister from the subprocess reaper + process registry -- without
re-testing the primitives themselves (covered by tests/subprocess/). Every
wiring call is fail-open, so these assert the happy-path contract.

All hermetic: no real subprocess, no real network, no voice stack. The
reader threads in DirectTaskHandle are stubbed; the daemon stop paths mock
``requests`` / ``urllib`` / ``kill_process_tree``.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ultron.subprocess.process_registry import (
    JobState,
    get_process_registry,
    reset_process_registry_for_testing,
)
from ultron.subprocess.zombie_killer import (
    get_zombie_killer,
    reset_zombie_killer_for_testing,
)


@pytest.fixture(autouse=True)
def _fresh_singletons():
    """Reset the module-level registry + killer around every test."""
    reset_process_registry_for_testing()
    reset_zombie_killer_for_testing()
    yield
    reset_process_registry_for_testing()
    reset_zombie_killer_for_testing()


# ---------------------------------------------------------------------------
# Parakeet daemon
# ---------------------------------------------------------------------------


def test_parakeet_stop_unregisters_from_zombie_killer(monkeypatch):
    from ultron.transcription import parakeet_engine as pe_mod

    killer = get_zombie_killer()
    killer.register(4242, "parakeet-server", persistent=True)
    assert killer.lookup(4242) is not None

    proc = MagicMock(name="server_proc")
    proc.poll.return_value = None  # alive throughout -> kill_tree path
    proc.pid = 4242
    monkeypatch.setattr(pe_mod, "_SERVER_PROCESS", proc)
    monkeypatch.setattr(pe_mod, "_SERVER_URL_CACHED", "http://127.0.0.1:8771")

    fake_requests = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    import ultron.subprocess.kill_tree as kt_mod

    def _fake_kill_tree(pid, *, grace_seconds=3.0, **_):
        class _Result:
            terminated = (pid,)
            force_killed = ()
            unreachable = ()
        return _Result()

    monkeypatch.setattr(kt_mod, "kill_process_tree", _fake_kill_tree)

    assert pe_mod.stop_parakeet_server(timeout_seconds=1.0) is True
    # The wiring released the registry entry as part of the stop path.
    assert killer.lookup(4242) is None


# ---------------------------------------------------------------------------
# XTTS daemon
# ---------------------------------------------------------------------------


def test_xtts_stop_unregisters_from_zombie_killer(monkeypatch):
    from ultron.tts.xtts_v3 import XttsV3Speech

    killer = get_zombie_killer()
    killer.register(8888, "xtts-server", persistent=True)
    assert killer.lookup(8888) is not None

    # No real network: the /shutdown POST raises and is swallowed.
    def _boom(*_a, **_k):
        raise OSError("no server")

    monkeypatch.setattr("urllib.request.urlopen", _boom)

    fake_proc = MagicMock(name="xtts_proc")
    fake_proc.pid = 8888
    fake_proc.wait.return_value = 0  # graceful -> no kill_tree

    sp = XttsV3Speech.__new__(XttsV3Speech)
    sp._server_proc = fake_proc
    sp.base_url = "http://127.0.0.1:8123"

    sp._stop_server_subprocess()

    assert killer.lookup(8888) is None
    assert sp._server_proc is None


# ---------------------------------------------------------------------------
# Coding-bridge subprocess
# ---------------------------------------------------------------------------


def _make_handle(task_id: str, pid: int, tmp_path):
    """Build a DirectTaskHandle via __new__ with the minimal attrs the
    _launch / _finalize paths touch -- bypasses the real subprocess + the
    directory snapshot in __init__."""
    from ultron.coding.bridge import TaskState, _StateMutex
    from ultron.coding.direct_bridge import DirectTaskHandle

    h = DirectTaskHandle.__new__(DirectTaskHandle)
    h._task_id = task_id
    h._argv = ["claude", "--print"]
    h._cwd = tmp_path
    h._request = SimpleNamespace(label="t", task_prompt="hi", timeout_s=60.0)
    h._log_path = None
    h._proc = SimpleNamespace(pid=pid)
    h._listeners = []
    h._listeners_lock = threading.Lock()
    h._done = threading.Event()
    h._result = None
    h._started_at = time.time()
    h._state = _StateMutex(
        TaskState(label="t", task_prompt="hi", cwd=tmp_path, started_at=h._started_at)
    )
    h._stdout_thread = None
    h._stderr_thread = None
    h._wait_thread = None
    return h


def test_direct_bridge_launch_registers_subprocess(monkeypatch, tmp_path):
    from ultron.coding import direct_bridge as db_mod
    from ultron.coding.direct_bridge import DirectTaskHandle

    h = _make_handle("abc123", 5555, tmp_path)
    h._proc = None  # _launch will set it from the faked Popen

    # Stub the reader/wait threads so nothing reads a real stream.
    h._read_stdout = lambda: None
    h._read_stderr = lambda: None
    h._wait_for_exit = lambda: None

    fake_proc = SimpleNamespace(pid=5555)
    monkeypatch.setattr(db_mod.subprocess, "Popen", lambda *a, **k: fake_proc)

    h._launch()

    reg = get_process_registry()
    killer = get_zombie_killer()
    job = reg.get("claude-abc123")
    assert job is not None
    assert job.pid == 5555
    assert "coding" in job.tags
    assert killer.lookup(5555) is not None


def test_direct_bridge_finalize_releases_tracking(tmp_path):
    h = _make_handle("fin1", 7777, tmp_path)

    reg = get_process_registry()
    killer = get_zombie_killer()
    reg.register("claude-fin1", scope_key="fin1", pid=7777,
                 command="claude", tags=("coding", "claude-cli"))
    killer.register(7777, "claude-cli:fin1", hard_timeout_s=3600.0)

    h._finalize(success=True, exit_status=0, error=None, summary="done")

    assert h._done.is_set()
    job = reg.get("claude-fin1")
    assert job is not None and job.state == JobState.EXITED
    assert killer.lookup(7777) is None
