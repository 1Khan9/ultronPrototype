"""Tests for the T11 pinning primitive."""

from __future__ import annotations

from pathlib import Path

import pytest

from kenning.install.lockfile import (
    LockfileEntry,
    read_lockfile,
    write_lockfile,
    Lockfile,
)
from kenning.install.pin import (
    KENNING_DEFAULT_PINS,
    UnpinNotPinnedError,
    is_default_pin,
    is_pinned,
    list_pinned,
    materialise_default_pins,
    pin,
    refuses_update,
    unpin,
)


# ---------------------------------------------------------------------------
# is_pinned / list_pinned


def test_is_pinned_unknown_slug_returns_false(tmp_path: Path) -> None:
    pinned, reason = is_pinned(tmp_path, "no-such-slug")
    assert pinned is False
    assert reason is None


def test_is_pinned_after_pin(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="anchored")
    pinned, reason = is_pinned(tmp_path, "alpha")
    assert pinned is True
    assert reason == "anchored"


def test_list_pinned_includes_only_pinned(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="r1")
    pin(tmp_path, "beta", reason="r2")
    # Pre-register an unpinned entry in the lockfile.
    lockfile = read_lockfile(tmp_path)
    lockfile = lockfile.with_entry(
        "gamma", LockfileEntry(version="0.1", installed_at=42)
    )
    write_lockfile(tmp_path, lockfile)

    listed = list_pinned(tmp_path)
    assert listed == {"alpha": "r1", "beta": "r2"}


# ---------------------------------------------------------------------------
# pin


def test_pin_creates_entry_when_missing(tmp_path: Path) -> None:
    result = pin(tmp_path, "alpha", reason="frozen")
    assert result.was_pinned_before is False
    assert result.is_pinned_after is True
    assert result.reason_after == "frozen"
    assert result.idempotent_noop is False
    lockfile = read_lockfile(tmp_path)
    entry = lockfile.entry("alpha")
    assert entry is not None
    assert entry.pinned is True
    assert entry.pin_reason == "frozen"
    assert entry.installed_at > 0


def test_pin_idempotent_with_same_reason(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="frozen")
    result = pin(tmp_path, "alpha", reason="frozen")
    assert result.idempotent_noop is True
    assert result.was_pinned_before is True
    assert result.is_pinned_after is True


def test_pin_updates_reason_when_different(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="first")
    result = pin(tmp_path, "alpha", reason="second")
    assert result.idempotent_noop is False
    assert result.reason_before == "first"
    assert result.reason_after == "second"


def test_pin_strips_whitespace_reason(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="   ")
    pinned, reason = is_pinned(tmp_path, "alpha")
    assert pinned is True
    assert reason is None  # whitespace-only collapsed to None


def test_pin_without_reason(tmp_path: Path) -> None:
    pin(tmp_path, "alpha")
    pinned, reason = is_pinned(tmp_path, "alpha")
    assert pinned is True
    assert reason is None


def test_pin_preserves_existing_installed_at(tmp_path: Path) -> None:
    # Pre-create an entry with a specific installed_at.
    lockfile = read_lockfile(tmp_path)
    lockfile = lockfile.with_entry(
        "alpha", LockfileEntry(version="1.0", installed_at=12345)
    )
    write_lockfile(tmp_path, lockfile)

    pin(tmp_path, "alpha", reason="anchored")
    entry = read_lockfile(tmp_path).entry("alpha")
    assert entry is not None
    assert entry.installed_at == 12345
    assert entry.pinned is True


def test_pin_create_if_missing_false_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        pin(tmp_path, "alpha", reason="x", create_if_missing=False)


# ---------------------------------------------------------------------------
# unpin


def test_unpin_strict_rejects_unknown(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        unpin(tmp_path, "no-such")


def test_unpin_strict_rejects_already_unpinned(tmp_path: Path) -> None:
    lockfile = read_lockfile(tmp_path)
    lockfile = lockfile.with_entry(
        "alpha", LockfileEntry(version="1", installed_at=42)
    )
    write_lockfile(tmp_path, lockfile)
    with pytest.raises(UnpinNotPinnedError) as exc_info:
        unpin(tmp_path, "alpha")
    assert exc_info.value.slug == "alpha"


def test_unpin_tolerant_already_unpinned(tmp_path: Path) -> None:
    lockfile = read_lockfile(tmp_path)
    lockfile = lockfile.with_entry(
        "alpha", LockfileEntry(version="1", installed_at=42)
    )
    write_lockfile(tmp_path, lockfile)
    result = unpin(tmp_path, "alpha", tolerate_unpinned=True)
    assert result.idempotent_noop is True
    assert result.is_pinned_after is False


def test_unpin_removes_pin_state(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="anchored")
    result = unpin(tmp_path, "alpha")
    assert result.was_pinned_before is True
    assert result.is_pinned_after is False
    assert result.reason_before == "anchored"
    assert result.reason_after is None
    assert result.idempotent_noop is False
    pinned, reason = is_pinned(tmp_path, "alpha")
    assert pinned is False
    assert reason is None


def test_unpin_preserves_other_entry_fields(tmp_path: Path) -> None:
    lockfile = read_lockfile(tmp_path)
    lockfile = lockfile.with_entry(
        "alpha",
        LockfileEntry(version="1.5", installed_at=42, pinned=True, pin_reason="x"),
    )
    write_lockfile(tmp_path, lockfile)
    unpin(tmp_path, "alpha")
    entry = read_lockfile(tmp_path).entry("alpha")
    assert entry is not None
    assert entry.version == "1.5"
    assert entry.installed_at == 42


# ---------------------------------------------------------------------------
# refuses_update


def test_refuses_update_unpinned(tmp_path: Path) -> None:
    refuse, reason = refuses_update(tmp_path, "alpha")
    assert refuse is False
    assert reason is None


def test_refuses_update_pinned(tmp_path: Path) -> None:
    pin(tmp_path, "alpha", reason="frozen")
    refuse, reason = refuses_update(tmp_path, "alpha")
    assert refuse is True
    assert reason == "frozen"


# ---------------------------------------------------------------------------
# default pins


def test_is_default_pin_known() -> None:
    assert is_default_pin("voicepack:kenning")
    assert is_default_pin("llm:qwen3.5-4b")


def test_is_default_pin_unknown() -> None:
    assert not is_default_pin("random-skill")


def test_materialise_default_pins_creates_all(tmp_path: Path) -> None:
    results = materialise_default_pins(tmp_path)
    assert len(results) == len(KENNING_DEFAULT_PINS)
    for slug, reason in KENNING_DEFAULT_PINS.items():
        pinned, observed = is_pinned(tmp_path, slug)
        assert pinned is True
        assert observed == reason


def test_materialise_default_pins_idempotent(tmp_path: Path) -> None:
    first = materialise_default_pins(tmp_path)
    second = materialise_default_pins(tmp_path)
    assert all(r.idempotent_noop is False for r in first)
    assert all(r.idempotent_noop is True for r in second)
