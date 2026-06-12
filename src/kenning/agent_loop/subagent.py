"""Subagent runner: read-only parallel research with token-meter rollup.

Adapted from cline's ``SubagentRunner`` pattern (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Ultron's variant runs N callables in
parallel with per-subagent token budgets, an enforced read-only tool
whitelist, and a rolled-up :class:`SubagentBatchStats` so the parent
caller can attribute aggregate cost back to the originating turn.

The primitive is intentionally agnostic about the inner LLM client:
each subagent is just a callable :class:`SubagentTask` whose body is
executed under the runner's safety enforcement layer. The orchestrator
wires the actual LLM call (or RAG retrieve, or web-search fan-out) on
top.

Key shapes:

* :class:`SubagentTask` -- one unit of read-only work (prompt, tool
  whitelist override, token cap, optional context-window cap).
* :class:`SubagentResult` -- per-task outcome (text, token meters,
  succeeded flag, error string).
* :class:`SubagentBatchStats` -- roll-up across the batch (total
  input tokens, total output tokens, max wall-clock seconds, success
  count).
* :class:`SubagentRunner` -- thread-pool-backed parallel dispatcher
  with the read-only tool guard + per-task isolation.

Tool whitelist enforcement: every task body receives a
:class:`ToolGuard` instance. Calls to ``ToolGuard.invoke(name, params)``
that fail the whitelist raise :class:`ToolNotPermittedError`. The
default whitelist matches cline's read-only tool set
(``FILE_READ``, ``LIST_FILES``, ``LIST_CODE_DEF``, ``SEARCH``,
``USE_SKILL``, ``EXECUTE_COMMAND_READONLY``). Callers can pass a
narrower whitelist per-task.

VRAM safety: ``max_parallel`` defaults to 1 (no parallelism) to
preserve the voice baseline contract -- callers must opt in explicitly
by raising the cap. This matches the catalog's "default off until
VRAM headroom verified" guidance.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence


#: Default read-only tool whitelist. Matches cline's subagent allowed
#: tool set translated into ultron's tool-name conventions.
DEFAULT_READONLY_TOOL_WHITELIST: frozenset[str] = frozenset({
    "file_read",
    "list_files",
    "list_code_definitions",
    "search",
    "ripgrep_search",
    "use_skill",
    "execute_command_readonly",
    "rag_query",
    "web_search",
})


class ToolNotPermittedError(Exception):
    """Raised when a subagent invokes a tool outside its whitelist."""

    def __init__(self, tool_name: str, whitelist: Iterable[str]) -> None:
        self.tool_name = tool_name
        self.whitelist = tuple(sorted(whitelist))
        super().__init__(
            f"tool {tool_name!r} not permitted; whitelist={list(self.whitelist)}",
        )


@dataclass(frozen=True)
class SubagentTask:
    """One unit of subagent work.

    Attributes:
        task_id: caller-supplied opaque identifier (echoed on the
            :class:`SubagentResult`). Useful for joining results back
            to a structured plan.
        prompt: the inner-LLM prompt body OR opaque payload the task
            body interprets. The runner does not inspect it; the body
            callable receives it verbatim.
        body: the actual work to run. Receives the prompt + a
            :class:`ToolGuard` + a :class:`TokenLedger`. Returns the
            response text (or any string the caller wants in
            :attr:`SubagentResult.text`).
        tool_whitelist: optional per-task whitelist override.
            Defaults to :data:`DEFAULT_READONLY_TOOL_WHITELIST` when
            ``None``.
        input_token_cap: optional hard cap on input tokens (the body
            is responsible for checking and self-aborting).
        output_token_cap: optional hard cap on output tokens.
        wall_clock_timeout_seconds: optional per-task timeout.
            ``0`` disables.
        notes: free-form annotation.
    """

    task_id: str
    prompt: str
    body: Callable[..., str]
    tool_whitelist: Optional[Iterable[str]] = None
    input_token_cap: int = 0
    output_token_cap: int = 0
    wall_clock_timeout_seconds: float = 0.0
    notes: str = ""


@dataclass(frozen=True)
class SubagentResult:
    """Outcome of one :class:`SubagentTask`.

    Attributes:
        task_id: echoed from the task.
        succeeded: ``True`` on a clean return; ``False`` on raise or
            timeout.
        text: the body's return value (or empty on failure).
        input_tokens: count recorded via :class:`TokenLedger`.
        output_tokens: count recorded via :class:`TokenLedger`.
        wall_clock_seconds: actual run time.
        error_message: empty when ``succeeded``; otherwise the
            exception class + message.
        tool_calls: list of tool names invoked (in order). Useful for
            audit + the "which tools did the subagent reach for?"
            telemetry.
    """

    task_id: str
    succeeded: bool
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    wall_clock_seconds: float = 0.0
    error_message: str = ""
    tool_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubagentBatchStats:
    """Aggregate stats across a :class:`SubagentRunner.run_batch` call.

    Attributes:
        n_tasks: how many tasks were dispatched.
        n_succeeded: how many returned cleanly.
        n_failed: how many raised or timed out.
        total_input_tokens: sum across all subagents.
        total_output_tokens: sum across all subagents.
        max_wall_clock_seconds: the slowest subagent's run time
            (this is what the parent observes as the batch latency
            when running in parallel).
        sum_wall_clock_seconds: sum of all subagent run times (what
            the work would have cost in sequential execution).
        tool_call_count: total tool invocations across the batch.
    """

    n_tasks: int = 0
    n_succeeded: int = 0
    n_failed: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    max_wall_clock_seconds: float = 0.0
    sum_wall_clock_seconds: float = 0.0
    tool_call_count: int = 0


class TokenLedger:
    """Mutable per-subagent token meter.

    Thread-safe (the runner uses one ledger per task; consumers should
    not share across threads).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._input: int = 0
        self._output: int = 0

    def add_input(self, n: int) -> None:
        if n <= 0:
            return
        with self._lock:
            self._input += n

    def add_output(self, n: int) -> None:
        if n <= 0:
            return
        with self._lock:
            self._output += n

    @property
    def input_tokens(self) -> int:
        with self._lock:
            return self._input

    @property
    def output_tokens(self) -> int:
        with self._lock:
            return self._output


