"""Moonshine engine tests (2026-05-22 rewrite for moonshine-voice).

The engine now uses ``moonshine-voice`` (the official Moonshine AI
package) which provides v2 streaming model variants. Tests fake the
``moonshine_voice.transcriber.Transcriber`` so engine construction
doesn't download real assets. The end-to-end real-load test is gated
behind ``PYTEST_RUN_GPU_TESTS=1``.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fake moonshine_voice surface
# ---------------------------------------------------------------------------


def _make_fake_transcriber(text: str = "hello world"):
    """Build a fake Transcriber that emits a fixed transcript on demand."""
    fake_line = MagicMock()
    fake_line.text = text
    fake_line.start_time = 0.0
    fake_line.duration = 1.0
    fake_line.line_id = 1
    fake_line.is_complete = True
    fake_line.last_transcription_latency_ms = 12

    fake_transcript = MagicMock()
    fake_transcript.lines = [fake_line]

    transcriber = MagicMock()
    transcriber.start = MagicMock()
    transcriber.stop = MagicMock()
    transcriber.close = MagicMock()
    transcriber.add_audio = MagicMock()
    transcriber.update_transcription = MagicMock()
    transcriber.add_listener = MagicMock()
    transcriber.transcribe_without_streaming = MagicMock(
        return_value=fake_transcript,
    )

    return transcriber, fake_line


@pytest.fixture
def fake_moonshine_voice(monkeypatch):
    """Inject a fake ``moonshine_voice`` package + submodule so the
    engine constructs without downloading real assets."""
    transcriber, fake_line = _make_fake_transcriber()

    transcriber_cls = MagicMock(return_value=transcriber)

    # Build a fake module tree
    fake_pkg = types.ModuleType("moonshine_voice")
    fake_transcriber_mod = types.ModuleType("moonshine_voice.transcriber")

    class _FakeArch:
        TINY = 0
        BASE = 1
        TINY_STREAMING = 2
        BASE_STREAMING = 3
        SMALL_STREAMING = 4
        MEDIUM_STREAMING = 5

    fake_pkg.ModelArch = _FakeArch
    fake_pkg.get_model_path = MagicMock(return_value="/fake/path")

    # ``get_model_for_language`` honours the requested arch when one
    # is passed; otherwise defaults to MEDIUM_STREAMING (the real
    # English default).
    def _fake_get_model_for_language(language="en", arch=None, **kwargs):
        chosen = arch if arch is not None else _FakeArch.MEDIUM_STREAMING
        return (f"/fake/path/{chosen}", chosen)

    fake_pkg.get_model_for_language = MagicMock(
        side_effect=_fake_get_model_for_language,
    )
    fake_pkg.string_to_model_arch = MagicMock(return_value=_FakeArch.MEDIUM_STREAMING)
    # Real moonshine returns lowercase strings ("base", "medium-streaming",
    # etc.); mirror that so the engine's streaming-check picks them up
    # correctly.
    fake_pkg.model_arch_to_string = MagicMock(
        side_effect=lambda arch: {
            _FakeArch.TINY: "tiny",
            _FakeArch.BASE: "base",
            _FakeArch.TINY_STREAMING: "tiny-streaming",
            _FakeArch.BASE_STREAMING: "base-streaming",
            _FakeArch.SMALL_STREAMING: "small-streaming",
            _FakeArch.MEDIUM_STREAMING: "medium-streaming",
        }.get(arch, str(arch)),
    )

    fake_transcriber_mod.Transcriber = transcriber_cls

    # Provide a TranscriptEventListener that the engine subclasses
    # imperatively (it accepts any class with on_* methods).
    class _StubListener:
        def on_line_started(self, e): pass
        def on_line_updated(self, e): pass
        def on_line_completed(self, e): pass
        def on_line_text_changed(self, e): pass
        def on_error(self, e): pass

    fake_transcriber_mod.TranscriptEventListener = _StubListener

    monkeypatch.setitem(sys.modules, "moonshine_voice", fake_pkg)
    monkeypatch.setitem(
        sys.modules, "moonshine_voice.transcriber", fake_transcriber_mod,
    )

    # Short-circuit the availability probe (which uses find_spec and
    # doesn't see the fake module in sys.modules).
    monkeypatch.setattr(
        "ultron.transcription.moonshine_engine.is_moonshine_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "ultron.transcription.is_moonshine_available", lambda: True,
    )

    return {
        "transcriber": transcriber,
        "transcriber_cls": transcriber_cls,
        "fake_line": fake_line,
        "ModelArch": _FakeArch,
        "pkg": fake_pkg,
    }


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def test_is_moonshine_available_returns_bool():
    from ultron.transcription.moonshine_engine import is_moonshine_available
    assert isinstance(is_moonshine_available(), bool)


def test_is_moonshine_available_handles_missing_module(monkeypatch):
    import importlib.util as _spec
    monkeypatch.setattr(_spec, "find_spec", lambda name: None)
    from ultron.transcription.moonshine_engine import is_moonshine_available
    assert is_moonshine_available() is False


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------


def test_engine_constructs_with_defaults(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    fake_moonshine_voice["transcriber_cls"].assert_called_once()
    kwargs = fake_moonshine_voice["transcriber_cls"].call_args.kwargs
    assert "model_path" in kwargs
    assert "model_arch" in kwargs
    assert "update_interval" in kwargs


def test_engine_resolves_streaming_alias(fake_moonshine_voice):
    """``"medium-streaming-en"`` should resolve to MEDIUM_STREAMING."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine(model_name="medium-streaming-en")
    kwargs = fake_moonshine_voice["transcriber_cls"].call_args.kwargs
    assert kwargs["model_arch"] == fake_moonshine_voice["ModelArch"].MEDIUM_STREAMING


