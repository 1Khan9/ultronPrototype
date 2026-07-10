"""Tests for :mod:`kenning.twitch.user_roster` — seen-login roster + fuzzy match.

Fully OFFLINE and lean: exercises only ``rapidfuzz`` + stdlib (no network, no
models, no creds), matching the anticheat posture of the module under test.

Coverage contract:

* exact match resolves to the login at a high score;
* mangled / phonetic STT (``john athan`` -> ``jonathan``) resolves;
* spelled-out single letters (``b o b`` -> ``bob``) normalize and resolve;
* an empty roster (and a no-real-match query) returns ``(None, ...)`` / a low
  best score, never a spurious hit;
* the size cap holds and evicts the OLDEST-observed login (LRU recency);
* concurrency smoke: many threads interleaving ``observe`` + ``match`` never
  corrupt the roster or raise.
"""

from __future__ import annotations

import threading

import pytest

from kenning.twitch.user_roster import (
    DEFAULT_MAX_SIZE,
    UserRoster,
    normalize_stt,
)

# --------------------------------------------------------------------------- #
# normalize_stt — the preprocessing contract
# --------------------------------------------------------------------------- #


def test_normalize_lowercases_and_strips_punctuation():
    assert normalize_stt("BOBBY!") == "bobby"
    assert normalize_stt("  xX_Sniper_Xx  ") == "xx sniper xx"


def test_normalize_collapses_whitespace():
    assert normalize_stt("john    smith") == "john smith"


def test_normalize_joins_spelled_out_letters():
    assert normalize_stt("b o b") == "bob"
    assert normalize_stt("b o b b y") == "bobby"
    assert normalize_stt("j d") == "jd"


def test_normalize_joins_letters_then_keeps_words():
    # leading spelled letters fuse, trailing word stays a separate token
    assert normalize_stt("x x sniper x x") == "xx sniper xx"


def test_normalize_drops_filler_words():
    assert normalize_stt("uh the guy named bobby") == "bobby"


def test_normalize_keeps_only_token_even_if_filler():
    # a login that equals a filler must survive — never normalize to empty
    assert normalize_stt("the") == "the"


def test_normalize_empty_and_punctuation_only():
    assert normalize_stt("") == ""
    assert normalize_stt("   ") == ""
    assert normalize_stt("!!!???") == ""
    assert normalize_stt(None) == ""  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# observe / load / membership
# --------------------------------------------------------------------------- #


def test_observe_records_login_canonicalized():
    r = UserRoster()
    r.observe("  JonAthan  ")
    assert "jonathan" in r
    assert "JONATHAN" in r  # __contains__ canonicalizes the probe too
    assert len(r) == 1
    assert r.usernames() == ["jonathan"]


def test_observe_ignores_blank_and_non_str():
    r = UserRoster()
    r.observe("")
    r.observe("   ")
    r.observe(None)  # type: ignore[arg-type]
    r.observe(12345)  # type: ignore[arg-type]
    assert len(r) == 0


def test_observe_many_and_load_seed_bulk():
    r = UserRoster()
    r.observe_many(["alice", "bob", "alice"])  # dup collapses
    assert len(r) == 2
    r.load(["carol", "dave"])
    assert len(r) == 4
    assert "carol" in r and "dave" in r


def test_observe_many_tolerates_none_iterable():
    r = UserRoster()
    r.observe_many(None)  # type: ignore[arg-type]
    assert len(r) == 0


def test_clear_empties_roster():
    r = UserRoster()
    r.load(["a", "b", "c"])
    r.clear()
    assert len(r) == 0
    assert r.best("a") == (None, 0.0)


# --------------------------------------------------------------------------- #
# match / best — exact, phonetic, spaced-letters
# --------------------------------------------------------------------------- #


def test_exact_match_scores_perfect():
    r = UserRoster()
    r.load(["jonathan", "bobby", "alice42"])
    login, score = r.best("jonathan")
    assert login == "jonathan"
    assert score == pytest.approx(100.0)


def test_mangled_phonetic_match_resolves():
    # the dominant STT failure: a single login split into syllables
    r = UserRoster()
    r.load(["jonathan", "streamerdude", "alice42"])
    login, score = r.best("john athan")
    assert login == "jonathan"
    assert score >= 80.0


