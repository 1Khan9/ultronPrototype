# B9: MAP testing-mode usage trace & the tracing substrate

## Overview

The Kenning/Ultron codebase has a layered tracing system with three distinct, separately-gated substrates:

1. **`kenning.trace` (thread-local structured prefix logging)** — A lightweight module that tags every `logging` call with a `turn=N phase=X` prefix so the per-session rotating log (`logs/kenning.log`) is grep-able per utterance. Used pervasively in the orchestrator across every pipeline stage.

2. **`_trace_turn_flow` + `logs/usage_trace.jsonl` (testing-mode durable capture)** — A method on `Orchestrator` that, when `testing_mode.enabled` is true (or the runtime flag is set), writes a full-turn JSONL record capturing raw STT → normalized → route + reason → final spoken line → channel. This is the "historical log" the corpus test harness was designed around. Gated strictly by `is_testing_mode_active()`.

3. **`kenning.observations` (canonical cross-subsystem observation framework)** — Append-only `data/observations.jsonl` that records structured events (routing verdict, addressing verdict, LLM call, memory retrieval, thinking-drift samples) with schema-stable fields. Always active when the writer is enabled; not gated by testing mode.

4. **`kenning.diagnostics` (spoken-audio diagnostics, operator toggle)** — Gates verbose TTS/audio logging (exact spoken text + per-utterance BLIP analysis). Active only when the sentinel file `~/.kenning/audio_diagnostics_on` exists OR `config.diagnostics.spoken_audio_logging=true` (the `diagnostics` key does NOT exist in `KenningConfig` today; the code reads it via `getattr(..., None)` and the path silently returns False — effectively sentinel-only).

5. **`kenning.observability.private_telemetry` (`data/observability/private_metrics.jsonl`)** — Privacy-by-construction aggregate telemetry; local-only, off unless `KENNING_TELEMETRY=opt-in`. Not a per-turn trace but a hashed-identifier event store.

6. **Offline corpus tracers (`scripts/relay_test/trace_corpus*.py`)** — Standalone scripts that drive the relay pipeline offline over synthetic corpora, logging every normalization/routing/snap/tail/prompt stage to a JSONL. These are NOT the runtime trace; they are the offline audit tooling.

---

## Files & Key Symbols

