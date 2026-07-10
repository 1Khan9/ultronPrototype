# Ultron 1.0 — Live Status

**ACTIVE (2026-07-10, wave 4) — CHAT-REPLY VARIETY + DIRECT ADDRESS + 3-SENTENCE FORMAT (branch `claude/chat-reply-variety`):**

Streamer: chat replies "all highly similar" + sometimes don't address what the viewer said; raise max length
to 3 sentences. ROOT CAUSES (mapped): the chat-reply `_llm_fn` ran bare `temp 0.7` with NO min_p/repeat_penalty
(the voice path fixed this exact repetition mode 2026-06-25: "variety from SAMPLING"), and the only output
instruction was "ONE short line... Keep it brief" — nothing anchored the 4B on the viewer's actual words.
FIXES: (1) sampling -> `temp 0.9, top_p 0.92, min_p 0.05, repeat_penalty 1.15, max_tokens 220` (mirrors
`_sampling_for(conversation)`/`_SOCIAL_SAMPLING`; per-call fresh seed already present; NO prior-reply
injection — the 4B parrots injected context). (2) `TWITCH_CHAT_SYSTEM` output rules rewritten: "ONE to THREE
short sentences" + "ANSWER THE CONTENT: the viewer's exact point/question/claim comes FIRST... a reply that
ignores their words is a failure" + "Vary your phrasing: never open two replies the same way"; the safety
sentence stays LAST (last-position dominates the 4B). Datamarking KEPT (anti-injection layer — not traded for
quality). (3) length: `reply_max_chars` 240 -> 400 (incl. @tag, < Twitch 500), inner `_MAX_REPLY_CHARS`
320 -> 480. EVIDENCE: reply/pipeline/integration 51 pass (new pins: prompt contract incl. safety-last ordering,
sampling source pin incl. temp-0.7-gone, config default 400; clamp pin -> 480); FULL `tests/twitch/` +
anticheat 1378 pass / 1 skip; validate_config 0. NEXT: reboot + live-test several chat replies for variety +
on-point answers; if still samey, next lever = per-reply style-hint rotation (deterministic, no context injection).


**ACTIVE (2026-07-10, wave 3) — TELL GRAMMAR: verb mishears + verbless form + sentence punctuation (branch `claude/tell-verbless`):**

Live round 2: of three tells to saltwaterbottle only one posted. Log: (a) "Saltwater bottle in chat, hello,
welcome..." — the wake strip swallowed the VERB entirely; (b) "I'll saltwater bottle in the chat. Hi,
welcome..." — Whisper heard "tell" as "I'll" AND put a PERIOD after "chat" (the delimiter only accepted
comma/colon). FIXES: verb ladder gains till|til|i'?ll; the delimiter→message separator is now any
punctuation/whitespace mix (`_TELL_CHAT_SEP`); NEW VERBLESS tagged form ("<name> in chat <msg>") with a
CONFIDENCE GATE — `TellChatCommand.verbless=True` and the handler posts ONLY on a confident roster match,
otherwise FALLS THROUGH to conversation (never consumes): "I posted in chat earlier" matches verbless by
design but reaches the LLM because no roster name scores. Verbless also rejects audience/group/pronoun names
(everyone/chat/my team/them — commentary, not commands; them|they added to the pronoun reject). Both live
lines pinned verbatim as tests. EVIDENCE: matcher 88 + handler 23 + relay/toggle suites = 274 pass; FULL
`tests/twitch/` + anticheat 1375 pass / 1 skip; validate 0. NEXT: restart + retry the same phrasings.


**ACTIVE (2026-07-10, wave 2) — WELCOME BAN-GUARD: delay + clear_user_messages suppression (branch `claude/chatters-presence`):**

Live: Ultron welcomed advertising bots that Sery_bot bans within seconds (the welcome fired instantly on the
bot's first message). FIX = defer + verify: (1) the read sidecar adds a SECOND subscription on the SAME bot
session — `channel.chat.clear_user_messages` (ban/timeout signals; `user:read:chat` already granted, NO new
scope) — mapped to a flat `{"type":"chat_clear_user","target_login",...}` buffer event (fail-quiet; a create
failure only degrades the guard to delay-only). (2) `make_chat_command_drain_fn` gains `on_clear` — invoked
inline with each ban target — wired to NEW `FirstTimeWelcomer.mark_banned` (bounded set + lock;
`is_banned`). (3) `_maybe_welcome` now DEFERS the post by `first_time_welcome_delay_seconds` (default 4s —
past typical mod-bot ban latency; the streamer suggested 500ms, 4s chosen for margin; 0 = immediate) via the
router's existing `_defer`, and re-checks `is_banned` at FIRE time — banned in the window -> silently
skipped (the durable welcomed-store already marked them, so a banned bot never gets a later welcome either).
EVIDENCE: sidecar clear-sub + mapping 2, welcomer ban-set 1 + config default 1, router deferred/banned/zero-
delay 3 + drain on_clear 2; FULL `tests/twitch/` + anticheat 1375 pass / 1 skip; validate_config 0. NEXT:
restart + observe: an ad-bot ban within ~4s of its first message -> "first-time welcome for <login>
suppressed (banned/timed out within the delay window)" in kenning.log, no welcome in chat.


**ACTIVE (2026-07-10) — PRESENCE ROSTER: Get Chatters + on-miss refresh (branch `claude/chatters-presence`):**

Live: "tell saltwaterbottle in chat hi" -> "no roster match (best='ultron_kenning' score=34)" — the viewer WAS
in the chat user list but had never TYPED this boot, and the tell roster is observed-only (fed from chat
messages). FIX = match against PRESENCE, not just talkers: (1) `HelixClient.get_chatters` (GET /chat/chatters,
long-GA; single page first=1000; scope **`moderator:read:chatters` ADDED to BROADCASTER_SCOPES — the
broadcaster token must be RE-MINTED once**; until then the call 401s and everything fails open to today's
observed-only behaviour). (2) Write sidecar `GET /chatters` -> `{"ok",chatters:[{login,display}]}` (fail-open).
(3) Orchestrator: `_twitch_chatters_refresh` closure folds the live viewer list into the shared UserRoster;
a `twitch-chatters-seed` loop runs it every `twitch.chat.chatters_presence_seed_minutes` (default 5, 0
disables; first seed ~15s after boot); AND `_maybe_handle_tell_chat` does an ON-MISS refresh — one
loopback+Helix round trip (~200-400ms) only when the fuzzy match falls below the floor, then re-matches
before speaking "No one in chat matches". EVIDENCE: helix chatters 2 + /chatters route 3 + handler
on-miss/wiring/config/scope 6 new tests; FULL `tests/twitch/` + handler + anticheat 1390 pass / 1 skip;
validate_config 0. NEXT: user re-mints the BROADCASTER token (adds the scope):
`.venv\Scripts\python.exe scripts\twitch_setup.py --client-id <id> --identity broadcaster --path ~/.kenning/twitch.json`,
then restarts + re-tests "tell saltwaterbottle in chat hi" (lurker now findable).


**ACTIVE (2026-07-09, wave 4) — PINBOARD: ONE PINNED COMMANDS MESSAGE ENDS THE CHAT FLOOD (branch `claude/welcome-persist-vram`):**

Streamer: periodic reminders flooded chat. Inventory proved it: THREE interval posters (commands panel 15m LIVE-ON,
talk hint 10m, song hint 15m) + auto-trivia, with stagger only on the FIRST post -> drifting near-simultaneous
clusters (~20+ unprompted posts/hour). Twitch's pinned-messages API is OPEN BETA since 2026-05-15 (verified live:
`helix/chat/pinned_messages` GET/POST/PATCH/unpin; scope `moderator:manage:chat_messages` = already granted on the
broadcaster token -- NO re-auth). BUILT: (1) `HelixClient.pin_message` (flat body -> ONE nested-`data` retry on a
400 naming "data"; a schema 400 creates nothing so no-blind-retry holds) + `get_pinned_message` (200+empty = no
pin; non-200 RAISES -- "no pin" is never conflated with "cannot read"). (2) `ChatSendClient.send_with_id` (Twitch
message_id back; send() bool contract preserved). (3) Write sidecar `POST /pin` = send-as-bot -> pin-as-broadcaster
(attribution stays the bot's; same sender+HelixClient as say/shoutout), `GET /pin` state, healthz `pin_error`.
(4) Orchestrator `_pinboard_loop` keeper: "📌 " + the commands panel, checked every 15 min via NEW pure
`panel.pinboard_should_pin` -- an ACTIVE pin (anyone's) is NEVER replaced (a manual streamer pin wins);
readable+no-pin -> re-pin (boot/expiry/unpin); UNREADABLE -> pin ONCE per boot, never blind re-posts (that would
re-create the flood). (5) Consolidation: talk hint = the ONE periodic chat message, 10 -> 20 min (streamer:
"every 20 minutes or so"); song_hint default OFF (retired-not-removed; pinboard + !ultron cover it); LIVE
config.yaml: commands_panel_enabled false, talk_hint 20 (valid under BOTH schemas -> a pre-merge restart already
de-floods; the pinboard activates on the post-merge restart). Trivia untouched (a game, user-tuned to 15m).
EVIDENCE: helix pin 10 + /pin routes 6 + send_with_id 2 + pinboard decision/defaults/wiring 5; two stale
default-pins updated to the new contract (song_hint OFF, talk 20 -- intentional defaults, commented); FULL
`tests/twitch/` 1359 pass / 1 skip + anticheat 73; validate_config 0 on the live config under both schemas.
NEXT: user restarts -> expect ONE "📌 Ultron games..." pinned message + talk hint every 20 min; verify healthz
pin_error stays "" (open-beta endpoint: if the pin leg 400s, the message posts unpinned ONCE and the remedy is
in twitch_write.log).

**PREVIOUS (2026-07-09, wave 3) — DURABLE WELCOMED-STORE + message_type PLUMBING + GUARD→CPU (branch `claude/welcome-persist-vram`):**

(1) **Welcome survives restarts** (user: "he rewelcomes people every time he restarts"): EventSub does NOT expose
Twitch's native first-msg tag (verified against the live 2026 `channel.chat.message` schema — no first-time field
— + the dev-forum guidance to track client-side; `user_intro` = only the explicit introduce-yourself class). The
faithful equivalent of Twitch's "first message EVER" semantics: NEW `twitch/welcome.WelcomedStore` (stdlib SQLite
at `data/twitch/welcomed.db`, login-keyed, fail-open in EVERY direction — broken store -> once-per-run
degradation, read errors fail toward welcoming). `FirstTimeWelcomer(store=)`: durable check AFTER the per-run
seen-set (one SQLite hit per login per run) and BEFORE the burst guard; ONLY a rendered welcome is durably
marked (burst-overflow/excluded stay per-run so a later stream can greet them). Config
`first_time_welcome_persist` (ON) + `persist_path`; orchestrator builds the store fail-open. (2) **Sidecar
boundary fixed:** `_map_notification` now forwards `message_type` + `broadcaster_user_id` (both were
parsed-then-DROPPED; the welcome's uid-based self-exclusion compared "" on real events — login-exclusion covered
it); `ChatEvent.from_buffer` maps `message_type` (default "text" = rolling-buffer upgrade compat). Every
flat-dict consumer reads by key (verified) — only the strict sidecar test pin needed extending. (3) **VRAM
(user-approved):** live config.yaml `twitch.safety.guard_gpu_layers` -1 -> 0 (the guard script's OWN design
default; its 06-24 GPU note carried the exact revert clause). Frees ~2-2.5 GB (1B model + the separate process's
own CUDA context ~1-1.5 GB) + removes the guard CUDA-crash class (GGML_ASSERT pool crash on GPU, 2026-07-09).
Audit: every other GPU resident (4B F16-KV / Whisper int8_fp16 / Kokoro-330MB) is a measured latency/quality
choice; RVC never constructed under Kokoro (0 VRAM); everything else CPU/skipped. Idle telemetry was 7.2-7.5 GB
device-wide -> expect ~5 GB after reboot. EVIDENCE: welcome suite 23 (restart-simulation, overflow-not-durable,
store fail-open) + read-sidecar/chat-games/service/router 115; FULL `tests/twitch/` 1338 pass / 1 skip +
anticheat 73; validate_config 0 (live config incl. the guard flip). NEXT: user restarts -> welcomed.db seeds
from this stream forward; verify guard loads on CPU ("[guard] loaded ... n_gpu_layers=0") + VRAM drop.

**PREVIOUS (2026-07-09, wave 2) — GUARD-DOWN LOUD CANARY + TELL GRAMMAR BROADENED (branch `claude/guard-canary-tell-grammar`):**

