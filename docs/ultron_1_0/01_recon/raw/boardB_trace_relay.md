# B2: TRACE "tell my team rush B", "they are pushing A", bare "cypher is flank"

## Overview

This document traces three canonical relay utterances through the full pipeline, from raw STT
transcript to spoken output on the VoiceMeeter device. The three examples cover the three
primary relay paths that differ in normalize_command behavior:

1. **"tell my team rush B"** — explicit group relay lead; strict matcher direct hit.
2. **"they are pushing A"** — bare enemy callout; `_CALLOUT_SIGNAL` fires, relay-intent gate
   consulted (STRONG_CALLOUT_RE misses "pushing" verb), gate returns True → "tell my team"
   prepended.
3. **bare "cypher is flank"** — agent name + bare action; `_AGENT_SIGNAL` and `_CALLOUT_SIGNAL`
   both fire, relay-intent gate consulted, likely returns True → "tell my team" prepended;
   `_as_enemy_action()` produces "Cypher is flanking." via bare-verb normalization.

All three paths converge at `match_relay_command` → `_RELAY_PATTERNS[0]` → `build_relay_line`
→ `_as_snap_callout()` → TTS synthesis → VoiceMeeter device playback. They differ only in
what happens inside `normalize_command` before the strict matcher sees the text.

---

## Files & key symbols (path:line tables)

| File | Role |
|------|------|
| `src/kenning/pipeline/orchestrator.py` | Turn entry; `run()` calls normalize then `_maybe_handle_relay_speech` |
| `src/kenning/audio/command_normalizer.py:975` | `normalize_command()` — all pre-routing normalization |
| `src/kenning/audio/command_normalizer.py:121` | `_strip_leading_junk()` — wake homophones and filler removal |
| `src/kenning/audio/command_normalizer.py:215` | `_canonicalize_directive_lead()` — mangled/doubled relay-verb rewrite |
| `src/kenning/audio/command_normalizer.py:293` | `_strip_scaffold()` — numbered prefix, say-directive lead, nested verbs |
| `src/kenning/audio/command_normalizer.py:904` | `recover_relay_lead()` — bare callout → prepend "tell my team" |
| `src/kenning/audio/command_normalizer.py:558` | `_HAS_RELAY_LEAD` — already a relay lead (skip recovery) |
| `src/kenning/audio/command_normalizer.py:646` | `_NOT_A_CALLOUT` — questions / Spotify / identity / desktop → leave verbatim |
| `src/kenning/audio/command_normalizer.py:690` | `_REPORTED_RESPOND_RE` — reported-speech+directive → leave verbatim |
| `src/kenning/audio/command_normalizer.py:604` | `_WANT_TEAM` — "I want my team to X" recovery |
| `src/kenning/audio/command_normalizer.py:635` | `_TRAILING_RELAY_TAIL` — "..., tell my team." trailing recovery |
| `src/kenning/audio/command_normalizer.py:614` | `_TEAM_LEAD` — "my team X" / "the squad X" recovery |
| `src/kenning/audio/command_normalizer.py:818` | `_STRONG_CALLOUT_RE` — unambiguous shapes that bypass the relay-intent gate |
| `src/kenning/audio/command_normalizer.py:742` | `_CALLOUT_SIGNAL` — broad keyword detector triggering relay-intent gate |
| `src/kenning/audio/command_normalizer.py:807` | `_AGENT_SIGNAL` — roster agent-name detector |
| `src/kenning/audio/command_normalizer.py:860` | `_NARRATION_MUSING_RE` — first-person musing fast-path block |
| `src/kenning/audio/_relay_intent.py:158` | `RelayIntentGate` — scores utterance vs. POSITIVE/NEGATIVE clouds |
| `src/kenning/audio/_relay_intent.py:216` | `RelayIntentGate.decide()` → True/False/None |
| `src/kenning/audio/_relay_intent.py:35` | `RELAY_POSITIVE_EXEMPLARS` — ~65 curated relay exemplars |
| `src/kenning/audio/_relay_intent.py:69` | `RELAY_NEGATIVE_EXEMPLARS` — ~55 curated anti-relay exemplars |
| `src/kenning/audio/_relay_intent.py:241` | `relay_intent_ok()` — module-level convenience called by recover_relay_lead |
| `src/kenning/audio/relay_speech.py:1704` | `match_relay_command()` — strict relay matcher (30+ handlers in priority order) |
| `src/kenning/audio/relay_speech.py:119` | `_RELAY_PATTERNS` — 13 regex patterns for explicit-lead group relay forms |
| `src/kenning/audio/relay_speech.py:72` | `_GROUP` / `_GROUP_PRON` / `_GROUP_WORDS` — group noun/pronoun definitions |
| `src/kenning/audio/relay_speech.py:1060` | `_NARRATION_LEAD_RE` — search-anywhere narration guard inside match_relay_command |
| `src/kenning/audio/relay_speech.py:1097` | `_LEADING_RELAY_RE` — exempts explicit-lead commands from narration gate |
| `src/kenning/audio/relay_speech.py:1360` | `_SITE_CALLOUT_CUES` — frozenset enabling site-letter "A/B/C" as payload content |
| `src/kenning/audio/relay_speech.py:1372` | `_payload_has_content()` — validates payload has a real message |
| `src/kenning/audio/relay_speech.py:1280` | `RelayCommand` — frozen dataclass: payload, addressee, compose, verbatim, context, directive |
| `src/kenning/audio/relay_speech.py:3234` | `_ENEMY_LEAD_RE` — "they are/they're X" prefix handler |
| `src/kenning/audio/relay_speech.py:3245` | `_as_enemy_status()` — "they are X" → "They're X." (from the ENEMY block) |
| `src/kenning/audio/relay_speech.py:4102` | `_as_enemy_action()` — agent/count + bare action → "Cypher is flanking." |
| `src/kenning/audio/relay_speech.py:3539` | `_ACTION_WORDS` — frozenset of -ing action verbs; "flanking" is in here |
| `src/kenning/audio/relay_speech.py:3549` | `_BARE_TO_ING` — bare-verb → -ing map ("flank" → "flanking") |
| `src/kenning/audio/relay_speech.py:4284` | `_parse_callout_slots()` — M1 slot grammar (LAST fallback) |
| `src/kenning/audio/relay_speech.py:4327` | `_as_snap_callout()` — 15+ deterministic handlers in priority order |
| `src/kenning/audio/relay_speech.py:3564` | `_IMPERATIVE_VERBS` — movement/ability verbs for team-directive handler |
| `src/kenning/audio/relay_speech.py:3584` | `_TEAM_DIRECTIVE_VERBS` — extended set; "rush" IS in here (via _IMPERATIVE_VERBS) |
| `src/kenning/audio/relay_speech.py:4677` | `_MOVE` dict — single-word movement shortcuts ("rush" → "Rush." bare only) |
| `src/kenning/audio/relay_speech.py:4698` | Team-directive handler — first word in _TEAM_DIRECTIVE_VERBS + 1-7 tokens |
| `src/kenning/audio/relay_speech.py:6012` | `build_relay_line()` — orchestrates snap/curated/LLM output |
| `src/kenning/audio/relay_speech.py:2081` | `_REPHRASE_PROMPT` / `_RELAY_REPHRASE_SYSTEM` — huge LLM system prompt |
| `src/kenning/audio/relay_speech.py:5977` | `is_complete_tactical_callout()` — optional early-endpoint gate (slot grammar) |
| `src/kenning/audio/routing_rules.py:47` | `AGENTS`, `MAPS`, `WEAPONS`, `ABILITIES`, `LOCATIONS`, `TERMS` — Valorant vocabulary |
| `src/kenning/audio/routing_rules.py:92` | `AGENT_MISHEARS`, `LOCATION_MISHEARS` — curated STT mishear maps |
| `config.yaml:1827` | `relay_speech.*` — enabled, output_device, rephrase, max_line_chars, addressee_names |

