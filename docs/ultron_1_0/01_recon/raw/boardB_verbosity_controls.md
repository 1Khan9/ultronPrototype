# B8: MAP verbosity/length controls today (the no/low/high flavor substrate)

## Overview

The system has two overlapping verbosity layers that act on different surfaces:

1. **Relay-path verbosity** — controls whether snap callouts carry an in-character flavor tail. Binary ON/OFF today (`KENNING_FLAVOR_TAILS`). When OFF, curated compact alternatives replace the tail-bearing versions for many social/identity/economy categories.

2. **Conversational-path verbosity** — controls the LLM's response LENGTH via:
   - Per-utterance `[Style: ...]` hints prepended by `apply_brevity_hint()` (response_style.py)
   - Optional adaptive `[Tone: ...]` hints prepended by `apply_temperament()` (evolution/personality.py)
   - `max_tokens` cap in `_RELAY_SAMPLING` (56 tokens) and `_ANSWER_SAMPLING` (80 tokens) for relay LLM paths, vs `default_max_tokens=512` for conversational

There is no concept of "low/medium/high verbosity" today — only:
- ON/OFF flavor tail (relay path)
- THINKING MODE ON/OFF (LLM vs deterministic on compose/social relay)
- auto-hinting per brevity/factual/procedural detection (conversational path)

**There is no prompt-driven verbosity slider.** The `PersonalityState.verbosity` field in `evolution/models.py` exists but its `[Tone: ...]` directive is barely wired and only affects the conversational (non-relay) path. The relay persona persona string (`ULTRON_GAMING_PERSONA`) hardcodes "one short sentence (two at most), under ~25 words."

---

## Files & key symbols (path:line tables)

### relay_speech.py — Flavor-tail controls

| Symbol | File:Line | Role |
|--------|-----------|------|
| `MAX_RELAY_LINE_CHARS` | `src/kenning/audio/relay_speech.py:65` | Hard character cap on final spoken relay line (360 chars) |
| `_flavor_tails_enabled` | `src/kenning/audio/relay_speech.py:1136` | Process-global bool; set from `KENNING_FLAVOR_TAILS` env at import |
| `set_flavor_tails_enabled(enabled)` | `relay_speech.py:1141` | Runtime setter (voice toggle calls this) |
| `flavor_tails_enabled()` | `relay_speech.py:1147` | Runtime getter checked at every tail join |
| `match_flavor_toggle(text)` | `relay_speech.py:1167` | Regex matcher; returns True/False/None; checks `_FLAVOR_OFF_RE`, `_FLAVOR_ON_RE`, and mishear variants |
| `_join_tail(head, tail)` | `relay_speech.py:3686` | Single chokepoint: if `_flavor_tails_enabled` is False, returns bare head |
| `_flavor_off_response(command, recent_lines)` | `relay_speech.py:5843` | Returns a tail-free curated line for overlapping social/identity/economy categories when flavor is OFF |
| `_flavor_off_identity_line(cat)` | `relay_speech.py:5829` | Returns crisp no-tail identity rebuttal for soundboard/voice_changer/streamer |
| `_FO_CLUTCH`, `_FO_FLAMING`, `_FO_CRINGE`, `_FO_ARGUING`, `_FO_SHUTUP`, `_FO_STOP`, `_FO_ENCOURAGE`, `_FO_FLAME_ENEMY`, `_FO_FLAME_AGENT`, `_FO_SIMPLE` | `relay_speech.py:5722–5800` | Flavor-OFF curated pool tuples for each social/economy command category |
| `_cap_line(line, max_chars)` | `relay_speech.py:5111` | Cap at sentence boundary; fallback to word boundary + period |
| `_cap_sentences(line, max_sentences=3)` | `relay_speech.py:5139` | Cap off-snap model output at N whole sentences (applied at 2 for relay LLM output, line 6413) |
| `_thinking_mode_enabled` | `relay_speech.py:1197` | Whether relay compose path uses LLM or deterministic pools |
| `set_thinking_mode_enabled(enabled)` | `relay_speech.py:1202` | Runtime setter for thinking mode |
| `thinking_mode_enabled()` | `relay_speech.py:1208` | Getter checked before `rephrase=` arg in build_relay_line |
| `_RELAY_SAMPLING` | `relay_speech.py:2507` | Dict: `max_tokens=56`, `temperature=0.8`, `top_p=0.92`, `top_k=40`, `min_p=0.08`, `repeat_penalty=1.18`, stop sequences |
| `_RELAY_REPHRASE_SYSTEM` | `relay_speech.py:2526` | System prompt for relay LLM rephrase: "one breath, no quotes, no preamble..." |
| `build_relay_line(command, llm, rephrase, max_chars, recent_lines, generate_fn)` | `relay_speech.py:6017–6017` | Master function; applies flavor-OFF override, then snap paths, then deterministic, then LLM if rephrase=True |

