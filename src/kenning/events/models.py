"""Stored event value types + search query shape.

The :class:`StoredEvent` row carries enough metadata for queries by
kind, session, time window, and chain integrity:

* ``id`` -- UUID4 hex, unique per row.
* ``session_id`` -- owning session.
* ``kind`` -- short event-type token (the bus event class name).
* ``timestamp`` -- unix epoch seconds (monotonic-aligned at the
  publishing thread; the store may use it for ordering).
* ``payload`` -- the event's structured data (already validated by
  the producing :class:`ultron.bus.event.BusEvent`).
* ``chain_prev_hash`` / ``chain_hash`` -- T13 tamper-evidence.

The store is JSON-encodable end-to-end. The canonical encoding helper
:func:`canonical_event_json` produces a stable hash-input string by
sorting keys -- this is what makes the chain reproducible across
backends.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence


DEFAULT_PAGE_LIMIT = 100
"""Pagination cap mirroring the OpenHands EventService default."""


class EventSortOrder(str, Enum):
    """Sort orders for :func:`EventStore.search_events`.

    Mirrors the OpenHands ``EventSortOrder`` shape:

    * ``TIMESTAMP`` -- ascending (oldest first).
    * ``TIMESTAMP_DESC`` -- descending (newest first).
    """

    TIMESTAMP = "timestamp"
    TIMESTAMP_DESC = "timestamp_desc"


DEFAULT_SEARCH_SORT = EventSortOrder.TIMESTAMP


class EventKind:
    """Sentinel-free namespace for canonical event-kind strings.

    Event kinds are plain strings; we keep a few load-bearing ones as
    class constants so call sites can use a single source of truth.
    Subsystems are free to invent additional kinds.
    """

    # Voice / orchestration lifecycle.
    TURN_STARTED = "TurnStarted"
    TURN_COMPLETED = "TurnCompleted"
    STT_TRANSCRIBED = "STTTranscribed"
    ROUTING_CLASSIFIED = "RoutingClassified"
    GATE_VERDICT = "GateVerdict"
    MEMORY_RETRIEVED = "MemoryRetrieved"
    LLM_STREAM_TOKEN = "LLMStreamToken"
    LLM_STREAM_COMPLETE = "LLMStreamComplete"
    TTS_PLAYED = "TTSPlayed"
    SAFETY_VIOLATED = "SafetyViolated"

    # Coding / supervisor.
    CODING_FILE_CHANGED = "CodingFileChanged"
    PROJECT_INDEXED = "ProjectIndexed"
    PROJECT_DIGEST_GENERATED = "ProjectDigestGenerated"
    SUPERVISOR_DECIDED = "SupervisorDecided"

    # Gaming mode.
    GAMING_ENGAGED = "GamingEngaged"
    GAMING_DISENGAGED = "GamingDisengaged"
    VRAM_RECLAIMED = "VRAMReclaimed"

    # Catch-all for subsystems that haven't been catalogued yet.
    USER_MESSAGE = "UserMessage"
    ASSISTANT_MESSAGE = "AssistantMessage"
    SYSTEM_NOTE = "SystemNote"


def new_event_id() -> str:
    """Return a fresh UUID4 hex string suitable for :class:`StoredEvent.id`."""

    return uuid.uuid4().hex


@dataclass(frozen=True)
class StoredEvent:
    """One event row.

    The :meth:`with_chain_hashes` helper returns a copy with chain
    fields populated; this lets the store enforce chain integrity at
    write time without mutating callers' frozen rows.

    Attributes:
        id: UUID4 hex.
        session_id: Owning session identifier (per-session log files
            keyed by this).
        kind: Short event-type token (see :class:`EventKind` constants).
        timestamp: Unix epoch seconds. Defaults to ``time.time()`` at
            construction.
        payload: Structured event-specific data.
        source: Optional free-form producer label (e.g. ``"bus"``,
            ``"safety"``).
        chain_prev_hash: SHA-256 hex of the previous event's
            ``chain_hash`` in this session (``None`` for the first
            event).
        chain_hash: SHA-256 hex of this event's canonical encoding +
            prev hash. Populated by :meth:`with_chain_hashes`.
        sequence: 0-indexed position within the session. Useful for
            sort stability when multiple events share a timestamp.
        extra: Free-form metadata not promoted to first-class fields.
    """

    id: str
    session_id: str
    kind: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None
    chain_prev_hash: str | None = None
    chain_hash: str | None = None
    sequence: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(
        cls,
        session_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        source: str | None = None,
        timestamp: float | None = None,
        event_id: str | None = None,
        sequence: int = 0,
        extra: Mapping[str, Any] | None = None,
    ) -> "StoredEvent":
        """Construct a :class:`StoredEvent` with sensible defaults.

        ``timestamp`` defaults to the current wall-clock time; tests
        may pass a fixed value for reproducible chains.
        """

        return cls(
            id=event_id or new_event_id(),
            session_id=session_id,
            kind=kind,
            timestamp=timestamp if timestamp is not None else time.time(),
            payload=dict(payload or {}),
            source=source,
            sequence=sequence,
            extra=dict(extra or {}),
        )

    def with_chain_hashes(
        self,
        *,
        prev_hash: str | None,
        chain_hash: str,
    ) -> "StoredEvent":
        """Return a copy with the chain fields populated."""

        return replace(
            self,
            chain_prev_hash=prev_hash,
            chain_hash=chain_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-encodable mapping of this event."""

        return {
            "id": self.id,
            "session_id": self.session_id,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
            "source": self.source,
            "chain_prev_hash": self.chain_prev_hash,
            "chain_hash": self.chain_hash,
            "sequence": self.sequence,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StoredEvent":
        """Inverse of :meth:`to_dict`. Missing optional fields fall to defaults."""

        return cls(
            id=str(data["id"]),
            session_id=str(data["session_id"]),
            kind=str(data["kind"]),
            timestamp=float(data["timestamp"]),
            payload=dict(data.get("payload") or {}),
            source=data.get("source"),
            chain_prev_hash=data.get("chain_prev_hash"),
            chain_hash=data.get("chain_hash"),
            sequence=int(data.get("sequence", 0)),
            extra=dict(data.get("extra") or {}),
        )


@dataclass(frozen=True)
class EventPage:
    """Paginated search result."""

    items: tuple[StoredEvent, ...]
    next_page_token: str | None = None
    total_estimated: int | None = None


@dataclass(frozen=True)
class EventQuery:
    """Query value object that mirrors the OpenHands kw shape."""

    session_id: str
    kind: str | None = None
    since: float | None = None
    until: float | None = None
    sort_order: EventSortOrder = DEFAULT_SEARCH_SORT
    page_token: str | None = None
    limit: int = DEFAULT_PAGE_LIMIT

    def with_overrides(self, **kwargs: Any) -> "EventQuery":
        return replace(self, **kwargs)


def canonical_event_json(event: StoredEvent) -> str:
    """Stable JSON encoding used as the chain-hash input.

    Sorts keys + omits the row's OWN ``chain_hash`` (which is computed
    over the rest of the row).  This makes the hash reproducible across
    different storage backends.
    """

    payload = {
        "id": event.id,
        "session_id": event.session_id,
        "kind": event.kind,
        "timestamp": _round_timestamp(event.timestamp),
        "payload": event.payload,
        "source": event.source,
        "sequence": event.sequence,
        "extra": event.extra,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _round_timestamp(value: float) -> float:
    """Round timestamps to 6 decimal places (microsecond) for reproducibility.

    ``time.time()`` returns higher-precision floats on some platforms;
    rounding here makes the chain stable across machines + OS clock
    granularity variations.
    """

    return round(value, 6)


def kinds_in(events: Sequence[StoredEvent]) -> list[str]:
    """Return the sorted unique event kinds in ``events``."""

    return sorted({e.kind for e in events})
