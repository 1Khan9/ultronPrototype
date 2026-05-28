"""Tests for the catalog 11 (clawhub-browser-agent) additions to
:class:`ultron.desktop.browser_use.BrowserUseTool`:

* T3 -- :meth:`click_css_selector` (CSS-selector -> getBoundingClientRect
  -> centre coordinate -> gated :meth:`click_at_coords`).
* T7 -- :meth:`wait_for_element_js` (MutationObserver event-driven wait
  via the gated :meth:`eval`).

Both compose the existing gated surface, so the tests mock ``eval`` /
``click_at_coords`` (binding rule R1: ``monkeypatch.setattr``) and never
spawn a subprocess or require the ``browser-use`` binary.
"""

from __future__ import annotations

import json

from ultron.desktop.browser_use import (
    BrowserActionResult,
    BrowserEvalResult,
    BrowserUseResult,
    BrowserUseTool,
)


# --- fakes ----------------------------------------------------------------


def _fake_eval(*, value=None, success=True, requires_two_phase=False, error=None):
    """Build a fake ``eval`` that records the script it was handed."""
    calls: list[dict] = []

    def fake_eval(script, **kwargs):
        calls.append({"script": script, "kwargs": kwargs})
        return BrowserEvalResult(
            success=success,
            action="eval",
            value=value,
            requires_two_phase=requires_two_phase,
            error=error,
            safety_verdict="" if requires_two_phase else "ALLOW",
        )

    fake_eval.calls = calls  # type: ignore[attr-defined]
    return fake_eval


def _fake_click(*, success=True, error=None):
    """Build a fake ``click_at_coords`` that records its coordinates."""
    calls: list[dict] = []

    def fake_click(x, y, **kwargs):
        calls.append({"x": x, "y": y, "kwargs": kwargs})
        return BrowserActionResult(
            success=success,
            action="click_at_coords",
            target=f"{x},{y}",
            error=error,
            safety_verdict="ALLOW",
        )

    fake_click.calls = calls  # type: ignore[attr-defined]
    return fake_click


def _tool() -> BrowserUseTool:
    # Constructor is lazy: no binary resolution, no subprocess.
    return BrowserUseTool()


# --- T3: click_css_selector ----------------------------------------------


def test_click_css_empty_selector():
    tool = _tool()
    result = tool.click_css_selector("   ")
    assert result.success is False
    assert "empty selector" in (result.error or "")


def test_click_css_disallowed_scheme():
    tool = _tool()
    for hostile in ("javascript:alert(1)", "DATA:text/html,x", "vbscript:msgbox"):
        result = tool.click_css_selector(hostile)
        assert result.success is False
        assert "disallowed URI scheme" in (result.error or ""), hostile


def test_click_css_happy_path_computes_center(monkeypatch):
    tool = _tool()
    ev = _fake_eval(value={"x": 10, "y": 20, "width": 100, "height": 40})
    click = _fake_click(success=True)
    monkeypatch.setattr(tool, "eval", ev)
    monkeypatch.setattr(tool, "click_at_coords", click)

    result = tool.click_css_selector("#submit", user_text="click submit")

    assert result.success is True
    assert result.action == "click_css_selector"
    # centre = (10 + 100/2, 20 + 40/2) = (60, 40)
    assert click.calls and click.calls[0]["x"] == 60 and click.calls[0]["y"] == 40
    # user_text threaded through to the gated coordinate click
    assert click.calls[0]["kwargs"].get("user_text") == "click submit"
    # label records selector + resolved coordinate for the audit log
    assert "#submit" in result.target and "(60,40)" in result.target


def test_click_css_selector_is_json_encoded_in_probe(monkeypatch):
    tool = _tool()
    ev = _fake_eval(value={"x": 0, "y": 0, "width": 5, "height": 5})
    monkeypatch.setattr(tool, "eval", ev)
    monkeypatch.setattr(tool, "click_at_coords", _fake_click())

    # A selector with a double-quote would break a naive string build.
    hostile_sel = 'a[title="x"]'
    tool.click_css_selector(hostile_sel)

    probe = ev.calls[0]["script"]
    # The selector must appear ONLY in its json.dumps-encoded form.
    assert json.dumps(hostile_sel) in probe
    assert "getBoundingClientRect" in probe
    # The raw unescaped selector must NOT appear verbatim (would mean a
    # broken-out string literal / injection).
    assert hostile_sel not in probe