### relay_speech.py — LLM output shaping after generation

| Symbol | File:Line | Role |
|--------|-----------|------|
| `_cap_sentences(line, max_sentences=2)` | `relay_speech.py:6413` | Applied post-LLM to cap model output at 2 whole sentences |
| `_strip_spurious_vocative(line, command)` | `relay_speech.py:5165` | Drop leading roster-name vocative the 3B prepended |
| `_fix_proper_nouns(line)` | Called at `relay_speech.py:6419` | Fix mangled Marvel proper nouns |
| `_repair_against_input(payload, line)` | `relay_speech.py:6424–6427` | Repair dropped facts/invariants for plain tactical lines |

### response_style.py — Conversational brevity hints

| Symbol | File:Line | Role |
|--------|-----------|------|
| `_BREVITY_HINT` | `src/kenning/response_style.py:54` | `[Style: respond in 1-3 short sentences...]` prepended to brief conversational questions |
| `_FACTUAL_HINT` | `response_style.py:46` | `[Style: respond with one short sentence containing only the specific fact...]` |
| `_PROCEDURAL_HINT` | `response_style.py:65` | `[Style: respond with detailed numbered steps...]` |
| `_BREVITY_MAX_WORDS` | `response_style.py:81` | 12 words threshold for "brief question" detection |
| `_BREVITY_MAX_CHARS` | `response_style.py:82` | 80 chars threshold for "brief question" detection |
| `is_brief_question(user_text)` | `response_style.py:238` | True iff <=12 words AND <=80 chars AND no depth markers |
| `is_factual_question(user_text)` | `response_style.py:222` | True iff matches factual-stem regex patterns (how much/when did/who invented etc.) |
| `is_procedural_request(user_text)` | `response_style.py:206` | True iff contains procedural marker phrases (step by step/walk me through/etc.) |
| `apply_brevity_hint(user_text)` | `response_style.py:272` | Public dispatcher: procedural > factual > brief > unchanged. Idempotent (skip if already hinted) |
| `_DEPTH_MARKERS` | `response_style.py:176` | Tuple of keywords that suppress brevity hint ("explain", "in detail", "thoroughly", etc.) |

### evolution/personality.py — Adaptive temperament hints

| Symbol | File:Line | Role |
|--------|-----------|------|
| `PersonalityState` | `src/kenning/evolution/models.py:509` | Dataclass with `verbosity: float`, `rigor: float`, `creativity: float`, `risk_tolerance: float`, `obedience: float` (all default 0.5) |
| `VERBOSITY_LOW` | `evolution/personality.py:50` | 0.35 threshold — below this, emit "keep it concise" |
| `VERBOSITY_HIGH` | `evolution/personality.py:51` | 0.65 threshold — above this, emit "be thorough" |
| `temperament_hint(state)` | `evolution/personality.py:95` | Returns `[Tone: keep it concise]` or `[Tone: be thorough]` (empty for balanced) |
| `apply_temperament(user_text, state)` | `evolution/personality.py:117` | Prepends tone hint; idempotent; no-op when balanced |
| `PersonalityTuner.record_feedback(fb)` | `evolution/personality.py:130` | Online gradient nudge: barge-in lowers verbosity, re-ask raises it, correction raises rigor |

