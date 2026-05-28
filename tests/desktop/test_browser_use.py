"""Tests for the browser-use CLI wrapper (catalog 10 batch 1).

All subprocess.run calls are mocked via monkeypatch; no real
``browser-use`` binary is required to run these tests. No network
access. Per the binding rules in
``docs/test_sweep_binding_rules.md``:

* R1 -- every monkeypatch is via the fixture
* R4 -- no real network calls
* R7 -- order-independent
* R10 -- ~100 tests at <1 ms each, under budget
* R11 -- no voice-stack loading
* R12 -- no bare time.sleep
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Sequence
from unittest.mock import MagicMock

import pytest

from ultron.desktop import browser_use as bu


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@dataclass
class _SubprocessCall:
    """Capture of one subprocess.run invocation."""

    cmd: list[str]
    timeout: float
    env: dict[str, str]
    creationflags: int


class _FakeSubprocess:
    """Stand-in for :func:`subprocess.run` that records every call
    and yields scripted responses. Tests configure the next response
    by setting ``.returncode`` / ``.stdout`` / ``.stderr`` / ``.raises``.
    """

    def __init__(self) -> None:
        self.calls: list[_SubprocessCall] = []
        self.returncode: int = 0
        self.stdout: str = ""
        self.stderr: str = ""
        self.raises: BaseException | None = None
        self._responses: list[
            tuple[int, str, str]
        ] = []  # scripted (returncode, stdout, stderr) queue

    def queue_response(
        self, *, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> None:
        """Push a scripted response onto the queue; consumed FIFO."""
        self._responses.append((returncode, stdout, stderr))

    def __call__(
        self,
        cmd: Sequence[str],
        *,
        capture_output: bool,
        text: bool,
        encoding: str,
        errors: str,
        timeout: float,
        creationflags: int,
        env: dict[str, str],
        check: bool,
    ) -> Any:
        self.calls.append(
            _SubprocessCall(
                cmd=list(cmd),
                timeout=float(timeout),
                env=dict(env),
                creationflags=creationflags,
            )
        )
        if self.raises is not None:
            exc = self.raises
            self.raises = None  # one-shot
            raise exc
        if self._responses:
            rc, out, err = self._responses.pop(0)
        else:
            rc, out, err = self.returncode, self.stdout, self.stderr
        result = MagicMock()
        result.returncode = rc
        result.stdout = out
        result.stderr = err
        return result


@pytest.fixture
def fake_subprocess(monkeypatch: pytest.MonkeyPatch) -> _FakeSubprocess:
    """Replace subprocess.run inside the browser_use module + force
    the binary-discovery cache to a deterministic fake path."""
    fake = _FakeSubprocess()
    monkeypatch.setattr(bu.subprocess, "run", fake)
    # Force binary discovery to succeed against a fake path.
    monkeypatch.setattr(
        bu.shutil, "which", lambda name: f"/fake/bin/{name}"
    )
    return fake


@pytest.fixture
def tool(fake_subprocess: _FakeSubprocess) -> bu.BrowserUseTool:
    """Construct a fresh tool that will use the fake subprocess."""
    return bu.BrowserUseTool()


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Reset the module-level singleton before AND after every test
    so cross-test state cannot leak. Required for R7 order-independence."""
    bu.reset_browser_use_tool_for_testing()
    yield
    bu.reset_browser_use_tool_for_testing()


# ---------------------------------------------------------------------------
# Construction + binary discovery
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_construction_does_not_resolve_binary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[str] = []
        monkeypatch.setattr(
            bu.shutil,
            "which",
            lambda name: called.append(name) or f"/fake/{name}",
        )
        bu.BrowserUseTool()
        assert called == [], (
            "construction should not call shutil.which until first invoke"
        )

    def test_invalid_default_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="default_timeout_s"):
            bu.BrowserUseTool(default_timeout_s=0)

    def test_negative_default_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="default_timeout_s"):
            bu.BrowserUseTool(default_timeout_s=-1.0)

    def test_invalid_session_name_raises(self) -> None:
        with pytest.raises(ValueError, match="session name"):
            bu.BrowserUseTool(session="has spaces")

    def test_session_name_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            bu.BrowserUseTool(session="a" * 33)

    def test_session_name_valid_characters(self) -> None:
        # Should accept alphanumeric + underscore + hyphen, 1-32 chars.
        bu.BrowserUseTool(session="default")
        bu.BrowserUseTool(session="agent-1")
        bu.BrowserUseTool(session="agent_2")
        bu.BrowserUseTool(session="A" * 32)


