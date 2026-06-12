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

from ultron.config import get_config
from ultron.errors import JinaReaderError
from ultron.resilience import CircuitBreaker, CircuitOpenError, get_error_log
from ultron.utils.logging import get_logger

logger = get_logger("web_search.jina")


# Shared breaker — Jina's free tier can rate-limit or 5xx in bursts.
# Threshold is more permissive than Brave because losing Jina degrades
# gracefully (we keep Brave snippets); the cost of a tripped breaker is
# lower so we tolerate more failures before tripping.
_JINA_BREAKER = CircuitBreaker(
    name="jina",
    failure_threshold=5,
    window_seconds=300.0,
    cooldown_seconds=180.0,
    expected_exceptions=(JinaReaderError,),
)


class JinaReaderClient:
    """Wrapper around r.jina.ai for clean page extraction."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout_s: Optional[float] = None,
        max_bytes: Optional[int] = None,
    ) -> None:
        cfg = get_config().web_search.jina
        endpoint = endpoint if endpoint is not None else cfg.endpoint
        # Endpoint must end with `/` so URL concatenation works.
        if not endpoint.endswith("/"):
            endpoint = endpoint + "/"
        self.endpoint = endpoint
        self.timeout_s = timeout_s if timeout_s is not None else cfg.timeout_seconds
        self.max_bytes = max_bytes if max_bytes is not None else cfg.max_bytes

    def fetch(self, url: str) -> Optional[str]:
        """Return cleaned-up markdown for ``url`` or ``None`` on failure.

        Output is truncated to ``self.max_bytes`` chars at the trailing
        edge with a marker, so giant pages don't blow up the LLM prompt.

        Failures (timeout, HTTP error, circuit open) record to
        ``logs/errors.jsonl`` and return ``None``; caller falls back to
        the Brave snippet rather than the full page.
        """
        url = url.strip()
        if not url:
            return None

        try:
            return _JINA_BREAKER.call(self._do_fetch, url)
        except CircuitOpenError as e:
            logger.warning("Jina circuit OPEN for %s — short-circuiting; %s",
                           url[:80], e)
            get_error_log().record(
                JinaReaderError(
                    "circuit open",
                    context={"url": url[:200], "circuit": "jina"},
                    recovery="short-circuited; Brave snippet only",
                ),
                dependency="jina",
                include_traceback=False,
            )
            return None
        except JinaReaderError as e:
            get_error_log().record(
                e.with_recovery("snippet-only fallback"),
                dependency="jina",
            )
            return None

    def _do_fetch(self, url: str) -> str:
        """Inner implementation. Raises :class:`JinaReaderError` on
        failure; the breaker counts those toward the threshold."""
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
        except requests.exceptions.Timeout as e:
            raise JinaReaderError(
                f"Jina timed out after {self.timeout_s:.1f}s",
                context={"url": url[:200], "timeout_s": self.timeout_s},
            ) from e
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            raise JinaReaderError(
                f"Jina HTTP {status}",
                context={"url": url[:200], "status_code": status},
            ) from e
        except requests.exceptions.RequestException as e:
            raise JinaReaderError(
                f"Jina request failed: {e}",
                context={"url": url[:200]},
            ) from e

        elapsed_ms = (time.monotonic() - t0) * 1000
        if len(text) > self.max_bytes:
            text = text[: self.max_bytes] + "\n\n[truncated]"
        logger.info("Jina: %s -> %d chars in %.0f ms", url[:60], len(text), elapsed_ms)
        return text