def test_engine_resolves_non_streaming_alias(fake_moonshine_voice):
    """``"moonshine/base"`` should resolve to BASE (non-streaming)."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine(model_name="moonshine/base")
    kwargs = fake_moonshine_voice["transcriber_cls"].call_args.kwargs
    assert kwargs["model_arch"] == fake_moonshine_voice["ModelArch"].BASE


def test_engine_raises_when_package_missing(monkeypatch):
    monkeypatch.setattr(
        "ultron.transcription.moonshine_engine.is_moonshine_available",
        lambda: False,
    )
    from ultron.transcription.moonshine_engine import MoonshineEngine
    with pytest.raises(ImportError, match="moonshine-voice"):
        MoonshineEngine()


def test_engine_normalises_cuda_request_to_cpu(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine(device="cuda")
    assert engine.device == "cpu"


# ---------------------------------------------------------------------------
# supports_streaming
# ---------------------------------------------------------------------------


def test_supports_streaming_true_for_streaming_arches(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine(model_name="medium-streaming-en")
    assert engine.supports_streaming() is True


def test_supports_streaming_false_for_non_streaming_arches(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine(model_name="moonshine/base")
    assert engine.supports_streaming() is False


# ---------------------------------------------------------------------------
# Streaming protocol
# ---------------------------------------------------------------------------


def test_start_stream_is_idempotent(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    engine.start_stream()
    # Only one underlying start call -- second start is a no-op.
    assert fake_moonshine_voice["transcriber"].start.call_count == 1


def test_feed_audio_passes_chunk_to_transcriber(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    chunk = np.zeros(256, dtype=np.float32)
    engine.feed_audio(chunk)
    transcriber = fake_moonshine_voice["transcriber"]
    transcriber.add_audio.assert_called_once()


def test_feed_audio_no_op_when_stream_not_started(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    chunk = np.zeros(256, dtype=np.float32)
    engine.feed_audio(chunk)
    fake_moonshine_voice["transcriber"].add_audio.assert_not_called()


def test_feed_audio_coerces_dtype(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    chunk = np.zeros(256, dtype=np.float64)
    engine.feed_audio(chunk)
    passed = fake_moonshine_voice["transcriber"].add_audio.call_args.args[0]
    assert passed.dtype == np.float32


def test_stop_stream_finalises_and_returns_text(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    # Simulate the listener firing with a completed line
    line = fake_moonshine_voice["fake_line"]
    line.text = "the cat sat"
    engine._collector._update_line(line)
    text = engine.stop_stream()
    assert text == "the cat sat"
    fake_moonshine_voice["transcriber"].stop.assert_called_once()


def test_stop_stream_idempotent(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    engine.stop_stream()
    engine.stop_stream()
    # Second stop returns the cached text without re-calling stop().
    assert fake_moonshine_voice["transcriber"].stop.call_count == 1


def test_get_partial_text_returns_current_lines(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    fake = fake_moonshine_voice["fake_line"]
    fake.text = "hello"
    fake.is_complete = False
    engine._collector._update_line(fake)
    assert engine.get_partial_text() == "hello"


def test_clear_stream_cache_drops_stash(fake_moonshine_voice):
    """2026-06-12 follow-up abort path: a discarded capture's partial
    transcript must not leak into the next transcribe call."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    line = fake_moonshine_voice["fake_line"]
    line.text = "discarded partial"
    engine._collector._update_line(line)
    engine.stop_stream()
    assert engine._last_streaming_text == "discarded partial"
    engine.clear_stream_cache()
    assert engine._last_streaming_text is None
    # A subsequent transcribe must NOT return the cleared text.
    result = engine.transcribe(np.zeros(16000 * 2, dtype=np.float32))
    assert result != "discarded partial"


