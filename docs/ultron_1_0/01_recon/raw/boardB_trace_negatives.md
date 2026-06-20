# B3: TRACE non-command paragraph, a ME-only question, and talking-to-someone-else

## Overview

This document traces three specific speech scenarios through the current Kenning/Ultron voice pipeline to show exactly where each is gated, dropped, or routed — and assesses the system's ability to distinguish intent categories under the Ultron 1.0 always-listening design.

**Scenario A:** A multi-sentence non-command paragraph (e.g., narration/stream commentary like "honestly I keep losing these duels. Their Jett is cracked. I should probably save this round.")

**Scenario B:** "Ultron, what map is this?" — a direct ME-only question with wake word, no relay intent.

**Scenario C:** Speech clearly aimed at a third party (e.g., a Discord friend): "Hey man, you should queue with us. We've got a good setup going."

---

## Files & Key Symbols

| Path | Role |
|---|---|
| `src/kenning/pipeline/orchestrator.py` | Main run loop, all gate logic, dispatch chain |
| `src/kenning/addressing/rules.py` | Rule-based addressing classifier (`classify()`, `AddressingDecision`) |
| `src/kenning/addressing/classifier.py` | `AddressingClassifier` — rule + zero-shot fusion |
| `src/kenning/addressing/zero_shot.py` | Flan-T5-small zero-shot fallback |
| `src/kenning/audio/relay_speech.py` | `match_relay_command()`, `_NARRATION_LEAD_RE`, `_NARRATION_MUSING_RE` (via command_normalizer) |
| `src/kenning/audio/command_normalizer.py` | `normalize_command()`, `recover_relay_lead()`, `_NARRATION_MUSING_RE` |
| `src/kenning/audio/_relay_intent.py` | `RelayIntentGate.decide()` — embedding-based relay guard |
| `src/kenning/audio/command_router.py` | Semantic command router (embedding similarity to exemplars) |
| `config.yaml` | `addressing.follow_up_enabled` (false), `addressing.warm_mode_duration_seconds` (30.0) |

### Key line references

| Symbol | File:Line |
|---|---|
| `run()` | orchestrator.py:5790 |
| Wake-word check gate | orchestrator.py:5937–5963 |
| Follow-up window gating | orchestrator.py:5895–5898 |
| Empty capture drop | orchestrator.py:5965–5972 |
| Wake-word-only drop (`_WAKE_REMNANT_RE`) | orchestrator.py:6026–6046 |
| Follow-up addressing gate entry | orchestrator.py:6052–6098 |
| `_FOLLOWUP_WAKE_RE` bypass | orchestrator.py:6067 |
| `_is_relay_command()` | orchestrator.py:3126 |
| `addressing.follow_up_enabled` config | config.yaml:892 |
| `_DIRECT_ADDRESS` (only "kenning") | addressing/rules.py:97–100 |
| `_PHONE_OPENERS` (NO rule) | addressing/rules.py:183–192 |
| `_THIRD_PARTY_NARRATIVE` (NO rule) | addressing/rules.py:140–165 |
| `_FACTUAL_QUESTION_STEMS` (YES rule) | addressing/rules.py:42–54 |
| `classify()` in rules.py | addressing/rules.py:207–307 |
| Zero-shot Flan-T5-small prompt | addressing/zero_shot.py:23–33 |
| `_NARRATION_MUSING_RE` | command_normalizer.py:860–901 |
| `_NARRATION_LEAD_RE` | relay_speech.py:1060–1089 |
| `_LEADING_RELAY_RE` | relay_speech.py:1097–1103 |
| `match_relay_command()` | relay_speech.py:1704–2047+ |
| `RelayIntentGate.decide()` | _relay_intent.py:158–200+ |
| Semantic router dispatch | orchestrator.py:6782–6883 |
| `_respond()` | orchestrator.py:8756 |
| `_build_response_stream()` | orchestrator.py:10031 |
| `_gaming_conversational_prompt()` | orchestrator.py:9006 |
| `ULTRON_GAMING_PERSONA` import | orchestrator.py:121–122 |

---

## Control/Data Flow

### Current system architecture (wake-word gated)

