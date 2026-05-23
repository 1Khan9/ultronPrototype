"""Fuzz cascade for SEARCH/REPLACE-style edits.

Pattern lifted in spirit (not in source) from aider's
``coders/search_replace.py`` + ``editblock_coder.py``
``replace_most_similar_chunk`` (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``).

LLMs are imperfect at reproducing source text byte-for-byte. A
SEARCH block that "looks right" to a human is often off by whitespace,
trailing newlines, or condensed sections marked with ``...``. This
module turns "search text doesn't match exactly" from a hard fail
into a graceful retry through a series of increasingly forgiving
strategies:

  1. **Perfect match** — exact substring with count == 1.
  2. **Skip leading blank line** — LLMs often add one extra blank
     line before the search block.
  3. **Whitespace-tolerant** — detect a uniform indentation offset
     between the search block and a candidate location in the file;
     apply the SAME offset to the replacement.
  4. **Dots elision** — when the search uses ``...`` placeholders to
     mark unchanged middles, split into chunks and apply each
     independently.
  5. **Relative-indent wrap** — convert search + replace + original to
     relative-indent form (via :class:`RelativeIndenter` from batch 1),
     re-run strategies 1-4, then convert the result back.

Each strategy is tried in order; the first one to match wins. The
result is a :class:`EditResult` with the modified text + telemetry
(which strategy succeeded, on what line, how many edits applied).

When every strategy fails, :func:`find_similar_lines` returns the
closest matching block from the file (±5 lines of context) so the
caller can feed it back to the LLM for self-correction. This is the
exact catalog T2 "find_similar_lines" pattern.

Public surface:

  * :class:`Strategy` — enum of strategy names.
  * :class:`EditResult` — outcome dataclass.
  * :func:`apply_edit` — single search/replace via the cascade.
  * :func:`apply_edit_to_files` — try each candidate file when the
    primary lookup fails (the "LLM named the wrong file" fallback).
  * :func:`find_similar_lines` — best-effort similar-block lookup.

Fail-open: every helper either returns a result or returns an empty
result with a reason. None raise.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple


logger = logging.getLogger("ultron.coding.edit_matcher")


# Catalog parameter — how many context lines to show on either side
# of the best-similar match when reporting back to the LLM.
DEFAULT_SIMILAR_CONTEXT_LINES = 5


# Catalog parameter — minimum similarity ratio for find_similar_lines
# to return a match. SequenceMatcher ratios below this are too noisy
# to be useful self-correction hints.
DEFAULT_SIMILARITY_THRESHOLD = 0.6


# Placeholder regex used by the dots-elision strategy. Matches lines
# that contain ONLY ``...`` (with optional surrounding whitespace).
_DOTS_ONLY_LINE = re.compile(r"^\s*\.\.\.\s*$")


class Strategy(str, Enum):
    """The cascade of strategies, in order of preference."""

    PERFECT = "perfect"
    SKIP_LEADING_BLANK = "skip_leading_blank"
    WHITESPACE_TOLERANT = "whitespace_tolerant"
    DOTS_ELISION = "dots_elision"
    RELATIVE_INDENT = "relative_indent"


@dataclass(frozen=True)
class EditResult:
    """Outcome of one :func:`apply_edit` call.

    Attributes:
        new_text: The original text with the edit applied. Empty
            string ``""`` when ``success`` is False; callers should
            check ``success`` rather than rely on the empty-string
            sentinel since legitimate edits can produce empty text
            (e.g., a search-and-replace that deletes the whole file).
        success: True iff some strategy in the cascade matched.
        strategy: Which strategy produced the result. ``""`` when
            ``success`` is False.
        attempts: Number of cascade attempts run before the result
            (1 = perfect-match on first try; 5 = relative-indent
            fallback succeeded).
        error: Short description when ``success`` is False.
    """

    new_text: str
    success: bool
    strategy: str = ""
    attempts: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------


def apply_edit(
    original: str,
    search: str,
    replace: str,
    *,
    strategies: Optional[Sequence[Strategy]] = None,
) -> EditResult:
    """Run the strategy cascade on a single search/replace pair.

    Args:
        original: The current file contents.
        search: The text to find. May contain ``...`` placeholders
            for elided middles (handled by the dots-elision strategy).
        replace: The replacement text.
        strategies: Override the strategy order. Defaults to the full
            cascade. Useful for tests + for callers that want to
            disable specific tiers (e.g., skip RELATIVE_INDENT to
            avoid the wrapping cost).

    Returns:
        :class:`EditResult` with ``success=True`` on first match.
    """
    if not original:
        return EditResult(
            new_text="",
            success=False,
            error="empty original",
        )
    if not search:
        return EditResult(
            new_text=original,
            success=False,
            error="empty search",
        )

    strats = list(strategies) if strategies else list(Strategy)
    attempts = 0
    for strat in strats:
        attempts += 1
        if strat == Strategy.PERFECT:
            result = _try_perfect(original, search, replace)
        elif strat == Strategy.SKIP_LEADING_BLANK:
            result = _try_skip_leading_blank(original, search, replace)
        elif strat == Strategy.WHITESPACE_TOLERANT:
            result = _try_whitespace_tolerant(original, search, replace)
        elif strat == Strategy.DOTS_ELISION:
            result = _try_dots_elision(original, search, replace)
        elif strat == Strategy.RELATIVE_INDENT:
            # The relative-indent wrap tries strategies 1-4 inside the
            # relative-indent space, so we skip it when running under
            # a restricted strategy list to avoid recursion confusion.
            inner_strats = [
                s for s in strats if s != Strategy.RELATIVE_INDENT
            ]
            result = _try_relative_indent(
                original, search, replace, inner_strats,
            )
        else:                                                     # pragma: no cover
            continue
        if result is not None:
            return EditResult(
                new_text=result,
                success=True,
                strategy=strat.value,
                attempts=attempts,
            )

    return EditResult(
        new_text="",
        success=False,
        attempts=attempts,
        error="no strategy matched",
    )


def apply_edit_to_files(
    files: Iterable[Tuple[str, str]],
    search: str,
    replace: str,
    *,
    primary_filename: Optional[str] = None,
    strategies: Optional[Sequence[Strategy]] = None,
) -> Tuple[Optional[str], EditResult]:
    """Try ``apply_edit`` against each file in ``files``; first match wins.

    Implements the catalog's "LLM named the wrong file" fallback:
    when the SEARCH block doesn't match the named file, try every
    file the LLM has visibility into. The first file whose contents
    yield a successful edit is the answer.

    Args:
        files: Iterable of ``(filename, content)`` pairs. The primary
            file (named by the LLM) is tried FIRST when
            ``primary_filename`` is supplied; otherwise iteration
            order is preserved.
        search: SEARCH text.
        replace: REPLACE text.
        primary_filename: Optional filename to try first.
        strategies: Forwarded to :func:`apply_edit`.

    Returns:
        ``(matched_filename, EditResult)``. ``matched_filename`` is
        None when no file produced a successful edit.
    """
    pairs = list(files)
    if primary_filename:
        primary = [(n, c) for n, c in pairs if n == primary_filename]
        rest = [(n, c) for n, c in pairs if n != primary_filename]
        pairs = primary + rest

    last_attempt = EditResult(
        new_text="",
        success=False,
        error="no files supplied",
    )
    for name, content in pairs:
        result = apply_edit(content, search, replace, strategies=strategies)
        if result.success:
            return name, result
        last_attempt = result

    return None, EditResult(
        new_text="",
        success=False,
        attempts=last_attempt.attempts,
        error=f"no file matched (last attempt: {last_attempt.error})",
    )


# ---------------------------------------------------------------------------
# Per-strategy implementations
# ---------------------------------------------------------------------------


def _try_perfect(original: str, search: str, replace: str) -> Optional[str]:
    """Strategy 1: exact substring with count == 1.

    Returns None when ``search`` doesn't appear OR appears more than
    once (ambiguous: we don't know which occurrence to replace).
    """
    count = original.count(search)
    if count != 1:
        return None
    return original.replace(search, replace, 1)


def _try_skip_leading_blank(
    original: str, search: str, replace: str,
) -> Optional[str]:
    """Strategy 2: strip one leading blank line from the search.

    LLMs sometimes prepend an extra blank line to the SEARCH block.
    Stripping the search's leading blank line and re-trying perfect
    match catches that case.
    """
    if not search.startswith("\n"):
        return None
    return _try_perfect(original, search.lstrip("\n"), replace.lstrip("\n"))


def _try_whitespace_tolerant(
    original: str, search: str, replace: str,
) -> Optional[str]:
    """Strategy 3: detect uniform indent offset; apply to replacement.

    When the LLM's SEARCH is indented one level less (or more) than
    the actual file location, look for a line in the original whose
    content matches the first non-blank search line at a different
    indent. If a candidate location is found and the offset is
    UNIFORM across all non-blank search lines, apply the same offset
    to the replacement.
    """
    search_lines = search.splitlines(keepends=True)
    if not search_lines:
        return None

    # Find the first non-blank search line; its indent is our anchor.
    anchor_idx = next(
        (i for i, line in enumerate(search_lines) if line.strip()),
        -1,
    )
    if anchor_idx < 0:
        return None
    anchor_line = search_lines[anchor_idx]
    anchor_indent_len = len(anchor_line) - len(anchor_line.lstrip())
    anchor_content = anchor_line.lstrip()

    original_lines = original.splitlines(keepends=True)

    # Track every valid match. Whitespace-tolerant should be as
    # conservative as perfect-match: exactly ONE matching window or
    # we refuse — multiple matches are ambiguous and the LLM probably
    # had a specific location in mind.
    matches: List[Tuple[int, int]] = []  # (start, offset)
    for start in range(len(original_lines) - len(search_lines) + 1):
        original_anchor = original_lines[start + anchor_idx]
        if not original_anchor.lstrip().startswith(anchor_content.rstrip("\n")):
            continue
        original_indent_len = len(original_anchor) - len(original_anchor.lstrip())
        offset = original_indent_len - anchor_indent_len

        # Validate that EVERY non-blank search line is at the offset
        # in the original. If not, this is a false match.
        ok = True
        for i, s_line in enumerate(search_lines):
            o_line = original_lines[start + i]
            if not s_line.strip() and not o_line.strip():
                continue
            s_indent = len(s_line) - len(s_line.lstrip())
            o_indent = len(o_line) - len(o_line.lstrip())
            if (o_indent - s_indent) != offset:
                ok = False
                break
            if o_line.lstrip() != s_line.lstrip():
                ok = False
                break
        if ok:
            matches.append((start, offset))

    if len(matches) != 1:
        return None
    start, offset = matches[0]

    # Apply the same offset to the replacement.
    replace_lines = replace.splitlines(keepends=True)
    adjusted_replace: List[str] = []
    for r_line in replace_lines:
        if not r_line.strip():
            adjusted_replace.append(r_line)
            continue
        if offset > 0:
            adjusted_replace.append(" " * offset + r_line)
        elif offset < 0:
            indent = len(r_line) - len(r_line.lstrip())
            strip_n = min(-offset, indent)
            adjusted_replace.append(r_line[strip_n:])
        else:
            adjusted_replace.append(r_line)

    replaced = (
        original_lines[:start]
        + adjusted_replace
        + original_lines[start + len(search_lines):]
    )
    return "".join(replaced)


def _try_dots_elision(
    original: str, search: str, replace: str,
) -> Optional[str]:
    """Strategy 4: handle ``...`` placeholders in SEARCH + REPLACE.

    When SEARCH contains lines that are just ``...``, split SEARCH
    and REPLACE on those lines, then verify each chunk pair has the
    same number of ``...`` separators. Apply each chunk independently
    via :func:`_try_perfect`. If any chunk fails, the whole strategy
    fails.

    This is the catalog's ``try_dotdotdots`` pattern.
    """
    search_lines = search.splitlines(keepends=True)
    has_dots = any(_DOTS_ONLY_LINE.match(line) for line in search_lines)
    if not has_dots:
        return None

    search_chunks = _split_on_dots(search)
    replace_chunks = _split_on_dots(replace)
    if len(search_chunks) != len(replace_chunks):
        return None
    if not search_chunks:
        return None

    current = original
    for s, r in zip(search_chunks, replace_chunks):
        if not s.strip():
            # An empty chunk pair (LLM emitted leading or trailing ...)
            # — skip; nothing to replace.
            continue
        applied = _try_perfect(current, s, r)
        if applied is None:
            return None
        current = applied
    return current


def _try_relative_indent(
    original: str,
    search: str,
    replace: str,
    inner_strats: Sequence[Strategy],
) -> Optional[str]:
    """Strategy 5: convert to relative-indent space and re-run.

    Uses :class:`ultron.utils.relative_indent.RelativeIndenter`. After
    the relative-indent transform, two blocks that differ only in
    overall indentation produce IDENTICAL text — so the inner
    strategies have a much better chance to match.

    Falls back silently when the relative-indent transform fails
    (e.g., the marker collides with all candidate codepoints; the
    indenter raises in that pathological case).
    """
    try:
        from ultron.utils.relative_indent import RelativeIndenter
    except ImportError:
        return None
    try:
        indenter = RelativeIndenter([original, search, replace])
        rel_original = indenter.make_relative(original)
        rel_search = indenter.make_relative(search)
        rel_replace = indenter.make_relative(replace)
    except (ValueError, Exception) as exc:                        # noqa: BLE001
        logger.debug("edit_matcher: RelativeIndenter prep failed: %s", exc)
        return None

    rel_result = apply_edit(
        rel_original,
        rel_search,
        rel_replace,
        strategies=inner_strats,
    )
    if not rel_result.success:
        return None
    try:
        return indenter.make_absolute(rel_result.new_text)
    except (ValueError, Exception) as exc:                        # noqa: BLE001
        logger.debug("edit_matcher: make_absolute failed: %s", exc)
        return None


def _split_on_dots(text: str) -> List[str]:
    """Split ``text`` on lines that are just ``...``."""
    chunks: List[str] = []
    current: List[str] = []
    for line in text.splitlines(keepends=True):
        if _DOTS_ONLY_LINE.match(line):
            chunks.append("".join(current))
            current = []
        else:
            current.append(line)
    chunks.append("".join(current))
    return chunks


# ---------------------------------------------------------------------------
# Similar-lines for LLM self-correction
# ---------------------------------------------------------------------------


def find_similar_lines(
    search: str,
    original: str,
    *,
    context_lines: int = DEFAULT_SIMILAR_CONTEXT_LINES,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> str:
    """Find the closest matching block in ``original`` for ``search``.

    Walks every same-length window of ``original`` and computes a
    ``difflib.SequenceMatcher`` ratio. Returns the best match with
    ``context_lines`` lines of leading + trailing context, formatted
    for inclusion in an LLM error-feedback prompt. Returns an empty
    string when the best ratio is below ``threshold``.

    This is the catalog T2 ``find_similar_lines`` pattern — when an
    edit fails, feed the LLM "here's the closest thing I could find
    in the file" so it can self-correct.
    """
    if not search or not original:
        return ""
    search_lines = search.splitlines()
    original_lines = original.splitlines()
    if not search_lines or len(search_lines) > len(original_lines):
        return ""

    # Character-level SequenceMatcher gives much smoother ratios than
    # line-level (a line-list comparison treats each line as one
    # opaque element; "return 99" vs "return 42" register as completely
    # different even though only 2 chars differ). For self-correction
    # feedback, character similarity is what we want.
    best_ratio = 0.0
    best_start = -1
    for start in range(len(original_lines) - len(search_lines) + 1):
        window_text = "\n".join(original_lines[start: start + len(search_lines)])
        ratio = difflib.SequenceMatcher(
            a=search.rstrip("\n"),
            b=window_text,
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = start
        if ratio == 1.0:
            break

    if best_ratio < threshold or best_start < 0:
        return ""

    lo = max(0, best_start - context_lines)
    hi = min(
        len(original_lines),
        best_start + len(search_lines) + context_lines,
    )
    snippet_lines: List[str] = []
    for i in range(lo, hi):
        marker = ">" if best_start <= i < best_start + len(search_lines) else " "
        snippet_lines.append(f"{marker} {original_lines[i]}")
    header = (
        f"Closest match (similarity {best_ratio:.2f}) "
        f"at lines {best_start + 1}-{best_start + len(search_lines)}:"
    )
    return header + "\n" + "\n".join(snippet_lines)


__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_SIMILAR_CONTEXT_LINES",
    "EditResult",
    "Strategy",
    "apply_edit",
    "apply_edit_to_files",
    "find_similar_lines",
]
