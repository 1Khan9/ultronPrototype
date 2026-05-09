"""OpenClawDispatcher — stubbed dispatch surface for OpenClaw-bound intents.

In Foundation Phase 5 every dispatch method returns a stub
:class:`DispatchResult` indicating the capability isn't yet integrated.
The voice phrase is in Ultron's voice so the user gets a coherent
response, not a stack trace.

The OpenClaw integration prompt that follows this phase replaces each
stub with a real Gateway call; the public API stays the same so
upstream callers (CapabilityVoiceController) don't need to change.

4B plan Item 8: each handle_* method runs a pre-flight block-and-revise
validator (if enabled and an LLM is wired) BEFORE the dispatch. When
the validator returns ``allow=False`` the dispatcher returns a
DispatchResult shaped like a stub but with the validator's reason —
so the user hears why the call was blocked rather than seeing it
silently dropped. Default OFF.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

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
        llm: an optional LLMEngine-like object used by the block-and-
            revise validator (4B plan Item 8). When ``None``, the
            validator fails open — dispatch proceeds as before.

    All dispatch methods are async because real OpenClaw calls will be
    HTTP. The stubs return immediately.
    """

    def __init__(
        self,
        config: UltronConfig | None = None,
        *,
        llm: Optional[Any] = None,
    ) -> None:
        cfg = config if config is not None else get_config()
        self._cfg = cfg
        self.enabled = cfg.openclaw.enabled
        self.gateway_url = cfg.openclaw.gateway_url
        self.fail_open = cfg.openclaw.fail_open
        self.stub_responses_enabled = cfg.routing.stub_responses_enabled
        # 4B plan Item 8 — block-and-revise validator. None when no LLM
        # is wired; the validator itself fails open when unset, so we
        # also short-circuit here to skip the LLM-call cost entirely.
        self._llm = llm

    # --- per-capability dispatch surface -----------------------------------

    async def handle_browser(self, intent: BrowserIntent) -> DispatchResult:
        """Browser automation (open/click/fill/screenshot)."""
        blocked = self._maybe_block(
            tool_name="browser",
            goal=intent.raw_text,
            tool_args={
                "action": intent.action, "url": intent.url,
                "target": intent.target, "value": intent.value,
            },
        )
        if blocked is not None:
            return blocked
        return self._stub_response(
            capability="browser_automation",
            voice_message=(
                "I'd open that page for you, but the gateway isn't connected yet."
            ),
            metadata={"action": intent.action, "url": intent.url},
        )

    async def handle_media_generation(self, intent: MediaGenIntent) -> DispatchResult:
        """Image / video / audio generation."""
        blocked = self._maybe_block(
            tool_name="media_generation",
            goal=intent.raw_text,
            tool_args={"medium": intent.medium, "description": intent.description},
        )
        if blocked is not None:
            return blocked
        return self._stub_response(
            capability="media_generation",
            voice_message=(
                "I'd generate that for you, but the gateway isn't connected yet."
            ),
            metadata={"medium": intent.medium},
        )

    async def handle_messaging(self, intent: MessagingIntent) -> DispatchResult:
        """Send a message via Telegram, push, email, etc."""
        blocked = self._maybe_block(
            tool_name="messaging",
            goal=intent.raw_text,
            tool_args={
                "channel": intent.channel,
                "recipient": intent.recipient,
                "body_preview": (intent.body or "")[:120],
            },
        )
        if blocked is not None:
            return blocked
        return self._stub_response(
            capability="messaging",
            voice_message=(
                "I'd send that for you, but the gateway isn't connected yet."
            ),
            metadata={"channel": intent.channel},
        )

    async def handle_file_operation(self, intent: FileOpIntent) -> DispatchResult:
        """Filesystem operations outside the project sandbox."""
        blocked = self._maybe_block(
            tool_name="file_operation",
            goal=intent.raw_text,
            tool_args={"operation": intent.operation, "path": intent.path},
        )
        if blocked is not None:
            return blocked
        return self._stub_response(
            capability="file_operations",
            voice_message=(
                "I can't reach files outside the project sandbox yet."
            ),
            metadata={"operation": intent.operation, "path": intent.path},
        )

    async def handle_shell_operation(self, intent: ShellOpIntent) -> DispatchResult:
        """Shell command execution via OpenClaw exec tool."""
        blocked = self._maybe_block(
            tool_name="shell_operation",
            goal=intent.raw_text,
            tool_args={"command_preview": (intent.command or "")[:120]},
        )
        if blocked is not None:
            return blocked
        return self._stub_response(
            capability="shell_operations",
            voice_message="I can't run shell commands yet.",
            metadata={"command_preview": intent.command[:60]},
        )

    # --- 4B plan Item 8: block-and-revise pre-flight ------------------------

    def _maybe_block(
        self,
        *,
        tool_name: str,
        goal: str,
        tool_args: Dict[str, Any],
    ) -> Optional[DispatchResult]:
        """Run the block-and-revise validator. Returns ``None`` when the
        call should proceed (validator allows OR feature is disabled OR
        no LLM is wired). Returns a ``DispatchResult`` to short-circuit
        when the validator BLOCKs.

        Failure-safe: any exception inside the validator path falls
        open (returns None), preserving the dispatch path's behaviour.
        """
        try:
            from ultron.openclaw_routing.block_and_revise import (
                ToolCallValidator, is_enabled,
            )
            if not is_enabled(self._cfg):
                return None
            if self._llm is None:
                return None
            validator = ToolCallValidator(self._llm)
            result = validator.validate(
                goal=goal or "(no stated goal)",
                tool_name=tool_name,
                tool_args=tool_args,
            )
        except Exception as e:
            logger.warning("block-and-revise check failed: %s", e)
            return None

        if result.allow:
            return None

        logger.info(
            "block-and-revise blocked %s call: %s",
            tool_name, result.reason,
        )
        return DispatchResult(
            success=False,
            voice_message=(
                f"I held off on that — {result.reason}"
            ),
            error="blocked by block-and-revise validator",
            metadata={
                "blocked": True,
                "tool_name": tool_name,
                "verdict": result.verdict,
                "reason": result.reason,
            },
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
