"""Fast speaker mute/unmute (2026-06-18).

The GUI quick MUTE / UNMUTE buttons fire a dedicated ``speaker_mute`` action
that flips a live override in the TTS engine directly, instead of going through
a full (heavy) config reload + spoken "Settings updated." confirmation.

These tests cover the live-override precedence + the tri-state clear; the GUI
wiring (write_action + overlay sync) and the orchestrator action branch are thin
glue verified by inspection.
"""
from __future__ import annotations

import pytest

from kenning.tts import kokoro_engine as k


@pytest.fixture(autouse=True)
def _reset_override():
    """Each test starts/ends with the override cleared (process-global)."""
    k.set_live_speaker_mute(None)
    yield
    k.set_live_speaker_mute(None)


def test_default_defers_to_config(monkeypatch):
    # No live override -> _speakers_muted reads audio.mute_speakers.
    class _Cfg:
        class audio:
            mute_speakers = True

    monkeypatch.setattr("kenning.config.get_config", lambda: _Cfg)
    assert k._live_speaker_mute is None
    assert k._speakers_muted() is True

    _Cfg.audio.mute_speakers = False
    assert k._speakers_muted() is False


def test_live_override_wins_over_config(monkeypatch):
    class _Cfg:
        class audio:
            mute_speakers = False  # config says NOT muted

    monkeypatch.setattr("kenning.config.get_config", lambda: _Cfg)
    k.set_live_speaker_mute(True)            # but the user just clicked MUTE
    assert k._speakers_muted() is True

    k.set_live_speaker_mute(False)           # ...then UNMUTE
    assert k._speakers_muted() is False


def test_clear_restores_config(monkeypatch):
    class _Cfg:
        class audio:
            mute_speakers = True

    monkeypatch.setattr("kenning.config.get_config", lambda: _Cfg)
    k.set_live_speaker_mute(False)
    assert k._speakers_muted() is False       # override active
    k.set_live_speaker_mute(None)             # full reload clears it
    assert k._speakers_muted() is True        # config authoritative again


def test_set_coerces_to_bool():
    k.set_live_speaker_mute(1)
    assert k._live_speaker_mute is True
    k.set_live_speaker_mute(0)
    assert k._live_speaker_mute is False


def test_speakers_muted_fails_open(monkeypatch):
    # get_config blowing up -> NOT muted (never silence on an error).
    def _boom():
        raise RuntimeError("config unavailable")

    monkeypatch.setattr("kenning.config.get_config", _boom)
    assert k._live_speaker_mute is None
    assert k._speakers_muted() is False
