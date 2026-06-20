# A10: Anticheat firewall, lean boot & gaming mode

## Overview

The Kenning/Ultron anticheat posture is a belt-and-suspenders, three-layer system designed to guarantee that no input-injection, screen-capture, window-control, or browser-automation code ever enters the process RAM while a kernel-anticheat game (Vanguard, EAC, BattlEye) is running. The lean-boot mechanism supplements this by ensuring that non-essential subsystems are never imported at all during a gaming session, not just call-gated.

The system has three distinct but coordinated mechanisms:

1. **Import firewall** (`src/kenning/safety/import_firewall.py`) — a `sys.meta_path` finder that hard-blocks at the loader level; installs before any other import.
2. **Anticheat mode** (`src/kenning/safety/anticheat.py`) — a process-wide flag with module-level call guards, safety-validator BLOCK_HARD, and orchestrator intent refusals.
3. **Gaming mode + lean boot** (`src/kenning/openclaw_routing/gaming_mode.py`, `src/kenning/config.py`, `src/kenning/pipeline/orchestrator.py`) — wires anticheat to game engage/disengage, skips non-essential subsystems at boot, reclaims VRAM at idle.

Defaults are **safe-by-default**: `anticheat_safe_mode: true`, `anticheat_with_gaming_mode: true`, `engage_at_startup: true`. A freshly unconfigured machine comes up in the locked-down gaming posture.

---

## Files & key symbols

| File | Role | Key symbols |
|------|------|-------------|
| `src/kenning/safety/import_firewall.py` | Loader-level block on blocked modules | `AnticheatImportFirewall`, `install_import_firewall()`, `assert_firewall_enforces()`, `is_firewall_installed()`, `is_blocked_module()`, `blocked_module_names()`, `_BLOCK_PREFIXES`, `_BLOCK_EXACT` |
| `src/kenning/safety/anticheat.py` | Process-wide mode flag, call guards, tool-name block list, voice toggle | `anticheat_active()`, `set_anticheat_active()`, `guard()`, `is_blocked_tool()`, `match_anticheat_toggle()`, `register_surface_hook()`, `AnticheatBlockedError`, `BLOCKED_NOTICE` |
| `src/kenning/openclaw_routing/gaming_mode.py` | Gaming mode engage/disengage state machine; ties to anticheat | `GamingModeManager`, `GamingModeStatus`, `GamingModeReport`, `is_gaming_mode_active()`, `set_gaming_mode_active()` |
| `src/kenning/config.py` (class `GamingModeConfig`, ~line 3000) | Schema for all gaming/anticheat/lean-boot flags with defaults | `GamingModeConfig`, `IdleVramReclaimConfig`, all `barebones_*` fields |
| `src/kenning/__main__.py` | Entry point; installs firewall FIRST; fatal if not enforcing under anticheat | `main()`, `_ResilientStream`, `_ensure_utf8_stdio()` |
| `src/kenning/pipeline/orchestrator.py` | Orchestrator boot; `_skip_for_lean_gaming()`, `_audit_anticheat_posture()`, gaming-mode manager, VRAM reclaim | `_skip_for_lean_gaming()` (line 1715), `_audit_anticheat_posture()` (line 1784), `_start_dialog_poller()` (line 1745), `_idle_vram_reclaim()` (line 3093) |
| `src/kenning/safety/validator.py` | Tool-call validator; anticheat pre-check before rule eval; audit-trail layer | `ToolCallValidator.check()`, `Verdict.BLOCK_HARD`, anticheat pre-check at line 275 |

---

## Control/data flow

### Boot sequence (anticheat path)

```
python -m kenning  (__main__.main)
  1. _ensure_utf8_stdio()           -- crash-proof stdout
  2. configure_logging()
  3. os.environ.setdefault("KENNING_FLAVOR_TAILS", "0")   -- flavor tails OFF for gaming
  4. install_import_firewall()      -- inserts AnticheatImportFirewall at sys.meta_path[0]
  5. assert_firewall_enforces()     -- live probe: tries to import "interception" (blocked+absent)
  6. anticheat_active() check       -- if active AND (firewall missing OR not enforcing):
       FATAL: log CRITICAL + print + return 4  (refuse to start)
  7. acquire_single_instance_lock() -- OS file lock; prevents double-boot
  8. (lazy) from kenning.pipeline import Orchestrator  -- NOW safe; firewall is live
  9. Orchestrator.__init__()        -- lean-boot gates fire here
 10. orchestrator.run()
```

