"""End-to-end Phase 6 verification.

These tests spawn a real AI coding agent subprocess against a real sandbox
directory and verify both the orchestration layer (bridge -> runner) and
the actual code that AI coding agent produces.

Slow tier: gated on ``PYTEST_RUN_GPU_TESTS=1`` AND requires the AI coding agent
CLI to be installed. Each test costs a small number of haiku tokens and
takes 10-60s.

Test plan:

1. **New-project flow (`test_new_project_creates_files_at_dynamic_root`)**
   * Empty sandbox, fresh registry.
   * Create a NEW project under sandbox root via ``new_sandbox_project``.
   * Submit a small task. Verify AI coding agent created the requested file
     INSIDE the project subdirectory and NOT at the sandbox root.

2. **Existing-project flow (`test_existing_project_edits_correct_root`)**
   * Pre-create two project subfolders in the sandbox, each registered.
   * Submit a task targeting project A.
   * Verify project A's file was modified, project B was untouched.
   * This is the dynamic-root requirement: AI coding agent's cwd MUST be the
     project subdir, not the shared sandbox root.

3. **Progress narration during a real run
   (`test_progress_narration_during_real_task`)**
   * Mid-task, ``progress_narration`` returns a non-trivial status that
     mentions the current step.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional

import pytest

from kenning.coding import (
    CodingTaskRunner,
    DirectClaudeCodeBridge,
    Project,
    ProjectRegistry,
    TaskRequest,
    new_sandbox_project,
)


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
        reason="set PYTEST_RUN_GPU_TESTS=1 to run e2e AI coding agent tests",
    ),
]


def _bridge() -> DirectClaudeCodeBridge:
    """Resolve the real claude CLI; skip the test if it's missing."""
    try:
        return DirectClaudeCodeBridge()
    except FileNotFoundError as e:
        pytest.skip(str(e))


def _runner(bridge: DirectClaudeCodeBridge, tmp_path: Path) -> CodingTaskRunner:
    return CodingTaskRunner(
        bridge=bridge,
        log_path=tmp_path / "coding_audit.jsonl",
    )


def _wait_with_progress(runner: CodingTaskRunner, timeout_s: float = 240.0) -> None:
    """Spin until the active task completes; raise TimeoutError otherwise."""
    deadline = time.monotonic() + timeout_s
    while runner.has_active_task():
        if time.monotonic() > deadline:
            runner.cancel_active()
            raise TimeoutError("e2e task did not complete in time")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# 1. New-project flow.
# ---------------------------------------------------------------------------


