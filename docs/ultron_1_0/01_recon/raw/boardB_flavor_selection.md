# B4: MAP the flavor-tail selection pipeline end-to-end

Recon date: 2026-06-20. Agent: claude-sonnet-4-6 (infallible-kepler-0a865d worktree).
All line citations are repo-root-relative. Branch: `claude/infallible-kepler-0a865d`.

---

## Overview

The flavor-tail pipeline appends short (≤6-word) in-character Ultron remarks to tactical
callouts. It is **strictly additive and fail-open**: a tail never changes the tactical
content; every failure silently falls back one tier. The full pipeline runs as:

```
callout facts (agent, location, damage, ability, count)
    → coarse register assignment (enemy / ult / damage / utility / command / self / careful)
    → situation refinement (spotted → moving / planting / ... via action keywords + ult-keyword lift)
    → agent fork (1 agent → AGENT_FLAVOR cell; 2+ → MULTI_FLAVOR cell; 0 → contextual templates + generic pool)
    → tag assembly (active_tags: loc:X + dmg:Y + ability:Z from callout facts)
    → 4-tier progressive tag filter (_tier_filter)
    → small-pool fast path (< 5 candidates → LRU, skip sidecar)
    → semantic re-ranker (≥ 5 candidates, sidecar enabled → cosine + MMR)
    → LRU fallback (_pick_lru, global anti-repeat)
    → _join_tail (single output chokepoint, flavor-ON/OFF gate)
```

The pipeline is **enemy-contempt aware**: registers `enemy`, `ult`, `damage`, `utility`
carry cold machine-contempt at enemies; registers `command`, `self`, `careful` carry
serene machine-certainty for ally/user speech — never contempt aimed at teammates.

---

## Files & key symbols

### `src/kenning/audio/relay_speech.py` — DISPATCHER & PIPELINE (6,751 lines)

All flavor-critical symbols live in this file unless noted.

| Symbol | Line(s) | Kind | Description |
|--------|---------|------|-------------|
| `_flavor_tails_enabled` | 1136 | `bool` (module-global) | Runtime toggle; init from `KENNING_FLAVOR_TAILS` env var. |
| `set_flavor_tails_enabled(bool)` | 1141 | function | Voice-command handler sets this at runtime. |
| `flavor_tails_enabled()` | 1147 | function | Query accessor used by `_join_tail`. |
| `match_flavor_toggle(text)` | 1167 | function | Matches "flavor off/on" + Whisper mishear fallbacks; returns True/False/None. |
| `_REGISTER_SITUATION` | 3775 | `dict` | Maps register → base enemy situation: `enemy→spotted, ult→ult, damage→damaged, utility→utility`. |
| `_REGISTER_POOL` | 3780 | `dict` | Maps register → generic fallback pool (7 registers). |
| `_ULT_KW_RE` | 3873 | `re.Pattern` | `\b(?:ult|ulted|ulting|ultimate|ultis?)\b` — ult-keyword LIFT detector. |
| `_situation_for(register, payload)` | 3876 | function | Derives fine situation. ULT keyword overrides all; enemy register refines via `_situation_for_payload`. |
| `_tier_filter(ents, active)` | 3892 | function | 4-tier tag progressive filter within a cell. Returns candidate text list. |
| `_flavor_ctx(callout, register, recent_lines, *, agents, ability, loc, count, payload)` | 3931 | function | **The main flavor selection entry point.** Calls `_situation_for`, `_build_active_tags`, picks pool, calls `_tier_filter`, `_select_tail`/`_pick_flavor`, then `_join_tail`. |
| `_payload_flavor_facts(p)` | 3989 | function | Extracts `{agents, loc, ability, count, payload}` from raw payload string. Called once per `build_relay_line` call; result passed as `**_ff` to all `_flavor_ctx` calls. |
| `_ctx_candidates(register, *, ability, loc, count)` | 3830 | function | Generates contextual template tails (location/ability/count) for calls with NO named agent. |
| `_standalone_loc(loc, *, for_command)` | 3811 | function | Validates that a location string is a genuine standalone map location (not a bare modifier). Gates the "cannot hold X" / "Own X" templates. |
| `_pick_flavor(pool, recent_lines)` | 3679 | function | Thin wrapper over `_pick_lru`. Anti-repeat via global LRU. |
| `_join_tail(head, tail)` | 3686 | function | **Single output chokepoint.** Drops tail when `_flavor_tails_enabled==False`. Ensures head ends with `.`/`!`/`?`. Returns `"head. tail"`. |
| `_flavored(callout, pool, recent_lines)` | 3712 | function | `_join_tail(callout, _pick_flavor(pool, recent_lines))`. Convenience; used by a few legacy call sites. |
| `_pick_lru(candidates, rng)` | 2715 | function | Global LRU anti-repeat picker. Never-used-first; ties broken randomly. Module-global `_LRU_SEEN: dict[str, int]` + `_LRU_COUNT: list[int]`. |
| `_LRU_SEEN` / `_LRU_COUNT` | 2711–2712 | module globals | Shared across ALL pools — each candidate's recency stored by its `.lower()` text. Cross-pool contamination is intentionally prevented by never comparing across pools (only within the candidate set). |
| `_AGENT_FLAVOR` | 3740 | `dict` | Imported from `_agent_flavor.py` (try/except; fallback `{}`). |
| `_MULTI_FLAVOR` | 3745 | `dict` | Imported from `_multi_flavor.py` (try/except; fallback `{}`). |
| `_select_tail` | 3769 | function | Imported from `_tail_selector.select_tail` (try/except; stub returns None if unavailable). |
| `_tail_entries` | 3751 | function | Imported from `_tail_schema.entries` — coerces str→TailEntry in legacy pools. |
| `_situation_for_payload` | 3752 | function | Imported from `_tail_schema.situation_for_payload`. |
| `_build_active_tags` | 3753 | function | Imported from `_tail_schema.build_active_tags`. |
| `_roster_agents(text)` | 3465 | function | Extracts ordered list of canonical agent names from text using `_ROSTER_RE`/`_ROSTER_CANON`. Used by `_payload_flavor_facts`. |
| `_fact_tokens(text)` | 4974 | function | Returns `(nums, agents, locs, abils)` sets — the raw fact extraction layer below `_payload_flavor_facts`. |
| `_OUR_ACTION_RE` | 5014 | `re.Pattern` | Detects our-team action verbs (plant/defuse/hold/rotate/...) to route to COMMAND register. |
| `fe(callout)` / `fcmd(callout)` / `fself(callout)` / `flav(callout, pool)` | 4359–4374 | local lambdas | Per-`build_relay_line` call closures that gate flavor on the `flavor` flag and dispatch to `_flavor_ctx`. |

