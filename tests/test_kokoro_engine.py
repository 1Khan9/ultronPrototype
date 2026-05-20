"""Tests for the Kokoro TTS engine wrapper (Track 5).

The wrapper ships unconditionally; the actual Kokoro weights load
lazily on first inference. Tests stub the model load + synth call
so the suite runs without the ``kokoro`` package or weights being
present.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import List

import numpy as np
import pytest

from ultron.tts.kokoro_engine import (
    ClipItem,
    KokoroEngineLoadError,
    KokoroSpeech,
    KokoroSynthError,
)


# ---------------------------------------------------------------------------
# Construction + lazy-load semantics
# ---------------------------------------------------------------------------


def test_construct_without_load():
    """Construction is cheap -- the engine should be instantiable even
    when the kokoro package + weights are absent. Load is lazy on
    first inference."""
    engine = KokoroSpeech(
        model_path=Path("/nonexistent/kokoro"),
        voice="af_alloy",
        device="cpu",
    )
    assert engine.sample_rate == 24000
    assert engine.voice == "af_alloy"
    assert engine.is_available() is True  # no load attempt yet


def test_first_synthesize_raises_load_error_when_dir_missing(tmp_path):
    engine = KokoroSpeech(model_path=tmp_path / "missing")
    with pytest.raises(KokoroEngineLoadError):
        engine._synthesize("Hello.")


def test_load_error_is_cached(tmp_path):
    """A failed load shouldn't be retried on every call."""
    engine = KokoroSpeech(model_path=tmp_path / "missing")
    with pytest.raises(KokoroEngineLoadError):
        engine._synthesize("Hello.")
    assert engine.is_available() is False
    # Second call still fails fast.
    with pytest.raises(KokoroEngineLoadError):
        engine._synthesize("Hello.")


def test_reset_load_error_clears_state(tmp_path):
    engine = KokoroSpeech(model_path=tmp_path / "missing")
    with pytest.raises(KokoroEngineLoadError):
        engine._synthesize("Hello.")
    assert engine.is_available() is False
    engine.reset_load_error()
    assert engine.is_available() is True


def test_warmup_swallows_load_error(tmp_path):
    """Warmup is fail-open. A missing model directory shouldn't
    raise -- the load error is logged + the warmup is a no-op."""
    engine = KokoroSpeech(model_path=tmp_path / "missing")
    # No exception -- warmup is intentionally tolerant.
    engine.warmup()


# ---------------------------------------------------------------------------
# Stubbed-inference round-trip
# ---------------------------------------------------------------------------


class _FakeKPipeline:
    """Stub that mimics the kokoro KPipeline call shape.

    The real pipeline yields (graphemes, phonemes, audio) tuples.
    Our stub yields one tuple per call -- enough to verify the
    engine collects + concatenates the audio + converts to int16.
    """

    def __init__(self, audio_samples: int = 1200):
        self.audio_samples = audio_samples
        self.last_text = None
        self.last_voice = None

    def __call__(self, text, *, voice, speed):
        self.last_text = text
        self.last_voice = voice
        # Generate a low-amplitude sine wave so the output is non-zero
        # but predictable.
        n = self.audio_samples
        wave = (0.1 * np.sin(np.linspace(0, np.pi, n))).astype(np.float32)
        yield ("graphemes", "phonemes", wave)


def test_synthesize_with_stubbed_pipeline_returns_int16():
    engine = KokoroSpeech(model_path=Path("/stub"), voice="af_alloy")
    # Bypass the load path with the stub.
    engine._model = _FakeKPipeline(audio_samples=2400)
    engine._loaded = True
    engine._load_error = None

    pcm, sr = engine._synthesize("Hello world.")
    assert pcm.dtype == np.int16
    assert pcm.size == 2400
    assert sr == 24000
    # Stub recorded the call.
    assert engine._model.last_text == "Hello world."
    assert engine._model.last_voice == "af_alloy"


def test_synthesize_empty_pipeline_returns_zero_clip():
    """Pipeline that yields no tuples -> empty PCM, sample rate
    preserved."""
    engine = KokoroSpeech(model_path=Path("/stub"))
    engine._model = lambda text, voice, speed: iter([])
    engine._loaded = True

    pcm, sr = engine._synthesize("")
    assert pcm.size == 0
    assert sr == 24000


