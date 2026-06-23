"""Tests for BusyEstimator — signals, hush, is_busy combinations."""
from __future__ import annotations

import math
import time

import pytest

from kenning.twitch.busy import BusyEstimator


def _make(vad=False, ptt=False, age=math.inf, **kw):
    """Helper: build a BusyEstimator with fixed signal values."""
    return BusyEstimator(
        vad_fn=lambda: vad,
        ptt_fn=lambda: ptt,
        callout_age_fn=lambda: age,
        **kw,
    )


# --- construction / validation -----------------------------------------------

def test_construction_defaults():
    est = _make()
    assert est.callout_busy_window_s == 8.0
    assert est.hush_s == 30.0


def test_construction_custom_windows():
    est = _make(callout_busy_window_s=5.0, hush_s=10.0)
    assert est.callout_busy_window_s == 5.0
    assert est.hush_s == 10.0


def test_construction_rejects_noncallable():
    with pytest.raises(TypeError):
        BusyEstimator("not_callable", lambda: False, lambda: math.inf)
    with pytest.raises(TypeError):
        BusyEstimator(lambda: False, "not_callable", lambda: math.inf)
    with pytest.raises(TypeError):
        BusyEstimator(lambda: False, lambda: False, "not_callable")


def test_construction_rejects_bad_window():
    with pytest.raises(ValueError):
        BusyEstimator(lambda: False, lambda: False, lambda: math.inf, callout_busy_window_s=0)
    with pytest.raises(ValueError):
        BusyEstimator(lambda: False, lambda: False, lambda: math.inf, callout_busy_window_s=-1)


def test_construction_rejects_bad_hush_s():
    with pytest.raises(ValueError):
        BusyEstimator(lambda: False, lambda: False, lambda: math.inf, hush_s=0)


# --- is_busy signal logic -----------------------------------------------------

def test_not_busy_when_all_signals_idle():
    est = _make(vad=False, ptt=False, age=math.inf)
    assert est.is_busy() is False


def test_busy_on_vad():
    est = _make(vad=True, ptt=False, age=math.inf)
    assert est.is_busy() is True


def test_busy_on_ptt():
    est = _make(vad=False, ptt=True, age=math.inf)
    assert est.is_busy() is True


def test_busy_on_recent_callout():
    est = _make(vad=False, ptt=False, age=3.0, callout_busy_window_s=8.0)
    assert est.is_busy() is True


def test_not_busy_on_old_callout():
    est = _make(vad=False, ptt=False, age=10.0, callout_busy_window_s=8.0)
    assert est.is_busy() is False


def test_busy_on_callout_at_exact_boundary():
    # age < window -> busy; age == window -> NOT busy
    est = _make(vad=False, ptt=False, age=8.0, callout_busy_window_s=8.0)
    assert est.is_busy() is False


def test_busy_on_callout_just_inside_boundary():
    est = _make(vad=False, ptt=False, age=7.999, callout_busy_window_s=8.0)
    assert est.is_busy() is True


# --- hush (manual override) --------------------------------------------------

def test_hush_sets_busy():
    est = _make()
    assert est.is_busy() is False
    est.hush(seconds=60.0)
    assert est.is_busy() is True


def test_hush_uses_default_hush_s_when_none():
    est = _make(hush_s=60.0)
    est.hush()
    assert est.is_busy() is True


def test_clear_hush_cancels_override():
    est = _make()
    est.hush(seconds=60.0)
    assert est.is_busy() is True
    est.clear_hush()
    assert est.is_busy() is False


def test_hush_extends_deadline_if_already_hushed():
    est = _make()
    est.hush(seconds=10.0)
    # Hushing again with a longer duration should extend, not shorten.
    est.hush(seconds=120.0)
    # Still busy (the longer hush won).
    assert est.is_busy() is True


def test_hush_rejects_zero_or_negative():
    est = _make()
    with pytest.raises(ValueError):
        est.hush(seconds=0)
    with pytest.raises(ValueError):
        est.hush(seconds=-5)


def test_hush_expires_naturally(monkeypatch):
    """Simulate time passing past the hush deadline."""
    now = [time.monotonic()]
    monkeypatch.setattr("kenning.twitch.busy.time.monotonic", lambda: now[0])

    est = _make()
    est.hush(seconds=5.0)
    assert est.is_busy() is True

    # Advance clock past the deadline.
    now[0] += 6.0
    assert est.is_busy() is False


# --- signal errors are tolerated (not-busy default) --------------------------

def test_vad_fn_error_treated_as_not_active():
    def bad_vad():
        raise RuntimeError("sensor offline")

    est = BusyEstimator(bad_vad, lambda: False, lambda: math.inf)
    # Should not raise; should be not-busy (error -> not-active).
    assert est.is_busy() is False


def test_ptt_fn_error_treated_as_not_active():
    def bad_ptt():
        raise OSError("key unavailable")

    est = BusyEstimator(lambda: False, bad_ptt, lambda: math.inf)
    assert est.is_busy() is False


def test_callout_age_fn_error_treated_as_quiet():
    def bad_age():
        raise ValueError("no callout data")

    est = BusyEstimator(lambda: False, lambda: False, bad_age)
    assert est.is_busy() is False


def test_callout_age_nan_treated_as_inf():
    est = BusyEstimator(lambda: False, lambda: False, lambda: float("nan"))
    assert est.is_busy() is False


# --- combined signals --------------------------------------------------------

def test_any_signal_true_means_busy():
    # vad alone
    assert _make(vad=True).is_busy() is True
    # ptt alone
    assert _make(ptt=True).is_busy() is True
    # recent callout alone
    assert _make(age=1.0).is_busy() is True


def test_all_signals_false_and_no_hush_is_not_busy():
    est = _make(vad=False, ptt=False, age=999.0)
    est.clear_hush()
    assert est.is_busy() is False
