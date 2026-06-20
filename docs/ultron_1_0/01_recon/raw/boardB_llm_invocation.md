# B7: MAP the conversational LLM invocation path (persona pin, sampling, streaming, thinking)

## Overview

This document traces every step from a recognized utterance reaching the LLM through to streamed tokens entering the TTS engine. It covers:

- Prompt assembly (system prompt sourcing, user message augmentation, RAG injection)
- Persona pinning (SOUL.md workspace vs config.yaml, gaming-mode Ultron override)
- Sampling parameters (defaults, relay overrides, answer-pipeline overrides)
- Token streaming to Kokoro TTS
- Thinking-mode handling (Qwen3 `/no_think` marker, `<think>` block stripping)
- Relay rephrase LLM path (separate system prompt, separate sampling)
- Adaptive ANSWER pipeline (`_ultron_answer.py`)
- Hot-swap presets and CPU/GPU device switch
- Speculative LLM prefetch

The LLM is `llama-cpp-python` (`Llama.create_chat_completion`), runtime `in_process` by default. An `http_server` runtime (OpenAI-compat) exists but is not the active voice path. Both share the same `generate` / `generate_stream` surface.

---

## Files & key symbols (path:line tables)

| File | Key symbols | Role |
|------|-------------|------|
| `src/kenning/llm/inference.py` | `LLMEngine`, `generate_stream`, `generate`, `generate_isolated`, `_build_messages`, `_chat_completion_kwargs`, `_apply_no_think_marker`, `_strip_thinking_blocks`, `strip_thinking_text`, `reload_for_preset`, `reload_for_device`, `_DEVICE_PROFILES` | Core LLM engine; all generation paths |
| `src/kenning/audio/llm_prompts.py` | `ULTRON_GAMING_PERSONA`, `ANSWER_PERSONA_CORE`, `ANSWER_MARVEL_RULES`, `ANSWER_THINK_RULES`, `ANSWER_SYSTEM_FOR` | Aggregate prompt constants for gaming persona + answer pipeline |
| `src/kenning/audio/_ultron_answer.py` | `build_answer_call`, `classify_answer_subtype`, `extract_answer_slots`, `_render_user`, `_ANSWER_SAMPLING`, `is_meta_leak`, `MARVEL_CANON`, `THINK_RESPOND_SUFFIX_RE` | Adaptive ANSWER pipeline (Marvel + think-and-respond routes) |
| `src/kenning/audio/relay_speech.py` | `_RELAY_REPHRASE_SYSTEM`, `_RELAY_SAMPLING`, `_build_rephrase_prompt`, `build_relay_line`, `thinking_mode_enabled`, `set_thinking_mode_enabled`, `match_thinking_toggle` | Relay rephrase LLM call; thinking-mode gate |
| `src/kenning/pipeline/orchestrator.py` | `_gaming_conversational_prompt`, `_build_response_stream`, `_kick_off_speculative_llm`, `_search_augmented_tokens`, `_maybe_handle_thinking_toggle`, `_maybe_handle_llm_device_switch` | Main dispatch; wires system prompt override into every `generate_stream` call |
| `src/kenning/openclaw_bridge/persona.py` | `PersonaLoader`, `default_workspace_dir`, `_MODE_FILES`, `PromptMode` | Reads SOUL.md / IDENTITY.md / USER.md from workspace; hot-reload |
| `src/kenning/config.py` | `LLMConfig`, `LLMPersonaConfig`, `LLM_PRESETS`, `_DEVICE_PROFILES` (via `inference.py`) | All LLM config schema; preset table |
| `config.yaml` | `llm.*`, `gaming_mode.*` | Canonical runtime values |

---

## Control/data flow

### A. Standard conversational turn (desktop / non-gaming)

