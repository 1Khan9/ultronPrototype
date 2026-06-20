# A1: Orchestrator main loop & dispatch decision-tree

Recon date: 2026-06-20. Branch: `claude/infallible-kepler-0a865d`. Tip: `c32d640`.
Source: `src/kenning/pipeline/orchestrator.py` (10,637 lines).

---

## Overview

The orchestrator is the single event-loop owner. It wires every subsystem and runs a four-state machine:

```
IDLE  ->  wake fires  ->  CAPTURING  ->  VAD end-of-speech  ->  PROCESSING
                                                                    |  STT -> dispatch -> LLM/TTS/relay
                                                                    |
                                                              FOLLOW_UP_LISTENING
                                                              (if follow_up_enabled)
```

Three threads:
- **Audio thread** (AudioCapture): only enqueues chunks.
- **Orchestrator thread**: everything else.
- **Interrupt watcher** daemon thread: runs wake-word detector during TTS to allow barge-in.

Speculative threads (daemon, per turn):
- Speculative STT (kicked ~32ms after speech silence onset, ~78ms ahead of VAD end)
- Speculative classification (chained after speculative STT)
- Speculative LLM (chained after classification when verdict is NO_SEARCH)

---

## Files & key symbols

### orchestrator.py — top-level

| Path:line | Symbol | Role |
|---|---|---|
| `orchestrator.py:162` | `class State` | Enum: IDLE / CAPTURING / PROCESSING / FOLLOW_UP_LISTENING |
| `orchestrator.py:183` | `_WAKE_MISHEAR` | Regex union of wake-word homophones + fillers |
| `orchestrator.py:194` | `_WAKE_REMNANT_RE` | Compiled: strips leading misheard wake tokens from transcript |
| `orchestrator.py:208` | `_FOLLOWUP_WAKE_RE` | Compiled: detects explicit wake in follow-up utterance → bypass addresser |
| `orchestrator.py:222` | `_CAPTURE_STALL_TIMEOUTS` | Const 2 (consecutive 0.5s timeouts = stall) |
| `orchestrator.py:223` | `_CAPTURE_STALL_SECONDS` | Const 1.0 (stall threshold for follow-up loop) |
| `orchestrator.py:226` | `_strip_leading_wake_remnant()` | Iterative strip (max 3x), fallback-only |
| `orchestrator.py:248` | `_trim_wake_from_capture()` | Audio-domain onset trim: clamps to `pre_roll_len`, guard before speech start |
| `orchestrator.py:300` | `_wake_command_cut()` | VAD-segmentation-based wake cut: returns sample index of command start |
| `orchestrator.py:353` | `class Orchestrator` | Main class |
| `orchestrator.py:5790` | `run()` | Main event loop |
| `orchestrator.py:6946` | `_wait_for_wake_word()` | IDLE-phase blocking loop; returns True on wake fire, False on shutdown |
| `orchestrator.py:7028` | `_capture_utterance()` | CAPTURING phase; VAD + Smart Turn logic; returns stripped audio ndarray |
| `orchestrator.py:7549` | `_strip_wake_audio()` | Post-capture VAD-segmentation wake drop (preferred) with onset-trim fallback |
| `orchestrator.py:7600` | `_follow_up_listen()` | FOLLOW_UP_LISTENING loop; returns `_FU_TIMEOUT` / `_FU_WAKE` / ndarray |
| `orchestrator.py:8756` | `_respond()` | PROCESSING/LLM path: interrupt watcher → response stream → TTS |
| `orchestrator.py:10031` | `_build_response_stream()` | Gate (web-search/no-search/search) + speculative consume + LLM generate |
| `orchestrator.py:9006` | `_gaming_conversational_prompt()` | Returns `ULTRON_GAMING_PERSONA` when gaming/testing active or 3B loaded |
| `orchestrator.py:3126` | `_is_relay_command()` | Probe: True iff strict relay match or relay toggle match |
| `orchestrator.py:3428` | `_maybe_handle_relay_speech()` | Relay handler (strict match + STT repair variants + force=True path) |
| `orchestrator.py:3126` | `_is_relay_command()` | Probe used by follow-up addressing gate |
| `orchestrator.py:4307` | `_maybe_dispatch_intent()` | Intent recognizer short-circuit (gaming mode engage/disengage/status + force-search) |
| `orchestrator.py:4389` | `_dispatch_intent_match()` | Routing for canonical intent phrases |
| `orchestrator.py:2786` | `_barebones_skip_web_search()` | True when gaming/testing mode + barebones_skip_web_search config |
| `orchestrator.py:1715` | `_skip_for_lean_gaming()` | True when lean gaming boot + named flag is on |
| `orchestrator.py:3380` | `_trace_turn_flow()` | Testing-mode usage capture → `logs/usage_trace.jsonl` + kenning.log |
| `orchestrator.py:3194` | `_GAMING_REFUSED_KINDS` | frozenset of RoutingIntentKind values blocked while anticheat active |
| `orchestrator.py:121` | `ULTRON_GAMING_PERSONA` | Import from `kenning.audio.llm_prompts` — persona for conversational LLM in gaming |