### Key symbol quick-reference

```
normalize_command()                   command_normalizer.py:975
  └── _strip_leading_junk()           command_normalizer.py:121
  └── correct_callout_stt()           _stt_correct.py (routing_rules SECTION 1 vocabulary)
  └── _canonicalize_directive_lead()  command_normalizer.py:215
  └── _strip_scaffold()               command_normalizer.py:293
  └── recover_relay_lead()            command_normalizer.py:904
        ├── _HAS_RELAY_LEAD           command_normalizer.py:558    (already relay → skip all)
        ├── _NOT_A_CALLOUT            command_normalizer.py:646    (question/Spotify/identity)
        ├── _REPORTED_RESPOND_RE      command_normalizer.py:690    (context+directive)
        ├── _WANT_TEAM                command_normalizer.py:604    ("I want my team to X")
        ├── _TRAILING_RELAY_TAIL      command_normalizer.py:635    ("..., tell my team")
        ├── _TEAM_LEAD_NOVERB         command_normalizer.py:624    ("on my team X")
        ├── _TEAM_LEAD                command_normalizer.py:614    ("my team X")
        ├── _STRONG_CALLOUT_RE        command_normalizer.py:818    (bypass gate)
        └── _CALLOUT_SIGNAL / _AGENT_SIGNAL → relay_intent_ok()   _relay_intent.py:241

match_relay_command()                 relay_speech.py:1704
  ├── PRIORITY INTERCEPTS (before narration gate)
  │     ├── _BARE_CLUTCH_RE           relay_speech.py:302
  │     └── _BARE_ENCOURAGE_RE        relay_speech.py:317
  ├── NARRATION GATE
  │     └── _NARRATION_LEAD_RE        relay_speech.py:1060 (search-anywhere)
  ├── SPECIAL PURPOSE MATCHERS
  │     ├── _ROAST_RE / _FLAME_ENEMY_RE / _STOP_CMD_RE / _CRITICIZE_RE / _COMPLIMENT_RE
  │     ├── _AGENT_SNAP_RE / _FUN_FACT_RE / _PROMO_RE
  │     ├── greet / farewell / compose / calm / ff-request patterns
  │     ├── _match_think_respond / _match_reported_question / _match_reported_reaction
  ├── GROUP CALLOUT PATTERNS          relay_speech.py:119 (13 explicit-lead patterns)
  ├── NAMED ADDRESSEES                relay_speech.py:932
  ├── CONTEXT+DIRECTIVE               relay_speech.py:1444
  └── FALLBACK FORMS                  relay_speech.py:800-2073

build_relay_line()                    relay_speech.py:6012
  ├── flavor-OFF override             (voice_lines.py social pools)
  ├── verbatim path
  ├── snap registry / hello / ask-day / wrapper strip
  ├── curated command / reaction / roast / morale
  ├── _as_snap_callout()              relay_speech.py:4327
  │     ├── named branch / question / agent-select / thank-you / careful
  │     ├── death / fp-lead / self-have / count / spike / ult / damage
  │     ├── agent utility / agent position / agent action
  │     ├── echo-enemy / echo-our / echo-sound / economy
  │     ├── _MOVE dict (bare single verbs)
  │     ├── _as_enemy_status() (they-lead)   relay_speech.py:3245
  │     ├── _as_enemy_action()              relay_speech.py:4102 (agent+bare-action)
  │     ├── _as_agent_position()            relay_speech.py:4068 (agent+place)
  │     ├── team-directive handler          relay_speech.py:4698 (imperative+object)
  │     └── _parse_callout_slots()          relay_speech.py:4284 (M1 grammar, last)
  ├── _as_compound_callout()          relay_speech.py:4780
  ├── _literal_relay()                (tactical token → faithful literal)
  └── LLM rephrase / fallback         relay_speech.py:6324+
```

---

## Control/data flow

### Stage 0: Turn entry (orchestrator.py)

After the addressing gate fires (wake word required; `config.yaml addressing.follow_up_enabled`
defaults to False), the raw STT transcript is recorded to dialogue history FIRST (real words),
then `normalize_command` is called:

```
raw STT → _record_dialogue_turn("user", user_text)
         → normalize_command(user_text)
         → user_text updated with normalized form (if changed)
         → dispatch stack → _maybe_handle_relay_speech()
```

`_maybe_handle_relay_speech` (orchestrator.py:3388) tries up to 4 STT repair variants in
order, calling `match_relay_command()` on each until one returns non-None. On match,
calls `build_relay_line()`, synthesizes, then plays on the VoiceMeeter Input virtual strip.

---

### Stage 1: normalize_command() — command_normalizer.py:975

Each step is cheap (~tens of microseconds). Idempotent: already-clean text returns unchanged.

1. **Bare greeting guard** (line 990): verbatim if text is a bare greeting ("hello", "hey").

2. **_strip_leading_junk()** (line 992): iteratively strips leading wake homophones
   (`_WAKE_HOMOPHONES` = 20+ strings: "ultron|tron|ron|ron|on|...") and filler tokens
   (`_FILLER` = "hey|ok|uh|um|bro|dude|yo|..."). Never empties the string.

3. **_RUNON_TEAM_LEAD_RE** (line 998): "Tellmyteam" → "tell my team".

4. **_REPEAT_MISHEAR** (line 1004): "Pete to my team X" → "repeat to my team X".

5. **_TEAM_POSSESSIVE** (line 1005): "my team's X" → "my team X".

6. **_canonicalize_directive_lead()** (line 1011): rewrites mangled or doubled relay-verb lead.
   The outer lead is checked against `_ANY_TEAM_LEAD_OUTER_RE` (valid team verb → keep, strip
   stacked inner lead) or `_MANGLED_TEAM_LEAD_RE` (mangled → rewrite to "tell my team ").
   Examples: "Call my team X" → "tell my team X"; "I told my team X" → "tell my team X".

7. **_GIVE_TEAM_TO_RE** (line 1014): "give my team to X" → "tell my team X".

8. **_DROP_POSSESSIVE_RE** (line 1017): "drop me his Sheriff" → "drop me your Sheriff".

9. **_BARE_ASK_RE** (line 1020): "ask if anyone has ult" → "ask my team if anyone has ult".

10. **_SOMEONE_LEAD_RE** (line 1021): "tell someone to anchor" → "tell my team someone to anchor".

