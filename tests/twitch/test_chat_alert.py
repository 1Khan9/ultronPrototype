"""Tests for the new-message SOUND ALERT (2026-07-11).

A speaker ping when a REAL viewer types, filtered to actual users: excluded
logins (bot / StreamElements / mod bots / broadcaster) never ping, a cooldown
throttles fast chat, and a ban-grace defer + re-check drops the ad-spam bots
Sery_bot auto-bans. The gate logic (ChatAlertPlayer) is pure + injectable; the
audio playback is the orchestrator's business (never exercised here).
"""
import inspect

import pytest

from kenning.twitch.chat_alert import ChatAlertPlayer


# --------------------------------------------------------------------------- #
# ChatAlertPlayer — the gate logic (fake clock, fake play, manual defer)
# --------------------------------------------------------------------------- #
class _Clock:
    def __init__(self, t=1000.0):
        self.t = float(t)

    def __call__(self):
        return self.t


def _player(**over):
    clock = over.pop("clock", _Clock())
    plays = over.pop("plays", [])
    banned = over.pop("banned", set())
    kw = dict(
        play_fn=lambda: plays.append(clock.t),
        is_banned_fn=lambda lg: lg in banned,
        exclude_logins=["ultron_kenning", "streamelements", "sery_bot"],
        cooldown_seconds=20.0,
        defer_seconds=0.0,          # fire inline unless a defer_fn is injected
        clock=clock,
    )
    kw.update(over)
    p = ChatAlertPlayer(**kw)
    return p, plays, banned, clock


def test_excluded_logins_never_ping():
    p, plays, _b, _c = _player()
    for lg in ("StreamElements", "ultron_kenning", "Sery_Bot", "@sery_bot"):
        p.observe(lg)
    assert plays == []


def test_real_user_pings():
    p, plays, _b, _c = _player()
    p.observe("alice")
    assert len(plays) == 1


def test_cooldown_throttles_fast_chat():
    p, plays, _b, clock = _player()
    p.observe("alice")
    clock.t = 1010.0
    p.observe("bob")               # within 20 s -> throttled
    assert len(plays) == 1
    clock.t = 1025.0
    p.observe("carol")             # past the window -> pings
    assert len(plays) == 2


def test_banned_user_suppressed_and_does_not_arm_cooldown():
    p, plays, banned, clock = _player()
    banned.add("spambot")
    p.observe("spambot")           # fires inline, banned at fire -> no ping
    assert plays == []
    # a REAL user right after is NOT blocked (the bot never armed the cooldown)
    clock.t = 1000.5
    p.observe("dave")
    assert len(plays) == 1


def test_empty_login_is_noop():
    p, plays, _b, _c = _player()
    p.observe("")
    p.observe("   ")
    p.observe(None)                # type: ignore[arg-type]
    assert plays == []


def test_play_fn_error_never_raises_and_clears_pending():
    def boom():
        raise RuntimeError("device gone")
    p, _plays, _b, clock = _player(play_fn=boom)
    p.observe("alice")             # must not raise
    # pending cleared -> a later real user can still ping
    clock.t = 1100.0
    hit = []
    p._play = lambda: hit.append(1)
    p.observe("bob")
    assert hit == [1]


def test_pending_defer_dedups_concurrent_messages():
    # An in-flight ban-grace defer blocks a second schedule (no double ping).
    stored = []
    def defer_fn(delay, fn):
        stored.append(fn)          # capture, do NOT run yet
    p, plays, _b, _c = _player(defer_seconds=0.5, defer_fn=defer_fn)
    p.observe("alice")             # schedules one defer
    p.observe("bob")               # in-flight -> ignored
    assert len(stored) == 1 and plays == []
    stored[0]()                    # the grace window elapses -> ping
    assert len(plays) == 1


