# Ultron architecture


> **Currency note (2026-05-22):** this document is a historical snapshot.
> For the **current** state (DualSTTRegistry, Kokoro TTS, qwen3.5-4b,
> intent recognizer, supervisor stack, news-category SearxNG routing,
> gaming-mode VRAM reclaim, event bus, OPEN_LAST_SOURCE / NAVIGATE_TO_SITE
> intents, etc.), see [`codebase_structure.md`](codebase_structure.md)
> which is kept current via the binding maintenance contract. The
> high-level shape and intent here are still accurate; specific subsystem
> identities and per-knob defaults have evolved.

System overview, pipeline shape, subsystem boundaries, on-disk layout.
Snapshot at the close of the Foundation phase.

## Hardware target

| Component | Spec |
|---|---|
| GPU | NVIDIA RTX 4070 Ti (12 GB) |
| CPU | AMD Ryzen 7 5800X |
| RAM | 32+ GB |
| OS | Windows 11 |

VRAM budget: peak ~10.4 GB observed under load (voice stack: Qwen + Whisper + RVC + Piper + addressing classifier). Hard cap 11.5 GB. See [baselines.json](../baselines.json) for the per-component breakdown.

## Pipeline (default conversational path)

```
┌─────────┐
│  mic    │ ───── 16 kHz mono ─────┐
└─────────┘                        ▼
                   ┌────────────────────────┐
                   │   AudioCapture +       │  audio thread, 32 ms callbacks
                   │   RingBuffer           │  pre-speech kept so first word isn't clipped
                   └────────────┬───────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
       ┌─────────────┐    ┌──────────────┐  ┌────────────┐
       │ openWakeWord│    │   Silero VAD  │  │ Addressing │  WARM mode follow-up
       │ "ultron"    │    │   start/end   │  │ classifier │  (rule-based + flan-t5-small CPU)
       └──────┬──────┘    └──────┬───────┘  └─────┬──────┘
              │ wake fires       │ end-of-speech   │ NOT_ADDRESSED → drop
              ▼                  │                 ▼ ADDRESSED → continue
       ┌──────────────────────────┐
       │   Whisper (faster-whisper)│  CUDA, small.en, fp16, beam=5
       └──────────────┬───────────┘
                      ▼
                  user_text
                      │
                      ▼
       ┌──────────────────────────┐
       │ classify_routing(...)     │  Phase 5 — top-level intent dispatch
       │  (rule-based; LLM         │
       │   disambiguation fallback)│
       └──────────────┬───────────┘
                      ▼
   ┌──────────┬───────┴────────────┬─────────────┐
   ▼          ▼                    ▼             ▼
 CODE_TASK  CONVERSATIONAL   AUTOMATION       HYBRID_TASK
   │          │              (browser /         │
   │          │               media /           │  HybridTaskDecomposer
   │          │               messaging /       │  splits into subtasks
   │          │               file / shell)     │  (currently stubbed)
   │          │                    │             │
   │          ▼                    ▼             ▼
   │  ┌─────────────┐  ┌─────────────────┐  ┌────────────┐
   │  │ Pre-flight  │  │ OpenClawDispatch│  │ subtasks → │
   │  │ uncertainty │  │ (currently      │  │ each handler│
   │  │ + RAG       │  │  STUBBED →      │  └────────────┘
   │  │ retrieval   │  │  voice msg)     │
   │  └──────┬──────┘  └────────┬────────┘
   │         │                  │
   │         ▼                  ▼
   │  ┌─────────────────────────────────┐
   │  │ Voice path: LLM stream → Piper  │
   │  │ TTS → RVC → audio device        │
   │  └─────────────────────────────────┘
   ▼
┌─────────────────────────┐
│ CodingTaskRunner        │ submits to bridge
│ (DirectClaudeCodeBridge)│ → claude --print --stream-json
└─────────┬───────────────┘
          │ TaskEvent stream
          ▼
┌─────────────────────────┐
│ ConversationCoordinator │ verification + corrective loop
│ + StatusNarrator        │ + Haiku→Sonnet escalation
└─────────────────────────┘
```

## Mode state machine (orchestrator main loop)

```
              ┌─────────┐
   start ───▶ │  IDLE   │
              └────┬────┘
                   │  wake word fires
                   ▼
              ┌────────────┐
              │ CAPTURING  │  VAD-bounded utterance capture
              └────┬───────┘
                   │  end-of-speech
                   ▼
              ┌────────────┐
              │ PROCESSING │  Whisper → routing → handler → TTS
              └────┬───────┘
                   │  TTS done
                   ▼
              ┌──────────────────────┐
              │ FOLLOW_UP_LISTENING  │  30 s (NOT 10s) per user override
              │  (no wake word req'd)│  addressing classifier on every utt
              └────┬─────────────────┘
                   │
        ┌──────────┼──────────────────┐
        ▼          ▼                  ▼
   timeout    addressed         not addressed
   (30 s)     utterance         (drop, stay in
        │          │             follow-up)
        ▼          ▼
      IDLE     CAPTURING
```

