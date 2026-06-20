# A7: LLM serving, device profiles, prompts & response style

## Overview

The LLM serving layer is built around `llama-cpp-python` running a GGUF-format model in-process (default) or against a separately-launched `llama-cpp-server` over an OpenAI-compatible HTTP API. The voice pipeline currently targets 3B–4B parameter Qwen3.5 and Llama-3.2 abliterated models. A `ModeLLMRouter` maps agent-loop modes (ACT, PLAN, GAMING, CODING_*) to preset names and drives hot-swaps. Two generation surfaces are exposed: a streaming iterator (`generate_stream`) and a blocking string (`generate`). An isolated bypass (`generate_isolated`) is used for background structured tasks. Prompt construction assembles [system → history → user] arrays per-turn with optional RAG injection, skills-block augmentation, brevity-style hints, and temperament hints. Persona is sourced from either `config.yaml:llm.system_prompt` (legacy), or the `PersonaLoader` workspace files (SOUL.md + IDENTITY.md + USER.md, hot-reload per turn). Gaming / relay calls override the per-turn system prompt to the Ultron persona. Thinking-mode (`<think>...</think>` blocks) is handled by token-streaming strippers and a `/no_think` marker appended to Qwen user turns when `enable_thinking=False`.

---

## Files & key symbols (path:line tables)

### `src/kenning/llm/inference.py` — Core engine

| Symbol | Line | Role |
|---|---|---|
| `_DEVICE_PROFILES` | 68 | Dict `{gpu: {...}, cpu: {...}}` with the 4 hardware knobs per profile |
| `_INJECTION_MARKERS` | 93 | Tag-style prompt-injection tokens to neutralise in user input |
| `_NL_JAILBREAK_PATTERNS` | 113 | 12 regex patterns for NL jailbreak detection |
| `_HARDENING_PREAMBLE` | 141 | Prepended to user text when NL jailbreak detected (non-severe) |
| `_GREETING_RE` / `_SHORT_ACK_RE` | 162/170 | Gates for skipping RAG on short conversational turns |
| `_FACTUAL_STEMS` | 177 | Frozenset of stems that allow RAG even on short queries |
| `_BREVITY_HINT_PREFIX_RE` | 203 | Strips `[Style: ...]` prefix before short-query detection |
| `_strip_thinking_blocks(stream)` | 367 | Stream filter: yields tokens with `<think>...</think>` removed; handles split-boundary |
| `strip_thinking_text(text)` | 409 | Blocking equivalent of `_strip_thinking_blocks` for `generate()` |
| `LLMEngine.__init__` | 540 | Two runtimes: `in_process` / `http_server` per `llm.runtime` config |
| `LLMEngine._build_llama(cfg, ...)` | 624 | Constructs fresh `Llama` instance; returns 4-tuple; does NOT mutate self |
| `LLMEngine._resolve_system_prompt()` | 851 | Priority: explicit constructor arg → workspace PersonaLoader → config string |
| `LLMEngine._build_messages(user_message, ...)` | 931 | Assembles `[{role, content}]` list: injection-sanitise → short-query gate → system → history → RAG → user |
| `LLMEngine._retrieve_rag_snippets(...)` | 1245 | Qdrant retrieval with short-query bypass, gaming-mode bypass, multi-pass gate |
| `LLMEngine._format_rag_block(snippets)` | 1319 | Renders retrieved snippets as labelled stale-memory block; optionally compresses |
| `LLMEngine.generate(user_message, ...)` | 1724 | Blocking generation; applies no_think marker + strips thinking; records history |
| `LLMEngine.generate_isolated(system, user, ...)` | 1835 | One-shot call bypassing persona, history, RAG — for background structured tasks |
| `LLMEngine.generate_stream(user_message, ...)` | 1979 | Streaming generator; same flags as `generate`; cancel-aware via `_cancel` Event |
| `LLMEngine._chat_completion_kwargs(...)` | 2149 | Builds `create_chat_completion` kwargs dict including per-call `sampling` overrides |
| `LLMEngine._apply_no_think_marker(messages, ...)` | 2201 | Appends ` /no_think` to last user message when `enable_thinking=False` AND model is Qwen-family |
| `LLMEngine.reload_for_preset(preset, ...)` | 1413 | Hot-swaps GGUF to a named preset; load-new-then-release-old strategy; resets history |
| `LLMEngine.reload_for_device(device, ...)` | 1599 | Hot-switches CPU↔GPU applying `_DEVICE_PROFILES`; keeps same GGUF + n_ctx |
| `LLMEngine.set_current_intent_kind(kind)` | 1366 | Sets per-turn intent for condenser selection in `_build_messages` |
| `LLMEngine.set_temperament_hint(hint)` | 1392 | Sets `[Tone: ...]` directive appended to system prompt for one turn (evolution) |
| `LLMEngine.pop_last_ttft_ms()` | 1966 | Read-and-clear time-to-first-token in ms from the most recent stream |
| `LLMEngine._http_chat_completion(...)` | 2269 | OpenAI-compat HTTP call to llama-cpp-server; returns dict or chunk iterator |

