"""Jina Reader client for full-page extraction.

Jina Reader (https://r.jina.ai/) takes a URL and returns clean Markdown
of the page, stripping nav/ads/scripts. No auth required for the volumes
the prototype uses.

The client truncates very large responses so a giant article doesn't
balloon the LLM prompt -- we only need the substantive content, not the
entire page.
"""

from __future__ import annotations

import time
from typing import Optional

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("web_search.jina")


class JinaReaderClient:
    """Wrapper around r.jina.ai for clean page extraction."""

    def __init__(
        self,
        endpoint: str = settings.WEB_SEARCH_JINA_ENDPOINT,
        timeout_s: float = settings.WEB_SEARCH_JINA_TIMEOUT_S,
        max_bytes: int = settings.WEB_SEARCH_JINA_MAX_BYTES,
    ) -> None:
        # Endpoint must end with `/` so URL concatenation works.
        if not endpoint.endswith("/"):
            endpoint = endpoint + "/"
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes

    def fetch(self, url: str) -> Optional[str]:
        """Return cleaned-up markdown for ``url`` or ``None`` on failure.

        Output is truncated to ``self.max_bytes`` chars at the trailing
        edge with a marker, so giant pages don't blow up the LLM prompt.
        """
        url = url.strip()
        if not url:
            return None

        import requests

        t0 = time.monotonic()
        try:
            resp = requests.get(
                self.endpoint + url,
                headers={"Accept": "text/markdown"},
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            text = resp.text or ""
        except requests.exceptions.Timeout:
            logger.warning("Jina timed out after %.1fs for %s", self.timeout_s, url)
            return None
        except requests.exceptions.HTTPError as e:
            logger.warning(
                "Jina HTTP %s for %s",
                e.response.status_code if e.response else "?", url,
            )
            return None
        except Exception as e:
            logger.warning("Jina fetch failed for %s: %s", url, e)
            return None

        elapsed_ms = (time.monotonic() - t0) * 1000
        if len(text) > self.max_bytes:
            text = text[: self.max_bytes] + "\n\n[truncated]"
        logger.info("Jina: %s -> %d chars in %.0f ms", url[:60], len(text), elapsed_ms)
        return text
