# A6: Addressing classifier (is this speech for Ultron?)

## Overview

The addressing classifier answers one question: given a VAD-bounded utterance in the follow-up
window (WARM mode), is it directed at Kenning/Ultron, or is it room chatter, inter-human speech,
or a third-party mention?

**Current status on HEAD (main, `c32d640`):**

The classifier exists and is fully wired into the orchestrator, but **the follow-up window is
disabled** (`addressing.follow_up_enabled: false`, committed in `ad186cf` 2026-06-18). Every
turn must therefore be initiated with a wake word. The classifier code is intact; it simply never
runs in the default live configuration.

Two implementations exist at different commit-points:

1. **HEAD (current):** Legacy two-layer cascade — rules first, if no rule fires above threshold
   then Flan-T5-small zero-shot. All in `src/kenning/addressing/` (4 files).

2. **`9438fc5` (developed 2026-06-18, not on current HEAD):** Full log-odds fusion — a graded
   feature extractor (`rules.features()`), lexical log-odds sum, recency prior, Flan consulted
   only in the undecided band, cost-asymmetric tau threshold. This was the intended v1 design but
   was rolled back when the follow-up window itself was disabled (false-positives from room
   chatter; the classifier was only one of two problems).

This document maps the HEAD state as the live substrate, with the fusion design called out
explicitly as the intended architecture for u1.0.

---

## Files & key symbols

### `src/kenning/addressing/__init__.py` (lines 1–26)

| Symbol | Type | Description |
|--------|------|-------------|
| `AddressingClassifier` | class (re-export) | Top-level entrypoint |
| `AddressingDecision` | enum (re-export) | ADDRESSED / NOT_ADDRESSED / UNCERTAIN |
| `AddressingVerdict` | dataclass (re-export) | Decision output including confidence, source, reason |

Module docstring (line 1–14) describes the two-layer hybrid design: rule-based first pass, zero-shot
fallback. The COLD/WARM mode framing is established here.

---

### `src/kenning/addressing/rules.py` (lines 1–322)

The rule-based first pass. All patterns are evaluated on CPU in microseconds.

**Pattern definitions:**

| Regex / Set | Lines | Decision signal | Confidence |
|-------------|-------|-----------------|------------|
| `_FACTUAL_QUESTION_STEMS` | 42–53 | ADDRESSED | 0.85 (or 0.55 if fragment) |
| `_SECOND_PERSON_QUESTIONS` | 60–74 | UNCERTAIN | 0.55 (deliberately ambiguous) |
| `_IMPERATIVE_VERBS` | 78–92 | ADDRESSED | 0.88 |
| `_DIRECT_ADDRESS` | 97–100 | ADDRESSED | 0.95 — keyed to "kenning" ONLY (NOT "ultron") |
| `_CONTINUATION_TOKENS` | 105–114 | ADDRESSED | 0.78 + 0.05 recency bias if < 5s |
| `_THIRD_PERSON_MENTION` | 125–128 | NOT_ADDRESSED | 0.85 |
| `_THIRD_PARTY_NARRATIVE` | 140–164 | NOT_ADDRESSED | 0.85 |
| `_THIRD_PARTY_POSSESSIVE_QUESTION` | 175–179 | NOT_ADDRESSED | 0.85 |
| `_PHONE_OPENERS` | 183–192 | NOT_ADDRESSED | 0.92 |
| `_INTERJECTIONS` | 195–204 | NOT_ADDRESSED | 0.85 |

**`classify()` function (lines 207–307):**
- Signature: `classify(utterance: str, seconds_since_response: float = 0.0) -> Optional[RuleHit]`
- Returns `None` when no rule fires with confidence >= 0.5 (caller falls through to zero-shot)
- Priority order: NO rules fire before YES rules (lines 228–252)
- Fragment guard for factual question stems: < 4 words, trails with conjunction, or third-person
  subject demotes to UNCERTAIN 0.55 (lines 274–291)
- Continuation bias: +0.05 when `seconds_since_response < 5.0` (lines 301–305)

