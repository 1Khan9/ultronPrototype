"""Latency hygiene helpers (2026-05-19, Track 2 sub-items).

Small, opt-in utility functions for shaving tail latency from the
voice pipeline without touching the hot path. Each helper is pure or
defensively scoped so callers can wire them at startup / shutdown /
between turns without risking the rest of the orchestration.

* :func:`raise_process_priority` -- bump the host process to
  Windows "Above Normal" (or POSIX equivalent) so background
  scheduling can't starve the voice loop mid-turn. ~50-200 ms of
  jitter eliminated on cold paths under load.

* :func:`pause_gc` / :func:`resume_gc` -- toggle Python's cyclic
  garbage collector around hot turns + explicitly collect during
  idle. ~50-200 ms of sporadic stutter avoided on long-running
  sessions.

* :func:`warmup_llm` -- send a no-op prompt to the LLM at startup
  so the first real turn doesn't pay the cold-context cost
  (~100-200 ms saved on first turn per session and after every
  ``MODEL_SWITCH`` swap).

* :func:`warmup_embedder` -- one-shot embed of a no-op string so the
  first retrieval call doesn't pay ONNX runtime warmup latency.

All helpers are fail-open: any underlying error (missing psutil,
unsupported platform, etc.) is caught + logged at DEBUG, the helper
returns without raising. The orchestrator can wire them
unconditionally.
"""

from __future__ import annotations

import gc
import os
import sys
import threading
import time
from typing import Any, Callable, Optional

from ultron.utils.logging import get_logger

logger = get_logger("latency_hygiene")


# ----------------------------------------------------------------------
# Process priority
# ----------------------------------------------------------------------


# Windows priority class constants. We intentionally support ONLY
# the "Above Normal" tier (and the default "Normal" to revert) --
# "High" can starve other apps including Valorant, and "Realtime"
# can deadlock the system.
_WIN_PRIORITY_NORMAL = 0x00000020
_WIN_PRIORITY_ABOVE_NORMAL = 0x00008000


def raise_process_priority(level: str = "above_normal") -> bool:
    """Bump the host process priority.

    Args:
        level: "above_normal" (the only supported elevation tier) or
            "normal" (revert). Anything else returns False without
            attempting a change.

    Returns:
        True iff the priority was successfully changed (or already
        at the target level). False on any failure -- helper is
        fail-open, the caller never has to deal with exceptions.

    Caveats:
        * Caps at "Above Normal" by design. "High" can starve
          gaming workloads; "Realtime" can hang the system.
        * Requires :mod:`psutil`. If the module isn't installed the
          helper logs at DEBUG and returns False.
        * Cross-platform: on Linux / macOS, ``nice(-5)`` is the
          rough equivalent (lowered niceness). Requires root /
          CAP_SYS_NICE to actually take effect; we attempt it and
          fail-open if denied.
    """
    target = (level or "").lower()
    if target not in {"above_normal", "normal"}:
        logger.debug("raise_process_priority: unsupported level %r", level)
        return False
    try:
        import psutil                                          # type: ignore
    except ImportError:
        logger.debug("raise_process_priority: psutil not installed")
        return False

    try:
        proc = psutil.Process(os.getpid())
        if sys.platform.startswith("win"):
            constant = (
                _WIN_PRIORITY_ABOVE_NORMAL
                if target == "above_normal"
                else _WIN_PRIORITY_NORMAL
            )
            proc.nice(constant)
        else:
            # POSIX: -5 niceness for above_normal, 0 for normal.
            # Negative nice values require privileges; psutil
            # surfaces the OSError if denied.
            proc.nice(-5 if target == "above_normal" else 0)
        return True
    except (PermissionError, OSError) as e:
        logger.debug(
            "raise_process_priority: insufficient permission "
            "(%s); leaving at default", e,
        )
        return False
    except Exception as e:                                    # noqa: BLE001
        logger.debug("raise_process_priority: unexpected error %s", e)
        return False


# ----------------------------------------------------------------------
# Garbage collector tuning
# ----------------------------------------------------------------------


_GC_PAUSE_LOCK = threading.Lock()
_GC_PAUSED: bool = False


