# B6: MAP addressee-confidence fusion & the three-scenario problem

Recon date: 2026-06-20. Branch: `claude/infallible-kepler-0a865d`. Tip: `dfadb89`.
Cross-reference: `boardA_addressing.md` maps the same subsystem from the static-structure angle.
This B-board document focuses on (1) the full addressing math, including the log-odds fusion design
on branch `9438fc5`, and (2) the three-scenario gap analysis for u1.0 always-listening.

---

## Overview

The addressee classifier answers: *is this spoken utterance directed at Ultron/Kenning?* It is the
gate between ambient/room/stream speech and the processing pipeline. As of HEAD (`dfadb89`), it is
**disabled** (`addressing.follow_up_enabled: false` in `config.yaml:892`). Every turn must be
initiated with the wake word. The classifier code is intact and was last meaningfully tested in
commit `9438fc5` (2026-06-18), which contained a superior log-odds fusion design that was shelved
when the follow-up window itself was disabled due to 114 false-positive captures per live session.

**For Ultron 1.0** (always-listening mandate), the classifier must be re-enabled and extended to
distinguish three scenarios, not just ADDRESSED/NOT_ADDRESSED:
- (A) talking to someone else (Discord, partner, roommate)
- (B) talking out loud to stream chat or muttering
- (C) talking to Ultron for a ME-ONLY reply

The existing relay bypass (`_is_relay_command()`) already partially implements a fourth sub-case
(relay-to-team). The gap is that the current binary classifier cannot separate (A), (B), and (C).

---

## Files & key symbols

### `src/kenning/addressing/__init__.py` (lines 1–26)

| Symbol | Kind | Description |
|--------|------|-------------|
| `AddressingClassifier` | class re-export | Top-level classifier entrypoint (from classifier.py) |
| `AddressingDecision` | enum re-export | ADDRESSED / NOT_ADDRESSED / UNCERTAIN |
| `AddressingVerdict` | dataclass re-export | Decision output with confidence, source, reason |

Module docstring (lines 1–14) establishes the COLD/WARM mode framing: COLD mode = wake word
answers the addressing question; WARM mode = follow-up window requires per-utterance classification.

---

### `src/kenning/addressing/rules.py` — HEAD (lines 1–322)

**Pattern constants (HEAD):**

| Symbol | Lines | Class | Confidence | Notes |
|--------|-------|-------|------------|-------|
| `_FACTUAL_QUESTION_STEMS` | 42–53 | YES | 0.85 (0.55 if fragment) | what/who/where/why/how/which at start |
| `_SECOND_PERSON_QUESTIONS` | 60–74 | UNCERTAIN | 0.55 | "do you/did you/can you" -- ambiguous |
| `_IMPERATIVE_VERBS` | 78–92 | YES | 0.88 | play/pause/find/open/turn on/... at start |
| `_DIRECT_ADDRESS` | 97–100 | YES | 0.95 | `(?:hey|okay|alright)?kenning\b` — kenning-ONLY, not "ultron" |
| `_CONTINUATION_TOKENS` | 105–114 | YES | 0.78+bias | yes/no/ok/go ahead/stop/cancel |
| `_THIRD_PERSON_MENTION` | 125–128 | NO | 0.85 | "kenning said/thinks/told/..." |
| `_THIRD_PARTY_NARRATIVE` | 140–164 | NO | 0.85 | "I'm talking to him/her", "you'll see", "watch this" |
| `_THIRD_PARTY_POSSESSIVE_QUESTION` | 175–179 | NO | 0.85 | "where's his X" / "what's her Y" |
| `_PHONE_OPENERS` | 183–192 | NO | 0.92 | "hello?", "hey mom", "it's me", "yo" |
| `_INTERJECTIONS` | 195–204 | NO | 0.85 | "oh god", "shit", "lol", "hmm" (set) |

**`classify()` function (HEAD, lines 207–307):**
- Signature: `classify(utterance: str, seconds_since_response: float = 0.0) -> Optional[RuleHit]`
- Returns `None` when no rule fires with confidence >= 0.5 (fall through to zero-shot)
- Priority: NO rules evaluated FIRST (phone_opener > third_person > third_party_narrative > possessive_q > interjection), then YES rules (direct_address > imperative > factual_question > second_person_q > continuation)
- Fragment guard at lines 274–291: factual question demoted to UNCERTAIN 0.55 if < 4 words, trails off, or has third-person subject
- Recency bias at lines 301–305: continuation token gets +0.05 if `seconds_since_response < 5.0`

---

### `src/kenning/addressing/rules.py` — FUSION DESIGN (commit `9438fc5`, NOT on HEAD)

Commit `9438fc5` (2026-06-18, branch `9438fc5`, not merged to HEAD) adds to `rules.py`:

**New pattern constants (fusion rules.py lines 205–232):**

| Symbol | Lines | Description |
|--------|-------|-------------|
| `_LEADING_WAKE` | 218–222 | Recognizes "ultron\|kenning\|altron\|ultraun" at start (fixes the kenning-only bug) |
| `_NAME_ANYWHERE` | 223 | `\b(?:ultron\|kenning)\b` — mid-sentence name detection |
| `_SUBJ_PRONOUN_OPENER` | 227–228 | `^\s*(?:i\|we\|he\|she\|they\|it)` at utterance start — NOT-ADDRESSED signal |
| `_PARTICLE_OPENER` | 229–230 | `^\s*(?:yeah\|yep\|ok\|oh\|uh+\|um+)` — acknowledgement particles, NOT-ADDRESSED |
| `_TRAILS_OFF` | 231 | Tuple `(",", " and", " but", " so", ...)` — incomplete utterance markers |
| `_THIRD_PERSON_SUBJ_Q` | 232–233 | `^(?:how\|what\|...)\s+(?:he\|she\|...)` — 3rd-person subject in question |