### inference.py — LLM token caps and generation controls

| Symbol | File:Line | Role |
|--------|-----------|------|
| `default_max_tokens` | `src/kenning/config.py:906` | Default 512 tokens for conversational LLM responses |
| `_build_sampling_kwargs(sampling, stream)` | `src/kenning/llm/inference.py:2176` | Builds kwargs; passes `sampling` overrides (allows max_tokens, temperature, top_p, top_k, min_p, repeat_penalty, stop, grammar) |
| `generate_stream(user_message, sampling=None, ...)` | `inference.py:1840` | Main streaming generate; accepts `sampling` dict for per-call overrides |
| `generate_isolated(system_prompt, user_prompt, max_tokens=2048, ...)` | `inference.py:1835` | Bypasses SOUL.md; used for background tasks |
| `_apply_no_think_marker(messages, enable_thinking)` | `inference.py:2201` | Appends `/no_think` to Qwen3 user message when `enable_thinking=False` |
| `_BREVITY_HINT_PREFIX_RE` | `inference.py:2203` | Pattern to strip `[Style: ...]` from query before RAG and short-query detection |
| `_strip_brevity_hint(text)` | `inference.py:2223` | Removes brevity hint prefix so RAG sees bare user text |

### _ultron_answer.py — Answer path sampling

| Symbol | File:Line | Role |
|--------|-----------|------|
| `_ANSWER_SAMPLING` | `src/kenning/audio/_ultron_answer.py:239` | `max_tokens=80`, `temperature=0.85`, stop sequences for Marvel/think-respond path |
| `build_answer_call(command)` | `_ultron_answer.py:251` | Returns (system, user, sampling, subtype) for answer path LLM call |

### TTS pacing controls

| Symbol | File:Line | Role |
|--------|-----------|------|
| `KokoroConfig.speed` | `src/kenning/config.py:2455` | Float 0.5–2.0; 1.0 native cadence; production default 1.0 (in-model prosody shaping handles cadence) |
| `KokoroConfig.dur_final_factor` | `config.py:2500` | 1.3 — sentence-final rime lengthening (slows final phoneme) |
| `KokoroConfig.dur_internal_factor` | `config.py:2501` | 1.18 — phrase-internal punctuation rime lengthening |
| `KokoroConfig.max_pause_cap_ms` | `config.py:2505` | 520ms cap on dramatic pauses |
| `tts.pause_ms` | `config.yaml:1158` | 50ms silence between consecutive sentence clips |
| `PiperConfig.piper_length_scale` | `config.yaml:1166` | 1.15 for Piper; >1.0 = slower (Piper legacy only) |
| `TTS_LENGTH_SCALE` (settings.py) | `config/settings.py:328` | Env: `KENNING_TTS_LENGTH_SCALE`; falls back to `piper_length_scale` |
| `TTS_PAUSE_MS` (settings.py) | `config/settings.py:330` | Env: `KENNING_TTS_PAUSE_MS`; falls back to `tts.pause_ms` |

### llm_prompts.py — Persona strings embedding verbosity directives

| Symbol | File:Line | Role |
|--------|-----------|------|
| `ULTRON_GAMING_PERSONA` | `src/kenning/audio/llm_prompts.py:48` | Hardcodes "ONE short sentence (two at most), under ~25 words. Never a paragraph, never a list..." |
| `ANSWER_PERSONA_CORE` | `llm_prompts.py:82` | "Speak ONE or TWO short sentences -- this is a live match, not a monologue." |
| `ANSWER_MARVEL_RULES` | `llm_prompts.py:97` | "one or two sentences" in task directive |
| `ANSWER_THINK_RULES` | `llm_prompts.py:113` | "one or two sentences" in task directive |

