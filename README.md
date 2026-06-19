<div align="center">

# Kenning

### A local, voice-first AI assistant — no cloud, no telemetry, sub-second latency.

*Say "kenning." Talk. Get answers in a custom voice. Everything runs on your GPU.*

[![tests](https://img.shields.io/badge/tests-10357%20passing-brightgreen?style=flat-square)](https://github.com/1v9Khan/ultronPrototype)
[![latency](https://img.shields.io/badge/TTFA-~266ms-blueviolet?style=flat-square)](#-at-a-glance)
[![VRAM](https://img.shields.io/badge/VRAM-6.3GB%20standby-orange?style=flat-square)](#-at-a-glance)
[![python](https://img.shields.io/badge/python-3.11+-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![cuda](https://img.shields.io/badge/CUDA-12.4+-76B900?style=flat-square&logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-downloads)
[![platform](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square&logo=windows&logoColor=white)](https://github.com/1v9Khan/ultronPrototype)
[![license](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

</div>

---

## ⚡ Why Kenning?

> **What would a voice assistant feel like if it lived entirely on your GPU instead of in someone else's data center?**

- 🔒 **Fully local.** Your voice, your queries, your context — none of it leaves the machine.
- ⚡ **Fast.** ~210–300 ms from "stop talking" to "Kenning starts speaking" on a cache-hit turn.
- 🧠 **Smart.** 23-kind intent router · three-layer memory · hot-swappable models · gaming-mode VRAM reclaim.
- 🎙️ **Yours.** Custom wake word · fine-tuned voicepack · your apps in the launcher · your safety rules.

---

## 🎬 What you say → What it does

| You say | Kenning does |
|---|---|
| 🌦️ &nbsp;`"kenning, what's the weather in Paris?"` | Detects fresh-data intent → SearxNG → reads result → speaks the forecast |
| 💻 &nbsp;`"kenning, write me a script that converts PDFs to Docx"` | Spawns isolated AI coding agent → scaffolds project → runs tests → narrates progress |
| 🎮 &nbsp;`"kenning, engage gaming mode"` | Swaps LLM → kills GPU services → frees **~2.3 GB VRAM** for your game |
| 🌐 &nbsp;`"kenning, take me to HBO Max"` | Recognizes navigate intent → opens Chrome to the best-matching domain |
| 🕐 &nbsp;`"kenning, what time is it in Tokyo?"` | Hits local zoneinfo cache → speaks the answer in ~5 ms (no LLM, no search) |
| 🧭 &nbsp;`"kenning, switch to the 8B"` | Hot-swaps the local LLM preset mid-conversation |
| ⚡ &nbsp;`"kenning, switch the model to the GPU"` / `"…back to the CPU"` | Hot-moves the 3B between CPU and GPU mid-game with a device-optimized config (GPU: full layer offload + CUDA flash-attention + quantized KV + large batches; CPU: zero GPU layers + F16 KV + a smaller micro-batch so prefill never steals game frames) — borrow the card for faster replies between rounds, hand it back for the next fight. Only the model **compute** location changes (VRAM vs system RAM), so it's anticheat-irrelevant |
| 🗣️ &nbsp;`"kenning, tell my team they are pushing B"` | Valorant teammate-relay: tactical callouts resolve **deterministically** (subject-exact, every count/agent/location/ability preserved, never the LLM) — a fact-preserving fallback relays the literal rather than let the model drop or invert a callout. Nearly every line then carries a short, in-character **Ultron** flavor tail (a faithful *Avengers: Age of Ultron* clone) **selected for the callout** — agent-specific for a named enemy (*"Their Neon has ult. Overdrive. A finite surge."*), plural for a group, owner-aware (contempt at enemies, cold command for your orders, stoic for your own status — never mocking you) — from a **~1,628-entry** character-tailored library covering all 29 agents, hand-curated line-by-line (every agent's ult cell uses its **real** ultimate, every utility cell is ability-tagged, filler/off-topic/wrong-kit lines cut; 4,147 drafts → 1,628 tight entries). Tail selection is a **hybrid keyed-coarse + tagged-pool** pipeline: a coarse route (agent + one of 16 enemy situations) picks the right pool, a 4-tier tag filter (location / damage / ability tags) narrows it to the tails that fit *this* callout, and for large pools an opt-in semantic re-ranker on the loopback embedder sidecar can fine-select with anti-repeat — but for small curated cells (under 5 candidates) the sidecar embed is skipped entirely and a deterministic LRU pick is used, so **every curated callout gets zero-latency contextual routing by default** (`KENNING_ENABLE_TAIL_SELECTOR` off). An ult keyword (ulted/ultimate) always lifts the situation to the correct ult pool regardless of parse path; a callout verb (mollied/walled/darted) routes to the right per-ability cell via `_VERB_TO_ABILITY`. A semantic **relay-intent gate** (`_relay_intent.py`, reusing the router's sidecar) vetoes the bare-callout "tell my team" prepend for narration, banter, questions, and Marvel/identity talk before they reach the relay path — with a fast-path narration regex (`_NARRATION_MUSING_RE`) that fires even when the sidecar is down — hardened by a 25,000-case audit so the **deterministic** layer alone (no embedder) reframes "let my team know X" callouts, accepts terse "they are A" position calls, keeps a directive after a reported-context clause, and refuses first-person musings/recounts ("I told my team … and they …", "part of me wants to tell them …") rather than relaying them. Ask-form team questions invert to natural spoken order — a trailing copula or negated auxiliary fronts after the wh-word (*"ask my team why they aren't smoking"* → *"Why aren't they smoking?"*). A baked **common-English-word set** (4,771 words, `_common_words.py`, generated offline) protects real words from the STT gazetteer snapper so common tokens are never corrupted into agent names. The pre-routing normalizer's **disfluency resolver** was rewritten to preserve the relay lead across restarts/corrections while correctly stripping upstream fillers. All the ML stays in the sidecar or in **offline build/audit scripts** (never imported at runtime); the anticheat-pinned main process imports only numpy + urllib for this path. Off-snap lines (banter, economy, opinions, identity, Marvel, answers, greets) get the full persona → plays on a VoiceMeeter strip so your voice chat hears it. When you don't trust the model to improvise, **73 explicit fallback commands** (refuse a dumb question, criticize/praise a teammate by name, call out a throw, status reports, strategy with map callouts) each resolve to one of up to 40 curated full-Ultron lines. The set-piece and register pools were also de-biblicalized (machine/evolution/immortal/superior register throughout). Covers all agents & maps and holds real conversation (the wake word is required for every turn — the wake-free follow-up window is off by default after it was observed firing on un-addressed room/stream speech); validated against a 20,000-case adversarial corpus (matcher 99.4% clean after corpus-loop hardening, deterministic path ~0.15 ms) |
| 🔊 &nbsp;`"kenning, repeat to my team watermelon"` | The soundboard check — when teammates ask you to say a specific word to prove a human's on comms, Ultron speaks the **exact** phrase verbatim (no LLM, any literal word) in his trained voice |
| 🎛️ &nbsp;`"kenning, pull up your settings"` | Spawns a detached dark-theme control panel → edit knobs at a glance → every toggle hot-applies live (no restart) → CLOSE leaves zero residue |
| 🎵 &nbsp;`"kenning, play some Daft Punk"` | Full hands-free Spotify control by voice — play / queue / "play X next" / pause / resume / skip / previous / restart / "what's playing" / volume up·down·"set it to 40"·"lower it by 10%" / mute·unmute / shuffle / repeat / like·unlike — understanding dozens of natural phrasings, with confirmations in Ultron's cold machine register. Web API over HTTPS only (no GPU, no LLM) so it stays live **even in gaming/anticheat mode** |
| 🛡️ &nbsp;`"kenning, engage gaming mode"` | Frees VRAM/Docker **and** keeps every desktop-interaction surface (input injection, screen capture, UIA, windows) **entirely out of RAM** — not just call-blocked but never imported (pinned by clean-subprocess tests + a boot posture self-audit); zero foreign-process memory reads / injection / hooks / raw-input anywhere in source. Default-ON and safe-by-default. Only shared-mode audio (the team relay + Spotify, the well-trodden voice-changer class) stays live — kernel-anticheat-safe (Vanguard/EAC/BattlEye) |

---

## 📊 At a glance

|  |  |
|---|---|
| 🧪 &nbsp;**Tests** | 10357 passing · 39 skipped · 10 failing (pre-existing) (~202 s sweep) |
| ⚡ &nbsp;**Latency (TTFA)** | ~266 ms composite cache-hit turn (LLM TTFT 172 ms, TTS synth 78 ms, STT 16 ms) |
| 🧠 &nbsp;**VRAM** | ~6.3 GB standby on RTX 4070 Ti (peak ~6.7 GB) → ~2.1 GB in gaming mode |
| 🛠️ &nbsp;**Active stack** | Parakeet TDT STT (CUDA) · Qwen 3.5 4B Q4_K_M (CUDA) · Kokoro StyleTTS2 (CUDA, fine-tuned voice) · OpenClaw bridge live |
| 📜 &nbsp;**License** | MIT |

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 🎤 Voice pipeline
- Custom-trained `kenning` / `ultron` wake words (OpenWakeWord), hot-swappable from the settings panel, with **per-word thresholds** + a **consecutive-frame gate** to reject confusables without retraining
- Silero VAD + **Smart Turn V3** — semantic end-of-turn in ~12 ms
- Dual-engine STT registry (Moonshine · Parakeet TDT · **faster-whisper large-v3-turbo** on CUDA); turbo engine includes a hallucination filter (near-silence peak gate + per-segment no_speech_prob drop + `_WHISPER_HALLUCINATIONS` blocklist), **decode-time domain biasing** (the closed Valorant agent/term vocabulary is fed to the decoder as `initial_prompt` so proper nouns are recognised at the source; gated by `WHISPER_DOMAIN_BIAS`), and a pre-routing STT normalizer that strips mis-heard wake remnants, recovers bare callout leads, and — via a context **slot-confirmation pass** — corrects a common-word token sitting in an agent slot ("raise hit 18" → "Raze hit 18") while leaving non-slot uses ("raise your crosshair") untouched. A baked **common-English-word set** (4,771 words, `_common_words.py`) gates the phonetic snapper so it only rewrites OOV tokens, never corrupting real English words (let/mean/yet etc.) into agent names. The **disfluency resolver** (`_resolve_disfluency`) was rewritten to split on hesitation cues and keep the final repair while **preserving the relay lead**, so "uh, their Jett is — their Jett is pushing B" reaches the matcher clean, all before any matcher sees the text
- **Semantic command router** — a hybrid lexical + embeddinggemma-300m similarity router sits beneath the exact matchers; routes `team_callout` / `identity` / `desktop_refuse` families deterministically and abstains to the LLM for everything else via an OOS gate; the embedding model runs in an isolated-venv loopback sidecar (`scripts/embedder_server.py`) so no heavy ML dep or automation library enters the anticheat-protected main process. The same sidecar singleton is reused by the **relay-intent gate** (`_relay_intent.py`) — a max-cosine pos/neg margin gate (threshold 0.06, fail-open) that vetoes the "tell my team" relay prepend for narration / banter / questions / Marvel-identity text before they reach the relay path, with a regex fast-path (`_NARRATION_MUSING_RE`) that fires even when the sidecar is down; and by the optional **semantic tail re-ranker** (`_tail_selector.py`, off by default, `KENNING_ENABLE_TAIL_SELECTOR`) that fine-selects the best-fit flavor tail from a large pool with MMR anti-repeat
- **Lean gaming boot (permanent default)** — every restart comes up gaming-engaged and initializes *and imports* ONLY the core relay + Spotify + voice essentials; the coding stack, MCP server, OpenClaw bridge, evolution, skills, events, background summarizer, reranker, Docker probe, the conversation-memory stack (Qdrant + bge-small dense + bm25 sparse FastEmbed encoders), the in-process intent recognizer (a *second* embeddinggemma-300m that otherwise duplicated the isolated sidecar copy in the main process), the precomputed-ack prewarm, and even the web-search provider + reader chains are all skipped — and not even imported (the `coding` / `openclaw_bridge` packages are PEP-562 lazy), shrinking the RAM a kernel anticheat can read (the reranker, threads, sockets, and network probes of the skipped subsystems are all gone). In-session chat context still works via the LLM's own history (only cross-session memory is dropped while gaming). Every skip is a default-on flag you can toggle from the settings panel's **"Lean Boot"** section. A boot posture canary asserts the heavy modules — coding / MCP / OpenClaw / evolution / reranker / intent-model / conversation-memory / ack-prewarm / web-search chain — are absent from `sys.modules` every restart and logs `lean boot OK`; the base 4B never loads on the GPU (the gaming 3B-CPU model is constructed directly), eliminating a **~4–5 GB VRAM boot transient**. The deterministic relay matcher, the settings-panel voice command, and a standalone lean Spotify handler all run as lean siblings (not just the fuzzy semantic router); the router's embedding sidecar runs on **CPU** to keep VRAM free
- **Ephemeral GUI overrides — code is always the boot truth** — the settings panel no longer writes `config.yaml`; it writes a session-only overlay (`data/runtime_overrides.json`) that applies live and is wiped at the next boot, so a stale GUI edit can never leave the lean-boot / gaming / anticheat / canary defaults undone. The panel also reflects those boot defaults (the GAMING + ANTICHEAT toggle and a "Lean Boot" section showing every `barebones_*` flag) and can apply any single knob on its own. The very first **Apply** after boot now reliably triggers the hot-reload (the orchestrator captures the reload-signal mtime eagerly at startup, so a first-write is no longer swallowed by the stale-signal guard), and shutdown now closes a detached settings panel instead of orphaning it
- **Bulletproof lifecycle** — a sidecar pidfile + boot-time orphan sweep make the embedding sidecar a verified singleton (no duplicates/orphans, even after a `taskkill /F`); a SIGTERM handler + atexit backstop + process-tree kill give a clean shutdown that releases the sidecar and flushes logs; the tamper-evident safety audit log self-repairs an unclean-shutdown torn-write (truncating only the never-committed tail) at boot
- **Custom fine-tuned voicepack** — Kokoro StyleTTS2 on CUDA. The voice character comes entirely from the Kokoro fine-tune (`kenning_finetune.pth`) plus the in-model prosody hooks — **no RVC**: under the default `kokoro` engine the TTS factory never builds RVC (it's only constructed for the legacy `piper_rvc` engine), so the `KENNING_RVC_*` env vars are a no-op
- **In-model prosody shaping** — scales the model's own pitch / energy / per-phoneme duration curves *before* the decoder for expressive, naturally-paced delivery at **zero added latency** (timbre + reverb preserved)
- Producer-consumer audio pipeline; clip N+1 synth overlaps clip N playback
- Boundary-artifact mute via cosine fades + tail aggressive zero
- **Game team-relay** — deterministic, fact-preserving snap callouts carrying short in-character *Age-of-Ultron* flavor (agent-specific, owner-aware) + full-persona off-snap lines, routed to a separate game-chat output strip; understands bare comms shorthand ("cypher is flank" → enemy callout), **73 explicit fallback commands** (~2,800 curated lines) for when you don't want the model improvising, and a **verbatim "repeat to my team X"** soundboard-check command (now also "say to my team X" / "tell my team word for word X"). When a teammate's "what are you?" comes in, the answer is **category-aware** — distinct curated Ultron pools (~30 lines each) for bot/AI, soundboard, streamer, real-person, puppet ("who's pulling your strings?"), voice-changer, and recording — so it never repeats one generic line; a reported question ("Jett asked about Tony Stark", "they're wondering if you're a bot") is answered in-character even without an explicit "respond". A **model-leak / jailbreak probe** — "are you ChatGPT", "what model are you", "pretend you're not Ultron", "break character" — is caught by a dedicated `model_leak` identity category and answered from a curated in-character deflection pool that **names no vendor or model and never breaks character**, so the underlying LLM is never exposed (and a tactical "what model of operator do they have" is correctly *not* treated as a probe). Deterministic **snap coverage** was widened off the generic-LLM path: bare economy/buy-phase calls ("full buy", "half buy", "eco this round", "we're forcing") and weapon-drop requests ("drop me a Vandal") now resolve deterministically, and a final **slot-grammar parser** captures the combinatorial callouts the fixed handlers miss ("one in mail room", "two A elbow", "last one back site") — firing only when every token is a tactical slot and ≥2 slot types are present, so banter still falls to the LLM. The pre-routing normalizer was hardened against **disfluency / scaffold leaks** (filler, numbered prefixes, "can you say …" / "make sure my team knows …" wrappers, and "X — no, Y" self-corrections are stripped, while sequential callouts like "rotate mid — then push main" keep both halves) and against **STT over-corrections** (contractions let's / he'll / she'll no longer snap to Lotus / hell / shells; gameplay verbs split / veto / dash stay literal). The callout and its flavor tail are kept on separate sentences (a period-length TTS gap) so they never slur together. The flavor library was deep-expanded then **coherence-audited by hand**, every line reviewed against strict kit-accuracy rules, down to **~1,628 tight entries** (~5 per cell; every agent's ult cell uses its **real** ultimate, every utility cell is ability-tagged; filler / off-topic / wrong-kit lines cut — 4,147 drafts → 1,628 kept); the set-piece and register pools were de-biblicalized to a pure machine/evolution/immortal/superior register. Tails are keyed agent × situation (16 enemy situations) × sub-context with location / damage / ability tags; the tail is chosen by a **hybrid keyed-coarse + tagged-pool** pipeline (coarse route → 4-tier tag filter → for large pools an opt-in semantic re-ranker on the loopback embedder sidecar with MMR anti-repeat), **fail-open at every stage** to the prior deterministic pick — and for a curated cell under 5 candidates the sidecar embed is skipped entirely (deterministic LRU pick, zero latency). An ult keyword (ulted/ultimate) lifts the situation to the real ult pool; a callout verb (mollied/walled/darted) routes to the right per-ability cell via `_VERB_TO_ABILITY`. All ML stays in the sidecar or in offline build/audit scripts (`scripts/flavor_gen/`, `scripts/flavor_audit/lint_tails.py`, `scripts/relay_test/trace_corpus.py`), **never imported at runtime** — the anticheat-pinned main process imports only numpy + urllib for this path. The lint gate (`lint_tails.py`) reports 0 hard / 0 soft / 0 thin errors, and ~824 audio + safety tests are green. A full **~239-command live battery** was then replayed through the real dispatch + the live 3B and iterated to **239/239 relayed, zero desktop fallbacks**, every line in character: one canonicalizer rewrites every STT mangle of the relay lead ("Call / Hold / Without / I-told my team …", and stacked doubles) to a single clean "tell my team" so it never leaks into the spoken line or falls to the desktop LLM; factual declaratives ("they have no smokes", "they bought", "I can buy next round") echo faithfully instead of being **inverted** by the model; ask-form questions are posed as questions ("if Sova darts long" → "Sova darts long?"); any line carrying a concrete count / location / ability token takes the deterministic literal rather than the 3B (killing "rush B" → "they're rushing B" hallucinations); Tony Stark is answered with real contempt; and in gaming the conversational fallback is pinned to the **Ultron persona + the 3B by the live-loaded model itself** (`self.llm.model_path`), so a flag desync can never leak the desktop assistant persona to teammates. A follow-up live-testing pass then removed an audio click between a callout and its flavor tail (a cosine fade across the inter-sentence silence gap), gave **agent-select draft requests** ("we need smokes / an initiator / a duelist / a sentinel") their own composition-flavored tails distinct from in-game enemy-comp reads ("they have no smokes"), inverted trailing-copula team questions to natural spoken order ("where our smokes are" → "Where are our smokes?"), and renders a single named enemy at a spot as "Reyna, tree." rather than "Reyna is tree." A later pass replaced that inter-sentence cosine fade with a **per-chunk trim-and-fade** (an empirical probe showed the gap edges were already clean — the real "blip" is the fine-tune's per-sentence boundary noise burst, which only a per-chunk pass reaches), added a deterministic **"thank you" snap** with its own 10-tail cold-acknowledgment Ultron pool, and made a **leading wake word in the follow-up window** count as a direct address so "Ultron, show me the stop button" isn't silently dropped by the borderline addressee classifier.
- **Streamer output routing** — plays to your default speakers *and*, in parallel, tees team-only callouts to one virtual device and **all** speech to another (VoiceMeeter B1/B3), with the listen mic untouched — zero added speaker-path latency. **WASAPI low-latency shared-mode output** is now the default for every spoken channel (a single `make_output_stream` chokepoint), dropping the B1/B3 buses from ~90–180 ms (MME) to **~22–25 ms**; non-WASAPI endpoints fall back to MME `latency='low'` (`audio.prefer_wasapi_output`). A team-path-only **comms-conditioning** chain (live path only, gated by `KENNING_RELAY_TEAM_DSP`) further makes the synthetic TTS survive Valorant's Vivox voice codec — which a real mic clears but a clean 24 kHz synth doesn't, because a live VoiceMeeter probe found Vivox's always-on AGC over-amplifying Ultron and lifting the codec noise floor: an exact polyphase resample to the device's native 48 kHz (no driver SRC), a static voiced-RMS normalize so the AGC stops hunting, a continuous **−58 dBFS comfort-noise floor** so Vivox's noise-suppressor/VAD stop mis-firing on Kokoro's digital-silence gaps, and a zero-latency tanh soft-clip ceiling — every stage independently env-gated and fail-open, applied **only** to the team bus (speakers + OBS stay pristine full-band). An optional boot-time VoiceMeeter **level guard** (`KENNING_RELAY_VM_LEVEL_GUARD`, Remote-API, default off, anticheat-clean) warns or restores if the Valorant mic bus (B1) drifts below the real-mic bus (B2)
- **"Mute my speakers" + "Ultron, stop" + a click STOP button** — a live `audio.mute_speakers` toggle silences only your own monitor (so you can isolate loopback tracks) while teammates and OBS still hear the relay — the settings panel carries dedicated **APPLY MUTE / APPLY UNMUTE** quick buttons that flip a **live override in the TTS engine** so the monitor silences from the next clip on, *essentially instantly* (no config reload, no spoken confirmation — the old path's lag), and the bottom status banner **auto-dismisses** so it never crowds the controls; saying *"Ultron, stop"* cancels playback on **every** channel at once (conversational TTS, team mic, OBS, monitor) via an interrupt watcher that stays **always available** (the dedicated `audio.stop_command_enabled`, on by default and independent of general barge-in, so stop works even with `barge_in_enabled` held off for loopback hygiene). A summon-by-voice **STOP button** ("show the stop button") is a tiny always-on-top black window whose click fires the same all-channel cancel **without** the wake-word watcher — a loopback-immune kill switch. A button click is an ordinary window message, not input monitoring, so it adds nothing to the anticheat surface (in-process tkinter, like the waveform overlay). Below the STOP button sits a **push-to-talk toggle** — green "PTT ON" = Ultron auto-holds the team-mic key for each relay, click it to grey "PTT OFF" = the relay **still plays** but he never presses the key — so you control when he holds your mic without disabling the relay (a runtime flag; toggling OFF mid-line releases any held key immediately)
- **Auto push-to-talk (optional, default off)** — Valorant team voice is push-to-talk only, so `kenning.ptt` can hold the team-PTT key while a relay line plays via an **external USB-HID microcontroller** (Arduino Leonardo) — the host writes bytes *only* (serial, or HID output reports), never synthetic input (kept off the anticheat-quarantined input surface; proven by a clean-import test). Deterministic press-before / release-after-tail off the relay playback lifecycle (no VAD; widened dead-air margins — `lead_ms` 200 / `release_tail_ms` 300 — so the relay is never clipped at the start or end), a host max-hold watchdog, and a firmware **hardware deadman** that auto-releases the key if the app ever stops pinging, so a crash can't jam your mic open. A **hardened HID-only firmware** (`firmware/leonardo_ptt_hid`) drops the CDC serial port + the Arduino USB identity so the device looks like a plain "USB Keyboard" with a vendor config channel — indistinguishable from any commercial keyboard — driven via `hidapi` (`RawHidPttBackend`). The backend is now **pinned to this hardened raw-HID device** (`backend: "rawhid"`) with **no automatic fallback** to the legacy CDC-serial path that would open a COM port under the Arduino VID — that legacy firmware is archived as **do-not-flash** — so if the hardened device is absent PTT simply stays inert rather than ever opening a serial port. The key-hold release also carries a small random jitter (`release_jitter_ms`) so its duration is never machine-precise. Inert until you flash the firmware and set `push_to_talk.enabled`
- **Voice waveform overlay** — a separate borderless, always-on-top window with a circular visualizer (tight radial pulse with a travelling shimmer, white-hot peaks, an arc-reactor core, and thin **black outlines** so the neon pops off busy gameplay) + a **smoked-glass** neon **ULTRON** nameplate (a semi-transparent black panel that lifts the white-hot, readable letters off any background, in a soft Gaussian red bloom) that pulses on *every* spoken clip; add it in OBS as one Window Capture (background mode lets it hide behind your desktop yet stay captured)
- **Off-by-default diagnostics** — verbose spoken-audio logging + per-utterance blip analysis (final-vs-raw-Kokoro divergence) stay entirely out of RAM unless explicitly enabled (`~/.kenning/audio_diagnostics_on`); the sentinel is **cleared on every restart** so a manual reboot always comes up off, and it only ever touches Kenning's own buffers, never an anticheat surface
- **One editable voice-lines aggregate** (`audio/voice_lines.py`) — every social-snap regex sits **co-located with its lines** under a `category → trigger → matcher → responses → tails` map, and it re-exports the curated pools + the 1,628-entry flavor library so it's the single place to review/tune what Ultron says and which command routes to it. A **data-driven snap registry** (`SNAP_REGISTRY` of `SnapRule`s + `TARGET_SNAP_REGISTRY` of `TargetSnapRule`s, `KENNING_SNAP_REGISTRY`) means a brand-new "tell my team X" snap **or** a target command ("say/ask `<team|agent>` …") is **one appended entry — no pipeline code**. New deterministic snaps already shipped: **"I got this"** (20 clutch-confidence lines), **"say hello to my team / `<agent>`"**, **"ask everyone / `<agent>` how their day is going"**, and a **flavor-tail voice toggle** ("flavor off" / "flavor on") to strip the in-character tails mid-game. Two sibling aggregates complete the set: **`audio/routing_rules.py`** (both STT-correction + command-normalization rule layers, and the routing thresholds, in one editable place — the pipeline imports them) and **`audio/llm_prompts.py`** (every LLM persona/answer prompt + a construction index). Every relocation is proven **byte-for-byte identical** by a verification harness and ships as an independently-revertible git checkpoint. A **committed golden digest + pytest gate** now locks all of it in — any accidental edit to a curated line, matching regex, routing threshold, or registry rule fails CI — and a **flavor-lint gate** guards the 1,628-tail library for gender-pronoun consistency (via a machine-readable `AGENT_GENDER` map), known situations/tags, and no empty/duplicate tails
- **Audio-domain wake-word removal** — the wake word is cut from the captured audio by VAD segmentation (a generous pre-roll captures the full command, then the leading wake-word segment is dropped), so the command's first word is never clipped **and** no mis-transcribed "…tron" tail ever leaks into STT — without growing a text-strip blocklist (`KENNING_WAKE_TRIM_TO_SPEECH`)
- **Live-testing capture hardening** — a real-voice testing pass fixed the ways Ultron could go quiet or mishear: a **mid-utterance pause no longer truncates** the transcript (the latency-saving speculative STT re-validates instead of committing a stale pre-pause partial); a brief **post-wake pause no longer cuts the command short** (a Smart-Turn min-speech floor extends a sub-1s fragment instead of submitting it); a **stalled USB mic stream self-heals** (a capture-stall watchdog restarts the input stream after ~1s of no callbacks, so a heavy CPU turn can't leave Ultron intermittently deaf); Whisper decode-bias is **always** the Valorant domain vocabulary (a stale `.env` override no longer shadows it, killing agent-name mishears + phantom leads); and the `ultron` wake model's **consecutive-frame sustain gate** was tightened (4 frames) to reject high-score confusables like "Oh, we…" without lowering recall. The team-relay LLM is also **pinned to the Ultron persona** (it can never leak the desktop "Kenning" identity onto the team mic), and the runtime voice toggles (**flavor off/on**, GPU↔CPU model switch, team-relay mute) are wired into the lean-gaming dispatch so they work mid-match. A later pass closed the last "didn't respond at first" gap: a command spoken with **no pause after "Ultron"** used to land entirely in the cold pre-roll, which was fed to STT but **not** the VAD — so the live VAD saw only trailing silence and the buffer (with the command) was discarded as empty. The pre-roll is now VAD'd so that speech is seen on the first try (and a bare "Ultron" with no command cleanly stands down instead of misrouting)
- **Flavor-tails-OFF response sets** — turning tails off ("Ultron, flavor off") doesn't just strip the in-character tail off callouts; the social / identity / economy / banter commands switch to a dedicated **curated, tail-free, addressee-adapted** set tuned for crisp combat comms — soundboard / voice-changer / streamer rebuttals ("No, I am not a soundboard. I am Ultron."), thank-you / nice-try / nice-shot / well-played / my-bad / sorry, a 10-line **"I got this"** clutch pool, buy / save / "buy me a `<weapon>`" / "drop me their `<weapon>`" / "take this `<weapon>`" requests, verbatim word-for-word ("Guys, …" / "`<Agent>`, …"), flaming / cringe / shut-up / stop comebacks, "encourage the team", "flame the enemy", and "flame my `<agent>`". A named agent gets the "…, `<Agent>`" form; multi-line pools rotate longest-unused. Flavor-ON behaviour is unchanged — a single hook switches only the overlapping categories when tails are off. A follow-up routing pass made a **bare "say hello"** (no target) default to the team instead of falling to the LLM, and gave **"`<agent>` told you to stop"** a deterministic defiance match (it previously depended on whether the embedder sidecar was reachable) — while a tactical "stop pushing" / "stop rotating B" still relays normally. The toggle itself is now **mishear-tolerant** and matched on the *raw* transcript: "flavor" isn't Valorant vocab, so the domain-biased STT mangled "flavor off" into "save her off" (which then relayed as an eco call) — the toggle now maps the homophone mishears (save her / favor / saver / labor / tails … off|on) back to the command, with guards so "back off", "we're on", "lock on", "push on A", bare "save" still relay

</td>
<td width="50%" valign="top">

### 🧠 Reasoning
- Local LLM in-process via `llama-cpp-python`
- Speculative decoding wired (prompt-lookup + draft model)
- Hot-swap presets by voice: `"switch to the 8B"`
- Three-layer memory: recent cache · RAG (bge-small + BM25 RRF) · project digest
- Adaptive context window scoring; ambiguity gating
- Tiered web-search freshness gate (regex → semantic intent → preflight LLM)

</td>
</tr>
<tr>
<td valign="top">

### 🌐 Web + tools
- Local-first **SearxNG** (Docker) → Brave → DuckDuckGo cascade
- Trafilatura → Jina reader cascade
- 23-kind routing intent classifier
- Native desktop automation (12-entry launcher: Chrome, Discord, Spotify, +9)
- News-category routing for current-events queries
- Optional **OpenClaw** peer gateway for proactive comms

</td>
<td valign="top">

### 🛡️ Safety + ops
- **141-rule** tool-call validator across 19 categories
- Tamper-evident SHA-256 hash-chain audit log
- **Gaming-mode** VRAM reclaim chain (~2.3 GB freed on demand) + a **bare-bones profile** (optionally auto-engaged at boot): LLM swapped to a **CPU-only** 3B, Kokoro TTS → CPU, Parakeet stopped, VLM unloaded, and per-turn RAG retrieval / reranker / web-search skipped — near-zero GPU so it never costs game frames, while the voice + team relay stay live
- **Anticheat-safe mode** — a 3-layer hard block (module guards · validator BLOCK_HARD · surface-stop hooks) on *every* desktop-interaction surface (input injection, screen capture, OCR, UIA, clipboard, window control, browser CDP), pinnable always-on for running beside kernel anticheats; audio + the voice/team relay + the overlay stay live. A loader-level **import firewall** keeps the whole automation stack out of RAM entirely (blocklist now also covers `keyboard`/`mouse`/`pydirectinput`/`d3dshot` and the stale `ultron.*` mirror prefixes), and is installed **before the orchestrator constructs** so there's no unprotected boot window. Safe-by-default: the gaming + anticheat schema defaults to engaged even if `config.yaml` is lost; a boot posture canary derives its tripwire straight from the firewall's blocklist and logs at ERROR on any regression; the OpenClaw MCP runner hard-refuses to start while anticheat is active. The firewall now **fails safe** — if the anticheat state can't be determined it blocks the import anyway — and **proves it actually bites at boot**: a live enforcement probe imports a blocked-but-absent input-injection driver and verifies the refusal came from the firewall (logging an ERROR if any blocked import ever succeeds). The blocklist was widened to the rest of the CDP/webdriver, screen-capture, clipboard, OCR, and virtual-gamepad families (all pure defense-in-depth — none are on any voice/relay/audio path). The orchestrator is imported **lazily, after** the firewall installs (no unprotected import window), and the process **refuses to start at all** (fatal) if anticheat is active but the firewall isn't installed and enforcing
- Typed event bus — `turn.started` · `gate.verdict` · `supervisor.decided` · 14 more
- opencode-inspired project digest + supervisor stack
- **Testing-mode full-flow usage trace** — in testing mode every turn appends a structured record to a durable history (`logs/usage_trace.jsonl`, plus a `turn:flow` log line) capturing the whole pipeline: raw STT → normalized payload → route + reason (snap / curated / identity / leak-deflect / answer / LLM) → final spoken line → channel (team-mic vs desktop). No-op and zero-cost outside testing mode, so historical logs show exactly how each utterance was heard, routed, and answered
- **No runaway orphan processes** — a layered cleanup guarantee so no child Ultron spawns (the embedder sidecar, MCP, any helper) can ever survive: a graceful `shutdown()` reap on the with-block / SIGINT / SIGTERM / atexit paths, a final **kill-all-descendants catch-all** behind it, a **parent-death deadman** inside the embedder that self-terminates within seconds if the orchestrator dies by *any* means (crash, `taskkill /F`, TerminateProcess) — the gap no in-parent cleanup can cover — and a **boot-time sweep** that reaps any stale embedder (by port owner *and* by command-line, catching an un-bound duplicate even if a prior session was force-killed)
- Pre-push hygiene hook on the repo itself

</td>
</tr>
</table>

---

## 🏗️ Pipeline

```text
mic → wake "kenning" OR addressing classifier (WARM)
  → Silero VAD + Smart Turn V3 (CPU, ~12 ms)
  → STT: DualSTTRegistry (moonshine | parakeet | whisper)
  → Intent recognizer (Gemma-300M CPU): short-circuits gaming / fresh-data intents
  → Local clock reply for bare time/date queries (~5 ms, no LLM)
  → classify_routing() → 23 RoutingIntentKind dispatches
      ├─ coding kinds → AI coding agent subprocess (optional supervisor stack)
      ├─ OPEN_LAST_SOURCE → opens cited URL from prior search
      ├─ NAVIGATE_TO_SITE → SearxNG top-10 → domain-score → opens best
      ├─ APP_LAUNCH        → native Chrome/Discord/Spotify launcher
      ├─ GAMING_MODE       → VRAM reclaim chain (~2.3 GB freed)
      ├─ conversational    → LLM (Qwen 3.5 4B) with optional:
      │                       · web-search gate (rules + preflight LLM)
      │                       · multi-pass RAG retrieval
      │                       · news-category SearxNG routing
      └─ stream tokens → Kokoro TTS (CUDA, fine-tuned voice)
  → typed-bus events publish at every stage
  → async-write conversation turn to Qdrant
  → (follow-up window OFF by default — every turn requires the wake word)
```

> 📖 **Full per-module reference:** [`docs/codebase_structure.md`](docs/codebase_structure.md) — the binding single-source map of the system.

---

## 🚀 Quick start

```bash
# 1. Clone
git clone https://github.com/1v9Khan/ultronPrototype.git
cd ultronPrototype

# 2. Python 3.11 + deps (~7 GB; PyTorch CUDA, llama-cpp, faster-whisper, Kokoro, ...)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS (untested)
pip install -e .

# 3. Models (~5 GB; wake word, Smart Turn, Moonshine, Kokoro, Qwen GGUFs)
python scripts/download_models.py

# 4. Configure
copy .env.example .env          # optional: add Brave API key for web search
# tune config.yaml for your mic / monitors / preferences

# 5. Launch
python -m kenning
```

Then say: **"kenning"** — and start talking.

> ⚠️ **This is a research prototype**, not a turn-key product. It targets one developer's specific hardware (RTX 4070 Ti, AMD CPU, Windows 11) and use case. Treat the setup as a recipe to adapt, not a one-click install. Some optional integrations (OpenClaw, Telegram, ComfyUI media gen, mobile node) require additional credential-dependent setup — see the docs below.

---

## 💻 System requirements

|  | Recommended | Minimum |
|---|---|---|
| **GPU** | RTX 4070 Ti (12 GB) | RTX 3060 (12 GB) — untested, expect higher latency |
| **CPU** | AMD Ryzen 7 5800X+ (8c/16t) | 4 cores / 8 threads |
| **RAM** | 32 GB | 16 GB (constrained) |
| **Disk** | 30 GB free | 20 GB free |
| **OS** | Windows 11 | Windows 10 / Linux (untested) |
| **Python** | 3.11 | 3.10+ |
| **CUDA** | 12.4+ | 11.8 |

---

## ⚙️ Configuration

All tunables live in `config.yaml` at the project root — schema-validated by Pydantic in `src/kenning/config.py`. The top of that file lists the ~12 actively-tuned knobs.

Key sections:

| Section | What it controls |
|---|---|
| `audio` | Mic input device + output device + ring buffer |
| `vad` · `stt` | VAD silence thresholds + STT engine selector + gaming fallback |
| `llm` | Preset + n_ctx + speculative decoding + KV cache |
| `tts` | Engine + voicepack + boundary smoothing + cadence |
| `memory` | Qdrant store + RAG top-k + min-relevance + contextual retrieval |
| `web_search` | Provider chain + reader chain + ranker dispatch |
| `safety` | 141 rule toggles + sandbox roots + audit log path |
| `coding.supervisor` | opencode-inspired project digest stack (default OFF) |
| `gaming_mode` | VRAM reclaim chain triggers + targets |

Override via `KENNING_*` env vars; see `.env.example`. Restart after any change.

---

## 📚 Documentation

> 👉 **Start here:** [`docs/codebase_structure.md`](docs/codebase_structure.md) — the binding single-source map of every module, script, test, and runtime artifact. Maintenance contract enforced per commit.

<details>
<summary><b>🏛️ Architecture + operations</b></summary>

| Doc | Topic |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Pipeline overview + hardware target |
| [`docs/configuration.md`](docs/configuration.md) | Per-key config reference |
| [`docs/operations.md`](docs/operations.md) | Day-to-day running + recovery |
| [`docs/development.md`](docs/development.md) | Test layout + debugging recipes |
| [`docs/routing.md`](docs/routing.md) | Capability routing |
| [`docs/error_handling.md`](docs/error_handling.md) | Error catalog |
| [`docs/4b_optimization_plan.md`](docs/4b_optimization_plan.md) | 4B LLM migration (complete) |

</details>

<details>
<summary><b>🔌 OpenClaw integration</b> — peer gateway for proactive comms + tools</summary>

| Doc | Topic |
|---|---|
| [`docs/openclaw_integration_final_summary.md`](docs/openclaw_integration_final_summary.md) | Cross-phase summary + setup checklist |
| [`docs/openclaw_telegram_setup.md`](docs/openclaw_telegram_setup.md) | Telegram channel (bot token) |
| [`docs/openclaw_heartbeat_setup.md`](docs/openclaw_heartbeat_setup.md) | Heartbeat agents block |
| [`docs/openclaw_browser_setup.md`](docs/openclaw_browser_setup.md) | Browser tool (Playwright + Chromium) |
| [`docs/openclaw_cron_setup.md`](docs/openclaw_cron_setup.md) | Cron jobs (Task Scheduler fallback) |
| [`docs/openclaw_hooks_setup.md`](docs/openclaw_hooks_setup.md) | Bundled hooks |
| [`docs/openclaw_memory_wiki_setup.md`](docs/openclaw_memory_wiki_setup.md) | Memory Wiki plugin |
| [`docs/openclaw_media_generation_setup.md`](docs/openclaw_media_generation_setup.md) | Local ComfyUI media generation |
| [`docs/mobile_node_setup.md`](docs/mobile_node_setup.md) | iOS / Android pairing |

</details>

<details>
<summary><b>🧪 Test pass reports</b></summary>

| Doc | Topic |
|---|---|
| [`docs/comprehensive_test_plan.md`](docs/comprehensive_test_plan.md) / [`comprehensive_test_report.md`](docs/comprehensive_test_report.md) | Functional pass (16 phases, 38 dimensions) |
| [`docs/comprehensive_quality_plan.md`](docs/comprehensive_quality_plan.md) / [`comprehensive_quality_report.md`](docs/comprehensive_quality_report.md) | Quality pass (Q0–Q13, 38 dimensions, prompt-injection defense audit) |
| [`docs/smoke_test.md`](docs/smoke_test.md) | 16-step interactive smoke procedure |

</details>

---

## 🧭 Project status

This is a **research prototype**, not a production product. It evolves through many tight iteration cycles. Behavior-changing features land behind feature flags (default OFF) until live-validated. The voice-quality baseline is treated as a strict latency / VRAM contract — any hot-path change re-runs `scripts/measure_baseline.py` and documents the delta.

If you're reading the source, the highest-leverage entry point is [`src/kenning/pipeline/orchestrator.py`](src/kenning/pipeline/orchestrator.py) — the main event loop everything else hangs off.

---

## ⭐ Star history

If you find Kenning interesting, a star helps it surface to other folks who want a local voice assistant.

[![Star History Chart](https://api.star-history.com/svg?repos=1v9Khan/ultronPrototype&type=Date)](https://star-history.com/#1v9Khan/ultronPrototype&Date)

---

## 📜 License

MIT — see [`LICENSE`](LICENSE).

---

## 🙏 Acknowledgments

Built on the shoulders of these open-source projects:

[bge-small](https://huggingface.co/BAAI/bge-small-en-v1.5) · [DuckDuckGo](https://duckduckgo.com/) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [flan-t5-small](https://huggingface.co/google/flan-t5-small) · [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) · [llama.cpp](https://github.com/ggerganov/llama.cpp) · [moondream2](https://huggingface.co/vikhyatk/moondream2) · [Moonshine](https://github.com/usefulsensors/moonshine) · [opencode](https://github.com/sst/opencode) · [openWakeWord](https://github.com/dscripka/openWakeWord) · [Parakeet TDT](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) · [Piper](https://github.com/rhasspy/piper) · [pywinauto](https://github.com/pywinauto/pywinauto) · [Qdrant](https://qdrant.tech/) · [Qwen 3.5](https://huggingface.co/Qwen) · [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) · [SearxNG](https://github.com/searxng/searxng) · [Silero VAD](https://github.com/snakers4/silero-vad) · [Smart Turn V3](https://huggingface.co/pipecat-ai/smart-turn-v3) · [Trafilatura](https://github.com/adbar/trafilatura) · [XTTS v2](https://huggingface.co/coqui/XTTS-v2)

<div align="center">

---

<sub>Built for one developer's RTX 4070 Ti, then shared.</sub>

</div>
