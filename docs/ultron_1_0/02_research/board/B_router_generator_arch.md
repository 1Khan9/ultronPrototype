# Router+Generator Voice-Agent Reference Architectures: Classify-then-Generate in ONE Structured LLM Call vs TWO Calls (Classifier then Generator); Latency/Quality Tradeoffs; Failure Handling; Observability; Examples from Production Voice Agents 2025-2026

**Research date:** 2026-06-20  
**System context:** Ultron 1.0 — local Windows, RTX 4070 Ti 12GB (10GB cap), Josiefied-Qwen3-8B-abliterated Q5_K_M via llama-cpp-python 0.3.22, EmbeddingGemma-300M sidecar, Valorant relay voice agent.

---

## TL;DR Recommendation for Ultron 1.0

**Use a three-tier hybrid that drives the 8B model only when it must generate.** The key insight from 2025-2026 production practice is that most voice turns do NOT need the 8B to classify—cheap layers (rules + EmbeddingGemma cosine) should intercept 80-90% of turns with zero LLM tokens consumed. For the remaining band (ambiguous intent), use ONE structured LLM call that emits a JSON header (`{"intent": "...", "verbosity": "...", "think": false}`) in the first ~8 tokens, then streams the response body immediately—so routing decision and generation are a single forward pass with no second roundtrip.

Only invoke TWO calls (classify then generate) for the minority of turns requiring thinking-mode reasoning, where the "classify call" sets `budget_tokens=0` (non-thinking, ~20-50ms) to decide whether deep reasoning is needed, then a second call with thinking enabled does the actual generation. This bounded two-call pattern is dramatically cheaper than always thinking, and avoids the latency cliff of gratuitous reasoning tokens.

The deterministic snap matchers (relay, thank-you, nice-try, etc.) become prompt-template selectors and exemplar injectors, not dead-ends—they still fire pre-LLM but now the "snap" is the full 8B response on a pre-assembled system prompt + curated exemplars. This preserves quality without serial classification overhead.

---

## Findings

### 1. The Fundamental Architecture Options

Production practice 2025-2026 identifies four patterns on a latency-vs-flexibility spectrum:

#### Pattern A: Pure Sequential Two-Call (Classifier → Generator)
Send the utterance to the LLM (or a smaller model) for classification; wait for the label; build a new prompt; send the generation call. Total cost: two full LLM roundtrips.

- **Cloud baseline latency (streaming):** Classification call (small model, fast path): 150-400ms TTFT. Generation call: 200-750ms TTFT. Sequential total: 350ms-1.15s before first token of real response, which is often too slow for voice [Twilio, 2025; Daily.co, 2025].
- **Local 8B estimate (Qwen3-8B Q5_K_M, RTX 4070 Ti ~40-50 tok/s):** Classification prompt ~100-200 tokens generates ~10-20 tokens ≈ 200-500ms per call at local TTFT. Two calls = ~400ms-1s routing overhead before first response word. At 40 tok/s, that is 10 tokens / 40 tok/s = 250ms generation time for a label. NOT including prefill latency for a 1K-token context.
- **When justified:** When the generator prompt is fundamentally different per category (e.g. a relay vs a Marvel lore answer uses a completely different system prompt with different exemplar sets), AND the classification can be done with a cheap, fast non-thinking call that the generation call cannot replicate.
- **Status:** SOTA for quality-critical cases; common in production [mkbctrl gist, 2025]; adds serial latency that is problematic for <800ms mouth-to-ear targets.

#### Pattern B: Single Structured Call (Joint Classification + Generation)
One LLM call emits `{"intent": "relay", "verbosity": "low", "think": false, "response": "..."}` where the model generates the classification header first, then the response body in the same forward pass.