### Orchestrator.__init__ anticheat/lean-boot sub-sequence

Within `Orchestrator.__init__` (orchestrator.py):

- **Line ~689**: Registers surface hooks via `register_surface_hook()`:
  - `"dialog_poller"` hook: stops/restores the UIA DialogPoller on mode flip.
  - `"capture_singletons"` hook: releases mss/pyautogui singletons on activate IF already loaded (never imports them).
- **Line ~727**: If config-pinned anticheat is active, calls `set_anticheat_active(True, "pinned by config at startup")` to fire surface hooks.
- **Line ~744**: `install_import_firewall()` — idempotent second call (no-op since `__main__` already installed it; guarded by `_INSTALLED` flag).
- **Line ~862**: Docker autostart: skipped via `_skip_for_lean_gaming("barebones_skip_docker_autostart")`.
- **Line ~904**: Reranker warmup: skipped via `_skip_for_lean_gaming("barebones_skip_reranker_warmup")`.
- **Line ~922**: LLM load: `_skip_for_lean_gaming("barebones_direct_gaming_llm")` → boot directly into gaming preset (3B CPU) instead of loading 4B GPU then swapping.
- **Line ~1162**: `GamingModeManager` constructed (always, even in lean boot — it owns the anticheat tie-in).
- **Line ~1498**: `engage_at_startup` check → calls `manager.engage()` at the END of `__init__`. Sets `_GAMING_MODE_ACTIVE=True` and calls `set_anticheat_active(True, "gaming mode engaged")`.
- **Line ~1524**: `_audit_anticheat_posture()` — last boot step, fail-open.

### Gaming mode engage/disengage (gaming_mode.py)

`GamingModeManager.engage()`:
1. For each plugin slug in `plugins_to_disable` → `client.disable_plugin(slug)` (best-effort, async).
2. Optionally stops Docker Desktop.
3. In `finally`: `set_gaming_mode_active(True)` → process-global bool.
4. In `finally`: `_set_anticheat(True)` → `set_anticheat_active(True, "gaming mode engaged")`.
5. Fires `_on_engaged` callback (used by orchestrator to swap LLM to gaming preset + Kokoro device).
6. Writes row to `logs/gaming_mode.jsonl`.

`GamingModeManager.disengage()`: reverse — re-enables plugins, `set_gaming_mode_active(False)`, `set_anticheat_active(False, "gaming mode disengaged")`, fires `_on_disengaged`.

### Firewall mechanics (import_firewall.py)

`AnticheatImportFirewall.find_spec(fullname, path, target)`:
1. `is_blocked_module(fullname)` — prefix check (`_BLOCK_PREFIXES`) + exact name check (`_BLOCK_EXACT`).
2. If blocked: read `anticheat_active()` LIVE. On any exception: `active = True` (fail-SAFE — uncertain → block).
3. If `active == False`: return `None` (pass through to normal finders).
4. If `active == True`: log ERROR + raise `ImportError` with message containing `"anticheat import firewall"`.

### Anticheat mode flag (anticheat.py)

`anticheat_active()` returns True if ANY of:
- `_runtime_active` (set by voice toggle or gaming-mode tie-in)
- `is_testing_mode_active()` (testing mode also gates the desktop stack)
- `get_config().gaming_mode.anticheat_safe_mode == True` (config pin, default True)

`set_anticheat_active(active, reason)`:
1. Sets `_runtime_active`.
2. Iterates `_surface_hooks` — calls each hook with `active`. Hooks are fail-open.

### Anticheat posture self-audit (orchestrator.py:1784)

Run as the LAST step of `__init__`. Steps:
1. Gets `blocked_module_names()` from firewall module.
2. Checks `sys.modules` for any blocked names (excluding `kenning.*`/`ultron.*` prefixes).
3. Checks `"kenning.desktop" in sys.modules` and `"kenning.openclaw_bridge.browser"` / `".desktop"`.
4. Verifies firewall installed AND enforcing via `assert_firewall_enforces()`.
5. Checks dialog poller running status.
6. If anticheat active and any of the above are present: logs `ERROR "ANTICHEAT POSTURE CANARY: ..."`.
7. Otherwise: logs `INFO "anticheat posture OK | ..."`.
8. Divergence check: if `engage_at_startup` and (`testing_mode ON` or `push_to_talk ENABLED`): logs `WARNING "NON-DEFAULT SAFETY FLAGS LIVE ..."`.
9. Lean boot canary: if `engage_at_startup`, checks that heavy modules (`kenning.openclaw_bridge.holder`, `kenning.coding.mcp_server`, `kenning.coding.voice`, `kenning.evolution.service`, `sentence_transformers`, `moonshine_voice.intent_recognizer`) are NOT in `sys.modules`; checks instance-level attributes `_intent_recognizer`, `_ack_clip_prewarm_thread`, `memory`, `web_gate`/`web_executor`. If any leaked: logs `ERROR "LEAN BOOT CANARY: ..."`.

