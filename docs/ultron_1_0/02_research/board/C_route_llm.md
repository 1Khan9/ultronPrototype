# Adversarial Verdict: Route-All-Through-LLM for Ultron 1.0 Relay

**Layer:** C — Adversarial verification  
**Cluster:** Route-all-through-LLM (fact fidelity, exemplar selection, router/generator arch, me-vs-team generation)  
**Adversarial agent:** Claude Sonnet 4.6  
**Date:** 2026-06-20  
**Goal:** Refute or qualify whether sending every relay through the Josiefied-Qwen3-8B degrades callout accuracy or blows the latency budget compared to the current deterministic snaps. Determine when deterministic is still better.

---

## Claims Examined

From the four Layer-B documents:

1. **B_fact_fidelity_grounding (FF):** Two-stage extract-then-relay with grammar-constrained JSON in Stage 1 eliminates agent-name hallucination; thinking mode OFF for relay; post-hoc RapidFuzz guard catches residual drift; the whole design is latency-safe (~0.5–1s Stage 1 overhead).

2. **B_exemplar_selection (ES):** 4–8 MMR-retrieved exemplars steer the 8B to Ultron cadence with 9–10% quality uplift vs random; static injection for snap categories; EmbeddingGemma retrieval adds only 3–6ms overhead; KV cache reuse valid for category-stable sets.

3. **B_router_generator_arch (RG):** Three-tier cascade (rules → EmbeddingGemma → 8B) with single structured JSON call (intent+verbosity+think+response fields) is the right architecture; TTFT stays inside the 1115ms mouth-to-ear budget; two-call only for thinking-mode routing.

4. **B_me_vs_team_generation (MG):** Full system-prompt swap per destination (RELAY vs PRIVATE vs IGNORE) is mandatory; hard brevity (≤12 words) for relay, soft for private reply; /no_think always for relay.

---

## Verdict Per Claim

### Claim FF-1: Grammar-constrained Stage 1 eliminates agent-name hallucination

**QUALIFIED — with a sharp practical caveat confirmed by production bug reports.**

The theory is correct: llama.cpp GBNF with `enum` fields cannot emit a token sequence outside the listed values, which physically prevents agent-name fabrication.

However, three real production bugs undercut the "eliminates" framing:

- **Silent grammar failure on schema complexity.** llama.cpp issue #21228 (early 2026): schemas using `$ref/$defs` silently exceed `MAX_REPETITION_THRESHOLD` (2000 rules), causing the grammar to degrade with no error raised. The structured output guarantee disappears silently, and downstream code receives unconstrained output. Layer-B correctly mentions this but characterizes it as "keep enum lists under ~100 entries" — the risk is that a combined agent+location+action schema with nested optional fields is closer to the limit than acknowledged.

- **Invalid JSON with mixed quote escaping under large payloads.** llama.cpp issue #20359 (2026): tool-call arguments produce mixed single/double quote escaping when the system prompt exceeds ~5000 chars + multiple schemas. Our relay prompt (system prompt + exemplars + kit facts + schema) approaches this range.

- **Array parameter serialization breaks with curly-brace content.** llama.cpp issue #21384: string values containing `{` or `}` inside arrays serialize incorrectly. Agent names themselves are safe, but flavor-tail or kit-fact injection that includes braces (e.g., "Sova kit: {Recon Bolt}") could corrupt the JSON.

**Correction:** Stage 1 grammar constraint REDUCES hallucination sharply for simple flat schemas, but does NOT eliminate it under production conditions. The post-hoc guard (Section 6 of FF) is not optional — it is load-bearing. The document's own "~25% improvement" figure (from DeepWiki) implies a non-trivial residual failure rate (~75% of baseline → grammar still hallucinates some of the time on unconstrained fields).

