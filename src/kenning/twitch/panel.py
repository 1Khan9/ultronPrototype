"""The periodic commands-panel message — a barebones chat post of how to play.

The orchestrator posts :func:`build_commands_panel_text` to chat every
``twitch.chat.commands_panel_interval_minutes`` (via the write sidecar ``/say``).
It is intentionally TERSE (fits Twitch's 500-char chat cap) and ends by pointing
viewers at the configured public guide URL when one is set. Pure stdlib;
anticheat-safe; no network here (the orchestrator does the loopback POST).
"""
from __future__ import annotations

from typing import Any

__all__ = ["build_commands_panel_text", "MAX_CHAT_CHARS"]

MAX_CHAT_CHARS = 500

# The barebones viewer command list. Detail lives in the public guide (the docx),
# linked at the end when commands_panel_doc_url is set.
_BASE = (
    "🤖 Ultron commands: !points · !gamble <amt> · !slots <amt> · !wheel (free) · "
    "!heist <amt> · !duel @user <amt> +!accept · !raffle · !give @user <amt> · "
    "!trivia · !leaderboard · !help. Earn cores just by watching."
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