### `src/kenning/llm/mode_router.py` — Preset routing

| Symbol | Line | Role |
|---|---|---|
| `DEFAULT_ROUTES` | 71 | Mapping `Mode → PresetEntry`; ACT/PLAN=qwen3.5-4b; GAMING=llama-3.2-3b-abliterated |
| `PresetEntry` | 41 | Frozen dataclass: preset_name, sampling_overrides, context_window_override, notes |
| `SwapResult` | 95 | Outcome of a swap: target, succeeded, was_already_active, failure_reason, sampling_overrides |
| `ModeLLMRouter.ensure_preset_for(mode)` | 207 | RLock-guarded: probe current preset → no-op or call reloader → fire on_swap |

### `src/kenning/llm/draft_model.py` — Real-model speculative draft

| Symbol | Line | Role |
|---|---|---|
| `make_qwen08b_draft_model(path, num_pred_tokens, n_ctx, n_gpu_layers)` | 83 | Returns `LlamaDraftModel` subclass wrapping a 0.8B Qwen GGUF; greedy sampling; KV-prefix-cache resync |

### `src/kenning/audio/llm_prompts.py` — Prompt aggregate (SINGLE SOURCE OF TRUTH)

| Symbol | Line | Role |
|---|---|---|
| `ULTRON_GAMING_PERSONA` | 48 | System prompt for gaming conversational turns; ~25-word limit; Tony Stark wound rule |
| `ANSWER_PERSONA_CORE` | 82 | Shared Ultron core for the adaptive answer pipeline |
| `ANSWER_MARVEL_RULES` | 97 | Marvel-specific rules block appended for marvel subtype |
| `ANSWER_THINK_RULES` | 113 | Think-and-respond rules block for think_respond subtype |
| `ANSWER_SYSTEM_FOR` | 123 | Dict `{marvel: CORE+MARVEL, think_respond: CORE+THINK}` |

### `src/kenning/audio/_ultron_answer.py` — Adaptive answer pipeline

| Symbol | Line | Role |
|---|---|---|
| `MARVEL_CANON` | 45 | Alias → canonical display map for Marvel gazetteer |
| `THINK_RESPOND_SUFFIX_RE` | 96 | Regex matching trailing "...think and respond" trigger |
| `classify_answer_subtype(command)` | 146 | Returns "marvel" or "think_respond" or None (use generic relay prompt) |
| `extract_answer_slots(command, subtype)` | 172 | Deterministic slot dict: addressee, topic, claim |
| `build_answer_call(command)` | 251 | Returns `(system_prompt, user_prompt, sampling, subtype)` or None |
| `_ANSWER_SAMPLING` | 239 | max_tokens=80, temp=0.85, top_p=0.92, top_k=40, min_p=0.08, repeat_penalty=1.18, stop sequences |
| `is_meta_leak(line)` | 307 | Detects character-break / refusal / scaffold-echo in model output |

### `src/kenning/audio/relay_speech.py` — Relay LLM calls

| Symbol | Line | Role |
|---|---|---|
| `_REPHRASE_PROMPT` | 2081 | ~120-line f-string template: snap vs off-snap register logic, first-person preservation, directive vs self-report, anti-repeat |
| `_RELAY_SAMPLING` | 2507 | max_tokens=56, temp=0.8, top_p=0.92, top_k=40, min_p=0.08, repeat_penalty=1.18 |
| `_RELAY_REPHRASE_SYSTEM` | 2526 | Concise Ultron persona for the relay rephrase call |
| `_build_rephrase_prompt(command, recent_lines)` | 2538 | Renders the rephrase user-turn from a `RelayCommand` |
| `match_thinking_toggle(text)` | 1235 | Returns True/False/None for voice "thinking mode on/off" commands |
| `_THINKING_OFF_RE` / `_THINKING_ON_RE` | 1217/1225 | Strict regexes for thinking-mode toggle commands |
| `match_flavor_toggle(text)` | 1167 | Returns True/False/None for "flavor on/off" voice commands |

### `src/kenning/response_style.py` — Per-call response style hints

| Symbol | Line | Role |
|---|---|---|
| `apply_brevity_hint(user_text)` | 272 | Dispatches in priority: procedural → factual → brief → unchanged |
| `is_procedural_request(user_text)` | 206 | Matches "step by step", "walk me through", etc. |
| `is_factual_question(user_text)` | 222 | Matches "how much", "when did", "what year", etc. |
| `is_brief_question(user_text)` | 238 | Short (<=12 words AND <=80 chars) + no depth markers |
| `_PROCEDURAL_HINT` | 65 | "[Style: respond with detailed numbered steps...]" |
| `_FACTUAL_HINT` | 46 | "[Style: respond with one short sentence containing only the specific fact...]" |
| `_BREVITY_HINT` | 53 | "[Style: respond in 1-3 short sentences...]" |

