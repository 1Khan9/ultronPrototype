"""Per-session JSON registry for inter-tool state.

Adapted from SWE-Agent's ``tools/registry/lib/registry.py:EnvRegistry``.
The pattern: every component participating in a single coding session
(the supervisor's decision layer, the architect narrator, the windowed-
file state machine, the submit-review loop, the autosubmission salvage
path) shares one JSON file on disk. This gives the participants a
common state-of-the-session view that survives subprocess restarts and
out-of-process tools.

Differences from SWE-Agent:

* **Per-session isolation.** SWE-Agent uses a single file at
  ``/root/.swe-agent-env``. Kenning may run multiple coding sessions
  in flight (or concurrent test sweeps); each gets its own file at
  ``data/coding/sessions/<session_id>/registry.json``.
* **Thread-safe writes.** A per-registry :class:`threading.RLock`
  guards reads + writes so the supervisor's dispatch thread and the
  architect narrator's daemon thread can share one registry safely.
* **Atomic transactions.** A :meth:`SessionRegistry.transaction`
  context manager batches writes so a multi-key update is either
  fully committed or not committed at all.
* **Optional TTL.** Per-key expiration via :meth:`set_with_ttl`. An
  expired key reads as missing without ever bleeding stale state
  into the next dispatch.
* **OS env fallback.** :meth:`get` mirrors SWE-Agent's
  ``fallback_to_env=True`` semantic: when the key is absent from JSON,
  consult :data:`os.environ` BEFORE returning the default. Lets the
  operator override any registry value via the launch environment
  without writing JSON.

The class is fail-open at every boundary: a corrupt JSON file logs a
WARN, resets to an empty dict, and lets the session continue rather
than crash the supervisor.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from kenning.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

#: Root directory under which per-session registry files live. Created
#: lazily on first write.
DEFAULT_REGISTRY_ROOT: Path = PROJECT_ROOT / "data" / "coding" / "sessions"

#: Sentinel value indicating "key absent" -- distinct from ``None``
#: which is a legitimate stored value.
_MISSING = object()


@dataclass
class _Entry:
    """Internal envelope for a stored value (supports per-key TTL)."""

    value: Any
    expires_at: Optional[float] = None  # epoch seconds; None = never expires


@dataclass
class SessionRegistryStats:
    """Diagnostic counters exposed via :meth:`SessionRegistry.stats`."""

    reads: int = 0
    writes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    env_fallback_hits: int = 0
    corrupt_file_recoveries: int = 0
    ttl_evictions: int = 0
    transactions: int = 0
    transaction_rollbacks: int = 0
    keys_at_last_load: int = 0
    last_payload_bytes: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class SessionRegistry:
    """A JSON-backed key-value store scoped to one coding session.

    Construct via :func:`get_session_registry` (preferred) to share
    one instance per session_id within a process. Direct construction
    is supported for tests + custom integrations.
    """

    def __init__(
        self,
        session_id: str,
        *,
        root: Optional[Path] = None,
        autosave: bool = True,
        fallback_to_env: bool = True,
    ) -> None:
        if not session_id or not str(session_id).strip():
            raise ValueError("session_id must be a non-empty string")
        self.session_id = str(session_id).strip()
        if root is None:
            root = DEFAULT_REGISTRY_ROOT
        self.root = Path(root)
        self.path = self.root / self.session_id / "registry.json"
        self.autosave = bool(autosave)
        self.fallback_to_env = bool(fallback_to_env)
        self._lock = threading.RLock()
        self._cache: dict[str, _Entry] = {}
        self._cache_loaded = False
        self._stats = SessionRegistryStats()
        self._in_transaction = False
        self._transaction_snapshot: Optional[dict[str, _Entry]] = None

    # ----- internal disk I/O ---------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._cache_loaded:
            return
        with self._lock:
            if self._cache_loaded:
                return
            self._cache = self._load_from_disk()
            self._cache_loaded = True

    def _load_from_disk(self) -> dict[str, _Entry]:
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "session-registry %s read failed: %s; resetting to empty",
                self.path,
                exc,
            )
            self._stats.corrupt_file_recoveries += 1
            return {}
        if not raw.strip():
            return {}
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "session-registry %s JSON parse failed: %s; resetting to empty",
                self.path,
                exc,
            )
            self._stats.corrupt_file_recoveries += 1
            return {}
        if not isinstance(blob, Mapping):
            logger.warning(
                "session-registry %s contained non-object payload; "
                "resetting to empty",
                self.path,
            )
            self._stats.corrupt_file_recoveries += 1
            return {}
        result: dict[str, _Entry] = {}
        for k, v in blob.items():
            if isinstance(v, Mapping) and "__kenning_registry_value__" in v:
                # Versioned envelope shape (carries TTL).
                result[str(k)] = _Entry(
                    value=v.get("value"),
                    expires_at=v.get("expires_at"),
                )
            else:
                # Bare-value shape (legacy / cross-tool compatible).
                result[str(k)] = _Entry(value=v, expires_at=None)
        self._stats.keys_at_last_load = len(result)
        self._stats.last_payload_bytes = len(raw.encode("utf-8"))
        return result

    def _serialise(self) -> str:
        payload: dict[str, Any] = {}
        for k, entry in self._cache.items():
            if entry.expires_at is None:
                payload[k] = entry.value
            else:
                payload[k] = {
                    "__kenning_registry_value__": True,
                    "value": entry.value,
                    "expires_at": entry.expires_at,
                }
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

    def _atomic_write(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "session-registry %s mkdir failed: %s; write skipped",
                self.path,
                exc,
            )
            return
        payload = self._serialise()
        try:
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix=".registry.",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            os.close(tmp_fd)
            tmp_path = Path(tmp_name)
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(str(tmp_path), str(self.path))
            self._stats.last_payload_bytes = len(payload.encode("utf-8"))
        except OSError as exc:
            logger.warning(
                "session-registry %s atomic write failed: %s; "
                "in-memory state preserved",
                self.path,
                exc,
            )

    def _evict_expired(self) -> None:
        if not self._cache:
            return
        now = time.time()
        expired: list[str] = []
        for k, entry in self._cache.items():
            if entry.expires_at is not None and entry.expires_at <= now:
                expired.append(k)
        for k in expired:
            self._cache.pop(k, None)
            self._stats.ttl_evictions += 1

    # ----- core dict-like surface ----------------------------------------

    def __getitem__(self, key: str) -> Any:
        self._ensure_loaded()
        with self._lock:
            self._evict_expired()
            self._stats.reads += 1
            if key in self._cache:
                self._stats.cache_hits += 1
                return self._cache[key].value
            self._stats.cache_misses += 1
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: object) -> bool:
        try:
            self.__getitem__(str(key))
        except KeyError:
            return False
        return True

    def __len__(self) -> int:
        self._ensure_loaded()
        with self._lock:
            self._evict_expired()
            return len(self._cache)

    def keys(self) -> list[str]:
        """Return a snapshot of current keys (sorted)."""
        self._ensure_loaded()
        with self._lock:
            self._evict_expired()
            return sorted(self._cache.keys())

    def get(
        self,
        key: str,
        default: Any = None,
        *,
        fallback_to_env: Optional[bool] = None,
    ) -> Any:
        """Safe lookup with the SWE-Agent fallback chain.

        Lookup order:

        1. The session JSON cache. Hit returns immediately.
        2. If ``fallback_to_env`` is True (default per constructor),
           ``os.environ[key]`` if the key is set there.
        3. The provided ``default``.

        Per SWE-Agent's behaviour, the env lookup happens AFTER the
        cache miss so a deliberately-stored ``None`` does NOT trigger
        env fallback.
        """
        self._ensure_loaded()
        with self._lock:
            self._evict_expired()
            self._stats.reads += 1
            if key in self._cache:
                self._stats.cache_hits += 1
                return self._cache[key].value
            self._stats.cache_misses += 1
            use_env = self.fallback_to_env if fallback_to_env is None else fallback_to_env
            if use_env and key in os.environ:
                self._stats.env_fallback_hits += 1
                return os.environ[key]
            return default

    def get_if_none(
        self,
        value: Any,
        key: str,
        default: Any = None,
        *,
        fallback_to_env: Optional[bool] = None,
    ) -> Any:
        """Return ``value`` if non-``None`` else :meth:`get(key, default)`.

        Direct port of SWE-Agent's ``registry.get_if_none`` -- collapses
        the common "if arg not passed, try registry, else default"
        pattern into one call. Useful in CLI scripts where an arg
        falls back to a registry value, which falls back to an env
        var, which falls back to a hardcoded default.
        """
        if value is not None:
            return value
        return self.get(key, default, fallback_to_env=fallback_to_env)

    def set(self, key: str, value: Any) -> None:
        """Persist ``value`` under ``key``. Autosaves to disk unless
        autosave is False or we're inside a :meth:`transaction`."""
        self._ensure_loaded()
        with self._lock:
            self._cache[key] = _Entry(value=value, expires_at=None)
            self._stats.writes += 1
            if self.autosave and not self._in_transaction:
                self._atomic_write()

    def set_with_ttl(self, key: str, value: Any, ttl_seconds: float) -> None:
        """Like :meth:`set` but the key expires ``ttl_seconds`` after
        the call. Reads after expiry return ``default``."""
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive (got {ttl_seconds})")
        self._ensure_loaded()
        with self._lock:
            self._cache[key] = _Entry(
                value=value,
                expires_at=time.time() + float(ttl_seconds),
            )
            self._stats.writes += 1
            if self.autosave and not self._in_transaction:
                self._atomic_write()

    def pop(self, key: str, default: Any = _MISSING) -> Any:
        """Remove ``key`` and return its value, or ``default`` if missing."""
        self._ensure_loaded()
        with self._lock:
            if key in self._cache:
                value = self._cache.pop(key).value
                self._stats.writes += 1
                if self.autosave and not self._in_transaction:
                    self._atomic_write()
                return value
            if default is _MISSING:
                raise KeyError(key)
            return default

    def clear(self) -> None:
        """Drop every key. Persists immediately unless inside a
        transaction or autosave is False."""
        self._ensure_loaded()
        with self._lock:
            self._cache.clear()
            self._stats.writes += 1
            if self.autosave and not self._in_transaction:
                self._atomic_write()

    def update(self, mapping: Mapping[str, Any]) -> None:
        """Bulk-set multiple keys in one atomic disk write."""
        if not mapping:
            return
        self._ensure_loaded()
        with self._lock:
            for k, v in mapping.items():
                self._cache[str(k)] = _Entry(value=v, expires_at=None)
                self._stats.writes += 1
            if self.autosave and not self._in_transaction:
                self._atomic_write()

    # ----- transaction support -------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator["SessionRegistry"]:
        """Group multiple writes into a single atomic disk commit.

        On the way in, snapshots the in-memory state. Writes inside the
        block update the cache but do NOT flush. On clean exit, one
        write commits everything. On exception, the snapshot is
        restored AND nothing is written -- the on-disk JSON is
        unchanged.
        """
        self._ensure_loaded()
        with self._lock:
            if self._in_transaction:
                # Nested transactions are flattened to the outermost.
                yield self
                return
            self._in_transaction = True
            self._transaction_snapshot = {
                k: _Entry(value=v.value, expires_at=v.expires_at)
                for k, v in self._cache.items()
            }
            self._stats.transactions += 1
            try:
                yield self
                if self.autosave:
                    self._atomic_write()
            except Exception:
                self._cache = self._transaction_snapshot or {}
                self._stats.transaction_rollbacks += 1
                raise
            finally:
                self._in_transaction = False
                self._transaction_snapshot = None

    # ----- diagnostics ----------------------------------------------------

    def stats(self) -> SessionRegistryStats:
        """Return a snapshot of the diagnostic counters."""
        with self._lock:
            return SessionRegistryStats(
                reads=self._stats.reads,
                writes=self._stats.writes,
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
                env_fallback_hits=self._stats.env_fallback_hits,
                corrupt_file_recoveries=self._stats.corrupt_file_recoveries,
                ttl_evictions=self._stats.ttl_evictions,
                transactions=self._stats.transactions,
                transaction_rollbacks=self._stats.transaction_rollbacks,
                keys_at_last_load=self._stats.keys_at_last_load,
                last_payload_bytes=self._stats.last_payload_bytes,
                extra=dict(self._stats.extra),
            )

    def reload(self) -> None:
        """Drop the in-memory cache and re-read from disk on next access.

        Useful when another process has updated the registry file.
        """
        with self._lock:
            self._cache.clear()
            self._cache_loaded = False

    def snapshot(self) -> dict[str, Any]:
        """Return a plain ``dict`` copy of every non-expired key.

        Mostly for tests + diagnostic logging. Does NOT include
        envelope metadata (TTL etc.).
        """
        self._ensure_loaded()
        with self._lock:
            self._evict_expired()
            return {k: e.value for k, e in self._cache.items()}


