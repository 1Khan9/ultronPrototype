"""Post-synthesis audio cleanup for XTTS output.

XTTS v2 produces clean speech but commonly emits two artifact classes
that need removing before the audio reaches Kokoro training (or the
runtime speaker):

1. **Edge silence + glitches.** Leading and trailing low-amplitude
   noise from autoregressive stop-token misfires. Trim symmetrically
   to the speech boundary, with asymmetric padding (more on the
   trailing side to preserve coarticulation tails like fricatives
   that decay slowly).

2. **Intra-clip blips.** When a multi-sentence input is split by XTTS
   into multiple synthesis passes and concatenated, a brief
   hallucinated phoneme can appear in the gap between sentences --
   sounds like a half-word that doesn't belong. Detect by finding a
   short audio burst (<= 200 ms) bracketed by long pauses (>= 150 ms
   each side) and silence it with crossfade.

Both passes operate frame-wise on the energy envelope. Pure DSP, no
neural model. Sub-millisecond per call.

Usage:
    from audio_cleanup import clean_xtts_output
    clean_xtts_output(path)  # rewrites path in place

CLI (clean every WAV under a directory in place, plus optional dry-run):
    python audio_cleanup.py <dir> [--dry-run]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf


# ---------------------------------------------------------------------------
# Tunable defaults. The rationale for each:
#
#  - silence_threshold_db = -45.0
#    Lower than the previous -40 to capture quieter decay tails.
#    Speech consonant releases (especially /s/, /sh/, /th/) fade
#    slowly and were getting trimmed by the -40 threshold.
#
#  - lead_pad_ms = 50
#    Short -- we want to remove leading silence/glitches aggressively.
#    The XTTS leading glitch is usually within 50-150 ms; over-padding
#    here would defeat the purpose.
#
#  - trail_pad_ms = 200
#    Generous. The user reported "last word ever so slightly cut off"
#    with the previous 50 ms trailing pad. 200 ms safely captures the
#    full release of trailing fricatives and plosives without dragging
#    in significant glitch noise (the trailing glitch is usually a
#    sharp click well after speech ends, separated by clear silence).
#
#  - fade_ms = 5
#    Short fade at edges to suppress click on the hard cut.
#
#  - intra_blip_max_ms = 200
#    Brief audio bursts longer than this are real speech, not blips.
#    XTTS hallucinations are typically much shorter (50-150 ms).
#
#  - intra_blip_pause_min_ms = 150
#    The blip must have at least this much silence on BOTH sides to
#    be considered an inter-sentence anomaly (not a normal short
#    word).
#
#  - intra_blip_fade_ms = 10
#    Crossfade at blip-replacement boundaries to avoid clicks.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CleanupConfig:
    silence_threshold_db: float = -45.0
    lead_pad_ms: float = 50.0
    # Was 200; bumped to 300 to capture full decay of trailing
    # fricatives (/s/, /sh/, /th/, /f/) that decay slowly. The user
    # reported "tiny microscopic bit of the s at end of 'steps' ends
    # a bit early" with 200 ms.
    trail_pad_ms: float = 300.0
    fade_ms: float = 5.0
    # Minimum length for a segment to count as "main speech body".
    # Anything shorter than this at the LEADING or TRAILING edge,
    # separated from the main body by silence, is treated as a
    # glitch / artifact and excluded from the trim window. Catches
    # the "tiny static at the very very end" failure mode where a
    # brief burst lands after the real speech ended.
    main_segment_min_ms: float = 80.0
    # If a short edge segment is separated from the main body by at
    # least this much silence, it's classed as a glitch and dropped.
    edge_glitch_gap_min_ms: float = 100.0
    intra_blip_max_ms: float = 200.0
    intra_blip_pause_min_ms: float = 150.0
    intra_blip_fade_ms: float = 10.0
    # Frame analysis hop. 5 ms gives reasonable resolution for both
    # speech-boundary detection and blip identification.
    analysis_hop_ms: float = 5.0
    analysis_frame_ms: float = 20.0


DEFAULT_CONFIG = CleanupConfig()


def _frame_rms_db(audio_mono: np.ndarray, sr: int, cfg: CleanupConfig) -> tuple[np.ndarray, int]:
    """Compute frame-wise RMS in dBFS. Returns (rms_db_array, hop_samples)."""
    frame_size = max(1, int(cfg.analysis_frame_ms / 1000.0 * sr))
    hop = max(1, int(cfg.analysis_hop_ms / 1000.0 * sr))
    if audio_mono.size == 0:
        return np.zeros(0, dtype=np.float32), hop
    n_pad = (frame_size - (audio_mono.size - frame_size) % hop) % hop
    if n_pad > 0:
        padded = np.concatenate([audio_mono, np.zeros(n_pad, dtype=audio_mono.dtype)])
    else:
        padded = audio_mono
    n_frames = max(1, 1 + (padded.size - frame_size) // hop)
    rms = np.empty(n_frames, dtype=np.float32)
    for i in range(n_frames):
        seg = padded[i * hop : i * hop + frame_size]
        rms[i] = float(np.sqrt(np.mean(seg.astype(np.float64) ** 2)))
    rms_db = 20.0 * np.log10(rms + 1e-10)
    return rms_db, hop


def _find_segments(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return list of (start_idx, end_idx) inclusive ranges where mask is True."""
    if mask.size == 0:
        return []
    out: list[tuple[int, int]] = []
    in_run = False
    start = 0
    for i, v in enumerate(mask):
        if v and not in_run:
            start = i
            in_run = True
        elif not v and in_run:
            out.append((start, i - 1))
            in_run = False
    if in_run:
        out.append((start, mask.size - 1))
    return out


