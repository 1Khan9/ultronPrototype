"""Hook registry — discovery + parallel fan-out across lifecycle points.

The :class:`HookRegistry` is the high-level orchestrator interface:
``registry.fire(kind, payload)`` enumerates every script registered
for ``kind``, runs them concurrently via ``concurrent.futures``, and
returns a :class:`HookFanoutResult` aggregating cancel decisions +
concatenated context modifications.

Cancel semantics: ANY hook returning ``cancel: true`` causes the
fanout to mark the action cancelled. Every ``context_modification``
is concatenated (in source-layer + filename order) into the result's
combined block, even when one hook cancelled — the orchestrator
typically surfaces the combined context as an audit note before
aborting.
"""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .discovery import (
    DEFAULT_DISCOVERY_TTL_SECONDS,
    DEFAULT_HOOKS_SUBDIR,
    HookDiscovery,
    HookScript,
)
from .lifecycle import (
    DEFAULT_CONTEXT_MOD_CAP_CHARS,
    DEFAULT_HOOK_TIMEOUT_SECONDS,
    HookKind,
    HookOutcome,
    HookPayload,
)
from .runner import HookExecutionError, HookRunResult, HookRunner

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HookFanoutResult:
    """Aggregated outcome of firing every hook for one lifecycle point.

    Attributes:
        kind: lifecycle point that fired.
        cancelled: True when any hook returned ``cancel: true``.
        context_modification: combined ``context_modification`` blocks,
            wrapped as ``<hook_context source="<HookName>:<layer>">...</hook_context>``
            and joined with blank lines so the LLM sees each separately.
        per_hook_results: per-script :class:`HookRunResult` records
            (sorted by run order). Useful for audit logging.
        elapsed_seconds: wall-clock duration of the fanout (max of
            per-hook durations since we run in parallel).
        error_count: number of hooks that failed to parse / timed out /
            raised. The orchestrator may decide to surface these to the
            user or just log + continue.
    """

    kind: HookKind
    cancelled: bool
    context_modification: str
    per_hook_results: tuple[HookRunResult, ...]
    elapsed_seconds: float
    error_count: int