### relay_speech.py

| Path | Symbol | Role |
|---|---|---|
| `audio/relay_speech.py:1704` | `match_relay_command()` | Strict relay matcher; returns RelayCommand or None |
| `audio/relay_speech.py:6012` | `build_relay_line()` | Builds the final spoken line: snap pool or LLM-rephrase (gated by thinking_mode) |
| `audio/relay_speech.py:5977` | `is_complete_tactical_callout()` | Used by snap-early-endpoint (E3): True if text is a complete deterministic callout |
| `audio/relay_speech.py:1147` | `flavor_tails_enabled()` | Session flag: whether flavor tails append to snaps |
| `audio/relay_speech.py:1208` | `thinking_mode_enabled()` | Session flag: whether the LLM can author relay lines (default OFF) |

### command_normalizer.py

| Path | Symbol | Role |
|---|---|---|
| `audio/command_normalizer.py:975` | `normalize_command()` | Pre-routing normalization: strip junk → Valorant vocab correction → relay-lead recovery |

### Related modules (referenced by orchestrator)

| Module | Role |
|---|---|
| `kenning.audio.command_router` | Semantic command router (hybrid lexical+embedding) — `get_command_router()`, `router.route()` |
| `kenning.addressing` | AddressingClassifier for follow-up gate |
| `kenning.openclaw_routing` | `classify_routing()` for RoutingIntentKind |
| `kenning.audio.llm_prompts` | `ULTRON_GAMING_PERSONA`, `_RELAY_REPHRASE_SYSTEM` |
| `kenning.audio._ultron_identity` | `IDENTITY_POOLS`, `classify_identity_question()` |
| `kenning.web_search` | WebSearchGate, WebSearchExecutor, GateVerdict |
| `kenning.safety.testing_mode` | `is_testing_mode_active()` |
| `kenning.safety.anticheat` | `anticheat_active()`, `set_anticheat_active()` |
| `kenning.openclaw_routing.gaming_mode` | `is_gaming_mode_active()` |

---

## Control/data flow

### Phase 0: Boot

`__init__()` (lines 367–1572) in order:
1. `log_effective_config()` — logs all KENNING_* env vars
2. Diagnostics reset
3. Embedder sidecar spawn (separate venv, anticontamination)
4. Safety validator construction
5. `AudioCapture`, `RingBuffer`, `VoiceActivityDetector`, `WakeWordDetector` instantiation
6. `SmartTurnDetector` (if configured; adjusts VAD silence baseline)
7. Dual-STT registry (`make_dual_stt_engines()`)
8. `LLMEngine` — lean gaming boot loads 3B-CPU directly (line 922)
9. TTS engine + warmup
10. `AddressingClassifier` (`_load_addressing_classifier()`)
11. GamingModeManager (hoisted out of coding_voice so lean boot finds it)
12. CodingVoiceController (`_load_coding_voice_if_enabled()`) — SKIPPED in lean gaming boot
13. Semantic command router build + embedding sidecar verification (lines 1527–1572)
14. `gaming_mode.engage_at_startup` → silent auto-engage

### Phase 1: IDLE → wake → CAPTURING

**`run()` main loop top** (lines 5817–5963):
```
loop iteration:
  _maybe_reload_config()                          # settings-panel hot-reload
  [announce pending completions, narrations, etc.]
  
  if _pending_capture.is_set:
    speech = _capture_utterance()                # barge-in / wake-during-follow-up path
  elif follow_up_until not expired AND follow_up_enabled:
    outcome = _follow_up_listen(deadline)
    # _FU_TIMEOUT -> continue (IDLE)
    # _FU_WAKE   -> speech = _capture_utterance()
    # ndarray    -> speech = outcome, came_from_follow_up = True
  else:
    _wait_for_wake_word()                        # blocks
    speech = _capture_utterance()
```

**`_wait_for_wake_word()`** (lines 6946–7002):
- Drains audio queue, resets wake+ring
- Per-chunk: `ring.write(chunk)` then `wake.process(chunk)`
- Capture-stall watchdog: 2 consecutive 0.5s get_chunk timeouts → `_restart_capture_stream()`
- Every 0.1s: `_drain_gui_actions()` (fast settings-panel action poll)

