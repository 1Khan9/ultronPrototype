"""One-shot migration: read data/memory.jsonl into the Qdrant store.

Idempotent. Skips turns whose ``turn_id`` is already present in the
collection. Run from anywhere; resolves paths from ``config.settings``.

Usage:
    python scripts/migrate_memory_to_qdrant.py
    python scripts/migrate_memory_to_qdrant.py --dry-run
    python scripts/migrate_memory_to_qdrant.py --reset    # WIPE Qdrant first
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import List

# Reach the main checkout (where models + memory.jsonl live).
_HERE = Path(__file__).resolve()
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from config import settings  # noqa: E402


def _load_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  skipping malformed line {line_num}: {e}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="print plan without writing")
    parser.add_argument("--reset", action="store_true",
                        help="DELETE the conversations collection first")
    parser.add_argument(
        "--source",
        type=Path,
        default=settings.MEMORY_JSONL_PATH,
        help="JSONL source (default: data/memory.jsonl)",
    )
    args = parser.parse_args()

    source: Path = args.source
    print(f"Source: {source}")
    print(f"Target Qdrant: {settings.MEMORY_QDRANT_PATH}")
    print(f"Collection:    {settings.MEMORY_QDRANT_CONVERSATIONS}\n")

    rows = _load_jsonl(source)
    print(f"Loaded {len(rows)} rows from JSONL")
    if not rows:
        print("Nothing to migrate.")
        return 0

    if args.dry_run:
        print("DRY RUN -- no writes. Sample row:")
        print(f"  {json.dumps(rows[0], ensure_ascii=False)}")
        return 0

    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        SparseVector,
        SparseVectorParams,
        VectorParams,
    )
    from kenning.memory.embedder import HybridEmbedder

    if args.reset and settings.MEMORY_QDRANT_PATH.exists():
        # Embedded Qdrant doesn't always release files on delete_collection;
        # blow the directory away and let the create path rebuild from
        # scratch instead.
        shutil.rmtree(settings.MEMORY_QDRANT_PATH)
        print(f"Removed Qdrant directory {settings.MEMORY_QDRANT_PATH}")
    settings.MEMORY_QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    client = QdrantClient(path=str(settings.MEMORY_QDRANT_PATH))

    existing = {c.name for c in client.get_collections().collections}
    if settings.MEMORY_QDRANT_CONVERSATIONS not in existing:
        client.create_collection(
            collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
            vectors_config={"dense": VectorParams(size=settings.MEMORY_DENSE_DIM,
                                                  distance=Distance.COSINE)},
            sparse_vectors_config={"bm25": SparseVectorParams()},
        )
        print(f"Created collection {settings.MEMORY_QDRANT_CONVERSATIONS}")

    # Find existing turn_ids so we can skip duplicates (idempotent re-run).
    existing_ids: set[int] = set()
    try:
        offset = None
        while True:
            page, offset = client.scroll(
                collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
                limit=512,
                with_payload=True,
                with_vectors=False,
                offset=offset,
            )
            for pt in page:
                tid = (pt.payload or {}).get("turn_id")
                if tid is not None:
                    existing_ids.add(int(tid))
            if offset is None:
                break
    except Exception as e:
        print(f"  (couldn't enumerate existing ids: {e})")
    print(f"Already in Qdrant: {len(existing_ids)} turns -- will skip those\n")

    pending = [r for r in rows if int(r.get("id", -1)) not in existing_ids]
    if not pending:
        print("All rows already migrated. Nothing to do.")
        client.close()
        return 0
    print(f"Migrating {len(pending)} new turns...")

    print("Loading HybridEmbedder (CPU)...")
    embedder = HybridEmbedder(eager=True)

    # Encode + upsert in batches so memory stays bounded for big histories.
    BATCH = 64
    written = 0
    t0 = time.monotonic()
    for batch_start in range(0, len(pending), BATCH):
        batch = pending[batch_start: batch_start + BATCH]
        dense_texts = [f"{r.get('role', '')}: {r.get('content', '')}" for r in batch]
        sparse_texts = [r.get("content", "") for r in batch]

        dvecs = embedder.encode_dense(dense_texts)
        svecs = embedder.encode_sparse(sparse_texts)

        points = []
        for r, dv, sv in zip(batch, dvecs, svecs):
            tid = int(r.get("id", 0))
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector={
                    "dense": dv.tolist(),
                    "bm25": SparseVector(indices=sv.indices, values=sv.values),
                },
                payload={
                    "turn_id": tid,
                    "ts": float(r.get("ts", 0.0)),
                    "role": str(r.get("role", "")),
                    "content": str(r.get("content", "")),
                    "session_id": str(r.get("session_id", "migrated-jsonl")),
                    "summary": "",
                    "entities": [],
                    "topic_tags": [],
                    "cluster_id": None,
                },
            ))
        client.upsert(
            collection_name=settings.MEMORY_QDRANT_CONVERSATIONS,
            points=points,
        )
        written += len(points)
        print(f"  upserted {written}/{len(pending)}")

    elapsed = time.monotonic() - t0
    print(f"\nMigrated {written} turns in {elapsed:.1f}s ({elapsed/max(written,1)*1000:.0f} ms/turn)")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
