"""Microphone capture.

A `sounddevice.InputStream` callback runs on a high-priority audio thread.
The callback's only job is to push the chunk onto a queue — anything heavier
risks underrun and dropouts. Consumers (VAD, wake word) pull from the queue
on their own threads.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("audio.capture")


class AudioCaptureError(RuntimeError):
    """Raised when the input stream cannot be opened or recovered."""


class AudioCapture:
    """Continuous microphone capture into a thread-safe queue.

    Use as a context manager:

        with AudioCapture() as mic:
            chunk = mic.get_chunk(timeout=1.0)
    """

    def __init__(
        self,
        sample_rate: int = settings.SAMPLE_RATE,
        channels: int = settings.CHANNELS,
        blocksize: int = settings.BLOCKSIZE,
        device: Optional[str | int] = settings.AUDIO_DEVICE,
        max_queue_size: int = 256,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_size)
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        self._overrun_warned = False

    # --- context manager -----------------------------------------------------

    def __enter__(self) -> "AudioCapture":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Open the input stream and begin capturing."""
        with self._lock:
            if self._stream is not None:
                return
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    blocksize=self.blocksize,
                    dtype=settings.DTYPE,
                    device=self.device,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as e:
                self._stream = None
                raise AudioCaptureError(f"Failed to open input stream: {e}") from e
            logger.info(
                "Audio capture started: %d Hz, %d ch, blocksize=%d, device=%s",
                self.sample_rate,
                self.channels,
                self.blocksize,
                self.device or "default",
            )

    def stop(self) -> None:
        """Stop and close the input stream. Safe to call twice."""
        with self._lock:
            if self._stream is None:
                return
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning("Error closing audio stream: %s", e)
            finally:
                self._stream = None
            logger.info("Audio capture stopped")

    # --- consumer API --------------------------------------------------------

    def get_chunk(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Pop the next captured chunk, or return None on timeout."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """Discard any pending chunks. Useful right before re-arming wake word."""
        with self._queue.mutex:
            self._queue.queue.clear()

    def qsize(self) -> int:
        return self._queue.qsize()

    # --- audio thread callback ----------------------------------------------

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,  # noqa: ARG002
        status: sd.CallbackFlags,
    ) -> None:
        """Runs on the audio thread. Must not block."""
        if status:
            # input_overflow / input_underflow / etc.
            if not self._overrun_warned:
                logger.warning("Audio status flag: %s", status)
                self._overrun_warned = True

        # Copy because sounddevice reuses the buffer.
        chunk = indata[:, 0].copy() if self.channels == 1 else indata.copy()
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            # Drop oldest to make room — better than blocking the audio thread.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except queue.Empty:
                pass
