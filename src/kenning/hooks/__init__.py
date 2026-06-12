"""Out-of-process hook lifecycle system.

Adapted from cline's ``src/core/hooks/`` family (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Hooks live under
``~/.ultron/hooks/<HookName>`` (global) and
``<project_root>/.ultron/hooks/<HookName>`` (project) as shebanged
executable files; ultron's variant additionally accepts ``<HookName>.py``
and ``<HookName>.ps1`` extensions so Windows users can drop scripts
without setting executable bits.

The runner spawns the matching script, writes the JSON-encoded
payload to stdin, reads JSON from stdout, and parses the
``{cancel, context_modification, error_message}`` envelope. The
registry composes multiple hooks per lifecycle point via parallel
fan-out (``asyncio.gather``); any ``cancel: true`` blocks the action,
and every ``context_modification`` is concatenated into the next
prompt.
"""

from __future__ import annotations

from .discovery import (
    DEFAULT_DISCOVERY_TTL_SECONDS,
    HookDiscovery,
    HookScript,
    discover_hook_scripts,
)
from .lifecycle import (
    DEFAULT_CONTEXT_MOD_CAP_CHARS,
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    HookKind,
    HookOutcome,
    HookPayload,
)
from .registry import (
    HookFanoutResult,
    HookRegistry,
    get_hook_registry,
    reset_hook_registry_for_testing,
)
from .runner import HookExecutionError, HookRunner, HookRunResult

__all__ = [
    "DEFAULT_CONTEXT_MOD_CAP_CHARS",
    "DEFAULT_DISCOVERY_TTL_SECONDS",
    "DEFAULT_HOOK_TIMEOUT_SECONDS",
    "HookDiscovery",
    "HookExecutionError",
    "HookFanoutResult",
    "HookKind",
    "HookOutcome",
    "HookPayload",
    "HookRegistry",
    "HookRunResult",
    "HookRunner",
    "HookScript",
    "discover_hook_scripts",
    "get_hook_registry",
    "reset_hook_registry_for_testing",
]
