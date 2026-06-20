# Board A: relay_speech.py — Relay Snap Matchers, Slot Grammar & Line Build

**Area:** A2 — Relay snap matchers, slot grammar & relay line build
**Primary file:** `src/kenning/audio/relay_speech.py` (~6750 lines)
**Supporting file:** `src/kenning/audio/voice_lines.py` (~376 lines)
**Date:** 2026-06-20

---

## 1. Module-level exports (`__all__`)

Key public names: `RelayCommand`, `RelayPlaybackResult`, `match_relay_command`, `build_relay_line`, `match_relay_toggle`, `match_flavor_toggle`, `match_thinking_toggle`, `match_llm_device_switch`, `relay_route_info`, `is_complete_tactical_callout`, `resolve_relay_device`, `play_to_device`, `DEFAULT_ADDRESSEE_NAMES`, plus re-exported line pools (`DEFAULT_ROAST_LINES`, `DEFAULT_FUN_FACTS`, …).

---

## 2. Normalization — `_normalize_speech(raw: str) -> str`

Runs before every matcher. Steps in order:

1. **KAY/O slash collapse**: `k/a/y/o` → `kayo`, `k.a.y.o` → `kayo`
2. **On-behalf strip**: removes "on my behalf" / "for me" trailing clauses
3. **Filler removal** (`_FILLER_RE`): removes "um", "uh", "er", "like", "you know", "I mean", "sort of", "kind of", "basically", "literally" scattered fillers
4. **Agent abbreviation** (`_AGENT_ABBREVS`): expands short STT mishear aliases to canonical names (e.g., "iso" → "Iso", "dead lock" → "Deadlock", "neon" → "Neon")
5. Strips extra whitespace.

---

## 3. Group reference patterns

Built at module load; used by relay pattern building:

- `_GROUP_WORDS`: bag of words — "team", "squad", "crew", "boys", "guys", "mates", "everyone", "everybody", "group", "party"
- `_GROUP`: compiled regex alternation of `_GROUP_WORDS`
- `_GROUP_PRON`: pronouns extending `_GROUP` — adds "them", "they", "us", "y'all", "you all"

---

## 4. Relay patterns — `_RELAY_PATTERNS` (13 patterns)

Order matters; first match wins. Patterns are compiled `re.IGNORECASE` regexes that capture `(?P<payload>…)`:

| # | Pattern description | Key trigger phrases |
|---|---|---|
| 1 | Explicit "tell my team X" | "tell my team", "tell the team", "tell them" |
| 2 | "let my team know X" / "let them know" | "let … know" |
| 3 | "say X to my team" / "pass X" | "say … to my team", "pass … to my team" |
| 4 | Relay verb lead | "relay X", "relay that X" |
| 5 | "my team should know X" | "my team should know", "your team should know" |
| 6 | "ask my team X" | "ask my team", "ask the team" |
| 7 | "message my team X" | "message the team" |
| 8 | Ambiguous tactical lead (`_AMBIG_TACTICAL_LEAD`) | "let my team know", "make sure my team knows", "make them aware" |
| 9 | Site callout cues (`_SITE_CALLOUT_CUES`) | site letters — A/B/C + site indicator words |
| 10 | Reported context clause ("they said X, tell them Y") | `_CONTEXT_VERB_RE` + `_DIRECTIVE_ATOM` closed vocab |
| 11 | "as … to relay" — team-as-subject (`_TEAM_AS_SUBJECT_RE`) | "as X, let them know" |
| 12 | ASK lead (`_ASK_LEAD`) | "ask <agent> about X" |
| 13 | Enemy-addressed bravado | "good fight / gg <payload>" forms |

Also: `_BARE_SAY_RE` ("say X" without explicit addressee → team by default), `_SAY_YESNO_RE` ("say yes/no to them"), `_ECONOMY_CALLOUT_RE` (eco/save/full-buy callout forms), `_DROP_WEAPON_RE` (drop-gun callout forms).

---

## 5. Named addressee patterns — `_named_patterns(names)`

LRU-cached (`@lru_cache(maxsize=4)`) function. Compiles per-name patterns that route "tell Jett X" / "let Sage know X" / "Reyna, X" etc. to a named-agent relay.

Inputs: an immutable frozenset from `DEFAULT_ADDRESSEE_NAMES`.

`DEFAULT_ADDRESSEE_NAMES` (31+ entries): all Valorant agents + common STT homophones:
- Standard: Astra, Breach, Brimstone, Chamber, Clove, Cypher, Deadlock, Fade, Gekko, Harbor, Iso, Jett, KAY/O, Killjoy, Neon, Omen, Phoenix, Raze, Reyna, Sage, Skye, Sova, Tejo, Viper, Vyse, Waylay, Yoru
- Homophones: "cipher" → Cypher, "gecko" → Gekko, "mix" → Miks (Mika), "way lay" → Waylay

---

## 6. Compose patterns — `_COMPOSE_PATTERNS`

~8 patterns for voice-authored full-line composes (not tactical relays): "write something for my team", "compose a message", "draft a team call", "introduce yourself", etc. These set `compose=True` on the returned `RelayCommand`.

