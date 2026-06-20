# Board A — Config Schema, Feature Flags & Runtime Overrides

**Area:** A9 — Config schema, feature flags & runtime overrides
**Recon date:** 2026-06-20
**Branch:** `claude/infallible-kepler-0a865d`
**Files audited:**
- `src/kenning/config.py` (4513 lines — primary schema, load chain, singleton)
- `config.yaml` (2058 lines — live runtime values)
- `.env.example` (46 lines — env var surface documentation)
- `src/kenning/diagnostics.py` (72 lines — sentinel-file pattern)
- `config/settings.py` (363 lines — legacy shim, env-var override surface)

---

## 1. Config Load Chain

```
boot
  1. env KENNING_CONFIG_PATH   or   DEFAULT_CONFIG_PATH (project root / config.yaml)
  2. yaml.safe_load(path)
  3. _substitute_env_vars(raw)        — replaces ${VAR_NAME} in YAML string values
  4. if KENNING_LLM_PRESET env set: raw["llm"]["preset"] = value
       unless KENNING_LLM_PRESET_KEEP_OVERRIDES=1
  5. if apply_overrides=True:
       _merge_runtime_overrides(raw)  — GUI overlay from data/runtime_overrides.json
  6. KenningConfig.model_validate(raw) — Pydantic v2, extra="forbid" everywhere
```

`load_config()` is called at module import of `config/settings.py` (which fires on `from config import settings`), populating the `_CONFIG_INSTANCE` global. All subsequent `get_config()` calls return the cached instance with zero overhead.

`reload_config()` sets `_CONFIG_INSTANCE = None` then calls `load_config(apply_overrides=True)` — the only path that ever applies the GUI overlay. Fresh boot (`load_config()` without `apply_overrides`) ignores the overlay file.

---

## 2. Pydantic Schema Structure

All config classes inherit `_Strict`, which sets `ConfigDict(extra="forbid")`. Unknown YAML keys produce a hard validation error at boot — no silent ignoring.

### Top-level aggregator: `KenningConfig`

| field | type | YAML key |
|---|---|---|
| audio | AudioConfig | `audio` |
| vad | VADConfig | `vad` |
| smart_turn | SmartTurnConfig | `smart_turn` |
| wake_word | WakeWordConfig | `wake_word` |
| stt | STTConfig | `stt` |
| llm | LLMConfig | `llm` |
| tts | TTSConfig | `tts` |
| gaming_mode | GamingModeConfig | `gaming_mode` |
| addressing | AddressingConfig | `addressing` |
| relay_speech | RelaySpeechConfig | `relay_speech` |
| testing_mode | TestingModeConfig | `testing_mode` |
| semantic_router | SemanticRouterConfig | `semantic_router` |
| evolution | EvolutionConfig | `evolution` |
| safety | SafetyConfig | `safety` |
| skills | SkillsConfig | `skills` |
| events | EventsConfig | `events` |
| memory | MemoryConfig | `memory` |
| qdrant | QdrantConfig | `qdrant` |
| web_search | WebSearchConfig | `web_search` |
| coding | CodingConfig | `coding` |
| logging | LoggingConfig | `logging` |
| intent | IntentConfig | `intent` |
| push_to_talk | PttConfig | `push_to_talk` |
| spotify | SpotifyConfig | `spotify` |
| stop_button | StopButtonConfig | `stop_button` |
| desktop | DesktopConfig | `desktop` |
| diagnostics | DiagnosticsConfig? | `diagnostics` |

Note: `diagnostics` is accessed via `getattr(get_config(), "diagnostics", None)` with a fail-safe None — it may be a schema section not present in all builds, or added after the primary config.py audit window.

---

## 3. Key Subsection Defaults vs. config.yaml Live Values

### Audio (`audio`)

| field | schema default | config.yaml |
|---|---|---|
| sample_rate | 16000 | 16000 |
| channels | 1 | 1 |
| blocksize | 512 | 512 |
| dtype | "int16" | "int16" |
| input_device | None | (device name) |
| output_device | None | (device name) |
| broadcast_device | None | None |
| barge_in_enabled | True | true |
| stop_command_enabled | True | true |
| barge_in_grace_seconds | 0.5 | 0.5 |
| ring_buffer_seconds | 3.0 | 3.0 |

