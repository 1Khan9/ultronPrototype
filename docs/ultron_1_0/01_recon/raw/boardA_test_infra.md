# A12: Existing test infra & the MP3 audio-corpus battery

## Overview

The test infrastructure has two distinct planes:

1. **Text-level (fast / hermetic)**: pytest with ~150+ test files organized by
   module. No live model, no mic. Tests run against the normalizer, matcher,
   LLM prompt construction, and routing logic via monkeypatched stubs. Includes
   several "frozen regression tables" that pin specific corpus-audit findings.

2. **Audio / full-pipeline (slow / integration)**: the `scripts/relay_test/`
   harness family plus the `audio_corpus/` sub-suite. These load real models (3B
   LLM, Kokoro TTS, Moonshine STT), synthesize audio, inject into the live
   orchestrator, and capture per-stage traces.

The MP3 battery (≈240 commands in `battery_cmds.txt`) is the source for the
audio-injection corpus. The corpus is built by splicing a real trained-wake-word
sample with Kokoro-synthesized command bodies, then feeding the resulting WAV
through the real `Orchestrator` via the `InjectableCapture` drop-in mic.

---

## Files & key symbols (path:line tables)

### Corpus / vocabulary data

| File | Key symbols | Role |
|---|---|---|
| `scripts/relay_test/battery_cmds.txt` | ≈240 `Ultron, <cmd>` lines | Source command list for the audio MP3 battery |
| `scripts/relay_test/corpus.py` | `Case`, `build_corpus()`, `LOCATIONS`, `AGENTS`, `MAP_CALLOUTS`, `_vary_phrasing()` | ~500+ base test cases for the text-level harness |
| `scripts/relay_test/corpus_packs.py` | `build_corpus()`, `build_corpus_10k()`, `_pack_cases()`, `_compound_cases()`, `_cap_stratified()` | Expands base corpus to 25k via vocab_packs; stratified cap; back-compat alias |
| `scripts/relay_test/vocab_packs/*.py` | `ITEMS` list per pack | Category-specific vocab: `callouts_maps`, `agents_abilities`, `directives_tactics_eco`, `stress_false_relay_hard`, `stress_oov_safety`, `questions_to_ultron`, etc. |

### Audio corpus pipeline

| File | Key symbols / functions | Role |
|---|---|---|
| `scripts/relay_test/audio_corpus/gen_commands.py` | `main()`, `LEAD_SILENCE_S=0.5`, `TAIL_SILENCE_S=1.3`, `GAP_COMMA_S=0.25`, `GAP_RUNON_S=0.06`, `WAKE_RE`, `_to_16k_f32()` | Step 1: generate composite WAV+MP3 clips per battery command |
| `scripts/relay_test/audio_corpus/inject.py` | `InjectableCapture(AudioCapture)`, `feed_pcm()`, `get_chunk()`, `drain()`, `_realtime=True` | Drop-in mic replacement; serves 256-sample frames at mic cadence |
| `scripts/relay_test/audio_corpus/run_corpus.py` | `main()`, Kokoro `_hooked` synth hook, `_trace_count()`, `_last_trace_row()` | Step 2: boot full orchestrator, swap mic, drive each clip, collect trace |
| `scripts/relay_test/audio_corpus/render_review.py` | `flags()`, auto-flag codes TX/RE/WK/NR/LLM | Step 3: render session JSONL to per-case `.review.txt` with anomaly summary |
| `scripts/relay_test/audio_corpus/README.md` | — | Protocol documentation, usage, caveats |

### Harness / replay scripts