11. **_strip_scaffold()** (line 1026): strips numbered prefixes, say-directive lead-ins, wrapper
    leads, nested relay verbs, embedded fillers.

12. **_WORD_FOR_WORD** (line 1027): "tell my team verbatim X" → "say exactly to my team X".

13. **_resolve_disfluency()** (line 1033): self-correction markers → final intent.

14. **_strip_possessive_names()** (line 1034): "relay to my Sova" → "relay to Sova".

15. **_collapse_multi_addressee()** (line 1035): "tell Sage and Clove X" → "tell my team X".

16. **Zero-mistakes gate** (line 1042): if text matches question/Spotify/identity/think-respond
    patterns, return VERBATIM (no STT correction and no relay-lead recovery).

17. **correct_callout_stt()** (line 1048): Valorant vocab correction. Uses `AGENT_MISHEARS`
    (routing_rules.py:92) for single-word agent mishears, location mishears, phonetic snapping,
    and context rules. "cypher" → "Cypher" (capitalized canonical form).

18. **KAY/O artifact collapse** (line 1052): "KAY/O O" → "KAY/O".

19. **recover_relay_lead()** (line 1053): bare-callout relay-lead recovery. See detailed
    breakdown below.

---

### recover_relay_lead() — command_normalizer.py:904

Priority order of decision points:

```python
# Guard 1: already a valid relay/compose/soundboard lead?
if _HAS_RELAY_LEAD.match(s): return text
# _HAS_RELAY_LEAD = "^(?:tell|say|let|warn|inform|remind|wish|ask|relay|repeat|echo|...)..."
# "tell my team rush B" fires this guard → return immediately.

# Guard 2: question / Spotify / identity / desktop?
if _NOT_A_CALLOUT.match(s): return text

# Guard 3: context+directive (reported speech + respond/calm/...)?
if _REPORTED_RESPOND_RE.search(s): return text

# Recovery 1: "I want my team to X" → extract directive + intent gate
if mw := _WANT_TEAM.match(s): ...

# Recovery 2: trailing relay command ("..., tell my team.")
if mt := _TRAILING_RELAY_TAIL.search(s): ...

# Recovery 3: "on my team X" / "to the squad X"
if mn := _TEAM_LEAD_NOVERB.match(s): ...

# Recovery 4: "my team X" / "the squad X" (verb dropped)
if _TEAM_LEAD.match(s): return "tell " + s

# Recovery 5: STRONG callout shapes → BYPASS relay-intent gate
if _STRONG_CALLOUT_RE.match(s) and not _NARRATION_MUSING_RE.match(s):
    return "tell my team " + s

# Recovery 6: keyword or agent signal → narration check + relay-intent gate
if _CALLOUT_SIGNAL.search(s) or _AGENT_SIGNAL.search(s):
    if _NARRATION_MUSING_RE.match(s): return text          # musing → leave as-is
    verdict = relay_intent_ok(s)                           # EmbeddingGemma gate
    if verdict is False: return text                       # gate vetoed → conversational
    # True (relay) or None (sidecar down → fail-open, keep keyword behavior)
    return "tell my team " + s

return text   # no signal → leave unchanged
```

**`_STRONG_CALLOUT_RE`** (command_normalizer.py:818) — unambiguous shapes, start-anchored:
- Sound: "I hear / footsteps / I heard"
- Enemy state: `(?:they|they're|the\s+enemy|enemy|enemies)\s+(?:have|has|bought|saved|forced|
  forcing|reset|eco'd|need|needs|will|won't|gonna|going\s+to|about\s+to|never|always|usually|
  crossed|wrapped|faking|re-hit|committing|splitting|playing|posting|camping|holding|waiting|
  saving\s+op|off\s+spike|all\s+there|could\s+be|may\s+be|might\s+be|tripped|out)\b`
- Count+word: bare count token (one/two/…/six or digit) + any following word
- Agent+tactical suffix: roster-agent + one of (main|site|long|short|mid|heaven|hell|window|
  garage|cat|plat|connector|link|ramp|market|sewer|spawn|cubby|elbow|pit|rafters|stairs|ult|
  ulted|ulting|walled|smoked|flashed|darted|caged|stunned|droned|naded|mollied|half|low|
  one\s+shot|dead|down|cracked|tree|nest|snake|baiting|baited|baits|flanking|lurking|peeking|
  rotating|pushing)
- "spike"

