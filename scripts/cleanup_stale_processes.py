"""Kill stale Kenning-related Python processes safely.

Use case: after a pytest run, an interrupted ``python -m kenning``, or
a crashed background task, Python workers can be left holding RAM and
VRAM. This script finds them and kills them -- while always preserving
a currently-running Kenning instance (detected by port 19761, the MCP
server's listen port).

Usage:

    python scripts/cleanup_stale_processes.py            # dry run; lists
    python scripts/cleanup_stale_processes.py --kill     # actually kills
    python scripts/cleanup_stale_processes.py --kill -y  # skip the prompt

Detection logic:

* Enumerate every running ``python.exe`` process.
* Identify the running Kenning via TCP port 19761; that process and its
  parent chain + child chain are PRESERVED no matter what.
* Identify the running XTTS server via the spawned subprocess (which
  binds an ephemeral port). The Kenning parent chain check covers it.
* Anything else matching the staleness rules below is killed:
   - ``pytest`` in the command line.
   - ``run_kenning_mcp_for_openclaw.py`` from any worktree.
   - ``kenningVoiceAudio\\scripts\\xtts_server.py`` not under the running
     Kenning's parent chain (orphaned voice server from a crashed run).
   - Older than ``--max-age-minutes`` (default 30) Python processes
     with no readable command line AND >= 200 MB RAM (orphaned workers
     from killed-without-cleanup tests).

The script never touches non-Python processes. It never touches the
process chain reachable from the listener on port 19761.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Iterable, Optional

try:
    import psutil
except ImportError:
    print("error: psutil is not installed in this venv", file=sys.stderr)
    sys.exit(2)


KENNING_MCP_PORT = 19761
RUNUP_GUARD_SECONDS = 10  # don't kill a child that started <10s ago


def _processes_holding_port(port: int) -> set[int]:
    """Return {pid} for processes currently listening on ``port``."""
    out: set[int] = set()
    try:
        conns = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, PermissionError):
        return out
    for c in conns:
        if c.laddr and c.laddr.port == port and c.status == "LISTEN":
            if c.pid:
                out.add(c.pid)
    return out


def _ancestors(pid: int) -> set[int]:
    """Return the set of ancestor PIDs (parent, grandparent, ...) for pid."""
    out: set[int] = set()
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return out
    while True:
        try:
            parent = p.parent()
        except psutil.NoSuchProcess:
            break
        if parent is None:
            break
        out.add(parent.pid)
        p = parent
    return out


def _descendants(pid: int) -> set[int]:
    """Return the set of descendant PIDs (recursive children) for pid."""
    out: set[int] = set()
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return out
    for child in p.children(recursive=True):
        out.add(child.pid)
    return out


def _is_python(proc: psutil.Process) -> bool:
    """True if the process is python.exe (or python)."""
    try:
        name = (proc.name() or "").lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    return name in {"python.exe", "python", "pythonw.exe", "pythonw"}


def _cmdline(proc: psutil.Process) -> str:
    """Return the command line for ``proc`` as a single string, or ''."""
    try:
        return " ".join(proc.cmdline() or [])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def _rss_mb(proc: psutil.Process) -> float:
    try:
        return proc.memory_info().rss / 1024 / 1024
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0.0


def _age_minutes(proc: psutil.Process) -> float:
    try:
        return (time.time() - proc.create_time()) / 60.0
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0.0


def find_running_kenning() -> set[int]:
    """Return the set of PIDs we must preserve (the running Kenning stack).

    Computed as: the process holding port 19761, plus its ancestors,
    plus all its descendants. The XTTS server is a child of the
    orchestrator and therefore caught by the descendant scan.
    """
    holders = _processes_holding_port(KENNING_MCP_PORT)
    if not holders:
        return set()
    preserved: set[int] = set(holders)
    for pid in holders:
        preserved |= _ancestors(pid)
        preserved |= _descendants(pid)
    return preserved


def is_stale(
    proc: psutil.Process,
    *,
    preserved: set[int],
    max_age_minutes: float,
    min_rss_mb_unknown: float,
) -> Optional[str]:
    """Return a short reason string when ``proc`` should be killed,
    otherwise None."""
    if proc.pid in preserved:
        return None
    if not _is_python(proc):
        return None
    age = _age_minutes(proc)
    if age < RUNUP_GUARD_SECONDS / 60.0:
        # Don't kill processes that just started -- could be a fresh
        # pytest run the user just kicked off.
        return None
    cmd = _cmdline(proc).lower()
    if "pytest" in cmd:
        return "pytest worker"
    if "run_kenning_mcp_for_openclaw.py" in cmd:
        return "stale MCP-stub (run_kenning_mcp_for_openclaw)"
    if "run_ultron_mcp_for_openclaw.py" in cmd:
        # Pre-rename (2026-06-12) script name: a stale process spawned
        # before the Kenning rename can outlive the rename itself.
        return "stale MCP-stub (legacy run_ultron_mcp_for_openclaw)"
    if "xtts_server.py" in cmd:
        # The currently-running XTTS would have been pulled in via the
        # preserved descendant scan; reaching here means it's orphaned.
        return "orphan XTTS server"
    if not cmd and age >= max_age_minutes and _rss_mb(proc) >= min_rss_mb_unknown:
        return (
            f"orphan python worker (no cmdline, "
            f"age={age:.1f} min, rss={_rss_mb(proc):.0f} MB)"
        )
    return None


def enumerate_targets(
    *,
    preserved: set[int],
    max_age_minutes: float,
    min_rss_mb_unknown: float,
) -> list[tuple[psutil.Process, str]]:
    """List every (proc, reason) pair that ``is_stale`` flagged."""
    targets: list[tuple[psutil.Process, str]] = []
    for proc in psutil.process_iter(attrs=["pid", "name"]):
        try:
            reason = is_stale(
                proc,
                preserved=preserved,
                max_age_minutes=max_age_minutes,
                min_rss_mb_unknown=min_rss_mb_unknown,
            )
        except psutil.NoSuchProcess:
            continue
        if reason:
            targets.append((proc, reason))
    return targets


def kill(procs: Iterable[psutil.Process], *, timeout: float = 5.0) -> tuple[int, int, float]:
    """Terminate then (after timeout) kill the given processes.

    Returns (killed_count, failed_count, freed_mb).
    """
    killed = 0
    failed = 0
    freed = 0.0
    snapshot = []
    for p in procs:
        try:
            snapshot.append((p, _rss_mb(p)))
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"  ! could not terminate PID {p.pid}: {e}", file=sys.stderr)
            failed += 1
    if not snapshot:
        return 0, 0, 0.0
    gone, alive = psutil.wait_procs(
        [p for p, _ in snapshot], timeout=timeout,
    )
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"  ! could not kill PID {p.pid}: {e}", file=sys.stderr)
            failed += 1
    for p, mb in snapshot:
        if not p.is_running():
            killed += 1
            freed += mb
    return killed, failed, freed


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kill stale Kenning-related Python processes "
            "(pytest workers, orphaned MCP stubs, orphaned XTTS servers)."
        ),
    )
    parser.add_argument(
        "--kill", action="store_true",
        help="actually terminate the listed processes. Without this flag "
             "the script only prints what it would kill (dry-run).",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true",
        help="skip the confirmation prompt (used with --kill).",
    )
    parser.add_argument(
        "--max-age-minutes", type=float, default=30.0,
        help="treat unknown-cmdline python workers older than this as "
             "stale (default: 30 minutes).",
    )
    parser.add_argument(
        "--min-rss-mb-unknown", type=float, default=200.0,
        help="only kill unknown-cmdline workers with at least this much "
             "RAM (default: 200 MB).",
    )
    args = parser.parse_args(argv)

    preserved = find_running_kenning()
    if preserved:
        print(
            f"running Kenning detected (port {KENNING_MCP_PORT}): "
            f"preserving PIDs {sorted(preserved)}"
        )
    else:
        print(
            f"no running Kenning detected on port {KENNING_MCP_PORT}; "
            f"nothing will be preserved by the port-listener rule"
        )

    targets = enumerate_targets(
        preserved=preserved,
        max_age_minutes=args.max_age_minutes,
        min_rss_mb_unknown=args.min_rss_mb_unknown,
    )

    if not targets:
        print("no stale processes found.")
        return 0

    print()
    print(f"{'PID':>7}  {'AGE_MIN':>7}  {'RSS_MB':>7}  REASON  CMDLINE")
    print(f"{'-' * 7}  {'-' * 7}  {'-' * 7}  -----------------")
    total_rss = 0.0
    for p, reason in targets:
        rss = _rss_mb(p)
        total_rss += rss
        cmd = _cmdline(p) or "(no cmdline)"
        if len(cmd) > 100:
            cmd = cmd[:97] + "..."
        print(f"{p.pid:>7}  {_age_minutes(p):>7.1f}  {rss:>7.0f}  {reason}  {cmd}")
    print()
    print(f"would kill {len(targets)} processes (~{total_rss:.0f} MB)")

    if not args.kill:
        print()
        print("dry run. add --kill to actually terminate them.")
        return 0

    if not args.yes:
        try:
            answer = input("\nproceed with kill? [y/N]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in {"y", "yes"}:
            print("aborted.")
            return 1

    procs = [p for p, _ in targets]
    killed, failed, freed = kill(procs)
    print()
    print(f"killed {killed} / {len(targets)}; failed {failed}; "
          f"freed ~{freed:.0f} MB")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
