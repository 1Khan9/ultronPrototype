# B5: MAP the data-driven snap registry & the "add a new snap" contract

Recon date: 2026-06-20. Agent: claude-sonnet-4-6 (infallible-kepler worktree).
All citations are repo-root-relative paths at HEAD of branch
`claude/infallible-kepler-0a865d`.

---

## Overview

The **snap registry** is a data-driven dispatch layer (Part C, 2026-06-18)
that lets a developer add a brand-new deterministic "tell my team X" snap
(or a target-addressed command "say/ask \<team|agent\> …") by **appending one
dataclass instance to a tuple** in `src/kenning/audio/voice_lines.py` — no
pipeline code change required.

Two independent registries exist:

| Registry | Class | Location in `voice_lines.py` | Purpose |
|----------|-------|------------------------------|---------|
| `SNAP_REGISTRY` | `SnapRule` | line 330 | Payload-based snaps ("I got this", "nice try", "unlucky", "gg") |
| `TARGET_SNAP_REGISTRY` | `TargetSnapRule` | line 363 | Target-addressed commands ("say hello to \<team\|agent\>", "ask \<target\> how their day") |

Both registries are:
- **Pure data** in `voice_lines.py` (the aggregate file); no dispatch logic lives there.
- **Consumed by three functions** in `relay_speech.py`:
  `_apply_snap_registry`, `_match_target_registry`, `_render_target_registry`.
- **Runtime-gated** by the single env var `KENNING_SNAP_REGISTRY` (default ON).
- **Fail-open**: a `try/except` wraps every registry iteration; an import or
  attribute error silently falls through to the hardcoded snap functions.
- **Covered by a golden-digest gate** (`tests/test_voice_lines_golden.py`) that
  runs `scripts/_voice_lines_verify.py check` in a subprocess with
  `PYTHONHASHSEED=0`; any unintentional edit to a rule, regex, or pool fails CI.

### Key invariant: hardcoded fallbacks remain

The hardcoded functions (`_as_clutch`, `_as_consolation_or_praise`, and the
hardcoded `hello` / `ask_day` branches in `build_relay_line`) remain as a
safety net. The registry's None return falls through to them. Turning the
registry off (`KENNING_SNAP_REGISTRY=0`) reactivates the hardcoded path
exclusively, making the registry fully reversible.

---

## Files & key symbols

### `src/kenning/audio/voice_lines.py` — data definitions

| Symbol | Line(s) | Kind | Description |
|--------|---------|------|-------------|
| `SnapRule` | 319–325 | `@dataclass(frozen=True)` | One payload snap: `name:str`, `match:re.Pattern`, `kind:str` ("pool"\|"head_tail"), `lines:tuple`, `tails:tuple` |
| `SNAP_REGISTRY` | 330–336 | `tuple[SnapRule, ...]` | 4 rules (clutch→pool, nice_try→head_tail, consolation→pool, praise→pool) |
| `TargetSnapRule` | 353–360 | `@dataclass(frozen=True)` | Target snap: `name:str`, `match:re.Pattern`, `team_lines:tuple`, `agent_templates:tuple`, `skip_if_contains:tuple` |
| `TARGET_SNAP_REGISTRY` | 363–375 | `tuple[TargetSnapRule, ...]` | 2 rules (hello, ask_day) |

**SnapRule fields:**

```python
@dataclass(frozen=True)
class SnapRule:
    name: str
    match: re.Pattern
    kind: str = "pool"          # "pool" | "head_tail"
    lines: tuple = ()           # for kind="pool"
    tails: tuple = ()           # for kind="head_tail"
```

**TargetSnapRule fields:**

```python
@dataclass(frozen=True)
class TargetSnapRule:
    name: str                   # == RelayCommand.directive
    match: re.Pattern           # must capture named group "target"
    team_lines: tuple = ()
    agent_templates: tuple = () # {name} templates
    skip_if_contains: tuple = () # phrases (lowercased) that disqualify the rule
```

### Current SNAP_REGISTRY contents (voice_lines.py:330–336)