### Orchestrator dispatch

| Symbol | File:Line | Role |
|--------|-----------|------|
| `_maybe_handle_flavor_toggle(user_text)` | `src/kenning/pipeline/orchestrator.py:3277` | Calls `match_flavor_toggle`; calls `set_flavor_tails_enabled`; speaks "Flavor on." or "Flavor off. Callouts only." |
| `_maybe_handle_thinking_toggle(user_text)` | `orchestrator.py:3300` | Calls `match_thinking_toggle`; calls `set_thinking_mode_enabled` |
| `_gaming_conversational_prompt()` | `orchestrator.py:9006` | Returns `ULTRON_GAMING_PERSONA` when gaming/testing active or 3B is loaded; else None (desktop "Kenning" persona) |
| `apply_brevity_hint(user_text)` called at | `orchestrator.py:10146, 10207, 10294, 9724` | Applied to conversational path before LLM calls |
| `_consume_last_barge_in()` | `orchestrator.py:4218` | Feeds `barged_in=True` to `PersonalityTuner.record_feedback()` which lowers verbosity drift |

### voice_lines.py — Regex toggles and registry

| Symbol | File:Line | Role |
|--------|-----------|------|
| `_FLAVOR_OFF_RE`, `_FLAVOR_ON_RE` | `src/kenning/audio/voice_lines.py` | Clean phrasings for "flavor off/on" voice commands |
| `_FLAVOR_OFF_MISHEAR_RE`, `_FLAVOR_ON_MISHEAR_RE` | `voice_lines.py` | ASR mishear fallbacks ("save her off" -> flavor off) |
| `SNAP_REGISTRY` | `voice_lines.py:330` | Ordered tuple of `SnapRule`; first match wins; each rule has lines or head_tail tails |
| `TARGET_SNAP_REGISTRY` | `voice_lines.py:363` | Ordered tuple of `TargetSnapRule` for target-based snaps (hello, ask_day) |

---

## Control/data flow

### Relay path (team callouts)

```
User speech
  -> STT -> command_normalizer -> router -> relay_speech.parse_relay_command()
  -> build_relay_line(command, llm, rephrase=thinking_mode_enabled(), max_chars=360)
       |
       v [FLAVOR-OFF GATE]
       if not flavor_tails_enabled():
           _flavor_off_response(command) -> curated tail-free line
           return _cap_line(fo_line, 360)
       |
       v [SNAP_REGISTRY data-driven snaps -- via _join_tail -> respects flavor toggle]
       _apply_snap_registry(payload, recent_lines)
           -> _join_tail(head, tail_pick)  -- tail dropped when flavor OFF
       |
       v [Hardcoded snap paths: clutch, consolation, praise, nice_try, agent_select, thank_you...]
           -> _join_tail(head, tail)  -- tail dropped when flavor OFF
       |
       v [LLM compose path -- only when rephrase=True (THINKING MODE ON)]
           generate_stream(prompt, system=_RELAY_REPHRASE_SYSTEM, sampling=_RELAY_SAMPLING)
           _RELAY_SAMPLING.max_tokens = 56
           _cap_sentences(line, max_sentences=2)
           _cap_line(line, 360)
```

### Conversational path (user speaking directly to Ultron)

```
User speech
  -> STT -> orchestrator._handle_conversational()
       |
       v apply_brevity_hint(user_text)
           is_procedural_request -> prepend _PROCEDURAL_HINT
           is_factual_question   -> prepend _FACTUAL_HINT
           is_brief_question     -> prepend _BREVITY_HINT
           else                  -> unchanged
       |
       v apply_temperament(hinted_text, personality_state)
           [Tone: keep it concise] if verbosity < 0.35
           [Tone: be thorough]     if verbosity > 0.65
       |
       v llm.generate_stream(hinted_text,
               system_prompt=_gaming_conversational_prompt(),  # "one short sentence..."
               sampling={"max_tokens": 512, "temperature": 0.7, ...},
               enable_thinking=False)
```

