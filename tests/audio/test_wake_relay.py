"""Tests for the STOP-window WAKE RELAY toggle (spec 13, 2026-07-11).

WAKE RELAY ON (the DEFAULT) = a team relay requires the WAKE WORD: "Ultron, tell
my team push" / "Ultron, explain to my team ..." transmit; a bare "tell my team
X", a turbo callout ("sova hit 84"), or any un-waked relay is consumed SILENTLY
at the single relay choke point (never transmitted, never role-played). The run
loop computes ``wake_confirmed`` per turn -- True on a fresh acoustic wake (not
came_from_follow_up) OR when the RAW transcript leads with the wake word -- and
passes it to every _maybe_handle_relay_speech call. WAKE RELAY OFF = today's
behaviour (normal + turbo relay without the wake word). It composes UNDER the
RELAY master toggle (team_relay), which is checked first and dominates.

Hermetic: no Tk, no sidecar, no LLM. Mirrors tests/audio/test_team_relay_toggle.py.
"""
import inspect
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from kenning.audio.relay_speech import (
    set_team_relay_enabled,
    set_wake_relay_enabled,
    team_relay_enabled,
    utterance_leads_with_wake,
    wake_relay_enabled,
)
from kenning.pipeline.orchestrator import Orchestrator


@pytest.fixture(autouse=True)
def _restore_relay_flags():
    """Both flags are process-globals; never leak a toggled state into others."""
    before_wake = wake_relay_enabled()
    before_team = team_relay_enabled()
    yield
    set_wake_relay_enabled(before_wake)
    set_team_relay_enabled(before_team)


# ---------------------------------------------------------------------------
# relay_speech -- the module flag
# ---------------------------------------------------------------------------

def test_wake_relay_defaults_on():
    assert wake_relay_enabled() is True


def test_wake_relay_set_and_get():
    set_wake_relay_enabled(False)
    assert wake_relay_enabled() is False
    set_wake_relay_enabled(True)
    assert wake_relay_enabled() is True


# ---------------------------------------------------------------------------
# utterance_leads_with_wake -- the inline-wake detector (RAW transcript)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Ultron, tell my team push B",
    "ultron tell my team sova hit 84",
    "hey ultron explain to my team what the meaning of life is",
    "Altron, tell my team rotate",          # STT mishear of the wake word
    "Voltron tell my team push",            # STT mishear
    "kenning tell my team go",              # the alternate real wake word
    "  ultra tell my team A",               # leading whitespace + mishear
    "okay ultron tell my team fall back",   # politeness lead
])
def test_leads_with_wake_positives(text):
    assert utterance_leads_with_wake(text) is True


@pytest.mark.parametrize("text", [
    "tell my team push B",                  # normal relay, no wake word
    "sova hit 84",                          # bare turbo callout
    "rotate to garage",
    "run it down mid",                      # 'run' is NOT a wake homophone here
    "they have breach ult play off site",
    "ron is pushing long",                  # 'ron' excluded (ordinary word)
    "tron mid",                             # 'tron' excluded
    "",
    "   ",
])
def test_leads_with_wake_negatives(text):
    assert utterance_leads_with_wake(text) is False


def test_leads_with_wake_only_leading_not_midline():
    # A wake-ish token buried mid-callout must never satisfy the gate.
    assert utterance_leads_with_wake("rotate to ultra site") is False
    assert utterance_leads_with_wake("push and tell my team ultron") is False


# ---------------------------------------------------------------------------
# StopButtonOverlay -- ctor wiring
# ---------------------------------------------------------------------------

def test_stop_button_accepts_wake_relay_kwargs():
    from kenning.audio.stop_button import StopButtonOverlay
    ov = StopButtonOverlay(
        on_stop=lambda: None,
        on_toggle_wake_relay=lambda v: None,
        wake_relay_enabled=False,
        wake_relay_height=30,
        wake_relay_label="WAKE RELAY",
    )
    assert ov._on_toggle_wake_relay is not None
    assert ov._wake_relay_enabled is False
    assert ov._wake_relay_h == 30
    assert ov._wake_relay_label == "WAKE RELAY"


