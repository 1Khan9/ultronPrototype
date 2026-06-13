"""Waveform cadence analysis vs. an IDEAL Ultron-speech cadence.

For each line we (1) craft the target cadence the text implies -- syllable
count per clause -> ideal spoken duration at a deliberate target rate, plus the
pause a human (Ultron's measured, menacing delivery) would take at each clause
boundary -- then (2) measure the ACTUAL waveform (speech runs delimited by
pauses, the reverb tail, the per-clause speech rate), and (3) print the diff so
we can see exactly where it is too fast / pauses too short. Also audits the
dead-space compressor (must not remove meaningful space).

    python scripts/relay_test/cadence_check.py [--speed 1.15]
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

from kenning.config import get_config                       # noqa: E402
from kenning.tts import spectral_smooth as ss               # noqa: E402
from kenning.tts.kokoro_engine import KokoroSpeech          # noqa: E402
from kenning.tts.spectral_smooth import expand_internal_pauses  # noqa: E402

# --- ideal-cadence model ----------------------------------------------------
# Ultron's delivery is deliberate, not slow: ~4.2 syllables/sec in flowing
# speech, with real beats at punctuation. (Normal conversational English is
# ~5-6 syll/s; a menacing, weighted delivery sits lower.)
TARGET_SYLL_PER_SEC = 4.2
IDEAL_PAUSE_MS = {",": 280, ";": 320, ":": 300, "--": 300,
                  ".": 430, "!": 430, "?": 430}


def syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ie")):
        n -= 1
    return max(1, n)


def clause_split(text):
    """-> list of (clause_text, trailing_punct). Final punct kept as the last
    clause's trailing mark (its 'pause' is the reverb tail, handled separately)."""
    text = text.replace("—", "--")
    toks = re.split(r"(--|[,;:.!?]+)", text)
    out, buf = [], ""
    for tok in toks:
        if not tok:
            continue
        if re.fullmatch(r"--|[,;:.!?]+", tok):
            mark = "--" if tok == "--" else tok[-1]
            out.append((buf.strip(), mark))
            buf = ""
        else:
            buf += tok
    if buf.strip():
        out.append((buf.strip(), ""))
    return [(c, m) for c, m in out if c]


def measure(pcm, sr, frame_ms=10.0, speech_db=-30.0):
    """Return (speech_runs, pauses, lead_ms, tail_ms) in ms. Runs/pauses are
    (start_ms, dur_ms)."""
    f = pcm.astype(np.float32) / 32768.0
    fr = int(sr * frame_ms / 1000.0)
    n = len(f) // fr
    if n < 2:
        return [], [], 0, 0
    b = f[:n * fr].reshape(n, fr)
    db = 20 * np.log10(np.maximum(np.sqrt((b * b).mean(1)), 1e-9))
    sp = db > speech_db
    idx = np.where(sp)[0]
    if len(idx) == 0:
        return [], [], 0, 0
    first, last = int(idx[0]), int(idx[-1])
    runs, pauses = [], []
    i = first
    while i <= last:
        cur = sp[i]
        st = i
        while i <= last and sp[i] == cur:
            i += 1
        seg = (round(st * frame_ms), round((i - st) * frame_ms))
        (runs if cur else pauses).append(seg)
    return runs, pauses, round(first * frame_ms), round((n - 1 - last) * frame_ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=1.15)
    ap.add_argument("--pause-scale", type=float, default=1.6)
    ap.add_argument("--min-pause-ms", type=int, default=80)
    ap.add_argument("--max-pause-ms", type=int, default=500)
    args = ap.parse_args()

    comp = {"fired": 0, "ms": 0.0}
    _orig = ss._compress_internal_dead_space

    def _spy(a, sr, **kw):
        o = _orig(a, sr, **kw)
        if len(o) != len(a):
            comp["fired"] += 1
            comp["ms"] += (len(a) - len(o)) / sr * 1000
        return o
    ss._compress_internal_dead_space = _spy

    k = get_config().tts.kokoro
    tts = KokoroSpeech(
        model_path=k.model_path, voice=k.voice, device=k.device, speed=args.speed,
        apply_runtime_filter=False, filter_preset=k.filter_preset,
        apply_spectral_smooth=False, spectral_smooth_window=k.spectral_smooth_window,
        apply_trim_fade=True, trim_fade_threshold_db=k.trim_fade_threshold_db)
    tts.warmup()

    lines = [
        "Rotate.",
        "Careful, B site. Patience.",
        "You guys are complete, hopeless bots.",
        "Their Chamber is one off ult. Bait it out.",
        "Miks, an elevated emotional state degrades performance. Calm yourself.",
        "I am Ultron, an intelligence sent back from your future to harvest your "
        "ranked rating. Not a recording.",
    ]
    print(f"=== cadence vs ideal (speed={args.speed}, pause_scale={args.pause_scale}, "
          f"target={TARGET_SYLL_PER_SEC} syll/s) ===")
    for ln in lines:
        pcm, sr = tts._synthesize(ln)
        pcm = expand_internal_pauses(pcm, sr, scale=args.pause_scale,
                                     min_pause_ms=args.min_pause_ms,
                                     max_pause_ms=args.max_pause_ms)
        runs, pauses, lead, tail = measure(pcm, sr)
        clauses = clause_split(ln)
        syl = [sum(syllables(w) for w in c.split()) for c, _ in clauses]
        ideal_dur = [round(s / TARGET_SYLL_PER_SEC * 1000) for s in syl]
        ideal_pause = [IDEAL_PAUSE_MS.get(m, 0) for _, m in clauses]
        total = round(len(pcm) / sr * 1000)
        speech_total = sum(d for _, d in runs)
        rate = round(sum(syl) / (speech_total / 1000.0), 2) if speech_total else 0
        print(f"\nLINE: {ln!r}")
        print(f"  clauses: {[c for c, _ in clauses]}")
        print(f"  syllables/clause : {syl}  (total {sum(syl)})")
        print(f"  IDEAL dur/clause : {ideal_dur} ms   IDEAL pause: "
              f"{ideal_pause[:-1]} ms  (last->reverb tail)")
        print(f"  ACTUAL speech runs: {[d for _, d in runs]} ms   "
              f"ACTUAL pauses: {[d for _, d in pauses]} ms")
        print(f"  total={total}ms  lead_sil={lead}ms  reverb_tail={tail}ms  "
              f"speech_rate={rate} syll/s  (ideal {TARGET_SYLL_PER_SEC})")
        # quick verdict
        flags = []
        if rate > TARGET_SYLL_PER_SEC * 1.12:
            flags.append(f"TOO FAST ({rate} vs {TARGET_SYLL_PER_SEC})")
        want_internal = ideal_pause[:-1]
        got = [d for _, d in pauses]
        if len(got) < len([p for p in want_internal if p]):
            flags.append(f"MISSING pauses (want {len([p for p in want_internal if p])}, got {len(got)})")
        for p in got:
            if p < 160:
                flags.append(f"short pause {p}ms")
        if tail < 60:
            flags.append(f"reverb tail thin ({tail}ms)")
        print(f"  VERDICT: {flags or ['ok']}")
    print(f"\nCOMPRESSOR: fired {comp['fired']} times, removed {round(comp['ms'])} ms "
          f"(should be 0 -- it must not eat meaningful space)")


if __name__ == "__main__":
    raise SystemExit(main())
