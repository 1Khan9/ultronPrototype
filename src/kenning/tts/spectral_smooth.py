"""Spectral magnitude smoothing for Kokoro fine-tune output.

The partially-trained Kenning Kokoro checkpoint (Stage 1 complete +
Stage 2 epoch 0 only -- SLM joint adversarial training at epoch 3+
never ran) produces audible **pitch wobble / shakiness**. The
right long-term fix is more training; the short-term fix is a
lightweight DSP smoothing pass that masks frame-to-frame harmonic
micro-variations without smearing consonants.

Algorithm: STFT -> median-filter magnitudes across time (NOT
frequency) -> ISTFT with original phase. The production window
is 5 frames at ``hop=512``, ``sr=24 kHz`` (~107 ms of audio) --
the post-A/B sweet spot on the partial-fine-tune corpus (2026-05-22
user pick after comparing windows 3 / 5 / 7 / 9 on the 16-sentence
Kenning test set). 3 frames (~64 ms) leaves audible wobble; 7+
frames (~150 ms+) starts softening fricatives.

Origin: this is the runtime port of ``_spectral_smooth`` in
``kenningVoiceAudio/scripts/bulk_evaluate_finetune.py``. The
bulk-evaluate version was proven on the 1654-clip training corpus
(used to A/B different smoothing intensities); the algorithm here
is bit-for-bit identical, just wrapped for runtime use with the
fail-open semantics the orchestrator expects.

**Cost:** ~10 ms per second of audio on CPU (measured against the
16-sentence Kenning test corpus on 2026-05-22):

  ============  ==========
  Clip length  Latency
  ============  ==========
  1.7 s         ~15-16 ms
  3.5 s         ~16-32 ms
  5-6 s         ~31-46 ms
  10.4 s        ~63 ms
  ============  ==========

The Kokoro engine's round-8c producer-consumer pipeline hides
this cost on every clip after the first -- synth N+1 (including
the smoothing pass) runs while playback N is still draining. The
ack cache pre-renders the 16 cached phrases at cache-build time
so cached acks pay zero smoothing cost at runtime.

**Net runtime impact:**

- Ack cache hit (most turns): 0 ms
- First clip of cache-miss reply (~1-3 s typical): +15-30 ms TTFT
- Clips 2, 3, ... of multi-sentence reply: 0 ms (overlap)
"""
from __future__ import annotations

import numpy as np

__all__ = ["spectral_smooth", "trim_and_fade"]


