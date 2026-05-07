"""Review recent addressing decisions made by the live classifier.

Reads the JSONL log at ``settings.ADDRESSING_LOG_PATH`` and prints recent
decisions in a compact, scannable form. Intended for tuning thresholds and
catching false positives / negatives.

Usage:
    python scripts/review_addressing.py            # last 50 decisions
    python scripts/review_addressing.py --tail 200 # last 200
    python scripts/review_addressing.py --misses   # only NOT_ADDRESSED
                                                   # (likely false negatives)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reach the main checkout for settings + log path.
_HERE = Path(__file__).resolve()
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from config import settings  # noqa: E402


def _format_record(record: dict) -> str:
    decision = record.get("decision", "?")
    src = record.get("source", "?")
    conf = record.get("confidence", 0.0)
    latency = record.get("latency_ms", 0.0)
    utt = record.get("utterance", "")
    if len(utt) > 70:
        utt = utt[:67] + "..."
    reason = record.get("reason", "")
    ts = record.get("ts", "")
    # Compact: 16:42:17  ADDRESSED   rule    0.88  12 ms  "play that song" -- imperative
    short_ts = ts.split("T", 1)[1].split(".", 1)[0] if "T" in ts else ts
    return (
        f"  {short_ts}  {decision:14s}  {src:11s}  "
        f"{conf:.2f}  {latency:5.0f} ms  {utt!r}  -- {reason}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Review addressing decisions.")
    parser.add_argument(
        "--tail", type=int, default=50, help="number of recent decisions to print"
    )
    parser.add_argument(
        "--misses",
        action="store_true",
        help="only show NOT_ADDRESSED decisions (likely false negatives)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=settings.ADDRESSING_LOG_PATH,
        help="path to the addressing log JSONL",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.is_file():
        print(f"No addressing log at {log_path} yet -- run Ultron first.")
        return 0

    records: list[dict] = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if args.misses:
        records = [r for r in records if r.get("decision") == "NOT_ADDRESSED"]

    tail = records[-args.tail:]
    print(f"Showing last {len(tail)} of {len(records)} decisions from {log_path}\n")
    print(
        "  time        decision        source       conf  lat     utterance"
    )
    print("  " + "-" * 96)
    for r in tail:
        print(_format_record(r))

    # Quick stats
    by_decision: dict[str, int] = {}
    by_source: dict[str, int] = {}
    latencies: list[float] = []
    for r in records:
        by_decision[r.get("decision", "?")] = by_decision.get(r.get("decision", "?"), 0) + 1
        by_source[r.get("source", "?")] = by_source.get(r.get("source", "?"), 0) + 1
        if (lat := r.get("latency_ms")) is not None:
            latencies.append(float(lat))

    print()
    print(f"  totals (across {len(records)} decisions):")
    for k, v in sorted(by_decision.items()):
        print(f"    {k:14s} {v}")
    print()
    print("  by classifier source:")
    for k, v in sorted(by_source.items()):
        print(f"    {k:14s} {v}")
    if latencies:
        latencies.sort()
        avg = sum(latencies) / len(latencies)
        p95 = latencies[int(0.95 * len(latencies))]
        print()
        print(
            f"  latency: avg {avg:.1f} ms  p95 {p95:.0f} ms  max {latencies[-1]:.0f} ms"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
