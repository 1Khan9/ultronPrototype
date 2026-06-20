# A11: Agent vocab libraries, aggregates & ingestion pipelines

## Overview

The Kenning/Ultron system maintains several parallel curated libraries of voice lines and
flavor content. These libraries are the substrate the Ultron 1.0 architect must preserve and
extend. There are three distinct tiers:

1. **Agent-contextual flavor tails** (`_agent_flavor.py`) — 1,628 TailEntry objects across 28
   Valorant agents, 16 tactical situations, tagged by location/damage/ability for fine
   selection. Script-generated + hand-curated.

2. **Generic/persona pools** (`_ultron_pools.py`, `_ultron_setpieces.py`, `_ultron_social.py`,
   `_ultron_commands.py`, `_ultron_identity.py`, `_ultron_answer.py`) — standalone curated
   response pools organized by intent category. Hand-authored only.

3. **User-curated corpora on disk** (`data/relay_fun_facts.txt`, `data/relay_roasts.txt`) —
   plain-text files re-read at runtime; trivially extensible by the user.

An **aggregate module** (`voice_lines.py`) re-exports all pools under one import surface and
provides the SNAP_REGISTRY / TARGET_SNAP_REGISTRY data-driven dispatch tables. A second
aggregate (`llm_prompts.py`) holds all system prompts. A third aggregate (`_command_exemplars.py`)
holds the semantic router family exemplars. The **golden-digest harness**
(`scripts/_voice_lines_verify.py` + `tests/test_voice_lines_golden.py`) guards all three aggregates
against accidental content changes.

---

## Files & key symbols (path:line tables)

### Core source libraries

| File | Lines | Key symbols |
|------|-------|-------------|
| `src/kenning/audio/_agent_flavor.py` | 2611 | `AGENT_FLAVOR: dict[str, dict[str, list[TailEntry]]]` — 28 agents × 16 situations × tags |
| `src/kenning/audio/_tail_schema.py` | 400 | `TailEntry`, `AGENT_GENDER`, `Sit`, `ENEMY_SITUATIONS`, `loc_class()`, `dmg_level_tag()`, `ability_tag()`, `lint_agent_flavor()` |
| `src/kenning/audio/_ultron_pools.py` | 471 | `_FLAVOR_ENEMY`, `_FLAVOR_ULT`, `_FLAVOR_DAMAGE`, `_FLAVOR_UTILITY`, `_FLAVOR_CAREFUL`, `_FLAVOR_COMMAND`, `_FLAVOR_SELF` (all `tuple[str,...]`) |
| `src/kenning/audio/_ultron_setpieces.py` | 351 | `DEFAULT_GREETING_LINES`, `DEFAULT_VICTORY_LINES`, `DEFAULT_DEFEAT_LINES`, `DEFAULT_FAREWELL_LINES`, `DEFAULT_IDENTITY_LINES`, `DEFAULT_CONSOLATION_LINES`, `DEFAULT_PRAISE_LINES`, `DEFAULT_CLUTCH_LINES`, `DEFAULT_ENCOURAGEMENT_LINES` |
| `src/kenning/audio/_ultron_commands.py` | 3160 | `COMMAND_RESPONSES: dict[str, tuple[str,...]]` (84 keys × ~30-40 lines each), `COMMAND_SCOPE`, `COMMAND_SLOT` |
| `src/kenning/audio/_ultron_social.py` | 675 | `SOCIAL_POOLS: dict[str, dict[str, tuple]]` (11 categories × team/named), `classify_social_reaction()` |
| `src/kenning/audio/_ultron_identity.py` | 379 | `IDENTITY_POOLS: dict[str, tuple[str,...]]` (8 categories × ~30 lines), `classify_identity_question()`, `is_model_leak_probe()` |
| `src/kenning/audio/_ultron_answer.py` | 316 | `MARVEL_CANON`, `marvel_topic()`, `THINK_RESPOND_SUFFIX_RE`, `classify_answer_subtype()`, `extract_answer_slots()`, `build_answer_call()`, `is_meta_leak()`, `_ANSWER_SAMPLING` |
| `src/kenning/audio/voice_lines.py` | 376 | `SNAP_REGISTRY: tuple[SnapRule,...]`, `TARGET_SNAP_REGISTRY: tuple[TargetSnapRule,...]`, `DEFAULT_ROAST_LINES`, `DEFAULT_FUN_FACTS`, `_FLAVOR_OFF_RE`, `_FLAVOR_ON_RE`, `_HELLO_RE`, `_ASK_DAY_RE`, `_CLUTCH_RE`, `_NICE_TRY_RE`, `_PRAISE_RE`, `_CONSOLATION_RE`, `_THANK_YOU_RE`, `_AGENT_SELECT_FULL_RE` |
| `src/kenning/audio/llm_prompts.py` | 127 | `ULTRON_GAMING_PERSONA`, `ANSWER_PERSONA_CORE`, `ANSWER_MARVEL_RULES`, `ANSWER_THINK_RULES`, `ANSWER_SYSTEM_FOR: dict[str,str]` |
| `src/kenning/audio/_command_exemplars.py` | 247 | `FAMILIES: dict[str, list[str]]`, `ABSTAIN_FAMILIES`, `DETERMINISTIC_FAMILIES` |

