"""Tests for cumulative diff snapshots + autosubmission salvage (T6 + T13)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ultron.coding.diff_snapshot import (
    DEFAULT_GIT_TIMEOUT_SECONDS,
    DIFF_PATCH_FILENAME,
    REGISTRY_KEY_LAST_DIFF,
    REGISTRY_KEY_LAST_DIFF_STATS,
    SALVAGE_META_FILENAME,
    AutosubmissionGuard,
    DiffSnapshot,
    DiffStats,
    SalvageResult,
    capture_diff_snapshot,
    parse_diff_stats,
    read_persisted_diff,
    salvage_on_error,
)
from ultron.coding.session_registry import (
    SessionRegistry,
    reset_session_registries_for_testing,
)


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    yield
    reset_session_registries_for_testing()


@pytest.fixture
def reg(tmp_path: Path) -> SessionRegistry:
    return SessionRegistry(session_id="diff-test", root=tmp_path / "sessions")


def _init_git_repo(repo: Path) -> bool:
    """Initialise a git repo + minimal config so git diff works.

    Returns True on success, False otherwise (test will skip).
    """
    repo.mkdir(parents=True, exist_ok=True)
    try:
        for args in (
            ["git", "init", "-q"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "Test User"],
        ):
            r = subprocess.run(args, cwd=repo, capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                return False
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _git_available() -> bool:
    try:
        r = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants_sane():
    assert DIFF_PATCH_FILENAME == "last_diff.patch"
    assert SALVAGE_META_FILENAME == "last_salvage.json"
    assert DEFAULT_GIT_TIMEOUT_SECONDS > 0
    assert REGISTRY_KEY_LAST_DIFF == "last_diff"
    assert REGISTRY_KEY_LAST_DIFF_STATS == "last_diff_stats"


# ---------------------------------------------------------------------------
# parse_diff_stats
# ---------------------------------------------------------------------------


def test_parse_stats_empty():
    s = parse_diff_stats("")
    assert s == DiffStats()
    assert s.is_empty


def test_parse_stats_counts_files_and_lines():
    patch = (
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -1,2 +1,3 @@\n"
        "-old line\n"
        "+new line one\n"
        "+new line two\n"
    )
    s = parse_diff_stats(patch)
    assert s.files_changed == 1
    assert s.lines_added == 2
    assert s.lines_removed == 1
    assert not s.is_empty


def test_parse_stats_multiple_files():
    patch = "diff --git a/a b/a\n+x\ndiff --git a/b b/b\n+y\n+z\n-w\n"
    s = parse_diff_stats(patch)
    assert s.files_changed == 2


# ---------------------------------------------------------------------------
# capture_diff_snapshot -- file_list fallback
# ---------------------------------------------------------------------------


def test_capture_with_no_git_falls_back_to_file_list(tmp_path: Path):
    repo = tmp_path / "norepo"
    repo.mkdir()
    (repo / "x.py").write_text("hi", encoding="utf-8")
    snap = capture_diff_snapshot(repo)
    assert snap.method == "file_list"
    assert "x.py" in snap.diff_text
    assert snap.stats.files_changed >= 1


def test_capture_missing_dir_returns_empty(tmp_path: Path):
    snap = capture_diff_snapshot(tmp_path / "missing")
    assert snap.method == "none"
    assert snap.diff_text == ""


def test_capture_persists_to_session_dir(tmp_path: Path):
    repo = tmp_path / "norepo"
    repo.mkdir()
    (repo / "x.py").write_text("hi", encoding="utf-8")
    sessions = tmp_path / "sessions"
    snap = capture_diff_snapshot(
        repo, session_id="sess-1", sessions_root=sessions
    )
    persisted = sessions / "sess-1" / DIFF_PATCH_FILENAME
    assert persisted.exists()
    assert "x.py" in persisted.read_text(encoding="utf-8")
    assert snap.patch_path == str(persisted)


def test_capture_mirrors_diff_into_registry(tmp_path: Path, reg: SessionRegistry):
    repo = tmp_path / "norepo"
    repo.mkdir()
    (repo / "x.py").write_text("hi", encoding="utf-8")
    capture_diff_snapshot(
        repo, session_id=reg.session_id, registry=reg, sessions_root=tmp_path / "sessions"
    )
    assert REGISTRY_KEY_LAST_DIFF in reg
    stats_dict = reg[REGISTRY_KEY_LAST_DIFF_STATS]
    assert stats_dict["files_changed"] >= 1


# ---------------------------------------------------------------------------
# capture_diff_snapshot -- git path (requires git binary)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_capture_with_git_repo_uses_git(tmp_path: Path):
    repo = tmp_path / "withgit"
    if not _init_git_repo(repo):
        pytest.skip("git init failed")
    (repo / "x.py").write_text("hello world\n", encoding="utf-8")
    snap = capture_diff_snapshot(repo)
    assert snap.method == "git"
    assert "hello world" in snap.diff_text
    assert snap.stats.lines_added >= 1


@pytest.mark.skipif(not _git_available(), reason="git not on PATH")
def test_capture_with_git_persists_session_diff(tmp_path: Path):
    repo = tmp_path / "withgit"
    if not _init_git_repo(repo):
        pytest.skip("git init failed")
    (repo / "x.py").write_text("body\n", encoding="utf-8")
    sessions = tmp_path / "sessions"
    snap = capture_diff_snapshot(
        repo, session_id="git-sess", sessions_root=sessions
    )
    patch = (sessions / "git-sess" / DIFF_PATCH_FILENAME).read_text(encoding="utf-8")
    assert "body" in patch


# ---------------------------------------------------------------------------
# read_persisted_diff
# ---------------------------------------------------------------------------


def test_read_persisted_diff_returns_none_when_missing(tmp_path: Path):
    out = read_persisted_diff("none-sess", sessions_root=tmp_path)
    assert out is None


def test_read_persisted_diff_returns_text_when_present(tmp_path: Path):
    sessions = tmp_path / "sessions"
    sd = sessions / "sess-x"
    sd.mkdir(parents=True)
    (sd / DIFF_PATCH_FILENAME).write_text("--patch--", encoding="utf-8")
    assert read_persisted_diff("sess-x", sessions_root=sessions) == "--patch--"


# ---------------------------------------------------------------------------
# salvage_on_error
# ---------------------------------------------------------------------------


def test_salvage_with_no_diff_writes_meta(tmp_path: Path):
    repo = tmp_path / "empty"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    result = salvage_on_error(
        repo,
        session_id="empty-sess",
        exit_status="exit_cost",
        sessions_root=sessions,
    )
    assert isinstance(result, SalvageResult)
    assert result.salvaged is False
    meta_path = sessions / "empty-sess" / SALVAGE_META_FILENAME
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["salvaged"] is False
    assert meta["original_exit_status"] == "exit_cost"


def test_salvage_with_changed_files_decorates_exit_status(tmp_path: Path):
    repo = tmp_path / "norepo"
    repo.mkdir()
    (repo / "x.py").write_text("body", encoding="utf-8")
    sessions = tmp_path / "sessions"
    result = salvage_on_error(
        repo,
        session_id="sess-A",
        exit_status="exit_cost",
        sessions_root=sessions,
    )
    assert result.salvaged is True
    assert result.exit_status.startswith("submitted (")
    assert "x.py" in result.snapshot.diff_text


def test_salvage_with_pre_persisted_diff_falls_back(tmp_path: Path):
    # Repo is empty (no files), but a prior diff was persisted.
    repo = tmp_path / "empty"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    sd = sessions / "fallback-sess"
    sd.mkdir(parents=True)
    (sd / DIFF_PATCH_FILENAME).write_text("--prior patch--", encoding="utf-8")
    result = salvage_on_error(
        repo,
        session_id="fallback-sess",
        exit_status="exit_runtime",
        sessions_root=sessions,
    )
    assert result.salvaged is True
    assert result.snapshot.method == "prior_persisted"
    assert "prior patch" in result.snapshot.diff_text


def test_salvage_meta_carries_exception_info(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    try:
        raise RuntimeError("test boom")
    except RuntimeError as exc:
        salvage_on_error(
            repo,
            session_id="exc-sess",
            exit_status="exit_runtime",
            exception=exc,
            sessions_root=sessions,
        )
    meta = json.loads(
        (sessions / "exc-sess" / SALVAGE_META_FILENAME).read_text(encoding="utf-8")
    )
    assert meta["exception_type"] == "RuntimeError"
    assert "test boom" in meta["exception_repr"]
    assert "RuntimeError" in meta["traceback"]


# ---------------------------------------------------------------------------
# AutosubmissionGuard
# ---------------------------------------------------------------------------


def test_guard_clean_exit_captures_snapshot(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    (repo / "y.py").write_text("body", encoding="utf-8")
    sessions = tmp_path / "sessions"
    with AutosubmissionGuard(
        repo, session_id="clean-sess", sessions_root=sessions
    ) as g:
        pass
    assert g.last_result is not None
    assert (sessions / "clean-sess" / DIFF_PATCH_FILENAME).exists()


def test_guard_exception_triggers_salvage_and_reraises(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    (repo / "y.py").write_text("body", encoding="utf-8")
    sessions = tmp_path / "sessions"
    g = AutosubmissionGuard(
        repo, session_id="err-sess", sessions_root=sessions
    )
    with pytest.raises(RuntimeError):
        with g:
            raise RuntimeError("planned failure")
    # Salvage ran; the exception still propagates.
    assert g.last_result is not None
    assert (sessions / "err-sess" / SALVAGE_META_FILENAME).exists()


def test_guard_keyboard_interrupt_bypasses_salvage(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    g = AutosubmissionGuard(
        repo, session_id="kb-sess", sessions_root=sessions
    )
    with pytest.raises(KeyboardInterrupt):
        with g:
            raise KeyboardInterrupt()
    # KeyboardInterrupt re-raises immediately; salvage is skipped.
    assert g.last_result is None


def test_guard_on_salvage_callback_fires(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    (repo / "y.py").write_text("body", encoding="utf-8")
    sessions = tmp_path / "sessions"
    seen: list[SalvageResult] = []

    def hook(result: SalvageResult) -> None:
        seen.append(result)

    with AutosubmissionGuard(
        repo,
        session_id="cb-sess",
        sessions_root=sessions,
        on_salvage=hook,
    ):
        pass
    assert len(seen) == 1
    assert isinstance(seen[0], SalvageResult)


def test_guard_on_salvage_callback_exception_swallowed(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    sessions = tmp_path / "sessions"

    def hook(_result: SalvageResult) -> None:
        raise RuntimeError("hook boom")

    # The guard should NOT propagate the hook's exception.
    with AutosubmissionGuard(
        repo,
        session_id="hookerr-sess",
        sessions_root=sessions,
        on_salvage=hook,
    ):
        pass  # clean exit


# ---------------------------------------------------------------------------
# Round-trip across instances (simulates crash recovery)
# ---------------------------------------------------------------------------


def test_round_trip_salvage_then_recovery(tmp_path: Path):
    repo = tmp_path / "x"
    repo.mkdir()
    (repo / "a.py").write_text("body", encoding="utf-8")
    sessions = tmp_path / "sessions"

    # First "process": salvage on error.
    try:
        raise RuntimeError("kaboom")
    except RuntimeError as exc:
        salvage_on_error(
            repo,
            session_id="rt-sess",
            exit_status="exit_runtime",
            exception=exc,
            sessions_root=sessions,
        )
    # Second "process": read the persisted diff.
    diff = read_persisted_diff("rt-sess", sessions_root=sessions)
    assert diff is not None
    assert "a.py" in diff