def _trim_edges(audio: np.ndarray, sr: int, cfg: CleanupConfig) -> np.ndarray:
    """Trim leading/trailing low-amplitude content with main-body detection.

    Naive "first/last frame above threshold" trimming has a failure
    mode: a brief glitch burst BEFORE or AFTER the real speech (with
    silence between it and the main body) gets included in the trim
    window, leaving the glitch in the output. This was the
    "tiny static at the very very end" failure mode.

    Improved logic:
      1. Find ALL contiguous speech segments.
      2. From the leading edge: find the FIRST segment that's >=
         ``main_segment_min_ms`` long, OR the first segment if all
         are shorter (degenerate case).
      3. From the trailing edge: same -- find the last segment >=
         the threshold length.
      4. If a short segment exists at either edge AND is separated
         from the main body by >= ``edge_glitch_gap_min_ms`` of
         silence, drop it (treat as glitch).
      5. Trim to [first_main_start - lead_pad, last_main_end + trail_pad].

    This way the trail_pad of 300 ms captures the slow decay of
    fricatives within the last word, while a separate trailing
    glitch is excluded.
    """
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    rms_db, hop = _frame_rms_db(mono, sr, cfg)
    above = rms_db > cfg.silence_threshold_db
    if not above.any():
        return audio

    speech_segments = _find_segments(above)
    main_min_frames = max(1, int(cfg.main_segment_min_ms / 1000.0 * sr / hop))
    edge_gap_min_frames = max(1, int(cfg.edge_glitch_gap_min_ms / 1000.0 * sr / hop))

    # Find first main segment (scanning from start)
    first_main_idx: Optional[int] = None
    for idx, (s, e) in enumerate(speech_segments):
        if (e - s + 1) >= main_min_frames:
            first_main_idx = idx
            break
    # Find last main segment (scanning from end)
    last_main_idx: Optional[int] = None
    for idx in range(len(speech_segments) - 1, -1, -1):
        s, e = speech_segments[idx]
        if (e - s + 1) >= main_min_frames:
            last_main_idx = idx
            break

    if first_main_idx is None or last_main_idx is None:
        # Degenerate case (all segments short). Fall back to first/last frame.
        first_main_start_frame = int(np.argmax(above))
        last_main_end_frame = int(above.size - 1 - np.argmax(above[::-1]))
    else:
        first_main_start_frame = speech_segments[first_main_idx][0]
        last_main_end_frame = speech_segments[last_main_idx][1]

        # If there's a leading short segment (idx < first_main_idx) close
        # to the main body (gap < edge_gap_min_frames), include it --
        # it's probably part of an early word, not a glitch.
        if first_main_idx is not None and first_main_idx > 0:
            prev_seg = speech_segments[first_main_idx - 1]
            gap_frames = first_main_start_frame - (prev_seg[1] + 1)
            if gap_frames < edge_gap_min_frames:
                first_main_start_frame = prev_seg[0]
        # Same on trailing side.
        if last_main_idx is not None and last_main_idx < len(speech_segments) - 1:
            next_seg = speech_segments[last_main_idx + 1]
            gap_frames = next_seg[0] - (last_main_end_frame + 1)
            if gap_frames < edge_gap_min_frames:
                last_main_end_frame = next_seg[1]

    lead_pad_samples = int(cfg.lead_pad_ms / 1000.0 * sr)
    trail_pad_samples = int(cfg.trail_pad_ms / 1000.0 * sr)
    start = max(0, first_main_start_frame * hop - lead_pad_samples)
    end = min(audio.shape[0], (last_main_end_frame + 1) * hop + trail_pad_samples)
    if start >= end:
        return audio
    trimmed = audio[start:end]
    fade_n = max(1, int(cfg.fade_ms / 1000.0 * sr))
    if trimmed.shape[0] > 2 * fade_n:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
        if trimmed.ndim > 1:
            ramp_in = ramp[:, None]
            ramp_out = ramp[::-1, None]
        else:
            ramp_in = ramp
            ramp_out = ramp[::-1]
        trimmed = trimmed.astype(np.float32, copy=True)
        trimmed[:fade_n] *= ramp_in
        trimmed[-fade_n:] *= ramp_out
    return trimmed


