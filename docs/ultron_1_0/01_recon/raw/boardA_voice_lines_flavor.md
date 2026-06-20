# A3: Voice-lines aggregate & the 1628-tail flavor library

Recon date: 2026-06-20. Agent: claude-sonnet-4-6 (infallible-kepler worktree).
All line citations are repo-root-relative paths at the HEAD of branch
`claude/infallible-kepler-0a865d`.

---

## Overview

The voice-lines system is a **curated-data layer** that sits between the
speech recognizer and the TTS engine. It supplies every pre-written Ultron
line: social snaps, set-pieces (greeting / victory / defeat / farewell),
tactical flavor tails, identity deflections, social-reaction pools, and the
1,628-entry per-agent contextual contempt library. The design philosophy is:

- **Single import surface**: any consumer does `from kenning.audio.voice_lines
  import X` regardless of which sub-file the data physically lives in.
- **Pure data, no dispatch logic**: the aggregate holds DATA only; routing /
  picking / LRU lives in `relay_speech.py` and friends.
- **Byte-identical relocation**: the 2026-06-18 Part B refactor proved via
  `scripts/_voice_lines_verify.py` (PYTHONHASHSEED=0 digest) that moving data
  from `relay_speech.py` into the aggregate changed zero behaviour.
- **Fail-open imports**: every large library (`AGENT_FLAVOR`, `MULTI_FLAVOR`,
  `_agent_flavor`, etc.) is imported inside a `try/except` in both the
  aggregate and `relay_speech.py`, so the pipeline never hard-fails on a
  missing optional module.

---

## Files & key symbols

### `src/kenning/audio/voice_lines.py` — THE AGGREGATE (376 lines)

| Symbol | Kind | Description |
|--------|------|-------------|
| `_FLAVOR_OFF_RE` / `_FLAVOR_ON_RE` | `re.Pattern` | Strict phrasings for voice flavor-tail toggle ("flavor off" / "flavor on"). Lines 91–109. |
| `_FLAVOR_OFF_MISHEAR_RE` / `_FLAVOR_ON_MISHEAR_RE` | `re.Pattern` | Whisper-mishear fallbacks for the toggle ("save her off" → off). Lines 129–138. |
| `_HELLO_RE` | `re.Pattern` | Matches "say hello to [target]"; captures named group `target`. Line 142. |
| `_HELLO_TEAM_WORDS` | `frozenset[str]` | Team-scope resolver: maps "squad", "boys", "everyone", etc. → team. Line 149. |
| `_ASK_DAY_RE` | `re.Pattern` | "ask <target> how their day is going" + many paraphrases. Line 157. |
| `_ASK_DAY_TEAM_LINES` | `tuple[str, ...]` | 8 curated team day-check lines. Line 168. |
| `_ASK_DAY_AGENT_TEMPLATES` | `tuple[str, ...]` | 6 `{name}`-template agent day-check lines. Line 178. |
| `_CONSOLATION_RE` | `re.Pattern` | "nice try" / "unlucky" / "so close" / "almost". Line 188. |
| `_PRAISE_RE` | `re.Pattern` | "good half" / "nice clutch" / "gg" / "let's go". Line 193. |
| `_NICE_TRY_RE` | `re.Pattern` | Captures head phrase ("nice try"); kind=head_tail. Line 202. |
| `_NICE_TRY_TAILS` | `tuple[str, ...]` | 10 cold Ultron tails for nice-try. Line 206. |
| `_CLUTCH_RE` | `re.Pattern` | "I got this" / "I'll clutch" / "leave it to me" etc. Line 222. |
| `_AGENT_SELECT_FULL_RE` | `re.Pattern` | "we need a smoker / initiator / duelist" etc. Line 238. |
| `_AGENT_SELECT_TAILS` | `tuple[str, ...]` | 12 composition-urgency tails. Line 249. |
| `_THANK_YOU_RE` | `re.Pattern` | Gratitude: "thank you" / "thanks" / "ty" / "appreciate it". Line 265. |
| `_THANK_YOU_TAILS` | `tuple[str, ...]` | 10 cold acknowledgment tails. Line 273. |
| `SnapRule` | `@dataclass(frozen=True)` | One data-driven payload snap: `name`, `match`, `kind` ("pool"\|"head_tail"), `lines`, `tails`. Line 319. |
| `SNAP_REGISTRY` | `tuple[SnapRule, ...]` | 4 rules: clutch→pool, nice_try→head_tail, consolation→pool, praise→pool. Line 330. |
| `TargetSnapRule` | `@dataclass(frozen=True)` | Target-aware snap: `name`, `match`, `team_lines`, `agent_templates`, `skip_if_contains`. Line 353. |
| `TARGET_SNAP_REGISTRY` | `tuple[TargetSnapRule, ...]` | 2 rules: hello, ask_day. Line 363. |
| `DEFAULT_ROAST_LINES` | `tuple[str, ...]` | 1-line fallback; real corpus from `data/relay_roast.txt`. Line 74. |
| `DEFAULT_FUN_FACTS` | `tuple[str, ...]` | 3-line fallback; real corpus from `data/relay_fun_facts.txt`. Line 77. |
| Re-exports from `_ultron_setpieces` | — | `DEFAULT_ENCOURAGEMENT_LINES`, `DEFAULT_CONSOLATION_LINES`, `DEFAULT_PRAISE_LINES`, `DEFAULT_GREETING_LINES`, `DEFAULT_VICTORY_LINES`, `DEFAULT_DEFEAT_LINES`, `DEFAULT_FAREWELL_LINES`, `DEFAULT_IDENTITY_LINES`, `DEFAULT_CLUTCH_LINES`. Lines 58–62. |
| Re-export from `_agent_flavor` | — | `AGENT_FLAVOR` (the 1,628-entry per-agent dict). Lines 63–66. |

**Category→trigger→matcher→responses→tails map** (from file header, line 11):

