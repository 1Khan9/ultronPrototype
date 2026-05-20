"""Track 6 voice-loop integration tests for ConversationMemory.

Exercises ``ConversationMemory.add(channel=...)`` plumbing into the
Qdrant payload and the read-side ``_payload_to_turn`` restoring the
channel for callers. Uses a stub Qdrant client so the tests don't
touch the embedded store.
"""

from __future__ import annotations

import queue
import threading
from types import SimpleNamespace
from typing import List

import numpy as np
import pytest

from ultron.channels import Channel, ChannelMetadata
from ultron.memory.embedder import _SparseVec
from ultron.memory.qdrant_store import (
    ConversationMemory,
    MemoryTurn,
    _payload_to_turn,
)


# ---------------------------------------------------------------------------
# Stubs -- a minimal QdrantClient + HybridEmbedder pair
# ---------------------------------------------------------------------------


class _StubEmbedder:
    """Just enough of HybridEmbedder for the write path to function."""

    def encode_dense(self, text: str):
        return np.zeros(384, dtype=np.float32)

    def encode_sparse(self, text: str):
        return [_SparseVec([1, 2], [0.1, 0.2])]


class _StubQdrantClient:
    """Records every upsert so tests can inspect the payload directly."""

    def __init__(self) -> None:
        self.upserts = []

    def upsert(self, *, collection_name, points):
        for p in points:
            self.upserts.append({
                "collection": collection_name,
                "id": p.id,
                "payload": dict(p.payload),
            })


def _make_memory_no_qdrant_load() -> "tuple[ConversationMemory, _StubQdrantClient]":
    """Build a ConversationMemory without touching the real Qdrant store."""
    m = object.__new__(ConversationMemory)
    m.path = None
    m._embedder = _StubEmbedder()
    m._recent_cache_size = 100
    m.session_id = "test-session"
    m._recent = []
    m._next_id = 0
    m._lock = threading.Lock()
    m._client = _StubQdrantClient()
    m._topic_tracker = None
    m._discourse_classifier = None
    # The async writer thread isn't started in these tests; we drain
    # the queue manually (or call _upsert_turn directly). The queue
    # itself MUST exist or ``add()`` raises AttributeError on the
    # put_nowait. Bounded the same way the production code does it,
    # but tests stay well below the limit.
    m._write_queue = queue.Queue(maxsize=256)
    return m, m._client


# ---------------------------------------------------------------------------
# Write-path tests
# ---------------------------------------------------------------------------


def test_memory_turn_default_channel_is_user():
    """Legacy code that constructs MemoryTurn without specifying a
    channel must still get a USER tag -- the field default carries
    the back-compat invariant."""
    turn = MemoryTurn(id=1, ts=0.0, role="user", content="hi")
    assert turn.channel is Channel.USER


def test_add_defaults_channel_to_user_when_kwarg_omitted():
    """Existing LLMEngine._record_turn calls add(role, content) with no
    channel; the default must be USER for byte-for-byte legacy
    behaviour."""
    m, _client = _make_memory_no_qdrant_load()
    turn = m.add("user", "what is the capital of France?")
    assert turn.channel is Channel.USER


def test_add_accepts_explicit_user_channel():
    m, _client = _make_memory_no_qdrant_load()
    turn = m.add("user", "hi", channel=Channel.USER)
    assert turn.channel is Channel.USER


def test_add_accepts_teammate_channel():
    m, _client = _make_memory_no_qdrant_load()
    turn = m.add("user", "push B", channel=Channel.TEAMMATE)
    assert turn.channel is Channel.TEAMMATE


def test_add_accepts_system_channel():
    m, _client = _make_memory_no_qdrant_load()
    turn = m.add("assistant", "standing order fired", channel=Channel.SYSTEM)
    assert turn.channel is Channel.SYSTEM


def test_add_explicit_none_channel_defaults_to_user():
    """Passing ``channel=None`` (rather than omitting) should still
    resolve to USER -- the kwarg-explicit caller shouldn't get
    different behaviour than the kwarg-omitted caller."""
    m, _client = _make_memory_no_qdrant_load()
    turn = m.add("user", "hi", channel=None)
    assert turn.channel is Channel.USER


# ---------------------------------------------------------------------------
# Qdrant payload tests
# ---------------------------------------------------------------------------


def test_upsert_payload_carries_user_channel(monkeypatch):
    """The Qdrant point payload from the default-channel write path
    must carry the ``channel`` + ``channel_confidence`` fields so a
    future filter / observability layer can scope on them."""
    m, client = _make_memory_no_qdrant_load()
    turn = MemoryTurn(
        id=42, ts=12345.0, role="user", content="hello world",
        session_id="sess", channel=Channel.USER,
    )

    # Need to stub the qdrant collection name lookup.
    monkeypatch.setattr(
        "ultron.memory.qdrant_store.get_config",
        lambda: SimpleNamespace(qdrant=SimpleNamespace(
            collections=SimpleNamespace(conversations="conv"),
        )),
    )
    m._upsert_turn(turn)
    assert len(client.upserts) == 1
    payload = client.upserts[0]["payload"]
    assert payload["channel"] == "user"
    assert payload["channel_confidence"] == pytest.approx(1.0)
    # Legacy fields still present
    assert payload["turn_id"] == 42
    assert payload["content"] == "hello world"


