"""Jinja2 template rendering for Claude Code prompts.

Five templates live in ``prompts/coding/``:

  * ``claude_code_initial_new``        -- new-project initial prompt
  * ``claude_code_initial_edit``       -- existing-project initial prompt
  * ``claude_code_correction``         -- post-verification-failure prompt
  * ``claude_code_adjustment``         -- mid-session user adjustment
  * ``claude_code_clarification_response`` -- minimal clarification wrapper

Every render goes through schema validation (required headers must
appear) and token-budget validation (rendered text must fit under
``settings.CODING_PROMPT_TOKEN_BUDGET``). Templates are loaded with
strict undefined behavior so a missing context field raises rather
than silently producing an empty section.

Public API:
  * :class:`TemplateRenderer` -- the loader + validator
  * :class:`PromptTooLargeError` -- raised when a render exceeds budget
  * :class:`SchemaValidationError` -- raised when required sections missing
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("coding.templates")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TemplateError(RuntimeError):
    """Base class."""


class PromptTooLargeError(TemplateError):
    """Rendered prompt exceeds the configured token budget."""

    def __init__(self, template_name: str, char_count: int, token_estimate: int, budget: int) -> None:
        super().__init__(
            f"Prompt {template_name!r} rendered to {char_count} chars "
            f"(~{token_estimate} tokens), over the {budget}-token budget."
        )
        self.template_name = template_name
        self.char_count = char_count
        self.token_estimate = token_estimate
        self.budget = budget


class SchemaValidationError(TemplateError):
    """A rendered prompt is missing one or more required sections."""

    def __init__(self, template_name: str, missing: List[str]) -> None:
        super().__init__(
            f"Prompt {template_name!r} is missing required sections: {missing}"
        )
        self.template_name = template_name
        self.missing = missing


# ---------------------------------------------------------------------------
# Schema: section markers each template must contain post-render
# ---------------------------------------------------------------------------


# Required substrings in the rendered output. Substring match is
# case-INSENSITIVE -- templates style headers as "# User adjustment"
# but we want schemas to be tolerant of header capitalization tweaks
# without rewriting the spec each time.
_SCHEMAS: Dict[str, List[str]] = {
    "claude_code_initial_new": [
        "## Goal",
        "## In scope",
        "## Out of scope",
        "## Working directory",
        "## Required stack",
        "## Testing requirements",
        "## Reporting requirements",
        "## Clarification protocol",
        "## Code quality",
        "## Completion criteria",
    ],
    "claude_code_initial_edit": [
        "## Change requested",
        "## Working directory",
        "## Existing project context",
        "## Preservation requirements",
        "## Verification",
        "## Testing requirements",
        "## Completion criteria",
    ],
    "claude_code_correction": [
        "Verification failed",  # may be H1 or inline text
        "Working directory",
        "What to do now",
    ],
    # The adjustment template has two legitimate render paths
    # (coordinator_followup verbatim vs the scaffold body). We can't
    # require a specific marker either way, so we only require the
    # rendered text to be non-empty -- the renderer's strip() + final
    # newline handles that automatically as long as content was
    # produced.
    "claude_code_adjustment": [],
    "claude_code_clarification_response": [],
}


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


@dataclass
class RenderResult:
    template_name: str
    text: str
    char_count: int
    token_estimate: int
    rendered_in_ms: float


class TemplateRenderer:
    """Loads + renders + validates the coding prompt templates.

    Args:
        template_dir: where the .j2 files live. Default uses
            :data:`settings.CODING_TEMPLATE_DIR`.
        token_budget: max approximate tokens after render.
        chars_per_token: heuristic ratio for token estimation. The model's
            actual tokenizer would be more precise but loading it would
            pull the LLM at template-render time, which we don't want.
            4 chars/token is conservative for English code prose.
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        *,
        token_budget: int = settings.CODING_PROMPT_TOKEN_BUDGET,
        chars_per_token: int = settings.CODING_PROMPT_CHARS_PER_TOKEN,
    ) -> None:
        import jinja2

        self.template_dir = Path(template_dir or settings.CODING_TEMPLATE_DIR)
        if not self.template_dir.is_dir():
            raise FileNotFoundError(
                f"Template directory not found: {self.template_dir}"
            )
        self.token_budget = token_budget
        self.chars_per_token = max(1, chars_per_token)
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            undefined=jinja2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
            autoescape=False,
        )

    # --- public API ---------------------------------------------------------

    def render(self, template_name: str, context: Dict[str, Any]) -> RenderResult:
        """Render and validate a template by name (without ``.j2``).

        Raises:
            jinja2.UndefinedError: missing required context field.
            SchemaValidationError: required section headers missing.
            PromptTooLargeError: rendered output exceeds the token budget.
        """
        t0 = time.monotonic()
        template = self._env.get_template(f"{template_name}.j2")
        text = template.render(**context).strip() + "\n"
        elapsed_ms = (time.monotonic() - t0) * 1000

        self._validate(template_name, text, context)

        return RenderResult(
            template_name=template_name,
            text=text,
            char_count=len(text),
            token_estimate=self.estimate_tokens(text),
            rendered_in_ms=elapsed_ms,
        )

    def render_initial_new(
        self,
        *,
        refined_goal: str,
        user_intent: str,
        project_root: Path,
        stack: Optional[Dict[str, Any]] = None,
        test_framework: Optional[str] = None,
        user_preferences: Optional[List[str]] = None,
    ) -> RenderResult:
        normalized_stack = {
            "language": "Python",
            "framework": None,
            "dependencies": [],
            "notes": None,
            **(stack or {}),
        }
        return self.render(
            "claude_code_initial_new",
            {
                "refined_goal": refined_goal,
                "user_intent": user_intent,
                "project_root": str(project_root),
                "stack": normalized_stack,
                "test_framework": test_framework,
                "user_preferences": list(user_preferences or []),
            },
        )

    def render_initial_edit(
        self,
        *,
        refined_goal: str,
        user_intent: str,
        project_root: Path,
        file_tree: List[Dict[str, Any]],
        language: Optional[str] = None,
        framework: Optional[str] = None,
        key_file_excerpts: Optional[Dict[str, str]] = None,
        user_preferences: Optional[List[str]] = None,
    ) -> RenderResult:
        return self.render(
            "claude_code_initial_edit",
            {
                "refined_goal": refined_goal,
                "user_intent": user_intent,
                "project_root": str(project_root),
                "file_tree": list(file_tree or []),
                "language": language,
                "framework": framework,
                "key_file_excerpts": dict(key_file_excerpts or {}),
                "user_preferences": list(user_preferences or []),
            },
        )

    def render_correction(
        self,
        *,
        project_root: Path,
        failures: List[Dict[str, str]],
        verification_failure_count: int = 0,
    ) -> RenderResult:
        if not failures:
            raise ValueError("render_correction: failures must be non-empty")
        return self.render(
            "claude_code_correction",
            {
                "project_root": str(project_root),
                "failures": failures,
                "verification_failure_count": verification_failure_count,
            },
        )

    def render_adjustment(
        self,
        *,
        user_text: str,
        current_stage: Optional[str] = None,
        stages_summary: str = "(nothing yet)",
        files_summary: str = "(none)",
        pivot_immediately: bool = True,
        coordinator_followup: Optional[str] = None,
    ) -> RenderResult:
        return self.render(
            "claude_code_adjustment",
            {
                "user_text": user_text,
                "current_stage": current_stage,
                "stages_summary": stages_summary,
                "files_summary": files_summary,
                "pivot_immediately": pivot_immediately,
                "coordinator_followup": coordinator_followup,
            },
        )

    def render_clarification_response(
        self,
        *,
        question: str,
        answer: str,
        source: str = "supervisor",
    ) -> RenderResult:
        if source not in ("user", "supervisor"):
            raise ValueError(f"invalid clarification source: {source!r}")
        return self.render(
            "claude_code_clarification_response",
            {
                "question": question or "",
                "answer": answer,
                "source": source,
            },
        )

    # --- internals ----------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """Conservative token-count estimate using a chars-per-token ratio.

        Uses 4 chars/token by default which over-estimates slightly for
        Latin-script code/prose -- safe direction for a budget cap.
        """
        if not text:
            return 0
        return max(1, len(text) // self.chars_per_token + 1)

    def _validate(self, template_name: str, text: str, context: Dict[str, Any]) -> None:
        # Schema: required section headers present.
        missing = self._missing_sections(template_name, text)
        if missing:
            raise SchemaValidationError(template_name, missing)
        # Token budget.
        token_estimate = self.estimate_tokens(text)
        if token_estimate > self.token_budget:
            raise PromptTooLargeError(
                template_name, len(text), token_estimate, self.token_budget,
            )
        # Project-root absoluteness check (best-effort).
        project_root = context.get("project_root")
        if project_root and not Path(project_root).is_absolute():
            raise SchemaValidationError(
                template_name,
                [f"project_root must be absolute, got {project_root!r}"],
            )

    def _missing_sections(self, template_name: str, text: str) -> List[str]:
        required = _SCHEMAS.get(template_name)
        if not required:
            # Empty schema -> only require the rendered text to have
            # something substantive in it (avoid silently accepting an
            # empty render).
            if not text.strip():
                return ["non-empty rendered output"]
            return []
        haystack = text.lower()
        return [s for s in required if s.lower() not in haystack]
