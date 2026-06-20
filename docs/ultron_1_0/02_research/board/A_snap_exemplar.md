# A: Snap-as-Router + Exemplar + Flavor Injection — Attach-Point Validation

**Validator:** claude-sonnet-4-6, worktree `infallible-kepler-0a865d`, 2026-06-20.
Sources read: `relay_speech.py` (6,751 lines), `voice_lines.py` (376 lines),
`_agent_flavor.py`, `_tail_schema.py`, `_tail_selector.py`, `_command_exemplars.py`,
`00_codebase_map.md`, `boardA_relay_speech.md`, `boardB_snap_registry.md`,
`boardB_flavor_selection.md`, `boardA_voice_lines_flavor.md`,
`boardA_semantic_router.md`, `boardB_llm_invocation.md`.

---

## Confirmed attach points (path:line)

### 1. `build_relay_line` — the 28-step chain entry point and LLM rephrase step

`src/kenning/audio/relay_speech.py:6012` — `build_relay_line(command, llm, *, rephrase, ...)`.
This is the correct, stable anchor. The 28-step dispatch is exactly here. The LLM rephrase
path (step 27 in the recon docs) starts at `relay_speech.py:6326` (the `if rephrase:` block).
The answer-path (`build_answer_call`) fires at `relay_speech.py:6332`.
The plain rephrase (`_build_rephrase_prompt` + `_RELAY_REPHRASE_SYSTEM`) fires at `relay_speech.py:6357`.

**u1.0 attach:** promote `rephrase=True` to the default/primary path, not the last resort.
The function signature already supports a `generate_fn` test seam (`relay_speech.py:6019`) —
the exemplar-injecting LLM call can replace the body of the rephrase block without changing
the function signature or its callers.

### 2. SNAP_REGISTRY / TargetSnapRule — the data-driven extension contract

`src/kenning/audio/voice_lines.py:318–375` — `SnapRule` (dataclass, line 318), `SNAP_REGISTRY`
tuple (line 330, 4 rules), `TargetSnapRule` (line 353), `TARGET_SNAP_REGISTRY` (line 363, 2 rules).

Dispatcher in `relay_speech.py`:
- `_apply_snap_registry` at `relay_speech.py:2791` — iterates `SNAP_REGISTRY`; called at
  `build_relay_line` step 21 (inside the `if not compose and not context and not verbatim` guard,
  line ~6247).
- `_match_target_registry` at `relay_speech.py:2842` — fires inside `match_relay_command`,
  producing a `RelayCommand(directive=rule.name)`.
- `_render_target_registry` at `relay_speech.py:2873` — fires at `build_relay_line` step 3
  (line 6061), BEFORE the curated command check.

**u1.0 attach:** `SnapRule` gains a `kind="prompt_template"` value (or a separate `RoutingRule`
dataclass). The `lines`/`tails` tuples become in-context exemplar banks. `_apply_snap_registry`
at `relay_speech.py:2791` becomes `_route_via_registry` — on a match it calls
`llm.generate_stream` with the rule's system prompt + the `lines` pool injected as few-shot
examples, instead of calling `pick_line`. The fail-open `except Exception` wrapper at
`relay_speech.py:2820` ensures any LLM failure falls back to the existing `pick_line` path.

### 3. Deterministic snap callout chain — `_as_snap_callout`

`src/kenning/audio/relay_speech.py:4327` — `_as_snap_callout(command, recent_lines, flavor=True)`.
This is confirmed at line 4327 (grep-verified). The 20-handler chain runs through to `_parse_callout_slots`
at `relay_speech.py:4284`. The `_as_compound_callout` entry point is at `relay_speech.py:4780`.

`thank-you` snap: `relay_speech.py:4421`; `agent-select` snap: `relay_speech.py:4410`.
Both are confirmed inside `_as_snap_callout`, NOT in `SNAP_REGISTRY` — the inconsistency
noted in the recon docs is real and verified.

**u1.0 attach:** each handler in `_as_snap_callout` is a taxonomy node. The handler's curated
pool (e.g. `_THANK_YOU_TAILS`, `_AGENT_SELECT_TAILS`, `_FLAVOR_DAMAGE`) becomes the exemplar
bank for the LLM prompt template for that node. The handler functions remain as fast-path
fallbacks when `rephrase=False` or LLM unavailable.