**`_capture_utterance()`** (lines 7028–7529):
1. `audio.drain()` — purge stale backlog from queue
2. `_cancel_background_summarizer()`
3. `_reset_speculative_stt_state()`
4. `_kick_off_tts_preopen()` — pre-open PortAudio output stream
5. Cold pre-roll snapshot from ring: `ring.snapshot(cold_pre_roll_samples)` — per-word configurable, extended when KENNING_WAKE_TRIM_TO_SPEECH=1
6. VAD pre-roll: pre-feed `chunks[0]` to `vad.process()` to latch `speech_seen` (fixes empty_capture freeze)
7. Live capture loop:
   - `get_chunk(timeout=0.5)` — capture-stall watchdog (2 timeouts while not speech_seen → restart)
   - `vad.process(chunk)`:
     - SPEECH_START: latch `speech_seen`, cancel in-flight speculative STT
     - SPEECH_END (while speech_seen):
       - If Smart Turn eligible: `_run_smart_turn(captured)` → `_classify_smart_turn_verdict()`
         - `early_complete` → break
         - `medium_complete` → wait `medium_grace_ms` more
         - `incomplete` → bump VAD silence, set extension anchor
         - `undecided` → trust VAD
       - **Min-speech floor** (KENNING_SMART_TURN_MIN_COMPLETE_MS=1000): sub-floor complete/medium → downgrade to incomplete UNLESS `_snap_early_endpoint=True` AND `is_complete_tactical_callout(speculative_text)`
       - Legacy path: trust VAD, break
   - Speculative STT kick-off: after 2 consecutive silence chunks while speech_seen → `_kick_off_speculative_stt(audio_so_far)`; invalidate on SPEECH_START
   - Long-utterance bump: >threshold_seconds of speech → raise VAD silence requirement
8. `_strip_wake_audio(full_buffer, pre_roll_len, speech_start_samples)`:
   - VAD segmentation (Silero model) → `_wake_command_cut()` → drop wake-word segment
   - Fallback: `_trim_wake_from_capture()` (onset-based)
9. Return stripped ndarray

### Phase 2: STT

**In `run()` after capture** (lines 5992–6046):
1. `_kick_off_tts_preopen()` (belt-and-braces)
2. `_collect_speculative_stt()` — hit: skip foreground STT; miss: call `stt.transcribe(speech)`
3. Empty transcript → `continue` (skip turn)
4. **Wake-word-only check**: `_WAKE_REMNANT_RE.match(user_text)` consumes whole transcript → log `routing:wake_word_only`, continue

### Phase 3: Addressing gate (follow-up only)

**Lines 6048–6105** (only when `came_from_follow_up`):
1. If `_is_relay_command(user_text)` OR `_FOLLOWUP_WAKE_RE.match(user_text)` → skip classifier, treat as addressed
2. Else: `addressing.classify(user_text, seconds_since_response)` → `AddressingDecision`
   - Not ADDRESSED → log `addressing:rejected_follow_up`, continue (discard turn)
   - ADDRESSED → proceed

Wake-word path (not follow-up): no addressing gate; all wake-word-triggered utterances are treated as addressed.

### Phase 4: Dual-history record

`_record_dialogue_turn("user", user_text)` — line 6111, BEFORE any short-circuit.

### Phase 5: Pre-routing normalization

**Lines 6128–6145**:
- `_raw_stt = user_text` — snapshot BEFORE normalization (used for toggle matchers)
- `normalize_command(user_text)` → `_normed`
  - `_strip_leading_junk()` (leading homophones/fillers)
  - Valorant vocab correction (agent names, location terms)
  - Relay-lead recovery: clipped callouts → prepend "tell my team"
  - Gates relay-lead via `_relay_intent.py` (semantic check, prevents false lead injection on questions)
- If `_normed != user_text`: `user_text = _normed`
- Logs `routing:normalized` with raw+normalized+changed

### Phase 6: Dispatch decision order

All of the following are tried in this exact order. First handler that returns True consumes the turn.

#### 6a. Intent recognizer (line 6153)
`_maybe_dispatch_intent(user_text)`:
- `intent.enabled=False` (default) → False
- Calls `recognizer.process_utterance(user_text)` → `_dispatch_intent_match(match)`
- Handles: `_INTENT_ENGAGE_PHRASES` (gaming mode engage), `_INTENT_DISENGAGE_PHRASES` (disengage), `_INTENT_STATUS_PHRASES` (status), `_INTENT_FORCE_SEARCH_PHRASES` (sets `_next_turn_force_search=True`, returns False — turn continues to LLM)

#### 6b. Evolution command intercept (line 6178)
`_maybe_handle_evolution_command(user_text)`: strict matcher; "evolve now" / "evolution status" → dispatched directly.

#### 6c. Capability routing (lines 6211–6624) — IF `coding_voice is not None`

`classify_routing(user_text, ...)` from `kenning.openclaw_routing` → `RoutingIntentKind`

