# A4: Normalization layers L1 (STT-correct) & L2 (command-normalize)

> Recon agent: claude-sonnet-4-6 | Date: 2026-06-20 | Branch: claude/infallible-kepler-0a865d

---

## Overview

Every raw STT transcript passes through two normalization layers before any matcher (relay, Spotify,
identity, desktop) or the semantic router ever sees it. The goal is to produce a *canonical command
string* — correct Valorant vocabulary, explicit relay lead, no wake-word artifact — while leaving
conversational, Spotify, and identity text completely untouched.

- **L1 (STT-correct)** lives in `_stt_correct.py` and is called `correct_callout_stt`. It repairs
  Valorant vocabulary: agent names, abilities, locations, weapons, and tactical terms. It is
  deliberately *not* called on conversational text (the L2 zero-mistakes gate prevents that).
- **L2 (command-normalize)** lives in `command_normalizer.py` and is called `normalize_command`. It
  is the single entry-point the orchestrator calls. It strips leading junk (wake-remnants, fillers),
  canonicalizes a mangled/dropped relay-verb lead, strips discourse scaffolding, resolves
  disfluency/self-correction, then calls L1 on callout-bound text, and finally runs relay-lead
  recovery.

A third, earlier, pass — **`_strip_leading_wake_remnant`** in `orchestrator.py` — runs as a
*text-level fallback* applied selectively by the orchestrator (Spotify match retry, relay-command
build) and is NOT the same as L2's `_strip_leading_junk`. They share a family resemblance but have
distinct scope and `_WAKE_MISHEAR` vs `_WAKE_HOMOPHONES` sets.

All normalization data (gazetteer, mishear maps, lead regexes, routing thresholds) is canonically
defined in **`routing_rules.py`** (Sections 1, 2, 3) and imported by `_stt_correct.py` and
`command_normalizer.py` with aliases.

---

## Files & key symbols (path:line tables)

| File | Role | Key symbols |
|---|---|---|
| `src/kenning/audio/routing_rules.py` | Single source of truth for all normalization DATA | `AGENTS` (L:47), `MAPS` (L:53), `WEAPONS` (L:57), `ABILITIES` (L:63), `LOCATIONS` (L:74), `TERMS` (L:82), `AGENT_MISHEARS` (L:92), `TERM_MISHEARS` (L:137), `MISHEAR_FORCE` (L:149), `FUZZY_BLOCK` (L:156), `PROTECT_EXTRA` (L:180), `MULTI_TERMS` (L:186), `NORM2_TEAM_NOUN` (L:211), `NORM2_MANGLED_TELL` (L:216), `NORM2_TELL_CLASS_VERB` (L:227), `NORM2_MANGLED_TEAM_LEAD_RE` (L:235), `NORM2_IRREGULAR_TEAM_LEAD_RE` (L:239), `NORM2_TELL_TEAM_LEAD_RE` (L:252), `ROUTE_DEFAULT_THRESHOLD` (L:268), `ROUTE_DEFAULT_MARGIN` (L:269), `ROUTE_FAMILY_THRESHOLDS` (L:270) |
| `src/kenning/audio/_stt_correct.py` | L1 STT correction engine | `correct_callout_stt` (L:459), `_phonetic_fuzzy_snap` (L:277), `_fix_token` (L:353), `_slot_agent_correct` (L:440), `_CONTEXT_RULES` (L:107), `_PHRASE_MISHEARS` (L:138), `_PHONETIC_INDEX` (L:90), `_GAZ_LOWER` (L:77), `_AGENT_LOWER` (L:86), `_MISHEARS` (L:127), `_MISHEAR_FORCE` (imported from routing_rules), `_FUZZY_BLOCK` (imported), `_COMMON_WORDS` (L:52), `_PROTECT_EXTRA` (imported), `_MULTI_TERMS` (imported) |
| `src/kenning/audio/_common_words.py` | 4771-word frozenset protecting real English words | `COMMON_WORDS` (L:10) — top-5000 Google-10k-english alpha-only len≥3 |
| `src/kenning/audio/command_normalizer.py` | L2 command normalization entry-point | `normalize_command` (L:975), `recover_relay_lead` (L:904), `_strip_leading_junk` (L:121), `_canonicalize_directive_lead` (L:215), `_strip_scaffold` (L:293), `_resolve_disfluency` (L:428), `_resolve_value_swap` (L:405), `_strip_possessive_names` (L:464), `_collapse_multi_addressee` (L:489) |
| `src/kenning/audio/routing_rules.py` (Section 3) | Routing thresholds / family overrides | `ROUTE_DEFAULT_THRESHOLD=0.50`, `ROUTE_DEFAULT_MARGIN=0.06`, `ROUTE_FAMILY_THRESHOLDS` (per-family) |
| `src/kenning/audio/_relay_intent.py` | Semantic relay-intent gate called by `recover_relay_lead` | `relay_intent_ok` (L:241), `RelayIntentGate` (L:158), `RELAY_POSITIVE_EXEMPLARS` (L:35), `RELAY_NEGATIVE_EXEMPLARS` (L:69) |
| `src/kenning/pipeline/orchestrator.py` | Call site + wake-remnant text-level strip | `normalize_command` call (L:6131), `_WAKE_REMNANT_RE` (L:194), `_WAKE_MISHEAR` (L:183), `_strip_leading_wake_remnant` (L:226), `_FOLLOWUP_WAKE_RE` (L:208) |

