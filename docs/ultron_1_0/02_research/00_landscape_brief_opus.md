# Ultron 1.0 — Frontier Landscape Brief (Opus, pre-board)

This is my own deep web-research pass (no agents), done to map the frontier before crafting the
large research board. It captures the current SOTA + concrete techniques for each pillar of the
Ultron 1.0 vision, with sources. It is intentionally uncut. The agent board (Phase 3) goes deeper;
this brief exists so I can craft that board with maximum specificity.

**Date:** 2026-06-20. **Knowledge cutoff caveat:** my training cutoff is Jan 2026; everything here
is cross-checked against live search (June 2026), which surfaced post-cutoff items (Qwen3.5/3.6,
vLLM Semantic Router GA, Pipecat Nemotron, Smart-Turn v3) — noted inline.

---

## Pillar 1 — Optional-wakeword, always-listening intent gate (the hardest, most novel piece)

**Goal:** always transcribe; per finalized speech segment, classify into one of three actions:
(A) **relay-to-team** (a callout/command meant for teammates), (B) **me-only reply** (talking to
Ultron, wants a private answer, no relay), (C) **ignore** (talking to a third party e.g. Discord, or
to stream chat, or thinking out loud). Wake word still works but becomes one strong signal, not a gate.

This is the research field of **Device-Directed Speech Detection (DDSD)** — deciding whether an
assistant was addressed without a trigger phrase.

