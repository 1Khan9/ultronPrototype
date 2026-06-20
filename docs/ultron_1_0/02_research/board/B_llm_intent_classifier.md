# LLM-as-intent-classifier with structured/constrained output: producing RELAY/PRIVATE/IGNORE reliably and fast

## TL;DR recommendation for Ultron 1.0

**Use a three-layer funnel, not a monolithic LLM call:**

1. **Layer 0 — Rules + RapidFuzz (already exists):** Handle all clearly-deterministic utterances (known snap patterns, explicit "tell my team", "Ultron + known command"). Zero latency. Covers ~60-75% of input in a tuned gaming-relay system.

2. **Layer 1 — EmbeddingGemma-300M cosine similarity gate:** For utterances that pass Layer 0, run a fast embedding + cosine-to-labeled-exemplars classification. EmbeddingGemma-300M on GPU in-sidecar runs in ~5-15 ms at 512 tokens. Calibrated threshold (e.g., cosine > 0.82) accepts confidently-RELAY and confidently-IGNORE cases. Covers most of the remaining 25-35%.

3. **Layer 2 — Josiefied-Qwen3-8B LLM (non-thinking, constrained):** Invoke ONLY for the ~5-10% genuinely ambiguous band. Use `max_tokens=1` with a GBNF grammar constraining output to exactly one of three tokens (`R`, `P`, `I` or full words `RELAY`, `PRIVATE`, `IGNORE`). TTFT for Qwen3-7B at 512-token context on an RTX 5080 is ~45ms (RTX 4070 Ti is ~100-105 ms estimated from the 2.3x gap); at a shorter 100-200 token prompt, expect ~20-50 ms prefill on the RTX 4070 Ti. Thinking mode MUST be disabled (`/no_think` or `enable_thinking=False`) — thinking tokens would add hundreds of ms with zero benefit for classification.

**Do NOT use raw LLM token logprobs for calibrated probability estimates.** Instruction-tuned models (RLHF/DPO) are systematically overconfident; ECE degrades significantly post-instruction-tuning. Instead use the constrained-output token-probability ratio `P(RELAY) / (P(RELAY) + P(PRIVATE) + P(IGNORE))` as a soft confidence signal for logging only, not for routing decisions. Hard constrained decoding (grammar) is superior to free-text generation for this task.

---

## Findings

### 1. Intent classification: LLM vs. embedding model accuracy and latency

The most comprehensive empirical comparison found is Levin et al. 2024, "Intent Detection in the Age of LLMs" (EMNLP Industry), which benchmarks Claude Haiku, Mistral Large, and SetFit sentence-transformers on real intent datasets.

**F1 score summary (Table 1 from paper):**
- Claude v3 Haiku: 0.736
- Mistral Large: 0.735
- Claude v2: 0.737
- SetFit + Negative Data Augmentation: 0.658
- SetFit baseline: 0.600

**Latency (single inference, production setting):**
- SetFit (embedding model): 0.030 ms baseline (56× faster than best LLM)
- Claude v3 Haiku: 1.697 ms
- Mistral Large: 3.565 ms

**Key takeaway:** LLMs outperform embedding models on F1 by ~8-12 percentage points in intent classification, but are 20-56× slower. A *hybrid uncertainty-based routing* (LLM for uncertain cases, embedding model for high-confidence cases) achieves within ~2% of full-LLM accuracy at ~50% less latency (measured by routing ~M=20 Monte Carlo dropout samples with threshold).

**For Ultron 1.0:** The 8-12 pp accuracy gap matters most in the ambiguous band (talking to Discord/stream vs. addressing Ultron). The embedding gate wins for obvious cases. The LLM gate wins for edge cases. This validates the three-layer funnel above.

### 2. Constrained/structured LLM output: grammar, logit bias, logprobs

#### GBNF grammar constrained decoding in llama.cpp

llama.cpp implements Graydon BNF (GBNF) constrained decoding. For every token at each position, `llama_grammar_apply_impl()` sets logits of invalid tokens to `-inf` (zero probability), then sampling proceeds on the valid-only distribution.

