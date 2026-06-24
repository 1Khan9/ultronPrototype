"""Tests for the deterministic chat-settings voice parser."""
from __future__ import annotations

from kenning.twitch.moderation.chat_settings import parse_chat_settings


def test_clear_chat():
    c = parse_chat_settings("clear chat")
    assert c is not None and c.clear and c.settings == {}
    assert parse_chat_settings("clear the chat").clear
    assert parse_chat_settings("clear all chat").clear


def test_slow_mode_on_default_and_durations():
    assert parse_chat_settings("slow mode on").settings == {
        "slow_mode": True, "slow_mode_wait_time": 30}
    assert parse_chat_settings("slow mode").settings["slow_mode_wait_time"] == 30
    assert parse_chat_settings("slow mode 45 seconds").settings["slow_mode_wait_time"] == 45
    # 2 minutes -> 120s, clamped to the Twitch max (120)
    assert parse_chat_settings("enable slow mode for 2 minutes").settings["slow_mode_wait_time"] == 120
    # below the 3s floor clamps up
    assert parse_chat_settings("slow mode 1 second").settings["slow_mode_wait_time"] == 3


def test_slow_mode_off():
    assert parse_chat_settings("slow mode off").settings == {"slow_mode": False}
    assert parse_chat_settings("turn off slow mode").settings == {"slow_mode": False}
    assert parse_chat_settings("disable slow mode").settings == {"slow_mode": False}


def test_followers_only():
    assert parse_chat_settings("followers only").settings == {
        "follower_mode": True, "follower_mode_duration": 0}
    assert parse_chat_settings("followers only off").settings == {"follower_mode": False}
    assert parse_chat_settings("followers only for 10 minutes").settings == {
        "follower_mode": True, "follower_mode_duration": 10}


def test_sub_emote_unique_modes():
    assert parse_chat_settings("subscribers only").settings == {"subscriber_mode": True}
    assert parse_chat_settings("sub only mode").settings == {"subscriber_mode": True}
    assert parse_chat_settings("emote only").settings == {"emote_mode": True}
    assert parse_chat_settings("emote only off").settings == {"emote_mode": False}
    assert parse_chat_settings("unique chat").settings == {"unique_chat_mode": True}
    assert parse_chat_settings("turn off unique chat").settings == {"unique_chat_mode": False}


def test_readback_present():
    assert "Slow mode on" in parse_chat_settings("slow mode on").readback
    assert parse_chat_settings("clear chat").readback == "Chat cleared."
    assert "Emote-only off" in parse_chat_settings("emote only off").readback


def test_non_command_returns_none():
    assert parse_chat_settings("rush B now") is None
    assert parse_chat_settings("tell my team to push A") is None
    assert parse_chat_settings("what time is it") is None
    assert parse_chat_settings("") is None
    assert parse_chat_settings("   ") is None
