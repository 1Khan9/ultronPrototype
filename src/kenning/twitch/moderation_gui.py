"""Always-on-top confirmation window for a Twitch mod action (in-process tkinter).

When a moderator-issued action (timeout / ban / unban / untimeout / delete-last)
resolves a *fuzzy* username match, this little window puts the decision in front
of the human: it names the ACTION, shows the best-match USERNAME large and
prominent, lists the alternative candidates it considered, and offers three
explicit buttons -- YES (confirm), NO (reject this match, try again) and CANCEL
(abandon the action). The click drives a single ``on_result`` callback.

Design notes (mirrors ``kenning/audio/stop_button.py``):
  * In-process: the Tk root lives in a dedicated daemon thread that owns the
    mainloop, so the button command can call the result callback DIRECTLY -- no
    IPC, no polling.
  * A button click is an ordinary window message to our OWN window -- it is NOT
    input monitoring, so it adds nothing to the anticheat surface.
  * Always-on-top (``-topmost``) so it floats over the stream/game.
  * Unlike the borderless STOP control, this window is *resizable*: it uses a
    grid with row/column weights AND rescales every font on ``<Configure>`` so
    the header, the prominent username, the alternatives list and the three
    buttons reorganize and resize to fit the window at any size.

Fail-open throughout: no display / no Tk -> ``available`` is False and every
method is a graceful no-op. Construction and every method NEVER raise into a
boot or a pytest run. Cross-thread requests (``prompt`` / ``update_match`` /
``hide`` called from the moderation loop) are marshalled onto the Tk thread via
``after`` so all widget mutation happens on the thread that owns the root.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Callable

logger = logging.getLogger("kenning.twitch.moderation_gui")

__all__ = ["ModerationConfirmGUI"]

# Force the fail-open / no-window path regardless of an available display. Used
# by lean/headless boots, CI, and tests (where building real Tk roots is both
# pointless and -- with rapid multi-root create/destroy on Windows -- a source
# of Tcl interpreter teardown faults). Any truthy value engages it.
_HEADLESS_ENV = "KENNING_MOD_GUI_HEADLESS"


def _headless_forced() -> bool:
    val = os.environ.get(_HEADLESS_ENV, "")
    return val.strip().lower() not in ("", "0", "false", "no", "off")


# Result tokens the YES / NO / CANCEL buttons emit.
_RESULT_YES = "yes"
_RESULT_NO = "no"
_RESULT_CANCEL = "cancel"
_VALID_RESULTS = (_RESULT_YES, _RESULT_NO, _RESULT_CANCEL)


class ModerationConfirmGUI:
    """Daemon-backed always-on-top, resizable mod-action confirm window.

    One per process. ``prompt`` shows (building the window lazily on first use)
    and (re)populates the window, wiring ``on_result`` to the three buttons.
    ``update_match`` refreshes the displayed username + alternatives after a
    re-search. ``hide`` lowers the window. ``available`` is False when Tk / a
    display is missing, in which case every method is a safe no-op.

    The Tk root is created on the UI thread on first ``prompt``; all subsequent
    widget mutation is marshalled onto that thread via a request queue drained
    by an ``after`` poll, so the public API is safe to call from the moderation
    loop thread.
    """

    def __init__(
        self,
        *,
        width: int = 380,
        height: int = 280,
        x: int = 80,
        y: int = 80,
        bg_color: str = "#0b0b0f",
        fg_color: str = "#e6e6ea",
        accent_color: str = "#bf7fff",
        yes_color: str = "#3ddc84",
        no_color: str = "#e0a82e",
        cancel_color: str = "#ff6b6b",
        always_on_top: bool = True,
        title: str = "ULTRON // CONFIRM MOD ACTION",
    ) -> None:
        self._width = max(220, int(width))
        self._height = max(160, int(height))
        self._x = int(x)
        self._y = int(y)
        self._bg = bg_color or "#0b0b0f"
        self._fg = fg_color or "#e6e6ea"
        self._accent = accent_color or "#bf7fff"
        self._yes_color = yes_color or "#3ddc84"
        self._no_color = no_color or "#e0a82e"
        self._cancel_color = cancel_color or "#ff6b6b"
        self._always_on_top = bool(always_on_top)
        self._title = title or "ULTRON // CONFIRM MOD ACTION"

        # ``available`` reflects whether a Tk display could be reached. It starts
        # optimistically True and is flipped False the first time Tk import or
        # window construction fails -- after which every method short-circuits.
        self.available: bool = self._probe_tk_available()

        # Current logical state, mutated only on the UI thread.
        self._action: str = ""
        self._username: str = ""
        self._alternatives: list[str] = []
        self._on_result: Callable[[str], None] | None = None
        # Guards against a double-fire (two clicks before the window hides).
        self._result_sent: bool = False

        # UI-thread machinery.
        self._ui: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._requests: queue.Queue[Callable[[], None]] = queue.Queue()
        # Populated on the UI thread; only touched there.
        self._tk = None
        self._root = None
        self._widgets: dict = {}

    # -- introspection -----------------------------------------------------

    @staticmethod
    def _probe_tk_available() -> bool:
        """True iff a Tk window may be built. False when the headless env flag
        is set or ``tkinter`` fails to import. We do NOT build a root here (that
        is deferred to the UI thread) -- a missing import is the cheap, common
        headless signal; a missing *display* is caught later and also flips
        ``available`` False."""
        if _headless_forced():
            logger.info("moderation confirm GUI forced headless via %s",
                        _HEADLESS_ENV)
            return False
        try:
            import tkinter  # noqa: F401
        except Exception as e:  # noqa: BLE001
            logger.info("moderation confirm GUI unavailable (no tkinter: %s)", e)
            return False
        return True

    @property
    def shown(self) -> bool:
        ui = self._ui
        return ui is not None and ui.is_alive()

    # -- public API --------------------------------------------------------

    def prompt(
        self,
        action: str,
        username: str,
        alternatives: list[str],
        on_result: Callable[[str], None],
    ) -> None:
        """Show / update the window for a pending mod action.

        Args:
            action: the action header, e.g. ``"TIMEOUT 10m"`` / ``"BAN"`` /
                ``"UNBAN"`` / ``"UNTIMEOUT"`` / ``"DELETE LAST MSG"``.
            username: the best-match username (shown large + prominent).
            alternatives: other candidate usernames the matcher considered.
            on_result: invoked exactly once with ``"yes"`` / ``"no"`` /
                ``"cancel"`` on the matching button click.

        Fail-open: a no-op when Tk / a display is unavailable.
        """
        if not self.available:
            return
        try:
            action_s = str(action or "")
            username_s = str(username or "")
            alts = [str(a) for a in (alternatives or []) if str(a)]
            cb = on_result if callable(on_result) else None

            def _apply() -> None:
                self._action = action_s
                self._username = username_s
                self._alternatives = alts
                self._on_result = cb
                self._result_sent = False
                self._render()
                self._raise_window()

            self._ensure_ui()
            self._requests.put(_apply)
            self._wake_ui()
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm prompt failed (fail-open): %s", e)
            self.available = False

    def update_match(self, username: str, alternatives: list[str]) -> None:
        """Refresh the displayed match after a re-search (NO click -> retry).

        Fail-open: a no-op when unavailable or no window is up.
        """
        if not self.available:
            return
        try:
            username_s = str(username or "")
            alts = [str(a) for a in (alternatives or []) if str(a)]

            def _apply() -> None:
                self._username = username_s
                self._alternatives = alts
                # A fresh candidate set means the prior result window is "live"
                # again -- allow a result to be sent for this new match.
                self._result_sent = False
                self._render()
                self._raise_window()

            self._requests.put(_apply)
            self._wake_ui()
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm update failed (fail-open): %s", e)

    def hide(self) -> None:
        """Withdraw the window (idempotent). Fail-open."""
        if not self.available:
            return
        try:
            def _apply() -> None:
                self._withdraw_window()

            self._requests.put(_apply)
            self._wake_ui()
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm hide failed (fail-open): %s", e)

    def close(self) -> None:
        """Tear the window + UI thread down. Used on orchestrator shutdown.

        Fail-open, and never blocks when called from the UI thread itself.
        """
        self._stop.set()
        self._wake_ui()
        ui = self._ui
        if ui is not None and ui is not threading.current_thread():
            try:
                ui.join(timeout=2.5)
            except Exception:  # noqa: BLE001
                pass
            self._ui = None

    # -- UI thread lifecycle ----------------------------------------------

    def _ensure_ui(self) -> None:
        """Start the UI thread on first use. Idempotent + thread-safe."""
        if not self.available:
            return
        with self._lock:
            if self._ui is not None and self._ui.is_alive():
                return
            self._stop.clear()
            self._ui = threading.Thread(
                target=self._ui_loop, daemon=True, name="mod-confirm-ui")
            self._ui.start()

    def _wake_ui(self) -> None:
        """Intentionally a no-op.

        Tk objects may be touched ONLY from the thread that created the root
        (mirroring ``stop_button.py``). Calling ``root.after``/``after_idle``
        from the moderation-loop thread corrupts the Tcl interpreter
        ('Tcl_AsyncDelete: ... wrong thread'). Instead the UI thread's own
        ``after``-driven ``_poll`` drains :attr:`_requests` every ~80 ms, so a
        cross-thread nudge is neither needed nor safe. Kept as a named seam so
        the public methods read clearly.
        """
        return

    def _ui_loop(self) -> None:
        """Own the Tk root + mainloop. Fail-open: any failure flips
        ``available`` False and returns cleanly."""
        try:
            import tkinter as tk
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm GUI: no tkinter (%s)", e)
            self.available = False
            return
        self._tk = tk
        root = None
        try:
            root = tk.Tk()
            self._root = root
            root.title(self._title)
            root.geometry(
                f"{self._width}x{self._height}+{self._x}+{self._y}")
            root.minsize(220, 160)
            root.configure(bg=self._bg)
            if self._always_on_top:
                try:
                    root.wm_attributes("-topmost", True)
                except Exception:  # noqa: BLE001
                    pass

            self._build_layout(root)

            # Start withdrawn; a prompt() raises it.
            try:
                root.withdraw()
            except Exception:  # noqa: BLE001
                pass

            # Rescale fonts whenever the window resizes so every element fits.
            root.bind("<Configure>", self._on_configure)

            def _poll() -> None:
                if self._stop.is_set():
                    try:
                        root.quit()
                    except Exception:  # noqa: BLE001
                        pass
                    return
                self._drain_requests()
                try:
                    root.after(80, _poll)
                except Exception:  # noqa: BLE001
                    pass

            try:
                root.after(80, _poll)
            except Exception:  # noqa: BLE001
                pass
            logger.info("moderation confirm GUI ready (%dx%d)",
                        self._width, self._height)
            try:
                root.mainloop()
            finally:
                try:
                    root.destroy()
                except Exception:  # noqa: BLE001
                    pass
                self._root = None
                self._widgets = {}
                # Release the tkfont.Font handles on THIS (UI) thread. A Font
                # garbage-collected on any OTHER thread raises
                # 'Tcl_AsyncDelete: ... wrong thread' and crashes the process
                # (exit 3) -- the same wrong-thread Tcl hazard _wake_ui documents.
                # The finally clears self._widgets but historically left
                # self._fonts holding the Font objects, so they were freed later
                # on whichever thread dropped the last reference. Dropping the refs
                # HERE + gc.collect() finalizes them on the thread that owns the
                # Tcl interpreter. (root is already destroyed, so each Font.__del__
                # hits a dead interpreter, which tkinter.font.Font.__del__ catches.)
                self._fonts = {}
                import gc
                gc.collect()
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm GUI stopped (%s)", e)
            self.available = False
            try:
                if root is not None:
                    root.destroy()
            except Exception:  # noqa: BLE001
                pass
            self._root = None

    def _drain_requests(self) -> None:
        """Run all queued UI mutations on the Tk thread. Fail-open per item."""
        while True:
            try:
                fn = self._requests.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                logger.warning("moderation confirm UI request failed: %s", e)

    # -- layout (built once, repopulated per prompt) -----------------------

    def _build_layout(self, root) -> None:
        """Construct the grid layout. Row/column weights make every region
        flex; fonts are (re)scaled in :meth:`_on_configure`."""
        tk = self._tk
        # Track the tk.font handles so <Configure> can rescale them.
        import tkinter.font as tkfont

        header_font = tkfont.Font(family="Segoe UI Semibold", size=12)
        user_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        alt_header_font = tkfont.Font(family="Segoe UI", size=8)
        alt_font = tkfont.Font(family="Consolas", size=9)
        btn_font = tkfont.Font(family="Segoe UI Semibold", size=11)

        self._fonts = {
            "header": header_font,
            "user": user_font,
            "alt_header": alt_header_font,
            "alt": alt_font,
            "btn": btn_font,
        }
        # Base sizes (px proxy) used to scale fonts proportionally on resize.
        self._base_fonts = {
            "header": 12, "user": 22, "alt_header": 8, "alt": 9, "btn": 11,
        }

        # 4 logical rows: header / username / alternatives / buttons.
        # Weighted so the username + alternatives regions absorb extra height.
        root.grid_rowconfigure(0, weight=0)   # header
        root.grid_rowconfigure(1, weight=3)   # username (dominant)
        root.grid_rowconfigure(2, weight=2)   # alternatives
        root.grid_rowconfigure(3, weight=0)   # buttons
        root.grid_columnconfigure(0, weight=1)

        # Header -- the ACTION.
        header = tk.Label(
            root, text="", font=header_font, fg=self._accent, bg=self._bg,
            anchor="center", justify="center", wraplength=self._width,
        )
        header.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 2))

        # Username -- large + prominent.
        user = tk.Label(
            root, text="", font=user_font, fg=self._fg, bg=self._bg,
            anchor="center", justify="center", wraplength=self._width,
        )
        user.grid(row=1, column=0, sticky="nsew", padx=8, pady=2)

        # Alternatives -- a smaller secondary region.
        alt_frame = tk.Frame(root, bg=self._bg)
        alt_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=2)
        alt_frame.grid_columnconfigure(0, weight=1)
        alt_frame.grid_rowconfigure(0, weight=0)
        alt_frame.grid_rowconfigure(1, weight=1)

        alt_header = tk.Label(
            alt_frame, text="alternatives", font=alt_header_font,
            fg="#8a8f98", bg=self._bg, anchor="w",
        )
        alt_header.grid(row=0, column=0, sticky="ew")

        alt_list = tk.Label(
            alt_frame, text="", font=alt_font, fg="#b9bcc6", bg=self._bg,
            anchor="nw", justify="left", wraplength=self._width,
        )
        alt_list.grid(row=1, column=0, sticky="nsew")

        # Buttons -- YES / NO / CANCEL across a 3-column sub-grid.
        btn_frame = tk.Frame(root, bg=self._bg)
        btn_frame.grid(row=3, column=0, sticky="nsew", padx=6, pady=(2, 8))
        for c in range(3):
            btn_frame.grid_columnconfigure(c, weight=1, uniform="btns")
        btn_frame.grid_rowconfigure(0, weight=1)

        yes_btn = self._make_button(
            btn_frame, "YES", self._yes_color, "#0c1f13",
            lambda: self._fire(_RESULT_YES), btn_font)
        no_btn = self._make_button(
            btn_frame, "NO", self._no_color, "#1a160a",
            lambda: self._fire(_RESULT_NO), btn_font)
        cancel_btn = self._make_button(
            btn_frame, "CANCEL", self._cancel_color, "#1a0d0d",
            lambda: self._fire(_RESULT_CANCEL), btn_font)
        yes_btn.grid(row=0, column=0, sticky="nsew", padx=3)
        no_btn.grid(row=0, column=1, sticky="nsew", padx=3)
        cancel_btn.grid(row=0, column=2, sticky="nsew", padx=3)

        self._widgets = {
            "header": header,
            "user": user,
            "alt_header": alt_header,
            "alt_list": alt_list,
            "yes": yes_btn,
            "no": no_btn,
            "cancel": cancel_btn,
        }
        # Allow Esc to cancel.
        try:
            root.bind("<Escape>", lambda _e: self._fire(_RESULT_CANCEL))
        except Exception:  # noqa: BLE001
            pass

    def _make_button(self, parent, text, fg, fill, command, font):
        tk = self._tk
        b = tk.Button(
            parent, text=text, command=command,
            bg=fill, fg=fg, activebackground=fill, activeforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=2,
            highlightbackground=fg, highlightcolor=fg,
            font=font, cursor="hand2",
        )
        return b

    # -- render / window-state (UI thread only) ---------------------------

    def _render(self) -> None:
        """Push current logical state into the widgets. UI thread only."""
        w = self._widgets
        if not w:
            return
        try:
            w["header"].configure(text=self._action or "MOD ACTION")
            w["user"].configure(text=self._username or "(no match)")
            if self._alternatives:
                w["alt_header"].configure(text="alternatives")
                w["alt_list"].configure(
                    text="\n".join(self._alternatives))
            else:
                w["alt_header"].configure(text="no other candidates")
                w["alt_list"].configure(text="")
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm render failed: %s", e)

    def _raise_window(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.deiconify()
            if self._always_on_top:
                root.wm_attributes("-topmost", True)
            root.lift()
        except Exception:  # noqa: BLE001
            pass

    def _withdraw_window(self) -> None:
        root = self._root
        if root is None:
            return
        try:
            root.withdraw()
        except Exception:  # noqa: BLE001
            pass

    def _on_configure(self, event) -> None:
        """Rescale every font proportionally to the window size so the header,
        username, alternatives and buttons reorganize + resize to fit. UI
        thread only (fired by Tk)."""
        root = self._root
        if root is None or not getattr(self, "_fonts", None):
            return
        # Only react to the toplevel's own resize, not child <Configure>s.
        try:
            if event is not None and event.widget is not root:
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            w = max(1, int(root.winfo_width()))
            h = max(1, int(root.winfo_height()))
        except Exception:  # noqa: BLE001
            return
        # Scale by the smaller of the width/height ratios against the base
        # geometry, clamped so text stays legible and never explodes.
        try:
            scale_w = w / float(self._width)
            scale_h = h / float(self._height)
            scale = min(scale_w, scale_h)
            scale = max(0.55, min(2.6, scale))
            for key, base in self._base_fonts.items():
                size = max(6, int(round(base * scale)))
                self._fonts[key].configure(size=size)
            # Keep wraplength in step so long names/alternatives wrap.
            wrap = max(80, w - 24)
            for wk in ("header", "user"):
                if wk in self._widgets:
                    self._widgets[wk].configure(wraplength=wrap)
            if "alt_list" in self._widgets:
                self._widgets["alt_list"].configure(wraplength=wrap)
        except Exception as e:  # noqa: BLE001
            logger.debug("moderation confirm font rescale skipped: %s", e)

    # -- the click ---------------------------------------------------------

    def _fire(self, result: str) -> None:
        """Button command: emit the result ONCE, then withdraw. Fail-open so a
        bad callback never kills the window. UI thread only."""
        if result not in _VALID_RESULTS:
            return
        if self._result_sent:
            return
        self._result_sent = True
        cb = self._on_result
        try:
            self._withdraw_window()
        except Exception:  # noqa: BLE001
            pass
        if cb is None:
            return
        try:
            cb(result)
            logger.info("moderation confirm -> %s (%s / %s)",
                        result, self._action, self._username)
        except Exception as e:  # noqa: BLE001
            logger.warning("moderation confirm result callback failed: %s", e)
