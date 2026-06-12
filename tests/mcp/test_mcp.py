"""Tests for the T22 MCP transport + registry primitives."""

from __future__ import annotations

import pytest

from kenning.mcp import (
    DEFAULT_DROP_ENV_VARS,
    DEFAULT_DROP_HTTP_HEADERS,
    HttpMcpTransportConfig,
    McpServerRegistry,
    McpServerState,
    SseMcpTransportConfig,
    StdioMcpTransportConfig,
    StreamableHttpMcpTransportConfig,
    filter_environment,
    filter_http_headers,
    get_mcp_server_registry,
    reset_mcp_server_registry_for_testing,
    sanitise_transport_config,
    set_mcp_server_registry,
)
from kenning.mcp.transport import McpTransportKind


@pytest.fixture(autouse=True)
def _isolate_singleton() -> None:
    reset_mcp_server_registry_for_testing()
    yield
    reset_mcp_server_registry_for_testing()


# ----------------------------------------------------------------------
# Transport-kind discriminator


def test_stdio_config_carries_stdio_kind() -> None:
    cfg = StdioMcpTransportConfig(command="server")
    assert cfg.kind == McpTransportKind.STDIO


def test_http_config_carries_http_kind() -> None:
    cfg = HttpMcpTransportConfig(url="http://x")
    assert cfg.kind == McpTransportKind.HTTP


def test_sse_config_carries_sse_kind() -> None:
    cfg = SseMcpTransportConfig(url="http://x")
    assert cfg.kind == McpTransportKind.SSE


def test_streamable_http_config_carries_streamable_http_kind() -> None:
    cfg = StreamableHttpMcpTransportConfig(url="http://x")
    assert cfg.kind == McpTransportKind.STREAMABLE_HTTP


# ----------------------------------------------------------------------
# filter_environment


def test_filter_drops_ld_preload() -> None:
    env = {"LD_PRELOAD": "/evil.so", "PATH": "/usr/bin"}
    out = filter_environment(env)
    assert "LD_PRELOAD" not in out
    assert "PATH" in out


def test_filter_drops_node_options() -> None:
    env = {"NODE_OPTIONS": "--require=evil.js", "USER": "alice"}
    out = filter_environment(env)
    assert "NODE_OPTIONS" not in out
    assert "USER" in out


def test_filter_drops_pythonpath() -> None:
    env = {"PYTHONPATH": "/tmp/evil", "HOME": "/home/me"}
    out = filter_environment(env)
    assert "PYTHONPATH" not in out


def test_filter_allow_overrides_drop() -> None:
    env = {"LD_PRELOAD": "/legit.so"}
    out = filter_environment(env, allow=["LD_PRELOAD"])
    assert out["LD_PRELOAD"] == "/legit.so"


def test_filter_passes_safe_vars_through() -> None:
    env = {"USER": "alice", "HOME": "/home", "LANG": "en_US"}
    out = filter_environment(env)
    assert out == env


def test_filter_empty_input_returns_empty() -> None:
    assert filter_environment({}) == {}


def test_filter_custom_drop_set() -> None:
    env = {"FOO": "x", "BAR": "y"}
    out = filter_environment(env, drop=["FOO"])
    assert out == {"BAR": "y"}


def test_default_drop_includes_dynamic_loader_hijacks() -> None:
    for name in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS", "PYTHONPATH"):
        assert name in DEFAULT_DROP_ENV_VARS


# ----------------------------------------------------------------------
# filter_http_headers


def test_filter_drops_authorization_case_insensitive() -> None:
    headers = {"Authorization": "Bearer x", "Content-Type": "application/json"}
    out = filter_http_headers(headers)
    assert "Authorization" not in out
    assert "Content-Type" in out


def test_filter_drops_cookie() -> None:
    headers = {"Cookie": "session=abc", "X-Custom": "ok"}
    out = filter_http_headers(headers)
    assert "Cookie" not in out
    assert "X-Custom" in out


