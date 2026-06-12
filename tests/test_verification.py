"""Phase 4 verification harness.

Each test builds a fixture project on disk, primes a ProjectSession +
CompletionClaim to match Claude's reported state, then runs the
verifier and asserts the right check fails (or the whole report
passes for the happy-path case).

Subprocess use: pytest, py_compile, and (when present) node are all
real. Each check has its own timeout, so a hung fixture can't take
the whole suite down.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import pytest

from kenning.coding.session import (
    CompletionClaim,
    SessionStore,
)
from kenning.coding.verification import (
    CheckId,
    Verifier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(store: SessionStore, project_root: Path, *, claim: CompletionClaim):
    session = store.create(
        project_root=project_root,
        user_intent="x",
        mode="new",
        model="haiku",
    )
    store.record_completion_claim(session.session_id, claim)
    # The session was created just now -- shift its started_at backwards
    # so files we just wrote register as "modified after start". Without
    # this, the mtime check (modified_at > started_at) is racy.
    s = store.get(session.session_id)
    s.started_at = time.time() - 5.0
    return session


def _verifier(tmp_path: Path) -> Verifier:
    store = SessionStore()
    return Verifier(store=store, sandbox_root=tmp_path)


@pytest.fixture
def env(tmp_path: Path):
    store = SessionStore()
    verifier = Verifier(
        store=store,
        sandbox_root=tmp_path,
        smoke_timeout_s=4.0,
        test_timeout_s=30.0,
        lint_timeout_s=15.0,
    )
    return {"store": store, "verifier": verifier, "tmp_path": tmp_path}


# ---------------------------------------------------------------------------
# Happy path: a clean Python project with passing tests passes verification.
# ---------------------------------------------------------------------------


def test_happy_path_clean_python_project(env):
    project = env["tmp_path"] / "clean_project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project]\nname = 'clean_project'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    (project / "main.py").write_text(
        "def add(a, b):\n    return a + b\n\n"
        "if __name__ == '__main__':\n    print(add(2, 3))\n",
        encoding="utf-8",
    )
    (project / "test_main.py").write_text(
        "from main import add\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n"
        "def test_add_negatives():\n    assert add(-1, -2) == -3\n",
        encoding="utf-8",
    )
    claim = CompletionClaim(
        summary="clean project",
        entry_point="main.py",
        run_command=None,
        files_created=["pyproject.toml", "main.py", "test_main.py"],
        files_modified=[],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert report.passed, "happy path should pass; failures: " + ", ".join(
        f"{c.check.value}={c.detail[:120]}" for c in report.failures
    )
    # Test suite check should have actually executed (not skipped).
    test_check = next(c for c in report.checks if c.check == CheckId.TESTS)
    assert not test_check.skipped


# ---------------------------------------------------------------------------
# Defective fixture 1: claimed file missing on disk.
# ---------------------------------------------------------------------------


def test_missing_claimed_file_caught(env):
    project = env["tmp_path"] / "missing_file"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "main.py").write_text("def f(): pass\n", encoding="utf-8")
    # claim says we created `helper.py` but we didn't.
    claim = CompletionClaim(
        summary="x",
        files_created=["main.py", "helper.py"],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    files_check = next(c for c in report.checks if c.check == CheckId.FILES_EXIST)
    assert not files_check.passed
    assert "helper.py" in files_check.detail


# ---------------------------------------------------------------------------
# Defective fixture 2: empty source files.
# ---------------------------------------------------------------------------


def test_empty_source_file_caught(env):
    project = env["tmp_path"] / "empty"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "main.py").write_text("", encoding="utf-8")  # 0 bytes
    claim = CompletionClaim(
        summary="x",
        files_created=["main.py"],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    structure = next(c for c in report.checks if c.check == CheckId.STRUCTURE)
    assert not structure.passed
    assert "empty" in structure.detail.lower()
    assert "main.py" in structure.detail


# ---------------------------------------------------------------------------
# Defective fixture 3: failing tests.
# ---------------------------------------------------------------------------


def test_failing_test_suite_caught(env):
    project = env["tmp_path"] / "failing_tests"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "math_helpers.py").write_text(
        "def add(a, b):\n    return a - b  # deliberately wrong\n",
        encoding="utf-8",
    )
    (project / "test_math_helpers.py").write_text(
        "from math_helpers import add\n\n"
        "def test_add():\n    assert add(2, 3) == 5  # will fail\n",
        encoding="utf-8",
    )
    claim = CompletionClaim(
        summary="x",
        files_created=["math_helpers.py", "test_math_helpers.py"],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    tests = next(c for c in report.checks if c.check == CheckId.TESTS)
    assert not tests.passed
    # Failure detail should reference the failing test.
    assert "failure" in tests.detail.lower() or "failed" in tests.detail.lower()


# ---------------------------------------------------------------------------
# Defective fixture 4: crashing entry point.
# ---------------------------------------------------------------------------


def test_crashing_entry_point_caught(env):
    project = env["tmp_path"] / "crashing"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "main.py").write_text(
        "import nonexistent_module_definitely\n"
        "print('never reached')\n",
        encoding="utf-8",
    )
    claim = CompletionClaim(
        summary="x",
        entry_point="main.py",
        files_created=["main.py"],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    smoke = next(c for c in report.checks if c.check == CheckId.SMOKE)
    assert not smoke.passed
    assert "exit" in smoke.detail.lower() or "error" in smoke.detail.lower()


# ---------------------------------------------------------------------------
# Defective fixture 5: Python syntax error.
# ---------------------------------------------------------------------------


def test_python_syntax_error_caught(env):
    project = env["tmp_path"] / "syntax_error"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "main.py").write_text(
        "def broken(:\n    return 0\n",  # invalid Python
        encoding="utf-8",
    )
    claim = CompletionClaim(
        summary="x",
        files_created=["main.py"],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    lint = next(c for c in report.checks if c.check == CheckId.LINT)
    assert not lint.passed
    assert "syntax" in lint.detail.lower() or "invalid" in lint.detail.lower()


# ---------------------------------------------------------------------------
# Defective fixture 6: claimed file outside project root (pollution).
# ---------------------------------------------------------------------------


def test_file_pollution_caught(env, tmp_path: Path):
    project = env["tmp_path"] / "polluted"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "main.py").write_text("x = 1\n", encoding="utf-8")
    # An ABSOLUTE claimed path that lives outside project.
    outside = (tmp_path / "outside" / "stray.py")
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("y = 2\n", encoding="utf-8")
    claim = CompletionClaim(
        summary="x",
        files_created=["main.py", str(outside)],
    )
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    poll = next(c for c in report.checks if c.check == CheckId.NO_POLLUTION)
    assert not poll.passed
    assert "outside" in poll.detail.lower() or "stray.py" in poll.detail


# ---------------------------------------------------------------------------
# Defective fixture 7: claim with no test framework when tests claimed.
# ---------------------------------------------------------------------------


def test_tests_claimed_but_no_test_files_caught(env):
    project = env["tmp_path"] / "no_tests"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "main.py").write_text("x = 1\n", encoding="utf-8")
    claim = CompletionClaim(
        summary="x",
        files_created=["main.py"],
    )
    session = _make_session(env["store"], project, claim=claim)
    # Claude lied about test results.
    env["store"].record_test_results(
        session.session_id,
        passing=4, failing=0, skipped=0, details="all good",
    )
    report = env["verifier"].verify(session.session_id)
    assert not report.passed
    tests = next(c for c in report.checks if c.check == CheckId.TESTS)
    assert not tests.passed
    assert "no recognizable test framework" in tests.detail.lower() or \
           "test files" in tests.detail.lower() or \
           "framework" in tests.detail.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_skip_smoke_when_no_entry_or_run_or_package(env):
    """A bare Python file with no entry_point/run_command and no package
    structure should result in SMOKE skipping, not failing."""
    project = env["tmp_path"] / "lib_no_pkg"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "lib.py").write_text("def f(): pass\n", encoding="utf-8")
    claim = CompletionClaim(summary="x", files_created=["lib.py"])
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    smoke = next(c for c in report.checks if c.check == CheckId.SMOKE)
    assert smoke.skipped or smoke.passed


def test_to_correction_failures_shape(env):
    """The report's correction-payload helper produces dicts with the
    keys the Phase 3 template expects."""
    project = env["tmp_path"] / "shape"
    project.mkdir()
    (project / "main.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    claim = CompletionClaim(summary="x", files_created=["main.py", "missing.py"])
    session = _make_session(env["store"], project, claim=claim)
    report = env["verifier"].verify(session.session_id)
    payload = report.to_correction_failures()
    assert payload, "expected at least one failure entry"
    for entry in payload:
        assert set(entry.keys()) == {"check", "detail", "hint"}
        assert entry["check"]
        assert entry["detail"]


def test_verify_raises_when_no_completion_claim(env):
    project = env["tmp_path"] / "noclaim"
    project.mkdir()
    session = env["store"].create(project_root=project, user_intent="x")
    with pytest.raises(ValueError):
        env["verifier"].verify(session.session_id)


# ---------------------------------------------------------------------------
# verify_tests_only: spec's verification.run_test_only.
# ---------------------------------------------------------------------------


def test_verify_tests_only_runs_just_the_test_check(env):
    project = env["tmp_path"] / "test_only"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (project / "test_smoke.py").write_text(
        "def test_smoke():\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    claim = CompletionClaim(summary="x", files_created=["test_smoke.py"])
    session = _make_session(env["store"], project, claim=claim)
    result = env["verifier"].verify_tests_only(session.session_id)
    assert result.check == CheckId.TESTS
    assert result.passed
