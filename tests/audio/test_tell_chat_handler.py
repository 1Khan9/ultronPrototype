"""Orchestrator wiring for the voice→chat TELL relay (spec 12, 2026-07-09).

_maybe_handle_tell_chat on a bare Orchestrator (no boot): broadcast + tagged
posting through the config templates, fuzzy roster resolution with the floor,
the TELL CHAT toggle-off consume, the not-connected consume, fail-open posting;
the run() source pins (both cascades check tell BEFORE the relay); the two
stop-window setters.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from kenning.pipeline.orchestrator import Orchestrator
from kenning.twitch.user_roster import UserRoster


def _mk(monkeypatch, *, roster=None, enabled=True, post="collect",
        floor=60, tagged_tpl="@{name} 🎙️ [live]: {message}",
        bcast_tpl="🎙️ [live]: {message}"):
    """A bare orchestrator with just the attrs the tell handler touches."""
    o = Orchestrator.__new__(Orchestrator)
    o._spoken = []
    o._posted = []
    o._speak = o._spoken.append          # type: ignore[method-assign]
    if post == "collect":
        o._twitch_chat_post = o._posted.append
    elif post == "boom":
        def _boom(_t):
            raise RuntimeError("sidecar down")
        o._twitch_chat_post = _boom
    # post == "absent": attribute deliberately not set
    o._tell_chat_enabled = enabled
    o._twitch_user_roster = roster
    import kenning.config as config_mod
    cfg = SimpleNamespace(twitch=SimpleNamespace(enabled=True, chat=SimpleNamespace(
        tell_chat_template=tagged_tpl,
        tell_chat_broadcast_template=bcast_tpl,
        tell_chat_match_floor=floor)))
    monkeypatch.setattr(config_mod, "get_config", lambda: cfg)
    return o


def test_non_match_falls_through(monkeypatch) -> None:
    o = _mk(monkeypatch)
    assert o._maybe_handle_tell_chat("tell my team rotate B") is False
    assert o._maybe_handle_tell_chat("what time is it") is False
    assert o._spoken == [] and o._posted == []


def test_broadcast_posts_silently(monkeypatch) -> None:
    """Success is SILENT (streamer 2026-07-10: 'just send it') — only
    failures speak, so a miss is never mistaken for a send."""
    o = _mk(monkeypatch)
    assert o._maybe_handle_tell_chat("tell chat be right back") is True
    assert o._posted == ["🎙️ [live]: be right back"]
    assert o._spoken == []


def test_tagged_fuzzy_matches_and_tags_display_name(monkeypatch) -> None:
    roster = UserRoster()
    roster.observe("dragonslayer99", "DragonSlayer99")
    roster.observe("bob", "Bob")
    o = _mk(monkeypatch, roster=roster)
    assert o._maybe_handle_tell_chat(
        "tell dragon slayer in chat nice sub") is True
    assert o._posted == ["@DragonSlayer99 🎙️ [live]: nice sub"]
    assert o._spoken == []          # success is silent (2026-07-10)


def test_tagged_display_falls_back_to_login(monkeypatch) -> None:
    roster = UserRoster()
    roster.observe("bob")                       # no display name observed
    o = _mk(monkeypatch, roster=roster)
    assert o._maybe_handle_tell_chat("tell bob in chat hi") is True
    assert o._posted == ["@bob 🎙️ [live]: hi"]


def test_below_floor_reports_no_match(monkeypatch) -> None:
    roster = UserRoster()
    roster.observe("zzqqxx")
    o = _mk(monkeypatch, roster=roster, floor=90)
    assert o._maybe_handle_tell_chat("tell bob in chat hi") is True
    assert o._posted == []
    assert o._spoken == ["No one in chat matches bob."]


def test_no_roster_reports_no_match(monkeypatch) -> None:
    o = _mk(monkeypatch, roster=None)
    assert o._maybe_handle_tell_chat("tell bob in chat hi") is True
    assert o._posted == []
    assert o._spoken == ["No one in chat matches bob."]


def test_toggle_off_consumes_silently_to_chat(monkeypatch) -> None:
    o = _mk(monkeypatch, enabled=False)
    assert o._maybe_handle_tell_chat("tell chat hello") is True
    assert o._posted == []
    assert o._spoken == ["The chat line is closed."]


def test_not_connected_consumes_and_never_relays(monkeypatch) -> None:
    o = _mk(monkeypatch, post="absent")
    assert o._maybe_handle_tell_chat("tell chat hello") is True
    assert o._spoken == ["The chat line isn't connected."]


def test_twitch_disabled_falls_through_to_legacy(monkeypatch) -> None:
    """With twitch.enabled=False the feature cannot exist — the handler must
    return False so 'tell chat X' keeps its LEGACY team-relay group meaning."""
    o = _mk(monkeypatch)
    import kenning.config as config_mod
    cfg = SimpleNamespace(twitch=SimpleNamespace(enabled=False, chat=None))
    monkeypatch.setattr(config_mod, "get_config", lambda: cfg)
    assert o._maybe_handle_tell_chat("tell chat hello") is False
    assert o._spoken == [] and o._posted == []


def test_post_failure_is_owned_not_leaked(monkeypatch) -> None:
    o = _mk(monkeypatch, post="boom")
    assert o._maybe_handle_tell_chat("tell chat hello") is True
    assert o._spoken == ["The chat line failed."]


# --------------------------------------------------------------- run() pins
def test_both_cascades_check_tell_before_relay() -> None:
    src = inspect.getsource(Orchestrator.run)
    assert src.count("_maybe_handle_tell_chat(_raw_stt)") == 2
    assert 'via="tell_chat"' in src
    assert 'via="tell_chat-lean"' in src
    # every tell check precedes the next relay-speech dispatch after it
    tell_1 = src.index("_maybe_handle_tell_chat(_raw_stt)")
    relay_1 = src.index("_maybe_handle_relay_speech(user_text)", tell_1)
    tell_2 = src.index("_maybe_handle_tell_chat(_raw_stt)", tell_1 + 1)
    relay_2 = src.index("_maybe_handle_relay_speech(user_text)", tell_2)
    assert tell_1 < relay_1 < tell_2 < relay_2


# ------------------------------------------------------------------ setters
def test_set_tell_chat_enabled_flips_attr() -> None:
    o = Orchestrator.__new__(Orchestrator)
    o._tell_chat_enabled = True
    o._set_tell_chat_enabled(False)
    assert o._tell_chat_enabled is False
    o._set_tell_chat_enabled(True)
    assert o._tell_chat_enabled is True


@pytest.mark.parametrize("raw,expect", [(40, 40), (0, 0), (-5, 0),
                                        (99999, 3600), ("55", 55)])
def test_set_stream_delay_clamps(raw, expect) -> None:
    o = Orchestrator.__new__(Orchestrator)
    o._stream_delay_seconds = 40
    o._set_stream_delay_seconds(raw)
    assert o._stream_delay_seconds == expect


def test_set_stream_delay_rejects_garbage() -> None:
    o = Orchestrator.__new__(Orchestrator)
    o._stream_delay_seconds = 40
    o._set_stream_delay_seconds("not a number")
    assert o._stream_delay_seconds == 40       # unchanged, no raise


# ---------------------------------------------- on-miss presence refresh
def test_roster_miss_triggers_presence_refresh_and_retries(monkeypatch) -> None:
    """Live 2026-07-10: 'tell saltwaterbottle in chat hi' failed because the
    observed-only roster had no lurkers. On a miss, the handler folds the
    CURRENT viewer list in once and re-matches before giving up."""
    roster = UserRoster()
    roster.observe("ultron_kenning")          # only a talker; target is lurking
    o = _mk(monkeypatch, roster=roster)

    def fake_refresh() -> int:
        roster.observe("saltwaterbottle", "Saltwaterbottle")
        return 5

    o._twitch_chatters_refresh = fake_refresh
    assert o._maybe_handle_tell_chat(
        "tell saltwaterbottle in chat hi") is True
    assert o._posted == ["@Saltwaterbottle 🎙️ [live]: hi"]
    assert o._spoken == []                     # success stays silent


def test_roster_miss_refresh_finds_nothing_speaks_no_match(monkeypatch) -> None:
    roster = UserRoster()
    roster.observe("ultron_kenning")
    o = _mk(monkeypatch, roster=roster)
    o._twitch_chatters_refresh = lambda: 0     # scope missing / sidecar down
    assert o._maybe_handle_tell_chat("tell saltwaterbottle in chat hi") is True
    assert o._posted == []
    assert o._spoken == ["No one in chat matches saltwaterbottle."]


def test_roster_miss_refresh_raising_is_owned(monkeypatch) -> None:
    roster = UserRoster()
    o = _mk(monkeypatch, roster=roster)

    def boom() -> int:
        raise RuntimeError("sidecar down")

    o._twitch_chatters_refresh = boom
    assert o._maybe_handle_tell_chat("tell bob in chat hi") is True
    assert o._spoken == ["No one in chat matches bob."]


def test_orchestrator_wires_presence_seeding() -> None:
    import inspect

    src = inspect.getsource(Orchestrator._start_twitch_chat_mode)
    assert "_chatters_seed_loop" in src
    assert "twitch-chatters-seed" in src
    assert "chatters_presence_seed_minutes" in src
    assert "_twitch_chatters_refresh" in src
    tell = inspect.getsource(Orchestrator._maybe_handle_tell_chat)
    assert "_twitch_chatters_refresh" in tell   # the on-miss retry


def test_config_presence_seed_default() -> None:
    from kenning.config import TwitchChatConfig
    assert TwitchChatConfig().chatters_presence_seed_minutes == 5


def test_broadcaster_scope_includes_read_chatters() -> None:
    from kenning.twitch.auth import BROADCASTER_SCOPES
    assert "moderator:read:chatters" in BROADCASTER_SCOPES


# ------------------------------------------------ verbless confidence gate
def test_verbless_confident_match_posts(monkeypatch) -> None:
    """The live fix: the wake strip swallowed the verb — a verbless tell with
    a confident roster match still posts (silently)."""
    roster = UserRoster()
    roster.observe("saltwaterbottle", "Saltwaterbottle")
    o = _mk(monkeypatch, roster=roster)
    assert o._maybe_handle_tell_chat(
        "Saltwater bottle in chat, hello, welcome to the stream.") is True
    assert o._posted == [
        "@Saltwaterbottle 🎙️ [live]: hello, welcome to the stream."]
    assert o._spoken == []


def test_verbless_no_match_falls_through_to_conversation(monkeypatch) -> None:
    """'I posted in chat earlier' matches verbless but finds no roster name —
    it must reach the LLM as conversation, NOT consume the turn."""
    roster = UserRoster()
    roster.observe("saltwaterbottle")
    o = _mk(monkeypatch, roster=roster)
    assert o._maybe_handle_tell_chat("I posted in chat earlier") is False
    assert o._posted == [] and o._spoken == []


def test_verbless_toggle_off_and_disconnected_fall_through(monkeypatch) -> None:
    o = _mk(monkeypatch, enabled=False)
    assert o._maybe_handle_tell_chat("bob in chat hello there") is False
    assert o._spoken == []                     # no 'chat line is closed'
    o2 = _mk(monkeypatch, post="absent")
    assert o2._maybe_handle_tell_chat("bob in chat hello there") is False
    assert o2._spoken == []
