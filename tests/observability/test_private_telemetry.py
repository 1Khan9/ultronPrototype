"""Tests for the T15 privacy-by-construction telemetry primitives."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kenning.observability.private_telemetry import (
    DEFAULT_STALE_DAYS,
    HashedEvent,
    HashedRootId,
    HashedSkillId,
    PrivateMetricsStore,
    RawPathLeakError,
    SAFE_ATTRIBUTE_KEYS,
    TELEMETRY_ENABLE_ENV,
    TELEMETRY_ENABLE_OPT_IN_TOKEN,
    TELEMETRY_EVENTS_FILENAME,
    canonical_label_root,
    hash_root,
    hash_skill_slug,
    is_telemetry_enabled,
    stale_root_ids,
)


EPOCH = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _telemetry_env_on() -> dict[str, str]:
    return {TELEMETRY_ENABLE_ENV: TELEMETRY_ENABLE_OPT_IN_TOKEN}


# ---------------------------------------------------------------------------
# is_telemetry_enabled


def test_telemetry_disabled_by_default() -> None:
    assert not is_telemetry_enabled({})


def test_telemetry_disabled_when_other_value() -> None:
    assert not is_telemetry_enabled({TELEMETRY_ENABLE_ENV: "1"})
    assert not is_telemetry_enabled({TELEMETRY_ENABLE_ENV: "on"})
    assert not is_telemetry_enabled({TELEMETRY_ENABLE_ENV: "yes"})


def test_telemetry_enabled_with_opt_in_token() -> None:
    assert is_telemetry_enabled({TELEMETRY_ENABLE_ENV: "opt-in"})
    # Case-insensitive
    assert is_telemetry_enabled({TELEMETRY_ENABLE_ENV: "Opt-In"})


def test_telemetry_disabled_when_disable_legacy_set() -> None:
    """Even the legacy KENNING_DISABLE_TELEMETRY=1 leaves telemetry off."""
    assert not is_telemetry_enabled({"KENNING_DISABLE_TELEMETRY": "1"})


# ---------------------------------------------------------------------------
# hash_root


def test_hash_root_returns_64_hex(tmp_path: Path) -> None:
    h = hash_root(r"C:\STC\ultronPrototype", project_root=tmp_path)
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_root_stable(tmp_path: Path) -> None:
    """Same path hashes to the same value within the same install."""
    a = hash_root(r"C:\STC\ultronPrototype", project_root=tmp_path)
    b = hash_root(r"C:\STC\ultronPrototype", project_root=tmp_path)
    assert a == b


def test_hash_root_case_insensitive_and_slash_invariant(tmp_path: Path) -> None:
    """Drive case + slash direction normalised before hashing."""
    a = hash_root(r"C:\STC\ultronPrototype", project_root=tmp_path)
    b = hash_root("c:/stc/ultronprototype", project_root=tmp_path)
    assert a == b


def test_hash_root_trailing_slash_stripped(tmp_path: Path) -> None:
    a = hash_root(r"C:\STC\ultronPrototype", project_root=tmp_path)
    b = hash_root(r"C:\STC\ultronPrototype\\", project_root=tmp_path)
    assert a == b


def test_hash_root_different_installs_different_hash(tmp_path: Path) -> None:
    """Salt per install means different project_root values diverge."""
    install_a = tmp_path / "install_a"
    install_b = tmp_path / "install_b"
    install_a.mkdir()
    install_b.mkdir()
    a = hash_root(r"C:\STC\ultronPrototype", project_root=install_a)
    b = hash_root(r"C:\STC\ultronPrototype", project_root=install_b)
    assert a != b


def test_hash_root_empty_returns_zero_hash(tmp_path: Path) -> None:
    assert hash_root("", project_root=tmp_path) == "0" * 64
    assert hash_root("   ", project_root=tmp_path) == "0" * 64


def test_hash_root_different_paths_different_hash(tmp_path: Path) -> None:
    a = hash_root(r"C:\STC\ultronPrototype", project_root=tmp_path)
    b = hash_root(r"C:\Users\me", project_root=tmp_path)
    assert a != b


# ---------------------------------------------------------------------------
# hash_skill_slug


def test_hash_skill_slug_returns_64_hex(tmp_path: Path) -> None:
    h = hash_skill_slug("@user/example", project_root=tmp_path)
    assert len(h) == 64


def test_hash_skill_slug_different_from_root_hash(tmp_path: Path) -> None:
    """Skill + path with same string don't collide due to namespace prefix."""
    a = hash_root("@user/example", project_root=tmp_path)
    b = hash_skill_slug("@user/example", project_root=tmp_path)
    assert a != b


