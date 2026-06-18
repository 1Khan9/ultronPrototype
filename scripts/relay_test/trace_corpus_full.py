#!/usr/bin/env python
"""FULL-STAGE corpus tracer for the by-hand 25k audit (2026-06-18).

Extends trace_corpus.py to log EVERY stage the audit reads, in order, so each
case can be reviewed line-by-line without guessing:

  text    -- simulated transcription input (the raw STT string)
  stt1    -- NORM LAYER 1: kenning.audio._stt_correct.correct_callout_stt(text)
             (Valorant vocab + agent-name correction)
  norm2   -- NORM LAYER 2 (full normalize): command_normalizer.normalize_command(text)
             (re-applies STT-correct + relay-lead recovery + disfluency + gates)
  router  -- ROUTING/SEMANTICS: command_router.route(norm2) -> family / abstained /
             confidence / margin / reason / scores  (the coarse semantic decision;
             captured best-effort -- needs the embedder sidecar for the hybrid
             backend, else the lexical decision is recorded + backend noted)
  match   -- the STRICT relay matcher: match_relay_command(norm2) -> RelayCommand
             (payload/addressee/compose/verbatim/directive/context) or None
  route   -- WHICH build_relay_line branch fires + a short reason (the dispatch /
             tail-selection decision)
  snap    -- the deterministic SNAP string (the bare callout, no tail)
  tail    -- the flavor TAIL appended after the snap
  llm_*   -- for the answer (Marvel / think-respond) path: the assembled system +
             user prompt + subtype (so prompt quality is auditable)
  final   -- the SPOKEN line: deterministic snap+tail / curated pool / fallback;
             llm_path=True flags cases that fall to the 3B (only the prompt +
             deterministic fallback are shown -- no 25k LLM calls)

Usage:
  RELAY_CORPUS_SEED=<n> RELAY_CORPUS_TARGET=25000 \
  KENNING_ROUTER_WAIT_SECONDS=<sidecar wait> \
  python scripts/relay_test/trace_corpus_full.py [out.jsonl]
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
from kenning.audio._stt_correct import correct_callout_stt  # noqa: E402
from kenning.audio.command_normalizer import normalize_command  # noqa: E402
from kenning.audio import relay_speech as RS     # noqa: E402
from kenning.audio.relay_speech import (         # noqa: E402
    match_relay_command, build_relay_line,
)
from kenning.audio._ultron_answer import build_answer_call  # noqa: E402
from kenning.audio._ultron_social import classify_social_reaction  # noqa: E402

# Optional: the semantic router (needs the embedder sidecar for the hybrid
# backend; falls back to lexical). Captured best-effort; never aborts the trace.
_ROUTER = None
_ROUTER_BACKEND = None
if os.environ.get("TRACE_WITH_ROUTER", "1").strip().lower() not in ("0", "false", "no"):
    try:
        from kenning.audio.command_router import get_command_router
        _ROUTER = get_command_router()
        _ROUTER_BACKEND = getattr(getattr(_ROUTER, "backend", None), "name", None)
    except Exception as e:  # noqa: BLE001
        _ROUTER = None
        _ROUTER_BACKEND = f"<unavailable: {e}>"


def _snap_only(cmd):
    fn = getattr(RS, "_as_snap_callout", None)
    if fn is None or cmd is None:
        return None
    if getattr(cmd, "compose", False) or getattr(cmd, "context", None) \
            or getattr(cmd, "verbatim", False):
        return None
    try:
        return fn(cmd, None, flavor=False)
    except Exception:  # noqa: BLE001
        return None


def _route_info(cmd) -> dict:
    info = {"route": "unknown", "reason": "", "subtype": None}
    if cmd is None:
        info.update(route="no_match", reason="match_relay_command returned None")
        return info
    try:
        if getattr(cmd, "verbatim", False):
            info.update(route="verbatim", reason="verbatim demand -> speak payload as-is")
            return info
        if RS._as_curated_command(cmd):
            info.update(route="curated_command", reason="payload matched a curated COMMAND pattern")
            return info
        rc = RS._as_curated_reaction(cmd)
        if rc:
            cat = (classify_social_reaction(getattr(cmd, "context", "") or "")
                   or classify_social_reaction(getattr(cmd, "payload", "") or ""))
            info.update(route=f"curated_reaction:{cat}", reason="reported social reaction -> curated pool")
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
        info.update(route="relay_llm", reason="off-snap tactical/banter -> generic LLM relay prompt")
    except Exception as e:  # noqa: BLE001
        info.update(route="route_err", reason=str(e))
    return info


def _router_decision(text: str):
    if _ROUTER is None:
        return None
    try:
        rd = _ROUTER.route(text)
        return {
            "family": getattr(rd, "family", None),
            "abstained": getattr(rd, "abstained", None),
            "routed": getattr(rd, "routed", None),
            "confidence": round(float(getattr(rd, "confidence", 0.0)), 4),
            "margin": round(float(getattr(rd, "margin", 0.0)), 4),
            "reason": getattr(rd, "reason", ""),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def main() -> int:
    seed = int(os.environ.get("RELAY_CORPUS_SEED", "0") or "0")
    target = int(os.environ.get("RELAY_CORPUS_TARGET", "25000") or "25000")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        _ROOT / "logs" / "relay_test" / "trace_full_25k.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = build_corpus(seed, target)
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for c in cases:
            rec = {"i": n, "text": c.text, "category": c.category,
                   "expect_match": c.expect_match}
            try:
                rec["stt1"] = correct_callout_stt(c.text)
            except Exception as e:  # noqa: BLE001
                rec["stt1"] = f"<STT_ERR {e}>"
            try:
                n2 = normalize_command(c.text)
            except Exception as e:  # noqa: BLE001
                n2 = f"<NORM_ERR {e}>"
            rec["norm2"] = n2
            cmd = None
            try:
                cmd = match_relay_command(n2)
            except Exception as e:  # noqa: BLE001
                rec["route_err"] = str(e)
            rec["matched"] = cmd is not None
            # Semantic router decision (what the LLM-fallthrough path would see).
            if cmd is None:
                rec["router"] = _router_decision(n2)
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
                try:
                    ans = build_answer_call(cmd)
                    if ans is not None:
                        rec["llm_system"] = ans[0]
                        rec["llm_user"] = ans[1]
                except Exception:  # noqa: BLE001
                    pass
                try:
                    line = build_relay_line(cmd, llm=None, rephrase=False, recent_lines=None)
                except Exception as e:  # noqa: BLE001
                    line = f"<LINE_ERR {e}>"
                rec["final"] = line
                if snap and isinstance(line, str) and line.startswith(snap):
                    rec["tail"] = line[len(snap):].strip()
                rec["llm_path"] = ri["route"] in ("relay_llm", "compose_llm") \
                    or ri["route"].startswith("answer:")
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            if n % 2500 == 0:
                print(f"  ...{n}", flush=True)
    pos = sum(1 for c in cases if c.expect_match)
    print(f"traced {n} cases (seed {seed}, target {target}, expect_match={pos}, "
          f"router_backend={_ROUTER_BACKEND}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
