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

from kenning.subprocess.process_registry import (
    JobState,
    get_process_registry,
    reset_process_registry_for_testing,
)
from kenning.subprocess.zombie_killer import (
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
    from kenning.transcription import parakeet_engine as pe_mod

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

    import kenning.subprocess.kill_tree as kt_mod

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
    from kenning.tts.xtts_v3 import XttsV3Speech

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
    from kenning.coding.bridge import TaskState, _StateMutex
    from kenning.coding.direct_bridge import DirectTaskHandle

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
    from kenning.coding import direct_bridge as db_mod
    from kenning.coding.direct_bridge import DirectTaskHandle

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


# ---------------------------------------------------------------------------
# Session-lifetime sidecars (embedder + twitch read/guard/write) MUST be
# registered PERSISTENT so the ZombieKiller's staleness reaper never force-
# kills a healthy long-lived sidecar mid-stream.
#
# REGRESSION (2026-06-26): these were registered ``persistent=False,
# hard_timeout_s=3600.0``. On a stream that runs longer than an hour the
# reaper terminated all of them at ~age 3600s (observed in reboot6.err:
# "terminated stale subprocess: ... twitch_read-sidecar age=3630s"), leaving
# only the orchestrator alive so chat/redeems/moderation/raid silently died.
# ---------------------------------------------------------------------------


def _bare_orchestrator():
    """An Orchestrator shell (``__new__``) with only the attrs the sidecar
    spawn path touches -- no audio/LLM/STT stack is constructed."""
    from kenning.pipeline.orchestrator import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch._zombie_killer = get_zombie_killer()
    orch._twitch_sidecar_procs = None
    return orch


def test_twitch_sidecars_registered_persistent(monkeypatch):
    """``_start_twitch_sidecars`` must register each spawned sidecar with the
    ZombieKiller as PERSISTENT (never auto-killed by the staleness reaper)."""
    import kenning.pipeline.orchestrator as orch_mod
    from kenning.twitch.sidecar_launch import SidecarSpec

    orch = _bare_orchestrator()
    killer = orch._zombie_killer

    # Plan two sidecars deterministically (avoid depending on live config).
    specs = [
        SidecarSpec(role="twitch_read",
                    script="scripts/twitch_read_sidecar.py", port=8773, env={}),
        SidecarSpec(role="twitch_guard",
                    script="scripts/twitch_guard_sidecar.py", port=8774, env={}),
    ]
    monkeypatch.setattr(orch_mod, "plan_sidecars", lambda _tcfg: specs,
                        raising=False)
    # The method imports plan_sidecars locally from kenning.twitch.sidecar_launch.
    import kenning.twitch.sidecar_launch as sl_mod
    monkeypatch.setattr(sl_mod, "plan_sidecars", lambda _tcfg: specs)

    # Script-path existence check must pass; never touch the real FS/interpreter.
    monkeypatch.setattr(orch_mod.os.path, "exists", lambda _p: True)

    pids = iter([41001, 41002])

    class _FakeProc:
        def __init__(self, *_a, **_k):
            self.pid = next(pids)

    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", _FakeProc)

    orch._start_twitch_sidecars(tcfg=object())

    read = killer.lookup(41001)
    guard = killer.lookup(41002)
    assert read is not None and read.persistent is True
    assert guard is not None and guard.persistent is True
    # And NO finite 1h timeout left behind (the regression's smoking gun).
    assert read.hard_timeout_s is None
    assert guard.hard_timeout_s is None


def test_twitch_sidecar_paths_anchor_to_project_root_not_cwd(monkeypatch, tmp_path):
    """A launch from a FOREIGN cwd must still find ``scripts/twitch_*.py``.

    2026-07-23 machine move: the venv ``python.exe`` re-execs the base
    interpreter, which inherits the LAUNCHING SHELL's cwd. Started from an
    admin PowerShell (cwd ``C:\\WINDOWS\\system32``), the old
    ``os.path.abspath(spec.script)`` resolved to ``<cwd>/scripts/...`` -> every
    sidecar logged "script missing" and NONE spawned, so all redeem/chat-game/
    chat-reply drains timed out and the guard stayed DOWN (chat replies
    fail-closed OFF). Pin script path, log dir and child cwd to PROJECT_ROOT.
    """
    import kenning.pipeline.orchestrator as orch_mod
    from kenning.config import PROJECT_ROOT
    from kenning.twitch.sidecar_launch import SidecarSpec

    orch = _bare_orchestrator()

    specs = [SidecarSpec(role="twitch_read",
                         script="scripts/twitch_read_sidecar.py",
                         port=8773, env={})]
    import kenning.twitch.sidecar_launch as sl_mod
    monkeypatch.setattr(sl_mod, "plan_sidecars", lambda _tcfg: specs)
    monkeypatch.setattr(orch_mod, "plan_sidecars", lambda _tcfg: specs,
                        raising=False)

    # Simulate the foreign launch cwd. The real script must still be found, so
    # NO os.path.exists stub here -- that is exactly what the bug defeated.
    monkeypatch.chdir(tmp_path)

    seen: dict = {}

    class _FakeProc:
        def __init__(self, argv, *_a, **kw):
            seen["argv"] = argv
            seen["cwd"] = kw.get("cwd")
            self.pid = 41010

    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", _FakeProc)

    orch._start_twitch_sidecars(tcfg=object())

    expected = str((PROJECT_ROOT / "scripts/twitch_read_sidecar.py").resolve())
    assert seen.get("argv"), "sidecar never spawned -- script path lost to cwd"
    assert seen["argv"][1] == expected
    # The child must not inherit the foreign cwd either.
    assert seen["cwd"] == str(PROJECT_ROOT)
    # ...and the per-role log lands in the repo, not <foreign cwd>/logs.
    assert not (tmp_path / "logs" / "twitch_sidecars").exists()


def test_persistent_sidecar_survives_staleness_sweep_past_one_hour():
    """The exact bug condition: a sidecar that lived past the old 3600s cap is
    NOT killed by the staleness sweep when registered persistent."""
    from kenning.subprocess import zombie_killer as zk_mod

    clock = {"t": 0.0}
    killed: list[int] = []
    killer = zk_mod.ZombieKiller(
        hard_timeout_s=3600.0,            # the OLD finite cap
        poll_interval_s=1000.0,
        clock=lambda: clock["t"],
        terminator=lambda pid: (killed.append(pid) or True),
        rss_probe=lambda _pid: 0,
    )
    killer.register(55001, "twitch_read-sidecar", persistent=True)
    killer.register(55002, "embedder-sidecar", persistent=True)

    clock["t"] = 4000.0                   # well past one hour (the observed ~3630s)
    killer.sweep_once()

    assert killed == []                   # neither healthy daemon was reaped
    assert killer.lookup(55001) is not None
    assert killer.lookup(55002) is not None


def test_nonpersistent_with_finite_timeout_would_have_been_killed():
    """Pins the OLD (buggy) behaviour so the regression can't silently return:
    a non-persistent 3600s registration IS reaped past the cap. Documents what
    the fix prevents."""
    from kenning.subprocess import zombie_killer as zk_mod

    clock = {"t": 0.0}
    killed: list[int] = []
    killer = zk_mod.ZombieKiller(
        hard_timeout_s=600.0,
        poll_interval_s=1000.0,
        clock=lambda: clock["t"],
        terminator=lambda pid: (killed.append(pid) or True),
        rss_probe=lambda _pid: 0,
    )
    killer.register(56001, "twitch_read-sidecar",
                    persistent=False, hard_timeout_s=3600.0)
    clock["t"] = 3630.0
    killer.sweep_once()
    assert killed == [56001]              # the pre-fix outcome the bug produced