### TTS pacing

```
TTS line (any path)
  -> KokoroEngine._synthesize_and_play(text)
       -> in-model prosody shaping:
            f0_contour_factor=1.4, f0_shift_semitones=-0.5, dur_final_factor=1.3, etc.
       -> pause_ms=50 silence between clips (TTS_PAUSE_MS)
```

---

## Key findings

1. **Flavor tail toggle is binary (ON/OFF) at a single chokepoint.** `_join_tail()` at `relay_speech.py:3686` is the ONLY place where a tail is appended to a callout. When `_flavor_tails_enabled` is False, the tail is dropped unconditionally regardless of what path produced it. This is the "single tail chokepoint" by design.

2. **Flavor-OFF has its OWN curated compact lines.** When flavor is OFF, `_flavor_off_response()` returns an ALTERNATIVE shorter, punchier line for many categories (clutch, flaming, cringe, arguing, shutup, stop, encourage, flame_enemy, flame_agent, simple social). These are NOT the same lines as flavor-ON minus the tail — they are independently written for the terse register. `_FO_*` pools at `relay_speech.py:5722–5800`.

3. **The app default is FLAVOR OFF** since `2026-06-19`. `__main__.py:111` calls `os.environ.setdefault("KENNING_FLAVOR_TAILS", "0")` before importing relay_speech, so the library default (1=ON) is overridden at app startup. Tests and standalone imports see tails ON (library default "1").

4. **THINKING MODE is off by default.** `KENNING_THINKING_MODE=0` means `rephrase=False` everywhere, so the relay NEVER calls the LLM — 100% deterministic paths. Thinking mode ON routes compose/social commands through the 3B.

5. **Conversational responses are length-controlled by prepended style hints, not by changing the persona.** SOUL.md is "voice-quality-locked". The brevity/factual/procedural hints are prepended to the USER message only. They operate OUTSIDE the system prompt.

6. **The relay has its own tight sampling.** `_RELAY_SAMPLING.max_tokens=56` and `_ANSWER_SAMPLING.max_tokens=80` are much tighter than the conversational default of 512. This is the primary verbosity lever for model-generated relay lines.

7. **`_cap_sentences(max_sentences=2)` is applied post-generation for relay LLM output** (`relay_speech.py:6413`). This is a post-hoc sentence cap on model output, acting AFTER `max_tokens`. Two whole sentences max for off-snap relay answers (Marvel/think-respond).

8. **`MAX_RELAY_LINE_CHARS=360` is the absolute character cap** for ALL relay outputs regardless of path. Applied via `_cap_line()` at every return site in `build_relay_line`.

9. **TTS pacing is controlled separately from content length.** Kokoro `speed=1.0` + in-model prosody shaping (`dur_final_factor=1.3`, etc.) is the speech-rate substrate. `pause_ms=50` controls inter-sentence silence. These are independent of verbal content length.

10. **No per-command verbosity intuition exists today.** "Sova hit 84" and "explain quantum entanglement" both flow through the same `apply_brevity_hint()` — the former is short enough to hit `_BREVITY_HINT`, the latter would be longer. There is no intent-aware verbosity routing. A "Sova hit 84" relay callout is handled deterministically (no LLM, no style hint) via the tactical snapshot path.

11. **`PersonalityState.verbosity` exists but is lightly wired.** The `[Tone: ...]` hint from `temperament_hint()` is defined but it is unclear from the source how often `apply_temperament()` is called in the live path (not seen in the main gaming turn flow — only in `evolution/personality.py` and referenced by the evolution framework). It does NOT override `apply_brevity_hint()`'s `[Style: ...]` because they use different prefixes.