**`explain_rules()` function (lines 310–322):** introspection for review tool

**CRITICAL GOTCHA — `_DIRECT_ADDRESS` is kenning-only (line 97–100):**
```python
_DIRECT_ADDRESS = re.compile(
    r"^\s*(?:hey\s+|okay\s+|alright\s+)?kenning\b[\s,.\-:]+",
    re.IGNORECASE,
)
```
The pattern matches "kenning" but NOT "ultron". This is the root cause of the live bug reported in
MEMORY: "Ultron, show me the stop button" scored 0.75 < 0.80 and was dropped, because the name
"ultron" was invisible to both `_DIRECT_ADDRESS` and the Flan model's YES/NO heuristic. The
`_FOLLOWUP_WAKE_RE` bypass in orchestrator.py was the workaround.

---

### `src/kenning/addressing/zero_shot.py` (lines 1–133)

**`ZeroShotAddresseeModel` class (line 50):**

- Model: `google/flan-t5-small` (default), ~300 MB CPU RAM, loaded lazily on first call
- Load time: ~8s on prototype hardware; warmup forward at load time eliminates JIT overhead
- `_ensure_loaded()` (line 58): lazy loader, checks `self._model is not None`
- Device: always CPU (`self._model.to("cpu")`, line 71); no VRAM used
- Prompt template (lines 23–33): asks YES/NO/UNCLEAR with context block + `seconds_since` + utterance
- Context: up to last 4 conversation turns via `_format_context()` (lines 36–47), capped at 200
  chars each
- Inference: `max_new_tokens=4, do_sample=False, num_beams=1` (lines 115–116); greedy decoding
- Latency: 78–94 ms median per docstring; budgeted < 100 ms

**`classify()` method (lines 88–132):**
- Returns `(verdict: str, confidence: float, latency_ms: float)`
- verdict is first word of output, must be in {"YES", "NO", "UNCLEAR"}
- Confidence: heuristic — YES/NO = 0.75, UNCLEAR = 0.50, unexpected token = 0.40 (lines 130–132)
- NOTE: The memory says "zero_shot.py flat-0.75 constant → REAL first-token P(YES)" was fixed in
  `9438fc5`. On current HEAD the 0.75 heuristic is still present (NOT the real first-token probability).

---

### `src/kenning/addressing/classifier.py` (lines 1–273)

**`AddressingVerdict` dataclass (lines 30–46):**

| Field | Type | Notes |
|-------|------|-------|
| `decision` | AddressingDecision | ADDRESSED / NOT_ADDRESSED / UNCERTAIN |
| `confidence` | float | 0–1 |
| `source` | str | "rule" / "zero_shot" / "default_silent" |
| `reason` | str | Human-readable explanation |
| `latency_ms` | float | Wall-clock ms for the whole classify() call |
| `rule_hit` | Optional[str] | The rule that fired, if any |
| `zero_shot_raw` | Optional[str] | Raw "YES"/"NO"/"UNCLEAR" from Flan |

**`AddressingClassifier` class (lines 48–273):**

Constructor parameters (lines 66–75):
| Param | Default | Notes |
|-------|---------|-------|
| `rule_confidence_threshold` | 0.8 | Rule must exceed this to short-circuit zero-shot |
| `default_silent_on_uncertain` | True | UNCERTAIN maps to NOT_ADDRESSED |
| `log_path` | None | JSONL decision log path |
| `zero_shot_model_name` | "google/flan-t5-small" | HF model id |
| `load_zero_shot_eagerly` | False | Warmup at construction vs first ambiguous utterance |
| `recent_turns_provider` | None | Callable returning [(role, content)] for context |
| `zero_shot_addressed_min_confidence` | 0.0 | Gate: low-confidence YES downgraded |

**`classify()` method (lines 96–203):**

