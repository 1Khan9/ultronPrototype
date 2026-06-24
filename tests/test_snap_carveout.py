"""Snap carve-out (2026-06-24): under route-all, a SHORT SINGLE TACTICAL snap
callout (+ a bare hello) routes back to the DETERMINISTIC pool; strings, questions,
ask-forms, social/identity/reported, and conversational lines stay on the LLM.

These pin the user's exact examples so a future routing change can't silently leak
a conversational/social line into the deterministic pool (or vice-versa). The
carve-out is ADDITIVE: it only flips _u1_route OFF for a qualifying command, reusing
the existing deterministic path -- the full snap pool stays revertible.

Routing is asserted by whether the LLM ``generate_fn`` is CALLED -- that is the
deterministic-vs-LLM decision. (A marker in the LLM output is unreliable: the
relay path's fact-preservation guard rejects a non-fact-preserving LLM line and
falls back to the deterministic literal, so the marker never survives.)
"""
from __future__ import annotations

import pytest

from kenning.audio.relay_speech import (
    RelayCommand,
    _is_carveout_snap,
    build_relay_line,
    set_flavor_tails_enabled,
    set_snap_carveout_enabled,
    set_u1_llm_route_enabled,
)


@pytest.fixture(autouse=True)
def _route_all_on():
    """Carve-out only matters under route-all; match the app's flavor-OFF default
    (crisp tail-free callouts). Reset all three flags after each test."""
    set_u1_llm_route_enabled(True)
    set_snap_carveout_enabled(True)
    set_flavor_tails_enabled(False)
    yield
    set_u1_llm_route_enabled(False)
    set_snap_carveout_enabled(True)
    set_flavor_tails_enabled(True)


def _route_and_count(cmd):
    """Run ``build_relay_line`` with a counting LLM stub. Returns (line, n_llm_calls).
    n_llm_calls == 0 -> the deterministic path was taken; >= 1 -> the LLM path."""
    calls = []

    def _gen(prompt):
        calls.append(prompt)
        return iter(["Copy that."])

    line = build_relay_line(cmd, generate_fn=_gen, rephrase=True)
    return line, len(calls)


# --------------------------------------------------------------------------
# Discriminator -- the SHORT SINGLE TACTICAL snaps the user OK'd as deterministic.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", [
    RelayCommand(payload="rush B", raw_text="tell my team to rush B"),
    RelayCommand(payload="I am lurking", raw_text="tell my team I am lurking"),
    RelayCommand(payload="I am flanking", raw_text="tell my team I am flanking"),
    RelayCommand(payload="sova hit 85", raw_text="sova hit 85"),
    RelayCommand(payload="one back site", raw_text="one backsite"),
    RelayCommand(payload="I am rotating", raw_text="tell my team im rotating"),
    RelayCommand(payload="hello", raw_text="hello", directive="hello"),
])
def test_carveout_accepts_short_single_tactical(cmd):
    assert _is_carveout_snap(cmd) is True


# --------------------------------------------------------------------------
# Discriminator -- the things that MUST stay on the LLM (user was emphatic).
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cmd", [
    # ask-forms (compose = Ultron authors a request)
    RelayCommand(payload="drop me his sheriff", raw_text="ask iso to drop me his sheriff", compose=True),
    RelayCommand(payload="heal me", raw_text="ask sage to heal me", compose=True),
    # ask-forms phrased as questions
    RelayCommand(payload="does she have a heal?", raw_text="ask sage if she has a heal"),
    RelayCommand(payload="why aren't they smoking?", raw_text="ask my team why they arent smoking"),
    # reported / social / identity (context or compose)
    RelayCommand(payload="respond", raw_text="jett is flaming you",
                 context="Jett is flaming you", directive="respond"),
    RelayCommand(payload="respond", raw_text="sage called you a soundboard",
                 context="Sage called you a soundboard", directive="respond"),
    RelayCommand(payload="respond", raw_text="reyna asked if you are a voice changer",
                 context="Reyna asked if you are a voice changer", directive="respond"),
    # strung-together callouts (conjunction / comma)
    RelayCommand(payload="push B and rotate mid", raw_text="tell my team push B and rotate mid"),
    RelayCommand(payload="they have spike, push A", raw_text="..."),
    # social directive (courtesy question)
    RelayCommand(payload="how are you", raw_text="ask the team how their day is going",
                 directive="ask_day"),
    # verbatim is already deterministic -- carve-out must not claim it
    RelayCommand(payload="gg wp", raw_text="say to my team word for word gg wp", verbatim=True),
    # long / conversational
    RelayCommand(payload="they should be smoking mid window every single round",
                 raw_text="tell my team they should be smoking mid window every round"),
])
def test_carveout_rejects_nontactical(cmd):
    assert _is_carveout_snap(cmd) is False


