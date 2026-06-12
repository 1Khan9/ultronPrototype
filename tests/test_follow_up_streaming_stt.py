"""Tests for the 2026-06-12 follow-up streaming-STT lane.

Live finding: on the production Moonshine streaming arch, WARM-window
follow-up captures paid a ~700 ms SYNCHRONOUS re-transcribe in run()'s
foreground STT call -- the speculative-STT lane deliberately no-ops on
streaming engines (race guard), and the streaming lane was wired only
into the COLD path (``_capture_utterance``). The fix mirrors the
streaming session into ``_follow_up_listen``, starting at SPEECH_START.

Hermetic: ``object.__new__(Orchestrator)`` stubs (no models, no audio
devices), fake engines with call counters, scripted VAD/wake events.
"""

from __future__ import annotations

import inspect
import threading
import time
from types import SimpleNamespace
from typing import List, Optional

import numpy as np
import pytest

from kenning.audio.vad import SpeechEvent
from kenning.pipeline.orchestrator import Orchestrator, _FU_TIMEOUT, _FU_WAKE


# ---------------------------------------------------------------------------
# Structural pins (mirror tests/test_tts_preopen.py's source-inspection style)
# ---------------------------------------------------------------------------


def test_follow_up_listen_contains_streaming_helpers() -> None:
    src = inspect.getsource(Orchestrator._follow_up_listen)
    assert "_maybe_start_stt_stream" in src
    assert "_maybe_feed_stt_chunk" in src
    assert "_maybe_stop_stt_stream" in src
    assert "_maybe_discard_stt_stream" in src


def test_capture_utterance_streaming_start_position_unchanged() -> None:
    # Pins that the COLD path was not restructured: streaming starts
    # BEFORE its while-loop (window-open semantics, unlike the WARM
    # path's SPEECH_START start).
    src = inspect.getsource(Orchestrator._capture_utterance)
    assert src.find("_maybe_start_stt_stream") < src.find(
        "while not self._shutdown"
    )


# ---------------------------------------------------------------------------
# Behavioral state-machine tests
# ---------------------------------------------------------------------------


