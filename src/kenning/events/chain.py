"""SHA-256 hash chain helpers (T13 from the OpenHands catalog).

The chain shape ports the existing kenning safety-audit hash-chain
pattern (``src/kenning/safety/audit.py``) and generalises it to any
event sequence. Per-session chain. Each event's ``chain_hash`` is
``sha256(prev_hash || canonical_event_json(event))``; missing
``prev_hash`` (first event of the session) hashes with an empty prefix.

Use :func:`compute_event_chain_hash` at write time, :func:`verify_chain`
to walk a sequence and assert integrity. A broken link surfaces the
exact index + expected vs actual hash so ``kenning diag chain`` can
report the breakage location without re-running the whole sequence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Sequence

from kenning.events.models import StoredEvent, canonical_event_json


class ChainVerificationError(RuntimeError):
    """Raised by :func:`verify_chain` (when called with ``strict=True``)."""


@dataclass(frozen=True)
class ChainVerificationResult:
    """Outcome of a chain verification pass."""

    ok: bool
    events_checked: int
    broken_at_index: int | None = None
    broken_event_id: str | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def compute_event_chain_hash(event: StoredEvent, prev_hash: str | None) -> str:
    """Return the chain hash for ``event`` given the previous link's hash.

    The hash input is ``(prev_hash or "") || canonical_event_json(event)``.
    """

    prefix = prev_hash if prev_hash else ""
    canonical = canonical_event_json(event)
    digest = hashlib.sha256()
    digest.update(prefix.encode("utf-8"))
    digest.update(canonical.encode("utf-8"))
    return digest.hexdigest()


def verify_chain(
    events: Sequence[StoredEvent],
    *,
    strict: bool = False,
) -> ChainVerificationResult:
    """Walk the chain and assert each event's ``chain_hash`` matches.

    Args:
        events: Sequence of :class:`StoredEvent` in their canonical
            insertion order. Pass the result of ``store.search_events``
            with the default ascending sort.
        strict: When True, raises :class:`ChainVerificationError` on
            the first mismatch. Default False -- the result carries
            the diagnostic and the caller decides what to do.

    Returns:
        :class:`ChainVerificationResult` describing the walk.
    """

    prev_hash: str | None = None
    notes: list[str] = []
    for index, event in enumerate(events):
        if event.chain_hash is None:
            notes.append(f"event {index} has no chain_hash (id={event.id})")
            if strict:
                raise ChainVerificationError(notes[-1])
            return ChainVerificationResult(
                ok=False,
                events_checked=index,
                broken_at_index=index,
                broken_event_id=event.id,
                notes=tuple(notes),
            )
        expected = compute_event_chain_hash(event, prev_hash)
        if expected != event.chain_hash:
            notes.append(
                f"event {index} chain_hash mismatch (id={event.id}, "
                f"expected {expected[:12]}..., actual {event.chain_hash[:12]}...)"
            )
            if strict:
                raise ChainVerificationError(notes[-1])
            return ChainVerificationResult(
                ok=False,
                events_checked=index,
                broken_at_index=index,
                broken_event_id=event.id,
                expected_hash=expected,
                actual_hash=event.chain_hash,
                notes=tuple(notes),
            )
        if event.chain_prev_hash != prev_hash:
            notes.append(
                f"event {index} chain_prev_hash mismatch (id={event.id})"
            )
            if strict:
                raise ChainVerificationError(notes[-1])
            return ChainVerificationResult(
                ok=False,
                events_checked=index,
                broken_at_index=index,
                broken_event_id=event.id,
                expected_hash=prev_hash,
                actual_hash=event.chain_prev_hash,
                notes=tuple(notes),
            )
        prev_hash = event.chain_hash

    return ChainVerificationResult(
        ok=True,
        events_checked=len(events),
        notes=tuple(notes),
    )
