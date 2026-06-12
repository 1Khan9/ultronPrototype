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
from kenning.audio.devices import describe_device, resolve_device
from kenning.utils.logging import get_logger

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
        max_queue_size: int = 1024,
        input_gain_db: Optional[float] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.configured_device = device
        self.device: Optional[int] = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_size)
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()
        # 2026-06-12 observability fix: the old `_overrun_warned` latch
        # warned ONCE per process forever, so recurrence within a
        # session was invisible ("sporadic" warnings in the live log
        # were an artifact of warn-once, not true frequency). Counters
        # below reset per start() so each capture session accounts for
        # itself. The audio thread only COUNTS (plus a single first-
        # occurrence warning); recurrence is reported from drain() on
        # the consumer thread, so the callback never does repeated
        # logging I/O.
        self._status_flag_count = 0     # PortAudio status flags this session
        self._status_reported = 0       # last count reported via drain()
        self._dropped_blocks = 0        # queue-full drop-oldest count
        self._dropped_reported = 0
        # 2026-05-09 audio-quality pass: pre-amp applied in the audio
        # callback. ``input_gain_db=None`` -> read from config (allows
        # tests to construct AudioCapture without a config singleton).
        if input_gain_db is None:
            try:
                from kenning.config import get_config
                input_gain_db = float(getattr(get_config().audio, "input_gain_db", 0.0))
            except Exception:
                input_gain_db = 0.0
        self.input_gain_db = float(input_gain_db)
        # Linear multiplier; cached so the audio thread doesn't recompute.
        # 0 dB -> 1.0 (no-op fast path).
        self._gain_linear = 1.0 if self.input_gain_db == 0.0 else float(
            10.0 ** (self.input_gain_db / 20.0)
        )

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
            # Fresh accounting per stop/start cycle (e.g. gaming-mode
            # toggles re-open the stream). Reset BEFORE the stream
            # opens so the first callbacks are never wiped.
            self._status_flag_count = 0
            self._status_reported = 0
            self._dropped_blocks = 0
            self._dropped_reported = 0
            try:
                self.device = resolve_device(self.configured_device, "input")
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
                describe_device(self.device, "input"),
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
        # Consumer-thread side: report accounting accumulated since
        # the last report (the audio thread itself never logs beyond
        # the single first-occurrence status warning).
        flags = self._status_flag_count
        if flags > max(self._status_reported, 1):
            logger.warning(
                "Audio status flags recurred: %d occurrences this "
                "capture session (host input buffer overruns; consumer "
                "busy)", flags,
            )
        self._status_reported = flags
        dropped = self._dropped_blocks
        if dropped > self._dropped_reported:
            logger.debug(
                "capture queue dropped %d oldest blocks since capture "
                "start (consumer busy)", dropped,
            )
            self._dropped_reported = dropped

    def qsize(self) -> int:
        return self._queue.qsize()

    @property
    def status_flag_count(self) -> int:
        """Cumulative PortAudio status flags (e.g. input overflow)
        observed this capture session."""
        return self._status_flag_count

    @property
    def dropped_blocks(self) -> int:
        """Queue-full drop-oldest count this capture session."""
        return self._dropped_blocks

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
            # input_overflow / input_underflow / etc. (PortAudio
            # host-buffer overrun: the callback wasn't serviced in
            # time, usually GIL contention during a CPU-heavy turn).
            # ONLY the first occurrence logs from the audio thread
            # (logging does handler I/O under the process-wide logging
            # lock, which must never recur on this thread); recurrence
            # is counted here and reported from drain() consumer-side.
            self._status_flag_count += 1
            if self._status_flag_count == 1:
                logger.warning("Audio status flag: %s", status)

        # Copy because sounddevice reuses the buffer.
        chunk = indata[:, 0].copy() if self.channels == 1 else indata.copy()
        # Apply pre-amp gain (audio-quality pass). Fast path skips the
        # multiply when gain is 0 dB. Float audio is in [-1, 1]; we
        # clip to that range to prevent wraparound on int16 conversion
        # downstream.
        if self._gain_linear != 1.0:
            chunk = chunk * self._gain_linear
            if self._gain_linear > 1.0:
                # Hard-clip to prevent distortion from over-gain. Soft
                # limiting would be smoother but adds a small per-block
                # CPU cost on the audio thread; clipping is one numpy
                # call and is acceptable for a single-mic prototype.
                np.clip(chunk, -1.0, 1.0, out=chunk)
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            # Drop oldest to make room — better than blocking the audio thread.
            # Counted (never logged here -- this runs on the audio
            # thread); drain() reports the total from the consumer side.
            self._dropped_blocks += 1
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except queue.Empty:
                pass