| Rule name | Regex symbol | Regex location | kind | Pool/tails source |
|-----------|-------------|----------------|------|-------------------|
| `clutch` | `_CLUTCH_RE` | voice_lines.py:222 | `pool` | `DEFAULT_CLUTCH_LINES` (from `_ultron_setpieces`) |
| `nice_try` | `_NICE_TRY_RE` | voice_lines.py:202 | `head_tail` | `_NICE_TRY_TAILS` (10 tails, voice_lines.py:206) |
| `consolation` | `_CONSOLATION_RE` | voice_lines.py:188 | `pool` | `DEFAULT_CONSOLATION_LINES` (from `_ultron_setpieces`) |
| `praise` | `_PRAISE_RE` | voice_lines.py:193 | `pool` | `DEFAULT_PRAISE_LINES` (from `_ultron_setpieces`) |

### Current TARGET_SNAP_REGISTRY contents (voice_lines.py:363–375)

| Rule name | Regex symbol | Regex location | team_lines | agent_templates | skip_if_contains |
|-----------|-------------|----------------|------------|----------------|------------------|
| `hello` | `_HELLO_RE` | voice_lines.py:142 | `("Hello team.",)` | `("Hello, {name}.",)` | `("introduce",)` |
| `ask_day` | `_ASK_DAY_RE` | voice_lines.py:157 | `_ASK_DAY_TEAM_LINES` (8 lines) | `_ASK_DAY_AGENT_TEMPLATES` (6 templates) | — |

### `src/kenning/audio/relay_speech.py` — dispatch functions

| Symbol | Line(s) | Role |
|--------|---------|------|
| `_apply_snap_registry(payload, recent_lines)` | 2791–2822 | Iterates `SNAP_REGISTRY` in order; renders first match (pool→`pick_line`, head_tail→`_join_tail(head, pick_line(tails))`); returns None on no-match/disabled/error |
| `_match_target_registry(cleaned, text)` | 2842–2870 | Iterates `TARGET_SNAP_REGISTRY`; returns a `RelayCommand(payload=rule.name, directive=rule.name, addressee=tgt)` on match; None otherwise |
| `_render_target_registry(command, recent_lines)` | 2873–2898 | Finds `TARGET_SNAP_REGISTRY` rule matching `command.directive`; renders team line or `agent_templates.format(name=tgt)`; None on no-match/disabled/error |
| `_resolve_hello_target(raw)` | 1253–1274 | Resolves the `target` capture group → "team" or canonical agent name; used by both target-registry functions |
| `_name_social_snap(line, command)` | 2825–2839 | Prepends addressee agent to a snap line for flavor-ON parity (e.g. "Sage, nice try. …"); team-addressed lines unchanged |
| `pick_line` | 2748 (alias of `pick_roast_line`) | LRU-based anti-repeat pool picker; used by all registry renders |
| `_join_tail(head, tail)` | 3686–3709 | Joins callout + flavor tail with sentence terminator; **single chokepoint** for `_flavor_tails_enabled` — drops tail when OFF |
| `_as_clutch(payload, recent_lines)` | 2783–2788 | Hardcoded fallback for clutch snap |
| `_as_consolation_or_praise(payload, recent_lines)` | 2901–2914 | Hardcoded fallback for consolation/nice-try/praise snaps |

### `src/kenning/pipeline/orchestrator.py` — snap call site

| What | Line(s) |
|------|---------|
| Import of `build_relay_line`, `match_relay_command` | 3444–3446 |
| `match_relay_command` call (where `_match_target_registry` fires) | 3479 |
| `build_relay_line` call (where `_apply_snap_registry` and `_render_target_registry` fire) | 3555 |

### `scripts/_voice_lines_verify.py` — golden digest harness

| What | Line(s) | Notes |
|------|---------|-------|
| Module list digested | 39–56 | 16 modules; includes `kenning.audio.voice_lines`, `kenning.audio.relay_speech` |
| `SnapRule`/`TargetSnapRule` digest strategy | 79–83 | Tuples of frozen dataclasses → `{"kind":"dataclass_seq","repr":repr(v)}`; reorder/drop/rewire is caught |
| `PYTHONHASHSEED=0` requirement | harness+test | Needed because some regexes compiled from sets; subprocess enforced |
| Golden file path | 34–36 | Default `logs/_voice_lines_digest.json`; CI overrides with `KENNING_VOICE_LINES_DIGEST=tests/data/voice_lines_golden_digest.json` |

