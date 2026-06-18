"""faster-whisper wrapper.

Loads the model once at construction (not lazily on first transcribe), so the
hot path is just GPU inference. Audio is expected as mono float32 at 16 kHz —
the rest of the pipeline already standardizes on that, so no resampling here.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import numpy as np

from config import settings
from kenning.errors import WhisperTranscriptionError
from kenning.resilience import get_error_log
from kenning.utils.logging import get_logger

logger = get_logger("transcription.whisper")

# Closed Valorant vocabulary fed to the decoder as initial_prompt (domain
# biasing) so agent names + callout terms are recognised at the source. <=200
# tokens; most-confusable proper nouns first. WHISPER_INITIAL_PROMPT is APPENDED
# to this (it no longer SHADOWS it -- see the build site below).
#
# 2026-06-18: every capture begins with the wake-word PRE-ROLL, so the prompt
# LEADS with "Ultron." -- this primes the decoder to render the clipped "...tron"
# tail as a strippable "Ultron"/"Tron" (caught by the normalizer's wake-remnant
# pass) instead of hallucinating it into phantom leading words (Franz / Prong /
# One / We're on) that contaminate the callout. Map LOCATIONS are included so
# spot calls ("tree", "plat") aren't misheard as numbers ("3") or filler.
_DOMAIN_PROMPT = (
    "Ultron. Valorant team comms. Agents: Raze, Jett, Sova, Omen, Killjoy, Cypher, Viper, "
    "Phoenix, Sage, Reyna, Breach, Fade, Skye, Astra, Harbor, Clove, Chamber, "
    "Brimstone, Gekko, Yoru, Iso, Deadlock, Tejo, Waylay, Vyse, Neon, KAY/O. "
    "Calls: spike, plant, defuse, ult, smoke, flash, molly, dart, rotate, eco, "
    "save, push, heaven, mid, long, short, A site, B site, C site, lurk, flank. "
    "Spots: tree, plat, platform, hell, default, elbow, garage, market, generator, "
    "back site, A main, B main, rafters, ramp, pit, link, window, lane, tube."
)

# faster-whisper emits stock phrases ("Thank you.", "Thanks for watching",
# "you", ".") on near-silence / room tone / non-speech audio. On the gaming
# relay path a false transcript would fire a bogus team callout or a
# conversational turn, so when the WHOLE transcript normalises to one of these
# it is dropped. Kept deliberately NARROW -- only phrases that are never a
# meaningful standalone command (real commands like "you're welcome" untouched).
_WHISPER_HALLUCINATIONS = frozenset({
    "thank you", "thanks", "thank you so much", "thank you very much",
    "thanks for watching", "thank you for watching", "thanks for watching everyone",
    "please subscribe", "subscribe", "thanks for listening", "you", "bye",
    "bye bye", "the", "music", "applause", "silence", "background noise",
    "i'm sorry", "oh", "hmm", "mm", "mmm", "uh", "um", "ah",
})


def _is_whisper_hallucination(text: str) -> bool:
    """True when ``text`` is, in whole, a known faster-whisper non-speech
    artifact (case/punctuation-insensitive)."""
    norm = re.sub(r"[^\w\s']", " ", text.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm in _WHISPER_HALLUCINATIONS


def _preprocess_utterance(audio: np.ndarray, *, target_dbfs: float = -24.0) -> np.ndarray:
    """Zero-latency in-process front-end on the already-captured utterance.

    Three guarded steps (each fails open to the input -- this never drops a clip):
      1. DC-offset removal (``x -= x.mean()``) -- makes the RMS/peak estimates
         exact; cannot blow up on a non-empty buffer.
      2. Per-utterance RMS loudness normalization toward ``target_dbfs`` with a
         finite-check and a HARD max-gain clamp (+24 dB). Whisper's log-mel is
         NOT scale-invariant -- too-quiet input drives the "Thank you." stock-
         phrase hallucination and inflates WER -- so leveling each utterance to a
         consistent loudness is a real robustness win (sized as variance
         reduction, not a precise mean-WER delta). MUST run AFTER the caller's
         raw-peak silence gate so pure room tone is never amplified.
      3. Soft-limit: a smooth tanh knee only when a sample is pushed hot (>0.95),
         which beats hard clipping (clipping injects broadband harmonics that
         smear the mel); finite for all finite inputs. A final clip is the
         backstop. Rarely fires at a -24 dBFS target (peaks land ~0.25-0.5).
    """
    try:
        x = audio if audio.dtype == np.float32 else audio.astype(np.float32)
        if x.size == 0:
            return x
        try:
            x = x - np.float32(x.mean())                       # 1) DC removal
        except Exception:                                     # noqa: BLE001
            pass
        try:                                                  # 2) RMS normalize
            rms = float(np.sqrt(np.mean(x * x)))
            if np.isfinite(rms) and rms > 1e-6:
                target_lin = float(10.0 ** (target_dbfs / 20.0))
                gain = min(target_lin / rms, 16.0)            # +24 dB hard clamp
                if np.isfinite(gain) and gain > 0:
                    x = (x * np.float32(gain)).astype(np.float32)
        except Exception:                                     # noqa: BLE001
            pass
        try:                                                  # 3) soft-limit
            if x.size and float(np.max(np.abs(x))) > 0.95:
                x = np.tanh(x).astype(np.float32)
            np.clip(x, -1.0, 1.0, out=x)
        except Exception:                                     # noqa: BLE001
            pass
        return x.astype(np.float32, copy=False)
    except Exception:                                         # noqa: BLE001
        return audio


class WhisperEngine:
    """Speech-to-text via faster-whisper on CUDA.

    Args:
        model_name: e.g. ``small.en``, ``base.en``, ``medium.en``.
        device: ``cuda`` or ``cpu``.
        compute_type: ``float16``, ``int8_float16``, ``int8``, ``float32``.
        beam_size: 1 for greedy decoding (fastest), >1 for beam search.
    """

    def __init__(
        self,
        model_name: str = settings.WHISPER_MODEL,
        device: str = settings.WHISPER_DEVICE,
        compute_type: str = settings.WHISPER_COMPUTE_TYPE,
        beam_size: int = settings.WHISPER_BEAM_SIZE,
    ) -> None:
        from faster_whisper import WhisperModel

        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size

        logger.info(
            "Loading Whisper '%s' on %s (%s)…",
            model_name,
            device,
            compute_type,
        )
        t0 = time.monotonic()
        try:
            self._model = WhisperModel(
                model_name, device=device, compute_type=compute_type
            )
        except Exception as e:
            logger.error("Whisper load failed: %s", e)
            raise
        logger.info("Whisper ready in %.2fs", time.monotonic() - t0)

    def __enter__(self) -> "WhisperEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # faster-whisper has no explicit close; let GC reclaim CUDA memory.
        self._model = None

    def transcribe(self, audio: np.ndarray, language: Optional[str] = "en") -> str:
        """Transcribe an audio segment to text.

        Args:
            audio: mono float32 at 16 kHz.
            language: ISO code, or ``None`` to autodetect (slower).

        Returns:
            Stripped transcription text. May be empty for silence.
            On Whisper failure, returns ``""`` and logs to errors.jsonl;
            the orchestrator's repeated-failure counter takes over from
            there ("Speech recognition is having trouble." after 3+).
        """
        if audio.size == 0:
            return ""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        # Silence gate: skip the GPU call on near-silent buffers. faster-whisper
        # hallucinates stock phrases ("Thank you.") on silence / faint room
        # tone; a real callout peaks far above this floor. Cheap insurance that
        # also saves an inference when upstream VAD lets a quiet buffer through.
        if float(np.max(np.abs(audio))) < 0.008:
            return ""
        # 2026-06-18 zero-latency front-end: DC removal -> RMS loudness normalize
        # -> soft-limit. Runs AFTER the raw-peak gate above (so pure noise is never
        # amplified) and BEFORE the GPU decode. Fail-open to the raw audio. Default
        # ON; gated by stt preprocessing flag so it can be A/B'd.
        if getattr(settings, "WHISPER_PREPROCESSING", True):
            audio = _preprocess_utterance(
                audio,
                target_dbfs=getattr(settings, "WHISPER_RMS_TARGET_DBFS", -24.0),
            )

        t0 = time.monotonic()
        try:
            # Decode-time DOMAIN BIASING: prime the decoder with the Valorant
            # closed vocabulary so proper nouns (agent names) and callout terms
            # are recognised at the SOURCE -- fewer downstream corrections needed.
            # Additive + reversible: gated by WHISPER_DOMAIN_BIAS (default on);
            # initial_prompt is supported by every faster-whisper version. Reset
            # per turn (condition_on_previous_text stays off for command STT).
            # 2026-06-18 mic-accuracy: re-arm the temperature FALLBACK tuple (a
            # scalar 0.0 disabled Whisper's canonical repetition/hallucination
            # retry) and pass the confidence gates (compression_ratio / log_prob /
            # no_speech) that improve PRECISION on the relay path -- all were set in
            # .env but never reached transcribe() before. suppress_blank +
            # without_timestamps constrain the output toward the command grammar.
            _temp_fallback = getattr(settings, "WHISPER_TEMPERATURE_FALLBACK", True)
            _kw = dict(
                language=language,
                beam_size=self.beam_size,
                temperature=((0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
                             if _temp_fallback else settings.WHISPER_TEMPERATURE),
                condition_on_previous_text=settings.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
                vad_filter=settings.WHISPER_VAD_FILTER,
                compression_ratio_threshold=getattr(
                    settings, "WHISPER_COMPRESSION_RATIO_THRESHOLD", 2.4),
                log_prob_threshold=getattr(
                    settings, "WHISPER_LOG_PROB_THRESHOLD", -1.0),
                no_speech_threshold=getattr(
                    settings, "WHISPER_NO_SPEECH_THRESHOLD", 0.6),
                suppress_blank=True,
                without_timestamps=True,
                prompt_reset_on_temperature=0.5,
            )
            if getattr(settings, "WHISPER_DOMAIN_BIAS", True):
                # 2026-06-18: COMBINE, never SHADOW. The .env carried a stale
                # WHISPER_INITIAL_PROMPT='Kenning.' (the OLD wake word) which,
                # via the previous `or`, replaced the whole Valorant domain prompt
                # -> domain biasing was effectively OFF (Sova->Silva, tree->3,
                # wake tail -> phantom words). Now the domain prompt is always used
                # and a *meaningful* custom prompt is appended; the obsolete
                # 'Kenning' value is ignored so it can never disable biasing again.
                _extra = (getattr(settings, "WHISPER_INITIAL_PROMPT", "") or "").strip()
                if _extra.lower().rstrip(". ") in ("", "kenning"):
                    _extra = ""
                _kw["initial_prompt"] = (
                    _DOMAIN_PROMPT + (" " + _extra if _extra else "")).strip()
                # One-time confirmation (after the first callout) that domain
                # biasing is LIVE with the wake prime -- proves the shadow fix.
                if not getattr(self, "_logged_domain_prompt", False):
                    self._logged_domain_prompt = True
                    logger.info(
                        "Whisper domain biasing ACTIVE: initial_prompt primes "
                        "wake word + Valorant vocab (%d chars)",
                        len(_kw["initial_prompt"]))
            # Drop any kwarg the installed faster-whisper doesn't accept, so a newer
            # knob can't TypeError and (via the except below) silently break ALL
            # transcription on an older library.
            try:
                import inspect as _inspect
                _supported = set(
                    _inspect.signature(self._model.transcribe).parameters)
                _kw = {k: v for k, v in _kw.items() if k in _supported}
            except Exception:                                     # noqa: BLE001
                pass
            segments, info = self._model.transcribe(audio, **_kw)
            kept = []
            for seg in segments:
                # Drop segments the model is highly confident are non-speech.
                if getattr(seg, "no_speech_prob", 0.0) > 0.85:
                    continue
                piece = (seg.text or "").strip()
                if piece:
                    kept.append(piece)
            text = " ".join(kept).strip()
            # Final guard: a whole-transcript stock phrase is a hallucination.
            if text and _is_whisper_hallucination(text):
                logger.debug("whisper: dropped non-speech hallucination %r", text)
                text = ""
        except Exception as e:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "Whisper transcribe failed in %.0fms: %s", elapsed_ms, e,
            )
            get_error_log().record(
                WhisperTranscriptionError(
                    f"transcribe failed: {e}",
                    context={
                        "audio_seconds": len(audio) / settings.SAMPLE_RATE,
                        "model": self.model_name,
                        "device": self.device,
                    },
                    recovery="returned empty transcription; orchestrator skips this turn",
                ),
                dependency="whisper",
            )
            return ""
        elapsed_ms = (time.monotonic() - t0) * 1000
        audio_seconds = len(audio) / settings.SAMPLE_RATE
        logger.info(
            "Whisper: %.2fs audio → %d chars in %.0fms (RTF=%.2f, lang=%s)",
            audio_seconds,
            len(text),
            elapsed_ms,
            elapsed_ms / 1000 / max(audio_seconds, 1e-6),
            info.language,
        )
        return text
