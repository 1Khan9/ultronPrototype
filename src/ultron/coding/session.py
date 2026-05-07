"""ProjectSession state machine for the supervisor layer.

Phase 1 ships the full schema (so the MCP tool signatures are stable)
but only the fields needed for the bare lifecycle are populated. Phase 2
fills in the rest as the coordinator decisions land.

State transitions are validated -- you cannot, for example, jump from
``planning`` straight to ``complete`` without going through ``executing``
and ``verifying`` first. The matrix lives at module scope so tests can
inspect and assert against it.
"""

from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SessionStatus(str, enum.Enum):
    PLANNING = "planning"                       # before first prompt sent
    EXECUTING = "executing"                     # Claude actively working
    AWAITING_CLARIFICATION = "awaiting_clarification"  # blocked on Claude
    AWAITING_USER = "awaiting_user"             # Qwen escalated, waiting on voice
    VERIFYING = "verifying"                     # full verification running
    CORRECTING = "correcting"                   # corrective prompt sent
    COMPLETE = "complete"                       # passed verification
    FAILED = "failed"                           # gave up after escalation
    TERMINATED = "terminated"                   # user-cancelled


# Allowed forward transitions. Anything not in this map is rejected.
# ``terminated`` is the universal sink -- we always allow it.
_TRANSITIONS: Dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.PLANNING: {
        SessionStatus.EXECUTING,
        SessionStatus.FAILED,
        SessionStatus.TERMINATED,
    },
    SessionStatus.EXECUTING: {
        SessionStatus.AWAITING_CLARIFICATION,
        SessionStatus.VERIFYING,
        SessionStatus.CORRECTING,
        SessionStatus.FAILED,
        SessionStatus.TERMINATED,
    },
    SessionStatus.AWAITING_CLARIFICATION: {
        SessionStatus.AWAITING_USER,
        SessionStatus.EXECUTING,        # Qwen answered, Claude resumes
        SessionStatus.TERMINATED,
    },
    SessionStatus.AWAITING_USER: {
        SessionStatus.AWAITING_CLARIFICATION,  # user answered, hand back to Claude
        SessionStatus.EXECUTING,                # adjustment routed without clarif
        SessionStatus.TERMINATED,
    },
    SessionStatus.VERIFYING: {
        SessionStatus.COMPLETE,
        SessionStatus.CORRECTING,
        SessionStatus.FAILED,
        SessionStatus.TERMINATED,
    },
    SessionStatus.CORRECTING: {
        SessionStatus.EXECUTING,
        SessionStatus.FAILED,
        SessionStatus.TERMINATED,
    },
    SessionStatus.COMPLETE: set(),         # terminal
    SessionStatus.FAILED: set(),           # terminal
    SessionStatus.TERMINATED: set(),       # terminal
}


def is_valid_transition(from_status: SessionStatus, to_status: SessionStatus) -> bool:
    if from_status == to_status:
        return True  # idempotent
    return to_status in _TRANSITIONS.get(from_status, set())


SessionMode = Literal["new", "edit", "continue"]
ClarificationUrgency = Literal["blocking", "preference"]
FollowupKind = Literal["clarification_response", "adjustment", "correction"]


# ---------------------------------------------------------------------------
# Sub-records
# ---------------------------------------------------------------------------


@dataclass
class StageRecord:
    """One report_progress call from Claude."""
    stage: str
    summary: str
    files_touched: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class FileRecord:
    """A file Claude reports having created or modified."""
    path: str   # relative to project_root
    first_seen: float = field(default_factory=time.time)


@dataclass
class TestStatus:
    """Last reported test results from Claude."""
    passing: int = 0
    failing: int = 0
    skipped: int = 0
    details: str = ""
    last_updated: Optional[float] = None


@dataclass
class ClarificationRequest:
    """A pending clarification call from Claude waiting on Qwen's response."""
    request_id: str
    question: str
    options: List[str] = field(default_factory=list)
    urgency: ClarificationUrgency = "blocking"
    asked_at: float = field(default_factory=time.time)
    answer: Optional[str] = None
    answered_at: Optional[float] = None
    decision_path: str = ""  # "intent" / "facts" / "heuristic" / "user_escalation" / "default"


@dataclass
class AdjustmentRecord:
    """A mid-session adjustment from the user."""
    text: str
    timestamp: float = field(default_factory=time.time)
    rendered_prompt: str = ""


@dataclass
class CompletionClaim:
    """Recorded when Claude calls declare_complete -- before verification."""
    summary: str
    entry_point: Optional[str] = None
    run_command: Optional[str] = None
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    claimed_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# ProjectSession
# ---------------------------------------------------------------------------


@dataclass
class ProjectSession:
    """In-memory state for one supervised coding session.

    All mutation must go through :class:`SessionStore` so the lock is
    held -- the MCP server's tool handlers run on an asyncio thread,
    while the runner accesses state from the main thread.
    """

    session_id: str
    project_root: Path
    user_intent: str
    refined_goal: str = ""
    mode: SessionMode = "new"
    model: str = "haiku"
    status: SessionStatus = SessionStatus.PLANNING
    current_stage: Optional[str] = None
    stages_completed: List[StageRecord] = field(default_factory=list)
    files_created: List[FileRecord] = field(default_factory=list)
    files_modified: List[FileRecord] = field(default_factory=list)
    test_status: TestStatus = field(default_factory=TestStatus)
    last_progress_update: Optional[float] = None
    pending_clarification: Optional[ClarificationRequest] = None
    user_adjustments: List[AdjustmentRecord] = field(default_factory=list)
    verification_failures: int = 0
    model_escalation_count: int = 0
    started_at: float = field(default_factory=time.time)
    last_user_status_query: Optional[float] = None
    completed_at: Optional[float] = None
    completion_claim: Optional[CompletionClaim] = None
    # Bridge handle for the active Claude subprocess; set by the runner,
    # not by the MCP layer.
    bridge_task_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Thread-safe store
