"""AST-based structural metadata extraction (2026-05-19, Track 1f).

Extracts what a Python source file does at the structural level --
function definitions, function calls, imports, class definitions,
and a syntax-valid flag -- using the stdlib ``ast`` module. Pure
parsing, zero LLM cost, ~5-50 ms per file depending on size.

Two primary consumers:

1. **Coding-task pre-flight verification** (Track 1g). The
   ``CodingTaskRunner`` consumes ``FILE_CHANGE`` events from Claude
   Code and can now call :func:`extract_python_metadata` on each
   created / modified Python file. A syntax-invalid file means
   ground-truth-broken code; the runner emits an audit row and can
   feed that signal back into completion narration so we stop
   reporting "Done." on broken syntax.

2. **Code-context retrieval enrichment**. When a conversation turn
   contains a code block, the structural metadata can be attached
   to the Qdrant payload so a later "what did we change in
   capture.py" query retrieves on function-name match rather than
   raw text cosine similarity. This consumer isn't wired yet; the
   primitives are ready for it.

Scope: Python only for v1 -- the stdlib ``ast`` module is enough.
Tree-sitter for cross-language support (JS/TS/Java/Apex) is the
follow-up if/when those workflows become primary. Failing gracefully
on non-Python files keeps the door open: ``extract_python_metadata``
returns a ``syntax_valid=False`` result with a helpful error string
when the input isn't parseable Python.

No external deps; no I/O beyond optional ``read_text`` for the
file-path convenience helper. Safe to call from any context including
the FILE_CHANGE listener which runs on the runner's event-processing
thread.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set


@dataclass(frozen=True)
class AstMetadata:
    """Structural snapshot of a Python source unit.

    Frozen so the result is safe to pass through observation
    pipelines, cache, or include as a Qdrant payload field.

    Attributes:
        syntax_valid: True iff ``ast.parse`` succeeded. False means
            the rest of the fields may be empty / partial; the
            ``error`` field carries the SyntaxError message.
        error: SyntaxError message + offending line / column when
            parsing failed; empty string when ``syntax_valid``.
        functions_defined: Names of top-level + nested ``def`` /
            ``async def`` declarations. Order: source order. Method
            names inside a class are qualified ``ClassName.method``.
        functions_called: Distinct names referenced as call targets
            anywhere in the module body (sorted alphabetically). Only
            the leftmost name of attribute calls is captured
            (``foo.bar()`` -> ``foo``); intentional simplification
            to keep the call-graph signal coarse.
        classes_defined: Names of top-level + nested ``class``
            declarations in source order.
        imports: Module names imported (the ``from X`` part of
            ``from X import Y`` or the ``X`` part of ``import X``).
            Deduplicated + sorted for stable output.
        line_count: Total lines in the parsed source.
        has_main_guard: True iff a top-level ``if __name__ ==
            "__main__":`` block was found.
    """

    syntax_valid: bool
    error: str = ""
    functions_defined: List[str] = field(default_factory=list)
    functions_called: List[str] = field(default_factory=list)
    classes_defined: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    line_count: int = 0
    has_main_guard: bool = False


def _strip_bom(text: str) -> str:
    """Remove a leading UTF-8 BOM so ``ast.parse`` doesn't trip on it."""
    if text.startswith("﻿"):
        return text[1:]
    return text


