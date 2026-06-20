# Observability / Tracing Design for LLM Voice Pipelines

**Research date:** 2026-06-20
**Scope:** Capturing the full prompt, thinking/reasoning trace, per-stage text transforms, routing
decisions + scores, and LLM outputs in a way that is analyzable for prompt refinement and
regression — specifically for Ultron 1.0 (local Windows, RTX 4070 Ti 12 GB, llama-cpp-python
0.3.22, Josiefied-Qwen3-8B-abliterated Q5_K_M, anticheat-safe, Valorant voice relay).

---

## TL;DR Recommendation for Ultron 1.0

**Do not adopt an external tracing backend** (Langfuse, Phoenix, Jaeger). The anticheat constraint
bans network calls from the relay path, and the overhead of a daemon process is not worth it for a
solo/small-team codebase. Instead:

1. **Promote `logs/usage_trace.jsonl` to the canonical "turn trace" record.** Extend it with
   the fields below. This file already exists; the Orchestrator already writes to it in testing
   mode. Remove the testing-mode gate for the new u1.0 LLM fields (turn traces are small,
   ~1–3 KB/turn) and write unconditionally, fail-open.

2. **Add a parallel `logs/llm_trace.jsonl`** for the heavy payload (full prompt, thinking block,
   raw completion). Keep it on a separate file so production log rotation / size limits never
   touch the lightweight turn trace. Gate via env `KENNING_LLM_TRACE=1`; default ON during
   development, OFF during a live anticheat game session (set in `.env`).

3. **Leverage the existing `kenning/trace.py` turn-id + phase system** to correlate every
   stage. Every JSONL record carries `turn_id` so you can join `routing_decisions.jsonl` +
   `usage_trace.jsonl` + `llm_trace.jsonl` by turn_id to reconstruct the full pipeline execution.

4. **Use llama.cpp server's native `reasoning_content` field** (available since 2025 via
   `reasoning_format=deepseek`) to capture the `<think>` block separately from the final
   completion. Intercept this at the llama-cpp-python call site in `inference.py:generate_stream`.

5. **Pin prompt template versions** in every JSONL record (`prompt_template_id`, `prompt_version`)
   and maintain a `prompts/` YAML registry. This is the critical enabler for regression diff.

6. **Golden-set JSONL regression gate:** pull 100–200 representative turns from production traces,
   freeze expected routing + output fields, run in CI via the MP3 battery harness. This is the
   u1.0 equivalent of the existing 186-case frozen test table.

---

## Findings

### 1. Industry-standard trace schemas: OTel GenAI + OpenInference

#### OpenTelemetry GenAI Semantic Conventions (OTel GenAI SIG, v1.37+, 2025)
[Source: greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions](https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions)
[Source: opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)

The CNCF-backed OTel GenAI SIG (active since April 2024, stable v1.37 in 2025) defines the SOTA
schema for LLM telemetry. Adopted by Google Cloud, AWS, Azure, Datadog, MLflow, Langfuse, and
Arize Phoenix. Key span attributes:

| Attribute | Description |
|---|---|
| `gen_ai.operation.name` | `chat`, `text_completion`, `generate_content` |
| `gen_ai.provider.name` | `llama`, `anthropic`, `openai`, etc. |
| `gen_ai.request.model` | Model identifier at request time |
| `gen_ai.response.model` | Actual model (may differ from request) |
| `gen_ai.usage.input_tokens` | Prompt token count |
| `gen_ai.usage.output_tokens` | Generated token count |
| `gen_ai.usage.reasoning.output_tokens` | Thinking/reasoning token count (provider extension) |
| `gen_ai.response.finish_reasons` | e.g. `["stop"]`, `["tool_calls"]` |

**Prompt / completion content is stored as span events, not attributes**, to avoid indexing large
blobs in the tracing backend. The event has:
```json
{
  "name": "gen_ai.content.prompt",
  "attributes": {
    "gen_ai.prompt": "...",
    "gen_ai.completion": "..."
  }
}
```