---

## Flags & config

| Flag/Config | Source | Default | Effect |
|-------------|--------|---------|--------|
| `KENNING_FLAVOR_TAILS` | env var | `"0"` (set by `__main__`; library default `"1"`) | When `"0"`: `_join_tail` drops tail; `_flavor_off_response()` returns compact alternatives |
| `KENNING_THINKING_MODE` | env var | `"0"` | When `"0"`: relay compose path uses deterministic pools; `rephrase=False` to `build_relay_line` |
| `KENNING_SNAP_REGISTRY` | env var | `"1"` | When `"0"`: data-driven SNAP_REGISTRY pass is skipped; hardcoded snap paths remain |
| `KENNING_RELAY_TEAM_DSP` | env var | `"1"` (boardA says enabled) | Gates audio DSP chain on team relay path; not a verbosity control |
| `KENNING_TTS_LENGTH_SCALE` | env var | `1.15` (Piper legacy) | Piper voice pacing; `>1.0` = slower. Kokoro uses `speed` instead |
| `KENNING_TTS_PAUSE_MS` | env var | `50` | Inter-sentence silence (ms) |
| `tts.kokoro.speed` | config.yaml:1200 | `1.0` | Kokoro speech rate multiplier |
| `tts.pause_ms` | config.yaml:1158 | `50` | Inter-sentence pause (ms) |
| `llm.default_max_tokens` | config.yaml / config.py:906 | `512` | Token cap for conversational LLM responses; exposed in settings GUI |
| `relay _RELAY_SAMPLING["max_tokens"]` | relay_speech.py:2508 | `56` (hardcoded) | Token cap for relay LLM rephrase; NOT exposed in config |
| `relay _ANSWER_SAMPLING["max_tokens"]` | _ultron_answer.py:240 | `80` (hardcoded) | Token cap for Marvel/think-respond LLM calls; NOT exposed in config |
| `addressing.follow_up_enabled` | config.yaml | `false` | When false, wake word required for every turn (not a verbosity control but affects which turns trigger responses) |
| `ULTRON_GAMING_PERSONA` phrase length directive | llm_prompts.py:48 | hardcoded | "one short sentence (two at most), under ~25 words" |

---

## Extension points

1. **`_join_tail()` is the single verbosity gate for relay tails.** To add a "low verbosity" mode (tail enabled but shorter tails), the cleanest extension is to pass a tail-length budget to `_join_tail()`, or to select from a dedicated short-tail pool. The function signature is `(head, tail) -> str`.

2. **`SNAP_REGISTRY` and `TARGET_SNAP_REGISTRY` in voice_lines.py.** Data-driven; adding `SnapRule` entries adds new snaps without code. Each rule can specify its own `tails` tuple, enabling per-snap verbosity control if the tuple is length-keyed.

3. **`_flavor_off_response()` is the `flavor-OFF` override hook.** For Ultron 1.0, this is the natural place to inject LLM-generated compact alternatives: the function currently returns from curated pools; it could instead call the 8B with a "terse mode" prompt for uncovered categories.

4. **`apply_brevity_hint()` in response_style.py** is the single place to extend conversational brevity detection. New hint classes (e.g. a "minimal" hint for purely tactical relay commands detected in the conversational path) would be added here.

5. **`temperament_hint()` in evolution/personality.py** is the hook for adaptive verbosity. The `PersonalityState.verbosity` float is the natural "no/low/high verbosity" substrate once it's wired to actual prompt selection.

6. **`_RELAY_SAMPLING` and `_ANSWER_SAMPLING` are inline dicts** at relay_speech.py:2507 and _ultron_answer.py:239. For Ultron 1.0 where ALL paths go through the 8B, these should be promoted to config keys so verbosity can be tuned without source edits.

