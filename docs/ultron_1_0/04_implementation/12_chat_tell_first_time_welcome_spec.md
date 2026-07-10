# Spec 12 — Voice→chat tell relay + first-time-chatter welcome (2026-07-09)

Branch `claude/chat-tell-welcome`. User problem: a **40-second stream delay** makes chat interaction
painful — by the time a viewer sees the streamer's on-air answer, 40s have passed. Two features:

1. **Tell relay:** the streamer says *"Ultron, tell &lt;name&gt; in chat &lt;message&gt;"*; Ultron fuzzy-matches the
   transcribed name against chatters actually seen this stream, `@`-tags the best match, and posts the
   message to Twitch chat **instantly** (chat is real-time; only the video feed lags). A broadcast form
   (*"tell chat &lt;message&gt;"*) posts untagged. A stop-button toggle turns the whole feature on/off.
2. **First-time welcome:** the first time a login chats this stream, Ultron welcomes them, states the
   **current stream delay** (set live via a numeric field on the stop-button GUI), apologizes on the
   streamer's behalf, and notes he will answer as fast as the delay allows.

## REQUIREMENTS (EARS)

- **R1** WHEN the streamer's addressed utterance matches the tell grammar AND the tell toggle is ON AND
  Twitch chat is connected, the system SHALL post the message to chat (tagged form: `@` + the roster's
  best fuzzy match; broadcast form: untagged) and speak a short local confirmation naming the target.
- **R2** WHEN the tagged form matches but no roster candidate scores ≥ `tell_chat_match_floor`, the
  system SHALL post nothing and speak that no chatter matches the heard name.
- **R3** WHEN the tell toggle is OFF and the grammar matches, the system SHALL consume the turn with a
  short local notice and post nothing (no fall-through to team relay or the LLM).
- **R4** WHILE Twitch chat runs, the system SHALL record every chatter (login + display name) into a
  bounded roster; the fuzzy match SHALL only ever select an observed chatter (never invent one).
- **R5** WHEN a login chats for the first time this run AND welcome is enabled AND the chatter is not
  the broadcaster/bot, the system SHALL post one welcome naming them and stating the live delay value;
  each login is welcomed at most once per run, and welcomes are capped per minute (overflow logins are
  marked seen silently — a raid must not trigger a greeting flood).
- **R6** WHEN the streamer commits a new delay value in the stop-button numeric field, subsequent
  welcomes SHALL state the new value (live read; no restart).
- **R7** The tell grammar SHALL NOT match team-relay leads ("tell my team …") or teammate-social forms
  ("tell Jett nice shot") — the named form requires the literal "in chat" delimiter.

## DESIGN

**Grammar** (matcher `match_tell_chat` in `audio/relay_speech.py`, stdlib-re only, anticheat-clean;
matched on RAW STT before the relay-lead normalizer can rewrite it):
- Tagged: `tell|message|inform|notify|reply to|say to|write to  <name 1-5 tokens>  in [the] chat[,:]  <message>`
- Broadcast: `tell|say to [the] chat <message>` · `tell everyone in [the] chat <message>` · `post|put in [the] chat <message>`
- A leading wake token ("ultron[,]") is stripped; leading "that " dropped from the message; 400-char cap.

**Roster** — reuse the existing tested-but-unwired `twitch/user_roster.py` (`UserRoster`, rapidfuzz
WRatio + `normalize_stt`). Additive extension: `observe(username, display_name=None)` retains the real
display name; new `display_of(login)`. Fed from `ChatGameRouter.tick` (the one consumer that sees every
chat event whenever Twitch economy is up — presence bookkeeping already lives there in `_observe`).

**Welcome** — new `twitch/welcome.py` `FirstTimeWelcomer(template, template_no_delay, delay_fn,
exclude_uids, max_per_minute, now_fn)`: `observe(login, display, uid, broadcaster_uid) -> Optional[str]`
returns the formatted welcome exactly once per login; `{delay}` renders "40 seconds" / "1 minute
20 seconds"; `delay <= 0` uses the no-delay template. Router posts the returned text via its reply fn.

**Orchestrator** — holds the shared `UserRoster` (observe side: router; match side: voice handler) +
`_tell_chat_enabled` / `_stream_delay_seconds` with GUI setters. New `_maybe_handle_tell_chat` inserted
**before `_maybe_handle_relay_speech` in BOTH dispatch cascades**, matching on raw STT; posts via the
existing `_twitch_chat_post` closure ("/say" → write sidecar → Helix).

**GUI** — stop-button gains a TELL CHAT toggle row (`_make_toggle_row` pattern) + the overlay's first
numeric row (label + `tk.Entry`, commit on Return/FocusOut, int-validated, revert on bad input).

**Alternatives considered**
1. *Welcome/roster in the chat-reply pipeline* — rejected: that pipeline only ticks while
   `reply_enabled` is on; the router seam sees every message whenever Twitch economy is up.
2. *A fourth read-sidecar drain (dedicated welcome poller)* — rejected: more threads/cursors for zero
   user-visible benefit; the router already drains, dedups, and can post.
3. *Twitch-native first-msg flag* — unavailable: EventSub `channel.chat.message` carries no first-time
   marker and the sidecar's flat dict drops `message_type`; per-run first-seen is also the semantically
   right trigger (every new arrival this stream should learn the delay).
4. *Name-free grammar ("tell &lt;name&gt; &lt;message&gt;")* — rejected: collides with the team relay and the
   teammate-social relay; "in chat" is an unambiguous, natural delimiter.

## TASKS
1. Config fields (TwitchChatConfig + StopButtonConfig) + spec (this file).
2. `match_tell_chat` + `TellChatCommand` in relay_speech.py + tests.
3. `UserRoster` display-name extension + tests.
4. `twitch/welcome.py` + tests.
5. `ChatGameRouter` roster/welcome hooks + tests.
6. Stop-button rows + orchestrator setters/wiring/handler/cascades + tests.
7. Docs/code-map/STATUS/memory; suites; merge + publish.

## OUT OF SCOPE
1. Whisper/DM delivery (Twitch whispers need extra scopes + user-id resolution; chat @mention suffices).
2. Persisting the roster or seen-set across restarts (per-run is the correct stream boundary here).
3. Welcoming via TTS on stream (chat-only; the delay makes spoken welcomes arrive 40s late anyway).
4. `stream.online`/`offline` EventSub subscriptions for a true stream boundary (run boundary ≈ stream
   boundary for this operator; revisit only if Ultron ever outlives a stream).

## OPEN QUESTIONS
- Exact welcome/tell template wording is config-tunable; defaults chosen persona-consistent (BR-P2).
- `tell_chat_match_floor` default 60 (WRatio 0-100) — calibrate live if mis-tags appear.
