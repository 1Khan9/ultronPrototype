"""Broadcast mirror -- tee EVERY line Kenning speaks to a second output.

The user captures a single, isolated audio source in OBS (a free VoiceMeeter
virtual input) so stream viewers hear Kenning -- both normal conversation AND
team relay -- WITHOUT either of the two things that would otherwise break:

* losing the speaker output the user themselves listens to, or
* leaking non-team audio into the microphone bus teammates hear.

The mirror is purely additive: it opens its OWN output stream to a SEPARATE
device and writes a copy of each clip there. It never touches ``output_device``
(the speakers) and is routing-independent of the relay's mic B-bus, so picking
a broadcast device that viewers hear can never make teammates hear normal
conversation -- that separation lives in VoiceMeeter's bus matrix, which this
code does not reconfigure.

Design constraints:

* **Zero added latency on the speaker path.** The speaker write loop is the
  latency-critical one. ``submit`` only copies the PCM and hands it to a
  bounded queue (drop-oldest under backpressure); a daemon thread does the
  actual blocking device write. The speaker path never waits on the mirror.
* **Fail-open.** A missing/unresolvable device, a closed stream, or a backend
  hiccup must never affect the turn loop -- the mirror just goes quiet and
  retries on the next clip.
* **Config-reactive.** The device can be (re)selected live from the settings
  GUI. ``configure`` swaps the target; the consumer reopens on the next clip.
* **Near-free when off.** With no device configured (the default), ``submit``
  is a single attribute check and an immediate return -- no copy, no queue, no
  thread. The mirror only spins up once a device is actually selected.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional, Union

import numpy as np

from kenning.utils.logging import get_logger

logger = get_logger("audio.broadcast")

DeviceSpec = Union[str, int]

# Bounded queue: a handful of clips is plenty of slack. If the consumer ever
# falls behind (a wedged device), we drop the OLDEST queued clip rather than
# block the producer -- viewers missing 50 ms of stale audio is invisible; a
# stalled speaker path is not.
_QUEUE_MAXSIZE = 16


class BroadcastSink:
    """A daemon-backed mirror that writes spoken clips to a second device.

    One instance is shared process-wide (see :func:`get_broadcast_sink`). It is
    safe to ``submit`` from any thread -- the playback engine's speaker thread,
    the relay path, etc. -- because all the producer does is copy + enqueue.
    """

    def __init__(self, *, resolver=None, stream_factory=None,
                 name: str = "broadcast") -> None:
        # Label used in the daemon thread name + INFO logs so a second
        # instance (the local monitor) is distinguishable from the broadcast
        # mirror in logs.
        self._name = name
        self._device_spec: Optional[DeviceSpec] = None
        self._resolved_index: Optional[int] = None
        self._lock = threading.Lock()
        self._queue: "queue.Queue[Optional[tuple[np.ndarray, int]]]" = queue.Queue(
            maxsize=_QUEUE_MAXSIZE
        )
        self._thread: Optional[threading.Thread] = None
        # Set by ``cancel_current()`` ("Ultron, stop" barge-in) to abort the
        # clip currently being written at the next 50 ms block boundary and to
        # drop everything still queued. Cleared on the next ``submit`` so a
        # later clip plays normally.
        self._cancel = threading.Event()
        self._stream = None
        self._stream_sr: Optional[int] = None
        # Generation counter bumped on every reconfigure so the consumer knows
        # to drop its current stream and re-resolve the (possibly new) device.
        self._generation = 0
        self._stream_generation = -1
        # Test seams (default None -> the real sounddevice / device resolver).
        # ``resolver(spec, "output") -> Optional[int]``;
        # ``stream_factory(samplerate, channels, dtype, device) -> stream``.
        self._resolver = resolver
        self._stream_factory = stream_factory

    # -- producer side -----------------------------------------------------

    def configure(self, device: Optional[DeviceSpec]) -> None:
        """Set (or clear) the broadcast target device.

        ``device`` may be a PortAudio index or a case-insensitive name
        substring (same grammar as ``audio.output_device`` /
        ``relay_speech.output_device``). ``None`` or an empty string disables
        the mirror. Idempotent: re-configuring with the same value is a no-op.
        """
        norm: Optional[DeviceSpec]
        if device is None:
            norm = None
        elif isinstance(device, str):
            norm = device.strip() or None
        else:
            norm = device
        with self._lock:
            if norm == self._device_spec:
                return
            self._device_spec = norm
            self._generation += 1
            logger.info("%s mirror device set to %r", self._name, norm)
            if norm is not None and (self._thread is None or not self._thread.is_alive()):
                self._start_consumer_locked()

    @property
    def enabled(self) -> bool:
        return self._device_spec is not None

    def submit(self, pcm: np.ndarray, sample_rate: int) -> None:
        """Tee one clip to the broadcast device. Non-blocking, fail-open.

        Called on the speaker path, so it must stay cheap: when no device is
        configured it returns immediately (no copy). Otherwise it copies the
        PCM (the caller may reuse/free its buffer) and enqueues it, dropping
        the oldest queued clip if the consumer has fallen behind.
        """
        # Fast path: mirror off -> one attribute read and out.
        if self._device_spec is None:
            return
        if pcm is None:
            return
        # A fresh clip clears any prior "stop" so it plays normally.
        self._cancel.clear()
        try:
            data = np.asarray(pcm)
            if data.size == 0:
                return
            # Own a contiguous int16 copy -- the producer's buffer is not ours.
            if data.dtype != np.int16:
                clipped = np.clip(data.astype(np.float32), -32768.0, 32767.0)
                data = clipped.astype(np.int16)
            data = np.ascontiguousarray(data).copy()
        except Exception as e:  # noqa: BLE001 - never let a tee break the turn
            logger.debug("broadcast submit: copy failed (%s)", e)
            return
        try:
            self._queue.put_nowait((data, int(sample_rate)))
        except queue.Full:
            # Drop the oldest, then enqueue the newest. Best-effort.
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait((data, int(sample_rate)))
            except queue.Full:
                pass

    def cancel_current(self) -> None:
        """Abort the clip being written NOW and drop everything still queued.

        Used by the "Ultron, stop" barge-in to silence this mirror immediately.
        The consumer stays alive (device unchanged); the next ``submit`` clears
        the flag and resumes normal playback. Best-effort, never raises.
        """
        self._cancel.set()
        # Drain anything queued so a backlog doesn't resume after the cut.
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            except Exception:                                    # noqa: BLE001
                break

    def close(self) -> None:
        """Stop the consumer and release the device. Best-effort/idempotent."""
        with self._lock:
            self._device_spec = None
            self._generation += 1
            thread = self._thread
            self._thread = None
        if thread is not None:
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            thread.join(timeout=2.0)

    # -- consumer side -----------------------------------------------------

    def _start_consumer_locked(self) -> None:
        """Spin up the daemon consumer. Caller holds ``self._lock``."""
        self._thread = threading.Thread(
            target=self._consume_loop, daemon=True, name=f"{self._name}-mirror",
        )
        self._thread.start()

    def _consume_loop(self) -> None:
        while True:
            try:
                item = self._queue.get()
            except Exception:  # noqa: BLE001
                break
            if item is None:
                break
            # If the device was cleared while this item waited, drop it.
            if self._device_spec is None:
                continue
            pcm, sr = item
            try:
                self._write_clip(pcm, sr)
            except Exception as e:  # noqa: BLE001 - fail-open, retry next clip
                logger.debug("broadcast write failed (%s); closing stream", e)
                self._close_stream()
        self._close_stream()

    def _ensure_stream(self, sr: int):
        """Open (or reuse) the output stream for ``sr``. Returns the stream or
        ``None`` if the device can't be resolved/opened (caller stays quiet)."""
        gen = self._generation
        if (
            self._stream is not None
            and self._stream_sr == sr
            and self._stream_generation == gen
        ):
            return self._stream
        # Device changed, sr changed, or first open -> (re)open.
        self._close_stream()
        spec = self._device_spec
        if spec is None:
            return None
        try:
            if self._resolver is not None:
                idx = self._resolver(spec, "output")
            else:
                from kenning.audio.devices import resolve_device

                idx = resolve_device(spec, "output")
        except Exception as e:  # noqa: BLE001
            logger.debug("broadcast device %r unresolved (%s)", spec, e)
            return None
        if idx is None:
            logger.debug("broadcast device %r unresolved", spec)
            return None
        try:
            # Lowest-latency stream for this mirror device: WASAPI low-latency
            # + auto-convert (OBS/Voicemeeter AUX) when available, else MME
            # latency='low'. ``_stream_factory`` (test seam) is honoured.
            from kenning.audio.devices import make_output_stream

            stream = make_output_stream(
                idx, sr, 2, "int16", stream_factory=self._stream_factory,
            )
            stream.start()
        except Exception as e:  # noqa: BLE001
            logger.debug("broadcast stream open failed for device %r (%s)", spec, e)
            return None
        self._stream = stream
        self._stream_sr = sr
        self._stream_generation = gen
        self._resolved_index = idx
        logger.info("%s mirror streaming to device index %s @ %d Hz",
                    self._name, idx, sr)
        return stream

    def _write_clip(self, pcm: np.ndarray, sr: int) -> None:
        stream = self._ensure_stream(sr)
        if stream is None:
            return
        # Mono -> stereo (centered) for VoiceMeeter virtual inputs, which are
        # stereo strips; a mono write would only feed the left channel.
        if pcm.ndim == 1:
            stereo = np.column_stack((pcm, pcm)).astype(np.int16, copy=False)
        elif pcm.ndim == 2 and pcm.shape[1] == 1:
            stereo = np.column_stack((pcm[:, 0], pcm[:, 0])).astype(np.int16, copy=False)
        else:
            stereo = np.ascontiguousarray(pcm.astype(np.int16, copy=False))
        block = max(1, int(sr * 0.05))
        for start in range(0, stereo.shape[0], block):
            # Drop mid-clip if the device was cleared (fast reaction to GUI off)
            # OR an "Ultron, stop" barge-in cancelled playback.
            if self._device_spec is None or self._cancel.is_set():
                return
            stream.write(stereo[start: start + block])

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        self._stream_sr = None
        self._stream_generation = -1
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Process-wide singleton + thin module-level helpers
# ---------------------------------------------------------------------------

