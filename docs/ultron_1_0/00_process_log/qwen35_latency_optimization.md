# Qwen3.5-4B latency/VRAM optimization (2026-06-24)

Source: deep-research (`logs/_dr_claims.md`, 85 verified claims) + load-test evidence.

## DONE (this session)
1. **Thinking fix — the #1 latency lever.** Qwen3.5 was generating ~80-140 hidden
   reasoning tokens before EVERY answer (a 6-char "Hello." took 138 tokens / ~3.3 s).
   `/no_think` is ignored by Qwen3.5 (llama.cpp #20182) and `create_chat_completion`
   can't pass `chat_template_kwargs` in 0.3.22. FIX (in `src/kenning/llm/inference.py`):
   for qwen3.5 presets, route in-process generation to **raw `create_completion` with
   an empty `<think>\n\n</think>\n\n` assistant prefill** (ChatML, no BOS) +
   `stop=["<|im_end|>"]`, instead of `create_chat_completion`. Applied to all 3 gen
   methods (`generate_stream` [voice], `generate`, `generate_isolated`);
   `_apply_no_think_marker` now skips qwen3.5; `_raw_deltas` + the blocking extractors
   handle the `text` chunk shape. Helpers: `_is_qwen35`, `_build_qwen35_nothink_prompt`.
   Expected: short replies ~2-3 s → ~300 ms.
2. **F16 KV (config.py `huihui-qwen3.5-4b` preset: `kv_cache_type: 1`).** llama.cpp
   PR #23907 makes **q8_0 KV + flash_attn** reserve an F16 dequant SCRATCH sized by the
   WHOLE KV cache → hidden VRAM overhead + a ~65% decode collapse (122→42 t/s; we
   measured ~42). F16 KV has no dequant → no scratch, and Qwen3.5 keeps KV on only
   8/32 layers (DeltaNet) so F16 KV is tiny anyway. Should reclaim the ~0.8 GB gap +
   lift decode. Also set `n_ubatch: 256` (smaller micro-batch trims TTFT on short
   prompts + shrinks the compute buffer). Revert to `8`/`512` to A/B.

## NO-HIDDEN-THINKING — DEFENSE IN DEPTH (DONE + PROVEN, 2026-06-24)
User asked for max robustness ("absolutely sure there is no hidden thinking"). The
GGUF's own chat template (seen in boot log) opens `<think>\n` BY DEFAULT, so any
templated path WOULD reason. Four independent layers now stop it, all in
`src/kenning/llm/inference.py`:
1. **Closed-`<think>` prefill (PRIMARY).** Raw `create_completion` with a
   `<think>\n\n</think>\n\n` assistant prefill — the model is handed a *closed*
   reasoning block, so it can't emit chain-of-thought. All 3 gen methods.
2. **`<think>` stop-guard.** `_qwen35_stops` adds `<think>` (+`<|im_end|>`) to the
   stops, so if the model ever RE-opens a block, generation halts (the tag-strip is
   BLIND to Qwen3.5's untagged reasoning, so this matters).
3. **Jinja template override.** `_build_qwen35_chat_handler` wires a chat handler
   that hardcodes the closed prefill, so even a future `create_chat_completion`
   caller gets no-think (the in-code equivalent of forcing `enable_thinking=false`).
   HTTP path also forces `enable_thinking=false`+`reasoning_budget=0` for qwen3.5.
4. **Audit telemetry (the PROOF).** `_audit_qwen35_output` logs raw token count
   every turn + raises a WARNING / `logs/thinking_audit.jsonl` record on any leak
   signature. `KENNING_THINK_AUDIT=1` records every turn. Token count is a SOUND
   proof: an autoregressive model can't reason without emitting tokens.

**PROVEN** — `scripts/_qwen35_nothink_proof.py` (`logs/_nothink_proof.txt`): every
guarded gen emits NO `<think>` and NO reasoning even under explicit bait ("think it
through step by step"). FINDING: this Huihui-3.5 model does NOT actually leak
reasoning even *unguarded* — it emits an empty `<think></think>` by default
(`reasoned=False` every row). The felt latency on short commands is **verbosity**
(a "Hello" → 73-token ramble), not thinking. Live boot confirms: warmup 12 tok, real
turns 2-37 tok, zero THINKING SUSPECTED; latency tracks token count (2 tok→533 ms,
37 tok→1406 ms). The server was deliberately NOT built: the same llama-cpp-python
0.3.22 *server* shares the create_chat_completion limitation (no robustness gain); a
truly independent 2nd engine needs an upstream `llama-server` binary (ask-first
dependency) — evidence says it's unnecessary.

## SETTLED (don't do)
- **No speculative draft.** The vocab-matched Qwen3.5-0.8B draft is **net-negative**
  (−11%, even at 100% accept) and adds draft+KV VRAM; short instruction outputs gain
  least. ([thc1006 RTX-3090 bench](https://github.com/thc1006/qwen3.6-speculative-decoding-rtx3090))
- **Quant:** stay Q4_K_M (3.01 GB); IQ4_XS (2.67 GB) only if we want the last ~340 MB.

## BUILT — prefix state-cache (gated HARD-OFF, 2026-06-24)
**Status:** implemented in `inference.py`, behind `KENNING_QWEN35_STATE_CACHE`
(default OFF → byte-identical to today). Wired into `generate_stream` only (the
voice hot path); fail-open on any error → full-prefill. Helpers: `_qwen35_stream`,
`_qwen35_cached_stream`, `_qwen35_token_stream`, `_state_cache_enabled`; snapshot in
`self._qwen35_prefix_cache`, cleared on model reload. Uses `generate(reset=False)`
after `load_state` (create_completion has no `reset` param + always rewinds, which
DeltaNet rejects).
**VERIFIED NOT VIABLE (2026-06-24 pm) — keep OFF.** Reworked to a LEAN snapshot
(`_qwen35_capture_state`/`_qwen35_restore_state`: raw `llama_state_get_data`/
`set_data`, skipping the multi-GB scores buffer that stock `save_state`/`load_state`
copies+zeros — that made the round-trip net-NEGATIVE, cached ~200-300 ms SLOWER).
`scripts/_qwen35_state_cache_verify.py` (lean, REAL ~302-token prefix): the lean
restore DOES save ~60-110 ms of prefix re-eval, BUT the cached output DIVERGED from
full-prefill (`MATCH=False`) — the hybrid recurrent-state save/restore desyncs at
realistic prefix sizes (known llama.cpp bugs ggml-org/llama.cpp#21831 + #20225),
producing subtly WRONG callouts. So the cache is correct only for tiny prefixes and
unsafe at real sizes. The benefit is also modest + already hidden by the relay's
end-of-turn overlap (`line_build=1ms`). Net: keep `KENNING_QWEN35_STATE_CACHE` OFF;
the real ~350 ms latency lever is the speculative-overlap fix (scour finding 6), not
caching. Re-test if a future llama-cpp-python bumps past the hybrid-state fix.

**Problem:** Qwen3.5 Gated-DeltaNet has **no prompt-cache reuse / context-shifting**
(`cache_reuse is not supported by this context`) — the linear layers' sequential
recurrent state can't rewind to an arbitrary prefix. So the full ~924-token persona
prompt **re-prefills every turn (~433 ms, uncacheable)**. (Standard-attention Qwen3
*can* prefix-reuse, but we don't use caching today — the `LlamaRAMCache` was disabled
for a TTFT regression — and the workaround below neutralizes the gap.)

**Workaround — state snapshot/restore (works on DeltaNet; not a prefix rewind):**
1. Once (boot/first use): prefill the FIXED persona/system prompt, then snapshot the
   FULL model state (KV cache + DeltaNet recurrent/SSM state) via
   `llama_state_get` / llama-cpp-python `save_state()`.
2. Per turn: `load_state()` the snapshot → prefill ONLY the new tokens (the callout) →
   generate. Restoring an exact recorded snapshot reconstructs the recurrent state
   perfectly — we never ask it to "rewind to position N" (the unsupported op).

**Effect:** per-turn prefill ~433 ms (924 tok) → ~50 ms (new tokens) → likely pushes
the LLM entirely inside the speculation window. Works for Qwen3 too (so caching is not
a reason to prefer Qwen3 over Qwen3.5).

**Catches (verify before relying on it):**
- Needs a **custom inference path** (manual `eval` + `save_state`/`load_state`), not
  `create_chat_completion`.
- Prompt must be `[fixed persona prefix] + [per-turn content]` — anything dynamic
  BEFORE the callout breaks the snapshot match → fall back to full prefill.
- **Must confirm 0.3.22's `save_state` actually captures the DeltaNet recurrent/SSM
  state** (recent hybrid state-handling regressions make this worth a quick test).
- Cheaper alternative to try first: just shrink the ~924-token persona prompt (it's
  re-prefilled every turn, so trimming it is a per-turn win, not one-time).

## Stability heads-up
llama.cpp's `qwen35` path is bug-prone right now: prompt-cache SAVE crash
(`ggml_backend_cuda_synchronize`, CUDA illegal access — `--cache-ram 0` half-helps),
heap-buffer OOB (#20093), regressions Mar→Apr 2026. A llama-cpp-python bump may fix
#23907 + the crash together. If the 3.5 ever crashes mid-response, this is why.
