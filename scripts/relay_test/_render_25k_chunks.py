"""Render the 25k full-stage trace into DENSE, COMPLETE, scannable per-case lines
for the by-hand line-by-line audit. One line per case; every NON-trivial stage is
shown. A normalization layer that left the text unchanged is shown by ABSENCE
(no `norm=`/`s1=` field) -- a no-op has nothing to flag. So every meaningful
transform, the routing/match decision, the snap+tail, and the final spoken line
are all visible, while unchanged passthrough stays terse. 1000 cases per chunk.

Usage: python scripts/relay_test/_render_25k_chunks.py [trace.jsonl] [outdir] [chunk_size]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

trace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs/relay_test/trace_full_25k.jsonl")
outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("logs/relay_test/_25k_chunks")
chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
outdir.mkdir(parents=True, exist_ok=True)


def q(s):
    return repr(s) if s is not None else "None"


def render(r: dict) -> str:
    text = r.get("text", "")
    stt1 = r.get("stt1", "")
    norm2 = r.get("norm2", "")
    flags = ""
    if r.get("llm_path"):
        flags += "!LLM"
    if not r.get("matched"):
        flags += "!NM"
    parts = [f"#{r.get('i')} {r.get('category')} {r.get('route')}{(' '+flags) if flags else ''}"]
    parts.append(f"T={q(text)}")
    # norm-layer-1 (correct_callout_stt) shown only when it changed the text.
    if stt1 != text:
        parts.append(f"s1={q(stt1)}")
    # norm-layer-2 (normalize_command) shown only when it differs from the raw
    # text (it internally re-applies stt-correct, so when it differs from s1 too
    # that's the lead-recovery/disfluency work).
    if norm2 != text:
        parts.append(f"norm={q(norm2)}")
    if r.get("matched"):
        cmd = [f"addr={q(r.get('addressee'))}", f"pay={q(r.get('payload'))}"]
        if r.get("compose"):
            cmd.append("comp=T")
        if r.get("verbatim"):
            cmd.append("verb=T")
        if r.get("directive"):
            cmd.append(f"dir={q(r.get('directive'))}")
        if r.get("context"):
            cmd.append(f"ctx={q(r.get('context'))}")
        parts.append("cmd[" + " ".join(cmd) + "]")
    else:
        rt = r.get("router")
        if rt:
            if "error" in rt:
                parts.append(f"router=ERR:{rt['error']}")
            else:
                parts.append(f"router={rt.get('family')}/abst={rt.get('abstained')}"
                             f"/c={rt.get('confidence')}/m={rt.get('margin')}")
    if r.get("snap"):
        parts.append(f"snap={q(r.get('snap'))}//tail={q(r.get('tail'))}")
    if r.get("subtype"):
        parts.append(f"sub={r.get('subtype')}")
    if "final" in r:
        parts.append(f"F={q(r.get('final'))}")
    return "  ¦  ".join(parts)


recs = [json.loads(l) for l in open(trace, encoding="utf-8")]
n = len(recs)
nchunks = (n + chunk - 1) // chunk
for ci in range(nchunks):
    lo, hi = ci * chunk, min((ci + 1) * chunk, n)
    body = "\n".join(render(recs[i]) for i in range(lo, hi))
    p = outdir / f"chunk_{ci:03d}_cases_{lo}-{hi-1}.txt"
    p.write_text(body + "\n", encoding="utf-8")
print(f"rendered {n} cases into {nchunks} chunks of {chunk} -> {outdir}")
