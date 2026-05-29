"""Tests for the Category U .ultronignore enforcement rule.

UltronIgnoreRule wraps the ignore controller: a tool call touching an ignored
path (read or write) -- or a file-reading shell command whose path argument is
ignored -- is BLOCK_HARD. Default-safe (no ignore file -> ALLOW) + fail-open.
The controller is faked so these tests pin the RULE logic, not pathspec.
"""

from __future__ import annotations

from types import SimpleNamespace

import ultron.safety.ignore as ig
from ultron.safety.rules.category_ignore import UltronIgnoreRule, build_ignore_rules
from ultron.safety.validator import Verdict


class _FakeController:
    def __init__(self, ignored=(), denied_cmd=None):
        self._ignored = set(ignored)
        self._denied_cmd = denied_cmd

    def check_path(self, path):
        return SimpleNamespace(
            ignored=str(path) in self._ignored,
            matched_layer="workspace",
            matched_pattern="secrets/",
        )

    def validate_command(self, command):  # noqa: ARG002
        return SimpleNamespace(denied_path=self._denied_cmd)


def _ctx(*, tool_name="file.read", paths=(), arguments=None):
    return SimpleNamespace(
        tool_name=tool_name, paths=tuple(paths), arguments=arguments or {},
    )


def test_blocks_ignored_path(monkeypatch):
    monkeypatch.setattr(
        ig, "get_ignore_controller",
        lambda *a, **k: _FakeController(ignored={"/proj/secrets/key.txt"}),
    )
    res = UltronIgnoreRule().evaluate(
        _ctx(paths=["/proj/secrets/key.txt"]), policy=None, resolver=None,
    )
    assert res.verdict == Verdict.BLOCK_HARD
    assert "secrets" in res.reason


def test_allows_non_ignored_path(monkeypatch):
    monkeypatch.setattr(
        ig, "get_ignore_controller",
        lambda *a, **k: _FakeController(ignored={"/proj/secrets/key.txt"}),
    )
    res = UltronIgnoreRule().evaluate(
        _ctx(paths=["/proj/src/main.py"]), policy=None, resolver=None,
    )
    assert res.verdict == Verdict.ALLOW


def test_blocks_ignored_read_command(monkeypatch):
    monkeypatch.setattr(
        ig, "get_ignore_controller",
        lambda *a, **k: _FakeController(denied_cmd="/proj/.env"),
    )
    res = UltronIgnoreRule().evaluate(
        _ctx(tool_name="shell.run", arguments={"command": "cat .env"}),
        policy=None, resolver=None,
    )
    assert res.verdict == Verdict.BLOCK_HARD


def test_no_ignore_file_is_noop(monkeypatch):
    monkeypatch.setattr(
        ig, "get_ignore_controller", lambda *a, **k: _FakeController(),
    )
    res = UltronIgnoreRule().evaluate(
        _ctx(paths=["/proj/secrets/key.txt"], arguments={"command": "cat foo"}),
        policy=None, resolver=None,
    )
    assert res.verdict == Verdict.ALLOW


def test_controller_unavailable_fails_open(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("controller down")

    monkeypatch.setattr(ig, "get_ignore_controller", _boom)
    res = UltronIgnoreRule().evaluate(_ctx(paths=["/x"]), policy=None, resolver=None)
    assert res.verdict == Verdict.ALLOW


def test_per_path_check_error_is_skipped(monkeypatch):
    class _BadCheck:
        def check_path(self, p):  # noqa: ARG002
            raise RuntimeError("boom")

        def validate_command(self, c):  # noqa: ARG002
            return SimpleNamespace(denied_path=None)

    monkeypatch.setattr(ig, "get_ignore_controller", lambda *a, **k: _BadCheck())
    res = UltronIgnoreRule().evaluate(_ctx(paths=["/x"]), policy=None, resolver=None)
    assert res.verdict == Verdict.ALLOW  # error skipped, no spurious block


def test_forwards_resolver_project_root_as_workspace_root(monkeypatch):
    """The rule must forward the active project root so the project + workspace
    .ultronignore layers resolve -- without it the controller keys on
    "__global__" and ONLY ~/.ultron/.ultronignore is consulted."""
    captured = {}

    def _capture(*a, **k):
        captured["workspace_root"] = k.get("workspace_root")
        return _FakeController()

    monkeypatch.setattr(ig, "get_ignore_controller", _capture)
    resolver = SimpleNamespace(project_root="/proj/myapp")
    UltronIgnoreRule().evaluate(
        _ctx(paths=["/proj/myapp/src/x.py"]), policy=None, resolver=resolver,
    )
    assert captured["workspace_root"] == "/proj/myapp"


def test_workspace_root_none_when_no_resolver(monkeypatch):
    captured = {}

    def _capture(*a, **k):
        captured["workspace_root"] = k.get("workspace_root")
        return _FakeController()

    monkeypatch.setattr(ig, "get_ignore_controller", _capture)
    UltronIgnoreRule().evaluate(_ctx(paths=["/x"]), policy=None, resolver=None)
    assert captured["workspace_root"] is None


def test_build_ignore_rules():
    rules = build_ignore_rules()
    assert len(rules) == 1
    assert rules[0].rule_id == "U1"


def test_rule_registered_in_default_validator():
    from ultron.safety.validator import build_validator_from_config

    validator = build_validator_from_config()
    assert any(getattr(r, "rule_id", "") == "U1" for r in validator.rules)
