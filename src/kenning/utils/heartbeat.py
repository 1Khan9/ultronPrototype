"""Daemon-thread keep-alive heartbeat for long-lived connections.

Catalog 11 (clawhub-browser-agent) T2 -- generic clean-room
re-implementation.

The upstream plugin's ``session_manager.py`` keeps a Chrome DevTools
Protocol WebSocket alive by spawning a daemon thread that sends a cheap
no-op (``Runtime.evaluate "1"``) every 60 s so the remote end's idle
timeout never fires during a long-running task. This module generalises
that pattern into a reusable, stoppable, fail-open primitive usable for
ANY long-lived connection kenning holds open: the ``browser-use`` CLI
daemon, the Parakeet STT HTTP server, the OpenClaw bridge -- anything
with a server-side idle timeout that differs from the caller's
expectation.

Improvements over the upstream ``while True: time.sleep(interval)``:

* **Stoppable.** The upstream had no stop path -- it relied solely on
  ``daemon=True`` + process exit, so a heartbeat could not be torn down
  mid-process (e.g. when the orchestrator swaps engines on gaming-mode
  engage). This implementation waits on a :class:`threading.Event`, so
  :meth:`HeartbeatThread.stop` returns the loop immediately even mid
  interval and joins the thread cleanly. Required by the test-sweep
  binding rules (R2 thread cleanup, R12 no bare ``time.sleep`` polling).
* **Fail-open.** A raised exception from the keep-alive target never
  escapes the loop: it is counted, recorded, optionally forwarded to an
  ``on_error`` callback, and the loop continues. A keep-alive that
  starts failing must NEVER crash the subsystem it is protecting.
* **Observable.** :meth:`HeartbeatThread.stats` returns a frozen
  snapshot (beats sent, errors, last error) for the fail-open
  dashboard / "are my long-lived connections healthy?" introspection.
* **Injectable clock** so jitter / timing accounting stays testable
  without real sleeps.

Each consumer owns its own :class:`HeartbeatThread`; there is no module
singleton (unlike the desktop tools) because a heartbeat is bound to a
specific connection's lifetime, not to the process.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from kenning.utils.logging import get_logger

logger = get_logger("utils.heartbeat")


# Default keep-alive interval. Matches the upstream plugin's 60 s CDP
# keep-alive. Latency-sensitive consumers (the Parakeet STT server)
# override with a shorter interval at construction time.
DEFAULT_HEARTBEAT_INTERVAL_S: float = 60.0

# Default join timeout when stopping. Generous enough that an in-flight
# beat (a quick no-op round-trip) finishes before we give up waiting,
# small enough that shutdown never blocks perceptibly.
DEFAULT_STOP_TIMEOUT_S: float = 2.0


@dataclass(frozen=True)
class HeartbeatStats:
    """Immutable snapshot of a heartbeat's runtime counters.

    Attributes:
        running: True iff the worker thread is currently alive.
        beats_sent: count of successful target invocations since start.
        errors: count of target invocations that raised.
        last_error: ``repr`` of the most recent exception, or empty.
        started_at: monotonic timestamp captured at :meth:`start`, or
            0.0 when never started.
    """

    running: bool
    beats_sent: int
    errors: int
    last_error: str
    started_at: float


class HeartbeatThread:
    """A stoppable daemon thread that calls ``target`` every
    ``interval_s`` seconds.

    Construction does NOT start the thread -- call :meth:`start`. The
    instance is single-use in the sense that once :meth:`stop` has run,
    :meth:`start` will spawn a fresh worker (the stop event is cleared on
    each start), so a heartbeat can be paused + resumed.

    Args:
        target: zero-argument callable invoked on each beat. Should be
            cheap + idempotent (a no-op liveness ping). Its return value
            is ignored. Exceptions are caught and counted, never
            propagated.
        interval_s: seconds between beats. Must be positive.
        name: thread name (also used as the log label).
        on_error: optional callback invoked with the exception when a
            beat raises. Exceptions from ``on_error`` itself are
            swallowed (a broken error handler must not break the loop).
        run_immediately: when True, fire one beat as soon as the worker
            starts, before the first interval wait. Default False so the
            first beat lands one interval after start (matching the
            upstream's ``sleep`` then ``ping`` ordering).
        clock: monotonic time source; injectable for tests.
    """

    def __init__(
        self,
        target: Callable[[], Any],
        *,
        interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
        name: str = "heartbeat",
        on_error: Optional[Callable[[BaseException], None]] = None,
        run_immediately: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_s <= 0:
            raise ValueError(f"interval_s must be positive, got {interval_s!r}")
        self._target = target
        self._interval_s = float(interval_s)
        self._name = name or "heartbeat"
        self._on_error = on_error
        self._run_immediately = bool(run_immediately)
        self._clock = clock

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._beats_sent = 0
        self._errors = 0
        self._last_error = ""
        self._started_at = 0.0

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        """Start the worker thread. Idempotent while already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._started_at = self._clock()
            self._thread = threading.Thread(
                target=self._loop,
                name=self._name,
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout: float = DEFAULT_STOP_TIMEOUT_S) -> None:
        """Signal the worker to stop and join it.

        Idempotent: safe to call when never started or already stopped.
        The :class:`threading.Event` wait returns immediately so an
        in-progress interval does not delay shutdown beyond one
        in-flight beat.
        """
        self._stop.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        with self._lock:
            # Only clear the handle if the thread actually died -- a
            # join timeout (target wedged) leaves it referenced so a
            # later stats() still reports running=True honestly.
            if self._thread is not None and not self._thread.is_alive():
                self._thread = None

    def is_alive(self) -> bool:
        """True iff the worker thread is currently running."""
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def stats(self) -> HeartbeatStats:
        """Return an immutable snapshot of the runtime counters."""
        with self._lock:
            return HeartbeatStats(
                running=self._thread is not None and self._thread.is_alive(),
                beats_sent=self._beats_sent,
                errors=self._errors,
                last_error=self._last_error,
                started_at=self._started_at,
            )

    # -- worker --------------------------------------------------------

    def _loop(self) -> None:
        """Worker body: optional immediate beat, then beat-per-interval
        until the stop event is set."""
        if self._run_immediately:
            self._beat()
        # ``Event.wait`` returns True when the event is set (stop
        # requested) and False on timeout (interval elapsed -> beat).
        while not self._stop.wait(self._interval_s):
            self._beat()

    def _beat(self) -> None:
        """Invoke the target once, counting success / failure. Never
        raises."""
        try:
            self._target()
        except BaseException as exc:  # noqa: BLE001 -- keep-alive must never crash the caller
            with self._lock:
                self._errors += 1
                self._last_error = repr(exc)
            logger.debug("heartbeat %r target raised: %s", self._name, exc)
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except Exception as cb_exc:  # noqa: BLE001 -- broken handler must not break the loop
                    logger.debug(
                        "heartbeat %r on_error callback raised: %s",
                        self._name,
                        cb_exc,
                    )
            return
        with self._lock:
            self._beats_sent += 1


__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL_S",
    "DEFAULT_STOP_TIMEOUT_S",
    "HeartbeatStats",
    "HeartbeatThread",
]
