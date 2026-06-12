"""Tree-sitter symbol extraction with pygments-as-ref fallback.

Pattern lifted in spirit from aider's ``repomap.get_tags_raw`` (Apache
2.0; see ``THIRD_PARTY_NOTICES.md``). This module is the structural
half of what aider's repo map needs to operate. The PageRank ranking
itself lives in :mod:`kenning.coding.repo_map` (batch 2).

Pipeline per source file:

  1. Detect language via :func:`grep_ast.filename_to_lang`. Skip if
     unknown.
  2. Load the language's tree-sitter parser + grammar via
     :func:`grep_ast.tsl.get_language` / ``get_parser`` (uses
     ``tree-sitter-language-pack`` bindings).
  3. Read the source bytes.
  4. Parse to an AST.
  5. Run the vendored ``<lang>-tags.scm`` query (see
     :mod:`kenning.coding.queries`).
  6. Walk captures: ``@name.definition.<kind>`` → ``Tag(kind="def")``,
     ``@name.reference.<kind>`` → ``Tag(kind="ref")``.
  7. If the query produced ``def`` captures but no ``ref`` captures
     (true for C/C++ tags-only queries), lex with ``pygments`` and
     emit ``Token.Name`` tokens as refs. Loose but useful.

Cache: optional :class:`~kenning.utils.mtime_cache.MtimeCache`. When
provided, parses are skipped if the file's mtime matches the cache
entry's mtime. The cache value is a list of ``Tag`` tuples; mtime
mismatch (file edited) forces a re-parse.

Failure modes are all fail-open:

  * Parser unavailable for a language → return ``[]``.
  * Query file missing → return ``[]``.
  * File unreadable → return ``[]``.
  * Tree-sitter parse error → return whatever tags came out before the
    error, plus an empty pygments fallback.

The :class:`Tag` namedtuple is intentionally shaped to match the
literature (aider, code-2024 retrieval papers) so downstream code that
reads catalogue patterns stays familiar.
"""

from __future__ import annotations

import logging
import os
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional

from kenning.coding.queries import get_query_path
from kenning.utils.mtime_cache import MtimeCache


logger = logging.getLogger("kenning.coding.tree_sitter_tags")


# tree_sitter has a FutureWarning at import time we don't care about.
warnings.simplefilter("ignore", category=FutureWarning)


class Tag(NamedTuple):
    """One symbol extracted from a source file.

    Attributes:
        rel_fname: Path relative to the supplied root, POSIX-form.
        fname: Absolute path on disk.
        line: 0-based line number where the symbol appears. ``-1``
            for pygments-fallback references (token has no line info).
        name: The identifier text.
        kind: ``"def"`` for definitions, ``"ref"`` for references.
    """

    rel_fname: str
    fname: str
    line: int
    name: str
    kind: str


def extract_tags(
    path: Path | str,
    root: Path | str,
    *,
    cache: Optional[MtimeCache] = None,
) -> List[Tag]:
    """Extract definitions + references from one source file.

    Args:
        path: Source file. Absolute or relative; the absolute form is
            stored on the returned tags. Symlinks are followed.
        root: Project root used to compute ``rel_fname``. POSIX form
            is used for stability across OSes (Windows paths get their
            backslashes flipped).
        cache: Optional mtime-keyed cache. When provided and the
            cached mtime matches the live file's mtime, the cached
            list is returned without re-parsing.

    Returns:
        List of :class:`Tag`. Empty when the file is unreadable, the
        language is unsupported, or no symbols matched the query.
    """
    abs_path = _abspath(path)
    abs_root = _abspath(root)
    rel_fname = _rel_posix(abs_path, abs_root)
    fname = str(abs_path)

    try:
        mtime = abs_path.stat().st_mtime
    except OSError as exc:
        logger.debug("tree_sitter_tags: stat failed for %s: %s", abs_path, exc)
        return []

    if cache is not None:
        cached = cache.get(fname, mtime)
        if cached is not None:
            return list(cached)

    tags = list(_extract_uncached(abs_path, rel_fname))
    if cache is not None:
        cache.set(fname, mtime, tags)
    return tags


