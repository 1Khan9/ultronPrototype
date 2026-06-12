"""MCP (Model Context Protocol) transport + registry primitives (T22).

T22 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Closes
the T9 MCP-hub gap deferred from the cline catalog. Provides:

* :mod:`kenning.mcp.transport` — stdio + HTTP transport configuration
  dataclasses + env filtering + header filtering helpers.
* :mod:`kenning.mcp.registry` — :class:`McpServerRegistry` with
  start / stop / kill-on-disconnect, scope-keyed listing, per-server
  connection-timeout enforcement; composes with the T12 process
  registry + T8 kill_tree for cross-cutting subprocess discipline.

The transport layer is the data-shape only — the actual JSON-RPC
protocol logic lives in :mod:`mcp` (Python SDK) when callers install
it. Kenning's :class:`McpServerRegistry` calls into the SDK behind a
thin adapter so the SDK dep stays optional.

YELLOW gating: the MCP server INSTALL is gated by T5 (static
scanner) + T9 (marketplace integrity). MCP server RUNTIME is gated
by Cap-3 (process spawning) + T12 process-registry (track all MCP
children) + T8 kill_tree (shutdown) + env filtering (block dangerous
env vars by default) + per-server connection timeout.
"""

from __future__ import annotations

from .registry import (
    DEFAULT_CONNECTION_TIMEOUT_SECONDS,
    McpServerHandle,
    McpServerRegistry,
    McpServerState,
    get_mcp_server_registry,
    reset_mcp_server_registry_for_testing,
    set_mcp_server_registry,
)
from .transport import (
    DEFAULT_DROP_ENV_VARS,
    DEFAULT_DROP_HTTP_HEADERS,
    HttpMcpTransportConfig,
    McpTransportKind,
    SseMcpTransportConfig,
    StdioMcpTransportConfig,
    StreamableHttpMcpTransportConfig,
    filter_environment,
    filter_http_headers,
    sanitise_transport_config,
)

__all__ = [
    "DEFAULT_CONNECTION_TIMEOUT_SECONDS",
    "DEFAULT_DROP_ENV_VARS",
    "DEFAULT_DROP_HTTP_HEADERS",
    "HttpMcpTransportConfig",
    "McpServerHandle",
    "McpServerRegistry",
    "McpServerState",
    "McpTransportKind",
    "SseMcpTransportConfig",
    "StdioMcpTransportConfig",
    "StreamableHttpMcpTransportConfig",
    "filter_environment",
    "filter_http_headers",
    "get_mcp_server_registry",
    "reset_mcp_server_registry_for_testing",
    "sanitise_transport_config",
    "set_mcp_server_registry",
]
