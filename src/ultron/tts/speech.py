"""Piper TTS wrapper with sentence-level streaming.

The streaming API takes an iterator of text fragments (usually LLM tokens)
and synthesizes once a sentence boundary is reached, so audio starts playing
before the LLM finishes generating. Synthesis runs on a worker thread; the
main thread can interrupt mid-stream by calling :meth:`stop`.
"""

from __future__ import annotations

import io
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Iterable, Iterator, Optional

import numpy as np
import sounddevice as sd

from config import settings
from ultron.utils.logging import get_logger

logger = get_logger("tts.speech")


class TextToSpeech:
    """Piper TTS playback with synchronous and streaming modes.

    Args:
        voice_path: Path to a Piper ``.onnx`` voice file.
        config_path: Path to the matching ``.onnx.json`` config.
        sample_rate: Output sample rate; must match the voice (Piper medium
            voices are 22050 Hz).
        flush_chars: Characters that flush a buffered fragment as a sentence.
    """

    def __init__(
        self,
        voice_path: Path = settings.TTS_VOICE_PATH,
        config_path: Path = settings.TTS_VOICE_CONFIG_PATH,
        sample_rate: int = settings.TTS_OUTPUT_SAMPLE_RATE,
        flush_chars: str = settings.TTS_SENTENCE_FLUSH_CHARS,
    ) -> None:
        from piper import PiperVoice

        if not Path(voice_path).is_file():
            raise FileNotFoundError(
                f"Piper voice not found at {voice_path}. "
                f"Run `python scripts/download_models.py` first."
            )

        self.voice_path = Path(voice_path)
        self.sample_rate = sample_rate
        self.flush_chars = set(flush_chars)
        self._stop_event = threading.Event()
        self._playback_lock = threading.Lock()

        logger.info("Loading Piper voice: %s", voice_path)
        t0 = time.monotonic()
        # PiperVoice.load is the canonical loader; some versions accept just
        # the model path and infer the config automatically.
        try:
            self._voice = PiperVoice.load(str(voice_path), config_path=str(config_path))
        except TypeError:
            self._voice = PiperVoice.load(str(voice_path))
        logger.info("Piper voice ready in %.2fs", time.monotonic() - t0)

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
        audio = self._synthesize(text)
        if audio.size > 0 and not self._stop_event.is_set():
            self._play(audio)

    def speak_stream(self, fragments: Iterable[str]) -> None:
        """Consume token fragments and play sentence-by-sentence.

        A worker thread reads the token iterator, accumulates a sentence,
        synthesizes, and pushes the resulting audio onto a playback queue.
        The calling thread drains that queue and plays each clip in order.
        """
        self._stop_event.clear()
        audio_q: queue.Queue[Optional[np.ndarray]] = queue.Queue(maxsize=8)

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
                            audio = self._synthesize(sentence)
                            if audio.size > 0:
                                audio_q.put(audio)
                # Trailing fragment without terminal punctuation.
                tail = "".join(buffer).strip()
                if tail and not self._stop_event.is_set():
                    audio = self._synthesize(tail)
                    if audio.size > 0:
                        audio_q.put(audio)
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

    def _synthesize(self, text: str) -> np.ndarray:
        """Run Piper and return mono int16 PCM as a numpy array."""
        t0 = time.monotonic()
        wav_buffer = io.BytesIO()
        try:
            with wave.open(wav_buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                self._voice.synthesize(text, wav)
        except Exception as e:
            logger.error("Piper synth failed for %r: %s", text[:60], e)
            return np.zeros(0, dtype=np.int16)

        wav_buffer.seek(0)
        with wave.open(wav_buffer, "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            sr = wav.getframerate()
        pcm = np.frombuffer(frames, dtype=np.int16)
        if sr != self.sample_rate:
            logger.warning("Piper produced sr=%d, expected %d", sr, self.sample_rate)
            self.sample_rate = sr  # adapt rather than misplay
        logger.debug(
            "TTS synth: %d chars → %.2fs audio in %.0fms",
            len(text),
            len(pcm) / self.sample_rate,
            (time.monotonic() - t0) * 1000,
        )
        return pcm

    def _play(self, pcm: np.ndarray) -> None:
        with self._playback_lock:
            if self._stop_event.is_set():
                return
            try:
                sd.play(pcm, samplerate=self.sample_rate, blocking=False)
                # Poll for completion, but bail fast on stop.
                duration = len(pcm) / self.sample_rate
                deadline = time.monotonic() + duration + 0.5
                while time.monotonic() < deadline:
                    if self._stop_event.is_set():
                        sd.stop()
                        return
                    try:
                        if not sd.get_stream().active:
                            return
                    except Exception:
                        return
                    time.sleep(0.02)
            except Exception as e:
                logger.warning("Playback error: %s", e)
