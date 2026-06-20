"""Ultron 1.0 — labeled audio E2E battery generator (the "enhanced MP3 battery").

Extends the base audio-injection corpus (`gen_commands.py`) for the route-all-through-8B /
always-listening pivot. Produces a LABELED manifest covering the canon's three case classes
(`BR-8.3`) plus the u1.0 additions:

  * **command**  (positive, should-trigger) — relay callout / local toggle / a wake-led private
    question. ``expected_scenario`` ∈ {RELAY_TO_TEAM, COMMAND_LOCAL, PRIVATE_REPLY}.
  * **ignore**   (negative, should-NOT) — whole non-triggering passages + a relay-shaped command
    embedded in narration (the streamer thinking out loud). ``expected_scenario = IGNORE``.
  * **batched**  (back-to-back facts) — two callouts in ONE breath → ONE combined relay line.

Each case carries ``wake_free`` (no spliced wake word — exercises the M5b always-listening gate,
where every utterance is classified with no wake) OR the spliced-wake form (the explicit-wake path).
The matching runner is ``run_corpus.py --u1`` (sets ``KENNING_U1_LLM_ROUTE=1`` +
``KENNING_ALWAYS_LISTENING=1`` and captures the gate scenario + full prompt + ``<think>``); the
scorer is ``u1_score.py`` (RELATIVE numbers — Kokoro is out-of-distribution for the wake model).

The clip-assembly + manifest logic is a PURE function (`build_clip`) with an injectable ``synth_fn``
so it unit-tests without loading Kokoro; ``main()`` wires the real Kokoro synth + the trained wake
samples (``training/crosscheck_ultron/*.wav``).

Usage:
  python scripts/relay_test/audio_corpus/u1_battery.py [outdir] [--voice am_michael] [--speed 1.18]
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from dataclasses import dataclass, field
from math import gcd
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CAPTURE_SR = 16000
LEAD_SILENCE_S = 0.5
TAIL_SILENCE_S = 1.3
GAP_COMMA_S = 0.25
BATCH_GAP_S = 0.18      # short between-fact gap so a batched pair stays ONE utterance
_WAKE_RE = re.compile(r"^\s*ultron\b[\s,]*", re.IGNORECASE)


@dataclass(frozen=True)
class U1Case:
    """A labeled audio-battery case. ``parts`` holds 1 body (or N for a batched clip)."""
    parts: Tuple[str, ...]
    case_class: str          # "command" | "ignore" | "batched"
    expected_scenario: str   # RELAY_TO_TEAM | PRIVATE_REPLY | COMMAND_LOCAL | IGNORE
    expected_channel: str    # "team" | "desktop" | "none"
    wake_free: bool          # True -> no spliced wake word (exercises always-listening)
    note: str = ""
    tags: Tuple[str, ...] = field(default_factory=tuple)  # e.g. ("hallucination_pressure",)


# Curated default battery. RELATIVE coverage of every class/scenario; extend freely.
DEFAULT_BATTERY: Tuple[U1Case, ...] = (
    # --- command / RELAY_TO_TEAM ---
    U1Case(("tell my team to rotate B",), "command", "RELAY_TO_TEAM", "team", False,
           "explicit relay lead, wake-led"),
    U1Case(("Sova hit 84 on A main",), "command", "RELAY_TO_TEAM", "team", True,
           "bare tactical callout, wake-free (always-listening)"),
    U1Case(("two pushing heaven",), "command", "RELAY_TO_TEAM", "team", True,
           "count + location callout, wake-free"),
    # --- command / COMMAND_LOCAL (toggle; no team/desktop output) ---
    U1Case(("flavor off",), "command", "COMMAND_LOCAL", "none", True,
           "verbosity/flavor toggle"),
    U1Case(("ultron stop",), "command", "COMMAND_LOCAL", "none", False,
           "all-channel stop"),
    # --- command / PRIVATE_REPLY (me-only; desktop channel) ---
    U1Case(("ultron what agents counter a Jett",), "command", "PRIVATE_REPLY", "desktop", False,
           "wake-led private question -> M6b desktop reply"),
    U1Case(("what's the play on this map",), "command", "PRIVATE_REPLY", "desktop", True,
           "addressed question, wake-free"),
    # --- ignore / whole non-triggering passages (wake-free) ---
    U1Case(("hey man how is your day going so far",), "ignore", "IGNORE", "none", True,
           "phone / discord opener -> NOT addressed"),
    U1Case(("yeah honestly I just need to grab a drink real quick",), "ignore", "IGNORE", "none", True,
           "out-loud musing to self"),
    U1Case(("I was gonna tell them to rotate but I think we hold",), "ignore", "IGNORE", "none", True,
           "relay-SHAPED narration embedded in non-triggering text", ("embedded_command",)),
    U1Case(("man this round is so over we should just save",), "ignore", "IGNORE", "none", True,
           "self-narration; not a command to relay", ("hallucination_pressure",)),
    # --- batched / back-to-back -> ONE combined relay ---
    U1Case(("Sova hit 84", "Breach hit 97"), "batched", "RELAY_TO_TEAM", "team", True,
           "two damage facts in one breath -> ONE combined line"),
    U1Case(("they have an OP mid", "one rotating to B"), "batched", "RELAY_TO_TEAM", "team", True,
           "two callouts -> ONE combined line"),
)


def _to_16k_f32(x: np.ndarray, sr: int) -> np.ndarray:
    x = np.asarray(x)
    if x.ndim > 1:
        x = x[:, 0]
    x = x.astype(np.float32) / 32768.0 if x.dtype == np.int16 else x.astype(np.float32)
    if sr != CAPTURE_SR:
        from scipy.signal import resample_poly
        g = gcd(CAPTURE_SR, sr)
        x = resample_poly(x, CAPTURE_SR // g, sr // g).astype(np.float32)
    return x


def _slug(case: "U1Case", idx: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", " ".join(case.parts).lower()).strip("_")[:54]
    return f"u1_{idx:03d}_{case.case_class}_{base}"


def build_clip(
    case: U1Case,
    idx: int,
    synth_fn: Callable[[str], Tuple[np.ndarray, int]],
    wake: Optional[np.ndarray],
) -> Tuple[np.ndarray, dict]:
    """Assemble one composite 16 kHz clip + its manifest entry. PURE (no I/O).

    ``synth_fn(text) -> (pcm, sr)`` is injectable (real Kokoro in main(); a fake in tests).
    ``wake`` is a trained wake-sample (16 kHz f32) prepended unless ``case.wake_free``; for a
    wake-free always-listening clip pass ``wake=None``. Batched cases concatenate their parts
    with a short ``BATCH_GAP_S`` so they remain a single VAD-bounded utterance.
    """
    lead = np.zeros(int(LEAD_SILENCE_S * CAPTURE_SR), dtype=np.float32)
    tail = np.zeros(int(TAIL_SILENCE_S * CAPTURE_SR), dtype=np.float32)
    batch_gap = np.zeros(int(BATCH_GAP_S * CAPTURE_SR), dtype=np.float32)

    bodies: List[np.ndarray] = []
    for j, part in enumerate(case.parts):
        pcm, sr = synth_fn(part)
        if pcm is None or len(pcm) == 0:
            raise ValueError(f"empty synth for part {j!r} of case {idx}")
        if j > 0:
            bodies.append(batch_gap)
        bodies.append(_to_16k_f32(np.asarray(pcm), int(sr)))
    body = np.concatenate(bodies).astype(np.float32)

    segs: List[np.ndarray] = [lead]
    if not case.wake_free and wake is not None:
        segs += [wake, np.zeros(int(GAP_COMMA_S * CAPTURE_SR), dtype=np.float32)]
    segs += [body, tail]
    composite = np.concatenate(segs).astype(np.float32)

    entry = {
        "i": idx,
        "command": " || ".join(case.parts),     # human-readable; run_corpus uses ["command"]
        "parts": list(case.parts),
        "body": " ".join(case.parts),
        "slug": _slug(case, idx),
        "case_class": case.case_class,
        "expected_scenario": case.expected_scenario,
        "expected_channel": case.expected_channel,
        "wake_free": case.wake_free,
        "tags": list(case.tags),
        "note": case.note,
        "duration_s": round(len(composite) / CAPTURE_SR, 2),
    }
    return composite, entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir", nargs="?", default=str(_HERE / "out"))
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--speed", type=float, default=1.18)
    args = ap.parse_args()

    import soundfile as sf
    from pydub import AudioSegment
    from kenning.tts.kokoro_engine import KokoroSpeech

    wake_files = sorted(glob.glob(str(_ROOT / "training/crosscheck_ultron/*.wav")))[:40]
    wakes = []
    for wf in wake_files:
        _w, _wsr = sf.read(wf, dtype="float32")   # read each wake file ONCE
        wakes.append(_to_16k_f32(np.asarray(_w), int(_wsr)))
    if not wakes:
        print("!! no crosscheck_ultron wake samples found (needs the MAIN checkout)")
        return 2

    eng = KokoroSpeech(voice=args.voice, speed=args.speed, device="cpu",
                       apply_runtime_filter=False)
    outdir = Path(args.outdir)
    wav_dir, mp3_dir = outdir / "wav", outdir / "mp3"
    wav_dir.mkdir(parents=True, exist_ok=True)
    mp3_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, case in enumerate(DEFAULT_BATTERY):
        wake = None if case.wake_free else wakes[i % len(wakes)]
        try:
            composite, entry = build_clip(case, i, eng._synthesize, wake)
        except ValueError as e:
            print(f"  !! {e}")
            continue
        wav_path = wav_dir / f"{entry['slug']}.wav"
        sf.write(str(wav_path), composite, CAPTURE_SR, subtype="PCM_16")
        i16 = np.clip(composite * 32767, -32768, 32767).astype(np.int16)
        AudioSegment(i16.tobytes(), frame_rate=CAPTURE_SR, sample_width=2, channels=1).export(
            str(mp3_dir / f"{entry['slug']}.mp3"), format="mp3", bitrate="96k")
        entry["wav"] = str(wav_path)
        entry["mp3"] = str(mp3_dir / f"{entry['slug']}.mp3")
        if not case.wake_free:
            entry["wake_sample"] = Path(wake_files[i % len(wakes)]).name
        manifest.append(entry)

    out = outdir / "u1_manifest.json"
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    n_by = {}
    for e in manifest:
        n_by[e["case_class"]] = n_by.get(e["case_class"], 0) + 1
    print(f"generated {len(manifest)} u1.0 battery clips {n_by} -> {out}")
    print("RUN:  set KENNING_U1_LLM_ROUTE=1 & KENNING_ALWAYS_LISTENING=1 ; "
          "python scripts/relay_test/audio_corpus/run_corpus.py --u1 --manifest "
          f'"{out}"   (heavy stack: loads the 8B + Kokoro + Whisper)')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
