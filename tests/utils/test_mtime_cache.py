"""Tests for :mod:`ultron.utils.mtime_cache`."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ultron.utils.mtime_cache import MtimeCache, MtimeCacheError, open_mtime_cache


def test_constructor_rejects_non_path():
    with pytest.raises(MtimeCacheError):
        MtimeCache("not/a/path/object")  # type: ignore[arg-type]


def test_get_miss_returns_none(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    assert cache.get("any-key", mtime=1.0) is None


def test_set_then_get_roundtrip(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    cache.set("k1", mtime=1.0, value=["a", "b", "c"])
    assert cache.get("k1", mtime=1.0) == ["a", "b", "c"]


def test_mtime_mismatch_is_miss(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    cache.set("k1", mtime=1.0, value="payload")
    # Different mtime → treat as stale → miss.
    assert cache.get("k1", mtime=2.0) is None
    # Original mtime still returns the value.
    assert cache.get("k1", mtime=1.0) == "payload"


def test_delete_removes_entry(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    cache.set("k1", mtime=1.0, value=1)
    cache.delete("k1")
    assert cache.get("k1", mtime=1.0) is None


def test_clear_drops_all(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    cache.set("k1", mtime=1.0, value=1)
    cache.set("k2", mtime=2.0, value=2)
    cache.clear()
    assert cache.get("k1", mtime=1.0) is None
    assert cache.get("k2", mtime=2.0) is None


def test_dict_mode_when_prefer_disk_false(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache", prefer_disk=False)
    assert cache.degraded is True
    cache.set("k1", mtime=1.0, value="hot")
    assert cache.get("k1", mtime=1.0) == "hot"


def test_versioned_directory_path(tmp_path: Path):
    cache = MtimeCache(tmp_path / "stuff", version=7)
    assert cache.path.name == "stuff.v7"


def test_close_is_idempotent(tmp_path: Path):
    cache = MtimeCache(tmp_path / "cache")
    cache.close()
    cache.close()  # should not raise


def test_open_mtime_cache_convenience_constructor(tmp_path: Path):
    cache = open_mtime_cache(tmp_path / "c", version=2)
    assert isinstance(cache, MtimeCache)
    assert cache.path.name == "c.v2"


def test_real_file_roundtrip(tmp_path: Path):
    """Integration: read mtime from disk, cache, mutate, miss."""
    cache = MtimeCache(tmp_path / "cache")
    target = tmp_path / "target.py"
    target.write_text("print('v1')")
    mt = target.stat().st_mtime
    cache.set(str(target), mtime=mt, value="parsed-v1")
    assert cache.get(str(target), mtime=mt) == "parsed-v1"
    # Force a later mtime; cache should treat as miss.
    time.sleep(0.01)
    target.write_text("print('v2')")
    mt2 = target.stat().st_mtime
    if mt2 == mt:
        # Filesystem mtime resolution is coarse (Windows often 2s); force it.
        mt2 = mt + 1.0
    assert cache.get(str(target), mtime=mt2) is None