| File | Key Symbols | Role |
|------|-------------|------|
| `src/kenning/trace.py` | `set_turn`, `get_turn`, `next_turn`, `set_phase`, `get_phase`, `fmt`, `tlog`, `phase`, `snapshot`, `restore` | Thread-local structured-prefix log substrate |
| `src/kenning/pipeline/orchestrator.py:3380` | `Orchestrator._trace_turn_flow` | Testing-mode per-turn JSONL write + `turn:flow` tlog |
| `src/kenning/pipeline/orchestrator.py:5820` | `trace.next_turn()` call site | Allocates new turn id at top of every voice-loop iteration |
| `src/kenning/pipeline/orchestrator.py:5821` | `trace.set_phase("loop")` | Sets initial phase at loop start |
| `src/kenning/pipeline/orchestrator.py:6002` | `trace.set_phase("stt")` | Phase transition at STT |
| `src/kenning/pipeline/orchestrator.py:6053` | `trace.set_phase("addressing")` | Phase transition at addressing |
| `src/kenning/pipeline/orchestrator.py:6152` | `trace.set_phase("intent")` | Phase transition at intent |
| `src/kenning/pipeline/orchestrator.py:6177` | `trace.set_phase("evolution")` | Phase transition at evolution |
| `src/kenning/pipeline/orchestrator.py:6212` | `trace.set_phase("routing")` | Phase transition at routing |
| `src/kenning/pipeline/orchestrator.py:6885` | `trace.set_phase("respond")` | Phase transition at LLM respond |
| `src/kenning/diagnostics.py` | `audio_diagnostics_enabled`, `reset_for_new_session`, `enable_for_testing` | Operator spoken-audio diagnostics toggle |
| `src/kenning/safety/testing_mode.py` | `is_testing_mode_active`, `set_testing_mode_active` | Testing-mode runtime gate |
| `src/kenning/config.py:3813` | `TestingModeConfig` (field `enabled: bool = False`) | Config binding for testing_mode |
| `src/kenning/config.py:2592` | `LoggingConfig` (fields `file`, `level`, `format`, `datefmt`) | Logging config binding |
| `src/kenning/utils/logging.py` | `configure_logging`, `get_logger` | RotatingFileHandler setup (`logs/kenning.log`, maxBytes=5MB, backupCount=3) |
| `src/kenning/observations/schema.py` | `Observation`, `new_event_id`, `KNOWN_SUBSYSTEMS`, `KNOWN_OUTCOMES` | Canonical observation schema |
| `src/kenning/observations/writer.py` | `ObservationWriter`, `emit_observation` | Thread-safe JSONL appender → `data/observations.jsonl` |
| `src/kenning/observations/integrations.py` | `observe_routing_verdict`, `observe_addressing_verdict`, `observe_retrieval`, `observe_llm_call`, `observe_llm_thinking_drift_sample` | Per-subsystem observation helpers |
| `src/kenning/observations/__init__.py` | Re-exports all observation symbols | Canonical import point |
| `src/kenning/observability/private_telemetry.py` | `PrivateMetricsStore`, `HashedEvent`, `hash_root`, `is_telemetry_enabled` | Hashed-id aggregate telemetry |
| `src/kenning/memory/qdrant_store.py:383` | `QdrantStore._trace` | Best-effort `trace.tlog` wrapper for memory ops |
| `src/kenning/memory/qdrant_store.py:647` | `trace.tlog(logger, "memory:recent", ...)` | Traces memory filter ratio per turn |
| `src/kenning/web_search/gating.py:466` | `_trace` helper, `gate:rules_start/match` trace calls | Web-search gate traces |
| `src/kenning/tts/kokoro_engine.py:661` | `SPOKEN(speak): %r` log line (diagnostics-gated) | Logs exact spoken text |
| `src/kenning/tts/kokoro_engine.py:719` | `SPOKEN(stream): %r` log line (diagnostics-gated) | Logs exact streamed text |
| `src/kenning/tts/kokoro_engine.py:1118` | SPOKEN-BLIP analysis (diagnostics-gated) | Per-sentence audio quality check |
| `src/kenning/llm/inference.py:2043` | `logger.info("LLM messages ...", ...)` with per-message 200-char preview | Message list shape and preview logged at INFO |
| `src/kenning/llm/inference.py:1808` | `logger.info("LLM: %d chars in %.2fs (%d tokens)", ...)` | Blocking-path LLM call timing |
| `src/kenning/llm/inference.py:2092` | `logger.info("LLM TTFT: %.0fms", ...)` | First-token latency on streaming path |
| `src/kenning/llm/inference.py:1814` | `observe_llm_call(event_type="generate", ...)` | Observation record for blocking LLM |
| `src/kenning/resilience/error_log.py` | `ErrorLog`, `_default_log_path` → `logs/errors.jsonl` | Structured error JSONL |
| `scripts/relay_test/trace_corpus.py` | `main()`, `_route_info`, `_snap_only` | Offline relay corpus tracer |
| `scripts/relay_test/trace_corpus_full.py` | `main()`, `_router_decision`, `_route_info` | Full-stage offline corpus tracer |

---

## Control / Data Flow

### Runtime Turn Lifecycle (one voice-loop iteration)

