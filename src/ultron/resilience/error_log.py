"""Phase 4 — structured error log writer.

Writes one JSON object per line to ``logs/errors.jsonl``. Each entry
records the dependency, the typed exception, the call context, and the
recovery action the wrapper took.

Designed to be cheap (best-effort append, no blocking) and never
itself a source of failure: a write error logs to the in-process logger
and otherwise does nothing.

Usage::

    from ultron.errors import BraveAPIError
    from ultron.resilience import get_error_log

    err = BraveAPIError("rate limited", context={"query": q})
    err.with_recovery("fell back to base knowledge with caveat")
    get_error_log().record(err, dependency="brave_api")
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ultron.config import resolve_path
from ultron.errors import UltronError
from ultron.utils.logging import get_logger

logger = get_logger("resilience.error_log")


def _default_log_path() -> Path:
    """Resolve ``logs/errors.jsonl`` against the project root."""
    return resolve_path("logs/errors.jsonl")


class ErrorLog:
    """Append-only JSONL writer for structured error records.

    Args:
        path: log file path; defaults to ``logs/errors.jsonl`` under
            project root.

    All public methods are thread-safe.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or _default_log_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def record(
        self,
        error: BaseException,
        *,
        dependency: str,
        session_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        include_traceback: bool = True,
    ) -> None:
        """Append one error record. Best-effort — never raises.

        Args:
            error: the exception that was caught. ``UltronError``
                subclasses contribute ``context`` and ``recovery``;
                generic exceptions log only their message + traceback.
            dependency: short label for the failing dependency
                (``"brave_api"``, ``"qdrant"``, ``"piper_tts"``, etc.)
            session_id: optional coding-session id when the failure
                occurs inside a coding task.
            extra: additional diagnostic key-value pairs (query text,
                URL, etc.). Sensitive content (API keys) MUST NOT be
                logged.
            include_traceback: include a formatted traceback. Default
                True. Disable for high-volume errors where the traceback
                isn't useful.
        """
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "monotonic": time.monotonic(),
            "dependency": dependency,
        }
        if session_id:
            record["session_id"] = session_id

        if isinstance(error, UltronError):
            record.update(error.to_log_dict())
        else:
            record["error_type"] = type(error).__name__
            record["message"] = str(error)
            record["context"] = {}
            record["recovery"] = None

        if extra:
            # Don't let extra clobber structural keys.
            safe_extra = {
                k: v for k, v in extra.items()
                if k not in {"timestamp", "error_type", "message",
                             "context", "recovery", "dependency",
                             "session_id", "monotonic"}
            }
            if safe_extra:
                ctx = record.get("context") or {}
                ctx.update(safe_extra)
                record["context"] = ctx

        if include_traceback:
            tb = "".join(traceback.format_exception(
                type(error), error, error.__traceback__,
            )).strip()
            if tb:
                record["traceback"] = tb

        try:
            with self._lock:
                with self._path.open("a", encoding="utf-8") as f:
                    json.dump(record, f, default=str)
                    f.write("\n")
        except OSError as e:
            # Logging the error log's own failure: in-process logger only.
            # Never raise from here.
            logger.error("errors.jsonl write failed: %s", e)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


_INSTANCE: Optional[ErrorLog] = None
_INSTANCE_LOCK = threading.Lock()


def get_error_log() -> ErrorLog:
    """Module-level singleton. Lazy-initialized on first access."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = ErrorLog()
    return _INSTANCE


def set_error_log(log: ErrorLog) -> None:
    """Test-only: swap the singleton (e.g. point at a tmp_path log)."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = log


__all__ = ["ErrorLog", "get_error_log", "set_error_log"]