### VAD (`vad`)

| field | schema default | config.yaml |
|---|---|---|
| threshold | 0.5 | 0.5 |
| min_speech_duration_ms | 250 | 250 |
| min_silence_duration_ms | 500 | 500 |
| window_samples | 512 | 512 |

### Wake Word (`wake_word`)

| field | schema default | config.yaml |
|---|---|---|
| name | "ultron" | "ultron" |
| model_path | models/... | models/... |
| fallback_model | None | None |
| threshold | 0.5 | 0.5 |
| cooldown_seconds | 1.0 | 1.0 |

### STT (`stt`)

| field | schema default | config.yaml |
|---|---|---|
| engine | "whisper" | "whisper" |
| model | "large-v3" | "large-v3" |
| device | "cpu" | "cpu" |
| compute_type | "int8" | "int8" |
| beam_size | 5 | 5 |
| temperature | 0.0 | 0.0 |
| condition_on_previous_text | False | false |
| vad_filter | True | true |

### LLM (`llm`)

| field | schema default | config.yaml |
|---|---|---|
| preset | None | "qwen3.5-4b" |
| model_path | (filled by preset) | (preset fills) |
| n_ctx | (filled by preset) | 8192 |
| draft_model_path | (filled by preset) | ... |
| gpu_layers | 0 | 0 |
| default_max_tokens | 512 | 512 |
| system_prompt | (Ultron persona) | (Ultron persona) |
| idle_vram_reclaim | ... | ... |

**LLM Presets** (via `LLM_PRESETS` dict + `_apply_preset` model_validator):

| preset name | model | n_ctx | has draft |
|---|---|---|---|
| `qwen3.5-9b` | Qwen3.5-9B-Q4_K_M | 8192 | No |
| `qwen3.5-4b` | Qwen3.5-4B-Q4_K_M | 8192 | Yes (0.8B) |
| `josiefied-qwen3-4b` | abliterated 4B | 8192 | Yes |
| `llama-3.2-3b-abliterated` | Llama 3.2 3B | 6144 | No (gpu_layers=0) |

Explicit YAML values always win over preset fills. `KENNING_LLM_PRESET` env var overrides the YAML preset key entirely (unless `KENNING_LLM_PRESET_KEEP_OVERRIDES=1` is set, which preserves explicit per-field overrides on top of the new preset).

### TTS (`tts`)

| field | schema default | config.yaml |
|---|---|---|
| engine | "kokoro" | "kokoro" |
| output_sample_rate | 24000 | 24000 |
| pause_ms | 350 | 350 |
| edge_fade_ms | 8 | 8 |
| piper_length_scale | 0.92 | 0.92 |
| rvc.enabled | False | false |

### Gaming Mode (`gaming_mode`)

| field | schema default | config.yaml |
|---|---|---|
| engage_at_startup | True | true |
| anticheat_safe_mode | True | true |

**Lean-boot barebones flags** (all schema default `True`, all config.yaml `true`):

| flag | effect |
|---|---|
| `barebones_skip_retrieval` | Skip RAG/Qdrant warm-up |
| `barebones_skip_web_search` | Skip brave/jina web-search init |
| `barebones_skip_coding` | Skip coding orchestrator init |
| `barebones_skip_openclaw` | Skip OpenClaw bridge |
| `barebones_skip_docker_autostart` | Skip Docker auto-start |
| `barebones_skip_evolution` | Skip Evolution subsystem |
| `barebones_skip_events` | Skip Events subsystem |
| `barebones_skip_skills` | Skip Skills subsystem |
| `barebones_skip_summarizer` | Skip background summarizer |
| `barebones_skip_memory` | Skip memory/Qdrant loading |
| `barebones_skip_intent` | Skip intent classifier loading |
| `barebones_skip_ack_prewarm` | Skip ACK pre-warm |
| `barebones_skip_reranker_warmup` | Skip reranker warm-up |
| `barebones_direct_gaming_llm` | Direct LLM path, bypass full pipeline |
| `barebones_lazy_zero_shot_addressee` | Defer flan-t5 addressee load |

These flags suppress entire subsystem imports at startup. Toggling any from `True` to `False` restores that subsystem. In gaming mode, all 15 are on — the full desktop assistant is effectively dormant.

