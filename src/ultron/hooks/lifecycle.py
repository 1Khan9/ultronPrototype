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
    """Lifecycle point at which a hook may fire."""

    TASK_START = "TaskStart"
    TASK_RESUME = "TaskResume"
    TASK_CANCEL = "TaskCancel"
    TASK_COMPLETE = "TaskComplete"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    PRE_COMPACT = "PreCompact"
    NOTIFICATION = "Notification"
    # Ultron-specific lifecycle extensions.
    PRE_LLM_REQUEST = "PreLLMRequest"
    PRE_MEMORY_WRITE = "PreMemoryWrite"
    PRE_GAMING_ENGAGE = "PreGamingEngage"
    PRE_DESKTOP_ACTION = "PreDesktopAction"
    WAKE_WORD_TRIGGERED = "WakeWordTriggered"


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


__all__ = [
    "DEFAULT_CONTEXT_MOD_CAP_CHARS",
    "DEFAULT_HOOK_TIMEOUT_SECONDS",
    "HookKind",
    "HookOutcome",
    "HookPayload",
]
