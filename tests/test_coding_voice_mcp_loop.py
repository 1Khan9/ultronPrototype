"""Tests for the B3 voice->MCP wiring on :class:`CodingVoiceController`.

Regression coverage for the production-hardening campaign: voice-dispatched
coding tasks must write a per-project ``.mcp.json`` pointing at the live
Ultron MCP server (so the spawned subprocess can call request_clarification /
report_progress / declare_complete back into the coordinator + verifier loop),
register a ProjectSession so ``_claude_active_session`` resolves, and set a hard
``timeout_s`` on supervisor-built requests. The ``.mcp.json`` is deliberately
NOT removed on completion (send_followup reuses it for follow-ups +
corrections). All paths are fail-open: when no MCP server is wired the task still
runs bridge-only, exactly as before.

Self-contained (own fake bridge/handle) so it stands alone.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

from ultron.coding.bridge import (
    CodingBridge,
    EventKind,
    EventListener,
    TaskEvent,
    TaskHandle,
    TaskRequest,
    TaskResult,
    TaskState,
)
from ultron.coding.projects import ProjectRegistry, ProjectResolver
from ultron.coding.runner import CodingTaskRunner
from ultron.coding.voice import CodingVoiceController


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


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

    def task_id(self) -> str:
        return "fake"

    def state(self) -> TaskState:
        return self._state

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def cancel(self) -> None:
        self._state.is_cancelled = True

    def wait(self, timeout=None) -> Optional[TaskResult]:
        return None

    def is_running(self) -> bool:
        return not self._done.is_set()

    def fire(self, event: TaskEvent) -> None:
        for L in list(self._listeners):
            L(event)


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


class _RunningServer:
    """Minimal stand-in for a live UltronMCPServer."""

    def __init__(self, sse_url: str = "http://127.0.0.1:19761/sse"):
        self._sse = sse_url

    def is_running(self) -> bool:
        return True

    @property
    def sse_url(self) -> str:
        return self._sse


class _StoppedServer:
    def is_running(self) -> bool:
        return False

    @property
    def sse_url(self) -> str:
        return "http://127.0.0.1:19761/sse"


class _BadServer:
    """is_running True but sse_url raises -> exercises the fail-open branch."""

    def is_running(self) -> bool:
        return True

    @property
    def sse_url(self) -> str:
        raise RuntimeError("boom")


class _FakeSession:
    def __init__(self, sid: str):
        self.session_id = sid


class _FakeStore:
    def __init__(self):
        self.created: list = []
        self.transitions: list = []

    def create(self, *, project_root, user_intent, mode, model):
        self.created.append({
            "project_root": project_root, "user_intent": user_intent,
            "mode": mode, "model": model,
        })
        return _FakeSession("sess-1")

    def transition(self, sid, status):
        self.transitions.append((sid, status))


class _FakeCoordinator:
    def __init__(self, store):
        self.store = store


def _make_controller(tmp_path: Path, *, mcp_server=None, coordinator=None):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir(exist_ok=True)
    registry = ProjectRegistry(path=tmp_path / "projects.json")
    resolver = ProjectResolver(registry, embedder=None)
    bridge = _FakeBridge()
    runner = CodingTaskRunner(bridge=bridge, log_path=tmp_path / "log.jsonl")
    controller = CodingVoiceController(
        runner=runner, registry=registry, resolver=resolver,
        sandbox_root=sandbox, coordinator=coordinator, mcp_server=mcp_server,
    )
    return controller, bridge, runner


# --------------------------------------------------------------------------
# _maybe_write_mcp_config
# --------------------------------------------------------------------------


def test_maybe_write_mcp_config_none_when_no_server(tmp_path):
    controller, *_ = _make_controller(tmp_path, mcp_server=None)
    proj = tmp_path / "p"
    proj.mkdir()
    assert controller._maybe_write_mcp_config(proj) is None
    assert not (proj / ".mcp.json").exists()


def test_maybe_write_mcp_config_none_when_server_stopped(tmp_path):
    controller, *_ = _make_controller(tmp_path, mcp_server=_StoppedServer())
    proj = tmp_path / "p"
    proj.mkdir()
    assert controller._maybe_write_mcp_config(proj) is None
    assert not (proj / ".mcp.json").exists()


def test_maybe_write_mcp_config_writes_real_file_when_running(tmp_path):
    controller, *_ = _make_controller(tmp_path, mcp_server=_RunningServer())
    proj = tmp_path / "p"
    proj.mkdir()
    path = controller._maybe_write_mcp_config(proj)
    assert path is not None and path.exists()
    assert path == proj / ".mcp.json"
    blob = json.dumps(json.loads(path.read_text()))
    assert "127.0.0.1:19761" in blob


def test_maybe_write_mcp_config_fail_open_on_error(tmp_path):
    controller, *_ = _make_controller(tmp_path, mcp_server=_BadServer())
    proj = tmp_path / "p"
    proj.mkdir()
    # sse_url raises -> the method must swallow it and return None.
    assert controller._maybe_write_mcp_config(proj) is None


# --------------------------------------------------------------------------
# RESUME follow-up listener re-attach + .mcp.json survives COMPLETE
# --------------------------------------------------------------------------


def test_resume_followup_reattaches_listeners(tmp_path, monkeypatch):
    """RESUME_FORWARD + the verifier's corrective re-prompt spawn a fresh
    handle, so the digest + voice-lock-review listeners must be re-attached
    to it (the original handle's listeners do not carry over)."""
    controller, bridge, runner = _make_controller(tmp_path)
    proj = tmp_path / "sandbox" / "myproj"
    proj.mkdir(parents=True)
    monkeypatch.setattr(runner, "active_state", lambda: SimpleNamespace(cwd=proj))
    calls = {"digest": [], "review": []}
    monkeypatch.setattr(controller, "_attach_supervisor_digest_listener",
                        lambda **kw: calls["digest"].append(kw))
    monkeypatch.setattr(controller, "_attach_submit_review_listener",
                        lambda **kw: calls["review"].append(kw))
    followup = _FakeHandle(TaskRequest(task_prompt="now add X", cwd=proj))
    controller._attach_resume_followup_listeners(followup, "now add X")
    assert len(calls["digest"]) == 1 and len(calls["review"]) == 1
    assert calls["digest"][0]["project_name"] == "myproj"
    assert calls["digest"][0]["handle"] is followup
    assert calls["digest"][0]["project_path"] == proj


def test_resume_followup_listeners_noop_without_active_state(tmp_path, monkeypatch):
    controller, bridge, runner = _make_controller(tmp_path)
    monkeypatch.setattr(runner, "active_state", lambda: None)
    called = []
    monkeypatch.setattr(controller, "_attach_supervisor_digest_listener",
                        lambda **kw: called.append(kw))
    monkeypatch.setattr(controller, "_attach_submit_review_listener",
                        lambda **kw: called.append(kw))
    controller._attach_resume_followup_listeners(
        _FakeHandle(TaskRequest(task_prompt="x", cwd=tmp_path)), "x",
    )
    assert called == []


def test_dispatch_keeps_mcp_config_after_complete(tmp_path, monkeypatch):
    """Regression: the .mcp.json must survive COMPLETE so send_followup()
    (RESUME + corrections) can reuse the runner's stored mcp_config_path.
    Earlier code deleted it on COMPLETE, stripping MCP from every follow-up."""
    controller, bridge, runner = _make_controller(tmp_path, mcp_server=_RunningServer())
    monkeypatch.setattr(controller, "_attach_supervisor_digest_listener", lambda **kw: None)
    monkeypatch.setattr(controller, "_attach_submit_review_listener", lambda **kw: None)
    proj = tmp_path / "sandbox" / "keepproj"
    req = TaskRequest(task_prompt="build it", cwd=proj, model="haiku", label="new:keepproj")
    outcome = SimpleNamespace(
        task_request=req, decision=None, already_narrated=True, voice_message="",
    )
    controller._dispatch_supervisor_task(SimpleNamespace(task_text="build it"), outcome)
    mcp_path = req.mcp_config_path
    assert mcp_path is not None and mcp_path.exists()
    # Fire COMPLETE -> the .mcp.json must REMAIN for follow-ups/corrections.
    bridge.last.fire(TaskEvent(kind=EventKind.COMPLETE))
    assert mcp_path.exists()


# --------------------------------------------------------------------------
# _create_and_bind_session
# --------------------------------------------------------------------------


def test_create_and_bind_session_noop_without_coordinator(tmp_path):
    controller, *_ = _make_controller(tmp_path, coordinator=None)
    assert controller._create_and_bind_session(tmp_path, "do x", is_new=True) is None


def test_create_and_bind_session_creates_and_binds(tmp_path, monkeypatch):
    store = _FakeStore()
    controller, bridge, runner = _make_controller(
        tmp_path, coordinator=_FakeCoordinator(store),
    )
    bound: list = []
    monkeypatch.setattr(runner, "bind_session", lambda sid: bound.append(sid))
    sid = controller._create_and_bind_session(tmp_path / "proj", "add tests", is_new=False)
    assert sid == "sess-1"
    assert len(store.created) == 1
    assert store.created[0]["mode"] == "edit"
    assert bound == ["sess-1"]


# --------------------------------------------------------------------------
# Supervisor dispatch path integration
# --------------------------------------------------------------------------


def test_dispatch_supervisor_task_sets_timeout_and_mcp_config(tmp_path, monkeypatch):
    controller, bridge, runner = _make_controller(tmp_path, mcp_server=_RunningServer())
    # Isolate from the digest / submit-review listeners (orthogonal here).
    monkeypatch.setattr(controller, "_attach_supervisor_digest_listener", lambda **kw: None)
    monkeypatch.setattr(controller, "_attach_submit_review_listener", lambda **kw: None)

    proj = tmp_path / "sandbox" / "myproj"
    req = TaskRequest(task_prompt="build it", cwd=proj, model="haiku", label="new:myproj")
    assert req.timeout_s is None and req.mcp_config_path is None  # supervisor builder omits both
    outcome = SimpleNamespace(
        task_request=req, decision=None, already_narrated=True, voice_message="",
    )
    intent = SimpleNamespace(task_text="build it")

    controller._dispatch_supervisor_task(intent, outcome)

    assert req.timeout_s is not None and req.timeout_s > 0
    assert req.mcp_config_path is not None and req.mcp_config_path.exists()
    assert bridge.last_request is req


def test_dispatch_supervisor_task_fail_open_without_server(tmp_path, monkeypatch):
    controller, bridge, runner = _make_controller(tmp_path, mcp_server=None)
    monkeypatch.setattr(controller, "_attach_supervisor_digest_listener", lambda **kw: None)
    monkeypatch.setattr(controller, "_attach_submit_review_listener", lambda **kw: None)
    proj = tmp_path / "sandbox" / "p2"
    req = TaskRequest(task_prompt="edit it", cwd=proj, model="haiku", label="edit:p2")
    outcome = SimpleNamespace(
        task_request=req, decision=None, already_narrated=True, voice_message="",
    )
    controller._dispatch_supervisor_task(SimpleNamespace(task_text="edit it"), outcome)
    # No server -> no mcp config, but timeout is still set and the task runs.
    assert req.mcp_config_path is None
    assert req.timeout_s is not None and req.timeout_s > 0
    assert bridge.last_request is req