### Addressing (`addressing`)

| field | schema default | config.yaml |
|---|---|---|
| follow_up_enabled | True | **false** |
| warm_mode_duration_seconds | 30.0 | 120.0 |
| default_uncertain_to_not_addressed | True | true |
| rule_confidence_threshold | 0.8 | 0.8 |
| zero_shot_addressed_min_confidence | 0.80 | 0.80 |
| zero_shot_model | "google/flan-t5-small" | "google/flan-t5-small" |
| load_eagerly | True | true |
| log_path | "logs/addressing.jsonl" | "logs/addressing.jsonl" |

`follow_up_enabled=false` in config.yaml means wake word is ALWAYS required — the warm-window follow-up is disabled. This was set after a live session showed 114 un-waked captures per session with the window enabled. The addressing fusion logic (`classifier.py`, log-odds + sigmoid, cost-asymmetric tau) exists behind this flag for future use.

`_addr_cfg` is captured once at `run()` entry (not re-fetched per turn), so a `reload_config()` mid-session requires a restart to take effect for the addressing path.

### Relay Speech (`relay_speech`)

| field | schema default | config.yaml |
|---|---|---|
| enabled | True | true |
| rephrase | True | true |
| follow_up_seconds | 120.0 | 120.0 |

SNAP_REGISTRY (via `KENNING_SNAP_REGISTRY` env, default `"1"` = ON): data-driven snap dispatch via `SnapRule` entries in `audio/voice_lines.py`. Turning off falls back to hardcoded snap functions.

KENNING_FLAVOR_TAILS (default `"1"` = ON at normal boot; `__main__.py` sets default `"0"` for diagnostics/non-stream): flavor tails appended after relay lines.

KENNING_THINKING_MODE (default `"0"` = OFF): compose commands snap deterministically when flavor is ON.

### Testing Mode (`testing_mode`)

| field | schema default | config.yaml |
|---|---|---|
| enabled | False | false |
| full_flow_logging | False | false |

When `testing_mode.enabled: true` (set locally, never committed), `logs/usage_trace.jsonl` gets full per-turn routing logs. Config.yaml repo default is `false`.

### Semantic Router (`semantic_router`)

| field | schema default | config.yaml |
|---|---|---|
| enabled | True | true |
| backend | "hybrid" | "hybrid" |

### Push-to-talk (`push_to_talk`)

| field | schema default | config.yaml |
|---|---|---|
| enabled | False | false |
| serial_port | None | None |
| backend | "rawhid" | "rawhid" |
| release_jitter_ms | 60 | 60 |

PTT is armed via `.env KENNING_PTT_ENABLED=true` (not config.yaml) for anticheat reasons. The `_ptt_runtime_enabled` flag in the orchestrator can be toggled at runtime via the stop-button GUI without restart.

---

## 4. Runtime Override System

### data/runtime_overrides.json (GUI overlay)

- Written by the settings GUI as `{"dotted.path": "rendered_value"}` (e.g., `{"audio.mute_speakers": "true"}`)
- Applied ONLY when `reload_config(apply_overrides=True)` is called (the normal mid-session voice command path)
- NEVER applied on fresh boot (`clear_runtime_overrides()` wipes the file at orchestrator startup)
- `_merge_runtime_overrides(raw)` merges in-place before `model_validate`
- This means GUI changes survive only until the next boot, which clears them

### config/settings.py shim (legacy env-var surface)

A 363-line bridge that re-exports every legacy `settings.X` constant from `config.yaml`. It also resolves env-var overrides at import time via `_env_bool`/`_env_int`/`_env_float`. As subsystems migrate to `get_config()` direct access, their constants disappear from this shim. Currently still used by orchestrator, ptt controller, memory, coding.

### Audio diagnostics sentinel (`src/kenning/diagnostics.py`)

- `_SENTINEL = Path.home() / ".kenning" / "audio_diagnostics_on"` — touch to enable diagnostics without restart
- `reset_for_new_session()` clears the sentinel at boot (called from orchestrator) — diagnostics are always OFF at boot
- `audio_diagnostics_enabled()`: returns `sentinel.exists() OR config.diagnostics.spoken_audio_logging`
- Checked per-utterance (utterances are infrequent; stat cost negligible)
- Fail-safe: any exception returns `False`

---

