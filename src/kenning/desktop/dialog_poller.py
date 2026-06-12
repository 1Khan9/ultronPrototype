"""Background dialog poller that publishes :class:`DialogAppearedEvent`.

Wires :func:`kenning.desktop.dialog_control.find_dialogs` into a daemon
thread + the typed event bus so subscribers (coding-bridge
auto-handler, voice narrator, autonomy gate) react to dialog
appearance without polling themselves.

Catalog 08's `wait_for_dialog` is a synchronous one-shot barrier; this
module is the continuous, event-driven equivalent. The poller fires
:data:`kenning.bus.events.DialogAppearedEvent` exactly once per newly-
seen dialog (deduplicated by hwnd + first-seen timestamp) and fires
:data:`kenning.bus.events.DialogResolvedEvent` when a previously-
announced dialog disappears from the next tick.

Default poll cadence is 750 ms (`DEFAULT_POLL_INTERVAL_S=0.75`). Fast
enough to catch save-as / overwrite-confirm / installer / UAC-adjacent
dialogs within a human-perceivable window, slow enough that the
periodic UIA enumeration cost (~5-15 ms per tick) is invisible against
voice baseline budgets.

Safety:
  * Read-only (Cap-2 screen observation). The poller never clicks /
    types -- subscribers do that themselves through the gated dialog
    primitives.
  * Fail-open at every tick: if :func:`find_dialogs` raises, the tick
    is treated as "no dialogs visible" and the loop continues. A
    persistently failing UIA layer never crashes the orchestrator.
  * Lifecycle: callers construct the poller, call :meth:`start` once,
    and :meth:`stop` on orchestrator shutdown. Start / stop are
    idempotent.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from kenning.utils.logging import get_logger

logger = get_logger("desktop.dialog_poller")


#: Default poll cadence. 750 ms strikes a balance between detection
#: latency (a save-as dialog opening is noticed within ~1 second) and
#: per-tick overhead (one UIA enumeration pass at the foreground level).
DEFAULT_POLL_INTERVAL_S: float = 0.75


#: Hard upper bound on tracked-dialog memory. If the system has more
#: than this many dialog windows simultaneously, oldest tracked entries
#: are dropped (each carries only an hwnd + timestamp so the memory
#: footprint is tiny but a sanity ceiling helps catch runaway state).
MAX_TRACKED_DIALOGS: int = 64


@dataclass
class _TrackedDialog:
    """One dialog the poller has announced and is watching for resolution."""

    hwnd: int
    title: str
    class_name: str
    matched_by: str
    process_name: str
    monitor_index: int
    first_seen_at: float
    last_seen_at: float


class DialogPoller:
    """Daemon-thread background poller for dialog windows.

    Construct once at orchestrator startup, call :meth:`start` to
    begin polling, :meth:`stop` to shut down on application exit.

    Args:
        poll_interval_s: seconds between ticks. Default
            :data:`DEFAULT_POLL_INTERVAL_S`. Lower values reduce
            detection latency at the cost of more UIA traffic.
        find_dialogs_fn: injection hook for tests -- defaults to
            :func:`kenning.desktop.dialog_control.find_dialogs`.
        publish_fn: injection hook for tests -- defaults to the
            module-level :func:`kenning.bus.publish`.
        clock_fn: injection hook for tests -- defaults to
            :func:`time.monotonic` for the tick interval AND
            :func:`time.time` for the timestamp recorded in the event.
        stale_after_ticks: a tracked dialog that is absent for this
            many consecutive ticks is removed from the tracked set
            and announced as resolved (``resolution="stale"``).
            Default 2 (i.e. dialog must be missing for 2 polls to
            count as gone, which dampens flicker on heavy systems).

    Notes:
        * The poller spawns ONE daemon thread on :meth:`start`. The
          thread exits cleanly on :meth:`stop` (or process exit, since
          it's a daemon).
        * Subscribers receive events on the poller's own thread; keep
          callbacks fast or hand off to your own queue (consistent
          with the bus's documented threading model).
        * Initial dialogs detected on the FIRST tick (i.e. dialogs
          present BEFORE the poller started) are announced normally;
          the bus subscription model does not distinguish between
          "we just saw it" and "it was already there when we started".
    """

    def __init__(
        self,
        *,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        find_dialogs_fn: Optional[Callable[..., list]] = None,
        publish_fn: Optional[Callable[..., object]] = None,
        clock_fn: Optional[Callable[[], float]] = None,
        wall_clock_fn: Optional[Callable[[], float]] = None,
        stale_after_ticks: int = 2,
    ) -> None:
        self._interval = max(0.05, float(poll_interval_s))
        self._find_dialogs = find_dialogs_fn
        self._publish = publish_fn
        self._monotonic = clock_fn if callable(clock_fn) else time.monotonic
        self._wall_clock = wall_clock_fn if callable(wall_clock_fn) else time.time
        self._stale_after_ticks = max(1, int(stale_after_ticks))

        self._tracked: dict[int, _TrackedDialog] = {}
        self._missing_ticks: dict[int, int] = {}
        self._tick_count = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """True iff the poller's daemon thread is alive."""
        t = self._thread
        return t is not None and t.is_alive()

    def start(self) -> None:
        """Start the daemon poll thread. Idempotent."""
        with self._lock:
            if self.running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="dialog-poller", daemon=True,
            )
            self._thread.start()

    def stop(self, *, wait_s: float = 2.0) -> None:
        """Signal the daemon thread to exit. Idempotent.

        Args:
            wait_s: max seconds to wait for the thread to actually
                join. The thread is a daemon, so it dies with the
                process anyway; this just gives a clean shutdown
                window.
        """
        self._stop_event.set()
        t = self._thread
        if t is not None and t.is_alive():
            try:
                t.join(timeout=max(0.0, float(wait_s)))
            except Exception:  # noqa: BLE001
                pass
        self._thread = None

    # ------------------------------------------------------------------
    # Public introspection
    # ------------------------------------------------------------------

    def tracked_hwnds(self) -> tuple[int, ...]:
        """Currently-tracked dialog hwnds. Thread-safe snapshot."""
        with self._lock:
            return tuple(self._tracked.keys())

    def tick_count(self) -> int:
        """How many poll ticks have completed since :meth:`start`."""
        with self._lock:
            return self._tick_count

    def tick_once(self) -> None:
        """Run exactly one poll iteration on the calling thread.

        Useful for tests; the daemon thread is the production path.
        """
        self._tick()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Daemon thread main loop."""
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001
                # Per-tick exceptions are absorbed; the poller must
                # never crash the orchestrator. The next tick re-tries.
                logger.debug("dialog_poller tick raised: %s", exc)
            # Wait_for_event-based sleep so stop() interrupts promptly.
            if self._stop_event.wait(self._interval):
                return

    def _tick(self) -> None:
        """One poll iteration. Public-ish via :meth:`tick_once` for tests."""
        dialogs = self._call_find_dialogs()
        now_mono = self._monotonic()
        now_wall = self._wall_clock()

        # Snapshot current-tick hwnds for the missing-tick bookkeeping.
        seen_hwnds: set[int] = set()
        new_to_announce: list[_TrackedDialog] = []

        with self._lock:
            self._tick_count += 1

            for d in dialogs:
                try:
                    hwnd = int(getattr(d, "hwnd"))
                    title = str(getattr(d, "title", "") or "")
                    class_name = str(getattr(d, "class_name", "") or "")
                    matched_by = str(getattr(d, "matched_by", "") or "")
                    window = getattr(d, "window", None)
                    process_name = (
                        str(getattr(window, "process_name", "") or "")
                        if window is not None else ""
                    )
                    monitor_index = (
                        int(getattr(window, "monitor_index", -1))
                        if window is not None else -1
                    )
                except Exception:  # noqa: BLE001
                    continue
                if hwnd <= 0:
                    continue

                seen_hwnds.add(hwnd)
                self._missing_ticks.pop(hwnd, None)

                existing = self._tracked.get(hwnd)
                if existing is None:
                    tracked = _TrackedDialog(
                        hwnd=hwnd,
                        title=title,
                        class_name=class_name,
                        matched_by=matched_by,
                        process_name=process_name,
                        monitor_index=monitor_index,
                        first_seen_at=now_wall,
                        last_seen_at=now_wall,
                    )
                    self._tracked[hwnd] = tracked
                    new_to_announce.append(tracked)
                    # Bound memory.
                    if len(self._tracked) > MAX_TRACKED_DIALOGS:
                        oldest_hwnd = min(
                            self._tracked,
                            key=lambda h: self._tracked[h].first_seen_at,
                        )
                        self._tracked.pop(oldest_hwnd, None)
                        self._missing_ticks.pop(oldest_hwnd, None)
                else:
                    existing.last_seen_at = now_wall

            # Find dialogs that disappeared from this tick.
            resolved_now: list[tuple[_TrackedDialog, str]] = []
            for hwnd, tracked in list(self._tracked.items()):
                if hwnd in seen_hwnds:
                    continue
                missing = self._missing_ticks.get(hwnd, 0) + 1
                self._missing_ticks[hwnd] = missing
                if missing >= self._stale_after_ticks:
                    resolved_now.append((tracked, "stale"))
                    self._tracked.pop(hwnd, None)
                    self._missing_ticks.pop(hwnd, None)

        # Publish OUTSIDE the lock to avoid blocking subscribers from
        # adding state. now_mono is used for lifetime computation so
        # the wall clock can't go backwards on us.
        for tracked in new_to_announce:
            self._publish_appeared(tracked)
        for tracked, resolution in resolved_now:
            self._publish_resolved(tracked, resolution, now_wall=now_wall)

    def _call_find_dialogs(self) -> list:
        """Invoke the dialog finder with fail-open semantics."""
        finder = self._find_dialogs
        if finder is None:
            try:
                from kenning.desktop.dialog_control import find_dialogs
            except Exception as exc:  # noqa: BLE001
                logger.debug("dialog_poller find_dialogs import failed: %s", exc)
                return []
            finder = find_dialogs
        try:
            result = finder()
        except Exception as exc:  # noqa: BLE001
            logger.debug("dialog_poller find_dialogs raised: %s", exc)
            return []
        return list(result) if result is not None else []

    def _publish_appeared(self, tracked: _TrackedDialog) -> None:
        """Fire :data:`DialogAppearedEvent` for a newly-seen dialog."""
        publisher = self._publish
        if publisher is None:
            try:
                from kenning.bus import publish as _publish
                from kenning.bus.events import DialogAppearedEvent
            except Exception as exc:  # noqa: BLE001
                logger.debug("dialog_poller bus import failed: %s", exc)
                return
            publisher = _publish
            event_def = DialogAppearedEvent
        else:
            from kenning.bus.events import DialogAppearedEvent
            event_def = DialogAppearedEvent
        try:
            publisher(
                event_def,
                {
                    "hwnd": tracked.hwnd,
                    "title": tracked.title,
                    "class_name": tracked.class_name,
                    "matched_by": tracked.matched_by,
                    "process_name": tracked.process_name,
                    "monitor_index": tracked.monitor_index,
                    "first_seen_at": tracked.first_seen_at,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("dialog_poller publish appeared raised: %s", exc)

    def _publish_resolved(
        self,
        tracked: _TrackedDialog,
        resolution: str,
        *,
        now_wall: float,
    ) -> None:
        """Fire :data:`DialogResolvedEvent` for a dialog that disappeared."""
        publisher = self._publish
        if publisher is None:
            try:
                from kenning.bus import publish as _publish
                from kenning.bus.events import DialogResolvedEvent
            except Exception as exc:  # noqa: BLE001
                logger.debug("dialog_poller bus import failed: %s", exc)
                return
            publisher = _publish
            event_def = DialogResolvedEvent
        else:
            from kenning.bus.events import DialogResolvedEvent
            event_def = DialogResolvedEvent
        try:
            lifetime_ms = max(
                0,
                int((now_wall - tracked.first_seen_at) * 1000),
            )
        except Exception:  # noqa: BLE001
            lifetime_ms = 0
        try:
            publisher(
                event_def,
                {
                    "hwnd": tracked.hwnd,
                    "title": tracked.title,
                    "resolution": resolution,
                    "lifetime_ms": lifetime_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("dialog_poller publish resolved raised: %s", exc)

    def announce_explicit_resolution(
        self,
        hwnd: int,
        resolution: str,
    ) -> bool:
        """Caller-driven resolution announce (e.g. after auto-dismiss).

        When the coding-bridge auto-handler successfully dismisses a
        dialog, it calls this method with ``resolution="dismissed"``
        / ``"auto_filled"`` to publish :data:`DialogResolvedEvent`
        with the correct cause -- otherwise the poller will eventually
        catch the disappearance and announce it as ``"stale"``.

        Returns:
            True if the hwnd was tracked and a resolved event was
            published; False if the poller wasn't tracking it.
        """
        with self._lock:
            tracked = self._tracked.pop(hwnd, None)
            self._missing_ticks.pop(hwnd, None)
        if tracked is None:
            return False
        self._publish_resolved(
            tracked, resolution, now_wall=self._wall_clock(),
        )
        return True


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_poller_singleton: Optional[DialogPoller] = None


def get_dialog_poller() -> DialogPoller:
    """Module-level singleton accessor.

    The orchestrator builds the production poller from config at
    startup and pushes it via :func:`set_dialog_poller`. Callers
    that arrive before the orchestrator (tests, scripts) get a
    default instance which is NOT started.
    """
    global _poller_singleton
    if _poller_singleton is None:
        _poller_singleton = DialogPoller()
    return _poller_singleton


def set_dialog_poller(poller: Optional[DialogPoller]) -> None:
    """Test / orchestrator hook -- swap the singleton."""
    global _poller_singleton
    _poller_singleton = poller


__all__ = [
    "DialogPoller",
    "DEFAULT_POLL_INTERVAL_S",
    "MAX_TRACKED_DIALOGS",
    "get_dialog_poller",
    "set_dialog_poller",
]
