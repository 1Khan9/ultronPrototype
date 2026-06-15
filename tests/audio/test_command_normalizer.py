"""Pins the pre-routing command normalizer: callouts route, vocab is corrected,
and conversational / Spotify text is NEVER over-corrected ("zero mistakes")."""

import pytest

from kenning.audio.command_normalizer import normalize_command
from kenning.audio.relay_speech import match_relay_command, _GREET_RE


def _routes_relay(text: str) -> bool:
    return match_relay_command(normalize_command(text)) is not None


def _is_greet(text: str) -> bool:
    return bool(_GREET_RE.match(normalize_command(text)))


# --- Callouts that MUST reach the relay (clipped leads + blends + vocab) -----
CALLOUTS = [
    "my team there's a Jett A main",
    "there's an enemy on jet main",
    "a jet on a main",
    "My team, there's a Jet A main",
    "It's a chamber holding long",
    "my team two enemies be main",
    "my team their neon has ult",
    "I hope my team Silva has his ult",
    "My team Jet ulted",
    "Call out a ray zombie",
    "my team I'm flanking through mid",
    "my team I'm planting",
    "my team good game",
    "my team to watch the flank",
    "my team were going to win",
    "tell my team Omen is lurking",
    "Tell my team their soba has old",       # phonetic Sova + ult
    "their cipher is in heaven",
    "warn my team killjoy turret on B",
]


@pytest.mark.parametrize("text", CALLOUTS)
def test_callouts_route_to_relay(text):
    assert _routes_relay(text), f"should relay: {text!r} -> {normalize_command(text)!r}"


# --- Conversational / Spotify / identity: must NOT be grabbed by relay -------
NOT_RELAY = [
    "Tell me about Tony Stark",
    "And my teammate asked about Black Widow",
    "what do you think of the enemy team",
    "are we going to win",
    "who are you",
    "what time is it",
    "play some Daft Punk",
    "pause the music",
    "turn it up",
    "skip this song",
    "what song is this",
    "set the volume to 40",
    "explain the spike timer",
    "thank you",
]


@pytest.mark.parametrize("text", NOT_RELAY)
def test_non_callouts_not_relayed(text):
    # Greetings are allowed to match the greet path; the rest must NOT relay.
    if _is_greet(text):
        return
    assert not _routes_relay(text), (
        f"should NOT relay: {text!r} -> {normalize_command(text)!r}")


# --- Vocab correction: the canonical term appears in the normalized output ---
VOCAB = [
    ("tell my team silva has ult", "Sova"),
    ("tell my team jet is pushing", "Jett"),
    ("tell my team cipher in heaven", "Cypher"),
    ("tell my team race ulted", "Raze"),
    ("tell my team their royal is low", "Reyna"),
    ("tell my team Arsova has ult", "our Sova"),
    ("call out a ray zombie", "Raze on B"),
    ("tell my team brimstoan smoked A", "Brimstone"),   # phonetic/fuzzy
    ("tell my team vipor wall is up", "Viper"),          # phonetic/fuzzy
    ("tell my team two enemies be main", "B main"),
]


@pytest.mark.parametrize("text,expected", VOCAB)
def test_vocab_corrected(text, expected):
    out = normalize_command(text)
    assert expected in out, f"{text!r} -> {out!r} (missing {expected!r})"


# --- ZERO MISTAKES: conversational text must be returned VERBATIM ------------
NO_OVERCORRECT = [
    "Tell me about Tony Stark",
    "what do you think of the enemy team",
    "play some Daft Punk",
    "pause the music",
    "are we going to win",
    "explain the spike timer",
]


@pytest.mark.parametrize("text", NO_OVERCORRECT)
def test_no_overcorrection_on_conversational(text):
    # Stripping leading filler is allowed, but no Valorant agent/term should be
    # injected and no "tell my team" lead added.
    out = normalize_command(text)
    assert not out.lower().startswith("tell my team"), f"{text!r} -> {out!r}"
    assert out == text, f"conversational altered: {text!r} -> {out!r}"


def test_empty_and_noise():
    assert normalize_command("") == ""
    assert normalize_command("   ") == "   "
    # single-word noise should not become a relay
    assert not _routes_relay("me")
