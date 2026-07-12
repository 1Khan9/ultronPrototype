"""Tests for the STOP-window TEAM BUS toggle (2026-07-12).

Switches the team-relay OUTPUT between the primary VoiceMeeter strip (B1,
"separate") and an ALT strip (B2, "shares the streamer's mic bus"). Anticheat-
clean by construction: it only changes WHICH output DEVICE the relay plays into
(the same play_to_device path) -- no VoiceMeeter control API. Default OFF (B1).
Hermetic: no Tk, no audio device, no VoiceMeeter.
"""
import inspect
from types import SimpleNamespace

import pytest

from kenning.audio.relay_speech import (
    active_relay_output_device,
    set_team_bus_alt_enabled,
    team_bus_alt_enabled,
)
from kenning.pipeline.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _restore_team_bus_flag():
    before = team_bus_alt_enabled()
    yield
    set_team_bus_alt_enabled(before)


# --------------------------------------------------------------------------- #
# relay_speech -- the module flag + active-device resolver
# --------------------------------------------------------------------------- #
def test_team_bus_defaults_off_b1():
    assert team_bus_alt_enabled() is False


def test_team_bus_set_and_get():
    set_team_bus_alt_enabled(True)
    assert team_bus_alt_enabled() is True
    set_team_bus_alt_enabled(False)
    assert team_bus_alt_enabled() is False


def _cfg(alt="Voicemeeter VAIO3 Input"):
    return SimpleNamespace(output_device="Voicemeeter Input",
                           team_bus_alt_device=alt)


def test_active_device_is_primary_when_off():
    set_team_bus_alt_enabled(False)
    assert active_relay_output_device(_cfg()) == "Voicemeeter Input"


def test_active_device_is_alt_when_on():
    set_team_bus_alt_enabled(True)
    assert active_relay_output_device(_cfg()) == "Voicemeeter VAIO3 Input"


def test_active_device_falls_back_to_primary_when_alt_unset():
    set_team_bus_alt_enabled(True)
    assert active_relay_output_device(_cfg(alt="")) == "Voicemeeter Input"
    assert active_relay_output_device(_cfg(alt="   ")) == "Voicemeeter Input"


def test_active_device_alt_whitespace_stripped():
    set_team_bus_alt_enabled(True)
    cfg = SimpleNamespace(output_device="Voicemeeter Input",
                          team_bus_alt_device="  Voicemeeter VAIO3 Input  ")
    assert active_relay_output_device(cfg) == "Voicemeeter VAIO3 Input"


def test_active_device_failsafe_on_bad_cfg():
    # Missing output_device -> returns the alt (never strands the relay); an
    # object with neither -> None, never raises.
    set_team_bus_alt_enabled(True)
    assert active_relay_output_device(SimpleNamespace(
        team_bus_alt_device="X")) == "X"
    assert active_relay_output_device(object()) is None  # no attrs, no raise


# --------------------------------------------------------------------------- #
# Orchestrator -- setter + it routes both relay paths through the active device
# --------------------------------------------------------------------------- #
def test_orchestrator_team_bus_setter_flips_flag():
    o = Orchestrator.__new__(Orchestrator)
    o._set_team_bus_alt(True)
    assert team_bus_alt_enabled() is True
    o._set_team_bus_alt(False)
    assert team_bus_alt_enabled() is False


def test_both_relay_paths_use_active_device():
    # The voice relay AND the SPEAK_TEAM redeem must resolve the ACTIVE device
    # (honoring the toggle), not the raw cfg.output_device.
    voice = inspect.getsource(Orchestrator._maybe_handle_relay_speech)
    assert "active_relay_output_device(cfg)" in voice
    assert "resolve_relay_device(getattr(cfg, \"output_device\"" not in voice
    src = inspect.getsource(Orchestrator)
    # exactly the two team-output call sites use the active device
    assert src.count("resolve_relay_device(active_relay_output_device(cfg))") == 2


def test_stop_button_team_bus_wired_when_alt_configured():
    src = inspect.getsource(Orchestrator.__init__)
    assert "on_toggle_team_bus=" in src
    assert "_set_team_bus_alt" in src
    assert "team_bus_alt_device" in src   # gated on the alt being set


def test_stop_button_team_bus_display_seeds_from_live_flag():
    # The button's initial label must reflect the ACTUAL bus (the live module
    # flag), not a hardcoded B1 — else env KENNING_TEAM_BUS_ALT=1 routes to B2
    # while the row shows B1 (review P2). Seed from team_bus_alt_enabled().
    src = inspect.getsource(Orchestrator.__init__)
    assert "team_bus_alt_enabled" in src
    assert "team_bus_enabled=_team_bus_on0" in src
    assert "team_bus_enabled=False" not in src   # no hardcoded default


# --------------------------------------------------------------------------- #
# Config defaults
# --------------------------------------------------------------------------- #
def test_config_team_bus_defaults():
    from kenning.config import RelaySpeechConfig, StopButtonConfig
    assert RelaySpeechConfig().team_bus_alt_device == ""   # off until set
    sb = StopButtonConfig()
    assert sb.team_bus_height == 26
    assert sb.team_bus_label == "TEAM"


# --------------------------------------------------------------------------- #
# StopButtonOverlay -- ctor wiring
# --------------------------------------------------------------------------- #
def test_stop_button_accepts_team_bus_kwargs():
    from kenning.audio.stop_button import StopButtonOverlay
    ov = StopButtonOverlay(
        on_stop=lambda: None,
        on_toggle_team_bus=lambda v: None,
        team_bus_enabled=False,
        team_bus_height=30,
        team_bus_label="TEAM",
    )
    assert ov._on_toggle_team_bus is not None
    assert ov._team_bus_enabled is False
    assert ov._team_bus_h == 30
    assert ov._team_bus_label == "TEAM"


def test_stop_button_team_bus_hidden_without_callback():
    from kenning.audio.stop_button import StopButtonOverlay
    ov = StopButtonOverlay(on_stop=lambda: None)
    assert ov._on_toggle_team_bus is None      # -> _has_team_bus False -> row hidden


def test_stop_button_team_bus_callback_flips_and_reports():
    from kenning.audio.stop_button import StopButtonOverlay
    seen = []
    ov = StopButtonOverlay(on_stop=lambda: None,
                           on_toggle_team_bus=lambda v: seen.append(v))
    ov._on_toggle_team_bus(True)
    ov._on_toggle_team_bus(False)
    assert seen == [True, False]
