# Ultron 1.0 — Architecture & Implementation Roadmap

**Status:** DRAFT v0.9 (2026-06-20). Grounded in recon (`01_recon/00_codebase_map.md` + 22 raw docs) and
the landscape brief (`02_research/00_landscape_brief_opus.md`) + live 8B probe. Six decisions marked
**[PENDING BOARD]** are confirmed/tuned when the research board (`02_research/board/`) completes; the
architecture itself is stable (the pivot is recomposition of existing machinery).

> Read with `01_recon/00_codebase_map.md` open — every attach point cites the line refs there.

---

## 0. Vision (what Ultron 1.0 is)

Ultron stops being a deterministic-snap relay and becomes an **LLM-authored, intent-routed teammate**:

1. **Every spoken response is authored by the 8B LLM.** Deterministic matchers are RETIRED into
   **routers**: they detect intent, pick a curated **prompt template**, and inject the matching snap
   lines + agent/flavor libraries as **in-context exemplars**. The LLM writes the final line (incl. its
   own context-fitting flavor tail).
2. **Optional wakeword / always-listening.** Ultron always transcribes and, per finalized utterance,
   classifies intent into **{RELAY_TO_TEAM, PRIVATE_REPLY, IGNORE}** via a cheap layered gate, escalating
   to the 8B only in the undecided band. Wakeword still works (a strong feature, not a gate).
3. **Flavor = verbosity.** `no / low / high` flavor controls reply length/verbosity (prompt-driven, per
   route), PLUS a separate flavor-tail on/off. Persona stays strictly Ultron.
4. **Keep everything.** Agent libraries, aggregate libraries + ingestion pipelines preserved; legacy paths
   RETIRED-not-removed (flag-gated, revisitable). 10GB VRAM cap, quality-first.

---

## 1. Target pipeline (new control flow)

```
mic (always capturing) ─► wake detector (optional) ──┐
                          rolling VAD + Smart-Turn ───┤
                                                      ▼
                         STT (faster-whisper turbo, domain-biased)  → raw_stt
                                                      ▼
                         L2+L1 normalization (UNCHANGED) → text      [zero-mistakes gate preserved]
                                                      ▼
        ┌──────────────  SCENARIO GATE  (new: UltronIntentGate) ───────────────┐
        │  features = rules + EmbeddingGemma sim(snap-exemplars) + RapidFuzz +  │
        │             relay-intent + recency + wake; log-odds fuse → tau;       │
        │  8B classifier ONLY in undecided band; output ∈ {RELAY, PRIVATE, IGNORE, COMMAND_LOCAL} │
        └───────────────────────────────┬──────────────────────────────────────┘
              IGNORE → discard            │ RELAY / PRIVATE / COMMAND_LOCAL
                                          ▼
                         ROUTER  (new: UltronRouter — repurposes match_relay_command +
                                  build_relay_line's 28-step taxonomy + semantic router)
                                  → RouteDecision{ template_id, slots, addressee(s),
                                                   exemplars[], agent_context[], verbosity,
                                                   flavor_tail: bool, channel, is_compound }
                                          ▼
                         PROMPT ASSEMBLER  (new: build_ultron_prompt)
                                  system = persona + register + verbosity + tail directive (+ grammar note)
                                  user   = slots/callout(s) + injected exemplars + agent kit context
                                  [stable prefix first → cacheable; variable callout last]
                                          ▼
                         8B LLM  (Josiefied-Qwen3-8B) via generate_stream(system_prompt=, sampling=,
                                  enable_thinking=<route-dependent>, grammar=<compound?>, suppress_memory_context=True)
                                  → <think> stripped→TRACE ; content streamed
                                          ▼
                         POST-VALIDATE (reuse _output_keeps_facts / _repair_against_input / _literal_relay
                                  fallback; _strip_artifacts; _cap_*; _ensure_addressee)
                                          ▼
                         CHANNEL: RELAY → play_to_device (VoiceMeeter B1 + PTT, _shape_for_team DSP)
                                  PRIVATE/COMMAND_LOCAL → tts.speak_stream (speakers/OBS)
                                          ▼
                         TRACE every stage → logs/usage_trace.jsonl + per-turn detailed trace
```

