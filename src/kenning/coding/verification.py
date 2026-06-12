"""Phase 4: post-``declare_complete`` verification.

When Claude calls :func:`declare_complete`, the supervisor doesn't take
the claim at face value. Six structured checks run before the session
transitions to ``COMPLETE``; if any fail, the coordinator drafts a
correction prompt (rendered via the Phase 3 template) and Claude is
told to fix the failures.

The checks are deliberately narrow and deterministic so a fixture-based
test harness can build broken projects and assert each check catches
its corresponding defect.

Public API:
  * :class:`Verifier`       -- runs the suite, returns a report.
  * :class:`CheckResult`    -- one check's outcome.
  * :class:`VerificationReport` -- full report with helpers for
    rendering the correction prompt.

Subprocess discipline: every check that runs an external process uses a
short timeout. The verifier never blocks indefinitely on a misbehaving
project.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from ultron.coding.session import (
    CompletionClaim,
    ProjectSession,
    SessionStore,
)
from ultron.utils.logging import get_logger

logger = get_logger("coding.verification")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class CheckId(str, Enum):
    FILES_EXIST = "files_exist"
    STRUCTURE = "structure"
    TESTS = "tests"
    SMOKE = "smoke"
    LINT = "lint"
    NO_POLLUTION = "no_pollution"


@dataclass
class CheckResult:
    """One check's outcome.

    ``passed`` is the actionable boolean. ``skipped`` means the check
    was inapplicable (e.g., no entry_point was claimed, so smoke didn't
    run); the report treats skipped as non-blocking. ``detail`` is what
    Claude reads in the correction prompt; ``hint`` is an optional
    one-liner suggesting a remediation.
    """

    check: CheckId
    passed: bool
    skipped: bool = False
    detail: str = ""
    hint: Optional[str] = None
    duration_ms: float = 0.0
    raw: Optional[Dict[str, Any]] = None  # diagnostic payload, audit-only


@dataclass
class VerificationReport:
    """Full verification result. ``passed`` iff every non-skipped check
    passed. ``failures`` is the actionable subset for the correction
    prompt."""

    session_id: str
    passed: bool
    checks: List[CheckResult] = field(default_factory=list)
    duration_s: float = 0.0
    skipped_count: int = 0

    @property
    def failures(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed and not c.skipped]

    def to_correction_failures(self) -> List[Dict[str, str]]:
        """Shape the failure list for the Phase 3 correction template."""
        return [
            {
                "check": _human_check_label(c.check),
                "detail": c.detail.strip() or "(no detail provided)",
                "hint": c.hint or "",
            }
            for c in self.failures
        ]


def _human_check_label(check: CheckId) -> str:
    return {
        CheckId.FILES_EXIST: "Files exist as claimed",
        CheckId.STRUCTURE: "Project structure sanity",
        CheckId.TESTS: "Test suite runs and passes",
        CheckId.SMOKE: "Smoke test entry point",
        CheckId.LINT: "Syntax / lint check",
        CheckId.NO_POLLUTION: "No file pollution outside project root",
    }[check]


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class Verifier:
    """Runs the 6 checks against a session + project tree.

    Args:
        store: shared :class:`SessionStore` (for reading the session).
        smoke_timeout_s / test_timeout_s / lint_timeout_s: per-check
            subprocess deadlines.
        sandbox_root: the directory under which all legitimate session
            paths live. Used by the no-pollution check.
    """

    def __init__(
        self,
        store: SessionStore,
        *,
        smoke_timeout_s: float = float(settings.CODING_VERIFICATION_SMOKE_TIMEOUT_S),
        test_timeout_s: float = float(settings.CODING_VERIFICATION_TEST_TIMEOUT_S),
        lint_timeout_s: float = float(settings.CODING_VERIFICATION_LINT_TIMEOUT_S),
        sandbox_root: Optional[Path] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        self.store = store
        self.smoke_timeout_s = smoke_timeout_s
        self.test_timeout_s = test_timeout_s
        self.lint_timeout_s = lint_timeout_s
        self.sandbox_root = (
            Path(sandbox_root).resolve()
            if sandbox_root
            else Path(settings.CODING_SANDBOX_PATH).resolve()
        )
        self.python_executable = python_executable or sys.executable

    # --- public entry point -------------------------------------------------

    def verify(self, session_id: str) -> VerificationReport:
        session = self.store.get(session_id)
        if session.completion_claim is None:
            raise ValueError(
                f"verify({session_id}): session has no completion_claim "
                f"yet -- declare_complete must be called first."
            )

        t0 = time.monotonic()
        checks: List[CheckResult] = []
        checks.append(self._check_files_exist(session))
        checks.append(self._check_project_structure(session))
        checks.append(self._check_test_suite(session))
        checks.append(self._check_smoke(session))
        checks.append(self._check_lint(session))
        checks.append(self._check_no_pollution(session))

        all_passed = all(c.passed or c.skipped for c in checks)
        skipped_count = sum(1 for c in checks if c.skipped)
        return VerificationReport(
            session_id=session.session_id,
            passed=all_passed,
            checks=checks,
            duration_s=time.monotonic() - t0,
            skipped_count=skipped_count,
        )

    def verify_tests_only(self, session_id: str) -> CheckResult:
        """Spec: ``verification.run_test_only``. Used by the corrective
        loop when the supervisor wants to re-check tests without redoing
        the structural / smoke checks."""
        session = self.store.get(session_id)
        return self._check_test_suite(session)

    # --- check 1: claimed files exist --------------------------------------

    def _check_files_exist(self, session: ProjectSession) -> CheckResult:
        t0 = time.monotonic()
        claim = session.completion_claim
        assert claim is not None
        project_root = session.project_root
        missing_created: List[str] = []
        missing_modified: List[str] = []
        unchanged_modified: List[str] = []
        for rel in claim.files_created:
            p = project_root / rel
            if not p.is_file():
                missing_created.append(rel)
        for rel in claim.files_modified:
            p = project_root / rel
            if not p.is_file():
                missing_modified.append(rel)
                continue
            try:
                if p.stat().st_mtime <= session.started_at:
                    unchanged_modified.append(rel)
            except OSError:
                missing_modified.append(rel)

        problems: List[str] = []
        if missing_created:
            problems.append(
                "Files claimed as CREATED but missing on disk: "
                + ", ".join(missing_created)
            )
        if missing_modified:
            problems.append(
                "Files claimed as MODIFIED but missing on disk: "
                + ", ".join(missing_modified)
            )
        if unchanged_modified:
            problems.append(
                "Files claimed as MODIFIED but mtime did not advance "
                f"after session start ({_iso(session.started_at)}): "
                + ", ".join(unchanged_modified)
            )
        passed = not problems
        return CheckResult(
            check=CheckId.FILES_EXIST,
            passed=passed,
            detail="; ".join(problems),
            hint=(
                "Either the file paths in declare_complete were wrong, or the "
                "files weren't actually saved. Re-check filenames and Write the "
                "files again."
                if not passed else None
            ),
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    # --- check 2: structure sanity -----------------------------------------

    def _check_project_structure(self, session: ProjectSession) -> CheckResult:
        t0 = time.monotonic()
        root = session.project_root
        if not root.is_dir():
            return CheckResult(
                check=CheckId.STRUCTURE, passed=False,
                detail=f"Project root {root} does not exist.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        py_files = list(root.rglob("*.py"))
        js_files = [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix in {".js", ".ts", ".jsx", ".tsx"}
            and ".pytest_cache" not in p.parts and "node_modules" not in p.parts
        ]
        is_python = bool(py_files)
        is_node = bool(js_files)

        problems: List[str] = []
        empty_files: List[str] = []

        if is_python:
            has_manifest = any((root / m).is_file() for m in (
                "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
            ))
            if not has_manifest:
                problems.append(
                    "Python project is missing a manifest file "
                    "(pyproject.toml / requirements.txt / setup.py)."
                )
            for p in py_files:
                try:
                    if p.stat().st_size == 0:
                        empty_files.append(str(p.relative_to(root)))
                except OSError:
                    continue
        elif is_node:
            if not (root / "package.json").is_file():
                problems.append("Node project is missing package.json.")
            for p in js_files:
                try:
                    if p.stat().st_size == 0:
                        empty_files.append(str(p.relative_to(root)))
                except OSError:
                    continue
        else:
            return CheckResult(
                check=CheckId.STRUCTURE, passed=True, skipped=True,
                detail="Language not Python or Node; skipping structure checks.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        if empty_files:
            problems.append(
                "Source files are empty (0 bytes): " + ", ".join(empty_files)
            )

        passed = not problems
        return CheckResult(
            check=CheckId.STRUCTURE,
            passed=passed,
            detail="; ".join(problems),
            hint=(
                "A project should have a manifest declaring it (pyproject.toml "
                "/ package.json) and non-empty source files."
                if not passed else None
            ),
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    # --- check 3: tests pass -----------------------------------------------

    def _check_test_suite(self, session: ProjectSession) -> CheckResult:
        t0 = time.monotonic()
        root = session.project_root

        # Decide whether the project HAS tests at all. Skip the check
        # only if there are no test files AND Claude didn't claim any.
        py_test_files = [
            p for p in root.rglob("test_*.py")
            if "__pycache__" not in p.parts
        ] + [
            p for p in root.rglob("*_test.py")
            if "__pycache__" not in p.parts
        ]
        ts_test_files = [
            p for p in root.rglob("*.test.ts")
            if "node_modules" not in p.parts
        ] + [
            p for p in root.rglob("*.spec.ts")
            if "node_modules" not in p.parts
        ]
        js_test_files = [
            p for p in root.rglob("*.test.js")
            if "node_modules" not in p.parts
        ] + [
            p for p in root.rglob("*.spec.js")
            if "node_modules" not in p.parts
        ]
        any_test_files = bool(py_test_files or ts_test_files or js_test_files)
        claimed_tests = (
            session.test_status.passing > 0
            or session.test_status.failing > 0
        )

        if not any_test_files and not claimed_tests:
            return CheckResult(
                check=CheckId.TESTS, passed=True, skipped=True,
                detail="No test files present and none claimed; skipping.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        # Python pytest path.
        if py_test_files:
            return self._run_pytest(root, t0)
        # Node test path -- use whatever's in package.json.
        if (ts_test_files or js_test_files) and (root / "package.json").is_file():
            return self._run_node_tests(root, t0)

        return CheckResult(
            check=CheckId.TESTS, passed=False,
            detail="Tests claimed but no recognizable test framework found.",
            hint="Use pytest for Python, jest/vitest for JS/TS.",
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    def _run_pytest(self, root: Path, t0: float) -> CheckResult:
        # Disable the hydra-pytest plugin because the version in this
        # repo's venv (a ML-stack transitive dep) crashes on import under
        # Python 3.11. The project under test wouldn't normally have
        # this plugin installed, but the verifier inherits the parent
        # venv's plugin set, so we suppress it explicitly.
        try:
            proc = subprocess.run(
                [self.python_executable, "-m", "pytest", "-q",
                 "--no-header", "-rN",
                 "-p", "no:hydra_pytest",
                 str(root)],
                capture_output=True, text=True, timeout=self.test_timeout_s,
                cwd=str(root),
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
            )
            stdout = (proc.stdout or "")
            stderr = (proc.stderr or "")
        except subprocess.TimeoutExpired:
            return CheckResult(
                check=CheckId.TESTS, passed=False,
                detail=f"pytest timed out after {self.test_timeout_s:.0f} s.",
                hint="A test is hanging; isolate it and add a tighter timeout.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except FileNotFoundError as e:
            return CheckResult(
                check=CheckId.TESTS, passed=False,
                detail=f"Could not run pytest: {e}",
                hint="Make sure pytest is installed and importable.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        passing, failing, errored = _parse_pytest_summary(stdout + "\n" + stderr)
        ok = (
            proc.returncode == 0
            and failing == 0 and errored == 0
            # Reject a "no tests collected" pass.
            and (passing > 0 or "passed" in stdout.lower())
        )
        if ok:
            return CheckResult(
                check=CheckId.TESTS, passed=True,
                detail=f"pytest: {passing} passing, {failing} failing.",
                duration_ms=(time.monotonic() - t0) * 1000,
                raw={"stdout_tail": stdout[-2000:]},
            )
        # Bubble the relevant failure lines to Claude in the correction.
        failure_lines = _extract_failure_lines(stdout)
        return CheckResult(
            check=CheckId.TESTS, passed=False,
            detail=(
                f"pytest reported {failing} failure(s), {errored} error(s) "
                f"(passing={passing}). Excerpt:\n{failure_lines or stdout[-1500:]}"
            ),
            hint="Read the failure messages and fix the underlying code; "
                 "do not delete the failing tests.",
            duration_ms=(time.monotonic() - t0) * 1000,
            raw={"returncode": proc.returncode, "stdout_tail": stdout[-2000:]},
        )

    def _run_node_tests(self, root: Path, t0: float) -> CheckResult:
        # Best-effort: defer to "npm test" if it's defined.
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            return CheckResult(
                check=CheckId.TESTS, passed=True, skipped=True,
                detail="npm not available; skipping Node tests.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        try:
            proc = subprocess.run(
                [npm, "test", "--silent"],
                capture_output=True, text=True, timeout=self.test_timeout_s,
                cwd=str(root),
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                check=CheckId.TESTS, passed=False,
                detail=f"npm test timed out after {self.test_timeout_s:.0f} s.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        ok = proc.returncode == 0
        return CheckResult(
            check=CheckId.TESTS, passed=ok,
            detail=(
                "npm test passed"
                if ok else
                f"npm test failed (exit {proc.returncode}). "
                f"Excerpt:\n{(proc.stdout or '')[-1500:]}\n"
                f"{(proc.stderr or '')[-500:]}"
            ),
            hint="See the npm test output above; fix the failing case.",
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    # --- check 4: smoke test ----------------------------------------------

    def _check_smoke(self, session: ProjectSession) -> CheckResult:
        t0 = time.monotonic()
        claim = session.completion_claim
        assert claim is not None
        entry_point = claim.entry_point
        run_cmd = claim.run_command

        # Pick what to actually run.
        argv: Optional[List[str]] = None
        smoke_kind = ""
        if run_cmd:
            argv = _split_command(run_cmd)
            smoke_kind = "run_command"
        elif entry_point:
            entry_path = session.project_root / entry_point
            if not entry_path.is_file():
                return CheckResult(
                    check=CheckId.SMOKE, passed=False,
                    detail=f"Claimed entry_point {entry_point!r} does not exist.",
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
            if entry_path.suffix == ".py":
                argv = [self.python_executable, str(entry_path)]
                smoke_kind = "python_entrypoint"
            elif entry_path.suffix == ".js":
                node = shutil.which("node")
                if node:
                    argv = [node, str(entry_path)]
                    smoke_kind = "node_entrypoint"

        if argv is None:
            # Library-style: try `python -c "import <package>"` if structure
            # is python-ish.
            return self._smoke_library_import(session, t0)

        try:
            proc = subprocess.run(
                argv,
                capture_output=True, text=True,
                cwd=str(session.project_root),
                timeout=self.smoke_timeout_s,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
            )
        except subprocess.TimeoutExpired:
            # Exceeding the smoke timeout means the program is still
            # running (likely a server) -- treat as a pass.
            return CheckResult(
                check=CheckId.SMOKE, passed=True,
                detail=(
                    f"{smoke_kind} kept running past {self.smoke_timeout_s:.0f} s; "
                    "treating as a healthy long-running process."
                ),
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except FileNotFoundError as e:
            return CheckResult(
                check=CheckId.SMOKE, passed=False,
                detail=f"Could not start the entry point: {e}",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        ok = proc.returncode == 0
        return CheckResult(
            check=CheckId.SMOKE, passed=ok,
            detail=(
                f"{smoke_kind} exited cleanly."
                if ok else
                f"{smoke_kind} exited with code {proc.returncode}. "
                f"stderr: {(proc.stderr or '')[-400:]}"
            ),
            hint=(
                "The entry point crashes on startup. Run it locally and "
                "fix the import / initialization error."
                if not ok else None
            ),
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    def _smoke_library_import(self, session: ProjectSession, t0: float) -> CheckResult:
        root = session.project_root
        # Look for a package directory: either src/<name>/__init__.py or <name>/__init__.py.
        candidates: List[Path] = []
        for p in (root.iterdir() if root.is_dir() else []):
            if p.is_dir() and (p / "__init__.py").is_file():
                candidates.append(p)
        src = root / "src"
        if src.is_dir():
            for p in src.iterdir():
                if p.is_dir() and (p / "__init__.py").is_file():
                    candidates.append(p)
        if not candidates:
            return CheckResult(
                check=CheckId.SMOKE, passed=True, skipped=True,
                detail="No entry_point / run_command claimed and no package "
                       "directory found; skipping smoke.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        pkg = candidates[0]
        pkg_name = pkg.name
        # Choose PYTHONPATH so the package is importable.
        pythonpath = str(pkg.parent)
        env = os.environ.copy()
        old_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = pythonpath + (os.pathsep + old_pp if old_pp else "")
        try:
            proc = subprocess.run(
                [self.python_executable, "-c", f"import {pkg_name}"],
                capture_output=True, text=True, env=env,
                timeout=self.smoke_timeout_s,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                check=CheckId.SMOKE, passed=False,
                detail=f"Library import for {pkg_name!r} hung past "
                       f"{self.smoke_timeout_s:.0f} s.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        ok = proc.returncode == 0
        return CheckResult(
            check=CheckId.SMOKE, passed=ok,
            detail=(
                f"Library {pkg_name!r} imports cleanly."
                if ok else
                f"`import {pkg_name}` failed: {(proc.stderr or '')[-400:]}"
            ),
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    # --- check 5: lint / syntax -------------------------------------------

    def _check_lint(self, session: ProjectSession) -> CheckResult:
        t0 = time.monotonic()
        root = session.project_root
        py_files = [
            p for p in root.rglob("*.py")
            if "__pycache__" not in p.parts
        ]
        if not py_files:
            return CheckResult(
                check=CheckId.LINT, passed=True, skipped=True,
                detail="No Python files; skipping syntax check.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        try:
            proc = subprocess.run(
                [self.python_executable, "-m", "py_compile", *map(str, py_files)],
                capture_output=True, text=True,
                timeout=self.lint_timeout_s,
                creationflags=(subprocess.CREATE_NO_WINDOW
                               if hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                check=CheckId.LINT, passed=False,
                detail=f"py_compile timed out after {self.lint_timeout_s:.0f} s.",
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        ok = proc.returncode == 0
        return CheckResult(
            check=CheckId.LINT, passed=ok,
            detail=(
                f"py_compile succeeded across {len(py_files)} file(s)."
                if ok else
                f"Syntax errors found:\n{(proc.stderr or '')[-1000:]}"
            ),
            hint=(
                "There is a Python syntax error -- run `python -m py_compile "
                "<file>` locally to pinpoint the line."
                if not ok else None
            ),
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    # --- check 6: no file pollution ----------------------------------------

    def _check_no_pollution(self, session: ProjectSession) -> CheckResult:
        t0 = time.monotonic()
        # Make absolute project_root consistent.
        root = session.project_root.resolve()
        offenders: List[str] = []
        # Examine every claimed path -- if any are absolute and escape
        # the root, that's pollution. (The bridge enforces cwd, but a
        # claim payload can still report a path outside.)
        claim = session.completion_claim
        assert claim is not None
        all_claimed = list(claim.files_created) + list(claim.files_modified)
        for rel in all_claimed:
            p = Path(rel)
            if p.is_absolute():
                resolved = p.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    offenders.append(str(resolved))
                    continue
        # And: anything Claude stamped onto session.files_created /
        # files_modified that's outside the root.
        for rec in list(session.files_created) + list(session.files_modified):
            p = Path(rec.path)
            target = p if p.is_absolute() else (root / p)
            try:
                target.resolve().relative_to(root)
            except ValueError:
                offenders.append(str(target))

        # Belt-and-suspenders: if the sandbox is configured, none of the
        # session paths should escape it. (We check against sandbox_root
        # only when the project root is itself inside the sandbox -- tests
        # using tmp_path live elsewhere and shouldn't trigger this.)
        if self.sandbox_root and self._is_under(root, self.sandbox_root):
            for o in list(offenders):
                # already counted
                continue
            for rec in session.files_created + session.files_modified:
                p = Path(rec.path)
                if p.is_absolute():
                    try:
                        p.resolve().relative_to(self.sandbox_root)
                    except ValueError:
                        offenders.append(str(p))

        offenders = sorted(set(offenders))
        passed = not offenders
        return CheckResult(
            check=CheckId.NO_POLLUTION, passed=passed,
            detail=(
                "No files outside project root were touched."
                if passed else
                "These claimed paths fall outside the project root:\n  "
                + "\n  ".join(offenders)
            ),
            hint=(
                "Only modify files inside the project's working directory. "
                "If the change really needs to touch a shared location, "
                "request_clarification first."
                if not passed else None
            ),
            duration_ms=(time.monotonic() - t0) * 1000,
        )

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False


# ---------------------------------------------------------------------------
# Pytest-output parsing
# ---------------------------------------------------------------------------


_PYTEST_LINE_RE = re.compile(
    r"=+\s*(?:(?P<failed>\d+)\s+failed,?\s*)?"
    r"(?:(?P<passed>\d+)\s+passed,?\s*)?"
    r"(?:(?P<errors>\d+)\s+error(?:s)?,?\s*)?"
    r".*?in\s+\d",
    re.IGNORECASE,
)


def _parse_pytest_summary(text: str) -> Tuple[int, int, int]:
    """Pull (passing, failing, errored) from a pytest summary line.

    Tolerant of -q output where the summary collapses to ``=== 1 failed,
    2 passed in 0.12s ===`` style lines.
    """
    passing = failing = errored = 0
    for line in reversed(text.splitlines()[-30:]):
        m = _PYTEST_LINE_RE.search(line)
        if not m:
            continue
        if m.group("passed"):
            passing = int(m.group("passed"))
        if m.group("failed"):
            failing = int(m.group("failed"))
        if m.group("errors"):
            errored = int(m.group("errors"))
        if passing or failing or errored:
            break
    return passing, failing, errored


def _extract_failure_lines(text: str, max_lines: int = 25) -> str:
    """Pick the most informative chunk of pytest output for the correction."""
    lines = text.splitlines()
    # Prefer the FAILED summary block at the end if present.
    out: List[str] = []
    in_failures = False
    for line in lines:
        if "FAILED" in line and "::" in line:
            out.append(line)
            in_failures = True
        elif in_failures and line.startswith(("==", "---", "FAILED", "ERROR")):
            out.append(line)
        if len(out) >= max_lines:
            break
    if out:
        return "\n".join(out)
    # Fallback: tail.
    return "\n".join(lines[-max_lines:])


def _split_command(cmd: str) -> List[str]:
    """Best-effort cmdline split. Keeps quoted segments intact."""
    import shlex
    try:
        return shlex.split(cmd, posix=(os.name != "nt"))
    except ValueError:
        return cmd.split()


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
