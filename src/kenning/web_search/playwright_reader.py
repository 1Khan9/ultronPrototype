"""JS-rendered page extraction via Playwright (opt-in, heavy dep).

Pattern lifted in spirit (not in source) from aider's
``scrape.scrape_with_playwright`` (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``).

For pages that trafilatura can't extract (single-page apps, JS-heavy
dashboards, Cloudflare-challenged sites), Playwright launches a real
headless Chromium browser, navigates the URL with
``wait_until="networkidle"`` (5 s timeout), grabs the post-JS DOM,
and feeds it through the slimdown → pandoc pipeline.

Catalog notes on UA strip: Chromium sets ``User-Agent`` containing
``HeadlessChrome``; many sites refuse to serve headless browsers.
We strip ``Headless`` from the UA string before navigation.

This is the heaviest reader by far:

  * ~150 MB Chromium download on first use (the user must run
    ``playwright install chromium``).
  * 1-3 s cold-start per process.
  * 0.5-5 s per page navigation.
  * ~150 MB RAM peak while a page is loading.

Therefore: DEFAULT OFF, opt-in via ``web_search.readers`` config.
When the playwright dep is missing we degrade silently to "skip
this reader" — the chain falls through to the next reader.

Public surface:

  * :class:`PlaywrightReader` — matches the
    ``fetch(url) -> Optional[str]`` interface used by the rest of
    the reader chain.

The reader is stateful (it holds a Playwright browser instance) but
constructs the browser LAZILY on the first ``fetch`` call so import
+ construction stay cheap when the feature isn't actually used.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional


logger = logging.getLogger("kenning.web_search.playwright_reader")


# Wait condition forwarded to Playwright's ``page.goto``. The catalog
# uses ``networkidle`` because most SPAs settle into idle after their
# initial render burst.
DEFAULT_WAIT_UNTIL = "networkidle"


# Per-navigation timeout in milliseconds.
DEFAULT_NAVIGATION_TIMEOUT_MS = 5_000


# Per-navigation script-execution timeout in milliseconds.
DEFAULT_BROWSER_LAUNCH_TIMEOUT_MS = 30_000


# Sanitised User-Agent — catalog rule: strip ``Headless`` from the
# default UA so sites that block headless browsers serve us content.
def _sanitised_user_agent() -> Optional[str]:
    """Build a UA string with ``Headless`` removed.

    Returns None when we can't probe the default UA (lets Playwright
    use its own default).
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            ua = p.chromium.launch(headless=True).new_context().new_page().evaluate(
                "navigator.userAgent"
            )
            return ua.replace("HeadlessChrome", "Chrome")
    except Exception:                                          # noqa: BLE001
        return None


class PlaywrightReader:
    """JS-aware page extractor backed by Playwright + slimdown + pandoc.

    Construct with no arguments; the browser launches LAZILY on first
    ``fetch``. Call ``close()`` to release the Chromium process when
    done.

    Args:
        wait_until: Forwarded to ``page.goto``. Default
            ``"networkidle"``.
        navigation_timeout_ms: Per-page timeout. Default 5 s.
        run_pandoc: When True (default), the post-JS DOM is passed
            through :func:`slimdown_html` then
            :func:`html_to_markdown`. When False, the raw HTML is
            returned.
    """

    def __init__(
        self,
        *,
        wait_until: str = DEFAULT_WAIT_UNTIL,
        navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        run_pandoc: bool = True,
    ) -> None:
        self._wait_until = wait_until
        self._navigation_timeout_ms = int(navigation_timeout_ms)
        self._run_pandoc = bool(run_pandoc)
        self._lock = threading.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._available_checked: bool = False
        self._available: bool = False

    def _ensure_available(self) -> bool:
        """Lazy-import + lazy-browser-launch."""
        if self._available_checked:
            return self._available
        self._available_checked = True
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            logger.info(
                "playwright not installed; PlaywrightReader disabled. "
                "Install with: pip install playwright && playwright install chromium"
            )
            self._available = False
            return False
        self._available = True
        return True

    def _ensure_browser(self) -> None:
        """Launch the persistent Chromium process if not already up."""
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
        )

    def fetch(self, url: str) -> Optional[str]:
        """Navigate to ``url``, return Markdown (or raw HTML if pandoc disabled).

        Returns ``None`` on:
          * playwright not installed,
          * browser launch failure,
          * navigation timeout / error,
          * empty content after extraction.
        """
        if not url:
            return None
        if not self._ensure_available():
            return None

        with self._lock:
            try:
                self._ensure_browser()
            except Exception as exc:                          # noqa: BLE001
                logger.warning(
                    "PlaywrightReader: browser launch failed (%s)", exc,
                )
                return None
            try:
                content = self._fetch_content(url)
            except Exception as exc:                          # noqa: BLE001
                logger.warning(
                    "PlaywrightReader: fetch failed for %s: %s", url, exc,
                )
                return None

        if not content:
            return None
        if not self._run_pandoc:
            return content
        return _slim_and_convert(content)

    def _fetch_content(self, url: str) -> Optional[str]:
        ua = _sanitised_user_agent()
        context_kwargs: dict[str, Any] = {}
        if ua:
            context_kwargs["user_agent"] = ua
        context = self._browser.new_context(**context_kwargs)
        try:
            page = context.new_page()
            page.set_default_navigation_timeout(self._navigation_timeout_ms)
            page.goto(url, wait_until=self._wait_until)
            return page.content()
        finally:
            try:
                context.close()
            except Exception:                                 # noqa: BLE001
                pass

    def close(self) -> None:
        """Release the Chromium process. Safe to call multiple times."""
        with self._lock:
            try:
                if self._browser is not None:
                    self._browser.close()
            except Exception:                                 # noqa: BLE001
                pass
            try:
                if self._playwright is not None:
                    self._playwright.stop()
            except Exception:                                 # noqa: BLE001
                pass
            self._browser = None
            self._playwright = None


def _slim_and_convert(html_text: str) -> Optional[str]:
    """Slim → pandoc. Returns markdown or None."""
    try:
        from kenning.web_search.slimdown_html import slimdown_html
        from kenning.web_search.pandoc_converter import html_to_markdown
    except ImportError:
        return None
    slimmed = slimdown_html(html_text)
    md = html_to_markdown(slimmed)
    if md is None:
        # If pandoc is unavailable, fall back to the slimmed HTML
        # itself — at least the visual / inline-data noise is gone.
        return slimmed
    return md


__all__ = [
    "DEFAULT_BROWSER_LAUNCH_TIMEOUT_MS",
    "DEFAULT_NAVIGATION_TIMEOUT_MS",
    "DEFAULT_WAIT_UNTIL",
    "PlaywrightReader",
]