class _Collector(ast.NodeVisitor):
    """Single-pass AST walker that fills :class:`AstMetadata` fields."""

    def __init__(self) -> None:
        self.functions_defined: List[str] = []
        self.functions_called: Set[str] = set()
        self.classes_defined: List[str] = []
        self.imports: Set[str] = set()
        self.has_main_guard: bool = False
        self._class_stack: List[str] = []

    # --- defs ----------------------------------------------------------

    def _qualified(self, name: str) -> str:
        if self._class_stack:
            return ".".join(self._class_stack + [name])
        return name

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions_defined.append(self._qualified(node.name))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.functions_defined.append(self._qualified(node.name))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes_defined.append(self._qualified(node.name))
        self._class_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self._class_stack.pop()

    # --- calls + imports ----------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        target = self._leftmost_name(node.func)
        if target:
            self.functions_called.add(target)
        self.generic_visit(node)

    @staticmethod
    def _leftmost_name(expr: ast.AST) -> Optional[str]:
        """``foo.bar.baz()`` -> ``foo``; ``foo()`` -> ``foo``; complex
        callable expressions (``(a or b)()``, subscripts, lambdas) ->
        None. We only capture the easy / high-signal cases."""
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            value = expr.value
            while isinstance(value, ast.Attribute):
                value = value.value
            if isinstance(value, ast.Name):
                return value.id
        return None

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            # ``import X.Y.Z`` -> capture the top-level ``X`` (the
            # name that would actually be bound in the namespace).
            self.imports.add(alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.imports.add(node.module.split(".")[0])
        # Relative imports (``from . import X``) contribute nothing
        # at the module-level granularity we track.
        self.generic_visit(node)

    # --- main guard ----------------------------------------------------

    def visit_If(self, node: ast.If) -> None:
        if _is_main_guard(node.test):
            self.has_main_guard = True
        self.generic_visit(node)


def _is_main_guard(test: ast.AST) -> bool:
    """Recognise ``__name__ == "__main__"`` (either order)."""
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return _is_dunder_name(left, "__name__") and _is_str_const(right, "__main__") \
        or _is_dunder_name(right, "__name__") and _is_str_const(left, "__main__")


def _is_dunder_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_str_const(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def extract_python_metadata(source: str) -> AstMetadata:
    """Parse a Python source string and return a :class:`AstMetadata`.

    On parse failure returns a result with ``syntax_valid=False`` and
    an ``error`` message; the other fields are empty. Never raises --
    callers can rely on returning a result for any input string.

    Performance: ~5-30 ms for source files in the 100-1000 line range.
    Pure CPU; safe to call on any thread.
    """
    if source is None:
        return AstMetadata(
            syntax_valid=False,
            error="extract_python_metadata received None",
        )

    cleaned = _strip_bom(source)
    line_count = cleaned.count("\n") + (0 if cleaned.endswith("\n") else 1)

    try:
        tree = ast.parse(cleaned)
    except SyntaxError as exc:
        # ast.parse's SyntaxError carries line + offset + msg; format
        # them into a single human-readable string so the audit log
        # row carries the same info Python itself would print.
        line = exc.lineno if exc.lineno is not None else "?"
        col = exc.offset if exc.offset is not None else "?"
        msg = exc.msg or "syntax error"
        return AstMetadata(
            syntax_valid=False,
            error=f"SyntaxError: {msg} (line {line}, column {col})",
            line_count=line_count,
        )
    except (ValueError, TypeError) as exc:
        # Non-syntactic parse failures (e.g. NUL byte in source).
        return AstMetadata(
            syntax_valid=False,
            error=f"{type(exc).__name__}: {exc}",
            line_count=line_count,
        )

    collector = _Collector()
    collector.visit(tree)

    return AstMetadata(
        syntax_valid=True,
        error="",
        functions_defined=collector.functions_defined,
        functions_called=sorted(collector.functions_called),
        classes_defined=collector.classes_defined,
        imports=sorted(collector.imports),
        line_count=line_count,
        has_main_guard=collector.has_main_guard,
    )


def extract_metadata_from_path(path: Path) -> AstMetadata:
    """Convenience: read ``path`` and parse it via
    :func:`extract_python_metadata`.

    Non-Python files are still attempted; the parser fails fast and
    returns ``syntax_valid=False`` with a helpful error. File-system
    errors (missing file, permission denied) propagate as
    ``syntax_valid=False`` with the OS error message rather than
    raising -- consistent with the "never raise" contract.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return AstMetadata(
            syntax_valid=False,
            error=f"file not found: {path}",
        )
    except (OSError, PermissionError) as exc:
        return AstMetadata(
            syntax_valid=False,
            error=f"{type(exc).__name__} reading {path}: {exc}",
        )
    return extract_python_metadata(source)


def is_python_file(path: Path) -> bool:
    """True iff ``path`` looks like a Python source file.

    Pure name-based heuristic -- doesn't read the file. ``.py`` and
    ``.pyi`` are accepted. Used as a cheap gate before calling the
    parser inside listeners that fire on every file write.
    """
    suffix = path.suffix.lower()
    return suffix in {".py", ".pyi"}


def is_syntax_valid(source: str) -> bool:
    """Fast yes/no syntax check without building the full metadata.

    Returns False on any parse error (SyntaxError or otherwise) and
    True on a clean parse. Use this when only the gate signal is
    needed -- skips the AST traversal that
    :func:`extract_python_metadata` performs.
    """
    if source is None:
        return False
    try:
        ast.parse(_strip_bom(source))
    except (SyntaxError, ValueError, TypeError):
        return False
    return True


__all__ = [
    "AstMetadata",
    "extract_python_metadata",
    "extract_metadata_from_path",
    "is_python_file",
    "is_syntax_valid",
]