### 4. Flavor selection pipeline — entry points

- `_flavor_ctx` at `relay_speech.py:3931` — the main flavor selection entry point. Takes
  `(callout, register, recent_lines, *, agents, ability, loc, count, payload)`.
- `_payload_flavor_facts` at `relay_speech.py:3989` — extracts `{agents, loc, ability, count, payload}`
  from raw payload. Called once per `build_relay_line` call.
- `_join_tail` at `relay_speech.py:3686` — the single chokepoint; drops tail when
  `_flavor_tails_enabled == False`.
- `_pick_lru` at `relay_speech.py:2715` — global LRU anti-repeat picker.
- `_flavor_tails_enabled` module-global at `relay_speech.py:1136`.

`AGENT_FLAVOR` in `_agent_flavor.py`: the 1,628-entry dict keyed `agent → situation → list[TailEntry]`.
`TailEntry` in `_tail_schema.py:33` — `(text, tags: frozenset[str])`.
`_tail_selector.select_tail` in `_tail_selector.py:60` — semantic MMR re-ranker, OFF by default
(`KENNING_ENABLE_TAIL_SELECTOR` not set).

**u1.0 attach (flavor injection):** when the LLM generates the relay line, agent flavor is
injected as in-context exemplars into the system prompt. The selection path is:
`_payload_flavor_facts` (relay_speech.py:3989) → look up `AGENT_FLAVOR[agent][situation]` →
`_tier_filter` (`relay_speech.py:3892`) → take top-N exemplars → inject into system prompt.
`_join_tail` at `relay_speech.py:3686` remains as the gating chokepoint: when `flavor_tails_enabled()`
is False, the LLM is instructed NOT to append a tail (prompt directive), and `_join_tail`
enforces this structurally on any deterministic fast-path still in use.

### 5. `relay_route_info` — route classification for tracing

`src/kenning/audio/relay_speech.py:5647`. Returns `{"route": ..., "reason": ..., "subtype": ...}`.
Current routes: `verbatim`, `curated_command`, `curated_reaction:*`, `roast`, `fun_fact`,
`answer:*`, `identity`, `criticize`, `directive_pool:*`, `compose_llm`, `snap`, `relay_llm`.

**u1.0 attach:** extend `relay_route_info` to emit `prompt_template_id` and `exemplar_count`
so traces capture which template fired and how many exemplars were injected.

### 6. `_RELAY_REPHRASE_SYSTEM` + `_RELAY_SAMPLING` — prompt and sampling constants

`src/kenning/audio/relay_speech.py:2526` — `_RELAY_REPHRASE_SYSTEM` (~2300 chars).
`src/kenning/audio/relay_speech.py:2507` — `_RELAY_SAMPLING` (tight `max_tokens`, stop sequences, `min_p`).
`src/kenning/audio/relay_speech.py:2538` — `_build_rephrase_prompt`.

**u1.0 attach:** `_RELAY_REPHRASE_SYSTEM` becomes the base persona prompt; exemplar injection
prepends a `## Examples` block to the user turn (or appends to the system turn after the
persona section). The `_RELAY_SAMPLING` `max_tokens` cap and stop sequences stay, since the
8B on 12GB GPU will be faster not longer. Add `prompt_template_id` field to sampling dict
for tracing (it is ignored by llama-cpp-python but captured by the trace layer).

### 7. `_command_exemplars.py` — semantic router exemplar format

`src/kenning/audio/_command_exemplars.py` — five family lists: `_TEAM_CALLOUT`, `_SPOTIFY`,
`_IDENTITY`, `_DESKTOP_REFUSE`, `_CONVERSATIONAL`. This is the EXISTING exemplar library
for coarse routing. It is embedded once at startup by `CommandRouter.__init__`.

**u1.0 attach:** the u1.0 prompt-exemplar injection is SEPARATE from these router exemplars.
Router exemplars route to a handler family; prompt exemplars are the Ultron-voice output
examples injected into the LLM system prompt for the chosen family. These do not conflict.
The `_TEAM_CALLOUT` list can be reused as negative examples (show "plain rephrase" style)
while the curated pools (`DEFAULT_CLUTCH_LINES`, etc.) are the positive exemplars for
each snap type.

