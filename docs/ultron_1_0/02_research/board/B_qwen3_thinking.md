# Qwen3 Thinking-Mode Best Practices: When It Helps vs. Hurts, Sampling, Parsing, Budgets, and llama.cpp/llama-cpp-python Integration

Research date: 2026-06-20. Model family: Qwen3-8B (Josiefied abliterated Q5_K_M GGUF).
Platform: Windows, RTX 4070 Ti 12GB, llama-cpp-python 0.3.22, in-process.

---

## TL;DR Recommendation for Ultron 1.0

**Default to NO-THINK for all Ultron relay + social paths; use THINK only for on-demand "analyze" / complex player-question paths.**

- Voice latency is the hard constraint. Thinking mode on 8B at ~50 tok/s adds 500–3000 tokens of internal chain-of-thought = 10–60 seconds of silent "dead time" before the first TTS word. That kills the relay persona entirely.
- Use `/no_think` in the system prompt or as a per-turn suffix for every relay, snap, social, and concise-reply prompt.
- Reserve `enable_thinking=True` (or `/think` prefix) for an explicit "think hard" user command or a complex analytical question that the user has flagged as non-time-critical.
- At the llama.cpp / llama-cpp-python server level: start with `--reasoning off` (builds >= b8322) or `--reasoning-budget 0` for zero-think default; expose a second slot or a per-call override only for the "think hard" path.
- Sampling differs between modes — do not mix them. See exact params below.
- Never strip `<think>` tags with a simple regex at `temp=1.0`; that causes content leakage. Use the token-ID split or the `reasoning_content` field from the llama.cpp server's `--reasoning-format deepseek`.
- Presence penalty 1.5 is the primary guard against infinite repetition loops inside `<think>` blocks.

---

## Findings

### 1. What Thinking Mode Is and Why It Exists

Qwen3 (April 2025 release, technical report arXiv:2505.09388) introduced a *unified* hybrid model that can operate in two modes within the same GGUF:

- **Thinking mode** (`enable_thinking=True`): The model generates a full chain-of-thought reasoning trace inside `<think>...</think>` before emitting its final answer. The trace is not shown to the user unless explicitly parsed out.
- **Non-thinking mode** (`enable_thinking=False`): No reasoning trace is emitted; the model behaves like a standard instruction-tuned LLM (analogous to Qwen2.5-Instruct).

The hybrid architecture means a single GGUF load handles both paths. The mode is selected at the *chat template* level, not at the model weight level — important for our in-process llama-cpp-python setup.

The Qwen team's design intent: "users control how much thinking the model performs based on the task at hand," with a "thinking budget mechanism allowing users to allocate computational resources adaptively."

**July 2025 variants**: Qwen released two split variants — `Qwen3-Thinking-2507` (thinking-only, always `<think>`, max 32768 output tokens) and `Qwen3-Instruct-2507` (non-thinking-only, no think tags). Our model is the original April 2025 8B hybrid; it supports both modes.

---

### 2. When Thinking Helps vs. Hurts

#### Thinking mode HELPS for:
- Multi-step math and logic puzzles where the first-guess answer is usually wrong
- Debugging / code reasoning (identify root cause, trace execution)
- Structured planning tasks (e.g., "what strategy should we run given X setup?")
- Adversarial review / fact-checking (the model can reason about its own confidence)
- Synthesis tasks over long documents
- Any task where the user will wait minutes and wants high accuracy

Benchmark context: enabling thinking on 8B raises accuracy from ~55% to ~62.5% on hard STEM benchmarks (LiveCodeBench), but at a 4× wall-time and 10× token-count cost.

#### Thinking mode HURTS for:
- **Real-time voice relay** — 10–60s dead time = catastrophic for gaming
- Short factual lookups: "What floor is the spike on?" — thinking adds zero accuracy, all cost
- Sentiment / social responses: compliments, taunts, "yes/no" — the correct answer is already in the non-thinking distribution
- Direct conversational commands: "tell my team we're pushing A" — deterministic relay, no reasoning needed
- Structured JSON / snap output: thinking mode occasionally leaks reasoning into the final JSON, breaking parsers
- Any sub-2-second SLA (relay, TTS pipelining)

