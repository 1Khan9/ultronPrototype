"""Tests for :mod:`ultron.coding.python_lint` and
:mod:`ultron.coding.tree_sitter_lint`."""

from __future__ import annotations

from pathlib import Path

import pytest

from ultron.coding.python_lint import (
    DEFAULT_FLAKE8_TIMEOUT,
    FLAKE8_FATAL_SELECT,
    lint_python,
)
from ultron.coding.tree_sitter_lint import (
    LintError,
    LintReport,
    tree_sitter_lint,
)


# ---------------------------------------------------------------------------
# tree_sitter_lint
# ---------------------------------------------------------------------------


def test_tree_sitter_lint_clean_python(tmp_path: Path):
    target = tmp_path / "ok.py"
    target.write_text("def foo():\n    return 42\n")
    report = tree_sitter_lint(target)
    assert report.ok
    assert report.errors == []
    assert report.language == "python"


def test_tree_sitter_lint_broken_python(tmp_path: Path):
    target = tmp_path / "broken.py"
    target.write_text("def foo(:\n    return\n")  # malformed parameter list
    report = tree_sitter_lint(target)
    # Tree-sitter is fault-tolerant — it might recover or flag the missing
    # parenthesis. Either way, the report should signal a problem.
    assert not report.ok or report.errors


def test_tree_sitter_lint_clean_javascript(tmp_path: Path):
    target = tmp_path / "ok.js"
    target.write_text("function foo() { return 42; }\n")
    report = tree_sitter_lint(target)
    assert report.language == "javascript"
    assert report.ok


def test_tree_sitter_lint_unsupported_language(tmp_path: Path):
    target = tmp_path / "data.unknown"
    target.write_text("anything\n")
    report = tree_sitter_lint(target)
    assert report.skipped_reason
    assert not report.errors


def test_tree_sitter_lint_missing_file(tmp_path: Path):
    target = tmp_path / "does_not_exist.py"
    report = tree_sitter_lint(target)
    assert report.skipped_reason


def test_tree_sitter_lint_empty_file(tmp_path: Path):
    target = tmp_path / "empty.py"
    target.write_text("")
    report = tree_sitter_lint(target)
    assert report.ok


def test_lint_report_ok_property():
    assert LintReport(path="x.py").ok is True
    assert LintReport(path="x.py", errors=[LintError(0, 0, "error", "x")]).ok is False
    assert LintReport(path="x.py", skipped_reason="x").ok is False


def test_lint_report_summary_with_no_errors():
    assert LintReport(path="x.py").summary() == "no errors"


def test_lint_report_summary_with_skip():
    assert "skipped" in LintReport(path="x.py", skipped_reason="x").summary()


def test_lint_report_summary_with_errors():
    r = LintReport(
        path="x.py",
        errors=[
            LintError(line=4, column=2, kind="error", message="boom"),
            LintError(line=10, column=0, kind="error", message="oops"),
        ],
    )
    s = r.summary()
    assert "line 5" in s  # 0-based -> 1-based for display
    assert "boom" in s
    assert "+1 more" in s


# ---------------------------------------------------------------------------
# lint_python — Layer 2 (compile)
# ---------------------------------------------------------------------------


def test_lint_python_clean_file(tmp_path: Path):
    target = tmp_path / "clean.py"
    target.write_text("def foo():\n    return 42\n")
    report = lint_python(target, run_flake8=False)
    assert report.errors == []
    assert report.language == "python"


def test_lint_python_compile_catches_syntax_error(tmp_path: Path):
    target = tmp_path / "bad.py"
    target.write_text("def foo(:\n    return\n")
    report = lint_python(target, run_flake8=False)
    # Either tree-sitter or compile should flag this.
    assert report.errors
    # At least one error should come from a real Python layer.
    sources = {e.source for e in report.errors}
    assert "compile" in sources or "tree_sitter" in sources


def test_lint_python_compile_catches_unmatched_paren(tmp_path: Path):
    target = tmp_path / "bad.py"
    target.write_text("def foo():\n    print('hi'\n")
    report = lint_python(target, run_flake8=False)
    assert report.errors