**`features()` function (fusion rules.py lines 237–272):**

Returns a `dict` of graded features in [0,1] (plus `recency_s: float`):

```python
{
    "leading_wake":           1.0 if name at start (NOT 3rd-person) else 0.0,
    "embedded_or_3p_name":    1.0 if name mid-sentence or 3rd-person mention else 0.0,
    "initial_imperative":     1.0 if imperative verb at start (of remainder after wake) else 0.0,
    "factual_question":       1.0 if question stem on remainder (>= 4 words, not trailing) else 0.0,
    "second_person_q":        1.0 if "do you/can you" pattern on remainder else 0.0,
    "continuation":           1.0 if lowered in _CONTINUATION_TOKENS else 0.0,
    "subj_pronoun_opener":    1.0 if subject pronoun at start (no wake present) else 0.0,
    "particle_opener":        1.0 if acknowledgement particle at start (no wake present) else 0.0,
    "phone_opener":           1.0 if _PHONE_OPENERS match else 0.0,
    "interjection":           1.0 if lowered in _INTERJECTIONS else 0.0,
    "third_party_narrative":  1.0 if _THIRD_PARTY_NARRATIVE match else 0.0,
    "possessive_q":           1.0 if possessive-question match else 0.0,
    "trails_off":             1.0 if ends with conjunction (and no wake/imperative) else 0.0,
    "recency_s":              float — seconds since last response,
}
```

Key design property: `leading_wake` evaluates features on the REST of the utterance after the wake
token (`text[wm.end():]`) so "Ultron, show me X" fires both `leading_wake=1.0` AND
`initial_imperative=1.0` on the remainder "show me X".

`matcher_hit` is injected by the caller (classifier.py line 149): `feats["matcher_hit"] = 1.0 if matcher_hit else 0.0`. This feature is NOT in `features()` — it must be added at call time.

---

### `src/kenning/addressing/zero_shot.py` — HEAD (lines 1–133)

**`ZeroShotAddresseeModel` (lines 50–132):**

| Symbol | Line | Value |
|--------|------|-------|
| `model_name` default | 53 | `"google/flan-t5-small"` (~300 MB CPU RAM) |
| device | 71 | always CPU (`self._model.to("cpu")`) |
| `_PROMPT_TEMPLATE` | 23–33 | YES/NO/UNCLEAR prompt with context block + `seconds_since` + utterance |
| `max_new_tokens` | 115 | 4 (greedy, `num_beams=1, do_sample=False`) |
| latency | docstring | 78–94 ms median; budgeted < 100 ms |

**`classify()` returns `(verdict: str, confidence: float, latency_ms: float)`:**
- `verdict` in `{"YES", "NO", "UNCLEAR"}`; unexpected → `"UNCLEAR", 0.40`
- On HEAD: confidence is **HEURISTIC** — YES/NO = 0.75, UNCLEAR = 0.50 (lines 130–132)
- On `9438fc5`: confidence is the **REAL softmax probability** of the first generated token; fail-open to heuristic constants if step scores unavailable

**Critical: HEAD zero_shot confidence = flat 0.75 for YES/NO.**
With `zero_shot_addressed_min_confidence: 0.80` in config.yaml, every zero-shot YES is
downgraded (0.75 < 0.80), making the min-confidence gate effectively "never trust zero-shot YES."
The fusion design (`9438fc5`) fixes this by using the real P(YES).

---

### `src/kenning/addressing/classifier.py` — HEAD (lines 1–273)

**`AddressingVerdict` dataclass (lines 29–46):**

| Field | Type | Description |
|-------|------|-------------|
| `decision` | AddressingDecision | ADDRESSED / NOT_ADDRESSED / UNCERTAIN |
| `confidence` | float | [0,1] |
| `source` | str | "rule" / "zero_shot" / "default_silent" |
| `reason` | str | Human-readable explanation string |
| `latency_ms` | float | Wall-clock ms for entire classify() call |
| `rule_hit` | Optional[str] | Rule reason if a rule fired |
| `zero_shot_raw` | Optional[str] | Raw "YES"/"NO"/"UNCLEAR" from Flan |

**`AddressingClassifier.__init__` constructor params (lines 66–75):**

| Param | Default | Effect |
|-------|---------|--------|
| `rule_confidence_threshold` | 0.8 | Rule >= this → skip zero-shot |
| `default_silent_on_uncertain` | True | UNCERTAIN → NOT_ADDRESSED |
| `log_path` | None | JSONL decision log |
| `zero_shot_model_name` | "google/flan-t5-small" | HF model id |
| `load_zero_shot_eagerly` | False | Load Flan-T5 at construction vs first call |
| `recent_turns_provider` | None | `Callable[[int], List[Tuple[str, str]]]` for context |
| `zero_shot_addressed_min_confidence` | 0.0 | Gate: zero-shot YES below this → demote |

**`classify()` method (HEAD, lines 96–203) — the legacy cascade:**

```
1. classify_by_rules(utterance, seconds_since) -> rule_hit
2. if rule_hit.confidence >= 0.8:
       return verdict (source="rule")
3. else:
       context = recent_turns_provider(4)
       (raw, zs_conf, zs_ms) = zero_shot.classify(utterance, context, seconds_since)
       if zero_shot fails:
           return NOT_ADDRESSED (source="default_silent", conf=0.30)
       if zs_conf < zero_shot_addressed_min_confidence and verdict==ADDRESSED:
           downgrade to NOT_ADDRESSED/UNCERTAIN
       if rule_hit agreed:
           confidence = max(zs_conf, rule_hit.confidence)
       return AddressingVerdict (source="zero_shot")
```