Then in order:
1. `_maybe_handle_report_concern(user_text)` — "log a concern about that response"
2. `_maybe_handle_run_program(user_text)` — "run the calculator"
3. `_maybe_handle_spotify(user_text)` — music control
4. `_maybe_handle_scrap_command(user_text)` — "scrap it"
5. `_maybe_handle_anticheat_toggle(user_text)` — "enable anticheat mode"
6. `_maybe_handle_llm_device_switch(user_text)` — "switch to the GPU"
7. `_maybe_handle_flavor_toggle(user_text)` — "flavor off" / "flavor on"
8. `_maybe_handle_thinking_toggle(user_text)` — "thinking mode on/off"
9. `_maybe_handle_relay_toggle(user_text)` — "mute the team chat"
10. `_maybe_handle_relay_speech(user_text)` — strict relay matcher → **team mic channel**
11. `_maybe_handle_settings_gui(user_text)` — "pull up your settings"
12. `_maybe_handle_stop_button(user_text)` — "show the stop button"
13. `_maybe_handle_deep_research(user_text)` — "research X in depth"
14. `_maybe_handle_deep_recall(user_text)` — "recall everything about X"
15. `_maybe_handle_code_exploration(user_text)` — "search the codebase for X"
16. `_maybe_handle_history_recall(user_text)` — "what did I say about X?"
17. `_maybe_refuse_capability_in_gaming(routing_intent)` — anticheat refusal gate
18. `OPEN_LAST_SOURCE` kind → `_handle_open_last_source()`
19. `NAVIGATE_TO_SITE` kind → `_handle_navigate_to_site()`
20. `coding_voice.handle_capability_intent(routing_intent)` → `_handle_capability_response()` — all remaining coding/capability kinds

If all return False/None → log `routing:fallthrough_to_llm`

#### 6d. Lean gaming boot fallbacks (lines 6626–6771) — IF `coding_voice is None`

Duplicate of the above handlers for the bare-bones gaming path (no coding_voice loaded):
1. `_maybe_handle_settings_gui(user_text)` (lean)
2. `_maybe_handle_stop_button(user_text)` (lean)
3. `_maybe_handle_llm_device_switch(user_text)` (lean)
4. `_maybe_handle_flavor_toggle(_raw_stt)` — NOTE: uses `_raw_stt` not `user_text` to avoid normalized relay-lead hiding the toggle text
5. `_maybe_handle_thinking_toggle(_raw_stt)` — same reason
6. `_maybe_handle_relay_toggle(user_text)` (lean)
7. `LeanSpotifyHandler.handle(user_text, _speak, _strip_leading_wake_remnant)` (lean)
8. `_maybe_handle_relay_speech(user_text)` (lean) — **strict relay matcher → team mic**

#### 6e. Semantic command router (lines 6773–6883)

After all exact matchers miss:
```
_cr = get_command_router()
_rd = _cr.route(user_text)
```
- `_rd.abstained` → skip (fall to LLM)
- `_rd.family == "team_callout"` AND NOT abstained → `_maybe_handle_relay_speech(user_text, force=True)` — **team mic, forced**
- `_rd.family == "identity"` AND NOT abstained → `classify_identity_question()` → pick from `IDENTITY_POOLS`, `_speak()` — **desktop channel**
- `_rd.family == "desktop_refuse"` AND NOT abstained → anticheat check → in-character refusal or fall-through

Router-consumed → `_router_consumed = True`, log `loop:iteration_end via=semantic_router`

#### 6f. LLM conversational fallback (line 6901)

All prior handlers returned False / router abstained:
```python
self._respond(user_text, routing_intent_kind=_intent_kind)
```

### Phase 7: `_respond()` — LLM path

**Lines 8756–8926**:
1. Clear `_interrupt`, set LLM intent kind + temperament hint
2. Start interrupt watcher thread (`_interrupt_watcher`)
3. `token_stream = _build_response_stream(user_text)` (generator)
4. Gated generator: yields tokens until interrupt/shutdown → `tts.speak_stream(gated())`
5. Finally: set interrupt (releases watcher), clear intent kind/temperament, emit telemetry

### Phase 8: `_build_response_stream()` — gate + token generation

**Lines 10031–10400+**:
1. **Local clock short-circuit** (`maybe_local_clock_reply`): bare time/date → yield text, return
2. **Speculative classification consume** (`_collect_speculative_classification`): reuse cached gate verdict + RAG future from silence-wait speculation
3. **Intent force-search override**: `_next_turn_force_search=True` → override verdict to SEARCH
4. **No web gate configured**: yield conversational ack → `llm.generate_stream(apply_brevity_hint(user_text), system_prompt=_gaming_conversational_prompt(), enable_thinking=False)`
5. **Bare-bones gaming skip**: verdict → NO_SEARCH (skip preflight LLM)
6. **Web gate classify**: `web_gate.classify(user_text)` → GateVerdict
7. **Uncertainty upgrade**: `apply_uncertainty(verdict, user_text)` — may promote NO_SEARCH → SEARCH
8. **NO_SEARCH / UNCERTAIN branch**:
   - `_maybe_conversational_ack()` → yield ack (suppressed in gaming mode)
   - Speculative LLM consume (`_collect_speculative_llm`) — yield buffered tokens; on 0-yield fall to fresh
   - `llm.generate_stream(apply_brevity_hint(augmented_text), ..., system_prompt=_gaming_conversational_prompt(), enable_thinking=False)`
