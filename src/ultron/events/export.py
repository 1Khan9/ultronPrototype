"""Session-export zip builder.

The OpenHands V1 server's ``export_conversation`` method zips every event
+ a ``meta.json`` for a downloadable trajectory. Ultron's analog lives
here -- ``export_session_to_bytes`` returns an in-memory zip; the path
variant writes to disk via the idempotent installer for the
"send Anthropic / GitHub a reproducer" use case.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ultron.events.chain import verify_chain
from ultron.events.models import StoredEvent
from ultron.events.store import EventStore

logger = logging.getLogger(__name__)

EXPORT_FORMAT_VERSION = "1.0"


@dataclass(frozen=True)
class SessionExport:
    """Result of :func:`export_session_to_bytes` / :func:`export_session_to_path`."""

    session_id: str
    event_count: int
    bytes: bytes
    chain_ok: bool
    chain_broken_at_index: int | None = None
    target_path: Path | None = None


def export_session_to_bytes(
    store: EventStore,
    session_id: str,
    *,
    redact_kinds: Iterable[str] | None = None,
    extra_meta: dict | None = None,
) -> SessionExport:
    """Build an in-memory zip of every event in ``session_id``.

    Layout:
        ``meta.json`` -- export metadata + chain-verification summary.
        ``events.jsonl`` -- one JSON event per line (canonical order).

    When ``redact_kinds`` is supplied, events of those kinds keep their
    metadata + chain fields but have their ``payload`` replaced with an
    empty mapping. The chain still verifies because the hash input
    excludes the redacted payload -- the export contract says hashes
    are over the canonical event encoding which is what was originally
    persisted, so redaction post-export does NOT touch chain integrity
    on the live store (callers redact only the zipped copy).
    """

    redact_set = set(redact_kinds) if redact_kinds else set()
    events: list[StoredEvent] = list(store.iter_events(session_id))
    chain_result = verify_chain(events)

    output_buffer = io.BytesIO()
    with zipfile.ZipFile(output_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_handle:
        events_lines: list[str] = []
        for event in events:
            row = event.to_dict()
            if event.kind in redact_set:
                row["payload"] = {"__redacted__": True}
            events_lines.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
        zip_handle.writestr("events.jsonl", "\n".join(events_lines))
        meta = {
            "format_version": EXPORT_FORMAT_VERSION,
            "session_id": session_id,
            "exported_at": time.time(),
            "event_count": len(events),
            "redacted_kinds": sorted(redact_set),
            "chain": {
                "ok": chain_result.ok,
                "events_checked": chain_result.events_checked,
                "broken_at_index": chain_result.broken_at_index,
                "broken_event_id": chain_result.broken_event_id,
                "notes": list(chain_result.notes),
            },
            "sha256_of_events_jsonl": _sha256_of("\n".join(events_lines)),
            "extra": dict(extra_meta or {}),
        }
        zip_handle.writestr("meta.json", json.dumps(meta, indent=2, ensure_ascii=False))

    raw_bytes = output_buffer.getvalue()
    return SessionExport(
        session_id=session_id,
        event_count=len(events),
        bytes=raw_bytes,
        chain_ok=chain_result.ok,
        chain_broken_at_index=chain_result.broken_at_index,
    )


def export_session_to_path(
    store: EventStore,
    session_id: str,
    target: Path | str,
    *,
    redact_kinds: Iterable[str] | None = None,
    extra_meta: dict | None = None,
) -> SessionExport:
    """Materialise the export to disk.

    The target directory is created if needed. Existing files at
    ``target`` are overwritten -- exports are reproducible artefacts,
    not append-only logs, so re-running gives a fresh snapshot.
    """

    target_path = Path(target)
    export = export_session_to_bytes(
        store,
        session_id,
        redact_kinds=redact_kinds,
        extra_meta=extra_meta,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(export.bytes)
    return SessionExport(
        session_id=export.session_id,
        event_count=export.event_count,
        bytes=export.bytes,
        chain_ok=export.chain_ok,
        chain_broken_at_index=export.chain_broken_at_index,
        target_path=target_path,
    )


def _sha256_of(text: str) -> str:
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()
