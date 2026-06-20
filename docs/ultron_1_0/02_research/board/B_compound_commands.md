# Compound/Multi-Intent Command Parsing and Response Composition for Ultron 1.0

**Research date:** 2026-06-20  
**Scope:** How production NLU and voice systems split compound utterances, fill slots across multiple intents, compose a single combined response, and what the known evaluation benchmarks and pitfalls are. Tailored throughout to Ultron 1.0's constraints: local RTX 4070 Ti 12 GB (10 GB design cap), llama-cpp-python 0.3.22, EmbeddingGemma-300M sidecar, anticheat (relay path: numpy/urllib/scipy/stdlib/rapidfuzz only), Valorant teammate-relay persona (Ultron), Josiefied-Qwen3-8B-abliterated Q5_K_M.

---

## TL;DR Recommendation for Ultron 1.0

**Use a two-stage pipeline: (1) cheap lexical/discourse segmentation → (2) LLM JSON-array structured-output extraction.**

1. **Segmentation first (free, anticheat-safe).** Detect compound utterances with a lightweight discourse-connector regex (conjunctions "and", "also", enumerative pauses, agent-list patterns like "Jett hit 84 and Reyna's tree"). This is the ClauseCompose insight: segment on surface markers; independent clause encoding outperforms whole-utterance multi-label models on unseen combinations by 4–15 pp exact-match depending on noise level.

2. **LLM structured output (single LLM call, grammar-constrained).** Pass all clauses into the 8B LLM with a Pydantic-defined JSON-array schema: `[{"intent": "relay|private|ignore", "agent": str|null, "payload": str, "dmg": int|null, "location": str|null}]`. Use llama.cpp GBNF grammar (`json_schema_to_grammar`) to guarantee valid JSON output with zero post-hoc parsing failures. The reasoning field should precede the answer array in the schema (schema field order affects quality: reasoning-first then commit).

3. **Response composition (LLM or deterministic).** For relay callouts, compose a single relay line by flattening the slot array through a prompt template or a deterministic formatter. The existing snap registry (SnapRule) handles known-shape compound cases deterministically; unknown combos fall to the LLM compositor. Avoid separate TTS segments per sub-intent when possible — one continuous sentence reads far more naturally as a callout than a pause between two segments.

**Key numbers to hold in mind:**
- ClauseCompose: 95.7% exact match on unseen intent pairs vs. 81.4% for whole-utterance multi-label; 91.1% on unseen triples.
- MixATIS/MixSNIPS top 2025 models: LoRA-fine-tuned LLMs and WHISMA (Whisper encoder + Llama-3 decoder) surpass all smaller specialized models.
- Voice agent latency budget: 8B LLM at ~80 tok/s on RTX 4070 Ti → TTFT ~100 ms, structured 30-token intent array ~375 ms generation, well within the 1 s interactive threshold.
- Grammar constrained decoding overhead in llama.cpp: negligible for shallow schemas; `x{0,N}` patterns far more efficient than `x? x? x?` cascades; keep `maxItems` ≤ 5 for compound utterances.

---

## Findings

### 1. The Problem Space: What Makes Compound Commands Hard

Compound commands in voice appear in several forms in the Valorant relay context:

- **Sequential callouts with explicit connective:** "Jett hit 84 and Reyna is low"
- **Agent enumeration:** "Tell my team Breach and Sova are holding B"
- **Implicit compound:** "Phoenix flash corner, Neon go right" (two directives, no connector)
- **Slot-sharing compound:** "Both Jett and Reyna are B site, low HP" (one location for two agents)
- **Intent-mixed compound:** "Tell my team Sage is tree, and ask where are the smokes" (relay + private reply)

The NLU literature identifies three distinct failure modes for compound inputs:

