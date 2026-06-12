"""Tests for kenning.hooks.registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.hooks import registry as reg
from kenning.hooks.discovery import HookScript
from kenning.hooks.lifecycle import HookKind, HookOutcome, HookPayload
from kenning.hooks.runner import HookRunner, HookRunResult


class _StubRunner:
    """Test stub returning a scripted outcome per script path."""

    def __init__(self, outcomes_by_path: dict[Path, HookOutcome]) -> None:
        self._outcomes = outcomes_by_path
        self.invocations: list[tuple[Path, HookPayload]] = []

    def run(self, script: HookScript, payload: HookPayload) -> HookRunResult:
        self.invocations.append((script.path, payload))
        outcome = self._outcomes.get(script.path, HookOutcome())
        return HookRunResult(
            script=script,
            outcome=outcome,
            elapsed_seconds=0.01,
            exit_code=0,
        )


def _write_py_hook(dir_: Path, name: str) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_text("# stub", encoding="utf-8")


class TestFanout:
    def test_no_hooks_returns_empty_result(self, tmp_path: Path) -> None:
        registry = reg.HookRegistry([(tmp_path, "project")])
        result = registry.fire(HookKind.TASK_START, HookPayload(kind=HookKind.TASK_START))
        assert result.cancelled is False
        assert result.context_modification == ""
        assert result.per_hook_results == ()
        assert result.error_count == 0

    def test_single_hook_runs(self, tmp_path: Path) -> None:
        _write_py_hook(tmp_path, "TaskStart.py")
        outcomes = {
            (tmp_path / "TaskStart.py").resolve(): HookOutcome(
                context_modification="hello",
            ),
        }
        stub = _StubRunner(outcomes)
        registry = reg.HookRegistry([(tmp_path, "project")], runner=stub)
        result = registry.fire(HookKind.TASK_START, HookPayload(kind=HookKind.TASK_START))
        assert len(result.per_hook_results) == 1
        assert "hello" in result.context_modification
        assert result.cancelled is False
        assert len(stub.invocations) == 1

    def test_cancel_aggregates(self, tmp_path: Path) -> None:
        _write_py_hook(tmp_path, "PreToolUse.py")
        outcomes = {
            (tmp_path / "PreToolUse.py").resolve(): HookOutcome(cancel=True),
        }
        stub = _StubRunner(outcomes)
        registry = reg.HookRegistry([(tmp_path, "project")], runner=stub)
        result = registry.fire(HookKind.PRE_TOOL_USE, HookPayload(kind=HookKind.PRE_TOOL_USE))
        assert result.cancelled is True

    def test_multiple_hooks_combined_context(self, tmp_path: Path) -> None:
        global_dir = tmp_path / "g"
        project_dir = tmp_path / "p"
        _write_py_hook(global_dir, "TaskStart.py")
        _write_py_hook(project_dir, "TaskStart.py")
        outcomes = {
            (global_dir / "TaskStart.py").resolve(): HookOutcome(
                context_modification="from-global",
            ),
            (project_dir / "TaskStart.py").resolve(): HookOutcome(
                context_modification="from-project",
            ),
        }
        stub = _StubRunner(outcomes)
        registry = reg.HookRegistry([
            (global_dir, "global"),
            (project_dir, "project"),
        ], runner=stub)
        result = registry.fire(HookKind.TASK_START, HookPayload(kind=HookKind.TASK_START))
        # Both hooks' contexts present, wrapped in <hook_context> blocks.
        assert "from-global" in result.context_modification
        assert "from-project" in result.context_modification
        assert result.context_modification.count("<hook_context") == 2

    def test_runner_exception_recorded(self, tmp_path: Path) -> None:
        _write_py_hook(tmp_path, "TaskStart.py")

        class _BrokenRunner:
            def run(self, script, payload):  # type: ignore[no-untyped-def]
                raise RuntimeError("boom")

        registry = reg.HookRegistry([(tmp_path, "project")], runner=_BrokenRunner())
        result = registry.fire(HookKind.TASK_START, HookPayload(kind=HookKind.TASK_START))
        assert len(result.per_hook_results) == 1
        assert result.per_hook_results[0].parse_error
        assert result.error_count >= 1

    def test_stats_accumulates(self, tmp_path: Path) -> None:
        _write_py_hook(tmp_path, "TaskStart.py")
        outcomes = {
            (tmp_path / "TaskStart.py").resolve(): HookOutcome(cancel=True),
        }
        stub = _StubRunner(outcomes)
        registry = reg.HookRegistry([(tmp_path, "project")], runner=stub)
        registry.fire(HookKind.TASK_START, HookPayload(kind=HookKind.TASK_START))
        registry.fire(HookKind.TASK_START, HookPayload(kind=HookKind.TASK_START))
        stats = registry.stats()
        assert stats["fire_count"] == 2
        assert stats["cancel_count"] == 2

    def test_invalidate_discovery(self, tmp_path: Path) -> None:
        registry = reg.HookRegistry([(tmp_path, "project")])
        # Should not raise even with empty directory.
        registry.invalidate_discovery()


class TestSingleton:
    def test_get_returns_stable_instance(self, tmp_path: Path) -> None:
        reg.reset_hook_registry_for_testing()
        try:
            a = reg.get_hook_registry(workspace_root=tmp_path)
            b = reg.get_hook_registry()
            assert a is b
        finally:
            reg.reset_hook_registry_for_testing()

    def test_rebuild_replaces_singleton(self, tmp_path: Path) -> None:
        reg.reset_hook_registry_for_testing()
        try:
            a = reg.get_hook_registry(workspace_root=tmp_path)
            b = reg.get_hook_registry(workspace_root=tmp_path, rebuild=True)
            assert a is not b
        finally:
            reg.reset_hook_registry_for_testing()
