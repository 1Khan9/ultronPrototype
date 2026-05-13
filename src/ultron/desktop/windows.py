"""Window enumeration + foreground detection via ``pywin32`` + ``psutil``.

Returns a :class:`WindowInfo` per visible top-level window with the
title, owning process name, and the index of the monitor it primarily
sits on. Use cases:

- "what app is the user looking at right now" -> :func:`get_foreground_window`
- "find the Chrome window on monitor 2" -> :func:`find_window`
- "list everything visible" -> :func:`enumerate_windows`

Fail-open: any pywin32 / psutil exception per window degrades to skipping
that window rather than raising up to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import psutil  # type: ignore[import]
import win32con  # type: ignore[import]
import win32gui  # type: ignore[import]
import win32process  # type: ignore[import]

from ultron.desktop.monitors import Monitor, enumerate_monitors
from ultron.utils.logging import get_logger

logger = get_logger("desktop.windows")


@dataclass(frozen=True)
class WindowInfo:
    """One top-level window.

    Attributes:
        hwnd: Win32 window handle.
        title: window title (post-Unicode normalisation; may be empty).
        class_name: Win32 window class name.
        process_name: owning process exe name (``chrome.exe``, ``Cursor.exe``);
            empty string when lookup fails.
        pid: owning process id; 0 when lookup fails.
        rect: (left, top, right, bottom) in virtual-screen coordinates.
        monitor_index: index of the monitor the window primarily sits on
            (greatest-overlap rule). None when the window is fully offscreen.
        is_minimized: True when iconic (minimized to taskbar).
        is_foreground: True when this window is currently the focused window.
    """

    hwnd: int
    title: str
    class_name: str
    process_name: str
    pid: int
    rect: tuple[int, int, int, int]
    monitor_index: Optional[int]
    is_minimized: bool
    is_foreground: bool

    @property
    def width(self) -> int:
        return max(0, self.rect[2] - self.rect[0])

    @property
    def height(self) -> int:
        return max(0, self.rect[3] - self.rect[1])

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.rect
        return ((l + r) // 2, (t + b) // 2)


def _monitor_index_for_rect(
    rect: tuple[int, int, int, int],
    monitors: list[Monitor],
) -> Optional[int]:
    """Index of the monitor with the most overlap with rect.

    Returns None when there's no overlap with any monitor.
    """
    l, t, r, b = rect
    if r <= l or b <= t:
        return None
    best_idx: Optional[int] = None
    best_overlap = 0
    for m in monitors:
        ox = max(0, min(r, m.right) - max(l, m.x))
        oy = max(0, min(b, m.bottom) - max(t, m.y))
        overlap = ox * oy
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = m.index
    return best_idx


def _process_name_for_pid(pid: int) -> str:
    """Fetch the exe name for ``pid``; empty string on any failure."""
    if pid <= 0:
        return ""
    try:
        return psutil.Process(pid).name() or ""
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""
    except Exception as e:  # noqa: BLE001
        logger.debug("psutil lookup failed for pid %d: %s", pid, e)
        return ""


def _build_window_info(
    hwnd: int,
    monitors: list[Monitor],
    fg_hwnd: int,
) -> Optional[WindowInfo]:
    """Build a :class:`WindowInfo` for ``hwnd``; None when the window can't be inspected."""
    try:
        title = win32gui.GetWindowText(hwnd) or ""
        class_name = win32gui.GetClassName(hwnd) or ""
        rect = win32gui.GetWindowRect(hwnd)  # (l, t, r, b)
        is_min = bool(win32gui.IsIconic(hwnd))
    except Exception as e:  # noqa: BLE001
        logger.debug("window inspect failed hwnd=%d: %s", hwnd, e)
        return None

    try:
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:  # noqa: BLE001
        pid = 0

    return WindowInfo(
        hwnd=int(hwnd),
        title=title,
        class_name=class_name,
        process_name=_process_name_for_pid(int(pid)),
        pid=int(pid),
        rect=(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])),
        monitor_index=_monitor_index_for_rect(rect, monitors),
        is_minimized=is_min,
        is_foreground=(int(hwnd) == int(fg_hwnd)),
    )


def enumerate_windows(
    *,
    include_minimized: bool = False,
    include_invisible: bool = False,
    require_title: bool = True,
) -> list[WindowInfo]:
    """List top-level windows.

    Args:
        include_minimized: include windows iconic to the taskbar.
        include_invisible: include windows hidden via ``ShowWindow(SW_HIDE)``
            and tool windows that don't appear in the alt-tab list.
        require_title: skip windows with empty title text (Explorer's
            shell windows, hidden helper windows, etc.).

    Returns the visible windows, in arbitrary order. Sort externally
    if a particular order is needed (e.g. foreground first).
    """
    monitors = enumerate_monitors()
    try:
        fg = win32gui.GetForegroundWindow()
    except Exception:  # noqa: BLE001
        fg = 0

    results: list[WindowInfo] = []

    def _enum_cb(hwnd: int, _) -> bool:
        try:
            visible = bool(win32gui.IsWindowVisible(hwnd))
        except Exception:  # noqa: BLE001
            return True
        if not include_invisible and not visible:
            return True

        info = _build_window_info(hwnd, monitors, fg)
        if info is None:
            return True
        if require_title and not info.title.strip():
            return True
        if not include_minimized and info.is_minimized:
            return True
        results.append(info)
        return True

    try:
        win32gui.EnumWindows(_enum_cb, None)
    except Exception as e:  # noqa: BLE001
        logger.warning("EnumWindows failed: %s", e)

    return results


def get_foreground_window() -> Optional[WindowInfo]:
    """Return the currently focused window, or None when there isn't one."""
    monitors = enumerate_monitors()
    try:
        hwnd = win32gui.GetForegroundWindow()
    except Exception as e:  # noqa: BLE001
        logger.warning("GetForegroundWindow failed: %s", e)
        return None
    if not hwnd:
        return None
    info = _build_window_info(int(hwnd), monitors, int(hwnd))
    if info is None:
        return None
    return info


def find_window(
    query: str,
    *,
    prefer_foreground: bool = True,
    prefer_monitor: Optional[int] = None,
    by_process: bool = True,
) -> Optional[WindowInfo]:
    """Find a window whose title (and optionally process name) matches ``query``.

    Matching:

    - Case-insensitive substring against title.
    - When ``by_process`` is True, also matches case-insensitive
      substring against process name (so ``"chrome"`` finds
      ``chrome.exe``'s window even when the title is the page name).

    Tiebreakers, in order:

    1. Exact title match wins over substring.
    2. ``prefer_foreground=True`` prefers the foreground window.
    3. ``prefer_monitor`` (when set) prefers windows whose
       ``monitor_index`` matches.
    4. Most recently enumerated (z-order) wins last.
    """
    q = (query or "").strip().lower()
    if not q:
        return None

    candidates: list[WindowInfo] = []
    for w in enumerate_windows():
        title_lower = w.title.lower()
        proc_lower = w.process_name.lower()
        title_match = q in title_lower
        proc_match = by_process and q in proc_lower
        if title_match or proc_match:
            candidates.append(w)

    if not candidates:
        return None

    def _score(w: WindowInfo) -> tuple[int, int, int]:
        title_lower = w.title.lower()
        exact = 1 if title_lower == q else 0
        fg = 1 if (prefer_foreground and w.is_foreground) else 0
        mon = 1 if (prefer_monitor is not None and w.monitor_index == prefer_monitor) else 0
        return (exact, fg, mon)

    candidates.sort(key=_score, reverse=True)
    return candidates[0]
