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
    # Schema default is XTTS-native 1.0 so direct ctor calls (mostly
    # tests) stay back-compat. The production value lives in
    # config.yaml.
    assert cfg.speed == 1.0
    # 2026-05-12 phantom-token mitigation: schema default 0.65 (vs
    # the XTTS library's 0.75). Tightens the duration-token
    # distribution so the model emits fewer phantom syllables.
    assert cfg.temperature == 0.65
    # Phantom-tail trim is defence-in-depth on top of the temperature
    # reduction. Default ON: trim is conservative (only fires when
    # the specific phantom pattern is matched).
    assert cfg.phantom_tail_trim_enabled is True
    assert cfg.phantom_tail_silence_threshold == 0.005
    assert cfg.phantom_tail_max_event_ms == 200.0
    assert cfg.phantom_tail_min_lead_silence_ms == 150.0


def test_xtts_v3_config_speed_range_enforced():
    """Bounded to keep things in the natural-sounding range. Below
    ~0.7 the model sounds drawn out; above ~1.4 it starts to slur
    consonants. The schema clamps at [0.5, 2.0] so callers can't
    accidentally ship a setting that destroys intelligibility."""
    from pydantic import ValidationError
    XttsV3Config(speed=0.5)  # ok (lower bound)
    XttsV3Config(speed=1.15)  # ok (production value)
    XttsV3Config(speed=2.0)  # ok (upper bound)
    with pytest.raises(ValidationError):
        XttsV3Config(speed=0.49)
    with pytest.raises(ValidationError):
        XttsV3Config(speed=2.01)


def test_xtts_v3_config_speed_round_trips_through_dict():
    cfg = XttsV3Config(speed=1.15)
    cfg2 = XttsV3Config.model_validate(cfg.model_dump())
    assert cfg2.speed == 1.15


def test_xtts_v3_config_filter_tail_ms_range_enforced():
    from pydantic import ValidationError
    XttsV3Config(filter_tail_silence_ms=0.0)  # ok
    XttsV3Config(filter_tail_silence_ms=2000.0)  # ok
    with pytest.raises(ValidationError):
        XttsV3Config(filter_tail_silence_ms=-1.0)
    with pytest.raises(ValidationError):
        XttsV3Config(filter_tail_silence_ms=2500.0)


def test_xtts_v3_client_forwards_speed_in_http_body(monkeypatch, tmp_path):
    """Pure wiring test: confirms ``XttsV3Speech._http_synthesize``
    sends the configured speed in the POST JSON body so the server's
    XTTS ``inference_stream(speed=...)`` call actually picks it up.

    Mocks the subprocess + HTTP seams so we don't load the voice
    stack (per feedback_voice_stack_concurrency). If the client ever
    silently drops the speed field, this test fails."""
    import json
    import urllib.request
    from ultron.tts import xtts_v3

    # The constructor asserts the configured paths exist; stub files
    # under tmp_path satisfy that without spawning anything.
    server_py = tmp_path / "python.exe"
    server_py.write_text("")
    server_sc = tmp_path / "xtts_server.py"
    server_sc.write_text("")
    ref_wav = tmp_path / "ref.wav"
    ref_wav.write_text("")

    captured: list[bytes] = []

    class _FakeResp:
        headers = {"X-Sample-Rate": "24000"}
        def read(self, n=None):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    def _fake_urlopen(req, timeout=None):
        data = getattr(req, "data", None)
        if data:
            captured.append(data)
        return _FakeResp()

    # Skip the subprocess spawn + health-probe loop.
    monkeypatch.setattr(xtts_v3.XttsV3Speech, "_start_server", lambda self: None)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    engine = xtts_v3.XttsV3Speech(
        server_python=server_py,
        server_script=server_sc,
        reference_audio=ref_wav,
        port=12345,
        speed=1.15,
    )

    engine._http_synthesize("hello there")

    assert captured, "expected exactly one POST to /synthesize"
    body = json.loads(captured[0].decode("utf-8"))
    assert body["text"] == "hello there"
    assert body["language"] == "en"
    assert body["speed"] == 1.15


# ---------------------------------------------------------------------------
# Temperature schema + HTTP-body wiring (2026-05-12 phantom-token mitigation)
# ---------------------------------------------------------------------------


def test_xtts_v3_config_temperature_range_enforced():
    """Bounded so callers can't ship a setting that destroys the
    duration-token distribution. Below ~0.4 prosody collapses; above
    ~1.0 the model becomes unstable."""
    from pydantic import ValidationError
    XttsV3Config(temperature=0.4)
    XttsV3Config(temperature=0.65)  # schema default
    XttsV3Config(temperature=1.0)
    with pytest.raises(ValidationError):
        XttsV3Config(temperature=0.39)
    with pytest.raises(ValidationError):
        XttsV3Config(temperature=1.01)


def test_xtts_v3_config_temperature_round_trips_through_dict():
    cfg = XttsV3Config(temperature=0.65)
    cfg2 = XttsV3Config.model_validate(cfg.model_dump())
    assert cfg2.temperature == 0.65


