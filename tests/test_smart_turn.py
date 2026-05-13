"""Tests for the Smart Turn V3 wrapper module.

Covers:
- SmartTurnConfig schema (ranges, defaults, round-trip)
- truncate_or_pad_for_smart_turn pure function (truncation, dtype, shape)
- SmartTurnDetector construction (path validation, threshold range,
  lazy-loading, fail-open on bad input)
- SmartTurnDetector.is_complete (verdict shape, undecided on error)
- build_detector_from_config (fail-open contract: disabled / missing
  file / construction error all return None)

The "real model" tests (load the actual ONNX from disk + run inference)
are gated on the model file's presence. They're CPU-only and don't
load any other voice-stack component -- safe to run in the default
test sweep when the model is present. When the model is absent (CI),
they skip cleanly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Constants reused across tests
# ---------------------------------------------------------------------------


def _find_real_model() -> Path:
    """Locate the production Smart Turn V3 ONNX model on disk.

    Tries ``PROJECT_ROOT / models / smart_turn / smart-turn-v3.2-cpu.onnx``
    first (matches the main-checkout case). When running from a
    worktree (``.claude/worktrees/<name>/``), the worktree's
    PROJECT_ROOT has no ``models/`` directory -- detect that layout
    and resolve against the parent main checkout instead. Returns
    the most-likely path even when nothing is found, so the test's
    skip message gives an informative location.
    """
    from ultron.config import PROJECT_ROOT
    candidate = PROJECT_ROOT / "models" / "smart_turn" / "smart-turn-v3.2-cpu.onnx"
    if candidate.is_file():
        return candidate
    # Worktree layout: <main>/.claude/worktrees/<name>/. The main
    # checkout is three parents up from PROJECT_ROOT.
    if (
        PROJECT_ROOT.parent.name == "worktrees"
        and PROJECT_ROOT.parent.parent.name == ".claude"
    ):
        main_checkout = PROJECT_ROOT.parent.parent.parent
        candidate = (
            main_checkout / "models" / "smart_turn" / "smart-turn-v3.2-cpu.onnx"
        )
        if candidate.is_file():
            return candidate
    # Not found anywhere. Return the PROJECT_ROOT-relative path so
    # the skip message points at the conventional location.
    return PROJECT_ROOT / "models" / "smart_turn" / "smart-turn-v3.2-cpu.onnx"


_REAL_MODEL_PATH = _find_real_model()


# ---------------------------------------------------------------------------
# SmartTurnConfig schema
# ---------------------------------------------------------------------------


def test_smart_turn_config_defaults_match_production_layout():
    """Defaults point at the v3.2-cpu ONNX bundled by
    scripts/download_models.py. If the download path moves, this test
    fails first so the schema and download stay in sync."""
    from ultron.config import SmartTurnConfig
    cfg = SmartTurnConfig()
    assert cfg.enabled is True
    assert cfg.model_path.endswith("smart-turn-v3.2-cpu.onnx")
    assert cfg.model_path.startswith("models/smart_turn/")
    assert cfg.completion_threshold == 0.5
    assert cfg.fast_path_silence_duration_ms == 500
    assert cfg.incomplete_extension_ms == 700
    assert cfg.window_seconds == 8.0
    assert cfg.num_threads == 1


def test_smart_turn_config_completion_threshold_range():
    """Threshold must be in (0.05, 0.95). Below ~0.05 the model
    always says complete (cuts off mid-thought); above ~0.95 it
    almost never says complete (always falls back to slow path)."""
    from pydantic import ValidationError
    from ultron.config import SmartTurnConfig
    SmartTurnConfig(completion_threshold=0.05)
    SmartTurnConfig(completion_threshold=0.95)
    with pytest.raises(ValidationError):
        SmartTurnConfig(completion_threshold=0.04)
    with pytest.raises(ValidationError):
        SmartTurnConfig(completion_threshold=0.96)


def test_smart_turn_config_fast_path_silence_range():
    from pydantic import ValidationError
    from ultron.config import SmartTurnConfig
    SmartTurnConfig(fast_path_silence_duration_ms=100)
    SmartTurnConfig(fast_path_silence_duration_ms=2000)
    with pytest.raises(ValidationError):
        SmartTurnConfig(fast_path_silence_duration_ms=99)
    with pytest.raises(ValidationError):
        SmartTurnConfig(fast_path_silence_duration_ms=2001)


def test_smart_turn_config_incomplete_extension_range():
    from pydantic import ValidationError
    from ultron.config import SmartTurnConfig
    SmartTurnConfig(incomplete_extension_ms=0)  # legal: no extension
    SmartTurnConfig(incomplete_extension_ms=3000)
    with pytest.raises(ValidationError):
        SmartTurnConfig(incomplete_extension_ms=-1)
    with pytest.raises(ValidationError):
        SmartTurnConfig(incomplete_extension_ms=3001)


def test_smart_turn_config_window_seconds_range():
    """Below 1 s the model has nothing to look at; above 30 s we'd
    be feeding clipped audio (smart-turn only sees the last 8 s)."""
    from pydantic import ValidationError
    from ultron.config import SmartTurnConfig
    SmartTurnConfig(window_seconds=1.0)
    SmartTurnConfig(window_seconds=30.0)
    with pytest.raises(ValidationError):
        SmartTurnConfig(window_seconds=0.99)
    with pytest.raises(ValidationError):
        SmartTurnConfig(window_seconds=30.01)


def test_smart_turn_config_num_threads_range():
    from pydantic import ValidationError
    from ultron.config import SmartTurnConfig
    SmartTurnConfig(num_threads=1)
    SmartTurnConfig(num_threads=16)
    with pytest.raises(ValidationError):
        SmartTurnConfig(num_threads=0)
    with pytest.raises(ValidationError):
        SmartTurnConfig(num_threads=17)


def test_smart_turn_config_round_trips_through_dict():
    from ultron.config import SmartTurnConfig
    cfg = SmartTurnConfig(
        enabled=False,
        completion_threshold=0.7,
        fast_path_silence_duration_ms=400,
        incomplete_extension_ms=900,
    )
    cfg2 = SmartTurnConfig.model_validate(cfg.model_dump())
    assert cfg2.enabled is False
    assert cfg2.completion_threshold == 0.7
    assert cfg2.fast_path_silence_duration_ms == 400
    assert cfg2.incomplete_extension_ms == 900


def test_vad_config_includes_smart_turn_subsection():
    from ultron.config import VADConfig, SmartTurnConfig
    cfg = VADConfig()
    assert isinstance(cfg.smart_turn, SmartTurnConfig)
    # Nested round-trip via dict (the YAML path).
    raw = cfg.model_dump()
    assert "smart_turn" in raw
    cfg2 = VADConfig.model_validate(raw)
    assert cfg2.smart_turn.enabled is True


# ---------------------------------------------------------------------------
# truncate_or_pad_for_smart_turn -- pure function
# ---------------------------------------------------------------------------


def test_truncate_or_pad_keeps_audio_under_window():
    """Audio shorter than the window passes through unchanged --
    padding is the feature extractor's job, not this helper's."""
    from ultron.audio.smart_turn import truncate_or_pad_for_smart_turn
    audio = np.random.randn(3 * 16000).astype(np.float32)
    out = truncate_or_pad_for_smart_turn(audio, 16000)
    assert out.shape[0] == audio.shape[0]
    assert np.array_equal(out, audio)


def test_truncate_or_pad_truncates_to_last_n_seconds():
    """Audio longer than the window is cut HEAD-first: the most
    recent ``window_seconds`` is kept. Matches Pipecat's reference
    behaviour (the model is trained on audio anchored to the end)."""
    from ultron.audio.smart_turn import truncate_or_pad_for_smart_turn
    audio = np.arange(12 * 16000, dtype=np.float32) / 1000.0
    out = truncate_or_pad_for_smart_turn(audio, 16000, window_seconds=8.0)
    assert out.shape[0] == 8 * 16000
    # Last samples should match the input's last 8 seconds.
    assert np.array_equal(out, audio[-8 * 16000:])


def test_truncate_or_pad_converts_to_float32():
    from ultron.audio.smart_turn import truncate_or_pad_for_smart_turn
    audio = (np.random.randn(16000) * 1000).astype(np.int16)
    out = truncate_or_pad_for_smart_turn(audio, 16000)
    assert out.dtype == np.float32


def test_truncate_or_pad_flattens_multidim_input():
    from ultron.audio.smart_turn import truncate_or_pad_for_smart_turn
    audio = np.random.randn(16000, 1).astype(np.float32)
    out = truncate_or_pad_for_smart_turn(audio, 16000)
    assert out.ndim == 1


def test_truncate_or_pad_rejects_non_16khz():
    from ultron.audio.smart_turn import truncate_or_pad_for_smart_turn
    audio = np.zeros(48000, dtype=np.float32)
    with pytest.raises(ValueError):
        truncate_or_pad_for_smart_turn(audio, 48000)


def test_truncate_or_pad_respects_custom_window_seconds():
    from ultron.audio.smart_turn import truncate_or_pad_for_smart_turn
    audio = np.random.randn(5 * 16000).astype(np.float32)
    out = truncate_or_pad_for_smart_turn(audio, 16000, window_seconds=2.0)
    assert out.shape[0] == 2 * 16000
    assert np.array_equal(out, audio[-2 * 16000:])


# ---------------------------------------------------------------------------
# SmartTurnDetector construction
# ---------------------------------------------------------------------------


def test_detector_construction_rejects_missing_model(tmp_path):
    from ultron.audio.smart_turn import SmartTurnDetector, SmartTurnLoadError
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(tmp_path / "no_such.onnx")


def test_detector_construction_rejects_out_of_range_threshold(tmp_path):
    from ultron.audio.smart_turn import SmartTurnDetector, SmartTurnLoadError
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")  # presence check only -- never opened in this test
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(stub, completion_threshold=0.0)
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(stub, completion_threshold=1.0)
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(stub, completion_threshold=-0.1)


def test_detector_construction_rejects_negative_window(tmp_path):
    from ultron.audio.smart_turn import SmartTurnDetector, SmartTurnLoadError
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(stub, window_seconds=0.0)
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(stub, window_seconds=-1.0)


def test_detector_construction_rejects_zero_threads(tmp_path):
    from ultron.audio.smart_turn import SmartTurnDetector, SmartTurnLoadError
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")
    with pytest.raises(SmartTurnLoadError):
        SmartTurnDetector(stub, num_threads=0)


def test_detector_is_lazy_loaded(tmp_path):
    """Construction must NOT load the ONNX session into memory --
    that happens on first is_complete() call or via warmup(). Keeps
    cold start cheap when the detector is enabled but never invoked."""
    from ultron.audio.smart_turn import SmartTurnDetector
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")  # presence check only; we never call is_complete
    det = SmartTurnDetector(stub)
    assert det.available is False  # not loaded yet
    assert det._session is None
    assert det._feature_extractor is None


def test_detector_warmup_propagates_load_failure(tmp_path):
    """warmup() returns False when load fails (bogus ONNX bytes).
    Subsequent is_complete() calls return None (undecided)."""
    from ultron.audio.smart_turn import SmartTurnDetector
    stub = tmp_path / "bogus.onnx"
    stub.write_bytes(b"this is not a real onnx model")
    det = SmartTurnDetector(stub)
    assert det.warmup() is False
    assert det.available is False
    assert det._load_failed is True


def test_detector_is_complete_returns_none_when_load_failed(tmp_path):
    """After a failed load, all subsequent is_complete() calls return
    None (treated as 'undecided' by the orchestrator -> trust VAD)."""
    from ultron.audio.smart_turn import SmartTurnDetector
    stub = tmp_path / "bogus.onnx"
    stub.write_bytes(b"not onnx")
    det = SmartTurnDetector(stub)
    det.warmup()  # forces load to fail
    audio = np.random.randn(16000).astype(np.float32)
    assert det.is_complete(audio) is None


def test_detector_is_complete_returns_none_on_empty_audio(tmp_path):
    """Empty audio buffer can't be classified -- return None so the
    caller falls back to VAD's verdict."""
    from ultron.audio.smart_turn import SmartTurnDetector
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")
    det = SmartTurnDetector(stub)
    empty = np.zeros(0, dtype=np.float32)
    assert det.is_complete(empty) is None


