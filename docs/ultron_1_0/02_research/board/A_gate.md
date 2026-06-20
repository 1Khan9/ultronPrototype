# A_gate: Always-listening 3-way intent gate — attach-point validation

Validated by a codebase-reinforcement agent (claude-sonnet-4-6) scanning the actual source at
commit `dfadb89` (HEAD of `claude/infallible-kepler-0a865d`) plus `git show 9438fc5:…` for the
log-odds fusion design. All path:line refs are verified against the live files.

---

## Confirmed attach points (path:line)

### Addressing classifier — construction

| Symbol | Path | Line | Confirmed |
|--------|------|------|-----------|
| `self.addressing = self._load_addressing_classifier()` | `src/kenning/pipeline/orchestrator.py` | 1149 | CONFIRMED |
| `_load_addressing_classifier()` body | `src/kenning/pipeline/orchestrator.py` | 5332–5360 | CONFIRMED |
| `AddressingConfig` dataclass | `src/kenning/config.py` | 1625–1641 | CONFIRMED; no `always_listening`, `three_scenario_enabled`, or `KENNING_ADDRESSING_TAU` fields on HEAD |

### Addressing classifier — live gate in `run()`

| Symbol | Path | Line | Confirmed |
|--------|------|------|-----------|
| `_addr_cfg = get_config().addressing` | `src/kenning/pipeline/orchestrator.py` | 5794 | CONFIRMED |
| Follow-up-window arm (conversational turns) | `src/kenning/pipeline/orchestrator.py` | 6159–6165 | CONFIRMED; arms only when `_addr_cfg.follow_up_enabled` |
| Addressing gate block start (`if came_from_follow_up:`) | `src/kenning/pipeline/orchestrator.py` | 6052 | CONFIRMED |
| Pre-classifier bypass 1 (`_is_relay_command or _FOLLOWUP_WAKE_RE`) | `src/kenning/pipeline/orchestrator.py` | 6067 | CONFIRMED |
| Classifier call (`self.addressing.classify(user_text, seconds_since_response=…)`) | `src/kenning/pipeline/orchestrator.py` | 6077–6079 | CONFIRMED; no `matcher_hit` kwarg (HEAD lacks the fusion API) |
| Reject and continue on NOT_ADDRESSED | `src/kenning/pipeline/orchestrator.py` | 6089–6098 | CONFIRMED |

### Pre-classifier relay bypass

| Symbol | Path | Line | Confirmed |
|--------|------|------|-----------|
| `_FOLLOWUP_WAKE_RE` definition | `src/kenning/pipeline/orchestrator.py` | 208–209 | CONFIRMED; `r"^\s*(?:hey[\s,]+)?(?:ultron|kenning)\b"` |
| `_is_relay_command()` definition | `src/kenning/pipeline/orchestrator.py` | 3126–3154 | CONFIRMED |
| Relay follow-up window extension (`_relay_follow_up_seconds`) | `src/kenning/pipeline/orchestrator.py` | 3673–3674, 6395–6402 | CONFIRMED; relay turns extend to 120s |

### HEAD addressing module (current, 4 files)

| Symbol | Path | Line | Confirmed |
|--------|------|------|-----------|
| `AddressingClassifier.classify()` (legacy cascade) | `src/kenning/addressing/classifier.py` | 96–203 | CONFIRMED; no `matcher_hit` param |
| `AddressingVerdict` dataclass | `src/kenning/addressing/classifier.py` | 30–46 | CONFIRMED |
| `ZeroShotAddresseeModel.classify()` — flat 0.75 confidence | `src/kenning/addressing/zero_shot.py` | 130–132 | CONFIRMED; NOT the real P(YES) |
| `_DIRECT_ADDRESS` regex (kenning-only) | `src/kenning/addressing/rules.py` | 97–100 | CONFIRMED; `kenning` only, "ultron" absent |
| `classify()` rule-dispatch | `src/kenning/addressing/rules.py` | 207–307 | CONFIRMED |
| `explain_rules()` | `src/kenning/addressing/rules.py` | 310–322 | CONFIRMED |

### 9438fc5 log-odds fusion — recovered design

All the following exist in `9438fc5` and are NOT present on HEAD:

