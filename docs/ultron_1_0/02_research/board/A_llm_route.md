# Route-all-through-LLM: Attach-Point Validation (u1.0)

**Scope:** validate the planned u1.0 "route ALL responses through an 8B LLM" pivot
against the ACTUAL source code on branch `claude/infallible-kepler-0a865d` @ `dfadb89`.
Read-only source pass; all path:line refs verified against live files.

---

## Confirmed Attach Points (path:line)

### 1. Primary generation surface — `generate_stream`
`src/kenning/llm/inference.py:1979`
`LLMEngine.generate_stream(user_message, *, system_prompt=None, sampling=None, enable_thinking=None, suppress_memory_context=False, record_history=True, ...)→ Iterator[str]`

This is the single LLM generation entry point for ALL streaming paths. Confirmed behavior when `system_prompt=` is provided (line 989–993): `_build_messages` returns `[{system}, {user}]` immediately — no RAG, no history, no skills, no temperament injection. This is the "fast isolated" path already used by relay and answer. For u1.0 route-all-through-LLM, every intent route passes its curated template here via `system_prompt=` + `sampling=` + `suppress_memory_context=True`.

### 2. Relay rephrase LLM call — `build_relay_line` step 27
`src/kenning/audio/relay_speech.py:6326–6377`
The LLM rephrase call is at lines 6339–6374 (answer path) and 6360–6374 (generic rephrase path), both calling `llm.generate_stream(...)` with `system_prompt=_RELAY_REPHRASE_SYSTEM`, `sampling=_RELAY_SAMPLING`, `record_history=False`, `suppress_memory_context=True`, `enable_thinking=False`. **Confirmed: the rephrase call IS the correct attach point for u1.0 — it is already an isolated, persona-pinned LLM call.** For u1.0, this call is promoted from step-27-of-28 to the PRIMARY path (earlier steps become routers that emit a prompt template + exemplars rather than a final line).

### 3. Relay system prompt constant
`src/kenning/audio/relay_speech.py:2526–2534` — `_RELAY_REPHRASE_SYSTEM`
Confirmed pinned to Ultron; never the desktop "Kenning" persona. In u1.0 this becomes the base of a family of route-specific system prompts (still in `relay_speech.py` or relocated to `llm_prompts.py`).

### 4. Relay sampling constant
`src/kenning/audio/relay_speech.py:2507–2516` — `_RELAY_SAMPLING`
`max_tokens=56, temperature=0.8, top_p=0.92, top_k=40, min_p=0.08, repeat_penalty=1.18`. Confirmed in whitelist (`_chat_completion_kwargs` line 2189). For u1.0, each route (tactical-snap exemplar, identity, social, marvel, directive, compose) needs its own sampling profile; the existing `_RELAY_SAMPLING` is the tactical-rephrase baseline profile.

### 5. Adaptive answer pipeline — `build_answer_call`
`src/kenning/audio/_ultron_answer.py:251`
Returns `(system_prompt, user_prompt, sampling, subtype)` for `"marvel"` and `"think_respond"` subtypes only. Called at `relay_speech.py:6332–6354` and invokes `generate_stream` with its own `system_prompt=ANSWER_SYSTEM_FOR[subtype]` and `sampling=_ANSWER_SAMPLING` (max_tokens=80). **Confirmed: this IS the blueprint for u1.0's per-intent prompt routing.** The `ANSWER_SYSTEM_FOR` dict (`llm_prompts.py:123`) is the extend-by-entry pattern for new subtypes.

### 6. Gaming conversational path — `_gaming_conversational_prompt`
`src/kenning/pipeline/orchestrator.py:9006–9036`
Returns `ULTRON_GAMING_PERSONA` from `llm_prompts.py:48` when gaming/testing mode is active OR when the live model path contains `"abliterat"/"llama-3.2-3b"/"gaming"`. This is passed as `system_prompt=` to every `generate_stream` call in `_build_response_stream` (confirmed at lines 10145/10160, 10206/10212, 10305/10320, 10437/10450, 10509/10526). **For u1.0, this function becomes the route dispatcher: it returns not just a single persona string but the correct per-intent system prompt from the route table.** The call-site pattern does not change.