def test_stop_button_wake_relay_default_on_row_hidden():
    from kenning.audio.stop_button import StopButtonOverlay
    ov = StopButtonOverlay(on_stop=lambda: None)
    # Display state defaults ON (today's intent); no callback -> row hidden.
    assert ov._wake_relay_enabled is True
    assert ov._on_toggle_wake_relay is None


def test_stop_button_wake_relay_callback_stored():
    from kenning.audio.stop_button import StopButtonOverlay
    sentinel = []
    ov = StopButtonOverlay(
        on_stop=lambda: None,
        on_toggle_wake_relay=lambda v: sentinel.append(v),
    )
    assert ov._on_toggle_wake_relay is not None
    ov._on_toggle_wake_relay(False)
    assert sentinel == [False]


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_config_wake_relay_defaults():
    from kenning.config import RelaySpeechConfig, StopButtonConfig
    assert RelaySpeechConfig().wake_relay is True
    sb = StopButtonConfig()
    assert sb.wake_relay_height == 26
    assert sb.wake_relay_label == "WAKE RELAY"


# ---------------------------------------------------------------------------
# Orchestrator -- setter flips the shared module flag
# ---------------------------------------------------------------------------

def test_orchestrator_wake_relay_setter_flips_module_flag():
    o = Orchestrator.__new__(Orchestrator)
    o._set_wake_relay_enabled(False)
    assert wake_relay_enabled() is False
    o._set_wake_relay_enabled(True)
    assert wake_relay_enabled() is True


def test_stop_button_wired_with_wake_relay_callback():
    src = inspect.getsource(Orchestrator.__init__)
    assert "on_toggle_wake_relay=" in src
    assert "_set_wake_relay_enabled" in src
    # Boot-apply from config so config.yaml is authoritative at boot.
    assert "set_wake_relay_enabled" in src
    assert "wake_relay" in src


def test_run_loop_computes_wake_confirmed_and_passes_it():
    src = inspect.getsource(Orchestrator.run)
    assert "_wake_confirmed" in src
    assert "utterance_leads_with_wake" in src
    assert "came_from_follow_up" in src
    # Every relay call site threads the signal through.
    assert "wake_confirmed=_wake_confirmed" in src


# ---------------------------------------------------------------------------
# The gate -- the single choke point in _maybe_handle_relay_speech
# ---------------------------------------------------------------------------

def _relay_cfg(**overrides: Any) -> SimpleNamespace:
    cfg = dict(
        enabled=True,
        output_device="Voicemeeter Aux Input",
        rephrase=False,
        max_line_chars=280,
        echo_to_user=False,
    )
    cfg.update(overrides)
    return SimpleNamespace(**cfg)


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


def _no_transmit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert the team bus is never keyed."""
    import kenning.audio.relay_speech as relay_mod

    def must_not_play(pcm, sr, device, **kw):  # pragma: no cover
        raise AssertionError("WAKE RELAY: an un-waked relay must not transmit")

    monkeypatch.setattr(relay_mod, "resolve_relay_device", lambda c: 25)
    monkeypatch.setattr(relay_mod, "play_to_device", must_not_play)


def test_wake_relay_on_unwaked_relay_suppressed_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WAKE RELAY ON + no wake word (wake_confirmed=False) -> the matched relay is
    consumed SILENTLY (returns True, never transmitted, no spoken notice)."""
    o = _bare_orchestrator()
    o._relay_runtime_enabled = False   # would speak "muted" IF the gate passed
    set_team_relay_enabled(True)
    set_wake_relay_enabled(True)
    _patch_config(monkeypatch, _relay_cfg())
    _no_transmit(monkeypatch)

    assert o._maybe_handle_relay_speech(
        "tell my team to rotate B", wake_confirmed=False) is True
    assert o._spoken == []             # suppressed BEFORE the mute notice