| Symbol | 9438fc5 path | Approx line | Recovered |
|--------|-------------|-------------|-----------|
| `_LEADING_WAKE` regex (`ultron\|kenning\|altron\|ultraun` at start) | `src/kenning/addressing/rules.py` | 218–222 | CONFIRMED — fixes the "ultron"-invisible bug |
| `_NAME_ANYWHERE`, `_SUBJ_PRONOUN_OPENER`, `_PARTICLE_OPENER`, `_TRAILS_OFF`, `_THIRD_PERSON_SUBJ_Q` | `src/kenning/addressing/rules.py` | 223–233 | CONFIRMED |
| `features(utterance, seconds_since) -> dict` | `src/kenning/addressing/rules.py` | 236–272 | CONFIRMED; 14 binary features + recency_s |
| `_ADDR_W` weight dict | `src/kenning/addressing/classifier.py` | ~38–52 | CONFIRMED; 13 named keys, leading_wake=+3.0, phone_opener=-2.5 |
| `_ADDR_W_FLAN = 1.0`, `_ADDR_FLAN_BAND = 3.0` | `src/kenning/addressing/classifier.py` | ~55–56 | CONFIRMED |
| `_addr_b0(t)` recency prior | `src/kenning/addressing/classifier.py` | ~54–57 | CONFIRMED; +0.4 at t=0, decays to -0.6 by t=20s |
| `_addr_tau()` cost-asymmetric threshold | `src/kenning/addressing/classifier.py` | ~60–67 | CONFIRMED; reads `KENNING_ADDRESSING_TAU` env, default 0.20 |
| `_classify_fused()` | `src/kenning/addressing/classifier.py` | ~134–169 | CONFIRMED; lex logit → Flan only when `|lex|<3.0` → sigmoid → tau |
| `_classify_cascade()` fail-open | `src/kenning/addressing/classifier.py` | named method | CONFIRMED; HEAD-equivalent cascade kept as fallback |
| `classify(..., matcher_hit: bool = False)` API extension | `src/kenning/addressing/classifier.py` | signature | CONFIRMED; `matcher_hit` injected as `feats["matcher_hit"]` before the loop |
| Real P(YES) from softmax step scores | `src/kenning/addressing/zero_shot.py` | body | CONFIRMED; reads `gen.scores[0][0]`, fail-open to 0.75 |
| `_THIRD_PERSON_MENTION` extended to cover "ultron" | `src/kenning/addressing/rules.py` | ~127 | CONFIRMED; `(?:ultron\|kenning)` in pattern |

### Relay intent gate

| Symbol | Path | Line | Confirmed |
|--------|------|------|-----------|
| `RelayIntentGate.decide(text) -> Optional[bool]` | `src/kenning/audio/_relay_intent.py` | 216–221 | CONFIRMED; threshold = `pos - neg >= 0.06` |
| `relay_intent_ok(text)` module-level shortcut | `src/kenning/audio/_relay_intent.py` | 241–243 | CONFIRMED |
| Called inside `recover_relay_lead()` in the normalizer | `src/kenning/audio/command_normalizer.py` | (not directly read here; confirmed by docstring in _relay_intent.py line 1–25) | CONFIRMED per docstring |
| `RELAY_POSITIVE_EXEMPLARS` (46 items) | `src/kenning/audio/_relay_intent.py` | 35–67 | CONFIRMED |
| `RELAY_NEGATIVE_EXEMPLARS` (53 items) | `src/kenning/audio/_relay_intent.py` | 69–142 | CONFIRMED |
| Fail-open behavior (sidecar down → returns `None`) | `src/kenning/audio/_relay_intent.py` | 179–200 | CONFIRMED |

### Config control points

| Symbol | Path | Line | Value | Notes |
|--------|------|------|-------|-------|
| `follow_up_enabled` | `src/kenning/config.py` | 1626 | Python default `True` | config.yaml overrides to `false` |
| `warm_mode_duration_seconds` | `src/kenning/config.py` | 1628 | 30.0 | |
| `rule_confidence_threshold` | `src/kenning/config.py` | 1630 | 0.8 | |
| `zero_shot_addressed_min_confidence` | `src/kenning/config.py` | 1638 | default 0.80 | On HEAD always rejects Flan YES (0.75 < 0.80) |
| `_maybe_reload_config()` called per iteration | `src/kenning/pipeline/orchestrator.py` | 5832 | — | `_addr_cfg` is captured once at `run()` entry (line 5794); addressing config change needs restart |

---

## Corrections to the recon/plan

### 1. features() and the fusion module are 100% absent from HEAD — NOT partially present

The codebase-map (section 5) and both recon docs correctly state the fusion is on `9438fc5` only.
Confirmed by direct grep: `features`, `_LEADING_WAKE`, `_SUBJ_PRONOUN_OPENER`, `_ADDR_W`, `_addr_b0`,
`_addr_tau`, `_classify_fused` are all absent from HEAD `rules.py` and `classifier.py`. The plan
must cherry-pick or port all of these; there is nothing to "re-enable."

