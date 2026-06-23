# Turbo Mode — spec (2026-06-23)

A flag-gated, **default-OFF** master switch that auto-relays *inferred* team callouts to the team
**without** a "tell my team" prefix. Additive, reversible, anticheat-clean; turbo-OFF is byte-identical
to today. User-requested + the two product forks were confirmed by the user:
- **Capture model:** *Turbo ON enables continuous (always-listening) capture* so the player can just talk;
  OFF returns to wake/keyword mode (stream/chat-safe).
- **False-positive posture:** *Balanced default* (relay clear callouts + directives; hold back the most
  ambiguous one-word/social lines), with a **live-tunable sensitivity** (voice + GUI).

## REQUIREMENTS (EARS)
- **R1** WHEN turbo mode is OFF (the default), the system SHALL behave exactly as today: only an explicit
  relay command (`tell my team X`, `ask <agent> Q`, `<agent> asked you Q`, `explain to <agent> X`,
  `tell/ask my team …`, the qa command) relays; normal speech does NOT relay.
- **R2** WHEN turbo mode is ON, the system SHALL listen continuously and SHALL relay an utterance it infers
  is a team callout (e.g. `sova hit 84`, `rotate`, `they are out B`, `planting A`, `one A main`,
  `sage do you have a heal`, `im saving`, `they have breach ult play off site`) to the team via the LLM,
  with no `tell my team` prefix.
- **R3** WHILE turbo mode is ON, the system SHALL still honor every explicit command and toggle (relay
  grammar, ask/tell-agent, verbosity/flavor/thinking/route toggles, the stop command, `turbo mode off`),
  and those SHALL take precedence over inferred callouts.
- **R4** The system SHALL route every turbo-relayed callout through the LLM (never a deterministic pure
  pool), consistent with route-all.
- **R5** The system SHALL expose turbo as a voice command (`turbo mode on` / `turbo mode off`) AND a button
  on the stop-button GUI, both flipping ONE shared runtime flag; default OFF at boot.
- **R6** The system SHALL expose a live sensitivity control (`turbo balanced` / `turbo aggressive`) trading
  recall vs false relays; default balanced.
- **R7** A false relay being the worst case, turbo SHALL keep the existing narration/musing + semantic
  relay-intent vetoes ON in balanced mode (aggressive opts into the semantic positives).

## DESIGN
**Chosen — Gate-flag reuse (minimal, contained).** Turbo is the opt-in to inference machinery that already
exists but is deliberately held back:
1. **Inference** lives in `intent_gate.classify_scenario` via a new `turbo` param threaded to
   `_relay_signal`. After the existing strict bands (strict matcher 0.95 / complete tactical 0.90 /
   agent+fact 0.88), the turbo branch runs the SAME normalizer the dispatch path uses
   (`command_normalizer.normalize_command` → `recover_relay_lead`) and returns RELAY (0.75) iff that
   recovers a team lead the strict matcher accepts. This guarantees a turbo RELAY verdict *always* relays
   downstream (no gate/dispatch mismatch), and `recover_relay_lead`'s narration/musing + semantic
   relay-intent vetoes still hold. Aggressive additionally relays a line the semantic relay-intent gate
   scores positive (0.60).
2. **Capture:** the run-loop effective always-listening becomes `addressing.always_listening OR
   turbo_mode_enabled()` (read live), so turbo ON drives the perpetual follow-up window + the 4-class gate.
3. **Dispatch is untouched:** once the gate keeps a callout-shaped line (not IGNORE), the EXISTING
   `normalize_command` → `recover_relay_lead` → `match_relay_command` → `_maybe_handle_relay_speech` path
   broadcasts it through the LLM. No new relay/broadcast code.
4. **Toggle + GUI + flag** clone the route-all flag stack (`relay_speech._u1_llm_route_enabled` triplet,
   `match_*_toggle`, the dual-path dispatch wiring) and the PTT stop-window button verbatim.

**Alternative A — New orchestrator relay handler on RELAY_TO_TEAM.** Add a `_maybe_handle_relay_from_scenario`
mirroring `_maybe_handle_private_reply` that force-relays a bare RELAY_TO_TEAM callout. Rejected: duplicates
the relay broadcast plumbing the normalize→recover→match path already provides; risks gate/dispatch drift.

**Alternative B — Loosen `_relay_signal`'s strict thresholds globally / promote `relay_intent_ok` as a
positive signal unconditionally.** Rejected: changes always-listening behavior even when turbo is OFF, and
re-introduces the exact false-relay regression hardened away on 2026-06-21 (`e085d0d`).

