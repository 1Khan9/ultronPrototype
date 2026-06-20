# Ultron 1.0 — Implementation State & Continuation Roadmap

**As of 2026-06-20.** Honest status of the build + the precise, de-risked continuation. Read with
`02_research/02_research_synthesis.md` (final decisions) and `01_recon/00_codebase_map.md` (attach points).

## What is DONE, tested, committed (branch `claude/infallible-kepler-0a865d`)
- **Phases 0–4** complete: scaffolding + binding rules + CLAUDE.md; full recon (22 maps + master synthesis);
  my landscape brief; the 41-agent research board + synthesis resolving all 6 key decisions; finalized plan.
- **Frozen test baseline:** 10966 pass / 22 pre-existing fail / 39 skip (`05_testing/00_baseline.md`). Regression rule defined.
- **M0 (serving foundation):** 8B (`josiefied-qwen3-8b`) is the verified default at `n_ctx=4096`
  (~7.1 GB VRAM, in-character, `enable_thinking=False` clean, 0.2-0.5s). DLL fix already in `kenning/__init__`.
  Worktree `models/`→`E:\UltronModels` junction; corrected env recipe. Zero new regressions.
- **M1 (prompt assembler) — module built, tested, LIVE-validated:** `src/kenning/audio/ultron_prompt.py`
  (`build_relay_prompt`/`build_private_prompt` → lean ~165-word prompt; no/low/high verbosity; flavor on/off;
  exemplar + agent-kit-context + recent-line injection; named-addressee + compound). 12 hermetic tests pass.
  Live 8B run confirms correct in-character relays, agent-context injection, compound→one-line, no think leak.

## M1 LIVE FINDINGS → exact next-step requirements
1. **Fact drift is frequent (MANDATORY guard wiring).** Live: named "heal me" → invented "health at 32";
   compound invented locations ("Jett ... on B", "Breach ... on A"). **When wiring the assembler into the
   relay path, the output MUST pass through `relay_speech._output_keeps_facts` + `_repair_against_input`,
   falling back to `_literal_relay` when a fact dropped/changed.** Non-negotiable correctness backstop.
2. **Verbosity no/low/high not yet differentiating** (8B emits the same short line for all 3 on a short
   callout). M2: harder directives (none→"facts only, telegraphic, e.g. 'Sova, 84, A main', NOT a sentence";
   high→"one vivid line + flavor tail") AND smaller `max_tokens` won't bind alone — the directive must.
   Calibrate against the text-injection battery.
3. **Private (me-only) path returns empty** — `build_private_prompt` needs prompt work (M6). Likely the
   question form + "Now respond:" needs a different framing; debug with the live probe.
4. ✅ Agent-kit-context injection works → M3 just needs the accurate kit table (verify via C_domain/B_valorant_kits).

## UPDATE 2026-06-20 (session 2): M1-wire + M2 LANDED (regression-clean)
- **M1-wire DONE** (commit `4222ff4`): `build_relay_line` generic rephrase → lean `ultron_prompt` behind
  `KENNING_U1_LLM_ROUTE` (default OFF); verbosity+flavor threaded; `<think>` guard; fact-guards untouched;
  hybrid preserved (tactical pre-route + snaps fire first). Live 8B verified. Diff vs baseline: 0 new fails.
- **M2 DONE** (commit `4d21015`): `match_verbosity_command` ("no/low/high flavor", off/on excluded) +
  `_maybe_handle_verbosity_command` wired BEFORE the flavor toggle in both dispatch paths (so "no flavor" =
  verbosity, "flavor off/on" = tail toggle). 23 tests; regression 0 new fails. Cleanup commit `828d075`.
- **Tooling lessons (in STATUS):** the Bash/PowerShell tools SHARE a cwd that drifts → use `git -C "$wt"`,
  pass explicit `path=` to Grep/Glob, run pytest from the worktree root (keep regression-log paths as `tests/...`),
  and diff failures by `::node-id` suffix (not full path).

