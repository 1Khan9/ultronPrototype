"""Whisper engine tests.

These are slow (~10s on first run) because they load a real model. Mark them
with ``@pytest.mark.slow`` so the default `pytest -m "not slow"` skips them.
"""

from __future__ import annotations

import os

import numpy as np
import pytest


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
    reason="set PYTEST_RUN_GPU_TESTS=1 to load CUDA models",
)
def test_whisper_transcribes_silence_to_empty():
    from ultron.transcription import WhisperEngine

    with WhisperEngine() as stt:
        silence = np.zeros(16000, dtype=np.float32)  # 1s of silence
        text = stt.transcribe(silence)
        assert isinstance(text, str)
        # silence should yield empty (or nearly empty) text
        assert len(text) <= 5


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
    reason="set PYTEST_RUN_GPU_TESTS=1 to load CUDA models",
)
def test_whisper_handles_empty_input():
    from ultron.transcription import WhisperEngine

    with WhisperEngine() as stt:
        assert stt.transcribe(np.zeros(0, dtype=np.float32)) == ""
