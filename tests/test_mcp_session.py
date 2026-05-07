"""Phase 1 tests: ProjectSession state machine + SessionStore mutation
helpers. Pure-Python; no MCP server needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ultron.coding.session import (
    ClarificationRequest,
    CompletionClaim,
    ProjectSession,
    SessionStatus,
    SessionStore,
    StateTransitionError,
    is_valid_transition,
)


# ---------------------------------------------------------------------------
# Transition matrix
# ---------------------------------------------------------------------------


def test_planning_transitions_legal_only_to_executing_failed_terminated():
    legal = {SessionStatus.EXECUTING, SessionStatus.FAILED, SessionStatus.TERMINATED}
    for s in SessionStatus:
        ok = is_valid_transition(SessionStatus.PLANNING, s)
        if s in legal or s == SessionStatus.PLANNING:  # idempotent
            assert ok, f"PLANNING -> {s.value} should be legal"
        else:
            assert not ok, f"PLANNING -> {s.value} should NOT be legal"


def test_terminated_is_universal_sink():
    """Every non-terminal status can transition to TERMINATED."""
    for s in SessionStatus:
        if s in (SessionStatus.COMPLETE, SessionStatus.FAILED, SessionStatus.TERMINATED):
            continue
        assert is_valid_transition(s, SessionStatus.TERMINATED), (
            f"{s.value} should be allowed to transition to TERMINATED"
        )


def test_complete_is_terminal():
    """COMPLETE has no forward edges."""
    for s in SessionStatus:
        if s == SessionStatus.COMPLETE:
            assert is_valid_transition(SessionStatus.COMPLETE, s)  # idempotent
        else:
            assert not is_valid_transition(SessionStatus.COMPLETE, s), (
                f"COMPLETE -> {s.value} should not be allowed"
            )


def test_planning_cannot_skip_to_complete():
    assert not is_valid_transition(SessionStatus.PLANNING, SessionStatus.COMPLETE)


def test_executing_can_reach_verifying_via_declare_complete():
    assert is_valid_transition(SessionStatus.EXECUTING, SessionStatus.VERIFYING)
    assert is_valid_transition(SessionStatus.VERIFYING, SessionStatus.COMPLETE)
    assert is_valid_transition(SessionStatus.VERIFYING, SessionStatus.CORRECTING)


# ---------------------------------------------------------------------------
# SessionStore CRUD + mutations
# ---------------------------------------------------------------------------


def _store_and_session(tmp_path: Path):
    store = SessionStore()
    session = store.create(
        project_root=tmp_path / "project",
        user_intent="Build me a thing",
        mode="new",
        model="haiku",
    )
    return store, session


def test_store_create_assigns_id_and_planning_status(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    assert session.session_id
    assert session.status == SessionStatus.PLANNING
    assert session.user_intent == "Build me a thing"
    assert session.mode == "new"
    assert session.model == "haiku"
    assert session.refined_goal == "Build me a thing"  # defaults to user_intent


def test_store_get_unknown_raises(tmp_path: Path):
    store = SessionStore()
    with pytest.raises(KeyError):
        store.get("not-a-real-id")


def test_store_list_active_excludes_terminal(tmp_path: Path):
    store = SessionStore()
    a = store.create(project_root=tmp_path / "a", user_intent="a")
    b = store.create(project_root=tmp_path / "b", user_intent="b")
    c = store.create(project_root=tmp_path / "c", user_intent="c")
    # Drive a to executing -> verifying -> complete; b stays at planning;
    # c is terminated.
    store.transition(a.session_id, SessionStatus.EXECUTING)
    store.transition(a.session_id, SessionStatus.VERIFYING)
    store.transition(a.session_id, SessionStatus.COMPLETE)
    store.transition(c.session_id, SessionStatus.TERMINATED)

    active_ids = {s.session_id for s in store.list_active()}
    assert active_ids == {b.session_id}


def test_store_transition_rejects_illegal(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    with pytest.raises(StateTransitionError):
        store.transition(session.session_id, SessionStatus.COMPLETE)


def test_store_transition_records_completed_at_for_terminals(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    store.transition(session.session_id, SessionStatus.EXECUTING)
    store.transition(session.session_id, SessionStatus.VERIFYING)
    store.transition(session.session_id, SessionStatus.COMPLETE)
    s = store.get(session.session_id)
    assert s.completed_at is not None
    assert s.status == SessionStatus.COMPLETE


def test_store_record_stage_tracks_files(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    store.record_stage(
        session.session_id,
        stage="scaffolding",
        summary="Created project structure",
        files_touched=["main.py", "tests/test_main.py"],
    )
    s = store.get(session.session_id)
    assert s.current_stage == "scaffolding"
    assert len(s.stages_completed) == 1
    assert {f.path for f in s.files_created} == {"main.py", "tests/test_main.py"}


def test_store_record_stage_classifies_repeats_as_modified(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    store.record_stage(
        session.session_id, stage="s1", summary="x",
        files_touched=["main.py"],
    )
    store.record_stage(
        session.session_id, stage="s2", summary="y",
        files_touched=["main.py"],   # same file twice -> the second is a modify
    )
    s = store.get(session.session_id)
    assert {f.path for f in s.files_created} == {"main.py"}
    assert {f.path for f in s.files_modified} == {"main.py"}


def test_store_set_and_resolve_clarification(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    request = ClarificationRequest(
        request_id="req-1",
        question="SQLite or Postgres?",
        options=["sqlite", "postgres"],
        urgency="blocking",
    )
    store.set_pending_clarification(session.session_id, request)

    resolved = store.resolve_clarification(
        session.session_id, "sqlite", "intent",
    )
    assert resolved is not None
    assert resolved.answer == "sqlite"
    assert resolved.decision_path == "intent"

    # And the session no longer has a pending clarification.
    assert store.get(session.session_id).pending_clarification is None


def test_store_record_completion_claim_merges_files(tmp_path: Path):
    store, session = _store_and_session(tmp_path)
    store.record_stage(
        session.session_id, stage="initial", summary="x",
        files_touched=["main.py"],
    )
    claim = CompletionClaim(
        summary="all done",
        entry_point="main.py",
        files_created=["main.py", "tests/test_main.py"],
        files_modified=["readme.md"],
    )
    store.record_completion_claim(session.session_id, claim)
    s = store.get(session.session_id)
    assert s.completion_claim is claim
    paths_created = {f.path for f in s.files_created}
    paths_modified = {f.path for f in s.files_modified}
    assert "main.py" in paths_created
    assert "tests/test_main.py" in paths_created
    assert "readme.md" in paths_modified
