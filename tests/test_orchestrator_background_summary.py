"""2026-05-19 Tracks 1c-1e voice-loop integration tests.

Exercises Orchestrator's BackgroundSummarizer wiring without touching
the real voice stack (audio / Whisper / Llama / XTTS). Each test
builds a bare Orchestrator via ``__new__`` and stubs only the surface
the method under test actually consults.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from ultron.config import (
    LLMConfig,
    MemoryConfig,
    UltronConfig,
    set_config,
)
from ultron.memory.background_summarizer import (
    BackgroundSummarizer,
    DecisionEntry,
    FactEntry,
    PreferenceEntry,
    SummaryResult,
    TurnSnapshot,
)
from ultron.pipeline.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubMemory:
    """Minimal ConversationMemory stub. ``recent(n)`` returns canned turns."""

    def __init__(self, turns=None) -> None:
        self._turns = list(turns or [])

    def recent(self, n):
        return list(self._turns[-n:])


class _RecordingMemory(_StubMemory):
    """Stub that raises -- exercises the recent_turns_fn fail-open."""

    def recent(self, n):
        raise RuntimeError("recent() exploded")


class _StubTurn:
    def __init__(self, turn_id, role, content, ts=None):
        self.id = turn_id
        self.role = role
        self.content = content
        self.ts = ts if ts is not None else float(turn_id)


class _StubLLM:
    """Records every isolated call so tests can assert prompt routing."""

    def __init__(self, response: str = '{"summary": "stub", "facts": [], "decisions": [], "preferences": []}') -> None:
        self.response = response
        self.isolated_calls = []
        # Required attributes the loader inspects.
        self._llm = object()

    def generate_isolated(self, *, system_prompt, user_prompt, temperature=0.2, **kwargs):
        self.isolated_calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "temperature": temperature,
            **kwargs,
        })
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bare_orchestrator():
    """Construct an Orchestrator without running its full __init__.

    This skips audio device probing, model loading, etc. Tests assign
    only the attributes the method under test needs.
    """
    o = Orchestrator.__new__(Orchestrator)
    o.memory = None
    o.llm = None
    o.background_summarizer = None
    o._background_summarizer_lock = threading.Lock()
    o._background_summarizer_thread = None
    o._last_response_finished_monotonic = 0.0
    return o


@pytest.fixture
def cfg_with_summary_enabled(tmp_path, monkeypatch):
    """Push a config with memory.background_summary enabled + a tmp
    output path; restore defaults on teardown."""
    cfg = UltronConfig()
    cfg.memory.background_summary.enabled = True
    cfg.memory.background_summary.cadence_turns = 2
    cfg.memory.background_summary.min_turns = 2
    cfg.memory.background_summary.idle_threshold_seconds = 0.0
    cfg.memory.background_summary.output_path = str(
        tmp_path / "background_summaries.jsonl"
    )
    set_config(cfg)
    try:
        yield cfg
    finally:
        set_config(UltronConfig())


# ---------------------------------------------------------------------------
# _load_background_summarizer_if_enabled
# ---------------------------------------------------------------------------


def test_loader_returns_none_when_flag_off(bare_orchestrator):
    # Default config has background_summary.enabled=False.
    set_config(UltronConfig())
    bare_orchestrator.memory = _StubMemory()
    bare_orchestrator.llm = _StubLLM()
    out = Orchestrator._load_background_summarizer_if_enabled(bare_orchestrator)
    assert out is None


def test_loader_returns_none_when_memory_missing(
    bare_orchestrator, cfg_with_summary_enabled,
):
    bare_orchestrator.memory = None
    bare_orchestrator.llm = _StubLLM()
    out = Orchestrator._load_background_summarizer_if_enabled(bare_orchestrator)
    assert out is None


def test_loader_returns_none_when_llm_missing(
    bare_orchestrator, cfg_with_summary_enabled,
):
    bare_orchestrator.memory = _StubMemory()
    bare_orchestrator.llm = None
    out = Orchestrator._load_background_summarizer_if_enabled(bare_orchestrator)
    assert out is None


def test_loader_builds_summarizer_when_enabled(
    bare_orchestrator, cfg_with_summary_enabled,
):
    bare_orchestrator.memory = _StubMemory()
    bare_orchestrator.llm = _StubLLM()
    out = Orchestrator._load_background_summarizer_if_enabled(bare_orchestrator)
    assert isinstance(out, BackgroundSummarizer)


def test_loader_summarizer_calls_llm_isolated(
    bare_orchestrator, cfg_with_summary_enabled,
):
    """Verifies the wired generate_fn calls llm.generate_isolated with
    the summarizer module's system prompt -- not via .generate() which
    would inject SOUL.md."""
    turns = [_StubTurn(1, "user", "hello"), _StubTurn(2, "assistant", "hi")]
    bare_orchestrator.memory = _StubMemory(turns)
    llm = _StubLLM()
    bare_orchestrator.llm = llm
    summarizer = Orchestrator._load_background_summarizer_if_enabled(bare_orchestrator)
    assert summarizer is not None

    # force_run bypasses the gating so we can inspect the LLM call shape.
    summarizer.force_run([
        TurnSnapshot(turn_id=1, ts=1.0, role="user", content="hello"),
        TurnSnapshot(turn_id=2, ts=2.0, role="assistant", content="hi"),
    ])
    assert len(llm.isolated_calls) == 1
    call = llm.isolated_calls[0]
    assert "internal worker for the Ultron memory system" in call["system_prompt"]
    assert "Summarise the conversation below" in call["user_prompt"]
    assert "[user] hello" in call["user_prompt"]


# ---------------------------------------------------------------------------
# _build_default_background_summary_store
# ---------------------------------------------------------------------------


def test_store_returns_none_when_output_path_empty():
    store = Orchestrator._build_default_background_summary_store("")
    assert store is None


def test_store_writes_jsonl_line(tmp_path):
    target = tmp_path / "summaries.jsonl"
    store = Orchestrator._build_default_background_summary_store(str(target))
    assert store is not None

    result = SummaryResult(
        summary="The user discussed quantum entanglement at length.",
        facts=[FactEntry(subject="user", predicate="cares about", object="quantum")],
        decisions=[DecisionEntry(topic="API choice", outcome="use REST", status="made")],
        preferences=[PreferenceEntry(topic="response length", value="terse")],
        turn_id_start=10, turn_id_end=20, span_seconds=120.5,
    )
    store(result)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["summary"].startswith("The user discussed")
    assert payload["facts"][0]["subject"] == "user"
    assert payload["decisions"][0]["status"] == "made"
    assert payload["preferences"][0]["value"] == "terse"
    assert payload["turn_id_start"] == 10
    assert payload["turn_id_end"] == 20
    assert payload["span_seconds"] == pytest.approx(120.5)
    assert "ts" in payload  # write timestamp


def test_store_appends_multiple_lines(tmp_path):
    target = tmp_path / "summaries.jsonl"
    store = Orchestrator._build_default_background_summary_store(str(target))

    result_1 = SummaryResult(summary="first pass")
    result_2 = SummaryResult(summary="second pass")
    store(result_1)
    store(result_2)

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["summary"] == "first pass"
    assert json.loads(lines[1])["summary"] == "second pass"


def test_store_swallows_io_failure(tmp_path, monkeypatch):
    """Stub out the file-write so the store function hits the
    fail-open WARN path. The store should not raise."""
    target = tmp_path / "summaries.jsonl"
    store = Orchestrator._build_default_background_summary_store(str(target))

    # Monkeypatch Path.open to raise IOError on write.
    original_open = Path.open

    def _boom(self, *args, **kwargs):
        raise IOError("disk on fire")

    monkeypatch.setattr(Path, "open", _boom)
    try:
        store(SummaryResult(summary="should not propagate"))
    finally:
        monkeypatch.setattr(Path, "open", original_open)
    # File should not have been created (open was patched before mkdir).
    # The key invariant is no exception escaped.


# ---------------------------------------------------------------------------
# _maybe_run_background_summarizer
# ---------------------------------------------------------------------------


def test_maybe_run_no_op_when_summarizer_disabled(bare_orchestrator):
    bare_orchestrator.background_summarizer = None
    bare_orchestrator._last_response_finished_monotonic = 100.0
    # Should not raise; should not spawn a thread.
    bare_orchestrator._maybe_run_background_summarizer()
    assert bare_orchestrator._background_summarizer_thread is None


def test_maybe_run_skips_when_no_prior_response(bare_orchestrator):
    """Until at least one foreground turn has finished
    (_last_response_finished_monotonic > 0) the summarizer should not
    be invoked -- the idle-threshold reference point is undefined."""
    called = threading.Event()

    class _Sum:
        def maybe_summarize(self, *, last_activity_monotonic):
            called.set()

        def cancel(self):
            pass

    bare_orchestrator.background_summarizer = _Sum()
    bare_orchestrator._last_response_finished_monotonic = 0.0
    bare_orchestrator._maybe_run_background_summarizer()
    # Give the spawned thread (if any) a chance to land.
    time.sleep(0.05)
    assert not called.is_set()
    assert bare_orchestrator._background_summarizer_thread is None


def test_maybe_run_spawns_thread_calling_maybe_summarize(bare_orchestrator):
    called = threading.Event()
    captured = {}

    class _Sum:
        def maybe_summarize(self, *, last_activity_monotonic):
            captured["last_activity"] = last_activity_monotonic
            called.set()

        def cancel(self):
            pass

    bare_orchestrator.background_summarizer = _Sum()
    bare_orchestrator._last_response_finished_monotonic = 42.5
    bare_orchestrator._maybe_run_background_summarizer()
    assert called.wait(timeout=2.0), "summarizer thread did not run"
    assert captured["last_activity"] == 42.5


def test_maybe_run_short_circuits_when_thread_alive(bare_orchestrator):
    """If a previous summarizer thread is still alive, the next
    invocation must not spawn a second one."""
    running = threading.Event()
    release = threading.Event()
    call_count = {"n": 0}

    class _Sum:
        def maybe_summarize(self, *, last_activity_monotonic):
            call_count["n"] += 1
            running.set()
            release.wait(timeout=2.0)

        def cancel(self):
            release.set()

    bare_orchestrator.background_summarizer = _Sum()
    bare_orchestrator._last_response_finished_monotonic = 1.0

    bare_orchestrator._maybe_run_background_summarizer()
    assert running.wait(timeout=2.0)
    # Second call while the first is still alive should be a no-op.
    bare_orchestrator._maybe_run_background_summarizer()
    # Let the first call finish.
    release.set()
    bare_orchestrator._background_summarizer_thread.join(timeout=2.0)
    assert call_count["n"] == 1


def test_maybe_run_swallows_summarizer_exception(bare_orchestrator):
    """A summarizer that raises should not propagate to the caller --
    the next attempt will simply try again."""
    finished = threading.Event()

    class _Sum:
        def maybe_summarize(self, *, last_activity_monotonic):
            try:
                raise RuntimeError("summarizer kaboom")
            finally:
                finished.set()

        def cancel(self):
            pass

    bare_orchestrator.background_summarizer = _Sum()
    bare_orchestrator._last_response_finished_monotonic = 1.0
    bare_orchestrator._maybe_run_background_summarizer()
    assert finished.wait(timeout=2.0)
    # Thread reference is set even though it raised inside.
    bare_orchestrator._background_summarizer_thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# _cancel_background_summarizer
# ---------------------------------------------------------------------------


def test_cancel_no_op_when_summarizer_disabled(bare_orchestrator):
    bare_orchestrator.background_summarizer = None
    # Must not raise.
    bare_orchestrator._cancel_background_summarizer()


def test_cancel_invokes_summarizer_cancel(bare_orchestrator):
    cancel_called = []

    class _Sum:
        def cancel(self):
            cancel_called.append(True)

    bare_orchestrator.background_summarizer = _Sum()
    bare_orchestrator._cancel_background_summarizer()
    assert cancel_called == [True]


def test_cancel_swallows_exception(bare_orchestrator):
    class _Sum:
        def cancel(self):
            raise RuntimeError("cancel kaboom")

    bare_orchestrator.background_summarizer = _Sum()
    # Must not raise.
    bare_orchestrator._cancel_background_summarizer()


# ---------------------------------------------------------------------------
# Integration: recent_turns_fn handles memory exceptions
# ---------------------------------------------------------------------------


def test_recent_turns_fn_fail_open_when_memory_raises(
    bare_orchestrator, cfg_with_summary_enabled,
):
    bare_orchestrator.memory = _RecordingMemory()
    bare_orchestrator.llm = _StubLLM()
    summarizer = Orchestrator._load_background_summarizer_if_enabled(bare_orchestrator)
    assert summarizer is not None
    # Calling force_run with no turns short-circuits cleanly; we want
    # to verify the wired callback didn't propagate the memory
    # exception when it ran.
    result = summarizer.force_run(None)
    assert result is None