def _silence_intra_blips(
    audio: np.ndarray, sr: int, cfg: CleanupConfig
) -> tuple[np.ndarray, int]:
    """Detect + silence brief audio bursts surrounded by long pauses.

    Returns (cleaned_audio, n_blips_silenced). Targets the
    "hallucinated half-word between sentences" failure mode.
    """
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    rms_db, hop = _frame_rms_db(mono, sr, cfg)
    if rms_db.size == 0:
        return audio, 0
    is_speech = rms_db > cfg.silence_threshold_db
    speech_segments = _find_segments(is_speech)
    silence_segments = _find_segments(~is_speech)

    blip_max_frames = int(cfg.intra_blip_max_ms / 1000.0 * sr / hop)
    pause_min_frames = int(cfg.intra_blip_pause_min_ms / 1000.0 * sr / hop)

    # Build silence lookup: map each frame index to "is in silence segment of length L"
    # Cheaper: iterate speech segments, find adjacent silence on each side.

    blips: list[tuple[int, int]] = []  # (start_sample, end_sample)
    for seg_start, seg_end in speech_segments:
        seg_len = seg_end - seg_start + 1
        if seg_len > blip_max_frames:
            continue  # too long to be a blip
        # Find silence segment immediately before and immediately after
        before = next(
            (s for s in silence_segments if s[1] == seg_start - 1), None
        )
        after = next(
            (s for s in silence_segments if s[0] == seg_end + 1), None
        )
        if before is None or after is None:
            # At the edge of audio -- handled by edge trim, not here
            continue
        before_len = before[1] - before[0] + 1
        after_len = after[1] - after[0] + 1
        if before_len < pause_min_frames or after_len < pause_min_frames:
            continue
        # Confirmed blip. Compute sample range.
        start_s = max(0, seg_start * hop)
        end_s = min(audio.shape[0], (seg_end + 1) * hop)
        if end_s > start_s:
            blips.append((start_s, end_s))

    if not blips:
        return audio, 0

    out = audio.astype(np.float32, copy=True)
    fade_n = max(1, int(cfg.intra_blip_fade_ms / 1000.0 * sr))
    for start_s, end_s in blips:
        # Pre-fade: ramp the existing audio down before the blip
        pre_start = max(0, start_s - fade_n)
        ramp_down = np.linspace(1.0, 0.0, start_s - pre_start, dtype=np.float32)
        # Post-fade: ramp the existing audio up after the blip
        post_end = min(out.shape[0], end_s + fade_n)
        ramp_up = np.linspace(0.0, 1.0, post_end - end_s, dtype=np.float32)
        if out.ndim > 1:
            if start_s > pre_start:
                out[pre_start:start_s] *= ramp_down[:, None]
            out[start_s:end_s] = 0.0
            if post_end > end_s:
                out[end_s:post_end] *= ramp_up[:, None]
        else:
            if start_s > pre_start:
                out[pre_start:start_s] *= ramp_down
            out[start_s:end_s] = 0.0
            if post_end > end_s:
                out[end_s:post_end] *= ramp_up

    return out, len(blips)