| File | Key symbols | Role |
|---|---|---|
| `scripts/relay_test/harness.py` | `run()`, `score_matcher()`, `score_rephrase()`, `score_audio()`, `score_asr()`, `_load_llm()`, `_spoken_then_stt()`, `_stt_pcm()`, stages: `matcher/rephrase/audio/asr/full` | Multi-stage text→audio harness; loads real models per stage |
| `scripts/relay_test/battery_replay.py` | `main()`, `_conversational()`, `GAMING_PRESET` | Feeds battery commands as STT text through routing; prints route/channel/spoken per command |
| `scripts/relay_test/transcript_replay.py` | `classify()`, `_relay_match()`, `_strip_wake()`, `MIC`, `DESKTOP` | Replays logged real-mic STT transcripts; checks no relay goes to DESKTOP |
| `scripts/relay_test/trace_corpus_full.py` | `main()`, `_route_info()`, `_router_decision()`, `_snap_only()` | Full-stage corpus tracer: emits per-case JSONL with stt1/norm2/router/match/route/snap/tail/final/llm_path |
| `scripts/relay_test/trace_corpus.py` | `main()` | Lighter variant of trace (pre-full) |

### Scripts (autonomous E2E, misc)

| File | Key symbols | Role |
|---|---|---|
| `scripts/autonomous_e2e_harness.py` | `Scenario`, phases 1–11: `phase_stt()`, `phase_llm()`, `phase_tts()`, `phase_web_search()`, `phase_memory()`, `phase_routing()`, `phase_gate()`, `phase_commands()`, `phase_short_circuits()`, `phase_full_loop()`, `phase_coding()`, `write_report()`, `_spoken_transcript()`, `_build_spoken_pipeline()` | Full 11-phase spoken-acoustic E2E harness; not relay-specific |

### pytest layout

| Path | Scope |
|---|---|
| `tests/conftest.py` | Session-level: concurrent-run guard (psutil), `_disable_observation_io_for_tests`, `_disable_tts_output_watcher_for_tests`, `_ignore_anticheat_config_pin_for_tests`, heartbeat/progress hooks, session-end subprocess cleanup |
| `tests/audio/test_relay_speech.py` | 1216 lines; matcher/build/play/DSP/snap/toggle/orchestrator wiring |
| `tests/audio/test_relay_speech_expansion.py` | 1563 lines; named addressee, context/respond, LLM prompts, economy, damage, snap callouts, verbatim, fun-fact, greet/farewell, snap flavor |
| `tests/audio/test_corpus_audit_fixes.py` | 1136 lines; frozen regression classes for corpus audit phases: P0b economy, C6 disfluency, C2 normalizer protect, C3 location tails, C5 compound wrapper, C10 answer/leak gate, C4 reported directive, C1 leak deflect, M1 slot parser, T617 testing fixes, ThankYouSnap, EnemyOutCallout, FlavorOff, NiceTryParity, SayHelloDefault, FlavorToggleMishears, BareMoraleRouting, MangledTeamLead, SttMishearTolerance, LiveBatch06{19B/C/D}, RunOnLead, FlavorOffYesNo, JoinedLocationMulti |
| `tests/audio/test_corpus_25k_fixes.py` | F1–F5 deterministic root fixes from the 2026-06-18 audit; 109 tests |
| `tests/audio/test_thinking_mode.py` | Thinking toggle matcher/state + deterministic-off snapping in both flavor states |
| `tests/audio/test_command_normalizer.py` | normalizer unit tests |
| `tests/audio/test_stt_correct.py` | `correct_callout_stt` unit tests |
| `tests/audio/test_flavor_lint.py` | `_tail_schema.lint_agent_flavor` gate (gender/situation/tag/dupe) |
| `tests/audio/test_output_quality.py` | `analyze_clip` blip/burst/dropout detector |
| `tests/audio/test_stream_routing.py` | command router unit tests |
| `tests/audio/test_social_marvel_answer.py` | social reaction + Marvel answer pipeline |
| `tests/audio/test_stop_button.py` | stop-button GUI wiring |
| `tests/audio/test_snap_early_endpoint.py` | snap early-endpoint feature |
| `tests/audio/test_waveform.py` | waveform analysis |
| `tests/audio/test_thinking_mode.py` | thinking mode |
| `tests/audio/test_broadcast.py` | broadcast channel |
| `tests/audio/test_monitor.py` | audio monitor |
| `tests/test_voice_lines_golden.py` | Golden digest gate: subproc `PYTHONHASHSEED=0 scripts/_voice_lines_verify.py check` against `tests/data/voice_lines_golden_digest.json` (358 symbols) |
| `tests/test_addressing.py`, `test_addressing_third_party_possessive.py` | Addressing classifier unit tests |
| `tests/routing/` | Routing classifier (not relay-specific) |
| `tests/subprocess/test_orphan_guardrails.py` | Embedder orphan guardrails |
| `tests/data/voice_lines_golden_digest.json` | Committed golden digest for voice-lines aggregate gate |

