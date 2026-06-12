"""Live smoke test for the XTTS v3 TTS engine.

Spawns the XTTS HTTP server, runs warmup + a single synth call, then
shuts down. Verifies end-to-end:

    Orchestrator-side XttsV3Speech
        -> spawns xtts_server.py in .venv-xtts
        -> POST /synthesize
        -> receives streamed PCM
        -> applies v3 Ultron filter via main-venv pedalboard
        -> returns int16 clip ready for the playback path

Does NOT play audio (no speaker access); writes the synthesised clip
to disk so a human can listen separately.

Run from the worktree (so src/ is on the path):

    python scripts/smoke_xtts_v3.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure the worktree's src/ is on the path (consistent with the test
# conftest pattern; this is a script not a test so we set it manually).
HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parent
sys.path.insert(0, str(WORKTREE / "src"))
sys.path.insert(0, str(WORKTREE))


def main() -> int:
    from ultron.config import get_config, load_config

    cfg_path = WORKTREE / "config.yaml"
    cfg = load_config(str(cfg_path))
    print(f"loaded config: tts.engine = {cfg.tts.engine!r}")

    # Force xtts_v3 + point at the audio-prep paths in the MAIN
    # checkout (the .venv-xtts and reference audio live next to the
    # main config.yaml, not under the worktree).
    from ultron.config import set_config
    cfg.tts.engine = "xtts_v3"
    main_checkout = Path("C:/STC/ultronPrototype")
    cfg.tts.xtts_v3.server_python = str(
        main_checkout / "ultronVoiceAudio" / ".venv-xtts" / "Scripts" / "python.exe"
    )
    cfg.tts.xtts_v3.server_script = str(
        main_checkout / "ultronVoiceAudio" / "scripts" / "xtts_server.py"
    )
    cfg.tts.xtts_v3.reference_audio = str(
        main_checkout / "ultronVoiceAudio" / "kokoro training audio" / "Ultron_vocals_mono_v1.wav"
    )
    set_config(cfg)

    from ultron.tts.xtts_v3 import XttsV3Speech

    print(f"\nXTTS paths (overridden to main checkout):")
    print(f"  server_python   = {cfg.tts.xtts_v3.server_python}")
    print(f"  server_script   = {cfg.tts.xtts_v3.server_script}")
    print(f"  reference_audio = {cfg.tts.xtts_v3.reference_audio}")

    print("\n=== Constructing XttsV3Speech (spawns server, waits for /healthz) ===")
    t0 = time.monotonic()
    tts = XttsV3Speech()
    print(f"engine ready in {time.monotonic()-t0:.1f}s")

    print("\n=== warmup ===")
    t0 = time.monotonic()
    tts.warmup()
    print(f"warmup in {time.monotonic()-t0:.1f}s")

    print("\n=== _synthesize sample ===")
    text = "Acknowledged. Initiating the requested operation."
    t0 = time.monotonic()
    pcm, sr = tts._synthesize(text)
    elapsed = time.monotonic() - t0
    audio_dur = pcm.shape[0] / max(sr, 1)
    print(
        f"synth ok: {pcm.shape[0]} samples ({audio_dur:.2f}s) @ {sr} Hz "
        f"in {elapsed*1000:.0f} ms (RTF {elapsed/max(audio_dur,1e-6):.2f})"
    )

    out_path = WORKTREE.parent / "ultronVoiceAudio" / "smoke_xtts_v3_output.wav"
    out_path.parent.mkdir(exist_ok=True)
    import soundfile as sf
    sf.write(str(out_path), pcm, sr, subtype="PCM_16")
    print(f"  wrote {out_path}")

    print("\n=== shutdown ===")
    tts._stop_server_subprocess()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
