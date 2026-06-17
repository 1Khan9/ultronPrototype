r"""End-to-end battery replay through the REAL gaming dispatch + 3B.

Feeds each command (as an STT transcript) through the live routing path:

    normalize_command  ->  match_relay_command  ->  build_relay_line(3B)   [team MIC]
                                              \->  conversational fallback   [desktop]
                                                   (ULTRON_GAMING_PERSONA + 3B)

and records, per command:  raw -> normalized -> ROUTE -> CHANNEL -> spoken line.

The point: prove that (a) every legitimate team command RELAYS as Ultron, (b)
nothing leaks the desktop "Kenning" persona, and (c) the outputs are coherent.
Run with the gaming 3B (GPU for speed -- identical output to the in-game CPU
load). Reads commands from battery_cmds.txt (one per line, '#'/blank ignored).

    .venv\Scripts\python.exe scripts\relay_test\battery_replay.py
"""
from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "relay_test"))

from kenning.audio.command_normalizer import normalize_command            # noqa: E402
from kenning.audio.relay_speech import (                                  # noqa: E402
    match_relay_command,
    build_relay_line,
)
from harness import _load_llm                                             # noqa: E402

# The real gaming persona (fall back to an inline copy if the orchestrator import
# is too heavy / has side effects in this harness context).
try:
    from kenning.pipeline.orchestrator import ULTRON_GAMING_PERSONA       # noqa: E402
except Exception:                                                         # noqa: BLE001
    ULTRON_GAMING_PERSONA = (
        "You are Ultron, speaking OUT LOUD into a live Valorant voice chat. "
        "Reply in ONE short sentence, cold and clinical, as Ultron."
    )

_CONV_SAMPLING = {
    "max_tokens": 60, "temperature": 0.8, "top_p": 0.92, "top_k": 40,
    "min_p": 0.08, "repeat_penalty": 1.18,
    "stop": ["\n\n", "\nUser:", "\nUSER:", "Ultron:"],
}


def _conversational(llm, user_text: str) -> str:
    """Mirror the orchestrator's gaming conversational fallback."""
    try:
        toks = llm.generate_stream(
            user_text, system_prompt=ULTRON_GAMING_PERSONA,
            sampling=_CONV_SAMPLING, record_history=False,
            suppress_memory_context=True, enable_thinking=False,
        )
        return "".join(toks).strip()
    except Exception as e:                                                # noqa: BLE001
        return f"<conv-error: {e}>"


def main() -> None:
    cmds_path = ROOT / "scripts" / "relay_test" / "battery_cmds.txt"
    lines = [ln.strip() for ln in cmds_path.read_text(encoding="utf-8").splitlines()]
    cmds = [ln for ln in lines if ln and not ln.startswith("#")]

    print(f"[battery] {len(cmds)} commands; loading gaming 3B...", flush=True)
    llm = _load_llm()
    print("[battery] 3B ready; replaying...\n", flush=True)

    recent: deque = deque(maxlen=8)
    out_lines: list[str] = []
    n_desktop = 0
    for i, raw in enumerate(cmds, 1):
        norm = normalize_command(raw)
        cmd = match_relay_command(norm)
        if cmd is not None:
            line = build_relay_line(cmd, llm=llm, recent_lines=list(recent))
            ch = "team_mic" if (getattr(cmd, "addressee", "team") or "team") else "team_mic"
            route = "RELAY"
            if getattr(cmd, "compose", False):
                route = f"RELAY/compose:{getattr(cmd, 'directive', '') or ''}"
            addr = getattr(cmd, "addressee", "team")
            recent.append(line)
        else:
            line = _conversational(llm, norm)
            ch = "DESKTOP"
            route = "CONVERSATIONAL"
            addr = "-"
            n_desktop += 1
        block = (f"[{i}] RAW : {raw}\n"
                 f"    NORM: {norm}\n"
                 f"    RT  : {route} | ch={ch} | addr={addr}\n"
                 f"    OUT : {line}\n")
        out_lines.append(block)
        print(block, flush=True)

    summary = (f"\n=== SUMMARY: {len(cmds)} cmds | "
               f"{n_desktop} -> DESKTOP conversational | "
               f"{len(cmds) - n_desktop} -> RELAY ===\n")
    print(summary, flush=True)
    out_path = ROOT / "logs" / "_battery_replay.txt"
    out_path.write_text("".join(out_lines) + summary, encoding="utf-8")
    print(f"[battery] wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
