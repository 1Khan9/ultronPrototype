"""Tests for the catalog batch 12 web-search reader additions:
:mod:`kenning.web_search.slimdown_html`,
:mod:`kenning.web_search.pandoc_converter`, and
:mod:`kenning.web_search.playwright_reader`."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# slimdown_html
# ---------------------------------------------------------------------------


def test_slimdown_drops_script_tags():
    from kenning.web_search.slimdown_html import slimdown_html

    html = "<html><body><p>hello</p><script>alert(1)</script></body></html>"
    out = slimdown_html(html)
    assert "<script>" not in out
    assert "alert" not in out
    assert "hello" in out


def test_slimdown_drops_style_tags():
    from kenning.web_search.slimdown_html import slimdown_html

    html = "<html><head><style>body{color:red}</style></head><body><p>x</p></body></html>"
    out = slimdown_html(html)
    assert "<style>" not in out
    assert "color:red" not in out


def test_slimdown_drops_img_and_svg():
    from kenning.web_search.slimdown_html import slimdown_html

    html = "<div><img src='cat.png'><svg><circle/></svg><p>text</p></div>"
    out = slimdown_html(html)
    assert "<img" not in out
    assert "<svg" not in out
    assert "text" in out


def test_slimdown_drops_form_widgets():
    from kenning.web_search.slimdown_html import slimdown_html

    html = "<form><input type='text'><button>Go</button></form><p>visible</p>"
    out = slimdown_html(html)
    assert "<form" not in out
    assert "<input" not in out
    assert "<button" not in out
    assert "visible" in out


def test_slimdown_strips_non_href_attributes():
    from kenning.web_search.slimdown_html import slimdown_html

    html = '<a href="https://x.com" class="big" data-tracking="abc">click</a>'
    out = slimdown_html(html)
    assert 'href="https://x.com"' in out
    assert "class=" not in out
    assert "data-tracking" not in out


def test_slimdown_drops_data_url_in_href():
    from kenning.web_search.slimdown_html import slimdown_html

    html = '<a href="data:image/png;base64,iVBORw0KG">huge</a>'
    out = slimdown_html(html)
    # The href is removed entirely; the anchor text survives.
    assert "data:image" not in out
    assert "huge" in out


def test_slimdown_handles_empty_input():
    from kenning.web_search.slimdown_html import slimdown_html

    assert slimdown_html("") == ""


def test_slimdown_handles_malformed_html():
    """bs4 is fault-tolerant — slimdown shouldn't crash."""
    from kenning.web_search.slimdown_html import slimdown_html

    out = slimdown_html("<div><p>missing close")
    assert "missing close" in out


def test_slimdown_preserves_paragraphs_and_links():
    from kenning.web_search.slimdown_html import slimdown_html

    html = (
        "<article>"
        "<h1 class='big' id='top'>Title</h1>"
        "<p>First paragraph with <a href='https://x.com' style='font:bold'>link</a>.</p>"
        "<p>Second paragraph.</p>"
        "</article>"
    )
    out = slimdown_html(html)
    assert "Title" in out
    assert "First paragraph" in out
    assert "Second paragraph" in out
    assert 'href="https://x.com"' in out
    # Attributes other than href stripped.
    assert "class=" not in out
    assert "id=" not in out


# ---------------------------------------------------------------------------
# pandoc_converter
# ---------------------------------------------------------------------------


def test_pandoc_available_returns_bool():
    from kenning.web_search.pandoc_converter import pandoc_available

    result = pandoc_available()
    assert isinstance(result, bool)


def test_pandoc_html_to_markdown_empty_returns_none():
    from kenning.web_search.pandoc_converter import html_to_markdown

    assert html_to_markdown("") is None


def test_pandoc_html_to_markdown_when_unavailable_returns_none():
    """If pandoc binary isn't installed, conversion returns None."""
    from kenning.web_search.pandoc_converter import html_to_markdown, pandoc_available

    if pandoc_available():
        # Conversion should succeed on this machine.
        result = html_to_markdown("<h1>Title</h1><p>body</p>")
        assert result is not None
        assert "Title" in result
        assert "body" in result
    else:
        # Conversion gracefully degrades.
        result = html_to_markdown("<h1>Title</h1>")
        assert result is None


def test_pandoc_handles_invalid_input_gracefully():
    """Pandoc's behavior on malformed HTML — we don't care what it
    returns, just that it doesn't crash."""
    from kenning.web_search.pandoc_converter import html_to_markdown

    result = html_to_markdown("<<<>>>not really html<<<>>>")
    # Either None (pandoc unavailable) or a string (pandoc tolerant) — both OK.
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# playwright_reader
# ---------------------------------------------------------------------------


def test_playwright_reader_constructs_without_playwright():
    """The reader's constructor must not require playwright to be installed."""
    from kenning.web_search.playwright_reader import PlaywrightReader

    reader = PlaywrightReader()
    assert reader is not None


def test_playwright_reader_fetch_returns_none_when_unavailable():
    """When playwright isn't installed, fetch() returns None silently."""
    from kenning.web_search.playwright_reader import PlaywrightReader
    import importlib.util as _u

    if _u.find_spec("playwright") is not None:
        pytest.skip("playwright IS installed; this test only validates the fallback")
    reader = PlaywrightReader()
    result = reader.fetch("https://example.com")
    assert result is None


def test_playwright_reader_close_is_safe_when_not_started():
    """Close should not raise when the browser was never launched."""
    from kenning.web_search.playwright_reader import PlaywrightReader

    reader = PlaywrightReader()
    reader.close()  # idempotent
    reader.close()


def test_playwright_reader_fetch_empty_url_returns_none():
    from kenning.web_search.playwright_reader import PlaywrightReader

    reader = PlaywrightReader()
    assert reader.fetch("") is None


# ---------------------------------------------------------------------------
# reader_chain registration
# ---------------------------------------------------------------------------


def test_reader_chain_accepts_playwright_in_factory_list():
    """The chain's factory dict should now know about ``playwright``."""
    from kenning.web_search.reader_chain import ReaderChain

    assert "playwright" in ReaderChain._READER_FACTORIES


def test_reader_chain_with_playwright_only_constructs():
    """Constructing the chain with just playwright should work; fetch
    will degrade gracefully when playwright isn't installed."""
    from kenning.web_search.reader_chain import ReaderChain

    chain = ReaderChain(reader_ids=["playwright"])
    assert chain.reader_ids == ["playwright"]
    # Fetch returns None because (a) playwright likely not installed
    # AND/OR (b) the URL won't resolve in the test environment.
    result = chain.fetch("https://example.com")
    # Result could be None (no playwright, or network blocked) or a
    # string (if playwright actually IS installed AND the test box can
    # reach example.com). Either is acceptable.
    assert result is None or isinstance(result, str)
