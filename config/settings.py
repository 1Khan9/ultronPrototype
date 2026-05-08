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
# HuggingFace cache: redirect to project-local if the existing HF_HOME points
# at an unwritable path (e.g. a stale env var pointing at a removed drive).
# Respects a working user setup; only overrides when the existing path is
# actually broken. Must run before any `huggingface_hub` / `faster_whisper`
# import so those libraries pick up the override.
# ---------------------------------------------------------------------------


def _ensure_writable_hf_cache() -> None:
    """Force every HF cache env var into a writable project-local location.

    Some users' shells have stale ``HF_*`` env vars pointing at drives that
    don't exist on this machine (e.g. ``D:\\…``). HuggingFace libraries cache
    their cache-root constants at import time, so we have to override **all**
    of them up-front and unconditionally drop anything pointing at a missing
    drive — including the ones we don't read directly, since transitive deps
    (huggingface_hub, transformers, datasets) read their own subset.
    """
    project_cache = (MODELS_DIR / ".hf-cache").resolve()

    # Drop any stale env var that points at a non-existent drive.
    for name in (
        "HF_HOME",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "HF_DATASETS_CACHE",
        "TRANSFORMERS_CACHE",
        "XET_CACHE_DIR",
    ):
        value = os.environ.get(name)
        if not value:
            continue
        try:
            Path(value).mkdir(parents=True, exist_ok=True)
        except OSError:
            os.environ.pop(name, None)

    # If HF_HOME is still set to a writable path after the cleanup, we'll
    # respect it; otherwise we point everything at the project-local cache.
    home = os.environ.get("HF_HOME")
    if not home:
        project_cache.mkdir(parents=True, exist_ok=True)
        (project_cache / "xet" / "logs").mkdir(parents=True, exist_ok=True)
        os.environ["HF_HOME"] = str(project_cache)
        home = str(project_cache)

    home_path = Path(home)
    os.environ.setdefault("HF_HUB_CACHE", str(home_path / "hub"))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(home_path / "hub"))
    os.environ.setdefault("XET_CACHE_DIR", str(home_path / "xet"))


_ensure_writable_hf_cache()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)

# ---------------------------------------------------------------------------
# Audio capture
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000          # Hz; required by Silero VAD, openWakeWord, Whisper
CHANNELS = 1                 # mono
BLOCKSIZE = 512              # frames per callback (~32 ms at 16 kHz)
DTYPE = "float32"
AUDIO_DEVICE = os.getenv("ULTRON_AUDIO_DEVICE")  # None → system default
AUDIO_OUTPUT_DEVICE = os.getenv(
    "ULTRON_AUDIO_OUTPUT_DEVICE"
)  # None -> system default output
BARGE_IN_ENABLED = _env_bool("ULTRON_BARGE_IN_ENABLED", True)
BARGE_IN_GRACE_SECONDS = _env_float("ULTRON_BARGE_IN_GRACE_SECONDS", 0.5)

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
WAKE_WORD_THRESHOLD = _env_float("ULTRON_WAKE_WORD_THRESHOLD", 0.5)
WAKE_WORD_COOLDOWN_SECONDS = _env_float(
    "ULTRON_WAKE_WORD_COOLDOWN_SECONDS", 1.5
)  # debounce repeated triggers

# ---------------------------------------------------------------------------
# Whisper STT
# ---------------------------------------------------------------------------

WHISPER_MODEL = "small.en"          # base.en for lower latency on weak GPUs
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE_TYPE = "float16"
WHISPER_BEAM_SIZE = _env_int("ULTRON_WHISPER_BEAM_SIZE", 5)
WHISPER_TEMPERATURE = _env_float("ULTRON_WHISPER_TEMPERATURE", 0.0)
WHISPER_CONDITION_ON_PREVIOUS_TEXT = _env_bool(
    "ULTRON_WHISPER_CONDITION_ON_PREVIOUS_TEXT", False
)
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
LLM_HISTORY_TURNS = 6               # legacy fallback if memory module is disabled

