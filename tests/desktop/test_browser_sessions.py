"""Tests for the browser-use session manager (catalog 10 batch 5).

All dependencies mocked via injected factories / fakes; no real
``browser-use`` binary, no real ProcessRegistry singleton mutation,
no network. Per ``docs/test_sweep_binding_rules.md``: R1 (monkeypatch
/ injection only), R4 (no network), R7 (order-independent), R11 (no
voice stack).
"""

from __future__ import annotations

from typing import Any

import pytest

from kenning.desktop import browser_sessions as bs
from kenning.desktop.browser_use import BrowserUseResult


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeTool:
    """Stand-in for BrowserUseTool bound to a session."""

    def __init__(self, session: str) -> None:
        self.session = session
        self.close_calls = 0
        self.close_succeeds = True

    def close(self) -> BrowserUseResult:
        self.close_calls += 1
        return BrowserUseResult(
            success=self.close_succeeds,
            action="close",
            error=None if self.close_succeeds else "daemon hung",
        )


class _FakeProcessRegistry:
    def __init__(self) -> None:
        self.registered: list[str] = []
        self.exited: list[str] = []

    def register(self, *, job_id: str, **kwargs: Any) -> Any:
        self.registered.append(job_id)
        return object()

    def mark_exited(self, job_id: str, *, exit_code: int = 0) -> bool:
        self.exited.append(job_id)
        return True


class _FakeValidator:
    def __init__(self) -> None:
        from kenning.safety.validator import ValidatorVerdict, Verdict

        self.contexts: list = []
        self._allow = ValidatorVerdict(verdict=Verdict.ALLOW, reason="ok")
        self.next_verdict = self._allow

    def check(self, ctx: Any) -> Any:
        self.contexts.append(ctx)
        return self.next_verdict

    def block(self, message: str = "blocked") -> None:
        from kenning.safety.validator import ValidatorVerdict, Verdict

        self.next_verdict = ValidatorVerdict(
            verdict=Verdict.BLOCK_HARD,
            reason=message,
            user_message=message,
        )


class _FakeApprovalRegistry:
    def __init__(self) -> None:
        from kenning.safety.two_phase_approval import ApprovalHandle

        self.registrations: list = []
        self._n = 0
        self._handle_cls = ApprovalHandle

    def register(self, request: Any) -> Any:
        self.registrations.append(request)
        self._n += 1
        return self._handle_cls(
            approval_id=f"appr-{self._n}",
            expires_at_seconds=999.0,
            request=request,
            pre_resolved=None,
        )


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    bs.reset_browser_sessions_manager_for_testing()
    yield
    bs.reset_browser_sessions_manager_for_testing()


@pytest.fixture
def fake_validator(monkeypatch: pytest.MonkeyPatch) -> _FakeValidator:
    fake = _FakeValidator()
    monkeypatch.setattr(bs, "get_validator", lambda: fake)
    return fake


@pytest.fixture
def fake_registry() -> _FakeProcessRegistry:
    return _FakeProcessRegistry()


