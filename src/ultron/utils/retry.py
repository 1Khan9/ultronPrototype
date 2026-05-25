"""Async-friendly retry decorator with exponential backoff and retry-after parsing.

Adapted from cline's ``withRetry`` decorator pattern (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Ultron's variant adds:

* Native ``async def`` and ``async def *`` (async generator) decoration.
* Sync ``def`` decoration via a separate decorator entry point.
* Optional ``asyncio.CancelledError`` pass-through so a cancellation
  during the backoff sleep does not eat the cancellation.
* A pluggable ``should_retry`` predicate for callers that need more than
  the default "HTTP-429-or-RetriableError" classification.
* A per-session retry-budget guard so a runaway provider can't drain
  the voice path of its TTFT budget.

The default exponential-backoff formula matches cline:

    delay_seconds = min(max_delay_s, base_delay_s * (2 ** attempt))

where ``attempt`` is zero-indexed (0 for the first retry, 1 for the
second, etc.). The retry-after header parsing uses the same
delta-seconds-vs-unix-timestamp heuristic ("if the integer value is
greater than the current unix time, treat as absolute timestamp").
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional, TypeVar

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

#: Default maximum attempts (initial + retries). Mirrors cline.
DEFAULT_MAX_ATTEMPTS: int = 3

#: Default base delay between retries (seconds).
DEFAULT_BASE_DELAY_S: float = 1.0

#: Default ceiling on a single backoff delay (seconds).
DEFAULT_MAX_DELAY_S: float = 10.0

#: Default per-session retry budget. Once exceeded, retries are skipped
#: and the exception propagates immediately. The budget is consumed by
#: the SLEEP time of the retries, not the call time itself.
DEFAULT_SESSION_BUDGET_S: float = 30.0

#: Header names checked for a retry-after value, in priority order.
_RETRY_AFTER_HEADER_KEYS: tuple[str, ...] = (
    "retry-after",
    "x-ratelimit-reset",
    "ratelimit-reset",
)


class RetriableError(Exception):
    """Mark an exception as retryable even when ``retry_all`` is False.

    Attributes:
        status: optional HTTP-like status code (defaults to 429 for
            rate-limit semantics).
        retry_after: optional retry-after hint (seconds OR unix-timestamp
            integer; the decoder applies the same heuristic as the
            header parser).
        headers: optional header mapping the decoder will probe for
            retry-after entries.
    """

    def __init__(
        self,
        message: str = "retryable failure",
        *,
        status: int = 429,
        retry_after: Optional[float] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.headers = dict(headers) if headers else {}


@dataclass(frozen=True)
class RetryAttempt:
    """Per-attempt diagnostic record passed to the on_retry callback."""

    attempt: int
    max_attempts: int
    delay_seconds: float
    error: BaseException
    error_class: str
    label: str = ""


@dataclass
class RetryBudget:
    """Per-session retry-budget tracker shared across decorated calls."""

    limit_seconds: float = DEFAULT_SESSION_BUDGET_S
    spent_seconds: float = 0.0
    triggered_at: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        """Seconds remaining before further retries are denied."""
        return max(0.0, self.limit_seconds - self.spent_seconds)

    def charge(self, seconds: float) -> None:
        """Record ``seconds`` of retry-sleep against the budget."""
        if seconds > 0:
            self.spent_seconds += seconds

    def reset(self) -> None:
        """Reset the budget for a new session."""
        self.spent_seconds = 0.0
        self.triggered_at = time.monotonic()


def parse_retry_after(value: str, *, now_unix: Optional[float] = None) -> Optional[float]:
    """Parse a retry-after header value into seconds-until-retry.

    Args:
        value: header value (delta-seconds integer or unix-timestamp seconds).
        now_unix: optional explicit current unix time for tests; defaults
            to :func:`time.time`.

    Returns:
        Seconds to wait, or None when the value cannot be parsed.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        as_float = float(text)
    except ValueError:
        return None
    if as_float < 0:
        return None
    now = now_unix if now_unix is not None else time.time()
    # Heuristic: if the value comfortably exceeds the current unix time,
    # treat it as an absolute timestamp; otherwise treat as delta-seconds.
    if as_float > now:
        return max(0.0, as_float - now)
    return as_float


def _extract_retry_after_from_exception(error: BaseException) -> Optional[float]:
    """Best-effort pull of a retry-after hint from an arbitrary exception."""
    # Explicit attribute (works for RetriableError, openai SDK, anthropic SDK).
    candidate = getattr(error, "retry_after", None)
    if candidate is not None:
        parsed = parse_retry_after(str(candidate))
        if parsed is not None:
            return parsed
    headers = getattr(error, "headers", None) or getattr(error, "response_headers", None)
    if isinstance(headers, Mapping):
        for key in _RETRY_AFTER_HEADER_KEYS:
            # Case-insensitive lookup.
            for header_name, header_value in headers.items():
                if header_name.lower() == key:
                    parsed = parse_retry_after(str(header_value))
                    if parsed is not None:
                        return parsed
    response = getattr(error, "response", None)
    if response is not None and isinstance(getattr(response, "headers", None), Mapping):
        for key in _RETRY_AFTER_HEADER_KEYS:
            for header_name, header_value in response.headers.items():
                if header_name.lower() == key:
                    parsed = parse_retry_after(str(header_value))
                    if parsed is not None:
                        return parsed
    return None


