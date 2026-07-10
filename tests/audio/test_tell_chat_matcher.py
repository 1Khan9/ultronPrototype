"""match_tell_chat — the voice→Twitch-chat tell grammar (spec 12, 2026-07-09).

Pins the two accepted forms (tagged "tell <name> in chat <msg>", broadcast
"tell chat <msg>"), the message cleaning, and — critically — the DISJOINTNESS
contract: no team-relay or teammate-social form may ever match (R7), because
this matcher runs BEFORE _maybe_handle_relay_speech in the dispatch cascades.
"""
from __future__ import annotations

import pytest

from kenning.audio.relay_speech import TellChatCommand, match_tell_chat


# ---------------------------------------------------------------- broadcast
@pytest.mark.parametrize(
    "text,msg",
    [
        ("tell chat brb", "brb"),
        ("tell the chat hello everyone", "hello everyone"),
        ("Ultron, tell chat I'll be back in five", "I'll be back in five"),
        ("say to chat gg", "gg"),
        ("say to the twitch chat good game", "good game"),
        ("post in chat the discord link is below", "the discord link is below"),
        ("put in the chat we go again", "we go again"),
        ("tell everyone in chat thanks for the raid", "thanks for the raid"),
        ("tell everybody in the chat one more game", "one more game"),
        ("tell them in chat gg", "gg"),
        # demonstrative "that" is KEPT (only reported-speech "that" drops)
        ("please tell chat that was my last round", "that was my last round"),
    ],
)
def test_broadcast_forms(text: str, msg: str) -> None:
    cmd = match_tell_chat(text)
    assert cmd == TellChatCommand(name=None, message=msg)


# ------------------------------------------------- wake homophones + leads
# Review 2026-07-09 P1: a mis-heard wake or a politeness scaffold must match
# HERE on the raw transcript — the normalizer strips/reframes these leads and
# the leftover "tell chat X" group form would be transmitted to the TEAM mic.
@pytest.mark.parametrize(
    "text,name,msg",
    [
        ("altron tell chat brb", None, "brb"),
        ("Voltron, tell chat one sec", None, "one sec"),
        ("ultra tell bob in chat hi", "bob", "hi"),
        ("ron, tell chat starting soon", None, "starting soon"),
        ("hey ultron tell chat we won", None, "we won"),
        ("could you tell chat brb", None, "brb"),
        ("can you please tell dragon slayer in chat nice one",
         "dragon slayer", "nice one"),
        ("i need you to tell chat gg", None, "gg"),
        ("go ahead and tell chat thanks all", None, "thanks all"),
        ("make sure you tell bob in chat i saw it", "bob", "i saw it"),
        ("ultron, would you tell chat five more minutes", None,
         "five more minutes"),
    ],
)
def test_wake_homophones_and_politeness_leads(text, name, msg) -> None:
    cmd = match_tell_chat(text)
    assert cmd == TellChatCommand(name=name, message=msg)


# ------------------------------------------------------------------- tagged
@pytest.mark.parametrize(
    "text,name,msg",
    [
        ("tell shroud in chat thanks for the sub", "shroud", "thanks for the sub"),
        ("Ultron tell dragon slayer in chat nice one", "dragon slayer", "nice one"),
        ("message bob in the chat that I saw it", "bob", "I saw it"),
        ("reply to jay dee in chat yes exactly", "jay dee", "yes exactly"),
        ("notify timmy on chat hurry up", "timmy", "hurry up"),
        ("write to mods in chat check the queue", "mods", "check the queue"),
        ("tell xx sniper xx in twitch chat you rock", "xx sniper xx", "you rock"),
        ("ultron, can you tell casey in chat welcome back", "casey", "welcome back"),
        ("inform ricky on the chat he is muted", "ricky", "he is muted"),
    ],
)
def test_tagged_forms(text: str, name: str, msg: str) -> None:
    cmd = match_tell_chat(text)
    assert cmd == TellChatCommand(name=name, message=msg)


def test_name_split_lands_on_first_in_chat() -> None:
    cmd = match_tell_chat("tell bob in chat see you in chat tomorrow")
    assert cmd == TellChatCommand(name="bob", message="see you in chat tomorrow")


# ------------------------------------------- delimiter STT-mishear tolerance
# Live 2026-07-10: Whisper rendered "tell 1v9khan IN CHAT hi" as
# "Tell 1v9con and chat hi." -> the strict "in chat" delimiter missed and the
# command fell through to the LLM (no chat post). The delimiter now absorbs
# the observed mishear family; the fuzzy roster match handles the name.
@pytest.mark.parametrize(
    "text,name,msg",
    [
        ("Tell 1v9con and chat hi.", "1v9con", "hi."),      # the EXACT live line
        ("tell bob an chat hello", "bob", "hello"),
        ("tell bob en chat one sec", "bob", "one sec"),
        ("tell bob into chat see you", "bob", "see you"),
        ("tell bob in chad hi", "bob", "hi"),               # "chat" mis-heard
        ("say hi to bob and chat", "bob", "hi"),
        ("greet bob and chat", "bob", "hi"),
    ],
)
def test_delimiter_mishears_still_match(text, name, msg) -> None:
    assert match_tell_chat(text) == TellChatCommand(name=name, message=msg)


