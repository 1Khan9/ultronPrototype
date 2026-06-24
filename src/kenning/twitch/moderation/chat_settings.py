"""Voice chat-SETTINGS moderation — slow / followers-only / subscribers-only /
emote-only / unique-chat toggles + clear-chat.

A deterministic regex parser (the abliterated LLM is NEVER in this path) that maps
a spoken streamer command to either a Helix ``update_chat_settings`` body or a
clear-chat request. These are channel-scoped (NO target user) and reversible, so
they execute directly (no per-target resolve / read-back), unlike ban/timeout.

``moderator:manage:chat_settings`` (toggles) and ``moderator:manage:chat_messages``
(clear) are broadcaster scopes already requested in ``auth.BROADCASTER_SCOPES``.

ANTICHEAT (BR-P1): stdlib only (``re`` / ``dataclasses`` / ``typing``).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("kenning.twitch.moderation.chat_settings")

__all__ = ["ChatSettingsCommand", "parse_chat_settings"]

# Twitch slow-mode bounds (seconds).
_SLOW_MIN, _SLOW_MAX, _SLOW_DEFAULT = 3, 120, 30
# Follower-mode duration is in MINUTES (0 = any follower).
_FOLLOWER_DEFAULT_MIN = 0


@dataclass(frozen=True)
class ChatSettingsCommand:
    """A parsed chat-settings action.

    Exactly one of ``settings`` (a Helix ``update_chat_settings`` body) or
    ``clear`` (clear all chat) is meaningful. ``readback`` is the spoken
    confirmation Ultron says after applying it.
    """

    settings: dict = field(default_factory=dict)
    clear: bool = False
    readback: str = ""


# Each mode: (canonical Helix key, the words that name it). Duration handled
# separately for slow/follower.
_MODES = (
    ("emote_mode", r"emote[\s-]?only|emote[\s-]?mode"),
    ("subscriber_mode", r"sub(?:scriber)?s?[\s-]?only|sub(?:scriber)?[\s-]?mode"),
    ("follower_mode", r"follower?s?[\s-]?only|follower[\s-]?mode"),
    ("unique_chat_mode", r"unique[\s-]?chat|no[\s-]?duplicate|r9k"),
    ("slow_mode", r"slow[\s-]?mode|slow[\s-]?chat"),
)
_OFF = re.compile(r"\b(off|disable[d]?|turn\s+off|stop|deactivate|end|lift|remove)\b", re.IGNORECASE)
_CLEAR = re.compile(r"\bclear(?:\s+(?:the|all))?\s+chat\b|\bclear\s+the\s+messages\b", re.IGNORECASE)
# "30 seconds" / "for 45s" / "10 minute(s)" trailing duration.
_DUR = re.compile(r"(?P<num>\d+)\s*(?P<unit>seconds?|secs?|s|minutes?|mins?|m)\b", re.IGNORECASE)


def _readback(label: str, on: bool, *, suffix: str = "") -> str:
    state = "on" if on else "off"
    extra = f" {suffix}" if (on and suffix) else ""
    return f"{label} {state}{extra}."


def parse_chat_settings(text: str) -> Optional[ChatSettingsCommand]:
    """Parse ``text`` into a :class:`ChatSettingsCommand`, or ``None`` when it is
    not a chat-settings command. Conservative: a recognised MODE word is required.
    Never raises."""
    try:
        raw = (text or "").strip()
        if not raw:
            return None
        low = raw.lower()

        if _CLEAR.search(low):
            return ChatSettingsCommand(clear=True, readback="Chat cleared.")

        for key, pat in _MODES:
            if not re.search(pat, low):
                continue
            # An explicit "off"/"disable"/"lift" word disables; otherwise the bare
            # mode phrase ("slow mode", "emote only") means turn it ON.
            on = _resolve_on_off(low)
            if key == "slow_mode":
                return _slow(low, on)
            if key == "follower_mode":
                return _follower(low, on)
            label = {
                "emote_mode": "Emote-only",
                "subscriber_mode": "Subscribers-only",
                "unique_chat_mode": "Unique-chat",
            }[key]
            return ChatSettingsCommand(settings={key: on}, readback=_readback(label, on))
        return None
    except Exception as e:  # noqa: BLE001 - parse is fail-safe
        logger.warning("chat-settings parse failed for %r (%s)", text, e)
        return None


def _resolve_on_off(low: str) -> bool:
    """True = enable. An explicit OFF word disables; otherwise default to enable
    (the common phrasing 'slow mode' / 'emote only' means turn it ON)."""
    return not bool(_OFF.search(low))


def _slow(low: str, on: bool) -> ChatSettingsCommand:
    if not on:
        return ChatSettingsCommand(settings={"slow_mode": False}, readback=_readback("Slow mode", False))
    wait = _SLOW_DEFAULT
    m = _DUR.search(low)
    if m:
        n = int(m.group("num"))
        unit = m.group("unit").lower()
        secs = n * (60 if unit.startswith(("m", "min")) else 1)
        wait = max(_SLOW_MIN, min(_SLOW_MAX, secs))
    return ChatSettingsCommand(
        settings={"slow_mode": True, "slow_mode_wait_time": wait},
        readback=_readback("Slow mode", True, suffix=f"at {wait} seconds"),
    )


def _follower(low: str, on: bool) -> ChatSettingsCommand:
    if not on:
        return ChatSettingsCommand(settings={"follower_mode": False},
                                   readback=_readback("Followers-only", False))
    minutes = _FOLLOWER_DEFAULT_MIN
    m = _DUR.search(low)
    if m:
        n = int(m.group("num"))
        unit = m.group("unit").lower()
        minutes = n if unit.startswith(("m", "min")) else max(0, n // 60)
    return ChatSettingsCommand(
        settings={"follower_mode": True, "follower_mode_duration": minutes},
        readback=_readback("Followers-only", True,
                           suffix=(f"for {minutes} minutes" if minutes else "")),
    )