9. **SEARCH branch**: `_search_augmented_tokens()` — ack phrase + Brave/Jina + ranked sources + LLM

### Phase 9: Relay path (inside `_maybe_handle_relay_speech`)

**Lines 3428–3681**:
1. Check `cfg.enabled` — bail if off
2. Progressive STT repair: try `user_text`, `correct_callout_stt(stripped)`, `correct_callout_stt(user_text)`, `stripped` — first match wins
3. `match_relay_command(variant, names=names)` — strict parser
4. `force=True` path: wrap raw text in RelayCommand directly (router-confirmed callout)
5. Session mute check: if `_relay_runtime_enabled=False` → speak muted notice, return True
6. **Roast** / **fun_fact** paths: pick verbatim from curated text files (never LLM)
7. **Main path**: `build_relay_line(command, llm, rephrase=thinking_mode_enabled())`
   - `thinking_mode_enabled()=False` (default) → snap from deterministic pool
   - `thinking_mode_enabled()=True` → LLM-rephrase (the 3B)
8. Synthesize: `tts._synthesize(relay_tts_text(line))` → `(pcm, sr)`
9. Tee outputs:
   - `broadcast.submit(pcm, sr)` — OBS mirror (optional)
   - `monitor.maybe_submit(pcm, sr)` — user's speakers echo (if `echo_to_user`)
   - `waveform.submit(pcm, sr)` — stream waveform overlay
10. PTT: `_ptt_hold()` → `play_to_device(pcm, sr, device, cancel_event=_relay_interrupt)` → `_ptt_release()`
11. Relay barge-in watcher thread (when stop-watcher enabled)
12. `_trace_turn_flow(channel="team_mic")`
13. Extend follow-up window: `_relay_follow_up_seconds` (default 120s)

### Follow-up window lifecycle

After any handled turn:
- If `_addr_cfg.follow_up_enabled`:
  - `follow_up_until = monotonic() + warm_mode_duration_seconds` (or `relay_follow_up_seconds` for relay turns)
  - Next iteration: `_follow_up_listen(deadline)` instead of `_wait_for_wake_word()`
- Relay turns extend the window longer (`follow_up_seconds=120s` vs `warm_mode_duration_seconds`)
- `follow_up_enabled` defaults to **False** (wake word required by default, config `addressing.follow_up_enabled`)

---

## Key findings

1. **Dispatch is a strict priority list — not a classifier**. Every handler is tried top-to-bottom with a strict regex/parser gate. Only after all exact matchers fail does the semantic router fire. Only after the router abstains does the LLM run.

2. **Two code paths for the same handlers** (lean-gaming vs full). When `coding_voice is None` (lean gaming boot), handlers 6d repeat most of 6c outside the `if self.coding_voice` block. This means relay, flavor toggle, thinking toggle, Spotify, etc. all appear **twice** in the dispatch sequence — first inside the `coding_voice` block, then duplicated in the lean-gaming fallback section. This is a maintenance burden and an extension gotcha.

3. **`_looks_like_slot_callout`** referenced in MEMORY.md (stream-build branch `da28d22`) is **NOT present** on this branch (`c32d640`). The forced-relay path via semantic router uses `force=True` on `_maybe_handle_relay_speech` instead.

4. **`_raw_stt` vs `user_text` split** (line 6128): toggle matchers (`_maybe_handle_flavor_toggle`, `_maybe_handle_thinking_toggle` in lean path) intentionally use `_raw_stt` not `user_text`, because `normalize_command` can prepend "tell my team" to a toggle phrase ("flavor off" → "tell my team flavor off") hiding it from the toggle matcher.

5. **Relay channel vs desktop channel** decided purely by which handler fires:
   - `_maybe_handle_relay_speech()` → `play_to_device(...)` — **team mic**
   - `_respond()` → `tts.speak_stream(...)` — **desktop speakers**
   - Identity pool answers → `_speak()` — **desktop speakers**
   - No routing metadata record distinguishes these at the LLM layer; channel is baked into the handler.

6. **`normalize_command` is a pre-routing rewrite** (line 6130). It runs BEFORE all matchers see the text. This means a relay lead added by the normalizer can "force" an utterance into the relay handler even if the user didn't say "tell my team". This is the relay-lead recovery path — intentional, but semantically important for U1.0: the "implicit relay intent" detection currently lives inside `normalize_command` (via `_relay_intent.py` sidecar check), not in a separate classification layer.

7. **Gaming conversational persona** (`_gaming_conversational_prompt()`): injects `ULTRON_GAMING_PERSONA` as `system_prompt` into `llm.generate_stream()`. Also keyed on the model path — if the 3B path is loaded, ULTRON_GAMING_PERSONA is forced regardless of the gaming-mode flag. This is the "desktop persona leak prevention" belt-and-suspenders (line 9029).

