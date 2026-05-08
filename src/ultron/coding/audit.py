"""Phase 7: per-session JSONL audit log.

One file per :class:`ProjectSession`, written under
``logs/sessions/<session_id>.jsonl``. Every state-affecting event is
appended as a JSON record for offline inspection and retrospective
tuning.

Hooks fire from three places:

  * :class:`SessionStore` -- automatic, on every CRUD/transition method.
    This covers the bulk of session activity (state changes, stage
    records, file lists, test results, completion claims, adjustments,
    clarification register/resolve).
  * :class:`ConversationCoordinator` -- on clarification decisions
    (which path was taken, what was answered) and verification cycles
    (per-check breakdown).
  * :class:`CodingTaskRunner` -- on task starts, follow-ups, and the
    prompt sent to Claude (chars only -- the full prompt lives in the
    coding_tasks.jsonl audit log).

The writer is thread-safe (lock-protected file appends). When
``log_dir`` is ``None`` every call is a no-op so unit tests don't spam
the filesystem.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Optional


class SessionAuditWriter:
    """Thread-safe append-only writer for per-session JSONL logs."""

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self.log_dir = Path(log_dir) if log_dir is not None else None
        if self.log_dir is not None:
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Bad path; disable logging gracefully.
                self.log_dir = None
        self._lock = threading.Lock()

    def write(self, session_id: str, event: str, **fields: Any) -> None:
        """Append a JSON record to the session's log file.

        ``event`` is a short snake_case label (e.g. ``transition``,
        ``stage_recorded``, ``clarification_asked``). Extra ``fields``
        are merged into the record verbatim (cast via default=str).
        """
        if self.log_dir is None or not session_id:
            return
        record = {
            "ts": time.time(),
            "session_id": session_id,
            "event": event,
            **fields,
        }
        path = self.log_dir / f"{session_id}.jsonl"
        try:
            with self._lock, path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError:
            # Disk full / permission issue / etc. -- audit logging is
            # best-effort and must never break the supervisor.
            pass

    def path_for(self, session_id: str) -> Optional[Path]:
        """Return the on-disk path for a session's log, or None if disabled."""
        if self.log_dir is None:
            return None
        return self.log_dir / f"{session_id}.jsonl"
