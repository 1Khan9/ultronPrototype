"""BusyEstimator — inferred do-not-disturb signal for chat-mode.

Detects when the player is actively mid-round using ONLY signals the relay
pipeline already owns (no game API, no screen capture, anticheat-clean).
All signal sources are INJECTED as callables so this module has zero imports
from kenning.audio or kenning.pipeline.

API::

    est = BusyEstimator(vad_fn, ptt_fn, callout_age_fn)
    if est.is_busy():
        ...  # skip speak step
    est.hush(seconds=15)   # manual override
    est.clear_hush()       # cancel early

ANTICHEAT (BR-P1): stdlib only — time, math, threading, logging, dataclasses.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("kenning.twitch.busy")

__all__ = ["BusyEstimator"]


class BusyEstimator:
    """Infers player busyness from three injected signals.

    :param vad_fn: callable() -> bool — True if VAD is currently active.
    :param ptt_fn: callable() -> bool — True if PTT key is currently held.
    :param callout_age_fn: callable() -> float — seconds since last relay
        callout output (math.inf if never).
    :param callout_busy_window_s: a callout within this many seconds means busy.
    :param hush_s: default manual-override duration when hush(seconds=None).
    """

    def __init__(
        self,
        vad_fn: Callable[[], bool],
        ptt_fn: Callable[[], bool],
        callout_age_fn: Callable[[], float],
        *,
        callout_busy_window_s: float = 8.0,
        hush_s: float = 30.0,
    ) -> None:
        if not callable(vad_fn):
            raise TypeError("vad_fn must be callable")
        if not callable(ptt_fn):
            raise TypeError("ptt_fn must be callable")
        if not callable(callout_age_fn):
            raise TypeError("callout_age_fn must be callable")
        if callout_busy_window_s <= 0:
            raise ValueError("callout_busy_window_s must be > 0")
        if hush_s <= 0:
            raise ValueError("hush_s must be > 0")

        self._vad_fn = vad_fn
        self._ptt_fn = ptt_fn
        self._callout_age_fn = callout_age_fn
        self._callout_busy_window_s = float(callout_busy_window_s)
        self._hush_s = float(hush_s)

        self._lock = threading.Lock()
        self._hush_until: float = 0.0  # monotonic deadline; 0 = not hushed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_busy(self) -> bool:
        """True if any signal indicates the player is mid-round / should not
        be interrupted. Never raises — signal errors are treated as not-busy."""
        try:
            vad = bool(self._vad_fn())
        except Exception:  # noqa: BLE001
            logger.debug("BusyEstimator: vad_fn error; treating as not-active")
            vad = False

        try:
            ptt = bool(self._ptt_fn())
        except Exception:  # noqa: BLE001
            logger.debug("BusyEstimator: ptt_fn error; treating as not-active")
            ptt = False

        try:
            age = float(self._callout_age_fn())
            if math.isnan(age):
                age = math.inf
        except Exception:  # noqa: BLE001
            logger.debug("BusyEstimator: callout_age_fn error; treating as quiet")
            age = math.inf

        callout_recent = age < self._callout_busy_window_s

        with self._lock:
            hushed = time.monotonic() < self._hush_until

        busy = vad or ptt or callout_recent or hushed
        if busy:
            reasons = []
            if vad:
                reasons.append("vad")
            if ptt:
                reasons.append("ptt")
            if callout_recent:
                reasons.append(f"callout_age={age:.1f}s")
            if hushed:
                reasons.append("hush")
            logger.debug("BusyEstimator: busy (%s)", ", ".join(reasons))
        return busy

    def hush(self, seconds: Optional[float] = None) -> None:
        """Force busy for N seconds (default: hush_s from constructor).

        If already hushed, extends the deadline to whichever is later.
        """
        duration = seconds if seconds is not None else self._hush_s
        if duration <= 0:
            raise ValueError("hush duration must be > 0")
        deadline = time.monotonic() + duration
        with self._lock:
            self._hush_until = max(self._hush_until, deadline)
        logger.info("BusyEstimator: hushed for %.1f s", duration)

    def clear_hush(self) -> None:
        """Cancel the manual hush override immediately."""
        with self._lock:
            self._hush_until = 0.0
        logger.info("BusyEstimator: hush cleared")

    @property
    def callout_busy_window_s(self) -> float:
        return self._callout_busy_window_s

    @property
    def hush_s(self) -> float:
        return self._hush_s