```
Orchestrator.run()
  └─ _process_turn(user_text)
       ├─ llm.set_current_intent_kind(routing_intent_kind)          # [orch:8804]
       ├─ llm.set_temperament_hint(evolution.pre_turn_system_hint()) # [orch:8817]
       ├─ _build_response_stream(user_text)                          # [orch:8823]
       │    ├─ maybe_local_clock_reply(user_text)  → short-circuit    # [orch:10068]
       │    ├─ _collect_speculative_classification(user_text)         # [orch:10090]
       │    ├─ _kick_off_rag_prefetch(user_text)   → ThreadPool       # [orch:10103]
       │    ├─ web_gate.classify(user_text)         → GateVerdict      # [orch:10189]
       │    ├─ apply_uncertainty(verdict, user_text)                  # [orch:10221]
       │    ├─ apply_brevity_hint(augmented_text)                     # [orch:10294]
       │    └─ llm.generate_stream(                                   # [orch:10305]
       │           augmented_text,
       │           gate_verdict=verdict,
       │           precomputed_rag_snippets=snippets,
       │           history_user_message=user_text,
       │           rag_query=user_text,
       │           enable_thinking=False,
       │           system_prompt=_gaming_conversational_prompt()  # None if not gaming
       │        )
       └─ tts.speak_stream(gated())                                   # [orch:8834]
```

### B. `LLMEngine.generate_stream` internals

```
generate_stream(user_message, ...)
  ├─ _cancel.clear()
  ├─ _build_messages(user_message, ...)
  │    ├─ _sanitize_user_input(user_message)          # injection scrub   [inf:963]
  │    ├─ short-query gate → suppress_memory_context  # greetings/acks    [inf:975]
  │    ├─ if system_prompt kwarg → use verbatim + skip skills/temp [inf:989]
  │    ├─ _resolve_system_prompt()                    # SOUL.md or config [inf:1000]
  │    │    ├─ explicit override?  → return it
  │    │    ├─ PersonaLoader.get_system_prompt("user_facing")  → IDENTITY+SOUL+USER
  │    │    └─ fallback → llm.system_prompt (config.yaml string)
  │    ├─ maybe_get_skills_block(user_message, mode, vlm_loaded, has_internet)
  │    │    → appended to system_content if non-empty               [inf:1036]
  │    ├─ _temperament_hint → appended to system_content            [inf:1047]
  │    ├─ RAG injection:
  │    │    ├─ suppress? → rag_block=""
  │    │    ├─ precomputed_rag_snippets? → _format_rag_block(snippets)
  │    │    └─ else → _retrieve_rag_snippets(retrieve_query) → _format_rag_block
  │    ├─ rag_position == "system"? → fold rag_block into system_content
  │    ├─ msgs = [{"role":"system","content":system_content}]        [inf:1113]
  │    ├─ history_block (recent turns / memory)
  │    │    └─ capped at memory.history_turns_for_llm (default 4)
  │    └─ user message appended (rag prepended if position=="recency")[inf:1218-1222]
  ├─ _apply_no_think_marker(messages, enable_thinking)               [inf:2036]
  │    └─ if enable_thinking is False AND model is Qwen:
  │         append " /no_think" to last user message
  ├─ _chat_completion_kwargs(_llm_cfg, enable_thinking, stream=True) [inf:2066]
  │    → {temperature, top_p, max_tokens, repeat_penalty} + optional sampling overrides
  ├─ _llm.create_chat_completion(messages=messages, **kwargs)        [inf:2068]
  ├─ _raw_deltas() → yields raw token strings
  │    └─ records first_token_time → self._last_ttft_ms              [inf:2091]
  └─ _strip_thinking_blocks(_raw_deltas())                           [inf:2097]
       └─ yields visible tokens (suppresses <think>...</think> blocks)
       → caller iterates and yields to tts.speak_stream
  finally:
    _record_turn(recorded_user, full) if completed & not canceled    [inf:2112]
```

### C. Token → TTS path