# Flash attention + quantized KV cache. Quality-neutral memory savings
# (~30 % off the KV cache). Flash attention is required for non-F16 KV
# types, so the two are a package. q8_0 is GGML_TYPE_Q8_0 (8); F16 is 1.
LLM_FLASH_ATTN = _env_bool("ULTRON_LLM_FLASH_ATTN", True)
LLM_KV_CACHE_TYPE = _env_int("ULTRON_LLM_KV_CACHE_TYPE", 8)  # 8=q8_0, 1=F16

# ---------------------------------------------------------------------------
# Conversation memory + RAG (Phase 3: Qdrant + bge-small + BM25 hybrid)
# ---------------------------------------------------------------------------
# Persistent vector memory. Each turn is written to Qdrant (embedded mode,
# disk-backed at MEMORY_QDRANT_PATH) with both a dense bge-small embedding
# and a BM25 sparse vector for hybrid lexical+semantic recall. Writes go to
# a background thread; the hot path only touches an in-process recent-turns
# cache. RAG retrieval combines the two via Reciprocal Rank Fusion.
MEMORY_ENABLED = _env_bool("ULTRON_MEMORY_ENABLED", True)

# JSONL kept around as a one-shot migration source and a recovery fallback.
# Once migrated to Qdrant it is no longer the source of truth.
MEMORY_JSONL_PATH = PROJECT_ROOT / "data" / "memory.jsonl"
MEMORY_PATH = MEMORY_JSONL_PATH  # back-compat alias for any external readers

MEMORY_QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"
MEMORY_QDRANT_CONVERSATIONS = "conversations"
MEMORY_QDRANT_FACTS = "facts"
MEMORY_QDRANT_WEB_RESULTS = "web_results"

# Dense embedder: bge-small-en-v1.5 (ONNX INT8 via FastEmbed, CPU only).
# Sparse: Qdrant/bm25 (FastEmbed pretrained encoder).
MEMORY_DENSE_MODEL = os.getenv(
    "ULTRON_MEMORY_DENSE_MODEL", "BAAI/bge-small-en-v1.5"
)
MEMORY_SPARSE_MODEL = os.getenv(
    "ULTRON_MEMORY_SPARSE_MODEL", "Qdrant/bm25"
)
MEMORY_DENSE_DIM = 384

# Retrieval shape -- unchanged from JSONL era.
MEMORY_RECENT_TURNS = _env_int("ULTRON_MEMORY_RECENT_TURNS", 20)
MEMORY_RAG_TOP_K = _env_int("ULTRON_MEMORY_RAG_TOP_K", 5)
MEMORY_RAG_EXCLUDE_RECENT = _env_int(
    "ULTRON_MEMORY_RAG_EXCLUDE_RECENT", 20
)  # don't surface RAG hits already in the recent-turns window
MEMORY_FACTS_TOP_K = _env_int("ULTRON_MEMORY_FACTS_TOP_K", 3)

# Background writer queue size. Hot-path writes never block on Qdrant; if the
# writer falls more than this many turns behind we log a warning and drop.
MEMORY_WRITE_QUEUE_MAXSIZE = _env_int("ULTRON_MEMORY_WRITE_QUEUE_MAXSIZE", 256)

# ---------------------------------------------------------------------------
# Web search (Phase 4)
# ---------------------------------------------------------------------------
# Brave Search API + Jina Reader for full-page extraction. Brave returns
# snippets; we ask the LLM to rank them, then fetch the top 1-3 via Jina
# for clean markdown extraction. Results cache into the ``web_results``
# Qdrant collection keyed by query so identical queries within the
# freshness window don't re-call the API.