Evidence: "Grammar-constrained generation... 37.5% higher latency at batch size 512" (arxiv 2502.14969 on constrained decoding overhead); llama.cpp GBNF documented performance gotchas per README; llama.cpp issue tracker active in 2025–2026 with the bugs above.

---

### Claim FF-2: Two-stage design latency overhead is ~0.5–1s and acceptable

**QUALIFIED — probably correct for isolated relay turns; not safe as a blanket claim.**

The Layer-B estimate: Stage 1 generates 20–40 tokens at ~40 tok/s → 0.3–0.7s. Prefill cost (~100–200ms) adds to that. Total per-relay overhead vs single-call: ~0.5–1s. The document calls this "acceptable for most relay scenarios."

Counter-evidence from production data:

- A two-stage whisper-large-v3 + Qwen3-8B pipeline measured p90 TTFT of ~800ms on a single H100 GPU (arxiv PredGen, 2506.15556). On an RTX 4070 Ti (roughly 1/4 the compute), p90 TTFT for Stage 1 alone approaches 1–2s — before Stage 2 starts.

- Industry consensus: LLM TTFT must be under 375ms (Twilio) to 500ms (median production target) for voice. Adding a full second of Stage 1 overhead breaks this target on every relay turn where both stages are needed.

- The document's own Table (B_router_generator_arch) confirms two-call cost pushes total LLM latency to "~775ms-1175ms" — "straining the <750ms TTFT target."

**Correction:** Two-stage extract-then-relay is latency-safe ONLY if Stage 1 is made ultra-cheap: use greedy decoding (temperature=0), a minimal flat schema (agent+damage+count only), and skip Stage 1 entirely for utterances where the deterministic slot parser (existing `relay_speech._parse_callout_slots`) already extracted all slots. The current deterministic slot parser is already doing this work — Stage 1 is only needed for novel/complex utterances that escape the parser.

---

### Claim FF-3: Thinking mode OFF for relay prevents hallucination amplification

**CONFIRMED — and the risk is worse than the document states.**

The B_fact_fidelity_grounding document cites Vectara benchmarks: DeepSeek R1 (reasoning) at 14.3% vs DeepSeek V3 (non-reasoning) at 3.9% hallucination rate on grounded summarization — a 4x increase. This is directionally correct and cross-validated.

Additional evidence strengthening the CONFIRMED verdict:

- arxiv 2505.16894 ("Shadows in the Attention"): hallucinations rise **monotonically** as context length grows; relevant context produces "high-confidence self-consistent hallucinations" (the model commits to wrong facts with high certainty); irrelevant context induces topic drift. Both effects worsen with longer thinking chains.

- arxiv 2506.17088 (Chain-of-Thought Obscures Hallucination Cues): reasoning model outputs harder to detect as hallucinated because the confident reasoning chain masks uncertainty cues. This is especially dangerous for relay — a hallucinated "Sova took 84" in a thinking chain will be emitted confidently and pass casual review.

- **Critical confirmed llama.cpp bug:** llama.cpp issue #20345 (August 2025): when `response_format` (JSON schema grammar) is used with `enable_thinking: true`, grammar enforcement is **completely inactive** and the model generates unconstrained output. A separate issue #13189: persistent `<think>` tags appear in Qwen3-32B output despite `enable_thinking: False` and `--reasoning-format none`. Issue #20182: `enable_thinking` param cannot turn off thinking for Qwen3.5 variants.

**This last point is a severe risk not surfaced in B_fact_fidelity_grounding:** the grammar constraint and the thinking mode toggle interact at the llama.cpp implementation level, and the interaction has documented bugs. If thinking leaks into a JSON schema call, the grammar goes inactive and the model generates unconstrained hallucinating text. The document recommends both grammar constraints AND thinking=False but does not flag that using them together in the same call is itself a failure mode in current llama.cpp.

**Corrective action:** Enforce thinking=OFF not just by `enable_thinking=False` kwarg but also by (1) `/no_think` token in the user message, AND (2) asserting `<think>` does not appear in raw output before relaying. Belt-and-suspenders is mandatory, not optional, given the live bugs.

