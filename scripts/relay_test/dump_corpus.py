#!/usr/bin/env python
"""Render a trace_corpus JSONL into a COMPLETE human-readable dump -- EVERY case,
one compact line each, grouped by route then category, so the whole 25k corpus can
be read by hand line-by-line for coherence/quality. This is a reading aid for the
human audit, NOT an auto-auditor.

Each line:  #IDX [route] (cat) IN: <transcription>  =>  OUT: <final>   {snap|tail|prompt}

    python scripts/relay_test/dump_corpus.py logs/relay_test/trace_iterN.jsonl \
        logs/relay_test/analysis/iterN/_readall.txt
"""
from __future__ import annotations

import json
import sys
from collections import Counter

_ROUTE_ORDER = [
    "snap", "curated_command", "curated_reaction:nice_shots",
    "curated_reaction:well_played", "curated_reaction:clutch",
    "curated_reaction:carry", "curated_reaction:praise",
    "curated_reaction:called_bad", "curated_reaction:cringe",
    "curated_reaction:stupid", "curated_reaction:shutup",
    "curated_reaction:insulted", "curated_reaction:giving_up",
    "identity", "answer:marvel", "answer:think_respond",
    "directive_pool:greet", "directive_pool:farewell",
    "directive_pool:farewell_win", "directive_pool:farewell_loss",
    "criticize", "verbatim", "compose_llm", "relay_llm", "no_match",
]


def _key(route: str) -> tuple:
    try:
        return (_ROUTE_ORDER.index(route), route)
    except ValueError:
        return (len(_ROUTE_ORDER), route)


def main() -> int:
    jsonl = sys.argv[1]
    out = sys.argv[2]
    rows = [json.loads(l) for l in open(jsonl, encoding="utf-8")]
    for i, r in enumerate(rows):
        r["_idx"] = i
    rows.sort(key=lambda r: (_key(r.get("route", "?")), r.get("category", ""),
                             r.get("_idx", 0)))
    counts = Counter(r.get("route", "?") for r in rows)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# COMPLETE corpus dump -- {len(rows)} cases, grouped by route.\n")
        f.write("# route counts: " + ", ".join(
            f"{rt}={n}" for rt, n in sorted(counts.items(),
                                            key=lambda kv: _key(kv[0]))) + "\n\n")
        cur = None
        for r in rows:
            rt = r.get("route", "?")
            if rt != cur:
                cur = rt
                f.write(f"\n========== ROUTE: {rt}  ({counts[rt]} cases) ==========\n")
            idx = r.get("_idx")
            cat = (r.get("category", "") or "").replace("pack_", "").replace("neg_", "-")
            txt = (r.get("text") or "").replace("\n", " ")
            fin = r.get("final")
            extra = ""
            if r.get("norm1") and r.get("norm1") != txt:
                extra += f"  [norm:{r['norm1']}]"
            if rt.startswith("answer:") and r.get("llm_user"):
                # the 3B fallback (final) is not the real answer; show the slot prompt
                u = r["llm_user"].replace("\n", " | ")
                extra += f"  [PROMPT:{u}]"
            if not r.get("matched"):
                f.write(f"#{idx:05d} ({cat}) IN: {txt}{extra}\n")
            else:
                f.write(f"#{idx:05d} ({cat}) IN: {txt}  =>  OUT: {fin}{extra}\n")
    print(f"wrote {len(rows)} cases -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