7. **`ULTRON_GAMING_PERSONA` in llm_prompts.py:48** hardcodes the "~25 words / one sentence" directive. For a verbosity-level system, this would become a template with a `{verbosity_directive}` slot.

8. **`build_relay_line()` `rephrase` arg** (`relay_speech.py:6017`) gates all LLM access on the relay path. Ultron 1.0's "route ALL through 8B" pivot means `rephrase=True` permanently, or better: restructure so intent detection populates a prompt template and the 8B always runs.

---

## Retire-not-remove candidates (u1.0)

| Candidate | Location | Retire-not-remove rationale |
|-----------|----------|-----------------------------|
| `_flavor_off_response()` + `_FO_*` pools | relay_speech.py:5712–5843 | Repurpose: become the "terse/minimal" exemplar pools for the 8B; the curated lines are still valuable as in-context examples |
| Hardcoded snap paths (clutch, consolation, praise, nice_try, agent_select, thank_you) | relay_speech.py:6100–6280 | Repurpose as ROUTERS (intent detectors) + exemplar injectors; the deterministic line pools become in-context examples for the 8B |
| `SNAP_REGISTRY` / `TARGET_SNAP_REGISTRY` | voice_lines.py:330–375 | Repurpose as the data-driven "intent -> prompt template" map |
| `_RELAY_SAMPLING` dict | relay_speech.py:2507 | Retire the tight 56-token cap; replace with verbosity-level-specific sampling params exposed in config |
| `match_flavor_toggle()` + `_FLAVOR_OFF_RE` / `_FLAVOR_ON_RE` | relay_speech.py:1167; voice_lines.py | Repurpose: the binary flavor toggle becomes "verbosity level" toggle; keep the voice command infrastructure |
| `_thinking_mode_enabled` / `match_thinking_toggle()` | relay_speech.py:1197–1235 | Retire: in Ultron 1.0, thinking mode is always ON (8B is always consulted); flag can be retained as an emergency snap-only override |
| `apply_brevity_hint()` | response_style.py:272 | Repurpose: the 3-class per-utterance hint becomes the "no/low/high" selector; the `[Style: ...]` format carries forward |
| `ULTRON_GAMING_PERSONA` hardcoded length directive | llm_prompts.py:48 | Retire the inline "~25 words" directive; move to a template with verbosity-level slot |

---

## Gotchas

1. **`_flavor_tails_enabled` is read-at-import from env.** `relay_speech.py:1136` runs `os.getenv("KENNING_FLAVOR_TAILS", "1")` at module import time. `__main__.py:111` sets `os.environ.setdefault("KENNING_FLAVOR_TAILS", "0")` BEFORE importing the orchestrator (which lazily imports relay_speech). The order matters: if relay_speech is imported before `__main__` sets the env, the default `"1"` (tails ON) takes effect and `__main__`'s override has no effect.

2. **Flavor-OFF categories are NOT exhaustive.** `_flavor_off_response()` returns `None` for categories not in its dispatch table — tactical callouts (enemy spotted, damage, site, etc.) then fall through to the normal rendering, which for those categories is DETERMINISTIC (no tail was ever added by `_join_tail()` because the callout-builder constructs the head + tail separately). So "Sova hit 84" with flavor OFF produces the same output as flavor ON for the tactical content but drops the flavor line. This is correct behavior but can be confusing.

3. **`_cap_sentences(max_sentences=2)` only applies to LLM output.** Curated set-pieces (greeting, identity, farewell, agent-select) return BEFORE this cap is reached (early return at `relay_speech.py:6063–6277`). The cap only touches model-generated output on the relay path.

4. **The relay `max_tokens=56` is hardcoded** in `_RELAY_SAMPLING` and is NOT exposed in config.yaml or the settings GUI. Changing it requires a source edit.

5. **`apply_brevity_hint()` is idempotent but does NOT compose.** If the user says something that matches BOTH `is_factual_question` and `is_brief_question`, only the factual hint fires (precedence: procedural > factual > brief). A text that already starts with `[Style:` is passed through unchanged.

