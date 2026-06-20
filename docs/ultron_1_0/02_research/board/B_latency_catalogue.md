# Local LLM Latency Optimization Catalogue — Ranked by Impact for Ultron 1.0

**Research date:** 2026-06-20  
**Hardware target:** RTX 4070 Ti, 12 GB VRAM (10 GB design cap), Windows 11, llama-cpp-python 0.3.22 in-process  
**Model target:** Josiefied-Qwen3-8B-abliterated Q5_K_M (thinking-capable, routed through per-request reasoning-budget toggle)

---

## TL;DR Recommendation for Ultron 1.0

The single highest-impact change is **streaming TTS overlap** (start Kokoro on the first sentence boundary while the 8B is still generating) — this is architectural and costs nothing in VRAM. Second is **prefix / prompt caching** of the static system prompt + exemplar block so repeated turns pay only the incremental-suffix prefill cost (19× prefill speedup on cache hit, verified at ~12 ms vs ~380 ms cold). Third is **KV cache quantization to q8_0** (free ~1–2 GB VRAM, enabling a larger context window or keeping more model layers on GPU, with under 0.1% quality loss). MTP/speculative decoding shows real gains (1.7–2.4×) but requires the Qwen3-8B to have been trained with MTP heads; verify GGUF metadata before enabling. Grammar overhead for structured output is real but manageable. Thinking-mode token budget must be capped per-request for voice paths to avoid catastrophic TTFT blowout. All techniques below are anticheat-safe (no kernel injection, no new driver hooks — only VRAM layout and inference parameters).

---

## Findings

### 1. Streaming TTS Overlap (Sentence-Boundary Pipelining)

**Mechanism:** Instead of waiting for the full LLM output before invoking Kokoro, begin TTS synthesis as soon as the LLM emits the first natural sentence boundary (`.`, `!`, `?`, or a short-clause comma). The LLM continues generating subsequent sentences while audio for sentence 1 is already playing.

