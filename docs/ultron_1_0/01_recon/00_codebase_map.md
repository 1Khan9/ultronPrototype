# Ultron 1.0 — Master Codebase Map (synthesis of the 22 recon docs)

**Synthesized by Opus 2026-06-20** from the two recon boards (`01_recon/raw/boardA_*.md` ×12,
`boardB_*.md` ×10). This is the high-level, regroundable single-source map; the raw docs hold the
exhaustive per-area detail (path:line tables, gotchas, open questions). **Headline finding: the
Ultron 1.0 pivot is ~70% recomposition of existing, well-built machinery, not a rewrite.**

Branch `claude/infallible-kepler-0a865d` @ `dfadb89`. Core package `src/kenning/`.

---

## 1. The pipeline, end to end (current)

```
mic (sounddevice, 16kHz, 256-blk)  [audio/capture.py AudioCapture; ring_buffer pre-roll]
  → wake word "ultron" (openWakeWord, audio/wake_word.py)        [addressing classifier OFF: follow_up_enabled=false → wake REQUIRED every turn]
  → _capture_utterance() + Silero VAD + Smart-Turn v3            [orchestrator.py:7028; KENNING_WAKE_TRIM_TO_SPEECH cuts wake from audio]
  → STT: faster-whisper large-v3 (config) / Moonshine / Parakeet [stt; domain-biased initial_prompt]
  → _raw_stt snapshot                                            [orchestrator.py:6128]
  → normalize_command()  = L2 then L1                            [audio/command_normalizer.py:975, called orchestrator:6130]
        L2: strip junk → canonicalize relay lead → strip scaffold → resolve disfluency
            → ZERO-MISTAKES GATE (questions/Spotify/reactions/think-respond return verbatim, skip L1)
            → L1 correct_callout_stt (4-stage: phrase→context→slot-confirm→phonetic[Metaphone]+fuzzy[RapidFuzz])
            → recover_relay_lead (bare callouts → relay-intent gate _relay_intent.py → maybe prepend "tell my team")
  → DISPATCH (orchestrator.run(), strict priority list ~20 exact matchers; FIRST match wins):
        toggles (relay/flavor/thinking/device-switch) → intent recognizer → capability routing
        → relay matcher (_maybe_handle_relay_speech, match_relay_command) → ...
        → semantic router (command_router.route, EmbeddingGemma sidecar) ONLY after all exact matchers miss
        → LLM fallback (_respond → _build_response_stream) ONLY after router abstains
  → response:
        relay path → build_relay_line() [audio/relay_speech.py:6012] → play_to_device() → VoiceMeeter B1 (team) + PTT
        desktop path → tts.speak_stream() → speakers/OBS
  → Kokoro TTS (tts/kokoro_engine.py, CUDA) ; barge-in + all-channel stop ; STOP button
  → testing-mode trace → logs/usage_trace.jsonl (_trace_turn_flow orchestrator:3380)
```

Two **audio channels**, selected purely by which handler fires: **team** (`play_to_device` → VoiceMeeter
B1 + optional PTT, with team-only DSP `_shape_for_team`) vs **desktop** (`tts.speak_stream` → speakers/OBS).

There are **two parallel dispatch code paths** in orchestrator.run(): the full path (`if self.coding_voice is not None`)
and **lean-gaming duplicates** (orchestrator.py:6626–6771). Toggle matchers in the lean path use `_raw_stt`
(not normalized text) to avoid matching the normalizer-injected relay lead. *(Maintenance hazard; the u1.0
router should unify these.)*

---

## 2. The route-all-through-LLM surface ALREADY EXISTS (A7, B7)

`LLMEngine.generate_stream(user_message, *, system_prompt=<override>, sampling=<dict>,
enable_thinking=bool, suppress_memory_context=bool, record_history=bool, generate_fn=...)`
(`src/kenning/llm/inference.py`). When `system_prompt=` is passed, `_build_messages` returns just
`[system, user]` — no RAG/history/injection-defense (the fast relay path). The relay ALREADY calls
this (`build_relay_line` step 27 → `_build_rephrase_prompt` + `_RELAY_REPHRASE_SYSTEM` + `_RELAY_SAMPLING`,
or `build_answer_call` for marvel/think-respond).

- **`sampling` whitelist already includes `grammar` + `logit_bias`** (unused) → the **constrained-decoding hook**
  for the combined multi-callout output and clean team-channel formatting.
