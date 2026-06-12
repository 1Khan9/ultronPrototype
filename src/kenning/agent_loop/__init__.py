"""Agent-loop primitives shared across the voice / coding / supervisor paths.

This package collects small helpers that govern the *outer* agent loop
(loop-detection, tool-signature normalisation, fan-out coordinators) so
each subsystem can opt in without dragging the orchestrator's full
machinery along.
"""

from __future__ import annotations

from .base import (
    DEFAULT_LOOP_REPEAT_CAP,
    DEFAULT_MAX_STEPS,
    AgentLoop,
    AgentLoopError,
    LoopResult,
    LoopStatus,
    StepOutcome,
    StepRecord,
)
from .loop_detection import (
    DEFAULT_HARD_THRESHOLD,
    DEFAULT_SOFT_THRESHOLD,
    LoopDetector,
    LoopVerdict,
    tool_call_signature,
)
from .mode import (
    DEFAULT_CODING_ARCHITECT_PREFIX,
    DEFAULT_PLAN_ACK,
    DEFAULT_PLAN_PREFIX,
    DEFAULT_POLICIES,
    Mode,
    ModeFlipResult,
    ModePolicy,
    ModeSession,
    PendingConfirmation,
    drop_mode_session,
    get_mode_session,
    reset_registry_for_testing,
)
from .subagent import (
    DEFAULT_READONLY_TOOL_WHITELIST,
    SubagentBatchStats,
    SubagentResult,
    SubagentRunner,
    SubagentTask,
    TokenLedger,
    ToolGuard,
    ToolNotPermittedError,
)

__all__ = [
    "AgentLoop",
    "AgentLoopError",
    "DEFAULT_CODING_ARCHITECT_PREFIX",
    "DEFAULT_HARD_THRESHOLD",
    "DEFAULT_LOOP_REPEAT_CAP",
    "DEFAULT_MAX_STEPS",
    "LoopResult",
    "LoopStatus",
    "StepOutcome",
    "StepRecord",
    "DEFAULT_PLAN_ACK",
    "DEFAULT_PLAN_PREFIX",
    "DEFAULT_POLICIES",
    "DEFAULT_READONLY_TOOL_WHITELIST",
    "DEFAULT_SOFT_THRESHOLD",
    "LoopDetector",
    "LoopVerdict",
    "Mode",
    "ModeFlipResult",
    "ModePolicy",
    "ModeSession",
    "PendingConfirmation",
    "SubagentBatchStats",
    "SubagentResult",
    "SubagentRunner",
    "SubagentTask",
    "TokenLedger",
    "ToolGuard",
    "ToolNotPermittedError",
    "drop_mode_session",
    "get_mode_session",
    "reset_registry_for_testing",
    "tool_call_signature",
]
