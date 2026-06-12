"""Named-session isolation for the browser-use CLI tier.

Catalog 10 batch 5 (T8 YELLOW). Mirrors the catalog's named-session
model: each session gets its own daemon, socket, PID, and browser
instance, isolated from every other session. The upstream ships
this as a ``--session NAME`` argument on every CLI call; this
module is the kenning-side orchestration layer that:

* validates session names against an allowlist (alphanumeric +
  underscore + hyphen, 1-32 chars) so a name can never become a
  hostile subprocess argument;
* enforces a configurable cap on simultaneous sessions
  (``browser.use.max_sessions``, default 3) so unbounded session
  creation cannot exhaust system memory;
* registers each session's lifecycle in
  :class:`kenning.subprocess.process_registry.ProcessRegistry` so
  ZombieKiller + orchestrator shutdown reap stale daemons cleanly;
* gates ``close_all`` behind two-phase approval (closing every
  session at once is destructive across whatever auth state the
  user had loaded);
* hands out :class:`BrowserUseTool` instances bound to each managed
  session via :meth:`BrowserUseTool.with_session`.

Workflow note: the manager does NOT start a daemon process
explicitly -- daemons spawn lazily on the first CLI call (per the
upstream's daemon model). The manager tracks WHICH session names
are active + holds the bound :class:`BrowserUseTool` instances, and
the ProcessRegistry tracks each daemon's lifecycle once a PID is
discovered (via ``cli sessions --json`` polling or attach_pid).

Per the catalog 10 + security review skip list:

* ``--cdp-url`` external URL argument is BLOCKED -- this manager
  never emits it. Connecting to an attacker-supplied CDP URL is an
  exfiltration vector with no legitimate kenning use case.
* ``BROWSER_USE_SESSION`` env var is scrubbed by the underlying
  :class:`BrowserUseTool` so session selection is always explicit.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from kenning.desktop.browser_use import (
    BrowserUseResult,
    BrowserUseTool,
    _is_valid_session_name,
)
from kenning.safety.two_phase_approval import (
    ApprovalRegistry,
    ApprovalRequest,
    get_approval_registry,
)
from kenning.safety.validator import (
    RuleContext,
    Verdict,
    get_validator,
)
from kenning.subprocess.kill_tree import kill_process_tree
from kenning.subprocess.process_registry import (
    ProcessRegistry,
    get_process_registry,
)
from kenning.utils.logging import get_logger

logger = get_logger("desktop.browser_sessions")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


DEFAULT_MAX_SESSIONS: int = 3
MAX_HARD_SESSIONS: int = 16

# ProcessRegistry tag prefix so a single registry lookup surfaces
# every browser-use session.
_PROCESS_TAG: str = "browser_use_session"

# Validator tool-name prefix for the session lifecycle operations.
_TOOL_NAME_PREFIX: str = "desktop.browser_use.session"

# Approval-request kind for ``close_all_sessions`` (the only
# operation that requires two-phase approval at this layer).
BROWSER_SESSION_APPROVAL_KIND: str = "browser_use_close_all_sessions"
BROWSER_SESSION_REASON_CODE: str = (
    "kenning.suspicious.browser_close_all_sessions"
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowserSession:
    """One managed session entry."""

    name: str
    browser_kind: str = "default"
    created_at: float = 0.0
    last_seen: float = 0.0
    pid: Optional[int] = None


@dataclass(frozen=True)
class BrowserSessionResult:
    """Outcome of a session-lifecycle call.

    ``session`` carries the entry for create / get; ``closed_names``
    carries the list for close / close_all; ``requires_two_phase``
    + ``approval_request_id`` populated only for the close_all path.
    """

    success: bool
    action: str
    session: Optional[BrowserSession] = None
    closed_names: tuple[str, ...] = ()
    error: Optional[str] = None
    requires_two_phase: bool = False
    approval_request_id: str = ""
    safety_verdict: str = ""


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


ToolFactory = Callable[[str], BrowserUseTool]


class BrowserSessionsManager:
    """Owns the set of named browser-use sessions for one orchestrator.

    Construction is cheap: no CLI calls, no subprocess, no IO. The
    underlying daemons spawn lazily on the first CLI invocation
    against the bound tool.

    Args:
        tool_factory: callable that builds a :class:`BrowserUseTool`
            for a given session name. ``None`` defaults to
            ``BrowserUseTool(session=name)``. Tests inject a mock.
        max_sessions: cap on simultaneous sessions. Clamped to
            ``[1, MAX_HARD_SESSIONS]``. Default 3 matches the
            catalog 10 + ``BrowserUseConfig.max_sessions`` default.
        process_registry: injected :class:`ProcessRegistry` for
            daemon lifecycle tracking. Defaults to the module
            singleton.
        kill_callable: injected pid-killer for tests. Defaults to
            :func:`kill_process_tree`. Only fires on hard close
            paths -- the normal close uses the CLI's own ``close``.
        clock: time source for tests. Defaults to
            :func:`time.monotonic`.
    """

    def __init__(
        self,
        *,
        tool_factory: Optional[ToolFactory] = None,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        process_registry: Optional[ProcessRegistry] = None,
        kill_callable: Optional[Callable[[int], Any]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tool_factory: ToolFactory = (
            tool_factory if tool_factory is not None else _default_tool_factory
        )
        self._max_sessions = max(1, min(int(max_sessions), MAX_HARD_SESSIONS))
        self._registry = (
            process_registry
            if process_registry is not None
            else get_process_registry()
        )
        self._kill = kill_callable if kill_callable is not None else kill_process_tree
        self._clock = clock
        self._sessions: dict[str, BrowserSession] = {}
        self._tools: dict[str, BrowserUseTool] = {}
        self._lock = threading.RLock()

    # -- properties ----------------------------------------------------

    @property
    def max_sessions(self) -> int:
        return self._max_sessions

    # -- listing -------------------------------------------------------

    def list_sessions(self) -> tuple[BrowserSession, ...]:
        """Snapshot of every managed session (newest-first by
        ``created_at``)."""
        with self._lock:
            return tuple(
                sorted(self._sessions.values(), key=lambda s: -s.created_at)
            )

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def get_tool(self, name: str) -> Optional[BrowserUseTool]:
        """Return the :class:`BrowserUseTool` bound to ``name``,
        or ``None`` if no session by that name is registered."""
        with self._lock:
            return self._tools.get(name)

    def has_session(self, name: str) -> bool:
        with self._lock:
            return name in self._sessions

    # -- create --------------------------------------------------------

    def create_session(
        self,
        name: str,
        *,
        browser_kind: str = "default",
        user_text: str = "",
    ) -> BrowserSessionResult:
        """Register a new session.

        Validates the name, enforces the cap, runs the safety
        validator, then constructs + caches a bound
        :class:`BrowserUseTool`.
        """
        name = (name or "").strip()
        if not name:
            return BrowserSessionResult(
                success=False,
                action="create_session",
                error="empty session name",
            )
        if not _is_valid_session_name(name):
            return BrowserSessionResult(
                success=False,
                action="create_session",
                error=(
                    f"name must match [A-Za-z0-9_-]{{1,32}}, got {name!r}"
                ),
            )
        with self._lock:
            if name in self._sessions:
                return BrowserSessionResult(
                    success=False,
                    action="create_session",
                    error=f"session {name!r} already exists",
                    session=self._sessions[name],
                )
            if len(self._sessions) >= self._max_sessions:
                return BrowserSessionResult(
                    success=False,
                    action="create_session",
                    error=(
                        f"session cap reached ({self._max_sessions}); "
                        f"close one before creating another"
                    ),
                )
        denial = self._safety_check(
            action="create_session",
            arguments={
                "name": name,
                "browser_kind": browser_kind,
            },
            user_text=user_text,
        )
        if denial is not None:
            return denial
        now = self._clock()
        session = BrowserSession(
            name=name,
            browser_kind=browser_kind,
            created_at=now,
            last_seen=now,
        )
        tool = self._tool_factory(name)
        with self._lock:
            # Re-check the cap inside the lock to be race-safe.
            if len(self._sessions) >= self._max_sessions:
                return BrowserSessionResult(
                    success=False,
                    action="create_session",
                    error="session cap reached during construction",
                )
            self._sessions[name] = session
            self._tools[name] = tool
        # Register in ProcessRegistry for lifecycle tracking. PID is
        # late-bound -- the daemon spawns on first CLI call.
        try:
            self._registry.register(
                job_id=_registry_job_id(name),
                scope_key=name,
                command="browser-use daemon",
                tags=(_PROCESS_TAG,),
            )
        except Exception as exc:  # pragma: no cover -- defensive
            logger.warning(
                "browser_sessions: ProcessRegistry.register failed for %r: %s",
                name, exc,
            )
        return BrowserSessionResult(
            success=True,
            action="create_session",
            session=session,
            safety_verdict="ALLOW",
        )

    # -- close one -----------------------------------------------------

    def close_session(
        self,
        name: str,
        *,
        user_text: str = "",
        force: bool = False,
    ) -> BrowserSessionResult:
        """Close one session.

        Sends ``close`` via the bound :class:`BrowserUseTool` so the
        daemon's own cleanup runs. With ``force=True`` ALSO calls
        ``kill_process_tree`` on the registered pid (when known) --
        for use when the daemon is hung and the graceful close
        timed out.
        """
        name = (name or "").strip()
        if not name:
            return BrowserSessionResult(
                success=False,
                action="close_session",
                error="empty session name",
            )
        with self._lock:
            session = self._sessions.get(name)
            tool = self._tools.get(name)
        if session is None:
            return BrowserSessionResult(
                success=False,
                action="close_session",
                error=f"session {name!r} not found",
            )
        denial = self._safety_check(
            action="close_session",
            arguments={"name": name, "force": force},
            user_text=user_text,
        )
        if denial is not None:
            return denial
        cli_error: Optional[str] = None
        if tool is not None:
            try:
                close_result: BrowserUseResult = tool.close()
            except Exception as exc:  # pragma: no cover -- defensive
                cli_error = f"close() raised: {exc}"
            else:
                if not close_result.success:
                    cli_error = close_result.error
        if force and session.pid is not None:
            try:
                self._kill(session.pid)
            except Exception as exc:  # pragma: no cover -- defensive
                logger.warning(
                    "browser_sessions: kill_process_tree(%s) raised: %s",
                    session.pid, exc,
                )
        with self._lock:
            self._sessions.pop(name, None)
            self._tools.pop(name, None)
        try:
            self._registry.mark_exited(_registry_job_id(name), exit_code=0)
        except Exception:  # pragma: no cover -- defensive
            pass
        return BrowserSessionResult(
            success=cli_error is None,
            action="close_session",
            closed_names=(name,),
            error=cli_error,
            safety_verdict="ALLOW",
        )

    # -- close all (two-phase) -----------------------------------------

    def close_all_sessions(
        self,
        *,
        user_text: str = "",
        assume_preapproved: bool = False,
        approval_registry: Optional[ApprovalRegistry] = None,
        approval_timeout_s: Optional[float] = None,
        approval_scope_key: str = "",
    ) -> BrowserSessionResult:
        """Close every managed session. Two-phase approval gated
        because the operation destroys whatever auth state every
        loaded site had across every browser instance.
        """
        with self._lock:
            names = tuple(self._sessions.keys())
        if not names:
            return BrowserSessionResult(
                success=True,
                action="close_all_sessions",
                closed_names=(),
                safety_verdict="ALLOW",
            )
        if not assume_preapproved:
            registry = (
                approval_registry
                if approval_registry is not None
                else get_approval_registry()
            )
            request = ApprovalRequest(
                kind=BROWSER_SESSION_APPROVAL_KIND,
                prompt=(
                    f"Browser is about to close all "
                    f"{len(names)} active session(s). Proceed?"
                ),
                actor="desktop_browser_use",
                scope_key=approval_scope_key,
                metadata={
                    "session_names": list(names),
                    "user_text": user_text,
                    "reason_code": BROWSER_SESSION_REASON_CODE,
                },
                timeout_seconds=approval_timeout_s,
                delivery_channel="voice",
            )
            handle = registry.register(request)
            preapproved_decision = (
                handle.pre_resolved.outcome.value
                if handle.pre_resolved is not None
                else ""
            )
            return BrowserSessionResult(
                success=False,
                action="close_all_sessions",
                error=f"two-phase approval required for {len(names)} session(s)",
                requires_two_phase=True,
                approval_request_id=handle.approval_id,
                safety_verdict=preapproved_decision,
            )
        closed: list[str] = []
        errors: list[str] = []
        for name in names:
            r = self.close_session(name, user_text=user_text)
            if r.success:
                closed.extend(r.closed_names)
            else:
                errors.append(f"{name}: {r.error}")
        return BrowserSessionResult(
            success=not errors,
            action="close_all_sessions",
            closed_names=tuple(closed),
            error="; ".join(errors) if errors else None,
            requires_two_phase=True,
            safety_verdict="ALLOW",
        )

    # -- safety helper -------------------------------------------------

    def _safety_check(
        self,
        *,
        action: str,
        arguments: dict[str, Any],
        user_text: str,
    ) -> Optional[BrowserSessionResult]:
        """Run the validator for a session lifecycle operation."""
        try:
            validator = get_validator()
        except Exception:  # pragma: no cover -- defensive
            return None
        try:
            ctx = RuleContext(
                tool_name=f"{_TOOL_NAME_PREFIX}.{action}",
                arguments=dict(arguments),
                capability="desktop_browser_use",
                user_text=user_text or "",
            )
            verdict = validator.check(ctx)
        except Exception as exc:
            logger.warning(
                "browser_sessions safety check raised; treating as deny: %s",
                exc,
            )
            return BrowserSessionResult(
                success=False,
                action=action,
                error=f"safety check raised: {type(exc).__name__}",
                safety_verdict="BLOCK_HARD",
            )
        if verdict.is_allowed:
            return None
        label = (
            verdict.verdict.value
            if isinstance(verdict.verdict, Verdict)
            else str(verdict.verdict)
        )
        msg = (
            verdict.user_message
            or verdict.reason
            or "safety validator blocked the call"
        )
        return BrowserSessionResult(
            success=False,
            action=action,
            error=f"safety denied ({label}): {msg}",
            safety_verdict=label,
        )


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------


_manager_singleton: Optional[BrowserSessionsManager] = None


def get_browser_sessions_manager() -> Optional[BrowserSessionsManager]:
    """Return the module-level singleton or ``None`` if unset."""
    return _manager_singleton


def set_browser_sessions_manager(
    manager: Optional[BrowserSessionsManager],
) -> None:
    """Install or clear the module-level singleton."""
    global _manager_singleton
    _manager_singleton = manager


def reset_browser_sessions_manager_for_testing() -> None:
    set_browser_sessions_manager(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_tool_factory(name: str) -> BrowserUseTool:
    """Default :class:`BrowserUseTool` builder. Tests inject a mock."""
    return BrowserUseTool(session=name)


def _registry_job_id(name: str) -> str:
    """Build the ProcessRegistry job_id for a named session.

    Prefixed so a registry-wide listing can identify browser-use
    daemons without consulting per-job metadata.
    """
    return f"browser_use_session:{name}"


__all__ = [
    "BROWSER_SESSION_APPROVAL_KIND",
    "BROWSER_SESSION_REASON_CODE",
    "BrowserSession",
    "BrowserSessionResult",
    "BrowserSessionsManager",
    "DEFAULT_MAX_SESSIONS",
    "MAX_HARD_SESSIONS",
    "ToolFactory",
    "get_browser_sessions_manager",
    "reset_browser_sessions_manager_for_testing",
    "set_browser_sessions_manager",
]