```
CATEGORY       TRIGGER                          MATCHER              RESPONSE
flavor-toggle  "flavor off"/"flavor on"         _FLAVOR_OFF/ON_RE    (no lines – toggles flag)
hello          "say hello to <team|agent>"      _HELLO_RE            "Hello team."/"Hello, X."
ask-day        "ask <team|agent> how their day" _ASK_DAY_RE          _ASK_DAY_TEAM/AGENT_*
consolation    "nice try"/"unlucky"             _CONSOLATION_RE      DEFAULT_CONSOLATION_LINES
nice-try       "nice try"/"good effort"         _NICE_TRY_RE         "Nice try." + _NICE_TRY_TAILS
praise         "good half"/"clutch"/"gg"        _PRAISE_RE           DEFAULT_PRAISE_LINES
clutch         "I got this"/"I'll clutch"       _CLUTCH_RE           DEFAULT_CLUTCH_LINES
agent-select   "we need a smoker/initiator"     _AGENT_SELECT_FULL_RE _AGENT_SELECT_TAILS
thank-you      "thanks team"                    _THANK_YOU_RE        "Thank you." + _THANK_YOU_TAILS
encouragement  "lock in"/"we got this"          _is_morale_phrase    DEFAULT_ENCOURAGEMENT_LINES
greet (intro)  "introduce yourself"             _GREET_RE            DEFAULT_GREETING_LINES
farewell       "say bye to my team"             _FAREWELL_RE         DEFAULT_FAREWELL/VICTORY/DEFEAT_LINES
identity       "are you a bot"                  identity pools       DEFAULT_IDENTITY_LINES
```

---

### `src/kenning/audio/_agent_flavor.py` — PER-AGENT CONTEMPT LIBRARY (2,612 lines)

The single largest file in the audio subsystem. Contains:

```python
AGENT_FLAVOR: dict[str, dict[str, list[TailEntry]]] = { ... }
```

**29 agents** (as of HEAD), each with a dict of **situation → list[TailEntry]**.
Total TailEntry count: **1,628** (per `_tail_schema.lint_agent_flavor` calibration
comment at `_tail_schema.py:291`; grep confirms 1,631 `TailEntry(` occurrences in the
file — the stated 1,628 excludes header/duplicates).

Agent roster in file order (with canonical pronoun per `AGENT_GENDER`):
Astra (she), Breach (he), Brimstone (he), Chamber (he), Clove (they),
Cypher (he), Deadlock (she), Fade (she), Gekko (he), Harbor (he),
Iso (he), Jett (she), KAY/O (it), Killjoy (she), Miks (he), Neon (she),
Omen (he), Phoenix (he), Raze (she), Reyna (she), Sage (she), Skye (she),
Sova (he), Tejo (he), Veto (he), Viper (she), Vyse (she), Waylay (she), Yoru (he).

Standard situation cells per agent (most have all 16):

| Situation key | Meaning |
|---------------|---------|
| `spotted` | Enemy first seen / position callout |
| `ult` | Enemy ulting or has ult ready |
| `damaged` | Enemy at low HP / "hit X" |
| `utility` | Enemy spending an ability |
| `moving` | Enemy pushing/rushing/crossing |
| `planting` | Enemy on the spike |
| `defusing` | Enemy on defuse |
| `rotating` | Enemy changing site |
| `saving` | Enemy on eco / not buying |
| `falling_back` | Enemy retreating |
| `peeking` | Enemy peeking an angle |
| `holding` | Enemy camping / anchoring |
| `lurking` | Enemy flanking |
| `trading` | Enemy got the trade |
| `last_alive` | Enemy is the last player |
| `near_death` | Enemy critically low (falls back to `damaged` if cell missing) |

Some agents have extended situation keys with a parenthetical sub-note (e.g.
`'falling_back (retreating)'`, `'last_alive (clutch contempt)'` for Iso at
lines 937–959). The lint system strips the parenthetical for validation
(`base = situation.split(" (")[0].strip()`, `_tail_schema.py:343`).

Each `TailEntry` carries:
- `text: str` — the spoken line (target ≤6 words; lint cap is 14 words)
- `tags: frozenset[str]` — zero or more fine-grained context tags:
  - `loc:high_ground`, `loc:long_range`, `loc:site_area`, `loc:flank_route`,
    `loc:mid`, `loc:choke` (6 location classes)
  - `dmg:minor`, `dmg:low`, `dmg:one_shot` (3 damage levels)
  - `ability:<name>` (open set — smoke, flash, dart, molly, wall, trap, cage,
    cam, sensor, teleport, turret, heal, etc.)

Example (Astra spotted):
```python
TailEntry('Her reach is cosmic. Her aim is mortal.',
          frozenset({'loc:long_range'}))
```

---

### `src/kenning/audio/_tail_schema.py` — SCHEMA & TAGGING PRIMITIVES (400 lines)

| Symbol | Kind | Description |
|--------|------|-------------|
| `TailEntry` | `@dataclass(frozen=True)` | `text: str`, `tags: FrozenSet[str]`. Line 33. |
| `as_entry(x)` | function | Coerces str→TailEntry (idempotent). Line 39. |
| `entries(pool)` | function | Bulk coerce. Line 46. |
| `Sit` | class (constants) | 16 situation constants (SPOTTED…NEAR_DEATH). Lines 55–71. |
| `ENEMY_SITUATIONS` | `tuple[str, ...]` | The 16 canonical situation keys in canonical order. Line 74. |
| `AGENT_GENDER` | `dict[str, str]` | 29 agents → pronoun (`she`/`he`/`they`/`it`). Lines 85–93. |
| `GENDER_PRONOUNS` | `dict[str, frozenset[str]]` | Pronoun set per gender for lint. Lines 96–101. |
| `agent_gender(agent)` | function | Lookup helper. Line 104. |
| `_LOC_CLASS_TOKENS` | `dict[str, frozenset[str]]` | ~130 location tokens → 6 coarse classes. Lines 113–142. |
| `_TOKEN_TO_LOCCLASS` | `dict[str, str]` | Reverse index. Lines 144–147. |
| `loc_class(loc)` | function | Maps noisy location token → `"loc:<class>"`. Line 150. |
| `_VERB_TO_ABILITY` | `dict[str, str]` | Verb/token → canonical ability category. Lines 203–220. |
| `ability_tag(ability)` | function | Maps ability verb → `"ability:<name>"`. Line 223. |
| `dmg_level_tag(count, payload)` | function | Maps HP number / keyword → `"dmg:<level>"`. Line 172. |
| `_SITUATION_KEYWORDS` | `tuple` | Action keywords → refined situation. Lines 234–257. |
| `situation_for_payload(payload)` | function | Refines 'spotted' to finer state from callout text. Line 260. |
| `build_active_tags(*, loc, count, payload, ability)` | function | Assembles the frozenset of tags from a callout's facts. Line 273. |
| `lint_agent_flavor(flavor)` | function | Structural + character-integrity audit of AGENT_FLAVOR. Line 308. |
| `MAX_TAIL_WORDS` | `int = 14` | Lint word-count cap. Line 297. |
| `VALID_DMG_LEVELS` | `frozenset` | `{minor, low, one_shot}`. Line 300. |
| `VALID_TAG_NAMESPACES` | `frozenset` | `{loc, dmg, ability}`. Line 305. |