---

### Claim ES-1: 4–8 MMR exemplars give 9–10% quality uplift; overhead is 3–6ms

**QUALIFIED on the uplift number; CONFIRMED on the overhead.**

The 9–10% figure conflates two different results: the DICL paper's MMR-vs-similarity gain (2.7–9.7%) and OptiSeq ordering gains (5.5–10.5pp). These are not additive — they come from different axes. Combining them would require simultaneous MMR reranking AND OptiSeq ordering, which the document correctly defers as a "future/offline" step. The 9–10% is a ceiling, not an expected gain from implementing MMR alone.

More critically: arxiv 2505.16894 shows that adding more context (including exemplars) raises hallucination monotonically. The exemplar block itself is a hallucination risk surface. For relay callouts where the prompt already carries slot data + kit facts + system persona, injecting 6 additional exemplars (~300 tokens) pushes deeper into the context zone where representation drift accelerates. The quality gain from exemplars must be weighed against this risk.

On the 3–6ms overhead: CONFIRMED. EmbeddingGemma cosine against 1628 entries in numpy is sub-millisecond; the bottleneck is the IPC call for the query embedding, already happening for intent classification. The overhead estimate is credible.

**Correction:** The quality gain from exemplar injection on relay tasks is likely 5–15% subjective improvement in Ultron persona cadence — meaningful but below the document's implied 9–10% on accuracy. The more important gain is persona lock-in (preventing the model from sounding like a generic assistant), which is harder to quantify but real. Do not add exemplars beyond k=6 for relay: diminishing returns and growing hallucination surface.

---

### Claim ES-2: KV cache reuse valid for category-stable static exemplar sets

**CONFIRMED — but limited by system-prompt swap constraint from B_me_vs_team.**

If the system prompt + exemplars are identical across consecutive relay turns, llama.cpp can reuse the KV cache prefix, cutting prefill from ~200ms to near-zero for matching turns. This is a genuine latency win.

The conflict: B_me_vs_team_generation correctly requires a full system-prompt swap per destination (RELAY vs PRIVATE). Each swap invalidates the KV cache. For relay-heavy sessions (most Valorant rounds), the relay system prompt + relay exemplars are stable → high cache reuse. For mixed sessions (relay + private reply questions), cache thrashes. Acceptable given the asymmetry: relay is latency-critical, private reply is not.

---

### Claim RG-1: Single structured JSON call (intent+verbosity+think+response) stays inside 1115ms budget

**REFUTED — for the proposed 4-field schema with `response` as a JSON string field.**

The document estimates TTFT overhead from the JSON header tokens at ~375ms (15 tokens at 40 tok/s on RTX 4070 Ti), pushing total LLM TTFT from ~300ms to ~675ms — "within acceptable range but tight."

Three underweighted problems:

**A. The `response` field as JSON string is problematic.** JSON strings require escaping of double quotes, backslashes, and newlines. llama.cpp issue #20359 documents invalid JSON with mixed quote escaping appearing in large-payload tool-call arguments. Ultron's persona frequently uses sarcastic quoted phrases and cold commands like `"Gratitude registered."` — quotes inside the response field cause grammar instability. The document acknowledges this risk but classifies it as easily fixed by "post-process unescaping" — in practice, the escaping bug produces invalid JSON that `json.loads` will fail to parse, requiring fallback logic on every relay.

**B. Thinking mode + JSON grammar = mutually exclusive in current llama.cpp.** Confirmed by issue #20345. If the single-call schema includes `"think": true` as a field value (meaning the model decided thinking is needed), the grammar enforcement immediately goes inactive for the rest of the response. The workaround requires a two-call pattern for thinking turns — which the document recommends but frames as "rare." For Ultron 1.0 where private replies to the user include tactical analysis ("should I buy Odin this round?"), thinking turns may be 20–30% of non-relay traffic.

