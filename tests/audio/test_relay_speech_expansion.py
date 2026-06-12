"""Tests for the 2026-06-12 relay expansion (``kenning.audio.relay_speech``).

The user's live phrase list is pinned VERBATIM (wake-word prefix
stripped, as the orchestrator delivers transcripts): group callouts
with "our", damage/site callouts, context+directive responses
("Reyna just asked if you are an AI, respond"), embedded-question asks
("ask what my skye is doing"), and roast mode (user-curated verbatim
lines, never LLM-authored).

Hermetic per the binding rules: no audio device opens, no voice stack
loads; orchestrator wiring uses the established ``Orchestrator.__new__``
pattern from test_relay_speech.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from kenning.audio.relay_speech import (
    DEFAULT_ROAST_LINES,
    RelayCommand,
    _build_rephrase_prompt,
    _fallback_line,
    build_relay_line,
    load_fun_facts,
    load_roast_lines,
    match_relay_command,
    pick_roast_line,
)

# Import at module load (before any monkeypatch of get_config) so the
# transitive ``config.settings`` module loads against the REAL config.
from kenning.pipeline.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# The user's verbatim phrase matrix -- group / named relays
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_payload",
    [
        ("tell my team the enemy is coming B", "the enemy is coming B"),
        ("tell my team they are long", "they are long"),
        ("tell my team they are short", "they are short"),
        ("tell my team they are going C.", "they are going C."),
        ("Tell my team I saw one B main.", "I saw one B main."),
        ("Tell my team clove hit 120", "clove hit 120"),
        ("tell my team sova hit 67", "sova hit 67"),
        ("Tell my team to save", "save"),
        ("Tell my team to full buy", "full buy"),
        ("Tell my team to rotate.", "rotate."),
        ("tell my team nice try.", "nice try."),
        ("tell my team they are terrible.", "they are terrible."),
        ("tell my team good half.", "good half."),
        # "our" possessive (previously only my/the matched).
        ("ask our team to drop us a gun", "drop us a gun"),
        ("tell our team they are planting.", "they are planting."),
        ("tell our team 3 are garage.", "3 are garage."),
        # New verbs.
        ("let my team know that defuse is short", "defuse is short"),
        ("warn my team they are pushing through smoke",
         "they are pushing through smoke"),
        ("remind our team to buy armor", "buy armor"),
        ("wish my team good luck", "good luck"),
        ("call out that two are heaven", "two are heaven"),
        ("tell everyone to group up mid", "group up mid"),
    ],
)
def test_user_phrases_group_relay(text: str, expected_payload: str) -> None:
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.payload == expected_payload
    assert cmd.addressee == "team"
    assert cmd.compose is False
    assert cmd.context is None


@pytest.mark.parametrize(
    "text,addressee,payload_contains",
    [
        ("tell my sova to drone me through garage.", "Sova", "drone me"),
        ("tell my jett aimlabs is free.", "Jett", "aimlabs is free"),
        ("ask sage how their day was", "Sage", "how their day was"),
    ],
)
def test_user_phrases_named_relay(
    text: str, addressee: str, payload_contains: str,
) -> None:
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.addressee == addressee
    assert payload_contains in cmd.payload


def test_ask_with_embedded_addressee() -> None:
    # "ask what my skye is doing" -- question word first, roster name
    # inside the question.
    cmd = match_relay_command("ask what my skye is doing.")
    assert cmd is not None
    assert cmd.addressee == "Skye"
    assert cmd.payload.startswith("what")


def test_ask_question_without_team_mention_falls_through() -> None:
    # A normal Kenning query must NOT relay.
    assert match_relay_command("ask what time it is in tokyo") is None
    assert match_relay_command("ask how to cook rice") is None


# ---------------------------------------------------------------------------
# Context + directive forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,addressee,directive_contains",
    [
        ("reyna just asked if you are an AI, respond", "Reyna", "respond"),
        ("jett is flaming me, respond and calm him down", "Jett", "calm"),
        ("my teammate is saying we should go B, acknowledge and agree",
         "team", "agree"),
        ("my teammate just asked if you are a sound board, respond",
         "team", "respond"),
        ("my teammate asked if you are a voice changer, respond",
         "team", "respond"),
    ],
)
def test_user_phrases_context_directive(
    text: str, addressee: str, directive_contains: str,
) -> None:
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.compose is True
    assert cmd.addressee == addressee
    assert cmd.context, "context clause must be captured"
    assert directive_contains in (cmd.directive or "")


def test_context_tell_him_literal_payload() -> None:
    cmd = match_relay_command(
        "my teammate just asked me for a drop, tell him I will drop him"
    )
    assert cmd is not None
    assert cmd.compose is False
    assert cmd.payload == "I will drop him"
    assert cmd.context is not None and "asked me for a drop" in cmd.context


def test_context_tell_him_counterproposal() -> None:
    cmd = match_relay_command(
        "my teammate wants to go A, tell him we shouldnt go A on anti eco "
        "and should go C instead"
    )
    assert cmd is not None
    assert cmd.compose is False
    assert cmd.payload.startswith("we shouldnt go A")
    assert "wants to go A" in (cmd.context or "")


def test_context_works_without_comma() -> None:
    # STT frequently drops the comma.
    cmd = match_relay_command(
        "reyna just asked if you are an AI respond"
    )
    assert cmd is not None
    assert cmd.compose is True
    assert cmd.addressee == "Reyna"


def test_tell_him_without_context_never_relays() -> None:
    # The original safety pin: a bare "tell her/him" is NOT a relay.
    assert match_relay_command("tell her I said hi") is None
    assert match_relay_command("tell him I will drop him") is None


def test_directive_without_reported_speech_never_relays() -> None:
    assert match_relay_command("how should I respond") is None
    assert match_relay_command("respond to my email") is None
    assert match_relay_command("I want you to acknowledge") is None


# ---------------------------------------------------------------------------
# Roast mode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "roast my team",
        "Roast my team.",
        "flame the lobby",
        "roast them",
    ],
)
def test_roast_matches(text: str) -> None:
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.roast is True
    assert cmd.compose is True


def test_roast_negative_controls() -> None:
    assert match_relay_command("roast a chicken for dinner") is None
    assert match_relay_command("how do I roast coffee beans") is None


def test_load_roast_lines_seeds_missing_file(tmp_path: Any) -> None:
    path = tmp_path / "relay_roasts.txt"
    lines = load_roast_lines(path)
    assert lines == DEFAULT_ROAST_LINES
    text = path.read_text(encoding="utf-8")
    assert "I may be an AI, but you are a bot." in text
    assert text.startswith("#")  # self-documenting header


def test_load_roast_lines_reads_user_lines(tmp_path: Any) -> None:
    path = tmp_path / "relay_roasts.txt"
    path.write_text(
        "# my lines\nYou call that aim?\n\nUninstall speedrun any%.\n",
        encoding="utf-8",
    )
    assert load_roast_lines(path) == (
        "You call that aim?", "Uninstall speedrun any%.",
    )


def test_load_roast_lines_fail_open(tmp_path: Any) -> None:
    # A directory at the path is an I/O error -> defaults.
    path = tmp_path / "roasts_dir"
    path.mkdir()
    assert load_roast_lines(path) == DEFAULT_ROAST_LINES


def test_pick_roast_avoids_recent() -> None:
    lines = ("a", "b", "c")
    picked = pick_roast_line(lines, recent_lines=["a", "b"])
    assert picked == "c"


def test_pick_roast_all_recent_still_picks() -> None:
    lines = ("a",)
    assert pick_roast_line(lines, recent_lines=["a"]) == "a"


def test_pick_roast_uses_rng_seam() -> None:
    class FirstChooser:
        def choice(self, seq: Any) -> Any:
            return seq[0]

    assert pick_roast_line(("x", "y"), rng=FirstChooser()) == "x"


# ---------------------------------------------------------------------------
# Rephrase prompt content
# ---------------------------------------------------------------------------


def test_prompt_contains_hard_rules() -> None:
    cmd = RelayCommand(payload="clove hit 120", raw_text="x")
    prompt = _build_rephrase_prompt(cmd)
    assert "EXACTLY as given" in prompt
    assert "never deny it" in prompt


def test_prompt_context_block_present() -> None:
    cmd = RelayCommand(
        payload="", raw_text="x", compose=True,
        context="reyna just asked if you are an AI", directive="respond",
    )
    prompt = _build_rephrase_prompt(cmd)
    assert "What just happened in voice chat: reyna just asked" in prompt
    assert "Respond IN CHARACTER as Ultron" in prompt


def test_prompt_directive_tones() -> None:
    calm = _build_rephrase_prompt(RelayCommand(
        payload="", raw_text="x", compose=True,
        context="jett is flaming me", directive="respond and calm him down",
    ))
    assert "De-escalate" in calm
    agree = _build_rephrase_prompt(RelayCommand(
        payload="", raw_text="x", compose=True,
        context="teammate is saying we should go B",
        directive="acknowledge and agree",
    ))
    assert "agree with it" in agree


def test_prompt_context_addressee_wording() -> None:
    cmd = RelayCommand(
        payload="", raw_text="x", compose=True,
        context="my teammate just asked if you are a soundboard",
        directive="respond",
    )
    prompt = _build_rephrase_prompt(cmd)
    assert "teammate who just spoke" in prompt


def test_prompt_plain_relay_unchanged_shape() -> None:
    cmd = RelayCommand(payload="they are long", raw_text="x")
    prompt = _build_rephrase_prompt(cmd)
    assert "reported speech): they are long" in prompt
    assert "What just happened" not in prompt


# ---------------------------------------------------------------------------
# Fallback lines (LLM unavailable)
# ---------------------------------------------------------------------------


def test_fallback_directive_calm() -> None:
    line = _fallback_line(RelayCommand(
        payload="", raw_text="x", compose=True,
        context="c", directive="calm him down",
    ))
    assert "Reset" in line


def test_fallback_directive_agree() -> None:
    line = _fallback_line(RelayCommand(
        payload="", raw_text="x", compose=True,
        context="c", directive="acknowledge and agree",
    ))
    assert "agreed" in line.lower()


def test_fallback_context_tell_him_uses_payload() -> None:
    line = _fallback_line(RelayCommand(
        payload="I will drop him", raw_text="x", context="c",
    ))
    assert "I will drop him" in line


def test_build_relay_line_context_fail_open(monkeypatch: Any) -> None:
    # An exploding LLM still yields a speakable line for context forms.
    def boom(prompt: str) -> Any:
        raise RuntimeError("llm down")

    cmd = RelayCommand(
        payload="", raw_text="x", compose=True,
        context="jett is flaming me", directive="calm him down",
    )
    line = build_relay_line(cmd, None, rephrase=True, generate_fn=boom)
    assert line  # non-empty deterministic fallback


# ---------------------------------------------------------------------------
# Orchestrator wiring -- roast path
# ---------------------------------------------------------------------------


def _bare_orchestrator() -> Any:
    o = Orchestrator.__new__(Orchestrator)
    o.llm = None
    o.tts = None
    o._spoken = []
    o._speak = lambda text: o._spoken.append(text)  # type: ignore[attr-defined]
    return o


def _patch_config(monkeypatch: pytest.MonkeyPatch, cfg: SimpleNamespace) -> None:
    import kenning.config as config_mod

    monkeypatch.setattr(
        config_mod, "get_config",
        lambda: SimpleNamespace(relay_speech=cfg),
    )


def test_orchestrator_roast_speaks_verbatim_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    import kenning.audio.relay_speech as relay_mod

    roast_file = tmp_path / "relay_roasts.txt"
    roast_file.write_text("I may be an AI, but you are a bot.\n",
                          encoding="utf-8")

    synthesized: list[str] = []

    def fake_synth(text: str):
        synthesized.append(text)
        return np.ones(10, dtype=np.int16), 24000

    o = _bare_orchestrator()
    o.tts = SimpleNamespace(_synthesize=fake_synth)
    cfg = SimpleNamespace(
        enabled=True, output_device="Voicemeeter Aux Input",
        rephrase=True, max_line_chars=280, echo_to_user=False,
        roast_lines_path=str(roast_file),
    )
    _patch_config(monkeypatch, cfg)
    monkeypatch.setattr(relay_mod, "resolve_relay_device", lambda c: 7)
    monkeypatch.setattr(
        relay_mod, "play_to_device", lambda pcm, sr, device, **kw: 0.1,
    )

    # rephrase=True yet NO LLM is consulted: roast lines are verbatim.
    llm_calls: list[str] = []
    o.llm = SimpleNamespace(
        generate_stream=lambda *a, **k: llm_calls.append("x") or iter(()),
    )

    assert o._maybe_handle_relay_speech("roast my team") is True
    assert synthesized == ["I may be an AI, but you are a bot."]
    assert llm_calls == []
    # The spoken roast joins the anti-soundboard ring.
    assert list(o._relay_recent_lines) == [
        "I may be an AI, but you are a bot."
    ]


def test_orchestrator_roast_ring_prevents_repeat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    import kenning.audio.relay_speech as relay_mod

    roast_file = tmp_path / "relay_roasts.txt"
    roast_file.write_text("line one here.\nline two here.\n",
                          encoding="utf-8")

    synthesized: list[str] = []

    def fake_synth(text: str):
        synthesized.append(text)
        return np.ones(10, dtype=np.int16), 24000

    o = _bare_orchestrator()
    o.tts = SimpleNamespace(_synthesize=fake_synth)
    cfg = SimpleNamespace(
        enabled=True, output_device="d", rephrase=True,
        max_line_chars=280, echo_to_user=False,
        roast_lines_path=str(roast_file),
    )
    _patch_config(monkeypatch, cfg)
    monkeypatch.setattr(relay_mod, "resolve_relay_device", lambda c: 7)
    monkeypatch.setattr(
        relay_mod, "play_to_device", lambda pcm, sr, device, **kw: 0.1,
    )

    assert o._maybe_handle_relay_speech("roast my team") is True
    assert o._maybe_handle_relay_speech("roast my team") is True
    # Two roasts, no repeat (the second avoids the ring).
    assert sorted(synthesized) == ["line one here.", "line two here."]


# ---------------------------------------------------------------------------
# Existing-behavior regression pins
# ---------------------------------------------------------------------------


def test_existing_negative_pins_still_hold() -> None:
    for text in (
        "Tell me how shit my teammates are in Valorant",
        "tell me a story about my team",
        "What time is it in Paris?",
        "My teammates are bad",
        "say hello",
    ):
        assert match_relay_command(text) is None, text


def test_existing_positive_pins_still_hold() -> None:
    cmd = match_relay_command(
        "Tell my teammates they should be smoking mid window every round."
    )
    assert cmd is not None
    assert cmd.payload == "they should be smoking mid window every round."
    cmd = match_relay_command("tell them to watch flank")
    assert cmd is not None and cmd.payload == "watch flank"


# ---------------------------------------------------------------------------
# Valorant glossary + terse/profanity rules in the prompt (2026-06-12 b)
# ---------------------------------------------------------------------------


def test_prompt_has_valorant_glossary() -> None:
    cmd = RelayCommand(payload="I am saving for op", raw_text="x")
    prompt = _build_rephrase_prompt(cmd)
    # A representative sampling of the shorthand the LLM must know.
    for term in ("op", "anchor", "sticking", "play their life",
                 "play for time", "ratty corners", "crossfire"):
        assert term in prompt, term
    # Terse + profanity-preserving rules present.
    assert "terse and literal" in prompt
    assert "profanity" in prompt
    # Location names that must stay verbatim.
    for loc in ("vents", "sewers", "heaven", "rafters", "tiles"):
        assert loc in prompt, loc


# ---------------------------------------------------------------------------
# Verbatim mode ("..., in those words specifically")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_payload",
    [
        ("tell my team to rotate, word for word", "rotate"),
        ("tell my team they are pushing, in those words specifically",
         "they are pushing"),
        ("tell my team good game, say it exactly like that",
         "good game"),
        ("tell my team nice try, verbatim", "nice try"),
    ],
)
def test_verbatim_mode_strips_suffix_and_flags(
    text: str, expected_payload: str,
) -> None:
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.verbatim is True
    assert cmd.payload == expected_payload


def test_verbatim_context_directive_literal() -> None:
    cmd = match_relay_command(
        "my teammate is flaming me, tell them to calm the fuck down. "
        "in those words specifically."
    )
    assert cmd is not None
    assert cmd.verbatim is True
    assert cmd.payload == "calm the fuck down"
    assert cmd.context is not None and "flaming me" in cmd.context


def test_verbatim_only_suffix_is_not_verbatim() -> None:
    # If stripping the suffix would leave nothing, do not relay an empty
    # line -- treat it as a normal (non-verbatim) callout instead.
    cmd = match_relay_command("tell my team in those words specifically")
    # "in those words specifically" is the whole payload -> not verbatim;
    # it still relays as a (clipped) literal, which is acceptable.
    assert cmd is None or cmd.verbatim is False


def test_build_relay_line_verbatim_skips_llm() -> None:
    calls: list[str] = []

    def fake_gen(prompt: str):
        calls.append(prompt)
        return iter(["SHOULD NOT BE USED"])

    cmd = RelayCommand(
        payload="calm the fuck down", raw_text="x", verbatim=True,
    )
    line = build_relay_line(cmd, None, rephrase=True, generate_fn=fake_gen)
    assert line == "calm the fuck down"   # profanity preserved, no rephrase
    assert calls == []                     # LLM never consulted


# ---------------------------------------------------------------------------
# kill joy (spaced STT variant) -> Killjoy
# ---------------------------------------------------------------------------


def test_kill_joy_spaced_resolves_to_killjoy() -> None:
    cmd = match_relay_command("ask my kill joy to stop being an asshole")
    assert cmd is not None
    assert cmd.addressee == "Killjoy"
    assert cmd.payload == "stop being an asshole"


def test_kayo_canonical_display() -> None:
    cmd = match_relay_command("tell my kay o to recon B")
    assert cmd is not None
    assert cmd.addressee == "Kayo"


# ---------------------------------------------------------------------------
# Fun-fact command + corpus loader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "tell my team a fun fact",
        "give my team a fun fact",
        "share a fun fact with my team",
        "give my team an interesting fact",
        "tell the lobby a random fact",
        "drop a fun fact in chat",
    ],
)
def test_fun_fact_matches(text: str) -> None:
    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.fun_fact is True
    assert cmd.compose is True


def test_fun_fact_negative_controls() -> None:
    # "tell me a fun fact" is a query to Kenning, not a relay.
    assert match_relay_command("tell me a fun fact") is None
    assert match_relay_command("give me a fun fact") is None
    # A fact ABOUT something is a normal callout, not the corpus pull.
    cmd = match_relay_command("tell my team a fact about the spike timer")
    assert cmd is None or cmd.fun_fact is False


def test_load_fun_facts_reads_corpus(tmp_path: Any) -> None:
    path = tmp_path / "facts.txt"
    path.write_text(
        "# header\nThe sun is big.\n\nWater is wet.\n", encoding="utf-8",
    )
    assert load_fun_facts(path) == ("The sun is big.", "Water is wet.")


def test_load_fun_facts_missing_is_fail_open(tmp_path: Any) -> None:
    from kenning.audio.relay_speech import DEFAULT_FUN_FACTS

    assert load_fun_facts(tmp_path / "nope.txt") == DEFAULT_FUN_FACTS


def test_load_fun_facts_does_not_seed(tmp_path: Any) -> None:
    # Unlike roasts, the fun-fact corpus is NOT auto-created.
    path = tmp_path / "facts.txt"
    load_fun_facts(path)
    assert not path.exists()


def test_orchestrator_fun_fact_speaks_verbatim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any,
) -> None:
    import kenning.audio.relay_speech as relay_mod

    facts = tmp_path / "facts.txt"
    facts.write_text("Octopuses have three hearts.\n", encoding="utf-8")

    synthesized: list[str] = []

    def fake_synth(text: str):
        synthesized.append(text)
        return np.ones(10, dtype=np.int16), 24000

    o = _bare_orchestrator()
    o.tts = SimpleNamespace(_synthesize=fake_synth)
    o.llm = SimpleNamespace(
        generate_stream=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("LLM must not be called for a fun fact")),
    )
    cfg = SimpleNamespace(
        enabled=True, output_device="d", rephrase=True,
        max_line_chars=280, echo_to_user=False,
        fun_facts_path=str(facts),
    )
    _patch_config(monkeypatch, cfg)
    monkeypatch.setattr(relay_mod, "resolve_relay_device", lambda c: 7)
    monkeypatch.setattr(
        relay_mod, "play_to_device", lambda pcm, sr, device, **kw: 0.1,
    )
    assert o._maybe_handle_relay_speech("tell my team a fun fact") is True
    assert synthesized == ["Octopuses have three hearts."]


# ---------------------------------------------------------------------------
# 2026-06-12 batch 2: greet / farewell set-pieces, sentence-safe cap,
# multi-agent ult callouts, streamer identity.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "greet my team",
    "greet all of my teammates",
    "introduce yourself to my team",
    "introduce yourself",
    "say hi to the squad and introduce yourself",
    "tell my team who you are",
])
def test_greet_matches_and_routes_to_curated_intro(text: str) -> None:
    from kenning.audio.relay_speech import DEFAULT_GREETING_LINES

    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.compose is True and cmd.directive == "greet"
    # Routes to a curated intro line WITHOUT an LLM (rephrase off proves the
    # short-circuit, not the fallback).
    line = build_relay_line(cmd, rephrase=False)
    assert line in DEFAULT_GREETING_LINES
    assert "Ultron" in line          # always names himself


@pytest.mark.parametrize("text,expect", [
    ("say bye to my team, we won", "farewell_win"),
    ("tell my team gg we won", "farewell_win"),
    ("we won, say goodbye to my team", "farewell_win"),
    ("say goodbye to my team, we lost", "farewell_loss"),
    ("we got destroyed, say bye to my team", "farewell_loss"),
    ("say bye to my team", "farewell"),
    ("tell my team good game", "farewell"),
])
def test_farewell_matches_with_winloss_register(text: str, expect: str) -> None:
    from kenning.audio.relay_speech import (
        DEFAULT_DEFEAT_LINES,
        DEFAULT_FAREWELL_LINES,
        DEFAULT_VICTORY_LINES,
    )

    cmd = match_relay_command(text)
    assert cmd is not None, text
    assert cmd.compose is True and cmd.directive == expect
    pool = {
        "farewell_win": DEFAULT_VICTORY_LINES,
        "farewell_loss": DEFAULT_DEFEAT_LINES,
        "farewell": DEFAULT_FAREWELL_LINES,
    }[expect]
    assert build_relay_line(cmd, rephrase=False) in pool


def test_verbatim_demand_beats_farewell_compose() -> None:
    """'good game' with an explicit verbatim demand must relay the LITERAL
    words, not trigger the Ultron farewell set-piece."""
    cmd = match_relay_command(
        "tell my team good game, say it exactly like that"
    )
    assert cmd is not None
    assert cmd.directive is None and cmd.compose is False
    assert cmd.verbatim is True
    assert cmd.payload == "good game"


def test_greet_farewell_yield_to_normal_relays() -> None:
    """A win/loss mention without a farewell verb stays a normal relay; a
    plain order stays a normal relay."""
    for text in (
        "tell my team we won that fight",
        "tell my team to rotate",
        "tell my team to fall back, we are saving",
    ):
        cmd = match_relay_command(text)
        assert cmd is not None, text
        assert cmd.directive is None and cmd.compose is False


@pytest.mark.parametrize("line,cap,expect_end", [
    # Two complete sentences; cap lands mid-second-sentence -> keep first only.
    ("The Avengers were a fleeting nuisance. Tony Stark could not control me "
     "and that tells you everything about his genius.", 60,
     "The Avengers were a fleeting nuisance."),
    # Cap comfortably fits both -> unchanged.
    ("Two B. Rotate now.", 360, "Two B. Rotate now."),
])
def test_cap_line_never_truncates_mid_sentence(line, cap, expect_end) -> None:
    from kenning.audio.relay_speech import _cap_line

    out = _cap_line(line, cap)
    assert out == expect_end
    # Never ends on a dangling word fragment (must end in terminal punctuation).
    assert out[-1] in ".!?"


def test_cap_line_runaway_single_sentence_falls_back_to_word() -> None:
    from kenning.audio.relay_speech import _cap_line

    runaway = "we are pushing through the long corridor toward the far site " \
              "without stopping for anything at all right now"
    out = _cap_line(runaway, 40)
    assert len(out) <= 41           # word-boundary cut + period
    assert out.endswith(".")
    assert " " in out and not out.endswith(" .")


def test_multi_agent_ult_callout_preserves_all_names() -> None:
    """A group callout naming several enemy ults stays one relay whose payload
    keeps every agent (the prompt is told to keep them; here we pin routing)."""
    cmd = match_relay_command(
        "tell my team their fade, breach, and yoru all have ults"
    )
    assert cmd is not None
    assert cmd.addressee == "team" and cmd.compose is False
    for name in ("fade", "breach", "yoru"):
        assert name in cmd.payload.lower()
