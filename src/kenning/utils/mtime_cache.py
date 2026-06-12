"""mtime-keyed cache with SQLite primary + in-memory dict fallback.

Pattern lifted in spirit (not in source) from aider's ``repomap.py``
cache layer. The original is Apache 2.0; see ``THIRD_PARTY_NOTICES.md``.

The cache stores ``(mtime, value)`` tuples keyed by an arbitrary string
(typically an absolute file path). Reads validate that the stored
``mtime`` matches the live file's mtime — if not, the entry is treated
as a miss so callers re-compute against the current file content.

SQLite is the preferred backend (``diskcache.Cache``) because it shares
state across process restarts. When the SQLite cache cannot be opened
or fails mid-operation (corruption, locked file, filesystem hiccup), we
degrade to an in-memory ``dict`` for the lifetime of the process and
emit a single WARN. This mirrors how aider's repo map keeps working on
a flaky filesystem — the cache silently turns into a hot-only cache
rather than crashing the caller.

Public surface:

  * :class:`MtimeCache` — the cache wrapper itself.
  * :class:`MtimeCacheError` — emitted only on programmer error (e.g.
    constructing with a non-Path). Operational errors are caught
    internally and trigger fallback, never raised.

Typical use::

    cache = MtimeCache(Path("data/.cache/symbol_tags.v1"))
    entry = cache.get(str(path), path.stat().st_mtime)
    if entry is None:
        entry = expensive_compute(path)
        cache.set(str(path), path.stat().st_mtime, entry)

Thread safety: ``diskcache.Cache`` is process- and thread-safe on the
backend, and the dict fallback's reads/writes are atomic for single
key operations. Concurrent ``set`` of the same key from two threads is
last-writer-wins — acceptable because both writers would have computed
identical values for the same mtime.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


logger = logging.getLogger("kenning.utils.mtime_cache")


SQLITE_ERRORS: Tuple[type, ...] = (
    sqlite3.OperationalError,
    sqlite3.DatabaseError,
    OSError,
)


class MtimeCacheError(Exception):
    """Raised on programmer-level misuse (not operational issues)."""


class MtimeCache:
    """File-mtime-keyed cache with SQLite primary and dict fallback.

    Args:
        path: Directory to host the SQLite cache files. Created on first
            use. Pass an absolute path — relative paths interact poorly
            with chdir.
        version: Bump when the value shape changes. Cache directory is
            suffixed with ``.v{version}`` so old caches are ignored
            rather than misread. Defaults to 1.
        prefer_disk: When False, skip SQLite entirely and run in dict
            mode. Useful for tests.
    """

    def __init__(
        self,
        path: Path,
        *,
        version: int = 1,
        prefer_disk: bool = True,
    ) -> None:
        if not isinstance(path, Path):
            raise MtimeCacheError(
                f"path must be pathlib.Path, got {type(path).__name__}"
            )
        self._base_path = path
        self._versioned_path = path.with_name(f"{path.name}.v{version}")
        self._version = version
        self._dict_cache: Dict[str, Tuple[float, Any]] = {}
        self._sqlite_cache: Optional[Any] = None  # diskcache.Cache or None
        self._degraded = False
        if prefer_disk:
            self._try_open_sqlite()
        else:
            self._degraded = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def degraded(self) -> bool:
        """True when running on the in-memory dict fallback."""
        return self._degraded

    @property
    def path(self) -> Path:
        """The versioned cache directory (may not exist yet)."""
        return self._versioned_path

    def get(self, key: str, mtime: float) -> Optional[Any]:
        """Return the cached value when the stored mtime matches.

        Returns ``None`` on miss (no entry, mtime mismatch, or backend
        error during read).
        """
        try:
            entry = self._read(key)
        except SQLITE_ERRORS as exc:
            self._handle_backend_error(exc)
            entry = self._dict_cache.get(key)
        if entry is None:
            return None
        stored_mtime, value = entry
        if stored_mtime != mtime:
            return None
        return value

    def set(self, key: str, mtime: float, value: Any) -> None:
        """Store ``value`` under ``key`` with the given ``mtime``.

        On backend error, falls back to the dict cache and keeps going.
        """
        try:
            self._write(key, mtime, value)
        except SQLITE_ERRORS as exc:
            self._handle_backend_error(exc)
            self._dict_cache[key] = (mtime, value)

    def delete(self, key: str) -> None:
        """Remove ``key`` if present; silent no-op otherwise."""
        try:
            if self._sqlite_cache is not None:
                try:
                    del self._sqlite_cache[key]
                except KeyError:
                    pass
        except SQLITE_ERRORS as exc:
            self._handle_backend_error(exc)
        self._dict_cache.pop(key, None)

    def clear(self) -> None:
        """Drop every cached entry from both layers."""
        self._dict_cache.clear()
        if self._sqlite_cache is not None:
            try:
                self._sqlite_cache.clear()
            except SQLITE_ERRORS as exc:
                self._handle_backend_error(exc)

    def __len__(self) -> int:
        """Approximate entry count across both layers (no dedup)."""
        n = len(self._dict_cache)
        if self._sqlite_cache is not None:
            try:
                n += len(self._sqlite_cache)
            except SQLITE_ERRORS as exc:
                self._handle_backend_error(exc)
        return n

    def close(self) -> None:
        """Release the SQLite handle if held. Safe to call repeatedly."""
        cache = self._sqlite_cache
        self._sqlite_cache = None
        if cache is not None:
            try:
                cache.close()
            except SQLITE_ERRORS:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read(self, key: str) -> Optional[Tuple[float, Any]]:
        if self._sqlite_cache is not None:
            stored = self._sqlite_cache.get(key)
            if stored is not None:
                return stored
        return self._dict_cache.get(key)

    def _write(self, key: str, mtime: float, value: Any) -> None:
        payload: Tuple[float, Any] = (mtime, value)
        if self._sqlite_cache is not None:
            self._sqlite_cache[key] = payload
        # Keep a dict copy so reads stay hot even when the disk write
        # succeeded (avoids the second sqlite hit on the very next get).
        self._dict_cache[key] = payload

    def _try_open_sqlite(self) -> None:
        try:
            from diskcache import Cache  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "diskcache not installed; mtime_cache running in dict mode"
            )
            self._degraded = True
            return
        try:
            self._versioned_path.parent.mkdir(parents=True, exist_ok=True)
            cache = Cache(str(self._versioned_path))
            # Sanity-check the cache with a round-trip.
            probe = "__mtime_cache_probe__"
            cache[probe] = (0.0, None)
            _ = cache[probe]
            del cache[probe]
            self._sqlite_cache = cache
        except SQLITE_ERRORS as exc:
            logger.warning(
                "mtime_cache failed to open SQLite at %s: %s; "
                "falling back to in-memory dict",
                self._versioned_path,
                exc,
            )
            self._sqlite_cache = None
            self._degraded = True

    def _handle_backend_error(self, exc: BaseException) -> None:
        if self._degraded:
            return
        logger.warning(
            "mtime_cache SQLite error (%s); promoting to dict-only mode",
            exc,
        )
        self._degraded = True
        # Try to recreate the cache once. If recreation fails, stay in dict mode.
        old_cache = self._sqlite_cache
        self._sqlite_cache = None
        if old_cache is not None:
            try:
                old_cache.close()
            except SQLITE_ERRORS:
                pass
        try:
            shutil.rmtree(self._versioned_path, ignore_errors=True)
        except OSError:
            pass


def open_mtime_cache(
    path: Path,
    *,
    version: int = 1,
    prefer_disk: bool = True,
) -> MtimeCache:
    """Convenience constructor mirroring the open() name pattern."""
    return MtimeCache(path, version=version, prefer_disk=prefer_disk)