### `tests/test_voice_lines_golden.py` — CI gate

Runs `scripts/_voice_lines_verify.py check` with `PYTHONHASHSEED=0` and
`KENNING_VOICE_LINES_DIGEST=tests/data/voice_lines_golden_digest.json`. Fails
if any voice line, regex, threshold, or registry rule diverges from the
committed golden. Re-bless via `baseline` subcommand + commit the updated JSON.

---

## Control/data flow

### Path A: payload snap (SNAP_REGISTRY)

```
User speech
  -> orchestrator._handle_relay_command
      -> match_relay_command(text)                     # relay_speech.py line 1860+
           -> <strict relay matchers, NOT snap-specific>
           -> returns RelayCommand(payload="nice try", ...)
      -> build_relay_line(command, llm, rephrase=…)    # relay_speech.py line 6012
           [1] flavor_tails_enabled() check → _flavor_off_response (returns if tails OFF)
           [2] verbatim check (returns if verbatim=True)
           [3] _render_target_registry(command) -- for TARGET snaps; None here
           [4] _as_curated_command(command) -- curated command pool; None here
           [5] _as_curated_reaction(command) -- social reactions; None here
           [6] roast / fun_fact fast-path
           [7] compose morale fast-path
           [8] greet/farewell directive_pools fast-path
           [9] calm / criticize / flame_enemy / stop_command / compliment / identity / fact
           [10] _is_morale_phrase check → DEFAULT_ENCOURAGEMENT_LINES (None here)
           [11] _apply_snap_registry(payload, recent_lines)  ← SNAP_REGISTRY HERE
                  -> iterates SNAP_REGISTRY in order
                  -> "nice try" matches SnapRule("nice_try", _NICE_TRY_RE, "head_tail", tails=_NICE_TRY_TAILS)
                  -> m.group(1) = "nice try", head = "Nice try"
                  -> _join_tail("Nice try", pick_line(_NICE_TRY_TAILS, recent_lines))
                  -> returns "Nice try. We take the next." (example)
           [12] _name_social_snap(reg, command) -- prepends addressee if named agent
           -> _cap_line(result, max_chars) -> FINAL LINE
```

### Path B: target snap (TARGET_SNAP_REGISTRY)

```
User speech: "say hello to my team"
  -> orchestrator._handle_relay_command
      -> match_relay_command("say hello to my team")   # relay_speech.py line 1857+
           -> not verbatim
           -> _match_target_registry(cleaned, text)
                -> iterates TARGET_SNAP_REGISTRY
                -> "say hello to my team" matches TargetSnapRule("hello", _HELLO_RE, …, skip_if_contains=("introduce",))
                -> "introduce" not in text -> not skipped
                -> _HELLO_RE.match("say hello to my team") -> m.group("target") = "my team"
                -> _resolve_hello_target("my team") -> "team"
                -> returns RelayCommand(payload="hello", directive="hello", addressee="team")
           -> returns that RelayCommand
      -> build_relay_line(command, llm, rephrase=…)
           [1] flavor_tails_enabled() / verbatim / ...
           [3] _render_target_registry(command)        ← TARGET SNAP RENDER HERE
                -> finds rule with name=="hello"
                -> addressee=="team" -> pick_line(("Hello team.",), recent_lines)
                -> returns "Hello team."
           -> _cap_line("Hello team.", max_chars) -> FINAL LINE
```

### Hardcoded fallback path (when KENNING_SNAP_REGISTRY=0 or exception)

Both `_apply_snap_registry` and `_match_target_registry`/`_render_target_registry`
return None. `build_relay_line` then falls to:
- `_as_clutch(payload, recent_lines)` — hardcoded clutch snap (relay_speech.py:2783)
- `_as_consolation_or_praise(payload, recent_lines)` — hardcoded nice-try/consolation/praise (relay_speech.py:2901)
- `hello` / `ask_day` directive branches in `build_relay_line` (lines 6068–6082)

---

## Key findings

1. **The contract for "add a new payload snap" is truly one-line**: append one
   `SnapRule(name, match_re, "pool", lines=(...))` to `SNAP_REGISTRY` in
   `voice_lines.py`. No function, no if-branch, no import needed. Tested and
   demonstrated in `tests/audio/test_relay_speech.py:test_snap_registry_routes_and_is_data_extensible`.

