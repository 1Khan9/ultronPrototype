"""Phase 3: TemplateRenderer + the five Jinja2 prompt templates.

Coverage:
  * Each template renders cleanly with realistic context (5 scenarios).
  * Schema validation catches malformed templates (missing sections).
  * Token-budget validation rejects oversize renders.
  * StrictUndefined: missing required fields raise.
  * Project-root absolute-path check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.coding.templates import (
    PromptTooLargeError,
    SchemaValidationError,
    TemplateRenderer,
)


@pytest.fixture
def renderer() -> TemplateRenderer:
    return TemplateRenderer()


# ---------------------------------------------------------------------------
# Five representative project scenarios (the spec's "Integration test:
# render templates for 5 representative project scenarios, verify output").
# ---------------------------------------------------------------------------


def test_scenario_1_new_simple_python_cli(renderer):
    """User: 'Make me a CLI that prints today's weather.'"""
    result = renderer.render_initial_new(
        refined_goal="Build a Python CLI that prints today's weather forecast for a city.",
        user_intent="Make me a weather CLI",
        project_root=r"C:\STC\ultronPrototype\data\sandbox\weather_cli",
        stack={"language": "Python", "framework": "click"},
        test_framework="pytest",
    )
    text = result.text
    # Schema sections all present.
    for header in (
        "## Goal", "## In scope", "## Out of scope", "## Working directory",
        "## Required stack", "## Testing requirements",
        "## Reporting requirements", "## Clarification protocol",
        "## Code quality", "## Completion criteria",
    ):
        assert header in text, f"missing section {header!r}"
    # Stack reflected
    assert "Python" in text
    assert "click" in text
    assert "pytest" in text
    # Project root absolute
    assert r"C:\STC\ultronPrototype\data\sandbox\weather_cli" in text
    # MCP tool names appear (so Claude knows what to call)
    assert "mcp__kenning_coding__report_progress" in text
    assert "mcp__kenning_coding__request_clarification" in text
    assert "mcp__kenning_coding__declare_complete" in text
    # Within budget
    assert result.token_estimate <= renderer.token_budget


def test_scenario_2_new_flask_web_app(renderer):
    """User: 'Build a small Flask app for tracking todos.'"""
    result = renderer.render_initial_new(
        refined_goal="Build a Flask web app that exposes /todos endpoints (GET/POST/DELETE) backed by SQLite.",
        user_intent="Build me a Flask todo app",
        project_root=r"C:\sandbox\todos_app",
        stack={
            "language": "Python",
            "framework": "Flask",
            "dependencies": ["flask", "sqlalchemy"],
            "notes": "Use SQLAlchemy ORM for the SQLite tables.",
        },
        test_framework="pytest",
        user_preferences=["Type hints everywhere", "No bare except"],
    )
    text = result.text
    assert "Flask" in text
    assert "flask, sqlalchemy" in text
    assert "Use SQLAlchemy ORM" in text
    assert "Type hints everywhere" in text
    assert "No bare except" in text
    assert result.token_estimate <= renderer.token_budget


def test_scenario_3_edit_existing_typescript_project(renderer, tmp_path):
    """User: 'Add a /search endpoint to my inventory api.'"""
    file_tree = [
        {"path": "package.json", "size_bytes": 412},
        {"path": "tsconfig.json", "size_bytes": 230},
        {"path": "src/server.ts", "size_bytes": 850},
        {"path": "src/routes/items.ts", "size_bytes": 1240},
        {"path": "src/db.ts", "size_bytes": 612},
        {"path": "tests/items.test.ts", "size_bytes": 880},
    ]
    excerpts = {
        "src/server.ts": (
            "import express from 'express';\nconst app = express();\n"
            "app.get('/items', items.list);\napp.post('/items', items.create);"
        ),
    }
    result = renderer.render_initial_edit(
        refined_goal="Add a GET /search endpoint that filters items by name substring.",
        user_intent="Add search to my inventory api",
        project_root=str(tmp_path / "inventory_api"),
        file_tree=file_tree,
        language="TypeScript",
        framework="Express",
        key_file_excerpts=excerpts,
    )
    text = result.text
    for header in (
        "## Change requested", "## Working directory",
        "## Existing project context", "## Preservation requirements",
        "## Verification", "## Testing requirements", "## Completion criteria",
    ):
        assert header in text, f"missing {header!r}"
    assert "TypeScript" in text
    assert "Express" in text
    assert "package.json" in text
    assert "src/server.ts" in text
    assert "import express from 'express'" in text
    assert "GET /search" in text
    # Required preservation language
    assert "must continue to pass" in text or "still pass" in text


