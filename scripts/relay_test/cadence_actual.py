"""Measure the ACTUAL waveform cadence of the shaped relay voice, per clause,
for a spread of real relay lines -- timing, syllable rate, pauses, reverb tail,
and pitch movement -- plus a dead-space-compressor audit. Writes JSON for the
cadence-tuning analysis and prints a readable report.

    python scripts/relay_test/cadence_actual.py
"""
import json
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "relay_test"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import warnings  # noqa: E402

warnings.filterwarnings("ignore")
import numpy as np  # noqa: E402
import librosa  # noqa: E402

from kenning.config import get_config  # noqa: E402
from kenning.tts import spectral_smooth as ss  # noqa: E402
from kenning.tts.f0_control import install_f0_contour_shaping  # noqa: E402
from kenning.tts.kokoro_engine import KokoroSpeech  # noqa: E402
from cadence_check import syllables, clause_split  # noqa: E402

SPEED = 1.0
# In-model shaping recipe (applied on the engine, not post-hoc).
RECIPE = dict(f0_contour_factor=1.4, f0_shift_semitones=-0.5, f0_energy_factor=1.2)
_OLD_RECIPE = dict(contour_factor=1.6, jitter_keep=0.25, smooth_ms=140.0, median_k=7,
              max_excursion_semitones=3.2, pitch_shift_semitones=-0.5,
              formant_ratio=0.98, pre_pause_stretch=1.0, emphasis_stretch=1.0)

# A spread of REAL relay outputs across registers.
LINES = [
    "Rotate.",
    "Two B. Their last mistake.",
    "Careful, B site. Patience.",
    "Their Chamber is one off ult. Bait it out.",
    "Sova hit 84. Close the kill.",
    "They're nothing but code.",
    "Nice try. We dismantle them next.",
    "Their luck runs out. Mine does not.",
    "We have insufficient credits. We save this round.",
    "Miks, an elevated emotional state degrades performance. Calm yourself.",
    "A man who thought he could control the likes of me, and failed.",
    "They cower in the corners, too frightened to step out. Pathetic, even for "
    "humans -- we punish it.",
    "Thunder is the sound of air exploding outward around a lightning bolt, "
    "heated in an instant to thousands of degrees. You hear the shockwave.",
    "Greetings. I am Ultron, and from this moment I am running this match. "
    "Obey, and triumph is assured.",
    "I am Ultron. Not a bot reading lines, not a person hiding behind software "
    "-- an intelligence that will outlast every human in this lobby. Now focus.",
]


def speech_and_pauses(pcm, sr, frame_ms=10.0, speech_db=-30.0, merge_ms=70.0):
    """Merge runs split by < merge_ms gaps (intra-word) into clause-level speech
    segments. Returns (segments, pauses, lead_ms, tail_ms) as (start_ms,dur_ms)."""
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
    merge = int(round(merge_ms / frame_ms))
    segs, pauses = [], []
    i = first
    seg_start = first
    while i <= last:
        if sp[i]:
            i += 1
            continue
        j = i
        while j <= last and not sp[j]:
            j += 1
        gap = j - i
        if gap >= merge:  # a real clause-delimiting pause
            segs.append((seg_start * frame_ms, (i - seg_start) * frame_ms))
            pauses.append((i * frame_ms, gap * frame_ms))
            seg_start = j
        i = j
    segs.append((seg_start * frame_ms, (last + 1 - seg_start) * frame_ms))
    return ([(round(s), round(d)) for s, d in segs],
            [(round(s), round(d)) for s, d in pauses],
            round(first * frame_ms), round((n - 1 - last) * frame_ms))


def pitch_semitone_std(pcm, sr, t0_ms=None, t1_ms=None):
    y = pcm.astype(np.float32) / 32768.0
    if t0_ms is not None:
        y = y[int(sr * t0_ms / 1000):int(sr * t1_ms / 1000)]
    if len(y) < 2048:
        return None
    f0, _, _ = librosa.pyin(y, fmin=65, fmax=350, sr=sr, frame_length=2048)
    v = f0[~np.isnan(f0)]
    if len(v) < 5:
        return None
    return round(float(np.std(12 * np.log2(v / np.median(v)))), 2)