# --------------------------------------------------------------------------
# End-to-end routing -- did the deterministic path or the LLM path run?
# --------------------------------------------------------------------------
def test_tactical_snaps_go_deterministic_not_llm():
    for cmd in (
        RelayCommand(payload="rush B", raw_text="tell my team to rush B"),
        RelayCommand(payload="I am lurking", raw_text="tell my team I am lurking"),
        RelayCommand(payload="sova hit 85", raw_text="sova hit 85"),
        RelayCommand(payload="one back site", raw_text="one backsite"),
        RelayCommand(payload="I am rotating", raw_text="tell my team im rotating"),
    ):
        line, n = _route_and_count(cmd)
        assert n == 0, f"{cmd.payload!r} should be deterministic, LLM was called {n}x"
        assert line.strip()


def test_hello_is_deterministic_and_just_hello():
    cmd = RelayCommand(payload="hello", raw_text="say hello", directive="hello", addressee="team")
    line, n = _route_and_count(cmd)
    assert n == 0, "hello should be deterministic"
    assert line.strip().lower() == "hello.", f"expected 'Hello.', got {line!r}"


def test_carveout_is_noop_for_nontactical():
    """The carve-out must ONLY touch tactical snaps -- for everything else the
    routing is identical whether it is ON or OFF (it never claims a non-snap).
    This is the additive guarantee for the LLM side: ask-forms, reported/social,
    compounds, and questions route exactly as full-route-all does."""
    nontactical = (
        RelayCommand(payload="push B and rotate mid", raw_text="..."),
        RelayCommand(payload="heal me", raw_text="ask sage to heal me", compose=True),
        RelayCommand(payload="respond", raw_text="jett is flaming you",
                     context="Jett is flaming you", directive="respond"),
        RelayCommand(payload="they should be smoking mid window every single round",
                     raw_text="..."),
    )
    for cmd in nontactical:
        set_snap_carveout_enabled(True)
        _l_on, n_on = _route_and_count(cmd)
        set_snap_carveout_enabled(False)
        _l_off, n_off = _route_and_count(cmd)
        assert n_on == n_off, (
            f"carve-out changed routing for non-tactical {cmd.payload!r}: "
            f"on={n_on} off={n_off}")


def test_carveout_off_sends_everything_to_llm():
    """The stop-button 'full LLM' mode: with the carve-out disabled, even a clean
    tactical snap goes to the LLM (absolutely everything routes through it)."""
    set_snap_carveout_enabled(False)
    _line, n = _route_and_count(
        RelayCommand(payload="rush B", raw_text="tell my team to rush B"))
    assert n >= 1, "carve-out OFF -> tactical snap must hit the LLM"


def test_route_all_off_is_untouched_full_deterministic():
    """Additive guarantee: with route-all OFF entirely, the full snap pool runs and
    the LLM is never consulted -- regardless of the carve-out flag."""
    set_u1_llm_route_enabled(False)
    for carve in (True, False):
        set_snap_carveout_enabled(carve)
        _line, n = _route_and_count(
            RelayCommand(payload="rush B", raw_text="tell my team to rush B"))
        assert n == 0, "route-all OFF must stay fully deterministic"