A minimal GBNF for 3-class classification:
```
root ::= "RELAY" | "PRIVATE" | "IGNORE"
```

This means the first token emitted by the model *must* be one of those three strings. Since these are multi-character sequences, the grammar propagates across multiple token positions if needed (e.g., `RELAY` might tokenize as `RE` + `LAY`), but you can choose single-character labels (`R`/`P`/`I`) that tokenize as single tokens, making true single-token output practical.

**Performance of GBNF enum constraints:**
- Grammar compilation: "under 60 ms" (Guidance), 0.12-0.30s for XGrammar (complex schemas only)
- Per-token mask computation: "under 50 microseconds with caching" for tight enums
- Overhead vs. unconstrained: practically zero for single-token enum selection (the masking happens at the sampling step which is CPU-bound, not GPU-bound in llama.cpp)
- The LMSYS compressed-FSM work (SGLang) showed constrained decoding can be *faster* than unconstrained generation in jump-forward scenarios: "up to 2× lower latency, 2.5× higher throughput"
- llama.cpp GBNF has acknowledged performance gotchas for *complex* grammars (deep rule trees, high repetition), but a 3-enum grammar is trivially shallow — no practical overhead

**Python API (llama-cpp-python 0.3.22):**
```python
from llama_cpp import Llama, LlamaGrammar

grammar = LlamaGrammar.from_string('root ::= "RELAY" | "PRIVATE" | "IGNORE"')

output = llm(
    prompt,
    max_tokens=1,          # only need first token
    grammar=grammar,       # constrain to 3 tokens
    temperature=0.0,       # deterministic
    logprobs=3,            # get top-3 logprobs for the chosen token
)
# output['choices'][0]['text'] will be one of "RELAY", "PRIVATE", "IGNORE"
# output['choices'][0]['logprobs']['top_logprobs'][0] = {token: log_prob, ...}
```

Note: `logprobs` in the high-level API returns token probabilities for the *generated* tokens. To get the full distribution over all three constrained tokens, use `logit_bias` + `logprobs` together, or read `llm.scores`/`llm._scores` after the call (low-level internal attribute, available post-generation).

#### logit_bias approach (alternative)

For single-token classification you can whitelist only the 3 class tokens and set all others to `-inf` using `logit_bias`:
```python
# token IDs for R, P, I in Qwen3 tokenizer (must look up at model load time)
RELAY_ID = tokenizer.encode("RELAY")[0]
PRIVATE_ID = tokenizer.encode("PRIVATE")[0]
IGNORE_ID = tokenizer.encode("IGNORE")[0]
# set all other tokens to -inf via logit_bias dict, or use grammar (simpler)
```
In practice, GBNF grammar is simpler and equivalent for this use case.

#### logprobs and calibration

**The logprobs API does work for single-token classification.** With `max_tokens=1` and `logprobs=3` (top-3), llama-cpp-python returns the log-probabilities of the top tokens generated. After applying grammar constraints, these are renormalized over only the valid tokens. You can extract:
```python
top_lp = output['choices'][0]['logprobs']['top_logprobs'][0]
# e.g., {"RELAY": -0.2, "PRIVATE": -2.1, "IGNORE": -3.4} as log probs
import math
probs = {k: math.exp(v) for k, v in top_lp.items()}
confidence = max(probs.values())
```

**Critical calibration caveat:** Instruction-tuned/RLHF/DPO models are systematically miscalibrated, especially for classification tasks. Research consistently shows:
- Post-instruction-tuning ECE degrades significantly
- Models concentrate nearly all probability mass on a single label (overconfidence)
- Self-reported verbalized confidences are unreliable (ECE 0.30+ on hard tasks)
- Token-level logprobs from constrained decoding are better calibrated than verbalized confidence, especially for simple closed-label tasks

For Josiefied-Qwen3-8B (abliterated, DPO-tuned): the token logprobs under grammar constraint are likely more reliable than free-text verbalization, but should be treated as relative ordering signals, not calibrated probabilities. Use them for logging and threshold-tuning, not for hard routing decisions. Hard routing should be: grammar output token → deterministic class.

### 3. TTFT and single-token latency on the Ultron hardware

