"""Dual-array history primitive: verbatim record + LLM-compactable history.

Adapted from cline's ``MessageStateHandler`` pattern (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Kenning's variant promotes the cline
shape from a per-task store to a per-session primitive that any
caller — voice, coding, supervisor — can use:

* :class:`VerbatimTurn` records the EXACT user / agent exchange the
  user actually heard / said, with optional TTS clip refs + image
  refs + per-turn metadata.
* :class:`ApiTurn` records the shape sent to the LLM (post-compaction,
  post-redaction, post-RAG-injection). Subject to truncation, dedup,
  and condenser passes.
* Both arrays share a :class:`TurnId` UUID so an operator's ``"what
  did I say earlier?"`` query can resolve verbatim ←→ api in O(1).

The primitive is intentionally I/O-free. Callers wire their own
persistence (Qdrant payload, JSONL audit log, in-memory recency
cache); :class:`DualHistoryStore` is just the data structure +
indices.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

#: Canonical role identifiers. Matches the existing ``ConversationMemory``
#: convention so callers can write through without rewriting role names.
ROLE_USER: str = "user"
ROLE_ASSISTANT: str = "assistant"
ROLE_SYSTEM: str = "system"
ROLE_TOOL: str = "tool"


def new_turn_id() -> str:
    """Generate a fresh stable turn identifier (32-char hex UUID4)."""
    return uuid.uuid4().hex


@dataclass(frozen=True)
class VerbatimTurn:
    """One verbatim record of what the user said / heard.

    Attributes:
        turn_id: stable UUID matching the corresponding
            :class:`ApiTurn` (if any).
        role: ``"user"`` / ``"assistant"`` / ``"system"`` / ``"tool"``.
        text: the literal text (not the prompt-augmented body).
        timestamp: monotonic-ish wall-clock seconds (caller-supplied,
            typically ``time.time()``).
        channel: optional channel label
            (``"USER"`` / ``"AGENT"`` / ``"SYSTEM"`` / ``"BACKGROUND"``).
        tts_clip_ref: optional path or content-hash pointing at the
            cached TTS audio for replay-by-voice-command.
        image_refs: optional sequence of image references (for
            multimodal turns; the verbatim record keeps these even
            when the api history strips them post-VLM-description).
        metadata: free-form extra fields (intent classification,
            confidence, retry status, etc.).
    """

    turn_id: str
    role: str
    text: str
    timestamp: float = 0.0
    channel: str = ""
    tts_clip_ref: str = ""
    image_refs: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiTurn:
    """One LLM-facing entry in the API history.

    Attributes:
        turn_id: stable UUID matching the corresponding
            :class:`VerbatimTurn` (if any). Pruned / compacted entries
            keep their original turn_id so callers can map back.
        role: provider role identifier.
        content: provider content shape (``str`` OR typed-block list).
        compacted: True when this entry replaced one or more dropped
            entries during a condenser pass.
        elided_count: when ``compacted`` is True, the number of
            verbatim turns this single entry summarises.
    """

    turn_id: str
    role: str
    content: Any
    compacted: bool = False
    elided_count: int = 0


@dataclass(frozen=True)
class HistorySnapshot:
    """Frozen point-in-time view of the dual store.

    Attributes:
        verbatim: ordered list of :class:`VerbatimTurn`.
        api: ordered list of :class:`ApiTurn`.
        turn_id_to_verbatim_index: lookup index from turn_id → verbatim
            list index.
        turn_id_to_api_index: lookup index from turn_id → api list index.
    """

    verbatim: tuple[VerbatimTurn, ...]
    api: tuple[ApiTurn, ...]
    turn_id_to_verbatim_index: Mapping[str, int]
    turn_id_to_api_index: Mapping[str, int]


class DualHistoryStore:
    """In-memory dual-array store keyed by stable per-turn UUIDs.

    Args:
        verbatim_cap: optional cap on the verbatim array size; when
            exceeded the oldest entries are silently dropped. ``None``
            keeps everything (the recommended default — verbatim is
            cheap to keep around).
        api_cap: optional cap on the api array size; when exceeded the
            oldest entries are dropped. Typically set lower than the
            verbatim cap since the api history is what costs tokens
            on every LLM call.
    """

    def __init__(
        self,
        *,
        verbatim_cap: Optional[int] = None,
        api_cap: Optional[int] = None,
    ) -> None:
        self._verbatim_cap = verbatim_cap
        self._api_cap = api_cap
        self._lock = threading.RLock()
        self._verbatim: list[VerbatimTurn] = []
        self._api: list[ApiTurn] = []
        self._verbatim_index: dict[str, int] = {}
        self._api_index: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Write surface
    # ------------------------------------------------------------------

    def record(
        self,
        role: str,
        text: str,
        *,
        turn_id: Optional[str] = None,
        timestamp: float = 0.0,
        channel: str = "",
        tts_clip_ref: str = "",
        image_refs: Optional[Iterable[str]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        api_content: Any = None,
    ) -> str:
        """Append a verbatim turn AND (optionally) the matching api turn.

        Args:
            role: role identifier (``"user"`` / ``"assistant"`` /
                ``"system"`` / ``"tool"``).
            text: verbatim text (the literal user utterance / agent
                response — NOT the prompt-augmented body).
            turn_id: optional pre-existing UUID. Caller-supplied id
                lets two stores agree on the same key across processes.
            timestamp: optional wall-clock seconds for the turn.
            channel: optional channel label.
            tts_clip_ref: optional path / hash for the cached audio.
            image_refs: optional iterable of image references kept
                verbatim alongside the text.
            metadata: optional free-form extras.
            api_content: optional api-facing content. When None, the
                store appends to verbatim only (use :meth:`record_api`
                separately when the api shape diverges from the
                verbatim text). When supplied, an :class:`ApiTurn` is
                appended with the same turn_id.

        Returns:
            The turn_id that was used / generated.
        """
        new_id = turn_id or new_turn_id()
        verbatim_entry = VerbatimTurn(
            turn_id=new_id,
            role=role,
            text=text,
            timestamp=timestamp,
            channel=channel,
            tts_clip_ref=tts_clip_ref,
            image_refs=tuple(image_refs) if image_refs else (),
            metadata=dict(metadata) if metadata else {},
        )
        with self._lock:
            self._verbatim.append(verbatim_entry)
            self._verbatim_index[new_id] = len(self._verbatim) - 1
            self._maybe_evict_verbatim_locked()
            if api_content is not None:
                api_entry = ApiTurn(
                    turn_id=new_id,
                    role=role,
                    content=api_content,
                )
                self._api.append(api_entry)
                self._api_index[new_id] = len(self._api) - 1
                self._maybe_evict_api_locked()
        return new_id

    def record_api(
        self,
        turn_id: str,
        role: str,
        content: Any,
        *,
        compacted: bool = False,
        elided_count: int = 0,
    ) -> None:
        """Append an :class:`ApiTurn` referencing ``turn_id``.

        Useful when the api shape is computed later (e.g. brevity hints
        injected post-record, or condenser summaries spanning multiple
        verbatim entries).
        """
        with self._lock:
            entry = ApiTurn(
                turn_id=turn_id,
                role=role,
                content=content,
                compacted=compacted,
                elided_count=elided_count,
            )
            self._api.append(entry)
            self._api_index[turn_id] = len(self._api) - 1
            self._maybe_evict_api_locked()

    def replace_api_range(
        self,
        start: int,
        stop: int,
        replacement: Optional[ApiTurn] = None,
    ) -> int:
        """Replace ``api[start:stop]`` with optional single ``replacement``.

        Args:
            start: inclusive start index.
            stop: exclusive stop index.
            replacement: optional :class:`ApiTurn` to substitute in;
                when None, the slice is dropped entirely.

        Returns:
            Number of entries removed (replacement counts as 1 inserted).
        """
        with self._lock:
            if start < 0:
                start = 0
            if stop > len(self._api):
                stop = len(self._api)
            if start >= stop:
                return 0
            removed_count = stop - start
            for entry in self._api[start:stop]:
                self._api_index.pop(entry.turn_id, None)
            if replacement is not None:
                self._api = (
                    self._api[:start] + [replacement] + self._api[stop:]
                )
                # Insertion may collide with an existing turn_id in a
                # different slot; reindex everything from the inserted
                # position onwards to be safe.
                for idx in range(start, len(self._api)):
                    self._api_index[self._api[idx].turn_id] = idx
            else:
                self._api = self._api[:start] + self._api[stop:]
                for idx in range(start, len(self._api)):
                    self._api_index[self._api[idx].turn_id] = idx
            return removed_count

    def truncate_after_turn(self, turn_id: str) -> tuple[int, int]:
        """Drop every entry whose turn-id sequence > the ``turn_id``'s.

        Used by the checkpoint restore path: ``"undo the last 3 voice
        turns"`` resolves to a target turn_id, and both arrays truncate
        back to that point.

        Args:
            turn_id: anchor turn_id; entries AT or BEFORE this
                position are kept. Pass an empty string to clear
                everything.

        Returns:
            ``(verbatim_dropped, api_dropped)`` pair.
        """
        with self._lock:
            verbatim_drop = 0
            api_drop = 0
            if not turn_id:
                verbatim_drop = len(self._verbatim)
                api_drop = len(self._api)
                self._verbatim.clear()
                self._api.clear()
                self._verbatim_index.clear()
                self._api_index.clear()
                return verbatim_drop, api_drop
            verbatim_idx = self._verbatim_index.get(turn_id)
            if verbatim_idx is not None:
                verbatim_drop = max(0, len(self._verbatim) - verbatim_idx - 1)
                for entry in self._verbatim[verbatim_idx + 1:]:
                    self._verbatim_index.pop(entry.turn_id, None)
                self._verbatim = self._verbatim[:verbatim_idx + 1]
            api_idx = self._api_index.get(turn_id)
            if api_idx is not None:
                api_drop = max(0, len(self._api) - api_idx - 1)
                for entry in self._api[api_idx + 1:]:
                    self._api_index.pop(entry.turn_id, None)
                self._api = self._api[:api_idx + 1]
            return verbatim_drop, api_drop

    def truncate_to_offset(self, *, offset_from_end: int) -> tuple[int, int]:
        """Drop the last ``offset_from_end`` verbatim turns + matching api.

        Args:
            offset_from_end: number of trailing verbatim entries to drop.

        Returns:
            ``(verbatim_dropped, api_dropped)`` pair.
        """
        with self._lock:
            if offset_from_end <= 0 or not self._verbatim:
                return 0, 0
            count = min(offset_from_end, len(self._verbatim))
            doomed = self._verbatim[-count:]
            self._verbatim = self._verbatim[:-count]
            for entry in doomed:
                self._verbatim_index.pop(entry.turn_id, None)
            # Collect all api indices BEFORE deletion so positions stay
            # valid; then delete in descending order so each delete
            # leaves earlier indices unchanged.
            api_indices: list[int] = []
            for entry in doomed:
                idx = self._api_index.pop(entry.turn_id, None)
                if idx is not None and 0 <= idx < len(self._api):
                    api_indices.append(idx)
            api_dropped = 0
            for api_idx in sorted(api_indices, reverse=True):
                del self._api[api_idx]
                api_dropped += 1
            # Reindex the api list since deletions shifted positions.
            self._api_index = {
                turn.turn_id: idx for idx, turn in enumerate(self._api)
            }
            return count, api_dropped

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------

    def verbatim(self) -> tuple[VerbatimTurn, ...]:
        with self._lock:
            return tuple(self._verbatim)

    def api(self) -> tuple[ApiTurn, ...]:
        with self._lock:
            return tuple(self._api)

    def recent_verbatim(self, n: int) -> tuple[VerbatimTurn, ...]:
        with self._lock:
            if n <= 0:
                return ()
            return tuple(self._verbatim[-n:])

    def recent_api(self, n: int) -> tuple[ApiTurn, ...]:
        with self._lock:
            if n <= 0:
                return ()
            return tuple(self._api[-n:])

    def get_verbatim(self, turn_id: str) -> Optional[VerbatimTurn]:
        with self._lock:
            idx = self._verbatim_index.get(turn_id)
            if idx is None:
                return None
            return self._verbatim[idx]

    def get_api(self, turn_id: str) -> Optional[ApiTurn]:
        with self._lock:
            idx = self._api_index.get(turn_id)
            if idx is None:
                return None
            return self._api[idx]

    def find_verbatim_by_substring(
        self, needle: str, *, limit: int = 10, case_insensitive: bool = True,
    ) -> tuple[VerbatimTurn, ...]:
        """Fuzzy search the verbatim record for ``needle`` (newest first)."""
        if not needle:
            return ()
        key = needle.lower() if case_insensitive else needle
        with self._lock:
            out: list[VerbatimTurn] = []
            for entry in reversed(self._verbatim):
                haystack = entry.text.lower() if case_insensitive else entry.text
                if key in haystack:
                    out.append(entry)
                    if len(out) >= limit:
                        break
            return tuple(out)

    def snapshot(self) -> HistorySnapshot:
        with self._lock:
            return HistorySnapshot(
                verbatim=tuple(self._verbatim),
                api=tuple(self._api),
                turn_id_to_verbatim_index=dict(self._verbatim_index),
                turn_id_to_api_index=dict(self._api_index),
            )

    def verbatim_turn_count(self) -> int:
        with self._lock:
            return len(self._verbatim)

    def api_turn_count(self) -> int:
        with self._lock:
            return len(self._api)

    def drift_report(self) -> dict[str, int]:
        """Per-call counts of entries present in one array but not the other.

        Useful for the daily drift-audit dashboard mentioned in the
        catalog ("you've been silenced 14 times by closed-window
        compression today").
        """
        with self._lock:
            verbatim_keys = set(self._verbatim_index.keys())
            api_keys = set(self._api_index.keys())
            return {
                "verbatim_only": len(verbatim_keys - api_keys),
                "api_only": len(api_keys - verbatim_keys),
                "shared": len(verbatim_keys & api_keys),
                "verbatim_total": len(verbatim_keys),
                "api_total": len(api_keys),
            }

    def clear(self) -> None:
        with self._lock:
            self._verbatim.clear()
            self._api.clear()
            self._verbatim_index.clear()
            self._api_index.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_evict_verbatim_locked(self) -> None:
        if self._verbatim_cap is None:
            return
        while len(self._verbatim) > self._verbatim_cap:
            evicted = self._verbatim.pop(0)
            self._verbatim_index.pop(evicted.turn_id, None)
        # Rebuild the index after eviction so positions stay accurate.
        self._verbatim_index = {
            entry.turn_id: idx for idx, entry in enumerate(self._verbatim)
        }

    def _maybe_evict_api_locked(self) -> None:
        if self._api_cap is None:
            return
        while len(self._api) > self._api_cap:
            evicted = self._api.pop(0)
            self._api_index.pop(evicted.turn_id, None)
        self._api_index = {
            entry.turn_id: idx for idx, entry in enumerate(self._api)
        }


__all__ = [
    "ApiTurn",
    "DualHistoryStore",
    "HistorySnapshot",
    "ROLE_ASSISTANT",
    "ROLE_SYSTEM",
    "ROLE_TOOL",
    "ROLE_USER",
    "VerbatimTurn",
    "new_turn_id",
]
