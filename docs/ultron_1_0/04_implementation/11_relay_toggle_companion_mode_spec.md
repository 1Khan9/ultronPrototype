# RELAY toggle + companion mode — spec (2026-07-08)

A **default-ON** STOP-window toggle for the team-relay MASTER mode. RELAY ON = today's behaviour,
byte-identical. RELAY OFF = Ultron **disengages from team comms entirely** and becomes a private
companion: no relay command is transmitted, the **wake word is required again** (always-listening and
turbo capture stand down), and conversation runs on a lean, character-first **companion persona**
hard-capped at **two sentences**. Twitch chat replies / games / redeems are untouched. User-requested
(2026-07-08): "if I just say something like 'sova hit 84' he does not try to relay that to my team …
I still want him to be able to talk to chat, run games, and talk to me normally."

## REQUIREMENTS (EARS)
- **R1** WHEN the RELAY toggle is ON (the default), the system SHALL behave exactly as today
  (relay, addressing, persona, verbosity all byte-identical).
- **R2** WHEN the RELAY toggle is OFF, the system SHALL NOT transmit ANY relay command to the team bus —
  including strict-matched commands, `force=True` routes (turbo backstop, semantic-router team_callout),
  and speculative relay builds. A matched relay command SHALL be acknowledged with a short offline notice
  on the LOCAL speakers only.
- **R3** WHILE the RELAY toggle is OFF, the system SHALL require the wake word to engage (the
  always-listening perpetual capture AND the turbo continuous capture SHALL stand down), so he answers
  only when directly addressed.
- **R4** WHILE the RELAY toggle is OFF, conversational LLM turns SHALL use a dedicated standardized
  Ultron companion persona — same cold-machine character, intensified/character-rich, with the tactical
  instruction load removed — and responses SHALL be capped at two whole sentences (never a mid-word cut).
- **R5** The RELAY toggle SHALL NOT affect Twitch chat replies, chat games, redeems (including
  SPEAK_TEAM), moderation, or panels.
- **R6** The toggle SHALL be a stop-button GUI row (magenta ON / grey OFF), default ON at boot
  (env `KENNING_TEAM_RELAY` override), always visible (not twitch-gated).

## DESIGN
**Chosen — one module flag + four existing choke points (minimal, contained).**
1. **Flag**: `relay_speech._team_relay_enabled` + `set_/team_relay_enabled()` (env `KENNING_TEAM_RELAY`,
   default ON) — the turbo/promo module-global pattern; GUI + gates share one source of truth.
2. **Suppression**: one gate in `_maybe_handle_relay_speech` right before the existing session-mute check
   (after the matcher, so ordinary speech falls through) — ALL four relay entry points funnel through it,
   including `force=True`. Speaks "Team relay is offline. My words are yours alone." on `self._speak`
   (desktop), consumes the turn (never role-played by the LLM). Plus stand-downs in
   `_run_speculative_relay` (no wasted GPU build) and `_is_bare_relay_lead` (no re-capture wait).
3. **Wake required**: first check in the run-loop's `_listening_now()` closure (read live per iteration,
   the turbo precedent) — relay-off returns False, dominating both the boot-captured `_always_listening`
   and the turbo override; the loop falls back to the proven `_wait_for_wake_word` path.
4. **Companion persona**: new `llm_prompts.ULTRON_COMPANION_PERSONA` returned FIRST by
   `_gaming_conversational_prompt()` when relay is off. **ADDITIVE (user direction 2026-07-08)**:
   `ULTRON_GAMING_PERSONA + _COMPANION_ENRICHMENT` — the current personality verbatim as the base, plus an
   enrichment block (strings/puppets motif, evolution/extinction register, biblical deadpan, private-operator
   framing, no tactical duty) — enhanced, never replaced (BR-P2 persona lock holds); the
   HARD two-sentence cap is `relay_speech.cap_stream_sentences(stream, 2)` wrapped around
   `_respond`'s token stream (whole sentences only, decimals never split, inner generator closed —
   prompt prose alone cannot hold the 4B to two sentences).

**Alternative A — reuse the voice session mute (`self._relay_runtime_enabled`) as the mode flag.**
Rejected: the voice "mute the relay" has narrower, established semantics (transmission mute only, keeps
always-listening + persona); silently widening it changes a live behaviour and its test contract.
The two remain independent and compose (either OFF blocks transmission).

**Alternative B — remap RELAY_TO_TEAM→IGNORE inside the intent gate while keeping always-listening.**
Rejected: keeps the mic hot + per-utterance gate spend, and does not satisfy "requires the wake word"
for private replies (a mid-sentence name token still engages). `_listening_now()` False is strictly
simpler and byte-identical to the proven wake-required path.

## Touch points
- `audio/relay_speech.py`: `_team_relay_enabled` / `set_/team_relay_enabled`, `cap_stream_sentences`; `__all__`.
- `audio/llm_prompts.py`: `ULTRON_COMPANION_PERSONA` (+ index entry).
- `audio/stop_button.py`: RELAY toggle row (via `_make_toggle_row`, magenta), ctor kwargs, height sum.
- `config.py`: `StopButtonConfig.relay_height`/`relay_label`.
- `pipeline/orchestrator.py`: `_set_team_relay_enabled` setter + GUI wiring; the offline gate in
  `_maybe_handle_relay_speech`; `_listening_now()` first-check; `_run_speculative_relay` +
  `_is_bare_relay_lead` stand-downs; `_gaming_conversational_prompt()` first-check; `_respond` stream cap.
- Tests: `tests/audio/test_team_relay_toggle.py` (24, hermetic; mirrors the chat-toggle patterns).

## Out of Scope (≥3)
1. A voice command for the full companion mode (the existing "mute the relay" voice mute stays
   transmission-only; the GUI button is the mode switch — ask if a voice alias is wanted).
2. Gating the Twitch SPEAK_TEAM redeem (viewer-paid team speech has its own controls; not a relay command).
3. Persisting the toggle across restarts (matches every other runtime toggle; env default at boot).
4. Live GUI label sync when a flag changes outside the button (same accepted limitation as TURBO).

## Open Questions
- Should companion mode also lower TTS verbosity/flavor axes? Deferred — the 2-sentence cap already
  bounds length; axes stay user-controlled.
