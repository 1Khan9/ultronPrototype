"""Phase 5 — capability routing layer.

Sits between the orchestrator's voice path and the existing
:mod:`kenning.coding` runner. Classifies user utterances into:

  * coding intents (delegated to the existing coding intent classifier)
  * conversational (default voice path)
  * OpenClaw-bound capabilities (browser, media, messaging, files, shell)
  * hybrid tasks that need decomposition

OpenClaw itself is NOT integrated yet — the dispatcher returns
in-character stub responses. The OpenClaw integration prompt fills these
stubs in with real Gateway calls.

Public API:

  * :class:`RoutingIntent` / :class:`RoutingIntentKind`
  * :func:`classify_routing` — main classifier
  * :class:`OpenClawDispatcher` — stubbed dispatch surface
  * :class:`AutomationTaskRunner` — stubbed-but-functional runner mirror
  * :class:`HybridTaskDecomposer` — Qwen-driven task decomposition
  * :class:`IntentDisambiguator` — Qwen-driven ambiguity resolution
  * :class:`RoutingDecisionLog` — JSONL writer for audit
"""

from kenning.openclaw_routing.intents import (
    AutomationIntent,
    BrowserIntent,
    DispatchResult,
    FileOpIntent,
    HybridSubtask,
    MediaGenIntent,
    MessagingIntent,
    RoutingIntent,
    RoutingIntentKind,
    ShellOpIntent,
    TaskInfo,
)
from kenning.openclaw_routing.classifier import classify_routing
from kenning.openclaw_routing.decision_log import (
    RoutingDecisionLog,
    get_routing_log,
    set_routing_log,
)
from kenning.openclaw_routing.decomposer import HybridTaskDecomposer
from kenning.openclaw_routing.disambiguator import (
    DisambiguationResult,
    IntentDisambiguator,
)
from kenning.openclaw_routing.dispatcher import OpenClawDispatcher
from kenning.openclaw_routing.runner import AutomationTaskRunner

__all__ = [
    "AutomationIntent",
    "AutomationTaskRunner",
    "BrowserIntent",
    "DisambiguationResult",
    "DispatchResult",
    "FileOpIntent",
    "HybridSubtask",
    "HybridTaskDecomposer",
    "IntentDisambiguator",
    "MediaGenIntent",
    "MessagingIntent",
    "OpenClawDispatcher",
    "RoutingDecisionLog",
    "RoutingIntent",
    "RoutingIntentKind",
    "ShellOpIntent",
    "TaskInfo",
    "classify_routing",
    "get_routing_log",
    "set_routing_log",
]