---

### `src/kenning/addressing/classifier.py` — FUSION DESIGN (commit `9438fc5`)

**Log-odds weights `_ADDR_W` (classifier.py lines ~38–52 in `9438fc5`):**

| Feature | Weight | Sign | Rationale |
|---------|--------|------|-----------|
| `leading_wake` | +3.0 | strong YES | Name at utterance start = vocative; most discriminative |
| `matcher_hit` | +2.2 | strong YES | Deterministic command matcher parsed it; definitionally addressed |
| `initial_imperative` | +1.6 | YES | Imperative verb after wake or at start |
| `factual_question` | +1.0 | YES | wh-question stem |
| `continuation` | +0.8 | YES | Single-word response token |
| `second_person_q` | 0.0 | neutral | "can you..." ambiguous; let recency decide |
| `embedded_or_3p_name` | -2.2 | strong NO | Name mid-sentence or third-person mention |
| `subj_pronoun_opener` | -1.4 | NO | "I/he/she/they" opener (empirically dominant NOT-ADDRESSED marker) |
| `particle_opener` | -1.2 | NO | "yeah/yep/ok/oh" opener (talking to/about someone else) |
| `phone_opener` | -2.5 | strong NO | "hey mom/yo/hello?" |
| `interjection` | -2.0 | NO | Self-talk / exclamation |
| `third_party_narrative` | -2.2 | strong NO | "I'm talking to him/you'll see" |
| `possessive_q` | -2.0 | strong NO | "where's his X?" |
| `trails_off` | -1.0 | NO | Utterance ends with conjunction (fragment) |

Additional scalars:
- `_ADDR_W_FLAN = 1.0` — weight on the Flan log-odds term when consulted
- `_ADDR_FLAN_BAND = 3.0` — Flan consulted only when `|lex_logit| < 3.0`

**Recency prior `_addr_b0(t)` (fusion classifier.py ~line 54–57):**
```python
def _addr_b0(t: float) -> float:
    return 0.4 - min(max(t, 0.0) / 20.0, 1.0) * 1.0
```
- At t=0 (just spoke): b0 = +0.4 (bias toward ADDRESSED)
- At t=20s: b0 = -0.6 (bias toward NOT_ADDRESSED)
- Decays linearly over 20 seconds

**Cost-asymmetric threshold `_addr_tau()` (fusion classifier.py ~line 60–67):**
```python
def _addr_tau() -> float:
    return float(os.getenv("KENNING_ADDRESSING_TAU", "0.20"))
```
- Default tau = 0.20 (very permissive: a sigmoid of 0.2 corresponds to logit ≈ -1.39)
- Caller can raise via `KENNING_ADDRESSING_TAU` env var at runtime for live-stream use

**Fusion math `_classify_fused()` (fusion classifier.py ~lines 134–169):**
```
feats = rule_features(utterance, seconds_since)   # dict from rules.features()
feats["matcher_hit"] = 1.0 if matcher_hit else 0.0
lex = _addr_b0(recency_s) + sum(_ADDR_W[k] * feats[k] for k in _ADDR_W)
logit = lex

if |lex| < _ADDR_FLAN_BAND (= 3.0):
    (raw, zs_conf, _) = zero_shot.classify(utterance, context, seconds_since)
    p_yes = zs_conf if raw=="YES" else (1-zs_conf) if raw=="NO" else 0.5
    logit += _ADDR_W_FLAN * log(p_yes / (1 - p_yes))

p = sigmoid(clip(logit, -30, 30))
tau = _addr_tau()    # default 0.20
decision = ADDRESSED if p >= tau else NOT_ADDRESSED (or UNCERTAIN if !default_silent)
verdict.source = "fusion"
```

**Fail-open fallback:** `classify()` wraps `_classify_fused()` in a try/except; if the fusion
raises, it calls `_classify_cascade()` (the HEAD-equivalent legacy rules→Flan cascade). The
cascade stays as a named method, not just a fallback.

**New `matcher_hit` parameter to `classify()`:** In the fusion design, the orchestrator can pass
`matcher_hit=True` when a deterministic command matcher already parsed the utterance. This injects
a +2.2 logit contribution before any other feature is computed, making clearly matched commands
(relay / Spotify / stop button) essentially always ADDRESSED without needing the wake word.

---

### `src/kenning/pipeline/orchestrator.py` — orchestrator wiring

**Key addressing-related constants at module level:**

| Symbol | Line | Description |
|--------|------|-------------|
| `_WAKE_MISHEAR` | 183 | Regex union of "ultron" homophones + fillers ("tron", "ron", "ultra", "yeah", "ok", ...) |
| `_WAKE_REMNANT_RE` | 194 | Strips leading misheard wake from transcript (iterative, fallback-only) |
| `_FOLLOWUP_WAKE_RE` | 208 | `^\s*(?:hey[\s,]+)?(?:ultron\|kenning)\b` — explicit wake in follow-up bypasses classifier |
| `_CAPTURE_STALL_TIMEOUTS` | 222 | 2 (consecutive 0.5s timeouts = stream stall) |
| `_CAPTURE_STALL_SECONDS` | 223 | 1.0 (stall threshold for _follow_up_listen loop) |
| `State.FOLLOW_UP_LISTENING` | 166 | Enum value "follow_up" |
| `_FU_TIMEOUT` | 170 | Sentinel from _follow_up_listen on deadline expiry |
| `_FU_WAKE` | 171 | Sentinel from _follow_up_listen on wake word during window |