## 5. KENNING_* Environment Variable Surface

### From `_ENV_OVERRIDE_NOTES` in config.py (logged at boot)

| env var | overrides |
|---|---|
| `KENNING_LLM_PRESET` | `llm.preset` (replaces preset, clears per-field overrides unless KEEP_OVERRIDES=1) |
| `KENNING_LLM_MODEL_PATH` | `llm.model_path` — WARNING: silently overrides the preset's auto-fill |
| `KENNING_AUDIO_DEVICE` | `audio.input_device` |
| `KENNING_AUDIO_OUTPUT_DEVICE` | `audio.output_device` |
| `KENNING_AUDIO_BROADCAST_DEVICE` | `audio.broadcast_device` |
| `KENNING_LOG_LEVEL` | `logging.level` |
| `KENNING_CONFIG_PATH` | config file path |
| `KENNING_BRAVE_API_KEY` | `web_search.brave` API key (value not logged) |
| `KENNING_CLAUDE_CLI` | `coding.claude_cli` |
| `KENNING_WHISPER_BEAM_SIZE` | `stt.beam_size` |
| `KENNING_WAKE_WORD_THRESHOLD` | `wake_word.threshold` |
| `KENNING_VAD_MIN_SILENCE_MS` | `vad.min_silence_duration_ms` |
| `KENNING_OPENCLAW_CLI` | `openclaw.bridge.cli_path` |
| `KENNING_OPENCLAW_WORKSPACE` | `openclaw.bridge.workspace_dir` |
| `KENNING_CODING_MCP_ALLOW_ANY_ROOT` | coding MCP sandbox escape (test-only; NEVER in production) |

### From `config/settings.py` shim (additional resolved at import)

| env var | overrides |
|---|---|
| `KENNING_BARGE_IN_ENABLED` | `audio.barge_in_enabled` |
| `KENNING_STOP_COMMAND_ENABLED` | `audio.stop_command_enabled` |
| `KENNING_BARGE_IN_GRACE_SECONDS` | `audio.barge_in_grace_seconds` |
| `KENNING_PTT_ENABLED` | `push_to_talk.enabled` |
| `KENNING_PTT_SERIAL_PORT` | `push_to_talk.serial_port` |
| `KENNING_WAKE_WORD_COOLDOWN_SECONDS` | `wake_word.cooldown_seconds` |
| `KENNING_WHISPER_TEMPERATURE` | `stt.temperature` |
| `KENNING_WHISPER_CONDITION_ON_PREVIOUS_TEXT` | `stt.condition_on_previous_text` |
| `KENNING_TTS_LENGTH_SCALE` | `tts.piper_length_scale` |
| `KENNING_TTS_PAUSE_MS` | `tts.pause_ms` |
| `KENNING_TTS_EDGE_FADE_MS` | `tts.edge_fade_ms` |
| `KENNING_RVC_PITCH_SHIFT` | `tts.rvc.pitch_shift` |
| `KENNING_RVC_INDEX_RATE` | `tts.rvc.index_rate` |
| `KENNING_RVC_PROTECT` | `tts.rvc.protect` |
| `KENNING_RVC_RMS_MIX_RATE` | `tts.rvc.rms_mix_rate` |
| `KENNING_RVC_FILTER_RADIUS` | `tts.rvc.filter_radius` |
| `KENNING_MEMORY_ENABLED` | `memory.enabled` |
| `KENNING_MEMORY_FACTS_TOP_K` | `memory.facts_top_k` |
| `KENNING_CODING_ENABLED` | `coding.enabled` |
| `KENNING_CODING_BRIDGE` | `coding.bridge` |
| `KENNING_CODING_MCP_ENABLED` | `coding.mcp.enabled` |
| `KENNING_CODING_MCP_HOST` | `coding.mcp.host` |
| `KENNING_CODING_MCP_PORT` | `coding.mcp.port` |
| `KENNING_CODING_MCP_CLARIFICATION_TIMEOUT_S` | `coding.mcp.clarification_timeout_seconds` |
| `KENNING_CODING_DEFAULT_MODEL` | `coding.default_model` |
| `KENNING_CODING_ESCALATION_MODEL` | `coding.escalation_model` |
| `KENNING_CODING_ESCALATION_THRESHOLD_DEFAULT` | `coding.escalation_threshold_default` |
| `KENNING_CODING_ESCALATION_THRESHOLD_ESCALATION` | `coding.escalation_threshold_escalation` |
| `KENNING_CODING_PROMPT_TOKEN_BUDGET` | `coding.prompt_token_budget` |
| `KENNING_CODING_TASK_TIMEOUT_S` | `coding.task_timeout_seconds` |
| `KENNING_CODING_SKIP_PERMISSIONS` | `coding.skip_permissions` |
| `KENNING_CODING_PRE_TASK_CONFIRMATION_ENABLED` | `coding.pre_task_confirmation_enabled` |
| `KENNING_CODING_PRE_TASK_MAX_WORDS` | `coding.pre_task_confirmation_max_words` |
| `KENNING_CODING_PRE_TASK_BARGE_IN_WINDOW_S` | `coding.pre_task_barge_in_window_seconds` |
| `KENNING_CLAUDE_CLI` | `coding.claude_cli` |
| `KENNING_CLAUDE_MODEL` | `coding.claude_model` |

