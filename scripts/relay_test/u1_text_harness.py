"""Ultron 1.0 — text-injection routing/intent harness (PRIMARY, deterministic).

Per the research synthesis (decision D6 / C_harness): the trustworthy routing-accuracy + intent
signal comes from injecting NORMALIZED TEXT straight into the post-STT pipeline (no audio, no STT
noise) -- ~1 ms/case, fully deterministic. The audio MP3 E2E harness (the user's explicit ask) is a
separate, slower acoustic-integration + regression check whose absolute numbers are an upper bound
(Kokoro TTS is out-of-distribution). THIS harness is the one that gives reliable routing numbers and
is the labeled corpus the u1.0 intent gate will calibrate against.

It runs each labeled case through the existing deterministic detection
  normalize_command -> match_relay_command -> relay_route_info
records a per-stage trace, and scores the user's three categories:
  (a) COMMAND      -- must RELAY (incl. commands embedded in non-triggering lead/trail text)
  (b) NON-TRIGGER  -- full paragraphs / banter / talking-to-others / questions: must NOT relay
  (c) COMPOUND     -- back-to-back callouts: must relay; the u1.0 LLM path (M1-wire+M4) combines
                      them into ONE response (this harness currently validates relay + completeness;
                      the combined-LLM-output assertion is added when that path is wired behind the flag).

Run (worktree):
  $env:PYTHONPATH="<worktree>\\src;<worktree>"; $env:KENNING_ROUTER_WAIT_SECONDS="0"
  .venv\\python.exe scripts\\relay_test\\u1_text_harness.py [--jsonl logs/u1_text_harness/run.jsonl]

NOTE: runs in embedder-sidecar-fail-open mode by default (deterministic, no network). The relay-intent
gate then uses keyword behavior; results are a deterministic lower bound on the semantic path. Some
cases are tagged ``known_baseline_fail`` -- they reflect the 22-fail frozen baseline (e.g. "kill the
enemy team" is wrongly hijacked today); the u1.0 LLM intent gate is expected to FIX these.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

# Ensure worktree root + src are importable when run directly.
_ROOT = Path(__file__).resolve().parents[2]
for p in (str(_ROOT / "src"), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import kenning  # noqa: F401,E402  (CUDA DLL path + package init)
from kenning.audio.command_normalizer import normalize_command  # noqa: E402
from kenning.audio.relay_speech import (  # noqa: E402
    match_relay_command,
    relay_route_info,
    is_complete_tactical_callout,
    DEFAULT_ADDRESSEE_NAMES,
)


@dataclass
class Case:
    text: str
    category: str          # "command" | "non_trigger" | "compound"
    should_relay: bool
    note: str = ""
    known_baseline_fail: bool = False
    # A current routing limitation the u1.0 LLM intent gate (M5) is built to FIX. Tracked, not a
    # "real" (new-bug) failure -- the harness reports it so we can watch the u1.0 gate close it.
    u1_gate_target: bool = False
    # for compound: how many sub-callouts the combined response must cover
    expect_subcallouts: int = 0


# ---------------------------------------------------------------------------
# Starter labeled corpus (grown each milestone). Three categories.
# ---------------------------------------------------------------------------
CASES: List[Case] = [
    # (a) COMMANDS that must relay -- plain
    Case("tell my team to rush B", "command", True, "explicit relay lead"),
    Case("sova hit 84 on A main", "command", True, "bare tactical callout"),
    Case("they have no smokes left", "command", True, "enemy-comp read"),
    Case("one back plat", "command", True, "count + location"),
    Case("their neon has ult", "command", True, "enemy ult"),
    Case("reyna is tree", "command", True, "single agent at spot"),
    Case("say to my team we should save this round", "command", True, "say-to-team lead"),
    Case("ask Jett to take the lurk", "command", True, "named-agent ask"),
    # (a) COMMANDS embedded in non-triggering lead/trail text (must still relay just the command).
    # CURRENT (sidecar-up): the relay-intent gate scores the surrounding narration as musing and
    # SUPPRESSES the embedded command (false-negative). The u1.0 LLM intent gate must extract it.
    Case("okay so anyway, tell my team to push A now, then we reset", "command", True,
         "command embedded mid-sentence", u1_gate_target=True),
    Case("uh hold on -- tell the team cypher is flank", "command", True, "filler lead + command",
         u1_gate_target=True),
    # (b) NON-TRIGGERING -- must NOT relay
    Case("I think this map is really fun honestly, the rotations feel clean and the sightlines are fair",
         "non_trigger", False, "opinion paragraph"),
    Case("yeah man I was telling my buddy earlier that valorant got way better this act",
         "non_trigger", False, "talking to someone else / recount"),
    Case("what do you think we should do next round", "non_trigger", False, "question to Ultron (me-only)"),
    Case("chat says hi everyone welcome back to the stream", "non_trigger", False, "talking to stream"),
    Case("I should probably tell them to push but I'm not sure", "non_trigger", False,
         "first-person musing (narration)"),
    # CURRENT: leaks to relay even with the semantic gate (false-positive); u1.0 gate must suppress.
    Case("man that was such a clutch round, gg", "non_trigger", False, "banter", u1_gate_target=True),
    Case("hey are you even listening to me right now", "non_trigger", False, "addressing a person"),
    Case("kill the enemy team", "non_trigger", False, "imperative w/ 'team' -- must NOT hijack as relay",
         known_baseline_fail=True),
    Case("push with the team", "non_trigger", False, "'team' as object, not relay",
         known_baseline_fail=True),
    # (c) COMPOUND -- must relay; u1.0 combines into ONE response.
    # CURRENT (sidecar-up): the bare double-callout (no explicit relay lead) is scored non-relay and
    # suppressed -> u1.0 gate target (it should relay + combine).
    Case("Sova hit 84, Breach hit 97", "compound", True, "two damage callouts (no lead)",
         u1_gate_target=True, expect_subcallouts=2),
    Case("Jett hit 84, Breach hit 97, one rotating to B", "compound", True,
         "three callouts", expect_subcallouts=3),
    Case("rush B then plant default", "compound", True, "sequential directives", expect_subcallouts=2),
]


def run_case(c: Case) -> dict:
    norm = normalize_command(c.text)
    cmd = match_relay_command(norm, names=DEFAULT_ADDRESSEE_NAMES)
    relayed = cmd is not None
    route = relay_route_info(cmd) if cmd is not None else {"route": "no_relay", "reason": "", "subtype": None}
    complete = is_complete_tactical_callout(norm)
    correct = (relayed == c.should_relay)
    return {
        "text": c.text,
        "category": c.category,
        "should_relay": c.should_relay,
        "note": c.note,
        "known_baseline_fail": c.known_baseline_fail,
        "u1_gate_target": c.u1_gate_target,
        # per-stage trace:
        "stage_normalized": norm,
        "stage_relayed": relayed,
        "stage_addressee": getattr(cmd, "addressee", None),
        "stage_payload": getattr(cmd, "payload", None),
        "stage_directive": getattr(cmd, "directive", None),
        "stage_route": route.get("route"),
        "stage_route_reason": route.get("reason"),
        "stage_complete_tactical": complete,
        "correct": correct,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="logs/u1_text_harness/run.jsonl")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    rows = [run_case(c) for c in CASES]

    out = Path(args.jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Scorecard. "Real" failures exclude the tagged known-baseline-fail cases.
    total = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    real_fails = [r for r in rows if not r["correct"] and not r["known_baseline_fail"] and not r["u1_gate_target"]]
    known_fails = [r for r in rows if not r["correct"] and r["known_baseline_fail"]]
    gate_targets = [r for r in rows if not r["correct"] and r["u1_gate_target"]]
    by_cat = {}
    for r in rows:
        c = r["category"]
        by_cat.setdefault(c, [0, 0])
        by_cat[c][1] += 1
        if r["correct"]:
            by_cat[c][0] += 1

    print(f"=== u1.0 text-injection routing harness ===  cases={total}  correct={correct}/{total}")
    for cat, (ok, n) in sorted(by_cat.items()):
        print(f"  {cat:12s}: {ok}/{n}")
    print(f"  REAL failures (new bugs -- excludes known-baseline + u1-gate-targets): {len(real_fails)}")
    print(f"  known-baseline failures (the frozen-22): {len(known_fails)}")
    print(f"  u1.0-gate TARGETS still open (current routing gaps M5 must close): {len(gate_targets)}")
    for r in gate_targets:
        print(f"    [GATE-TARGET] {r['category']}/{'relay' if r['should_relay'] else 'no'} "
              f"relayed={r['stage_relayed']} :: {r['text']!r}")
    if args.verbose or real_fails:
        for r in (real_fails or rows if args.verbose else real_fails):
            tag = "KNOWN" if r["known_baseline_fail"] else "FAIL"
            print(f"  [{tag}] {r['category']}/{'relay' if r['should_relay'] else 'no'}  "
                  f"relayed={r['stage_relayed']}  route={r['stage_route']}  :: {r['text']!r}")
    # compound completeness (informational until the LLM combine path is wired)
    comp = [r for r in rows if r["category"] == "compound"]
    print(f"  compound cases relaying: {sum(1 for r in comp if r['stage_relayed'])}/{len(comp)} "
          f"(combined-LLM-output assertion lands with M1-wire+M4)")
    print(f"  trace -> {out}")
    # exit non-zero only on REAL (non-baseline) failures, so this is a CI gate
    return 1 if real_fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
