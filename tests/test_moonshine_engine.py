"""Moonshine ONNX engine tests (2026-05-22).

Most tests run without the actual model by patching the
``moonshine_onnx`` module surface. The end-to-end real-load test is
gated behind ``PYTEST_RUN_GPU_TESTS=1`` to avoid downloading the
58 MB ONNX bundle on CI.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_moonshine_module(monkeypatch):
    """Inject a fake ``moonshine_onnx`` module so the engine constructs
    without downloading real ONNX assets. Also stubs the
    ``is_moonshine_available`` probe to return True so the engine's
    early ImportError check passes."""
    fake_model = MagicMock()
    # ``model.generate`` returns a 2-D batch of token IDs; the engine
    # passes this to ``tokenizer.decode_batch``.
    fake_model.generate.return_value = [[1, 2, 3, 4]]

    fake_tokenizer = MagicMock()
    fake_tokenizer.decode_batch.return_value = ["hello world"]

    fake_model_cls = MagicMock(return_value=fake_model)

    fake_pkg = types.ModuleType("moonshine_onnx")
    fake_pkg.MoonshineOnnxModel = fake_model_cls
    fake_transcribe_module = types.ModuleType("moonshine_onnx.transcribe")
    fake_transcribe_module.load_tokenizer = MagicMock(return_value=fake_tokenizer)
    fake_pkg.transcribe = fake_transcribe_module

    monkeypatch.setitem(sys.modules, "moonshine_onnx", fake_pkg)
    monkeypatch.setitem(sys.modules, "moonshine_onnx.transcribe",
                        fake_transcribe_module)

    # The engine + factory call ``is_moonshine_available`` (which uses
    # ``importlib.util.find_spec``) BEFORE the import of MoonshineOnnxModel,
    # so we have to short-circuit both call sites.
    monkeypatch.setattr(
        "ultron.transcription.moonshine_engine.is_moonshine_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "ultron.transcription.is_moonshine_available", lambda: True,
    )

    return {
        "module": fake_pkg,
        "model_cls": fake_model_cls,
        "model": fake_model,
        "tokenizer": fake_tokenizer,
    }


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------


def test_is_moonshine_available_returns_bool():
    from ultron.transcription.moonshine_engine import is_moonshine_available
    result = is_moonshine_available()
    assert isinstance(result, bool)


def test_is_moonshine_available_handles_missing_module(monkeypatch):
    """``find_spec`` returning None should map to False."""
    import importlib.util as _spec
    monkeypatch.setattr(_spec, "find_spec", lambda name: None)
    from ultron.transcription.moonshine_engine import is_moonshine_available
    assert is_moonshine_available() is False


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------


def test_engine_constructs_with_defaults(fake_moonshine_module):
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    # Model_name should fall back to the config default; precision
    # should also resolve from config (default "float").
    fake_moonshine_module["model_cls"].assert_called_once()
    kwargs = fake_moonshine_module["model_cls"].call_args.kwargs
    assert kwargs["model_name"].startswith("moonshine/")
    assert kwargs["model_precision"] in {"float", "quantized"}


def test_engine_constructs_with_explicit_model(fake_moonshine_module):
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine(
        model_name="moonshine/tiny",
        model_precision="quantized",
    )
    kwargs = fake_moonshine_module["model_cls"].call_args.kwargs
    assert kwargs["model_name"] == "moonshine/tiny"
    assert kwargs["model_precision"] == "quantized"


def test_engine_normalises_cuda_request_to_cpu(fake_moonshine_module, caplog):
    """Moonshine ONNX is CPU-only; the engine should accept device='cuda'
    for API parity but log a notice and run on CPU."""
    from ultron.transcription.moonshine_engine import MoonshineEngine

    with caplog.at_level("INFO"):
        engine = MoonshineEngine(device="cuda")
    assert engine.device == "cpu"


def test_engine_raises_importerror_when_module_missing(monkeypatch):
    monkeypatch.setattr(
        "ultron.transcription.moonshine_engine.is_moonshine_available",
        lambda: False,
    )
    from ultron.transcription.moonshine_engine import MoonshineEngine

    with pytest.raises(ImportError, match="useful-moonshine-onnx"):
        MoonshineEngine()


# ---------------------------------------------------------------------------
# transcribe behaviour
# ---------------------------------------------------------------------------


def test_transcribe_empty_audio_returns_empty_string(fake_moonshine_module):
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    assert engine.transcribe(np.zeros(0, dtype=np.float32)) == ""
    # Empty input should not invoke the model.
    fake_moonshine_module["model"].generate.assert_not_called()


def test_transcribe_sub_100ms_clip_returns_empty_string(fake_moonshine_module):
    """Moonshine's per-call floor is 100 ms; shorter clips must be skipped."""
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    # 800 samples @ 16 kHz = 50 ms, below the 100 ms minimum.
    short_clip = np.zeros(800, dtype=np.float32)
    assert engine.transcribe(short_clip) == ""
    fake_moonshine_module["model"].generate.assert_not_called()