Flow:
1. Call `classify_by_rules(utterance, seconds_since_response)` → `rule_hit`
2. If `rule_hit.confidence >= self.rule_threshold` (0.8) → return verdict immediately (source="rule")
3. Otherwise: call `recent_turns_provider(4)` for conversation context
4. Call `self._zero_shot.classify(utterance, context, seconds_since_response)` → `(raw_verdict, zs_conf, zs_ms)`
5. On zero-shot exception: return NOT_ADDRESSED (if `default_silent`) or UNCERTAIN; log error
6. Apply `zero_shot_addressed_min_confidence` gate: if YES but `zs_conf < min_confidence`, downgrade
   to NOT_ADDRESSED or UNCERTAIN (lines 166–177)
7. If rule had a soft hint (>0.5) that agrees with zero-shot, take `max(zs_conf, rule_hit.confidence)`
   (lines 181–186); otherwise trust zero-shot
8. Return `AddressingVerdict` with source="zero_shot"

**`should_respond()` convenience wrapper (lines 205–211):**
Returns `bool` — True iff decision == ADDRESSED. Matches orchestrator's old call signature.

**`_log()` method (lines 215–252):**
- Logs to `logger.info` (always)
- Calls `observe_addressing_verdict()` (fail-open) via kenning.observations
- Appends to JSONL file if `self.log_path` is set (thread-safe via `_log_lock`)

---

## Control/data flow

### COLD mode (current default — `follow_up_enabled: false`)

```
wake word detected
  -> _capture_utterance()
  -> STT transcription -> user_text
  -> (addressing classifier NOT called)
  -> _is_relay_command() check or routing
```

The classifier is NEVER called in COLD mode. Every turn must begin with the wake word. The
`came_from_follow_up` flag is always False.

### WARM mode (when `follow_up_enabled: true`)

```
any turn completes (spoken or dispatched)
  -> follow_up_until = time.monotonic() + warm_mode_duration_seconds (30s)

main loop:
  if follow_up_until is not None and follow_up_enabled and time.monotonic() < follow_up_until:
    -> _follow_up_listen(deadline=follow_up_until)
      -> VAD-bounded audio capture (no wake word requirement)
      -> STT transcription -> user_text
      -> came_from_follow_up = True

  if came_from_follow_up:
    # TWO bypasses BEFORE the classifier:
    if _is_relay_command(user_text) OR _FOLLOWUP_WAKE_RE.match(user_text):
      -> route directly (no classifier)
    else:
      seconds_since = time.monotonic() - _last_response_finished_monotonic
      verdict = self.addressing.classify(user_text, seconds_since_response=seconds_since)
      if verdict.decision != ADDRESSED:
        -> continue (discard, keep follow-up window alive)
      -> proceed to routing
```

**Two pre-classifier bypasses (orchestrator.py lines 6067):**

1. `_is_relay_command(user_text)`: strict relay matcher ("tell my team X" etc.) — definitionally
   addressed; skips ~190ms classifier latency
2. `_FOLLOWUP_WAKE_RE.match(user_text)`: `^\s*(?:hey[\s,]+)?(?:ultron|kenning)\b` — explicit wake
   word in follow-up window; workaround for `_DIRECT_ADDRESS` being kenning-only

The follow-up window deadline is NOT reset on rejected utterances (orchestrator.py line 6049–6050
comments) — window runs from last response time, not from last detected sound.

### Orchestrator construction

`_load_addressing_classifier()` (orchestrator.py lines 5332–5360):
- Creates a closure `recent_turns_provider` that reads `self.memory.recent(n)` (safe if memory=None)
- Reads `addr_cfg = get_config().addressing`
- Applies lean-gaming skip: `barebones_lazy_zero_shot_addressee` flag defers Flan-T5 load
  even when `load_eagerly=True`
- `self.addressing` is always constructed (line 1149); only the eager Flan load is deferred in lean gaming

---

## Key findings

1. **Classifier is disabled de facto.** `follow_up_enabled: false` in config.yaml means the
   classifier code is dead code at runtime. For u1.0 always-listening, this is the first thing to
   re-enable.

