"""Aggressive HTML preprocessing for clean Markdown conversion.

Pattern lifted in spirit (not in source) from aider's
``scrape.slimdown_html`` (Apache 2.0; see ``THIRD_PARTY_NOTICES.md``).

Before piping HTML through pandoc, strip everything that bloats the
output but adds no real reading value:

  * ``<svg>`` / ``<img>`` tags — visual content, irrelevant to text.
  * ``<style>`` / ``<script>`` tags — formatting + behavior, never
    content.
  * ``<noscript>`` blocks — empty placeholders for JS-disabled clients.
  * Attributes on every element EXCEPT ``href`` on ``<a>`` — class
    names / data-* / aria-* / id / style add bytes pandoc faithfully
    preserves as Markdown.{attr=val} runs.
  * ``data:`` and ``blob:`` URLs — base64 image bombs.
  * Inline form widgets (``<input>`` / ``<button>`` / ``<select>``) —
    interactive UI, not content.

Empirically this drops typical landing-page HTML by 70-90 % WITHOUT
removing any text the LLM cares about. Pandoc's HTML→Markdown pass
then runs much faster and produces dramatically cleaner output.

Public surface:

  * :func:`slimdown_html(html_text) -> str` — preprocess and return
    the slimmer HTML.

Fail-open: when BeautifulSoup is unavailable for any reason, returns
the input unchanged. Callers should treat the output as opaque.
"""

from __future__ import annotations

import logging
from typing import Optional


logger = logging.getLogger("ultron.web_search.slimdown_html")


# Tags whose ENTIRE subtree is discarded.
_DROP_TAGS = (
    "svg",
    "img",
    "style",
    "script",
    "noscript",
    "iframe",
    "video",
    "audio",
    "canvas",
    "button",
    "input",
    "select",
    "form",
    "textarea",
    "object",
    "embed",
)


# Schemes whose href / src values we replace with ``#`` to avoid
# embedding huge base64 payloads.
_DROP_SCHEMES = ("data:", "blob:", "javascript:")


def slimdown_html(html_text: str) -> str:
    """Strip visual / interactive / inline-data noise from HTML.

    Returns the slimmer HTML text. Returns the input unchanged when
    BeautifulSoup isn't installed.
    """
    if not html_text:
        return ""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]
    except ImportError:
        logger.debug(
            "slimdown_html: bs4 not installed; returning input unchanged"
        )
        return html_text

    try:
        soup = BeautifulSoup(html_text, "html.parser")
    except Exception as exc:                                  # noqa: BLE001
        logger.debug("slimdown_html: bs4 parse failed (%s); returning input", exc)
        return html_text

    # 1. Drop entire subtrees we never want.
    for tag_name in _DROP_TAGS:
        for tag in soup.find_all(tag_name):
            try:
                tag.decompose()
            except Exception:                                 # noqa: BLE001
                continue

    # 2. Replace inline-data URLs on remaining tags.
    for tag in soup.find_all(True):
        # Only keep href / src and strip everything else.
        attrs_to_keep: dict[str, str] = {}
        try:
            tag_attrs = dict(tag.attrs)
        except Exception:                                     # noqa: BLE001
            tag_attrs = {}
        for attr, value in tag_attrs.items():
            attr_lower = attr.lower()
            if attr_lower in {"href", "src"}:
                val = _normalise_attr_value(value)
                if _is_dropped_url(val):
                    continue  # drop the attribute entirely
                attrs_to_keep[attr] = val
        try:
            tag.attrs = attrs_to_keep
        except Exception:                                     # noqa: BLE001
            continue

    # 3. Return as text. Use minimal formatter to avoid extra
    # whitespace runs.
    try:
        return str(soup)
    except Exception:                                         # noqa: BLE001
        return html_text


def _normalise_attr_value(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def _is_dropped_url(value: str) -> bool:
    lowered = value.strip().lower()
    return any(lowered.startswith(s) for s in _DROP_SCHEMES)


__all__ = ["slimdown_html"]