def _is_rate_limit(error: BaseException) -> bool:
    """Detect HTTP-429 semantics across common SDK shapes."""
    if isinstance(error, RetriableError):
        return True
    status = getattr(error, "status", None) or getattr(error, "status_code", None)
    if status == 429:
        return True
    response = getattr(error, "response", None)
    if response is not None and getattr(response, "status_code", None) == 429:
        return True
    return False


def _default_should_retry(error: BaseException) -> bool:
    """Default retry classifier — 429s + :class:`RetriableError`."""
    return _is_rate_limit(error) or isinstance(error, RetriableError)


def _backoff_seconds(
    attempt: int,
    base_delay_s: float,
    max_delay_s: float,
    *,
    jitter: float = 0.0,
) -> float:
    """Compute the next backoff sleep in seconds.

    Args:
        attempt: zero-indexed retry attempt.
        base_delay_s: starting delay for the geometric progression.
        max_delay_s: ceiling on the result.
        jitter: optional fractional jitter (0.0-1.0). When > 0 the result
            is multiplied by ``random.uniform(1 - jitter, 1 + jitter)``.

    Returns:
        Sleep time in seconds (non-negative, never NaN, capped).
    """
    if attempt < 0:
        attempt = 0
    raw = base_delay_s * (2 ** attempt)
    capped = min(max_delay_s, raw)
    if jitter > 0:
        spread = max(0.0, min(1.0, jitter))
        capped *= random.uniform(1.0 - spread, 1.0 + spread)
    return max(0.0, capped)


def _resolve_callback(
    fn: Optional[Callable[..., Any]],
) -> Callable[[RetryAttempt], Awaitable[None] | None]:
    """Wrap an optional callback so call sites can fire-and-forget."""

    if fn is None:
        async def _noop(_: RetryAttempt) -> None:
            return None
        return _noop

    async def _invoke(attempt: RetryAttempt) -> None:
        try:
            result = fn(attempt)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - telemetry callback never breaks the call
            LOGGER.warning(
                "on_retry callback raised for %s (attempt %d/%d)",
                attempt.error_class,
                attempt.attempt,
                attempt.max_attempts,
                exc_info=True,
            )

    return _invoke