**Measured data (RTX 5080, Qwen3-7B FP16, 512-token context, batch=1):**
- TTFT p50: 44.8 ms, p95: 47.1 ms, p99: 48.3 ms
- The benchmark article states RTX 5080 is "2.3× faster than the RTX 4070 Ti Super" for this test

**Derived estimate for RTX 4070 Ti (Ultron's GPU), Qwen3-8B Q5_K_M:**
- FP16 RTX 5080 TTFT × 2.3 = ~103 ms for FP16 equivalent
- Q5_K_M quantization vs FP16: prefill is compute-bound, quantization primarily helps decode throughput more than prefill TTFT; expect 10-20% prefill speedup → **~85-95 ms TTFT at 512-token context**
- At shorter prompt (~128-200 tokens for a terse intent-gate call): **~25-40 ms TTFT** (prefill scales roughly linearly with context for single-batch)
- Decode of 1 token after prefill: ~15-19 ms at 52-68 tok/s (RTX 4070 class)
- **Total for single-token classification at short prompt: ~40-60 ms end-to-end**

**Thinking mode penalty:** Qwen3's thinking mode prepends a `<think>...</think>` block before the answer. With `budget_tokens` uncapped, this could add 500-2000+ tokens of generation before the answer token, destroying latency. With `budget_tokens=0` (supported via Alibaba's API, unclear in llama.cpp in-process), or `/no_think` system prompt prefix, thinking is suppressed. For classification, thinking mode provides zero benefit and must be disabled.

**Cold-start latency:** First inference after CUDA graph compilation: ~480 ms (warm: 45 ms on RTX 5080). For Ultron this is a startup penalty only; subsequent calls hit the warm path.

### 4. Hybrid routing: when to escalate to the LLM gate

The routing/cascading survey (Zhang et al., 2025) identifies the optimal hybrid approach for latency-sensitive systems:

**Recommended pattern for Ultron's intent gate:**

```
Utterance
  → Layer 0: Rules + RapidFuzz (< 1 ms)
      IF match → deterministic class, done
      ELSE → Layer 1: EmbeddingGemma cosine similarity (5-15 ms)
          IF cosine > high_threshold (0.82) → class from nearest exemplar
          IF cosine < low_threshold (0.45) → IGNORE (not addressed to Ultron at all)
          ELSE → Layer 2: Qwen3-8B constrained classification (40-60 ms)
              single-token GBNF output → RELAY / PRIVATE / IGNORE
```

**Uncertainty thresholds:** From Levin et al. 2024, Monte Carlo dropout M=20 samples from SetFit used variance > threshold to escalate. For EmbeddingGemma cosine similarity as a proxy:
- `cosine > 0.82`: high confidence, accept embedding decision
- `0.45 < cosine < 0.82`: uncertain band, escalate to LLM
- `cosine < 0.45`: likely not addressed to Ultron at all (IGNORE)

These thresholds are initializations — they should be tuned on labeled evaluation data from Ultron's actual usage traces (logs/kenning.log).

**Cost savings:** ICLR 2024 Hybrid LLM paper showed threshold-based routing achieves "up to 40% fewer large-model calls" with no quality drop. RouteLLM achieved 85% cost reduction at 95% GPT-4 quality by routing only 14% of queries to the strong model.

For Ultron, "cost" is measured in latency: routing ~10% of utterances to the 8B LLM (40-60 ms) vs. all utterances (would dominate the budget) is the key optimization.

### 5. Prompt design for LLM classification

For the Qwen3-8B intent gate call, the prompt must be:
- **Short** (128-200 tokens max to hit the ~25-40 ms prefill target)
- **Non-thinking mode** (system prompt must include `/no_think` or `\nYou are a classifier. Respond with exactly one word.`)
- **Few-shot exemplars** (2-3 per class, embedded in the system prompt — frozen, not dynamic)