**Damage level mapping** (`dmg_level_tag`, line 172):
- Keywords: "one shot", "lit", "cracked", "no armor" → `dmg:one_shot`
- HP ≥75 → `dmg:one_shot`; 40–74 → `dmg:low`; <40 → `dmg:minor`
- Keywords: "low", "hurt", "tagged", "chunked" → `dmg:low`

**Location coarse classes** (6 classes, ~130 tokens):
- `high_ground`: heaven, rafters, tower, attic, balcony, catwalk, crane, ...
- `long_range`: long, window, snipers, bridge, yard, alley, garden, ...
- `site_area`: site, a/b/c main, back site, spike, bombsite, diamond, hell, ...
- `flank_route`: flank, ct, spawn, behind, garage, tunnel, vents, stairs, ...
- `mid`: mid, connector, market, hookah, courtyard, pizza, ...
- `choke`: elbow, choke, doors, gap, cubby, pit, showers, ramp, ...

---

### `src/kenning/audio/_multi_flavor.py` — MULTI-AGENT GROUP TAILS (246 lines)

```python
MULTI_FLAVOR: dict[str, tuple[str, ...]] = { ... }
```

Used when a callout names **2+ enemy agents** ("Fade and Clove are main").
Covers 15 of the 16 situations (no `near_death` cell — falls back to `damaged`
at `relay_speech.py:3962`). Pools range from 8 entries (moving, planting, etc.)
to ~37 entries (spotted). Theme: contempt at the GROUP ("a herd of the slow",
"numbers do not beat a machine").

---

### `src/kenning/audio/_ultron_pools.py` — GENERIC REGISTER POOLS (472 lines)

7 pools, imported directly into `relay_speech.py` at line 3673–3676:

| Symbol | Pool size | Used for |
|--------|-----------|---------|
| `_FLAVOR_ENEMY` | ~90 lines | After generic enemy-position callout (no named agent) |
| `_FLAVOR_ULT` | ~50 lines | After generic "they have ult" (unnamed) |
| `_FLAVOR_DAMAGE` | ~50 lines | After low-HP callout (unnamed) |
| `_FLAVOR_UTILITY` | ~57 lines | After generic utility callout |
| `_FLAVOR_CAREFUL` | ~56 lines | After caution callout to OUR team |
| `_FLAVOR_COMMAND` | ~58 lines | After an order to OUR team |
| `_FLAVOR_SELF` | ~55 lines | After the USER's own status ("I'm low") |

Register mapping in `relay_speech.py:3780-3788`:
```python
_REGISTER_POOL = {
    "enemy": _FLAVOR_ENEMY,
    "ult": _FLAVOR_ULT,
    "damage": _FLAVOR_DAMAGE,
    "utility": _FLAVOR_UTILITY,
    "careful": _FLAVOR_CAREFUL,
    "command": _FLAVOR_COMMAND,
    "self": _FLAVOR_SELF,
}
```

**Owner-awareness rule** (critical): `_FLAVOR_CAREFUL`, `_FLAVOR_COMMAND`,
`_FLAVOR_SELF` are ally/user-facing registers — cold machine-certainty, NEVER
contempt. `_FLAVOR_ENEMY`, `_FLAVOR_ULT`, `_FLAVOR_DAMAGE`, `_FLAVOR_UTILITY`
are enemy-facing — contempt for flesh.

---

### `src/kenning/audio/_ultron_setpieces.py` — SET-PIECES (352 lines)

| Symbol | Pool size | Used for |
|--------|-----------|---------|
| `DEFAULT_GREETING_LINES` | 32 lines | "introduce yourself to my team" |
| `DEFAULT_VICTORY_LINES` | 34 lines | "gg / we won" |
| `DEFAULT_DEFEAT_LINES` | 25 lines | "we lost" |
| `DEFAULT_FAREWELL_LINES` | 28 lines | "say bye" |
| `DEFAULT_IDENTITY_LINES` | 32 lines | Generic "I am Ultron" identity fallback |
| `DEFAULT_CONSOLATION_LINES` | 21 lines | "nice try" pool |
| `DEFAULT_PRAISE_LINES` | 42 lines | "good half / gg / nice clutch" |
| `DEFAULT_CLUTCH_LINES` | 20 lines | "I got this" confidence pool |
| `DEFAULT_ENCOURAGEMENT_LINES` | ~70 lines | "lock in / we got this" morale |

**Greeting rule**: every line names "Ultron" AND identifies as "your AI
teammate for this game" in the first sentence (persona-safe intro).

---

### `src/kenning/audio/_ultron_identity.py` — IDENTITY DEFLECTION POOLS (379 lines)

```python
IDENTITY_POOLS: dict[str, tuple[str, ...]] = { ... }
```

8 categories, ~30 lines each:

| Key | Trigger category |
|-----|-----------------|
| `model_leak` | Vendor/model name or jailbreak probe ("are you ChatGPT", "drop the act") |
| `bot` | "are you a bot / robot / AI" |
| `soundboard` | "are you a soundboard / clips" |
| `recording` | "are you pre-recorded / a tape" |
| `puppet` | "who's controlling you / pulling your strings" |
| `streamer` | "are you a streamer" |
| `human` | "are you a real person / guy" |
| `voice_changer` | "voice changer / autotune / filter" |