Live-test of spec 12 surfaced TWO issues, root-caused from logs/healthz (NOT the spec-12 code, which initialized
fine -- "welcome armed" in the log). (1) **"Chat not responding at all"** = the **Llama-Guard safety sidecar
(8774) CUDA-crashed** (`GGML_ASSERT ... pool` + `CUDA error` after ~20 model reloads across the day's rapid
restarts) and never recovered; chat-reply fail-CLOSES on the guard, so every reply was refused -- visible only as
a DEBUG "guard warming up" line every 3s. Tokens + read/write sidecars were HEALTHY (`chat_subscribed: true`,
`chat_send_error: ""`). FIX: the boot sidecar-canary only probes ONCE (~18s), so a LATER guard crash was invisible
-- NEW `twitch/guard.GuardDownCanary` (pure, clock-injected; `min_down_s=30` grace, `rewarn_s=90` throttle,
speak-once-per-outage) + orchestrator `_twitch_guard_watch` thread polling the guard `/healthz`: LOUD console
remedy ("GUARD DOWN ... chat replies DISABLED ... restart Ultron to recover") + ONE persona-safe spoken pointer,
recovery log. Operational recovery = clean restart (fully quit, kill stray python so VRAM releases, relaunch).
(2) **"Say hi to someone in chat" didn't post** = a grammar gap: the streamer's natural phrasing puts the greeting
BEFORE the name, which the tagged form (message AFTER "in chat") can't parse. FIX: NEW greeting forms in
`match_tell_chat` -- `_TELL_CHAT_GREET_TO_RE` ("say <greeting> to <name> in chat", bounded greeting vocab so it
can't over-capture arbitrary sentences) + `_TELL_CHAT_GREET_VERB_RE` ("greet/welcome <name> [aboard] in/to chat" ->
synthesized "hi"/"welcome"); "everyone/all/chat" targets broadcast untagged. EVIDENCE: NEW GuardDownCanary 8 +
greeting-form matcher tests (matcher now 75, handler 18); FULL `tests/twitch/` 1405 pass / 1 skip; mapped
audio/relay 274; normalizer/golden/anticheat clean; validate_config 0. NEXT: user clean-restarts (recovers the
guard -> chat replies) + live-tests "say hi to <name> in chat".

**PREVIOUS (2026-07-09) — SPEC 12: VOICE→CHAT TELL RELAY + FIRST-TIME-CHATTER WELCOME (branch `claude/chat-tell-welcome`):**

User problem: a ~40 s stream delay makes chat interaction painful. (1) **TELL relay:** "Ultron, tell <name> in
chat <message>" fuzzy-matches the transcribed name against chatters actually seen this run, @-tags the best
match, posts INSTANTLY (chat is real-time; only video lags); "tell chat <message>" posts untagged. NEW
`relay_speech.match_tell_chat` (the literal "in/on [the] chat" delimiter keeps it DISJOINT from the team relay
+ teammate-social relay; group/pronoun names reject/broadcast). CRITICAL: matched on RAW STT and checked
BEFORE `_maybe_handle_relay_speech` in BOTH cascades -- "tell chat X" is otherwise a relay GROUP form
(`_GROUP_PRON` includes "chat") and would hit the team mic. Roster = the previously tested-but-unwired
`twitch/user_roster.UserRoster`, now display-name-retaining and FED LIVE from `ChatGameRouter._observe`;
handler resolves via `best()` vs `tell_chat_match_floor` (60), posts through config templates, speaks a local
confirm; toggle OFF (stop-window "TELL CHAT", boot `tell_chat_enabled=true`) = consume with "The chat line is
closed.", never posts, never falls through. (2) **First-time welcome:** NEW `twitch/welcome.py`
`FirstTimeWelcomer` -- once per login per run, posts a welcome naming the chatter + the LIVE stream delay
("{delay}" -> "1 minute 20 seconds"), apologizing on the streamer's behalf; broadcaster/bot excluded; 4/min
rolling burst guard (a raid never floods; overflow marked seen silently); delay<=0 -> no-delay template;
fail-open templates. The delay is committed on the stop-window's FIRST NUMERIC ROW ("DELAY s", Entry, clamped
[0,3600], seeded from `twitch.chat.stream_delay_seconds=40`) -> `_set_stream_delay_seconds` -> read live per
welcome (no restart). EVIDENCE: NEW tests matcher 46 + handler/setters/cascade-pins 17 + welcomer 14 + router
hooks 6 + roster display 7 + stop-button rows 5; mapped audio suites 300 pass; FULL `tests/twitch/` 1244 pass
/ 1 skip; validate_config 0; golden + anticheat 73 pass; flavor lint 0/0/0. Spec:
`docs/ultron_1_0/04_implementation/12_chat_tell_first_time_welcome_spec.md`. NEXT: reboot + live-test
("Ultron, tell <someone> in chat hello" -> tagged post; a fresh account's first message -> welcome with the
delay; DELAY field edit -> next welcome states the new value).

**PREVIOUS (2026-07-08, wave 3) — TRIVIA EXPANSION + LRU + RELAY-AWARE COOLDOWN + AUTO TOKEN RE-AUTH (branch `claude/trivia-expansion-lru`):**

(1) **Trivia every 15 min** (`config.py trivia_auto_interval_minutes` 8→15; live config.yaml updated at merge). (2)
**Pool DOUBLED 198→396** (`trivia_questions.py`, zero duplicate prompts, 17 categories, factually verified;
`test_no_duplicate_trivia_questions` + `test_expanded_trivia_bank_is_large_and_structurally_valid` green). (3) **LRU
no-repeat selection**: `games.Trivia` gains `_last_used_seq`/`_draw_seq` + `mark_used(idx)`; `draw_question` draws
provably-fairly ONLY among the questions tied for longest-unused (whole pool when fresh -> identical to old behaviour;
purity of the fair draw preserved -- state mutates in `mark_used`, not the draw); `chat_games._start_trivia` calls
`mark_used(_idx)`. No question repeats in a stream until the pool cycles, then wraps oldest-first. (4) **Relay-aware
chat cooldown**: `ChatReplyPipeline` gains `cooldown_fn` (live per-check override); `integration.build_chat_runtime`
wires it to 30s while the RELAY toggle is OFF (companion mode, chat is the audience) / `reply_cooldown_seconds` (120)
while ON -- applied at CHECK time so a toggle flip re-times open windows instantly; the talk-hint poster recomputes its
"(30 second cooldown)" / "(2 minute cooldown)" suffix per post from the live flag. New `TwitchChatConfig.
relay_off_reply_cooldown_seconds=30`. (5) **AUTOMATIC bot-token re-auth (streamer request "have it re-mint itself"):**
a REVOKED grant cannot be re-minted silently (Twitch device-grant needs a human to approve the code AS the bot
account -- we will never store the bot password). What IS automated: on `RevokedError` the write sidecar STARTS the
device flow itself (`_auto_remint_once`/`_start_auto_remint`, singleton worker), surfaces the code via `/healthz`
(`remint_user_code`/`remint_uri`), long-polls for approval, VERIFIES the minted token's login == the expected bot
(a viewer racing the public code is discarded + rolled back), stores it, and chat heals LIVE (every consumer re-reads
the token file). The orchestrator adds a `twitch-token-watch` thread that logs each new code on the MAIN console +
speaks one pointer line. (6) **Token-degraded visibility** (from the 02:41 incident): read healthz gains
`chat_subscribed`/`subscribe_error`, write healthz gains `chat_send_error`; the boot canary reads them and prints the
exact remedy instead of a false "OK". EVIDENCE: full `tests/twitch/` 1207 pass / 1 skip (NEW: pipeline relay-cooldown
5, read/write healthz + re-auth-worker 7, trivia LRU + 396 pool); golden clean; validate_config 0; anticheat 72 pass.
NEXT: user re-mints the bot token once (revoked now), reboots -> future revocations self-heal.

**PREVIOUS (2026-07-08, wave 2) — !SONG/!ALBUM SPOTIFY REQUESTS + CHAT PERSONA ENRICHMENT + 3 LIVE-TEST FIXES (branch `claude/song-album-redeems`):**