Key observation: `_STRONG_CALLOUT_RE` requires specific verb/suffix pairs. **"they are pushing"**
misses because "are" + "pushing" is not in the enemy-state verb list (which has "have/has/
bought/..." but NOT "are pushing"). **"Cypher is flank"** misses because "flanking" IS listed
but "flank" (bare stem) is not in the suffix list.

**`_CALLOUT_SIGNAL`** (command_normalizer.py:742) — broad keyword set (~80+ terms): enemy/
hostile/spotting verbs, ability names, location words, self-status phrases, order/morale words,
counts, weapons. Includes: `push|pushed|pushing`, `flank|flanking`, `rotate|rotating`, etc.

**`_AGENT_SIGNAL`** (command_normalizer.py:807): any of the 29+ canonical roster agent names.

**`_NARRATION_MUSING_RE`** (command_normalizer.py:860) — start-anchored:
- "I should/wish/could/never/keep/was going to ... tell/say/relay"
- "I told my team" (past recount), "I've been wanting to tell"
- "should I / do I / how do I ... tell/relay"
- "part of me wants to", "one of my biggest problems"
- "chat/stream/viewers says ... respond"

**`relay_intent_ok()`** (`_relay_intent.py:241`) → `RelayIntentGate.decide()` (line 216):
- Reuses the command_router's singleton EmbeddingBackend (no extra sidecar call per turn).
- `score(text)` → `(max(pos_cosines), max(neg_cosines))`.
- `decide(text)` → True if `(pos_sim - neg_sim) >= 0.06`, False otherwise, None if sidecar down.
- **FAIL-OPEN**: None → caller falls through to "tell my team " prepend (keyword behavior kept).
- Applied ONLY to the bare-callout branch (Recovery 6). Explicit leads skip the gate entirely.

---

### Stage 2: match_relay_command() — relay_speech.py:1704

Priority order of matchers (first non-None return wins):

1. `_BARE_CLUTCH_RE`: "I got this", "I'll clutch" — team relay without lead.
2. `_BARE_ENCOURAGE_RE`: "encourage the team" — compose=True.
3. **NARRATION GATE**: `_NARRATION_LEAD_RE.search()` AND NOT `_LEADING_RELAY_RE.match()` → None.
4. `_match_repeat_command()`: "repeat to my team X" → verbatim.
5. `_ROAST_RE`, `_FLAME_ENEMY_RE`, `_STOP_CMD_RE`, `_CRITICIZE_RE`, `_COMPLIMENT_RE`.
6. `_AGENT_SNAP_RE`: "Clove nice try" → named addressee + snap.
7. `_FUN_FACT_RE`, `_PROMO_RE`: fun facts, stream promo.
8. Target-snap registry, hello/ask-day/greet/farewell.
9. Compose patterns, calm, FF request.
10. Think-and-respond, reported question, reported reaction.
11. **GROUP CALLOUT PATTERNS** (line 1960): loop over 13 `_RELAY_PATTERNS`. First match wins.
    - `_RELAY_PATTERNS[0]` = starts with tell/warn/inform/let/ask etc. + group noun.
    - payload = `m.group("payload").strip()`.
    - Strip leading "to " (`^to\s+`), verbatim suffix/prefix markers.
    - `_payload_has_content(payload)` → None if empty/junk.
    - Returns `RelayCommand(payload=payload, verbatim=verbatim)`.
12. Named addressees, context+directive.
13. `_ASK_OPEN_RE`, `_SAY_YESNO_RE`, `_BARE_SAY_RE`, `_ECONOMY_CALLOUT_RE`, `_DROP_WEAPON_RE`.
14. `_match_imperative_directive()`, `_extract_bare_verbatim()`.

**`_payload_has_content()`** (line 1372):
- 2+ words → True (unless all are junk words in `_JUNK_SINGLE_WORDS`).
- Single word → True only if in `_SHORT_CALLOUTS` ("eco op go gg ace...") or len≥4 and not junk.
- **Site-letter rescue** (line 1389, F2 fix, 2026-06-18): if last token is "a"/"b"/"c" AND
  second-to-last is in `_SITE_CALLOUT_CUES`, treat as content. This rescues "they are A",
  "rotate to A", "pushing A". `_SITE_CALLOUT_CUES` (line 1360) includes: are, is, re, at, on,
  in, to, into, onto, toward, towards, push, pushing, pushed, hold, holding, rotate, rotating,
  rush, rushing, go, going, hit, hitting, take, taking, split, swing, swinging, cross, crossing,
  head, heading, defending, defend, one, two, three, four, five, both, all.

---

### Stage 3: build_relay_line() → _as_snap_callout() — relay_speech.py:6012

`build_relay_line` dispatches through ~25 stages (see symbol table). All three traces fall
through to `_as_snap_callout()` at stage 23 (relay_speech.py:6270).

`_as_snap_callout()` (relay_speech.py:4327) — priority sub-handlers:

1. Named addressee branch.
2. `_as_question_relay()` — ask-form.
3. `_AGENT_SELECT_FULL_RE` — draft role request.
4. `_THANK_YOU_RE` — gratitude.
5. careful / death / `_FP_LEAD_RE` / "I have X" / "I saw N place".
6. `_LEADING_COUNT_RE` — count+description.
7. Count+movement, spike (`_as_spike_callout`), ult (`_as_ult_callout`).
8. Damage callouts.
9. **Agent utility** (`_as_agent_utility` — relay_speech.py:4646).
10. Economy, economy request, `_MOVE` dict.
11. **Enemy-lead block** (relay_speech.py:4550): `_ENEMY_LEAD_RE.match(p)` → "they are X":
    - If rest is a place → `fe("They're {rest}.")`.
    - If rest is an action word → `fe("They're {rest}.")`.
    - Else: `_as_agent_position(p)`, `_as_ult_callout(p)`, `_as_agent_utility(p)`.
12. **`_as_enemy_action()`** (relay_speech.py:4584): agent/count + bare action → enemy callout.
    Called BEFORE `_as_agent_position` so an action word is never mistaken for a place.
13. **`_as_agent_position()`** (relay_speech.py:4589): named agent(s) + is/are + location.
14. **Team-directive handler** (relay_speech.py:4698): first word in `_TEAM_DIRECTIVE_VERBS`
    + 1-7 tokens and not a question → `fcmd(imperative.)`.
15. **M1 slot grammar** (relay_speech.py:4709): `_parse_callout_slots(p)` — LAST fallback.

**Flavor functions:**
- `fe(line)` = `_join_tail(line, enemy flavor tail)` — short Ultron enemy-contempt flavor.
- `fcmd(line)` = `_join_tail(line, command flavor tail)` — short tactical-command tail.
- `flav(line, flavor_key)` = `_join_tail(line, tail from flavor pool)`.
- All flavor functions are gated by `_flavor_tails_enabled()`. When flavor is OFF, tails are
  not appended and the bare snap is returned as-is.

**Thinking mode:**
- `rephrase = cfg.rephrase AND thinking_mode_enabled()`.
- Default `KENNING_THINKING_MODE=0` → `rephrase=False`.
- When rephrase=False, ALL `build_relay_line` paths that would call LLM instead compose from
  the deterministic pools. The LLM is never consulted for these three traces.

---

## Detailed per-input traces

### Trace 1: "tell my team rush B"

**normalize_command:**
- Step 2: `_strip_leading_junk` → "Ultron, " stripped if present. Assume input was already
  "tell my team rush B" (post wake-strip in the orch STT repair loop).
- Step 6: `_canonicalize_directive_lead` → `_ANY_TEAM_LEAD_OUTER_RE` matches "tell my team "
  (outer lead is a valid team verb, "tell"). Payload = "rush B". No stacked inner lead.
  Result: "tell my team rush B" (unchanged).
- Step 16: Zero-mistakes gate: no question/Spotify/identity match → continues.
- Step 17: `correct_callout_stt("tell my team rush B")` → "B" is canonical; "rush" unchanged.
- Step 19: `recover_relay_lead("tell my team rush B")`:
  - `_HAS_RELAY_LEAD.match("tell my team rush B")` → "tell" matches → return immediately.
- **Output of normalize_command: "tell my team rush B"** (effectively unchanged).

**match_relay_command("tell my team rush B"):**
- `_normalize_speech` → unchanged.
- `_BARE_CLUTCH_RE`, `_BARE_ENCOURAGE_RE` → no match.
- `_NARRATION_LEAD_RE` → no first-person modal → no match.
- Special-purpose matchers → no match.
- **GROUP CALLOUT PATTERNS**: `_RELAY_PATTERNS[0]` matches "tell my team rush B".
  - payload = "rush B".
  - `_payload_has_content("rush B")` → 2 words → True.
- **Returns: `RelayCommand(payload="rush B", addressee="team", verbatim=False)`**

**build_relay_line:**
- flavor-OFF override → None (flavor is ON; "rush B" is not a social snap).
- verbatim=False → skip verbatim path.
- `_as_snap_callout("rush B")`:
  - Named branch → skip (addressee="team").
  - `_as_question_relay("rush B")` → not a question → None.
  - careful, death, fp-lead, have, saw, count, spike, ult, damage, agent-utility → no.
  - Economy and economy-request → "rush" is not economy.
  - `_MOVE` dict: `bl="rush b"`, `_MOVE.get("rush b")` → no exact match (dict has "rush" bare
    only, which maps to "Rush." — but payload is "rush b" not bare "rush").
  - Enemy-lead block: `_ENEMY_LEAD_RE.match("rush B")` → "rush" not "they/enemy/..." → no.
  - `_as_enemy_action("rush B")` → `sub="rush"`, but `_roster_agents("rush")` = [] (not an
    agent) AND count match fails → returns None.
  - `_as_agent_position("rush B")` → "rush" not an agent → None.
  - **Team-directive handler** (relay_speech.py:4698):
    - `body = "rush B"` (re.sub `^to\s+` = no change).
    - `first = "rush"`.
    - `"rush" in _TEAM_DIRECTIVE_VERBS` = **True** (relay_speech.py:3564-3588: "rush" is in
      `_IMPERATIVE_VERBS` at line 3565 — "rotate push fall...rush...").
    - `_is_compound` = False.
    - `_is_question_payload("rush B")` = False.
    - `len("rush B".split())` = 2, in [1, 7] = True.
    - `out = "rush B"`.
    - → **`fcmd("Rush B.")` — "Rush B." + command-flavor tail.**
- **Spoken output: "Rush B." + short Ultron command-flavor tail.**
- **Channel: VoiceMeeter Input → game team voice chat.**

---

### Trace 2: "they are pushing A"

**normalize_command:**
- Step 2: `_strip_leading_junk` → no wake homophone → unchanged.
- Step 6: `_canonicalize_directive_lead` → "they" is not a mangled-tell word → no match.
- Step 16: Zero-mistakes gate → "they are pushing A" is not a question or Spotify command.
- Step 17: `correct_callout_stt("they are pushing A")` → site "A" canonical; "pushing" clean.
- Step 19: `recover_relay_lead("they are pushing A")`:
  - Guard 1: `_HAS_RELAY_LEAD.match("they ...")` → "they" is not a relay verb → **no**.
  - Guard 2: `_NOT_A_CALLOUT.match("they ...")` → "they" is not "what/who/how/is/play/..." → **no**.
  - Guard 3: `_REPORTED_RESPOND_RE.search(...)` → no directive verb → **no**.
  - Recovery 1-4: `_WANT_TEAM`, `_TRAILING_RELAY_TAIL`, `_TEAM_LEAD_NOVERB`, `_TEAM_LEAD` → no.
  - Recovery 5: `_STRONG_CALLOUT_RE.match("they are pushing A")`:
    - Enemy-state branch: `"they are pushing"` → "are" is NOT in the enemy-state verb list
      (which requires have/has/bought/saved/forced/...). **No match.**
    - Count branch: "they" is not a count word. **No match.**
    - Agent branch: "they" is not a roster agent name. **No match.**
    - **`_STRONG_CALLOUT_RE` does NOT match.**
  - Recovery 6: `_CALLOUT_SIGNAL.search("they are pushing A")`:
    - "pushing" is in `_CALLOUT_SIGNAL` (as `push|pushed|pushing`). **Matches.**
  - `_NARRATION_MUSING_RE.match("they are pushing A")` → "they" is not "I should/..." → **no**.
  - `relay_intent_ok("they are pushing A")`:
    - Embeds "they are pushing A" via EmbeddingGemma sidecar.
    - Compares against `RELAY_POSITIVE_EXEMPLARS` (includes: "they're hitting B hard",
      "enemy on A fast", "pushing mid", "their Cypher is in heaven").
    - Compares against `RELAY_NEGATIVE_EXEMPLARS` (includes narration/banter/questions).
    - "they are pushing A" is an unambiguous enemy-position callout → high positive cosine,
      low negative cosine → `pos - neg >= 0.06` → **returns True**.
    - (If sidecar down, returns None → falls through to prepend anyway — fail-open.)
  - → `return "tell my team " + "they are pushing A"`
- **Output of normalize_command: "tell my team they are pushing A"**

**match_relay_command("tell my team they are pushing A"):**
- `_normalize_speech` → unchanged.
- Narration gate → no first-person modal → pass.
- Special-purpose matchers → no match.
- **GROUP CALLOUT PATTERNS**: `_RELAY_PATTERNS[0]` matches "tell my team they are pushing A".
  - payload = "they are pushing A".
  - `_payload_has_content("they are pushing A")`:
    - 4 words → True.
    - Even without word-count, site-letter rescue: last word "A" (as "a"), second-to-last
      "pushing" IS in `_SITE_CALLOUT_CUES` → rescue fires → True.
- **Returns: `RelayCommand(payload="they are pushing A", addressee="team", verbatim=False)`**

**build_relay_line:**
- `_as_snap_callout("they are pushing A")`:
  - `_as_enemy_action("they are pushing A")` → sub="they", `_roster_agents("they")=[]`, count
    match: "they" is not "one/two/all five" → returns None.
  - **Enemy-lead block** (relay_speech.py:4550): `_ENEMY_LEAD_RE.match("they are pushing A")`:
    - Pattern: `^\s*(?:they(?:'re|\s+are)|the\s+enem...|enemies)\s+(?P<rest>.+)$`
    - "they are " matches. rest = "pushing A".
    - `_is_place("pushing A")` → "pushing" not in `_LOC_TOKENS` (which are location names,
      not verbs) → False.
    - `rl = "pushing a"`. `rl.split()[0] = "pushing"`. `"pushing" in _ACTION_WORDS` = **True**
      (relay_speech.py:3540: "_ACTION_WORDS = frozenset(('flanking flank pushing planting...')").
    - → **`fe("They're pushing A.")` — "They're pushing A." + enemy-flavor tail.**
- **Spoken output: "They're pushing A." + short Ultron enemy-flavor tail.**
- **Channel: VoiceMeeter Input → game team voice chat.**

---

### Trace 3: bare "cypher is flank"

Assume STT returns "cypher is flank" (common Valorant ASR output).

**normalize_command:**
- Step 2: `_strip_leading_junk` → "cypher" is not a wake homophone → unchanged.
- Step 6: `_canonicalize_directive_lead` → "cypher" is not a mangled-tell word → no match.
- Step 16: Zero-mistakes gate → "cypher is flank" is not a question or Spotify command.
- Step 17: `correct_callout_stt("cypher is flank")`:
  - `AGENT_MISHEARS` (routing_rules.py:92) maps "cypher" → "Cypher" (lowercase → capitalized
    canonical form). "is" and "flank" unchanged.
  - Result: "Cypher is flank".
- Step 19: `recover_relay_lead("Cypher is flank")`:
  - Guard 1: `_HAS_RELAY_LEAD.match("Cypher ...")` → "Cypher" is not a relay verb → **no**.
  - Guard 2: `_NOT_A_CALLOUT.match("Cypher ...")` → "Cypher" not "what/who/how/is/.." at pos 0
    (the `is` pattern requires "is" at START, not after an agent name) → **no**.
  - Guard 3-Recovery 4: none match.
  - Recovery 5: `_STRONG_CALLOUT_RE.match("Cypher is flank")`:
    - Agent+tactical-suffix branch: "Cypher" IS a roster agent. Suffix check: "flank" →
      the suffix list includes "flanking" but NOT "flank" (bare stem). **No match.**
    - (Note: if STT had produced "cypher is flanking", `_STRONG_CALLOUT_RE` would match and
      bypass the gate entirely.)
  - Recovery 6: `_CALLOUT_SIGNAL.search("Cypher is flank")`:
    - "flank" IS in `_CALLOUT_SIGNAL` (as `flank|flanking`). **Matches.**
    - Also `_AGENT_SIGNAL.search("Cypher is flank")`: "Cypher" IS in `_AGENT_SIGNAL`. **Matches.**
  - `_NARRATION_MUSING_RE.match("Cypher is flank")` → "Cypher" is not "I should/..." → **no**.
  - `relay_intent_ok("Cypher is flank")`:
    - Embeds "Cypher is flank" via EmbeddingGemma sidecar.
    - POSITIVE exemplars include: "their Cypher is in heaven", "Cypher trip on B",
      "enemy Raze rushing B", "Reyna pushing mid", "their Sova is holding short".
    - NEGATIVE exemplars include: banter/analysis about agents, questions about Cypher.
    - "Cypher is flank" (agent + tactical position) closely matches positive exemplars like
      "Cypher trip on B" and "their Sova is holding short" in semantic space.
    - Likely: `pos - neg >= 0.06` → **returns True**.
    - (If sidecar down, returns None → fail-open → prepend anyway.)
  - → `return "tell my team " + "Cypher is flank"`
- **Output of normalize_command: "tell my team Cypher is flank"**

**match_relay_command("tell my team Cypher is flank"):**
- `_normalize_speech` → unchanged.
- Narration gate → no first-person modal → pass.
- **GROUP CALLOUT PATTERNS**: `_RELAY_PATTERNS[0]` matches "tell my team Cypher is flank".
  - payload = "Cypher is flank".
  - `_payload_has_content("Cypher is flank")` → 3 words → True.
- **Returns: `RelayCommand(payload="Cypher is flank", addressee="team", verbatim=False)`**

**build_relay_line:**
- `_as_snap_callout("Cypher is flank")`:
  - Enemy-lead block: `_ENEMY_LEAD_RE.match("Cypher is flank")` → "Cypher" is not "they/the
    enemy/..." → **no match**.
  - **`_as_enemy_action("Cypher is flank")`** (relay_speech.py:4584, called BEFORE agent-position):
    - Regex match: `^(?P<sub>.+?)\s+(?:is\s+|are\s+)?(?P<act>[a-z][a-z\-]+)$` →
      sub="Cypher", act="flank".
    - `_norm_action("flank")` → `_BARE_TO_ING.get("flank")` = "flanking" (line 3550).
    - `"flanking" in _ACTION_WORDS` = **True** (line 3540).
    - sub is not "our/my" (it is "Cypher") → pass.
    - `sub = re.sub("^(?:their|the\s+enemy|enemy)\s+", "", "Cypher")` = "Cypher" (no prefix).
    - Count match: "Cypher" is not "one/two/all five" → no.
    - `_roster_agents("Cypher")` = ["Cypher"] (agent name recognized).
    - residual after stripping agent names and connectors = "" → empty, so pass.
    - `len(agents) == 1` → **returns `"Cypher is flanking."`**
  - `fe("Cypher is flanking.")` = `_join_tail("Cypher is flanking.", <enemy-flavor tail>)`
    → **"Cypher is flanking." + enemy-flavor tail**.
- **Spoken output: "Cypher is flanking." + short Ultron enemy-flavor tail.**
- **Channel: VoiceMeeter Input → game team voice chat.**

---

## Path comparison table

| Dimension | "tell my team rush B" | "they are pushing A" | "cypher is flank" |
|-----------|----------------------|-----------------------|-------------------|
| STT form | explicit relay lead | bare enemy callout | bare agent+action |
| recover_relay_lead | _HAS_RELAY_LEAD fires; returns immediately | _CALLOUT_SIGNAL("pushing"); relay_intent_ok → True | _CALLOUT_SIGNAL("flank") + _AGENT_SIGNAL("Cypher"); relay_intent_ok → True |
| Intent gate consulted? | NO | YES (sidecar embed) | YES (sidecar embed) |
| _STRONG_CALLOUT_RE fires? | N/A | NO ("are pushing" not in verb list) | NO ("flank" bare stem not in suffix list) |
| After normalize | "tell my team rush B" | "tell my team they are pushing A" | "tell my team Cypher is flank" |
| match_relay_command path | _RELAY_PATTERNS[0] | _RELAY_PATTERNS[0] | _RELAY_PATTERNS[0] |
| _payload_has_content | 2 words → True | 4 words → True; site-letter rescue (F2) also fires | 3 words → True |
| _as_snap_callout handler | team-directive (line 4698) "rush" in _TEAM_DIRECTIVE_VERBS | enemy-lead block (line 4550) "_ENEMY_LEAD_RE" → _ACTION_WORDS check | _as_enemy_action (line 4584) _BARE_TO_ING "flank"→"flanking" |
| Output form | "Rush B." | "They're pushing A." | "Cypher is flanking." |
| Flavor tail | command flavor (fcmd) | enemy flavor (fe) | enemy flavor (fe) |
| LLM consulted? | NO | NO | NO |

---

## Key findings

1. **recover_relay_lead is the only place where explicit-vs-bare diverges.** The `match_relay_command`
   → `_RELAY_PATTERNS` → `build_relay_line` pipeline is identical for all three inputs once
   normalize_command has prepended "tell my team ".

2. **`_STRONG_CALLOUT_RE` is narrower than expected.** It covers agent+specific-suffix and
   enemy+specific-verb, but does NOT cover "they are pushing X" (the "are" form is excluded) or
   bare "Cypher is flank" (the bare stem "flank" vs "flanking" matters). Both inputs therefore
   fall through to the relay-intent gate (Recovery 6), not the bypass (Recovery 5).

3. **`relay_intent_ok` is the semantic safety valve for ~97% of corpus relay decisions.**
   Without it, `_CALLOUT_SIGNAL` alone would fire on narration like "I should tell them to push"
   (also contains "push"). The gate has been calibrated to a low margin (0.06) with bias toward
   relaying (missed callout = re-say; false relay = broadcast noise to teammates).

4. **`_BARE_TO_ING` is the key for bare-stem action words.** "flank" → "flanking" via
   `_norm_action()` at line 3559, allowing `_as_enemy_action` to recognize the bare form.
   The dict covers: flank, push, rotate, rush, peek, hold, lurk, bait, trade, swing, plant,
   defuse, default, anchor, drone, smoke, execute, retake, defend, stick, save, force.

5. **`_as_enemy_action` (line 4102) runs BEFORE `_as_agent_position` (line 4589) in
   `_as_snap_callout`.** This is intentional (comment at line 4579): prevents an action word
   from being mistaken for a place. "Cypher is flank" → action handler wins → "Cypher is
   flanking." Never routes to "Cypher, flank." (the position form).

6. **`_payload_has_content` F2 site-letter rescue** (line 1389, 2026-06-18 audit) is what
   makes "they are A" / "pushing A" work. Without it, "A" as the sole content-bearing token
   would be rejected as junk. `_SITE_CALLOUT_CUES` includes "pushing" which unlocks "A".

7. **`_as_enemy_status` (called from the enemy-lead block at line 4551-4559) handles "they
   are X" where X is a place or action word.** It does NOT match "Cypher is flank" (wrong
   subject). It would match "they are pushing A" if `_is_place("pushing A")` returned True
   (it does not), then falls through to the action-word check which succeeds.

