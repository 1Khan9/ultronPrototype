"""In-model F0-contour shaping for Kokoro / StyleTTS2 -- expressiveness with
ZERO added latency and perfect timbre + reverb preservation.

Kokoro's ``KModel.forward_with_tokens`` predicts an explicit pitch curve
``F0_pred`` and feeds it straight to the ISTFTNet decoder::

    F0_pred, N_pred = self.predictor.F0Ntrain(en, s)
    audio = self.decoder(asr, F0_pred, N_pred, ref_s[:, :128])

We wrap ``predictor.F0Ntrain`` to EXPAND that curve's variation around its
median (and optionally deepen it) BEFORE the decoder runs. The decoder then
renders the voice's timbre and baked-in reverb with a richer, less-monotone
pitch -- in the SAME forward pass, so:

- the reverb tail and mechanical timbre are preserved exactly (the decoder
  produces them; we only changed the pitch it renders), unlike post-hoc PSOLA
  which replaced the reverb with a flat noise floor;
- there is no second resynthesis, so latency is unchanged (a single tensor op);
- the predicted F0 is neural-clean -- no octave-error spikes or estimation
  jitter -- so expansion needs no de-spike/de-shake and cannot produce the
  single-word spikes or warble that acoustic-domain pitch editing did.

The hook reads its parameters live off the engine instance, so they hot-swap.
Fail-open: a missing model / shape surprise leaves synthesis untouched.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def scale_f0_curve(f0, *, factor: float, shift_semitones: float,
                   max_excursion_semitones: float):
    """Expand a predicted F0 curve around its median (log domain), soft-limited.

    Args:
        f0: torch float tensor of F0 in Hz (Kokoro's ``F0_pred``); unvoiced
            frames are ~0 and are left untouched.
        factor: contour expansion. 1.0 = identity.
        shift_semitones: median shift (negative = deeper).
        max_excursion_semitones: tanh soft-limit on distance from the median.

    Returns:
        A new tensor; on any anomaly returns the input unchanged.
    """
    try:
        import torch

        if factor == 1.0 and shift_semitones == 0.0:
            return f0  # true no-op (the soft-limit would otherwise compress)
        out = f0.clone()
        pos = out > 1.0
        n = int(pos.sum())
        if n < 4:
            return out
        logf = torch.log2(out[pos])
        med = torch.median(logf)
        dev_semi = (logf - med) * 12.0
        m = float(max_excursion_semitones)
        shaped = m * torch.tanh(dev_semi * float(factor) / m)
        out[pos] = torch.pow(
            2.0, med + (float(shift_semitones) + shaped) / 12.0)
        return out
    except Exception as e:  # noqa: BLE001 - never break synthesis
        logger.warning("F0 curve scaling failed (passing through): %s", e)
        return f0


def scale_energy_curve(n, *, factor: float):
    """Mean-preserving expansion of the predicted energy curve ``N_pred``.

    Widens loud-vs-quiet dynamics (natural emphasis) without changing overall
    loudness. Gentle (~1.1-1.3); 1.0 = identity. Fail-open.
    """
    try:
        import torch

        if factor == 1.0:
            return n
        m = n.mean()
        return m + (n - m) * float(factor)
    except Exception as e:  # noqa: BLE001
        logger.warning("energy curve scaling failed (passing through): %s", e)
        return n


def install_f0_contour_shaping(engine) -> bool:
    """Patch ``engine``'s Kokoro model so synthesis applies the live F0 shaping
    read from ``engine.f0_contour_factor`` / ``f0_shift_semitones`` /
    ``f0_max_excursion``. Idempotent. Returns True if the hook is in place.

    The engine is expected to expose the KPipeline at ``_model`` with a
    ``.model`` KModel (the standard ``kokoro`` package layout). Any deviation
    is logged and leaves synthesis unchanged.
    """
    try:
        kp = getattr(engine, "_model", None)
        km = getattr(kp, "model", None) or getattr(kp, "_model", None)
        if km is None or not hasattr(km, "predictor"):
            logger.debug("F0 shaping: no KModel.predictor; skipping")
            return False
        pred = km.predictor
        if not hasattr(pred, "F0Ntrain"):
            logger.debug("F0 shaping: predictor has no F0Ntrain; skipping")
            return False
        if getattr(pred, "_f0shape_orig", None) is None:
            pred._f0shape_orig = pred.F0Ntrain
        orig = pred._f0shape_orig

        def _hook(en, s):
            f0, npred = orig(en, s)
            factor = float(getattr(engine, "f0_contour_factor", 1.0) or 1.0)
            shift = float(getattr(engine, "f0_shift_semitones", 0.0) or 0.0)
            m = float(getattr(engine, "f0_max_excursion", 5.0) or 5.0)
            efac = float(getattr(engine, "f0_energy_factor", 1.0) or 1.0)
            if factor != 1.0 or shift != 0.0:
                f0 = scale_f0_curve(f0, factor=factor, shift_semitones=shift,
                                    max_excursion_semitones=m)
            if efac != 1.0:
                npred = scale_energy_curve(npred, factor=efac)
            return f0, npred

        pred.F0Ntrain = _hook
        logger.info("Kokoro in-model F0 contour shaping installed")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("could not install F0 contour shaping: %s", e)
        return False
