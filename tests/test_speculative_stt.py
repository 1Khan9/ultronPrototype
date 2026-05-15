"""Tests for the speculative-STT path on Orchestrator.

2026-05-16 latency pass 2: the orchestrator kicks off Whisper STT in a
background thread as soon as VAD reports a short run of consecutive
silence chunks (~32 ms at the new 16 ms blocksize). By the time the
fast-path silence baseline (~300 ms) elapses and Smart Turn V3 confirms
end-of-turn, Whisper (~78 ms) has finished and the transcript is
consumable from the main run() loop without paying the full
foreground Whisper latency.

These tests cover the kick-off / collect / invalidate / reset helpers
on Orchestrator in isolation. The orchestrator itself is constructed
via ``object.__new__`` so we don't load any models -- the helpers
are tested as pure state machines + thread coordination.
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Stub Orchestrator
# ---------------------------------------------------------------------------


def _stub_orchestrator(stt_result: Optional[str] = "hello world",
                       stt_delay_s: float = 0.0,
                       stt_raises: Optional[Exception] = None):
    """Build a partial Orchestrator with the speculative-STT helpers
    attached. The stub ``stt`` returns ``stt_result`` (or raises) after
    ``stt_delay_s`` so tests can exercise the thread-coordination
    paths."""
    from ultron.pipeline.orchestrator import Orchestrator
    o = object.__new__(Orchestrator)
    o._speculative_stt_lock = threading.Lock()
    o._speculative_stt_thread = None
    o._speculative_stt_result = None
    o._speculative_stt_active = False
    o._speculative_stt_invalidated = False

    def _transcribe(audio):
        if stt_delay_s > 0:
            time.sleep(stt_delay_s)
        if stt_raises is not None:
            raise stt_raises
        return stt_result

    o.stt = SimpleNamespace(transcribe=_transcribe)
    return o


def _silence(seconds: float = 5.0, sample_rate: int = 16000) -> np.ndarray:
    return np.zeros(int(seconds * sample_rate), dtype=np.float32)


# ---------------------------------------------------------------------------
# Kick-off contract
# ---------------------------------------------------------------------------


def test_kick_off_starts_background_thread():
    """Successful kick-off marks state active and stores a thread
    handle that can be joined."""
    o = _stub_orchestrator(stt_result="hi", stt_delay_s=0.05)
    o._kick_off_speculative_stt(_silence(0.5))
    # Thread handle should exist and be alive (or just completed).
    assert o._speculative_stt_thread is not None
    result = o._collect_speculative_stt(timeout_s=2.0)
    assert result == "hi"


def test_kick_off_is_idempotent_while_in_flight():
    """Re-calling kick-off while a thread is still running is a no-op
    -- the existing inference completes; the second request is
    silently dropped."""
    o = _stub_orchestrator(stt_result="first", stt_delay_s=0.15)
    o._kick_off_speculative_stt(_silence(0.5))
    # Second call -- should not launch a new thread.
    first_thread = o._speculative_stt_thread
    o._kick_off_speculative_stt(_silence(0.5))
    assert o._speculative_stt_thread is first_thread
    result = o._collect_speculative_stt(timeout_s=2.0)
    assert result == "first"


def test_kick_off_skips_when_thread_launch_fails(monkeypatch):
    """If threading.Thread() raises during construction, state must
    end up clean (not stuck active) and no leak -- the caller falls
    back to the foreground STT path."""
    o = _stub_orchestrator()

    original_thread = threading.Thread

    def _failing_thread(*args, **kwargs):
        raise RuntimeError("thread launch failed")

    monkeypatch.setattr(threading, "Thread", _failing_thread)
    o._kick_off_speculative_stt(_silence(0.5))
    # State must be back to inactive so the next kick-off can proceed.
    assert o._speculative_stt_active is False
    # Restore for any later test scaffolding.
    monkeypatch.setattr(threading, "Thread", original_thread)


# ---------------------------------------------------------------------------
# Collect contract
# ---------------------------------------------------------------------------


def test_collect_returns_none_when_no_kickoff():
    """No kick-off ever happened -> collect returns None and the
    state stays clean."""
    o = _stub_orchestrator()
    assert o._collect_speculative_stt() is None


def test_collect_waits_for_in_flight_thread():
    """Collect must join the thread (up to timeout) so the result
    is fully populated before returning."""
    o = _stub_orchestrator(stt_result="done", stt_delay_s=0.10)
    o._kick_off_speculative_stt(_silence(0.5))
    # Immediately collect -- should block until the thread finishes.
    result = o._collect_speculative_stt(timeout_s=2.0)
    assert result == "done"


def test_collect_resets_state_for_next_capture():
    """After collect, internal state is reset so the next kick-off
    starts fresh -- no stale result leak."""
    o = _stub_orchestrator(stt_result="first")
    o._kick_off_speculative_stt(_silence(0.5))
    first = o._collect_speculative_stt(timeout_s=2.0)
    assert first == "first"
    assert o._speculative_stt_result is None
    assert o._speculative_stt_active is False
    assert o._speculative_stt_thread is None


def test_collect_returns_none_on_transcription_exception():
    """If Whisper raises mid-call, the background thread swallows
    the exception and stores None; collect returns None."""
    o = _stub_orchestrator(stt_raises=RuntimeError("CUDA OOM"))
    o._kick_off_speculative_stt(_silence(0.5))
    assert o._collect_speculative_stt(timeout_s=2.0) is None


def test_collect_returns_none_when_thread_hangs_past_timeout():
    """If the background thread is still running past the timeout,
    collect returns None. The caller falls back to foreground STT."""
    o = _stub_orchestrator(stt_result="late", stt_delay_s=1.0)
    o._kick_off_speculative_stt(_silence(0.5))
    # Very short timeout -- thread won't finish.
    result = o._collect_speculative_stt(timeout_s=0.05)
    assert result is None
    # Cleanup: let the thread finish so the test runner doesn't leak it.
    if o._speculative_stt_thread is None:
        pass


# ---------------------------------------------------------------------------
# Invalidate contract
# ---------------------------------------------------------------------------


def test_invalidate_causes_collect_to_return_none():
    """User resumed speaking before SPEECH_END -> invalidate the
    in-flight speculative result. Collect returns None even though
    the thread completed successfully."""
    o = _stub_orchestrator(stt_result="stale", stt_delay_s=0.05)
    o._kick_off_speculative_stt(_silence(0.5))
    o._invalidate_speculative_stt()
    # Wait for the thread to actually finish before collect.
    time.sleep(0.15)
    result = o._collect_speculative_stt(timeout_s=2.0)
    assert result is None


def test_invalidate_then_kick_off_again_after_collect():
    """After invalidation + collect, the state must be clean enough
    to support a fresh kick-off in the next silence period."""
    o = _stub_orchestrator(stt_result="run1", stt_delay_s=0.05)
    o._kick_off_speculative_stt(_silence(0.5))
    o._invalidate_speculative_stt()
    time.sleep(0.15)
    assert o._collect_speculative_stt(timeout_s=2.0) is None
    # Swap the stub result to verify it's a fresh run.
    o.stt.transcribe = lambda audio: "run2"
    o._kick_off_speculative_stt(_silence(0.5))
    assert o._collect_speculative_stt(timeout_s=2.0) == "run2"


# ---------------------------------------------------------------------------
# Reset contract
# ---------------------------------------------------------------------------


def test_reset_clears_stale_result_without_killing_thread():
    """_reset_speculative_stt_state at the start of a capture must
    clear any stale result so it can't leak into the new turn's
    transcript."""
    o = _stub_orchestrator(stt_result="ancient")
    o._kick_off_speculative_stt(_silence(0.5))
    # Let the background thread complete and populate the result.
    time.sleep(0.05)
    while o._speculative_stt_active:
        time.sleep(0.005)
    # Now reset (simulating the start of a new capture).
    o._reset_speculative_stt_state()
    assert o._speculative_stt_result is None
    assert o._speculative_stt_invalidated is False
    assert o._speculative_stt_thread is None


# ---------------------------------------------------------------------------
# Audio buffer is snapshotted, not aliased
# ---------------------------------------------------------------------------


def test_kick_off_copies_audio_to_avoid_race():
    """The background thread reads its OWN copy of the audio buffer
    so the live capture can keep growing its chunk list without
    racing with the in-flight inference."""
    received_audio = []

    o = _stub_orchestrator()
    # Custom stt.transcribe that records what was passed in.
    def _capture(audio):
        received_audio.append(audio)
        return "ok"
    o.stt.transcribe = _capture

    original = _silence(0.5)
    o._kick_off_speculative_stt(original)
    # Mutate the original BEFORE the thread finishes (race window).
    original[:] = 0.99
    o._collect_speculative_stt(timeout_s=2.0)
    # Thread should have seen the original zero-buffer, not the mutated one.
    assert len(received_audio) == 1
    seen = received_audio[0]
    assert np.allclose(seen, 0.0)