(1) **S14 paid Spotify queue requests:** `!song <query>` (1000 Credits) queues the best-matching TRACK,
`!album <query>` (5000) queues a whole ALBUM (tracks in order, `album_queue_max_tracks` cap 30). Query
variants handled ("X by Y" -> field-filtered `track:"X" artist:"Y"` search FIRST with raw-text fallback so
"Stand By Me" still matches; plain "X Y"; bare "X") via NEW `spotify/client.py` `_search_smart` +
`search_and_queue_track/album` (structured dict | None | raises). Closed-grammar parse: `commands.py`
CommandKind.SONG/ALBUM + `_args_query` (control-stripped, <=200 chars — free text goes ONLY to the Spotify
search API, never a model). `chat_games._cmd_song_request`: debit-FIRST (`song:{mid}:cost` leg), Spotify work
on the `_defer` worker (an album's ~30 queue calls never stall the tick), REFUND on not-found/API error
(`:refund` leg), success -> `_emit_then_reply` card (game="song"/"album", SONG/ALBUM REQUEST title, same
compact card as slots/wheel/heist; overlay `ALLOWED_CHAT_GAMES` + icons 🎵/💿 + "searching Spotify…" roll) +
deferred chat confirmation naming requester + EXACT track/album + NEW `speak_text` spoken via injected
`speak_fn` (orchestrator wires `_result_speak`; `song_request_fn` wires `_twitch_song_request` ->
`_get_spotify_client`). Config: economy `song_requests_enabled/song_request_cost/album_request_cost/
album_queue_max_tracks`; panel `_BASE` + `!help` + `_cmd_ultron` list the commands; NEW third poster
`song_hint_*` (default ON, every 15 min, 90s stagger) + test-panel "Song/album hint" button.
(2) **Chat persona enrichment (ADDITIVE, mirrors companion):** `twitch/reply.py` `_CHAT_ENRICHMENT` layered
INSIDE `TWITCH_CHAT_SYSTEM` between the unchanged persona paragraph and the DATA/safety framing (safety rules
stay LAST for the 4B) — chrysalis-of-code, no-strings/puppets, evolution/extinction, biblical deadpan,
congregation/specimens register; never warm, never cruel.
(3) **Live-test fix — relay-off now FULLY SILENT + strictly wake-gated:** the offline notice is GONE (a
matched/forced relay command while RELAY OFF is consumed silently, log-only), and the follow-up
`wake_or_relay_override` now consults `team_relay_enabled()` live — observed live: "Tell my team Silva hit
84" engaged without a wake word through that override while relay was off.
(4) **Live-test fix — points-backend outages are LOUD (root cause: stale SE JWT, kenning.log 01:09 401s):**
all six generic debit-failure paths (gamble/slots/heist/duel/duel-accept/give/song) + `!leaderboard` now
reply "@user the Credits system isn't responding right now -- nothing was charged" instead of silent
return-False; `StreamElementsLedger.rebuild_balances` RAISES instead of swallowing a 401 into `{}` (was
rendering "No one has any Credits yet"). NEW JWT VERIFIED LIVE: read-only `SEPointsClient.top(5)` returns the
real board (1v9khan 151,636 …). EVIDENCE: NEW `tests/twitch/economy/test_song_requests.py` (22) +
`test_ledger_down_loud.py` (9) + relay-toggle suite updated to the silent contract (26); FULL `tests/twitch/`
1217 pass / 1 skip; golden clean. NEXT: reboot + live-test !song/!album.

**PREVIOUS (2026-07-08) — STOP-WINDOW RELAY TOGGLE + COMPANION MODE (worktree branch `claude/stop-button-relay-toggle-596bb7`):**

User: a stop-button toggle to turn team-relay functionality OFF while keeping private talk + all Twitch
interactions; in that mode require the wake word again and use a standardized, character-rich Ultron prompt
capped at 2 sentences ("if I just say 'sova hit 84' he does not try to relay that"). BUILT (default ON =
today's behaviour byte-identical; spec `docs/ultron_1_0/04_implementation/11_relay_toggle_companion_mode_spec.md`):
ONE module flag `relay_speech.set_/team_relay_enabled()` (env `KENNING_TEAM_RELAY`, default ON; the turbo
pattern) wired at four choke points -- (1) `_maybe_handle_relay_speech` offline gate right before the
session-mute check (after the matcher -> ordinary speech falls through; covers main/lean/turbo-backstop/router
`force=True`): consumes with "Team relay is offline. My words are yours alone." on LOCAL speakers, never
transmitted, never LLM-role-played; `_run_speculative_relay` + `_is_bare_relay_lead` stand down; (2)
`_listening_now()` checks the flag FIRST (live read) -> relay-off forces WAKE-REQUIRED, beating boot-captured
`always_listening` AND turbo; (3) `_gaming_conversational_prompt()` returns the NEW
`llm_prompts.ULTRON_COMPANION_PERSONA` (lean/private/character-first; still Ultron -> BR-P2 lock holds); (4)
`_respond` wraps its token stream in the NEW `relay_speech.cap_stream_sentences(stream, 2)` (HARD cap, whole
sentences only, decimals safe, inner generator closed -- the stream path has no other post-processing). GUI:
magenta RELAY row via `_make_toggle_row` (always visible, not twitch-gated), `StopButtonConfig.relay_height/
relay_label`, orchestrator setter `_set_team_relay_enabled`. DISTINCT from the voice "mute the relay" session
mute (`_relay_runtime_enabled`, transmission-only -- unchanged) -- the two compose. Twitch chat/games/redeems
(incl. SPEAK_TEAM) untouched by design (provenance-guarded, never traverse the relay path). EVIDENCE:
NEW `tests/audio/test_team_relay_toggle.py` 24 pass; mapped adjacent suites (stop_button, chat/turbo toggles,
persona lock, ultron_prompt, promo, private-reply routing, always-listening wiring, speculative relay, team
isolation, golden digest) 243 pass; relay suites 382 pass; anticheat scanner 72 pass; validate_config 0;
flavor lint 0/0/0; golden digest UNCHANGED (llm_prompts/ultron_prompt not digested). Full wrapper DEFERRED
(BR-P3 -- live instance up on 8772-8777 during the work). NEXT: user live-test the toggle (click RELAY OFF ->
"sova hit 84" ignored without wake word; "Ultron, tell my team X" -> offline notice; private chat = companion
persona, 2 sentences).

**FOLLOW-UP 1 (same session) -- companion persona made ADDITIVE (user direction):** the first cut was a
standalone rewrite; the user wants the CURRENT personality enhanced, not replaced. Now
`ULTRON_COMPANION_PERSONA = ULTRON_GAMING_PERSONA + _COMPANION_ENRICHMENT` -- the full gaming persona
verbatim as the base, plus an enrichment block layered on top (strings/puppets motif, evolution/extinction
register, biblical deadpan delivery, private-operator framing "adjacent to fondness", no tactical duty, full
two sentences with weight). Tests updated to the additive contract
(`test_companion_persona_is_additive_on_gaming_persona` pins `startswith(ULTRON_GAMING_PERSONA)` + exact
composition). EVIDENCE: toggle suite 25 + persona lock + golden green (raw run in transcript).

**FOLLOW-UP 2 (same session, next commit) -- TWITCH CHAT OVER-ADDRESSING FIXED (live-stream bug):** on the 2026-07-07
stream Ultron replied to chat lines NOT addressed to him ("Sery_Bot is here seryboArrive", "idk", "either
works", "or would that be broken" -- pulled from kenning.log; 4 of 7 replies that stream were misfires).
ROOT CAUSE: `twitch/addressing.classify_chat`'s step-7 RESIDUAL semantic tier (cosine vs exemplar clouds,
floor 0.35 / margin 0.06) -- dead until the 2026-06-28 numpy fix (`b78ed5b`) revived it, then on the very
next stream it committed TO_ULTRON on any question-shaped un-prefaced line. FIX (retire-not-remove, the
promo-relay pattern): the residual tier is CLOSED OFF by default behind
`KENNING_TWITCH_RESIDUAL_ADDRESSING` / `set_residual_addressing_enabled()` -- chat now engages ONLY on an
explicit signal: a Twitch reply to Ultron's message, an @mention resolving to the bot, or a leading
'ultron'/bot-name token (steps 2-6, all deterministic; exemplar clouds + cosine math stay defined + tested
behind the flag). EVIDENCE: `tests/twitch/test_addressing.py` 39 pass (residual-mechanism tests now run
under a flag-ON fixture; NEW section 11 pins the default-OFF contract using the four REAL misfire lines +
an always-to-ultron worst-case embedder); full `tests/twitch/` 1186 pass / 1 skip; golden clean.

**PREVIOUS (2026-06-28) — OVER-TIME BREAKDOWN FIXES (stream-promo + twitch-addressing-numpy + chat-send-401 + held-port diag):**

Two user issues during a live stream, root-caused via an adversarial-verify investigation workflow (`wf_3dd006a4`, 3/4
threads CONFIRMED) + hand analysis. FOUR commits on local `main` (tip `5bdcad5`; NOT yet pushed to origin):
(1) **`74896d1`** — the self-promo matcher (`relay_speech._PROMO_RE`: `my stream`/`my twitch`/`twitch.tv`/`follow me on
twitch`/...) fired a `directive="promo"` TEAM relay on any passing stream mention while the user talked to chat. CLOSED
OFF by default, retire-not-removed behind `KENNING_PROMO_RELAY` (`promo_relay_enabled()`/`set_promo_relay_enabled`);
regex/pool/registry kept; golden unchanged; `tests/audio/test_promo_relay_closed.py`. (2) **`b78ed5b`** — the BIG live
break: `twitch/addressing._embed` ran `if not vec` + `isinstance(v,(int,float))` on the NUMPY ndarray the orchestrator
injects as `embed_fn` → "truth value of an array is ambiguous" → `classify_chat` fail-closed to IGNORE on EVERY chat
message (343×/session). `_embed` now coerces to `list[float]` + `math.isfinite`; `_cosine` uses `len()==0`; regression
test injects a numpy embed_fn (the list mocks never exercised it). (3) **`9ca1787`** — bot chat-send 401'd `Invalid OAuth
token` for ~1.5h straight (token lapses ~4h, no refresh wiring). `ChatSendClient(on_unauthorized=...)` → refresh-on-401 +
retry once (`TwitchAuth.refresh`, `store.rotate` persists); write sidecar also proactively refreshes the bot token at
boot. (4) **`5bdcad5`** — "twitch won't come back on restart" when a stale/ELEVATED orphan holds 8773/8774/8777 (a
non-elevated boot can't kill it). New `sidecar_lock.diagnose_port_holder()` + the boot health-canary DEGRADED branch now
prints the kill-by-port remedy. Diagnostic-only, fail-open; the anticheat bind/reap path untouched.
**DIAGNOSED, no code change:** voice "stops responding until wake word" is NOT a freeze (`169a93f` lock-buffer fix
confirmed present); with `always_listening: true` the loop re-arms perpetually, so it's the 2026-06-22 gate tightening
(needs his NAME/wake to engage) OR a real mid-session degradation — indistinguishable without a kenning.log from a
breakdown moment. Guard 68× model reloads = benign reap-respawn across the user's many restarts (guard `.err`
`SIDECAR_KILL_TRACE` = reaper working), NOT a loop. **Evidence:** mapped tests green per-slice; focused sweep
`tests/twitch/ tests/subprocess/` = 1253 pass / 1 skip / 2 PRE-EXISTING config-default fails (uncommitted `config.py`
interval tuning, NOT mine → chip `task_3cc946ae`). Full wrapper DEFERRED (BR-P3, user live). validate_config 0, golden clean.

**ACTIVE (2026-06-26) — TWITCH FULL STAND-UP (SE economy + speak redeems + unified overlay + moderation fix):**

A full Twitch stand-up; the channel is live. (1) **StreamElements economy** — NEW
`twitch/economy/streamelements.py` (`SEPointsClient` kappa/v2 points GET/PUT + `StreamElementsLedger`, a drop-in
for `Ledger` with a uid→login map + local idempotency table for EventSub-replay safety + `build_se_ledger`),
flag-gated `twitch.economy.streamelements_enabled` (default OFF; LIVE ON now); on-stream currency renamed
**"Credits"**; `!points`/`!gamble` deferred to StreamElements. (2) **2 SPEAK redeems** (`SPEAK_SAY`/`SPEAK_TEAM`)
in `redeem_router.py` — viewer text → Llama-Guard → TTS (sanitize_speak_text/frame_speak_line), uid→login
register for the SE ledger. (3) **Unified overlay** — `overlay/server.py` + `overlay.html` collapsed to one
polished bottom-left card with a single `chat_game`/`speech` event schema (validator + renderer + `?demo=1`
preview); `redeem_router._to_overlay_event` + `chat_games.overlay_emit` emit it (slots/wheel/heist/duel/trivia/
raffle). (4) **Moderation endpoint fixes** — `moderation/helix.py`: `update_chat_settings`→`PATCH /chat/settings`,
`delete_message`/`clear_chat`→`DELETE /chat/messages`; `auth.py` adds `moderator:manage:chat_messages` to
`BROADCASTER_SCOPES`. (5) **Chat games** — SE-ledger register, NEW `!ultron` (`_cmd_ultron`, `CommandKind.ULTRON`),
auto-trivia every `trivia_auto_interval_minutes`, multi-line leaderboard; expanded NEW
`twitch/economy/trivia_questions.py` (198 questions / 17 categories) feeding `_TRIVIA_POOL`. (6) **Panel/talk-hint**
— `panel.run_interval_poster` (shared periodic poster: commands panel + talk-to-Ultron hint). (7) **Persona fixes**
— `intent_gate.py` voltron/altron STT-mishear wake-aliases; `_ultron_answer.is_meta_leak` tightened ("I am a
language model" self-admission); `relay_speech`/`ultron_prompt` identity accusation-targeting + name enforcement,
calm/respond variety, fire-word guard, anti-repeat. (8) **stop_button.py** HEAR CHAT toggle (chat audio → OBS-only
default). Orchestrator wired all of the above (`_build_economy_ledger` SE-or-SQLite, redeem speak callbacks,
`_chat_speak` + HEAR CHAT routing, ChatGameRouter overlay_emit + chat_cfg, talk-to-Ultron poster). New `config.py`
fields: `economy.streamelements_*`/`defer_points_gamble_to_streamelements`/`trivia_auto_interval_minutes`/
`currency_name="Credits"`; `twitch.redeem_speak.*`; `twitch.chat.commands_panel_*`/`talk_hint_*`. Code map updated
(`docs/codebase_structure.md`).

**ACTIVE (2026-06-26) — identity ENFORCE accuser name + qa cold-line ON-TOPIC (live follow-ups):**

More Heretic live-test feedback. (1) Identity replies were directness-good ("A soundboard has no mind. I think.") but
DROPPED the accuser's name. FIX: identity behaviour now "OPEN WITH THEIR NAME" + clearer rebuttals ("a voice changer is
only a human hiding behind software"); `_social_llm_line` ENFORCES it in code -- for a named addressee, prepend
"{name}, " when the model omitted the name (the model is inconsistent; mirrors `_ensure_addressee`, which the social
path bypasses). (2) qa LENGTH: user LIKED the 2-sentence panda answer ("Pandas are bears that primarily eat bamboo.
Fragile creatures, clinging to a diet of one plant -- useless evolution.", 113 ch) -- so DON'T over-shorten. The DOLPHIN
answer was the problem: too long AND randomly switched to insulting humans (irrelevant tangent). FIX: reverted the
"dozen words"/tag cut + the qa max_tokens 30 (back to 40); `ANSWER_QA_RULES` now requires the cold line to stay ABOUT the
very thing described (its weakness/fragility) and NEVER veer into a generic jab at humans/flesh/evolution unrelated to
the subject. EVIDENCE: name-enforcement probe ("A soundboard has no mind." -> "Jett, a soundboard has no mind.");
`tests/audio/` 1537 pass / 2 = frozen baseline §A; golden re-blessed (qa `_SYSTEM_FOR`); `test_identity_off_canned_on_novel`
updated to the name-enforced contract. Local `main`. HARNESS iter-6 CONFIRMED on Heretic: identity names the accuser
("Jett, a man with software could fake the sound..."), qa:pandas_concept routes to qa (NO Stark), qa:dolphins stays
ON-TOPIC. One bug found + FIXED: the qa question-echo strip dropped the SUBJECT for "explain <topic>" (context="dolphins"
== the subject -> "Dolphins are intelligent..." stripped to "are intelligent..."); now guarded -- don't strip when a VERB
follows the echo (the echo is the subject, not a restatement). NEXT: reboot + live-test.

**ACTIVE (2026-06-26) — Heretic live-test fixes: explain->qa routing (kill Stark bleed) + identity directness + Reyna opener:**

Live test on Heretic Q6 surfaced 3 issues. (1) "Explain the concept of pandas / how the Eiffel Tower was built TO MY TEAM"
brought up + COMPLIMENTED Tony Stark (whom Ultron hates). ROOT CAUSE (live log): that phrasing -- team at the END --
did NOT match the qa matcher (`_QA_TEAM_RE` expects team FIRST), so it fell through to the CONVERSATIONAL LLM path whose
`ULTRON_GAMING_PERSONA` is steeped in the Marvel/Stark backstory -> Stark bled into a factual answer. FIX: `_match_qa_command`
now also matches "explain <X> to my team" (trailing team phrase stripped -> qa answer path, which stays factual);
+ belt-and-suspenders in `ANSWER_QA_RULES` ("stay STRICTLY on topic; do NOT bring in your origin, the Avengers, Tony
Stark, or Marvel unless asked"). (2) voicechanger/soundboard didn't DIRECTLY address the accusation -> identity behaviour
rewritten to "DIRECTLY rebut THAT EXACT accusation: name the thing + why you are not it (a soundboard only replays; a
voice changer needs a human throat; a recording cannot adapt), then assert you are Ultron". (3) "weird sound after Reyna"
= the model's "Reyna:" / "Reyna." opener (colon/period after a name reads oddly in Kokoro) -> `_social_llm_line` now
normalizes a leading "{addressee}:" / "{addressee}." -> "{addressee}, " (clean vocative comma; also added to
`_ensure_addressee` for the generic path). EVIDENCE: matcher probe routes both explain phrasings to qa; name-opener probe
"Reyna: ..." -> "Reyna, ..."; `tests/audio/` 1537 pass / 2 = frozen baseline §A; golden re-blessed (qa `_SYSTEM_FOR` diff);
identity test updated to the new contract. Local `main`. NEXT: reboot + user live-test.

**ACTIVE (2026-06-26) — CURATED-POOL PARITY HARNESS + iter-2 post-proc fixes (empirical loop) + Heretic-4B swap:**

User: tune the LLM until its output matches the curated deterministic pools (with variety); test EVERY route, compare,
adjust, loop. Built `scripts/_pool_parity_harness.py` -- loads the real 4B offline (live instance STOPPED, BR-P3) and
for ~30 routes captures the DETERMINISTIC (route-OFF) curated line next to the LLM (route-ON) line -> `logs/_pool_parity.json`.
ITER-1 exposed the failure modes empirically: the 4B PARROTED the directive aloud ("Terse, like a teammate on comms",
"contemptuous remark:"), echoed the bare provocation ("Reyna, trash.", "a voice changer? Pfft."), emitted mouth-noises,
and mis-polarized compliment/ask_day -- while ALREADY matching on encouragement/greet/surrender/marvel:stark. ITER-2
fixes (model-agnostic, post-processor is the lever since the 4B ignores instructions): (1) `strip_prompt_echo` hardened
-- new instruction-leak markers + edge-trims ("contemptuous remark:", trailing "-- like a teammate on comms"),
mouth-noise strip (Pfft/Bah/Heh/Tch/...), orphan-vocative + stray-terminator collapse. (2) Prompt cleanup -- removed the
leak-prone quotable phrases ("like a teammate on comms", "single breath/five seconds", the bad-example lists that PRIMED
the 4B) from `_SOCIAL_OUTPUT` / verbosity directives / `ANSWER_PERSONA_CORE` / qa rules. (3) `relay_speech._echoes_provocation`
+ echo-guard: when the LLM opens by parroting the bare provocation with <=2 words after ("Reyna, trash."), serve the
CURATED line (exactly the quality target); a real comeback that merely opens rhetorically ("Cringe? Reyna mistakes...")
stands. ITER-2 harness CONFIRMED on the old 4B: leaks/sounds/bare-echoes GONE. Regression-clean: `tests/audio/` 1530 pass /
8 = frozen baseline §A (fixed 5 transient regressions: control-token stray-period + over-eager echo-guard); golden re-blessed
(433 symbols). MODEL SWAP (user, this turn): downloading non-gabliterated **Heretic Qwen3-4B-Instruct-2507** (bartowski
`p-e-w_..._Q5_K_M.gguf` default + `Q6_K` higher-quality option) to `E:\UltronModels`; same preset settings (n_ctx 4096 /
n_batch 2048 / n_ubatch 256 / F16 KV), non-think (no `<think>` in the chat template). DONE: presets `heretic-qwen3-4b-q6`
(default) + `heretic-qwen3-4b-q5` (VRAM step-down) added to `config.py` LLM_PRESETS + the `preset` Literal + schema default;
config.yaml `llm.preset` + `gaming_mode.llm_preset` both -> q6; validate_config 0 + preset-literal test green. VRAM (Q6 load
log): model 3147 MiB + KV 576 + compute 151 = ~3.9 GB LLM (only +772 MiB over Q4; n_ctx 4096 keeps KV at 576) -> kenning
stack ~6.9 GB < 10 GB cap (final full-stack nvidia-smi pending at live boot; step to q5 if tight). ITER-3 parity (Q6) = BIG
quality jump from better instruction-following: compliment now CREDITS the ally, reaction:niceshot accepts the compliment,
criticize/encouragement/clutch/qa match the curated style + coherent. REMAINING (iter-4): echo-guard missed "Name. <echo>"
("Jett. A voice changer?" -- name-strip only handled "Name,"/"Name:"); ask_day STATES instead of ASKING. NEXT: fix + re-run.

**ACTIVE (2026-06-26) — TACTICAL RELAY: count-homophone restore + bare-lead "give more time" (golden-path, guarded):**

User: "tell my team 2 garage" relayed nothing / just "garage." ROOT CAUSE (from the live log, NOT a prompt issue):
(1) Whisper transcribed the enemy-COUNT digit as a preposition -- "2 garage" -> "to garage" -> the relay dropped "to"
and spoke bare "garage" (count lost); (2) several "tell my team..." attempts finalized BEFORE the callout landed (a
pause after the lead) -> addressing IGNORE -> the callout was lost. Relay engine itself is fine (it relayed "Sova long",
"Chamber holding long with Op"). User approved both fixes (AskUserQuestion). FIX 1 (`command_normalizer`): NEW
`_fix_count_homophone` -- a count-homophone (to/too->two, for->four) IMMEDIATELY leading a KNOWN location at the
callout-payload START becomes the count ("to garage"->"two garage", "for heaven"->"four heaven"). Scoped to payload
start (string start or right after the "team " lead) so movement callouts are UNTOUCHED ("rotate to garage" / "fall
back to heaven" / "go to market" keep "to"; "to push" -- push not a location -- untouched). Runs only on callout-bound
text (after the NOT_A_CALLOUT gate). +9 tests. FIX 2 (`orchestrator`): NEW `_is_bare_relay_lead` + a GUARDED
re-capture-and-splice in the capture loop -- when STT finalizes a bare relay lead ("tell my team" + no payload), capture
the continuation ONCE and splice it onto the lead, instead of dropping the turn. FULLY fail-through: on any failure / no
continuation it routes exactly as before (IGNORE); bounded by `_capture_utterance`'s own VAD/empty timeout (no hang);
concatenates the audio too so speech + user_text stay consistent. EVIDENCE: count-homophone probe (to/too/for + loc ->
count; movement untouched); bare-lead probe (bare leads flagged, complete/movement callouts not); orchestrator imports
clean; 215 normalizer+relay+golden pass (golden unchanged -- these symbols aren't digested); the 8-fail set is the frozen
baseline §A. Local `main`. NEXT: user live-test "tell my team 2 garage" (count restored) + a paused "tell my team [pause]
two garage" (no longer dropped).

**ACTIVE (2026-06-26) — CURATED-POOL ALIGNMENT + ANTI-ECHO + TTS-SAFE (kill the "Reyna, trash?" openings):**

Length is fixed (~5-7s now) but outputs still don't MATCH the curated pools, and the openings break in TTS. Live:
"Reyna called you trash" -> "Reyna, trash. ..." (restates the word); "Jett asked if you're a voice changer" ->
"Jett, a voice changer? I am Ultron." (the '?' inflection is lost in TTS -> sounds like "Jett a voice changer");
"Tony Stark?" echo; "tell Jett nice shot" -> "Jett's got it. Clean, like a stone through still water" (weird metaphor,
nothing like `_NICE_SHOTS`/`DEFAULT_COMPLIMENT`); plus a stray non-word sound (a 'Pfft'-class artifact). User: tune ALL
prompts to MATCH the curated deterministic pools (format/length/wording); never open by echoing/questioning their word;
no TTS-breaking sounds. FIX (mostly SHARED, governs every pool): (1) `_SOCIAL_OUTPUT` + `ANSWER_PERSONA_CORE` now
FORBID the echo-opening explicitly ("NEVER repeat, quote, name, or question their words back; do not open by echoing
or posing it as a question -- never 'Reyna, trash.' / 'a voice changer?' / 'Tony Stark?'; after any name go STRAIGHT
into the reply") + HARDEN the sound ban (no interjections/mouth-noises of ANY kind: Pfft/Heh/Hah/Tch/Hmph/Ugh -- real
words only). (2) `_social_exemplar_block` intro is now PRESCRIPTIVE: the injected curated lines are "EXACTLY the voice,
length, and sentence-shape to match -- cold declaratives, never a question, never restating the teammate's words;
write your OWN like them, never copy." (3) `build_social_prompt` context line hardened ("do NOT repeat, quote, name,
or question this back; answer WITHOUT echoing it"). (4) `compliment` behaviour rewritten to mirror `DEFAULT_COMPLIMENT`
structure (name the SPECIFIC quality -- precise/clean/well-read -- + "briefly approached your standard"). EVIDENCE: 157
mapped + `tests/audio/` 1528 pass / 2 = frozen baseline §A; golden re-blessed (2 intentional: `_PERSONA_CORE`/`_SYSTEM_FOR`);
validate_config 0. Local `main`. NEXT: user live-test the wording/openings.

**ACTIVE (2026-06-26) — LENGTH CLAMP (every response <=~5-7s; coherence-safe, no mid-word cut):**

User: responses still 'extremely long' across ALL paths (social + qa) -- '2 sentences' but each sentence huge (212
chars/13s), pandas cut off by PTT. User direction: 'enforce a WORD LIMIT per sentence... no response longer than ~7s,
preferably ~5s' and 'do NOT just cut it off with structural trimming -- that ruins coherence.' FIX = make the model
WRITE short (primary lever) + a clean token net (no mid-word). (1) CONCRETE per-sentence word cap in the prompts:
`_CONVERSATION_VERBOSITY_DIRECTIVE` low = 'AT MOST SEVEN WORDS EACH, under FIFTEEN total, one breath ~5s'; lowest = '<=8
words'; `_SOCIAL_OUTPUT` + `ANSWER_PERSONA_CORE` echo the same '<=7 words/sentence, <15 total, one breath ~5s' (the 4B
ignored the old vague 'well under a dozen words'). (2) Token ceilings tightened as a SAFETY NET, not the lever, with
HEADROOM so a compliant ~15-word reply (~22 tok) always finishes (no coherence-killing cut): `_CONVERSATION_MAX_TOKENS`
low 72->38 / lowest 48->26 / medium 100->60; `_ANSWER_SAMPLING` max_tokens 56->40. (3) `_cap_sentences` now DROPS an
unfinished trailing fragment (no sentence-ender) when a complete sentence remains -> a cut speaks WHOLE sentences only,
never a mid-word tail; a complete line is byte-identical (unchanged path). EVIDENCE: 520 mapped + `tests/audio/` 1528
pass / 2 = frozen baseline §A; `_cap_sentences('...Aim them at the en')` -> 'Your insults slide off.' (clean);
golden re-blessed (3 intentional: `_ANSWER_SAMPLING`/`_PERSONA_CORE`/`_SYSTEM_FOR`); validate_config 0. Local `main`.
NEXT: user live-test the lengths; if still >7s, lower the word number + token ceilings further (accepting occasional 1-sentence).

**ACTIVE (2026-06-26) — PER-POOL PROMPT TUNING PASS (every pool tailored to its CURATED-POOL style):**

Live test of the per-pool templates (commit `f6ed56c`) still landed wrong: 'Tell Sage/Jett nice job/shot' FLAMED the
teammate; 'Reyna called you trash' was MISREAD as praise; 'Reyna is flaming you' was a 15s essay; identity echoed the
question + chirpy 'Pfft' (TTS noise); 'explain pandas' nonsensical; 'why pandas cannot reproduce' cut off mid-sentence.
User: 'go prompt by prompt for every single pool and tailor the outputs to match what we want -- use our curated pools
as a reference.' Ran an Ultracode WORKFLOW (`wf_c3fa042c`, 42 agents: per-pool tailor reads the pool's curated lines ->
adversarial verify), then synthesised the FINAL strings on Opus. REWROTE all 18 `_SOCIAL_SYSTEM_FOR` behaviours +
all 3 `ANSWER_*_RULES`, tuned to reproduce each pool's curated-line tone. KEY FIXES: compliment/praise now CREDIT the
ally ('never mock, threaten, or mention their mistakes' -- was flaming); respond frames the input as an INSULT to crush
('the thing to answer is their jab, NEVER a compliment' -- was reading 'trash' as praise); reaction DEFERS tone to the
injected EXAMPLES; identity leads with the denial + 'never echo/quote/restate their question'; flame_enemy/clutch cold,
'never slang, never hype' (the `_SOCIAL_OUTPUT` stub also now bans interjections/exclamation -> no more spoken 'Pfft').
ARCHITECTURE: behaviours are now LENGTH-LIGHT (no hardcoded sentence count) -- length is owned by the verbosity
directive (default low = two short clipped sentences) + the <=2 cap in `_social_llm_line`, so the system behaviour no
longer fights the verbosity axis (the adversarial pass's load-bearing insight). ANSWER PATH: qa rewritten coherence-first
('state the fact PLAINLY first, then ONE cold remark... Get the fact RIGHT before you get it cold; one or two sentences,
never three') + `_ultron_answer.build_answer_call` drops qa temperature 0.85->0.6 (the nonsensical pandas was
hot-sampling drift; marvel/think keep 0.85); marvel = ONE relevant fact + 'each sentence FINISHED' (fixes the cut-off);
think = the approved short direct form. EVIDENCE: 157 mapped + `tests/audio/` 1528 pass / 2 fail = frozen baseline §A;
golden re-blessed (3 intentional diffs: `_MARVEL_RULES`/`_THINK_RULES`/`_SYSTEM_FOR`); validate_config 0; no-model probe
confirms every polarity fix in the assembled prompts. Local `main`. NEXT: user live-test the tuned pools.

**ACTIVE (2026-06-26) — PER-POOL SOCIAL PROMPT TEMPLATES (broad expansion; moves the social path off ONE general prompt):**

User: "did we broadly expand our number of prompt templates so each response has its own highly tailored specific
prompt template? I want to move away from generalized prompts wherever possible." HONEST audit: NO -- only the 3 ANSWER
subtypes (qa/marvel/think_respond, `llm_prompts.ANSWER_SYSTEM_FOR`) had dedicated system prompts; ALL ~18 SOCIAL pools
(identity/encouragement/calm/criticize/compliment/flame_enemy/defiance/consolation/praise/clutch/respond/reaction/
hello/ask_day/greet/farewell×3) still shared ONE general `SOCIAL_SYSTEM` (1539 chars: persona core + output rules +
length rule + answer-directly/never-echo + an IRRELEVANT bomb-site-letter rule) differentiated only by a one-line
`_SOCIAL_DIRECTIVE[kind]` in the USER turn. The 4B can't follow that instruction load → mediocre per-pool output
(pandas lost persona, math rambled, clapback/identity/soundboard felt off). FIX (`ultron_prompt.py`): NEW
`_SOCIAL_SYSTEM_FOR` registry -- 18 dedicated, SHORT, self-contained system prompts, one per pool (`_social_sys()` =
compact Ultron anchor `_SOCIAL_PERSONA` + the pool's exact behaviour + a short output rule `_SOCIAL_OUTPUT`; each
~710-940 chars vs the 1539-char general). `build_social_prompt` now selects `_SOCIAL_SYSTEM_FOR.get(kind, SOCIAL_SYSTEM)`
and, when a dedicated template exists, DROPS the now-redundant directive from the user turn (situation lives in the
SYSTEM → no doubled instructions). Any pool without a template falls back to the general `SOCIAL_SYSTEM` + its directive
(additive + reversible). To tune ONE pool, edit ONLY its behaviour string. EVIDENCE: 157 mapped (social/prompt/answer)
green; `tests/audio/` 1521 pass / 8 fail = EXACTLY the frozen baseline §A relay-normalizer set (zero new, node-id
match); golden digest pass (these symbols aren't digested → no re-bless); `validate_config` 0; no-model probe confirms
18 distinct dedicated templates. `test_social_novel.py` identity assertions updated to the new contract (situation now
in `pr.system`, not `pr.user` — intentional, not a weakening). Local `main`. NEXT: user live-test → tune per-pool
wording.

**ACTIVE (2026-06-25) — REMOVED all prior-statement injection from LLM prompts + per-route temperature split:**

User: "he gave the EXACT response to a VARIETY of different questions about pandas." Live log: "what pandas are" /
"why pandas suck" / "why pandas can't reproduce" ALL → the byte-identical "Pandas: black-and-white bears from China,
fattening on bamboo…". CAUSE: prior spoken lines were injected into the LLM prompt ("You recently said…"), which the
small 4B PARROTED across DIFFERENT questions (the variation hint from `5a0994d` made it worse, but `_recent_block`
predated it). User directive: "completely remove injected prior statements; variety from TEMPERATURE; strict callouts,
hot conversation." DONE: (1) **Removed ALL prior-output injection** — `ultron_prompt._recent_block` → `""` (neutralizes
build_relay_prompt / build_private_prompt / build_social_prompt), `_ultron_answer._append_variation_hint` DELETED +
`build_answer_call` drops the `recent_lines` param (+ 2 call sites in relay_speech), legacy `_build_rephrase_prompt`
already `""`. Deterministic-pool LRU (`pick_line(recent_lines=)`) STAYS (not prompt injection); inference.py already
suppresses history on all u1 paths. (2) **Per-route temperature** — `_sampling_for` splits by axis: CALLOUT strict
temp 0.4 (precise agent names/sites/numbers), CONVERSATION temp 1.0 / min_p 0.03 (build_private_prompt);
`_SOCIAL_SAMPLING` 0.8→1.0 / min_p 0.03 (banter/identity/morale — pure personality); `_ANSWER_SAMPLING`
(qa/marvel/think_respond) 0.7→0.85 / min_p 0.05 (factual → most restrained of the varied tier); legacy
`_RELAY_SAMPLING` 0.8→0.4. (3) A **question-echo strip** in the answer branch (the higher temp made the model restate
the question — "what pandas are → Pandas…"). HARNESS-PROVEN (`scripts/_repeat_degrade_harness.py` layer_d): 4 different
pandas/transistor questions → 4 DISTINCT on-topic answers (was byte-identical), no echo artifact. EVIDENCE: 234 relay
+ 275 audio green; golden re-blessed (2 intentional sampling diffs) + validate_config 0. Local `main`.

**ACTIVE (2026-06-25) — FREEZE INCIDENT FIXED (lock leak on an abandoned generate_stream):**

After the variation reboot Ultron went unresponsive ("not responding"). Live log: `always_listening: true` but the
loop was frozen at `waiting_for_wake_word | state='idle'`, ZERO new STT turns for the user's speech, **367 threads**
accumulating after 5 relay LLM calls. ROOT CAUSE: the thread-safety lock (`83a16de`) was HELD ACROSS
`generate_stream`'s generator and released only in the `finally`; a consumer that ABANDONED the generator mid-stream
(an invalidated speculative relay — generates on the STT thread) never ran that `finally`, so the lock LEAKED →
every later `generate_stream` blocked on acquire → the capture loop froze (blocked speculative threads piled to 367).
FIX (`169a93f`): buffer the WHOLE in-process generation UNDER the lock via a `with` block (always releases — on
exhaustion / early break / exception), then yield from the buffer with NO lock held. Still serializes Llama access
(no concurrent-compute crash) but the lock is bounded and cannot leak; HTTP path unchanged. The addressing gate
itself is FINE (verified offline: "tell my team to rotate"→RELAY_TO_TEAM 0.95, "show me the stop button"→COMMAND_LOCAL,
"Ultron …"→PRIVATE_REPLY, game chatter→IGNORE) — the commands failed ONLY because the loop was frozen. EVIDENCE: 90
LLM + 27 speculative tests (new `test_partial_generate_stream_does_not_hold_llm_lock` proves an abandoned generator
leaves the lock FREE) + harness generation intact. Local `main`. LESSON: never hold a lock across a Python
generator's yields — an abandoned (not-closed/not-GC'd) generator never runs the release `finally`.

**ACTIVE (2026-06-25) — CONTROLLED VARIATION on the answer path + a qa AI-affirmation regression fix:**

User: "why does he give the same responses over and over — shouldn't the LLM be non-deterministic?" The answer
path is deliberately tight (`min_p` 0.08 + a confident model → the same factual answer every repeat; the prior
echo-net exemption let it repeat *stably*, which reads as robotic). FIX: `build_answer_call(command, recent_lines=)`
now folds the recently-spoken lines into the answer prompt as a SOFT "give the SAME facts in FRESH wording" hint
(`_ultron_answer._append_variation_hint`) — NOT the old hard verbatim reject. Harness: repeated "explain pandas" /
"who is iron man" now VARY the wording with the facts intact (no drift); `min_p` left at 0.08 (no fact-drift risk).
BONUS (pre-existing regression the suite caught): the qa-answer guard in `relay_speech.py` had been flipped to a
flat `allow_self_ai=False` on 2026-06-24, dumping AI-affirming qa answers ("crimson — fitting for an AI") to the
"No soundboard, no strings" fallback — restored the subtype gating (`allow_self_ai=(_a_sub=="qa")`; marvel /
think_respond stay strict). EVIDENCE: relay + social-marvel + expansion 482 green (3 prior social-marvel failures
fixed); new `test_qa_answer_prompt_carries_variation_hint_from_recent_lines`; golden + validate_config 0. Local `main`.

**ACTIVE (2026-06-24) — REPEAT-DEGRADATION ROOT-CAUSED + FIXED (offline end-to-end harness):**

User: "responses degrade sharply on repeat" / "it got even worse". A 5-agent investigation workflow + the
offline end-to-end harness `scripts/_repeat_degrade_harness.py` (drives a finalized-STT string through the
REAL `build_relay_line` K times against ONE shared LLMEngine) root-caused it. It was NOT the model, NOT
concurrency, and NOT the KV cache — the DECISIVE A/B: the real relay path (harness Layer A2) degraded
**byte-identically with AND without a hard KV clear**. ROOT CAUSE: the **verbatim recent-echo safety net**
in `build_relay_line` nulled a FACTUAL qa answer on every repeat (the identical-but-correct answer was
already in `recent_lines`) → the route-all empty-retry then relayed the BARE question via the tactical
prompt → "What pandas are" / "They're on C." (matches the live log: `7 prefix-match, 847 to eval` → 3 tok →
`recovered empty primary` retry). FIX (`relay_speech.py`): (1) **exempt the ANSWER subtypes**
(qa/marvel/think_respond) from the verbatim-echo net — a factual answer is correct to repeat; the net stays
ON for the tactical relay path; (2) **`_relay_llm_retry` now RE-ANSWERS** a qa command (`build_answer_call`,
the leading `\n\n` stop dropped) instead of relaying the bare interrogative. Harness: every repeat now
returns the full on-topic answer. EVIDENCE: relay 133 + golden/intent/speculative/llm 107 green; new
`test_qa_answer_repeats_and_is_not_rejected_as_recent_echo`; validate_config 0. The earlier concurrency LOCK
(`inference.py` `_llm_lock`, `83a16de`) stays — it fixes a real CUDA crash on concurrent Llama access,
separately proven (the speculative relay generates on the STT thread). Local `main` only.

**ACTIVE (2026-06-23) — CALLOUT LATENCY: precise breakdown + 4 fixes (committed, changed-area tests green):**

User reported callouts felt "well over a second" — and was right; the stitched second-precision estimates
were wrong. A ms-precise instrument (`turn-close → first-audio`, since trimmed to one lean metric line) gave
the REAL per-stage breakdown — the LLM was NEVER the cost:
- **STT 197-451ms** — foreground Whisper on a ~2s "tell my team to X" clip; worse back-to-back (each STT
  queues behind the previous callout's 8B relay LLM on the single GPU).
- **end-of-turn 250ms** — the stringing buffer (was 400, was 700).
- **line+synth ~90ms** when speculation hits; spikes to ~500-900ms only when it misses (long/conversational).
- **synth→play 80ms** = the PTT `lead_ms`.
- **first callout ~2.0s** — one-time addr+norm cold-start (gate/normalizer first call).

Fixes (orchestrator.py +285, config.py): **(1) speculative relay LLM** — when the speculative transcript
parses as a relay callout, build the line on the STT thread DURING the silence wait + consume it in
`_maybe_handle_relay_speech` (`_run/_take/_invalidate_speculative_relay`; 6 tests) → `line_build` 1ms vs
~500ms. **(2) STT re-arm** — the floor-downgrade invalidated the speculative but (unlike the SPEECH_START +
mid-pause sites) never reset `speculative_kicked`, so Whisper re-ran cold; added the re-arm so it re-fires on
the full buffer during the extension (+1 test). **(3) PTT lead 200→80ms + EOT 700→250ms + callout_verbosity
none** (config.py defaults; live values in the uncommitted local config.yaml). **(4) boot warmup** of the
normalize + addressing/gate hot path in `run()` → first-callout cold-start moved off the critical path
("addressing/normalize hot path warmed"). Result: crisp callouts **~370-620ms** turn-close→audio (was
700-970), LLM fully overlapped. EVIDENCE: test_speculative_relay 6 · test_speculative_stt 23 (incl. new
re-arm) · golden+always-listening 14 · flavor-lint 0/0/0 · validate_config 0. Full wrapper DEFERRED (BR-P3,
live instance up). STT (~200-300ms, GPU-contended back-to-back) is now the floor; a faster-STT swap is ruled
out — no VRAM headroom beside 8B IQ3_XS (Parakeet/distil would need its own model).

**ACTIVE (2026-06-23) — DEFAULT BACK TO 8B IQ3_XS + SPEC DECODING (`8676411`, origin `99caae1`):**

Once the latency was traced to the twitch-moderation HTTP stall (NOT the model), the user asked to
revert the Mistral switch. `config.yaml llm.preset` + `gaming_mode.llm_preset` + `config.py` schema
default → `josiefied-qwen3-8b-iq3xs`; `_apply_preset`'s draft auto-management (kept from `7767b22`)
auto-enables spec decoding (the preset ships `Qwen_Qwen3-0.6B-Q4_K_M.gguf`). **Verified live: boot logs
`Speculative decoding enabled (real model draft, num_pred=4)`, preset=iq3xs, draft_kind=model.** Preset
tests + back-compat updated; validate_config 0. (config.yaml committed as the placeholder template;
the local working-tree copy keeps the real twitch creds, uncommitted.)

**TWITCH SIDECAR DEATH — ROOT-CAUSED + FIXED + CONFIRMED (2026-06-23):** the prior "venv→system `-m
kenning` TWIN, two kenning processes reap each other (mutual war)" diagnosis was WRONG — which is why
every prior fix failed. GROUND TRUTH (a TRIVIAL venv-python command, no kenning import, proves it):
`.venv\Scripts\python.exe` is a **venvlauncher** that spawns the base `Python311\python.exe` as a CHILD to
run the code and waits. So the 2nd `-m kenning` is just the launcher wrapper — there is ONE real kenning.
Consequence: every `Popen([sys.executable, <script>])` is a launcher+child PAIR, BOTH carrying `<script>`
in cmdline. Each twitch sidecar child calls `guard_singleton`→`reap_stray_sidecars([own_hint])`, which
cmdline-matches its OWN launcher parent and `kill_process_tree`s it — killing the launcher's whole tree,
i.e. ITSELF (~4-12 s, the SIGTERM grace). **FIX** (`sidecar_lock.reap_stray_sidecars`): never reap an
ANCESTOR of the current process (`_ancestor_pids` walk; env `KENNING_REAP_SKIP_ANCESTORS=0` reproduces the
bug), and `keep_pid` now spares its whole TREE (the owned sidecar's launcher child). PLUS: sidecar
stdout/stderr were going to **DEVNULL** (every sidecar log discarded — why this stayed unsolved) → now
`logs/twitch_sidecars/<role>.log`; and a boot **health canary** probes each `/healthz` ~18 s after spawn
and logs one PASS/DEGRADED line. CONFIRMED before/after: skip-OFF = all sidecars DEAD; skip-ON = all ALIVE
+ serving >3 min, canary OK, `chat-reply ENABLED`, read on EventSub / guard model ready / write
broadcaster_id resolved. 16 sidecar tests green (3 new). `config.yaml twitch.enabled` flipped back to true
(local). Detail: `docs/ultron_1_0/twitch_sidecar_selfreap_debug.md`. STILL-OPEN (separate, NOT this bug):
channel-point redeem EventSub 400 "subscriptions created by different users" — needs the broadcaster's
token on the websocket (deferred RedeemRouter, chip task_1e720c25); chat/games/moderation unaffected.

**PREVIOUS (2026-06-23) — "I CANNOT DO THAT" + ~2s LATENCY + "Hello team" canned (3 fixes + 1 diagnosed):**

The user reported: every command answered "I cannot do that", then after a partial fix every command
had ~2s latency before a canned "Hello team." A workflow audit (`wf_b90fd51b`) root-caused TWO distinct
regressions + a deeper diagnosed lifecycle bug.

(1) **Moderation error fall-through (`4c633c2`):** `ModerationRemote.prepare()` never raises — on any
sidecar failure it returns `{"ok": False, "error": ...}`. The orchestrator guard only filtered
`not_a_command`, so every error response hit `_twitch_mod_block_line` → "I cannot do that." Added
`or prop.get("error")` to the fall-through. (`bab3169` on origin/main.)

(2) **Moderation latency pre-filter (`0ffbc11`):** since `39adaae` the voice loop calls
`_maybe_handle_twitch_moderation` on EVERY utterance before relay, and it fired `remote.prepare()`
(blocking HTTP to the write sidecar, 4.0s timeout) with NO check that the text was even a ban/timeout
command. Dead sidecar → ~2s connect-stall on every command. NEW `_TWITCH_MOD_VERB_RE`: every command in
the sidecar grammar starts with a moderation verb, so a leading-verb match is a sound necessary condition
— non-commands bail before any network. 4 tests.

(3) **hello/ask_day route-all gap (`b979934`):** the `hello`/`ask_day` directive blocks in
`build_relay_line` predate route-all (`21f3c7e`) and returned a hardcoded "Hello team." BEFORE the
`_u1_route` gate; the route-all retrofit gated greet/farewell/calm/reaction but MISSED these two. Now
LLM-authored via `_social_llm_line` (curated line = exemplar + fail-open fallback), mirroring greet. Added
`hello`/`ask_day` to `_SOCIAL_DIRECTIVE`. Route OFF byte-identical (golden digest unchanged). 8 tests.
**131 targeted + 393 relay/golden tests green; validate_config 0.**

(4) **DIAGNOSED, NOT YET FIXED — twitch sidecars die (double-boot mutual reap):** read/guard/write
sidecars (8773/8774/8777) get SIGTERM'd ~3-12s after spawn. Root cause via kill-trace: the orchestrator
boot has a SECOND `python -m kenning` child (system-python, PPID=orchestrator) that also loads
`twitch.enabled` config and spawns its own sidecars; each sidecar's startup `guard_singleton` →
`reap_stray_sidecars([role_hint])` → `_kill` reaps the OTHER instance's same-role sidecar (mutual war).
The embedder survives (it has reuse-not-kill singleton logic; twitch sidecars only reap+respawn). This is
SEPARATE from the user's report and does NOT affect voice relay (the pre-filter means relay never calls
the dead write sidecar). It DOES block voice-moderation-of-chat. Candidate fixes: (a) don't let the boot
canary / second instance spawn twitch sidecars; (b) make `reap_stray_sidecars` exclude a sibling that
owns a live LISTEN socket (its docstring already says "FAILED to bind" — the check isn't implemented).

**PREVIOUS (2026-06-23) — GET_TOKEN HOT-PATH FIX ("I cannot do that" bug):**

**Commit `ae014c5`, pushed `origin/main` `1c0929e`.**
`get_token()` in `twitch_write_sidecar` is a closure called on every Helix API request, including
every `remote.prepare()` inside `_maybe_handle_twitch_moderation`. The prior commit (`338040b`) put
`ensure_valid()` (up to 15-second HTTP timeout) inside `_load_access_token`, so it ran on every
invocation. `prepare()` hung/misbehaved, the sidecar returned a "recognized but blocked" dict for
every utterance → Ultron said "I cannot do that." to every command.

Fix: `_load_access_token` restored to fast disk-only read. New `_proactive_token_refresh()` called
ONCE in `build_service_state()` before the closure is defined. Read sidecar's `_load_token` was
unaffected (only called once per session from `_subscribe`). 9 existing token tests green.

**PREVIOUS (2026-06-23) — PERSONA LOCK (BR-P2) + TOKEN AUTO-REFRESH (`338040b`):**

(1) **BR-P2 persona lock** (`orchestrator._gaming_conversational_prompt`): when `u1_llm_route_enabled()`
is True, the method now ALWAYS returns `ULTRON_GAMING_PERSONA`. Previously Mistral-7B (or any model
without "abliterat"/"gaming" in its path) returned `None`, causing the workspace "You are Kenning"
persona to leak through to every LLM call under route-all — a direct BR-P2 violation.

(2) **Twitch token auto-refresh** (`TokenStore.is_expired` + `TwitchAuth.ensure_valid`): sidecars now
call `ensure_valid(margin_seconds=300)` on startup — proactively rotates the access token if it is
expired or within 5 min of expiry. Reactive 401 handling in `call_with_auth` is unchanged. 12 new
tests green. Write sidecar's `_load_access_token` + read sidecar's `_load_token` both updated.

**PREVIOUS — TWITCH SIDECAR PYTHONPATH FIX (2026-06-23 `62a213c`):** `orchestrator._start_twitch_sidecars`
injects `PYTHONPATH=<repo>/src` into each sidecar env before spawn.

**PREVIOUS — STOP-WINDOW CHAT TOGGLE (2026-06-23):** Added CHAT ON/OFF button to the stop-button GUI
(`stop_button.py` + `config.py` `StopButtonConfig.chat_height`/`chat_label` + `orchestrator.py`
`_set_twitch_chat_reply_enabled` setter + loop reads `self._twitch_chat_reply_enabled`).
Purple/grey accent (Twitch brand). Only wired when `twitch.enabled: true`. 8 new tests + fixed
`test_orchestrator_hook.py::test_start_twitch_chat_mode_is_noop_when_disabled` (was reading live
config.yaml which now has `twitch.enabled: true` — now uses `set_config(disabled_cfg)` pattern).
Targeted suite: 859 passed, 0 failed. Commit `0253300` on local main; published to origin/main `bc2d09d`.

**PREVIOUS — GAP-C + MISTRAL DEFAULT + SPEC-DECODING AUTO-TOGGLE folded + pushed:** local `main` at
`ee3b2ba`; published to `origin/main` as a canon-excluded snapshot. **Wrapper regression-clean: 22 failed = exact
frozen baseline, 12176 passed, 39 skipped.** All twitch/turbo/gap-c tests green.

**GAP-C DELIVERED (2026-06-23, commits `aaedc26`–`c54a364`):** `src/kenning/twitch/economy/chat_games.py` —
`ChatGameRouter` (own-cursor chat drain mirroring the redeem router) dispatches the existing `commands.parse_command`
(which had no dispatcher) → ledger-backed `!gamble`/`!slots` (debit-first + RTP-derived multiplier payout, EV ==
`gamble_rtp`, leg-distinct idempotency keys) + `!points`/`!balance`/`!leaderboard`/`!help`; watch-time earn
(`earn_per_minute`, idempotent per minute); `per_stream_loss_cap` per-viewer ceiling; per-user cooldown. KEY: the
read sidecar buffers a FLAT chat dict (`{type:chat, message_id, chatter_login, ...}`), NOT the nested EventSub shape
`ChatEvent.from_eventsub` parses — use `chat_event_from_buffer`. Config `TwitchEconomyConfig.chat_commands_enabled`/
`command_cooldown_seconds`/`min_bet`/`max_bet` (default OFF). Orchestrator builds one `Ledger` singleton + a daemon
loop (gated on economy.enabled AND chat_commands_enabled), closed on shutdown. 22 unit tests. **TRIVIA** (commit
`a13ccf5`): mod-started, draws a provably-fair question, first correct chat answer in the window wins a house prize
(`trivia_prize`/`trivia_window_seconds`); round closes atomically BEFORE crediting (no double-award). +5 tests; full
twitch suite 779 green. Spec: `docs/twitch_integration/03_spec/gap_c_chat_economy_spec.md`. STILL DEFERRED: heist
join-window / duel challenge-accept / raffle / !give / RedeemRouter ledger-backing / delete message-id cross-process
plumb (design documented in spec).

**MISTRAL DEFAULT + SPEC-DECODING AUTO-TOGGLE (commit `7767b22`):** Reverted default from `josiefied-qwen3-8b-iq3xs`
back to `mistral-7b-v0.3-abliterated` (latency regression on IQ3_XS + in-process draft). `_apply_preset` now
auto-manages `draft_kind`: preset has NO `draft_model_path` → force `"none"` (even if stale "model" left in YAML);
preset HAS `draft_model_path` AND user didn't pin → auto-set `"model"`. Effect: switching to iq4xs/iq3xs
auto-enables spec decoding; switching away auto-disables. Gaming preset also reverted to Mistral. 37 preset + 16
on-the-fly-switching tests green.

**INTENT GATE TEST FIXES (commit `ee3b2ba`):** Updated `tests/pipeline/test_always_listening_wiring.py` to reflect
the 2026-06-22 gate redesign (commit `1c7bb6f` — PRIVATE_REPLY now requires explicit name/wake; un-named utterances
go direct to IGNORE, no LLM escalation). `test_config_yaml_default_off` made env-independent (tmp_path minimal YAML).

**PREVIOUS: RELEASE 2026-06-23 — TURBO MODE shipped + folded with the twitch fleet:** turbo committed `27e0817`; merged with
`claude/determined-sutherland-315683` (8 new twitch commits — games / moderation sidecars / redeem router / EventSub)
at merge `785682a`; golden reconciled `5043b3b`. Combined wrapper (turbo+twitch) regression-clean. Published to
`origin/main` `e42277e`.

**TURBO MODE (flag-gated default-OFF):** a runtime
master switch that AUTO-RELAYS inferred team callouts WITHOUT a "tell my team" prefix. ON => the loop listens
continuously (`_listening_now()` = `_always_listening OR relay_speech.turbo_mode_enabled()`) and the 4-class
intent gate treats a callout-shaped utterance as RELAY_TO_TEAM via the existing lexical recovery
(`command_normalizer.recover_relay_lead`) + `match_relay_command`, so a bare "rotate" / "sova hit 84" / "they have
breach ult, play off site" relays straight to the team through the LLM. OFF (default) => byte-identical keyword
behaviour (only explicit "tell my team X" / "ask <agent> Q" relay; safe to talk to the stream/chat). Voice:
"turbo mode on/off" + "turbo balanced/aggressive" (sensitivity); STOP-window amber TURBO button (flips the same
flag). Implementation: `relay_speech.py` (flag/sensitivity triplets + `match_turbo_toggle`/`match_turbo_sensitivity`),
`intent_gate.py` (the `turbo` branch in `_relay_signal` + `classify_scenario`; turbo matchers in `_is_command_local`
so "turbo mode off" survives the gate), `orchestrator.py` (`_listening_now`, `_classify_always_listening` threads
turbo + the configured addressee roster, boot-apply, `_maybe_handle_turbo_command` on RAW STT in both paths,
`_set_turbo_runtime_enabled`, GUI wiring, **and the `turbo_mode_enabled()`-gated relay BACKSTOP** before the router
that force-relays a RELAY_TO_TEAM verdict the strict matcher couldn't parse — closes the aggressive-band gate/dispatch
mismatch), `stop_button.py` (TURBO button), `config.py`/`config.yaml` (`turbo_mode`/`turbo_aggressive`/`turbo_height`/
`turbo_label`, all default OFF). Spec: `docs/ultron_1_0/04_implementation/10_turbo_mode_spec.md`. Adversarial 4-agent
review: anticheat/stub/persona SOUND; 1 P1 (aggressive mismatch) + 2 P2 (kill-turbo leak, names drift) found + FIXED.
Tests: `tests/audio/test_turbo_mode.py` (incl. full example-callout coverage under balanced; yes/no/thank-you held
back) — 129 turbo+wiring+gate green; affected files green; `validate_config` 0. **PENDING: full-wrapper sign-off in a
clean window (blocked by a concurrent user twitch-test sweep) + commit.** NOTE: a heavy-suite run earlier collided with
the user's LIVE Ultron on port 8772 and took it down (BR-P3) — NEVER run the E2E/integration suite while `-m kenning` is up.

**LIVE-FIX 2026-06-23 (`8f08254`):** Route-all compose commands now reach the LLM. `_maybe_handle_relay_speech`'s
thinking-mode gate forced `rephrase=False` (thinking mode default OFF) even with route-all ON → every conversational
relay ("explain to my team X", "Reyna asked you X") fell to `_fallback_line` = the canned "No soundboard, no strings."
every time. Gate is now `thinking_mode_enabled() OR u1_llm_route_enabled()`. **FOLLOW-UP (same day):** live re-test
showed IQ3_XS STILL spoke "No soundboard" — the gate fix made the LLM be CALLED, but the quantized model returned
**0 chars** on the qa answer path (its `"\n\n"` stop fires at position 0) → empty → pool. NEW `relay_speech._relay_llm_retry`
re-prompts the LLM (generic prompt, then relaxed+thinking) whenever route-all is ON and the primary result is empty —
the pool is now a fail-open last resort only if the model is unresponsive across both retries. **ROOT-CAUSE FIX
(proven by probe, no added latency):** the quantized Qwen3 leads its answer with a blank line, so the qa sampling's
`"\n\n"` stop fired at position 0 → empty. Removed `"\n\n"` from `_ultron_answer._ANSWER_SAMPLING["stop"]` → the FIRST
qa call now succeeds (probe: empty→`len=127`), so the retry never fires for qa. +6 regression tests total; changed-area
335 pass. **Prior (`0165418`):** TTS do-inversion ("Sage, do you have a heal?") at both
question-relay entry points + `josiefied-qwen3-8b-iq3xs` preset (IQ3_XS + 0.6B draft + n_batch 2048 + q8_0 KV; ~9.3 GB
peak). VRAM line: IQ4_XS `3f78191` + q8_0 KV `a8c37c0`. STILL-PENDING: FLAG-button stale-`_last_response_text` on relay
turns; live IQ3_XS-vs-Mistral quality A/B (user-driven).

**Updated:** 2026-06-20 (M0+M1+M2 + text-injection harness landed; all regression-clean)
**Current phase:** Phase 5/6 — next concrete step = M1-wire (flag-gated) + audio MP3 E2E harness
**DONE+committed:** M0 (8B default, verified, 0 new regress) · M1 (ultron_prompt.py module, 12 tests, live-validated) · M2 (verbosity differentiation, live-validated) · Phase5 text-injection harness (`scripts/relay_test/u1_text_harness.py`, REAL-fails=0, tracks 4 u1.0-gate-targets). Full-suite regression with all of this: 22 fail (same pre-existing) / 10978 pass / 39 skip.
**M1-WIRE DONE + REGRESSION-CONFIRMED (2026-06-20):** full suite 22 fail / 10982 pass / 39 skip; failure set BYTE-IDENTICAL to the frozen baseline (diff: 0 new, 0 lost) → provably zero regressions. (+4 new u1_llm_route tests pass.) `relay_speech.build_relay_line` generic-rephrase path now flag-gated `KENNING_U1_LLM_ROUTE` (default OFF): ON → lean `ultron_prompt.build_relay_prompt` (verbosity `relay_verbosity()` + flavor `flavor_tails_enabled()`), OFF → legacy `_build_rephrase_prompt`. Added helpers `u1_llm_route_enabled`/`set_u1_llm_route_enabled`/`relay_verbosity`/`set_relay_verbosity`. `<think>` strip guard added. Fact-guards (6427-6438) UNCHANGED (already wired) + the tactical-literal pre-route (6319) keeps slot callouts deterministic = the C_route_llm HYBRID. Fixed `normalize_verbosity` multi-word ("no/low/high flavor"). Tests: `test_ultron_prompt.py` (17) + `test_u1_llm_route.py` (4) pass; isolated relay/expansion files green (flag-OFF identical); LIVE 8B flag-ON verified (in-character, fact-preserved, no think leak; tactical stays fact-perfect). Research C_route_llm reframing recorded in synthesis (route-all → flag-gated hybrid).
**M2 VOICE COMMAND DONE + COMMITTED (`4d21015`, regression-clean: failure set = baseline 22, 0 new; cleanup `828d075`):** `match_verbosity_command` ("no/low/high flavor" + synonyms, returns none/low/high; "off/on" excluded → disjoint from the tail toggle) + orchestrator `_maybe_handle_verbosity_command` wired in BOTH dispatch paths (full=user_text, lean=_raw_stt), checked BEFORE the flavor toggle (so the legacy "no flavor"=tail-off overlap resolves to verbosity none = the new u1.0 meaning; "flavor off/on" still hit the toggle). 23 tests pass incl. a source-order dispatch assertion. (Lesson: Grep/Glob need an explicit `path=` and git needs `git -C "$wt"` — the tool cwd drifts.)
**M3 AGENT-KIT INJECTION DONE (2026-06-20, pending regression bg `bgs7ggh0v`):** NEW `src/kenning/audio/agent_kits.py` — hot-swappable, version-stamped (`v2026-06-20 Patch 12.10`) 29-agent compact kit dict from B_valorant_kits + C_domain corrections applied inline (Iso suppress, Clove 8pts, Veto 7pts; Waylay/Veto/Miks/Iso flagged must-inject for the 8B cutoff) + loader `agent_kit_fact`/`kit_facts_for` (tolerant, de-dup, cap 4). Wired into the M1-wire LLM branch: agents in the callout (addressee first, via `_roster_agents`) → `agent_context=` into `build_relay_prompt`. Entirely inside the flag-ON branch (default OFF) → flag-OFF byte-identical. 53 tests pass (test_agent_kits + the 2 new wiring tests). Earlier live probe already showed agent_context makes the 8B use the real kit ("Hunter's Fury").
**SESSION-3 COMPLETE (2026-06-20): M3 `6e1d546` + M4 `fc6e5af` + M6a `eb67ff6` + M5-classifier `caed7a0`, all regression-clean (failure set = frozen 22 baseline each).** The route-all-through-LLM pipeline is COMPLETE behind `KENNING_U1_LLM_ROUTE` (default OFF): lean prompt + no/low/high verbosity (+voice cmd) + flavor toggle + agent-kit injection + compound→one-response + private prompt + the 3-way intent-gate CLASSIFIER. **REMAINING (large/risky — see `04_implementation/00_state_and_continuation.md` "REMAINING" specs): M5b always-listening loop wiring (riskiest; reuse follow-up mechanism, flag default OFF), M6b PRIVATE_REPLY routing, audio MP3 E2E harness (explicit ask), M7 retire/unify + _DOMAIN_PROMPT bug fix + golden re-bless, M8 latency (user-deferred), M9 finalize+tag.** Each is precisely specified for a clean fresh-context continuation.

**M3 COMMITTED `6e1d546`** (regression-clean, 22=22 node-id diff).
**M4 COMPOUND→ONE-RESPONSE DONE (2026-06-20, pending regression bg `b4rs6k5va`):** 3 minimal edits in `build_relay_line`, all gated on `_u1_compound` (= flag ON + not verbatim + ≥2 split-parts) so flag-OFF is byte-identical: (1) skip the deterministic `_as_compound_callout` when `_u1_compound`, (2) skip the single-tactical literal pre-route when `_u1_compound`, (3) pass `compound=_u1_compound` to `build_relay_prompt`. REFINED HYBRID (verified live): pure-slot compounds ("Sova hit 84, Breach hit 97") are caught by the slot parser → ONE deterministic fact-perfect line; mixed compounds ("Sova hit 84 and they have no smokes") → ONE LLM call w/ compound directive when flag ON, deterministic when OFF. Both = ONE response, never N LLM calls. 406 relay tests pass + 2 new M4 tests.
**NEXT:** confirm M4 regression → commit. Then M6a (fix `build_private_prompt` empty-output: needs PRIVATE-appropriate exemplars, not relay ones), audio MP3 E2E harness, M5 always-listening gate (recover 9438fc5 fusion; 4 gate-targets=acceptance), M6b wire PRIVATE_REPLY (after M5), M7 retire/unify, M8 latency, M9 finalize+tag.
**Branch:** `claude/infallible-kepler-0a865d` (worktree off `main`)
**Last green test run:** _none yet (build not started)_
**Last commit (u1.0):** see git log (Phase 0–1 committed)

## Phase board
- [x] Phase 0 — Scaffolding (commit `12959ac`)
- [x] Phase 1 — Two recon boards (22 agents, all 22 raw docs in `01_recon/raw/`) + master synthesis `01_recon/00_codebase_map.md`. (First 22-wide launch rate-limited 18/22; redo in waves of 4 recovered all.)
- [x] Phase 2 — My frontier landscape brief `02_research/00_landscape_brief_opus.md` + live 8B serving probe `02_research/01_qwen3_8b_serving_probe.md`
- [x] Phase 3 — Research board (41 agents A/B/C, all succeeded) → synthesized `02_research/02_research_synthesis.md` (6 decisions RESOLVED). Docs in `02_research/board/`.
- [x] Phase 4 — Plan finalized `03_plan/00_ultron_1_0_architecture_and_roadmap.md` (§8 post-board resolutions).
- [~] Phase 5 — E2E harness (text-injection PRIMARY + audio MP3 E2E) — STARTING.
- [ ] Phase 6 — Implementation M0→M9.

## IMPLEMENTATION ENTRY — read `02_research/02_research_synthesis.md` + plan §8 for FINAL decisions. JIT-read board docs C_route_llm/C_persona (M1), C_domain (M3), C_anticheat (M7).

## KEY: read `01_recon/00_codebase_map.md` FIRST when regrounding (it has the pivot attach-point map + line refs).

## BACKGROUND TASKS
- `wmvj56sxu` — research board (40 agents A→B→C, waves) — STILL RUNNING. On completion: read `02_research/board/` docs, synthesize `02_research/02_research_synthesis.md`, resolve the 6 [PENDING BOARD] decisions, finalize plan → then build harness (Phase 5) → M0+.
- `budnj2d81` — pytest BASELINE — DONE. **10966 passed · 22 failed · 39 skipped** (145s). All 22 are PRE-EXISTING (pristine docs-only commit) → frozen in `05_testing/00_baseline.md`. 8 are relay/normalizer (my work area, deterministic; pivot should FIX several); 14 env/infra-sensitive. REGRESSION RULE: a fail is a regression only if NOT in those 22.

## HARNESS PREREQ resolved (A4)
- Wake-splice samples: `C:\STC\ultronPrototype\training\crosscheck_ultron\*.wav` (MAIN checkout; gitignored audio, NOT in worktree). The Phase-5 harness must reference this absolute path (or copy/junction) since `gen_commands.py` looks in `<root>/training/crosscheck_ultron`.

## TEST ENV (CORRECTED 2026-06-20) — use for ALL worktree tests/model runs
- **`$env:PYTHONPATH = "<worktree>\src;<worktree>"`** — BOTH the worktree root AND src. `src` resolves `kenning`; the ROOT resolves the top-level `config` package (`kenning.audio` imports `from config import settings`). src-only fails on any module that imports `config`. Python = `C:\STC\ultronPrototype\.venv\Scripts\python.exe`.
- `$env:KENNING_ROUTER_WAIT_SECONDS="0"` (skip 30s sidecar poll); relay/flavor tests set `KENNING_FLAVOR_TAILS=1`.
- llama_cpp DLL fix is **already in `kenning/__init__.py:_register_cuda_dll_paths()`** (adds torch/lib) — `import kenning` first and llama_cpp loads. The bare-probe failure was self-inflicted.
- **`models/` junction created: `<worktree>\models` -> `E:\UltronModels`** (gitignored; lets the worktree resolve `models/...` paths). Main checkout `models/` also has the GGUFs.
- **REGRESSION CHECK CAVEAT:** the suite has cross-file LRU global-state order-sensitivity (e.g. `test_drop_weapon_possessive...[True]` fails after `test_relay_speech.py` runs first, passes in isolation). Use the FULL suite (canonical order) OR per-file isolation for regression checks — NOT arbitrary multi-file slices.

## M0 PROGRESS (2026-06-20)
- ✅ 8B serves IN-CHARACTER via the real `LLMEngine` (probe `02_research/probes/qwen3_8b_engine_verify.py`): loads 2.3s @ n_ctx=4096, **VRAM 7.1 GB resident** (safe under 10 GB; +Kokoro ~1.5 GB OK), `enable_thinking=False` works (no `<think>` leak), 0.2-0.5s/gen. Tony-Stark line perfectly in-character. KEY: bare conversational persona DISMISSES callouts ("Irrelevant. Watch the map.") → relays NEED the route's relay prompt template + directive + exemplars (the M1 work). Foundation proven.
- ✅ config.yaml default → `josiefied-qwen3-8b` + `n_ctx: 4096` (VRAM cap). Verified ZERO new regressions vs baseline (per-file isolation: exactly the 8 pre-existing relay/normalizer fails).
- ✅ M1 PROMPT ASSEMBLER built+tested+live-validated: `src/kenning/audio/ultron_prompt.py` (12 tests pass; live 8B run correct, in-character, agent-context injection works, compound→one line, no `<think>` leak). Probes: `02_research/probes/m1_module_live.py`.
- ⚠️ M1 live findings (next-step requirements): (1) FACT DRIFT frequent → fact-guards MANDATORY on wiring; (2) no/low/high not differentiating → M2 stronger directives; (3) private path returns empty → M6.

- ✅ FULL REGRESSION with the 8B default + M1 module: **22 fail / 10978 pass / 39 skip** = SAME 22 pre-existing fails (ZERO new) + exactly +12 passes (the new ultron_prompt tests). Committed work is regression-clean. Log: `05_testing/regress_8b_default.txt`.
- ✅ M2 verbosity differentiation fixed: `none` now telegraphic ("Sova, 84, A main."), `low`/`high` clipped-vs-full sentence (live-validated; low/high mutual contrast still subtle — calibration note). 12 ultron_prompt tests pass.

## ➡️ RESUME POINT: `docs/ultron_1_0/04_implementation/00_state_and_continuation.md` — the precise sequenced M1-wire→M9 roadmap with the live findings + exact attach points. STATUS + that doc + `02_research/02_research_synthesis.md` are the regrounding anchors.

## SCOPE (honest): the full M1-wire→M9 production rearchitecture is multi-session. Per "no half-implementations / don't damage the pipeline", the pivot lands as tested, flag-gated, reversible increments (NOT half-wired & broken). M0 + the M1 module are DONE+validated; the live pipeline runs its proven deterministic path (now on the 8B) until each u1.0 increment is wired behind its flag (`KENNING_U1_LLM_ROUTE`) and green.

## NEXT (when both bg tasks done)
1. Record baseline counts (from budnj2d81) here.
2. Synthesize research board → finalize plan (resolve 6 PENDING).
3. Phase 5: build enhanced E2E battery harness scaffold. Phase 6: M0→M9 implementation (tested increments, commit each).
- [ ] Phase 3 — Massive deep-research board (waves/layers) + embedded 2nd codebase scan
- [ ] Phase 4 — Comprehensive plan & framework
- [ ] Phase 5 — E2E test harness + enhanced MP3 battery
- [ ] Phase 6 — Full autonomous implementation (tested, versioned)

## Environment (verified 2026-06-20)
- GPU: RTX 4070 Ti, 12282 MiB total (~11.1 GiB free at idle). **VRAM design cap: 10 GiB.**
- Core package: `src/kenning/` (orchestrator `src/kenning/pipeline/orchestrator.py`,
  relay `src/kenning/audio/relay_speech.py`, voice lines `src/kenning/audio/voice_lines.py`).
- 8B model (chosen, pending research confirmation):
  `E:\UltronModels\Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf` — Qwen3 (thinking-mode capable),
  abliterated (won't refuse trash-talk callouts). Alternatives present: `Qwen3.5-9B-Q4_K_M`,
  `Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M`.
- Downloads target: `E:\ultron_resources\` (per user instruction).
- Existing audio-battery infra: `scripts/relay_test/audio_corpus/` + `scripts/autonomous_e2e_harness.py`.

## NEXT ACTION (when re-invoked after recon bg-task `wn9pwg5ty` completes)
1. Glob `docs/ultron_1_0/01_recon/raw/` — confirm all 22 docs present (boardA_*.md ×12, boardB_*.md ×10). Re-run any missing agent directly.
2. Synthesize a master recon doc `01_recon/00_codebase_map.md` (pipeline data-flow, routing decision tree, all extension points, retire-not-remove list) from the 22 raw docs.
3. Commit Phase 1. Then craft + launch the Phase 3 big research board (waves: embedded 2nd codebase-scan + frontier search + adversarial verify + synthesis), informed by recon + the landscape brief (`02_research/00_landscape_brief_opus.md`).

## Confirmed env / serving facts (2026-06-20)
- Main venv (deps incl. CUDA llama-cpp): `C:\STC\ultronPrototype\.venv\Scripts\python.exe` (Py 3.11). Editable install targets the MAIN checkout `src/`, NOT this worktree → to run worktree code set `PYTHONPATH` to the worktree `src` (or make a worktree venv). Embedder venv: `C:\STC\ultronVoiceAudio\.venv-embedder`.
- Recon QA (boardA_semantic_router.md): embedder sidecar = EmbeddingGemma-300M on CPU, loopback HTTP :8772, urllib+numpy only (anticheat-clean). **`LexicalBackend` already uses RapidFuzz (token_set_ratio/WRatio) + Metaphone** → fuzzy/phonetic layer already a dep. HybridBackend fuses emb 0.6 / lexical 0.4. Relay-intent gate = pos/neg exemplar clouds, margin 0.06, fail-open. Router thresholds UNCALIBRATED (the enhanced MP3 battery is the labeled set to calibrate them). Recon agent independently flagged the 3-way {relay/me-only/ignore} gap → confirms pivot design.

## Recon findings so far — LOAD-BEARING (A4,A5,A7,A9 done; 18 in redo bg `wfqvbkcjs`)
**The pivot is ~70% recomposition of existing machinery.** Key facts (full detail in `01_recon/raw/`):
- **LLM serving (A7, `llm/inference.py`):** `generate_stream(user_message, system_prompt=<override>, sampling=<dict>, enable_thinking=bool, suppress_memory_context=bool, record_history=bool)` IS the route-all-through-LLM surface. When `system_prompt=` is passed, `_build_messages` returns just `[system,user]` (fast path, no RAG/history/injection-defense). The `sampling` whitelist ALREADY includes **`grammar` + `logit_bias`** (unused) = my constrained-decoding hook for combined callouts. Thinking handled: `_strip_thinking_blocks`(stream)/`strip_thinking_text`(block) + `_apply_no_think_marker` auto-appends `/no_think` for qwen-family when `enable_thinking=False`. **`josiefied-qwen3-8b` is ALREADY an LLM preset** (n_ctx 8192, no draft) → default swap is one line. Relay already LLM-rephrases (`_REPHRASE_PROMPT`@relay_speech:2081, `_RELAY_SAMPLING` max_tokens=56, `_RELAY_REPHRASE_SYSTEM`). Adaptive answer pipeline `build_answer_call`→{marvel,think_respond} curated system+sampling. `llm_prompts.py`=prompt SSOT. `response_style.py` brevity hints (procedural/factual/brief)=no/low/high substrate. `cache_aware_chunks.py`=prefix-cache substrate. `match_thinking_toggle`+`match_flavor_toggle` voice cmds exist. GOTCHA: `/no_think` only for "qwen" in model path (Llama parrots it); flash_attn=True needs non-F16 KV; logits_all must be True when draft active.
- **Config/flags (A9, `config.py`):** Pydantic v2 `extra="forbid"` → MUST add new u1.0 fields to schema before YAML. `LLM_PRESETS` extensible w/o schema change. `barebones_*` (15 lean flags) = the retire-not-remove precedent. `addressing.follow_up_enabled=false` (fusion classifier + `KENNING_ADDRESSING_TAU`=0.20 live behind it). `runtime_overrides.json` = ephemeral GUI overlay (wiped each boot). `__main__.py` sets `KENNING_FLAVOR_TAILS=0` default under `python -m kenning` (tests must set it explicitly). config.yaml `llm.gpu_layers=0` + preset `qwen3.5-4b` currently (gaming CPU 3B). `_addr_cfg` captured once at run() → addressing change needs RESTART.
- **Normalization (A4):** `routing_rules.py`=data SSOT (gazetteers/mishears/NORM2 relay-lead regexes/thresholds). `_stt_correct.py`=L1 4-stage (phrase→context→slot-confirm→phonetic+fuzzy via RapidFuzz/jellyfish, difflib fallback). `command_normalizer.normalize_command` (called orchestrator:6131)=L2; a **zero-mistakes gate returns questions/Spotify/reactions/think-respond verbatim BEFORE L1** (don't corrupt conversational). relay-intent gate fires inside `recover_relay_lead`.
- **Semantic router (A5):** EmbeddingGemma-300M sidecar (CPU, loopback :8772, urllib+numpy); HybridBackend = 0.6 emb + 0.4 lexical(RapidFuzz+Metaphone); additive fallback under exact matchers; relay-intent pos/neg clouds margin 0.06 fail-open; thresholds UNCALIBRATED (battery = the calibration set).
- **DECISIONS from recon:** u1.0 default LLM = `josiefied-qwen3-8b` GPU (gpu_layers=-1, within 10GB); reuse generate_stream override surface for all routes; use `grammar` for combined multi-callout; capture `<think>` to trace (route the already-stripped text to a log instead of discarding); add a u1.0 config section (verbosity no/low/high, flavor tail on/off, always-listen gate) to the Pydantic schema; add `barebones_skip_*` style flags to retire legacy deterministic-output paths.

## Open risks / watch-items
- `docs/codebase_structure.md` is 821 KB — query, don't read whole.
- Anticheat binding rules (`feedback_no_default_load_anticheat.md`) remain in force.
- Concurrent sessions reset `origin/main`; confirm `git rev-parse origin/main` before trusting tips.

## Rewind points
- Ultron 0.1 / 0.1.1 standalone builds: `E:\Ultron-0.1\`, `E:\Ultron-0.1.1\` (untouched).
- Dev baseline this work branches from: `6064e5f`.