8. **`_MOVE` dict** (line 4677) handles bare single-word movement calls ("rush" → "Rush.").
   "rush B" (two words) does NOT hit the dict. It falls through to the team-directive handler
   which covers 1-7 tokens beginning with a `_TEAM_DIRECTIVE_VERBS` member.

9. **The relay-intent gate is fail-open.** When the EmbeddingGemma sidecar is down, `decide()`
   returns None and `recover_relay_lead` treats it as "relay approved" (keyword behavior falls
   through). This was intentional design: a missed callout is less harmful than a silent Ultron.

10. **Thinking mode and rephrase are irrelevant for these three inputs.** All three produce
    results from `_as_snap_callout()` long before the LLM path is reached. Even if
    `KENNING_THINKING_MODE=1` and `rephrase=True`, these would be served from deterministic
    pools because `_as_snap_callout` returns before `build_relay_line` reaches the LLM stage.

11. **Flavor tails are gated per output.** `fe()` calls `_join_tail(line, enemy_flavor_tail)`;
    `fcmd()` calls `_join_tail(line, command_flavor_tail)`. Both are no-ops when
    `_flavor_tails_enabled()` is False (`KENNING_FLAVOR_TAILS=0` or runtime toggle).

---

## Flags & config

| Flag / Config | Location | Default | Effect on relay |
|---------------|----------|---------|-----------------|
| `KENNING_FLAVOR_TAILS` | env | "1" (ON) | When OFF, `fe()` / `fcmd()` / `flav()` omit flavor tail; bare snap returned |
| `KENNING_THINKING_MODE` | env | "0" (OFF) | When OFF, `rephrase=False`; ALL outputs from deterministic pools, no 3B call |
| `KENNING_SNAP_REGISTRY` | env | "1" (ON) | Enables data-driven SNAP_REGISTRY pass in `build_relay_line` |
| `KENNING_SNAP_EARLY_ENDPOINT` | env | "0" (OFF) | When ON, `is_complete_tactical_callout()` closes VAD capture early |
| `KENNING_RELAY_TEAM_DSP` | env | "0" (OFF) | When ON, applies rumble-HP → RMS-norm → comfort-noise → tanh soft-clip |
| `KENNING_RELAY_VM_LEVEL_GUARD` | env | "0" (OFF) | When ON, boots VoiceMeeter level check (requires VoiceMeeter Remote API) |
| `KENNING_ADDRESSING_TAU` | env | "0.20" | Cost-asymmetric addressing threshold (not used when follow_up disabled) |
| `KENNING_WAKE_TRIM_TO_SPEECH` | env | "0" (OFF) | When ON, VAD segments audio to strip wake word from STT feed |
| `relay_speech.enabled` | config.yaml | true | Master relay on/off |
| `relay_speech.output_device` | config.yaml | "Voicemeeter Input" | PortAudio device name for relay TTS output |
| `relay_speech.rephrase` | config.yaml | true | Master rephrase config; must be true AND thinking_mode=ON for LLM |
| `relay_speech.max_line_chars` | config.yaml | 360 | Maximum characters in a relay line before truncation |
| `relay_speech.echo_to_user` | config.yaml | true | Also play relay audio on desktop speakers |
| `relay_speech.addressee_names` | config.yaml | [] | List of in-game teammate names for named-addressee routing |
| `relay_speech.follow_up_seconds` | config.yaml | 120.0 | Follow-up window (active only when addressing.follow_up_enabled=true) |
| `addressing.follow_up_enabled` | config.yaml | false | Must be false for wake-word-required mode |

