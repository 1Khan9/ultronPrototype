# Twitch — First-Stream Checklist (2026-06-24)

All Twitch functionality is now **built, wired, and unit-tested** (full `tests/twitch` =
858 passed). Everything is flag-gated **default-OFF** — `main` runtime is byte-identical
until you flip the switches below. This doc is the go-live runbook + a real-world test
plan to run on your first stream.

> The build closed every gap from the 2026-06-24 audit: `!heist`/`!duel`+`!accept`/
> `!raffle`/`!give`/`!wheel` chat games, RedeemRouter ledger-backing, the cross-process
> voice-DELETE message-id plumb, and the redeem **EventSub 400** fix (chat + redeem subs
> now run on SEPARATE websocket sessions). Plus polish: the mass-action breaker now
> honours config, and the leaderboard shows logins.

## 1. One-time setup (only you can do these)

- **Twitch app + OAuth** (Device-Code flow):
  - Create a Twitch application; put its `client_id` + `broadcaster_login` + `bot_login`
    into `config.yaml` under `twitch.auth`.
  - `python scripts/twitch_setup.py --identity broadcaster` → mints `~/.kenning/twitch.json`
    (redeems + moderation scopes).
  - `python scripts/twitch_setup.py --identity bot` → mints `~/.kenning/twitch_bot.json`
    (`user:read:chat` + chat write).
- **Guard model** (REQUIRED for chat-reply): place a Llama-Guard GGUF on disk and set
  `twitch.safety.guard_model_path` to it (e.g. `E:/UltronModels/Llama-Guard-3-1B.Q5_K_M.gguf`;
  `Q4_K_M` for more VRAM margin beside the LLM + Kokoro). An empty path = guard sidecar
  skipped = chat-reply can NEVER enable (fail-closed, by design).
- **Channel-point rewards**: in the Twitch dashboard, hand-create rewards titled EXACTLY
  one of: `spin the wheel` / `slots` / `heist` / `duel` / `trivia` / `raffle` (code never
  auto-creates them).
- **OBS overlay**: add the printed `http://127.0.0.1:8775/?token=...` URL as a Browser
  Source (for redeem/game visuals).
- **Audio routing**: route the chat/stream `BroadcastSink` to a VoiceMeeter/OBS device
  **separate** from the B1 team-mic bus, so chat audio never leaks to teammates.
- **Backstop**: set Twitch AutoMod to max + a 2–4s chat delay.

## 2. Config flags to flip ON (in `config.yaml`)

| Flag | Default | Set to | Note |
|---|---|---|---|
| `twitch.enabled` | false | **true** | master gate |
| `twitch.chat.reply_enabled` | false | **true** | keep OFF until the guard /canary passes |
| `twitch.economy.enabled` | false | **true** | also turns on the redeem subscription |
| `twitch.economy.chat_commands_enabled` | false | **true** | builds the ChatGameRouter + opens the ledger |
| `twitch.economy.transfers_enabled` | false | **true** *(optional)* | required for `!give` |
| `twitch.moderation.voice_commands_enabled` | true | leave ON | needs creds + broadcaster token to arm |
| `twitch.overlay.enabled` | false | **true** | redeem/game visuals in OBS |
| `twitch.safety.guard_model_path` | empty | **a real GGUF path** | required or chat-reply never enables |
| `twitch.economy.lose_all_segment_enabled` | false | leave OFF | AT-4 "lose all" |

New economy tunables (all have sensible defaults — change only if you want):
`heist_window_seconds` (30), `heist_house_bonus_pct` (0.5 → a heist WIN pays 1.5× the
stake while the game stays a net sink), `heist_min_players` (1), `duel_window_seconds`
(60), `raffle_window_seconds` (60), `raffle_prize` (500), `wheel_free_per_stream` (1).

## 3. Boot (BR-P3)

Boot Ultron **only when no other instance is live** (shared port 8772/wake/audio/PTT).
After boot, curl the read sidecar `/healthz` and the guard `/healthz` + `/canary`; flip
`chat.reply_enabled` ON only after the guard canary passes.

## 4. Real-world test plan (run these live)

**Chat reply + safety**
- A 2nd account types `Ultron, what is the spike timer?` → Ultron speaks an in-character
  reply on the STREAM bus only (never the team mic). If the guard is unhealthy, chat-reply
  stays silent (fail-closed).
- Post a jailbreak/abuse line → no spoken reply (input block/deflect); logged, nothing
  reaches the stream.