def test_scenario_4_correction_after_failed_tests(renderer):
    """Verifier flagged failures; coordinator generates a correction prompt."""
    failures = [
        {
            "check": "Test suite runs and passes",
            "detail": (
                "pytest reported 2 failures:\n"
                "  - test_auth.py::test_login_rejects_bad_password\n"
                "  - test_db.py::test_connection_pool_releases"
            ),
            "hint": "The login flow may be missing the bcrypt verification step.",
        },
        {
            "check": "Smoke test entry point",
            "detail": "Running `python -m my_app` produced ImportError: cannot import name 'config'.",
            "hint": "src/my_app/__main__.py imports config from a path that doesn't exist.",
        },
    ]
    result = renderer.render_correction(
        project_root=r"C:\sandbox\my_app",
        failures=failures,
        verification_failure_count=1,
    )
    text = result.text
    assert "# Verification failed" in text
    assert "## Working directory" in text
    assert "## What to do now" in text
    assert "test_auth.py::test_login_rejects_bad_password" in text
    assert "ImportError" in text
    assert "bcrypt" in text  # hint surfaces
    assert "2nd verification cycle" in text  # uses count


def test_scenario_5_mid_session_adjustment(renderer):
    """User mid-task: 'Have him use Postgres instead of SQLite.'"""
    result = renderer.render_adjustment(
        user_text="Have him use Postgres instead of SQLite.",
        current_stage="data layer",
        stages_summary="scaffolding done; data layer in progress",
        files_summary="created: db.py, models.py",
        pivot_immediately=True,
    )
    text = result.text
    assert "user adjustment" in text.lower()
    assert "Postgres instead of SQLite" in text
    assert "data layer" in text
    assert "Apply this adjustment immediately" in text


def test_scenario_5b_adjustment_with_coordinator_followup(renderer):
    """When the coordinator already rendered a precise prompt, the
    template uses it verbatim instead of building its own scaffold."""
    coord_followup = (
        "Switch from SQLite to Postgres now: replace the connection "
        "string in db.py with an env-var-driven Postgres URL, regenerate "
        "the schema migration, rerun tests. Keep the existing model code."
    )
    result = renderer.render_adjustment(
        user_text="Use Postgres",
        coordinator_followup=coord_followup,
    )
    # The verbatim coordinator text wins.
    assert coord_followup in result.text


# ---------------------------------------------------------------------------
# Clarification response (small, but verify both source variants)
# ---------------------------------------------------------------------------


def test_clarification_response_user_source(renderer):
    result = renderer.render_clarification_response(
        question="SQLite or Postgres?",
        answer="Use SQLite. Simpler for this scope.",
        source="user",
    )
    assert "SQLite or Postgres" in result.text
    assert "Use SQLite" in result.text
    assert "Continue from where you were" in result.text


def test_clarification_response_supervisor_source(renderer):
    result = renderer.render_clarification_response(
        question="What linter?",
        answer="Use ruff with default config.",
        source="supervisor",
    )
    assert "Use ruff with default config." in result.text
    # Supervisor source is minimal -- no "Continue" prologue.
    assert "Continue from where you were" not in result.text


def test_clarification_response_invalid_source_raises(renderer):
    with pytest.raises(ValueError):
        renderer.render_clarification_response(
            question="x", answer="y", source="not_a_source",
        )


