"""Phase 4 — structured error log writer.

Writes one JSON object per line to ``logs/errors.jsonl``. Each entry
records the dependency, the typed exception, the call context, and the
recovery action the wrapper took.

Designed to be cheap (best-effort append, no blocking) and never
itself a source of failure: a write error logs to the in-process logger
and otherwise does nothing.

Usage::

    from kenning.errors import BraveAPIError
    from kenning.resilience import get_error_log

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
from typing import Any, Callable, Dict, Optional

from kenning.config import resolve_path
from kenning.errors import KenningError
from kenning.utils.ansi_safe import sanitize_for_log
from kenning.utils.logging import get_logger

logger = get_logger("resilience.error_log")


def _sanitize_record(value: Any) -> Any:
    """Recursively strip ANSI + control chars from string leaves.

    Defends against CWE-117 log forging via attacker-controlled
    exception messages (network responses, subprocess stderr, etc.).
    Fail-open per leaf so a sanitiser exception never drops the
    record.
    """
    try:
        if isinstance(value, str):
            return sanitize_for_log(value)
        if isinstance(value, dict):
            return {str(k): _sanitize_record(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            cleaned = [_sanitize_record(v) for v in value]
            return cleaned if isinstance(value, list) else tuple(cleaned)
        return value
    except Exception:  # noqa: BLE001
        return value


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
            error: the exception that was caught. ``KenningError``
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

        if isinstance(error, KenningError):
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

        # T18 (openclaw-main catalog port): strip ANSI + control bytes
        # from attacker-influenced string fields. CVE-class defence
        # against log forging via fake-newline / cursor-jump in
        # exception messages (subprocess stderr, HTTP response bodies,
        # etc.). Fail-open per leaf -- never drop a record because
        # sanitisation glitched on an exotic encoding.
        record = _sanitize_record(record)

        try:
            with self._lock:
                with self._path.open("a", encoding="utf-8") as f:
                    json.dump(record, f, default=str)
                    f.write("\n")
        except OSError as e:
            # Logging the error log's own failure: in-process logger only.
            # Never raise from here.
            logger.error("errors.jsonl write failed: %s", e)

        # Evolution reach-signals (#62/#125/#64): notify the registered
        # observer of every recorded failure so the self-improvement loop
        # can learn from RECURRING dependency failures (web search, Qdrant,
        # desktop, bridge, TTS, ...) through ONE seam instead of per-site
        # plumbing. Pure observation, after the write, fail-open -- an
        # observer error can never drop a record or raise to the caller.
        observer = _error_observer
        if observer is not None:
            try:
                observer(dependency, str(record.get("message", "")))
            except Exception as e:  # noqa: BLE001
                logger.debug("error observer failed: %s", e)


# ---------------------------------------------------------------------------
# Error observer (evolution reach-signals #62/#125/#64)
# ---------------------------------------------------------------------------

#: Optional ``(dependency, message) -> None`` callback fired after every
#: recorded error. Observation only -- it cannot drop or alter records.
_error_observer: Optional[Callable[[str, str], None]] = None


def set_error_observer(observer: Optional[Callable[[str, str], None]]) -> None:
    """Register (or clear, with ``None``) the recorded-error observer.

    The orchestrator registers a bounded-queue enqueue here so the
    evolution service can learn from recurring dependency failures
    anywhere in the system (web search, memory, desktop, bridge, TTS --
    every subsystem that records typed errors flows through this one
    seam). The observer runs AFTER the JSONL write and is wrapped
    fail-open at the call site; it can never raise to the caller.
    """
    global _error_observer
    _error_observer = observer


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


__all__ = ["ErrorLog", "get_error_log", "set_error_log", "set_error_observer"]
