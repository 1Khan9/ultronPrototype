"""Subagent depth-aware tool-policy denylist (T7).

T7 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Two
denylists govern what a subagent may invoke:

* :data:`SUBAGENT_TOOL_DENY_ALWAYS` — tools a subagent NEVER gets
  regardless of depth. These are orchestrator-only capabilities:
  the gateway / sessions / cron management surface. For ultron,
  the equivalents are TTS speaking (subagents must not speak
  via Kokoro), gaming-mode toggle (mode transitions are
  orchestrator-only), and the safety-validator override path.
* :data:`SUBAGENT_TOOL_DENY_LEAF` — tools a subagent loses at the
  LEAF depth (``depth >= max_spawn_depth``). Intermediate subagents
  (depth = 1 with ``max_spawn_depth >= 2``) keep these so they can
  spawn their own children for fan-out; leaf subagents lose them
  to prevent runaway recursion.

The default ``max_spawn_depth = 1`` means: depth-0 (orchestrator)
spawns depth-1 subagents which CANNOT spawn further (they're at
``depth >= max_spawn_depth``). Bump to 2 to allow one-level of
nested fan-out.

Custom per-deployment denylists supply additional tools to deny,
and the policy resolver merges them with the defaults. Explicit
``allow`` / ``also_allow`` entries in the policy can override
specific deny entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

#: Default max-spawn-depth: orchestrator (depth=0) spawns depth=1
#: subagents which are LEAF (cannot spawn further).
DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH: int = 1

#: Tools every subagent loses regardless of depth. Pattern from
#: OpenClaw's ``SUBAGENT_TOOL_DENY_ALWAYS``. Adapted to ultron's
#: tool-name conventions: gateway management, session listing,
#: cron, direct messaging across the announce chain (subagents
#: communicate via announce, not direct send), TTS speaking,
#: gaming-mode toggle, validator-set, install-skill.
SUBAGENT_TOOL_DENY_ALWAYS: frozenset[str] = frozenset({
    # Gateway + session admin (OpenClaw direct ports).
    "gateway",
    "agents_list",
    "session_status",
    "cron",
    "sessions_send",
    # Ultron-specific extensions: subagents are research/read tools;
    # they MUST NOT speak via TTS, toggle modes, or modify safety.
    "tts_speak",
    "kokoro_speak",
    "gaming_mode_engage",
    "gaming_mode_disengage",
    "mode_router_swap",
    "set_validator",
    "install_skill",
    "uninstall_skill",
})

#: Tools a LEAF subagent loses (in addition to DENY_ALWAYS).
#: Intermediate subagents (depth < max_spawn_depth) keep these so
#: they can manage their own children. Pattern from OpenClaw's
#: ``SUBAGENT_TOOL_DENY_LEAF`` plus ultron MCP add/remove extensions.
SUBAGENT_TOOL_DENY_LEAF: frozenset[str] = frozenset({
    # OpenClaw direct ports.
    "subagents",
    "sessions_list",
    "sessions_history",
    "sessions_spawn",
    # Ultron extensions: MCP server lifecycle is orchestrator-only.
    "mcp_add_server",
    "mcp_remove_server",
})


class PolicySource(str, Enum):
    """Provenance tag for an entry in the resolved policy.

    Mirrors OpenClaw's source-tagging shape so the audit log can
    distinguish operator-supplied tools from defaults.
    """

    AGENT = "agent"
    GLOBAL = "global"
    DEFAULT = "default"


@dataclass(frozen=True)
class PolicyEntry:
    """One policy entry (allow OR deny) with its provenance."""

    tool: str
    source: PolicySource


@dataclass(frozen=True)
class ResolvedSubagentToolPolicy:
    """The merged policy a subagent's tool-guard consults.

    Attributes:
        allow: explicitly-allowed tools. Empty set means "allow all
            EXCEPT deny" (the inverted default). Non-empty allow set
            switches to allowlist-only semantics where unlisted tools
            are rejected even if they're not in the deny list.
        deny: explicitly-denied tools (merged DENY_ALWAYS + maybe
            DENY_LEAF + caller extras). Always applied even when
            ``allow == []``.
        also_allow: extension entries that broaden ``allow`` without
            forcing allowlist-only semantics. Stays additive.
        sources: per-tool provenance, useful for the audit log.
        is_leaf: ``True`` when the resolved policy is for a leaf
            subagent (depth >= max_spawn_depth).
        depth: the actual depth that produced this policy.
        max_spawn_depth: the cap that produced ``is_leaf``.
    """

    allow: frozenset[str] = frozenset()
    deny: frozenset[str] = frozenset()
    also_allow: frozenset[str] = frozenset()
    sources: dict[str, PolicySource] = field(default_factory=dict)
    is_leaf: bool = True
    depth: int = 0
    max_spawn_depth: int = DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH

    def is_permitted(self, tool: str) -> bool:
        """Decide whether ``tool`` is permitted under this policy.

        Order:

        1. ``deny`` is terminal — tool in deny always rejected.
        2. If ``allow`` is set (non-empty), tool must appear in
           ``allow`` OR ``also_allow`` to be permitted.
        3. If ``allow`` is empty, any tool not in ``deny`` is
           permitted (including tools in ``also_allow``).
        """
        if tool in self.deny:
            return False
        if self.allow:
            return tool in self.allow or tool in self.also_allow
        return True

    def explain(self, tool: str) -> str:
        """One-line diagnostic for the audit log."""
        if tool in self.deny:
            src = self.sources.get(tool, PolicySource.DEFAULT)
            return f"deny ({src.value})"
        if self.allow:
            if tool in self.allow:
                return f"allow ({self.sources.get(tool, PolicySource.DEFAULT).value})"
            if tool in self.also_allow:
                return f"also_allow ({self.sources.get(tool, PolicySource.DEFAULT).value})"
            return "implicit_deny (not in allow)"
        return "default_allow (no allow set, not in deny)"


@dataclass(frozen=True)
class SubagentPolicyConfig:
    """Caller-supplied policy customisation.

    Attributes:
        max_spawn_depth: cap for "leaf" determination.
        extra_deny: additional tools to deny beyond the defaults.
        extra_deny_leaf: additional tools to deny only at leaf depth.
        allow: explicit allowlist (switches to allowlist-only when set).
        also_allow: extension allowlist (additive; doesn't switch mode).
        clear_default_deny_always: when True, only deny the
            caller-supplied ``extra_deny`` (operator override; rarely
            used; audit-logged loudly when set).
        clear_default_deny_leaf: same for the leaf-only defaults.
    """

    max_spawn_depth: int = DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH
    extra_deny: frozenset[str] = frozenset()
    extra_deny_leaf: frozenset[str] = frozenset()
    allow: frozenset[str] = frozenset()
    also_allow: frozenset[str] = frozenset()
    clear_default_deny_always: bool = False
    clear_default_deny_leaf: bool = False


def is_leaf(depth: int, *, max_spawn_depth: int = DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH) -> bool:
    """``True`` when a subagent at ``depth`` is at the spawn cap."""
    if max_spawn_depth < 1:
        max_spawn_depth = 1
    return depth >= max_spawn_depth


def resolve_subagent_tool_policy(
    *,
    depth: int = 1,
    config: Optional[SubagentPolicyConfig] = None,
) -> ResolvedSubagentToolPolicy:
    """Resolve the effective subagent tool policy for ``depth``.

    Args:
        depth: the subagent's depth in the spawn tree. Depth 0 is the
            orchestrator (typically not passed to this resolver);
            depth 1 is the orchestrator's first-spawn level. Defaults
            to 1.
        config: optional :class:`SubagentPolicyConfig` for per-deployment
            customisation. ``None`` uses the defaults.

    Returns:
        :class:`ResolvedSubagentToolPolicy` with merged deny + allow
        sets and the provenance map.
    """
    cfg = config or SubagentPolicyConfig()
    leaf = is_leaf(depth, max_spawn_depth=cfg.max_spawn_depth)
    sources: dict[str, PolicySource] = {}
    deny: set[str] = set()
    if not cfg.clear_default_deny_always:
        for tool in SUBAGENT_TOOL_DENY_ALWAYS:
            deny.add(tool)
            sources[tool] = PolicySource.DEFAULT
    if leaf and not cfg.clear_default_deny_leaf:
        for tool in SUBAGENT_TOOL_DENY_LEAF:
            deny.add(tool)
            sources.setdefault(tool, PolicySource.DEFAULT)
    for tool in cfg.extra_deny:
        deny.add(tool)
        sources[tool] = PolicySource.AGENT
    if leaf:
        for tool in cfg.extra_deny_leaf:
            deny.add(tool)
            sources[tool] = PolicySource.AGENT
    # When a tool appears in both deny and allow / also_allow, the
    # operator override wins — remove from deny and tag source.
    allow_set = frozenset(cfg.allow)
    also_allow_set = frozenset(cfg.also_allow)
    for tool in allow_set | also_allow_set:
        if tool in deny:
            deny.discard(tool)
        sources[tool] = PolicySource.AGENT
    return ResolvedSubagentToolPolicy(
        allow=allow_set,
        deny=frozenset(deny),
        also_allow=also_allow_set,
        sources=sources,
        is_leaf=leaf,
        depth=depth,
        max_spawn_depth=cfg.max_spawn_depth,
    )


def filter_tools_by_policy(
    tools: Iterable[str],
    policy: ResolvedSubagentToolPolicy,
) -> tuple[str, ...]:
    """Return the subset of ``tools`` permitted under ``policy``.

    Preserves input order. Useful for filtering a tool-catalog list
    before exposing it to a subagent's prompt.
    """
    return tuple(t for t in tools if policy.is_permitted(t))


__all__ = [
    "DEFAULT_SUBAGENT_MAX_SPAWN_DEPTH",
    "PolicyEntry",
    "PolicySource",
    "ResolvedSubagentToolPolicy",
    "SUBAGENT_TOOL_DENY_ALWAYS",
    "SUBAGENT_TOOL_DENY_LEAF",
    "SubagentPolicyConfig",
    "filter_tools_by_policy",
    "is_leaf",
    "resolve_subagent_tool_policy",
]
