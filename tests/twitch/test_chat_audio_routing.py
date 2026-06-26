"""Chat-audio routing toggle (2026-06-26).

The streamer's CHAT-directed audio -- the Twitch chat-reply path AND the
"ultron says" (SPEAK_SAY) redeem, both funnelled through the orchestrator's
``_twitch_speak_and_post`` -> ``_chat_speak`` -- plays to OBS / the broadcast
mirror ONLY by default, NOT the local speakers, so it isn't distracting mid-game.
A "HEAR CHAT" stop-button toggle flips local-speaker playback ON/OFF. Default OFF.

The lever is a PER-UTTERANCE ``set_live_speaker_mute`` wrapper around ``_speak``:
``kokoro_engine._play`` tees the clip to the BroadcastSink (OBS) BEFORE the local
speaker write and zeroes ONLY the local buffer when ``_speakers_muted()`` is True,
so the OBS mirror always receives the clip while the speakers are silenced.

Fully offline: ``Orchestrator._chat_speak`` is exercised as an UNBOUND method on a
tiny fake ``self`` (no boot, no model, no TTS). A fake ``_speak`` records the live
``_speakers_muted()`` state at the moment of speaking, which proves the routing.
"""
from __future__ import annotations

import pytest

from kenning.pipeline.orchestrator import Orchestrator
from kenning.tts import kokoro_engine as k


@pytest.fixture(autouse=True)
def _reset_override():
    """Each test starts/ends with the speaker-mute override cleared (global)."""
    k.set_live_speaker_mute(None)
    yield
    k.set_live_speaker_mute(None)


class _FakeOrch:
    """Minimal stand-in for the orchestrator: just the attrs/methods _chat_speak
    touches. ``_speak`` records whether the LOCAL speakers were muted at the
    instant of speaking (what actually determines OBS-only vs speakers+OBS)."""

    def __init__(self, *, to_speakers: bool) -> None:
        self._chat_audio_to_speakers = to_speakers
        self.spoken: list[str] = []
        self.muted_at_speak: list[bool] = []

    def _speak(self, text: str) -> None:
        # Record the live mute state AT speak time -- the broadcast tee always
        # fires inside the real _play; muted == "local speakers suppressed".
        self.muted_at_speak.append(k._speakers_muted())
        self.spoken.append(text)


def _chat_speak(orch, text):
    """Call the real (unbound) Orchestrator._chat_speak with our fake self."""
    return Orchestrator._chat_speak(orch, text)


# --------------------------------------------------------------------------- #
# flag OFF (default) -> OBS / broadcast ONLY, local speakers suppressed
# --------------------------------------------------------------------------- #
def test_flag_off_suppresses_local_speakers_for_the_utterance():
    orch = _FakeOrch(to_speakers=False)
    _chat_speak(orch, "chat says hi")
    assert orch.spoken == ["chat says hi"]
    # The local speakers were MUTED while speaking (the OBS tee still got it).
    assert orch.muted_at_speak == [True]


def test_flag_off_restores_override_after_speaking():
    # The per-utterance mute must NOT leak into the next (team/conversational)
    # line: the override is restored to its prior value (None) in a finally.
    orch = _FakeOrch(to_speakers=False)
    assert k._live_speaker_mute is None
    _chat_speak(orch, "chat line")
    assert k._live_speaker_mute is None        # restored, not left True


def test_flag_off_restores_prior_nondefault_override():
    # If something had already set a live override (e.g. the user clicked global
    # MUTE), _chat_speak restores THAT exact value afterwards, not None.
    orch = _FakeOrch(to_speakers=False)
    k.set_live_speaker_mute(False)             # prior state: explicitly UNMUTED
    _chat_speak(orch, "chat line")
    assert orch.muted_at_speak == [True]       # still OBS-only during the line
    assert k._live_speaker_mute is False       # prior explicit value restored


# --------------------------------------------------------------------------- #
# flag ON -> speakers + OBS (normal _speak, no per-utterance mute)
# --------------------------------------------------------------------------- #
def test_flag_on_plays_to_local_speakers(monkeypatch):
    # With no config mute, speakers are NOT muted while speaking -> heard locally.
    class _Cfg:
        class audio:
            mute_speakers = False

    monkeypatch.setattr("kenning.config.get_config", lambda: _Cfg)
    orch = _FakeOrch(to_speakers=True)
    _chat_speak(orch, "heard out loud")
    assert orch.spoken == ["heard out loud"]
    assert orch.muted_at_speak == [False]      # local speakers live
    assert k._live_speaker_mute is None        # never touched the override


# --------------------------------------------------------------------------- #
# edge cases
# --------------------------------------------------------------------------- #
def test_empty_text_is_not_spoken():
    orch = _FakeOrch(to_speakers=False)
    _chat_speak(orch, "")
    assert orch.spoken == []
    assert k._live_speaker_mute is None


def test_default_flag_is_off():
    # The routing default is OBS-only: a fresh fake mirrors the orchestrator's
    # self._chat_audio_to_speakers = False initialization.
    orch = _FakeOrch(to_speakers=False)
    assert orch._chat_audio_to_speakers is False


def test_setter_flips_the_flag():
    orch = _FakeOrch(to_speakers=False)
    Orchestrator._set_chat_audio_to_speakers(orch, True)
    assert orch._chat_audio_to_speakers is True
    Orchestrator._set_chat_audio_to_speakers(orch, False)
    assert orch._chat_audio_to_speakers is False


# --------------------------------------------------------------------------- #
# stop-button wiring: the HEAR-CHAT row appears + drives the callback
# --------------------------------------------------------------------------- #
def test_stop_button_accepts_hear_chat_toggle_params():
    # The overlay must accept the new wiring without error (no Tk shown here).
    from kenning.audio.stop_button import StopButtonOverlay

    seen: list[bool] = []

    def _cb(state: bool) -> None:
        seen.append(state)

    ov = StopButtonOverlay(
        on_stop=lambda: None,
        on_toggle_chat_audio=_cb,
        chat_audio_enabled=False,
        chat_audio_label="HEAR CHAT",
    )
    # The constructor stored the toggle + default state.
    assert ov._on_toggle_chat_audio is _cb
    assert ov._chat_audio_enabled is False
    assert ov._chat_audio_label == "HEAR CHAT"
