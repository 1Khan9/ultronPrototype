"""HTTP rate-limit envelope parser + backoff helpers (T14).

T14 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
A canonical client-side primitive that:

1. **Parses the triple-header envelope** every well-behaved JSON HTTP
   server now emits: the legacy ``X-RateLimit-*`` family with
   ``X-RateLimit-Reset`` as an absolute Unix-epoch timestamp; the
   standardised ``RateLimit-*`` family (RFC draft-ietf-httpapi-ratelimit-headers)
   with ``RateLimit-Reset`` as a seconds-until-reset delay; and the
   universal ``Retry-After`` header (numeric seconds or HTTP-date)
   that's emitted on 429 responses.
2. **Picks the next-retry timestamp** with the documented preferred-
   fallback order: ``Retry-After`` -> ``RateLimit-Reset`` ->
   ``X-RateLimit-Reset``. The first present-and-parseable header
   wins.
3. **Computes backoff delay** as exponential with jitter, falling back
   to the server-supplied retry hint when present. Default base
   300 ms, cap 5 s, jitter 0-300 ms, mirroring the upstream client.

Generalised beyond web-search providers: the same parser + state +
backoff shape applies to any HTTP-talking subsystem in ultron
(MCP transport, future remote-LLM cascade, Jina reader, OpenClaw
gateway), so this lives under :mod:`ultron.web_search` for
historical wiring proximity but its public API is provider-agnostic.
"""

from __future__ import annotations

import email.utils
import logging
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Header name constants (API contracts; case-insensitive on the wire)

#: Legacy header family. Reset is absolute Unix-epoch seconds.
X_RATELIMIT_LIMIT: str = "X-RateLimit-Limit"
X_RATELIMIT_REMAINING: str = "X-RateLimit-Remaining"
X_RATELIMIT_RESET: str = "X-RateLimit-Reset"

#: Standardised header family. Reset is a delay in seconds.
RATELIMIT_LIMIT: str = "RateLimit-Limit"
RATELIMIT_REMAINING: str = "RateLimit-Remaining"
RATELIMIT_RESET: str = "RateLimit-Reset"

#: Emitted on 429 responses. Numeric seconds OR HTTP-date.
RETRY_AFTER: str = "Retry-After"

#: When parsing :data:`RETRY_AFTER` and the value is a bare integer
#: this large or larger, the parser treats it as an absolute Unix
#: epoch timestamp rather than a delay. The upstream client uses 31
#: million seconds (~1 year) as the heuristic threshold; matches.
RETRY_AFTER_EPOCH_THRESHOLD_SECONDS: float = 31_000_000.0


# ---------------------------------------------------------------------------
# Defaults

#: Base delay (seconds) for exponential backoff when the server has
#: NOT supplied a Retry-After / Reset hint. Doubles per attempt up to
#: :data:`DEFAULT_BACKOFF_CAP_SECONDS`.
DEFAULT_BACKOFF_BASE_SECONDS: float = 0.3

#: Cap for the deterministic part of the backoff. Jitter adds on top.
DEFAULT_BACKOFF_CAP_SECONDS: float = 5.0

#: Maximum jitter (seconds) added uniformly at random to every
#: computed backoff. Smooths out thundering-herd retries from
#: concurrent callers.
DEFAULT_BACKOFF_JITTER_SECONDS: float = 0.3

#: Default retry budget per logical operation. The chain-driver
#: skips a provider after this many consecutive 429s.
DEFAULT_MAX_RETRIES: int = 2


# ---------------------------------------------------------------------------
# Parser primitives


def _to_int(raw: object) -> Optional[int]:
    """Return ``raw`` as an int when parseable, else None.

    Accepts ``int``, ``str`` (numeric), or anything :func:`int` can
    convert. Returns None on parse failure or negative value (the
    standard explicitly forbids negative counts).
    """
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def _to_float(raw: object) -> Optional[float]:
    """Return ``raw`` as a non-negative float when parseable, else None."""
    if raw is None:
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _normalize_headers(headers: Mapping[str, object]) -> dict[str, str]:
    """Return ``headers`` with case-folded keys mapping to stripped str values.

    HTTP header names are case-insensitive; this function lets
    :func:`parse_rate_limit_headers` consume mappings produced by
    ``requests.Response.headers`` (case-insensitive dict),
    ``httpx`` (case-insensitive), or hand-built ``dict[str, str]``
    fixtures uniformly.
    """
    normalised: dict[str, str] = {}
    for key, value in headers.items():
        if key is None or value is None:
            continue
        normalised[str(key).casefold()] = str(value).strip()
    return normalised


