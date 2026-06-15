"""Manual auto-PTT hardware test -- run WHILE Valorant is open.

WHY THIS EXISTS: a USB-HID keypress that works perfectly at the OS level (types
into Notepad) can still be dropped by Vanguard once Valorant boots -- so testing
outside the game is NOT representative. This isolates the PTT key-hold (no Ultron
audio, no pipeline) so you can see, inside Valorant, whether holding the team-PTT
key via the Leonardo actually makes the game transmit.

USAGE (from the repo root):
    .venv\\Scripts\\python.exe scripts\\ptt_test.py            # 5 cycles, 3s hold
    .venv\\Scripts\\python.exe scripts\\ptt_test.py --hold 4 --cycles 8
    .venv\\Scripts\\python.exe scripts\\ptt_test.py --port COM5

WHAT TO WATCH (two independent signals so we can localize any failure):
  1. The Leonardo's onboard LED -- it lights while the key is HELD. That proves
     the firmware received the command and is asserting the key. (Hardware OK.)
  2. Inside Valorant (open a custom game / the Range, or the mic test), watch the
     team-voice "transmitting" indicator. It should light in sync with the LED,
     and an OBS recording / a teammate should hear your mic.

DIAGNOSIS:
  * LED lights AND Valorant transmits in sync  -> Tier C works on this rig. Done.
  * LED lights BUT Valorant shows NO transmit   -> Vanguard is dropping the input
    (the composite HID-keyboard+serial device is distrusted). This is the known
    failure mode -> we pivot to the relay-across-a-real-key build (Tier B).
  * LED does NOT light                          -> firmware/serial issue, not
    Vanguard; re-flash / check the port.

First do a BASELINE run with Notepad focused to confirm the key types at the OS
level, THEN alt-tab into Valorant and run it again to see if Vanguard interferes.
"""
import argparse
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser(description="Manual auto-PTT hardware test")
    ap.add_argument("--hold", type=float, default=3.0, help="seconds to hold the key per cycle")
    ap.add_argument("--gap", type=float, default=2.0, help="seconds between cycles")
    ap.add_argument("--cycles", type=int, default=5, help="number of hold/release cycles")
    ap.add_argument("--countdown", type=float, default=4.0, help="seconds before starting (alt-tab to Valorant)")
    ap.add_argument("--port", default=None, help="COM port (default: auto-detect the Arduino)")
    ap.add_argument("--baud", type=int, default=9600)
    args = ap.parse_args()

    from kenning.ptt.backends import SerialHidPttBackend, find_arduino_port

    port = args.port or find_arduino_port()
    if not port:
        print("ERROR: no Arduino found. Plug in the Leonardo (or pass --port).")
        return 1

    backend = SerialHidPttBackend(port, args.baud)
    if not backend.available:
        print(f"ERROR: could not open {port}. Is another process holding it?")
        return 1

    print(f"PTT test on {port}: {args.cycles} cycles, hold {args.hold}s, gap {args.gap}s.")
    print("ALT-TAB to Valorant now (mic test / custom game) and watch the transmit")
    print("indicator + the Leonardo's onboard LED.\n")
    for i in range(int(args.countdown), 0, -1):
        print(f"  starting in {i}...", end="\r", flush=True)
        time.sleep(1.0)
    print(" " * 30, end="\r")

    try:
        for c in range(1, args.cycles + 1):
            print(f"[{c}/{args.cycles}] HOLD    key down  (LED ON)  ...", flush=True)
            backend.press()
            t_end = time.monotonic() + args.hold
            while time.monotonic() < t_end:
                backend.heartbeat()          # keep the firmware deadman fresh
                time.sleep(0.05)
            backend.release()
            print(f"          RELEASE key up    (LED OFF)", flush=True)
            if c < args.cycles:
                time.sleep(args.gap)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        backend.close()

    print("\nDone. If Valorant's transmit indicator lit in sync with the LED, the")
    print("full PTT path works through Vanguard. If the LED lit but Valorant never")
    print("transmitted, Vanguard is dropping the input -> tell me and we pivot to")
    print("the relay-across-a-real-key build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