```
Orchestrator (gated() wrapper)
  → tts.speak_stream(gated())                    # Kokoro: [kokoro_engine.py:698]
       ├─ fragments = list(fragments)             # materialise all tokens first
       ├─ synth_worker thread:
       │    _run_synth_loop(fragments, push=audio_q.put)
       │    → sentence-boundary split → per-sentence Kokoro synthesis → ClipItem
       └─ playback on main thread:
            WASAPI OutputStream (KENNING_RELAY_DSP path shapes PCM)
```

### D. Relay rephrase LLM path

```
build_relay_line(command, llm, rephrase=True, ...)      [relay_speech.py:~6320]
  ├─ if compose+context: → _ultron_answer.build_answer_call(command)
  │    → (system_prompt=ANSWER_SYSTEM_FOR[subtype],
  │       user_prompt=_render_user(subtype, slots),
  │       sampling=_ANSWER_SAMPLING)
  │    └─ llm.generate_stream(
  │           user_prompt,
  │           system_prompt=answer_system,
  │           sampling=_ANSWER_SAMPLING,
  │           record_history=False,
  │           suppress_memory_context=True,
  │           enable_thinking=False,
  │        )                                              [relay_speech.py:6340]
  └─ else: → _build_rephrase_prompt(command, recent_lines)
       └─ llm.generate_stream(
              prompt,
              system_prompt=_RELAY_REPHRASE_SYSTEM,
              sampling=_RELAY_SAMPLING,
              record_history=False,
              suppress_memory_context=True,
              enable_thinking=False,
           )                                              [relay_speech.py:6367]
```

### E. Speculative LLM prefetch

```
_run_speculative_classification()
  └─ _kick_off_speculative_llm(user_text, verdict, rag_future)      [orch:9647]
       └─ background thread:
            apply_uncertainty → apply_brevity_hint → snippets
            → llm.generate_stream(
                 augmented, gate_verdict=...,
                 precomputed_rag_snippets=snippets,
                 record_history=False,
                 system_prompt=_gaming_conversational_prompt(),
              )                                                       [orch:9726]
            → tokens buffered in Queue; committed via record_completed_turn() if consumed
```

---

## Key findings

### 1. Persona resolution hierarchy (per turn)

**Resolution order** (`inference.py:_resolve_system_prompt`, line 851):
1. Explicit `system_prompt=` kwarg to `generate_stream` → used VERBATIM, skips skills + temperament injection (`inference.py:989`). This is the primary mechanism for the gaming Ultron persona and the relay rephrase.
2. `llm.persona.source == "workspace"` → `PersonaLoader.get_system_prompt("user_facing")` → composes IDENTITY.md + SOUL.md + USER.md from `~/.openclaw/` workspace (`openclaw_bridge/persona.py:80`). Hot-reloads via mtime check per turn (~6 stat() calls, sub-ms).
3. Fallback to `llm.system_prompt` in config.yaml (the "You are Kenning..." string, line 633).

**Gaming-mode override** (`orchestrator.py:9006`): `_gaming_conversational_prompt()` returns `ULTRON_GAMING_PERSONA` (from `llm_prompts.py:48`) when `is_gaming_mode_active()` or `is_testing_mode_active()` is True, OR when the live-loaded model path contains `abliterat` / `llama-3.2-3b` / `gaming`. This is passed as the `system_prompt=` kwarg, bypassing SOUL.md entirely. Every `generate_stream` call in `_build_response_stream` passes this kwarg (lines 10160, 10212, 10320, 10450, 10526).

**Relay rephrase persona** (`relay_speech.py:2526`): `_RELAY_REPHRASE_SYSTEM` is a separate, shorter Ultron persona specifically for the relay LLM call — prevents the Kenning desktop persona leaking into team voice chat. Always passed via `system_prompt=` kwarg.

**Answer pipeline persona** (`_ultron_answer.py` / `llm_prompts.py`): Two per-subtype variants:
- `marvel`: `ANSWER_PERSONA_CORE` + `ANSWER_MARVEL_RULES`
- `think_respond`: `ANSWER_PERSONA_CORE` + `ANSWER_THINK_RULES`

### 2. Sampling parameters