---

## Extension points

1. **`RELAY_POSITIVE_EXEMPLARS` / `RELAY_NEGATIVE_EXEMPLARS`** (`_relay_intent.py:35/69`) —
   adding/removing exemplars shifts the semantic boundary. The gate uses max-over-cloud cosine,
   so adding a closely-matching positive exemplar lowers the effective threshold for that
   utterance class. The margin threshold (0.06) is the single tunable knob.

2. **`_STRONG_CALLOUT_RE`** (command_normalizer.py:818) — adding patterns here bypasses the
   sidecar entirely (always relay). Adding "they are pushing/rushing/rotating" to the enemy-verb
   list would bypass the gate for those common forms. Trade-off: faster but loses the semantic
   check on ambiguous narration.

3. **`_SITE_CALLOUT_CUES`** (relay_speech.py:1360) — adding new "context words" that precede a
   site letter makes more payload shapes pass `_payload_has_content`.

4. **`_BARE_TO_ING`** (relay_speech.py:3549) — adding new bare-stem action verbs here makes
   them recognizable by `_as_enemy_action`. Any new "X is <verb>" bare callout form needs an
   entry here plus the -ing form in `_ACTION_WORDS`.

5. **`_MOVE` dict** (relay_speech.py:4677) — adding new single-word movement shortcuts here
   routes them to `fcmd(...)` ahead of the team-directive handler and M1 grammar.