def clean_xtts_output(
    path: Path | str,
    *,
    cfg: CleanupConfig = DEFAULT_CONFIG,
    dry_run: bool = False,
) -> dict:
    """Clean an XTTS output file in place.

    Returns a dict with metrics:
        {
            'before_seconds': float,
            'after_seconds': float,
            'edge_trim_seconds': float,
            'intra_blips_silenced': int,
        }

    On dry_run=True, computes and returns metrics but does not write.
    Best-effort: any exception returns an empty dict and leaves the file
    untouched (callers can detect failure by missing keys).
    """
    p = Path(path)
    try:
        audio, sr = sf.read(str(p))
    except Exception:
        return {}

    before_samples = audio.shape[0]
    before_seconds = before_samples / sr

    edge_trimmed = _trim_edges(audio, sr, cfg)
    deblipped, n_blips = _silence_intra_blips(edge_trimmed, sr, cfg)

    after_seconds = deblipped.shape[0] / sr
    edge_trim_seconds = before_seconds - (edge_trimmed.shape[0] / sr)

    metrics = {
        "before_seconds": before_seconds,
        "after_seconds": after_seconds,
        "edge_trim_seconds": edge_trim_seconds,
        "intra_blips_silenced": n_blips,
    }

    if dry_run:
        return metrics

    try:
        sf.write(str(p), deblipped, sr, subtype="PCM_16")
    except Exception:
        return {}
    return metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: audio_cleanup.py <dir_or_file> [--dry-run]")
        return 2
    target = Path(argv[1])
    dry_run = "--dry-run" in argv
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(target.glob("*.wav"))
    else:
        print(f"ERROR: not found: {target}")
        return 1
    if not files:
        print(f"no .wav files in {target}")
        return 0

    total_before = 0.0
    total_after = 0.0
    total_blips = 0
    n_processed = 0
    for f in files:
        m = clean_xtts_output(f, dry_run=dry_run)
        if not m:
            print(f"  FAILED  {f.name}")
            continue
        total_before += m["before_seconds"]
        total_after += m["after_seconds"]
        total_blips += m["intra_blips_silenced"]
        n_processed += 1
        if m["intra_blips_silenced"] > 0:
            print(
                f"  {f.name:<50} "
                f"trim={m['edge_trim_seconds']*1000:>5.0f}ms  "
                f"blips={m['intra_blips_silenced']}"
            )
    print(
        f"\n{n_processed} files processed. "
        f"total before={total_before:.1f}s, after={total_after:.1f}s. "
        f"intra-blips silenced: {total_blips}"
    )
    if dry_run:
        print("(dry-run; no files were modified)")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
