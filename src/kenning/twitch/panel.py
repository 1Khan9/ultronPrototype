"""The periodic commands-panel message — a barebones chat post of how to play.

The orchestrator posts :func:`build_commands_panel_text` to chat every
``twitch.chat.commands_panel_interval_minutes`` (via the write sidecar ``/say``).
It is intentionally TERSE (fits Twitch's 500-char chat cap) and ends by pointing
viewers at the configured public guide URL when one is set. Pure stdlib;
anticheat-safe; no network here (the orchestrator does the loopback POST).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("kenning.twitch.panel")

__all__ = [
    "build_commands_panel_text",
    "MAX_CHAT_CHARS",
    "run_interval_poster",
]

MAX_CHAT_CHARS = 500

# The barebones viewer command list. Detail lives in the public guide (the docx),
# linked at the end when commands_panel_doc_url is set.
_BASE = (
    "🤖 Ultron games: !slots <amt> · !wheel (free) · !heist <amt> · "
    "!leaderboard · !help. Redeem channel points for games + Make Ultron "
    "Speak. Earn Credits by watching!"
)


def build_commands_panel_text(cfg: Any) -> str:
    """Build the panel chat message from the chat config (reads only
    ``commands_panel_doc_url``). Always <= :data:`MAX_CHAT_CHARS`."""
    text = _BASE
    url = str(getattr(cfg, "commands_panel_doc_url", "") or "").strip()
    if url:
        text = f"{text} Full guide → {url}"
    if len(text) > MAX_CHAT_CHARS:
        text = text[:MAX_CHAT_CHARS]
    return text


def run_interval_poster(
    build_text: Callable[[], str],
    post_fn: Callable[[str], object],
    *,
    interval_s: float,
    should_stop: Callable[[], bool],
    sleep_fn: Callable[[float], object],
    first_offset_s: float = 0.0,
) -> None:
    """Loop that posts ``build_text()`` to ``post_fn`` every ``interval_s`` seconds.

    The shared body behind a periodic chat poster (the commands panel + the
    talk-to-Ultron hint). Clock-injectable for tests: ``sleep_fn`` advances time
    in 1-second slices (so a stop is honoured promptly) and ``should_stop`` is
    polled before every slice and before every post. The FIRST post waits
    ``first_offset_s`` instead of the full ``interval_s`` (used to STAGGER two
    posters so they never fire on the same instant); subsequent posts use
    ``interval_s``. A build/post error is swallowed (logged at debug) so the loop
    never dies — fail-safe per the orchestrator's poster contract.
    """
    first = True
    while not should_stop():
        target = max(0.0, first_offset_s if first else interval_s)
        waited = 0.0
        while waited < target:
            if should_stop():
                return
            sleep_fn(1.0)
            waited += 1.0
        first = False
        if should_stop():
            return
        try:
            text = build_text()
            if text:
                post_fn(text)
        except Exception as exc:  # noqa: BLE001 — never crash the poster loop
            logger.debug("interval poster post failed: %s", exc)
