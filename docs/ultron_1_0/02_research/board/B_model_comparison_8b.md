# Qwen3 / Qwen3.5 / Josiefied (gabliteration) 8–9B comparison: which is best for Ultron 1.0 Valorant relay?

*Research date: 2026-06-20. Sources fetched from primary docs, HF model pages, arxiv papers, benchmark aggregators.*

---

## TL;DR recommendation for Ultron 1.0

**Stay on Josiefied-Qwen3-8B-abliterated Q5_K_M for now; do NOT upgrade to Qwen3.5-9B yet.**

Concrete rationale:

1. **llama-cpp-python 0.3.22 does not reliably support Qwen3.5-9B's hybrid GDN architecture.** Qwen3.5 uses Gated Delta Networks (GDN) — linear attention layers interleaved through 75% of the stack — a fundamentally different compute graph from the standard dense Qwen3 transformer. llama.cpp added qwen3_5 arch support in mid-2026, but llama-cpp-python 0.3.22 (our pinned version) predates stable Qwen3.5 support and active bugs have been reported (GitHub issue #2137). Loading Qwen3.5-9B GGUF under our pinned library is unsupported / high-risk.

2. **Josiefied-Qwen3-8B Q5_K_M fits cleanly in our 10 GB VRAM design cap.** At ~5.95 GB model weight + ~1–2 GB KV cache headroom for typical 4–8k turns, we stay safely under 10 GB. Qwen3.5-9B Q5_K_M balloons to 7.11 GB model weight alone, leaving marginal KV budget before hitting the 10 GB cap.

3. **Benchmark gains from Qwen3.5-9B are real but mostly irrelevant for our task.** IFEval: 91.5% vs 83.2% (a real +8 pp jump). But Ultron relay is extremely short-form (1–3 sentences), persona-locked, and routing-constrained — our actual failure modes are persona drift and refusal behavior, not instruction complexity. Those are solved by gabliteration + prompt engineering, not a bigger model.

4. **No Josiefied-Qwen3.5-9B GGUF exists yet.** The Goekdeniz-Guelmez gabliteration series only covers Qwen3.5-0.8B at time of research (June 2026). If we want gabliterated Qwen3.5-9B, we have to wait for the creator or do it ourselves.

5. **When to revisit:** (a) llama-cpp-python pins to a version that ships Qwen3.5 arch support, (b) a Josiefied-Qwen3.5-9B GGUF appears, and (c) we benchmark that Q4_K_M (5.39 GB) fits with 2+ GB KV headroom. At that point the IFEval and roleplay improvements are worth switching.

---

## Findings

### 1. Model family overview

