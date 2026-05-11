"""XTTS v2 sanity-check sample generator.

Phase A of the Kokoro fine-tune pipeline. Generates 5 short utterances
using the cleaned Ultron reference audio so we can verify XTTS is
correctly cloning the timbre BEFORE burning hours generating bulk
synthetic data for Kokoro training.

This is NOT a quality decision point ("should we use Kokoro?") — that's
locked. It's a sanity gate: if XTTS clones the wrong voice or produces
audible artifacts, we'd waste 4 hours of GPU generating bad training
data. A 30-min sanity pass catches that.

Run:
    python C:/STC/ultronPrototype/ultronVoiceAudio/scripts/generate_sanity_samples.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Workaround for Windows env vars pointing at non-existent D:\
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent  # C:/STC/ultronPrototype/ultronVoiceAudio
os.environ["TORCH_HOME"] = str(PROJECT / ".torch_cache")
os.environ["HF_HOME"] = str(PROJECT / ".hf_cache")
os.environ["TRANSFORMERS_CACHE"] = str(PROJECT / ".hf_cache")
os.environ["COQUI_TOS_AGREED"] = "1"  # auto-accept Coqui Public Model License
(PROJECT / ".torch_cache").mkdir(exist_ok=True)
(PROJECT / ".hf_cache").mkdir(exist_ok=True)

REFERENCE_WAV = PROJECT / "Ultron_vocals_mono_v1.wav"
OUTPUT_DIR = PROJECT / "sanity_samples"
OUTPUT_DIR.mkdir(exist_ok=True)

# Five sanity utterances chosen to cover:
#   - Short response (typical "Acknowledged" turn)
#   - Ultron-flavored statement (theatrical but not over the top)
#   - Medium technical (most common shape: information delivery)
#   - Tool-call ack (the second-most-common shape: status announcement)
#   - Slightly longer composed sentence (stress test for prosody coherence)
SAMPLES = [
    ("01_short", "Acknowledged. Initiating the requested operation."),
    ("02_ultron_flavor", "There are no humans here. Just me."),
    ("03_medium_technical", "I have completed the analysis. The optimal solution requires three steps."),
    ("04_tool_ack", "Searching the web for that information now."),
    ("05_longer", "I find your question intriguing. Allow me to elaborate on the relevant facts before we proceed."),
]


def main() -> int:
    import torch
    print(f"torch: {torch.__version__}")
    print(f"cuda available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"device: {torch.cuda.get_device_name(0)}")

    if not REFERENCE_WAV.is_file():
        print(f"ERROR: reference audio missing: {REFERENCE_WAV}")
        return 1
    print(f"reference: {REFERENCE_WAV} ({REFERENCE_WAV.stat().st_size/1e6:.1f} MB)")

    # Late import so the env vars are set before TTS reads them.
    from TTS.api import TTS

    print("\nLoading XTTS v2 (downloads ~2 GB on first run)...")
    t0 = time.monotonic()
    tts = TTS(
        model_name="tts_models/multilingual/multi-dataset/xtts_v2",
        gpu=torch.cuda.is_available(),
    )
    load_seconds = time.monotonic() - t0
    print(f"XTTS v2 loaded in {load_seconds:.1f}s")

    if torch.cuda.is_available():
        vram_mb = torch.cuda.memory_allocated() / 1e6
        print(f"VRAM after load: {vram_mb:.0f} MB")

    print(f"\nGenerating {len(SAMPLES)} sanity samples to {OUTPUT_DIR}/")
    timings = []
    for tag, text in SAMPLES:
        out = OUTPUT_DIR / f"{tag}.wav"
        print(f"  [{tag}] '{text[:60]}...'" if len(text) > 60 else f"  [{tag}] '{text}'")
        t0 = time.monotonic()
        tts.tts_to_file(
            text=text,
            speaker_wav=str(REFERENCE_WAV),
            language="en",
            file_path=str(out),
            split_sentences=True,
        )
        synth_s = time.monotonic() - t0
        timings.append((tag, synth_s, len(text)))
        print(f"    -> {out.name} ({synth_s:.2f}s)")

    print("\n" + "=" * 60)
    print("Per-sample synthesis time")
    print(f"{'tag':<22}{'wall (s)':>10}{'chars':>8}{'ms/char':>10}")
    print("-" * 60)
    for tag, s, chars in timings:
        print(f"{tag:<22}{s:>10.2f}{chars:>8d}{s*1000/chars:>10.1f}")
    total = sum(s for _, s, _ in timings)
    print(f"{'TOTAL':<22}{total:>10.2f}")
    if torch.cuda.is_available():
        peak = torch.cuda.max_memory_allocated() / 1e6
        print(f"\nPeak VRAM during synthesis: {peak:.0f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