@pytest.fixture
def manager(
    fake_validator: _FakeValidator, fake_registry: _FakeProcessRegistry
) -> bs.BrowserSessionsManager:
    tools: dict[str, _FakeTool] = {}

    def factory(name: str) -> Any:
        t = _FakeTool(name)
        tools[name] = t
        return t

    mgr = bs.BrowserSessionsManager(
        tool_factory=factory,
        max_sessions=3,
        process_registry=fake_registry,
        kill_callable=lambda pid: None,
    )
    mgr._test_tools = tools  # type: ignore[attr-defined]
    return mgr


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_max_sessions_clamped_low(self) -> None:
        m = bs.BrowserSessionsManager(max_sessions=0)
        assert m.max_sessions == 1

    def test_max_sessions_clamped_high(self) -> None:
        m = bs.BrowserSessionsManager(max_sessions=999)
        assert m.max_sessions == bs.MAX_HARD_SESSIONS

    def test_default_max(self) -> None:
        m = bs.BrowserSessionsManager()
        assert m.max_sessions == bs.DEFAULT_MAX_SESSIONS


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_canonical(
        self,
        manager: bs.BrowserSessionsManager,
        fake_registry: _FakeProcessRegistry,
    ) -> None:
        result = manager.create_session("scraper", user_text="open scraper")
        assert result.success is True
        assert result.session is not None
        assert result.session.name == "scraper"
        assert manager.has_session("scraper")
        assert manager.session_count() == 1
        # Registered for lifecycle tracking.
        assert "browser_use_session:scraper" in fake_registry.registered

    def test_empty_name_rejected(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        result = manager.create_session("   ", user_text="x")
        assert result.success is False
        assert "empty" in (result.error or "")

    def test_invalid_name_rejected(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        result = manager.create_session("has spaces", user_text="x")
        assert result.success is False
        assert "match" in (result.error or "")

    def test_duplicate_rejected(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        result = manager.create_session("a", user_text="x")
        assert result.success is False
        assert "already exists" in (result.error or "")

    def test_cap_enforced(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        manager.create_session("b", user_text="x")
        manager.create_session("c", user_text="x")
        result = manager.create_session("d", user_text="x")
        assert result.success is False
        assert "cap reached" in (result.error or "")
        assert manager.session_count() == 3

    def test_safety_block(
        self,
        manager: bs.BrowserSessionsManager,
        fake_validator: _FakeValidator,
    ) -> None:
        fake_validator.block("not allowed")
        result = manager.create_session("a", user_text="x")
        assert result.success is False
        assert result.safety_verdict == "BLOCK_HARD"
        assert not manager.has_session("a")

    def test_get_tool_after_create(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        tool = manager.get_tool("a")
        assert tool is not None
        assert tool.session == "a"

    def test_validator_context_shape(
        self,
        manager: bs.BrowserSessionsManager,
        fake_validator: _FakeValidator,
    ) -> None:
        manager.create_session("a", browser_kind="headed", user_text="open")
        ctx = fake_validator.contexts[0]
        assert ctx.tool_name == "desktop.browser_use.session.create_session"
        assert ctx.capability == "desktop_browser_use"
        assert ctx.arguments["name"] == "a"
        assert ctx.arguments["browser_kind"] == "headed"


# ---------------------------------------------------------------------------
# list / get
# ---------------------------------------------------------------------------


class TestListSessions:
    def test_empty(self, manager: bs.BrowserSessionsManager) -> None:
        assert manager.list_sessions() == ()

    def test_newest_first(
        self, fake_validator: _FakeValidator
    ) -> None:
        # Inject a deterministic incrementing clock so the two
        # created_at timestamps never tie (a real monotonic clock
        # can return identical values for two rapid calls).
        ticks = iter([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        mgr = bs.BrowserSessionsManager(
            tool_factory=lambda name: _FakeTool(name),
            process_registry=_FakeProcessRegistry(),
            clock=lambda: next(ticks),
        )
        mgr.create_session("a", user_text="x")
        mgr.create_session("b", user_text="x")
        names = [s.name for s in mgr.list_sessions()]
        # newest-first -> b before a
        assert names == ["b", "a"]

    def test_get_tool_missing_returns_none(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        assert manager.get_tool("nope") is None


# ---------------------------------------------------------------------------
# close_session
# ---------------------------------------------------------------------------


class TestCloseSession:
    def test_canonical(
        self,
        manager: bs.BrowserSessionsManager,
        fake_registry: _FakeProcessRegistry,
    ) -> None:
        manager.create_session("a", user_text="x")
        result = manager.close_session("a", user_text="close a")
        assert result.success is True
        assert result.closed_names == ("a",)
        assert not manager.has_session("a")
        assert "browser_use_session:a" in fake_registry.exited

    def test_calls_tool_close(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        tool = manager._test_tools["a"]  # type: ignore[attr-defined]
        manager.close_session("a", user_text="close")
        assert tool.close_calls == 1

    def test_missing_session(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        result = manager.close_session("nope", user_text="close")
        assert result.success is False
        assert "not found" in (result.error or "")

    def test_empty_name(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        result = manager.close_session("  ", user_text="close")
        assert result.success is False

    def test_safety_block(
        self,
        manager: bs.BrowserSessionsManager,
        fake_validator: _FakeValidator,
    ) -> None:
        manager.create_session("a", user_text="x")
        fake_validator.block("no closing")
        result = manager.close_session("a", user_text="close")
        assert result.success is False
        # Session NOT removed when blocked.
        assert manager.has_session("a")

    def test_cli_close_failure_surfaced(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        tool = manager._test_tools["a"]  # type: ignore[attr-defined]
        tool.close_succeeds = False
        result = manager.close_session("a", user_text="close")
        # The session is still removed, but the CLI error is surfaced.
        assert result.success is False
        assert "daemon hung" in (result.error or "")
        assert not manager.has_session("a")

    def test_force_kills_pid(
        self, fake_validator: _FakeValidator
    ) -> None:
        killed: list[int] = []
        mgr = bs.BrowserSessionsManager(
            tool_factory=lambda name: _FakeTool(name),
            kill_callable=lambda pid: killed.append(pid),
        )
        mgr.create_session("a", user_text="x")
        # Inject a known pid onto the session entry.
        with mgr._lock:  # type: ignore[attr-defined]
            sess = mgr._sessions["a"]  # type: ignore[attr-defined]
            mgr._sessions["a"] = bs.BrowserSession(  # type: ignore[attr-defined]
                name=sess.name,
                browser_kind=sess.browser_kind,
                created_at=sess.created_at,
                last_seen=sess.last_seen,
                pid=4321,
            )
        mgr.close_session("a", user_text="force close", force=True)
        assert killed == [4321]

    def test_cap_frees_after_close(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        manager.create_session("b", user_text="x")
        manager.create_session("c", user_text="x")
        manager.close_session("a", user_text="close")
        # Now there's room for a new one.
        result = manager.create_session("d", user_text="x")
        assert result.success is True


# ---------------------------------------------------------------------------
# close_all_sessions
# ---------------------------------------------------------------------------


class TestCloseAllSessions:
    def test_empty_is_noop_success(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        result = manager.close_all_sessions(user_text="close all")
        assert result.success is True
        assert result.closed_names == ()

    def test_requires_approval(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        manager.create_session("b", user_text="x")
        registry = _FakeApprovalRegistry()
        result = manager.close_all_sessions(
            user_text="close all",
            approval_registry=registry,
        )
        assert result.success is False
        assert result.requires_two_phase is True
        assert result.approval_request_id == "appr-1"
        # Sessions still alive -- approval not yet granted.
        assert manager.session_count() == 2
        req = registry.registrations[0]
        assert req.kind == bs.BROWSER_SESSION_APPROVAL_KIND
        assert req.metadata["reason_code"] == bs.BROWSER_SESSION_REASON_CODE
        assert set(req.metadata["session_names"]) == {"a", "b"}

    def test_preapproved_closes_all(
        self,
        manager: bs.BrowserSessionsManager,
        fake_registry: _FakeProcessRegistry,
    ) -> None:
        manager.create_session("a", user_text="x")
        manager.create_session("b", user_text="x")
        result = manager.close_all_sessions(
            user_text="close all",
            assume_preapproved=True,
        )
        assert result.success is True
        assert set(result.closed_names) == {"a", "b"}
        assert manager.session_count() == 0

    def test_preapproved_partial_failure(
        self, manager: bs.BrowserSessionsManager
    ) -> None:
        manager.create_session("a", user_text="x")
        manager.create_session("b", user_text="x")
        # Make one tool's close fail.
        manager._test_tools["a"].close_succeeds = False  # type: ignore[attr-defined]
        result = manager.close_all_sessions(
            user_text="close all",
            assume_preapproved=True,
        )
        assert result.success is False
        assert "a:" in (result.error or "")
        # Both still removed from tracking (close removes regardless).
        assert manager.session_count() == 0


# ---------------------------------------------------------------------------
# Singleton + helpers
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_round_trip(self) -> None:
        m = bs.BrowserSessionsManager()
        bs.set_browser_sessions_manager(m)
        assert bs.get_browser_sessions_manager() is m

    def test_default_none(self) -> None:
        assert bs.get_browser_sessions_manager() is None


class TestHelpers:
    def test_registry_job_id(self) -> None:
        assert bs._registry_job_id("foo") == "browser_use_session:foo"

    def test_default_tool_factory_binds_session(self) -> None:
        tool = bs._default_tool_factory("agent-1")
        assert tool.session == "agent-1"

    def test_all_exports_present(self) -> None:
        for name in bs.__all__:
            assert hasattr(bs, name)