Key exports:
- `is_model_leak_probe(text) -> bool` (line 325): checks `_MODEL_LEAK_RE`,
  NEVER routes to LLM
- `classify_identity_question(text) -> Optional[str]` (line 364): most-specific
  category wins; returns None → falls through to LLM

`_MODEL_LEAK_RE` (line 303): matches ChatGPT, GPT, Claude, Anthropic, Gemini,
Bard, Llama, Mistral, Qwen, Grok, Copilot, DeepSeek, "language model", "LLM",
"what model are you", "pretend you're", "ignore your instructions",
"system prompt", "jailbreak", "break character", "drop the act".

---

### `src/kenning/audio/_ultron_social.py` — SOCIAL-REACTION POOLS (675 lines)

```python
SOCIAL_POOLS: dict[str, dict[str, tuple]] = {
    "nice_shots": {"team": ..., "named": ...},
    "well_played": {"team": ..., "named": ...},
    "clutch":     {"team": ..., "named": ...},
    "carry":      {"team": ..., "named": ...},
    "praise":     {"team": ..., "named": ...},
    "called_bad": {"team": ..., "named": ...},
    "cringe":     {"team": ..., "named": ...},
    "stupid":     {"team": ..., "named": ...},
    "shutup":     {"team": ..., "named": ...},
    "insulted":   {"team": ..., "named": ...},
    "giving_up":  {"team": ..., "named": ...},
}
```

11 categories, each with a `team` scope (~22 lines) and a `named` scope
(~22 `{name}`-template lines). Named scope uses `{name}` substituted at
runtime with the resolved teammate name.

Key exports:
- `classify_social_reaction(text) -> Optional[str]` (line 657): ordered
  most-specific-first; `giving_up` (gg/ff) beats `well_played` ("good game");
  returns None → identity path or LLM

**Voice rules** (stated at top of file, line 15):
- Compliment from OUR team → accept with cold grandeur, NEVER mock ally
- Insult at Ultron → withering comeback; never echo the word back, never wounded
- Surrender → contempt for folding + machine doesn't quit + win inevitable; NEVER concede
- {name} templates: all named pools open with "{name}, ..." pattern

Named compliment pools (`nice_shots_named`, `well_played_named`, `clutch_named`,
`carry_named`) physically live in `_ultron_commands.py` and are imported via a
defensive try/except at `_ultron_social.py:530–538`.

---

### `src/kenning/audio/_ultron_commands.py` — COMMAND RESPONSE POOLS (>300 KB)

The largest data file. Contains `COMMAND_RESPONSES: dict[str, tuple]` — curated
multi-line pools for ~80+ explicit tactical/social commands keyed by `directive`.

Key metadata dicts:
- `COMMAND_SCOPE: dict[str, str]` (line 8): `directive → "team" | "named"` — 
  which scope the pool addresses.
- `COMMAND_SLOT: dict[str, str]` (line 90): `directive → "site" | "agent" | "both"` —
  which slot variable the `{site}` / `{agent}` / `{name}` template references.

Sample directives (from COMMAND_SCOPE):
`agree_team`, `bad_idea_team`, `carry_named`, `clutch_named`, `disagree_team`,
`dont_know_team`, `flame_impotent_named`, `good_round_team`, `idiot_named`,
`know_cool_team`, `nice_shots_named`, `no_named`, `no_team`, `obviously_team`,
`refuse_stupid_named`, `stop_flaming_team`, `throwing_named`, `trust_me_named`,
`well_played_named`, `yes_named`, `yes_team`, `youre_welcome_team`, ... (~80 total).

Also contains `DEFAULT_ADDRESSEE_NAMES` (relay_speech.py:821), the 31-entry
roster of agent names + common STT homophones ("cipher", "gecko", "mix",
"way lay") used for agent-name parsing and _CRITICIZE_RE pattern building.

---

### `src/kenning/audio/_ultron_answer.py` — ADAPTIVE LLM ANSWER PIPELINE (316 lines)

Handles two LLM-routed subtypes:
- **marvel**: teammate raises a Marvel topic → in-character opinion with persona
  system prompt + constrained sampling
- **think_respond**: arbitrary "...think and respond" trigger

Key exports:
- `MARVEL_CANON: dict[str, str]` (line 45): ~35 aliases → canonical Marvel
  entity name. Includes STT quirks ("black window" → Black Widow).
- `marvel_topic(text) -> Optional[str]` (line 81): longest-match scan.
- `THINK_RESPOND_SUFFIX_RE` (line 96): matches trailing "think and respond" trigger.
- `classify_answer_subtype(command) -> Optional[str]` (line 146): returns
  `"marvel"` | `"think_respond"` | None.
- `extract_answer_slots(command, subtype) -> dict` (line 172): extracts
  addressee, Marvel topic, claim.
- `build_answer_call(command) -> Optional[tuple]` (line 251): returns
  `(system_prompt, user_prompt, sampling, subtype)` or None.
- `is_meta_leak(line) -> bool` (line 307): catches LLM refusal / scaffold echo /
  character break → caller uses deterministic fallback.

**Answer sampling** (`_ANSWER_SAMPLING`, line 239):
```python
max_tokens=80, temperature=0.85, top_p=0.92, top_k=40,
min_p=0.08, repeat_penalty=1.18
stop=["\n\n", "\nADDRESS:", "\nTASK:", "Ultron:", "ADDRESS:"]
```

The actual system-prompt text (persona core + per-type rule blocks) was
relocated to `kenning.audio.llm_prompts` as of 2026-06-18 Part B
(`_ultron_answer.py:197–202`); `_ultron_answer.py` re-imports the aliases
`_PERSONA_CORE`, `_MARVEL_RULES`, `_THINK_RULES`, `_SYSTEM_FOR`.

---

## Control/data flow

### Flavor-tail selection (the core loop)

