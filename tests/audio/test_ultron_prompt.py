"""Tests for the Ultron 1.0 lean prompt assembler (src/kenning/audio/ultron_prompt.py).

Hermetic -- no model load. Validates the prompt structure, the no/low/high verbosity axis, the
flavor on/off toggle, exemplar/agent-context/recent-line injection, the named-addressee and
compound forms, and the always-thinking-off + per-verbosity sampling contract.
"""
import pytest

from kenning.audio import ultron_prompt as up


def test_normalize_verbosity_synonyms():
    assert up.normalize_verbosity("none") == "none"
    assert up.normalize_verbosity("no flavor".split()[0]) == "none"  # "no" -> none
    assert up.normalize_verbosity("minimal") == "low"
    assert up.normalize_verbosity("terse") == "low"
    assert up.normalize_verbosity("verbose") == "high"
    assert up.normalize_verbosity("vivid") == "high"
    assert up.normalize_verbosity("") == up.DEFAULT_VERBOSITY
    assert up.normalize_verbosity("gibberish") == up.DEFAULT_VERBOSITY
    # multi-word spoken commands ("<level> flavor")
    assert up.normalize_verbosity("no flavor") == "none"
    assert up.normalize_verbosity("low flavor") == "low"
    assert up.normalize_verbosity("high flavor") == "high"
    assert up.normalize_verbosity("turn flavor off") == "none"
    assert up.normalize_verbosity("minimal flavor please") == "low"


def test_relay_prompt_basic_structure():
    r = up.build_relay_prompt("Sova hit 84 on A main")
    assert r.system == up.RELAY_SYSTEM
    assert r.enable_thinking is False
    # callout present verbatim in the user message
    assert "Sova hit 84 on A main" in r.user
    assert "Relay this callout to your team" in r.user
    assert r.user.rstrip().endswith("Now say it:")
    # persona + output-rule guards are present in the system prompt
    assert "Ultron" in r.system
    assert "no stage directions" in r.system
    assert "EXACT" in r.system
    assert "never break character" in r.system


def test_verbosity_differentiates_directive_and_tokens():
    none = up.build_relay_prompt("rush B", verbosity="none")
    low = up.build_relay_prompt("rush B", verbosity="low")
    high = up.build_relay_prompt("rush B", verbosity="high")
    # distinct directives
    assert up._VERBOSITY_DIRECTIVE["none"] in none.user
    assert up._VERBOSITY_DIRECTIVE["low"] in low.user
    assert up._VERBOSITY_DIRECTIVE["high"] in high.user
    assert none.user != low.user != high.user
    # token budgets scale with verbosity
    assert none.sampling["max_tokens"] < low.sampling["max_tokens"] < high.sampling["max_tokens"]


def test_flavor_toggle():
    on = up.build_relay_prompt("they have no smokes", flavor_tail=True)
    off = up.build_relay_prompt("they have no smokes", flavor_tail=False)
    assert up._FLAVOR_ON in on.user and up._FLAVOR_ON not in off.user
    assert up._FLAVOR_OFF in off.user and up._FLAVOR_OFF not in on.user


def test_exemplars_injected_custom_and_default():
    default = up.build_relay_prompt("rush B")
    assert "Examples of your voice:" in default.user
    assert "Sova tagged one for 84" in default.user  # default exemplar
    custom = up.build_relay_prompt("rush B", exemplars=(("foo bar", "Foo. Bar."),))
    assert 'player: "foo bar" -> "Foo. Bar."' in custom.user
    assert "Sova tagged one for 84" not in custom.user  # custom replaces default


def test_agent_context_and_recent_lines():
    r = up.build_relay_prompt(
        "their sova ulted",
        agent_context=["Sova: initiator; ult = Hunter's Fury (3 damaging blasts)"],
        recent_lines=["Their smokes are gone. Take the space."],
    )
    assert "Agent facts" in r.user and "Hunter's Fury" in r.user
    assert "do NOT repeat" in r.user and "Their smokes are gone" in r.user


def test_named_addressee_opens_with_name():
    r = up.build_relay_prompt("heal me", addressee="Sage")
    assert "teammate Sage" in r.user
    assert "opening with their name" in r.user


def test_compound_combines_into_one_line():
    r = up.build_relay_prompt("Jett hit 84, Breach hit 97, one rotating B", compound=True)
    assert "ONE combined spoken line" in r.user
    assert "Jett hit 84, Breach hit 97, one rotating B" in r.user


def test_private_prompt_is_not_relayed():
    r = up.build_private_prompt("what map is this")
    assert r.system == up.PRIVATE_SYSTEM
    assert "only they can hear you" in r.system
    assert "NOT relayed" in r.system
    assert "what map is this" in r.user
    assert r.enable_thinking is False


def test_private_uses_private_exemplars_not_relay_callouts():
    # M6a: the private path must use Q&A exemplars, not relay-callout exemplars
    # (the relay default made the 8B emit empty/callout-shaped output on a question).
    r = up.build_private_prompt("what should I buy this round")
    assert "should I buy this round" in r.user            # a private exemplar present
    assert "Sova tagged one for 84" not in r.user         # relay default must NOT leak in
    # relay path still uses relay exemplars
    rr = up.build_relay_prompt("rush B")
    assert "Sova tagged one for 84" in rr.user


@pytest.mark.parametrize("v", ["none", "low", "high"])
def test_sampling_always_has_required_keys(v):
    r = up.build_relay_prompt("rush B", verbosity=v)
    for k in ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "max_tokens"):
        assert k in r.sampling
