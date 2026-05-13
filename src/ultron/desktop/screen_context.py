"""Screen-context orchestrator -- assemble "what is the user looking at"
into a structured snapshot for LLM injection.

This is the load-bearing module for the "explain what I'm looking at"
voice flow:

1. User says "Ultron, what does this error mean?"
2. Orchestrator calls :func:`build_screen_context` -- this module --
   to get the current screen state.
3. The result is folded into the next LLM call as structured context
   (similar shape to RAG): foreground app, window title, monitor
   layout, UIA text snippets, optional VLM description.
4. The LLM responds in Ultron's voice with grounded knowledge of
   what's on screen.

Components consulted (all fail-open at their level):

- :mod:`ultron.desktop.windows` -- foreground window + visible windows
- :mod:`ultron.desktop.monitors` -- multi-monitor layout
- :mod:`ultron.desktop.capture` -- on-demand screen capture (PNG bytes
  for the VLM)
- :mod:`ultron.desktop.uia` -- UIA tree text for the foreground window
- :mod:`ultron.desktop.vlm` (Phase 6) -- moondream2 scene description
  when registered; ``None`` otherwise

Performance: a full snapshot takes ~50-300 ms when no VLM call fires
(window enum + UIA walk dominate). VLM call adds 3-8 s. The
orchestrator routes the cheap layer continuously and the VLM call
on-demand only.

Caching: a small ring buffer (default 3 entries) stores recent
snapshots so a follow-up question within ~15 s can reuse the previous
visual context without re-capturing.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from ultron.desktop.capture import Screenshot, get_screen_capture
from ultron.desktop.monitors import Monitor, enumerate_monitors
from ultron.desktop.uia import collect_window_text
from ultron.desktop.windows import (
    WindowInfo,
    enumerate_windows,
    get_foreground_window,
)
from ultron.utils.logging import get_logger

logger = get_logger("desktop.screen_context")


# ---------------------------------------------------------------------------
# Snapshot dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScreenContextSnapshot:
    """One assembled screen-state snapshot.

    Attributes:
        timestamp: ``time.time()`` at assembly.
        monitors: per-monitor layout for context.
        foreground: foreground window (None when nothing's focused).
        windows: visible top-level windows -- limited list, no duplicates.
        ui_text: UIA-extracted text from the foreground window.
        screenshot: PNG bytes of the foreground monitor (or None when
            ``capture=False`` or capture failed).
        vlm_description: optional VLM scene description (None when no
            VLM wired or VLM call disabled / failed).
        elapsed_ms: total wall-clock to assemble this snapshot.
    """

    timestamp: float
    monitors: tuple[Monitor, ...]
    foreground: Optional[WindowInfo]
    windows: tuple[WindowInfo, ...]
    ui_text: tuple[str, ...]
    screenshot: Optional[Screenshot]
    vlm_description: Optional[str]
    elapsed_ms: float

    def render_for_llm(self, *, max_ui_text: int = 40) -> str:
        """Render the snapshot as a single text block for LLM injection.

        Designed for prepending to the user's utterance as context.
        Keeps the block readable to the model (uses headings + bullets,
        not a JSON blob -- Qwen handles natural-language context far
        better than nested JSON).
        """
        lines: list[str] = ["[Visual context -- what is on the user's screen right now]"]
        if self.foreground is not None:
            fg = self.foreground
            lines.append(
                f"Foreground app: {fg.process_name or '(unknown)'}; "
                f"window title: {fg.title!r}; "
                f"monitor: {fg.monitor_index if fg.monitor_index is not None else '?'}."
            )
        else:
            lines.append("No window is currently focused.")

        if self.monitors:
            mon_blurb = ", ".join(
                f"#{m.index}({'primary' if m.is_primary else f'{m.width}x{m.height}'})"
                for m in self.monitors
            )
            lines.append(f"Connected monitors: {mon_blurb}.")

        if self.windows:
            other = [w for w in self.windows if w is not self.foreground]
            if other:
                procs = sorted({w.process_name for w in other if w.process_name})
                lines.append(
                    "Other visible apps: " + ", ".join(procs[:12]) + "."
                )

        if self.ui_text:
            sample = list(self.ui_text)[:max_ui_text]
            lines.append("Visible UI text from the focused window:")
            for s in sample:
                # Trim each line for safety; UIA strings can be long.
                snippet = s.strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                lines.append(f"  - {snippet}")

        if self.vlm_description:
            lines.append("Visual description (image model):")
            for ln in self.vlm_description.strip().splitlines():
                lines.append(f"  {ln}")

        lines.append("[End visual context]")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# VLM hook type
# ---------------------------------------------------------------------------


# A callable that takes PNG bytes and returns a description string.
# Phase 6 wires moondream2 in via :func:`set_vlm_describe`.
VLMDescribeFn = Callable[[bytes], Optional[str]]

_vlm_describe: Optional[VLMDescribeFn] = None
_vlm_lock = threading.Lock()


def set_vlm_describe(fn: Optional[VLMDescribeFn]) -> None:
    """Register / clear the VLM describe callable. Phase 6 calls this."""
    global _vlm_describe
    with _vlm_lock:
        _vlm_describe = fn


def get_vlm_describe() -> Optional[VLMDescribeFn]:
    """Current VLM describe callable, or None when none registered."""
    return _vlm_describe


# ---------------------------------------------------------------------------
# Main assembly function
# ---------------------------------------------------------------------------


def build_screen_context(
    *,
    capture: bool = True,
    capture_all_monitors: bool = False,
    include_uia: bool = True,
    include_vlm: bool = False,
    ui_text_max_elements: int = 80,
    window_list_cap: int = 12,
    vlm_prompt: Optional[str] = None,
    discard_image_after_analysis: bool = True,
) -> ScreenContextSnapshot:
    """Assemble a screen-context snapshot.

    Args:
        capture: when True, capture the foreground monitor (or all
            monitors if ``capture_all_monitors``).
        capture_all_monitors: capture every monitor instead of just
            the foreground one. Increases bytes by 3-5x; useful for
            VLM calls when the user's question doesn't clearly point
            at the foreground.
        include_uia: when True, run :func:`collect_window_text` on the
            foreground window.
        include_vlm: when True AND a VLM describe callable is registered,
            run it on the captured screenshot. The VLM is slow
            (~3-8 s on CPU), so this defaults to False -- callers opt
            in when answering a contextual question.
        ui_text_max_elements: cap on UIA tree traversal size.
        window_list_cap: max windows returned in the snapshot.
        vlm_prompt: optional question to thread into the VLM call
            (e.g. the user's actual utterance). Currently unused
            (Phase 6 will wire VLM signatures that accept prompts).
        discard_image_after_analysis: when True (default) AND the VLM
            ran successfully, strip ``image_bytes`` from the returned
            screenshot before returning. Saves memory + reduces the
            data-at-rest footprint -- the textual VLM description is
            what callers actually use downstream; the raw pixels are
            redundant once analysed. The :class:`Screenshot` instance
            still carries dimensions / timestamp / monitor_index;
            only the bytes field is cleared (with ``bytes_discarded=
            True`` to distinguish from "no capture was made").
            Set False when the caller specifically needs the bytes
            (saving to disk for debugging, downstream image-processing
            tool that can't consume text).

    Returns:
        :class:`ScreenContextSnapshot`. Always returns a snapshot --
        every component fails to its empty/None default rather than
        raising.
    """
    t0 = time.time()

    # Monitors -- fast, no IO.
    monitors = enumerate_monitors()

    # Foreground window + visible windows.
    foreground = get_foreground_window()
    try:
        all_wins = enumerate_windows()
    except Exception as e:  # noqa: BLE001
        logger.warning("enumerate_windows failed: %s", e)
        all_wins = []

    # Cap the window list so injection stays small.
    windows = tuple(all_wins[:window_list_cap])

    # UIA text from foreground -- only useful when foreground is real.
    ui_text: tuple[str, ...] = ()
    if include_uia and foreground is not None:
        try:
            ui_text = tuple(collect_window_text(
                foreground, max_elements=ui_text_max_elements,
            ))
        except Exception as e:  # noqa: BLE001
            logger.warning("collect_window_text failed: %s", e)

    # Screen capture -- foreground monitor or all monitors.
    shot: Optional[Screenshot] = None
    if capture:
        cap = get_screen_capture()
        try:
            target_idx: Optional[int] = None
            if (
                not capture_all_monitors
                and foreground is not None
                and foreground.monitor_index is not None
            ):
                target_idx = foreground.monitor_index
            elif monitors:
                target_idx = 0
            if target_idx is not None:
                shot = cap.capture_monitor(target_idx)
        except Exception as e:  # noqa: BLE001
            logger.warning("screen capture failed: %s", e)

    # VLM description -- slow; only when explicitly requested.
    vlm_text: Optional[str] = None
    if include_vlm and shot is not None:
        describe = get_vlm_describe()
        if describe is not None:
            try:
                vlm_text = describe(shot.image_bytes)
            except Exception as e:  # noqa: BLE001
                logger.warning("VLM describe failed: %s", e)
                vlm_text = None

    # Analyze-and-discard: when the VLM successfully described the
    # image, the textual description is what we need going forward.
    # Drop the bytes to keep memory + downstream-storage footprint
    # small (and reduce the surface for accidental exfil downstream).
    if (
        shot is not None
        and vlm_text is not None
        and discard_image_after_analysis
    ):
        shot = shot.without_bytes()

    elapsed_ms = (time.time() - t0) * 1000.0
    return ScreenContextSnapshot(
        timestamp=t0,
        monitors=tuple(monitors),
        foreground=foreground,
        windows=windows,
        ui_text=ui_text,
        screenshot=shot,
        vlm_description=vlm_text,
        elapsed_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Recent-snapshot cache for follow-up questions
# ---------------------------------------------------------------------------


class ScreenContextCache:
    """In-memory rolling cache of recent snapshots.

    Used so a follow-up question within a short window can reuse the
    previously-built context without paying the assembly cost again.
    Snapshots are NOT persisted to disk -- screen captures contain
    sensitive content.

    By default the cache strips ``image_bytes`` from stored snapshots
    (the analyze-and-discard pattern). The textual VLM description +
    window / UIA / monitor metadata are what callers actually need for
    follow-up queries; the raw pixels just sit in memory until eviction.
    Set ``discard_image_bytes=False`` at construction to preserve bytes
    (useful when a downstream consumer specifically needs the image,
    e.g. an image-stylize tool).
    """

    def __init__(
        self,
        *,
        ring_size: int = 3,
        max_age_seconds: float = 15.0,
        discard_image_bytes: bool = True,
    ) -> None:
        self._ring: deque[ScreenContextSnapshot] = deque(maxlen=max(1, ring_size))
        self._max_age = float(max_age_seconds)
        self._discard_bytes = bool(discard_image_bytes)
        self._lock = threading.Lock()

    def store(self, snapshot: ScreenContextSnapshot) -> None:
        """Append a snapshot to the ring buffer.

        When ``discard_image_bytes`` is True (the default), the snapshot
        is rebuilt with ``screenshot.without_bytes()`` applied first --
        so the cache only ever retains the textual description + metadata.
        """
        if (
            self._discard_bytes
            and snapshot.screenshot is not None
            and snapshot.screenshot.image_bytes is not None
        ):
            snapshot = ScreenContextSnapshot(
                timestamp=snapshot.timestamp,
                monitors=snapshot.monitors,
                foreground=snapshot.foreground,
                windows=snapshot.windows,
                ui_text=snapshot.ui_text,
                screenshot=snapshot.screenshot.without_bytes(),
                vlm_description=snapshot.vlm_description,
                elapsed_ms=snapshot.elapsed_ms,
            )
        with self._lock:
            self._ring.append(snapshot)

    def latest(self) -> Optional[ScreenContextSnapshot]:
        """Most recent snapshot, ignoring age. Returns None when empty."""
        with self._lock:
            return self._ring[-1] if self._ring else None

    def latest_fresh(self) -> Optional[ScreenContextSnapshot]:
        """Most recent snapshot only if within ``max_age_seconds``."""
        with self._lock:
            if not self._ring:
                return None
            latest = self._ring[-1]
            if (time.time() - latest.timestamp) <= self._max_age:
                return latest
            return None

    def all(self) -> list[ScreenContextSnapshot]:
        with self._lock:
            return list(self._ring)

    def clear(self) -> None:
        with self._lock:
            self._ring.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._ring)


# Module-level singleton cache (orchestrator pushes its own via setter).
_cache_singleton: Optional[ScreenContextCache] = None


def get_screen_context_cache() -> ScreenContextCache:
    """Module-level singleton accessor."""
    global _cache_singleton
    if _cache_singleton is None:
        _cache_singleton = ScreenContextCache()
    return _cache_singleton


def set_screen_context_cache(cache: Optional[ScreenContextCache]) -> None:
    """Test / orchestrator hook -- swap the singleton."""
    global _cache_singleton
    _cache_singleton = cache


# ---------------------------------------------------------------------------
# Convenience: build + cache in one call
# ---------------------------------------------------------------------------


def capture_and_cache(
    *,
    capture: bool = True,
    include_uia: bool = True,
    include_vlm: bool = False,
    capture_all_monitors: bool = False,
) -> ScreenContextSnapshot:
    """Build a snapshot AND store it in the singleton cache.

    Convenience for the orchestrator's "explain this" flow:
    one call yields a fresh snapshot and stashes it so a follow-up
    question can reuse it.
    """
    snap = build_screen_context(
        capture=capture,
        include_uia=include_uia,
        include_vlm=include_vlm,
        capture_all_monitors=capture_all_monitors,
    )
    get_screen_context_cache().store(snap)
    return snap


__all__ = [
    "ScreenContextSnapshot",
    "ScreenContextCache",
    "VLMDescribeFn",
    "build_screen_context",
    "capture_and_cache",
    "get_screen_context_cache",
    "set_screen_context_cache",
    "set_vlm_describe",
    "get_vlm_describe",
]