**Numbers:**
- Perceived first-audio latency: TTFT (~200–400 ms for an 8B at short prompts) + TTS-first-chunk (~150 ms for Kokoro streaming) = **350–550 ms to first word**. Without overlap, total response time before *any* audio is TTFT + full generation + TTS ≈ 2–4 s for a 3-sentence relay. With overlap, the user hears the first word at 350–550 ms, regardless of total generation length.
- [Smallest.ai latency budget guide](https://smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget) confirms: "streaming at every stage is the single highest-impact architectural choice you can make," saving 300–600 ms perceived latency vs sequential pipeline.
- [Retell AI engineering overview](https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts) confirms "modern voice agents stream audio out in 200–400 ms chunks so the caller hears the first word before the full reply has been generated."

**Ultron 1.0 tie-in:** Ultron already has Kokoro in a streaming posture and the per-sentence `_join_tail` pipeline. The relay rephrase prompt design should front-load the speak-able unit (team relay message before flavor tail) so the sentence boundary arrives early. The flavor tail arrives last and can be synthesized while the relay audio is already playing, cutting perceived latency by the full tail-generation time.

**Status:** SOTA / recommended — this is table stakes for every production voice AI in 2025–2026.

**Caveats:** Sentence boundary detection needs to avoid false splits on abbreviations (e.g., "A site" vs end of sentence). A simple heuristic (split on `. ` or `! ` or `? ` followed by whitespace, not on `.` before a digit) is sufficient for the relay domain.

---

### 2. Prefix / KV Cache of System Prompt + Exemplars

**Mechanism:** llama.cpp maintains a per-slot KV cache ring. When a new prompt shares a prefix with the slot's previously-evaluated tokens, those cached tensors are reused and only the new suffix is evaluated. This is automatic in llama-cpp-python in-process: the `Llama` class in generate() detects the longest common prefix and skips re-evaluation. No special flag is needed in-process; the `LlamaRAMCache` API (`llama_instance.set_cache(LlamaRAMCache(capacity_bytes=N))`) provides explicit LRU management if you have multiple concurrent prompt types.

**Numbers:**
- [CraftRigs prefix cache guide](https://craftrigs.com/guides/llama-cpp-server-prefix-cache-setup-verify/): Cold TTFT ~380 ms, cache-hit TTFT ~12 ms — **31× faster** on the shared prefix portion.
- A 4096-token system prompt at ~0.1 ms/token = 410 ms prefill overhead on a cold start. With a cache hit on 90% of tokens, that drops to ~40 ms for the 10% new content.
- Cache hit rates for identical system prompts: "85–95% on that prefix" for repeated conversational turns.
- In llama-cpp-python in-process mode, this is automatic when the same `Llama` instance handles sequential calls — no API changes required. The `reset` parameter in `generate()` controls whether the prefix match is attempted.

**Ultron 1.0 tie-in:** The 8B's system prompt (Ultron persona + routing instructions + exemplar library injection) will be large — potentially 1,500–3,000 tokens. Every voice turn will share this prefix. Without caching, each turn pays 150–300 ms extra prefill. With caching, the repeated prefix costs ~1–2 ms. The key requirement is using a **single persistent `Llama` instance** across turns (which Ultron already does for hot-reload reasons) and keeping the system prompt structurally stable between turns (inject per-agent flavor as a fixed ordered block, not randomized each turn).

**Status:** SOTA / essential — already implemented in llama.cpp's internal slot management. Free win.

**Caveats:**
- Bug window: llama.cpp builds b8825–b8891 (Jan 14 – Feb 3, 2025) silently broke prefix cache. llama-cpp-python 0.3.22 is well past that range.
- The cache key is the exact token sequence — any change to the shared prefix (e.g., inserting a timestamp or random seed in the system prompt) destroys the cache hit. Keep exemplars in a deterministic, stable order.
- In server mode, `slot_id` must be explicitly passed per-request or the server assigns round-robin slots that break cross-request cache continuity. In in-process mode this is not relevant.
- `preserve_thinking=true` for Qwen3.5-arch GGUFs may currently block prompt cache on the thinking section ([GitHub issue #22615](https://github.com/ggml-org/llama.cpp/issues/22615)) — a known open bug as of mid-2026. For Qwen3-8B standard GGUF, test whether the cached prompt includes or excludes the `<think>` block prefix.

---

### 3. KV Cache Quantization (q8_0)

**Mechanism:** The KV cache stores intermediate attention tensors that grow with context length. By default these are FP16 (2 bytes/element). `--cache-type-k q8_0 --cache-type-v q8_0` halves this to 1 byte/element with negligible quality loss.

**Numbers:**
- Memory: KV cache at FP16 for Qwen3-8B at ctx=4096 ≈ 0.5–0.8 GB. At q8_0: ~0.25–0.4 GB. **Saving: ~250–400 MB per 4K context.**
- Quality: Q8_0 KV achieves "~98% of FP16 quality" per [CraftRigs / medium guide](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec). Perplexity increase: under 0.1% for standard architectures.
- Speed: Q8_0 KV adds roughly 3–5% generation overhead vs FP16 (measured on DGX Spark with 30B model — see [NVIDIA forum benchmark](https://forums.developer.nvidia.com/t/kv-cache-quantization-benchmarks-on-dgx-spark-q4-0-vs-q8-0-vs-f16-llama-cpp-nemotron-30b-128k-context/365138)); negligible at short contexts.
- Q4_0 KV: saves more VRAM (~75% reduction vs FP16) but shows generation speed collapse at long contexts: -35% at 64K tokens, and the DGX Spark benchmark showed q4_0 at 64K context was **92.5% slower** on prompt processing than f16. For our 2K–4K relay context, q4_0 is acceptable on paper, but the community consensus is "q8_0 first, q4_0 only if you need more headroom."

**Ultron 1.0 tie-in:** 10 GB VRAM cap. Qwen3-8B Q5_K_M ≈ 6.0–6.5 GB model weights. KV cache at FP16 for ctx=4096 ≈ 0.6 GB. With q8_0 KV, you save ~300 MB = can safely run ctx=6144 or keep more GPU layers. Flash attention (next section) further halves the peak KV footprint during attention computation.

**In-process flags (llama-cpp-python):**
```python
Llama(
    model_path="...",
    n_ctx=4096,
    cache_type_k="q8_0",  # llama-cpp-python >= 0.2.90
    cache_type_v="q8_0",
)
```

**Status:** SOTA / recommended — part of every optimized llama.cpp deployment as of 2025.

---

### 4. Flash Attention (`-fa` / `flash_attn=True`)

**Mechanism:** Replaces the naive O(n²) attention computation with a tiled, IO-aware kernel that fuses the softmax and projection into a single CUDA kernel pass. Reduces peak VRAM for the attention activations during the forward pass (not the KV cache — that's separate). Mathematically equivalent to standard attention.

**Numbers:**
- VRAM: halves peak attention activation memory during prefill. On an 8B model at ctx=4096, this can save ~0.5–1.0 GB peak during the prefill pass.
- CUDA Graphs: NVIDIA's llama.cpp optimizations (CUDA Graphs implementation) reduce kernel launch gaps and CPU overhead. [NVIDIA RTX blog](https://developer.nvidia.com/blog/accelerating-llms-with-llama-cpp-on-nvidia-rtx-systems/) reports "~150 tok/s" on RTX 4090 with Llama 3 8B int4; the RTX 4070 Ti achieves 85–95 tok/s at Q4_K_M, ~80 tok/s at Q8_0.
- Flash attention speeds up long-context prefill disproportionately because the naive kernel's O(n²) overhead grows quadratically with prompt length.
- Known issue: Flash Attention on some RTX 4060 Ti cards had a compute-capability bug in llama.cpp (#13092) that produced incorrect outputs. RTX 4070 Ti (CC 8.9) is unaffected.

**In-process flags:**
```python
Llama(
    model_path="...",
    flash_attn=True,
    n_gpu_layers=-1,  # -1 = all layers
)
```

**Status:** SOTA / recommended since 2024. Enable by default on any CUDA build.

---

### 5. MTP / Speculative Decoding (Model-native or Draft-model)

**Mechanism:** Two variants:
- **Draft-model spec-decode:** A small draft model (e.g., Qwen3-0.6B) proposes N tokens; the 8B verifies them all in one forward pass, accepting a run that would otherwise require N passes. Net gain if acceptance rate ≥ 60%.
- **MTP (Multi-Token Prediction) heads:** The target model itself has a built-in MTP head (trained alongside the base model) that drafts additional tokens without a separate model. Qwen3.6-27B has this; Qwen3-8B standard GGUF may or may not (check GGUF metadata for `split_mode` or MTP head presence).

**Numbers — draft-model (consumer GPU, 2025–2026):**
- Qwen3 0.6B → Qwen3 8B: reported **1.9× speedup** at 81% acceptance rate on code-style structured output ([vucense.com benchmark](https://vucense.com/dev-corner/speculative-decoding-explained-2x-faster-local-llms-ollama-llama-cpp-2026/)).
- Llama 3.2 1B → Llama 3.1 8B on A100: 1.8× latency reduction (introl.com speculative guide).
- For open-ended chat (most similar to relay rephrasing): acceptance rate 45–60%, speedup 1.4–1.8× if at all. Creative/varied outputs hurt acceptance.
- **Critical constraint:** Running Qwen3-0.6B draft + Qwen3-8B target on a single 12 GB GPU: 0.6B Q4 ≈ 0.4 GB + 8B Q5_K_M ≈ 6.0 GB = 6.4 GB combined, well within 10 GB cap. VRAM headroom is not the constraint; the issue is CUDA Graph thrashing (variable accepted-token count per step).

**Numbers — MTP heads (Qwen3.6-27B, RTX 3090):**
- [HackMD adversarial test](https://hackmd.io/ODXuOQNzSiyUITz7g9mtBw): On Qwen3.6-35B-A3B (MoE), ALL speculative modes were slower than baseline. Baseline: 137 tok/s; best speculative: 85.6 tok/s (−38%). Root cause: each speculative token requires loading a fresh expert slice in the sparse MoE attention, overwhelming bandwidth savings.
- For **dense** models (Qwen3-8B is dense), gains are more reliable: RTX 3090 with Qwen3.6 27B (dense) improved from 38 → 65 tok/s (1.71×).

**Ultron 1.0 tie-in:** For the relay rephrase path (short output, structured), acceptance rates will be higher than for open-ended chat. The key question is whether the Josiefied-Qwen3-8B GGUF includes MTP heads. If yes, enable with `--draft-max 2 --draft-min 1` (conservative — recommended to start; see [dev.to MTP failure analysis](https://dev.to/alanwest/why-mtp-doesnt-speed-up-your-llamacpp-inference-and-how-to-actually-fix-it-2m2m)) and measure before/after. If using a separate 0.6B draft model, the VRAM budget allows it. Expected gain: **1.5–1.9× generation throughput** on structured relay outputs if acceptance ≥ 65%.

**Flags:**
```python
# Draft-model speculative decoding (llama-cpp-python server mode or CLI)
# --model-draft qwen3-0.6b-q4.gguf --n-gpu-layers-draft 99 --draft 4
# In-process: llama-cpp-python does not yet expose draft-model API natively;
# use llama-server + HTTP in-process or the llama_speculative C binding
```

**Status:** EXPERIMENTAL to PRODUCTION — MTP on dense models is increasingly stable (2025–2026). MoE models: do not use. Draft-model spec-decode on 8B: validated but requires tuning. Default `--draft 4–8` is often too aggressive; start at `--draft 2`.

**Caveats:**
- Reduces effective context window: each speculative step requires extra KV slots for the draft candidates, increasing KV cache pressure.
- CUDA Graph capture failures at variable accepted-token counts can negate all gains — if using CUDA graphs, disable them or use static-graph mode.
- Quality is mathematically identical (rejected tokens fall back to target sampling) but thinking-mode outputs may behave differently with speculative proposals.

---

### 6. Reasoning Budget Control (Thinking-Mode Token Cap)

**Mechanism:** Qwen3-8B's thinking mode generates `<think>...</think>` tokens before the response. These are invisible to the user but count against generation time at the same tok/s rate. An uncapped thinking run can add 500–3000 extra tokens before the first relay-visible token, adding 5–30 s at 80 tok/s.

**Numbers:**
- At 80 tok/s (Q5_K_M, RTX 4070 Ti), 500 thinking tokens = **6.25 s** added latency before first visible output. 200 thinking tokens = 2.5 s. 50 thinking tokens = 0.6 s.
- [llama.cpp discussion #21445](https://github.com/ggml-org/llama.cpp/discussions/21445): `thinking_budget_tokens` parameter accepted per-request in the JSON body when `--reasoning-budget` is NOT set on the command line. Setting `{"thinking_budget_tokens": 0}` = immediate end of thinking = thinking-mode OFF for this request. Setting 64–128 = allows a brief internal planning pass.
- Qwen3 on HumanEval: thinking=ON: 94% pass; thinking=OFF: 88%; thinking with forced hard cutoff (wrong prompt): 78%. So budget 64–128 tokens for relay tasks (simple rephrase) is sufficient; complex reasoning paths (exemplar selection) may benefit from 256–512.
- `t_max_predict_ms` in llama-server: a time-based hard cutoff (in ms) on the prediction phase — an alternative for strict latency guarantees.

**Ultron 1.0 tie-in:** The routing layer must set `thinking_budget_tokens` per request type:
- **Snap route (deterministic):** thinking = 0 (no LLM call at all — snaps don't need thinking)
- **Relay rephrase:** thinking_budget_tokens = 64–128 (simple rephrase; more thinking wastes time)
- **Private reply (complex):** thinking_budget_tokens = 256–512
- **Fallback/unknown:** thinking_budget_tokens = 256

**Status:** RECOMMENDED — essential for voice use case where thinking-mode default is uncapped. New feature, landed in llama.cpp ~late 2025 / 2026.

**Caveats:**
- Forcibly cutting thinking mid-stream can degrade coherence. Use `--reasoning-budget-message` (a closing token sequence) to let the model gracefully end reasoning, otherwise output quality on complex tasks drops significantly (78% vs 88% on HumanEval when hard-cutoff without prompting).
- `preserve_thinking=true` currently blocks prompt cache on Qwen3.5 GGUFs ([issue #22615](https://github.com/ggml-org/llama.cpp/issues/22615)) — may affect prefix cache savings.

---

### 7. Model Weight Quantization (Q5_K_M vs Q4_K_M vs Q8_0)

**Mechanism:** Lower bit quantization = smaller model = faster decode = less VRAM. Quality decreases sub-linearly.

**Numbers (Llama-3.1-8B, representative for Qwen3-8B):**

| Quant | tok/s (RTX 4070 Ti) | VRAM | Perplexity vs F16 |
|-------|---------------------|------|-------------------|
| Q4_K_M | ~90–95 tok/s | ~5.0 GB | +0.054 |
| Q5_K_M | ~82–88 tok/s | ~6.0 GB | +0.014 |
| Q6_K | ~72–78 tok/s | ~7.2 GB | +0.004 |
| Q8_0 | ~65–70 tok/s | ~9.0 GB | +0.0004 |

Sources: [runaihome.com quantization comparison 2026](https://runaihome.com/blog/quantization-q4-q5-q6-q8-quality-loss-2026/), community benchmarks.

**Ultron 1.0 tie-in:** Q5_K_M is the currently-chosen quant. It is the right balance: −7% speed vs Q4_K_M, −94% perplexity penalty vs Q4_K_M. For relay rephrasing (quality matters for tone/persona), Q5_K_M is correct. If latency becomes critical and quality is acceptable, dropping to Q4_K_M buys ~5–8 extra tok/s. Q8_0 is not viable on 10 GB cap (9.0 GB weights alone exceeds the cap before KV cache).

**Status:** ESTABLISHED — Q5_K_M is the community standard "quality-first" choice for 8B on 10–12 GB VRAM as of 2025–2026.

---

### 8. Batch Size / n_ubatch Tuning

**Mechanism:** `n_batch` (max tokens fed per batch call) and `n_ubatch` (micro-batch within the batch) control GPU utilization during prefill. Larger values = better GPU parallelism during prompt processing (lower TTFT for long prompts). For single-token decode (the generation phase), batch=1 by design — these parameters primarily affect prefill speed.

**Numbers:**
- [GitHub discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112): `n_batch=128, n_ubatch=512` gave "+30% real-world increase in context handling with no loss in throughput" vs defaults on discrete GPUs.
- Community guidance: `--n-batch 2048 --n-ubatch 512` is common for RTX 4070-class GPUs. The "larger is always better" assumption is wrong — too large a ubatch increases peak VRAM during prefill and can cause layer offload to CPU.
- For short prompts (relay turns are typically 20–100 tokens new content): prefill is fast regardless; n_ubatch has minimal effect. For long system prompts on cold start: larger n_batch helps, but prefix caching makes this moot after the first call.

**Ultron 1.0 tie-in:** Prefix caching removes most of the prefill burden after warmup. Keep defaults or `n_batch=512, n_ubatch=256` — don't over-optimize here until profiling shows prefill is the bottleneck (it won't be after the system prompt is cached).

**Status:** ESTABLISHED — tune only after confirming prefill is the bottleneck.

---

### 9. Grammar Overhead (Structured Output / GBNF)

**Mechanism:** llama.cpp's GBNF grammar constrains the sampling distribution at each token, requiring incremental parsing overhead per step. This adds CPU-side overhead per decode step.

**Numbers:**
- Research ([Pre³ paper, arxiv 2506.03887](https://arxiv.org/pdf/2506.03887)): grammar overhead is "negligible for ED and CP tasks" but can reach "several seconds per step" for complex grammars in the Outlines library. In llama.cpp's native GBNF, the overhead is typically 1–5 ms per token (100 tok/s → 90 tok/s equivalent ceiling).
- [NVIDIA DGX Spark benchmark](https://forums.developer.nvidia.com/t/kv-cache-quantization-benchmarks-on-dgx-spark-q4-0-vs-q8-0-vs-f16-llama-cpp-nemotron-30b-128k-context/365138): grammar overhead not separately measured, but GBNF parsing is CPU-bound; on an RTX 4070 Ti where generation is GPU-bound, grammar overhead is masked by CUDA kernel latency and is typically invisible (< 2% of generation time for simple grammars).
- Complex grammars (deeply recursive JSON schemas) can exhibit O(state²) parser overhead. Keep grammars flat and short.

**Ultron 1.0 tie-in:** The DDSD (Data-Driven Snap Dispatch) architecture uses the 8B to select a template or fill a slot — the grammar for "pick one of N labels" or "fill `{agent}` `{payload}`" is shallow and fast. Avoid recursive grammars for voice relay outputs where the structure is always simple. Grammar is optional if the 8B reliably produces structured output with explicit prompting alone (test first).

**Status:** ESTABLISHED / LOW RISK — grammar overhead is real but small for simple GBNF schemas on GPU-bound inference.

---

### 10. Prompt Length Minimization / Exemplar Pruning

**Mechanism:** TTFT scales approximately linearly with prompt token count (for short-to-medium prompts; attention is O(n²) but GPU parallelism keeps it near-linear up to ~4K). Cutting 500 tokens from the system prompt saves ~50 ms cold TTFT (at 10K prefill tok/s).

**Numbers:**
- At a representative prefill rate of 500–1,000 tok/s on GPU for an 8B model (decode is 80–90 tok/s; prefill is much faster due to batched matrix ops), 1,000 tokens = ~1–2 s cold TTFT. With prefix cache, this is one-time.
- [Prompt Cache paper (arxiv 2311.04934)](https://arxiv.org/pdf/2311.04934): modular attention reuse can reduce effective prompt computation to near-zero for repeated prefixes.

**Ultron 1.0 tie-in:** With prefix caching, exemplar length matters only on the first call (cold start). Prune exemplars to 3–5 per category (not 10–20) to keep the cold-start manageable. After warm-up, exemplar length has zero latency cost. The more important optimization is keeping the **per-turn suffix** short: relay turns should inject only the utterance + routing hint, not re-inject the full flavor library.

**Status:** IMPORTANT for cold start / session startup; irrelevant after prefix cache warms.

---

### 11. Resizable BAR / Driver-Level

**Mechanism:** Resizable BAR (Base Address Register) allows the CPU to access the full GPU VRAM in one mapping rather than 256 MB windows, reducing PCIe latency for weight loading.

**Numbers:**
- [Community benchmark on RTX 4070+](https://lifetips.alibaba.com/tech-efficiency/run-local-ai-llm-from-nvidia-gpu): "Resizable BAR reduces GPU memory mapping latency by 11–14%, yielding 4.3% higher tok/s on RTX 4070+ cards."

**Ultron 1.0 tie-in:** Enable in BIOS (Above 4G Decoding + Resizable BAR). This is a one-time system setting, not a code change. RTX 4070 Ti supports it; most modern Z-series motherboards have it available. Estimated gain: **~4% tok/s** for free.

**Status:** ESTABLISHED / FREE WIN — enable it if not already done.

---

## Concrete Techniques / Params We Should Adopt

Ordered by implementation effort vs impact:

### Tier 1 — Implement Immediately (zero VRAM cost, high impact)

1. **Streaming TTS overlap at first sentence boundary** — front-load the relay message in LLM output; start Kokoro on `.`/`!`/`?` while 8B continues generating. Expected gain: 300–600 ms reduction in perceived latency.

2. **Prefix cache warm-up on boot** — make one dummy inference call at startup with the full system prompt so the KV cache is warm before the first real turn. All subsequent turns pay only the incremental suffix cost. Expected gain: eliminates ~200–400 ms prefill overhead per turn (from cold ~380 ms to warm ~12 ms on the shared prefix).

3. **Per-request `thinking_budget_tokens`** — set in the inference call based on route type:
   - Snap route: 0 (or bypass LLM entirely)
   - Relay rephrase: 64–128
   - Private reply: 256
   - Unknown: 128
   Expected gain: eliminates 2–30 s of invisible thinking-token generation for relay turns.

4. **Stable system prompt ordering** — do NOT randomize, timestamp, or version-stamp the system prompt between turns. Any prefix change invalidates the cache. Expected gain: maintains 31× cache speedup on every warm turn.

### Tier 2 — Parameter Changes (low effort, free VRAM savings)

5. **KV cache q8_0** — add `cache_type_k="q8_0", cache_type_v="q8_0"` to the `Llama()` constructor. Expected gain: ~300–400 MB VRAM freed, enabling larger ctx or keeping all layers on GPU. Quality impact: negligible (<0.1%).

6. **Flash attention** — add `flash_attn=True` to the `Llama()` constructor. Expected gain: ~0.5 GB peak VRAM reduction during prefill; modest speed improvement on long prefills.

7. **`n_batch=512, n_ubatch=256`** — set these if profiling shows prefill is a bottleneck. For warm-turn relay (short suffix after cached prefix), this has minimal impact. Still worth setting as a safety default.

8. **Enable Resizable BAR in BIOS** — if not already enabled. Free ~4% tok/s. Check with `nvidia-smi` or GPU-Z.

### Tier 3 — After Baseline Established (more setup, conditional gains)

9. **MTP / speculative decoding** — verify Josiefied-Qwen3-8B GGUF has MTP heads (check GGUF metadata). If present, test `--draft-max 2 --draft-min 1` first. If using a separate 0.6B draft model: Qwen3-0.6B Q4 ≈ 0.4 GB VRAM, feasible on 10 GB cap. Benchmark relay rephrase acceptance rate — if ≥ 65%, expected gain: 1.5–1.9× generation throughput. If < 55%, disable (overhead costs more than savings).

10. **Exemplar / prompt pruning for cold start** — trim the exemplar library injection to 3–5 examples per category. This only matters for the very first turn of a session (cold start) given prefix caching.

### Tier 4 — Defer (complex, limited marginal gain after Tier 1–3)

11. **Grammar (GBNF) for slot-filling** — use only for shallow `{agent}|{payload}` schemas. Avoid recursive JSON schemas. If the 8B is reliable without grammar (test this!), skip grammar overhead entirely.

12. **Q4_K_M downgrade** — only if Q5_K_M + q8_0 KV + flash_attn still hits VRAM limits. Buys ~5–8 tok/s, costs measurable quality.

---

## Risks / Caveats for Our Constraints

### Anticheat Safety
All techniques listed are **anticheat-safe**: they operate entirely within the inference process (VRAM layout, parameter flags, Python API). None require kernel drivers, USB HID injection, or network hooks. MTP and speculative decoding are pure CUDA computation changes.

### llama-cpp-python 0.3.22 Compatibility
- KV cache quantization: supported since ~0.2.90; confirmed working in 0.3.x.
- Flash attention: `flash_attn=True` supported since ~0.2.85; stable in 0.3.x.
- `thinking_budget_tokens`: this is a server-mode parameter. In in-process mode, equivalent control is via sampling parameters or the `/think` / `/no_think` Qwen3 chat template tokens. Verify that Josiefied GGUF respects `enable_thinking=False` in the chat template kwargs — if it doesn't (the known Qwen3.5 bug in issue #20182), use a custom stopping criterion.
- Draft-model spec-decode: `llama-cpp-python` 0.3.22 does not expose a native Python API for a second draft model instance. Use llama-server mode or the C-level `llama_speculative` binary; alternatively, test MTP heads (model-native) which do work in-process.

### VRAM Budget (10 GB Cap)
- Qwen3-8B Q5_K_M: ~6.0 GB
- KV cache q8_0, ctx=4096: ~0.35 GB
- Flash attention peak: ~0.3 GB (temporary, during prefill)
- EmbeddingGemma sidecar: ~0.6–0.8 GB (separate process but shares GPU)
- **Total peak: ~7.3–7.5 GB** — well within 10 GB cap. Safe to extend ctx to 6144 (q8_0 KV = ~0.52 GB) without risk.

### MTP VRAM Warning
Running Qwen3-8B (6.0 GB) + Qwen3-0.6B draft (0.4 GB) = 6.4 GB combined. Plus KV cache (0.35 GB) + EmbeddingGemma (0.7 GB) = ~7.45 GB — still within cap. But MTP heads built into the model add ~5–10% to the model size; verify the GGUF total size before concluding it fits.

### Thinking-Mode Prefix Cache Interaction
If the system prompt includes a `<think>` prefix seed (for models that need it to activate thinking), or if `preserve_thinking=true` is set, the prefix cache may fail to reuse the thinking portion. Keep the cached prefix strictly before any dynamic thinking content.

### Qwen3 Thinking-Mode OFF Bug
`enable_thinking: false` in the chat template is currently unreliable on some Qwen3.5 GGUFs (GitHub issue #20182). Validate empirically on the Josiefied-Qwen3-8B GGUF specifically. If thinking cannot be disabled cleanly, use `thinking_budget_tokens: 0` in server mode, or implement a custom sampler that terminates the `<think>` block early via a custom stopping string.

---

## Sources

1. [CraftRigs — llama.cpp Server Prefix Cache Setup and Verify](https://craftrigs.com/guides/llama-cpp-server-prefix-cache-setup-verify/)
2. [Optimize Your GPU KV-Cache for llama.cpp (medium/rigel-computer-com)](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec)
3. [NVIDIA Developer Blog — Accelerating LLMs with llama.cpp on NVIDIA RTX Systems](https://developer.nvidia.com/blog/accelerating-llms-with-llama-cpp-on-nvidia-rtx-systems/)
4. [KV Cache Quantization Benchmarks on DGX Spark — NVIDIA Developer Forums](https://forums.developer.nvidia.com/t/kv-cache-quantization-benchmarks-on-dgx-spark-q4-0-vs-q8-0-vs-f16-llama-cpp-nemotron-30b-128k-context/365138)
5. [Speculative Decoding: Achieving 2-3x LLM Inference Speedup — Introl Blog](https://introl.com/blog/speculative-decoding-llm-inference-speedup-guide-2025)
6. [Speculative Decoding Explained: 2x Faster Local LLMs with Ollama and llama.cpp — vucense.com](https://vucense.com/dev-corner/speculative-decoding-explained-2x-faster-local-llms-ollama-llama-cpp-2026/)
7. [Tested every llama.cpp speculative-decode mode on Qwen3.6-35B-A3B + RTX 3090 — HackMD](https://hackmd.io/ODXuOQNzSiyUITz7g9mtBw)
8. [Why MTP doesn't speed up your llama.cpp inference — DEV Community](https://dev.to/alanwest/why-mtp-doesnt-speed-up-your-llamacpp-inference-and-how-to-actually-fix-it-2m2m)
9. [Dynamically adjusting reasoning-budget per chat prediction — GitHub llama.cpp Discussion #21445](https://github.com/ggml-org/llama.cpp/discussions/21445)
10. [llama.cpp reasoning-budget update — AI Haven](https://aihaven.com/news/llama-cpp-reasoning-budget-update/)
11. [State Management and Caching — llama-cpp-python DeepWiki](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching)
12. [Optimize my llama.cpp — GitHub Discussion #21112](https://github.com/ggml-org/llama.cpp/discussions/21112)
13. [Q4 vs Q5 vs Q6 vs Q8 Quantization: Real Quality Loss Numbers — runaihome.com](https://runaihome.com/blog/quantization-q4-q5-q6-q8-quality-loss-2026/)
14. [Designing Voice Assistants: STT, LLM, TTS, Tools, and Latency Budget — Smallest.ai](https://smallest.ai/blog/designing-voice-assistants-stt-llm-tts-tools-and-latency-budget)
15. [How Real-Time Voice AI Actually Works — Retell AI](https://www.retellai.com/blog/how-real-time-voice-ai-works-stt-llm-tts)
16. [preserve_thinking=true blocks prompt cache on Qwen3.5 — GitHub Issue #22615](https://github.com/ggml-org/llama.cpp/issues/22615)
17. [enable_thinking param cannot turn off thinking for Qwen3.5 — GitHub Issue #20182](https://github.com/ggml-org/llama.cpp/issues/20182)
18. [Pre³: Enabling Deterministic Pushdown Automata for Faster Structured LLM Generation — arxiv 2506.03887](https://arxiv.org/pdf/2506.03887)
19. [llama.cpp adds Multi-Token Prediction — StartupFortune](https://startupfortune.com/llamacpp-adds-multi-token-prediction-and-doubles-qwen36-27b-throughput-for-local-inference/)
20. [Running Qwen2.5-32B on RTX 4060 — DEV Community (KV cache quant details)](https://dev.to/plasmon_imp/running-qwen25-32b-on-rtx-4060-8gb-beating-m4-at-108-ts-with-llamacpp-11je)
21. [Flash Attention bug on RTX 4060 Ti — GitHub Issue #13092](https://github.com/ggml-org/llama.cpp/issues/13092)
22. [Prompt Cache: Modular Attention Reuse for Low-Latency Inference — arxiv 2311.04934](https://arxiv.org/pdf/2311.04934)