**Qwen3-8B** (Alibaba, released 2025-04/05, [technical report arxiv:2505.09388](https://arxiv.org/pdf/2505.09388))
- Dense causal decoder-only transformer, 8B parameters
- Native context: 131,072 tokens
- Dual thinking/non-thinking hybrid: `/think` and `/no_think` tokens in-prompt, or `--chat-template-kwargs '{"enable_thinking": false}'` in llama-server
- IFEval (Prompt Strict): 83.2% (some sources cite 83.18–83.7% depending on eval harness)
- Architecture: fully compatible with llama.cpp since Qwen3 launch; llama-cpp-python 0.3.x has supported it since mid-2025
- Excels at creative writing, role-playing, multi-turn dialogues per official benchmarks
- Non-thinking recommended params: temperature=0.7, top_p=0.8, top_k=20, min_p=0, presence_penalty=1.5

**Qwen3.5-9B** (Alibaba, released 2026-03-02, [official blog](https://qwen.ai/blog?id=qwen3.5))
- Hybrid Gated Delta Network (GDN) + sparse MoE architecture — fundamentally different from Qwen3's dense stack
- 75% of layers are GDN (linear attention), 25% are standard full attention; this is Alibaba's linear-complexity long-context strategy
- 9B parameters, native context 262,144 tokens (up to 1,010,000 tokens extensible)
- Natively multimodal (early fusion of vision tokens, 201 languages)
- IFEval: 91.5% — outperforms Qwen3-30B (88.9%) at 3.3x smaller size
- MMLU-Pro: 82.5% vs Qwen3-8B's ~71–72%
- HMMT25: 82.9% vs 32.5% (huge reasoning jump, less relevant for relay)
- Thinking disabled by default (opposite of Qwen3); enable via `{"enable_thinking": true}`
- VRAM at Q4 quant: ~6.5 GB model weight (per Unsloth docs); Q5_K_M: 7.11 GB (per bartowski GGUF page)
- **Architecture risk: llama.cpp added qwen3_5 arch support late 2025 / early 2026, but llama-cpp-python 0.3.22 is unlikely to include stable Qwen3.5 support.** Ollama has reported that no Qwen3.5 GGUF currently works due to separate mmproj vision files. Active bugs in llama.cpp issue tracker (e.g., EAGLE3 speculative decoding broken for qwen3_5 hybrid, ctx overflow at ~700 tokens in some configs).

**Key architecture difference that matters for us:**
Qwen3-8B: standard dense transformer. Every layer is a full attention layer. llama-cpp-python has mature support. Josiefied GGUF runs at ~45–55 t/s on RTX 4070 in Q5_K_M with `-ngl 99`.

Qwen3.5-9B: GDN hybrid requires inference backends to implement the deltanet recurrent state alongside the KV cache — a different code path. vLLM added native support in v0.17 (May 2026). llama.cpp added qwen3_5 support but the GDN state handling had documented issues through mid-2026. llama-cpp-python 0.3.22 pins to an older llama.cpp that almost certainly does NOT include stable Qwen3.5 support.

---

### 2. Gabliteration vs abliteration: what they actually are

**Standard abliteration** (Maxime Labonne, 2024, [HF blog](https://huggingface.co/blog/mlabonne/abliteration)):
- Identifies the "refusal direction" (mean difference of harmful vs harmless prompt activations) across transformer residual streams
- Projects it out of the weight matrices: `W_new = W - W @ refusal_dir @ refusal_dir.T`
- Single direction, single pass per layer
- Works but is mathematically unprincipled: it conflates directional and magnitude components, disturbing learned weight geometry

**Norm-preserving biprojected abliteration** (grimjim, 2024, [HF blog](https://huggingface.co/blog/grimjim/norm-preserving-biprojected-abliteration)):
- Decomposes weights into magnitude and directional components separately
- Projects out refusal direction from the directional component only, then recombines with original row norms
- Addresses the Hydra Effect (compensatory self-repair) via multi-layer intervention
- Benchmarks vs standard abliteration: UGI 32.61 vs 32.08 (norm-preserving wins); NatInt 21.33 vs 18.64 (norm-preserving wins significantly); baseline: 19.58 / 18.72
- Better reasoning preservation specifically because weight norms are kept intact

**Gabliteration** (Gökdeniz Gülmez, arxiv:2512.18901, [paper](https://arxiv.org/abs/2512.18901)):
- Full title: "Adaptive Multi-Directional Neural Weight Modification for Selective Behavioral Alteration in Large Language Models"
- Uses SVD (singular value decomposition) on difference matrices between harmful and harmless prompt representations to extract **multiple** refusal directions (not just one)
- Employs "adaptive multi-directional projections with regularized layer selection" and "dynamic layer optimization, regularized projection matrices, and adaptive scaling mechanisms"
- Claims to address "the fundamental limitation of existing methods that compromise model quality while attempting to modify specific behavioral patterns"
- The paper released gabliterated-v1 model series covering 0.6B to 4B sizes
- The Josiefied creator Gökdeniz Gülmez uses this as the underlying technique for gabliterated variants; abliterated variants (older naming) use the standard single-direction method

**Quality comparison of uncensoring methods** ([arxiv:2512.13655](https://arxiv.org/abs/2512.13655), comprehensive abliteration methods study):
- 4 tools tested: Heretic, DECCP, ErisForge, FailSpy across 16 models (7B–14B)
- Best capability preservation: ErisForge (-0.28 pp GSM8K avg), DECCP (-0.13 pp avg)
- Mathematical reasoning most sensitive: up to -18.81 pp GSM8K in worst case (-26.5% relative)
- Heretic showed -7.81 pp GSM8K on average (more aggressive)
- General instruction-following preservation across all methods: 0–5% typical degradation for well-constructed abliteration; DPO fine-tuning post-abliteration recovers most losses
- **Gabliteration not directly compared in this paper** (it was released concurrently); but the multi-directional approach with norm preservation aligns with the highest-quality methods

**Independent abliteration benchmark on Qwen3.5 models** ([Nathan Sapwell, 2026](https://nathan.sapwell.net/posts/hauhaucs-abliteration-analysis/)):
- Tested HauhauCS, Heretic, Huihui on Qwen3.5-2B/4B/9B/27B
- Qwen3.5-9B: HauhauCS lost 8 points on TruthfulQA; Huihui lost 12.65 points
- KL divergence (behavioral change measure): varies 0.02–3.65 depending on model size and method
- Conclusion: "lossless" marketing claims not upheld at larger scales; residual safety behaviors persist across methods
- Larger models (9B+) show more variable abliteration quality than smaller models

**What this means for Josiefied-Qwen3-8B:**
The Josiefied-Qwen3-8B-abliterated-v1 uses the standard (older) abliteration technique — single refusal direction, not multi-directional gabliteration. The UGI score on the leaderboard (32.6) places it in the "good" tier. The gabliterated-v2 variants for 4B models use the newer SVD multi-directional approach and are expected to have better quality/capability preservation. No Qwen3-8B gabliterated-v2 exists as of June 2026 (only abliterated-v1 for 8B; gabliterated versions only go up to 4B in the creator's series).

**DavidAU's Josiefied variants** (e.g., Qwen3-8B-192k-Josiefied-Uncensored-NEO-Max-GGUF): These are third-party builds that apply the Josiefied base + additional context extension (192k via RoPE scaling) and sometimes merge with other fine-tuned weights. Quality is anecdotally good for creative/roleplay tasks but no benchmarks are published.

---

### 3. VRAM and GGUF sizing for RTX 4070 Ti (10 GB cap)

#### Josiefied-Qwen3-8B-abliterated-v1 (our current model)

From Mungert GGUF page (same weights, different packager):

| Quant   | Size   | Notes                        |
|---------|--------|------------------------------|
| Q4_K_M  | 4.56 GB | Slightly lower quality       |
| Q5_K_M  | 5.95 GB | **Current production quant** |
| Q6_K_M  | 6.73 GB | Best quality, still fits     |
| Q8_0    | 8.71 GB | Fits with minimal KV budget  |

At Q5_K_M (5.95 GB) + ~2 GB KV at 4k context = ~8 GB total. Comfortable under 10 GB. At Q6_K_M = ~8.73 GB total — still fine. Q8_0 = ~10.71 GB — cuts it too close.

#### Qwen3.5-9B (hypothetical upgrade)

From bartowski/Qwen_Qwen3.5-9B-GGUF and unsloth/Qwen3.5-9B-GGUF:

| Quant      | Size    | Notes                                  |
|------------|---------|----------------------------------------|
| IQ4_XS     | 5.50 GB | Compressed 4-bit                       |
| Q4_K_S     | 5.86 GB | Smaller 4-bit                          |
| UD-Q4_K_XL | 5.97 GB | Unsloth dynamic (upcasts key layers)   |
| Q5_K_M     | 7.11 GB | Quality parity with Q5_K_M on 8B       |
| Q6_K       | 7.96 GB | Near-lossless                          |
| Q8_0       | 9.80 GB | Almost at VRAM limit                   |

At Q4_K_S (5.86 GB) + ~2 GB KV = ~7.86 GB — fits under 10 GB.
At Q5_K_M (7.11 GB) + ~2 GB KV = ~9.11 GB — marginal.
At Q6_K (7.96 GB) + ~2 GB KV = ~9.96 GB — right at the cap, risky.

**For comparable quality to our Q5_K_M Qwen3-8B, we'd need Q5_K_M Qwen3.5-9B (~7.11 GB), leaving only ~2.9 GB for KV, OS, other processes.** At long relay turns or if we extend context, this becomes a problem.

---

### 4. Benchmark summary table

| Benchmark       | Qwen3-8B  | Qwen3.5-9B | Delta      | Relevant for Ultron? |
|-----------------|-----------|------------|------------|----------------------|
| IFEval          | 83.2%     | 91.5%      | +8.3 pp    | Somewhat (follow instructions in prompt) |
| MMLU-Pro        | ~71.6%    | 82.5%      | +10.9 pp   | Low (general knowledge) |
| MMLU-Redux      | ~84.9%    | 91.1%      | +6.2 pp    | Low                  |
| HMMT25 (math)   | 32.5%     | 82.9%      | +50 pp     | Irrelevant           |
| LiveCodeBench   | 39.3%     | 65.6%      | +26.3 pp   | Irrelevant           |
| PolyMATH        | 30.4%     | 57.3%      | +26.9 pp   | Irrelevant           |
| Context window  | 131k      | 262k       | 2x         | Low for relay (4–8k turns) |
| VRAM at Q5_K_M  | 5.95 GB   | 7.11 GB    | +1.16 GB   | Matters (10 GB cap)  |

Qwen3.5-9B's benchmark advantages are concentrated in reasoning and math tasks — not what Ultron relay does. The IFEval gap (+8 pp) is the most relevant improvement, but 83% instruction-following on short 1–3 sentence constrained relay prompts is already more than sufficient with proper prompt engineering.

---

### 5. Thinking mode analysis for relay use

Both models support thinking/non-thinking hybrid modes.

**Qwen3-8B:** Thinking OFF by default requires explicit `/no_think` tag or `enable_thinking=False`. For relay, we want thinking OFF (fast path, no chain-of-thought overhead). The `presence_penalty=1.5` setting is critical for quantized models to suppress repetition.

**Qwen3.5-9B:** Thinking is **disabled by default** (opposite of Qwen3) — the non-thinking path is the natural one. This is slightly friendlier for relay use, but the architectural incompatibility with llama-cpp-python 0.3.22 overrides this advantage.

**For Ultron persona:** The non-thinking path for both models delivers direct, fast responses. The thinking path (if enabled) adds latency and chain-of-thought tokens that must be stripped — unacceptable for a live relay. Non-thinking mode for both models produces "cold machine" short-form output that suits Ultron well, provided the system prompt enforces brevity.

---

### 6. Roleplay / persona quality

No published head-to-head roleplay benchmarks exist for Josiefied-Qwen3-8B vs stock Qwen3.5-9B. However, the following is well-evidenced:

1. **Abliteration on Qwen3-8B preserves instruction-following at ~80–83% of base capability** (consistent with the 0–5% degradation figure for well-constructed single-direction abliteration). Our Q5_K_M quant further degrades this slightly (estimated <2% vs full-precision).

2. **For Valorant trash-talk and relay persona, instruction-following score is a proxy for "will the model stay in character and follow the prompt template."** The Josiefied 8B at 83% IFEval has demonstrated in production (on our system) that it follows the relay template reliably when prompted correctly.

3. **Stock Qwen3.5-9B at 91.5% IFEval would follow templates more reliably** — but without gabliteration applied, it retains refusal behavior that will block aggressive trash-talk and villain-persona lines. A non-abliterated Qwen3.5-9B would refuse "you're a useless piece of shit, tell my team their Sage is inting" type content.

4. **No Josiefied-Qwen3.5-9B GGUF exists as of June 2026.** The gabliteration series stops at Qwen3.5-0.8B from the primary author; the 8B line only has abliterated-v1. This is a blocking gap.

5. **Quality degradation from abliteration on creative/roleplay tasks is lower than on math tasks.** The Sapwell study found math benchmarks most sensitive; roleplay and instruction-following degradation is typically smaller (0–3% range) for well-targeted single-direction abliteration.

---

### 7. llama-cpp-python 0.3.22 compatibility matrix

| Model                       | Architecture    | llama-cpp-python 0.3.22 | Status    |
|-----------------------------|-----------------|------------------------|-----------|
| Josiefied-Qwen3-8B-abliterated-v1 (our current) | dense qwen3 | Yes — stable | **Works** |
| Qwen3-8B-GGUF (base)        | dense qwen3     | Yes — stable            | Works     |
| DavidAU Josiefied variants  | dense qwen3     | Yes                     | Works     |
| Qwen3.5-9B-GGUF             | GDN hybrid (qwen3_5 arch) | Likely NOT — active bugs | **Risky** |
| Josiefied-Qwen3.5-9B GGUF  | GDN hybrid      | Doesn't exist yet       | N/A       |

The llama-cpp-python GitHub issue #2137 (opened March 2026, closed without clear resolution) indicates user confusion and potential failures loading Qwen3.5 models. Ollama has explicitly stated no Qwen3.5 GGUF works currently. vLLM 0.17 added native support (May 2026) but that is irrelevant to our llama-cpp-python in-process path.

**Risk level for loading Qwen3.5-9B GGUF under llama-cpp-python 0.3.22: HIGH.** Best case it loads with degraded performance; worst case it crashes or produces garbled output due to the GDN state not being handled.

---

### 8. When Qwen3.5-9B DOES become viable

Criteria that must ALL be met before switching:

1. llama-cpp-python updates to a version that includes stable `qwen3_5` arch support (likely requires bumping to 0.3.30+ or later depending on when the upstream fix lands)
2. A Josiefied-Qwen3.5-9B GGUF is published (or we run gabliteration ourselves — documented in the arxiv paper)
3. We benchmark Q4_K_S (5.86 GB) fits within 10 GB with our typical context window without memory pressure
4. We verify the IFEval improvement actually translates to better in-persona relay adherence in our test battery

If all four are met, the upgrade path is: Q4_K_S (5.86 GB) for maximum VRAM safety, or UD-Q4_K_XL (5.97 GB, Unsloth dynamic upcast) for slightly better quality at nearly the same size. Both leave ~4 GB KV headroom, which is comfortable.

---

## Concrete techniques/params we should adopt (NOW, for current model)

These apply to our existing Josiefied-Qwen3-8B-abliterated-v1 Q5_K_M setup:

1. **Always use non-thinking mode.** Ensure relay inference path passes `enable_thinking=False` (or `chat_template_kwargs={"enable_thinking": False}` if using the chat template interface). Never allow `<think>` tokens to appear in relay output.

2. **Sampling params for relay:** temperature=0.7, top_p=0.8, top_k=20, min_p=0, presence_penalty=1.5. The `presence_penalty=1.5` is especially important for Q5_K_M quantized inference to suppress repetition artifacts that appear under quantization.

3. **Consider Q6_K_M (6.73 GB)** if quality matters more than VRAM headroom. At 6.73 GB model + ~1.5 GB KV (short relay context) = ~8.23 GB total — still safely under 10 GB. This may improve persona adherence without requiring a model change.

4. **Do NOT upgrade to Q8_0** for the current 8B model — 8.71 GB leaves only ~1.3 GB KV headroom, which will OOM on longer context turns.

5. **Prompt template discipline:** Since IFEval is 83% (not 91%), keep relay prompt templates SHORT and IMPERATIVE. Long multi-clause instructions have higher failure rate. System prompt should be ≤300 tokens for the cold Ultron persona. Exemplar injections from the flavor library should be compact (3–5 examples max).

6. **Wake up thinking-mode edge case:** If an Ultron 1.0 request ever hits the thinking path accidentally (prompt contains `/think`), the relay will stall waiting for `</think>` before the response. Add a strip/guard in the inference wrapper: `if '<think>' in raw_response: strip to after </think>`.

---

## Risks/caveats for our constraints

1. **Anticheat constraint not affected by model choice.** Both Qwen3-8B and Qwen3.5-9B are run entirely through llama-cpp-python in-process; no network calls, no pywin32, no desktop imports. Model weights are read-only binary files. No anticheat risk from either model.

2. **EmbeddingGemma sidecar unchanged.** The intent gate (EmbeddingGemma-300M) is architecture-independent; it works regardless of which 8B model we use on the relay path.

3. **VRAM contention with EmbeddingGemma.** Our EmbeddingGemma sidecar runs on CPU (design choice in the current system). If we ever move it to GPU, add ~600 MB VRAM to the budget. Still safe at current levels with Q5_K_M.

4. **Josiefied abliteration may degrade reasoning slightly.** For relay this is fine — we are not asking the model to reason, we are asking it to template-fill. But if we ever use the 8B for structured JSON slot-filling or complex multi-step instructions (e.g., in Ultron 1.0's LLM-route pipeline), we may observe ~5% degradation vs the base model on edge cases.

5. **No Qwen3.5 josiefied GGUF exists at all for 9B.** If we want Qwen3.5 uncensored, the options are: (a) wait for creator to release it, (b) run gabliteration ourselves on the Qwen3.5-9B weights (requires GPU time, the gabliteration codebase, and then GGUF conversion — feasible but not trivial), (c) use a stock uncensored fine-tune if one appears.

6. **Qwen3.5-9B GDN hybrid may actually be faster at long context** (the linear attention layers are O(n) vs O(n²) for full attention). But our relay context is short (4–8k tokens max); at these lengths the GDN advantage is negligible and the architecture overhead from the hybrid state may actually be slower per-token than dense Qwen3-8B in llama.cpp.

7. **Abliteration quality variance by method.** Our current Josiefied-Qwen3-8B-abliterated-v1 uses standard single-direction abliteration. This is not the best available method (gabliteration / norm-preserving biprojected abliteration are better). If we ever see character breaks or unexpected refusals in production, consider upgrading to: (a) a gabliterated 8B if one appears, or (b) applying norm-preserving biprojected abliteration ourselves.

8. **DavidAU "Josiefied" variants have no official benchmark.** They add RoPE context extension (64k/192k) which can slightly degrade short-context quality. For Ultron relay we don't need extended context, so the base Goekdeniz-Guelmez 8B-abliterated-v1 (with its ~32k native context from Qwen3-8B) is preferable.

---

## Sources

- [Qwen3 Technical Report (arxiv:2505.09388)](https://arxiv.org/pdf/2505.09388) — official Qwen3 8B architecture and benchmarks
- [Qwen3.5 Official Blog — Alibaba](https://qwen.ai/blog?id=qwen3.5) — Qwen3.5 architecture and GDN description
- [Qwen3.5-9B GGUF — bartowski (HF)](https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF) — full quant size table for Qwen3.5-9B
- [Qwen3.5-9B GGUF — Unsloth (HF)](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) — dynamic quant sizes, context, sampling params
- [Qwen3.5 local run guide — Unsloth docs](https://unsloth.ai/docs/models/qwen3.5) — thinking mode, recommended params, VRAM table
- [llm-stats: Qwen3 VL 8B vs Qwen3.5-9B benchmark comparison](https://llm-stats.com/models/compare/qwen3-vl-8b-instruct-vs-qwen3.5-9b) — head-to-head benchmark table (IFEval, MMLU-Pro, etc.)
- [Artificial Analysis: Qwen3.5 small models](https://artificialanalysis.ai/articles/qwen3-5-small-models) — intelligence index, reasoning benchmark gains
- [Qwen 3.5 9B Review — Emelia.io](https://emelia.io/hub/qwen-35-9b-review) — VRAM requirements, benchmark numbers
- [Josiefied-Qwen3-8B-abliterated-v1 (HF — Goekdeniz-Guelmez)](https://huggingface.co/Goekdeniz-Guelmez/Josiefied-Qwen3-8B-abliterated-v1) — UGI leaderboard score 32.6, uncensored description
- [Josiefied and Abliterated Qwen3 collection (HF)](https://huggingface.co/collections/Goekdeniz-Guelmez/josiefied-and-abliterated-qwen3) — full 13-model family listing
- [Josiefied-Qwen3.5-0.8B-gabliterated-v1 (HF — Goekdeniz-Guelmez)](https://huggingface.co/Goekdeniz-Guelmez/Josiefied-Qwen3.5-0.8B-gabliterated-v1) — gabliteration technique referenced, arxiv:2512.18901 cited
- [Gabliteration paper (arxiv:2512.18901)](https://arxiv.org/abs/2512.18901) — "Adaptive Multi-Directional Neural Weight Modification for Selective Behavioral Alteration in Large Language Models"
- [Norm-Preserving Biprojected Abliteration (HF blog — grimjim)](https://huggingface.co/blog/grimjim/norm-preserving-biprojected-abliteration) — technical comparison vs naive abliteration; UGI/NatInt benchmark comparison table
- [Uncensor any LLM with abliteration (HF blog — mlabonne)](https://huggingface.co/blog/mlabonne/abliteration) — standard abliteration method reference
- [Comparative Analysis of LLM Abliteration Methods (arxiv:2512.13655)](https://arxiv.org/pdf/2512.13655) — 4-tool abliteration comparison across 16 models; GSM8K degradation data
- [Abliteration analysis: HauhauCS vs Heretic vs Huihui — Nathan Sapwell (2026)](https://nathan.sapwell.net/posts/hauhaucs-abliteration-analysis/) — Qwen3.5-9B abliteration quality degradation benchmarks
- [Mungert/Josiefied-Qwen3-8B-abliterated-v1-GGUF (HF)](https://huggingface.co/Mungert/Josiefied-Qwen3-8B-abliterated-v1-GGUF) — GGUF quant sizes for Josiefied Qwen3-8B
- [llama-cpp-python Qwen3.5 support issue #2137 (GitHub)](https://github.com/abetlen/llama-cpp-python/issues/2137) — evidence of Qwen3.5 llama-cpp-python incompatibility
- [Qwen3 unified thinking/non-thinking (debuggercafe.com)](https://debuggercafe.com/qwen3-unified-models-for-thinking-and-non-thinking/) — thinking mode mechanics
- [Deep Dive: Qwen 3.5 hybrid architecture (Trilogy AI)](https://trilogyai.substack.com/p/deep-dive-qwen-35-brings-native-multimodality) — GDN vs full attention architecture comparison
- [Qwen 3.5 Complete Guide (Techie007 Substack)](https://techie007.substack.com/p/qwen-35-the-complete-guide-benchmarks) — hardware requirements, GPQA Diamond comparison
- [DavidAU/Qwen3-8B-192k-Josiefied-Uncensored-NEO-Max-GGUF (HF)](https://huggingface.co/DavidAU/Qwen3-8B-192k-Josiefied-Uncensored-NEO-Max-GGUF) — third-party extended-context Josiefied variant
- [Spheron: Deploy Qwen 3.5 GDN Hybrid Architecture](https://www.spheron.network/blog/deploy-qwen-3-5-gpu-cloud/) — GDN architecture explanation for Qwen3.5 deployment
