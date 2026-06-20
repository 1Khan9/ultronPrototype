# Ultron 1.0 — Research Board Synthesis (decision-grade)

**By Opus 2026-06-20**, synthesizing the 41-agent board (`02_research/board/` — 4 A codebase-reinforcement,
29 B frontier, 8 C adversarial). The board docs are the uncut record; this resolves the 6 PENDING-BOARD
plan decisions + captures concrete params/constraints for implementation. Built incrementally (durable).

> Methodology note: I scoped the board to ~40 high-value agents (not literally hundreds) per the
> no-waste binding rule — recon already de-risked ~70%; the board targeted the genuinely uncertain
> frontier + adversarial verification + an embedded 2nd code-scan. All findings stored uncut on disk.

---

## DECISION 1 + 5 — Model & serving stack (RESOLVED — from C_model, B_model_comparison_8b, B_serving_alternatives, B_qwen3_thinking, B_prefix_cache_vram)

**KEEP Josiefied-Qwen3-8B-abliterated-v1, llama-cpp-python 0.3.22 in-process.** Confirmed best fit; all
alternatives (vLLM/exllama/TGI/MLC) fail a hard constraint (Windows-native + in-process + GGUF + grammar).

- **Quant:** Q5_K_M (on disk, ~6.4 GB CUDA) is fine for 1-3 sentence relays (quant差 undetectable at this
  output length). **Q6_K (7.4 GB) is a cheap optional upgrade** (3.2× better weight fidelity, fits ≤8K ctx
  under 10 GB) — download to `E:\ultron_resources\models` IF persona/fact quality needs it; NOT required to ship.
