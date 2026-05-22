"""Speech-to-text engines.

Three engines are wired:

- :class:`WhisperEngine` -- the long-standing default; faster-whisper
  on CUDA. Strong on accented / noisy audio; ~80 ms median on 5 s
  audio with ``base.en`` beam=1.
- :class:`ParakeetEngine` -- NVIDIA Parakeet TDT via NeMo.
  Frontier-enhancement Item 5 (2026-05-21). Streaming-native RNN-T;
  ~RTFx 2000+ on consumer GPUs. Requires
  ``pip install nemo_toolkit[asr]`` in an isolated venv.
- :class:`MoonshineEngine` -- Moonshine ONNX (2026-05-22). Lowest-
  footprint option (58 MB base model on CPU); streaming-native; ~5-
  15 ms on short voice clips. Requires
  ``pip install useful-moonshine-onnx`` -- pure ONNX runtime, no
  Keras / TF / PyTorch upgrade needed.

Use :func:`make_stt_engine` to construct the configured engine
(respects ``stt.engine`` and falls back gracefully when deps are
missing).
"""

from __future__ import annotations

from typing import Union, TYPE_CHECKING

from ultron.transcription.moonshine_engine import (
    MOONSHINE_INSTALL_HINT,
    MoonshineEngine,
    is_moonshine_available,
)
from ultron.transcription.parakeet_engine import (
    PARAKEET_INSTALL_HINT,
    ParakeetEngine,
    is_nemo_available,
)
from ultron.transcription.whisper_engine import WhisperEngine
from ultron.utils.logging import get_logger

if TYPE_CHECKING:
    from ultron.config import STTConfig

logger = get_logger("transcription.factory")

# Type alias: any engine that quacks like the WhisperEngine
# transcribe interface. All engines expose
# ``transcribe(audio: np.ndarray, language: Optional[str]) -> str``.
STTEngine = Union[WhisperEngine, ParakeetEngine, MoonshineEngine]


def make_stt_engine(cfg: "STTConfig | None" = None) -> STTEngine:
    """Construct the STT engine selected by ``stt.engine``.

    Resolution:
    - ``auto``: Parakeet if NeMo is installed; else Whisper. (Moonshine
      is opt-in via the explicit selector because its WER trade-off vs
      Whisper depends on the user's audio characteristics and we don't
      want to silently switch.)
    - ``whisper``: always Whisper.
    - ``parakeet``: always Parakeet (raises if NeMo missing).
    - ``moonshine``: always Moonshine ONNX (raises if package missing).

    The active choice is logged at INFO so it's visible at startup --
    important because the engine is the FIRST thing to suspect if
    voice transcription regresses.
    """
    if cfg is None:
        from ultron.config import get_config
        cfg = get_config().stt

    selector = getattr(cfg, "engine", "whisper")

    if selector == "moonshine":
        if not is_moonshine_available():
            raise ImportError(MOONSHINE_INSTALL_HINT)
        logger.info(
            "STT engine: moonshine (forced by config; ONNX on CPU)"
        )
        return MoonshineEngine(
            model_name=getattr(cfg, "moonshine_model", None),
            device=getattr(cfg, "moonshine_device", None),
            model_precision=getattr(cfg, "moonshine_precision", None),
        )

    if selector == "parakeet":
        if not is_nemo_available():
            raise ImportError(PARAKEET_INSTALL_HINT)
        logger.info(
            "STT engine: parakeet (forced by config; frontier item 5)"
        )
        return ParakeetEngine(
            model_name=getattr(cfg, "parakeet_model", None),
            device=getattr(cfg, "parakeet_device", None),
        )

    if selector == "auto":
        if is_nemo_available():
            try:
                engine = ParakeetEngine(
                    model_name=getattr(cfg, "parakeet_model", None),
                    device=getattr(cfg, "parakeet_device", None),
                )
                logger.info(
                    "STT engine: parakeet (auto-detected NeMo; "
                    "frontier item 5. If voice quality regresses, "
                    "set ``stt.engine: whisper`` to swap back.)"
                )
                return engine
            except Exception as e:                                 # noqa: BLE001
                logger.warning(
                    "Parakeet auto-load failed (%s); falling back to "
                    "Whisper. Set ``stt.engine: parakeet`` explicitly "
                    "to surface this error.", e,
                )
        logger.info("STT engine: whisper (auto -- NeMo not available)")
        return WhisperEngine()

    # selector == "whisper" or anything unrecognised
    logger.info("STT engine: whisper")
    return WhisperEngine()


__all__ = [
    "make_stt_engine",
    "STTEngine",
    "WhisperEngine",
    "ParakeetEngine",
    "MoonshineEngine",
    "is_nemo_available",
    "is_moonshine_available",
    "PARAKEET_INSTALL_HINT",
    "MOONSHINE_INSTALL_HINT",
]