**C. Intent `"ignore"` still consumes full header overhead.** Every utterance the system cannot classify before the 8B call generates 15 JSON header tokens (~375ms) before producing an empty response. For "ignore" turns that clear the embedding gate threshold (ambiguous zone), this is pure waste. At 40 tok/s local, this is significant.

**Correction:** Decouple the intent/routing header from the response generation. Use a compact 2-field intent-only call (`{"intent":"relay","think":false}` — ~10 tokens, ~250ms at local speed) as a lightweight pre-filter before committing to the full response call. This is Pattern B's "mini two-call" variant described in B_router_generator_arch but not recommended — it should be recommended for the ignore/ambiguous band specifically.

---

### Claim RG-2: Rules → EmbeddingGemma → 8B cascade intercepts 80–90% of turns before the 8B

**CONFIRMED — consistent with existing Ultron 0.x measurements.**

The existing `_relay_intent.py` architecture at 99.4% matcher accuracy (from memory/codebase) and the 25k-corpus audit showing 482/482 tests green after F1–F5 fixes validates that the cascade can handle the vast majority of turns without the 8B. The Layer-B figure of "80–90% of turns intercepted" is conservative relative to what the current system already achieves for relay vs not-relay classification. CONFIRMED for classification accuracy.

Caveat: "80–90% intercepted before 8B" is a design target, not a measured figure for the new three-class (relay/private/ignore) routing problem. Private reply classification is a NEW class that the existing sidecar is not trained on. The embedding gate's performance on private-reply vs relay disambiguation is unknown and needs empirical measurement before claiming the cascade handles 80–90% of three-class traffic.

---

### Claim MG-1: Hard brevity (≤12 words) for relay, enforced by stop tokens and max_tokens=60

**CONFIRMED — and the asymmetry finding from "Concise Agent is Less Expert" is correctly applied.**

The arXiv:2601.10809 paper confirms: forcing brevity on extraction/reformulation tasks does NOT degrade accuracy when the content is already a constrained fact (position, count). For Ultron relay (reformulating a slot-parsed callout into spoken form), no expertise is sacrificed by a 12-word hard cap. The max_tokens=60 + stop tokens approach is correct. CONFIRMED.

One addition: the document recommends stripping leading "Hey"/"Okay"/"Alright" filler via post-process regex. This is necessary and validated by voice UX research (every filler syllable at PTT open adds dead air before the callout content).

---

### Claim MG-2: System-prompt swap per destination is mandatory; conditional blocks are insufficient for 8B Q5

**CONFIRMED — the codebase itself is the evidence.**

The memory context records a live regression (circa 2026-06-18) where the relay path inherited the base "You are Kenning" system prompt — the exact failure mode this claim warns against. The existing `_RELAY_REPHRASE_SYSTEM` was discovered as a fix. CONFIRMED from production experience.

---

## The Core Adversarial Finding: Route-All-Through-LLM Is NOT the Right Framing

The Layer-B documents collectively frame the goal as "route ALL responses through the 8B LLM, with deterministic snaps retired into ROUTERS." This framing is subtly wrong in a way that matters.

**What the evidence actually supports:**

Sending every utterance's RESPONSE through the 8B is not universally better than deterministic snaps. The evidence supports a more precise claim: routing every utterance through a DECISION layer (to pick the right template/snap/generation path) is valuable, but generation itself should remain deterministic for the high-frequency, low-ambiguity cases.

Concretely:

- **Exact-match snaps (thank-you, clutch, nice-try, hello):** The existing curated pools (`_THANK_YOU_TAILS`, `_CLUTCH_LINES`, etc.) produce higher per-utterance accuracy than the 8B would — they are 100% persona-accurate, 0ms latency, 0 hallucination risk. Routing these through the 8B adds variance with no benefit. Layer-B's own recommendation for snap categories ("static injection of the 4–6 curated lines") is correct but the framing of "8B generates a variation" adds unnecessary failure modes. The deterministic random-sample from the curated pool IS the better path.