### Runtime-only env flags (not in config.yaml schema; checked inline)

| env var | default | where consumed |
|---|---|---|
| `KENNING_FLAVOR_TAILS` | "1" (ON) | `relay_speech.py` + `__main__.py` sets "0" for non-stream boot |
| `KENNING_THINKING_MODE` | "0" (OFF) | `relay_speech.py` — compose snap determinism |
| `KENNING_SNAP_REGISTRY` | "1" (ON) | `relay_speech.py`, `voice_lines.py` — data-driven snap dispatch |
| `KENNING_WAKE_TRIM_TO_SPEECH` | "1" (ON) | `orchestrator.py` — audio-domain wake-word trim |
| `KENNING_WAKE_TRIM_GUARD_MS` | 200 | `orchestrator.py` |
| `KENNING_ROUTER_WAIT_SECONDS` | (normal) | `command_router.py` — fast-fail in CI |
| `KENNING_ENABLE_TAIL_SELECTOR` | (unset=OFF) | `_tail_selector.py` — semantic tail re-ranker |
| `KENNING_RELAY_TEAM_DSP` | "1" (ON) | `relay_speech.py` — team audio DSP pipeline |
| `KENNING_RELAY_HIGHPASS_HZ` | 100.0 | `relay_speech.py` |
| `KENNING_RELAY_LOWPASS_HZ` | 0.0 (OFF) | `relay_speech.py` |
| `KENNING_RELAY_TARGET_DBFS` | -20.0 | `relay_speech.py` |
| `KENNING_RELAY_NOISE_DBFS` | -58.0 | `relay_speech.py` |
| `KENNING_RELAY_CEILING_DBFS` | -1.0 | `relay_speech.py` |
| `KENNING_RELAY_COMMS_FILTER` | "1" (ON) | `relay_speech.py` |
| `KENNING_RELAY_NORMALIZE` | "1" (ON) | `relay_speech.py` |
| `KENNING_RELAY_COMFORT_NOISE` | "1" (ON) | `relay_speech.py` |
| `KENNING_RELAY_SOFTCLIP` | "1" (ON) | `relay_speech.py` |
| `KENNING_RELAY_VM_LEVEL_GUARD` | "0" (OFF) | `voicemeeter_level.py` |
| `KENNING_RELAY_VM_RESTORE` | "0" (OFF) | `voicemeeter_level.py` |
| `KENNING_RELAY_VM_B1_INDEX` | 5 | `voicemeeter_level.py` |
| `KENNING_RELAY_VM_B2_INDEX` | 6 | `voicemeeter_level.py` |
| `KENNING_RELAY_VM_DELTA_DB` | 6.0 | `voicemeeter_level.py` |
| `KENNING_VOICEMEETER_DLL` | (default path) | `voicemeeter_level.py` |
| `KENNING_SNAP_EARLY_ENDPOINT` | (unset=OFF) | `relay_speech.py` |
| `KENNING_LLM_PRESET_KEEP_OVERRIDES` | (unset) | `config.py` — preserve per-field overrides when changing preset |
| `KENNING_MCP_TOKEN` | (generated) | `identity/short_lived_token.py` |
| `KENNING_TESSERACT_CMD` | (default path) | `desktop/ocr.py` |
| `KENNING_PROJECT_ROOT` | "." | `streaming/window.py` |
| `KENNING_REGISTRY` | (default) | `install/discovery.py` — skill registry |