## M3 DESIGN (from C_domain — do NOT fabricate kits; accuracy is the whole point)
- Build a **hot-swappable, version-stamped** kit file (per C_domain R6), e.g. `data/agent_kits.yaml` or
  `src/kenning/audio/agent_kits.py`, + a loader `agent_kit_facts(agent)->list[str]` + wire `agent_context=` in
  the M1-wire path when the relay addresses/mentions an agent. ALSO inject the EXISTING `AGENT_FLAVOR` situation
  tails as exemplars (the user's "inject our agent-specific libraries as context"; reuses curated accurate data).
- **Populate kits from `02_research/board/B_valorant_kits.md` (read it — large, NOT yet in context) with the
  C_domain CORRECTIONS applied:** Iso Undercut = fragile+SUPPRESS 4s (1 charge, 300cr); Clove Not Dead Yet ult
  = **8 pts** (not 6); Veto Evolution = **7 pts** (not TBC), lasts until death; Neon post-12.09 (no air-speed
  bonus; kill-fuel only during Overdrive). **MUST-inject (8B cutoff ~late-2024 can't know them):** Waylay, Veto,
  Miks, and Iso's suppression. Version-stamp `# KITS v2026-06-20 (Patch 12.10)`. Agents absent from the file →
  no injection (LLM falls back; fact-guards catch drift). Relay path uses ability NAMES so low-risk; PRIVATE_REPLY
  kit Q&A is where accuracy matters most.
- Verified-correct to inject as-is (C_domain): Harbor rework (11.10), Miks kit, economy numbers, Act-3 map pool,
  callout vocab/formula. Corrode released Jun-25-2025 (not Oct); add A-site "Pocket","Crane".

## UPDATE 2026-06-20 (session 3): M3, M4, M6a, M5-classifier LANDED (all regression-clean)
- **M3** `6e1d546`: `agent_kits.py` (29-agent hot-swappable kit dict + C_domain corrections) wired into
  the LLM relay branch (`agent_context=`). **M4** `fc6e5af`: compound→ONE combined LLM call (flag-gated;
  refined hybrid: pure-slot compounds stay deterministic, mixed compounds → one LLM call). **M6a** `eb67ff6`:
  fixed `build_private_prompt` empty-output (private Q&A exemplars, not relay callouts; live-verified).
  **M5 classifier** `caed7a0`: `intent_gate.py` 4-class {RELAY_TO_TEAM,PRIVATE_REPLY,COMMAND_LOCAL,IGNORE}
  cost-asymmetric fail-closed gate (composition of existing matchers + ASR pre-reject + 8B band escalation;
  21 tests). Each: failure set byte-identical to the frozen 22 baseline.
- **State of the route-all-through-LLM pipeline:** COMPLETE + flag-gated (`KENNING_U1_LLM_ROUTE` default OFF):
  lean prompt + no/low/high verbosity (+ voice command) + flavor toggle + agent-kit injection + compound→one
  response + private prompt + the 3-way gate CLASSIFIER. Default OFF → proven deterministic path still ships.

## REMAINING (precise specs — large/risky; do with fresh context, flag-gated, tested):
- **M5b — wire always-listening into the run loop (RISKIEST):** add `addressing.always_listening: bool=False`
  to the Pydantic schema (`config.py` AddressingConfig + config.yaml). The cheapest functional integration
  REUSES the existing follow-up mechanism: at the orchestrator follow-up gate (~orch:6048-6104, where it
  calls the binary addressing classifier) call `intent_gate.classify_scenario(text, wake_present=…,
  seconds_since_response=…, no_speech_prob=…, avg_logprob=…)` instead, and when ON keep the window armed
  perpetually; route RELAY_TO_TEAM→`_maybe_handle_relay_speech(force=True)`, COMMAND_LOCAL→the toggle
  handlers, PRIVATE_REPLY→the normal LLM/desktop dispatch, IGNORE→`continue`. For pre-first-wake always-on,
  the main wake gate must also be bypassable when always_listening (bigger; gate carefully). `resolve_with_llm`
  for the undecided band (pass `self.llm`). DEFAULT OFF; wake stays default. PREREQ: VoiceMeeter mic isolation
  (add a boot warn via `voicemeeter_level`). Calibrate `KENNING_GATE_*` thresholds on the battery + logs.
- **M6b — PRIVATE_REPLY routing:** when the gate (M5b) returns PRIVATE_REPLY, generate via
  `ultron_prompt.build_private_prompt` → `tts.speak_stream` (desktop channel, NOT the team mic / no PTT).
- **Audio MP3 E2E harness (user's explicit ask):** extend `scripts/relay_test/audio_corpus/` — enhanced
  battery (commands embedded in non-triggering text; full non-triggering paragraphs→IGNORE; back-to-back
  command strings→one combined response), wake-spliced + WAKE-FREE clips (for always-listening), run with
  `KENNING_U1_LLM_ROUTE=1`, per-stage trace schema (raw_stt→norm→gate(features+scenario)→route(template_id,
  exemplars,verbosity,channel)→FULL prompt→`<think>`→output→post-validate→final→channel). Report numbers
  RELATIVE (Kokoro is OOD). Hallucination-pressure IGNORE subset. Wake samples: `C:\STC\ultronPrototype\training\crosscheck_ultron\*.wav`.
- **M7 retire/unify:** fix the `_DOMAIN_PROMPT` `.env`-shadow STT bug; decide the legacy-snap default
  (keep deterministic center per C_route_llm; LLM-route opt-in); unify the lean/full dispatch duplication;
  golden-digest re-bless (`scripts/_voice_lines_verify.py baseline`); confirm anticheat (JIT C_anticheat).
- **M8 latency (user DEFERRED — "optimize after"):** prefix caching, KV quant, exemplar pruning, ubatch. Document, don't rush.
- **M9 finalize:** full sweep green; update CLAUDE.md + `docs/codebase_structure.md` + memory; tag `ultron-1.0`.

## CONTINUATION ROADMAP (precise, sequenced, tested increments — resume here)

**M1-wire (next):** wire `ultron_prompt.build_relay_prompt` into `relay_speech.build_relay_line` as a new
LLM-route path BEHIND a flag `KENNING_U1_LLM_ROUTE` (default OFF until proven; retire-not-remove). Where:
the LLM rephrase block at `relay_speech.py:6326-6374` — when the flag is ON, replace the
`_build_rephrase_prompt`+`_RELAY_REPHRASE_SYSTEM` call with `build_relay_prompt(...)` + supply exemplars
(from the matched snap pool / `relay_route_info`) + agent_context (from `_agent_flavor`/kit table) +
verbosity (from a new runtime flag) + flavor_tail (`flavor_tails_enabled()`). KEEP the post-LLM guards
(`_output_keeps_facts`/`_repair_against_input`/`_strip_artifacts`/`_cap_sentences`/`_ensure_addressee`).
Add `_sanitize_user_input` on the `inference.py:~989` `system_prompt=` branch. Tests: a text-injection
slice asserting fact-preservation + in-character + no think-leak (mock or real 8B via `generate_fn`).

**M2 verbosity:** add `match_verbosity_command` ("no/low/high flavor") + a runtime verbosity flag +
config field; strengthen directives (finding #2); calibrate on the battery. Keep `match_flavor_toggle`.

**M3 agent-context:** build an accurate agent-kit table (verify kits via `02_research/board/B_valorant_kits.md`
+ C_domain); inject by addressed agent(s). Reuse `_agent_flavor` situation tails as exemplars.

**M4 compound:** wire the compound path (parse via `_as_compound_callout` split → `build_relay_prompt(compound=True)`
→ one combined line → fact-guard each sub-callout). NO grammar (research D4: free-text + post-validate).

**M5 always-listening 3-way gate:** recover the `9438fc5` log-odds fusion (`git show 9438fc5:src/kenning/addressing/*`),
extend to {RELAY_TO_TEAM,PRIVATE_REPLY,IGNORE,COMMAND_LOCAL}, add features (discord/stream/relay-hint/snap-sim),
ASR-confidence pre-reject, 8B-in-undecided-band fail-CLOSED to IGNORE, post-IGNORE skepticism window.
DEFAULT OFF (opt-in); calibrate τ/weights on the text-injection battery. Prereq: VoiceMeeter mic-isolation check.
JIT-read `02_research/board/C_gate.md`.

**M6 private path:** fix `build_private_prompt` (finding #3); wire PRIVATE_REPLY (no relay, desktop channel).
JIT-read `C_route_llm.md`, `C_persona.md`.

**M7 retire-not-remove + unify:** flag-gate the legacy deterministic-output snaps (default to LLM-route ON),
unify the lean/full dispatch duplication, confirm anticheat posture (JIT-read `C_anticheat.md`), `_DOMAIN_PROMPT`
shadow-bug fix, golden-digest re-bless.

**Phase 5 harnesses (build alongside M1-wire+):** (1) text-injection routing/intent harness (PRIMARY,
deterministic, build on `scripts/relay_test/trace_corpus_full.py`; the enhanced battery = commands-in-noise +
non-triggering paragraphs + back-to-back strings, each a LABELED Case with intent/channel/verbosity; also the
gate calibration set); (2) audio MP3 E2E (the explicit ask; `InjectableCapture` + wake-spliced clips +
per-stage traces incl. full prompt + `<think>` + outputs; numbers RELATIVE). Hallucination-pressure IGNORE
subset. Per-stage trace schema (synthesis D6). Wake samples at `C:\STC\ultronPrototype\training\crosscheck_ultron\*.wav`.

**M8 latency** (after quality): prefix caching, KV quant, exemplar pruning, ubatch. **M9:** full sweep green,
docs/CLAUDE.md/codebase_structure/memory updated, tag `ultron-1.0`.

## HONEST SCOPE NOTE
The full M1-wire→M9 production rearchitecture (incl. editing the 10,637-line orchestrator, the 3-way gate,
two harnesses, retire-not-remove) is a multi-session engineering effort. To honor "no stubs / no
half-implementations / do not damage the pipeline," the pivot is being landed as **tested, flag-gated,
reversible increments** — NOT half-wired into the live pipeline and left broken. M0 + the M1 module are
complete and validated; the live pipeline still runs its proven deterministic path (now on the 8B) until each
u1.0 increment is wired behind its flag and tested green. Resume from this roadmap + `STATUS.md`.