- **Thinking**: `_strip_thinking_blocks` (stream) / `strip_thinking_text` (block) remove `<think>…</think>`;
  `_apply_no_think_marker` appends `/no_think` for **qwen-family only** when `enable_thinking=False`.
  llama-cpp-python 0.3.22 does NOT separate `reasoning_content` → we parse `<think>` from content ourselves
  (route to trace, strip before TTS). (Confirmed live in `02_research/01_qwen3_8b_serving_probe.md`.)
- **`josiefied-qwen3-8b` is ALREADY an `LLM_PRESETS` entry** (n_ctx 8192, no draft) → default swap = config.
- **Presets/device profiles/hot-swap**: `reload_for_preset`, `reload_for_device` (GPU/CPU `_DEVICE_PROFILES`:
  GPU=full offload+flash_attn+q8_0 KV+512 batch; CPU=0 layers+F16 KV+256 ubatch). `mode_router.py` maps modes→presets.
- **Prompts SSOT** `audio/llm_prompts.py` (`ULTRON_GAMING_PERSONA`, `_RELAY_REPHRASE_SYSTEM`, `ANSWER_*`).
  **Verbosity substrate** `response_style.py` (`apply_brevity_hint` procedural/factual/brief).
  **Prefix-cache substrate** `llm/cache_aware_chunks.py` (`ChunkedPrompt`).
- GOTCHAS: `/no_think` only when "qwen" in model path; `flash_attn=True` needs non-F16 KV; `logits_all=True`
  required when a draft model is active; system_prompt override path SKIPS injection defenses (relay trusts routing).

## 3. Deterministic snap routing = the router + exemplar source (A2, A5, B1, B5)

`build_relay_line` is a **28-step dispatch chain** (relay_speech.py): flavor-off override → verbatim →
TARGET_SNAP_REGISTRY → curated command/social → roast/funfact → directive pools → SNAP_REGISTRY →
clutch/consolation/praise → `_as_snap_callout` (20-handler position/count/damage/ult/possession/movement/
ability/M1-slot chain) → `_as_compound_callout` (splits "Jett hit 84, Breach hit 97") → tactical literal →
**LLM rephrase (step 27)** → fallback. Each step is a **taxonomy node** that in u1.0 becomes an LLM prompt
route + a source of in-context exemplars.

- **M1 slot grammar** `_parse_callout_slots`: token sets `_M1_{AGENTS,COUNT,DMG,LOC,ACTION,OWNER,CONNECTOR}`,
  ≥2 meaningful types rule; multi-digit numbers = dmg. → in u1.0, the LLM does slot-fill; the `_M1_*` sets
  are recognized vocab + few-shot exemplars; the ≥2-type rule becomes a confidence gate.
- **SNAP_REGISTRY (SnapRule) + TARGET_SNAP_REGISTRY (TargetSnapRule)** in `audio/voice_lines.py` = the
  data-driven extension contract (append one entry, no code; `KENNING_SNAP_REGISTRY`). FIRST match wins (precedence).
  → in u1.0 these become routing rules whose `lines`/`tails` are injected as exemplars.
- **Semantic router** (A5): `command_router.route` over family exemplars (`_command_exemplars.py`), HybridBackend
  = 0.6·EmbeddingGemma-300M(sidecar) + 0.4·lexical(RapidFuzz token_set/WRatio + Metaphone). Additive fallback
  under exact matchers; abstains→LLM. **Relay-intent gate** `_relay_intent.py` (pos/neg exemplar clouds,
  margin 0.06, fail-open) inside `recover_relay_lead`. Thresholds UNCALIBRATED.
- **Fact-preservation guards** `_output_keeps_facts`/`_repair_against_input`/`_literal_relay` — CRITICAL
  correctness mechanisms; in u1.0 they become post-LLM validators (NOT removed).

## 4. Flavor library = persona anchors + agent context (A2§14, A3, B4)

- 7 register pools (`_ultron_pools.py`: enemy/ult/damage/utility/careful/command/self). **1,628 per-agent
  curated tails** `AGENT_FLAVOR` (`_agent_flavor.py`, keyed agent→situation→tails, 16-situation taxonomy,
  AGENT_GENDER). `MULTI_FLAVOR` for 2+ agents. `_tail_schema.py` (`situation_for_payload`, tags).
  `_tail_selector.py` MMR re-ranker (off by default, `KENNING_ENABLE_TAIL_SELECTOR`) — **reuse for exemplar selection**.
- Selection: `_flavor_ctx` coarse-route → tag filter → `_pick_lru` (anti-repeat). Owner-aware (enemy contempt /
  your-order command / your-status stoic). `_VERB_TO_ABILITY`, ult-keyword lift.
