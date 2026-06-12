"""Tree-sitter-based syntax check for any supported language.

Pattern lifted in spirit (not in source) from aider's
``linter.py``'s ``basic_lint`` + ``traverse_tree`` (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``).

For any language with a vendored ``<lang>-tags.scm`` (see
:mod:`kenning.coding.queries`), parses the file with tree-sitter and
walks the AST for nodes where ``node.is_error`` is True or
``node.is_missing`` is True. Each such node yields a
:class:`LintError`. The walk is bounded by node count (anti-DOS:
malicious / pathological input shouldn't wedge the FILE_CHANGE
listener).

Public surface:

  * :class:`LintError` — frozen dataclass for one error
  * :class:`LintReport` — frozen dataclass aggregating errors per
    file. Convenience ``.ok``, ``.summary()``.
  * :func:`tree_sitter_lint` — run the check on one file path

Fail-open: unsupported languages, unreadable files, parser
construction failure all return a :class:`LintReport` with no errors
and a non-empty ``skipped_reason`` so callers can distinguish
"file is clean" from "we couldn't even check".
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence


warnings.simplefilter("ignore", category=FutureWarning)


logger = logging.getLogger("kenning.coding.tree_sitter_lint")


# Hard cap on AST node visits. Trees deeper than this stop the walk
# and the report is marked truncated. 50k is enough for files up to
# a few thousand lines of real code; anything beyond is either
# minified / generated or hostile.
MAX_NODE_VISITS = 50_000


@dataclass(frozen=True)
class LintError:
    """One lint error in a source file.

    Attributes:
        line: 0-based line where the error starts.
        column: 0-based column where the error starts.
        kind: ``"error"`` (an ``ERROR`` node) or ``"missing"`` (an
            ``is_missing`` node — tree-sitter recovered from a parse
            failure by inserting a placeholder).
        message: Human-readable description.
        source: Always ``"tree_sitter"`` from this module; downstream
            aggregators use this to distinguish from python_lint's
            ``"compile"`` / ``"flake8"`` sources.
    """

    line: int
    column: int
    kind: str
    message: str
    source: str = "tree_sitter"


@dataclass(frozen=True)
class LintReport:
    """Aggregated lint output for one file.

    Attributes:
        path: Absolute path to the linted file.
        language: Detected language name (``"python"``, ``"javascript"``,
            etc.) or empty when unknown.
        errors: List of :class:`LintError` records, ordered by
            ``(line, column)``.
        skipped_reason: Non-empty when no lint actually ran (missing
            parser, unreadable file). When set, ``errors`` is empty
            but that doesn't mean the file is clean.
        truncated: True when the walk hit :data:`MAX_NODE_VISITS`
            before finishing.
    """

    path: str
    language: str = ""
    errors: List[LintError] = field(default_factory=list)
    skipped_reason: str = ""
    truncated: bool = False

    @property
    def ok(self) -> bool:
        """True iff lint ran and found no errors."""
        return not self.errors and not self.skipped_reason

    def summary(self) -> str:
        """One-line text summary suitable for audit logs + narration."""
        if self.skipped_reason:
            return f"skipped: {self.skipped_reason}"
        if not self.errors:
            return "no errors"
        first = self.errors[0]
        rest = max(0, len(self.errors) - 1)
        head = (
            f"line {first.line + 1}:{first.column + 1} {first.kind}: "
            f"{first.message[:80]}"
        )
        if rest:
            head += f" (+{rest} more)"
        return head


def tree_sitter_lint(path: Path | str) -> LintReport:
    """Run a tree-sitter syntax check on one source file.

    Returns a :class:`LintReport`. Never raises; failure modes are
    encoded in ``skipped_reason``.
    """
    p = Path(path)
    try:
        abs_path = p.resolve()
    except OSError:
        abs_path = p
    path_str = str(abs_path)

    try:
        from grep_ast import filename_to_lang  # type: ignore[import-not-found]
        from grep_ast.tsl import get_language  # type: ignore[import-not-found]
        import tree_sitter  # type: ignore[import-not-found]
    except ImportError as exc:
        return LintReport(
            path=path_str,
            skipped_reason=f"grep_ast/tree_sitter not installed: {exc}",
        )

    lang = filename_to_lang(path_str)
    if not lang:
        return LintReport(
            path=path_str,
            skipped_reason=f"no tree-sitter language for {p.name}",
        )

    try:
        language = get_language(lang)
        parser = tree_sitter.Parser(language)
    except Exception as exc:                                    # noqa: BLE001
        return LintReport(
            path=path_str,
            language=lang,
            skipped_reason=f"parser construction failed: {exc}",
        )

    try:
        source_bytes = abs_path.read_bytes()
    except OSError as exc:
        return LintReport(
            path=path_str,
            language=lang,
            skipped_reason=f"read failed: {exc}",
        )

    if not source_bytes:
        return LintReport(path=path_str, language=lang)

    try:
        tree = parser.parse(source_bytes)
    except Exception as exc:                                    # noqa: BLE001
        return LintReport(
            path=path_str,
            language=lang,
            skipped_reason=f"parse failed: {exc}",
        )

    errors, truncated = _walk_for_errors(tree.root_node)
    errors.sort(key=lambda e: (e.line, e.column))
    return LintReport(
        path=path_str,
        language=lang,
        errors=errors,
        truncated=truncated,
    )


def _walk_for_errors(root_node) -> tuple[List[LintError], bool]:
    """Iterative DFS for ERROR / is_missing nodes. Bounded by visits."""
    stack: List[object] = [root_node]
    errors: List[LintError] = []
    visited = 0
    truncated = False
    while stack:
        if visited >= MAX_NODE_VISITS:
            truncated = True
            break
        node = stack.pop()
        visited += 1
        try:
            is_error = bool(getattr(node, "is_error", False)) or (
                getattr(node, "type", "") == "ERROR"
            )
            is_missing = bool(getattr(node, "is_missing", False))
        except Exception:                                       # noqa: BLE001
            continue
        if is_error or is_missing:
            try:
                start = node.start_point
                if is_missing:
                    kind = "missing"
                    msg = f"missing {getattr(node, 'type', '?')!s}"
                else:
                    kind = "error"
                    msg = f"syntax error in {getattr(node, 'type', '?')!s}"
            except Exception:                                   # noqa: BLE001
                continue
            row = start[0] if isinstance(start, (tuple, list)) else getattr(start, "row", 0)
            col = start[1] if isinstance(start, (tuple, list)) else getattr(start, "column", 0)
            errors.append(LintError(
                line=int(row),
                column=int(col),
                kind=kind,
                message=msg,
            ))
        # Stack children for further traversal. ``node.children`` is a
        # list-like attribute on standard tree-sitter Nodes.
        try:
            for child in node.children:
                stack.append(child)
        except Exception:                                       # noqa: BLE001
            continue
    return errors, truncated


__all__ = [
    "LintError",
    "LintReport",
    "MAX_NODE_VISITS",
    "tree_sitter_lint",
]