2. **Two implementations exist at different commits.** HEAD has the legacy two-layer cascade
   (rules → Flan-T5). Commit `9438fc5` has the superior log-odds fusion design (graded features +
   recency prior + flan in undecided-band only + cost-asymmetric tau). The fusion was never rolled
   back from HEAD — the FOLLOW-UP WINDOW was disabled instead. For u1.0 the fusion design should
   be the base.

3. **`_DIRECT_ADDRESS` is "kenning"-only.** The most important YES rule (direct vocative address)
   does not recognize "Ultron" as the wake word. This is a latent correctness bug that the
   `_FOLLOWUP_WAKE_RE` bypass in orchestrator.py papers over. For u1.0 it must be fixed in the
   rule itself.

4. **Zero-shot confidence is heuristic 0.75/0.50, not real P(YES).** The current HEAD zero_shot.py
   returns flat 0.75 for YES/NO; the fusion commit `9438fc5` replaced this with the real first-token
   probability. For u1.0 always-listening with a stronger model (8B LLM), the heuristic is
   unsuitable.

5. **No three-scenario discrimination.** The classifier returns ADDRESSED / NOT_ADDRESSED / UNCERTAIN.
   It has NO concept of (A) talking-to-team, (B) talking-out-loud-to-stream, (C) talking-to-Ultron.
   This is the most significant architectural gap for u1.0's "distinguish relay vs me-only vs
   others" requirement.

6. **The follow-up window is the only place the classifier fires.** Wake-word-gated turns (COLD
   mode, the current default) bypass the classifier entirely. In u1.0 always-listening mode, EVERY
   utterance would need to be classified, making the classifier the hot path.

7. **Relay commands bypass the classifier.** `_is_relay_command()` short-circuits addressing with
   a "definitionally addressed" assumption. For u1.0, this is a relay-intent detection upstream of
   the addressing gate — effectively already implementing one branch of the three-scenario split.

8. **Flan-T5-small is the only NLU model.** The zero-shot model (300 MB, 78–94 ms per call) is
   CPU-only, loaded lazily. For u1.0 with an always-on 8B LLM, the addressing question can be
   answered by the LLM itself (or a much lighter classifier) with real calibrated probabilities.

9. **JSONL audit log at `logs/addressing.jsonl`.** Every verdict is logged with utterance, decision,
   confidence, source, reason, latency. This is the training data for offline logistic-regression
   calibration mentioned in the `9438fc5` commit as a deferred step.

10. **`observe_addressing_verdict()` wires into the observations system** (fail-open). Cross-cutting
    telemetry is already in place for measuring real-world performance.

---

## Flags & config

All under `addressing:` in `config.yaml` (lines 885–907) and `AddressingConfig` in
`src/kenning/config.py` (lines 1625–1641).

| Key | Python default | config.yaml value | Effect |
|-----|---------------|-------------------|--------|
| `follow_up_enabled` | `True` | **`false`** | Master switch. False = wake-word-only, classifier never runs |
| `warm_mode_duration_seconds` | 30.0 | 30.0 | Follow-up window length after a response |
| `default_uncertain_to_not_addressed` | `True` | `true` | UNCERTAIN maps to NOT_ADDRESSED |
| `rule_confidence_threshold` | 0.8 | 0.8 | Rule must exceed this to short-circuit zero-shot |
| `zero_shot_addressed_min_confidence` | 0.80 | 0.80 | Low-confidence YES downgraded; 0.0 disables |
| `zero_shot_model` | "google/flan-t5-small" | "google/flan-t5-small" | HF model id for zero-shot |
| `load_eagerly` | `True` | `true` | Load Flan-T5 at boot vs first ambiguous utterance |
| `log_path` | "logs/addressing.jsonl" | "logs/addressing.jsonl" | JSONL decision log |

**Environment variables (from `9438fc5` fusion design — NOT present on HEAD):**
| Env var | Default | Effect |
|---------|---------|--------|
| `KENNING_ADDRESSING_TAU` | 0.20 | Cost-asymmetric ADDRESSED threshold in fusion; raise on stream to be conservative |