### 7. Desktop conversational LLM entry — `_build_response_stream` / `_respond`
`src/kenning/pipeline/orchestrator.py:10031` / `8756`
All non-relay, non-snap responses flow through `_respond` → `_build_response_stream` → `llm.generate_stream(...)`. **For u1.0, `_build_response_stream` is the second major attach point** (alongside `build_relay_line`) where the route classification drives system prompt selection.

### 8. `_REPHRASE_PROMPT` (the 28-step dispatch chain's LLM template)
`src/kenning/audio/relay_speech.py:2081–2210`
A ~130-line f-string with `{task}`, `{addressee}`, `{by_name}`, `{payload_block}`, `{recent_block}`, `{context_block}` fields. Built by `_build_rephrase_prompt()` (line 2538). **Confirmed: NOT yet in `llm_prompts.py` — the comment at `llm_prompts.py:32` explicitly flags this as "indexed-in-place; relocating needs a behavioral diff".** This is the richest existing prompt template and the primary exemplar surface for u1.0.

### 9. `josiefied-qwen3-8b` preset — `LLM_PRESETS`
`src/kenning/config.py:691–694`
`{"model_path": "models/Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf", "n_ctx": 8192, "draft_model_path": None}`. Confirmed present. The `_apply_no_think_marker` check at `inference.py:2254` confirms `"qwen"` is in this path → `/no_think` marker is correctly applied for this model family. **No code change needed to activate this preset; only `config.yaml: llm.preset: "josiefied-qwen3-8b"` and `gpu_layers: -1`.**

### 10. `sampling` whitelist (grammar, logit_bias hooks)
`src/kenning/llm/inference.py:2189–2196` — `_chat_completion_kwargs`
Confirmed whitelist includes `"grammar"` and `"logit_bias"` (both accepted by llama-cpp-python 0.3.22 per the comment). Neither is currently used in production. **These are the constrained-decoding hooks for u1.0 structured callout output.**

### 11. `_strip_thinking_blocks` — streaming-safe `<think>` removal
`src/kenning/llm/inference.py:367`
HOLD=8 char tail buffer. Confirmed already in all streaming paths. For u1.0 with thinking enabled on complex intents: the stripped content must be routed to a trace buffer BEFORE `_strip_thinking_blocks` discards it — the current implementation discards silently.

### 12. Prompt aggregate SSOT — `llm_prompts.py`
`src/kenning/audio/llm_prompts.py:1–126`
Confirmed contains: `ULTRON_GAMING_PERSONA` (line 48), `ANSWER_PERSONA_CORE` (line 82), `ANSWER_MARVEL_RULES` (line 97), `ANSWER_THINK_RULES` (line 113), `ANSWER_SYSTEM_FOR` dict (line 123). **This is the correct file for all new u1.0 per-intent system prompt constants.** `_REPHRASE_PROMPT` and `_RELAY_REPHRASE_SYSTEM` are still in `relay_speech.py` — the recon correctly identified this gap.

### 13. `_build_messages` bypass when `system_prompt=` is provided
`src/kenning/llm/inference.py:989–993`
When `system_prompt=` kwarg is not None: returns `[{system_prompt}, {user}]` immediately. **Critically, this bypass also skips `_sanitize_user_input()` (injection sanitisation), skills injection, and temperament hints.** The relay path trusts routing-layer validation; for u1.0 the injection sanitisation should be preserved even on the `system_prompt=` path.

---

## Corrections to the Recon/Plan

### C1. Recon line ref for `build_relay_line` is imprecise
The codebase map (`00_codebase_map.md`, section 2) says "relay_speech:6012" as the step-27 primary attach point. The actual LLM call is at **relay_speech.py:6339–6374**, not 6012 (which is the function definition). The 28-step chain begins at 6012 and reaches the LLM in the `if rephrase:` block at line 6326. The plan should reference 6326 (the rephrase guard) as the actual entry to the LLM step, not the function definition.

