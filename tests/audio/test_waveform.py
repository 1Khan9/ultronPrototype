"""Tests for the voice waveform overlay sink (no Tk window is created here)."""
from __future__ import annotations

import threading
import time

import numpy as np

from kenning.audio import waveform as wf


def _speechy(sr=24000, secs=1.0):
    t = np.arange(int(sr * secs)) / sr
    sig = sum(np.sin(2 * np.pi * f * t) for f in (200, 600, 1800))
    env = (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)) ** 2
    return ((sig / 3.0) * env * 0.5 * 32767).astype(np.int16)


def test_analyze_clip_returns_frames():
    frames = wf.analyze_clip(_speechy(), 24000, fps=30, n_bands=60)
    assert len(frames) > 10
    level, bands = frames[len(frames) // 2]
    assert 0.0 <= level <= 1.0
    assert bands.shape == (60,)
    assert float(bands.max()) <= 1.0 + 1e-6
    assert float(bands.max()) > 0.0          # a voiced frame moves the bars


def test_analyze_clip_silence_is_calm():
    sil = np.zeros(24000, dtype=np.int16)
    frames = wf.analyze_clip(sil, 24000, fps=30, n_bands=48)
    # Silence still yields frames, but levels/bands stay ~0 (calm, not slammed).
    assert frames
    assert max(l for l, _ in frames) < 0.05
    assert max(float(b.max()) for _, b in frames) < 0.05


def test_analyze_clip_fail_open_on_garbage():
    assert wf.analyze_clip(np.array([], dtype=np.int16), 24000, fps=30, n_bands=60) == []
    assert wf.analyze_clip(np.zeros(4, dtype=np.int16), 0, fps=30, n_bands=60) == []


def test_submit_is_noop_when_disabled():
    sink = wf.WaveformSink()
    assert sink.enabled is False
    sink.submit(_speechy(), 24000)
    assert sink._queue.qsize() == 0          # nothing enqueued while off


def test_submit_enqueues_and_drops_oldest_when_enabled():
    sink = wf.WaveformSink()
    sink._enabled = True                     # flip flag WITHOUT starting the UI thread
    for _ in range(wf._QUEUE_MAXSIZE + 5):
        sink.submit(_speechy(secs=0.2), 24000)
    # Bounded queue: never exceeds maxsize (drop-oldest keeps newest).
    assert sink._queue.qsize() <= wf._QUEUE_MAXSIZE


def test_submit_copies_buffer():
    sink = wf.WaveformSink()
    sink._enabled = True
    buf = _speechy(secs=0.2)
    sink.submit(buf, 24000)
    buf[:] = 0                               # mutate caller buffer after submit
    queued, _sr = sink._queue.get_nowait()
    assert queued.any()                      # the sink kept its own copy


def test_module_submit_fast_path_no_sink():
    # With no global sink built, module submit must be a cheap no-op (no raise).
    wf._SINK = None
    wf.submit(_speechy(), 24000)             # should not raise / not build a sink
    assert wf._SINK is None


def test_pacer_survives_stale_sentinel():
    """A leftover None (e.g. from a prior disable) must NOT kill a fresh pacer
    -- only a None WHILE _stop is set ends it. (Regression: re-enable made the
    pacer read a stale sentinel and exit immediately.)"""
    sink = wf.WaveformSink()
    sink._enabled = True
    sink._stop.clear()
    th = threading.Thread(target=sink._pace_loop, daemon=True)
    th.start()
    try:
        sink._queue.put((_speechy(secs=0.1), 24000))
        time.sleep(0.1)
        sink._queue.put(None)                # stale sentinel, _stop NOT set
        time.sleep(0.15)
        assert th.is_alive(), "pacer exited on a stale sentinel"
    finally:
        sink._stop.set()
        sink._queue.put(None)                # real stop
        th.join(timeout=2.0)
    assert not th.is_alive()


def test_teardown_drains_queue_and_clears_threads():
    sink = wf.WaveformSink()
    sink._enabled = True
    for _ in range(3):
        sink.submit(_speechy(secs=0.1), 24000)
    assert sink._queue.qsize() > 0
    sink._teardown()                         # no threads running -> just drains
    assert sink._queue.qsize() == 0
    assert sink._pacer is None and sink._ui is None
