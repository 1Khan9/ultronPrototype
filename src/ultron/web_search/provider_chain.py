"""Multi-provider web-search chain with local-first fallback ladder.

Wraps a configurable ordered list of search providers and tries them
in sequence: the first one that returns a non-empty result list wins,
the rest are skipped. Empty results from one provider cascade to the
next so a SearxNG that's not running doesn't block the voice path —
we fall through to Brave, then to DuckDuckGo, before giving up.

Configured via ``web_search.providers`` (a list of provider IDs in
preference order). Default order:

    ["searxng", "brave", "duckduckgo"]

This ladder gives:

- **SearxNG**: zero-API-key, local meta-search (Google + DDG +
  Wikipedia + Brave + Bing in parallel via a self-hosted relay).
  Best privacy + speed + no quota.
- **Brave**: free 2000/mo public API. Fast and quality-ranked. Falls
  here when SearxNG isn't running.
- **DuckDuckGo**: HTML-scrape via ``duckduckgo-search`` lib. No key,
  no quota ceiling, ~500-1500 ms latency. Last-resort fallback.

The chain is constructed once at startup. Per-provider clients are
lazy-loaded (don't pay import cost for providers we don't use). Each
client has its own circuit breaker, so a provider that's flapping
gets short-circuited without slowing the chain down.

Empty-list semantics:
- A provider returning ``[]`` means "I had no opinion / I failed"
  — chain moves to next provider.
- A provider returning ``[result, ...]`` means "I have an answer" —
  chain stops there and returns.
- All providers empty -> chain returns ``[]`` (caller falls back to
  base knowledge with uncertainty caveat).

This matches the existing single-provider failure semantics so
:class:`ultron.web_search.search.WebSearchExecutor` doesn't need to
change.
"""

from __future__ import annotations

import time
from typing import List, Mapping, Optional

from ultron.config import get_config
from ultron.utils.logging import get_logger
from ultron.web_search.brave import SearchResult
from ultron.web_search.rate_limit import (
    RateLimitState,
    RateLimitTracker,
    get_global_tracker,
    parse_rate_limit_headers,
)

logger = get_logger("web_search.chain")