### `src/kenning/conversational_ack.py` — Filler acknowledgment

| Symbol | Line | Role |
|---|---|---|
| `ConversationalAckSource` | 106 | Shuffled-cycle phrase source for pre-LLM filler acks |
| `is_conversational_ack_eligible(user_text, ...)` | 68 | Gate: >11 chars AND >4 words AND no pending clarification AND not gaming |
| `_CONVERSATIONAL_PHRASES` | 49 | 8-phrase pool: "Mm.", "Right.", "Hm.", "Considering.", etc. |

### `src/kenning/llm/condensers/` — History compression

| Symbol | File | Role |
|---|---|---|
| `select_condenser_for_intent(intent)` | `factory.py:134` | Returns condenser instance per intent kind |
| `_INTENT_KIND_MAP` | `factory.py:86` | Maps "gaming/greeting/ack/conversational" → "noop"; "factual" → "recent"; "coding" → "llm_summarizing" |
| `build_condenser(kind, ...)` | `factory.py:28` | Factory: noop, recent, amortized, observation_masking, llm_summarizing |
| `Condenser.condense(turns, ...)` | `base.py:85` | ABC: receives `(role, content)` tuples, returns `CondenseResult` |

### `src/kenning/llm/cache_aware_chunks.py` — Chunked prompt for HTTP caching

| Symbol | Line | Role |
|---|---|---|
| `ChunkedPrompt` | 116 | Named slots: system, examples, repo_map, readonly_files, chat_files, history, current |
| `to_anthropic_messages(prompt)` | 185 | Serialises with Anthropic `cache_control: {type: ephemeral}` on last cacheable block |
| `to_plain_messages(prompt)` | 248 | Serialises without cache markers for local llama-cpp |

### `src/kenning/config.py` — LLM configuration

| Symbol | Line | Role |
|---|---|---|
| `LLM_PRESETS` | 661 | Dict of 6 preset names to `{model_path, n_ctx, draft_model_path, gpu_layers?}` |
| `LLMConfig` | 810 | Pydantic model: all LLM knobs; `_apply_preset` validator fills preset-derived fields |
| `LLMConfig.default_temperature` | 904 | Default 0.7 |
| `LLMConfig.default_top_p` | 905 | Default 0.9 |
| `LLMConfig.default_max_tokens` | 906 | Default 512 |
| `LLMConfig.default_repeat_penalty` | 907 | Default 1.1 |
| `LLMConfig.n_ctx` | 902 | Default 8192 |
| `LLMConfig.gpu_layers` | 903 | Default -1 (full offload) |
| `LLMConfig.flash_attn` | 909 | Default True |
| `LLMConfig.kv_cache_type` | 910 | Default 8 (q8_0); 1=F16 |
| `LLMConfig.draft_kind` | 890 | `"none"/"pld"/"model"`, default `"none"` |
| `LLMConfig.prefix_cache_ram_bytes` | 939 | Default 0 (disabled; LlamaRAMCache bench showed regression on short prompts) |

### `src/kenning/openclaw_bridge/persona.py` — Workspace persona loader

| Symbol | Line | Role |
|---|---|---|
| `PersonaLoader.get_system_prompt(mode)` | (class) | Returns composed string from IDENTITY.md+SOUL.md+USER.md for "user_facing" mode |
| `PersonaLoader.refresh_if_stale()` | (class) | Compares mtime+size; hot-reloads changed files; called on every `_build_messages` invocation |
| `_MODE_FILES` | 79 | user_facing=(IDENTITY, SOUL, USER); background=(AGENTS only); etc. |

---

## Control/data flow

### 1. Conversation LLM turn (non-relay)

```
orchestrator.run() -> voice capture -> Whisper STT -> user_text
  -> apply_brevity_hint(user_text)          [response_style.py]
  -> _gaming_conversational_prompt()        [→ ULTRON_GAMING_PERSONA or None]
  -> llm.generate_stream(
       augmented_text,
       system_prompt=<gaming persona or None>,
       enable_thinking=False,               [/no_think appended for Qwen]
       gate_verdict=...,
       precomputed_rag_snippets=...,
     )
       │
       ├─> _build_messages(user_message, system_prompt=override_or_none)
       │     ├─ _sanitize_user_input()      [neutralise injection markers / NL jailbreak]
       │     ├─ _is_short_conversational_query() → suppress_memory_context flag
       │     ├─ _resolve_system_prompt()    [PersonaLoader hot-reload OR config string]
       │     ├─ maybe_get_skills_block()    [SkillRegistry per-turn injection]
       │     ├─ temperament_hint append     [evolution service [Tone: ...]]
       │     ├─ _retrieve_rag_snippets()    [Qdrant; skip in gaming/testing mode]
       │     ├─ _format_rag_block()         [stale-memory block; optional compress]
       │     ├─ history block               [memory.recent(N) or deque; optional condenser]
       │     └─ [system, ...history, user_with_rag]
       │
       ├─> _apply_no_think_marker()         [append /no_think if enable_thinking=False AND Qwen model]
       │
       ├─> Llama.create_chat_completion(messages, stream=True, **kwargs)
       │     kwargs: temperature, top_p, max_tokens, repeat_penalty [, per-call sampling overrides]
       │
       └─> _strip_thinking_blocks(raw_stream)
             → yield visible tokens to TTS
             → accumulate full response
             → _record_turn() on completion
```

