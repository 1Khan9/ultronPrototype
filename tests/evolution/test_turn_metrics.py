"""Tests for the guardrail-brake instrumentation (#15 + #65).

Covers :mod:`kenning.evolution.turn_metrics`: the per-turn metrics ring
(recording, window bounding, monotonic totals, since-marker slicing),
the sampler's minimum-sample floors (a field without enough data stays
``None`` so its guardrail is skipped), and the fail-open ``nvidia-smi``
VRAM probe (subprocess mocked -- binding rule R4: no real subprocess).
All hermetic; no voice stack; no IO.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

import kenning.evolution.turn_metrics as tm
from kenning.evolution.guardrails import GuardrailSample
from kenning.evolution.turn_metrics import (
    TurnMetricsRing,
    build_guardrail_sampler,
    probe_vram_mb,
)


# ---------------------------------------------------------------------------
# TurnMetricsRing -- recording
# ---------------------------------------------------------------------------


class TestRingRecording:
    def test_starts_empty(self) -> None:
        ring = TurnMetricsRing()
        assert ring.totals() == (0, 0)
        sample = ring.sample()
        assert sample.ttft_ms is None
        assert sample.error_rate is None
        assert sample.correction_rate is None
        assert sample.turns_observed == 0

    def test_note_response_increments_totals(self) -> None:
        ring = TurnMetricsRing()
        ring.note_response(ttft_ms=100.0)
        ring.note_response(errored=True)
        assert ring.totals() == (2, 0)

    def test_note_quality_increments_totals(self) -> None:
        ring = TurnMetricsRing()
        ring.note_quality(corrected=True)
        ring.note_quality()
        assert ring.totals() == (0, 2)

    def test_window_bounds_records_but_not_totals(self) -> None:
        ring = TurnMetricsRing(window=5)
        for i in range(12):
            ring.note_response(ttft_ms=float(i))
        # Totals stay monotonic past the window.
        assert ring.totals() == (12, 0)
        # Only the newest 5 records are retained (median of 7..11 = 9).
        sample = ring.sample(min_latency_samples=1, min_rate_samples=1)
        assert sample.ttft_ms == 9.0
        assert sample.turns_observed == 5

    def test_invalid_ttft_values_recorded_as_none(self) -> None:
        ring = TurnMetricsRing()
        ring.note_response(ttft_ms=-5.0)
        ring.note_response(ttft_ms="garbage")  # type: ignore[arg-type]
        sample = ring.sample(min_latency_samples=1, min_rate_samples=1)
        assert sample.ttft_ms is None  # no valid observations
        assert sample.turns_observed == 2

    def test_window_floor_is_one(self) -> None:
        ring = TurnMetricsRing(window=0)
        ring.note_response(ttft_ms=50.0)
        ring.note_response(ttft_ms=70.0)
        sample = ring.sample(min_latency_samples=1, min_rate_samples=1)
        assert sample.turns_observed == 1  # window clamped to 1


# ---------------------------------------------------------------------------
# TurnMetricsRing -- sampling semantics
# ---------------------------------------------------------------------------


class TestRingSampling:
    def test_ttft_median_at_min_samples(self) -> None:
        ring = TurnMetricsRing()
        for v in (100.0, 200.0, 150.0, 120.0, 180.0):
            ring.note_response(ttft_ms=v)
        sample = ring.sample(min_latency_samples=5, min_rate_samples=1)
        assert sample.ttft_ms == 150.0

    def test_ttft_none_below_min_samples(self) -> None:
        ring = TurnMetricsRing()
        for v in (100.0, 200.0, 150.0, 120.0):
            ring.note_response(ttft_ms=v)
        sample = ring.sample(min_latency_samples=5, min_rate_samples=1)
        assert sample.ttft_ms is None

    def test_none_ttft_turns_excluded_from_median(self) -> None:
        ring = TurnMetricsRing()
        ring.note_response(ttft_ms=None)  # e.g. a search-augmented turn
        for v in (100.0, 110.0, 120.0):
            ring.note_response(ttft_ms=v)
        sample = ring.sample(min_latency_samples=3, min_rate_samples=1)
        assert sample.ttft_ms == 110.0
        assert sample.turns_observed == 4

    def test_error_rate_at_min_samples(self) -> None:
        ring = TurnMetricsRing()
        for i in range(10):
            ring.note_response(errored=(i < 2))
        sample = ring.sample(min_latency_samples=1, min_rate_samples=10)
        assert sample.error_rate == pytest.approx(0.2)

    def test_error_rate_none_below_min_samples(self) -> None:
        ring = TurnMetricsRing()
        for _ in range(9):
            ring.note_response()
        sample = ring.sample(min_latency_samples=1, min_rate_samples=10)
        assert sample.error_rate is None

    def test_correction_rate_counts_any_dissatisfied_flag(self) -> None:
        ring = TurnMetricsRing()
        ring.note_quality(corrected=True)
        ring.note_quality(re_asked=True)
        ring.note_quality(barged_in=True)
        ring.note_quality()
        sample = ring.sample(min_latency_samples=1, min_rate_samples=4)
        assert sample.correction_rate == pytest.approx(0.75)

    def test_correction_rate_none_below_min_samples(self) -> None:
        ring = TurnMetricsRing()
        ring.note_quality(corrected=True)
        sample = ring.sample(min_latency_samples=1, min_rate_samples=2)
        assert sample.correction_rate is None

    def test_vram_probe_wired_into_sample(self) -> None:
        ring = TurnMetricsRing()
        sample = ring.sample(vram_probe=lambda: 6400.0)
        assert sample.vram_peak_mb == 6400.0

    def test_vram_probe_failure_is_fail_open(self) -> None:
        def _boom() -> Optional[float]:
            raise RuntimeError("nvidia-smi exploded")

        ring = TurnMetricsRing()
        sample = ring.sample(vram_probe=_boom)
        assert sample.vram_peak_mb is None

    def test_since_markers_slice_only_new_records(self) -> None:
        ring = TurnMetricsRing()
        for v in (1000.0, 1000.0, 1000.0):
            ring.note_response(ttft_ms=v)
        ring.note_quality(corrected=True)
        markers = ring.totals()
        for v in (100.0, 110.0, 120.0):
            ring.note_response(ttft_ms=v)
        ring.note_quality()
        ring.note_quality()
        sample = ring.sample(min_latency_samples=3, min_rate_samples=2, since=markers)
        # Only the three post-marker responses are considered.
        assert sample.ttft_ms == 110.0
        assert sample.turns_observed == 3
        # Only the two post-marker quality records: zero dissatisfied.
        assert sample.correction_rate == pytest.approx(0.0)

    def test_since_markers_with_no_new_records(self) -> None:
        ring = TurnMetricsRing()
        ring.note_response(ttft_ms=100.0)
        markers = ring.totals()
        sample = ring.sample(min_latency_samples=1, min_rate_samples=1, since=markers)
        assert sample.ttft_ms is None
        assert sample.turns_observed == 0

    def test_since_markers_survive_window_eviction(self) -> None:
        ring = TurnMetricsRing(window=4)
        for _ in range(3):
            ring.note_response(ttft_ms=999.0)
        markers = ring.totals()
        for v in (10.0, 20.0, 30.0, 40.0, 50.0, 60.0):
            ring.note_response(ttft_ms=v)
        # 6 new records but the window only holds 4 -- the slice is bounded.
        sample = ring.sample(min_latency_samples=1, min_rate_samples=1, since=markers)
        assert sample.turns_observed == 4
        assert sample.ttft_ms == 45.0  # median of 30/40/50/60


# ---------------------------------------------------------------------------
# probe_vram_mb (subprocess mocked -- R4)
# ---------------------------------------------------------------------------


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


class TestProbeVram:
    def test_parses_first_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tm.subprocess, "run", lambda *a, **k: _FakeProc(0, "6254\n")
        )
        assert probe_vram_mb() == 6254.0

    def test_multi_gpu_uses_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tm.subprocess, "run", lambda *a, **k: _FakeProc(0, "1715\n300\n")
        )
        assert probe_vram_mb() == 1715.0

    def test_nonzero_returncode_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tm.subprocess, "run", lambda *a, **k: _FakeProc(9, ""))
        assert probe_vram_mb() is None

    def test_empty_output_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tm.subprocess, "run", lambda *a, **k: _FakeProc(0, "  \n"))
        assert probe_vram_mb() is None

    def test_exception_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*a: Any, **k: Any) -> Any:
            raise FileNotFoundError("nvidia-smi not on PATH")

        monkeypatch.setattr(tm.subprocess, "run", _boom)
        assert probe_vram_mb() is None

    def test_unparseable_output_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            tm.subprocess, "run", lambda *a, **k: _FakeProc(0, "N/A\n")
        )
        assert probe_vram_mb() is None


# ---------------------------------------------------------------------------
# build_guardrail_sampler
# ---------------------------------------------------------------------------


class TestBuildSampler:
    def test_sampler_returns_ring_sample(self) -> None:
        ring = TurnMetricsRing()
        for v in (100.0, 110.0, 120.0, 130.0, 140.0):
            ring.note_response(ttft_ms=v)
        sampler = build_guardrail_sampler(ring, vram_probe=None)
        sample = sampler()
        assert isinstance(sample, GuardrailSample)
        assert sample.ttft_ms == 120.0

    def test_sampler_fail_open_on_broken_ring(self) -> None:
        class _Broken:
            def sample(self, **kwargs: Any) -> GuardrailSample:
                raise RuntimeError("ring boom")

        sampler = build_guardrail_sampler(_Broken())  # type: ignore[arg-type]
        sample = sampler()
        assert sample.ttft_ms is None
        assert sample.turns_observed == 0

    def test_sampler_threads_min_sample_floors(self) -> None:
        ring = TurnMetricsRing()
        ring.note_response(ttft_ms=100.0)
        sampler = build_guardrail_sampler(
            ring, min_latency_samples=1, min_rate_samples=1, vram_probe=None
        )
        assert sampler().ttft_ms == 100.0
        strict = build_guardrail_sampler(
            ring, min_latency_samples=5, min_rate_samples=5, vram_probe=None
        )
        assert strict().ttft_ms is None