**Global defaults** (`config.yaml:602`):
```yaml
default_temperature: 0.7
default_top_p: 0.9
default_max_tokens: 512
default_repeat_penalty: 1.1
```
Set in `_chat_completion_kwargs` (`inference.py:2176`).

**Relay rephrase sampling** (`relay_speech.py:2507`):
```python
_RELAY_SAMPLING = {
    "max_tokens": 56,        # tight cap — one spoken breath
    "temperature": 0.8,
    "top_p": 0.92,
    "top_k": 40,
    "min_p": 0.08,
    "repeat_penalty": 1.18,
    "stop": ["\n\n", "\nADDRESS:", "\nTASK:", ...],
}
```

**Answer pipeline sampling** (`_ultron_answer.py:239`):
```python
_ANSWER_SAMPLING = {
    "max_tokens": 80,        # slightly longer for Marvel/think answers
    "temperature": 0.85,
    "top_p": 0.92,
    "top_k": 40,
    "min_p": 0.08,
    "repeat_penalty": 1.18,
    "stop": ["\n\n", "\nADDRESS:", "\nTASK:", ...],
}
```

The `sampling=` dict override in `generate_stream` is applied inside `_chat_completion_kwargs` (`inference.py:2188`) for an allowed key set: `temperature`, `top_p`, `top_k`, `min_p`, `max_tokens`, `repeat_penalty`, `presence_penalty`, `frequency_penalty`, `stop`, `grammar`, `logit_bias`, `seed`.

### 3. Thinking-mode handling

**Current default**: `enable_thinking=False` is hardcoded on every voice-path `generate_stream` call in the orchestrator (lines 10159, 10211, 10319, 10446, 10523) and in the relay paths (`relay_speech.py:6346, 6373`).

**`/no_think` marker** (`inference.py:2201`): `_apply_no_think_marker` appends ` /no_think` to the last user message when `enable_thinking is False` AND the live model path contains `"qwen"`. This is the Qwen3/Qwen3.5 chat-template convention for disabling chain-of-thought. NON-Qwen models (e.g. `llama-3.2-3b-abliterated`) do NOT get the marker — it was observed to be parroted verbatim by Llama, producing "No think." in TTS.

**`<think>` block stripping** (streaming): `_strip_thinking_blocks(_raw_deltas())` (`inference.py:367`) holds a tail buffer (HOLD=8 chars) to handle tags split across token boundaries. Strips the entire `<think>...</think>` block before tokens reach the TTS.

**`<think>` block stripping** (blocking): `strip_thinking_text(raw_text)` (`inference.py:409`) applied in `generate()` and `generate_isolated()`.

**Relay thinking-mode toggle** (`relay_speech.py:1197`): Process-global `_thinking_mode_enabled` flag (default `False`, env `KENNING_THINKING_MODE`). When OFF, `build_relay_line` forces `rephrase=False` for compose commands, preventing the LLM from authoring relay lines — they snap from deterministic pools instead. Voice command: "thinking mode on/off" (`orchestrator.py:3300`).

**Thinking drift sampling** (`config.py:954`): `enable_thinking_drift_sample_rate` (default 0.02) causes 1-in-50 voice turns to be recorded as `thinking_drift_sample` observations for offline accuracy regression review, without actually changing the response.

### 4. LLM presets and device switch

**Presets** (`config.py:661`, `config.yaml:553`):
- `qwen3.5-4b`: `models/Qwen3.5-4B-Q4_K_M.gguf`, n_ctx=8192, draft=0.8B (active config default)
- `qwen3.5-9b`: `models/Qwen3.5-9B-Q4_K_M.gguf`, n_ctx=8192, no draft
- `josiefied-qwen3-8b`: `models/Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf`, n_ctx=8192
- `josiefied-qwen3-4b`: `models/Josiefied-Qwen3-4B-abliterated-v2.Q4_K_M.gguf`, n_ctx=6144
- `gemma-3-4b-abliterated`: `models/gemma-3-4b-it-abliterated.Q4_K_M.gguf`, n_ctx=4096
- `llama-3.2-3b-abliterated`: `models/Llama-3.2-3B-Instruct-abliterated.Q4_K_M.gguf`, n_ctx=6144, `gpu_layers=0` (gaming preset, CPU-only)