# ---------------------------------------------------------------------------


class StateTransitionError(RuntimeError):
    """Raised when an attempted SessionStatus transition is not allowed."""


class SessionStore:
    """Lock-protected dictionary of session_id -> ProjectSession.

    Used by the MCP server (asyncio thread) and the runner / coordinator
    (main thread) to share session state safely.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, ProjectSession] = {}
        self._lock = threading.RLock()

    # --- CRUD ---------------------------------------------------------------

    def create(
        self,
        *,
        project_root: Path,
        user_intent: str,
        mode: SessionMode = "new",
        model: str = "haiku",
        refined_goal: str = "",
    ) -> ProjectSession:
        session = ProjectSession(
            session_id=uuid.uuid4().hex[:12],
            project_root=Path(project_root),
            user_intent=user_intent,
            refined_goal=refined_goal or user_intent,
            mode=mode,
            model=model,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> ProjectSession:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError:
                raise KeyError(f"unknown session: {session_id}")

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def list_active(self) -> List[ProjectSession]:
        with self._lock:
            return [
                s for s in self._sessions.values()
                if s.status not in (
                    SessionStatus.COMPLETE,
                    SessionStatus.FAILED,
                    SessionStatus.TERMINATED,
                )
            ]

    def list_all(self) -> List[ProjectSession]:
        with self._lock:
            return list(self._sessions.values())

    # --- mutation under lock -----------------------------------------------

    def transition(self, session_id: str, to_status: SessionStatus) -> ProjectSession:
        with self._lock:
            session = self.get(session_id)
            if not is_valid_transition(session.status, to_status):
                raise StateTransitionError(
                    f"illegal transition for {session_id}: "
                    f"{session.status.value} -> {to_status.value}"
                )
            session.status = to_status
            if to_status in (
                SessionStatus.COMPLETE, SessionStatus.FAILED, SessionStatus.TERMINATED
            ) and session.completed_at is None:
                session.completed_at = time.time()
            return session

    def record_stage(
        self,
        session_id: str,
        *,
        stage: str,
        summary: str,
        files_touched: List[str],
    ) -> StageRecord:
        with self._lock:
            session = self.get(session_id)
            record = StageRecord(
                stage=stage, summary=summary, files_touched=list(files_touched),
            )
            session.stages_completed.append(record)
            session.current_stage = stage
            session.last_progress_update = record.timestamp
            # Fold files_touched into the file lists. We don't know if a
            # path is "created" vs "modified" from this signal alone --
            # treat anything we haven't seen as created, others as modified.
            seen = {f.path for f in session.files_created} | {
                f.path for f in session.files_modified
            }
            for f in files_touched:
                if f in seen:
                    if not any(rec.path == f for rec in session.files_modified):
                        session.files_modified.append(FileRecord(path=f))
                else:
                    session.files_created.append(FileRecord(path=f))
            return record

    def set_pending_clarification(
        self, session_id: str, request: ClarificationRequest
    ) -> None:
        with self._lock:
            session = self.get(session_id)
            session.pending_clarification = request
            # Don't enforce the transition here -- the MCP server may set
            # this from EXECUTING mid-run; coordinator will explicitly
            # transition the status as part of its decision flow.

    def resolve_clarification(
        self, session_id: str, answer: str, decision_path: str
    ) -> Optional[ClarificationRequest]:
        with self._lock:
            session = self.get(session_id)
            request = session.pending_clarification
            if request is None:
                return None
            request.answer = answer
            request.answered_at = time.time()
            request.decision_path = decision_path
            session.pending_clarification = None
            return request

    def record_test_results(
        self, session_id: str, *, passing: int, failing: int, skipped: int, details: str
    ) -> None:
        with self._lock:
            session = self.get(session_id)
            session.test_status = TestStatus(
                passing=passing, failing=failing, skipped=skipped,
                details=details, last_updated=time.time(),
            )

    def record_completion_claim(
        self, session_id: str, claim: CompletionClaim
    ) -> None:
        with self._lock:
            session = self.get(session_id)
            session.completion_claim = claim
            # Roll any newly-claimed files into the tracked lists too.
            existing = {f.path for f in session.files_created}
            for fp in claim.files_created:
                if fp not in existing:
                    session.files_created.append(FileRecord(path=fp))
            existing_mod = {f.path for f in session.files_modified}
            for fp in claim.files_modified:
                if fp not in existing_mod:
                    session.files_modified.append(FileRecord(path=fp))

    def record_adjustment(
        self, session_id: str, text: str, rendered_prompt: str = ""
    ) -> AdjustmentRecord:
        with self._lock:
            session = self.get(session_id)
            record = AdjustmentRecord(text=text, rendered_prompt=rendered_prompt)
            session.user_adjustments.append(record)
            return record

    def touch_status_query(self, session_id: str) -> None:
        with self._lock:
            session = self.get(session_id)
            session.last_user_status_query = time.time()