_SINK: Optional[BroadcastSink] = None
_SINK_LOCK = threading.Lock()


def get_broadcast_sink() -> BroadcastSink:
    """Return the shared :class:`BroadcastSink`, creating it on first use."""
    global _SINK
    if _SINK is None:
        with _SINK_LOCK:
            if _SINK is None:
                _SINK = BroadcastSink()
    return _SINK


def submit(pcm: np.ndarray, sample_rate: int) -> None:
    """Module-level tee used by the playback engines + relay path.

    Cheap no-op when the mirror is off, so engines can call it unconditionally
    on the hot path.
    """
    sink = _SINK
    if sink is None or sink._device_spec is None:  # noqa: SLF001 - fast path
        return
    sink.submit(pcm, sample_rate)


def cancel_current() -> None:
    """Module-level "stop" hook: abort the broadcast mirror's current clip.

    No-op when the mirror was never created/configured. Used by the
    "Ultron, stop" barge-in to silence the OBS feed mid-callout.
    """
    sink = _SINK
    if sink is None:
        return
    try:
        sink.cancel_current()
    except Exception:                                            # noqa: BLE001
        pass


def configure_from_config() -> None:
    """(Re)read ``audio.broadcast_device`` from config and apply it.

    Called at orchestrator startup and whenever the settings GUI signals a
    live audio-routing change. Fail-open: a config read error leaves the mirror
    in its current state.
    """
    try:
        from kenning.config import get_config

        device = get_config().audio.broadcast_device
    except Exception as e:  # noqa: BLE001
        logger.debug("broadcast configure_from_config: config read failed (%s)", e)
        return
    get_broadcast_sink().configure(device)
