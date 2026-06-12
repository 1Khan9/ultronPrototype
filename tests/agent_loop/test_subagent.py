"""Tests for kenning.agent_loop.subagent."""

from __future__ import annotations

import pytest

from kenning.agent_loop import subagent as sa


# ---------------------------------------------------------------------------
# ToolGuard
# ---------------------------------------------------------------------------

class TestToolGuard:
    def test_permitted_call_runs(self) -> None:
        captured: list[tuple[str, dict]] = []
        def dispatcher(name, params):
            captured.append((name, dict(params)))
            return "ok"
        guard = sa.ToolGuard(whitelist=["search"], dispatcher=dispatcher)
        result = guard.invoke("search", {"q": "weather"})
        assert result == "ok"
        assert captured == [("search", {"q": "weather"})]

    def test_unpermitted_call_raises(self) -> None:
        guard = sa.ToolGuard(whitelist=["search"], dispatcher=lambda n, p: None)
        with pytest.raises(sa.ToolNotPermittedError) as exc_info:
            guard.invoke("write_file", {"path": "x"})
        assert "write_file" in str(exc_info.value)
        assert "search" in str(exc_info.value)

    def test_call_log_records_all_invocations(self) -> None:
        guard = sa.ToolGuard(whitelist=["a", "b"], dispatcher=lambda n, p: None)
        guard.invoke("a")
        guard.invoke("b")
        try:
            guard.invoke("c")
        except sa.ToolNotPermittedError:
            pass
        assert guard.call_log == ("a", "b", "c")

    def test_is_permitted_check(self) -> None:
        guard = sa.ToolGuard(whitelist=["x"], dispatcher=lambda n, p: None)
        assert guard.is_permitted("x") is True
        assert guard.is_permitted("y") is False


# ---------------------------------------------------------------------------
# TokenLedger
# ---------------------------------------------------------------------------

class TestTokenLedger:
    def test_initial_zero(self) -> None:
        ledger = sa.TokenLedger()
        assert ledger.input_tokens == 0
        assert ledger.output_tokens == 0

    def test_add_input_accumulates(self) -> None:
        ledger = sa.TokenLedger()
        ledger.add_input(10)
        ledger.add_input(15)
        assert ledger.input_tokens == 25

    def test_add_zero_or_negative_no_op(self) -> None:
        ledger = sa.TokenLedger()
        ledger.add_input(0)
        ledger.add_output(-5)
        assert ledger.input_tokens == 0
        assert ledger.output_tokens == 0


# ---------------------------------------------------------------------------
# SubagentRunner -- serial path
# ---------------------------------------------------------------------------

class TestSubagentRunnerSerial:
    def test_empty_batch_returns_empty(self) -> None:
        runner = sa.SubagentRunner()
        results, stats = runner.run_batch([])
        assert results == ()
        assert stats.n_tasks == 0

    def test_single_task_runs(self) -> None:
        def body(prompt, guard, ledger):
            ledger.add_input(10)
            ledger.add_output(5)
            return f"echo:{prompt}"
        task = sa.SubagentTask(task_id="t1", prompt="hello", body=body)
        runner = sa.SubagentRunner()
        results, stats = runner.run_batch([task])
        assert len(results) == 1
        assert results[0].text == "echo:hello"
        assert results[0].succeeded is True
        assert results[0].input_tokens == 10
        assert results[0].output_tokens == 5
        assert stats.n_succeeded == 1
        assert stats.total_input_tokens == 10
        assert stats.total_output_tokens == 5

    def test_failing_task_records_error(self) -> None:
        def body(prompt, guard, ledger):
            raise ValueError("nope")
        task = sa.SubagentTask(task_id="t1", prompt="x", body=body)
        runner = sa.SubagentRunner()
        results, stats = runner.run_batch([task])
        assert results[0].succeeded is False
        assert "ValueError" in results[0].error_message
        assert "nope" in results[0].error_message
        assert stats.n_failed == 1
        assert stats.n_succeeded == 0

    def test_tool_call_recorded(self) -> None:
        captured: list[str] = []
        def dispatcher(name, params):
            captured.append(name)
            return None
        def body(prompt, guard, ledger):
            guard.invoke("search", {"q": "x"})
            guard.invoke("rag_query", {"q": "y"})
            return "ok"
        task = sa.SubagentTask(task_id="t1", prompt="x", body=body)
        runner = sa.SubagentRunner(dispatcher=dispatcher)
        results, stats = runner.run_batch([task])
        assert results[0].tool_calls == ("search", "rag_query")
        assert captured == ["search", "rag_query"]
        assert stats.tool_call_count == 2

    def test_task_specific_whitelist_overrides_default(self) -> None:
        def body(prompt, guard, ledger):
            # Override the default whitelist with just "echo".
            guard.invoke("echo")
            return "ok"
        task = sa.SubagentTask(
            task_id="t1",
            prompt="",
            body=body,
            tool_whitelist=["echo"],
        )
        runner = sa.SubagentRunner()
        results, stats = runner.run_batch([task])
        assert results[0].succeeded is True
        assert results[0].tool_calls == ("echo",)

    def test_write_tool_blocked_by_default(self) -> None:
        def body(prompt, guard, ledger):
            guard.invoke("write_file", {"path": "x", "content": "y"})
            return "ok"
        task = sa.SubagentTask(task_id="t1", prompt="", body=body)
        runner = sa.SubagentRunner()
        results, stats = runner.run_batch([task])
        assert results[0].succeeded is False
        assert "write_file" in results[0].error_message