## Subsystems and where they live

| Subsystem | Module | Single source of truth (config.yaml) |
|---|---|---|
| Audio capture | [src/ultron/audio/](../src/ultron/audio/) | `audio:` |
| VAD | [src/ultron/audio/vad.py](../src/ultron/audio/vad.py) | `vad:` |
| Wake word | [src/ultron/audio/wake_word.py](../src/ultron/audio/wake_word.py) | `wake_word:` |
| Addressing classifier | [src/ultron/addressing/](../src/ultron/addressing/) | `addressing:` |
| Whisper STT | [src/ultron/transcription/whisper_engine.py](../src/ultron/transcription/whisper_engine.py) | `stt:` |
| LLM (llama-cpp-python) | [src/ultron/llm/inference.py](../src/ultron/llm/inference.py) | `llm:` |
| Embeddings (FastEmbed) | [src/ultron/memory/embedder.py](../src/ultron/memory/embedder.py) | `embeddings:` |
| Qdrant memory | [src/ultron/memory/qdrant_store.py](../src/ultron/memory/qdrant_store.py) | `qdrant:` + `memory:` |
| Web search | [src/ultron/web_search/](../src/ultron/web_search/) | `web_search:` |
| Uncertainty signals | [src/ultron/uncertainty.py](../src/ultron/uncertainty.py) | (no config; output of preflight gate) |
| TTS (Piper) | [src/ultron/tts/speech.py](../src/ultron/tts/speech.py) | `tts:` |
| RVC voice conversion | [src/ultron/tts/rvc.py](../src/ultron/tts/rvc.py) | `tts.rvc:` |
| Coding orchestration (Phase A + Coding Addendum) | [src/ultron/coding/](../src/ultron/coding/) | `coding:` |
| Context projections (Phase C / Foundation Part 2) | [src/ultron/coding/projections.py](../src/ultron/coding/projections.py) | `projections:` |
| Capability routing (Foundation Part 5) | [src/ultron/openclaw_routing/](../src/ultron/openclaw_routing/) | `routing:` + `openclaw:` |
| Errors + circuit breakers (Foundation Part 4) | [src/ultron/errors.py](../src/ultron/errors.py), [src/ultron/resilience/](../src/ultron/resilience/) | `error_phrases:` |
| Logging | [src/ultron/utils/logging.py](../src/ultron/utils/logging.py) | `logging:` |
| Orchestrator (main loop) | [src/ultron/pipeline/orchestrator.py](../src/ultron/pipeline/orchestrator.py) | n/a (composition root) |

## Configuration

Single source of truth: [config.yaml](../config.yaml) at the project root. Loaded + validated by [src/ultron/config.py](../src/ultron/config.py) (pydantic schema with `extra="forbid"`).

A thin compatibility shim at [config/settings.py](../config/settings.py) re-exports legacy `settings.X` constants from `get_config()`. Subsystem migration to direct `get_config()` reads is partial; remaining work is tracked in [docs/phase3_5_followup.md](phase3_5_followup.md).

Full config reference: [docs/configuration.md](configuration.md).

## On-disk layout

```
<repo root>/
  config.yaml              ← canonical config
  baselines.json           ← perf baselines (per-phase nested)
  README.md
  pyproject.toml

  src/ultron/              ← source
    audio/  addressing/  coding/  llm/  memory/
    pipeline/  tts/  transcription/  utils/
    web_search/  openclaw_routing/  resilience/
    config.py  errors.py  uncertainty.py
  config/                  ← compat shim
    settings.py

  models/                  ← all loaded models (NOT in worktrees; only in main checkout)
    Qwen3.5-9B-Q4_K_M.gguf      ← LLM
    openwakeword/ultron.onnx    ← custom wake word
    piper/en_US-ryan-medium.onnx ← TTS voice
    rvc/{hubert_base.pt,rmvpe.pt} ← RVC support files
  ultron_james_spader_mcu_6941/ ← RVC voice model
    Ultron.pth, added_IVF301_…_Ultron_v2.index

  data/
    qdrant/                ← embedded Qdrant store (3 collections)
    memory.jsonl           ← legacy/recovery turn log
    projects.json          ← coding project registry
    sandbox/               ← auto-created coding projects
    summaries.jsonl        ← maintenance summaries
    maintenance.sqlite     ← maintenance state

  logs/
    ultron.log             ← main log (rotating)
    addressing.jsonl       ← classifier audit
    coding_tasks.jsonl     ← coding task progress
    verifications.jsonl    ← verifier runs
    clarifications.jsonl   ← clarification decisions
    mcp_calls.jsonl        ← MCP tool calls
    sessions/<id>.jsonl    ← per-session coding audit
    errors.jsonl           ← Phase 4 typed errors
    routing_decisions.jsonl ← Phase 5 routing audit
    automation_tasks.jsonl  ← Phase 5 OpenClaw task audit

  docs/                    ← all .md docs
  tests/                   ← test suites
  scripts/                 ← operational scripts
  prompts/coding/          ← Jinja templates for Claude prompts
```