### Key source files exercised by tests

| File | Role |
|---|---|
| `src/kenning/audio/relay_speech.py` | The relay engine; `match_relay_command`, `build_relay_line`, `_shape_for_team`, snap registry, flavor pool, `set_flavor_tails_enabled`, `set_thinking_mode_enabled` |
| `src/kenning/audio/command_normalizer.py` | `normalize_command`, `recover_relay_lead`, `_strip_scaffold`, `_NARRATION_MUSING_RE` |
| `src/kenning/audio/_stt_correct.py` | `correct_callout_stt` |
| `src/kenning/audio/voice_lines.py` | `SNAP_REGISTRY`, `SnapRule`, `DEFAULT_*_LINES` aggregated pool |
| `src/kenning/audio/output_quality.py` | `analyze_clip`, `set_output_watcher_enabled` |
| `src/kenning/audio/capture.py` | `AudioCapture` base class extended by `InjectableCapture` |
| `src/kenning/pipeline/orchestrator.py` | `Orchestrator`, `orch.audio` injection point, `orch.run()`, `ULTRON_GAMING_PERSONA` |
| `src/kenning/safety/testing_mode.py` | `set_testing_mode_active` |
| `src/kenning/tts/kokoro_engine.py` | `KokoroSpeech`, `_synthesize` hook point |
| `src/kenning/transcription/moonshine_engine.py` | `MoonshineEngine.transcribe` |

---

## Control/data flow

### Text-level harness (fast, no models)

```
battery_cmds.txt (240 cmds)
  -> corpus.py:build_corpus()         [~500 base Case objects]
  -> corpus_packs.py:build_corpus()   [+vocab_packs expansions -> 25k cap]
  -> harness.py:run(stage="matcher")
        normalize_command(text)
        -> match_relay_command(normalized)
        -> score_matcher(case, cmd)   [expect_match / addressee / flags]
        -> write JSONL to logs/relay_test/<stage>_<run>.jsonl

  stage="rephrase": + build_relay_line(cmd, llm=real_3B)
  stage="audio":    + KokoroSpeech._synthesize(line) + analyze_clip()
  stage="asr":      + MoonshineEngine.transcribe(pcm) + score_asr()
  stage="full":     + also synthesize input cmd via neutral KokoroSpeech
                      -> MoonshineEngine.transcribe -> feed as heard_in
```

### Audio MP3 battery pipeline

```
battery_cmds.txt
  -> gen_commands.py
       for each cmd:
         WAKE_RE.sub("", cmd) -> body
         KokoroSpeech(voice="am_michael", speed=1.18)._synthesize(body) -> body_f32
         wakes = training/crosscheck_ultron/*.wav (up to 40, rotated; fire ~0.94)
         composite = [0.5s silence] + wake[i%N] + [gap 0.25s comma / 0.06s run-on]
                     + body_f32 + [1.3s silence]
         -> wav_dir/<slug>.wav (16kHz PCM16)
         -> mp3_dir/<slug>.mp3 (96k MP3)
  -> out/manifest.json

  -> run_corpus.py
       KokoroSpeech._synthesize hooked (capture response PCM)
       Orchestrator() built (full boot with firewall + real wake model)
       orch.audio = InjectableCapture(realtime=True)
       set_testing_mode_active(True)
       orch.run() in daemon thread
       boot detection: poll kenning.log for "waiting_for_wake_word"

       for each manifest entry:
         inj.feed_pcm(wav_pcm)          # enqueue to InjectableCapture
         [InjectableCapture.get_chunk() returns 256-sample frames at ~16ms cadence]
         [wake fires ~mid-stream; orchestrator: pre-roll -> VAD -> STT -> norm -> route]
         wait: usage_trace.jsonl new row AND Kokoro quiescent (>1.8s since last synth)
         last_trace_row: raw / normalized / route / reason / subtype / payload / final
         response_audio: concatenate cap_state["buf"], re-transcribe with orch.stt.transcribe()
         re-derive: correct_callout_stt(raw), normalize_command(raw), match_relay_command()
         write rec to session_<stamp>/corpus_<stamp>.log.jsonl

  -> render_review.py
       for each rec:
         TX: transcription vs expected_body (token overlap < 80%)
         WK: "ultron/tron/altron/ultra" in transcript
         RE: response retranscription vs final_spoken (content overlap < 70%)
         NR: no trace row captured
         LLM: route ends with "llm" or is "conversational_llm"
       write .review.txt with per-case block + summary header
```