**`_load_addressing_classifier()` (lines 5332–5360):**
- Called at construction (line 1149): `self.addressing = self._load_addressing_classifier()`
- Reads `addr_cfg = get_config().addressing`
- Creates `recent_turns_provider` closure over `self.memory.recent(n)` (safe if memory=None)
- Lean gaming: `barebones_lazy_zero_shot_addressee=True` forces lazy Flan-T5 load even when `load_eagerly=True`
- Returns `AddressingClassifier` instance; always constructed, even when `follow_up_enabled=False`

**`run()` addressing gate (lines 6048–6104):**

```python
if came_from_follow_up:
    # Pre-classifier bypass 1: relay commands are definitionally addressed
    if self._is_relay_command(user_text) or _FOLLOWUP_WAKE_RE.match(user_text):
        # route directly -- no classifier latency
    else:
        seconds_since = time.monotonic() - self._last_response_finished_monotonic
        verdict = self.addressing.classify(user_text, seconds_since_response=seconds_since)
        if verdict.decision != AddressingDecision.ADDRESSED:
            continue  # discard; keep follow-up window alive
```

**Key note:** rejected follow-up utterances do NOT reset `follow_up_until`. The window expires
relative to the LAST RESPONSE time, not relative to last room sound. This is intentional
(orchestrator.py:6049 comment).

**`_is_relay_command()` (lines 3126–3154):**
- Checks `match_relay_toggle(user_text)` and `match_relay_command(user_text, names=...)` 
- Returns False if `relay_speech.enabled=False`
- Fail-open to False on any exception
- This is the "relay-intent bypass" that partially implements Scenario A (relay to team)

**Follow-up window arms after EVERY successful dispatch (multiple sites, e.g. 6159–6165):**
```python
if _addr_cfg.follow_up_enabled:
    follow_up_until = (
        self._last_response_finished_monotonic
        + _addr_cfg.warm_mode_duration_seconds
    )
```
Relay turns use a longer extension: `max(warm_mode_duration_seconds, relay_follow_up_seconds)`.

---

### `src/kenning/audio/_relay_intent.py` — relay-intent gate

The relay-intent gate is a SEPARATE pre-classifier component in the normalizer, NOT part of the
addressing classifier. It runs inside `command_normalizer.recover_relay_lead()` before the
addressing classifier sees the utterance:

**`RelayIntentGate` (lines 158–221):**
- `decide(text)` → `True` (relay), `False` (abstain → conversational), or `None` (gate down)
- Threshold: `pos - neg >= 0.06` where pos/neg are max cosine similarity over exemplar clouds
- Exemplar clouds: 46 positive relay phrases vs. 53 negative narration/banter/analysis phrases
- Fail-open: if embedding sidecar is down, returns `None` (caller falls back to keyword behavior)

This gate answers a SUBSET of the three-scenario question: "is this a team relay or narration?"
It does NOT distinguish scenario (A) vs. (B) vs. (C) — it only guards against false-relay.

---

## Control/data flow

### COLD mode — current default (`follow_up_enabled: false`)

```
wake word fires
  -> _wait_for_wake_word() returns True
  -> _capture_utterance() -> speech ndarray
  -> STT -> user_text
  -> _WAKE_REMNANT_RE strip
  -> _WAKE_ONLY check (stand down if bare wake word)
  -> addressing classifier NOT called (came_from_follow_up = False)
  -> record dialogue turn
  -> normalize_command()
  -> intent dispatch -> relay -> routing -> LLM/TTS
```

### WARM mode — when `follow_up_enabled: true`

```
last turn completes
  -> follow_up_until = now + warm_mode_duration_seconds (30s)

main loop (follow_up condition):
  -> _follow_up_listen(deadline=follow_up_until)
       runs VAD + wake-word detection simultaneously
       returns: _FU_TIMEOUT / _FU_WAKE / audio_ndarray
  -> on audio_ndarray: came_from_follow_up = True

came_from_follow_up = True:
  -> STT -> user_text
  -> _WAKE_REMNANT_RE strip
  -> _WAKE_ONLY check

  BYPASS GATE (orchestrator.py:6067):
  if _is_relay_command(user_text):
      route to relay (addressing bypassed)
  elif _FOLLOWUP_WAKE_RE.match(user_text):   ("ultron" or "kenning" at start)
      route directly (addressing bypassed)
  else:
      verdict = addressing.classify(user_text, seconds_since=seconds_since)
      if verdict.decision != ADDRESSED:
          continue  (discard, window stays alive)
      # proceed to routing
```

### The relay-intent gate in the normalizer (separate from addressing)

```
normalize_command(user_text):
  if bare callout detected (no explicit "tell my team" lead):
    relay_intent_ok(text) -> True/False/None
    if True: prepend "tell my team" lead
    if False: leave as-is (goes to conversational)
    if None (sidecar down): fall back to keyword behavior
```

### Full turn-to-turn data flow (WARM mode, follow_up_enabled=true, sidecar up)

```
mic audio (continuous)
  -> ring_buffer (pre-roll)
  -> VAD detects speech
  -> _follow_up_listen captures audio ndarray

-> Whisper STT -> raw user_text
-> _WAKE_REMNANT_RE strip
-> _is_relay_command() probe (bypass if True)
-> _FOLLOWUP_WAKE_RE probe (bypass if True)
-> AddressingClassifier.classify()
     -> rules.classify() -> RuleHit or None
        if conf >= 0.8: return immediately (source="rule")
     -> zero_shot.classify(utterance, context=recent_4_turns, seconds_since)
        -> Flan-T5-small on CPU (78-94ms)
        -> (raw_verdict, heuristic_0.75, zs_ms)
     -> min_confidence gate (0.80): downgrade YES if zs_conf < 0.80
     -> AddressingVerdict (source="zero_shot")
        log to logs/addressing.jsonl
        observe_addressing_verdict() telemetry
-> if NOT_ADDRESSED: continue (discard)
-> record_dialogue_turn("user", user_text)
-> normalize_command()
     -> relay_intent gate (if bare callout)
-> intent dispatch -> relay -> routing -> LLM/TTS
```