class HookRegistry:
    """Discovery + execution orchestrator for the hooks system.

    Args:
        directories: ordered ``(base_dir, layer_label)`` tuples passed
            through to :class:`HookDiscovery`.
        runner: optional :class:`HookRunner` (lets tests inject a
            mock). When omitted, a default runner is constructed
            with :data:`DEFAULT_HOOK_TIMEOUT_SECONDS` / cap.
        max_parallel: cap on concurrent hook executions for one
            lifecycle point (default 4). Beyond this the fanout
            serialises in batches.
        clock: optional monotonic clock (test hook).
    """

    def __init__(
        self,
        directories: Sequence[tuple[Path, str]],
        *,
        runner: Optional[HookRunner] = None,
        ttl_seconds: float = DEFAULT_DISCOVERY_TTL_SECONDS,
        max_parallel: int = 4,
        clock: Optional[object] = None,
    ) -> None:
        self._discovery = HookDiscovery(
            directories, ttl_seconds=ttl_seconds, clock=clock,
        )
        self._runner = runner or HookRunner()
        self._max_parallel = max(1, int(max_parallel))
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._fire_count: int = 0
        self._cancel_count: int = 0
        self._error_count: int = 0

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def fire(
        self, kind: HookKind, payload: HookPayload,
    ) -> HookFanoutResult:
        """Fire every script registered for ``kind`` and aggregate results.

        Args:
            kind: lifecycle point firing this fanout.
            payload: per-call :class:`HookPayload` (must match ``kind``).

        Returns:
            :class:`HookFanoutResult` aggregating cancel + context
            modifications. Always returns; never raises.
        """
        with self._lock:
            self._fire_count += 1
        scripts = self._discovery.discover_for(kind)
        if not scripts:
            return HookFanoutResult(
                kind=kind,
                cancelled=False,
                context_modification="",
                per_hook_results=(),
                elapsed_seconds=0.0,
                error_count=0,
            )
        start = self._clock()
        results: list[HookRunResult] = []
        # Parallel fan-out via a bounded thread pool.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self._max_parallel, len(scripts)),
            thread_name_prefix=f"hook-{kind.value}",
        ) as pool:
            futures = {
                pool.submit(self._run_one, script, payload): script
                for script in scripts
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)
        elapsed = self._clock() - start
        # Sort by script run order so the aggregated context is stable.
        order = {script.path: idx for idx, script in enumerate(scripts)}
        results.sort(key=lambda r: order.get(r.script.path, len(scripts)))
        cancelled = any(r.outcome.cancel for r in results)
        error_count = sum(
            1 for r in results
            if r.parse_error or r.timed_out or (r.exit_code not in (None, 0))
        )
        with self._lock:
            if cancelled:
                self._cancel_count += 1
            self._error_count += error_count
        combined = self._combine_context(kind, results)
        return HookFanoutResult(
            kind=kind,
            cancelled=cancelled,
            context_modification=combined,
            per_hook_results=tuple(results),
            elapsed_seconds=elapsed,
            error_count=error_count,
        )

    def invalidate_discovery(self) -> None:
        """Drop the discovery cache so the next fire re-scans."""
        self._discovery.invalidate()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "fire_count": self._fire_count,
                "cancel_count": self._cancel_count,
                "error_count": self._error_count,
            }

    def configured_directories(self) -> list[tuple[Path, str]]:
        return self._discovery.configured_directories()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_one(
        self, script: HookScript, payload: HookPayload,
    ) -> HookRunResult:
        try:
            return self._runner.run(script, payload)
        except HookExecutionError as exc:
            LOGGER.warning(
                "hook spawn failed for %s: %s", script.path, exc,
            )
            return HookRunResult(
                script=script,
                outcome=HookOutcome(
                    cancel=False,
                    context_modification="",
                    error_message=str(exc),
                ),
                elapsed_seconds=0.0,
                exit_code=None,
                stdout_preview="",
                stderr_preview="",
                timed_out=False,
                parse_error=f"spawn error: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 - never let a hook crash the orchestrator
            LOGGER.warning(
                "hook execution raised for %s", script.path, exc_info=True,
            )
            return HookRunResult(
                script=script,
                outcome=HookOutcome(
                    cancel=False,
                    context_modification="",
                    error_message=f"{type(exc).__name__}: {exc}",
                ),
                elapsed_seconds=0.0,
                exit_code=None,
                stdout_preview="",
                stderr_preview="",
                timed_out=False,
                parse_error=f"runner exception: {type(exc).__name__}",
            )

    @staticmethod
    def _combine_context(
        kind: HookKind, results: Sequence[HookRunResult],
    ) -> str:
        """Combine per-hook context_modification fields into one block."""
        parts: list[str] = []
        for result in results:
            body = result.outcome.context_modification.strip()
            if not body:
                continue
            label = (
                f'<hook_context source="{kind.value}" '
                f'script="{result.script.path.name}" '
                f'layer="{result.script.source_layer}">'
            )
            parts.append(f"{label}\n{body}\n</hook_context>")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY: Optional[HookRegistry] = None
_REGISTRY_LOCK = threading.RLock()


def get_hook_registry(
    *,
    workspace_root: Optional[Path] = None,
    extra_directories: Optional[Sequence[tuple[Path, str]]] = None,
    rebuild: bool = False,
) -> HookRegistry:
    """Return (and lazily construct) the module-level hook registry.

    Args:
        workspace_root: project root used to derive the project layer
            (``<workspace_root>/.ultron/hooks/``). None uses cwd.
        extra_directories: optional extra ``(dir, layer)`` tuples
            appended after the project layer.
        rebuild: when True, drop any existing registry and reconstruct
            with the supplied arguments.
    """
    global _DEFAULT_REGISTRY
    with _REGISTRY_LOCK:
        if _DEFAULT_REGISTRY is not None and not rebuild:
            return _DEFAULT_REGISTRY
        directories: list[tuple[Path, str]] = []
        global_dir = Path.home() / ".ultron" / DEFAULT_HOOKS_SUBDIR
        directories.append((global_dir, "global"))
        if workspace_root is not None:
            project_dir = Path(workspace_root) / ".ultron" / DEFAULT_HOOKS_SUBDIR
            directories.append((project_dir, "project"))
        if extra_directories:
            directories.extend(
                (Path(d), label) for d, label in extra_directories
            )
        _DEFAULT_REGISTRY = HookRegistry(directories)
        return _DEFAULT_REGISTRY


def reset_hook_registry_for_testing() -> None:
    """Drop the module-level registry (test-only)."""
    global _DEFAULT_REGISTRY
    with _REGISTRY_LOCK:
        _DEFAULT_REGISTRY = None


__all__ = [
    "HookFanoutResult",
    "HookRegistry",
    "get_hook_registry",
    "reset_hook_registry_for_testing",
]
