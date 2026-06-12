"""Tests for the session export zip builder."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from kenning.events.export import (
    EXPORT_FORMAT_VERSION,
    SessionExport,
    export_session_to_bytes,
    export_session_to_path,
)
from kenning.events.models import StoredEvent
from kenning.events.store import MemoryEventStore


def _populate(store: MemoryEventStore, session_id: str, n: int = 3) -> list[StoredEvent]:
    saved: list[StoredEvent] = []
    for i in range(n):
        saved.append(
            store.save_event(
                StoredEvent.make(session_id, f"K{i}", payload={"i": i}, timestamp=float(i))
            )
        )
    return saved


def _read_zip(data: bytes) -> dict[str, str]:
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data), "r") as zh:
        for name in zh.namelist():
            out[name] = zh.read(name).decode("utf-8")
    return out


def test_export_to_bytes_contains_meta_and_events():
    store = MemoryEventStore()
    _populate(store, "sess", n=3)
    export = export_session_to_bytes(store, "sess")

    assert isinstance(export, SessionExport)
    assert export.session_id == "sess"
    assert export.event_count == 3
    assert export.chain_ok is True
    assert export.target_path is None

    contents = _read_zip(export.bytes)
    assert set(contents.keys()) == {"meta.json", "events.jsonl"}
    meta = json.loads(contents["meta.json"])
    assert meta["session_id"] == "sess"
    assert meta["format_version"] == EXPORT_FORMAT_VERSION
    assert meta["event_count"] == 3
    assert meta["chain"]["ok"] is True
    lines = [line for line in contents["events.jsonl"].splitlines() if line]
    assert len(lines) == 3


def test_export_redacts_kinds():
    store = MemoryEventStore()
    _populate(store, "sess", n=3)
    export = export_session_to_bytes(store, "sess", redact_kinds=["K1"])
    contents = _read_zip(export.bytes)
    rows = [json.loads(line) for line in contents["events.jsonl"].splitlines() if line]
    redacted = [r for r in rows if r["kind"] == "K1"]
    untouched = [r for r in rows if r["kind"] != "K1"]
    assert all(r["payload"] == {"__redacted__": True} for r in redacted)
    assert all("i" in r["payload"] for r in untouched)


def test_export_empty_session():
    store = MemoryEventStore()
    export = export_session_to_bytes(store, "empty")
    assert export.event_count == 0
    assert export.chain_ok is True
    contents = _read_zip(export.bytes)
    assert contents["events.jsonl"] == ""


def test_export_meta_carries_extra():
    store = MemoryEventStore()
    _populate(store, "sess", n=1)
    export = export_session_to_bytes(store, "sess", extra_meta={"build": "abc"})
    meta = json.loads(_read_zip(export.bytes)["meta.json"])
    assert meta["extra"]["build"] == "abc"


def test_export_to_path_writes_zip(tmp_path: Path):
    store = MemoryEventStore()
    _populate(store, "sess", n=2)
    out = tmp_path / "exports" / "sess.zip"
    export = export_session_to_path(store, "sess", out)
    assert export.target_path == out
    assert out.exists()
    assert out.read_bytes() == export.bytes


def test_export_to_path_creates_parent(tmp_path: Path):
    store = MemoryEventStore()
    _populate(store, "sess", n=1)
    out = tmp_path / "deep" / "nested" / "dir" / "sess.zip"
    export_session_to_path(store, "sess", out)
    assert out.exists()


def test_export_chain_broken_recorded():
    """When the persisted chain is corrupted, the export captures the breakage."""

    store = MemoryEventStore()
    saved = _populate(store, "sess", n=3)
    # Tamper directly in the memory store's internal state.
    store._sessions["sess"][1] = saved[1].with_chain_hashes(  # type: ignore[index]
        prev_hash=saved[1].chain_prev_hash,
        chain_hash="0" * 64,
    )
    export = export_session_to_bytes(store, "sess")
    assert export.chain_ok is False
    assert export.chain_broken_at_index == 1
    meta = json.loads(_read_zip(export.bytes)["meta.json"])
    assert meta["chain"]["ok"] is False
    assert meta["chain"]["broken_at_index"] == 1
