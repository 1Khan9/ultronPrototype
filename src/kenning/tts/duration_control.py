"""In-model per-phoneme DURATION shaping for Kokoro / StyleTTS2 -- natural,
context-aware cadence at ZERO latency, reverb + timbre preserved.

Kokoro computes a per-phoneme integer frame vector ``pred_dur`` BEFORE building
the alignment (kokoro/model.py forward_with_tokens):

    duration = sigmoid(predictor.duration_proj(x)).sum(-1) / speed
    pred_dur = round(duration).clamp(min=1)

We multiply the pre-round ``duration`` by a per-phoneme ``pace_vec`` derived from
the phoneme string, so the decoder renders a NON-isochronous, human rhythm in
the SAME forward pass -- no resynthesis, no added latency, fully deterministic.

Two natural-speech behaviors (FastSpeech2/FastPitch-style duration control,
grounded in phonetics: duration is the strongest acoustic correlate of stress,
and phrase-final lengthening is the canonical de-roboticizer):

1. PHRASE/SENTENCE-FINAL LENGTHENING -- the final-syllable rime before every
   sentence (. ! ?) and phrase (, ; : --) boundary is lengthened (strongest on
   the vowel, half on the coda), more at sentence-final than phrase-internal.
2. STRESS EMPHASIS -- the primary-stressed vowel of a word gets a small lift.

All edits are clamped to a safe per-phoneme range (~0.85-1.45x) so a vowel is
never smeared and a phoneme is never deleted (clamp(min=1) downstream). This is
a DIFFERENT pipeline stage than the F0 contour shaping (pred_dur is
pre-alignment; F0_pred is post-alignment), and the two compose -- a lengthened
phoneme also gets more F0 frames, so a leaned-on word naturally carries more
pitch movement too. Fail-open: any error leaves synthesis untouched.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# misaki/Kokoro vowels: lowercase + IPA monophthongs + the uppercase diphthongs
# (A=eI, I=aI, O=oU, W=aU, Y=OI) + the reduced vowels (schwa, etc.).
_VOWELS = frozenset(
    "aeiouAIOWY" + "ɑɐɒæɔəɚɛɜɨɪɯøœʊʌɤᵻ")
_SENT_PUNCT = frozenset(".!?")
_PHRASE_PUNCT = frozenset(",;:—…")
_SPACE = frozenset(" ")
_PACE_MIN = 0.85
_PACE_MAX = 1.45


def _lengthen_rime(chars, pace, punct_i, factor):
    """Lengthen the final-syllable rime (last vowel + coda) before ``punct_i``."""
    j = punct_i - 1
    while j > 0 and chars[j] in _SPACE:
        j -= 1
    coda_end = j
    while j > 0 and chars[j] not in _VOWELS and chars[j] not in _SPACE:
        j -= 1
    if j > 0 and chars[j] in _VOWELS:
        pace[j] *= factor                       # vowel: full lengthening
        for p in range(j + 1, coda_end + 1):    # coda consonants: half
            pace[p] *= 1.0 + (factor - 1.0) * 0.5


def compute_pace_vec(chars, *, final_factor, internal_factor, stress_factor):
    """Per-phoneme pace multipliers for ``chars`` (incl. the two 0-marker ends).

    Index 0 and the last index are sentinel markers and are never touched.
    """
    n = len(chars)
    pace = [1.0] * n
    for i in range(1, n - 1):
        c = chars[i]
        if c in _SENT_PUNCT:
            _lengthen_rime(chars, pace, i, final_factor)
        elif c in _PHRASE_PUNCT:
            _lengthen_rime(chars, pace, i, internal_factor)
    if stress_factor != 1.0:
        for i in range(1, n - 1):
            if chars[i] == "ˈ":  # primary stress mark -> next vowel is stressed
                for j in range(i + 1, min(i + 4, n - 1)):
                    if chars[j] in _VOWELS:
                        pace[j] = max(pace[j], stress_factor)
                        break
    return [min(_PACE_MAX, max(_PACE_MIN, p)) for p in pace]


def install_duration_shaping(engine) -> bool:
    """Patch the engine's Kokoro model so synthesis applies the live per-phoneme
    pace read from ``engine.dur_final_factor`` / ``dur_internal_factor`` /
    ``dur_stress_factor`` (all default 1.0 = off). Idempotent. Returns True if
    the hook is installed.
    """
    try:
        import torch

        kp = getattr(engine, "_model", None)
        km = getattr(kp, "model", None) or getattr(kp, "_model", None)
        if km is None or not hasattr(km, "forward_with_tokens"):
            logger.debug("duration shaping: no KModel.forward_with_tokens")
            return False
        id2char = {v: k for k, v in km.vocab.items()}
        if getattr(km, "_dur_orig_fwt", None) is None:
            km._dur_orig_fwt = km.forward_with_tokens
        orig = km._dur_orig_fwt

        @torch.no_grad()
        def _patched(input_ids, ref_s, speed=1):
            ff = float(getattr(engine, "dur_final_factor", 1.0) or 1.0)
            inf = float(getattr(engine, "dur_internal_factor", 1.0) or 1.0)
            sf = float(getattr(engine, "dur_stress_factor", 1.0) or 1.0)
            if ff == 1.0 and inf == 1.0 and sf == 1.0:
                return orig(input_ids, ref_s, speed)
            # Vendored forward_with_tokens with pace_vec on the duration vector
            # (mirrors kokoro/model.py exactly except the marked insertion).
            input_lengths = torch.full(
                (input_ids.shape[0],), input_ids.shape[-1],
                device=input_ids.device, dtype=torch.long)
            tm = torch.arange(input_lengths.max()).unsqueeze(0).expand(
                input_lengths.shape[0], -1).type_as(input_lengths)
            text_mask = torch.gt(tm + 1, input_lengths.unsqueeze(1)).to(km.device)
            bert_dur = km.bert(input_ids, attention_mask=(~text_mask).int())
            d_en = km.bert_encoder(bert_dur).transpose(-1, -2)
            s = ref_s[:, 128:]
            d = km.predictor.text_encoder(d_en, s, input_lengths, text_mask)
            x, _ = km.predictor.lstm(d)
            duration = km.predictor.duration_proj(x)
            duration = torch.sigmoid(duration).sum(axis=-1) / speed
            # >>> per-phoneme cadence pace <<<
            chars = [id2char.get(int(i), "") for i in input_ids[0].tolist()]
            pace = compute_pace_vec(chars, final_factor=ff,
                                    internal_factor=inf, stress_factor=sf)
            pace_t = torch.tensor(pace, device=duration.device,
                                  dtype=duration.dtype)
            if pace_t.shape[-1] == duration.shape[-1]:
                duration = duration * pace_t
            # >>> end <<<
            pred_dur = torch.round(duration).clamp(min=1).long().squeeze()
            indices = torch.repeat_interleave(
                torch.arange(input_ids.shape[1], device=km.device), pred_dur)
            pred_aln_trg = torch.zeros(
                (input_ids.shape[1], indices.shape[0]), device=km.device)
            pred_aln_trg[indices, torch.arange(indices.shape[0])] = 1
            pred_aln_trg = pred_aln_trg.unsqueeze(0).to(km.device)
            en = d.transpose(-1, -2) @ pred_aln_trg
            F0_pred, N_pred = km.predictor.F0Ntrain(en, s)  # F0 hook composes here
            t_en = km.text_encoder(input_ids, input_lengths, text_mask)
            asr = t_en @ pred_aln_trg
            audio = km.decoder(asr, F0_pred, N_pred, ref_s[:, :128]).squeeze()
            return audio, pred_dur

        km.forward_with_tokens = _patched
        logger.info("Kokoro in-model duration shaping installed")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("could not install duration shaping: %s", e)
        return False
