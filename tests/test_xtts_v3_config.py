"""Tests for the XTTS v3 TTS engine selection + config schema.

Covers the 2026-05-10 voice-pipeline swap:

- ``tts.engine`` defaults to legacy ``piper_rvc`` so existing
  installs keep working without config changes.
- ``"xtts_v3"`` is accepted by the schema.
- Unknown engine names are rejected.
- ``XttsV3Config`` round-trips through the loader with the expected
  defaults pointing at the audio prep layout.
- The ultron filter module imports cleanly with all three presets.
"""

from __future__ import annotations

import numpy as np
import pytest

from ultron.config import (
    TTSConfig,
    UltronConfig,
    XttsV3Config,
)


# ---------------------------------------------------------------------------
# Engine selection schema
# ---------------------------------------------------------------------------


def test_tts_engine_defaults_to_legacy_piper_rvc():
    cfg = TTSConfig()
    assert cfg.engine == "piper_rvc"


def test_tts_engine_accepts_xtts_v3():
    cfg = TTSConfig(engine="xtts_v3")
    assert cfg.engine == "xtts_v3"


def test_tts_engine_rejects_unknown_value():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TTSConfig(engine="kokoro_lora")


# ---------------------------------------------------------------------------
# XttsV3Config defaults
# ---------------------------------------------------------------------------


def test_xtts_v3_config_defaults_match_audio_prep_layout():
    """Defaults point at the layout established during the 2026-05-10
    voice swap. If the audio prep moves, these defaults need to move
    with it AND the engine has to keep working without explicit
    config overrides."""
    cfg = XttsV3Config()
    assert cfg.server_python.endswith(".venv-xtts/Scripts/python.exe")
    assert cfg.server_script.endswith("xtts_server.py")
    assert cfg.reference_audio.endswith("Ultron_vocals_mono_v1.wav")
    assert cfg.host == "127.0.0.1"
    assert cfg.port is None  # engine picks free port at startup
    assert cfg.filter_preset == "v3_heavy"
    assert cfg.filter_tail_silence_ms == 200.0


def test_xtts_v3_config_filter_tail_ms_range_enforced():
    from pydantic import ValidationError
    XttsV3Config(filter_tail_silence_ms=0.0)  # ok
    XttsV3Config(filter_tail_silence_ms=2000.0)  # ok
    with pytest.raises(ValidationError):
        XttsV3Config(filter_tail_silence_ms=-1.0)
    with pytest.raises(ValidationError):
        XttsV3Config(filter_tail_silence_ms=2500.0)


def test_xtts_v3_config_nested_under_tts():
    cfg = TTSConfig()
    assert isinstance(cfg.xtts_v3, XttsV3Config)
    assert cfg.xtts_v3.filter_preset == "v3_heavy"


def test_full_ultron_config_round_trips_with_xtts_v3_engine():
    cfg = UltronConfig()
    cfg.tts.engine = "xtts_v3"
    cfg.tts.xtts_v3.filter_preset = "v2_medium"
    # Round-trip through dict to mimic YAML load.
    cfg2 = UltronConfig.model_validate(cfg.model_dump())
    assert cfg2.tts.engine == "xtts_v3"
    assert cfg2.tts.xtts_v3.filter_preset == "v2_medium"


# ---------------------------------------------------------------------------
# Ultron filter (runtime port)
# ---------------------------------------------------------------------------


def test_ultron_filter_imports_all_three_presets():
    from ultron.tts.ultron_filter import get_preset
    for preset_name in ("v1_subtle", "v2_medium", "v3_heavy"):
        board = get_preset(preset_name)
        # Each preset constructs a fresh Pedalboard with a non-empty plugin chain.
        assert board is not None
        # Mutating the chain should not affect a freshly-constructed one.
        board2 = get_preset(preset_name)
        assert board is not board2


def test_ultron_filter_unknown_preset_raises():
    from ultron.tts.ultron_filter import get_preset
    with pytest.raises(ValueError):
        get_preset("v99_galaxy_brain")  # type: ignore[arg-type]


def test_ultron_filter_apply_roundtrips_silence_with_tail_padding():
    """A silent input should come back longer by ~tail_silence_ms when
    tail padding is enabled. Validates that the padding logic actually
    extends the buffer (so the reverb tail has room to decay)."""
    from ultron.tts.ultron_filter import apply_filter
    sr = 24000
    silent = np.zeros(int(0.5 * sr), dtype=np.float32)
    out = apply_filter(silent, sr, preset="v3_heavy", tail_silence_ms=200.0)
    expected_len = silent.shape[0] + int(0.200 * sr)
    # Allow ~ a few samples of slop from filter internal state.
    assert abs(out.shape[0] - expected_len) < int(0.005 * sr)


def test_ultron_filter_apply_no_tail_padding_preserves_length():
    from ultron.tts.ultron_filter import apply_filter
    sr = 24000
    audio = np.zeros(int(0.5 * sr), dtype=np.float32)
    out = apply_filter(audio, sr, preset="v3_heavy", tail_silence_ms=0.0)
    assert out.shape[0] == audio.shape[0]


def test_ultron_filter_apply_int16_preserves_dtype():
    from ultron.tts.ultron_filter import apply_filter
    sr = 24000
    audio = np.zeros(int(0.5 * sr), dtype=np.int16)
    out = apply_filter(audio, sr, preset="v3_heavy", tail_silence_ms=0.0)
    assert out.dtype == np.int16
