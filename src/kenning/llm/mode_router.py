"""Per-mode LLM preset router.

Adapted from cline's ``buildApiHandler`` + ``planModeApiProvider`` vs
``actModeApiProvider`` per-task selection (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Ultron's variant maps an
:class:`ultron.agent_loop.mode.Mode` to a preset name configured in
``config.yaml:llm.presets`` and delegates the actual hot-swap to the
existing :meth:`LLMEngine.reload_for_preset` path.

The router is intentionally I/O-free: it owns the mode -> preset
mapping + the hot-swap interlock + the per-swap event hook, and
delegates the actual GGUF reload to the engine. This keeps the in-
process llama-cpp dependency out of the import path so tests / non-
voice subsystems can use the router without loading models.

Key shapes:

* :class:`PresetEntry` -- the route for a single mode (preset name,
  optional sampling overrides, optional context-window override).
* :class:`SwapResult` -- outcome of a swap attempt (succeeded,
  reused, failed_reason).
* :class:`ModeLLMRouter` -- holds the mode -> preset mapping, exposes
  ``ensure_preset_for(mode)`` which either no-ops (already on the
  right preset) or asks the engine to reload.

The interlock is RLock-guarded so concurrent ``ensure_preset_for``
calls from the orchestrator + the background summarizer don't race
into a double-reload. The engine handle is passed in as an opaque
callable so test code can substitute a fake.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from ultron.agent_loop.mode import Mode


@dataclass(frozen=True)
class PresetEntry:
    """A mode -> preset route.

    Attributes:
        preset_name: the preset string consumed by
            :meth:`LLMEngine.reload_for_preset`. Must match a key in
            ``config.yaml:llm.presets``.
        sampling_overrides: optional mapping of sampling kwargs
            (``temperature``, ``top_p``, ``top_k``, ``repeat_penalty``)
            applied on top of the preset's defaults. The router merely
            carries these; the engine is responsible for honouring
            them when it builds the chat completion kwargs.
        context_window_override: optional ``n_ctx`` override. ``0``
            keeps the preset default.
        notes: free-form annotation -- shown in the audit log.
    """

    preset_name: str
    sampling_overrides: Mapping[str, Any] = field(default_factory=dict)
    context_window_override: int = 0
    notes: str = ""


#: Default mode -> preset routes. Caller can override the entire map
#: via :class:`ModeLLMRouter` constructor or per-entry via
#: :meth:`ModeLLMRouter.set_preset`. The defaults match ultron's
#: current standby (``qwen3.5-4b``) + gaming (``llama-3.2-3b-abliterated``)
#: + coding-architect (uses the same standby preset but with lower
#: temperature for determinism) layout.
DEFAULT_ROUTES: Mapping[Mode, PresetEntry] = {
    Mode.ACT: PresetEntry(preset_name="qwen3.5-4b"),
    Mode.PLAN: PresetEntry(
        preset_name="qwen3.5-4b",
        sampling_overrides={"temperature": 0.5},
        notes="cooler sampling for terse plan ack",
    ),
    Mode.CODING_EDITOR: PresetEntry(
        preset_name="qwen3.5-4b",
        sampling_overrides={"temperature": 0.2},
        notes="determinism for code edits",
    ),
    Mode.CODING_ARCHITECT: PresetEntry(
        preset_name="qwen3.5-4b",
        sampling_overrides={"temperature": 0.4},
        notes="architect narration",
    ),
    Mode.GAMING: PresetEntry(
        preset_name="llama-3.2-3b-abliterated",
        notes="cheap gaming swap (VRAM reclaim)",
    ),
}


@dataclass(frozen=True)
class SwapResult:
    """Outcome of a preset swap attempt.

    Attributes:
        target_mode: the mode the router was asked to switch into.
        target_preset: the preset chosen for that mode.
        succeeded: ``True`` when the engine is now on the target
            preset.
        was_already_active: ``True`` when no reload was needed.
        failure_reason: empty when ``succeeded``; otherwise a short
            human-readable string.
        sampling_overrides: per-mode sampling overrides the caller
            should apply on the next generation.
        context_window_override: per-mode n_ctx override (``0`` for none).
    """

    target_mode: Mode
    target_preset: str
    succeeded: bool
    was_already_active: bool = False
    failure_reason: str = ""
    sampling_overrides: Mapping[str, Any] = field(default_factory=dict)
    context_window_override: int = 0


#: Type for the reload callable injected into :class:`ModeLLMRouter`.
#: Signature matches the existing :meth:`LLMEngine.reload_for_preset`:
#: takes a preset string, returns ``(ok: bool, reason: str)``.
PresetReloader = Callable[[str], tuple[bool, str]]


#: Type for the "what preset is currently loaded?" callable. The
#: orchestrator hands the router a closure that reads the engine's
#: own state (or the active ``ULTRON_LLM_PRESET`` env var).
PresetProbe = Callable[[], str]


class ModeLLMRouter:
    """Maps :class:`Mode` to LLM preset + drives hot-swaps.

    Args:
        reloader: callable that performs the actual preset swap. The
            real wiring uses
            :meth:`ultron.llm.inference.LLMEngine.reload_for_preset`;
            tests pass a fake that records calls.
        active_preset_probe: callable that returns the preset name
            currently loaded. Lets the router skip the swap when the
            target preset is already active.
        routes: optional mapping of :class:`Mode` to
            :class:`PresetEntry`. Missing entries fall back to
            :data:`DEFAULT_ROUTES`.
        on_swap: optional callback fired after every swap attempt
            (success or failure). Receives the :class:`SwapResult`.
            Errors raised by the callback are silently swallowed --
            the router refuses to crash the voice path over a
            telemetry failure.
        protected_modes: optional iterable of modes whose preset
            should NEVER be hot-swapped (kept on the active preset).
            Empty by default.
    """

    def __init__(
        self,
        *,
        reloader: PresetReloader,
        active_preset_probe: PresetProbe,
        routes: Optional[Mapping[Mode, PresetEntry]] = None,
        on_swap: Optional[Callable[[SwapResult], None]] = None,
        protected_modes: tuple[Mode, ...] = (),
    ) -> None:
        self._lock = threading.RLock()
        self._reloader = reloader
        self._probe = active_preset_probe
        self._routes: dict[Mode, PresetEntry] = dict(DEFAULT_ROUTES)
        if routes:
            self._routes.update(routes)
        self._on_swap = on_swap
        self._protected_modes = set(protected_modes)

    # ------------------------------------------------------------------
    # Route management
    # ------------------------------------------------------------------

    def get_preset(self, mode: Mode) -> PresetEntry:
        """Return the :class:`PresetEntry` for ``mode`` (default fallback)."""
        with self._lock:
            return self._routes.get(mode, DEFAULT_ROUTES.get(mode, DEFAULT_ROUTES[Mode.ACT]))

    def set_preset(self, mode: Mode, entry: PresetEntry) -> None:
        """Override the route for ``mode``."""
        with self._lock:
            self._routes[mode] = entry

    def routes(self) -> Mapping[Mode, PresetEntry]:
        """Snapshot the current route map."""
        with self._lock:
            return dict(self._routes)

    def mark_protected(self, mode: Mode) -> None:
        """Add ``mode`` to the protected set (no hot-swap for it)."""
        with self._lock:
            self._protected_modes.add(mode)

    def unmark_protected(self, mode: Mode) -> None:
        with self._lock:
            self._protected_modes.discard(mode)

    # ------------------------------------------------------------------
    # Swap driver
    # ------------------------------------------------------------------

    def ensure_preset_for(self, mode: Mode) -> SwapResult:
        """Make the engine's loaded preset match ``mode``'s route.

        Algorithm:

        1. Look up the :class:`PresetEntry` for ``mode``.
        2. Probe the engine's current preset.
        3. If protected or already-on-target: return a ``was_already_active=True`` SwapResult.
        4. Otherwise call ``reloader(target_preset)``.
        5. Fire ``on_swap`` (if set), swallowing any errors.

        Returns:
            A :class:`SwapResult` describing the outcome.
        """
        with self._lock:
            entry = self.get_preset(mode)
            target_preset = entry.preset_name
            if mode in self._protected_modes:
                result = SwapResult(
                    target_mode=mode,
                    target_preset=target_preset,
                    succeeded=True,
                    was_already_active=True,
                    failure_reason="",
                    sampling_overrides=dict(entry.sampling_overrides),
                    context_window_override=entry.context_window_override,
                )
                self._fire_on_swap(result)
                return result
            try:
                active = self._probe()
            except Exception as exc:  # noqa: BLE001 -- fail-open
                active = ""
                probe_failure = f"probe failed: {exc.__class__.__name__}"
            else:
                probe_failure = ""
            if active == target_preset:
                result = SwapResult(
                    target_mode=mode,
                    target_preset=target_preset,
                    succeeded=True,
                    was_already_active=True,
                    failure_reason="",
                    sampling_overrides=dict(entry.sampling_overrides),
                    context_window_override=entry.context_window_override,
                )
                self._fire_on_swap(result)
                return result
            try:
                ok, reason = self._reloader(target_preset)
            except Exception as exc:  # noqa: BLE001 -- fail-open
                ok = False
                reason = f"reloader raised: {exc.__class__.__name__}: {exc}"
            failure_reason = "" if ok else reason
            if not ok and probe_failure:
                failure_reason = f"{failure_reason}; {probe_failure}"
            result = SwapResult(
                target_mode=mode,
                target_preset=target_preset,
                succeeded=ok,
                was_already_active=False,
                failure_reason=failure_reason,
                sampling_overrides=dict(entry.sampling_overrides),
                context_window_override=entry.context_window_override,
            )
            self._fire_on_swap(result)
            return result

    def _fire_on_swap(self, result: SwapResult) -> None:
        if self._on_swap is None:
            return
        try:
            self._on_swap(result)
        except Exception:  # noqa: BLE001 -- fail-open
            pass


__all__ = [
    "DEFAULT_ROUTES",
    "ModeLLMRouter",
    "PresetEntry",
    "PresetProbe",
    "PresetReloader",
    "SwapResult",
]
