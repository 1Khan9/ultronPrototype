"""Tests for kenning.hooks.runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from kenning.hooks import runner as r
from kenning.hooks.discovery import HookScript
from kenning.hooks.lifecycle import HookKind, HookPayload


def _write_py_hook(dir_: Path, name: str, body: str) -> HookScript:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / name
    path.write_text(body, encoding="utf-8")
    return HookScript(
        kind=HookKind.TASK_START,
        path=path.resolve(),
        source_layer="project",
        suffix=path.suffix,
    )


class TestEnvelopeExtraction:
    def test_pure_json_parses(self) -> None:
        env, err = r.HookRunner._extract_envelope('{"cancel": true}')
        assert env == {"cancel": True}
        assert err == ""

    def test_noisy_with_trailing_json(self) -> None:
        text = "debug info here\n{\"context_modification\": \"hi\"}\nmore noise"
        env, err = r.HookRunner._extract_envelope(text)
        assert env is not None and env["context_modification"] == "hi"

    def test_no_json_returns_none(self) -> None:
        env, err = r.HookRunner._extract_envelope("no json at all here")
        assert env is None
        assert "no parseable" in err.lower() or err

    def test_picks_last_balanced(self) -> None:
        text = '{"first": 1}\nsome noise\n{"last": 2}'
        env, _ = r.HookRunner._extract_envelope(text)
        assert env == {"last": 2}


class TestPyHookExecution:
    def test_python_hook_returns_envelope(self, tmp_path: Path) -> None:
        body = (
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'cancel': False, 'context_modification': 'hello'}))\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner(timeout_seconds=10.0)
        result = runner.run(script, HookPayload(kind=HookKind.TASK_START))
        assert result.outcome.cancel is False
        assert result.outcome.context_modification == "hello"
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.parse_error == ""

    def test_python_hook_can_cancel(self, tmp_path: Path) -> None:
        body = (
            "import json, sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'cancel': True, 'error_message': 'blocked'}))\n"
        )
        script = _write_py_hook(tmp_path, "PreToolUse.py", body)
        script = HookScript(
            kind=HookKind.PRE_TOOL_USE,
            path=script.path,
            source_layer="project",
            suffix=script.suffix,
        )
        runner = r.HookRunner()
        result = runner.run(script, HookPayload(kind=HookKind.PRE_TOOL_USE))
        assert result.outcome.cancel is True
        assert result.outcome.error_message == "blocked"

    def test_python_hook_truncates_context_modification(self, tmp_path: Path) -> None:
        body = (
            "import json, sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'context_modification': 'x' * 20000}))\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner(context_mod_cap_chars=100)
        result = runner.run(script, HookPayload(kind=HookKind.TASK_START))
        assert len(result.outcome.context_modification) <= 100 + len(
            "\n... (truncated)",
        )
        assert result.outcome.context_modification.endswith("... (truncated)")

    def test_python_hook_empty_stdout(self, tmp_path: Path) -> None:
        body = (
            "import sys, json\n"
            "json.load(sys.stdin)\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner()
        result = runner.run(script, HookPayload(kind=HookKind.TASK_START))
        # No JSON envelope → outcome with empty fields.
        assert result.outcome.cancel is False
        assert result.outcome.context_modification == ""
        assert "empty stdout" in result.parse_error

    def test_python_hook_invalid_json(self, tmp_path: Path) -> None:
        body = (
            "import sys, json\n"
            "json.load(sys.stdin)\n"
            "print('not json')\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner()
        result = runner.run(script, HookPayload(kind=HookKind.TASK_START))
        assert result.outcome.cancel is False
        assert "no parseable" in result.parse_error.lower()

    def test_python_hook_receives_payload(self, tmp_path: Path) -> None:
        body = (
            "import json, sys\n"
            "payload = json.load(sys.stdin)\n"
            "print(json.dumps({'context_modification': payload['extra']['echo']}))\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner()
        result = runner.run(
            script,
            HookPayload(kind=HookKind.TASK_START, extra={"echo": "the-value"}),
        )
        assert result.outcome.context_modification == "the-value"

    def test_python_hook_timeout(self, tmp_path: Path) -> None:
        body = (
            "import sys, time, json\n"
            "json.load(sys.stdin)\n"
            "time.sleep(5)\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner(timeout_seconds=0.6)
        result = runner.run(script, HookPayload(kind=HookKind.TASK_START))
        assert result.timed_out is True
        assert "timed out" in result.outcome.error_message.lower()


class TestErrorPaths:
    def test_missing_interpreter_raises(self, tmp_path: Path) -> None:
        body = "print('{}')\n"
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner(python_executable="definitely-not-a-real-python-zzz")
        with pytest.raises(r.HookExecutionError):
            runner.run(script, HookPayload(kind=HookKind.TASK_START))

    def test_extra_fields_forwarded(self, tmp_path: Path) -> None:
        body = (
            "import json, sys\n"
            "json.load(sys.stdin)\n"
            "print(json.dumps({'cancel': False, 'custom': 'value'}))\n"
        )
        script = _write_py_hook(tmp_path, "TaskStart.py", body)
        runner = r.HookRunner()
        result = runner.run(script, HookPayload(kind=HookKind.TASK_START))
        assert result.outcome.extra.get("custom") == "value"