**Practical latency data on similar hardware (~RTX 4070 at Q4_K_M)**:
- Token generation speed: ~52 tok/s (same for think and no-think modes — speed does not change, volume does)
- Non-thinking response: 50–200 tokens = ~1–4 seconds
- Thinking response: 500–3000 tokens internal + 50–200 final = ~12–60 seconds total before first response token

For Ultron relay this is a non-starter. The snap/relay paths must bypass thinking entirely.

---

### 3. Sampling Parameters (Mode-Specific — Do Not Mix)

#### Thinking Mode
```
temperature:       0.6
top_p:             0.95
top_k:             20
min_p:             0.0
presence_penalty:  0.0  (or 1.5 if repetition loops are observed)
```

**Critical**: DO NOT use greedy decoding (temperature=0) with thinking mode. Greedy decoding causes performance degradation and "endless repetitions" inside the `<think>` block. This is an official Qwen3 warning, confirmed by multiple independent reporters.

#### Non-Thinking Mode
```
temperature:       0.7
top_p:             0.8
top_k:             20
min_p:             0.0
presence_penalty:  1.5  (recommended for conversational paths)
```

The non-thinking mode uses slightly higher temperature and lower top_p; presence_penalty 1.5 guards against token-level repetition on the direct output path.

#### Why the parameters differ
In thinking mode, the model samples from a broad distribution while reasoning (high top_p=0.95 allows exploratory chains) but needs moderate temperature (0.6) to stay coherent. In non-thinking mode, lower top_p=0.8 keeps responses more focused and direct; the higher presence penalty compensates for shorter context with no reasoning to anchor the continuation.

---

### 4. Soft Switches: `/think` and `/no_think`

When the model is loaded with `enable_thinking=True` (the default for hybrid Qwen3), users or the system prompt can control per-turn thinking via inline commands:

- Add `/no_think` to the user message or system prompt to disable thinking for that turn
- Add `/think` to re-enable it in a subsequent turn
- The model follows the **most recent** `/think` or `/no_think` it has seen in context

Examples:
```
User: Tell my team we're going A. /no_think
User: What's the best counter to a Cypher tripwire at B site? /think
```

**For Ultron 1.0**: The system prompt for all relay/social/snap paths should include `/no_think` at the end. The `think` path can be triggered by a specific intent gate keyword.

**Limitation**: When `enable_thinking=True` is set, the model still emits `<think></think>` block wrappers even when `/no_think` is active — the content inside will be empty or minimal, but the tokens are still present. When `enable_thinking=False` is set at the template level, no think tags appear at all.

---

### 5. Think Tag Parsing — Correct Methods

#### Method 1: Token-ID split (HuggingFace transformers path)
The closing `</think>` tag is a special token with ID **151668**.

```python
try:
    index = len(output_ids) - output_ids[::-1].index(151668)
    thinking_content = tokenizer.decode(output_ids[:index], skip_special_tokens=True)
    content = tokenizer.decode(output_ids[index:], skip_special_tokens=True)
except ValueError:
    # No </think> found — entire output is content
    thinking_content = ""
    content = tokenizer.decode(output_ids, skip_special_tokens=True)
```

#### Method 2: llama.cpp server `reasoning_content` field
When llama-server is run with `--reasoning-format deepseek`, the `/v1/chat/completions` response separates thinking from output:
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "reasoning_content": "...chain of thought...",
      "content": "...final answer..."
    }
  }]
}
```

Access via: `response.choices[0].message.reasoning_content`

#### Method 3: Streaming regex parse (client-side fallback)
For llama-cpp-python in-process (no server), stream the output and track state:
```python
in_think = False
think_buf = []
content_buf = []
for token in stream:
    if "<think>" in token:
        in_think = True
    elif "</think>" in token:
        in_think = False
    elif in_think:
        think_buf.append(token)
    else:
        content_buf.append(token)