### User-curated corpora on disk

| File | Lines | Format |
|------|-------|--------|
| `data/relay_fun_facts.txt` | 1019 | One fact per line; `#` = comment; ~1000 facts, re-read at runtime |
| `data/relay_roasts.txt` | 6 | Same format; currently 1 roast line ("I may be an AI, but you are a bot.") + header comments |

### Ingestion / tooling scripts

| File | Purpose | Input | Output |
|------|---------|-------|--------|
| `scripts/flavor_gen/integrate_tails.py` | Board JSON -> `_agent_flavor.py`; lint+dedup+merge with existing | `<board_output.json>` (sets format) | `src/kenning/audio/_agent_flavor.py` |
| `scripts/flavor_gen/apply_curated.py` | CURATED hand-overrides -> `_agent_flavor.py`; per-cell replace | `curated_overrides.py` (imported) | `src/kenning/audio/_agent_flavor.py` |
| `scripts/flavor_gen/apply_cuts.py` | Audit-board cut list -> removes tail texts from `_agent_flavor.py` | `<audit_output.json>` (results format) | `src/kenning/audio/_agent_flavor.py` |
| `scripts/flavor_gen/curated_overrides.py` | CURATED hand-authored data for 29 agents | (hand-edited) | imported by `apply_curated.py` |
| `scripts/flavor_audit/lint_tails.py` | Pre-commit deterministic lint: word cap, gender, quotes, floor | `_agent_flavor.py` (import) | stdout; exit code |
| `scripts/_voice_lines_verify.py` | Baseline/check digest of all curated pools + regexes + prompts | env `KENNING_VOICE_LINES_DIGEST` | `logs/_voice_lines_digest.json` or diff |
| `scripts/build_common_words.py` | Fetches Google frequency list -> `_common_words.py` | URL (public domain) | `src/kenning/audio/_common_words.py` |

### Test fixtures and vocab packs

| File | Role |
|------|------|
| `tests/test_voice_lines_golden.py` | CI gate: runs `_voice_lines_verify.py check` under PYTHONHASHSEED=0 vs committed golden |
| `tests/data/voice_lines_golden_digest.json` | Version-controlled golden; must be re-blessed when data changes intentionally |
| `tests/audio/test_flavor_lint.py` | Structural lint gate for `AGENT_FLAVOR` via `lint_agent_flavor()` |
| `scripts/relay_test/vocab_packs/` | ~50 test corpus packs (ITEMS lists) organized by domain; used by corpus sweep scripts |

---

## Control/data flow

### Agent flavor tail selection (runtime)

```
Callout arrives (agent + situation + loc + dmg + ability slots)
        |
        v
_tail_schema.build_active_tags(loc, dmg, ability)  ->  frozenset of tags
        |
        v
AGENT_FLAVOR[agent][situation]  (coarse route: 28 agents × 16 situations)
        |
        v
4-tier tag filter (relay_speech._flavor_ctx):
  Tier 1: entries whose tags are a SUBSET of active_tags (exact sub-context)
  Tier 2: entries whose tags INTERSECT active_tags (partial)
  Tier 3: tagless entries (base pool)
  Tier 4: any entry (last resort)
        |
        v
LRU anti-repeat ring (per-agent, per-situation, size ~8)
        |
        v
TailEntry.text appended to callout ("Two B main. <tail>")
```

