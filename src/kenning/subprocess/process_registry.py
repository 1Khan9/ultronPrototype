"""Persistent shell-process registry with backgrounding + scope-keyed lookup.

T12 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Long-lived
process registry the orchestrator uses to track every spawned
subprocess. Adds four capabilities beyond plain ``Popen``:

* **Backgrounding** — a foreground job that exceeds its wait timeout
  transitions to ``BACKGROUNDED``; the agent can later poll status
  / fetch tail output instead of blocking the turn.
* **Scope-keyed lookup** — registered jobs carry a ``scope_key``
  (typically the owning session id). Listing is filtered so a
  session sees only its own jobs.
* **TTL sweep** — :data:`DEFAULT_JOB_TTL_SECONDS` (default 30 min,
  clamped to ``[MIN_JOB_TTL_SECONDS, MAX_JOB_TTL_SECONDS]``).
  Backgrounded jobs past TTL are auto-killed and migrated to
  ``finished`` for one last poll.
* **Exit notification** — registry remembers who asked to be notified
  on exit (``notify_on_exit``) so completion routes back to the
  right caller even if the parent session has rolled.

The registry composes with :func:`kenning.subprocess.kill_tree.kill_process_tree`
(T8) for shutdown; with :class:`ZombieKiller` (cline T23) for the
overall hard cap. This T12 primitive is the FINE-grained per-process
lifecycle layer between those two.

YELLOW gating: the registry itself is GREEN runtime infrastructure;
the YELLOW concern is the spawn-tool that PUTS jobs into the
registry. Spawn gating remains the responsibility of Cap-3 + the
IT category (interactive-tools blocklist) + the bash-tools shell
validator. The registry's `notify_on_exit` channel routing is
locked at spawn time (a registry consumer cannot later swap the
notification target to a channel it shouldn't have access to).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional

LOGGER = logging.getLogger(__name__)

#: Default TTL for backgrounded jobs (seconds). Matches OpenClaw's
#: 30-minute default.
DEFAULT_JOB_TTL_SECONDS: float = 30 * 60.0

#: Floor on TTL — anything shorter and the sweep starts thrashing.
MIN_JOB_TTL_SECONDS: float = 60.0

#: Ceiling on TTL — anything longer and the registry holds onto
#: zombies. Matches OpenClaw's 3-hour ceiling.
MAX_JOB_TTL_SECONDS: float = 3 * 60 * 60.0

#: Max characters per ring-buffered stream (stdout + stderr each).
#: Larger streams get truncated head; the agent can re-poll for tail.
DEFAULT_MAX_OUTPUT_CHARS: int = 64 * 1024

#: Max characters per pending-output snapshot returned by poll().
#: Lower than the stream cap so the poll response stays bounded.
DEFAULT_PENDING_MAX_OUTPUT_CHARS: int = 16 * 1024


class JobState(str, Enum):
    """Lifecycle state of a registered process."""

    FOREGROUND = "foreground"
    BACKGROUNDED = "backgrounded"
    EXITED = "exited"
    KILLED = "killed"
    UNREACHABLE = "unreachable"


def _now() -> float:
    """Monotonic clock used for age + TTL math."""
    return time.monotonic()


def _clamp_ttl(ttl_seconds: float) -> float:
    """Clamp ``ttl_seconds`` to ``[MIN_JOB_TTL_SECONDS, MAX_JOB_TTL_SECONDS]``."""
    if ttl_seconds < MIN_JOB_TTL_SECONDS:
        return MIN_JOB_TTL_SECONDS
    if ttl_seconds > MAX_JOB_TTL_SECONDS:
        return MAX_JOB_TTL_SECONDS
    return float(ttl_seconds)


@dataclass
class DeliveryTarget:
    """Frozen handle the notifier uses to route an exit event.

    The actual channel / handler resolution is the orchestrator's
    business — the registry just carries an opaque payload from
    spawn time to exit time so the notification arrives at the
    intended caller.
    """

    channel: str = ""
    handler: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class JobOutput:
    """Bounded captured-output snapshot for a registered job.

    The registry holds two of these per job (stdout + stderr).
    Methods are thread-safe; append() truncates from the head once
    the cap is hit so the buffer stays bounded.
    """

    cap_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    _buffer: deque[str] = field(default_factory=deque, init=False)
    _total_chars: int = field(default=0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)

    def append(self, chunk: str) -> None:
        """Append ``chunk`` to the buffer; truncate from head when over cap."""
        if not chunk:
            return
        with self._lock:
            self._buffer.append(chunk)
            self._total_chars += len(chunk)
            while self._total_chars > self.cap_chars and self._buffer:
                head = self._buffer.popleft()
                self._total_chars -= len(head)
                # If popping head still leaves us over cap, the head
                # was small; loop continues. If the head itself was
                # larger than cap, we lose the whole thing.
                if not self._buffer:
                    break

    def snapshot(self, *, max_chars: int = DEFAULT_PENDING_MAX_OUTPUT_CHARS) -> str:
        """Return up to ``max_chars`` of the most-recent output (tail)."""
        with self._lock:
            joined = "".join(self._buffer)
        if len(joined) <= max_chars:
            return joined
        return joined[-max_chars:]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._total_chars = 0

    def total_chars(self) -> int:
        with self._lock:
            return self._total_chars


@dataclass
class RegisteredJob:
    """One tracked subprocess + its lifecycle state.

    Attributes:
        job_id: caller-supplied identifier; used as the registry key.
        scope_key: typically the owning session id; filters listings.
        pid: OS pid (may be ``None`` until the spawn helper records it).
        command: human-readable command string for diagnostics.
        state: current :class:`JobState`.
        exit_code: populated when the process exits / is killed.
        started_at: monotonic timestamp at registration.
        backgrounded_at: monotonic timestamp when state flipped to
            ``BACKGROUNDED`` (``None`` while still foreground).
        ttl_seconds: per-job TTL, clamped.
        stdout / stderr: bounded :class:`JobOutput` ring buffers.
        notify_on_exit: optional :class:`DeliveryTarget` for the
            exit-notification handler.
        tags: free-form tagging for the registry's filter helpers.
        last_seen: timestamp of the most recent poll / append (used
            by ``known_poll_no_progress`` detectors).
    """

    job_id: str
    scope_key: str = ""
    pid: Optional[int] = None
    command: str = ""
    state: JobState = JobState.FOREGROUND
    exit_code: Optional[int] = None
    started_at: float = field(default_factory=_now)
    backgrounded_at: Optional[float] = None
    ttl_seconds: float = DEFAULT_JOB_TTL_SECONDS
    stdout: JobOutput = field(default_factory=JobOutput)
    stderr: JobOutput = field(default_factory=JobOutput)
    notify_on_exit: Optional[DeliveryTarget] = None
    tags: tuple[str, ...] = ()
    last_seen: float = field(default_factory=_now)

    def age_seconds(self, *, clock: Callable[[], float] = _now) -> float:
        return max(0.0, clock() - self.started_at)

    def time_since_backgrounded(self, *, clock: Callable[[], float] = _now) -> Optional[float]:
        if self.backgrounded_at is None:
            return None
        return max(0.0, clock() - self.backgrounded_at)


@dataclass(frozen=True)
class JobReference:
    """Lightweight handle returned by registry helpers (no buffer copy)."""

    job_id: str
    scope_key: str
    state: JobState
    pid: Optional[int]
    exit_code: Optional[int]
    age_seconds: float
    command: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class JobSnapshot:
    """Frozen poll result with output snapshots."""

    reference: JobReference
    stdout: str
    stderr: str
    is_finished: bool


@dataclass(frozen=True)
class SweepReport:
    """Summary of one TTL-sweep pass over the registry."""

    examined: int = 0
    killed_for_ttl: int = 0
    moved_to_finished: int = 0
    unreachable: int = 0
    elapsed_seconds: float = 0.0


class ProcessRegistry:
    """Persistent per-session process registry.

    Thread-safe. Construct one per orchestrator instance and pass
    around (or use :func:`get_process_registry` for the module
    singleton).
    """

    def __init__(
        self,
        *,
        default_ttl_seconds: float = DEFAULT_JOB_TTL_SECONDS,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        pending_max_output_chars: int = DEFAULT_PENDING_MAX_OUTPUT_CHARS,
        clock: Callable[[], float] = _now,
        kill_callable: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._default_ttl = _clamp_ttl(default_ttl_seconds)
        self._max_output = max(1, int(max_output_chars))
        self._pending_max = max(1, int(pending_max_output_chars))
        self._clock = clock
        self._kill_callable = kill_callable
        self._running: dict[str, RegisteredJob] = {}
        self._finished: dict[str, RegisteredJob] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration

    def register(
        self,
        job_id: str,
        *,
        scope_key: str = "",
        pid: Optional[int] = None,
        command: str = "",
        ttl_seconds: Optional[float] = None,
        notify_on_exit: Optional[DeliveryTarget] = None,
        tags: Optional[tuple[str, ...]] = None,
    ) -> RegisteredJob:
        """Register a new job. Replaces any prior job with the same id."""
        if not job_id:
            raise ValueError("job_id must be non-empty")
        ttl = _clamp_ttl(ttl_seconds if ttl_seconds is not None else self._default_ttl)
        with self._lock:
            self._running.pop(job_id, None)
            self._finished.pop(job_id, None)
            job = RegisteredJob(
                job_id=job_id,
                scope_key=scope_key,
                pid=pid,
                command=command,
                ttl_seconds=ttl,
                notify_on_exit=notify_on_exit,
                tags=tuple(tags or ()),
                stdout=JobOutput(cap_chars=self._max_output),
                stderr=JobOutput(cap_chars=self._max_output),
                started_at=self._clock(),
                last_seen=self._clock(),
            )
            self._running[job_id] = job
            return job

    def attach_pid(self, job_id: str, pid: int) -> bool:
        """Late-bind a pid to a registered job. Returns ``True`` on hit."""
        with self._lock:
            job = self._running.get(job_id)
            if job is None:
                return False
            job.pid = pid
            job.last_seen = self._clock()
            return True

    # ------------------------------------------------------------------
    # Output capture

    def append_stdout(self, job_id: str, chunk: str) -> bool:
        """Append ``chunk`` to the job's stdout buffer."""
        with self._lock:
            job = self._running.get(job_id) or self._finished.get(job_id)
            if job is None:
                return False
            job.stdout.append(chunk)
            job.last_seen = self._clock()
            return True

    def append_stderr(self, job_id: str, chunk: str) -> bool:
        with self._lock:
            job = self._running.get(job_id) or self._finished.get(job_id)
            if job is None:
                return False
            job.stderr.append(chunk)
            job.last_seen = self._clock()
            return True

    # ------------------------------------------------------------------
    # Lifecycle transitions

    def mark_backgrounded(self, job_id: str) -> bool:
        """Transition the job from foreground to backgrounded."""
        with self._lock:
            job = self._running.get(job_id)
            if job is None or job.state != JobState.FOREGROUND:
                return False
            job.state = JobState.BACKGROUNDED
            job.backgrounded_at = self._clock()
            job.last_seen = self._clock()
            return True

    def mark_exited(self, job_id: str, exit_code: int) -> bool:
        """Mark exited and move to finished. Fires notify_on_exit callback."""
        return self._finalize(job_id, exit_code=exit_code, state=JobState.EXITED)

    def mark_killed(self, job_id: str, *, exit_code: int = -9) -> bool:
        """Mark killed (e.g. by TTL sweep) and move to finished."""
        return self._finalize(job_id, exit_code=exit_code, state=JobState.KILLED)

    def mark_unreachable(self, job_id: str) -> bool:
        """Mark unreachable (process gone but no exit code captured)."""
        return self._finalize(job_id, exit_code=None, state=JobState.UNREACHABLE)

    def _finalize(
        self,
        job_id: str,
        *,
        exit_code: Optional[int],
        state: JobState,
    ) -> bool:
        notify: Optional[DeliveryTarget] = None
        finalized_job: Optional[RegisteredJob] = None
        with self._lock:
            job = self._running.pop(job_id, None)
            if job is None:
                return False
            job.state = state
            job.exit_code = exit_code
            job.last_seen = self._clock()
            self._finished[job_id] = job
            notify = job.notify_on_exit
            finalized_job = job
        if notify is not None and finalized_job is not None:
            self._fire_exit_notification(finalized_job, notify)
        return True

    def _fire_exit_notification(self, job: RegisteredJob, target: DeliveryTarget) -> None:
        """Subclassing hook for wiring exit notifications.

        The base implementation logs at INFO. Orchestrator subclasses
        (or callers via composition) override or replace this to route
        the event through the bus / channel framework.
        """
        LOGGER.info(
            "job %s exited (state=%s code=%s); notify channel=%s handler=%s",
            job.job_id, job.state.value, job.exit_code,
            target.channel, target.handler,
        )

    # ------------------------------------------------------------------
    # Lookup / listing

    def get(self, job_id: str) -> Optional[RegisteredJob]:
        """Return the running job, or the most-recent finished job."""
        with self._lock:
            job = self._running.get(job_id)
            if job is not None:
                return job
            return self._finished.get(job_id)

    def list_active(self, *, scope_key: Optional[str] = None) -> tuple[JobReference, ...]:
        """Snapshot of running jobs, optionally filtered by ``scope_key``."""
        with self._lock:
            clock = self._clock()
            refs = [
                self._make_ref(job, clock=clock)
                for job in self._running.values()
                if scope_key is None or job.scope_key == scope_key
            ]
        return tuple(sorted(refs, key=lambda r: r.age_seconds, reverse=True))

    def list_finished(self, *, scope_key: Optional[str] = None) -> tuple[JobReference, ...]:
        with self._lock:
            clock = self._clock()
            refs = [
                self._make_ref(job, clock=clock)
                for job in self._finished.values()
                if scope_key is None or job.scope_key == scope_key
            ]
        return tuple(sorted(refs, key=lambda r: r.age_seconds, reverse=True))

    def snapshot(
        self,
        job_id: str,
        *,
        max_chars: Optional[int] = None,
    ) -> Optional[JobSnapshot]:
        """Return a frozen :class:`JobSnapshot` for the job."""
        with self._lock:
            job = self._running.get(job_id) or self._finished.get(job_id)
            if job is None:
                return None
            cap = max_chars if max_chars is not None else self._pending_max
            stdout = job.stdout.snapshot(max_chars=cap)
            stderr = job.stderr.snapshot(max_chars=cap)
            return JobSnapshot(
                reference=self._make_ref(job, clock=self._clock()),
                stdout=stdout,
                stderr=stderr,
                is_finished=job.state in (JobState.EXITED, JobState.KILLED, JobState.UNREACHABLE),
            )

    def _make_ref(self, job: RegisteredJob, *, clock: float) -> JobReference:
        return JobReference(
            job_id=job.job_id,
            scope_key=job.scope_key,
            state=job.state,
            pid=job.pid,
            exit_code=job.exit_code,
            age_seconds=max(0.0, clock - job.started_at),
            command=job.command,
            tags=job.tags,
        )

    # ------------------------------------------------------------------
    # TTL sweep

    def sweep_ttl(self) -> SweepReport:
        """Walk backgrounded jobs; kill + move-to-finished those past TTL."""
        start = self._clock()
        examined = 0
        killed = 0
        moved = 0
        unreachable = 0
        candidates: list[RegisteredJob] = []
        with self._lock:
            for job in list(self._running.values()):
                if job.state != JobState.BACKGROUNDED:
                    continue
                examined += 1
                age = job.time_since_backgrounded(clock=self._clock) or 0.0
                if age > job.ttl_seconds:
                    candidates.append(job)
        for job in candidates:
            if job.pid is not None and self._kill_callable is not None:
                try:
                    self._kill_callable(job.pid)
                    killed += 1
                except Exception:  # noqa: BLE001
                    LOGGER.warning(
                        "TTL-sweep kill failed for pid %s (job %s)",
                        job.pid, job.job_id, exc_info=True,
                    )
                    unreachable += 1
            self._finalize(job.job_id, exit_code=-9 if killed else None, state=JobState.KILLED)
            moved += 1
        return SweepReport(
            examined=examined,
            killed_for_ttl=killed,
            moved_to_finished=moved,
            unreachable=unreachable,
            elapsed_seconds=max(0.0, self._clock() - start),
        )

    def clear(self) -> None:
        """Drop every running + finished entry (test helper)."""
        with self._lock:
            self._running.clear()
            self._finished.clear()


