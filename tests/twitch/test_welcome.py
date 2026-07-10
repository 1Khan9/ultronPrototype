"""FirstTimeWelcomer + format_delay (spec 12, 2026-07-09).

Pins: once-per-login-per-run, broadcaster/bot exclusion, the rolling-minute
burst guard (overflow marked seen SILENTLY), live delay reads, the no-delay
template, and fail-open on a bad user-edited template.
"""
from __future__ import annotations

from kenning.twitch.welcome import FirstTimeWelcomer, format_delay

TPL = "@{name} welcome — the feed runs {delay} behind."
TPL_ND = "@{name} welcome."


def _mk(**kw):
    defaults = dict(
        template=TPL,
        template_no_delay=TPL_ND,
        delay_fn=lambda: 40,
        max_per_minute=4,
    )
    defaults.update(kw)
    return FirstTimeWelcomer(**defaults)


# ------------------------------------------------------------- format_delay
def test_format_delay_units():
    assert format_delay(40) == "40 seconds"
    assert format_delay(1) == "1 second"
    assert format_delay(60) == "1 minute"
    assert format_delay(80) == "1 minute 20 seconds"
    assert format_delay(120) == "2 minutes"
    assert format_delay(61) == "1 minute 1 second"
    assert format_delay(0) == "0 seconds"
    assert format_delay(-5) == "0 seconds"


# ------------------------------------------------------------ once per login
def test_first_message_welcomed_once():
    w = _mk()
    out = w.observe("newbie", display_name="Newbie")
    assert out == "@Newbie welcome — the feed runs 40 seconds behind."
    assert w.observe("newbie", display_name="Newbie") is None
    assert w.observe("NEWBIE") is None, "login match is case-insensitive"


def test_display_name_falls_back_to_login():
    w = _mk()
    assert w.observe("ghost") == "@ghost welcome — the feed runs 40 seconds behind."


def test_distinct_logins_each_welcomed():
    w = _mk()
    assert w.observe("a") is not None
    assert w.observe("b") is not None
    assert w.seen_count() == 2


def test_blank_or_invalid_login_ignored():
    w = _mk()
    assert w.observe("") is None
    assert w.observe("   ") is None
    assert w.observe(None) is None  # type: ignore[arg-type]
    assert w.seen_count() == 0


# ----------------------------------------------------------------- exclusion
def test_excluded_login_and_uid_never_welcomed():
    w = _mk(exclude_logins={"ultron_kenning"}, exclude_uids={"111"})
    assert w.observe("ultron_kenning", chatter_uid="999") is None
    assert w.observe("somebot", chatter_uid="111") is None
    # and they stay excluded on re-observe (marked seen)
    assert w.observe("ultron_kenning") is None


def test_broadcaster_never_welcomed_in_own_channel():
    w = _mk()
    assert w.observe("streamer", chatter_uid="42", broadcaster_uid="42") is None
    assert w.observe("viewer", chatter_uid="7", broadcaster_uid="42") is not None


# ---------------------------------------------------------------- burst guard
def test_burst_guard_caps_welcomes_and_marks_seen_silently():
    clock = {"t": 0.0}
    w = _mk(max_per_minute=2, now_fn=lambda: clock["t"])
    assert w.observe("r1") is not None
    assert w.observe("r2") is not None
    assert w.observe("r3") is None, "over budget -> silent"
    # r3 was marked seen: it is NOT welcomed later once budget frees up
    clock["t"] = 61.0
    assert w.observe("r3") is None
    # but a genuinely new login after the window IS welcomed
    assert w.observe("r4") is not None


def test_burst_guard_window_rolls():
    clock = {"t": 0.0}
    w = _mk(max_per_minute=1, now_fn=lambda: clock["t"])
    assert w.observe("a") is not None
    assert w.observe("b") is None
    clock["t"] = 30.0
    assert w.observe("c") is None, "window not yet rolled"
    clock["t"] = 61.0
    assert w.observe("d") is not None, "window rolled -> budget restored"


# ---------------------------------------------------------------- delay reads
def test_delay_is_read_live_per_welcome():
    delay = {"v": 40}
    w = _mk(delay_fn=lambda: delay["v"])
    assert "40 seconds" in w.observe("a")
    delay["v"] = 95
    assert "1 minute 35 seconds" in w.observe("b")


def test_zero_delay_uses_no_delay_template():
    w = _mk(delay_fn=lambda: 0)
    assert w.observe("a", display_name="A") == "@A welcome."


def test_delay_fn_failure_falls_back_to_no_delay_template():
    def boom():
        raise RuntimeError("gui not up")

    w = _mk(delay_fn=boom)
    assert w.observe("a") == "@a welcome."


