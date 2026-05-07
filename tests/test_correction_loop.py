"""Phase 4 integration: coordinator's correction loop.

Verifier is stubbed -- we don't want real subprocesses in this file.
What we DO verify:
  * declare_complete transitions COMPLETE on a passing report
  * declare_complete transitions CORRECTING + emits a correction prompt
    on a failing report
  * The session.verification_failures counter advances
  * model_escalation_count is set when the haiku threshold is crossed
  * After total threshold, session transitions to FAILED + on_failed
    callback fires
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import pytest

from ultron.coding.coordinator import ConversationCoordinator
from ultron.coding.session import (
    CompletionClaim,
    SessionStatus,
    SessionStore,
)
from ultron.coding.templates import TemplateRenderer
from ultron.coding.verification import CheckId, CheckResult, VerificationReport


# ---------------------------------------------------------------------------
# Stub verifier that returns scripted reports
# ---------------------------------------------------------------------------


@dataclass
class _StubVerifier:
    scripted: List[VerificationReport] = field(default_factory=list)
    calls: int = 0

    def queue(self, *reports: VerificationReport) -> None:
        self.scripted.extend(reports)

    def verify(self, session_id: str) -> VerificationReport:
        self.calls += 1
        if not self.scripted:
            raise AssertionError("stub verifier ran out of scripted reports")
        return self.scripted.pop(0)

    def verify_tests_only(self, session_id: str) -> CheckResult:
        # not exercised here
        raise NotImplementedError


def _passing_report(session_id: str) -> VerificationReport:
    return VerificationReport(
        session_id=session_id, passed=True, duration_s=0.1,
        checks=[
            CheckResult(check=CheckId.FILES_EXIST, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.STRUCTURE, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.TESTS, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.SMOKE, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.LINT, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.NO_POLLUTION, passed=True, duration_ms=1.0),
        ],
    )


def _failing_report(session_id: str, *, failure_detail: str = "tests fail") -> VerificationReport:
    return VerificationReport(
        session_id=session_id, passed=False, duration_s=0.1,
        checks=[
            CheckResult(check=CheckId.FILES_EXIST, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.STRUCTURE, passed=True, duration_ms=1.0),
            CheckResult(
                check=CheckId.TESTS, passed=False,
                detail=failure_detail,
                hint="run pytest yourself",
                duration_ms=1.0,
            ),
            CheckResult(check=CheckId.SMOKE, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.LINT, passed=True, duration_ms=1.0),
            CheckResult(check=CheckId.NO_POLLUTION, passed=True, duration_ms=1.0),
        ],
    )


# ---------------------------------------------------------------------------
# Fixture: store + coordinator + scripted verifier
# ---------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path: Path):
    store = SessionStore()
    project = tmp_path / "project"
    project.mkdir()
    session = store.create(
        project_root=project, user_intent="x",
        mode="new", model="haiku",
    )
    store.transition(session.session_id, SessionStatus.EXECUTING)
    store.record_completion_claim(
        session.session_id,
        CompletionClaim(summary="x", files_created=["main.py"]),
    )
    store.transition(session.session_id, SessionStatus.VERIFYING)

    failed_callbacks: List[tuple] = []
    def on_failed(sid: str, reason: str) -> None:
        failed_callbacks.append((sid, reason))

    stub = _StubVerifier()
    renderer = TemplateRenderer()
    coord = ConversationCoordinator(
        store=store, llm=None, renderer=renderer,
        verifier=stub, on_failed_session=on_failed,
    )
    return {
        "store": store,
        "session_id": session.session_id,
        "stub": stub,
        "coord": coord,
        "failed_callbacks": failed_callbacks,
    }


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Happy path: passing report transitions COMPLETE
# ---------------------------------------------------------------------------


def test_declare_complete_passing_transitions_complete(env):
    env["stub"].queue(_passing_report(env["session_id"]))
    answer = _run(env["coord"].handle_declare_complete(env["session_id"]))
    s = env["store"].get(env["session_id"])
    assert s.status == SessionStatus.COMPLETE
    assert "passed" in answer.lower()
    assert s.verification_failures == 0


# ---------------------------------------------------------------------------
# First failure: correction prompt emitted, counter incremented
# ---------------------------------------------------------------------------


def test_first_failure_emits_correction_and_increments_counter(env):
    env["stub"].queue(_failing_report(env["session_id"]))
    answer = _run(env["coord"].handle_declare_complete(env["session_id"]))
    s = env["store"].get(env["session_id"])
    assert s.verification_failures == 1
    assert s.status == SessionStatus.EXECUTING  # correction loops back to executing
    # Correction prompt mentions the failing check
    assert "verification failed" in answer.lower()
    assert "tests" in answer.lower() or "test suite" in answer.lower()
    # Not yet at the haiku threshold -> no escalation yet
    assert s.model_escalation_count == 0


# ---------------------------------------------------------------------------
# Repeated failures hit the haiku threshold -> escalation flag set
# ---------------------------------------------------------------------------


def test_haiku_threshold_sets_escalation_flag(env):
    """3 failures should mark the session for sonnet escalation on the
    next subprocess start."""
    for _ in range(3):
        env["stub"].queue(_failing_report(env["session_id"]))
        # Need to put the session back into VERIFYING before each call
        # since CORRECTING -> EXECUTING was applied by the previous one.
        if env["store"].get(env["session_id"]).status == SessionStatus.EXECUTING:
            env["store"].transition(env["session_id"], SessionStatus.VERIFYING)
        _run(env["coord"].handle_declare_complete(env["session_id"]))
    s = env["store"].get(env["session_id"])
    assert s.verification_failures == 3
    assert s.model_escalation_count >= 1, (
        "escalation_count should be set after crossing the haiku threshold"
    )
    # Still not FAILED -- we're at exactly the haiku threshold.
    assert s.status == SessionStatus.EXECUTING


# ---------------------------------------------------------------------------
# Total threshold (haiku + sonnet) -> FAILED + callback fires
# ---------------------------------------------------------------------------


def test_total_threshold_marks_session_failed(env):
    """3 haiku fails + 2 sonnet fails = 5 total -> FAILED."""
    for _ in range(5):
        env["stub"].queue(_failing_report(env["session_id"]))
        if env["store"].get(env["session_id"]).status == SessionStatus.EXECUTING:
            env["store"].transition(env["session_id"], SessionStatus.VERIFYING)
        _run(env["coord"].handle_declare_complete(env["session_id"]))
    s = env["store"].get(env["session_id"])
    assert s.status == SessionStatus.FAILED
    assert s.verification_failures == 5
    assert env["failed_callbacks"], "on_failed_session callback must fire"
    sid, reason = env["failed_callbacks"][0]
    assert sid == env["session_id"]
    assert "5 times" in reason or "verification has failed" in reason.lower()


# ---------------------------------------------------------------------------
# Recovery: failure followed by passing report transitions COMPLETE
# ---------------------------------------------------------------------------


def test_failure_then_pass_resolves_to_complete(env):
    env["stub"].queue(
        _failing_report(env["session_id"]),
        _passing_report(env["session_id"]),
    )
    # First call -> correction
    _run(env["coord"].handle_declare_complete(env["session_id"]))
    # Second call -> verify pass, COMPLETE
    env["store"].transition(env["session_id"], SessionStatus.VERIFYING)
    answer = _run(env["coord"].handle_declare_complete(env["session_id"]))
    s = env["store"].get(env["session_id"])
    assert s.status == SessionStatus.COMPLETE
    assert s.verification_failures == 1  # not reset; informational only
    assert "passed" in answer.lower()


# ---------------------------------------------------------------------------
# Verifier-less coordinator: claim is trusted (Phase 1 behavior)
# ---------------------------------------------------------------------------


def test_no_verifier_trusts_claim(env, tmp_path):
    project = tmp_path / "trusted"
    project.mkdir()
    store = SessionStore()
    session = store.create(project_root=project, user_intent="x")
    store.transition(session.session_id, SessionStatus.EXECUTING)
    store.record_completion_claim(
        session.session_id,
        CompletionClaim(summary="ok", files_created=["x.py"]),
    )
    store.transition(session.session_id, SessionStatus.VERIFYING)

    coord = ConversationCoordinator(store=store, llm=None, verifier=None)
    answer = _run(coord.handle_declare_complete(session.session_id))
    assert store.get(session.session_id).status == SessionStatus.COMPLETE
    assert "skipped" in answer.lower()


# ---------------------------------------------------------------------------
# Correction prompt rendering shape
# ---------------------------------------------------------------------------


def test_correction_prompt_includes_failure_detail_and_hint(env):
    env["stub"].queue(
        _failing_report(env["session_id"], failure_detail="2 failures: foo, bar"),
    )
    answer = _run(env["coord"].handle_declare_complete(env["session_id"]))
    assert "2 failures: foo, bar" in answer
    assert "Hint: run pytest yourself" in answer
