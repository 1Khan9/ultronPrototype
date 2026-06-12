"""Unit tests for ConversationMemory's local-mode lock-race retry.

The embedded (local-mode) Qdrant serialises access to a storage folder with
an OS-level portalocker lock. A *dead* holder releases it automatically, but a
sibling process that is mid-shutdown can still hold it for a few hundred ms,
which surfaces as "Storage folder ... is already accessed by another instance"
on open. ``_open_client_with_retry`` rides out that release race so a transient
collision no longer silently degrades memory to disabled.

These tests exercise the retry method in isolation -- no embedder, no model
load, no real Qdrant -- by binding it onto a tiny stub carrying just the
attributes the method reads. Backoff is forced to 0 so the suite stays fast.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kenning.errors import QdrantUnavailableError
from kenning.memory.qdrant_store import ConversationMemory


class _Stub:
    """Minimal carrier for the attributes ``_open_client_with_retry`` reads."""

    path = Path("X:/does-not-matter")
    _OPEN_RETRIES = 4
    _OPEN_BACKOFF_S = 0.0  # no real sleeping in tests
    _open_client_with_retry = ConversationMemory._open_client_with_retry


def _locked_then_ok(succeed_on: int):
    """Return a fake client class that raises the lock error until the
    ``succeed_on``-th attempt, then returns a sentinel."""
    state = {"calls": 0}

    class _FakeClient:
        def __init__(self, path):
            state["calls"] += 1
            if state["calls"] < succeed_on:
                raise RuntimeError(
                    f"Storage folder {path} is already accessed by another instance"
                )

    return _FakeClient, state


def test_succeeds_after_transient_lock():
    """A lock that clears within the retry budget yields a live client."""
    stub = _Stub()
    fake_cls, state = _locked_then_ok(succeed_on=3)
    client = stub._open_client_with_retry(fake_cls)
    assert isinstance(client, fake_cls)
    assert state["calls"] == 3  # failed twice, succeeded on the third


def test_first_attempt_happy_path():
    """No contention -> opens on the very first try, no retries."""
    stub = _Stub()
    fake_cls, state = _locked_then_ok(succeed_on=1)
    client = stub._open_client_with_retry(fake_cls)
    assert isinstance(client, fake_cls)
    assert state["calls"] == 1


def test_persistent_lock_raises_qdrant_unavailable():
    """A holder that never releases surfaces as QdrantUnavailableError after
    exhausting the budget (callers then degrade memory gracefully)."""
    stub = _Stub()
    # succeed_on far beyond the retry budget -> always locked.
    fake_cls, state = _locked_then_ok(succeed_on=999)
    with pytest.raises(QdrantUnavailableError) as ei:
        stub._open_client_with_retry(fake_cls)
    assert state["calls"] == _Stub._OPEN_RETRIES  # exhausted every attempt
    assert "locked by another live instance" in str(ei.value)
    # The original lock error is chained for diagnostics.
    assert isinstance(ei.value.__cause__, RuntimeError)


def test_non_lock_error_surfaces_immediately():
    """A non-lock failure (corrupt storage, bad path) must NOT be retried --
    it surfaces on the first attempt so real problems aren't masked."""
    stub = _Stub()
    state = {"calls": 0}

    class _BadClient:
        def __init__(self, path):
            state["calls"] += 1
            raise RuntimeError("storage is corrupt: bad magic header")

    with pytest.raises(RuntimeError) as ei:
        stub._open_client_with_retry(_BadClient)
    assert "corrupt" in str(ei.value)
    assert state["calls"] == 1  # raised immediately, no retry


def test_oserror_lock_message_is_retried():
    """The lock race can also arrive as an OSError mentioning 'lock'; treat it
    the same as the RuntimeError variant."""
    stub = _Stub()
    state = {"calls": 0}

    class _LockyClient:
        def __init__(self, path):
            state["calls"] += 1
            if state["calls"] < 2:
                raise OSError("could not acquire lock on storage")

    client = stub._open_client_with_retry(_LockyClient)
    assert isinstance(client, _LockyClient)
    assert state["calls"] == 2