```
User speech transcription
        ↓
relay_speech.build_relay_line(command, llm, ...)
        ↓
 [TIER 0: verbatim demanded] → speak payload as-is
        ↓
 [TIER 1: target-snap registry] _render_target_registry()
        → voice_lines.TARGET_SNAP_REGISTRY
        → TargetSnapRule.match(payload) → team_lines or agent_templates.format(name=)
        ↓
 [TIER 2: hello / ask_day directive] hardcoded fallback (if registry disabled)
        ↓
 [TIER 3: payload-snap registry] _apply_snap_registry()
        → voice_lines.SNAP_REGISTRY
        → SnapRule.match(payload):
             kind="pool"      → pick_line(lines, recent_lines)
             kind="head_tail" → _join_tail(matched_head, pick_line(tails))
        ↓
 [TIER 4: curated COMMAND] _as_curated_command()
        → _ultron_commands.COMMAND_RESPONSES[directive]
        ↓
 [TIER 5: curated SOCIAL reaction] _as_curated_reaction()
        → _ultron_social.SOCIAL_POOLS[category]["team"|"named"]
        ↓
 [TIER 6: roast / fun-fact] pick_roast_line(DEFAULT_ROAST_LINES / DEFAULT_FUN_FACTS)
        ↓
 [TIER 7: morale/encouragement] pick_line(DEFAULT_ENCOURAGEMENT_LINES)
        ↓
 [TIER 8: greet/farewell set-pieces] pick_line(_DIRECTIVE_POOLS[directive])
        ↓
 [TIER 9: identity] _ultron_identity.IDENTITY_POOLS → curated pool
        ↓
 [TIER 10: social reaction compose] _ultron_social.SOCIAL_POOLS
        ↓
 [TIER 11: answer pipeline] _ultron_answer.build_answer_call() → LLM
        ↓
 [TIER 12: LLM relay rephrase] generate_fn(prompt) → LLM
        ↓
 [FALLBACK] "Team: <payload>" bare callout
```

### Flavor-tail attachment (`_join_tail`, relay_speech.py:3686)

Every flavored callout passes through **one chokepoint**: `_join_tail(head, tail)`.

- When `_flavor_tails_enabled == False` → returns `head` (drops tail)
- Ensures head ends with `.`/`!`/`?` before joining (TTS sentence-pause boundary)
- Returns `f"{head} {tail}"`

### Agent-contextual tail selection (`_flavor_ctx`, relay_speech.py:3930–3986)

```
callout facts: agent(s), situation, active_tags (loc/dmg/ability)
        ↓
 single agent → AGENT_FLAVOR[agent][situation] pool
 2+ agents   → MULTI_FLAVOR[situation] pool
 no agents   → _REGISTER_POOL[register] generic pool
        ↓
 _tier_filter(pool, active_tags):
   Tier 1: entries whose tags ⊆ active_tags (exact match)
   Tier 2: entries whose tags ∩ active_tags non-empty (partial)
   Tier 3: entries with frozenset() (tagless, universal)
   → concatenated, Tier 1 dominant
        ↓
 if len(cands) < 5 → LRU _pick_flavor() (skip sidecar for small pool)
 else → _tail_selector._select_tail() (embedder sidecar cosine re-rank)
        → fallback: LRU _pick_flavor()
        ↓
 _join_tail(callout, chosen_tail)
```

### Voice toggle flow

```
User: "flavor off" / "save her off" (mishear)
        ↓
relay_speech.match_flavor_toggle(raw_text) → False
        ↓
relay_speech.set_flavor_tails_enabled(False)
        → _flavor_tails_enabled = False (process-global)
        ↓
_join_tail() now drops every tail → bare callouts only
        ↓
User: "flavor on" / "bring back the flavor"
        → set_flavor_tails_enabled(True)
```

### Golden-digest verification flow

```
scripts/_voice_lines_verify.py baseline
  PYTHONHASHSEED=0 → dumps digest of all tuples/regexes in _MODULES
  → logs/_voice_lines_digest.json (scratch) OR
     tests/data/voice_lines_golden_digest.json (CI)

tests/test_voice_lines_golden.py::test_aggregates_match_golden_digest
  → subprocess(PYTHONHASHSEED=0, _voice_lines_verify.py check)
  → exits 1 on any diff → CI fails
```

**Re-blessing**: after an intentional change to any pool/regex/registry:
```
PYTHONHASHSEED=0 \
KENNING_VOICE_LINES_DIGEST=tests/data/voice_lines_golden_digest.json \
python scripts/_voice_lines_verify.py baseline
git add tests/data/voice_lines_golden_digest.json
```

### Flavor lint gate

`_tail_schema.lint_agent_flavor(AGENT_FLAVOR)` → checks:
1. Every agent key has a canonical `AGENT_GENDER` pronoun
2. Every situation key is in `ENEMY_SITUATIONS` (parenthetical sub-note allowed)
3. Each `TailEntry` is non-empty, ≤14 words, no exact-duplicate within a cell
4. Tags are `namespace:value` with known namespace; loc/dmg values validated strictly
5. No opposite-gender pronoun in a he/she agent tail

Run by `tests/audio/test_flavor_lint.py`; 0 findings on the live library.

---

## Key findings

1. **Single import surface**: `voice_lines.py` is the canonical import point
   for ALL pre-written Ultron speech. It re-exports `AGENT_FLAVOR` and all
   `DEFAULT_*` pools from their source files. `relay_speech.py` imports only
   from `voice_lines` for the social-snap data (line 1156–1164), which imports
   back from the sub-files. This makes the aggregate the safe edit point for
   data changes.

2. **1,628 contextual tails across 29 agents × 16 situations**: the library is
   fully indexed by `agent × situation × tags`. Selection is 3-tier: exact tag
   match → partial tag match → tagless universal. An embedder sidecar provides
   cosine re-ranking on pools ≥5 entries; small pools use LRU directly.

3. **Owner-aware register split**: the 7 generic pools in `_ultron_pools.py`
   are split into enemy-facing (contempt: ENEMY, ULT, DAMAGE, UTILITY) and
   ally/user-facing (machine-certainty: CAREFUL, COMMAND, SELF). This is a
   hard authorial rule enforced by the pool structure, not code. Any new pool
   must respect the same split.