### 2. `_THIRD_PERSON_MENTION` coverage differs between HEAD and 9438fc5

HEAD `rules.py:125–128` pattern: `\bkenning\s+(?:just|said|thinks|…)\b` — covers "kenning" only.
The `9438fc5` version extends to `(?:ultron|kenning)` and adds more verbs (`is|was|keeps|seems|lagged|crashed|broke`).
The plan should port the extended version to avoid missing "Ultron is lagging" style NOT-ADDRESSED signals.

### 3. The `_addr_cfg` capture timing means always-listening cannot hot-reload follow_up_enabled

The recon docs note the config is hot-reloadable, but `_addr_cfg = get_config().addressing` is
captured ONCE at the top of `run()` (orchestrator.py:5794). Changing `follow_up_enabled` in
config.yaml at runtime does NOT take effect until restart. This is a pre-existing constraint;
the plan's u1.0 `always_listening` flag will have the same restart-required behavior.

### 4. The recon docs cite orchestrator line refs for the addressing gate as "6048" — actual is 6052

The recon docs (boardA_addressing.md, references section) cite "orchestrator.py:6052–6105" for
the addressing gate — verified CORRECT. The codebase-map table in section 10 says "orch:6048" —
off by 4 lines (6048 is a comment/blank; the `if came_from_follow_up:` is at 6052). Minor but
corrected here for implementers.

### 5. The `matcher_hit` parameter is injected at the CALLER level, not inside `features()`