def test_click_css_no_element(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "eval", _fake_eval(value=None))
    click = _fake_click()
    monkeypatch.setattr(tool, "click_at_coords", click)

    result = tool.click_css_selector("#missing")
    assert result.success is False
    assert "matched no element" in (result.error or "")
    assert not click.calls, "click must not fire when no element matched"


def test_click_css_zero_size_element(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        tool, "eval", _fake_eval(value={"x": 5, "y": 5, "width": 0, "height": 0})
    )
    click = _fake_click()
    monkeypatch.setattr(tool, "click_at_coords", click)

    result = tool.click_css_selector("#hidden")
    assert result.success is False
    assert "zero-size" in (result.error or "")
    assert not click.calls


def test_click_css_non_numeric_rect(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        tool, "eval", _fake_eval(value={"x": "nope", "y": 0, "width": 1, "height": 1})
    )
    click = _fake_click()
    monkeypatch.setattr(tool, "click_at_coords", click)

    result = tool.click_css_selector("#weird")
    assert result.success is False
    assert "not numeric" in (result.error or "")
    assert not click.calls


def test_click_css_eval_two_phase_blocks_click(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        tool, "eval", _fake_eval(success=False, requires_two_phase=True, error="approval")
    )
    click = _fake_click()
    monkeypatch.setattr(tool, "click_at_coords", click)

    result = tool.click_css_selector("#x")
    assert result.success is False
    assert not click.calls, "click must not fire when probe needs approval"


def test_click_css_eval_failure_blocks_click(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        tool, "eval", _fake_eval(success=False, error="cli down")
    )
    click = _fake_click()
    monkeypatch.setattr(tool, "click_at_coords", click)

    result = tool.click_css_selector("#x")
    assert result.success is False
    assert "cli down" in (result.error or "")
    assert not click.calls


def test_click_css_propagates_click_failure(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        tool, "eval", _fake_eval(value={"x": 1, "y": 1, "width": 10, "height": 10})
    )
    monkeypatch.setattr(
        tool, "click_at_coords", _fake_click(success=False, error="click blocked")
    )

    result = tool.click_css_selector("#x")
    assert result.success is False
    assert "click blocked" in (result.error or "")


# --- T7: wait_for_element_js ---------------------------------------------


def test_wait_js_empty_selector():
    result = _tool().wait_for_element_js("")
    assert result.success is False
    assert "empty selector" in (result.error or "")


def test_wait_js_bad_timeout():
    result = _tool().wait_for_element_js("#x", timeout_ms=0)
    assert result.success is False
    assert "timeout_ms" in (result.error or "")


def test_wait_js_matched_true(monkeypatch):
    tool = _tool()
    ev = _fake_eval(value=True)
    monkeypatch.setattr(tool, "eval", ev)

    result = tool.wait_for_element_js("#ready", timeout_ms=5000)
    assert result.success is True
    assert result.matched is True
    assert result.state == "js_observer"
    # The injected JS must use MutationObserver + a bounded setTimeout
    # (the improvement over the upstream's unbounded promise) + the
    # json-encoded selector.
    js = ev.calls[0]["script"]
    assert "MutationObserver" in js
    assert "setTimeout" in js
    assert "5000" in js
    assert json.dumps("#ready") in js


def test_wait_js_timeout_returns_unmatched(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "eval", _fake_eval(value=False))
    result = tool.wait_for_element_js("#never")
    assert result.matched is False
    assert result.success is False
    assert "did not appear" in (result.error or "")


def test_wait_js_string_true_coerced(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "eval", _fake_eval(value="true"))
    result = tool.wait_for_element_js("#ready")
    assert result.matched is True


