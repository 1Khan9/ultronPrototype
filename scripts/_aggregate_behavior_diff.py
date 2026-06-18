"""End-to-end BEHAVIORAL diff harness for the aggregate refactor (2026-06-18).

Runs a fixed corpus through the DETERMINISTIC pipeline surface and dumps a stable
JSON so the SAME corpus can be replayed at the pre-aggregate baseline (21f3c7e)
and at HEAD and diffed. A zero-diff proves the aggregate batch is 1:1 on
behavior/response/routing for existing inputs; any diff is a finding.

Surface captured per line (the deterministic, aggregate-touched path):
  raw -> _stt_correct.correct_callout_stt -> command_normalizer.normalize_command
      -> relay_speech.match_relay_command -> relay_route_info + build_relay_line

Determinism: line/flavor selection (_pick_lru) is monkeypatched to first-candidate
and random is seeded + LRU state reset PER LINE, so output depends only on the
matched pool + path (pools are byte-proven identical by the golden harness). The
LLM is stubbed to a fixed sentinel so a relay that falls through to the 3B yields
a stable marker (we compare the ROUTING decision, not LLM text). Version-agnostic:
new-feature symbols absent at baseline are recorded as null.

Usage:
  KENNING_ROUTER_WAIT_SECONDS=0 python scripts/_aggregate_behavior_diff.py <corpus> <out.json>
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for p in (_ROOT, _ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")

from kenning.audio import _stt_correct, command_normalizer, relay_speech  # noqa: E402


def _stub_llm(prompt):  # deterministic stand-in for the 3B rephrase
    return "<<LLM>>"


def _det_pick(candidates, rng=None):
    """Deterministic selection: first candidate (pools have stable order)."""
    try:
        seq = list(candidates)
    except TypeError:
        return candidates
    return seq[0] if seq else ""


# Force deterministic selection everywhere it routes through the LRU core.
if hasattr(relay_speech, "_pick_lru"):
    relay_speech._pick_lru = _det_pick


def _reset_selection_state():
    random.seed(20260618)
    for nm in ("_LRU_COUNT",):
        v = getattr(relay_speech, nm, None)
        if isinstance(v, list) and v:
            v[0] = 0
    seen = getattr(relay_speech, "_LRU_SEEN", None)
    if isinstance(seen, dict):
        seen.clear()


def _cmd_fields(cmd):
    if cmd is None:
        return None
    return {
        "addressee": getattr(cmd, "addressee", None),
        "payload": getattr(cmd, "payload", None),
        "directive": getattr(cmd, "directive", None),
        "compose": getattr(cmd, "compose", None),
        "context": getattr(cmd, "context", None),
    }


def _record(raw: str) -> dict:
    rec: dict = {"raw": raw}
    try:
        stt = _stt_correct.correct_callout_stt(raw)
    except Exception as e:  # noqa: BLE001
        rec["stt_error"] = repr(e)
        stt = raw
    rec["stt"] = stt
    try:
        norm = command_normalizer.normalize_command(stt)
    except Exception as e:  # noqa: BLE001
        rec["norm_error"] = repr(e)
        norm = stt
    rec["norm"] = norm
    try:
        cmd = relay_speech.match_relay_command(norm)
    except Exception as e:  # noqa: BLE001
        rec["match_error"] = repr(e)
        cmd = None
    rec["cmd"] = _cmd_fields(cmd)
    if cmd is not None:
        try:
            rec["route"] = relay_speech.relay_route_info(cmd)
        except Exception as e:  # noqa: BLE001
            rec["route_error"] = repr(e)
        _reset_selection_state()
        try:
            rec["line"] = relay_speech.build_relay_line(
                cmd, None, rephrase=True, generate_fn=_stub_llm,
            )
        except Exception as e:  # noqa: BLE001
            rec["line_error"] = repr(e)
    return rec


def main() -> int:
    corpus_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    lines = [ln.rstrip("\n") for ln in corpus_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    out = [_record(ln) for ln in lines]
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(out)} records to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