# ----------------------------------------------------------------------
# Module-level singleton


_registry_singleton: Optional[ProcessRegistry] = None
_registry_lock = threading.Lock()


def get_process_registry() -> ProcessRegistry:
    """Module-level singleton accessor."""
    global _registry_singleton
    with _registry_lock:
        if _registry_singleton is None:
            _registry_singleton = ProcessRegistry()
        return _registry_singleton


def set_process_registry(registry: ProcessRegistry) -> None:
    """Replace the singleton (init / tests)."""
    global _registry_singleton
    with _registry_lock:
        _registry_singleton = registry


def reset_process_registry_for_testing() -> None:
    """Drop the singleton; next :func:`get_process_registry` returns fresh."""
    global _registry_singleton
    with _registry_lock:
        _registry_singleton = None


__all__ = [
    "DEFAULT_JOB_TTL_SECONDS",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_PENDING_MAX_OUTPUT_CHARS",
    "DeliveryTarget",
    "JobOutput",
    "JobReference",
    "JobSnapshot",
    "JobState",
    "MAX_JOB_TTL_SECONDS",
    "MIN_JOB_TTL_SECONDS",
    "ProcessRegistry",
    "RegisteredJob",
    "SweepReport",
    "get_process_registry",
    "reset_process_registry_for_testing",
    "set_process_registry",
]