def test_defer_fn_ban_recheck_at_fire_time():
    # A user NOT banned at observe but banned during the grace window is dropped.
    stored = []
    p, plays, banned, _c = _player(
        defer_seconds=0.5, defer_fn=lambda d, fn: stored.append(fn))
    p.observe("adbot")
    banned.add("adbot")            # Sery_bot bans during the 500 ms window
    stored[0]()
    assert plays == []


# --------------------------------------------------------------------------- #
# Config defaults
# --------------------------------------------------------------------------- #
def test_config_chat_alert_defaults():
    from kenning.config import StopButtonConfig, TwitchChatConfig
    c = TwitchChatConfig()
    assert c.chat_alert_enabled is True
    assert c.chat_alert_sound_path == ""          # off until a file is set
    assert c.chat_alert_volume == 0.5
    assert c.chat_alert_cooldown_seconds == 20.0
    assert c.chat_alert_ban_delay_seconds == 0.5
    assert "streamelements" in c.chat_alert_exclude_logins
    assert "sery_bot" in c.chat_alert_exclude_logins
    sb = StopButtonConfig()
    assert sb.alert_volume_height == 42
    assert sb.alert_volume_label == "PING VOL"


def test_config_alert_volume_clamped():
    from kenning.config import TwitchChatConfig
    with pytest.raises(Exception):
        TwitchChatConfig(chat_alert_volume=1.5)   # ge=0.0, le=1.0


# --------------------------------------------------------------------------- #
# Orchestrator wiring — setter, persistence, build gating, GUI + tick pins
# --------------------------------------------------------------------------- #
def _bare_orch():
    from kenning.pipeline.orchestrator import Orchestrator
    return Orchestrator.__new__(Orchestrator)


def test_set_alert_volume_clamps_and_scales(tmp_path, monkeypatch):
    o = _bare_orch()
    monkeypatch.setattr(o, "_alert_volume_state_path",
                        lambda: tmp_path / "chat_alert.json")
    o._alert_volume = 0.5
    o._set_alert_volume(80)
    assert abs(o._alert_volume - 0.8) < 1e-6
    o._set_alert_volume(200)                       # clamp high
    assert o._alert_volume == 1.0
    o._set_alert_volume(-5)                         # clamp low
    assert o._alert_volume == 0.0


def test_set_alert_volume_rejects_garbage(tmp_path, monkeypatch):
    o = _bare_orch()
    monkeypatch.setattr(o, "_alert_volume_state_path",
                        lambda: tmp_path / "chat_alert.json")
    o._alert_volume = 0.5
    o._set_alert_volume("nope")
    assert o._alert_volume == 0.5                   # unchanged, no raise


def test_alert_volume_persists_and_reloads(tmp_path, monkeypatch):
    o = _bare_orch()
    monkeypatch.setattr(o, "_alert_volume_state_path",
                        lambda: tmp_path / "chat_alert.json")
    # The durable round-trip (setter persist is debounced; test the write path
    # directly so it's deterministic — the debounce is covered separately).
    o._persist_alert_volume(30)
    assert abs(o._load_persisted_alert_volume() - 0.30) < 1e-6
    o2 = _bare_orch()
    monkeypatch.setattr(o2, "_alert_volume_state_path",
                        lambda: tmp_path / "chat_alert.json")
    assert abs(o2._load_persisted_alert_volume() - 0.30) < 1e-6


def test_set_alert_volume_gain_immediate_persist_debounced(tmp_path, monkeypatch):
    o = _bare_orch()
    monkeypatch.setattr(o, "_alert_volume_state_path",
                        lambda: tmp_path / "chat_alert.json")
    o._alert_volume = 0.5
    o._set_alert_volume(30)
    # Gain applies IMMEDIATELY (realtime); disk write is deferred to the timer.
    assert abs(o._alert_volume - 0.30) < 1e-6
    assert o._alert_volume_persist_pending == 30
    # Flush the debounce deterministically instead of sleeping.
    t = getattr(o, "_alert_volume_persist_timer", None)
    if t is not None:
        t.cancel()
    o._persist_alert_volume(o._alert_volume_persist_pending)
    assert abs(o._load_persisted_alert_volume() - 0.30) < 1e-6


