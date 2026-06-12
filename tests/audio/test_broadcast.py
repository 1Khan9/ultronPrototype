"""Tests for the broadcast mirror (second OBS-capture output).

The mirror tees EVERY spoken line to a separate device for stream viewers
without disturbing the speaker path or the relay mic bus. These tests cover:

* the off state is a true no-op (no copy, no thread, no enqueue),
* ``submit`` owns an independent int16 copy (producer may reuse its buffer),
* the bounded queue drops the OLDEST clip under backpressure (never blocks),
* mono clips are expanded to stereo for VoiceMeeter strips,
* the consumer end-to-end writes a submitted clip to the (faked) device,
* clearing the device disables the mirror again.

No real audio backend is touched: the device resolver and output-stream
factory are injected test seams.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from kenning.audio.broadcast import BroadcastSink, _QUEUE_MAXSIZE


class _FakeStream:
    """Records every block written; signals once ``min_frames`` arrive."""

    def __init__(self, *, min_frames: int = 1):
        self.blocks: list[np.ndarray] = []
        self.started = False
        self.closed = False
        self._min = min_frames
        self.enough = threading.Event()
        self._frames = 0

    def start(self):
        self.started = True

    def write(self, data):
        self.blocks.append(np.array(data, copy=True))
        self._frames += len(data)
        if self._frames >= self._min:
            self.enough.set()

    def stop(self):
        pass

    def close(self):
        self.closed = True

    def written(self) -> np.ndarray:
        if not self.blocks:
            return np.empty((0, 2), dtype=np.int16)
        return np.concatenate(self.blocks, axis=0)


def test_off_is_a_true_noop():
    sink = BroadcastSink()
    assert sink.enabled is False
    sink.submit(np.ones(100, dtype=np.int16), 24000)
    assert sink._queue.qsize() == 0          # nothing enqueued
    assert sink._thread is None              # no consumer spun up


def test_submit_owns_an_independent_copy():
    sink = BroadcastSink()
    sink._device_spec = "FakeDev"            # enable WITHOUT starting consumer
    original = np.arange(10, dtype=np.int16)
    sink.submit(original, 24000)
    original[:] = 0                          # mutate the producer's buffer
    queued, sr = sink._queue.get_nowait()
    assert sr == 24000
    assert np.array_equal(queued, np.arange(10, dtype=np.int16))  # copy intact


def test_float_input_is_converted_to_int16():
    sink = BroadcastSink()
    sink._device_spec = "FakeDev"
    sink.submit(np.array([0.0, 1.0, -1.0], dtype=np.float32), 24000)
    queued, _ = sink._queue.get_nowait()
    assert queued.dtype == np.int16


def test_drop_oldest_under_backpressure():
    sink = BroadcastSink()
    sink._device_spec = "FakeDev"            # no consumer -> queue fills
    # Submit one more than capacity; each clip tagged by its first sample.
    for i in range(_QUEUE_MAXSIZE + 1):
        sink.submit(np.full(4, i, dtype=np.int16), 24000)
    assert sink._queue.qsize() == _QUEUE_MAXSIZE
    # Oldest (tag 0) must have been dropped; newest (tag MAXSIZE) survives.
    tags = []
    while sink._queue.qsize():
        clip, _ = sink._queue.get_nowait()
        tags.append(int(clip[0]))
    assert 0 not in tags
    assert _QUEUE_MAXSIZE in tags


def test_configure_idempotent_same_value():
    sink = BroadcastSink()
    sink.configure("DevA")
    gen1 = sink._generation
    sink.configure("DevA")                   # same -> no-op
    assert sink._generation == gen1
    sink.configure("DevB")                   # changed -> bump
    assert sink._generation == gen1 + 1
    sink.close()


def test_empty_string_disables():
    sink = BroadcastSink()
    sink.configure("DevA")
    assert sink.enabled is True
    sink.configure("   ")                    # whitespace -> off
    assert sink.enabled is False


def test_consumer_writes_stereo_clip_end_to_end():
    stream = _FakeStream(min_frames=200)
    sink = BroadcastSink(
        resolver=lambda spec, kind: 7,        # any index
        stream_factory=lambda **kw: stream,
    )
    sink.configure("FakeDev")                 # starts the consumer thread
    mono = (np.ones(200, dtype=np.int16) * 1234)
    sink.submit(mono, 24000)
    assert stream.enough.wait(timeout=5.0), "consumer never wrote the clip"
    out = stream.written()
    assert out.ndim == 2 and out.shape[1] == 2     # stereo
    assert out.shape[0] == 200
    assert np.all(out == 1234)                     # both channels carry the clip
    sink.close()
    # Generous join window: close() signals + joins the daemon.
    time.sleep(0.05)
    assert stream.closed is True


def test_close_is_idempotent():
    sink = BroadcastSink()
    sink.configure("DevA")
    sink.close()
    sink.close()                              # second close must not raise
    assert sink.enabled is False


def test_orchestrator_gui_action_toggles_the_mirror_live():
    """The settings-panel 'Broadcast output' dropdown emits a
    ``broadcast_device`` action; dispatching it must enable/disable the shared
    sink without a restart (no clip is submitted, so no real device is opened).
    """
    from kenning.pipeline.orchestrator import Orchestrator
    from kenning.audio import broadcast

    broadcast._SINK = None                    # fresh shared sink for the test
    spoken: list[str] = []

    class _Stub:
        def _speak(self, text):
            spoken.append(text)

        _apply_gui_action = Orchestrator._apply_gui_action

    stub = _Stub()
    stub._apply_gui_action("broadcast_device", "Voicemeeter VAIO3 Input")
    assert broadcast.get_broadcast_sink().enabled is True
    assert any("set" in s.lower() for s in spoken)

    stub._apply_gui_action("broadcast_device", "")     # blank -> off
    assert broadcast.get_broadcast_sink().enabled is False
    assert any("clear" in s.lower() for s in spoken)

    broadcast.get_broadcast_sink().close()
    broadcast._SINK = None