---

## Control/data flow

### Full pipeline for one STT transcript

```
RAW STT TEXT (from Whisper/Moonshine)
       |
       v
[Orchestrator pre-check: _WAKE_REMNANT_RE on raw text]
   -- if entire transcript is wake-word-only -> discard (routing:wake_word_only) [orch:6037]
       |
       v
[Orchestrator: normalize_command(user_text)]  [orch:6131]
       |
       v  ← command_normalizer.normalize_command (L:975)
       |
  (A) Bare-greeting check [L:990]
      -- _BARE_GREETING.match(raw) → return raw verbatim (never corrected, never relayed)
       |
  (B) _strip_leading_junk(raw) [L:992]
      -- iteratively strip _LEADING_JUNK: wake-homophones + fillers + "like" (Spotify guard)
      -- _WAKE_HOMOPHONES: ultron|ultra|tron|ron|run|rons|voltron|oltron|ultraun...
      -- _FILLER: hey|ok|um|uh|please|alright|bro|bruh|yo|... + 2026-06-16 broadened list
       |
  (C) _RUNON_TEAM_LEAD_RE.sub [L:998]
      -- "Tellmyteam" / "Askmyteam" (no spaces) → "tell my team " / "ask my team "
       |
  (D) _REPEAT_MISHEAR.sub [L:1004]
      -- "Pete/peat/heat/repeet to" → "repeat to"
       |
  (E) _TEAM_POSSESSIVE.sub [L:1005]
      -- "my team's" → "my team" (drops possessive "'s" on team noun)
       |
  (F) _canonicalize_directive_lead(s) [L:1011]
      -- outer lead is a valid team verb (_ANY_TEAM_LEAD_OUTER_RE) → keep verb, strip stacked
         inner leads via _strip_stacked_team_leads (loops ≤3)
      -- outer lead is mangled (_MANGLED_TEAM_LEAD_RE) or irregular (_IRREGULAR_TEAM_LEAD_RE)
         → rewrite to "tell my team " + stripped payload
      -- MANGLED_TELL set (from routing_rules.NORM2_MANGLED_TELL): calls|called|holds|help|
         helps|builds|while|how|puts|don't|without|tale|tales|fell|filled|hail|paul|y'all|
         told|sell|tal|tel|kel|whilst|hauled|valorant|tellin'|telling|hope|hopes|hoped
      -- IRREGULAR_TEAM_LEAD_RE: "that's the team" / "this is the team"
       |
  (G) _GIVE_TEAM_TO_RE.sub [L:1014]
      -- "give my team to <verb>" → "tell my team <verb>"
       |
  (H) _DROP_POSSESSIVE_RE.sub [L:1017]
      -- "drop me his/her/their X" → "drop me your X"
       |
  (I) _BARE_ASK_RE.sub [L:1020]
      -- "ask <question-word>..." → "ask my team <question-word>..."
       |
  (J) _SOMEONE_LEAD_RE.sub [L:1021]
      -- "tell/ask someone to X" → "tell my team someone X"
       |
  (K) _strip_scaffold(s) [L:1026]
      -- (3a) numbered prefix strip: "1. " / "2) " / "first, " (then rest must be relay-led)
      -- (3c) say-directive / wrapper lead → "tell my team X" (R2-gated: skip if remainder
         is question/Spotify/musing/reported-reaction/think-respond)
         _SAY_DIRECTIVE: "can you say X", "should relay X", "go ahead and say X"...
         _WRAPPER_LEAD_RE: "make sure my team knows that X", "let them know that X",
           "give the team a heads-up that X", "shout out that X", "pass along that X"
      -- (3b) nested relay verb strip (only when outer relay frame already confirmed),
         guarded by _TEAM_AS_SUBJECT_RE so a context clause doesn't eat a real directive
      -- (3d) embedded filler loop (≤4 passes): "-- uh -- kind of --" → ""
       |
  (L) _WORD_FOR_WORD match [L:1027]
      -- "tell my team word for word X" / "verbatim X" → "say exactly to my team X"
       |
  (M) _resolve_disfluency(s) [L:1033]
      -- if _DISFLUENCY_CUE_RE present: split on _DISFLUENCY_SPLIT_RE, take tail, preserve
         relay lead ("tell my team " prepended if tail is bare but original had relay lead)
      -- cues: "--wait", "no wait", "no no", "scratch that", "never mind", "forget it",
         "actually no", "or rather", "i mean", "--no", "--actually", "--to all/the",
         "well no", "no actually", "i don't know"
      -- else: _resolve_value_swap (bare "--" repair only for head-verb repeat or buy-class)
       |
  (N) _strip_possessive_names(s) [L:1034]
      -- "relay to my Sova" → "relay to Sova"; "and my Fade" → "and Fade"
       |
  (O) _collapse_multi_addressee(s) [L:1035]
      -- "tell Jett and Sova X" (both ROSTER names) → "tell my team X"
       |
  (P) ZERO-MISTAKES GATE [L:1042]
      -- if _NOT_A_CALLOUT.match(s) → return s (no L1 correction)
      -- if _SPOTIFY_SIGNAL.search(s) → return s
      -- if _REPORTED_QUESTION_GATE.match(s) → return s
      -- if _REPORTED_REACTION_RE.match(s) AND classify_social_reaction(s) is not None → return s
      -- if THINK_RESPOND_SUFFIX_RE.search(s) → return s
       |
  (Q) correct_callout_stt(s)  ← L1 entry point [L:1048]
      |
      v  ← _stt_correct.correct_callout_stt (L:459)
      |
      Stage 0: _PHRASE_MISHEARS substitution (multi-word blends) [L:467]
          Examples: "ray zombie"→"Raze on B", "ar sova"→"our Sova", "toast my team"→"roast",
          "bee main"→"B main", "won mid"→"one mid", "tree pushing"→"three pushing",
          "recon dart"→"recon bolt", "black window"→"Black Widow"...
          (38 patterns as of recon date)
      |
      Stage 1: _CONTEXT_RULES substitution [L:471]
          _ULTISH=old|sold|alt|oat|halt|vault|ault... →
            "has/have/got/using ult-like" → "has/have/got/using ult"
            "ult-like up/ready" → "ult up/ready"
          site-letter normalization: "site a"→"A site"; "a main"→"A main"; "on a"→"on A"
          (6 patterns)
      |
      Stage 1.5: _slot_agent_correct(text) [L:474]
          -- override common-word protection for agent names in characteristic SLOTS:
             _SLOT_HIT_RE: "<tok> hit/tagged/chunked/dinked/cracked/wiped/clipped <damage>"
               → snap <tok> to nearest agent at JW≥0.82
             _SLOT_HIT_OBJ_RE: "hit/tagged the <tok> for <N>"
               → snap <tok>
             _SLOT_SIDE_RE: "their/enemy/our/the <tok> ulted/mollied/walled/smoked/darted..."
               → snap <tok>
          (Only override for agent slot; knowledge of context confirms ambiguous common words)
      |
      Stage 2: token-level _fix_token via _WORD_RE.sub [L:476]
          For each alpha token:
            (a) contraction guard: if "'" in tok and tok not in _MISHEARS → return tok
            (b) _MISHEARS lookup (AGENT_MISHEARS + TERM_MISHEARS merged):
                if tok in _MISHEARS AND (tok not in _COMMON_WORDS OR tok in _MISHEAR_FORCE)
                → return canonical
            (c) _GAZ_LOWER direct hit (already canonical):
                if tok in _PROTECT_EXTRA AND not forced → return tok (prevent mangling payloads)
                else → return _GAZ_LOWER[tok]
            (d) _phonetic_fuzzy_snap:
                -- len<3 OR in _FUZZY_BLOCK OR in _COMMON_WORDS OR in _PROTECT_EXTRA → None
                -- inflected guard: -ed/-ing/-ers len≥5 → None; -s plural with stem in
                   _COMMON_WORDS or _GAZ_LOWER → None
                -- Phonetic: jellyfish.metaphone(tok) → lookup _PHONETIC_INDEX (code→canonicals)
                  if unambiguous (1 candidate) → phon_hit
                -- Fuzzy: rapidfuzz JaroWinkler over _GAZ_KEYS; score≥0.92 → fuzzy_hit
                -- Decision: (phon_hit corroborated by JW sim ≥0.88) OR (fuzzy_score ≥0.92)
                  AND NOT _is_oov_superstring (prevents "omenix"→Omen etc.)
                → snap or None (token unchanged)
       |
       v  back in normalize_command
  (R) KAY/O artifact fix [L:1052]
      -- "KAY/O O" → "KAY/O" (STT renders "Kay O" as two tokens; corrector snaps "Kay"→"KAY/O",
         leaving stray "O")
       |
  (S) recover_relay_lead(s) [L:1053]
      -- if _HAS_RELAY_LEAD.match(s) → return s (already led)
      -- if _NOT_A_CALLOUT.match(s) → return s
      -- if _REPORTED_RESPOND_RE.search(s) → return s (context+directive → in-char answer path)
      -- if _WANT_TEAM.match(s): "I want my team to X" → "tell my team X"
         (vetoed if _NARRATION_MUSING_RE or relay_intent_ok returns False)
      -- if _TRAILING_RELAY_TAIL.search(s): "X, tell my team." → "tell my team X"
      -- if _TEAM_LEAD_NOVERB.match(s): "on my team X" → "tell my team X"
      -- if _TEAM_LEAD.match(s): "my team X" → "tell my team X"
      -- if _STRONG_CALLOUT_RE.match(s) AND NOT _NARRATION_MUSING_RE → "tell my team " + s
         (sound info / enemy-comp / count+loc / spike shapes; bypass semantic gate)
      -- if _CALLOUT_SIGNAL.search(s) OR _AGENT_SIGNAL.search(s):
           if _NARRATION_MUSING_RE → return text (conversational)
           verdict = relay_intent_ok(s)  ← SEMANTIC GATE (embeddinggemma sidecar)
             True → prepend "tell my team "
             False → return text (conversational)
             None (sidecar down) → prepend "tell my team " (keyword behavior fallback)
       |
       v
NORMALIZED COMMAND STRING (returned to orchestrator)
  → used as user_text from L:6142 onward for all downstream matching
```