def with_retry(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    retry_all: bool = False,
    should_retry: Optional[Callable[[BaseException], bool]] = None,
    on_retry: Optional[Callable[[RetryAttempt], Any]] = None,
    budget: Optional[RetryBudget] = None,
    jitter: float = 0.0,
    label: str = "",
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorate an async coroutine or async generator with retry semantics.

    Args:
        max_attempts: total attempts (initial + retries). Must be >= 1.
        base_delay_s: starting delay (seconds) for exponential backoff.
        max_delay_s: ceiling on a single backoff (seconds).
        retry_all: when True, retry on every exception (except
            ``asyncio.CancelledError``). Default: False (only 429s +
            :class:`RetriableError`).
        should_retry: optional classifier overriding both ``retry_all``
            and the default 429-aware predicate.
        on_retry: optional callback receiving a :class:`RetryAttempt`
            record; may be sync or async.
        budget: optional :class:`RetryBudget` shared across calls; once
            exhausted the decorator stops retrying and propagates the
            exception even if attempts remain.
        jitter: optional fractional jitter (0-1) applied to each backoff.
        label: optional label injected into log lines and the
            :class:`RetryAttempt` record.

    Returns:
        A decorator producing the wrapped coroutine or async generator.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay_s < 0 or max_delay_s < 0:
        raise ValueError("delay configuration must be non-negative")

    classifier = should_retry or (
        (lambda _err: True) if retry_all else _default_should_retry
    )
    callback = _resolve_callback(on_retry)

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        if inspect.isasyncgenfunction(func):
            @functools.wraps(func)
            async def async_gen_wrapper(*args: Any, **kwargs: Any):
                attempt_index = 0
                while True:
                    try:
                        async for item in func(*args, **kwargs):
                            yield item
                        return
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:  # noqa: BLE001
                        await _maybe_sleep_or_raise(
                            exc,
                            attempt_index,
                            max_attempts,
                            base_delay_s,
                            max_delay_s,
                            classifier,
                            callback,
                            budget,
                            jitter,
                            label or func.__qualname__,
                        )
                        attempt_index += 1
            return async_gen_wrapper

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def coro_wrapper(*args: Any, **kwargs: Any) -> T:
                attempt_index = 0
                while True:
                    try:
                        return await func(*args, **kwargs)
                    except asyncio.CancelledError:
                        raise
                    except BaseException as exc:  # noqa: BLE001
                        await _maybe_sleep_or_raise(
                            exc,
                            attempt_index,
                            max_attempts,
                            base_delay_s,
                            max_delay_s,
                            classifier,
                            callback,
                            budget,
                            jitter,
                            label or func.__qualname__,
                        )
                        attempt_index += 1
            return coro_wrapper

        raise TypeError(
            "with_retry decorates async functions / generators only; use "
            "with_retry_sync for synchronous callables."
        )

    return decorator


def with_retry_sync(
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    retry_all: bool = False,
    should_retry: Optional[Callable[[BaseException], bool]] = None,
    on_retry: Optional[Callable[[RetryAttempt], None]] = None,
    budget: Optional[RetryBudget] = None,
    jitter: float = 0.0,
    label: str = "",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Synchronous twin of :func:`with_retry`.

    Suitable for blocking call sites (web-search clients, subprocess
    invocations). The contract mirrors :func:`with_retry` exactly except
    callbacks must be sync.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay_s < 0 or max_delay_s < 0:
        raise ValueError("delay configuration must be non-negative")

    classifier = should_retry or (
        (lambda _err: True) if retry_all else _default_should_retry
    )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt_index = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except BaseException as exc:  # noqa: BLE001
                    if attempt_index >= max_attempts - 1 or not classifier(exc):
                        raise
                    delay = _extract_retry_after_from_exception(exc)
                    if delay is None:
                        delay = _backoff_seconds(
                            attempt_index, base_delay_s, max_delay_s, jitter=jitter,
                        )
                    delay = min(delay, max_delay_s)
                    if budget is not None:
                        remaining = budget.remaining()
                        if remaining <= 0:
                            raise
                        delay = min(delay, remaining)
                        budget.charge(delay)
                    record = RetryAttempt(
                        attempt=attempt_index + 1,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        error=exc,
                        error_class=type(exc).__name__,
                        label=label or func.__qualname__,
                    )
                    if on_retry is not None:
                        try:
                            on_retry(record)
                        except Exception:  # noqa: BLE001
                            LOGGER.warning(
                                "sync on_retry callback raised for %s",
                                type(exc).__name__,
                                exc_info=True,
                            )
                    if delay > 0:
                        time.sleep(delay)
                    attempt_index += 1
        return wrapper

    return decorator


async def _maybe_sleep_or_raise(
    exc: BaseException,
    attempt_index: int,
    max_attempts: int,
    base_delay_s: float,
    max_delay_s: float,
    classifier: Callable[[BaseException], bool],
    callback: Callable[[RetryAttempt], Awaitable[None]],
    budget: Optional[RetryBudget],
    jitter: float,
    label: str,
) -> None:
    """Decide between sleeping for the next retry or re-raising the error.

    Raises:
        BaseException: re-raises the original error when retries are
            exhausted, the classifier denies retry, or the session budget
            is empty.
    """
    if attempt_index >= max_attempts - 1:
        raise exc
    if not classifier(exc):
        raise exc
    delay = _extract_retry_after_from_exception(exc)
    if delay is None:
        delay = _backoff_seconds(attempt_index, base_delay_s, max_delay_s, jitter=jitter)
    delay = min(delay, max_delay_s)
    if budget is not None:
        remaining = budget.remaining()
        if remaining <= 0:
            raise exc
        delay = min(delay, remaining)
        budget.charge(delay)
    record = RetryAttempt(
        attempt=attempt_index + 1,
        max_attempts=max_attempts,
        delay_seconds=delay,
        error=exc,
        error_class=type(exc).__name__,
        label=label,
    )
    await callback(record)
    if delay > 0:
        await asyncio.sleep(delay)


def retry_iterable_keys(headers: Mapping[str, str]) -> Iterable[tuple[str, str]]:
    """Yield ``(canonical_key, value)`` pairs for retry-after extraction.

    Useful in callers that have a custom header bag and want to perform
    the same case-insensitive priority lookup the decorator uses.
    """
    if not headers:
        return
    lowered = {k.lower(): v for k, v in headers.items()}
    for key in _RETRY_AFTER_HEADER_KEYS:
        if key in lowered:
            yield key, lowered[key]


__all__ = [
    "DEFAULT_BASE_DELAY_S",
    "DEFAULT_MAX_ATTEMPTS",
    "DEFAULT_MAX_DELAY_S",
    "DEFAULT_SESSION_BUDGET_S",
    "RetriableError",
    "RetryAttempt",
    "RetryBudget",
    "parse_retry_after",
    "retry_iterable_keys",
    "with_retry",
    "with_retry_sync",
]
