"""Regenerate the full 1227-case relay corpus AND play a comprehensive random
sample aloud through the PC's DEFAULT speaker -- each sample run through the
FULL relay pipeline live (command -> 3B rephrase -> Kokoro TTS -> speaker), so
you hear exactly what a teammate would hear.

    python scripts/relay_test/play_sample.py [--tag b10] [--seed 11] [--cap 70]

Phase 1 generates ALL 1227 lines and writes them to
``logs/relay_test/rephrase_<tag>.jsonl`` for later review (no audio).
Phase 2 takes a stratified random sample (every category represented; the
persona/variety categories get an extra), runs each one through the WHOLE
pipeline fresh, and plays the result back to back, one clip at a time.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "relay_test"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))  # top-level `config` package lives at repo root

from corpus import build_corpus  # noqa: E402
from harness import _load_llm    # noqa: E402

# Categories whose lines are the most interesting to HEAR (persona / variety):
# they get an EXTRA sample. Every other category still gets one, so the sample
# covers the whole corpus while front-loading the lines worth listening to.
SHOWCASE = {
    "banter", "banter_at_ultron", "marvel", "general_knowledge", "identity",
    "greet", "farewell", "named_directive", "eco_tactics", "compose",
    "enemy_read", "context_respond", "damage", "ult", "careful", "all_enemies",
    "agent_position", "named_addressed", "roast", "fun_fact", "have_weapon",
    "enemy_ult", "enemy_utility", "self_status",
}


def _line_for(cmd, llm, recent):
    """Run the rephrase exactly like the orchestrator (roast / fun-fact speak
    verbatim from their pools; everything else goes through build_relay_line)."""
    from kenning.audio.relay_speech import (
        build_relay_line, load_fun_facts, load_roast_lines, pick_line,
    )
    if getattr(cmd, "roast", False):
        return pick_line(load_roast_lines("data/relay_roasts.txt"),
                         recent_lines=recent[-6:])
    if getattr(cmd, "fun_fact", False):
        return pick_line(load_fun_facts("data/relay_fun_facts.txt"),
                         recent_lines=recent[-6:])
    return build_relay_line(cmd, llm=llm, rephrase=True, recent_lines=recent[-6:])


def generate_all(tag, llm):
    """Phase 1: full corpus -> jsonl for later review. No audio."""
    from kenning.audio.relay_speech import match_relay_command
    cases = build_corpus()
    random.Random(7).shuffle(cases)  # match harness ordering (recent-ring realism)
    out_dir = ROOT / "logs" / "relay_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"rephrase_{tag}.jsonl"
    recent: list[str] = []
    t0 = time.time()
    with out_path.open("w", encoding="utf-8") as fh:
        for i, case in enumerate(cases, 1):
            cmd = match_relay_command(case.text)
            line = ""
            if cmd is not None:
                try:
                    line = _line_for(cmd, llm, recent)
                except Exception as e:  # noqa: BLE001
                    line = ""
            if line:
                recent.append(line)
            fh.write(json.dumps({
                "text": case.text, "category": case.category,
                "matched": cmd is not None, "line": line,
            }) + "\n")
            if i % 150 == 0:
                print(f"  ... generated {i}/{len(cases)}", flush=True)
    print(f"[generate] {len(cases)} lines in {time.time() - t0:.0f}s -> {out_path}")
    return cases


def pick_sample(cases, seed, cap):
    """Stratified random sample of CASES, total capped at ``cap``. Showcase
    (persona / variety) categories are front-loaded so a SMALL cap still plays
    the multi-sentence lines where voice quality matters most; the rest fill in
    after, then a second pick per showcase category if room remains."""
    rng = random.Random(seed)
    by_cat: dict[str, list] = {}
    for c in cases:
        if getattr(c, "expect_match", True):  # skip negative controls (no audio)
            by_cat.setdefault(c.category, []).append(c)
    show, rest, extras = [], [], []
    for cat, cs in sorted(by_cat.items()):
        picks = rng.sample(cs, min(2 if cat in SHOWCASE else 1, len(cs)))
        (show if cat in SHOWCASE else rest).append(picks[0])
        extras.extend(picks[1:])
    rng.shuffle(show)
    rng.shuffle(rest)
    rng.shuffle(extras)
    sample = (show + rest + extras)[: cap] if cap else (show + rest + extras)
    rng.shuffle(sample)
    return sample


def _build_production_kokoro(speed_override=None):
    """Build the EXACT Kokoro engine the main voice path uses -- the tuned
    Ultron voicepack with the production settings from config.yaml
    (spectral-smooth OFF, trim/fade blip+dead-space removal ON, no pedalboard).
    ``speed_override`` lets us dial the cadence for tuning (config is 1.3).
    """
    from kenning.config import get_config
    from kenning.tts.kokoro_engine import KokoroSpeech
    k = get_config().tts.kokoro
    speed = float(speed_override) if speed_override is not None else k.speed
    print(f"Kokoro: voice={k.voice!r} speed={speed} "
          f"spectral_smooth={k.apply_spectral_smooth} "
          f"trim_fade={k.apply_trim_fade} runtime_filter={k.apply_runtime_filter}")
    tts = KokoroSpeech(
        model_path=k.model_path,
        voice=k.voice,
        device=k.device,
        speed=speed,
        apply_runtime_filter=k.apply_runtime_filter,
        filter_preset=k.filter_preset,
        apply_spectral_smooth=k.apply_spectral_smooth,
        spectral_smooth_window=k.spectral_smooth_window,
        apply_trim_fade=k.apply_trim_fade,
        trim_fade_threshold_db=k.trim_fade_threshold_db,
    )
    tts.warmup()
    return tts


def synth_shaped(tts, text, args, enhanced=True):
    """Synthesize with IN-MODEL F0 contour shaping (zero latency, reverb+timbre
    preserved) live-toggled on the engine. ``enhanced=False`` = flat baseline.
    Punctuation pauses are still edited in the SILENT audio domain (artifact-free)."""
    from kenning.audio.relay_speech import relay_tts_text
    from kenning.tts.spectral_smooth import expand_internal_pauses
    if enhanced:
        tts.f0_contour_factor = args.pitch_factor
        tts.f0_shift_semitones = args.pitch_shift
        tts.f0_max_excursion = args.max_excursion
        tts.f0_energy_factor = args.energy_factor
        tts.dur_final_factor = args.dur_final
        tts.dur_internal_factor = args.dur_internal
        tts.dur_stress_factor = args.dur_stress
        tts.max_pause_cap_ms = args.max_pause_ms  # capped inside _synthesize
    else:
        tts.f0_contour_factor = 1.0
        tts.f0_shift_semitones = 0.0
        tts.f0_energy_factor = 1.0
        tts.dur_final_factor = 1.0
        tts.dur_internal_factor = 1.0
        tts.dur_stress_factor = 1.0
        tts.max_pause_cap_ms = None
    pcm, sr = tts._synthesize(relay_tts_text(text))
    return pcm, sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="b10")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--cap", type=int, default=70)
    ap.add_argument("--gap", type=float, default=0.5,
                    help="seconds of silence between clips")
    ap.add_argument("--no-regen", action="store_true",
                    help="skip regenerating the full 1227 corpus (just play)")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Kokoro speed (config is 1.3; lower = slower/clearer)")
    ap.add_argument("--pause-scale", type=float, default=1.0,
                    help="multiply each existing punctuation pause by this "
                         "(1.0 = natural pauses only; lowering speed already "
                         "lengthens them, so artificial insertion is off by default)")
    ap.add_argument("--min-pause-ms", type=int, default=80,
                    help="only stretch dips longer than this (skips word gaps)")
    ap.add_argument("--max-pause-ms", type=int, default=520,
                    help="cap any pause at this (keeps deliberate pauses under "
                         "the 600ms dead-air threshold; artifact-free)")
    ap.add_argument("--pitch-factor", type=float, default=1.4,
                    help="IN-MODEL F0 contour expansion (1.0=off; ~1.4-1.8 = more "
                         "expressive; zero latency, reverb/timbre preserved)")
    ap.add_argument("--jitter-keep", type=float, default=0.22,
                    help="fast pitch residual kept (<1 de-shakes; 0=glass smooth)")
    ap.add_argument("--smooth-ms", type=float, default=140.0,
                    help="window separating slow intonation from fast jitter")
    ap.add_argument("--median-k", type=int, default=7,
                    help="median-filter width on the pitch track (spike guard)")
    ap.add_argument("--max-excursion", type=float, default=4.5,
                    help="soft semitone limit on F0 deviation from median")
    ap.add_argument("--pitch-shift", type=float, default=-0.5,
                    help="median pitch shift in semitones (negative = deeper)")
    ap.add_argument("--energy-factor", type=float, default=1.2,
                    help="IN-MODEL energy (N_pred) dynamics expansion for "
                         "emphasis (1.0=off; ~1.1-1.3; zero latency)")
    ap.add_argument("--dur-final", type=float, default=1.3,
                    help="IN-MODEL sentence-final rime lengthening (cadence)")
    ap.add_argument("--dur-internal", type=float, default=1.18,
                    help="IN-MODEL phrase-internal (comma) rime lengthening")
    ap.add_argument("--dur-stress", type=float, default=1.08,
                    help="IN-MODEL stressed-vowel lengthening (emphasis)")
    ap.add_argument("--formant-ratio", type=float, default=1.0,
                    help="formant shift (<1 = darker/bigger timbre; 1.0=off)")
    ap.add_argument("--pre-pause-stretch", type=float, default=1.0,
                    help="slow the ~250ms leading into each pause (1.0=off, low latency)")
    ap.add_argument("--emphasis-stretch", type=float, default=1.0,
                    help="lengthen pitch-peak (emphasized) words (1.0=off)")
    ap.add_argument("--ab", action="store_true",
                    help="play each line TWICE: flat original, then enhanced")
    args = ap.parse_args()

    llm = _load_llm()

    # Phase 1 -- regenerate the whole corpus for review (unless --no-regen).
    if args.no_regen:
        cases = build_corpus()
        random.Random(7).shuffle(cases)
    else:
        cases = generate_all(args.tag, llm)
    sample = pick_sample(cases, args.seed, args.cap)

    # Phase 2 -- full pipeline, live, through the default speaker.
    from kenning.audio.relay_speech import match_relay_command, play_to_device
    import sounddevice as sd

    tts = _build_production_kokoro(speed_override=args.speed)
    from kenning.tts.f0_control import install_f0_contour_shaping
    from kenning.tts.duration_control import install_duration_shaping
    ok = install_f0_contour_shaping(tts)
    ok2 = install_duration_shaping(tts)
    print(f"In-model F0 shaping: {ok}   duration shaping: {ok2}")
    try:
        out = sd.query_devices(kind="output")
        print(f"\nDefault output device: {out['name']}")
    except Exception:  # noqa: BLE001
        pass

    print(f"\n=== Full pipeline -> speaker: {len(sample)} clips, back to back ===")
    print(f"    speed={args.speed} F0={args.pitch_factor}x shift={args.pitch_shift}st "
          f"energy={args.energy_factor}x | dur final={args.dur_final}x "
          f"internal={args.dur_internal}x stress={args.dur_stress}x | ab={args.ab}")
    print("    [IN-MODEL F0+energy+duration, 0-latency, reverb/timbre-safe, +A-site fix]")
    print("    (each: command -> 3B rephrase -> Kokoro TTS -> your speaker)\n",
          flush=True)
    recent: list[str] = []
    for i, case in enumerate(sample, 1):
        cmd = match_relay_command(case.text)
        if cmd is None:
            continue
        try:
            line = _line_for(cmd, llm, recent)
        except Exception as e:  # noqa: BLE001
            print(f"[{i:>2}/{len(sample)}] ({case.category}) rephrase error: {e}")
            continue
        if line:
            recent.append(line)
        print(f"[{i:>2}/{len(sample)}] ({case.category})", flush=True)
        print(f"     IN : {case.text}")
        print(f"     OUT: {line}", flush=True)
        try:
            if args.ab:
                print("     [A: flat]", flush=True)
                pcm, sr = synth_shaped(tts, line, args, enhanced=False)
                play_to_device(pcm, sr, None)
                time.sleep(0.35)
                print("     [B: shaped]", flush=True)
            pcm, sr = synth_shaped(tts, line, args, enhanced=True)
            play_to_device(pcm, sr, None)  # device=None -> system default speaker
        except Exception as e:  # noqa: BLE001
            print(f"     [audio error: {e}]", flush=True)
        time.sleep(args.gap)
    print("\n=== done ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