### 2. Relay (gaming mode — rephrase path)

```
orchestrator dispatches to relay_speech.build_relay_line(command, llm, ...)
  ├─ [deterministic snaps / set-pieces checked first]
  ├─ build_answer_call(command)             [marvel / think_respond adaptive pipeline]
  │     → (system_prompt, user_prompt, sampling, subtype)
  │     → llm.generate_stream(user_prompt, system_prompt=ANSWER_SYSTEM_FOR[subtype],
  │         sampling=_ANSWER_SAMPLING, record_history=False,
  │         suppress_memory_context=True, enable_thinking=False)
  │     → is_meta_leak() gate → discard or accept
  └─ _build_rephrase_prompt(command, recent_lines)  [generic relay]
        → llm.generate_stream(prompt, system_prompt=_RELAY_REPHRASE_SYSTEM,
            sampling=_RELAY_SAMPLING, record_history=False,
            suppress_memory_context=True, enable_thinking=False)
        → post-processing: _strip_artifacts, _cap_sentences(max=2),
          _strip_spurious_vocative, _repair_against_input
```

### 3. Device / preset hot-swap

```
voice command "switch to the GPU/CPU"
  -> orchestrator._maybe_handle_llm_device_switch()
  -> llm.reload_for_device("gpu" or "cpu")
       └─ _DEVICE_PROFILES[target] -> 4 override kwargs
       -> _build_llama(cfg, same model_path, same n_ctx, profile knobs)
       -> release old Llama; assign new; reset history

voice command "switch to the 8B / heretic / josiefied / huihui / 3B"
  -> orchestrator
  -> llm.reload_for_preset(preset_name)
       └─ TOFU digest check + version-exact validation
       -> env override KENNING_LLM_PRESET=preset_name
       -> reload_config() -> _build_llama(new_cfg, None, None, gpu_layers)
       -> release old; assign new; reset history

Mode change (agent-loop)
  -> ModeLLMRouter.ensure_preset_for(mode)
       -> probe active preset -> no-op or reloader(target_preset) -> on_swap callback
```

### 4. Token → TTS pipeline

```
generate_stream yields visible tokens (thinking blocks stripped)
  -> orchestrator accumulates + forwards to TTS (Kokoro/Piper speak_stream)
  -> TTFT recorded via _last_ttft_ms attribute (evolution ring)
  -> on stream completion: _record_turn(bare_user_text, full_response)
```

---

## Key findings

1. **Two runtimes, same surface** — `in_process` (llama-cpp-python directly loads GGUF; default) and `http_server` (OpenAI-compat HTTP to a separately-managed llama-cpp-server). Both expose identical `generate` / `generate_stream` APIs; only the internal plumbing differs. The HTTP path supports `chat_template_kwargs={"enable_thinking": ...}` (server passes it through); the in-process path uses the `/no_think` marker workaround because `chat_template_kwargs` is not accepted by llama-cpp-python 0.3.22.

2. **Thinking mode handling** — Qwen3/Qwen3.5 emit `<think>...</think>` blocks during reasoning. The streaming path strips them in `_strip_thinking_blocks()` (handles split-boundary via hold buffer). The blocking path uses `strip_thinking_text()`. To suppress the block entirely, `enable_thinking=False` appends ` /no_think` to the last user message — but ONLY if `"qwen"` appears in the live model path (guards against the Llama gaming model parroting the marker literally). The voice pipeline typically passes `enable_thinking=False` on relay calls.

3. **Three prompt surfaces in use concurrently**:
   - **Base desktop persona** (SOUL.md → PersonaLoader → `_resolve_system_prompt()`): used for all non-gaming conversational turns; hot-reloads per turn via mtime check.
   - **Gaming / Ultron persona** (`ULTRON_GAMING_PERSONA` from `llm_prompts.py`): injected as `system_prompt=` override on `generate_stream()` whenever gaming mode or the 3B model is active; NEVER uses PersonaLoader / desktop "Kenning" string.
   - **Relay personas** (`_RELAY_REPHRASE_SYSTEM`, `ANSWER_SYSTEM_FOR[subtype]`): injected via `system_prompt=` on relay LLM calls; always explicit, always pinned to Ultron, always `suppress_memory_context=True`.

4. **`_build_messages` is the single prompt construction site** — it handles: injection sanitisation, short-query RAG bypass, skills-block injection, temperament hint append, RAG position (system vs recency), history condensation, and the per-call system_prompt override path (when override is set, ALL the above is skipped and the function returns [system, user] only — the fast relay path depends on this).