def test_wake_relay_on_force_true_unwaked_suppressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """force=True (turbo backstop / semantic router) funnels through the same
    choke point -- a forced un-waked callout is suppressed silently too."""
    o = _bare_orchestrator()
    o._relay_runtime_enabled = False
    set_team_relay_enabled(True)
    set_wake_relay_enabled(True)
    _patch_config(monkeypatch, _relay_cfg())
    _no_transmit(monkeypatch)

    assert o._maybe_handle_relay_speech(
        "sova hit 84", force=True, wake_confirmed=False) is True
    assert o._spoken == []


def test_wake_relay_on_waked_relay_passes_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WAKE RELAY ON + wake_confirmed=True -> the gate does NOT suppress; the turn
    proceeds past it (proven by reaching the downstream session-mute notice)."""
    o = _bare_orchestrator()
    o.tts = SimpleNamespace(
        _synthesize=lambda text: (np.ones(10, dtype=np.int16), 24000),
    )
    o._relay_runtime_enabled = False   # session mute -> "muted" IF gate passed
    set_team_relay_enabled(True)
    set_wake_relay_enabled(True)
    _patch_config(monkeypatch, _relay_cfg())

    assert o._maybe_handle_relay_speech(
        "tell my team to rotate B", wake_confirmed=True) is True
    assert o._spoken and "muted" in o._spoken[0]


def test_wake_relay_default_wake_confirmed_true_preserves_direct_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """wake_confirmed defaults True, so existing direct callers / tests that do
    NOT pass it are unaffected even with WAKE RELAY ON."""
    o = _bare_orchestrator()
    o.tts = SimpleNamespace(
        _synthesize=lambda text: (np.ones(10, dtype=np.int16), 24000),
    )
    o._relay_runtime_enabled = False
    set_team_relay_enabled(True)
    set_wake_relay_enabled(True)
    _patch_config(monkeypatch, _relay_cfg())

    assert o._maybe_handle_relay_speech("tell my team to rotate B") is True
    assert o._spoken and "muted" in o._spoken[0]


def test_wake_relay_off_unwaked_relay_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WAKE RELAY OFF = today's behaviour: an un-waked relay is NOT suppressed by
    the wake gate (reaches the downstream mute notice)."""
    o = _bare_orchestrator()
    o.tts = SimpleNamespace(
        _synthesize=lambda text: (np.ones(10, dtype=np.int16), 24000),
    )
    o._relay_runtime_enabled = False
    set_team_relay_enabled(True)
    set_wake_relay_enabled(False)
    _patch_config(monkeypatch, _relay_cfg())

    assert o._maybe_handle_relay_speech(
        "tell my team to rotate B", wake_confirmed=False) is True
    assert o._spoken and "muted" in o._spoken[0]


def test_team_relay_off_dominates_wake_relay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The RELAY master (team_relay) is checked FIRST: team relay OFF suppresses
    silently even when wake_confirmed=True (full disengage wins)."""
    o = _bare_orchestrator()
    o._relay_runtime_enabled = False
    set_team_relay_enabled(False)
    set_wake_relay_enabled(True)
    _patch_config(monkeypatch, _relay_cfg())
    _no_transmit(monkeypatch)

    assert o._maybe_handle_relay_speech(
        "tell my team to rotate B", wake_confirmed=True) is True
    assert o._spoken == []             # team-relay-off silent, before the mute check


def test_wake_relay_on_ordinary_utterance_still_falls_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate sits AFTER the matcher: ordinary speech is untouched and falls to
    the conversational path (returns False) even with WAKE RELAY ON."""
    o = _bare_orchestrator()
    set_team_relay_enabled(True)
    set_wake_relay_enabled(True)
    _patch_config(monkeypatch, _relay_cfg())
    assert o._maybe_handle_relay_speech(
        "what time is it", wake_confirmed=False) is False
    assert o._spoken == []
