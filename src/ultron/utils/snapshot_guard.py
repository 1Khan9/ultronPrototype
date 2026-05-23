"""Snapshot-identity race protection for background work.

Pattern lifted in spirit (not in source) from aider's
``base_coder.summarize_start``/``summarize_end`` machinery. Apache 2.0
attribution in ``THIRD_PARTY_NOTICES.md``.

The problem: a foreground thread launches background work against a
snapshot of mutable state. While the background work runs, the
foreground may have mutated the state further (a new user turn, a new
edit, a new event in the queue). When the background work completes,
blindly applying its result clobbers the newer foreground state — a
"ghost write" race.

The fix: capture an identity-stable snapshot at launch time. When the
background work returns, compare *current* state against the captured
snapshot. Match → apply. Mismatch → discard silently, foreground wins.

Two flavours are provided:

  * :func:`take` + :func:`matches` — functional API. Deep-copies the
    object at capture time, compares with ``==`` at check time. Best
    for small structured state like a list-of-dicts message log.
  * :class:`SnapshotGuard` — class with keyed snapshots, useful when
    one supervisor holds several pending background jobs (e.g. an
    LLM summary AND a digest write AND a project-index refresh, each
    keyed by a job name).

When state is too large to deep-copy cheaply, callers can compose
:func:`take` with a custom fingerprinting step (e.g. snapshot the
length and last item's hash, not the whole list).

Thread safety: capture and compare are atomic with respect to a single
Python reference. Concurrent mutation between ``take`` and ``matches``
on the same object IS the use case — the comparison just answers
"did anything change?" honestly.
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import Any, Dict, Optional


logger = logging.getLogger("ultron.utils.snapshot_guard")


# A unique sentinel that callers can compare to. The opaque value is
# carried by-reference; never compared to user data.
class _SnapshotToken:
    """Opaque value returned by :func:`take`. Hashable, immutable.

    Holds a deep copy of the captured object so subsequent mutations
    of the original do not bleed into the captured value.
    """

    __slots__ = ("_value", "_repr")

    def __init__(self, value: Any) -> None:
        try:
            self._value = copy.deepcopy(value)
        except (TypeError, copy.Error):
            # Some objects (e.g. open files, threads) reject deepcopy.
            # Fall back to a shallow copy: better than nothing, and
            # callers that care can pass a deep_copy=False flag.
            try:
                self._value = copy.copy(value)
            except (TypeError, copy.Error):
                self._value = value  # last-ditch: capture the reference
        self._repr = f"_SnapshotToken({type(value).__name__}@{id(value):x})"

    def equals(self, current: Any) -> bool:
        return self._value == current

    def __repr__(self) -> str:
        return self._repr


def take(obj: Any, *, deep: bool = True) -> _SnapshotToken:
    """Capture a snapshot of ``obj`` for later comparison.

    Args:
        obj: Any object. For best results, pass a structurally
            comparable value (list, dict, dataclass) whose ``==`` is
            content-based.
        deep: Deep-copy the value (default). Pass False to capture a
            shallow copy — useful for objects whose elements cannot be
            deep-copied (e.g. include sockets or threads).

    Returns:
        A :class:`_SnapshotToken`. Treat it as opaque; pass it later
        to :func:`matches` together with the (possibly mutated) live
        object.
    """
    token = _SnapshotToken.__new__(_SnapshotToken)
    if deep:
        try:
            token._value = copy.deepcopy(obj)
        except (TypeError, copy.Error):
            token._value = copy.copy(obj)
    else:
        token._value = copy.copy(obj)
    token._repr = f"_SnapshotToken({type(obj).__name__}@{id(obj):x})"
    return token


def matches(token: _SnapshotToken, current: Any) -> bool:
    """Return True iff ``current`` still equals the captured snapshot.

    Equality is per Python's ``==`` (structural for stdlib collections,
    field-by-field for ``@dataclass``-like objects).
    """
    if not isinstance(token, _SnapshotToken):
        raise TypeError(
            f"token must come from snapshot_guard.take(), got "
            f"{type(token).__name__}"
        )
    return token.equals(current)


class StaleSnapshotError(Exception):
    """Raised by :meth:`SnapshotGuard.require` when state has changed."""


class SnapshotGuard:
    """Keyed snapshot store for supervisors juggling multiple jobs.

    Usage::

        guard = SnapshotGuard()
        guard.snapshot("summary", self.messages)
        # ... background work runs ...
        if guard.unchanged("summary", self.messages):
            self.apply(result)
        guard.drop("summary")

    Methods are thread-safe — internal locking guards the keyed map.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: Dict[str, _SnapshotToken] = {}

    def snapshot(self, key: str, value: Any, *, deep: bool = True) -> None:
        """Capture ``value`` under ``key``. Overwrites any prior snapshot."""
        token = take(value, deep=deep)
        with self._lock:
            self._tokens[key] = token

    def unchanged(self, key: str, current: Any) -> bool:
        """Return True iff ``current`` matches the snapshot at ``key``.

        Returns False if no snapshot exists at that key — treat the
        absence as "you never asked, so we have nothing to compare".
        """
        with self._lock:
            token = self._tokens.get(key)
        if token is None:
            return False
        return token.equals(current)

    def require(self, key: str, current: Any) -> None:
        """Raise :class:`StaleSnapshotError` when state has drifted."""
        if not self.unchanged(key, current):
            raise StaleSnapshotError(
                f"snapshot {key!r} no longer matches live state"
            )

    def drop(self, key: str) -> None:
        """Forget the snapshot at ``key`` (no-op if absent)."""
        with self._lock:
            self._tokens.pop(key, None)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._tokens

    def clear(self) -> None:
        """Forget every snapshot."""
        with self._lock:
            self._tokens.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._tokens)


__all__ = [
    "SnapshotGuard",
    "StaleSnapshotError",
    "matches",
    "take",
]