def test_detector_is_complete_returns_none_on_wrong_sample_rate(tmp_path):
    """Wrong sample rate -> None (logged at WARN). Callers shouldn't
    silently get a misclassified verdict on a resampling error."""
    from ultron.audio.smart_turn import SmartTurnDetector
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")
    det = SmartTurnDetector(stub)
    audio = np.zeros(48000, dtype=np.float32)
    assert det.is_complete(audio, sample_rate=48000) is None


def test_detector_close_is_idempotent_and_disables(tmp_path):
    from ultron.audio.smart_turn import SmartTurnDetector
    stub = tmp_path / "stub.onnx"
    stub.write_bytes(b"")
    det = SmartTurnDetector(stub)
    det.close()
    det.close()  # idempotent
    assert det.available is False
    audio = np.zeros(16000, dtype=np.float32)
    assert det.is_complete(audio) is None


# ---------------------------------------------------------------------------
# build_detector_from_config -- fail-open contract
# ---------------------------------------------------------------------------


def test_build_detector_returns_none_when_disabled(tmp_path):
    """``enabled=false`` skips construction even when the model file
    exists -- operator opt-out path."""
    from ultron.audio.smart_turn import build_detector_from_config
    from ultron.config import SmartTurnConfig
    cfg = SmartTurnConfig(enabled=False)
    assert build_detector_from_config(cfg, tmp_path) is None


