"""GuardDownCanary — the loud-outage signal for a guard that crashes AFTER boot
(2026-07-09). Pins: grace before the first alert, speak-once-then-log-only
re-warn, recovery, and re-arm across a second outage. Clock is injected.
"""
from __future__ import annotations

from kenning.twitch.guard import GuardCanaryEvent, GuardDownCanary


def _healthy_then(c, t=0.0):
    """Mark the guard as having been healthy once (the post-boot 'crash later'
    regime), returning c for chaining."""
    assert c.observe(True, t) is None
    return c


def test_healthy_stream_never_alerts():
    c = GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90)
    assert all(c.observe(True, t) is None for t in range(0, 300, 10))


def test_grace_then_first_down_speaks():
    c = _healthy_then(GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90))
    assert c.observe(False, 1.0) is None        # outage begins, within grace
    assert c.observe(False, 20.0) is None       # still within grace
    ev = c.observe(False, 32.0)                 # past grace -> first alert
    assert ev == GuardCanaryEvent("down", speak=True)


def test_rewarn_is_log_only_and_throttled():
    c = _healthy_then(GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90))
    c.observe(False, 1.0)
    assert c.observe(False, 32.0) == GuardCanaryEvent("down", speak=True)
    # no re-warn before rewarn_s elapses
    assert c.observe(False, 60.0) is None
    assert c.observe(False, 120.0) is None
    # first re-warn once >= 32 + 90 = 122: log-only (speak False)
    assert c.observe(False, 123.0) == GuardCanaryEvent("down", speak=False)
    assert c.observe(False, 150.0) is None
    assert c.observe(False, 214.0) == GuardCanaryEvent("down", speak=False)


def test_recovery_after_outage_emits_recovered_once():
    c = _healthy_then(GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90))
    c.observe(False, 1.0)
    c.observe(False, 32.0)                       # down (warned)
    assert c.observe(True, 40.0) == GuardCanaryEvent("recovered", speak=True)
    assert c.observe(True, 50.0) is None         # stays quiet while healthy


def test_transient_blip_shorter_than_grace_never_alerts():
    c = _healthy_then(GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90))
    c.observe(False, 1.0)
    c.observe(False, 10.0)
    assert c.observe(True, 15.0) is None         # recovered before warning -> silent
    # and no lingering "recovered" since we never warned
    assert c.observe(True, 20.0) is None


def test_second_outage_rearms():
    c = _healthy_then(GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90))
    c.observe(False, 1.0)
    assert c.observe(False, 32.0) == GuardCanaryEvent("down", speak=True)
    assert c.observe(True, 40.0) == GuardCanaryEvent("recovered", speak=True)
    # a fresh outage later must speak again (re-armed)
    assert c.observe(False, 100.0) is None
    assert c.observe(False, 131.0) == GuardCanaryEvent("down", speak=True)


def test_unhealthy_since_resets_on_recovery():
    """A flap (down<grace, up, down again) must restart the grace clock so a
    brief blip never counts toward the next outage's threshold."""
    c = _healthy_then(GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90))
    c.observe(False, 1.0)
    c.observe(True, 10.0)                        # blip cleared, since-clock reset
    c.observe(False, 20.0)                       # new outage starts at t=20
    assert c.observe(False, 45.0) is None         # 25s in -> still within grace
    assert c.observe(False, 51.0) == GuardCanaryEvent("down", speak=True)  # 31s in


# --- boot window: a guard still LOADING (never healthy) uses the longer grace
def test_slow_boot_load_within_boot_grace_is_silent():
    """A cold guard that has NEVER been healthy must not be called dead during
    its GGUF load — the longer boot grace covers it, so no spurious 'restart me'."""
    c = GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90)
    # unhealthy from the first poll, still loading; below boot_grace -> silent
    assert c.observe(False, 0.0) is None
    assert c.observe(False, 30.0) is None        # would alert under the SHORT grace
    assert c.observe(False, 60.0) is None
    assert c.observe(False, 89.0) is None
    # once it finishes loading, no alert ever fired
    assert c.observe(True, 95.0) is None


def test_guard_that_never_comes_up_eventually_alerts():
    """A guard that never loads is NOT silent — it alerts after the boot grace
    (the one-shot boot canary is not the only signal)."""
    c = GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90)
    assert c.observe(False, 0.0) is None
    assert c.observe(False, 89.0) is None
    assert c.observe(False, 91.0) == GuardCanaryEvent("down", speak=True)


def test_first_ever_sample_unhealthy_then_healthy_switches_to_short_grace():
    c = GuardDownCanary(min_down_s=30, boot_grace_s=90, rewarn_s=90)
    c.observe(False, 0.0)                         # still loading
    c.observe(True, 40.0)                         # loaded -> ever_healthy
    c.observe(False, 50.0)                        # later crash
    assert c.observe(False, 79.0) is None          # 29s into crash -> within short grace
    assert c.observe(False, 81.0) == GuardCanaryEvent("down", speak=True)  # 31s in


def test_orchestrator_wires_the_guard_watch():
    """Pin the watcher wiring: _start_twitch_sidecars must spawn a guard-watch
    thread that feeds GuardDownCanary and logs the restart remedy."""
    import inspect

    from kenning.pipeline.orchestrator import Orchestrator

    src = inspect.getsource(Orchestrator._start_twitch_sidecars)
    assert "_twitch_guard_watch" in src
    assert "twitch-guard-watch" in src
    assert "GuardDownCanary" in src
    assert 'role == "twitch_guard"' in src
    assert "GUARD DOWN" in src            # the loud console remedy

