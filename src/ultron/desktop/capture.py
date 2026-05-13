"""Multi-monitor screen capture via ``mss``.

mss is ~5 ms per monitor on this hardware and ships as a single
pure-Python wheel. Its native handle is NOT thread-safe in a single
instance, so :class:`ScreenCapture` keeps one ``mss.mss()`` per
thread via thread-local storage.

Every successful capture is recorded in the safety taint tracker
(capability=``screen_context``) by default so the validator's
exfil-detection layer can match if those exact bytes show up as
an outbound tool argument later. Recording is sub-millisecond
(SHA-256 over the PNG bytes); set ``record_taint=False`` to disable
for tests.

The :class:`Screenshot` dataclass holds PNG-encoded bytes. PNG is
the right format here: lossless (so OCR / VLM see exactly what the
user sees), well-compressed for typical desktop content, and the
universal interchange format the moondream2 VLM accepts.
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass
from typing import Optional, Union

import mss
from PIL import Image

from ultron.desktop.monitors import Monitor, enumerate_monitors
from ultron.utils.logging import get_logger

logger = get_logger("desktop.capture")


class ScreenCaptureError(RuntimeError):
    """Raised when a capture call cannot be satisfied (caught + fail-open by callers)."""


@dataclass(frozen=True)
class Screenshot:
    """One captured frame.

    Attributes:
        image_bytes: PNG-encoded image data. ``None`` once the bytes
            have been discarded (post-VLM analysis under the
            analyze-and-discard pattern -- see :meth:`without_bytes` and
            :func:`ultron.desktop.screen_context.build_screen_context`'s
            ``discard_image_after_analysis`` flag).
        monitor_index: source monitor index, or None for arbitrary regions.
        width: pixel width.
        height: pixel height.
        timestamp: ``time.time()`` at capture moment.
        origin_x: leftmost pixel coordinate of the capture in virtual-screen space.
        origin_y: topmost pixel coordinate of the capture in virtual-screen space.
        bytes_discarded: True iff the original bytes were intentionally
            dropped after analysis. Lets callers distinguish "no
            capture was made" (image_bytes=None, bytes_discarded=False)
            from "capture was made + analysed, then discarded for
            storage efficiency / privacy" (image_bytes=None,
            bytes_discarded=True). Defaults False.
    """

    image_bytes: Optional[bytes]
    monitor_index: Optional[int]
    width: int
    height: int
    timestamp: float
    origin_x: int
    origin_y: int
    bytes_discarded: bool = False

    def without_bytes(self) -> "Screenshot":
        """Return a copy with ``image_bytes`` cleared and
        ``bytes_discarded=True``.

        Used by the screen-context layer post-VLM analysis so the
        cache only ever retains the textual description, not the raw
        pixels. Idempotent on already-discarded screenshots.
        """
        if self.image_bytes is None and self.bytes_discarded:
            return self
        return Screenshot(
            image_bytes=None,
            monitor_index=self.monitor_index,
            width=self.width,
            height=self.height,
            timestamp=self.timestamp,
            origin_x=self.origin_x,
            origin_y=self.origin_y,
            bytes_discarded=True,
        )


def _bgra_to_png_bytes(bgra: bytes, width: int, height: int) -> bytes:
    """Convert mss's BGRA raw buffer to PNG-encoded bytes."""
    img = Image.frombytes("RGB", (width, height), bgra, "raw", "BGRX")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _record_taint_safe(image_bytes: bytes) -> None:
    """Record capture bytes in the safety taint tracker. Fail-open."""
    if not image_bytes:
        return
    try:
        from ultron.safety.taint import get_taint_tracker

        get_taint_tracker().record(data=image_bytes, capability="screen_context")
    except Exception as e:  # noqa: BLE001 -- safety side must never break capture
        logger.debug("taint record skipped: %s", e)