def spectral_smooth(
    audio: np.ndarray,
    sr: int = 24000,
    *,
    n_fft: int = 2048,
    hop: int = 512,
    median_window_frames: int = 5,
) -> np.ndarray:
    """Smooth ``audio`` by median-filtering STFT magnitudes across time.

    Args:
        audio: 1-D float numpy array, expected normalized to [-1, 1].
            Other dtypes are upcast to float32. Multi-channel input
            is not supported -- pass mono.
        sr: sample rate in Hz. Default 24000 (Kokoro's native rate).
        n_fft: FFT size in samples. 2048 = ~85 ms window at 24 kHz.
        hop: STFT hop size in samples. 512 = 25 % overlap with the
            default ``n_fft``.
        median_window_frames: width of the magnitude median filter
            across time, in STFT frames. Default 5 frames at
            hop=512, sr=24 kHz covers ~107 ms -- the post-A/B sweet
            spot on the partial-fine-tune corpus (2026-05-22 user
            pick after comparing 3 / 5 / 7 / 9 on the 16-sentence
            Kenning test set). 3 (~64 ms) leaves audible wobble; 7+
            (~150 ms+) starts softening fricatives. Pass 1 to
            disable smoothing (no-op) without removing the call
            site. Values < 1 are clamped to 1.

    Returns:
        Float32 numpy array, same shape rank as input but possibly
        slightly different length at the tail due to STFT framing
        (always within ``n_fft`` samples of the input length).

    Raises:
        ImportError: scipy not installed. Callers using this in a
            hot path should wrap in try/except and fail open.

    Notes:
        - Phase is preserved exactly; only magnitudes are smoothed.
          This is what keeps consonants from blurring while killing
          pitch micro-wobble in vowels.
        - For very short clips (< n_fft samples = ~85 ms at 24 kHz)
          the function returns the input unchanged (a single STFT
          frame can't be median-filtered across time).
        - Implementation uses Python loops for STFT/ISTFT rather
          than scipy.signal.stft for byte-for-byte parity with the
          corpus-evaluation version. The cost dominates at clip
          length; the loop overhead is negligible. Vectorization
          via stride_tricks is an obvious optimization if a future
          session needs sub-10 ms smoothing.
    """
    from scipy.ndimage import median_filter

    audio_f32 = np.asarray(audio, dtype=np.float32)
    if median_window_frames < 1:
        median_window_frames = 1

    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (len(audio_f32) - n_fft) // hop
    if n_frames < 1:
        # Clip too short to STFT meaningfully -- pass through.
        return audio_f32

    frames = np.zeros((n_fft, n_frames), dtype=np.float32)
    for i in range(n_frames):
        frames[:, i] = audio_f32[i * hop: i * hop + n_fft] * window
    spec = np.fft.rfft(frames, axis=0)
    mag = np.abs(spec)
    phase = np.angle(spec)
    mag_smooth = median_filter(mag, size=(1, median_window_frames))
    spec_smooth = mag_smooth * np.exp(1j * phase)
    frames_out = np.fft.irfft(spec_smooth, n=n_fft, axis=0).astype(np.float32)

    out_len = (n_frames - 1) * hop + n_fft
    out = np.zeros(out_len, dtype=np.float32)
    weight = np.zeros(out_len, dtype=np.float32)
    for i in range(n_frames):
        out[i * hop: i * hop + n_fft] += frames_out[:, i] * window
        weight[i * hop: i * hop + n_fft] += window * window
    weight[weight < 1e-8] = 1.0
    return out / weight


def _strip_post_gap_blip(
    audio_f32: "np.ndarray",
    sr: int,
    *,
    content_db: float = -33.0,
    energy_after_db: float = -56.0,
    min_gap_ms: float = 90.0,
    frame_ms: float = 10.0,
    min_content_ms: float = 60.0,
) -> "np.ndarray":
    """Chop an isolated blip the fine-tune emits AFTER a long near-silence gap.

    Waveform-measured (2026-06-12): an isolated bump 200-700 ms past the last
    real speech, with a long stretch of near-total silence between. It comes in
    two flavours, both handled here:

    * a FAINT bump (~-41 dB) that sits below the -40 dB trim threshold, so the
      run-discard in ``trim_and_fade`` never sees it; and
    * a LOUD, FRAGMENTED bump (measured at ~-20 dB on "...cringe, Sage.") that
      the run-discard misses because it splits into two adjacent loud runs --
      the trailing-burst tiers only compare the last run to its IMMEDIATE
      predecessor (the other fragment, a 10 ms gap away), so the large gap to
      the speech body is hidden.

    The loud case is why ``last_content`` is the end of the last SUSTAINED
    content run (>= ``min_content_ms``), NOT merely the last frame above
    ``content_db``: a <= ~50 ms blip at -20 dB must not be mistaken for the
    speech body, or we would refuse to cut after it. A real final syllable is
    longer than that, so it is never reclassified as a blip.

    Told apart from the natural REVERB tail by the gap: reverb decays
    continuously (no >= ``min_gap_ms`` near-silence stretch with energy after
    it), so a reverb-only tail is never touched -- only a silence-then-energy
    pattern is cut, at the start of that silence.

    Cheap: one framed-RMS pass + a slice. No FFT, no per-sample work.
    """
    if len(audio_f32) == 0:
        return audio_f32
    fr = max(1, int(sr * frame_ms / 1000.0))
    n = len(audio_f32) // fr
    if n < 4:
        return audio_f32
    block = audio_f32[: n * fr].reshape(n, fr)
    rms = np.sqrt(np.maximum(np.mean(block * block, axis=1), 1e-12))
    content = 10.0 ** (content_db / 20.0)
    energy_after = 10.0 ** (energy_after_db / 20.0)
    above = rms > content
    if not above.any():
        return audio_f32
    # Speech (incl. strong reverb onset) ends at the last SUSTAINED content
    # run -- a run of >= min_content_ms frames above ``content``. A short,
    # isolated loud blip (the very thing we strip) is NOT sustained, so it is
    # not mistaken for the speech body. AFTER that point, a single
    # ``energy_after`` threshold splits the tail into quiet (gap, incl. the
    # decaying reverb's faint floor) and energy. A frame above the threshold
    # following a >= min_gap_ms quiet run is the post-gap blip -> chop at the
    # gap start. A reverb-only tail decays into the quiet floor with NO energy
    # after it, so it is never cut.
    min_content_frames = max(1, int(np.ceil(min_content_ms / frame_ms)))
    last_content = -1
    k = 0
    while k < n:
        if above[k]:
            j = k
            while j + 1 < n and above[j + 1]:
                j += 1
            if (j - k + 1) >= min_content_frames:
                last_content = j
            k = j + 1
        else:
            k += 1
    if last_content < 0:
        return audio_f32
    gap_frames = max(1, int(np.ceil(min_gap_ms / frame_ms)))
    gap_run = 0
    gap_start = None
    for k in range(last_content + 1, n):
        if rms[k] <= energy_after:
            if gap_run == 0:
                gap_start = k
            gap_run += 1
        else:
            if gap_run >= gap_frames and gap_start is not None:
                return audio_f32[: gap_start * fr].copy()
            gap_run = 0
            gap_start = None
    return audio_f32


