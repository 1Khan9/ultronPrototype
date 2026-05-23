"""Tests for the catalog batch 7 wiring of repo_map_text + architect_plan_text
into :class:`SupervisorDispatchController` 's prompt body."""

from __future__ import annotations

from pathlib import Path

import pytest

from ultron.coding.project_supervisor import (
    SupervisorAction,
    SupervisorDecision,
    SupervisorInputs,
)
from ultron.coding.supervisor_dispatch import SupervisorDispatchController


def _make_controller(*, enriched=False, sandbox_root=None):
    """Build a controller with no-op speak callbacks."""
    return SupervisorDispatchController(
        supervisor=None,  # type: ignore[arg-type]
        index=None,
        barge_in_speak=lambda *_a, **_k: False,
        plain_speak=lambda *_a, **_k: None,
        narrate_enabled=False,
        enriched_context_enabled=enriched,
        sandbox_root=sandbox_root,
    )


def _make_inputs(text: str = "add login validation") -> SupervisorInputs:
    return SupervisorInputs(user_text=text)


def _make_edit_decision(
    *,
    path: Path,
    repo_map: str = "",
    architect_plan: str = "",
) -> SupervisorDecision:
    return SupervisorDecision(
        action=SupervisorAction.EDIT,
        target_project_name="demo",
        target_project_path=str(path),
        user_text="add login validation",
        repo_map_text=repo_map or None,
        architect_plan_text=architect_plan or None,
    )


# ---------------------------------------------------------------------------
# EDIT prompt body
# ---------------------------------------------------------------------------


def test_edit_prompt_includes_architect_plan_when_present(tmp_path: Path):
    controller = _make_controller(enriched=False)
    decision = _make_edit_decision(
        path=tmp_path,
        architect_plan="Step 1: modify auth.py. Step 2: add tests.",
    )
    prompt = controller._build_edit_prompt(decision, _make_inputs(), tmp_path)
    assert "Architect plan" in prompt
    assert "Step 1: modify auth.py" in prompt


def test_edit_prompt_includes_repo_map_when_present(tmp_path: Path):
    controller = _make_controller(enriched=False)
    decision = _make_edit_decision(
        path=tmp_path,
        repo_map="auth.py:\n  class Login:\n    def validate(...):",
    )
    prompt = controller._build_edit_prompt(decision, _make_inputs(), tmp_path)
    assert "Repo map" in prompt
    assert "class Login" in prompt


def test_edit_prompt_includes_both_when_both_present(tmp_path: Path):
    controller = _make_controller(enriched=False)
    decision = _make_edit_decision(
        path=tmp_path,
        repo_map="map content",
        architect_plan="plan content",
    )
    prompt = controller._build_edit_prompt(decision, _make_inputs(), tmp_path)
    assert "Architect plan" in prompt
    assert "Repo map" in prompt
    # Architect plan appears BEFORE repo map (plan is the spec, map is
    # the orientation).
    assert prompt.find("Architect plan") < prompt.find("Repo map")


def test_edit_prompt_omits_sections_when_absent(tmp_path: Path):
    controller = _make_controller(enriched=False)
    decision = _make_edit_decision(path=tmp_path)
    prompt = controller._build_edit_prompt(decision, _make_inputs(), tmp_path)
    assert "Architect plan" not in prompt
    assert "Repo map" not in prompt


def test_edit_prompt_includes_user_request_first(tmp_path: Path):
    """The user's verbatim request stays at the top of the prompt
    even when architect plan + repo map are present."""
    controller = _make_controller(enriched=False)
    decision = _make_edit_decision(
        path=tmp_path,
        repo_map="map",
        architect_plan="plan",
    )
    prompt = controller._build_edit_prompt(decision, _make_inputs(), tmp_path)
    assert prompt.startswith("User request:")
    assert prompt.find("User request:") < prompt.find("Architect plan")


def test_edit_prompt_enriched_context_still_works(tmp_path: Path):
    """The architect/repo-map sections are independent of enriched_context."""
    # Make a fake project with one file so the snapshot has content.
    (tmp_path / "x.py").write_text("def foo(): pass\n")
    controller = _make_controller(enriched=True)
    decision = _make_edit_decision(
        path=tmp_path,
        architect_plan="add bar()",
    )
    prompt = controller._build_edit_prompt(decision, _make_inputs(), tmp_path)
    # Architect plan is still emitted alongside enriched sections.
    assert "Architect plan" in prompt
    # And enriched sections still appear (Project layout from snapshot).
    assert "Project layout" in prompt


# ---------------------------------------------------------------------------
# NEW dispatch
# ---------------------------------------------------------------------------


def test_new_dispatch_prompt_includes_plan_and_map(tmp_path: Path):
    controller = _make_controller(sandbox_root=tmp_path)
    decision = SupervisorDecision(
        action=SupervisorAction.NEW,
        target_project_path=None,
        user_text="scaffold a TODO app",
        repo_map_text="(empty)",  # NEW scaffolds rarely have a map but support it
        architect_plan_text="Scaffold with Flask + SQLite.",
    )
    inputs = SupervisorInputs(user_text="scaffold a TODO app")
    task_request = controller._build_new_task_request(decision, inputs)
    assert task_request is not None
    body = task_request.task_prompt
    assert "Architect plan" in body
    assert "Scaffold with Flask + SQLite." in body
    assert "Repo map" in body
    assert "User request:" in body
    assert "scaffold a TODO app" in body


def test_new_dispatch_prompt_without_supervisor_extras(tmp_path: Path):
    """NEW dispatch with no plan/map falls back to user_text-only prompt."""
    controller = _make_controller(sandbox_root=tmp_path)
    decision = SupervisorDecision(
        action=SupervisorAction.NEW,
        user_text="build a hello world",
    )
    inputs = SupervisorInputs(user_text="build a hello world")
    task_request = controller._build_new_task_request(decision, inputs)
    assert task_request is not None
    assert "Architect plan" not in task_request.task_prompt
    assert "Repo map" not in task_request.task_prompt
    assert "User request:" in task_request.task_prompt
    assert "build a hello world" in task_request.task_prompt