---

## Key findings

1. **The classifier is dead code at runtime.** `follow_up_enabled: false` in `config.yaml:892`
   disables the follow-up window; the classifier is constructed at boot but never called. For u1.0
   always-listening, enabling the classifier is the first prerequisite.

2. **Two implementations exist across commits.** HEAD has the legacy two-layer cascade (rules →
   Flan-T5). Commit `9438fc5` (never merged, on its own ephemeral branch) has the superior
   log-odds fusion: graded feature extractor (`rules.features()`), calibrated log-odds sum,
   recency prior, Flan consulted only in the undecided band (`|lex|<3.0`), cost-asymmetric
   threshold (tau=0.20), and a `matcher_hit` signal from the orchestrator. The fusion was never
   rolled back — the WINDOW was disabled instead (the classifier was not the only problem; the
   30s window itself was too permissive regardless of classifier quality).

3. **The fusion design is architecturally superior and should be the u1.0 base.** Specifically:
   - Position-aware `_LEADING_WAKE` fixes the "ultron" invisibility bug in `_DIRECT_ADDRESS`
   - `features()` is the natural extension point for any new binary signal
   - The band-consult design (`|lex|<3.0`) skips Flan for clear cases → zero model latency for ~80% of utterances
   - `matcher_hit` signal from orchestrator enables deterministic short-circuits to feed back into the fusion
   - Real P(YES) from Flan (not flat 0.75) is calibratable via logistic regression on `logs/addressing.jsonl`

4. **`_DIRECT_ADDRESS` is "kenning"-only (HEAD, rules.py:97-100).** The wake word "ultron" is
   invisible to the rule-based direct-address pattern. The orchestrator patches this with
   `_FOLLOWUP_WAKE_RE` (lines 208–209) which recognizes "ultron|kenning" at start of follow-up
   utterances. The fusion design fixes this properly via `_LEADING_WAKE` in `rules.features()`.

5. **Zero-shot confidence is flat 0.75 on HEAD.** The `zero_shot_addressed_min_confidence: 0.80`
   gate in config.yaml effectively rejects ALL zero-shot YES verdicts (0.75 < 0.80 always). This
   makes the HEAD classifier behave as: if a rule fires at >= 0.8 → use it; else → NOT_ADDRESSED.
   The zero-shot model is consulted but its YES verdict is always overridden. This is confirmed by
   the config.yaml:898–903 comment acknowledging the 0.75 saturation problem.

6. **No three-scenario discrimination exists anywhere in the codebase.** The classifier output
   is ADDRESSED / NOT_ADDRESSED / UNCERTAIN. There is no concept of:
   - Scenario A: talking to Discord/partner/third party (currently lumped into NOT_ADDRESSED)
   - Scenario B: talking to stream/out-loud (also NOT_ADDRESSED)
   - Scenario C: talking to Ultron for a private reply (currently ADDRESSED → full pipeline)
   The relay-intent gate (`_relay_intent.py`) partially answers "is this a team relay?" but it is
   a separate system targeting a different slice of the problem.

7. **`_is_relay_command()` is the closest existing approximation of Scenario A detection.** It
   tests whether the utterance matches the strict relay grammar ("tell my team X", "ask Jett to
   Y"). When true, it is treated as definitionally addressed + sent to the relay handler (not the
   personal LLM). This is effectively the relay-to-team sub-case of Scenario A, but it only
   catches explicit relay commands, not "I should tell them to push" or the broader stream-chat
   narration.

8. **The relay-intent gate (`_relay_intent.py`) addresses false-relays, NOT false-addresses.**
   Its job is inside `recover_relay_lead()`: prevent bare callouts (no "tell my team" lead) from
   being falsely prepended with a relay lead and sent to teammates. It does NOT gate whether the
   utterance is for Ultron at all. These are two different detection problems.

9. **Observations telemetry is in place.** `observe_addressing_verdict()` in
   `src/kenning/observations/integrations.py:61` emits an event per verdict with utterance_len,
   decision, confidence, reason, classifier_source, latency_ms. The `logs/addressing.jsonl` JSONL
   log captures every verdict with the full utterance text. This is the training data for offline
   calibration. NOTE: `seconds_since_response=0.0` is hardcoded in the observation call
   (classifier.py:236) — a logging gap.

10. **The 78-test addressing test suite covers the binary ADDRESSED/NOT_ADDRESSED split.** No
    tests exercise three-scenario discrimination; the test set has no "talking-to-stream" or
    "talking-to-Discord" labels.

---

## Flags & config

All under `addressing:` in `config.yaml` (lines 885–907) and `AddressingConfig` in
`src/kenning/config.py` (lines 1625–1641).

| Key | Python default | config.yaml live value | Effect |
|-----|---------------|------------------------|--------|
| `follow_up_enabled` | `True` | **`false`** | Master switch. False = wake-word-only; classifier never runs |
| `warm_mode_duration_seconds` | 30.0 | 30.0 | Length of follow-up window after a response |
| `default_uncertain_to_not_addressed` | `True` | `true` | UNCERTAIN → NOT_ADDRESSED (conservative) |
| `rule_confidence_threshold` | 0.8 | 0.8 | Rule >= this → skip zero-shot (lines 105, 5347) |
| `zero_shot_addressed_min_confidence` | 0.80 (AddressingConfig) | 0.80 | Low-confidence YES downgraded; effectively rejects all zero-shot YES on HEAD |
| `zero_shot_model` | "google/flan-t5-small" | "google/flan-t5-small" | HF model id for zero-shot |
| `load_eagerly` | `True` | `true` | Load Flan-T5 at boot vs first ambiguous utterance |
| `log_path` | "logs/addressing.jsonl" | "logs/addressing.jsonl" | JSONL decision log |