class TestBinaryDiscovery:
    def test_resolve_binary_returns_first_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bu.shutil, "which", lambda name: f"/usr/bin/{name}")
        tool = bu.BrowserUseTool()
        assert tool.resolve_binary() == "/usr/bin/browser-use"

    def test_resolve_binary_tries_aliases(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def which(name: str) -> str | None:
            return f"/usr/bin/{name}" if name == "bu" else None

        monkeypatch.setattr(bu.shutil, "which", which)
        tool = bu.BrowserUseTool()
        assert tool.resolve_binary() == "/usr/bin/bu"

    def test_resolve_binary_returns_none_when_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bu.shutil, "which", lambda name: None)
        tool = bu.BrowserUseTool()
        assert tool.resolve_binary() is None
        assert tool.is_available() is False

    def test_resolve_binary_caches_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def which(name: str) -> str | None:
            nonlocal calls
            calls += 1
            return "/fake/bin"

        monkeypatch.setattr(bu.shutil, "which", which)
        tool = bu.BrowserUseTool()
        first = tool.resolve_binary()
        second = tool.resolve_binary()
        assert first == second == "/fake/bin"
        assert calls == 1, "second resolve should hit the cache"

    def test_reset_binary_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def which(name: str) -> str | None:
            nonlocal calls
            calls += 1
            return "/fake/bin"

        monkeypatch.setattr(bu.shutil, "which", which)
        tool = bu.BrowserUseTool()
        tool.resolve_binary()
        tool.reset_binary_cache()
        tool.resolve_binary()
        assert calls == 2

    def test_explicit_binary_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bu.shutil, "which", lambda name: f"/from-which/{name}")
        tool = bu.BrowserUseTool(binary_path="/custom/bu")
        # shutil.which sees the override first.
        assert tool.resolve_binary() == "/from-which//custom/bu"

    def test_missing_binary_returns_fail_open_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bu.shutil, "which", lambda name: None)
        tool = bu.BrowserUseTool()
        result = tool.state()
        assert result.success is False
        assert "not found" in (result.error or "")
        assert result.action == "state"


# ---------------------------------------------------------------------------
# Subprocess construction details
# ---------------------------------------------------------------------------