thinking = "".join(think_buf)
content = "".join(content_buf)
```

**Warning**: This regex approach breaks if the model emits reasoning content *outside* of `<think>` tags — which has been reported at temperature=1.0. Keep temperature at 0.6 to minimize this.

**Another warning**: The chat template automatically adds the opening `<think>` tag when `enable_thinking=True`. The model only needs to emit the closing `</think>`. Some frameworks fail to add the opening tag, causing malformed output where the model embeds raw reasoning without delimiters.

---

### 6. Token Budgets for Thinking

#### Why budgets matter
The `</think>` closing token is **probabilistic, not guaranteed**. Empirical data: on LiveCodeBench, 17.4% of thinking-mode outputs had truncated thinking (no `</think>` before token budget ran out), and 84% of those showed repetition rates above 30%. Without a budget cap, a stuck model will exhaust `max_new_tokens` and return zero usable content — just an incomplete reasoning chain.

#### Official guidance
- `thinking_budget` should not be set below **1024 tokens** — too short for meaningful reasoning improvement
- Default is the model's max chain-of-thought length (effectively unlimited)
- For time-constrained use, the official API example uses budgets like 50 tokens (very short, demo-only) up to 38,912 for competition-level math
- Budget=0 forces an immediate `</think>` on the first decode step (useful to disable thinking dynamically when `enable_thinking=False` is not available at template level)

#### How llama.cpp enforces it
The `--reasoning-budget N` server flag:
- `-1`: unlimited
- `0`: forces immediate `</think>` (model sees reasoning block opened and immediately closed)
- `N>0`: hard cap; when N tokens generated inside `<think>`, the server forces the `</think>` token regardless of model distribution

This "forced token injection" is the correct mechanism — it assigns a huge logit value to the `</think>` token sequence when budget is exhausted. Client-side truncation does NOT work reliably because it leaves the model mid-thought with no answer.

**For Ultron 1.0**: If thinking is enabled for the "think hard" path, use `--reasoning-budget 1024` as the default cap on that path. For relay/snap paths, `--reasoning-budget 0` or `enable_thinking=False`.

---

### 7. Hybrid Control in llama.cpp / llama-cpp-python 0.3.22

#### Server-level flags (llama-server / llama-cpp-python server mode)

```bash
# Start with thinking OFF globally (builds >= b8322)
llama-server -m model.gguf --reasoning off --reasoning-format deepseek -ngl 99

# Start with thinking ON, specific budget
llama-server -m model.gguf --reasoning on --reasoning-budget 2048 --reasoning-format deepseek -ngl 99

# Old method (deprecated in b8322, emits deprecation warning):
llama-server --chat-template-kwargs '{"enable_thinking": false}'
```

The `--reasoning-format` options:
- `none`: `<think>` content stays raw in `message.content` (client must parse)
- `deepseek`: Think content split into `message.reasoning_content`, final answer in `message.content`
- `deepseek-legacy`: Tags kept in `content` AND `reasoning_content` populated
- `auto`: Detect from chat template (default)

**Recommended for Ultron 1.0**: `--reasoning-format deepseek` + `--reasoning off` at startup for the relay server, with `--reasoning-budget 0` as belt-and-suspenders. This surfaces a clean `reasoning_content` field (empty when off) and `content` field (the actual reply).

#### In-process llama-cpp-python (our actual path)

llama-cpp-python 0.3.22 uses the underlying llama.cpp build. The Python bindings expose chat_template_kwargs at model load time:

```python
from llama_cpp import Llama

llm = Llama(
    model_path="path/to/Qwen3-8B-Q5_K_M.gguf",
    n_gpu_layers=-1,        # full offload to RTX 4070 Ti
    n_ctx=8192,
    chat_format="chatml",
    chat_template_kwargs={"enable_thinking": False},  # default OFF
    verbose=False,
)
```

For per-call toggle (without reloading), use the soft switch in the messages:
```python
response = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": "You are Ultron. /no_think"},
        {"role": "user", "content": "tell my team we're going A"},
    ],
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    presence_penalty=1.5,
)
```

For the think path:
```python
response = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": "You are Ultron."},
        {"role": "user", "content": "analyze the enemy comp and suggest a counter strategy /think"},
    ],
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    min_p=0.0,
    max_tokens=4096,
)
```

#### Per-request control: current state (June 2026)

The `chat_template_kwargs` in the request body was **deprecated in llama.cpp >= b8322** in favor of the server-startup `--reasoning on/off` flag. As of June 2026, there is no clean per-request toggle via the OpenAI-compatible `/v1/chat/completions` endpoint without running two server instances (one with reasoning on, one off).

**Workaround for in-process llama-cpp-python**: The soft switch (`/no_think` / `/think` in the message text) still works reliably because it operates at the chat template level (Jinja2), not at the server flag level. This is the recommended approach for our single in-process Llama instance.

#### Prompt cache note

`preserve_thinking=True` serializes reasoning content across turns (adds reasoning to chat history). This is **NOT** the same as fixing the prompt cache bug on Qwen3.5+ architectures. The hybrid-recurrent KV cache remains inert regardless of `preserve_thinking`. Do not use `preserve_thinking=True` for relay paths — it would balloon context with reasoning tokens across turns.

---

### 8. Multi-Turn Conversation Handling

**Rule**: Strip thinking content from chat history. Never include `<think>...</think>` blocks in the `assistant` message when building subsequent turns.

The Jinja2 chat template handles this automatically when used through `apply_chat_template`. When constructing messages manually (as in llama-cpp-python with custom message dicts), only include the final answer text in the `assistant` turn.

```python
# CORRECT: strip thinking from history
history.append({
    "role": "assistant",
    "content": response_without_thinking  # NOT the full output with <think> block
})

