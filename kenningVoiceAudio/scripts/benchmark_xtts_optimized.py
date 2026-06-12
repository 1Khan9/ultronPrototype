"""Benchmark XTTS v2 with all the optimisations the naive ``tts_to_file``
path skips: streaming inference, pre-computed speaker embedding,
direct model API (bypasses the high-level TTS wrapper overhead).

Goal: measure realistic production-mode latency for the voice path
to decide whether XTTS+v3 is competitive with current Piper+RVC.

Reports for each sentence:
  - TTFT (time-to-first-audio-chunk) -- the user-perceived latency
  - TTC  (time-to-completion -- last chunk emitted)
  - audio_duration -- wall-clock playback length
  - rtf  (real-time factor: synth_time / audio_duration; <1 = faster than realtime)

Run:
    python benchmark_xtts_optimized.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REFERENCE_WAV = PROJECT / "kokoro training audio" / "Kenning_vocals_mono_v1.wav"

# Same 5 sentences as the sanity batch so we can compare against
# the prior (non-optimised) numbers head-to-head.
SAMPLES = [
    ("01_short", "Acknowledged. Initiating the requested operation."),
    ("02_kenning_flavor", "There are no humans here. Just me."),
    ("03_medium_technical", "I have completed the analysis. The optimal solution requires three steps."),
    ("04_tool_ack", "Searching the web for that information now."),
    ("05_longer", "I find your question intriguing. Allow me to elaborate on the relevant facts before we proceed."),
]


def _build_xtts(use_fp16: bool):
    """Load the XTTS model directly (not via the TTS wrapper).

    The wrapper auto-resolves model paths via Coqui's model manager
    and downloads if missing. We do the same here but instantiate the
    Xtts model class directly so we get access to the
    ``inference_stream`` + ``get_conditioning_latents`` methods.
    """
    from TTS.utils.manage import ModelManager
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    # Resolve model path (downloads on first run, but should already be cached
    # from the earlier sanity run).
    manager = ModelManager()
    model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
    model_path, config_path, _ = manager.download_model(model_name)
    print(f"  model_path: {model_path}")

    config = XttsConfig()
    config.load_json(str(Path(model_path) / "config.json"))

    model = Xtts.init_from_config(config)
    model.load_checkpoint(
        config,
        checkpoint_dir=str(model_path),
        eval=True,
    )
    if torch.cuda.is_available():
        model.cuda()
        # NOTE: fp16 conversion (model.half() / model.gpt.half()) breaks
        # both the speaker encoder (conv1d filter) and downstream bias
        # tensors -- XTTS isn't trained with mixed precision in mind.
        # Streaming + cached embedding gives the bulk of the speedup
        # without the dtype hazards.
    return model, config


def _bench_one(model, gpt_latent, speaker_emb, text: str,
               stream_chunk_size: int, sample_rate: int) -> dict:
    """Run one streaming inference + measure TTFT, TTC, audio_duration."""
    chunks = []
    chunk_times = []
    t0 = time.monotonic()
    for chunk in model.inference_stream(
        text=text,
        language="en",
        gpt_cond_latent=gpt_latent,
        speaker_embedding=speaker_emb,
        stream_chunk_size=stream_chunk_size,
        temperature=0.75,
    ):
        chunk_times.append(time.monotonic() - t0)
        # chunk is a torch tensor on GPU; move to CPU
        chunks.append(chunk.detach().cpu().numpy())
    if not chunks:
        return {"error": "no chunks emitted"}
    full_audio = np.concatenate(chunks)
    audio_duration = full_audio.shape[0] / sample_rate
    ttft = chunk_times[0]
    ttc = chunk_times[-1]
    return {
        "ttft": ttft,
        "ttc": ttc,
        "audio_duration": audio_duration,
        "rtf": ttc / max(audio_duration, 1e-6),
        "n_chunks": len(chunks),
        "chars": len(text),
    }


def main() -> int:
    print(f"torch: {torch.__version__}, cuda: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"device: {torch.cuda.get_device_name(0)}")
    print(f"reference: {REFERENCE_WAV}")

    if not REFERENCE_WAV.is_file():
        print(f"ERROR: reference missing")
        return 1

    print("\n=== Loading XTTS (fp16) ===")
    t0 = time.monotonic()
    model, config = _build_xtts(use_fp16=True)
    print(f"loaded in {time.monotonic()-t0:.1f}s")
    if torch.cuda.is_available():
        print(f"VRAM after load: {torch.cuda.memory_allocated()/1e6:.0f} MB")

    sample_rate = config.audio.output_sample_rate
    print(f"output sample rate: {sample_rate}")

    print("\n=== Pre-computing speaker embedding (one-time) ===")
    t0 = time.monotonic()
    gpt_latent, speaker_emb = model.get_conditioning_latents(audio_path=str(REFERENCE_WAV))
    print(f"computed in {time.monotonic()-t0:.2f}s")
    print(f"  gpt_latent shape: {tuple(gpt_latent.shape)}")
    print(f"  speaker_emb shape: {tuple(speaker_emb.shape)}")

    # Warmup pass on a tiny string to JIT-compile any kernels.
    print("\n=== Warmup pass ===")
    t0 = time.monotonic()
    _ = list(model.inference_stream(
        text="Hello.",
        language="en",
        gpt_cond_latent=gpt_latent,
        speaker_embedding=speaker_emb,
        stream_chunk_size=20,
    ))
    print(f"warmup in {time.monotonic()-t0:.2f}s")

    # Benchmark with two stream chunk sizes:
    #   20 = default (Coqui's recommended for streaming)
    #   40 = larger chunks, fewer per-call overhead, slightly higher TTFT
    for chunk_size in (20, 40):
        print(f"\n=== Benchmark with stream_chunk_size={chunk_size} ===")
        print(f"{'tag':<22}{'chars':>6}{'TTFT (ms)':>11}{'TTC (ms)':>10}{'audio (s)':>11}{'RTF':>7}{'chunks':>8}")
        print("-" * 75)
        ttft_samples = []
        ttc_samples = []
        for tag, text in SAMPLES:
            r = _bench_one(model, gpt_latent, speaker_emb, text, chunk_size, sample_rate)
            if "error" in r:
                print(f"{tag:<22} {r['error']}")
                continue
            ttft_samples.append(r["ttft"])
            ttc_samples.append(r["ttc"])
            print(f"{tag:<22}{r['chars']:>6}{r['ttft']*1000:>11.0f}{r['ttc']*1000:>10.0f}{r['audio_duration']:>11.2f}{r['rtf']:>7.2f}{r['n_chunks']:>8}")
        if ttft_samples:
            print(f"\nTTFT median: {sorted(ttft_samples)[len(ttft_samples)//2]*1000:.0f} ms")
            print(f"TTFT min:    {min(ttft_samples)*1000:.0f} ms")
            print(f"TTFT max:    {max(ttft_samples)*1000:.0f} ms")

    if torch.cuda.is_available():
        peak = torch.cuda.max_memory_allocated() / 1e6
        print(f"\nPeak VRAM: {peak:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
