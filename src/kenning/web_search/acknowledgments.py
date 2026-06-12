"""Acknowledgment phrases for the web-search workflow.

When the gate decides a search is needed, Kenning speaks one of these
phrases immediately so the user isn't stuck in silence while Brave +
Jina + the LLM cycle through. Phrases stay in character (precise,
weighted, slightly menacing) and avoid the filler vocabulary explicitly
banned by the system prompt.
"""

from __future__ import annotations

import random
import threading
from typing import List

# Curated pool. Kept short -- the user shouldn't notice the same phrase
# twice in the same session. All preserve Kenning's voice (no
# "Of course!" / "Sure thing!" / etc).
_PHRASES: List[str] = [
    "Querying external sources.",
    "Consulting the network.",
    "Reaching out for fresh data.",
    "One moment.",
    "Acquiring current information.",
    "Pulling that from outside.",
    "Verifying against the network.",
    "Checking external feeds.",
]


class AcknowledgmentSource:
    """Round-robin shuffled acknowledgment-phrase generator.

    Shuffling means the user never hears the same phrase twice in a row,
    but each phrase shows up once per cycle so we don't repeat too often
    overall.
    """

    def __init__(self, phrases: List[str] = _PHRASES) -> None:
        if not phrases:
            raise ValueError("AcknowledgmentSource needs a non-empty phrase pool")
        self._pool = list(phrases)
        self._lock = threading.Lock()
        self._cycle: List[str] = []

    def next_phrase(self) -> str:
        with self._lock:
            if not self._cycle:
                self._cycle = list(self._pool)
                random.shuffle(self._cycle)
            return self._cycle.pop()