def extract_tags_for_files(
    paths: Iterable[Path | str],
    root: Path | str,
    *,
    cache: Optional[MtimeCache] = None,
) -> List[Tag]:
    """Bulk-extract tags for many files.

    Each file is parsed independently — order of the returned list
    mirrors the input order. Single-file failures are logged at DEBUG
    and skipped.
    """
    abs_root = _abspath(root)
    out: List[Tag] = []
    for entry in paths:
        try:
            out.extend(extract_tags(entry, abs_root, cache=cache))
        except Exception as exc:  # pragma: no cover - defence-in-depth
            logger.warning(
                "tree_sitter_tags: extraction failed for %s: %s",
                entry,
                exc,
            )
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _abspath(path: Path | str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = p.resolve()
    return p


def _rel_posix(abs_path: Path, abs_root: Path) -> str:
    try:
        rel = abs_path.relative_to(abs_root)
    except ValueError:
        # File lives outside the root (different drive on Windows, etc.).
        rel = abs_path
    return str(rel).replace("\\", "/")


def _extract_uncached(abs_path: Path, rel_fname: str) -> Iterable[Tag]:
    try:
        from grep_ast import filename_to_lang  # type: ignore[import-not-found]
        from grep_ast.tsl import get_language  # type: ignore[import-not-found]
        import tree_sitter  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "tree_sitter_tags: grep_ast/tree_sitter not installed; "
            "tags extraction disabled"
        )
        return

    fname = str(abs_path)
    lang = filename_to_lang(fname)
    if not lang:
        return

    query_path = get_query_path(lang)
    if query_path is None:
        logger.debug(
            "tree_sitter_tags: no vendored query for language %r (file %s)",
            lang,
            fname,
        )
        return

    # ``grep_ast.tsl.get_language`` returns a ``tree_sitter.Language`` even
    # though ``tree-sitter-language-pack`` (its backend) ships its own
    # incompatible ``Parser`` / ``Node`` types via ``get_parser``. We
    # construct our own ``tree_sitter.Parser`` so the resulting tree
    # exposes the standard tree-sitter Python API (``tree.root_node``,
    # ``node.start_point``, ``node.text``, etc.).
    try:
        language = get_language(lang)
        parser = tree_sitter.Parser(language)
    except Exception as exc:
        logger.debug(
            "tree_sitter_tags: loader failed for %r: %s", lang, exc
        )
        return

    try:
        source_bytes = abs_path.read_bytes()
    except OSError as exc:
        logger.debug("tree_sitter_tags: read failed %s: %s", fname, exc)
        return
    if not source_bytes:
        return

    try:
        tree = parser.parse(source_bytes)
    except Exception as exc:
        logger.debug("tree_sitter_tags: parse failed %s: %s", fname, exc)
        return

    try:
        query_text = query_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - vendor files are bundled
        logger.warning(
            "tree_sitter_tags: query unreadable %s: %s", query_path, exc
        )
        return

    captures = _run_captures(language, query_text, tree.root_node)

    captures_by_tag: defaultdict = defaultdict(list)
    for tag_name, nodes in captures.items():
        for node in nodes:
            captures_by_tag[tag_name].append(node)

    saw_kinds: set[str] = set()
    for tag_name, nodes in captures_by_tag.items():
        if tag_name.startswith("name.definition."):
            kind = "def"
        elif tag_name.startswith("name.reference."):
            kind = "ref"
        else:
            continue
        saw_kinds.add(kind)
        for node in nodes:
            try:
                ident = node.text.decode("utf-8", errors="replace")
            except (AttributeError, ValueError):
                continue
            yield Tag(
                rel_fname=rel_fname,
                fname=fname,
                line=node.start_point[0],
                name=ident,
                kind=kind,
            )

    # If we saw defs but no refs (e.g., C/C++ tags-only queries),
    # backfill refs with pygments tokenization. The line number is
    # unknown for pygments tokens so we emit -1.
    if "def" in saw_kinds and "ref" not in saw_kinds:
        yield from _pygments_refs(abs_path, rel_fname, source_bytes)


def _run_captures(language, query_text: str, root_node):
    """Compatibility shim for tree-sitter Query/QueryCursor APIs.

    tree-sitter < 0.24 exposed ``Query.captures(node)``. 0.24+ moved it
    to a separate ``QueryCursor`` object. We try the new API first,
    fall back to the old one on AttributeError.
    """
    from tree_sitter import Query  # type: ignore[import-not-found]

    query = Query(language, query_text)
    try:
        from tree_sitter import QueryCursor  # type: ignore[import-not-found]

        cursor = QueryCursor(query)
        return cursor.captures(root_node)
    except ImportError:
        # Old API
        return query.captures(root_node)


def _pygments_refs(
    abs_path: Path, rel_fname: str, source_bytes: bytes
) -> Iterable[Tag]:
    try:
        from pygments.lexers import guess_lexer_for_filename
        from pygments.token import Name
    except ImportError:
        return
    try:
        source_text = source_bytes.decode("utf-8", errors="replace")
        lexer = guess_lexer_for_filename(str(abs_path), source_text)
    except Exception as exc:  # pygments raises a variety of errors here.
        logger.debug(
            "tree_sitter_tags: pygments lexer failed for %s: %s",
            abs_path,
            exc,
        )
        return
    try:
        tokens = lexer.get_tokens(source_text)
    except Exception as exc:
        logger.debug(
            "tree_sitter_tags: pygments tokenize failed for %s: %s",
            abs_path,
            exc,
        )
        return
    fname = str(abs_path)
    for ttype, text in tokens:
        if ttype in Name:
            yield Tag(
                rel_fname=rel_fname,
                fname=fname,
                line=-1,
                name=text,
                kind="ref",
            )


def supported_languages() -> List[str]:
    """List languages with vendored query files (sorted)."""
    queries_dir = Path(__file__).parent / "queries"
    out = []
    for p in queries_dir.glob("*-tags.scm"):
        out.append(p.stem.removesuffix("-tags"))
    return sorted(out)


__all__ = [
    "Tag",
    "extract_tags",
    "extract_tags_for_files",
    "supported_languages",
]