def parse_retry_after(value: str, *, now: Optional[datetime] = None) -> Optional[float]:
    """Return the delay (seconds) requested by a ``Retry-After`` header.

    Accepts either:

    * **Numeric**: a delay in seconds (e.g. ``"30"``). Negative or
      non-numeric -> None.
    * **HTTP-date**: RFC 7231 IMF-fixdate (e.g. ``"Wed, 21 Oct 2015
      07:28:00 GMT"``). Parsed via :func:`email.utils.parsedate_to_datetime`.

    When the numeric value is at least
    :data:`RETRY_AFTER_EPOCH_THRESHOLD_SECONDS`, it's treated as an
    absolute Unix epoch (matches upstream behaviour).

    ``now`` may be supplied for deterministic tests; defaults to
    :func:`datetime.datetime.now` in UTC.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    reference = now or datetime.now(timezone.utc)

    numeric = _to_float(text)
    if numeric is not None:
        if numeric >= RETRY_AFTER_EPOCH_THRESHOLD_SECONDS:
            delay = numeric - reference.timestamp()
            return max(0.0, delay)
        return numeric

    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delay = parsed.timestamp() - reference.timestamp()
    return max(0.0, delay)


def _delay_from_reset(value: str, *, absolute: bool, now: datetime) -> Optional[float]:
    """Translate a reset header into a delay-in-seconds.

    ``absolute=True`` for :data:`X_RATELIMIT_RESET` (Unix epoch);
    ``absolute=False`` for :data:`RATELIMIT_RESET` (delay).
    """
    parsed = _to_float(value)
    if parsed is None:
        return None
    if not absolute:
        return parsed
    delay = parsed - now.timestamp()
    return max(0.0, delay)


# ---------------------------------------------------------------------------
# RateLimitState dataclass


@dataclass(frozen=True)
class RateLimitState:
    """Decoded view of one HTTP response's rate-limit envelope.

    Fields:
        limit: server-declared quota in this window (None when
            neither header family is present).
        remaining: requests remaining in this window. None means
            unknown.
        reset_at: absolute datetime when the window resets, in UTC.
            None when the server didn't supply any reset signal.
        retry_after_seconds: explicit delay-until-retry from the
            :data:`RETRY_AFTER` header. None on non-429 responses
            without a server-supplied retry hint.
        parsed_from: ordered tuple of header-family names that
            contributed to the parsed state, in priority order.
            Useful for debug logging.
        observed_at: when the headers were parsed; used for
            recomputing :meth:`time_to_reset` later in the same
            chain step.
    """

    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_at: Optional[datetime] = None
    retry_after_seconds: Optional[float] = None
    parsed_from: tuple[str, ...] = ()
    observed_at: Optional[datetime] = None

    @property
    def is_exhausted(self) -> bool:
        """True when remaining quota is known and zero.

        Used by chain drivers to fail-forward to the next provider
        before issuing a request the server will reject.
        """
        return self.remaining is not None and self.remaining <= 0

    def time_to_reset(self, *, now: Optional[datetime] = None) -> Optional[float]:
        """Return seconds-until-reset given the current ``now``.

        Returns None when no reset signal was parsed. ``now``
        defaults to :func:`datetime.datetime.now` in UTC. Clamped
        to a minimum of 0.0 (never returns negative).
        """
        if self.reset_at is None:
            return None
        reference = now or datetime.now(timezone.utc)
        delay = self.reset_at.timestamp() - reference.timestamp()
        return max(0.0, delay)

    def server_supplied_retry(self) -> Optional[float]:
        """Return the most-trusted server-supplied retry delay (seconds).

        Preferred-fallback order matches the upstream contract:
        :data:`RETRY_AFTER` first, then :meth:`time_to_reset`. Returns
        None when neither was parsed.
        """
        if self.retry_after_seconds is not None:
            return self.retry_after_seconds
        return self.time_to_reset()


def parse_rate_limit_headers(
    headers: Mapping[str, object],
    *,
    now: Optional[datetime] = None,
) -> Optional[RateLimitState]:
    """Return the parsed :class:`RateLimitState` for ``headers``, or None.

    Returns None when none of the seven recognised headers are
    present (so callers can short-circuit when the server doesn't
    advertise quotas).

    The parser follows the documented preferred-fallback order for
    the retry delay:

    1. Prefer :data:`RETRY_AFTER` when present.
    2. Otherwise compute delay from :data:`RATELIMIT_RESET` (relative
       seconds).
    3. Otherwise compute delay from :data:`X_RATELIMIT_RESET`
       (absolute epoch).

    For the quota counters, prefer the standardised :data:`RATELIMIT_LIMIT`
    / :data:`RATELIMIT_REMAINING` headers over the legacy
    :data:`X_RATELIMIT_LIMIT` / :data:`X_RATELIMIT_REMAINING` (the
    standard headers are explicit about their semantics; the legacy
    headers may diverge in some implementations).

    ``now`` may be supplied for deterministic tests.
    """
    reference = now or datetime.now(timezone.utc)
    folded = _normalize_headers(headers)

    standard_limit = _to_int(folded.get(RATELIMIT_LIMIT.casefold()))
    legacy_limit = _to_int(folded.get(X_RATELIMIT_LIMIT.casefold()))
    standard_remaining = _to_int(folded.get(RATELIMIT_REMAINING.casefold()))
    legacy_remaining = _to_int(folded.get(X_RATELIMIT_REMAINING.casefold()))

    raw_retry_after = folded.get(RETRY_AFTER.casefold())
    raw_standard_reset = folded.get(RATELIMIT_RESET.casefold())
    raw_legacy_reset = folded.get(X_RATELIMIT_RESET.casefold())

    parsed_from: list[str] = []
    retry_after_seconds: Optional[float] = None
    delay: Optional[float] = None

    if raw_retry_after:
        retry_after_seconds = parse_retry_after(raw_retry_after, now=reference)
        if retry_after_seconds is not None:
            parsed_from.append(RETRY_AFTER)
            delay = retry_after_seconds

    if delay is None and raw_standard_reset:
        candidate = _delay_from_reset(
            raw_standard_reset, absolute=False, now=reference
        )
        if candidate is not None:
            parsed_from.append(RATELIMIT_RESET)
            delay = candidate

    if delay is None and raw_legacy_reset:
        candidate = _delay_from_reset(
            raw_legacy_reset, absolute=True, now=reference
        )
        if candidate is not None:
            parsed_from.append(X_RATELIMIT_RESET)
            delay = candidate

    limit = standard_limit if standard_limit is not None else legacy_limit
    if standard_limit is not None:
        parsed_from.append(RATELIMIT_LIMIT)
    elif legacy_limit is not None:
        parsed_from.append(X_RATELIMIT_LIMIT)

    remaining = (
        standard_remaining if standard_remaining is not None else legacy_remaining
    )
    if standard_remaining is not None:
        parsed_from.append(RATELIMIT_REMAINING)
    elif legacy_remaining is not None:
        parsed_from.append(X_RATELIMIT_REMAINING)

    if not parsed_from:
        return None

    reset_at: Optional[datetime] = None
    if delay is not None:
        reset_at = datetime.fromtimestamp(
            reference.timestamp() + delay, tz=timezone.utc
        )

    return RateLimitState(
        limit=limit,
        remaining=remaining,
        reset_at=reset_at,
        retry_after_seconds=retry_after_seconds,
        parsed_from=tuple(parsed_from),
        observed_at=reference,
    )


# ---------------------------------------------------------------------------
# Backoff computation


@dataclass(frozen=True)
class BackoffConfig:
    """Tunable parameters for :func:`compute_backoff`."""

    base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS
    cap_seconds: float = DEFAULT_BACKOFF_CAP_SECONDS
    jitter_seconds: float = DEFAULT_BACKOFF_JITTER_SECONDS

    def __post_init__(self) -> None:
        if self.base_seconds < 0:
            raise ValueError("base_seconds must be >= 0")
        if self.cap_seconds < self.base_seconds:
            raise ValueError("cap_seconds must be >= base_seconds")
        if self.jitter_seconds < 0:
            raise ValueError("jitter_seconds must be >= 0")


DEFAULT_BACKOFF_CONFIG: BackoffConfig = BackoffConfig()


def compute_backoff(
    state: Optional[RateLimitState],
    *,
    attempt: int,
    config: BackoffConfig = DEFAULT_BACKOFF_CONFIG,
    rng: Optional[random.Random] = None,
) -> float:
    """Return the delay (seconds) before the next attempt.

    Preference order:

    1. If ``state`` has a server-supplied retry delay (via
       :meth:`RateLimitState.server_supplied_retry`), use it plus a
       small jitter to avoid thundering herd.
    2. Otherwise compute exponential backoff:
       ``min(cap, base * 2^(attempt-1))`` plus jitter.

    ``attempt`` is 1-indexed (first retry = ``attempt=1``). Values
    below 1 are treated as 1.

    ``rng`` may be supplied for deterministic tests; defaults to the
    module-level :class:`random.Random` instance.
    """
    actual_rng = rng or _DEFAULT_RNG
    n = max(1, int(attempt))
    jitter = (
        actual_rng.uniform(0.0, config.jitter_seconds)
        if config.jitter_seconds > 0
        else 0.0
    )

    if state is not None:
        server_hint = state.server_supplied_retry()
        if server_hint is not None:
            return max(0.0, server_hint + jitter)

    deterministic = min(config.cap_seconds, config.base_seconds * (2 ** (n - 1)))
    return max(0.0, deterministic + jitter)


def sleep_for_backoff(
    state: Optional[RateLimitState],
    *,
    attempt: int,
    config: BackoffConfig = DEFAULT_BACKOFF_CONFIG,
    sleeper: Optional["object"] = None,
    rng: Optional[random.Random] = None,
) -> float:
    """Compute backoff via :func:`compute_backoff` and sleep that long.

    ``sleeper`` is the callable that performs the actual sleep.
    Defaults to :func:`time.sleep`. Supplying an alternative lets
    tests run instantly: pass ``lambda _seconds: None`` to skip the
    delay while still recording the requested duration.

    Returns the computed delay in seconds (so callers can log or
    audit the backoff length).
    """
    delay = compute_backoff(state, attempt=attempt, config=config, rng=rng)
    actual_sleeper = sleeper or time.sleep
    actual_sleeper(delay)
    return delay


# ---------------------------------------------------------------------------
# Per-provider tracker (chain integration)


class RateLimitTracker:
    """Per-provider rate-limit state cache.

    The chain driver wires one tracker per provider id; each successful
    response updates the tracker via :meth:`record`, and the chain
    consults :meth:`should_skip` before issuing a request to a provider
    that's still cooling down. Decoupled from the provider client so
    the same tracker shape works for any HTTP-talking provider.

    Thread-safe via an internal :class:`threading.RLock`.
    """

    def __init__(self, *, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        import threading

        self._lock = threading.RLock()
        self._states: dict[str, RateLimitState] = {}
        self._cooldowns: dict[str, datetime] = {}
        self._consecutive_429: dict[str, int] = {}
        self.max_retries = max_retries

    def record(
        self,
        provider_id: str,
        state: Optional[RateLimitState],
        *,
        was_429: bool = False,
        now: Optional[datetime] = None,
    ) -> None:
        """Record the parsed envelope for ``provider_id``.

        When ``was_429`` is True the cooldown window is set to the
        server-supplied retry hint (or, when absent, the next
        exponential-backoff slot). Otherwise the consecutive-429
        counter is reset.
        """
        reference = now or datetime.now(timezone.utc)
        with self._lock:
            if state is not None:
                self._states[provider_id] = state
            if was_429:
                self._consecutive_429[provider_id] = (
                    self._consecutive_429.get(provider_id, 0) + 1
                )
                hint = (
                    state.server_supplied_retry() if state is not None else None
                )
                if hint is None:
                    hint = compute_backoff(
                        state,
                        attempt=self._consecutive_429[provider_id],
                    )
                self._cooldowns[provider_id] = datetime.fromtimestamp(
                    reference.timestamp() + max(0.0, hint),
                    tz=timezone.utc,
                )
            else:
                self._consecutive_429.pop(provider_id, None)
                self._cooldowns.pop(provider_id, None)

    def should_skip(
        self,
        provider_id: str,
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        """Return True when ``provider_id`` is still in cooldown.

        A provider stays in cooldown until: (a) the recorded
        :data:`RateLimitState.reset_at` has passed; OR (b) the
        consecutive-429 counter has rolled over the
        :attr:`max_retries` budget AND the cooldown is still in the
        future. A provider that's never been used (no record) returns
        False (let the chain try it).
        """
        reference = now or datetime.now(timezone.utc)
        with self._lock:
            cooldown_until = self._cooldowns.get(provider_id)
            if cooldown_until is None:
                state = self._states.get(provider_id)
                if state is None:
                    return False
                if state.is_exhausted:
                    reset_at = state.reset_at
                    if reset_at is None:
                        return False
                    return reset_at > reference
                return False
            if cooldown_until <= reference:
                self._cooldowns.pop(provider_id, None)
                self._consecutive_429.pop(provider_id, None)
                return False
            return True

    def consecutive_429(self, provider_id: str) -> int:
        """Return the consecutive-429 counter for ``provider_id``."""
        with self._lock:
            return self._consecutive_429.get(provider_id, 0)

    def state(self, provider_id: str) -> Optional[RateLimitState]:
        """Return the last recorded state for ``provider_id`` (or None)."""
        with self._lock:
            return self._states.get(provider_id)

    def reset(self, provider_id: Optional[str] = None) -> None:
        """Clear tracker state.

        Pass an explicit ``provider_id`` to clear a single entry, or
        omit it to clear everything (used by tests).
        """
        with self._lock:
            if provider_id is None:
                self._states.clear()
                self._cooldowns.clear()
                self._consecutive_429.clear()
                return
            self._states.pop(provider_id, None)
            self._cooldowns.pop(provider_id, None)
            self._consecutive_429.pop(provider_id, None)

    def known_providers(self) -> tuple[str, ...]:
        """Return the set of provider ids the tracker has seen."""
        with self._lock:
            seen = set(self._states.keys()) | set(self._cooldowns.keys())
            return tuple(sorted(seen))


# ---------------------------------------------------------------------------
# Module singletons


_DEFAULT_RNG = random.Random()
_GLOBAL_TRACKER: Optional[RateLimitTracker] = None


def get_global_tracker() -> RateLimitTracker:
    """Return the process-wide :class:`RateLimitTracker` singleton.

    Used by the web-search provider chain so a 429 from one logical
    operation poisons the provider's cooldown for the next operation
    as well, preventing a thundering retry storm.
    """
    global _GLOBAL_TRACKER
    if _GLOBAL_TRACKER is None:
        _GLOBAL_TRACKER = RateLimitTracker()
    return _GLOBAL_TRACKER


def reset_global_tracker_for_testing() -> None:
    """Test helper: drop the global tracker so the next call rebuilds it."""
    global _GLOBAL_TRACKER
    _GLOBAL_TRACKER = None


__all__ = [
    "X_RATELIMIT_LIMIT",
    "X_RATELIMIT_REMAINING",
    "X_RATELIMIT_RESET",
    "RATELIMIT_LIMIT",
    "RATELIMIT_REMAINING",
    "RATELIMIT_RESET",
    "RETRY_AFTER",
    "RETRY_AFTER_EPOCH_THRESHOLD_SECONDS",
    "DEFAULT_BACKOFF_BASE_SECONDS",
    "DEFAULT_BACKOFF_CAP_SECONDS",
    "DEFAULT_BACKOFF_JITTER_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "BackoffConfig",
    "DEFAULT_BACKOFF_CONFIG",
    "RateLimitState",
    "RateLimitTracker",
    "parse_retry_after",
    "parse_rate_limit_headers",
    "compute_backoff",
    "sleep_for_backoff",
    "get_global_tracker",
    "reset_global_tracker_for_testing",
]


def known_header_names() -> Iterable[str]:
    """Return all seven recognised rate-limit header names (in canonical case).

    Useful for tests + debugging code that wants to filter a response
    headers dict to just the rate-limit envelope.
    """
    return (
        X_RATELIMIT_LIMIT,
        X_RATELIMIT_REMAINING,
        X_RATELIMIT_RESET,
        RATELIMIT_LIMIT,
        RATELIMIT_REMAINING,
        RATELIMIT_RESET,
        RETRY_AFTER,
    )
