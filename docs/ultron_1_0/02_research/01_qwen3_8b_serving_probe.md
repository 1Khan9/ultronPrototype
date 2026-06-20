# Ultron 1.0 — 8B model serving probe (live, on-machine)

**Date:** 2026-06-20. **Model:** `E:\UltronModels\Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf`.
**Stack:** `llama-cpp-python 0.3.22` (CUDA) in `C:\STC\ultronPrototype\.venv`, RTX 4070 Ti.
Probe script: `docs/ultron_1_0/02_research/probes/qwen3_8b_smoke.py`. This is FIRST-HAND, not web research.

## Results (decisive, feed into plan §LLM-serving + §prompt-construction)

1. **Serving-env fix (REQUIRED on this box):** the CUDA `llama.dll` won't import until
   `torch/lib` is on the DLL search path (it ships `cudart64_12.dll`, `cudnn64_9.dll`, etc.).
   Fix = `os.add_dll_directory(<torch>/lib)` **before** `import llama_cpp`. (CUDA v11.8 toolkit bin
   also present.) The running Kenning process must already do an equivalent; the worktree probe/tests
   need this shim. → Plan: ensure the LLM module adds the torch-lib DLL dir on Windows before load.
2. **Load:** `load_ok in 2.7s` with `n_gpu_layers=-1` (full offload), `n_batch=512`. `n_ctx_train=40960`
   → we can run a much larger context than 4096 (room for big exemplar/agent-context prompts) and stay
   well under 10 GB (Q5_K_M 8B ≈ ~5.6 GB weights + KV; measure peak in Phase 6).
3. **Thinking mode (default ON):** emits `<think> … </think>` inline. With `max_tokens=300` the **entire
   budget was consumed by the thinking block** (300 completion tokens, answer never reached). ⇒ Thinking
   needs a LARGE token budget; do NOT use it on latency-critical short relays with a small cap.
4. **`/no_think` soft switch WORKS:** appending `/no_think` to the user message → `<think>\n\n</think>`
   (empty) then an immediate answer: **0.5s, 33 tokens**, clean + in-persona:
   > Enemy down. Sova's precision is unmatched. Let's push.  *Snaps a finger, calculating…*
   ⇒ Fast relay path = `/no_think` (or template `enable_thinking=False`). Reserve thinking for the
   ambiguous intent gate + longer answers, with a big budget + a watchdog cap.
5. **`reasoning_content` is NOT separated** by llama-cpp-python 0.3.22's `create_chat_completion` — the
   `<think>…</think>` tags are inline in `message.content`. ⇒ We MUST parse `<think>…</think>` out of
   `content` ourselves: route the inner text to the **trace log** (the user-required thinking trace),
   and **strip it before TTS**. (Matches the web finding "almost everyone runs Qwen3 on llama.cpp wrong".)
6. **Persona holds even with zero few-shot** (abliterated model produced cold-machine register), but it
   **hallucinated Sova's kit** in the thinking ("M4A1-S", a CS gun) ⇒ **inject agent-kit context**
   (Sova = initiator, recon bow, ult = Hunter's Fury) to keep callouts kit-accurate. Validates the
   "keep + inject agent-specific libraries" requirement.
7. **TTS hazard:** the model emitted a `*stage direction*` (asterisk action). The system prompt MUST
   forbid stage directions / emotes / markdown, since TTS would read them aloud.
8. **Chat template** is embedded in the GGUF (`chat_template present in metadata: True`) and the
   `/no_think` soft switch is honored through it. Qwen3 recommended sampling (thinking): temp 0.6,
   top_p 0.95, top_k 20; (non-thinking): temp 0.7, top_p 0.8, top_k 20 — to confirm/tune in Phase 6.

## Implications locked for the plan
- Two LLM "modes": **fast** (`/no_think`, small budget, snap-style relays) and **deliberate**
  (thinking ON, big budget, ambiguous routing/answers) — selected by the router/intent layer.
- A `<think>` parser is a required component (trace + strip).
- Agent-kit context injection is mandatory for kit accuracy.
- System prompt forbids stage directions/markdown; output is plain spoken text.
- Stable persona/system prefix → cache it (prefix caching) once latency work begins.