# ---------------------------------------------------------------------------
# Module-level registry of registries (one per session_id)
# ---------------------------------------------------------------------------

_REGISTRY_INSTANCES: dict[str, SessionRegistry] = {}
_REGISTRY_LOCK = threading.RLock()


def get_session_registry(
    session_id: str,
    *,
    root: Optional[Path] = None,
) -> SessionRegistry:
    """Return the canonical :class:`SessionRegistry` for ``session_id``.

    The first call for a given session_id constructs the instance;
    subsequent calls return the same one. Different ``root`` values
    will be respected only on the first call -- changes after the
    instance exists are ignored. Tests should call
    :func:`reset_session_registries_for_testing` between assertions.
    """
    if not session_id:
        raise ValueError("session_id must be non-empty")
    key = str(session_id)
    with _REGISTRY_LOCK:
        if key not in _REGISTRY_INSTANCES:
            _REGISTRY_INSTANCES[key] = SessionRegistry(
                session_id=key,
                root=root,
            )
        return _REGISTRY_INSTANCES[key]


def reset_session_registries_for_testing() -> None:
    """Forget every cached SessionRegistry instance.

    Call from test fixtures so the next :func:`get_session_registry`
    returns a fresh instance rooted at the test's ``tmp_path``.
    """
    with _REGISTRY_LOCK:
        _REGISTRY_INSTANCES.clear()


def new_session_id(prefix: str = "session") -> str:
    """Generate a stable session id (``prefix-<hex>``).

    Useful for ad-hoc tests + autonomous-run harnesses that need a
    fresh registry without an external session bookkeeper.
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


__all__ = [
    "DEFAULT_REGISTRY_ROOT",
    "SessionRegistry",
    "SessionRegistryStats",
    "get_session_registry",
    "new_session_id",
    "reset_session_registries_for_testing",
]
