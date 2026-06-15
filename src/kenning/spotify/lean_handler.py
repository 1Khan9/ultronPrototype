"""Self-contained Spotify voice dispatch for the LEAN GAMING BOOT.

The normal orchestrator Spotify dispatch lives INSIDE the
``if self.coding_voice is not None:`` block of the run loop. The lean gaming boot
gates ``coding_voice`` off (to keep the coding stack out of RAM), so that whole
block -- and the Spotify handler with it -- is skipped, and music commands fall
through to the semantic router, which abstains and lets the LLM HALLUCINATE a
fake "now playing" reply.

Rather than un-gate that coding-coupled block (risking a coding/openclaw import
leak into the anticheat-pinned process), the lean dispatch path calls THIS
standalone handler instead. It imports ONLY the ``kenning.spotify.*`` primitives
(matcher / client / auth) + config -- nothing coding, nothing openclaw, nothing
heavy, nothing that touches input/capture/automation. Spotify is a Web API over
HTTPS, so it is anticheat-irrelevant and safe to run in a barebones session.

Behaviour mirrors the orchestrator's ``_maybe_handle_spotify`` exactly:
  * non-music utterance  -> returns False (caller falls through to the router)
  * matched + no creds   -> speaks a clear setup instruction, returns True
  * matched + client OK   -> executes the action, speaks the reply, returns True

Fail-open throughout: any unexpected error returns False (fall through) rather
than crashing the voice loop.
"""

from __future__ import annotations

from typing import Callable, Optional

from kenning.utils.logging import get_logger

logger = get_logger("spotify.lean_handler")


class LeanSpotifyHandler:
    """Stateful (authorized-client-caching) Spotify dispatcher for lean boot.

    One instance is held by the orchestrator and reused across turns so the
    OAuth client is built once. All Spotify imports are deferred to call time so
    merely importing this module pulls nothing.
    """

    def __init__(self) -> None:
        self._client = None

    # ------------------------------------------------------------------
    def _client_or_none(self):
        """Build (and cache) an AUTHORIZED Spotify client, or return None.

        Caches only an authorized client; an unauthorized one (no refresh token
        yet) is rebuilt every call so finishing the one-time OAuth mid-session is
        picked up live without a restart -- identical to the orchestrator path.
        """
        cached = self._client
        if cached is not None and getattr(
                getattr(cached, "_auth", None), "authorized", False):
            return cached
        client = None
        try:
            from kenning.config import get_config
            from kenning.spotify.auth import SpotifyAuth, load_credentials
            from kenning.spotify.client import SpotifyClient

            cfg = get_config().spotify
            if getattr(cfg, "enabled", False):
                creds = load_credentials(cfg.credentials_path)
                client = SpotifyClient(
                    SpotifyAuth(creds),
                    default_device=getattr(cfg, "default_device", ""),
                )
        except Exception as e:                                        # noqa: BLE001
            logger.debug("lean spotify client unavailable: %s", e)
            client = None
        if client is not None and client._auth.authorized:
            self._client = client
        return client

    # ------------------------------------------------------------------
    def handle(
        self,
        user_text: str,
        speak: Callable[[str], None],
        strip_wake: Optional[Callable[[str], str]] = None,
    ) -> bool:
        """Dispatch a Spotify voice command.

        Args:
            user_text: the (already normalized) utterance.
            speak: callback that speaks a reply line to the user.
            strip_wake: optional fn to strip a mis-heard leading wake remnant,
                tried as a fallback when the raw text doesn't match.

        Returns True iff this was a Spotify command (turn consumed); False to let
        the caller fall through to the router / LLM. Never raises.
        """
        try:
            from kenning.config import get_config
            from kenning.spotify.voice import (
                handle_spotify_command,
                match_spotify_command,
            )

            if not getattr(get_config().spotify, "enabled", False):
                return False
            command = match_spotify_command(user_text)
            if command is None and strip_wake is not None:
                cleaned = strip_wake(user_text)
                if cleaned != user_text:
                    command = match_spotify_command(cleaned)
        except Exception as e:                                        # noqa: BLE001
            logger.debug("lean spotify matcher unavailable: %s", e)
            return False
        if command is None:
            return False
        client = self._client_or_none()
        if client is None:
            speak("Spotify isn't set up yet. Add your credentials and run "
                  "the Spotify setup once.")
            return True
        try:
            line = handle_spotify_command(command, client)
        except Exception as e:                                        # noqa: BLE001
            logger.warning("lean spotify handling failed: %s", e)
            line = "Something went wrong with Spotify."
        logger.info("spotify(lean) | action=%s | arg=%r | -> %r",
                    command.action, command.argument[:40], line[:80])
        speak(line)
        return True