def test_build_detector_returns_none_when_model_missing(tmp_path):
    """Enabled + missing file -> None (logged at WARN). Orchestrator
    falls back to legacy VAD-only end-of-turn. This is the primary
    rollout-safety path: users who haven't run download_models.py
    don't get a hard error."""
    from ultron.audio.smart_turn import build_detector_from_config
    from ultron.config import SmartTurnConfig
    cfg = SmartTurnConfig(
        enabled=True,
        model_path="models/smart_turn/does-not-exist.onnx",
    )
    assert build_detector_from_config(cfg, tmp_path) is None


def test_build_detector_returns_none_when_absolute_path_missing(tmp_path):
    """Absolute paths are honoured directly -- no PROJECT_ROOT join."""
    from ultron.audio.smart_turn import build_detector_from_config
    from ultron.config import SmartTurnConfig
    cfg = SmartTurnConfig(model_path=str(tmp_path / "nope.onnx"))
    assert build_detector_from_config(cfg, tmp_path) is None


def test_build_detector_succeeds_when_file_present(tmp_path):
    """Stub a model file at the configured path; construction
    succeeds and returns a detector. (The detector is lazy, so we
    don't have to bake in a real ONNX -- the file just has to exist
    and be non-empty.)"""
    from ultron.audio.smart_turn import build_detector_from_config, SmartTurnDetector
    from ultron.config import SmartTurnConfig
    stub = tmp_path / "models" / "smart_turn" / "stub.onnx"
    stub.parent.mkdir(parents=True)
    stub.write_bytes(b"stub")
    cfg = SmartTurnConfig(model_path="models/smart_turn/stub.onnx")
    det = build_detector_from_config(cfg, tmp_path)
    assert isinstance(det, SmartTurnDetector)
    assert det.available is False  # still lazy