- **Apple's DDSD** (ML Research): a *dual-model ensemble* — an **acoustic-only** model + an
  **ASR-decoder-feature** model (LatticeRNN over the recognition lattice) — trained with
  **weak supervision + knowledge distillation** (LatticeRNN regularizes the acoustic model's loss).
  Reported ~**4% EER** for the ensemble; distillation gave a 66% EER improvement over acoustic-alone.
  Takeaway: **fuse acoustic + ASR + text signals**; you don't need one perfect classifier.
- **Multimodal / foundation-model DDSD** (arXiv 2312.03632): use large-foundation-model
  representations (audio + ASR text + decoder signals) for resource-efficient DDSD. Takeaway: an
  LLM/embedding classifier over the transcript + light acoustic features is a strong, trainable-free path.
- **SELMA** (arXiv 2501.19377): a single speech-enabled LM jointly handling DDSD + ASR + intent —
  the modern "one model does addressing + understanding" direction.
- Practical reality (Picovoice/Sensory 2026 guides): always-on raises **privacy/compute** concerns;
  the standard always-listening chain is wake → VAD → intent/STT, and "no-wakeword" systems must add
  a directedness classifier. For us, everything is local so privacy is bounded to the machine.

**My synthesis for Ultron 1.0 (training-free, fits our stack):** a **layered, cost-asymmetric gate**:
  1. Cheap text signals (reuse the existing `addressing/` features: wake word present? imperative
     mood? 2nd-person-plural "they/them/enemy"? agent/location/ability tokens? site letters?).
  2. **Semantic similarity** of the transcript to the **relay-command exemplar set** (the snap
     library — thousands of real callouts) via the embedder sidecar; high max-cosine ⇒ relay-likely.
  3. **Fuzzy/lexical** match (RapidFuzz) to canonical callout templates for ASR-robustness.
  4. A small **LLM classifier** (the 8B itself, or flan) for the ambiguous middle band only —
     prompt it to choose {relay, me-only, ignore} given the transcript + recent context, **constrained
     decoding** (GBNF) to a single token. Consult only when layers 1–3 are uncertain (zero latency for
     clear cases — mirrors the existing "flan only when |logit|<3" design).
  5. Fuse in **log-odds** with a **cost-asymmetric threshold** (false relay is worse than a missed
     relay — already the existing `tau` philosophy). Wake word = a large positive feature, not a gate.
  6. **Context window:** keep the last few turns + whether Ultron just spoke (barge-in vs new turn);
     "talking to someone else" is signaled by 2nd-person-singular address to a *named non-agent*,
     question-to-a-person cadence, and absence of tactical tokens.

---

## Pillar 2 — Route ALL responses through the 8B LLM, with deterministic snaps as routers

**Goal:** snaps no longer *produce* the line; they *route* — pick a curated prompt template + inject
the matching snap responses as **in-context exemplars** + inject agent/flavor libraries. The LLM
authors the final reply (incl. its own context-fitting flavor tail).

- **Semantic routing is the validated pattern** (vLLM Semantic Router GA Jan 2026; Aurelio
  `semantic-router`): **pre-encode example utterances per route**, route by **nearest-neighbor in
  embedding space**; "adding new routing patterns doesn't require retraining — add candidate phrases
  and embed them." This is *exactly* "use our snap-callout library as match targets." Modern stacks add
  a small classifier (ModernBERT) for speed. Signal-Decision architectures fuse Domain/Keyword/
  Embedding/Factual signals — matches our hybrid lexical+semantic router.
- **Dynamic exemplar selection** (multiple 2025 papers): select few-shot exemplars **per input** by
  embedding similarity + **MMR** (relevance + diversity). Reported +5–7% F1 over fixed exemplars.
  **We already have an MMR tail selector** (`_tail_selector.py`) — reuse it to pick the best snap
  exemplars to inject. TF-IDF/SBERT retrieval both work; SBERT (our embeddinggemma) is stronger.
- **Persona/role-play prompting** (FURINA benchmark 2510.06800; "Talk Less, Call Right" 2509.00482;
  Prompt Report 2406.06608): strict persona is best held by (a) a strong system prompt defining the
  character, (b) **few-shot persona anchors** (curated in-character lines — we have ~1,628), and
  (c) optional **test-time persona alignment**. Abliterated models can drift off-persona, so persona
  anchoring + a tight system prompt matter more, not less.
- **Reliable structured output** = **constrained decoding / GBNF grammars** (llama.cpp converts a
  JSON-Schema subset → GBNF; eliminates retry logic; slightly slower; *schema is NOT injected into the
  prompt* — you must also describe the format in the prompt). This is how we make the
  **back-to-back-commands → one combined response** deterministic and parseable, and how we keep the
  relay line clean (callout + tail in a known shape) for the team channel.

**My synthesis:** a **prompt-assembly pipeline**: route → select template → retrieve top-k snap
exemplars (MMR) → inject agent context/vocab/tails by addressed agent(s)/team → set verbosity
directive (no/low/high) → set tail on/off → (for command-strings) instruct one combined output under a
grammar. The system-prompt + persona-anchor prefix is **stable** ⇒ cache it (Pillar 5).

---

## Pillar 3 — The 8B model + thinking mode + serving in ≤10 GB VRAM

- **Model pick CONFIRMED: `Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M`** (on `E:\UltronModels`).
  JOSIEFIED (goekdenizguelmez) uses **"gabliteration"** — multi-directional, regularized weight
  modification that achieves uncensored behavior **without** the quality degradation of naive
  abliteration; "often outperform base on standard benchmarks" and preserves **tool use + instruction
  following**. Qwen3 = **hybrid thinking** model (we get the thinking trace the user wants). 8B exactly
  matches the mandate. Abliteration matters because Ultron must trash-talk/flame on command without refusals.
  - Alternatives on disk: `Qwen3.5-9B-Q4_K_M` (newer arch, but 9B not 8B, **not abliterated**, reasoning
    **off by default**) and `Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M`. Keep them for an A/B lab
    (the 0.1.1 model-lab pattern). Extended-context Josiefied 8B variants (64k/192k) exist if needed.
  - VRAM: Q5_K_M 8B ≈ ~5.6 GB weights; +KV cache. Comfortably under 10 GB even with a big context and
    a draft model; can put KV at q8_0 and offload all layers (4070 Ti, 12 GB).
- **Thinking-mode control (llama.cpp / llama-cpp-python):** soft switches `/think` `/no_think`;
  server flags `--reasoning-format deepseek` (separates `reasoning_content` from `content`),
  `--reasoning off`, `--chat-template-kwargs '{"enable_thinking": false}'`. **Known bug:** `enable_thinking:false`
  sometimes still thinks; robust fix = a custom chat template / inject `/no_think`. **The `<think></think>`
  tags must be parsed correctly** — "almost everyone runs Qwen3 on llama.cpp incorrectly" (garbled output
  if mishandled). In-process (llama-cpp-python) we parse `<think>…</think>` from the stream → route to the
  **trace log**, never to TTS. Thinking ON for ambiguous routing/answers; OFF for fast snap-style relays.
- **Latency levers (deferred but architecturally relevant):** prefix/prompt caching (Pillar 5),
  speculative decoding (already wired: prompt-lookup + draft model), KV-cache quantization, ubatch tuning.

---

## Pillar 4 — Always-on STT + turn-taking

- **faster-whisper** streams near-zero-latency on GPU; **two-pass decoding** (CTC prefix beam search
  for partials → attention rescoring at endpoint, Interspeech 2025) and **Whisper-Streaming**
  local-agreement give finalized text at low latency. Whisper large-v3-turbo already in the stack.
- **Turn detection / semantic VAD:** Smart-Turn v3 (already used) classifies end-of-turn from the
  **waveform** (intonation/pace), beyond energy VAD; the 2026 production stack (Pipecat SmartTurn,
  LiveKit TurnDetector) classifies **backchannel vs barge-in vs continued silence** as a learned signal.
  For always-on: keep turn detection active during playback (barge-in), finalize segments on endpoint,
  run the intent gate per finalized segment.
- **Reference topology:** Pipecat (`Mic → STT → LLM → TTS`) is the canonical real-time voice-agent
  framework (2026). We already have a stronger, anticheat-pinned, local version of this; we adopt its
  *patterns* (continuous capture, semantic turn-taking, barge-in), not the dependency.

---

## Pillar 5 — Make route-all-through-LLM affordable (quality-first now, but cheap to keep fast)

- **Prompt prefix caching** (llama.cpp `--cache-reuse`, host-RAM prompt cache; llama-cpp-python kv
  reuse): a **stable system-prompt + persona-anchor + exemplar prefix** is cached once; prefill drops
  from full cost to ~ms on subsequent turns. Architect the prompt so the **variable part (the actual
  callout) is at the END**, maximizing the cached prefix. This is the single biggest lever for making
  "every turn hits the LLM" viable later.
- **Grammar-constrained decoding** adds slight overhead but removes retries and guarantees parseable,
  clean team-channel output.

---

## Pillar 6 — Fuzzy/lexical matching library

- **RapidFuzz** (C++, MIT) is the 2025/2026 standard: ~40% faster than alternatives, rich metrics
  (Levenshtein, Jaro-Winkler, token-set). **Jellyfish** for phonetic (Soundex/Metaphone) but weak on
  long text. Both are pure compute libs — **anticheat-safe** (no system access). Use RapidFuzz for the
  ASR-robust template/callout matching layer in the intent gate; phonetic for agent-name confusables
  (complements the existing common-words gate + gazetteer).

---

## Cross-cutting design implications (feed these into the board + plan)

1. **Hybrid gate, cost-asymmetric, fail-open** — reuse the addressing `tau` philosophy for the 3-way
   {relay, me-only, ignore} decision; wake word = strong feature, not gate.
2. **Reuse, don't rebuild:** embedder sidecar (semantic), `_tail_selector` MMR (exemplar pick),
   addressing features, snap library (exemplars + fuzzy targets), flavor library (persona anchors +
   agent context), trace/usage-trace (per-stage tracing). The pivot is largely *recomposition*.
3. **Anticheat constraint holds:** new libs must be pure-compute (RapidFuzz ok); all heavy ML stays in
   the sidecar or offline; nothing on the voice/relay path may import automation.
4. **Persona is load-bearing for an abliterated model** — strong system prompt + few-shot persona
   anchors + (optionally) a light output grammar to prevent drift/leaks.
5. **Combined multi-callout output** = grammar-constrained single generation, not N LLM calls.
6. **Thinking trace is a first-class artifact** — capture `<think>` separately for prompt-refinement
   (exactly what the user asked for in the test harness).

---

## Sources

Pillar 1 (DDSD / always-on): [Apple — Device-Directed Speech Detection](https://machinelearning.apple.com/research/device-directed-speech) · [Multimodal DDSD w/ Large Foundation Models (arXiv 2312.03632)](https://arxiv.org/pdf/2312.03632) · [SELMA (arXiv 2501.19377)](https://arxiv.org/pdf/2501.19377) · [Picovoice wake-word guide 2026](https://picovoice.ai/blog/complete-guide-to-wake-word/) · [Sensory — do assistants need wakewords?](https://sensory.com/do-voice-agents-voice-assistants-and-llms-need-wakewords/)
Pillar 2 (routing/exemplars/persona/grammar): [vLLM Semantic Router](https://blog.vllm.ai/2025/09/11/semantic-router.html) · [vLLM SR Iris GA](https://vllm.ai/blog/2026-01-05-vllm-sr-iris) · [Signal-Decision routing](https://vllm.ai/blog/2025-11-19-signal-decision) · [Modular LoRA routing](https://blog.vllm.ai/2025/10/27/semantic-router-modular.html) · [Dynamic exemplar selection (arXiv 2409.01466)](https://arxiv.org/pdf/2409.01466) · [RAG dynamic few-shot NER (PMC12408026)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12408026/) · [FURINA role-play benchmark (arXiv 2510.06800)](https://arxiv.org/pdf/2510.06800) · [Talk Less, Call Right (arXiv 2509.00482)](https://arxiv.org/pdf/2509.00482) · [Prompt Report (arXiv 2406.06608)](https://arxiv.org/pdf/2406.06608) · [llama.cpp grammars README](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md) · [Constrained decoding guide](https://www.aidancooper.co.uk/constrained-decoding/) · [llama-cpp-python grammars](https://deepwiki.com/abetlen/llama-cpp-python/6.1-grammar-based-generation)
Pillar 3 (8B/thinking/serving): [JOSIEFIED-Qwen3:8b (Ollama)](https://ollama.com/goekdenizguelmez/JOSIEFIED-Qwen3:8b) · [Josiefied-Qwen3-4B-Abliterated-V2 / gabliteration](https://skywork.ai/blog/models/josiefied-qwen3-4b-abliterated-v2-free-chat-online-skywork-ai/) · [Qwen llama.cpp docs](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html) · [Turn off think mode (llama.cpp #20182)](https://github.com/ggml-org/llama.cpp/issues/20182) · [enable/disable reasoning Qwen3.5-9B](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/discussions/2) · [Unsloth Qwen3.5 run guide](https://unsloth.ai/docs/models/qwen3.5) · ["Only correct way" Qwen3.x + llama.cpp](https://blog.gopenai.com/the-only-correct-way-to-use-llama-cpp-with-qwen3-6-27b-d550bd0605a7)
Pillar 4 (STT/turn-taking): [Two-pass streaming Whisper (Interspeech 2025)](https://www.isca-archive.org/interspeech_2025/zhou25_interspeech.pdf) · [Baseten fastest Whisper streaming](https://www.baseten.co/blog/the-fastest-whisper-transcription-with-streaming-and-diarization/) · [Smart-Turn v3](https://huggingface.co/pipecat-ai/smart-turn-v3) · [Semantic VAD (Inworld)](https://inworld.ai/resources/what-is-semantic-vad) · [Barge-in/turn-taking 2026 (LiveKit)](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection) · [Pipecat](https://github.com/pipecat-ai/pipecat)
Pillar 5 (caching): [Host-memory prompt caching tutorial (llama.cpp #20574)](https://github.com/ggml-org/llama.cpp/discussions/20574) · [cache system prompt (#8947)](https://github.com/ggml-org/llama.cpp/discussions/8947) · [llama-cpp-python prompt caching (#44)](https://github.com/abetlen/llama-cpp-python/issues/44)
Pillar 6 (fuzzy): [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) · [Python text-matching comparison](https://www.researchgate.net/publication/390846511_A_Comparative_Analysis_of_Python_Text_Matching_Libraries_A_Multilingual_Evaluation_of_Capabilities_Performance_and_Resource_Utilization)