### trace_corpus_full.py (full-stage JSONL audit)

```
build_corpus(seed, target=25k)
  for each Case:
    correct_callout_stt(text)   -> stt1
    normalize_command(text)     -> norm2
    [optional] _ROUTER.route(norm2) -> router {family/abstained/confidence/margin}
    match_relay_command(norm2)  -> cmd or None
    _route_info(cmd)            -> {route, reason, subtype}
    if cmd:
      payload / addressee / compose / verbatim / directive / context
      _snap_only(cmd)           -> snap
      build_answer_call(cmd)    -> llm_system / llm_user
      build_relay_line(cmd, llm=None, rephrase=False) -> final
      tail = final[len(snap):].strip() if snap in final
    write JSONL row
```

### conftest.py session lifecycle

```
pytest_configure:   concurrent-run guard (psutil)
pytest_sessionstart: write heartbeat / progress JSONL / current-test files
pytest_runtest_logstart: update heartbeat + current-test before each test
pytest_runtest_logreport: append passed/failed/skipped + duration to JSONL
pytest_sessionfinish: kill python descendants (except live orchestrator on port 19761)
                       write session_end to progress JSONL

autouse session fixtures:
  _disable_observation_io_for_tests       (suppress data/observations.jsonl writes)
  _disable_tts_output_watcher_for_tests   (suppress audio_quality.jsonl + daemon thread)
  _ignore_anticheat_config_pin_for_tests  (hermetic regardless of live config.yaml)
```

---

## Key findings

1. **InjectableCapture IS the full-pipeline mic simulator.** It subclasses `AudioCapture` (same `blocksize=256, sample_rate=16000` contract), overrides `start()`/`stop()` to no-ops, and `get_chunk()` to serve pre-queued PCM frames at real mic cadence (`time.sleep(frame_s)` = ~16ms per block). The live wake word detector, VAD, pre-roll ring, STT, normalizer, routing, and TTS stack all run unmodified.

2. **The wakeword problem solved with spliced real samples.** The custom openWakeWord "ultron" model scores stock Kokoro synthesis at ~0.27 (threshold 0.65), so it would never fire. The battery clips splice in real trained samples from `training/crosscheck_ultron/*.wav` (up to 40, rotated with `i % len(wakes)`; these fire at ~0.94). This is a critical substrate detail for u1.0: any new audio battery must preserve this splice or provide an equivalent acoustic trigger.

3. **Turn completion detection in run_corpus.py is fragile.** The runner waits for BOTH a new `usage_trace.jsonl` row AND Kokoro quiescence (>1.8s since last synth chunk). If the system produces no trace row (e.g. routing failure, model crash, stall) it falls through after `turn_timeout` (default 90s). The `NR` flag in the review marks these cases.

4. **Response retranscription uses `orch.stt.transcribe()` (Moonshine) on the CAPTURED Kokoro output PCM.** This exercises the full audio quality of the relay: not just "did it route correctly" but "is the spoken output intelligible."

5. **The harness uses a temp Qdrant path per run** (`kenning_relay_test_qdrant_<PID>`) registered via `atexit` for cleanup. This prevents contention with any live orchestrator's `data/qdrant` lock.

6. **25k corpus sampling is seeded and stratified.** `corpus_packs.build_corpus(seed, target=25000)` de-dups, shuffles by category proportionally via `_cap_stratified`, and the seed rotates the prefix assignments so each run covers a fresh 25k slice of the full ~29k+ unique payloads. `RELAY_CORPUS_SEED` env var controls this.