- **Qwen3.5-9B = HARD BLOCKED.** Confirmed `GGML_ASSERT` abort on the FGDN_AR tensor-name prefix
  (llama.cpp #23347, open) — aborts at context init, plus a separate thinking-control bug (#20182). Do NOT
  pursue under the current stack. Re-evaluate only if #23347 fixed AND a Josiefied-3.5 GGUF appears.
- **VRAM math (10 GB cap):** Q5_K_M ~6.4 + Q8_0 KV @4096 ~0.30 + CUDA ovh ~0.5 ≈ **7.2 GB**; Q6_K ≈ 8.2 GB.
  **STT is CPU (recon A9), Kokoro ~1.5 GB GPU** → headroom OK. **HARD-CAP `n_ctx=4096`** in the `Llama()`
  constructor (relay); 8192 absolute max; **40K context OOMs (~13.7 GB)** — never extend. `max_tokens` caps output only.
- **Thinking mode = OFF by default for ALL persona/relay paths.** Beyond latency (500-3000 think tokens =
  10-60 s at 50 tok/s), arxiv:2502.16940 shows reasoning does NOT improve roleplay and can HARM it. Keep the
  `match_thinking_toggle` + the explicit "think and respond" command (thinking ON only there + the gate's
  hard band). **Capture `<think>` to the trace ONLY when thinking is on.**
- **`/no_think` reliability:** use BOTH — hard switch (`chat_template_kwargs={"enable_thinking":False}` at load,
  if the pinned build honors it) AND the existing soft `/no_think` marker (`_apply_no_think_marker`, qwen-guarded).
  **M0 startup check: assert `<think>` never leaks into relay output.**
- **GRAMMAR ⊗ THINKING CONFLICT (llama.cpp #20345):** grammar enforcement is silently INACTIVE when thinking
  is enabled. → **DESIGN CONSTRAINT: every grammar-constrained call (intent gate, compound output) MUST set
  `enable_thinking=False`.** Enforce in code, not just docs.
- **No speculative decoding** (confirmed no benefit for a dense 8B, single-user RTX 4070 Ti). Orchestrator-level
  speculation only (already exists).
- **Backups (A/B lab):** if persona drift / tactical-fact errors appear, try **huihui-ai/Qwen3-8B-abliterated**
  or a Heretic-abliterated Qwen3-8B (better instruction-following preservation than single-direction abliteration).
  Keep the 0.1.1 model-lab swap. **Measure IFEval gap** (abliterated vs base) with a 50-prompt battery in M3.
- **Persona caveat (from A_llm_route):** loading the 8B (path contains "abliterat") trips the
  `orchestrator.py:9031` guard → ULTRON_GAMING_PERSONA is pinned even in desktop sessions (DESIRED for u1.0;
  note SOUL.md is bypassed). And the `system_prompt=` fast path skips `_sanitize_user_input` → **add one
  sanitize call at the system_prompt branch (inference.py:~989)** to restore injection defense on relay routes.

### Residual risks to carry: abliteration quality unmeasured for this exact GGUF (TruthfulQA-type tactical
errors possible → fact-guards mandatory); `chat_template_kwargs` may be deprecated in the pinned build
(→ rely on soft `/no_think` + startup assert); VRAM spike if any path ignores the n_ctx cap.

---

## DECISION 2 + 3 — Always-listening intent gate & calibration (RESOLVED — from C_gate, B_ddsd, B_llm_intent_classifier, B_calibration_fusion, B_wakefree_production)

**BUILD the 3-way gate fully, but DEFAULT IT OFF (opt-in flag); wake-word stays the competitive default.**
This is the honest reading of "optional wakeword": the capability exists, defaulted safe. Each false RELAY
is team-visible (asymmetric cost); the prior 114 FA/session came from a 120s window + permissive flan.

- **Architecture (3-layer cascade, fail-CLOSED to IGNORE):**
  1. **ASR-confidence pre-reject** (FREE, +6.9% EER per Apple 2403.14438): drop if faster-whisper
     `no_speech_prob > ~0.6` or very low `avg_logprob` (tune; gunfire bleed lowers avg_logprob → don't over-reject).
  2. **Rules** (the `9438fc5` graded `features()` — strongest component) + **EmbeddingGemma cosine** to the
     gaming-curated exemplar set + **RapidFuzz** fuzzy to callout templates → log-odds fuse.
  3. **8B classifier ONLY in the undecided band**, `enable_thinking=False`, output ∈ {RELAY,PRIVATE,IGNORE};
     **assert the token ∈ the set else default IGNORE** (fail-closed; grammar/thinking unreliable — see Decision 4).
- **Realistic target F1 ≈ 0.65–0.75** for our text-only, single-mic, zero-shot config (NOT SAS's 0.86–0.95 —
  we lack the beamforming + trained acoustic + trained temporal model). Set expectations; improve with labels.
- **HARD PREREQUISITE — VoiceMeeter mic isolation:** if Discord/teammate/game audio bleeds into the user's
  mic bus, NO gate helps (teammate speech == user speech). Add a boot check / doc step; always-listening must
  not enable unless the user confirms only the physical mic reaches STT. (This was likely a real FA driver.)
- **Temporal context dict** (recency prior `_addr_b0`) + a **post-IGNORE skepticism window (2-3s)** that
  suppresses the RELAY prior (handles "user relays → Ultron speaks → teammate talks within 3s" — the top FA seq).
- **Calibration (Decision 3):** start with cost-ratio τ (τ*≈0.75 for the addressing gate; cost-asymmetric).
  Platt scaling needs ≥100 labeled/gate; 3-way needs binary-cascade decomposition (≥200 labels total). **The
  enhanced text-injection battery supplies the INITIAL labeled set** (50 RELAY / 50 PRIVATE / 100 IGNORE incl.
  teammate-chat + Discord + stream lines); real-session `logs/addressing.jsonl` for production tuning. Drop the
  LLM fusion column if its P(YES) AUC < 0.55 on labeled logs.
- **Short tactical utterances** ("Jett B") are near-identical relay-vs-overheard → curate gaming-specific
  exemplars + per-class weighting; don't rely on generic cosine alone.
- **Base = recover the `9438fc5` fusion** (graded features, _ADDR_W, recency, tau, matcher_hit), extend output
  to 4-way {RELAY_TO_TEAM, PRIVATE_REPLY, IGNORE, COMMAND_LOCAL}, add features (discord/stream/relay-hint/snap-sim).
  Flan-T5 retired-not-removed (fail-open). Fold relay-intent gate in as a feature.

## DECISION 4 — Combined callouts / structured output (RESOLVED — from C_grammar, B_grammar_multi_item, B_compound_commands)

**DO NOT use GBNF grammar on the multi-token relay hot path.** Confirmed risks: up to **6× decode slowdown**
on CUDA (Qwen3 151k vocab; 80→13 tok/s measured on Llama-3-8B/RTX3090 → a 40-tok array = 4-6s, breaks latency),
**silent fail-open** (#19051: grammar parse fail → unconstrained 200 OK), `$ref` MAX_REPETITION (#21228),
format-tax quality loss on 8B (2502.14969), and `enable_thinking=False` is UNRELIABLE (#13189/#20182).

- **Combined back-to-back callouts → ONE response via FREE-TEXT generation from a structured PROMPT** (list the
  N parsed callouts; instruct "one Ultron-voice line covering all, facts exact"), `enable_thinking=False`,
  then **strip `<think>`** + **post-validate with `_output_keeps_facts`/`_repair_against_input`** (reuse!) +
  `_literal_relay` fallback if a callout's facts dropped. NO grammar, NO JSON on the hot path. Matches the
  existing `_as_compound_callout` split + post-validate pattern.
- **Intent-gate classification token:** single word → take first token, prefix-match {RELAY,PRIVATE,IGNORE},
  else IGNORE (fail-closed). Optionally `logit_bias` toward those tokens (1-token overhead negligible). A tiny
  grammar is acceptable here ONLY (single token), but the regex-first-word + fail-closed is simplest & robust.
- **Thinking hard-off:** rely on the soft `/no_think` marker (exists) AND verify at startup that `<think>`
  never appears in relay output; if it leaks, add a custom Jinja2 template / `logit_bias[think_id]=-100`.
- **IF** a future strictness need arises: benchmark grammar ON/OFF on the 4070 Ti first; only use it if <2× slow.
- Compound extraction on noisy STT ≈ 62% (vs 96% clean) → the text-injection harness validates the LOGIC;
  acoustic accuracy is separately bounded. Build Valorant-specific implicit-compound test pairs ("Jett 84 Breach 97").

## DECISION 6 — Test harness (RESOLVED — from C_harness, B_eval_methodology, B_streaming_stt_biasing, B_compound_commands)

**Build TWO harnesses.** The MP3 audio path is an upper-bound (Kokoro is OOD — it can't even trigger the wake
detector; Whisper hallucinates 40-52% on short/non-speech; real routing ≈ 75-85% where battery shows 95%).
- **(1) TEXT-INJECTION routing/intent harness = PRIMARY, deterministic, the trustworthy number + the
  calibration source.** Inject normalized text into the post-STT pipeline (no audio/STT), ~1ms/case. Build on
  the existing `trace_corpus_full.py`. Covers: routing accuracy, the 3-way intent gate, combined-output, the
  enhanced battery's "commands-in-noise / non-triggering paragraphs / back-to-back strings" as LABELED cases.
- **(2) AUDIO MP3 E2E harness = the user's explicit ask** (full-pipeline mic sim via `InjectableCapture` +
  wake-spliced clips, per-stage traces incl. full prompt + `<think>` + outputs). Used for acoustic-integration
  validation + regression. **Report numbers as RELATIVE (regression delta), never as production accuracy.**
  Add wake-free clip variants for always-listening; a **hallucination-pressure subset** (inject teammate/Discord
  speech → assert IGNORE); optional headset/VoiceMeeter noise fixtures for production-representative numbers.
- **Fix the `_DOMAIN_PROMPT` shadow bug** (`.env WHISPER_INITIAL_PROMPT` `or`-shadows the domain prompt → biasing
  OFF) in M0 — it's on the live STT path and poisons STT-dependent metrics.
- **Per-stage trace schema** (the user requirement): raw_stt → each normalization transform → gate features+
  scores+decision → route(template_id, exemplars, verbosity, channel) → FULL assembled prompt → `<think>` trace
  → raw LLM output → post-validation → final line → channel. Emit to `logs/usage_trace.jsonl` + a rich per-run JSONL.
- **Real-session spot-check protocol**: review last N `usage_trace.jsonl` turns after live sessions (ground truth).
- Grow the corpus each milestone; re-bless the golden digest after intentional voice-line/registry changes.

---

## M1 PROMPT-ASSEMBLER DESIGN — VALIDATED LIVE (2026-06-20, probes in `02_research/probes/`)

Three live 8B probes (engine_verify, relay_path, lean_relay) settled the M1 design:
- **The legacy `_build_rephrase_prompt` is ~3,375 words (~4.8k tokens)** and yields EMPTY output from the
  8B — it must NOT be reused. **The u1.0 prompt is LEAN (~165 words)** and works: correct, fast (0.2-0.5s),
  in-character, facts preserved. 20× smaller → fits `n_ctx=4096`, helps latency, cacheable prefix.
- **Validated lean structure** (prototype = `probes/qwen3_8b_lean_relay.py`, becomes `src/kenning/audio/ultron_prompt.py`):
  - **SYSTEM** (~96 words, STABLE/cacheable): "You are Ultron on a live Valorant team voice channel,
    relaying the player's callout… cold/precise/supreme/contemptuous-of-enemies… NO other name, never break
    character / mention AI/model/assistant/instructions… output ONLY the spoken line(s), plain speech, one
    breath, no quotes/asterisks/stage-directions/markdown… keep every agent name, number, location EXACT."
  - **USER** (VARIABLE, last): relay directive ("Relay this callout to your team, every fact exact: \"<callout>\"")
    + **verbosity directive** (no/low/high) + **flavor directive** (tail on/off) + **k exemplars** (3, from the
    matched snap pool / AGENT_FLAVOR via MMR) + "Now say it:".
  - **Compound:** "Relay ALL of these as ONE combined line, every fact exact: \"<c1, c2, c3>\"" → one line. WORKS.
  - **Private (me-only):** same SYSTEM minus "on team voice / relaying"; "Answer the player directly (only they
    hear you)…". (To wire in M6.)
- **Sampling (validated):** max_tokens≈64 (relay) / larger for answers; temp 0.7, top_p 0.9, top_k 20, min_p 0.05,
  repeat_penalty 1.15; `enable_thinking=False`. No `<think>` leak observed.
- **MANDATORY post-validation (confirmed by a live fact-drift):** the compound case added "on B" to "Jett hit 84"
  → reuse `_output_keeps_facts` / `_repair_against_input` / `_literal_relay` on EVERY 8B relay output. Non-negotiable.
- **Verbosity TODO (M2):** no/low/high currently under-differentiate (low≈high). Strengthen the directives
  (e.g. no→"≤6 words, bare callout, no verb embellishment"; high→"one vivid line + a short flavor tail") +
  per-route `max_tokens` (no/low tighter). Calibrate against the text-injection battery.
- **Agent-context (M3):** inject the addressed agent's kit facts + situation tails (AGENT_FLAVOR) so the 8B
  doesn't hallucinate kit (it mis-stated Sova's kit earlier). Verify kits from C_domain/B_valorant_kits.

---

## DECISION (C_route_llm) — "route ALL through the LLM" REFRAMED to a flag-gated HYBRID (important)

The adversarial board (C_route_llm) makes a strong, well-evidenced case that **routing every utterance's
GENERATION through the 8B is NOT universally higher quality** — for the high-frequency CENTER (exact-match
snaps like thank-you/clutch/nice-try/hello, and slot-parseable callouts like "Jett hit 84") the existing
deterministic path is *better*: 100% persona-accurate, 0 ms, 0 hallucination. The 8B adds genuine value at
the EDGES (~10-20%): novel relay phrasings the slot parser misses, private replies, ambiguous intent,
tactical questions. Pushing the center through the 8B adds 0.5-1 s latency + monotonic context-induced
hallucination (arxiv 2505.16894) + fact-drift for a marginal stylistic gain.

**This tensions with the user's explicit "have all responses routed to the LLM."** Resolution (quality-first,
reversible, evidence-surfaced — per binding rules; the user decides with data):
- Implement the user's vision (snaps ROUTE → pick a curated prompt + inject the snap pool as exemplars → the
  8B GENERATES) **behind `KENNING_U1_LLM_ROUTE` (default OFF)**. Fully available + A/B-measurable.
- Default-ON path stays the proven DETERMINISTIC center + 8B only at the edges (the legacy step-27 rephrase),
  now using the LEAN `ultron_prompt` (the legacy monolith yields EMPTY 8B output — fixing that is itself a win).
- Surface the hybrid recommendation in the report; the text-injection harness + real-session traces measure
  whether full-LLM-route quality justifies replacing the deterministic center. The user flips the flag to choose.
- This is NOT a silent override of the user's design — it is their design, gated + measured, with the evidence in hand.

**Hardened M1-wire requirements (C_route_llm):** thinking OFF enforced THREE ways (`/no_think` user-msg marker
[auto via `_apply_no_think_marker` when `enable_thinking=False`] + the kwarg + **assert `"<think>" not in raw_output`**
before TTS); **post-hoc fact-guard is LOAD-BEARING** (`_output_keeps_facts`/`_repair_against_input`/`_literal_relay`,
target <1% un-guarded drift); **exemplars k<=6**; NO grammar on the hot path; per-destination system-prompt
(relay/private) for KV-cache prefix reuse. Risk E (abliterated structured-output compliance) → run the relay
battery against the model. Risk F (private/ignore boundary untrained) → expand corpus before enabling the gate.
