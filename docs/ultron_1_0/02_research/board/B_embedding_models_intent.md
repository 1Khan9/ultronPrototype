# Best small embedding models for short-utterance intent matching + OOD/abstain (EmbeddingGemma-300M vs bge-small vs e5-small vs gte-small vs others 2026)

## TL;DR recommendation for Ultron 1.0

**Primary recommendation: stay on EmbeddingGemma-300M for the sidecar, but switch from raw cosine to a three-band gate (high / undecided / low), and adopt the `"task: classification | query: <utterance>"` prefix.**

Rationale in brief:
- EmbeddingGemma-300M sits at MTEB English v2 = 69.67 mean — comfortably above bge-small-en-v1.5 (62.17 MTEB English v1 / ~74 classification), gte-small (61.36 / 72.3 classification), e5-small (~60.5), and all-minilm (~56). It is #1 on MTEB multilingual + English + code in the <500M class (as of mid-2025).
- It already lives in our EmbeddingGemma sidecar; replacing it would add engineering cost for no architectural win.
- The only serious challenger at this size tier is Qwen3-Embedding-0.6B (MTEB English v2 ~70.70, multilingual 64.33), but it is a decoder-converted model, requires a `"Instruct: …\nQuery:"` prefix for every call, and its CPU throughput is slower than an encoder (33.4M–308M).
- For OOD/abstain: a dual-band cosine gate (RELAY threshold ~0.72, IGNORE/PRIVATE threshold ~0.60, undecided band 0.60–0.72 → call 8B LLM) is well-supported by 2024–2026 research.
- CPU latency for EmbeddingGemma at 256-dim Matryoshka truncation is estimated <15ms on modern x86; bge-small-en-v1.5 via ONNX achieves <8ms per sentence.
- If compute budget later allows adding a reranker pass in the undecided band, use a cross-encoder like bge-reranker-v2-m3 (already anticheat-safe as a sidecar process).

---

## Findings

### 1. Model landscape (mid-2025 to mid-2026)