- **Slot-parseable relay callouts (Jett hit 84, two on B, Sova spotted mid):** The existing `_parse_callout_slots` + deterministic template instantiation already achieves near-100% accuracy. Adding an 8B rephrase step adds 500ms–1s latency plus hallucination risk for a marginal stylistic improvement. This is the wrong trade — the existing system is already winning here.

- **Ambiguous or complex utterances (asked how much Sova ult costs, should we eco, tactical analysis):** THIS is where the 8B is genuinely needed and adds value the deterministic system cannot provide.

**The correct framing for Ultron 1.0:** Expand the LLM's role at the EDGES (ambiguous intent, complex private replies, novel relay phrasings that don't match the slot parser) while preserving deterministic snap and template paths for the HIGH-FREQUENCY CENTER. The 8B is a fallback and enrichment layer, not a mandatory pass for every utterance.

---

## Corrected Recommendation for Ultron 1.0

1. **Preserve and strengthen deterministic paths for:** exact-match snaps (thank-you, clutch, nice-try, clutch, hello), slot-parseable relay callouts (existing `_parse_callout_slots` success path). These should NOT route through the 8B for generation — only through the 8B if the slot parser fails and the embedding gate cannot classify.

2. **Use the 8B for:** novel relay phrasings the slot parser cannot parse, private reply generation, intent disambiguation in the undecided embedding band, complex tactical questions. This is a minority of total utterances (~10–20%).

3. **Two-stage extract-then-relay:** Apply ONLY to utterances that escape the deterministic slot parser AND are classified as relay by the embedding gate. Not every relay. Stage 1 must use minimal flat schema (agent, damage, count — no nested `$ref`, no optional arrays with brace content). Schema size budget: under 100 enum entries total.

4. **Grammar constraints in Stage 1:** Use GBNF/JSON schema BUT assert `len(schema_rules) < 1500` at startup to stay under `MAX_REPETITION_THRESHOLD`. Add an integration test that checks the grammar does not fail silently: call `llm("Extract from: 'Jett hit 84'", grammar=relay_grammar)` at boot and assert the output is valid JSON with `agent="Jett"`.

5. **Thinking mode OFF is mandatory for relay — but enforce defensively:** Add three independent guards: (a) `/no_think` in user message, (b) `enable_thinking=False` kwarg (or equivalent), (c) assert `"<think>" not in raw_output` before TTS. This is necessary given confirmed llama.cpp bug #20345 where grammar + enable_thinking conflict.

6. **Single-call intent+response schema:** Accept this design only with the `response` field as a JSON string AND a mandatory post-parse fallback for JSON decode failure. Do NOT rely on the grammar preventing quote-escaping failures — confirmed bug #20359 shows they occur with complex payloads.

7. **KV cache targeting:** Use per-intent system prompt swap (relay / private / ignore), with the relay system prompt + relay exemplars as the cacheable prefix. Accept that private reply calls invalidate the cache; this is latency-acceptable since private replies are not time-critical.

8. **Exemplar count hard cap:** k=6 maximum. Do not inject more exemplars in an attempt to improve quality — context-induced hallucination risk rises monotonically with context length (arxiv 2505.16894).

9. **Post-hoc RapidFuzz guard is NOT optional:** It is the primary backstop for Stage 2 drift. Target failure-to-guard rate of <1% (not "~5% cases" as the document states — 5% hallucination rate on relay callouts would be unacceptable in a live game).

---

## Residual Risks

**Risk A (HIGH): Stage 1 latency on slow turns.** If the slot parser misses and the 8B must do Stage 1, total relay latency adds ~0.5–1s on an RTX 4070 Ti. Under GPU contention (the model is mid-KV-cache-eviction from a large previous context), this can spike to 1.5–2s. No mitigation in the current design. Mitigation: measure p95 Stage 1 latency empirically under realistic session load (not just isolated calls) before committing to two-stage as the default path.

