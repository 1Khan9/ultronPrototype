"""Hook lifecycle enum, payload types, and outcome envelope.

The lifecycle points mirror cline's nine-hook catalog (TaskStart,
TaskResume, TaskCancel, TaskComplete, UserPromptSubmit, PreToolUse,
PostToolUse, PreCompact, Notification) with ultron-specific extras
exposed for the voice path: PreMemoryWrite, PreGamingEngage,
PreDesktopAction, WakeWordTriggered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

#: Default per-hook timeout (seconds). Tighter than cline's 30 s
#: default — the voice path is latency-sensitive and the typical hook
#: is a small Python / PowerShell script.
DEFAULT_HOOK_TIMEOUT_SECONDS: float = 10.0

#: Cap on the ``context_modification`` field returned by a hook (chars).
#: Cline's 50 kB ceiling is too aggressive for the voice context
#: budget; 8 kB is the right size for a one-paragraph injection.
DEFAULT_CONTEXT_MOD_CAP_CHARS: int = 8 * 1024


class HookKind(str, Enum):
    """Lifecycle point at which a hook may fire.

    Initial 14 lifecycle points came from cline's hook catalog plus
    ultron-specific voice extensions. T3 (OpenClaw catalog port; see
    ``THIRD_PARTY_NOTICES.md``) adds 22 additional events giving a
    total of ~36 lifecycle points covering every meaningful agent
    transition: model resolution, prompt build, compaction symmetry,
    message inbound/outbound, subagent quartet (spawning / spawned /
    delivery / ended), gateway lifecycle, periodic heartbeat, cron
    state changes.
    """

    # Original cline-derived 9 lifecycle points.
    TASK_START = "TaskStart"
    TASK_RESUME = "TaskResume"
    TASK_CANCEL = "TaskCancel"
    TASK_COMPLETE = "TaskComplete"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    PRE_COMPACT = "PreCompact"
    NOTIFICATION = "Notification"
    # Ultron-specific voice extensions (original 5).
    PRE_LLM_REQUEST = "PreLLMRequest"
    PRE_MEMORY_WRITE = "PreMemoryWrite"
    PRE_GAMING_ENGAGE = "PreGamingEngage"
    PRE_DESKTOP_ACTION = "PreDesktopAction"
    WAKE_WORD_TRIGGERED = "WakeWordTriggered"
    # T3 OpenClaw additions: model + prompt lifecycle.
    BEFORE_MODEL_RESOLVE = "BeforeModelResolve"
    BEFORE_PROMPT_BUILD = "BeforePromptBuild"
    AGENT_TURN_PREPARE = "AgentTurnPrepare"
    BEFORE_AGENT_REPLY = "BeforeAgentReply"
    MODEL_CALL_STARTED = "ModelCallStarted"
    MODEL_CALL_ENDED = "ModelCallEnded"
    LLM_INPUT = "LlmInput"
    LLM_OUTPUT = "LlmOutput"
    BEFORE_AGENT_FINALIZE = "BeforeAgentFinalize"
    AGENT_END = "AgentEnd"
    BEFORE_AGENT_RUN = "BeforeAgentRun"
    # T3 OpenClaw additions: compaction + reset symmetry.
    AFTER_COMPACTION = "AfterCompaction"
    BEFORE_RESET = "BeforeReset"
    # T3 OpenClaw additions: inbound / outbound message lifecycle.
    INBOUND_CLAIM = "InboundClaim"
    MESSAGE_RECEIVED = "MessageReceived"
    MESSAGE_SENDING = "MessageSending"
    MESSAGE_SENT = "MessageSent"
    BEFORE_MESSAGE_WRITE = "BeforeMessageWrite"
    TOOL_RESULT_PERSIST = "ToolResultPersist"
    # T3 OpenClaw additions: session lifecycle.
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    # T3 OpenClaw additions: subagent quartet.
    SUBAGENT_SPAWNING = "SubagentSpawning"
    SUBAGENT_SPAWNED = "SubagentSpawned"
    SUBAGENT_ENDED = "SubagentEnded"
    SUBAGENT_DELIVERY_TARGET = "SubagentDeliveryTarget"
    # T3 OpenClaw additions: gateway + scheduled work.
    GATEWAY_START = "GatewayStart"
    GATEWAY_STOP = "GatewayStop"
    HEARTBEAT_PROMPT_CONTRIBUTION = "HeartbeatPromptContribution"
    CRON_CHANGED = "CronChanged"


@dataclass(frozen=True)
class HookPayload:
    """JSON payload delivered to a hook script over stdin.

    Attributes:
        kind: lifecycle point firing this hook.
        session_id: session identifier (informational; hooks may use
            it for per-session state files).
        turn_id: optional per-turn identifier (the orchestrator's
            ``trace`` module assigns these).
        actor: short identifier of the producing subsystem
            (``"voice"`` / ``"coding"`` / ``"supervisor"`` / etc.).
        extra: free-form payload specific to the lifecycle point
            (tool name + args for ``PRE_TOOL_USE``, summary text for
            ``PRE_COMPACT``, etc.).
    """

    kind: HookKind
    session_id: str = ""
    turn_id: str = ""
    actor: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Render the payload as a JSON-serialisable dict."""
        return {
            "kind": self.kind.value,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "actor": self.actor,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True)