# WRONG: including thinking in history wastes context and confuses subsequent turns
history.append({
    "role": "assistant",
    "content": full_output_including_think_block  # BAD
})
```

For Ultron 1.0 with the relay model, conversation history is typically single-turn (stateless per utterance), so this is mainly relevant for any multi-turn analytical path.

---

### 9. Common Mistakes That Garble Qwen3 Output

#### Mistake 1: Greedy decoding (temperature=0) with thinking mode
**Effect**: Endless repetition inside `<think>` blocks, never emitting `</think>`, zero usable output. This is confirmed and documented by Qwen team.
**Fix**: Always use temperature >= 0.6 for thinking mode.

#### Mistake 2: Wrong sampling params between modes
**Effect**: Non-thinking mode with thinking-mode params (temp=0.6, top_p=0.95) produces slightly over-confident, verbose direct answers. Thinking mode with non-thinking params (temp=0.7, top_p=0.8) can produce less coherent reasoning chains.
**Fix**: Apply the correct param set per mode. Use `/no_think` to ensure mode is what you expect.

#### Mistake 3: Including thinking content in chat history
**Effect**: Context bloat, confuses subsequent turns (model sees its own reasoning as prior output, may reference or continue it), reduces effective context for the actual conversation.
**Fix**: Strip `<think>...</think>` before appending to history.

#### Mistake 4: Regex-stripping think tags client-side without handling empty think blocks
**Effect**: When `/no_think` is active but `enable_thinking=True` is set at template level, the model emits `<think>\n</think>` (empty block). Naive regexes that look for content between tags find nothing and pass the wrong string.
**Fix**: Use the token-ID split (Method 1 above) or `reasoning_content` field (Method 2). If regex, handle empty blocks: `re.sub(r'<think>[\s\S]*?</think>', '', text)`.

#### Mistake 5: Using `enable_thinking=False` with `chat_template_kwargs` in llama.cpp >= b8322
**Effect**: Deprecation warning; behavior may be silently ignored depending on build.
**Fix**: Use `--reasoning off` at server start, or soft switch `/no_think` in messages.

#### Mistake 6: Setting `--reasoning-budget` very low (under 256) without forcing `</think>`
**Effect**: Model is cut off mid-reasoning, `</think>` may not be emitted, and the final answer tokens are appended directly to incomplete reasoning — garbled output.
**Fix**: Use `--reasoning-budget 0` to disable entirely, or set budget >= 1024 for meaningful reasoning. The llama.cpp server forces the `</think>` token when budget is hit, but this requires a build that implements `ThinkingTokenBudgetLogitsProcessor`-equivalent logic.

#### Mistake 7: Absence of presence_penalty in thinking mode with repetition tendency
**Effect**: The model enters a repetition loop inside `<think>` — repeating phrases like "Let me think... Let me think..." — eventually exhausting the token budget and returning no answer.
**Fix**: Add `presence_penalty=1.5`. Note: this slightly degrades quality and may cause language mixing at values > 2.0. Use sparingly.

#### Mistake 8: Using `--reasoning-format none` but expecting clean output
**Effect**: Think tags remain in `message.content`, passed raw to TTS/relay. Kokoro would speak the internal reasoning aloud.
**Fix**: Use `--reasoning-format deepseek` to get split fields, or parse client-side before passing to TTS.

#### Mistake 9: Assuming `enable_thinking=False` is equivalent to `/no_think`
**Effect**: `enable_thinking=False` at template level prevents the opening `<think>` from being injected; `/no_think` in the prompt is a soft instruction that the model can technically override (it usually doesn't, but abliterated models may behave differently). The hard template-level switch is more reliable.

#### Mistake 10: Not checking if `</think>` was emitted before parsing final answer
**Effect**: If the model truncates before emitting `</think>` (budget exceeded, max_tokens hit), the "content" parsed after the non-existent closing tag will be empty or the split logic will return wrong indices.
**Fix**: Always wrap token-ID search in try/except; fall back to treating the whole output as content.

---

### 10. Our Specific GGUF: Josiefied-Qwen3-8B-Abliterated Q5_K_M

- **Abliteration** removes refusal-related weights but does not modify the chat template or thinking mode machinery. The `/no_think` soft switch and `enable_thinking` parameter should work identically to the base model.
- **Q5_K_M quantization**: At 12GB VRAM (10GB design cap), Q5_K_M for 8B uses approximately 5.5–6GB for weights, leaving 4–4.5GB for KV cache. At 8192 context this is comfortable; at 32768 context it may exceed the 10GB cap. Recommended context for relay path: 4096 tokens. For the think-hard path: 8192 tokens max.
- **Speed estimate**: ~50–60 tok/s on RTX 4070 Ti with full offload (-ngl -1). Thinking mode thinking tokens cost the same per-token; you just generate more of them. A 1000-token think block = ~20 seconds.
- **Anticheat safety**: The thinking mode toggle operates entirely at the chat template / sampling level — no additional imports, no network, no OS hooks. The relay/snap path with `/no_think` and direct in-process llama-cpp-python inference is anticheat-safe under the existing architecture.

---

### 11. llama.cpp Server vs. In-Process in llama-cpp-python 0.3.22

llama-cpp-python 0.3.22 exposes two usage patterns:

**Pattern A (in-process, our current path)**:
```python
from llama_cpp import Llama
llm = Llama(model_path=..., n_gpu_layers=-1, ...)
response = llm.create_chat_completion(messages=..., temperature=..., ...)
```
- `reasoning_content` field: NOT available in this path (no server involved)
- Think tag separation: must be done client-side (regex or token-ID)
- Per-call thinking toggle: soft switch (`/no_think`) in messages, or reload with different `chat_template_kwargs`
- `--reasoning` flag: not applicable (that's a server CLI flag)

**Pattern B (embedded server)**:
```python
from llama_cpp.server.app import create_app
# or: python -m llama_cpp.server --model ... --reasoning off
```
- Full llama-server feature set including `--reasoning-format deepseek`
- `reasoning_content` field available in response
- Per-request `reasoning_format` override available

**Recommendation for Ultron 1.0**: The relay/LLM pipeline is in-process (Pattern A). Use soft switch + client-side regex parse. Keep thinking disabled by default via `chat_template_kwargs={"enable_thinking": False}` at model load. For the "think hard" path, pass `/think` in the user message and parse `<think>...</think>` out before TTS.

---

## Concrete Techniques/Params We Should Adopt

### A. Model Load (all relay paths)
```python
llm = Llama(
    model_path="path/Qwen3-8B-abliterated-Q5_K_M.gguf",
    n_gpu_layers=-1,          # full RTX 4070 Ti offload
    n_ctx=4096,               # relay path: 4K sufficient, anticheat-lean
    chat_format="chatml",
    chat_template_kwargs={"enable_thinking": False},  # hard-disable by default
    verbose=False,
)
```

### B. Relay / Snap / Social Call (no_think path)
```python
response = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": RELAY_SYSTEM_PROMPT + "\n/no_think"},
        {"role": "user",   "content": user_utterance},
    ],
    temperature=0.7,
    top_p=0.8,
    top_k=20,
    min_p=0.0,
    presence_penalty=1.5,
    max_tokens=256,           # relay answers must be short
    stream=False,
)
content = response["choices"][0]["message"]["content"]
# No think parsing needed when enable_thinking=False at load
```

### C. Think-Hard Path (explicit "analyze" intent, user-flagged non-urgent)
```python
llm_think = Llama(
    # Either reload with enable_thinking=True, or use same instance with /think soft switch
    model_path="path/Qwen3-8B-abliterated-Q5_K_M.gguf",
    n_gpu_layers=-1,
    n_ctx=8192,
    chat_format="chatml",
    chat_template_kwargs={"enable_thinking": True},
    verbose=False,
)