### 8. `_as_compound_callout` — multi-fact callout split

`src/kenning/audio/relay_speech.py:4780` — `_as_compound_callout(command, recent_lines)`.
Split logic uses `_split_compound` (comma/and/plus/also delimiters). Returns
`(det_line, leftover)`. Partial resolution recursively calls `build_relay_line` at `relay_speech.py:6293`.

**u1.0 attach:** in the all-LLM path, compound callouts can be sent as a single prompt with
GBNF grammar for structured multi-callout output (as noted in the master map). The split
logic at line 4780 is still useful for token budget estimation and for the deterministic
fast-path when `rephrase=False`. The `sampling.grammar` kwarg is already wired through
`LLMEngine.generate_stream` (confirmed in B7 recon doc, `_chat_completion_kwargs`).

---

## Corrections to the recon/plan

### C1. `build_relay_line` step numbering is not 28 steps — the actual count varies by path

The master map says "28-step dispatch chain." The actual code has approximately 23 numbered
logical branches in `build_relay_line`, but the recon docs used their own step numbering
based on the audit that found 28 distinct code paths. This is not a functional error; just
be aware that when the plan refers to "step 27" (LLM rephrase), the code line is `relay_speech.py:6326`
(`if rephrase:` block), not a literal step-27 counter. The tactical literal pre-route
(recon "step 26") starts at `relay_speech.py:6308`. The compound callout ("step 25") starts
at `relay_speech.py:6275`. All verified correct by direct read.

### C2. `relay_route_info` does NOT check the snap registry before classifying as "snap"

The current `relay_route_info` at `relay_speech.py:5701` calls `_as_snap_callout(command, None, flavor=False)`
to decide if route is "snap" — but this misses the `SNAP_REGISTRY` check (`_apply_snap_registry`)
which fires EARLIER in `build_relay_line` (step 21 vs step 24). So "clutch" / "nice try" /
"consolation" / "praise" are currently classified as `relay_llm` by `relay_route_info` if
they do not match `_as_snap_callout`, even though `_apply_snap_registry` would catch them.
The recon docs do not flag this explicitly. For u1.0 trace fidelity, `relay_route_info` needs
to also probe `_apply_snap_registry`.

### C3. `thank-you` and `agent-select` are NOT in `SNAP_REGISTRY` — use `_pick_lru` not `pick_line`

Confirmed by direct source read: `_THANK_YOU_RE` at `voice_lines.py:265` and
`_AGENT_SELECT_FULL_RE` at `voice_lines.py:238` are in `voice_lines.py` (data side),
but their dispatch is HARDCODED in `_as_snap_callout` at `relay_speech.py:4421` and `4410`,
not in `SNAP_REGISTRY`. They use `_pick_lru(list(_THANK_YOU_TAILS))` at `relay_speech.py:4424`
(global process-wide LRU) instead of `pick_line` (recent-ring anti-repeat). The plan to
"repurpose SNAP_REGISTRY as prompt-routing rules" must account for this: migrating `thank-you`
and `agent-select` into the registry first is a prerequisite for uniform treatment.

### C4. The master map pivot table says "build_relay_line step 27 (relay_speech:6012)" — this is wrong

Line 6012 is the FUNCTION DEFINITION of `build_relay_line`, not step 27. Step 27 (LLM rephrase)
is at `relay_speech.py:6326`. This should be corrected in the pivot table in `00_codebase_map.md`.

### C5. `relay_route_info` does NOT mirror `_flavor_off_response` (step 1 of `build_relay_line`)

`_flavor_off_response` is the FIRST check in `build_relay_line` (line 6048) and returns early
for flavor-OFF. `relay_route_info` at line 5647 never checks `not flavor_tails_enabled()`.
This means traces generated when flavor is OFF will report routes like "snap" or "relay_llm"
when the actual path was `_flavor_off_response`. Not a blocker for u1.0 but a trace accuracy gap.

### C6. The addressing fusion branch (`9438fc5`) is confirmed absent from HEAD

