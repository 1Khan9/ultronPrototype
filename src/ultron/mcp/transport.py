"""MCP transport configuration + env / header sanitisation.

T22 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Defines
the four canonical MCP transport configurations (stdio / http / sse /
streamable_http) as frozen dataclasses, plus helpers for the
defensive env-var + HTTP-header filtering that should run before any
MCP child process is spawned.

Env filter: dangerous environment variables (``LD_PRELOAD``,
``DYLD_INSERT_LIBRARIES``, ``NODE_OPTIONS``, ``PYTHONPATH``,
``LD_LIBRARY_PATH``, ``DYLD_LIBRARY_PATH``, etc.) are dropped from
the child's environment by default. The MCP server config can
explicitly opt-in by listing them in ``allow_env`` — usually wrong
unless the server author has a documented reason.

HTTP header filter: ``Authorization``, ``Cookie``, ``Set-Cookie``
are dropped from the outbound header set by default; the MCP
server config opts in via ``allow_headers``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional


class McpTransportKind(str, Enum):
    """The four MCP transport variants OpenClaw + the SDK support."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


@dataclass(frozen=True)
class StdioMcpTransportConfig:
    """Stdio transport: spawn a child process and speak JSON-RPC over its pipes.

    Attributes:
        command: absolute path or PATH-resolvable command name.
        args: argv tail (the command's CLI args).
        cwd: optional working directory for the spawn. ``None`` = inherit.
        env: caller-supplied environment additions / overrides. Filtered
            through :func:`filter_environment` before reaching the child.
        allow_env: env-var names the caller explicitly opts into for
            inheritance from the parent environment (whitelist on top
            of the defaults-dropped list).
        connection_timeout_seconds: max wait for the initial handshake.
    """

    kind: McpTransportKind = field(default=McpTransportKind.STDIO, init=False)
    command: str = ""
    args: tuple[str, ...] = ()
    cwd: Optional[str] = None
    env: Mapping[str, str] = field(default_factory=dict)
    allow_env: tuple[str, ...] = ()
    connection_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class HttpMcpTransportConfig:
    """HTTP transport: speak JSON-RPC POST to a remote URL."""

    kind: McpTransportKind = field(default=McpTransportKind.HTTP, init=False)
    url: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    allow_headers: tuple[str, ...] = ()
    connection_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class SseMcpTransportConfig:
    """Server-Sent Events transport (long-lived stream + POST replies)."""

    kind: McpTransportKind = field(default=McpTransportKind.SSE, init=False)
    url: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    allow_headers: tuple[str, ...] = ()
    connection_timeout_seconds: float = 30.0


@dataclass(frozen=True)
class StreamableHttpMcpTransportConfig:
    """Streamable-HTTP transport (modern MCP-over-HTTP shape)."""

    kind: McpTransportKind = field(default=McpTransportKind.STREAMABLE_HTTP, init=False)
    url: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    allow_headers: tuple[str, ...] = ()
    connection_timeout_seconds: float = 30.0


TransportConfig = (
    StdioMcpTransportConfig
    | HttpMcpTransportConfig
    | SseMcpTransportConfig
    | StreamableHttpMcpTransportConfig
)


#: Env vars dropped from child processes by default (supply-chain
#: defence). Operators opt in via the per-server ``allow_env``.
DEFAULT_DROP_ENV_VARS: frozenset[str] = frozenset({
    # POSIX dynamic-linker hijacks.
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    # Node.js side-channel.
    "NODE_OPTIONS",
    "NODE_PATH",
    # Python import + site-customisation hijacks.
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONHOME",
    "PYTHONINSPECT",
    "PYTHONNOUSERSITE",
    "USERSITE",
    # Ruby / Perl import hijacks.
    "RUBYOPT",
    "RUBYLIB",
    "PERL5OPT",
    "PERL5LIB",
    # JVM agent attach.
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
})


#: HTTP headers dropped from outbound MCP requests by default.
DEFAULT_DROP_HTTP_HEADERS: frozenset[str] = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
})