**Risk B (HIGH): Grammar silent failure.** llama.cpp #21228 and #19051 document cases where grammar fails silently — the structured output guarantee disappears with no exception. The codebase has no defense against this. Mitigation: add startup integration test (call grammar-constrained LLM once, assert output is valid JSON) and a runtime `try: json.loads(output)` fallback that triggers the deterministic template path.

**Risk C (HIGH): Thinking mode / grammar interaction bug.** Confirmed llama.cpp #20345: `response_format` + `enable_thinking: true` disables grammar enforcement. For Ultron 1.0's single-call design that emits `"think": true` in the header, the moment the model decides thinking is needed, the remainder of the JSON is unconstrained. Mitigation: separate thinking calls from constrained-output calls entirely — they cannot coexist in the same call safely.

**Risk D (MEDIUM): Context-induced hallucination growth.** Each additional token in the prompt (exemplars, kit facts, history) increases hallucination risk monotonically (arxiv 2505.16894). The total prompt for a relay call with 6 exemplars + kit facts + history can reach 1200–1500 tokens. This is a non-zero hallucination risk zone even for simple slot-relay tasks. Mitigation: keep prompts short; use static exemplars (no dynamic retrieval) for high-frequency relay categories to stay within the cache prefix and minimize prompt length variance.

**Risk E (MEDIUM): Abliterated fine-tune instruction-following degradation on structured output.** The Qwen3-8B Q5_K_M base achieves F1=0.933 on tool selection. The Josiefied abliterated variant's structured output compliance is untested against that baseline. Abliteration modifies weights; its effect on grammar-constrained sampling compliance is unknown. Mitigation: run the frozen relay test battery (existing 482 tests) against the abliterated model with grammar constraints enabled to measure compliance delta.

**Risk F (MEDIUM): Private reply "not relay" ambiguity.** The three-class routing (relay/private/ignore) introduces a new edge case the current binary system does not have: utterances like "should I tell them to push?" are private advice, not a relay request, but contain relay-positive language. The embedding gate is calibrated on relay vs not-relay; the private/ignore boundary is untrained. Rate of misroute to private-reply is unknown. Mitigation: expand the corpus with PRIVATE_REPLY positive and IGNORE negative exemplars before production deployment; measure confusion matrix on all three classes.

**Risk G (LOW): JSON `response` field quote-escaping.** Confirmed llama.cpp bug #20359: mixed quote corruption with large payloads. For Ultron's relay outputs (typically under 20 words, well-formed), this may be unlikely in practice — the bug triggers at ~5000 char system prompts + 20 tools. Our relay prompts are shorter. Monitor but do not block on this.

---

## Sources

### Counter-evidence discovered by this adversarial pass

