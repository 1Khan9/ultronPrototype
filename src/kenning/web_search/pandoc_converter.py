"""HTML → Markdown conversion via pypandoc, with graceful degradation.

Pattern lifted in spirit (not in source) from aider's ``scrape.py``
``html_to_markdown`` (Apache 2.0; see ``THIRD_PARTY_NOTICES.md``).

Pandoc produces the highest-quality HTML→Markdown conversion available
in open source: it preserves heading structure, lists, tables, and
code blocks faithfully where naive regex / HTML-stripping approaches
flatten them into unstructured paragraphs.

This module wraps :mod:`pypandoc` with three failure modes that all
degrade to "skip the conversion, return None":

  1. ``pypandoc`` not installed → None.
  2. Pandoc binary not installed (the system tool, not the Python
     wrapper) → None. We DON'T auto-install per the catalog's
     suggestion — Pandoc is a 150 MB+ system install and the user
     should opt in deliberately.
  3. Pandoc raises during conversion (malformed HTML, encoding
     errors) → None.

Callers should pre-slim the HTML via
:func:`kenning.web_search.slimdown_html.slimdown_html` before passing
it here. That cuts pandoc's wall time significantly on landing-page
content.

Public surface:

  * :func:`html_to_markdown(html_text) -> Optional[str]` — convert
    or return None on any failure.
  * :func:`pandoc_available() -> bool` — checks both layers (Python
    wrapper + system binary) and returns True iff both are present.
"""

from __future__ import annotations

import logging
from typing import Optional


logger = logging.getLogger("kenning.web_search.pandoc_converter")


# Pandoc args matching aider's:
#   --from html --to markdown_strict --wrap=none --columns=200
# strict markdown means no Pandoc-specific extensions in the output
# (e.g., raw HTML blocks stay collapsed); --wrap=none keeps lines
# uncluttered for token efficiency.
_PANDOC_FROM = "html"
_PANDOC_TO = "markdown_strict"
_PANDOC_EXTRA_ARGS = ["--wrap=none", "--columns=200"]


def html_to_markdown(html_text: str) -> Optional[str]:
    """Convert HTML to Markdown via pandoc.

    Returns the Markdown string on success, ``None`` on any failure
    (missing dep / missing binary / pandoc error / empty result).
    """
    if not html_text:
        return None
    try:
        import pypandoc  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("pypandoc not installed; skipping conversion")
        return None
    try:
        result = pypandoc.convert_text(
            html_text,
            to=_PANDOC_TO,
            format=_PANDOC_FROM,
            extra_args=_PANDOC_EXTRA_ARGS,
        )
    except OSError as exc:
        # OSError typically means the pandoc binary isn't installed.
        logger.debug("pandoc binary unavailable (%s); skipping", exc)
        return None
    except Exception as exc:                                  # noqa: BLE001
        logger.debug("pandoc conversion failed (%s); skipping", exc)
        return None
    stripped = (result or "").strip()
    if not stripped:
        return None
    return stripped


def pandoc_available() -> bool:
    """True iff both ``pypandoc`` (Python wrapper) AND the Pandoc
    binary are available.

    A False return means callers should skip the conversion step and
    fall back to the raw text (or :func:`slimdown_html` only).
    """
    try:
        import pypandoc  # type: ignore[import-not-found]
    except ImportError:
        return False
    try:
        pypandoc.get_pandoc_version()
    except (OSError, Exception):
        return False
    return True


__all__ = ["html_to_markdown", "pandoc_available"]