8. **Thinking mode** (line 3546–3554): `thinking_mode_enabled()` session flag in `relay_speech.py`. When OFF (default), `rephrase=False` forces `build_relay_line` to snap from deterministic pool. When ON, the 3B LLM authors the relay line. This is the primary LLM-relay gate.

9. **Speculative pipeline** (3 stages): speculative STT (kicked during silence-wait) → speculative classification (chained) → speculative LLM generation (chained). All fail-open; on invalidation (SPEECH_START resumed), foreground paths run normally. The speculative LLM only fires on NO_SEARCH turns.

10. **Smart Turn V3** is the primary end-of-turn mechanism (not pure silence-based VAD). It classifies the captured audio into complete/medium/incomplete/undecided and either submits early or extends. The min-speech floor (`KENNING_SMART_TURN_MIN_COMPLETE_MS=1000ms`) prevents premature end on post-wake-pause fragments.

11. **Audio-domain wake removal** (`_strip_wake_audio`, line 7549): runs Silero VAD segmentation over the full captured buffer to find the wake-word segment and drop it before STT. The text-level `_strip_leading_wake_remnant` is the fallback. Both are gated by `KENNING_WAKE_TRIM_TO_SPEECH=1` (default ON).

12. **`_trace_turn_flow()`** (line 3380): logs the full pipeline (raw→normalized→route→channel→spoken) to both `kenning.log` (tlog) AND `logs/usage_trace.jsonl`. No-op outside testing mode. This is the key observability seam for corpus analysis.

13. **Follow-up addressing gate**: when `follow_up_enabled=True`, every utterance in the window passes through `AddressingClassifier.classify()` UNLESS it matches `_is_relay_command()` or `_FOLLOWUP_WAKE_RE` (explicit wake leads → bypass). The classifier (flan-T5 zero-shot + rule features + log-odds fusion) gates to ADDRESSED or NOT_ADDRESSED. `follow_up_enabled` defaults to False — wake word required.

---

## Flags & config