### Orchestrator-level text-level wake strip (_strip_leading_wake_remnant)

Separate from L2. Applied by the orchestrator as a *fallback* in two places:
1. Spotify retry [orch:2998]: if Spotify match fails on `user_text`, retry with `_strip_leading_wake_remnant(user_text)`.
2. Relay command build [orch:3468]: `stripped = _strip_leading_wake_remnant(user_text)` used to build variant list for relay command.

`_WAKE_REMNANT_RE` [orch:194] pattern:
```
^\s*(?:ultron|ultra(?:n|m)?|altron|all[\s-]*tron|run|ron|tron|trond|front|fron|one|won|wun|
ulton|olt?ron|elt?ron|to|too|two|yeah|yep|yes|yup|ok|okay|so|well|um|uh|hey|alright|nah|now)
\b[\s.,!?:;]*(?:(?:to|and|then|and\s+then|um|uh)[\s,]+)?
```
Iterates up to 3 times to strip stacked prefixes. Preserves a standalone wake word (never empties string).

`_FOLLOWUP_WAKE_RE` [orch:208]: `^\s*(?:hey[\s,]+)?(?:ultron|kenning)\b` — narrow set, only real wake words, used for follow-up window leading-wake addressing override.

---

## Key findings

1. **Two distinct wake-strip passes exist and serve different roles.** L2's `_strip_leading_junk` (`_WAKE_HOMOPHONES` + `_FILLER`) runs inside `normalize_command` on every turn. The orchestrator's `_strip_leading_wake_remnant` (`_WAKE_MISHEAR` set) runs selectively as a fallback. They partially overlap but are NOT the same regex or the same timing.

