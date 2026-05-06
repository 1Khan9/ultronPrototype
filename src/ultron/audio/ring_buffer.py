"""A thread-safe ring buffer of recent audio samples.

When VAD fires "speech started", the orchestrator pulls a snapshot from the
ring so the front of the utterance isn't clipped. The buffer stores raw
mono float32 samples — not chunks — so the snapshot length is independent of
the audio callback's blocksize.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque

import numpy as np


class RingBuffer:
    """Fixed-capacity FIFO of audio samples."""

    def __init__(self, capacity_samples: int) -> None:
        """
        Args:
            capacity_samples: Maximum number of mono samples to retain.
        """
        if capacity_samples <= 0:
            raise ValueError("capacity_samples must be positive")
        self._capacity = capacity_samples
        self._buffer: Deque[float] = deque(maxlen=capacity_samples)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)

    def write(self, samples: np.ndarray) -> None:
        """Append samples; oldest are evicted automatically."""
        if samples.ndim != 1:
            samples = samples.reshape(-1)
        with self._lock:
            self._buffer.extend(samples.tolist())

    def snapshot(self) -> np.ndarray:
        """Return a contiguous copy of the current contents."""
        with self._lock:
            return np.array(self._buffer, dtype=np.float32)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