Example system prompt:
```
You are a classifier. Respond with exactly one word: RELAY, PRIVATE, or IGNORE.
RELAY = utterance should be relayed to the team (tactical info, callout, etc.)
PRIVATE = utterance is addressed to Ultron personally (question, command)
IGNORE = utterance is not addressed to Ultron or the team (talking to Discord/stream)

Examples:
"Jett is B" -> RELAY
"Ultron what ability does Sova have" -> PRIVATE
"nice play bro" (to streamer) -> IGNORE
```

User message: `<transcribed utterance>`

This is ~130 tokens, hitting the low end of the prefill budget.

### 6. Calibration of LLM-emitted class probabilities

**What is calibrated:** A model is well-calibrated if when it assigns 80% confidence to a prediction, that prediction is correct 80% of the time.

**What research shows for instruction-tuned models:**
- Base LLMs (pre-RLHF): token-level next-token calibration is reasonably good for MCQ-style prompts
- Post-instruction-tuning (RLHF/DPO): ECE degrades; models overconcentrate probability mass
- Verbalized probabilities ("I am 90% confident"): ECE > 0.30 on most tasks, unreliable
- Token logprob ratios under constrained decoding: more reliable than verbalization but still miscalibrated for instruction-tuned models
- Best approach for calibrated confidence: post-hoc temperature scaling (learn a scalar T on held-out labeled data, apply to logits before softmax); or use M=10 sampling runs with `temperature=0.5` and measure class vote fractions

**For Ultron 1.0:** Do not trust raw Qwen3 logprobs as probabilities. Treat the GBNF-constrained output token as a hard classification decision. If confidence estimation is needed (e.g., for fallback logic), use:
1. `logprobs` to get the log-ratio of the chosen vs. runner-up class
2. Log-ratio > 2.0 nats: high confidence, accept
3. Log-ratio < 0.5 nats: low confidence, consider fallback (e.g., default to PRIVATE to avoid missed relays)

### 7. Anticheat compatibility

**Layer 0 (rules/RapidFuzz):** numpy + stdlib only. Anticheat-safe.

**Layer 1 (EmbeddingGemma):** Already running in the sidecar process. The sidecar communicates via IPC (socket). Anticheat-safe as designed — the gaming process does not import torch/transformers.

**Layer 2 (Qwen3-8B via llama-cpp-python):** llama-cpp-python is in-process. The anticheat constraint says "relay path imports only numpy+urllib+scipy+stdlib+rapidfuzz." If the 8B LLM is also loaded in-process in the same Python runtime, this conflicts with the constraint (llama-cpp-python depends on its own C shared library, not torch, but it is still a non-trivial native extension).

**Resolution options:**
- **Option A (Recommended):** Move the 8B LLM to the sidecar or a separate subprocess. The sidecar already exists for EmbeddingGemma; adding a second inference endpoint (or co-locating Qwen3-8B in the sidecar) keeps the relay/orchestrator process clean. This matches existing architecture (sidecar_lock, IPC socket).
- **Option B:** Keep 8B LLM in-process but classify it as "LLM inference module" separate from "relay path" — if the anticheat scope only covers specific relay-path imports, and the LLM module is loaded only at startup (not conditionally triggered by game events), risk may be acceptable. Check existing firewall rules.

### 8. Layer 2 calibration via exemplar injection

Since Ultron 1.0 retires hard snap matchers in favor of LLM-with-exemplars, the classification prompt can inject **in-context exemplars** from the existing 1628-tail flavor library and the curated snap registry as class demonstrations. This is functionally equivalent to a few-shot classifier and avoids fine-tuning.

Research finding: Few-shot exemplar injection for classification (without fine-tuning) closes 80-90% of the gap between zero-shot LLM and fine-tuned classifiers on similar intent tasks (see "Exploring Zero and Few-shot Techniques for Intent Classification", arXiv 2305.07157). For a 3-class problem with clearly-defined classes, 3-5 exemplars per class is sufficient.

### 9. Self-REF confidence tokens (future option)

The Self-REF paper (arXiv 2410.13284) shows that fine-tuning a small model to append `<CN>` (correct) / `<UN>` (uncertain) tokens after its answer, then using `P(<CN>) / (P(<CN>) + P(<UN>))` as a routing signal, achieves:
- 2.03× latency improvement over always using large model
- Outperforms verbalized confidence, logits-based methods, and prompted scoring

