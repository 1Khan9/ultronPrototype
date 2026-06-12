"""Ripgrep subprocess wrapper with byte-capped grouped JSON-line output.

Adapted from cline's ``regexSearchFiles`` pattern (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Kenning's variant:

* Uses Python ``subprocess.Popen`` with line-buffered stdout so the
  result accumulator can stop early once any cap is hit.
* Defaults to streaming line-by-line read with a hard wall-clock kill
  if rg hangs (the original relies on Node readline's process.kill).
* Adds Windows-specific ``CREATE_NO_WINDOW`` to keep a phantom console
  from flashing during synth-and-search voice turns.
* Accepts an optional path-predicate (``ignore_predicate``) so the
  result set can be filtered against ``.kenningignore`` policy before
  rendering.

Output shape mirrors cline's grouped-by-file format with pipe-character
separators so the LLM sees a stable contract whether the matches come
from rg or from a future search backend.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

LOGGER = logging.getLogger(__name__)

#: Default name of the binary searched for on ``PATH``.
DEFAULT_BINARY_NAME: str = "rg"

#: Cap on the number of grouped match records returned.
MAX_RESULTS: int = 300

#: Cap on the total byte size of the assembled output (mirror of cline's
#: 0.25 MB ceiling). Encoded in bytes for direct comparison.
MAX_RIPGREP_BYTES: int = 256 * 1024

#: Cap on the number of stdout lines we will read before forcibly
#: killing the rg subprocess. Mirrors cline's MAX_RESULTS * 5 heuristic
#: with a small safety margin.
MAX_RIPGREP_LINES: int = MAX_RESULTS * 6

#: Default per-call wall-clock timeout in seconds. rg is fast on small
#: trees but the wrapper still guards against runaway scans.
DEFAULT_TIMEOUT_S: float = 8.0

# Windows CREATE_NO_WINDOW flag (suppresses phantom console window
# during voice-path subprocess invocations).
_CREATE_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)


class RipgrepError(RuntimeError):
    """Raised when the rg subprocess cannot be started or produced an error.

    The orchestrator wraps every caller in fail-open semantics so a
    missing-rg or process-spawn failure logs WARN and returns an empty
    result; raising lets dev-time callers decide whether to surface or
    swallow.
    """


@dataclass(frozen=True)
class RipgrepMatch:
    """One match emitted by ripgrep with optional surrounding context.

    Attributes:
        relative_path: file path relative to the directory the search
            originated from. Always uses forward slashes for cross-
            platform display stability.
        line_number: 1-indexed line of the match.
        column: 1-indexed column of the first capture group of the match.
        line_text: full text of the matched line (no terminator).
        before_context: lines immediately preceding the match.
        after_context: lines immediately following the match.
    """

    relative_path: str
    line_number: int
    column: int
    line_text: str
    before_context: tuple[str, ...] = field(default_factory=tuple)
    after_context: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RipgrepResult:
    """Container for a complete ripgrep search outcome.

    Attributes:
        matches: matches in emission order, capped at :data:`MAX_RESULTS`.
        rendered: pre-rendered grouped output suitable for prompt
            injection (the LLM sees this string verbatim).
        truncated: True when the search exceeded :data:`MAX_RESULTS`,
            :data:`MAX_RIPGREP_BYTES`, or :data:`MAX_RIPGREP_LINES`.
        elapsed_seconds: wall-clock duration of the search.
        binary: absolute path to the rg binary that was used.
        files_with_matches: ordered sequence of unique file paths.
    """

    matches: tuple[RipgrepMatch, ...]
    rendered: str
    truncated: bool
    elapsed_seconds: float
    binary: str
    files_with_matches: tuple[str, ...] = field(default_factory=tuple)


def rg_binary_available(binary_name: str = DEFAULT_BINARY_NAME) -> Optional[str]:
    """Resolve the absolute path to ``rg`` if installed on the system.

    Args:
        binary_name: name of the ripgrep binary on ``PATH``.

    Returns:
        Absolute path to the binary, or None when not present.
    """
    located = shutil.which(binary_name)
    if located:
        return located
    # On Windows the user often has rg under one of a couple of common
    # install locations even when not on PATH.
    if sys.platform == "win32":
        for candidate in (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "ripgrep"
            / "rg.exe",
            Path(os.environ.get("USERPROFILE", ""))
            / "scoop"
            / "apps"
            / "ripgrep"
            / "current"
            / "rg.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    return None


def _to_posix(path: str) -> str:
    """Normalise display paths to forward-slash form for prompt stability."""
    return path.replace("\\", "/")


def _decode_rg_line(raw: bytes) -> Optional[dict]:
    """Decode one line of rg ``--json`` stdout into a Python dict.

    Returns None on decode failure; the caller continues so a single
    corrupt line does not abort the entire scan.
    """
    if not raw:
        return None
    try:
        text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    except Exception:  # noqa: BLE001 - fail-open per cline convention
        return None
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_text_field(node: dict | None) -> str:
    """Pull the ``text`` field from an rg JSON ``text`` object.

    rg encodes some lines as ``{"text": "..."}`` and others as
    ``{"bytes": "<base64>"}`` when the content is not valid UTF-8. We
    skip the bytes form for prompt cleanliness.
    """
    if not isinstance(node, dict):
        return ""
    if "text" in node and isinstance(node["text"], str):
        return node["text"]
    return ""


def _build_relative(path: str, cwd: Path) -> str:
    """Compute a clean forward-slash relative path for display.

    Falls back to the absolute path when the match lives outside cwd.
    """
    try:
        rel = os.path.relpath(path, cwd)
    except ValueError:
        return _to_posix(path)
    return _to_posix(rel)


def _render(matches: Iterable[RipgrepMatch], truncated: bool) -> str:
    """Render the grouped output the LLM (or supervisor narration) sees."""
    matches_list = list(matches)
    if not matches_list:
        return "No matches."
    grouped: dict[str, list[RipgrepMatch]] = {}
    file_order: list[str] = []
    for match in matches_list:
        if match.relative_path not in grouped:
            grouped[match.relative_path] = []
            file_order.append(match.relative_path)
        grouped[match.relative_path].append(match)
    lines: list[str] = [f"Found {len(matches_list)} match(es)."]
    for file_path in file_order:
        lines.append("")
        lines.append(file_path)
        lines.append("│----")
        for i, match in enumerate(grouped[file_path]):
            if i > 0:
                lines.append("│----")
            for before in match.before_context:
                lines.append(f"│{before}")
            lines.append(f"│{match.line_text}")
            for after in match.after_context:
                lines.append(f"│{after}")
        lines.append("│----")
    if truncated:
        lines.append("")
        lines.append(
            f"[Results truncated at {MAX_RESULTS} match(es) / "
            f"{MAX_RIPGREP_BYTES // 1024} KB. Narrow the pattern or glob "
            "for a sharper result set.]"
        )
    return "\n".join(lines)


def regex_search_files(
    cwd: str | os.PathLike[str],
    directory: str | os.PathLike[str],
    pattern: str,
    *,
    file_pattern: str = "*",
    context_lines: int = 1,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    ignore_predicate: Optional[Callable[[str], bool]] = None,
    binary_name: str = DEFAULT_BINARY_NAME,
    extra_args: Iterable[str] = (),
) -> RipgrepResult:
    """Run ``rg --json`` against ``directory`` and return grouped output.

    Args:
        cwd: the working-directory anchor used for relative-path display.
        directory: directory tree to search (must exist).
        pattern: ripgrep regex pattern (Rust regex syntax).
        file_pattern: glob filter forwarded as ``--glob``. Default ``*``.
        context_lines: lines of context emitted before AND after each
            match (mirrors cline's ``--context 1``). Negative values are
            clamped to 0.
        timeout_s: wall-clock kill timeout (seconds) for runaway scans.
        ignore_predicate: optional callable mapping a relative path to
            True when the path is ignored by policy; matching matches are
            dropped after rg returns.
        binary_name: name of the rg binary on ``PATH``.
        extra_args: optional extra CLI arguments appended after the
            standard set (e.g., ``("--hidden",)``). Use sparingly.

    Returns:
        :class:`RipgrepResult` with the parsed matches and a pre-rendered
        grouped string.

    Raises:
        RipgrepError: when rg is not installed, the subprocess fails to
            launch, or the directory does not exist.
    """
    cwd_path = Path(cwd).resolve()
    directory_path = Path(directory).resolve()
    if not directory_path.exists():
        raise RipgrepError(f"directory not found: {directory_path}")
    binary = rg_binary_available(binary_name)
    if not binary:
        raise RipgrepError(
            f"ripgrep binary '{binary_name}' not on PATH; install rg or "
            "set the binary name explicitly."
        )
    context_value = max(0, int(context_lines))
    cmd = [
        binary,
        "--json",
        "-e",
        pattern,
        "--glob",
        file_pattern,
        "--context",
        str(context_value),
        str(directory_path),
    ]
    cmd.extend(str(x) for x in extra_args)

    start = time.monotonic()
    try:
        process = subprocess.Popen(  # noqa: S603 - args are controlled
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise RipgrepError(f"failed to spawn rg: {exc}") from exc
    except OSError as exc:
        raise RipgrepError(f"failed to spawn rg: {exc}") from exc

    matches: list[RipgrepMatch] = []
    current_path: Optional[str] = None
    pending_before: list[str] = []
    pending_after_holder: list[RipgrepMatch] = []
    byte_budget = 0
    line_count = 0
    truncated = False

    assert process.stdout is not None
    try:
        for raw_line in process.stdout:
            line_count += 1
            if line_count > MAX_RIPGREP_LINES:
                truncated = True
                break
            event = _decode_rg_line(raw_line)
            if not event:
                continue
            event_type = event.get("type")
            if event_type == "begin":
                data = event.get("data") or {}
                current_path = _build_relative(
                    _extract_text_field(data.get("path")), cwd_path,
                )
                pending_before = []
                pending_after_holder = []
                continue
            if event_type == "context":
                data = event.get("data") or {}
                line_text = _extract_text_field(data.get("lines"))
                line_text = line_text.rstrip("\n")
                if pending_after_holder:
                    # Context line trailing the most-recent match.
                    last = pending_after_holder[-1]
                    pending_after_holder[-1] = RipgrepMatch(
                        relative_path=last.relative_path,
                        line_number=last.line_number,
                        column=last.column,
                        line_text=last.line_text,
                        before_context=last.before_context,
                        after_context=last.after_context + (line_text,),
                    )
                else:
                    pending_before.append(line_text)
                    # Keep ``before_context`` bounded to the requested width.
                    if len(pending_before) > context_value:
                        pending_before = pending_before[-context_value:]
                continue
            if event_type == "match":
                data = event.get("data") or {}
                line_text = _extract_text_field(data.get("lines"))
                line_text = line_text.rstrip("\n")
                submatches = data.get("submatches") or []
                column = 1
                if submatches and isinstance(submatches[0], dict):
                    column = int(submatches[0].get("start", 0)) + 1
                match = RipgrepMatch(
                    relative_path=current_path or "",
                    line_number=int(data.get("line_number", 0) or 0),
                    column=column,
                    line_text=line_text,
                    before_context=tuple(pending_before),
                    after_context=(),
                )
                pending_before = []
                if ignore_predicate is not None:
                    try:
                        if ignore_predicate(match.relative_path):
                            continue
                    except Exception:  # noqa: BLE001
                        # Fail-open: a broken predicate keeps the match.
                        pass
                pending_after_holder.append(match)
                matches.append(match)
                # Replace the prior reference because match objects are
                # immutable and the ``pending_after_holder`` may rebind it.
                matches[-1] = pending_after_holder[-1]
                byte_budget += len(line_text.encode("utf-8")) + len(file_pattern) + 8
                if len(matches) >= MAX_RESULTS or byte_budget >= MAX_RIPGREP_BYTES:
                    truncated = True
                    break
                continue
            if event_type == "end":
                # End-of-file marker; replace the last stored match with
                # its context-augmented version (the after-context lines
                # were attached above).
                if pending_after_holder:
                    # Walk backwards to update matches with their final
                    # after_context contents.
                    for stored in pending_after_holder:
                        for idx in range(len(matches) - 1, -1, -1):
                            existing = matches[idx]
                            if (
                                existing.relative_path == stored.relative_path
                                and existing.line_number == stored.line_number
                                and existing.column == stored.column
                            ):
                                matches[idx] = stored
                                break
                pending_after_holder = []
                pending_before = []
                continue
            # summary / other events are not surfaced to callers.
    finally:
        # Drain remaining output to avoid SIGPIPE on the rg side.
        if process.stdout:
            try:
                process.stdout.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            stderr_bytes = process.stderr.read() if process.stderr else b""
        except Exception:  # noqa: BLE001
            stderr_bytes = b""
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=1.0)
            except Exception:  # noqa: BLE001
                pass
            truncated = True

    elapsed = time.monotonic() - start
    if process.returncode is not None and process.returncode not in (0, 1):
        stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
        if stderr_text:
            LOGGER.warning("rg exited %s: %s", process.returncode, stderr_text)

    files_seen: list[str] = []
    seen_set: set[str] = set()
    for match in matches:
        if match.relative_path not in seen_set:
            seen_set.add(match.relative_path)
            files_seen.append(match.relative_path)

    rendered = _render(matches, truncated)
    return RipgrepResult(
        matches=tuple(matches),
        rendered=rendered,
        truncated=truncated,
        elapsed_seconds=elapsed,
        binary=binary,
        files_with_matches=tuple(files_seen),
    )


__all__ = [
    "DEFAULT_BINARY_NAME",
    "DEFAULT_TIMEOUT_S",
    "MAX_RESULTS",
    "MAX_RIPGREP_BYTES",
    "MAX_RIPGREP_LINES",
    "RipgrepError",
    "RipgrepMatch",
    "RipgrepResult",
    "regex_search_files",
    "rg_binary_available",
]