```
run() top-of-loop
  trace.next_turn()                      # allocates process-global counter, sets thread-local turn id
  trace.set_phase("loop")
  trace.tlog(..., "loop:iteration_start", state, pending_capture, follow_up_until)

  [wake / follow-up / capture path]
  trace.tlog(..., "loop:capture_path" / "loop:follow_up_listen" / "loop:waiting_for_wake_word")
  trace.tlog(..., "loop:wake_word_fired" / "loop:follow_up_utterance_captured")
  trace.tlog(..., "loop:empty_capture")  # if no audio, continue

  trace.set_phase("stt")
  trace.tlog(..., "stt:foreground_start", audio_samples)
  stt.transcribe(speech)
  trace.tlog(..., "stt:foreground_end", chars, elapsed_ms, text[:160])
  -- OR --
  trace.tlog(..., "stt:speculative_hit", chars, text[:160])
  trace.tlog(..., "stt:empty_transcript")  # if blank, continue

  [wake-word-only guard]
  trace.tlog(..., "routing:wake_word_only", text[:160])

  trace.set_phase("addressing")
  -- if follow-up window --
    trace.tlog(..., "addressing:wake_or_relay_override", text[:160])
    -- OR --
    addressing.classify(user_text, seconds_since_response)
    trace.tlog(..., "addressing:verdict", decision, source, conf, reason, seconds_since_response, text[:160])
    trace.tlog(..., "addressing:rejected_follow_up")  # if not addressed, continue
  -- else (wake path) --
    trace.tlog(..., "addressing:wake_word_path_no_classify", text[:160])

  [dialogue history record]

  [pre-routing normalization]
  normalize_command(user_text)
  trace.tlog(..., "routing:normalized", raw[:200], normalized[:200], changed)

  trace.set_phase("intent")
  _maybe_dispatch_intent(user_text)  → if handled:
    trace.tlog(..., "intent:dispatched")
    trace.tlog(..., "loop:iteration_end", via="intent")
    continue

  trace.set_phase("evolution")
  _maybe_handle_evolution_command(user_text) → if handled:
    trace.tlog(..., "loop:iteration_end", via="evolution_command")
    continue

  [if coding_voice present]
  trace.set_phase("routing")
  classify_routing(user_text)
  trace.tlog(..., "routing:classified", kind, conf, source, reason, has_active_task, has_pending_clarification)

  [relay / stop_button / settings_gui / spotify / etc. handlers — each with]
  trace.tlog(..., "loop:iteration_end", via="relay_speech"/"spotify"/"stop_button"/...)
  continue  [if consumed]

  trace.tlog(..., "routing:capability_response", kind, chars, preview[:160])
  trace.tlog(..., "routing:fallthrough_to_llm", kind)

  [semantic router]
  _cr.route(user_text)
  trace.tlog(..., "router:decision", family, abstained, conf, margin, reason)
  -- identity pool answer --
    _trace_turn_flow(raw, route="identity:<cat>", ..., channel="desktop")
  trace.tlog(..., "loop:iteration_end", via="semantic_router")
  continue [if consumed]

  trace.set_phase("respond")
  _respond(user_text, routing_intent_kind=...)
    [LLM inference.py:2043]
    logger.info("LLM messages ...") + per-message 200-char previews at INFO
    logger.info("LLM TTFT: %.0fms")
    [after stream completes]
    _trace_turn_flow(raw, route="conversational_llm", reason, subtype, final, channel="desktop")
    observe_llm_call(...)
  trace.tlog(..., "loop:iteration_end", via="respond")
```

### `_trace_turn_flow` Internal Flow

```
orchestrator._trace_turn_flow(raw, route, reason, final, channel, normalized, payload, addressee, directive, subtype, **extra)
  Gate: is_testing_mode_active()  → return immediately if False
  trace.tlog(logger, "turn:flow", route, channel, raw[:120], norm[:120], final[:160], reason)
  json.dumps({
    "ts": float,        # unix timestamp (3 decimal places)
    "raw": str,         # raw STT output (uncapped)
    "normalized": str,  # post-normalize_command text (or None)
    "route": str,       # e.g. "relay", "snap", "conversational_llm", "identity:model"
    "reason": str,      # human-readable routing rationale
    "subtype": str,     # intent subtype or relay sub-category
    "payload": str,     # relay payload (what is relayed)
    "addressee": str,   # relay addressee agent name
    "directive": str,   # relay directive (greet/praise/etc.)
    "channel": str,     # "team_mic" or "desktop"
    "final": str,       # actual spoken line (relay line or LLM response)
    **extra             # optional: forced (bool), seconds (float) for relay path
  })
  → logs/usage_trace.jsonl (append, fail-open)
```

