"""Tests for inter-tool sentinel parsing (catalog T17)."""

from __future__ import annotations

from kenning.coding import sentinels as S


# ---------------------------------------------------------------------------
# Constant invariants
# ---------------------------------------------------------------------------


def test_pair_sentinels_are_ascii_and_unique():
    seen = set()
    for marker in S.PAIR_SENTINELS:
        assert marker.isascii()
        assert marker.startswith("<<") and marker.endswith(">>")
        assert marker not in seen
        seen.add(marker)


def test_single_sentinels_are_ascii_and_unique():
    seen = set()
    for marker in S.SINGLE_SENTINELS:
        assert marker.isascii()
        assert marker.startswith("###") and marker.endswith("###")
        assert marker not in seen
        seen.add(marker)


def test_pair_and_single_sentinels_do_not_overlap():
    pair = set(S.PAIR_SENTINELS)
    single = set(S.SINGLE_SENTINELS)
    assert not (pair & single)


def test_known_sentinels_present():
    # Spot-check the names the rest of the codebase imports.
    assert S.KENNING_SUBMIT in S.PAIR_SENTINELS
    assert S.KENNING_SUBMIT_DIFF in S.PAIR_SENTINELS
    assert S.KENNING_EXIT_FORFEIT in S.SINGLE_SENTINELS
    assert S.KENNING_LINT_REVERT in S.SINGLE_SENTINELS


# ---------------------------------------------------------------------------
# observation_scan
# ---------------------------------------------------------------------------


def test_observation_scan_empty_returns_empty():
    assert S.observation_scan("") == []
    assert S.observation_scan(None) == []  # type: ignore[arg-type]


def test_observation_scan_no_match():
    matches = S.observation_scan("just regular tool output\nnothing fancy")
    assert matches == []


def test_observation_scan_pair_marker_with_payload():
    text = f"prefix {S.KENNING_SUBMIT}diff body here{S.KENNING_SUBMIT} suffix"
    matches = S.observation_scan(text)
    assert len(matches) == 1
    m = matches[0]
    assert m.sentinel == S.KENNING_SUBMIT
    assert m.payload == "diff body here"
    assert text[m.start:m.end].startswith(S.KENNING_SUBMIT)
    assert text[m.start:m.end].endswith(S.KENNING_SUBMIT)


def test_observation_scan_unterminated_pair_marker_treated_as_signal():
    text = f"saw {S.KENNING_TEST_SWEEP_PASS} but no close"
    matches = S.observation_scan(text)
    assert len(matches) == 1
    assert matches[0].sentinel == S.KENNING_TEST_SWEEP_PASS
    assert matches[0].payload == ""


def test_observation_scan_single_fire_no_payload():
    text = f"agent emitted {S.KENNING_EXIT_FORFEIT} -- bail"
    matches = S.observation_scan(text)
    assert len(matches) == 1
    assert matches[0].sentinel == S.KENNING_EXIT_FORFEIT
    assert matches[0].payload is None


def test_observation_scan_multiple_matches_in_order():
    text = (
        "first "
        f"{S.KENNING_LINT_REVERT}"
        " then "
        f"{S.KENNING_EXIT_FORFEIT}"
        " plus "
        f"{S.KENNING_TEST_SWEEP_PASS}clean{S.KENNING_TEST_SWEEP_PASS}"
    )
    matches = S.observation_scan(text)
    assert [m.sentinel for m in matches] == [
        S.KENNING_LINT_REVERT,
        S.KENNING_EXIT_FORFEIT,
        S.KENNING_TEST_SWEEP_PASS,
    ]
    assert matches[-1].payload == "clean"


def test_observation_scan_pair_marker_preferred_over_single_at_same_pos():
    # Construct text where a hypothetical single sentinel sits at the
    # same start as a longer pair marker; pair should win because it's
    # longer (length-ordered preference).
    payload = "diff"
    text = f"{S.KENNING_SUBMIT_DIFF}{payload}{S.KENNING_SUBMIT_DIFF}"
    matches = S.observation_scan(text)
    assert len(matches) == 1
    assert matches[0].sentinel == S.KENNING_SUBMIT_DIFF
    assert matches[0].payload == payload


