"""Kenning mechanical-voice post-processing filter chain.

XTTS v2 (and Kokoro after fine-tuning) produces clean natural speech
in the cloned voice character. The MCU Kenning voice has an additional
DSP processing layer on top -- the "robotic / mechanical / hollow
metal cavity" character. This module is that processing layer.

The chain runs at synthesis output time, after Kokoro produces audio
and before it reaches the speaker. Total latency: ~5-15 ms on CPU
for typical sentence-length clips.

Three preset intensities are provided so the operator can pick the
right amount of processing. Each chain is built from the same set of
DSP primitives (pitch shift, compression, saturation, comb-style
delay, reverb, EQ); they differ in the parameter weights.

Run as a CLI to A/B several presets against one input file:

    python kenning_filter.py <input.wav> [<output_dir>]

Outputs ``<input>__filter_v1_subtle.wav``, ``__v2_medium.wav``,
``__v3_heavy.wav`` (and a ``__v0_passthrough.wav`` for reference)
into ``<output_dir>`` (defaults to the input's parent).

When called as a library, use ``apply_filter(audio, sr, preset=...)``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Tuple

import numpy as np

# pedalboard is the engine. Spotify-maintained, VST-grade DSP, all CPU.
# The handful of effects we use are well below 1 ms / sentence even on
# modest hardware.
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
# Filter chain presets
# ---------------------------------------------------------------------------


def _v1_subtle() -> Pedalboard:
    """Light Kenning filter: noticeable but understated.

    Use when the voice should feel "slightly enhanced" rather than
    obviously processed -- e.g., for casual / quiet utterances where
    you want naturalism with a hint of the machine.
    """
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
    """Balanced Kenning filter: clearly mechanical, still clean.

    Default-recommended starting point. Pitch slightly deeper, a small
    comb-style delay for the metallic edge, modest reverb body, mild
    high-shelf cut for the industrial feel.
    """
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=80),
        PitchShift(semitones=-1.2),
        Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=4.0, release_ms=70.0),
        LowShelfFilter(cutoff_frequency_hz=140, gain_db=3.5, q=0.7),
        # Short delay with light feedback approximates a thin comb
        # filter -- gives the "speaking through a metal mask" overtone.
        # Keep mix low so it sits behind the dry signal as a tint, not
        # an audible echo.
        Delay(delay_seconds=0.005, feedback=0.18, mix=0.13),
        Distortion(drive_db=5.0),
        PeakFilter(cutoff_frequency_hz=2400, gain_db=2.5, q=1.4),
        HighShelfFilter(cutoff_frequency_hz=6500, gain_db=-3.0, q=0.7),
        Reverb(room_size=0.16, damping=0.62, wet_level=0.12,
               dry_level=0.88, width=1.0),
        LowpassFilter(cutoff_frequency_hz=9000),
    ])


def _v3_heavy() -> Pedalboard:
    """Full Kenning filter: pronounced robotic processing.

    Use when the voice should obviously sound like a machine -- when
    you want maximum character at the cost of some intelligibility
    headroom. Closest to the MCU production sound.
    """
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=85),
        PitchShift(semitones=-1.8),
        Compressor(threshold_db=-22.0, ratio=4.0, attack_ms=3.0, release_ms=60.0),
        LowShelfFilter(cutoff_frequency_hz=160, gain_db=4.5, q=0.7),
        # Slightly longer delay + more feedback for a more present
        # comb resonance. Plus a touch of chorus to add the subtle
        # multi-voice / "vocoded" character.
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_preset(preset: PresetName) -> Pedalboard:
    """Construct the named preset's pedalboard chain.

    Returns a fresh Pedalboard each call so the caller can mutate
    parameters (e.g. tweak ``board[1].semitones`` to find the right
    pitch by ear) without polluting other callers.
    """
    if preset not in _PRESETS:
        raise ValueError(
            f"Unknown preset {preset!r}; available: {sorted(_PRESETS)}"
        )
    return _PRESETS[preset]()


def apply_filter(
    audio: np.ndarray,
    sample_rate: int,
    preset: PresetName = "v2_medium",
    tail_silence_ms: float = 500.0,
) -> np.ndarray:
    """Apply the Kenning filter chain to ``audio``.

    Args:
        audio: 1-D mono float32 array in [-1, 1], OR shape
            ``(samples, channels)``. Pedalboard handles both.
        sample_rate: input sample rate in Hz. Output rate is the same.
        preset: which filter chain to apply.
        tail_silence_ms: amount of trailing silence to pad onto the
            input BEFORE filtering, so the reverb / delay tail can
            decay into it naturally instead of being clipped at the
            buffer end. The output is longer than the input by this
            amount. Set to 0 to disable (output length matches input).
            Default 500 ms is comfortably more than the v3_heavy
            chain's audible tail (~250-400 ms).

    Returns:
        Processed audio array, same dtype as input. Length = input
        length + tail_silence_ms worth of samples (when default).
    """
    board = get_preset(preset)
    # Pedalboard expects float32; convert if needed.
    in_dtype = audio.dtype
    if audio.dtype != np.float32:
        audio_f32 = audio.astype(np.float32)
    else:
        audio_f32 = audio.copy()  # we will potentially mutate via concat

    # Pad trailing silence so the reverb/delay tail has room to decay.
    # Pedalboard's Reverb processes in-place on the input buffer; any
    # tail that would extend past the buffer's end is truncated. Padding
    # with silence first means the tail decays into the padding instead
    # of being clipped at the boundary.
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
        # Cast back, clipping to int16 range when relevant.
        if np.issubdtype(in_dtype, np.integer):
            out = np.clip(out, -1.0, 1.0)
            out = (out * np.iinfo(in_dtype).max).astype(in_dtype)
        else:
            out = out.astype(in_dtype)
    return out


# ---------------------------------------------------------------------------
# CLI: A/B several presets on a single input
# ---------------------------------------------------------------------------


def _cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: kenning_filter.py <input.wav> [<output_dir>]")
        return 2
    src = Path(argv[1])
    if not src.is_file():
        print(f"ERROR: input file not found: {src}")
        return 1
    out_dir = Path(argv[2]) if len(argv) >= 3 else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    import soundfile as sf
    audio, sr = sf.read(str(src), always_2d=False)
    in_dtype = audio.dtype
    print(f"input: {src.name}  shape={audio.shape}  sr={sr}  dtype={in_dtype}")

    # v0: passthrough copy for direct A/B with the unfiltered XTTS output.
    pass_path = out_dir / f"{src.stem}__v0_passthrough.wav"
    sf.write(str(pass_path), audio, sr, subtype="PCM_16")
    print(f"  v0 passthrough -> {pass_path.name}")

    for preset_name in ("v1_subtle", "v2_medium", "v3_heavy"):
        out = apply_filter(audio, sr, preset=preset_name)
        out_path = out_dir / f"{src.stem}__filter_{preset_name}.wav"
        sf.write(str(out_path), out, sr, subtype="PCM_16")
        print(f"  {preset_name:<12} -> {out_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
