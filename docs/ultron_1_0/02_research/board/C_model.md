# Adversarial Verification: Model Choice for Ultron 1.0

**Layer:** C (Adversarial)
**Cluster:** Model comparison, thinking mode, VRAM budget, serving stack
**Adversarial agent:** claude-sonnet-4-6, 2026-06-20
**Source docs reviewed:** B_model_comparison_8b.md, B_qwen3_thinking.md, B_prefix_cache_vram.md, B_serving_alternatives.md

---

## Goal

Refute or qualify the Layer-B recommendation to stay on Josiefied-Qwen3-8B-abliterated-v1 Q5_K_M via llama-cpp-python 0.3.22. Find: counter-evidence on VRAM fit, speed, abliteration quality, llama.cpp compatibility, and whether Qwen3.5-9B is actually blocked.

---

## Claims Examined

1. Q5_K_M (5.95 GB) + 2 GB KV = ~8 GB total, comfortably under 10 GB
2. Qwen3.5-9B GDN architecture is incompatible with llama-cpp-python 0.3.22
3. Josiefied-Qwen3-8B uses standard (single-direction) abliteration, not gabliteration, causing measurable quality loss
4. IFEval 83.2% is sufficient for short relay persona tasks
5. Thinking mode on 8B adds 10-60 seconds dead time before first response
6. `/no_think` soft switch reliably disables thinking in in-process llama-cpp-python
7. No Josiefied-Qwen3.5-9B GGUF exists, blocking upgrade
8. llama-cpp-python 0.3.22 is the right stack; alternatives fail on anticheat or in-process constraints
9. Speculative decoding does not improve single-user 8B throughput on RTX 4070 Ti
10. Q6_K_M is worth considering as an upgrade over Q5_K_M

---

## Verdict Per Claim

### Claim 1: Q5_K_M fits cleanly within 10 GB VRAM cap

**QUALIFIED — the math holds but the safety margin is larger than stated.**

The B-layer claimed ~8 GB total (5.95 GB weights + 2 GB KV at 4-8k context). Independent measurement from llmrun.dev gives Q5_K_M at **6.4 GB** for this model (model weights + alignment), slightly higher than the 5.95 GB GGUF size alone, consistent with actual CUDA allocation overhead. At n_ctx=4096 with Q8_0 KV quantization, the B_prefix_cache_vram formula gives 0.30 GB KV + 0.5 GB CUDA overhead = ~7.2 GB total. At FP16 KV, 0.59 GB KV = ~7.5 GB. Both are comfortably under 10 GB.

**Correction:** The 2 GB KV figure at 4k context is pessimistic — actual KV at n_ctx=4096 (FP16) is ~0.59 GB for Qwen3-8B due to its 8 GQA KV heads (4x fewer than Llama-class models). The B-layer's claim is CONSERVATIVE (safe), not optimistic. Total at 4k FP16 is closer to 7.5 GB not 8 GB. At full 40K context, KV adds ~5.7 GB (llmrun.dev), putting total at ~12.1 GB — this EXCEEDS 10 GB. The 10 GB cap is safe only for ≤8K contexts (Q8_0 KV, ≤1.18 GB) or ≤16K (Q8_0 KV, ≤1.77 GB). For any relay path using extended context, the cap binds.

**Source:** llmrun.dev hardware table for Josiefied-Qwen3-8B-abliterated-v1; B_prefix_cache_vram KV formula cross-check.

---

### Claim 2: Qwen3.5-9B GDN is incompatible with llama-cpp-python 0.3.22

**CONFIRMED — and the failure mode is harder than the B-layer described.**

The B-layer cited GitHub issue #2137 (user confusion, CMAKE issues). The actual confirmed failure is more specific and serious: llama.cpp issue #23347 (filed May 2026) documents an **GGML_ASSERT abort** in `sched_reserve()` during context initialization. The assertion checks that tensor names start with `__fgdn_ar__-<suffix>` but the GDN callback names tensors `__fgdn_ar__` (no suffix), causing an unconditional abort before inference begins. This assertion has been in llama-context.cpp since PR #20340 (2026-03-11). The bug affects all current Qwen3.5 GGUFs.

llama-cpp-python 0.3.22 was released ~May 2, 2026 (latest is 0.3.31 as of June 20, 2026). Issue #23347 was filed after 0.3.22 shipped, meaning the fix (if any) is in 0.3.23+ or later. No confirmed fix was found in the search results; the issue was open as of the research date.