- Curated pools: `_ultron_commands.py` (COMMAND_RESPONSES), `_ultron_social.py` (SOCIAL_POOLS,
  classify_social_reaction), `_ultron_identity.py` (IDENTITY_POOLS, is_model_leak_probe), `_ultron_setpieces.py`
  (DEFAULT_*_LINES), `_ultron_answer.py` (build_answer_call, marvel/think-respond). `DEFAULT_ROAST_LINES`,
  `DEFAULT_FUN_FACTS` in data/.
- **Aggregation/ingestion (A11)**: `voice_lines.py` re-exports everything (single review surface); golden-digest
  gate `scripts/_voice_lines_verify.py` + `tests/data/voice_lines_golden_digest.json` (358 symbols, PYTHONHASHSEED=0);
  flavor-lint `scripts/flavor_audit/lint_tails.py`; offline builders `scripts/flavor_gen/`. → in u1.0 these stay;
  exemplars are *selected from* these libraries and injected into prompts.

## 5. The always-listening 3-way gate (the hardest new piece) (A6, B6)

Current: addressing classifier is **dead code at runtime** (`addressing.follow_up_enabled=false`); wake required.
The superior **log-odds fusion design lives on branch `9438fc5`** (NOT on HEAD): graded `rules.features()`
(leading_wake, imperative, question, continuation, subj_pronoun/particle/phone openers, interjection,
third-party-narrative, possessive-q, trails-off) → `_ADDR_W` log-odds sum + recency prior `_addr_b0(t)` +
Flan P(YES) only when `|lex|<3.0` → sigmoid → cost-asymmetric `tau` (`KENNING_ADDRESSING_TAU`=0.20) +
`matcher_hit` signal. Disabled because the 30s *window* (not the classifier) caused 114 false-positives/session.

**u1.0 build:** recover `9438fc5` as the base; extend output to **{RELAY_TO_TEAM, PRIVATE_REPLY, IGNORE}**;
add features (`talking_to_discord`, `talking_to_stream`, `team_relay_hint` = relay-intent gate result,
`snap_exemplar_sim` = max cosine/fuzzy to the snap-callout library); consult the **8B only in the undecided band**
(reuse band-consult); calibrate `tau`/weights against the MP3 battery (`logs/addressing.jsonl` is the data sink).
`_is_relay_command` generalizes into `_classify_scenario`. The relay-intent gate moves into this classifier.

## 6. Config / flags / retire-not-remove (A9, B10)