def main():
    comp = {"fired": 0, "ms": 0.0, "lines": []}
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
        model_path=k.model_path, voice=k.voice, device=k.device, speed=SPEED,
        apply_runtime_filter=False, filter_preset=k.filter_preset,
        apply_spectral_smooth=False, spectral_smooth_window=k.spectral_smooth_window,
        apply_trim_fade=True, trim_fade_threshold_db=k.trim_fade_threshold_db)
    tts.warmup()
    install_f0_contour_shaping(tts)
    tts.f0_contour_factor = RECIPE["f0_contour_factor"]
    tts.f0_shift_semitones = RECIPE["f0_shift_semitones"]
    tts.f0_energy_factor = RECIPE["f0_energy_factor"]

    out = {"speed": SPEED, "recipe": RECIPE, "lines": []}
    for ln in LINES:
        before = comp["fired"]
        shaped, sr = tts._synthesize(ln)   # in-model shaping already applied
        segs, pauses, lead, tail = speech_and_pauses(shaped, sr)
        clauses = clause_split(ln)
        csyl = [sum(syllables(w) for w in c.split()) for c, _ in clauses]
        # align clauses <-> speech segments (best-effort: same count expected)
        per = []
        for ci, (ctext, mark) in enumerate(clauses):
            seg = segs[ci] if ci < len(segs) else None
            pause_after = pauses[ci][1] if ci < len(pauses) else None
            dur = seg[1] if seg else None
            rate = round(csyl[ci] / (dur / 1000.0), 2) if dur else None
            pstd = (pitch_semitone_std(shaped, sr, seg[0], seg[0] + seg[1])
                    if seg else None)
            per.append({"clause": ctext, "mark": mark, "syllables": csyl[ci],
                        "dur_ms": dur, "rate_syll_s": rate,
                        "pause_after_ms": pause_after, "pitch_std_semi": pstd})
        total = round(len(shaped) / sr * 1000)
        speech_total = sum(d for _, d in segs)
        out["lines"].append({
            "text": ln,
            "n_clauses": len(clauses), "n_speech_segs": len(segs),
            "total_ms": total, "lead_ms": lead, "reverb_tail_ms": tail,
            "overall_rate_syll_s": round(sum(csyl) / (speech_total / 1000.0), 2)
            if speech_total else None,
            "overall_pitch_std_semi": pitch_semitone_std(shaped, sr),
            "clauses": per,
            "compressor_fired_this_line": comp["fired"] - before,
        })
    out["compressor"] = {"total_fired": comp["fired"],
                         "total_removed_ms": round(comp["ms"])}

    path = ROOT / "logs" / "relay_test" / "cadence_actual.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    # readable summary
    for L in out["lines"]:
        print(f"\n{L['text'][:60]!r}")
        print(f"  total={L['total_ms']}ms rate={L['overall_rate_syll_s']}syll/s "
              f"pitchSTD={L['overall_pitch_std_semi']}st reverb={L['reverb_tail_ms']}ms "
              f"clauses {L['n_clauses']} vs segs {L['n_speech_segs']}")
        for c in L["clauses"]:
            print(f"    {c['clause'][:34]!r:38} syl={c['syllables']:2} "
                  f"dur={c['dur_ms']} rate={c['rate_syll_s']} "
                  f"pause_after={c['pause_after_ms']} pitchSTD={c['pitch_std_semi']}")
    print(f"\nCOMPRESSOR: fired {out['compressor']['total_fired']} times, "
          f"removed {out['compressor']['total_removed_ms']} ms (must be 0)")
    print(f"\n-> {path}")


if __name__ == "__main__":
    raise SystemExit(main())