# ---------------------------------------------------------------------------
# Real-model tests (gated on the production ONNX file being on disk)
# ---------------------------------------------------------------------------

_HAVE_REAL_MODEL = _REAL_MODEL_PATH.is_file()


@pytest.mark.skipif(
    not _HAVE_REAL_MODEL,
    reason=f"smart-turn-v3.2-cpu.onnx not present at {_REAL_MODEL_PATH} "
           f"(run scripts/download_models.py to fetch)",
)
def test_real_model_loads_and_warmup_succeeds():
    """End-to-end smoke: real ONNX loads + warmup completes.

    CPU-only -- doesn't touch GPU or load any voice-stack component.
    Safe in the default test sweep when the model is present."""
    from ultron.audio.smart_turn import SmartTurnDetector
    det = SmartTurnDetector(_REAL_MODEL_PATH)
    assert det.warmup() is True
    assert det.available is True


@pytest.mark.skipif(
    not _HAVE_REAL_MODEL,
    reason=f"smart-turn-v3.2-cpu.onnx not present at {_REAL_MODEL_PATH}",
)
def test_real_model_returns_well_formed_verdict_on_silence():
    """Pure silence is highly unlikely to be classified as a
    complete utterance -- but the structural contract holds:
    probability in [0,1], latency_ms > 0, is_complete is a bool."""
    from ultron.audio.smart_turn import SmartTurnDetector
    det = SmartTurnDetector(_REAL_MODEL_PATH)
    silence = np.zeros(8 * 16000, dtype=np.float32)
    verdict = det.is_complete(silence)
    assert verdict is not None
    assert isinstance(verdict.is_complete, bool)
    assert 0.0 <= verdict.probability <= 1.0
    assert verdict.latency_ms > 0.0