def test_phonetic_near_miss_resolves():
    r = UserRoster()
    r.load(["jonathan", "bobby"])
    login, score = r.best("jonathon")  # 'a' -> 'o' STT slip
    assert login == "jonathan"
    assert score >= 80.0


def test_spaced_letters_resolve():
    r = UserRoster()
    r.load(["bob", "bobby", "alice"])
    login, score = r.best("b o b")
    assert login == "bob"
    assert score == pytest.approx(100.0)


def test_spaced_letters_with_trailing_word():
    r = UserRoster()
    r.load(["xx_sniper_xx", "streamerdude"])
    login, score = r.best("x x sniper x x")
    assert login == "xx_sniper_xx"
    assert score >= 80.0


def test_substring_handle_resolves():
    # STT often catches only the salient middle of a decorated handle. Logins
    # are stored canonical (lowercase) — Twitch logins are case-insensitive and
    # STT never recovers display-name casing — so the returned login is lowered.
    r = UserRoster()
    r.load(["xX_sniper_Xx", "streamerdude", "alice42"])
    login, score = r.best("sniper")
    assert login == "xx_sniper_xx"
    assert score >= 80.0


def test_match_returns_top_n_sorted_descending():
    r = UserRoster()
    r.load(["jon", "jonathan", "jonas", "alice", "bob"])
    results = r.match("jon", limit=3)
    assert len(results) == 3
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0][0] == "jon"  # exact wins
    # all returned logins are the jon* family, not the unrelated ones
    assert all(login.startswith("jon") for login, _ in results)


def test_match_limit_param_bounds_results():
    r = UserRoster()
    r.load(["alice", "alicia", "alison", "alec", "alan"])
    assert len(r.match("ali", limit=2)) == 2
    assert len(r.match("ali", limit=10)) == 5  # capped by roster size


def test_match_limit_zero_or_negative_returns_empty():
    r = UserRoster()
    r.load(["alice"])
    assert r.match("alice", limit=0) == []
    assert r.match("alice", limit=-1) == []


# --------------------------------------------------------------------------- #
# empty roster / no-match behavior
# --------------------------------------------------------------------------- #


def test_empty_roster_best_is_none():
    r = UserRoster()
    assert r.best("anybody") == (None, 0.0)
    assert r.match("anybody") == []


def test_empty_query_against_populated_roster():
    r = UserRoster()
    r.load(["alice", "bob"])
    assert r.best("") == (None, 0.0)
    assert r.best("!!!") == (None, 0.0)
    assert r.match("   ") == []


def test_no_real_match_scores_low():
    # a query bearing no resemblance to any login should score poorly, so a
    # caller threshold (e.g. >= 70) rejects it.
    r = UserRoster()
    r.load(["jonathan", "bobby", "alice42"])
    login, score = r.best("zxqwvk")
    # best() still names *a* nearest login, but the score must be clearly low
    assert score < 50.0


# --------------------------------------------------------------------------- #
# eviction cap
# --------------------------------------------------------------------------- #


def test_eviction_cap_holds():
    r = UserRoster(max_size=10)
    for i in range(25):
        r.observe(f"user{i}")
    assert len(r) == 10


def test_eviction_drops_oldest_observed():
    r = UserRoster(max_size=3)
    r.observe("first")
    r.observe("second")
    r.observe("third")
    assert set(r.usernames()) == {"first", "second", "third"}
    r.observe("fourth")  # overflow -> 'first' (oldest) evicted
    assert "first" not in r
    assert set(r.usernames()) == {"second", "third", "fourth"}


def test_reobserve_refreshes_recency_and_survives_eviction():
    r = UserRoster(max_size=3)
    r.observe("a")
    r.observe("b")
    r.observe("c")
    r.observe("a")  # touch 'a' -> now most-recent; 'b' is oldest
    r.observe("d")  # overflow -> 'b' evicted, NOT 'a'
    assert "a" in r
    assert "b" not in r
    assert set(r.usernames()) == {"a", "c", "d"}


def test_default_max_size_constant():
    assert DEFAULT_MAX_SIZE == 2000
    assert UserRoster()._max_size == 2000