Three capture modes are defined: (a) not recorded, (b) on span attributes (for debug), (c) in
external storage with a reference URL. Mode (c) is recommended for production.

**Agent spans** (`invoke_agent`, `chat`, `execute_tool`) nest hierarchically:
```
invoke_agent voice-turn (INTERNAL)
├── chat qwen3-8b (CLIENT)           [routing decision + LLM call]
│   └── [event: gen_ai.content.prompt + reasoning_content]
├── execute_tool relay_to_team (INTERNAL)
└── chat qwen3-8b (CLIENT)           [follow-up if needed]
```

OTel spans also carry `gen_ai.evaluation.result` events for post-call quality scores:
- `gen_ai.evaluation.score.value` (float)
- `gen_ai.evaluation.score.label` (string rubric name)

#### OpenInference Semantic Conventions (Arize Phoenix, ELv2, 9k+ GitHub stars)
[Source: github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md)

OpenInference is the competing open standard used by Arize Phoenix; it predates OTel GenAI and has
richer message-level detail. Notably it has **explicit reasoning token support**:

| Attribute | Description |
|---|---|
| `llm.input_messages.<i>.message.role` | `system`, `user`, `assistant` |
| `llm.input_messages.<i>.message.content` | Full text of the message part |
| `llm.output_messages.<i>.message.contents.<j>.message_content.type` | `text`, `reasoning`, `audio`, `image`, `tool_use` |
| `llm.token_count.completion_details.reasoning` | Thinking token count |
| `llm.cost.completion_details.reasoning` | Cost attributed to think tokens |
| `llm.finish_reason` | Completion reason |
| `llm.invocation_parameters` | JSON of sampling params (temperature, top_p, etc.) |
| `embedding.model_name` / `embedding.text` / `embedding.vector` | For sidecar embedding spans |
| `retrieval.documents.<i>.document.score` | Routing/retrieval confidence scores |
| `metadata` | Arbitrary JSON dict for custom fields (route, template_id, etc.) |
| `session.id` / `user.id` | Conversation session ID |
| `openinference.span.kind` | `LLM`, `EMBEDDING`, `RETRIEVER`, `RERANKER`, `AGENT`, `TOOL`, `CHAIN` |

The `message_content.type = "reasoning"` is the key mechanism for separating thinking tokens from
final answer in the observation record. This maps directly to what llama.cpp returns in
`message.reasoning_content` when `reasoning_format=deepseek`.