2. **The contract for "add a new target snap" is also one-line**: append one
   `TargetSnapRule(name, match_re, team_lines=(...), agent_templates=(...))` to
   `TARGET_SNAP_REGISTRY`. Both the matcher (`_match_target_registry`) and
   renderer (`_render_target_registry`) auto-discover it. Tested at
   `tests/audio/test_relay_speech.py:test_target_snap_registry_is_data_extensible` (line 723).

3. **First-match-wins precedence**: rules are tried in tuple order.
   APPENDING to the end only works if no earlier rule already claims the trigger.
   A more specific rule that overlaps a broader one must be INSERTED before it.

4. **`_join_tail` is the single chokepoint for flavor-tails OFF**: both
   `_apply_snap_registry` (for `head_tail` kind) and the hardcoded snap
   functions call `_join_tail`. Setting `_flavor_tails_enabled = False`
   (via voice toggle or `KENNING_FLAVOR_TAILS=0`) causes `_join_tail` to
   return head-only, dropping the tail for ALL snaps uniformly.

5. **`thank-you` and `agent-select` are NOT in SNAP_REGISTRY**: they live
   in `_as_snap_callout` (relay_speech.py:4410–4425), which runs AFTER
   `_apply_snap_registry` in the `build_relay_line` dispatch chain. Both use
   `_pick_lru` (global process-wide LRU), not `pick_line`'s recent-ring
   anti-repeat. This is an inconsistency with the data-driven pattern.

6. **`_name_social_snap` (flavor parity, 2026-06-19)**: wraps the registry
   result to prepend the addressed agent ("Sage, nice try. …") when
   `command.addressee` is not "team". This was a discovered inconsistency
   (the registry produced the bare line, hardcoded functions named the agent).

7. **Golden digest covers the registries**: `scripts/_voice_lines_verify.py`
   digests `SNAP_REGISTRY` and `TARGET_SNAP_REGISTRY` as frozen-dataclass
   sequences (repr-based). CI (`tests/test_voice_lines_golden.py`) fails on
   any unintentional change. Re-bless by running `baseline` with
   `PYTHONHASHSEED=0` and committing the JSON.

8. **The orchestrator does not pre-intercept snap commands**: it calls
   `match_relay_command` and then `build_relay_line`. The snap registry
   is entirely inside those two functions — the orchestrator is unaware
   of which branch fired.

9. **`_match_target_registry` fires in the MATCHER** (`match_relay_command`),
   while `_apply_snap_registry` fires in the RENDERER** (`build_relay_line`).
   This means target snaps produce a `RelayCommand` object (with `directive`
   set to the rule name) that flows through the full orchestrator path
   (logging, ring update, etc.), while payload snaps bypass that level —
   they are rendered directly in `build_relay_line`.

10. **`rephrase=False` (thinking-mode OFF, the default)**: the orchestrator
    gates `rephrase` by `thinking_mode_enabled()`. When thinking mode is off,
    `build_relay_line` still fires the registry snaps (they are deterministic
    and do not call the LLM), so snap latency is unaffected by thinking mode.

---

## Flags & config

| Flag | Type | Default | Effect |
|------|------|---------|--------|
| `KENNING_SNAP_REGISTRY` | env var | `"1"` (ON) | `"0"/"false"/"no"/"off"` → all three registry functions return None; hardcoded snaps become the sole path |
| `KENNING_FLAVOR_TAILS` | env var | `"1"` (ON) | `"0"` sets `_flavor_tails_enabled=False`; `_join_tail` returns head-only for ALL snaps |
| `KENNING_THINKING_MODE` | env var | `"0"` (OFF) | `"1"` enables LLM authoring in `build_relay_line`; snap paths are deterministic and unaffected |
| `config.yaml: relay_speech.rephrase` | config bool | `true` | Combined with thinking_mode_enabled() in orchestrator to set `rephrase` kwarg |
| `KENNING_VOICE_LINES_DIGEST` | env var | `logs/_voice_lines_digest.json` | Path override for golden-digest CI gate (CI sets to `tests/data/voice_lines_golden_digest.json`) |