Everything above the SCENARIO GATE is unchanged. The GATE, ROUTER, PROMPT ASSEMBLER, and the
LLM-as-primary path are the new/rewired pieces; all reuse existing components.

---

## 2. Component designs

### 2.1 UltronIntentGate (always-listening 3-way) — `src/kenning/addressing/` (extend)
- **Base:** recover the log-odds **fusion design from commit `9438fc5`** (graded `rules.features()`,
  `_ADDR_W` weights, recency prior `_addr_b0`, cost-asymmetric `tau`, Flan-only-in-band, `matcher_hit`).
  [PENDING BOARD: confirm fusion is the right base vs an 8B structured-token classifier — A2/B1/B2/C1.]
- **Extend output** to `{RELAY_TO_TEAM, PRIVATE_REPLY, IGNORE, COMMAND_LOCAL}` (COMMAND_LOCAL = device/
  flavor/thinking toggles, Spotify, stop — handled locally, may or may not speak).
- **New features:** `snap_exemplar_sim` (max cosine to the snap-callout exemplar set via the EmbeddingGemma
  sidecar + RapidFuzz fuzzy max-ratio), `team_relay_hint` (the relay-intent gate result folded in as a
  feature, not a separate stage), `talking_to_discord`, `talking_to_stream`, `tactical_token_density`.
- **Escalation:** when `|fused_logit|` is in the undecided band, consult the **8B** for a single structured
  class token (constrained), not Flan. Flan retired-not-removed as fail-open. [PENDING BOARD: band width +
  whether 8B latency is acceptable per-utterance in always-listening — B2/C1.]
- **Calibration:** fit weights + `tau` from the labeled MP3 battery + `logs/addressing.jsonl`. Cost-asymmetric
  (false RELAY ≫ worse than missed RELAY; false PRIVATE during a match is bad too). [PENDING BOARD: method —
  logistic/Platt, class-imbalance handling — B3/C1.]
- **Wakeword:** present → large positive feature toward RELAY/PRIVATE (decided by content), not a gate.
- **Config:** `addressing.always_listening: bool` (default keep wake-required until calibrated), `tau` knobs.
- **Retire-not-remove:** `_FOLLOWUP_WAKE_RE`/`_DIRECT_ADDRESS` bypasses, the 30s window concept, Flan-primary.

### 2.2 UltronRouter — `src/kenning/audio/` (repurpose relay_speech matchers)
- Wrap `match_relay_command` + the `build_relay_line` 28-step taxonomy + `relay_route_info` + the semantic
  router into a `route(text, scenario) -> RouteDecision`. Each existing snap branch maps to a `template_id`
  and supplies its curated lines as **exemplars** (not as the final output).
- `RouteDecision` fields: `template_id`, `slots` (from `_parse_callout_slots` / M1 grammar — now an LLM-side
  slot-fill hint), `addressee(s)`, `exemplars[]` (selected via `_tail_selector` MMR from the matched pool +
  AGENT_FLAVOR), `agent_context[]` (kit facts for named agents), `verbosity`, `flavor_tail`, `channel`,
  `is_compound`, `compound_parts[]`.
- **Templates** live in `audio/llm_prompts.py` (the SSOT) as a small registry keyed by `template_id`
  (relay_callout, enemy_action, self_status, economy, agent_select, social_reaction, identity, marvel,
  think_respond, private_answer, compound, …). One template = one curated system+structure.
- **Retire-not-remove:** the direct-return snap outputs stay behind `KENNING_U1_LLM_ROUTE` (default ON in
  u1.0) as a deterministic FAST-PATH fallback + the exemplar source.

### 2.3 Prompt assembler — `audio/llm_prompts.py` + new `audio/ultron_prompt.py`
- `build_ultron_prompt(route) -> (system_prompt, user_prompt, sampling)`.
- **System** (stable, cacheable prefix): Ultron persona core + register (relay vs private) + **verbosity
  directive** (no/low/high → explicit length+style rules; e.g. "no flavor: bare callout, ≤8 words"; "high:
  one vivid in-character line + a short flavor tail") + **flavor-tail directive** (author one fitting tail /
  none) + output rules (plain spoken text, NO stage directions/markdown/quotes, keep facts EXACT, never break
  character, name no vendor/model) + (if compound) the grammar contract description.