def filter_environment(
    incoming: Mapping[str, str],
    *,
    allow: Iterable[str] = (),
    drop: Iterable[str] = DEFAULT_DROP_ENV_VARS,
) -> dict[str, str]:
    """Drop dangerous env vars from ``incoming`` unless allow-listed.

    The match is case-sensitive on POSIX, case-insensitive on Windows
    (where env var names are case-insensitive at the OS level).

    Args:
        incoming: original env-var map (often ``os.environ.copy()``).
        allow: caller-supplied whitelist (env var names that survive
            even if they appear in ``drop``).
        drop: env var names to drop. Defaults to
            :data:`DEFAULT_DROP_ENV_VARS`.

    Returns:
        New dict with the dropped vars removed.
    """
    is_windows = os.name == "nt"
    allow_set = {a.upper() if is_windows else a for a in allow}
    drop_set = {d.upper() if is_windows else d for d in drop}
    out: dict[str, str] = {}
    for key, value in incoming.items():
        match_key = key.upper() if is_windows else key
        if match_key in drop_set and match_key not in allow_set:
            continue
        out[key] = value
    return out


def filter_http_headers(
    incoming: Mapping[str, str],
    *,
    allow: Iterable[str] = (),
    drop: Iterable[str] = DEFAULT_DROP_HTTP_HEADERS,
) -> dict[str, str]:
    """Drop sensitive HTTP headers from ``incoming`` unless allow-listed.

    Header names are compared case-insensitively (HTTP semantics).
    """
    allow_set = {a.lower() for a in allow}
    drop_set = {d.lower() for d in drop}
    out: dict[str, str] = {}
    for name, value in incoming.items():
        lname = name.lower()
        if lname in drop_set and lname not in allow_set:
            continue
        out[name] = value
    return out


def sanitise_transport_config(
    config: TransportConfig,
    *,
    parent_env: Optional[Mapping[str, str]] = None,
) -> TransportConfig:
    """Return a copy of ``config`` with env / header sanitisation applied.

    For stdio configs, merges ``parent_env`` (default ``os.environ``)
    with the config's ``env`` and runs :func:`filter_environment`.
    For HTTP-family configs, applies :func:`filter_http_headers` to
    the header map.
    """
    if isinstance(config, StdioMcpTransportConfig):
        base = dict(parent_env) if parent_env is not None else dict(os.environ)
        merged = {**base, **dict(config.env)}
        filtered = filter_environment(merged, allow=config.allow_env)
        return StdioMcpTransportConfig(
            command=config.command,
            args=tuple(config.args),
            cwd=config.cwd,
            env=filtered,
            allow_env=tuple(config.allow_env),
            connection_timeout_seconds=config.connection_timeout_seconds,
        )
    if isinstance(config, HttpMcpTransportConfig):
        return HttpMcpTransportConfig(
            url=config.url,
            headers=filter_http_headers(config.headers, allow=config.allow_headers),
            allow_headers=tuple(config.allow_headers),
            connection_timeout_seconds=config.connection_timeout_seconds,
        )
    if isinstance(config, SseMcpTransportConfig):
        return SseMcpTransportConfig(
            url=config.url,
            headers=filter_http_headers(config.headers, allow=config.allow_headers),
            allow_headers=tuple(config.allow_headers),
            connection_timeout_seconds=config.connection_timeout_seconds,
        )
    if isinstance(config, StreamableHttpMcpTransportConfig):
        return StreamableHttpMcpTransportConfig(
            url=config.url,
            headers=filter_http_headers(config.headers, allow=config.allow_headers),
            allow_headers=tuple(config.allow_headers),
            connection_timeout_seconds=config.connection_timeout_seconds,
        )
    raise TypeError(f"unknown transport config type: {type(config).__name__}")


__all__ = [
    "DEFAULT_DROP_ENV_VARS",
    "DEFAULT_DROP_HTTP_HEADERS",
    "HttpMcpTransportConfig",
    "McpTransportKind",
    "SseMcpTransportConfig",
    "StdioMcpTransportConfig",
    "StreamableHttpMcpTransportConfig",
    "TransportConfig",
    "filter_environment",
    "filter_http_headers",
    "sanitise_transport_config",
]
