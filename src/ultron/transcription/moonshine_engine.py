"""Moonshine ONNX STT engine (2026-05-22).

Drop-in replacement for :class:`WhisperEngine` -- same
``transcribe(audio: np.ndarray, language: Optional[str]) -> str``
interface, very different model underneath.

**Why Moonshine** (per user direction 2026-05-22): lowest perceived
latency + competitive accuracy with the smallest footprint of any
production-grade ASR. Streaming-native (no 30-second Whisper window),
purely ONNX runtime, no Keras/TF/PyTorch upgrade required.

Sizes (model_name parameter):
    moonshine/tiny    --  27 MB ONNX,  ~12.66% WER (averaged across
                          OpenASR-leaderboard datasets), fastest.
    moonshine/base    --  58 MB ONNX,  ~10.07% WER, recommended
                          default for English voice queries.

Inference path: CPU via ``onnxruntime``. The 4070 Ti's CUDA cores
stay free for the LLM + Kokoro warmup; Moonshine runs in ~5-15 ms
on CPU for short voice clips, which is FASTER than Whisper on GPU
for the same clips because Whisper's 30-second padding amortizes
poorly on short audio.

**Easy reversibility** (the "variable switch"):
- ``stt.engine: whisper``  -> Whisper (the long-standing default).
- ``stt.engine: parakeet`` -> Parakeet (NVIDIA TDT, ~5 GB VRAM).
- ``stt.engine: moonshine`` -> Moonshine ONNX (this engine).

The :func:`make_stt_engine` factory dispatches via these strings.
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np

from config import settings
from ultron.errors import WhisperTranscriptionError
from ultron.resilience import get_error_log
from ultron.utils.logging import get_logger

logger = get_logger("transcription.moonshine")


MOONSHINE_INSTALL_HINT = (
    "Moonshine requires the ``useful-moonshine-onnx`` package. Install with:\n"
    "    .venv/Scripts/pip install useful-moonshine-onnx\n"
    "It's ONNX-only -- no Keras / TF / PyTorch upgrade required.\n"
    "\n"
    "Or revert to Whisper with stt.engine: whisper in config.yaml."
)


# Moonshine's audio-length constraints (per moonshine_onnx.transcribe.py).
_MIN_AUDIO_SECONDS = 0.1
_MAX_AUDIO_SECONDS = 64.0


def is_moonshine_available() -> bool:
    """Return True iff the ``moonshine_onnx`` package can be imported."""
    try:
        import importlib.util
        return importlib.util.find_spec("moonshine_onnx") is not None
    except Exception:                                                  # noqa: BLE001
        return False


class MoonshineEngine:
    """Moonshine ONNX speech-to-text.

    Args:
        model_name: ``moonshine/tiny`` or ``moonshine/base``. Defaults
            to the value in ``stt.moonshine_model`` (``moonshine/base``
            unless overridden).
        device: kept for parity with the other engines; ignored
            because Moonshine ONNX runs on CPU. (A future CUDA EP
            could be added via ``onnxruntime-gpu``.)
        model_precision: ``"float"`` (default; fp32 weights) or
            ``"quantized"`` (int8 weights, smaller + slightly faster
            on supported CPUs at ~0.1-0.2 pp WER cost).

    Raises:
        ImportError: when ``moonshine_onnx`` is not installed.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        model_precision: Optional[str] = None,
    ) -> None:
        from ultron.config import get_config

        stt_cfg = get_config().stt

        self.model_name = model_name or getattr(
            stt_cfg, "moonshine_model", "moonshine/base",
        )
        # ``device`` is accepted for API parity with WhisperEngine /
        # ParakeetEngine but Moonshine ONNX is CPU-only. Log a hint
        # if the operator asked for cuda explicitly.
        self.device = device or getattr(stt_cfg, "moonshine_device", "cpu")
        if self.device.lower() != "cpu":
            logger.info(
                "Moonshine ONNX is CPU-only; ignoring device=%r and "
                "running on CPU.", self.device,
            )
        self.device = "cpu"
        self.model_precision = (
            model_precision
            or getattr(stt_cfg, "moonshine_precision", "float")
        )

        if not is_moonshine_available():
            raise ImportError(MOONSHINE_INSTALL_HINT)

        logger.info(
            "Loading Moonshine '%s' (precision=%s) on CPU...",
            self.model_name, self.model_precision,
        )
        t0 = time.monotonic()
        try:
            from moonshine_onnx import MoonshineOnnxModel
            from moonshine_onnx.transcribe import load_tokenizer

            self._model = MoonshineOnnxModel(
                model_name=self.model_name,
                model_precision=self.model_precision,
            )
            # Tokenizer is shared across model sizes; loading once at
            # init keeps the hot path free of file I/O.
            self._tokenizer = load_tokenizer()
        except Exception as e:
            logger.error("Moonshine load failed: %s", e)
            raise

        logger.info(
            "Moonshine ready in %.2fs", time.monotonic() - t0,
        )

    def __enter__(self) -> "MoonshineEngine":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # ONNX session is GC'd with the engine; nothing to do.
        self._model = None
        self._tokenizer = None

    def transcribe(self, audio: np.ndarray, language: Optional[str] = "en") -> str:
        """Transcribe a mono float32 16 kHz audio segment to text.

        Args:
            audio: 1-D numpy array, mono float32 at 16 kHz. Empty
                arrays return ``""``.
            language: kept for API parity; Moonshine v1/v2 base+tiny
                models are English-only and don't accept a language
                hint.

        Returns:
            Stripped transcription text. Returns ``""`` on:
            * Empty / sub-100ms audio (below Moonshine's minimum
              segment length).
            * Audio longer than 64s (the per-call ceiling) -- pre-
              segment audio upstream before calling.
            * Any underlying error (logged to errors.jsonl).
        """
        if audio.size == 0:
            return ""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Audio is 1-D (samples,); Moonshine expects (batch, samples).
        if audio.ndim == 1:
            audio_batched = audio[None, ...]
        else:
            audio_batched = audio

        num_samples = audio_batched.shape[-1]
        num_seconds = num_samples / settings.SAMPLE_RATE
        if num_seconds < _MIN_AUDIO_SECONDS:
            logger.debug(
                "Moonshine: skipping %.3fs clip (below %.1fs minimum)",
                num_seconds, _MIN_AUDIO_SECONDS,
            )
            return ""
        if num_seconds > _MAX_AUDIO_SECONDS:
            logger.warning(
                "Moonshine: %.1fs audio exceeds %.0fs per-call ceiling; "
                "returning empty. Pre-segment longer audio upstream or "
                "swap to stt.engine: whisper.",
                num_seconds, _MAX_AUDIO_SECONDS,
            )
            return ""

        t0 = time.monotonic()
        try:
            tokens = self._model.generate(audio_batched)
            decoded = self._tokenizer.decode_batch(tokens)
            text = decoded[0] if decoded else ""
            text = text.strip() if isinstance(text, str) else str(text).strip()
        except Exception as e:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.error(
                "Moonshine transcribe failed in %.0fms: %s "
                "(if this is recurring, swap to stt.engine: whisper)",
                elapsed_ms, e,
            )
            get_error_log().record(
                WhisperTranscriptionError(
                    f"Moonshine transcribe failed: {e}",
                    context={
                        "audio_seconds": num_seconds,
                        "model": self.model_name,
                        "precision": self.model_precision,
                        "engine": "moonshine",
                    },
                    recovery=(
                        "returned empty transcription; orchestrator "
                        "skips this turn. Operator: consider "
                        "``stt.engine: whisper`` to revert."
                    ),
                ),
                dependency="moonshine",
            )
            return ""

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Moonshine: %.2fs audio -> %d chars in %.0fms (RTF=%.3f, model=%s)",
            num_seconds, len(text), elapsed_ms,
            elapsed_ms / 1000 / max(num_seconds, 1e-6),
            self.model_name,
        )
        return text


__all__ = ["MoonshineEngine", "is_moonshine_available", "MOONSHINE_INSTALL_HINT"]