---

## Extension points

1. **Add a payload snap** (`voice_lines.py:SNAP_REGISTRY`): append one
   `SnapRule` entry. The worked example in the file header (lines 302–313):
   ```python
   SnapRule(
       name="execute",
       match=re.compile(r"^\s*(execute|run it|go time|it'?s time)\b", re.I),
       kind="pool",
       lines=("Execute. The outcome is decided.", "Now. No hesitation."),
   )
   ```
   Then re-bless the golden digest.

2. **Add a target snap** (`voice_lines.py:TARGET_SNAP_REGISTRY`): append one
   `TargetSnapRule`. The worked example in the file header (lines 346–350):
   ```python
   TargetSnapRule("wish_luck",
       re.compile(r"^(?:please\s+)?wish\s+(?P<target>.+?)\s+(?:good\s+)?luck", re.I),
       team_lines=("Luck is for the unprepared. But -- proceed.",),
       agent_templates=("{name}. Luck is beneath you. Win anyway.",)),
   ```
   Target regex MUST capture named group `"target"`. Re-bless the golden digest.

3. **Add a snap kind beyond "pool" and "head_tail"**: extend the
   `_apply_snap_registry` dispatcher at relay_speech.py:2812–2819.
   Currently only two branches (`head_tail` and default/pool).

4. **Move `thank-you` and `agent-select` into SNAP_REGISTRY**: they currently
   live as hardcoded branches in `_as_snap_callout`. Moving them would make
   them editable data-only. Requires migrating their `_pick_lru` calls to
   `pick_line` (different anti-repeat strategy) or adding a third kind to
   `SnapRule`.

5. **Migrate the registries to disk (YAML/JSON)**: the current design is
   in-code tuples. An external file would allow hot-reloading without restart
   and non-developer editing. The verify harness would need updating.

6. **u1.0 prompt-routing rules**: for the LLM-centric pivot, each `SnapRule`
   (or `TargetSnapRule`) can evolve into a **routing rule** that picks a
   curated prompt template and injects the existing snap pool as in-context
   exemplars. The `kind` field would gain a "prompt_template" value; the
   `lines` tuple becomes the exemplar bank.

---

## Retire-not-remove candidates (u1.0)

| Symbol / path | Status | u1.0 disposition |
|---------------|--------|-----------------|
| `SNAP_REGISTRY` / `SnapRule` in `voice_lines.py` | Active, data-driven | **Repurpose as prompt-routing rules**: rule's regex detects intent, rule's lines become exemplars for an LLM prompt template. The `_apply_snap_registry` function becomes `_route_snap_to_prompt`. |
| `TARGET_SNAP_REGISTRY` / `TargetSnapRule` | Active, data-driven | Same: repurpose as target-aware prompt routers; `team_lines` / `agent_templates` become exemplar banks. |
| `_apply_snap_registry` | Active dispatcher | Rename / extend to `_route_via_registry`; inject snap lines as in-context examples into LLM call |
| `_match_target_registry` | Active matcher | Keep as-is (the matching logic is reusable); wiring changes |
| `_render_target_registry` | Active renderer | Replace with LLM-prompt renderer; fall back to current pick-line for thinking-mode-off fast-path |
| Hardcoded `_as_clutch`, `_as_consolation_or_praise` | Fallback | Retire as primary; keep as thinking-mode-off fast-path OR as deterministic exemplar picker |
| Hardcoded `hello`/`ask_day` branches in `build_relay_line` (lines 6068–6082) | Fallback | Retire; they exist ONLY as safety net below the registry; can be removed once registry is stable |
| `_as_snap_callout` `thank-you`/`agent-select` hardcoded branches (lines 4410–4425) | NOT in registry (inconsistency) | Migrate into `SNAP_REGISTRY` first, then repurpose with u1.0 |

---

## Gotchas

1. **Precedence silently swallows a new rule**: if you append a "well played"
   rule, it will NEVER fire because the existing `praise` rule (`_PRAISE_RE`)
   already matches "well played". Debug by checking all existing regexes first.

2. **`target` group is mandatory in `TargetSnapRule.match`**: `_match_target_registry`
   calls `m.group("target")` unconditionally (relay_speech.py:2862). A regex
   without that named group raises a `KeyError` caught by the broad
   `except Exception` and silently falls through.

