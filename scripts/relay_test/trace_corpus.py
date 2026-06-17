#!/usr/bin/env python
"""Full-pipeline tracer for the relay corpus -- regenerates the corpus through the
CURRENT system and logs EVERY stage of every case so the whole corpus can be read
case-by-case:

  transcription (raw)
    -> norm1   (normalize_command: STT-correct + relay-lead recovery + gates)
    -> routing (match_relay_command -> RelayCommand: payload/addressee/flags)
    -> route   (WHICH dispatch branch fired in build_relay_line, + a short reason)
    -> norm2   (the deterministic SNAP string, payload -> snap)
    -> tail    (the flavor TAIL appended after the snap)
    -> answer  (for the Marvel / think-and-respond LLM pipeline: the assembled
                system + user prompt + subtype, so prompt quality is auditable)
    -> final   (the spoken line: deterministic snap+tail / curated / fallback)

Deterministic (no LLM): snap callouts + curated pools produce their REAL spoken
line; off-snap cases that need the 3B are flagged ``llm_path`` and show the
assembled prompt + the deterministic fallback. This keeps a 25k trace fast while
showing every callout+tail pairing AND every routing decision -- the focus of the
audit.

Usage: RELAY_CORPUS_SEED=0 .venv/Scripts/python.exe scripts/relay_test/trace_corpus.py [out.jsonl]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
sys.path.insert(0, str(_HERE))                 # corpus_packs / corpus
sys.path.insert(0, str(_ROOT / "src"))         # kenning
sys.path.insert(0, str(_ROOT))                 # top-level `config` package

from corpus_packs import build_corpus           # noqa: E402
from kenning.audio.command_normalizer import normalize_command  # noqa: E402
from kenning.audio import relay_speech as RS     # noqa: E402
from kenning.audio.relay_speech import (         # noqa: E402
    match_relay_command, build_relay_line,
)
from kenning.audio._ultron_answer import build_answer_call  # noqa: E402
from kenning.audio._ultron_social import classify_social_reaction  # noqa: E402


def _snap_only(cmd):
    """Bare snap (norm2 output) WITHOUT the flavor tail -- _as_snap_callout takes
    the COMMAND and flavor=False yields the literal callout."""
    fn = getattr(RS, "_as_snap_callout", None)
    if fn is None or cmd is None:
        return None
    if getattr(cmd, "compose", False) or getattr(cmd, "context", None) \
            or getattr(cmd, "verbatim", False):
        return None
    try:
        return fn(cmd, None, flavor=False)
    except Exception:                                            # noqa: BLE001
        return None


def _route_info(cmd) -> dict:
    """Classify which build_relay_line branch produces this command's line, with a
    short reason -- mirrors the dispatch order in build_relay_line. Best-effort,
    fail-open (a classification error never aborts the trace)."""
    info = {"route": "unknown", "reason": "", "subtype": None}
    if cmd is None:
        info.update(route="no_match", reason="match_relay_command returned None")
        return info
    try:
        if getattr(cmd, "verbatim", False):
            info.update(route="verbatim", reason="verbatim demand -> speak payload as-is")
            return info
        if RS._as_curated_command(cmd):
            info.update(route="curated_command",
                        reason="payload matched a curated COMMAND pattern")
            return info
        rc = RS._as_curated_reaction(cmd)
        if rc:
            cat = (classify_social_reaction(getattr(cmd, "context", "") or "")
                   or classify_social_reaction(getattr(cmd, "payload", "") or ""))
            info.update(route=f"curated_reaction:{cat}",
                        reason="reported social reaction -> curated pool")
            return info
        ans = build_answer_call(cmd)
        if ans is not None:
            info.update(route=f"answer:{ans[3]}", subtype=ans[3],
                        reason="Marvel / think-and-respond -> LLM answer pipeline")
            return info
        ctx = getattr(cmd, "context", "") or ""
        pl = getattr(cmd, "payload", "") or ""
        if RS._is_identity_question(ctx) or RS._is_identity_question(pl):
            info.update(route="identity", reason="identity question -> IDENTITY_POOLS")
            return info
        d = getattr(cmd, "directive", None) or ""
        if d.startswith("criticize:"):
            info.update(route="criticize", reason="criticize named teammate")
            return info
        if getattr(cmd, "compose", False) and d in RS._DIRECTIVE_POOLS:
            info.update(route=f"directive_pool:{d}", reason="greet/farewell set-piece")
            return info
        if getattr(cmd, "compose", False):
            info.update(route="compose_llm", reason="compose -> LLM (morale/other)")
            return info
        snap = _snap_only(cmd)
        if snap is not None:
            info.update(route="snap", reason="deterministic snap callout")
            return info
        info.update(route="relay_llm",
                    reason="off-snap tactical/banter -> generic LLM relay prompt")
    except Exception as e:                                       # noqa: BLE001
        info.update(route="route_err", reason=str(e))
    return info


def main() -> int:
    seed = int(os.environ.get("RELAY_CORPUS_SEED", "0") or "0")
    target = int(os.environ.get("RELAY_CORPUS_TARGET", "25000") or "25000")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        _ROOT / "logs" / "relay_test" / "trace_full.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = build_corpus(seed, target)
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for c in cases:
            rec = {"text": c.text, "category": c.category,
                   "expect_match": c.expect_match}
            try:
                n1 = normalize_command(c.text)
            except Exception as e:                               # noqa: BLE001
                n1 = f"<NORM_ERR {e}>"
            rec["norm1"] = n1
            cmd = None
            try:
                cmd = match_relay_command(n1)
            except Exception as e:                               # noqa: BLE001
                rec["route_err"] = str(e)
            rec["matched"] = cmd is not None
            ri = _route_info(cmd)
            rec.update(route=ri["route"], reason=ri["reason"])
            if ri["subtype"]:
                rec["subtype"] = ri["subtype"]
            if cmd is not None:
                rec["payload"] = getattr(cmd, "payload", None)
                rec["addressee"] = getattr(cmd, "addressee", None)
                rec["compose"] = getattr(cmd, "compose", None)
                rec["verbatim"] = getattr(cmd, "verbatim", None)
                rec["directive"] = getattr(cmd, "directive", None)
                rec["context"] = getattr(cmd, "context", None)
                snap = _snap_only(cmd)
                rec["snap"] = snap
                # Capture the assembled answer prompt (Marvel / think-respond).
                try:
                    ans = build_answer_call(cmd)
                    if ans is not None:
                        rec["llm_system"] = ans[0]
                        rec["llm_user"] = ans[1]
                except Exception:                                # noqa: BLE001
                    pass
                try:
                    line = build_relay_line(cmd, llm=None, rephrase=False,
                                            recent_lines=None)
                except Exception as e:                           # noqa: BLE001
                    line = f"<LINE_ERR {e}>"
                rec["final"] = line
                # tail = the flavor appended after the bare snap (if snap-routed).
                if snap and isinstance(line, str) and line.startswith(snap):
                    rec["tail"] = line[len(snap):].strip()
                rec["llm_path"] = ri["route"] in ("relay_llm", "compose_llm") \
                    or ri["route"].startswith("answer:")
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n % 2500 == 0:
                print(f"  ...{n}", flush=True)
    pos = sum(1 for c in cases if c.expect_match)
    print(f"traced {n} cases (seed {seed}, target {target}, expect_match={pos}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
