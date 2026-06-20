# In-context exemplar selection (kNN / MMR / diversity / coverage) to steer an LLM's STYLE and CONTENT from a library of curated lines: how many shots, ordering effects, dynamic per-input retrieval, measured quality gains; applicability to injecting snap callouts + flavor tails as exemplars

**Research date:** 2026-06-20
**System context:** Ultron 1.0 — local Windows, RTX 4070 Ti 12GB (10GB cap), Josiefied-Qwen3-8B-abliterated Q5_K_M via llama-cpp-python 0.3.22, EmbeddingGemma-300M sidecar, 1628-tail flavor library, snap callouts moving from deterministic matchers to LLM-routed prompt templates.

---

## TL;DR recommendation for Ultron 1.0

**Use 4–8 dynamically retrieved exemplars per prompt, selected by EmbeddingGemma cosine similarity (kNN) followed by MMR reranking (lambda=0.7 relevance / 0.3 diversity), injected in relevance-ascending order (most similar last, nearest to query).**

Concrete recipe:
1. At system startup, embed all 1628 flavor-tail entries + snap callout pools with EmbeddingGemma-300M into a flat numpy array (one-time cost, ~2–4s).
2. Per utterance, embed the normalized transcript → cosine similarity against the pool → take top-25 candidates.
3. MMR rerank those 25 down to k=6 final exemplars: `score(e) = 0.7·sim(e, query) − 0.3·max_sim(e, already_selected)`.
4. Sort selected 6 ascending by similarity (least similar first, most similar last = recency position).
5. Inject into the prompt as a `<examples>` block AFTER the system prompt, BEFORE the user query.
6. For snap callouts (thank-you, clutch, nice-try etc.) where you already know the category: skip retrieval, inject the 4–6 curated snap lines directly — they ARE the exemplars, and deterministic injection beats embedding overhead here.

**Expected gains:** 9–10% accuracy/quality uplift vs random selection (OptiSeq), 9.7% F1 on style-discriminative tasks (MMR vs plain similarity), consistent gains in 17/24 benchmark configurations. Ordering alone is worth 5.5–10.5pp. Latency cost: ~0.5–2ms for EmbeddingGemma retrieval on 25 candidates (the sidecar is already hot).

**Hard constraints respected:** EmbeddingGemma lives in the sidecar (anticheat-clean), retrieval uses numpy cosine (no new imports on the relay path), no LLM call needed for exemplar selection itself, llama.cpp log-probs are available for future OptiSeq-style ordering if needed.

---

## Findings

### 1. Core mechanism: what exemplars actually do

In-context learning (ICL) works by conditioning the LLM on input→output pairs that demonstrate the desired behavior without touching weights. For style/content steering, exemplars teach the model:
- **Format** (how long, what structure)
- **Register** (Ultron persona: clipped, cold, superior)
- **Content anchoring** (which tactical facts to surface, which flavor tail form to use)
- **Verbosity level** (zero vs one sentence vs flavor tail)