Call sites for `_trace_turn_flow`:
- `orchestrator.py:3658` — relay path (after `play_to_device`), channel="team_mic", includes `forced` + `seconds`
- `orchestrator.py:6841` — identity-pool answer (semantic router identity branch), channel="desktop"
- `orchestrator.py:8842` — conversational LLM path (at end of `_respond`), channel="desktop"

### `kenning.trace` Thread-Local State

```
_state = threading.local()           # per-thread storage
_turn_counter: int                   # process-global, protected by _turn_counter_lock

next_turn() → increments counter, calls set_turn(N), returns N
set_phase(name) → _state.phase = name
snapshot() → {"turn": get_turn(), "phase": get_phase()}
restore(state) → set_turn + set_phase from dict

fmt(msg, **kwargs) → "turn=N | phase=X | msg | k=v | ..."
tlog(log, msg, level=INFO, **kwargs) → if log.isEnabledFor(level): log.log(level, fmt(...))

phase(name, log=..., level=INFO, **kwargs) contextmanager:
  → logs "<name>:start" on entry
  → yields mutable `extra` dict (body can stash fields)
  → logs "<name>:end | elapsed_ms=N | ..." on exit
  → restores prior phase (nesting supported)
```

Cross-thread propagation: `snapshot()` captures current thread's turn+phase; `restore(state)` installs on a new thread. Used for background threads (speculative STT/LLM/RAG prefetch).

### Spoken-Audio Diagnostics Flow

```
audio_diagnostics_enabled():
  if ~/.kenning/audio_diagnostics_on exists → True
  elif get_config().diagnostics.spoken_audio_logging (getattr'd) → True
  else → False

kokoro_engine.speak():3:661  → if audio_diagnostics_enabled(): logger.info("SPOKEN(speak): %r", text[:200])
kokoro_engine.speak_stream():719 → if audio_diagnostics_enabled(): logger.info("SPOKEN(stream): %r", joined[:200])
kokoro_engine._run_synth_loop():1118 → if audio_diagnostics_enabled():
  analyze_clip(final_pcm) → if not clean: raw_rep=analyze_clip(raw_pcm)
  logger.warning("SPOKEN-BLIP dsp-introduced ...") or logger.info("SPOKEN-BLIP in-raw ...")

reset_for_new_session() called at orchestrator boot (line 387) → deletes ~/.kenning/audio_diagnostics_on
```

### Observation Framework Flow

```
observations.writer.ObservationWriter._DEFAULT_PATH = "data/observations.jsonl"
  emit(Observation) → json.dumps(observation.to_dict()) → append to file (thread-safe lock)
  fail-open: IO errors logged WARN, observation dropped

Per-subsystem helpers in integrations.py:
  observe_routing_verdict(utterance, intent_kind, confidence, source, reason, latency_ms)
    → Observation(subsystem="routing", event_type="classify_routing", extra={utterance_len, confidence, source, reason})
  observe_addressing_verdict(utterance, decision, confidence, reason, seconds_since_response, source, latency_ms)
    → Observation(subsystem="addressing", event_type="classify_addressing", extra={...})
  observe_retrieval(query, lineage_ids, k, latency_ms, collection)
    → Observation(subsystem="memory", event_type="retrieve", lineage_ids=tuple, extra={query_len, k, result_count})
  observe_llm_call(event_type, user_message_len, tokens_used, latency_ms, streamed, enable_thinking)
    → Observation(subsystem="llm", event_type=..., tokens_used=N, latency_ms=N, extra={user_message_len, streamed})
  observe_llm_thinking_drift_sample(user_text, response_text, ...)
    → Observation with verbatim texts (truncated at 4000 chars each)
```

---

## Key Findings

1. **`trace.py` is orchestrator-only for phase/turn tracking.** Only `orchestrator.py`, `qdrant_store.py`, and `web_search/gating.py` use `trace.tlog`/`from kenning import trace`. All other modules (relay_speech, command_normalizer, command_router, addressing, LLM inference, TTS) log via `logger.info/debug` only — no `turn=N phase=X` prefix.