2. **`routing_rules.py` is the single data source of truth for both layers.** All gazetteer groups (AGENTS, MAPS, WEAPONS, ABILITIES, LOCATIONS, TERMS), both mishear maps (AGENT_MISHEARS, TERM_MISHEARS), the protection sets (MISHEAR_FORCE, FUZZY_BLOCK, PROTECT_EXTRA), the lead-recognition regexes (NORM2_*), and routing thresholds live there. `_stt_correct.py` and `command_normalizer.py` import and alias them.

3. **L1 is only called on callout-bound text.** The zero-mistakes gate (step P in the pipeline) routes questions, Spotify, reported-reactions, and think-respond text back verbatim BEFORE `correct_callout_stt` runs. This is critical: aggressive phonetic/fuzzy correction would corrupt song titles, Marvel character names, and conversational English.

4. **L1 has four correction stages in order:** phrase mishears (multi-word blends) → context rules (ult disambiguation + site-letter normalization) → context SLOT confirmation (agent name overrides common-word protection in damage/side slots) → token-level (curated map + phonetic + fuzzy with layered protection).

5. **Common-word protection is layered:** `_COMMON_WORDS` (4771-word frozenset, primary barrier), `_FUZZY_BLOCK` (hand-curated denylist including some agent names like raze/sage/neon/iso that overlap common English), `_PROTECT_EXTRA` (payload/kit words the gaz-direct branch would mangle). `_MISHEAR_FORCE` is the escape hatch that overrides `_COMMON_WORDS` for known STT mishears (jet→Jett, sky→Skye, race→Raze, etc.).

