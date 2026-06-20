# Board B — Config / Feature-Flag Wiring (End-to-End Map)

**Recon date:** 2026-06-20  
**Branch:** `claude/infallible-kepler-0a865d`  
**Scope:** config.yaml → config.py (Pydantic) → settings.py shim → orchestrator behavior; runtime_overrides overlay; lean-dispatch gating; retire-not-remove pattern; recipes for u1.0 work.

---

## 1. The Five-Stage Config Pipeline

```
  config.yaml (disk)
      │
      ▼  yaml.safe_load()
  raw dict
      │
      ▼  _substitute_env_vars()        ${VAR_NAME} → os.environ[VAR_NAME]
  raw dict (env-vars expanded)
      │
      ▼  KENNING_LLM_PRESET env check  overrides llm.preset + clears
  raw dict                              model_path/draft/n_ctx unless
      │                                 KENNING_LLM_PRESET_KEEP_OVERRIDES=1
      ▼  _merge_runtime_overrides()     ONLY when apply_overrides=True
  raw dict (+ GUI edits)               (i.e. only in reload_config(), NEVER
      │                                 at cold boot -- see §3)
      ▼  KenningConfig.model_validate()
  KenningConfig singleton              extra="forbid" → typos fail here
```

**Key constants** (`src/kenning/config.py`, lines ~58-65):

```python
PROJECT_ROOT          = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH   = PROJECT_ROOT / "config.yaml"
RUNTIME_OVERRIDES_PATH = PROJECT_ROOT / "data" / "runtime_overrides.json"
MODELS_DIR            = PROJECT_ROOT / "models"
LOGS_DIR              = PROJECT_ROOT / "logs"
```

**Path resolution order** in `load_config()` (line ~4101):
1. Explicit `path` argument
2. `KENNING_CONFIG_PATH` env var
3. `DEFAULT_CONFIG_PATH` (`<project root>/config.yaml`)

A missing file raises `ConfigurationError` — no silent defaults fallback in production.

---

## 2. Pydantic Schema Architecture

**File:** `src/kenning/config.py`

### 2.1 Base class