### VRAM reclaim (orchestrator.py:3093, `_idle_vram_reclaim()`)

Called at idle transition (after response spoken, before blocking on wake word). Steps:
1. Reads `cfg.llm.idle_vram_reclaim` — if not enabled, no-op.
2. If `torch.cuda.is_available()` and slack (reserved − allocated) > `min_slack_mb` (default 192 MB): calls `torch.cuda.empty_cache()`.
3. Fail-open throughout. Zero turn-latency cost.

Also: a post-init `torch.cuda.empty_cache()` fires unconditionally at the end of `__init__` (line ~1482) to trim allocator fragmentation after model loads.

---

## Key findings

1. **Firewall installs before the Orchestrator module is even imported** — `__main__.main()` calls `install_import_firewall()` before the lazy `from kenning.pipeline import Orchestrator` (line 199 of `__main__.py`). There is zero window where blocked modules could load transitively through the Orchestrator's own imports.

2. **Fatal boot if not enforcing under anticheat** — if `anticheat_active()` is True and the firewall is not installed or not enforcing, `main()` returns exit code 4 with a CRITICAL log and console message. Does not boot at all.

3. **Fail-SAFE throughout** — the firewall defaults to BLOCKING on any exception reading the anticheat flag; `_skip_for_lean_gaming()` defaults to SKIP (lean posture) on config-read error; `anticheat_active()` fail-open only for the config pin (runtime flag still applies).

4. **Three activation paths for anticheat**:
   - Config pin: `gaming_mode.anticheat_safe_mode: true` (default True) — always-on.
   - Gaming mode tie-in: `anticheat_with_gaming_mode` (default True) — fires on engage/disengage.
   - Voice toggle: "enable anticheat mode" / "disable anticheat mode" — strict regex only.
   - Testing mode: `is_testing_mode_active()` also activates the flag (keeps desktop stack blocked).

