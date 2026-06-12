"""Validate a trained openWakeWord model against synthesized clips.

Scores every WAV in a positives dir and a negatives dir through the
RUNTIME inference path (openwakeword.model.Model.predict over 1280-sample
frames -- the same frame size WakeWordDetector feeds) and reports
detection / false-accept rates at the production threshold.

Usage (from the repo root, runtime venv):
    .venv\\Scripts\\python.exe training\\validate_wake_model.py \
        --model models/openwakeword/kenning.onnx \
        --positives training/my_custom_model/kenning/positive_test \
        --negatives training/my_custom_model/kenning/negative_test \
        --threshold 0.5

Optional --extra-negatives dirs (e.g. clips of the OLD wake word) are
scored separately so cross-name rejection is visible at a glance.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import wave

import numpy as np

FRAME = 1280  # 80 ms @ 16 kHz -- matches WakeWordDetector's chunking


def _read_wav_16k_mono(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        channels = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit PCM, got width={width}")
    pcm = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)
    if rate != 16000:
        # Cheap linear resample; synthesized training clips are 16 kHz
        # already, so this is a guard rather than a hot path.
        n_out = int(len(pcm) * 16000 / rate)
        pcm = np.interp(
            np.linspace(0, len(pcm) - 1, n_out),
            np.arange(len(pcm)),
            pcm.astype(np.float32),
        ).astype(np.int16)
    return pcm


def score_clip(model, pcm: np.ndarray) -> float:
    # Trailing silence so a phrase ending at the clip boundary still
    # passes fully through the model's feature window (live audio always
    # has a post-phrase tail; without this, recall reads biased-low).
    pcm = np.concatenate([pcm, np.zeros(FRAME * 12, dtype=np.int16)])
    model.reset()
    best = 0.0
    for i in range(0, len(pcm) - FRAME + 1, FRAME):
        scores = model.predict(pcm[i : i + FRAME])
        frame_best = max(scores.values())
        if frame_best > best:
            best = float(frame_best)
    return best


def score_dir(model, path: str, limit: int | None = None) -> np.ndarray:
    wavs = sorted(glob.glob(os.path.join(path, "*.wav")))
    if limit:
        wavs = wavs[:limit]
    if not wavs:
        raise SystemExit(f"no WAVs found under {path}")
    out = np.empty(len(wavs), dtype=np.float64)
    for i, wav in enumerate(wavs):
        out[i] = score_clip(model, _read_wav_16k_mono(wav))
        if (i + 1) % 200 == 0:
            print(f"  ... {i + 1}/{len(wavs)}", flush=True)
    return out


def summarize(name: str, scores: np.ndarray, threshold: float, positive: bool) -> None:
    hits = scores >= threshold
    rate = hits.mean()
    label = "detected" if positive else "FALSE-ACCEPTED"
    print(
        f"{name}: n={len(scores)}  {label}@{threshold}: {rate:.1%}  "
        f"mean={scores.mean():.3f}  p50={np.percentile(scores, 50):.3f}  "
        f"p90={np.percentile(scores, 90):.3f}  max={scores.max():.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--positives", required=True)
    ap.add_argument("--negatives", required=True)
    ap.add_argument("--extra-negatives", nargs="*", default=[])
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    from openwakeword.model import Model

    model = Model(wakeword_models=[args.model], inference_framework="onnx")

    print(f"model: {args.model}")
    print("scoring positives ...", flush=True)
    pos = score_dir(model, args.positives, args.limit)
    print("scoring negatives ...", flush=True)
    neg = score_dir(model, args.negatives, args.limit)

    print()
    summarize("positives", pos, args.threshold, positive=True)
    summarize("negatives", neg, args.threshold, positive=False)

    for extra in args.extra_negatives:
        print(f"scoring extra negatives: {extra} ...", flush=True)
        scores = score_dir(model, extra, args.limit)
        summarize(os.path.basename(extra.rstrip("/\\")), scores,
                  args.threshold, positive=False)

    # Hard gate: recall must beat 90% on raw synthesized positives and
    # false-accepts stay under 8% on the ADVERSARIAL negative set (these
    # are deliberately-confusable phrases, so the bar is looser than a
    # generic-speech FAR; real-world FP pressure is tracked by the
    # training harness's false-positives-per-hour metric instead).
    recall = (pos >= args.threshold).mean()
    far = (neg >= args.threshold).mean()
    ok = recall >= 0.90 and far <= 0.08
    print(f"\nverdict: recall={recall:.1%} far={far:.1%} -> "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
