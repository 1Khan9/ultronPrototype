"""Direct tests for the ErrorLog writer + phrase library."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ultron.errors import (
    BraveAPIError,
    ConfigurationError,
    QdrantUnavailableError,
)
from ultron.resilience import ErrorLog, phrase_for, reset_phrase_cache


def test_record_writes_one_jsonl_line(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    err = BraveAPIError(
        "rate-limited",
        context={"query": "test"},
        recovery="returned [] to caller",
    )
    log.record(err, dependency="brave_api", include_traceback=False)
    lines = (tmp_path / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["dependency"] == "brave_api"
    assert rec["error_type"] == "BraveAPIError"
    assert rec["context"]["query"] == "test"
    assert rec["recovery"] == "returned [] to caller"


def test_record_appends_multiple_entries(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    log.record(BraveAPIError("a"), dependency="brave_api", include_traceback=False)
    log.record(QdrantUnavailableError("b"), dependency="qdrant", include_traceback=False)
    lines = (tmp_path / "errors.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_record_handles_generic_exception_with_message_only(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    log.record(
        RuntimeError("not an UltronError"),
        dependency="something_else",
        include_traceback=False,
    )
    rec = json.loads((tmp_path / "errors.jsonl").read_text(encoding="utf-8").strip())
    assert rec["error_type"] == "RuntimeError"
    assert rec["message"] == "not an UltronError"
    assert rec["recovery"] is None


def test_record_includes_traceback_when_requested(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    try:
        raise BraveAPIError("with tb")
    except BraveAPIError as e:
        log.record(e, dependency="brave_api", include_traceback=True)
    rec = json.loads((tmp_path / "errors.jsonl").read_text(encoding="utf-8").strip())
    assert "traceback" in rec
    assert "BraveAPIError" in rec["traceback"]


def test_record_extra_merges_into_context(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    err = BraveAPIError("x", context={"query": "q"})
    log.record(err, dependency="brave_api", extra={"latency_ms": 1234},
               include_traceback=False)
    rec = json.loads((tmp_path / "errors.jsonl").read_text(encoding="utf-8").strip())
    assert rec["context"]["query"] == "q"
    assert rec["context"]["latency_ms"] == 1234


def test_record_extra_does_not_clobber_structural_keys(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    log.record(
        BraveAPIError("x"),
        dependency="brave_api",
        extra={"dependency": "OVERWRITE_ATTEMPT", "session_id": "OVERWRITE"},
        include_traceback=False,
    )
    rec = json.loads((tmp_path / "errors.jsonl").read_text(encoding="utf-8").strip())
    assert rec["dependency"] == "brave_api"  # original preserved
    assert "OVERWRITE_ATTEMPT" not in str(rec.get("context", {}))


def test_record_with_session_id(tmp_path):
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    log.record(
        BraveAPIError("x"),
        dependency="brave_api",
        session_id="abc123",
        include_traceback=False,
    )
    rec = json.loads((tmp_path / "errors.jsonl").read_text(encoding="utf-8").strip())
    assert rec["session_id"] == "abc123"


def test_record_swallows_write_errors(tmp_path, caplog):
    """Errors writing the error log must not propagate — logging the
    error log's own failure goes to the in-process logger."""
    log = ErrorLog(path=tmp_path / "errors.jsonl")
    # Force a write failure by replacing _path with a directory.
    bad_dir = tmp_path / "blocked_dir"
    bad_dir.mkdir()
    log._path = bad_dir  # writing to a directory raises
    # Should not raise:
    log.record(BraveAPIError("x"), dependency="brave_api", include_traceback=False)


# ---------------------------------------------------------------------------
# Phrase library
# ---------------------------------------------------------------------------


def test_phrase_for_returns_one_of_the_pool():
    reset_phrase_cache()
    valid = {
        "Memory's not responding right now.",
        "I can't reach my long-term memory at the moment.",
    }
    assert phrase_for("qdrant_unavailable") in valid


def test_phrase_for_unknown_failure_mode_returns_none():
    reset_phrase_cache()
    assert phrase_for("nonexistent_failure_mode") is None


def test_phrase_for_cycles_without_repetition():
    """Each cycle visits every phrase once before repeating any."""
    reset_phrase_cache()
    pool = {
        "Memory's not responding right now.",
        "I can't reach my long-term memory at the moment.",
    }
    seen = set()
    for _ in range(len(pool)):
        seen.add(phrase_for("qdrant_unavailable"))
    assert seen == pool
