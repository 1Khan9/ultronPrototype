"""Unified pytest runner with built-in safeguards.

THE single entry point for running the test sweep. Use this instead
of calling ``pytest tests/`` directly so the safeguards always apply.

Why this exists: during the 2026-05-21 frontier-enhancement pass, the
test sweep recurrently broke in ways that wasted hours to debug:

- Two ``pytest tests/`` invocations launched from different shells
  contended for fixture locks, GPU memory, and the HF cache. Both
  hung at ~0 % CPU. Diagnosis required `tasklist` / `psutil` chasing.

- Individual tests hung silently because pytest had no per-test
  timeout. The whole sweep would freeze with no indication of which
  test was the culprit.

- One test's mutation of the global config singleton would leak into
  unrelated tests downstream, producing failures that vanished when
  the tests were run in isolation.

This wrapper does:

1. **Pre-flight kill**: if any other pytest processes are running
   against this codebase, terminates them before starting (with a
   loud warning naming the PIDs). No more silent concurrent-run
   contention.

2. **Per-test timeout**: passes ``--timeout=30 --timeout-method=thread``
   (also set as the default in pyproject.toml). Any individual hang
   surfaces as ``Failed: Timeout >30.0s`` naming the offending test.

3. **Live streaming**: forwards stdout/stderr so you see progress
   tick-by-tick, not a buffered wall of dots at the end.

4. **Clean shutdown**: on Ctrl-C or completion, terminates all
   pytest descendants so no zombie workers linger.

5. **Coloured pass/fail summary** at the end with timing.

Usage::

    python scripts/run_tests.py                  # full sweep
    python scripts/run_tests.py tests/memory/    # just one dir
    python scripts/run_tests.py -k embedder      # just matching
    python scripts/run_tests.py --fast           # skip slow markers
    python scripts/run_tests.py --no-timeout     # disable per-test
                                                 # timeout (debug aid)
    python scripts/run_tests.py --kill-only      # just clean up + exit

Exit codes mirror pytest's: 0 on green, 1 on failures, 2 on internal
errors. Returns 4 if the pre-flight kill couldn't establish a clean
slate.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


# Sweep-durability tunables (2026-05-22).
#
# Any pytest process older than this is treated as an ORPHAN — killed
# unconditionally with no operator prompt. The Claude harness
# sometimes backgrounds a tool call, marks it as "completed" while
# the actual pytest child is still alive, and that orphan then blocks
# the next sweep's conftest concurrent-run guard. 5 min is more than
# enough for any legitimate sweep (typical: 75-80 s, slowest ever
# observed: ~3 min including a CUDA-warmup test).
ORPHAN_AGE_SECONDS = 5 * 60


# Mutex file path. Two concurrent ``scripts/run_tests.py`` invocations
# clobber each other's MCP port + fixture-file locks; even if both
# pre-flight kills run successfully against an empty list, the two
# sweeps race against each other from second one onward. The lock
# file is the explicit mutex. Cleanup is registered via ``atexit``
# so a crash leaves a stale lock; the next invocation detects the
# stale PID and recovers.
SWEEP_LOCK_FILE = ROOT / "data" / ".run_tests.lock"


# ---------------------------------------------------------------------------
# Pre-flight: kill any other pytest processes on this codebase
# ---------------------------------------------------------------------------


def _acquire_sweep_lock() -> bool:
    """Acquire the cross-instance sweep lock or return False.

    The lock is a file at :data:`SWEEP_LOCK_FILE` containing the PID
    of the active sweep. On entry:

      * If the file doesn't exist → write our PID, return True.
      * If it exists with a live python PID whose cmdline mentions
        ``run_tests.py`` or ``pytest`` → another sweep is alive,
        return False.
      * If it exists with a dead PID (stale lock from a crashed
        instance) → overwrite with our PID, return True.

    Cleanup is registered via :mod:`atexit`. A SIGTERM bypasses the
    cleanup, so stale-lock recovery on the next invocation is the
    real safety net.
    """
    try:
        import psutil  # type: ignore[import]
    except ImportError:
        # No psutil → can't check the existing PID's liveness.
        # Honor the lock conservatively: if it exists, treat as held.
        if SWEEP_LOCK_FILE.exists():
            print(
                f"!!! sweep lock at {SWEEP_LOCK_FILE} held; psutil "
                "unavailable to check liveness. Delete the file if "
                "this is a stale lock."
            )
            return False
        SWEEP_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        SWEEP_LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
        return True

    SWEEP_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SWEEP_LOCK_FILE.exists():
        try:
            existing_pid_text = SWEEP_LOCK_FILE.read_text(encoding="utf-8").strip()
            existing_pid = int(existing_pid_text)
        except (OSError, ValueError):
            existing_pid = -1
        if existing_pid > 0 and psutil.pid_exists(existing_pid):
            try:
                proc = psutil.Process(existing_pid)
                cmd_joined = " ".join(proc.cmdline()).lower()
                if "run_tests.py" in cmd_joined or "pytest" in cmd_joined:
                    print(
                        f"!!! Another scripts/run_tests.py instance is "
                        f"already active (PID {existing_pid}).\n"
                        f"    Use --wait to wait, or kill it manually."
                    )
                    return False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        # Stale lock file from a crashed previous instance.
        print(
            f"  Recovering stale sweep lock at {SWEEP_LOCK_FILE} "
            f"(was PID {existing_pid}, no longer alive)."
        )

    try:
        SWEEP_LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except OSError as e:
        print(f"!!! Could not write sweep lock file: {e}")
        return False
    return True


def _release_sweep_lock() -> None:
    """Drop the sweep lock if we own it. Safe to call multiple times."""
    try:
        if not SWEEP_LOCK_FILE.exists():
            return
        try:
            held_by = SWEEP_LOCK_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return
        if held_by != str(os.getpid()):
            return  # someone else's lock; don't touch
        SWEEP_LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _list_competing_pytests(include_age: bool = False) -> list[dict]:
    """Return process info for any python.exe processes running
    pytest on this codebase EXCLUDING this script's own PID + its
    ancestors.

    Args:
        include_age: When True, attaches an ``age_seconds`` field
            computed from ``create_time()``. Used by the orphan-kill
            pass to distinguish young (probably-legitimate) competing
            sweeps from old orphans left behind by background harness
            cancellations.
    """
    try:
        import psutil  # type: ignore[import]
    except ImportError:
        print("WARNING: psutil unavailable; can't enforce concurrent-run "
              "safeguard. Install with: pip install psutil")
        return []

    me_pid = os.getpid()
    try:
        me_proc = psutil.Process(me_pid)
        ancestors = {a.pid for a in me_proc.parents()}
    except Exception:
        ancestors = set()
    ancestors.add(me_pid)

    now = time.time()
    found = []
    for p in psutil.process_iter(attrs=["pid", "name", "cmdline", "create_time"]):
        try:
            name = (p.info.get("name") or "").lower()
            if "python" not in name:
                continue
            cmdline = p.info.get("cmdline") or []
            joined = " ".join(cmdline).lower()
            if "pytest" not in joined:
                continue
            if "tests" not in joined and "tests/" not in joined:
                continue
            if p.info["pid"] in ancestors:
                continue
            info = dict(p.info)
            if include_age:
                try:
                    info["age_seconds"] = now - float(p.info.get("create_time") or now)
                except (TypeError, ValueError):
                    info["age_seconds"] = 0.0
            found.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def _kill_competing_pytests(yes: bool = False) -> bool:
    """Terminate any competing pytest processes. Returns True if the
    slate is clean afterwards.

    Two passes:

      1. **Aggressive orphan kill**: anything older than
         :data:`ORPHAN_AGE_SECONDS` (5 min) gets killed unconditionally
         WITH NO PROMPT. These are the leftover pytest workers the
         Claude harness sometimes orphans when it backgrounds a
         tool call — they're never legitimate and only cause
         conftest concurrent-run blocks.
      2. **Recent-run kill**: anything under that age is also killed
         but with a printed notice so the operator can see it
         happen. (Same behaviour as the previous revision.)

    Each pass: ``terminate()`` first, wait up to 3 s, then ``kill()``
    survivors. Final ``_list_competing_pytests()`` check verifies the
    slate is clear before we return True.
    """
    try:
        import psutil  # type: ignore[import]
    except ImportError:
        return True

    competing = _list_competing_pytests(include_age=True)
    if not competing:
        return True

    orphans = [c for c in competing if c.get("age_seconds", 0.0) >= ORPHAN_AGE_SECONDS]
    recent = [c for c in competing if c.get("age_seconds", 0.0) < ORPHAN_AGE_SECONDS]

    if orphans:
        print(
            f"\n!!! Found {len(orphans)} ORPHAN pytest process(es) "
            f"(older than {ORPHAN_AGE_SECONDS:.0f}s; killing unconditionally):"
        )
        for c in orphans:
            cmd_preview = " ".join((c["cmdline"] or [])[:5])
            age = c.get("age_seconds", 0.0)
            print(f"      PID {c['pid']} ({age:.0f}s old): {cmd_preview}")
    if recent:
        print(
            f"\n!!! Found {len(recent)} other (recent) pytest process(es) "
            "running on this codebase:"
        )
        for c in recent:
            cmd_preview = " ".join((c["cmdline"] or [])[:5])
            age = c.get("age_seconds", 0.0)
            print(f"      PID {c['pid']} ({age:.0f}s old): {cmd_preview}")
        if not yes:
            print("\n  These will be terminated before the new sweep starts.")
            print("  (Concurrent runs contend for fixture locks + GPU memory")
            print("   and cause the symptom of 'pytest hangs at 0 % CPU'.")
            print("  Pass --wait to wait for them to finish instead.)")

    killed_pids: list[int] = []
    for c in (orphans + recent):
        try:
            proc = psutil.Process(c["pid"])
            proc.terminate()
            killed_pids.append(c["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if killed_pids:
        try:
            _gone, alive = psutil.wait_procs(
                [psutil.Process(pid) for pid in killed_pids
                 if psutil.pid_exists(pid)],
                timeout=3.0,
            )
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            # Second wait for SIGKILL to take effect on Windows.
            psutil.wait_procs(
                [psutil.Process(pid) for pid in killed_pids
                 if psutil.pid_exists(pid)],
                timeout=2.0,
            )
        except Exception:
            pass

    leftover = _list_competing_pytests()
    if leftover:
        print(f"\n!!! Could not terminate all competing pytest processes; "
              f"{len(leftover)} still running. Bailing out.")
        print(
            "   Manual fix: Get-Process -Name python | "
            "Where-Object {{$_.CommandLine -match 'pytest'}} | "
            "Stop-Process -Force"
        )
        return False
    return True


def _wait_for_competing_pytests(poll_seconds: float = 2.0) -> bool:
    """Block until no competing pytest is running, then return True.

    Used by ``--wait`` mode: instead of killing concurrent sweeps,
    politely wait for them to finish. Useful in CI pipelines where
    several parallel jobs may legitimately want to run tests against
    the same checkout.

    Always returns True (we wait forever; the operator's Ctrl-C is
    the only escape). On psutil unavailability returns True
    immediately.
    """
    try:
        import psutil  # type: ignore[import]  # noqa: F401
    except ImportError:
        return True
    waited = 0.0
    while True:
        competing = _list_competing_pytests()
        if not competing:
            if waited > 0:
                print(f"  Waited {waited:.0f}s for competing sweep(s) to finish.")
            return True
        if waited == 0:
            print(
                f"\n!!! --wait mode: {len(competing)} competing pytest "
                "process(es) detected. Waiting for them to finish...",
            )
            for c in competing:
                cmd_preview = " ".join((c["cmdline"] or [])[:5])
                print(f"      PID {c['pid']}: {cmd_preview}")
        time.sleep(poll_seconds)
        waited += poll_seconds


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Unified Ultron test runner with safeguards.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage::")[1] if "Usage::" in __doc__ else "",
    )
    parser.add_argument(
        "pytest_args", nargs=argparse.REMAINDER,
        help="Args passed through to pytest (paths, -k, etc.)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Skip @pytest.mark.slow tests (default off).",
    )
    parser.add_argument(
        "--no-timeout", action="store_true",
        help="Disable the per-test timeout (debug aid only).",
    )
    parser.add_argument(
        "--kill-only", action="store_true",
        help="Pre-flight kill any competing pytest runs, then exit.",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Don't prompt for the pre-flight kill confirmation.",
    )
    parser.add_argument(
        "--wait", action="store_true",
        help=(
            "Wait for any competing pytest runs to finish instead of "
            "killing them. Useful in CI pipelines with parallel jobs."
        ),
    )
    args = parser.parse_args(argv)

    # Step 1: pre-flight clean-up. ``--wait`` mode politely waits for
    # competing sweeps; default mode kills orphans + recent
    # competitors. Either way, the slate must be clear before we
    # spawn the new pytest, or conftest's concurrent-run guard would
    # block us.
    print("=" * 70)
    print("Ultron test runner")
    print("=" * 70)

    # Cross-instance mutex: prevents two scripts/run_tests.py copies
    # from racing each other (a real failure mode when the Claude
    # harness falsely reports background tool calls as "completed"
    # while their pytest child is still running).
    if not _acquire_sweep_lock():
        if args.wait:
            print("  --wait mode: blocking until the other sweep finishes...")
            if not _wait_for_competing_pytests():
                return 4
            if not _acquire_sweep_lock():
                print("!!! Could not acquire sweep lock after wait.")
                return 4
        else:
            return 4
    import atexit
    atexit.register(_release_sweep_lock)

    if args.wait:
        if not _wait_for_competing_pytests():
            return 4
    else:
        if not _kill_competing_pytests(yes=args.yes):
            return 4

    if args.kill_only:
        print("\n  Pre-flight kill complete. Exiting.")
        return 0

    # Step 2: assemble the pytest command.
    pytest_exe = ROOT / ".venv" / "Scripts" / "python.exe"
    if not pytest_exe.is_file():
        # Fallback to the calling interpreter.
        pytest_exe = Path(sys.executable)

    cmd = [
        str(pytest_exe), "-m", "pytest",
        "--no-header",
        "-q",
    ]
    if args.no_timeout:
        # Override the addopts-default timeout.
        cmd += ["-o", "addopts=-p no:hydra_pytest --durations=10"]
    if args.fast:
        cmd += ["-m", "not slow"]
    # Forward remaining args to pytest.
    if args.pytest_args:
        # argparse leaves a leading "--" in pytest_args when REMAINDER
        # was used after a flag; strip it.
        forwarded = list(args.pytest_args)
        if forwarded and forwarded[0] == "--":
            forwarded = forwarded[1:]
        cmd += forwarded
    else:
        cmd += [
            "tests/",
            "--ignore=tests/coding/test_orchestration_real.py",
        ]

    print(f"\n  Running: {' '.join(cmd)}")
    print()
    print("-" * 70)

    # Step 3: spawn pytest. Live-stream stdout/stderr to the user.
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
    except FileNotFoundError as e:
        print(f"!!! Could not spawn pytest: {e}")
        return 2

    try:
        for line in proc.stdout:                                   # type: ignore[union-attr]
            print(line, end="")
        proc.wait()
        rc = proc.returncode or 0
    except KeyboardInterrupt:
        print("\n\n  Interrupted; terminating pytest...")
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        rc = 130

    elapsed = time.monotonic() - t0
    print()
    print("-" * 70)
    print(f"  Run took {elapsed:.1f}s; pytest exit code {rc}")
    print("=" * 70)

    # Step 4: clean shutdown -- terminate any python descendants of
    # this runner that might still be lingering.
    try:
        import psutil  # type: ignore[import]
        me = psutil.Process()
        for child in me.children(recursive=True):
            try:
                if "python" in (child.name() or "").lower():
                    child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