def test_xtts_v3_client_forwards_temperature_in_http_body(monkeypatch, tmp_path):
    """Pure wiring test: confirms ``XttsV3Speech._http_synthesize``
    sends the configured temperature in the POST JSON body. If the
    client ever silently drops the temperature field, the server
    falls back to its library default of 0.75 and the phantom-token
    rate goes back up. This test pins that wiring closed."""
    import json
    import urllib.request
    from ultron.tts import xtts_v3

    server_py = tmp_path / "python.exe"
    server_py.write_text("")
    server_sc = tmp_path / "xtts_server.py"
    server_sc.write_text("")
    ref_wav = tmp_path / "ref.wav"
    ref_wav.write_text("")

    captured: list[bytes] = []

    class _FakeResp:
        headers = {"X-Sample-Rate": "24000"}
        def read(self, n=None):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    def _fake_urlopen(req, timeout=None):
        data = getattr(req, "data", None)
        if data:
            captured.append(data)
        return _FakeResp()

    monkeypatch.setattr(xtts_v3.XttsV3Speech, "_start_server", lambda self: None)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    engine = xtts_v3.XttsV3Speech(
        server_python=server_py,
        server_script=server_sc,
        reference_audio=ref_wav,
        port=12345,
        temperature=0.65,
    )

    engine._http_synthesize("hello there")

    assert captured, "expected exactly one POST to /synthesize"
    body = json.loads(captured[0].decode("utf-8"))
    assert body["temperature"] == 0.65


# ---------------------------------------------------------------------------
# Phantom-tail trim configuration (2026-05-12 phantom-token mitigation)
# ---------------------------------------------------------------------------


def test_xtts_v3_config_phantom_tail_trim_enabled_default_on():
    cfg = XttsV3Config()
    assert cfg.phantom_tail_trim_enabled is True


def test_xtts_v3_config_phantom_tail_silence_threshold_range_enforced():
    from pydantic import ValidationError
    XttsV3Config(phantom_tail_silence_threshold=0.0001)
    XttsV3Config(phantom_tail_silence_threshold=0.005)  # schema default
    XttsV3Config(phantom_tail_silence_threshold=0.05)
    with pytest.raises(ValidationError):
        XttsV3Config(phantom_tail_silence_threshold=0.0)
    with pytest.raises(ValidationError):
        XttsV3Config(phantom_tail_silence_threshold=0.06)


def test_xtts_v3_config_phantom_tail_max_event_ms_range_enforced():
    from pydantic import ValidationError
    XttsV3Config(phantom_tail_max_event_ms=50.0)
    XttsV3Config(phantom_tail_max_event_ms=200.0)  # schema default
    XttsV3Config(phantom_tail_max_event_ms=500.0)
    with pytest.raises(ValidationError):
        XttsV3Config(phantom_tail_max_event_ms=49.0)
    with pytest.raises(ValidationError):
        XttsV3Config(phantom_tail_max_event_ms=501.0)


def test_xtts_v3_config_phantom_tail_min_lead_silence_ms_range_enforced():
    from pydantic import ValidationError
    XttsV3Config(phantom_tail_min_lead_silence_ms=50.0)
    XttsV3Config(phantom_tail_min_lead_silence_ms=150.0)  # schema default
    XttsV3Config(phantom_tail_min_lead_silence_ms=500.0)
    with pytest.raises(ValidationError):
        XttsV3Config(phantom_tail_min_lead_silence_ms=49.0)
    with pytest.raises(ValidationError):
        XttsV3Config(phantom_tail_min_lead_silence_ms=501.0)


# ---------------------------------------------------------------------------
# trim_phantom_tail function — pure DSP, no engine needed
# ---------------------------------------------------------------------------


def _build_buffer(sr: int, *segments: tuple[str, float, float]) -> np.ndarray:
    """Helper: build a float32 audio buffer from (kind, duration_s, amplitude) segments.

    ``kind == 'silence'`` produces zeros; anything else produces a
    sine wave at 200 Hz scaled to the amplitude. Simulates the
    phantom-token signature (sustained speech -> silence -> short
    burst -> silence) deterministically.
    """
    chunks: list[np.ndarray] = []
    for kind, dur_s, amp in segments:
        n = int(dur_s * sr)
        if kind == "silence" or amp == 0.0:
            chunks.append(np.zeros(n, dtype=np.float32))
        else:
            t = np.linspace(0.0, dur_s, n, endpoint=False, dtype=np.float32)
            chunks.append((amp * np.sin(2 * np.pi * 200.0 * t)).astype(np.float32))
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)


def test_trim_phantom_tail_detects_and_removes_classic_phantom():
    """Reproduces the 19.28s pattern observed in the user's session:
    long speech -> ~280 ms silence -> ~100 ms isolated burst ->
    ~420 ms silence. The trim should keep the long speech (plus a
    small grace cushion) and drop everything after."""
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    buf = _build_buffer(
        sr,
        ("speech", 1.5, 0.3),    # sustained speech
        ("silence", 0.28, 0.0),  # lead silence (>=150ms threshold)
        ("speech", 0.10, 0.3),   # the phantom (100 ms event, <200ms ceiling)
        ("silence", 0.42, 0.0),  # trailing silence
    )
    out, trimmed = trim_phantom_tail(buf, sr)
    assert trimmed is True
    # The trim should land somewhere AT or shortly AFTER 1.5 s
    # (sustained speech end) and definitely BEFORE 1.78 s (where the
    # phantom starts).
    keep_s = out.shape[0] / sr
    assert 1.5 <= keep_s < 1.78