---

## 7. Directive patterns

| Regex | Directive value set | Purpose |
|---|---|---|
| `_BARE_CLUTCH_RE` | — | "I got this / I'll clutch" → `clutch` pool |
| `_BARE_ENCOURAGE_RE` | — | "lock in / let's go" → morale pool |
| `_ROAST_RE` | `roast=True` | "roast the enemy / roast them" |
| `_FUN_FACT_RE` | `fun_fact=True` | "give a fun fact / share a fun fact" |
| `_PROMO_RE` | `promo` directive | "promote yourself / advertise yourself" |
| `_GREET_RE` | `greet` directive | "introduce yourself / say hi to the team" (LONG intro) |
| `_FAREWELL_RE` | `farewell` directive | "say bye / farewell / wrap it up" |
| `_WIN_RE` | `win` directive | "tell them we won / gg we won" |
| `_LOSS_RE` | `loss` directive | "tell them we lost / better luck next time" |
| `_CRITICIZE_RE` | `criticize:<name>` directive | "criticize Reyna / call out Jett" |
| `_COMPLIMENT_RE` | `compliment:<name>` directive | "compliment my Sage / big up Clove" |
| `_AGENT_SNAP_RE` | — | Agent-select / comp draft ("we need a smoker") |
| `_FLAME_ENEMY_RE` | `flame_enemy` directive | "flame the enemy / talk trash" |
| `_STOP_CMD_RE` | `stop_command` directive | "<agent> told you to stop" |

---

## 8. Verbatim modes

Four independent capture paths, all short-circuit to speaking the exact payload:

### 8a. Trailing suffix — `_VERBATIM_SUFFIX_RE`
Triggers on: "in those words", "word for word", "verbatim", "exactly like that", "as I said it", "don't change anything", "those exact words", "keep it exactly" at end of utterance. Sets `verbatim=True`; the suffix is stripped before payload extraction.

### 8b. Leading prefix — `_VERBATIM_PREFIX_RE`
Triggers on: "repeat exactly / say exactly / literally say / verbatim say" at start.

### 8c. Bare verbatim — `_extract_bare_verbatim(text)`
Triggered when the payload itself starts with quotation marks ("say "go A"") or is enclosed in quotes. Extracts content inside quotes.

### 8d. Repeat command — `_match_repeat_command(text)`
`_REPEAT_LEAD_RE`: "say that again / repeat that / say it again / one more time" → replays the last spoken relay line (stored globally). Returns a `RelayCommand` with `verbatim=True` and the last payload.

---

## 9. RelayCommand dataclass

```python
@dataclass
class RelayCommand:
    payload: str              # the callout text (stripped of wrappers)
    raw_text: str             # original STT transcript
    addressee: str            # "team" or a canonical agent name
    compose: bool = False     # voice-authored full compose
    context: Optional[str]    # "Jett said X" clause
    directive: Optional[str]  # "greet", "farewell", "win", "loss",
                               # "flame_enemy", "stop_command",
                               # "criticize:<name>", "compliment:<name>",
                               # "ask_day", "hello", "calm", ...
    roast: bool = False
    fun_fact: bool = False
    verbatim: bool = False
```

---

## 10. match_relay_command — full dispatch sequence (lines 1704–2078)

Runs after `_normalize_speech`. Returns `Optional[RelayCommand]`.

**Narration gate** (`_NARRATION_MUSING_RE`, `_NARRATION_LEAD_RE`): checked FIRST. Suppresses false-relay on musings, recounts ("I told my team…"), and general statements that start with narration leads. Returns `None` to suppress.

**Dispatch order:**

