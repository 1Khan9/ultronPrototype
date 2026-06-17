#!/usr/bin/env python
"""Route scorecard: deterministic snap% vs LLM-path% over the corpus packs, with
NO LLM (uses the same `_route_info` classifier the tracer uses). The Part-2 gate
for the M1-M3 snap-coverage work is: a SHORT (<=7-word) callout that falls to the
generic `relay_llm` prompt (or no_match) is a snap MISS -- M1's target. Run before
and after a change to measure coverage delta.

    python scripts/relay_test/route_scorecard.py [seed] [target]
"""
from __future__ import annotations

import sys
from collections import Counter

from corpus_packs import build_corpus                # noqa: E402
from trace_corpus import _route_info                 # noqa: E402
from kenning.audio.command_normalizer import normalize_command
from kenning.audio.relay_speech import match_relay_command


def _wc(s: str) -> int:
    return len((s or "").split())


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    cases = build_corpus(seed=seed, target=target)
    routes: Counter = Counter()
    short_llm: list[str] = []     # <=7w that fell to the generic LLM relay / no_match
    for c in cases:
        text = c.text if hasattr(c, "text") else c[0]
        cmd = match_relay_command(normalize_command(text))
        route = _route_info(cmd)["route"]
        routes[route] += 1
        if _wc(text) <= 7 and route in ("relay_llm", "no_match"):
            short_llm.append(f"[{route}] {text}")

    total = sum(routes.values())
    snap = routes.get("snap", 0)
    relay_llm = routes.get("relay_llm", 0)
    no_match = routes.get("no_match", 0)
    print(f"# route scorecard  (seed={seed}, n={total})")
    print(f"  snap        : {snap:6d}  ({100*snap/total:.1f}%)")
    print(f"  relay_llm   : {relay_llm:6d}  ({100*relay_llm/total:.1f}%)")
    print(f"  no_match    : {no_match:6d}  ({100*no_match/total:.1f}%)")
    for r, n in sorted(routes.items(), key=lambda kv: -kv[1]):
        if r not in ("snap", "relay_llm", "no_match"):
            print(f"  {r:12}: {n:6d}  ({100*n/total:.1f}%)")
    print(f"\n# GATE: SHORT (<=7w) llm/no_match (M1 targets) = {len(short_llm)}")
    for line in short_llm[:80]:
        print(f"    {line}")
    if len(short_llm) > 80:
        print(f"    ... +{len(short_llm) - 80} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