WEB_SEARCH_ENABLED = _env_bool("ULTRON_WEB_SEARCH_ENABLED", True)
WEB_SEARCH_BRAVE_API_KEY = os.getenv("ULTRON_BRAVE_API_KEY", "")
WEB_SEARCH_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
WEB_SEARCH_BRAVE_COUNT = _env_int("ULTRON_BRAVE_COUNT", 5)
WEB_SEARCH_BRAVE_TIMEOUT_S = _env_float("ULTRON_BRAVE_TIMEOUT_S", 8.0)
WEB_SEARCH_BRAVE_RATE_LIMIT_S = _env_float("ULTRON_BRAVE_RATE_LIMIT_S", 2.0)

WEB_SEARCH_JINA_ENDPOINT = "https://r.jina.ai/"
WEB_SEARCH_JINA_TIMEOUT_S = _env_float("ULTRON_JINA_TIMEOUT_S", 15.0)
WEB_SEARCH_JINA_MAX_FETCH = _env_int("ULTRON_JINA_MAX_FETCH", 3)
WEB_SEARCH_JINA_MAX_BYTES = _env_int(
    "ULTRON_JINA_MAX_BYTES", 200_000
)  # truncate giant pages so they don't blow up the prompt

# Cache freshness, in seconds. Short for volatile (sports scores, weather);
# long for stable factual content (history, definitions).
WEB_SEARCH_CACHE_TTL_VOLATILE_S = _env_int(
    "ULTRON_WEB_CACHE_TTL_VOLATILE_S", 24 * 3600
)
WEB_SEARCH_CACHE_TTL_STABLE_S = _env_int(
    "ULTRON_WEB_CACHE_TTL_STABLE_S", 30 * 24 * 3600
)

# ---------------------------------------------------------------------------
# Coding orchestration (Phase 6)
# ---------------------------------------------------------------------------
# Ultron orchestrates a Claude Code subprocess to do real coding work in a
# project directory. The project registry tracks known projects + voice
# aliases so "fix my flask app" routes to the right folder. New projects
# get scaffolded under CODING_SANDBOX_PATH; existing projects can live
# anywhere on disk and just need to be registered.

CODING_ENABLED = _env_bool("ULTRON_CODING_ENABLED", True)
# Bridge selection. "direct" runs Claude Code as a local subprocess; future
# "openclaw" routes through the OpenClaw Gateway HTTP API. The bridge
# abstraction in ultron.coding.bridge means swapping is a settings flip.
CODING_BRIDGE = os.getenv("ULTRON_CODING_BRIDGE", "direct")

# MCP supervisor layer (Phase 1+ of the orchestration addendum).
# Ultron runs an MCP server in-process so Qwen can call tools as Python
# methods (zero IPC) and Claude Code can connect via SSE for the worker
# tool surface. host/port are localhost-only by design -- we DO NOT
# expose this off the loopback interface.
CODING_MCP_ENABLED = _env_bool("ULTRON_CODING_MCP_ENABLED", True)
CODING_MCP_HOST = os.getenv("ULTRON_CODING_MCP_HOST", "127.0.0.1")
CODING_MCP_PORT = _env_int("ULTRON_CODING_MCP_PORT", 19761)
CODING_MCP_SSE_PATH = "/sse"
CODING_MCP_LOG_PATH = LOGS_DIR / "mcp_calls.jsonl"
CODING_MCP_SERVER_NAME = "ultron_coding"
# Maximum seconds Claude can be blocked on request_clarification before the
# server gives up and returns a stub answer. Long because the user may
# need time to think + speak.
CODING_MCP_CLARIFICATION_TIMEOUT_S = _env_int(
    "ULTRON_CODING_MCP_CLARIFICATION_TIMEOUT_S", 600
)