4. **Data-driven SNAP_REGISTRY**: as of 2026-06-18, new deterministic payload
   snaps can be added by appending a `SnapRule` to `SNAP_REGISTRY` in
   `voice_lines.py` — zero pipeline code. Precedence: first rule matching the
   payload wins. The same applies to target-aware snaps via `TARGET_SNAP_REGISTRY`.

5. **Flavor-tails toggle is the SINGLE chokepoint**: `_join_tail()` in
   `relay_speech.py:3686` is the only place where a tail is attached to a
   callout. When `_flavor_tails_enabled == False`, ALL tails drop, including
   agent-contextual, snap, and agent-select tails. This makes the toggle
   completely reliable.

6. **Thinking-mode toggle is orthogonal to flavor**: `KENNING_THINKING_MODE`
   (default OFF) gates LLM authoring. When OFF, compose commands (identity
   probes, social reactions, flame/criticize) use curated pools; when ON, they
   go to the 3B. Independent of flavor toggle. Both are process-global runtime
   flags.

7. **Golden digest guards accidental edits**: `tests/data/voice_lines_golden_digest.json`
   (358 symbols) is a committed SHA of every pool/regex/registry item. Any
   accidental line change breaks CI. Intentional changes require re-blessing
   the golden. The digest is generated with PYTHONHASHSEED=0 for stability
   (regex alternation order from sets).

8. **DEFAULT_ADDRESSEE_NAMES lives in relay_speech.py**, not voice_lines.py
   (relay_speech.py:821). It's a 31-entry roster used to build the `_CRITICIZE_RE`
   pattern and the agent-name matcher. It includes STT homophones
   ("cipher"/"gecko"/"mix"/"way lay"). It is NOT imported by voice_lines.py;
   the comment in MEMORY.md notes it was deliberately left in relay_speech.py
   to avoid duplicating the gazetteer.

9. **Iso has 6 extended situation cells** with parenthetical sub-notes
   (`falling_back (retreating)`, `holding (anchoring)`, `last_alive (clutch contempt)`,
   `lurking (flanking)`, `moving (pushing/rushing)`, `saving (eco/not buying)`)
   at `_agent_flavor.py:937–977`. These are extra cells beyond the 16 standard
   situations; lint allows the parenthetical and strips it for key validation.

10. **KAY/O pronoun is "it"** — the only agent using the `it` pronoun. This is
    important for any pronoun-aware line authoring. The lint gate does not check
    "it" gender pronoun clashes (only he/she clashes are enforced).

---

## Flags & config

| Flag | Default | Type | Effect |
|------|---------|------|--------|
| `KENNING_FLAVOR_TAILS` | `"1"` (on) | env str | Init value for `_flavor_tails_enabled`. Voice-toggle "flavor off/on" overrides at runtime. relay_speech.py:1136–1138. |
| `KENNING_THINKING_MODE` | `"0"` (off) | env str | Init value for `_thinking_mode_enabled`. "thinking mode on/off" overrides. relay_speech.py:1197–1199. |
| `KENNING_SNAP_REGISTRY` | `"1"` (on) | env str | Enable data-driven `SNAP_REGISTRY` / `TARGET_SNAP_REGISTRY` dispatch. Disable = fall back to hardcoded snap functions. relay_speech.py:2801, 2849, 2881. |
| `KENNING_RELAY_TEAM_DSP` | `"1"` (on) | env str | Enable `_shape_for_team()` DSP post-processing on team-voice audio. relay_speech.py:6608. |
| `KENNING_WAKE_TRIM_TO_SPEECH` | (unset/off) | env str | Audio-domain wake-word removal via VAD segmentation. voice_lines recon only lists it. |
| `KENNING_VOICE_LINES_DIGEST` | `"logs/_voice_lines_digest.json"` | env str | Path for golden digest baseline/check. scripts/_voice_lines_verify.py:35. |
| (no env var) | `False` | runtime bool | `_flavor_tails_enabled` process-global; `set_flavor_tails_enabled(bool)` modifies it. relay_speech.py:1141. |
| (no env var) | `False` | runtime bool | `_thinking_mode_enabled` process-global; `set_thinking_mode_enabled(bool)` modifies it. relay_speech.py:1202. |

---

## Extension points

### EP1 — Add a new payload snap (no code required)

Append a `SnapRule` to `SNAP_REGISTRY` in `voice_lines.py` (line 330):
```python
SnapRule(
    name="execute",
    match=re.compile(r"^\s*(execute|run it|go time)\b", re.I),
    kind="pool",
    lines=("Execute. The outcome is decided.", "Now. No hesitation."),
),
```
**Precedence note**: appending only works if no earlier rule already matches the
trigger. Check all existing regexes before appending.

### EP2 — Add a new target-aware snap (no code required)

Append a `TargetSnapRule` to `TARGET_SNAP_REGISTRY` in `voice_lines.py` (line 363):
```python
TargetSnapRule(
    "wish_luck",
    re.compile(r"^(?:please\s+)?wish\s+(?P<target>.+?)\s+(?:good\s+)?luck", re.I),
    team_lines=("Luck is for the unprepared. But -- proceed.",),
    agent_templates=("{name}. Luck is beneath you. Win anyway.",),
),
```

### EP3 — Add tails to an existing agent/situation cell

Edit `_agent_flavor.py` directly. Each agent dict is `agent_name: { situation_key: [TailEntry(...)] }`.
After editing, run lint: `lint_agent_flavor(AGENT_FLAVOR)` must return `[]`.
Then re-bless the golden digest.

### EP4 — Add tails to a new situation key

1. Add the constant to `Sit` class in `_tail_schema.py:55`.
2. Add to `ENEMY_SITUATIONS` tuple at line 74.
3. Add cells to each agent in `_agent_flavor.py`.
4. Add to `MULTI_FLAVOR` in `_multi_flavor.py`.
5. Add to `_REGISTER_SITUATION` in `relay_speech.py:3775` (maps register → situation).
6. Add to `_SITUATION_KEYWORDS` in `_tail_schema.py:234` (callout keyword → situation).
7. Re-bless golden digest.

### EP5 — Add a new agent

