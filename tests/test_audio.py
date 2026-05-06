"""Audio module tests.

Capture-with-real-mic tests are skipped by default (CI has no audio device);
they only run if PYTEST_RUN_MIC_TESTS=1 is set in the environment.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from ultron.audio.ring_buffer import RingBuffer


# ---- RingBuffer (pure, no I/O) -------------------------------------------


def test_ring_buffer_retains_recent_samples():
    rb = RingBuffer(capacity_samples=10)
    rb.write(np.arange(15, dtype=np.float32))
    snap = rb.snapshot()
    assert snap.shape == (10,)
    assert np.array_equal(snap, np.arange(5, 15, dtype=np.float32))


def test_ring_buffer_clear():
    rb = RingBuffer(capacity_samples=8)
    rb.write(np.ones(4, dtype=np.float32))
    rb.clear()
    assert len(rb) == 0
    assert rb.snapshot().shape == (0,)


def test_ring_buffer_handles_2d_input():
    rb = RingBuffer(capacity_samples=10)
    # sounddevice gives shape (frames, channels); RingBuffer must flatten.
    chunk = np.array([[1.0], [2.0], [3.0]], dtype=np.float32)
    rb.write(chunk)
    assert np.array_equal(rb.snapshot(), np.array([1, 2, 3], dtype=np.float32))


def test_ring_buffer_rejects_zero_capacity():
    with pytest.raises(ValueError):
        RingBuffer(capacity_samples=0)


# ---- AudioCapture (real device) ------------------------------------------


@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_MIC_TESTS") != "1",
    reason="set PYTEST_RUN_MIC_TESTS=1 to enable mic tests",
)
def test_audio_capture_produces_chunks():
    from ultron.audio.capture import AudioCapture

    with AudioCapture(blocksize=512) as mic:
        chunk = mic.get_chunk(timeout=2.0)
        assert chunk is not None
        assert chunk.dtype == np.float32
        assert chunk.shape == (512,)
