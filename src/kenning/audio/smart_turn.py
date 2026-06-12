"""Smart Turn V3 — semantic end-of-turn confirmation (CPU-only).

After Silero VAD declares end-of-speech at the fast-path silence
threshold (typically 400-500 ms instead of the legacy 1200 ms), this
module runs Pipecat's Smart Turn V3 ONNX model on the captured audio
to confirm the user is actually done speaking. The model looks at
the audio's intonation, pace, and final-syllable shape and returns a
probability that the turn is complete; the orchestrator uses that
verdict to:

* trust the early end-of-speech and submit to Whisper immediately
  (typical case -- saves 500-1200 ms of perceived latency per turn), OR
* keep listening past the fast threshold (when the user actually
  trailed off mid-thought rather than finishing).

The model:

* 8M params (Whisper Tiny encoder + linear classifier head)
* int8 quantised ONNX, 8 MB on disk, ~25-35 MB CPU RAM at runtime
* ~12 ms inference on a modern CPU
* zero VRAM cost -- pinned to ``CPUExecutionProvider``
* trained on 16 kHz mono PCM, up to 8 seconds (audio is padded at
  the start, not the end)
* sigmoid output already baked into the ONNX graph -- no manual
  activation needed
* license: BSD-2-Clause

Fail-open semantics: when the model file is missing, the wrapper
construction returns ``None`` from :func:`build_detector_from_config`
and the orchestrator falls back to the legacy 1200 ms behaviour.
When the model loads but a single inference call raises, the
detector returns ``None`` (an "undecided" verdict) rather than
forcing a wrong decision; the caller treats this as "trust VAD".

References:

* https://huggingface.co/pipecat-ai/smart-turn-v3 -- model card
* https://github.com/pipecat-ai/smart-turn -- reference implementation
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from ultron.utils.logging import get_logger

logger = get_logger("audio.smart_turn")

# Required mel-spectrogram shape produced by ``WhisperFeatureExtractor(chunk_length=8)``
# at 16 kHz: 80 mel bins, 800 frames (8 s at hop 160). Verified by ONNX
# introspection on smart-turn-v3.2-cpu.onnx.
SMART_TURN_SAMPLE_RATE = 16000
SMART_TURN_WINDOW_SECONDS = 8.0
SMART_TURN_MEL_BINS = 80
SMART_TURN_MEL_FRAMES = 800
SMART_TURN_INPUT_NAME = "input_features"


class SmartTurnLoadError(RuntimeError):
    """Raised when the Smart Turn ONNX model cannot be loaded.

    Construction-time only: once a detector is built, inference
    errors degrade to ``None`` verdicts (treated as "undecided" by
    the caller) rather than raising.
    """


@dataclass(frozen=True)
class SmartTurnVerdict:
    """Result of a single Smart Turn V3 inference call.

    Attributes:
        is_complete: Whether the model believes the user has finished
            speaking. True when ``probability >= completion_threshold``.
        probability: Raw sigmoid output (already activated inside the
            ONNX graph; no manual sigmoid required). Range [0.0, 1.0].
        latency_ms: Wall-clock duration of the inference call,
            including preprocessing. Useful for diagnostic logging and
            verifying the ~12 ms target on the deployment hardware.
    """

    is_complete: bool
    probability: float
    latency_ms: float


def truncate_or_pad_for_smart_turn(
    audio: np.ndarray,
    sample_rate: int,
    *,
    window_seconds: float = SMART_TURN_WINDOW_SECONDS,
) -> np.ndarray:
    """Prepare an audio buffer for the Smart Turn feature extractor.

    Smart Turn V3 was trained on the LAST ``window_seconds`` of
    speech: when audio is longer than the window, the most recent
    ``window_seconds`` is kept (cuts the head, preserves the tail);
    when audio is shorter, ``WhisperFeatureExtractor`` pads zeros at
    the start so the speech remains aligned to the end of the input
    vector. This function handles the truncation step only; the
    feature extractor handles padding internally via
    ``padding="max_length"``.

    Args:
        audio: 1-D float32 in [-1, 1] (or other shape that flattens
            to 1-D). Other dtypes are converted to float32 in-place.
        sample_rate: Hz. Must equal :data:`SMART_TURN_SAMPLE_RATE`
            (16000) -- callers are responsible for resampling.
        window_seconds: Window cap. The default matches the model's
            training window; reducing it without retraining the model
            is unsupported.

    Returns:
        A 1-D float32 array, no longer than ``window_seconds`` of
        samples. Shorter inputs pass through unchanged (padding is
        applied later by the feature extractor).

    Raises:
        ValueError: When ``sample_rate`` is not 16000.
    """
    if sample_rate != SMART_TURN_SAMPLE_RATE:
        raise ValueError(
            f"Smart Turn V3 requires {SMART_TURN_SAMPLE_RATE} Hz audio, "
            f"got {sample_rate} Hz"
        )
    if audio.ndim != 1:
        audio = audio.reshape(-1)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)
    max_samples = int(window_seconds * sample_rate)
    if audio.shape[0] > max_samples:
        return audio[-max_samples:]
    return audio


class SmartTurnDetector:
    """Lazy-loading ONNX detector for Smart Turn V3.

    Construction validates the model file exists but does NOT load
    the session into memory -- that happens on the first
    :meth:`is_complete` call (or via :meth:`warmup`). This keeps cold
    starts cheap when smart-turn is enabled but never invoked (e.g.
    a session with only very short utterances).

    Thread-safe: a single internal lock guards the lazy-load path
    and the inference path. The ONNX session is configured for
    single-threaded sequential execution, so the lock just ensures
    one call at a time.

    Fail-open inference: any exception raised during preprocessing
    or inference is logged at WARN and the call returns ``None``.
    The orchestrator treats ``None`` as "undecided" and falls back
    to trusting VAD's verdict directly. Construction-time failures
    (bad model path, missing transformers) propagate as
    :class:`SmartTurnLoadError`.

    Args:
        model_path: Path to ``smart-turn-v3.*-cpu.onnx``. Must exist
            at construction time.
        completion_threshold: Probability above which the verdict's
            ``is_complete`` flag is set. Pipecat's tested default is
            0.5; tightening to 0.6-0.7 reduces false-positives at the
            cost of more "incomplete" verdicts (longer perceived
            latency on confidently-done turns).
        window_seconds: Audio window cap fed to the model. Matches
            the training window; reducing it without retraining the
            model is unsupported.
        num_threads: ONNX runtime intra-op thread count. 1 is the
            recommended default -- the model is tiny enough that
            threading overhead exceeds the parallelism win.
    """

    def __init__(
        self,
        model_path: Path,
        *,
        completion_threshold: float = 0.5,
        window_seconds: float = SMART_TURN_WINDOW_SECONDS,
        num_threads: int = 1,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise SmartTurnLoadError(
                f"Smart Turn V3 model file not found: {self.model_path}"
            )
        if not (0.0 < completion_threshold < 1.0):
            raise SmartTurnLoadError(
                f"completion_threshold must be in (0, 1), got {completion_threshold}"
            )
        if window_seconds <= 0:
            raise SmartTurnLoadError(
                f"window_seconds must be positive, got {window_seconds}"
            )
        if num_threads < 1:
            raise SmartTurnLoadError(
                f"num_threads must be >= 1, got {num_threads}"
            )

        self.completion_threshold = float(completion_threshold)
        self.window_seconds = float(window_seconds)
        self.num_threads = int(num_threads)
        self._session = None  # ort.InferenceSession lazy-loaded
        self._feature_extractor = None  # WhisperFeatureExtractor lazy-loaded
        self._load_lock = threading.Lock()
        self._loaded = False
        self._load_failed = False

    @property
    def available(self) -> bool:
        """True iff the model has been loaded and the session is live.

        False before the first :meth:`is_complete` / :meth:`warmup`
        call, and after a load failure. Useful in tests to confirm
        lazy-loading behaviour without forcing a real load.
        """
        return self._loaded and not self._load_failed

    def warmup(self) -> bool:
        """Force the lazy-load path to run now.

        Returns True on success, False if the load failed. The load
        is silent on failure (logged at WARN) so callers don't have
        to wrap with try/except just to opt out of warmup.
        """
        with self._load_lock:
            return self._ensure_loaded_locked()

    def _ensure_loaded_locked(self) -> bool:
        """Idempotent loader -- caller must hold ``_load_lock``."""
        if self._loaded:
            return True
        if self._load_failed:
            return False
        t0 = time.monotonic()
        try:
            import onnxruntime as ort  # local import keeps cold-start light
            from transformers import WhisperFeatureExtractor

            so = ort.SessionOptions()
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            so.intra_op_num_threads = self.num_threads
            so.inter_op_num_threads = 1
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=so,
                providers=["CPUExecutionProvider"],
            )
            self._feature_extractor = WhisperFeatureExtractor(chunk_length=8)
            self._loaded = True
            logger.info(
                "Smart Turn V3 loaded in %.0f ms (model=%s, threads=%d)",
                (time.monotonic() - t0) * 1000,
                self.model_path.name,
                self.num_threads,
            )
            return True
        except Exception as e:
            self._load_failed = True
            logger.warning(
                "Smart Turn V3 load failed -- detector disabled (model=%s): %s",
                self.model_path,
                e,
            )
            return False

    def is_complete(
        self,
        audio: np.ndarray,
        sample_rate: int = SMART_TURN_SAMPLE_RATE,
    ) -> Optional[SmartTurnVerdict]:
        """Run inference and return a verdict, or ``None`` on error.

        Args:
            audio: Mono PCM at ``sample_rate`` Hz. Float32 in [-1, 1]
                is preferred; other dtypes are converted in-place.
                Multi-dimensional inputs are flattened to 1-D. Empty
                arrays return ``None`` (treated as "undecided" by
                callers).
            sample_rate: Hz of the input. Must equal
                :data:`SMART_TURN_SAMPLE_RATE` (16000); callers
                resample upstream.

        Returns:
            A :class:`SmartTurnVerdict` on success, or ``None`` when:
            - the model failed to load (one-time failure -- subsequent
              calls also return ``None``);
            - the audio is empty;
            - preprocessing or inference raised (logged at WARN);
            - ``sample_rate`` doesn't match the model's expectation.
        """
        if sample_rate != SMART_TURN_SAMPLE_RATE:
            logger.warning(
                "Smart Turn V3 input sample_rate %d != %d; skipping",
                sample_rate, SMART_TURN_SAMPLE_RATE,
            )
            return None
        if audio is None or audio.size == 0:
            return None

        with self._load_lock:
            if not self._ensure_loaded_locked():
                return None

        t0 = time.monotonic()
        try:
            prepped = truncate_or_pad_for_smart_turn(
                audio,
                sample_rate,
                window_seconds=self.window_seconds,
            )
            # WhisperFeatureExtractor pads zeros at the start so the
            # speech is anchored to the end of the input vector --
            # matching the training distribution.
            features = self._feature_extractor(
                prepped,
                sampling_rate=SMART_TURN_SAMPLE_RATE,
                return_tensors="np",
                padding="max_length",
                max_length=int(self.window_seconds * SMART_TURN_SAMPLE_RATE),
                truncation=True,
                do_normalize=True,
            )
            input_features = features.input_features.astype(np.float32)
            if input_features.ndim == 2:
                # WhisperFeatureExtractor returns (batch, mels, frames)
                # already; defensive in case future versions strip the
                # batch dim.
                input_features = np.expand_dims(input_features, axis=0)
            outputs = self._session.run(
                None, {SMART_TURN_INPUT_NAME: input_features}
            )
            probability = float(outputs[0][0].item())
        except Exception as e:
            logger.warning(
                "Smart Turn V3 inference failed (%d samples @ %d Hz): %s",
                audio.size, sample_rate, e,
            )
            return None

        latency_ms = (time.monotonic() - t0) * 1000
        is_complete = probability >= self.completion_threshold
        logger.debug(
            "Smart Turn V3: prob=%.3f (threshold=%.2f) -> %s in %.1f ms",
            probability,
            self.completion_threshold,
            "complete" if is_complete else "incomplete",
            latency_ms,
        )
        return SmartTurnVerdict(
            is_complete=is_complete,
            probability=probability,
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        """Release the ONNX session.

        Idempotent. Subsequent :meth:`is_complete` calls will return
        ``None`` because the detector flags itself as load-failed
        after close.
        """
        with self._load_lock:
            self._session = None
            self._feature_extractor = None
            self._loaded = False
            self._load_failed = True


def build_detector_from_config(
    smart_turn_cfg,
    project_root: Path,
) -> Optional[SmartTurnDetector]:
    """Construct a :class:`SmartTurnDetector` from a pydantic
    ``SmartTurnConfig`` section, or return ``None`` to skip.

    Fail-open: when ``smart_turn_cfg.enabled`` is False, when the
    model file doesn't exist, or when construction raises, this
    returns ``None`` and the orchestrator falls back to its legacy
    VAD-only end-of-turn detection. A WARN-level log message
    distinguishes "disabled by config" from "enabled but file
    missing".

    Args:
        smart_turn_cfg: The ``VADConfig.smart_turn`` pydantic model.
        project_root: Base directory for resolving the relative
            model path. Typically :data:`PROJECT_ROOT` from
            :mod:`ultron.config`.

    Returns:
        A constructed (but not yet loaded) :class:`SmartTurnDetector`
        on success, or ``None`` when smart-turn is disabled / the
        model is missing / construction fails.
    """
    if not getattr(smart_turn_cfg, "enabled", False):
        logger.info("Smart Turn V3 disabled by config")
        return None

    rel_path = Path(getattr(smart_turn_cfg, "model_path", ""))
    if not rel_path.is_absolute():
        model_path = Path(project_root) / rel_path
    else:
        model_path = rel_path

    if not model_path.is_file():
        logger.warning(
            "Smart Turn V3 enabled but model file missing at %s; "
            "falling back to legacy VAD-only end-of-turn",
            model_path,
        )
        return None

    try:
        return SmartTurnDetector(
            model_path,
            completion_threshold=float(
                getattr(smart_turn_cfg, "completion_threshold", 0.5)
            ),
            window_seconds=float(
                getattr(smart_turn_cfg, "window_seconds", SMART_TURN_WINDOW_SECONDS)
            ),
            num_threads=int(getattr(smart_turn_cfg, "num_threads", 1)),
        )
    except SmartTurnLoadError as e:
        logger.warning("Smart Turn V3 construction failed: %s", e)
        return None
    except Exception as e:
        logger.warning(
            "Smart Turn V3 construction failed unexpectedly: %s", e
        )
        return None