### `src/kenning/audio/_agent_flavor.py` — PER-AGENT CONTEMPT LIBRARY (2,612 lines)

```python
AGENT_FLAVOR: dict[str, dict[str, list[TailEntry]]] = { ... }
```

**29 agents × up to 16 situation keys** = 1,628 curated `TailEntry` objects.

| Agent group | Agents |
|-------------|--------|
| she | Astra, Deadlock, Fade, Jett, Killjoy, Neon, Raze, Reyna, Sage, Skye, Viper, Vyse, Waylay |
| he | Breach, Brimstone, Chamber, Cypher, Gekko, Harbor, Iso, Miks, Omen, Phoenix, Sova, Tejo, Veto, Yoru |
| they | Clove |
| it | KAY/O |

Standard situation cells per agent (16):
`spotted, ult, damaged, utility, moving, planting, defusing, rotating, saving, falling_back, peeking, holding, lurking, trading, last_alive, near_death`

**Iso extended cells** (6 bonus at lines 937–982 with parenthetical sub-notes):
`falling_back (retreating)`, `holding (anchoring)`, `last_alive (clutch contempt)`, `lurking (flanking)`, `moving (pushing/rushing)`, `saving (eco/not buying)`. These are currently unreachable from the standard `situation_for_payload()` dispatch (which only returns plain keys).

Each `TailEntry`:
- `text: str` — spoken line (target ≤6 words; lint cap 14 words)
- `tags: frozenset[str]` — zero or more fine-grained context tags

Tag namespaces and values:
- `loc:high_ground | long_range | site_area | flank_route | mid | choke` (6 location classes)
- `dmg:minor | low | one_shot` (3 damage levels)
- `ability:<name>` (open set; e.g. smoke, flash, dart, molly, wall, trap, cage, cam, sensor, teleport, turret, heal, dash, updraft, suppress, gravnet, ...)

### `src/kenning/audio/_multi_flavor.py` — MULTI-AGENT GROUP TAILS (246 lines)

```python
MULTI_FLAVOR: dict[str, tuple[str, ...]] = { ... }
```

15 situation keys (no `near_death` — falls to `damaged` at relay_speech.py:3962). Pool
sizes: 8 entries (smaller situations) to 37 entries (`spotted`). Theme: contempt at the
GROUP — numbers of mortals do not beat a machine. Plain `str` entries (no tags);
`_tail_entries()` coerces them to tagless `TailEntry` objects.

### `src/kenning/audio/_tail_schema.py` — SCHEMA & TAGGING PRIMITIVES (400 lines)

| Symbol | Line | Kind | Description |
|--------|------|------|-------------|
| `TailEntry` | 33 | `@dataclass(frozen=True)` | `text: str`, `tags: FrozenSet[str]`. |
| `as_entry(x)` | 39 | function | Coerces `str→TailEntry` (idempotent). |
| `entries(pool)` | 46 | function | Bulk coerce list; used by `_tail_entries` alias in relay_speech. |
| `Sit` | 55 | class | 16 situation constants: SPOTTED, ULT, DAMAGED, UTILITY, MOVING, PLANTING, DEFUSING, ROTATING, SAVING, FALLING_BACK, PEEKING, HOLDING, LURKING, TRADING, LAST_ALIVE, NEAR_DEATH. |
| `ENEMY_SITUATIONS` | 74 | `tuple[str, ...]` | 16 canonical situation keys in order. |
| `AGENT_GENDER` | 85 | `dict[str, str]` | 29 agents → canonical pronoun (`she/he/they/it`). Hard gate: wrong-gender tail impossible to ship. |
| `GENDER_PRONOUNS` | 96 | `dict[str, frozenset[str]]` | Pronoun set per gender for lint clash detection. |
| `agent_gender(agent)` | 104 | function | AGENT_GENDER lookup; returns None if unknown. |
| `_LOC_CLASS_TOKENS` | 113 | `dict[str, frozenset[str]]` | ~130 location tokens → 6 coarse classes. Used to build `_TOKEN_TO_LOCCLASS`. |
| `_TOKEN_TO_LOCCLASS` | 144 | `dict[str, str]` | Reverse index: token → class name. |
| `loc_class(loc)` | 150 | function | Noisy location token/phrase → `"loc:<class>"` tag. Multi-token: tries last word then first word as fallback. Returns None if unknown. |
| `_VERB_TO_ABILITY` | 203 | `dict[str, str]` | ~50 verbs/tokens → canonical ability category name. Used by `ability_tag()`. |
| `ability_tag(ability)` | 223 | function | Ability verb/token → `"ability:<name>"` tag or None. |
| `dmg_level_tag(count, payload)` | 172 | function | HP number / keyword → `"dmg:minor|low|one_shot"` or None. |
| `_SITUATION_KEYWORDS` | 234 | `tuple[tuple[str, tuple[str,...]], ...]` | 11 (situation, keywords) pairs ordered most-specific-first (defusing > planting > ... > moving). |
| `situation_for_payload(payload)` | 260 | function | Scans payload for situation keywords; returns first match or None (→ caller keeps "spotted"). |
| `build_active_tags(*, loc, count, payload, ability)` | 273 | function | Assembles `frozenset[str]` of active tags from callout facts. Calls `loc_class`, `dmg_level_tag`, `ability_tag`. |
| `lint_agent_flavor(flavor)` | 308 | function | Full structural + character integrity audit of AGENT_FLAVOR dict. Returns list of human-readable findings; empty = clean. |
| `MAX_TAIL_WORDS` | 297 | `int = 14` | Lint word-count cap (library tops at 10 words; 14 catches paragraphs). |
| `VALID_DMG_LEVELS` | 300 | `frozenset` | `{minor, low, one_shot}`. |
| `VALID_TAG_NAMESPACES` | 305 | `frozenset` | `{loc, dmg, ability}`. |