7. **Two pre-existing compound-directive failures are known and confirmed unrelated.** The memory module notes them as "stash-verified" pre-existing fails (compound reported-directive payload extraction); they appear in most traces.

8. **pytest session isolation is strict:** three session-scope autouse fixtures mute observation IO, TTS watcher daemon, and the anticheat config pin. The concurrent-run guard uses psutil to detect any other pytest invocation against this codebase and raises `UsageError` before any fixture runs.

9. **The golden-digest gate (`test_voice_lines_golden.py`) validates the entire voice-lines + routing + prompt aggregate.** It runs `scripts/_voice_lines_verify.py check` in a subprocess with `PYTHONHASHSEED=0` (required for stable regex alternation order from set iteration) against `tests/data/voice_lines_golden_digest.json` (358 symbols). Any accidental edit to a voice line, regex, threshold, or registry rule fails CI.

10. **Autonomous E2E harness (`scripts/autonomous_e2e_harness.py`) is 11-phase and NOT relay-specific.** It covers STT accuracy, LLM, TTS, web search, memory, routing classifier, gate, spoken-command matrix (all RoutingIntentKind), short-circuit matchers, full loops, and voice coding. Its `Scenario` record class and `_spoken_transcript()` helper (neutral Kokoro → Moonshine → transcript) are reusable infrastructure for a u1.0 harness.

11. **The text-level harness stages (matcher → rephrase → audio → asr → full) are progressive.** Each stage is a superset of the previous: `matcher` is fast (no models), `full` is the complete acoustic round-trip (synthesize input → STT → route → build → TTS → retranscribe). The `GAMING_PRESET` in `harness.py:324` is hardcoded to `"llama-3.2-3b-abliterated"`.

12. **The `score_asr` function in harness.py uses a deliberately lenient calibration.** For short callouts (< 5 content words) it only checks that any alphabetic word is present (speech vs. silence). Only for longer lines (≥ 5 content words) does it check gross reconstruction coverage (< 35% fails). Exact ASR fidelity is NOT graded — this is intentional because Kenning's reverb voice character causes consistent STT mis-hears of intelligible speech.

13. **vocab_packs auto-discovery:** `corpus_packs._all_pack_names()` does `os.listdir(_PACK_DIR)` to enumerate `*.py` files; packs are classified by membership in `_QUESTION_PACKS`, `_NEGATIVE_PACKS`, `_VERBATIM_PACKS`, or `_EXCLUDE_PACKS`; the rest are RELAY packs.

14. **The 29-agent roster in corpus.py includes all 2026 Valorant agents + STT homophones** (kill joy, kay o, cipher, gecko, mix, way lay). These exercise the matcher's `_NAME_CANON` homophone canon.

---

## Flags & config