6. **`SNAP_REGISTRY` / `SnapRule`** (voice_lines.py) — data-driven: adding one SnapRule adds
   a new snap with no code change (when `KENNING_SNAP_REGISTRY=1`).

7. **`_RELAY_PATTERNS`** (relay_speech.py:119) — adding new explicit-lead patterns (e.g. new
   relay-verb synonyms or sentence shapes) allows more surface forms to hit the strict matcher
   without needing relay-lead recovery.

8. **`is_complete_tactical_callout()`** (relay_speech.py:5977) — the slot-grammar early-endpoint
   gate. When `KENNING_SNAP_EARLY_ENDPOINT=1`, this is called speculatively on partial STT
   transcripts to close the capture window early for confirmed tactical callouts. Extending the
   M1 slot grammar also improves this gate's coverage.

---

## Retire-not-remove candidates (Ultron 1.0 pivot)

The Ultron 1.0 pivot targets an LLM-centric architecture where an 8B model handles all relay
outputs. The following components become candidates for reclassification as routing-only
infrastructure (kept to classify intent + pick prompt templates, not to produce final output):

1. **`_as_snap_callout()` and all 15+ sub-handlers** — currently produce final TTS output.
   In U1.0 these become: (a) intent detectors that select a curated prompt template, or
   (b) in-context exemplars injected into the 8B prompt. The snap output itself becomes the
   few-shot exemplar for that slot type, not the broadcast line.

2. **`_REPHRASE_PROMPT` / `_RELAY_REPHRASE_SYSTEM`** (relay_speech.py:2081) — the current
   3B rephrase prompt. Would be replaced by an 8B-specific system prompt that is always active
   (not gated by `thinking_mode`). The current prompt's tactical rules (preserve positions,
   ownership, brevity, no moralizing) remain relevant as 8B system prompt content.

3. **`_as_enemy_action` and `_as_agent_position`** — useful as routing signals: "does the
   payload describe an enemy agent doing something?" can select a "enemy-spotted" prompt
   template for the 8B with appropriate exemplars.

4. **`_as_economy_callout` and `_MOVE` dict** — economy/movement calls are SHORT and
   deterministic by design. Retaining them as snap-pass-through (skip the 8B for these)
   reduces LLM latency for the simplest callout types.

