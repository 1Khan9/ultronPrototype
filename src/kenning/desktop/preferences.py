"""Desktop preference learning -- write successful actions to a local
JSONL log AND (when wired) to the OpenClaw memory-wiki.

The pattern is the one the user named in conversation:

    "user opens YouTube fullscreen on monitor 2"  ->  next time
    "open YouTube", the default placement is monitor 2 fullscreen.

Storage shape:

    logs/desktop_preferences.jsonl     -- local, always written, the
                                          source of truth for query.
    ~/.openclaw/workspace/MEMORY.md    -- optional, when the OpenClaw
                                          WorkspaceWriter is wired in
                                          via :func:`set_workspace_writer`,
                                          a one-liner per successful
                                          action is appended so
                                          OpenClaw agents can read it.

Querying:

    :func:`find_preference_for_phrase` does a substring match against
    the phrase the user originally said. Recency-weighted: newer entries
    rank ahead of older ones with the same phrase. Returns the most
    recent matching :class:`DesktopPreference` or None.

The launcher / dispatcher hook this on success only. Failures are not
recorded (a failed launch should not become the new default).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any, List, Optional

from kenning.utils.logging import get_logger

logger = get_logger("desktop.preferences")


# Default JSONL path -- relative to project root.
DEFAULT_PREFERENCES_PATH = "logs/desktop_preferences.jsonl"


# ---------------------------------------------------------------------------
# DesktopPreference dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesktopPreference:
    """One learned desktop preference.

    Attributes:
        user_phrase: a normalised version of what the user originally
            said ("open youtube on my second monitor"); used as the
            lookup key.
        app_name: app registry name as resolved by the launcher.
        url: URL passed to Chrome, when applicable.
        monitor_index: monitor the window landed on.
        fullscreen: whether the placement was fullscreen.
        maximize: whether the window was maximized.
        success: True for recorded successes; False entries are kept
            for diagnostic purposes but excluded from query results.
        timestamp: ``time.time()`` at write.
    """

    user_phrase: str
    app_name: str
    url: Optional[str] = None
    monitor_index: Optional[int] = None
    fullscreen: bool = False
    maximize: bool = False
    success: bool = True
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Optional WorkspaceWriter hook (OpenClaw memory-wiki integration)
# ---------------------------------------------------------------------------


# When set, successful preferences are mirrored to the OpenClaw workspace
# (one daily memory file + an appended MEMORY.md line per write). The
# orchestrator pushes its OpenClawBridge.workspace via
# :func:`set_workspace_writer` when ``openclaw.enabled=true``.
_workspace_writer: Any = None
_workspace_lock = Lock()


def set_workspace_writer(writer: Any) -> None:
    """Register the OpenClaw WorkspaceWriter (or None to clear).

    Memory writes via the writer happen asynchronously on a separate
    thread so :meth:`PreferenceLogger.record` stays sync + fast.
    """
    global _workspace_writer
    with _workspace_lock:
        _workspace_writer = writer


def get_workspace_writer() -> Any:
    """Return the registered WorkspaceWriter, or None."""
    return _workspace_writer


def _format_for_workspace(pref: DesktopPreference) -> str:
    """Format a preference as a single Markdown line for MEMORY.md.

    Shape:
        - 14:32 user said "open youtube on my second monitor" -> launched chrome on monitor 2 with maximize
    """
    parts = [f'user said "{pref.user_phrase}" ->']
    parts.append(f"launched {pref.app_name}")
    if pref.monitor_index is not None:
        parts.append(f"on monitor {pref.monitor_index + 1}")  # 1-indexed for readability
    flags: List[str] = []
    if pref.fullscreen:
        flags.append("fullscreen")
    if pref.maximize:
        flags.append("maximized")
    if flags:
        parts.append("with " + " + ".join(flags))
    if pref.url:
        parts.append(f"(URL: {pref.url})")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# PreferenceLogger
# ---------------------------------------------------------------------------


class PreferenceLogger:
    """Append-only JSONL writer for desktop preferences.

    Thread-safe. Records on a sync write path; OpenClaw workspace
    mirroring runs in a daemon thread so the launcher hot-path doesn't
    block on filesystem IO across two locations.
    """

    def __init__(self, log_path: Path) -> None:
        self.log_path = Path(log_path)
        self._lock = Lock()
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "preference log parent mkdir failed (%s): %s",
                self.log_path.parent, e,
            )

    def record(self, pref: DesktopPreference) -> bool:
        """Append a preference to the JSONL log.

        Returns True on successful local write. Workspace-writer
        mirror happens in a daemon thread regardless.
        """
        if not pref.success:
            # Diagnostic entry only; still record for debugging.
            pass

        payload = asdict(pref)
        # Stamp timestamp if caller didn't.
        if payload["timestamp"] in (0, 0.0, None):
            payload["timestamp"] = time.time()

        line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        try:
            with self._lock, self.log_path.open(
                "a", encoding="utf-8", newline="\n",
            ) as f:
                f.write(line + "\n")
        except OSError as e:
            logger.warning("preference log write failed: %s", e)
            return False

        # Mirror to OpenClaw workspace when wired. Daemon thread so
        # filesystem IO doesn't block the launcher hot path.
        writer = get_workspace_writer()
        if writer is not None and pref.success:
            import threading

            def _mirror() -> None:
                try:
                    self._write_to_workspace(writer, pref)
                except Exception as e:  # noqa: BLE001
                    logger.debug("workspace mirror failed: %s", e)

            t = threading.Thread(
                target=_mirror, daemon=True,
                name="desktop-pref-workspace-mirror",
            )
            t.start()

        return True

    def _write_to_workspace(
        self,
        writer: Any,
        pref: DesktopPreference,
    ) -> None:
        """Push a preference line to OpenClaw's daily memory file.

        The :class:`OpenClawWorkspaceWriter` API is async; we call
        through an event loop here. Failures are swallowed -- the
        local JSONL log is the source of truth.
        """
        import asyncio
        from datetime import datetime

        line = _format_for_workspace(pref)
        date_str = datetime.fromtimestamp(pref.timestamp or time.time()).strftime("%Y-%m-%d")

        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(writer.write_memory_entry(
                    entry=line, date=date_str, prefix_timestamp=True,
                ))
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("workspace write_memory_entry failed: %s", e)

    def read_all(self, *, max_age_days: Optional[float] = None) -> List[DesktopPreference]:
        """Read every preference from the log.

        Args:
            max_age_days: when set, drop entries older than this.

        Returns the preferences in write order (oldest first). Empty
        on missing or unreadable log.
        """
        if not self.log_path.exists():
            return []
        cutoff = (
            time.time() - max_age_days * 86400.0
            if max_age_days is not None and max_age_days > 0
            else None
        )
        out: List[DesktopPreference] = []
        try:
            with self._lock, self.log_path.open(
                "r", encoding="utf-8", errors="ignore",
            ) as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if cutoff is not None and obj.get("timestamp", 0) < cutoff:
                        continue
                    out.append(_from_dict(obj))
        except OSError as e:
            logger.warning("preference log read failed: %s", e)
            return []
        return out


def _from_dict(obj: dict) -> DesktopPreference:
    """Build a DesktopPreference from a JSONL row. Missing fields use defaults."""
    return DesktopPreference(
        user_phrase=str(obj.get("user_phrase", "")),
        app_name=str(obj.get("app_name", "")),
        url=obj.get("url"),
        monitor_index=obj.get("monitor_index"),
        fullscreen=bool(obj.get("fullscreen", False)),
        maximize=bool(obj.get("maximize", False)),
        success=bool(obj.get("success", True)),
        timestamp=float(obj.get("timestamp", 0.0)),
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def find_preference_for_phrase(
    phrase: str,
    *,
    logger_instance: Optional[PreferenceLogger] = None,
    max_age_days: float = 90.0,
    min_substring_length: int = 4,
) -> Optional[DesktopPreference]:
    """Look up the most recent successful preference whose ``user_phrase``
    overlaps with ``phrase``.

    Matching: normalised lowercase substring. ``"open youtube"`` finds
    a stored ``"open youtube on my second monitor"``.

    Args:
        phrase: the user's current utterance (lowercased + trimmed
            for comparison).
        logger_instance: which logger to read from. Defaults to the
            singleton.
        max_age_days: ignore preferences older than this.
        min_substring_length: require at least this much overlap
            (avoids returning a preference for ``"o"`` matching every
            ``"open ..."`` phrase).
    """
    q = (phrase or "").lower().strip()
    if not q or len(q) < min_substring_length:
        return None
    lg = logger_instance if logger_instance is not None else get_preference_logger()
    if lg is None:
        return None
    prefs = lg.read_all(max_age_days=max_age_days)
    if not prefs:
        return None

    # Filter to successful + substring-match.
    matches = [
        p for p in prefs
        if p.success and q in p.user_phrase.lower()
    ]
    if not matches:
        # Try the reverse direction (stored is a substring of query).
        matches = [
            p for p in prefs
            if p.success
            and p.user_phrase.lower()
            and p.user_phrase.lower() in q
        ]
    if not matches:
        return None
    # Most recent wins.
    matches.sort(key=lambda p: p.timestamp, reverse=True)
    return matches[0]


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_singleton: Optional[PreferenceLogger] = None
_singleton_lock = Lock()


def get_preference_logger(
    *,
    path: Optional[Path] = None,
) -> Optional[PreferenceLogger]:
    """Module-level singleton accessor.

    Constructs a default :class:`PreferenceLogger` rooted at the
    project's ``logs/desktop_preferences.jsonl`` when no path is
    provided. Returns None when the project root can't be discovered.
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    with _singleton_lock:
        if _singleton is not None:
            return _singleton
        target = path
        if target is None:
            try:
                from kenning.config import PROJECT_ROOT
                target = PROJECT_ROOT / DEFAULT_PREFERENCES_PATH
            except Exception as e:  # noqa: BLE001
                logger.debug("project root resolution failed: %s", e)
                return None
        try:
            _singleton = PreferenceLogger(Path(target))
        except Exception as e:  # noqa: BLE001
            logger.warning("preference logger construction failed: %s", e)
            return None
    return _singleton


