"""Tests for the T12 persistent shell-process registry."""

from __future__ import annotations

import pytest

from ultron.subprocess.process_registry import (
    DEFAULT_JOB_TTL_SECONDS,
    DEFAULT_MAX_OUTPUT_CHARS,
    DeliveryTarget,
    JobOutput,
    JobState,
    MAX_JOB_TTL_SECONDS,
    MIN_JOB_TTL_SECONDS,
    ProcessRegistry,
    SweepReport,
    _clamp_ttl,
    get_process_registry,
    reset_process_registry_for_testing,
    set_process_registry,
)


@pytest.fixture(autouse=True)
def _isolate_singleton() -> None:
    reset_process_registry_for_testing()
    yield
    reset_process_registry_for_testing()


# ----------------------------------------------------------------------
# Constants + clamping


def test_constants_match_openclaw_defaults() -> None:
    assert DEFAULT_JOB_TTL_SECONDS == 30 * 60
    assert MIN_JOB_TTL_SECONDS == 60
    assert MAX_JOB_TTL_SECONDS == 3 * 60 * 60


def test_clamp_ttl_low_value() -> None:
    assert _clamp_ttl(10) == MIN_JOB_TTL_SECONDS


def test_clamp_ttl_high_value() -> None:
    assert _clamp_ttl(MAX_JOB_TTL_SECONDS * 5) == MAX_JOB_TTL_SECONDS


def test_clamp_ttl_within_band() -> None:
    assert _clamp_ttl(300) == 300


# ----------------------------------------------------------------------
# JobOutput ring buffer


def test_joboutput_append_below_cap() -> None:
    output = JobOutput(cap_chars=100)
    output.append("hello")
    output.append(" world")
    assert output.snapshot(max_chars=100) == "hello world"


def test_joboutput_truncates_head_when_over_cap() -> None:
    output = JobOutput(cap_chars=10)
    output.append("aaaaa")
    output.append("bbbbb")
    output.append("ccccc")  # forces truncate
    snap = output.snapshot(max_chars=100)
    assert len(snap) <= 10
    assert "ccccc" in snap


def test_joboutput_snapshot_respects_max_chars() -> None:
    output = JobOutput(cap_chars=10000)
    output.append("X" * 1000)
    snap = output.snapshot(max_chars=50)
    assert len(snap) == 50


def test_joboutput_empty_returns_empty_string() -> None:
    output = JobOutput()
    assert output.snapshot() == ""


def test_joboutput_clear_resets_buffer() -> None:
    output = JobOutput()
    output.append("hi")
    output.clear()
    assert output.total_chars() == 0


# ----------------------------------------------------------------------
# ProcessRegistry register / lookup


def test_register_creates_entry() -> None:
    registry = ProcessRegistry()
    job = registry.register("j1", scope_key="s1", pid=123, command="ls")
    assert job.job_id == "j1"
    assert job.state == JobState.FOREGROUND
    assert registry.get("j1") is job


def test_register_empty_job_id_rejected() -> None:
    registry = ProcessRegistry()
    with pytest.raises(ValueError):
        registry.register("")


def test_register_replaces_existing_job() -> None:
    registry = ProcessRegistry()
    registry.register("j1", command="old")
    registry.register("j1", command="new")
    assert registry.get("j1").command == "new"


def test_register_clamps_low_ttl() -> None:
    registry = ProcessRegistry()
    job = registry.register("j1", ttl_seconds=1)
    assert job.ttl_seconds == MIN_JOB_TTL_SECONDS


def test_attach_pid_late_binds() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    assert registry.attach_pid("j1", 456) is True
    assert registry.get("j1").pid == 456


def test_attach_pid_unknown_job_returns_false() -> None:
    registry = ProcessRegistry()
    assert registry.attach_pid("missing", 1) is False


# ----------------------------------------------------------------------
# Append output


def test_append_stdout_records_chunk() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    assert registry.append_stdout("j1", "hello") is True
    snap = registry.snapshot("j1")
    assert snap.stdout == "hello"


def test_append_stderr_records_chunk() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    registry.append_stderr("j1", "boom")
    snap = registry.snapshot("j1")
    assert snap.stderr == "boom"


def test_append_unknown_job_returns_false() -> None:
    registry = ProcessRegistry()
    assert registry.append_stdout("nope", "x") is False


# ----------------------------------------------------------------------
# Lifecycle transitions


def test_mark_backgrounded_transitions_state() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    assert registry.mark_backgrounded("j1") is True
    assert registry.get("j1").state == JobState.BACKGROUNDED


def test_mark_backgrounded_only_from_foreground() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    registry.mark_backgrounded("j1")
    # Second call no-ops.
    assert registry.mark_backgrounded("j1") is False


def test_mark_exited_moves_to_finished() -> None:
    registry = ProcessRegistry()
    registry.register("j1", scope_key="s1")
    assert registry.mark_exited("j1", exit_code=0) is True
    assert registry.list_active() == ()
    finished = registry.list_finished()
    assert len(finished) == 1
    assert finished[0].job_id == "j1"
    assert finished[0].state == JobState.EXITED
    assert finished[0].exit_code == 0