### Generic pool dispatch (runtime, relay_speech)

```
Relay payload
        |
        v
SNAP_REGISTRY (voice_lines.py:330) -- FIRST matching SnapRule wins
  SnapRule.kind == "pool"      -> random from SnapRule.lines (anti-repeat)
  SnapRule.kind == "head_tail" -> echo regex group 1 + random from SnapRule.tails
        |
        v (if no SNAP_REGISTRY match)
hardcoded snap functions (relay_speech):
  _try_clutch_snap, _try_nice_try_snap, etc. (safety net, same logic)
```

### Target snaps (voice_lines.TARGET_SNAP_REGISTRY)

```
Relay payload
        |
        v
TARGET_SNAP_REGISTRY (voice_lines.py:363) -- ordered, first match wins
  captures group "target" via regex -> _resolve_hello_target() ->
    "team" -> TargetSnapRule.team_lines[random]
    "<Agent>" -> TargetSnapRule.agent_templates[random].format(name=Agent)
```

### Ingestion pipeline (offline, scriptable)

```
Tail-gen board output (JSON)
        |
        v
scripts/flavor_gen/integrate_tails.py
  Lint (word cap <=8; gender check; quote strip)
  Dedup (within-cell + cross-agent)
  Merge (generated INTO existing: tagless base kept, generated adds tagged variants)
        |
        v
src/kenning/audio/_agent_flavor.py  (overwritten)

--- ALTERNATIVELY ---

scripts/flavor_gen/curated_overrides.py  (hand-edit CURATED dict)
        |
        v
scripts/flavor_gen/apply_curated.py  (replaces cells per-agent/situation)
        |
        v
src/kenning/audio/_agent_flavor.py  (overwritten)

--- POST-EDIT (both paths) ---

scripts/flavor_audit/lint_tails.py  (hard: word cap, gender, quotes, floor; soft: tactical-start)
tests/audio/test_flavor_lint.py     (pytest gate; calls lint_agent_flavor())
PYTHONHASHSEED=0 scripts/_voice_lines_verify.py baseline  (re-bless golden if content changed)
tests/test_voice_lines_golden.py    (CI gate)
```

### Voice-line data ownership (aggregate vs source)

```
voice_lines.py                       (AGGREGATE -- single import surface)
  re-exports FROM:
    _ultron_setpieces.py             (DEFAULT_*_LINES: setpieces)
    _agent_flavor.py                 (AGENT_FLAVOR)
  physically holds:
    social snap regexes + tails (_HELLO_RE, _NICE_TRY_TAILS, ...)
    SNAP_REGISTRY, TARGET_SNAP_REGISTRY (data-driven dispatch tables)
    DEFAULT_ROAST_LINES, DEFAULT_FUN_FACTS (fallback tuples for disk corpora)

llm_prompts.py                       (AGGREGATE -- all LLM system prompts)
  physically holds:
    ULTRON_GAMING_PERSONA
    ANSWER_PERSONA_CORE + ANSWER_MARVEL_RULES + ANSWER_THINK_RULES -> ANSWER_SYSTEM_FOR

INDEXED ONLY (not imported into aggregates; edit at source):
  _ultron_commands.py    (COMMAND_RESPONSES)
  _ultron_social.py      (SOCIAL_POOLS)
  _ultron_identity.py    (IDENTITY_POOLS)
  _ultron_pools.py       (_FLAVOR_* generic callout tails)
  _ultron_answer.py      (MARVEL_CANON, is_meta_leak, build_answer_call)
```

---

## Key findings

1. **1,628 curated TailEntry objects across 28 agents** (`_agent_flavor.py`), each carrying
   `frozenset` tags from three namespaces (`loc:`, `dmg:`, `ability:`). The 16 situation keys
   are defined as string constants in `_tail_schema.Sit`. The tag-filter + LRU selection chain
   is the primary flavor "voice" mechanism. (Source: `_tail_schema.py:55-77`; count from
   grep `TailEntry` = 1631 lines including imports.)

2. **`COMMAND_RESPONSES` has 84 command keys × ~30-40 lines each** (`_ultron_commands.py:104`),
   making it by far the largest pool. Lines use `{name}`, `{site}`, `{agent}` slots for runtime
   substitution. Scope is team or named (via `COMMAND_SCOPE`), slot is agent/site/both (via
   `COMMAND_SLOT`).