### 2. llama.cpp server: native observability hooks
[Source: github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
[Source: fossies.org/linux/llama.cpp/tools/server/README.md](https://fossies.org/linux/llama.cpp/tools/server/README.md)

**Prometheus `/metrics` endpoint** (enable with `--metrics` flag):
| Metric | Description |
|---|---|
| `llamacpp:prompt_tokens_total` | Cumulative prompt tokens processed |
| `llamacpp:prompt_seconds_total` | Cumulative prompt processing wall time |
| `llamacpp:prompt_tokens_seconds` | Average prompt throughput (tokens/s) |
| `llamacpp:tokens_predicted_total` | Cumulative generation tokens |
| `llamacpp:predicted_tokens_seconds` | Average generation throughput (tokens/s) |
| `llamacpp:requests_processing` | Active concurrent requests |
| `llamacpp:requests_deferred` | Queue depth |
| `llamacpp:n_tokens_max` | Context size high-watermark |
| `llamacpp:n_decode_total` | Total decode calls |
| `llamacpp:n_busy_slots_per_decode` | Average busy KV-cache slots |

**Logging flags:** `--log-file FNAME`, `-v`/`-lv N` (0–5), `--log-timestamps`

**Thinking/reasoning response schema** — when using `/v1/chat/completions` with
`reasoning_format: "deepseek"` (or `--reasoning-format deepseek`):
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "The final user-visible answer.",
      "reasoning_content": "<the raw thinking block stripped of <think> tags>"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 412,
    "completion_tokens": 87,
    "total_tokens": 499
  }
}
```
With `reasoning_format: "none"`, the `<think>...</think>` block stays unparsed in `content`.
With `reasoning_format: "auto"`, llama.cpp decides based on model metadata.
The `reasoning_budget` parameter sets a token cap for thinking (-1 = unlimited).

**Note for llama-cpp-python in-process (our setup):** We do NOT use the HTTP server; we call
`llama_cpp.Llama.__call__` directly. The `reasoning_content` field is returned via
`response["choices"][0]["message"]["reasoning_content"]` when the model emits `<think>` blocks and
`reasoning_format` is passed as a create-completion kwarg. Confirmed supported in llama-cpp-python
0.3.x via the underlying llama.cpp shared library. If the key is absent (non-thinking turn), treat
as empty string.

### 3. Voice pipeline-specific tracing: per-stage latency decomposition
[Source: livekit.com/blog/understand-and-improve-agent-latency](https://livekit.com/blog/understand-and-improve-agent-latency)
[Source: livekit.com/blog/sequential-pipeline-architecture-voice-agents](https://livekit.com/blog/sequential-pipeline-architecture-voice-agents)
[Source: smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget](https://smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget)

Production voice pipeline observability (2025 consensus from LiveKit, Retell AI, Inworld AI) tracks
these distinct latency stages:

| Stage | Metric | Typical Range |
|---|---|---|
| VAD end-of-speech detection | `vad_latency_ms` | 0–80 ms |
| STT transcription | `stt_latency_ms` | 50–150 ms (Parakeet/Whisper local) |
| Wake/address classification | `addr_latency_ms` | 5–50 ms |
| Lexical/fuzzy routing | `lex_route_ms` | 1–5 ms |
| Embedding routing (sidecar) | `embed_route_ms` | 10–40 ms |
| LLM time-to-first-token (TTFT) | `llm_ttft_ms` | 300–800 ms |
| LLM total generation | `llm_gen_ms` | 1,000–4,000 ms |
| TTS time-to-first-byte (TTFB) | `tts_ttfb_ms` | 75–200 ms |
| Audio playback start | `playback_start_ms` | 0–50 ms |
| Total end-to-end | `e2e_latency_ms` | 500–3,000+ ms |

The LiveKit Agents SDK emits these on every `ChatMessage.metrics`. The recommended approach for
custom pipelines is to time each phase explicitly with the existing `kenning/trace.py phase()`
context manager and record to JSONL.

**TTFT is the dominant user-perceived latency signal** for voice: human conversation tolerates
~300–500 ms before the response feels unnatural. For Ultron 1.0 routing all through 8B:
- Cold path (thinking ON): TTFT likely 500–1,200 ms (need to measure; thinking tokens precede answer tokens)
- Snap path (thinking OFF, short exemplar): TTFT likely 250–500 ms
- TTFT budget must be tracked per `route_type` (relay vs identity vs social vs directive)

### 4. Self-hosted tracing tools: Langfuse, Phoenix, plain JSONL
[Source: langfuse.com/docs/observability/overview](https://langfuse.com/docs/observability/overview)
[Source: langfuse.com/integrations/model-providers/ollama](https://langfuse.com/integrations/model-providers/ollama)
[Source: arize.com/phoenix/](https://arize.com/phoenix/)
[Source: mlflow.org/articles/top-llm-observability-tools-in-2026-a-pro-guide/](https://mlflow.org/articles/top-llm-observability-tools-in-2026-a-pro-guide/)

**Langfuse (MIT, self-hosted):**
- Architecture: queued OTLP ingestion → S3 → ClickHouse. Requires Docker compose with
  PostgreSQL + ClickHouse + Redis + S3-compatible store. Heavy for a single-machine gaming rig.
- Trace model: `trace` → `observation` (generation/span/event) with `session_id`, `user_id`,
  `metadata` dict, `input`/`output`/`usage` on each generation.
- v4 (2025): native OTel SpanExporter interface, no mocks needed for any OpenAI-compatible API.
- **Verdict for Ultron:** Too heavy to run alongside the game. Not anticheat-safe (network daemon).
  Could be used for offline post-session analysis if the JSONL trace is loaded via Langfuse SDK.

**Arize Phoenix (ELv2, self-hosted, ~9k stars):**
- Runs as a lightweight Python process (`pip install arize-phoenix`; no Docker required).
- Built on OpenInference + OTel; accepts spans from any OTel-instrumented Python code.
- Would require importing `opentelemetry-sdk` and `arize-phoenix-otel` into the relay path.
  **Both packages import C extensions (grpc, protobuf) — this violates the anticheat import
  firewall for the voice/relay path.** Safe only if tracing SDK is isolated to a sidecar or
  post-session analysis script.
- UI is notebook/browser-based; excellent for RAG and embedding drift analysis. Not needed for
  voice relay where the trace is compact enough to read as JSONL.

**MLflow tracing (Apache 2.0):**
- MLflow 2.x added LLM tracing with `mlflow.start_span()` / `@mlflow.trace` decorator. Records
  prompt + completion + parameters + metrics. Good for experiment comparison.
- Requires a tracking server (SQLite backend acceptable for local). Same import-firewall concern.
- Best fit: offline experimentation with prompt templates, not hot-path production logging.

**Plain JSONL (our current approach, extended):**
- Zero dependencies. Already used: `logs/routing_decisions.jsonl`, `logs/usage_trace.jsonl`.
- Anticheat-safe: Python stdlib `json` + `pathlib`, no network, no C extension.
- Queryable with `jq`, `pandas`, or any Python script.
- **This is the correct baseline for Ultron 1.0.** Optionally load into Phoenix/Langfuse
  post-session for visual analysis without carrying the overhead during gameplay.

### 5. Prompt regression testing: golden-set JSONL + paired CI
[Source: futureagi.com/blog/prompt-regression-testing-2026/](https://futureagi.com/blog/prompt-regression-testing-2026/)
[Source: testquality.com/llm-regression-testing-pipeline/](https://testquality.com/llm-regression-testing-pipeline/)
[Source: coverge.ai/blog/llm-regression-testing](https://coverge.ai/blog/llm-regression-testing)

**Recommended golden-set schema (JSONL, one record per test case):**
```json
{
  "case_id": "relay_damage_001",
  "route": "relay.tactical",
  "prompt_template_id": "relay_tactical_v3",
  "input": "Jett hit 84, Breach hit 97",
  "expected_route": "relay_to_team",
  "expected_snap": null,
  "expected_output_contains": ["84", "97"],
  "expected_output_excludes": ["I think", "According to"],
  "rubrics": ["no_sycophancy", "ultron_persona", "team_relay_format"],
  "edge_case": false,
  "added_from": "production_trace_20260614"
}
```

**Baseline score pinning:**
```python
baseline = json.loads((BASELINES / f"{route}.json").read_text())
# Per rubric: baseline[rubric] = [per_case_scores]
```

**Paired delta CI gate** — bootstrap 95% CI on per-case score deltas:
```python
d = np.array(candidate_scores) - np.array(baseline_scores)
boot = [d[np.random.choice(len(d), len(d))].mean() for _ in range(10_000)]
lo, hi = np.percentile(boot, [2.5, 97.5])
# Block if: hi < 0 (regressed) OR mean < floor threshold
```

**Set size:** 100–300 cases per route. Ultron 1.0 routes: relay.tactical, relay.damage,
relay.compose, identity, social.compliment, social.insult, marvel, directive.

**Prompt template versioning (YAML):**
```yaml
# prompts/relay_tactical/v3.yaml
version: 3
parent: 2
template: |
  You are Ultron. A Valorant teammate has said: {utterance}
  ...
