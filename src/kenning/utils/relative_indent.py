"""Relative-indent text transform.

Pattern lifted in spirit from aider's ``coders/search_replace.py``
``RelativeIndenter`` (Apache 2.0; see ``THIRD_PARTY_NOTICES.md``).

Why this exists: two code fragments that share identical structure
but differ in their absolute indentation level (e.g. a method body
extracted at top level vs. a method body at class scope) produce
*different bytes* under naive comparison. After the relative-indent
transform, only the leading indent of the *first* line still varies —
every subsequent line is encoded as its delta from the line above.
That collapses the absolute-vs-relative difference, making
whitespace-tolerant pattern matching trivial.

Round-trip property: for any text ``T``::

    T == make_absolute(make_relative(T))

The encoding interleaves "dent-indicator" lines with "content" lines:

  * A *positive* indent change (this line is more indented than the
    previous) is encoded as a dent-indicator line containing only the
    extra leading whitespace (so the absolute indent can be
    reconstructed by concatenating with the previous indent).
  * A *negative* indent change (this line is less indented) is encoded
    as a dent-indicator line containing ``marker * abs(delta)``, where
    ``marker`` is a Unicode codepoint not appearing in the source.
  * No change → an empty dent-indicator line.

The default marker is U+2190 LEFTWARDS ARROW (``←``). When the source
already contains that codepoint, the constructor walks the high
Unicode planes (down from U+10FFFF) until a free codepoint is found.

This module is small and deliberately stdlib-only — no compiled deps,
no IO. Safe to call from any context including the voice hot path.

Public surface:

  * :class:`RelativeIndenter` — captures the marker choice for a set
    of input texts and exposes ``make_relative`` / ``make_absolute``.
  * :func:`relative_indent` / :func:`absolute_indent` — convenience
    one-shots that build a single-use indenter.
"""

from __future__ import annotations

from typing import Iterable, List


_DEFAULT_MARKER = "←"  # ←
_HIGH_UNICODE_END = 0x10000  # below this lives normal text


class _MarkerCollisionError(ValueError):
    """Internal: source already contains every candidate marker."""


class RelativeIndenter:
    """Stateful indent encoder/decoder using a chosen outdent marker.

    Args:
        texts: Iterable of source strings. The marker is chosen so it
            appears in none of them.
        marker: Override marker. Pass when you specifically need a
            given codepoint (e.g. to make snapshots stable across
            runs). When the override is found in ``texts``, the
            constructor raises ``ValueError``.

    Attributes:
        marker: The chosen outdent marker (a single character).
    """

    def __init__(
        self,
        texts: Iterable[str],
        *,
        marker: str | None = None,
    ) -> None:
        chars = set()
        for text in texts:
            chars.update(text)
        if marker is not None:
            if marker in chars:
                raise ValueError(
                    f"requested marker {marker!r} already appears in input"
                )
            if len(marker) != 1:
                raise ValueError(
                    f"marker must be a single character, got {marker!r}"
                )
            self.marker = marker
            return
        if _DEFAULT_MARKER not in chars:
            self.marker = _DEFAULT_MARKER
            return
        self.marker = self._pick_unused_marker(chars)

    @staticmethod
    def _pick_unused_marker(used: set[str]) -> str:
        # Walk high Unicode planes downward until we hit an unused codepoint.
        for codepoint in range(0x10FFFF, _HIGH_UNICODE_END, -1):
            candidate = chr(codepoint)
            if candidate not in used:
                return candidate
        raise _MarkerCollisionError(
            "input uses every high-Unicode codepoint; no marker available"
        )

    # ------------------------------------------------------------------
    # Encode
    # ------------------------------------------------------------------

    def make_relative(self, text: str) -> str:
        """Encode ``text`` as relative-indent form.

        Raises:
            ValueError: when ``text`` already contains the outdent
                marker. Callers should construct the indenter with
                ``text`` in the texts iterable so the marker is chosen
                cleanly.
        """
        if self.marker in text:
            raise ValueError(
                f"text contains the chosen outdent marker {self.marker!r}; "
                "construct the indenter with all texts in advance"
            )

        lines = text.splitlines(keepends=True)
        output: List[str] = []
        prev_indent = ""
        for line in lines:
            stripped = line.rstrip("\n\r")
            indent_len = len(stripped) - len(stripped.lstrip())
            indent = line[:indent_len]
            delta = indent_len - len(prev_indent)
            if delta > 0:
                # New deeper indent: encode the newly-added prefix.
                dent_indicator = indent[-delta:]
            elif delta < 0:
                # Outdented: emit marker per missing space.
                dent_indicator = self.marker * (-delta)
            else:
                dent_indicator = ""
            output.append(dent_indicator + "\n" + line[indent_len:])
            prev_indent = indent
        return "".join(output)

    # ------------------------------------------------------------------
    # Decode
    # ------------------------------------------------------------------

    def make_absolute(self, text: str) -> str:
        """Reverse :meth:`make_relative`.

        Raises:
            ValueError: when the input is malformed (odd line count,
                outdent below column 0, marker survives in the result).
        """
        lines = text.splitlines(keepends=True)
        if len(lines) % 2 != 0:
            raise ValueError(
                f"relative-indent stream has odd line count "
                f"({len(lines)} lines); expected dent/content pairs"
            )
        output: List[str] = []
        prev_indent = ""
        for i in range(0, len(lines), 2):
            dent = lines[i].rstrip("\r\n")
            content = lines[i + 1]
            if dent.startswith(self.marker):
                # Outdent: number of markers = spaces to strip from prev.
                if any(ch != self.marker for ch in dent):
                    raise ValueError(
                        f"dent indicator mixes marker with other chars "
                        f"on pair {i // 2}: {dent!r}"
                    )
                outdent_len = len(dent)
                if outdent_len > len(prev_indent):
                    raise ValueError(
                        f"outdent of {outdent_len} would underflow "
                        f"current indent of {len(prev_indent)} "
                        f"on pair {i // 2}"
                    )
                cur_indent = prev_indent[:-outdent_len] if outdent_len else prev_indent
            else:
                cur_indent = prev_indent + dent
            if not content.rstrip("\r\n"):
                # Blank line keeps no indent.
                output.append(content)
            else:
                output.append(cur_indent + content)
            prev_indent = cur_indent
        result = "".join(output)
        if self.marker in result:
            raise ValueError(
                f"outdent marker {self.marker!r} leaked into decoded text"
            )
        return result


def relative_indent(text: str, *, marker: str | None = None) -> str:
    """One-shot encode: returns the relative-indent form of ``text``."""
    indenter = RelativeIndenter([text], marker=marker)
    return indenter.make_relative(text)


def absolute_indent(text: str, *, marker: str | None = None) -> str:
    """One-shot decode of a relative-indent stream produced with the
    same marker as the encoder used."""
    if marker is None:
        marker = _DEFAULT_MARKER
    indenter = RelativeIndenter([], marker=marker)
    return indenter.make_absolute(text)


__all__ = [
    "RelativeIndenter",
    "relative_indent",
    "absolute_indent",
]