def test_load_persisted_alert_volume_absent_is_none(tmp_path, monkeypatch):
    o = _bare_orch()
    monkeypatch.setattr(o, "_alert_volume_state_path",
                        lambda: tmp_path / "nope.json")
    assert o._load_persisted_alert_volume() is None


def test_build_chat_alert_disabled_without_sound_path():
    from types import SimpleNamespace
    o = _bare_orch()
    o._alert_volume = 0.5
    o._alert_pcm = None
    o._alert_sr = 0
    o._alert_device = None
    tcfg = SimpleNamespace(
        auth=SimpleNamespace(broadcaster_login="s", bot_login="b"),
        chat=SimpleNamespace(chat_alert_enabled=True, chat_alert_sound_path=""),
    )
    assert o._build_chat_alert(None, tcfg) is None


def test_build_chat_alert_disabled_flag():
    from types import SimpleNamespace
    o = _bare_orch()
    tcfg = SimpleNamespace(
        auth=SimpleNamespace(broadcaster_login="s", bot_login="b"),
        chat=SimpleNamespace(chat_alert_enabled=False,
                             chat_alert_sound_path="whatever.wav"),
    )
    assert o._build_chat_alert(None, tcfg) is None


# --------------------------------------------------------------------------- #
# BanTracker — the SHARED ban-guard (works even when the welcome is disabled)
# --------------------------------------------------------------------------- #
def test_ban_tracker_mark_and_query():
    from kenning.twitch.welcome import BanTracker
    bt = BanTracker()
    assert bt.is_banned("adbot") is False
    bt.mark_banned("AdBot")                 # case-insensitive
    assert bt.is_banned("adbot") is True
    assert bt.is_banned("") is False
    bt.mark_banned("")                      # no-op, no raise
    bt.mark_banned(None)                    # type: ignore[arg-type]


def test_alert_shares_ban_tracker_even_without_welcome():
    # Wiring pin: on_clear + the alert read a shared _ban_tracker (the welcomer
    # when welcome is on, else a standalone BanTracker) so the ad-bot filter is
    # NOT silently inert when the first-time welcome is disabled.
    from kenning.pipeline.orchestrator import Orchestrator
    src = inspect.getsource(Orchestrator._start_twitch_chat_mode)
    assert "_ban_tracker" in src
    assert "BanTracker()" in src
    assert "_ban_tracker.mark_banned" in src
    assert "_ban_tracker.is_banned" in src


def test_stop_button_alert_volume_slider_wired():
    from kenning.pipeline.orchestrator import Orchestrator
    src = inspect.getsource(Orchestrator.__init__)
    assert "on_set_alert_volume=" in src
    assert "_set_alert_volume" in src


def test_chat_games_calls_alert_fn_in_tick():
    from kenning.twitch.economy import chat_games
    src = inspect.getsource(chat_games.ChatGameRouter)
    assert "self._maybe_alert(ev)" in src
    assert "self._alert_fn" in src


def test_stop_button_accepts_alert_volume_kwargs():
    from kenning.audio.stop_button import StopButtonOverlay
    ov = StopButtonOverlay(
        on_stop=lambda: None,
        on_set_alert_volume=lambda v: None,
        alert_volume_value=70,
        alert_volume_height=40,
        alert_volume_label="PING VOL",
    )
    assert ov._on_set_alert_volume is not None
    assert ov._alert_volume_value == 70
    assert ov._alert_volume_h == 40
    assert ov._alert_volume_label == "PING VOL"


def test_chat_games_alert_fn_default_none_is_noop():
    # A router built WITHOUT alert_fn never calls it (byte-identical). Verified by
    # the guard in _maybe_alert: alert_fn is None -> immediate return.
    src = inspect.getsource(
        __import__("kenning.twitch.economy.chat_games", fromlist=["x"])
        .ChatGameRouter._maybe_alert)
    assert "if self._alert_fn is None" in src