def test_upsert_payload_carries_teammate_channel(monkeypatch):
    m, client = _make_memory_no_qdrant_load()
    turn = MemoryTurn(
        id=1, ts=0.0, role="user", content="push B",
        session_id="sess", channel=Channel.TEAMMATE,
    )

    monkeypatch.setattr(
        "ultron.memory.qdrant_store.get_config",
        lambda: SimpleNamespace(qdrant=SimpleNamespace(
            collections=SimpleNamespace(conversations="conv"),
        )),
    )
    m._upsert_turn(turn)
    assert client.upserts[0]["payload"]["channel"] == "teammate"


def test_upsert_payload_carries_system_channel(monkeypatch):
    m, client = _make_memory_no_qdrant_load()
    turn = MemoryTurn(
        id=1, ts=0.0, role="assistant", content="standing order",
        session_id="sess", channel=Channel.SYSTEM,
    )

    monkeypatch.setattr(
        "ultron.memory.qdrant_store.get_config",
        lambda: SimpleNamespace(qdrant=SimpleNamespace(
            collections=SimpleNamespace(conversations="conv"),
        )),
    )
    m._upsert_turn(turn)
    assert client.upserts[0]["payload"]["channel"] == "system"


# ---------------------------------------------------------------------------
# Read-path tests (_payload_to_turn round-trip)
# ---------------------------------------------------------------------------


def test_payload_to_turn_restores_user_channel():
    payload = {
        "turn_id": 1, "ts": 0.0, "role": "user", "content": "hi",
        "session_id": "sess", "channel": "user",
    }
    turn = _payload_to_turn(payload)
    assert turn.channel is Channel.USER


def test_payload_to_turn_restores_teammate_channel():
    payload = {
        "turn_id": 1, "ts": 0.0, "role": "user", "content": "push B",
        "session_id": "sess", "channel": "teammate",
    }
    turn = _payload_to_turn(payload)
    assert turn.channel is Channel.TEAMMATE


def test_payload_to_turn_restores_system_channel():
    payload = {
        "turn_id": 1, "ts": 0.0, "role": "assistant",
        "content": "scheduled task fired",
        "session_id": "sess", "channel": "system",
    }
    turn = _payload_to_turn(payload)
    assert turn.channel is Channel.SYSTEM


def test_payload_to_turn_legacy_payload_defaults_to_user():
    """Payloads written before the channel field landed (pre-2026-05-19)
    have no ``channel`` key. The reader must default to USER, not
    raise -- otherwise the maintenance script + retrieve path would
    explode on every old turn."""
    legacy_payload = {
        "turn_id": 1, "ts": 0.0, "role": "user", "content": "ancient turn",
        "session_id": "old-sess",
    }
    turn = _payload_to_turn(legacy_payload)
    assert turn.channel is Channel.USER


def test_payload_to_turn_unknown_channel_string_defaults_to_user():
    """Channel.from_str coerces unknown strings to USER. A typo or a
    future channel that hasn't been added to the enum yet shouldn't
    crash the reader."""
    payload = {
        "turn_id": 1, "ts": 0.0, "role": "user", "content": "hi",
        "session_id": "sess", "channel": "alien-channel-from-the-future",
    }
    turn = _payload_to_turn(payload)
    assert turn.channel is Channel.USER


# ---------------------------------------------------------------------------
# Full write -> read round-trip
# ---------------------------------------------------------------------------


def test_round_trip_user_channel_via_upsert_and_payload_to_turn(monkeypatch):
    """End-to-end: write through _upsert_turn, then reconstruct via
    _payload_to_turn -- verifies the channel survives the trip with
    the metadata shape ChannelMetadata produces."""
    m, client = _make_memory_no_qdrant_load()
    monkeypatch.setattr(
        "ultron.memory.qdrant_store.get_config",
        lambda: SimpleNamespace(qdrant=SimpleNamespace(
            collections=SimpleNamespace(conversations="conv"),
        )),
    )
    turn_in = MemoryTurn(
        id=10, ts=999.0, role="user", content="round trip me",
        session_id="rt", channel=Channel.TEAMMATE,
    )
    m._upsert_turn(turn_in)
    payload = client.upserts[0]["payload"]
    turn_out = _payload_to_turn(payload)
    assert turn_out.channel is Channel.TEAMMATE
    assert turn_out.content == "round trip me"
    assert turn_out.id == 10