def set_preference_logger(lg: Optional[PreferenceLogger]) -> None:
    """Test / orchestrator hook -- swap the singleton."""
    global _singleton
    with _singleton_lock:
        _singleton = lg


# ---------------------------------------------------------------------------
# Convenience: record from a LaunchResult + intent
# ---------------------------------------------------------------------------


def record_launch_preference(
    *,
    user_phrase: str,
    app_name: str,
    monitor_index: Optional[int],
    fullscreen: bool,
    maximize: bool,
    url: Optional[str] = None,
    success: bool = True,
) -> bool:
    """High-level helper for the dispatcher / voice handler to call after a launch.

    Encapsulates ``DesktopPreference`` construction + the singleton
    lookup so callers don't have to import everything. Fail-open:
    returns False on any error.
    """
    if not user_phrase or not app_name:
        return False
    pref = DesktopPreference(
        user_phrase=user_phrase.strip().lower(),
        app_name=app_name,
        url=url,
        monitor_index=monitor_index,
        fullscreen=bool(fullscreen),
        maximize=bool(maximize),
        success=bool(success),
        timestamp=time.time(),
    )
    lg = get_preference_logger()
    if lg is None:
        return False
    return lg.record(pref)


__all__ = [
    "DEFAULT_PREFERENCES_PATH",
    "DesktopPreference",
    "PreferenceLogger",
    "find_preference_for_phrase",
    "get_preference_logger",
    "get_workspace_writer",
    "record_launch_preference",
    "set_preference_logger",
    "set_workspace_writer",
]
