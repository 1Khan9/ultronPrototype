"""Filenames-only directory search with hard cap.

Direct port of SWE-Agent's ``tools/search/bin/search_dir`` +
``search_file`` + ``find_file`` (MIT, Yang et al. 2024). The ACI
rationale: "directory-wide search that returns only filenames
(with match counts), not match content -- fuller results overflowed
the model and produced confused next-actions."

Three search primitives:

* :func:`search_dir_filenames_only` -- recursive substring search;
  returns ``[(path, count)]`` pairs sorted by count desc. Hard cap
  at 100 files -- exceeding the cap returns a structured
  :class:`SearchTooBroadError` with a tiered narrowing hint
  instead of any results (matches SWE-Agent's "flooding the
  context is treated as a hard error, not a soft truncation").
* :func:`search_in_file_with_cap` -- substring search WITHIN a
  single file; returns ``[(line_number, line_content)]`` pairs.
  Hard cap at 100 lines per file.
* :func:`find_file_by_pattern` -- glob-style filename match.

Backend: prefers ``ripgrep`` when on PATH (5-10x faster than grep,
respects ``.gitignore`` by default); falls back to a pure-Python
walk that's still acceptable for kenning's typical ~600-file tree
(<100 ms uncached).

Tiered cap escalation hint (creative extension from the catalog):
when overflow happens, the message names the top extensions and
their counts so the model can narrow productively.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Caps + defaults
# ---------------------------------------------------------------------------

#: SWE-Agent default cap on the number of files that may appear in a
#: directory-search result. Exceeding this is a hard error, not a
#: soft truncation.
DEFAULT_DIR_SEARCH_CAP: int = 100

#: SWE-Agent default cap on lines returned from a single-file search.
DEFAULT_FILE_SEARCH_CAP: int = 100

#: Tiered cap escalation: a result above the first tier returns a
#: hint asking the model to narrow before promoting to the next
#: tier. Maps to the catalog's creative extension.
DEFAULT_TIERED_CAPS: tuple[int, ...] = (5, 25, 100)

#: Directories the search NEVER recurses into. Mirrors SWE-Agent's
#: ``find ... ! -path '*/.*'`` plus kenning-specific build/cache
#: noise.
DEFAULT_SKIP_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        ".venv-xtts",
        ".venv-parakeet",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".coverage",
        "htmlcov",
        ".claude",
        ".idea",
        ".vscode",
        ".windsurf",
        "logs",
        "models",
        "data",
    }
)


# ---------------------------------------------------------------------------
# Error + result records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileMatch:
    """One file with its match count from a directory search."""

    path: str
    count: int


@dataclass(frozen=True)
class LineMatch:
    """One line match from a single-file search."""

    line_number: int  # 1-indexed
    content: str


@dataclass(frozen=True)
class SearchResult:
    """Output of a directory or file search.

    :param matches: the matched files (for dir search) or lines (for
        file search). Empty list when no matches.
    :param total_matches: total count across all matches (sum of
        file-level counts, or len(matches) for a file search).
    :param truncated: True if the result was clipped at a cap.
    :param cap_message: the user-facing message produced when the
        search overflowed the cap (or empty string).
    """

    matches: list[FileMatch | LineMatch] = field(default_factory=list)
    total_matches: int = 0
    truncated: bool = False
    cap_message: str = ""


class SearchTooBroadError(Exception):
    """Raised when a directory search returns more files than the cap.

    Carries the rendered message (matches SWE-Agent's
    ``"More than N files matched for ..."``) plus the structured
    breakdown so callers can surface a structured retry hint.
    """

    def __init__(
        self,
        message: str,
        *,
        cap: int,
        actual: int,
        top_extensions: Optional[list[tuple[str, int]]] = None,
    ) -> None:
        super().__init__(message)
        self.cap = cap
        self.actual = actual
        self.top_extensions = top_extensions or []


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------


def _ripgrep_available() -> bool:
    return shutil.which("rg") is not None


def _resolve_dir(directory: str | Path) -> Path:
    p = Path(directory).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def _should_skip_dir(name: str, *, skip: frozenset[str]) -> bool:
    if name in skip:
        return True
    if name.startswith("."):
        # SWE-Agent's ! -path '*/.*' (skip every hidden directory).
        return True
    return False


# ---------------------------------------------------------------------------
# Public API: search_dir_filenames_only
# ---------------------------------------------------------------------------


def search_dir_filenames_only(
    term: str,
    directory: str | Path = ".",
    *,
    max_files: int = DEFAULT_DIR_SEARCH_CAP,
    skip_directories: frozenset[str] = DEFAULT_SKIP_DIRECTORIES,
    tiered_caps: Sequence[int] = DEFAULT_TIERED_CAPS,
    use_ripgrep: Optional[bool] = None,
) -> SearchResult:
    """Search ``directory`` recursively for files containing ``term``.

    Returns a :class:`SearchResult` whose ``matches`` is a list of
    :class:`FileMatch` records sorted by ``count`` descending. Raises
    :class:`SearchTooBroadError` if the number of matching files
    exceeds ``max_files`` -- callers can either surface the rendered
    message to the model or catch the exception and adjust the
    search before retrying.

    The tiered-cap hint (creative extension): when overflow happens,
    the error message lists the top extensions present in the match
    set so the model can productively narrow (e.g. "try restricting
    to .py").

    :param term: substring to search for; empty raises ValueError.
    :param directory: directory to search; defaults to CWD.
    :param max_files: hard cap on file count (mirrors SWE-Agent's
        100). Overflow raises :class:`SearchTooBroadError`.
    :param skip_directories: names skipped during traversal; defaults
        to :data:`DEFAULT_SKIP_DIRECTORIES`.
    :param tiered_caps: tier thresholds for the narrowing-hint
        progression (matches the catalog's creative extension).
    :param use_ripgrep: ``None`` auto-detects; ``True`` requires
        ripgrep on PATH; ``False`` forces the pure-Python walk.
    """
    if not term:
        raise ValueError("search term must be non-empty")
    root = _resolve_dir(directory)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(str(root))

    if use_ripgrep is None:
        use_ripgrep = _ripgrep_available()
    elif use_ripgrep and not _ripgrep_available():
        raise RuntimeError("ripgrep requested but not available on PATH")

    counts: dict[str, int]
    if use_ripgrep:
        counts = _ripgrep_count(root, term, skip_directories)
    else:
        counts = _python_walk_count(root, term, skip_directories)

    sorted_matches = sorted(
        ({"path": p, "count": c} for p, c in counts.items()),
        key=lambda d: (-d["count"], d["path"]),
    )
    n_files = len(sorted_matches)
    if n_files > max_files:
        ext_counts: dict[str, int] = {}
        for d in sorted_matches:
            ext = Path(d["path"]).suffix or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + d["count"]
        top_extensions = sorted(
            ext_counts.items(), key=lambda kv: -kv[1]
        )[:3]
        tier = _pick_tier_hint(n_files, tiered_caps)
        ext_hint = ", ".join(f"{ext}={n}" for ext, n in top_extensions)
        msg = (
            f"More than {max_files} files matched for {term!r} in "
            f"{root}. Please narrow your search. Top extensions: "
            f"{ext_hint}. Consider {tier}."
        )
        raise SearchTooBroadError(
            msg,
            cap=max_files,
            actual=n_files,
            top_extensions=top_extensions,
        )

    matches: list[FileMatch | LineMatch] = [
        FileMatch(path=d["path"], count=d["count"]) for d in sorted_matches
    ]
    total = sum(d["count"] for d in sorted_matches)
    return SearchResult(
        matches=matches, total_matches=total, truncated=False
    )


def _pick_tier_hint(n_files: int, tiers: Sequence[int]) -> str:
    """Suggest a tighter tier given how overflowing the result is."""
    sorted_tiers = sorted(set(tiers))
    for t in sorted_tiers:
        if t < n_files:
            return (
                f"restricting to roughly {t} files via a more specific "
                "search term or a subdirectory"
            )
    return "tightening your search with a more specific term"


def _ripgrep_count(
    root: Path,
    term: str,
    skip_directories: frozenset[str],
) -> dict[str, int]:
    """Run ripgrep + parse counts. Falls back to pure-Python on any
    ripgrep error (returns whatever counts ripgrep produced before
    the failure)."""
    cmd: list[str] = [
        "rg",
        "--count",
        "--no-messages",
        "--fixed-strings",
        "--with-filename",
    ]
    for skip in skip_directories:
        cmd.extend(["--glob", f"!{skip}"])
        cmd.extend(["--glob", f"!{skip}/**"])
    cmd.extend(["--", term, str(root)])
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning(
            "ripgrep invocation failed (%s); falling back to Python walk",
            exc,
        )
        return _python_walk_count(root, term, skip_directories)
    if proc.returncode not in (0, 1):  # 1 = no matches
        logger.warning(
            "ripgrep returned %s; stderr=%s; falling back",
            proc.returncode,
            proc.stderr.strip()[:200],
        )
        return _python_walk_count(root, term, skip_directories)
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        # Format: ``<path>:<count>``.
        idx = line.rfind(":")
        if idx == -1:
            continue
        path = line[:idx]
        try:
            counts[path] = int(line[idx + 1 :])
        except ValueError:
            continue
    return counts


def _python_walk_count(
    root: Path,
    term: str,
    skip_directories: frozenset[str],
) -> dict[str, int]:
    """Pure-Python recursive search. Reads each file as bytes and
    counts occurrences."""
    counts: dict[str, int] = {}
    term_b = term.encode("utf-8")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            d for d in dirnames if not _should_skip_dir(d, skip=skip_directories)
        ]
        for name in filenames:
            if name.startswith("."):
                continue  # mirror SWE-Agent's ! -path '*/.*'
            full = Path(dirpath) / name
            try:
                with full.open("rb") as f:
                    data = f.read()
            except OSError:
                continue
            if not data:
                continue
            try:
                c = data.count(term_b)
            except Exception:
                continue
            if c:
                counts[str(full)] = c
    return counts


# ---------------------------------------------------------------------------
# Public API: search_in_file_with_cap
# ---------------------------------------------------------------------------


def search_in_file_with_cap(
    term: str,
    path: str | Path,
    *,
    max_lines: int = DEFAULT_FILE_SEARCH_CAP,
) -> SearchResult:
    """Search a single file for ``term``; return matching ``(line, content)`` pairs.

    Returns a :class:`SearchResult` whose ``matches`` is a list of
    :class:`LineMatch` records. Hard cap at ``max_lines`` -- exceeding
    the cap returns the FIRST ``max_lines`` matches with
    ``truncated=True`` and a ``cap_message`` suggesting a more
    selective term.
    """
    if not term:
        raise ValueError("search term must be non-empty")
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(str(p))
    if not p.is_file():
        raise ValueError(f"{p} is not a regular file")
    matches: list[FileMatch | LineMatch] = []
    total = 0
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            for i, raw in enumerate(f, start=1):
                if term in raw:
                    total += 1
                    if len(matches) < max_lines:
                        matches.append(LineMatch(line_number=i, content=raw.rstrip("\n")))
    except OSError as exc:
        raise RuntimeError(f"failed to read {p}: {exc}") from exc
    truncated = total > max_lines
    cap_message = ""
    if truncated:
        cap_message = (
            f"More than {max_lines} lines matched for {term!r} in {p}. "
            f"Showing the first {max_lines}; refine your search to see the rest."
        )
    return SearchResult(
        matches=matches,
        total_matches=total,
        truncated=truncated,
        cap_message=cap_message,
    )


# ---------------------------------------------------------------------------
# Public API: find_file_by_pattern
# ---------------------------------------------------------------------------


def find_file_by_pattern(
    pattern: str,
    directory: str | Path = ".",
    *,
    skip_directories: frozenset[str] = DEFAULT_SKIP_DIRECTORIES,
    max_files: int = DEFAULT_DIR_SEARCH_CAP,
) -> list[str]:
    """Find files by filename glob pattern (``*.py``, ``test_*.py``, ...).

    Returns absolute paths of matching files (sorted lexicographically).
    Hard cap at ``max_files`` -- exceeding raises
    :class:`SearchTooBroadError`.

    Patterns follow ``fnmatch`` semantics (Python's :mod:`fnmatch`
    module). The pattern is matched against the BASENAME only, not
    the full path.
    """
    import fnmatch

    if not pattern:
        raise ValueError("pattern must be non-empty")
    root = _resolve_dir(directory)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(str(root))
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            d for d in dirnames if not _should_skip_dir(d, skip=skip_directories)
        ]
        for name in filenames:
            if name.startswith("."):
                continue
            if fnmatch.fnmatchcase(name, pattern):
                out.append(str(Path(dirpath) / name))
                if len(out) > max_files:
                    raise SearchTooBroadError(
                        f"More than {max_files} files matched pattern "
                        f"{pattern!r} in {root}. Please narrow.",
                        cap=max_files,
                        actual=len(out),
                    )
    return sorted(out)


__all__ = [
    "DEFAULT_DIR_SEARCH_CAP",
    "DEFAULT_FILE_SEARCH_CAP",
    "DEFAULT_SKIP_DIRECTORIES",
    "DEFAULT_TIERED_CAPS",
    "FileMatch",
    "LineMatch",
    "SearchResult",
    "SearchTooBroadError",
    "find_file_by_pattern",
    "search_dir_filenames_only",
    "search_in_file_with_cap",
]