- **User** (variable, last): the callout(s)/slots + injected exemplars (k≈3–6 via MMR) + agent kit context for
  named agents + recent-line anti-repeat. [PENDING BOARD: exemplar count/ordering, verbosity calibration — B7/B9/B10.]
- **Sampling:** per-route profile (relay: tight max_tokens, stop seqs, min_p; private/answer: larger). Qwen3
  recommended sampling per think/no_think. `enable_thinking` route-dependent (off for fast relays; on for
  ambiguous answers / the gate's hard band). [PENDING BOARD: exact sampling — B14.]

### 2.4 8B serving — `src/kenning/llm/inference.py` (extend)
- Default preset → **`josiefied-qwen3-8b`** on **GPU** (`gpu_layers=-1`) within 10GB. Keep the device-switch
  voice command (GPU↔CPU) for mid-match VRAM handback. Keep the 0.1.1-style **model lab** A/B
  (josiefied-8b vs qwen3.5-9b vs qwen2.5-7b-abliterated). [PENDING BOARD: final model + Qwen3.5-9B compare — B13/C3.]
- **Windows DLL fix:** add `os.add_dll_directory(<torch>/lib)` before `import llama_cpp` (probe-confirmed).
- **Thinking trace:** route the stripped `<think>` text to the trace log (don't discard); parse manually.
- **Constrained decoding:** wire `sampling.grammar` (GBNF) for compound callouts. [PENDING BOARD: grammar
  reliability/speed — B9/C4.]
- **Prefix caching / speculative decoding:** design the prompt for a stable prefix; enable prefix cache +
  draft model in the LATER latency pass (quality-first now). [PENDING BOARD: in-process caching specifics — B15/B16.]

### 2.5 Agent-context injection — reuse `_agent_flavor.py` + new kit facts
- Build/curate an accurate **agent kit table** (abilities + ultimate per agent) — the 8B hallucinated Sova's
  kit, so this is mandatory. Inject the kit + situation tails for the addressed agent(s) into the prompt.
  [PENDING BOARD: authoritative 2026 kits/roster/maps — B22/B23/B24/C7.]

### 2.6 Combined back-to-back callouts → ONE response
- The gate/router detects a compound utterance (`_as_compound_callout` split + the new endpointing).
  Build ONE prompt listing each callout as a slot; the LLM emits one combined response (all callouts strung
  together in-persona). Use a **grammar** to keep it parseable + fact-correct. NOT N LLM calls. [PENDING
  BOARD: compound handling + grammar — B20/B9/C4.]

### 2.7 Verbosity + flavor toggles
- `no/low/high` flavor → a `verbosity` enum threaded into the system prompt. Keep `match_flavor_toggle`
  (tail on/off) and add a `match_verbosity_command` ("no/low/high flavor"). Config fields + voice commands +
  GUI overlay. Retire nothing.

### 2.8 Tracing — `trace.py` + `usage_trace.jsonl` (extend)
- Add per-turn fields: raw_stt, each normalization transform, gate features+scores+decision, route decision
  (template_id, exemplars, verbosity, channel), the FULL assembled prompt (system+user), the `<think>` trace,
  the raw LLM output, post-validation actions, final spoken line, channel. This is the user-required deep trace.

---

## 3. Config / flags (Pydantic `extra=forbid` → add to schema first)
New section `ultron_v1` (or extend existing): `llm_route_enabled` (default ON), `always_listening` (default
OFF until calibrated), `verbosity` (no/low/high; default low), `flavor_tail` (on/off), `intent_gate.tau*`,
`compound_grammar_enabled`, model preset default → josiefied-qwen3-8b. Mirror the `barebones_*` retire pattern
for every legacy path. GUI overlay + voice commands wired.

---

## 4. Testing strategy (Phase 5, built first + grown each batch)
Reuse `InjectableCapture` + `run_corpus.py` boot/inject pattern. Build the **enhanced battery**:
- Commands embedded in non-triggering text (must fire only the intended command).
- Full non-triggering paragraphs (stream narration / Discord) → expect IGNORE.
- Back-to-back command strings → expect ONE combined LLM response.
- New `Case` fields: `intent` (relay/private/ignore), `channel`, `verbosity`, `expected_callouts[]`.
- New negative packs: `_DISCORD_PACKS`, `_STREAM_PACKS`, `_ME_ONLY_PACKS`.
- Simulate as mic input through the FULL pipeline (wake-spliced + wake-free variants for always-listening).
- **Deep per-stage traces** (the §2.8 schema), incl. full prompt + thinking trace + outputs.
- Component unit tests AND end-to-end. Run after every batch + regression guard (golden digest re-bless process).
- [PENDING BOARD: harness validity given short-jargon TTS noise; real-voice need — B19/C6.]
Known: short-jargon synthetic STT is poor → the battery validates ROUTING/INTENT/COMBINED-OUTPUT primarily;
short-callout STT fidelity is a separate (real-voice) concern. Find `training/crosscheck_ultron/*.wav` (A4).

---

## 5. Implementation roadmap (sequenced, tested increments — NO deferrals)
Each step: implement → unit tests → E2E battery slice → regression sweep → commit (+ tag at phase ends).

- **M0 Serving + harness foundation:** DLL fix; default preset josiefied-qwen3-8b (GPU); `<think>`→trace;
  worktree test env (PYTHONPATH/venv); enhanced-battery scaffold + trace schema + InjectableCapture wake-free.
- **M1 Prompt assembler + template registry + 8B relay path (flavor ON, verbosity):** route the existing
  relay intents through templates+exemplars+agent-context; post-validate; behind `KENNING_U1_LLM_ROUTE`.
- **M2 Verbosity (no/low/high) + flavor-tail directive + toggles.**
- **M3 Agent-context kit table + injection** (accurate kits) + fact-fidelity validators on LLM output.
- **M4 Compound callouts → one grammar-constrained combined response.**
- **M5 UltronIntentGate (3-way) + calibration** from the battery + always-listening (behind flag, default OFF
  until false-accept acceptable).
- **M6 PRIVATE_REPLY path** (me-only answers) + IGNORE handling + scenario tracing.
- **M7 Retire-not-remove pass:** flag-gate all legacy deterministic-output paths; unify the lean/full dispatch
  duplication; confirm anticheat posture; golden re-bless.
- **M8 Latency pass (only after quality):** prefix caching, draft/speculative, KV quant, ubatch, exemplar
  pruning. Re-measure baselines.
- **M9 Full battery green + real-world readiness:** full sweep, traces reviewed, docs/CLAUDE.md/codebase_structure
  updated, memories updated, tagged release `ultron-1.0`.

## 6. Risks & mitigations
- Always-listening false-accepts (the 114/session lesson) → calibrate hard, default OFF until proven, wake-as-
  feature, cost-asymmetric tau, IGNORE is the safe default.
- LLM fact drift on callouts → keep `_output_keeps_facts`/`_literal_relay` as a hard guard; grammar for compound.
- Persona/leak with abliterated model → strong persona prefix + exemplars + identity/leak guards (existing). [C5]
- VRAM > 10GB → measure peak; Q5 8B + KV fits; draft optional. [B16/C3]
- Latency of route-all-through-LLM → quality-first now; M8 caching/draft; deterministic fast-path fallback stays.
- Rate limits on agent boards → small waves (learned).

## 7. Versioning / rewind
Commit per increment; tag phase ends (`u1.0-mN-*`); branch `claude/infallible-kepler-0a865d`. 0.1/0.1.1 standalone
builds on `E:\` untouched. Every legacy path is flag-gated (not deleted) → instant behavioral rewind via flags;
git revert for code. Final tag `ultron-1.0`.

> **Finalize after board:** resolve the 6 [PENDING BOARD] decisions, fold `02_research/board/` findings into
> §2/§4/§5, then begin M0.

---

## 8. POST-BOARD RESOLUTIONS (FINAL — 2026-06-20, from `02_research/02_research_synthesis.md`)

The research board (41 agents) resolved all 6 PENDING decisions. Net changes to the plan:

- **[D1 model] FINAL:** Josiefied-Qwen3-8B-abliterated, llama-cpp-python 0.3.22 in-process, **Q5_K_M** (on
  disk; Q6_K optional). **Qwen3.5-9B HARD-BLOCKED** (FGDN_AR abort). **Hard-cap `n_ctx=4096`** in the
  constructor (VRAM). No speculative decoding. STT stays CPU → VRAM headroom OK.
- **[D-thinking] FINAL (NEW):** **thinking OFF by default for ALL persona/relay paths** — reasoning *harms*
  roleplay (arxiv:2502.16940) and breaks grammar (#20345). Keep the toggle + explicit "think and respond";
  capture `<think>`→trace only when on. Startup assert: no `<think>` leaks into relay output.
- **[D2 gate] FINAL:** build the 3-way gate (ASR-confidence pre-reject → rules+embedding+fuzzy log-odds →
  8B-in-undecided-band, fail-CLOSED to IGNORE) on the recovered `9438fc5` fusion, extended to
  {RELAY_TO_TEAM,PRIVATE_REPLY,IGNORE,COMMAND_LOCAL}. **DEFAULT OFF (opt-in); wake-word = competitive default.**
  Realistic F1 ≈ 0.65–0.75. **Prerequisite: VoiceMeeter mic isolation check.** Post-IGNORE 2-3s skepticism window.
- **[D3 calibration] FINAL:** cost-ratio τ (τ*≈0.75) to start; Platt once ≥100 labels/gate; the text-injection
  battery supplies initial labels (50 RELAY/50 PRIVATE/100 IGNORE incl. teammate/Discord/stream); real-session
  `logs/addressing.jsonl` for production. Drop the LLM fusion column if AUC<0.55.
- **[D4 grammar] FINAL (CHANGED):** **NO grammar on the multi-token hot path** (up to 6× CUDA slowdown +
  fail-open). Combined callouts = **free-text generation from a structured prompt** + strip `<think>` +
  reuse `_output_keeps_facts`/`_repair_against_input`/`_literal_relay`. Gate token = first-word prefix match,
  fail-closed (optional logit_bias). Benchmark grammar before any future hot-path use.
- **[D5 serving] FINAL:** stay llama-cpp-python in-process (all alternatives fail a hard constraint).
  Add the `torch/lib` DLL fix. Consider 0.3.31 only in a test env later.
- **[D6 harness] FINAL (EXPANDED):** **TWO harnesses** — (1) **text-injection routing/intent harness =
  PRIMARY/deterministic/calibration source** (build on `trace_corpus_full.py`); (2) the **audio MP3 E2E**
  the user asked for (acoustic integration + regression + per-stage traces incl. full prompt + `<think>`),
  numbers reported RELATIVE. Add hallucination-pressure IGNORE tests + wake-free variants. **Fix the
  `_DOMAIN_PROMPT` shadow bug in M0.** Real-session `usage_trace.jsonl` spot-check = ground truth.
- **Codebase corrections (A_llm_route):** LLM rephrase call is `relay_speech.py:6326-6374` (not 6012=def);
  add a `_sanitize_user_input` call on the `system_prompt=` branch (`inference.py:~989`) to restore injection
  defense; the `'abliterat' in model_path` guard (`orchestrator.py:9031`) auto-pins Ultron persona when the 8B
  loads (DESIRED). `ANSWER_SYSTEM_FOR` (`llm_prompts.py:123`) is the route-subtype extension point.
- **JIT reads:** C_route_llm + C_persona before M1; C_domain before M3 (agent kits); C_anticheat before M7.

**Roadmap unchanged (M0→M9), with M0 also doing: DLL fix, n_ctx cap, thinking-off + startup assert,
domain-prompt bug fix, the text-injection harness scaffold, sanitize-on-override.**
