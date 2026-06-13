"""Tests for in-model per-phoneme duration shaping (cadence)."""
from __future__ import annotations

from kenning.tts.duration_control import compute_pace_vec

# Phoneme strings are wrapped in marker spaces, mirroring Kokoro's [0, ..., 0].
# 'sˈIt.' = s | ˈ(stress) | I(vowel /aI/) | t(coda) | .(sentence end)


def _wrap(ph):
    return list(" " + ph + " ")


def test_sentence_final_lengthens_rime():
    chars = _wrap("sˈIt.")  # ' ',s,ˈ,I,t,.,' '
    pv = compute_pace_vec(chars, final_factor=1.3, internal_factor=1.18,
                          stress_factor=1.0)
    i_vowel = chars.index("I")
    coda = i_vowel + 1
    assert pv[i_vowel] > 1.25            # vowel gets full final lengthening
    assert 1.10 < pv[coda] < pv[i_vowel] + 0.01  # coda half as much


def test_internal_comma_lengthens_less_than_final():
    final = compute_pace_vec(_wrap("sˈIt."), final_factor=1.3,
                             internal_factor=1.18, stress_factor=1.0)
    internal = compute_pace_vec(_wrap("sˈIt,"), final_factor=1.3,
                                internal_factor=1.18, stress_factor=1.0)
    iv = _wrap("sˈIt.").index("I")
    assert internal[iv] < final[iv]      # comma < period


def test_stress_lifts_vowel():
    chars = _wrap("sˈIt")  # no punctuation
    pv = compute_pace_vec(chars, final_factor=1.3, internal_factor=1.18,
                          stress_factor=1.12)
    assert pv[chars.index("I")] >= 1.12 - 1e-6


def test_markers_untouched():
    chars = _wrap("sˈIt.")
    pv = compute_pace_vec(chars, final_factor=1.4, internal_factor=1.2,
                          stress_factor=1.1)
    assert pv[0] == 1.0 and pv[-1] == 1.0


def test_combined_stress_and_final_is_clamped():
    # a vowel that is BOTH stressed and sentence-final must not compound past cap
    chars = _wrap("ˈI.")
    pv = compute_pace_vec(chars, final_factor=1.4, internal_factor=1.2,
                          stress_factor=1.3)
    assert max(pv) <= 1.45 + 1e-9


def test_all_factors_one_is_flat():
    pv = compute_pace_vec(_wrap("sˈIt."), final_factor=1.0, internal_factor=1.0,
                          stress_factor=1.0)
    assert all(abs(p - 1.0) < 1e-9 for p in pv)
