"""Ultron mechanical-voice DSP filter chain (runtime).

XTTS v2 (or any neural cloning TTS) produces clean natural speech in
the cloned Ultron voice character. The MCU Ultron voice has an
additional DSP processing layer on top -- the "robotic / mechanical
/ hollow metal cavity" character. This module is that processing
layer, applied at synthesis output time before audio reaches the
speaker.

Architecturally this is the runtime port of the prototype that lives
at ``ultronVoiceAudio/scripts/ultron_filter.py``. The presets are
identical (v3_heavy is the user-locked production preset). The only
runtime-specific tweak is a smaller default ``tail_silence_ms`` --
the prototype uses 500 ms (preserves full reverb decay for offline
sample evaluation), runtime uses ~200 ms (the audible portion of the
v3_heavy reverb tail; the orchestrator's existing inter-sentence
pause absorbs the rest).

Total per-sentence processing latency on CPU: ~5-15 ms for the full
v3_heavy chain on typical sentence-length audio. Sub-millisecond
overhead per pedalboard step.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from pedalboard import (
    Chorus,
    Compressor,
    Delay,
    Distortion,
    HighShelfFilter,
    HighpassFilter,
    LowShelfFilter,
    LowpassFilter,
    PeakFilter,
    Pedalboard,
    PitchShift,
    Reverb,
)

PresetName = Literal["v1_subtle", "v2_medium", "v3_heavy"]


# ---------------------------------------------------------------------------
# Filter chain presets (mirrors the prototype at
# ultronVoiceAudio/scripts/ultron_filter.py exactly so A/B sounds the
# same between the offline tuning samples and the runtime output).
# ---------------------------------------------------------------------------


def _v1_subtle() -> Pedalboard:
    """Light Ultron filter: noticeable but understated."""
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=80),
        PitchShift(semitones=-0.7),
        Compressor(threshold_db=-18.0, ratio=2.5, attack_ms=5.0, release_ms=80.0),
        LowShelfFilter(cutoff_frequency_hz=120, gain_db=2.0, q=0.7),
        Distortion(drive_db=3.0),
        Reverb(room_size=0.12, damping=0.65, wet_level=0.08,
               dry_level=0.92, width=1.0),
        LowpassFilter(cutoff_frequency_hz=10000),
    ])


def _v2_medium() -> Pedalboard:
    """Balanced Ultron filter: clearly mechanical, still clean."""
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=80),
        PitchShift(semitones=-1.2),
        Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=4.0, release_ms=70.0),
        LowShelfFilter(cutoff_frequency_hz=140, gain_db=3.5, q=0.7),
        Delay(delay_seconds=0.005, feedback=0.18, mix=0.13),
        Distortion(drive_db=5.0),
        PeakFilter(cutoff_frequency_hz=2400, gain_db=2.5, q=1.4),
        HighShelfFilter(cutoff_frequency_hz=6500, gain_db=-3.0, q=0.7),
        Reverb(room_size=0.16, damping=0.62, wet_level=0.12,
               dry_level=0.88, width=1.0),
        LowpassFilter(cutoff_frequency_hz=9000),
    ])


def _v3_heavy() -> Pedalboard:
    """Full Ultron filter: pronounced robotic processing.

    User-locked production preset (2026-05-10). Bit-identical to the
    prototype version; do not retune without re-running the offline
    A/B (the v4 sample batch in ``ultronVoiceAudio/sanity_v4_filtered/``
    is the ground truth).
    """
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=85),
        PitchShift(semitones=-1.8),
        Compressor(threshold_db=-22.0, ratio=4.0, attack_ms=3.0, release_ms=60.0),
        LowShelfFilter(cutoff_frequency_hz=160, gain_db=4.5, q=0.7),
        Delay(delay_seconds=0.007, feedback=0.25, mix=0.18),
        Chorus(rate_hz=0.9, depth=0.18, centre_delay_ms=4.5,
               feedback=0.10, mix=0.10),
        Distortion(drive_db=7.0),
        PeakFilter(cutoff_frequency_hz=2500, gain_db=3.5, q=1.3),
        HighShelfFilter(cutoff_frequency_hz=6000, gain_db=-4.0, q=0.7),
        Reverb(room_size=0.20, damping=0.58, wet_level=0.16,
               dry_level=0.84, width=1.0),
        LowpassFilter(cutoff_frequency_hz=8500),
    ])


_PRESETS: dict[PresetName, callable] = {
    "v1_subtle": _v1_subtle,
    "v2_medium": _v2_medium,
    "v3_heavy": _v3_heavy,
}


def get_preset(preset: PresetName) -> Pedalboard:
    """Construct a fresh pedalboard for ``preset``. Returns a NEW
    instance per call -- callers can mutate parameters without
    polluting other callers."""
    if preset not in _PRESETS:
        raise ValueError(
            f"Unknown preset {preset!r}; available: {sorted(_PRESETS)}"
        )
    return _PRESETS[preset]()


def apply_filter(
    audio: np.ndarray,
    sample_rate: int,
    preset: PresetName = "v3_heavy",
    tail_silence_ms: float = 200.0,
) -> np.ndarray:
    """Apply the Ultron filter chain to ``audio``.

    Args:
        audio: 1-D mono float32 in [-1, 1], or shape ``(N, channels)``.
        sample_rate: Hz.
        preset: which chain to apply.
        tail_silence_ms: trailing silence padded BEFORE filtering so the
            reverb tail can decay into it without being clipped at the
            buffer end. Runtime default is 200 ms (audible portion of
            the v3 reverb); offline / standalone samples should use
            500 ms for full decay. Pass 0 to disable padding.

    Returns:
        Processed audio, same dtype as input. Length = input + tail
        samples (when default).
    """
    board = get_preset(preset)
    in_dtype = audio.dtype
    if audio.dtype != np.float32:
        audio_f32 = audio.astype(np.float32)
    else:
        audio_f32 = audio.copy()

    if tail_silence_ms > 0:
        tail_n = int(tail_silence_ms / 1000.0 * sample_rate)
        if tail_n > 0:
            if audio_f32.ndim == 1:
                tail = np.zeros(tail_n, dtype=np.float32)
            else:
                tail = np.zeros((tail_n, audio_f32.shape[1]), dtype=np.float32)
            audio_f32 = np.concatenate([audio_f32, tail], axis=0)

    out = board(audio_f32, sample_rate)
    if in_dtype != np.float32:
        if np.issubdtype(in_dtype, np.integer):
            out = np.clip(out, -1.0, 1.0)
            out = (out * np.iinfo(in_dtype).max).astype(in_dtype)
        else:
            out = out.astype(in_dtype)
    return out