def test_invalid_max_size_rejected():
    with pytest.raises(ValueError):
        UserRoster(max_size=0)
    with pytest.raises(ValueError):
        UserRoster(max_size=-5)


# --------------------------------------------------------------------------- #
# concurrency smoke
# --------------------------------------------------------------------------- #


def test_concurrency_observe_and_match_smoke():
    """Many threads interleave observe + match; no crash, roster stays bounded."""
    r = UserRoster(max_size=500)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def writer(base: int) -> None:
        try:
            barrier.wait()
            for i in range(400):
                r.observe(f"viewer_{base}_{i}")
        except BaseException as exc:  # noqa: BLE001 — record, fail in main thread
            errors.append(exc)

    def reader() -> None:
        try:
            barrier.wait()
            for _ in range(400):
                r.match("viewer mangled name", limit=3)
                r.best("v i e w e r")
                r.usernames()
                len(r)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(b,)) for b in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "thread did not finish"
    assert errors == [], f"concurrent access raised: {errors!r}"
    # cap strictly held under concurrent writers
    assert len(r) <= 500


def test_concurrency_match_during_eviction_churn():
    """A reader matching while a writer churns past the cap never raises."""
    r = UserRoster(max_size=50)
    stop = threading.Event()
    errors: list[BaseException] = []

    def churn() -> None:
        try:
            i = 0
            while not stop.is_set():
                r.observe(f"churn{i}")
                i += 1
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def matcher() -> None:
        try:
            for _ in range(2000):
                r.match("churn name", limit=3)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    w = threading.Thread(target=churn)
    m = threading.Thread(target=matcher)
    w.start()
    m.start()
    m.join(timeout=30)
    stop.set()
    w.join(timeout=30)

    assert errors == [], f"concurrent access raised: {errors!r}"
    assert len(r) <= 50


# ---------------------------------------------------------------------------
# Display-name retention (spec 12, 2026-07-09) — observe() optionally keeps the
# chatter's cased Twitch display name for @tag rendering.
# ---------------------------------------------------------------------------

def test_display_name_stored_and_returned():
    r = UserRoster()
    r.observe("xx_sniper_xx", "xX_Sniper_Xx")
    assert r.display_of("xx_sniper_xx") == "xX_Sniper_Xx"
    # lookup is canonicalized like observe (case/whitespace-insensitive)
    assert r.display_of("  XX_SNIPER_XX ") == "xX_Sniper_Xx"


def test_display_name_optional_and_never_erased_by_omission():
    r = UserRoster()
    r.observe("bob")                      # legacy single-arg call still works
    assert r.display_of("bob") is None
    r.observe("bob", "BobTheGreat")
    r.observe("bob")                      # re-observe WITHOUT display
    assert r.display_of("bob") == "BobTheGreat", "omitted display must not erase"


def test_display_name_updates_on_reobserve():
    r = UserRoster()
    r.observe("bob", "OldBob")
    r.observe("bob", "NewBob")
    assert r.display_of("bob") == "NewBob"


def test_display_name_blank_and_nonstring_ignored():
    r = UserRoster()
    r.observe("bob", "   ")
    assert r.display_of("bob") is None
    r.observe("bob", 42)  # type: ignore[arg-type]
    assert r.display_of("bob") is None


def test_display_of_unknown_or_invalid_login():
    r = UserRoster()
    assert r.display_of("ghost") is None
    assert r.display_of("") is None
    assert r.display_of(None) is None  # type: ignore[arg-type]


def test_display_evicted_in_lockstep_with_login():
    r = UserRoster(max_size=2)
    r.observe("a", "DispA")
    r.observe("b", "DispB")
    r.observe("c", "DispC")              # evicts "a"
    assert "a" not in r
    assert r.display_of("a") is None, "evicted login must drop its display too"
    assert r.display_of("b") == "DispB"
    assert r.display_of("c") == "DispC"
    # the internal display map never grows past the seen map (bounded memory)
    assert len(r._display) <= len(r._seen)


def test_clear_drops_display_names():
    r = UserRoster()
    r.observe("bob", "Bob")
    r.clear()
    assert r.display_of("bob") is None
