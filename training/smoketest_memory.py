"""Manual smoketest for the Qdrant-backed memory module.

Phase 3+ replaced the JSONL/MiniLM stack with a Qdrant + bge-small + BM25
hybrid. This script exercises a fresh ephemeral store end-to-end.

Run from anywhere; it points at a tempdir Qdrant.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"C:\STC\ultronPrototype")
sys.path.insert(0, r"C:\STC\ultronPrototype\src")

from ultron.memory import ConversationMemory, HybridEmbedder

emb = HybridEmbedder(eager=True)
print(f"HybridEmbedder ready (dim={emb.dim})")

with tempfile.TemporaryDirectory() as d:
    qdrant_dir = Path(d) / "qdrant"
    mem = ConversationMemory(path=qdrant_dir, embedder=emb)
    mem.add("user", "we decided to use sqlite for the cache")
    mem.add("assistant", "noted")
    mem.add("user", "lets refactor the auth module")
    mem.add("assistant", "okay")
    mem.add("user", "whats the weather today")
    mem.add("assistant", "i dont have a sensor for that")

    # Drain async writes before searching.
    import time
    time.sleep(1.5)

    # Query something semantically near the auth turn but using different words.
    hits = mem.retrieve("rewrite the login flow", k=2, exclude_recent=2)
    print('hybrid hits for "rewrite the login flow":')
    for h in hits:
        print(f"  - [{h.id}] {h.role}: {h.content}")

    mem.close()