class SearchProviderChain:
    """Sequenced search providers with local-first fallback.

    Args:
        provider_ids: ordered list of provider names. None -> use
            ``web_search.providers`` from config.

    Raises:
        ValueError: if an unknown provider id is configured.
    """

    # Registry of known providers -> lazy factory functions.
    # Factories return the client OR raise (e.g., missing API key for
    # Brave). The chain catches construction errors and skips the
    # provider so a missing Brave key doesn't break SearxNG+DDG.
    _PROVIDER_FACTORIES = {
        "searxng": lambda: _make_searxng(),
        "brave": lambda: _make_brave(),
        "duckduckgo": lambda: _make_duckduckgo(),
    }

    def __init__(
        self,
        provider_ids: Optional[List[str]] = None,
        *,
        tracker: Optional[RateLimitTracker] = None,
    ) -> None:
        if provider_ids is None:
            cfg = get_config().web_search
            provider_ids = list(getattr(cfg, "providers", ["brave"]))
        if not provider_ids:
            raise ValueError("provider_ids cannot be empty")

        self.provider_ids: List[str] = []
        self._clients: dict = {}
        # T14 (openclaw-clawhub catalog port). Per-provider rate-limit
        # tracker. Default to the process-wide singleton so a 429
        # observed in one search call cools the provider down for
        # subsequent calls in the same session. Tests pass an
        # explicit tracker to keep state isolated.
        self._tracker: RateLimitTracker = tracker or get_global_tracker()
        for pid in provider_ids:
            pid = pid.lower().strip()
            if pid not in self._PROVIDER_FACTORIES:
                raise ValueError(
                    f"Unknown search provider {pid!r}; "
                    f"valid options: {sorted(self._PROVIDER_FACTORIES)}"
                )
            self.provider_ids.append(pid)
        logger.info(
            "Search provider chain: %s (in order; first non-empty wins)",
            " -> ".join(self.provider_ids),
        )

    @property
    def tracker(self) -> RateLimitTracker:
        """Return the chain's rate-limit tracker (for inspection + tests)."""
        return self._tracker

    def should_skip(self, provider_id: str) -> bool:
        """Return True iff ``provider_id`` is currently in cooldown.

        Mirrors :meth:`RateLimitTracker.should_skip` against the
        chain's tracker. Callers that wrap the chain (e.g. the
        speculative-classification path) can consult this before
        kicking off a fan-out to avoid burning latency on a
        known-cooled provider.
        """
        return self._tracker.should_skip(provider_id)

    def record_provider_outcome(
        self,
        provider_id: str,
        headers: Optional[Mapping[str, object]],
        *,
        was_429: bool = False,
    ) -> Optional[RateLimitState]:
        """Record a parsed rate-limit envelope for ``provider_id``.

        Provider clients call this after each request to keep the
        chain's tracker fresh. ``headers`` may be a
        :class:`requests.Response.headers` mapping, an ``httpx``
        ``Headers`` object, or a plain dict; case-insensitive lookup
        happens inside :func:`parse_rate_limit_headers`. Returns the
        parsed state (or ``None`` when no recognised headers were
        present) so the caller can also use it for in-call decisions.

        Providers that don't expose rate-limit headers don't need to
        call this; the tracker simply stays empty for them and the
        chain falls back to its legacy empty-list-cascade behaviour.
        """
        state = parse_rate_limit_headers(headers) if headers else None
        self._tracker.record(provider_id, state, was_429=was_429)
        return state

    def _get_client(self, pid: str):
        """Lazy-construct + cache the client for ``pid``. Returns
        ``None`` if construction failed (provider gets skipped)."""
        if pid in self._clients:
            return self._clients[pid]
        try:
            client = self._PROVIDER_FACTORIES[pid]()
            self._clients[pid] = client
            return client
        except Exception as e:                                         # noqa: BLE001
            logger.warning(
                "Failed to construct %r provider (%s); skipping in chain.",
                pid, e,
            )
            self._clients[pid] = None
            return None

    def search(
        self,
        query: str,
        count: Optional[int] = None,
        categories: Optional[str] = None,
    ) -> List[SearchResult]:
        """Run the chain. Returns the first non-empty result list.

        Args:
            query: the search text.
            count: max results per provider.
            categories: optional category hint (e.g. ``"news"``).
                Forwarded to providers that accept it (currently
                SearxNG); silently ignored by others.
        """
        query = query.strip()
        if not query:
            return []

        for pid in self.provider_ids:
            # T14: skip providers still in rate-limit cooldown.
            # Tracker is empty for any provider that hasn't surfaced
            # rate-limit headers via :meth:`record_provider_outcome`
            # so this is a no-op for legacy clients that haven't been
            # extended.
            if self._tracker.should_skip(pid):
                logger.debug(
                    "Chain: %r still in rate-limit cooldown; skipping",
                    pid,
                )
                continue
            client = self._get_client(pid)
            if client is None:
                continue
            t0 = time.monotonic()
            try:
                # Forward `categories` only to providers that accept
                # it; Brave + DuckDuckGo don't have the kwarg.
                if categories is not None and pid == "searxng":
                    results = client.search(
                        query, count=count, categories=categories,
                    )
                else:
                    results = client.search(query, count=count)
            except Exception as e:                                     # noqa: BLE001
                # The individual clients SHOULD return [] rather than
                # raise -- but defend against bugs / new providers.
                logger.warning(
                    "Provider %r raised unexpectedly (%s); "
                    "falling through.", pid, e,
                )
                results = []
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            if results:
                logger.info(
                    "Chain: %r served %d results from %r in %.0f ms",
                    query[:60], len(results), pid, elapsed_ms,
                )
                return results
            else:
                logger.debug(
                    "Chain: %r empty from %r in %.0f ms; trying next provider",
                    query[:60], pid, elapsed_ms,
                )

        logger.info(
            "Chain: %r exhausted all %d providers; returning empty",
            query[:60], len(self.provider_ids),
        )
        return []


# --- Lazy factory helpers ---------------------------------------------------


def _make_searxng():
    from ultron.web_search.searxng import SearxNGSearchClient
    return SearxNGSearchClient()


def _make_brave():
    from ultron.web_search.brave import BraveSearchClient
    return BraveSearchClient()


def _make_duckduckgo():
    from ultron.web_search.duckduckgo import DuckDuckGoSearchClient
    return DuckDuckGoSearchClient()


__all__ = ["SearchProviderChain"]
