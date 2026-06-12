"""Tests for the SHA-256 hash chain helpers (T13)."""

from __future__ import annotations

import pytest

from kenning.events.chain import (
    ChainVerificationError,
    compute_event_chain_hash,
    verify_chain,
)
from kenning.events.models import StoredEvent


def _event(session_id: str, kind: str, timestamp: float = 1.0) -> StoredEvent:
    return StoredEvent(
        id=kind,
        session_id=session_id,
        kind=kind,
        timestamp=timestamp,
        payload={"k": kind},
    )


def test_first_event_hash_uses_empty_prev():
    e = _event("s", "A")
    h = compute_event_chain_hash(e, None)
    # SHA-256 hex is 64 characters.
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_hash_chains_change_on_prev_hash_change():
    e = _event("s", "A")
    h_a = compute_event_chain_hash(e, None)
    h_b = compute_event_chain_hash(e, "deadbeef")
    assert h_a != h_b


def test_hash_chains_change_on_event_content_change():
    e1 = _event("s", "A")
    e2 = _event("s", "A2")
    assert compute_event_chain_hash(e1, None) != compute_event_chain_hash(e2, None)


def _stamp_chain(events: list[StoredEvent]) -> list[StoredEvent]:
    """Helper: build a valid chain for the input events."""
    stamped: list[StoredEvent] = []
    prev_hash: str | None = None
    for e in events:
        h = compute_event_chain_hash(e, prev_hash)
        stamped.append(e.with_chain_hashes(prev_hash=prev_hash, chain_hash=h))
        prev_hash = h
    return stamped


def test_verify_chain_happy_path():
    chain = _stamp_chain([_event("s", "A"), _event("s", "B"), _event("s", "C")])
    result = verify_chain(chain)
    assert result.ok is True
    assert result.events_checked == 3
    assert result.broken_at_index is None


def test_verify_chain_detects_broken_hash():
    chain = _stamp_chain([_event("s", "A"), _event("s", "B")])
    bad_event = chain[1].with_chain_hashes(
        prev_hash=chain[1].chain_prev_hash,
        chain_hash="0" * 64,
    )
    tampered = [chain[0], bad_event]
    result = verify_chain(tampered)
    assert result.ok is False
    assert result.broken_at_index == 1
    assert result.broken_event_id == "B"


def test_verify_chain_detects_broken_prev_hash():
    chain = _stamp_chain([_event("s", "A"), _event("s", "B")])
    bad_event = chain[1].with_chain_hashes(
        prev_hash="0" * 64,
        chain_hash=chain[1].chain_hash,
    )
    tampered = [chain[0], bad_event]
    result = verify_chain(tampered)
    assert result.ok is False
    assert result.broken_at_index == 1


def test_verify_chain_strict_raises():
    chain = _stamp_chain([_event("s", "A"), _event("s", "B")])
    bad = chain[1].with_chain_hashes(
        prev_hash=chain[1].chain_prev_hash,
        chain_hash="abc",
    )
    with pytest.raises(ChainVerificationError):
        verify_chain([chain[0], bad], strict=True)


def test_verify_chain_empty_sequence_is_ok():
    result = verify_chain([])
    assert result.ok is True
    assert result.events_checked == 0


def test_verify_chain_missing_chain_hash_flagged():
    e = _event("s", "A")  # No hashes ever stamped.
    result = verify_chain([e])
    assert result.ok is False
    assert "no chain_hash" in result.notes[0]


def test_chain_is_deterministic_across_calls():
    events = [_event("s", f"E{i}") for i in range(5)]
    stamped_a = _stamp_chain(events)
    stamped_b = _stamp_chain(events)
    assert [e.chain_hash for e in stamped_a] == [e.chain_hash for e in stamped_b]


def test_chain_is_sensitive_to_payload_change():
    base = [_event("s", "A"), _event("s", "B")]
    chain_a = _stamp_chain(base)
    mutated = [base[0], base[1].__class__(**{**base[1].__dict__, "payload": {"k": "mutated"}})]
    chain_b = _stamp_chain(mutated)
    assert chain_a[-1].chain_hash != chain_b[-1].chain_hash