2. **`_trace_turn_flow` / `usage_trace.jsonl` is testing-mode only and has only 3 call sites.** The full-turn record (raw → norm → route → final → channel) is ONLY written in testing mode. There is no persistent per-turn record in production. The relay path (`:3658`), identity pool (`:6841`), and conversational LLM (`:8842`) are covered; no capture for `relay_toggle`, `flavor_toggle`, `spotify`, `stop_button`, `settings_gui`, `intent`, or `evolution` routes.

3. **LLM prompts are logged at INFO in `inference.py:2043` on every streaming call.** The full message list (role, content) is logged as a series of `msg[i] role=X (N chars): PREVIEW` lines. Content is truncated at 200 chars per message. This is unconditional (not gated by testing mode or diagnostics), always goes to `logs/kenning.log`. However: full prompt text (system prompt, RAG context, all history) is NOT logged verbatim anywhere — only 200-char previews.

4. **Thinking trace / chain-of-thought is never captured.** The streaming path in `inference.py` strips `<think>...</think>` blocks via `_strip_thinking_blocks()` before yielding tokens. The stripped content is discarded; it never reaches any log, usage_trace, or observation file. The only thinking-related tracing is `observe_llm_thinking_drift_sample` which records sampled (user_text, response_text) pairs for REVIEW — no actual chain-of-thought captured.

5. **`diagnostics.spoken_audio_logging` config key is a dead code path.** `KenningConfig` has no `diagnostics` field. The `getattr(get_config(), "diagnostics", None)` in `diagnostics.py:47` always returns `None`, so the config path never activates. Only the sentinel file `~/.kenning/audio_diagnostics_on` works. The `diagnostics.spoken_audio_logging: true` in the docstring refers to a config key that doesn't exist in the schema.

6. **No per-turn trace record for the snap/relay path in production.** In a live gaming session (testing_mode=False), the relay path writes nothing to `usage_trace.jsonl`. Only the `relay:spoken | device=... | seconds=... | chars=... | line=...` line in `kenning.log` (at INFO) and the `relay playback:` timing in the console mark a relay turn. These are not structured JSONL.

7. **The offline corpus tracers (`trace_corpus.py`, `trace_corpus_full.py`) are far more detailed than the runtime trace.** They capture: `stt1` (STT-correct output), `norm2` (full normalize), `router` (semantic router decision with confidence/margin), `match` (relay matcher output with payload/addressee/compose/verbatim/directive/context), `snap` (deterministic snap text), `tail` (flavor tail separately), `llm_system` + `llm_user` (assembled prompts for LLM-path cases), `final` (spoken line), `llm_path` (boolean). The runtime trace captures none of this granularity.

8. **`observations.jsonl` captures routing/addressing decisions structurally but WITHOUT utterance text.** By design: `observe_routing_verdict` stores `utterance_len` (not the text), `observe_addressing_verdict` likewise. Full text only appears in `usage_trace.jsonl` (testing mode) and `kenning.log` (always).

9. **Thread-local turn/phase state is only set on the orchestrator's main run-loop thread.** Background threads (speculative STT, synth workers, embedder probes) do NOT call `next_turn()` or `set_phase()`. The `snapshot()`/`restore()` mechanism exists but usage in the codebase is limited; not confirmed to be called in all background paths.

10. **`logs/kenning.log` is a rotating file (5MB, 3 backups).** All `trace.tlog` calls, all `logger.info/debug/warning` calls throughout the system go here. The format is `%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s`. With `turn=N phase=X | ...` prefixes from `trace.fmt()`, every pipeline stage for turn N is grep-able via `grep "turn=42" logs/kenning.log`.

---

## Flags & Config