class FakeStreamingSTT:
    """Streaming-capable STT fake with call counters."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.clear_calls = 0
        self.full_transcribe_calls = 0
        self.stash: Optional[str] = None
        self.fed: List[np.ndarray] = []
        self._fed_lock = threading.Lock()

    def supports_streaming(self) -> bool:
        return True

    def start_stream(self) -> None:
        self.start_calls += 1

    def feed_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> None:
        with self._fed_lock:
            self.fed.append(audio)

    def stop_stream(self) -> str:
        self.stop_calls += 1
        self.stash = "final text"
        return self.stash

    def clear_stream_cache(self) -> None:
        self.clear_calls += 1
        self.stash = None

    def transcribe(self, audio: np.ndarray) -> str:
        self.full_transcribe_calls += 1
        if self.stash is not None:
            text, self.stash = self.stash, None
            return text
        return "sync"


def _chunk(value: float = 0.1, n: int = 256) -> np.ndarray:
    return np.full(n, value, dtype=np.float32)


def _stub_follow_up_orchestrator(
    monkeypatch,
    *,
    vad_events,
    wake_script=None,
    stt=None,
    n_chunks: int = 64,
):
    """Build a partial Orchestrator driving the REAL _follow_up_listen.

    ``vad_events`` is a list of SpeechEvent-or-None scripted per chunk
    (None means probability-only silence). ``wake_script`` is a list
    of bools per chunk (default: never fires).
    """
    o = object.__new__(Orchestrator)
    o._shutdown = threading.Event()

    # Speculative-lane slots so _reset_speculative_stt_state's chain
    # doesn't AttributeError.
    o._speculative_stt_lock = threading.Lock()
    o._speculative_stt_thread = None
    o._speculative_stt_result = None
    o._speculative_stt_active = False
    o._speculative_stt_invalidated = False
    o._speculative_classification_lock = threading.Lock()
    o._speculative_classification = None
    o._speculative_classification_invalidated = False
    o._speculative_llm_lock = threading.Lock()
    o._speculative_llm_thread = None
    o._speculative_llm_buffer = None
    o._speculative_llm_text = None
    o._speculative_llm_response = None
    o._speculative_llm_active = False
    o._speculative_llm_invalidated = False

    chunks = [_chunk() for _ in range(n_chunks)]
    chunk_iter = iter(chunks)

    def _get_chunk(timeout: float = 0.1):
        try:
            return next(chunk_iter)
        except StopIteration:
            return None

    o.audio = SimpleNamespace(drain=lambda: None, get_chunk=_get_chunk)

    wake_list = list(wake_script or [])
    wake_state = {"i": 0}

    def _wake_process(chunk) -> bool:
        i = wake_state["i"]
        wake_state["i"] += 1
        return wake_list[i] if i < len(wake_list) else False

    o.wake = SimpleNamespace(reset=lambda: None, process=_wake_process)

    vad_list = list(vad_events)
    vad_state = {"i": 0}

    def _vad_process(chunk):
        i = vad_state["i"]
        vad_state["i"] += 1
        ev = vad_list[i] if i < len(vad_list) else None
        # probability above threshold while "speaking", below when not;
        # keep it above so the speculative lane never kicks (we pin
        # that separately).
        return SimpleNamespace(event=ev, probability=0.9)

    o.vad = SimpleNamespace(
        reset=lambda: None,
        process=_vad_process,
        threshold=0.5,
        set_min_silence_duration_ms=lambda ms: None,
    )

    o.ring = SimpleNamespace(
        write=lambda chunk: None,
        snapshot=lambda n: np.full(n, 0.5, dtype=np.float32),
    )

    o.tts = None  # _kick_off_tts_preopen no-ops without an engine
    o.stt = stt if stt is not None else FakeStreamingSTT()

    monkeypatch.setattr(o, "_cancel_background_summarizer", lambda: None)
    monkeypatch.setattr(
        o, "_smart_turn_should_check", lambda **kw: False,
    )

    o._max_utterance_seconds = 30.0
    o._warm_pre_roll_seconds = 0.5
    o._smart_turn_incomplete_extension_ms = 1000
    o._smart_turn_medium_grace_ms = 500

    return o


def test_streaming_session_runs_during_follow_up_capture(monkeypatch):
    stt = FakeStreamingSTT()
    o = _stub_follow_up_orchestrator(
        monkeypatch,
        vad_events=[None, SpeechEvent.SPEECH_START, None,
                    SpeechEvent.SPEECH_END],
        stt=stt,
    )
    result = o._follow_up_listen(deadline=time.monotonic() + 5.0)
    assert isinstance(result, np.ndarray)
    assert stt.start_calls == 1
    assert stt.stop_calls == 1
    # THE latency assertion: no synchronous transcribe during the
    # listen itself (run()'s later transcribe() hits the stash).
    assert stt.full_transcribe_calls == 0
    # First fed buffer is the pre-roll; total fed == returned buffer.
    assert np.allclose(stt.fed[0], 0.5)
    fed_samples = sum(int(a.size) for a in stt.fed)
    assert fed_samples == int(result.size)


def test_stream_not_started_before_speech(monkeypatch):
    stt = FakeStreamingSTT()
    o = _stub_follow_up_orchestrator(
        monkeypatch, vad_events=[None] * 8, stt=stt, n_chunks=8,
    )
    result = o._follow_up_listen(deadline=time.monotonic() + 0.3)
    assert result == _FU_TIMEOUT
    # No idle-window CPU burn: the stream never started.
    assert stt.start_calls == 0
    assert stt.stop_calls == 0


def test_wake_word_mid_utterance_discards_stream(monkeypatch):
    stt = FakeStreamingSTT()
    o = _stub_follow_up_orchestrator(
        monkeypatch,
        vad_events=[SpeechEvent.SPEECH_START, None, None, None],
        wake_script=[False, False, True],  # wake on the 3rd chunk
        stt=stt,
    )
    result = o._follow_up_listen(deadline=time.monotonic() + 5.0)
    assert result == _FU_WAKE
    assert stt.stop_calls == 1
    assert stt.clear_calls == 1
    assert stt.stash is None  # no leak into the next capture


def test_deadline_mid_utterance_discards_stream(monkeypatch):
    stt = FakeStreamingSTT()
    o = _stub_follow_up_orchestrator(
        monkeypatch,
        vad_events=[SpeechEvent.SPEECH_START] + [None] * 60,
        stt=stt,
        n_chunks=64,
    )
    result = o._follow_up_listen(deadline=time.monotonic() + 0.3)
    assert result == _FU_TIMEOUT
    assert stt.stop_calls == 1
    assert stt.clear_calls == 1


def test_non_streaming_engine_keeps_speculative_lane(monkeypatch):
    # Whisper-shaped engine: no supports_streaming attr at all. The
    # streaming lane must stay inert and the speculative lane must
    # still fire after consecutive silence chunks post-speech.
    o = _stub_follow_up_orchestrator(
        monkeypatch,
        vad_events=[SpeechEvent.SPEECH_START, None, None, None,
                    SpeechEvent.SPEECH_END],
        stt=SimpleNamespace(transcribe=lambda audio: "sync"),
    )

    # Silence probabilities after speech so the speculative kick-off
    # threshold (2 consecutive) is crossed.
    vad_list = [SpeechEvent.SPEECH_START, None, None, None,
                SpeechEvent.SPEECH_END]
    state = {"i": 0}

    def _vad_process(chunk):
        i = state["i"]
        state["i"] += 1
        ev = vad_list[i] if i < len(vad_list) else None
        prob = 0.9 if ev == SpeechEvent.SPEECH_START else 0.1
        return SimpleNamespace(event=ev, probability=prob)

    o.vad = SimpleNamespace(
        reset=lambda: None, process=_vad_process, threshold=0.5,
        set_min_silence_duration_ms=lambda ms: None,
    )

    kicked = []
    monkeypatch.setattr(
        o, "_kick_off_speculative_stt", lambda audio: kicked.append(audio),
    )
    result = o._follow_up_listen(deadline=time.monotonic() + 5.0)
    assert isinstance(result, np.ndarray)
    assert len(kicked) == 1  # the speculative lane still fires


def test_speculative_kickoff_noop_on_streaming_engine(monkeypatch):
    # Pins the race guard the streaming-lane fix depends on: on a
    # streaming engine the speculative kick-off must do nothing.
    o = object.__new__(Orchestrator)
    o._speculative_stt_lock = threading.Lock()
    o._speculative_stt_thread = None
    o._speculative_stt_result = None
    o._speculative_stt_active = False
    o._speculative_stt_invalidated = False
    o.stt = SimpleNamespace(
        transcribe=lambda a: "x",
        supports_streaming=lambda: True,
    )
    o._kick_off_speculative_stt(np.zeros(1600, dtype=np.float32))
    assert o._speculative_stt_active is False
    assert o._speculative_stt_thread is None


def test_discard_helper_is_fail_open_without_engine_support():
    # An engine without clear_stream_cache must not break the discard.
    o = object.__new__(Orchestrator)
    o.stt = SimpleNamespace(transcribe=lambda a: "x")
    o._stt_stream_queue = None
    o._stt_stream_worker = None
    o._stt_stream_sentinel = None
    o._maybe_discard_stt_stream()  # must not raise
