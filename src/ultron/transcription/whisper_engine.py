"""faster-whisper wrapper.

Loads the model once at construction (not lazily on first transcribe), so the
hot path is just GPU inference. Audio is expected as mono float32 at 16 kHz —
the rest of the pipeline already standardizes on that, so no resampling here.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("transcription.whisper")


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
        """
        if audio.size == 0:
            return ""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        t0 = time.monotonic()
        segments, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=self.beam_size,
            temperature=settings.WHISPER_TEMPERATURE,
            condition_on_previous_text=settings.WHISPER_CONDITION_ON_PREVIOUS_TEXT,
            vad_filter=settings.WHISPER_VAD_FILTER,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
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
