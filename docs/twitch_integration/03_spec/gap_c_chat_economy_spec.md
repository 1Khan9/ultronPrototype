# Gap (c) — chat-command games + economy ledger + delete message-id (spec, 2026-06-23)

Flag-gated default-OFF; main runtime byte-identical with flags off. Anticheat: stdlib-only
(sqlite3/hashlib/hmac/secrets/re/urllib/json/threading) — no new deps. Reuses the EXISTING
`commands.parse_command`, `economy.ledger.Ledger`, `economy.games.*` (pure resolvers),
`economy.rng.ProvablyFairRNG`, and mirrors `redeem_router`'s own-cursor daemon-drain pattern.

## REQUIREMENTS (EARS)
- **R1** WHEN `twitch.economy.enabled` AND a new `twitch.economy.chat_commands_enabled` are both ON, the system
  SHALL drain the read-sidecar chat buffer (own cursor, never acks — like the redeem router) and dispatch
  `!`-prefixed commands; OFF → no chat-command code runs.
- **R2** The system SHALL persist every game stake (debit) and payout (credit) to the SQLite-WAL `Ledger`, keyed by
  leg-distinct idempotency keys so an EventSub replay never double-applies.
- **R3** Viewers SHALL EARN currency by watch-time: each active chatter is credited `earn_per_minute` cores once per
  elapsed minute (idempotent per `earn:{login}:{minute}`).
- **R4** Single-shot bet games — `!slots <amount>`, `!spin <amount>`, `!gamble <amount>` — SHALL debit the stake
  first (InsufficientFunds → a "you only have N" reply, no game), resolve provably-fairly, then credit the
  multiplier payout; payout tables SHALL be derived so EV = `gamble_rtp` (net-negative house edge).
- **R5** `!points` / `!balance` SHALL reply the caller's balance; `!leaderboard` the top N; `!help` the command list.
- **R6** The system SHALL enforce `per_stream_loss_cap` as a per-viewer net-loss ceiling for the session (a bet that
  would push net loss past the cap is refused with a reply); reset at boot.
- **R7** AT-4 gates SHALL hold: `lose_all_segment_enabled` (wheel LOSE_ALL / heist all-in wipe) and
  `transfers_enabled` (`!give`, duel peer-settle) stay OFF by default and gate any balance-zeroing / peer move.
- **R8** Voice moderation `delete` SHALL work: the chat drain maintains a recent `{login → last message_id}` map; the
  delete handler threads that message_id through `ModerationRemote`→the write sidecar→`ModerationService.confirm`,
  which calls the existing `HelixClient.delete_message`.
- **R9** Per-user command cooldown SHALL throttle spam; the abliterated model is NEVER in the decision path
  (deterministic parse + ledger only).

## DESIGN
**New module `src/kenning/twitch/economy/chat_games.py`** — `ChatGameRouter` mirroring `RedeemRouter`:
- ctor `(drain_fn, *, ledger: Ledger, rng: ProvablyFairRNG, cfg: TwitchEconomyConfig, announce_fn, now_fn=time.monotonic)`.
- `tick()`: drain `ChatEvent`s; update presence `{login: last_seen}`; run the earn ticker; `parse_command` each
  `!` event; dispatch by `CommandKind`; dedup on `message_id` (bounded LRU; empty id bypasses dedup like redeem).
- Handlers: POINTS/balance → `ledger.balance`; SLOTS/WHEEL/GAMBLE → bet flow (R4); LEADERBOARD/HELP → reply;
  HEIST/DUEL/TRIVIA/RAFFLE → "coming soon" reply (built next pass); GIVE → gated `transfers_enabled` (next pass).
- **Bet flow:** check cooldown + loss-cap → `debit(stake, key=f'{game}:{mid}:bet')` (InsufficientFunds → reply) →
  resolve game with a fresh `rng.new_round()` → compute payout (RTP-derived) → if payout>0 `credit(payout,
  key=f'{game}:{mid}:win')` → reply outcome + new balance; update the per-viewer net-loss accumulator.
- **RTP:** `_slots_multiplier = rtp · S²` (P(win)=1/S² for 3 reels) ⇒ EV=rtp·bet. `_gamble`: win prob p, payout
  `m=rtp/p` (default p=0.5 ⇒ m≈1.8×). `!spin`: wheel segments carry signed multipliers tuned so weighted EV=rtp.
- **`make_chat_command_drain_fn(read_endpoint)`** — copy `make_redeem_drain_fn` but keep `type=='chat'` events whose
  `text` starts with the prefix; returns the inner dicts.
- **Orchestrator:** build ONE `Ledger(resolve_path(cfg.db_path))` at the economy gate, pass it into the RedeemRouter
  (next pass) AND a new `ChatGameRouter` daemon-thread loop (mirror `_redeem_loop`); `ledger.close()` on shutdown.