6. **Agent-slot confirmation overrides common-word protection in context.** `_slot_agent_correct` runs on damage-report/side slots ("`<tok>` hit 18", "their `<tok>` ulted") and applies JW≥0.82 fuzzy snap without the common-word guard. This is the ONLY place the common-word protection is overridden.

7. **Relay-lead recovery has a semantic gate.** `recover_relay_lead` gates the bare-callout branch (step S) through `relay_intent_ok`, which calls the embeddinggemma sidecar (`RelayIntentGate`). The gate is **fail-open** (sidecar down → keyword behavior). Threshold is cosine margin ≥0.06 (positive exemplar max − negative exemplar max). Strong callout shapes (`_STRONG_CALLOUT_RE`) bypass the gate entirely.

8. **Relay-lead preservation across disfluency.** `_resolve_disfluency` explicitly re-prepends "tell my team " to the post-correction tail when the original had a relay lead but the tail does not. This prevents a self-correction from losing the routing context.

9. **The `_NARRATION_MUSING_RE` is the primary false-relay suppressor** before the semantic gate. It catches first-person modals ("I should tell them", "I told my team X", "I'd ask", "I'm going to tell"), recount forms, and detached-musing frames. Start-anchored to avoid gating real self-status callouts ("I'm planting", "I died").

10. **`normalize_command` is idempotent on already-clean text.** Tested by the corpus harness (482 tests); every sub-step no-ops when its pattern is absent.

11. **AGENTS gazetteer has 30 entries.** Includes new agents Tejo, Waylay, Miks, Veto (added recently). AGENT_MISHEARS has ~80 curated wrong→right entries. KAY/O is treated specially (slash removed for matching: "KAYO").

12. **Phonetic library is optional (`jellyfish`).** Fuzzy library is optional (`rapidfuzz`). Both fall back gracefully: `difflib.get_close_matches` (cutoff 0.84) is used when rapidfuzz is absent. Phonetic index is empty if jellyfish is missing.

---

## Flags & config

| Name | Type | Default | Effect | Source |
|---|---|---|---|---|
| `KENNING_SNAP_REGISTRY` | env var | `"1"` (on) | Gates data-driven `SNAP_REGISTRY` / `SnapRule` dispatch in relay_speech | relay_speech.py:2801 |
| `KENNING_SNAP_EARLY_ENDPOINT` | env var | off | Closes capture early on a recognized complete slot-callout | relay_speech.py:5987 |
| `KENNING_RELAY_TEAM_DSP` | env var | off | Enables audio DSP shaping for team-path relay lines | relay_speech.py |
| `KENNING_RELAY_VM_LEVEL_GUARD` | env var | off | Boot VoiceMeeter B1 level guard | audio/voicemeeter_level.py |
| `KENNING_ADDRESSING_TAU` | env var | `0.20` | Addressee classifier cost-asymmetric threshold | addressing/classifier.py |
| `KENNING_WAKE_TRIM_TO_SPEECH` | env var | off | VAD-based wake-word audio removal from capture | orchestrator.py |
| `addressing.follow_up_enabled` | config.yaml | `false` | Follow-up window (wake-free re-address) | config.yaml, orchestrator |
| `push_to_talk.enabled` | config.yaml | `false` (repo default); `true` in local | PTT hardware hold | config.yaml |
| `testing_mode.enabled` | config.yaml | `false` | Enables full-flow usage logs (logs/usage_trace.jsonl) | config.yaml |
| `ROUTE_DEFAULT_THRESHOLD` | routing_rules.py:268 | `0.50` | Min top-family score to commit semantic route | routing_rules.py |
| `ROUTE_DEFAULT_MARGIN` | routing_rules.py:269 | `0.06` | Min (top − runner_up) to commit | routing_rules.py |
| `ROUTE_FAMILY_THRESHOLDS` | routing_rules.py:270 | `{identity:0.55, spotify:0.50, team_callout:0.48, desktop_refuse:0.50}` | Per-family threshold overrides | routing_rules.py |
| Relay-intent gate `threshold` | `_relay_intent.py:166` | `0.06` | Margin for bare-callout relay decision | _relay_intent.py |

