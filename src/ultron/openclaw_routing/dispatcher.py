"""OpenClawDispatcher — stubbed dispatch surface for OpenClaw-bound intents.

In Foundation Phase 5 every dispatch method returns a stub
:class:`DispatchResult` indicating the capability isn't yet integrated.
The voice phrase is in Ultron's voice so the user gets a coherent
response, not a stack trace.

The OpenClaw integration prompt that follows this phase replaces each
stub with a real Gateway call; the public API stays the same so
upstream callers (CapabilityVoiceController) don't need to change.
"""

from __future__ import annotations

from typing import Any, Dict

from ultron.config import UltronConfig, get_config
from ultron.openclaw_routing.intents import (
    BrowserIntent,
    DispatchResult,
    FileOpIntent,
    MediaGenIntent,
    MessagingIntent,
    ShellOpIntent,
)
from ultron.utils.logging import get_logger

logger = get_logger("openclaw_routing.dispatcher")


class OpenClawDispatcher:
    """Dispatcher for OpenClaw-dependent intents.

    Args:
        config: The full :class:`UltronConfig`. Read at construction so
            tests can inject a config without re-reading the YAML.

    All dispatch methods are async because real OpenClaw calls will be
    HTTP. The stubs return immediately.
    """

    def __init__(self, config: UltronConfig | None = None) -> None:
        cfg = config if config is not None else get_config()
        self.enabled = cfg.openclaw.enabled
        self.gateway_url = cfg.openclaw.gateway_url
        self.fail_open = cfg.openclaw.fail_open
        self.stub_responses_enabled = cfg.routing.stub_responses_enabled

    # --- per-capability dispatch surface -----------------------------------

    async def handle_browser(self, intent: BrowserIntent) -> DispatchResult:
        """Browser automation (open/click/fill/screenshot)."""
        return self._stub_response(
            capability="browser_automation",
            voice_message=(
                "I'd open that page for you, but the gateway isn't connected yet."
            ),
            metadata={"action": intent.action, "url": intent.url},
        )

    async def handle_media_generation(self, intent: MediaGenIntent) -> DispatchResult:
        """Image / video / audio generation."""
        return self._stub_response(
            capability="media_generation",
            voice_message=(
                "I'd generate that for you, but the gateway isn't connected yet."
            ),
            metadata={"medium": intent.medium},
        )

    async def handle_messaging(self, intent: MessagingIntent) -> DispatchResult:
        """Send a message via Telegram, push, email, etc."""
        return self._stub_response(
            capability="messaging",
            voice_message=(
                "I'd send that for you, but the gateway isn't connected yet."
            ),
            metadata={"channel": intent.channel},
        )

    async def handle_file_operation(self, intent: FileOpIntent) -> DispatchResult:
        """Filesystem operations outside the project sandbox."""
        return self._stub_response(
            capability="file_operations",
            voice_message=(
                "I can't reach files outside the project sandbox yet."
            ),
            metadata={"operation": intent.operation, "path": intent.path},
        )

    async def handle_shell_operation(self, intent: ShellOpIntent) -> DispatchResult:
        """Shell command execution via OpenClaw exec tool."""
        return self._stub_response(
            capability="shell_operations",
            voice_message="I can't run shell commands yet.",
            metadata={"command_preview": intent.command[:60]},
        )

    # --- internal ----------------------------------------------------------

    def _stub_response(
        self,
        *,
        capability: str,
        voice_message: str,
        metadata: Dict[str, Any] | None = None,
    ) -> DispatchResult:
        """Build the canonical "not yet integrated" stub. The OpenClaw
        integration prompt replaces these per-capability handlers; the
        helper stays for tests and operator dry-runs."""
        meta = {"stub": True, "capability": capability}
        if metadata:
            meta.update(metadata)
        logger.info(
            "OpenClawDispatcher stub: capability=%s (gateway enabled=%s)",
            capability, self.enabled,
        )
        return DispatchResult(
            success=False,
            voice_message=voice_message,
            error=(
                f"{capability} not yet integrated; available after "
                f"OpenClaw integration phase"
            ),
            metadata=meta,
        )


__all__ = ["OpenClawDispatcher"]