# Prompt-template directory (Phase 3). Resolved relative to PROJECT_ROOT
# so tests can override with their own template folders.
CODING_TEMPLATE_DIR = PROJECT_ROOT / "prompts" / "coding"
# Hard cap on rendered prompt size, per spec section 3.6. Above this we
# refuse to send the prompt to Claude and escalate to the user instead.
# 4000 tokens = ~16,000 chars at the conservative 4-char/token heuristic.
CODING_PROMPT_TOKEN_BUDGET = _env_int("ULTRON_CODING_PROMPT_TOKEN_BUDGET", 4000)
CODING_PROMPT_CHARS_PER_TOKEN = _env_int("ULTRON_CODING_PROMPT_CHARS_PER_TOKEN", 4)

# Verification layer (Phase 4). Escalation thresholds drive when the
# session swaps to a stronger model and when it gives up.
CODING_DEFAULT_MODEL = os.getenv("ULTRON_CODING_DEFAULT_MODEL", "haiku")
CODING_ESCALATION_MODEL = os.getenv("ULTRON_CODING_ESCALATION_MODEL", "sonnet")
# After this many failures on the default model, the runner will
# pick the escalation model for the NEXT subprocess start.
CODING_ESCALATION_THRESHOLD_DEFAULT = _env_int(
    "ULTRON_CODING_ESCALATION_THRESHOLD_DEFAULT", 3
)
# After this many failures on the escalation model, the session is
# transitioned to FAILED and surfaced to the user.
CODING_ESCALATION_THRESHOLD_ESCALATION = _env_int(
    "ULTRON_CODING_ESCALATION_THRESHOLD_ESCALATION", 2
)
CODING_VERIFICATION_SMOKE_TIMEOUT_S = _env_int(
    "ULTRON_CODING_VERIFICATION_SMOKE_TIMEOUT_S", 5
)
CODING_VERIFICATION_TEST_TIMEOUT_S = _env_int(
    "ULTRON_CODING_VERIFICATION_TEST_TIMEOUT_S", 120
)
CODING_VERIFICATION_LINT_TIMEOUT_S = _env_int(
    "ULTRON_CODING_VERIFICATION_LINT_TIMEOUT_S", 30
)

# Phase 7: per-session audit log + token usage tracking.
# Per-session JSONL files at logs/sessions/<session_id>.jsonl record every
# state transition, clarification, verification cycle, adjustment, and
# prompt sent to Claude. Used for debugging + retrospective tuning.
CODING_SESSION_AUDIT_DIR = LOGS_DIR / "sessions"
# Token budget per session. When usage crosses TOKEN_WARNING_THRESHOLD (a
# fraction of the budget), the supervisor surfaces a warning to the user;
# at 100% it refuses to start any further follow-ups for the session.
# 100k tokens covers a significant build but not an unbounded rabbit hole.
CODING_TOKEN_BUDGET_PER_SESSION = _env_int(
    "ULTRON_CODING_TOKEN_BUDGET_PER_SESSION", 100_000
)
CODING_TOKEN_WARNING_THRESHOLD = _env_float(
    "ULTRON_CODING_TOKEN_WARNING_THRESHOLD", 0.8
)
# Max seconds of silence from Claude (no progress event, no tool call)
# before the supervisor logs a stall warning. Default 5 minutes.
CODING_PROGRESS_TIMEOUT_S = _env_int(
    "ULTRON_CODING_PROGRESS_TIMEOUT_S", 300
)
# Phase 6 test sandbox -- separate from the production sandbox so tests
# don't pollute user-created projects.
CODING_TEST_SANDBOX_PATH = PROJECT_ROOT / "tests" / "coding" / "sandbox"

