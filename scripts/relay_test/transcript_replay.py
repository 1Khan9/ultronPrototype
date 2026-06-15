"""Replay REAL test-drive STT transcripts through the LEAN-BOOT dispatch.

Every line the user actually spoke was transcribed by Whisper and logged as
``routing:normalized | raw='...'``. Those raw strings are EXACTLY what the live
mic->STT pipeline produces, so replaying them through the normalizer + the
deterministic matchers is a faithful test of routing WITHOUT needing the mic or
a running model.

For each transcript this prints:
  raw  ->  normalized  ->  ROUTE  ->  DEVICE  [-> deterministic line]

ROUTE / DEVICE mirror the lean-boot run loop order (orchestrator.py):
  1. lean Spotify   (match_spotify_command)      -> DESKTOP  (private)
  2. deterministic relay (match_relay_command)   -> MIC+OBS  (team hears)
  3. else                                        -> ROUTER/LLM -> DESKTOP (private)

The CRITICAL property checked: the team MIC (device 19) must carry ONLY relay
routes. Anything the user says just TO Ultron (questions, banter, Spotify, a bare
identity probe) must land on DESKTOP (device 15) and never reach teammates.

Usage:
    python -m scripts.relay_test.transcript_replay [path-to-log]
    (defaults to logs/_td_compact.txt)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
# The editable install (.pth) puts ``kenning`` (src/) on the path already; the
# repo ROOT is needed for the top-level ``config`` package kenning.audio imports.
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from kenning.audio.command_normalizer import normalize_command          # noqa: E402
from kenning.audio._stt_correct import correct_callout_stt              # noqa: E402
from kenning.audio.relay_speech import (                                # noqa: E402
    build_relay_line,
    match_relay_command,
)
from kenning.spotify.voice import match_spotify_command                 # noqa: E402

# Device map (from config / monitor wiring).
MIC = "MIC(19)+OBS(25)+mon(15)"   # teammates hear this
DESKTOP = "DESKTOP(15)"           # only the user hears this

_RAW_RE = re.compile(r"raw='((?:[^'\\]|\\.)*)'")


def _strip_wake(s: str) -> str:
    """Mirror orchestrator._strip_leading_wake_remnant (lightweight copy)."""
    return re.sub(
        r"^\s*(?:ultron|altron|voltron|ultra|ultro|tron|ron|run|one|"
        r"yeah|so|um+|uh+)\b[\s,.:;-]*(?:to|and|then)?\s*",
        "", s, count=1, flags=re.IGNORECASE,
    ).strip() or s


def _relay_match(normalized: str):
    """Mirror _maybe_handle_relay_speech's progressive variant matching."""
    stripped = _strip_wake(normalized)
    variants = [normalized]
    for v in (correct_callout_stt(stripped),
              correct_callout_stt(normalized), stripped):
        if v and v not in variants:
            variants.append(v)
    for v in variants:
        cmd = match_relay_command(v)
        if cmd is not None:
            return cmd
    return None


def classify(raw: str):
    """Return (normalized, route, device, line)."""
    normalized = normalize_command(raw)
    # 1. lean Spotify (private -> desktop)
    sp = match_spotify_command(normalized)
    if sp is None:
        sp = match_spotify_command(_strip_wake(normalized))
    if sp is not None:
        return normalized, f"spotify:{sp.action}", DESKTOP, ""
    # 2. deterministic relay (team -> mic)
    cmd = _relay_match(normalized)
    if cmd is not None:
        try:
            line = build_relay_line(cmd, generate_fn=lambda p: [])
        except Exception as e:                                       # noqa: BLE001
            line = f"<build error: {e}>"
        kind = "relay"
        if getattr(cmd, "roast", False):
            kind = "relay:roast"
        elif getattr(cmd, "directive", None):
            kind = f"relay:{cmd.directive}"
        elif getattr(cmd, "addressee", "team") != "team":
            kind = f"relay->{cmd.addressee}"
        return normalized, kind, MIC, line
    # 3. fallthrough -> router (fuzzy) / conversational LLM -> desktop
    return normalized, "conversational", DESKTOP, ""


def main() -> None:
    log = Path(sys.argv[1]) if len(sys.argv) > 1 else _REPO / "logs" / "_td_compact.txt"
    seen: list[str] = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "routing:normalized" not in line:
            continue
        m = _RAW_RE.search(line)
        if m:
            raw = m.group(1).encode().decode("unicode_escape")
            seen.append(raw)
    print(f"# {len(seen)} transcripts from {log.name}\n")
    counts: dict[str, int] = {}
    for raw in seen:
        normalized, route, device, line = classify(raw)
        bucket = route.split(":")[0].split("->")[0]
        counts[bucket] = counts.get(bucket, 0) + 1
        tag = "MIC " if device == MIC else "priv"
        extra = f"  | {line}" if line else ""
        print(f"[{tag}] {raw!r}")
        if normalized != raw:
            print(f"        norm: {normalized!r}")
        print(f"        -> {route}  [{device}]{extra}")
    print("\n# route counts:", counts)


if __name__ == "__main__":
    main()