def test_synthesize_failure_raises_synth_error():
    """Underlying inference exception becomes a KokoroSynthError."""
    engine = KokoroSpeech(model_path=Path("/stub"))

    def broken_pipeline(text, *, voice, speed):
        raise RuntimeError("oom")

    engine._model = broken_pipeline
    engine._loaded = True
    with pytest.raises(KokoroSynthError):
        engine._synthesize("test")


def test_synthesize_concatenates_multiple_pipeline_chunks():
    """Multi-sentence pipelines yield multiple chunks; the engine
    concatenates them in order."""

    class _MultiChunk:
        def __call__(self, text, *, voice, speed):
            yield ("g", "p", np.full(100, 0.05, dtype=np.float32))
            yield ("g", "p", np.full(200, 0.1, dtype=np.float32))

    engine = KokoroSpeech(model_path=Path("/stub"))
    engine._model = _MultiChunk()
    engine._loaded = True

    pcm, _sr = engine._synthesize("Two sentences. Combined.")
    assert pcm.size == 300


# ---------------------------------------------------------------------------
# Runtime filter (pre-fine-tune path)
# ---------------------------------------------------------------------------


def test_runtime_filter_does_not_crash_on_unimportable():
    """If the pedalboard filter import fails (e.g., pedalboard not
    installed in the venv), the engine falls back to unfiltered
    output rather than raising."""
    engine = KokoroSpeech(
        model_path=Path("/stub"),
        apply_runtime_filter=True,
    )
    engine._model = _FakeKPipeline()
    engine._loaded = True
    # Should not raise even if pedalboard / ultron_filter are
    # unavailable -- the engine catches the exception.
    pcm, _sr = engine._synthesize("test")
    assert pcm.dtype == np.int16


# ---------------------------------------------------------------------------
# Public API surface mirrors XttsV3Speech
# ---------------------------------------------------------------------------


def test_public_surface_matches_xtts_v3():
    """The orchestrator swaps engines via tts.engine; the playback
    path doesn't know which engine it has. Verify the contract."""
    engine = KokoroSpeech(model_path=Path("/stub"))
    assert hasattr(engine, "speak")
    assert hasattr(engine, "speak_stream")
    assert hasattr(engine, "warmup")
    assert hasattr(engine, "stop")
    assert hasattr(engine, "prepare_output_stream")
    assert hasattr(engine, "sample_rate")


def test_stop_clears_preopened_stream():
    """stop() releases the device handle so the playback path opens
    fresh next time. Mirrors XTTS behaviour."""
    engine = KokoroSpeech(model_path=Path("/stub"))

    class _FakeStream:
        def __init__(self):
            self.stopped = False
            self.closed = False

        def stop(self):
            self.stopped = True

        def close(self):
            self.closed = True

    fake = _FakeStream()
    engine._preopened_stream = fake
    engine.stop()
    assert fake.stopped is True
    assert fake.closed is True
    assert engine._preopened_stream is None


def test_clipitem_namedtuple_shape():
    """ClipItem mirrors the XTTS / legacy queue contract."""
    item = ClipItem(audio=np.zeros(10, dtype=np.int16), sample_rate=24000)
    assert item.is_known_last is False
    item2 = ClipItem(
        audio=np.zeros(10, dtype=np.int16),
        sample_rate=24000,
        is_known_last=True,
    )
    assert item2.is_known_last is True


# ---------------------------------------------------------------------------
# Config / engine selection
# ---------------------------------------------------------------------------


def test_kokoro_engine_in_tts_schema():
    """tts.engine accepts 'kokoro' alongside legacy + xtts_v3."""
    from ultron.config import TTSConfig
    cfg = TTSConfig(engine="kokoro")
    assert cfg.engine == "kokoro"


def test_kokoro_config_has_sensible_defaults():
    from ultron.config import KokoroConfig
    cfg = KokoroConfig()
    assert cfg.model_path == "models/kokoro"
    assert cfg.voice == "af_alloy"
    assert cfg.device == "cpu"
    assert cfg.speed == 1.0
    assert cfg.apply_runtime_filter is False
