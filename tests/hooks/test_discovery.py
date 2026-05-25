"""Tests for ultron.hooks.discovery."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ultron.hooks import discovery as d
from ultron.hooks.lifecycle import HookKind


def _write_hook(dir_: Path, name: str, body: str = "#!/usr/bin/env python\nprint('{}')\n") -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / name
    p.write_text(body, encoding="utf-8")
    return p


class TestDiscovery:
    def test_empty_directory_returns_no_scripts(self, tmp_path: Path) -> None:
        disc = d.HookDiscovery([(tmp_path, "global")])
        assert disc.discover() == {}

    def test_finds_python_hook(self, tmp_path: Path) -> None:
        _write_hook(tmp_path, "TaskStart.py")
        disc = d.HookDiscovery([(tmp_path, "global")])
        result = disc.discover()
        assert HookKind.TASK_START in result
        scripts = result[HookKind.TASK_START]
        assert len(scripts) == 1
        assert scripts[0].suffix == ".py"
        assert scripts[0].source_layer == "global"

    def test_finds_powershell_hook(self, tmp_path: Path) -> None:
        _write_hook(tmp_path, "PreToolUse.ps1", body="Write-Output '{}'\n")
        disc = d.HookDiscovery([(tmp_path, "project")])
        result = disc.discover_for(HookKind.PRE_TOOL_USE)
        assert len(result) == 1
        assert result[0].suffix == ".ps1"

    def test_finds_no_suffix_hook(self, tmp_path: Path) -> None:
        _write_hook(tmp_path, "PostToolUse", body="#!/usr/bin/env python\n")
        disc = d.HookDiscovery([(tmp_path, "project")])
        result = disc.discover_for(HookKind.POST_TOOL_USE)
        assert len(result) == 1
        assert result[0].suffix == ""

    def test_skips_unknown_kind_names(self, tmp_path: Path) -> None:
        _write_hook(tmp_path, "NotAHook.py")
        disc = d.HookDiscovery([(tmp_path, "project")])
        assert disc.discover() == {}

    def test_layer_ordering(self, tmp_path: Path) -> None:
        global_dir = tmp_path / "g"
        project_dir = tmp_path / "p"
        _write_hook(global_dir, "TaskStart.py")
        _write_hook(project_dir, "TaskStart.py")
        disc = d.HookDiscovery([
            (global_dir, "global"),
            (project_dir, "project"),
        ])
        scripts = disc.discover_for(HookKind.TASK_START)
        # Both layers present in source-layer order.
        assert len(scripts) == 2
        assert scripts[0].source_layer == "global"
        assert scripts[1].source_layer == "project"

    def test_cache_hits_on_unchanged_dir(self, tmp_path: Path) -> None:
        _write_hook(tmp_path, "TaskStart.py")
        disc = d.HookDiscovery([(tmp_path, "global")])
        first = disc.discover_for(HookKind.TASK_START)
        # No file mutation → second call returns the same script.
        second = disc.discover_for(HookKind.TASK_START)
        assert [s.path for s in first] == [s.path for s in second]

    def test_invalidate_drops_cache(self, tmp_path: Path) -> None:
        disc = d.HookDiscovery([(tmp_path, "global")])
        _write_hook(tmp_path, "TaskStart.py")
        disc.discover()
        # Delete and invalidate; next call returns nothing.
        (tmp_path / "TaskStart.py").unlink()
        os.utime(tmp_path, None)
        disc.invalidate()
        assert disc.discover_for(HookKind.TASK_START) == []

    def test_missing_directory_safe(self, tmp_path: Path) -> None:
        disc = d.HookDiscovery([(tmp_path / "absent", "global")])
        assert disc.discover() == {}

    def test_one_shot_helper(self, tmp_path: Path) -> None:
        _write_hook(tmp_path, "Notification.py")
        out = d.discover_hook_scripts([(tmp_path, "global")])
        assert HookKind.NOTIFICATION in out
