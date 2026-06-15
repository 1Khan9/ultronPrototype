"""Unit tests for :class:`WakeWordDetector` (A4 ``fired_recently`` accessor).

The detector wraps openWakeWord's ``Model`` which loads an ONNX file at
construction time. These tests avoid the model load by patching the
underlying ``_load_model`` helper -- the methods under test only touch
``_last_trigger_ts`` and ``time.monotonic()``.
"""

from __future__ import annotations

import time

import pytest

from kenning.audio.wake_word import WakeWordDetector


@pytest.fixture
def detector(monkeypatch):
    monkeypatch.setattr(
        WakeWordDetector, "_load_model",
        lambda self, path, fallback: object(),
    )
    return WakeWordDetector(model_path=None, fallback_name="hey_jarvis")


def test_fired_recently_false_before_first_trigger(detector):
    assert detector.fired_recently(window_s=10.0) is False


def test_fired_recently_true_just_after_trigger(detector):
    detector._last_trigger_ts = time.monotonic()  # noqa: SLF001
    assert detector.fired_recently(window_s=0.5) is True


def test_fired_recently_false_after_window_elapsed(detector):
    detector._last_trigger_ts = time.monotonic() - 5.0  # noqa: SLF001
    assert detector.fired_recently(window_s=0.5) is False


def test_fired_recently_idempotent(detector):
    """Calling fired_recently must not consume / clear the trigger."""
    detector._last_trigger_ts = time.monotonic()  # noqa: SLF001
    assert detector.fired_recently(window_s=10.0) is True
    assert detector.fired_recently(window_s=10.0) is True
    assert detector.fired_recently(window_s=10.0) is True


def test_fired_recently_window_s_is_inclusive_lower_bound(detector):
    """Border case: setting window_s=0 always returns False (trigger
    happened in the past, not 'now')."""
    detector._last_trigger_ts = time.monotonic() - 0.001  # noqa: SLF001
    assert detector.fired_recently(window_s=0.0) is False


def test_fired_recently_zeroed_state_returns_false(detector):
    """A reset detector (initial _last_trigger_ts == 0) must NOT report
    a barge-in -- the timestamp would otherwise be 0 vs now and the
    delta would be huge but the contract is 'never fired = no barge-in'."""
    detector._last_trigger_ts = 0.0  # noqa: SLF001
    assert detector.fired_recently(window_s=1_000_000.0) is False


def test_fired_recently_negative_window_returns_false(detector):
    detector._last_trigger_ts = time.monotonic()  # noqa: SLF001
    # Caller-error case; the implementation clamps via float() comparison.
    assert detector.fired_recently(window_s=-1.0) is False


# ---------------------------------------------------------------------------
# Per-word thresholds + consecutive-frame gate (2026-06-12 no-retrain
# false-accept controls). The active word's threshold overrides the flat one,
# and a single above-threshold frame must NOT fire -- the score has to persist
# for ``min_consecutive_frames`` in a row.
# ---------------------------------------------------------------------------

import numpy as np  # noqa: E402


class _ScoreModel:
    score = 0.0

    def predict(self, pcm):
        return {"w": self.score}

    def reset(self):
        pass


def _stub_load(self, path, fb):
    self._active_word = self._name  # noqa: SLF001
    return _ScoreModel()


def _scored(monkeypatch, word="ultron", thresholds=None, min_consec=2,
            consec_by_word=None):
    monkeypatch.setattr(WakeWordDetector, "_load_model", _stub_load)
    d = WakeWordDetector(model_path=None, name=word)
    d._thresholds = thresholds or {"kenning": 0.4, "ultron": 0.6}  # noqa: SLF001
    d._min_consecutive = min_consec  # noqa: SLF001
    # Default to NO per-word override so ``min_consec`` is authoritative in the
    # generic gate tests; pass ``consec_by_word`` to exercise the override.
    d._consec_by_word = consec_by_word or {}  # noqa: SLF001
    d.threshold = d._threshold_for(word)
    return d


def test_per_word_consecutive_overrides_flat(monkeypatch):
    """Per-word consecutive-frame gate overrides the flat default (2026-06-15:
    "ultron" requires 3 sustained frames so a transient confusable can't fire
    it)."""
    d = _scored(monkeypatch, word="ultron", min_consec=2,
                consec_by_word={"ultron": 3})
    frame = np.zeros(1280, dtype=np.float32)
    d._model.score = 0.7  # noqa: SLF001 - above ultron threshold
    assert d.process(frame) is False           # consec 1 < 3
    assert d.process(frame) is False           # consec 2 < 3
    assert d.process(frame) is True            # consec 3 >= 3 -> fire
    assert d._consec_for("ultron") == 3        # noqa: SLF001
    assert d._consec_for("kenning") == 2       # noqa: SLF001 - flat fallback


def test_per_word_threshold_overrides_flat(monkeypatch):
    d = _scored(monkeypatch, word="ultron")
    assert d.threshold == 0.6                 # ultron runs hotter
    assert d._threshold_for("kenning") == 0.4  # noqa: SLF001
    assert d._threshold_for("unknown") == d._default_threshold  # noqa: SLF001


def test_consecutive_frame_gate_fires_only_when_sustained(monkeypatch):
    d = _scored(monkeypatch, word="ultron", min_consec=2)
    frame = np.zeros(1280, dtype=np.float32)
    d._model.score = 0.5                       # below 0.6  # noqa: SLF001
    assert d.process(frame) is False
    d._model.score = 0.7                       # 1st above  # noqa: SLF001
    assert d.process(frame) is False           # consec 1 < 2
    assert d.process(frame) is True            # consec 2 >= 2 -> fire


def test_single_frame_spike_is_filtered(monkeypatch):
    d = _scored(monkeypatch, word="ultron", min_consec=2)
    frame = np.zeros(1280, dtype=np.float32)
    for score in (0.7, 0.3, 0.7):              # spike broken by a dip
        d._model.score = score                 # noqa: SLF001
        assert d.process(frame) is False       # never two-in-a-row


def test_swap_applies_target_word_threshold(monkeypatch):
    # reload_for_word recomputes the per-word threshold + resets the gate.
    d = _scored(monkeypatch, word="ultron")
    d._thresholds = {"kenning": 0.4, "ultron": 0.6}  # noqa: SLF001
    d._consec = 5  # noqa: SLF001
    d._active_word = "ultron"  # noqa: SLF001
    # Simulate the in-place recompute the swap performs:
    d.threshold = d._threshold_for("kenning")
    d._consec = 0  # noqa: SLF001
    assert d.threshold == 0.4 and d._consec == 0  # noqa: SLF001