**Note:** `AddressingConfig.zero_shot_addressed_min_confidence` defaults to 0.80 in the dataclass
(`config.py:1638`) and in config.yaml. But `AddressingClassifier.__init__`'s default is 0.0
(`classifier.py:74`). The live value comes from config → always 0.80. The Python constructor
default of 0.0 is only the fallback when not built via `_load_addressing_classifier()`.

**Env vars (fusion design `9438fc5` only — NOT in config.yaml or config.py on HEAD):**

| Env var | Default | Effect |
|---------|---------|--------|
| `KENNING_ADDRESSING_TAU` | 0.20 | Cost-asymmetric ADDRESSED threshold; raise on stream to reduce false-positives |

**Lean gaming feature flag:**

| config.yaml key | Lines | Default | Effect |
|----------------|-------|---------|--------|
| `features.barebones_lazy_zero_shot_addressee` | 3086, 1675 | `true` | Forces lazy Flan-T5 load even when `load_eagerly=true` |

**`relay_speech.follow_up_seconds` (relay config, line 3755):**

| Key | Default | Effect |
|-----|---------|--------|
| `relay_speech.follow_up_seconds` | 120.0 | After a relay turn, extend follow-up window to this duration (vs `warm_mode_duration_seconds`) |

This is a relay-specific override: relay turns extend the follow-up window to 120s so the user
can chain relay commands without re-waking. Regular conversational turns use 30s.

---

## Extension points

1. **`rules.py:features()` (from `9438fc5`) — add new binary signals.** The feature dict is the
   natural extension point. Each new signal is a key + a `_ADDR_W[key]` weight. No other code
   changes needed; the fusion logit sum picks it up automatically.
   - Candidate new features for three-scenario: `talking_to_discord` (detects Discord-ping
     patterns), `talking_to_stream` (detects "chat"/"stream" direct-address), `team_relay_hint`
     (relay-intent gate result injected here instead of in normalizer).

2. **`rules.py:_LEADING_WAKE` (from `9438fc5`) — extend with ASR mishears.** The current pattern
   covers "ultron|kenning|altron|ultraun". Additional mishears from `_WAKE_MISHEAR` in
   orchestrator.py should be added when they are reliably position-specific (not fillers).

3. **`zero_shot.py:_PROMPT_TEMPLATE` (lines 23–33) — extend for three-scenario.** The prompt
   currently asks YES/NO/UNCLEAR for "is this for Kenning?" For u1.0 it can be extended to:
   RELAY / PRIVATE / IGNORE — with exemplars for each class. Or, more practically, the 8B LLM
   replaces Flan and produces a structured classification token before the response.

4. **`AddressingClassifier.classify()` — `matcher_hit` parameter (from `9438fc5`).** The
   orchestrator already calls `_is_relay_command()` before the classifier. In u1.0, this probe
   can set `matcher_hit=True` and also pass the relay signal, avoiding the pre-classifier bypass
   pattern and keeping all signals inside the classifier.

5. **`_load_addressing_classifier()` (orchestrator.py:5332) — configuration extension.** A new
   `three_scenario: bool` config key here could switch between the binary classifier (legacy) and
   a three-class classifier for u1.0 always-listening mode.

6. **`_is_relay_command()` (orchestrator.py:3126) — already the relay-intent detection upstream.**
   For u1.0, this probe can be generalized into a `_classify_scenario()` method that returns
   RELAY / PRIVATE / IGNORE / UNKNOWN, replacing both `_is_relay_command()` and the classifier
   follow-up gate.

7. **`config.yaml addressing:` block — add u1.0 keys.** Candidates:
   - `always_listening: bool` — replaces `follow_up_enabled`
   - `three_scenario_enabled: bool` — activate RELAY/PRIVATE/IGNORE output
   - `tau_stream: float` — conservative tau for stream use (vs tau_gaming)
   All are hot-reloadable via `_maybe_reload_config()` (orchestrator.py:5832).

8. **`logs/addressing.jsonl` — training data for logistic regression.** The fusion design noted
   that `_ADDR_W` weights were hand-set and should be fit offline using the accumulated JSONL log.
   The observation schema already captures all needed fields. A `scripts/fit_addressing_weights.py`
   script would produce calibrated log-odds weights from real session data.

9. **`scripts/review_addressing.py` — add three-scenario labels.** Extend to show
   relay/private/ignore labels once the three-scenario output is implemented. The `--misses` flag
   already supports filtering by NOT_ADDRESSED.

---

## Retire-not-remove candidates (u1.0)

1. **`ZeroShotAddresseeModel` / Flan-T5-small.** The 300 MB CPU model with flat 0.75 heuristic
   confidence is a poor fit for u1.0's always-on 8B LLM. The addressing question (or the
   three-scenario classification) can be answered by the 8B LLM itself, either as a structured
   prefix token before the response or as a fast discriminative head. Retire as the primary path;
   keep as a fail-open fallback or development reference. `AddressingConfig.zero_shot_model` and
   `load_eagerly` become vestigial.