Note: `push_to_talk.enabled=true` and `testing_mode.enabled=false` are the REPOSITORY defaults. Local working copies may differ (the memory runbook notes these are NOT committed).

---

## Extension points

1. **Add a new Valorant agent:** Add name to `routing_rules.AGENTS` (L:47). `_stt_correct` derives its phonetic index and lower-case map automatically from that tuple. Add known STT mishears to `routing_rules.AGENT_MISHEARS` (L:92). Add any common-English-like tokens that should override `_COMMON_WORDS` to `MISHEAR_FORCE`.

2. **Add a new STT multi-word blend fix:** Add a `(re.compile(pattern), replacement)` tuple to `_stt_correct._PHRASE_MISHEARS` (L:138).

3. **Add a new single-word term correction or ability term:** Add to `routing_rules.TERM_MISHEARS` (L:137) for wrong→right maps, or to the relevant vocabulary tuple (ABILITIES/LOCATIONS/TERMS/WEAPONS).

4. **Add a new "tell my team" STT mishear verb (e.g. STT keeps hearing "tall"):** Add to `routing_rules.NORM2_MANGLED_TELL` (L:216). The MANGLED_TEAM_LEAD_RE is built from it automatically.

5. **Add a new team noun synonym (e.g. "posse"):** Add to `routing_rules.NORM2_TEAM_NOUN` (L:211).

6. **Add a new relay-intent exemplar (positive or negative):** Add to `_relay_intent.RELAY_POSITIVE_EXEMPLARS` or `_relay_intent.RELAY_NEGATIVE_EXEMPLARS`. The embeddinggemma gate picks them up at next init.

7. **Tune routing thresholds:** Edit `routing_rules.ROUTE_DEFAULT_THRESHOLD`, `ROUTE_DEFAULT_MARGIN`, `ROUTE_FAMILY_THRESHOLDS` (L:268-275). Per-family overrides in `ROUTE_FAMILY_THRESHOLDS` dict.

8. **Add a common English word that the snapper is corrupting:** Add to `routing_rules.FUZZY_BLOCK` (L:156) or `PROTECT_EXTRA` (L:180). The distinction: `FUZZY_BLOCK` is for words that are also agent/ability names (raze, sage, etc.) and must stay literal; `PROTECT_EXTRA` is for payload/kit words the gaz-direct branch corrupts.

9. **Add a context rule (ult-disambiguation etc.):** Add a `(compiled_re, replacement_or_lambda)` tuple to `_stt_correct._CONTEXT_RULES` (L:107).

10. **Add a say-directive pattern (e.g. new leading scaffold form):** Add regex fragment to `command_normalizer._SAY_DIRECTIVE` (L:79) or `_WRAPPER_LEAD_RE` (L:102).

11. **Extend callout signal coverage (for relay-lead recovery):** Add tokens to `command_normalizer._CALLOUT_SIGNAL` (L:742) or shapes to `_STRONG_CALLOUT_RE` (L:818).

---

## Retire-not-remove candidates (u1.0)

Under Ultron 1.0's LLM-centric design, most of L2's *routing purpose* is retired (the LLM decides intent), but parts of L1 and L2 remain valuable as PREPROCESSORS that improve transcript quality before the LLM sees it.

