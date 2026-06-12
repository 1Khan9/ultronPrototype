"""Run the full integration suite with a clear summary.

Wraps ``pytest tests/integration tests/routing tests/error_recovery`` so
the output is more readable than raw pytest noise. Use ``--gpu`` to
include the live-stack tests gated on ``PYTEST_RUN_GPU_TESTS=1``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INTEGRATION_DIRS = [
    REPO / "tests" / "integration",
    REPO / "tests" / "routing",
    REPO / "tests" / "error_recovery",
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Kenning integration test suite.",
    )
    parser.add_argument(
        "--gpu", action="store_true",
        help="Include PYTEST_RUN_GPU_TESTS=1 live-stack tests (slow; "
             "may meter Claude API).",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Quiet pytest output (one char per test).",
    )
    args = parser.parse_args(argv)

    env = os.environ.copy()
    if args.gpu:
        env["PYTEST_RUN_GPU_TESTS"] = "1"
        print("=" * 60)
        print("RUNNING WITH PYTEST_RUN_GPU_TESTS=1")
        print("Slow tests will load real models or hit Claude API.")
        print("=" * 60)
        print()

    cmd = [
        sys.executable, "-m", "pytest",
        *[str(p) for p in INTEGRATION_DIRS if p.is_dir()],
        "-q" if args.quiet else "-v",
        "--tb=short",
    ]
    print("cmd:", " ".join(cmd))
    print()

    t0 = time.monotonic()
    result = subprocess.run(cmd, env=env, cwd=str(REPO))
    elapsed = time.monotonic() - t0
    print()
    print("=" * 60)
    print(f"Wall clock: {elapsed:.1f}s")
    print(f"Exit code: {result.returncode}")
    print("=" * 60)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