**Gaming mode preset**: `config.yaml:1691` → `gaming_mode.llm_preset: "llama-3.2-3b-abliterated"`. On engage, the 4B is swapped out and the 3B is loaded CPU-only. `barebones_direct_gaming_llm: true` constructs the 3B directly without a transient 4B load.

**`reload_for_preset`** (`inference.py:1413`): Voice-command hot-swap. Loads new GGUF first, then releases old. Verifies GGUF digest via `voice_baseline_verify`. Resets history on success. Only `in_process` runtime.

**`reload_for_device`** (`inference.py:1599`): Hot-switch CPU↔GPU of the CURRENTLY loaded model (same GGUF, different `_DEVICE_PROFILES`). Profiles (`inference.py:68`):
- GPU: `n_gpu_layers=-1`, `flash_attn=True`, `kv_cache_type=8` (q8_0), `n_batch=512`, `n_ubatch=512`
- CPU: `n_gpu_layers=0`, `flash_attn=False`, `kv_cache_type=1` (F16), `n_batch=512`, `n_ubatch=256`
Voice command: "switch the model to the GPU/CPU" (`orchestrator.py:3326`).

### 5. System prompt construction detail

When `system_prompt=` kwarg is NOT passed (standard desktop conversational path):
- `_resolve_system_prompt()` returns SOUL.md composition (IDENTITY.md + SOUL.md + USER.md)
- `maybe_get_skills_block` appends skill manifests filtered by mode/vlm/internet
- `_temperament_hint` (from EvolutionService) appended if non-empty
- RAG block injected at position `"recency"` (default) — prepended to the final user message — or `"system"` (config option)

When `system_prompt=` kwarg IS passed (gaming conversational, relay rephrase, answer pipeline):
- **Used VERBATIM** (`inference.py:989-993`)
- Skills block: SKIPPED
- Temperament hint: SKIPPED
- History / RAG: still applied unless `suppress_memory_context=True`

The relay and answer pipeline both pass `suppress_memory_context=True` + `record_history=False`, completely isolating the LLM call from conversational history and RAG.

### 6. RAG injection

RAG is retrieved from Qdrant via `bge-small-en-v1.5` (dense) + `bm25` (sparse) embeddings. In gaming mode, RAG is entirely skipped (`barebones_skip_retrieval: true`, `inference.py:1279`). Default position: `"recency"` (prepended to the user message, not the system message) for maximum attention. Suppressed for: (a) short queries / greetings (`inference.py:975`), (b) `suppress_memory_context=True`, (c) queries with fewer than 5 tokens (`_rag_query_has_min_content`, `inference.py:219`).

### 7. Token history recording

- `_record_turn(recorded_user, full)` is called at stream end if `completed and not canceled and record_history`.
- `history_user_message=` kwarg (default `None`) controls what is stored: bare user text, NOT the brevity-hinted or search-augmented prompt body. Prevents RAG contamination loops.
- Relay and answer paths pass `record_history=False` — never stored in history.

---

## Flags & config