**Lean gaming feature flag:**
| config.yaml key | Default | Effect |
|----------------|---------|--------|
| `features.barebones_lazy_zero_shot_addressee` | `true` | Forces lazy load of Flan-T5 even when `load_eagerly=true`; saves 8s + 300 MB at gaming boot |

**Note on Python default vs config.yaml value mismatch:**
`AddressingConfig.follow_up_enabled` defaults to `True` in Python (config.py:1626), but the live
config.yaml overrides it to `false`. This was the deliberate choice in `ad186cf` to disable false
positives — the code default was left optimistic for future re-enabling.

---

## Extension points

1. **`rules.py` — add rules:** New patterns can be added as regex/set constants and evaluated in
   `classify()`. The rule-hit priority order (NO before YES) is enforced manually; new rules must be
   inserted in the right place. The `explain_rules()` function should be updated correspondingly.

2. **`rules.py:features()` (from `9438fc5`):** The graded feature dict is the natural extension
   point for new lexical signals. Adding a key here + a weight in `_ADDR_W` immediately incorporates
   it into the log-odds fusion without any other code changes.

3. **`zero_shot.py:ZeroShotAddresseeModel`:** The model name is configurable. The prompt template
   (`_PROMPT_TEMPLATE`) is the natural extension point for adding context signals, persona
   information, or the three-scenario framing.

4. **`AddressingClassifier.__init__` — `recent_turns_provider`:** The conversation context injection
   point. For u1.0, this can pass structured turn history including relay-intent metadata.

5. **`_is_relay_command()` in orchestrator.py (line 3126):** Already the extension point for
   pre-addressing relay detection. Adding new command matchers here bypasses the classifier.

6. **`_FOLLOWUP_WAKE_RE` in orchestrator.py (line 208):** Narrow bypass for explicit wake words
   in follow-up window. Add new forms of the assistant name here (e.g. ASR mishears).

7. **`config.yaml addressing:` block:** All thresholds are externalized and hot-reloadable (the
   orchestrator calls `_maybe_reload_config()` at every loop iteration, line 5832).

8. **`src/kenning/observations/integrations.py:observe_addressing_verdict()`:** Telemetry schema
   for addressing decisions; extend `extra` dict to add new signals without breaking the log format.

9. **Evaluation harness:** `scripts/eval_harness.py:score_addressing()` (lines 263–302) and
   `tests/test_addressing.py` (50-utterance ground truth set). New test cases can be added to
   `_CASES`; the eval harness reads a corpus JSONL with `expected_addressing` field.

---

## Retire-not-remove candidates (u1.0)

1. **`ZeroShotAddresseeModel` / Flan-T5-small:** The 300 MB CPU model with flat 0.75 confidence
   is a poor fit for u1.0's always-on 8B LLM. The addressing question can be answered by the 8B
   model itself (one extra output token, zero new inference cost). Retire the Flan model as the
   fallback; keep the class as a reference for the prompt template and the context-injection pattern.

2. **Two-layer cascade (`_classify_cascade`):** The rules → Flan fallback in the legacy classifier
   should be retired as the primary path. It should be preserved as the fail-open fallback (already
   named `_classify_cascade` in `9438fc5`). The log-odds fusion should become primary.

3. **`AddressingConfig.zero_shot_model` / `load_eagerly`:** Both are Flan-specific. When Flan is
   retired, these become dead config. Leave in place with comments explaining they are deprecated.

4. **`_DIRECT_ADDRESS` regex:** Already partially superseded by `_FOLLOWUP_WAKE_RE` in
   orchestrator.py. Should be merged/replaced with a wider pattern that covers both "kenning" and
   "ultron" (and ASR mishears). The current regex can be kept with a note that it is the
   short-circuit-rate-optimized path for the pure-rule layer.

5. **`follow_up_enabled` flag:** In u1.0 always-listening, the "follow-up window" concept is
   replaced by continuous classification. The flag can be retired but its mechanics (the
   `warm_mode_duration_seconds` window concept) may be repurposed for a "recency prior" parameter.

