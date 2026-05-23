"""Tests for :mod:`ultron.utils.snapshot_guard`."""

from __future__ import annotations

import threading
import time

import pytest

from ultron.utils.snapshot_guard import (
    SnapshotGuard,
    StaleSnapshotError,
    matches,
    take,
)


def test_take_returns_token():
    token = take([1, 2, 3])
    assert token is not None
    assert "list" in repr(token)


def test_matches_true_when_unchanged():
    state = [1, 2, 3]
    token = take(state)
    assert matches(token, state) is True


def test_matches_false_after_mutation():
    state = [1, 2, 3]
    token = take(state)
    state.append(4)
    assert matches(token, state) is False


def test_matches_with_separate_equal_object():
    """Comparison is by ==, so a fresh equal list still matches."""
    state = [1, 2, 3]
    token = take(state)
    other = [1, 2, 3]
    assert matches(token, other) is True


def test_matches_with_dict():
    state = {"a": 1, "b": [2, 3]}
    token = take(state)
    assert matches(token, state) is True
    state["b"].append(4)
    assert matches(token, state) is False


def test_matches_rejects_non_token():
    with pytest.raises(TypeError):
        matches("not-a-token", [1, 2, 3])  # type: ignore[arg-type]


def test_deepcopy_isolates_snapshot():
    state = [[1], [2], [3]]
    token = take(state)
    # Mutating the inner list of the live state must not bleed into the snapshot.
    state[0].append(99)
    assert matches(token, state) is False


def test_shallow_mode():
    state = [1, 2, 3]
    token = take(state, deep=False)
    state.append(4)
    # With shallow copy of a list, the snapshot is also a list — still
    # captures the value at capture time.
    assert matches(token, state) is False


def test_guard_snapshot_unchanged():
    state = [1, 2]
    guard = SnapshotGuard()
    guard.snapshot("key", state)
    assert guard.unchanged("key", state) is True


def test_guard_snapshot_changed():
    state = [1, 2]
    guard = SnapshotGuard()
    guard.snapshot("key", state)
    state.append(3)
    assert guard.unchanged("key", state) is False


def test_guard_unknown_key_returns_false():
    guard = SnapshotGuard()
    assert guard.unchanged("never-set", [1]) is False


def test_guard_require_raises_on_stale():
    state = [1, 2]
    guard = SnapshotGuard()
    guard.snapshot("k", state)
    state.append(99)
    with pytest.raises(StaleSnapshotError):
        guard.require("k", state)


def test_guard_drop_forgets_snapshot():
    guard = SnapshotGuard()
    guard.snapshot("k", [1, 2])
    guard.drop("k")
    assert not guard.has("k")
    assert guard.unchanged("k", [1, 2]) is False


def test_guard_clear_drops_all():
    guard = SnapshotGuard()
    guard.snapshot("a", [1])
    guard.snapshot("b", [2])
    guard.clear()
    assert len(guard) == 0


def test_guard_overwrites_on_resnapshot():
    state = [1, 2]
    guard = SnapshotGuard()
    guard.snapshot("k", state)
    state.append(3)
    guard.snapshot("k", state)  # re-capture with mutated value
    assert guard.unchanged("k", state) is True


def test_guard_thread_safety_smoke():
    """Concurrent snapshot/check across threads must not crash."""
    guard = SnapshotGuard()
    errors: list[BaseException] = []

    def worker(name: int) -> None:
        try:
            for i in range(50):
                guard.snapshot(f"k{name}", [name, i])
                guard.unchanged(f"k{name}", [name, i])
                guard.drop(f"k{name}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert errors == []


def test_aider_summarize_pattern():
    """End-to-end test of the canonical race-protection pattern.

    Foreground starts background work against a snapshot. Foreground
    mutates state while background runs. On completion, the
    snapshot mismatch must be visible so the background's result is
    discarded.
    """
    state = {"messages": [{"role": "user", "content": "hi"}]}
    guard = SnapshotGuard()
    guard.snapshot("summary_job", state)

    background_done = threading.Event()

    def background() -> None:
        # Simulate work taking a small slice of time.
        time.sleep(0.02)
        background_done.set()

    t = threading.Thread(target=background)
    t.start()

    # Foreground appends another message before background finishes.
    state["messages"].append({"role": "assistant", "content": "hello"})

    t.join(timeout=2)
    assert background_done.is_set()
    # Background "result" should be discarded because state changed.
    assert guard.unchanged("summary_job", state) is False