class TestSubprocessInvocation:
    def test_session_flag_inserted_before_subcommand(
        self, fake_subprocess: _FakeSubprocess
    ) -> None:
        tool = bu.BrowserUseTool(session="agent-1")
        tool.state()
        cmd = fake_subprocess.calls[0].cmd
        # Binary, --session, agent-1, then subcommand.
        assert cmd[1] == "--session"
        assert cmd[2] == "agent-1"
        assert cmd[3] == "state"

    def test_no_session_flag_when_unset(
        self, fake_subprocess: _FakeSubprocess
    ) -> None:
        tool = bu.BrowserUseTool()
        tool.state()
        cmd = fake_subprocess.calls[0].cmd
        assert "--session" not in cmd

    def test_create_no_window_set_on_windows(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.state()
        creationflags = fake_subprocess.calls[0].creationflags
        if sys.platform == "win32":
            assert creationflags == 0x08000000
        else:
            assert creationflags == 0

    def test_env_scrub_removes_browser_use_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_subprocess: _FakeSubprocess,
        tool: bu.BrowserUseTool,
    ) -> None:
        monkeypatch.setenv("BROWSER_USE_SESSION", "leaked-session")
        monkeypatch.setenv("OTHER_VAR", "kept")
        tool.state()
        env = fake_subprocess.calls[0].env
        assert "BROWSER_USE_SESSION" not in env
        assert env.get("OTHER_VAR") == "kept"

    def test_env_overrides_cannot_reintroduce_scrubbed_var(
        self,
        fake_subprocess: _FakeSubprocess,
    ) -> None:
        tool = bu.BrowserUseTool(
            env_overrides={"BROWSER_USE_SESSION": "should-not-appear"}
        )
        tool.state()
        env = fake_subprocess.calls[0].env
        assert "BROWSER_USE_SESSION" not in env

    def test_env_overrides_are_applied(
        self, fake_subprocess: _FakeSubprocess
    ) -> None:
        tool = bu.BrowserUseTool(env_overrides={"HTTP_PROXY": "http://proxy"})
        tool.state()
        env = fake_subprocess.calls[0].env
        assert env.get("HTTP_PROXY") == "http://proxy"

    def test_default_timeout_applied(
        self, fake_subprocess: _FakeSubprocess
    ) -> None:
        tool = bu.BrowserUseTool(default_timeout_s=12.0)
        tool.state()
        assert fake_subprocess.calls[0].timeout == 12.0

    def test_per_call_timeout_override(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.open("https://example.com", timeout_s=5.0)
        assert fake_subprocess.calls[0].timeout == 5.0

    def test_non_zero_exit_returns_failure(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.returncode = 2
        fake_subprocess.stderr = "browser not running"
        result = tool.state()
        assert result.success is False
        assert result.exit_code == 2
        assert "browser not running" in (result.error or "")

    def test_subprocess_timeout_returns_failure(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.raises = subprocess.TimeoutExpired(
            cmd=["browser-use"], timeout=1.0
        )
        result = tool.state()
        assert result.success is False
        assert "timeout" in (result.error or "").lower()

    def test_subprocess_spawn_error_returns_failure(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.raises = FileNotFoundError("missing")
        result = tool.state()
        assert result.success is False
        assert "spawn failed" in (result.error or "")

    def test_os_error_returns_failure(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.raises = OSError("broken pipe")
        result = tool.state()
        assert result.success is False
        assert "os error" in (result.error or "")

    def test_large_stdout_truncated(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        # 1 MB of output -> truncated to 256 KB with elision marker.
        fake_subprocess.stdout = "x" * (1024 * 1024)
        result = tool.get_html()
        assert "bytes elided" in result.stdout
        assert len(result.stdout) < 300_000


# ---------------------------------------------------------------------------
# T1 -- state enumeration
# ---------------------------------------------------------------------------


class TestState:
    def test_state_passes_json_flag(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.state()
        assert "--json" in fake_subprocess.calls[0].cmd

    def test_state_parses_canonical_json(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {
                "url": "https://example.com/page",
                "title": "Example Page",
                "elements": [
                    {
                        "index": 0,
                        "label": "Sign in",
                        "type": "button",
                        "enabled": True,
                    },
                    {
                        "index": 1,
                        "label": "Search",
                        "type": "input",
                        "enabled": True,
                    },
                ],
            }
        )
        result = tool.state()
        assert result.success is True
        assert result.url == "https://example.com/page"
        assert result.title == "Example Page"
        assert len(result.elements) == 2
        assert result.elements[0].index == 0
        assert result.elements[0].label == "Sign in"
        assert result.elements[0].type == "button"

    def test_state_tolerates_alternative_key_names(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {
                "url": "https://x.com",
                "title": "t",
                "interactive_elements": [
                    {"index": 0, "text": "Click", "role": "button"}
                ],
            }
        )
        result = tool.state()
        assert len(result.elements) == 1
        assert result.elements[0].label == "Click"
        assert result.elements[0].type == "button"

    def test_state_handles_json_parse_failure_softly(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "not json"
        result = tool.state()
        # Still ``success=True`` because the CLI itself succeeded.
        assert result.success is True
        assert result.elements == ()
        assert "parse" in (result.error or "").lower()

    def test_state_failure_propagates_when_cli_fails(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.returncode = 1
        result = tool.state()
        assert result.success is False
        assert result.elements == ()


# ---------------------------------------------------------------------------
# T2 -- DOM-native extraction
# ---------------------------------------------------------------------------


class TestGetHtml:
    def test_no_selector(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "<html><body>hi</body></html>"
        result = tool.get_html()
        assert result.success is True
        assert result.html == "<html><body>hi</body></html>"
        assert "--selector" not in fake_subprocess.calls[0].cmd

    def test_with_selector(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "<h1>Title</h1>"
        result = tool.get_html(selector="h1")
        cmd = fake_subprocess.calls[0].cmd
        assert "--selector" in cmd
        assert "h1" in cmd
        assert result.selector == "h1"

    def test_empty_selector_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.get_html(selector="   ")
        assert result.success is False
        assert "empty selector" in (result.error or "")
        # And subprocess should not be called.
        assert fake_subprocess.calls == []


class TestGetText:
    def test_basic(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "Sign in\n"
        result = tool.get_text(0)
        assert result.success is True
        assert result.text == "Sign in"
        assert result.index == 0
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-3:] == ["get", "text", "0"]

    def test_negative_index_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.get_text(-1)
        assert result.success is False
        assert "non-negative" in (result.error or "")
        assert fake_subprocess.calls == []


class TestGetValue:
    def test_basic(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "user@example.com"
        result = tool.get_value(3)
        assert result.success is True
        assert result.value == "user@example.com"
        assert result.index == 3

    def test_negative_index_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.get_value(-5)
        assert result.success is False


class TestGetAttributes:
    def test_parses_json_mapping(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {"id": "btn1", "class": "primary", "type": "submit"}
        )
        result = tool.get_attributes(2)
        assert result.success is True
        assert result.attributes == {
            "id": "btn1",
            "class": "primary",
            "type": "submit",
        }

    def test_non_mapping_payload_falls_back_to_raw(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(["not", "a", "mapping"])
        result = tool.get_attributes(2)
        assert "__raw__" in result.attributes
        assert "non-mapping" in (result.error or "")

    def test_parse_failure_falls_back_to_raw(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "not json at all"
        result = tool.get_attributes(2)
        assert "__raw__" in result.attributes
        assert "parse failed" in (result.error or "").lower()


class TestGetBbox:
    def test_canonical_shape(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {"x": 100, "y": 200, "width": 50, "height": 30}
        )
        result = tool.get_bbox(0)
        assert result.success is True
        assert result.bbox is not None
        assert result.bbox.x == 100
        assert result.bbox.y == 200
        assert result.bbox.width == 50
        assert result.bbox.height == 30
        assert result.bbox.center_x == 125
        assert result.bbox.center_y == 215
        assert result.bbox.center == (125, 215)

    def test_left_top_shape(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {"left": 10, "top": 20, "width": 40, "height": 80}
        )
        result = tool.get_bbox(0)
        assert result.bbox is not None
        assert result.bbox.x == 10
        assert result.bbox.y == 20

    def test_short_w_h_shape(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {"x": 5, "y": 5, "w": 100, "h": 50}
        )
        result = tool.get_bbox(0)
        assert result.bbox is not None
        assert result.bbox.width == 100

    def test_negative_dimensions_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {"x": 0, "y": 0, "width": -1, "height": 50}
        )
        result = tool.get_bbox(0)
        assert result.success is False
        assert "negative" in (result.error or "")

    def test_malformed_payload(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "garbage"
        result = tool.get_bbox(0)
        assert result.success is False
        assert "parse" in (result.error or "").lower()


class TestGetTitle:
    def test_basic(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "Page Title\n"
        result = tool.get_title()
        assert result.success is True
        assert result.title == "Page Title"


# ---------------------------------------------------------------------------
# T5 -- wait barriers
# ---------------------------------------------------------------------------


class TestWaitSelector:
    def test_canonical(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_selector(".content", timeout_ms=10_000)
        cmd = fake_subprocess.calls[0].cmd
        assert "wait" in cmd
        assert "selector" in cmd
        assert ".content" in cmd
        assert "--state" in cmd
        assert "visible" in cmd
        assert "--timeout" in cmd
        assert "10000" in cmd
        assert result.matched is True
        assert result.target == ".content"

    def test_default_state_visible(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_selector(".x")
        assert result.state == "visible"

    def test_all_states_accepted(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        for state in bu.WAIT_SELECTOR_STATES:
            r = tool.wait_selector(".x", state=state)
            assert r.success is True

    def test_invalid_state_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_selector(".x", state="exploded")
        assert result.success is False
        assert "state must" in (result.error or "")
        assert fake_subprocess.calls == []

    def test_empty_selector_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_selector("   ")
        assert result.success is False
        assert "empty selector" in (result.error or "")

    def test_subprocess_timeout_exceeds_wait_timeout(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.wait_selector(".x", timeout_ms=10_000)
        # 10s wait -> subprocess timeout >= 15s (wait + 5s margin).
        assert fake_subprocess.calls[0].timeout >= 15.0

    def test_negative_timeout_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_selector(".x", timeout_ms=-1)
        assert result.success is False
        assert "positive" in (result.error or "")

    def test_wait_failure_returns_unmatched(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.returncode = 1
        fake_subprocess.stderr = "Timeout 5000ms exceeded"
        result = tool.wait_selector(".missing")
        assert result.success is False
        assert result.matched is False


class TestWaitText:
    def test_canonical(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_text("Welcome")
        cmd = fake_subprocess.calls[0].cmd
        assert "wait" in cmd
        assert "text" in cmd
        assert "Welcome" in cmd
        assert result.matched is True
        assert result.target == "Welcome"
        assert result.state == "text"

    def test_empty_text_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.wait_text("")
        assert result.success is False
        assert fake_subprocess.calls == []


# ---------------------------------------------------------------------------
# T6 -- tab lifecycle
# ---------------------------------------------------------------------------


class TestTabList:
    def test_parses_canonical_list(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            [
                {
                    "index": 0,
                    "url": "https://a.com",
                    "title": "A",
                    "active": True,
                },
                {
                    "index": 1,
                    "url": "https://b.com",
                    "title": "B",
                    "active": False,
                },
            ]
        )
        result = tool.tab_list()
        assert result.success is True
        assert len(result.tabs) == 2
        assert result.tabs[0].active is True
        assert result.tabs[1].title == "B"

    def test_parses_tabs_under_mapping(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = json.dumps(
            {"tabs": [{"index": 0, "url": "https://a.com"}]}
        )
        result = tool.tab_list()
        assert len(result.tabs) == 1
        assert result.tabs[0].url == "https://a.com"
        assert result.tabs[0].active is False  # missing key -> False

    def test_parse_failure(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        fake_subprocess.stdout = "no json"
        result = tool.tab_list()
        assert result.tabs == ()
        assert "parse" in (result.error or "").lower()


class TestTabNew:
    def test_blank(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.tab_new()
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-2:] == ["tab", "new"]

    def test_with_url(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.tab_new("https://example.com")
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-3:] == ["tab", "new", "https://example.com"]

    def test_empty_url_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.tab_new("   ")
        assert result.success is False
        assert fake_subprocess.calls == []


class TestTabSwitch:
    def test_basic(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.tab_switch(2)
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-3:] == ["tab", "switch", "2"]

    def test_negative_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.tab_switch(-1)
        assert result.success is False


class TestTabClose:
    def test_single_index(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.tab_close([1])
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-3:] == ["tab", "close", "1"]

    def test_multiple_indices(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.tab_close([1, 3, 5])
        cmd = fake_subprocess.calls[0].cmd
        # Last 5 args: tab, close, 1, 3, 5
        assert cmd[-5:] == ["tab", "close", "1", "3", "5"]

    def test_empty_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.tab_close([])
        assert result.success is False

    def test_negative_in_list_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.tab_close([1, -2, 3])
        assert result.success is False


# ---------------------------------------------------------------------------
# Navigation + lifecycle helpers
# ---------------------------------------------------------------------------


class TestOpenAndClose:
    def test_open_url(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.open("https://example.com")
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-2:] == ["open", "https://example.com"]

    def test_open_headed_appends_flag(
        self, fake_subprocess: _FakeSubprocess
    ) -> None:
        tool = bu.BrowserUseTool(headed=True)
        tool.open("https://example.com")
        cmd = fake_subprocess.calls[0].cmd
        # Flag comes BEFORE the subcommand.
        assert "--headed" in cmd
        headed_idx = cmd.index("--headed")
        open_idx = cmd.index("open")
        assert headed_idx < open_idx

    def test_open_empty_url_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.open("")
        assert result.success is False
        assert fake_subprocess.calls == []

    def test_back(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.back()
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-1] == "back"

    def test_close(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.close()
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-1] == "close"
        assert "--all" not in cmd

    def test_close_all(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.close(all_sessions=True)
        cmd = fake_subprocess.calls[0].cmd
        assert "--all" in cmd


class TestScroll:
    def test_down(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.scroll("down")
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-2:] == ["scroll", "down"]

    def test_up(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.scroll("up")
        cmd = fake_subprocess.calls[0].cmd
        assert cmd[-2:] == ["scroll", "up"]

    def test_with_amount(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        tool.scroll("down", amount=500)
        cmd = fake_subprocess.calls[0].cmd
        assert "--amount" in cmd
        assert "500" in cmd

    def test_invalid_direction_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.scroll("diagonal")
        assert result.success is False
        assert fake_subprocess.calls == []

    def test_negative_amount_rejected(
        self, fake_subprocess: _FakeSubprocess, tool: bu.BrowserUseTool
    ) -> None:
        result = tool.scroll("down", amount=-1)
        assert result.success is False


# ---------------------------------------------------------------------------
# Singleton + with_session
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_set_get_round_trip(self) -> None:
        tool = bu.BrowserUseTool()
        bu.set_browser_use_tool(tool)
        assert bu.get_browser_use_tool() is tool

    def test_unset_returns_none(self) -> None:
        assert bu.get_browser_use_tool() is None
        bu.set_browser_use_tool(bu.BrowserUseTool())
        bu.reset_browser_use_tool_for_testing()
        assert bu.get_browser_use_tool() is None


class TestWithSession:
    def test_returns_new_instance(self) -> None:
        a = bu.BrowserUseTool()
        b = a.with_session("agent-1")
        assert a is not b
        assert a.session is None
        assert b.session == "agent-1"

    def test_invalid_name_raises(self) -> None:
        a = bu.BrowserUseTool()
        with pytest.raises(ValueError):
            a.with_session("has spaces")

    def test_unset_via_none(self) -> None:
        a = bu.BrowserUseTool(session="x")
        b = a.with_session(None)
        assert b.session is None


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


class TestSessionNameValidator:
    def test_alphanumeric_ok(self) -> None:
        assert bu._is_valid_session_name("default")
        assert bu._is_valid_session_name("Agent42")

    def test_with_underscore_and_hyphen(self) -> None:
        assert bu._is_valid_session_name("agent_1-test")

    def test_too_long(self) -> None:
        assert not bu._is_valid_session_name("a" * 33)

    def test_empty(self) -> None:
        assert not bu._is_valid_session_name("")

    def test_invalid_chars(self) -> None:
        assert not bu._is_valid_session_name("a/b")
        assert not bu._is_valid_session_name("a b")
        assert not bu._is_valid_session_name("a.b")


class TestEnvScrub:
    def test_drops_scrub_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BROWSER_USE_SESSION", "leaked")
        env = bu._build_scrubbed_env({})
        assert "BROWSER_USE_SESSION" not in env

    def test_keeps_other_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KEEP_ME", "yes")
        env = bu._build_scrubbed_env({})
        assert env.get("KEEP_ME") == "yes"

    def test_overrides_layer_on_top(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("X", "old")
        env = bu._build_scrubbed_env({"X": "new"})
        assert env["X"] == "new"

    def test_overrides_cannot_reintroduce_scrub_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = bu._build_scrubbed_env({"BROWSER_USE_SESSION": "smuggled"})
        assert "BROWSER_USE_SESSION" not in env


class TestTruncate:
    def test_small_payload_unchanged(self) -> None:
        assert bu._truncate("hello") == "hello"

    def test_empty_string(self) -> None:
        assert bu._truncate("") == ""

    def test_large_payload_truncated(self) -> None:
        text = "x" * (1024 * 1024)
        result = bu._truncate(text)
        assert "bytes elided" in result
        assert len(result.encode("utf-8")) < 300_000


class TestExtractCliError:
    def test_prefers_stderr(self) -> None:
        assert bu._extract_cli_error("oops\n", "stdout") == "oops"

    def test_falls_back_to_stdout(self) -> None:
        assert bu._extract_cli_error("", "from stdout") == "from stdout"

    def test_strips_whitespace_and_caps(self) -> None:
        long_line = "e" * 1000
        out = bu._extract_cli_error(long_line, "")
        assert out is not None
        assert len(out) <= 512

    def test_returns_none_when_both_blank(self) -> None:
        assert bu._extract_cli_error("   ", "  \n") is None


class TestParseStateJson:
    def test_canonical(self) -> None:
        payload = json.dumps(
            {
                "url": "https://x.com",
                "title": "X",
                "elements": [
                    {"index": 0, "label": "a", "type": "button"}
                ],
            }
        )
        result = bu._try_parse_state_json(payload)
        assert result is not None
        assert result["url"] == "https://x.com"
        assert result["elements"][0].index == 0

    def test_returns_none_on_garbage(self) -> None:
        assert bu._try_parse_state_json("not json") is None

    def test_returns_none_on_array(self) -> None:
        # The top-level must be a mapping.
        assert bu._try_parse_state_json("[]") is None

    def test_returns_none_on_empty(self) -> None:
        assert bu._try_parse_state_json("") is None


class TestParseBbox:
    def test_canonical(self) -> None:
        bbox, err = bu._try_parse_bbox(
            json.dumps({"x": 10, "y": 20, "width": 30, "height": 40})
        )
        assert bbox is not None
        assert err is None
        assert bbox.x == 10

    def test_empty(self) -> None:
        bbox, err = bu._try_parse_bbox("")
        assert bbox is None
        assert err is not None

    def test_invalid_types(self) -> None:
        bbox, err = bu._try_parse_bbox(
            json.dumps({"x": "abc", "y": 0, "width": 10, "height": 10})
        )
        assert bbox is None
        assert err is not None


class TestParseTabs:
    def test_list_shape(self) -> None:
        tabs, err = bu._try_parse_tabs(
            json.dumps([{"index": 0, "url": "https://x.com"}])
        )
        assert err is None
        assert len(tabs) == 1
        assert tabs[0].url == "https://x.com"

    def test_mapping_shape(self) -> None:
        tabs, err = bu._try_parse_tabs(
            json.dumps({"tabs": [{"index": 0, "url": "https://x.com"}]})
        )
        assert err is None
        assert len(tabs) == 1

    def test_missing_tabs_key(self) -> None:
        tabs, err = bu._try_parse_tabs(json.dumps({"other": []}))
        assert tabs == ()
        assert err is not None

    def test_empty_string(self) -> None:
        tabs, err = bu._try_parse_tabs("")
        assert tabs == ()
        assert err is not None

    def test_garbage_json(self) -> None:
        tabs, err = bu._try_parse_tabs("nope")
        assert tabs == ()


# ---------------------------------------------------------------------------
# Public API exposure
# ---------------------------------------------------------------------------


class TestPublicApi:
    def test_all_exports_present(self) -> None:
        for name in bu.__all__:
            assert hasattr(bu, name), f"__all__ lists {name!r} but it's missing"

    def test_constants_have_expected_values(self) -> None:
        assert bu.DEFAULT_TIMEOUT_S > 0
        assert bu.DEFAULT_WAIT_TIMEOUT_MS > 0
        assert "visible" in bu.WAIT_SELECTOR_STATES
        assert "down" in bu.SCROLL_DIRECTIONS
        assert "browser-use" in bu.BROWSER_USE_BINARY_CANDIDATES