| Flag / Config Key | Location | Default | Effect |
|-------------------|----------|---------|--------|
| `testing_mode.enabled` | `config.yaml` / `TestingModeConfig` | `false` | Enables `usage_trace.jsonl` writes and disables RAG/web-search/desktop (matches gaming-mode disabled-functionality for corpus testing). Also controlled by `set_testing_mode_active(True)` runtime API. |
| `config.logging.file` | `LoggingConfig` | `"logs/kenning.log"` | Path to the rotating log file; all `trace.tlog` output goes here |
| `config.logging.level` | `LoggingConfig` | `"INFO"` | Console handler level (file handler is always DEBUG) |
| `config.diagnostics.spoken_audio_logging` | (dead — no field in `KenningConfig`) | N/A | Intended to enable TTS spoken-audio logging from config; currently inert — use sentinel file instead |
| `~/.kenning/audio_diagnostics_on` (sentinel file) | `diagnostics.py:29` | absent (OFF after boot reset) | When present: enables `SPOKEN(speak/stream)` and `SPOKEN-BLIP` log lines in `kenning.log`. Reset at every boot by `reset_for_new_session()`. |
| `KENNING_LOG_LEVEL` env var | `utils/logging.py:41` | (uses config) | Overrides console log level |
| `KENNING_TELEMETRY` env var | `observability/private_telemetry.py` | disabled | Must be `"opt-in"` to enable `data/observability/private_metrics.jsonl` writes |
| `llm.enable_thinking_drift_sample_rate` | `LLMConfig` | (check config) | Float fraction of no-think turns that emit `thinking_drift_sample` observation with verbatim (user_text, response_text) |
| `TRACE_WITH_ROUTER` env var | `scripts/relay_test/trace_corpus_full.py:60` | `"1"` (on) | Set to `"0"` to skip semantic router call in offline corpus trace (avoids needing the embedder sidecar) |
| `RELAY_CORPUS_SEED` env var | corpus tracers | `"0"` | Seed for corpus generation |
| `RELAY_CORPUS_TARGET` env var | corpus tracers | `"25000"` | Number of cases to trace |
| `KENNING_ROUTER_WAIT_SECONDS` env var | corpus tracer | — | How long to wait for embedder sidecar on startup |

---

## Extension Points

1. **`_trace_turn_flow` JSONL record** (`orchestrator.py:3414-3420`): The `rec` dict uses `**extra` so any caller can inject arbitrary fields. Adding a new field (e.g., `prompt_tokens`, `thinking_trace`, `llm_system_prompt`) requires only adding a kwarg at the call site.

2. **`_trace_turn_flow` call sites** (`orchestrator.py:3658`, `6841`, `8842`): New route branches (e.g., snap-path, flavor-toggle, Spotify) can add `_trace_turn_flow(...)` calls identically to the three existing ones. All are fail-open (`try/except Exception: pass`).

3. **`kenning.observations.integrations`** (`observations/integrations.py`): The `observe_*` helpers follow a uniform pattern — add a new `observe_X` function that calls `Observation.create(...)` and `emit_observation()`. The schema's `extra` dict absorbs any new fields without schema changes.

4. **`kenning.trace.phase` context manager** (`trace.py:217`): Designed for nesting. Any new pipeline stage (e.g., LLM prompt construction, thinking-mode block, flavor injection) can be bracketed with `with phase("new_stage", log=logger, ...) as ctx:` to get auto-timed start/end log lines.

5. **`trace.snapshot()` / `restore()`** (`trace.py:118, 132`): Already designed for background thread propagation. New background tasks (speculative LLM prefill, async TTS pre-synthesis) can call `snap = trace.snapshot()` on the parent thread and `trace.restore(snap)` at the start of the background thread to inherit turn/phase tagging.

6. **`TestingModeConfig`** (`config.py:3813`): The testing mode is already a clean boolean. For u1.0 the testing-mode gate can be extended to also capture: LLM full system prompt + history, thinking trace tokens, per-stage latencies. The `_trace_turn_flow` method is the natural home.

7. **Offline corpus trace structure** (`trace_corpus_full.py`): The JSONL schema used there (`stt1`, `norm2`, `router`, `match`, `snap`, `tail`, `llm_system`, `llm_user`, `final`) is the gold standard for what a u1.0 runtime trace should capture. The offline scripts can serve as the schema blueprint.