### Anticheat reason-code env vars (internal sentinel names; never set by users)

`KENNING_VOICE_BASELINE_TOUCH`, `KENNING_PERSONA_DRIFT`, `KENNING_AUDIT_LOG_TAMPER`, `KENNING_VALIDATOR_CONFIG_TAMPER`, `KENNING_INTERACTIVE_TOOL`, `KENNING_CAP_BYPASS_ATTEMPT`, `KENNING_K_CATEGORY_SELF_MODIFY`, `KENNING_KNOWN_BLOCKED_PATTERN` — used only within `install/reason_codes.py` as symbolic names for anticheat finding codes; not user-settable.

---

## 6. Singleton + Reload Pattern

```python
# src/kenning/config.py

_CONFIG_INSTANCE: Optional[KenningConfig] = None

def get_config() -> KenningConfig:
    global _CONFIG_INSTANCE
    if _CONFIG_INSTANCE is None:
        load_config()
    return _CONFIG_INSTANCE

def reload_config(path=None) -> KenningConfig:
    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = None
    return load_config(path, apply_overrides=True)
```

`reload_config()` is the ONLY path that ever applies the GUI overlay. Most orchestrator subsystems call `get_config()` at call-time (not stored at init), so a reload takes effect on the next call into that subsystem. Exception: `_addr_cfg` is captured once at `run()` entry — addressing changes require a restart.

Attribute writes on the live config object (e.g., `get_config().audio.broadcast_device = device`) propagate immediately because the singleton is mutable in Python. This is used for runtime device switches.

---

## 7. Preset Validator Pattern

```python
class LLMConfig(_Strict):
    preset: Optional[str] = None
    model_path: Optional[str] = None  # filled by preset if unset
    n_ctx: int = 4096                 # filled by preset if unset
    ...

    @model_validator(mode="after")
    def _apply_preset(self) -> "LLMConfig":
        if not self.preset:
            return self
        data = LLM_PRESETS.get(self.preset)
        if not data:
            raise ValueError(f"Unknown LLM preset '{self.preset}'")
        for key, val in data.items():
            if getattr(self, key) is None or getattr(self, key) == <schema_default>:
                setattr(self, key, val)
        return self
```

Explicit YAML field values always win over preset fills — the validator only sets fields that are at their schema default/None state.

---

## 8. Key Flags for U1.0 Pivot

### Flags enabling always-listening / LLM-centric mode

| flag | current value | U1.0 intent |
|---|---|---|
| `addressing.follow_up_enabled` | false (config.yaml) | Would need `true` for always-listening — but the live session showed it caused 114 false-positives/session; the fusion classifier is behind this flag |
| `wake_word.*` | wake required | U1.0 would move toward lower threshold or shorter wake requirement |
| `gaming_mode.barebones_lazy_zero_shot_addressee` | true | Defers flan-t5 load — could keep for U1.0 if addressing is redesigned |
| `testing_mode.enabled` | false (repo) / true (local) | Must stay false in repo |

### Flags for flavor verbosity

| flag | current value | U1.0 intent |
|---|---|---|
| `KENNING_FLAVOR_TAILS` | "1" (ON) | Voice toggle already wired (`match_flavor_toggle`); U1.0 should expose via config.yaml field too |
| `KENNING_THINKING_MODE` | "0" (OFF) | Can be exposed as config field |
| `KENNING_SNAP_REGISTRY` | "1" (ON) | New snap entries via SnapRule — zero code change |

### Flags for agent-specific libraries

| flag | current value | U1.0 intent |
|---|---|---|
| `relay_speech.rephrase` | true | LLM rephrase is already wired; agent-specific libraries would be new routing |
| `barebones_*` | all true | New agent-library subsystem would need a new barebones_skip_agent_libs flag |

---

## 9. Retire-Not-Remove Candidates