| Component | Status in u1.0 | Notes |
|---|---|---|
| `correct_callout_stt` (L1) | **KEEP** — demoted to pre-LLM transcript cleaner | Agent/ability/location vocab correction is valuable for the LLM; a raw mishear "Silva" confuses it too. Call L1 on all text (relax the zero-mistakes gate), not just callouts. |
| `_PHRASE_MISHEARS` table | **KEEP** | Multi-word blend fixes apply regardless of routing path. |
| `_CONTEXT_RULES` + `_slot_agent_correct` | **KEEP** | Contextual snapping is useful for LLM prompts. |
| `_COMMON_WORDS` / `_FUZZY_BLOCK` / `_PROTECT_EXTRA` | **KEEP** | Protection sets are even more important now: the LLM must see real English intact. |
| `AGENT_MISHEARS` / `TERM_MISHEARS` | **KEEP** | Curated maps remain authoritative. |
| `_strip_leading_junk` / `_strip_leading_wake_remnant` | **KEEP** (possibly simplify) | Wake-remnant stripping must happen before the LLM prompt. Could merge the two passes. |
| `_canonicalize_directive_lead` + NORM2_* relay lead regexes | **RETIRE as router; KEEP as intent detector** | The "tell my team" canonicalization purpose is retired (LLM decides relay vs not). But these regexes are a fast, cheap, high-precision *relay-intent detector* that can inform the LLM's router prompt as a feature or be used to select the "relay" prompt template. |
| `_strip_scaffold` | **KEEP** | Numbered prefixes, nested relay verbs, embedded fillers should be stripped before the LLM sees the text. |
| `_resolve_disfluency` | **KEEP** | Self-correction resolution is useful for the LLM; it should not see the correction noise. |
| `recover_relay_lead` | **PARTIAL RETIRE** | The hard-prepend logic is retired (LLM decides). Keep `_NARRATION_MUSING_RE`, `_STRONG_CALLOUT_RE`, and the semantic gate as **intent-classification features** for the LLM router, not as text rewriters. |
| `relay_intent_ok` / `RelayIntentGate` | **REPURPOSE** | Demote from a gate that rewrites text to a gate that sets an intent feature for the LLM prompt template selection ("this looks like a relay"). |
| `_NOT_A_CALLOUT` / `_SPOTIFY_SIGNAL` / `_REPORTED_QUESTION_GATE` | **RETIRE as zero-mistakes gate; REPURPOSE as routing hint** | The blocking gate is not needed under LLM routing. Retain as lightweight "is this Spotify / is this a question" signals to select the correct prompt template. |
| `ROUTE_DEFAULT_THRESHOLD` / `ROUTE_FAMILY_THRESHOLDS` | **RETIRE** | These tune the current embedding-based semantic router, which is superseded by the LLM router. |
| `_CALLOUT_SIGNAL` / `_AGENT_SIGNAL` | **REPURPOSE as features** | Large regex sets; useful for fast "is this a callout?" feature before LLM call. |
| AGENTS/MAPS/WEAPONS/ABILITIES/LOCATIONS/TERMS gazetteers | **KEEP** | Feed into LLM prompt context, flavor libraries, slot extraction. |
| `NORM2_MANGLED_TELL` / `NORM2_TEAM_NOUN` | **REPURPOSE** | Use these to build a fast "relay-intent pre-filter" regex that can inform the LLM prompt routing with zero LLM cost. |

---

## Gotchas

1. **L2's `_strip_leading_junk` and the orchestrator's `_strip_leading_wake_remnant` are NOT the same.** They have overlapping but distinct token sets. `_strip_leading_junk` uses `_WAKE_HOMOPHONES` and is inside `normalize_command`. `_strip_leading_wake_remnant` uses `_WAKE_MISHEAR` (broader: includes "to", "too", "two", "tron", "one") and is a *fallback retry* in the orchestrator. Conflating them will break either the corpus tests or the live Spotify retry.

2. **The zero-mistakes gate (step P) protects the LLM's conversational path from aggressive Valorant correction.** Under u1.0, if L1 is applied to all text (as suggested under "Retire-not-remove"), the gate must evolve: rather than blocking L1, it should limit L1 to *pure vocabulary correction* (no relay-lead recovery). The current gate's boolean return (skip L1 entirely) is safe but conservative.

3. **`_BARE_GREETING` is checked on RAW text before junk stripping.** If checked after stripping, "hey there" would be stripped to "there" and the greeting gate would miss it. Any refactor must preserve this ordering.

4. **`_COMMON_WORDS` is a generated file** (rebuilt via `scripts/build_common_words.py`). It includes "iso", "harbor", "phoenix", "chamber", "jet", "race", "sky", "silver", "wise", "royal" — common English words that are ALSO agent names. The `MISHEAR_FORCE` set is the only way to override this protection for confirmed STT mishears of those names.

5. **KAY/O requires special handling throughout.** The slash is removed in matching (`a.replace("/", "")`) but preserved in display. The post-L1 KAY/O artifact strip [L:1052] is needed because STT renders it as two tokens. Any LLM prompt that names agents must handle "KAY/O" explicitly.

6. **The relay-intent gate is fail-OPEN.** If the embeddinggemma sidecar is down, `relay_intent_ok` returns `None`, and `recover_relay_lead` treats that as "relay it" (keyword behavior). This means the false-relay rate increases when the sidecar is down. Under u1.0, if the LLM IS the sidecar, this fail-open behavior becomes the desired path.