The `models/` directory and the RVC voice model live in the main
checkout (`C:\STC\ultronPrototype\`). Worktrees share the same venv but
do not duplicate model files — heavy measurement work runs in the main
checkout.

## Voice path latency budget

| Stage | Median | Notes |
|---|---|---|
| End-of-speech detection (VAD) | 500 ms (config) | trailing silence required |
| Whisper transcription (2.5 s utterance) | 109 ms | small.en, fp16, CUDA |
| LLM TTFT (post-prompt-submit) | 125 ms | Qwen3.5-9B Q4 with flash-attn + q8_0 KV |
| Piper synth (first sentence) | 508 ms | RVC adds ~300 ms / sentence |
| RVC inference per sentence | ~300 ms | rmvpe pitch, cuda:0 |
| **Composite TTFA estimate** | **~742 ms** | end-of-speech to first audible word |

Numbers from [baselines.json](../baselines.json) → `phase_foundation_start.latency_ms.aggregate`. Refresh via [scripts/measure_baseline.py](../scripts/measure_baseline.py) or [scripts/measure_baseline_extended.py](../scripts/measure_baseline_extended.py).

## Logging conventions

- **DEBUG** — diagnostic detail (token counts, per-call timings, internal state). Off by default; enable via `ULTRON_LOG_LEVEL=DEBUG`.
- **INFO** — normal operation (component init, query received, response sent, projection truncations applied).
- **WARN** — unexpected but handled (Brave returned 429, Jina timed out, RVC failed → fell back to Piper, projection landed near budget cap).
- **ERROR** — unhandled failure or recovery required (LLM model missing, Qdrant search failed, projection over budget after exhaustive trim).

## Error handling shape

Every external dependency has a typed exception class. See [docs/error_handling.md](error_handling.md) for the per-dependency catalog. Brave and Jina are protected by per-process circuit breakers; in-process dependencies (Qdrant, Whisper, Piper, RVC, addressing classifier) get typed errors + structured `logs/errors.jsonl` entries but no breakers.

## Capability routing (Phase 5)

The `classify_routing` layer ([src/ultron/openclaw_routing/classifier.py](../src/ultron/openclaw_routing/classifier.py)) classifies utterances into 12 kinds and dispatches via `CapabilityVoiceController.handle_capability_intent`. OpenClaw-bound kinds (browser / media / messaging / file / shell / hybrid) currently return in-character stub messages because the OpenClaw Gateway integration prompt hasn't run yet. Conversational utterances pass through; coding utterances delegate to the existing `CodingTaskRunner`.

See [docs/routing.md](routing.md) for the full architecture.

## What this phase changed

The Foundation phase (Parts 0-7) added or consolidated:

| Part | Change |
|---|---|
| 0 | Baseline measurements + extended measurements (search VRAM, coding-session VRAM, scenario timing, TTA microbench) |
| 1 | [docs/system_inventory.md](system_inventory.md) — per-component inventory |
| 2 | Verified the context projection refactor at HEAD `4ecc7ec`; added `truncation_warning` field + INFO/ERROR logging via `_finalize_projection` |
| 3 | Unified config.yaml + pydantic loader + per-subsystem migration (partial — see [phase3_5_followup.md](phase3_5_followup.md)) |
| 4 | Typed error hierarchy + circuit breakers + `logs/errors.jsonl` + voice-character error phrases + 52 error-recovery tests |
| 5 | Capability routing layer (`ultron.openclaw_routing`) + `CapabilityVoiceController` rename with backward-compat alias + 148 routing tests |
| 6 | Orchestrator wired to call `classify_routing` + 83 integration tests + [tests/integration/mocks.md](../tests/integration/mocks.md) + [tests/integration/performance.json](../tests/integration/performance.json) |
| 7 | Code-quality sweep, 4 new operational scripts, this doc + operations.md + development.md, README refresh |