def pause_gc() -> bool:
    """Disable Python's automatic cyclic garbage collector.

    The voice hot path is short-lived; the cyclic collector
    sporadically pauses execution for ~50-200 ms on a full sweep.
    Pausing it for the duration of a turn + running an explicit
    sweep during idle eliminates mid-turn stutter.

    Returns True iff GC was enabled before the call. Idempotent --
    calling pause when already paused returns False. Thread-safe.
    """
    global _GC_PAUSED
    with _GC_PAUSE_LOCK:
        if _GC_PAUSED:
            return False
        try:
            gc.disable()
            _GC_PAUSED = True
            return True
        except Exception as e:                                # noqa: BLE001
            logger.debug("pause_gc failed: %s", e)
            return False


def resume_gc(*, collect_now: bool = True) -> bool:
    """Re-enable the cyclic GC and optionally run a sweep.

    Args:
        collect_now: when True (default), call ``gc.collect()`` once
            before re-enabling so the deferred work doesn't all hit
            the next user turn.

    Returns True iff GC was paused before the call and is now
    resumed. False when no pause was active.
    """
    global _GC_PAUSED
    with _GC_PAUSE_LOCK:
        if not _GC_PAUSED:
            return False
        try:
            if collect_now:
                try:
                    gc.collect()
                except Exception:
                    pass
            gc.enable()
            _GC_PAUSED = False
            return True
        except Exception as e:                                # noqa: BLE001
            logger.debug("resume_gc failed: %s", e)
            return False


def is_gc_paused() -> bool:
    """Thread-safe query of the paused state."""
    with _GC_PAUSE_LOCK:
        return _GC_PAUSED


# ----------------------------------------------------------------------
# Model warmup
# ----------------------------------------------------------------------


# Default warmup prompt -- short, neutral, doesn't elicit a refusal
# from any model in the preset table. The LLM's response is
# discarded; only the prefill warmup matters.
DEFAULT_LLM_WARMUP_PROMPT: str = "Ready."


def warmup_llm(
    generate_fn: Callable[[str], Any],
    *,
    prompt: str = DEFAULT_LLM_WARMUP_PROMPT,
) -> Optional[float]:
    """Send a no-op prompt to the LLM so the first real turn doesn't
    pay cold-context cost.

    Used at orchestrator startup + after every preset swap. Calls
    ``generate_fn(prompt)`` and discards the result. Returns the
    elapsed wall-clock time in seconds, or None on failure
    (fail-open).

    Args:
        generate_fn: callable that takes a prompt and produces a
            result. Typically ``llm_engine.generate`` (blocking) so
            warmup completes before construction returns.
        prompt: the warmup text. Default ``"Ready."`` is short
            enough to keep warmup cheap (~50-150 ms on Qwen3-4B).

    Notes:
        * The LLM's response is discarded -- any conversation state
          updates from this call should be reset by the caller. For
          ``LLMEngine``, the safe pattern is to call
          ``engine.record_history=False`` if available; otherwise
          accept the no-op response in history.
    """
    t0 = time.monotonic()
    try:
        generate_fn(prompt)
        elapsed = time.monotonic() - t0
        logger.info("LLM warmup completed in %.0f ms", elapsed * 1000)
        return elapsed
    except Exception as e:                                    # noqa: BLE001
        logger.debug("LLM warmup skipped (%s)", e)
        return None


def warmup_embedder(
    encode_fn: Callable[[str], Any],
    *,
    prompt: str = "warmup",
) -> Optional[float]:
    """Touch the embedder so the first retrieval doesn't pay ONNX
    cold-start cost.

    Returns the elapsed wall-clock time in seconds, or None on
    failure (fail-open).
    """
    t0 = time.monotonic()
    try:
        encode_fn(prompt)
        elapsed = time.monotonic() - t0
        logger.info("Embedder warmup completed in %.0f ms", elapsed * 1000)
        return elapsed
    except Exception as e:                                    # noqa: BLE001
        logger.debug("Embedder warmup skipped (%s)", e)
        return None


__all__ = [
    "DEFAULT_LLM_WARMUP_PROMPT",
    "is_gc_paused",
    "pause_gc",
    "raise_process_priority",
    "resume_gc",
    "warmup_embedder",
    "warmup_llm",
]