- **Config:** `TwitchEconomyConfig.chat_commands_enabled: bool = False` (+ `command_cooldown_seconds: int = 5`,
  `min_bet: int = 1`, `max_bet: int = 10000`). config.yaml + validate_config same commit (BR-7.1).
- **Delete-plumb:** the chat drain (main process) maintains `{login_lower: message_id}` LRU; the orchestrator delete
  handler looks it up, passes `message_id` to `ModerationRemote.prepare/confirm`; the write-sidecar HTTP + body carry
  it; `ModerationService.confirm` calls `delete_message` when present (else the existing unsupported reply).

**Alternative rejected:** folding command interception into `ChatReplyPipeline` — it filters to TO_ULTRON reply
targets at step 1, so `!cmd` messages are dropped before it sees them. An independent own-cursor drain is required.

## THIS-PASS SCOPE — DELIVERED (foundation + single-shot games)
chat_games.py (`ChatGameRouter` + `make_chat_command_drain_fn` + `chat_event_from_buffer`) + `!points`/`!balance`/
`!leaderboard`/`!help` + `!gamble`/`!slots` (ledger-backed, RTP-derived payouts) + watch-time earning +
`per_stream_loss_cap` + per-user cooldown + config flags + the Ledger singleton + orchestrator daemon-loop wiring
(closed on shutdown) + the read-sidecar `badges` field. 22 unit tests; full twitch suite 773 green. (Note: `!wheel`
takes no amount in the parser → it's a future free-spin; `!spin` is not in the grammar — the two single-shot BET
games the parser supports are `!gamble`/`!slots`.)

## ALSO DELIVERED — Trivia (the first multi-viewer state machine, commit a13ccf5)
`!trivia` (mod-gated) draws a provably-fair question, opens a window; the FIRST correct chat answer (scanned over the
ordinary-message drain) wins a house-funded prize (`trivia_prize`/`trivia_window_seconds`). The round closes
atomically BEFORE crediting → first-correct-wins, no double-award on replay/second answer; timeout announces the
answer. +5 tests; full twitch suite 779 green.

## DEFERRED (next pass) — ✅ ALL DELIVERED 2026-06-24

> Every item below is now built + wired + unit-tested (heist join-window with a
> `Heist.house_bonus_pct`; duel challenge/accept via a new `CommandKind.ACCEPT`; raffle via
> `CommandKind.RAFFLE`/`enter`; `!give` gated `transfers_enabled` with presence-based
> login→uid; RedeemRouter ledger-backing; the cross-process delete message-id plumb).
> See `00_STATUS.md` (2026-06-24) + `FIRST_STREAM_CHECKLIST.md`. Original design retained
> below for reference.

### original deferred design — with refined design
- **Remaining multi-viewer state machines:** heist join-window (collect `!heist <bet>` over a window → debit each →
  resolve → credit per head; needs a house bonus on the pot so a WIN profits — Heist.resolve splits a fixed pot, so
  a pure sum-of-stakes pot is break-even on win), duel challenge/accept (challenger debit → `!accept` → resolve →
  settle), raffle (the stateful game).
- **`!give` transfers** — gated `transfers_enabled`, two keyed legs (debit giver / credit receiver).
- **RedeemRouter ledger-backing** — replace the fixed pot=100 with real balances + the same keyed-leg pattern.
- **DELETE message-id plumb (CROSS-PROCESS — refined design):** the message-id index belongs in the READ SIDECAR
  (it sees every chat message in `_map_notification`), NOT the chat-game router (which is decoupled / only on when
  chat games are enabled). Plan: (1) read sidecar maintains a bounded `{login_lower → last message_id}` index +
  exposes `GET /last_message?login=X`; (2) `ModerationService` takes an injectable `message_id_lookup(login)`;
  its `confirm()` delete branch calls `delete_message` when the lookup returns an id (else the existing unsupported
  reply); (3) the write sidecar constructs the service with a lookup that GETs the read sidecar's `/last_message`.
  This keeps the moderation safety path clean (additive; ban/timeout/unban unaffected). The chat-game router's
  `last_message_id()` (built + tested this pass) is a secondary in-process source.

## Out of Scope (this feature)
1. Persisting in-memory round state (heist/trivia/raffle) across an Ultron restart — in-memory v1.
2. A leaderboard projection table — computed from `ledger.rebuild_balances()` on demand.
3. Speak-to-team / any chat→team path (structurally walled; unchanged).
4. Deriving the wheel/slots symbol sets from config — fixed defaults this pass.

## Open Questions
- Atomic bet+win (a new `Ledger.transact`) vs debit-first + keyed legs? → v1 uses keyed legs (recoverable on replay).
- `per_stream_loss_cap` per-viewer vs global? → per-viewer net loss, reset at boot.
- Recent-message map TTL/maxlen for delete? → LRU 4096, keyed on lowercased login (last message only; the delete
  regex matches "last/that message" singular).
