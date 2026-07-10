"""Pinboard keeper decision + poster-consolidation defaults (2026-07-09).

The flood fix: ONE pinned commands message (kept by the keeper) + ONE 20-min
talk hint, instead of three drifting interval posters. Pins the decision
matrix (never fight a manual pin; never blind re-post on unreadable state),
the config default flips, and the orchestrator wiring.
"""
from __future__ import annotations

import inspect

from kenning.twitch.panel import pinboard_should_pin


# ------------------------------------------------------------ decision matrix
def test_no_active_pin_pins():
    state = {"ok": True, "active": False, "readable": True}
    assert pinboard_should_pin(state, pinned_this_boot=False) is True
    # ...and again after an expiry/manual unpin, even if we pinned earlier
    assert pinboard_should_pin(state, pinned_this_boot=True) is True


def test_active_pin_never_replaced():
    """An active pin might be the streamer's manual pin — NEVER fight it."""
    state = {"ok": True, "active": True, "readable": True}
    assert pinboard_should_pin(state, pinned_this_boot=False) is False
    assert pinboard_should_pin(state, pinned_this_boot=True) is False


def test_unreadable_state_pins_once_per_boot_only():
    """Open-beta GET may be unavailable: pin once, then never blind re-post
    (a blind re-post loop would re-create the reminder flood)."""
    for state in ({"ok": True, "active": None, "readable": False}, None, "junk"):
        assert pinboard_should_pin(state, pinned_this_boot=False) is True
        assert pinboard_should_pin(state, pinned_this_boot=True) is False


# ------------------------------------------------------------ config defaults
def test_flood_fix_config_defaults():
    from kenning.config import TwitchChatConfig

    cfg = TwitchChatConfig()
    assert cfg.pinboard_enabled is True
    assert cfg.pinboard_check_interval_minutes == 15
    assert cfg.talk_hint_interval_minutes == 20      # was 10 (streamer: ~20 min)
    assert cfg.song_hint_enabled is False            # folded into the pinboard
    assert cfg.commands_panel_enabled is False       # schema default unchanged


# ------------------------------------------------------------ orchestrator pin
def test_orchestrator_wires_the_pinboard_keeper():
    from kenning.pipeline.orchestrator import Orchestrator

    src = inspect.getsource(Orchestrator._start_twitch_chat_mode)
    assert "_pinboard_loop" in src
    assert "twitch-pinboard" in src
    assert "pinboard_should_pin" in src
    assert "pinboard_enabled" in src
    # the keeper posts to /pin (send+pin), not /say (that would be the flood)
    assert '"/pin"' in src or "/pin" in src
    # review 2026-07-09 P1: a posted-but-unpinned outcome LATCHES the keeper
    # off for the boot — a broken open-beta pin leg must never degrade the
    # pinboard into an interval poster. And the latch is set only when
    # something actually reached chat (a pure send failure may retry).
    assert "pin_leg_broken" in src
    assert src.count("pin_leg_broken") >= 3       # init + check + set
    assert "posted = bool(res.get(" in src