2. **Two-layer cascade `_classify_cascade()` (in `9438fc5`).** The rules→Flan fallback should
   be retained as a named fail-open backup (it already is in `9438fc5`'s design). The primary path
   in u1.0 should be either the log-odds fusion → LLM or a fully LLM-driven classification.

3. **`follow_up_enabled` flag.** The concept of "a 30s follow-up window after each turn" is
   replaced by "always listening." The `warm_mode_duration_seconds` value may be repurposed as a
   "recency_s decay horizon" parameter in the log-odds recency prior (`_addr_b0`). The flag itself
   can be retired with a deprecation comment.

4. **`_DIRECT_ADDRESS` regex (HEAD, rules.py:97).** Partially superseded by `_LEADING_WAKE` in
   the fusion design. For u1.0, if the fusion design is adopted, `_DIRECT_ADDRESS` can be retired
   in favor of `_LEADING_WAKE` (which covers both "kenning" and "ultron" and is position-aware).

5. **Pre-classifier bypass `_FOLLOWUP_WAKE_RE` (orchestrator.py:208).** A workaround for
   `_DIRECT_ADDRESS` being kenning-only. In u1.0 with the fusion design's `_LEADING_WAKE`, the
   bypass is no longer needed — the classifier itself handles leading "ultron". Retire the bypass
   and route through the classifier for all utterances.

6. **Pre-classifier bypass `_is_relay_command()` (orchestrator.py:3126).** Conceptually should
   move INSIDE the three-scenario classifier as a `RELAY` output class, not a bypass. Keep the
   function for now but wire it differently: pass its result as `matcher_hit=True` to the
   classifier instead of bypassing the classifier.

7. **`should_respond()` convenience wrapper (classifier.py:205).** Not called in live code
   (orchestrator uses `verdict.decision` directly). Can be retained as an API shim.

---

## Gotchas

1. **`_DIRECT_ADDRESS` is "kenning"-only.** "Ultron, ..." does NOT fire the 0.95-confidence
   direct-address rule at HEAD. Papered over by `_FOLLOWUP_WAKE_RE`. If the follow-up window is
   re-enabled WITHOUT adopting the fusion design, this bug reappears.

2. **`follow_up_enabled` Python default (True) conflicts with config.yaml value (false).** If
   `config.yaml` is absent or the `addressing:` block missing, the Python default arms the
   follow-up window and generates false positives. Always ship with config.yaml present and
   complete.

3. **Zero-shot YES always rejects on HEAD.** With `zero_shot_addressed_min_confidence: 0.80` and
   Flan's flat 0.75 YES confidence, the min-confidence gate always downgrades YES. The effective
   behavior is: if a rule fires >= 0.8 → use it; else → NOT_ADDRESSED (even if Flan says YES).
   This is a silent logical error. On `9438fc5` the real P(YES) fixes this.

4. **114 false-positive captures per session (live measurement).** When `follow_up_enabled=true`
   in live gaming, the 30s window armed after every turn and the only gate was Flan-T5. "Okay."
   and "Why is it suddenly running like this" were accepted as ADDRESSED. The log-odds fusion
   was designed to fix this but never shipped.

5. **Lean gaming stall risk.** `barebones_lazy_zero_shot_addressee=true` defers Flan-T5 load.
   If `follow_up_enabled` is re-enabled in gaming mode, the first ambiguous follow-up utterance
   stalls ~8s while Flan loads. Currently harmless (follow_up is off in gaming), but a trap.

6. **`matcher_hit` parameter not in HEAD classifier.** The fusion design's `classify(utterance,
   ..., matcher_hit=bool)` API change is NOT on HEAD. Code calling `addressing.classify()` on HEAD
   cannot pass this signal; on `9438fc5` it is the primary upstream bypass mechanism.

7. **Relay follow-up window (120s) vs. conversational (30s) creates two-tier behavior.** After a
   relay turn, the follow-up window is 120s; after a conversational turn, 30s. Rejected utterances
   do not reset either window. This means the addressing classifier is consulted more on relay-heavy
   sessions, and a false-accept during the 120s relay window is a longer-lived false-positive.

8. **`sentences_since_response=0.0` hardcoded in observation.** classifier.py:236 always emits
   `seconds_since_response=0.0` to telemetry regardless of the actual value passed to `classify()`.
   The actual recency datum is not observable via the telemetry system.

9. **No test coverage for three-scenario.** The 50-utterance test set (`tests/test_addressing.py`)
   has no "stream-chat comment", "Discord conversation", or "private reply request" test cases.
   The binary ADDRESSED/NOT_ADDRESSED test suite cannot validate three-scenario behavior.

10. **`_addr_tau()` (fusion design) reads `KENNING_ADDRESSING_TAU` on every classify() call.**
    This is intentional (allows runtime tuning) but adds a small os.getenv overhead per call.
    For always-listening (high-frequency calls), consider caching or moving to config.yaml.

---

## Open questions

1. **Should u1.0 use the 8B LLM to classify scenarios directly?** If every utterance goes through
   the 8B anyway, the addressing question can be encoded as a structured first token (RELAY /
   PRIVATE / IGNORE / COMMAND). This would retire Flan-T5 entirely. Latency impact depends on
   whether the classification token arrives before the response begins streaming.

2. **What is the right three-scenario output taxonomy?** Current candidate:
   - `RELAY_TO_TEAM`: pass through the relay handler (team PTT + LLM rephrase)
   - `PRIVATE_REPLY`: Ultron speaks privately (no relay, no PTT)
   - `IGNORE`: discard (Discord/stream/self-talk)
   The current `ADDRESSED` maps to `PRIVATE_REPLY`; `NOT_ADDRESSED` maps to `IGNORE`. `RELAY_TO_TEAM`
   is new. Should `RELAY_TO_TEAM` be a sub-case of `ADDRESSED` (with relay intent as a routing
   signal) or a top-level scenario class?

3. **Where does relay-intent detection move?** Currently the relay-intent gate (`_relay_intent.py`)
   runs in the normalizer, before addressing. For u1.0, it should probably move into the
   three-scenario classifier so all scenario signals are computed together and the normalizer is
   purely a text-cleaning layer.

4. **Is `_ADDR_W_FLAN = 1.0` the right weight for the Flan term?** It was hand-set. Logistic
   regression on `logs/addressing.jsonl` would calibrate this along with all other weights. Is
   there enough labeled data?

5. **Should the recency prior `_addr_b0` decay horizon be configurable?** Currently hardcoded
   to 20s. For always-listening (u1.0), the "recency" concept changes: there may be no clearly
   defined "last response time" if the user speaks in bursts without waiting for Ultron.

6. **How does the three-scenario gate interact with the relay normalizer's `relay_intent_ok()`?**
   Today, `relay_intent_ok()` is called inside `recover_relay_lead()` (normalizer). If the
   three-scenario gate separately identifies `RELAY_TO_TEAM`, does `relay_intent_ok()` become
   redundant, or does it serve a different role (reject non-relay callouts from getting a relay
   lead prepended)?

7. **What distinguishes "talking to Discord/partner" from "talking to stream"?** Both are
   currently NOT_ADDRESSED. For u1.0 they may both collapse to `IGNORE`, but the distinction
   matters if stream narration should trigger a different behavior (e.g., stream-mode relay that
   doesn't use PTT but does post a chat message).

8. **Should `KENNING_ADDRESSING_TAU` move to config.yaml?** The env var approach is appropriate
   for live tuning during a stream, but config.yaml is cleaner for persistent settings and the
   hot-reload mechanism already works.

9. **What is the always-listening latency budget?** The current classifier targets < 100 ms for
   the zero-shot path (80% of calls skip it). For always-listening, EVERY utterance is classified,
   not just follow-up ones. Is the rule-layer + band-consult pattern sufficient, or does always-
   listening require the 8B LLM with a structured classification prefix?

10. **Is the `addressing.jsonl` labeled data usable for logistic regression?** The log captures
    decisions but not ground truth. A labeling pass over the log (correct / incorrect decision)
    is needed before the weights can be fit. The `review_addressing.py` tool can surface false
    positives (`--misses`), but systematic labeling has not been done.

---

## References

- `src/kenning/addressing/__init__.py` — module docstring, re-exports
- `src/kenning/addressing/rules.py:1–322` (HEAD) — rule patterns, `classify()`, `explain_rules()`
- `src/kenning/addressing/rules.py` (`9438fc5`) — `_LEADING_WAKE`, `_NAME_ANYWHERE`, `_SUBJ_PRONOUN_OPENER`, `_PARTICLE_OPENER`, `_TRAILS_OFF`, `_THIRD_PERSON_SUBJ_Q`, `features()`
- `src/kenning/addressing/zero_shot.py:1–133` (HEAD) — Flan-T5-small, `_PROMPT_TEMPLATE`, flat-0.75 heuristic
- `src/kenning/addressing/zero_shot.py` (`9438fc5`) — real P(YES) from softmax step scores
- `src/kenning/addressing/classifier.py:1–273` (HEAD) — legacy cascade, `AddressingVerdict`, `_log()`, `observe_addressing_verdict()`
- `src/kenning/addressing/classifier.py` (`9438fc5`) — `_ADDR_W`, `_ADDR_W_FLAN`, `_ADDR_FLAN_BAND`, `_addr_b0()`, `_addr_tau()`, `_classify_fused()`, `_classify_cascade()` fail-open, `matcher_hit` param
- `src/kenning/config.py:1625–1641` — `AddressingConfig` dataclass
- `config.yaml:885–907` — live `addressing:` config block; `follow_up_enabled: false`
- `src/kenning/pipeline/orchestrator.py:45` — import AddressingClassifier/Decision
- `src/kenning/pipeline/orchestrator.py:183–209` — `_WAKE_MISHEAR`, `_WAKE_REMNANT_RE`, `_FOLLOWUP_WAKE_RE`
- `src/kenning/pipeline/orchestrator.py:1149` — `self.addressing = self._load_addressing_classifier()`
- `src/kenning/pipeline/orchestrator.py:3126–3154` — `_is_relay_command()`
- `src/kenning/pipeline/orchestrator.py:5332–5360` — `_load_addressing_classifier()`
- `src/kenning/pipeline/orchestrator.py:5790–6104` — `run()` main loop, follow-up window logic, addressing gate
- `src/kenning/audio/_relay_intent.py:1–243` — `RelayIntentGate`, `RELAY_POSITIVE_EXEMPLARS`, `RELAY_NEGATIVE_EXEMPLARS`, `relay_intent_ok()`
- `src/kenning/observations/integrations.py:61–88` — `observe_addressing_verdict()` schema
- `tests/test_addressing.py` — 50-utterance binary ground truth test set
- `tests/error_recovery/test_addressing_failures.py` — failure-mode tests
- `tests/integration/test_addressing_pipeline.py` — pipeline integration tests
- `tests/test_addressing_third_party_possessive.py` — possessive-question guard tests
- `scripts/review_addressing.py` — JSONL decision log viewer
- `docs/ultron_1_0/01_recon/raw/boardA_addressing.md` — static-structure map (complement)
- `docs/ultron_1_0/01_recon/raw/boardA_semantic_router.md` — relay-intent gate + semantic router
- `docs/ultron_1_0/01_recon/raw/boardA_orchestrator_dispatch.md` — dispatch decision-tree
- Git commit `9438fc5` — log-odds fusion design (NOT on HEAD; ephemeral branch)
- Git commit `ad186cf` — disable follow_up_enabled (wake-word-required hotfix)
- Git commit `0b5da79` — re-add blunt `_FOLLOWUP_WAKE_RE` bypass