The master map correctly states the fusion design lives on branch `9438fc5`. Direct git status
confirms the worktree HEAD is `dfadb89`, which does not contain it. The recon is correct.
The u1.0 3-way gate must recover from that branch.

---

## Risks & gotchas for the implementation

### R1. Golden digest breaks on every registry or voice-line change — mandatory re-bless step

`tests/test_voice_lines_golden.py` runs `scripts/_voice_lines_verify.py check` with
`PYTHONHASHSEED=0` and CI path `tests/data/voice_lines_golden_digest.json`. Any change to
`SNAP_REGISTRY`, `TARGET_SNAP_REGISTRY`, or any pool in `voice_lines.py` fails CI until
`PYTHONHASHSEED=0 python scripts/_voice_lines_verify.py baseline` is re-run and the JSON
committed. This will fire on every u1.0 exemplar or registry change. Plan for it as a
mechanical step in each implementation PR.

### R2. `_apply_snap_registry` imports `SNAP_REGISTRY` lazily inside the function body

`relay_speech.py:2807`: `from kenning.audio.voice_lines import SNAP_REGISTRY` inside the
function. This means the first call triggers the import; subsequent calls use the cached
module attribute. Hot-patching `SNAP_REGISTRY` in tests via `monkeypatch.setattr` on the
`voice_lines` module works (the import already happened). BUT adding a `prompt_template_id`
field to `SnapRule` requires updating the golden digest and all existing `SnapRule(...)` callsites.

### R3. Fail-open `except Exception` wrappers suppress ALL errors silently

Both `_apply_snap_registry` (line 2820) and `_render_target_registry` (line 2896) catch
`except Exception` and `logger.debug` the error. In u1.0, if the LLM call inside a
registry handler raises (OOM, timeout, context overflow), the error is swallowed and the
hardcoded fallback fires. This is the correct behavior for production, but during development
it hides bugs. Add a `KENNING_SNAP_REGISTRY_STRICT=1` mode that re-raises for dev runs.

### R4. `_join_tail` is the ONLY flavor-ON/OFF gate for tail attachment — the LLM path bypasses it

`_join_tail` at `relay_speech.py:3686` drops the tail when `_flavor_tails_enabled() == False`.
But in u1.0, if the LLM generates the relay line INCLUDING the flavor tail (because the
system prompt instructs "append one tail"), `_join_tail` never fires on LLM output. The
LLM output goes through `_strip_artifacts` + `_cap_sentences` + `_repair_against_input`,
none of which remove a tail. So for u1.0, the flavor-OFF instruction must live in the SYSTEM
PROMPT (or be enforced by a post-LLM tail-stripping pass), not rely on `_join_tail`.
Currently the relay rephrase path uses `enable_thinking=False` and does not pass flavor-state
to the LLM — this gap must be closed.

### R5. `suppress_memory_context=True` is critical and must be enforced on ALL u1.0 relay LLM calls

`relay_speech.py:6371`: `llm.generate_stream(..., suppress_memory_context=True, record_history=False)`.
Without this, `_build_messages` in `inference.py` prepends the full conversation history and
the 8B answers the CONVERSATION instead of generating a relay line. This is a live-observed
bug from the 3B (logged in MEMORY.md). Every new prompt template in u1.0 must pass both flags.
Add a `_relay_generate` helper function that enforces these flags as non-negotiable defaults
so individual callers cannot accidentally omit them.

### R6. `_output_keeps_facts` / `_repair_against_input` are post-LLM validators — do NOT remove

`relay_speech.py` (grep confirms these are present). These validators check that the LLM
preserved fact-tokens (numbers, agent names, location tokens, ability tokens) from the input
payload. In the 8B era they remain important: the 8B is more capable but can still drop a
damage number or swap an agent name when rephrasing. The validators must remain as
post-processing on ALL LLM output paths in u1.0. The `_literal_relay` fallback at
`relay_speech.py:6320` is the escape hatch when facts are dropped.

### R7. `rephrase=False` gates the ENTIRE LLM block — snap-registry LLM calls would be skipped

