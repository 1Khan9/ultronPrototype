"""Mouse + keyboard automation via ``pyautogui``.

Distinct from :mod:`ultron.desktop.uia` -- this module does
pixel-coordinate / synthetic-input control rather than semantic UIA
clicks. Use UIA when the target is a standard UI element; use this
module when:

- the target is canvas-rendered (games, image viewers, video players)
- you need keyboard hotkeys (Ctrl+S, Alt+Tab, etc.)
- you need scroll
- you have explicit coordinates from a VLM / OCR pass

Safety:

- Every action passes through the runtime tool-call validator. Cap-4
  rules block synthetic input near UAC / security-class windows;
  Cap-3 action-verb rules block clicks on payment / OAuth buttons by
  label match. Validator runs BEFORE pyautogui touches the OS.
- Foreground-window check: actions refuse when the current foreground
  window's class name matches a known security pattern (UAC consent
  dialog, Windows Defender, credential UI). This is belt-and-braces
  on top of the Cap-4 rule because the rule is a regex match on
  argument values; the foreground check is a runtime check on actual
  on-screen state.
- Rate limit: ``max_actions_per_second`` (default 5) caps how fast a
  caller (or runaway agent) can fire actions. Exceeding the rate
  limit fails the call rather than blocking -- the orchestrator
  doesn't want to deadlock waiting on a stuck input loop.
- pyautogui's own failsafe (move mouse to corner to abort) stays
  on; do NOT disable it.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from threading import Lock
from typing import Optional

import pyautogui  # type: ignore[import]

from ultron.utils.logging import get_logger

logger = get_logger("desktop.input_control")

# Window class names whose foreground presence blocks synthetic input.
# These match Windows' built-in security UI surfaces.
_SECURITY_WINDOW_CLASSES = frozenset({
    "Credential Dialog Xaml Host",
    "CredentialUIControl",
    "ConsentUI",
    "UACDialog",
    "Windows.UI.Core.CoreWindow",  # generic; further checked by title
    "Shell_Dialog",
})

# Window titles that further qualify _SECURITY_WINDOW_CLASSES matches
# (some legit UWP apps share Windows.UI.Core.CoreWindow).
_SECURITY_TITLE_KEYWORDS = (
    "user account control",
    "windows security",
    "credential",
    "sign in",  # Microsoft account sign-in dialogs
    "two-factor",
    "smartscreen",
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputControlResult:
    """Outcome of one input action."""

    success: bool
    action: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Foreground security check
# ---------------------------------------------------------------------------


def _foreground_is_security_window() -> bool:
    """True iff the current foreground window is a UAC / Windows Security UI.

    Synthetic input on these is blocked by Windows itself (UIPI: User
    Interface Privilege Isolation) but we refuse upstream so the
    refusal is logged with context for audit.
    """
    try:
        from ultron.desktop.windows import get_foreground_window
        fg = get_foreground_window()
    except Exception as e:  # noqa: BLE001
        logger.debug("foreground check failed: %s", e)
        return False
    if fg is None:
        return False

    if fg.class_name in _SECURITY_WINDOW_CLASSES:
        # Some classes are too broad; narrow by title.
        if fg.class_name == "Windows.UI.Core.CoreWindow":
            title_l = fg.title.lower()
            return any(kw in title_l for kw in _SECURITY_TITLE_KEYWORDS)
        return True
    return False


# ---------------------------------------------------------------------------
# Safety validator hook
# ---------------------------------------------------------------------------


def _validate_input_action(
    *,
    action: str,
    arguments: dict,
    user_text: str = "",
) -> object:
    """Run the safety validator against an input action.

    Cap-4 rules check for synthetic input near security windows by
    inspecting argument values; we ALSO check foreground state
    directly in the controller.
    """
    try:
        from ultron.safety.validator import RuleContext, get_validator

        ctx = RuleContext(
            tool_name=f"desktop.input.{action}",
            arguments=arguments,
            capability="desktop_input",
            user_text=user_text,
        )
        return get_validator().check(ctx)
    except Exception as e:  # noqa: BLE001
        logger.debug("input_control validator skipped: %s", e)
        from ultron.safety.validator import ValidatorVerdict, Verdict
        return ValidatorVerdict(
            verdict=Verdict.ALLOW, reason="validator unavailable",
        )


# ---------------------------------------------------------------------------
# InputController
# ---------------------------------------------------------------------------


class InputController:
    """Pyautogui-backed input controller with rate limiting + safety gate."""

    def __init__(
        self,
        *,
        max_actions_per_second: float = 5.0,
        enforce_security_window_block: bool = True,
    ) -> None:
        self._rate = max(0.1, float(max_actions_per_second))
        self._enforce_security_block = bool(enforce_security_window_block)
        # Track timestamps of the last N actions to enforce the rate limit.
        self._action_times: deque[float] = deque(maxlen=64)
        self._lock = Lock()

        # Keep pyautogui's failsafe enabled (move mouse to corner aborts).
        try:
            pyautogui.FAILSAFE = True  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    # ---- gating helpers ----

    def _gate(
        self,
        *,
        action: str,
        arguments: dict,
        user_text: str = "",
    ) -> Optional[InputControlResult]:
        """Run security + rate-limit + validator. Returns a failure result
        when the action is refused, or None when the action may proceed.
        """
        if self._enforce_security_block and _foreground_is_security_window():
            return InputControlResult(
                success=False, action=action,
                error="refused: a Windows security window is in the foreground",
            )

        if not self._take_rate_slot():
            return InputControlResult(
                success=False, action=action,
                error=f"refused: rate limit of {self._rate:.1f} actions/s exceeded",
            )

        verdict = _validate_input_action(
            action=action, arguments=arguments, user_text=user_text,
        )
        if not verdict.is_allowed:
            return InputControlResult(
                success=False, action=action,
                error=f"safety: {verdict.reason}",
            )
        return None

    def _take_rate_slot(self) -> bool:
        """Track a new action timestamp; return False if over the rate cap."""
        now = time.monotonic()
        with self._lock:
            window = 1.0
            # Drop entries older than the rolling 1s window.
            while self._action_times and now - self._action_times[0] > window:
                self._action_times.popleft()
            if len(self._action_times) >= int(self._rate):
                return False
            self._action_times.append(now)
            return True

    # ---- public actions ----

    def move_mouse(
        self,
        x: int,
        y: int,
        *,
        duration_s: float = 0.1,
        user_text: str = "",
    ) -> InputControlResult:
        """Move the cursor to (x, y). Duration smooths the motion."""
        gate = self._gate(
            action="move_mouse",
            arguments={"x": int(x), "y": int(y), "duration_s": float(duration_s)},
            user_text=user_text,
        )
        if gate is not None:
            return gate
        try:
            pyautogui.moveTo(
                int(x), int(y), duration=max(0.0, float(duration_s)),
            )
        except Exception as e:  # noqa: BLE001
            return InputControlResult(
                success=False, action="move_mouse", error=str(e)[:200],
            )
        return InputControlResult(success=True, action="move_mouse")

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        *,
        button: str = "left",
        clicks: int = 1,
        interval_s: float = 0.05,
        user_text: str = "",
    ) -> InputControlResult:
        """Mouse click. When ``x``/``y`` are None, clicks at the current
        cursor location.

        ``button`` accepts ``"left"`` / ``"right"`` / ``"middle"``.
        ``clicks=2`` performs a double click.
        """
        if button not in ("left", "right", "middle"):
            return InputControlResult(
                success=False, action="click",
                error=f"unknown button {button!r}",
            )
        if clicks < 1 or clicks > 5:
            return InputControlResult(
                success=False, action="click",
                error=f"clicks out of range: {clicks}",
            )

        args = {
            "button": button,
            "clicks": int(clicks),
        }
        if x is not None:
            args["x"] = int(x)
        if y is not None:
            args["y"] = int(y)

        gate = self._gate(
            action="click", arguments=args, user_text=user_text,
        )
        if gate is not None:
            return gate

        try:
            pyautogui.click(
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
                button=button, clicks=int(clicks),
                interval=max(0.0, float(interval_s)),
            )
        except Exception as e:  # noqa: BLE001
            return InputControlResult(
                success=False, action="click", error=str(e)[:200],
            )
        return InputControlResult(success=True, action="click")

    def type_text(
        self,
        text: str,
        *,
        interval_s: float = 0.0,
        user_text: str = "",
    ) -> InputControlResult:
        """Type a string at the current focus.

        Use :meth:`ultron.desktop.uia.type_text_into_element` for
        targeting a specific UI element semantically.
        """
        if not isinstance(text, str):
            return InputControlResult(
                success=False, action="type_text", error="text must be str",
            )
        if not text:
            return InputControlResult(success=True, action="type_text")

        gate = self._gate(
            action="type_text",
            arguments={
                "text_preview": text[:120],
                "length": len(text),
                "interval_s": float(interval_s),
            },
            user_text=user_text,
        )
        if gate is not None:
            return gate

        try:
            pyautogui.write(text, interval=max(0.0, float(interval_s)))
        except Exception as e:  # noqa: BLE001
            return InputControlResult(
                success=False, action="type_text", error=str(e)[:200],
            )
        return InputControlResult(success=True, action="type_text")

    def press_key(self, key: str, *, user_text: str = "") -> InputControlResult:
        """Press and release a single key (``"enter"``, ``"esc"``,
        ``"f5"``, etc.).
        """
        if not isinstance(key, str) or not key.strip():
            return InputControlResult(
                success=False, action="press_key", error="empty key",
            )
        gate = self._gate(
            action="press_key", arguments={"key": key},
            user_text=user_text,
        )
        if gate is not None:
            return gate
        try:
            pyautogui.press(key)
        except Exception as e:  # noqa: BLE001
            return InputControlResult(
                success=False, action="press_key", error=str(e)[:200],
            )
        return InputControlResult(success=True, action="press_key")

    def press_hotkey(
        self, *keys: str, user_text: str = "",
    ) -> InputControlResult:
        """Press a hotkey combination (``ctrl, s``, ``alt, tab``, etc.).

        Keys are pressed in order then released in reverse.
        """
        if not keys:
            return InputControlResult(
                success=False, action="press_hotkey", error="no keys",
            )
        gate = self._gate(
            action="press_hotkey",
            arguments={"keys": list(keys)},
            user_text=user_text,
        )
        if gate is not None:
            return gate
        try:
            pyautogui.hotkey(*keys)
        except Exception as e:  # noqa: BLE001
            return InputControlResult(
                success=False, action="press_hotkey", error=str(e)[:200],
            )
        return InputControlResult(success=True, action="press_hotkey")

    def scroll(
        self,
        amount: int,
        *,
        x: Optional[int] = None,
        y: Optional[int] = None,
        user_text: str = "",
    ) -> InputControlResult:
        """Scroll up (positive ``amount``) or down (negative) at (x, y) or
        the current cursor location.

        ``amount`` is in OS-specific scroll units (typically ~120 per notch).
        """
        args: dict = {"amount": int(amount)}
        if x is not None:
            args["x"] = int(x)
        if y is not None:
            args["y"] = int(y)
        gate = self._gate(
            action="scroll", arguments=args, user_text=user_text,
        )
        if gate is not None:
            return gate
        try:
            pyautogui.scroll(
                int(amount),
                x=int(x) if x is not None else None,
                y=int(y) if y is not None else None,
            )
        except Exception as e:  # noqa: BLE001
            return InputControlResult(
                success=False, action="scroll", error=str(e)[:200],
            )
        return InputControlResult(success=True, action="scroll")


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_controller_singleton: Optional[InputController] = None


def get_input_controller() -> InputController:
    """Module-level singleton accessor."""
    global _controller_singleton
    if _controller_singleton is None:
        _controller_singleton = InputController()
    return _controller_singleton


def set_input_controller(controller: Optional[InputController]) -> None:
    """Test / orchestrator hook -- swap the singleton."""
    global _controller_singleton
    _controller_singleton = controller


__all__ = [
    "InputControlResult",
    "InputController",
    "get_input_controller",
    "set_input_controller",
]