```
[IDLE] --(wake word fires)--> [CAPTURING] --(VAD end)--> [PROCESSING]
                                                               |
                                              STT (Moonshine / Whisper)
                                                               |
                                            Wake-word-only check (drop)
                                                               |
                                          [If in follow-up window]
                                        Addressing classifier check
                                          (ADDRESSED/NOT_ADDRESSED/UNCERTAIN)
                                                               |
                                              normalize_command()
                                                               |
                                            Intent recognizer (if enabled)
                                                               |
                                          Relay/Spotify/toggle/etc. matchers
                                                               |
                                          Semantic command router (embedding)
                                                               |
                                               _respond() -> LLM
```

**Critical fact for Ultron 1.0:** Currently `addressing.follow_up_enabled` is `false` (config.yaml:892). This means the addressing classifier is NEVER consulted. Every turn requires a wake word. There is NO mechanism to distinguish between-wake-word speech aimed at Ultron, at teammates, or at a Discord friend. All such speech is SILENTLY DISCARDED (never captured beyond the wake loop).

---

## Scenario A: Multi-sentence non-command paragraph

**Example:** "Honestly I keep losing these duels. Their Jett is cracked. I should probably save this round."

### Gate 1: Wake word requirement

The user must first say the wake word ("Ultron"/"Kenning") for any audio to be captured and processed. A bare narration paragraph with no wake word is NEVER processed — the run loop sits in `_wait_for_wake_word()` (orchestrator.py:6946) draining audio into the ring buffer, firing only when `WakeWordDetector` returns a hit.

**Current outcome:** If no wake word precedes this paragraph, it is dropped at the wake-loop level. Zero processing.

### Gate 2: Wake-word-only check (if wake was present)

If the user said "Ultron" and then launched into the paragraph, the audio from after the wake-word fire is captured by `_capture_utterance()`. The paragraph is then STT'd. Then:

At orchestrator.py:6037–6046, `_WAKE_REMNANT_RE.match(user_text)` checks if the WHOLE transcript is just a wake-remnant/filler. A paragraph will NOT match this (it has content after the wake). So the paragraph passes through.

### Gate 3: Follow-up window — DISABLED

With `follow_up_enabled: false` (config.yaml:892), the addressing classifier path (orchestrator.py:6052–6098) is NEVER entered for a captured utterance unless `came_from_follow_up` is True. With the flag off, `follow_up_until` stays `None` after each turn, so the follow-up branch (orchestrator.py:5895–5898) never fires. The paragraph is processed on the WAKE path only (orchestrator.py:6100–6101: `print(f"  you: {user_text}")`).

### Gate 4: normalize_command() — the narration guard

At orchestrator.py:6130–6143, `normalize_command(user_text)` is called. Inside `normalize_command()` (command_normalizer.py:975+), `recover_relay_lead()` is called:

1. `_NARRATION_MUSING_RE.match(s)` (command_normalizer.py:860–901) is checked. This RE matches paragraphs that start with first-person musings like "honestly I keep...", "I should...", "I wish...", "I keep...". For the example paragraph starting "Honestly I keep...", this RE FIRES (the prefix "Honestly" is in the leading-discourse list, and "I should" is in the musing body). Result: `recover_relay_lead()` returns `text` unchanged (command_normalizer.py:962–963).

2. Even if `_NARRATION_MUSING_RE` did not fire, `_NOT_A_CALLOUT` would also be consulted. For a paragraph ending with "I should probably save this round", the `relay_intent_ok()` call (via `_CALLOUT_SIGNAL` match) would consult the embedding gate, which should return False for a narration.

**The paragraph does NOT get a "tell my team" lead prepended.** It arrives at the relay matcher without a lead.

### Gate 5: Relay matcher — match_relay_command()

Called via `_maybe_handle_relay_speech()`. Inside `match_relay_command()` (relay_speech.py:1704+):

