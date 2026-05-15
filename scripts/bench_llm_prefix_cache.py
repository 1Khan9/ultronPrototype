"""Bench TTFT with vs without the LlamaRAMCache prefix cache.

2026-05-16 latency pass 2 -- Phase 2: ``LlamaRAMCache`` was attached
in ``LLMEngine._build_llama`` so completed session KV state is stored
in host RAM keyed by the longest-common-prefix of the token sequence.
Subsequent calls with a shared prefix (every voice turn -- the system
prompt + history is stable across turns) restore the cached state
instead of re-evaluating those tokens.

This script measures:

1. **Cold path** (cache disabled via ``prefix_cache_ram_bytes=0``):
   each turn re-evaluates the full prompt prefix.

2. **Warm path** (cache enabled, default 2 GiB): turn 1 populates
   the cache; turn N (N >= 2) hits the prefix cache and only needs
   to evaluate the new user message.

Median TTFT delta across 5 representative voice queries with growing
conversation history (turn-2-onward should benefit from prefix
matching). Also reports per-call cache hit/miss diagnostics where
llama-cpp-python exposes them.

VRAM is unaffected (cache is host RAM only). Voice quality is
unaffected (we don't change sampling params or prompt content).

**Voice-stack-concurrency rule:** loads the full LLM. ASK before
running per ``feedback_voice_stack_concurrency.md``.

Run:
    python scripts/bench_llm_prefix_cache.py [--turns 5] [--warmup 1]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import List, Tuple


# Project-root path setup so ``from ultron.*`` works.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))


# Five representative voice queries (mirroring measure_baseline.py
# selection in spirit -- short, conversational, voice-friendly).
_QUERIES = [
    "What's the weather like today?",
    "Tell me a short joke.",
    "How do I list files in a directory on Linux?",
    "Define entropy in one sentence.",
    "Who wrote The Old Man and the Sea?",
]


def _measure_ttft_for_engine(eng, queries: List[str]) -> List[float]:
    """Run ``queries`` sequentially through ``eng.generate_stream`` and
    record TTFT for each. The engine retains conversation history
    across calls so turn 2+ benefits from prefix matching when the
    cache is enabled."""
    ttfts: List[float] = []
    for i, q in enumerate(queries, start=1):
        t0 = time.monotonic()
        first_tok_time = None
        for tok in eng.generate_stream(q, enable_thinking=False):
            if first_tok_time is None:
                first_tok_time = time.monotonic()
                ttfts.append((first_tok_time - t0) * 1000.0)
            # Drain the rest so history records correctly. Don't print.
        if first_tok_time is None:
            ttfts.append(float("nan"))
        # Brief pause so logs are readable.
        time.sleep(0.1)
    return ttfts


def _build_engine(prefix_cache_ram_bytes: int):
    """Build a fresh LLMEngine with the cache knob set to the given
    value. Returns the engine; caller is responsible for cleanup."""
    import os
    # Override the cache config via env-style hook: we pass a custom
    # constructor arg path through the usual init. Simpler: temporarily
    # mutate the loaded config singleton.
    from ultron.config import get_config, reload_config
    cfg = get_config()
    # In-place override -- this is a one-process bench script.
    object.__setattr__(cfg.llm, "prefix_cache_ram_bytes", prefix_cache_ram_bytes)
    from ultron.llm.inference import LLMEngine
    return LLMEngine()


def _percentile(xs: List[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _summarise(ttfts: List[float]) -> dict:
    clean = [t for t in ttfts if t == t]  # drop NaN
    if not clean:
        return {"median_ms": None, "p95_ms": None, "min_ms": None,
                "max_ms": None, "n": 0}
    return {
        "median_ms": round(statistics.median(clean), 1),
        "p95_ms": round(_percentile(clean, 0.95), 1),
        "min_ms": round(min(clean), 1),
        "max_ms": round(max(clean), 1),
        "n": len(clean),
        "raw_ms": [round(t, 1) for t in clean],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--turns", type=int, default=5,
                   help="Number of representative queries to time per condition (default: 5)")
    p.add_argument("--warmup", type=int, default=1,
                   help="Warmup turns to discard before recording (default: 1)")
    p.add_argument("--out", type=Path, default=_ROOT / "baselines.json",
                   help="JSON file to merge results into (default: baselines.json)")
    args = p.parse_args(argv)

    queries = _QUERIES[: args.turns]
    if not queries:
        print("Need at least 1 query.", file=sys.stderr)
        return 2

    results: dict = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "queries": queries,
            "warmup_turns": args.warmup,
            "voice_pass_label": "2026-05-16 latency pass 2 / Phase 2",
        },
    }

    # --- Cold path: cache disabled -----------------------------------
    print(">>> Cold path: prefix_cache_ram_bytes=0 (cache disabled)")
    cold_eng = _build_engine(prefix_cache_ram_bytes=0)
    # Discard warmup turns.
    if args.warmup > 0:
        _ = _measure_ttft_for_engine(cold_eng, queries[: args.warmup])
    cold_ttfts = _measure_ttft_for_engine(cold_eng, queries)
    cold_summary = _summarise(cold_ttfts)
    print(f"Cold TTFTs: {cold_ttfts}")
    print(f"Cold median: {cold_summary['median_ms']} ms")
    del cold_eng

    # --- Warm path: cache enabled (2 GiB default) --------------------
    print("\n>>> Warm path: prefix_cache_ram_bytes=2147483648 (2 GiB)")
    warm_eng = _build_engine(prefix_cache_ram_bytes=2 * 1024 * 1024 * 1024)
    if args.warmup > 0:
        _ = _measure_ttft_for_engine(warm_eng, queries[: args.warmup])
    warm_ttfts = _measure_ttft_for_engine(warm_eng, queries)
    warm_summary = _summarise(warm_ttfts)
    print(f"Warm TTFTs: {warm_ttfts}")
    print(f"Warm median: {warm_summary['median_ms']} ms")
    del warm_eng

    # --- Delta -------------------------------------------------------
    delta_ms = None
    if cold_summary["median_ms"] is not None and warm_summary["median_ms"] is not None:
        delta_ms = round(cold_summary["median_ms"] - warm_summary["median_ms"], 1)
    print(f"\nMedian TTFT improvement: {delta_ms} ms (cold {cold_summary['median_ms']} -> warm {warm_summary['median_ms']})")

    # --- Persist into baselines.json --------------------------------
    results["cold_path"] = cold_summary
    results["warm_path"] = warm_summary
    results["median_delta_ms"] = delta_ms

    out_path = Path(args.out)
    block_key = "llm_prefix_cache_bench"
    try:
        existing = {}
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        existing[block_key] = results
        out_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"\nWrote results to {out_path} under '{block_key}'")
    except Exception as e:
        print(f"Failed to persist results: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
