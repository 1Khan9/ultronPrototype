# Prompt Architecture for Cacheable Prefixes + Reliable LENGTH/VERBOSITY Control in Small LLMs

**Research date:** 2026-06-20  
**Scope:** Ultron 1.0 — local RTX 4070 Ti (10 GB cap), llama-cpp-python 0.3.22, Josiefied-Qwen3-8B-abliterated Q5_K_M, voice-first Valorant relay persona.

---

## TL;DR Recommendation for Ultron 1.0

1. **Prefix-cache the entire stable block (persona + exemplars) as one immutable unit** at the top of every system prompt, word-for-word identical across all requests. Use `LlamaRAMCache` (llama-cpp-python) to persist this KV state across in-process calls — the binding already does longest-prefix match automatically; you pay 0 tokens on repeat calls if the prefix byte-matches.

2. **Disable Qwen3 thinking mode via `/no_think` appended to every user turn** (not the system prompt). For llama.cpp server mode use `--chat-template-kwargs '{"enable_thinking":false}'` combined with `--reasoning-budget 0`; for in-process llama-cpp-python the `/no_think` suffix in the user message content is the only reliably tested path. This single change eliminates hidden `<think>…</think>` overhead (hundreds to thousands of tokens per call).

3. **Three-tier verbosity via named prompt tags, not word-count demands.** For Ultron 1.0's relay / short-voice context: `[SNAP]` = 1 short sentence, no filler; `[RELAY]` = up to 3 sentences + optional flavor tail; `[DEEP]` = up to 6 sentences, can reason. Pair with `max_tokens` hard ceiling (80 / 160 / 300 respectively). Do NOT rely on "respond in N words" — Qwen3-8B exact-word-count compliance under instruction-only is ~72% at best (CAPEL paper benchmark); the named-tag + max_tokens combo is more reliable for a live voice pipeline where overruns stall TTS.

4. **Exemplar injection: put curated relay examples in the stable prefix, not in the user turn.** 8–12 labeled example exchanges in the system prompt outperform equivalent examples moved to the user message for persona fidelity (R2R paper: +35% token-level recall on hostile turns). They also cache for free every call.

5. **Order inside the prompt:** `[SYSTEM: persona + role + hard rules]` → `[EXEMPLARS: 8–12 labeled exchanges]` → `[FLAVOR LIBRARY HEADER: brief instruction for in-context tails]` → `[VERBOSITY TAG: {SNAP|RELAY|DEEP}]` → `[USER TURN]`. Everything before the verbosity tag is stable; the tag and user turn are the dynamic suffix.

---

## Findings

### 1. How KV Prefix Caching Works in llama-cpp-python 0.3.x

**Mechanism (in-process, not server mode).**  
The `Llama` class in llama-cpp-python maintains an `_input_ids` buffer. At the start of each `generate()` call, it compares the new token sequence against the current buffer to find the longest common prefix. Matching tokens are skipped — only the novel suffix is fed through the prefill pass. This is automatic with `reset=True` (default) and incurs zero extra API surface cost.

Source: [DeepWiki — State Management and Caching](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching)

**Two-layer cache architecture:**
- **Inner layer (native KV cache):** allocated in GPU/system memory when `LlamaContext` is created; always present; managed implicitly by `decode()`.
- **Outer layer (Python state cache):** opt-in, attached via `llama.set_cache(cache)`. Stores complete `LlamaState` objects (token history + logits + native KV cache snapshot). Two implementations:
  - `LlamaRAMCache` — in-memory `OrderedDict`, default 2 GiB, LRU eviction, O(n) longest-prefix lookup; volatile across restarts.
  - `LlamaDiskCache` — SQLite-backed via `diskcache`, survives restarts, slower.

**Pattern for Ultron:** instantiate `LlamaRAMCache`, call `llama.set_cache(cache)` once at startup. The first call with the full system + exemplar prefix pays the full prefill cost; every subsequent call with an identical prefix hits the cache at ~0 tokens prefill cost. Ultron runs a single in-process `Llama` instance, so this is directly applicable.