6. **The `[Tone: ...]` directive from `temperament_hint()` does NOT suppress `[Style: ...]`.** Both can be prepended to the same user message. The LLM sees both; behavior depends on the model's ability to follow two competing style instructions. The prefixes differ deliberately (`[Tone:` vs `[Style:`) so the idempotence guards don't interfere.

7. **Kokoro `speed` config.yaml shows `1.3` in the TUNING SUMMARY comment** (`config.yaml:40`) but the actual `kokoro:` subsection sets `speed: 1.0` (`config.yaml:1200`). The comment is stale. In-model prosody shaping (`dur_final_factor`, etc.) provides the equivalent of the former 1.3x speed nudge.

8. **`piper_length_scale=1.15` in config.yaml applies ONLY to the `piper_rvc` engine.** Kokoro does not read this field. It has no effect when `tts.engine = "kokoro"` (the current default).

9. **Thinking mode's independence from flavor tails.** The comment at `relay_speech.py:1195` explicitly says "Independent of the flavor-tails toggle (tails = persona suffix on a snap; thinking = LLM on/off)." This means you can have: flavor-ON + thinking-ON (LLM output with tails), flavor-ON + thinking-OFF (deterministic with tails), flavor-OFF + thinking-ON (LLM output without tails), flavor-OFF + thinking-OFF (deterministic without tails — the competitive gaming default).

---

## Open questions

1. **Is `apply_temperament()` called in the live gaming turn path?** The grep shows it defined in `evolution/personality.py` and referenced in `evolution/models.py`, but the orchestrator's main conversational turn flow was not observed calling it. It may only be active when `evolution.enabled=true`.

2. **Per-command verbosity routing for Ultron 1.0.** "Sova hit 84" should be minimal (one fact, no tail). "Think and respond about Sokovia" should be moderate (1–2 sentences). A freeform ramble should allow more. There is no current mechanism to pass a "verbosity budget" from the intent detector to the prompt template. Where should this live — in `RelayCommand`, in the `SnapRule`/prompt template, or in a separate verbosity-level context object?

3. **Flavor tail pools as in-context exemplars for the 8B.** The `AGENT_FLAVOR` (1,628 curated entries) and `_FO_*` compact lines are natural exemplar sources. What injection strategy should Ultron 1.0 use — pre-filled template slots, a retrieval step keyed on intent+agent, or a fixed static block?

4. **Should `_RELAY_SAMPLING` and `_ANSWER_SAMPLING` be promoted to config?** For Ultron 1.0 where the 8B is always consulted, per-verbosity-level sampling parameters (temperature, top_p, max_tokens, stop sequences) should be config-driven. Is there a preferred verbosity-level schema — e.g. `relay.verbosity.minimal.max_tokens`, `relay.verbosity.low.max_tokens`, `relay.verbosity.high.max_tokens`?

5. **How does "separate tail on/off" interact with verbosity levels in Ultron 1.0?** The pivot description says "flavor becomes no/low/high verbosity (prompt-driven) + a separate flavor-tail on/off." Currently flavor-OFF replaces the entire output with compact alternatives, not just drops the tail. Does the Ultron 1.0 design intend: (a) verbosity level controls LLM prompt length directive, and the tail is a separate addendum gated by tail-on/off, or (b) verbosity level IS the response style and "tail" means something different (e.g. the 1,628-entry AGENT_FLAVOR contextual commentary appended as a second sentence)?

6. **How is the 8B's extended context window used for exemplar injection?** The current 3B relay prompt (`_build_rephrase_prompt`) is ~120 lines with slots for `task`/`addressee`/`by_name`. The 8B has more capacity. Will the exemplar injection be per-turn (inject the 10 most relevant flavor lines per call) or pre-cached in the system prompt?
