"""Voice matcher + process lifecycle for the settings panel.

The panel runs as a DETACHED subprocess so the voice loop never hosts
UI state: spawning is fire-and-forget, and when the panel closes (its
own Close button, the window X, or the voice "close the settings"
command) the process exits and the pipeline is back to exactly its
prior state with zero residual resources.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from typing import Callable, Optional

logger = logging.getLogger("ultron.settings_gui.launch")

__all__ = ["match_settings_command", "launch_gui", "close_gui"]

_PANEL_WORDS = (
    r"(?:settings(?:\s+(?:panel|gui|menu|page|window))?"
    r"|control\s+panel|config(?:uration)?(?:\s+panel)?|knobs)"
)

_OPEN_RE = re.compile(
    rf"^(?:please\s+)?(?:open|show\s+me|show|pull\s+up|bring\s+up|launch)"
    rf"\s+(?:the\s+|your\s+|my\s+)?{_PANEL_WORDS}\s*[.!?]?$",
    re.IGNORECASE,
)
_CLOSE_RE = re.compile(
    rf"^(?:please\s+)?(?:close|hide|dismiss)"
    rf"\s+(?:the\s+|your\s+|my\s+)?{_PANEL_WORDS}\s*[.!?]?$",
    re.IGNORECASE,
)


def match_settings_command(text: str) -> Optional[str]:
    """Match the strict open/close settings-panel phrasings.

    Args:
        text: the user's transcript for this turn.

    Returns:
        ``"open"`` / ``"close"`` / None. Ordinary sentences that merely
        mention settings ("what are your settings?") never match.
    """
    if not text:
        return None
    cleaned = text.strip()
    if _OPEN_RE.match(cleaned):
        return "open"
    if _CLOSE_RE.match(cleaned):
        return "close"
    return None


def launch_gui(
    *,
    spawn_fn: Optional[Callable[..., "subprocess.Popen"]] = None,
) -> Optional[int]:
    """Spawn the settings panel as a detached process.

    Args:
        spawn_fn: test seam -- called with the same arguments as
            ``subprocess.Popen``.

    Returns:
        The child PID, or None when the spawn failed (logged; the
        caller speaks a clear error -- fail-open).
    """
    try:
        from ultron.config import PROJECT_ROOT

        creationflags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        spawn = spawn_fn or subprocess.Popen
        proc = spawn(
            [sys.executable, "-m", "ultron.settings_gui"],
            cwd=str(PROJECT_ROOT),
            creationflags=creationflags,
            close_fds=True,
        )
        pid = int(getattr(proc, "pid", 0) or 0)
        logger.info("settings panel spawned (pid=%d)", pid)
        return pid or None
    except Exception as e:  # noqa: BLE001 - fail-open
        logger.warning("settings panel spawn failed: %s", e)
        return None


def close_gui(
    pid: Optional[int],
    *,
    kill_fn: Optional[Callable[[int], object]] = None,
) -> bool:
    """Terminate a previously spawned panel.

    Args:
        pid: the PID :func:`launch_gui` returned (None -> nothing to do).
        kill_fn: test seam -- defaults to the repo's
            ``kill_process_tree``.

    Returns:
        True iff a process was terminated.
    """
    if not pid:
        return False
    try:
        if kill_fn is None:
            from ultron.subprocess.kill_tree import kill_process_tree

            kill_fn = kill_process_tree
        kill_fn(pid)
        logger.info("settings panel closed (pid=%d)", pid)
        return True
    except Exception as e:  # noqa: BLE001 - fail-open
        logger.warning("settings panel close failed (pid=%s): %s", pid, e)
        return False