| Key / Env | Default | Effect |
|---|---|---|
| `addressing.follow_up_enabled` (config.yaml) | `False` | Enables follow-up window; False = wake required for every turn |
| `addressing.warm_mode_duration_seconds` | (config) | Duration of follow-up window after each turn |
| `KENNING_WAKE_TRIM_TO_SPEECH` | `1` (ON) | Enable audio-domain wake removal via VAD segmentation |
| `KENNING_WAKE_TRIM_GUARD_MS` | `200` | Guard samples before command onset in onset-based trim |
| `KENNING_WAKE_CAPTURE_PRE_ROLL_MS` | `500` | Generous pre-roll when wake trim is ON |
| `KENNING_SNAP_EARLY_ENDPOINT` | `0` (OFF) | Allow Smart Turn to end sub-floor captures when callout is complete |
| `KENNING_SMART_TURN_MIN_COMPLETE_MS` | `1000` | Min speech duration before Smart Turn complete/medium is trusted |
| `KENNING_ADDRESSING_TAU` | `0.20` | Cost-asymmetric threshold for addressing log-odds → sigmoid |
| `KENNING_RELAY_TEAM_DSP` | (env) | Enable team-path DSP (rumble HP + RMS normalize + comfort noise) |
| `KENNING_RELAY_VM_LEVEL_GUARD` | OFF | Boot-time VoiceMeeter B1 fader guard |
| `KENNING_PTT_ENABLED` / `settings.PUSH_TO_TALK_ENABLED` | False | Enable auto PTT via USB-HID |
| `KENNING_EMBEDDER_PARENT_PID` | (set by orchestrator) | Embedder sidecar deadman: kills sidecar ~3s after parent death |
| `KENNING_TELEMETRY` | off | Per-turn telemetry (opt-in only) |
| `relay_speech.rephrase` (config) | True | Master rephrase gate (AND'd with `thinking_mode_enabled()`) |
| `relay_speech.follow_up_seconds` (config) | 120.0 | Follow-up window duration after relay turns |
| `relay_speech.enabled` (config) | False | Enables team relay feature |
| `relay_speech.echo_to_user` (config) | False | Echo relay audio to user's default speakers |
| `gaming_mode.engage_at_startup` (config) | False | Auto-engage gaming mode (lean boot) |
| `gaming_mode.barebones_skip_web_search` (config) | True | Skip web-search preflight in gaming mode |
| `gaming_mode.llm_gpu_layers` (config) | 0 | GPU layers for gaming LLM (default CPU-only) |
| `intent.enabled` (config) | False | Enable cosine intent recognizer |
| `mcp.enabled` (config) | False | Enable MCP client |
| `vad.smart_turn.enabled` (config) | — | Enable Smart Turn V3 end-of-turn model |
| `vad.smart_turn.completion_threshold` | 0.5 | Smart Turn probability threshold for complete |
| `stt.engine` (config) | `auto` | STT engine: auto/whisper/parakeet |
| `KENNING_DEBUG_CAPTURE_DUMP` | OFF | Dump pre/post-strip WAV files to logs/ for capture debugging |
| `KENNING_LLM_MODEL_PATH` | (env override) | Override LLM model path (silent override — known source of bugs) |

---

## Extension points

For U1.0, these are the natural seams:

1. **`_maybe_handle_*` handler slot** (line ~6230–6535): insert a new handler before the relay block and it will run for all addressed turns. The U1.0 "route ALL through 8B LLM with prompt template" could be a single handler here that intercepts non-relay intents and selects a template.

2. **`normalize_command()` in `command_normalizer.py`**: currently does relay-lead injection implicitly (via `_relay_intent.py` sidecar). U1.0 could add an "intent category" annotation here (ME_ONLY / RELAY / DISCORD / OUT_LOUD) that downstream handlers consume.

3. **`_gaming_conversational_prompt()`** (line 9006): single injection point for system prompt override. U1.0 verbosity levels (no/low/high) could be threaded as an additional prompt parameter here, or via `apply_brevity_hint`.

4. **`build_relay_line()` in `relay_speech.py`**: the snap pool vs LLM gate. U1.0 could make this the 8B LLM call with a prompt template + exemplar injection from the curated pools. `thinking_mode_enabled()` already provides the on/off gate.

5. **`_trace_turn_flow()` / `logs/usage_trace.jsonl`** (line 3380): the observability seam. U1.0 training/refinement loop should consume this file.

6. **`SNAP_REGISTRY` / `SnapRule` in `audio/voice_lines.py`**: data-driven snap registry — adding a SnapRule adds a new snap with no code. U1.0 exemplar injection could load from this registry.

7. **`get_command_router().route()` + `_maybe_handle_relay_speech(force=True)`** (line 6797): the router's `team_callout` family already forces the relay. U1.0 non-explicit relay detection (person talking to team without saying "tell my team") should slot in here, either as new router families or a higher-level classifier that precedes the router.

8. **Addressing gate** (`addressing.classify()`, line 6077): currently binary ADDRESSED/NOT_ADDRESSED. U1.0 needs a 3-way classification: (A) to Discord / (B) out-loud / (C) to Ultron for ME_ONLY. This is a new dimension of the existing AddressingClassifier.

9. **`_intent_recognizer` / `_maybe_dispatch_intent()`**: intent.enabled=False by default; registering new phrases + handlers extends the quick-dispatch path without touching the main dispatch block.

10. **Agent-specific libraries** in `audio/voice_lines.py` (`AGENT_FLAVOR`, etc.): the curated library + `SNAP_REGISTRY` are the extension surface for adding new relay content without code changes.

---

## Retire-not-remove candidates (u1.0)

1. **Strict relay matchers as routers** (`match_relay_command()`, relay-lead recovery in `normalize_command()`): in U1.0 these detect intent and pick the relay template, not the full response. The matcher logic is retained; the "match → build_relay_line(snap pool only)" end-to-end is the part being repurposed. `build_relay_line` becomes the 8B-LLM call with the snap pool as exemplars.

2. **`thinking_mode_enabled()` flag** (relay_speech.py:1208): U1.0 makes the LLM the default for relay authoring. This flag becomes the "pure snap fallback" toggle rather than "LLM enable". The name may invert.

3. **`_gaming_conversational_prompt()` model-path check** (line 9029): the belt-and-suspenders "if 3B model path is loaded → Ultron persona" check. U1.0 standardizes on Ultron persona everywhere; this branch can be simplified.

4. **`_maybe_conversational_ack()`** (line 8965): suppressed in gaming mode already (line 8985). In U1.0, if the LLM is always on, the ack suppression logic should be reviewed — a latency-masking ack before LLM output may still be needed for non-gaming turns.

5. **Dual coding_voice / lean-gaming dispatch duplication** (lines 6626–6771 repeating 6211–6624): a maintenance hazard. U1.0 should unify. One clean approach: each handler checks its own mode-gate internally; the dispatch block calls all handlers unconditionally.

6. **`_maybe_handle_relay_speech(force=True)` from semantic router**: in U1.0, the router abstaining or classifying as "team_callout" both feed the same relay path. The `force=True` path (which bypasses strict parsing and relays the raw text) may be retired in favor of the LLM path, since U1.0 doesn't need the strict parser to succeed.

---

## Gotchas

1. **`_raw_stt` vs `user_text` split is critical**. Toggle matchers in the lean path (flavor, thinking) take `_raw_stt` NOT `user_text`. If a new handler is added in the lean-gaming block and accidentally uses `user_text`, a toggle phrase with a normalizer-injected lead ("tell my team flavor off") will never match.

2. **`coding_voice is None` lean-gaming gate** (line 6211 and 6632): the ENTIRE capability routing block (OpenClaw, coding, Spotify, etc.) is guarded by `if self.coding_voice is not None`. Adding a new non-gaming handler inside this block silently skips it in lean gaming. Duplicate in the lean fallback section is required (or restructure).

3. **`normalize_command()` can inject a relay lead** before any matcher sees the text. If U1.0 adds a "is this for me vs team vs discord" classifier, it must run on `_raw_stt` OR the normalizer must produce the canonical lead with an intent annotation, not alter the text in-place.

4. **Follow-up window is OFF by default** (`addressing.follow_up_enabled=False`). The addressing classifier code exists and works, but the wake-word-only mode is the live default. U1.0 "always listening" changes this fundamentally — the addressing gate becomes the primary discriminator, not an optional follow-up mode.

5. **Semantic router (`command_router.route()`)** fires only AFTER all exact matchers have missed. It uses EmbeddingGemma-300M in a separate sidecar process. The sidecar must be running for hybrid mode; without it, the router falls to lexical-only which has lower coverage. The boot sequence verifies embedding availability and retries once (lines 1527–1572).

6. **Speculative LLM is only for NO_SEARCH turns**. SEARCH turns do not benefit from the speculative pipeline. In U1.0, if the 8B LLM is on every turn, the speculative path needs extending or redesigning.

7. **`thinking_mode_enabled()` and `flavor_tails_enabled()` are in-process session flags** (not config keys). They are set via voice commands and reset at process restart. There is no persistence. U1.0 should clarify the persistence model.

8. **Relay PTT (`_ptt_hold` / `_ptt_release`)** wraps every `play_to_device()` call. If U1.0 routes all responses through the 8B LLM, the desktop LLM response still goes via `_respond()` → `tts.speak_stream()`, NOT through PTT. The PTT path is relay-specific.

9. **`_GAMING_REFUSED_KINDS`** (line 3194): these desktop/browser kinds are refused while anticheat is active. The refusal fires in `_maybe_refuse_capability_in_gaming()` BEFORE `coding_voice.handle_capability_intent()`. If U1.0 adds new routing kinds that are also desktop-interaction, they must be added to this frozenset.

10. **The `_respond()` path always calls `_gaming_conversational_prompt()` as `system_prompt`**. If the 8B LLM is always on, and the gaming persona is always Ultron when gaming is active, the persona selection logic is already in place. The U1.0 change is making this the only path (retiring the desktop "Kenning" persona for gaming contexts).

---

## Open questions

1. **Who decides ME_ONLY vs RELAY vs DISCORD vs OUT_LOUD in U1.0?** Currently: `_is_relay_command()` (strict) + semantic router `team_callout` family. Non-explicit relay intent is not detected. The `normalize_command()` relay-lead recovery is a heuristic. U1.0 needs a proper intent classification here — is it the 8B LLM itself (via structured output) or a lighter classifier?

2. **How is the relay system prompt / template library injected into the 8B LLM call?** Currently `build_relay_line()` in relay_speech.py orchestrates this. In U1.0, does `build_relay_line` become the 8B LLM call, or does the orchestrator's `_respond()` handle it with a different prompt template?

3. **Does U1.0 retain the separate team-mic audio channel** (`play_to_device()` → VoiceMeeter B1 bus)? The audio routing is independent of LLM authorship. If LLM authors all relay lines, the audio path can stay unchanged.

4. **Verbosity levels (no/low/high)** — where in the dispatch do they attach? Currently `apply_brevity_hint()` is applied in `_build_response_stream`. U1.0 verbosity levels would replace/extend this. Does verbosity also apply to relay lines?

5. **`thinking_mode_enabled()` default is OFF** — deterministic snaps. U1.0 wants LLM on by default. How does the toggle semantics change? Does the snap pool become "LLM-as-fallback-when-disabled" rather than "snap-as-default"?

6. **Addressing classifier** (currently flan-T5 zero-shot): U1.0 "always listening" needs this to be fast, cheap, and accurate for Discord vs stream vs Ultron discrimination. Is flan-T5 sufficient, or does U1.0 require a different model?

7. **Speculative LLM pipeline** — currently only kicks for NO_SEARCH turns. Does U1.0's "always LLM" path make the speculative pipeline the main latency lever for ALL turns? If so, the relay path (which currently bypasses the LLM when thinking_mode=OFF) would need speculative support.

8. **`_looks_like_slot_callout()`** referenced in MEMORY (stream-build branch) is NOT on this branch. The stream-build has a slightly different slot-callout forced-relay path. Which branch is the U1.0 base?

9. **`ULTRON_GAMING_PERSONA`** in `kenning.audio.llm_prompts` — in U1.0 this becomes the primary persona for all gaming turns. What is the persona for non-gaming turns? Is the "Kenning" desktop persona retained for desktop-assistant use cases?

10. **`_trace_turn_flow()` no-op outside testing mode** — the U1.0 corpus pipeline needs production-safe logging of routing decisions. Does `_trace_turn_flow()` get promoted to always-on (gated by a log level, not testing mode), or does U1.0 add a separate lightweight routing logger?