def test_lint_python_compile_handles_null_bytes(tmp_path: Path):
    target = tmp_path / "with_nulls.py"
    target.write_bytes(b"x = 1\n\x00\n")
    report = lint_python(target, run_flake8=False)
    # Null bytes -> ValueError in compile(); should not crash.
    assert isinstance(report, LintReport)


def test_lint_python_compile_handles_bad_encoding(tmp_path: Path):
    target = tmp_path / "bad_enc.py"
    target.write_bytes(b"# -*- coding: utf-8 -*-\n\x80\xff\n")
    report = lint_python(target, run_flake8=False)
    # Encoding failure surfaces as a compile-level error and doesn't crash.
    assert isinstance(report, LintReport)


# ---------------------------------------------------------------------------
# lint_python — Layer 3 (flake8 FATAL-only)
# ---------------------------------------------------------------------------


def test_flake8_fatal_select_covers_aider_set():
    """Sanity-check the FATAL rule set matches the catalog."""
    expected = {"E9", "F821", "F823", "F831", "F406", "F407", "F701", "F702", "F704", "F706"}
    actual = set(FLAKE8_FATAL_SELECT.replace(" ", "").split(","))
    assert actual == expected


def test_lint_python_flake8_catches_undefined_name(tmp_path: Path):
    """F821: name used but never defined."""
    target = tmp_path / "undef.py"
    target.write_text("def foo():\n    return undefined_thing\n")
    report = lint_python(target)
    # F821 is in the FATAL set; should be caught.
    fatal_codes = [e.message for e in report.errors if e.source == "flake8"]
    assert any("F821" in code for code in fatal_codes), (
        f"expected F821 in {[e.message for e in report.errors]}"
    )


def test_lint_python_flake8_ignores_style_errors(tmp_path: Path):
    """E1xx, E2xx, W* are NOT in the FATAL set; should be ignored."""
    target = tmp_path / "stylish.py"
    target.write_text("def foo( ):\n    x=1\n    return x\n")
    report = lint_python(target)
    # No fatal errors — style is explicitly out of scope.
    flake8_errors = [e for e in report.errors if e.source == "flake8"]
    assert flake8_errors == [], (
        f"unexpected style errors: {[e.message for e in flake8_errors]}"
    )


def test_lint_python_flake8_can_be_disabled(tmp_path: Path):
    target = tmp_path / "undef.py"
    target.write_text("def foo():\n    return undefined_thing\n")
    report = lint_python(target, run_flake8=False)
    flake8_errors = [e for e in report.errors if e.source == "flake8"]
    assert flake8_errors == []


# ---------------------------------------------------------------------------
# Non-Python paths
# ---------------------------------------------------------------------------


def test_lint_python_non_python_path_returns_tree_sitter_only(tmp_path: Path):
    """Calling lint_python on a .js file should return tree-sitter result."""
    target = tmp_path / "ok.js"
    target.write_text("function foo() { return 42; }\n")
    report = lint_python(target)
    assert report.language == "javascript"
    # No compile/flake8 errors should appear for a JS file.
    assert all(e.source == "tree_sitter" for e in report.errors)


# ---------------------------------------------------------------------------
# Listener integration with the runner
# ---------------------------------------------------------------------------


def test_runner_lint_listener_disabled_by_default(tmp_path: Path):
    """When the flag is off, _make_pre_write_lint_listener returns None."""
    from ultron.coding.runner import CodingTaskRunner

    # We don't need a full runner construction — call the method on a
    # stand-in object that has the necessary attributes.
    class FakeHandle:
        def task_id(self):
            return "test-id"

    runner = CodingTaskRunner.__new__(CodingTaskRunner)
    # Reach into the method directly so we don't need to spin up the
    # full runner. The config knob is what matters here.
    listener = runner._make_pre_write_lint_listener(FakeHandle())
    # Default config has enabled=False, so the listener should be None.
    assert listener is None