### C2. `_gaming_conversational_prompt` model-path check is broader than documented
The codebase map says the function returns `ULTRON_GAMING_PERSONA` "when gaming/testing mode is active". The actual code (`orchestrator.py:9031`) also returns it when `"abliterat" in mp or "llama-3.2-3b" in mp or "gaming" in mp`. This means the 8B josiefied preset (path: `Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf`) will trigger the `"abliterat"` branch and return `ULTRON_GAMING_PERSONA` even when gaming mode flag is not set, as long as the 8B is the loaded model. **u1.0 implication: loading the 8B as the new default will permanently pin `ULTRON_GAMING_PERSONA` as the conversational system prompt, even in non-gaming desktop sessions. If desktop persona (SOUL.md / "Kenning") is ever needed alongside the 8B, the `"abliterat"` guard must be narrowed or the function must check gaming flag exclusively.**

### C3. Relay thinking-mode toggle gate (`thinking_mode_enabled`) inverts for u1.0
The recon (boardB_llm_invocation.md, retire-not-remove #5) notes this correctly. **But the retire-not-remove entry mis-states the current default**: the `_thinking_mode_enabled` flag defaults to `False` (env `KENNING_THINKING_MODE` unset = 0), meaning the current toggle is OFF = snap from deterministic pools, ON = LLM rephrase. For u1.0 "route all through LLM", the flag semantics INVERT: OFF in u1.0 would mean "LLM-routed always", ON = snap-only emergency mode. This inversion is not reflected in the plan; it needs a concrete renamed flag or a polarity flip.

### C4. `_REPHRASE_PROMPT` line ref
`00_codebase_map.md` says "relay_speech.py:2081". Confirmed correct (`_REPHRASE_PROMPT = (` is at line 2081). The recon line refs for this symbol are accurate.

### C5. `_ANSWER_SAMPLING` lives in `_ultron_answer.py`, not `relay_speech.py`
`boardA_llm_serving.md` table lists `_ANSWER_SAMPLING` at `_ultron_answer.py:239`. Confirmed: line 239 in `_ultron_answer.py`. `relay_speech.py` holds `_RELAY_SAMPLING` (line 2507). These are separate constants; the plan should not conflate them when building the u1.0 per-route sampling registry.

### C6. `josiefied-qwen3-8b` n_ctx is 8192 — no draft model
`config.py:691–694`: `"n_ctx": 8192, "draft_model_path": None`. The comment ("No matching 0.8B draft is published") explains the absence. The plan mentions "quality-first now, latency optimized later" — correct; speculative decoding will not help here. The 8B at Q5_K_M on the 4070 Ti (12 GB) costs ~5.5 GB VRAM. With Kokoro TTS (~1.5 GB), STT (~2 GB), embedder sidecar (~0.5 GB), and OS/game overhead, the VRAM budget is ~12 GB − 9.5 GB = ~2.5 GB slack. This is tight and the plan must account for it.

### C7. `_build_messages` injection sanitization is BYPASSED by `system_prompt=` kwarg
This is documented in boardA_llm_serving.md (gotcha #4) but NOT called out in the codebase map's pivot map. **For u1.0, every relay/route path passes `system_prompt=`; this means `_sanitize_user_input()` (line 963) is NEVER called on relay inputs.** The relay path already sanitizes at the routing layer (normalizer + matcher), but explicit acknowledgment is needed in the plan.

---

## Risks & Gotchas for the Implementation

### R1. VRAM budget is the hard constraint
8B Q5_K_M = ~5.5 GB. Kokoro CUDA TTS = ~1.5 GB. faster-whisper large-v3 = ~1.6 GB. EmbeddingGemma sidecar (CPU) = 0. OS + Discord + Chrome background = ~1.5–2 GB. Total: ~10–11 GB on a 12 GB card. This leaves 1–2 GB for KV cache at n_ctx=8192 (q8_0 KV = ~0.5 GB for 8B at 8k ctx; F16 KV = ~1 GB). **The margin is real but thin.** GPU-mode 8B requires `flash_attn=True` + `kv_cache_type=8` (q8_0) to stay within budget. The existing `_DEVICE_PROFILES["gpu"]` already specifies this combination — it is the correct profile for the 8B.

### R2. `/no_think` guard is model-path based, not model-family config based
`_apply_no_think_marker` checks `"qwen" in ident.lower()` against the LIVE-LOADED model path (line 2254). The josiefied-8B path is `Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf` — `"qwen"` is NOT present (it is `Qwen3` → `qwen3` in the filename... wait: `Josiefied-Qwen3-8B` → the string `"Qwen3"` IS present). Checking: `"Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf".lower()` = `"josiefied-qwen3-8b-abliterated-v1.q5_k_m.gguf"` → `"qwen"` IS in this string. **Confirmed safe: the `/no_think` marker will be correctly applied to the 8B josiefied model.** No action needed.

### R3. `system_prompt=` kwarg bypass skips injection defences
As confirmed in attach point #13: passing `system_prompt=` to `generate_stream` bypasses `_sanitize_user_input()`. For u1.0 where ALL paths use `system_prompt=`, injection defences are entirely absent from the generation layer. The routing layer (normalizer + matcher) must be the sanitization boundary; or a minimal sanitize-and-continue wrapper should be added to the `_build_messages` branch at inference.py:989 before the return.

### R4. Relay is currently stateless; u1.0 must decide on conversational context
Every relay LLM call passes `suppress_memory_context=True, record_history=False` (confirmed relay_speech.py:6344–6346, 6370–6373). For simple tactical callouts this is correct. For u1.0 routes where the 8B is expected to produce contextually coherent social/identity responses, **zero conversational context means the model cannot refer back to anything said earlier in the match.** The plan must decide: (a) keep stateless for all relay paths (fastest, safest), or (b) inject a short session-recent-lines context block via the `recent_lines` mechanism already in `_build_rephrase_prompt` (lines 2611–2618 — already limited to 6 prior lines for team-addressed lines).

### R5. Relay verbatim-echo safety nets depend on model output format
`relay_speech.py:6381–6400` has two post-LLM safety nets: (1) reject if output verbatim-echoes a recent line; (2) reject "they're switch" hallucination. Both check the final model output string. For an 8B with thinking mode enabled, the raw output includes `<think>...</think>` which is stripped by `_strip_thinking_blocks` BEFORE these guards run (since `generate_stream` already strips). This is correct. However, if the 8B outputs multi-sentence responses, the `_cap_sentences(line, max_sentences=2)` gate at line 6413 is the final trimmer — the 8B may require tighter sampling caps (`max_tokens` in `_RELAY_SAMPLING`) since it will be more verbose than the 3B.

### R6. Fact-preservation guards (`_output_keeps_facts`, `_repair_against_input`) are critical — do not remove
`relay_speech.py:6424–6438`. These run after the LLM output and before the final return. **For u1.0, these are the correctness backstop.** An 8B model is MORE likely than the 3B to drop or hallucinate tactical facts on short-callout inputs (higher perplexity at short-output regime). These guards must remain and may need tuning (the `_fact_tokens` function at line 6309 determines what counts as a "tactical token").

### R7. `_gaming_conversational_prompt` will return `ULTRON_GAMING_PERSONA` for the 8B always
As noted in C2: loading the 8B (path contains `"abliterat"`) permanently triggers the model-path guard. The desktop conversational path will use `ULTRON_GAMING_PERSONA` as the system prompt even outside of a gaming session, and the SOUL.md persona loader will never fire. **This is the intended behavior for u1.0 (Ultron always), but it means SOUL.md is silently bypassed — any operators who rely on workspace persona hot-reload for the 8B must be warned.**

### R8. `LLM_PRESETS["josiefied-qwen3-8b"]` has no draft model — speculative decoding is off
For u1.0, the orchestrator-level speculative LLM prefetch (`_kick_off_speculative_llm`, orchestrator.py:9660) still works (it is not tied to the GGUF-level draft), but llama-cpp-level PLD/model draft is unavailable. Latency on the 8B will be higher than on the 3B; the speculative prefetch is the only latency mitigation available at launch.

### R9. History reset on preset swap clears in-memory deque only
`reload_for_preset` at inference.py:1593: `self._history.clear()`. Qdrant-backed `ConversationMemory` is unaffected. The in-session deque (4 turns, default) is lost. For u1.0 where relay calls set `record_history=False`, this is a non-issue for relay; it only affects the rare conversational desktop path.

### R10. `_REPHRASE_PROMPT` relocation is deferred — plan must acknowledge
The comment at `llm_prompts.py:32` ("relocating it needs a behavioral (not value) diff") means the `_REPHRASE_PROMPT` f-string template cannot simply be copy-pasted. The relocation must be accompanied by a byte-identical behavioral check (the golden-digest mechanism in `scripts/_voice_lines_verify.py` covers the `voice_lines.py` aggregate but NOT `relay_speech.py`). u1.0 must either defer the relocation or add a separate checksum test.

---

## Concrete Recommendation

**1. Minimal viable attach for the first route-all iteration:**

Promote the existing `build_relay_line` LLM rephrase call (`relay_speech.py:6326`) to fire for ALL non-verbatim, non-curated relay inputs by removing or gating the deterministic snap steps that currently short-circuit it. Each step that currently returns early should instead emit a `(template_id, exemplars[])` tuple into the user-message block. The `llm.generate_stream(prompt, system_prompt=_RELAY_REPHRASE_SYSTEM, sampling=_RELAY_SAMPLING, ...)` call at line 6367 is the confirmed single hook — no new LLM plumbing needed.

**2. Switch preset in `config.yaml` ONLY:**

Add `llm.preset: "josiefied-qwen3-8b"` and `llm.gpu_layers: -1` to `config.yaml`. All other inference machinery (`reload_for_preset`, `/no_think`, `_DEVICE_PROFILES`, `_strip_thinking_blocks`) is already correct for this model. Confirm VRAM budget at boot before any code changes.

**3. Expand `ANSWER_SYSTEM_FOR` in `llm_prompts.py` for new route subtypes:**

Add constants for: `identity` (teammate identity questions), `social` (compliment/insult/surrender reactions), `tactical_rephrase` (the new primary relay route, replacing `_RELAY_REPHRASE_SYSTEM`), `compose_directive` (compose with directive), `compose_morale` (compose encouragement). The `classify_answer_subtype` function in `_ultron_answer.py:146` is the router to extend — it currently returns only `"marvel"` or `"think_respond"`. Widen to 6–8 subtypes.

**4. Inject snap/flavor exemplars into the user message block, not the system prompt:**

The `_build_rephrase_prompt` function (relay_speech.py:2538) already has a `recent_lines` injection pattern (lines 2611–2618). Extend this with a `snap_exemplars` block: 3–5 curated `(input, output)` pairs drawn from `SNAP_REGISTRY` / `AGENT_FLAVOR` / `_M1_*` sets that match the current command's type. This is in-context few-shot, not prompt bloat — each pair is under 30 tokens.

**5. Preserve fact-preservation guards unconditionally:**

`_output_keeps_facts`, `_repair_against_input`, `_literal_relay` (relay_speech.py:6424–6438) must remain active on the 8B output path. Do not gate these on model size or route type.

**6. Add thinking-trace capture before `_strip_thinking_blocks`:**

In `generate_stream` at inference.py:2097, the current code is:
```python
for visible in _strip_thinking_blocks(_raw_deltas()):
```
For u1.0 thinking trace, insert a tee: capture the raw `<think>...</think>` content from `_raw_deltas()` into a buffer before stripping, and emit it to `logs/usage_trace.jsonl` via the existing `_trace_turn_flow` mechanism. This is a 10-line addition inside `generate_stream`.

**7. Fix the `_build_messages` injection sanitisation gap:**

Add a single `_sanitize_user_input()` call at the top of the `system_prompt is not None` branch in `_build_messages` (inference.py:989) before the early return. This restores injection defence on all relay/route paths in u1.0 without any latency impact (the function is a regex scan, sub-millisecond).

**8. Do NOT touch `generate_isolated`, `_strip_thinking_blocks`, or `_record_turn`:**

These are stable and correctly scoped. `generate_isolated` is the correct surface for any u1.0 background tasks (thinking-trace digest, exemplar scoring). No changes needed.