| Flag / env var | Default | Effect | Where set |
|---|---|---|---|
| `RELAY_CORPUS_SEED` | `0` | Shuffle seed for corpus pack prefix assignment + stratified cap | `harness.py:181`, `trace_corpus.py:117`, `trace_corpus_full.py:149` |
| `RELAY_CORPUS_TARGET` | `25000` | Corpus size cap for trace runs | `trace_corpus.py:118`, `trace_corpus_full.py:150` |
| `RELAY_TEST_GPU_LAYERS` | unset (defaults to `-1` = full GPU) | GPU layers for the 3B during harness rephrase stages | `harness.py:383` |
| `TRACE_WITH_ROUTER` | `1` (on) | Whether to load the semantic router sidecar in trace_corpus_full | `trace_corpus_full.py:60` |
| `KENNING_ALLOW_MULTIPLE_INSTANCES` | not set | Set to `"1"` in `run_corpus.py:52` to allow concurrent orchestrator | `run_corpus.py:52` |
| `KENNING_SNAP_REGISTRY` | `1` (on) | Gates the data-driven SNAP_REGISTRY path in `_apply_snap_registry` | `relay_speech.py:2801, 2849, 2881` |
| `KENNING_FLAVOR_TAILS` | `1` (on) | Default flavor-tails state at startup; runtime-overridable via `set_flavor_tails_enabled()` | `relay_speech.py:1136` |
| `KENNING_THINKING_MODE` | `0` (off) | Default thinking-mode state; `match_thinking_toggle()` flips it at runtime | `relay_speech.py:1197` |
| `KENNING_RELAY_TEAM_DSP` | `1` (on) | Master gate for `_shape_for_team` DSP pipeline | `relay_speech.py:6608` |
| `KENNING_RELAY_COMMS_FILTER` | `1` (on) | High-pass filter stage in team DSP | `relay_speech.py:6613` |
| `KENNING_RELAY_NORMALIZE` | `1` (on) | RMS normalize stage | `relay_speech.py:6615` |
| `KENNING_RELAY_COMFORT_NOISE` | `1` (on) | Comfort noise floor stage | `relay_speech.py:6617` |
| `KENNING_RELAY_SOFTCLIP` | `1` (on) | Soft clip ceiling stage | `relay_speech.py:6619` |
| `KENNING_RELAY_LOWPASS_HZ` | `0.0` (off) | Low-pass cutoff for team path | `relay_speech.py:6522` |
| `KENNING_RELAY_HIGHPASS_HZ` | `100.0` | High-pass cutoff | `relay_speech.py:6521` |
| `KENNING_RELAY_TARGET_DBFS` | `-20.0` | RMS normalize target | `relay_speech.py:6544` |
| `KENNING_RELAY_NOISE_DBFS` | `-58.0` | Comfort noise floor level | `relay_speech.py:6571` |
| `KENNING_RELAY_CEILING_DBFS` | `-1.0` | Soft-clip ceiling | `relay_speech.py:6592` |
| `KENNING_WAKE_TRIM_TO_SPEECH` | `1` (on) | Audio-domain wake-word removal via VAD segmentation | `orchestrator.py:280`, `orchestrator.py:7116`, `orchestrator.py:7558` |
| `KENNING_WAKE_TRIM_GUARD_MS` | `200` | Guard margin for wake trim | `orchestrator.py:288` |
| `KENNING_SNAP_EARLY_ENDPOINT` | `0` (off) | Early capture closure on snap route detection | `relay_speech.py:5987` |
| `PYTHONHASHSEED` | (caller) | Must be `0` for stable regex alternation in golden digest | `test_voice_lines_golden.py`, `scripts/_voice_lines_verify.py` |
| `KENNING_VOICE_LINES_DIGEST` | (arg or env) | Path to the golden digest JSON for `_voice_lines_verify.py` | `scripts/_voice_lines_verify.py` |

---

## Extension points

1. **Adding new battery commands**: append a line to `scripts/relay_test/battery_cmds.txt`, then re-run `gen_commands.py` to regenerate the composite audio clips. The manifest is rebuilt from scratch each run.

2. **Adding new vocab pack**: create `scripts/relay_test/vocab_packs/<name>.py` with an `ITEMS: list[str]` variable. `corpus_packs._all_pack_names()` auto-discovers it. Classify it into `_QUESTION_PACKS`, `_NEGATIVE_PACKS`, `_VERBATIM_PACKS`, or leave as a RELAY pack.

3. **Adding a new SnapRule (data-driven snap)**: add a `SnapRule(...)` entry to `SNAP_REGISTRY` in `src/kenning/audio/voice_lines.py`. No code change needed; gated by `KENNING_SNAP_REGISTRY`.

4. **Adding a new voice-lines pool**: add to the category→trigger→matcher→responses→tails map in `voice_lines.py`. Then re-bless the golden digest with `PYTHONHASHSEED=0 python scripts/_voice_lines_verify.py baseline`.

5. **Adding a new test class**: the `corpus.py` `Case` dataclass is the canonical test input. Add a new section in `corpus.py:build_corpus()` or a new vocab pack. The harness picks it up automatically.

6. **Extending harness stages**: `harness.py:run()` checks `stage in {"rephrase","audio","asr","full"}` for model loading. A new stage can be added by extending the `stage` CLI choice and the `need_*` flags.