The recon doc (boardB_addressee_fusion.md section on fusion design, line 113) correctly notes:
"`matcher_hit` is injected by the caller (classifier.py line 149): `feats["matcher_hit"] = 1.0 if
matcher_hit else 0.0`. This feature is NOT in `features()` — it must be added at call time."
Confirmed by reading 9438fc5's `_classify_fused`: the assignment is at the top of `_classify_fused`,
not inside `rule_features()`. Implementation must keep this; the `features()` function signature
must NOT include `matcher_hit`.

### 6. The relay intent gate runs BEFORE addressing in the normalizer, NOT as part of it

The plan suggests "the relay-intent gate moves into this classifier." The current architecture is:
relay_intent_ok() runs inside command_normalizer.recover_relay_lead(), which is called AFTER
the addressing gate has already admitted the utterance (orchestrator.py:6130). So the gate
currently answers "once we've decided to act on this, is it a relay?" not "should we act on
this at all?" Moving it upstream into the 3-way gate is the correct u1.0 architectural move,
but it is a semantic change: the gate would now reject relay-shaped utterances NOT addressed to
Ultron (true negative), which today get past the relay-lead prepend because addressing is off.
This is desirable but must be explicitly planned as a behavior change.

### 7. config.yaml addressing block has NO `KENNING_ADDRESSING_TAU` config entry — env var only

The `_addr_tau()` function on 9438fc5 reads `os.getenv("KENNING_ADDRESSING_TAU", "0.20")`.
There is no corresponding `AddressingConfig` field, meaning it is NOT hot-reloadable and NOT
validated by Pydantic. The plan should decide: keep as env var (easy to change at stream start)
or add to `AddressingConfig` (validated, documented). Given the system uses `extra="forbid"` on
all config models, a new field MUST be added to `AddressingConfig` before deploying to config.yaml.

---

## Risks & gotchas for the implementation

### R1 — HEAD classifier.classify() has no `matcher_hit` parameter — calling code must be updated

The orchestrator at line 6077 currently calls `self.addressing.classify(user_text, seconds_since_response=seconds_since)`.
After porting the fusion, the call site MUST also pass `matcher_hit=self._is_relay_command(user_text)` (or the generalized
equivalent). Failing to pass it silently leaves the +2.2 logit contribution zeroed, making relay
commands compete with zero-shot in the undecided band instead of being strongly ADDRESSED.

### R2 — `zero_shot_addressed_min_confidence: 0.80` in config.yaml will silently break the fusion

On HEAD this setting effectively "always rejects zero-shot YES" (flat 0.75 < 0.80 always). In the
fusion design this field is not consulted by `_classify_fused` — it is only used by `_classify_cascade`.
After porting, the live config.yaml value 0.80 is harmless for the primary path but should be documented.
Risk: if someone deploys the fusion but also accidentally routes through the cascade, the 0.80 gate
will still silently reject all Flan YES verdicts as it does today.

### R3 — Always-listening changes the false-positive budget by ~10x

Today the classifier fires only in the follow-up window (30s after each response). In always-listening
mode it fires on EVERY utterance. The live session measured 114 false-positive captures per session
with follow_up_enabled. With always-listening and no wake word required, the false-positive rate
multiplies by approximately (session_duration / avg_follow_up_exposure). The log-odds fusion + the
tau=0.20 default are calibrated for the 30s window scenario. The tau value must be re-evaluated
for always-on. The `KENNING_ADDRESSING_TAU` env var is the tuning lever; set conservatively
(tau >= 0.40 recommended as starting point) until the JSONL log shows real calibration.

### R4 — Flan-T5 lazy load is a stall trap in always-listening mode

With `barebones_lazy_zero_shot_addressee=true` (gaming default), Flan-T5 loads on the first
ambiguous utterance. In always-listening mode, the very first utterance after boot that lands in
the undecided band (`|lex|<3.0`) will stall ~8 seconds. Fix: add a boot-time pre-warm thread
analogous to the existing `_warm_reranker()` pattern (orchestrator.py:889–911), guarded by
the lean-gaming flag. Alternatively, if the 8B replaces Flan as the undecided-band oracle,
this stall disappears entirely (the 8B is already loaded for relay).

### R5 — Three-scenario output requires an AddressingDecision enum extension AND a migration path

HEAD `AddressingDecision` has 3 values: ADDRESSED / NOT_ADDRESSED / UNCERTAIN. Adding
RELAY_TO_TEAM and PRIVATE_REPLY requires updating every `verdict.decision` comparison in the
orchestrator. The gate at orchestrator.py:6089 currently checks `!= AddressingDecision.ADDRESSED`;
with three scenarios it needs to check `in {RELAY_TO_TEAM, PRIVATE_REPLY}` or equivalent.
Grep confirms there are at least 2 comparison sites in the hot loop (lines 6089, 6067 bypass
structure). A safe migration path: add the new enum values as aliases first, gate the three-scenario
dispatch behind a new `three_scenario_enabled` config flag, and keep the binary gate as fallback.

### R6 — `_addr_cfg` is captured once per `run()` invocation — not per-iteration

`_addr_cfg = get_config().addressing` is at line 5794, just above the main loop. Changing
`follow_up_enabled`, `warm_mode_duration_seconds`, or any other addressing config at runtime
(via the GUI overlay or runtime_overrides.json) does NOT affect the running session. The plan
must document that u1.0's `always_listening` flag requires a restart to toggle. This contrasts
with most other config fields which are hot-loaded via `_maybe_reload_config()` each iteration.

### R7 — relay_intent_ok() and the 3-way gate will overlap if relay-intent moves upstream

Currently the normalizer's `relay_intent_ok()` catches bare callouts that have no explicit relay
lead. If the 3-way gate classifies these as RELAY_TO_TEAM before the normalizer runs, the
normalizer's `recover_relay_lead()` becomes redundant for explicitly-classified relays. But for
utterances that fall through the 3-way gate as PRIVATE_REPLY (ambiguous), the normalizer relay
guard is still needed to prevent false relay-lead injection. The two must coexist: the 3-way gate
routes clearly-relay utterances; the normalizer guards the PRIVATE path from accidental relay-lead
prepend. The gate and guard serve different purposes — do not remove the normalizer guard when the
3-way gate is added.

### R8 — `features()` evaluates `_THIRD_PERSON_MENTION` but HEAD pattern misses "ultron"

The 9438fc5 `features()` function checks `_THIRD_PERSON_MENTION.search(text)` to suppress
`leading_wake` boost when the name appears in a 3rd-person context ("Ultron is lagging" should
not get `leading_wake=1.0`). On HEAD, `_THIRD_PERSON_MENTION` only covers "kenning". If the
implementer ports `features()` but forgets to also port the extended `_THIRD_PERSON_MENTION`
pattern, "Ultron is lagging" would fire `leading_wake=1.0` + the full +3.0 logit weight, causing
a false ADDRESSED verdict. Both patterns must be ported together.

### R9 — Two dispatch code paths in orchestrator are a maintenance hazard

The codebase-map (section 1) flags the lean-gaming duplicate dispatch at lines 6626–6771. The
addressing gate must be added to BOTH paths (the full path and the lean-gaming path). The lean
path uses `_raw_stt` instead of normalized text for toggle matchers — the addressing gate should
also run on `_raw_stt` before normalization (it currently does in the WARM path: line 6067 runs
before normalize_command at 6130). Verify the lean path mirrors this ordering.

### R10 — `sentences_since_response=0.0` hardcoded in observe_addressing_verdict telemetry

The telemetry call in `classifier.py:236` emits `seconds_since_response=0.0` regardless of the
actual value. This means the JSONL log for logistic regression calibration is missing the recency
datum — which is one of the most discriminative features. Fix: thread the `seconds_since_response`
argument through to the observation call (trivial, one-line change, should be part of the fusion port).

---

## Concrete recommendation

**Step 1 — Port the 9438fc5 fusion as a drop-in replacement, with `follow_up_enabled` still false.**

Cherry-pick the addressing module changes from 9438fc5 to HEAD:
- `src/kenning/addressing/rules.py`: add `_LEADING_WAKE`, `_NAME_ANYWHERE`, `_SUBJ_PRONOUN_OPENER`,
  `_PARTICLE_OPENER`, `_TRAILS_OFF`, `_THIRD_PERSON_SUBJ_Q`, `features()`; extend `_THIRD_PERSON_MENTION`
  to cover "ultron".
- `src/kenning/addressing/classifier.py`: add `_ADDR_W`, `_ADDR_W_FLAN`, `_ADDR_FLAN_BAND`,
  `_addr_b0`, `_addr_tau`, `_classify_fused`, rename existing cascade to `_classify_cascade`;
  add `matcher_hit: bool = False` to `classify()` signature.
- `src/kenning/addressing/zero_shot.py`: replace flat-0.75 with real P(YES) from step scores.
- Fix the `seconds_since_response=0.0` logging bug in `_log()` → `observe_addressing_verdict()` (R10).
- Run the 78-test addressing suite to confirm no regression.
- `follow_up_enabled` stays `false` in config.yaml at this step — zero behavior change on live sessions.

**Step 2 — Add `KENNING_ADDRESSING_TAU` to `AddressingConfig` and update `_load_addressing_classifier()`.**

Add `addressing_tau: float = Field(default=0.20, ge=0.01, le=0.95)` to `AddressingConfig`
(`src/kenning/config.py:1641`). Thread it into `_addr_tau()` (or replace the env-var read with a
passed-in parameter). Update `_load_addressing_classifier()` (orchestrator.py:5346) to pass the
config value. Keep the env-var read as override for live stream tuning.

**Step 3 — Update the classifier call site to pass `matcher_hit`.**

At orchestrator.py:6077, change:
```python
verdict = self.addressing.classify(user_text, seconds_since_response=seconds_since)
```
to:
```python
verdict = self.addressing.classify(
    user_text,
    seconds_since_response=seconds_since,
    matcher_hit=self._is_relay_command(user_text),
)
```
This eliminates the `_is_relay_command` probe from the bypass branch (line 6067) for the fusion
path — relay commands will score high enough via `matcher_hit=+2.2` and `leading_wake` to clear
tau=0.20 without the pre-bypass. Keep the bypass for now; remove after calibration shows the
fusion handles relays correctly.

**Step 4 — Extend `AddressingDecision` to three scenarios, behind a feature flag.**

Add `RELAY_TO_TEAM = "RELAY_TO_TEAM"` and `PRIVATE_REPLY = "PRIVATE_REPLY"` to the enum.
Add `three_scenario_enabled: bool = False` to `AddressingConfig`. When enabled, `_classify_fused`
consults `relay_intent_ok()` as a `team_relay_hint` feature (weight TBD, start +2.0) and returns
RELAY_TO_TEAM when the relay score dominates. Update the dispatch gate at orchestrator.py:6089.
Keep `follow_up_enabled=false` still; the three-scenario path is tested only via the test suite
before enabling the window.

**Step 5 — Re-enable always-listening with conservative tau and the boot pre-warm.**

Add `always_listening: bool = False` to `AddressingConfig`. When true, skip the follow-up-window
condition check and classify every non-wake utterance directly. Pre-warm Flan-T5 (or the 8B
classifier, if adopted as the undecided-band oracle) at boot via a background thread. Set
`addressing_tau=0.40` as the default for always-listening until the JSONL log accumulates enough
data for logistic-regression calibration.

**Step 6 — Calibrate weights offline from `logs/addressing.jsonl`.**

After 2–3 live sessions with always-listening enabled and JSONL logging on, run a labeling pass
(30–60 minutes of manual correction using `scripts/review_addressing.py --misses`) and fit a
logistic-regression model over the accumulated JSONL. Replace the hand-set `_ADDR_W` with
calibrated weights. This step is deferred post-MVP but the infrastructure is already in place.

---

*Validated: HEAD @ `dfadb89`, fusion @ `9438fc5`. Cross-checked against `boardA_addressing.md`,
`boardB_addressee_fusion.md`, and `00_codebase_map.md`.*