3. **Golden digest must be re-blessed after any registry change**: forgetting
   to run `PYTHONHASHSEED=0 python scripts/_voice_lines_verify.py baseline`
   and commit `tests/data/voice_lines_golden_digest.json` will fail CI. The
   failure message tells you exactly what diverged.

4. **`_join_tail` vs `_pick_lru` inconsistency**: payload snaps in
   `SNAP_REGISTRY` use `pick_line` (recent-ring anti-repeat); hardcoded
   `_as_snap_callout` snaps (`thank-you`, `agent-select`) use `_pick_lru`
   (global process-wide LRU). Both avoid repeats but in different scopes.

5. **`_name_social_snap` only wraps `_apply_snap_registry` output, not
   `_render_target_registry` output**: target snaps embed the agent name
   via `{name}` template formatting, so they don't need wrapping. But if
   a new `SnapRule` in `SNAP_REGISTRY` is agent-addressed (unusual), it
   WILL get the `_name_social_snap` prefix — potentially double-naming.

6. **The registry import is deferred (`from kenning.audio.voice_lines import
   SNAP_REGISTRY` inside the function body)**: this means `voice_lines.py`
   is imported lazily on first registry call. Hot-patching `SNAP_REGISTRY`
   via `monkeypatch.setattr(vl, "SNAP_REGISTRY", …)` works in tests because
   the import already happened; restarting the process resets to disk state.

7. **`skip_if_contains` is case-insensitive substring match on `cleaned.lower()`**
   (relay_speech.py:2857). A rule with `skip_if_contains=("introduce",)` will
   skip any input containing the string "introduce" anywhere, including
   "reintroduce", "introductory", etc. This is intentional for the `hello`
   rule but can be surprising for new rules.

8. **`thinking_mode_enabled()` does NOT affect snap routing**: snaps are
   always deterministic. `rephrase=False` only prevents the LLM authoring
   path in `build_relay_line`; snap registry is checked before the LLM
   reaches for compose paths (step [11] in the dispatch order above). The
   thinking-mode toggle only matters for lines that fall through to the
   LLM at the very bottom.

---

## Open questions

1. **Should `thank-you` and `agent-select` move into `SNAP_REGISTRY`?**
   They are semantically identical to other registry rules but live in
   `_as_snap_callout`. The inconsistency means they use a different
   anti-repeat strategy and are not visible as data. Proposed for u1.0.

2. **LRU scope**: `pick_line` uses a global `_LRU_SEEN` dict (process-wide).
   For a multi-user or async architecture this would need to become
   per-session. Is this in scope for u1.0?

3. **SnapRule `kind` extensibility**: for u1.0's prompt-routing role, should
   `kind` gain a `"prompt_template"` value? Or should the registry be replaced
   with a richer `RoutingRule` dataclass that carries a prompt key, an exemplar
   bank, and a render strategy?

4. **Hot-reload of registries**: currently the tuple is frozen at import time.
   For the u1.0 add-a-snap-without-restart workflow, is hot-reload needed?
   The file header comment implies restart is acceptable ("append… with no
   pipeline code"), but a live-edit capability would be natural for the dev
   loop.

5. **`skip_if_contains` is a blunt substring filter**: should it accept
   callable predicates for more nuanced disqualification in u1.0?

6. **`_resolve_hello_target` is coupled to `_stt_correct._AGENT_LOWER`**
   (relay_speech.py:1264): if `_stt_correct` is absent, the target resolver
   falls back to None (only `_HELLO_TEAM_WORDS` match). Should the resolver
   be a first-class extension point for u1.0's broader agent/target recognition?

7. **No "no target" arm for `TargetSnapRule`**: a rule with optional target
   (like `_HELLO_RE`, which has `(?P<target>…)?`) handles the bare "say hello"
   case by treating `_raw_tgt is None` as team in the hardcoded block
   (relay_speech.py:1873–1874), but `_match_target_registry` calls
   `_resolve_hello_target(m.group("target"))` without a None-guard
   (relay_speech.py:2862). This works because `_resolve_hello_target` handles
   None inputs, but it is fragile for new rules with optional target groups.
