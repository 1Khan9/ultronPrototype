"""Python-specific lint cascade: basic + compile + flake8 FATAL-only.

Pattern lifted in spirit (not in source) from aider's
``linter.py::py_lint`` (Apache 2.0; see ``THIRD_PARTY_NOTICES.md``).
Three layers run in cascade:

  1. **basic** — :func:`~ultron.coding.tree_sitter_lint.tree_sitter_lint`
     walks the AST for ERROR / is_missing nodes. Cheap (~10-50 ms per
     file).
  2. **compile** — Python's stdlib ``compile(code, fname, "exec")``.
     Catches Python-specific syntax that tree-sitter doesn't (e.g.
     ``match`` statement semantic constraints, indentation errors
     that tree-sitter recovers from). On failure the traceback is
     reformatted into a single :class:`LintError`.
  3. **flake8** — runs the user's installed flake8 with a
     hand-picked **FATAL-only** rule set:
       * ``E9``  — SyntaxError / indentation / file decoding errors
       * ``F821`` — undefined name (likely runtime crash)
       * ``F823`` — local var referenced before assignment
       * ``F831`` — duplicate argument name
       * ``F406``/``F407`` — ``from X import *`` with undefined names
       * ``F701``/``F702``/``F704``/``F706`` — ``break``/``continue``
         outside loop, etc.
     Style errors (E1xx, E2xx, W*) are explicitly OUT of scope. The
     deal is "definitely-broken at runtime", not "doesn't match
     this team's style".

Each layer's errors get merged into one :class:`LintReport`. The
output also notes which layer caught each error so downstream
narration can say "tree-sitter caught a syntax error" vs "flake8
caught an undefined name".

Fail-open: any subprocess failure (flake8 not installed, timeout,
weird subprocess error) is logged at DEBUG and that layer is
skipped. The other layers still run.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess
import sys
import tokenize
import traceback
from pathlib import Path
from typing import List, Optional

from ultron.coding.tree_sitter_lint import LintError, LintReport, tree_sitter_lint


logger = logging.getLogger("ultron.coding.python_lint")


# Catalog T8: FATAL flake8 rules ONLY. Anything that "guaranteed
# breaks at runtime" — never style, never line length, never spacing.
FLAKE8_FATAL_SELECT = (
    "E9,"
    "F821,F823,F831,"
    "F406,F407,"
    "F701,F702,F704,F706"
)


# Default subprocess timeout for the flake8 call. flake8 on a single
# file is normally <500 ms; we cap at a few seconds to survive
# pathological inputs.
DEFAULT_FLAKE8_TIMEOUT = 5.0


# Subprocess creation flag for Windows — keeps the CREATE_NO_WINDOW
# discipline that the rest of ultron honours so flake8 doesn't flash
# a console window when invoked from the FILE_CHANGE listener.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def lint_python(
    path: Path | str,
    *,
    run_flake8: bool = True,
    flake8_timeout: float = DEFAULT_FLAKE8_TIMEOUT,
) -> LintReport:
    """Run the three-tier Python lint cascade.

    Args:
        path: Source file on disk. Must be a ``.py`` / ``.pyi`` file
            for the compile + flake8 layers to fire — non-Python
            paths short-circuit to a tree-sitter-only check (which is
            generic across languages).
        run_flake8: Skip the flake8 layer when False. Useful in tests
            and when flake8 is intentionally not installed.
        flake8_timeout: Subprocess timeout in seconds.

    Returns:
        :class:`LintReport` aggregating errors from all enabled layers.
    """
    p = Path(path)
    abs_path = p.resolve() if not p.is_absolute() else p
    path_str = str(abs_path)
    suffix = abs_path.suffix.lower()

    base_report = tree_sitter_lint(abs_path)
    errors: List[LintError] = list(base_report.errors)

    if suffix not in {".py", ".pyi"}:
        # Non-Python — return the tree-sitter base. Upstream callers
        # often still call us on .js/.yaml/etc.; we just degrade.
        return LintReport(
            path=path_str,
            language=base_report.language,
            errors=errors,
            skipped_reason=base_report.skipped_reason if not errors else "",
            truncated=base_report.truncated,
        )

    # Layer 2: compile()
    compile_errors = _python_compile_check(abs_path)
    errors.extend(compile_errors)

    # Layer 3: flake8 FATAL-only
    if run_flake8:
        flake8_errors = _python_flake8_check(abs_path, timeout=flake8_timeout)
        errors.extend(flake8_errors)

    errors.sort(key=lambda e: (e.line, e.column))
    return LintReport(
        path=path_str,
        language="python",
        errors=errors,
        truncated=base_report.truncated,
    )


# ---------------------------------------------------------------------------
# Layer 2: Python compile()
# ---------------------------------------------------------------------------


def _python_compile_check(path: Path) -> List[LintError]:
    """Run ``compile(code, fname, "exec")`` and convert errors to
    :class:`LintError`."""
    try:
        with tokenize.open(str(path)) as fh:
            code = fh.read()
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        # Tokenize-level failure IS a "lint" failure too — record it.
        return [LintError(
            line=0,
            column=0,
            kind="error",
            message=f"file unreadable / encoding: {exc}",
            source="compile",
        )]
    try:
        compile(code, str(path), "exec")
    except SyntaxError as exc:
        line = (exc.lineno or 1) - 1
        col = (exc.offset or 1) - 1
        msg = (exc.msg or "syntax error").strip()
        return [LintError(
            line=max(0, line),
            column=max(0, col),
            kind="error",
            message=msg,
            source="compile",
        )]
    except (ValueError, TypeError) as exc:
        # ValueError: source code contains null bytes (etc.)
        return [LintError(
            line=0,
            column=0,
            kind="error",
            message=f"{type(exc).__name__}: {exc}",
            source="compile",
        )]
    except Exception as exc:                                    # noqa: BLE001
        # Defensive: shouldn't happen, but never raise out of a linter.
        logger.debug("python compile() raised unexpected %s: %s", type(exc).__name__, exc)
        return []
    return []


# ---------------------------------------------------------------------------
# Layer 3: flake8 FATAL-only
# ---------------------------------------------------------------------------


def _python_flake8_check(
    path: Path,
    *,
    timeout: float = DEFAULT_FLAKE8_TIMEOUT,
) -> List[LintError]:
    """Run flake8 with the FATAL-only rule selection."""
    flake8 = _locate_flake8()
    if flake8 is None:
        return []

    cmd = [
        *flake8,
        f"--select={FLAKE8_FATAL_SELECT}",
        "--format=%(row)d:%(col)d:%(code)s:%(text)s",
        "--no-show-source",
        str(path),
    ]

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.debug("flake8 timed out on %s after %.1fs", path, timeout)
        return []
    except (OSError, FileNotFoundError) as exc:
        logger.debug("flake8 invocation failed: %s", exc)
        return []
    except Exception as exc:                                    # noqa: BLE001
        logger.debug("flake8 invocation unexpected: %s", exc)
        return []

    out = (completed.stdout or "") + (completed.stderr or "")
    return _parse_flake8_output(out)


def _locate_flake8() -> Optional[List[str]]:
    """Return the command list to invoke flake8 or ``None`` when
    unavailable.

    Preferred: ``sys.executable -m flake8`` so we don't depend on
    PATH. Fallback: ``shutil.which("flake8")``.
    """
    # 1. ``python -m flake8`` is most portable and uses the active venv.
    try:
        import flake8  # noqa: F401
        return [sys.executable, "-m", "flake8"]
    except ImportError:
        pass

    on_path = shutil.which("flake8")
    if on_path:
        return [on_path]
    return None


def _parse_flake8_output(text: str) -> List[LintError]:
    """Parse the flake8 ``--format=%(row)d:%(col)d:%(code)s:%(text)s``
    output back into :class:`LintError` rows."""
    out: List[LintError] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # When the path is in the format too, flake8 emits
        # ``path:row:col:CODE:text``. With our format string the path
        # is omitted but a leading "stdin:" sneaks in if no file was
        # passed; we strip any leading "x:" segments until we hit the
        # row digits.
        parts = line.split(":", maxsplit=4)
        # Walk back from the end: row should be 4th-from-last, col
        # 3rd-from-last, code 2nd-from-last, text the rest.
        # Easiest: try to find the first numeric:numeric pair in the
        # split.
        if len(parts) < 4:
            continue
        # Common shape: "<row>:<col>:<code>:<text>"
        # Extra shape: "<path>:<row>:<col>:<code>:<text>"
        if len(parts) == 5:
            _, row_s, col_s, code, msg = parts
        else:
            row_s, col_s, code, msg = parts[-4], parts[-3], parts[-2], parts[-1]
        try:
            row = int(row_s)
            col = int(col_s)
        except ValueError:
            continue
        out.append(LintError(
            line=max(0, row - 1),
            column=max(0, col - 1),
            kind="error",
            message=f"{code.strip()}: {msg.strip()}",
            source="flake8",
        ))
    return out


__all__ = [
    "DEFAULT_FLAKE8_TIMEOUT",
    "FLAKE8_FATAL_SELECT",
    "lint_python",
]