## Touch points
- `audio/relay_speech.py`: `_turbo_mode_enabled` / `set_/get`, `_turbo_aggressive` / `set_/get`,
  `match_turbo_toggle`, `match_turbo_sensitivity`; `__all__`.
- `audio/intent_gate.py`: `_relay_signal(..., turbo=False)` turbo branch; `classify_scenario(..., turbo=False)`.
- `pipeline/orchestrator.py`: `_classify_always_listening` passes turbo; run-loop effective-always-listening
  (`_listening_now()`); boot-apply; `_maybe_handle_turbo_command`; dual-path dispatch wiring;
  StopButtonOverlay wiring + `_set_turbo_runtime_enabled`.
- `audio/stop_button.py`: TURBO toggle button (clone of PTT).
- `config.py`: `RelaySpeechConfig.turbo_mode`/`turbo_aggressive` (default False);
  `StopButtonConfig.turbo_height`/`turbo_label`. `config.yaml`: the same defaults.
- `KENNING_TURBO_MODE` / `KENNING_TURBO_AGGRESSIVE` env overrides (mirror the u1.0 flags).

## Out of Scope (≥3)
1. Calibrating the gate / relay-intent thresholds against a labeled battery (turbo inherits the current
   uncalibrated heuristics; a calibration pass is a separate, user-gated effort).
2. A new ML classifier — turbo composes existing CPU/sidecar machinery only (anticheat envelope).
3. Persisting the live turbo toggle across restarts (matches every other runtime toggle; resets to the
   config/env default at boot).
4. M8 latency work for the extra in-gate normalize pass (idempotent + cheap; optimization deferred).

## Open Questions
- Should the in-gate `normalize_command` result be threaded to dispatch to avoid the (cheap) double pass?
  Deferred — correctness first; idempotent and microsecond-scale.
- Does the GUI button need live re-sync of its displayed state on reopen (it reads the config default at
  construction, like PTT)? Accepted limitation, matches PTT.

## Adversarial review (2026-06-23) — findings + resolution
A fresh-context 4-agent review (correctness/precedence, anticheat, default-OFF byte-identity) ran on the diff.
Anticheat/stub/persona dimension: SOUND (no new import surface; tkinter stays lazy; no global key hook; no
stub/TODO; `_speak` strings stay in cold Ultron register). Findings + resolution:
- **P1 — aggressive-band gate/dispatch mismatch (FIXED):** the 0.60 aggressive band returned `RELAY_TO_TEAM`
  but nothing downstream force-relayed it (the strict matcher abstains by definition, so the normal relay
  handler returned False). Fixed with a `turbo_mode_enabled()`-gated **relay backstop** before the semantic
  router: when the gate classified the turn `RELAY_TO_TEAM` and no explicit handler consumed it,
  `_maybe_handle_relay_speech(user_text, force=True)` broadcasts it. This makes a turbo RELAY verdict ALWAYS
  relay (DESIGN §1) for BOTH bands, and is byte-identical when turbo is OFF.
- **P2 — "kill turbo" leak (FIXED):** the full dispatch block passed normalized `user_text`, so "kill turbo"
  → "tell my team kill turbo" hid the toggle AND broadcast it. Fixed: the full block now matches on `_raw_stt`
  (like the lean block + the documented toggle convention).
- **P2 — names drift (FIXED):** `_classify_always_listening` now threads `relay_speech.addressee_names` into
  the gate so its `match_relay_command` predicate uses the same roster as dispatch (was `names=None`).
- **P2 (accepted, documented):** under the shipped config (`always_listening: true`), literal "turbo …"
  control phrases classify `COMMAND_LOCAL` even with turbo OFF — intended (keeps the voice toggle reachable;
  same pattern as the flavor/thinking/route matchers in `_is_command_local`). So the byte-identity guarantee
  is: **turbo-OFF leaves every NON-turbo utterance byte-identical**; only literal "turbo …" phrases change.
- **P2 (accepted):** the STOP window is ~26 px taller by default (the TURBO row always renders, like PTT/FLAG).
  Set `stop_button.turbo_height: 0` to hide the row and keep only the voice toggle.
- **P2 (accepted, by-design):** aggressive mode deliberately re-opens the semantic relay-intent positive path
  (the false-relay path hardened away in `e085d0d`) — this is the user's R6/R7 opt-in, double-gated behind
  turbo ON + turbo_aggressive ON (both default OFF). `KENNING_TURBO_MODE` is a module/test default only;
  `relay_speech.turbo_mode` (config) is authoritative at boot (matches the other u1.0 flags).
