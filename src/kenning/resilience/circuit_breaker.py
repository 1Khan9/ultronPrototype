"""Phase 4 — circuit breaker.

Standard three-state breaker:

    CLOSED  → calls flow through; failures count up.
    OPEN    → calls fail fast with CircuitOpenError; cooldown timer runs.
    HALF_OPEN → first call after cooldown is a probe; success closes,
              failure reopens.

Designed for the external-dependency wrappers (Brave, Jina, Anthropic,
Ollama-future). Attach one breaker per dependency. Per-call timeouts
are the wrapper's responsibility, not the breaker's.

Thread-safe via a single internal lock. Counters reset on transitions
and on the rolling failure window.

Usage::

    from ultron.resilience import CircuitBreaker, CircuitOpenError

    brave_breaker = CircuitBreaker(
        name="brave",
        failure_threshold=3,
        window_seconds=300,
        cooldown_seconds=300,
    )

    def search(query):
        try:
            return brave_breaker.call(_real_brave_call, query)
        except CircuitOpenError:
            # short-circuit; fall back to base knowledge
            return None
        except BraveAPIError:
            return None  # already counted as failure by call()
"""

from __future__ import annotations

import threading
import time
from collections import deque
from enum import Enum
from typing import Callable, Deque, TypeVar

from ultron.utils.logging import get_logger

logger = get_logger("resilience.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised by :meth:`CircuitBreaker.call` when the circuit is OPEN.

    Distinct from the dependency's own typed errors so callers can
    differentiate "we tried and the API failed" from "we didn't even
    try because the breaker is tripped".
    """

    def __init__(self, breaker_name: str, opened_at: float, cooldown_seconds: float):
        self.breaker_name = breaker_name
        self.opened_at = opened_at
        self.cooldown_seconds = cooldown_seconds
        remaining = max(0.0, cooldown_seconds - (time.monotonic() - opened_at))
        super().__init__(
            f"circuit '{breaker_name}' is open "
            f"(cooldown: {remaining:.0f}s remaining)"
        )


T = TypeVar("T")


class CircuitBreaker:
    """Per-dependency failure aggregator.

    Args:
        name: identifier for logs (e.g. ``"brave"``, ``"jina"``).
        failure_threshold: failures within ``window_seconds`` to trip OPEN.
        window_seconds: rolling window for the failure counter.
        cooldown_seconds: how long OPEN lasts before HALF_OPEN.
        expected_exceptions: tuple of exception types that count as
            failures. Other exceptions propagate unchanged WITHOUT
            counting (so a programming bug doesn't trip the breaker).
            Default: ``(Exception,)`` — count everything.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        window_seconds: float = 300.0,
        cooldown_seconds: float = 300.0,
        expected_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if window_seconds <= 0 or cooldown_seconds <= 0:
            raise ValueError("window_seconds and cooldown_seconds must be > 0")

        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = float(window_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self.expected_exceptions = expected_exceptions

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0
        # Rolling list of recent failure timestamps within window.
        self._failures: Deque[float] = deque()

    # --- introspection -----------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    @property
    def failure_count(self) -> int:
        """Number of failures within the rolling window."""
        with self._lock:
            self._evict_old_failures()
            return len(self._failures)

    def reset(self) -> None:
        """Force the breaker back to CLOSED with empty failure window.
        Test-only / operator-only."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures.clear()
            self._opened_at = 0.0

    # --- main entry --------------------------------------------------------

    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute ``func`` through the breaker.

        Raises:
            CircuitOpenError: breaker is OPEN, call did not run.
            anything ``func`` raises: propagates after counting (if it
                matches ``expected_exceptions``).
        """
        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    self.name, self._opened_at, self.cooldown_seconds,
                )
            # Both CLOSED and HALF_OPEN allow the call through; HALF_OPEN
            # treats it as a probe.
            in_half_open = self._state == CircuitState.HALF_OPEN

        try:
            result = func(*args, **kwargs)
        except BaseException as e:  # noqa: BLE001 — we re-raise after bookkeeping
            counted = isinstance(e, self.expected_exceptions)
            if counted:
                self._record_failure()
            raise
        else:
            # Success path. HALF_OPEN probe success closes the circuit.
            if in_half_open:
                self._close_after_probe()
            return result

    # --- internal: state transitions --------------------------------------

    def _evict_old_failures(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _record_failure(self) -> None:
        with self._lock:
            self._evict_old_failures()
            self._failures.append(time.monotonic())
            if (
                self._state == CircuitState.CLOSED
                and len(self._failures) >= self.failure_threshold
            ):
                self._open()
            elif self._state == CircuitState.HALF_OPEN:
                # Probe failed -> reopen
                self._open()

    def _open(self) -> None:
        prev = self._state
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        logger.warning(
            "circuit '%s' OPEN (transition: %s -> open; failures in window: %d, "
            "cooldown: %.0fs)",
            self.name, prev.value, len(self._failures), self.cooldown_seconds,
        )

    def _maybe_transition_to_half_open(self) -> None:
        # Caller holds lock.
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "circuit '%s' HALF_OPEN (cooldown elapsed; next call is a probe)",
                    self.name,
                )

    def _close_after_probe(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures.clear()
            self._opened_at = 0.0
            logger.info(
                "circuit '%s' CLOSED (probe succeeded; failure counter reset)",
                self.name,
            )


__all__ = ["CircuitBreaker", "CircuitOpenError", "CircuitState"]