3. **SNAP_REGISTRY + TARGET_SNAP_REGISTRY are the extension points for new snap commands**
   (`voice_lines.py:330-375`). A `SnapRule` or `TargetSnapRule` is a frozen dataclass;
   appending one to the registry adds a new deterministic snap with zero pipeline code.
   Gated by env `KENNING_SNAP_REGISTRY` (default `"1"` = ON).

4. **`voice_lines.py` is the import surface for all output-side data** (social snaps,
   setpieces, flavor, snap registries). `llm_prompts.py` is the import surface for all
   LLM prompts. These two aggregates plus `_command_exemplars.py` are the three files the
   digest harness gates.

5. **Golden digest CI gate** (`tests/test_voice_lines_golden.py`) runs `_voice_lines_verify.py
   check` under `PYTHONHASHSEED=0` against `tests/data/voice_lines_golden_digest.json`.
   The digest covers: tuples/lists of str, re.Pattern objects, dict (repr-stable), numeric
   knobs, frozensets of str, dataclass sequences. Any accidental content edit fails CI.
   Re-blessing: `PYTHONHASHSEED=0 KENNING_VOICE_LINES_DIGEST=tests/data/voice_lines_golden_digest.json
   python scripts/_voice_lines_verify.py baseline`.

6. **`data/relay_fun_facts.txt` is re-read on every request** (not at boot), so it can be
   extended live. ~1,000 facts spanning 18 topic domains. The disk corpus format:
   one fact per line, `#` = comment, blank lines OK.

7. **`data/relay_roasts.txt` has only one non-comment line** ("I may be an AI, but you are a
   bot."). The format is identical to fun_facts and is trivially extensible.

8. **Agent gender is machine-enforced** via `AGENT_GENDER` (`_tail_schema.py:85-93`), 28 agents
   mapped to `she/he/they/it`. The lint script and flavor-lint pytest gate reject wrong-gender
   pronouns hard. `Miks` and `Veto` are custom agents also in the map.

9. **`_command_exemplars.py` provides the semantic router's training set** — five families
   (`team_callout`, `spotify`, `identity`, `desktop_refuse`, `conversational`) with explicit
   per-family example lists. `ABSTAIN_FAMILIES = {"conversational"}`. The `spotify` family
   exists only as an embedding-space separator (Spotify hits from its exact matcher; Spotify
   exemplars prevent music commands from routing to team_callout). These lists are embedded
   once at startup; editing them is cheap (no recompile, just restart).

10. **The `_ANSWER_SAMPLING` dict** (`_ultron_answer.py:239-248`) contains constrained sampling
    parameters for the LLM answer path: `max_tokens=80`, `temperature=0.85`, `min_p=0.08`,
    explicit stop sequences. These are the only explicit per-path LLM knobs in the library
    layer; the main relay rephrase path's sampling lives in `relay_speech.py` (not yet
    extracted to `llm_prompts.py`).

11. **The social pools in `_ultron_social.py`** are assembled via a defensive import of
    `_ultron_commands.py::COMMAND_RESPONSES` (lines 530-538): the team-scope compliment pools
    delegate to the named pools in `_ultron_commands.py`, with local tuples as fallback if
    the key is ever renamed.

12. **Vocab packs (50 files)** in `scripts/relay_test/vocab_packs/` each export an `ITEMS`
    list used by the corpus sweep scripts. They are domain-segregated (agents/abilities,
    callouts/maps, economy, directives, etc.) and also include stress-test and variant packs.
    They are test fixtures, not runtime data.

---

## Flags & config

