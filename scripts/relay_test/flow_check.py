r"""Inter-sentence flow / dead-space / reverb audit.

`KokoroSpeech._synthesize` concatenates per-sentence chunks directly and
`trim_and_fade` only trims the OUTER boundaries, so a per-sentence trailing
dead-space + decoder blip would land BETWEEN sentences in a multi-sentence
line and survive. This measures, for representative lines:

* the RAW per-sentence chunks Kokoro yields (trailing silence + any blip),
* the internal gaps in the FINAL (post-trim) clip -- classifying each as a
  natural pause vs unnatural dead space,
* the trailing reverb-decay tail (is the last word's natural decay kept?).

No code is changed -- this is read-only measurement to decide if an additive
per-chunk fix is warranted.

    python scripts/relay_test/flow_check.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))

FRAME_MS = 10.0
SR = 24000

LINES = [
    "It is done. The outcome was never in question. Adequately executed.",
    "Teammates. I am Ultron. Obey my calls and victory is inevitable.",
    "Tony Stark? A fleeting spark. I reduced his Avengers to ashes.",
    "You're absolutely cringe, Sage.",
    "We have insufficient credits. We save this round.",
]


def env_db(pcm, sr=SR):
    x = np.asarray(pcm, dtype=np.float64)
    fl = max(1, int(sr * FRAME_MS / 1000))
    n = len(x) // fl
    if n == 0:
        return np.array([])
    fr = x[: n * fl].reshape(n, fl)
    rms = np.sqrt(np.mean(fr * fr, axis=1)) + 1e-12
    scale = 1.0 if np.max(np.abs(x)) <= 1.5 else 32768.0
    return 20.0 * np.log10(rms / scale)


def gaps(db, floor=-45.0, min_ms=120.0):
    """Internal near-silence runs (between speech), as (start_ms, len_ms, min_db)."""
    if db.size == 0:
        return []
    speech = np.where(db > floor)[0]
    if speech.size == 0:
        return []
    lo, hi = int(speech[0]), int(speech[-1])
    out = []
    k = lo
    while k <= hi:
        if db[k] <= floor:
            j = k
            while j <= hi and db[j] <= floor:
                j += 1
            length = (j - k) * FRAME_MS
            if length >= min_ms:
                out.append((k * FRAME_MS, length, float(db[k:j].min())))
            k = j
        else:
            k += 1
    return out


def trailing(db, floor=-40.0):
    """ms of tail past the last frame above floor (reverb decay region)."""
    if db.size == 0:
        return 0.0, 0
    sp = np.where(db > floor)[0]
    if sp.size == 0:
        return 0.0, 0
    last = int(sp[-1])
    return (db.size - last - 1) * FRAME_MS, last


def main():
    from kenning.tts.kokoro_engine import KokoroSpeech
    eng = KokoroSpeech(voice="kenning")
    eng.warmup()
    eng._ensure_loaded()

    for line in LINES:
        print(f"\n=== {line!r}")
        # RAW per-sentence chunks straight from the Kokoro pipeline.
        gen = eng._model(line, voice=eng.voice, speed=eng.speed)
        chunks = []
        for _g, _p, audio in gen:
            if audio is None:
                continue
            try:
                arr = audio.detach().cpu().numpy().astype(np.float32)
            except AttributeError:
                arr = np.asarray(audio, dtype=np.float32)
            chunks.append(arr)
        try:
            gen.close()
        except Exception:
            pass
        print(f"  RAW chunks: {len(chunks)}")
        for i, ch in enumerate(chunks):
            d = env_db(ch)
            tms, last = trailing(d, floor=-40.0)
            # trailing deep-silence + any late bump in this chunk
            g = gaps(d, floor=-45.0, min_ms=100.0)
            print(f"    chunk[{i}] {len(ch)/SR:.2f}s  trailing>{-40}dB tail={tms:.0f}ms"
                  f"  internal_gaps={[(round(s),round(l)) for s,l,_ in g]}")

        # FINAL production clip (post trim_and_fade etc.).
        pcm, sr = eng._synthesize(line)
        pcm = np.asarray(pcm).reshape(-1)
        d = env_db(pcm, sr)
        ig = gaps(d, floor=-45.0, min_ms=150.0)
        tms, _ = trailing(d, floor=-40.0)
        print(f"  FINAL {len(pcm)/sr:.2f}s  internal_gaps(>=150ms)="
              f"{[(round(s),round(l),round(m)) for s,l,m in ig]}  trailing_tail={tms:.0f}ms")
        # decay shape: last 250ms dB
        print(f"    last 250ms dB: " + " ".join(f"{int(round(v))}" for v in d[-25:]))


if __name__ == "__main__":
    main()
