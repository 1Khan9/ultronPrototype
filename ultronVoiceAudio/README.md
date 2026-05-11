# Ultron Voice Audio — voice-pipeline replacement workshop

Working directory for the 2026-05-10 voice-pipeline swap that replaced
the legacy Piper + RVC stack with **XTTS v2 streaming + a v3 Ultron
DSP filter**. Most artifacts here are gitignored (large WAVs,
isolated venvs, model caches, working sample directories) -- only the
source scripts + the corpus JSON are tracked.

## What's tracked

- `scripts/xtts_server.py` -- XTTS v2 HTTP server. Runs in the
  isolated `.venv-xtts` venv (Coqui TTS deps conflict with what
  fairseq/RVC need in the main venv). Spawned by the orchestrator's
  `XttsV3Speech` engine on startup.
- `scripts/audio_cleanup.py` -- post-synthesis trim + intra-clip
  blip removal. Used by both the bulk-generation script and the
  manual sample-cleaning pipeline. Tunable thresholds in
  `CleanupConfig`.
- `scripts/ultron_filter.py` -- prototype of the v3 Ultron filter
  chain (the runtime port lives at `src/ultron/tts/ultron_filter.py`
  in the main src tree). Bit-identical preset definitions; used for
  generating offline A/B samples that match the production runtime.
- `scripts/generate_sanity_samples.py` -- quick 5-sample XTTS
  generation for verifying the cloning is on track.
- `scripts/generate_bulk_synthetic.py` -- bulk synthesis for
  Kokoro fine-tune training data (deferred phase).
- `scripts/corpus.json` -- 602-entry text corpus for bulk synthesis,
  balanced across 8 categories. Built by `corpus_builder.py`.
- `scripts/corpus_builder.py` -- the corpus authoring script.
- `scripts/benchmark_xtts_optimized.py` -- direct-XTTS streaming
  latency benchmark (model-only TTFT, no HTTP overhead).

## What's NOT tracked

- `.venv-xtts/`, `.venv-demucs/`, `.venv-f5tts/` -- isolated venvs.
  Each is 1.5-3 GB. Recreate per the setup section below.
- `.torch_cache/`, `.hf_cache*/` -- model caches.
- `*.wav`, `*.mp3` -- audio source assets (large + personal-content).
- `synth_audio/`, `sanity_*/`, `for_review/`, `demucs_out/`,
  `smoke_*/` -- working sample directories. Regenerate with the
  scripts.
- `manifest.csv`, `manifest.jsonl`, `*.log` -- per-run outputs.

## Setup (cold start on a fresh machine)

```powershell
# 1. Create the XTTS isolated venv (matches torch CUDA version of main venv)
cd C:\STC\ultronPrototype\ultronVoiceAudio
py -3.11 -m venv .venv-xtts
.venv-xtts\Scripts\python.exe -m pip install --upgrade pip wheel setuptools
.venv-xtts\Scripts\python.exe -m pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 `
    --index-url https://download.pytorch.org/whl/cu124
.venv-xtts\Scripts\python.exe -m pip install coqui-tts fastapi uvicorn
# Coqui ships transformers 5.x which crashes XTTS; pin back to 4.x
.venv-xtts\Scripts\python.exe -m pip install "transformers>=4.46,<5.0"

# 2. Provide the speaker reference audio
# Place the cleaned mono Ultron reference at:
#   ultronVoiceAudio/Ultron_vocals_mono_v1.wav
# (Demucs separation + Audacity cleanup; see git history for the
# 2026-05-10 voice-swap session for the workflow.)

# 3. Smoke test the XTTS engine end-to-end
cd C:\STC\ultronPrototype
.venv\Scripts\python.exe scripts\smoke_xtts_v3.py
# Expects: server boot ~25s, sample synth in ~1.5s wall.
```

## Production usage

The main Ultron orchestrator picks the TTS engine via
`config.yaml -> tts.engine`:

- `"piper_rvc"` (default) -- legacy Piper + RVC stack.
- `"xtts_v3"` -- this stack. The orchestrator's
  [src/ultron/tts/xtts_v3.py](../src/ultron/tts/xtts_v3.py)
  spawns `xtts_server.py` from this directory at startup and talks
  to it over loopback HTTP. Filter parameters live under
  `tts.xtts_v3.*` in the same config.

## Deferred work: Kokoro fine-tune

The bulk synthesis script (`generate_bulk_synthetic.py`) was built
to produce ~50 minutes of Ultron-voice synthetic audio for fine-
tuning Kokoro (StyleTTS2-based, ~330 MB model, native sub-300 ms
TTFT). Kokoro fine-tune is the planned latency-recovery step once
the rest of Ultron is tuned. Constraints discovered during
research (2026-05-10):

- Kokoro has no first-party LoRA pipeline.
- Community forks (kokoro-deutsch) target full fine-tune with 20-50
  hours of audio; we have ~50 minutes of synthetic + 3 minutes of
  cleaned original.
- LoRA on StyleTTS2 with ~2 hours per speaker is the rough
  community-reported sweet spot; we'd want to expand the corpus
  before attempting.

When revisiting: extend the corpus to ~2 hours of synthetic, set up
a community StyleTTS2 LoRA fork, train with checkpointing every
~1000 steps, integrate as a third `tts.engine` value (keeping XTTS
v3 as fallback).
