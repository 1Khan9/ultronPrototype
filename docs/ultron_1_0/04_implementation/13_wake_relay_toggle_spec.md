# Spec 13 — WAKE RELAY toggle (require the wake word before a team relay)

**Status:** implemented (branch `claude/wake-relay-toggle`).
**Owner:** voice/relay path. **Anticheat:** BR-P1 — all new code is `re`/`os`/stdlib only.

## REQUIREMENTS (EARS)

Context: today the streamer has two relay modes.
- **Normal relay** — an explicit lead transmits without the wake word: "tell my team sova hit 84".
- **Turbo** (default OFF) — a bare inferred callout transmits: "sova hit 84".

The streamer wants a THIRD, default-ON stop-window toggle **WAKE RELAY** that gates team
transmission on the wake word.

- **R1** — WHEN WAKE RELAY is ON AND the streamer utters a team-relay command that carries the
  wake word ("Ultron, tell my team sova hit 84" / "Ultron, explain to my team what the meaning of
  life is"), the system SHALL transmit the relay to the team as normal.
- **R2** — WHEN WAKE RELAY is ON AND a matched (or turbo/force-routed) team-relay command does NOT
  carry the wake word ("tell my team X", bare "sova hit 84"), the system SHALL suppress the
  transmission silently (no team audio, no local notice, no LLM role-play) and log it.
- **R3** — WHEN WAKE RELAY is OFF, the system SHALL behave byte-identically to today (normal +
  turbo relay unaffected).
- **R4** — The wake requirement SHALL be satisfied by a fresh ACOUSTIC wake for the capture (the
  streamer said the wake word to trigger the turn, so no textual copy is needed) OR by the wake
  word appearing at the start of the RAW transcript (the normalizer strips a leading wake word from
  the routed text, so the check runs on `_raw_stt`).
- **R5** — The toggle SHALL appear as a stop-window row (default ON), be flippable live, and default
  ON at boot from `relay_speech.wake_relay` (config), env override `KENNING_WAKE_RELAY`.
- **R6** — WAKE RELAY SHALL NOT affect Twitch chat / games / redeems (incl. the SPEAK_TEAM redeem):
  those never traverse the voice relay path and are provenance-guarded.

## DESIGN

Two candidate gate sites were considered.

- **Alternative A — gate at the relay choke point `_maybe_handle_relay_speech` (CHOSEN).** Every
  voice team transmission — "tell my team X", "explain/ask ... to my team" (compose), roast,
  turbo/router `force=True` — funnels through this one method, which is exactly where the existing
  `team_relay_enabled()` master gate already lives. A `wake_confirmed: bool` parameter (default
  `True`, so ~30 existing direct-call relay tests are unaffected) is passed by the run loop; when
  WAKE RELAY is ON and `wake_confirmed` is False the matched command is consumed silently. Single
  choke point ⇒ no transmit path can slip past; mirrors the proven team-relay-off precedent.

- **Alternative B — gate in the addressing block** (the `_relay_override` that lets a relay command
  bypass the wake gate in the follow-up window). Rejected as the *primary* site: it is one of
  several entry points (misses turbo/force), and the addressing block is delicate/live-bug-scarred.
  The choke point is the definitive backstop, so B is unnecessary.

**wake_confirmed signal (computed once per turn in the loop, on `_raw_stt`):**
`_wake_confirmed = (not came_from_follow_up) or utterance_leads_with_wake(_raw_stt)`.
`came_from_follow_up` is False for every fresh acoustic-wake capture (pending / barge-in /
wait-for-wake / wake-during-follow-up) and True only for continuous captures — which is exactly how
always-listening AND turbo arrive. So a fresh acoustic wake satisfies the requirement; a continuous
capture must carry the wake word inline. Fail-open: any error ⇒ `_wake_confirmed = True` (legacy).

**Composition / precedence.** `team_relay_enabled()` (RELAY master, full disengage) is checked FIRST
and dominates; WAKE RELAY only matters when team relay is ON. WAKE RELAY composes with turbo:
turbo ON + WAKE RELAY ON = "infer callouts, but only when I prefix the wake word." In the default
wake-required loop (turbo OFF, always-listening OFF) a fresh acoustic wake already sets
`wake_confirmed` True, so WAKE RELAY ON does not break the ordinary "Ultron → tell my team X" flow.

**Wake vocabulary.** `utterance_leads_with_wake` matches a LEADING wake word (optional hey/ok) from
the real wake words + clear STT mishears (`ultron`/`ulltron`/`ultronn`/`ultran`/`ultram`/`altron`/
`voltron`/`ultra`/`ultro`/`ultr`/`oltron`/`ultraun`/`kenning`) but EXCLUDES the ultra-loose
homophones `run`/`ron`/`tron`/`rons` used by the tell-chat matcher — there is no downstream
delimiter here, so a leading "run it down" must not false-count as a wake.

## FILES

- `src/kenning/audio/relay_speech.py` — `_wake_relay_enabled` flag + `set_/wake_relay_enabled()`;
  `_WAKE_RELAY_HOMOPHONES` / `_WAKE_RELAY_LEAD_RE` / `utterance_leads_with_wake()`; `__all__`.
- `src/kenning/pipeline/orchestrator.py` — `_maybe_handle_relay_speech(..., wake_confirmed=True)`
  gate; loop `_wake_confirmed` + pass to all 4 relay call sites; `_set_wake_relay_enabled`; config
  boot-apply; stop-button row wiring.
- `src/kenning/audio/stop_button.py` — `on_toggle_wake_relay` row (params, geometry, `_make_toggle_row`).
- `src/kenning/config.py` — `RelaySpeechConfig.wake_relay`; `StopButtonConfig.wake_relay_height/label`.
- `tests/audio/test_wake_relay.py` — flag, helper positives/negatives, choke-point gate matrix,
  config defaults, stop-button row presence.

## OUT OF SCOPE

1. Changing WHEN the loop listens (WAKE RELAY is a transmit gate only, not a capture-mode change).
2. Gating the Twitch SPEAK_TEAM redeem or any chat/games path (provenance-guarded, deliberately separate).
3. A per-utterance spoken "say the wake word first" nudge (silent-suppress by design, matching team-relay-off).

## OPEN QUESTIONS

- None blocking. If the streamer later wants an audible nudge on a suppressed un-waked relay, add a
  throttled local notice behind a sub-flag (kept silent for now to match the team-relay-off UX).
