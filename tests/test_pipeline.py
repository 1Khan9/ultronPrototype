"""Pipeline-level smoke test.

Drives the orchestrator with a synthetic audio source. Mocks out the audio
hardware so it can run in CI, but still loads STT/LLM/TTS — gated on
PYTEST_RUN_GPU_TESTS.
"""

from __future__ import annotations

import os
import threading
import time

import numpy as np
import pytest


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
    reason="set PYTEST_RUN_GPU_TESTS=1 to load full pipeline",
)
def test_orchestrator_constructs_and_shuts_down():
    """Verify all components load without raising."""
    from kenning.pipeline import Orchestrator

    orch = Orchestrator()
    # Don't run(); just confirm shutdown is graceful.
    orch.shutdown()


def test_pipeline_imports_clean():
    """Pure-import smoke test that doesn't touch heavy components."""
    from kenning.audio.ring_buffer import RingBuffer
    from kenning.audio.vad import SpeechEvent
    from kenning.audio import VoiceActivityDetector  # noqa: F401

    assert SpeechEvent.SPEECH_START.value == "speech_start"
    rb = RingBuffer(8)
    rb.write(np.ones(4, dtype=np.float32))
    assert len(rb) == 4
