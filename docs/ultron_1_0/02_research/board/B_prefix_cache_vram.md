# Prompt Prefix Caching in llama-cpp-python In-Process + VRAM Budgeting for Ultron 1.0

**Research date:** 2026-06-20  
**Scope:** llama-cpp-python 0.3.x in-process (not the server), KV retention across calls, LlamaRAMCache, save/load KV state, measured prefill savings, cache invalidation on variable suffixes, plus VRAM math for 8B Q5_K_M + KV + EmbeddingGemma-300M sidecar under a 10 GB cap.

---

## TL;DR Recommendation for Ultron 1.0

**Do all four of these together:**

1. **Attach a `LlamaRAMCache` at startup** — 256–512 MB capacity, keyed to the Qwen3-8B instance. This gives free prefix reuse for the fixed Ultron system-prompt block across every turn. No code changes needed at call sites; `llama.set_cache(ram_cache)` is sufficient.

2. **Quantize the KV cache to Q8_0** — pass `type_k=llama_cpp.GGML_TYPE_Q8_0, type_v=llama_cpp.GGML_TYPE_Q8_0` plus `flash_attn=True` at construction. Cuts active KV VRAM by ~50 % with negligible quality loss for NLG tasks. **Requires Flash Attention** — without FA the quantized tensors must be dequantized on every attention step, costing more, not less.

3. **Keep the system prompt at the very front of every prompt, byte-identical** — the prefix cache hits only as long as the leading tokens are identical. Routing logic must never prepend per-turn variable content before the static system prompt.

4. **Keep EmbeddingGemma-300M in its own subprocess (sidecar)** — it already is in Ultron 0.x. Do NOT bring it in-process. It competes for VRAM and can evict the LLM's allocated pages; as a subprocess it runs CPU-side, keeping VRAM entirely for the 8B + KV cache.

**Budget math for 10 GB cap (n_ctx=4096, Q8_0 KV):**  
`5.5 GB (weights) + 0.7 GB (KV @ 4096 tokens, Q8_0) + 0.5 GB (CUDA graphs/overhead) ≈ 6.7 GB`  
This leaves **~3.3 GB headroom** — ample for speculative decoding (a 1B draft would need ~700 MB) or a longer context window.

---

## Findings

### 1. The In-Process Cache Object: LlamaRAMCache and LlamaDiskCache

llama-cpp-python exposes a Python-level cache abstraction through three classes in `llama_cpp/llama_cache.py`:

- **`BaseLlamaCache`** — abstract base, defines `capacity_bytes`, abstract `cache_size`, `__getitem__`, `__contains__`, `__setitem__`, and the static `_find_longest_prefix_key()` comparator.
- **`LlamaRAMCache`** — concrete in-memory implementation backed by Python's `collections.OrderedDict`. Stores `LlamaState` objects (serialised native KV blobs). LRU eviction: on insert, oldest entries are popped until `cache_size < capacity_bytes`. On access, the matched key is moved to the end. Default capacity: 2 GiB (configurable at construction via `capacity_bytes`).
- **`LlamaDiskCache`** — same semantics, but backed by the `diskcache` SQLite library; survives process restarts. Default location: `.cache/llama_cache`. Slower than RAM cache for warm hits because disk I/O is involved on restoration.
- **`LlamaCache`** — backward-compat alias for `LlamaRAMCache`.

**How to attach:**
```python
from llama_cpp import Llama, LlamaRAMCache

llm = Llama(
    model_path="Qwen3-8B-Q5_K_M.gguf",
    n_ctx=4096,
    n_gpu_layers=-1,
    flash_attn=True,
    type_k=llama_cpp.GGML_TYPE_Q8_0,
    type_v=llama_cpp.GGML_TYPE_Q8_0,
    offload_kqv=True,
)
llm.set_cache(LlamaRAMCache(capacity_bytes=512 * 1024 * 1024))  # 512 MB
```

There is **no separate "VRAM cache" type** in the Python binding — the Python cache stores serialised state in host RAM and restores it back into the GPU context on a hit; the active KV cache lives in VRAM as always.