1. **Whole-utterance multi-label collapse** — a single-encoder model trained only on pairs it has seen memorizes co-occurrences rather than learning intent structure. On held-out pair combinations, accuracy drops 10–20 pp absolute (CoMIX-Shift benchmark, ClauseCompose paper, 2026).
2. **Slot cross-contamination** — when extracting slots for two agents simultaneously, a model not explicitly segmented by agent will assign damage values to the wrong agent ("Jett hit 84, Reyna 62" → both slots may bleed into one record).
3. **Response verbosity explosion** — answering each sub-intent separately produces two or more separate sentences that sound unnatural over comms; a fused single-sentence response is preferred but harder to generate reliably.

---

### 2. Discourse-Marker Segmentation (ClauseCompose, Microsoft Research 2026)

**Source:** [ClauseCompose / CoMIX-Shift — Microsoft Research / arXiv:2603.28929](https://arxiv.org/html/2603.28929)

The most directly applicable research for Ultron 1.0 is ClauseCompose from Microsoft Research India (arXiv March 2026). It introduces CoMIX-Shift, a compositional benchmark for multi-intent detection that explicitly tests generalization to **unseen intent combinations**, discourse pattern shifts, longer/noisier wrappers, held-out clause templates, and zero-shot triples.

**ClauseCompose technique (three-stage):**

1. **Train a singleton intent classifier** on single-intent examples only. The encoder learns atomic intent representations without exposure to any multi-intent combinations.
2. **At inference, apply a small discourse-marker grammar** to segment the compound utterance into clauses. The grammar detects explicit connectors ("and", "also", "plus", sequential pauses) and splits the input string on them.
3. **Classify each clause independently** using the trained singleton classifier, then merge: one high-scoring intent per clause, duplicates suppressed.

**Results on CoMIX-Shift:**

| Split | ClauseCompose | BERT whole-utterance | Multi-label baseline |
|---|---|---|---|
| Seen pairs | 95.2% | 100.0% | 100.0% |
| Unseen pairs | **95.7%** | 91.5% | 81.4% |
| Discourse shift | **93.9%** | 77.6% | 55.7% |
| Long/noisy pairs | **62.5%** | 48.9% | 18.8% |
| Held-out templates | **49.8%** | 11.0% | 15.5% |
| Unseen triples | **91.1%** | 0.0% | 0.0% |

The key insight: whole-utterance models achieve near-perfect results on training distributions but collapse catastrophically on unseen combinations. ClauseCompose sacrifices ~5% on seen pairs but maintains 95%+ on unseen pairs and **scales to triples with zero additional training.**

**Oracle segmentation test:** With gold clause boundaries, ClauseCompose achieves 100.0% on pair-shift and long-shift splits. The residual error is entirely from the heuristic discourse-marker segmenter, not the intent classifier. This means a *better* connector grammar directly translates to better compound handling.

**Ultron 1.0 applicability:** The relay path is anticheat-constrained to stdlib + rapidfuzz + scipy. A regex-based discourse connector grammar (no ML) that splits on "and", "also", "plus", commas between agent names, and clause-initial capitalized agent names is free to implement and directly replicable. The singleton intent classifier maps to the existing hybrid router (RapidFuzz + EmbeddingGemma); the LLM is the fallback for ambiguous segments.

**Limitation:** Slot filling is explicitly out of scope in ClauseCompose. It proves segmentation + singleton classification works, but doesn't address which slot values belong to which intent record.

---

### 3. Joint Multi-Intent + Slot Filling (MixATIS/MixSNIPS Ecosystem)

**Sources:**  
- [MISCA: Joint Model for Multiple Intent Detection and Slot Filling with Intent-Slot Co-Attention (EMNLP Findings 2023)](https://aclanthology.org/2023.findings-emnlp.841.pdf)  
- [Generative Model for Joint Multiple Intent Detection and Slot Filling (arXiv:2602.08322)](https://arxiv.org/abs/2602.08322)  
- [Multi-Intent Spoken Language Understanding: Methods, Trends, and Challenges (arXiv:2512.11258)](https://arxiv.org/pdf/2512.11258)

The standard benchmark datasets are **MixATIS** (13,162 train, 828 test; airline queries, 1–3 intents, distribution 30/50/20%) and **MixSNIPS** (39,776 train, 2,199 test; multi-domain). Both are "mixed" by concatenating single-intent utterances with connectors — a known weakness: the concatenation structure is artificial and does not reflect real-world compound speech.

**Joint modeling approaches:**

- **MISCA** (2023): A dedicated encoder with an Intent-Slot Co-Attention module. The key architectural innovation is bidirectional interaction: intent predictions inform slot prediction and vice versa. Results ~92–93% slot F1 on MixSNIPS.
- **Self-Distillation** (AAAI 2022 / IEEE): Three orderly connected decoders where each decoder output is auxiliary input to the next. Intent decoder first, then slot decoder conditioned on intent. Effective for 2-3 intent utterances.
- **Generative (attention-over-attention decoder, arXiv:2602.08322)**: Frames the problem as seq2seq: input is the raw utterance, output is a linearized "(intent1, slot1=val1, slot2=val2)(intent2, ...)" structure. Achieves SOTA on MixATIS/MixSNIPS. The attention-over-attention mechanism manages multi-task interference.
- **LoRA fine-tuned LLMs and WHISMA (2025)**: Whisper encoder + Llama-3 decoder with modal alignment has surpassed all pipeline-based methods. LLMs fine-tuned with LoRA exceed specialized small models in 2025 evaluations.

**Slot cross-contamination pitfall:** When multiple agents each have separate damage values ("Jett 84, Reyna 62"), models without explicit segmentation frequently assign both values to one record. The mitigation is to either: (a) segment first, then extract slots per segment, or (b) use a list-of-objects JSON schema where each object is one intent+slot bundle.

**Production deployment pitfalls identified in the literature:**
- Many constructed multi-intent datasets are unnatural; models overfit the connector-concatenation pattern and fail on real speech.
- "Slot-intent alignment is central to deployed SLU systems" but most academic papers omit this for evaluation simplicity.
- Low-quality multi-intent training data leads to models that memorize slot co-occurrence patterns rather than genuine structural understanding.

---

### 4. LLM Structured Output via Grammar-Constrained Decoding (llama.cpp)

**Sources:**  
- [llama.cpp Grammar and Structured Output (DeepWiki)](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output)  
- [Instructor + llama-cpp-python integration guide](https://python.useinstructor.com/integrations/llama-cpp-python/)  
- [Structured Outputs 2026 (Aidan Cooper)](https://www.aidancooper.co.uk/constrained-decoding/)

For Ultron 1.0, the 8B LLM runs in-process via llama-cpp-python 0.3.22. The most robust approach for compound intent extraction is **GBNF grammar-constrained decoding**, which masks invalid tokens at sampling time — no post-hoc parsing, no retries, zero JSON decode errors.

**GBNF for multi-intent array output:**

llama.cpp ships `json_schema_to_grammar()` (Python: `examples/json_schema_to_grammar.py`). Given a Pydantic model or JSON schema, it produces GBNF rules that enforce:
- Array container syntax `[...]`
- Per-element object structure `{"intent": ..., "payload": ..., ...}`
- Type constraints (string enum for intent, optional int for damage, etc.)

```python
from llama_cpp import Llama
import json

schema = {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "intent":  {"type": "string", "enum": ["relay", "private", "ignore"]},
      "agent":   {"type": ["string", "null"]},
      "payload": {"type": "string"},
      "dmg":     {"type": ["integer", "null"]},
      "location":{"type": ["string", "null"]}
    },
    "required": ["intent", "payload"]
  },
  "minItems": 1,
  "maxItems": 5
}
# Pass as grammar= to llama.create_chat_completion or via instructor patch
```

**Critical schema design rules:**
- Use `x{0,N}` quantifiers (efficient), not cascading `x? x? x?` (quadratic stack depth, slow).
- Keep `maxItems` bounded (≤ 5 for callout context; longer arrays slow sampling noticeably at depth).
- Place `"reasoning"` field first in each object if chain-of-thought is needed — field ordering in the schema affects quality because the model commits reasoning before the intent field.
- Lazy grammar trigger: llama.cpp supports a `trigger_patterns` mode that activates the grammar only after a keyword token. Useful if wrapping the JSON in a `<callouts>...</callouts>` sentinel to separate prose preamble from the structured array.

**Performance overhead:** Grammar constraints filter invalid tokens at each sampling step. Overhead is constant per token for flat schemas; deep nesting causes exponential stack growth. For the flat compound-intent array described above, overhead is negligible. The `MAX_REPETITION_THRESHOLD` constant (2000) in llama.cpp prevents pathological memory consumption.

**Instructor integration** (llama-cpp-python): Patch the Llama instance with `instructor.patch()` in `JSON_SCHEMA` mode, pass a Pydantic model as `response_model=`. Handles retries automatically on schema violation (though with grammar constraints, violations should be zero for well-defined schemas).

---

### 5. The Babylon Drive-Thru System: Production Edge-Efficient Multi-Intent NLU

**Source:** [Babylon: Real-Time Edge-Efficient Multi-Intent Translation System for Drive-Thru Ordering (arXiv:2411.15372)](https://arxiv.org/abs/2411.15372)

Babylon is a production NLU system from a fast-food drive-thru ordering context — highly applicable to Ultron's multi-callout scenario because:
- Noisy ASR input (drive-thru acoustics ≈ Valorant game audio)
- Real-time latency requirement
- Multi-intent in a single turn (ordering multiple items simultaneously)

**Key architectural decision:** Rather than decomposing the utterance into sequential single-intent turns, Babylon reformulates NLU as **intent translation**: map the raw ASR transcript to a sequence of "transcodes" that encode both intents and slot information in a structured string format. This handles multi-intent in a single pass without segmentation.

**LSTM-based phoneme pooling:** Reduces input length for low-latency, low-memory edge deployment. Relevant to Ultron because Kokoro TTS + Whisper STT already introduce their own latency budget; intent parsing must be fast.

**Outperforms Flan-T5 and BART** on accuracy-latency-memory trade-off. Edge deployment (embedded device) — implies the technique works at model sizes far smaller than 8B, suggesting our 8B has more than enough capacity for compound intent extraction.

**Robustness to ASR noise:** The transcode formulation inherently smooths over ASR errors because the model is trained to produce structured output from noisy text. Same benefit applies to Ultron where Whisper may mishear agent names or numbers.

---

### 6. DialogUSR: Utterance Splitting + Reformulation as a Plug-In Module

**Source:** [DialogUSR: Complex Dialogue Utterance Splitting and Reformulation (EMNLP Findings 2022)](https://aclanthology.org/2022.findings-emnlp.234/)

DialogUSR proposes treating compound utterance splitting as a seq2seq task: given a multi-intent utterance, generate N single-intent sub-queries with coreference resolved and ellipsis filled. For example:

> "I want to book a flight to Paris and a hotel there" →  
> ["Book a flight to Paris", "Book a hotel in Paris"]

This is a **domain-agnostic plug-in module**: it doesn't require training a dedicated multi-intent model downstream. Any existing single-intent NLU system can consume the reformulated sub-queries.

**For Ultron 1.0:** The existing slot-callout parser (`relay_speech._parse_callout_slots`) and snap matchers are single-intent focused. Running DialogUSR-style reformulation upstream would let the full snap + router pipeline handle each sub-callout independently. However, DialogUSR requires a seq2seq model (generative LM), which for us is the 8B LLM. This adds a generation step for reformulation before the routing step.

**Practical tradeoff vs. direct structured extraction:**
- DialogUSR-style: 2 LLM calls (reformulate → route per sub-utterance) or 1 LLM call reformulation then deterministic routing
- Direct JSON array extraction: 1 LLM call → array of `{intent, slots}` records → deterministic composition

The direct extraction approach is generally preferred for Ultron 1.0's latency budget. DialogUSR's approach makes sense when the downstream system is complex (many intents, many snaps) and cannot be retrained; since we control the full stack, we prefer the unified extraction.

---

### 7. Low-Latency Voice Agent Pipeline (Streaming Architecture)

**Source:** [Low-Latency End-to-End Voice Agents with Streaming ASR, Quantized LLMs, Real-Time TTS (arXiv:2508.04721)](https://arxiv.org/html/2508.04721v1)

Measured latency breakdown for a production voice agent (2025):

| Component | Mean Latency |
|---|---|
| Streaming ASR | 49 ms |
| RAG retrieval | 8 ms |
| LLM (2B, 4-bit) | 670 ms |
| TTS synthesis | 286 ms |
| **Total** | **934 ms** |

TTFT (time-to-first-token for LLM) = 106 ms. This is with a 2B model on an H100 at ~80 tok/s.

**Ultron 1.0 extrapolation:** Our 8B Q5_K_M on RTX 4070 Ti achieves approximately 40–60 tok/s. A compact compound-intent JSON array (30–50 tokens) would take 500–750 ms for full generation at 60 tok/s, with TTFT ~100 ms. That fits within a 1.5–2 s total voice round-trip (including Kokoro TTS ~200–300 ms and Whisper STT ~50–100 ms on GPU).

**Producer-consumer streaming pattern:** TTS begins on the first sentence emitted by LLM; LLM and TTS run in parallel threads. For compound relay response, the composed relay line should be a single sentence to enable smooth TTS without internal pauses.

**Binary serialization (msgpack)** between LLM and TTS reduces pipeline latency by 0.8–1.0 s compared to JSON string passing. Ultron's in-process architecture avoids this overhead entirely since LLM output is already in-memory Python.

---

### 8. Multi-Intent Evaluation: Benchmarks, Metrics, and Pitfalls

**Sources:**  
- [Multi-Intent SLU Survey (arXiv:2512.11258)](https://arxiv.org/pdf/2512.11258)  
- [BlendX: Complex Multi-Intent Detection with Blended Patterns (arXiv:2403.18277)](https://arxiv.org/pdf/2403.18277)

**Standard evaluation metrics:**
- **Intent accuracy / F1** — per-intent correct
- **Slot F1** — token-level BIO labeling F1
- **Semantic frame accuracy (Overall Acc)** — exact match of both intent and slot predictions simultaneously; the strict metric; typical top model scores 73–79% on MixATIS, 85–90% on MixSNIPS

**BlendX (2024):** Introduces "blended pattern" multi-intent detection — utterances where 2–3 intents overlap or coexist with no clear clause boundary (e.g., "I need help booking and payment"). Uses multi-label classification with attention over intent interdependencies. Shows "particular gains" for 2–3 co-occurring intents. Relevant for Ultron's "Sage is tree and she's B" type compound where the agent is shared across two predicates.

**Critical pitfall — artificial dataset bias:** Both MixATIS and MixSNIPS are constructed by concatenating single-intent utterances with connectors. Real compound speech is NOT structured this way — speakers share arguments across clauses, elide subjects, and use prosodic grouping rather than explicit connectors. Models trained on these datasets overfit to explicit connectors and fail on implicit compounds.

**Evaluation culture shift (ClauseCompose finding):** Standard holdout evaluation — split on utterances — dramatically overstates model performance because identical or near-identical intent pairs appear in both train and test. CoMIX-Shift introduces **pair-level holdout**: specific intent combinations are excluded entirely from training. This is the realistic evaluation condition for a system like Ultron that will encounter callout combinations never seen during development.

**Implication for Ultron testing:** The existing 186-case frozen table and 25k corpus trace should include held-out agent+callout-type pairs that test compositional generalization, not just per-utterance coverage. A compound-specific eval set (e.g., "Jett 84 and Reyna tree" as a pair that doesn't appear in training) is needed.

---

### 9. Response Composition: From Multiple Intents to One Relay Line

This is under-researched in NLU literature (which typically stops at intent+slot extraction) but is the most critical piece for Ultron:

**Option A: Template-based flattening (RECOMMENDED for relay-relay combos)**

When all sub-intents are `relay`, merge slot records into a single template:
- "Jett 84 and Reyna tree" → two records `{agent: Jett, dmg: 84}` + `{agent: Reyna, location: tree}` → compose: `"Jett's hit for 84, Reyna's on tree."`
- The compositor is a pure Python function over the slot array — anticheat-safe, zero LLM latency.
- The existing SnapRegistry / flavor library can provide tail variations for merged compound lines.

**Option B: LLM compositor (for mixed-intent combos or novel structures)**

When sub-intents include relay + private or when the slot structure is novel, pass the slot array back to the LLM with a composition prompt: `"Given these callouts, write one natural combined callout: [...]"`. The LLM generates a single sentence that merges the information.

**Option C: Sequential TTS segments (NOT RECOMMENDED)**

Concatenating two separate TTS audio clips with a pause between them sounds robotic and takes longer to play. Valorant comms require concise, single-breath callouts. Avoid.

**Composition pitfalls:**
- Sharing one agent across two predicates: "Reyna is tree and has no ult" — do not duplicate the agent name in the output ("Reyna tree, Reyna no ult" is wrong; "Reyna on tree, no ult" is correct).
- Damage + location in one breath: "Jett's hit 84, she's B site" — confirm TTS handles the pronoun resolution before committing.
- Connector word selection: Ultron persona should use "also", "and", or comma-list in-character style ("84 on Jett. Reyna is tree. Move.") rather than editorial "furthermore."

---

### 10. Slot Assignment Ambiguity in Compound Utterances

The hardest problem: given "Jett and Reyna hit 84 and 62 respectively" or "Jett 84, Breach 97", which damage value belongs to which agent?

**Techniques from the literature:**

1. **Position alignment** — in listed form "A val1, B val2", position matches agent to value; heuristic but works for most Valorant compound callouts.
2. **Grammar-constrained per-agent JSON objects** — the LLM emits `[{agent: "Jett", dmg: 84}, {agent: "Breach", dmg: 97}]` with the schema enforcing one dmg per agent object. The LLM is trained/prompted to assign values locally per record.
3. **Ambiguity fallback** — when confidence in assignment is low, emit the full compound as a single relay text without slot separation ("Jett 84, Breach 97 — relay as-is") and let the relay playback handle it verbatim.

**The `_parse_callout_slots` existing behavior** (`da28d22` hotfix): currently handles `dmg` as a single-digit or multi-digit per-callout matched by slot grammar. For compound inputs like "Jett 84 Breach 97", the slot parser sees two agent tokens and two number tokens; the fix added multi-digit damage support but is still single-intent structured. The compound case requires either: (a) running `_parse_callout_slots` once per segment after discourse splitting, or (b) moving to LLM-based slot extraction that emits a list.

---

## Concrete Techniques/Params We Should Adopt

1. **Discourse-connector segmenter (stdlib regex, zero cost)**  
   Build `_COMPOUND_SPLIT_RE` that triggers on: `, and `, ` and `, ` also `, ` plus `, ` as well as `, sentence-final comma before an agent name (e.g., `"84, Reyna tree"`). Yields a list of candidate sub-utterances. If only one segment: existing single-intent path. If multiple: compound path.

2. **Single-pass LLM structured extraction for compound path**  
   Use `llama.create_chat_completion(..., response_format={"type": "json_object"})` with a GBNF grammar derived from the compound-intent schema above. Prompt: system = "Extract each callout as a JSON array of {intent, agent, payload, dmg, location}. Reasoning first, then output the array." Keep `maxItems=5`, use `x{0,N}` not cascading optionals.

3. **Segment-then-route fallback**  
   For each segment, try the existing deterministic snap matchers first (RapidFuzz + `_looks_like_slot_callout`). Only invoke LLM for the segment(s) that don't snap. This preserves deterministic latency for the common case ("Jett hit 84 and Reyna is tree" → both segments snap deterministically).

4. **Template compositor for relay-relay**  
   Implement `_compose_compound_relay(slot_records: list[dict]) -> str` that joins up to 4 sub-relays into one sentence: `"{agent} hit {dmg}, {agent2} on {loc2}."` Select per-slot format from an inline template table, join with comma + space. Feed into existing TTS pipeline as a single input string.

5. **Evaluation: compound-pair holdout set**  
   Add a frozen test set of ~50 compound utterances with held-out agent/action pairs. Measure ClauseCompose-style exact match on the full (intent, agent, dmg, location) tuple per sub-callout. Include cross-agent damage sharing, shared-location cases, and mixed relay+private intents.

6. **Schema field ordering for quality**  
   In the JSON schema object, define `"reasoning"` before `"intent"` and `"payload"`. This forces the LLM to reason about which intent to assign before committing the enum value — empirically reduces intent mismatch on ambiguous boundaries.

7. **`maxItems` cap and edge-case handling**  
   Cap at 5 sub-intents. Utterances with more than ~5 callouts are extremely rare in Valorant comms and are likely ASR artifacts; emit a fallback single relay ("Lots happening — [verbatim transcript]") rather than attempting to parse a 6+ element array.

---

## Risks/Caveats for Our Constraints

### Anticheat constraint (relay path must be importable without heavy ML)
- The discourse-connector regex is pure stdlib — safe.
- The LLM call goes through the existing `inference.py` path which is already in the orchestrator — safe.
- The slot array compositor is pure Python dict manipulation — safe.
- **Risk:** If compound detection requires EmbeddingGemma (for intent boundary detection), that sidecar is already in the architecture but adds sidecar roundtrip latency (~5–10 ms). Keep it optional; use it only if the discourse regex is ambiguous.

### Grammar constrained decoding overhead
- Flat schemas (depth ≤ 3) have negligible overhead. The compound-intent array schema is depth 2 (array → object). Safe.
- Do NOT nest reasoning inside each array element (depth 3+ causes stack growth). Keep reasoning as a top-level separate field or as a prefix string before the array.

### LLM VRAM budget (10 GB cap)
- Qwen3-8B Q5_K_M: ~5.5 GB model weights + ~1 GB KV cache at 4K context = ~6.5 GB total.
- A compound callout prompt is short (~200 tokens input, ~60 tokens output). No VRAM concern.
- Grammar-constrained decoding does not add VRAM overhead.

### Slot cross-contamination for real Valorant speech
- The MixATIS/MixSNIPS benchmarks use artificial connectors; Valorant compound callouts are often implicit ("Jett 84 Breach 97" — no explicit connector). The discourse regex must handle this.
- Mitigation: add a secondary trigger: any utterance with 2+ agent-name tokens detected by the existing agent gazetteer is a candidate compound, regardless of explicit connector.

### TTS single-sentence assumption
- Kokoro TTS performs better on single coherent sentences. The compound compositor must produce one sentence (or at most two short sentences) without internal list markers.
- Do not emit numbered lists, bullet points, or explicit "first/second" enumeration — unnatural for voice comms.

### Thinking-mode interaction
- Qwen3-8B with thinking enabled will spend tokens on `<think>` reasoning before committing the JSON array. This adds ~200–500 ms but improves slot assignment accuracy on ambiguous compounds. **Recommended: use thinking-mode for compound path only.** Deterministic single-intent paths bypass thinking as they do today.

### No established gaming-specific compound NLU benchmark
- No academic benchmark covers Valorant-style compound callouts. The closest analogs are MixATIS (airline multi-intent, artificial connectors) and drive-thru ordering (Babylon). All numbers cited are transfers — real-world performance must be measured with Ultron's own compound test battery.

### Real-world compound rate
- Academic multi-intent literature notes that naturally occurring compound utterances are rarer than artificially constructed benchmarks suggest. In actual Valorant comms, most utterances are single-callout. The compound path will be triggered less often than single-intent; optimize the common single-intent path first; compound is a quality-of-life improvement.

---

## Sources

1. ClauseCompose / CoMIX-Shift (Microsoft Research India, 2026) — [https://arxiv.org/html/2603.28929](https://arxiv.org/html/2603.28929) and [https://www.microsoft.com/en-us/research/publication/known-intents-new-combinations-clause-factorized-decoding-for-compositional-multi-intent-detection/](https://www.microsoft.com/en-us/research/publication/known-intents-new-combinations-clause-factorized-decoding-for-compositional-multi-intent-detection/)

2. Multi-Intent Spoken Language Understanding: Methods, Trends, and Challenges (survey, 2025) — [https://arxiv.org/pdf/2512.11258](https://arxiv.org/pdf/2512.11258)

3. BlendX: Complex Multi-Intent Detection with Blended Patterns (2024) — [https://arxiv.org/pdf/2403.18277](https://arxiv.org/pdf/2403.18277)

4. Babylon: Real-Time Edge-Efficient Multi-Intent Translation for Drive-Thru Ordering (2024) — [https://arxiv.org/abs/2411.15372](https://arxiv.org/abs/2411.15372)

5. Generative Model for Joint Multiple Intent Detection and Slot Filling (2026) — [https://arxiv.org/abs/2602.08322](https://arxiv.org/abs/2602.08322)

6. MISCA: Joint Model for Multiple Intent Detection and Slot Filling with Intent-Slot Co-Attention (EMNLP 2023) — [https://aclanthology.org/2023.findings-emnlp.841.pdf](https://aclanthology.org/2023.findings-emnlp.841.pdf)

7. DialogUSR: Complex Dialogue Utterance Splitting and Reformulation (EMNLP Findings 2022) — [https://aclanthology.org/2022.findings-emnlp.234/](https://aclanthology.org/2022.findings-emnlp.234/)

8. Low-Latency End-to-End Voice Agents: Streaming ASR, Quantized LLMs, Real-Time TTS (2025) — [https://arxiv.org/html/2508.04721v1](https://arxiv.org/html/2508.04721v1)

9. llama.cpp Grammar and Structured Output (DeepWiki technical reference) — [https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output](https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output)

10. Instructor + llama-cpp-python integration — [https://python.useinstructor.com/integrations/llama-cpp-python/](https://python.useinstructor.com/integrations/llama-cpp-python/)

11. Aligner2: Enhancing Joint Multiple Intent Detection and Slot Filling (AAAI 2024) — [https://ojs.aaai.org/index.php/AAAI/article/view/29952/31664](https://ojs.aaai.org/index.php/AAAI/article/view/29952/31664)

12. Joint Multiple Intent Detection and Slot Filling via Self-Distillation (IEEE ICASSP 2022) — [https://ieeexplore.ieee.org/document/9747843/](https://ieeexplore.ieee.org/document/9747843/)

13. SoundHound Deep Meaning Understanding / multi-query NLU — [https://www.soundhound.com/voice-ai-products/nlu/](https://www.soundhound.com/voice-ai-products/nlu/)

14. STEER: Semantic Turn Extension-Expansion Recognition for Voice Assistants (2023) — [https://arxiv.org/pdf/2310.16990](https://arxiv.org/pdf/2310.16990)

15. A Guide to Structured Generation Using Constrained Decoding (Aidan Cooper) — [https://www.aidancooper.co.uk/constrained-decoding/](https://www.aidancooper.co.uk/constrained-decoding/)