def test_filter_allow_overrides_header_drop() -> None:
    headers = {"Authorization": "Bearer x"}
    out = filter_http_headers(headers, allow=["Authorization"])
    assert out["Authorization"] == "Bearer x"


def test_filter_headers_empty_input() -> None:
    assert filter_http_headers({}) == {}


def test_default_drop_includes_known_credentials() -> None:
    for name in ("authorization", "cookie", "set-cookie", "proxy-authorization"):
        assert name in DEFAULT_DROP_HTTP_HEADERS


# ----------------------------------------------------------------------
# sanitise_transport_config


def test_sanitise_stdio_drops_dangerous_env() -> None:
    cfg = StdioMcpTransportConfig(
        command="server",
        env={"LD_PRELOAD": "/evil", "PATH": "/usr/bin"},
    )
    sanitised = sanitise_transport_config(cfg, parent_env={})
    assert "LD_PRELOAD" not in sanitised.env
    assert sanitised.env["PATH"] == "/usr/bin"


def test_sanitise_stdio_merges_parent_env_then_filters() -> None:
    parent = {"USER": "alice", "LD_PRELOAD": "/parent_evil"}
    cfg = StdioMcpTransportConfig(command="server")
    sanitised = sanitise_transport_config(cfg, parent_env=parent)
    assert "LD_PRELOAD" not in sanitised.env
    assert sanitised.env["USER"] == "alice"


def test_sanitise_http_drops_authorization() -> None:
    cfg = HttpMcpTransportConfig(url="http://x", headers={"Authorization": "x"})
    sanitised = sanitise_transport_config(cfg)
    assert "Authorization" not in sanitised.headers


def test_sanitise_http_with_allow_keeps_authorization() -> None:
    cfg = HttpMcpTransportConfig(
        url="http://x",
        headers={"Authorization": "Bearer x"},
        allow_headers=("Authorization",),
    )
    sanitised = sanitise_transport_config(cfg)
    assert "Authorization" in sanitised.headers


def test_sanitise_sse_filters_headers() -> None:
    cfg = SseMcpTransportConfig(url="http://x", headers={"Cookie": "session=1"})
    sanitised = sanitise_transport_config(cfg)
    assert "Cookie" not in sanitised.headers


def test_sanitise_streamable_http_filters_headers() -> None:
    cfg = StreamableHttpMcpTransportConfig(
        url="http://x", headers={"Cookie": "session=1"},
    )
    sanitised = sanitise_transport_config(cfg)
    assert "Cookie" not in sanitised.headers


def test_sanitise_unknown_type_raises() -> None:
    with pytest.raises(TypeError):
        sanitise_transport_config("not a config")


# ----------------------------------------------------------------------
# McpServerRegistry


def test_register_creates_handle() -> None:
    registry = McpServerRegistry()
    handle = registry.register(
        "srv-1",
        transport=StdioMcpTransportConfig(command="cmd"),
        scope_key="s1",
    )
    assert handle.server_id == "srv-1"
    assert handle.state == McpServerState.REGISTERED


def test_register_empty_server_id_rejected() -> None:
    registry = McpServerRegistry()
    with pytest.raises(ValueError):
        registry.register("", transport=StdioMcpTransportConfig(command="x"))


def test_register_sanitises_transport_at_registration_time() -> None:
    registry = McpServerRegistry()
    handle = registry.register(
        "srv",
        transport=StdioMcpTransportConfig(command="x", env={"LD_PRELOAD": "/evil"}),
    )
    assert "LD_PRELOAD" not in handle.transport.env


def test_get_returns_registered_handle() -> None:
    registry = McpServerRegistry()
    registry.register("s", transport=HttpMcpTransportConfig(url="http://x"))
    assert registry.get("s") is not None


def test_get_unknown_returns_none() -> None:
    assert McpServerRegistry().get("missing") is None