def test_observation_scan_pair_marker_empty_payload():
    text = f"{S.KENNING_TEST_SWEEP_PASS}{S.KENNING_TEST_SWEEP_PASS}"
    matches = S.observation_scan(text)
    assert len(matches) == 1
    assert matches[0].payload == ""


def test_observation_scan_payload_with_special_chars():
    payload = "diff with <html>tags</html> and \"quotes\" and {braces}"
    text = f"{S.KENNING_SUBMIT}{payload}{S.KENNING_SUBMIT}"
    matches = S.observation_scan(text)
    assert matches[0].payload == payload


def test_observation_scan_two_pair_payloads_in_sequence():
    text = (
        f"{S.KENNING_SUBMIT}first{S.KENNING_SUBMIT}"
        " gap "
        f"{S.KENNING_SUBMIT}second{S.KENNING_SUBMIT}"
    )
    matches = S.observation_scan(text)
    assert [m.payload for m in matches] == ["first", "second"]


def test_observation_scan_custom_sentinel_sets():
    custom_pair = ("<<CUSTOM>>",)
    custom_single = ("###X###",)
    text = "<<CUSTOM>>data<<CUSTOM>> and ###X### plus noise"
    matches = S.observation_scan(
        text, pair_sentinels=custom_pair, single_sentinels=custom_single
    )
    assert [m.sentinel for m in matches] == ["<<CUSTOM>>", "###X###"]
    assert matches[0].payload == "data"


def test_observation_scan_ignores_empty_sentinel_in_overrides():
    # Defensive: empty-string overrides shouldn't infinite-loop.
    matches = S.observation_scan(
        "anything", pair_sentinels=("",), single_sentinels=("",)
    )
    assert matches == []


# ---------------------------------------------------------------------------
# first_match
# ---------------------------------------------------------------------------


def test_first_match_returns_first_pair_marker():
    text = (
        f"a{S.KENNING_SUBMIT}one{S.KENNING_SUBMIT}"
        f"b{S.KENNING_SUBMIT}two{S.KENNING_SUBMIT}"
    )
    m = S.first_match(text, sentinel=S.KENNING_SUBMIT)
    assert m is not None
    assert m.payload == "one"


def test_first_match_returns_none_when_missing():
    assert S.first_match("clean output", sentinel=S.KENNING_EXIT_FORFEIT) is None


def test_first_match_handles_single_sentinel():
    text = f"some {S.KENNING_EXIT_FORFEIT} text"
    m = S.first_match(text, sentinel=S.KENNING_EXIT_FORFEIT)
    assert m is not None
    assert m.payload is None


def test_first_match_accepts_unknown_sentinel_as_single_fire():
    # Useful for ad-hoc markers in tests / one-off tools.
    custom = "###ADHOC###"
    text = f"hello {custom} world"
    m = S.first_match(text, sentinel=custom)
    assert m is not None
    assert m.sentinel == custom
    assert m.payload is None


# ---------------------------------------------------------------------------
# strip_sentinels
# ---------------------------------------------------------------------------


def test_strip_sentinels_removes_pair_marker_and_payload():
    text = (
        "before "
        f"{S.KENNING_SUBMIT_DIFF}---patch---{S.KENNING_SUBMIT_DIFF}"
        " after"
    )
    stripped = S.strip_sentinels(text)
    assert "before " in stripped
    assert "after" in stripped
    assert S.KENNING_SUBMIT_DIFF not in stripped
    assert "---patch---" not in stripped


def test_strip_sentinels_removes_single_fire():
    text = f"hi {S.KENNING_EXIT_FORFEIT} bye"
    stripped = S.strip_sentinels(text)
    assert S.KENNING_EXIT_FORFEIT not in stripped
    assert stripped.startswith("hi ")
    assert stripped.endswith(" bye")


def test_strip_sentinels_preserves_natural_text():
    text = "no sentinels here"
    assert S.strip_sentinels(text) == text


def test_strip_sentinels_empty_input():
    assert S.strip_sentinels("") == ""
    assert S.strip_sentinels(None) == ""  # type: ignore[arg-type]


def test_strip_sentinels_multiple_markers():
    text = (
        f"{S.KENNING_LINT_REVERT}"
        " gap "
        f"{S.KENNING_TEST_SWEEP_PASS}ok{S.KENNING_TEST_SWEEP_PASS}"
        " end"
    )
    stripped = S.strip_sentinels(text)
    assert stripped == " gap  end"