5. **The `sampling` dict** is the per-call override mechanism — passed through `_chat_completion_kwargs()` after a whitelist filter. Relay uses `_RELAY_SAMPLING` (max_tokens=56, stop sequences). Answer pipeline uses `_ANSWER_SAMPLING` (max_tokens=80, min_p=0.08). Default conversational uses config-level defaults (max_tokens=512, temp=0.7).

6. **Speculative decoding** has two layers:
   - **llama-cpp-level**: `draft_kind` config knob; `"pld"` = LlamaPromptLookupDecoding (n-gram, default disabled — hit llama_decode -1 bug on 0.3.22); `"model"` = Qwen08BDraftModel (second Llama instance, greedy, KV-prefix-cache resync, also default-off pending live verification).
   - **Orchestrator-level**: "speculative LLM" — starts `generate_stream(record_history=False)` on a background thread DURING the VAD silence wait after the last turn ends; tokens buffered in a Queue; consumed by the main path if user doesn't speak again; invalidated if user starts speaking.

7. **Device profiles** — `_DEVICE_PROFILES` defines exactly 4 knobs per device: `n_gpu_layers`, `flash_attn`, `kv_cache_type`, `n_batch` / `n_ubatch`. GPU profile: full offload (-1), flash_attn=True, kv=q8_0 (type 8), n_batch=512, n_ubatch=512. CPU profile: 0 layers, flash_attn=False, kv=F16 (type 1, mandatory when flash_attn off), n_batch=512, n_ubatch=256. VRAM guard: checks `torch.cuda.is_available()` before GPU reload.

8. **Preset table (`LLM_PRESETS`)** — 6 named presets: `qwen3.5-9b` (n_ctx=8192, no draft), `qwen3.5-4b` (n_ctx=8192, 0.8B draft), `josiefied-qwen3-8b` (n_ctx=8192, no draft), `josiefied-qwen3-4b` (n_ctx=6144, no draft), `gemma-3-4b-abliterated` (n_ctx=4096, 1B draft), `llama-3.2-3b-abliterated` (n_ctx=6144, gpu_layers=0, no draft). Config default as of the current branch: `qwen3.5-4b`.

9. **History compression** — `_INTENT_KIND_MAP` in `condensers/factory.py` maps intent labels to strategies. Gaming/greeting/ack/conversational → NoOp (zero cost). Factual → Recent. Coding → LLMSummarizing. Only consulted when `llm.history_compression.intent_adaptive=True`; the orchestrator sets `llm.set_current_intent_kind(kind)` before each `generate_stream` call.

10. **RAG bypass in gaming** — `_retrieve_rag_snippets()` unconditionally returns `[]` when `is_gaming_mode_active() or is_testing_mode_active()` AND `gaming_mode.barebones_skip_retrieval=True` (default True). This keeps the embedder + cross-encoder off the GPU during matches. The per-turn RAG position (`rag.position: "recency"`) prepends retrieved snippets directly to the user message — empirically +10-20% recall on the 4B vs the legacy "fold into system" position.

11. **Prompt injection defence** — `_sanitize_user_input()` replaces tag-style markers (`[INST]`, `<|im_start|>`, etc.) with `[NEUTRALIZED_TAG]`; strips stray `</think>` to prevent chain-of-thought injection; detects NL jailbreaks via 12 patterns and either prepends `_HARDENING_PREAMBLE` (soft override attempt) or rewrites the user message as a description of an attempt (severe: "respond with exactly X"). Always fail-open (defence never breaks the voice path).

12. **`generate_isolated()`** — completely bypasses persona/history/RAG; called by the background summarizer when the engine is idle. Uses caller-supplied system + user prompt only; does NOT record to history; returns "" on any error.

13. **PersonaLoader** — loads IDENTITY.md + SOUL.md + USER.md from the OpenClaw workspace directory; composes them in render order for `"user_facing"` mode. `refresh_if_stale()` is called inside `_resolve_system_prompt()` on every `_build_messages()` invocation (~6 stat() calls, sub-ms cost). Gaming mode bypasses the PersonaLoader entirely (hardcoded `ULTRON_GAMING_PERSONA`).

14. **ConversationalAckSource** — produces filler phrases ("Mm.", "Right.", "Processing.", etc.) before the LLM stream starts to mask the TTFT gap (~2.5s total latency). Suppressed when: gaming mode active (determined by `_gaming_conversational_prompt() is not None`), short utterance (<11 chars / <4 words), or pending clarification.

