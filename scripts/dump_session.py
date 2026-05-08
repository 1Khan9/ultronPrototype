"""Render a coding session's audit log into a human-readable transcript.

The orchestrator writes per-session JSONL files to
``logs/sessions/<session_id>.jsonl`` (each line one event: state
transition, clarification request/answer, file change, verification
result, completion claim). This script renders them into a readable
walkthrough.

Usage:
    python scripts/dump_session.py <session_id>
    python scripts/dump_session.py logs/sessions/abc123.jsonl
    python scripts/dump_session.py --latest          # most recent
    python scripts/dump_session.py --list            # list available
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO = Path(__file__).resolve().parent.parent
DEFAULT_SESSIONS_DIR = REPO / "logs" / "sessions"


def _resolve_session_path(token: str, sessions_dir: Path) -> Optional[Path]:
    """Accepts a bare session id, a relative path, or an absolute path."""
    p = Path(token)
    if p.is_file():
        return p
    p = sessions_dir / token
    if p.is_file():
        return p
    p = sessions_dir / f"{token}.jsonl"
    if p.is_file():
        return p
    return None


def _read_records(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [warn] {path.name}:{line_no}: malformed JSON ({e})",
                      file=sys.stderr)
    return records


def _format_record(rec: Dict[str, Any]) -> str:
    """One line per record. Different record types format differently."""
    kind = rec.get("kind") or rec.get("type") or rec.get("event") or "?"
    ts = rec.get("ts") or rec.get("timestamp") or ""
    ts_short = ts.split("T", 1)[1].split(".", 1)[0] if "T" in str(ts) else str(ts)
    if kind in ("transition", "state_transition"):
        return f"  {ts_short}  → {rec.get('to_status', '?')}"
    if kind == "stage":
        return (
            f"  {ts_short}  STAGE  {rec.get('stage', '?')}: "
            f"{rec.get('summary', '')}"
        )
    if kind == "clarification_request":
        return (
            f"  {ts_short}  CLARIFY?  {rec.get('question', '')}"
        )
    if kind == "clarification_resolved":
        return (
            f"  {ts_short}  CLARIFY!  → {rec.get('answer', '')}"
        )
    if kind == "adjustment":
        return f"  {ts_short}  ADJUST  {rec.get('text', '')}"
    if kind in ("file_change", "file_recorded"):
        op = rec.get("kind_of_change") or rec.get("op") or "modify"
        return f"  {ts_short}  FILE {op:>8s}  {rec.get('path', '')}"
    if kind == "test_results":
        return (
            f"  {ts_short}  TESTS  {rec.get('passing', 0)} passing, "
            f"{rec.get('failing', 0)} failing"
        )
    if kind == "verification":
        passed = rec.get("passed", "?")
        return f"  {ts_short}  VERIFY  passed={passed}"
    if kind == "completion_claim":
        return (
            f"  {ts_short}  COMPLETE  {rec.get('summary', '')}\n"
            f"          entry={rec.get('entry_point') or '-'}  "
            f"run={rec.get('run_command') or '-'}"
        )
    if kind == "usage":
        return (
            f"  {ts_short}  USAGE  in={rec.get('input', 0)}  "
            f"out={rec.get('output', 0)}"
        )
    if kind == "prompt_sent":
        prev = (rec.get("prompt") or "")[:120]
        return f"  {ts_short}  PROMPT  {prev!r}{'...' if len(prev) >= 120 else ''}"
    # Fallback: render kind + a few interesting fields.
    interesting = ", ".join(
        f"{k}={v}" for k, v in rec.items()
        if k not in {"ts", "timestamp", "kind", "type", "event", "session_id"}
    )
    if len(interesting) > 200:
        interesting = interesting[:200] + "..."
    return f"  {ts_short}  {kind:14s}  {interesting}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dump a coding-session audit log.")
    parser.add_argument("session", nargs="?", help="session id or path")
    parser.add_argument("--latest", action="store_true",
                        help="dump the most recently modified session")
    parser.add_argument("--list", action="store_true",
                        help="list available sessions and exit")
    parser.add_argument("--sessions-dir", type=Path,
                        default=DEFAULT_SESSIONS_DIR,
                        help="override the sessions directory")
    args = parser.parse_args(argv)

    sessions_dir: Path = args.sessions_dir
    if not sessions_dir.is_dir():
        print(f"sessions directory does not exist: {sessions_dir}",
              file=sys.stderr)
        return 1

    if args.list:
        files = sorted(
            sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            print("(no sessions)")
            return 0
        for f in files:
            mtime = f.stat().st_mtime
            from datetime import datetime
            stamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  {stamp}  {f.stem}  ({f.stat().st_size} B)")
        return 0

    if args.latest:
        files = sorted(
            sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            print("(no sessions)", file=sys.stderr)
            return 1
        path = files[0]
    elif args.session:
        path = _resolve_session_path(args.session, sessions_dir)
        if path is None:
            print(f"session not found: {args.session}", file=sys.stderr)
            return 1
    else:
        parser.print_help(sys.stderr)
        return 2

    print("=" * 70)
    print(f"Session: {path.stem}")
    print(f"File:    {path}")
    print("=" * 70)
    records = _read_records(path)
    if not records:
        print("(empty)")
        return 0
    for rec in records:
        print(_format_record(rec))
    print("=" * 70)
    print(f"Total events: {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