def test_new_project_creates_files_at_dynamic_root(tmp_path: Path):
    """Verify that a new project gets its own subdirectory and AI coding agent
    writes ONLY inside that subdirectory."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    registry = ProjectRegistry(path=tmp_path / "projects.json")

    project = new_sandbox_project(
        registry,
        name="Greeter",
        description="single-file greeting script",
        sandbox_root=sandbox,
        aliases=["greeter project"],
    )
    project_root = Path(project.path)
    # Sandbox should have exactly one subdirectory now -- the new project.
    assert [p.name for p in sandbox.iterdir()] == [project_root.name]

    bridge = _bridge()
    runner = _runner(bridge, tmp_path)
    handle = runner.start_task(TaskRequest(
        task_prompt=(
            "Create a single file named `greeting.txt` containing exactly "
            "the line `hello from kenning`. Do not create any other files."
        ),
        cwd=project_root,
        model="haiku",
        require_testing=False,  # tiny one-file task; testing prompt would inflate it
        timeout_s=180.0,
        label="greeter",
    ))

    result = handle.wait(timeout=180.0)
    assert result.success, (
        f"AI coding agent failed: exit={result.exit_status} error={result.error} summary={result.summary[:300]}"
    )

    # File exists at the dynamic project root, not at the sandbox root.
    expected_file = project_root / "greeting.txt"
    assert expected_file.is_file(), (
        f"greeting.txt missing at expected path. project_root={project_root} "
        f"contents={list(project_root.iterdir())} "
        f"sandbox_contents={list(sandbox.iterdir())}"
    )
    contents = expected_file.read_text(encoding="utf-8").strip()
    assert "hello from kenning" in contents.lower(), f"unexpected file body: {contents!r}"

    # Sandbox root has no extra files (Claude didn't escape cwd).
    sandbox_files = [p for p in sandbox.iterdir() if p.is_file()]
    assert sandbox_files == [], (
        f"Sandbox root should be empty of files; got {sandbox_files}"
    )

    # Bridge result agrees with the filesystem truth.
    created_names = {p.name for p in result.files_created}
    assert "greeting.txt" in created_names


# ---------------------------------------------------------------------------
# 2. Existing-project flow with dynamic root selection.
# ---------------------------------------------------------------------------


def test_existing_project_edits_correct_root(tmp_path: Path):
    """Two projects exist side-by-side. Asking Kenning to edit project A
    must modify A's files only -- B must remain pristine."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    registry = ProjectRegistry(path=tmp_path / "projects.json")

    # Project A: calculator, has add() only.
    proj_a = sandbox / "calculator"
    proj_a.mkdir()
    (proj_a / "calc.py").write_text(
        "def add(x, y):\n    return x + y\n",
        encoding="utf-8",
    )
    proj_a_initial_other_files = list((proj_a).iterdir())

    # Project B: greeter, totally unrelated.
    proj_b = sandbox / "greeter"
    proj_b.mkdir()
    (proj_b / "greet.py").write_text(
        "def greet(name):\n    return f'hello {name}'\n",
        encoding="utf-8",
    )
    proj_b_initial = {p.name: p.read_bytes() for p in proj_b.iterdir() if p.is_file()}

    registry.add(Project(
        name="Calculator",
        path=str(proj_a),
        aliases=["calc", "the calculator project"],
        language="python",
        description="basic arithmetic helpers",
    ))
    registry.add(Project(
        name="Greeter",
        path=str(proj_b),
        aliases=["greeting", "greet project"],
        language="python",
        description="produces hello-world greetings",
    ))

    # Resolve "the calculator" via the registry (lexical -- no embedder needed).
    from kenning.coding import ProjectResolver, ResolutionKind
    resolution = ProjectResolver(registry).resolve("the calculator project")
    assert resolution.kind in {
        ResolutionKind.EXACT, ResolutionKind.ALIAS, ResolutionKind.SUBSTRING,
    }
    assert resolution.project is not None
    target_root = Path(resolution.project.path)
    assert target_root == proj_a

    bridge = _bridge()
    runner = _runner(bridge, tmp_path)
    handle = runner.start_task(TaskRequest(
        task_prompt=(
            "Add a new function `subtract(x, y)` to calc.py that returns "
            "x - y. Do not change `add`. Do not create new files. Make "
            "the smallest possible edit."
        ),
        cwd=target_root,
        model="haiku",
        require_testing=False,
        timeout_s=180.0,
        label="add-subtract",
    ))
    result = handle.wait(timeout=180.0)
    assert result.success, (
        f"AI coding agent failed: exit={result.exit_status} error={result.error}"
    )

    # calc.py now defines BOTH add and subtract.
    calc_body = (proj_a / "calc.py").read_text(encoding="utf-8")
    assert "def add(" in calc_body
    assert "def subtract(" in calc_body, (
        f"subtract() not added to calc.py. Body:\n{calc_body}"
    )

    # Greeter (project B) is byte-identical to its initial state.
    proj_b_after = {p.name: p.read_bytes() for p in proj_b.iterdir() if p.is_file()}
    assert proj_b_after == proj_b_initial, (
        f"Greeter project was touched! "
        f"before={list(proj_b_initial)} after={list(proj_b_after)}"
    )

    # Sandbox root holds only the two project directories -- nothing else
    # was scribbled at the higher level.
    top_level = sorted(p.name for p in sandbox.iterdir())
    assert top_level == ["calculator", "greeter"]


# ---------------------------------------------------------------------------
# 3. Progress narration during a live task.
# ---------------------------------------------------------------------------


def test_progress_narration_during_real_task(tmp_path: Path):
    """While the task is running, progress_narration should produce a
    sensible status string. This is the voice 'how's it going?' path."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    registry = ProjectRegistry(path=tmp_path / "projects.json")
    project = new_sandbox_project(
        registry,
        name="ProgressTest",
        sandbox_root=sandbox,
    )

    bridge = _bridge()
    runner = _runner(bridge, tmp_path)
    handle = runner.start_task(TaskRequest(
        task_prompt=(
            "Create three text files, alpha.txt beta.txt gamma.txt, each "
            "with a single line of plain content. No other files."
        ),
        cwd=Path(project.path),
        model="haiku",
        require_testing=False,
        timeout_s=180.0,
        label="progress",
    ))

    # Poll progress while running. Capture at least one mid-task narration.
    captured: list[str] = []
    deadline = time.monotonic() + 180.0
    while runner.has_active_task() and time.monotonic() < deadline:
        msg = runner.progress_narration()
        captured.append(msg)
        time.sleep(0.6)

    result = handle.wait(timeout=10.0)
    assert result.success, f"task failed: {result.error}"

    # We should have at least one mid-task message that wasn't the
    # "no active task" placeholder, and the final completion message.
    mid = [m for m in captured if m and "no coding task" not in m.lower()]
    assert mid, f"never captured a live progress narration; captures={captured}"
    final = runner.completion_narration()
    assert "Done." in final or "complete" in final.lower()
    assert "Project root" in final