For Ultron 1.0 this is **future/optional** (requires fine-tuning Qwen3-8B on Ultron-specific labeled data). The immediate approach (GBNF constrained classification) is sufficient for launch.

---

## Concrete techniques/params we should adopt

1. **GBNF grammar for constrained classification output:**
   ```python
   grammar = LlamaGrammar.from_string('root ::= "RELAY" | "PRIVATE" | "IGNORE"')
   output = llm(prompt, max_tokens=1, grammar=grammar, temperature=0.0, logprobs=3)
   label = output['choices'][0]['text'].strip()
   ```
   Use `max_tokens=1` for true single-token cost. Grammar masks invalid tokens before sampling.

2. **Non-thinking mode:** Always prepend `/no_think` or equivalent in the system prompt when calling Qwen3-8B for classification. Thinking tokens have zero benefit for 3-class intent classification and add 100-2000 ms.

3. **Short prompt discipline:** Cap the classification prompt at 128-200 tokens. At 200 tokens, RTX 4070 Ti prefill is ~10-20 ms; at 512 tokens it is ~85-95 ms. The difference is 65-80 ms per call — significant for a real-time voice pipeline.

4. **Uncertainty band gating:** Only invoke Layer 2 (LLM) when Layer 1 (EmbeddingGemma cosine) falls in the `[0.45, 0.82]` band. Tune these thresholds on 200+ labeled utterances from `logs/kenning.log`.

5. **Hard decision, soft logging:** Trust the GBNF-constrained output token as the classification decision. Log the log-ratio of chosen vs. runner-up class for offline calibration analysis. Do not use raw logprobs for routing decisions without post-hoc temperature scaling.

6. **Log-ratio confidence threshold:** If `log P(chosen) - log P(runner_up) < 0.5`, flag as low-confidence and default to PRIVATE (conservative: better to answer Ultron privately than miss a relay or falsely relay non-team speech).

7. **Sidecar co-location:** If anticheat requires it, run Qwen3-8B intent classification endpoint in the sidecar alongside EmbeddingGemma (separate socket endpoint). Add ~2-5 ms IPC overhead; still well within budget.

8. **Exemplar injection:** Inject 3-5 per-class exemplars in the system prompt, drawn from the existing snap registry and usage logs. Rotate exemplars based on in-game context (e.g., in a competitive match, weight toward tactical relay exemplars).

9. **Budget token control:** In llama-cpp-python, Qwen3 thinking mode is controlled by system-prompt prefix (`<|im_start|>system\n/no_think\n...`) rather than a budget parameter. Confirm `enable_thinking=False` is respected in the in-process llama-cpp-python build.

---

## Risks/caveats for our constraints

### Risk 1: Logprob calibration not reliable out-of-box
Instruction-tuned Qwen3-8B (Josiefied, abliterated, DPO) will have degraded ECE. Raw logprob confidences will be overconfident. Mitigation: use hard constrained output for routing; reserve logprobs for offline calibration and threshold tuning.

### Risk 2: GBNF overhead on complex grammars
For a 3-enum GBNF, overhead is negligible (<50 µs masking). If the grammar grows (e.g., adding structured JSON output for slot extraction in the same call), complexity increases. Keep the intent-gate grammar minimal; use a separate call for slot extraction.

### Risk 3: TTFT dominates when prompt is long
If the context passed to the LLM gate includes conversation history or the full flavor library, prefill can balloon. At 2048 tokens, RTX 4070 Ti prefill ≈ 300-400 ms — catastrophic for real-time voice. Hard limit: 256 tokens for the intent gate call.

### Risk 4: Qwen3-8B in-process vs. anticheat
llama-cpp-python is not a standard Windows DLL that anticheat tools scan for by name, but it does load a `.dll`/`.so`. Verify it is not triggering BattlEye/Vanguard module load hooks. The safest path is sidecar co-location (Risk mitigation = Option A above).