@pytest.mark.skipif(
    not _HAVE_REAL_MODEL,
    reason=f"smart-turn-v3.2-cpu.onnx not present at {_REAL_MODEL_PATH}",
)
def test_real_model_threshold_changes_verdict():
    """Same audio, different thresholds -> potentially different
    verdicts. The probability stays the same; only is_complete flips.
    """
    from ultron.audio.smart_turn import SmartTurnDetector
    audio = np.random.randn(8 * 16000).astype(np.float32) * 0.1
    det_loose = SmartTurnDetector(_REAL_MODEL_PATH, completion_threshold=0.1)
    det_strict = SmartTurnDetector(_REAL_MODEL_PATH, completion_threshold=0.9)
    v_loose = det_loose.is_complete(audio)
    v_strict = det_strict.is_complete(audio)
    assert v_loose is not None and v_strict is not None
    # Same probability (deterministic given same input).
    assert abs(v_loose.probability - v_strict.probability) < 1e-6
    # Loose threshold should classify at-or-above strict.
    # i.e. loose.is_complete is True iff strict OR prob > 0.1.
    if v_strict.is_complete:
        assert v_loose.is_complete


@pytest.mark.skipif(
    not _HAVE_REAL_MODEL,
    reason=f"smart-turn-v3.2-cpu.onnx not present at {_REAL_MODEL_PATH}",
)
def test_real_model_handles_short_audio():
    """Audio much shorter than the 8s window should still produce a
    valid verdict (WhisperFeatureExtractor pads zeros at the start)."""
    from ultron.audio.smart_turn import SmartTurnDetector
    det = SmartTurnDetector(_REAL_MODEL_PATH)
    short = np.random.randn(int(0.5 * 16000)).astype(np.float32) * 0.1
    verdict = det.is_complete(short)
    assert verdict is not None
    assert 0.0 <= verdict.probability <= 1.0


@pytest.mark.skipif(
    not _HAVE_REAL_MODEL,
    reason=f"smart-turn-v3.2-cpu.onnx not present at {_REAL_MODEL_PATH}",
)
def test_real_model_handles_long_audio_via_truncation():
    """Audio longer than 8s is truncated to the last 8s by the
    wrapper; the model never sees more than 8s of input."""
    from ultron.audio.smart_turn import SmartTurnDetector
    det = SmartTurnDetector(_REAL_MODEL_PATH)
    long_audio = np.random.randn(12 * 16000).astype(np.float32) * 0.1
    verdict = det.is_complete(long_audio)
    assert verdict is not None
    assert 0.0 <= verdict.probability <= 1.0