def test_clear_stream_cache_idempotent_when_empty(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.clear_stream_cache()
    engine.clear_stream_cache()  # second call must not raise
    assert engine._last_streaming_text is None


# ---------------------------------------------------------------------------
# transcribe (one-shot + interaction with streaming state)
# ---------------------------------------------------------------------------


def test_transcribe_empty_audio_returns_empty(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    assert engine.transcribe(np.zeros(0, dtype=np.float32)) == ""


def test_transcribe_sub_100ms_returns_empty(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    short = np.zeros(800, dtype=np.float32)  # 50ms
    assert engine.transcribe(short) == ""


def test_transcribe_consumes_cached_streaming_text(fake_moonshine_voice):
    """When stop_stream just stashed a final transcript, the next
    transcribe(buffer) call should return that cached text instantly
    without re-running the model."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine._last_streaming_text = "stashed result"
    audio = np.zeros(16000, dtype=np.float32)
    assert engine.transcribe(audio) == "stashed result"
    # And the slot is consumed on first read.
    assert engine._last_streaming_text is None


def test_transcribe_during_active_stream_returns_partial(fake_moonshine_voice):
    """When a streaming session is in flight, transcribe should peek
    the current partial WITHOUT stopping the stream."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.start_stream()
    fake = fake_moonshine_voice["fake_line"]
    fake.text = "partial transcript"
    fake.is_complete = False
    engine._collector._update_line(fake)
    result = engine.transcribe(np.zeros(16000, dtype=np.float32))
    assert result == "partial transcript"
    # Stream still active afterwards.
    assert engine._stream_active is True
    fake_moonshine_voice["transcriber"].stop.assert_not_called()


def test_transcribe_one_shot_for_non_streaming_arch(fake_moonshine_voice):
    """On a non-streaming arch, transcribe uses transcribe_without_streaming."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine(model_name="moonshine/base")
    text = engine.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "hello world"
    fake_moonshine_voice["transcriber"].transcribe_without_streaming.assert_called_once()


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------


def test_warmup_runs_a_silence_transcribe(fake_moonshine_voice):
    from ultron.transcription.moonshine_engine import MoonshineEngine
    engine = MoonshineEngine()
    engine.warmup()
    # Warmup invokes the transcribe path; the fake transcriber.start
    # is touched at least once.
    assert fake_moonshine_voice["transcriber"].start.called


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


def test_factory_dispatches_moonshine(fake_moonshine_voice):
    from ultron.transcription import make_stt_engine, MoonshineEngine
    fake_cfg = MagicMock()
    fake_cfg.engine = "moonshine"
    fake_cfg.moonshine_model = "medium-streaming-en"
    fake_cfg.moonshine_device = "cpu"
    fake_cfg.moonshine_precision = "float"
    engine = make_stt_engine(fake_cfg)
    assert isinstance(engine, MoonshineEngine)


def test_factory_raises_when_moonshine_missing(monkeypatch):
    monkeypatch.setattr(
        "ultron.transcription.is_moonshine_available", lambda: False,
    )
    from ultron.transcription import make_stt_engine
    fake_cfg = MagicMock()
    fake_cfg.engine = "moonshine"
    with pytest.raises(ImportError, match="moonshine-voice"):
        make_stt_engine(fake_cfg)


# ---------------------------------------------------------------------------
# Real-load smoke test (gated)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("PYTEST_RUN_GPU_TESTS") != "1",
    reason="set PYTEST_RUN_GPU_TESTS=1 to run real-model load tests",
)
def test_moonshine_real_load_and_transcribe_silence():
    """End-to-end: load the actual medium-streaming-en bundle and
    transcribe 1 s of silence. Silence should produce a short / empty
    string."""
    from ultron.transcription.moonshine_engine import MoonshineEngine
    with MoonshineEngine(model_name="medium-streaming-en") as stt:
        silence = np.zeros(16000, dtype=np.float32)
        text = stt.transcribe(silence)
        assert isinstance(text, str)
        assert len(text) <= 32