```python
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

Every sub-model inherits `_Strict`. An unknown YAML key causes validation failure at startup — typo detection is immediate.

### 2.2 Top-level model

```python
class KenningConfig(_Strict):
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VadConfig = Field(default_factory=VadConfig)
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)
    stt: SttConfig = Field(default_factory=SttConfig)
    tts: TtsConfig = Field(default_factory=TtsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    gaming_mode: GamingModeConfig = Field(default_factory=GamingModeConfig)
    relay_speech: RelaySpeechConfig = Field(default_factory=RelaySpeechConfig)
    semantic_router: SemanticRouterConfig = Field(default_factory=SemanticRouterConfig)
    addressing: AddressingConfig = Field(default_factory=AddressingConfig)
    push_to_talk: PushToTalkConfig = Field(default_factory=PushToTalkConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    coding: CodingConfig = Field(default_factory=CodingConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    testing_mode: TestingModeConfig = Field(default_factory=TestingModeConfig)
    # ... (intent, events, skills, mcp, notifications, deep_research, etc.)
```

### 2.3 Model validators (preset/tier expansion)

**LLM preset expansion** (line ~982, `LLMConfig._apply_preset`):
```python
@model_validator(mode="after")
def _apply_preset(self) -> "LLMConfig":
    defaults = LLM_PRESETS.get(self.preset)
    for field, value in defaults.items():
        if field not in self.model_fields_set:  # don't clobber explicit overrides
            object.__setattr__(self, field, value)
    return self
```
`LLM_PRESETS` maps preset name → `{model_path, n_ctx, draft_model_path, gpu_layers}`.  
Current entries: `"qwen3.5-9b"`, `"qwen3.5-4b"`, `"josiefied-qwen3-8b"`, `"josiefied-qwen3-4b"`, `"gemma-3-4b-abliterated"`, `"llama-3.2-3b-abliterated"` (gaming default, `gpu_layers:0`).

**CodingSupervisor tier expansion** (same pattern, `SUPERVISOR_TIERS`):
- Tiers: `"off"` / `"indexing_only"` / `"deciding"` / `"full"`  
- Each tier maps to a set of per-phase bool flags.

**Rule:** never clobber explicitly-set fields (`model_fields_set` check). This means adding a key under `[llm]` in config.yaml takes precedence over the preset table for that key only.

---

## 3. Runtime Overrides (GUI Overlay)

**File:** `data/runtime_overrides.json` (not committed; ephemeral)

**Format:** flat JSON dict with dot-path keys:
```json
{ "audio.barge_in_enabled": "true", "llm.default_max_tokens": "512" }
```

**When applied:**
- `reload_config()` calls `load_config(apply_overrides=True)` → `_merge_runtime_overrides(raw)` runs
- Cold boot: `clear_runtime_overrides()` is called FIRST by the orchestrator, deleting the file → GUI edits NEVER survive a restart

**`clear_runtime_overrides()`** (line ~4053):
```python
def clear_runtime_overrides() -> None:
    RUNTIME_OVERRIDES_PATH.unlink(missing_ok=True)
```
Called at orchestrator startup. Intentional — the lean-boot / anticheat / canary defaults MUST always apply fresh.

**`_merge_runtime_overrides(raw)`** (line ~4068):  
- Reads the JSON file, splits each key on `.`, walks the raw dict to set the leaf value  
- Values are YAML-parsed: `"true"` → `True`, `"40"` → `40`, `"cpu"` → `"cpu"`  
- Fully fail-open: malformed entries skipped entry-by-entry, never breaks boot

**GUI write path:** the settings panel writes to `RUNTIME_OVERRIDES_PATH` then calls `reload_config()`. The restart-needed note in the panel is for subsystems (e.g. LLM model path, Qdrant data dir, audio sample rate) that capture their config value once at construction time; flags that are read on every turn take effect immediately.

---

## 4. Singleton Accessor Pattern

```python
_CONFIG_INSTANCE: Optional[KenningConfig] = None

def get_config() -> KenningConfig:
    if _CONFIG_INSTANCE is None:
        load_config()
    return _CONFIG_INSTANCE

def reload_config(path=None) -> KenningConfig:
    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = None
    return load_config(path, apply_overrides=True)

def set_config(cfg: KenningConfig) -> None:  # test injection
    global _CONFIG_INSTANCE
    _CONFIG_INSTANCE = cfg
```

Read pattern in subsystems: `cfg = get_config(); val = cfg.section.field`. The `settings.py` shim does this once at module import time for backward-compat constants.

---

## 5. The `settings.py` Compatibility Shim

**File:** `config/settings.py`

A transitional bridge. Re-exports every legacy `settings.X` constant by reading from `get_config()` at import time. 35 source files used `from config import settings; settings.X`. Subsystems migrate to direct `get_config()` use over time; once migrated, names disappear from the shim.

Key behavior:
- `_cfg = get_config()` runs at module import (line 82)
- Env-var override helpers (`_env_bool`, `_env_int`, `_env_float`) preserved during migration
- **LLM block** already migrated to direct `get_config()` in `inference.py`; only `LLM_MAX_TOKENS` remains (coordinator.py temporarily overrides it via attribute write)
- **Web search block** fully migrated; no shim re-exports
- `CODING_*`, `MEMORY_*`, `AUDIO_*`, `PTT_*`, `WAKE_WORD_*`, `WHISPER_*`, `VAD_*` still present

**Note for u1.0:** new subsystems should read `get_config()` directly. Never add new entries to the shim.

---

## 6. Lean-Gaming Boot: `_skip_for_lean_gaming()` and `barebones_skip_*` Flags

### 6.1 The method

**File:** `src/kenning/pipeline/orchestrator.py`, line 1715

```python
def _skip_for_lean_gaming(self, flag: str) -> bool:
    """True when this is a LEAN GAMING-startup boot AND the named barebones
    skip flag is on -- non-essential subsystem must NOT load / import / touch RAM."""
    try:
        from kenning.config import get_config
        gm = get_config().gaming_mode
        return bool(getattr(gm, "engage_at_startup", False)
                    and getattr(gm, flag, True))
    except Exception as e:
        # Fail-SAFE: if config can't be read, SKIP the subsystem (lean posture).
        logger.warning("lean-gaming skip for %r -- fail-SAFE: SKIPPING.", flag, e)
        return True
```

**Critical design note:** gated on `gaming_mode.engage_at_startup` (CONFIG INTENT), NOT on `is_gaming_mode_active()` (which is False throughout `__init__`), NOT on `anticheat_active()` (a non-gaming anticheat dev boot still loads coding/search). Lean gaming boot is the PERMANENT default; every skip is individually toggleable.

**Fail direction changed** (2026-06-17 audit): previously failed toward keeping the subsystem; now fails toward SKIPPING (True). A config-read error at boot means lean posture is safer than importing heavy/automation-adjacent modules under a kernel anticheat.

### 6.2 Complete `barebones_skip_*` flag inventory

All in `GamingModeConfig`. All default `True` in both schema and config.yaml.

| Flag | Subsystem skipped when True |
|------|------------------------------|
| `barebones_skip_retrieval` | RAG retrieval chain (Qdrant queries) |
| `barebones_skip_web_search` | `web_gate`/`web_executor` provider+reader chains |
| `barebones_skip_coding` | `CodingVoiceController`, `ProjectIndex`, `Supervisor`, `project_introspect` bus invalidator, MCP server (port 19761 + SSE thread) |
| `barebones_skip_openclaw` | OpenClaw bridge (gateway probe + MCP-registration retry thread + voice-handoff receiver; `kenning.openclaw_bridge` not imported) |
| `barebones_skip_docker_autostart` | Docker autostart for SearXNG (web search is off anyway) |
| `barebones_skip_evolution` | Evolution service (temperament / autonomous cycle) |
| `barebones_skip_events` | Events store (bus subscription, hash chain) |
| `barebones_skip_skills` | Skills registry |
| `barebones_skip_summarizer` | Background conversation summarizer |
| `barebones_skip_memory` | Conversation memory (`Qdrant` + `bge-small`/`bm25` FastEmbed encoders) |
| `barebones_skip_intent` | Intent recognizer (`moonshine_voice.intent_recognizer`, in-process embeddinggemma-300m q4) |
| `barebones_skip_ack_prewarm` | Ack-clip prewarm (conversational filler-acks suppressed in gaming) |
| `barebones_skip_reranker_warmup` | Cross-encoder reranker warmup (RAG retrieval off; lazy-loads on demand) |
| `barebones_direct_gaming_llm` | Direct LLM construction from `gaming_mode.llm_preset` at init (bypasses normal late-load path; `gpu_layers:0` for lean memory) |
| `barebones_lazy_zero_shot_addressee` | Defers flan-t5 model load until an ambiguous follow-up actually needs it |

### 6.3 How a lean-gaming gate looks in the orchestrator

```python
# In __init__ (line ~421):
if not self._skip_for_lean_gaming("barebones_skip_coding"):
    try:
        from kenning.coding.project_introspect import install_bus_invalidator
        install_bus_invalidator()
    except Exception as e:
        logger.debug("project_introspect bus invalidator init: %s", e)

# In a builder method (line ~4522):
def _build_coding_voice_controller(self):
    if self._skip_for_lean_gaming("barebones_skip_coding"):
        logger.info("lean gaming boot: CodingVoiceController skipped")
        return None
    if not settings.CODING_ENABLED:
        return None
    # ... lazy import + construction
```

**The lazy import pattern** is the key technique: coding stack is NEVER imported at module top level, only inside gated builder methods. The comment at orchestrator.py lines 69-73 states this explicitly: "a LEAN GAMING BOOT never loads the coding stack into RAM."

### 6.4 Anticheat-safe mode posture check

`_audit_anticheat_posture()` (line ~1784) walks `sys.modules` for desktop/automation libraries and logs a WARNING if any are found loaded while anticheat is active. This is a regression canary — if any lean-gaming gate leaks, it surfaces here. Also: `_start_dialog_poller()` (line ~1745) refuses to import `kenning.desktop.dialog_poller` if `anticheat_active()` is True, keeping pyautogui/mss/pywinauto out of RAM entirely.

---

## 7. All Default-OFF Flags (Complete Inventory)

### 7.1 Schema defaults (off unless config.yaml overrides)

| Config path | Default | Effect |
|-------------|---------|--------|
| `push_to_talk.enabled` | `False` | Master PTT switch; no hardware assumed |
| `addressing.follow_up_enabled` | `False` | Wake word required for every turn (schema was True; forced False in YAML with comment; same fix as un-merged `0163ba6`) |
| `notifications.telegram.enabled` | `False` | Telegram notification pings |
| `testing_mode.enabled` | `False` | GPU testing mode; never triggers gaming device swaps |
| `memory.reranking.enabled` | `False` | Cross-encoder re-rank (17-18s latency on CPU; turned back off) |
| `memory.topical_chunking.enabled` | `False` | Topical chunking for ingestion |
| `memory.discourse_tagging.enabled` | `False` | Discourse tagging |
| `memory.background_summary.enabled` | `False` | Background conversation summarizer |
| `memory.history_compression.enabled` | `False` | Memory history compression |
| `memory.contextual_retrieval.enabled` | `False` | Contextual retrieval |
| `coding.canonical_monitor.enabled` | `False` | AST canonical monitor |
| `coding.ast_metadata.enabled` | `False` | AST metadata extraction |
| `coding.pre_write_lint.enabled` | `False` | Pre-write lint |
| `coding.goal_anchors.enabled` | `False` | Goal anchor tracking |
| `coding.ai_comment_watcher.enabled` | `False` | AI comment watcher |
| `coding.architect.enabled` | `False` | Coding architect |
| `coding.repo_map.enabled` | `False` | Repo map |
| `coding.supervisor.enabled` | `False` | Coding supervisor (tier="off") |
| `intent.enabled` | `False` | Intent recognizer subsystem |
| `events.enabled` | `False` | Events store |
| `skills.enabled` | `False` | Skills registry |
| `mcp.enabled` | `False` | MCP server |
| `llm.compression.enabled` | `False` | LLM compression (schema default; **config.yaml overrides to True**) |
| `llm.self_consistency.enabled` | `False` | Self-consistency sampling (schema default; **config.yaml overrides to True**) |
| `llm.ambiguity_band.enabled` | `False` | Ambiguity band clarification |
| `llm.routing_irma.enabled` | `False` | IRMA routing |
| `openclaw.block_and_revise.enabled` | `False` | OpenClaw block-and-revise |
| `tts.click_preview.enabled` | `False` | TTS click preview |
| `visualizer.enabled` | `False` | Visualizer |

### 7.2 Default-ON flags (safe-by-default posture)

| Config path | Default | Significance |
|-------------|---------|--------------|
| `gaming_mode.enabled` | `True` | Gaming mode on by default |
| `gaming_mode.anticheat_safe_mode` | `True` | **PINNED ON** — never auto-disabled |
| `gaming_mode.engage_at_startup` | `True` | Lean-boot guard gate |
| `gaming_mode.barebones_skip_*` | `True` | All skip flags default on |
| `relay_speech.enabled` | `True` | Team relay pipeline |
| `spotify.enabled` | `True` | Spotify control |
| `safety.enabled` | `True` | Runtime tool-call validator |
| `evolution.enabled` | `True` | Evolution (skipped in lean boot) |
| `semantic_router.enabled` | `True` | Hybrid lexical+embedding routing |
| `deep_research.enabled` | `True` | Deep research mode |
| `smart_turn.enabled` | `True` | Smart Turn V3 end-of-turn detection |
| `web_search.enabled` | `True` | Web search (skipped in lean boot) |
| `memory.enabled` | `True` | Memory (skipped in lean boot) |
| `coding.pre_edit_snapshot.enabled` | `True` | Pre-edit snapshot |
| `coding.dialog_auto_handler.enabled` | `True` | Dialog auto-handler |

### 7.3 Config.yaml overrides that contradict schema defaults

These deserve special attention because reading the schema alone would mislead:

| Path | Schema default | Config.yaml value | Reason |
|------|----------------|-------------------|--------|
| `addressing.follow_up_enabled` | `True` | `false` | Wake-free follow-up fired on room speech; user: "reject anything not initiated with wake word" |
| `llm.compression.enabled` | `False` | `true` | Intentionally ON for production quality |
| `llm.self_consistency.enabled` | `False` | `true` | Intentionally ON for production quality |

---

## 8. Environment Variable Override Surface

### 8.1 `_ENV_OVERRIDE_NOTES` (documented overrides)

Defined at config.py line ~4233 and surfaced in `log_effective_config()` at startup.

| Env var | What it overrides |
|---------|-------------------|
| `KENNING_LLM_PRESET` | `llm.preset` (also clears `model_path`/`draft`/`n_ctx` unless `KENNING_LLM_PRESET_KEEP_OVERRIDES=1`) |
| `KENNING_LLM_MODEL_PATH` | `llm.model_path` (silently overrides preset auto-fill — known root of 9B/4B mix-up) |
| `KENNING_AUDIO_DEVICE` | `audio.input_device` |
| `KENNING_AUDIO_OUTPUT_DEVICE` | `audio.output_device` |
| `KENNING_AUDIO_BROADCAST_DEVICE` | `audio.broadcast_device` |
| `KENNING_LOG_LEVEL` | `logging.level` |
| `KENNING_CONFIG_PATH` | config file path (stage 1 in path resolution) |
| `KENNING_BRAVE_API_KEY` | `web_search.brave` API key (value not logged) |
| `KENNING_CLAUDE_CLI` | `coding.claude_cli` |
| `KENNING_WHISPER_BEAM_SIZE` | `stt.beam_size` |
| `KENNING_WAKE_WORD_THRESHOLD` | `wake_word.threshold` |
| `KENNING_VAD_MIN_SILENCE_MS` | `vad.min_silence_duration_ms` |
| `KENNING_OPENCLAW_CLI` | `openclaw.bridge.cli_path` |
| `KENNING_OPENCLAW_WORKSPACE` | `openclaw.bridge.workspace_dir` |
| `KENNING_CODING_MCP_ALLOW_ANY_ROOT` | coding.mcp sandbox escape — test-only, NEVER in production |

### 8.2 Inline env vars checked in orchestrator

These are read directly in the orchestrator, outside the Pydantic config:

| Env var | Default | Effect |
|---------|---------|--------|
| `KENNING_WAKE_TRIM_TO_SPEECH` | `"1"` | Enable audio-domain wake-word trim (VAD segmentation); `"0"` disables |
| `KENNING_WAKE_TRIM_GUARD_MS` | `"200"` | Guard margin around wake-trim cut |
| `KENNING_SMART_TURN_MIN_COMPLETE_MS` | `"1000"` | Min contiguous speech ms before Smart Turn complete/medium fires |
| `KENNING_SNAP_EARLY_ENDPOINT` | `"0"` | Latency E3: skip min-speech floor for complete tactical callouts |
| `KENNING_PTT_ENABLED` | — | Overrides `push_to_talk.enabled` (read in settings.py shim) |

### 8.3 Additional env vars in settings.py shim (transitional)

`KENNING_BARGE_IN_ENABLED`, `KENNING_STOP_COMMAND_ENABLED`, `KENNING_BARGE_IN_GRACE_SECONDS`, `KENNING_PTT_SERIAL_PORT`, `KENNING_WHISPER_CONDITION_ON_PREVIOUS_TEXT`, `KENNING_MEMORY_ENABLED`, `KENNING_MEMORY_FACTS_TOP_K`, `KENNING_CODING_ENABLED`, `KENNING_CODING_BRIDGE`, `KENNING_CODING_MCP_ENABLED`, `KENNING_CODING_MCP_HOST`, `KENNING_CODING_MCP_PORT`, `KENNING_CODING_CLARIFICATION_TIMEOUT_S`, `KENNING_CODING_PROMPT_TOKEN_BUDGET`, `KENNING_CODING_PROMPT_CHARS_PER_TOKEN`, `KENNING_CODING_DEFAULT_MODEL`, `KENNING_CODING_ESCALATION_MODEL`, `KENNING_CODING_VERIFICATION_SMOKE_TIMEOUT_S`, `KENNING_CODING_VERIFICATION_TEST_TIMEOUT_S`, `KENNING_CODING_VERIFICATION_LINT_TIMEOUT_S`, `KENNING_CODING_TOKEN_BUDGET_PER_SESSION`, `KENNING_CODING_TOKEN_WARNING_THRESHOLD`, `KENNING_CODING_PROGRESS_TIMEOUT_S`, `KENNING_CODING_PRE_TASK_CONFIRMATION_ENABLED`, `KENNING_CODING_PRE_TASK_MAX_WORDS`, `KENNING_CODING_PRE_TASK_BARGE_IN_WINDOW_S`, `KENNING_CODING_ESCALATION_THRESHOLD_DEFAULT`, `KENNING_CODING_ESCALATION_THRESHOLD_ESCALATION`, `KENNING_CLAUDE_MODEL`.

---

## 9. Retire-Not-Remove Pattern

The codebase has a consistent pattern for retiring features without deleting them:

### 9.1 Default-off toggle (pure feature flag)

Add a new config key defaulting to `False`. The code path stays; the flag gates it.

**Canonical example:** `addressing.follow_up_enabled`
- Schema originally defaulted `True`
- Caused false-positives (room speech, teammate speech captured without wake)
- Set to `False` in config.yaml with comment explaining the decision
- Code (`_follow_up_listen`, the fusion classifier, `_FOLLOWUP_WAKE_RE`) remains intact and can be re-enabled via config

### 9.2 Lean-gaming skip (heavyweight subsystem retirement)

Add a `barebones_skip_X: bool = True` to `GamingModeConfig`. Gate all import points with `if not self._skip_for_lean_gaming("barebones_skip_X"):`. When the flag is True, the subsystem's module is NEVER imported into the process.

**Canonical examples:**
- `barebones_skip_coding` → `kenning.coding.*`, `kenning.coding.project_introspect`, MCP server all stay cold
- `barebones_skip_memory` → `Qdrant`, `bge-small`, `bm25` FastEmbed encoders never load
- `barebones_skip_intent` → `moonshine_voice.intent_recognizer` stays out of RAM

### 9.3 Anticheat surface hook (runtime subsystem halt)

For subsystems that may have already started but must stop when anticheat mode activates: register a surface hook via `register_surface_hook(name, callback)`. The callback stops/restarts the subsystem on mode toggle. Example: `_anticheat_dialog_poller` stops/starts the UIA DialogPoller thread.

### 9.4 Import firewall (hard block)

`install_import_firewall()` installs a `sys.meta_path` finder that raises on any import of blocked desktop/automation modules while anticheat is active. This is the backstop that catches lazy imports that escape all gating logic.

### 9.5 LLM presets (model retirement)

Remove a preset name from `LLM_PRESETS` dict. Any `config.yaml` that references it will still parse (the preset field is a free string) but `_apply_preset` will skip expansion (returns the empty-defaults path). To hard-retire: remove from dict AND add a validator that rejects the name.

### 9.6 SUPERVISOR_TIERS tier "off"

`coding.supervisor.tier = "off"` expands to all phases False. Sets `enabled = False`. This is the coding-supervisor retire pattern — the code exists, tier "off" is a no-op.

---

## 10. Recipe: Adding a u1.0 Feature Flag

### Step 1 — Define the Pydantic model

In `src/kenning/config.py`, add a new `_Strict` subclass:

```python
class UltronLlmRouterConfig(_Strict):
    enabled: bool = False
    # ... knobs
    min_confidence: float = 0.7
    timeout_ms: int = 200
```

Default `enabled: False` — safe rollout, never surprising at boot.

### Step 2 — Add the field to KenningConfig

```python
class KenningConfig(_Strict):
    # ...
    llm_router: UltronLlmRouterConfig = Field(default_factory=UltronLlmRouterConfig)
```

### Step 3 — Add the section to config.yaml

```yaml
llm_router:
  enabled: false       # OFF by default; flip true when routing is stable
  min_confidence: 0.7
  timeout_ms: 200
```

Any key not in the schema causes a startup `ConfigurationError` — typo protection is automatic.

### Step 4 — Read in the subsystem

```python
from kenning.config import get_config

cfg = get_config()
if cfg.llm_router.enabled:
    # ... use cfg.llm_router.min_confidence etc.
```

### Step 5 — Add a lean-gaming skip (if heavyweight)

If the subsystem loads models or starts threads that shouldn't run in a gaming boot:

In `GamingModeConfig`:
```python
barebones_skip_llm_router: bool = True
```

In config.yaml `gaming_mode` section:
```yaml
gaming_mode:
  barebones_skip_llm_router: true
```

In the orchestrator builder method:
```python
def _build_llm_router(self):
    if self._skip_for_lean_gaming("barebones_skip_llm_router"):
        logger.info("lean gaming boot: LLM router skipped")
        return None
    if not get_config().llm_router.enabled:
        return None
    from kenning.llm.router import LlmRouter  # lazy import
    return LlmRouter(get_config().llm_router)
```

### Step 6 — Wire the GUI (optional)

The settings panel writes to `data/runtime_overrides.json` as `{"llm_router.enabled": "true"}`. `reload_config()` picks this up without a restart IF the subsystem reads config on each turn. For subsystems that capture config at construction, they need a restart; document this.

---

## 11. Retire-Not-Remove Candidates for u1.0

The u1.0 pivot (all responses through 8B LLM; deterministic snap paths become ROUTERS; always-listening semantic matching; flavor becomes verbosity levels) creates natural retire candidates:

| Subsystem | Current flag / path | Retire action |
|-----------|---------------------|---------------|
| Deterministic snap matchers in `relay_speech.py` (`_THANK_YOU_RE`, `_SNAP_REGISTRY`, etc.) | Always active when `relay_speech.enabled` | Add `relay_speech.snap_registry_enabled: bool = True`; flip to `False` for u1.0 LLM path. Keep matchers as ROUTERS (detect intent type, pass to LLM with structured hint) |
| Flan-t5 zero-shot addressee classifier | `barebones_lazy_zero_shot_addressee`; only loaded when follow_up_enabled=True | Already gated; if follow-up is removed, the whole classifier can be skipped (`barebones_skip_zero_shot: bool`) |
| `relay_speech.py` flavor tail library | `KENNING_SNAP_REGISTRY` env; `_join_tail` gate | Add `relay_speech.flavor_tails_enabled: bool = True`; map to "verbosity level" in u1.0 |
| `relay_speech._RELAY_REPHRASE_SYSTEM` | Always active for LLM relay rephrase | Absorb into u1.0 unified system prompt; old constant becomes a retired default |
| `addressing.follow_up_enabled` | `False` in YAML | Already retired in v1; remove the fusion code only AFTER confirming u1.0 always-on addressing replaces it |
| Background summarizer | `barebones_skip_summarizer` / `memory.background_summary.enabled` | Already lean-gated; confirm u1.0 LLM context window makes it redundant before removing |
| `barebones_direct_gaming_llm` path | `GamingModeConfig.barebones_direct_gaming_llm: True` | u1.0 LLM is always direct-loaded; this flag may become the universal default and "non-direct" path retired |
| `semantic_router` two-stage (lexical + embedding) | `semantic_router.enabled` | In u1.0, LLM replaces the embedding stage; lexical stage becomes a fast first-pass ONLY. `semantic_router.embedding_enabled: bool` can gate the embedding half independently |

---

## 12. Key Gotchas

1. **Schema default vs config.yaml value can contradict.** Always check both. `addressing.follow_up_enabled` schema=True, yaml=False. `llm.compression.enabled` schema=False, yaml=True. Reading only the schema gives the wrong answer.

2. **`_skip_for_lean_gaming` gates on `engage_at_startup`, not `anticheat_active()`.** A non-gaming anticheat dev boot (anticheat pinned on but `gaming_mode.engage_at_startup: False`) does NOT skip coding/search subsystems. Both guards exist for different reasons.

3. **`reload_config()` applies overrides; `load_config()` (cold boot) does not.** The GUI's `runtime_overrides.json` is INVISIBLE at cold boot. `clear_runtime_overrides()` deletes it at orchestrator startup as defense-in-depth.

4. **`model_fields_set` in preset expansion.** If `config.yaml` explicitly sets `llm.model_path`, the preset's `model_path` will NOT overwrite it. But `KENNING_LLM_PRESET` env var CLEARS `model_path` from the raw dict before validation, so the env var WINS over an explicit yaml value (unless `KENNING_LLM_PRESET_KEEP_OVERRIDES=1`).

5. **`settings.py` is import-time snapshot.** Constants like `CODING_ENABLED` are set once at import. A `reload_config()` in-session doesn't update them. Subsystems that haven't migrated to direct `get_config()` use won't see in-session GUI changes.

6. **Fail-SAFE direction of `_skip_for_lean_gaming`.** A config-read error returns `True` (skip the subsystem), NOT `False` (load it). This is intentional for anticheat safety.

7. **`anticheat_safe_mode` PINNED ON in schema.** The default is `True` and there's no documented way to permanently set it False — it's a safe-by-default posture. The config.yaml confirms `anticheat_safe_mode: true`.

8. **Import firewall is ALWAYS installed**, regardless of anticheat state (line ~744). It's a no-op while anticheat is off; it fires the moment anticheat is activated. Never bypass.

9. **`KENNING_RELAY_TEAM_DSP`** — the team-path audio DSP gate — is an env var gate (not a config.yaml flag). It's the pattern for anticheat-safe runtime toggles that don't need Pydantic validation.

---

## 13. Files and Symbols Reference

| File | Role |
|------|------|
| `config.yaml` (2058 lines) | Single source of truth; all tunable parameters; uses `${VAR}` for env substitution |
| `src/kenning/config.py` (~4400 lines) | Pydantic schema + singleton loader + runtime overrides + effective-config log |
| `config/settings.py` | Legacy compat shim; re-exports `settings.X` from `get_config()`; being phased out |
| `data/runtime_overrides.json` | Ephemeral GUI overlay; never committed; wiped at each boot |
| `src/kenning/pipeline/orchestrator.py` | Main event loop; `_skip_for_lean_gaming()`; lazy imports; anticheat hooks |
| `src/kenning/safety/anticheat.py` | `anticheat_active()`, `set_anticheat_active()`, `register_surface_hook()` |
| `src/kenning/safety/import_firewall.py` | `install_import_firewall()` — sys.meta_path backstop |

**Key symbols in `config.py`:**
- `_Strict` — base model with `extra="forbid"`
- `KenningConfig` — top-level config model
- `GamingModeConfig` — all `barebones_skip_*` flags live here
- `LLM_PRESETS` — preset name → field values dict
- `SUPERVISOR_TIERS` — tier name → phase-flag expansion dict
- `LLMConfig._apply_preset` — `@model_validator(mode="after")` preset expansion
- `load_config()` — 5-stage pipeline; `apply_overrides` controls GUI overlay
- `get_config()` — singleton accessor
- `reload_config()` — forces reload with `apply_overrides=True`
- `set_config()` — test injection
- `clear_runtime_overrides()` — called at orchestrator startup; wipes GUI edits
- `_merge_runtime_overrides()` — dot-path JSON overlay application
- `_ENV_OVERRIDE_NOTES` — documented KENNING_* env var effects
- `log_effective_config()` — startup diagnostic; logs all KENNING_* env vars + key settings

**Key symbols in `orchestrator.py`:**
- `_skip_for_lean_gaming(flag)` — lean-boot gate (line 1715)
- `clear_runtime_overrides()` call — at orchestrator `__init__` startup
- `_audit_anticheat_posture()` — regression canary (line 1784)
- `_start_dialog_poller()` — anticheat-gated desktop import (line 1745)
- `KENNING_SNAP_EARLY_ENDPOINT` — inline env var for latency E3 snap-early-endpoint (off by default)
- `KENNING_SMART_TURN_MIN_COMPLETE_MS` — inline env var for min-speech floor
