"""2026-05-19 cross-session contamination fix tests.

Live session 2026-05-19 (bpv9qjpxb): the user said 'and say hello'
and got back 'According to Realfast.ai, Agentforce pricing is $2 per
conversation...'. The Salesforce content came from a much older
session that was still sitting in the in-process recent-turn cache.
``LLMEngine._build_messages`` then injected the last 4 cached turns
into the prompt as 'conversation history', producing a replay of
stale cross-topic content.

Fix: ``ConversationMemory.recent(n)`` now filters the cache to the
current session_id. Cross-session content remains accessible via
``recent_all_sessions(n)`` and via the RAG ``retrieve`` path.
"""

from __future__ import annotations

import queue
import threading

import pytest

from kenning.channels import Channel
from kenning.memory.embedder import _SparseVec
from kenning.memory.qdrant_store import (
    ConversationMemory,
    MemoryTurn,
)


def _make_memory_no_qdrant_load(session_id: str = "current-session") -> ConversationMemory:
    """Build a ConversationMemory without touching Qdrant."""
    m = object.__new__(ConversationMemory)
    m.path = None
    m._embedder = None
    m._recent_cache_size = 100
    m.session_id = session_id
    m._recent = []
    m._next_id = 0
    m._lock = threading.Lock()
    m._client = None
    m._topic_tracker = None
    m._discourse_classifier = None
    m._write_queue = queue.Queue(maxsize=256)
    return m


def _turn(id_: int, role: str, content: str, session_id: str) -> MemoryTurn:
    return MemoryTurn(
        id=id_, ts=float(id_), role=role, content=content,
        session_id=session_id, channel=Channel.USER,
    )


def test_recent_returns_empty_when_no_turns():
    m = _make_memory_no_qdrant_load()
    assert m.recent(5) == []


def test_recent_returns_only_current_session_turns():
    """The root cause of the cross-session contamination: prior-session
    turns sitting in the in-process cache used to bleed into the LLM
    prompt as 'recent history'. Now they're filtered out."""
    m = _make_memory_no_qdrant_load(session_id="current")
    m._recent = [
        _turn(1, "user", "old salesforce question", session_id="old-session-1"),
        _turn(2, "assistant", "Salesforce Agentforce costs $2", session_id="old-session-1"),
        _turn(3, "user", "old fbi question", session_id="old-session-2"),
        _turn(4, "assistant", "FBI watch list contains names", session_id="old-session-2"),
        _turn(5, "user", "current hello", session_id="current"),
        _turn(6, "assistant", "Hello.", session_id="current"),
    ]
    out = m.recent(10)
    assert len(out) == 2
    assert all(t.session_id == "current" for t in out)
    assert out[0].content == "current hello"
    assert out[1].content == "Hello."
    # The stale Salesforce / FBI content is gone.
    assert all("Salesforce" not in t.content for t in out)
    assert all("FBI" not in t.content for t in out)


def test_recent_caps_at_n_within_current_session():
    m = _make_memory_no_qdrant_load(session_id="current")
    m._recent = [
        _turn(i, "user", f"turn {i}", session_id="current")
        for i in range(10)
    ]
    out = m.recent(3)
    assert len(out) == 3
    assert [t.content for t in out] == ["turn 7", "turn 8", "turn 9"]


def test_recent_returns_empty_when_only_other_sessions_in_cache():
    """Fresh Kenning boot: cache has 100 prior-session turns loaded,
    but the new session has no turns yet. recent() should return
    [] -- NOT the cached prior-session content."""
    m = _make_memory_no_qdrant_load(session_id="fresh-boot")
    m._recent = [
        _turn(i, "user", f"old turn {i}", session_id="prior-session")
        for i in range(50)
    ]
    assert m.recent(10) == []


def test_recent_handles_n_zero_or_negative():
    m = _make_memory_no_qdrant_load(session_id="current")
    m._recent = [_turn(1, "user", "x", session_id="current")]
    assert m.recent(0) == []
    assert m.recent(-1) == []


def test_recent_all_sessions_preserves_legacy_cross_session_view():
    """Operators who specifically need the cross-session cache (e.g.
    maintenance script) use recent_all_sessions()."""
    m = _make_memory_no_qdrant_load(session_id="current")
    m._recent = [
        _turn(1, "user", "old", session_id="other"),
        _turn(2, "user", "current", session_id="current"),
    ]
    out = m.recent_all_sessions(10)
    assert len(out) == 2
    assert {t.content for t in out} == {"old", "current"}


def test_recent_all_sessions_handles_zero():
    m = _make_memory_no_qdrant_load()
    assert m.recent_all_sessions(0) == []


# ---------------------------------------------------------------------------
# Live-session scenario regression: 'and say hello' must not receive
# stale cross-session turns as 'recent history'.
# ---------------------------------------------------------------------------


def test_live_session_2026_05_19_salesforce_does_not_leak_to_new_session():
    """Reproduce the bug + verify the fix: a fresh session with stale
    Salesforce content in the cross-session cache must NOT see that
    content via recent()."""
    m = _make_memory_no_qdrant_load(session_id="2026-05-19-new")
    # Pre-load the cache as it would be on Kenning boot with 100 prior turns.
    stale = [
        _turn(1, "user", "tell me about agentforce", session_id="2026-05-18-old"),
        _turn(
            2, "assistant",
            "According to Realfast.ai, Agentforce pricing is $2 per conversation",
            session_id="2026-05-18-old",
        ),
        _turn(3, "user", "what about the fbi watchlist", session_id="2026-05-17-old"),
        _turn(
            4, "assistant",
            "I have opened FBI's watch list. It contains names...",
            session_id="2026-05-17-old",
        ),
    ]
    m._recent = stale
    # In a fresh session the cache is full of cross-session content
    # but recent() returns []. The LLM's prompt will have NO recent
    # history block, so the model can't replay Salesforce / FBI.
    assert m.recent(4) == []