Additional bug: llama.cpp issue #20182 documents `enable_thinking=false` failing to disable thinking on Qwen3.5 models (still thinking despite the flag). This is a separate bug from the FGDN_AR abort — even if the abort were fixed, the thinking-mode control is broken.

**Additional disconfirming evidence:** Unsloth docs say "Currently no Qwen3.5 GGUF works in Ollama due to separate mmproj vision files." This is a different failure mode (Ollama's wrapper) but reflects the general fragility of Qwen3.5 GGUF support across the ecosystem.

**Corrective nuance:** llama-cpp-python 0.3.31 (latest, June 20 2026) MAY include a fix. The example in PyPI docs shows `lmstudio-community/Qwen3.5-0.8B-GGUF` loading, suggesting the 0.8B version at least can be loaded in SOME builds of llama.cpp. Whether the 9B (larger, same architecture) works is unverified. The NVIDIA DGX Spark forums show Qwen3.5 GGUF benchmarks running over llama.cpp RPC, but on specialized hardware (Grace Blackwell), not consumer RTX.

**Bottom line:** The B-layer's claim is confirmed and strengthened. The risk is even higher than described — it is not just "active bugs" but a hard abort at context init, not a degraded-inference scenario.

---

### Claim 3: Josiefied-Qwen3-8B uses standard single-direction abliteration (not gabliteration), causing measurable quality loss

**CONFIRMED — with an important quantitative refinement.**

The HuggingFace model card for Josiefied-Qwen3-8B-abliterated-v1 confirms this is the older naming convention ("abliterated-v1") and lists no technical details about the method. The UGI score of 32.6 is the only metric published. No IFEval or MMLU comparison between abliterated and base Qwen3-8B is publicly available.

The Nathan Sapwell study (cited in B-layer) measured abliteration on Qwen3.6-27B (a larger, different model). On the 27B model, when accounting for incomplete responses due to truncated thinking budgets, math degradation was only 2.8 pp. For non-math benchmarks: MMLU -2.0 pp worst case, HellaSwag -6.2 pp worst case, TruthfulQA -10.6 pp worst case. Heretic and Huihui showed the best capability preservation.

**The B-layer's claim that instruction-following degradation is "0-5% typical" is consistent with the evidence but not proven specifically for Josiefied-Qwen3-8B.** The arxiv:2512.13655 comparison study did NOT include gabliteration in its comparison set. The claim that gabliteration is better than single-direction abliteration is supported only by the gabliteration paper itself (arxiv:2512.18901, authored by the same person who created Josiefied), which is a conflict-of-interest source.

**The adversarial finding:** The comparison between Heretic (KL divergence 0.16) and manual abliteration methods (KL 0.45-1.04) on Gemma-3-12B shows that automated methods can achieve better quality preservation than human-optimized abliteration. The single-direction standard abliteration (Josiefied v1) may actually be the worst of the available methods. If quality degradation in persona maintenance is ever observed in production, switching to a Heretic-abliterated Qwen3-8B variant would be the correct mitigation — not waiting for a Josiefied v2.

**Concrete risk for Ultron:** The most sensitive benchmark is TruthfulQA (up to -10.6 pp). For Ultron relay, "truthfulness" maps to accuracy of tactical information relayed. If the model invents or corrupts agent callouts, this is the mechanism.

---

### Claim 4: IFEval 83.2% is sufficient for 1-3 sentence constrained relay prompts

**CONFIRMED — but with an important caveat about abliteration interaction.**

The B-layer's reasoning is sound: short-form, template-driven relay generation does not need the full IFEval score to be high. The model only needs to follow: (a) stay in persona, (b) produce 1-3 sentences, (c) relay the correct tactical content. These are simpler constraints than the full IFEval benchmark.

**Adversarial finding:** IFEval 83.2% is for the BASE Qwen3-8B. No abliterated-v1 IFEval score exists. Standard single-direction abliteration targets refusal directions specifically, but it can accidentally project out instruction-following dimensions that are geometrically correlated with the refusal direction. The norm-preserving biprojected abliteration (grimjim) was explicitly designed to avoid this. The standard method used in Josiefied-v1 does not preserve norms.

For the Ultron relay use case, the risk is: a persona that has been told "speak like a cold superior machine, one sentence maximum" may occasionally bleed through to more verbose or off-persona outputs due to abliteration disturbing the instruction-adherence dimensions. This has not been measured. The B-layer's 0-5% degradation estimate may be optimistic for instruction-following specifically (as opposed to math, where the Sapwell data is available).

**Practical recommendation:** Run the existing MP3 battery on the abliterated model vs stock Qwen3-8B-Instruct (with a system prompt that refuses unsafe content) and compare instruction-following rate directly. This is the only way to ground the IFEval gap for this specific use case.

---

### Claim 5: Thinking mode on 8B adds 10-60 seconds of dead time

**CONFIRMED — with stronger grounding than the B-layer provided.**

The B-layer cited ~50 tok/s generation speed and 500-3000 token thinking chains for 10-60 seconds. Independent data from Artificial Analysis places Qwen3-8B (via Alibaba API, non-thinking) at 39.4 tok/s output throughput. On local hardware (RTX 4070 Ti, Q5_K_M), community reports suggest 50-80 tok/s decode.

At 50 tok/s, 500 thinking tokens = 10 seconds, 3000 tokens = 60 seconds. This calculation is correct.

**Additional adversarial finding from arxiv:2502.16940 ("Reasoning Does Not Necessarily Improve Role-Playing Ability"):** The paper finds that thinking/reasoning mode does NOT improve role-playing quality and can harm it — the model spends budget reasoning about the task analytically rather than generating authentic in-character responses. This directly supports the B-layer recommendation to use no-think mode for relay paths but goes further: thinking mode should be avoided even for complex tactical queries in a persona-first system.

For Ultron 1.0, thinking mode should be disabled by default for ALL relay paths (confirmed). The "think hard" path proposed in B_qwen3_thinking.md (for "analyze" intents) should be treated with skepticism: it adds latency AND may degrade persona quality simultaneously.

---

### Claim 6: `/no_think` soft switch reliably disables thinking in in-process llama-cpp-python

**QUALIFIED — reliability is lower than the B-layer suggests.**

The B-layer notes that `chat_template_kwargs={"enable_thinking": False}` is the reliable hard switch. It acknowledges the soft switch (`/no_think`) is less reliable.

**Adversarial finding:** llama.cpp issue #20182 documents `enable_thinking=false` failing to disable thinking on Qwen3.5 models specifically. For Qwen3-8B (our model, NOT Qwen3.5), the issue is distinct: users report mixed results with `--reasoning-budget 0` vs `enable_thinking` vs `/no_think` soft switch. The deprecation of `chat_template_kwargs` in llama.cpp >= b8322 means behavior depends on which llama.cpp build is pinned in 0.3.22.

**The B-layer correctly identifies the most reliable approach for Qwen3-8B:** set `enable_thinking=False` at model load via `chat_template_kwargs`. However, it also notes this was deprecated in b8322+. The 0.3.22 wrapper pins an unknown llama.cpp build (released ~May 2, 2026). If that build includes the deprecation, the `chat_template_kwargs` approach may silently fail without an error.

**Practical risk:** The `/no_think` soft switch in the system prompt is the belt-and-suspenders fallback. The B-layer's recommendation to use BOTH (hard switch at load + soft switch in system prompt) is the correct defensive posture. The claim that the soft switch "still works reliably" is true for the standard Qwen3-8B chat template but cannot be guaranteed for the abliterated Josiefied variant (abliteration does not modify the Jinja2 template, so it should be fine — but this is assumed, not verified).

---

### Claim 7: No Josiefied-Qwen3.5-9B GGUF exists

**CONFIRMED — no disconfirming evidence found.**

Web search confirms the Goekdeniz-Guelmez gabliteration series covers only Qwen3.5-0.8B as of June 2026. The 9B is not listed. Unsloth has released Qwen3.5-9B-GGUF and Qwen3.5-9B-MTP-GGUF (standard quantizations), but these are uncensored only to the extent Qwen3.5 base is uncensored (less than abliterated).

**Additional adversarial finding:** The B-layer mentions "do it ourselves" (run gabliteration on Qwen3.5-9B weights). This is feasible in principle but blocked by the FGDN_AR abort bug in current llama.cpp builds — the resulting GGUF would not load for inference under llama-cpp-python 0.3.22. So even if we ran gabliteration ourselves, we could not use the result in the current stack.

---

### Claim 8: llama-cpp-python in-process is the correct stack; alternatives fail

**CONFIRMED for our constraints — with one nuance.**

The B_serving_alternatives.md analysis is correct. The constraint matrix rules out all alternatives on at least one hard constraint (Windows-native, in-process, GGUF format, grammar support, VRAM budget).

**Adversarial finding — the grammar+thinking bug (llama.cpp issue #20345) is the most serious active risk:**
When `response_format` (JSON schema grammar) is active AND `enable_thinking=True`, grammar enforcement is completely inactive. This is a hard blocker for intent classification with grammar-constrained JSON output and thinking enabled simultaneously. The B-layer acknowledges this but calls it "the one actionable finding." It should be treated as a DESIGN CONSTRAINT: the intent gate MUST use `enable_thinking=False`, confirmed and unambiguous.

**Nuance on 0.3.22 vs 0.3.31:** llama-cpp-python 0.3.31 was released June 20, 2026 (same day as this research). The 9-version gap between 0.3.22 and 0.3.31 may include Qwen3.5 fixes, grammar+thinking fixes, or other relevant changes. Pinning to 0.3.22 is a conservative choice that avoids untested regressions, but it may also prevent access to bug fixes relevant to our constraints. The upgrade path to 0.3.31 should be evaluated before Ultron 1.0 ships — in a test environment, not production.

---

### Claim 9: Speculative decoding does not help for dense 8B on single RTX consumer GPU

**CONFIRMED — evidence is solid.**

The B_serving_alternatives.md cites the RTX 3090 + Qwen3.6-35B-A3B benchmark showing all 19 speculative decode configurations slower than baseline. The dense 8B case is even less favorable for speculative decoding (draft acceptance rate is lower for more capable target models). No disconfirming evidence found.

**Adversarial finding:** The "Qwen 3.6 MTP (multi-token-prediction) ~30% speedup on RTX 4070" result is for an ARCHITECTURE-LEVEL feature baked into different model weights, not a GGUF/llama.cpp speculative decode configuration. It is not applicable to Josiefied-Qwen3-8B. The B-layer correctly distinguishes this.

---

### Claim 10: Q6_K_M is worth considering as an upgrade over Q5_K_M

**CONFIRMED — and the upgrade is likely cost-free under our VRAM budget.**

llmrun.dev measures Q6_K at **7.4 GB** for Josiefied-Qwen3-8B (vs 6.4 GB for Q5_K_M). The perplexity improvement from Q5_K_M to Q6_K is small but real: the runaihome.com quantization study measures +0.0142 pp perplexity above FP16 for Q5_K_M vs +0.0044 pp for Q6_K — a 3.2x better approximation of the original model.

At n_ctx=4096 with Q8_0 KV (0.30 GB) + CUDA overhead (0.5 GB): Q6_K total = 7.4 + 0.30 + 0.5 = **8.2 GB** — within the 10 GB cap with 1.8 GB headroom. This is tighter than Q5_K_M (8 GB margin) but still safe for 4K relay context.

**The B-layer's recommendation to "consider Q6_K_M" is correct.** For a relay path with n_ctx=4096, Q6_K adds 1 GB VRAM for meaningfully better weight fidelity. It is the recommended upgrade if VRAM headroom is not needed for other uses.

**Adversarial caveat:** instruction-tuned models are highly robust to quantization differences (runaihome.com: identical HumanEval pass@1 between Q4_K_M and Q5_K_M). For 1-3 sentence relay outputs, the perplexity difference between Q5_K_M and Q6_K may be undetectable in practice. The upgrade is cheap and risk-free, but do not expect dramatic quality improvement.

---

## Corrected Recommendation for Ultron 1.0

**The B-layer recommendation to stay on Josiefied-Qwen3-8B-abliterated-v1 Q5_K_M is correct.** No disconfirming evidence overturns it. The following corrections and additions apply:

### What the B-layer gets right (keep as-is)
- Stay on Josiefied-Qwen3-8B Q5_K_M for now
- Do NOT upgrade to Qwen3.5-9B under the current stack (hard abort bug confirmed)
- Use no-think mode for ALL relay paths
- Keep EmbeddingGemma sidecar CPU-only
- Do NOT enable speculative decoding
- Stay on llama-cpp-python in-process

### Corrections and additions

**1. Upgrade to Q6_K immediately (not "consider").**
Q6_K (7.4 GB) fits under 10 GB at n_ctx=4096 with Q8_0 KV. It is a 3.2x better weight approximation than Q5_K_M with no other downside. Download it now.

**2. Context cap is 8K, not 16K-ish, under the 10 GB constraint.**
At Q6_K + FP16 KV + n_ctx=16384: 7.4 + 2.36 + 0.5 = 10.26 GB — over cap. Keep n_ctx=8192 as the hard max; use 4096 for relay. Explicitly document this in the config.

**3. Do not extend context to 40K under ANY circumstances at this VRAM level.**
Full 40K context adds ~5.7 GB KV (FP16), bringing total to ~13.7 GB with Q5_K_M weights — far exceeding the 12 GB physical VRAM. Even with Q4_0 KV (÷4), 40K = ~1.4 GB KV, total ~8.3 GB — borderline. Long-context relay is not needed; enforce n_ctx=4096 in the Llama() constructor to prevent accidental extension.

**4. Thinking mode also harms persona quality (not just adds latency).**
Disable thinking for ALL paths by default, including any planned "analyze" or "think hard" path. The arxiv:2502.16940 finding that reasoning mode does NOT improve role-playing should suppress the "think hard" idea entirely for a persona-first system.

**5. Upgrade llama-cpp-python to 0.3.31 in a test environment before locking it.**
0.3.31 (June 20, 2026) is 9 versions ahead of 0.3.22. It may include fixes for the grammar+thinking bug (#20345) and other relevant issues. Test the Josiefied GGUF under 0.3.31 before Ultron 1.0 ships; if stable, upgrade.

**6. Track the FGDN_AR abort fix in llama.cpp (issue #23347).**
When that is resolved AND a Josiefied-Qwen3.5-9B GGUF appears AND llama-cpp-python ships the fix, run a controlled VRAM test at Q4_K_S (estimated 5.86 GB model + 0.30 GB KV + 0.5 GB overhead = 6.66 GB) — well under 10 GB. At that point, the upgrade may be worthwhile for the IFEval gap (+8.3 pp).

**7. Consider a Heretic-abliterated Qwen3-8B as a drop-in backup.**
If Josiefied-Qwen3-8B shows persona drift or TruthfulQA-type tactical errors in production testing, Heretic abliteration (KL divergence 0.16 on Gemma-3-12B vs 1.04 for manual methods) may offer better instruction-following preservation. The `huihui-ai/Qwen3-8B-abliterated` is a published alternative with good community feedback. Test it against the relay MP3 battery before committing.

**8. IFEval baseline for the abliterated model is unknown — measure it.**
No IFEval score exists for Josiefied-Qwen3-8B-abliterated-v1. The B-layer's "83.2%" is the base model score. Abliteration with single-direction projection can reduce IFEval by 0-8 pp depending on the geometric alignment of the refusal and instruction-following directions. For a relay system, run a simple 50-prompt instruction-following battery on both models (abliterated vs base with safety prompt) and measure the gap directly.

---

## Residual Risks

**R1 — VRAM spike on context extension.** If any code path fails to enforce n_ctx=4096 and generates a longer context, VRAM can spike above 10 GB mid-session, causing an OOM crash during a live game. Mitigation: set `n_ctx=4096` in the Llama() constructor (hard cap), not just as a guideline. The `max_tokens=256` per-call cap guards the output side but not the input context.

**R2 — Abliteration quality unknown for this specific model.** No abliterated-vs-base IFEval comparison exists for Josiefied-Qwen3-8B-abliterated-v1. The 0-5% degradation figure is a class-level estimate. The actual figure could be higher (up to 8 pp based on the arxiv:2512.13655 worst-case for standard single-direction abliteration). This risk is real and unquantified.

**R3 — `/no_think` reliability on the abliterated GGUF.** Abliteration does not modify the Jinja2 chat template, so `/no_think` should behave identically to the base model. However, if abliteration disturbs the hidden-state geometry that the template relies on, soft switches may be less reliable. This cannot be confirmed without empirical testing on the specific GGUF.

**R4 — llama-cpp-python 0.3.22 `chat_template_kwargs` deprecation.** If the pinned build is >= b8322, `chat_template_kwargs={"enable_thinking": False}` at model load may be silently ignored. The fallback (soft `/no_think` in system prompt) is the only guard. Verify empirically that `<think>` tags never appear in relay output at startup.

**R5 — Grammar+thinking conflict (issue #20345).** If any future code path attempts grammar-constrained intent classification with thinking enabled, it will silently produce wrong JSON. This must be enforced at the architecture level, not just as a documentation note.

**R6 — Qwen3.5-9B upgrade path timing.** The FGDN_AR abort (issue #23347) was open as of May 2026. If it is fixed in a llama.cpp build that ships in llama-cpp-python 0.3.31, and if a Josiefied-Qwen3.5-9B GGUF appears, the upgrade could be attempted much sooner than the B-layer's multi-criteria timeline implies. Monitor both issues actively.

**R7 — TTS bottleneck obscures LLM speed.** The B-layer and B_serving_alternatives both note that Kokoro TTS generation dominates latency, making LLM decode speed a secondary concern. If Kokoro is replaced with a faster TTS, or if streaming TTS is implemented (first audio chunk while generation continues), the LLM decode speed becomes the bottleneck. At that point, the 50-80 tok/s for Q5_K_M or Q6_K may need to be revisited.

---

## Sources

- [Josiefied Qwen3-8B-abliterated-v1 — Hardware Requirements (llmrun.dev)](https://llmrun.dev/model/goekdeniz-guelmez-josiefied-qwen3-8b-abliterated-v1) — Q5_K_M VRAM = 6.4 GB; full 41K context adds 5.7 GB
- [Eval bug: Qwen3.5 GGUF aborts on FGDN_AR tensor-name prefix assertion (llama.cpp issue #23347)](https://github.com/ggml-org/llama.cpp/issues/23347) — hard abort confirmed, affects all Qwen3.5 GGUFs
- [Misc. bug: enable_thinking param cannot turn off thinking for qwen3.5 (llama.cpp issue #20182)](https://github.com/ggml-org/llama.cpp/issues/20182) — second failure mode for Qwen3.5 thinking control
- [Eval bug: Qwen3.5-9B tool calls in XML with thinking enabled (llama.cpp issue #20837)](https://github.com/ggml-org/llama.cpp/issues/20837) — third failure mode for Qwen3.5
- [Unsloth Qwen3.5 How to Run Locally](https://unsloth.ai/docs/models/qwen3.5) — VRAM table (4-bit = 6.5 GB, 6-bit = 9 GB, 8-bit = 13 GB); confirms no Ollama GGUF works
- [Qwen3.6-27B Abliteration Benchmarked — Nathan Sapwell](https://nathan.sapwell.net/posts/qwen36-27b-abliteration/) — abliteration quality: math -2.8 pp adjusted; TruthfulQA worst-case -10.6 pp; Heretic/Huihui best preservation
- [Heretic vs Abliterated LLMs: Refusal Rates & Benchmarks (aithinkerlab.com)](https://aithinkerlab.com/heretic-ai-abliteration-benchmarks-2026/) — Heretic KL divergence 0.16 vs manual 0.45-1.04 on Gemma-3-12B
- [Q4 vs Q5 vs Q6 vs Q8 Quantization: Real Quality Loss Numbers (runaihome.com)](https://runaihome.com/blog/quantization-q4-q5-q6-q8-quality-loss-2026/) — perplexity delta: Q5_K_M +0.0142, Q6_K +0.0044 vs FP16
- [Qwen3-8B API latency benchmarks (artificialanalysis.ai)](https://artificialanalysis.ai/models/qwen3-8b-instruct) — non-thinking TTFT 3.75s on API; output 39.4 tok/s
- [llama-cpp-python PyPI — version history](https://pypi.org/project/llama-cpp-python/) — 0.3.22 released ~May 2, 2026; 0.3.31 latest June 20, 2026
- [Reasoning Does Not Necessarily Improve Role-Playing Ability (arxiv:2502.16940)](https://arxiv.org/pdf/2502.16940) — thinking/reasoning mode does NOT improve roleplay quality
- [Grammar enforcement not applied when thinking is enabled (llama.cpp issue #20345)](https://github.com/ggml-org/llama.cpp/issues/20345) — grammar+thinking conflict confirmed open
- [Josiefied-Qwen3-8B-abliterated-v1 model card (HuggingFace)](https://huggingface.co/Goekdeniz-Guelmez/Josiefied-Qwen3-8B-abliterated-v1) — UGI 32.6; no IFEval published; abliteration technique unspecified
- [Comparative Analysis of LLM Abliteration Methods (arxiv:2512.13655)](https://arxiv.org/pdf/2512.13655) — GSM8K worst-case -18.81 pp; IFEval degradation 0-5% typical; gabliteration not in comparison set
- [Qwen3.5 VRAM requirements (llmrun.dev/family/qwen-3-5)](https://llmrun.dev/family/qwen-3-5) — 9B minimum 4.7 GB (quantized)
- [SparkRun Qwen3.5 GGUF Benchmarks over llama.cpp RPC (NVIDIA forums)](https://forums.developer.nvidia.com/t/sparkrun-qwen3-5-gguf-benchmarks-over-llama-cpp-rpc/361088) — Qwen3.5 running on llama.cpp in specialized environments (GB10 hardware, not consumer RTX)
