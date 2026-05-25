"""Hook-script discovery with mtime-validated caching.

Walks the configured directories (global + project) looking for files
named ``<HookKind>``, ``<HookKind>.py``, or ``<HookKind>.ps1``. The
discovery result is cached per directory with an mtime + TTL guard so
the per-turn ``discover`` call is constant-time when nothing has
changed.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .lifecycle import HookKind

LOGGER = logging.getLogger(__name__)

#: Default discovery cache TTL (seconds). Mirrors cline's 30 s.
DEFAULT_DISCOVERY_TTL_SECONDS: float = 30.0

#: Filename suffixes accepted as hook scripts.
_ACCEPTED_SUFFIXES: tuple[str, ...] = ("", ".py", ".ps1", ".sh", ".bat", ".cmd")

#: Default discovery directories (relative to each base path).
DEFAULT_HOOKS_SUBDIR: str = "hooks"


@dataclass(frozen=True)
class HookScript:
    """One discovered hook script.

    Attributes:
        kind: lifecycle point this script handles.
        path: resolved absolute path to the script.
        source_layer: ``"global"`` / ``"project"`` / caller-supplied label.
        suffix: file extension (`.py`, `.ps1`, etc.; empty for shebang).
    """

    kind: HookKind
    path: Path
    source_layer: str = "project"
    suffix: str = ""


@dataclass
class _DirEntry:
    """Internal per-directory cache record."""

    base_dir: Path
    layer: str
    cached_mtime_ns: int
    cached_at: float
    scripts: tuple[HookScript, ...]


class HookDiscovery:
    """Discover hook scripts under one or more base directories.

    Args:
        directories: ordered list of ``(base_dir, layer_label)`` tuples
            scanned in turn; the per-kind result keeps the LAST-found
            script (so project layers override global by appearing
            later in the list).
        ttl_seconds: TTL on the per-directory cache (default 30 s).
        clock: optional monotonic clock callable (test hook).
    """

    def __init__(
        self,
        directories: Sequence[tuple[Path, str]],
        *,
        ttl_seconds: float = DEFAULT_DISCOVERY_TTL_SECONDS,
        clock: Optional[object] = None,
    ) -> None:
        # Resolve directories once + remember the layer labels.
        self._directories: list[tuple[Path, str]] = [
            (Path(p).resolve(), label) for p, label in directories
        ]
        self._ttl = max(0.0, float(ttl_seconds))
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._entries: dict[Path, _DirEntry] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> dict[HookKind, list[HookScript]]:
        """Return the per-kind list of currently-discovered scripts.

        Multiple scripts per kind are allowed (one global + one project,
        or operator-supplied overlays). The list is in source-layer
        order so the registry can fire them deterministically.
        """
        with self._lock:
            per_kind: dict[HookKind, list[HookScript]] = {}
            for base_dir, layer in self._directories:
                entry = self._refresh_dir(base_dir, layer)
                if entry is None:
                    continue
                for script in entry.scripts:
                    per_kind.setdefault(script.kind, []).append(script)
            return per_kind

    def discover_for(self, kind: HookKind) -> list[HookScript]:
        """Return the discovered scripts for one specific ``kind``."""
        return self.discover().get(kind, [])

    def invalidate(self) -> None:
        """Drop every cached entry (forces fresh scan on next call)."""
        with self._lock:
            self._entries.clear()

    def configured_directories(self) -> list[tuple[Path, str]]:
        return list(self._directories)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_dir(self, base_dir: Path, layer: str) -> Optional[_DirEntry]:
        if not base_dir.is_dir():
            return None
        try:
            mtime = os.stat(base_dir).st_mtime_ns
        except OSError:
            return None
        now = self._clock()
        cached = self._entries.get(base_dir)
        if (
            cached is not None
            and cached.cached_mtime_ns == mtime
            and (now - cached.cached_at) <= self._ttl
        ):
            return cached
        scripts = self._scan(base_dir, layer)
        entry = _DirEntry(
            base_dir=base_dir,
            layer=layer,
            cached_mtime_ns=mtime,
            cached_at=now,
            scripts=scripts,
        )
        self._entries[base_dir] = entry
        return entry

    def _scan(self, base_dir: Path, layer: str) -> tuple[HookScript, ...]:
        scripts: list[HookScript] = []
        try:
            entries = list(base_dir.iterdir())
        except OSError:
            return ()
        for entry in sorted(entries, key=lambda p: p.name):
            if not entry.is_file():
                continue
            kind = self._match_kind(entry.name)
            if kind is None:
                continue
            scripts.append(
                HookScript(
                    kind=kind,
                    path=entry.resolve(),
                    source_layer=layer,
                    suffix=entry.suffix,
                )
            )
        return tuple(scripts)

    @staticmethod
    def _match_kind(filename: str) -> Optional[HookKind]:
        """Map a filename to a :class:`HookKind`."""
        # Files named exactly ``<HookKind><suffix>``.
        for suffix in _ACCEPTED_SUFFIXES:
            if not suffix:
                if filename in {kind.value for kind in HookKind}:
                    return HookKind(filename)
                continue
            if filename.endswith(suffix):
                stem = filename[: -len(suffix)]
                if stem in {kind.value for kind in HookKind}:
                    return HookKind(stem)
        return None


def discover_hook_scripts(
    directories: Sequence[tuple[Path, str]],
    *,
    ttl_seconds: float = DEFAULT_DISCOVERY_TTL_SECONDS,
) -> dict[HookKind, list[HookScript]]:
    """One-shot convenience wrapper around :class:`HookDiscovery`."""
    return HookDiscovery(directories, ttl_seconds=ttl_seconds).discover()


__all__ = [
    "DEFAULT_DISCOVERY_TTL_SECONDS",
    "DEFAULT_HOOKS_SUBDIR",
    "HookDiscovery",
    "HookScript",
    "discover_hook_scripts",
]
