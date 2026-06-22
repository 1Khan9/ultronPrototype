"""Voice-summoned terminal-log viewer (in-process tkinter).

"Ultron, show me the logs" pops a scrollable, SELECTABLE window streaming the
tail of the runtime log (``logs/kenning.log``) so the user can read it live and
copy text out to document issues. Read-only (select + Ctrl+C, never edits the
file), auto-scrolls unless you scroll up, dark theme.

In-process exactly like the STOP window + waveform overlay: the Tk root lives in
a dedicated daemon thread; a second daemon thread tails the log file and feeds
new text to the Text widget through a thread-safe queue. A log window is an
ordinary window reading our OWN log file -- NOT input monitoring, NOT OS
interaction -- so it adds nothing to the anticheat surface.

Fail-open throughout: no display / no Tk -> the window never appears and the
voice path is untouched.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from collections import deque
from queue import Empty, Queue
from typing import Optional

logger = logging.getLogger("kenning.audio.log_viewer")

__all__ = ["LogViewerOverlay", "match_logs_command"]


# ---------------------------------------------------------------------------
# Voice matcher -- "show / pull up / open the logs" (and "close the logs").
# Strict: a long sentence or a question that merely mentions logs never matches.
# ---------------------------------------------------------------------------
_LOGS_RE = re.compile(
    r"\b(?:logs?|log\s+(?:window|viewer|stream|output|console|terminal|file)|"
    r"terminal\s+(?:logs?|output|stream)|console\s+(?:logs?|output))\b",
    re.IGNORECASE,
)
_OPEN_KW_RE = re.compile(
    r"\b(?:show|pull\s+up|open|bring\s+up|display|let\s+me\s+see|see|view|"
    r"give\s+me|pop\s+up|read|check)\b",
    re.IGNORECASE,
)
_CLOSE_KW_RE = re.compile(
    r"\b(?:close|hide|dismiss|get\s+rid|take\s+down|put\s+away|go\s+away|"
    r"remove|minimi[sz]e|stash)\b",
    re.IGNORECASE,
)
# A leading question word / subject pronoun = narration or a question, not a
# command ("what's in the logs", "are there logs") -> leave it to the LLM.
_NONCOMMAND_LEAD_RE = re.compile(
    r"^\s*(?:where|what'?s?|how|why|who|when|which|is|are|was|were|does|do|did|"
    r"has|have|i|we|he|she|they|that|this)\b",
    re.IGNORECASE,
)


def match_logs_command(text: str) -> Optional[str]:
    """Match "show / pull up / open the logs" (and "close the logs").

    Args:
        text: the user's transcript for this turn.

    Returns:
        ``"open"`` / ``"close"`` / None. Must reference the log window AND lead
        with an open/close verb, and be a short command (>8 words = not a
        command). Questions / narration fall through to the LLM.
    """
    if not text:
        return None
    cleaned = text.strip()
    if _LOGS_RE.search(cleaned) is None or len(cleaned.split()) > 8:
        return None
    if _NONCOMMAND_LEAD_RE.match(cleaned):
        return None
    if _CLOSE_KW_RE.search(cleaned):
        return "close"
    if _OPEN_KW_RE.search(cleaned):
        return "open"
    return None


class LogViewerOverlay:
    """Daemon-backed scrollable, copyable log window. One per process.

    ``show`` / ``hide`` are idempotent and thread-safe (called from the voice
    loop). Two daemon threads: the Tk UI thread (owns the root) and a file-tail
    thread (feeds new log text through a queue). Build-on-show / tear-down-on-hide
    mirrors the STOP window.
    """

    def __init__(
        self,
        log_path: str,
        *,
        width: int = 780,
        height: int = 460,
        x: int = 90,
        y: int = 90,
        bg_color: str = "#0b0b10",
        fg_color: str = "#d6d6e0",
        accent_color: str = "#e5484d",
        max_lines: int = 5000,
        tail_lines: int = 500,
        title: str = "ULTRON // LOGS",
    ) -> None:
        self._log_path = str(log_path)
        self._w = max(360, int(width))
        self._h = max(180, int(height))
        self._x = int(x)
        self._y = int(y)
        self._bg = bg_color or "#0b0b10"
        self._fg = fg_color or "#d6d6e0"
        self._accent = accent_color or "#e5484d"
        self._max_lines = max(200, int(max_lines))
        self._tail_lines = max(20, int(tail_lines))
        self._title = title or "ULTRON // LOGS"
        self._ui: Optional[threading.Thread] = None
        self._tail: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._q: "Queue[str]" = Queue(maxsize=4000)

    # -- lifecycle ---------------------------------------------------------

    @property
    def shown(self) -> bool:
        ui = self._ui
        return ui is not None and ui.is_alive()

    def show(self) -> None:
        """Build + raise the window. Idempotent (a no-op if already up)."""
        with self._lock:
            if self._ui is not None and self._ui.is_alive():
                return
            self._stop.clear()
            self._tail = threading.Thread(
                target=self._tail_loop, daemon=True, name="log-viewer-tail")
            self._tail.start()
            self._ui = threading.Thread(
                target=self._ui_loop, daemon=True, name="log-viewer-ui")
            self._ui.start()

    def hide(self) -> None:
        """Tear the window down. Idempotent."""
        self._teardown()

    def close(self) -> None:
        """Alias for :meth:`hide` -- used on orchestrator shutdown."""
        self._teardown()

    def _teardown(self) -> None:
        self._stop.set()
        ui = self._ui
        if ui is not None and ui is not threading.current_thread():
            try:
                ui.join(timeout=2.5)
            except Exception:  # noqa: BLE001
                pass
            self._ui = None

    # -- file tail ---------------------------------------------------------

    def _tail_loop(self) -> None:
        """Seed with the last ``tail_lines``, then stream new appends. Handles
        log rotation (file shrinks -> restart from its new start). Fail-open."""
        path = self._log_path
        pos = 0
        try:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    seed = deque(f, maxlen=self._tail_lines)
                self._safe_put("".join(seed))
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(0, os.SEEK_END)
                    pos = f.tell()
            except FileNotFoundError:
                self._safe_put(f"(waiting for {path} to appear ...)\n")
                pos = 0
            while not self._stop.is_set():
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(0, os.SEEK_END)
                        end = f.tell()
                        if end < pos:           # rotated / truncated
                            pos = 0
                        f.seek(pos)
                        chunk = f.read()
                        pos = f.tell()
                    if chunk:
                        self._safe_put(chunk)
                except FileNotFoundError:
                    pos = 0
                except Exception as e:          # noqa: BLE001
                    logger.debug("log tail read error: %s", e)
                self._stop.wait(0.4)
        except Exception as e:                  # noqa: BLE001
            logger.debug("log tail loop stopped: %s", e)

    def _safe_put(self, text: str) -> None:
        if not text:
            return
        try:
            self._q.put(text, timeout=0.5)
        except Exception:                       # noqa: BLE001 (full -> drop)
            pass

    # -- window ------------------------------------------------------------

    def _ui_loop(self) -> None:
        try:
            import tkinter as tk
        except Exception as e:                  # noqa: BLE001
            logger.warning("log viewer unavailable (no tkinter: %s)", e)
            return
        root = None
        try:
            root = tk.Tk()
            root.title(self._title)
            root.geometry(f"{self._w}x{self._h}+{self._x}+{self._y}")
            root.configure(bg=self._bg)
            root.wm_attributes("-topmost", True)

            bar = tk.Frame(root, bg=self._bg, height=30)
            bar.pack(fill="x", side="top")
            bar.pack_propagate(False)
            tk.Label(bar, text="  ULTRON // LOGS", bg=self._bg, fg=self._accent,
                     font=("Segoe UI Semibold", 10)).pack(side="left")

            text = tk.Text(
                root, bg="#070709", fg=self._fg, insertbackground=self._fg,
                font=("Consolas", 9), wrap="word", bd=0, padx=8, pady=6,
                selectbackground="#34344f", highlightthickness=0,
            )
            yscroll = tk.Scrollbar(root, command=text.yview)
            text.configure(yscrollcommand=yscroll.set)
            yscroll.pack(side="right", fill="y")
            text.pack(side="left", fill="both", expand=True)

            # Read-only but selectable + copyable: block typing via the general
            # <Key> binding; the more-specific Ctrl+C / Ctrl+A bindings still
            # fire (Tk runs the most-specific widget binding per event).
            text.bind("<Key>", lambda _e: "break")

            def _copy_sel(_e=None):
                try:
                    sel = text.get("sel.first", "sel.last")
                    if sel:
                        root.clipboard_clear()
                        root.clipboard_append(sel)
                except Exception:               # noqa: BLE001 (no selection)
                    pass
                return "break"

            def _copy_all(_e=None):
                try:
                    root.clipboard_clear()
                    root.clipboard_append(text.get("1.0", "end-1c"))
                except Exception:               # noqa: BLE001
                    pass
                return "break"

            def _select_all(_e=None):
                try:
                    text.tag_add("sel", "1.0", "end-1c")
                except Exception:               # noqa: BLE001
                    pass
                return "break"

            text.bind("<Control-c>", _copy_sel)
            text.bind("<Control-C>", _copy_sel)
            text.bind("<Control-a>", _select_all)
            text.bind("<Control-A>", _select_all)

            def _mk_btn(label, cmd):
                return tk.Button(
                    bar, text=label, command=cmd, bg="#141420", fg=self._fg,
                    activebackground="#22223c", activeforeground="#ffffff",
                    relief="flat", bd=0, highlightthickness=1,
                    highlightbackground="#33334d", highlightcolor="#33334d",
                    font=("Segoe UI", 9), cursor="hand2", padx=8,
                )
            _mk_btn("Close", self.hide).pack(side="right", padx=4, pady=3)
            _mk_btn("Clear", lambda: text.delete("1.0", "end")).pack(
                side="right", padx=2, pady=3)
            _mk_btn("Copy all", _copy_all).pack(side="right", padx=2, pady=3)

            # Only auto-scroll when the view is already pinned to the bottom, so a
            # user reading older lines isn't yanked away.
            state = {"autoscroll": True}

            def _track(*_a):
                try:
                    state["autoscroll"] = text.yview()[1] >= 0.999
                except Exception:               # noqa: BLE001
                    pass
            text.bind("<MouseWheel>", lambda _e: root.after(20, _track))
            text.bind("<ButtonRelease-1>", lambda _e: root.after(20, _track))

            def _drain():
                if self._stop.is_set():
                    try:
                        root.quit()
                    except Exception:           # noqa: BLE001
                        pass
                    return
                appended = False
                for _ in range(300):
                    try:
                        chunk = self._q.get_nowait()
                    except Empty:
                        break
                    try:
                        text.insert("end", chunk)
                        appended = True
                    except Exception:           # noqa: BLE001
                        break
                if appended:
                    try:
                        n = int(text.index("end-1c").split(".")[0])
                        if n > self._max_lines:
                            text.delete("1.0", f"{n - self._max_lines}.0")
                    except Exception:           # noqa: BLE001
                        pass
                    if state["autoscroll"]:
                        try:
                            text.see("end")
                        except Exception:       # noqa: BLE001
                            pass
                root.after(150, _drain)

            root.protocol("WM_DELETE_WINDOW", self.hide)
            root.after(120, _drain)
            logger.info("log viewer window up (%dx%d) tailing %s",
                        self._w, self._h, self._log_path)
            try:
                root.mainloop()
            finally:
                try:
                    root.destroy()
                except Exception:               # noqa: BLE001
                    pass
                root = None
                import gc
                gc.collect()
        except Exception as e:                  # noqa: BLE001
            logger.warning("log viewer window stopped (%s)", e)
            try:
                if root is not None:
                    root.destroy()
            except Exception:                   # noqa: BLE001
                pass