7. **u1.0 E2E harness substrate**: `inject.py:InjectableCapture` + the `run_corpus.py` boot/inject/wait pattern is the reusable kernel. For u1.0 with always-listening and LLM-centric routing, the injection pattern is identical; what changes is: (a) the commands injected include non-triggering paragraphs and back-to-back compound strings, (b) the trace needs new fields (`llm_call_count`, `prompt_template_id`, `intent_kind`), (c) the turn-completion signal may need to be more robust than the Kokoro quiescence heuristic.

8. **Discriminator corpus for u1.0**: the `_QUESTION_PACKS`, `_NEGATIVE_PACKS`, and `_VERBATIM_PACKS` classification in `corpus_packs.py` is the existing discriminator corpus structure. For u1.0, new negative packs can cover (A) Discord/out-loud speech, (B) teammate speech, (C) ME-ONLY query intent — these become the three-way discriminator test corpus.

---

## Retire-not-remove candidates (u1.0)

The following are tagged as "retire-not-remove" because their structure (regex pools, slot grammar, snap logic) will be repurposed as intent detectors, prompt template pickers, or exemplar injectors rather than being discarded:

1. **`match_relay_command()`** — retire as the ONLY routing gate; repurpose as a **strong-signal intent detector** feeding the LLM router. Its 30+ pattern branches become the "high-confidence relay" fast path and positive exemplar injection.

2. **`build_relay_line()`** — retire the direct-snap path as the output mechanism; repurpose as a **prompt template + exemplar injector** for the 8B LLM. The `_snap_only()` calls become the curated in-context examples. The `_load_llm()` helper in harness.py already loads the real gaming 3B; for u1.0 swap to 8B.

3. **`SNAP_REGISTRY` / `SnapRule`** — retain as a **template library**; each SnapRule's trigger/matcher becomes a routing rule, its responses become exemplars, its tails become flavoring instructions.

4. **`corpus.py:build_corpus()` + `corpus_packs.py`** — retain and AUGMENT. The `Case` dataclass gains new fields: `intent` (one of relay/me-only/non-addressed), `channel` (team-mic/desktop/none), `verbosity` (no/low/high). The existing 25k corpus becomes the u1.0 routing discriminator test set.

5. **`harness.py` stages** — retain all 5 stages; add stage `"llm_route"` to test the LLM routing decision before any relay action. The `score_matcher()` function becomes `score_intent()` with the new three-way classification.

6. **`render_review.py`** — retain; add new auto-flag `IN` (intent mismatch: system thought "relay" but correct label is "me-only" or "non-addressed").

7. **`_QUESTION_PACKS` / `_NEGATIVE_PACKS`** — retain and SPLIT into three new pack families: `_DISCORD_PACKS` (talking to others), `_STREAM_PACKS` (talking out loud), `_ME_ONLY_PACKS` (Ultron private query).

8. **The `battery_cmds.txt` ~240 command list** — retain as the positive relay corpus. Augment with ~100 non-relay paragraphs (stream narration, Discord banter) and ~50 back-to-back compound command strings for the u1.0 "combined LLM call" test.

---

## Gotchas

1. **Stock Kokoro "Ultron" never fires the wake detector.** The custom openWakeWord model scores stock Kokoro at ~0.27 (threshold 0.65). The battery clips MUST splice in real samples from `training/crosscheck_ultron/*.wav`. If this directory is missing or empty, `gen_commands.py:99` prints an error and returns exit code 2.

2. **TTS simulation fidelity is low for short Valorant jargon.** Per `README.md`: `am_michael @1.18x` garbles short callouts ("jett A main" → "GENTLEMEN", "sova" → "Silva"). TX flags on short callouts are mostly harness artifacts, not pipeline bugs. A real human voice is needed for faithful short-callout STT validation.

3. **`KENNING_ALLOW_MULTIPLE_INSTANCES=1` required in run_corpus.py.** Without it the orchestrator boot fails if any other instance is running (single-instance lock). Set as `os.environ.setdefault` at `run_corpus.py:52`.

4. **`usage_trace.jsonl` polling is racey.** `run_corpus.py` detects a new trace row by counting lines. If the orchestrator writes the row during the 0.25s poll sleep, or if the LLM call takes longer than `turn_timeout` (default 90s), the row is missed and the NR flag fires. Long LLM turns (the real 3B on CPU) can exceed this.