**Damage level mapping details** (`dmg_level_tag`, line 172):
- Keywords "one shot", "lit", "cracked", "almost dead", "critical", "no armor" → `dmg:one_shot`
- HP ≥75 → `dmg:one_shot`; 40–74 → `dmg:low`; <40 → `dmg:minor`
- Keywords "low", "hurt", "wounded", "tagged", "chunked", "weak" → `dmg:low`
- If no keywords and no numeric HP: returns None

**Location coarse classes** (`loc_class`, 6 classes, ~130 tokens):
- `high_ground`: heaven, rafters, tower, attic, perch, nest, balcony, upper, top, ropes, catwalk, boathouse, tree, crane, ...
- `long_range`: long, a/b/c long, window, snipers, bridge, fountain, yard, alley, garden, boba, lane, ...
- `site_area`: site, a/b/c site, a/b/c main, back site, default, plant, spike, bombsite, diamond, hell, ...
- `flank_route`: flank, ct, spawn, behind, rotation, link, a/b link, garage, tunnel, vents, vent, sewer, stairs, back, ...
- `mid`: mid, middle, connector, market, hookah, courtyard, pizza, top mid, mid courtyard, b/a mid, ...
- `choke`: elbow, corner, choke, doors, gap, cubby, nook, dish, pit, showers, kitchen, generator, ramp, ...

**`_VERB_TO_ABILITY` entries** (partial — ~50 verbs):
mollied/molly/naded → `molly`; walled/wall → `wall`; smoked/smoke → `smoke`;
darted/dart/shocked → `dart`; flashed/flash/blinded → `flash`; caged/cage → `cage`;
stunned/stun/concussed → `stun`; droned/drone → `drone`; recon/reconned → `recon`;
healed/heal/rez → `heal`; slowed/slow → `slow`; dashed/dash → `dash`;
teleported/tp/tped → `teleport`; turret → `turret`; trip/tripwire/trap → `trap`;
suppressed/suppress → `suppress`.

### `src/kenning/audio/_tail_selector.py` — SEMANTIC RE-RANKER (118 lines)

```python
def select_tail(cands, recent_lines, *, agent, situation, active_tags, pool_kind) -> Optional[str]
```

Opt-in semantic re-ranker (cosine + MMR) via the embeddinggemma sidecar.

**Module-level state:**
- `_DOC_CACHE: dict` — doc-matrix cache keyed by `tuple(cands)`. Valid whole session (tails are deterministic per model); survives sidecar restarts.
- `_RECENT: deque(maxlen=16)` — rolling window of recently-chosen tail vectors for MMR soft diversity.
- `_THRESHOLD: dict` — abstain floors: `{"agent": 0.30, "multi": 0.26, "generic": 0.20}`. Below top cosine → abstain → LRU fallback.

**Query construction** (`_query_for`, line 43):
```
"<agent> <situation> <tag1_value> <tag2_value> ..."
```
E.g.: "Jett spotted high_ground" — a structured context sentence up to 120 chars.
Used as the query embedding; doc embeddings are the candidate tail texts.

**Selection algorithm:**
1. Abort if numpy unavailable, `< 2` candidates, or `KENNING_ENABLE_TAIL_SELECTOR` unset (line 78).
2. Get backend: `command_router.get_embedding_backend()`. Abort if sidecar unavailable.
3. Fetch/cache doc matrix (shape `[len(cands), embed_dim]`) via `be.prepare(cands)`.
4. Embed the structured query via `be._embed([query], kind="query")`.
5. Compute cosine sims: `sims = mat @ q[0]`.
6. If `max(sims) < _THRESHOLD[pool_kind]` → abstain (low confidence → LRU fallback).
7. MMR diversity penalty from `_RECENT` vectors: `score = 0.85*sims - 0.15*max_prev_sim` (λ=0.85 for ≥10 candidates, 0.65 otherwise).
8. HARD mask tails already spoken this round: `score[already_spoken] = -1e9`.
9. Pick `argmax(score)`, append to `_RECENT`, return `cands[idx]`.

**Fail-open guarantees:** any exception (network error, shape mismatch, numpy error) returns `None`, causing the caller to use `_pick_lru` instead.

### `src/kenning/audio/_ultron_pools.py` — GENERIC REGISTER POOLS (472 lines)

7 pools, imported at relay_speech.py:3673–3676:

