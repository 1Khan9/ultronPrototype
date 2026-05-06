"""List input/output audio devices visible to sounddevice.

Use this to find a device name you can pass via ``ULTRON_AUDIO_DEVICE`` or
``ULTRON_AUDIO_OUTPUT_DEVICE`` in ``.env`` if the system defaults are wrong.
"""

from __future__ import annotations

import sounddevice as sd


def main() -> int:
    print("\nAudio devices visible to sounddevice:\n")
    devices = sd.query_devices()
    default_in, default_out = sd.default.device
    for idx, dev in enumerate(devices):
        kind_bits = []
        if dev["max_input_channels"] > 0:
            kind_bits.append(f"in={dev['max_input_channels']}")
        if dev["max_output_channels"] > 0:
            kind_bits.append(f"out={dev['max_output_channels']}")
        flags = []
        if idx == default_in:
            flags.append("DEFAULT-IN")
        if idx == default_out:
            flags.append("DEFAULT-OUT")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(
            f"  [{idx:>2}] {dev['name']}"
            f"  ({', '.join(kind_bits)})  @ {int(dev['default_samplerate'])} Hz"
            f"{flag_str}"
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
