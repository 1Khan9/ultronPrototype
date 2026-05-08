"""Quick VRAM check.

Prints current GPU memory usage on the configured GPU index, plus the
hard cap (11.5 GB) and target (9.2 GB) from the Foundation prompt's
non-negotiables. Flags warning / critical thresholds.

Usage:
    python scripts/check_vram.py             # one-shot snapshot
    python scripts/check_vram.py --watch     # refresh every 2 s
    python scripts/check_vram.py --watch 0.5 # refresh every 0.5 s
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from typing import Optional


HARD_CAP_MB = 11500
TARGET_MB = 9216
WARN_FRACTION = 0.85   # warn at 85 % of hard cap


def vram_used_mb(gpu_id: int = 0) -> Optional[int]:
    """Return current VRAM use on ``gpu_id``, or None if nvidia-smi
    isn't available."""
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
            f"--id={gpu_id}",
        ], text=True, timeout=5).strip()
        return int(out)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


def vram_total_mb(gpu_id: int = 0) -> Optional[int]:
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=memory.total",
            "--format=csv,noheader,nounits",
            f"--id={gpu_id}",
        ], text=True, timeout=5).strip()
        return int(out)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


def gpu_name(gpu_id: int = 0) -> Optional[str]:
    try:
        out = subprocess.check_output([
            "nvidia-smi", "--query-gpu=name", "--format=csv,noheader",
            f"--id={gpu_id}",
        ], text=True, timeout=5).strip()
        return out
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def _format_line(used: int, total: Optional[int]) -> str:
    parts = [f"{used} MB used"]
    if total:
        pct = 100.0 * used / total
        parts.append(f"of {total} MB total ({pct:.0f}%)")
    parts.append(f"target {TARGET_MB} MB")
    parts.append(f"cap {HARD_CAP_MB} MB")
    status = "OK"
    if used > HARD_CAP_MB:
        status = "CRITICAL — over hard cap"
    elif used > HARD_CAP_MB * WARN_FRACTION:
        status = f"WARN — over {int(WARN_FRACTION*100)}% of hard cap"
    elif used > TARGET_MB:
        status = "above target (under cap)"
    parts.append(f"[{status}]")
    return " | ".join(parts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="VRAM snapshot")
    parser.add_argument("--gpu", type=int, default=0, help="GPU index (default 0)")
    parser.add_argument(
        "--watch", nargs="?", type=float, const=2.0, default=None,
        help="Refresh every N seconds (default 2.0)",
    )
    args = parser.parse_args(argv)

    name = gpu_name(args.gpu)
    if name is None:
        print("nvidia-smi not available or no GPU at that index.", file=sys.stderr)
        return 1
    total = vram_total_mb(args.gpu)
    print(f"GPU {args.gpu}: {name}" + (f"  (total {total} MB)" if total else ""))

    if args.watch is None:
        used = vram_used_mb(args.gpu)
        if used is None:
            return 1
        print(_format_line(used, total))
        return 0

    print(f"Watching every {args.watch}s. Ctrl+C to stop.")
    try:
        while True:
            used = vram_used_mb(args.gpu)
            if used is None:
                break
            print(_format_line(used, total))
            time.sleep(args.watch)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