6. **`should_respond()` convenience wrapper:** The orchestrator accesses `verdict.decision`
   directly; the wrapper is not called in the current live code. Can be retired or retained as an
   API convenience shim.

---

## Gotchas

1. **`_DIRECT_ADDRESS` is "kenning"-only.** "Ultron, ..." does NOT fire the 0.95-confidence direct
   address rule. In the follow-up window this is papered over by `_FOLLOWUP_WAKE_RE` in
   orchestrator.py:6067. In u1.0, "ultron" must be added to `_DIRECT_ADDRESS` (or its replacement).

2. **`follow_up_enabled` Python default (True) conflicts with config.yaml value (false).** If
   `config.yaml` is not present or the `addressing:` block is missing, the Python default arms the
   follow-up window — which generates false positives. Always ship with config.yaml present.

3. **Flan-T5 zero-shot confidence is NOT calibrated.** The 0.75 YES/NO / 0.50 UNCLEAR heuristic
   means `zero_shot_addressed_min_confidence: 0.80` always rejects zero-shot YES (0.75 < 0.80).
   This makes the min-confidence gate effectively a "never trust zero-shot YES" rule on HEAD.
   Intended or not, the net effect is that ambiguous utterances in the follow-up window always
   resolve to NOT_ADDRESSED when the zero-shot returns YES.

4. **114 false-positive captures per session (live measurement).** When `follow_up_enabled=true`
   the 30s window armed after every turn and captured room/stream/teammate speech. Flan-T5 was the
   only gate and mis-accepted "Okay." and "Why is it suddenly running like this" as ADDRESSED. The
   log-odds fusion design was specifically developed to fix this but was not shipped because the
   window was disabled instead.

5. **Lean gaming boot defers Flan-T5.** `barebones_lazy_zero_shot_addressee: true` forces lazy
   load even when `load_eagerly=true`. First call to `classify()` when follow-up fires will stall
   ~8s in gaming mode. Since `follow_up_enabled=false` in gaming, this is currently harmless but
   is a trap if follow_up is re-enabled without adjusting gaming boot behavior.

6. **Classifier is constructed at orchestrator init (line 1149) unconditionally.** It is always
   built even in lean gaming / follow_up_enabled=false. Only the Flan model load is deferred.
   This means the `recent_turns_provider` closure is always created and the `_log_lock` always
   allocated — trivial cost but notable for u1.0 if the whole classifier is replaced.

7. **No three-scenario discrimination exists.** The three scenarios in u1.0 (relay-to-team,
   talking-to-stream/others, talking-to-ultron) require a new signal layer. The current binary
   ADDRESSED/NOT_ADDRESSED cannot represent all three. Adding a RELAY_INTENT output is the missing
   piece; `_is_relay_command()` in the orchestrator already partially implements this.

8. **Follow-up window deadline is measured from last response, not last sound.** Rejected utterances
   (NOT_ADDRESSED) do NOT reset the window deadline. A 30-second window starting after the last
   response means the effective classification window is strictly bounded; room chatter does not
   keep it alive indefinitely. This is intentional behavior per code comments (orchestrator.py:6049).

9. **`zero_shot_addressed_min_confidence` defaults differ.** Python code: `0.0` (line 75 of
   classifier.py); config.yaml: `0.80`; AddressingConfig dataclass: `0.80`. The orchestrator reads
   from config, so the live value is 0.80. The Python constructor default of 0.0 is only the fallback
   when not constructed via `_load_addressing_classifier()`.

10. **`observations.observe_addressing_verdict()` is called with `seconds_since_response=0.0`
    hardcoded** (classifier.py:236). The actual value was passed to `classify()` but is not
    forwarded to the observation. This is a logging gap.

---

## Open questions

1. **Will u1.0 use always-listening (every utterance classified) or a hybrid (wake-word required,
   optional follow-up)?** The current classifier was designed for the follow-up window only. An
   always-on gate changes the false-positive budget dramatically and likely requires the 8B LLM
   to answer the addressing question directly.

