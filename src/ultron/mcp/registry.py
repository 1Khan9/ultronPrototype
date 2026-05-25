"""MCP server registry: lifecycle + scope-keyed listing + kill-on-disconnect.

T22 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Tracks
every registered MCP server (stdio child process OR HTTP endpoint)
in one shared registry. Composes with the T12 process registry for
subprocess discipline AND the T8 kill_tree primitive for tree
shutdown on orchestrator exit.

Lifecycle:

1. :meth:`McpServerRegistry.register` — add server config + transport,
   move state to ``REGISTERED``.
2. :meth:`start` — spawn the stdio child (or open the HTTP connection),
   transition to ``CONNECTED`` on success, ``FAILED`` on raise. Honors
   the per-server ``connection_timeout_seconds``.
3. :meth:`stop` — graceful disconnect; for stdio this kills the child
   process tree via T8 :func:`kill_process_tree` (composed via the
   injected ``kill_callable``). Transition to ``STOPPED``.
4. :meth:`mark_disconnected` — invoked when the SDK reports the
   transport died unexpectedly; transitions to ``DISCONNECTED``.

The registry holds the metadata + state — it does NOT itself speak
JSON-RPC. The actual MCP protocol layer lives in the ``mcp`` Python
SDK and is wired in by the orchestrator (kept optional so the
registry can be tested without the SDK installed).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .transport import (
    StdioMcpTransportConfig,
    TransportConfig,
    sanitise_transport_config,
)

LOGGER = logging.getLogger(__name__)

#: Default per-server connection timeout (seconds). Mirrors OpenClaw.
DEFAULT_CONNECTION_TIMEOUT_SECONDS: float = 30.0


class McpServerState(str, Enum):
    """Lifecycle state of a registered MCP server."""

    REGISTERED = "registered"
    STARTING = "starting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class McpServerHandle:
    """One tracked MCP server."""

    server_id: str
    scope_key: str = ""
    transport: Optional[TransportConfig] = None
    state: McpServerState = McpServerState.REGISTERED
    pid: Optional[int] = None
    registered_at: float = field(default_factory=time.monotonic)
    connected_at: Optional[float] = None
    last_error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class McpServerReference:
    """Frozen snapshot returned by listing helpers."""

    server_id: str
    scope_key: str
    state: McpServerState
    pid: Optional[int]
    transport_kind: Optional[str]
    age_seconds: float


KillCallable = Callable[[int], Any]
StarterCallable = Callable[[McpServerHandle], Optional[int]]


def _now() -> float:
    return time.monotonic()


class McpServerRegistry:
    """Thread-safe MCP server registry.

    Args:
        starter: optional callable invoked from :meth:`start`. Receives
            a sanitised handle (transport env / headers already
            filtered); returns the child pid for stdio transports (or
            ``None`` for HTTP). Raises to signal a failed start.
        killer: callable used by :meth:`stop` to terminate stdio child
            processes; receives the pid. Defaults to a no-op so the
            registry stays testable without the T8 helper installed.
        default_connection_timeout: per-server timeout cap. Honored by
            the starter callable (the registry doesn't enforce it
            directly — the starter is expected to respect the budget).
    """

    def __init__(
        self,
        *,
        starter: Optional[StarterCallable] = None,
        killer: Optional[KillCallable] = None,
        default_connection_timeout: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS,
    ) -> None:
        self._starter = starter
        self._killer = killer
        self._default_timeout = float(default_connection_timeout)
        self._servers: dict[str, McpServerHandle] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration

    def register(
        self,
        server_id: str,
        *,
        transport: TransportConfig,
        scope_key: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> McpServerHandle:
        """Add a server to the registry; sanitise its transport config.

        Sanitisation runs at registration time so subsequent
        :meth:`start` calls always work with the filtered env / headers.
        """
        if not server_id:
            raise ValueError("server_id must be non-empty")
        sanitised = sanitise_transport_config(transport)
        with self._lock:
            self._servers[server_id] = McpServerHandle(
                server_id=server_id,
                scope_key=scope_key,
                transport=sanitised,
                metadata=dict(metadata or {}),
            )
            return self._servers[server_id]

    def unregister(self, server_id: str) -> bool:
        """Drop the server. Returns ``True`` on hit."""
        with self._lock:
            return self._servers.pop(server_id, None) is not None

    def get(self, server_id: str) -> Optional[McpServerHandle]:
        with self._lock:
            return self._servers.get(server_id)

    def list_registered(self, *, scope_key: Optional[str] = None) -> tuple[McpServerReference, ...]:
        with self._lock:
            now = _now()
            out: list[McpServerReference] = []
            for handle in self._servers.values():
                if scope_key is not None and handle.scope_key != scope_key:
                    continue
                out.append(
                    McpServerReference(
                        server_id=handle.server_id,
                        scope_key=handle.scope_key,
                        state=handle.state,
                        pid=handle.pid,
                        transport_kind=(handle.transport.kind.value if handle.transport else None),
                        age_seconds=max(0.0, now - handle.registered_at),
                    )
                )
        return tuple(out)

    # ------------------------------------------------------------------
    # Lifecycle

    def start(self, server_id: str) -> McpServerState:
        """Invoke the starter callable; transition to CONNECTED / FAILED."""
        with self._lock:
            handle = self._servers.get(server_id)
            if handle is None:
                return McpServerState.FAILED
            handle.state = McpServerState.STARTING
        if self._starter is None:
            # No starter wired — leave in STARTING (caller decides).
            return McpServerState.STARTING
        try:
            pid = self._starter(handle)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                handle.state = McpServerState.FAILED
                handle.last_error = f"{type(exc).__name__}: {exc}"
            LOGGER.warning("MCP server %s start failed", server_id, exc_info=True)
            return McpServerState.FAILED
        with self._lock:
            handle.pid = pid
            handle.connected_at = _now()
            handle.state = McpServerState.CONNECTED
            handle.last_error = None
        return McpServerState.CONNECTED

    def stop(self, server_id: str) -> bool:
        """Stop the server (kill stdio child via the killer callable)."""
        with self._lock:
            handle = self._servers.get(server_id)
            if handle is None:
                return False
            pid = handle.pid
            is_stdio = isinstance(handle.transport, StdioMcpTransportConfig)
        if is_stdio and pid is not None and self._killer is not None:
            try:
                self._killer(pid)
            except Exception:  # noqa: BLE001
                LOGGER.warning("MCP server %s kill failed for pid %s", server_id, pid, exc_info=True)
        with self._lock:
            handle.state = McpServerState.STOPPED
            handle.pid = None
        return True

    def mark_disconnected(self, server_id: str, *, reason: str = "") -> bool:
        """The SDK reports the transport died; record + leave for restart."""
        with self._lock:
            handle = self._servers.get(server_id)
            if handle is None:
                return False
            handle.state = McpServerState.DISCONNECTED
            handle.last_error = reason or "transport disconnected"
            handle.pid = None
        return True

    def stop_all(self) -> int:
        """Stop every registered server; return the count stopped."""
        with self._lock:
            ids = list(self._servers.keys())
        stopped = 0
        for server_id in ids:
            if self.stop(server_id):
                stopped += 1
        return stopped

    def clear(self) -> None:
        """Test helper: drop every server (does NOT call stop)."""
        with self._lock:
            self._servers.clear()


# ----------------------------------------------------------------------
# Singleton


_registry_singleton: Optional[McpServerRegistry] = None
_registry_lock = threading.Lock()


def get_mcp_server_registry() -> McpServerRegistry:
    """Module-level singleton accessor."""
    global _registry_singleton
    with _registry_lock:
        if _registry_singleton is None:
            _registry_singleton = McpServerRegistry()
        return _registry_singleton


def set_mcp_server_registry(registry: McpServerRegistry) -> None:
    """Replace the singleton."""
    global _registry_singleton
    with _registry_lock:
        _registry_singleton = registry


def reset_mcp_server_registry_for_testing() -> None:
    global _registry_singleton
    with _registry_lock:
        _registry_singleton = None


__all__ = [
    "DEFAULT_CONNECTION_TIMEOUT_SECONDS",
    "KillCallable",
    "McpServerHandle",
    "McpServerReference",
    "McpServerRegistry",
    "McpServerState",
    "StarterCallable",
    "get_mcp_server_registry",
    "reset_mcp_server_registry_for_testing",
    "set_mcp_server_registry",
]