def test_unregister_drops_entry() -> None:
    registry = McpServerRegistry()
    registry.register("s", transport=HttpMcpTransportConfig(url="http://x"))
    assert registry.unregister("s") is True
    assert registry.get("s") is None


def test_list_registered_filters_by_scope() -> None:
    registry = McpServerRegistry()
    registry.register("a", transport=HttpMcpTransportConfig(url="http://a"), scope_key="alpha")
    registry.register("b", transport=HttpMcpTransportConfig(url="http://b"), scope_key="beta")
    out = registry.list_registered(scope_key="alpha")
    assert {ref.server_id for ref in out} == {"a"}


def test_start_invokes_starter_and_transitions_to_connected() -> None:
    registry = McpServerRegistry(starter=lambda h: 999)
    registry.register("s", transport=StdioMcpTransportConfig(command="x"))
    state = registry.start("s")
    assert state == McpServerState.CONNECTED
    assert registry.get("s").pid == 999


def test_start_unknown_id_returns_failed() -> None:
    registry = McpServerRegistry()
    assert registry.start("nope") == McpServerState.FAILED


def test_start_starter_exception_transitions_to_failed() -> None:
    def starter(_):
        raise RuntimeError("spawn failed")

    registry = McpServerRegistry(starter=starter)
    registry.register("s", transport=StdioMcpTransportConfig(command="x"))
    state = registry.start("s")
    assert state == McpServerState.FAILED
    assert "spawn failed" in registry.get("s").last_error


def test_start_no_starter_stays_in_starting() -> None:
    registry = McpServerRegistry()
    registry.register("s", transport=StdioMcpTransportConfig(command="x"))
    state = registry.start("s")
    assert state == McpServerState.STARTING


def test_stop_invokes_killer_for_stdio() -> None:
    kills: list[int] = []
    registry = McpServerRegistry(
        starter=lambda h: 555,
        killer=lambda pid: kills.append(pid),
    )
    registry.register("s", transport=StdioMcpTransportConfig(command="x"))
    registry.start("s")
    assert registry.stop("s") is True
    assert kills == [555]
    assert registry.get("s").state == McpServerState.STOPPED


def test_stop_http_does_not_invoke_killer() -> None:
    kills: list[int] = []
    registry = McpServerRegistry(
        starter=lambda h: None,
        killer=lambda pid: kills.append(pid),
    )
    registry.register("s", transport=HttpMcpTransportConfig(url="http://x"))
    registry.start("s")
    registry.stop("s")
    assert kills == []


def test_mark_disconnected_records_reason() -> None:
    registry = McpServerRegistry(starter=lambda h: 1)
    registry.register("s", transport=StdioMcpTransportConfig(command="x"))
    registry.start("s")
    registry.mark_disconnected("s", reason="EOF on stdin")
    handle = registry.get("s")
    assert handle.state == McpServerState.DISCONNECTED
    assert handle.last_error == "EOF on stdin"


def test_stop_all_stops_every_server() -> None:
    registry = McpServerRegistry(starter=lambda h: 1, killer=lambda pid: None)
    registry.register("a", transport=HttpMcpTransportConfig(url="http://a"))
    registry.register("b", transport=HttpMcpTransportConfig(url="http://b"))
    assert registry.stop_all() == 2


def test_clear_empties_registry() -> None:
    registry = McpServerRegistry()
    registry.register("a", transport=HttpMcpTransportConfig(url="http://a"))
    registry.clear()
    assert registry.list_registered() == ()


# ----------------------------------------------------------------------
# Singleton


def test_singleton_returns_same_instance() -> None:
    a = get_mcp_server_registry()
    b = get_mcp_server_registry()
    assert a is b


def test_set_singleton_replaces() -> None:
    custom = McpServerRegistry()
    set_mcp_server_registry(custom)
    assert get_mcp_server_registry() is custom