5. **Lean boot is gated on CONFIG INTENT** (`gaming_mode.engage_at_startup`), NOT on the runtime gaming mode state (which isn't set until the end of `__init__`). This is critical: `_skip_for_lean_gaming()` checks `engage_at_startup`, not `is_gaming_mode_active()`.

6. **The embedder sidecar runs in an ISOLATED venv** — the embeddinggemma-300M model never loads into the anticheat-pinned main process. The sidecar receives `KENNING_EMBEDDER_PARENT_PID` so it self-exits if the orchestrator dies.

7. **The pytesseract exception is documented** — `transformers` (pulled by Kokoro TTS + Whisper) calls `importlib.util.find_spec("pytesseract")` at import time. The old firewall raised on `find_spec` probes (not just actual imports), cascading to silence Kokoro/Whisper. Fix (2026-06-18, reapplied): pytesseract deliberately NOT in `_BLOCK_EXACT`; its OCR capability is already blocked via the `kenning.desktop` prefix.

8. **`prevent == detect` symmetry** — `_audit_anticheat_posture()` derives its tripwire module set directly from `blocked_module_names()` (the firewall's own list), so they can never drift apart.

9. **Surface hooks are call-gated, not just flag-gated** — `register_surface_hook()` fires on every `set_anticheat_active()` call so RUNNING subsystems (UIA poller thread, cached mss objects) are physically stopped, not just call-blocked.

10. **Idle VRAM reclaim** — `torch.cuda.empty_cache()` at idle (after spoken response, before wake-word block), gated on 192 MB slack. Only fires when the caching allocator has real bloat (Kokoro CUDA high-water-mark drift). Never on the hot path.

---

## Flags & config

All in `config.yaml` under `gaming_mode:` unless noted. Schema in `src/kenning/config.py`:

| Key | Default | Effect |
|-----|---------|--------|
| `gaming_mode.enabled` | `True` | GamingModeManager is active at all |
| `gaming_mode.anticheat_safe_mode` | `True` | Pins anticheat ON permanently via config; firewall bites on every blocked import |
| `gaming_mode.anticheat_with_gaming_mode` | `True` | anticheat flips with gaming mode engage/disengage |
| `gaming_mode.engage_at_startup` | `True` | Gaming mode engaged automatically at boot; gates all lean-boot skips |
| `gaming_mode.barebones_direct_gaming_llm` | `True` | Boot directly into gaming LLM preset; no 4B-GPU load-then-swap |
| `gaming_mode.barebones_skip_reranker_warmup` | `True` | Skip cross-encoder reranker warmup at boot |
| `gaming_mode.barebones_skip_docker_autostart` | `True` | Skip SearxNG/Docker probe at boot |
| `gaming_mode.barebones_skip_coding` | `True` | Skip MCP server + coding coordinator + CodingVoice/ProjectIndex/Supervisor |
| `gaming_mode.barebones_skip_openclaw` | `True` | Skip OpenClaw bridge (gateway probe + retry thread + voice-handoff receiver) |
| `gaming_mode.barebones_skip_evolution` | `True` | Skip autonomous self-improvement service |
| `gaming_mode.barebones_skip_skills` | `True` | Skip skills registry walk + per-turn prompt injection |
| `gaming_mode.barebones_skip_events` | `True` | Skip JSONL bus event sink |
| `gaming_mode.barebones_skip_summarizer` | `True` | Skip idle background LLM summarization pass |
| `gaming_mode.barebones_skip_memory` | `True` | Skip conversation memory store (Qdrant + FastEmbed encoders) |
| `gaming_mode.barebones_skip_intent` | `True` | Skip in-process intent recognizer (prevents second embeddinggemma in main process) |
| `gaming_mode.barebones_skip_ack_prewarm` | `True` | Skip precomputed ack-clip cache warmup |
| `gaming_mode.barebones_lazy_zero_shot_addressee` | `True` | Defer flan-t5 addressee model load until first ambiguous follow-up |
| `gaming_mode.barebones_skip_retrieval` | `True` | Skip per-turn RAG memory retrieval |
| `gaming_mode.barebones_skip_web_search` | `True` | Skip web-search preflight + executor |
| `gaming_mode.llm_gpu_layers` | `0` | GPU layers for gaming LLM; 0 = fully CPU; -1 = keep on GPU |
| `gaming_mode.kokoro_engage_device` | `"cuda"` | Kokoro voice model device while gaming (kept GPU for low latency) |
| `gaming_mode.llm_preset` | `"llama-3.2-3b-abliterated"` | LLM preset used during gaming mode |
| `gaming_mode.plugins_to_disable` | `["desktop-control", "windows-control"]` | OpenClaw plugins disabled on engage |
| `gaming_mode.toggle_docker` | `False` | Whether to kill Docker Desktop on engage |
| `gaming_mode.log_path` | `"logs/gaming_mode.jsonl"` | Gaming mode transition log |
| `llm.idle_vram_reclaim.enabled` | `True` | torch.cuda.empty_cache() at idle |
| `llm.idle_vram_reclaim.min_slack_mb` | `192.0` | Minimum VRAM slack before reclaim fires |
| `addressing.follow_up_enabled` | `False` (schema default) | Wake-free follow-up window — default OFF to prevent false positives |

**Env vars** (override config at entry or process level):

| Env var | Default | Effect |
|---------|---------|--------|
| `KENNING_FLAVOR_TAILS` | `"0"` (set by `__main__`) | Flavor tails off for gaming; overrides library default of `"1"` |
| `KENNING_SNAP_REGISTRY` | `"1"` | Snap registry (data-driven SnapRule) on/off |
| `KENNING_RELAY_TEAM_DSP` | `"1"` | DSP chain on team relay path |
| `KENNING_WAKE_TRIM_TO_SPEECH` | `"1"` | VAD-based wake word audio trimming |
| `KENNING_EMBEDDER_PARENT_PID` | (set by orchestrator) | PID passed to embedder sidecar for orphan self-exit |
| `KENNING_EMBEDDER_BACKEND` | `"sentence_transformers"` | Embedder backend |
| `KENNING_EMBEDDER_DEVICE` | (from config) | Device for embedder sidecar |
| `KENNING_PTT_*` | — | PTT config; takes precedence over config.yaml |
| `KENNING_AUDIO_DEVICE` / `KENNING_AUDIO_OUTPUT_DEVICE` / `KENNING_AUDIO_BROADCAST_DEVICE` | (none) | Audio device overrides |
| `KENNING_ADDRESSING_TAU` | `0.20` | Cost-asymmetric threshold for addressee confidence |

---

## Extension points

For Ultron 1.0 (LLM-centric pivot):

1. **Firewall blocklist** (`import_firewall.py:_BLOCK_EXACT` and `_BLOCK_PREFIXES`): add entries by appending to either collection. The posture self-audit and canary automatically pick them up via `blocked_module_names()` with no second list to maintain.

2. **Surface hooks** (`anticheat.py:register_surface_hook(name, hook)`): register a callable to stop/restore any new subsystem on mode flip. The orchestrator registers two at boot; new subsystems can register their own.

3. **Lean boot skips** (`config.py:GamingModeConfig`): add a new `barebones_skip_<X>: bool = True` field plus a corresponding `_skip_for_lean_gaming("barebones_skip_<X>")` gate in orchestrator. The lean-boot canary automatically checks instance attributes named `_<X>` if you also add the attribute check at orchestrator.py:1927.

4. **Gaming mode callbacks** (`gaming_mode.py:GamingModeManager.__init__`): `on_engaged` and `on_disengaged` callables are wired by the orchestrator for Kokoro device swap and LLM preset swap. New u1.0 model-management hooks can be wired here.

5. **Tool-name block list** (`anticheat.py:_BLOCKED_TOOL_EXACT` and `_BLOCKED_TOOL_PREFIXES`): add new tool names/prefixes that must never dispatch under anticheat. The validator's pre-check runs before rule evaluation.

6. **Voice toggle phrasings** (`anticheat.py:_TOGGLE_ON_RE / _TOGGLE_OFF_RE`): extend the regexes if new phrasings are needed. Currently matches: "enable/engage/activate/turn on anticheat/anti-cheat/tournament mode".

---

## Retire-not-remove candidates (u1.0)

The pivot context says deterministic snaps become ROUTERS that detect intent and pick prompt templates. The anticheat/lean-boot system is architecture-agnostic and carries forward with minimal change. Specific candidates:

1. **`barebones_skip_intent`** — currently skips the in-process intent recognizer (which loaded a second embeddinggemma). If u1.0 routes ALL responses through an 8B LLM, the intent recognizer may be retired or replaced entirely. The skip flag and its canary check remain as guards for whatever replaces it — do not remove the skip mechanism.

2. **`barebones_skip_skills`** — skills registry injects per-turn prompts. If u1.0 uses curated prompt templates instead, the skills injection path may not be needed. Retain the skip gate; retire the skills loading in gaming mode.

3. **`barebones_skip_summarizer`** — idle background LLM summarization competes with relay latency. If u1.0 uses the 8B in-process for relay, the idle summarizer is even more likely to collide. Retain the skip; reassess whether to retire the summarizer entirely or time-slice differently.

4. **`barebones_skip_reranker_warmup`** — cross-encoder reranker is used for RAG. If u1.0 skips retrieval in gaming mode, the reranker is never called. Retain the skip; the reranker itself is a retire candidate for gaming sessions.

5. **Deterministic snap paths in relay_speech** — per the pivot, these become intent detectors + template selectors + exemplar injectors rather than response generators. The `KENNING_SNAP_REGISTRY` flag and the snap registry data structure are natural extension points for the new "router picks curated prompt template" role.

6. **`GamingModeConfig.llm_preset`** — currently swaps to a 3B-CPU model on engage. If u1.0 uses an 8B LLM for all responses, this preset will need to be updated. The swap mechanism (and the `on_engaged`/`on_disengaged` callbacks) are retain-and-update, not retire.

---

## Gotchas

1. **pytesseract must stay out of `_BLOCK_EXACT`** — `transformers` calls `importlib.util.find_spec("pytesseract")` at import time (not just on `import pytesseract`). The firewall intercepts `find_spec` calls because it hooks `find_spec` on `MetaPathFinder`. The 2026-06-18 hotfix removed pytesseract from `_BLOCK_EXACT` because the probe hit the raise-always firewall → Kokoro/Whisper cascade went silent. Any future addition to `_BLOCK_EXACT` must be checked: if a commonly-imported library (transformers, torch, etc.) probes it via `find_spec`, the same silence regression will recur.

2. **`_skip_for_lean_gaming()` gates on CONFIG INTENT, not runtime state** — it reads `gaming_mode.engage_at_startup` from config, which is a boot-time constant. Calling it after `__init__` or in a hot path is safe (idempotent), but its answer never changes mid-session. The RUNTIME gaming mode (`is_gaming_mode_active()`) is a separate flag and is what the per-turn guards use.

3. **Fail-SAFE skip direction** — `_skip_for_lean_gaming()` returns `True` (skip the subsystem) on a config-read error. This is intentional: beside a kernel anticheat, failing to read the config is worse than skipping an optional subsystem. Any new subsystem that is NOT optional for gaming (e.g. core relay) must NOT be gated behind this helper.

4. **anticheat_active() consults testing_mode** — `is_testing_mode_active()` returning True also triggers `anticheat_active() == True`, which bites the firewall. `testing_mode.enabled: true` in config.yaml + anticheat flags = all blocked imports stay blocked even in testing. The divergence check in `_audit_anticheat_posture()` will warn about this.

5. **The posture self-audit is fail-open** — it logs errors but never raises or aborts boot. A regression canary that fires in the log is visible but the process continues. For u1.0, consider escalating this to a startup refusal if ANY blocked lib is found in sys.modules under anticheat.

6. **`anticheat_safe_mode: true` (config default) means the firewall ALWAYS bites** even in non-gaming sessions unless the user explicitly sets it to false or the runtime flag is off and testing_mode is off. The config pin is the strongest activator and is safe-by-default.

7. **Surface hook order matters** — hooks run in registration order. The `"dialog_poller"` hook stops/starts the UIA poller. The `"capture_singletons"` hook releases mss/pyautogui state. These must run before any new hook that assumes the desktop stack is cold.

8. **The embedder sidecar isolation** — the embedding model (embeddinggemma-300M, ~200 MB) runs in a SEPARATE process and venv, receiving the parent PID via `KENNING_EMBEDDER_PARENT_PID`. This is the anticheat isolation for the router's semantic backend. For u1.0, if the 8B LLM is used for routing (instead of or in addition to the embedder), ensure it also runs in-process (already anticheat-safe: no OS interaction) rather than as a sidecar that could be mistaken for injection-adjacent.

9. **`comtypes.gen` vs `comtypes`** — the firewall blocks `comtypes.gen.*` (the generated UIA COM proxy stubs) but NOT `comtypes` itself (pycaw/audio may pull it). This is intentional. The UIA capability lives in the generated stubs; blocking the prefix keeps it cold.

10. **Two-process PTT** — PTT is the ONLY in-process keyboard-like operation and it is explicitly anticheat-clean: the host writes bytes to an external USB-HID microcontroller over serial/HID, the peripheral physically presses the key. `keyboard`/`pydirectinput` are in `_BLOCK_EXACT` as tripwires for the auto-PTT path regressing to in-process keypress libs.

---

## Open questions

1. **u1.0 8B LLM VRAM budget with gaming** — the current gaming mode swaps to a 3B CPU model to free ~1.5 GB VRAM. With u1.0 routing everything through an 8B LLM, what is the GPU strategy? Keep 8B on GPU and accept the VRAM hit, or keep it on CPU (slower but anticheat-clean for VRAM)?

2. **`_skip_for_lean_gaming()` for u1.0 new subsystems** — the LLM-centric pipeline will likely need a prompt-template store, an intent classification path, and possibly an exemplar injector. Are these new subsystems always loaded (part of core relay) or conditionally skipped in lean gaming? Architect needs to decide before the lean-boot canary check is extended.

3. **Does the posture self-audit need to become fatal?** — currently it logs ERROR but never aborts. Given that u1.0 will be a production-grade tool, should a loaded blocked module under anticheat be a startup refusal (not just a canary log)? The firewall already blocks calls, but loaded memory is a footprint Vanguard could theoretically observe.

4. **Testing mode + anticheat interaction in u1.0** — `testing_mode.enabled: true` activates the firewall. Will the u1.0 testing harness need a testing mode that does NOT activate the firewall (to test desktop tools in CI)? Currently `conftest.py` calls `set_config_pin_enabled(False)` but this only disables the config pin, not a testing_mode flag.

5. **`barebones_skip_memory` + u1.0 conversation history** — the lean boot skips Qdrant + encoders entirely. If u1.0 uses the LLM's in-context history deque for conversation state in gaming, this is fine. But if any of the new LLM-centric pipeline features (e.g. conversation grounding, persona consistency) require vector retrieval, they will silently degrade to nothing in lean gaming.

6. **OpenClaw bridge retire path** — `barebones_skip_openclaw: true` skips the OpenClaw bridge entirely. If u1.0 removes OpenClaw dependency (moving to direct LLM dispatch), the bridge skip flag becomes a permanent noop and could be cleaned up.