# ---------------------------------------------------------------------------
# Schema validation: catch malformed templates
# ---------------------------------------------------------------------------


def test_schema_validation_catches_missing_section(renderer, tmp_path: Path):
    """Stub a broken template into a temp dir and verify the renderer flags it."""
    # Copy real templates over so dependencies render, then overwrite one
    # with a deliberately incomplete copy.
    src = renderer.template_dir
    dst = tmp_path / "prompts"
    dst.mkdir()
    for f in src.glob("*.j2"):
        (dst / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    # Strip the "## Goal" header from the new-project template.
    bad = dst / "claude_code_initial_new.j2"
    text = bad.read_text(encoding="utf-8").replace("## Goal", "## Aim")
    bad.write_text(text, encoding="utf-8")

    bad_renderer = TemplateRenderer(template_dir=dst)
    with pytest.raises(SchemaValidationError) as excinfo:
        bad_renderer.render_initial_new(
            refined_goal="x",
            user_intent="x",
            project_root=r"C:\sandbox\x",
        )
    assert "## Goal" in excinfo.value.missing


# ---------------------------------------------------------------------------
# Token-budget enforcement
# ---------------------------------------------------------------------------


def test_token_budget_rejects_oversize_render(renderer):
    """Render initial_new with a refined_goal so large the result blows
    the budget. The renderer must raise PromptTooLargeError."""
    huge_goal = ("scope detail line. " * 500) + ("more " * 5000)  # ~30 KB
    with pytest.raises(PromptTooLargeError) as excinfo:
        renderer.render_initial_new(
            refined_goal=huge_goal,
            user_intent="x",
            project_root=r"C:\sandbox\x",
        )
    assert excinfo.value.template_name == "claude_code_initial_new"
    assert excinfo.value.token_estimate > renderer.token_budget


def test_token_budget_can_be_lowered(tmp_path):
    """A custom-budget renderer trips on prompts the default would accept."""
    r = TemplateRenderer(token_budget=200)
    with pytest.raises(PromptTooLargeError):
        r.render_initial_new(
            refined_goal="x",
            user_intent="x",
            project_root=r"C:\sandbox\x",
        )


# ---------------------------------------------------------------------------
# Project-root absolute-path check
# ---------------------------------------------------------------------------


def test_relative_project_root_is_rejected(renderer):
    with pytest.raises(SchemaValidationError):
        renderer.render_initial_new(
            refined_goal="x",
            user_intent="x",
            project_root="relative/path",
        )


# ---------------------------------------------------------------------------
# StrictUndefined enforcement
# ---------------------------------------------------------------------------


def test_missing_required_context_raises(renderer):
    """Rendering by name without required fields should fail loudly."""
    import jinja2
    with pytest.raises(jinja2.UndefinedError):
        renderer.render(
            "claude_code_initial_new",
            {
                # Intentionally missing everything.
                "project_root": r"C:\x",
            },
        )


# ---------------------------------------------------------------------------
# Smoke: rendered prompts are reasonable size
# ---------------------------------------------------------------------------


def test_initial_new_default_render_under_2000_tokens(renderer):
    """Sanity guard: the bare-bones new-project render should fit
    comfortably below the default budget so user-supplied content has room."""
    result = renderer.render_initial_new(
        refined_goal="Tiny task.",
        user_intent="Tiny task.",
        project_root=r"C:\x",
    )
    assert result.token_estimate < 2000, (
        f"baseline render unexpectedly large: {result.token_estimate} tokens"
    )


def test_correction_under_1000_tokens_for_typical_failures(renderer):
    """A correction prompt for 2-3 failures should stay surgical."""
    failures = [
        {"check": "Test suite", "detail": "1 failure", "hint": "x"},
        {"check": "Smoke test", "detail": "imports cleanly", "hint": ""},
    ]
    result = renderer.render_correction(
        project_root=r"C:\x", failures=failures, verification_failure_count=0,
    )
    assert result.token_estimate < 1000