15. **`apply_brevity_hint()`** — prepends ONE style directive to the user message before it reaches the LLM (priority order: procedural > factual > brief). The directive is a `[Style: ...]` bracketed prefix that `_is_short_conversational_query()` and `_strip_brevity_hint()` see through to detect the bare user intent. Idempotent (won't double-hint a message that already has a `[Style:` prefix).

---

## Flags & config

| Flag / Config Key | Default | Effect |
|---|---|---|
| `llm.runtime` | `"in_process"` | `"in_process"` or `"http_server"` |
| `llm.preset` | `"qwen3.5-4b"` | Named preset from `LLM_PRESETS`; fills model_path/n_ctx/draft_model_path |
| `llm.model_path` | (from preset) | Path to GGUF file relative to project root |
| `llm.draft_model_path` | (from preset) | Path to draft GGUF; presence + `draft_kind` controls speculative decoding |
| `llm.draft_kind` | `"none"` | `"none"/"pld"/"model"` |
| `llm.n_ctx` | 8192 | Context window in tokens |
| `llm.gpu_layers` | -1 | -1=full GPU; 0=CPU; N=N layers on GPU |
| `llm.flash_attn` | True | CUDA flash attention (required for non-F16 KV cache types) |
| `llm.kv_cache_type` | 8 | 8=q8_0, 1=F16 (F16 mandatory when flash_attn=False) |
| `llm.n_batch` | None | Prefill batch size; None=llama.cpp default (512) |
| `llm.n_ubatch` | None | Micro-batch; None=llama.cpp default (512); 256 recommended for voice on 4070Ti |
| `llm.default_temperature` | 0.7 | Default sampling temperature |
| `llm.default_top_p` | 0.9 | Default nucleus sampling p |
| `llm.default_max_tokens` | 512 | Default max generation tokens |
| `llm.default_repeat_penalty` | 1.1 | Default repetition penalty |
| `llm.history_turns` | 6 | Max recent turns in legacy deque mode (no memory) |
| `llm.prefix_cache_ram_bytes` | 0 | LlamaRAMCache capacity; 0=disabled (bench showed regression on short prompts) |
| `llm.rag.position` | `"recency"` | `"system"` or `"recency"` (prepend to user msg; +10-20% recall on 4B) |
| `llm.compression.enabled` | True | Heuristic compression for RAG/web blocks |
| `llm.compression.compress_rag` | True | Compress RAG block before injection |
| `llm.compression.compress_web` | True | Compress web search context |
| `llm.compression.compress_history` | False | Off — history has user voice, mangling risk |
| `llm.history_compression.enabled` | False | Enable condenser pipeline on history block |
| `llm.history_compression.intent_adaptive` | True | Per-intent condenser selection when compression enabled |
| `llm.history_compression.closed_window_enabled` | True | Remove closed file-view windows from history |
| `llm.enable_thinking_drift_sample_rate` | 0.02 | Fraction of /no_think turns sampled for thinking-mode drift detection |
| `llm.persona.source` | `"config"` | `"config"` = hardcoded string; `"workspace"` = PersonaLoader SOUL.md hot-reload |
| `llm.persona.workspace_dir` | (default_workspace_dir) | Path to OpenClaw workspace files |
| `llm.persona.fallback_to_config_on_empty` | True | Fall back to `llm.system_prompt` if workspace returns empty |
| `llm.system_prompt` | `""` | Hardcoded system prompt (legacy / config source) |
| `llm.self_consistency.enabled` | (see class) | Majority-vote on high-stakes LLM calls (off voice hot path) |
| `llm.idle_vram_reclaim.enabled` | True | `torch.cuda.empty_cache()` at IDLE transition |
| `llm.idle_vram_reclaim.min_slack_mb` | 192 | Minimum reserved-minus-allocated VRAM to trigger reclaim |
| `llm.speculative_max_ngram_size` | 2 | PLD n-gram size (only when draft_kind="pld") |
| `llm.speculative_num_pred_tokens` | 10 | PLD prediction tokens per call |
| `llm.model_draft_num_pred_tokens` | 4 | Real-model draft tokens per verification round |
| `gaming_mode.barebones_skip_retrieval` | True | Skip Qdrant RAG during gaming/testing mode |
| `KENNING_LLM_MODEL_PATH` env | (unset) | Override model path without editing config |
| `KENNING_LLM_PRESET` env | (unset) | Override preset name (used by reload_for_preset) |
| `KENNING_LLM_GPU_LAYERS` env | (unset) | Override gpu_layers at runtime |
| `KENNING_SNAP_REGISTRY` env | `"1"` | Gate for data-driven snap registry in relay |
| `KENNING_RELAY_TEAM_DSP` env | (unset) | Gate for team-path audio DSP (relay shaping) |
| `KENNING_ADDRESSING_TAU` env | 0.20 | Confidence threshold for addressee fusion |
| `KENNING_WAKE_TRIM_TO_SPEECH` env | (unset) | Gate for VAD-based wake-word audio trimming |

---

## Extension points

1. **New prompt template** — Add to `llm_prompts.py` as a named constant, add to `ANSWER_SYSTEM_FOR` dict if it's an answer subtype, or wire as a `system_prompt=` override on a specific `generate_stream()` call site in relay_speech.py or the orchestrator.

2. **New LLM preset** — Add entry to `LLM_PRESETS` dict in `config.py:661`, add the preset literal to `LLMConfig.preset` Literal type, add to `scripts/download_models.py`.

3. **New mode → preset route** — Add `Mode.NEW_MODE` entry to `DEFAULT_ROUTES` in `mode_router.py:71`, or call `router.set_preset(mode, PresetEntry(...))` at runtime.

4. **New condenser strategy** — Subclass `Condenser` in `condensers/`, add kind string to `KNOWN_CONDENSER_KINDS`, wire in `build_condenser()`, add intent mappings to `_INTENT_KIND_MAP`.

5. **New response style hint** — Add detection predicate and hint string to `response_style.py`, wire into the dispatch priority in `apply_brevity_hint()`.

6. **New snap registry entry** — Add `SnapRule` instance to `SNAP_REGISTRY` or `TargetSnapRule` to `TARGET_SNAP_REGISTRY` in `voice_lines.py` (data-driven, no code change needed per the snap registry design).

7. **Sampling override** — Any `generate_stream()` call can pass a `sampling` dict with keys from `_chat_completion_kwargs()` allowlist: `temperature, top_p, top_k, min_p, max_tokens, repeat_penalty, presence_penalty, frequency_penalty, stop, grammar, logit_bias, seed`.

8. **Prompt injection for route-all-LLM** — The `system_prompt=` kwarg to `generate_stream()` and the `sampling=` dict together are the complete override surface. A route-all-LLM pivot only needs: (a) a curated system prompt per intent/route, (b) a `sampling` dict appropriate for the output length, and (c) injection of deterministic exemplars into the user message — no new API is needed.

9. **Temperament hint / evolution** — `llm.set_temperament_hint("[Tone: ...]")` appends a `[Tone: ...]` directive to the system prompt for the next turn only. The evolution service produces this from per-turn TTFT + satisfaction signals.

---

## Retire-not-remove candidates (u1.0)

1. **`_REPHRASE_PROMPT` (relay_speech.py:2081)** — The ~120-line f-string covering snap vs off-snap register, first-person, directives, asking vs answering. In the u1.0 route-all-LLM design this becomes one curated prompt template injected as a system prompt; the deterministic snap paths become routers that pick this template + inject exemplar snap lines as in-context examples. The template stays but migrates to `llm_prompts.py` as a named constant (currently indexed-but-not-relocated per the llm_prompts.py comment at line 32).

2. **`_RELAY_SAMPLING` / `_ANSWER_SAMPLING`** — These per-path sampling presets become part of the route table. Retain as named constants but collect them into a sampling-profile registry.

3. **`_build_rephrase_prompt()`** — Retire as a monolithic builder; replace with a template-renderer that inserts exemplars from the snap/flavor library into the prompt. The addressee/context/recent-lines injection logic is still needed.

4. **`classify_answer_subtype()` / `build_answer_call()`** — These are the router+builder for the adaptive answer pipeline. In u1.0, the router function is extended (detecting more intent classes: identity, social, tactical-rephrase, marvel, think-respond) and the builder applies prompt templates from `llm_prompts.py`. Retire the current hard-coded 2-subtype structure in favour of a small dispatch table keyed on subtype string.

5. **`apply_brevity_hint()`** — In u1.0, with all responses LLM-routed, the style directive becomes part of the prompt template for each route rather than a prefix prepended to user text. The current function can be retired or repurposed as a template parameter injector.

6. **`_CONVERSATIONAL_PHRASES` / `ConversationalAckSource`** — The filler-ack pool should survive into u1.0 (perceived latency fix). However it may need to be Ultron-persona phrases (Ultron does not say "Processing." in character during a match). Retire / replace pool contents; keep the mechanism.

7. **`generate_isolated()`** — Retain exactly as-is for background structured tasks (summarizer, evaluation). Its bypass-everything contract is correct and should not be changed.

8. **`_GREETING_RE` / `_SHORT_ACK_RE` RAG bypass** — Retain for non-gaming turns. In gaming mode, RAG is already fully suppressed by `barebones_skip_retrieval`; these gates are belt-and-suspenders for the desktop persona path.

---

## Gotchas

1. **`/no_think` marker is model-family specific** — The marker is only appended when `"qwen"` appears in the LIVE model path (checked from `self.model_path`, falling back to config on HTTP runtime). The Llama-3.2 gaming preset would literally parrot `/no_think` as speech if this guard is bypassed. Any new model added that does not consume the marker must have its family substring guarded in `_apply_no_think_marker()`.

2. **`flash_attn=True` requires non-F16 KV cache** — If `flash_attn=False`, `kv_cache_type` MUST be 1 (F16); q8_0 crashes without CUDA flash attention. The CPU device profile enforces this (`flash_attn=False, kv_cache_type=1`) but the config allows arbitrary combinations; llama.cpp will error silently or crash if the pair is wrong.

3. **`logits_all=True` is mandatory when speculative draft is active** — A llama-cpp-python bug (0.3.22): when `draft_model=` is set, `_logits_all` is silently forced True internally but the `scores` buffer is still sized by the original `logits_all` arg. If `logits_all` is not explicitly passed as True, the scores slice falls outside the buffer for prompts longer than `n_batch`, crashing with a shape broadcast error. `_build_llama()` handles this at line 780.

4. **`_build_messages()` is bypassed entirely when `system_prompt=` override is passed** — When a caller passes `system_prompt=` to `generate_stream()`, `_build_messages()` returns `[{system}, {user}]` immediately — no injection sanitisation, no history, no RAG, no skills block, no temperament hint. This is intentional for the relay path (strict latency + correctness) but means injection defences are absent on that surface. The relay path trusts that `command.payload` has already been validated by the routing layer.

5. **History reset on every hot-swap** — Both `reload_for_preset()` and `reload_for_device()` call `self._history.clear()`. Memory turns on disk are preserved (the ConversationMemory object survives), but the in-memory deque is cleared. Post-swap continuity depends entirely on the ConversationMemory path being active.

6. **Per-turn system prompt resolution is NOT thread-safe** — `_resolve_system_prompt()` calls `PersonaLoader.refresh_if_stale()`, which does file-system stat() calls; concurrently calling `generate_stream()` from multiple threads (speculative LLM + main LLM) while the workspace files are being edited could produce a torn read. In practice, the speculative path uses `generate_stream(system_prompt=<gaming>)` which bypasses the PersonaLoader; the risk is low but real for desktop mode.

7. **RAG position "recency" puts retrieved memory immediately before the user message** — This is in the strongest-attention zone for the 4B model. However, a large RAG block can dominate the user query for factual questions where the retrieved memory is stale (the "stale warning" header added in the format block is a partial mitigation). The format block labels memories as "possibly stale" but small models still over-weight nearby content.

8. **Thinking mode drift sampling** — `enable_thinking_drift_sample_rate=0.02` causes 1 in 50 calls that would have used `/no_think` to instead allow the thinking block. This is for offline drift detection only; the thinking block is stripped before TTS, so the user never hears it. But the token budget for that turn is much higher, which can cause TTFT spikes that the evolution service misinterprets as regressions.

9. **`generate_isolated()` has no cancel mechanism** — It calls `create_chat_completion` directly with no `self._cancel` guard. The background summarizer is supposed to gate on engine idle state before calling it, but if a foreground stream starts concurrently, both will use the Llama instance simultaneously (llama.cpp is NOT thread-safe for concurrent generation).

---

## Open questions

1. **For u1.0 route-all-LLM: where does the intent/route classification live?** — Currently the deterministic snap paths in `relay_speech.py` and the router in the orchestrator decide whether to call the LLM at all. For u1.0, we need a lightweight intent classifier that fires BEFORE the LLM to select a prompt template and sampling profile. Does this replace the current `classify_answer_subtype()` + the deterministic matcher pipeline, or does it sit alongside?

2. **Verbosity / flavor as LLM prompt param vs TTS gating** — Currently `flavor_tails_enabled()` decides at the relay output layer whether to append a flavor tail. In u1.0 with prompt-driven verbosity, does "low verbosity" become a directive in the system prompt ("no flavor tails"), or does the tail selection remain deterministic post-LLM? The distinction affects whether flavor knowledge needs to be in the prompt or not.

3. **The `_REPHRASE_PROMPT` has strong register-detection logic** (snap vs off-snap, first-person, asking vs answering) — In u1.0 does this become exemplar-driven (show the model examples of correct snap vs off-snap relay), or does deterministic pre-classification continue to set the mode before the LLM is called?

4. **Multiple concurrent system prompts** — The relay path always uses its own `system_prompt=` override. If u1.0 introduces more specialized routes (identity, social, etc.), each with its own system prompt, the bypass-everything behaviour of `_build_messages()` when `system_prompt` is set means injection defences are absent on all those routes. Should a lighter sanitise-and-pass be preserved even for the override path?

5. **Speculative decoding stability** — Both PLD and real-model draft are default-OFF due to `llama_decode returned -1` crashes in llama-cpp-python 0.3.22. Does u1.0 plan to upgrade the llama-cpp-python wheel to test these, or continue with orchestrator-level speculation only?

6. **The `sampling` whitelist in `_chat_completion_kwargs()`** includes `grammar` and `logit_bias` but these are never used in the current codebase. Are they reserved for u1.0 constrained output (e.g., forcing the model to output valid callout slot JSON, or biasing toward specific Valorant agent names)?

7. **PersonaLoader hot-reload on every turn** — 6 stat() calls per `_build_messages()` invocation. In a high-throughput u1.0 route-all-LLM system, this fires on every turn. Is a debounce/version-hash approach needed, or is the current mtime+size comparison (sub-ms) sufficient?

8. **`generate_isolated()` concurrency safety** — The background summarizer currently gates on engine idle state before calling it, but the code has no mutex around the Llama instance. Is a lock needed if u1.0 introduces more background-task LLM callers?