1. Toggle matchers: `match_relay_toggle`, `match_flavor_toggle`, `match_thinking_toggle`, `match_llm_device_switch` — all checked before relay matching to prevent them from being relayed as speech
2. `_match_repeat_command` — verbatim repeat of last line
3. `_SAY_YESNO_RE` — "say yes/no to them"
4. Verbatim prefix patterns (`_VERBATIM_PREFIX_RE`)
5. Economy callout (`_ECONOMY_CALLOUT_RE`)
6. Drop-weapon callout (`_DROP_WEAPON_RE`)
7. Bare say (`_BARE_SAY_RE`) — "say X" without explicit addressee
8. Named addressee patterns (`_named_patterns`) — "tell Jett X"
9. `_RELAY_PATTERNS` (#1–#13 above)
10. Compose patterns (`_COMPOSE_PATTERNS`)
11. Agent-snap / agent-select (`_AGENT_SNAP_RE`)
12. Roast / fun-fact (`_ROAST_RE`, `_FUN_FACT_RE`)
13. Bare clutch / bare encourage
14. Greeting / farewell / win / loss
15. Social reaction patterns (criticize/compliment/flame/stop)
16. Returns `None` if no match

---

## 11. Toggle matchers

### `match_relay_toggle(text) -> Optional[bool]`
Returns `True` (relay ON) / `False` (relay OFF) / `None` (no match). Toggles the runtime relay-on/off flag.

### `match_flavor_toggle(text) -> Optional[bool]`
Imported from `voice_lines`. Matches `_FLAVOR_OFF_RE` / `_FLAVOR_ON_RE` / `_FLAVOR_OFF_MISHEAR_RE` / `_FLAVOR_ON_MISHEAR_RE`. Controls `_flavor_tails_enabled()` global flag.

### `match_thinking_toggle(text) -> Optional[bool]`
Matches `_TOGGLE_OFF_RE` / `_TOGGLE_ON_RE` on the phrase "thinking mode". Controls `KENNING_THINKING_MODE` env gating.

### `match_llm_device_switch(text) -> Optional[str]`
Matches `_LLM_TO_GPU_RE` / `_LLM_TO_CPU_RE`:
- GPU: "switch to the GPU / put the model on the GPU / use GPU"
- CPU: "switch to CPU / move back to CPU / run on CPU"
Returns `"gpu"` or `"cpu"`.

---

## 12. Snap callout infrastructure

### 12a. Snap callout entry point — `_as_snap_callout(command, recent_lines)`

Full sequence of 20+ deterministic handlers checked IN ORDER. Returns a fully-rendered string or `None`:

| Step | Handler | Trigger |
|---|---|---|
| 1 | Thank-you snap | `_THANK_YOU_RE` → "Thank you." + random tail from `_THANK_YOU_TAILS` |
| 2 | Agent-select snap | `_AGENT_SELECT_FULL_RE` → "We need a <role>." + tail from `_AGENT_SELECT_TAILS` |
| 3 | Economy callout | explicit eco patterns → literal economy line |
| 4 | Drop weapon | drop-weapon pattern → literal drop line |
| 5 | Yes/no relay | `_SAY_YESNO_RE` |
| 6 | Position/count — self ("I'm on A") | `_as_agent_position` |
| 7 | Enemy action ("they're pushing B") | `_as_enemy_action` |
| 8 | Location-based callout | `_is_place` gate + location token extraction |
| 9 | Count snap ("two remaining") | digit/count tokens |
| 10 | Damage snap ("hit for 90") | dmg token + `_M1_DMG` set |
| 11 | Ult snap ("I have ult") | `_ABILITY_VERBS` + ult tokens |
| 12 | Possession snap ("I have a ghost") | possession verbs + weapon tokens |
| 13 | Movement snap ("rush / rotate") | `_IMPERATIVE_VERBS` |
| 14 | Ability snap ("I'll wall off") | `_ABILITY_VERBS` |
| 15 | "Last" snap ("last one alive") | "last" token |
| 16 | Agent status snap ("Reyna is low / Jett is dead") | agent name + status verb |
| 17 | Enemy count ("three left on B") | count + location tokens |
| 18 | Self-status ("I'm low / I'm dead") | first-person + status |
| 19 | M1 slot grammar fallback | `_parse_callout_slots` (see §13) |

After each snap handler, the result is flavored via `_flavored(line, command, recent_lines)` which appends a context-appropriate tail.

### 12b. Economy callout — `_as_economy_callout`
Matches explicit eco vocabulary: "eco / save / bonus / full buy / force buy / half buy / light buy / rifle up / rifle round". Returns literal economic line.

---

## 13. M1 slot grammar — `_parse_callout_slots(payload)`

Every token in the payload must classify into one of these sets. At least 2 DISTINCT meaningful types required.

### Token classifier sets:

| Set name | Contents / meaning |
|---|---|
| `_M1_AGENTS` | Valorant roster canonical names (all 27) |
| `_M1_COUNT` | digit words + numeric forms: "one","two","three","four","five","six","seven","eight","nine","zero","1"–"9" + "all","both","solo","alone","everyone","triple","double","quad" |
| `_M1_DMG` | damage verbs: "hit","damage","hurt","shot","tap","tapped","tagged","clipped","melted","bopped","chunk","chunks","chunked","nicked" + damage nouns: "hp","health","shield","armor" + numerals |
| `_M1_LOC` | location tokens: site letters (A/B/C), named positions (mid/ct/t-side/…), direction words (left/right/flank/…), structure words (window/garage/stairs/…) |
| `_M1_ACTION` | action words: buy/plant/defuse/rotate/push/hold/play/cover/watch/anchor + `_ACTION_WORDS` set |
| `_M1_OWNER` | possession/ownership: "their","my","our","the","enemy","ally","teammate","friendly" |
| `_M1_CONNECTOR` | grammar connectors (non-meaningful): "is","are","was","were","at","on","in","to","and","with","but","a","an","the","have","has","got","get","be","been","being" |

**The >=2-meaningful-types rule:** a token classified as `_M1_CONNECTOR` or `_M1_OWNER` does NOT count toward the minimum. So "they are A" needs `_M1_LOC`(A) + `_M1_OWNER`(they) which counts 1 meaningful type — needs one more to pass. A payload "Jett hit 84" → `_M1_AGENTS`(Jett) + `_M1_DMG`(hit,84) = 2 types → passes.

**Multi-digit number handling (added 2026-06-18):** any multi-digit number (e.g., "84", "97") is now classified as `_M1_DMG` (previously only single-digit numbers were taken as count, causing damage values to bail as residual).

**Returns:** `Optional[tuple[str, ...]]` — tuple of classified slot strings, or `None` if not all tokens classify or <2 meaningful types.

---

## 14. Flavor system

### 14a. Flavor registers (7)

All pools live in `_ultron_pools.py`:

| Register | Pool var | Situation |
|---|---|---|
| `enemy` | `_FLAVOR_ENEMY` | tracking enemy positions/counts |
| `ult` | `_FLAVOR_ULT` | ult readiness callouts |
| `damage` | `_FLAVOR_DAMAGE` | damage dealt/taken reports |
| `utility` | `_FLAVOR_UTILITY` | ability/kit usage callouts |
| `careful` | `_FLAVOR_CAREFUL` | defensive / "watch out" calls |
| `command` | `_FLAVOR_COMMAND` | tactical directives / buy orders |
| `self` | `_FLAVOR_SELF` | self-status / positioning |

Each pool: tuple of short 1–2 sentence Ultron-persona flavor tails.

### 14b. Per-agent flavor — `AGENT_FLAVOR`

In `_agent_flavor.py`: 1628 curated entries, dict keyed by agent name → dict of situation → tuple of tails. Used when the callout addresses a specific agent.

### 14c. Multi-agent flavor — `MULTI_FLAVOR`

In `_multi_flavor.py`: flavor for 2+ agent situations.

### 14d. `_flavor_ctx(payload, addressee)` — context router

Coarse-routes payload text to a flavor register:
1. Checks `situation_for_payload(payload)` from `_tail_schema.py` (semantic tag matcher)
2. Maps situation → register
3. If agent-specific, looks up `AGENT_FLAVOR[addressee][situation]`
4. Falls back to general pool

### 14e. `_pick_flavor(payload, addressee, recent_lines)` → `Optional[str]`

Picks one tail from the resolved pool using `_pick_lru` (LRU anti-repeat with global `_LRU_COUNT`/`_LRU_SEEN`).

### 14f. `_join_tail(head, tail)` → `str`

Joins head + tail with exactly one space; handles trailing punctuation so the result reads naturally.

### 14g. `_flavored(line, command, recent_lines)` → `str`

Applies `_pick_flavor` and joins, ONLY if `flavor_tails_enabled()` returns `True`. When tails are off, returns `line` unchanged.

---

## 15. Flavor-OFF response set — `_flavor_off_response`

When `flavor_tails_enabled() == False`, `build_relay_line` checks this FIRST (before verbatim/snap/curated). Returns a response from a category-specific pool with no flavor tail, or `None` to let normal (tail-stripped) rendering proceed.

Pools defined directly in `relay_speech.py`:

| Pool var | Category | Size |
|---|---|---|
| `_FO_CLUTCH` | clutch confidence | ~6 lines |
| `_FO_FLAMING` | teammate flame | ~8 lines |
| `_FO_CRINGE` | cringe/awkward reactions | ~6 lines |
| `_FO_ARGUING` | argument / toxicity | ~6 lines |
| `_FO_SHUTUP` | "shut up" direction | ~6 lines |
| `_FO_STOP` | stop-command defiance | ~8 lines |
| `_FO_ENCOURAGE` | encouragement | ~8 lines |
| `_FO_FLAME_ENEMY` | enemy flame | ~8 lines |
| `_FO_FLAME_AGENT` | specific agent flame | ~6 lines |
| `_FO_SIMPLE` | generic simple relay | ~6 lines |

Helper `_fo_pick(pool, name, recent_lines)` applies LRU selection, optional `{name}` formatting.

---

## 16. Compound callouts — `_as_compound_callout`

Handles "Jett hit 84, Breach hit 97" (two+ facts in one utterance).

1. Splits payload on `_split_compound` (comma/and/plus/also delimiters)
2. Each piece is resolved with `_as_snap_callout` individually
3. If ALL pieces resolve deterministically → joins with `_join_tail` → returns `(det_line, None)`
4. If SOME pieces resolve → returns `(det_line, leftover)` — partial resolution; leftover goes back through `build_relay_line` recursively

---

## 17. Post-processing helpers

### `_strip_artifacts(line)` 
Strips control-token leakage ("/no_think", "<|im_end|>", etc.), newlines, leading/trailing quotes.

### `_ensure_addressee(line, command)`
If `command.addressee` is a named agent and the line doesn't open with their name, prepends it as a vocative: "Jett, <line>".

### `_repair_against_input(payload, line)`
Adaptive guardrail: checks that the model output kept key facts from the input (first-person forms, "last", count values, enemy-subject invariant). Reconstructs canonical form if not. No-op when model kept it.

### `_literal_relay(payload, recent_lines, addressee)` → `Optional[str]`
Returns payload as-is (after TTS fixes) with a short flavor tail. Used when the model would corrupt a tactical fact. Fastest deterministic path — "fact-perfect literal."

### `_cap_line(line, max_chars)` / `_cap_sentences(line, max_sentences=2)`
Length guardrails. `_cap_sentences` cuts at a whole-sentence boundary (2-sentence max for model output).

### `_strip_spurious_vocative(line, command)`
Drops a spurious leading vocative the 3B prepended to team-wide answers ("Jett, buy me…" when addressee=team).

### `_fix_proper_nouns(line)`
Corrects mangled Marvel/MCU proper nouns that Whisper or the model mangles ("sovokia" → "Sokovia").

### `_preserve_agent_names(want, line)`
Undoes a single-agent name swap (Chamber → KAY/O). `want` is the list of agents in the payload.

### `_fact_tokens(payload)` → `(nums, agents, locs, abils)`
Extracts concrete tactical fact tokens: counts/numbers, agent names, location tokens, ability tokens.

### `_output_keeps_facts(payload, line)` → `bool`
Checks that the model output preserved all fact-tokens from the payload. Returns `False` → trigger literal relay fallback.

### `_as_known_fact(command)` → `Optional[str]`
Checks payload against `_GK_FACTS` (28 curated general-knowledge question→answer pairs). Returns the curated answer if recognized, bypassing the model. Examples: "first president" → Washington, "how many planets" → 8.

---

## 18. SNAP_REGISTRY (data-driven extension contract)

Defined in `voice_lines.py`. Runtime-gated by env var `KENNING_SNAP_REGISTRY` (default ON). Checked inside `build_relay_line` at the morale/consolation phase.

### `SnapRule` dataclass
```python
@dataclass(frozen=True)
class SnapRule:
    name: str            # identifier (for logging)
    match: re.Pattern    # regex tested against the raw payload
    kind: str = "pool"   # "pool" | "head_tail"
    lines: tuple = ()    # for kind="pool": pool of full responses
    tails: tuple = ()    # for kind="head_tail": pool of tails
```

**kind="pool":** picks a random (LRU anti-repeat) line from `lines`.
**kind="head_tail":** echoes matched group 1 (capitalized) + random tail from `tails`. Example: input "nice try" → "Nice try. We take the next."

### Current `SNAP_REGISTRY` (4 rules, in order):
1. `clutch` — `_CLUTCH_RE` → `kind="pool"`, pool=`DEFAULT_CLUTCH_LINES`
2. `nice_try` — `_NICE_TRY_RE` → `kind="head_tail"`, tails=`_NICE_TRY_TAILS` (10 tails)
3. `consolation` — `_CONSOLATION_RE` → `kind="pool"`, pool=`DEFAULT_CONSOLATION_LINES`
4. `praise` — `_PRAISE_RE` → `kind="pool"`, pool=`DEFAULT_PRAISE_LINES`

**PRECEDENCE NOTE:** Rules are tried in order; FIRST match wins. Appending a new rule only works if no EARLIER rule already captures the trigger.

---

## 19. TARGET_SNAP_REGISTRY (target-based data-driven snaps)

### `TargetSnapRule` dataclass
```python
@dataclass(frozen=True)
class TargetSnapRule:
    name: str                    # == RelayCommand.directive value
    match: re.Pattern            # must capture group "target"
    team_lines: tuple = ()       # picked when target resolves to "team"
    agent_templates: tuple = ()  # {name} templates for a named agent
    skip_if_contains: tuple = () # lowercased phrases that disqualify
```

**Render logic** (`_render_target_registry`): 
1. Iterates `TARGET_SNAP_REGISTRY` in order
2. Tests `rule.match.search(payload)` (or `command.directive == rule.name`)
3. Checks `skip_if_contains` against raw payload
4. Resolves target via `_resolve_hello_target` → "team" or agent name
5. Picks line from `team_lines` (LRU anti-repeat) or formats `agent_templates` entry
6. Returns line or `None`

Also rendered by `_match_target_registry` for the matching phase.

### Current `TARGET_SNAP_REGISTRY` (2 rules):
1. `hello` — `_HELLO_RE` (captures `target`), skip_if_contains=("introduce",), team="Hello team.", agent="Hello, {name}."
2. `ask_day` — `_ASK_DAY_RE` (captures `target`), team=`_ASK_DAY_TEAM_LINES` (8 lines), agent=`_ASK_DAY_AGENT_TEMPLATES` (6 templates)

---

## 20. build_relay_line — full dispatch chain

**Signature:**
```python
def build_relay_line(
    command: RelayCommand,
    llm: Optional[object] = None,
    *,
    rephrase: bool = True,
    max_chars: int = MAX_RELAY_LINE_CHARS,
    recent_lines: Optional[Sequence[str]] = None,
    generate_fn: Optional[Callable[[str], Iterable[str]]] = None,
) -> str:
```

**Dispatch chain (in order; first return wins):**

1. **Flavor-OFF override** — if `not flavor_tails_enabled()`: call `_flavor_off_response(command, recent_lines)`. If non-None → `_cap_line` and return.

2. **Verbatim demand** — if `command.verbatim and command.payload`: return `_cap_line(_strip_artifacts(payload))`.

3. **TARGET_SNAP_REGISTRY** (Part C data-driven) — `_render_target_registry(command, recent_lines)`. If non-None → return.

4. **Hardcoded hello fallback** — if `directive == "hello"`: "Hello team." or "Hello, {agent}.". (Fallback when registry disabled.)

5. **Hardcoded ask-day fallback** — if `directive == "ask_day"`: pick from `_ASK_DAY_TEAM_LINES` or format `_ASK_DAY_AGENT_TEMPLATES`.

6. **Relay wrapper strip** — strips performative wrapper from payload ("bro relay that X" → "X"). One-time; not applied to verbatim.

7. **Curated COMMAND** — `_as_curated_command(command)`. Matches 50+ explicit curated patterns (in `_CURATED_PATTERNS` / `_ultron_commands.py`). No LLM. If non-None → return.

8. **Curated SOCIAL reaction** — `_as_curated_reaction(command)`. Teammate compliment/insult/surrender/praise. If non-None → return.

9. **Roast** — if `command.roast`: pick from `DEFAULT_ROAST_LINES`.

10. **Fun fact** — if `command.fun_fact`: pick from `DEFAULT_FUN_FACTS`.

11. **Morale compose** (compose + no directive + no context + morale payload) → pick from `DEFAULT_ENCOURAGEMENT_LINES`.

12. **Directive pools** (compose + directive) — `_DIRECTIVE_POOLS.get(directive)`. Dispatches greet/farewell/win/loss to curated set-piece pools.

13. **Calm-down** — if calm directive or calm payload: pick from `DEFAULT_CALM_LINES` with name formatting.

14. **Criticize directive** (`criticize:<name>`) → `DEFAULT_CRITICIZE_LINES.format(name=target)`.

15. **Flame enemy** (`flame_enemy`) → `_fo_pick(_FO_FLAME_ENEMY, ...)`.

16. **Stop command** (`stop_command`) → `_fo_pick(_FO_STOP, agent, ...)`.

17. **Compliment directive** (`compliment:<name>`) → `DEFAULT_COMPLIMENT_LINES.format(name=target)`.

18. **Identity question** — if payload/context is identity question: classify + pick from `IDENTITY_POOLS` (from `_ultron_identity.py`). Named asker gets vocative prefix.

19. **Known GK fact** — `_as_known_fact(command)`: 28 curated correct answers. Non-verbatim only.

20. **Short morale phrase** — `_is_morale_phrase(payload)` → `DEFAULT_ENCOURAGEMENT_LINES`.

21. **SNAP_REGISTRY** (Part C data-driven) — `_apply_snap_registry(payload, recent_lines)`. First matching SnapRule → `_name_social_snap(result, command)`.

22. **Clutch snap** (hardcoded fallback) — `_as_clutch(payload, recent_lines)`.

23. **Consolation/praise** (hardcoded fallback) — `_as_consolation_or_praise(payload, recent_lines)`.

24. **Deterministic SNAP callout** — `_as_snap_callout(command, recent_lines)`. Full 20-handler position/count/damage/ult/possession/movement/ability/M1-slot chain.

25. **Compound callout** — `_as_compound_callout(command, recent_lines)`.
    - Fully resolved → return `det_line`.
    - Partially resolved → recursively call `build_relay_line(leftover)` and join with `_join_tail`.

26. **Tactical literal pre-route** — if payload has `tactical >= 1` (count/location/ability token): `_literal_relay(payload, recent_lines, addressee)`. Bypasses LLM entirely for single-fact tactical lines.

27. **LLM rephrase** (if `rephrase=True` and `llm` available):
    - If ANSWER PATH applies (`build_answer_call` non-None — Marvel/think-and-respond): call `llm.generate_stream` with focused per-type system prompt + constrained sampling.
    - Otherwise: call `llm.generate_stream` with `_build_rephrase_prompt(command, recent_lines)` + `_RELAY_REPHRASE_SYSTEM` + `_RELAY_SAMPLING` (fully isolated, `suppress_memory_context=True`, `record_history=False`).
    - Safety nets: reject verbatim-recent echo; reject "switch" position hallucination.

28. **Fallback** (`_fallback_line(command)`) — generic morale line if LLM produces nothing.

**Post-LLM processing (always applied):**
- `_strip_artifacts(line)` — strip control tokens
- `_cap_sentences(line, max_sentences=2)` — 2-sentence cap for model output
- `_strip_spurious_vocative(line, command)`
- `_fix_proper_nouns(line)`
- `_repair_against_input(payload, line)` — for plain (non-compose, non-context, non-directive) callouts only
- `_output_keeps_facts` check → literal relay abstention if facts dropped
- `_preserve_agent_names(want, line)`
- `_ensure_addressee(line, command)`
- `_cap_line(line, max_chars)`

---

## 21. Team DSP — `_shape_for_team(samples, sr)`

Applied ONLY on the live Valorant team path inside `play_to_device`; speaker/OBS feeds never call it. Gated by `KENNING_RELAY_TEAM_DSP` env var (default ON).

**Chain (in order, each independently gated):**

1. **Rumble HP + optional LP** (`_team_bandshape`) — gated by `KENNING_RELAY_COMMS_FILTER` (default ON). Butterworth 2nd-order high-pass at `KENNING_RELAY_HIGHPASS_HZ` (default 100 Hz). Optional low-pass at `KENNING_RELAY_LOWPASS_HZ` (default 0 = OFF).

2. **Static RMS normalize** (`_team_normalize`) — gated by `KENNING_RELAY_NORMALIZE` (default ON). Voiced-frame RMS normalize to `KENNING_RELAY_TARGET_DBFS` (default -20 dBFS). Gain clamped ±12 dB. Uses voiced mask (gate -50 dBFS) to avoid boosting silence gaps.

3. **Comfort noise floor** (`_team_comfort_noise`) — gated by `KENNING_RELAY_COMFORT_NOISE` (default ON). Adds continuous pinkish room-tone at `KENNING_RELAY_NOISE_DBFS` (default -58 dBFS, hard-capped at -52 dBFS) so Vivox's noise-suppressor has a stable reference.

4. **Tanh soft-clip ceiling** (`_team_softclip`) — gated by `KENNING_RELAY_SOFTCLIP` (default ON). Memoryless tanh ceiling at `KENNING_RELAY_CEILING_DBFS` (default -1 dBFS). Zero latency.

**Root cause context:** VoiceMeeter Remote-API probe found B1 bus (Valorant mic) at -21.14 dB vs B2 (real mic) at 0.0 dB. Vivox AGC applies huge makeup gain → lifts codec noise floor → "gritty/low-quality" sound.

---

## 22. play_to_device — additional details

After `_shape_for_team`, the flow in `play_to_device`:

1. Polyphase resample (scipy `resample_poly`) to device's native rate via `sounddevice.query_devices` — removes double-resample artifact on VoiceMeeter endpoints.
2. Mono → stereo widening (`np.column_stack`) before opening stream — avoids VoiceMeeter backend 1→2 up-mix static.
3. Opens via `make_output_stream` (WASAPI low-latency).
4. If `cancel_event` given: chunked write at `chunk_ms` (default 100ms) granularity; aborts on set (barge-in support).

---

## 23. Relay rephrase prompt — `_RELAY_REPHRASE_SYSTEM` / `_build_rephrase_prompt`

`_RELAY_REPHRASE_SYSTEM` (≈2300 chars): Ultron persona prompt establishing:
- Character: logical, analytical, dry, cold, superior — NEVER warm/encouraging/cheerful
- "You are a weapons AI" framing
- Anti-filler, anti-padding, anti-human-speech rules
- Relay-specific rules: relay the FACT, not your reaction; keep it first-person if user said "I"; keep locations/counts exact; don't add agents not mentioned

`_build_rephrase_prompt(command, recent_lines)`: builds the user-turn prompt including:
- `addressee` context (team or agent name)
- `context` clause if present
- `directive` if present
- Recent lines (last 5, as few-shot anti-repeat examples)
- Payload to rephrase

`_RELAY_SAMPLING`: constrained sampling params — tight `max_tokens` (~60), stop sequences, `min_p` to prevent rambling.

---

## 24. Curated command infrastructure

### `_CURATED_PATTERNS` (50+ patterns) + `_as_curated_command`

Defined at bottom of `relay_speech.py` (~lines 5351–5575). Each entry: (regex, response_pool_or_literal). Categories include:
- Agent kit questions ("what does Sage do", "how does Jett's dash work")
- Economy decisions ("should I buy", "what should I buy")
- Map-specific callouts ("where is this", "where are the spikes")
- Meta questions ("how do I improve", "what rank are you")
- Game-state reads ("are they eco", "are they saving")

Imports from `_ultron_commands.py` (not read directly but referenced as `COMMAND_RESPONSES`, `COMMAND_SCOPE`, `COMMAND_SLOT`).

### `_as_curated_reaction` + `_ultron_social.py`

Social reaction pools: `classify_social_reaction(payload)` classifies into categories (compliment/insult/surrender/cringe/arguing/shutup). Each category has an addressee-adapted pool from `SOCIAL_POOLS`. Returns None for non-social payloads.

---

## 25. relay_route_info — route classification

`relay_route_info(command) -> dict`: returns metadata about how a command would route. Fields include:
- `route`: one of "verbatim", "snap", "curated", "reaction", "morale", "compose", "greet", "identity", "gk_fact", "literal", "rephrase", "fallback"
- `snap_type`: which specific snap matched (if route="snap")
- `addressee`: resolved addressee

Used by the trace/corpus tooling for behavioral analysis.

---

## 26. is_complete_tactical_callout

`is_complete_tactical_callout(payload) -> bool`: checks if a payload is a "complete" tactical callout that can snap deterministically (no LLM needed). Used as a pre-filter in the orchestrator for latency routing.

Returns `True` if: all tokens classify in M1 grammar AND >=2 meaningful types AND no off-snap content (no question words, no banter verbs, no "why/how/what" lead).

---

## 27. LRU anti-repeat system

Global module-level state:
- `_LRU_COUNT`: int — max number of recent selections to remember
- `_LRU_SEEN`: dict[str, deque] — per-pool (identified by pool id()) recent picks

`_pick_lru(pool, recent_lines)`: picks the next line from `pool` that:
1. Is not in `_LRU_SEEN[pool_id]` (global anti-repeat)
2. Is not in `recent_lines` (session anti-repeat)
Falls back to random if all lines are in the LRU window.

`pick_line(pool, recent_lines)` and `pick_roast_line(pool, recent_lines)` are the public wrappers.

---

## 28. Thinking mode toggle

`KENNING_THINKING_MODE` env var (or runtime toggle via `match_thinking_toggle`). When ON: the relay rephrase path may use extended thinking in `llm.generate_stream` calls. When OFF: `enable_thinking=False` is always passed (the default, and what the relay uses regardless — "thinking" here refers to whether the orchestrator as a whole uses thinking mode, not the relay specifically; the relay always passes `enable_thinking=False`).

---

## 29. Key gotchas for Ultron 1.0 design

1. **`_RELAY_REPHRASE_SYSTEM` is 2300 chars** — in an LLM-centric 1.0 design, this becomes a routing prompt or exemplar-injection system prompt; keep the Ultron voice rules but shift from "rephrase callout" to "generate callout in Ultron voice from intent+slots".

2. **26-step dispatch chain** — each step is a snap that can be an exemplar in an LLM context. The chain's implicit taxonomy (morale / social / tactical / identity / compose) becomes explicit prompt routes in 1.0.

3. **M1 slot grammar is hard-coded vocabulary** — in 1.0, the slot extractor becomes an LLM-side slot-fill task; the _M1_* sets become the recognized vocab (few-shot examples). The >=2-type constraint becomes an LLM confidence gate.

4. **Fact preservation (_output_keeps_facts / _repair_against_input)** — critical correctness mechanism. In 1.0, these become unit-tested post-processing validators applied on LLM output; they are NOT removed.

5. **SNAP_REGISTRY is the extension contract** — adding SnapRule/TargetSnapRule to `voice_lines.py` is already "LLM-lite" (data-driven, no code change). In 1.0, these rules become in-context exemplars that steer an LLM to the same behavior.

6. **Flavor-OFF path is a complete parallel surface** — when tails are off, every category has its own pool. In 1.0, this becomes a system-prompt flag that suppresses the tail-generation step.

7. **`_looks_like_slot_callout`** — referenced in memory/docs as a function in the orchestrator (stream-build branch `da28d22`), but NOT present in the current worktree branch (`infallible-kepler-0a865d`). It was a pre-semantic-router forced-relay gate for bare slot callouts. This pattern is relevant to 1.0 design: the deterministic slot-callout pre-route should survive into the new architecture as a fast path.

8. **`recent_lines=None` for compound leftovers** — explicitly set to None for the recursive compound call to prevent LRU bleed from a prior line's content contaminating the compound tail (audit #0781 fix).

9. **`suppress_memory_context=True` on all relay LLM calls** — without this, the engine prepends the running conversation history and the model answers the conversation instead of rephrasing the callout. Critical isolation requirement for 1.0.

10. **`generate_fn` test seam** — any callable that takes a prompt string and returns an iterable of token strings. The test suite (trace/corpus tools) uses this to bypass the real LLM.

---

## 30. File sizes and extension points

| File | Lines | Role |
|---|---|---|
| `relay_speech.py` | ~6752 | All relay snap matchers, build_relay_line, DSP, playback |
| `voice_lines.py` | ~376 | Social-snap regexes + pools, SNAP_REGISTRY, TARGET_SNAP_REGISTRY |
| `_ultron_pools.py` | unknown | 7 flavor tail pools (_FLAVOR_ENEMY etc.) |
| `_agent_flavor.py` | unknown | 1628 per-agent situation tails |
| `_multi_flavor.py` | unknown | Multi-agent situation tails |
| `_tail_schema.py` | unknown | Tail entry library, `situation_for_payload`, `build_active_tags` |
| `_tail_selector.py` | unknown | `select_tail` (semantic sidecar for tail selection) |
| `_ultron_social.py` | unknown | `classify_social_reaction`, SOCIAL_POOLS |
| `_ultron_commands.py` | unknown | COMMAND_RESPONSES, COMMAND_SCOPE, COMMAND_SLOT |
| `_ultron_answer.py` | unknown | `build_answer_call`, `marvel_topic`, `strip_think_respond` |
| `_ultron_identity.py` | unknown | IDENTITY_POOLS, `classify_identity_question`, `is_model_leak_probe` |
| `_ultron_setpieces.py` | unknown | DEFAULT_*_LINES pools (greeting/victory/defeat/farewell/identity/consolation/praise/encouragement) |

**To add a new payload snap:** append a `SnapRule` to `SNAP_REGISTRY` in `voice_lines.py`.
**To add a new target snap:** append a `TargetSnapRule` to `TARGET_SNAP_REGISTRY` in `voice_lines.py`.
**To add a new curated command:** add an entry to `_CURATED_PATTERNS` in `relay_speech.py` or the relevant dict in `_ultron_commands.py`.
**To add a flavor tail pool:** add entries to `_ultron_pools.py` or `_agent_flavor.py`.
