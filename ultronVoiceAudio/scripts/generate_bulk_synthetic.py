"""XTTS v2 bulk synthetic-data generation.

Phase B of the Kokoro fine-tune pipeline. Reads ``corpus.json``,
synthesises every entry through XTTS v2 using the cleaned Ultron
reference audio, and emits:

    - One audio WAV per entry under ``synth_audio/<id>.wav``
    - ``manifest.csv``  -- LJSpeech-style ``id|audio_path|text|...``
    - ``manifest.jsonl`` -- one JSON object per line with full metadata
    - ``generation_log.jsonl`` -- per-entry generation event log

**Resume semantics.** If a previous run was interrupted, just re-run
this script. It skips entries whose audio file already exists on
disk and re-uses the prior manifest entry. To re-generate a specific
entry, delete its WAV file and re-run.

**Failure handling.** Per-entry failures (XTTS synth error, disk
write error) are logged to ``generation_log.jsonl`` with status
``failed`` and the run continues. The final ``manifest.csv`` excludes
failed entries so downstream Kokoro training never sees broken audio.

Run:
    python C:/STC/ultronPrototype/ultronVoiceAudio/scripts/generate_bulk_synthetic.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Workaround for Windows env vars pointing at non-existent D:\
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent  # C:/STC/ultronPrototype/ultronVoiceAudio
os.environ["TORCH_HOME"] = str(PROJECT / ".torch_cache")
os.environ["HF_HOME"] = str(PROJECT / ".hf_cache")
os.environ["TRANSFORMERS_CACHE"] = str(PROJECT / ".hf_cache")
os.environ["COQUI_TOS_AGREED"] = "1"

REFERENCE_WAV = PROJECT / "Ultron_vocals_mono_v1.wav"
CORPUS_JSON = HERE / "corpus.json"
OUTPUT_DIR = PROJECT / "synth_audio"
MANIFEST_CSV = PROJECT / "manifest.csv"
MANIFEST_JSONL = PROJECT / "manifest.jsonl"
LOG_JSONL = PROJECT / "generation_log.jsonl"


def _append_log(payload: dict[str, Any]) -> None:
    """Append one event to the generation log. Best-effort, never raises."""
    try:
        with LOG_JSONL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception as e:  # pragma: no cover - log-of-log is fine to swallow
        print(f"WARN: failed to write generation log: {e}")


def _audio_duration_seconds(path: Path) -> Optional[float]:
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return info.frames / info.samplerate
    except Exception:
        return None


def _trim_silence_and_fade(path: Path) -> None:
    """Clean an XTTS output WAV in place.

    Delegates to :mod:`audio_cleanup.clean_xtts_output` -- see that
    module for the trim + intra-clip-blip-removal logic and tunable
    thresholds. Best-effort wrapper: any exception is logged and the
    file is left as-is.
    """
    try:
        import audio_cleanup  # local module under scripts/
        audio_cleanup.clean_xtts_output(path)
    except Exception as e:  # pragma: no cover - best-effort cleanup
        print(f"WARN: cleanup failed for {path.name}: {e}")


def main() -> int:
    import torch

    print(f"torch: {torch.__version__}, cuda: {torch.cuda.is_available()}")
    if not REFERENCE_WAV.is_file():
        print(f"ERROR: reference audio missing: {REFERENCE_WAV}")
        return 1
    if not CORPUS_JSON.is_file():
        print(f"ERROR: corpus missing: {CORPUS_JSON}")
        print(f"Run scripts/corpus_builder.py first.")
        return 1

    OUTPUT_DIR.mkdir(exist_ok=True)
    entries = json.loads(CORPUS_JSON.read_text(encoding="utf-8"))
    print(f"corpus: {len(entries)} entries")

    # Pre-flight: count what's already done so we can report skipped-vs-fresh.
    pre_done = sum(1 for e in entries if (OUTPUT_DIR / f"{e['id']}.wav").is_file())
    print(f"already complete: {pre_done} / {len(entries)} (will skip on resume)")

    from TTS.api import TTS
    print("\nLoading XTTS v2...")
    t0 = time.monotonic()
    tts = TTS(
        model_name="tts_models/multilingual/multi-dataset/xtts_v2",
        gpu=torch.cuda.is_available(),
    )
    load_s = time.monotonic() - t0
    print(f"XTTS v2 loaded in {load_s:.1f}s")
    if torch.cuda.is_available():
        print(f"VRAM after load: {torch.cuda.memory_allocated()/1e6:.0f} MB")

    _append_log({
        "event": "run_start",
        "ts": time.time(),
        "corpus_size": len(entries),
        "already_complete": pre_done,
        "model_load_seconds": load_s,
        "torch": torch.__version__,
        "cuda": bool(torch.cuda.is_available()),
    })

    manifest_jsonl_records: list[dict[str, Any]] = []
    fresh_synth_count = 0
    skip_count = 0
    fail_count = 0
    total_synth_seconds = 0.0
    start_wall = time.monotonic()

    for idx, entry in enumerate(entries, start=1):
        entry_id = entry["id"]
        text = entry["text"]
        category = entry["category"]
        out_path = OUTPUT_DIR / f"{entry_id}.wav"

        # Resume: skip if the file already exists.
        if out_path.is_file():
            skip_count += 1
            duration = _audio_duration_seconds(out_path)
            manifest_jsonl_records.append({
                "id": entry_id,
                "category": category,
                "text": text,
                "audio_path": str(out_path.relative_to(PROJECT)),
                "audio_path_absolute": str(out_path),
                "duration_seconds": duration,
                "synth_seconds": None,  # unknown for resumed entries
                "status": "skipped_existing",
            })
            if idx % 50 == 0 or idx == len(entries):
                elapsed = time.monotonic() - start_wall
                print(f"  [{idx}/{len(entries)}] skip+done ({elapsed:.0f}s wall)")
            continue

        # Fresh synthesis.
        try:
            t0 = time.monotonic()
            tts.tts_to_file(
                text=text,
                speaker_wav=str(REFERENCE_WAV),
                language="en",
                file_path=str(out_path),
                split_sentences=True,
            )
            synth_s = time.monotonic() - t0
            # Edge-trim + fade: removes XTTS autoregressive artifacts
            # (start/end blips, leading silence, trailing glitches)
            # before this clip is added to the Kokoro training set.
            # Cleaner training data -> cleaner Kokoro output.
            _trim_silence_and_fade(out_path)
            total_synth_seconds += synth_s
            fresh_synth_count += 1
            duration = _audio_duration_seconds(out_path)
            manifest_jsonl_records.append({
                "id": entry_id,
                "category": category,
                "text": text,
                "audio_path": str(out_path.relative_to(PROJECT)),
                "audio_path_absolute": str(out_path),
                "duration_seconds": duration,
                "synth_seconds": synth_s,
                "status": "synthesised",
            })
            _append_log({
                "event": "entry_done",
                "id": entry_id,
                "category": category,
                "chars": len(text),
                "synth_seconds": synth_s,
                "duration_seconds": duration,
                "ts": time.time(),
            })
        except Exception as e:
            fail_count += 1
            err_msg = f"{type(e).__name__}: {e}"
            print(f"  [{idx}/{len(entries)}] FAILED {entry_id}: {err_msg}")
            _append_log({
                "event": "entry_failed",
                "id": entry_id,
                "category": category,
                "chars": len(text),
                "error": err_msg,
                "ts": time.time(),
            })
            # Skip from the manifest entirely so downstream training never sees it.
            continue

        # Periodic progress.
        if idx % 25 == 0 or idx == len(entries):
            elapsed = time.monotonic() - start_wall
            done_total = fresh_synth_count + skip_count
            rate = fresh_synth_count / max(total_synth_seconds, 1e-3)
            eta_s = ((len(entries) - idx) / max(rate, 1e-3)) if rate > 0 else 0
            print(
                f"  [{idx}/{len(entries)}] fresh={fresh_synth_count} skip={skip_count} "
                f"fail={fail_count}, wall={elapsed:.0f}s, eta~{eta_s:.0f}s"
            )

    # Emit manifests after the loop. Resume-friendly because we always
    # overwrite the manifest with the union of fresh + previously-existing.
    print("\nWriting manifests...")

    # JSONL (full metadata).
    with MANIFEST_JSONL.open("w", encoding="utf-8") as fh:
        for rec in manifest_jsonl_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  {MANIFEST_JSONL.relative_to(PROJECT)}: {len(manifest_jsonl_records)} entries")

    # CSV (LJSpeech-style: id|audio_path|text). Compatible with most
    # StyleTTS2 / Kokoro fine-tune forks. Use absolute paths so the
    # CSV is portable to a different working directory.
    with MANIFEST_CSV.open("w", encoding="utf-8") as fh:
        for rec in manifest_jsonl_records:
            audio = rec["audio_path_absolute"].replace("\\", "/")
            text = rec["text"].replace("|", " ")  # pipe is the field separator
            fh.write(f"{rec['id']}|{audio}|{text}\n")
    print(f"  {MANIFEST_CSV.relative_to(PROJECT)}: {len(manifest_jsonl_records)} entries")

    # Summary.
    wall = time.monotonic() - start_wall
    print(
        f"\nrun summary: fresh={fresh_synth_count}, skipped={skip_count}, "
        f"failed={fail_count}, wall={wall:.1f}s, total_synth_seconds={total_synth_seconds:.1f}s"
    )
    if torch.cuda.is_available():
        peak = torch.cuda.max_memory_allocated() / 1e6
        print(f"peak VRAM: {peak:.0f} MB")

    _append_log({
        "event": "run_complete",
        "ts": time.time(),
        "fresh": fresh_synth_count,
        "skipped": skip_count,
        "failed": fail_count,
        "wall_seconds": wall,
        "total_synth_seconds": total_synth_seconds,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
