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
    """Each test starts/ends with the speaker-mute override cleared (global) +
    the ref-counted mute scope depth reset (CHANGE 4 global state)."""
    k.set_live_speaker_mute(None)
    k._chat_mute_depth = 0
    k._chat_mute_saved = None
    yield
    k.set_live_speaker_mute(None)
    k._chat_mute_depth = 0
    k._chat_mute_saved = None


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

    def _speaker_mute_scope(self):
        # Use the REAL ref-counted scope so the test exercises the production gate.
        return Orchestrator._speaker_mute_scope(self)


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


# --------------------------------------------------------------------------- #
# CHANGE 4 (2026-06-26) — REFERENCE-COUNTED speaker mute: back-to-back / overlapping
# gated clips must NOT unmute between them (the speak-redeem + chat-reply race).
# --------------------------------------------------------------------------- #
class _RaceOrch:
    """Stand-in carrying _chat_speak / _result_speak + a _speak that records the
    live mute state at speak time. Lets the inner clip's _speak trigger ANOTHER
    gated clip to model the overlap (one path's restore must not unmute the other)."""

    def __init__(self) -> None:
        self._chat_audio_to_speakers = False     # HEAR CHAT off
        self._hear_results_to_speakers = False   # HEAR RESULTS off
        self.muted_at_speak: list[bool] = []
        self._on_inner = None

    def _speak(self, text: str) -> None:
        self.muted_at_speak.append(k._speakers_muted())
        if self._on_inner is not None:
            cb, self._on_inner = self._on_inner, None
            cb()   # fire the OVERLAPPING clip while THIS one is still "playing"

    def _speaker_mute_scope(self):
        return Orchestrator._speaker_mute_scope(self)


def test_overlapping_chat_clips_stay_muted_no_unmute_between():
    # Clip A (chat) is "playing" when clip B (another chat line) starts; B finishes
    # FIRST -> its scope-exit must NOT unmute, because A is still active. Both must
    # observe a muted speaker, and the prior override is restored ONLY at the end.
    orch = _RaceOrch()
    orch._on_inner = lambda: Orchestrator._chat_speak(orch, "clip B")
    Orchestrator._chat_speak(orch, "clip A")
    # BOTH clips saw the speakers muted (no leak) ...
    assert orch.muted_at_speak == [True, True]
    # ... and the depth is back to 0 with the prior (None) restored at the very end.
    assert k._chat_mute_depth == 0
    assert k._live_speaker_mute is None


def test_overlapping_chat_then_result_clip_stays_muted():
    # CROSS-PATH overlap: a chat-reply (HEAR CHAT) and a game-result announce (HEAR
    # RESULTS) overlapping must SHARE the one ref-counted scope -> neither clobbers
    # the other's mute. The result clip starts while the chat clip is active.
    orch = _RaceOrch()
    orch._on_inner = lambda: Orchestrator._result_speak(orch, "HEIST WIN")
    Orchestrator._chat_speak(orch, "chat reply")
    assert orch.muted_at_speak == [True, True]   # both muted; no unmute between
    assert k._chat_mute_depth == 0
    assert k._live_speaker_mute is None


def test_concurrent_threads_never_unmute_mid_clip():
    # The real race: two gated clips on DIFFERENT threads. Each thread enters the
    # scope, waits on a barrier so they OVERLAP, then exits. While both are inside,
    # and as the FIRST one exits, the live mute must stay True (only the LAST exit
    # restores). Driven through the public enter/exit so it exercises the lock.
    import threading

    k.set_live_speaker_mute(None)
    k._chat_mute_depth = 0
    k._chat_mute_saved = None

    both_in = threading.Barrier(2)
    first_exited = threading.Event()
    second_may_exit = threading.Event()
    observations: dict[str, object] = {}

    def worker_a():
        k._enter_chat_speaker_mute()
        both_in.wait(timeout=5)
        # A exits FIRST while B is still inside -> must remain muted.
        k._exit_chat_speaker_mute()
        observations["after_a_exit_muted"] = k._speakers_muted()
        observations["after_a_exit_depth"] = k._chat_mute_depth
        first_exited.set()

    def worker_b():
        k._enter_chat_speaker_mute()
        both_in.wait(timeout=5)
        first_exited.wait(timeout=5)
        # B is the LAST leaver -> this exit restores the prior override.
        k._exit_chat_speaker_mute()
        observations["after_b_exit_muted"] = k._speakers_muted()
        second_may_exit.set()

    ta = threading.Thread(target=worker_a, name="clip-a")
    tb = threading.Thread(target=worker_b, name="clip-b")
    ta.start(); tb.start()
    ta.join(timeout=6); tb.join(timeout=6)
    second_may_exit.wait(timeout=6)

    # After A (the first) exited, the speaker was STILL muted (B active) at depth 1.
    assert observations["after_a_exit_muted"] is True
    assert observations["after_a_exit_depth"] == 1
    # After B (the last) exited, the prior override (None) is restored -> unmuted.
    assert observations["after_b_exit_muted"] is False
    assert k._chat_mute_depth == 0
    assert k._live_speaker_mute is None


def test_scope_preserves_prior_nondefault_override_under_nesting():
    # A pre-existing explicit override (user clicked global MUTE=False / UNMUTE) is
    # saved by the FIRST entrant and restored only by the LAST -- nesting included.
    k.set_live_speaker_mute(False)               # prior: explicitly UNMUTED
    k._chat_mute_depth = 0
    k._chat_mute_saved = None
    orch = _RaceOrch()
    orch._on_inner = lambda: Orchestrator._chat_speak(orch, "inner")
    Orchestrator._chat_speak(orch, "outer")
    assert orch.muted_at_speak == [True, True]   # muted across both
    assert k._live_speaker_mute is False         # prior explicit value restored once