- **Mechanism:** Use JSON Schema constrained decoding (GBNF in llama.cpp / `response_format` with `json_schema` in the OpenAI-compatible server) so the model is forced to emit the intent field before any response text. The routing code can fire as soon as the intent field is complete—before the response body streams [AssemblyAI, 2025].
- **Key insight from streaming:** "If the first field in your schema is `intent`, your routing logic can fire before the model finishes generating the response body" [AssemblyAI, 2025]. This means the TTS pipeline can start on the right voice persona / verbosity level mid-stream.
- **Latency overhead of constrained decoding:** XGrammar-2 (ACM CAIS '26) achieves under 40 microseconds per token for JSON Schema constraints, up to 3x speedup vs naive constrained decoding. GBNF in llama.cpp adds negligible overhead per token for simple schemas. Constrained decoding is sometimes *faster* than unconstrained because the masked token sampling space is smaller.
- **Token overhead:** The classification header itself (~10-20 JSON tokens) is the only overhead vs a pure generation call. At 40 tok/s local speed, that is 0.25-0.5s overhead per call for the header tokens—but these tokens are generating concurrently with the prefill, not serially after it.
- **Status:** Recommended by AssemblyAI (2025), standard for intent-routing IVR/voice agents; matches the "streaming structured output" pattern now universal across GPT, Claude, Gemini.

#### Pattern C: Pre-generation Activation Routing (Research-grade, 2025-2026)
Analyze the LLM's internal prefill activations before any tokens are generated to predict which route/model is best. The routing decision happens in the prefill phase at zero generation cost.

- **Technique (LLM Router, arxiv 2603.20895):** A lightweight MLP ("SharedTrunkNet") reads prefill hidden states and predicts task difficulty/suitability. Achieved 10.9pp accuracy gain over best single model and 74.31% cost savings vs always using the expensive model.
- **Relevance to Ultron 1.0:** Since we have only one 8B model (not a model pool), the activation-routing approach maps to *thinking vs non-thinking mode selection*. The prefill activation can predict whether this turn needs `budget_tokens > 0` (thinking) or can be answered in non-thinking fast path.
- **Status:** Research / cutting edge as of 2025-2026; not directly available in llama-cpp-python 0.3.22 without custom inference hooks. Monitoring for 0.4.x.

#### Pattern D: Cascade (Cheap Fast Path → Expensive Slow Path)
Run the EmbeddingGemma sidecar or RapidFuzz rules first; only escalate to the 8B when those cannot decide. This is the *existing* Ultron 0.x architecture extended into 1.0.

- **Production validation:** Semantic routing via embedding + cosine achieves 92-96% precision after tuning at sub-penny cost per query vs ~$0.65/10k LLM calls; "instead of waiting for slow LLM generations, we use the magic of semantic vector space" [mkbctrl, 2025].
- **Production recommendation:** "Semantic router (fast, cheap) as first-pass filter + LLM agent (flexible, fallback) for uncategorized queries" [mkbctrl, 2025]. This is the dominant hybrid in production 2025-2026.
- **Status:** STRONGLY RECOMMENDED for Ultron 1.0 as the outer gate; the 8B is invoked only in the undecided band. Matches our existing EmbeddingGemma + RapidFuzz + rules pipeline.

---

### 2. Latency Numbers: The Concrete Pipeline Budget

The industry standard mouth-to-ear target for production voice agents is **<1115ms** with an LLM TTFT target of **375ms** (max 750ms) [Twilio, November 2025]. In optimized streaming pipelines: 500-800ms is achievable; sequential (non-streaming) pipelines easily hit 2-4 seconds [bitbytes.io, 2026; ReveoAI, 2025].

For our LOCAL pipeline (no network hops, RTX 4070 Ti):

| Stage | Estimate | Notes |
|-------|----------|-------|
| Faster-Whisper/Parakeet STT | ~100-300ms | Local GPU; streaming transcript available sooner |
| EmbeddingGemma intent gate | ~10-30ms | 300M sidecar, cosine sim; existing system |
| RapidFuzz / rules pre-filter | <5ms | Deterministic, pure Python |
| Qwen3-8B prefill (1K tokens) | ~100-200ms | RTX 4070 Ti: ~5-10ms/layer × ~28 layers effective |
| Qwen3-8B generation (40-50 tok/s) | 25ms/token | Q5_K_M on 12GB VRAM; all layers in VRAM |
| JSON header generation (15 tokens) | ~375ms | Includes prefill + 15 tokens |
| First TTS sentence (15 words) | ~30-100ms | Kokoro streaming local |
| Kokoro audio output | overlap | Pipelined with remaining generation |

**Key:** At 40-50 tok/s for Qwen3-8B Q5_K_M on RTX 4070 Ti, TTFT is dominated by prefill latency, which scales with context length. A 2K-token context (system prompt + exemplars + history + user turn) will have ~200-400ms prefill. Adding 15 JSON header tokens ≈ 375ms extra. Total LLM TTFT: ~575-775ms for the first word of the response—within acceptable range if STT is fast.

**Two-call cost:** For the classification-then-generation pattern, the first call adds a full prefill + 20 token generation ≈ 400ms before the second call even starts. This pushes total LLM latency to ~775ms-1175ms, straining the <750ms TTFT target. NOT recommended for the common fast path.

**Non-thinking vs thinking latency:** Qwen3 non-thinking mode is dramatically faster because the model skips the `<think>...</think>` block. Thinking tokens for an 8B on a relay question easily add 500-2000 extra tokens = 10-50 seconds at local speed. Reserve thinking for: Marvel lore questions, complex tactical analysis, "answer a question I don't know the snap for." Default to non-thinking for relay, social snaps, confirmations.

---

### 3. Qwen3-8B Function Calling + Structured Output Quality

- **F1 score on tool selection:** 0.933 for Qwen3-8B (Docker evaluation, June 2025)—matches Claude 3 Haiku. Qwen3-14B reaches 0.971, near GPT-4's 0.974 [InsiderLLM, 2025].
- **Grammar enforcement reliability:** llama.cpp GBNF guarantees syntactically valid JSON but does NOT guarantee semantically correct values. Validation must happen in application code (e.g. `intent` must be one of the expected enum values). This is a known limitation [InsiderLLM, 2025].
- **Thinking mode integration:** Qwen3 ships with a dual-mode architecture—`/no_think` in the system prompt or `budget_tokens=0` disables the reasoning chain, giving fast non-thinking responses. `budget_tokens` caps the thinking token count for middle-ground cases [Qwen3 technical report, arxiv 2505.09388].
- **llama.cpp Q5_K_M performance estimate:** 35-50 tokens/sec on RTX 4070 Ti at Q5_K_M with all 32 layers in VRAM (Qwen3-8B model size ~6GB VRAM, leaving ~4GB for KV cache and EmbeddingGemma sidecar). This is well within budget.

---

### 4. Single-Call Structured Output: The Streaming Intent-First Pattern

This is the recommended production pattern for Ultron 1.0's 8B-only turns [AssemblyAI, 2025]:

```python
# Proposed schema for single-call routing+generation
ROUTING_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["relay", "private_reply", "ignore", "marvel", "social", "device_cmd"]
        },
        "verbosity": {
            "type": "string",
            "enum": ["low", "medium", "high"]
        },
        "think": {"type": "boolean"},
        "response": {"type": "string"}
    },
    "required": ["intent", "verbosity", "think", "response"]
}
```

The JSON schema is passed as `grammar=LlamaGrammar.from_json_schema(json.dumps(ROUTING_SCHEMA))` in llama-cpp-python. The model generates `intent`, `verbosity`, `think` before generating `response`, so code can:
1. Parse intent as soon as `intent` field token sequence completes (~5 tokens).
2. Route TTS to the right voice / apply verbosity modifier mid-stream.
3. If `think=true` was generated (rare), optionally abort and retry with thinking enabled—though this is a design choice; see risk below.

**Streaming implication:** The `response` field value starts streaming as soon as the JSON header is complete. TTS can begin on the first sentence of `response` while the LLM finishes generating the remainder. This is the key latency win vs a two-call pattern.

---

### 5. Two-Call Pattern: When It Is Actually Justified

Despite the latency cost, two calls are justified in exactly ONE scenario for Ultron 1.0:

**Thinking-mode routing:** A non-thinking call (fast, ~200-400ms) first decides `needs_thinking: bool`. If true, a second thinking-enabled call does the actual generation. This is justified because:
- Non-thinking classification with a single boolean is a ~10-token response: ~250ms at local speed.
- This saves the cost of thinking tokens (potentially 500-2000 tokens = 10-50 seconds!) on every turn where thinking is NOT needed.
- The alternative (always thinking) is catastrophically slow for voice. The alternative (never thinking) loses quality for hard questions.

Architecture for this case:
```
Turn → gate layers (rules/embed/fuzzy) → [clear answer] → snap template + 8B non-thinking
                                       → [undecided, complex] → 8B non-thinking classify (thinking?) 
                                                               → no:  8B non-thinking generate
                                                               → yes: 8B thinking generate
```

The "thinking? classify" call is ~200-400ms + ~10 tokens = ~450ms. The thinking generation call starts immediately after. Net cost vs never thinking: +450ms for truly complex turns (acceptable). Net savings vs always thinking: avoid 10-50s of thinking on simple relay turns (massive).

---

### 6. Failure Handling Patterns

Production voice agent data (2025-2026 engineering sources) identifies the key failure modes:

#### 6.1 Schema Compliance Failures
Grammar-constrained decoding guarantees syntactic validity but not semantic validity. Observed real failures:
- Model generates a valid `intent` enum value but the wrong one (misclassification).
- Model generates a `response` that contradicts the intent (e.g. `intent="relay"` but response is addressed to user privately).
- Model generates out-of-range values when the schema is too permissive.

**Mitigation:** 
- Keep the intent enum small (6-8 values max). Too many intents → model confusion and misroutes, especially under 8B [mkbctrl, 2025; InsiderLLM, 2025].
- Add a secondary validation pass in Python code (fast, pure rule check on the decoded intent field).
- Log every intent decision with the raw utterance for post-hoc analysis.

#### 6.2 Cascaded Misrouting (Two-Call)
If the classifier call misclassifies, the generator call runs with the wrong system prompt + exemplars, producing garbage. The user hears a coherent-sounding wrong response (worse than a fallback).

**Mitigation:**
- In the single-call pattern, misclassification still produces a response on the same prompt context—the "intent" field is just metadata for logging/routing, not a context switch. Harder to cascade-fail.
- In the two-call pattern, always provide a fallback in the generator prompt ("if you are uncertain, respond in Ultron persona asking for clarification").
- Monitor intent distribution: if `relay` drops suddenly, likely a misroute upstream.

#### 6.3 Pre-Roll / Empty Capture (Existing Ultron Bug)
The existing frozen `ad15ded` freeze: VAD sees empty capture because the cold pre-roll is not fed to VAD. This is an upstream failure mode independent of the router architecture. The 1.0 router should be robust to empty/garbled utterances by checking for minimum token count before invoking the 8B.

#### 6.4 Context Length / KV Cache Overflow
With a rich system prompt (Ultron persona + exemplars for multiple categories + history), context length can reach 3K-5K tokens per turn. At Q5_K_M, 4K context takes ~300-600ms prefill on RTX 4070 Ti. This is the dominant latency contributor for complex multi-category prompts.

**Mitigation:**
- Keep system prompt + exemplars below 1K tokens. Use MMR-selected exemplars (existing infrastructure) rather than all 1628 tails.
- Use per-intent prompt templates: load the relevant exemplar set ONLY after the gate layers have narrowed the intent. This means the LLM context for a relay turn does NOT include Marvel exemplars.
- Alternatively: accept the full-context approach and benchmark first—the single-call pattern may still be faster than two calls even at 3K tokens.

---

### 7. Observability: What to Log

Production LLM observability best practice (2025-2026) for routing agents uses distributed tracing at the span level [Datadog GenAI conventions, December 2025; Groundcover, 2025]:

```
Trace: voice_turn
  Span: stt                     → {duration_ms, transcript, word_error_rate_est}
  Span: gate_layers             → {duration_ms, method: "rules|embed|fuzzy", intent_label, confidence, threshold}
  Span: llm_classify_or_generate → {duration_ms, ttft_ms, tokens_prompt, tokens_gen, intent, verbosity, think_flag, model_name, quantization}
  Span: tts                     → {duration_ms, first_audio_ms, char_count}
  Span: relay_ptt               → {duration_ms, key_held_ms, outcome: "sent|cancelled"}
  Event: misroute_detected      → {expected_intent, actual_intent, utterance}
  Event: latency_breach         → {threshold_ms, actual_ms, stage}
```

Critical metrics to track:
- **Intent distribution per session:** Baseline ratio of relay vs social vs ignore. Sudden shifts = misroute or STT degradation.
- **p50/p95/p99 TTFT by intent:** Relay should be faster than Marvel (shorter exemplar set). Regressions visible immediately.
- **`think=true` rate:** If this is >10% of turns, either the prompts are under-specified or users are asking many hard questions. Validate against intent logs.
- **Classification confidence:** For the EmbeddingGemma gate, log cosine similarity score. Turns near the threshold (0.65-0.75) are the highest-risk misroutes.
- **Fallback rate:** Turns that hit `intent="ignore"` but had a wake word are likely misroutes.

The existing `logs/kenning.log` + `logs/usage_trace.jsonl` infrastructure provides the foundation. Extend with span-level timing from the router decision point.

---

### 8. Production Examples and Reference Architectures

#### 8.1 IVR / Contact Center (commercial production, 2025-2026)
Standard pattern: Embedding-based semantic router (fast first-pass, 50-100ms) → if high confidence, dispatch to specialized agent; if low confidence, LLM classification call → generator call [assemblyai, mkbctrl].

Example: classify intent as `{billing, support, sales, cancel, other}` + `urgency` + `escalate` in a single non-streaming structured call (300-500ms). If no escalation, stream conversational reply. Used by contact center platforms including Twilio ConversationRelay (<0.5s median with managed hosting) and similar.

#### 8.2 Gaming Voice Relay (closest analog to Ultron)
The Ultron 0.x architecture is already in this space. The 1.0 pivot to the 8B maps to: intent gate (rules/embed) → prompt template selector → 8B single call with structured header → streaming TTS. No published paper matches this exactly but the sub-500ms local voice agent builder [ntik.me, 2025] using Groq llama-3.3-70b at 80ms TTFT shows the achievable range with fast inference; local RTX 4070 Ti will be slower (40 tok/s vs Groq's 100+ tok/s) but has zero network latency.

#### 8.3 Semantic Router for vLLM (research, 2025)
"When to Reason" (arxiv 2510.08731): A semantic router that decides per-turn whether to invoke the thinking/reasoning mode. This is exactly the "thinking-mode routing" two-call pattern recommended above. The paper demonstrates measurable latency savings by avoiding reasoning on simple turns. Applying this to Qwen3's `budget_tokens` parameter is the direct translation.

#### 8.4 SimpleTool: Parallel Decoding for Function Calling (arxiv 2603.00030)
Enables simultaneous decoding of multiple function calls in one pass. For Ultron 1.0, this maps to: the model can generate both the intent metadata AND the relay command arguments in parallel within the same JSON schema call. Relevant if the 8B is asked to both classify AND extract slot-fills (agent name, message) in one structured call.

#### 8.5 RelayGen: Intra-Generation Model Switching (arxiv 2602.06454)
A speculative decoding variant where a small draft model generates tokens until it reaches a routing decision point, then the target model takes over if needed. Not directly applicable to our single-model setup, but relevant if we later add a 3B draft model (existing Ultron 0.1.1 3B model) alongside the 8B.

---

### 9. Anticheat Safety and Import Constraints

The relay/voice path in Ultron has a hard constraint: only `numpy`, `urllib`, `scipy`, `stdlib`, `rapidfuzz`, and light pure-Python allowed in the hot path. Heavy ML (EmbeddingGemma sidecar, llama-cpp-python) must be in the sidecar or inference.py.

For the router architecture, this means:
- The JSON schema definition is pure Python dict—safe.
- Grammar instantiation (`LlamaGrammar.from_json_schema`) happens inside `inference.py` (where llama-cpp-python already lives)—safe.
- The gate layers (EmbeddingGemma cosine, RapidFuzz, rules) are already correctly isolated in their sidecar paths.
- The structured output parsing (JSON decode of the header fields) is stdlib `json`—safe.
- The routing decision (dispatch based on `intent` field value) is pure Python branching—safe.

No anticheat risk from the architecture change itself. The main risk remains in the import firewall: ensure that no new heavy imports sneak into the relay dispatch path via the exemplar injector or prompt template builder.

---

## Concrete Techniques/Params We Should Adopt

1. **Primary architecture:** Three-tier cascade: `rules/RapidFuzz/Metaphone → EmbeddingGemma cosine gate → 8B single structured call`. The 8B is invoked only in the undecided band (~10-20% of turns).

2. **Single-call structured output for 8B turns:** Use `LlamaGrammar.from_json_schema()` with a tight 4-field schema (`intent` enum, `verbosity` enum, `think` bool, `response` str). Pass `grammar=` to llama-cpp-python's `create_completion`. Order fields with `intent` first so routing fires from the first ~5 tokens.

3. **Non-thinking by default:** Pass `/no_think` in the Ultron system prompt header. Override to `budget_tokens=200` (or 500) only for `marvel`, `lore`, `tactical_analysis` intents. Never enable thinking for `relay`, `social`, `snap`, `device_cmd` intents.

4. **Two-call only for thinking routing:** Implement a lightweight non-thinking "needs_thinking?" call (20-token response, ~400ms) for utterances that clear the embed gate but are ambiguous between thinking/non-thinking. This saves up to 50 seconds of thinking on relay turns.

5. **Per-intent prompt templates:** Keep each template under 1K tokens. Use MMR to inject top-3 exemplars from the relevant flavor library (relay exemplars for relay, social exemplars for social). Do NOT inject all 1628 tails into every prompt.

6. **Streaming-first TTS trigger:** Start Kokoro TTS on the first sentence boundary of the `response` field, not after full JSON is received. Implement a streaming JSON partial parser or simply stream the `response` field value directly (bypass full JSON parse).

7. **Intent-first validation gate:** After the structured output is received, validate `intent` is in expected enum; validate `response` is non-empty and reasonable length. If validation fails, fall back to a deterministic snap (e.g., "Understood." for a relay failure) rather than silence.

8. **Observability spans:** Log `{intent, verbosity, think, ttft_ms, tokens_prompt, tokens_gen, gate_method, gate_confidence}` per turn to `logs/usage_trace.jsonl`. Alert on `ttft_ms > 900ms` or `intent_distribution_shift > 20%` from baseline.

9. **Context budget:** Target `prompt_tokens < 1500` per call. System prompt ≤ 600 tokens, exemplars ≤ 600 tokens, conversation history ≤ 300 tokens. Trim oldest history turns when budget is exceeded.

10. **Speculative future (Ultron 1.1):** Use the existing Ultron 0.1.1 3B model as a draft model for speculative decoding against the 8B target. Expected 1.5-2.5x throughput gain on short relay responses (RTX 4090 data scales to ~1.3-2x on 4070 Ti). This is the RelayGen pattern (2602.06454) applied to our hardware.

---

## Risks/Caveats for Our Constraints

### Risk 1: TTFT Regression from Structured Header Tokens
Adding 15-20 JSON header tokens before the response body increases TTFT by ~375-500ms at 40 tok/s. This pushes local LLM TTFT from ~300ms (non-structured) to ~675ms (structured). Combined with STT (~200ms) and TTS (~100ms first audio), total mouth-to-ear ≈ 975ms—within the 1115ms target but tight. Measure empirically before committing.

**Mitigation:** Use a minimal schema (3 enum values for intent, not 6; remove `verbosity` from the header if it can be inferred from intent). Every token saved in the header is 25ms at 40 tok/s.

### Risk 2: Grammar Constraint Conflict with Thinking Mode
llama-cpp-python's grammar constraints may conflict with Qwen3's `<think>...</think>` thinking format. The thinking tokens are NOT valid JSON and will be suppressed by the grammar. This means thinking mode CANNOT be used with JSON schema grammar in the same call—you must choose one or the other.

**Mitigation:** For non-thinking turns (99% of relay/social), use JSON schema grammar. For thinking turns (Marvel, complex tactical), disable grammar and parse the `<think>` block + final answer via post-processing. Alternatively: use a two-call pattern where the thinking call is unconstrained and generates a final answer that you then relay.

### Risk 3: Schema Blowup with `response` Field
The `response` field in a JSON schema structured output is a `string`, but JSON strings require escaping quotes, backslashes, and newlines. This adds parsing complexity and may cause the model to generate awkward escaped text in the `response` field when it naturally wants to use quotes (which Ultron's persona often does for sarcasm/commands).

**Mitigation:** Either (a) post-process unescaping in Python (trivial), or (b) use a SPLIT approach: the first call generates a compact JSON header (`{"intent":"relay","verbosity":"low"}`), then the second streaming call generates the free-form response without schema constraints. This is a lighter two-call pattern where the "classify call" is only ~30 tokens (~750ms total including prefill)—borderline acceptable.

### Risk 4: Anticheat Firewall + Import-Time Side Effects
llama-cpp-python's `LlamaGrammar` class triggers import of additional grammar modules at class instantiation, not at import time. Verify that creating a `LlamaGrammar` instance from within `inference.py` does not trigger any imports that touch the blocked list. Run `assert_firewall_enforces()` after adding grammar support.

### Risk 5: VRAM Contention
Qwen3-8B Q5_K_M uses approximately 6GB VRAM. EmbeddingGemma-300M uses ~600MB VRAM. Total: ~6.6GB. The 10GB cap leaves ~3.4GB for KV cache. At context length 2K tokens × 32 layers × 2 (K+V) × 2 bytes (fp16) × 128 head_dim ≈ ~500MB KV cache per concurrent session. This is fine for single-user local use; would be a problem for multi-user.

### Risk 6: Qwen3-8B Instruction Following Quality at Q5_K_M
Abliterated + Josiefied finetuning on top of Q5_K_M may reduce reliable structured output compliance compared to the base Qwen3-8B. The 0.933 F1 score cited above is for the base model, not the abliterated finetune. Test the specific model checkpoint on a frozen test set of relay/social/ignore/marvel turns before deploying the structured header schema.

### Risk 7: Intent `"ignore"` False Negative
In the Valorant scenario, "ignore" (talking to teammates, stream, not Ultron) is the most latency-critical correct answer—we must NOT relay or generate. The structured output approach emits `intent="ignore"` and `response=""` but the model still generates ~15 JSON header tokens before reaching the empty response, wasting ~375ms and a KV cache slot.

**Mitigation:** The gate layers (rules/embed/fuzzy) should intercept most "ignore" turns before the 8B is called. For turns that reach the 8B with likely "ignore" classification, the context from the gate's near-miss score can be injected ("classifier confidence 0.68, likely external speech") to bias the model toward `intent=ignore` quickly.

---

## Sources

1. Twilio — "Core Latency in AI Voice Agents" (November 2025): https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents  
2. AssemblyAI — "Stream LLM responses in a voice pipeline: Tool calling, structured outputs, and real-time actions" (2025): https://www.assemblyai.com/blog/stream-llm-responses-voice-pipeline-tool-calling-structured-outputs-real-time-actions  
3. mkbctrl (GitHub Gist) — "Intent Recognition and Auto-Routing in Multi-Agent Systems" (2025): https://gist.github.com/mkbctrl/a35764e99fe0c8e8c00b2358f55cd7fa  
4. InsiderLLM — "Best Local LLMs for Function Calling: Qwen 3.6, Gemma 4" (June 2025): https://insiderllm.com/guides/function-calling-local-llms/  
5. ReveoAI (Medium) — "Solving Voice AI Latency: From 5 Seconds to Sub-1 Second Responses" (2025): https://medium.com/@reveoai/solving-voice-ai-latency-from-5-seconds-to-sub-1-second-responses-d0065e520799  
6. Daily.co — "Benchmarking LLMs for Voice Agent Use Cases" (2025): https://www.daily.co/blog/benchmarking-llms-for-voice-agent-use-cases/  
7. bitbytes.io — "How AI Voice Agent Architecture Works (2026)": https://www.bitbytes.io/blog/ai-voice-speech-tools/ai-voice-agent-architecture-pipeline  
8. Nick Tikhonov — "How I built a sub-500ms latency voice agent from scratch" (2025): https://www.ntik.me/posts/voice-agent  
9. arxiv 2603.20895 — "LLM Router: Rethinking Routing with Prefill Activations" (2026): https://arxiv.org/html/2603.20895  
10. arxiv 2601.04426 — "XGrammar-2: Efficient Dynamic Structured Generation Engine for Agentic LLMs" (ACM CAIS '26): https://arxiv.org/pdf/2601.04426  
11. arxiv 2504.10519 — "Toward Super Agent System with Hybrid AI Routers" (April 2025): https://arxiv.org/pdf/2504.10519  
12. arxiv 2505.09388 — "Qwen3 Technical Report" (May 2025): https://arxiv.org/pdf/2505.09388  
13. arxiv 2510.08731 — "When to Reason: Semantic Router for vLLM" (October 2025): https://arxiv.org/pdf/2510.08731  
14. arxiv 2604.06753 — "Select-then-Solve: Paradigm Routing as Inference-Time Optimization for LLM Agents" (April 2026): https://arxiv.org/pdf/2604.06753  
15. arxiv 2603.00030 — "SimpleTool: Parallel Decoding for Real-Time LLM Function Calling" (March 2026): https://arxiv.org/pdf/2603.00030  
16. arxiv 2602.06454 — "RelayGen: Intra-Generation Model Switching for Efficient Reasoning" (February 2026): https://arxiv.org/pdf/2602.06454  
17. DeepWiki — "Grammar-Based Generation in llama-cpp-python": https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation  
18. OpenReview — "Fast Intent Classification for LLM Routing via Statistical Analysis of Representations": https://openreview.net/forum?id=UMuVvvIEvA  
19. Groundcover — "AI Agent Observability Guide: Telemetry, Traces, Metrics, and Evals" (2025): https://www.groundcover.com/learn/observability/ai-agent-observability  
20. getMaxim — "Top 5 LLM Router Solutions in 2026": https://www.getmaxim.ai/articles/top-5-llm-router-solutions-in-2026/  
21. Qwen docs — "llama.cpp integration for Qwen3": https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html  
22. LocalLLM.in — "llama.cpp VRAM Requirements: Complete 2026 Guide": https://localllm.in/blog/llamacpp-vram-requirements-for-local-llms  
