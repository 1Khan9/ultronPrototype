#!/usr/bin/env python
"""Turn a trace_corpus JSONL into readable audit artifacts for the line-by-line
review:

  _summary.txt    -- route distribution + anomaly counts.
  _anomalies.txt  -- every structural problem (no-match where expected, route/line
                     errors, empty final, meta-leak-shaped final, tail on a
                     non-snap line, etc.) -- read ALL of these.
  _newpaths.txt   -- every NEW-pathway case (Marvel / think-respond / curated
                     reaction / identity / simple yes-no / agree-disagree) in full
                     flow -- read ALL of these (the highest-risk new routes).
  pairings/<agent>.txt -- the UNIQUE (callout -> snap -> tail -> final) triples per
                     agent, so the agent x callout tail coherence can be scanned.

    python scripts/relay_test/audit_trace.py logs/relay_test/trace_iter1.jsonl \
        logs/relay_test/analysis/iter1
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

_ROSTER = ("astra", "breach", "brimstone", "chamber", "clove", "cypher",
           "deadlock", "fade", "gekko", "harbor", "iso", "jett", "kayo", "kay/o",
           "killjoy", "miks", "neon", "omen", "phoenix", "raze", "reyna", "sage",
           "skye", "sova", "tejo", "veto", "viper", "vyse", "waylay", "yoru")
_AGENT_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a in _ROSTER) + r")\b",
                       re.IGNORECASE)


def _agent_of(rec) -> str | None:
    for field in ("payload", "context", "final"):
        v = rec.get(field) or ""
        m = _AGENT_RE.search(v)
        if m:
            return m.group(1).lower().replace("/", "")
    return None


def main() -> int:
    jsonl = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(jsonl), "analysis")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(os.path.join(outdir, "pairings"), exist_ok=True)

    rows = [json.loads(l) for l in open(jsonl, encoding="utf-8")]
    routes = Counter(r.get("route", "?") for r in rows)
    cats = Counter(r.get("category", "?") for r in rows)

    anomalies = []
    newpaths = []
    pairings = defaultdict(set)

    META_RE = re.compile(
        r"\bas an? (?:ai|language model|assistant)\b|\blanguage model\b|"
        r"\bi can'?t (?:help|do|answer|respond|engage)\b|\bi'?m (?:sorry|unable)\b|"
        r"<\||```|\bhere'?s (?:my|a) response\b", re.I)

    for i, r in enumerate(rows):
        route = r.get("route", "")
        final = r.get("final")
        exp = r.get("expect_match")
        # --- anomalies ---
        if exp and not r.get("matched") and route not in ("no_match",):
            pass
        if exp and not r.get("matched"):
            anomalies.append((i, "NO_MATCH_BUT_EXPECTED", r))
        if r.get("route_err"):
            anomalies.append((i, "ROUTE_ERR", r))
        if isinstance(final, str) and final.startswith("<LINE_ERR"):
            anomalies.append((i, "LINE_ERR", r))
        if r.get("matched") and isinstance(final, str) and not final.strip():
            anomalies.append((i, "EMPTY_FINAL", r))
        if isinstance(final, str) and META_RE.search(final):
            anomalies.append((i, "META_LEAK_SHAPED", r))
        # a tail that duplicates/!= relate to snap or is suspiciously long
        tail = r.get("tail")
        if tail and len(tail.split()) > 18:
            anomalies.append((i, "LONG_TAIL", r))
        # --- new pathways (read all) ---
        if (route.startswith("answer:") or route.startswith("curated_reaction:")
                or route == "identity"
                or r.get("category") in ("pack_var_marvel_think",
                                         "pack_var_social_reactions",
                                         "pack_var_yesno_agree")):
            newpaths.append((i, r))
        # --- agent x callout tail pairings (snap-routed) ---
        if route == "snap" and r.get("snap") and tail:
            ag = _agent_of(r)
            if ag:
                pairings[ag].add((r.get("snap", ""), tail, r.get("final", "")))

    # summary
    with open(os.path.join(outdir, "_summary.txt"), "w", encoding="utf-8") as f:
        f.write(f"total cases: {len(rows)}\n")
        f.write(f"matched: {sum(1 for r in rows if r.get('matched'))}\n")
        f.write(f"anomalies: {len(anomalies)}\n")
        f.write(f"new-pathway cases: {len(newpaths)}\n\n")
        f.write("=== ROUTE DISTRIBUTION ===\n")
        for rt, n in routes.most_common():
            f.write(f"  {n:>6}  {rt}\n")
        f.write("\n=== TOP CATEGORIES ===\n")
        for ct, n in cats.most_common(50):
            f.write(f"  {n:>6}  {ct}\n")

    def _flow(r):
        out = [f"  IN  : {r.get('text')}",
               f"  norm: {r.get('norm1')}",
               f"  route: {r.get('route')}  ({r.get('reason')})"]
        if r.get("addressee"):
            out.append(f"  addr: {r.get('addressee')}  dir={r.get('directive')}")
        if r.get("snap"):
            out.append(f"  snap: {r.get('snap')}")
        if r.get("tail"):
            out.append(f"  tail: {r.get('tail')}")
        if r.get("llm_user"):
            out.append(f"  PROMPT(user): {r.get('llm_user')[:400]}")
        out.append(f"  FINAL: {r.get('final')}")
        return "\n".join(out)

    with open(os.path.join(outdir, "_anomalies.txt"), "w", encoding="utf-8") as f:
        f.write(f"{len(anomalies)} anomalies\n\n")
        for i, kind, r in anomalies:
            f.write(f"#{i:05d} [{kind}] cat={r.get('category')}\n{_flow(r)}\n\n")

    with open(os.path.join(outdir, "_newpaths.txt"), "w", encoding="utf-8") as f:
        f.write(f"{len(newpaths)} new-pathway cases\n\n")
        for i, r in newpaths:
            f.write(f"#{i:05d}\n{_flow(r)}\n\n")

    for ag, triples in sorted(pairings.items()):
        with open(os.path.join(outdir, "pairings", f"{ag}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(f"=== {ag} : {len(triples)} unique callout->tail pairings ===\n\n")
            for snap, tail, final in sorted(triples):
                f.write(f"  snap : {snap}\n  tail : {tail}\n  full : {final}\n\n")

    print(f"rows={len(rows)} anomalies={len(anomalies)} newpaths={len(newpaths)} "
          f"agents_with_pairings={len(pairings)} -> {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