class HookOutcome:
    """Parsed response from a single hook execution.

    Attributes:
        cancel: when True, the orchestrator should ABORT the action
            associated with this lifecycle point (e.g. block the
            PreToolUse, skip the compaction).
        context_modification: optional string the orchestrator concats
            into the next prompt (truncated to
            :data:`DEFAULT_CONTEXT_MOD_CAP_CHARS`).
        error_message: optional error string the hook surfaced (purely
            informational — the orchestrator decides whether to relay).
        extra: free-form extra fields the hook returned (forwarded to
            observability sinks but not interpreted by the orchestrator).
    """

    cancel: bool = False
    context_modification: str = ""
    error_message: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# T3 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``):
# discriminated-union HookDecision shape with severity-based merging.
# The cline-derived HookOutcome above is the per-hook subprocess
# response shape (JSON over stdout); HookDecision below is the
# in-process pass/block discriminated-union for plugin policies that
# don't go through the subprocess boundary.


class HookOutcomeKind(str, Enum):
    """Outcome discriminator for :class:`HookDecision`."""

    PASS = "pass"
    BLOCK = "block"


#: Severity table for merging multiple decisions. Higher number wins
#: when merging; ``block`` always beats ``pass``.
HOOK_DECISION_SEVERITY: dict[HookOutcomeKind, int] = {
    HookOutcomeKind.PASS: 0,
    HookOutcomeKind.BLOCK: 2,
}


@dataclass(frozen=True)
class HookDecision:
    """Discriminated-union decision returned by an in-process hook.

    Use :func:`make_pass` / :func:`make_block` to construct; the
    discriminator field ``outcome`` distinguishes the two cases.

    Attributes:
        outcome: ``PASS`` or ``BLOCK`` discriminator.
        reason: INTERNAL diagnostic. Always populated for ``BLOCK``;
            never spoken to the user verbatim. Includes the matched
            pattern / file path / regex fragment.
        message: USER-FACING wording. Optional for ``PASS``. When
            present on a ``BLOCK``, this is what the orchestrator
            speaks via TTS (the synthesised fallback "Your request
            was blocked..." form is used when ``message`` is empty).
        category: analytics label (``"pii"`` / ``"cost_limit"`` /
            ``"voice_lock"``). Lets audit dashboards group by
            reason without hard-coding the taxonomy into core.
        metadata: opaque per-hook blob; carried through to observability
            sinks but not interpreted by the merger.
    """

    outcome: HookOutcomeKind = HookOutcomeKind.PASS
    reason: str = ""
    message: str = ""
    category: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return self.outcome == HookOutcomeKind.BLOCK

    @property
    def severity(self) -> int:
        return HOOK_DECISION_SEVERITY.get(self.outcome, 0)


def make_pass(message: str = "") -> HookDecision:
    """Construct a :class:`HookDecision` with ``PASS`` outcome."""
    return HookDecision(outcome=HookOutcomeKind.PASS, message=message)


def make_block(
    reason: str,
    *,
    message: str = "",
    category: str = "",
    metadata: Optional[Mapping[str, Any]] = None,
) -> HookDecision:
    """Construct a :class:`HookDecision` with ``BLOCK`` outcome.

    Args:
        reason: REQUIRED. Internal diagnostic (matched pattern, etc.).
            Never empty for a block.
        message: Optional user-facing wording. When empty, the caller
            synthesises a generic block message.
        category: Optional analytics label.
        metadata: Optional opaque per-hook blob.

    Returns:
        :class:`HookDecision`.
    """
    if not reason:
        raise ValueError("block decisions must include a non-empty reason")
    return HookDecision(
        outcome=HookOutcomeKind.BLOCK,
        reason=reason,
        message=message,
        category=category,
        metadata=metadata or {},
    )


def merge_hook_decisions(
    a: Optional[HookDecision],
    b: HookDecision,
) -> HookDecision:
    """Merge two decisions, most-restrictive wins.

    ``a == None`` is treated as a permissive pass; ``b`` always wins
    in that case. When both are blocks, the first-blocked one is
    preserved (it ran earliest, so its diagnostic is closest to the
    triggering condition).
    """
    if a is None:
        return b
    a_sev = a.severity
    b_sev = b.severity
    if b_sev > a_sev:
        return b
    return a


def resolve_block_message(
    decision: HookDecision,
    *,
    blocked_by: str = "",
    fallback_prefix: str = "Your request was blocked",
) -> str:
    """Format the user-facing block message for ``decision``.

    Args:
        decision: A blocked :class:`HookDecision`.
        blocked_by: Optional plugin / rule identifier appended in
            parentheses (e.g. ``"pii_redactor"``).
        fallback_prefix: Used when ``decision.message`` is empty.

    Returns:
        Formatted string suitable for TTS / channel delivery.
    """
    if not decision.blocked:
        return ""
    body = decision.message or fallback_prefix
    if blocked_by:
        return f"{body} (blocked by {blocked_by})"
    return body


__all__ = [
    "DEFAULT_CONTEXT_MOD_CAP_CHARS",
    "DEFAULT_HOOK_TIMEOUT_SECONDS",
    "HOOK_DECISION_SEVERITY",
    "HookDecision",
    "HookKind",
    "HookOutcome",
    "HookOutcomeKind",
    "HookPayload",
    "make_block",
    "make_pass",
    "merge_hook_decisions",
    "resolve_block_message",
]