def test_mark_killed_moves_to_finished_with_kill_state() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    registry.mark_killed("j1", exit_code=-15)
    finished = registry.list_finished()
    assert finished[0].state == JobState.KILLED


def test_mark_exited_unknown_returns_false() -> None:
    registry = ProcessRegistry()
    assert registry.mark_exited("missing", exit_code=0) is False


# ----------------------------------------------------------------------
# Scope-keyed listing


def test_list_active_filters_by_scope_key() -> None:
    registry = ProcessRegistry()
    registry.register("a", scope_key="alpha")
    registry.register("b", scope_key="beta")
    registry.register("c", scope_key="alpha")
    alpha = registry.list_active(scope_key="alpha")
    assert {r.job_id for r in alpha} == {"a", "c"}


def test_list_active_no_filter_returns_all() -> None:
    registry = ProcessRegistry()
    registry.register("a")
    registry.register("b")
    assert {r.job_id for r in registry.list_active()} == {"a", "b"}


def test_list_finished_filters_by_scope() -> None:
    registry = ProcessRegistry()
    registry.register("a", scope_key="alpha")
    registry.register("b", scope_key="beta")
    registry.mark_exited("a", exit_code=0)
    registry.mark_exited("b", exit_code=0)
    out = registry.list_finished(scope_key="alpha")
    assert [r.job_id for r in out] == ["a"]


# ----------------------------------------------------------------------
# Snapshot


def test_snapshot_returns_output_and_state() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    registry.append_stdout("j1", "out")
    registry.append_stderr("j1", "err")
    snap = registry.snapshot("j1")
    assert snap is not None
    assert snap.stdout == "out"
    assert snap.stderr == "err"
    assert snap.is_finished is False


def test_snapshot_finished_marks_is_finished() -> None:
    registry = ProcessRegistry()
    registry.register("j1")
    registry.mark_exited("j1", exit_code=0)
    snap = registry.snapshot("j1")
    assert snap is not None and snap.is_finished is True


def test_snapshot_unknown_returns_none() -> None:
    registry = ProcessRegistry()
    assert registry.snapshot("missing") is None


# ----------------------------------------------------------------------
# Exit notification


def test_mark_exited_invokes_subclass_hook(caplog) -> None:
    registry = ProcessRegistry()
    target = DeliveryTarget(channel="voice", handler="callback")
    registry.register("j1", notify_on_exit=target)
    with caplog.at_level("INFO", logger="ultron.subprocess.process_registry"):
        registry.mark_exited("j1", exit_code=0)
    assert any("voice" in record.message for record in caplog.records)


# ----------------------------------------------------------------------
# TTL sweep


def test_sweep_ttl_kills_backgrounded_past_deadline() -> None:
    kills: list[int] = []
    clock_value = {"t": 0.0}

    def clock() -> float:
        return clock_value["t"]

    def fake_kill(pid: int) -> None:
        kills.append(pid)

    registry = ProcessRegistry(
        default_ttl_seconds=60,
        clock=clock,
        kill_callable=fake_kill,
    )
    registry.register("j1", pid=100)
    registry.mark_backgrounded("j1")
    clock_value["t"] = 200  # well past TTL
    report = registry.sweep_ttl()
    assert report.killed_for_ttl == 1
    assert kills == [100]
    finished = registry.list_finished()
    assert finished and finished[0].state == JobState.KILLED


def test_sweep_ttl_ignores_foreground_jobs() -> None:
    registry = ProcessRegistry(default_ttl_seconds=60)
    registry.register("fg")  # foreground, never backgrounded
    report = registry.sweep_ttl()
    assert report.killed_for_ttl == 0


def test_sweep_ttl_no_kill_callable_still_moves_to_finished() -> None:
    clock_value = {"t": 0.0}

    def clock() -> float:
        return clock_value["t"]

    registry = ProcessRegistry(default_ttl_seconds=60, clock=clock)
    registry.register("j1", pid=200)
    registry.mark_backgrounded("j1")
    clock_value["t"] = 1000
    report = registry.sweep_ttl()
    assert report.moved_to_finished == 1


# ----------------------------------------------------------------------
# Singleton


def test_get_process_registry_returns_singleton() -> None:
    a = get_process_registry()
    b = get_process_registry()
    assert a is b


def test_set_process_registry_replaces() -> None:
    custom = ProcessRegistry()
    set_process_registry(custom)
    assert get_process_registry() is custom


def test_reset_process_registry_drops_singleton() -> None:
    a = get_process_registry()
    reset_process_registry_for_testing()
    assert get_process_registry() is not a


# ----------------------------------------------------------------------
# Clear (test helper)


def test_clear_drops_running_and_finished() -> None:
    registry = ProcessRegistry()
    registry.register("a")
    registry.register("b")
    registry.mark_exited("b", exit_code=0)
    registry.clear()
    assert registry.list_active() == ()
    assert registry.list_finished() == ()