| Env var / key | Default | Effect |
|---------------|---------|--------|
| `KENNING_SNAP_REGISTRY` | `"1"` (ON) | Gates `SNAP_REGISTRY` + `TARGET_SNAP_REGISTRY` dispatch in `relay_speech._apply_snap_registry`. `"0"/"false"/"off"` falls through to hardcoded snap functions. |
| `KENNING_FLAVOR_TAILS` | `"0"` at lean boot (set by `kenning/__main__.py:111`); `"1"` when user enables | Global flavor tail toggle. `_flavor_tails_enabled` is a module-level bool in `relay_speech`. **Skipped by the golden digest** (runtime state, not curated content). |
| `KENNING_WAKE_TRIM_TO_SPEECH` | `"1"` (ON) | VAD-based wake-word audio trim in orchestrator. Not directly a vocab flag. |
| `KENNING_RELAY_TEAM_DSP` | `"1"` (ON) | Team-path DSP shaping in `relay_speech._shape_for_team`. Not directly a vocab flag. |
| `KENNING_VOICE_LINES_DIGEST` | `"logs/_voice_lines_digest.json"` | Path for the verify harness; overridden to `tests/data/voice_lines_golden_digest.json` in CI. |
| `KENNING_SNAP_REGISTRY` (in `_apply_target_snap_registry`) | `"1"` | Same gate, checked in three separate places in `relay_speech.py` (payload snaps, hello, agent-select). |

Config keys in `config.yaml`:
- `audio.llm` (system prompt) — the base "You are Kenning" desktop persona; never loaded in lean gaming.
- `addressing.follow_up_enabled` — default `false` (wake word required).

---

## Extension points

### Add a new deterministic payload snap

Append a `SnapRule` to `SNAP_REGISTRY` in `voice_lines.py:330`. Parameters:
- `name`: string (also used as `RelayCommand.directive`)
- `match`: `re.Pattern` matching the relay payload
- `kind`: `"pool"` (random from `lines`) or `"head_tail"` (echo match group 1 + random from `tails`)
- `lines`: tuple of response strings
- `tails`: tuple of follow-on strings

Re-bless the golden digest after adding. **Precedence: first match wins; append only if no
earlier rule claims the trigger.**

### Add a new target snap ("say X to <team|agent>")

Append a `TargetSnapRule` to `TARGET_SNAP_REGISTRY` in `voice_lines.py:363`. Parameters:
- `name`: directive name
- `match`: pattern with group `"target"`
- `team_lines`: tuple (rendered when target = team)
- `agent_templates`: tuple with `{name}` slot
- `skip_if_contains`: tuple of disqualifying substrings (optional)

### Add agent-flavor tails (new lines)

Two paths:
1. **Hand-curate**: add to `scripts/flavor_gen/curated_overrides.py::CURATED[agent][situation]`
   as `(text, (tags...))` tuples; run `apply_curated.py`; run lint; re-bless golden.
2. **Board-generate**: run a tail-gen board, save JSON, run `integrate_tails.py <output.json>`;
   the script lints (word cap, gender, quotes) + deduplicates + merges tagged variants with
   existing tagless base; then run lint + re-bless golden.

### Add a command response (new `COMMAND_RESPONSES` key)

Edit `_ultron_commands.py`. Add the key to `COMMAND_SCOPE` (team/named) and optionally
`COMMAND_SLOT` (agent/site/both). Add the key to `COMMAND_RESPONSES` as a tuple of response
strings. Re-bless golden.

### Add semantic router exemplars

Edit `_command_exemplars.py`. Add lines to the appropriate family list (or a new family key in
`FAMILIES`). If adding a new family that should route deterministically, add it to
`DETERMINISTIC_FAMILIES`. If it should route to the LLM, add it to `ABSTAIN_FAMILIES`.
No recompile needed; exemplars are embedded at orchestrator startup. Re-bless golden.

### Add fun facts or roast lines

Edit `data/relay_fun_facts.txt` or `data/relay_roasts.txt` directly. One line per entry,
`#` for comments. **These files are re-read at runtime** (every request for fun facts, every
roast request), so no restart needed.

### Add LLM system prompts / persona copy

Edit `llm_prompts.py`. Update `ULTRON_GAMING_PERSONA` (gaming conversational turns),
`ANSWER_PERSONA_CORE`/`ANSWER_MARVEL_RULES`/`ANSWER_THINK_RULES` (adaptive answer pipeline),
or `ANSWER_SYSTEM_FOR` (the compiled per-type system prompt map). Re-bless golden.

### Add a new agent to the flavor library

1. Add the agent to `AGENT_GENDER` in `_tail_schema.py:85-93` with the correct pronoun.
2. Add cells to `AGENT_FLAVOR` in `_agent_flavor.py` or add to `curated_overrides.py` and
   run `apply_curated.py`.