variables: [utterance, agent, flavor_tails]
owners: [ultron-dev]
last_validated_against: tests/data/golden/relay_tactical.jsonl@sha:a3f1b9
```

Every trace record carries `prompt_template_id` + `prompt_version` as a span attribute so CI can
align candidate runs with the correct baseline.

### 6. Reasoning token capture: the think-block split
[Source: github.com/ggml-org/llama.cpp/discussions/15362](https://github.com/ggml-org/llama.cpp/discussions/15362)
[Source: ttms.com/llm-observability-how-to-monitor-ai-when-it-thinks-in-tokens/](https://ttms.com/llm-observability-how-to-monitor-ai-when-it-thinks-in-tokens/)

For Qwen3 thinking mode, the model emits:
```
<think>
[reasoning steps — may be 20–500 tokens for a tactical relay]
</think>
[final answer — the only part spoken to the user]
```

With `reasoning_format=deepseek` in the llama.cpp API call:
- `message.content` = final answer only
- `message.reasoning_content` = the raw think block (no `<think>` tags)
- `usage.completion_tokens` = total (think + answer)

For observability, the llm_trace.jsonl record should capture **both fields separately**:
```json
{
  "turn_id": 42,
  "prompt_template_id": "relay_tactical_v3",
  "prompt_version": 3,
  "system_prompt_hash": "sha256:abc123...",
  "system_prompt": "...",
  "user_message": "Jett hit 84, Breach hit 97",
  "full_messages": [...],
  "thinking_content": "The user is reporting damage dealt...",
  "thinking_tokens": 183,
  "final_content": "Jett eighty-four, Breach ninety-seven.",
  "completion_tokens": 12,
  "total_tokens": 195,
  "finish_reason": "stop",
  "sampling": {"temperature": 0.8, "top_p": 0.92, "max_tokens": 56},
  "llm_ttft_ms": 412,
  "llm_gen_ms": 891,
  "timestamp": "2026-06-20T10:15:33.210Z"
}
```

**Prompt hash:** SHA-256 of the system prompt text enables detecting when a prompt changed between
sessions without diffing full text. Include in the golden-set baseline so regressions in the prompt
itself are flagged.

### 7. Per-stage routing decision schema (extension of existing routing_decisions.jsonl)

The existing `logs/routing_decisions.jsonl` already captures `intent`, `confidence`, `source`,
`reason`, `rule_based`, `handler`, `outcome`. For u1.0, extend with:

```json
{
  "turn_id": 42,
  "timestamp": "...",
  "utterance": "Jett hit 84, Breach hit 97",
  "raw_stt": "Jett hit 84, Breach hit 97",
  "normalized": "Jett hit 84 Breach hit 97",

  "stage1_lex": {
    "matcher": "relay_speech._parse_callout_slots",
    "matched": true,
    "score": 1.0,
    "match_type": "slot_callout_forced",
    "slots": {"agents": ["Jett", "Breach"], "damages": [84, 97]}
  },
  "stage2_embed": null,
  "stage3_llm_gate": null,

  "intent": "relay_to_team",
  "route_type": "relay.damage",
  "prompt_template_id": "relay_tactical_v3",
  "prompt_version": 3,
  "handler": "relay_speech.build_relay_line",
  "outcome": "relay_played",

  "latency": {
    "stt_ms": 92,
    "addr_ms": 8,
    "lex_route_ms": 2,
    "embed_route_ms": null,
    "llm_gate_ms": null,
    "llm_ttft_ms": 387,
    "llm_gen_ms": 742,
    "tts_ms": 148,
    "playback_start_ms": 18,
    "e2e_ms": 1397
  }
}
```

`stage2_embed` and `stage3_llm_gate` are `null` when not consulted (lexical short-circuit). This
makes it easy to query "how often did we need the embedder" and "how often did the LLM gate decide
differently from the embedder."

### 8. Existing Ultron infrastructure audit

Current assets that are already close to the right shape:

| Asset | Location | Gap |
|---|---|---|
| `kenning/trace.py` | `src/kenning/trace.py` | No JSON sink; only structured log lines |
| `logs/routing_decisions.jsonl` | `logs/routing_decisions.jsonl` | Missing turn_id join key, missing latency fields, missing LLM-gate fields |
| `logs/usage_trace.jsonl` | `logs/` (testing-mode only) | Testing-mode gate needs removing; missing prompt_template_id, thinking_content, TTFT |
| `orchestrator._record_full_flow` | `orchestrator.py:3388` | Extend with new fields; add LLM-trace branch |
| `inference.py:generate_stream` | `src/kenning/llm/inference.py:1979` | No timing capture, no reasoning_content capture; `reasoning_format` kwarg not wired |

The plan is additive: no existing logging is removed. New JSONL fields are appended via `rec.update(extra)` which is already the pattern in `_record_full_flow`.

---

## Concrete Techniques/Params We Should Adopt

### A. Add `reasoning_format="deepseek"` to generate_stream calls where thinking is enabled

In `inference.py:_build_completion_kwargs` or the `_RELAY_SAMPLING` call site:
```python
completion_kwargs["reasoning_format"] = "deepseek"  # only when enable_thinking=True
```
Then in the response-reading loop (currently `generate_stream` yields chunks from the streaming
response), extract `choices[0]["delta"].get("reasoning_content", "")` for the think-block
accumulator, and `choices[0]["delta"].get("content", "")` for the final-answer accumulator.
At stream end, write both to `llm_trace.jsonl`.

### B. Extend `kenning/trace.py` with a JSONL sink

Add a `record(kind: str, data: dict)` function that appends to `logs/{kind}.jsonl` with
`turn_id` + `timestamp` injected. This keeps all JSONL writes consistent and inherits the
existing thread-local `turn_id`.

### C. Schema for `logs/llm_trace.jsonl` (full prompt + thinking capture)

Fields: `turn_id`, `route_type`, `prompt_template_id`, `prompt_version`, `system_prompt_hash`,
`system_prompt` (full text — only write when `KENNING_LLM_TRACE_FULL_PROMPT=1`; otherwise hash
only), `user_message`, `thinking_content`, `thinking_tokens`, `final_content`,
`completion_tokens`, `total_tokens`, `finish_reason`, `sampling`, `llm_ttft_ms`, `llm_gen_ms`,
`timestamp`.

Default: write `thinking_content` always (it is the primary refinement signal). System prompt
is large (~1–3 KB) — write only when the env flag is set.

### D. Schema for `logs/turn_trace.jsonl` (lightweight per-stage record)

Promote `usage_trace.jsonl` to `turn_trace.jsonl` with these fields:
`turn_id`, `timestamp`, `raw_stt`, `normalized`, `addr_result`, `route_type`,
`prompt_template_id`, `snap_used`, `final_spoken`, `channel`, `latency` (object with per-stage
ms fields as in §7 above).

### E. Prompt template registry: `prompts/` directory with versioned YAML

Structure:
```
prompts/
  relay_tactical/
    v1.yaml
    v2.yaml
    v3.yaml  ← current
  relay_compose/
    v1.yaml
  identity/
    v1.yaml
  ...