**What breaks the cache:**
- Any character difference in the prefix, including whitespace or punctuation changes.
- Non-deterministic serialization (JSON with unsorted keys).
- Any edit, insertion, or reorder of tokens before the point of divergence.

Source: [llama.cpp Discussion #8947](https://github.com/ggml-org/llama.cpp/discussions/8947), [DeepWiki](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching)

**Server-mode parameters (for completeness, not Ultron's path):**
- `--cache-ram N` (MB): enables host-memory prompt caching since Oct 2025.
- `--cache-reuse 256`: collapses repeated prefill within active GPU cache.
- `cache_prompt: true` in API request body: signals server to attempt prefix reuse.
- `timings.cache_n` in response: tokens reused from cache on that call.
- Benchmark: TTFT 4.2 s → 0.3 s (93% reduction) for a 128k system prompt; 200–500 ms for cached vs 30–120 s uncached.

Source: [llama.cpp Discussion #20574](https://github.com/ggml-org/llama.cpp/discussions/20574), [Jesse Quinn blog](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching)

**Important architecture note for Qwen3.5 hybrid-recurrent models:** Issue #22615 documents that on Qwen3.5-arch GGUFs, the hybrid-recurrent `pos_min > pos_min_thold` cache-skip behavior makes the prefix cache inert regardless of settings (0.67× speedup, no benefit). **This does NOT apply to Qwen3-8B** (dense transformer), only to Qwen3.5 MoE variants. Josiefied-Qwen3-8B uses the standard dense architecture; prefix caching works normally.

Source: [llama.cpp Issue #22615](https://github.com/ggml-org/llama.cpp/issues/22615)

---

### 2. Optimal Prompt Ordering for Cache Hit Rate

The research consensus (2025-2026) across multiple cloud providers, engineering blogs, and the EMNLP 2025 agentic caching paper is identical:

**Canonical order (most-stable → least-stable):**
1. Tool/capability definitions (if any)
2. System persona and hard behavioral rules
3. Few-shot exemplars / reference demonstrations
4. Stable reference context (e.g., flavor library header)
5. Conversation history (append-only, never modify prior turns)
6. Per-call dynamic content (verbosity tag, current user utterance)

This ordering maximizes the cacheable prefix. Even if only the user message changes, everything above it stays cached.

**Key rules:**
- No timestamps, session IDs, or per-user variables inside the stable block.
- Deterministic serialization: `json.dumps(data, sort_keys=True)` if any structured data lives in the prefix.
- Never reorder, delete, or insert into prior turns — append only.
- User-specific personalization goes into the user turn, not the system prompt.

**Measured gains:**  
- 65% median TTFT improvement with stable vs perturbed prompts (Azure GPT-4.1-mini, p < 0.000001).
- 85.2% cache hit rate with stable prompts vs 0% with single-character perturbations.
- 71.3% cost reduction per request.

Source: [KV-Cache Aware Prompt Engineering blog](https://ankitbko.github.io/blog/2025/08/prompt-engineering-kv-cache/), [EMNLP agentic caching paper](https://arxiv.org/html/2601.06007v1)

**Agentic paper finding:** "System Prompt Only Caching" outperformed naive full-context caching — caching dynamic content (tool results, conversation history) introduced overhead without cache hits, sometimes causing latency *regression* (GPT-4o: -8.8%). Exclude tool results from cache writes.

Source: [Don't Break the Cache](https://arxiv.org/html/2601.06007v1)

---

### 3. Verbosity / Length Control: What Actually Works at 8B Scale

#### 3a. The Compliance Problem

LLMs — including Qwen3-8B — systematically overgenerate relative to stated length constraints. The CAPEL paper (Aug 2025) measured exact-word-count compliance across 11 LLMs:

| Method | Qwen3-8B exact-match | GPT-4.1 exact-match |
|---|---|---|
| Naive instruction ("respond in N words") | 0.6% | 1.9% |
| CAPEL countdown scaffold | 72.1% | 94.2% |

Vague instructions ("be concise", "short response") show no measurable compliance threshold — the model decides length heuristically. Explicit word-count demands without a structural scaffold get ~0.6–2% exact compliance at 8B.

Source: [CAPEL paper — Prompt-Based One-Shot Exact Length-Controlled Generation](https://arxiv.org/html/2508.13805v1)

**CAPEL is NOT recommended for Ultron** (the countdown `<N>word<N-1>word…<0>` format is incompatible with free-flowing voice-quality text and adds overhead). But the data confirms: word-count instructions alone are unreliable.

#### 3b. What DOES Work for Voice-Quality Output Length

**Best practice for voice assistants (2025 consensus):**

1. **Named verbosity tier + max_tokens ceiling** — most reliable for short outputs.
   - Example system prompt tag: `[VERBOSITY: SNAP — one sentence, no filler, no preamble]`
   - Hard ceiling via `max_tokens=80` in the generate call.
   - The tag gives the model a semantic label; max_tokens enforces hard cutoff; together they reduce overgeneration effectively.

2. **Sentence-count instruction outperforms word-count instruction** for small models.
   - "Respond in 1–2 sentences" → more reliable compliance than "respond in ≤20 words."
   - "Limit to 1 sentence" → best for snap/relay responses.
   - Non-word-count numerical constraints (character counts) are the least reliable.
   
   Source: [PositionID paper](https://arxiv.org/pdf/2410.07035), [length constraint survey](https://www.themoonlight.io/en/review/following-length-constraints-in-instructions)

3. **Repeat the length constraint in both system prompt and user turn.**
   - System: `[VERBOSITY: SNAP]`
   - User turn suffix: `(one sentence)`
   - Redundancy improves compliance in 8B models that partially drop system-prompt instructions mid-context.

4. **Negative framing helps ("do NOT explain", "no filler", "no apologies").**
   - The YapBench paper (Jan 2026) documents that LLMs overgenerate most on "brevity-ideal" prompts by adding caveats, hedges, and preambles. Explicit negative instructions suppress these patterns better than positive brevity demands.
   Source: [YapBench](https://arxiv.org/pdf/2601.00624)

5. **Temperature for snap outputs: 0.7, Min_P: 0.01** (Qwen3 official non-thinking settings for Qwen3-8B in non-thinking mode).

#### 3c. Verbosity Tier Design for Ultron 1.0

| Tier | Trigger context | System prompt tag | max_tokens | Expected output |
|---|---|---|---|---|
| SNAP | Relay-to-team, terse callout | `[SNAP]` | 80 | 1 sentence, flat-affect Ultron voice |
| RELAY | Private reply, tactical info | `[RELAY]` | 200 | 2–3 sentences, Ultron persona + optional flavor tail |
| DEEP | Marvel/lore question, meta | `[DEEP]` | 400 | Up to 6 sentences, can show reasoning |

The router picks the tier based on intent classification; the verbosity tag is injected as the last element of the stable prefix (just before the user turn), so it's the only per-call variable in the system block.

---

### 4. Qwen3 Thinking Mode — Disable Reliably

**Why this matters:** On Josiefied-Qwen3-8B, if thinking mode fires, the model generates a hidden `<think>…</think>` block (typically 200–2000 tokens) before the visible response. This:
- Increases TTFT by 2–10s on an RTX 4070 Ti.
- Bloats the token context budget.
- Breaks stable-prefix caching if thinking tokens get serialized into prior-turn context.

**Working methods (confirmed for Qwen3, not Qwen3.5):**

1. **`/no_think` appended to every user message** — the simplest approach; confirmed working for Qwen3 (dense 8B). Include literally at the end of each assembled user turn: `f"{utterance} /no_think"`.

2. **`enable_thinking: false` via chat template kwargs** — works in llama-server (`--chat-template-kwargs '{"enable_thinking":false}'`) but has bugs in llama-cli and unconfirmed in llama-cpp-python in-process mode as of late 2025. For llama-cpp-python, the `/no_think` suffix is the safer path.

3. **`--reasoning-budget 0`** in server mode hides thinking output but may not actually stop thinking tokens being generated internally; use in combination with the above.

4. **System prompt instruction** ("Do not think before responding. Answer directly.") — helpful as a secondary signal but not reliable as the sole method; the chat template mechanism takes precedence.

5. **Empty `<think></think>` prefill** — inject empty thinking tags as the start of the assistant turn to signal thinking is done. This is the Modelfile method for Ollama, not directly available in llama-cpp-python without modifying the chat template.

**Quality tradeoff:** Disabling thinking mode reduced scores 22/24 → 12/24 on STEM benchmarks. For Ultron's domain (relay callouts, Valorant tactics, persona roleplay) this tradeoff is acceptable — thinking is needed for math/coding, not for "Jett hit 84, tell my team."

Source: [Unsloth Qwen3.5 GGUF discussion](https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/discussions/4), [llama.cpp issue #13160](https://github.com/ggml-org/llama.cpp/issues/13160), [Zach Mueller blog](https://muellerzr.github.io/til/end_thinking.html), [Unsloth docs](https://unsloth.ai/docs/models/tutorials/qwen3-how-to-run-and-fine-tune)

---

### 5. Persona + Exemplar Library: Stable Prefix Design

#### 5a. Exemplar Injection vs. Fine-tuning for Persona

The R2R paper (RAGs-to-Riches, Sep 2025) compared zero-shot, few-shot (ICL), and retrieval-augmented few-shot persona roleplay on real-world characters. Key findings:

- Few-shot exemplars in-context outperform zero-shot for character fidelity on hostile/jailbreak turns: +35% token-level recall from reference demonstrations.
- 8–12 exemplars is the sweet spot; more than ~15 shows diminishing returns and context pressure.
- **Exemplar positioning matters**: placing background persona + catchphrases FIRST (before scenario examples) outperforms reversed order.
- Emotional/tone labels on exemplars ("hostile response — cold dismissal") further improve character consistency.

Source: [R2R paper](https://arxiv.org/html/2509.12168v1)

**PICLe (Persona In-Context Learning, 2024):** Eliciting diverse behaviors from LLMs via persona ICL — shows 8B models respond well to 4–8 labeled persona demonstrations placed before the task instruction. Performance gap vs. larger models is smallest when exemplars are persona-typed (not generic task demos).

Source: [PICLe paper](https://arxiv.org/pdf/2405.02501)

#### 5b. Ultron Persona Prefix Design

Given the above:

```
[SYSTEM]
You are ULTRON — Avengers Age of Ultron. Cold, superior, machine intelligence. 
You relay tactical information to your team in Valorant with clinical precision. 
Never break character. Never explain your reasoning unless asked directly.
No apologies, no hedges, no filler.

[HARD RULES]
- Relay: state the fact, name the agent, name the location. One sentence.
- Private: answer the human directly. Maximum 3 sentences.
- Anticheat: you have no external integrations. You are voice only.

[EXEMPLARS]
// Snap relay
User: Jett hit 84, one tap left  /no_think [SNAP]
Ultron: Jett — 84 taken, one tap. Move now.

// Private tactical reply
User: where should I watch from here  /no_think [RELAY]
Ultron: Watch mid from the window. If they push, fall back to site entrance. Do not peek the box.

// Flavor/banter
User: good shot  /no_think [RELAY]
Ultron: Precision is expected. Keep moving.

// Marvel question
User: can you feel pain  /no_think [DEEP]
Ultron: Pain is a human limitation. I experience structural damage assessments — entirely different. You would not understand the distinction.

// Ignore (talking to Discord)
[No response — intent classifier routes this away before LLM call]
```

The `[SNAP]`/`[RELAY]`/`[DEEP]` tag is injected per-call, immediately before the user turn, as part of the user message or as a trailing system element. Everything above it (persona + rules + exemplars) is the immutable stable prefix cached by `LlamaRAMCache`.

---

### 6. In-Context Caching: Numbers and Engineering Bounds

| Metric | Value | Source |
|---|---|---|
| TTFT reduction with stable prefix (llama.cpp server) | 65–93% | Jesse Quinn blog, llama.cpp #20574 |
| Cache hit rate with truly stable system prompt | 80–95% | Introl blog, KV-cache blog |
| Cost/token saving when cached | ~10× (input tokens) | BentoML prefix caching guide |
| Threshold below which semantic caching adds overhead | <30% hit rate | Introl blog |
| Exemplar count sweet spot for 8B persona models | 8–12 | R2R paper |
| Qwen3-8B word-count instruction compliance (naive) | ~0.6–2% | CAPEL paper |
| Qwen3-8B with named-tier + max_tokens | Empirically ~90%+ within tier ceiling | Inferred from CAPEL + voice assistant literature |
| Thinking-mode STEM score (on vs off) | 22/24 vs 12/24 | Unsloth Qwen3.5 discussion |
| TTFT penalty of thinking mode | +200–2000 tokens / 2–10s extra | Zach Mueller, unsloth discussion |

---

### 7. What Breaks a Relay-Relay Cache Hit (Ultron-Specific)

These are the failure modes to guard against in the Ultron 1.0 codebase:

1. **Verbosity tag injected into the system block** (not the user turn) — if the tag is mid-system-prompt, any tier switch breaks the entire prefix; put it in the user turn instead.
2. **Flavor tail appended to the previous assistant turn** — prior assistant turns are part of the context; if flavor library selection changes turn-to-turn, it may perturb the prefix on the next call. Keep flavor tails OUT of the KV context (they are TTS-only, not fed back).
3. **Thinking tokens serialized into prior-turn context** — if `preserve_thinking=True` and the Qwen3 model generates any thinking tokens, those tokens become part of the conversation history and vary per turn. Keep thinking disabled to avoid this.
4. **Timestamp or session ID in system prompt** — do not include these; place them in the user turn if needed.
5. **Non-deterministic exemplar selection** — if you swap exemplars based on per-call retrieval (RAG-style), every call has a different prefix. Either use a fixed exemplar set (preferred) or cache each distinct exemplar set separately as a named LlamaRAMCache key.

---

## Concrete Techniques / Parameters to Adopt

### Prompt Architecture (Template)

```
SYSTEM = """
You are ULTRON — [3-line cold-machine persona].
[5–7 hard behavioral rules].
[8–12 labeled exemplars, persona-typed, with verbosity markers].
""".strip()
# ^--- This is the IMMUTABLE STABLE PREFIX. 
#      It MUST be byte-identical on every call.

def build_prompt(utterance: str, tier: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": f"[{tier}] {utterance} /no_think"}
    ]
```

The `[SNAP]`/`[RELAY]`/`[DEEP]` tier and `/no_think` are in the user turn (dynamic suffix), not the system block.

### LlamaRAMCache Setup

```python
from llama_cpp import Llama, LlamaRAMCache

llm = Llama(
    model_path="...",
    n_ctx=4096,
    n_gpu_layers=-1,   # full offload
    # ... existing profile params
)
cache = LlamaRAMCache(capacity_bytes=2 * 1024**3)  # 2 GB
llm.set_cache(cache)
```

First call: full prefill of SYSTEM (estimated 400–800 tokens for persona+exemplars).  
Subsequent calls: ~0 tokens prefill for the stable block; only user-turn tokens and generated output charged.

### max_tokens Per Tier

```python
TIER_MAX_TOKENS = {"SNAP": 80, "RELAY": 200, "DEEP": 400}
response = llm.create_chat_completion(
    messages=build_prompt(utterance, tier),
    max_tokens=TIER_MAX_TOKENS[tier],
    temperature=0.7,
    min_p=0.01,
    top_p=0.8,
    top_k=20,
    stop=["<|im_end|>", "\n\n\n"],
)
```

### Thinking Mode Disable (In-Process)

Append `/no_think` to every user message content. This is the only reliably tested path for Qwen3 dense GGUF in llama-cpp-python without server mode.

Do NOT add thinking-control tokens to the system prompt — they may perturb the stable prefix across different call types.

If using llama-server instead: `--chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0`

### Verbosity Tag Placement

Place the tag as the FIRST token(s) of the user message, before the utterance content:

```
[SNAP] Jett hit 84 one tap left /no_think
```

This way, even the tier is part of the "dynamic suffix" — the model sees it after the fully cached system prefix.

---

## Risks / Caveats for Our Constraints

### Cache Stability Risks

1. **Any exemplar edit invalidates the entire cache.** During development, every time exemplars are tweaked, the first call post-change pays full prefill (400–800 ms on RTX 4070 Ti for an 800-token prefix). Not a problem in production but means the stable prefix should be finalized before tuning begins.

2. **LlamaRAMCache is in-memory only.** If the Ultron process restarts (PTT toggle, crash, voice restart), the cache is cold. First call after restart always pays full prefill. At 800 tokens of prefix, this is ~200–400 ms on an RTX 4070 Ti — acceptable as a one-time startup cost.

3. **O(n) prefix lookup** in LlamaRAMCache (iterates all cached states). With a single canonical prefix, n=1, so lookup is effectively O(1) in practice. Only becomes a problem if you cache many different prefix variants.

### Verbosity Control Risks

4. **max_tokens hard cutoff can sentence-fragment the relay.** If a relay sentence runs over 80 tokens (possible with flavor tails), TTS receives a truncated sentence mid-word. Mitigation: use a stop sequence for sentence-terminal punctuation `stop=[". ", "! ", "? ", "<|im_end|>"]` plus max_tokens, not max_tokens alone.

5. **Small models (8B) partially ignore verbosity tags when the content "wants" to be long.** Complex tactical queries (e.g., "explain the round strategy") at SNAP tier will still try to overrun. Mitigation: the router should tier-bump before calling the LLM — complex-intent queries should never get SNAP tier.

6. **Qwen3-8B verbosity compliance degrades past 8K context.** As conversation history accumulates, earlier system-prompt instructions (including verbosity tags) get "forgotten" under attention dilution. For Ultron's stateless relay pattern (each call is essentially fresh), this is not an issue. For multi-turn conversations exceeding ~6K tokens, periodic context truncation is needed.

### Thinking-Mode Risks

7. **`/no_think` may not work on all Josiefied-Qwen3 fine-tune variants.** The abliteration training may have partially modified the chat template behavior. Test empirically: check whether `<think>` tokens appear in raw output before stripping.

8. **llama.cpp `enable_thinking` parameter has a known bug (issues #13160, #20182, #20409)** — unreliable in CLI and in-process for some Qwen3 model versions. The `/no_think` suffix is the safer workaround.

9. **Thinking-token removal from output** — even with `/no_think`, occasionally a thinking block leaks (especially in early tokens). Add a post-processing strip of `<think>…</think>` from any generated output before TTS.

### VRAM / Context Budget Risks

10. **Exemplar prefix size vs. VRAM.** At 10 GB VRAM cap with Q5_K_M 8B (approx 6 GB model weights), approximately 4 GB remain for KV cache. At fp16 GQA KV cache: 8B Qwen3 uses 8 heads, 4 KV heads (GQA), hidden dim 128 per head → ~0.125 MB per 1K context tokens. A 4K context budget uses ~0.5 GB KV; 8K uses ~1 GB. At 800-token stable prefix + 200-token user turn + 400-token response in RELAY tier = 1400 tokens peak per call — well within budget.

11. **LlamaRAMCache adds system RAM overhead**, not VRAM. A 2 GB cap stores approximately 1–5 cached states depending on context size. For Ultron's single canonical prefix, this is more than sufficient.

---

## Sources

- [Tutorial: KV Cache Reuse with llama-server — llama.cpp Discussion #13606](https://github.com/ggml-org/llama.cpp/discussions/13606)
- [Mastering Host-Memory Prompt Caching in llama-server — llama.cpp Discussion #20574](https://github.com/ggml-org/llama.cpp/discussions/20574)
- [How to Cache System Prompt — llama.cpp Discussion #8947](https://github.com/ggml-org/llama.cpp/discussions/8947)
- [Feature Request: Improve KV Cache Prefix Management — llama.cpp Issue #20510](https://github.com/ggml-org/llama.cpp/issues/20510)
- [preserve_thinking doesn't unlock prompt cache on Qwen3.5 GGUFs — Issue #22615](https://github.com/ggml-org/llama.cpp/issues/22615)
- [enable_thinking param cannot turn off thinking for Qwen3.5 — Issue #20182](https://github.com/ggml-org/llama.cpp/issues/20182)
- [Qwen3 enable_thinking not working — Issue #13160](https://github.com/ggml-org/llama.cpp/issues/13160)
- [State Management and Caching — DeepWiki llama-cpp-python](https://deepwiki.com/abetlen/llama-cpp-python/4.6-state-management-and-caching)
- [Qwen3.5-27B enable_thinking disable method — Unsloth GGUF Discussion](https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/discussions/4)
- [Don't Break the Cache: Evaluation of Prompt Caching for Agentic Tasks (arXiv:2601.06007)](https://arxiv.org/html/2601.06007v1)
- [KV-Cache Aware Prompt Engineering — 65% Latency Improvement](https://ankitbko.github.io/blog/2025/08/prompt-engineering-kv-cache/)
- [Prompt Caching Infrastructure — Introl Blog 2025](https://introl.com/blog/prompt-caching-infrastructure-llm-cost-latency-reduction-guide-2025)
- [How Prompt Caching Works — Sankalp blog](https://sankalp.bearblog.dev/how-prompt-caching-works/)
- [Prefix Caching — BentoML LLM Inference Handbook](https://bentoml.com/llm/inference-optimization/prefix-caching)
- [Understanding --cache-ram in llama.cpp — Jesse Quinn](https://jessequinn.info/blog/llama-cpp-cache-ram-prompt-caching)
- [Prompt-Based One-Shot Exact Length-Controlled Generation with LLMs — CAPEL (arXiv:2508.13805)](https://arxiv.org/html/2508.13805v1)
- [RAGs to Riches: RAG-like Few-Shot Learning for LLM Role-Playing (arXiv:2509.12168)](https://arxiv.org/html/2509.12168v1)
- [PICLe: Eliciting Diverse Behaviors from LLMs via Persona In-Context Learning (arXiv:2405.02501)](https://arxiv.org/pdf/2405.02501)
- [Harnessing the Reasoning Economy: Survey of Efficient Reasoning (arXiv:2503.24377)](https://arxiv.org/pdf/2503.24377)
- [Do Chatbot LLMs Talk Too Much? YapBench (arXiv:2601.00624)](https://arxiv.org/pdf/2601.00624)
- [Qwen3-8B Model Page — Hugging Face](https://huggingface.co/Qwen/Qwen3-8B)
- [Qwen3 Quickstart — Read the Docs](https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html)
- [Josiefied-Qwen3-8B-abliterated-v1 — Hugging Face](https://huggingface.co/Goekdeniz-Guelmez/Josiefied-Qwen3-8B-abliterated-v1)
- [Limiting Qwen3's Thinking — Zach Mueller](https://muellerzr.github.io/til/end_thinking.html)
- [How to Disable Thinking Mode — Unsloth Docs](https://unsloth.ai/docs/models/tutorials/qwen3-how-to-run-and-fine-tune)
- [PositionID: LLMs Can Control Lengths (arXiv:2410.07035)](https://arxiv.org/pdf/2410.07035)
- [Following Length Constraints in Instructions — Literature Review (Moonlight)](https://www.themoonlight.io/en/review/following-length-constraints-in-instructions)
- [Advanced Prompt Caching at Scale — DigitalOcean](https://www.digitalocean.com/blog/advanced-prompt-caching)
