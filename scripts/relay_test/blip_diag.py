"""Diagnose the internal_dropout blips on long verbose lines: reproduce the
production synthesis, run the watcher, and measure the offending gap (position,
duration, and the dB floor inside it). Run from repo root with the train/main venv.
"""
import sys, warnings
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
import numpy as np
from kenning.tts import make_tts_engine
from kenning.audio.output_quality import analyze_clip

LINES = [
    "Killjoy solo-holds a site better than any other sentinel in the game. Own site.",
    "Jett, The moon orbits at an average distance of about 384,400 kilometers. That is the distance -- it is far smaller than that across.",
    "Time slows for anything moving near light speed, relative to a still observer -- special relativity. The faster you travel, the further your clock falls behind mine.",
    "Sage, I built nothing without intent, and you were included in this equation with intent. A variable that ignores its value corrupts everything downstream.",
]

def gaps(pcm, sr, frame_ms=5.0):
    x = pcm.astype(np.float32) / 32768.0 if pcm.dtype == np.int16 else pcm.astype(np.float32)
    fr = max(1, int(sr * frame_ms / 1000.0)); n = len(x) // fr
    b = x[:n*fr].reshape(n, fr)
    rms = np.sqrt(np.maximum(np.mean(b*b, axis=1), 1e-12))
    db = 20*np.log10(np.maximum(rms, 1e-9))
    speech = np.where(db > -28.0)[0]
    if len(speech) < 2: return []
    first, last = int(speech[0]), int(speech[-1])
    out = []; i = first
    while i < last:
        # a "gap" = run below -28 dB (the watcher's speech floor) inside speech
        if db[i] <= -28.0:
            j = i
            while j < last and db[j] <= -28.0: j += 1
            ms = (j - i) * frame_ms
            if ms >= 150:
                floor = float(db[i:j].min())
                out.append((round(i*frame_ms), round(ms), round(floor, 1)))
            i = j
        else:
            i += 1
    return out

_, tts = make_tts_engine()
tts.warmup()
print("max_pause_cap_ms =", getattr(tts, "max_pause_cap_ms", None))
for ln in LINES:
    pcm, sr = tts._synthesize(ln)
    rep = analyze_clip(pcm, sr, label=ln[:40])
    drop = [f for f in rep.findings if f.kind == "internal_dropout"]
    g = gaps(pcm, sr)
    print("\n%r  (%.1fs)" % (ln[:55], len(pcm)/sr))
    print("  dropouts:", [(round(f.position_ms), f.detail.split('(')[0].strip()) for f in drop] or "none")
    print("  gaps>=150ms (start_ms, len_ms, dB_floor):", g)