response = llm_think.create_chat_completion(
    messages=[
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user",   "content": user_question + " /think"},
    ],
    temperature=0.6,
    top_p=0.95,
    top_k=20,
    min_p=0.0,
    presence_penalty=0.0,     # 0 initially; set to 1.5 if repetition observed
    max_tokens=4096,
)
full_output = response["choices"][0]["message"]["content"]

# Parse out thinking content (regex method for in-process)
import re
content = re.sub(r'<think>[\s\S]*?</think>', '', full_output).strip()
# Or use token-ID method if output_ids accessible
```

### D. System Prompt Pattern
For relay/snap: end the system prompt with `/no_think` on its own line.
```
You are Ultron, a cold superior AI machine operating as a Valorant teammate relay...
[rest of system prompt]
/no_think
```

This ensures that even if `chat_template_kwargs={"enable_thinking": True}` were ever set, the soft switch overrides it.

### E. Safety Guard Against Think-Tag Leakage to TTS
Before passing any LLM output to Kokoro TTS:
```python
import re
def strip_think_tags(text: str) -> str:
    """Remove any residual think blocks before TTS. Fail-safe."""
    return re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
```
This is belt-and-suspenders for the no_think path in case of edge-case leakage.

### F. Repetition Guard
If any relay/snap call returns a response longer than 3× the expected length, or if the response contains repeated 5-gram sequences (detectable with a simple overlap check), treat it as a repetition failure and:
1. Re-call with `presence_penalty=1.5`
2. Or fall back to the deterministic snap pool

---

## Risks/Caveats for Our Constraints

### Risk 1: In-process llama-cpp-python has no clean per-request reasoning toggle post-b8322
The server's `--reasoning on/off` flag cannot be changed without restart. For our in-process Pattern A setup, we rely on soft switches. This is reliable for the base model but **abliteration may alter compliance** — the abliterated model occasionally ignores soft instructions on the original base (refusals were the main target of abliteration, thinking toggle is different). Verify empirically that `/no_think` reliably suppresses think blocks on the specific Josiefied GGUF.

### Risk 2: Empty `<think></think>` blocks add latency even when /no_think is active
When `enable_thinking=True` at template level but `/no_think` is used as soft switch, the model still emits an empty `<think>\n</think>` preamble (~10–20 tokens = ~0.2–0.4 seconds). For a relay with < 1 second SLA, this matters. Mitigation: use `enable_thinking=False` at load time to eliminate the preamble entirely.

### Risk 3: VRAM headroom for KV cache at context lengths
At Q5_K_M the weights use ~5.5GB. At 4096 context + 8B architecture, KV cache adds ~1.5–2GB = ~7.5GB total. Well within 10GB. At 8192 context (think path): ~9GB. At 16384 context: would exceed 10GB. Keep the think path at 8192 max.

### Risk 4: Abliterated model + thinking mode may produce unconstrained reasoning
Abliteration removes safety-related suppression. In thinking mode, the internal chain-of-thought is unconstrained. This is fine for our use case (no safety concern in Valorant relay context) but means the thinking content should never be piped anywhere externally.

### Risk 5: Infinite repetition loop risk in thinking mode
As documented, Qwen3.5 series (and to a lesser extent base Qwen3-8B) can enter thinking-mode repetition loops. Primary mitigations: temperature=0.6 (not 0 or 1.0), presence_penalty=1.5 if loops observed, and a timeout/max_tokens cap with fallback logic. The 8B model is somewhat less prone than the MoE variants (35B-A3B, 122B-A10B) based on reported data, but the risk is non-zero.

### Risk 6: `--reasoning-budget` forced-`</think>` behavior is llama.cpp server-only
The elegant "force `</think>` when budget exceeded" mechanism is implemented in llama-server as a logits processor. In in-process llama-cpp-python, there is no equivalent — if `max_tokens` is hit inside a thinking block, the output is truncated mid-thought. Mitigation: set a `max_tokens` cap large enough that budget runs out before truncation, and use the regex parse with `try/except` on the closing tag.

### Risk 7: `preserve_thinking=True` is not a prompt cache fix
For multi-turn paths that might use `preserve_thinking`, note that this does NOT fix the Qwen3.5+ hybrid-recurrent cache bug — prompt cache remains inert. Do not expect cache speedup on repeated relay calls.

### Risk 8: Josiefied model is Q5_K_M, not an official Qwen3 GGUF
Josiefied abliterated quantized models may have slightly different token distributions due to quantization + abliteration interaction. The documented sampling params (temp=0.6/0.7) are for official GGUFs. Empirically verify that the repetition behavior is acceptable; if loops occur more than expected, raise presence_penalty to 1.5 even for the thinking path.

---

## Sources

- Qwen3 official blog post (thinking + sampling details): https://qwenlm.github.io/blog/qwen3/
- Qwen3 ReadTheDocs quickstart (sampling params, think tag parsing, code examples): https://qwen.readthedocs.io/en/latest/getting_started/quickstart.html
- Qwen3 ReadTheDocs llama.cpp guide (server flags, YaRN, reasoning format): https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html
- Qwen3 GitHub repository (model card, enable_thinking, soft switches): https://github.com/QwenLM/Qwen3
- Qwen3-8B HuggingFace model card (token ID 151668, sampling params, YaRN): https://huggingface.co/Qwen/Qwen3-8B
- Qwen3-4B HuggingFace model card (detailed sampling + common mistakes): https://huggingface.co/Qwen/Qwen3-4B
- Qwen3-32B HuggingFace model card (multi-turn handling, soft switch examples): https://huggingface.co/Qwen/Qwen3-32B
- Qwen3 Technical Report (arXiv:2505.09388): https://arxiv.org/abs/2505.09388
- Alibaba Cloud deep thinking docs (thinking_budget API, token consumption, API examples): https://www.alibabacloud.com/help/en/model-studio/deep-thinking
- llama.cpp server README (--reasoning flags, reasoning-format, reasoning_content field, reasoning-budget): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- llama.cpp discussion: per-request reasoning toggle for hybrid models (current state, deprecation of chat_template_kwargs): https://github.com/ggml-org/llama.cpp/discussions/23351
- llama.cpp issue #20182: enable_thinking param cannot turn off thinking for Qwen3.5 (bug, workarounds): https://github.com/ggml-org/llama.cpp/issues/20182
- llama.cpp issue #22615: preserve_thinking vs prompt cache bug (independent issues): https://github.com/ggml-org/llama.cpp/issues/22615
- llama.cpp issue #13189: persistent think tags despite enable_thinking=false and --reasoning-format none: https://github.com/ggml-org/llama.cpp/issues/13189
- Unsloth Qwen3.5-27B discussion: working method to disable thinking in llama.cpp: https://huggingface.co/unsloth/Qwen3.5-27B-GGUF/discussions/4
- Qwen3.6 issue #145: infinite loop in reasoning with reference sampling params: https://github.com/QwenLM/Qwen3.6/issues/145
- Moonglade blog — "Why Qwen3.5 Falls Into Infinite Thinking — and How to Fix It" (root cause, ThinkingTokenBudgetLogitsProcessor, forced </think> mechanism): https://lyn.one/reasoning-control-flow
- llama-cpp-python server docs (chat_template_kwargs, enable_thinking config): https://llama-cpp-python.readthedocs.io/en/latest/server/
- llama-cpp-python discussion #2011: getting think content via streaming in Python: https://github.com/abetlen/llama-cpp-python/discussions/2011
- LLM Hardware guide — Qwen3 hardware requirements and speed benchmarks: https://llmhardware.io/guides/qwen3-hardware-requirements
- Conflicting sampling recommendations discussion (unsloth Qwen3-VL): https://huggingface.co/unsloth/Qwen3-VL-30B-A3B-Thinking-GGUF/discussions/1
- llama.cpp PR #11607 — reasoning_content return in server for DeepSeek R1 / Qwen: https://app.semanticdiff.com/gh/ggml-org/llama.cpp/pull/11607/overview