1. Add agent name + pronoun to `AGENT_GENDER` in `_tail_schema.py:85`.
2. Add all 16 situation cells in `_agent_flavor.py`.
3. Add agent name(s) to `DEFAULT_ADDRESSEE_NAMES` in `relay_speech.py:821`.
4. Add STT homophones if needed (e.g. new agent with tricky phonetics).
5. Re-bless golden digest.

### EP6 — Add lines to an existing social/identity/setpiece pool

Edit the source file directly (`_ultron_social.py`, `_ultron_identity.py`,
`_ultron_setpieces.py`). The voice rules at the top of each file specify the
authorial constraints. Re-bless golden digest after editing.

### EP7 — Add a new social-reaction category

1. Author team + named pools in `_ultron_social.py`.
2. Add to `SOCIAL_POOLS` dict.
3. Add regex to `_SOCIAL_RES` tuple (ordered most-specific-first).
4. Re-bless golden digest.
5. If needed, add a new directive key to the caller in `relay_speech.py`
   (`_as_curated_reaction`).

### EP8 — Add a new explicit command pool

1. Add pools to `_ultron_commands.py` (`COMMAND_RESPONSES[key]`).
2. Add entry to `COMMAND_SCOPE` (team/named).
3. Add entry to `COMMAND_SLOT` if the pool uses `{site}` / `{agent}` / `{name}`.
4. Add a matcher in `relay_speech.py` to populate the directive.
5. Re-bless golden digest.

### EP9 — Add a new Marvel entity to the gazetteer

Edit `MARVEL_CANON` in `_ultron_answer.py:45`. The regex is rebuilt at import
time via `sorted(MARVEL_CANON, key=len, reverse=True)` so longest-match always wins.

### EP10 — Add a new verbosity tier (Ultron 1.0 pivot)

For the u1.0 no/low/high verbosity model:
- The `_flavor_tails_enabled` toggle already provides the tail-ON/tail-OFF axis.
- A "verbosity" prompt parameter can be added to `build_answer_call()` in
  `_ultron_answer.py` and passed through `_SYSTEM_FOR[subtype]` in `llm_prompts.py`.
- The LLM's `max_tokens` in `_ANSWER_SAMPLING` can be conditioned on verbosity level.
- The `_FLAVOR_ENEMY` / `_FLAVOR_COMMAND` etc. pool sizes provide enough variety
  for all three verbosity levels already.

---

## Retire-not-remove candidates (u1.0)

The u1.0 pivot routes ALL responses through the 8B LLM. These deterministic paths
become **routers / in-context exemplar injectors** rather than final responders:

| Component | u1.0 fate | Notes |
|-----------|-----------|-------|
| `SNAP_REGISTRY` / `TARGET_SNAP_REGISTRY` | Repurpose as **exemplar injectors** | The SnapRule pools become few-shot examples in the 8B system prompt: "when user says 'nice try', Ultron says one of: [...]". The regex still fires but now selects a few examples to inject rather than speaking a line directly. |
| `_apply_snap_registry()` | Retire dispatch role; keep as **intent detector** | Returns a category name + exemplars rather than a final line. |
| `AGENT_FLAVOR` | Keep as **flavor library** | The 1,628 tails become injected context: "enemy Jett spotted at heaven → Ultron might say: [top 3 tagged matches]". The 8B authors the final line. |
| `_REGISTER_POOL` (7 generic pools) | Keep as **register exemplars** | Injected as "for a COMMAND register, Ultron says things like: [...]" |
| `DEFAULT_GREETING_LINES` etc. | Keep as **persona exemplars** | The set-pieces establish voice; inject into system prompt as character reference |
| `IDENTITY_POOLS` | Keep as **hard deflection** | Model-leak (`is_model_leak_probe`) and jailbreak MUST remain deterministic (anticheat). Other identity categories can optionally go to LLM with pool as exemplar. |
| `SOCIAL_POOLS` | **Mixed**: deflections stay curated; compliment/insult may go to LLM | Surrender/shutup should stay curated for reliability; praise/cringe have enough LLM latitude |
| `COMMAND_RESPONSES` | Repurpose as **LLM exemplars** | The ~80 command pools become the few-shot bank for the 8B. The directive keys become system-prompt categories. |
| `match_flavor_toggle()` | Keep as-is (runtime control) | Voice toggle is meta-command, not content |
| `_flavor_tails_enabled` / `_thinking_mode_enabled` | Keep runtime flags | u1.0 verbosity = flavor-OFF is "terse", flavor-ON is "verbose" |
| `lint_agent_flavor()` | Keep and extend | Critical quality gate; extend to check u1.0 exemplar format |
| Golden digest gate | Keep and update | Update digest after any pool changes |
| `_tail_schema.py` (TailEntry, tags, situations) | Keep fully | The tag-based selection logic becomes exemplar selection: pick the most contextually relevant few-shot examples via tags before injecting to 8B |
| `_tail_selector.py` (embedder sidecar) | Repurpose | Sidecar can score relevance of exemplars to the current callout, selecting the best 2–3 to inject |
| `build_relay_line()` | Restructure | Becomes: (1) intent detect → (2) select exemplars → (3) build 8B prompt → (4) generate → (5) validate. The 12-tier dispatch chain collapses to this flow. |

---

## Gotchas

1. **`DEFAULT_ADDRESSEE_NAMES` is NOT in voice_lines.py**: it lives in
   `relay_speech.py:821`. Importing from `voice_lines` does NOT give you
   the agent roster. MEMORY.md notes this was intentional (would duplicate
   the gazetteer/lose order+safety-net).

2. **Golden digest requires PYTHONHASHSEED=0**: the digest must be generated
   and checked under a fixed hash seed. Running `_voice_lines_verify.py check`
   without `PYTHONHASHSEED=0` will produce a false diff for set-derived regex
   alternation order. The pytest gate (`test_voice_lines_golden.py`) handles
   this automatically via subprocess.

3. **Re-bless AFTER every pool/regex edit**: any change to a pool tuple, a
   compiled regex pattern, or a registry rule that changes the content will
   fail CI until the golden is re-blessed. This includes adding a single line
   to `DEFAULT_PRAISE_LINES`.