### Risk 5: Thinking mode leakage in llama-cpp-python
Qwen3's thinking mode is triggered by the system prompt content. If the system prompt does not explicitly suppress thinking (`/no_think`), the model may spontaneously enter thinking mode and prepend a long `<think>` block, only emitting the classification token after hundreds of decoding steps. Always include the no-think directive and verify with a test inference that the first emitted token is directly a class label.

### Risk 6: Tokenization of class labels
`RELAY`, `PRIVATE`, `IGNORE` may each tokenize as 2+ tokens in Qwen3's BPE tokenizer, making `max_tokens=1` insufficient to fully emit the label. Solutions:
- Use single-character labels (`R`, `P`, `I`) that are guaranteed single tokens
- Or use `max_tokens=6` to allow full label emission with GBNF enforcing exact strings
- Verify token IDs at model load time: `llm.tokenize(b"RELAY")` should return a list of 1 or 2 IDs

### Risk 7: EmbeddingGemma cosine similarity as a calibrated gate
Cosine similarity to exemplars is not a probabilistic classifier — the threshold values (0.45, 0.82) are heuristic starting points. Must be tuned on labeled data before deployment. An incorrectly-placed lower threshold will flood Layer 2 (all utterances hit the LLM); an incorrectly-placed upper threshold will cause embedding misclassifications to bypass the LLM.

---

## Sources

1. Levin et al., "Intent Detection in the Age of LLMs", EMNLP 2024 Industry Track — https://arxiv.org/abs/2410.01627 / https://arxiv.org/html/2410.01627
2. "Beyond the Hype: Embeddings vs. Prompting for Multiclass Classification Tasks", arXiv 2025 — https://arxiv.org/pdf/2504.04277
3. LMSYS Blog, "Fast JSON Decoding for Local LLMs with Compressed Finite State Machine" (SGLang jump-forward decoding) — https://www.lmsys.org/blog/2024-02-05-compressed-fsm/
4. Tianpan, "Grammar-Constrained Generation: The Output Reliability Technique Most Teams Skip" (2026, llama.cpp overhead numbers) — https://tianpan.co/blog/2026-04-16-grammar-constrained-generation-output-reliability
5. DeepWiki llama.cpp Grammar and Structured Output documentation — https://deepwiki.com/ggml-org/llama.cpp/8.1-grammar-and-structured-output
6. DeepWiki llama-cpp-python Grammar-Based Generation documentation — https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation
7. Zhang et al., "Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey", arXiv 2025 — https://arxiv.org/html/2603.04445v2
8. Ding et al., "Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing", ICLR 2024 — https://arxiv.org/pdf/2404.14618
9. "Confident or Seek Stronger: Exploring Uncertainty-Based On-device LLM Routing From Benchmarking to Generalization", arXiv 2025 — https://arxiv.org/abs/2502.04428
10. Self-REF: "Learning to Route LLMs with Confidence Tokens", arXiv 2024 — https://arxiv.org/html/2410.13284v3
11. LLM Router prefill activations paper — https://arxiv.org/html/2603.20895v2
12. Qwen3 TTFT benchmarks on RTX 5080 — https://markaicode.com/benchmarks/cuda-qwen-3-rtx-5080-ttft-benchmark/
13. "Calibration Across Layers: Understanding Calibration Evolution in LLMs", arXiv 2025 — https://arxiv.org/html/2511.00280v1
14. llama-cpp-python logprobs discussion — https://github.com/abetlen/llama-cpp-python/discussions/1101
15. llama-cpp-python API Reference — https://llama-cpp-python.readthedocs.io/en/latest/api-reference/
16. Qwen3 speed benchmarks — https://qwen.readthedocs.io/en/latest/getting_started/speed_benchmark.html
17. EmbeddingGemma 300M paper — https://arxiv.org/pdf/2509.20354
18. "Leveraging Uncertainty Estimation for Efficient LLM Routing", arXiv 2025 — https://arxiv.org/pdf/2502.11021
19. "Calibrating Verbalized Probabilities for Large Language Models", arXiv 2024 — https://arxiv.org/pdf/2410.06707
20. XGrammar: "Flexible and Efficient Structured Generation Engine for LLMs", arXiv 2024 — https://arxiv.org/pdf/2411.15100