def test_delimiter_mishears_broadcast_and_disjointness() -> None:
    # broadcast group form tolerates the delimiter mishear too
    assert match_tell_chat("tell everyone and chat gg") == TellChatCommand(
        name=None, message="gg")
    # the broadcast HEAD stays strict: "tell chad hi" is a person, not chat
    assert match_tell_chat("tell chad hi") is None
    # group names still reject through the widened delimiter
    assert match_tell_chat("tell my team and chat the plan") is None
    # no chat word at all -> never matches
    assert match_tell_chat("tell bob and jane the plan") is None


# ------------------------------------------------- greeting-before-name forms
# Review 2026-07-09: the natural inverse phrasing ("say hi to <name> in chat")
# puts the greeting BEFORE the name — the streamer's reported failing case.
@pytest.mark.parametrize(
    "text,name,msg",
    [
        ("say hi to bob in chat", "bob", "hi"),
        ("Ultron, say hi to dragon slayer in chat", "dragon slayer", "hi"),
        ("say hello to timmy in chat", "timmy", "hello"),
        ("say hey to jay dee in the chat", "jay dee", "hey"),
        ("could you say what's up to ricky in chat", "ricky", "what's up"),
        ("say welcome to newbie in chat", "newbie", "welcome"),
        ("say hi to bob in chat and thanks for the follow", "bob",
         "hi and thanks for the follow"),
        # greet / welcome verbs synthesize a greeting
        ("greet casey in chat", "casey", "hi"),
        ("Ultron greet dragon slayer in the chat", "dragon slayer", "hi"),
        ("welcome timmy to chat", "timmy", "welcome"),
        ("welcome ricky to the chat", "ricky", "welcome"),
        ("welcome bob aboard in chat", "bob", "welcome"),
    ],
)
def test_greeting_before_name_forms(text, name, msg) -> None:
    assert match_tell_chat(text) == TellChatCommand(name=name, message=msg)


@pytest.mark.parametrize(
    "text,msg",
    [
        ("say hi to everyone in chat", "hi"),
        ("say hello to everybody in chat", "hello"),
        ("greet everyone in chat", "hi"),
        ("welcome all to the chat", "welcome"),
    ],
)
def test_greeting_to_whole_audience_broadcasts(text, msg) -> None:
    assert match_tell_chat(text) == TellChatCommand(name=None, message=msg)


def test_greeting_to_team_falls_through() -> None:
    # "say hi to my team in chat" is a team reference -> not a chat tag
    assert match_tell_chat("say hi to my team in chat") is None
    assert match_tell_chat("greet the squad in chat") is None


# --------------------------------------------------------- message cleaning
def test_leading_that_is_dropped_and_whitespace_collapsed() -> None:
    cmd = match_tell_chat("tell   bob   in chat   that   you   are   right")
    assert cmd == TellChatCommand(name="bob", message="you are right")


def test_demonstrative_that_is_kept() -> None:
    cmd = match_tell_chat("tell chat that was insane")
    assert cmd == TellChatCommand(name=None, message="that was insane")
    cmd = match_tell_chat("tell bob in chat that is the plan")
    assert cmd == TellChatCommand(name="bob", message="that is the plan")


def test_message_is_length_capped() -> None:
    long = "tell bob in chat " + "x" * 1000
    cmd = match_tell_chat(long)
    assert cmd is not None
    assert len(cmd.message) == 400


def test_control_characters_are_stripped() -> None:
    cmd = match_tell_chat("tell chat hi\x00\x07 there")
    assert cmd == TellChatCommand(name=None, message="hi there")


# ------------------------------------------------- disjointness (R7) + None
@pytest.mark.parametrize(
    "text",
    [
        # Team-relay leads must NEVER match (they belong to match_relay_command).
        "tell my team rotate B",
        "tell my team two garage",
        "tell the squad push A",
        "tell my teammates in chat the plan",       # group word in the name slot
        "tell the squad in chat hi",                # group word in the name slot
        "tell my team in chat the plan",            # "my ..." name reject
        "say to the guys we win this",
        "tell 'em to rotate",
        # Teammate-social relay forms must fall through (no "in chat").
        "tell jett nice shot",
        "tell sage nice job",
        # Bare pronouns in the name slot fall through.
        "tell him in chat hello",
        "tell her in chat hello",
        # Incomplete — no message.
        "tell chat",
        "tell bob in chat",
        "tell chat   ",
        # Ordinary speech.
        "we should chat in a bit",
        "tell me about pandas",
        "what did chat say",
        "I posted in chat earlier",
        "",
    ],
)
def test_falls_through(text: str) -> None:
    assert match_tell_chat(text) is None


def test_none_input_is_safe() -> None:
    assert match_tell_chat(None) is None  # type: ignore[arg-type]


def test_config_defaults_exist() -> None:
    """The spec-12 chat config fields ship with the intended defaults."""
    from kenning.config import TwitchChatConfig

    cfg = TwitchChatConfig()
    assert cfg.tell_chat_enabled is True
    assert cfg.tell_chat_match_floor == 60
    assert "{name}" in cfg.tell_chat_template
    assert "{message}" in cfg.tell_chat_template
    assert "{message}" in cfg.tell_chat_broadcast_template
    assert cfg.first_time_welcome_enabled is True
    assert "{name}" in cfg.first_time_welcome_text
    assert "{delay}" in cfg.first_time_welcome_text
    assert "{name}" in cfg.first_time_welcome_text_no_delay
    assert cfg.first_time_welcome_max_per_minute == 4
    assert cfg.stream_delay_seconds == 40
