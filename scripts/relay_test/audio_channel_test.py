"""Quick HARDWARE audio-routing test: actually PLAY audio on each channel.

Confirms (audibly / on the Voicemeeter + OBS meters) that:
  * a RELAY    reaches B1 (teammates) + B3 (OBS) + default speakers, and
  * a NON-RELAY reaches B3 (OBS) + default speakers ONLY (never B1).

It plays a real tone through the SAME code the live paths use:
  * B1 + default via ``relay_speech.play_to_device`` (the relay mic write),
  * B3 via the async ``BroadcastSink`` (the OBS mirror path).

Distinct pitch per channel so they're tellable apart if you monitor them.
Run while watching the Voicemeeter "Voicemeeter Input"/"AUX" strip meters + OBS
audio meter; the default-speaker tone you hear directly.

Usage:  python scripts/relay_test/audio_channel_test.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from kenning.audio.broadcast import BroadcastSink                       # noqa: E402
from kenning.audio.devices import resolve_device                       # noqa: E402
from kenning.audio.relay_speech import (                               # noqa: E402
    play_to_device,
    resolve_relay_device,
)
from kenning.config import get_config                                  # noqa: E402

SR = 24000


def _tone(freq: float, seconds: float = 1.1) -> np.ndarray:
    """A clean fading sine -- int16 mono. Fade avoids start/stop clicks."""
    t = np.arange(int(SR * seconds)) / SR
    wave = 0.35 * np.sin(2 * np.pi * freq * t)
    fade = int(SR * 0.04)
    env = np.ones_like(wave)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return (wave * env * 32767).astype(np.int16)


def _play_direct(label: str, idx, freq: float) -> None:
    if idx is None:
        print(f"   [SKIP] {label}: device not resolved")
        return
    print(f"   -> {label} (index {idx}, {freq:.0f} Hz) ...", flush=True)
    play_to_device(_tone(freq), SR, idx)


def _play_broadcast(label: str, idx, freq: float) -> None:
    """Drive B3 through the REAL async BroadcastSink (the OBS mirror path)."""
    if idx is None:
        print(f"   [SKIP] {label}: device not resolved")
        return
    print(f"   -> {label} (index {idx}, {freq:.0f} Hz, via BroadcastSink) ...",
          flush=True)
    sink = BroadcastSink(name="audiotest")
    sink.configure(idx)
    sink.submit(_tone(freq), SR)
    time.sleep(1.4)        # let the consumer thread play it out
    sink.close()


def main() -> None:
    cfg = get_config()
    b1 = resolve_relay_device(getattr(cfg.relay_speech, "output_device", None))
    _b3_spec = getattr(cfg.audio, "broadcast_device", None)
    b3 = resolve_device(_b3_spec, "output") if _b3_spec else None
    _out = getattr(cfg.audio, "output_device", None)
    if _out:
        dflt = resolve_device(_out, "output")
    else:
        import sounddevice as sd
        dflt = sd.default.device[1]

    import sounddevice as sd
    def _name(i):
        try:
            return sd.query_devices(i)["name"] if i is not None else "None"
        except Exception:                                            # noqa: BLE001
            return f"<{i}>"
    print("Resolved channels:")
    print(f"  B1 teammates (relay) : [{b1}] {_name(b1)}")
    print(f"  B3 OBS broadcast     : [{b3}] {_name(b3)}")
    print(f"  default speakers     : [{dflt}] {_name(dflt)}")
    print()

    print("TEST 1 -- RELAY callout: should play on ALL THREE "
          "(teammates hear it + OBS + your speakers)")
    _play_direct("B1 teammates", b1, 523)       # C5
    time.sleep(0.3)
    _play_broadcast("B3 OBS", b3, 659)          # E5
    time.sleep(0.3)
    _play_direct("default speakers", dflt, 784)  # G5  (you HEAR this one)
    print()

    print("TEST 2 -- NON-RELAY (talking to Ultron): should play on B3 + default "
          "ONLY -- B1 (teammates) stays SILENT")
    print("   [B1 teammates: intentionally SKIPPED -- teammates must NOT hear this]")
    _play_broadcast("B3 OBS", b3, 659)
    time.sleep(0.3)
    _play_direct("default speakers", dflt, 784)
    print()
    print("Done. Confirm: TEST 1 moved the B1 + B3 meters (+ you heard the "
          "speaker tone); TEST 2 moved ONLY B3 (+ speakers), B1 meter stayed flat.")


if __name__ == "__main__":
    main()