def test_hash_skill_slug_case_insensitive(tmp_path: Path) -> None:
    a = hash_skill_slug("@User/Example", project_root=tmp_path)
    b = hash_skill_slug("@user/example", project_root=tmp_path)
    assert a == b


def test_hash_skill_slug_empty_returns_zero_hash(tmp_path: Path) -> None:
    assert hash_skill_slug("", project_root=tmp_path) == "0" * 64


# ---------------------------------------------------------------------------
# canonical_label_root


def test_label_root_basic() -> None:
    assert canonical_label_root(r"C:\STC\ultronPrototype") == "~/STC/ultronPrototype"


def test_label_root_forward_slash() -> None:
    assert canonical_label_root("/home/user/project") == "~/user/project"


def test_label_root_trailing_slash() -> None:
    assert canonical_label_root("/home/user/project/") == "~/user/project"


def test_label_root_single_segment() -> None:
    assert canonical_label_root("project") == "~/project"


def test_label_root_empty() -> None:
    assert canonical_label_root("") == ""
    assert canonical_label_root("   ") == ""


# ---------------------------------------------------------------------------
# PrivateMetricsStore basic flow


def test_store_no_op_when_telemetry_disabled(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        env={},  # opt-in not set
    )
    root_id = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(kind="intent_fire", root_id=root_id)
    written = store.record_event(event)
    assert written is False
    assert not store.events_path.is_file()


def test_store_records_when_telemetry_enabled(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        env=_telemetry_env_on(),
    )
    root_id = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(kind="intent_fire", root_id=root_id)
    written = store.record_event(event)
    assert written is True
    assert store.events_path.is_file()
    lines = store.events_path.read_text().splitlines()
    assert len(lines) == 1


def test_store_bypass_enable_check_via_constructor(tmp_path: Path) -> None:
    """enforce_enable_check=False lets tests exercise the type-boundary
    behaviour without setting an env var."""
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    root_id = hash_root(str(tmp_path), project_root=tmp_path)
    written = store.record_event(HashedEvent(kind="x", root_id=root_id))
    assert written is True


# ---------------------------------------------------------------------------
# Type boundary: RawPathLeakError