7. **`_NARRATION_MUSING_RE` excludes "I'm" self-status forms.** "I'm planting", "I died", "I'm low" are real callouts and must survive. The regex is anchored to modal forms ("I should/wish/can't/always/never/told/asked/..."). Any extension must not accidentally gate these live callouts.

8. **The `_PROTECT_EXTRA` set explicitly excludes "ego"** (so "ego"→"eco" STT fix stays) and "incendiary" (→"molly"). The comment in `_stt_correct.py:267` explains the live trade-off. Adding these to `_PROTECT_EXTRA` would disable useful corrections.

9. **Multi-addressee collapse `_collapse_multi_addressee` is order-dependent.** It requires `_strip_possessive_names` to have already run ("relay to my Sova and my Fade" → "relay to Sova and Fade" → then the multi-addressee collapse fires). The step order in `normalize_command` is load-bearing.

10. **Routing thresholds in `routing_rules.py` Section 3 tune the EXISTING embedding-based semantic router**, not L2 normalization. They are co-located in `routing_rules.py` for editability, not because they are part of the normalization pipeline.

11. **`_DISFLUENCY_SPLIT_RE` includes bare `--` as a split boundary** BUT only when an explicit disfluency cue (`_DISFLUENCY_CUE_RE`) is also present. A tactical callout with a bare em-dash ("rotate mid -- then push main") is never split by this.

---

## Open questions

1. **Under u1.0, should L1 (`correct_callout_stt`) run on ALL text or remain gated?** The zero-mistakes gate currently protects conversational text. If L1 runs on everything, agent names in questions ("should we pick Phoenix for Ascent?") would get correctly cased, but Spotify queries and song titles might get corrupted by fuzzy matching. A softer gate (skip only the fuzzy/phonetic snap, keep curated maps) might be the right middle ground.

2. **Who calls `normalize_command` in u1.0?** Currently the orchestrator calls it once per turn. Under LLM routing, does L2 run before the LLM router, before each specialized matcher, or not at all? The relay-lead canonicalization's purpose changes (it becomes an intent detector rather than a routing rewrite).

3. **Should the relay-intent gate (`RelayIntentGate`) migrate to the LLM router or be preserved as a fast pre-filter?** The embeddinggemma sidecar is already loaded; using it as a pre-filter before the 8B LLM call could save latency on non-relay turns.

4. **The `_WAKE_REMNANT_RE` in the orchestrator and `_strip_leading_junk` in L2 partially overlap.** Is there a unification path? Or is the redundancy intentional (belt-and-suspenders for different failure modes)?

5. **`COMMON_WORDS` contains "iso", "harbor", "phoenix", "chamber", "jet" as real English.** This means the fuzzy snapper never auto-corrects these without an explicit `MISHEAR_FORCE` or curated `AGENT_MISHEARS` entry. Under u1.0, should the LLM be given both the raw token and the MISHEAR_FORCE-corrected form as context?

6. **The `_NARRATION_MUSING_RE` has grown very large** (covering first-person past recount, intent-musing, general-statement, detached-musing, stream-chat address, etc.). Is it the right architectural shape (a single large regex) or should it be factored into a small fast-path for obvious cases + a slower classifier for borderline ones?

7. **`_SLOT_HIT_RE` / `_SLOT_HIT_OBJ_RE` / `_SLOT_SIDE_RE` use hard-coded slot grammar.** Under u1.0 with an 8B LLM, could slot extraction be done by the LLM itself (no explicit regex) and then used to confirm/correct agent names? Or does the regex approach remain useful as a pre-LLM commit?

8. **`PROTECT_EXTRA` is a small frozenset (12 entries) that protects kit/payload words from the `_GAZ_LOWER` direct branch.** As new agents and abilities are added, will this need ongoing curation? Is there a better structural approach (e.g., mark gazetteer entries as "ability" vs "tactical-verb" to prevent the confusion)?

9. **The `_WORD_FOR_WORD` → "say exactly to my team" rewrite** is a special path for verbatim/soundboard relays. How does this interact with u1.0's LLM-authored relay? Should verbatim mode bypass the LLM entirely and emit exactly the payload?

10. **The `_RESOLVE_VALUE_SWAP` (bare "--" correction for weapon/buy repeat)** only fires when no explicit disfluency cue is present. Are there live cases where the explicit cue fires but the token after the split boundary is very short (< 2 words) and the original is kept? The current guard returns the original if `len(tail.split()) < 2`.