| Key | Default | Effect |
|-----|---------|--------|
| `llm.preset` | `"qwen3.5-4b"` | Active model GGUF + n_ctx; voice hot-swap via `reload_for_preset` |
| `llm.runtime` | `"in_process"` | `"http_server"` for separate llama-cpp-server |
| `llm.default_temperature` | `0.7` | Base sampling temperature |
| `llm.default_top_p` | `0.9` | Top-p nucleus sampling |
| `llm.default_max_tokens` | `512` | Max output tokens (relay overrides to 56/80) |
| `llm.default_repeat_penalty` | `1.1` | Repeat penalty |
| `llm.gpu_layers` | `-1` | Full GPU offload; gaming_mode forces `0` |
| `llm.flash_attn` | `true` | CUDA flash attention (required for non-F16 KV cache) |
| `llm.kv_cache_type` | `1` (F16) | KV cache quantization; `8`=q8_0 (GPU only) |
| `llm.n_ctx` | `8192` | Context window; per-preset |
| `llm.persona.source` | `"workspace"` | `"config"` to use hardcoded `llm.system_prompt` |
| `llm.persona.fallback_to_config_on_empty` | `true` | Fallback when workspace files absent |
| `llm.rag.position` | `"recency"` | `"system"` to fold RAG into system message |
| `llm.enable_thinking_drift_sample_rate` | `0.02` | Fraction of turns sampled for thinking-drift obs |
| `llm.prefix_cache_ram_bytes` | `0` | LlamaRAMCache capacity (disabled after bench showed regression) |
| `llm.draft_kind` | `"none"` | `"pld"` or `"model"` for speculative decoding |
| `gaming_mode.llm_preset` | `"llama-3.2-3b-abliterated"` | LLM preset loaded on gaming engage |
| `gaming_mode.llm_gpu_layers` | `0` | Gaming LLM runs fully on CPU |
| `gaming_mode.barebones_skip_retrieval` | `true` | Skip RAG during gaming (GPU/compute saver) |
| `gaming_mode.barebones_direct_gaming_llm` | `true` | Construct 3B directly (no 4B transient) |
| `gaming_mode.barebones_skip_web_search` | `true` | Skip web-search preflight in gaming |
| `KENNING_LLM_MODEL_PATH` | unset | Env override for GGUF path |
| `KENNING_LLM_PRESET` | unset | Env override for preset name |
| `KENNING_THINKING_MODE` | `"0"` | Process-global relay thinking mode flag |

---

## Extension points

1. **Adding a new LLM prompt / persona**: Add a constant to `src/kenning/audio/llm_prompts.py` and pass it as `system_prompt=` in the relevant `generate_stream` call. The aggregate file is the canonical single location for all gaming/relay prompts.

2. **Adding a new ANSWER subtype** (e.g., C: teammate compliment, D: lore): Add the subtype key to `ANSWER_SYSTEM_FOR` in `llm_prompts.py`, extend `classify_answer_subtype` in `_ultron_answer.py`, add extraction logic to `extract_answer_slots` and `_render_user`. Zero changes to the LLM engine itself.

3. **Adding a new LLM preset**: Add entry to `LLM_PRESETS` in `src/kenning/config.py:661`, add the GGUF download in `scripts/download_models.py`, add a TOFU pin in `scripts/voice_baseline_verify.py`. Voice hot-swap via `reload_for_preset` is automatic.

4. **Adjusting sampling per intent**: The `sampling=` dict accepted by `generate_stream` (`inference.py:1991`) is the clean extension point. Relay uses `_RELAY_SAMPLING`; answer pipeline uses `_ANSWER_SAMPLING`; a new route-all-through-LLM path would define its own sampling dict keyed by intent.

5. **Thinking-mode per-intent**: The `enable_thinking` parameter (`Optional[bool]`) is already plumbed end-to-end. For a route-all-LLM u1.0 build, a per-intent `enable_thinking` map (e.g. True for complex tactical queries, False for banter) is directly pluggable.

6. **Route-all through LLM (u1.0 pivot)**: The cleanest seam is `_build_response_stream` in `orchestrator.py:10031`. Currently this function returns only after classifying the intent and branching between deterministic paths, web search, and the LLM. For u1.0 the deterministic snap paths become prompt templates injected into the LLM call (as system prompt blocks or in-context exemplars), routed by intent. The existing `system_prompt=` override kwarg already supports per-intent prompt switching without LLMEngine changes.