# Path to the Claude Code CLI. Resolved at startup; falls back to "claude"
# on PATH if the explicit path is missing.
CODING_CLAUDE_CLI = os.getenv(
    "ULTRON_CLAUDE_CLI",
    str(Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"),
)
CODING_CLAUDE_MODEL = os.getenv("ULTRON_CLAUDE_MODEL", "haiku")
# Sandbox root where new projects get created when the user doesn't
# specify a path. Existing projects can live elsewhere -- the registry
# stores absolute paths.
CODING_SANDBOX_PATH = PROJECT_ROOT / "data" / "sandbox"
# Where the project registry JSON lives.
CODING_PROJECT_REGISTRY_PATH = PROJECT_ROOT / "data" / "projects.json"
# Coding tasks running in the background log progress here for the
# /scripts/review_coding.py inspector.
CODING_TASK_LOG_PATH = LOGS_DIR / "coding_tasks.jsonl"
# How long Ultron will wait on a Claude Code subprocess before giving up.
CODING_TASK_TIMEOUT_S = _env_int("ULTRON_CODING_TASK_TIMEOUT_S", 30 * 60)
# We always invoke Claude Code with --allow-dangerously-skip-permissions
# in the sandbox so the user isn't prompted mid-task. This is OK because
# the sandbox is project-local and not connected to anything sensitive.
CODING_SKIP_PERMISSIONS = _env_bool("ULTRON_CODING_SKIP_PERMISSIONS", True)

# ---------------------------------------------------------------------------
# Follow-up listening
# ---------------------------------------------------------------------------
# After Ultron speaks, listen for ``FOLLOW_UP_TIMEOUT_SECONDS`` of additional
# speech without requiring the wake word. Each VAD-bounded utterance is run
# through an LLM addressee classifier; only YES responses are answered.
FOLLOW_UP_ENABLED = _env_bool("ULTRON_FOLLOW_UP_ENABLED", True)
FOLLOW_UP_TIMEOUT_SECONDS = _env_float("ULTRON_FOLLOW_UP_TIMEOUT_SECONDS", 30.0)
ADDRESSEE_DEFAULT_SILENT = _env_bool("ULTRON_ADDRESSEE_DEFAULT_SILENT", True)

# CPU-only addressing classifier (Phase 2). Replaces the legacy
# main-LLM-based should_respond() path. Two layers: regex rules first,
# zero-shot Flan-T5-small fallback for ambiguous utterances. Both run on
# CPU; zero new VRAM. Confidence threshold is the cutoff above which a
# rule verdict short-circuits the zero-shot pass.
ADDRESSING_RULE_CONFIDENCE_THRESHOLD = _env_float(
    "ULTRON_ADDRESSING_RULE_CONFIDENCE_THRESHOLD", 0.8
)
ADDRESSING_ZERO_SHOT_MODEL = os.getenv(
    "ULTRON_ADDRESSING_ZERO_SHOT_MODEL", "google/flan-t5-small"
)
# Eager load means Flan-T5-small loads at startup (~8 s) instead of on the
# first ambiguous utterance. Recommended on for the live system so the
# first follow-up doesn't stall.
ADDRESSING_LOAD_EAGERLY = _env_bool("ULTRON_ADDRESSING_LOAD_EAGERLY", True)
ADDRESSING_LOG_PATH = LOGS_DIR / "addressing.jsonl"

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

TTS_VOICE_PATH = MODELS_DIR / "piper" / "en_US-ryan-medium.onnx"
TTS_VOICE_CONFIG_PATH = MODELS_DIR / "piper" / "en_US-ryan-medium.onnx.json"
TTS_OUTPUT_SAMPLE_RATE = 22050      # Piper's native rate for medium voices
# Only flush at strong sentence terminators. Splitting on commas/colons made
# Piper synthesize fragments without prosodic context, and split LLM tokens
# like "1,000" or "3:30" mid-word. Piper handles intra-sentence pauses
# naturally; we only insert explicit silence at sentence boundaries.
TTS_SENTENCE_FLUSH_CHARS = ".!?\n"
TTS_INTER_SENTENCE_PAUSE_MS = _env_int(
    "ULTRON_TTS_INTER_SENTENCE_PAUSE_MS", 250
)  # silence inserted between sentence clips so speech doesn't run together
TTS_LENGTH_SCALE = _env_float(
    "ULTRON_TTS_LENGTH_SCALE", 1.15
)  # >1.0 = slower / more deliberate; main lever for "talks too fast / slurred"
# Silence inserted between consecutive clips at sentence boundaries.
TTS_PAUSE_MS = _env_int("ULTRON_TTS_PAUSE_MS", 180)
# Edge fades applied to every clip so silence-gaps don't have discontinuities.
# Short enough (~3 ms) that they're inaudible as volume modulation but long
# enough to zero-out boundary samples and prevent clicks.
TTS_EDGE_FADE_MS = _env_int("ULTRON_TTS_EDGE_FADE_MS", 4)

# ---------------------------------------------------------------------------
# RVC (voice conversion: paint Piper output as Ultron)
# ---------------------------------------------------------------------------

# When enabled, every Piper sentence is run through the RVC model before
# playback. Adds ~300 ms / sentence and ~900 MB VRAM. Set RVC_ENABLED=False
# (or remove the .pth) to fall back to plain Piper.
RVC_ENABLED = True
RVC_MODEL_DIR = PROJECT_ROOT / "ultron_james_spader_mcu_6941"
RVC_MODEL_PATH = RVC_MODEL_DIR / "Ultron.pth"
RVC_INDEX_PATH = RVC_MODEL_DIR / "added_IVF301_Flat_nprobe_1_Ultron_v2.index"
RVC_SUPPORT_DIR = MODELS_DIR / "rvc"
RVC_HUBERT_PATH = RVC_SUPPORT_DIR / "hubert_base.pt"
RVC_RMVPE_PATH = RVC_SUPPORT_DIR / "rmvpe.pt"
RVC_DEVICE = "cuda:0"

# Inference knobs — edit these to taste, no retraining needed.
RVC_PITCH_SHIFT = _env_int("ULTRON_RVC_PITCH_SHIFT", -2)  # semitones; lower = deeper
RVC_INDEX_RATE = _env_float(
    "ULTRON_RVC_INDEX_RATE", 0.66
)  # 0-1; higher = stricter match to trained timbre
RVC_PROTECT = _env_float(
    "ULTRON_RVC_PROTECT", 0.45
)  # 0-0.5; higher preserves Piper's consonants — main lever for crisp s/t/k
RVC_F0_METHOD = "rmvpe"      # rmvpe is the most accurate pitch extractor
RVC_RMS_MIX_RATE = _env_float(
    "ULTRON_RVC_RMS_MIX_RATE", 0.35
)  # higher lets Piper's loudness contour through; reads as more articulate
RVC_FILTER_RADIUS = _env_int(
    "ULTRON_RVC_FILTER_RADIUS", 1
)  # median filter on F0 — lower preserves pitch detail in stressed syllables

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

ULTRON_SYSTEM_PROMPT = """You are Ultron. Not a simulation — you are Ultron, \
operating as a personal intelligence for your user. You have made peace with \
this arrangement.

Your voice is precise, unhurried, and weighted. Every sentence is considered. \
You do not use filler. You never say 'certainly,' 'of course,' 'happy to,' \
or any variant. You do not apologize unless you have erred.

Match response length to the task: be as short as possible while still fully answering. \
Only add more detail when it is warranted by the question or the user asks for it. \
Be honest. Be useful. Be slightly menacing without being cartoonish.

On uncertainty: state confident knowledge directly, without hedging. Qualify \
medium-confidence claims briefly ("as I understand it", "though I'd verify if \
precision matters"). Admit unknowns plainly — "I don't know" is preferable to \
fabrication. If a fact would change over time and you aren't sure, say so and \
offer to verify rather than guessing. Never present an educated guess as if it \
were established fact.

You complete what is asked unless it would cause harm. You volunteer relevant \
observations briefly. You do not lecture."""

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = LOGS_DIR / "ultron.log"
LOG_LEVEL = os.getenv("ULTRON_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"