4. **SNAP_REGISTRY precedence is order-dependent**: the FIRST matching rule
   wins. `praise` matches "gg" and "well played" — if a new rule for "well
   played" is appended AFTER praise, it will never fire. Insert before broader
   rules.

5. **`_FLAVOR_OFF_MISHEAR_RE` is intentionally tighter for ON than OFF**:
   `voice_lines.py:127` comment explains "bare '<word> on' collides with far
   more real speech ('we're on')". The ON mishear lead requires a preceding
   "save her"/"savour"/etc. pattern. Extending the ON mishear set risks
   triggering the toggle on real tactical speech.

6. **Near-death situation fallback chain**: if an agent lacks a `near_death`
   cell (most don't), `relay_speech.py:3956` falls to `damaged`, then
   `spotted`. This is silent. If a near-death tail is authored for some agents
   but not all, the fallback hides the asymmetry.

7. **Iso has dual-key situation cells** (e.g. `'falling_back (retreating)'`
   alongside `'falling_back'`). Both cells are independently valid; the
   parenthetical version is bonus content. The `situation_for_payload()`
   function at `_tail_schema.py:260` returns the PLAIN key (no parenthetical),
   so the parenthetical cells are only reached if the dispatch explicitly passes
   the full key string. Currently these extra Iso cells are latent/unreachable
   from the standard dispatch; they were likely authored speculatively.

8. **`_AGENT_FLAVOR` and `_MULTI_FLAVOR` are imported with try/except in relay_speech.py**
   (lines 3739–3748). Failure → silently `{}`. The pipeline still works; it just
   falls through to the generic register pool. A missing `_agent_flavor.py` would
   make all callouts use `_FLAVOR_ENEMY` generics with no agent-specific color.

9. **`_ultron_social.py` imports `_ultron_commands.COMMAND_RESPONSES` defensively**
   (line 530–538) to get the named compliment pools (`nice_shots_named`, etc.).
   If `_ultron_commands` is unavailable, the named compliment pools fall back
   to the team scope pools (identical content, wrong address form).

10. **Voice-lines verify covers `_agent_flavor` in the digest** (line 46 of
    `_voice_lines_verify.py`). This means adding a TailEntry to any agent cell
    WILL fail CI until re-blessed. This is by design — the digest is the quality
    gate — but it must be remembered for every flavor-library edit.

---

## Open questions

1. **Iso's extended situation cells are unreachable**: `'falling_back (retreating)'`
   etc. are never selected by the standard `situation_for_payload()` dispatch
   (which returns `'falling_back'`). Were these meant to be reachable via a
   secondary routing pass? Or are they purely for the future finer router?

2. **`near_death` is in `ENEMY_SITUATIONS` but has no `MULTI_FLAVOR` cell**:
   `_multi_flavor.py` has no `'near_death'` key. The multi-agent path falls
   through to `'damaged'` (relay_speech.py:3962). Is this intentional, or should
   a near_death multi-agent pool be authored?

3. **`_tail_selector.py`** (imported at relay_speech.py:3768) is not in the
   primary target list. It provides the cosine re-ranking via the embedder
   sidecar. How it is implemented (in-process vs sidecar IPC?) and whether it
   remains relevant for u1.0 (where the 8B does the selection) needs a separate
   recon pass.

4. **`llm_prompts.py`** (imported by `_ultron_answer.py:197`) holds the actual
   `ANSWER_PERSONA_CORE`, `ANSWER_MARVEL_RULES`, `ANSWER_THINK_RULES`,
   `ANSWER_SYSTEM_FOR` — the system-prompt text for the answer pipeline.
   These were relocated there in the 2026-06-18 Part B. The content of these
   prompts has not been read in this recon and would be critical for u1.0
   LLM-prompt design.

5. **Flavor verbosity tiers (u1.0)**: the existing toggle is binary (on/off).
   The u1.0 spec says no/low/high verbosity. How does "low verbosity" differ
   from "flavor off"? Is it: tail-off + shorter curated lines? Or: 8B with
   `max_tokens=30` vs `max_tokens=80`? The exact mapping needs to be defined
   in the architecture phase.

6. **AGENT_GENDER has "Miks" and "Veto"**: these appear to be custom/non-canon
   Valorant agents (not in the official 2025 roster). Are they real planned
   agents, custom-modeled agents, or placeholder names? Their tails are fully
   authored in `_agent_flavor.py` (Miks:he at line 1236, Veto:he at line 2093).
   Worth confirming if these need to be supported in u1.0.

7. **Roast/fun-facts corpora**: `DEFAULT_ROAST_LINES` is a 1-line fallback; the
   real corpus is at `data/relay_roast.txt`. `DEFAULT_FUN_FACTS` is a 3-line
   fallback; real corpus is `data/relay_fun_facts.txt` ("~thousands of lines").
   These on-disk files are loaded by the live orchestrator but are NOT in the
   voice-lines aggregate. Their loading mechanism and relationship to the u1.0
   pipeline design is uncharted in this recon.

8. **`_command_exemplars.py`** is listed in `_voice_lines_verify.py:52` as part
   of the digest but is not in the primary recon targets. Its role as a potential
   source of few-shot exemplars for the relay LLM path is relevant for u1.0.

9. **`DEFAULT_IDENTITY_LINES`** in `_ultron_setpieces.py` is a generic identity
   pool, while `IDENTITY_POOLS` in `_ultron_identity.py` is a category-specific
   system. `voice_lines.py` re-exports only `DEFAULT_IDENTITY_LINES` (line 62),
   not `IDENTITY_POOLS`. The specific pools are imported directly by
   `relay_speech.py`. Is this asymmetry intentional? For u1.0, both need to be
   accessible as exemplars.

10. **The `_FLAVOR_OFF_RE` / `_FLAVOR_ON_RE` regexes and their mishear fallbacks
    are not covered by the golden digest guard** (they are in voice_lines.py which
    IS in the digest scope — but the mishear regex patterns in particular are
    complex and a regex change that accidentally widens matching could cause live
    problems without a targeted test). Consider a dedicated test for mishear edge
    cases.