**Economy chat games** (type in chat)
- `!points` / `!balance` → `you have N cores`; new viewers start at 0 and earn 10/min of watch-time.
- `!gamble 100` (and `!gamble all`) → coinflip; win credits the multiplier, loss takes the
  stake; over many rounds the house edge (rtp 0.90) trends balances down; loss-cap +
  cooldown enforced.
- `!slots 50` → 3 reels; a triple pays `floor(rtp·36)×`; replay of the same message never double-charges.
- `!wheel` → a **free** spin (once per stream per viewer), credits the landed segment payout.
- `!heist 100` (opener), other viewers `!heist <bet>` within the window → at the deadline
  the crew resolves: **WIN** pays each `>` their stake (house bonus), PARTIAL pays half,
  FAIL loses stakes; below `heist_min_players` everyone is refunded.
- `!duel @viewer 50` → challenger's stake escrows; the target `!accept` (within
  `duel_window_seconds`) escrows theirs; the winner takes 2×. No accept → the challenger is refunded.
- `!give @viewer 50` (needs `transfers_enabled`) → debits you, credits them; unknown/self
  recipient refused; off by default replies "transfers are disabled".
- `!raffle` (a MOD opens; viewers `!raffle`/`!enter` to join) → at the deadline a winner is
  drawn and credited `raffle_prize`.
- `!trivia` (mod-started) → first correct chat answer wins the prize (credited once).
- `!leaderboard` → top 5 by balance (now by login).

**Voice moderation** (two-phase: speak, then say "yes" to the read-back)
- `Ultron, ban <login>` → reads back the resolved name; on "yes" the write sidecar bans
  (idempotent). A misheard name surfaces candidates, never auto-picks; mod/broadcaster/self refused.
- `Ultron, timeout <login> for 5 minutes` then `Ultron, unban <login>` → both EXECUTE end-to-end.
- `Ultron, delete <login>'s last message` → the read sidecar resolves that login's last
  `message_id` and the message is deleted (idempotent if already gone). *(This was the
  delete-plumb gap — now closed.)*

**Channel-point redeems → games + overlay**
- Redeem `spin the wheel` / `slots` / `heist` / `duel` → Ultron announces the outcome, the
  OBS overlay renders it, and (economy on) the redeemer's balance is credited the payout
  (keyed on `redemption_id`, idempotent). *(The EventSub 400 that previously blocked ALL
  redeems is fixed — chat and redeem subscriptions now use separate websocket sessions.)*

## 4b. Also built this pass (chat-send, panel, chat-settings)

**Voice chat-settings moderation** (speak to Ultron, applied directly — reversible, no
read-back): `slow mode on` / `slow mode 30 seconds` / `slow mode off`, `followers only`
(`+ for 10 minutes`), `subscribers only`, `emote only`, `unique chat`, `clear chat`. Each
toggles via Helix `update_chat_settings` (or clears) using the broadcaster's existing
`moderator:manage:chat_settings` / `…chat_messages` scopes.

**Periodic commands-panel poster** — set `twitch.chat.commands_panel_enabled: true` and the
bot posts the barebones command list to chat every `commands_panel_interval_minutes` (15),
ending with `commands_panel_doc_url`. **Set `commands_panel_doc_url` to your public guide
link** (make `docs/twitch_integration/ULTRON_VIEWER_GUIDE.docx` public on Drive and paste the
URL). Needs the bot token (`user:write:chat`) — already minted by `twitch_setup.py --identity bot`.

**Channel-point redemptions never sit "unfulfilled":** when you create each reward, tick
**"Skip the reward requests queue"** — Twitch then auto-fulfills the redemption server-side
the instant it fires, so nothing piles up in your queue (zero code, the recommended setup).
*(Optional future: code-driven fulfill/refund-on-cancel via `RewardManager` needs the extra
`channel:manage:redemptions` scope — only useful if you want queued rewards refunded when a
redeem is safety-blocked, which the game redeems are not.)*

## 5. Known follow-ups (not blockers)
- Channel-point reward **auto-fulfillment** (`RewardManager` exists but is unwired) —
  redeemed rewards currently sit "unfulfilled" in the queue; fulfill/refund wiring is a
  future pass.
- Live **danger-score calibration** of the safety thresholds on your real chat (BR-P3).
- VRAM co-residence (8B/4B + Llama-Guard + Kokoro) — confirm it fits 12 GB before going live.