Currently `rephrase=False` is passed when thinking mode is OFF (the default in gaming). The
snap registry today is deterministic and unaffected by `rephrase`. In u1.0, if snap-registry
handlers call the LLM, they must NOT be gated by the `rephrase` flag — they need their own
flag (e.g. `snap_llm_enabled`). Otherwise flavor-OFF + thinking-mode-OFF leaves the registry
in deterministic-only mode, which may be desirable but must be explicit.

### R8. `_LRU_SEEN` is a process-wide global — cross-pool contamination risk in u1.0

`relay_speech.py:2712`: `_LRU_SEEN: dict[str, int] = {}`. All pools share the same LRU
counter keyed by `.lower()` tail text. If two different exemplar banks happen to share a
phrase (e.g. "Precision." appears in both `_THANK_YOU_TAILS` and a new damage exemplar pool),
picking it from one pool increments its global counter and suppresses it in the other.
For 1,628 curated tails this is unlikely but grows with the exemplar bank size. Consider
scoping LRU by `(pool_id, text)` tuples before expanding the exemplar library.

### R9. `_as_compound_callout` recursive call at `relay_speech.py:6293` is depth-bounded only by the compound split

The recursive `build_relay_line(sub, ...)` call for partial-compound leftovers (line 6293)
uses `rephrase=rephrase`. If the leftover is itself a partial compound, it re-enters
`_as_compound_callout`. In practice `_split_compound` produces at most ~5 pieces and each
piece is a single fact, so depth is bounded. But the u1.0 LLM path can extend latency
multiplicatively if each compound piece triggers a separate LLM call. For u1.0, consider
batching compound pieces into a SINGLE prompt with structured output (the GBNF grammar
path noted in the master map) rather than recursing.

### R10. `relay_route_info` omits the `TARGET_SNAP_REGISTRY` path

`relay_route_info` at `relay_speech.py:5647` does not probe `_render_target_registry`.
Commands routed via `TARGET_SNAP_REGISTRY` (hello, ask_day) will be misclassified as
`curated_command` or `identity` by the route classifier (since it probes `_as_curated_command`
first, which returns None for these, then falls through to `snap`/`relay_llm`). For u1.0
tracing, add a `target_snap` route case to `relay_route_info`.

---

## Concrete recommendation

**Step 0 (pre-requisite, no behavior change): migrate `thank-you` and `agent-select` into `SNAP_REGISTRY`.**

Before treating the registry as the universal snap-to-prompt router, move the two
hardcoded handlers from `_as_snap_callout` (lines 4410–4425) into `SNAP_REGISTRY` as
`kind="pool"` + `kind="head_tail"` entries respectively. This closes the inconsistency
(C3), makes all snap pools uniform, and removes the LRU/pick_line discrepancy. Re-bless
the golden digest. Estimated: ~30 lines changed + digest re-bless.

**Step 1: extend `SnapRule` with `prompt_template_id` + `exemplar_lines` fields.**

```python
@dataclass(frozen=True)
class SnapRule:
    name: str
    match: re.Pattern
    kind: str = "pool"
    lines: tuple = ()       # deterministic pool (fast-path + exemplar bank)
    tails: tuple = ()       # head_tail tails (exemplar bank)
    prompt_template_id: str = ""    # u1.0: which LLM prompt template to call
    max_exemplars: int = 4          # how many lines to inject as few-shot examples
```

Gate: if `prompt_template_id` is set AND LLM available AND `snap_llm_enabled()` → call
the LLM with the template + `lines[:max_exemplars]` injected as `## Examples`. Otherwise
fall through to `pick_line(lines)` (deterministic fast-path, zero latency). This gives
a clean `kind="prompt_template"` upgrade path without breaking existing `kind="pool"` rules.

**Step 2: add a `_relay_generate` helper wrapping `llm.generate_stream`.**

Enforces `suppress_memory_context=True`, `record_history=False`, `enable_thinking=False`
as non-overridable defaults for all relay-path LLM calls. Accepts `(prompt, system_prompt,
sampling, *, flavor_on=True)`. When `flavor_on=False`, appends a system-prompt directive
"Do not add a commentary tail." so the LLM does not generate one. This closes R4 (flavor-OFF
bypass) and R5 (suppress_memory_context safety).

**Step 3: inject agent context into system prompts via `_flavor_ctx` output, not raw `AGENT_FLAVOR`.**