def test_wait_js_eval_two_phase(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(
        tool, "eval", _fake_eval(success=False, requires_two_phase=True, error="approval")
    )
    result = tool.wait_for_element_js("#x")
    assert result.success is False
    assert result.matched is False


def test_wait_js_eval_failure(monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "eval", _fake_eval(success=False, error="cli down"))
    result = tool.wait_for_element_js("#x")
    assert result.success is False
    assert "cli down" in (result.error or "")


def test_wait_js_selector_injection_safe(monkeypatch):
    tool = _tool()
    ev = _fake_eval(value=True)
    monkeypatch.setattr(tool, "eval", ev)
    hostile = 'div[data-x="y"]'
    tool.wait_for_element_js(hostile)
    js = ev.calls[0]["script"]
    assert json.dumps(hostile) in js
    assert hostile not in js


# --- T6: export_pdf -------------------------------------------------------


class _FakeResolver:
    """Minimal PathResolver stand-in: forces the resolve() fallback (the
    not-yet-existing-output-file case) and returns a fixed path."""

    def __init__(self, resolved):
        self._resolved = resolved

    def safe_realpath(self, _s):
        return None

    def resolve(self, _s):
        return self._resolved


def _fake_invoke(*, success=True, error=None):
    calls: list[dict] = []

    def fake_invoke(args, *, action, timeout_s=None):
        calls.append({"args": list(args), "action": action})
        return BrowserUseResult(
            success=success,
            action=action,
            stdout="ok" if success else "",
            error=error,
            exit_code=0 if success else 1,
        )

    fake_invoke.calls = calls  # type: ignore[attr-defined]
    return fake_invoke


def test_export_pdf_empty_path():
    result = _tool().export_pdf("   ")
    assert result.success is False
    assert "empty destination" in (result.error or "")


def test_export_pdf_bad_dimensions(tmp_path):
    tool = _tool()
    result = tool.export_pdf(
        str(tmp_path / "out.pdf"),
        paper_width=0,
        path_resolver=_FakeResolver(tmp_path / "out.pdf"),
    )
    assert result.success is False
    assert "paper dimensions" in (result.error or "")


def test_export_pdf_parent_missing(tmp_path):
    tool = _tool()
    missing_parent = tmp_path / "nope" / "out.pdf"
    result = tool.export_pdf(
        str(missing_parent), path_resolver=_FakeResolver(missing_parent)
    )
    assert result.success is False
    assert "parent directory does not exist" in (result.error or "")


def test_export_pdf_happy_path_builds_args(tmp_path, monkeypatch):
    tool = _tool()
    dest = tmp_path / "report.pdf"
    inv = _fake_invoke(success=True)
    monkeypatch.setattr(tool, "_invoke", inv)

    result = tool.export_pdf(
        str(dest),
        paper_width=8.5,
        paper_height=11.0,
        user_text="save this as a pdf",
        path_resolver=_FakeResolver(dest),
    )
    assert result.success is True
    assert result.action == "export_pdf"
    assert result.target == str(dest)
    args = inv.calls[0]["args"]
    assert args[0] == "pdf"
    assert str(dest) in args
    assert "--paper-width" in args and "8.5" in args
    assert "--paper-height" in args and "11.0" in args
    # print_background defaults True -> flag present; landscape default
    # False -> absent.
    assert "--print-background" in args
    assert "--landscape" not in args


def test_export_pdf_landscape_flag(tmp_path, monkeypatch):
    tool = _tool()
    dest = tmp_path / "land.pdf"
    inv = _fake_invoke(success=True)
    monkeypatch.setattr(tool, "_invoke", inv)
    tool.export_pdf(
        str(dest), landscape=True, path_resolver=_FakeResolver(dest)
    )
    assert "--landscape" in inv.calls[0]["args"]


def test_export_pdf_cli_failure_fails_open(tmp_path, monkeypatch):
    tool = _tool()
    dest = tmp_path / "x.pdf"
    monkeypatch.setattr(
        tool, "_invoke", _fake_invoke(success=False, error="pdf unsupported")
    )
    result = tool.export_pdf(str(dest), path_resolver=_FakeResolver(dest))
    assert result.success is False
    assert "pdf unsupported" in (result.error or "")


def test_export_pdf_safety_denial_blocks_invoke(tmp_path, monkeypatch):
    tool = _tool()
    dest = tmp_path / "x.pdf"
    inv = _fake_invoke(success=True)
    monkeypatch.setattr(tool, "_invoke", inv)

    def deny(**kwargs):
        return BrowserActionResult(
            success=False,
            action="export_pdf",
            error="safety denied (BLOCK_HARD): nope",
            safety_verdict="BLOCK_HARD",
            target=str(dest),
        )

    monkeypatch.setattr(tool, "_safety_check", deny)
    result = tool.export_pdf(str(dest), path_resolver=_FakeResolver(dest))
    assert result.success is False
    assert result.safety_verdict == "BLOCK_HARD"
    assert not inv.calls, "subprocess must not run when safety denies"
