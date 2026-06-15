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

        t0 = time.monotonic()
        try:
            segments, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=self.beam_size,
                temperature=settings.WHISPER_TEMPERATURE,
                condition_on_previous_text=settings.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
                vad_filter=settings.WHISPER_VAD_FILTER,
            )
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