```

Each YAML has `version`, `parent`, `template`, `variables`, `last_validated_against`.
A `prompts/index.json` maps `{template_id: {current_version, path}}` for runtime lookup.

### F. Golden-set regression harness integration

Extend `tests/test_relay_corpus.py` (the existing 482-test frozen table) with:
1. A `tests/data/golden/` directory with per-route JSONL golden sets (100–200 cases).
2. A `tests/test_llm_regression.py` that:
   - Loads golden JSONL per route
   - Runs `inference.generate_stream` with the versioned prompt template
   - Compares `route_type`, `snap_used`, `final_spoken` against expected
   - Checks rubrics via deterministic string checks (for anticheat-safe path, no LLM-as-judge)
   - Reads `tests/data/baselines/{route}.json` for score history
   - Blocks on floor violation or negative CI

### G. Per-session analysis script

`scripts/trace_analyze.py` — reads `logs/turn_trace.jsonl` + `logs/llm_trace.jsonl`,
joins on `turn_id`, computes:
- P50/P95 per-stage latency by `route_type`
- Think token budget utilization (thinking_tokens / reasoning_budget)
- Routes where `thinking_content` is long but `final_content` is short (over-thinking signal)
- Prompt template hit/miss rate by version
- Frequency of each `snap_used` value

Output: markdown report to `logs/session_analysis_{date}.md`.

### H. OTel span hierarchy (optional, for future Phoenix integration)

If we ever load traces into Arize Phoenix for visual analysis post-session, the span hierarchy
using OpenInference conventions should be:
```
CHAIN  voice_turn (turn_id=42, session_id=...)
├── CHAIN  routing (utterance=..., addr_result=...)
│   ├── TOOL  lex_matcher (matcher=..., score=..., matched=...)
│   └── EMBEDDING  embed_route (model=gemma-300m, score=...)
└── LLM  qwen3_relay (model=qwen3-8b-q5km, ...)
    ├── span_event: gen_ai.content.prompt
    ├── span_event: gen_ai.content.reasoning (thinking_content=...)
    └── span_event: gen_ai.content.completion