# ------------------------------------------------------------------ fail-open
def test_bad_template_logs_and_skips():
    w = _mk(template="@{nmae} oops {delay}")
    assert w.observe("a") is None            # no crash, no text
    assert w.observe("b") is None            # still consuming quietly


def test_empty_render_returns_none():
    w = _mk(template_no_delay="   ", delay_fn=lambda: 0)
    assert w.observe("a") is None


# ---------------------------------------------------------------------------
# Durable welcomed-store (2026-07-09) — welcome once EVER, across restarts.
# ---------------------------------------------------------------------------
from kenning.twitch.welcome import WelcomedStore


def test_store_roundtrip(tmp_path):
    s = WelcomedStore(tmp_path / "welcomed.db")
    assert s.seen("bob") is False
    s.mark("bob")
    assert s.seen("bob") is True
    assert s.seen("BOB ") is True          # canonicalized like the welcomer
    assert s.seen("alice") is False
    assert len(s) == 1
    s.mark("bob")                          # idempotent
    assert len(s) == 1


def test_store_survives_reopen(tmp_path):
    p = tmp_path / "welcomed.db"
    WelcomedStore(p).mark("bob")
    assert WelcomedStore(p).seen("bob") is True


def test_store_invalid_input_and_bad_path():
    s = WelcomedStore("Z:/definitely/not/writable\0/x.db")   # NUL -> init fails
    s.mark("bob")                          # no raise
    assert s.seen("bob") is False          # fail-open toward welcoming
    s2 = WelcomedStore.__new__(WelcomedStore)
    s2._conn = None
    s2._lock = __import__("threading").Lock()
    assert s2.seen(None) is False          # type: ignore[arg-type]
    s2.mark("")                            # blank ignored, no raise


def test_restart_does_not_rewelcome(tmp_path):
    """The user's exact complaint: a reboot must not re-greet known chatters."""
    store = WelcomedStore(tmp_path / "welcomed.db")
    w1 = _mk(store=store)
    assert w1.observe("bob", display_name="Bob") is not None
    # --- simulate a restart: a FRESH welcomer (empty per-run set), same store
    w2 = _mk(store=WelcomedStore(tmp_path / "welcomed.db"))
    assert w2.observe("bob", display_name="Bob") is None, "rebooted -> no re-welcome"
    assert w2.observe("newbie") is not None, "genuinely new login still welcomed"


def test_burst_overflow_not_durably_marked(tmp_path):
    """An overflow suppression is per-run only — the chatter can still be
    welcomed on a later stream."""
    p = tmp_path / "welcomed.db"
    clock = {"t": 0.0}
    w1 = _mk(store=WelcomedStore(p), max_per_minute=1, now_fn=lambda: clock["t"])
    assert w1.observe("a") is not None       # consumes the budget; durably marked
    assert w1.observe("b") is None           # overflow: per-run only
    w2 = _mk(store=WelcomedStore(p))         # next stream
    assert w2.observe("a") is None           # durably welcomed
    assert w2.observe("b") is not None       # gets the welcome this time


def test_excluded_never_durably_marked(tmp_path):
    p = tmp_path / "welcomed.db"
    w1 = _mk(store=WelcomedStore(p), exclude_logins={"ultron_kenning"})
    assert w1.observe("ultron_kenning") is None
    assert WelcomedStore(p).seen("ultron_kenning") is False


def test_store_error_degrades_to_per_run():
    class Boom:
        def seen(self, _l):
            raise RuntimeError("db locked")

        def mark(self, _l):
            raise RuntimeError("db locked")

    w = _mk(store=Boom())
    assert w.observe("bob") is not None      # still welcomes (per-run contract)
    assert w.observe("bob") is None          # per-run dedup still holds


def test_no_store_is_legacy_per_run_behaviour():
    w = _mk(store=None)
    assert w.observe("bob") is not None
    assert w.observe("bob") is None


def test_config_persist_defaults():
    from kenning.config import TwitchChatConfig
    cfg = TwitchChatConfig()
    assert cfg.first_time_welcome_persist is True
    assert cfg.first_time_welcome_persist_path == "data/twitch/welcomed.db"


# ---------------------------------------------------------------------------
# Ban guard (2026-07-10) — clear_user_messages suppression of delayed welcomes
# ---------------------------------------------------------------------------

def test_mark_banned_and_is_banned():
    w = _mk()
    assert w.is_banned("adbot") is False
    w.mark_banned("AdBot ")                    # canonicalized
    assert w.is_banned("adbot") is True
    assert w.is_banned("ADBOT") is True
    w.mark_banned("")                          # blank ignored, no raise
    w.mark_banned(None)                        # type: ignore[arg-type]
    assert w.is_banned("") is False


def test_config_welcome_delay_default():
    from kenning.config import TwitchChatConfig
    assert TwitchChatConfig().first_time_welcome_delay_seconds == 4