def test_record_event_rejects_raw_path_in_root_id(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    event = HashedEvent(
        kind="x",
        root_id=HashedRootId(r"C:\STC\ultronPrototype"),  # NOT a hash
    )
    with pytest.raises(RawPathLeakError) as exc_info:
        store.record_event(event)
    assert exc_info.value.field_name == "root_id"


def test_record_event_rejects_raw_string_in_skill_id(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    valid_root = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(
        kind="x",
        root_id=valid_root,
        skill_id=HashedSkillId("@user/example"),  # not hashed
    )
    with pytest.raises(RawPathLeakError):
        store.record_event(event)


def test_record_event_rejects_long_string_attribute(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    valid_root = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(
        kind="x",
        root_id=valid_root,
        attributes={"user_text": "the user said something very revealing here"},
    )
    with pytest.raises(RawPathLeakError) as exc_info:
        store.record_event(event)
    assert "user_text" in exc_info.value.field_name


def test_record_event_accepts_safe_attribute_keys(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    valid_root = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(
        kind="x",
        root_id=valid_root,
        attributes={"outcome": "this_is_long_but_safe_key_outcome_string"},
    )
    assert store.record_event(event) is True


def test_record_event_accepts_id_suffixed_attribute(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    valid_root = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(
        kind="x",
        root_id=valid_root,
        attributes={"turn_id": "a" * 32},
    )
    assert store.record_event(event) is True


def test_record_event_accepts_short_string_attribute(tmp_path: Path) -> None:
    """Strings <=12 chars are assumed metadata-safe (no raw paths fit)."""
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    valid_root = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(
        kind="x",
        root_id=valid_root,
        attributes={"version": "1.2.3"},
    )
    assert store.record_event(event) is True


def test_record_event_accepts_numeric_attributes(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    valid_root = hash_root(str(tmp_path), project_root=tmp_path)
    event = HashedEvent(
        kind="x",
        root_id=valid_root,
        attributes={"count": 42, "confidence": 0.8, "matched": True},
    )
    assert store.record_event(event) is True


# ---------------------------------------------------------------------------
# Aggregation


def test_root_records_aggregates_per_root(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    root_a = hash_root(str(tmp_path / "a"), project_root=tmp_path)
    root_b = hash_root(str(tmp_path / "b"), project_root=tmp_path)
    store.record_event(HashedEvent(kind="x", root_id=root_a, recorded_iso="2026-01-01T00:00:00+00:00"))
    store.record_event(HashedEvent(kind="x", root_id=root_a, recorded_iso="2026-01-02T00:00:00+00:00"))
    store.record_event(HashedEvent(kind="x", root_id=root_b, recorded_iso="2026-01-03T00:00:00+00:00"))
    records = store.root_records()
    assert len(records) == 2


def test_skill_records_aggregates_pairs(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    root = hash_root(str(tmp_path), project_root=tmp_path)
    skill_a = hash_skill_slug("@u/a", project_root=tmp_path)
    skill_b = hash_skill_slug("@u/b", project_root=tmp_path)
    for _ in range(3):
        store.record_event(HashedEvent(
            kind="match",
            root_id=root,
            skill_id=skill_a,
            recorded_iso="2026-01-01T00:00:00+00:00",
        ))
    store.record_event(HashedEvent(
        kind="match",
        root_id=root,
        skill_id=skill_b,
        recorded_iso="2026-01-02T00:00:00+00:00",
    ))
    records = store.skill_records()
    by_skill = {r.skill_id: r for r in records}
    assert by_skill[skill_a].match_count == 3
    assert by_skill[skill_b].match_count == 1


def test_skill_records_tracks_last_version(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    root = hash_root(str(tmp_path), project_root=tmp_path)
    skill = hash_skill_slug("@u/a", project_root=tmp_path)
    store.record_event(HashedEvent(
        kind="m",
        root_id=root,
        skill_id=skill,
        attributes={"version": "1.0.0"},
        recorded_iso="2026-01-01T00:00:00+00:00",
    ))
    store.record_event(HashedEvent(
        kind="m",
        root_id=root,
        skill_id=skill,
        attributes={"version": "2.0.0"},
        recorded_iso="2026-02-01T00:00:00+00:00",
    ))
    records = store.skill_records()
    assert records[0].last_version == "2.0.0"


# ---------------------------------------------------------------------------
# Deletion


def test_delete_all_removes_file(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    root = hash_root(str(tmp_path), project_root=tmp_path)
    store.record_event(HashedEvent(kind="x", root_id=root))
    assert store.events_path.is_file()
    store.delete_all()
    assert not store.events_path.is_file()


def test_delete_all_is_idempotent(tmp_path: Path) -> None:
    store = PrivateMetricsStore(project_root=tmp_path)
    # No events ever recorded; delete should still no-op.
    store.delete_all()


# ---------------------------------------------------------------------------
# Staleness


def test_stale_root_ids_returns_old_roots(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    fresh = hash_root(str(tmp_path / "fresh"), project_root=tmp_path)
    stale = hash_root(str(tmp_path / "stale"), project_root=tmp_path)
    now = EPOCH
    fresh_iso = now.isoformat()
    stale_iso = (now - timedelta(days=DEFAULT_STALE_DAYS + 1)).isoformat()
    store.record_event(HashedEvent(kind="x", root_id=fresh, recorded_iso=fresh_iso))
    store.record_event(HashedEvent(kind="x", root_id=stale, recorded_iso=stale_iso))
    result = stale_root_ids(store, now=now)
    assert stale in result
    assert fresh not in result


def test_stale_root_ids_empty_when_all_fresh(tmp_path: Path) -> None:
    store = PrivateMetricsStore(
        project_root=tmp_path,
        enforce_enable_check=False,
    )
    root = hash_root(str(tmp_path), project_root=tmp_path)
    store.record_event(
        HashedEvent(kind="x", root_id=root, recorded_iso=EPOCH.isoformat())
    )
    assert stale_root_ids(store, now=EPOCH) == ()


# ---------------------------------------------------------------------------
# Salt persistence


def test_salt_persists_across_store_instances(tmp_path: Path) -> None:
    """Two different stores under the same project_root use the same salt."""
    a = hash_root("/x/y", project_root=tmp_path)
    b = hash_root("/x/y", project_root=tmp_path)
    assert a == b


def test_salt_file_under_project_root(tmp_path: Path) -> None:
    hash_root("/some/path", project_root=tmp_path)
    assert (tmp_path / "data/observability/telemetry_salt.txt").is_file()


# ---------------------------------------------------------------------------
# Constants


def test_default_stale_days_is_120() -> None:
    assert DEFAULT_STALE_DAYS == 120


def test_safe_attribute_keys_has_common_metadata() -> None:
    assert "outcome" in SAFE_ATTRIBUTE_KEYS
    assert "verdict" in SAFE_ATTRIBUTE_KEYS
    assert "status" in SAFE_ATTRIBUTE_KEYS


def test_telemetry_events_file_name_constant() -> None:
    assert TELEMETRY_EVENTS_FILENAME == "private_metrics.jsonl"