5. **`relay_intent_ok()` / `RelayIntentGate`** — the semantic gate is architecture-agnostic.
   In U1.0 it would remain as the relay-vs-conversational router gate (unchanged role). It
   could potentially be replaced by the 8B's own intent classification, but the sidecar
   provides a cheaper, faster, always-available intent signal.

6. **`_payload_has_content()` + `_SITE_CALLOUT_CUES`** — content gating logic that validates
   `match_relay_command` outputs before they reach the 8B. Should be retained: the 8B should
   not receive empty or junk payloads.

7. **`_RELAY_PATTERNS` (13 explicit-lead regexes)** — remain as the primary explicit-lead
   classifiers. They are cheap, deterministic, and always faster than an 8B forward pass.

8. **`recover_relay_lead()`** — remains as the bare-callout recovery step. The
   "was this a relay intent?" gate question is the same regardless of downstream 8B vs snap.

---

## Gotchas

1. **"they are pushing" misses `_STRONG_CALLOUT_RE`.** Only "they have/bought/saved/..." forms
   bypass the gate. "they are" + any verb hits Recovery 6 and pays the sidecar cost. If the
   sidecar is slow or down, this form is delayed (with sidecar down) or fail-open (returns True
   by None fallback).

2. **Bare "flank" vs "flanking" matters for `_STRONG_CALLOUT_RE`.** If STT says "Cypher is
   flanking" (with -ing), the agent+tactical suffix list includes "flanking" and the gate is
   bypassed. If STT says "flank" (bare stem), it falls through to the gate. The `_BARE_TO_ING`
   table in `_as_enemy_action` normalizes this AFTER the gate decision, not before it.

3. **`_SITE_CALLOUT_CUES` is checked in `_payload_has_content`, not in `recover_relay_lead`.**
   The bare utterance "pushing A" (without a relay lead) will reach `recover_relay_lead`, where
   `_CALLOUT_SIGNAL` fires on "pushing" and the gate is consulted. `_SITE_CALLOUT_CUES` only
   matters later, in `_payload_has_content`, to keep the resulting payload alive after the strict
   matcher extracts it.

4. **Relay-intent gate decision is per-utterance, not cached.** Each bare callout in a turn
   pays the embedding cost (one sidecar request per `relay_intent_ok` call). Back-to-back bare
   callouts in the same utterance (e.g., "two on A, Cypher is flank") become a compound and are
   handled by `_as_compound_callout`, which re-runs `_as_snap_callout` on each sub-fact.

5. **The `_ENEMY_LEAD_RE` handler inside `_as_snap_callout` (line 4550) operates on the
   PAYLOAD, not the full normalized text.** By the time `_as_snap_callout` is called, the
   "tell my team " prefix has been stripped off by `match_relay_command`. So `_ENEMY_LEAD_RE`
   matches "they are pushing A" (the payload), not "tell my team they are pushing A".

6. **`correct_callout_stt` runs BEFORE `recover_relay_lead`.** The STT correction at step 17
   produces "Cypher" (capital C) before the relay-lead recovery at step 19. `_AGENT_SIGNAL`
   looks for capitalized agent names. If correct_callout_stt failed to capitalize, `_AGENT_SIGNAL`
   might miss the agent and only `_CALLOUT_SIGNAL` ("flank") would trigger the gate.

7. **The narration gate (`_NARRATION_LEAD_RE`) is checked TWICE**: once in `recover_relay_lead`
   (as `_NARRATION_MUSING_RE`, start-anchored, in the normalizer) and once in
   `match_relay_command` (as `_NARRATION_LEAD_RE`, search-anywhere, in the relay matcher).
   They are slightly different regexes covering different narration forms. A narration that
   slips past the first check can still be caught by the second.

8. **`rephrase=False` when thinking mode is OFF.** All three traces end at deterministic snap
   handlers and never reach the LLM path, so thinking mode is currently irrelevant for them.
   This changes if any handler returns None (e.g. a payload that is not a recognized tactical
   form and is not a compound) — then the LLM fallback at `build_relay_line:6324` is the next
   stage, gated by `rephrase`.

9. **Flavor is always appended on the snap output, not on the broadcast line.** The VoiceMeeter
   device receives the FULL flavor-tailed line ("Rush B. Hesitate and we lose it."). If flavor
   is too long, it extends the TTS duration. `max_line_chars` (default 360) is a post-processing
   cap on the TOTAL output (snap + tail), not just the tactical content.

---

## Open questions

1. **Does `_CALLOUT_SIGNAL` include "are" or "is" as keyword triggers?** If not, a one-word
   utterance like just "Cypher" (agent name only, no action word) would only trigger via
   `_AGENT_SIGNAL`. What is the relay-intent gate decision for a bare agent name? The positive
   exemplars do not include bare agent names.

2. **What is the exact relay-intent gate score distribution for borderline cases** like "their
   Sage is alive" (is this a relay or an analysis)? The 0.06 margin was calibrated on a corpus
   from 2026-06-16 — has the exemplar cloud been updated since then?

3. **`_as_enemy_action` checks `_roster_agents(sub)` but what if STT introduces a spurious
   word?** "like Cypher is flank" → sub="like Cypher", `_roster_agents("like Cypher")` —
   does the roster matcher handle leading connective words?

4. **What happens to "they are pushing A" if the sidecar takes > utterance TTL?** The gate
   blocks recover_relay_lead until `score()` returns. Is there a timeout on the sidecar request?
   If the sidecar is slow (not down), the gate call blocks normalize_command, which blocks the
   full turn latency.

5. **The `_REPHRASE_PROMPT` is a 3B-specific prompt.** If thinking mode is turned on for the
   first time in a live session, are "they are pushing A" / "Cypher is flanking" still served
   from snap handlers, or could a payload escape to the LLM? Mapping which payloads currently
   escape `_as_snap_callout` → None is important for U1.0 routing.

6. **Named addressee routing: if `relay_speech.addressee_names` is populated** (e.g. "jett,sova"),
   does "tell Jett rush B" get routed to the named-addressee branch in `match_relay_command`
   instead of the group branch? How does `_named_patterns()` interact with `_RELAY_PATTERNS`?

7. **`_as_compound_callout` splits "A and B" payloads.** What is the split criterion for
   "they are pushing A and Cypher is flank"? Is this treated as one compound or two separate
   relay turns?

---

## References

- `src/kenning/audio/command_normalizer.py` — full normalize_command pipeline
- `src/kenning/audio/_relay_intent.py` — RelayIntentGate (fully read)
- `src/kenning/audio/relay_speech.py` — match_relay_command, build_relay_line,
  _as_snap_callout, _as_enemy_action, _as_agent_position, _BARE_TO_ING, _ACTION_WORDS,
  _MOVE, _TEAM_DIRECTIVE_VERBS (lines 72-302, 1060-1704, 2081-2400, 3234-3620, 4068-4720, 6012-6446)
- `src/kenning/audio/routing_rules.py` — AGENTS, AGENT_MISHEARS, LOCATIONS, TERMS (lines 47-194)
- `src/kenning/pipeline/orchestrator.py` — _maybe_handle_relay_speech, run() dispatch
  (lines 3388-3560, 6100-6520)
- `config.yaml:1827` — relay_speech config block