7. **Thinking trace logging**: `_last_ttft_ms` is already stashed per stream (`inference.py:2091`). Adding a `_thinking_trace` buffer to `_raw_deltas` (before `_strip_thinking_blocks`) would capture the raw `<think>...</think>` content per turn. `observe_llm_call` (`inference.py:2128`) already emits to observations; a new `observe_thinking_trace` event type would be additive.

8. **Persona for always-listening mode**: The `system_prompt=` kwarg + the `_gaming_conversational_prompt` gate are the existing hooks. For u1.0 always-listening, a new discriminator function (analogous to `_gaming_conversational_prompt`) would map the detected intent (A=talking to Discord, B=talking to stream, C=talking to Ultron) to the appropriate system prompt or a `None` to suppress response entirely.

---

## Retire-not-remove candidates (u1.0)

1. **`_build_response_stream` gate logic** (orchestrator.py:10031–10341): The web-gate classify + uncertainty upgrade + brevity-hint + RAG-prefetch branching. In u1.0 (route all through LLM), these become prompt ingredients, not routing branches. The function body is replaced; the `llm.generate_stream` call is preserved.

2. **`maybe_get_skills_block` injection** (inference.py:1022): Skills manifest prepended to system prompt per-turn. In u1.0 with a fixed Ultron persona, skills are either embedded in the persona or dropped for gaming. The injection hook stays; the registry content changes.

3. **`apply_brevity_hint`** (response_style.py, called at orch:10294, 10146): A `[Style: respond in 1–3 short sentences]` prefix prepended to the user message. In u1.0 verbosity is prompt-driven (no/low/high blocks in the system prompt), so this helper becomes redundant on the gaming path. Keep for desktop.

4. **`_is_short_conversational_query` / RAG suppression** (inference.py:231, 975): Already gaming-mode-bypassed. Safe to leave in place; the `barebones_skip_retrieval` flag covers it in gaming.

5. **`thinking_mode_enabled()` gate in `build_relay_line`** (relay_speech.py:3551): The relay thinking-mode toggle was designed for "OFF = snap from deterministic pools, ON = LLM". In u1.0 thinking mode IS the default (all through LLM), so the gate inverts — the relay path would be the deterministic snap path used as an exemplar, not as the output. The flag can be repurposed as a "snap-only mode" emergency toggle.

6. **`generate_isolated`** (inference.py:1835): Already used by background summarizer / decomposer with custom system prompts. Is the correct surface for background LLM tasks in u1.0 (no persona, no history, structured extraction). Promote this as the non-voice-path LLM call convention.

---

## Gotchas

1. **`/no_think` is Qwen-family only** (`inference.py:2225–2264`): The marker is checked against the LIVE-LOADED model path (not config), because lean gaming boots the 3B directly while config.llm still names the 4B. The original config-only check appended `/no_think` to Llama, which parroted it as "economy. /no_think" → TTS spoke "No think." aloud into game chat.

2. **`system_prompt=` kwarg skips temperament + skills** (`inference.py:989`): Any caller passing an explicit system prompt gets NO EvolutionService temperament hint, NO skills block, and the `self.system_prompt` attribute is overwritten with the kwarg value for that turn (for debug log visibility). This is correct for relay/answer/gaming, but would be a gotcha if a future caller expected skills injection with a custom persona.

3. **Relay and answer LLM calls are fully isolated** (`suppress_memory_context=True, record_history=False`): They do not see conversation history, do not persist to history, and do not trigger RAG. This means the 3B on the relay path has zero conversational context — every relay call is stateless. For u1.0 route-all-through-LLM this isolation must be reconsidered.

4. **Thinking drift sampling** (`inference.py:2091` + orch:8848): The orchestrator records `_maybe_emit_thinking_drift_sample` AFTER the stream completes. The 2% sample rate means the full response is generated with `enable_thinking=False`; the "thinking" variant is NOT generated again. The observation is just a label on the no-think response for offline audit.

5. **`<think>` block stripping is streaming-safe** but has a 8-char tail buffer: `_strip_thinking_blocks` (`inference.py:367`) holds `HOLD=8` chars so a tag split across token boundaries (`</thi` + `nk>`) is handled. A sufficiently unusual tokenization could still slip through; `strip_thinking_text` on the blocking path is the backstop.