The 2025 Context Engineering Survey ([arxiv 2507.13334](https://arxiv.org/html/2507.13334v1)) reports code-domain gains of 9.9% BLEU-4 on summarization and 175.96% in exact match for bug-fixing from carefully selected exemplars vs random. The mechanism is well-established: exemplars bias the model's output distribution toward patterns matching the demonstrated style.

Key nuance: **exemplars work at the level of pattern, not explicit instruction.** This is especially relevant for Ultron 1.0 — injecting actual Ultron-flavored relay lines (e.g. "Reyna's lit — one left in pit.") teaches the desired cadence better than an instruction saying "use short clipped phrasing." The two combine: system prompt sets the persona; exemplars set the specific style signature.

### 2. How many shots: the shot count curve

The literature is consistent on the shape of the curve but the optimal k is task-dependent:

| Regime | Shots (k) | Notes |
|--------|-----------|-------|
| Zero-shot | 0 | Baseline; good for aligned models, bad for style lock-in |
| Few-shot standard | 1–8 | Steep gains; diversity matters most here |
| Mid-range | 8–32 | Diminishing returns begin; context cost grows |
| Many-shot | 32–1000+ | NeurIPS 2024 many-shot paper ([arxiv 2404.11018](https://arxiv.org/html/2404.11018v3)) shows continued gains for reasoning/MT up to 997 shots; MATH peaks ~125 |

For Ultron 1.0's use case (style-consistent short text generation, not multi-step reasoning):
- **k = 4–8 is the practical sweet spot.** TICL (speech ICL) found K≈4 optimal for speech with degradation beyond K=4 from noise accumulation ([arxiv 2509.13395](https://arxiv.org/html/2509.13395v1)). The DICL diversity paper found diversity benefits emerge at k≥7 ([arxiv 2505.01842](https://arxiv.org/html/2505.01842)).
- **k=6 balances diversity, context budget, and latency.** At Q5_K_M the 8B model has a ~8k-16k effective context; 6 flavor-tail exemplars cost roughly 400–600 tokens.
- Performance is non-monotonic: adding shots past k=10 for short-form generation can degrade quality (the model pattern-matches too literally to the examples, reducing variation; the "lost in the middle" effect means middle exemplars get underweighted anyway).
- The many-shot paper explicitly confirms: **distinct examples matter more than repetition.** Repeating the same example n times gives zero additional benefit.

### 3. Retrieval strategy: kNN vs random vs MMR

**kNN (pure similarity):**
- Retrieves top-k by cosine similarity between query embedding and pool embeddings.
- Consistently beats random (TICL: up to 84.7% relative WER reduction vs random baseline; gradient-matching paper: +4% over random on Qwen2.5-72B).
- Risk: if the pool has many near-duplicates (which our 1628-entry library does by agent × situation), kNN returns 6 near-identical examples → redundancy, no style diversity.

**MMR (Maximal Marginal Relevance):**
- Iterative selection: `θ_MMR(x, u, S; α) = α·sim(x, query) − (1−α)·max_{s∈S}sim(x, s_already_selected)`
- Lambda α=0.7 (relevance) / 1−α=0.3 (diversity) found optimal in [arxiv 2505.01842](https://arxiv.org/html/2505.01842) for most configurations.
- Results from DICL paper across 4 datasets and 3 models (Phi2-2.7B, Mistral-7B, LLaMA3-8B):
  - COLA/SBERT-MMR: **+9.7%** over similarity baseline
  - TREC/TFIDF-MMR on LLaMA3-8B: **+8.8%**
  - RTE/TFIDF-MMR: **+2.7%**
  - Overall: MMR beats or matches baseline in **17/24 configurations (70.8%)**
- The paper tests k ∈ {1, 3, 5, 7, 9, 10} and finds k≥7 shows the most consistent MMR benefits (smaller k doesn't have room to express diversity).

**Coverage-based (CEIL, coverage maximization):**
- Selects examples that collectively "cover" different aspects of the task space, rather than all being near the query.
- COM-BOM (EMNLP 2025) applies Bayesian optimization for exemplar subset selection; strong but computationally expensive.
- For Ultron 1.0: the 1628 entries already have a 16-situation taxonomy + loc/dmg/ability tags. Using MMR on pre-computed embeddings gives most of the coverage benefit at near-zero runtime cost vs Bayesian search.

**SKILL-kNN / skill-decomposition:**
- Decomposes the query into "skills" needed (e.g. "location callout + damage report") and retrieves exemplars covering each skill.
- Conceptually maps well to our tag system (loc/dmg/ability). Practical implementation: query tag extraction → tag-filtered pool → cosine within pool.
- No extra model needed; our existing tag taxonomy suffices.
- This is the **recommended hybrid**: filter by matching tags first, then run MMR over the filtered subset.

**Gradient matching (many-shot only):**
- +4% over random for Qwen2.5-72B at 4–128 shots; operates on small proxy model (3B/8B) gradients.
- Too expensive for per-query selection in a real-time voice system; useful for an offline "pre-select best 50 from the 1628" global warmup step.

### 4. Ordering effects: where to place exemplars

This is one of the most practically impactful findings and consistently underappreciated.

**The primacy/recency U-curve:**
- LLMs exhibit "lost in the middle" — content in the middle of a long context receives less attention than content at the start or end.
- GPT-style (causal) models: **recency bias dominates** — the last example before the query gets the most weight.
- OptiSeq (EMNLP 2025, IBM Research, [arxiv 2501.15030](https://arxiv.org/abs/2501.15030)) reorders examples using LLM log-probs at inference time:
  - **+10.5pp vs random ordering**
  - **+6.5pp vs Top-K (no reordering)**
  - **+5.5pp vs other baselines**
  - Uses the LLM's own log P(output | context ordering) as a search signal to prune the permutation space.
- Many-shot ICL paper ([arxiv 2404.11018](https://arxiv.org/html/2404.11018v3)): "performance varies significantly across different splits when reordering the same 50 examples."

**Practical recommendation for Ultron 1.0:**
- **Most similar exemplar LAST** (closest to the query, in the recency position = gets maximum attention from the 8B).
- **Sort ascending by similarity**: least relevant → most relevant → [system prompt ends] → [user query].
- This exploits recency bias without OptiSeq's LLM round-trip cost.
- Keep exemplar block short enough that the "lost in the middle" zone is the least-similar (less critical) examples.
- Never bury the snap target (the user query + task instruction) in the middle of a long exemplar list.

**Primacy for personality anchoring:**
- The system prompt should carry the Ultron persona; exemplars reinforce it.
- One trick: a single "anchor exemplar" can go first (primacy position) to set the persona register, then the 4–5 retrieved exemplars fill the rest of the block.

### 5. Dynamic per-input retrieval vs static exemplar sets

**Dynamic (per-query) retrieval:**
- Consistently outperforms static fixed exemplar sets for tasks with varied inputs.
- TICL (speech ICL): text-embedding kNN retrieval "consistently achieves the best performance across all settings" vs random.
- The key finding: **diversity of the retrieved set matters more than absolute similarity to any single example** for style learning tasks.
- Delta-kNN (2025): refines kNN with a "delta" term that accounts for influence on output quality, not just semantic similarity.

**Static (pre-curated, fixed exemplar set):**
- Acceptable when the input distribution is narrow and consistent.
- For Ultron 1.0: most relay categories are narrow (damage callout, location callout, ability callout) so a good **static exemplar set per category** (6 curated lines, carefully chosen for variety) will capture 80% of the benefit at near-zero retrieval cost.
- The snap callout categories (thank-you, nice-try, clutch, etc.) are exactly this pattern: static injection of the curated snap pool IS the exemplar block.

**Recommended hybrid for Ultron 1.0:**
- **Deterministic snap categories** (thank-you, clutch, nice-try, hello, etc.): static injection of the 4–6 curated lines from `voice_lines.py` → zero retrieval cost.
- **Agent/situation flavor tails** (agent-specific relay suffix): dynamic EmbeddingGemma kNN + MMR from the 1628-entry library, filtered by matching agent + situation tag, k=6.
- **Generic tactical relay** (location, damage, site callouts): semi-static — pre-compute best 6 exemplars per relay category at boot, use unless the specific agent/slot is unusual.

### 6. EmbeddingGemma-300M as the retrieval engine

The existing sidecar already runs EmbeddingGemma-300M for the relay-intent gate. The same embeddings can drive exemplar retrieval at effectively zero marginal cost.

**EmbeddingGemma-300M technical spec** ([arxiv 2509.20354](https://arxiv.org/html/2509.20354v2)):
- 308M params, encoder-only, built from Gemma 3
- Mean pooling → 768-dim embeddings (also supports 512/256/128 via MRL)
- MTEB(English v2): 69.67 (rank #16 overall, best under 500M)
- MTEB(Multilingual v2): 61.15 (rank #8 overall, best open under 500M)
- <15ms embedding inference for 256 tokens on EdgeTPU; expect 2–5ms on RTX 4070 Ti GPU
- **Critical config requirement**: must use `encode_query()` / `encode_document()` methods; must run in bfloat16 or float32 (not float16); requires transformers from source or recent release to get bidirectional attention. Without this, retrieval degrades to near-random ([HuggingFace discussion](https://huggingface.co/google/embeddinggemma-300m/discussions/3)).

**Retrieval cost for 1628 entries:**
- Pre-compute all embeddings at startup: ~3–6s one-time.
- Store as numpy float32 array: 1628 × 768 = 1.25M floats = ~5MB RAM.
- Per-query cosine similarity against 1628 entries: <1ms on CPU (numpy dot product), <0.2ms on GPU.
- MMR rerank top-25: negligible (25 cosine ops in a loop).
- **Total per-query exemplar selection overhead: ~1–3ms**, dominated by the single query embedding (already happening for intent classification).

### 7. Injecting snap callouts + flavor tails: the Ultron 1.0 architecture

The Ultron 1.0 design retires deterministic snap matchers in favor of LLM routing with curated prompt templates. Exemplar injection is the mechanism by which the curated content steers LLM output:

**Snap callout injection (e.g. "thank you", "nice try"):**
```
[System prompt: Ultron persona]
<examples>
[User says "good shot"] → "Lucky. Do it again."
[User says "thank you"] → "Gratitude registered. Moving on."
[Teammate compliments] → "Noted. Irrelevant to the objective."
... (4–6 lines from _THANK_YOU_TAILS pool)
</examples>
[Current: User said "<transcribed utterance>"]
→ Ultron responds:
```
The LLM sees the pattern and produces a stylistically consistent response. No embedding needed; inject the full category pool directly.

**Flavor tail injection (agent-specific relay suffix):**
```
[System prompt: Ultron persona + relay task]
<relay_context>
Agent: Jett | Situation: KILL | Tags: dmg, ability
</relay_context>
<style_examples>
"Jett hit 84 — Sova pushed mid with drone. Clean up."
"Two down by Jett — they're trading A."
"Jett clipped — vault's exposed."
... (6 MMR-retrieved entries for Jett/KILL situation)
</style_examples>
[Relay content: "<tactical content from utterance>"]
→ Relay line:
```

**Verbosity tier injection:**
The system prompt controls the verbosity tier (zero/low/high), but a few exemplars per tier calibrate the actual length better than prose instruction alone. Pre-select 2 exemplars from each tier to accompany the verbosity instruction.

### 8. Quality gains: what to realistically expect

| Technique | Gain vs baseline | Source |
|-----------|-----------------|--------|
| kNN retrieval vs random | Large (task-dependent: 8–84% rel. improvement) | TICL; gradient matching paper |
| MMR over kNN | +2.7–9.7% F1 (17/24 configs positive) | DICL (2505.01842) |
| Ordering optimization (OptiSeq) | +5.5–10.5pp accuracy | IBM Research EMNLP 2025 |
| Static per-category exemplar set vs zero-shot | ~30–40% on constrained style tasks | Few-Shot Bot; PICLe |
| Careful selection (gradient matching) vs random in many-shot regime | +2–4% at 4–128 shots | arxiv 2506.04579 |
| Dynamic vs static when input distribution is narrow | ~0–5% marginal gain | DICL; many-shot ICL paper |

**For Ultron 1.0's use case specifically:** The biggest gain is not between MMR and kNN but between EXEMPLAR-INJECTED and NO-EXEMPLAR. Getting the Ultron cadence right from exemplars vs. relying on system prompt instruction alone is likely worth 20–40% subjective quality improvement on style-sensitive relay lines. MMR vs kNN gives an additional 3–10% on top of that — meaningful but secondary.

### 9. Qwen3 8B behavior with exemplars

Qwen3-8B supports `/think` and `/no_think` mode switching per turn. Key behavior for exemplar injection:
- In **non-thinking mode** (`/no_think`): standard ICL behavior; exemplars heavily guide output.
- In **thinking mode** (`/think`): the model may "reason away" from the exemplar style if the thinking chain leads it to a different conclusion. Use thinking mode sparingly for persona/style tasks; it's primarily beneficial for multi-step reasoning.
- Chat template note: historical thinking content (`<think>...</think>`) is EXCLUDED from the context passed to subsequent turns — so exemplars should be in the user/assistant turn structure, not in thinking output.
- The model is abliterated (Josiefied variant): this removes some refusal behavior but may slightly reduce strict persona adherence. Exemplar injection compensates for this by providing strong behavioral anchors.

### 10. Anticheat and production constraints

**Anticheat constraint:** EmbeddingGemma already lives in the sidecar process. Exemplar embedding at startup is a one-time batch job (no ML imports in the relay path). The retrieval step itself is pure numpy cosine similarity — already allowed.

**llama.cpp context budget:** At Q5_K_M the 8B model has an effective context of ~8k tokens. Rough budget:
- System prompt: ~200–400 tokens
- 6 exemplars (averaging ~50 tokens each): ~300 tokens
- Relay context (tactical content + agent info): ~100–200 tokens
- Thinking output (if enabled): 500–2000 tokens (budget separately)
- **Total for generation turn: ~1000–2600 tokens prompt** — well within 8k.

**KV cache reuse:** If the system prompt + exemplar block is stable across turns (same category), llama.cpp can reuse the KV cache for those tokens, reducing prefill cost. This is a strong argument for **category-stable exemplar sets**: keep the exemplar block identical for all turns of the same relay category. Dynamic per-query exemplar selection breaks KV cache reuse; for categories where the query is always similar (damage callout, thank-you), prefer static exemplar sets.

**Latency:**
- EmbeddingGemma query embed: ~2–5ms on GPU sidecar (already happening for intent gate)
- Cosine against 1628: <1ms numpy
- MMR rerank top-25: <0.5ms
- **Net overhead: 3–6ms total** — acceptable for voice relay (baseline LLM response is 300ms+)
- For snap categories: 0ms (static injection, no embedding).

---

## Concrete techniques/params we should adopt

**A. Pre-embed the flavor library at sidecar startup:**
- Embed all 1628 TailEntry lines using EmbeddingGemma `encode_document()` in bfloat16.
- Store in `numpy.float32` shape `(1628, 768)` alongside metadata array (agent, situation, tags, text).
- Estimated RAM: ~5MB. Estimated embed time: 3–6s at boot (acceptable).

**B. Per-utterance retrieval pipeline (agent flavor tails):**
1. Query = `encode_query(f"{agent} {situation} {normalized_utterance}")` via sidecar IPC (already exists).
2. Cosine similarity: `scores = embeddings @ query_vec.T` (numpy; already in sidecar).
3. Filter to relevant agent + situation bucket first (reduces search space to ~50–100 entries).
4. MMR rerank top-25 of filtered results → select k=6.
   - `α = 0.7`, iterative greedy: `best = argmax(0.7·sim[i, query] − 0.3·max(sim[i, selected]))`
5. Sort 6 selected ascending by query similarity (ascending = least similar first, most similar last).
6. Format as `<examples>...</examples>` block.

**C. Static injection for snap categories:**
- `voice_lines.py` `SNAP_REGISTRY` entries: inject the full pool (typically 4–10 lines) directly as exemplars.
- No embedding needed; category is already deterministic.
- These ARE the exemplars; the LLM generates a variation consistent with the pool's style.

**D. Verbosity-tier exemplars:**
- Pre-select 2 representative examples per verbosity tier (zero, low, high) from the flavor library.
- Inject 2 tier-appropriate exemplars alongside the verbosity instruction.
- Keeps the tier calibration concrete rather than abstract.

**E. Ordering (always):**
- Exemplars in ascending similarity order (MMR-selected order reversed = least → most similar → [query]).
- Single anchor exemplar in primacy position (index 0) that establishes the Ultron cold/clipped voice — hardcoded, not retrieved.

**F. KV-cache-friendly grouping:**
- System prompt + static exemplars (anchor + category exemplars) = cacheable prefix.
- Dynamic exemplars (query-specific) appended after the cache prefix.
- This preserves KV cache reuse for the constant portion across turns in the same category.

**G. OptiSeq ordering (future / offline):**
- If we add an offline evaluation harness (MP3 battery), can run OptiSeq-style permutation search using llama.cpp log-probs (the `llama_get_logits` API is available).
- Use offline to determine best static ordering of exemplar slots per category.
- Expected: +5.5–10.5pp quality on the evaluation battery.

---

## Risks/caveats for our constraints

**Risk 1: EmbeddingGemma bidirectional attention gotcha.**
If the sidecar's transformers version is outdated, EmbeddingGemma silently uses causal attention, giving near-random retrieval. Symptom: retrieved exemplars feel semantically unrelated to the query. Mitigation: pin `transformers>=4.50` in `requirements.txt`; add an integration test that checks retrieve("Jett hit 80") returns entries with dmg/kill tags.

**Risk 2: KV cache invalidation from dynamic exemplars.**
Dynamic per-query exemplar selection changes the prompt for each turn, breaking llama.cpp's KV cache prefix reuse. For categories with high query volume (relay callouts), this adds prefill cost (~50ms for 300-token prompt on 8B Q5_K_M). Mitigation: use static exemplar sets for high-volume categories; reserve dynamic retrieval for rare/novel relay situations.

**Risk 3: Exemplar overfitting / literal copy.**
If exemplars are too similar to the query AND the model is in non-thinking mode, it may copy exemplar text verbatim rather than generating a variation. Observed with k=1 (single closest match). Mitigation: always use k≥4; MMR diversity ensures exemplars are not all identical; avoid using the exact target line as an exemplar.

**Risk 4: "Lost in the middle" with long exemplar blocks.**
If we inject 10+ exemplars, the middle ones get underweighted. At k=6 this is manageable (item 3 of 6 still receives meaningful attention in 8B-sized models). Hard cap: k≤8 exemplars; if the category pool has fewer than 8 entries, inject all of them.

**Risk 5: Thinking mode undermining exemplar style.**
Qwen3's thinking mode can reason away from the demonstrated style if the chain of thought concludes that style is wrong. For relay/flavor outputs: use `/no_think` (non-thinking mode). Reserve thinking only for intent classification (the undecided band of the intent gate).

**Risk 6: Anticheat — sidecar IPC latency.**
The exemplar retrieval IPC call is an additional round-trip to the sidecar (embedding + cosine). If the sidecar is under load during an LLM turn, this can add 10–30ms. Mitigation: the sidecar already handles the intent classification call; exemplar retrieval can be pipelined in the same IPC call or pre-fetched while the intent decision is being finalized.

**Risk 7: Abliteration effects on persona stability.**
The Josiefied-Qwen3 abliteration modifies weights to remove refusal behavior but may reduce persona lock-in strength. System prompt persona instructions + exemplars together should provide sufficient anchoring; but if the model drifts into generic "assistant" tone, increasing exemplar count (k=8) and placing the strongest Ultron-register example in the recency slot (last before query) is the corrective measure.

**Risk 8: Exemplar quality vs quantity tradeoff.**
From the many-shot ICL paper: **distinct examples matter more than additional examples.** Our 1628-entry library has duplicates and near-duplicates by design (multiple entries per agent × situation). MMR's diversity penalty directly addresses this — but a manual curation pass to select 50–100 "gold" exemplars per major category (using the existing golden digest infrastructure in `voice_lines_golden_digest.json`) would outperform random retrieval from the full 1628.

---

## Sources

- [Exploring the Role of Diversity in Example Selection for In-Context Learning (DICL, 2025)](https://arxiv.org/html/2505.01842) — MMR formula, lambda values, k values tested, 17/24 benchmark results
- [Many-Shot In-Context Learning (Google DeepMind, NeurIPS 2024)](https://arxiv.org/html/2404.11018v3) — shot count curves, ordering sensitivity, MATH/MT results, distinct examples insight
- [TICL: Text-Embedding KNN For Speech In-Context Learning (2025)](https://arxiv.org/html/2509.13395v1) — kNN retrieval for ICL, K≈4 optimal, 84.7% WER reduction
- [OptiSeq: Ordering Examples On-The-Fly for In-Context Learning (EMNLP 2025, IBM)](https://arxiv.org/abs/2501.15030) — +5.5–10.5pp from ordering alone, log-prob search
- [Selecting Demonstrations for Many-Shot ICL via Gradient Matching (2025)](https://arxiv.org/abs/2506.04579) — +2–4% over random, 4–128 shot experiments
- [EmbeddingGemma: Powerful and Lightweight Text Representations (Google, 2025)](https://arxiv.org/html/2509.20354v2) — architecture, MTEB scores, training methodology
- [Introducing EmbeddingGemma (Google Developers Blog)](https://developers.googleblog.com/introducing-embeddinggemma/) — 300M params, 768-dim MRL, <15ms EdgeTPU
- [EmbeddingGemma HuggingFace discussion: bidirectional attention bug](https://huggingface.co/google/embeddinggemma-300m/discussions/3) — critical config gotcha
- [A Survey of Context Engineering for Large Language Models (2025)](https://arxiv.org/html/2507.13334v1) — 1400-paper taxonomy, dynamic context assembly
- [LLM Position Bias: Primacy and Recency Effects (IntuitionLabs)](https://intuitionlabs.ai/articles/llm-position-bias-primacy-recency-effects) — U-shaped attention, model-specific effects, ordering recommendations
- [DICE: Dynamic In-Context Example Selection in LLM Agents (2025)](https://arxiv.org/abs/2507.23554) — causal framework, transferable vs non-transferable knowledge
- [PICLe: Eliciting Diverse Behaviors from Large Language Models with Persona In-Context Learning (2024)](https://arxiv.org/pdf/2405.02501) — likelihood-ratio exemplar selection for persona
- [Use Random Selection for Now: Investigation of Few-Shot Selection Strategies (2024)](https://arxiv.org/pdf/2410.10756) — baseline comparisons across selection strategies
- [Coverage-based Example Selection for In-Context Learning (2023/ICLR 2024)](https://arxiv.org/pdf/2305.14907) — coverage and diversity as selection objectives
- [Practical Long-Context LLM Inference with llama.cpp (nullmirror, 2025)](https://nullmirror.com/en/blog/2025-11-01-practical-long-context-llm-inference-with-llama.cpp/) — KV cache budgeting, 16k trivial for 7B–13B, context window guidance
- [Qwen3 Technical Report (2025)](https://arxiv.org/pdf/2505.09388) — thinking mode, /think /no_think tokens, chat template behavior
- [Serial Position Effects of Large Language Models (2024)](https://arxiv.org/abs/2406.15981) — primacy/recency empirical study
- [Few-Shot Bot: Prompt-Based Learning for Dialogue Systems (2021, foundational)](https://arxiv.org/abs/2110.08118) — curated exemplar injection for dialogue; GPT-J-6B competitive with fine-tuned via prompt
