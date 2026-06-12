"""Qdrant failure modes: query embedding failure / hybrid search failure.

Validates ConversationMemory.retrieve() returns ``[]`` on failure, errors.jsonl
receives a QdrantUnavailableError, and the calling LLM proceeds from base
knowledge instead of crashing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from kenning.memory.qdrant_store import ConversationMemory


@pytest.fixture
def mem(tmp_path) -> ConversationMemory:
    """A real ConversationMemory with a tmp-path Qdrant. Embedder is mocked
    so we don't need fastembed at test time."""
    embedder = MagicMock()
    embedder.dim = 4
    embedder.encode_dense.return_value = [0.0, 0.0, 0.0, 0.0]
    embedder.encode_query_dense.return_value = MagicMock(tolist=lambda: [0.0, 0.0, 0.0, 0.0])
    embedder.encode_query_sparse.return_value = MagicMock(indices=[1], values=[0.5])
    return ConversationMemory(path=tmp_path / "qdrant", embedder=embedder)


def test_qdrant_embedding_failure_returns_empty(mem, errors_log, read_errors):
    """Query embedding raises -> retrieve returns []; errors logged."""
    mem._embedder.encode_query_dense.side_effect = RuntimeError("embedder dead")

    # Pre-populate next_id so cutoff > 0 (otherwise we exit before embedding).
    mem._next_id = 100
    out = mem.retrieve("a query")
    assert out == []
    records = read_errors()
    assert any(
        r["dependency"] == "qdrant_embedder" and r["error_type"] == "QdrantUnavailableError"
        for r in records
    )


def test_qdrant_search_failure_returns_empty(mem, errors_log, read_errors):
    """Qdrant query_points raises -> retrieve returns []; errors logged."""
    mem._next_id = 100
    with patch.object(
        mem._client, "query_points",
        side_effect=RuntimeError("qdrant client raised"),
    ):
        out = mem.retrieve("a query")
    assert out == []
    records = read_errors()
    assert any(
        r["dependency"] == "qdrant" and r["error_type"] == "QdrantUnavailableError"
        for r in records
    )
    rec = next(r for r in records if r["dependency"] == "qdrant")
    assert "base knowledge" in rec["recovery"]


def test_qdrant_subsequent_retrieve_works_after_failure(
    mem, errors_log, read_errors,
):
    """A transient query failure doesn't disable future retrieves."""
    mem._next_id = 100

    # First call fails
    with patch.object(
        mem._client, "query_points", side_effect=RuntimeError("transient"),
    ):
        assert mem.retrieve("first") == []

    # Second call succeeds (returns empty because nothing's indexed, but
    # critically: it doesn't raise, and no error is logged the second time).
    pre_count = len(read_errors())
    assert mem.retrieve("second") == []
    assert len(read_errors()) == pre_count, (
        "second successful call should not have added an error log entry"
    )
