# Iteration 1 — comprehensive fix plan (personally synthesized from 8-agent line-by-line audit of 764 rephrase lines, ~56% flagged)

## Root cause
Architecture is already hybrid: `build_relay_line` routes verbatim → morale → greet/farewell →
calm → identity → known-fact → morale → consolation/praise → `_as_snap_callout` (DETERMINISTIC) →
LLM (off-snap, with `_repair_against_input`). The catastrophic failures all happen when a line
**falls through to the 3B LLM**, which is good at off-snap flavor but corrupts tactical facts.

## Failure modes (ranked, from the audit)
1. **COMPOUND COLLAPSE (#1, ~130 lines, CRITICAL).** `_as_snap_callout` returns None for compounds
   ("spike A, planted + Reyna has ult"); they hit the LLM, which keeps ONE fact / hallucinates filler
   ("Three souls stored", "Nice try. We take the next.", "They're switch."). Compounds = ~25% of corpus.
2. **OWNERSHIP/SUBJECT INVERSION (~30, CRITICAL).** our↔their, they↔we, "Vyse hit 84"→"84 to Vyse".
3. **DIRECTIVE↔OBSERVATION INVERSION (~15, CRITICAL).** "crossfire this corner"→"They're crossfire";
   "play it slow" (order)→"They're playing too slow" (enemy obs).
4. **FIRST-PERSON FLIP (~20, MAJOR).** "I'm rotating"→"Rotate"; "I have a good record"→"you've held".
5. **ECO TEMPLATE BLEED (~12, MAJOR).** "insufficient credits/we save" misfires on full buy, force buy,
   enemy-save, anti-eco, full retake, even a fun fact.
6. **FRAGMENT COLLAPSE (~20, CRITICAL).** multi-fact → "Defuse."/"Chamber"/"Mid.".
7. **OPINION MANGLING (~20, MAJOR).** dropped/argued/inverted ("ranked not fun"→"not a challenge for you").
8. **ASK/ANSWER + RESPOND (~20, MAJOR).** answered instead of posed; hallucinated cooldown numbers; wrong target.
9. **ABILITY-NAME drop/hallucination + ult-spent↔up (~25).** "Fade seize"→"tethered"; "just used ult"→"has ult".
10. **HALLUCINATED SPECIFICS (~15, CRITICAL).** "cage the entrance"→"Harbor, cage"; "Sage slow"→physics lecture(!).
11. **NANOSWARM WAIT collapse (~6, CRITICAL).** "wait 3s then defuse"→"Defuse." (defuser dies).
12. **OUTPUT ARTIFACTS (~10).** "Team:" prefix, wrapping quotes, raw echo.
13. **FLAVOR REPETITION (~40, MINOR).** Inevitable/Trivial/Insects/Hold the line/Nice try overused.
14. **LENGTH (~10).** identity/Marvel/calm/morale 40-65 words.
15. **CALM-DOWN not naming target (~8).** "Calm yourself." with no name / wrong invented name.

## Fixes (this iteration)
- **F1 COMPOUND DECOMPOSITION** (`_as_compound_callout`): split payload on safe connectors
  (`--`, `—`, `also`, `plus`, `, and `, ` and their/our `, conservative `,`/`and`), run EACH piece
  through `_as_snap_callout`; if ALL resolve, join with " ". Mixed (snap+off-snap) defers to LLM. → kills #1,#6 for tactical.
- **F2 SNAP EXTENSIONS** in `_as_snap_callout`: "<count> rotating [from X] to <place> [through Y]";
  ult-spent ("just used/fired/popped/dismissed ult"→"just used ult"); "has no ult"; plant status
  ("spike <place>, planted"); ensure defusing/planting are enemy actions. → #2,#9,#11 tactical.
- **F3 ECO DETERMINISTIC**: handle save/force/full-buy as deterministic buy/save lines (never LLM). → #5.
- **F4 ARTIFACT STRIP**: extend `_strip_artifacts` to drop leading "Team:/Ultron:/<Agent>:" labels + wrapping quotes. → #12.
- **F5 FLAVOR EXPANSION**: +20-30 tails per `_FLAVOR_*` pool, bigger encouragement/consolation/praise. → #13.
- **F6 PROMPT HARDENING** (residual LLM lines): ownership-lock, directive≠observation, opinion-relay,
  ult-spent, anti-hallucination ("you are in a Valorant match; never invent an agent/site/number/cooldown;
  never give real-world explanations"), respond=address named teammate, length<30, calm-name. → #3,#4,#7,#8,#10,#14,#15.
- **F7 REPAIR EXTENSION**: ownership-inversion (our↔their) in `_repair_against_input`; opinion first-person preserve.

## Validate
Re-run `harness --stage rephrase --limit 800` (same seed), compare flag rate, commit only if improved.
Then reshuffle (RELAY_CORPUS_SEED) for iteration 2.
