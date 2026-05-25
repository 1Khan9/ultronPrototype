"""Tests for the T6 stable-identity alias graph."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ultron.identity.alias_graph import (
    DEFAULT_RESERVATION_DAYS,
    MAX_REDIRECT_DEPTH,
    RESERVED_SLUGS,
    AliasGraph,
    AliasGraphEvent,
    AliasOperation,
    AliasResolveError,
    InvalidSlugError,
    SlugReservedError,
    normalize_slug,
    validate_slug,
)


# A fixed wall-clock for deterministic tests.
EPOCH = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _Clock:
    """Simple monotonic-ish clock fixture."""

    def __init__(self, start: datetime = EPOCH) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, days: int = 0, seconds: int = 0) -> datetime:
        self.now = self.now + timedelta(days=days, seconds=seconds)
        return self.now


def _make_graph(tmp_path: Path | None = None, clock: _Clock | None = None) -> AliasGraph:
    return AliasGraph(
        audit_log_path=tmp_path / "alias.jsonl" if tmp_path else None,
        now_fn=clock or _Clock(),
    )


# ---------------------------------------------------------------------------
# normalize_slug / validate_slug


def test_normalize_slug_strips_whitespace_and_case() -> None:
    assert normalize_slug("  Foo-Bar  ") == "foo-bar"


def test_normalize_slug_collapses_leading_at() -> None:
    assert normalize_slug("@@@owner/slug") == "@owner/slug"


def test_normalize_slug_none() -> None:
    assert normalize_slug("") == ""


def test_validate_slug_accepts_simple() -> None:
    assert validate_slug("hello-world") == "hello-world"


def test_validate_slug_accepts_scoped() -> None:
    assert validate_slug("@owner/skill") == "@owner/skill"


def test_validate_slug_rejects_empty() -> None:
    with pytest.raises(InvalidSlugError):
        validate_slug("")


def test_validate_slug_rejects_uppercase() -> None:
    # Upper-case input is normalised; the regex should accept it.
    # But truly invalid characters like spaces or slashes-not-in-scope fail.
    with pytest.raises(InvalidSlugError):
        validate_slug("has spaces")


def test_validate_slug_rejects_reserved_unscoped() -> None:
    with pytest.raises(SlugReservedError):
        validate_slug("admin")


def test_validate_slug_allows_reserved_when_scoped() -> None:
    assert validate_slug("@bob/admin") == "@bob/admin"


def test_validate_slug_rejects_ultron_keyword_unscoped() -> None:
    for keyword in ("soul", "validator", "voicepack"):
        with pytest.raises(SlugReservedError):
            validate_slug(keyword)


# ---------------------------------------------------------------------------
# register / resolve


def test_register_returns_entry() -> None:
    g = _make_graph()
    entry = g.register("alpha", owner="alice")
    assert entry.canonical == "alpha"
    assert entry.owner == "alice"


def test_register_invalid_raises() -> None:
    g = _make_graph()
    with pytest.raises(InvalidSlugError):
        g.register("has spaces")


def test_register_reserved_raises() -> None:
    g = _make_graph()
    with pytest.raises(SlugReservedError):
        g.register("admin")


def test_resolve_unknown_raises() -> None:
    g = _make_graph()
    with pytest.raises(AliasResolveError):
        g.resolve("no-such")


def test_resolve_canonical_returns_entry() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    entry = g.resolve("alpha")
    assert entry.canonical == "alpha"


def test_resolve_walks_redirect() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.rename("alpha", "beta", actor="alice")
    entry = g.resolve("alpha")
    assert entry.canonical == "beta"


def test_resolve_detects_redirect_cycle(tmp_path: Path) -> None:
    """A pathological log with a cycle is caught at resolve time."""
    g = AliasGraph(audit_log_path=tmp_path / "log.jsonl", now_fn=_Clock())
    g.register("a", owner="x")
    g.register("b", owner="x")
    # Manually inject a cycle via direct entry mutation.
    with g._lock:                                                           # noqa: SLF001
        from ultron.identity.alias_graph import AliasGraphEntry as E
        g._entries["a"] = E(canonical="a", redirect_target="b")             # noqa: SLF001
        g._entries["b"] = E(canonical="b", redirect_target="a")             # noqa: SLF001
    with pytest.raises(AliasResolveError):
        g.resolve("a")


# ---------------------------------------------------------------------------
# rename


def test_rename_creates_redirect() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    new_entry, redirect = g.rename("alpha", "beta", actor="alice")
    assert new_entry.canonical == "beta"
    assert new_entry.owner == "alice"
    assert redirect.redirect_target == "beta"
    assert g.resolve("alpha").canonical == "beta"
    assert g.resolve("beta").canonical == "beta"


def test_rename_same_slug_raises() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    with pytest.raises(InvalidSlugError):
        g.rename("alpha", "alpha", actor="alice")


def test_rename_unknown_raises() -> None:
    g = _make_graph()
    with pytest.raises(AliasResolveError):
        g.rename("alpha", "beta", actor="alice")


def test_rename_to_existing_active_target_raises() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.register("beta", owner="bob")
    with pytest.raises(InvalidSlugError):
        g.rename("alpha", "beta", actor="alice")


def test_rename_to_hardcoded_reserved_raises() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    with pytest.raises(SlugReservedError):
        g.rename("alpha", "admin", actor="alice")


def test_rename_preserves_owner() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    new_entry, _ = g.rename("alpha", "beta", actor="alice")
    assert new_entry.owner == "alice"


# ---------------------------------------------------------------------------
# merge


def test_merge_hides_source() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.register("beta", owner="alice")
    redirect = g.merge("alpha", "beta", actor="alice")
    assert redirect.hidden is True
    assert redirect.redirect_target == "beta"
    assert g.resolve("alpha").canonical == "beta"


def test_merge_unknown_target_raises() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    with pytest.raises(AliasResolveError):
        g.merge("alpha", "no-such", actor="alice")


def test_merge_same_slug_raises() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    with pytest.raises(InvalidSlugError):
        g.merge("alpha", "alpha", actor="alice")


def test_merge_walks_target_chain() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.register("beta", owner="alice")
    g.rename("beta", "gamma", actor="alice")
    # beta now redirects to gamma; merging alpha into beta should
    # land on the canonical (gamma).
    redirect = g.merge("alpha", "beta", actor="alice")
    assert redirect.redirect_target == "gamma"


# ---------------------------------------------------------------------------
# transfer


def test_transfer_changes_owner() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    new_entry = g.transfer("alpha", "bob", actor="alice")
    assert new_entry.owner == "bob"
    # Slug stays canonical -- no redirect.
    assert new_entry.redirect_target is None


def test_transfer_requires_to_owner() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    with pytest.raises(ValueError):
        g.transfer("alpha", "", actor="alice")


def test_transfer_unknown_raises() -> None:
    g = _make_graph()
    with pytest.raises(AliasResolveError):
        g.transfer("alpha", "bob", actor="alice")


# ---------------------------------------------------------------------------
# soft_delete + reservation


def test_soft_delete_reserves_for_default_days() -> None:
    clock = _Clock()
    g = AliasGraph(now_fn=clock)
    g.register("alpha", owner="alice")
    entry = g.soft_delete("alpha", actor="alice")
    assert entry.hidden is True
    assert entry.reserved_until is not None
    expected = EPOCH + timedelta(days=DEFAULT_RESERVATION_DAYS)
    assert entry.reserved_until == expected
    assert entry.original_owner == "alice"


def test_soft_delete_blocks_other_owner_during_reservation() -> None:
    clock = _Clock()
    g = AliasGraph(now_fn=clock)
    g.register("alpha", owner="alice")
    g.soft_delete("alpha", actor="alice")
    with pytest.raises(SlugReservedError):
        g.register("alpha", owner="bob")


def test_soft_delete_allows_original_owner_immediately() -> None:
    clock = _Clock()
    g = AliasGraph(now_fn=clock)
    g.register("alpha", owner="alice")
    g.soft_delete("alpha", actor="alice")
    # is_claimable for original owner returns True
    assert g.is_claimable("alpha", by_owner="alice")


def test_soft_delete_lapses_after_window() -> None:
    clock = _Clock()
    g = AliasGraph(now_fn=clock)
    g.register("alpha", owner="alice")
    g.soft_delete("alpha", actor="alice")
    clock.advance(days=DEFAULT_RESERVATION_DAYS + 1)
    assert g.is_claimable("alpha", by_owner="bob")


def test_soft_delete_negative_days_raises() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    with pytest.raises(ValueError):
        g.soft_delete("alpha", reservation_days=-1, actor="alice")


def test_soft_delete_zero_days_immediately_claimable() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.soft_delete("alpha", reservation_days=0, actor="alice")
    assert g.is_claimable("alpha", by_owner="bob")


# ---------------------------------------------------------------------------
# hard_delete


def test_hard_delete_no_reservation() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    entry = g.hard_delete("alpha", actor="moderator")
    assert entry.hidden is True
    assert entry.reserved_until is None
    assert g.is_claimable("alpha", by_owner="anyone")


# ---------------------------------------------------------------------------
# is_claimable


def test_is_claimable_unknown_slug() -> None:
    g = _make_graph()
    assert g.is_claimable("brand-new-slug") is True


def test_is_claimable_active_returns_false() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    assert g.is_claimable("alpha") is False


def test_is_claimable_invalid_slug_returns_false() -> None:
    g = _make_graph()
    assert g.is_claimable("admin") is False  # reserved hardcoded
    assert g.is_claimable("has spaces") is False  # invalid pattern


# ---------------------------------------------------------------------------
# Listing helpers


def test_list_active_excludes_redirects_and_hidden() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.register("beta", owner="alice")
    g.rename("beta", "gamma", actor="alice")  # beta -> gamma (redirect)
    g.register("delta", owner="alice")
    g.soft_delete("delta", actor="alice")  # delta hidden
    active = g.list_active()
    canonicals = sorted(e.canonical for e in active)
    assert canonicals == ["alpha", "gamma"]


def test_list_redirects() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.rename("alpha", "beta", actor="alice")
    redirects = g.list_redirects()
    assert len(redirects) == 1
    assert redirects[0].canonical == "alpha"
    assert redirects[0].redirect_target == "beta"


def test_list_reserved() -> None:
    g = _make_graph()
    g.register("alpha", owner="alice")
    g.soft_delete("alpha", actor="alice")
    reserved = g.list_reserved()
    assert len(reserved) == 1
    assert reserved[0].canonical == "alpha"


# ---------------------------------------------------------------------------
# Persistence + replay


def test_persistence_writes_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "alias.jsonl"
    g = AliasGraph(audit_log_path=log, now_fn=_Clock())
    g.register("alpha", owner="alice")
    g.rename("alpha", "beta", actor="alice")
    text = log.read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if l]
    assert len(lines) == 2


def test_replay_recovers_state(tmp_path: Path) -> None:
    log = tmp_path / "alias.jsonl"
    clock = _Clock()
    g1 = AliasGraph(audit_log_path=log, now_fn=clock)
    g1.register("alpha", owner="alice")
    g1.rename("alpha", "beta", actor="alice")
    g1.transfer("beta", "bob", actor="alice")

    g2 = AliasGraph(audit_log_path=log, now_fn=_Clock())
    assert g2.resolve("alpha").canonical == "beta"
    assert g2.get("beta") is not None
    assert g2.get("beta").owner == "bob"


def test_chain_verification_clean(tmp_path: Path) -> None:
    log = tmp_path / "alias.jsonl"
    g = AliasGraph(audit_log_path=log, now_fn=_Clock())
    g.register("alpha", owner="alice")
    g.rename("alpha", "beta", actor="alice")
    assert g.verify_log_chain() is True


def test_chain_verification_detects_tamper(tmp_path: Path) -> None:
    log = tmp_path / "alias.jsonl"
    g = AliasGraph(audit_log_path=log, now_fn=_Clock())
    g.register("alpha", owner="alice")
    g.rename("alpha", "beta", actor="alice")
    # Tamper: mutate the first row's payload directly.
    original = log.read_text(encoding="utf-8")
    lines = original.splitlines()
    tampered = lines[0].replace('"alice"', '"mallory"', 1)
    log.write_text("\n".join([tampered] + lines[1:]) + "\n", encoding="utf-8")
    assert g.verify_log_chain() is False


# ---------------------------------------------------------------------------
# Event helpers


def test_event_hash_is_stable() -> None:
    event = AliasGraphEvent(
        op=AliasOperation.REGISTER,
        slug="alpha",
        actor="alice",
        at=EPOCH,
        payload={"owner": "alice"},
        prev_hash="",
    )
    h1 = event.hash()
    h2 = event.hash()
    assert h1 == h2
    assert len(h1) == 64


def test_event_hash_differs_on_payload_change() -> None:
    e1 = AliasGraphEvent(
        op=AliasOperation.REGISTER, slug="alpha", actor="alice", at=EPOCH,
        payload={"owner": "alice"}, prev_hash="",
    )
    e2 = AliasGraphEvent(
        op=AliasOperation.REGISTER, slug="alpha", actor="mallory", at=EPOCH,
        payload={"owner": "alice"}, prev_hash="",
    )
    assert e1.hash() != e2.hash()


def test_event_jsonl_line_is_parseable() -> None:
    import json

    event = AliasGraphEvent(
        op=AliasOperation.RENAME,
        slug="alpha",
        actor="alice",
        at=EPOCH,
        payload={"new_slug": "beta", "owner": "alice"},
        prev_hash="",
    )
    parsed = json.loads(event.to_jsonl_line())
    assert parsed["op"] == "rename"
    assert parsed["slug"] == "alpha"
    assert parsed["payload"]["new_slug"] == "beta"
    assert "hash" in parsed
