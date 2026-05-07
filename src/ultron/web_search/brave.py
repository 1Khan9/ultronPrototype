"""Brave Search API client.

Thin wrapper around the Brave Web Search REST endpoint. Returns a
normalized list of :class:`BraveResult` objects; callers don't see
Brave-specific JSON shape.

Rate-limited via a per-client monotonic timestamp -- Brave's free tier
caps concurrent requests, so we space calls out by a configurable
minimum interval.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import List, Optional

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("web_search.brave")


@dataclass(frozen=True)
class BraveResult:
    """One result row from a Brave search."""

    url: str
    title: str
    snippet: str  # Brave's "description" field
    rank: int  # 0-based position in the result list


class BraveSearchClient:
    """Client for Brave Web Search API.

    Args:
        api_key: ``X-Subscription-Token``. Pulled from settings if not given.
        rate_limit_s: minimum seconds between requests across all callers.
        timeout_s: per-request timeout.
        endpoint: override the default URL (rarely needed).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_s: float = settings.WEB_SEARCH_BRAVE_RATE_LIMIT_S,
        timeout_s: float = settings.WEB_SEARCH_BRAVE_TIMEOUT_S,
        endpoint: str = settings.WEB_SEARCH_BRAVE_ENDPOINT,
    ) -> None:
        self.api_key = api_key or settings.WEB_SEARCH_BRAVE_API_KEY
        if not self.api_key:
            raise ValueError(
                "Brave API key missing. Set ULTRON_BRAVE_API_KEY in your env "
                "or pass api_key=... to BraveSearchClient."
            )
        self.endpoint = endpoint
        self.rate_limit_s = rate_limit_s
        self.timeout_s = timeout_s
        self._last_call = 0.0
        self._lock = threading.Lock()

    def search(
        self,
        query: str,
        count: int = settings.WEB_SEARCH_BRAVE_COUNT,
    ) -> List[BraveResult]:
        """Run a single Brave search.

        Returns up to ``count`` :class:`BraveResult` rows. On API failure or
        empty response, returns ``[]`` and logs the reason.
        """
        query = query.strip()
        if not query:
            return []
        self._respect_rate_limit()

        import requests

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": min(20, max(1, count)),
            # Conservative defaults: keep results clean + recent.
            "safesearch": "moderate",
            "result_filter": "web",
        }
        t0 = time.monotonic()
        try:
            resp = requests.get(
                self.endpoint,
                headers=headers,
                params=params,
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            logger.warning("Brave timed out after %.1fs for %r", self.timeout_s, query)
            return []
        except requests.exceptions.HTTPError as e:
            logger.warning("Brave HTTP %s for %r", e.response.status_code if e.response else "?", query)
            return []
        except Exception as e:
            logger.warning("Brave request failed for %r: %s", query, e)
            return []

        web_results = (data.get("web") or {}).get("results") or []
        results: List[BraveResult] = []
        for i, row in enumerate(web_results[:count]):
            url = (row.get("url") or "").strip()
            if not url:
                continue
            results.append(
                BraveResult(
                    url=url,
                    title=(row.get("title") or "").strip(),
                    snippet=(row.get("description") or "").strip(),
                    rank=i,
                )
            )
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Brave: %r -> %d results in %.0f ms",
            query[:80], len(results), elapsed_ms,
        )
        return results

    def _respect_rate_limit(self) -> None:
        """Block in-process until enough time has elapsed since the last call.

        Single-process only; the embedded prototype doesn't share a rate
        limit across machines.
        """
        with self._lock:
            now = time.monotonic()
            wait = (self._last_call + self.rate_limit_s) - now
            if wait > 0:
                logger.debug("Brave rate-limit sleep: %.2fs", wait)
                time.sleep(wait)
            self._last_call = time.monotonic()