class ToolGuard:
    """Per-subagent tool whitelist enforcer.

    The runner constructs one of these per task and passes it to the
    body. The body invokes tools through :meth:`invoke`, which
    delegates to a caller-supplied dispatcher only when the tool is on
    the whitelist; otherwise raises :class:`ToolNotPermittedError`.

    Args:
        whitelist: iterable of permitted tool names.
        dispatcher: callable that actually invokes a permitted tool.
            Signature: ``dispatcher(name: str, params: Mapping)``.
            Returns whatever the tool returns; the guard merely
            records the invocation.
    """

    def __init__(
        self,
        *,
        whitelist: Iterable[str],
        dispatcher: Callable[[str, Mapping[str, Any]], Any],
    ) -> None:
        self._whitelist: frozenset[str] = frozenset(whitelist)
        self._dispatcher = dispatcher
        self._calls: list[str] = []
        self._lock = threading.Lock()

    def is_permitted(self, name: str) -> bool:
        return name in self._whitelist

    def invoke(self, name: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        """Invoke a tool by name; raise on whitelist miss.

        Records the invocation in the per-guard call log regardless of
        outcome.
        """
        with self._lock:
            self._calls.append(name)
        if name not in self._whitelist:
            raise ToolNotPermittedError(name, self._whitelist)
        return self._dispatcher(name, dict(params) if params else {})

    @property
    def call_log(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._calls)


_DEFAULT_CLOCK: Callable[[], float] = time.monotonic


class SubagentRunner:
    """Parallel read-only subagent dispatcher with token-meter rollup.

    Args:
        dispatcher: callable that actually invokes a permitted tool
            on behalf of every subagent. Passed to each task's
            :class:`ToolGuard`. The default is a no-op that returns
            ``None``; production callers wire the orchestrator's
            tool-call dispatcher.
        default_tool_whitelist: optional override for the default
            whitelist. ``None`` keeps :data:`DEFAULT_READONLY_TOOL_WHITELIST`.
        max_parallel: max concurrent subagents. ``1`` (default)
            preserves the voice baseline contract by running serially;
            callers must opt in to true parallelism (e.g. ``2`` for
            two RAG retrieves) when VRAM + context headroom is known.
        clock: optional injectable clock; defaults to
            :func:`time.monotonic`.
    """

    def __init__(
        self,
        *,
        dispatcher: Optional[Callable[[str, Mapping[str, Any]], Any]] = None,
        default_tool_whitelist: Optional[Iterable[str]] = None,
        max_parallel: int = 1,
        clock: Callable[[], float] = _DEFAULT_CLOCK,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
        self._dispatcher = dispatcher or _noop_dispatcher
        if default_tool_whitelist is None:
            self._default_whitelist = DEFAULT_READONLY_TOOL_WHITELIST
        else:
            self._default_whitelist = frozenset(default_tool_whitelist)
        self._max_parallel = max_parallel
        self._clock = clock

    def run_batch(
        self,
        tasks: Sequence[SubagentTask],
    ) -> tuple[tuple[SubagentResult, ...], SubagentBatchStats]:
        """Dispatch ``tasks`` and return per-task results + roll-up.

        Tasks are dispatched via a :class:`ThreadPoolExecutor` with
        ``max_workers = min(max_parallel, len(tasks))``. Each task
        runs in its own thread; the runner gathers results in
        completion order then sorts by ``task_id`` for stable output.

        Returns:
            ``(results, stats)`` where results is a tuple sorted to
            match the input order (by index, not by ``task_id``).
        """
        if not tasks:
            return (), SubagentBatchStats()
        n_workers = min(self._max_parallel, len(tasks))
        results_by_index: dict[int, SubagentResult] = {}
        with ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="ultron-subagent") as pool:
            future_to_index = {
                pool.submit(self._run_one, task): idx
                for idx, task in enumerate(tasks)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 -- fail-open
                    task = tasks[idx]
                    result = SubagentResult(
                        task_id=task.task_id,
                        succeeded=False,
                        error_message=f"{exc.__class__.__name__}: {exc}",
                    )
                results_by_index[idx] = result
        ordered = tuple(results_by_index[i] for i in range(len(tasks)))
        stats = self._roll_up(ordered)
        return ordered, stats

    def _run_one(self, task: SubagentTask) -> SubagentResult:
        whitelist = (
            frozenset(task.tool_whitelist)
            if task.tool_whitelist is not None
            else self._default_whitelist
        )
        guard = ToolGuard(whitelist=whitelist, dispatcher=self._dispatcher)
        ledger = TokenLedger()
        started_at = self._clock()
        text: str = ""
        succeeded = False
        error_message: str = ""
        try:
            text = task.body(task.prompt, guard, ledger) or ""
            succeeded = True
        except Exception as exc:  # noqa: BLE001 -- fail-open per-task
            error_message = f"{exc.__class__.__name__}: {exc}"
        ended_at = self._clock()
        return SubagentResult(
            task_id=task.task_id,
            succeeded=succeeded,
            text=text,
            input_tokens=ledger.input_tokens,
            output_tokens=ledger.output_tokens,
            wall_clock_seconds=max(0.0, ended_at - started_at),
            error_message=error_message,
            tool_calls=guard.call_log,
        )

    def _roll_up(self, results: Sequence[SubagentResult]) -> SubagentBatchStats:
        n_tasks = len(results)
        n_succeeded = sum(1 for r in results if r.succeeded)
        n_failed = n_tasks - n_succeeded
        total_in = sum(r.input_tokens for r in results)
        total_out = sum(r.output_tokens for r in results)
        max_wall = max((r.wall_clock_seconds for r in results), default=0.0)
        sum_wall = sum(r.wall_clock_seconds for r in results)
        tool_count = sum(len(r.tool_calls) for r in results)
        return SubagentBatchStats(
            n_tasks=n_tasks,
            n_succeeded=n_succeeded,
            n_failed=n_failed,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            max_wall_clock_seconds=max_wall,
            sum_wall_clock_seconds=sum_wall,
            tool_call_count=tool_count,
        )


def _noop_dispatcher(name: str, params: Mapping[str, Any]) -> Any:
    """Default dispatcher: returns ``None`` for any permitted tool."""
    return None


__all__ = [
    "DEFAULT_READONLY_TOOL_WHITELIST",
    "SubagentBatchStats",
    "SubagentResult",
    "SubagentRunner",
    "SubagentTask",
    "TokenLedger",
    "ToolGuard",
    "ToolNotPermittedError",
]
