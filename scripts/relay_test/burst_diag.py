r"""Diagnose why the 'cringe, Sage' trailing burst survives trim_and_fade.

Synthesizes the clip RAW (trim off) and TRIMMED (default), prints the framed
dB envelope of the tail, and reconstructs the loud-run grouping the trim does,
so we can see exactly which run survives and why.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))

LINE = "You're absolutely cringe, Sage."
FRAME_MS = 10.0


def fdb(pcm, sr):
    x = np.asarray(pcm, dtype=np.float64)
    fl = max(1, int(sr * FRAME_MS / 1000))
    n = len(x) // fl
    fr = x[: n * fl].reshape(n, fl)
    rms = np.sqrt(np.mean(fr * fr, axis=1)) + 1e-12
    # pcm is float [-1,1] from raw path OR int16 from _synthesize; normalize
    scale = 1.0 if np.max(np.abs(x)) <= 1.5 else 32768.0
    return 20.0 * np.log10(rms / scale)


def runs_above(db, thr):
    loud = np.where(db > thr)[0]
    if len(loud) == 0:
        return []
    runs = []
    s = p = int(loud[0])
    for f in loud[1:]:
        f = int(f)
        if f == p + 1:
            p = f; continue
        runs.append((s, p)); s = p = f
    runs.append((s, p))
    return runs


from kenning.tts.kokoro_engine import KokoroSpeech

raw_tts = KokoroSpeech(voice="kenning", apply_trim_fade=False, apply_spectral_smooth=True)
raw_tts.warmup()
trim_tts = KokoroSpeech(voice="kenning")          # defaults: trim on
trim_tts.warmup()

for tag, eng in [("RAW(no-trim)", raw_tts), ("TRIMMED(default)", trim_tts)]:
    pcm, sr = eng._synthesize(LINE)
    pcm = np.asarray(pcm).reshape(-1)
    db = fdb(pcm, sr)
    dur = len(pcm) / sr
    runs = runs_above(db, -40.0)
    print(f"\n### {tag}: dur={dur:.2f}s frames={len(db)}  loud-runs(> -40dB):")
    for (s, e) in runs:
        print(f"    frames[{s:>4}..{e:>4}]  {s*10:>5}-{e*10:>5}ms  "
              f"len={e-s+1:>3}f  peakdB={db[s:e+1].max():.1f}")
    if len(runs) >= 2:
        s, e = runs[-1]; ps, pe = runs[-2]
        gap = s - pe - 1
        print(f"    >> last run: len={e-s+1}f gap_from_prev={gap}f "
              f"({gap*10}ms)  [tier1 needs len<=12 & gap>=20]")
    # last 60 frames dB dump
    tail = db[-60:]
    print("    tail dB (last 600ms, 10ms/val):")
    print("     " + " ".join(f"{int(round(v)):>3}" for v in tail))