# ---------------------------------------------------------------------------
# SubagentRunner -- parallel path
# ---------------------------------------------------------------------------

class TestSubagentRunnerParallel:
    def test_multiple_tasks_run_in_order(self) -> None:
        def body(prompt, guard, ledger):
            ledger.add_input(1)
            ledger.add_output(1)
            return prompt.upper()
        tasks = [
            sa.SubagentTask(task_id=f"t{i}", prompt=f"task{i}", body=body)
            for i in range(3)
        ]
        runner = sa.SubagentRunner(max_parallel=3)
        results, stats = runner.run_batch(tasks)
        # Output order matches input order (the runner sorts by index).
        assert [r.text for r in results] == ["TASK0", "TASK1", "TASK2"]
        assert stats.n_succeeded == 3

    def test_roll_up_sums_correctly(self) -> None:
        def body(prompt, guard, ledger):
            ledger.add_input(int(prompt))
            ledger.add_output(int(prompt) * 2)
            return ""
        tasks = [
            sa.SubagentTask(task_id=f"t{i}", prompt=str(i + 1), body=body)
            for i in range(3)
        ]
        runner = sa.SubagentRunner(max_parallel=3)
        results, stats = runner.run_batch(tasks)
        # Inputs: 1+2+3 = 6; outputs: 2+4+6 = 12.
        assert stats.total_input_tokens == 6
        assert stats.total_output_tokens == 12

    def test_partial_failure_rolls_up_correctly(self) -> None:
        def good_body(p, g, l):
            l.add_input(5)
            return "ok"
        def bad_body(p, g, l):
            raise RuntimeError("boom")
        tasks = [
            sa.SubagentTask(task_id="ok", prompt="", body=good_body),
            sa.SubagentTask(task_id="bad", prompt="", body=bad_body),
        ]
        runner = sa.SubagentRunner(max_parallel=2)
        results, stats = runner.run_batch(tasks)
        assert stats.n_succeeded == 1
        assert stats.n_failed == 1
        assert stats.total_input_tokens == 5  # only the success counted.


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_max_parallel_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            sa.SubagentRunner(max_parallel=0)

    def test_max_parallel_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            sa.SubagentRunner(max_parallel=-1)


# ---------------------------------------------------------------------------
# DEFAULT_READONLY_TOOL_WHITELIST sanity
# ---------------------------------------------------------------------------

class TestDefaultWhitelist:
    def test_contains_expected_readonly_tools(self) -> None:
        wl = sa.DEFAULT_READONLY_TOOL_WHITELIST
        assert "file_read" in wl
        assert "search" in wl
        assert "rag_query" in wl

    def test_excludes_write_tools(self) -> None:
        wl = sa.DEFAULT_READONLY_TOOL_WHITELIST
        assert "write_file" not in wl
        assert "execute_command" not in wl  # only the readonly variant
