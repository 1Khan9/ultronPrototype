# llama-cpp-python 0.3.x deep dive: grammar + logit_bias, speculative decoding, KV-cache quantization + flash-attention, n_batch/n_ubatch tuning on Ada (RTX 4070 Ti), and known crash modes

Research date: 2026-06-20. Covers llama-cpp-python ≤0.3.22 (our pinned version) and the underlying llama.cpp ggml-org/llama.cpp master branch up to ~June 2026.

---

## TL;DR recommendation for Ultron 1.0

| Area | Recommendation | Confidence |
|---|---|---|
| **Grammar / structured output** | Use `LlamaGrammar.from_json_schema()` for deterministic routing output; do NOT combine grammar with thinking/enable_thinking simultaneously — it silently disables grammar enforcement (open bug as of March 2026) | High |
| **logit_bias** | Safe for token steering (e.g., boosting `</think>` to terminate thinking cheaply). Use `Dict[int, float]` in `create_completion()`. Unreliable with some CUDA builds for strong suppression (`-100` bans) | Medium |
| **Speculative decoding** | Prompt-lookup n-gram (`--spec-draft-type ngram-simple`) is zero-VRAM-cost and safe; skip draft-model speculative decoding — no compatible small Qwen3 draft model exists and the post-Apr 2026 reasoning-budget sampler introduces silent hang risk | High |
| **KV cache quant + flash-attn** | `type_k="q8_0"`, `type_v="q8_0"`, `flash_attn=True` — safe, symmetric, activates the fused Flash Attention path. Do NOT mix q8_0-K + q4_0-V (asymmetric → silent fallback to slow non-fused path) | High |
| **n_batch / n_ubatch** | For single-turn voice relay (short decode, short prompt): `n_batch=512`, `n_ubatch=512`. Larger values (2048) give diminishing returns at batch-size-1 decode. CUDA Graphs enabled by default for batch-size-1; keep batch at 1 for voice path | High |
| **Reasoning / thinking budget** | Set `reasoning_budget` (or `--reasoning-budget N`) to ~512–1024 for Qwen3 thinking mode. Without a cap, default is INT_MAX — model hangs indefinitely on builds from April 2026 onward | Critical |
| **Windows / CUDA wheels** | v0.3.22 re-enabled Windows CUDA wheels after a period where they were disabled. Pin to 0.3.22 (cu122 or cu124 wheel) | High |

---

## Findings

### 1. Grammar-Based Generation (GBNF / JSON Schema)

