"""Hierarchical sandbox tool policy with 4-source resolution + alsoAllow.

T11 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Resolves
the effective allow / deny / also_allow sets for a given agent by
merging four sources with source-tagging:

* **agent** scope (per-agent override; highest precedence)
* **global** scope (operator-wide config)
* **default** scope (built-in safe defaults)
* **also_allow** (additive extension that does NOT switch into
  allowlist-only mode)

The four-mode shape is:

* ``allow`` — explicit allowlist. Non-empty switches the policy
  into "allowlist-only" semantics where unlisted tools are
  implicitly denied even when not in ``deny``.
* ``deny`` — explicit denylist. Always wins.
* ``also_allow`` — extension that broadens ``allow`` without
  forcing the switch into allowlist-only mode.
* The special case ``allow = []`` means "allow everything" (the
  deliberate special-case preserved across resolution).

Provenance: every resolved entry carries the source that produced
it (``agent`` / ``global`` / ``default``), useful for the audit log.

Generalises beyond the sandbox use case: per-agent safety policies,
per-channel tool exposure, per-mode (gaming / standby) tool sets
all consume the same shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional


class PolicySource(str, Enum):
    """Provenance tag for a resolved policy entry."""

    AGENT = "agent"
    GLOBAL = "global"
    DEFAULT = "default"


@dataclass(frozen=True)
class SandboxToolPolicy:
    """One scope's policy declaration (agent / global / default).

    Fields default to ``None`` so the resolver can distinguish
    "not set" (use the next scope) from "explicitly empty" (the
    ``allow: []`` special case).

    Attributes:
        allow: explicit allowlist. ``None`` = not set; ``[]`` = allow
            all; non-empty = allowlist-only mode.
        deny: explicit denylist. ``None`` = not set; ``[]`` = no
            denials beyond defaults; non-empty = these tools blocked.
        also_allow: extension allowlist. ``None`` = not set; non-empty
            tools added to allow without switching mode.
    """

    allow: Optional[tuple[str, ...]] = None
    deny: Optional[tuple[str, ...]] = None
    also_allow: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class ResolvedSandboxToolPolicy:
    """Merged policy with provenance.

    Attributes:
        allow: merged allow set (``frozenset``). Empty set when not
            set anywhere (allowlist-only mode is off).
        deny: merged deny set.
        also_allow: merged also-allow extension.
        sources: per-tool ``PolicySource`` annotation.
        allow_is_empty_meaning_unrestricted: ``True`` when ``allow``
            was explicitly set to ``[]`` (the "allow everything"
            special case). Used by :meth:`is_permitted` to decide
            between allowlist-only and unrestricted semantics.
    """

    allow: frozenset[str] = frozenset()
    deny: frozenset[str] = frozenset()
    also_allow: frozenset[str] = frozenset()
    sources: dict[str, PolicySource] = field(default_factory=dict)
    allow_is_empty_meaning_unrestricted: bool = False

    def is_permitted(self, tool: str) -> bool:
        """Decide whether ``tool`` is permitted.

        Order:

        1. ``deny`` is terminal — tool in ``deny`` is always denied.
        2. When ``allow_is_empty_meaning_unrestricted`` is True
           (``allow == []`` special case), any non-denied tool
           passes.
        3. When ``allow`` is non-empty, the tool must be in ``allow``
           OR ``also_allow`` to pass.
        4. When ``allow`` is empty AND the special case is not set,
           any non-denied tool passes (no allowlist enforcement).
        """
        if tool in self.deny:
            return False
        if self.allow_is_empty_meaning_unrestricted:
            return True
        if self.allow:
            return tool in self.allow or tool in self.also_allow
        return True


def _normalise(values: Optional[Iterable[str]]) -> Optional[tuple[str, ...]]:
    """Strip empties + dedupe; preserve order. ``None`` -> ``None``."""
    if values is None:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        if not item:
            continue
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)


def make_policy(
    *,
    allow: Optional[Iterable[str]] = None,
    deny: Optional[Iterable[str]] = None,
    also_allow: Optional[Iterable[str]] = None,
) -> SandboxToolPolicy:
    """Construct a :class:`SandboxToolPolicy` from loose iterables."""
    return SandboxToolPolicy(
        allow=_normalise(allow),
        deny=_normalise(deny),
        also_allow=_normalise(also_allow),
    )


def _pick_first_defined(
    *layers: tuple[Optional[tuple[str, ...]], PolicySource],
) -> tuple[Optional[tuple[str, ...]], PolicySource]:
    """Return the first ``(values, source)`` where values is not None."""
    for values, source in layers:
        if values is not None:
            return values, source
    return None, PolicySource.DEFAULT


def resolve_sandbox_tool_policy(
    *,
    agent: Optional[SandboxToolPolicy] = None,
    global_scope: Optional[SandboxToolPolicy] = None,
    default: Optional[SandboxToolPolicy] = None,
) -> ResolvedSandboxToolPolicy:
    """Merge the four sources into a single :class:`ResolvedSandboxToolPolicy`.

    Precedence (per-axis): agent > global > default. ``also_allow``
    follows the same precedence chain but is then ALSO merged into
    the ``allow`` set when non-empty (additive).

    Args:
        agent: per-agent policy (highest precedence).
        global_scope: operator-wide policy.
        default: built-in defaults.

    Returns:
        :class:`ResolvedSandboxToolPolicy`.
    """
    a = agent or SandboxToolPolicy()
    g = global_scope or SandboxToolPolicy()
    d = default or SandboxToolPolicy()

    allow_values, allow_source = _pick_first_defined(
        (a.allow, PolicySource.AGENT),
        (g.allow, PolicySource.GLOBAL),
        (d.allow, PolicySource.DEFAULT),
    )
    deny_values, deny_source = _pick_first_defined(
        (a.deny, PolicySource.AGENT),
        (g.deny, PolicySource.GLOBAL),
        (d.deny, PolicySource.DEFAULT),
    )
    also_allow_values, also_allow_source = _pick_first_defined(
        (a.also_allow, PolicySource.AGENT),
        (g.also_allow, PolicySource.GLOBAL),
        (d.also_allow, PolicySource.DEFAULT),
    )

    allow_set = frozenset(allow_values or ())
    deny_set = frozenset(deny_values or ())
    also_allow_set = frozenset(also_allow_values or ())
    allow_is_unrestricted = allow_values is not None and len(allow_values) == 0
    sources: dict[str, PolicySource] = {}
    for tool in allow_set:
        sources[tool] = allow_source
    for tool in also_allow_set:
        # also_allow inherits its own source tag; if the tool already
        # has a tag from allow, prefer the more-specific (later wins).
        sources[tool] = also_allow_source
    for tool in deny_set:
        # Deny wins for tagging purposes too — it's the "why this
        # tool was rejected" diagnostic.
        sources[tool] = deny_source
    return ResolvedSandboxToolPolicy(
        allow=allow_set,
        deny=deny_set,
        also_allow=also_allow_set,
        sources=sources,
        allow_is_empty_meaning_unrestricted=allow_is_unrestricted,
    )


def filter_tools(
    tools: Iterable[str],
    policy: ResolvedSandboxToolPolicy,
) -> tuple[str, ...]:
    """Return the subset of ``tools`` permitted under ``policy`` (in order)."""
    return tuple(t for t in tools if policy.is_permitted(t))


def explain(tool: str, policy: ResolvedSandboxToolPolicy) -> str:
    """One-line diagnostic for the audit log."""
    if tool in policy.deny:
        src = policy.sources.get(tool, PolicySource.DEFAULT)
        return f"deny ({src.value})"
    if policy.allow_is_empty_meaning_unrestricted:
        return "allow_all (allow: [] special case)"
    if policy.allow:
        if tool in policy.allow:
            return f"allow ({policy.sources.get(tool, PolicySource.DEFAULT).value})"
        if tool in policy.also_allow:
            return f"also_allow ({policy.sources.get(tool, PolicySource.DEFAULT).value})"
        return "implicit_deny (not in allow)"
    return "default_allow (no allow set, not in deny)"


__all__ = [
    "PolicySource",
    "ResolvedSandboxToolPolicy",
    "SandboxToolPolicy",
    "explain",
    "filter_tools",
    "make_policy",
    "resolve_sandbox_tool_policy",
]
