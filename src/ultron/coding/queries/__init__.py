"""Vendored tree-sitter symbol queries.

The ``*-tags.scm`` files in this package are adapted from
``aider/queries/tree-sitter-language-pack/*-tags.scm`` (Apache License
2.0). Each file carries a header comment with attribution; the
top-level ``THIRD_PARTY_NOTICES.md`` records the full license terms.

Loaders should look up a query file via :func:`get_query_path`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


_THIS_DIR = Path(__file__).resolve().parent


def get_query_path(language: str) -> Optional[Path]:
    """Return the path to the ``<language>-tags.scm`` file or ``None``.

    Args:
        language: Tree-sitter language name (e.g. ``"python"``,
            ``"javascript"``). Lowercased before lookup.
    """
    if not language:
        return None
    candidate = _THIS_DIR / f"{language.lower()}-tags.scm"
    if candidate.is_file():
        return candidate
    return None
