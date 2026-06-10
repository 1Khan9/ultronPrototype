"""Tests for the pervasive evolution reach-signals (#62/#125/#63/#64/#66/#68).

Covers the two pure-observation seams (the error-log observer + the
validator BLOCK_HARD observer), the coding-runner task-success queue, and
the orchestrator-side drains + re-ask detection. All hermetic: tmp_path
logs, ``Orchestrator.__new__`` pattern, no voice stack, observers cleared
in ``finally`` so no state leaks across tests (binding rule R1/R7).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ultron.coding.bridge import EventKind
from ultron.coding.runner import CodingTaskRunner
from ultron.pipeline.orchestrator import Orchestrator
from ultron.resilience.error_log import ErrorLog, set_error_observer
from ultron.safety import Policy, RuleContext, ToolCallValidator, Verdict
from ultron.safety.rules.base import CommandPatternRule
from ultron.safety.validator import set_block_observer


# ---------------------------------------------------------------------------
# error-log observer (#62/#125/#64)
# ---------------------------------------------------------------------------


class TestErrorLogObserver:
    def test_observer_fires_on_record(self, tmp_path: Path) -> None:
        seen: list[tuple] = []
        log = ErrorLog(path=tmp_path / "errors.jsonl")
        set_error_observer(lambda dep, msg: seen.append((dep, msg)))
        try:
            log.record(RuntimeError("brave rate limited"), dependency="brave_api")
        finally:
            set_error_observer(None)
        assert seen == [("brave_api", "brave rate limited")]
        # The record itself still landed.
        assert "brave rate limited" in (tmp_path / "errors.jsonl").read_text(
            encoding="utf-8"
        )

    def test_observer_raise_never_drops_record(self, tmp_path: Path) -> None:
        def _boom(dep: str, msg: str) -> None:
            raise RuntimeError("observer boom")

        log = ErrorLog(path=tmp_path / "errors.jsonl")
        set_error_observer(_boom)
        try:
            log.record(RuntimeError("qdrant down"), dependency="qdrant")
        finally:
            set_error_observer(None)
        assert "qdrant down" in (tmp_path / "errors.jsonl").read_text(
            encoding="utf-8"
        )

    def test_cleared_observer_is_noop(self, tmp_path: Path) -> None:
        seen: list[tuple] = []
        log = ErrorLog(path=tmp_path / "errors.jsonl")
        set_error_observer(lambda dep, msg: seen.append((dep, msg)))
        set_error_observer(None)
        log.record(RuntimeError("x"), dependency="d")
        assert seen == []


# ---------------------------------------------------------------------------
# validator BLOCK_HARD observer (#63)
# ---------------------------------------------------------------------------


def _blocking_validator() -> ToolCallValidator:
    blocker = CommandPatternRule(
        rule_id="X1", description="always-block", category="X", patterns=[r".*"],
    )
    return ToolCallValidator(
        policy=Policy(enabled=True, rule_enabled={}), rules=[blocker], audit_log=None,
    )


class TestBlockObserver:
    def test_observer_fires_on_block_hard(self) -> None:
        seen: list[tuple] = []
        v = _blocking_validator()
        set_block_observer(lambda tool, reason: seen.append((tool, reason)))
        try:
            verdict = v.check(
                RuleContext(tool_name="shell.exec", arguments={"cmd": "rm"}, capability="c")
            )
        finally:
            set_block_observer(None)
        assert verdict.verdict == Verdict.BLOCK_HARD
        assert len(seen) == 1
        assert seen[0][0] == "shell.exec"

    def test_observer_not_fired_on_allow(self) -> None:
        seen: list[tuple] = []
        v = ToolCallValidator(
            policy=Policy(enabled=True, rule_enabled={}), rules=[], audit_log=None,
        )
        set_block_observer(lambda tool, reason: seen.append((tool, reason)))
        try:
            verdict = v.check(
                RuleContext(tool_name="t", arguments={}, capability="c")
            )
        finally:
            set_block_observer(None)
        assert verdict.verdict == Verdict.ALLOW
        assert seen == []

    def test_observer_raise_never_alters_verdict(self) -> None:
        def _boom(tool: str, reason: str) -> None:
            raise RuntimeError("observer boom")

        v = _blocking_validator()
        set_block_observer(_boom)
        try:
            verdict = v.check(
                RuleContext(tool_name="t", arguments={"x": "y"}, capability="c")
            )
        finally:
            set_block_observer(None)
        assert verdict.verdict == Verdict.BLOCK_HARD  # verdict unaffected


# ---------------------------------------------------------------------------
# runner task-success queue (#66)
# ---------------------------------------------------------------------------


def _bare_runner() -> Any:
    import threading

    r = CodingTaskRunner.__new__(CodingTaskRunner)
    r._pending_task_successes = []
    r._task_success_lock = threading.Lock()
    return r


def _evolution_cfg(enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(evolution=SimpleNamespace(enabled=enabled))


class TestRunnerSuccessQueue:
    def test_listener_none_when_evolution_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod

        monkeypatch.setattr(cfgmod, "get_config", lambda: _evolution_cfg(False))
        r = _bare_runner()
        assert r._make_evolution_success_listener(None, "label") is None

    def test_complete_success_queues_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod

        monkeypatch.setattr(cfgmod, "get_config", lambda: _evolution_cfg(True))
        r = _bare_runner()
        listener = r._make_evolution_success_listener(None, "build calculator")
        assert listener is not None
        event = SimpleNamespace(
            kind=EventKind.COMPLETE, exit_status=0, summary="Created calc.py"
        )
        listener(event)
        listener(event)  # second COMPLETE must not double-queue
        assert r.drain_task_successes() == [("build calculator", "Created calc.py")]
        assert r.drain_task_successes() == []  # drained

    def test_nonzero_exit_does_not_queue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod

        monkeypatch.setattr(cfgmod, "get_config", lambda: _evolution_cfg(True))
        r = _bare_runner()
        listener = r._make_evolution_success_listener(None, "label")
        listener(SimpleNamespace(kind=EventKind.COMPLETE, exit_status=2, summary="boom"))
        assert r.drain_task_successes() == []

    def test_non_complete_events_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ultron.config as cfgmod

        monkeypatch.setattr(cfgmod, "get_config", lambda: _evolution_cfg(True))
        r = _bare_runner()
        listener = r._make_evolution_success_listener(None, "label")
        listener(SimpleNamespace(kind=EventKind.TEXT, text="hi"))
        assert r.drain_task_successes() == []


# ---------------------------------------------------------------------------
# orchestrator drains + re-ask detection (#66/#68 + queue drain)
# ---------------------------------------------------------------------------


class _FakeEvolutionSink:
    def __init__(self) -> None:
        self.turns: list[dict] = []
        self.command_failures: list[dict] = []

    def record_turn(self, **kwargs: Any) -> None:
        self.turns.append(kwargs)

    def record_command_failure(
        self, command: str = "", output: str = "", *, exit_code=None
    ) -> None:
        self.command_failures.append(
            {"command": command, "output": output, "exit_code": exit_code}
        )


def _bare_orch() -> Any:
    o = Orchestrator.__new__(Orchestrator)
    o.evolution = None
    o.coding_voice = None
    o.llm = None
    return o


class TestReachSignalDrain:
    def test_install_noop_when_evolution_disabled(self) -> None:
        o = _bare_orch()
        o._install_evolution_reach_observers()
        assert getattr(o, "_evolution_reach_queue", None) is None

    def test_observers_feed_queue_and_drain(self, tmp_path: Path) -> None:
        o = _bare_orch()
        fake = _FakeEvolutionSink()
        o.evolution = fake
        o._install_evolution_reach_observers()
        try:
            # The error seam.
            log = ErrorLog(path=tmp_path / "errors.jsonl")
            log.record(RuntimeError("search timed out"), dependency="brave_api")
            # The block seam.
            v = _blocking_validator()
            v.check(RuleContext(tool_name="shell.exec", arguments={}, capability="c"))
        finally:
            set_error_observer(None)
            set_block_observer(None)
        assert len(o._evolution_reach_queue) == 2
        o._drain_evolution_reach_signals()
        assert len(o._evolution_reach_queue) == 0
        assert len(fake.command_failures) == 2
        first = fake.command_failures[0]
        assert first["command"] == "dependency:brave_api"
        assert first["exit_code"] == 1
        assert "failed" in first["output"]
        assert fake.command_failures[1]["command"] == "safety_block:shell.exec"

    def test_drain_noop_when_queue_empty(self) -> None:
        o = _bare_orch()
        o.evolution = _FakeEvolutionSink()
        o._install_evolution_reach_observers()
        try:
            o._drain_evolution_reach_signals()
        finally:
            set_error_observer(None)
            set_block_observer(None)
        assert o.evolution.command_failures == []

    def test_drain_fail_open_on_service_raise(self) -> None:
        class _Boom(_FakeEvolutionSink):
            def record_command_failure(self, *a: Any, **k: Any) -> None:
                raise RuntimeError("service boom")

        o = _bare_orch()
        o.evolution = _Boom()
        o._install_evolution_reach_observers()
        try:
            o._evolution_reach_queue.append(("dependency:x", "detail"))
            o._drain_evolution_reach_signals()  # swallowed
        finally:
            set_error_observer(None)
            set_block_observer(None)


class TestTaskSuccessDrain:
    def test_feeds_successes_as_opportunity_turns(self) -> None:
        o = _bare_orch()
        fake = _FakeEvolutionSink()
        o.evolution = fake
        successes = [("build calculator", "Created calc.py")]
        o.coding_voice = SimpleNamespace(
            runner=SimpleNamespace(drain_task_successes=lambda: list(successes))
        )
        o._drain_evolution_task_successes()
        assert len(fake.turns) == 1
        turn = fake.turns[0]
        assert turn["user_text"] == "build calculator"
        assert turn["signals"] == ("coding_task_success",)
        assert turn["response_summary"] == "Created calc.py"

    def test_noop_when_evolution_disabled(self) -> None:
        o = _bare_orch()
        o.coding_voice = SimpleNamespace(
            runner=SimpleNamespace(drain_task_successes=lambda: [("l", "s")])
        )
        o._drain_evolution_task_successes()  # must not raise

    def test_noop_when_runner_lacks_drain(self) -> None:
        o = _bare_orch()
        o.evolution = _FakeEvolutionSink()
        o.coding_voice = SimpleNamespace(runner=SimpleNamespace())
        o._drain_evolution_task_successes()
        assert o.evolution.turns == []


class TestReAskDetection:
    def test_identical_repeat_detected(self) -> None:
        o = _bare_orch()
        assert o._detect_re_ask("what is the boiling point of lead") is False
        assert o._detect_re_ask("what is the boiling point of lead") is True

    def test_near_identical_repeat_detected(self) -> None:
        o = _bare_orch()
        o._detect_re_ask("what is the boiling point of lead")
        assert o._detect_re_ask("what's the boiling point of lead") is True

    def test_different_question_not_detected(self) -> None:
        o = _bare_orch()
        o._detect_re_ask("what is the boiling point of lead")
        assert o._detect_re_ask("how far away is the moon from earth") is False

    def test_short_utterances_never_trip(self) -> None:
        o = _bare_orch()
        assert o._detect_re_ask("yes") is False
        assert o._detect_re_ask("yes") is False  # identical but too short

    def test_first_utterance_never_trips(self) -> None:
        o = _bare_orch()
        assert o._detect_re_ask("a perfectly reasonable first question") is False