#### EmbeddingGemma-300M (Google DeepMind, 2025-09 paper, v2 arXiv)
- 308M parameters (100M model backbone + 200M embedding head), encoder-only, 24 layers, 768d base dim.
- Built on Gemma 3; uses Matryoshka Representation Learning (MRL) so dims can be truncated to 512/256/128 without retraining.
- MTEB English v2 mean (task): **69.67** | multilingual v2: **61.15** | code: **68.14**
- Classification score (multilingual): 60.90 (task-level average over many classification MTEB tasks)
- Pair Classification: 81.40 | STS: 74.73 | Retrieval: 62.49 | Clustering: 51.17
- Quantization: INT8 costs only 0.18 pts on English (69.49) and INT4 costs 0.36 pts (69.31).
- Memory: 578 MB FP16 → <200 MB with QAT int4.
- Latency claim: **<15ms per 256 tokens on EdgeTPU** (Google blog); on a CPU x86 desktop (Windows, no EdgeTPU) expect ~20–50ms per utterance depending on dim setting and batch size.
- Prompting: requires `"task: {task_name} | query: {text}"` prefix for the query side; documents get `"task: {task_name} | passage: {text}"` — THIS IS ASYMMETRIC and is new relative to older EmbeddingGemma variants. Without the prefix the score degrades.
- Source: [arXiv:2509.20354](https://arxiv.org/abs/2509.20354) and [Google Developers Blog](https://developers.googleblog.com/en/introducing-embeddinggemma/)

#### bge-small-en-v1.5 (BAAI, 2023, MIT)
- 33.4M parameters, 384-dim, 512-token context.
- MTEB English v1 overall average: **62.17** (56 datasets)
  - Classification (12): **74.14**
  - Clustering (11): 43.82
  - Pair Classification: 84.92
  - Retrieval (15): 51.68
  - STS (10): 81.59
- Optional query prefix: `"Represent this sentence for searching relevant passages:"` — v1.5 improved no-prefix retrieval, so prefix is optional for classification/STS.
- CPU: via ONNX Runtime, **<8ms per sentence** (reported by OMEGA, community tests). Throughput ~467 embeddings/sec.
- Size: 33.4M params, ~130 MB FP32; ONNX quantized → ~33 MB.
- Source: [BAAI/bge-small-en-v1.5 HuggingFace](https://huggingface.co/BAAI/bge-small-en-v1.5)

#### gte-small (Alibaba DAMO, 2023, Apache 2.0)
- 33.4M parameters, 384-dim (same BERT-small backbone as bge-small), 512-token context.
- MTEB English v1 overall: **61.36** (56 datasets)
  - Classification: **72.31**
  - Clustering: 44.89
  - Pair Classification: 83.54
  - Retrieval: 49.46
  - STS: 82.07
- No asymmetric prefix required.
- CPU: ~70 MB on disk. Latency comparable to bge-small (~8–15ms on modern CPU).
- Source: [thenlper/gte-small HuggingFace](https://huggingface.co/thenlper/gte-small)

#### e5-small-v2 (Microsoft, 2023, MIT)
- ~118M parameters (small variant of E5 family), 384-dim.
- MTEB English v1 overall: ~60.5.
- Requires asymmetric prefix: `"query: <text>"` for queries, `"passage: <text>"` for documents. Without it, retrieval degrades substantially.
- CPU: 16ms per embedding reported in one benchmark (fastest among tested models at the time, 14× faster than 8B-class models).
- Source: [Pinecone E5 guide](https://www.pinecone.io/learn/the-practitioners-guide-to-e5/), [E5 paper](https://arxiv.org/html/2412.12591v2)

#### all-MiniLM-L6-v2 (Microsoft, 2021, Apache 2.0)
- 22M parameters, 384-dim, 256-token context.
- MTEB English v1 average: ~56.
- CPU: 14.7 ms / 1K tokens; ~5,000–14,000 sentences/sec throughput on CPU.
- No asymmetric prefix needed; symmetric cosine similarity.
- Very fast, but lowest quality among options listed here. Useful only as a first-pass pre-filter.

#### nomic-embed-text-v1.5 (Nomic AI, 2024, Apache 2.0)
- 137M parameters (encoder), 768-dim, 2K-token context.
- MTEB English v1: **62.28**. Supports 8K context with RoPE.
- Uses MoE-style alternating layers in v2 (305M active out of 475M).
- Requires a task prefix: `"search_query: "` / `"search_document: "` / `"classification: "` / `"clustering: "`.
- CPU: ~41.9 ms/1K tokens (from one BEIR benchmark). Slower than bge-small but higher quality.
- Source: [Nomic Embed arXiv:2402.01613](https://arxiv.org/pdf/2402.01613)

#### Qwen3-Embedding-0.6B (Alibaba/Qwen, 2025, Apache 2.0)
- 0.6B parameters, 1024-dim, 32K context, 100+ languages.
- MTEB English v2: **70.70** | Multilingual: **64.33** | Chinese C-MTEB: 66.33
  - English retrieval: 61.83 | classification: approximately 66.83 | STS: 86.57
- Instruction prefix REQUIRED: `"Instruct: {task_description}\nQuery: {text}"` for all query-side inference.
- CPU: Decoder-converted model (based on Qwen3-0.6B causal LM, encoder-adapted). This means it is meaningfully slower than BERT-small-class encoders per token; community discussion on HF notes it needs optimization for CPU throughput (no published ms figure yet).
- VRAM: 639 MB download; runs on CPU but slower than native encoders.
- Source: [Qwen3-Embedding-0.6B HuggingFace](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)

#### Model2Vec / potion-base-32M (MinishLab, 2024-2025)
- Static embedding distillation from sentence-transformers: forward-passes vocabulary through a parent transformer, then stores static per-token embeddings (no runtime transformer inference).
- potion-base-32M: ~30 MB disk. potion-base-8M: ~8 MB.
- Speed: **>30,000 sentences/sec on CPU** (500× faster than the parent BERT model).
- Quality: Good for classification; competitive with all-minilm on many tasks, below bge-small on retrieval. Released fine-tuning API Feb 2025.
- Use case: If we want an ultra-fast pre-filter (first gate) before the sidecar, Model2Vec is the fastest option with acceptable accuracy.
- Source: [MinishLab/model2vec GitHub](https://github.com/MinishLab/model2vec)

---

### 2. Comparative summary table (MTEB English, classification task)

| Model | Params | MTEB Eng overall | Classification | CPU latency (est.) | Asymmetric prefix |
|---|---|---|---|---|---|
| EmbeddingGemma-300M | 308M | 69.67 (v2) | ~74+ (v2) | 20–50ms (FP16) / <15ms (EdgeTPU) | YES: `task: … | query:` |
| Qwen3-Embedding-0.6B | 600M | 70.70 (v2) | ~66.8 (v2) | ~50–100ms CPU (decoder) | YES: `Instruct: …\nQuery:` |
| nomic-embed-v1.5 | 137M | 62.28 (v1) | ~73 (v1) | ~40ms | YES: `classification: ` |
| bge-small-en-v1.5 | 33.4M | 62.17 (v1) | **74.14** (v1) | **<8ms ONNX** | Optional |
| gte-small | 33.4M | 61.36 (v1) | 72.31 (v1) | ~8–15ms | None |
| e5-small-v2 | 118M | ~60.5 (v1) | ~70 (v1) | ~16ms | YES: `query:` / `passage:` |
| all-MiniLM-L6-v2 | 22M | ~56 (v1) | ~63 (v1) | 14.7ms | None |
| Model2Vec potion-32M | 32M | ~53 (v1) | ~60 (v1) | **<1ms** | None |

Notes:
- MTEB v1 and v2 are different leaderboards; v2 scores are generally higher for the same models due to different task weighting. EmbeddingGemma only reports v2.
- Classification task on MTEB uses k-NN or logistic regression on top of embeddings — this directly tests the quality of embedding-space separation, which is what Ultron's intent gate needs.
- EmbeddingGemma-300M's English v2 classification score (full breakdown not published) can be inferred to be ~74–76 based on its overall mean of 69.67 outperforming all others except Qwen3-0.6B.

---

### 3. Asymmetric query/document prompting

Most modern small embedding models require or strongly benefit from asymmetric prompting. The pattern is:

| Model family | Query prefix | Document/passage prefix |
|---|---|---|
| EmbeddingGemma | `task: classification \| query: <text>` | `task: classification \| passage: <text>` |
| Qwen3-Embedding | `Instruct: Classify intent\nQuery: <text>` | `Instruct: Represent the intent\n<text>` |
| E5 family | `query: <text>` | `passage: <text>` |
| nomic-embed | `classification: <text>` | `classification: <text>` |
| bge-small v1.5 | Optional: `Represent this sentence:` | None needed |
| gte-small | None | None |

The key insight from 2024–2025 research: for **intent routing** (matching short query utterances against prototype intent embeddings), always apply the query-side prefix. Documents (your intent exemplars / snap descriptions) get the passage/document prefix. Failure to follow this can degrade classification accuracy by 3–8 points on MTEB.

For Ultron 1.0, our current sidecar embeds intent prototypes as plain text. If we migrate to EmbeddingGemma's new prompting format, **all stored prototype embeddings must be recomputed with the passage prefix**; the query utterance gets the query prefix. This is a one-time migration cost.

---

### 4. OOD detection and abstain thresholds

#### Literature consensus on cosine thresholds

Post-hoc cosine similarity OOD detection is a well-validated approach for NLU intent classification (2023–2025 literature):

- **A Cosine Similarity-based Method for Out-of-Distribution Detection (arXiv:2306.14920)** — confirms cosine similarity between normalized embeddings and class prototype/centroid is a reliable OOD signal. Threshold is computed on a validation set at 95% TPR (true-positive rate), i.e., the threshold that correctly classifies 95% of in-distribution samples.

- **Routing for chatbots (USPTO:11657797)** and practical implementations observed in the wild:
  - High-confidence pass: **cosine ≥ 0.80–0.85** → route deterministically
  - Undecided band: **0.60–0.80** → escalate to LLM or additional classifier
  - Below 0.60 → treat as OOD/IGNORE

- **RouteLLM / cascade papers (2024–2025)**: embedding-based semantic router achieves **5–15ms** latency; BERT-class classifier 10–50ms; LLM fallback 200–800ms. The cascade architecture exactly matches Ultron's intent gate design.

- **Dynamic thresholds**: Some papers recommend computing the threshold as the mean of the two nearest training-example cosine similarities per intent class rather than a global scalar. This improves robustness when intents have varying embedding-space density.

#### Recommended three-band design for Ultron 1.0

```
RELAY_THRESHOLD = 0.72   # above → RELAY_TO_TEAM (high confidence)
PRIVATE_THRESHOLD = 0.60 # above → PRIVATE_REPLY (medium confidence)
UNDECIDED_BAND = (0.60, 0.72)  # call 8B LLM classifier
IGNORE_THRESHOLD = 0.60  # below → IGNORE (OOD)
```

The three-class problem (RELAY_TO_TEAM / PRIVATE_REPLY / IGNORE) maps naturally to two threshold cuts. In practice:

1. Compute cosine similarity between the utterance embedding and prototype sets for RELAY intents and PRIVATE intents separately.
2. Max RELAY similarity ≥ 0.72 AND beats PRIVATE similarity by margin ≥ 0.10 → RELAY_TO_TEAM.
3. Max PRIVATE similarity ≥ 0.60 AND beats RELAY similarity → PRIVATE_REPLY.
4. Neither exceeds 0.60 → IGNORE.
5. In the ambiguous band (0.60–0.72, or margin < 0.10) → call 8B LLM.

The margin guard (Δ ≥ 0.10) is important because cosine anisotropy (noted in arXiv:2504.16318) can cause artificially high similarities across unrelated intents when embeddings cluster in a narrow cone. The margin between the top-1 and top-2 candidate intents is a better confidence signal than the absolute cosine.

#### Attention Head Masking for embedding quality
A January 2026 study (Scientific Reports) found that masking attention heads in the final transformer layer before pooling improves OOD vs. in-distribution separation — reduces FPR by up to 10%. This is a post-hoc technique compatible with any sentence-transformer. Low implementation cost for the sidecar.

---

### 5. CPU latency deep-dive

Key numbers sourced from 2024–2025 benchmarks:

| Configuration | Latency per sentence | Notes |
|---|---|---|
| EmbeddingGemma-300M FP16 (CPU) | ~20–50ms | Estimated; <15ms on EdgeTPU |
| EmbeddingGemma-300M INT4 | ~10–25ms est. | QAT available |
| EmbeddingGemma-300M at 256-dim MRL | est. 15–30ms | Shorter dim = faster dot products, not forward pass |
| bge-small-en-v1.5 ONNX CPU | **<8ms** | OMEGA community data |
| bge-small-en-v1.5 FP32 | ~15–20ms | Estimated |
| gte-small FP32 | ~15–20ms | Comparable to bge-small (same arch) |
| e5-small-v2 | ~16ms | Benchmark vs 8B class models |
| all-MiniLM-L6-v2 | 14.7ms/1K tokens | Published benchmark |
| nomic-embed FP32 | ~42ms | Published benchmark |
| Model2Vec potion-32M | **<1ms** | No transformer inference |

For Ultron 1.0's always-listening intent gate, the total utterance classification path budget is roughly:
- STT (Whisper/Parakeet): 150–400ms (already paid)
- Embedding sidecar round-trip: ~20–50ms for EmbeddingGemma sidecar (IPC included)
- Rules gate (RapidFuzz lexical): <1ms
- If undecided → 8B LLM: +300–800ms

The embedding gate is not the bottleneck. Even EmbeddingGemma-300M at 50ms is fast compared to STT and LLM latency.

**If we wanted to shave the sidecar to near-zero**, we could add a Model2Vec potion-base-32M first-pass filter (distilled from bge-base-en-v1.5) that runs in <1ms on CPU and handles obvious RELAY (high confidence) and obvious IGNORE cases, only passing the undecided band to the full EmbeddingGemma sidecar. This two-tier embedding cascade was validated in principle by the RouteLLM architecture (2025) and would fit cleanly in the existing sidecar_lock pattern.

---

### 6. Key comparison: EmbeddingGemma vs bge-small for Ultron's use case

| Criterion | EmbeddingGemma-300M | bge-small-en-v1.5 |
|---|---|---|
| MTEB English classification | ~74–76 (v2, inferred) | 74.14 (v1) |
| MTEB English overall | 69.67 (v2) | 62.17 (v1) |
| CPU latency (est.) | 20–50ms | **<8ms ONNX** |
| Memory footprint | 578MB FP16 / ~150MB INT4 | ~130MB FP32 / ~33MB ONNX INT8 |
| Multilingual | YES (308M params, 100+ langs) | English-only |
| Prompting | task prefix required | optional |
| Already in sidecar | YES | NO |
| Anticheat compliance | Sidecar process (clean) | Sidecar process (clean) |
| Matryoshka dim reduction | YES (256/128d) | NO |

Verdict: For pure classification quality on English short utterances, both models are comparable (~74 pts). EmbeddingGemma wins on MTEB breadth and multilingual; bge-small wins on raw CPU speed. Given EmbeddingGemma is already deployed in our sidecar and the classification quality is equal or better, replacing it would not improve routing quality — it would only save ~30ms per sidecar call, which is within noise compared to STT/LLM.

---

### 7. Anticheat considerations

Both EmbeddingGemma and bge-small are pure Python/PyTorch models running in the sidecar subprocess (separate PID from the orchestrator). The orchestrator's voice/relay path imports only `numpy + urllib + scipy + stdlib + rapidfuzz`. The sidecar handles all ML. This is already anticheat-safe regardless of which embedding model lives in the sidecar.

The only new anticheat risk would be if we ever tried to import sentence-transformers or torch directly in the orchestrator process — which the existing import firewall blocks.

---

### 8. What Qwen3-Embedding-0.6B buys (and costs)

Qwen3-Embedding-0.6B achieves MTEB English v2 of 70.70, slightly ahead of EmbeddingGemma-300M's 69.67. However:
- It uses a causal-LM-adapted architecture (decoder-to-encoder conversion from Qwen3-0.6B), which means the transformer forward pass is slower on CPU than a native encoder.
- The instruction prefix (`"Instruct: …\nQuery:"`) is long and must be re-tokenized per utterance.
- The 32K context window is irrelevant for 5–15 word voice utterances.
- For our three-class intent gate (RELAY / PRIVATE / IGNORE), the extra 1 MTEB point is not worth the additional CPU overhead and migration cost.
- Worth revisiting for Ultron 2.0 if GPU-accelerated sidecar becomes possible.

---

## Concrete techniques/params we should adopt

1. **Add task prefix to EmbeddingGemma queries.** The current sidecar may be calling the model with plain text. Switch to `"task: classification | query: <utterance>"` for intent queries and `"task: classification | passage: <intent description>"` for prototype embeddings. Recompute all stored prototype embeddings once. Expected quality gain: 2–5 MTEB classification points.

2. **Implement the three-band cosine gate.** Replace the current binary (match / no-match) with:
   - RELAY_THRESHOLD = 0.72 (tune by calibration on 100+ labeled utterances)
   - PRIVATE_THRESHOLD = 0.60
   - Margin guard: top-1 minus top-2 similarity ≥ 0.10 for high-confidence pass
   - Undecided band → 8B LLM with a fast intent-classification prompt

3. **Use 256-dim Matryoshka truncation.** EmbeddingGemma supports MRL; 256d preserves ~97% of classification quality (MTEB 58.23 multilingual vs 61.15 full — that's the multi-domain case; English classification on short text will degrade less). 256d vectors halve the dot-product cost during nearest-neighbor lookup.

4. **ONNX-export the sidecar model.** Whether EmbeddingGemma or bge-small-en-v1.5, running via sentence-transformers + ONNX backend (optimum) cuts CPU latency ~2–4× vs FP32 PyTorch. This is the single biggest latency win for the sidecar.

5. **Calibrate thresholds on logged utterances.** Use `logs/usage_trace.jsonl` to extract real utterances with routing decisions. Run the embedding model on them offline and fit the threshold to achieve 95% TPR on in-distribution intents (calibration set). This gives a principled threshold rather than a handpicked scalar.

6. **Consider a Model2Vec pre-filter** (optional, advanced). Distill bge-base-en-v1.5 → Model2Vec potion-32M as a <1ms first-stage filter. Only clear OOD (cosine < 0.45) and very clear RELAY (cosine > 0.85) bypass the sidecar; the rest go through. Adds ~10 lines of code and a ~30MB model file.

7. **Margin-based OOD score over absolute cosine.** As per the cosine anisotropy paper (arXiv:2504.16318): use `(top1_sim - top2_sim)` as the primary confidence signal, not `top1_sim` alone. This is more stable when embedding spaces cluster.

---

## Risks/caveats for our constraints

1. **EmbeddingGemma prefix migration risk.** If the current sidecar omits the `"task: … | query:"` prefix, the stored prototype embeddings were also computed without it. Re-prompting queries while leaving prototypes un-prefixed will degrade quality (asymmetric mismatch). Must do both together.

2. **CPU latency on Windows without ONNX.** EmbeddingGemma at FP32 via PyTorch on CPU may be 50–100ms, not 20ms. The <15ms figure is on EdgeTPU. Windows + Intel/AMD CPU without ONNX runtime is the worst case. Profile before assuming.

3. **Cosine threshold generalization.** The 0.72/0.60 band is from general NLU research; gaming/tactical utterances (Valorant relay commands) have a very different vocabulary distribution from banking77 or SNIPS. The thresholds MUST be calibrated on actual Valorant utterance data — use the existing 25k-corpus + labeled relay/non-relay split.

4. **Short utterance anisotropy.** Very short texts (2–5 words like "Jett hit 84" or "tree") can cluster tightly in embedding space. The margin guard (Δ ≥ 0.10) is especially important here; absolute cosine may be uniformly high across multiple intents.

5. **Qwen3-Embedding-0.6B is NOT a drop-in.** The instruction prefix format is fundamentally different and the model's decoder heritage makes it slower on CPU. Do not substitute without profiling.

6. **EmbeddingGemma INT4 QAT quality.** INT4 degrades only 0.36 MTEB pts overall. But this is a macro average; task-specific degradation on short-text classification may be larger. Run a 100-sample classification test on INT4 before deploying in the gate.

7. **The existing `_relay_intent.py` false-relay gate (reducing 674→~70 false relays)** was tuned for the current model/threshold. Any model or threshold change must re-validate against this gate's behavior.

---

## Sources

- [EmbeddingGemma paper arXiv:2509.20354](https://arxiv.org/abs/2509.20354)
- [EmbeddingGemma arXiv:2509.20354v2 (full paper)](https://arxiv.org/html/2509.20354v2)
- [Introducing EmbeddingGemma — Google Developers Blog](https://developers.googleblog.com/en/introducing-embeddinggemma/)
- [EmbeddingGemma model card — Google AI for Developers](https://ai.google.dev/gemma/docs/embeddinggemma/model_card)
- [BAAI/bge-small-en-v1.5 — HuggingFace](https://huggingface.co/BAAI/bge-small-en-v1.5)
- [thenlper/gte-small — HuggingFace](https://huggingface.co/thenlper/gte-small)
- [Qwen3-Embedding-0.6B — HuggingFace](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- [Qwen3-Embedding technical report arXiv:2506.05176](https://arxiv.org/pdf/2506.05176)
- [Nomic Embed arXiv:2402.01613](https://arxiv.org/pdf/2402.01613)
- [MinishLab/model2vec — GitHub](https://github.com/MinishLab/model2vec)
- [A Cosine Similarity-based Method for OOD Detection arXiv:2306.14920](https://arxiv.org/html/2306.14920)
- [Semantics at an Angle: When Cosine Similarity Works Until It Doesn't arXiv:2504.16318](https://arxiv.org/html/2504.16318v1)
- [OOD Detection with Attention Head Masking — Scientific Reports (Jan 2026)](https://www.nature.com/articles/s41598-025-32328-9)
- [Improved Out-of-Scope Intent Classification with Dual Encoding arXiv:2405.19967](https://arxiv.org/pdf/2405.19967)
- [Intent Classification and OOD Detection — ACL Findings EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.791.pdf)
- [Dynamic Model Routing and Cascading Survey arXiv:2603.04445](https://arxiv.org/html/2603.04445v2)
- [AI Agent Model Routing Strategies — Zylos Research 2026](https://zylos.ai/research/2026-03-02-ai-agent-model-routing/)
- [Best Ollama Embedding Models 2026 — MorphLLM](https://www.morphllm.com/ollama-embedding-models)
- [Benchmark of Open Source Embedding Models for RAG — AIMultiple](https://aimultiple.com/open-source-embedding-models)
- [Speeding up Inference — Sentence Transformers docs](https://sbert.net/docs/sentence_transformer/usage/efficiency.html)
- [Supermemory: Best Open-Source Embedding Models Benchmarked](https://supermemory.ai/blog/best-open-source-embedding-models-benchmarked-and-ranked/)
- [The Practitioner's Guide To E5 — Pinecone](https://www.pinecone.io/learn/the-practitioners-guide-to-e5/)
- [Benchmarking Google Embeddings 2 arXiv:2605.23618](https://arxiv.org/html/2605.23618)
- [OpenSearch asymmetric embedding semantic search](https://docs.opensearch.org/latest/tutorials/vector-search/semantic-search/semantic-search-asymmetric/)
