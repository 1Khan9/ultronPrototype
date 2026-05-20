"""Kokoro TTS engine (2026-05-19, Track 5).

Wrapper around the Kokoro StyleTTS2 + ISTFTNet inference model. Same
public surface as :class:`ultron.tts.xtts_v3.XttsV3Speech` (and the
legacy :class:`ultron.tts.speech.TextToSpeech`) so the orchestrator
can switch engines via ``tts.engine`` without touching the playback
path.

Module ships unconditionally; the actual Kokoro weights load lazily
on first ``warmup()`` / ``speak()`` call. When the weights aren't on
disk (the typical state on a fresh checkout), the engine surfaces a
clear :class:`KokoroEngineLoadError` rather than silently producing
silence -- callers can fall back to a different engine via config.

Three things deliberately omitted vs the XTTS engine to keep the
scope of this change small:

1. **No automatic v3 pedalboard filter chain.** Kokoro is intended to
   be fine-tuned on POST-filter audio (so the filter character is
   baked into the model weights and chunk streaming becomes
   tractable -- see the 2026-05-19 design conversation). The runtime
   filter pass exists as an opt-in ``apply_runtime_filter`` flag for
   pre-fine-tune use while the corpus is being prepared.
2. **No isolated venv subprocess.** Kokoro's dep tree (transformers,
   phonemizer, scipy) overlaps cleanly with the main Ultron venv.
   In-process loading saves a CUDA context + ~50 ms IPC overhead per
   synth.
3. **No fine-tune training code.** Training pipelines live in
   ``ultronVoiceAudio/`` per the existing voice-prep convention.
   This module is inference-only.

Default ``tts.engine`` is unchanged. To use Kokoro: place weights at
``models/kokoro/`` and set ``tts.engine: kokoro`` in ``config.yaml``.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, NamedTuple, Optional, Tuple

import numpy as np

from ultron.utils.logging import get_logger

logger = get_logger("tts.kokoro")


# ----------------------------------------------------------------------
# Public exceptions + types
# ----------------------------------------------------------------------


class KokoroEngineLoadError(RuntimeError):
    """Raised when Kokoro weights / dependencies are unavailable."""


class KokoroSynthError(RuntimeError):
    """Raised when an inference call fails."""


Clip = Tuple[np.ndarray, int]


class ClipItem(NamedTuple):
    """Mirror of the XTTS / legacy ClipItem shape for queue uniformity."""

    audio: np.ndarray
    sample_rate: int
    is_known_last: bool = False


# Kokoro models the SAME native sample rate as XTTS (24 kHz) so the
# orchestrator's output-stream pre-open machinery can hand the
# device handle between engines without re-opening.
_KOKORO_DEFAULT_SAMPLE_RATE: int = 24000


# ----------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------


class KokoroSpeech:
    """Kokoro StyleTTS2 inference engine.

    Drop-in for :class:`XttsV3Speech` and :class:`TextToSpeech` --
    exposes ``speak`` / ``speak_stream`` / ``warmup`` /
    ``prepare_output_stream`` / ``stop`` so the playback path doesn't
    change when the orchestrator swaps engines.

    Args:
        model_path: directory containing the Kokoro weights + voices.
            Defaults to ``models/kokoro/``. The directory must exist
            for the engine to load; missing weights produce a
            :class:`KokoroEngineLoadError` on first inference.
        voice: name of the voice to render. Production-tuned Ultron
            voice is loaded from ``model_path/voices/{voice}.pt`` once
            the fine-tune lands; pre-fine-tune we fall back to one of
            Kokoro's stock voices (typically ``af_alloy`` or
            ``am_michael``) so the engine boots even before the
            corpus is prepared.
        device: ``"cpu"`` or ``"cuda"``. Kokoro is genuinely fast on
            CPU (StyleTTS2 + ISTFTNet is feed-forward; near-realtime
            on modern CPUs). Default ``"cpu"`` keeps the GPU free for
            LLM + Whisper. Set to ``"cuda"`` to push synthesis on the
            GPU for ~3x faster inference.
        speed: speech-rate multiplier (1.0 = native). Mirrors the
            XTTS speed knob -- the orchestrator can hot-swap engines
            without re-tuning cadence.
        apply_runtime_filter: when True, the v3 Ultron pedalboard
            filter runs on Kokoro's output (CPU; ~10-30 ms /
            sentence). Useful pre-fine-tune so the voice character
            matches the XTTS pipeline. Default False since the
            target end-state is Kokoro fine-tuned on already-
            filtered audio (filter baked into weights).
        filter_preset: pedalboard preset name when
            ``apply_runtime_filter`` is True.
    """

    def __init__(
        self,
        *,
        model_path: Optional[Path] = None,
        voice: str = "af_alloy",
        device: str = "cpu",
        speed: float = 1.0,
        apply_runtime_filter: bool = False,
        filter_preset: str = "v3_heavy",
        flush_chars: str = ".!?\n",
        sample_rate: int = _KOKORO_DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.model_path = Path(model_path) if model_path else Path("models/kokoro")
        self.voice = voice
        self.device = device
        self.speed = float(speed)
        self.apply_runtime_filter = bool(apply_runtime_filter)
        self.filter_preset = filter_preset
        self.flush_chars = set(flush_chars)
        self._sample_rate = int(sample_rate)
        self._model = None
        self._model_lock = threading.Lock()
        self._loaded = False
        self._load_error: Optional[str] = None
        self._stop_event = threading.Event()
        self._playback_lock = threading.Lock()
        # 2026-05-15 latency parity: pre-open output stream slot.
        self._preopened_stream = None
        self._preopened_lock = threading.Lock()
        # Lazy import inside the synth path so a missing kokoro
        # install doesn't crash at module import time -- callers can
        # construct the engine and discover the load failure at the
        # first inference call (matches the XTTS pattern).

    # ------------------------------------------------------------------
    # Lifecycle / lazy load
    # ------------------------------------------------------------------

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def is_available(self) -> bool:
        """True iff the engine has successfully loaded (or hasn't tried).

        Returns False after a prior load attempt failed; the engine
        won't retry the load until :meth:`reset_load_error` clears
        the cached failure. Used by the orchestrator to decide
        whether to fall back to XTTS / legacy.
        """
        if self._load_error is not None:
            return False
        return True

    def reset_load_error(self) -> None:
        """Clear the cached load-failure state so the next inference
        retries the load. Useful after the operator drops the
        weights into ``model_path`` mid-session."""
        with self._model_lock:
            self._load_error = None

    def _ensure_loaded(self) -> None:
        """Lazy-load Kokoro on first use.

        Raises :class:`KokoroEngineLoadError` on failure (missing
        directory, missing package, etc.). The failure is cached --
        subsequent calls fail fast without retrying the import.
        """
        if self._loaded:
            return
        if self._load_error is not None:
            raise KokoroEngineLoadError(self._load_error)
        with self._model_lock:
            if self._loaded:
                return
            if self._load_error is not None:
                raise KokoroEngineLoadError(self._load_error)
            try:
                self._do_load()
                self._loaded = True
            except Exception as e:                            # noqa: BLE001
                msg = f"Kokoro load failed: {e}"
                self._load_error = msg
                logger.warning(msg)
                raise KokoroEngineLoadError(msg) from e

    def _do_load(self) -> None:
        """Construct the Kokoro pipeline object.

        Tries the ``kokoro`` package's high-level API first (preferred
        for production); falls back to a manual StyleTTS2 + ISTFTNet
        load if the package isn't installed. Both paths assume the
        weights are in ``self.model_path``.
        """
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Kokoro model directory not found: {self.model_path}. "
                f"Download weights with scripts/download_models.py or "
                f"point tts.kokoro.model_path at the correct location."
            )
        try:
            # Preferred path: hexgrad/kokoro PyPI package.
            from kokoro import KPipeline                       # type: ignore
        except ImportError as e:
            raise KokoroEngineLoadError(
                "The ``kokoro`` package is not installed. Add it to "
                "the venv via ``uv pip install kokoro`` (or ``pip "
                "install kokoro``) and re-run."
            ) from e
        # ``lang_code='a'`` selects American English. The pipeline
        # internally loads ISTFTNet vocoder + StyleTTS2 acoustic model.
        self._model = KPipeline(
            lang_code="a",
            device=self.device,
        )
        logger.info(
            "Kokoro ready (voice=%s, device=%s, sample_rate=%d)",
            self.voice, self.device, self._sample_rate,
        )

    def warmup(self, text: str = "Online.") -> None:
        """Touch the inference pipeline with a tiny request.

        Fail-open: load failures are logged WARN and the warmup is a
        no-op. The first real ``speak`` call will surface the same
        error if it persists.
        """
        if not text.strip():
            return
        try:
            t0 = time.monotonic()
            self._synthesize(text)
            logger.info(
                "Kokoro warmup complete in %.0f ms",
                (time.monotonic() - t0) * 1000,
            )
        except KokoroEngineLoadError as e:
            logger.warning("Kokoro warmup skipped: %s", e)
        except Exception as e:                                # noqa: BLE001
            logger.warning("Kokoro warmup failed (%s); engine may be unhealthy", e)

    # ------------------------------------------------------------------
    # Public synth + playback API (mirrors XttsV3Speech)
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Signal playback interrupt -- mirrors XTTS stop()."""
        self._stop_event.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        with self._preopened_lock:
            s = self._preopened_stream
            self._preopened_stream = None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass

    def speak(self, text: str) -> None:
        """Synth + play synchronously. Mirrors XttsV3Speech.speak()."""
        if not text.strip():
            return
        self._stop_event.clear()
        clip = self._synthesize(text)
        if clip[0].size > 0 and not self._stop_event.is_set():
            self._play(clip)

    def prepare_output_stream(self) -> None:
        """Pre-open the PortAudio output device.

        Mirrors the 2026-05-15 latency-pass pattern on XTTS. The
        orchestrator calls this on a daemon thread during STT so the
        ~50 ms device-open cost overlaps with transcription. Fails
        open -- live ``speak_stream`` opens fresh if pre-open
        couldn't complete.
        """
        with self._preopened_lock:
            if self._preopened_stream is not None:
                return
            try:
                import sounddevice as sd
                stream = sd.OutputStream(
                    samplerate=self._sample_rate,
                    channels=2,
                    dtype="int16",
                )
                stream.start()
                # 50 ms silence write wakes the device clock.
                silence = np.zeros((self._sample_rate // 20, 2), dtype=np.int16)
                stream.write(silence)
                self._preopened_stream = stream
            except Exception as e:                            # noqa: BLE001
                logger.warning("Kokoro pre-open failed: %s", e)

    def speak_stream(self, fragments: Iterable[str]) -> None:
        """Consume token fragments + play sentence-by-sentence.

        Streams sentences as they complete (flush on
        ``flush_chars``). Mirrors the XTTS / legacy contract so the
        orchestrator's playback path works unchanged.
        """
        self._stop_event.clear()
        buffer: list[str] = []
        for frag in fragments:
            if self._stop_event.is_set():
                return
            if not frag:
                continue
            remaining = frag
            while remaining:
                flush_pos = next(
                    (i for i, c in enumerate(remaining) if c in self.flush_chars),
                    -1,
                )
                if flush_pos == -1:
                    buffer.append(remaining)
                    break
                buffer.append(remaining[: flush_pos + 1])
                sentence = "".join(buffer).strip()
                buffer.clear()
                remaining = remaining[flush_pos + 1:]
                if sentence:
                    try:
                        clip = self._synthesize(sentence)
                    except KokoroEngineLoadError as e:
                        logger.warning(
                            "Kokoro load error mid-stream (%s); "
                            "skipping sentence: %r", e, sentence[:40],
                        )
                        continue
                    if clip[0].size > 0:
                        self._play(clip)
        tail = "".join(buffer).strip()
        if tail and not self._stop_event.is_set():
            try:
                clip = self._synthesize(tail)
            except KokoroEngineLoadError as e:
                logger.warning("Kokoro load error on tail (%s)", e)
                return
            if clip[0].size > 0:
                self._play(clip)

    # ------------------------------------------------------------------
    # Internal: synth + playback
    # ------------------------------------------------------------------

    def _synthesize(self, text: str) -> Clip:
        """Run Kokoro inference on a sentence and return int16 PCM."""
        self._ensure_loaded()
        if self._model is None:
            raise KokoroEngineLoadError("Kokoro model is None after load")
        try:
            # KPipeline returns a generator of (graphemes, phonemes,
            # audio_tensor) tuples per sentence; we concatenate.
            audio_chunks: list[np.ndarray] = []
            generator = self._model(text, voice=self.voice, speed=self.speed)
            for _gs, _ps, audio in generator:
                if audio is None:
                    continue
                # ``audio`` is a torch Tensor (cpu or cuda). Convert
                # to numpy float32 [-1, 1].
                try:
                    arr = audio.detach().cpu().numpy().astype(np.float32)
                except AttributeError:
                    # Already a numpy array.
                    arr = np.asarray(audio, dtype=np.float32)
                audio_chunks.append(arr)
        except Exception as e:                                # noqa: BLE001
            raise KokoroSynthError(f"Kokoro inference failed: {e}") from e

        if not audio_chunks:
            return np.zeros(0, dtype=np.int16), self._sample_rate

        pcm_f32 = np.concatenate(audio_chunks)

        # Optional pre-fine-tune runtime filter pass.
        if self.apply_runtime_filter:
            try:
                from ultron.tts.ultron_filter import apply_filter
                pcm_f32 = apply_filter(
                    pcm_f32, self._sample_rate,
                    preset=self.filter_preset,
                    tail_silence_ms=200.0,
                )
            except Exception as e:                            # noqa: BLE001
                logger.warning("Ultron filter on Kokoro output failed: %s", e)

        # Clip + convert to int16 (mirrors the XTTS engine's tail).
        np.clip(pcm_f32, -1.0, 1.0, out=pcm_f32)
        out_pcm = (pcm_f32 * 32767.0).astype(np.int16)
        return out_pcm, self._sample_rate

    def _play(self, clip: Clip) -> None:
        """Single-shot playback."""
        pcm, sr = clip
        try:
            import sounddevice as sd
        except Exception as e:                                # noqa: BLE001
            logger.warning("sounddevice unavailable -- skipping Kokoro playback: %s", e)
            return
        if pcm.size == 0:
            return
        with self._playback_lock:
            if self._stop_event.is_set():
                return
            try:
                # Stereo expand for the output stream.
                stereo = np.column_stack((pcm, pcm)).astype(np.int16, copy=False)
                stream = self._consume_preopened_stream(sr)
                opened_here = False
                if stream is None:
                    stream = sd.OutputStream(
                        samplerate=sr, channels=2, dtype="int16",
                    )
                    stream.start()
                    opened_here = True
                try:
                    block_frames = max(1, int(sr * 0.05))
                    for start in range(0, stereo.shape[0], block_frames):
                        if self._stop_event.is_set():
                            return
                        stream.write(stereo[start: start + block_frames])
                finally:
                    if opened_here:
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
            except Exception as e:                            # noqa: BLE001
                logger.warning("Kokoro playback error: %s", e)

    def _consume_preopened_stream(self, sr: int):
        """Take ownership of any pre-opened output stream."""
        with self._preopened_lock:
            s = self._preopened_stream
            self._preopened_stream = None
        if s is None:
            return None
        if sr != self._sample_rate:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
            return None
        return s


__all__ = [
    "ClipItem",
    "KokoroEngineLoadError",
    "KokoroSpeech",
    "KokoroSynthError",
]
