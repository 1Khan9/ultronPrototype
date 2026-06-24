"""UserRoster — a seen-username roster + fuzzy matcher for Twitch STT.

Twitch viewers address each other (and the streamer/bot) by voice through the
streamer's mic, but the STT layer mangles handles badly: it lowercases, drops
punctuation, splits a name into syllables (``jonathan`` -> ``john athan``), or
spells it out letter-by-letter (``b o b`` -> ``bob``). Matching that mangled
text back to a real chatter login is a fuzzy-string problem, so this module
keeps a rolling roster of usernames actually *observed* in chat and resolves an
STT phrase against it with :mod:`rapidfuzz`.

Design notes:

* **Observed-only.** Only logins we have actually seen in chat enter the roster
  (via :meth:`UserRoster.observe` / :meth:`observe_many` / :meth:`load`). The
  matcher therefore never invents a viewer who is not present, and the candidate
  set stays small (one channel's recent talkers), which keeps the fuzzy scan
  cheap and the false-match rate low.
* **Capped + LRU-ish eviction.** The roster is bounded (default 2000). When it
  overflows, the *oldest-observed* login is evicted. Re-observing a login
  refreshes its recency (it survives eviction longer) — an
  insertion-ordered dict gives O(1) move-to-end recency without a heap.
* **Monotonic timestamps.** Recency uses :func:`time.monotonic` so a wall-clock
  step (NTP, DST) can never reorder eviction.
* **Thread-safe.** A single re-entrant-free :class:`threading.Lock` guards every
  mutation and every read snapshot. The chat-ingest thread (``observe``) and the
  addressing/reply thread (``match``) run concurrently; all public methods are
  safe to call from any thread.
* **Robust normalization.** STT text is lowercased, punctuation-stripped,
  whitespace-collapsed, run-together single letters are joined into a word
  (``b o b`` -> ``bob``), and a small filler set (``uh``/``um``/``the`` …) is
  dropped before scoring.
* **Scorer.** :func:`rapidfuzz.fuzz.WRatio` is the primary scorer: empirically it
  handles the dominant STT failure modes — syllable splits, single-character
  drops/insertions, and substring handles (``sniper`` inside ``xX_sniper_Xx``) —
  better than ``token_set_ratio`` on this corpus, while still scoring 100 on the
  spelled-out / punctuated exact cases.

ANTICHEAT (BR-P1): lean imports only — :mod:`rapidfuzz` + stdlib (``re``,
``time``, ``threading``, ``collections``, ``typing``). No network, no models, no
desktop stack; this path sits beside the voice/relay code and stays
import-firewall-clean.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Iterable

from rapidfuzz import fuzz, process

__all__ = ["UserRoster", "normalize_stt"]

logger = __import__("logging").getLogger("kenning.twitch.user_roster")

# Default roster cap. One channel's recent talkers is far below this; the cap
# only bounds memory against a pathological flood of unique logins.
DEFAULT_MAX_SIZE = 2000

# Fillers a viewer's *speech* injects around a name that STT transcribes but
# which are never part of a Twitch login. Dropped during normalization so they
# cannot dilute the fuzzy score. Single-token only — multi-word handles are not
# fillers.
_FILLER_WORDS = frozenset(
    {
        "uh",
        "um",
        "uhh",
        "umm",
        "er",
        "ah",
        "hey",
        "yo",
        "the",
        "a",
        "an",
        "at",
        "to",
        "is",
        "this",
        "that",
        "guy",
        "dude",
        "user",
        "name",
        "username",
        "called",
        "named",
    }
)

# Strip everything that is not an ASCII letter/digit/space. Twitch logins are
# ``[a-z0-9_]{4,25}`` but STT never emits an underscore, so we also fold ``_`` to
# a space (handled by this class excluding it) — the join-single-letters pass
# then re-fuses any fragments. We keep only [a-z0-9 ] after lowercasing.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")


def normalize_stt(text: str) -> str:
    """Normalize a raw STT phrase to a stable, scorer-friendly form.

    Steps, in order:

    1. lowercase;
    2. replace every non ``[a-z0-9 ]`` run with a single space (drops
       punctuation, underscores, unicode);
    3. collapse whitespace;
    4. join a run of single-character tokens into one word
       (``b o b`` -> ``bob``, ``j d`` -> ``jd``) — STT spells handles out;
    5. drop filler tokens — but never drop the *only* remaining token, so a
       login that happens to equal a filler (e.g. a viewer literally named
       ``the``) still survives.

    Returns the normalized string (possibly empty for input that was all
    punctuation / whitespace).
    """
    if not text:
        return ""
    s = text.lower()
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return ""

    tokens = s.split(" ")

    # Pass 1: fuse consecutive single-character tokens into one word.
    fused: list[str] = []
    buf: list[str] = []
    for tok in tokens:
        if len(tok) == 1:
            buf.append(tok)
        else:
            if buf:
                fused.append("".join(buf))
                buf = []
            fused.append(tok)
    if buf:
        fused.append("".join(buf))

    # Pass 2: drop fillers, but keep at least one token so we never normalize a
    # real (filler-named) login down to the empty string.
    kept = [t for t in fused if t not in _FILLER_WORDS]
    if not kept:
        kept = fused

    return " ".join(kept)


class UserRoster:
    """Thread-safe, capped roster of observed Twitch logins with a fuzzy matcher.

    Parameters
    ----------
    max_size:
        Maximum number of distinct logins retained. When exceeded, the
        oldest-observed login is evicted. Must be a positive int.
    """

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        if not isinstance(max_size, int) or max_size <= 0:
            raise ValueError(f"max_size must be a positive int, got {max_size!r}")
        self._max_size = max_size
        self._lock = threading.Lock()
        # login -> monotonic last-seen timestamp. Insertion-ordered: the first
        # key is the oldest, so eviction pops the front. Re-observing moves the
        # key to the end (most-recent), so it survives eviction longer.
        self._seen: OrderedDict[str, float] = OrderedDict()

    # ----------------------------------------------------------------- ingest
    def observe(self, username: str) -> None:
        """Record one seen ``username``, refreshing its recency.

        Non-string, ``None``, or blank input is ignored (defensive — chat events
        are external, untrusted data). The stored key is the login lowercased and
        stripped; recency uses :func:`time.monotonic`.
        """
        login = self._canonical(username)
        if login is None:
            return
        ts = time.monotonic()
        with self._lock:
            # move-to-end on re-observe so recency reflects the latest sighting.
            if login in self._seen:
                self._seen.move_to_end(login)
            self._seen[login] = ts
            self._evict_locked()

    def observe_many(self, usernames: Iterable[str]) -> None:
        """Record each username in ``usernames`` (see :meth:`observe`)."""
        if usernames is None:
            return
        ts = time.monotonic()
        with self._lock:
            for raw in usernames:
                login = self._canonical(raw)
                if login is None:
                    continue
                if login in self._seen:
                    self._seen.move_to_end(login)
                self._seen[login] = ts
            self._evict_locked()

    def load(self, usernames: Iterable[str]) -> None:
        """Bulk-seed the roster from ``usernames`` (e.g. a chatter snapshot).

        Identical to :meth:`observe_many` but named for the seed-at-startup
        intent; insertion order is the iteration order, so the last item seeded
        is treated as most-recent.
        """
        self.observe_many(usernames)

    # ------------------------------------------------------------------ match
    def match(self, stt_text: str, limit: int = 3) -> list[tuple[str, float]]:
        """Return up to ``limit`` ``(login, score)`` best matches, score 0-100.

        ``stt_text`` is normalized via :func:`normalize_stt` before scoring. The
        result is sorted best-first. An empty roster, blank/empty-after-normalize
        input, or ``limit <= 0`` yields ``[]``. Scores are plain floats in
        ``[0, 100]`` (rapidfuzz's :func:`fuzz.WRatio`).
        """
        if limit is None or limit <= 0:
            return []
        query = normalize_stt(stt_text)
        if not query:
            return []

        with self._lock:
            if not self._seen:
                return []
            # Snapshot the candidate logins under the lock; scoring is done
            # OUTSIDE the lock so a large fuzzy scan never blocks ingest.
            choices = list(self._seen.keys())

        # process.extract preprocesses each choice with the SAME normalizer so a
        # login like ``xX_sniper_Xx`` is compared as ``xx sniper xx`` (the form
        # STT would ever produce), keeping the scorer phonetics-aligned.
        extracted = process.extract(
            query,
            choices,
            scorer=fuzz.WRatio,
            processor=normalize_stt,
            limit=limit,
        )
        # process.extract yields (choice, score, index) — drop the index.
        return [(choice, float(score)) for choice, score, _index in extracted]

    def best(self, stt_text: str) -> tuple[str | None, float]:
        """Return the single best ``(login, score)`` or ``(None, 0.0)``.

        Convenience over :meth:`match` with ``limit=1``; returns ``(None, 0.0)``
        when there is no candidate (empty roster / empty query).
        """
        top = self.match(stt_text, limit=1)
        if not top:
            return (None, 0.0)
        return top[0]

    # --------------------------------------------------------------- introspect
    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)

    def __contains__(self, username: object) -> bool:
        if not isinstance(username, str):
            return False
        login = self._canonical(username)
        if login is None:
            return False
        with self._lock:
            return login in self._seen

    def usernames(self) -> list[str]:
        """Return the current roster logins, oldest-observed first (a snapshot)."""
        with self._lock:
            return list(self._seen.keys())

    def clear(self) -> None:
        """Drop every observed login."""
        with self._lock:
            self._seen.clear()

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _canonical(username: object) -> str | None:
        """Lowercase/strip a login; return ``None`` for non-str/blank input."""
        if not isinstance(username, str):
            return None
        login = username.strip().lower()
        if not login:
            return None
        return login

    def _evict_locked(self) -> None:
        """Evict oldest entries until size <= max_size. Caller holds the lock."""
        while len(self._seen) > self._max_size:
            # popitem(last=False) removes the front = oldest-observed key.
            self._seen.popitem(last=False)