3. Run `lint_tails.py`. Re-bless golden.

---

## Retire-not-remove candidates (u1.0)

In the Ultron 1.0 pivot (all responses routed through 8B LLM), the DETERMINISTIC snaps and
response pools are repurposed as **routers** (detect intent, choose template, inject exemplars)
rather than final outputs. The following are candidates to retire-as-dispatch (keep in place,
no longer used as primary output):

| Candidate | Current role | U1.0 repurposed role |
|-----------|-------------|----------------------|
| `SNAP_REGISTRY` / `TARGET_SNAP_REGISTRY` | Primary deterministic dispatch | Intent router: pattern match -> choose LLM prompt template; inject matched snap as in-context exemplar |
| `COMMAND_RESPONSES` (84 keys) | Final deterministic output | Exemplar bank: inject 2-3 matched lines as examples in the 8B prompt ("respond like this"); keep for coverage |
| `SOCIAL_POOLS` (11 categories) | Final deterministic social response | In-context exemplars for 8B social turns |
| `IDENTITY_POOLS` (8 categories) | Final deterministic identity answer | In-context exemplars for 8B identity turns; `is_model_leak_probe()` stays as a HARD gate (never to LLM) |
| `_FLAVOR_*` pools in `_ultron_pools.py` | Appended after callout | Flavor verbosity: no/low/high = no tail / short pool tail / 8B-generated |
| `AGENT_FLAVOR` (1628 entries) | Per-callout tail selection | Stay as fine-grained in-context exemplar bank; inject best-match tail as example in the 8B prompt |
| `build_answer_call()` / `_ANSWER_SAMPLING` | Adaptive LLM path for Marvel/think | Subsumes into a single 8B call with per-intent system prompt; the sampling dict is the template for 8B call params |
| Hardcoded fallback snaps in `relay_speech` | Safety net when SNAP_REGISTRY off | Retire entirely; 8B handles |
| `_command_exemplars.py::FAMILIES` | Coarse semantic routing | Stays as intent-family classifier; becomes the "which template?" decision |

**Hard-keep (do NOT retire):**
- `is_model_leak_probe()` + `_MODEL_LEAK` pool — anticheat hard gate; must intercept before any LLM call.
- `AGENT_GENDER` — gender-enforcement for any generated/curated content; critical for quality gate.
- `lint_agent_flavor()` — structural integrity gate; keep for all future curations.
- Golden digest CI gate — keep and extend to cover new aggregates.
- `data/relay_fun_facts.txt` / `data/relay_roasts.txt` — user-extensible corpora; keep disk format.
- `_tail_schema.TailEntry`, `loc_class()`, `dmg_level_tag()`, `ability_tag()` — tag infrastructure; used for in-context slot injection in U1.0.

---

## Gotchas

1. **`voice_lines.py` re-exports vs. physically holds**: `DEFAULT_*_LINES` are imported FROM
   `_ultron_setpieces.py` (edit there); `AGENT_FLAVOR` is imported FROM `_agent_flavor.py`
   (edit there). But `_HELLO_RE`, `_NICE_TRY_TAILS`, `SNAP_REGISTRY`, etc. are PHYSICALLY
   in `voice_lines.py` (edit there). The module-level comment (`voice_lines.py:1-51`) is the
   authoritative index.

2. **Golden digest requires `PYTHONHASHSEED=0`**: some regexes are compiled from `set`
   iteration (order-unstable across runs). The baseline and check must BOTH use
   `PYTHONHASHSEED=0`. The test runs in a subprocess for this reason. Forgetting this when
   re-blessing produces a flapping golden.

3. **`_flavor_tails_enabled` is SKIPPED by the digest** (`_SKIP_RUNTIME_STATE` in verify.py)
   because it toggles at runtime via the `KENNING_FLAVOR_TAILS` env var. Do not add other
   runtime-state module globals to the digest without adding them to `_SKIP_RUNTIME_STATE`.

4. **`SNAP_REGISTRY` is gated in three separate places** in `relay_speech.py` (payload snaps,
   hello/target snaps, agent-select), all checking `KENNING_SNAP_REGISTRY`. Disabling it
   falls back to hardcoded logic, not an error.

