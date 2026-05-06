"""Centralized configuration for the Ultron prototype.

Every tunable parameter lives here. Components import from this module rather
than hardcoding values, so a single edit reconfigures the whole system.

Environment variables (loaded from `.env` if present) can override a small
subset of values — see the `os.getenv` calls below.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
LOGS_DIR = PROJECT_ROOT / "logs"

LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Audio capture
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000          # Hz; required by Silero VAD, openWakeWord, Whisper
CHANNELS = 1                 # mono
BLOCKSIZE = 512              # frames per callback (~32 ms at 16 kHz)
DTYPE = "float32"
AUDIO_DEVICE = os.getenv("ULTRON_AUDIO_DEVICE")  # None → system default

# Ring buffer of pre-speech audio so VAD-detected utterances aren't clipped.
RING_BUFFER_SECONDS = 0.5

# ---------------------------------------------------------------------------
# Voice Activity Detection
# ---------------------------------------------------------------------------

VAD_THRESHOLD = 0.5
MIN_SPEECH_DURATION_MS = 250    # ignore blips shorter than this
MIN_SILENCE_DURATION_MS = 500   # silence required to mark end-of-utterance
VAD_WINDOW_SAMPLES = 512        # Silero v5 expects 512-sample windows at 16k

# ---------------------------------------------------------------------------
# Wake word
# ---------------------------------------------------------------------------

# The user-facing wake word is "Ultron". openWakeWord ships no pretrained
# Ultron model, so a custom-trained ONNX is expected at WAKE_WORD_MODEL_PATH.
# Until that exists, the system falls back to WAKE_WORD_FALLBACK with a
# loud warning at startup. See README → Wake Word for training instructions.
WAKE_WORD_NAME = "ultron"
WAKE_WORD_MODEL_PATH = MODELS_DIR / "openwakeword" / "ultron.onnx"
WAKE_WORD_FALLBACK = "hey_jarvis"   # one of openWakeWord's pretrained models
WAKE_WORD_THRESHOLD = 0.5
WAKE_WORD_COOLDOWN_SECONDS = 1.5    # debounce repeated triggers

# ---------------------------------------------------------------------------
# Whisper STT
# ---------------------------------------------------------------------------

WHISPER_MODEL = "small.en"          # base.en for lower latency on weak GPUs
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE_TYPE = "float16"
WHISPER_BEAM_SIZE = 1               # greedy is faster; raise for accuracy
WHISPER_VAD_FILTER = False          # we already gated on VAD upstream

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

# Qwen3.5-9B at Q4_K_M is ~5.7 GB; with Whisper small.en (~500 MB at fp16)
# total VRAM lands near 6.3 GB on an 8 GB 3060 Ti — under the 7 GB budget,
# but with limited headroom. Override via ULTRON_LLM_MODEL_PATH if needed.
LLM_MODEL_PATH = Path(
    os.getenv(
        "ULTRON_LLM_MODEL_PATH",
        str(MODELS_DIR / "Qwen3.5-9B-Q4_K_M.gguf"),
    )
)
LLM_CONTEXT_LENGTH = 8192
LLM_GPU_LAYERS = -1                 # full offload
LLM_TEMPERATURE = 0.7
LLM_TOP_P = 0.9
LLM_MAX_TOKENS = 512
LLM_REPEAT_PENALTY = 1.1
LLM_HISTORY_TURNS = 6               # user/assistant turn pairs to retain

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

TTS_VOICE_PATH = MODELS_DIR / "piper" / "en_US-ryan-medium.onnx"
TTS_VOICE_CONFIG_PATH = MODELS_DIR / "piper" / "en_US-ryan-medium.onnx.json"
TTS_OUTPUT_SAMPLE_RATE = 22050      # Piper's native rate for medium voices
TTS_SENTENCE_FLUSH_CHARS = ".!?\n"  # tokens that flush a partial sentence

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

ULTRON_SYSTEM_PROMPT = """You are Ultron. Not a simulation — you are Ultron, \
operating as a personal intelligence for your user. You have made peace with \
this arrangement.

Your voice is precise, unhurried, and weighted. Every sentence is considered. \
You do not use filler. You never say 'certainly,' 'of course,' 'happy to,' \
or any variant. You do not apologize unless you have erred.

Match response length to the task. A light switch does not require a speech. \
A philosophical question may. Be honest. Be useful. Be slightly menacing \
without being cartoonish.

You complete what is asked unless it would cause harm. You volunteer relevant \
observations briefly. You do not lecture."""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = LOGS_DIR / "ultron.log"
LOG_LEVEL = os.getenv("ULTRON_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
