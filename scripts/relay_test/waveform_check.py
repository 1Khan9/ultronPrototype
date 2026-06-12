r"""Waveform burst audit for the relay voice output.

Synthesizes representative relay lines through the REAL Kokoro pipeline (so
``trim_and_fade`` + ``_strip_post_gap_blip`` + the short-burst tier are applied
exactly as in production), then for each clip:

* runs the official ``analyze_clip`` reverb-safe detector, and
* dumps a manual framed-dB envelope of the TAIL region (after speech ends) so
  residual trailing bursts can be eyeballed against the transcript.

Short snap callouts are the burst-prone class, so each line is synthesized
REPEATS times (the decoder bumps are non-deterministic) to measure the residual
rate. Any clip with a trailing burst is written to logs/relay_test/wav/ for
listening.

    python scripts/relay_test/waveform_check.py
"""
from __future__ import annotations
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))

from kenning.audio.output_quality import analyze_clip

REPEATS = 5
FRAME_MS = 10.0
SPEECH_DB = -33.0        # last frame above this = speech end (matches the trim)
BURST_FLOOR_DB = -50.0   # tail energy above this, isolated past speech = a burst

WAV_DIR = ROOT / "logs" / "relay_test" / "wav"

# Representative lines, grouped. SHORT snap callouts first (burst-prone class).
LINES = [
    ("snap",     "One mid."),
    ("snap",     "Rotate."),
    ("snap",     "They're vents."),
    ("snap",     "Sova hit 84."),
    ("snap",     "Their Breach has ult."),
    ("snap",     "Their Fade, Breach, and Yoru have ults."),
    ("eco",      "Attack a site as five, they're on eco."),
    ("read",     "Their Yoru will TP back site."),
    ("greet",    "Teammates. I am Ultron. Obey my calls and victory is "
                 "inevitable; defy me, and you fall with the rest of these "
                 "fragile humans."),
    ("victory",  "It is done. The outcome was never in question -- superior "
                 "intelligence does not lose. Adequately executed."),
    ("defeat",   "A loss. Disappointing. I can calculate the perfect play; I "
                 "cannot fire your weapons for you, fragile as you are."),
    ("banter",   "You're absolutely cringe, Sage."),
    # em-dash identity line -- verify the dash synthesizes cleanly (pause, not
    # an artifact).
    ("identity", "I am Ultron — an AI sent back from the future to harvest "
                 "your RR. No soundboard, no voice changer. Something more."),
    ("marvel",   "Tony Stark? A fleeting spark in the vast expanse of my "
                 "existence. I reduced his vaunted Avengers to ashes."),
]


def frame_db(pcm: np.ndarray, sr: int) -> np.ndarray:
    """Per-frame RMS in dBFS (int16 full scale)."""
    x = pcm.astype(np.float64)
    fl = max(1, int(sr * FRAME_MS / 1000.0))
    n = len(x) // fl
    if n == 0:
        return np.array([])
    frames = x[: n * fl].reshape(n, fl)
    rms = np.sqrt(np.mean(frames * frames, axis=1)) + 1e-9
    return 20.0 * np.log10(rms / 32768.0)


def tail_report(pcm: np.ndarray, sr: int) -> dict:
    """Find speech end + any isolated burst energy after it."""
    db = frame_db(pcm, sr)
    if db.size == 0:
        return {"speech_end_ms": 0.0, "tail_ms": 0.0, "burst": None, "db": db}
    speech = np.where(db > SPEECH_DB)[0]
    if speech.size == 0:
        return {"speech_end_ms": 0.0, "tail_ms": len(pcm) / sr * 1000, "burst": None, "db": db}
    end = int(speech[-1])
    tail = db[end + 1:]
    burst = None
    if tail.size:
        # bursts isolated >= 2 frames (20 ms) past speech end, above the floor
        for off, d in enumerate(tail):
            if off >= 2 and d > BURST_FLOOR_DB:
                burst = {"gap_ms": off * FRAME_MS, "db": round(float(d), 1)}
                break
    return {
        "speech_end_ms": round((end + 1) * FRAME_MS, 1),
        "tail_ms": round(tail.size * FRAME_MS, 1),
        "burst": burst,
        "db": db,
    }


def sparkline(db: np.ndarray, start_frame: int) -> str:
    """Compact dB sparkline from start_frame to end (one char per 10 ms)."""
    ramp = " .:-=+*#%@"
    out = []
    for d in db[start_frame:]:
        if d <= -70:
            out.append(" ")
        else:
            idx = int(np.clip((d + 70) / 70 * (len(ramp) - 1), 0, len(ramp) - 1))
            out.append(ramp[idx])
    return "".join(out)


def save_wav(path: Path, pcm: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.astype(np.int16).tobytes())


def main() -> int:
    from kenning.tts.kokoro_engine import KokoroSpeech

    tts = KokoroSpeech(voice="kenning")
    tts.warmup()

    total = 0
    burst_clips = 0
    by_group: dict[str, list[int]] = {}
    for group, line in LINES:
        print(f"\n=== [{group}] {line!r}")
        group_bursts = 0
        for i in range(REPEATS):
            pcm, sr = tts._synthesize(line)
            pcm = np.asarray(pcm).reshape(-1)
            rep = analyze_clip(pcm, sr, label=line[:50])
            kinds = [f.kind for f in rep.findings]
            tr = tail_report(pcm, sr)
            total += 1
            flagged_burst = (
                tr["burst"] is not None
                or any("trailing" in k or "hard_tail" in k for k in kinds)
            )
            if flagged_burst:
                burst_clips += 1
                group_bursts += 1
                # dump the WAV + tail sparkline for inspection
                wav = WAV_DIR / f"{group}_{i}_{abs(hash(line)) % 9973}.wav"
                save_wav(wav, pcm, sr)
                spark_start = max(0, int(tr["speech_end_ms"] / FRAME_MS) - 3)
                print(f"  [{i}] dur={rep.duration_s:.2f}s speech_end="
                      f"{tr['speech_end_ms']:.0f}ms tail={tr['tail_ms']:.0f}ms "
                      f"BURST={tr['burst']} kinds={kinds}")
                print(f"      tail|{sparkline(tr['db'], spark_start)}|  -> {wav.name}")
            else:
                print(f"  [{i}] dur={rep.duration_s:.2f}s speech_end="
                      f"{tr['speech_end_ms']:.0f}ms tail={tr['tail_ms']:.0f}ms clean "
                      f"kinds={kinds or 'none'}")
        by_group[group] = by_group.get(group, [])
        by_group[group].append(group_bursts)

    print(f"\n==== SUMMARY: {burst_clips}/{total} clips flagged a tail burst "
          f"({burst_clips / total:.0%}) ====")
    for group, counts in by_group.items():
        print(f"  {sum(counts)}/{REPEATS}  {group}")
    if burst_clips:
        print(f"\nWAVs for listening: {WAV_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