def _compress_internal_dead_space(
    audio_f32: "np.ndarray",
    sr: int,
    *,
    speech_db: float = -40.0,
    silence_db: float = -76.0,
    keep_silence_ms: float = 120.0,
    min_silence_ms: float = 190.0,
    frame_ms: float = 10.0,
) -> "np.ndarray":
    """Shorten a run of PURE DIGITAL SILENCE between sentences -- speech-safe.

    Kokoro returns a multi-sentence line as one concatenated clip; most of its
    internal sentence/clause pauses are natural (~290-550 ms, floor ~-62..-73
    dB room tone) and must be KEPT -- they are the intentional beats (sentence
    boundaries, commas, pauses for effect). Occasionally the decoder emits a
    LONGER pause whose CORE is pure digital silence (waveform-measured 300-500
    ms reaching -82..-97 dB between sentences) -- dead space, not an intentional
    beat.

    GUARANTEE -- this never alters the spoken sentence in ANY way: it removes
    ONLY frames at or below ``silence_db`` (-76 dB ~= 0.016 % of full scale),
    which is far below the voice's natural room-tone pause floor (~-62..-73 dB)
    and below anything audible -- no speech sample, no consonant tail, no reverb
    is ever this quiet. So only the inaudible digital-silence CORE of a dead
    pause is shortened; the pause's audible decay-in and ramp-out (which live
    ABOVE silence_db) are left byte-for-byte intact, as is every speech frame.

    A contiguous pure-silence run longer than ``min_silence_ms`` (strictly
    between the first and last speech frame -- leading/trailing silence is the
    boundary trim's job) is shrunk to ``keep_silence_ms`` by dropping its centre.
    A natural pause (room-tone floor, no sub-``silence_db`` core) has no such run
    and is never touched. The join is silence-to-silence, so no click is
    introduced. Cheap: one framed-RMS pass + a boolean frame mask.
    """
    if len(audio_f32) == 0:
        return audio_f32
    fr = max(1, int(sr * frame_ms / 1000.0))
    n = len(audio_f32) // fr
    if n < 4:
        return audio_f32
    block = audio_f32[: n * fr].reshape(n, fr)
    rms = np.sqrt(np.maximum(np.mean(block * block, axis=1), 1e-12))
    speech_lin = 10.0 ** (speech_db / 20.0)
    silence_lin = 10.0 ** (silence_db / 20.0)
    speech = np.where(rms > speech_lin)[0]
    if len(speech) < 2:
        return audio_f32
    first, last = int(speech[0]), int(speech[-1])
    keep_frames = max(1, int(round(keep_silence_ms / frame_ms)))
    min_frames = max(keep_frames + 2, int(round(min_silence_ms / frame_ms)))
    keep_mask = np.ones(n, dtype=bool)
    touched = False
    k = first + 1
    while k < last:
        # Only PURE-silence frames are even considered for removal.
        if rms[k] <= silence_lin:
            r = k
            while r < last and rms[r] <= silence_lin:
                r += 1
            run_len = r - k
            if run_len > min_frames:
                drop = run_len - keep_frames
                start = k + (run_len - drop) // 2
                keep_mask[start: start + drop] = False
                touched = True
            k = r
        else:
            k += 1
    if not touched:
        return audio_f32
    kept = block[keep_mask].reshape(-1)
    tail = audio_f32[n * fr:]
    return np.concatenate([kept, tail]) if len(tail) else kept