def test_trim_phantom_tail_leaves_sustained_speech_alone():
    """An ordinary speech clip with no phantom (just sustained speech
    followed by silence) should NOT be trimmed -- legitimate end-of-
    sentence audio must be preserved."""
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    buf = _build_buffer(
        sr,
        ("speech", 2.0, 0.3),
        ("silence", 0.20, 0.0),
    )
    out, trimmed = trim_phantom_tail(buf, sr)
    assert trimmed is False
    assert out.shape[0] == buf.shape[0]


def test_trim_phantom_tail_leaves_short_inter_word_silence_alone():
    """A natural mid-sentence inter-word pause (short silence) between
    two speech regions must NOT be misread as a phantom signature.
    The 150 ms ``min_lead_silence_ms`` threshold should reject a
    100 ms gap as too short."""
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    buf = _build_buffer(
        sr,
        ("speech", 1.0, 0.3),
        ("silence", 0.10, 0.0),  # short inter-word gap
        ("speech", 0.08, 0.3),   # short trailing word
        ("silence", 0.30, 0.0),
    )
    out, trimmed = trim_phantom_tail(buf, sr)
    assert trimmed is False


def test_trim_phantom_tail_leaves_legitimate_long_trailing_speech_alone():
    """A trailing event longer than ``max_event_ms`` is legitimate
    speech, not a phantom. Verify even when preceded by long
    silence we don't trim it."""
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    buf = _build_buffer(
        sr,
        ("speech", 1.0, 0.3),
        ("silence", 0.30, 0.0),
        ("speech", 0.40, 0.3),  # 400 ms trailing event > 200 ms ceiling
        ("silence", 0.10, 0.0),
    )
    out, trimmed = trim_phantom_tail(buf, sr)
    assert trimmed is False


def test_trim_phantom_tail_handles_empty_input():
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    empty = np.zeros(0, dtype=np.float32)
    out, trimmed = trim_phantom_tail(empty, sr)
    assert trimmed is False
    assert out.shape[0] == 0


def test_trim_phantom_tail_handles_very_short_clip():
    """Anything shorter than four analysis windows can't be reliably
    classified -- bail out without trimming."""
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    short = np.zeros(int(0.03 * sr), dtype=np.float32)  # 30 ms < 4 * 20 ms
    out, trimmed = trim_phantom_tail(short, sr)
    assert trimmed is False
    assert out.shape[0] == short.shape[0]


def test_trim_phantom_tail_handles_all_silent_clip():
    """Pure silence has no speech to anchor the pattern. Pass through."""
    from ultron.tts.xtts_v3 import trim_phantom_tail
    sr = 24000
    silent = np.zeros(int(2.0 * sr), dtype=np.float32)
    out, trimmed = trim_phantom_tail(silent, sr)
    assert trimmed is False
    assert out.shape[0] == silent.shape[0]


def test_trim_phantom_tail_respects_disabled_flag_via_engine(monkeypatch, tmp_path):
    """When ``phantom_tail_trim_enabled=False`` the engine skips the
    trim entirely -- useful for A/B comparison. Verify by patching
    the trim function and asserting it is NOT called."""
    import urllib.request
    from ultron.tts import xtts_v3

    server_py = tmp_path / "python.exe"
    server_py.write_text("")
    server_sc = tmp_path / "xtts_server.py"
    server_sc.write_text("")
    ref_wav = tmp_path / "ref.wav"
    ref_wav.write_text("")

    class _FakeResp:
        headers = {"X-Sample-Rate": "24000"}
        def read(self, n=None):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    # Server returns 100 ms of silence so _synthesize has audio to
    # filter (synth path is shared between trim-on and trim-off).
    pcm = (np.zeros(2400, dtype=np.int16)).tobytes()
    response_chunks = [pcm, b""]

    class _ResponseWithBody(_FakeResp):
        def __init__(self):
            self._chunks = list(response_chunks)
        def read(self, n=None):
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    def _fake_urlopen(req, timeout=None):
        return _ResponseWithBody()

    monkeypatch.setattr(xtts_v3.XttsV3Speech, "_start_server", lambda self: None)
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    call_counter = {"n": 0}

    def _spy_trim(*args, **kwargs):
        call_counter["n"] += 1
        return args[0], False

    monkeypatch.setattr(xtts_v3, "trim_phantom_tail", _spy_trim)

    engine = xtts_v3.XttsV3Speech(
        server_python=server_py,
        server_script=server_sc,
        reference_audio=ref_wav,
        port=12345,
        phantom_tail_trim_enabled=False,
    )

    engine._synthesize("hello")
    assert call_counter["n"] == 0


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