1. `_BARE_CLUTCH_RE`, `_BARE_ENCOURAGE_RE` — won't match a paragraph.
2. `_NARRATION_LEAD_RE.search(cleaned)` (relay_speech.py:1750) — for a multi-sentence paragraph with "I keep losing" and "I should probably save", this FIRES (the pattern matches `\bi\s+(?:should|...|keep)\b...\b(?:tell|telling|say|asking|relay)\b`). The narration matches. And `_LEADING_RELAY_RE.match(cleaned)` does NOT fire (paragraph doesn't start with "tell my squad"). Result: `match_relay_command()` returns `None`.

**The paragraph is NOT treated as a relay command.** Falls through to the rest of the dispatch chain.

### Gate 6: Semantic command router

At orchestrator.py:6782–6883, the semantic router routes via embedding similarity. For a musing paragraph, the router would score low similarity to relay exemplars and likely ABSTAIN (margin below threshold). The `_NARRATION_MUSING_RE` path in `recover_relay_lead()` (applied during normalization, step 4) also ensures the embedding gate is never asked whether a narration is a relay — it returns the text unchanged.

Even if the router sees the paragraph, it would likely classify it as CONVERSATIONAL and let it fall through (abstain = no router handling at orchestrator.py:6869–6883).

### Gate 7: LLM fallback (_respond)

The paragraph falls through to `_respond()` (orchestrator.py:8756 via orchestrator.py:6901). The gaming persona (`_gaming_conversational_prompt()`, orchestrator.py:9006) is used if gaming/testing mode is active. The Ultron persona LLM answers the paragraph as if it were a question to Ultron. For "honestly I keep losing these duels..." this produces a conversational Ultron reply — the paragraph is treated as a ME-directed remark/question.

**Summary for Scenario A (with wake word):** Multi-sentence narration paragraph → passes wake gate → not caught by follow-up classifier (disabled) → normalization's `_NARRATION_MUSING_RE` fires and blocks relay-lead prepend → relay matcher's `_NARRATION_LEAD_RE` fires and blocks relay → semantic router abstains → falls to LLM → LLM answers as if user is talking to Ultron. This is WRONG behavior for true stream narration that isn't aimed at Ultron.

**Summary for Scenario A (no wake word):** Silently dropped at the wake-loop level.

---

## Scenario B: "Ultron, what map is this?" — ME-only question

### Gate 1: Wake word

"Ultron" at the start of "Ultron, what map is this?" is the wake word. `WakeWordDetector` fires. Audio is captured via `_capture_utterance()`.

### Gate 2: STT

The transcript produced is something like "Ultron, what map is this?" (or with STT mishear, possibly "what map is this?" after the pre-roll trim). The audio-domain wake-trim (`_trim_wake_from_capture`, orchestrator.py:248–297) cuts the wake-word audio; the text-level strip (`_strip_leading_wake_remnant`, orchestrator.py:226–245) may strip the leading "Ultron," text remnant.

### Gate 3: Wake-word-only check

"what map is this?" has `[A-Za-z0-9]` content after the wake-remnant — the check at orchestrator.py:6037–6046 does NOT drop it.

### Gate 4: Addressing — BYPASSED (wake path)

Since `came_from_follow_up = False` (the utterance came from the wake path, not the follow-up window), the addressing classifier is NOT called. orchestrator.py:6100: `print(f"  you: {user_text}")`. The question is accepted unconditionally.

### Gate 5: normalize_command()

`normalize_command("what map is this?")` runs:
- `_LEADING_JUNK` strip — nothing to strip.
- `correct_callout_stt()` — no Valorant vocab to correct.
- `recover_relay_lead()`:
  - `_HAS_RELAY_LEAD.match(s)` → false.
  - `_NOT_A_CALLOUT.match(s)` → this regex matches QUESTION forms at the front. "what map is this?" starts with "what" → `_NOT_A_CALLOUT` fires → returns `text` unchanged.

The question passes through normalization as-is.

### Gate 6: Relay matchers — all miss

`_maybe_handle_relay_speech("what map is this?")` → `match_relay_command()`:
- `_NARRATION_LEAD_RE.search()` — no musing pattern.
- Vocabulary scan, explicit relay verbs — none present.
- No callout keywords trigger. Returns `None`.

All deterministic matchers (Spotify, settings, stop button, etc.) also return False.

### Gate 7: Semantic router

The semantic router sees "what map is this?" — this matches CONVERSATIONAL (question to Ultron, not a team callout). Router either abstains or classifies as identity/conversational. Either way, `_router_consumed = False`.

### Gate 8: _respond() → LLM

Falls through to `_respond()`. With gaming mode active:
- `_gaming_conversational_prompt()` returns `ULTRON_GAMING_PERSONA` (the Ultron in-character system prompt, from `src/kenning/audio/llm_prompts.py`, imported at orchestrator.py:121).
- `_build_response_stream()` skips web search (gaming mode: `_barebones_skip_web_search()` → true) or classifies NO_SEARCH.
- LLM answers "what map is this?" as Ultron, responding on the DESKTOP/speaker channel.

**Result:** Correct behavior. "Ultron, what map is this?" is answered by Ultron on the desktop channel. No relay to teammates.

**Key observation:** This works ONLY because the wake word was present. In an always-listening design without a wake word, "what map is this?" would need to be distinguished from the same question someone says to their Discord friend — which the current system cannot do.

---

## Scenario C: Speech clearly aimed at a third party (Discord)

**Example:** "Hey man, you should queue with us. We've got a good setup going."

### Gate 1: Wake word — ABSENT

There is no wake word in this utterance. In the current system, the run loop (`_wait_for_wake_word()`, orchestrator.py:6946) will NOT be triggered. The audio flows through the ring buffer unprocessed.

**Current outcome:** The entire utterance is SILENTLY DISCARDED. The system never sees this speech.

### IF follow_up_enabled were True (hypothetical):

If `addressing.follow_up_enabled: true` (config.yaml:892) were set, and the user had spoken to Ultron within the last 30 seconds (`warm_mode_duration_seconds: 30.0`), THEN `_follow_up_listen()` (orchestrator.py:7600) would be running during the follow-up window, and this utterance would be captured by VAD and sent to the addressing classifier.

**Addressing classifier path (orchestrator.py:6052–6098):**

First, `_is_relay_command("Hey man, you should queue with us.")` → `match_relay_command()` — no relay pattern → returns False.

Then `_FOLLOWUP_WAKE_RE.match("Hey man, you should queue with us.")` (orchestrator.py:6067) → does NOT match ("hey man" is not "hey ultron"/"hey kenning").

So the addressing classifier is consulted:

1. **Rule layer** (`classify()` in rules.py:207–307):
   - `_PHONE_OPENERS.search(text)` at rules.py:228 → "Hey man" matches the pattern `hey\s+(?:dude|man|bro|...)` → returns `RuleHit(NOT_ADDRESSED, 0.92, "phone-call / interpersonal opener")`.
   - Confidence 0.92 >= `rule_confidence_threshold` (0.8) → short-circuits zero-shot.
   - Verdict: **NOT_ADDRESSED, conf=0.92, source="rule"**.

2. The verdict is NOT_ADDRESSED → orchestrator.py:6089–6098 → `continue` (the turn is discarded with log `addressing:rejected_follow_up`).

**Result for Discord scenario with follow-up enabled:** The `_PHONE_OPENERS` rule catches "Hey man" precisely and returns NOT_ADDRESSED at high confidence. This specific example IS handled correctly. The utterance is dropped.

### Gaps and limitations for the "talking to Discord" case:

However, consider a Discord conversation that does NOT use interpersonal openers:

**Example 2:** "You're a great player. I've been watching your stream."

- `_PHONE_OPENERS` — no match.
- `_THIRD_PERSON_MENTION` — no match.
- `_THIRD_PARTY_NARRATIVE` — "I've been watching" could match `_THIRD_PARTY_NARRATIVE` if followed by "him/her/it", but "your stream" doesn't have those pronouns.
- `_SECOND_PERSON_QUESTIONS` — no match (not a question).
- `_IMPERATIVE_VERBS` — no.
- `_FACTUAL_QUESTION_STEMS` — no.
- Falls through to zero-shot. Zero-shot prompt sees: "Are you directed at Kenning?" Context says 30 seconds since Kenning last spoke. Flan-T5-small would likely return UNCLEAR (it IS second-person "you" but aimed at a different person).
- With `zero_shot_addressed_min_confidence: 0.80` and heuristic confidence 0.75 for UNCLEAR → downgraded to NOT_ADDRESSED.

**Example 3:** "What do you think we should do?" (to a Discord friend)

- `_SECOND_PERSON_QUESTIONS` matches "do you" → `RuleHit(UNCERTAIN, 0.55)`. Below 0.8 → falls to zero-shot.
- Zero-shot: "You decide if this is directed at Kenning... 'What do you think we should do?'" → likely UNCLEAR at 0.50. With `default_uncertain_to_not_addressed: true` → NOT_ADDRESSED. Dropped correctly.

**Example 4:** "What time is the match?" (to Discord friend)

- `_FACTUAL_QUESTION_STEMS.match()` fires on "What time" → `RuleHit(ADDRESSED, 0.85)` → SHORT-CIRCUITS zero-shot → ADDRESSED verdict. This is a FALSE POSITIVE — the system would answer this as if addressed to Ultron.

This is the critical gap: the current rule set treats ALL factual question stems as ADDRESSED at high confidence regardless of whether the question is aimed at Ultron or at a Discord/room companion. The only protection is `_PHONE_OPENERS` (interpersonal openers) and `_THIRD_PERSON_MENTION` / `_THIRD_PARTY_NARRATIVE` patterns.

---

## Key Findings

1. **Wake word is the ONLY current gate for non-follow-up speech.** All three scenarios are trivially handled by the wake-word requirement: only wake-word-triggered utterances are processed. This means there is currently ZERO ability to distinguish to-me vs to-team vs to-others for unwaked speech — because all unwaked speech is discarded before any classifier runs.

2. **`follow_up_enabled` is FALSE by default (and in the current live config).** The addressing classifier exists, is wired, but is never invoked at runtime. It was disabled (config.yaml:886–892) because of live false-positives: 114 un-waked captures per session when enabled, with flan-t5 mis-accepting "Okay." and "Why is it suddenly running like this" as ADDRESSED.

3. **Scenario A (paragraph) with wake word correctly avoids relay but falls to LLM.** `_NARRATION_MUSING_RE` (command_normalizer.py:860–901) and `_NARRATION_LEAD_RE` (relay_speech.py:1060–1089) together block relay-lead prepend and relay-command match for first-person musing narration. The paragraph falls to the LLM which answers it as if it were addressed to Ultron — technically wrong for pure stream commentary, but benign in practice because the user said the wake word.

4. **Scenario B (ME-only question) works correctly on the wake path.** "What map is this?" passes through the relay gate (no relay signals), routes to the LLM with the Ultron gaming persona. The addressing classifier is irrelevant (wake path bypasses it at orchestrator.py:6100–6104, trace log `addressing:wake_word_path_no_classify`).

5. **Scenario C (Discord speech) is handled by `_PHONE_OPENERS` IF the follow-up window were active.** "Hey man" is a reliable interpersonal opener and is caught at rules.py:228 with 0.92 confidence. BUT this works only in the follow-up window, which is currently disabled.

6. **The `_DIRECT_ADDRESS` rule (rules.py:97–100) only recognizes "kenning", not "ultron".** This is a known bug documented in the `_FOLLOWUP_WAKE_RE` bypass comment (orchestrator.py:200–209). The fix applied was a text-level bypass (`_FOLLOWUP_WAKE_RE` at orchestrator.py:208–209 matches "ultron" or "kenning"), but that bypass lives in the orchestrator's follow-up path, not in the rule classifier itself. If the rule classifier were used more broadly (e.g., always-listening), "Ultron, show me the map" would NOT be caught by `_DIRECT_ADDRESS`, would fall to zero-shot, and might score 0.75 (below the 0.80 ADDRESSED threshold), causing a false-negative drop.

7. **The embedding-based `RelayIntentGate` (_relay_intent.py) fires on the relay path only.** It assesses whether a bare callout is team-relay-intent vs narration/banter. It is NOT used for to-me vs to-others classification.

8. **The semantic command router (command_router.py) also has no to-me vs to-others signal.** Its families are: `team_callout`, `identity`, `desktop_refuse`, and abstain-to-LLM. There is no "talking to a third party" family.

9. **The Flan-T5-small zero-shot model (zero_shot.py) is the only sub-LLM that handles genuine ambiguity**, but its prompt (zero_shot.py:23–33) frames the question as "is this directed at Kenning?" with only two context signals: recent conversation + seconds-since-response. It has no way to detect "talking to Discord friend" vs "talking to Ultron" except by surface cues in the text. Its confidence is heuristic (0.75 for YES/NO, 0.50 for UNCLEAR) and it fires only when the rule layer fails to reach 0.8.

10. **Multi-sentence utterances are not specially gated.** There is no "paragraph detector" — the system processes any STT transcript as a single unit regardless of sentence count, punctuation, or length. The narration detection works at the semantic level (first-person modal patterns), not at the structural level.

---

## Flags & Config

| Flag / Key | Location | Default | Effect |
|---|---|---|---|
| `addressing.follow_up_enabled` | config.yaml:892 | `false` | Master switch for the follow-up window and addressing classifier; `false` = wake word required for every turn |
| `addressing.warm_mode_duration_seconds` | config.yaml:895 | `30.0` | How long (seconds after last response) the follow-up window stays open |
| `addressing.default_uncertain_to_not_addressed` | config.yaml:896 | `true` | Treat UNCERTAIN classifier results as NOT_ADDRESSED (safe default) |
| `addressing.rule_confidence_threshold` | config.yaml:897 | `0.8` | Rule verdicts at or above this bypass zero-shot |
| `addressing.zero_shot_addressed_min_confidence` | config.yaml:904 | `0.80` | Zero-shot YES verdicts below this are downgraded to NOT_ADDRESSED |
| `addressing.zero_shot_model` | config.yaml:905 | `"google/flan-t5-small"` | Model used for ambiguous zero-shot classification |
| `addressing.load_eagerly` | config.yaml:906 | `true` | Load Flan-T5 at startup (~8s) vs lazy on first ambiguous utterance |
| `KENNING_WAKE_TRIM_TO_SPEECH` | env var | `"1"` (on) | Trim wake-word audio from capture before STT |
| `KENNING_WAKE_TRIM_GUARD_MS` | env var | `"200"` | Guard window (ms) before speech onset when trimming wake audio |
| `KENNING_FLAVOR_TAILS` | env var | `"1"` (on) | Enable in-character flavor tails on relay snaps |
| `KENNING_THINKING_MODE` | env var | `"0"` (off) | Whether relay compose path uses LLM or deterministic snaps |
| `KENNING_SNAP_REGISTRY` | env var | (deferred) | Enable data-driven snap registry |
| `KENNING_RELAY_TEAM_DSP` | env var | (default off) | Enable relay-path audio shaping for team voice |

---

## Extension Points

1. **`addressing/rules.py` — `classify()` function:** New NO rules for Discord/teammate speech can be added here by inserting pattern checks before the YES rules. E.g., a rule for "username, " patterns (Discord @-mentions read aloud), gaming-username-style openers, or Valorant agent names used as vocatives ("Clove, can you smoke?"). Each new rule is a `re.compile()` + `RuleHit` return.

2. **`addressing/rules.py` — `_PHONE_OPENERS` and `_THIRD_PARTY_NARRATIVE`:** These regexes can be extended with gaming-specific patterns. "Hey <Valorant_agent>", "yo Sova", "Reyna, rotate" as team-channel speech (not aimed at Ultron) could be added.

3. **`addressing/zero_shot.py` — `_PROMPT_TEMPLATE`:** The zero-shot prompt can be enriched with Valorant-specific context: "The user may be playing Valorant and may speak to teammates in game chat." This could improve discrimination between to-Ultron and to-teammate speech.

4. **`src/kenning/audio/command_normalizer.py` — `_NARRATION_MUSING_RE`:** Can be extended with new musing/narration patterns. Adding "to the chat", "for the viewers", "stream reacted", streaming-specific discourse frames.

5. **New intent gate: `to_self_or_third_party`:** An extension point could be added between the addressing classifier and the relay/LLM dispatch — a lightweight classifier that distinguishes (A) to Ultron, (B) to teammates (relay), (C) to Discord/stream/self, with the third category silently dropped or logged.

6. **`src/kenning/audio/_relay_intent.py` — `RelayIntentGate`:** The positive/negative exemplar lists can be extended. Adding Discord-conversation exemplars to `RELAY_NEGATIVE_EXEMPLARS` would help the gate reject Discord speech that contains Valorant vocabulary.

7. **`orchestrator.py` — the `run()` dispatch chain:** The `came_from_follow_up` → addressing classifier path is the main hook for always-listening behavior. An always-listening redesign would remove the follow-up window constraint and run the addressing classifier on ALL utterances, using a richer set of signals.

8. **`orchestrator.py:6067` — `_FOLLOWUP_WAKE_RE`:** Add "ultron" to the `_DIRECT_ADDRESS` rule in `rules.py` so the bypass in the orchestrator is no longer necessary and the rule layer handles it consistently.

---

## Retire-not-remove Candidates (u1.0)

For Ultron 1.0 (all responses via 8B LLM, always-listening), these components become ROUTERS rather than handlers:

1. **`match_relay_command()` (relay_speech.py:1704+):** Instead of dispatching directly, it becomes a router that fires when a relay-intent signal is strong, passing a structured `RelayCommand` to the LLM as a prompt template selector. The narration guards (`_NARRATION_LEAD_RE`, `_NARRATION_MUSING_RE`) should be PRESERVED and passed as negative signals to the LLM.

2. **`_NARRATION_MUSING_RE` and `_NARRATION_LEAD_RE`:** These are the primary guards against relaying stream narration. They should be KEPT as pre-LLM signal extractors and passed as features to the routing layer, not discarded.

3. **`RelayIntentGate` (_relay_intent.py):** KEEP as a lightweight embedding-based binary probe for relay-vs-narration, injected as a feature into the LLM prompt template selection.

4. **Addressing classifier (`classifier.py`, `rules.py`, `zero_shot.py`):** PROMOTE from follow-up-only to always-on (if wake word is optional). The rule-based layer is cheap and reliable for strong signals; the Flan-T5 zero-shot needs prompt enrichment for gaming context. Both should be extended for Discord/teammate discrimination.

5. **`_PHONE_OPENERS` rule:** RETIRE the current hardcoded list of interpersonal openers; REPLACE with a model-driven signal that handles gamer-specific openers ("bro", "dude", teammate names, Discord usernames).

6. **Semantic command router (`command_router.py`):** REPURPOSE as an intent signal extractor that feeds into the LLM prompt template selection (relay vs identity vs ME-only), not a terminal dispatcher.

7. **`_FOLLOWUP_WAKE_RE` bypass in orchestrator.py:6067:** RETIRE once `_DIRECT_ADDRESS` in rules.py is updated to include "ultron" alongside "kenning".

---

## Gotchas

1. **The addressing classifier is NEVER called in the current live config.** `addressing.follow_up_enabled: false` means the `AddressingClassifier` at `self.addressing` (orchestrator.py:1149) is constructed but never invoked at runtime. Reading the classifier code in isolation gives a false impression of its role.

2. **`_DIRECT_ADDRESS` does not recognize "ultron" as a wake-word vocative.** `rules.py:97–100` matches only "kenning". The orchestrator patches this via `_FOLLOWUP_WAKE_RE` (orchestrator.py:208–209), but only in the follow-up window. In always-listening redesign, this asymmetry must be fixed in rules.py.

3. **Wake-word-gated path BYPASSES the addressing classifier entirely.** orchestrator.py:6100–6104 logs `addressing:wake_word_path_no_classify`. Any speech post-wake-word is unconditionally accepted as addressed to Ultron, regardless of whether it might be directed at teammates or a third party mid-conversation.

4. **Flan-T5-small zero-shot confidence is hard-coded at 0.75 for YES/NO.** (zero_shot.py:131). With `zero_shot_addressed_min_confidence: 0.80`, ALL zero-shot YES verdicts are downgraded to NOT_ADDRESSED by the low-confidence gate (0.75 < 0.80). This means the zero-shot model currently NEVER produces an ADDRESSED verdict on its own — the only path to ADDRESSED in the follow-up window is via the rule layer (≥0.8) or the `_FOLLOWUP_WAKE_RE` bypass. This is likely unintentional or was temporarily tuned tightly to prevent the false-positive issue, but it makes the zero-shot fallback effectively a forced-NOT_ADDRESSED fallback for all borderline cases.

5. **Multi-sentence paragraphs that start with a factual question stem would be ADDRESSED.** "What's happening? They're rotating and I don't know why. Should I tell my team?" — the first sentence "What's happening?" would trigger `_FACTUAL_QUESTION_STEMS` at ADDRESSED 0.85 (>= 0.8) in the follow-up window, and the whole paragraph would be treated as directed at Ultron. The paragraph is NOT split into sentences; the system processes the whole STT transcript as one unit.

6. **The relay-intent gate (`RelayIntentGate`) only fires on the normalization/relay path.** It is NOT used to distinguish to-me vs to-others; it distinguishes team-relay-intent vs narration/banter within the relay routing layer. A Discord conversation that contains Valorant callout vocabulary would not be correctly rejected by this gate — only `_NARRATION_MUSING_RE` and `_NARRATION_LEAD_RE` patterns protect against narration-shaped relay false positives.

7. **The `_NARRATION_MUSING_RE` test is on the NORMALIZED text after leading junk strip.** If a paragraph's first person musing words are in the middle (e.g., "Jett is cracked, honestly I should save."), the RE (which is start-anchored via `^\s*`) would NOT fire. Only leading-position narration markers are caught.

8. **There is no structural paragraph detector.** The current system does not detect multiple sentences, does not look at punctuation patterns to classify "is this a monologue vs a command". A 5-sentence stream narrative would be treated identically to a 5-word callout.

9. **The `_PHONE_OPENERS` regex requires specific interpersonal openers.** Casual gamer-to-gamer speech often uses "bro", "dude", "man" without the "hey" prefix. "Bro rotate now" could be a Discord message or a team callout — `_PHONE_OPENERS` requires "hey bro" or "hi bro", not bare "bro". The normalizer's `_FILLER` list strips "bro" as a filler at the front, which means the relay path would receive "rotate now" — a valid callout that would be relayed. This is a false-positive risk.

---

## Open Questions

1. **Always-listening architecture:** In Ultron 1.0, if the wake word becomes optional and all audio is transcribed, how does the system decide whether each utterance is (A) to Ultron for a ME-only reply, (B) to Ultron to relay to teammates, or (C) to a third party (Discord/stream)? The current `AddressingClassifier` was designed for (A) vs everything-else in a post-wake-word context; it would need extension for three-way or even four-way classification.

2. **Zero-shot confidence calibration:** The Flan-T5-small model currently never reaches the 0.80 ADDRESSED threshold (it heuristically caps at 0.75). Should the `zero_shot_addressed_min_confidence` be lowered to 0.75? Or should confidence calibration be improved by replacing the heuristic with real token probabilities (as was done for `zero_shot.py:real first-token P(YES)` in a different branch mentioned in memory)?

3. **Wake word as a signal, not a gate:** Could the presence/absence of the wake word be used as a FEATURE (strong ADDRESSED signal) rather than a binary gate? This would allow always-listening while still treating "Ultron, ..." as a high-confidence to-me signal.

4. **Discord-specific signals:** Is there any audio-level signal that distinguishes Discord voice chat (comes through a different audio channel) from in-game voice (which is game-capture only)? If Discord audio and microphone audio go through separate routes, the distinction is trivial at the hardware level.

5. **Paragraph handling in the LLM prompt:** When a multi-sentence narration paragraph reaches the LLM, the gaming persona prompt tells Ultron to answer briefly and in-character. Should the 1.0 LLM detect "this is stream commentary, not a question" and respond accordingly (or stay silent)?

6. **The `_NARRATION_MUSING_RE` start-anchor limitation:** Should the narration musing check be anywhere in the utterance (not just at the start)? A command like "kill the Reyna, I should have done that sooner" starts with a legitimate callout but includes narration. Start-anchoring protects the callout; but a pure narration starting with a neutral phrase like "so we lost that round, I should probably adjust my play" would not be caught.

7. **Utterance splitting:** For Ultron 1.0's LLM-centric design, should a multi-sentence utterance be passed to the LLM as-is, or preprocessed to extract the command-like sentence from the narrative? The LLM with the right prompt template could do this reasoning natively.

8. **Relay exemplar sets for Discord speech:** The current `RELAY_NEGATIVE_EXEMPLARS` in `_relay_intent.py` include "tell Jordan to anchor B he's watching the stream" (out-of-roster named addressee). Should a Discord-conversation exemplar cloud be added to the relay-intent gate to reject team-relay-shaped Discord conversation?