8. **`data/observations.jsonl` `payload_ref` field** (`schema.py:103`): Designed for `"logs/routing_decisions.jsonl#L123"` style references to verbose detail files. This is an unused extension point — a per-turn full-prompt log file could be referenced here.

---

## Retire-Not-Remove Candidates (u1.0)

For u1.0 (LLM-centric routing, snap paths become ROUTERS not terminal handlers), the following trace behavior needs to evolve:

1. **`_trace_turn_flow` snap+relay call site** (`orchestrator.py:3658`): Currently captures `route="relay"` with snap/callout info. In u1.0, this becomes the "router-selected-snap" trace record; the LLM invocation that produces the final line needs its own capture. The `_trace_turn_flow` dict field set must expand to include `llm_prompt`, `llm_thinking_trace`, `snap_exemplars`, `template_id`.

2. **Testing-mode gate on `_trace_turn_flow`**: In u1.0, full LLM-prompt capture should arguably always be available behind a lower-friction flag (not requiring full testing-mode which also disables RAG/web/desktop). Consider a separate `tracing.full_turn_capture: bool` flag in config that only activates the JSONL + tlog writes, without the functionality-disable side effects.

3. **Deterministic snap paths (relay, identity, greet)**: These are the routes that in u1.0 become prompt-template selectors. Their trace records will need a new field `selected_template` and `exemplars_injected`. The retire-not-remove contract means the existing `route="snap"` / `route="identity:<cat>"` etc. values can be kept as-is and the new fields added additively.

4. **`_strip_thinking_blocks()` in `inference.py`**: Currently discards thinking tokens. In u1.0, `tracing.capture_thinking_trace: bool` could route the thinking block content into the `_trace_turn_flow` record before stripping. Zero runtime overhead when flag is off.

5. **`observe_llm_call` in `observations/integrations.py`**: Currently captures only `user_message_len`, `tokens_used`, `latency_ms`, `streamed`, `enable_thinking`. In u1.0, extend `extra` to include `template_id`, `snap_path_used`, `thinking_tokens_stripped` (count of chars in `<think>` block).

6. **Corpus tracer scripts**: The offline `trace_corpus_full.py` schema is the gold standard. The u1.0 runtime `_trace_turn_flow` should converge on this schema: `stt1` (STT-correct output), `norm2`, `router` (coarse semantic decision with confidence), `match` (which snap matched + slots), `template_id`, `snap_text`, `tail`, `thinking_trace`, `llm_prompt_preview` (first N chars), `final`.

---

## Gotchas

1. **`diagnostics.spoken_audio_logging` config key is silently inert.** The config schema has no `diagnostics` field. `getattr(get_config(), "diagnostics", None)` returns `None` → `getattr(None, "spoken_audio_logging", False)` returns `False`. Setting `diagnostics.spoken_audio_logging: true` in config.yaml does nothing. Only `touch ~/.kenning/audio_diagnostics_on` works.

2. **`usage_trace.jsonl` path is hardcoded as relative `Path("logs") / "usage_trace.jsonl"`** (`orchestrator.py:3421`). If the process CWD is not the repo root, the file lands in the wrong place. No env var override exists.

3. **Turn id resets each process start.** `_turn_counter` starts at 0 per-process. The JSONL `ts` field is the only durable cross-session anchor; turn ids from different sessions collide.

4. **`usage_trace.jsonl` records from relay path include BOTH raw and normalized as separate fields**, but the relay call site passes `normalized=getattr(command, "payload", None)` (the extracted payload, not `normalize_command` output). The field name `normalized` is therefore misleading on the relay path — it holds the PAYLOAD, not the STT-corrected command text.

5. **The conversational LLM call site (`orchestrator.py:8842`) passes `raw=user_text`** where `user_text` at that point may already be the NORMALIZED text (if `normalize_command` changed it). The truly raw STT output is `_raw_stt` (saved at `:6128`), but this variable is out of scope in `_respond()`. So `raw` in the conversational LLM trace record may be post-normalized, not actual-raw.