2. **What is the right three-scenario taxonomy for u1.0?**
   - (A) talking-to-team (relay intent, for LLM to rephrase and forward)
   - (B) talking-to-stream / third party / self (ignore)
   - (C) talking-to-Ultron for private reply
   The current binary classifier provides no basis for (A) vs (C).

3. **Should the relay bypass (`_is_relay_command()`) move inside the classifier or remain in the
   orchestrator?** In u1.0 where relay is one of the three scenarios, it is architecturally cleaner
   to classify relay-intent inside the addressing gate rather than bypass it.

4. **Can the 8B LLM produce calibrated addressing probabilities?** In u1.0 all responses go through
   the 8B LLM. If the LLM's first token is a structured YES/NO/RELAY/IGNORE verdict, the entire
   separate classifier can be retired. This needs latency measurement (streaming the classification
   token before deciding whether to continue generation).

5. **Should `KENNING_ADDRESSING_TAU` (the cost-asymmetric threshold from `9438fc5`) be in
   config.yaml rather than an env var?** The env var approach was appropriate for live
   stream-tuning; config.yaml is cleaner for persistent settings.

6. **Is the 30s warm_mode_duration correct for u1.0?** Chosen in 2026-05 for the conversational
   use case. Gaming use case with relay-intent always-on may want a different model entirely.

7. **Logistic-regression calibration of the log-odds weights** was mentioned in `9438fc5` as
   deferred. Is there enough labeled data in `logs/addressing.jsonl` to run a fit? The observation
   system is collecting data already.

8. **`_FOLLOWUP_WAKE_RE` hardcodes "ultron|kenning|altron|ultraun".** These ASR mishears should be
   a shared constants file with the wake-word engine's mishear table. Is there a canonical source
   of truth for wake-word ASR variations?

---

## References

- `src/kenning/addressing/__init__.py` — module docstring + re-exports
- `src/kenning/addressing/rules.py` — rule definitions, `classify()`, `explain_rules()`
- `src/kenning/addressing/zero_shot.py` — Flan-T5-small wrapper, `_PROMPT_TEMPLATE`, `classify()`
- `src/kenning/addressing/classifier.py` — `AddressingClassifier`, `AddressingVerdict`, decision logging
- `src/kenning/config.py:1625–1641` — `AddressingConfig` dataclass
- `config.yaml:885–907` — live `addressing:` config block
- `src/kenning/pipeline/orchestrator.py:45` — import of AddressingClassifier/Decision
- `src/kenning/pipeline/orchestrator.py:200–209` — `_FOLLOWUP_WAKE_RE` definition + motivation
- `src/kenning/pipeline/orchestrator.py:1149` — `self.addressing` construction
- `src/kenning/pipeline/orchestrator.py:3126–3155` — `_is_relay_command()`
- `src/kenning/pipeline/orchestrator.py:5332–5360` — `_load_addressing_classifier()`
- `src/kenning/pipeline/orchestrator.py:5794` — `_addr_cfg = get_config().addressing` in `run()`
- `src/kenning/pipeline/orchestrator.py:5897` — follow-up window arm check
- `src/kenning/pipeline/orchestrator.py:6052–6105` — addressing gate in the hot loop
- `src/kenning/observations/integrations.py:61–85` — `observe_addressing_verdict()`
- `tests/test_addressing.py` — 50-utterance ground truth set
- `tests/error_recovery/test_addressing_failures.py` — failure-mode tests
- `scripts/review_addressing.py` — JSONL decision log viewer
- `scripts/eval_harness.py:263–302` — `score_addressing()` evaluator
- Git commit `9438fc5` — log-odds fusion design (NOT on HEAD; branch `9438fc5`)
- Git commit `ad186cf` — disable follow_up_enabled (wake-word-required fix)
- Git commit `0b5da79` — re-add blunt _FOLLOWUP_WAKE_RE bypass