- [Grammar enforcement not applied when thinking is enabled — llama.cpp issue #20345](https://github.com/ggml-org/llama.cpp/issues/20345) — CRITICAL: confirmed that `response_format` + `enable_thinking: true` disables grammar in llama.cpp; grammar and thinking mode cannot coexist in one call.

- [Persistent `<think>` tags despite `enable_thinking: False` — llama.cpp issue #13189](https://github.com/ggml-org/llama.cpp/issues/13189) — thinking mode toggle unreliable in llama.cpp for Qwen3 family; affects relay path safety.

- [enable_thinking param cannot turn off thinking for Qwen3.5 — llama.cpp issue #20182](https://github.com/ggml-org/llama.cpp/issues/20182) — independent confirmation of thinking-toggle unreliability.

- [json_schema with $ref/$defs silently fails grammar rule count — llama.cpp issue #21228](https://github.com/ggml-org/llama.cpp/issues/21228) — silent grammar failure on complex schemas; structured output guarantee disappears silently.

- [Streamed tool call arguments invalid JSON with mixed quotes — llama.cpp issue #20359](https://github.com/ggml-org/llama.cpp/issues/20359) — quote-escaping corruption in large-payload JSON schema outputs.

- [llama-server fails open when JSON schema grammar parsing fails — llama.cpp issue #19051](https://github.com/ggml-org/llama.cpp/issues/19051) — grammar fail-open documented; no exception raised on silent grammar failure.

- [Shadows in the Attention: Contextual Perturbation and Representation Drift (arxiv 2505.16894)](https://arxiv.org/abs/2505.16894v1) — hallucination rises monotonically with context length and exemplar count; self-consistent hallucinations under relevant context.

- [Lost in Space: Optimizing Tokens for Grammar-Constrained Decoding (arxiv 2502.14969)](https://arxiv.org/html/2502.14969v1) — grammar constrained decoding shows up to 37.5% higher latency at scale; performance gotchas documented.

- [PredGen: Accelerated Inference for Real-Time Speech Interaction (arxiv 2506.15556)](https://arxiv.org/pdf/2506.15556) — two-stage whisper + Qwen3-8B pipeline p90 TTFT ~800ms on H100; RTX 4070 Ti will be significantly higher.

- [LLM Hallucination Statistics 2026](https://sqmagazine.co.uk/llm-hallucination-statistics/) — 31.4% hallucination rate in real-world LLM interactions; 40–80% on open-ended generation; open-source models worse than frontier.

- [A Concise Agent is Less Expert (arxiv 2601.10809)](https://arxiv.org/abs/2601.10809) — confirmed asymmetry: brevity degrades expertise on complex tasks but NOT on constrained reformulation tasks (relay callout is reformulation, not expertise).

- [Trust the Server, Not the LLM: A Deterministic Approach (dev.to)](https://dev.to/nodefiend/trust-the-server-not-the-llm-a-deterministic-approach-to-llm-accuracy-20ag) — templates showed 43% lower precision vs GPT-4o in open-ended QA, but deterministic template "skeleton-then-fill" avoids semantic hallucination for closed-domain substitution tasks — directly analogous to relay slot instantiation.

- [Core Latency in AI Voice Agents (Twilio, 2025)](https://www.twilio.com/en-us/blog/developers/best-practices/guide-core-latency-ai-voice-agents) — industry standard: LLM TTFT target 375ms (max 750ms) for mouth-to-ear <1115ms; confirms two-call serial latency is straining the budget.

- [Grammar-Constrained Generation (TianPan.co, 2026)](https://tianpan.co/blog/2026-04-16-grammar-constrained-generation-output-reliability) — production deployment patterns; grammar sample time documented at up to 56.21 ms/token in pathological cases (17.79 tok/s vs unconstrained).

### Sources from Layer-B docs relied upon and confirmed

- [XGrammar (arxiv 2411.15100)](https://arxiv.org/abs/2411.15100) — grammar overhead reduction; not applicable to llama.cpp 0.3.22 without engineering work (CONFIRMED by adversarial pass — XGrammar targets vLLM, not llama.cpp).

- [DICL Diversity paper (arxiv 2505.01842)](https://arxiv.org/html/2505.01842) — MMR vs similarity gains (2.7–9.7%); CONFIRMED directionally but note the gains are not additive with OptiSeq ordering.

- [Vectara hallucination benchmarks (DeepSeek R1 4x rate vs V3)](https://suprmind.ai/hub/ai-hallucination-rates-and-benchmarks/) — CONFIRMED; strengthened by independent arxiv 2505.16894 evidence.

- [Qwen3 Technical Report (arxiv 2505.09388)](https://arxiv.org/pdf/2505.09388) — thinking mode dual-architecture; budget_tokens mechanism. CONFIRMED; qualified by llama.cpp implementation bugs above.
