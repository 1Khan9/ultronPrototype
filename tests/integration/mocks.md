# Integration test mock setup

Phase 6 integration tests use a layered approach:
in-process mocks for fast deterministic tests; PYTEST_RUN_GPU_TESTS=1
gates for the slower live-stack tests; and `scripts/measure_baseline_extended.py`
for performance benchmarking against real models.

## What's mocked vs. real

| Component | Default integration tests | `PYTEST_RUN_GPU_TESTS=1` tests | `measure_baseline_extended.py --full` |
|---|---|---|---|
| Whisper STT | mock (just feeds `user_text` directly to controller) | real | real |
| LLM (Qwen via llama-cpp) | `StubLLM` returning canned strings | real | real |
| Piper TTS | not exercised | real | real |
| RVC | not exercised | real | real |
| Qdrant memory | not loaded; `memory=None` on LLMEngine | embedded Qdrant | embedded Qdrant |
| Brave API | `_MockBrave` returns fixture rows | real (only if `ULTRON_BRAVE_API_KEY` set) | mocked (no metering) |
| Jina Reader | `_MockJina` returns canned markdown | real | mocked (no metering) |
| AI coding agent subprocess | `ScriptedClaudeBridge` (in-process worker thread) | real `claude` CLI subprocess | not exercised |
| MCP server | real `UltronMCPServer` (in-process; no SSE wire) | real with SSE | not exercised |

## Fixtures

[tests/integration/conftest.py](conftest.py) provides:

- **`stub_llm`** — `StubLLM` instance. Use `.push("response 1", "response 2")` for scripted replies.
- **`cap_stack`** — full `CapabilityVoiceController` wired against `UltronMCPServer` + `CodingTaskRunner` + a placeholder `ScriptedClaudeBridge`. Tests that need a real coding task swap in their own scripted bridge.
- **`errors_log` / `routing_log`** — tmp-path JSONL writers; replace the singletons for the test duration.
- **`read_errors` / `read_routing`** — helpers that parse the log files into dict lists.
- **`_reset_phrase_cache`** (autouse) — clears the error-phrase shuffle cache so each test gets a fresh cycle.
- **`_reset_external_breakers`** (autouse) — resets the Brave + Jina circuit breakers so a tripped breaker from one test doesn't leak.

## Helper

`tests.integration.conftest.dispatch_utterance(cap_stack, utterance)` mirrors the orchestrator's main-loop dispatch:

```python
routing_intent = classify_routing(
    utterance,
    has_active_coding_task=cap_stack.runner.has_active_task(),
    has_pending_clarification=cap_stack.voice.has_pending_clarification(),
)
return cap_stack.voice.handle_capability_intent(routing_intent)
```

This is the canonical way to exercise the orchestrator's voice path without bringing up audio/STT/TTS.

## Test categories (per Phase 6 spec)

| File | Category | Tests |
|---|---|---|
| [test_routing_dispatch.py](test_routing_dispatch.py) | 5 — Routing stub dispatch | 20 |
| [test_conversational_pipeline.py](test_conversational_pipeline.py) | 1 — Conversational | 21 |
| [test_search_pipeline.py](test_search_pipeline.py) | 2 — Search-triggering | 12 |
| [test_coding_pipeline.py](test_coding_pipeline.py) | 3 — Coding tasks | 9 |
| [test_addressing_pipeline.py](test_addressing_pipeline.py) | 4 — Addressing / WARM mode | 13 |
| [test_error_recovery_pipeline.py](test_error_recovery_pipeline.py) | 6 — Error recovery integration | 4 |

Total: 79 integration tests, all running in <2 s wall via mocks.

Plus the existing 52 tests in [tests/error_recovery/](../error_recovery/) covering per-dependency failure modes in isolation.

## Live-stack tests (opt-in)

The following test files exercise real models / metered services. They're gated on env vars so they don't run in the default suite:

| File | Gate | What it loads |
|---|---|---|
| [tests/test_llm.py](../test_llm.py) | `PYTEST_RUN_GPU_TESTS=1` | Real Qwen via llama-cpp-python |
| [tests/test_transcription.py](../test_transcription.py) | `PYTEST_RUN_GPU_TESTS=1` | Real Whisper |
| [tests/test_addressing.py::*_full_classifier_*` | `PYTEST_RUN_GPU_TESTS=1` | Real flan-t5-small |
| [tests/test_pipeline.py](../test_pipeline.py) | `PYTEST_RUN_GPU_TESTS=1` | Full orchestrator construction (no mic) |
| [tests/test_coding_e2e.py](../test_coding_e2e.py) | `PYTEST_RUN_GPU_TESTS=1` | Real `claude` CLI subprocess (metered Claude API) |
| [tests/test_mcp_e2e.py](../test_mcp_e2e.py) | `PYTEST_RUN_GPU_TESTS=1` | Real Claude → MCP SSE round-trip |
| [tests/coding/test_orchestration_real.py](../coding/test_orchestration_real.py) | `PYTEST_RUN_GPU_TESTS=1` | All 10 orchestration scenarios with real Claude |
| [tests/test_uncertainty.py::test_low_confidence_*](../test_uncertainty.py) | `PYTEST_RUN_GPU_TESTS=1` | Real LLM uncertainty signals |
| [tests/test_web_gating.py::test_preflight_*](../test_web_gating.py) | `PYTEST_RUN_GPU_TESTS=1` | Real LLM pre-flight gate |

Run with:
```
$env:PYTEST_RUN_GPU_TESTS = "1"
pytest tests/ -q
```

## Performance benchmarking

Performance numbers come from [scripts/measure_baseline_extended.py](../../scripts/measure_baseline_extended.py), not from tests. Run modes:

- `--lite` — CPU-only metrics: TTA microbench, scenario timing, composite TTFA. ~30s. Doesn't touch the GPU.
- `--full` — Loads voice stack + measures search VRAM (mocked Brave+Jina) and coding-session VRAM (mock bridge). ~3 min. Locks the GPU.
- `--all` — Both. Default.

Latest results live in [baselines.json](../../baselines.json) under `phase_foundation_start.measurements_extended`.

## Why no full audio-loop test in the default suite

A truly end-to-end test would synthesize speech, feed it through Silero VAD + openWakeWord + Whisper + the full LLM/TTS chain, and capture the rendered PCM for content + latency assertions. That's 30+ seconds per test, requires 10 GB of VRAM, and burns Claude API tokens for any coding scenarios. Not appropriate for the default `pytest tests/` suite.

The integration tests in this directory verify the **dispatch state machine** — that the orchestrator routes utterances to the right handler, that handlers produce the right artifacts (voice messages, audit log rows, runner state changes), and that failure paths degrade gracefully. The real-stack tests verify that the underlying components actually work end-to-end.
