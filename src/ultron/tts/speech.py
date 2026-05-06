"""Piper TTS wrapper with sentence-level streaming and optional RVC conversion.

The streaming API takes an iterator of text fragments (usually LLM tokens)
and synthesizes once a sentence boundary is reached, so audio starts playing
before the LLM finishes generating. Synthesis runs on a worker thread; the
main thread can interrupt mid-stream by calling :meth:`stop`.

If an :class:`RvcConverter` is passed in, every synthesized sentence is run
through it before playback. This converts Piper's neutral voice to the
trained target (Ultron). RVC may output at a different sample rate than
Piper, so each clip carries its own ``(pcm, sample_rate)`` pair through the
queue.
"""

from __future__ import annotations

import io
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Iterable, Optional, Tuple

import numpy as np
import sounddevice as sd

from config import settings
from ultron.audio.devices import describe_device, resolve_device
from ultron.tts.rvc import RvcConverter
from ultron.utils.logging import get_logger

logger = get_logger("tts.speech")

# A clip is (pcm_int16, sample_rate). Sample rate may vary per clip when RVC
# is in the loop because it can up-rate output beyond Piper's native 22050.
Clip = Tuple[np.ndarray, int]


class TextToSpeech:
    """Piper TTS playback with synchronous and streaming modes.

    Args:
        voice_path: Path to a Piper ``.onnx`` voice file.
        config_path: Path to the matching ``.onnx.json`` config.
        sample_rate: Piper's native output rate (medium voices = 22050).
        flush_chars: Characters that flush a buffered fragment as a sentence.
        length_scale: Piper pacing; >1.0 slows the voice down.
        rvc: Optional :class:`RvcConverter`. When set, every Piper sentence
            is run through RVC before playback.
    """

    def __init__(
        self,
        voice_path: Path = settings.TTS_VOICE_PATH,
        config_path: Path = settings.TTS_VOICE_CONFIG_PATH,
        sample_rate: int = settings.TTS_OUTPUT_SAMPLE_RATE,
        flush_chars: str = settings.TTS_SENTENCE_FLUSH_CHARS,
        length_scale: float = settings.TTS_LENGTH_SCALE,
        rvc: Optional[RvcConverter] = None,
    ) -> None:
        from piper import PiperVoice

        if not Path(voice_path).is_file():
            raise FileNotFoundError(
                f"Piper voice not found at {voice_path}. "
                f"Run `python scripts/download_models.py` first."
            )

        self.voice_path = Path(voice_path)
        self.piper_sample_rate = sample_rate
        self.flush_chars = set(flush_chars)
        self.length_scale = length_scale
        self.rvc = rvc
        self.output_device = resolve_device(settings.AUDIO_OUTPUT_DEVICE, "output")
        self._stop_event = threading.Event()
        self._playback_lock = threading.Lock()

        logger.info("Loading Piper voice: %s", voice_path)
        t0 = time.monotonic()
        try:
            self._voice = PiperVoice.load(str(voice_path), config_path=str(config_path))
        except TypeError:
            self._voice = PiperVoice.load(str(voice_path))
        logger.info(
            "Piper voice ready in %.2fs (length_scale=%.2f, rvc=%s)",
            time.monotonic() - t0,
            length_scale,
            "on" if rvc else "off",
        )
        logger.info("TTS output device: %s", describe_device(self.output_device, "output"))

    def __enter__(self) -> "TextToSpeech":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # --- public API ----------------------------------------------------------

    def stop(self) -> None:
        """Interrupt any in-progress playback."""
        self._stop_event.set()
        try:
            sd.stop()
        except Exception:
            pass

    def speak(self, text: str) -> None:
        """Synchronously synthesize and play ``text`` to completion."""
        if not text.strip():
            return
        self._stop_event.clear()
        clip = self._synthesize(text)
        if clip[0].size > 0 and not self._stop_event.is_set():
            self._play(clip)

    def speak_stream(self, fragments: Iterable[str]) -> None:
        """Consume token fragments and play sentence-by-sentence.

        A worker thread reads the token iterator, accumulates a sentence,
        synthesizes (and converts via RVC if configured), and pushes the
        resulting clip onto a playback queue. The calling thread drains
        the queue and plays each clip in order.
        """
        self._stop_event.clear()
        audio_q: queue.Queue[Optional[Clip]] = queue.Queue(maxsize=8)

        def synth_worker() -> None:
            buffer = []
            try:
                for frag in fragments:
                    if self._stop_event.is_set():
                        break
                    if not frag:
                        continue
                    buffer.append(frag)
                    if any(c in self.flush_chars for c in frag):
                        sentence = "".join(buffer).strip()
                        buffer.clear()
                        if sentence:
                            clip = self._synthesize(sentence)
                            if clip[0].size > 0:
                                audio_q.put(clip)
                tail = "".join(buffer).strip()
                if tail and not self._stop_event.is_set():
                    clip = self._synthesize(tail)
                    if clip[0].size > 0:
                        audio_q.put(clip)
            except Exception as e:
                logger.error("TTS worker error: %s", e)
            finally:
                audio_q.put(None)  # sentinel

        worker = threading.Thread(target=synth_worker, daemon=True)
        worker.start()

        while True:
            if self._stop_event.is_set():
                break
            try:
                clip = audio_q.get(timeout=10.0)
            except queue.Empty:
                logger.warning("TTS playback queue starved; aborting")
                break
            if clip is None:
                break
            self._play(clip)

        worker.join(timeout=2.0)

    # --- internals -----------------------------------------------------------

    def _synthesize(self, text: str) -> Clip:
        """Synthesize one sentence: Piper → optional RVC → (pcm, sample_rate)."""
        t0 = time.monotonic()
        pcm, sr = self._piper_synth(text)
        if pcm.size == 0:
            return pcm, sr

        if self.rvc is not None:
            try:
                pcm, sr = self.rvc.convert(pcm, sr)
            except Exception as e:
                logger.warning("RVC convert failed (using raw Piper): %s", e)

        logger.debug(
            "TTS pipeline: %d chars → %.2fs audio @ %d Hz in %.0fms",
            len(text),
            len(pcm) / max(sr, 1),
            sr,
            (time.monotonic() - t0) * 1000,
        )
        return pcm, sr

    def _piper_synth(self, text: str) -> Clip:
        """Run Piper alone and return ``(int16 pcm, sample_rate)``."""
        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, "wb") as wav:
                if hasattr(self._voice, "synthesize_wav"):
                    syn_config = self._synthesis_config()
                    self._voice.synthesize_wav(text, wav, syn_config=syn_config)
                else:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(self.piper_sample_rate)
                    try:
                        self._voice.synthesize(
                            text, wav, length_scale=self.length_scale
                        )
                    except TypeError:
                        self._voice.synthesize(text, wav)
        except Exception as e:
            logger.error("Piper synth failed for %r: %s", text[:60], e)
            return np.zeros(0, dtype=np.int16), self.piper_sample_rate

        wav_buffer.seek(0)
        with wave.open(wav_buffer, "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            sr = wav.getframerate()
        pcm = np.frombuffer(frames, dtype=np.int16)
        if pcm.size == 0:
            logger.warning("Piper produced no audio for %r", text[:60])
        return pcm, sr

    def _synthesis_config(self):
        """Build a Piper synthesis config when the installed API supports it."""
        try:
            from piper.config import SynthesisConfig

            return SynthesisConfig(length_scale=self.length_scale)
        except Exception:
            return None

    def _play(self, clip: Clip) -> None:
        pcm, sr = clip
        with self._playback_lock:
            if self._stop_event.is_set():
                return
            try:
                audio = self._stereo_pcm(pcm)
                duration = audio.shape[0] / max(sr, 1)
                logger.info(
                    "Playing TTS clip: %.2fs @ %d Hz via %s",
                    duration,
                    sr,
                    describe_device(self.output_device, "output"),
                )

                block_frames = max(1, int(sr * 0.05))
                with sd.OutputStream(
                    samplerate=sr,
                    channels=2,
                    dtype="int16",
                    device=self.output_device,
                ) as stream:
                    for start in range(0, audio.shape[0], block_frames):
                        if self._stop_event.is_set():
                            return
                        stream.write(audio[start : start + block_frames])
            except Exception as e:
                logger.warning("Playback error: %s", e)

    @staticmethod
    def _stereo_pcm(pcm: np.ndarray) -> np.ndarray:
        """Return 2-channel int16 PCM for predictable headphone playback."""
        mono = np.asarray(pcm, dtype=np.int16).reshape(-1)
        if mono.size == 0:
            return np.zeros((0, 2), dtype=np.int16)
        return np.column_stack((mono, mono)).astype(np.int16, copy=False)