def expand_internal_pauses(
    audio: "np.ndarray",
    sr: int,
    *,
    scale: float = 1.6,
    min_pause_ms: float = 80.0,
    max_pause_ms: float = 500.0,
    min_keep_ms: float = 110.0,
    threshold_db: float = -30.0,
    speech_db: float = -28.0,
    frame_ms: float = 5.0,
) -> "np.ndarray":
    """Scale the natural pauses at punctuation -- prosody-preserving, blip-free.

    The line is synthesized as ONE clean clip (so there is exactly one boundary
    trim and no per-fragment burst). This pass then resizes only the existing
    INTERNAL low-energy dips -- a comma leaves ~180 ms at ~-45 dB, a sentence
    end a deeper gap -- by inserting OR removing pure silence at the MIDDLE of
    each dip. The spoken samples and Kokoro's intonation are left byte-for-byte
    intact; edits happen between the dip's own ramp-down and ramp-up, so neither
    join is a speech edge and no click/burst is created.

    ``scale`` > 1 lengthens each pause (capped at ``max_pause_ms``); ``scale`` < 1
    shortens it UNIFORMLY (never below ``min_keep_ms`` -- so a pause is trimmed,
    never erased). This is the controlled replacement for the old dead-space
    compressor, which cut pauses arbitrarily. Only dips longer than
    ``min_pause_ms`` (real punctuation beats) are touched; word-internal gaps and
    the clip's leading/trailing edges never are. ``scale == 1`` is a no-op.
    dtype (int16/float32) preserved.
    """
    if audio is None or len(audio) == 0:
        return audio
    # scale == 1.0 still runs IF a finite cap is set (to clamp over-long pauses
    # under the dead-air threshold); otherwise it is a no-op.
    if scale == 1.0 and (max_pause_ms is None or max_pause_ms <= 0):
        return audio
    is_int16 = audio.dtype == np.int16
    f = (audio.astype(np.float32) / 32768.0) if is_int16 else audio.astype(np.float32)
    fr = max(1, int(sr * frame_ms / 1000.0))
    n = len(f) // fr
    if n < 4:
        return audio
    block = f[: n * fr].reshape(n, fr)
    rms = np.sqrt(np.maximum(np.mean(block * block, axis=1), 1e-12))
    db = 20.0 * np.log10(np.maximum(rms, 1e-9))
    speech = np.where(db > speech_db)[0]
    if len(speech) < 2:
        return audio
    first, last = int(speech[0]), int(speech[-1])
    min_frames = max(1, int(round(min_pause_ms / frame_ms)))
    keep_frames = max(1, int(round(min_keep_ms / frame_ms)))
    max_frames = int(round(max_pause_ms / frame_ms)) if max_pause_ms > 0 else None
    parts: list[np.ndarray] = []
    changed = False
    i = 0
    while i < n:
        if first < i < last and db[i] < threshold_db:
            j = i
            while j < last and db[j] < threshold_db:
                j += 1
            run = j - i
            if run >= min_frames:
                target = int(round(run * scale))
                if max_frames is not None:
                    target = min(target, max_frames)
                target = max(target, keep_frames)
                half = run // 2
                if target > run:  # lengthen: inject silence in the middle
                    parts.append(block[i:i + half].reshape(-1))
                    parts.append(np.zeros((target - run) * fr, dtype=np.float32))
                    parts.append(block[i + half:j].reshape(-1))
                    changed = True
                elif target < run:  # shorten: drop the centre of the pure pause
                    drop = run - target
                    parts.append(block[i:i + half - drop // 2].reshape(-1))
                    parts.append(block[i + half - drop // 2 + drop:j].reshape(-1))
                    changed = True
                else:
                    parts.append(block[i:j].reshape(-1))
            else:
                parts.append(block[i:j].reshape(-1))
            i = j
        else:
            parts.append(block[i])
            i += 1
    if not changed:
        return audio
    tail = f[n * fr:]
    if len(tail):
        parts.append(tail)
    out = np.concatenate(parts)
    if is_int16:
        np.clip(out, -1.0, 1.0, out=out)
        return (out * 32767.0).astype(np.int16)
    return out


def trim_and_fade(
    audio: np.ndarray,
    sr: int = 24000,
    *,
    threshold_db: float = -40.0,
    frame_ms: float = 10.0,
    fade_in_ms: float = 25.0,
    fade_out_ms: float = 45.0,
    pad_ms: float = 5.0,
    hard_silence_pad_ms: float = 8.0,
    tail_aggressive_trim_ms: float = 25.0,
    tail_floor_db: float = -58.0,
    compress_dead_space: bool = False,
) -> np.ndarray:
    """Trim boundary noise, apply fades, prepend/append hard silence.

    Designed for the partial Kokoro fine-tune: the undertrained model
    (Stage 1 + Stage 2 epoch 0 only; no SLM joint) generates noise
    bursts before speech starts and after speech ends -- ranging from
    short clicks (<5 ms) to medium bursts (up to ~40 ms). This applies
    three layers of defense:

    1. **RMS trim** removes low-level boundary noise (below threshold).
    2. **Cosine fades** attenuate medium-level artifacts within the
       fade-in / fade-out region (raised-cosine curve quieter early
       than a linear ramp).
    3. **Hard silence pad** guarantees the first/last few samples are
       byte-exact zeros, eliminating any DC-step or sub-frame artifact
       that survives the trim+fade.

    Args:
        audio: 1-D float numpy array, expected normalized to [-1, 1].
            Other dtypes are upcast to float32.
        sr: Sample rate in Hz. Default 24000 (Kokoro native).
        threshold_db: RMS frames below this level (dB relative to
            full scale) are treated as silence/noise and may be
            trimmed from the boundaries. Default -40 dB (1% of full
            scale).
        frame_ms: Frame size in ms for RMS energy analysis. Default
            10 ms = 240 samples at 24 kHz.
        fade_in_ms: Duration of the raised-cosine fade-in applied
            after leading-noise trim. Default 25 ms. Long enough to
            attenuate burst artifacts up to ~20 ms in length.
        fade_out_ms: Duration of the raised-cosine fade-out applied
            after trailing-noise trim. Default 30 ms. Slightly longer
            than fade-in because natural speech offset is gentler and
            the partial fine-tune tends to leave slightly longer tail
            artifacts than leading ones.
        pad_ms: Silence buffer to keep around the detected speech
            region before trimming. Default 5 ms. Smaller than before
            since the longer fades absorb consonant onsets natively.
        hard_silence_pad_ms: Pure-silence buffer prepended and
            appended to the trimmed+faded audio. Default 4 ms = 96
            samples at 24 kHz. Guarantees the very first and very
            last samples played are byte-exact zeros so stream
            transitions are clean regardless of any residual artifact
            inside the audio body. Pass 0 to disable padding.

    Returns:
        Trimmed, faded, padded float32 array. If no speech region is
        found (all silence/noise) or the clip is too short for
        analysis, returns the input unchanged as float32.
    """
    audio_f32 = np.asarray(audio, dtype=np.float32)
    frame_samples = max(1, int(sr * frame_ms / 1000))
    n_frames = len(audio_f32) // frame_samples
    if n_frames < 2:
        return audio_f32

    rms_linear = 10.0 ** (threshold_db / 20.0)
    rms = np.array([
        np.sqrt(np.mean(audio_f32[i * frame_samples:(i + 1) * frame_samples] ** 2))
        for i in range(n_frames)
    ])

    speech_frames = np.where(rms > rms_linear)[0]
    if len(speech_frames) == 0:
        return audio_f32

    # 2026-06-11 live fix (user-audible "blip after the sentence"):
    # the partial fine-tune emits an isolated noise burst well AFTER
    # speech ends (watcher-measured live: a ~70 ms burst ~440 ms past
    # the body). A loud burst counts as a "speech frame" above the
    # threshold, so ``speech_frames[-1]`` used to point at the BURST --
    # the trim kept the dead air + blip and faded the blip's tail
    # instead of the speech's. Group loud frames into runs and discard
    # edge runs that are SHORT (<= burst_max) and ISOLATED from the
    # body by a large gap (>= burst_gap): real words are longer than
    # 120 ms, and intra-sentence pauses at a clip edge rarely exceed
    # 200 ms of sub-threshold silence, so speech is never clipped.
    burst_max_frames = max(1, int(np.ceil(120.0 / frame_ms)))
    burst_gap_frames = max(1, int(np.ceil(200.0 / frame_ms)))
    runs: list[tuple[int, int]] = []
    run_start = prev = int(speech_frames[0])
    for f in speech_frames[1:]:
        f = int(f)
        if f == prev + 1:
            prev = f
            continue
        runs.append((run_start, prev))
        run_start = prev = f
    runs.append((run_start, prev))
    while len(runs) > 1:
        s, e = runs[-1]
        gap = s - runs[-2][1] - 1
        if (e - s + 1) <= burst_max_frames and gap >= burst_gap_frames:
            runs.pop()                      # trailing isolated burst
        else:
            break
    # 2026-06-12: a second, tighter tier for the VERY SHORT tail blips the
    # fine-tune emits right after speech (watcher-measured live: 20-50 ms
    # bursts only ~60-90 ms past the body) that the 200 ms-gap rule above
    # misses. A run this short (<= ~55 ms) is shorter than any real spoken
    # syllable, so an isolated one at the very tail is a decoder blip, not a
    # word -- discard it even on a smaller (>= 40 ms) gap. A substantial
    # speech run (>= 90 ms) must remain so a clip is never emptied and a
    # genuine short final callout ('B', 'A', 'mid' -- all >> 55 ms when
    # spoken) is never clipped.
    # Thresholds chosen to be UNAMBIGUOUSLY safe against word-final stop
    # releases (the 't' in 'site/plant/default', 'd' in 'mid'): a stop
    # release follows its closure by <= ~50-60 ms, so a >= 70 ms gap means
    # the short run is NOT a stop release but a detached decoder blip.
    short_burst_max = max(1, int(np.ceil(45.0 / frame_ms)))
    short_burst_gap = max(1, int(np.ceil(70.0 / frame_ms)))
    speech_run_min = max(1, int(np.ceil(100.0 / frame_ms)))
    while len(runs) > 1:
        s, e = runs[-1]
        prev_s, prev_e = runs[-2]
        gap = s - prev_e - 1
        if ((e - s + 1) <= short_burst_max and gap >= short_burst_gap
                and (prev_e - prev_s + 1) >= speech_run_min):
            runs.pop()                      # short trailing blip
        else:
            break
    while len(runs) > 1:
        s, e = runs[0]
        gap = runs[1][0] - e - 1
        if (e - s + 1) <= burst_max_frames and gap >= burst_gap_frames:
            runs.pop(0)                     # leading isolated burst
        else:
            break

    pad_frames = max(0, int(np.ceil(pad_ms / frame_ms)))
    first_frame = max(0, runs[0][0] - pad_frames)
    last_frame = min(n_frames - 1, runs[-1][1] + pad_frames)

    # Reverb-tail preservation. The speech threshold (-40 dB) sits HIGH in this
    # voice's reverb decay, so stopping at the last >-40 dB frame lops off the
    # audible reverb (waveform-measured: the tail decays -40 -> -58 over
    # ~100-200 ms before going inaudible). Walk forward through the CONTINUOUS
    # decay, keeping frames down to ``tail_floor_db``, and stop once the signal
    # has been sustainedly below that floor -- which lands BEFORE any detached
    # trailing decoder blip (that blip sits past a real silence gap and is
    # removed by _strip_post_gap_blip below). Only EXTENDS the kept region, so a
    # voice without a reverb tail (decay already below -58 within a frame) is a
    # no-op. tail_floor_db >= threshold_db disables it.
    if tail_floor_db < threshold_db:
        tail_floor_lin = 10.0 ** (tail_floor_db / 20.0)
        sil_hold = max(1, int(np.ceil(60.0 / frame_ms)))
        ext = int(runs[-1][1])
        run_sil = 0
        kf = ext + 1
        while kf < n_frames:
            if rms[kf] >= tail_floor_lin:
                ext = kf
                run_sil = 0
            else:
                run_sil += 1
                if run_sil >= sil_hold:
                    break
            kf += 1
        last_frame = min(n_frames - 1, max(last_frame, ext + pad_frames))

    start = first_frame * frame_samples
    end = min(len(audio_f32), (last_frame + 1) * frame_samples)
    trimmed = audio_f32[start:end].copy()

    if len(trimmed) == 0:
        return audio_f32

    # Chop the sub-threshold post-gap blip the run-discard above can't see
    # (it lives below the -40 dB speech threshold). Reverb-safe: only cuts a
    # silence-then-faint-energy pattern, never a continuous decay.
    trimmed = _strip_post_gap_blip(trimmed, sr)
    if len(trimmed) == 0:
        return audio_f32

    # Internal dead-space compression is OFF by default (2026-06-12): this clean
    # voice renders its real sentence pauses as PURE digital silence (-91 dB),
    # so the compressor was shortening MEANINGFUL pauses (measured: a 250 ms
    # sentence pause cut to 120 ms). Pause length is now controlled, uniformly
    # and predictably, by ``expand_internal_pauses`` downstream instead.
    if compress_dead_space:
        trimmed = _compress_internal_dead_space(trimmed, sr)
        if len(trimmed) == 0:
            return audio_f32

    # Raised-cosine fade is quieter in the first ~30% of the ramp
    # than a linear fade -- better at hiding burst artifacts that
    # sit close to the boundary.
    fi = min(int(sr * fade_in_ms / 1000), len(trimmed) // 4)
    if fi > 1:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, fi, dtype=np.float32))
        trimmed[:fi] *= ramp

    fo = min(int(sr * fade_out_ms / 1000), len(trimmed) // 4)
    if fo > 1:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(np.pi, 0.0, fo, dtype=np.float32))
        trimmed[-fo:] *= ramp

    # 2026-05-22 -- aggressive last-N-samples mute. The partial fine-
    # tune produces an audible "blip" right at the very end of clips
    # (after the fade-out completes the audio decays but a residual
    # decoder artifact is still above zero). Force the LAST N samples
    # to byte-exact zero so the speaker sees clean silence regardless
    # of any sample-level artifact the cosine fade left in. Cost: at
    # most 25 ms of clipped speech tail, which on natural speech is
    # already in the breath-decay zone.
    if tail_aggressive_trim_ms > 0:
        ta = min(int(sr * tail_aggressive_trim_ms / 1000), len(trimmed) // 4)
        if ta > 0:
            trimmed[-ta:] = 0.0

    if hard_silence_pad_ms > 0:
        pad_samples = max(1, int(sr * hard_silence_pad_ms / 1000))
        silence = np.zeros(pad_samples, dtype=np.float32)
        trimmed = np.concatenate([silence, trimmed, silence])

    return trimmed