class ScreenCapture:
    """Per-process screen capture facade.

    One instance per orchestrator. Thread-safe via a thread-local mss
    handle (mss's underlying GDI / DXGI objects are not safe to share
    across threads).
    """

    def __init__(self, *, record_taint: bool = True) -> None:
        self._tls = threading.local()
        self._record_taint = bool(record_taint)
        self._closed = False

    @property
    def closed(self) -> bool:
        """True once :meth:`close` has been called."""
        return self._closed

    def _sct(self) -> "mss.MSS":
        if self._closed:
            raise ScreenCaptureError("ScreenCapture is closed")
        sct = getattr(self._tls, "sct", None)
        if sct is None:
            sct = mss.MSS()
            self._tls.sct = sct
        return sct

    def capture_monitor(self, monitor: Union[Monitor, int]) -> Optional[Screenshot]:
        """Capture one monitor by :class:`Monitor` instance or index.

        Returns None on any failure (missing monitor, mss error). Caller
        treats None as "couldn't see the screen right now".
        """
        if isinstance(monitor, int):
            mons = enumerate_monitors()
            if not (0 <= monitor < len(mons)):
                logger.warning("capture_monitor: index %d out of range", monitor)
                return None
            mon = mons[monitor]
        else:
            mon = monitor

        return self._capture_region(
            x=mon.x,
            y=mon.y,
            width=mon.width,
            height=mon.height,
            monitor_index=mon.index,
        )

    def capture_all_monitors(self) -> list[Screenshot]:
        """Capture every connected monitor in index order."""
        results: list[Screenshot] = []
        for mon in enumerate_monitors():
            shot = self.capture_monitor(mon)
            if shot is not None:
                results.append(shot)
        return results

    def capture_region(
        self,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> Optional[Screenshot]:
        """Capture an arbitrary rectangle in virtual-screen coordinates."""
        if width <= 0 or height <= 0:
            return None
        return self._capture_region(
            x=x, y=y, width=width, height=height, monitor_index=None,
        )

    def _capture_region(
        self,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        monitor_index: Optional[int],
    ) -> Optional[Screenshot]:
        try:
            sct = self._sct()
            grab = sct.grab({
                "left": x,
                "top": y,
                "width": width,
                "height": height,
            })
        except Exception as e:  # noqa: BLE001 -- mss raises ScreenShotError and others
            logger.warning(
                "screen capture failed at (%d,%d,%d,%d): %s",
                x, y, width, height, e,
            )
            return None

        try:
            png_bytes = _bgra_to_png_bytes(
                bytes(grab.raw), grab.size[0], grab.size[1],
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("PNG encode failed: %s", e)
            return None

        if self._record_taint:
            _record_taint_safe(png_bytes)

        return Screenshot(
            image_bytes=png_bytes,
            monitor_index=monitor_index,
            width=grab.size[0],
            height=grab.size[1],
            timestamp=time.time(),
            origin_x=x,
            origin_y=y,
        )

    def close(self) -> None:
        """Release the mss handle on every thread that touched this instance.

        Idempotent. Subsequent capture calls raise :class:`ScreenCaptureError`.
        """
        self._closed = True
        sct = getattr(self._tls, "sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception:  # noqa: BLE001
                pass
            self._tls.sct = None


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_capture_singleton: Optional[ScreenCapture] = None
_capture_lock = threading.Lock()


def get_screen_capture() -> ScreenCapture:
    """Module-level singleton accessor.

    The orchestrator constructs the production :class:`ScreenCapture`
    on init and pushes it via :func:`set_screen_capture`. Callers that
    arrive before the orchestrator (tests, scripts) get a default
    instance with taint recording enabled.
    """
    global _capture_singleton
    if _capture_singleton is None:
        with _capture_lock:
            if _capture_singleton is None:
                _capture_singleton = ScreenCapture()
    return _capture_singleton


def set_screen_capture(capture: Optional[ScreenCapture]) -> None:
    """Test / orchestrator hook -- swap the singleton."""
    global _capture_singleton
    with _capture_lock:
        _capture_singleton = capture