Pydantic v2 `extra="forbid"` → new u1.0 fields MUST be added to the schema first. `LLM_PRESETS` extensible
without schema change. **Retire-not-remove precedent = the 15 `barebones_*` lean flags** (default-on skips that
don't import the subsystem). `runtime_overrides.json` = ephemeral GUI overlay (wiped each boot). Env runtime flags:
`KENNING_FLAVOR_TAILS` (default 0 under `python -m kenning`!), `KENNING_THINKING_MODE`, `KENNING_SNAP_REGISTRY`,
relay DSP family. `_addr_cfg` captured once at run() → addressing change needs RESTART. config.yaml currently
`llm.preset=qwen3.5-4b`, `gpu_layers=0` (gaming CPU 3B).

## 7. Anticheat / lean boot (A10) — HARD CONSTRAINT (unchanged for u1.0)

Import firewall installs **before** the orchestrator constructs, fail-safe (blocks on unknown anticheat state),
boot canary asserts heavy/automation modules absent from `sys.modules`, refuses to start if anticheat active but
firewall not enforcing. Lean gaming default skips+does-not-import the desktop/coding/openclaw/evolution/memory/web
stacks. **u1.0 rule: everything new on the voice/relay path imports only numpy+urllib+stdlib+(RapidFuzz/scipy already
present); all heavy ML stays in the embedder sidecar or offline scripts.** The 8B runs in-process via llama-cpp-python
(already the case for the 3B) — that's compute, not automation, anticheat-irrelevant.

## 8. Tracing substrate (B9) — for the required per-stage traces

`trace.py` + testing-mode `logs/usage_trace.jsonl` (`_trace_turn_flow` orchestrator:3380) capture raw STT →
normalized → route+reason → final → channel today. `trace_corpus_full.py` emits per-case JSONL with
stt1/norm2/router/match/route/snap/tail/final/llm_path. **Gaps to fill for u1.0:** full LLM prompt, `<think>`
trace, per-callout breakdown in combined strings, intent-classification scores, prompt_template_id, llm_call_count.

## 9. Test/harness infra (A12) — for Phase 5

`InjectableCapture` (`scripts/relay_test/audio_corpus/inject.py`) = the drop-in mic (256-sample frames @16ms;
full wake/VAD/STT/route/TTS unmodified) = the E2E harness kernel. `gen_commands.py` splices a **real** trained
wake sample (`training/crosscheck_ultron/*.wav`, fires ~0.94) + Kokoro-synth body (stock Kokoro "Ultron"≈0.27
won't fire). `run_corpus.py` boots orchestrator + swaps mic + testing-mode + drives clips + retranscribes.
`render_review.py` flags TX/RE/WK/NR/LLM. `battery_cmds.txt` ≈240 cmds. `corpus.py`/`corpus_packs.py`/`vocab_packs/`
→ 25k text corpus. pytest: 10k+ tests, golden-digest gate, `pyproject.toml [tool.pytest]` (30s timeout).
KNOWN: short-callout TTS sim fidelity is low (am_michael@1.18x garbles jargon) → battery validates ROUTING/intent,
not short-callout STT fidelity (real-voice needed for that). 2 pre-existing compound-directive fails.

---

## 10. Pivot map — where each u1.0 capability attaches (with line refs)

| u1.0 capability | Attach point | Reuse |
|---|---|---|
| Route ALL through 8B | `build_relay_line` step 27 (relay_speech:6012) becomes primary, not last; `_respond`/`_build_response_stream` for desktop | `generate_stream` override surface; `llm_prompts.py` |
| Snap→prompt-router + exemplars | the 28-step chain + `relay_route_info` → emit (template_id, exemplars[]) instead of a final line | SNAP_REGISTRY, `_command_exemplars`, AGENT_FLAVOR, `_tail_selector` MMR |
| Always-listening 3-way gate | recover `9438fc5` fusion; `_classify_scenario` replacing `_is_relay_command`(orch:3126) + addressing gate(orch:6048); add features | rules.features/_ADDR_W/tau, relay-intent gate, EmbeddingGemma sidecar, RapidFuzz |
| no/low/high verbosity | system-prompt directive chosen by route; thread through `_gaming_conversational_prompt`(orch:9006) + relay prompt builder | response_style hints |
| flavor tail on/off | system-prompt instruction ("author one tail" / "no tail"); keep `match_flavor_toggle` | `flavor_tails_enabled()`, `_join_tail` |
| combined back-to-back callouts → 1 response | parse compound, build one prompt with per-callout slots, **GBNF grammar** for structured output | `_as_compound_callout` split logic; `sampling.grammar` |
| agent context injection | inject AGENT_FLAVOR[agent] kit/situation + agent gazetteer into prompt by addressed agents | AGENT_FLAVOR, `_tail_schema` |
| thinking trace logging | route stripped `<think>` text to trace instead of discarding | `_strip_thinking_blocks` |
| config | new `ultron_v1` config section (Pydantic) + flags; default preset → josiefied-qwen3-8b, gpu_layers -1 | LLM_PRESETS, barebones_* pattern |
| E2E harness | extend `Case` (intent/channel/verbosity); new negative packs (discord/stream/me-only) + paragraphs + compound strings; trace gains llm fields | InjectableCapture, run_corpus, trace_corpus_full |

## 11. Retire-not-remove registry (switch off, keep, revisitable)
- Deterministic-output snap paths (`_as_snap_callout` direct return, curated/social direct return) → gated behind a
  flag; default routes through the LLM-with-exemplars path. Keep as fast-path fallback + exemplar source.
- Flan-T5 zero-shot addressing → retire as primary (replaced by fusion + 8B band-consult); keep as fail-open.
- `_FOLLOWUP_WAKE_RE` / `_DIRECT_ADDRESS` bypasses → superseded by `_LEADING_WAKE` feature; keep until fusion proven.
- The lean dispatch duplication → unify under the u1.0 router (keep both until parity verified).
- All gated by new default-aware flags (mirror `barebones_*`), nothing deleted.

## 12. Open questions carried into the plan
1. Always-listening latency budget: 8B on every ambient utterance is too costly → cheap layered gate (rules+emb+fuzzy)
   handles clear cases; 8B only in the undecided band. Confirm P99 of the cheap gate under continuous transcription.
2. Combined-callout gap protocol in audio (trailing/leading silence) so VAD segments or merges as intended.
3. `training/crosscheck_ultron/*.wav` location (not in worktree) — needed for the wake-spliced battery; find or relocate.
4. Golden-digest re-bless process once voice-line/registry changes land.
5. Whether to keep the 0.1.1 model-lab A/B (josiefied-8b vs qwen3.5-9b vs qwen2.5-7b-abliterated) — yes, cheap to keep.

> Detail for any line above: see the matching `01_recon/raw/board{A,B}_*.md`. This map + `00_process_log/STATUS.md`
> are the primary regrounding sources for the rest of the build.
