"""Tests for ultron.lifecycle.single_instance.

Hermetic: tmp_path-scoped lock files only (never the repo's
``data/`` lock, so a live Ultron on this machine cannot interfere),
monkeypatch-only mutation, no network, no voice stack, no sleeps.
"""

from __future__ import annotations

import errno
import json
import os

import pytest

from ultron.lifecycle import single_instance as si


def test_acquire_writes_metadata_and_releases(tmp_path):
    p = tmp_path / "i.lock"
    lock = si.acquire_single_instance_lock(p)
    assert lock is not None
    assert lock.mode in {"msvcrt", "fcntl", "pidfile"}
    meta = si.read_lock_metadata(p)
    assert meta is not None
    assert meta["pid"] == os.getpid()
    assert "started_at" in meta
    lock.release()
    second = si.acquire_single_instance_lock(p)
    assert second is not None
    second.release()


def test_second_acquire_returns_none_while_held(tmp_path):
    p = tmp_path / "i.lock"
    first = si.acquire_single_instance_lock(p)
    assert first is not None and first.mode in {"msvcrt", "fcntl"}
    try:
        assert si.acquire_single_instance_lock(p) is None
    finally:
        first.release()
    # After release the lock is acquirable again.
    third = si.acquire_single_instance_lock(p)
    assert third is not None
    third.release()


def test_metadata_readable_while_locked(tmp_path):
    # Pins the offset-4096 design: on Windows msvcrt locks are
    # MANDATORY, so a lock over the metadata bytes would make this
    # read fail with OSError.
    p = tmp_path / "i.lock"
    lock = si.acquire_single_instance_lock(p)
    assert lock is not None
    try:
        meta = si.read_lock_metadata(p)
        assert meta is not None and meta["pid"] == os.getpid()
    finally:
        lock.release()


def test_release_is_idempotent(tmp_path):
    p = tmp_path / "i.lock"
    lock = si.acquire_single_instance_lock(p)
    assert lock is not None
    lock.release()
    lock.release()  # second release must not raise
    again = si.acquire_single_instance_lock(p)
    assert again is not None
    again.release()


def test_is_another_instance_running(tmp_path):
    p = tmp_path / "i.lock"
    assert si.is_another_instance_running(p) is None
    holder = si.acquire_single_instance_lock(p)
    assert holder is not None
    try:
        assert si.is_another_instance_running(p) == os.getpid()
    finally:
        holder.release()
    # The probe must not leave the lock held.
    assert si.is_another_instance_running(p) is None
    reacquired = si.acquire_single_instance_lock(p)
    assert reacquired is not None
    reacquired.release()


def test_env_escape_hatch_bypasses(tmp_path, monkeypatch):
    p = tmp_path / "i.lock"
    holder = si.acquire_single_instance_lock(p)
    assert holder is not None
    try:
        monkeypatch.setenv(si.ALLOW_MULTIPLE_ENV, "1")
        dup = si.acquire_single_instance_lock(p)
        assert dup is not None and dup.mode == "bypass"
        dup.release()  # no-op; must not raise or disturb the holder
        # The holder still holds: un-set the env and contention returns.
        monkeypatch.delenv(si.ALLOW_MULTIPLE_ENV)
        assert si.acquire_single_instance_lock(p) is None
    finally:
        holder.release()


def test_pidfile_fallback_dead_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_msvcrt", None)
    monkeypatch.setattr(si, "_fcntl", None)
    monkeypatch.setattr(si, "_pid_is_running", lambda pid: False)
    p = tmp_path / "i.lock"
    p.write_text(
        json.dumps({"pid": 999_999, "started_at": "x"}) + "\n",
        encoding="utf-8",
    )
    lock = si.acquire_single_instance_lock(p)
    assert lock is not None and lock.mode == "pidfile"
    meta = si.read_lock_metadata(p)
    assert meta is not None and meta["pid"] == os.getpid()
    lock.release()


def test_pidfile_fallback_live_pid_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(si, "_msvcrt", None)
    monkeypatch.setattr(si, "_fcntl", None)
    monkeypatch.setattr(si, "_pid_is_running", lambda pid: True)
    p = tmp_path / "i.lock"
    p.write_text(
        json.dumps({"pid": os.getpid() + 1, "started_at": "x"}) + "\n",
        encoding="utf-8",
    )
    assert si.acquire_single_instance_lock(p) is None


def test_contention_oserror_from_locking_means_duplicate(
    tmp_path, monkeypatch
):
    def _raiser(*_a, **_k):
        raise OSError(errno.EACCES, "locked")

    if si._msvcrt is not None:
        monkeypatch.setattr(si._msvcrt, "locking", _raiser)
    elif si._fcntl is not None:
        monkeypatch.setattr(si._fcntl, "flock", _raiser)
    else:  # pragma: no cover - exotic platform
        pytest.skip("no locking primitive on this platform")
    assert si.acquire_single_instance_lock(tmp_path / "i.lock") is None


def test_non_contention_lock_oserror_fails_open(tmp_path, monkeypatch):
    # ENOLCK (kernel lock table exhausted / lockless filesystem) is an
    # ENVIRONMENT problem, not a duplicate -- the documented
    # refuse-only-on-contention contract demands a bypass lock here.
    def _raiser(*_a, **_k):
        raise OSError(errno.ENOLCK, "no locks available")

    if si._msvcrt is not None:
        monkeypatch.setattr(si._msvcrt, "locking", _raiser)
    elif si._fcntl is not None:
        monkeypatch.setattr(si._fcntl, "flock", _raiser)
    else:  # pragma: no cover - exotic platform
        pytest.skip("no locking primitive on this platform")
    lock = si.acquire_single_instance_lock(tmp_path / "i.lock")
    assert lock is not None and lock.mode == "bypass"
    lock.release()


def test_release_does_not_unlink_lock_file(tmp_path):
    # Removing the path after unlock opens a POSIX lock-after-unlink
    # race that can admit two instances; the file must stay behind.
    p = tmp_path / "i.lock"
    lock = si.acquire_single_instance_lock(p)
    assert lock is not None
    lock.release()
    assert p.exists()


def test_fail_open_on_broken_path(tmp_path, monkeypatch):
    def _raiser(*_a, **_k):
        raise OSError(errno.EIO, "disk on fire")

    monkeypatch.setattr(si.os, "open", _raiser)
    lock = si.acquire_single_instance_lock(tmp_path / "i.lock")
    # A broken lock path must NEVER block a legitimate start.
    assert lock is not None and lock.mode == "bypass"
    lock.release()


def test_read_lock_metadata_missing_and_corrupt(tmp_path):
    assert si.read_lock_metadata(tmp_path / "missing.lock") is None
    bad = tmp_path / "bad.lock"
    bad.write_text("not json\n", encoding="utf-8")
    assert si.read_lock_metadata(bad) is None


def test_default_lock_path_is_under_data():
    # The default anchors at <project>/data so any launch CWD shares
    # the same guard for this install.
    assert si.DEFAULT_LOCK_PATH.parent.name == "data"
    assert si.DEFAULT_LOCK_PATH.name == ".ultron_instance.lock"