def test_transcribe_over_64s_returns_empty_with_warning(
    fake_moonshine_module, caplog,
):
    """Moonshine's per-call ceiling is 64 s; longer clips must be skipped."""
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    # 64.5 s @ 16 kHz
    long_clip = np.zeros(int(64.5 * 16000), dtype=np.float32)
    with caplog.at_level("WARNING"):
        result = engine.transcribe(long_clip)
    assert result == ""
    fake_moonshine_module["model"].generate.assert_not_called()
    assert any("64s" in r.message or "ceiling" in r.message
               for r in caplog.records)


def test_transcribe_returns_decoded_text(fake_moonshine_module):
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    audio = np.zeros(16000, dtype=np.float32)  # 1 s of silence buffer
    result = engine.transcribe(audio)
    assert result == "hello world"
    fake_moonshine_module["model"].generate.assert_called_once()
    fake_moonshine_module["tokenizer"].decode_batch.assert_called_once()


def test_transcribe_adds_batch_dimension(fake_moonshine_module):
    """The engine receives 1-D (samples,) but Moonshine wants (1, samples)."""
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    audio = np.zeros(16000, dtype=np.float32)
    engine.transcribe(audio)
    passed = fake_moonshine_module["model"].generate.call_args.args[0]
    assert passed.ndim == 2
    assert passed.shape == (1, 16000)


def test_transcribe_coerces_audio_dtype_to_float32(fake_moonshine_module):
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    # Pass float64 — engine should silently convert.
    audio = np.zeros(16000, dtype=np.float64)
    engine.transcribe(audio)
    passed = fake_moonshine_module["model"].generate.call_args.args[0]
    assert passed.dtype == np.float32


def test_transcribe_error_returns_empty_and_logs(
    fake_moonshine_module, caplog,
):
    fake_moonshine_module["model"].generate.side_effect = RuntimeError(
        "synthetic onnx failure",
    )
    from ultron.transcription.moonshine_engine import MoonshineEngine

    engine = MoonshineEngine()
    audio = np.zeros(16000, dtype=np.float32)
    with caplog.at_level("ERROR"):
        result = engine.transcribe(audio)
    assert result == ""
    assert any("synthetic onnx failure" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


def test_factory_dispatches_moonshine(fake_moonshine_module, monkeypatch):
    """When stt.engine == 'moonshine', the factory should construct
    MoonshineEngine rather than Whisper or Parakeet."""
    from ultron.transcription import make_stt_engine, MoonshineEngine

    fake_cfg = MagicMock()
    fake_cfg.engine = "moonshine"
    fake_cfg.moonshine_model = "moonshine/base"
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
    with pytest.raises(ImportError, match="useful-moonshine-onnx"):
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
    """End-to-end: load the actual base ONNX bundle and transcribe
    1 s of silence. Silence should produce a short / empty string."""
    from ultron.transcription.moonshine_engine import MoonshineEngine

    with MoonshineEngine(model_name="moonshine/base") as stt:
        silence = np.zeros(16000, dtype=np.float32)
        text = stt.transcribe(silence)
        assert isinstance(text, str)
        # Silence shouldn't generate paragraph-length hallucinations.
        assert len(text) <= 32