- **`config/settings.py` shim** — the comment in the file says "Will be removed when subsystems migrate to direct `get_config()` reads". Currently 35+ source files still import from it. For U1.0, no further shim additions should be made; new subsystems should go direct to `get_config()`.
- **`KENNING_WHISPER_CONDITION_ON_PREVIOUS_TEXT`** — this env var is wired in `settings.py` but the field `condition_on_previous_text` is already `False` as schema default and false in config.yaml. If whisper domain biasing (via `WHISPER_INITIAL_PROMPT`) is replaced or fixed, the condition-on-previous-text path may never be enabled.
- **`KENNING_RELAY_COMMS_FILTER` sub-flags** — `KENNING_RELAY_HIGHPASS_HZ`, `KENNING_RELAY_LOWPASS_HZ`, etc. — these exist as fine-grained knobs for a band-shape the live session decided to move away from (LP off by default; 100Hz HP default). For U1.0, if the DSP is re-evaluated these become moot.
- **RVC block** — `RVC_ENABLED`, `RVC_MODEL_PATH`, etc. — RVC is `enabled: false` and appears to be a legacy voice-conversion stack. Kokoro+SOUL is the current path.

---

## 10. Extension Points for U1.0

1. **New `barebones_*` flag for agent-specific libraries** — add `barebones_skip_agent_libs: bool = True` to `GamingModeConfig`; boot gate honors it; no change to load chain.

2. **Flavor verbosity as a config.yaml field** — `relay_speech.flavor_enabled: bool = True` — maps to `KENNING_FLAVOR_TAILS`; allows GUI overlay to toggle it without env-var friction.

3. **Thinking mode as a config.yaml field** — `relay_speech.thinking_mode: bool = False` — maps to `KENNING_THINKING_MODE`.

4. **New LLM preset entries** — add to `LLM_PRESETS` dict with no schema change; the `_apply_preset` validator picks them up automatically.

5. **New snap rules** — add `SnapRule` entries to `SNAP_REGISTRY` in `audio/voice_lines.py` — zero code change required (data-driven via `_apply_snap_registry`).

6. **Addressing confidence redesign** — the fusion classifier (`classifier.py`, log-odds + sigmoid, cost-asymmetric `KENNING_ADDRESSING_TAU` env, default 0.20) is fully implemented behind `addressing.follow_up_enabled`. Raising tau reduces false-positives; lowering it allows more permissive follow-up.

7. **Runtime overlay extension** — any new GUI-controllable setting can write `{"new.dotted.path": "value"}` to `data/runtime_overrides.json`; `reload_config()` picks it up with no schema change if the field already exists.

---

## 11. Gotchas

- **`_addr_cfg` is captured once at `run()` entry.** Addressing config changes (especially `follow_up_enabled`) require a full restart, not just `reload_config()`.
- **`KENNING_LLM_MODEL_PATH` silently overrides the preset's auto-fill.** If set in `.env`, the preset's model_path fill is skipped, but other preset fields (n_ctx, draft_model_path) are still filled. The combination can be incoherent — the code comment in `_ENV_OVERRIDE_NOTES` calls this out explicitly.
- **config.yaml is IMMUTABLE at boot from the GUI's perspective.** The ephemeral overlay (`data/runtime_overrides.json`) is the only runtime mutation path. A GUI that writes directly to config.yaml would be ignored until the next boot.
- **`KENNING_FLAVOR_TAILS` default differs between normal boot and `__main__.py`.** `__main__.py` sets `os.environ.setdefault("KENNING_FLAVOR_TAILS", "0")` — meaning if the env var is not explicitly set, flavor tails are OFF when launched via `python -m kenning`. The relay tests that depend on flavor ON must set the env var explicitly.
- **`extra="forbid"` on all config classes.** Adding a YAML key not in the schema raises a `ValidationError` at boot — there is no silent fallthrough.
- **`clear_runtime_overrides()` is called at orchestrator startup** — every boot wipes the GUI overlay. Any setting changed via GUI mid-session is lost on restart.
- **`testing_mode.enabled: true` and `push_to_talk.enabled: true` are local-only uncommitted flips** (config.yaml local working tree). The repo default is `false` for both. Never commit these flips — they violate anticheat and binding rules.
- **The `diagnostics` config section** is accessed via `getattr(get_config(), "diagnostics", None)` with a fail-safe None in `diagnostics.py`. If the section is not defined in `KenningConfig`, `diagnostics.spoken_audio_logging` always returns `False`, and only the sentinel file path enables spoken-audio logging.
