"""Activation planner for skills / plugins / channels (T15).

T15 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Loads
a manifest's cheap activation triggers BEFORE the plugin's runtime
imports so cold-start stays fast and idle subsystems don't load
their dependencies.

A manifest declares triggers like::

    activation:
      on_startup: false
      on_capabilities: ["voice", "coding"]
      on_commands: ["search", "rag"]
      on_channels: ["voice"]
      on_routes: ["WEB_SEARCH"]
      on_config_paths: ["web_search.enabled"]
      on_providers: ["brave", "searxng"]

When the orchestrator builds its activation context (active
capabilities, current channels, configured providers, etc.), it
calls :func:`evaluate_activation` for each candidate manifest.
Manifests whose triggers don't match get skipped — their bodies
are never loaded.

Generalises beyond OpenClaw's plugin marketplace use case: the
same trigger shape applies to skills, intent-phrase packs,
voice-ack pools, safety-rule packs, persona overlays, memory
backends, VLM lazy-load, future channels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence

LOGGER = logging.getLogger(__name__)


class CapabilityKind(str, Enum):
    """Standard capability tags an activation trigger may reference.

    Free-form strings beyond this set are accepted (open-ended), but
    the values here are the canonical ones the orchestrator emits.
    """

    PROVIDER = "provider"
    CHANNEL = "channel"
    TOOL = "tool"
    HOOK = "hook"
    SKILL = "skill"
    INTENT = "intent"
    VOICE = "voice"
    CODING = "coding"
    MEMORY = "memory"
    DESKTOP = "desktop"
    GAMING = "gaming"


@dataclass(frozen=True)
class ActivationTriggers:
    """Activation trigger declaration for a manifest.

    Empty / unset triggers behave as "don't trigger on this axis";
    a manifest with ALL triggers empty AND ``on_startup=False`` will
    never activate (deliberate: forces operators to declare what
    they're activating on).
    """

    on_startup: bool = False
    on_providers: tuple[str, ...] = ()
    on_agent_harnesses: tuple[str, ...] = ()
    on_commands: tuple[str, ...] = ()
    on_channels: tuple[str, ...] = ()
    on_routes: tuple[str, ...] = ()
    on_config_paths: tuple[str, ...] = ()
    on_capabilities: tuple[str, ...] = ()

    @property
    def has_any(self) -> bool:
        """True when at least one trigger is non-empty."""
        return (
            self.on_startup
            or bool(self.on_providers)
            or bool(self.on_agent_harnesses)
            or bool(self.on_commands)
            or bool(self.on_channels)
            or bool(self.on_routes)
            or bool(self.on_config_paths)
            or bool(self.on_capabilities)
        )


@dataclass(frozen=True)
class ActivationContext:
    """Runtime context the planner evaluates manifests against.

    The orchestrator builds one of these at startup (and rebuilds
    whenever its set of active providers / channels / commands
    changes) and passes it to :func:`evaluate_activation`.
    """

    is_startup: bool = True
    providers: frozenset[str] = frozenset()
    agent_harnesses: frozenset[str] = frozenset()
    commands: frozenset[str] = frozenset()
    channels: frozenset[str] = frozenset()
    routes: frozenset[str] = frozenset()
    config_paths_set: frozenset[str] = frozenset()
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ActivationResult:
    """Outcome of evaluating one manifest's triggers against context.

    Attributes:
        activated: ``True`` when at least one trigger matched.
        matched_axes: which axis names produced the match
            (``"on_startup"`` / ``"on_capabilities"`` / etc.).
        matched_values: per-axis intersection of trigger values with
            context values (useful for the audit log).
    """

    activated: bool
    matched_axes: tuple[str, ...] = ()
    matched_values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


def _normalise_triggers(value: Optional[Iterable[str]]) -> tuple[str, ...]:
    """Filter ``None`` and empty strings; deduplicate; preserve order."""
    if not value:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        if not item:
            continue
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)


def make_triggers(
    *,
    on_startup: bool = False,
    on_providers: Optional[Iterable[str]] = None,
    on_agent_harnesses: Optional[Iterable[str]] = None,
    on_commands: Optional[Iterable[str]] = None,
    on_channels: Optional[Iterable[str]] = None,
    on_routes: Optional[Iterable[str]] = None,
    on_config_paths: Optional[Iterable[str]] = None,
    on_capabilities: Optional[Iterable[str]] = None,
) -> ActivationTriggers:
    """Construct a :class:`ActivationTriggers` from loose iterables.

    Normalises each axis (strips empties, deduplicates, preserves
    insertion order).
    """
    return ActivationTriggers(
        on_startup=bool(on_startup),
        on_providers=_normalise_triggers(on_providers),
        on_agent_harnesses=_normalise_triggers(on_agent_harnesses),
        on_commands=_normalise_triggers(on_commands),
        on_channels=_normalise_triggers(on_channels),
        on_routes=_normalise_triggers(on_routes),
        on_config_paths=_normalise_triggers(on_config_paths),
        on_capabilities=_normalise_triggers(on_capabilities),
    )


def evaluate_activation(
    triggers: ActivationTriggers,
    context: ActivationContext,
) -> ActivationResult:
    """Decide whether ``triggers`` activate under ``context``.

    A manifest activates when ANY trigger axis matches. This is the
    "load if any reason applies" semantic (vs "load only when all
    reasons apply"). Matching is set-intersection within each axis.

    Args:
        triggers: the manifest's declared triggers.
        context: the runtime activation context.

    Returns:
        :class:`ActivationResult` with the matched axes + per-axis
        intersections.
    """
    matched_axes: list[str] = []
    matched_values: dict[str, tuple[str, ...]] = {}
    if triggers.on_startup and context.is_startup:
        matched_axes.append("on_startup")
    for axis_name, trigger_values, context_values in (
        ("on_providers", triggers.on_providers, context.providers),
        ("on_agent_harnesses", triggers.on_agent_harnesses, context.agent_harnesses),
        ("on_commands", triggers.on_commands, context.commands),
        ("on_channels", triggers.on_channels, context.channels),
        ("on_routes", triggers.on_routes, context.routes),
        ("on_config_paths", triggers.on_config_paths, context.config_paths_set),
        ("on_capabilities", triggers.on_capabilities, context.capabilities),
    ):
        if not trigger_values:
            continue
        overlap = tuple(v for v in trigger_values if v in context_values)
        if overlap:
            matched_axes.append(axis_name)
            matched_values[axis_name] = overlap
    return ActivationResult(
        activated=bool(matched_axes),
        matched_axes=tuple(matched_axes),
        matched_values=matched_values,
    )


@dataclass(frozen=True)
class ActivationCandidate:
    """One manifest + its triggers, ready for the planner."""

    identifier: str
    triggers: ActivationTriggers
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivationPlanResult:
    """Outcome of evaluating an entire candidate set.

    Attributes:
        activated: identifiers that activated.
        skipped: identifiers that did not.
        per_candidate: full :class:`ActivationResult` keyed by identifier.
    """

    activated: tuple[str, ...]
    skipped: tuple[str, ...]
    per_candidate: Mapping[str, ActivationResult] = field(default_factory=dict)


def plan_activation(
    candidates: Sequence[ActivationCandidate],
    context: ActivationContext,
) -> ActivationPlanResult:
    """Evaluate every candidate; return aggregated activation plan.

    Args:
        candidates: every manifest known to the orchestrator (skill /
            plugin / channel / etc.). Order is preserved in the
            activation order.
        context: runtime activation context.

    Returns:
        :class:`ActivationPlanResult` with the activated + skipped
        identifier lists.
    """
    activated: list[str] = []
    skipped: list[str] = []
    per: dict[str, ActivationResult] = {}
    for candidate in candidates:
        if not candidate.triggers.has_any:
            # Defensive: a manifest with no triggers at all never
            # activates (forces operators to declare intent).
            per[candidate.identifier] = ActivationResult(activated=False)
            skipped.append(candidate.identifier)
            continue
        result = evaluate_activation(candidate.triggers, context)
        per[candidate.identifier] = result
        if result.activated:
            activated.append(candidate.identifier)
        else:
            skipped.append(candidate.identifier)
    return ActivationPlanResult(
        activated=tuple(activated),
        skipped=tuple(skipped),
        per_candidate=per,
    )


def auto_enable_for_configured_providers(
    candidates: Sequence[ActivationCandidate],
    configured_providers: frozenset[str],
) -> tuple[str, ...]:
    """Return identifiers whose ``on_providers`` references a configured provider.

    Implements OpenClaw's ``autoEnableWhenConfiguredProviders``
    pattern: a provider plugin auto-enables when the user's config
    references its provider id, without needing a separate "enable
    this plugin" toggle.
    """
    out: list[str] = []
    for candidate in candidates:
        if not candidate.triggers.on_providers:
            continue
        if any(p in configured_providers for p in candidate.triggers.on_providers):
            out.append(candidate.identifier)
    return tuple(out)


__all__ = [
    "ActivationCandidate",
    "ActivationContext",
    "ActivationPlanResult",
    "ActivationResult",
    "ActivationTriggers",
    "CapabilityKind",
    "auto_enable_for_configured_providers",
    "evaluate_activation",
    "make_triggers",
    "plan_activation",
]