6. **PersonaLoader hot-reload** (`openclaw_bridge/persona.py`): SOUL.md edits take effect on the next LLM turn without restart. However, in gaming mode `_gaming_conversational_prompt()` bypasses SOUL.md entirely, so SOUL.md edits are invisible while gaming. The Ultron persona in `llm_prompts.py:ULTRON_GAMING_PERSONA` requires a code redeploy.

7. **HTTP runtime** (`inference.py:887`): The `http_server` runtime passes `chat_template_kwargs={"enable_thinking": enable_thinking}` directly in the HTTP payload (`inference.py:2299`), which llama-cpp-server accepts. The in-process runtime does NOT use this kwarg (it was discovered to be unsupported in llama-cpp-python 0.3.22) — it uses the `/no_think` marker instead. The two paths are asymmetric in thinking-mode implementation.

8. **KV cache type constraint**: `kv_cache_type=8` (q8_0) requires `flash_attn=True` (GPU). When gaming mode switches to CPU (`gpu_layers=0`), the device profile forces `flash_attn=False` + `kv_cache_type=1` (F16). An incorrect combination crashes llama-cpp-python at decode time.

9. **History reset on model swap**: Both `reload_for_preset` and `reload_for_device` call `self._history.clear()` on success. The in-process `deque` history is lost. Memory-backed turns persist on disk via Qdrant and are unaffected — they will be retrieved again on the next turn via RAG. This means the conversational context is NOT fully lost on a model swap, just the in-memory deque used when memory is disabled.

---

## Open questions

1. **SOUL.md content**: The workspace files (IDENTITY.md, SOUL.md, USER.md) are not in the repo — they live in `~/.openclaw/` and were not read in this recon. The actual "Kenning" persona content is unknown to this analysis. For u1.0, the Ultron gaming persona (ULTRON_GAMING_PERSONA in llm_prompts.py) would expand significantly; it is unclear if this should also be moved to a workspace file or remain in code.

2. **Thinking-mode and route-all-LLM tradeoff**: With `enable_thinking=False` hardcoded on the voice path to save 5–10 s TTFT, an 8B model in u1.0 would either keep the no-think constraint (fast but shallow) or enable thinking for complex intents (slower but higher accuracy). The per-intent table in `docs/4b_optimization_plan.md` was designed for this but is not yet wired. Needs explicit u1.0 decision.

3. **In-context exemplars for snap paths**: The u1.0 pivot requires deterministic snaps to become LLM in-context exemplars. The exact prompt injection format (few-shot examples in system prompt vs user/assistant pairs in history) is not determined. The existing `_build_messages` function already supports both injection points.

4. **Always-listening discriminator integration**: The classification of A (Discord), B (stream/out-loud), C (Ultron) replaces the current wake-word gate. How this discriminator result feeds into the `system_prompt=` selection (None → suppress, C → Ultron persona) and whether it runs inline or pre-emptively is not designed yet.

5. **Verbosity levels (no/low/high) in prompt**: Currently only `apply_brevity_hint` (a prefix on the user message) controls verbosity. In u1.0 this moves to the system prompt. The exact format and trigger for each verbosity level needs design.

6. **`generate_isolated` for u1.0 background tasks**: The background summarizer / decomposer already uses `generate_isolated`. Should u1.0 thinking-trace logging, intent classification, and addressee discrimination use `generate_isolated` (isolated, no history) or a dedicated lightweight engine? The current engine is shared (single Llama instance).

7. **Relay rephrase prompt at scale**: `_build_rephrase_prompt` is a ~120-line f-string template in `relay_speech.py:2538`. For u1.0 this is a candidate for relocation to `llm_prompts.py`, but the note in `llm_prompts.py:32` flags it as "too large to retype safely byte-exact; relocating it needs a behavioural (not value) diff". Confirm this relocation is in scope.
