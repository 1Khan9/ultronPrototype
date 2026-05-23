"""Tests for the per-session JSON registry (catalog T15)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from ultron.coding.session_registry import (
    SessionRegistry,
    SessionRegistryStats,
    get_session_registry,
    new_session_id,
    reset_session_registries_for_testing,
)


@pytest.fixture
def reg(tmp_path: Path) -> SessionRegistry:
    """A fresh SessionRegistry rooted under tmp_path."""
    reset_session_registries_for_testing()
    return SessionRegistry(session_id="test-session", root=tmp_path)


@pytest.fixture(autouse=True)
def _cleanup() -> None:
    yield
    reset_session_registries_for_testing()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_requires_session_id(tmp_path: Path):
    with pytest.raises(ValueError):
        SessionRegistry(session_id="", root=tmp_path)


def test_construction_strips_session_id(tmp_path: Path):
    r = SessionRegistry(session_id="  myid  ", root=tmp_path)
    assert r.session_id == "myid"
    assert r.path.parent.name == "myid"


def test_construction_uses_default_root_when_none(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "ultron.coding.session_registry.DEFAULT_REGISTRY_ROOT", tmp_path / "sessions"
    )
    r = SessionRegistry(session_id="abc")
    # When root=None we still get a fully-qualified path under the
    # patched default.
    assert r.path.parent.parent.name == "sessions"


# ---------------------------------------------------------------------------
# Basic dict-like surface
# ---------------------------------------------------------------------------


def test_set_then_get_value(reg: SessionRegistry):
    reg["foo"] = "bar"
    assert reg["foo"] == "bar"


def test_get_missing_returns_default(reg: SessionRegistry):
    assert reg.get("missing") is None
    assert reg.get("missing", default="DEFAULT") == "DEFAULT"


def test_contains_membership(reg: SessionRegistry):
    assert "foo" not in reg
    reg["foo"] = 1
    assert "foo" in reg


def test_len_counts_keys(reg: SessionRegistry):
    assert len(reg) == 0
    reg["a"] = 1
    reg["b"] = 2
    assert len(reg) == 2


def test_keys_returns_sorted_snapshot(reg: SessionRegistry):
    reg["b"] = 1
    reg["a"] = 2
    reg["c"] = 3
    assert reg.keys() == ["a", "b", "c"]


def test_pop_removes_and_returns_value(reg: SessionRegistry):
    reg["foo"] = "bar"
    assert reg.pop("foo") == "bar"
    assert "foo" not in reg


def test_pop_missing_raises_without_default(reg: SessionRegistry):
    with pytest.raises(KeyError):
        reg.pop("missing")


def test_pop_missing_with_default_returns_default(reg: SessionRegistry):
    assert reg.pop("missing", default="X") == "X"


def test_clear_drops_all(reg: SessionRegistry):
    reg["a"] = 1
    reg["b"] = 2
    reg.clear()
    assert len(reg) == 0


def test_update_bulk_set(reg: SessionRegistry):
    reg.update({"x": 1, "y": 2, "z": 3})
    assert reg["x"] == 1
    assert reg["y"] == 2
    assert reg["z"] == 3


def test_update_empty_dict_noop(reg: SessionRegistry):
    reg.update({})
    assert len(reg) == 0


# ---------------------------------------------------------------------------
# Disk persistence
# ---------------------------------------------------------------------------


def test_set_persists_to_disk(reg: SessionRegistry):
    reg["k"] = "v"
    raw = reg.path.read_text(encoding="utf-8")
    assert json.loads(raw)["k"] == "v"


def test_reload_picks_up_external_changes(reg: SessionRegistry):
    reg["k"] = "initial"
    # Simulate another process editing the file.
    reg.path.write_text(
        json.dumps({"k": "external"}), encoding="utf-8"
    )
    reg.reload()
    assert reg["k"] == "external"


def test_atomic_write_uses_temp_file(reg: SessionRegistry):
    reg["k"] = "v"
    # No leftover .tmp files in the directory.
    tmps = list(reg.path.parent.glob(".registry.*.tmp"))
    assert tmps == []


def test_load_from_corrupt_json_resets_to_empty(tmp_path: Path):
    p = tmp_path / "corrupt" / "registry.json"
    p.parent.mkdir(parents=True)
    p.write_text("this is not json {{{", encoding="utf-8")
    r = SessionRegistry(session_id="corrupt", root=tmp_path)
    assert r.get("anything") is None
    assert r.stats().corrupt_file_recoveries == 1


def test_load_from_non_object_json_resets_to_empty(tmp_path: Path):
    p = tmp_path / "arr" / "registry.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    r = SessionRegistry(session_id="arr", root=tmp_path)
    assert r.get("anything") is None
    assert r.stats().corrupt_file_recoveries == 1


def test_load_from_empty_file_returns_empty(tmp_path: Path):
    p = tmp_path / "empty" / "registry.json"
    p.parent.mkdir(parents=True)
    p.write_text("", encoding="utf-8")
    r = SessionRegistry(session_id="empty", root=tmp_path)
    assert len(r) == 0


# ---------------------------------------------------------------------------
# Env fallback (SWE-Agent semantics)
# ---------------------------------------------------------------------------


def test_env_fallback_hits_when_key_missing(reg: SessionRegistry, monkeypatch):
    monkeypatch.setenv("ULTRON_TEST_FALLBACK", "from-env")
    assert reg.get("ULTRON_TEST_FALLBACK") == "from-env"
    assert reg.stats().env_fallback_hits == 1


def test_env_fallback_disabled_returns_default(reg: SessionRegistry, monkeypatch):
    monkeypatch.setenv("ULTRON_TEST_FALLBACK", "from-env")
    assert reg.get("ULTRON_TEST_FALLBACK", default="DEFAULT", fallback_to_env=False) == "DEFAULT"
    assert reg.stats().env_fallback_hits == 0


def test_stored_value_wins_over_env(reg: SessionRegistry, monkeypatch):
    monkeypatch.setenv("ULTRON_TEST_KEY", "from-env")
    reg["ULTRON_TEST_KEY"] = "from-store"
    assert reg.get("ULTRON_TEST_KEY") == "from-store"
    assert reg.stats().env_fallback_hits == 0


def test_constructor_flag_disables_env_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ULTRON_TEST_NOENV", "from-env")
    r = SessionRegistry(session_id="noenv", root=tmp_path, fallback_to_env=False)
    assert r.get("ULTRON_TEST_NOENV", default="DEFAULT") == "DEFAULT"


# ---------------------------------------------------------------------------
# get_if_none
# ---------------------------------------------------------------------------


def test_get_if_none_returns_value_when_not_none(reg: SessionRegistry):
    reg["k"] = "from-store"
    assert reg.get_if_none("explicit", "k") == "explicit"


def test_get_if_none_falls_back_to_get_when_value_is_none(reg: SessionRegistry):
    reg["k"] = "from-store"
    assert reg.get_if_none(None, "k") == "from-store"


def test_get_if_none_returns_default_when_both_missing(reg: SessionRegistry):
    assert reg.get_if_none(None, "missing", default="DEFAULT") == "DEFAULT"


# ---------------------------------------------------------------------------
# TTL semantics
# ---------------------------------------------------------------------------


def test_set_with_ttl_value_visible_before_expiry(reg: SessionRegistry):
    reg.set_with_ttl("ephemeral", "fresh", ttl_seconds=60)
    assert reg["ephemeral"] == "fresh"


def test_set_with_ttl_value_invisible_after_expiry(
    reg: SessionRegistry, monkeypatch
):
    # Use monkeypatch on time.time so we don't actually sleep.
    base = time.time()
    monkeypatch.setattr(
        "ultron.coding.session_registry.time.time", lambda: base
    )
    reg.set_with_ttl("ephemeral", "fresh", ttl_seconds=1.0)
    assert reg["ephemeral"] == "fresh"

    # Fast-forward beyond the TTL.
    monkeypatch.setattr(
        "ultron.coding.session_registry.time.time", lambda: base + 5
    )
    assert reg.get("ephemeral", default="EVICTED") == "EVICTED"
    assert reg.stats().ttl_evictions >= 1


def test_set_with_ttl_rejects_non_positive(reg: SessionRegistry):
    with pytest.raises(ValueError):
        reg.set_with_ttl("k", "v", ttl_seconds=0)
    with pytest.raises(ValueError):
        reg.set_with_ttl("k", "v", ttl_seconds=-1)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def test_transaction_commits_on_clean_exit(reg: SessionRegistry):
    with reg.transaction():
        reg["a"] = 1
        reg["b"] = 2
    # Both committed; disk reflects them.
    on_disk = json.loads(reg.path.read_text(encoding="utf-8"))
    assert on_disk == {"a": 1, "b": 2}


def test_transaction_rolls_back_on_exception(reg: SessionRegistry):
    reg["preexisting"] = "original"
    with pytest.raises(RuntimeError):
        with reg.transaction():
            reg["preexisting"] = "modified"
            reg["new"] = "added"
            raise RuntimeError("simulate failure")
    # Rolled back: the on-disk file still has the original.
    assert reg["preexisting"] == "original"
    assert "new" not in reg
    assert reg.stats().transaction_rollbacks == 1


def test_transaction_defers_disk_writes(reg: SessionRegistry):
    # Capture the disk file content BEFORE and DURING the transaction.
    reg["seed"] = 0
    pre = reg.path.read_text(encoding="utf-8")
    with reg.transaction():
        reg["seed"] = 100
        # During the transaction the disk file should still show 0.
        mid = reg.path.read_text(encoding="utf-8")
        assert json.loads(mid)["seed"] == 0
    # After commit, the disk file reflects the new value.
    post = reg.path.read_text(encoding="utf-8")
    assert json.loads(post)["seed"] == 100
    assert pre != post


def test_nested_transactions_flatten_to_outermost(reg: SessionRegistry):
    with reg.transaction():
        reg["a"] = 1
        with reg.transaction():
            reg["b"] = 2
        reg["c"] = 3
    on_disk = json.loads(reg.path.read_text(encoding="utf-8"))
    assert on_disk == {"a": 1, "b": 2, "c": 3}


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def test_stats_returns_snapshot(reg: SessionRegistry):
    reg["x"] = 1
    _ = reg["x"]
    _ = reg.get("missing", default="d")
    s = reg.stats()
    assert isinstance(s, SessionRegistryStats)
    assert s.writes >= 1
    assert s.reads >= 2
    assert s.cache_hits >= 1
    assert s.cache_misses >= 1


def test_snapshot_returns_plain_dict(reg: SessionRegistry):
    reg["a"] = 1
    reg["b"] = "two"
    snap = reg.snapshot()
    assert isinstance(snap, dict)
    assert snap == {"a": 1, "b": "two"}


# ---------------------------------------------------------------------------
# Thread safety smoke
# ---------------------------------------------------------------------------


def test_concurrent_writes_dont_corrupt(reg: SessionRegistry):
    n_threads = 4
    n_per_thread = 25

    def worker(tid: int) -> None:
        for i in range(n_per_thread):
            reg[f"thread{tid}-key{i}"] = i

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    try:
        for t in threads:
            t.join(timeout=5.0)
    finally:
        for t in threads:
            if t.is_alive():  # pragma: no cover -- safety net
                pytest.fail(f"worker thread {t.name} hung")

    # All keys persisted.
    assert len(reg) == n_threads * n_per_thread
    # And the on-disk JSON is still valid.
    raw = reg.path.read_text(encoding="utf-8")
    assert isinstance(json.loads(raw), dict)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


def test_get_session_registry_returns_same_instance_per_id(tmp_path: Path):
    reset_session_registries_for_testing()
    a = get_session_registry("session-1", root=tmp_path)
    b = get_session_registry("session-1", root=tmp_path)
    assert a is b


def test_get_session_registry_isolates_different_ids(tmp_path: Path):
    reset_session_registries_for_testing()
    a = get_session_registry("session-1", root=tmp_path)
    b = get_session_registry("session-2", root=tmp_path)
    assert a is not b
    a["x"] = "from-a"
    assert b.get("x") is None


def test_get_session_registry_rejects_empty_id():
    with pytest.raises(ValueError):
        get_session_registry("")


def test_reset_session_registries_for_testing_clears_cache(tmp_path: Path):
    reset_session_registries_for_testing()
    a = get_session_registry("session-1", root=tmp_path)
    reset_session_registries_for_testing()
    b = get_session_registry("session-1", root=tmp_path)
    assert a is not b


def test_new_session_id_is_unique():
    a = new_session_id()
    b = new_session_id()
    assert a != b
    assert a.startswith("session-")


def test_new_session_id_accepts_custom_prefix():
    sid = new_session_id(prefix="batch")
    assert sid.startswith("batch-")


# ---------------------------------------------------------------------------
# Round-trip across instances (simulates subprocess restart)
# ---------------------------------------------------------------------------


def test_state_survives_instance_recreation(tmp_path: Path):
    reset_session_registries_for_testing()
    a = SessionRegistry(session_id="persist", root=tmp_path)
    a["k1"] = "value1"
    a["k2"] = [1, 2, 3]
    a["k3"] = {"nested": "dict"}

    # Simulate a fresh process: new instance pointing at the same path.
    b = SessionRegistry(session_id="persist", root=tmp_path)
    assert b["k1"] == "value1"
    assert b["k2"] == [1, 2, 3]
    assert b["k3"] == {"nested": "dict"}


def test_ttl_survives_serialisation_round_trip(tmp_path: Path):
    a = SessionRegistry(session_id="ttl", root=tmp_path)
    a.set_with_ttl("ephemeral", "v", ttl_seconds=60)

    b = SessionRegistry(session_id="ttl", root=tmp_path)
    # Value still visible from the new instance because the TTL hasn't
    # expired.
    assert b["ephemeral"] == "v"