The existing `_payload_flavor_facts` at `relay_speech.py:3989` already extracts
`{agents, loc, ability, count, payload}`. Feed this into a new `_build_exemplar_block(agents, situation, n=4)`
function that calls `_tier_filter` on `AGENT_FLAVOR[agent][situation]` and returns a
formatted `## Flavor examples for {agent}` block. Inject this block into the system prompt
in `_build_rephrase_prompt` (currently at `relay_speech.py:2538`) after the persona section.
The `_tail_selector.select_tail` MMR reranker (relay_speech.py:3769, OFF by default) can be
wired as the exemplar selector when `KENNING_ENABLE_TAIL_SELECTOR=1`.

**Step 4: fix `relay_route_info` to cover `SNAP_REGISTRY` and `TARGET_SNAP_REGISTRY`.**

Probe `_apply_snap_registry(command.payload)` before the `_as_snap_callout` probe (line 5701),
and probe `command.directive in {r.name for r in TARGET_SNAP_REGISTRY}` before `_as_curated_command`.
This closes C2, C5, R10.

**Step 5: add `KENNING_SNAP_REGISTRY_STRICT=1` dev flag** (closes R3).

When set, `_apply_snap_registry` and `_render_target_registry` re-raise instead of logging
at DEBUG. Gated on env var so production remains fail-open.

**Step 6: for compound callouts, collect per-piece LLM tokens into a SINGLE call** (closes R9).

Replace the recursive `build_relay_line(sub, ...)` path for compound leftovers with a
`_build_compound_prompt(pieces)` that batches all off-snap pieces into one LLM call using
GBNF grammar for structured output (`{"piece_1": "...", "piece_2": "..."}` → join). The
deterministic pieces still resolve immediately; only the off-snap leftovers go to the LLM
as a batch.

**Line reference summary for implementation PRs:**

| Symbol | File | Line |
|--------|------|------|
| `build_relay_line` (function entry) | relay_speech.py | 6012 |
| LLM rephrase block (`if rephrase:`) | relay_speech.py | 6326 |
| `_apply_snap_registry` | relay_speech.py | 2791 |
| `_match_target_registry` | relay_speech.py | 2842 |
| `_render_target_registry` | relay_speech.py | 2873 |
| `_as_snap_callout` | relay_speech.py | 4327 |
| `_parse_callout_slots` | relay_speech.py | 4284 |
| `_as_compound_callout` | relay_speech.py | 4780 |
| compound recursive call | relay_speech.py | 6293 |
| tactical literal pre-route | relay_speech.py | 6308 |
| `_RELAY_SAMPLING` | relay_speech.py | 2507 |
| `_RELAY_REPHRASE_SYSTEM` | relay_speech.py | 2526 |
| `_build_rephrase_prompt` | relay_speech.py | 2538 |
| `relay_route_info` | relay_speech.py | 5647 |
| `_join_tail` (flavor chokepoint) | relay_speech.py | 3686 |
| `_flavor_tails_enabled` (global) | relay_speech.py | 1136 |
| `_flavor_ctx` (flavor entry) | relay_speech.py | 3931 |
| `_payload_flavor_facts` | relay_speech.py | 3989 |
| `_pick_lru` | relay_speech.py | 2715 |
| `_as_curated_command` | relay_speech.py | 5530 |
| `_as_curated_reaction` | relay_speech.py | 5605 |
| `thank-you` hardcoded handler | relay_speech.py | 4421 |
| `agent-select` hardcoded handler | relay_speech.py | 4410 |
| `_LRU_SEEN` (global) | relay_speech.py | 2712 |
| `SnapRule` dataclass | voice_lines.py | 318 |
| `SNAP_REGISTRY` tuple | voice_lines.py | 330 |
| `TargetSnapRule` dataclass | voice_lines.py | 353 |
| `TARGET_SNAP_REGISTRY` tuple | voice_lines.py | 363 |
| `AGENT_FLAVOR` dict | _agent_flavor.py | 12 |
| `TailEntry` dataclass | _tail_schema.py | 33 |
| `select_tail` MMR reranker | _tail_selector.py | 60 |
| `KENNING_ENABLE_TAIL_SELECTOR` gate | _tail_selector.py | 78 |