5. **Qdrant isolation via temp path.** The harness creates a PID-unique Qdrant path. If the process crashes without running the atexit handler, temp dirs accumulate in `%TEMP%`. The memory notes mention a "5 GB lingering test holder."

6. **The orchestrator takes up to 180s to boot.** `run_corpus.py:149` polls `kenning.log` for the `waiting_for_wake_word` marker with a 180s deadline then adds 3s sleep. A cold boot (cold model cache) can exceed this.

7. **`conftest.py` concurrent-run guard uses psutil.** If psutil is not installed or returns `AccessDenied`, the guard silently falls through (fail-open). The guard matches "python" in process name + "pytest" + "tests" in cmdline — a CI runner with different naming may not be protected.

8. **`score_rephrase` in harness.py checks for control tokens but not persona leaks.** It looks for `/no_think`, `<|...|>`, `<think>` control tokens and `*...*` stage directions, and forbids quotation marks. It does NOT check for "Kenning" persona leaks in the relay output (that is a separate audio review concern).

9. **The harness's `_load_llm()` defaults to full GPU for testing.** The note at `harness.py:381`: "In-game the gaming preset is CPU-only (gpu_layers=0). For TESTING we default to full GPU (-1) for speed." Set `RELAY_TEST_GPU_LAYERS=0` to match the production CPU path.

10. **`trace_corpus_full.py` only calls `build_relay_line(cmd, llm=None, rephrase=False)`.** This exercises only the deterministic snap path. Cases on the LLM path (`relay_llm`, `compose_llm`, `answer:*`) have `llm_path=True` in the trace but the actual LLM output is NOT generated in the trace run.

11. **`harness.py` uses `build_corpus_10k` which is an alias to `build_corpus(target=25000)`.** The name `10k` is a historic misnomer; the actual corpus target is 25k.

---

## Open questions

1. **Where does the training/crosscheck_ultron/ wake-word sample directory live?** The gen_commands.py mentions `_ROOT / "training/crosscheck_ultron/*.wav"`. Is this in the repo (not seen in this worktree)? Is it in the shared model store? What happens if it moves to E:\UltronModels\?

2. **Is there a fixed count of battery commands?** The file has 240 lines including comments and blanks; the actual command count after filtering is not asserted anywhere. Is there a CI gate on the battery size?

3. **Is `run_corpus.py` ever run in CI or is it always manual?** The README says to run it manually. For u1.0, should this become an automated gate (e.g. nightly) with a pass threshold?

4. **The "two pre-existing compound-directive failures" are known but not pinned.** For u1.0 where the relay path is LLM-centric, will these cases now route correctly through the LLM? Should they be promoted from "known-fail" to "expected-pass" in the corpus?

5. **`autonomous_e2e_harness.py` is not wired to pytest.** It's a standalone script. Should it be converted to a pytest phase or kept as a separate one-shot harness for u1.0?

6. **The `_CAPTURE_STALL_TIMEOUTS` and `_CAPTURE_STALL_SECONDS` in orchestrator.py** protect against USB mic stalls. Do these need to be adjusted for the `InjectableCapture` path? (Current behavior: `InjectableCapture.get_chunk()` always returns a frame immediately, never None, so the stall watchdog should never fire. But it is untested explicitly.)

7. **For u1.0 "back-to-back command strings → one combined LLM call":** how does `InjectableCapture.feed_pcm()` chain two clips? Is there a gap protocol (silence duration between) or does the VAD segment them naturally? The trailing silence of clip 1 + leading silence of clip 2 need tuning.

8. **Is there a `pytest.ini` or `pyproject.toml` configuring test collection, timeouts, or markers?** Not seen in this scan; the test suite appears to rely on pytest defaults.

9. **The `tests/data/voice_lines_golden_digest.json` must be re-blessed after any intentional voice-line change.** For u1.0, the snap registry and voice line pools will change substantially. What is the process to invalidate and rebuild the golden under the new LLM-centric architecture?