| Symbol | Approx size | Register | Tone |
|--------|------------|---------|------|
| `_FLAVOR_ENEMY` | ~90 lines | enemy (no named agent, no specific register) | Cold contempt: "flesh against a machine", "predictable like all flesh" |
| `_FLAVOR_ULT` | ~50 lines | ult (unnamed ult callout) | Contempt at their ability spend: "a delay, nothing more" |
| `_FLAVOR_DAMAGE` | ~50 lines | damage (unnamed low-HP callout) | Contempt at wounded flesh |
| `_FLAVOR_UTILITY` | ~57 lines | utility (unnamed utility callout) | Contempt at their tool spend |
| `_FLAVOR_CAREFUL` | ~56 lines | careful (caution callout to OUR team) | Machine-certainty for allies: serene, never contempt |
| `_FLAVOR_COMMAND` | ~58 lines | command (order to OUR team) | Cold commanding certainty; never mocks teammates |
| `_FLAVOR_SELF` | ~55 lines | self (user's own status) | Stoic self-assessment; NEVER mocks the user |

**Owner-awareness hard rule:** ENEMY/ULT/DAMAGE/UTILITY are enemy-facing (contempt);
CAREFUL/COMMAND/SELF are ally/user-facing (machine-certainty). This is enforced by pool
structure and the register routing logic, not by runtime code.

---

## Control/data flow

### Step 1 — Register assignment (in `build_relay_line` / `_as_snap_callout` / LLM fallback path)

The caller (a local lambda `fe`, `fcmd`, `fself`, or `flav`) chooses the register based
on the callout's semantic content at relay_speech.py:4359–4374:

```
addressee == named teammate:
    first_person → _flavor_ctx(..., "self", ...)
    else         → _flavor_ctx(..., "command", ...)

"they / their / enemy" in text:
    → _flavor_ctx(..., "enemy", ...)

first_person ("I", "I'm", "my"):
    → _flavor_ctx(..., "self", ...)

"we / our" OR first in _TEAM_DIRECTIVE_VERBS / _IMPERATIVE_VERBS OR _OUR_ACTION_RE.search:
    → _flavor_ctx(..., "command", ...)

ff.get("agents") (bare named-agent callout like "cypher main"):
    → _flavor_ctx(..., "enemy", ...)

ff.get("loc") AND len(p.split()) <= 7 (short bare position callout):
    → _flavor_ctx(..., "enemy", ...)

ff.get("count") AND len(p.split()) <= 4 (short bare count):
    → _flavor_ctx(..., "enemy", ...)
```

Additionally: the explicit register-typed snap functions use typed lambdas:
- `fe(callout)` → `_flavor_ctx(callout, "enemy", ...)`
- `fcmd(callout)` → `_flavor_ctx(callout, "command", ...)`
- `fself(callout)` → `_flavor_ctx(callout, "self", ...)`
- `flav(callout, pool)` → `_flavor_ctx(callout, _POOL_REG[id(pool)], ...)`

### Step 2 — Fact extraction (`_payload_flavor_facts`, line 3989)

Called ONCE per `build_relay_line` invocation (relay_speech.py:4353); result stored as `_ff`:

```python
_ff = {
    "agents": _roster_agents(p),   # ordered list of canonical agent names (may be 0, 1, or 2+)
    "loc":    first_valid_loc,      # first non-article location token; None if none
    "ability": first_ability,       # first ability token from _ABILITY_LEAD; None if none
    "count":  first_count,          # first numeric token; None if none
    "payload": p,                   # raw payload string
}
```

`_roster_agents` uses `_ROSTER_RE` (all 29 agent names + STT homophones) + `_ROSTER_CANON`
(lowercase alias → canonical name). Articles `a/an/the` are excluded from `loc` even if
they appear in `_LOC_TOKENS`.

### Step 3 — `_flavor_ctx` main logic (relay_speech.py:3931–3986)

```
1. sit = _situation_for(register, payload)
   → ULT keyword in payload? → sit = "ult" (OVERRIDES register classification)
   → register in _REGISTER_SITUATION? → base = spotted/ult/damaged/utility
   → base == "spotted"? → refine via _situation_for_payload(payload) or keep "spotted"
   → register not in _REGISTER_SITUATION (command/self/careful)? → sit = None

2. active = _build_active_tags(loc=, count=, payload=, ability=)
   → calls loc_class(loc), dmg_level_tag(count, payload), ability_tag(ability)
   → returns frozenset of up to 3 tags

3. if sit and agents:
   if len(agents) == 1:
       cell = _AGENT_FLAVOR.get(agents[0], {})
       pool = cell.get(sit)
               or (cell.get("damaged") if sit == "near_death" else None)   # M5 fallback
               or cell.get("spotted")                                        # last resort
               or ()
       pk = "agent"
   else (2+ agents):
       pool = _MULTI_FLAVOR.get(sit)
               or (_MULTI_FLAVOR.get("damaged") if sit == "near_death" else None)
               or _MULTI_FLAVOR.get("spotted")
               or ()
       pk = "multi"

   if pool:
       cands = _tier_filter(_tail_entries(pool), active)
       if cands:
           if len(cands) < 5:                      # SMALL-POOL FAST PATH
               return _join_tail(callout, _pick_flavor(cands, recent_lines))
           # SEMANTIC RE-RANK path
           chosen = _select_tail(cands, recent_lines,
                                 agent=(agents[0] if single else None),
                                 situation=sit, active_tags=active, pool_kind=pk)
           return _join_tail(callout, chosen or _pick_flavor(cands, recent_lines))

4. (no agents, or empty pool)
   ctx = _ctx_candidates(register, ability=, loc=, count=)
   pool = list(_REGISTER_POOL.get(register, _FLAVOR_ENEMY))
   cands = ctx * 4 + pool if ctx else pool    # fact-templates dominate 4:1 when present
   chosen = _select_tail(cands, recent_lines, situation=register,
                         active_tags=active, pool_kind="generic")
   return _join_tail(callout, chosen or _pick_flavor(cands, recent_lines))
```

### Step 4 — `_tier_filter` algorithm (relay_speech.py:3892–3928)

Input: `list[TailEntry]` (the cell), `frozenset[str]` (active tags from callout).

```
if active == frozenset():
    → return [e.text for e in ents]   # no tags → all entries pass

T1: t1 = [e for e in ents if e.tags <= active]   # tags are SUBSET of active (exact fit)
    if len(t1) >= 3:
        SPECIFICITY LADDER: bucket by tag-count descending;
        take the most-specific band with ≥2 entries (union downward);
        → return [e.text for e in (picked if ≥2 else t1)]

T2: for pref in ("ability:", "dmg:", "loc:"):    # priority: ability > dmg > loc
        tag = next(t for t in active if t.startswith(pref))
        t2 = [e for e in ents if tag in e.tags or not e.tags]
        if len(t2) >= 3: return [e.text for e in t2]

T3: t3 = [e for e in ents if not e.tags]        # tagless base tails
    if len(t3) >= 3: return [e.text for e in t3]

T4: return [e.text for e in ents]               # whole cell (final resort)
```

**Threshold throughout**: ≥3 survivors needed to use a tier (relaxes on failure).
**Specificity ladder** at T1: among exact-fit entries, prefer the most-specific band
(most tags) that has ≥2 entries. This ensures a `loc:high_ground` callout gets the
high-ground-tagged tails and NOT the generic base tails (which would dilute variety).

### Step 5 — Situation refinement detail (`_situation_for`, line 3876)

```
if payload and _ULT_KW_RE.search(payload):         # "ult/ulted/ulting/ultimate/ultis"
    → return "ult"   (HARD LIFT regardless of register)

base = _REGISTER_SITUATION.get(register)
if base == "spotted":
    return _situation_for_payload(payload) or "spotted"
return base  # "ult", "damaged", "utility", or None for command/self/careful
```

`_situation_for_payload` (`_tail_schema.py:260`) scans for the first matching keyword
pair (ordered most-specific-first):

| Priority | Situation | Sample keywords |
|----------|-----------|----------------|
| 1 (highest) | `defusing` | defusing, defuse, on the defuse, tapping it |
| 2 | `planting` | planting, plant the, going for the plant |
| 3 | `last_alive` | last alive, last one, their last, 1 left, one left |
| 4 | `saving` | saving, on eco, eco round, won't buy |
| 5 | `falling_back` | falling back, retreating, backing off, pulled back |
| 6 | `rotating` | rotating, rotate, rotated, rotation |
| 7 | `lurking` | lurking, lurk, flanking, flank, behind us, on our flank |
| 8 | `peeking` | peeking, peek, wide swing, jiggle, shoulder peek |
| 9 | `holding` | holding, anchoring, camping, posted up, waiting |
| 10 | `trading` | traded, refrag, re-fragged, refragged |
| 11 (lowest) | `moving` | pushing, push, rushing, rush, coming, heading, moving, swinging |

**Ult-keyword LIFT** (`_ULT_KW_RE`, line 3873): matches before the keyword scan. This
ensures "their Viper ulted B" routes to the `ult` situation cell (Viper's Pit), NOT
the `utility` pool even if the register was classified as utility.

Named-ult lexicon ("Viper pit", "Jett blade storm", etc.) is handled upstream in the
routing/snap layer, not in `_situation_for`. The regex lift covers generic "ult/ulted"
verbs; named ults would need explicit routing to hit the ult cell via agent+keyword.

### Step 6 — Contextual template path (no agent, `_ctx_candidates`, line 3830)

When no agents are named in the callout, contextual templates are generated per register:

```python
"enemy" register:
    if loc and _standalone_loc(loc):
        → ["They cannot hold {loc}.", "{Loc} will not save them.", "Mortals, pinned at {loc}."]
    if ability:
        → ["Their {ability} changes nothing.", "The {ability} only delays them.", "I accounted for the {ability}."]
    if count in ("1", "one"):
        → ["One target. Trivial.", "A single mortal.", "One. Finish it."]
    if count in ("3".."5"):
        → ["They overcommit.", "More flesh, no more threat."]

"ult" register:
    → ["A delay, nothing more.", "Spend it. Flesh still loses."]
    if ability: → ["The {ability} only delays them."]

"utility" register:
    if ability: → ["Their {ability} is wasted.", "I read the {ability}.", ...]

"command" register:
    if loc and _standalone_loc(loc, for_command=True):
        → ["{Loc} is ours to take.", "Own {loc}."]
```

The `ctx * 4 + pool` weighting (line 3983) ensures contextual templates dominate the
selection 4:1 when present. The generic pool provides breadth when no fact is available.

`_standalone_loc` validation gates:
- Wide `_LOC_TOKENS` membership for all tokens (keeps "arcade", "snake", "hookah")
- Last token NOT in `_LOC_MODIFIERS` (blocks bare "right", "close", "low", "deep")
- `for_command=True`: additionally blocks tokens in `_POSSESSION_LOC_BLOCK` (ct, spawn, back, drop, dish, hell, default, flank)

### Step 7 — Small-pool fast path (relay_speech.py:3973)

```python
if len(cands) < 5:
    return _join_tail(callout, _pick_flavor(cands, recent_lines))
```

The semantic sidecar is SKIPPED entirely when fewer than 5 candidates remain after
tier-filtering. A curated/tag-filtered cell is already a tight fit — LRU rotation
is as good as cosine re-rank on a small pool, and the round-trip to the sidecar costs
real latency. This is a latency optimization (2026-06-16 user directive).

### Step 8 — Output chokepoint `_join_tail` (line 3686)

```python
def _join_tail(head: str, tail: str) -> str:
    head = (head or "").rstrip()
    tail = (tail or "").strip()
    if not _flavor_tails_enabled:      # FLAVOR-OFF GATE
        return head or tail
    if not tail: return head
    if not head: return tail
    if head[-1] not in ".!?":
        head = head + "."              # TTS sentence-pause boundary
    return f"{head} {tail}"
```

This is the **single** place where any tail (agent-contextual, generic, snap, agent-select,
thank-you) can be suppressed at runtime. The guard `not _flavor_tails_enabled` drops the
tail and returns only the head. This makes the voice toggle completely reliable.

---

## Key findings

1. **Three-layer fail-open chain:** The pipeline has three fallback levels:
   (a) `_select_tail` returns None → `_pick_lru` takes over (any sidecar error);
   (b) pool is empty → `_ctx_candidates + _REGISTER_POOL` generic takes over (no agent cell);
   (c) `_join_tail` drops the tail entirely when `_flavor_tails_enabled=False` (flavor toggle).
   Every level is independently fail-open. A missing `_agent_flavor.py` import causes
   `_AGENT_FLAVOR = {}` and silently falls through to generic pools.

2. **ULT-keyword LIFT overrides register classification** (relay_speech.py:3884): the
   word "ult/ulted/ulting/ultimate" in a payload forces `sit = "ult"` even if the snap
   classifier classified the command as `"utility"`. This ensures "their Viper ulted B"
   reaches Viper's `ult` cell (her Pit contempt) not the generic utility pool.

3. **Specificity ladder in `_tier_filter`** (relay_speech.py:3899–3915): after T1 exact-fit
   filter, a specificity ladder picks the most-specific band that has ≥2 tails. This
   prevents specific tails (e.g. `loc:high_ground`) from being diluted by tagless base
   tails in the same cell. The threshold is ≥2, not ≥3, so two precisely-tagged tails
   always beat one generic.

4. **Priority within T2 tag preference is `ability > dmg > loc`** (relay_speech.py:3917):
   when multiple active tags exist but T1 doesn't meet threshold, the single "most
   specific active tag" preferred is an ability tag first, damage second, location third.
   This is a hard-coded priority order — a `"ability:flash"` callout will use the
   flash-tagged entries over any loc-tagged entries.

5. **`_ctx_candidates` generates contextual templates 4:1** (relay_speech.py:3983):
   `ctx * 4 + pool` gives a 4:1 weighting in favor of location/ability/count-specific
   templates over the generic register pool when facts are present. This means the LRU
   anti-repeat sees the templates ~4× as often as generic lines, keeping fact-referencing
   responses varied.

6. **AGENT_GENDER is the only pronoun enforcement mechanism**: `_tail_schema.py:85–101`
   defines canonical pronouns per agent (29 entries). The lint (`lint_agent_flavor`)
   detects opposite-gender pronoun clashes in he/she agents. `they` and `it` gender agents
   (Clove, KAY/O) are NOT checked for pronoun clashes (lint skips them by design — line 333).

7. **Iso has unreachable extended cells**: `_agent_flavor.py:937–982` defines 6 cells with
   parenthetical sub-notes (`falling_back (retreating)`, etc.). These are NEVER reached by
   `_situation_for` (which returns plain keys only). They are likely speculative
   future-proofing for a finer router.

8. **`_MULTI_FLAVOR` has NO `near_death` cell**: `relay_speech.py:3962` handles this with
   `(_MULTI_FLAVOR.get("damaged") if sit == "near_death" else None)`. Single-agent path
   at line 3956 has the same fallback: `near_death → damaged → spotted`.

9. **Sidecar is skipped by default** (`_tail_selector.py:78`): `KENNING_ENABLE_TAIL_SELECTOR`
   must be explicitly set to activate the cosine re-ranker. The deterministic hierarchy
   (situation routing + 4-tier filter) selects a correct cell with zero embeds; the
   sidecar is opt-in for A/B testing or offline pre-computed embeddings.

10. **LRU is global and pool-agnostic** (relay_speech.py:2711): `_LRU_SEEN` stores every
    spoken line's recency by lowercase text. Cross-pool contamination is prevented because
    only the current candidate set is compared (the minimum recency among candidates is
    computed within that set). A greeting line's recency does NOT block a flavor tail.

11. **Context carried by the selector that an LLM would need**: `_select_tail` receives:
    - `agent: str | None` — canonical agent name
    - `situation: str` — fine situation key
    - `active_tags: frozenset[str]` — assembled loc/dmg/ability tags
    - `pool_kind: str` — "agent" | "multi" | "generic"
    For the u1.0 pivot, an LLM authoring its own tail would need the same inputs:
    agent, situation, loc class, damage level, ability, and the full payload string.
    The `_query_for` function (`_tail_selector.py:43`) shows the minimal structured form:
    `"<agent> <situation> <loc_value> <dmg_value> <ability_value>"`.

---

## Flags & config

| Flag / setting | Default | Type | Effect |
|----------------|---------|------|--------|
| `KENNING_FLAVOR_TAILS` | `"1"` (on) | env str | Init value for `_flavor_tails_enabled`. `"0"/"false"/"no"/"off"/""` → tails off at boot. relay_speech.py:1136–1138. |
| `KENNING_ENABLE_TAIL_SELECTOR` | unset (off) | env str | Any truthy value activates the semantic re-ranker. _tail_selector.py:78. Default OFF = zero embed calls, pure LRU determinism. |
| `KENNING_THINKING_MODE` | `"0"` (off) | env str | When OFF: relay compose commands use curated pools; when ON: go to 3B LLM. Orthogonal to flavor toggle. relay_speech.py:1197–1199. |
| `_flavor_tails_enabled` | True | runtime `bool` | Process-global; modified by `set_flavor_tails_enabled(bool)`. Voice command "flavor off/on" routes here. |
| `_thinking_mode_enabled` | False | runtime `bool` | Process-global; modified by `set_thinking_mode_enabled(bool)`. Voice command "thinking mode on/off". |
| `_THRESHOLD["agent"]` | 0.30 | `float` (in _tail_selector.py) | Minimum cosine similarity for agent pool semantic selection. Below threshold → LRU fallback. |
| `_THRESHOLD["multi"]` | 0.26 | `float` | Threshold for multi-agent pool. |
| `_THRESHOLD["generic"]` | 0.20 | `float` | Threshold for no-agent generic pool. |
| `_RECENT` maxlen | 16 | `int` | MMR diversity window: last 16 chosen tail vectors for soft anti-repeat. |
| Small-pool cutoff | 5 | `int` (relay_speech.py:3973) | `len(cands) < 5` → skip sidecar entirely; use LRU. |
| `MAX_TAIL_WORDS` | 14 | `int` (_tail_schema.py:297) | Lint word-count cap per tail. |
| `KENNING_SNAP_REGISTRY` | `"1"` (on) | env str | Enables data-driven SNAP_REGISTRY / TARGET_SNAP_REGISTRY. Off = hardcoded snap fallback only. relay_speech.py:2801. |

---

## Extension points

### EP-B1 — Add a new situation key

1. Add constant to `Sit` class: `_tail_schema.py:55`.
2. Add to `ENEMY_SITUATIONS` tuple: `_tail_schema.py:74`.
3. Add to `_REGISTER_SITUATION` if it's an enemy-facing register: `relay_speech.py:3775`.
4. Add keyword triggers to `_SITUATION_KEYWORDS`: `_tail_schema.py:234`. Insert in
   most-specific-first order (defusing/planting before moving).
5. Add cells to every agent in `_agent_flavor.py`.
6. Add to `_MULTI_FLAVOR` in `_multi_flavor.py`.
7. Re-bless golden digest: `PYTHONHASHSEED=0 python scripts/_voice_lines_verify.py baseline`.

### EP-B2 — Add new location class tokens

Edit `_LOC_CLASS_TOKENS` at `_tail_schema.py:113`. The reverse index `_TOKEN_TO_LOCCLASS`
is built at module load. New tokens are immediately available to `loc_class()` and
`build_active_tags()`. Tag the appropriate tails in `_agent_flavor.py`.

### EP-B3 — Add new ability verb mapping

Edit `_VERB_TO_ABILITY` at `_tail_schema.py:203`. Maps verb/token → canonical category
name. The canonical name becomes the `ability:` tag value in `ability_tag()`. New entries
are available immediately to `ability_tag()` and `build_active_tags()`.

### EP-B4 — Add a new damage tier

Currently only 3 tiers (`minor`, `low`, `one_shot`). To add a tier:
1. Update `dmg_level_tag()` threshold conditions: `_tail_schema.py:172`.
2. Add to `VALID_DMG_LEVELS`: `_tail_schema.py:300`.
3. Tag appropriate tails in `_agent_flavor.py`.
4. Lint and re-bless digest.

### EP-B5 — Add a new generic register pool

1. Define pool in `_ultron_pools.py` (follow the owner-aware rule: enemy-facing = contempt;
   ally-facing = machine-certainty).
2. Add to `_REGISTER_POOL` at `relay_speech.py:3780`.
3. Add calling site in `build_relay_line` / lambda setup at lines 4354–4374.
4. If contextual templates are needed, add to `_ctx_candidates` at line 3830.

### EP-B6 — Pre-compute tail embeddings offline (for sidecar bypass)

The `_DOC_CACHE` in `_tail_selector.py:27` is keyed by `tuple(cands)`. If tail embeddings
are precomputed offline and injected into `_DOC_CACHE` at boot, the sidecar round-trip
is eliminated while keeping the full cosine + MMR ranking. The cache is valid for the
whole session (tails are deterministic per model).

### EP-B7 — LLM-authored flavor tail (u1.0 path)

The substrate for "LLM authors its own context-fitting tail":

```python
# Inputs the LLM tail author needs:
context = {
    "agent": agents[0] if len(agents) == 1 else None,   # e.g. "Jett"
    "situation": sit,                                     # e.g. "spotted"
    "loc_class": next((t for t in active if t.startswith("loc:")), None),  # e.g. "loc:high_ground"
    "dmg_level": next((t for t in active if t.startswith("dmg:")), None),  # e.g. "dmg:one_shot"
    "ability": next((t for t in active if t.startswith("ability:")), None), # e.g. "ability:flash"
    "agent_gender": AGENT_GENDER.get(agents[0]) if agents else None,        # e.g. "she"
    "pool_kind": pk,                                                         # "agent"|"multi"|"generic"
    "exemplars": cands[:5],         # top tier-filtered tails as few-shot examples
    "recent_lines": recent_lines,   # what Ultron has said recently (anti-repeat)
    "payload": payload,             # the full raw callout text
}
```

The `_tier_filter` output is the natural few-shot exemplar set for the 8B: it's already
correct for the (agent, situation, loc/dmg/ability) combination. Injecting the top 3
tier-filtered tails as in-context examples plus the context dict is sufficient for the
8B to author a contextually precise tail in the Ultron voice.

---

## Retire-not-remove candidates (u1.0)

The u1.0 pivot routes ALL responses through the 8B LLM; the deterministic snap paths
become routers and exemplar injectors. Within the flavor-tail pipeline specifically:

| Component | Current role | u1.0 fate | Notes |
|-----------|-------------|-----------|-------|
| `_flavor_ctx` | Selects and appends a curated tail | Repurpose as **context assembler** | Becomes the function that assembles agent/situation/tags/exemplars into a dict for the 8B prompt, no longer the final responder. |
| `_tier_filter` | Narrows cell to context-matching tails | Keep as **exemplar selector** | `_tier_filter(cell, active_tags)[:3]` gives the 8B exactly the right few-shot examples. |
| `_situation_for` | Derives fine situation | Keep fully | The ULT keyword lift and situation refinement logic is needed regardless of whether the tail is curated or LLM-authored. |
| `_build_active_tags` | Assembles tag frozenset | Keep fully | The tag assembly logic (loc/dmg/ability) is the structured context the 8B needs. |
| `AGENT_FLAVOR` (1,628 tails) | Final tail selection | Repurpose as **exemplar library** | The curated tails become few-shot examples injected into the 8B prompt: "for Jett spotted at high_ground, Ultron might say: [top 3 tier-filtered tails]". The 8B authors the final variant. |
| `MULTI_FLAVOR` (group tails) | Final group-contempt tails | Repurpose as **group exemplars** | Same as AGENT_FLAVOR. |
| `_ultron_pools.py` (7 register pools) | Final generic tail selection | Repurpose as **register exemplars** | Injected as register context: "for a COMMAND register, Ultron says things like: [...]". |
| `_pick_lru` | Anti-repeat selection | Retire as final picker | In u1.0, the 8B's own temperature + the `recent_lines` context handle variety. The LRU can remain as a lightweight fallback for edge cases or when the sidecar/8B is down. |
| `_tail_selector` (sidecar re-ranker) | Optional cosine re-rank | Repurpose as **exemplar ranker** | Instead of re-ranking curated tails, the sidecar scores candidate exemplars for relevance and feeds the top 2–3 to the 8B. The architecture is identical; only the final step changes (inject vs. speak). |
| `_join_tail` | Single output chokepoint; flavor toggle gate | Keep fully | The toggle is a user-facing meta-control independent of who authors the tail. For u1.0: when tails are OFF, skip the 8B tail-authoring call entirely (latency savings). When ON, the 8B result goes through `_join_tail`. |
| `_flavor_tails_enabled` | Runtime on/off toggle | Keep; extend to verbosity | u1.0 verbosity: tails OFF = "terse" (no tail at all); tails ON + `max_tokens=25` = "low"; tails ON + `max_tokens=60` = "high". The binary toggle maps to the outer two tiers. |
| `_situation_for_payload` + `_SITUATION_KEYWORDS` | Refines "spotted" to finer state | Keep fully | This keyword-to-situation mapping is the routing logic that selects which exemplar cell the 8B draws from. It stays relevant. |
| `_VERB_TO_ABILITY` + `ability_tag` | Maps ability verbs to tags | Keep fully | Critical for selecting ability-specific exemplars for the 8B. |
| `_LOC_CLASS_TOKENS` + `loc_class` | Maps noisy location to 6 classes | Keep fully | Same — location class selects the right exemplar band. |
| `dmg_level_tag` | Maps HP to damage tier | Keep fully | Same. |
| `AGENT_GENDER` + `GENDER_PRONOUNS` | Hard-gates wrong pronouns in curated tails | Keep; extend to LLM validation | In u1.0, the 8B could still generate a wrong-gender pronoun. The gender map can gate a post-generation validation pass (detect → retry or substitute). |
| `lint_agent_flavor` | Audits curated library for integrity | Keep and extend | Extend to validate exemplar format + tag completeness. Also useful for auditing any new tails added to the exemplar library. |
| `_ctx_candidates` | Generates 3 contextual template strings per fact | Retire as final output; preserve as **template exemplars** | In u1.0, these contextual templates become the richest exemplars (they already reference the specific fact). Feed them as preferred examples to the 8B. |
| Small-pool fast path (`len < 5`) | Skips sidecar for small cells | Retire or rethink | In u1.0 the 8B is always called for authored tails; this heuristic becomes irrelevant. However, the threshold can be repurposed: if ≤2 exemplars exist, inject all of them (no selection needed). |

---

## Gotchas

1. **`_situation_for_payload` returns ONLY plain situation keys** — Iso's parenthetical
   cells (`falling_back (retreating)`, etc.) are permanently unreachable from the standard
   dispatch. If a finer router is built for u1.0, these cells need explicit routing with
   the full key string.

2. **ULT-keyword lift is UNCONDITIONAL**: any payload containing "ult/ulted/ultimate"
   routes to the `ult` situation even if the agent or register does not warrant it.
   "I have my ult" → `sit = "ult"` even though this is a self-status line. This is
   mostly harmless (the `ult` cell has appropriate contempt tails for enemy ults) but
   could produce minor semantic mismatches for "I saved my ult" type self-status
   callouts.

3. **`_MULTI_FLAVOR` has no `near_death` cell**: single-agent path falls to `damaged`
   then `spotted` (`near_death → damaged → spotted`). Multi-agent path also falls to
   `damaged` then `spotted` (`relay_speech.py:3962`). Near-death multi-agent contempt
   is always from the `damaged` pool — the finality / clutch nuance is lost.

4. **The generic `_ctx_candidates` path ignores `payload` for ability-tag extraction**:
   `_ctx_candidates` at line 3830 receives `ability` as a pre-extracted string, not the
   raw payload. The ability string comes from `_payload_flavor_facts`'s `"ability"` key,
   which is the FIRST ability token found (not the most relevant). If a callout mentions
   two abilities, only the first is used as the template anchor.

5. **T2 tag preference is hard-coded** at `("ability:", "dmg:", "loc:")` in `_tier_filter`
   line 3917. Adding a 4th tag namespace (e.g., a side tag like `side:attacker`) requires
   updating this tuple to define where the new namespace fits in the fallback hierarchy.

6. **Cross-pool LRU accumulation over time**: `_LRU_SEEN` grows unboundedly over a
   session. After thousands of callouts, every tail in every pool has an LRU entry.
   The anti-repeat works per-pool (only the minimum within the candidate set is used),
   but memory growth is unchecked. Not an issue at normal session lengths.

7. **`_AGENT_FLAVOR` fail-open is silent**: a corrupted or missing `_agent_flavor.py`
   produces `_AGENT_FLAVOR = {}` at relay_speech.py:3742 with no warning. All agent-named
   callouts fall through to the generic `_FLAVOR_ENEMY` pool with no indication that
   the per-agent library is missing.

8. **The `dmg_level_tag` function imports `re` inline** (`_tail_schema.py:183`):
   `import re as _re` is inside the function body. This is standard Python (module is
   cached after first import) but unusual and could confuse tools scanning imports.

9. **Fact extraction by `_roster_agents` vs `_fact_tokens`**: there are TWO agent-extraction
   paths: `_roster_agents(text)` (ordered, via `_ROSTER_RE`/`_ROSTER_CANON`) and
   `_fact_tokens(text).agents` (set, via `_ROSTER_CANON` dict key membership). The
   flavor pipeline uses `_roster_agents` (via `_payload_flavor_facts`) for the `agents`
   list passed to `_flavor_ctx`. The set from `_fact_tokens` is used elsewhere (compound
   callout detection, literal relay). These must stay in sync if the agent canon changes.

10. **`_select_tail` has a `len(cands) < 2` early abort** (`_tail_selector.py:70`):
    a single-candidate cell skips the sidecar entirely (no meaningful re-rank on one
    option). Combined with the `< 5` fast path in `_flavor_ctx`, the sidecar is only
    consulted on pools of 5–N entries. A deeply curated cell with only 4 situation-specific
    entries (e.g. a newly added situation) always uses LRU.

---

## Open questions

1. **Iso's extended parenthetical situation cells** (`_agent_flavor.py:937–982`): are these
   intended for future routing, or are they orphaned? Would a finer u1.0 router want to
   reach them (e.g., "clutch" situation vs. "last_alive"), or should they be migrated to
   standard keys?

2. **Named-ult lexicon** ("Viper pit", "Jett blade storm", "Sova drone"): the current ULT
   lift only catches the generic "ult" word. Named ult callouts need upstream routing to
   set the register to `"ult"` before `_flavor_ctx` is called, OR the ULT keyword pattern
   `_ULT_KW_RE` needs to expand to include named ult references. Is there a planned routing
   layer for this in u1.0?

3. **Ability tag priority over DMG tag in T2 filtering**: is `ability > dmg > loc` the right
   priority order? For a "hit Jett for 84 while she dashed" callout, both `dmg:one_shot`
   and `ability:dash` are active. T2 selects ability-tagged tails. Is a dash-specific tail
   more fitting than a one-shot-specific tail here? This is a design choice that should
   be validated against real callout patterns.

4. **Generic pool for `careful` register has no contextual templates**: `_ctx_candidates`
   at line 3830 generates no templates for `"careful"` register (only enemy/ult/utility/command
   get templates). A careful callout ("careful ramp") always falls to the generic `_FLAVOR_CAREFUL`
   pool. If the location in "careful ramp" should be referenced in the tail, a template path
   needs to be added.

5. **No template for `self` register either**: similar to `careful`, the `self` register
   generates no contextual templates. "I'm low at A" just gets a generic stoic tail from
   `_FLAVOR_SELF` without referencing "A" or "low HP". In u1.0, the LLM could naturally
   incorporate these facts.

6. **Miks and Veto**: these appear to be custom/non-canon Valorant agents at `_agent_flavor.py`
   (Miks:he line ~1236, Veto:he line ~2093). Are they released agents (not in standard Valorant
   as of 2025), planned agents, or prototype placeholders? Their status affects whether to
   maintain them in the u1.0 agent roster.

7. **LRU cross-session persistence**: `_LRU_SEEN` is a module-global dict that resets on
   restart. There is no disk-persisted session memory for tail selection. After restart,
   Ultron could repeat a tail that was just spoken 5 minutes ago (before the restart). Is
   cross-session LRU persistence worth implementing for u1.0?

8. **MMR lambda tuning** (`_tail_selector.py:99`): λ=0.85 for ≥10 candidates, λ=0.65
   otherwise. These values were not empirically calibrated for the Valorant callout domain.
   For u1.0, with the 8B as the author, is MMR in the exemplar-selection layer still
   the right diversity mechanism, or should the 8B's temperature handle it?

9. **Verbosity tier mapping**: the existing toggle is binary (on/off). The u1.0 spec says
   no/low/high verbosity. "Low verbosity" could mean: (a) tails off, shorter curated
   callouts; (b) 8B with tight `max_tokens` cap; or (c) shorter exemplar pool injected.
   The exact mapping should be defined before implementation.

10. **`_flavor_tails_enabled` initialization order**: `relay_speech.py:1134` uses `import os as _os_flavor`
    immediately before line 1136. The env var is read at module import time. If a caller
    sets `KENNING_FLAVOR_TAILS=0` AFTER importing `relay_speech`, the module-level bool
    is already set to True. Runtime toggle (`set_flavor_tails_enabled`) is the safe path.
