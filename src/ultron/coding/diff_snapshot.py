"""Cumulative diff snapshots + autosubmission salvage on error.

Direct port of two SWE-Agent patterns that fit together:

* **T6 -- `tools/diff_state/bin/_state_diff_state`.** Snapshot the
  cumulative session diff to a stable location every dispatch. The
  snapshot survives orchestrator death; the next session can resume
  from it.
* **T13 -- `sweagent/agent/agents.py:attempt_autosubmission_after_error`.**
  When the supervisor / orchestrator crashes mid-session, salvage
  the latest diff before exiting. Even violent terminations
  (KeyboardInterrupt opt-out aside) try to extract and save the
  partial work.

The pattern: every coding-session dispatch updates a per-session
``last_diff.patch`` file under ``data/coding/sessions/<id>/``. The
top-level supervisor / runner exception handler catches everything
EXCEPT :class:`KeyboardInterrupt` and writes the latest captured
diff to disk so the user's partial work survives.

For ultron the wiring differs from SWE-Agent's:

* **Git invocation is OPTIONAL.** SWE-Agent assumes the
  ``/root/`` workspace is a git repo. Ultron coding sessions
  run under ``data/sandbox/<project>/`` which is git-init'd
  by default but may not be -- the snapshotter checks first
  and degrades to a file-list-only summary when git is absent.
* **Session-isolated paths.** Snapshots live in
  ``data/coding/sessions/<id>/`` (matches T15 SessionRegistry's
  layout) so concurrent sessions don't overwrite each other.
* **Atomic writes.** The diff file is written via tempfile +
  ``os.replace`` so a crash mid-write leaves the previous good
  diff intact.

The salvage path also publishes a :class:`SalvageEvent` on the
ultron bus (when available) so subscribers can react in-process.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, ContextManager, Iterable, Optional

from ultron.coding.session_registry import (
    SessionRegistry,
    get_session_registry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Filename for the per-session cumulative diff patch.
DIFF_PATCH_FILENAME: str = "last_diff.patch"

#: Filename for the per-session salvage metadata (timestamp,
#: exit_status, exception_type, etc.).
SALVAGE_META_FILENAME: str = "last_salvage.json"

#: Registry key under which the most recent diff capture (string)
#: lives. Matches SWE-Agent's ``state["diff"]`` JSON path.
REGISTRY_KEY_LAST_DIFF: str = "last_diff"

#: Registry key under which the most recent diff stats are stored.
REGISTRY_KEY_LAST_DIFF_STATS: str = "last_diff_stats"

#: Default subprocess timeout for git invocations (seconds). Past
#: this we give up + fall back to the no-git path.
DEFAULT_GIT_TIMEOUT_SECONDS: float = 10.0


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DiffStats:
    """Numeric breakdown of a captured diff."""

    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    is_empty: bool = True


@dataclass(frozen=True)
class DiffSnapshot:
    """Output of :func:`capture_diff_snapshot`.

    :param diff_text: the full cumulative patch (or a degraded
        summary when git is unavailable).
    :param stats: numeric breakdown for narration.
    :param patch_path: absolute path of the on-disk
        ``last_diff.patch``.
    :param captured_at: epoch seconds when the snapshot landed.
    :param method: ``"git"`` if produced via git diff; ``"file_list"``
        if produced from a directory walk because git wasn't usable;
        ``"none"`` if the repo couldn't be inspected at all.
    :param error: optional human-readable string when the snapshot
        is empty or partial because of an internal error.
    """

    diff_text: str = ""
    stats: DiffStats = field(default_factory=DiffStats)
    patch_path: Optional[str] = None
    captured_at: float = 0.0
    method: str = "none"
    error: str = ""


@dataclass(frozen=True)
class SalvageResult:
    """Output of :func:`salvage_on_error`.

    :param salvaged: True if a non-empty diff was captured AND
        persisted.
    :param snapshot: the captured :class:`DiffSnapshot` (always set,
        even when salvaged is False; check ``snapshot.method`` to
        understand what was possible).
    :param exit_status: short tag for the trajectory recorder
        (``"submitted (exit_cost)"`` etc.). Always carries the
        ``submitted (...)`` prefix when ``salvaged`` is True so the
        operator can tell at a glance that the exit was salvaged.
    :param observation: human-readable description of the salvage
        attempt's outcome.
    """

    salvaged: bool
    snapshot: DiffSnapshot
    exit_status: str = ""
    observation: str = ""


# ---------------------------------------------------------------------------
# Diff capture
# ---------------------------------------------------------------------------


def capture_diff_snapshot(
    repo_root: str | Path,
    *,
    session_id: Optional[str] = None,
    registry: Optional[SessionRegistry] = None,
    sessions_root: Optional[Path] = None,
    git_timeout: float = DEFAULT_GIT_TIMEOUT_SECONDS,
) -> DiffSnapshot:
    """Capture the cumulative diff for ``repo_root`` and persist it.

    Algorithm (mirrors SWE-Agent's ``_state_diff_state`` shape):

    1. If ``repo_root`` is a git repo and ``git`` is on PATH:
       ``git add -A && git diff --cached`` -> the patch text.
       Compute simple stats from the patch.
    2. If git isn't usable: walk the directory + list every regular
       file with size and a short prefix; record ``method="file_list"``.
       Better than nothing for the salvage narration.
    3. If neither is possible: return an empty snapshot with
       ``method="none"`` + ``error`` populated.

    The patch text is written to
    ``<sessions_root>/<session_id>/last_diff.patch`` via tempfile +
    ``os.replace``. The current diff text and stats are mirrored
    into the :class:`SessionRegistry` under
    :data:`REGISTRY_KEY_LAST_DIFF` and :data:`REGISTRY_KEY_LAST_DIFF_STATS`
    so other components (architect narrator, completion narrator)
    can read them without re-running git.

    Fail-open at every layer: any I/O / subprocess failure returns
    a partial snapshot with ``error`` populated rather than raising.
    """
    captured_at = time.time()
    repo = Path(repo_root).expanduser().resolve()

    # Prefer git capture when possible.
    snapshot: DiffSnapshot
    if _looks_like_git_repo(repo):
        try:
            patch_text, stats = _git_capture(repo, timeout=git_timeout)
            snapshot = DiffSnapshot(
                diff_text=patch_text,
                stats=stats,
                captured_at=captured_at,
                method="git",
            )
        except Exception as exc:
            logger.warning(
                "git diff capture failed for %s: %s; falling back",
                repo,
                exc,
            )
            patch_text, stats = _file_list_capture(repo)
            snapshot = DiffSnapshot(
                diff_text=patch_text,
                stats=stats,
                captured_at=captured_at,
                method="file_list",
                error=str(exc),
            )
    else:
        patch_text, stats = _file_list_capture(repo)
        snapshot = DiffSnapshot(
            diff_text=patch_text,
            stats=stats,
            captured_at=captured_at,
            method="file_list" if patch_text else "none",
        )

    # Persist to disk.
    persisted_path: Optional[str] = None
    if session_id is not None or registry is not None:
        try:
            persisted_path = _persist_diff(
                snapshot.diff_text,
                session_id=session_id,
                sessions_root=sessions_root,
            )
        except OSError as exc:
            logger.warning(
                "diff_snapshot persistence failed for session %s: %s",
                session_id,
                exc,
            )
    # Mirror to registry if provided.
    reg = registry
    if reg is None and session_id is not None:
        try:
            reg = get_session_registry(session_id)
        except Exception:
            reg = None
    if reg is not None:
        try:
            with reg.transaction():
                reg[REGISTRY_KEY_LAST_DIFF] = snapshot.diff_text
                reg[REGISTRY_KEY_LAST_DIFF_STATS] = {
                    "files_changed": snapshot.stats.files_changed,
                    "lines_added": snapshot.stats.lines_added,
                    "lines_removed": snapshot.stats.lines_removed,
                    "is_empty": snapshot.stats.is_empty,
                }
        except Exception as exc:
            logger.warning(
                "diff_snapshot registry mirror failed: %s", exc
            )

    if persisted_path is not None:
        snapshot = DiffSnapshot(
            diff_text=snapshot.diff_text,
            stats=snapshot.stats,
            patch_path=persisted_path,
            captured_at=snapshot.captured_at,
            method=snapshot.method,
            error=snapshot.error,
        )
    return snapshot


def _looks_like_git_repo(repo: Path) -> bool:
    if not repo.exists():
        return False
    if not repo.is_dir():
        return False
    return (repo / ".git").exists()


def _git_capture(repo: Path, *, timeout: float) -> tuple[str, DiffStats]:
    """Run ``git add -A && git diff --cached`` and return ``(patch, stats)``."""
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    common = {
        "cwd": str(repo),
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "creationflags": creationflags,
        "check": False,
    }
    # `git add -A` to include untracked files in the diff. Failure
    # here doesn't abort -- the diff still has tracked-file changes.
    subprocess.run(["git", "add", "-A"], **common)
    proc = subprocess.run(
        ["git", "diff", "--cached", "--no-color"],
        **common,
    )
    patch_text = proc.stdout if proc.returncode == 0 else ""
    stats = parse_diff_stats(patch_text)
    return patch_text, stats


def _file_list_capture(repo: Path) -> tuple[str, DiffStats]:
    """Walk the directory + emit a readable file-list summary.

    Used when git isn't available so the salvage path still has
    SOMETHING to show the operator about the partial work.
    """
    if not repo.exists() or not repo.is_dir():
        return "", DiffStats()
    rows: list[str] = []
    total_lines = 0
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            p = Path(dirpath) / name
            try:
                size = p.stat().st_size
            except OSError:
                continue
            rows.append(f"+ {p.relative_to(repo)} ({size} bytes)")
            file_count += 1
            if file_count > 500:
                rows.append("... (truncated; >500 files)")
                break
        if file_count > 500:
            break
    text = "\n".join(rows)
    if not rows:
        return "", DiffStats()
    # Stats: file-list mode has no add/remove distinction.
    return text, DiffStats(
        files_changed=file_count,
        lines_added=total_lines,
        lines_removed=0,
        is_empty=file_count == 0,
    )


def parse_diff_stats(patch_text: str) -> DiffStats:
    """Count file changes / added / removed lines from a unified diff."""
    if not patch_text or not patch_text.strip():
        return DiffStats()
    files = 0
    added = 0
    removed = 0
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            files += 1
        elif line.startswith("+++ ") or line.startswith("--- "):
            # File header; not a content line.
            continue
        elif line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return DiffStats(
        files_changed=files,
        lines_added=added,
        lines_removed=removed,
        is_empty=files == 0 and added == 0 and removed == 0,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _persist_diff(
    diff_text: str,
    *,
    session_id: Optional[str],
    sessions_root: Optional[Path],
) -> str:
    """Write ``diff_text`` to the session's ``last_diff.patch``.

    Skips the write when ``diff_text`` is empty / whitespace -- we
    don't want to overwrite a previously-persisted good patch with
    an empty fresh capture (e.g. when the repo has been wiped before
    salvage runs). The on-disk last_diff therefore always reflects
    the most-recent NON-EMPTY snapshot.
    """
    if session_id is None:
        return ""
    if not diff_text or not diff_text.strip():
        return ""
    root = sessions_root
    if root is None:
        from ultron.coding.session_registry import DEFAULT_REGISTRY_ROOT
        root = DEFAULT_REGISTRY_ROOT
    target_dir = Path(root) / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / DIFF_PATCH_FILENAME
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=DIFF_PATCH_FILENAME + ".",
        suffix=".tmp",
        dir=str(target_dir),
    )
    os.close(tmp_fd)
    Path(tmp_name).write_text(diff_text, encoding="utf-8")
    os.replace(tmp_name, str(target))
    return str(target)


def read_persisted_diff(
    session_id: str,
    *,
    sessions_root: Optional[Path] = None,
) -> Optional[str]:
    """Read the previously-persisted ``last_diff.patch`` for a session.

    Returns ``None`` if no patch has been persisted yet.
    """
    root = sessions_root
    if root is None:
        from ultron.coding.session_registry import DEFAULT_REGISTRY_ROOT
        root = DEFAULT_REGISTRY_ROOT
    path = Path(root) / session_id / DIFF_PATCH_FILENAME
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Salvage on error
# ---------------------------------------------------------------------------


def salvage_on_error(
    repo_root: str | Path,
    *,
    session_id: str,
    exit_status: str = "exit_unknown",
    exception: Optional[BaseException] = None,
    sessions_root: Optional[Path] = None,
    registry: Optional[SessionRegistry] = None,
    git_timeout: float = DEFAULT_GIT_TIMEOUT_SECONDS,
) -> SalvageResult:
    """Attempt to salvage the latest diff before exiting.

    Mirrors SWE-Agent's
    :func:`attempt_autosubmission_after_error` shape:

    1. Try to capture a fresh diff. If successful AND non-empty,
       persist + mark the exit_status as
       ``"submitted (<original_exit>)"`` so the trajectory
       recorder shows BOTH the cause of death and the salvaged
       submission.
    2. If the fresh capture fails (e.g. the repo is unreachable),
       fall back to the last-persisted diff on disk.
    3. If both fail, persist a salvage-metadata JSON so the next
       session knows we tried.

    Never raises -- only :class:`KeyboardInterrupt` should bypass
    this path. The orchestrator wraps its top-level try/except
    around this call.

    :param repo_root: directory whose diff to capture.
    :param session_id: per-session identifier (drives the on-disk
        layout under ``data/coding/sessions/<id>/``).
    :param exit_status: the original exit tag the orchestrator
        was about to use.
    :param exception: the exception that triggered the salvage.
    :param sessions_root: override the session-files root (tests).
    :param registry: optional pre-constructed registry.
    :param git_timeout: subprocess timeout for git.
    """
    snapshot = capture_diff_snapshot(
        repo_root,
        session_id=session_id,
        registry=registry,
        sessions_root=sessions_root,
        git_timeout=git_timeout,
    )

    salvaged = bool(snapshot.diff_text.strip())
    decorated_exit = exit_status
    observation = ""

    if not salvaged:
        # Try the fallback path: read the previously-persisted diff.
        prior = read_persisted_diff(
            session_id, sessions_root=sessions_root
        )
        if prior:
            snapshot = DiffSnapshot(
                diff_text=prior,
                stats=parse_diff_stats(prior),
                patch_path=snapshot.patch_path,
                captured_at=time.time(),
                method="prior_persisted",
                error=snapshot.error or "fresh capture empty",
            )
            salvaged = True

    if salvaged:
        decorated_exit = (
            f"submitted ({exit_status})"
            if exit_status and not exit_status.startswith("submitted (")
            else exit_status or "submitted"
        )
        observation = (
            "Environment died unexpectedly. Exited (autosubmitted). "
            f"Salvaged {snapshot.stats.files_changed} file(s), "
            f"+{snapshot.stats.lines_added}/-{snapshot.stats.lines_removed} lines."
        )
    else:
        observation = "Salvage attempt failed: no diff captured and no prior on disk."

    # Persist the salvage metadata for offline inspection.
    try:
        _persist_salvage_meta(
            session_id=session_id,
            sessions_root=sessions_root,
            exit_status=decorated_exit,
            original_exit=exit_status,
            exception=exception,
            snapshot=snapshot,
            salvaged=salvaged,
        )
    except OSError as exc:
        logger.warning(
            "salvage metadata persistence failed for session %s: %s",
            session_id,
            exc,
        )

    return SalvageResult(
        salvaged=salvaged,
        snapshot=snapshot,
        exit_status=decorated_exit,
        observation=observation,
    )


def _persist_salvage_meta(
    *,
    session_id: str,
    sessions_root: Optional[Path],
    exit_status: str,
    original_exit: str,
    exception: Optional[BaseException],
    snapshot: DiffSnapshot,
    salvaged: bool,
) -> None:
    root = sessions_root
    if root is None:
        from ultron.coding.session_registry import DEFAULT_REGISTRY_ROOT
        root = DEFAULT_REGISTRY_ROOT
    target_dir = Path(root) / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / SALVAGE_META_FILENAME
    payload = {
        "salvaged_at": time.time(),
        "exit_status": exit_status,
        "original_exit_status": original_exit,
        "salvaged": salvaged,
        "exception_type": type(exception).__name__ if exception else "",
        "exception_repr": repr(exception) if exception else "",
        "traceback": (
            "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            )
            if exception
            else ""
        ),
        "snapshot_method": snapshot.method,
        "snapshot_chars": len(snapshot.diff_text),
        "snapshot_path": snapshot.patch_path,
        "stats": {
            "files_changed": snapshot.stats.files_changed,
            "lines_added": snapshot.stats.lines_added,
            "lines_removed": snapshot.stats.lines_removed,
        },
        "python_version": sys.version.split()[0],
    }
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=SALVAGE_META_FILENAME + ".",
        suffix=".tmp",
        dir=str(target_dir),
    )
    os.close(tmp_fd)
    Path(tmp_name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp_name, str(target))


# ---------------------------------------------------------------------------
# Context-manager wrapper
# ---------------------------------------------------------------------------


class AutosubmissionGuard:
    """Context manager that fires :func:`salvage_on_error` on exit.

    Usage::

        with AutosubmissionGuard(repo_root, session_id="abc"):
            # ... long-running session work ...

    On clean exit, captures one final snapshot (so the salvage file
    always reflects the most-recent state). On exception, runs the
    salvage path with the exception details. :class:`KeyboardInterrupt`
    is RE-RAISED so user-driven cancellation behaves as expected.

    Caller can pass ``on_salvage`` for a notification hook (e.g.
    publish a bus event).
    """

    def __init__(
        self,
        repo_root: str | Path,
        *,
        session_id: str,
        exit_status_on_clean_exit: str = "completed",
        exit_status_on_error: str = "exit_unknown",
        on_salvage: Optional[Callable[[SalvageResult], None]] = None,
        sessions_root: Optional[Path] = None,
        registry: Optional[SessionRegistry] = None,
        git_timeout: float = DEFAULT_GIT_TIMEOUT_SECONDS,
    ) -> None:
        self.repo_root = repo_root
        self.session_id = session_id
        self.exit_status_on_clean_exit = exit_status_on_clean_exit
        self.exit_status_on_error = exit_status_on_error
        self.on_salvage = on_salvage
        self.sessions_root = sessions_root
        self.registry = registry
        self.git_timeout = git_timeout
        self.last_result: Optional[SalvageResult] = None

    def __enter__(self) -> "AutosubmissionGuard":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is KeyboardInterrupt:
            # Let user cancellation bubble; don't salvage.
            return False
        try:
            self.last_result = salvage_on_error(
                self.repo_root,
                session_id=self.session_id,
                exit_status=(
                    self.exit_status_on_error
                    if exc_type is not None
                    else self.exit_status_on_clean_exit
                ),
                exception=exc_val,
                sessions_root=self.sessions_root,
                registry=self.registry,
                git_timeout=self.git_timeout,
            )
            if self.on_salvage is not None and self.last_result is not None:
                try:
                    self.on_salvage(self.last_result)
                except Exception:
                    logger.warning(
                        "AutosubmissionGuard on_salvage callback raised",
                        exc_info=True,
                    )
        except Exception as exc:
            logger.warning(
                "AutosubmissionGuard salvage path raised: %s", exc
            )
        # Don't suppress the original exception.
        return False


__all__ = [
    "AutosubmissionGuard",
    "DEFAULT_GIT_TIMEOUT_SECONDS",
    "DIFF_PATCH_FILENAME",
    "DiffSnapshot",
    "DiffStats",
    "REGISTRY_KEY_LAST_DIFF",
    "REGISTRY_KEY_LAST_DIFF_STATS",
    "SALVAGE_META_FILENAME",
    "SalvageResult",
    "capture_diff_snapshot",
    "parse_diff_stats",
    "read_persisted_diff",
    "salvage_on_error",
]