Sources: [DeepWiki state-management](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching), [GitHub discussion #1102](https://github.com/abetlen/llama-cpp-python/discussions/1102), [llama_cache.py source](https://huggingface.co/spaces/aelitta/BioMistral_gradio/blob/16806560100c4c0382368f86e27d2438f000bc64/llama-cpp-python/llama_cpp/llama_cache.py)

---

### 2. Prefix Matching Semantics

The `_find_longest_prefix_key(cache_state, key)` static method iterates every key in the OrderedDict and calls `Llama.longest_token_prefix(cached_key, new_key)` — a simple element-wise token comparison returning match length. The entry with the **longest prefix** wins.

On a cache **hit**:
- The stored `LlamaState` is restored via `llama_state_set_data()` (C API).
- The `Llama` object's internal `n_tokens` counter is set to the match length.
- Only the **suffix tokens** (those beyond the match point) need to be evaluated.
- The `generate()` method handles this transparently when `reset=True` (the default); callers do not need to do anything special.

On a cache **miss** (or partial miss):
- Full evaluation of the new prefix occurs.
- After generation, the completed state is serialised via `llama_state_get_data()` and stored back under the new token-sequence key.

**Key insight: the match is on the raw tokenised sequence, not on text strings.** Two strings that produce the same token IDs are interchangeable; even a single inserted BOS or whitespace token can break the match.

Source: [DeepWiki](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching), [llama.cpp main.py source](https://github.com/abetlen/llama-cpp-python/blob/main/llama_cpp/llama.py)

---

### 3. Measured Prefill Savings

The following numbers are drawn from real benchmarks on comparable hardware:

| Scenario | Cold TTFT | Warm TTFT | Improvement |
|---|---|---|---|
| 4096-token system prompt (server, RTX 3090) | 4,300 ms | 300 ms | **93 % reduction** |
| 4096-token system prompt (server, measured) | 380–445 ms | 12–20 ms | **19–24× faster** |
| 2571-token prefix (CPU-only benchmark) | 172,980 ms | 837 ms | **99.5 % reduction** |
| llama-server slot log (43-token prompt) | 43 tokens evaluated | 1 token evaluated | 98 % skip |

These are measured on the server, but the in-process Python binding uses the identical underlying C++ `llama_decode()` / KV-restore path — the speedup is the same mechanism. The "restore" cost (copying host-RAM state back into GPU) is approximately proportional to the serialised state size; for the 8B model at 4096 tokens, an early estimate is ~50–100 ms for the host→GPU copy, but this is still massively faster than re-running the prefill.

Sources: [GitHub discussion #20574](https://github.com/ggml-org/llama.cpp/discussions/20574), [CraftRigs guide](https://craftrigs.com/guides/llama-cpp-server-prefix-cache-setup-verify/), [Jesse Quinn blog](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching)

---

### 4. Cache Invalidation and Variable-Suffix Architecture

**The problem:** If the system prompt includes any per-turn variable content (timestamp, turn counter, last utterance echo), the token sequence differs on every call → zero cache hits.

**The rule:** The static prefix must be a strict leading prefix of every prompt, byte-identical at the token level. The variable suffix (user utterance, RAG context, conversation history tail) goes at the end.

```
[FIXED SYSTEM PROMPT BLOCK — cached]
[Optional in-context exemplars — semi-fixed]
<user>: {current utterance}
<agent>:
```

The prefix cache captures everything up to and including the in-context exemplars if those are also static. In Ultron 1.0, the system prompt + agent persona + flavor examples are fixed per session → they will be cached after the first turn. Verbosity tier and thinking flag, if encoded in the prompt, must go in a section that stays constant or be moved to a system-level parameter rather than inline text.

**Multi-level caching trick (two LlamaRAMCache instances):** You can call `llm.set_cache(cache_A)` before one completion and `llm.set_cache(cache_B)` before another to maintain separate conversation histories in RAM — for example, one per VERBOSITY_TIER. Each cache independently tracks its own prefix. This is confirmed working in llama-cpp-python (issue #997 resolved the earlier assertion crash).

Sources: [Jesse Quinn blog](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching), [GitHub #1102](https://github.com/abetlen/llama-cpp-python/discussions/1102), [CraftRigs guide](https://craftrigs.com/guides/llama-cpp-server-prefix-cache-setup-verify/)

---

### 5. KV Cache Quantisation: Types, VRAM Savings, Quality Impact

#### Supported types (llama.cpp, as of 2025–2026)

| `type_k` / `type_v` constant | Bits/element | vs FP16 VRAM | Quality delta (NLG) |
|---|---|---|---|
| `GGML_TYPE_F16` (default) | 16 | 1.0× baseline | reference |
| `GGML_TYPE_Q8_0` | 8 | **0.5×** | under 0.1 % loss |
| `GGML_TYPE_Q4_0` | 4 | **0.25×** | noticeable but acceptable for many tasks |
| `turbo3` (TurboQuant Q3) | ~3.25 | **~0.20×** | near-FP16 on 8B+ (experimental, 2026) |
| `turbo4` (TurboQuant Q4) | ~4.25 | **~0.27×** | near-FP16 on 8B+ (experimental, 2026) |

**Flash Attention is required for Q8_0/Q4_0 KV quantisation.** Without `flash_attn=True`, llama.cpp must dequantize the KV tensors for every attention step, eliminating the memory saving and actually slowing inference. This is confirmed in both the llama.cpp issue tracker (#11200) and the KV Cache Strategies guide.

**K vs V asymmetry:** Key vectors are more tolerant of quantisation (attention pattern discrimination is robust). Value vectors directly determine output token probabilities and are more sensitive. Best practice for quality-first operation (Ultron 1.0): use `type_k=Q8_0, type_v=Q8_0` as the safe default; `type_v=F16` if any degradation in complex relay formulation is detected.

**TurboQuant (Q3/Q4 via Randomised Hadamard Transform):** Experimental as of mid-2026. Achieves 4.6–4.9× compression vs FP16 with near-FP16 perplexity on 8B+ models. CUDA and Metal backends implemented; requires explicit `--cache-type-k turbo3`. Not yet stable in the Python binding API (no confirmed `GGML_TYPE_TURBO3` constant in 0.3.22 — use server flags only for now).

Sources: [Medium KV cache guide](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec), [TurboQuant discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969), [smcleod.net KV quantisation](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/), [llama-cpp-python issue #1305](https://github.com/abetlen/llama-cpp-python/issues/1305)

---

### 6. VRAM Budget Math — Qwen3-8B Q5_K_M on RTX 4070 Ti (10 GB design cap)

#### Qwen3-8B Architecture Parameters (sourced from Qwen3 repo + Qwen2.5 technical report)

| Parameter | Value |
|---|---|
| Total parameters | ~8.2 B |
| Layers (n_layers) | 36 |
| Attention heads (n_heads Q) | 32 |
| KV heads (n_kv_heads, GQA) | 8 |
| Head dimension (d_head) | 128 (hidden 4096 / 32 heads) |
| Hidden size | 4096 |

Note: Josiefied-Qwen3-8B is a derivative fine-tune of Qwen3-8B, so the architecture parameters are identical.

#### A. Model Weight VRAM

Q5_K_M uses approximately 0.69 bytes/parameter:

```
8.2 B params × 0.69 bytes = 5.66 GB  (weights only, all layers offloaded)
```

Practical measurement with overhead: **~5.5–5.7 GB** (confirmed by multiple community measurements; the 0.1–0.2 GB spread is tensor alignment + embedding table rounding).

#### B. Active KV Cache VRAM (in VRAM, with `offload_kqv=True`)

Formula for FP16:
```
KV_bytes = 2 (K+V) × n_layers × n_kv_heads × d_head × n_ctx × 2 (bytes/FP16)
```

For Qwen3-8B at various context lengths (FP16 baseline):
```
n_ctx=2048:  2 × 36 × 8 × 128 × 2048 × 2 = 301 MB  ≈ 0.29 GB
n_ctx=4096:  2 × 36 × 8 × 128 × 4096 × 2 = 603 MB  ≈ 0.59 GB
n_ctx=8192:  2 × 36 × 8 × 128 × 8192 × 2 = 1,207 MB ≈ 1.18 GB
n_ctx=16384: 2 × 36 × 8 × 128 × 16384 × 2 ≈ 2.36 GB
```

With **Q8_0 KV quantisation (÷ 2)**:
```
n_ctx=4096  → ~0.30 GB
n_ctx=8192  → ~0.59 GB
n_ctx=16384 → ~1.18 GB
```

With **Q4_0 KV quantisation (÷ 4)**:
```
n_ctx=4096  → ~0.15 GB
n_ctx=8192  → ~0.30 GB
n_ctx=16384 → ~0.59 GB
```

Note: These numbers are notably smaller than popular "8B needs 4.5 GB for 32K context" claims, which are for older Llama 3 8B with 32 KV heads at d_head=128. Qwen3-8B has only **8 GQA KV heads** (4× fewer), so KV footprint is ~4× smaller for the same context length. This is a meaningful advantage for Ultron 1.0.

#### C. CUDA Graphs + Overhead

llama.cpp allocates CUDA compute graphs, scratch buffers, and activation memory. Empirically: ~400–600 MB for an 8B model.

#### D. EmbeddingGemma-300M (sidecar, subprocess — NOT in-process)

In the current Ultron architecture the embedder runs as a separate process. It does NOT occupy the 4070 Ti's VRAM when running CPU-only (the current mode). If it were brought GPU-side, it would need approximately:

```
300M params × 2 bytes (FP16 inference) = 600 MB
```

**Recommendation: keep it CPU-only / subprocess.** The latency benefit of GPU embedding is small (EmbeddingGemma is lightweight; routing is not latency-critical); the VRAM cost is not.

#### E. Full Budget Table

| Component | n_ctx=4096, Q8_0 KV | n_ctx=8192, Q8_0 KV | n_ctx=4096, F16 KV |
|---|---|---|---|
| Qwen3-8B Q5_K_M weights | 5.60 GB | 5.60 GB | 5.60 GB |
| Active KV cache | 0.30 GB | 0.59 GB | 0.59 GB |
| CUDA overhead | 0.50 GB | 0.50 GB | 0.50 GB |
| LlamaRAMCache in host RAM | 0.25–0.50 GB | 0.50 GB | 0.25–0.50 GB |
| **Total VRAM** | **6.40 GB** | **6.69 GB** | **6.69 GB** |
| Headroom to 10 GB cap | **3.60 GB** | **3.31 GB** | **3.31 GB** |

**Even at n_ctx=16384 with Q8_0 KV, total VRAM remains ≈ 7.3 GB**, comfortably under the 10 GB cap. This means Ultron 1.0 can afford long system prompts + full conversation history without VRAM pressure.

#### F. Optional Draft Model (Speculative Decoding)

A 1B draft model at Q4_K_M ≈ 700 MB. This leaves ~2.9 GB headroom after the 6.4 GB base. Speculative decoding with a compatible Qwen3-1B draft is viable under the 10 GB cap at n_ctx=4096.

Sources: [llm-stats.com formula](https://llm-stats.com/blog/research/hardware-requirements-running-llms-locally), [oobabooga VRAM formula](https://oobabooga.github.io/blog/posts/gguf-vram-formula/), [Qwen3 GitHub](https://github.com/QwenLM/Qwen3), [DEV Community Q4 KV cache math](https://dev.to/plasmon_imp/q4-kv-cache-fit-32k-context-into-8gb-vram-only-math-broke-209k), [smcleod.net](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/)

---

### 7. Save/Load KV State — Lower-Level API

For cases where you want manual control (e.g., persisting the "Ultron system prompt" state across process restarts without repeating the prefill every cold start):

```python
# Save
state_bytes = llm.save_state()  # returns bytes from llama_state_get_data()
with open("ultron_syspt_state.bin", "wb") as f:
    f.write(state_bytes)

# Load on next startup
with open("ultron_syspt_state.bin", "rb") as f:
    state_bytes = f.read()
llm.load_state(state_bytes)  # calls llama_state_set_data()
```

This is essentially `LlamaDiskCache` done manually. The state file is model-specific and non-portable (tied to the exact GGUF, n_ctx, quantisation, and llama.cpp version). It can be hundreds of MB for large contexts; for Qwen3-8B at 4096 context with a 1K-token system prompt, estimated serialised size is ~600 MB (FP16) or ~300 MB (Q8_0).

`LlamaDiskCache` automates this under the `diskcache` library. It is appropriate for cross-session reuse of common prefixes (e.g., if the system prompt rarely changes).

Source: [Jesse Quinn blog](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching), [DeepWiki](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching)

---

### 8. Known Limitations and Bugs (as of 0.3.22 / b-builds 2025)

1. **Performance regression with LlamaRAMCache when using `offload_kqv=True`:** An early community report found ~50 % slower inference when cache was enabled. This was traced to a missing `offload_kqv` flag and was fixed in a post-#997 release. Confirm `offload_kqv=True` is set alongside the cache.

2. **No VRAM-resident Python cache class:** The Python API's cache always serialises to host RAM, then restores to GPU context on a hit. The copy overhead is non-zero but much smaller than re-running prefill for >200 token prefixes.

3. **Slot metadata corruption (server, b8825–b8891):** Affected llama-server, not in-process Python. Fixed in b8892. Not relevant for our use case.

4. **Recurrent/hybrid model restriction:** Models with stateful recurrent layers (Mamba, etc.) cannot support partial KV rewind — they require a full reset. Qwen3-8B is transformer-only and not affected.

5. **`--kv-unified` flag (server only):** Required in the server to correctly combine prefix caching with parallelism. Not applicable to in-process single-instance use.

6. **TurboQuant constants not confirmed in Python binding 0.3.22:** `turbo3`/`turbo4` are CLI flags for the server. The Python `type_k` / `type_v` integer constants for TurboQuant formats have not been confirmed in 0.3.22's public API. Use Q8_0 for now; revisit TurboQuant after upgrading to a build where the constants are documented.

7. **`--cache-ram` is a server flag only:** The server's `--cram` (host RAM prompt cache for multi-slot) is separate from in-process `LlamaRAMCache`. They are not the same mechanism. In-process code should only use `set_cache()`.

Sources: [GitHub #1102](https://github.com/abetlen/llama-cpp-python/discussions/1102), [Jesse Quinn blog](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching), [TurboQuant discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969)

---

## Concrete Techniques / Parameters to Adopt

### Llama() Constructor (at startup)

```python
llm = Llama(
    model_path="Josiefied-Qwen3-8B-abliterated-Q5_K_M.gguf",
    n_ctx=4096,            # voice relay: 4096 is ample; bump to 8192 only if needed
    n_batch=512,           # prompt chunk size; 512 is safe default
    n_ubatch=512,          # physical micro-batch; match n_batch
    n_gpu_layers=-1,       # offload ALL layers to GPU
    offload_kqv=True,      # KV cache in VRAM (required for performance)
    flash_attn=True,       # REQUIRED for type_k/type_v quantisation to save VRAM
    type_k=llama_cpp.GGML_TYPE_Q8_0,   # 50 % KV memory saving, near-lossless
    type_v=llama_cpp.GGML_TYPE_Q8_0,   # same; can fall back to F16 if quality issues
)
```

### Cache Attachment (after construction)

```python
from llama_cpp import LlamaRAMCache
# 256 MB holds ~3–5 distinct system-prompt states at Qwen3-8B 4096 context (Q8_0 serialised ~60 MB/state)
llm.set_cache(LlamaRAMCache(capacity_bytes=256 * 1024 * 1024))
```

### Prompt Structure (for maximum hit rate)

```
<|im_start|>system
[STATIC ULTRON PERSONA BLOCK — never changes]
[STATIC FLAVOR EXEMPLARS — never changes per session]
<|im_end|>
<|im_start|>user
[VERBOSITY DIRECTIVE — static per tier]
[CURRENT UTTERANCE — variable]
<|im_end|>
<|im_start|>assistant
```

Everything up to and including the flavor exemplars will be cached after the first call. The "VERBOSITY DIRECTIVE + CURRENT UTTERANCE" block is the suffix that is re-evaluated each turn.

### Checking Cache Effectiveness

In the Python binding, inspect `llm.n_tokens` before and after a call. A large n_tokens before a call (from a prior turn) that does NOT drop to 0 indicates the prefix was reused (context was not fully reset). You can also monkey-patch `BaseLlamaCache.__getitem__` to log hits.

### Disk Persistence (optional, cold-start speedup)

```python
from llama_cpp import LlamaDiskCache
llm.set_cache(LlamaDiskCache(capacity_bytes=2 * 1024 * 1024 * 1024))
# State stored in .cache/llama_cache — survives restarts
# First warm-up call takes ~full prefill time; subsequent restarts restore in ~seconds
```

---

## Risks / Caveats for Ultron Constraints

### 1. Anticheat safety
`LlamaRAMCache` uses `collections.OrderedDict`, `ctypes`, and `numpy` — all stdlib / approved. No external ML imports. **Safe.** The `LlamaDiskCache` adds `diskcache` (pure Python + SQLite); also safe, though it adds a pip dependency. The KV quantisation path (`type_k`, `type_v`) operates entirely inside llama.cpp C++ — anticheat never sees it.

### 2. Token-level byte-exactness is mandatory
Any change in the template (whitespace, newline, BOS token insertion) creates a cache miss. The Qwen3 tokeniser uses `<|im_start|>`/`<|im_end|>` delimiters. Build prompts with a single deterministic function; never concatenate strings ad-hoc at call sites.

### 3. State size vs capacity
A single `LlamaState` for Qwen3-8B at n_ctx=4096 with Q8_0 KV is approximately 300–500 MB serialised (the full KV buffer for all processed tokens, not just the prefix). A 256 MB cache can therefore only hold ~1 state reliably. **Recommendation: set `capacity_bytes=512 MB`**, which fits 1 full state with room for a shorter variant. If multiple verbosity-tier caches are needed, allocate one `LlamaRAMCache` per tier and swap with `set_cache()`.

### 4. Copy overhead on cache restore
Restoring a LlamaState involves `llama_state_set_data()` which copies ~300–500 MB from host RAM to GPU context. On PCIe 4.0 × 16 (≈32 GB/s peak, ~20 GB/s practical), this takes roughly 15–25 ms. This is negligible for Ultron's use case (saves hundreds of milliseconds of prefill). For sub-100ms latency goals later, this overhead should be profiled on the actual hardware.

### 5. EmbeddingGemma process isolation
Ollama's experience shows that bringing EmbeddingGemma in-process (in the same CUDA context) causes the embedding model's allocation to evict the LLM's VRAM pages. The existing sidecar architecture is correct. Do not merge them.

### 6. KV quantisation quality floor
For relay utterances ("Hit 84, Breach down"), Q8_0 KV loss is undetectable. For longer reasoning turns (thinking-mode enabled, multi-step tactical analysis), theoretically Q4_0 could introduce coherence drift in very long chains. Use `type_k=Q8_0, type_v=Q8_0` as the default. If the optional speculative draft model is introduced, the draft model should share the same `flash_attn=True` and KV quantisation config.

### 7. Multi-cache-instance assertion (historical, fixed)
The crash (`GGML_ASSERT: ctx->logits.capacity()`) seen when switching between two `LlamaRAMCache` instances was fixed post-issue #997. Confirm the installed version is >= that fix before deploying multi-tier caches.

---

## Sources

1. [DeepWiki — State Management and Caching (llama-cpp-python)](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching)
2. [llama-cpp-python llama_cache.py source (HuggingFace mirror)](https://huggingface.co/spaces/aelitta/BioMistral_gradio/blob/16806560100c4c0382368f86e27d2438f000bc64/llama-cpp-python/llama_cpp/llama_cache.py)
3. [llama-cpp-python llama.py source (GitHub)](https://github.com/abetlen/llama-cpp-python/blob/main/llama_cpp/llama.py)
4. [llama-cpp-python GitHub Discussion #1102 — Switching back and forth between caches](https://github.com/abetlen/llama-cpp-python/discussions/1102)
5. [llama.cpp Discussion #13606 — KV cache reuse with llama-server](https://github.com/ggml-org/llama.cpp/discussions/13606)
6. [llama.cpp Discussion #20574 — Mastering Host-Memory Prompt Caching in llama-server](https://github.com/ggml-org/llama.cpp/discussions/20574)
7. [Jesse Quinn blog — Understanding --cache-ram in llama.cpp](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching)
8. [CraftRigs — llama.cpp Server Prefix Cache: What It Does and How to Verify It's Working](https://craftrigs.com/guides/llama-cpp-server-prefix-cache-setup-verify/)
9. [Medium / rigel-computer-com — Optimize Your GPU KV-Cache for Llama.cpp](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec)
10. [llama.cpp Discussion #20969 — TurboQuant Extreme KV Cache Quantization](https://github.com/ggml-org/llama.cpp/discussions/20969)
11. [smcleod.net — Bringing K/V Context Quantisation to Ollama](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/)
12. [llm-stats.com — How to Calculate Hardware Requirements for Running LLMs Locally](https://llm-stats.com/blog/research/hardware-requirements-running-llms-locally)
13. [oobabooga blog — A formula that predicts GGUF VRAM usage from GPU layers and context length](https://oobabooga.github.io/blog/posts/gguf-vram-formula/)
14. [DEV Community — Q4 KV Cache: Fit 32K Context into 8GB VRAM](https://dev.to/plasmon_imp/q4-kv-cache-fit-32k-context-into-8gb-vram-only-math-broke-209k)
15. [Qwen3 GitHub — QwenLM/Qwen3](https://github.com/QwenLM/Qwen3)
16. [Google Developers Blog — Introducing EmbeddingGemma](https://developers.googleblog.com/introducing-embeddinggemma/)
17. [Ollama issue #12247 — EmbeddingGemma unloads other models](https://github.com/ollama/ollama/issues/12247)
18. [llama-cpp-python issue #1305 — cache-type-k and cache-type-v parameters support](https://github.com/abetlen/llama-cpp-python/issues/1305)
19. [llama.cpp issue #11200 — KV cache quantization and flash attention bug](https://github.com/ggml-org/llama.cpp/issues/11200)
20. [KV Cache Quantization Guide — TechPlained](https://www.techplained.com/kv-cache-quantization)
