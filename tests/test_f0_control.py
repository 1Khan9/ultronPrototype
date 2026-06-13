"""Tests for in-model F0 / energy curve shaping (kenning.tts.f0_control)."""
from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from kenning.tts.f0_control import scale_energy_curve, scale_f0_curve


def test_f0_scaling_increases_variance_preserves_center():
    f0 = torch.tensor([90.0, 95.0, 100.0, 105.0, 110.0, 100.0, 95.0])
    out = scale_f0_curve(f0, factor=1.6, shift_semitones=0.0,
                         max_excursion_semitones=8.0)
    # center pitch preserved (no chipmunk shift)
    assert abs(float(out.median()) - float(f0.median())) < 1.0
    # variation expanded
    assert float(out.std()) > float(f0.std()) * 1.2


def test_f0_factor_one_is_identity():
    f0 = torch.tensor([95.0, 100.0, 105.0, 100.0])
    out = scale_f0_curve(f0, factor=1.0, shift_semitones=0.0,
                         max_excursion_semitones=8.0)
    assert torch.allclose(out, f0, atol=1e-2)


def test_f0_shift_deepens_median():
    f0 = torch.tensor([95.0, 100.0, 105.0, 100.0])
    out = scale_f0_curve(f0, factor=1.0, shift_semitones=-2.0,
                         max_excursion_semitones=8.0)
    ratio = float(out.median()) / float(f0.median())
    assert 0.86 < ratio < 0.91  # 2**(-2/12) = 0.891


def test_f0_leaves_unvoiced_frames_zero():
    f0 = torch.tensor([0.0, 0.0, 100.0, 105.0, 0.0])
    out = scale_f0_curve(f0, factor=1.6, shift_semitones=-1.0,
                         max_excursion_semitones=8.0)
    assert float(out[0]) == 0.0 and float(out[1]) == 0.0 and float(out[4]) == 0.0


def test_f0_soft_limit_caps_excursion():
    f0 = torch.tensor([50.0, 100.0, 200.0, 100.0])  # ±1 octave around 100
    out = scale_f0_curve(f0, factor=3.0, shift_semitones=0.0,
                         max_excursion_semitones=4.0)
    voiced = out[out > 1]
    semis = 12.0 * torch.log2(voiced / torch.median(voiced))
    assert float(semis.abs().max()) <= 4.0 + 0.6


def test_energy_scaling_is_mean_preserving():
    n = torch.tensor([0.5, 1.0, 1.5, 1.0, 0.5])
    out = scale_energy_curve(n, factor=1.4)
    assert abs(float(out.mean()) - float(n.mean())) < 1e-4   # loudness unchanged
    assert float(out.std()) > float(n.std())                # dynamics widened


def test_energy_factor_one_is_identity():
    n = torch.tensor([0.5, 1.0, 1.5])
    assert torch.allclose(scale_energy_curve(n, factor=1.0), n)