6. **Background thread turn propagation is not wired in most places.** `trace.snapshot()`/`restore()` exist but the speculative STT thread, synth worker threads in `kokoro_engine.py`, and web-search background threads do NOT call `restore(snap)`. Their log lines therefore carry `turn=None phase=None` prefixes, breaking the per-turn grep story.

7. **The semantic router `trace.tlog("router:decision", ...)` call** (`orchestrator.py:6789`) records the router's verdict but NOT the per-candidate scores or embedding distances. The `RouteDecision` object likely carries more detail than is logged.

8. **`observations/integrations.py:observe_routing_verdict`** is not actually called from the orchestrator's routing classifier path — the `routing:classified` trace.tlog covers it but no observation is emitted for capability routing decisions. The observation helpers may be wired in places other than the main loop.

9. **`logs/usage_trace.jsonl` is NOT created at boot.** It's created on first write in testing mode. If testing mode is enabled mid-session (runtime flag), writes start from that point. There's no session header record.

10. **`kenning.trace.phase` context manager** exists but is NOT used in the main turn loop. All phase transitions are done with bare `trace.set_phase()` calls + manual `trace.tlog(... "stt:start/end", ...)`. The context manager would auto-generate start/end + elapsed_ms but requires callers to switch to the CM form.

---

## Open Questions

1. **Is `observe_routing_verdict` wired anywhere in production code?** The helper exists in `integrations.py` but a Grep didn't find it called from the main orchestrator turn loop or from `openclaw_routing.classify_routing`. It may only be wired in tests or an older code path.

2. **What does `relay_route_info(command)` return?** Called at `orchestrator.py:3657` to populate `route` and `reason` for the `_trace_turn_flow` record. The function lives in `relay_speech.py` — its full return shape needs confirming (the trace record may have more fields than are used).

3. **Does `trace.copy_to_thread` (mentioned in trace.py docstring) exist as an exported function?** The module docstring mentions `copy_to_thread` but `__all__` exports `snapshot`/`restore` instead. The docstring appears to be a drafting artifact — `snapshot`/`restore` IS the mechanism. Verify no caller uses the old name.

4. **Are LLM prompt previews in `inference.py:2043` always at INFO level?** If `config.logging.level` is set higher than DEBUG but the file handler is at DEBUG, these 200-char previews still go to `kenning.log`. They go to the console only if level <= INFO. Since level default is INFO this means prompt shapes are console-visible by default — could be surprising in a live gaming session.

5. **Is the `observations/integrations.py` `observe_addressing_verdict` actually called?** The addressing classifier produces a verdict but the addressing phase `trace.tlog(..., "addressing:verdict", ...)` call does not appear to also call `observe_addressing_verdict`. The observation may be redundant-but-wired, or it may be an unused stub.

6. **What is the `data/observations.jsonl` `enabled` flag wired to?** `ObservationWriter` accepts `enabled: bool = True`. Where is the singleton instantiated and what configuration enables/disables it? `get_observation_writer()` returns the singleton — is it always enabled?

7. **`thinking_mode_enabled()` (from `relay_speech.py`) controls whether the relay rephrase path calls the LLM.** When thinking mode is ON, does the relay path also produce a `thinking_trace`? Is that trace logged anywhere?

8. **For u1.0 "full LLM prompt + thinking trace" per-stage capture:** what is the right granularity gating? Options: (a) always-on per-stage JSONL (high disk usage), (b) testing-mode-gated (current pattern, but disables RAG/web), (c) new `tracing.capture_llm_prompts: bool` flag (preferred). No decision recorded in codebase yet.

9. **`_relay_intent.py`** is the semantic intent gate for relay commands. Does it emit any trace records? Not confirmed in this pass.

10. **What happens to `usage_trace.jsonl` records when `_trace_turn_flow` is called from both the relay path AND the conversational LLM path in the same turn?** In theory only one fires per turn (relay returns True, aborting the LLM path). But if the semantic router forces relay AND the relay fails, both could potentially be called. The fail-open contract means duplicate records won't crash, but the semantics are unclear.