@pytest.mark.skipif(
    not _HAVE_REAL_MODEL,
    reason=f"smart-turn-v3.2-cpu.onnx not present at {_REAL_MODEL_PATH}",
)
def test_real_model_inference_latency_under_budget():
    """Pipecat advertises ~12 ms CPU inference. We give a generous
    150 ms ceiling -- the first call includes one-time graph
    optimisation and may be slower; the median of subsequent calls
    should be comfortably under the target."""
    from ultron.audio.smart_turn import SmartTurnDetector
    det = SmartTurnDetector(_REAL_MODEL_PATH)
    det.warmup()  # eat the first-call overhead
    audio = np.random.randn(8 * 16000).astype(np.float32) * 0.1
    latencies: list[float] = []
    for _ in range(5):
        verdict = det.is_complete(audio)
        assert verdict is not None
        latencies.append(verdict.latency_ms)
    median = sorted(latencies)[len(latencies) // 2]
    # Per-call ceiling: 150 ms is generous (includes feature
    # extraction overhead, which is ~10-30 ms on modern CPUs).
    assert median < 150.0, f"median latency {median:.1f}ms exceeds 150ms budget"


# ---------------------------------------------------------------------------
# Orchestrator-level wiring (uses Orchestrator.__new__ to skip heavy init)
# ---------------------------------------------------------------------------


def _make_orch_for_smart_turn(*, smart_turn=None, smart_turn_cfg=None):
    """Build a partially-initialised Orchestrator with just enough
    attributes for the smart-turn helper methods. The construction
    skips audio/vad/llm/tts/etc."""
    from ultron.pipeline.orchestrator import Orchestrator
    o = Orchestrator.__new__(Orchestrator)
    o.smart_turn = smart_turn
    o._smart_turn_cfg = smart_turn_cfg
    o._smart_turn_window_seconds = 8.0
    o._smart_turn_fast_path_silence_ms = 500
    o._smart_turn_incomplete_extension_ms = 700
    return o


def test_orchestrator_smart_turn_should_check_returns_false_when_detector_missing():
    """No detector -> always skip the check, regardless of speech state."""
    from ultron.pipeline.orchestrator import Orchestrator
    o = _make_orch_for_smart_turn(smart_turn=None)
    assert o._smart_turn_should_check(speech_seen=True, speech_samples=8000) is False


def test_orchestrator_smart_turn_should_check_returns_false_without_speech():
    """No speech detected -> nothing for smart-turn to analyse."""
    class _StubDetector:
        pass
    o = _make_orch_for_smart_turn(smart_turn=_StubDetector())
    assert o._smart_turn_should_check(speech_seen=False, speech_samples=0) is False


def test_orchestrator_smart_turn_should_check_returns_true_within_window():
    """Detector present + speech detected + utterance within 8 s of
    speech -> fire smart-turn."""
    class _StubDetector:
        pass
    o = _make_orch_for_smart_turn(smart_turn=_StubDetector())
    # 7 seconds of speech at 16 kHz (orchestrator uses 16 kHz).
    assert o._smart_turn_should_check(
        speech_seen=True, speech_samples=7 * 16000,
    ) is True


def test_orchestrator_smart_turn_should_check_returns_false_above_window():
    """Utterance longer than smart-turn's training window -> bypass
    the model (the adaptive long-utterance VAD backstop handles it)."""
    class _StubDetector:
        pass
    o = _make_orch_for_smart_turn(smart_turn=_StubDetector())
    # 10 seconds of speech > 8 s window.
    assert o._smart_turn_should_check(
        speech_seen=True, speech_samples=10 * 16000,
    ) is False


def test_orchestrator_run_smart_turn_swallows_exceptions():
    """Detector's is_complete raising must not propagate. The caller
    treats the resulting None as 'undecided' -> trust VAD."""
    class _BoomDetector:
        def is_complete(self, audio, sample_rate=16000):
            raise RuntimeError("intentional test failure")
    o = _make_orch_for_smart_turn(smart_turn=_BoomDetector())
    audio = np.zeros(16000, dtype=np.float32)
    assert o._run_smart_turn(audio) is None


def test_orchestrator_run_smart_turn_passes_through_verdict():
    """A successful verdict from the detector is returned verbatim."""
    from ultron.audio.smart_turn import SmartTurnVerdict
    expected = SmartTurnVerdict(
        is_complete=True, probability=0.85, latency_ms=10.0,
    )
    class _FakeDetector:
        def is_complete(self, audio, sample_rate=16000):
            return expected
    o = _make_orch_for_smart_turn(smart_turn=_FakeDetector())
    audio = np.zeros(16000, dtype=np.float32)
    result = o._run_smart_turn(audio)
    assert result is expected


def test_orchestrator_run_smart_turn_returns_none_when_detector_none():
    """No detector -> immediate None without touching audio."""
    o = _make_orch_for_smart_turn(smart_turn=None)
    audio = np.zeros(16000, dtype=np.float32)
    assert o._run_smart_turn(audio) is None


def test_orchestrator_build_smart_turn_detector_returns_none_when_disabled():
    """When ``_smart_turn_cfg`` is None (disabled via config or
    construction-time fallback), the build helper returns None."""
    o = _make_orch_for_smart_turn(smart_turn_cfg=None)
    assert o._build_smart_turn_detector() is None


def test_orchestrator_build_smart_turn_detector_returns_none_when_file_missing(tmp_path):
    """Enabled config + missing file -> None (fail-open)."""
    from ultron.config import SmartTurnConfig
    cfg = SmartTurnConfig(
        enabled=True,
        model_path="models/smart_turn/does-not-exist.onnx",
    )
    o = _make_orch_for_smart_turn(smart_turn_cfg=cfg)
    assert o._build_smart_turn_detector() is None