5. **`_ultron_commands.py` is indexed but NOT imported into `voice_lines.py`**: it is too
   large to import early; `relay_speech.py` imports it directly. The same is true for
   `_ultron_social.py`, `_ultron_identity.py`, `_ultron_pools.py`. `_ultron_answer.py` imports
   its prompts FROM `llm_prompts.py` (aliases; relocated 2026-06-18 Part B).

6. **`integrate_tails.py` has a MIN_CELL floor of 4 for `spotted` base tails** in
   `apply_cuts.py` (the cut script also enforces this). If curating leaves fewer than 4
   tagless base tails in `spotted`, cut lines are restored. The lint gate enforces the same
   floor as `_MIN_BASE = 4` for the `spotted` situation specifically.

7. **Situation taxonomy has 16 keys** (from 4 in the original library). The 12 new keys
   (`moving`, `planting`, `defusing`, `rotating`, `saving`, `falling_back`, `peeking`,
   `holding`, `lurking`, `trading`, `last_alive`, `near_death`) may have sparse or empty
   cells in `_agent_flavor.py` for some agents (the curated_overrides added them only for
   some). The runtime falls through gracefully.

8. **`data/relay_roasts.txt` has only 1 line**. The runtime LRU anti-repeat will always serve
   the same line until more are added. The file is trivially extensible.

9. **The `_rephrase_prompt` (relay LLM system prompt)** is NOT yet in `llm_prompts.py` — it
   remains in `relay_speech.py` as a large f-string template (~120 lines). The `llm_prompts.py`
   module notes this as a follow-up relocation. Editing the relay persona requires editing
   `relay_speech.py` directly.

10. **`_ultron_social.py:530-538`** has a defensive import of `_ultron_commands.py` at module
    load time (wrapped in try/except). If `COMMAND_RESPONSES` keys are ever renamed, the
    `_cmd()` function falls back to the locally-authored pool tuple rather than crashing.

---

## Open questions

1. **U1.0 in-context exemplar selection**: which pool entries make the best exemplars for the
   8B? Should the SNAP_REGISTRY order determine which exemplar is injected, or should there
   be a semantic match against the live utterance?

2. **Flavor verbosity levels (no/low/high)**: the current binary toggle (`KENNING_FLAVOR_TAILS`)
   maps to `_FLAVOR_*` pools or `AGENT_FLAVOR` tails. In U1.0, "high verbosity" presumably
   means 8B-generated tails. What is the U1.0 design for "low" (a curated pool tail injected
   as a prefix to the 8B call? spoken separately before the 8B output?)?

3. **`data/relay_roasts.txt` expansion**: the file has a placeholder. Should it be populated
   before U1.0? The architecture note says "keep user-extensible disk corpora" — is there a
   target size?

4. **The relay rephrase system prompt** (in `relay_speech.py`) is the largest prompt in the
   pipeline and is not yet in `llm_prompts.py`. Should it be extracted to `llm_prompts.py` in
   U1.0, or will the 8B's prompt design supersede it entirely?

5. **`curated_overrides.py` has 29 agents** vs `AGENT_GENDER` which has 28. The curated
   overrides include `Miks` and `Veto` (custom agents). Confirm these are intentional
   in-universe agents and not a leftover from an earlier naming scheme.

6. **`_command_exemplars.py`'s `spotify` family**: currently the Spotify exemplars only exist
   as a negative-space guard (prevent music commands from routing to team_callout). In U1.0,
   if Spotify commands are still handled by a dedicated path, this family design is unchanged.
   If Spotify is removed, the exemplars become dead weight.

7. **Anti-repeat ring sizing**: the LRU ring size for agent flavor tails and for the setpiece
   pools is not defined in these files (it is in `relay_speech.py`). Is there a planned change
   to ring size for U1.0?

8. **How to add Valorant agents not yet in `AGENT_GENDER`**: the schema (`_tail_schema.py:85`)
   only has agents through the 2026-06-19 roster. A new Valorant agent release would require
   editing `AGENT_GENDER` and `curated_overrides.py` before any flavor generation.

9. **`voice_lines.py` import graph**: the module imports `_ultron_setpieces` and
   `_agent_flavor` at module load. For U1.0, if `AGENT_FLAVOR` grows significantly (e.g. all
   agents curated to all 16 situations), will the import-time cost of loading 2600+ line
   module be significant? (Currently 2611 lines, loads fine.)