```
This can be exported from the JSONL records offline using a conversion script and the
`opentelemetry-sdk` package (imported only in the offline script, not the hot path).

---

## Risks / Caveats for Our Constraints

### Risk 1: Anticheat import firewall
The relay/voice hot path has a strict import allowlist (`numpy`, `urllib`, `scipy`, `stdlib`,
`rapidfuzz`). OpenTelemetry SDK (`opentelemetry-sdk`, `opentelemetry-api`, `grpcio`) are NOT
on this list and must not be imported in-process during a live game. The JSONL approach avoids
this entirely. Any OTel export must happen in an offline post-session script.

### Risk 2: File I/O in the hot path
Writing to JSONL on every turn adds I/O latency. Mitigation: use `Path.open("a")` with a small
in-process buffer (`io.TextIOWrapper` with `write_through=False`), or use a background thread
with a `queue.Queue` to absorb bursts. The existing `_record_full_flow` already uses a try/except
fail-open pattern — keep this, as a logging failure must never drop a relay.

### Risk 3: `reasoning_content` field availability in llama-cpp-python 0.3.22
The `reasoning_format` kwarg is a server-side parameter; for in-process llama-cpp-python it
depends on the underlying llama.cpp shared library version. Must verify at boot that
`response["choices"][0]["message"].get("reasoning_content")` is not `KeyError` with our actual
binary. If absent (older llama.cpp build), fall back to regex-splitting `<think>...</think>` from
`content`. The existing `inference.py` streaming path may need to detect the split mid-stream
(the `<think>` tag appears in early chunks; accumulate into a separate buffer until `</think>` seen).

### Risk 4: Think block size — VRAM budget
For Qwen3-8B Q5_K_M at 10 GB cap, a long think block consumes KV-cache. With `reasoning_budget=200`
tokens the risk is low, but if prompt + think + answer exceeds context window, llama.cpp will silently
truncate. The JSONL trace should record `context_used_tokens` (available from `usage.total_tokens`)
so we can monitor proximity to the 8192-token context limit.

### Risk 5: Golden-set representativeness drift
The relay corpus is Valorant-specific. Season meta changes (new agents, map rotations) will make
some test cases obsolete. The `added_from` field in each golden-set record helps track when a case
was harvested from production; cases older than ~3 months should be reviewed.

### Risk 6: System prompt hash collisions
SHA-256 of the system prompt text will differ on any whitespace change. This is a feature (any
change is flagged), but it means each prompt template edit bumps the version and invalidates the
baseline. This is correct behavior and is the intended regression gate.

### Risk 7: `reasoning_format` and grammar/JSON output conflict
As of mid-2025, there is a known llama.cpp bug where `response_format` + `enable_thinking` (i.e.,
grammar enforcement + reasoning mode) conflict (GitHub issue #20345). For Ultron 1.0 routes that
use JSON-constrained output (structured slot extraction), thinking mode must be disabled (`enable_thinking=False`) or `reasoning_format` kept at `"none"`. Log `thinking_enabled` in every
llm_trace record so this can be diagnosed.

---

## Sources (Full URLs)

1. MLflow LLM observability pipelines 2026: https://mlflow.org/articles/setting-up-llm-observability-pipelines-in-2026/
2. Portkey complete guide to LLM observability 2026: https://portkey.ai/blog/the-complete-guide-to-llm-observability/
3. OpenTelemetry GenAI semantic conventions (OTel registry): https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
4. OTel GenAI agent spans spec: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/
5. How OTel traces LLM calls, agent reasoning, and MCP tools (Greptime 2026-05): https://greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions
6. Datadog LLM observability + OTel GenAI semantic conventions: https://www.datadoghq.com/blog/llm-otel-semantic-convention/
7. OpenInference semantic conventions spec (Arize-ai GitHub): https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
8. OpenInference traces spec: https://github.com/Arize-ai/openinference/blob/main/spec/traces.md
9. llama.cpp server README (tools/server): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
10. llama.cpp reasoning_format discussion (different reasoning fields): https://github.com/ggml-org/llama.cpp/discussions/15362
11. llama.cpp grammar + thinking conflict issue #20345: https://github.com/ggml-org/llama.cpp/issues/20345
12. Langfuse LLM observability overview: https://langfuse.com/docs/observability/overview
13. Langfuse Ollama (local LLM) integration: https://langfuse.com/integrations/model-providers/ollama
14. Langfuse self-hosting guide: https://langfuse.com/self-hosting
15. Langfuse v4 + Ollama local LLMs (DEV community): https://dev.to/jmolinasoler/langfuse-v4-ollama-tracing-local-llms-without-mocks-or-monkey-patches-478c
16. Arize Phoenix LLM observability: https://arize.com/phoenix/
17. MLflow top LLM observability tools 2026: https://mlflow.org/articles/top-llm-observability-tools-in-2026-a-pro-guide/
18. ZenML best LLM monitoring tools 2025: https://www.zenml.io/blog/best-llm-monitoring-tools
19. LLM Observability Tools in 2025 (iguazio): https://www.iguazio.com/blog/llm-observability-tools-in-2025/
20. LiveKit: Understanding and improving voice agent latency: https://livekit.com/blog/understand-and-improve-agent-latency
21. LiveKit sequential pipeline architecture for voice agents: https://livekit.com/blog/sequential-pipeline-architecture-voice-agents
22. Designing voice assistants: STT, LLM, TTS, tools, and latency budget (smallest.ai): https://smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget
23. Prompt regression testing practical guide 2026 (FutureAGI): https://futureagi.com/blog/prompt-regression-testing-2026/
24. LLM regression testing pipeline for QA (testquality.com): https://testquality.com/llm-regression-testing-pipeline/
25. LLM regression testing: catching quality drift (coverge.ai): https://coverge.ai/blog/llm-regression-testing
26. LLM observability: how to monitor AI when it thinks in tokens (TTMS): https://ttms.com/llm-observability-how-to-monitor-ai-when-it-thinks-in-tokens/
27. Monitoring LLM inference: Prometheus + Grafana for llama.cpp (glukhov.org): https://www.glukhov.org/observability/monitoring-llm-inference-prometheus-grafana/
28. Observability in LLM workflows: metrics, traces, logs (TrueFoundry): https://www.truefoundry.com/blog/observability-in-llm-workflows
29. Qwen3 llama.cpp run-locally guide: https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html
