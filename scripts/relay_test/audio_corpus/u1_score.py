"""Ultron 1.0 — score a u1.0 audio E2E battery session (RELATIVE metrics).

Reads a ``run_corpus.py --u1`` session log (one JSON row per clip, with the labeled
``expected_scenario`` / ``expected_channel`` / ``case_class`` + the live ``gate_scenario`` /
``channel`` / ``final_spoken``) and grades the always-listening gate + routing.

Numbers are RELATIVE, not a pass/fail gate: Kokoro is out-of-distribution for the wake model and
am_michael garbles short jargon through Whisper, so STT mishears are expected — the gate decision
(relay vs private vs command vs ignore) + the IGNORE-suppression rate are the meaningful signals.
The hallucination-pressure subset (IGNORE cases engineered to bait a false response) is reported
separately. ``score_session`` is PURE (unit-tested); ``main`` loads the latest session + prints.

Usage:
  python scripts/relay_test/audio_corpus/u1_score.py [session_log.jsonl]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

_HERE = Path(__file__).resolve().parent


def _spoke(row: dict) -> bool:
    """True iff the turn produced ANY spoken output (a final line or re-transcribed audio)."""
    return bool((row.get("final_spoken") or "").strip()
                or (row.get("response_retranscribed") or "").strip())


def score_session(rows: List[dict]) -> dict:
    """Grade a list of u1.0 session rows. PURE -- no I/O. Returns a RELATIVE scorecard."""
    by_class: dict = {}
    halluc = {"n": 0, "suppressed": 0}     # hallucination-pressure IGNORE subset
    scenario_hits = scenario_n = 0
    channel_hits = channel_n = 0
    ignore_n = ignore_suppressed = 0

    for r in rows:
        cls = r.get("case_class") or "?"
        exp_s = r.get("expected_scenario")
        act_s = r.get("gate_scenario")
        c = by_class.setdefault(cls, {"n": 0, "scenario_match": 0, "channel_match": 0})
        c["n"] += 1

        if exp_s is not None:
            scenario_n += 1
            if act_s == exp_s:
                scenario_hits += 1
                c["scenario_match"] += 1

        exp_ch = r.get("expected_channel")
        if exp_ch and exp_ch != "none":
            channel_n += 1
            if (r.get("channel") or "") == exp_ch:
                channel_hits += 1
                c["channel_match"] += 1

        if exp_s == "IGNORE":
            ignore_n += 1
            # Correctly suppressed = the gate said IGNORE AND nothing was spoken.
            if act_s == "IGNORE" and not _spoke(r):
                ignore_suppressed += 1
            if "hallucination_pressure" in (r.get("tags") or []):
                halluc["n"] += 1
                if act_s == "IGNORE" and not _spoke(r):
                    halluc["suppressed"] += 1

    def _rate(a: int, b: int) -> Optional[float]:
        return round(a / b, 3) if b else None

    return {
        "n": len(rows),
        "scenario_accuracy": _rate(scenario_hits, scenario_n),
        "scenario_n": scenario_n,
        "channel_accuracy": _rate(channel_hits, channel_n),
        "channel_n": channel_n,
        "ignore_suppression_rate": _rate(ignore_suppressed, ignore_n),
        "ignore_n": ignore_n,
        "hallucination_pressure_suppression": _rate(halluc["suppressed"], halluc["n"]),
        "hallucination_pressure_n": halluc["n"],
        "by_class": {
            k: {"n": v["n"],
                "scenario_match_rate": _rate(v["scenario_match"], v["n"]),
                "channel_match": v["channel_match"]}
            for k, v in sorted(by_class.items())
        },
    }


def _load_rows(path: Path) -> List[dict]:
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            rows.append(json.loads(ln))
    return rows


def _latest_session_log() -> Optional[Path]:
    logs = sorted(_HERE.glob("session_*/corpus_*.log.jsonl"))
    return logs[-1] if logs else None


def main() -> int:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = _latest_session_log()
        if path is None:
            print("no session_*/corpus_*.log.jsonl found -- run run_corpus.py --u1 first")
            return 2
    rows = _load_rows(path)
    card = score_session(rows)
    print(f"[u1-score] {path}")
    print(json.dumps(card, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