#### How it works
llama.cpp uses GBNF (Graydon's Backus-Naur Form) to constrain token sampling. At each sampling step, logits for tokens that would violate the grammar are set to `-inf` before any sampling. This is enforced inside `LlamaSampler` via `llama_sampler_chain`.

The Python-level API (llama-cpp-python):

```python
from llama_cpp import Llama, LlamaGrammar

llm = Llama(model_path="model.gguf", n_gpu_layers=-1)

# From raw GBNF
grammar = LlamaGrammar.from_string('root ::= "RELAY" | "PRIVATE" | "IGNORE"')

# From JSON Schema (recommended for structured routing output)
schema = '{"type":"object","properties":{"intent":{"type":"string","enum":["RELAY","PRIVATE","IGNORE"]}},"required":["intent"]}'
grammar = LlamaGrammar.from_json_schema(schema)

result = llm.create_completion(prompt, grammar=grammar, max_tokens=32)
```

The `SchemaConverter` class handles `$ref` pointers and recursive schemas. A `SPACE_RULE` prevents runaway whitespace that degrades generation throughput.

Source: [DeepWiki: Grammar-Based Generation in llama-cpp-python](https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation); [llama.cpp grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)

#### GBNF syntax notes relevant to Ultron 1.0

- Non-terminals: dashed lowercase (`relay-intent`)
- Terminal ranges support Unicode; negation with `^` prefix
- Repetition: `*`, `+`, `?`, `{m}`, `{m,n}` all supported
- Token-level matching via `<[token-id]>` or `<token>` — useful for matching EOS or `</think>`
- **Performance gotcha**: avoid patterns like `x? x? x?` — use `x{0,3}` instead; repeated optionals cause exponential sampling overhead
- `additionalProperties` defaults to `false` in JSON Schema conversion
- Nested `$ref`s are broken in the C++ version
- `uniqueItems`, `contains`, conditionals, remote `$ref` — all unsupported

#### CRITICAL BUG: Grammar + Thinking = Grammar enforcement disabled

GitHub issue #20345 (filed 2026-03-10, **still open as of June 2026**):

> When `response_format` (JSON schema → grammar) is combined with `enable_thinking: true`, grammar enforcement is completely inactive. The model produces unconstrained output violating the schema.

This affects llama.cpp builds from commit `d088d5b` onward (which includes the autoparser from PR #18675).

**Workaround**: Never combine grammar constraints with thinking mode in the same call. For the Ultron 1.0 intent gate:
- If doing thinking-mode classification, skip grammar — parse the response manually or use regex post-processing
- If using grammar for strict structured output, disable thinking (`enable_thinking=False` / omit `<think>` budget)

Related: issue #12196 documents a server crash when lazy grammars encounter `</think>` tokens in the stack. Reproducible with `llama-server` + lazy grammar + Qwen3 thinking models.

Source: [Issue #20345](https://github.com/ggml-org/llama.cpp/issues/20345); [Issue #12196 Crash on lazy grammar](https://github.com/ggml-org/llama.cpp/issues/12196)

---

### 2. logit_bias

#### API
```python
# Dict[int, float] — token_id (int) → additive logit bias (float)
logit_bias = {
    151668: 10.0,   # boost </think> to end thinking early
    151649: -100.0, # suppress <think> to prevent entering thinking mode
}
result = llm.create_completion(prompt, logit_bias=logit_bias, max_tokens=256)
```

In the OpenAI-compatible server, the format is a list of `[token_id, bias]` pairs. The in-process Python API uses `Dict[int, float]`.

#### Thinking budget via logit_bias (Ultron 1.0 relevance)
The llama.cpp reasoning-budget update (2026) describes a soft approach: ramp up logit weight of `</think>` as the budget runs low, then hard-force at the limit. Before the formal `--reasoning-budget` sampler existed, this logit_bias trick was the only way to cap thinking length.

For Qwen3 models, the `</think>` token ID must be looked up from the tokenizer. Example (Qwen3 8B):
```python
end_think_id = llm.tokenize(b"</think>", add_bos=False, special=True)[-1]
logit_bias = {end_think_id: 8.0}  # strong push toward ending thinking
```

#### Known reliability issues
- GitHub issue #13605: logit_bias via `-l` flag does not suppress tokens in Kimi K2.5 on CUDA backend (status: stale/unconfirmed). Suggests CUDA-path logit_bias may have a masking ordering bug for strong negative values.
- For hard token bans (`-100`), the grammar approach is more reliable than logit_bias since grammar zeroes logits before sampling, while logit_bias applies before softmax but depends on the sampler chain order.

Source: [Issue #827 logit_bias in-process](https://github.com/abetlen/llama-cpp-python/issues/827); [Issue #13605 logit-bias CUDA bug](https://github.com/ggml-org/llama.cpp/issues/13605)

---

### 3. Speculative Decoding

#### Available modes in llama.cpp (0.3.22 era)

| Mode | Type constant | VRAM overhead | Notes |
|---|---|---|---|
| Draft model | `COMMON_SPECULATIVE_TYPE_DRAFT_SIMPLE` | Full second model | Requires vocab-compatible small model |
| N-gram simple | `COMMON_SPECULATIVE_TYPE_NGRAM_MAP_K` | ~0 MB | Looks up prior n-gram matches in history |
| N-gram cache | `COMMON_SPECULATIVE_TYPE_NGRAM_CACHE` | ~16 MB | Statistics + persistence support |
| N-gram mod | ~16 MB lightweight hasher | ~16 MB | LCG hash, variable draft lengths |
| EAGLE/MTP | Self-speculative head | Head weights only | Requires EAGLE-specific checkpoint |

Source: [llama.cpp docs/speculative.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md); [DeepWiki speculative decoding](https://deepwiki.com/ggml-org/llama.cpp/8.3-speculative-decoding)

#### Draft model performance (reference benchmarks, consumer GPU)

| Config | Draft tokens | Speedup |
|---|---|---|
| Llama 3.1 8B + Llama 3.2 1B | 5 | 1.83× |
| Qwen 2.5 32B + 0.5B | 4 | 1.84× |
| Coding tasks, 0.5B draft | 8–10 | 2.5–2.9× |
| General text, 1.5B draft | 4 | 1.63× |
| General text, 3B draft | 4 | 1.33× |

Key insight: **draft model must be from the same model family** (ideally distilled). Qwen 2.5, Llama 3.x pairs work because they share vocabulary AND distillation. A randomly-paired model (e.g., Gemma 2B drafting Llama 8B) may provide zero speedup.

Source: [GitHub Discussion #10466](https://github.com/ggml-org/llama.cpp/discussions/10466); [LM Studio 0.3.10 speculative decoding](https://lmstudio.ai/blog/lmstudio-v0.3.10)

#### Vocabulary compatibility constraint
Draft and target models must match:
- `llama_vocab_type` (exact type match)
- BOS/EOS token IDs and their special-token flags
- Token string mappings (byte-for-byte)

This means **no existing public small model is compatible with Josiefied-Qwen3-8B-abliterated** unless it was specifically distilled from Qwen3. The base Qwen3-0.6B would be the closest candidate, but the abliteration/fine-tuning may have altered the tokenizer in ways that break the strict validation checks.

#### Prompt-lookup n-gram (recommended for Ultron 1.0)
```python
# In llama-cpp-python, prompt-lookup can be enabled via n_draft + lookup params
# For the Python API, enable via the underlying Llama params:
llm = Llama(
    model_path="qwen3-8b.gguf",
    n_gpu_layers=-1,
    # Speculative draft via n-gram lookup (no second model needed):
    # Note: direct Python API for ngram spec is limited in 0.3.22 — 
    # better accessed via llama_cpp.llama_speculative_* low-level API
)
```

The n-gram approach:
- Zero additional VRAM (scans existing context, ~16 MB for the mod hasher)
- Acceptance rate ~0.57–0.70 in practice (from docs/speculative.md example stats)
- Works well when the relay output echoes input phrases (team relay content repeats tactical callouts)
- 1.1–1.5× speedup on short deterministic sequences; ~1.13× on mixed content
- No vocab compatibility requirement — same model, same vocab

#### Post-April 2026 reasoning-budget sampler hang (CRITICAL)
Builds from commit `d088d5b` onward (April 10, 2026+) auto-register thinking tags and activate the reasoning-budget sampler with `INT_MAX` default. Without setting `--reasoning-budget N`, models with thinking tags hang indefinitely.

This affects llama-cpp-python 0.3.20+ (built against post-Apr 2026 llama.cpp). **Workaround**: always set `reasoning_budget` or use the `sampler` chain with an explicit budget, or pass `--reasoning-budget 0` to disable thinking entirely.

Source: [forge issue #54: reasoning budget silent hang](https://github.com/antoinezambelli/forge/issues/54); [r/LocalLLaMA reasoning budget tracking](https://insights.marvin-42.com/articles/rlocalllama-tracks-llamacpps-new-reasoning-budget-controls)

---

### 4. KV Cache Quantization + Flash Attention

#### The symmetric rule (critical)
Flash Attention in llama.cpp uses a **fused kernel path** that requires K and V cache types to match (symmetric). If they differ (asymmetric, e.g., `q8_0-K` + `q4_0-V`), the runtime silently falls back to a non-fused, non-optimized attention path with no warning or log message.

Confirmed: [GitHub Discussion #22411 — Symmetric KV cache quantization enables the fast fused Flash Attention path](https://github.com/ggml-org/llama.cpp/discussions/22411)

#### Safe symmetric configurations for CUDA (RTX 4070 Ti)

| Config | VRAM vs F16 | Speed impact | Quality impact | Notes |
|---|---|---|---|---|
| `f16 / f16` | 1.0× (baseline) | baseline | baseline | Default |
| `q8_0 / q8_0` | ~0.5× | +10–38% (context dependent) | Negligible | **Recommended** |
| `q4_0 / q4_0` | ~0.25× | −3% at 8K, −35% at 64K, −92% at 64K prompt | Noticeable | Problematic at long contexts |

The q4_0 performance paradox: at 64K context, q4_0 is **92% slower** than f16 for prompt processing due to dequantization overhead, and actually uses more memory than f16 for small contexts. **q4_0 is NOT recommended** for our use case.

Source: [NVIDIA Developer Forums: KV Cache Benchmarks DGX Spark](https://forums.developer.nvidia.com/t/kv-cache-quantization-benchmarks-on-dgx-spark-q4-0-vs-q8-0-vs-f16-llama-cpp-nemotron-30b-128k-context/365138); [Medium: Optimize GPU KV Cache](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec)

#### Concrete VRAM math for Ultron 1.0 (Qwen3 8B Q5_K_M, 10GB cap)

Model weights: Qwen3-8B Q5_K_M ≈ 5.5–5.7 GB
Context window: target 2048 tokens (voice relay, short turns)
KV cache with f16: 2048 × 32 layers × 2 (K+V) × 128 head_dim × 2 bytes ≈ ~512 MB
KV cache with q8_0: ~256 MB (halved)

Budget: ~10 GB cap → model 5.7 GB + overhead 0.5 GB + q8_0 KV 256 MB = ~6.45 GB. Leaves ~3.5 GB headroom for EmbeddingGemma sidecar (sits in separate process, so GPU VRAM only used by llama-cpp-python's in-process load — EmbeddingGemma uses its own allocation).

Flash attention at q8_0 symmetric frees ~20–30% VRAM vs non-fused paths by eliminating the attention score materialization.

#### Python API parameters

```python
llm = Llama(
    model_path="qwen3-8b-q5_k_m.gguf",
    n_gpu_layers=-1,          # full GPU offload
    n_ctx=2048,               # voice relay context window
    n_batch=512,              # physical batch size
    n_ubatch=512,             # micro-batch (optimal for decode)
    flash_attn=True,          # enable Flash Attention
    type_k=ggml_type.GGML_TYPE_Q8_0,   # KV key cache quantization
    type_v=ggml_type.GGML_TYPE_Q8_0,   # KV value cache quantization
    offload_kqv=True,         # keep KV cache on GPU (default True)
)
```

Note: `type_k` and `type_v` were exposed in the `Llama()` constructor as of the `offload_kqv` work in v0.2.24. They remain in 0.3.22. Confirm the enum via `from llama_cpp.llama_types import *` or pass the int literal (ggml type `q8_0` = 8).

#### TurboQuant (experimental — do NOT use in production)
Discussion #20969 proposes TQ3 (3.25 bit) and TQ4 (4.25 bit) formats using randomized Hadamard transforms. Currently **not merged into llama.cpp main**. Multiple forks with varying maturity. Quality holds on 35B+ models but degrades on 8B and smaller. Skip for 1.0.

Source: [TurboQuant Discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)

---

### 5. n_batch / n_ubatch Tuning on Ada (RTX 4070 Ti)

#### What each controls
- `n_batch`: total token capacity of the input `llama_batch` structure — the maximum the engine will accept in one call
- `n_ubatch`: the micro-batch (ubatch) size into which the batch is subdivided for compute. Controls GPU kernel dispatch granularity.

For **single-token decode** (voice relay hot path): only 1 token is processed per step. Both `n_batch` and `n_ubatch` are irrelevant for decode throughput in this regime — the bottleneck is memory bandwidth, not compute.

For **prefill** (system prompt + context ingestion at startup or cache miss): larger `n_ubatch` = bigger matrix multiplications = better GPU utilization.

#### CUDA Graphs interaction
CUDA Graphs are now **enabled by default for batch-size-1 inference** on NVIDIA GPUs in llama.cpp main branch. This gives ~10–20% latency reduction at batch=1 decode by collapsing per-kernel launch overhead into a single graph submission. No tuning required — it's automatic.

Restriction: CUDA Graphs are currently batch-size-1 only. Larger batch sizes (for parallel slot serving, not relevant for single-voice use) fall back to standard kernel dispatch.

Source: [NVIDIA Blog: Optimizing llama.cpp AI Inference with CUDA Graphs](https://developer.nvidia.com/blog/optimizing-llama-cpp-ai-inference-with-cuda-graphs/)

#### Recommended starting values

| Parameter | Voice relay hot path | Justification |
|---|---|---|
| `n_batch` | 512 | Prefill of prompt + system context; no need for 2048 at 2K ctx |
| `n_ubatch` | 512 | Matches Ada SM cache working set; ≥512 shows diminishing returns |
| `n_ctx` | 2048 | Voice turns are short; saves VRAM vs 4096+ |

Community benchmark (GitHub Discussion #18308): ubatch values of 512, 1024, and 2048 all produced ~295–298 t/s in parallel multi-slot serving tests, confirming diminishing returns above 512. The bottleneck shifts to CPU-side sampling work at higher parallelism.

A dramatic counter-example exists: one user boosted ubatch to 64 to match AMD GPU L3 cache, pushing Qwen3.5-27B prompt speed from 59 → 582 t/s. This was an AMD-specific pathology (mismatch between default value and hardware). For Ada (Ada Lovelace, sm_89), the default 512 is generally appropriate.

Source: [GitHub Discussion #18308](https://github.com/ggml-org/llama.cpp/discussions/18308)

---

### 6. Thinking Mode (Qwen3 8B) — Specific Guidance

#### Enabling/disabling thinking in llama-cpp-python 0.3.22

Qwen3 models support thinking mode via special tokens: `<think>` / `</think>`. In llama.cpp, there are now two control planes:

**1. Chat template level** (`enable_thinking` in chat_completion):
```python
result = llm.create_chat_completion(
    messages=[...],
    enable_thinking=True,    # generates <think>...</think> block
    # OR
    enable_thinking=False,   # suppresses thinking (adds /no_think system prefix)
)
```

**2. Reasoning budget sampler** (`reasoning_budget`):
- Set to `-1` (default in older builds): unlimited thinking
- Set to `0`: no thinking (hard disable)
- Set to `N > 0`: hard token budget, terminates at N thinking tokens
- **Post-April 2026 builds**: default is `INT_MAX` which causes silent hang — always set explicitly

**3. logit_bias soft steering** (alternative to hard budget):
```python
# Get the </think> token ID first
think_end_tokens = llm.tokenize(b"</think>", add_bos=False, special=True)
end_think_id = think_end_tokens[-1]

# Boost </think> to terminate thinking after ~N tokens via callback/streaming
logit_bias = {end_think_id: 8.0}  # strong push; use 15.0 for near-force
```

Known issue: `enable_thinking: False` with `--reasoning-format none` does NOT reliably suppress `<think>` tags in some builds (issues #13189, #20182). Workaround: use `logit_bias` to ban `<think>` token + set `reasoning_budget=0`.

**Performance impact on HumanEval coding** (community benchmark):
- Full thinking (no budget): 94% accuracy
- No thinking at all: 88%
- Hard budget with cutoff: 78% (mid-sentence termination hurts quality)
- Budget + transition message (`--reasoning-budget-message`): 89%

For Ultron 1.0 relay path: thinking is low-value for short tactical relay (adds 500–2000ms latency for marginal quality gain on "tell my team Jett hit 84"). Budget=0 (thinking disabled) for relay snaps; small budget (128–256 tokens) for genuinely ambiguous private-reply LLM calls.

---

### 7. llama-cpp-python 0.3.22 — Key Version Facts

- Release date: approximately **May 2, 2026**
- Pinned llama.cpp commit: corresponds to mid-April to early May 2026 llama.cpp state (includes the reasoning-budget sampler — see hang risk above)
- **Windows CUDA wheels re-enabled** in 0.3.22 after a period of disablement (0.3.3 had previously re-enabled them; they were disabled again at some point before 0.3.22)
- v0.3.16 added `flash_attn` parameter to `Llama()` constructor and `ModelSettings`
- v0.3.0 redesigned sampler API to use `sampler chain` — old per-parameter sampling (temperature, top_k as individual kwargs) is now internally converted to chain nodes
- v0.3.2 fixed JSON strings grammar (blacklisted control-character token sets)
- v0.3.6 fixed grammar printing bug (repeated output per call)
- v0.3.1 fixed speculative decoding regression
- v0.3.24 (post-0.3.22) fixes cleanup errors for partially initialized `LlamaModel` objects — relevant if using the `LlamaModel` low-level API directly

Source: [llama-cpp-python CHANGELOG.md](https://github.com/abetlen/llama-cpp-python/blob/main/CHANGELOG.md); [Changelog docs](https://llama-cpp-python.readthedocs.io/en/latest/changelog/)

---

## Concrete techniques/params we should adopt

### A. Llama() constructor (production config)
```python
from llama_cpp import Llama
import llama_cpp

llm = Llama(
    model_path="E:/UltronModels/josiefied-qwen3-8b-abliterated-q5_k_m.gguf",
    n_gpu_layers=-1,           # all layers on GPU (fits 10GB with q8_0 KV)
    n_ctx=2048,                # voice relay context; upgrade to 4096 for private-reply LLM turns
    n_batch=512,               # prompt prefill batch size
    n_ubatch=512,              # micro-batch; Ada Lovelace sweet spot
    flash_attn=True,           # enable Flash Attention (required for KV quant fast path)
    type_k=8,                  # GGML_TYPE_Q8_0 — symmetric KV quantization
    type_v=8,                  # GGML_TYPE_Q8_0 — MUST match type_k for fused FA path
    offload_kqv=True,          # KV cache on GPU (default, confirm it's not overridden)
    verbose=False,             # suppress llama.cpp stdout in production
)
```

### B. Relay inference call (no thinking, grammar for intent gate)
```python
from llama_cpp import LlamaGrammar

INTENT_SCHEMA = '{"type":"string","enum":["RELAY","PRIVATE","IGNORE"]}'
intent_grammar = LlamaGrammar.from_json_schema(INTENT_SCHEMA)

result = llm.create_completion(
    prompt=formatted_intent_prompt,
    grammar=intent_grammar,         # only works if thinking is OFF
    max_tokens=16,
    temperature=0.0,                # deterministic for gate
    logit_bias=None,
)
intent = result["choices"][0]["text"].strip()
```

### C. LLM relay rephrase call (thinking-mode, no grammar)
```python
# Get </think> token ID once at startup
end_think_id = llm.tokenize(b"</think>", add_bos=False, special=True)[-1]

result = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": RELAY_REPHRASE_SYSTEM},
        {"role": "user", "content": relay_user_msg},
    ],
    enable_thinking=True,
    max_tokens=256,
    temperature=0.7,
    # Budget-soft approach: ramp up </think> logit as we approach limit
    # (implement via streaming + per-token logit_bias update)
    # OR: use hard reasoning_budget parameter when exposed in Python API
)
```

### D. Prompt-lookup n-gram speculative decoding (optional VRAM-free speedup)
```python
# Access via low-level llama_cpp API (0.3.22 does not cleanly expose
# ngram spec in high-level Llama() — check if llama_speculative_ngram
# is wrapped; otherwise use llama.cpp CLI for testing first)
# CLI test:
# llama-cli -m model.gguf --spec-draft-type ngram-simple \
#   --spec-draft-n-max 3 -c 2048 -ngl -1
```

### E. Thinking termination for Qwen3 (production-safe)
```python
# Option 1: disable entirely for relay path (recommended for short tactical relay)
result = llm.create_chat_completion(messages=[...], enable_thinking=False)

# Option 2: short budget for ambiguous/private-reply path
result = llm.create_chat_completion(
    messages=[...],
    enable_thinking=True,
    # If reasoning_budget is exposed in your 0.3.22 build:
    # reasoning_budget=256,
    # Otherwise, logit-bias the </think> token:
    logit_bias={end_think_id: 12.0},
    max_tokens=512,
)
```

---

## Risks/caveats for our constraints

### R1: Grammar + thinking mutual exclusion
**Risk**: If future Ultron 1.0 intent gate tries to use JSON Schema grammar output AND Qwen3 thinking for better classification quality, the combination silently disables grammar. The model will output unconstrained text.
**Mitigation**: Strict architectural separation — thinking path uses text parsing/regex, grammar path uses thinking=False. Document this as a hard invariant in the Ultron 1.0 architecture.

### R2: Reasoning-budget sampler hang (post-April 2026 builds)
**Risk**: llama-cpp-python 0.3.22 was built against a mid-April–May 2026 llama.cpp revision that auto-registers thinking tags with `INT_MAX` budget by default. Any Qwen3 call without an explicit budget cap on a thinking-capable model may hang indefinitely if the model enters a thinking phase.
**Mitigation**: Always pass `reasoning_budget=0` (relay path) or `reasoning_budget=N` (LLM path) when thinking is enabled. Implement a generation timeout watchdog in the orchestrator.

### R3: logit_bias reliability on CUDA for hard suppression
**Risk**: Strong negative logit_bias (`-100` to ban a token) may not reliably suppress tokens on CUDA backends per issue #13605 (unconfirmed, stale, affects Kimi K2.5 specifically — may not affect Qwen3).
**Mitigation**: Use grammar constraints instead of logit_bias for hard bans. Use logit_bias only for soft steering (positive boosts to guide toward `</think>`). Test on our specific model+GPU.

### R4: Asymmetric KV cache quantization silent fallback
**Risk**: If `type_k` and `type_v` are set to different values (e.g., a future "optimization" sets K=q8_0, V=q4_0), Flash Attention silently falls back to the slow non-fused path. Performance degrades 30–40% with no log warning.
**Mitigation**: Always use matching (symmetric) K+V types. Codify as a check in `inference.py` constructor validation: `assert type_k == type_v if flash_attn else True`.

### R5: Draft model speculative decoding — no compatible Qwen3 small model
**Risk**: The abliteration fine-tune of Qwen3-8B may have altered token weights in ways that break the strict vocab validation for draft-model speculative decoding. Even if Qwen3-0.6B exists, it needs byte-for-byte token string compatibility.
**Mitigation**: Do not attempt draft-model spec decoding for 1.0. Use n-gram lookup only. Revisit if/when Qwen3-0.6B abliterated distill becomes available.

### R6: Windows CUDA wheel stability in 0.3.22
**Risk**: Windows CUDA wheels have been repeatedly disabled and re-enabled across versions. 0.3.22 re-enables them, but there may be unresolved issues inherited from the period they were disabled.
**Mitigation**: Build from source with our specific CUDA version if wheel installs exhibit crashes. The existing working Ultron 0.1.1 build (llama-cpp-python working on this system) provides a known-good baseline. Upgrade carefully; test after each llama-cpp-python version bump.

### R7: VRAM budget with flash_attn + q8_0 at higher context
**Risk**: If we ever need `n_ctx=8192` for longer private-reply reasoning chains, KV cache at q8_0 ≈ 1 GB, total ≈ 7.2 GB — still within 10 GB cap, but leaves less headroom.
**Mitigation**: Keep relay path at n_ctx=2048. Use a separate inference context (or dynamic n_ctx upgrade) for long private-reply sessions. Never exceed n_ctx=4096 on the voice relay path.

### R8: Anticheat safety
The llama-cpp-python hot path imports: `ctypes`, `numpy`, `os`, `pathlib`, `struct`, `subprocess`. All stdlib or numpy. The grammar/logit_bias/speculative decoding features are all handled inside the `.dll`/`.so` — no additional Python-level ML framework imports. **Anticheat-clean**: the relay path stays within the existing import firewall constraints.

---

## Sources

- [DeepWiki: Grammar-Based Generation in llama-cpp-python](https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation)
- [DeepWiki: Grammar and Structured Output in llama.cpp](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output)
- [llama.cpp grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- [llama.cpp Issue #20345: Grammar enforcement disabled when thinking is enabled](https://github.com/ggml-org/llama.cpp/issues/20345)
- [llama.cpp Issue #12196: Crash on lazy grammar with thinking](https://github.com/ggml-org/llama.cpp/issues/12196)
- [llama.cpp Issue #13189: Persistent think tags despite enable_thinking: False](https://github.com/ggml-org/llama.cpp/issues/13189)
- [llama.cpp Issue #20182: enable_thinking cannot turn off thinking for Qwen3.5](https://github.com/ggml-org/llama.cpp/issues/20182)
- [llama-cpp-python Issue #827: logit_bias outside server](https://github.com/abetlen/llama-cpp-python/issues/827)
- [llama.cpp Issue #13605: logit-bias doesn't seem to work (CUDA)](https://github.com/ggml-org/llama.cpp/issues/13605)
- [llama.cpp docs/speculative.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md)
- [DeepWiki: Speculative Decoding in llama.cpp](https://deepwiki.com/ggml-org/llama.cpp/8.3-speculative-decoding)
- [GitHub Discussion #10466: Speculative decoding on consumer GPUs](https://github.com/ggml-org/llama.cpp/discussions/10466)
- [LM Studio Blog: Speculative Decoding in 0.3.10](https://lmstudio.ai/blog/lmstudio-v0.3.10)
- [GitHub Discussion #22411: Symmetric KV cache quantization + Flash Attention fused path](https://github.com/ggml-org/llama.cpp/discussions/22411)
- [NVIDIA Developer Forums: KV Cache Quantization Benchmarks (q4_0 vs q8_0 vs f16)](https://forums.developer.nvidia.com/t/kv-cache-quantization-benchmarks-on-dgx-spark-q4-0-vs-q8-0-vs-f16-llama-cpp-nemotron-30b-128k-context/365138)
- [Medium: Optimize Your GPU KV-Cache for Llama.cpp](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec)
- [GitHub Discussion #20969: TurboQuant Extreme KV Cache Quantization](https://github.com/ggml-org/llama.cpp/discussions/20969)
- [GitHub Issue #21450: Metal mixed quantized KV + Flash Attention failure](https://github.com/ggml-org/llama.cpp/issues/21450)
- [GitHub Discussion #18308: Optimal parameters for parallel inference (n_ubatch)](https://github.com/ggml-org/llama.cpp/discussions/18308)
- [NVIDIA Blog: Optimizing llama.cpp AI Inference with CUDA Graphs](https://developer.nvidia.com/blog/optimizing-llama-cpp-ai-inference-with-cuda-graphs/)
- [forge Issue #54: Reasoning budget sampler silent hang after April 2026 builds](https://github.com/antoinezambelli/forge/issues/54)
- [llama.cpp Issue #20632: Graceful reasoning budget termination](https://github.com/ggml-org/llama.cpp/issues/20632)
- [r/LocalLLaMA: llama.cpp reasoning budget controls](https://insights.marvin-42.com/articles/rlocalllama-tracks-llamacpps-new-reasoning-budget-controls)
- [llama-cpp-python CHANGELOG.md](https://github.com/abetlen/llama-cpp-python/blob/main/CHANGELOG.md)
- [llama-cpp-python Changelog (readthedocs)](https://llama-cpp-python.readthedocs.io/en/latest/changelog/)
- [llama-cpp-python Releases (GitHub)](https://github.com/abetlen/llama-cpp-python/releases)
- [Zach Mueller: Limiting Qwen3's Thinking](https://muellerzr.github.io/til/end_thinking.html)
- [DEV Community: Speculative Decoding on home GPU cluster](https://dev.to/defilan/i-tested-speculative-decoding-on-my-home-gpu-cluster-heres-why-it-didnt-help-3ej6)
- [DEV Community: Q4 KV Cache fit 32K context into 8GB VRAM](https://dev.to/plasmon_imp/q4-kv-cache-fit-32k-context-into-8gb-vram-only-math-broke-209k)
- [llama.cpp Feature Request Issue #20632: Reasoning budget graceful termination](https://github.com/ggml-org/llama.cpp/issues/20632)
