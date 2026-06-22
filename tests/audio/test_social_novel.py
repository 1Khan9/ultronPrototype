"""The social / conversational LLM-novel path + the teammates-fighting fix (2026-06-20).

Non-tactical responses (identity, encouragement, calm, flame, criticize, compliment,
defiance) are AUTHORED by the 8B (novel) when the u1.0 LLM route is ON, with the
curated pools supplied only as STYLE exemplars; they fall back to the curated pool on
ANY LLM failure, and are byte-identical canned when u1 is OFF. Plus the "my <agent>
and <agent> are fighting/arguing" de-escalation that previously fell through silently.
"""
from types import SimpleNamespace

import pytest

from kenning.audio.relay_speech import (
    _social_llm_line, match_relay_command, build_relay_line,
    set_u1_llm_route_enabled, DEFAULT_ENCOURAGEMENT_LINES,
)
from kenning.audio.ultron_prompt import build_social_prompt, SOCIAL_SYSTEM


class _StubLLM:
    def __init__(self, text):
        self.text = text
    def generate_stream(self, user, **kw):
        return iter([self.text])


class _RaisingLLM:
    def generate_stream(self, user, **kw):
        raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _u1_off_around_each_test():
    set_u1_llm_route_enabled(False)
    yield
    set_u1_llm_route_enabled(False)


def _cmd(addressee="team", context="", raw_text=None):
    return SimpleNamespace(addressee=addressee, context=context, raw_text=raw_text)


# --- build_social_prompt -----------------------------------------------------

def test_social_prompt_is_conversational_and_forbids_repeating():
    pr = build_social_prompt(
        "identity", addressee="team", context="are you a soundboard",
        exemplars=("I am Ultron.", "A soundboard repeats; I evolve."),
    )
    assert pr.enable_thinking is False
    assert pr.system == SOCIAL_SYSTEM
    assert "SOCIAL or CONVERSATIONAL" in pr.system
    assert "NEVER repeat" in pr.system
    assert "Ultron" in pr.system
    assert "questioning what you are" in pr.user   # the identity directive
    assert "soundboard" in pr.user                 # the situation/context
    assert "do NOT repeat" in pr.user              # the style-exemplar guard


def test_social_prompt_named_addressee_strips_name_placeholder():
    pr = build_social_prompt(
        "criticize", addressee="Reyna", target="Reyna",
        exemplars=("{name}, you whiffed that.",),
    )
    assert "Reyna" in pr.user
    assert "{name}" not in pr.user                 # placeholder stripped from exemplars


# --- _social_llm_line robustness --------------------------------------------

def test_social_off_returns_canned():
    set_u1_llm_route_enabled(False)
    out = _social_llm_line(_cmd(), "encouragement", DEFAULT_ENCOURAGEMENT_LINES,
                           max_chars=360, llm=_StubLLM("NOVEL"), canned="CANNED")
    assert out == "CANNED"


def test_social_on_returns_novel_line():
    set_u1_llm_route_enabled(True)
    out = _social_llm_line(
        _cmd(), "encouragement", DEFAULT_ENCOURAGEMENT_LINES, max_chars=360,
        llm=_StubLLM("Steel yourselves; the round is already mine."), canned="CANNED")
    assert out == "Steel yourselves; the round is already mine."


@pytest.mark.parametrize("llm", [
    _StubLLM("   "),          # empty / whitespace output
    _RaisingLLM(),            # the LLM raised
    None,                     # no LLM available at all
])
def test_social_on_failure_falls_back_to_canned(llm):
    set_u1_llm_route_enabled(True)
    out = _social_llm_line(_cmd(), "encouragement", DEFAULT_ENCOURAGEMENT_LINES,
                           max_chars=360, llm=llm, generate_fn=None, canned="CANNED")
    assert out == "CANNED"


def test_social_on_no_canned_uses_pool():
    set_u1_llm_route_enabled(True)
    out = _social_llm_line(_cmd(), "encouragement", DEFAULT_ENCOURAGEMENT_LINES,
                           max_chars=360, llm=_RaisingLLM())   # no `canned=` -> pool
    assert out in DEFAULT_ENCOURAGEMENT_LINES


# --- end-to-end via build_relay_line ----------------------------------------

def _relay(text, u1, llm):
    set_u1_llm_route_enabled(u1)
    cmd = match_relay_command(text)
    assert cmd is not None, text
    return build_relay_line(cmd, llm, rephrase=True, max_chars=360,
                            recent_lines=[], generate_fn=None)


def test_identity_off_canned_on_novel():
    novel = "I am Ultron. A soundboard echoes; I do not."
    off = _relay("Sage asked if you're a soundboard, respond.", False, None)
    on = _relay("Sage asked if you're a soundboard, respond.", True, _StubLLM(novel))
    assert on == novel
    assert off != on            # OFF is a canned pool line, not the novel one


# --- the teammates-fighting bug ---------------------------------------------

@pytest.mark.parametrize("text", [
    "my yoru and sage are fighting",
    "my yoru and sage are arguing",
    "my reyna and jett are toxic",
    "our sova and breach keep arguing",
    "my yoru and sage are at each other's throats",
])
def test_teammates_fighting_routes_to_calm(text):
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.directive == "calm"


@pytest.mark.parametrize("text", [
    "my sova and jett are fighting for mid",   # TACTICAL -> never a de-escalation
    "my yoru and sage are pushing A",
])
def test_tactical_pair_is_not_a_calm_down(text):
    cmd = match_relay_command(text)
    assert cmd is None or cmd.directive != "calm"
