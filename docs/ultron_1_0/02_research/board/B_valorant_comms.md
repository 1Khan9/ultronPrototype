# Valorant comms / callout conventions: vocabulary, economy terms, brevity, info-priority

**Research date:** 2026-06-20
**Scope:** Standard competitive Valorant communication vocabulary — positional callouts, economy round terminology, spike/plant/defuse/rotate shorthand, and the brevity + info-priority model that a good callout follows. Goal: inform the no/low/high VERBOSITY levels for Ultron 1.0's relay path.

---

## TL;DR recommendation for Ultron 1.0

**Relay verbosity should map directly onto the tactical callout hierarchy:**

| Verbosity level | What Ultron adds beyond the raw relay | Example relay |
|---|---|---|
| **None (bare relay)** | Exactly what the user said, stripped to action+location | "Two B long." |
| **Low** | Adds count, damage/util state if known, or a spike-status suffix | "Two B long, one tagged 70." |
| **High** | Full callout: count + location + state + action directive + flavor tail | "Two pushing B long — one's low, no flash left. Hit A." [+ Ultron tail] |

The standard competitive callout formula is `[Count] [Location] [Action] [Condition]` — e.g., "Two B main, walking" or "One heaven, no util." This is the atomic unit everything should reformat to. Ultron's LLM prompt templates should enforce this order. The economy vocab is a small closed set (~8 terms) and can be fully covered by snap-matchers or exemplar injection without LLM reasoning.

---

## Findings

### 1. Positional callout vocabulary — universal layer

These terms are map-agnostic and used on every Valorant map. Any relay touching locations must understand them.

**Lane / zone labels:**
- **Main** — primary choke entering a site (A Main, B Main)
- **Site** — the actual plant zone
- **Mid** — central corridor linking both sites
- **Link** — connector between a lane and a site, or between Mid and a site
- **Lobby** — staging area before Main (safer; used for defaults/regrouping)
- **Elbow** — a bent corridor; common retake route
- **Window** — a sightline cutout / high-value angle

**Elevation labels:**
- **Heaven** — upper platform or balcony overlooking a site
- **Hell** — under-platform / below Heaven
- **Back site** — deep defensive area behind the default plant spot

**Distance / position modifiers:**
- **Close / Deep** — distance along a lane
- **Top / Bottom** — elevation
- **Off-angle** — non-standard / unexpected angle

**Per-site named positions (map-specific, community-standardised):**
Cubby, Long, Short, Garage, Garden, Catwalk, Pit, Stairs, Hall — actual names vary per map. The sidecar EmbeddingGemma and RapidFuzz fuzzy matcher already handles ASR-mangled versions of these (e.g., "pit" vs "pit side", "cat" vs "catwalk").

**Source:** [ONE Esports terms guide](https://www.oneesports.gg/valorant/valorant-terms-calls-comms/), [Boosteria map callouts 2026](https://boosteria.org/guides/valorant-map-callouts-guide-2026-terms-rotations), [DiamondLobby glossary](https://diamondlobby.com/valorant/glossary/)

---

### 2. The canonical callout format

**Formula: `[Count] [Location] [Action] [Condition]`**

This is confirmed by multiple independent coaching sources as the competitive standard.

- Count: exact number ("one", "two", "three", "five") — never vague ("some guys")
- Location: specific zone name ("B main", "heaven", "link")
- Action (optional but high-value): what they're doing ("walking", "pushing", "peeking", "lurking")
- Condition (optional): damage, utility state, spike info ("one shot", "tagged 70", "no flash")

**Concrete examples from sources:**
- "Two B main, walking" — the complete 4-element callout
- "One heaven, no util"
- "One close left"
- "One tucked back site"
- "Two front site"
- "One flank"

**Anti-patterns (what good comms avoid):**
- Vague: "some guys are somewhere" → noise
- Redundant: repeating a callout 3× after initial delivery → distraction
- Emotional: "why are you there?" → restricted comms, no info value
- Unconfirmed guesses: "I think there's two?" → damages trust

**The golden brevity rule** (from BoostRoom IGL guide): *"Talk to change an action. If your words won't change what anyone does next, don't say them."*

**Source:** [BoostRoom IGL guide](https://boostroom.com/blog/communication-callouts-how-to-igl-in-solo-queue-without-being-toxic), [Boosteria 40-callout playbook](https://boosteria.org/guides/valorant-communication-playbook-40-ranked-winning-callouts), [Gankster teamplay guide](https://gankster.gg/effective-communication-and-callouts-the-teamplay-guide-for-valorant/), [Blix.gg voice tips](https://blix.gg/blog/news/valorant/valorant-voice-communication-tips/)

---

### 3. Information priority hierarchy

Multiple coaching sources converge on the same 4-tier hierarchy of what to say first:

1. **Enemy position: count + location** (highest value, time-sensitive)
2. **Utility / ability state** (flash used, smoke fading, drone out, ult available)
3. **Spike status** (spike down / planted / location of plant)
4. **Timing / tempo indicators** (they're walking, rushing, defaulting)
5. **Actionable directive** (rotate, hold, retake, push) — IGL role

During active fights: **silent** except for critical contact/death calls. Clutch = minimal comms, hard info only.

**Negative info is equally valid:** "No one B Main for 30 seconds" is as tactically valuable as a positive callout — tells the IGL a site is open.

**Source:** [Boosteria 40-callout playbook](https://boosteria.org/guides/valorant-communication-playbook-40-ranked-winning-callouts), [BoostRoom IGL guide](https://boostroom.com/blog/communication-callouts-how-to-igl-in-solo-queue-without-being-toxic), [Blix.gg voice tips](https://blix.gg/blog/news/valorant/valorant-voice-communication-tips/)

---

### 4. Damage and combat-state callouts

These are the most time-sensitive callouts and carry the highest per-word information density:

| Callout | Meaning |
|---|---|
| "Tagged [HP]" | Enemy is damaged; HP remaining (e.g., "tagged 70" = 30 hp taken) |
| "One shot" | Enemy at 1-hit-kill HP for almost any gun; do NOT overuse — trust degradation |
| "No armor" | Enemy has no shields |
| "Traded" | You killed the enemy that killed your teammate |
| "Clear" | Zone has been checked and is empty |

**Agent/ability state callouts:**
- "[Agent] used [ability]" — e.g., "Jett used dash", "Sova drone out"
- "No flash" — flash resource expended
- "Smoke fading" — controller smoke timing out soon
- "Ult ready" / "Ult used" — ultimate status
- "Molly on spike" — post-plant lineup active
- "Wall broken" — sentinel utility disabled

**Source:** [Boosteria 40-callout playbook](https://boosteria.org/guides/valorant-communication-playbook-40-ranked-winning-callouts)

---

### 5. Economy terminology — closed vocabulary set

**Round types and buy calls:**

| Term | Credit context | What teammates say |
|---|---|---|
| **Pistol round** | 800 cr start; no previous economy | (implicit — round 1 / round 13) |
| **Eco / Save / Full save** | Under ~2,000 cr; buy almost nothing | "Save this round" / "full eco" |
| **Half buy** | ~2,000–3,000 cr; light weapons, mixed shields | "Half buy" / "light buy" |
| **Force buy** | Sub-threshold but spend everything | "Force this" / "force buy" |
| **Bonus round** | After winning pistol + second round; hold cheap guns | "Bonus round, hold Spectre" |
| **Full buy** | 3,900+ cr (rifle + full shields + util) | "Full buy together" |
| **Anti-eco** | Full buy vs. enemy eco — don't let them get rifles | "Anti-eco, don't let them get guns" |

**Credit mechanics (authoritative numbers, stable across 2024–2026):**
- Start: 800 cr
- Win round: 3,000 cr
- Kill: 200 cr
- Spike plant bonus: 300 cr (attacking team only)
- Loss bonus (streak): 1,900 / 2,400 / 2,900 cr (1 / 2 / 3+ consecutive losses)
- Credit cap: 9,000 cr
- Vandal/Phantom: 2,900 cr; Operator: 4,700 cr; Ghost: 500 cr; Sheriff: 800 cr; Full shields: ~1,000 cr

**Key economy coordination phrase:** "Decide as a five" — mixed buys (2 save + 3 force) produce the worst outcome for everyone. The call is always team-wide.

**Source:** [ValoBub economy guide](https://valohub.co/guides/valorant-economy-guide), [DiamondLobby glossary](https://diamondlobby.com/valorant/glossary/), [Dignitas economy 101](https://dignitas.gg/articles/valorant-economy-101-a-guide-to-manage-your-credits), [Boosteria economy guide](https://boosteria.org/guides/valorant-economy-guide-buy-force-bonus-full-save)

---

### 6. Spike / plant / defuse / post-plant vocabulary

**Planting:**
- "Spike down" — spike has been planted; most important post-plant callout
- "Planting safe" — planting in cover, not exposed
- "Planting for [location]" — planting in a spot that favors a specific post-plant angle (e.g., "planting for main")
- "Plant default" vs "plant open" — default = community-standard spot; open = exposed position. These completely change post-plant positioning.
- "Safe plant" — behind cover, teammates covering planter

**Post-plant:**
- "Post-plant" — the phase after spike is planted; attackers shift to defensive play
- "Play for time" — use utility to stall retake; don't peek
- "Play crossfire" — hold two angles that cover each other
- "Tap spike, I swing" — baiting a defuse attempt to create a swing opportunity
- "Half it" — start defusing to provoke enemy action, then stop
- "Fake defuse" — begin defuse briefly to bait enemy peek
- "Stick" — teammate covering; keep defusing
- "Spike tapped" — someone started defusing
- "Exit frag" — kill an attacker leaving site after plant

**Defusing:**
- "Defusing" — callout that someone is on the spike
- "Ninja defuse" — stealth defuse without enemy knowing
- "On spike" / "Watching spike" — covering the spike from a position

**Source:** [DiamondLobby glossary](https://diamondlobby.com/valorant/glossary/), [Boosteria map guide 2026](https://boosteria.org/guides/valorant-map-callouts-guide-2026-terms-rotations), [Switchblade Gaming spike mechanics](https://www.switchbladegaming.com/valorant/spike-mechanics-guide/), [Red Bull spike guide](https://www.redbull.com/ca-en/spike-guide-valorant), [Boosteria 40-callout playbook](https://boosteria.org/guides/valorant-communication-playbook-40-ranked-winning-callouts)

---

### 7. Rotation and map-control vocabulary

| Term | Meaning |
|---|---|
| **Rotate** | Move from one site/zone to another |
| **Hold rotate** | Don't rotate yet; wait for more info |
| **They rotated off** | Enemy left a site (creates opportunity) |
| **Retake** | Reclaim a site the enemy took |
| **Lurk** | Solo attacker holds back, waits for an opportunity on the opposite side |
| **Flank** | Attack from rear or unexpected side |
| **Anchor** | Defender holding site alone while others rotate |
| **Stack** | Concentrate multiple defenders on one site |
| **Default** | Slow play, gather info, wait for enemy commitment before executing |
| **Rush** | All five push same location simultaneously |
| **Execute** | Coordinated hit on a site with utility |
| **Fake** | Appear to hit one site, then redirect to the other |

**Timing vocabulary (IGL-layer):**
- "Contact" — move quiet, don't reveal, punish aggression
- "Scale" — take space step-by-step with trades
- "Explode" — fast hit with layered utility
- "Reset" — stop, regroup, re-approach
- "Late" — intentionally slow; burn utility or force rotates
- "Pinch" — attack from two sides simultaneously
- "Pressure [lane], I'm falling / I'm staying" — rotation communication template

**Round timing cues:**
- 1:10 mark: utility wave 1; common execute timing
- 0:20 mark: utility wave 2 / final window
- "Play time" — use the clock; don't over-peek
- "Save exit" — spike will detonate; save weapons for next round exit kills

**Source:** [Boosteria map callouts 2026](https://boosteria.org/guides/valorant-map-callouts-guide-2026-terms-rotations), [BoostRoom IGL guide](https://boostroom.com/blog/communication-callouts-how-to-igl-in-solo-queue-without-being-toxic), [ONE Esports terms](https://www.oneesports.gg/valorant/valorant-terms-calls-comms/)

---

### 8. The 40-callout competitive playbook (verified categories)

From the Boosteria 40-ranked-callouts playbook — these represent the minimum viable callout vocabulary for competitive play, organized by category:

**Contact/Position (10):** "One close left", "One close right", "One tucked", "One wide", "One off-angle", "Two front site", "One back site", "One heaven", "One hell", "One flank"

**Damage/Utility (10):** "Tagged 80", "One shot", "No armor", "He used dash", "No flash", "Smoke fading", "Drone out", "Trap here", "Molly on spike", "Wall broken"

**Tempo/Map Control (10):** "They're walking", "They're rushing", "Contact only", "Defaulting", "They gave space", "Mid is open", "Spike spotted", "Spike down", "They rotated off", "Hold rotate"

**Execute/Teamplay (10):** "Flash in three, two, one", "Swing on my contact", "I can smoke for plant", "Planting safe", "Planting for main", "Play crossfire", "Play time", "Tap spike, I swing", "Half it", "Save exit"

**Source:** [Boosteria 40-callout playbook](https://boosteria.org/guides/valorant-communication-playbook-40-ranked-winning-callouts)

---

### 9. Verbosity levels — what this maps to

Based on the research synthesis, three distinct communication "densities" emerge naturally:

**Bare / No verbosity (info-only):**
- Just the atomic `[Count] [Location]` — pure position data
- Example: "Two B main." / "One heaven." / "Spike down."
- Used: during active firefights; when the teammate is in the middle of an action
- Principle: "If words won't change what anyone does next, don't say them"

**Low verbosity (info + state):**
- `[Count] [Location] [Action/State]` — adds damage, util, or movement qualifier
- Example: "Two B main, walking." / "One heaven, tagged 80." / "Spike down, planted for main."
- Used: during setup phase; when the state materially changes teammate decision-making

**High verbosity (full callout + directive):**
- `[Count] [Location] [Action] [State] + [Directive]` — includes what to DO next
- Example: "Two pushing B main, one's one-shot, no flash. Rotate B, I've got site." / "Spike down, planted for main, play crossfire from CT and back site."
- Used: during buy-phase planning; when an IGL-style directive is needed; when Ultron's persona is appropriate (cold superior analysis of the round state)
- This is the only level where Ultron's flavor tail is appropriate — adding it on bare callouts clutters the channel

---

## Concrete techniques / params we should adopt

### A. Callout format normalizer (STT post-processing)
The EmbeddingGemma + RapidFuzz layer should normalize ASR mangled callouts to canonical form before relay. Priority mismatches to handle:
- "three guys B main" → "Three B main" (strip "guys")
- "they hit A" → "Pushing A" (verb normalization)
- "bomb down" → "Spike down" (game-specific alias; "bomb" is CS:GO legacy)

### B. Economy snap matcher (no LLM needed)
Economy calls are a closed vocabulary of ~8 terms. All should be deterministic snaps, not LLM-routed:
- "eco this" / "save" / "full save" → ECONOMY_ECO snap
- "force" / "force buy" / "force it" → ECONOMY_FORCE snap
- "full buy" / "buy together" → ECONOMY_FULL snap
- "half buy" / "light buy" → ECONOMY_HALF snap
- "bonus" / "bonus round" / "hold SMG" → ECONOMY_BONUS snap

Each snap injects the relevant vocabulary into the relay as a concise team message with an Ultron-flavored editorial (cold, superior acknowledgment of the economic state).

### C. Spike/post-plant phrase injection
When the user says any spike-related call, Ultron's relay should preserve the exact plant-location information — this is highest-priority tactical data. Verbosity level controls whether Ultron adds a post-plant directive:
- None: "Spike down, back site." (exact relay)
- Low: "Spike down, back site. Play time." (adds tempo directive)
- High: "Spike planted back site. Hold your angles — crossfire from CT and back. They have to push." (full analysis)

### D. Damage callout precision enforcement
User said "tagged 70" → relay exactly as "Tagged 70" not paraphrased. Ultron's prompt template for damage state: preserve the HP number exactly; do not round or editorialize the number. "One shot" should only be relayed if the user said it — Ultron should NOT infer "one shot" from a damage number.

### E. IGL-directive layer (High verbosity only)
When verbosity is HIGH, the LLM prompt should include:
- The 3-sentence IGL model: Observation → Plan → Trigger
- Example format injection: "Two pushing B. Let's anchor A, one rotates on a pick. If they commit B, we retake together at 0:25."
- The 1628-tail flavor library provides Ultron's persona; the IGL directive provides the tactical structure. They should not overlap — flavor goes on the END of the callout, not in the tactical layer.

### F. Verbosity trigger heuristics
Based on competitive communication norms, the following round-state signals should push verbosity UP:
- Spike planted → always relay spike location (Low floor)
- Economy round callout → relay buy call + Ultron editorial (Low floor)
- Clutch situation → verbosity forced DOWN to bare (Ultron stays quiet; only hard info)
- Full execute call ("let's hit A") → High verbosity appropriate (IGL mode)

### G. Template exemplars for the 8B LLM
The 40-callout vocabulary should be injected into the LLM context as few-shot exemplars when building relay phrases. This gives the 8B model the correct register (terse, location-first, count before state) without relying on its training distribution for Valorant jargon. The Josiefied-Qwen3-8B model has been abliterated — it will not refuse tactical content — but its Valorant vocabulary calibration is unknown; exemplar injection compensates.

---

## Risks / caveats for our constraints

### 1. Anticheat path: no problem
All callout vocabulary (location names, economy terms, spike shorthand) is pure text. It lives in Python string literals and the prompt templates — no heavy ML required. The relay path (numpy + urllib + scipy + stdlib + rapidfuzz) is fully anticheat-safe for vocabulary lookup, snap matching, and callout normalization. Zero risk here.

### 2. EmbeddingGemma sidecar latency
The sidecar is already running for intent classification. If we use cosine similarity to detect economy / spike / rotation intent in the "undecided band" (when rules + fuzzy miss), this adds one sidecar round-trip (~15–30ms on loopback). For map-specific callout location names (highly map-dependent), embedding lookup is useful but should be the fallback after lexical matching — most callout terms are short, exact, and faster with RapidFuzz.

### 3. ASR mangling risk
Faster-Whisper / Parakeet is domain-biased for speech, not Valorant jargon. Known risk patterns:
- "Elbow" → "elbow" (fine); "Heaven" → "haven" (homophone collision with agent name); "Hell" → "hell" vs "Hele" vs "held"
- "Eco" → "echo" (common Whisper substitution — add "eco" to domain bias prompt)
- "Vandal" → usually correct; "Operator" → "operator" (fine)
- Agent names used as location proxies ("Jett hit 84") — already handled by the slot-callout forced-relay path (`_looks_like_slot_callout()`)
- Existing `_DOMAIN_PROMPT` whisper initial-prompt bug (shadow issue) noted in memory — must be fixed to get domain-biased ASR for these terms

### 4. Map-specificity
Positional callout names are partially map-specific. "Long" means different things on different maps; "CT" is a CS:GO legacy term that confuses some Valorant players. Ultron should not relay location names it didn't hear — only relay what was said. The relay's job is reformatting and injecting flavor, not inferring map-specific location names from context. This keeps the system correct across map rotations without requiring map-awareness.

### 5. Economy figure accuracy
Credit amounts (loss bonus tiers: 1,900 / 2,400 / 2,900) are stable but subject to Riot game balance patches. If the system ever needs to reason about credit amounts numerically (e.g., "do we have enough to full buy?"), it needs patch-versioned numbers. For Ultron 1.0, economy calls are relay-only (user decides, Ultron relays the call) — so stale credit numbers are not a risk unless we add budget-advisory features later.

### 6. "Bomb" vs "Spike" terminology
A significant fraction of players (especially CS:GO veterans, and likely users of the existing system) say "bomb" instead of "spike." The relay normalizer should map "bomb down" → "Spike down" for team communication, since Valorant teammates expect "Spike." This is a single-rule normalization.

### 7. Verbosity level control surface
The research confirms that over-communication is as harmful as under-communication ("Over communication may be as terrible as the lack of it" — Gankster guide). Ultron's High verbosity mode must have a hard cap: maximum 2 sentences of directive, then flavor tail. Do not allow the 8B LLM to produce multi-paragraph callout essays. Temperature/max_tokens constraints on the relay-generation prompt path are necessary.

---

## Sources (full URLs)

- [ONE Esports — Valorant terms and calls all players should know](https://www.oneesports.gg/valorant/valorant-terms-calls-comms/)
- [Boosteria — Valorant Communication Playbook: 40 Ranked-Winning Callouts](https://boosteria.org/guides/valorant-communication-playbook-40-ranked-winning-callouts)
- [Boosteria — VALORANT Map Callouts Guide 2026: Terms & Rotations](https://boosteria.org/guides/valorant-map-callouts-guide-2026-terms-rotations)
- [Boosteria — VALORANT Economy Guide: Buy, Force, Bonus & Full Save](https://boosteria.org/guides/valorant-economy-guide-buy-force-bonus-full-save)
- [BoostRoom — VALORANT Solo Queue IGL: Callouts Without Toxicity](https://boostroom.com/blog/communication-callouts-how-to-igl-in-solo-queue-without-being-toxic)
- [DiamondLobby — Valorant Terms Glossary](https://diamondlobby.com/valorant/glossary/)
- [Dignitas — Valorant Economy 101: A Guide to Manage Your Credits](https://dignitas.gg/articles/valorant-economy-101-a-guide-to-manage-your-credits)
- [ValoBub — Valorant Economy Guide 2026: Buy, Save, Force](https://valohub.co/guides/valorant-economy-guide)
- [Blix.gg — Valorant Voice Communication Tips](https://blix.gg/blog/news/valorant/valorant-voice-communication-tips/)
- [Gankster.gg — Valorant Callouts Guide: How to Communicate Like a Pro Teammate](https://gankster.gg/effective-communication-and-callouts-the-teamplay-guide-for-valorant/)
- [Switchblade Gaming — The 2.4-Second Rule That Wins Valorant Spike Rounds](https://www.switchbladegaming.com/valorant/spike-mechanics-guide/)
- [WeCoach — A Detailed Guide for Mastering the Valorant Economy](https://wecoach.gg/blog/article/a-detailed-guide-for-mastering-the-valorant-economy)
- [VLR.gg — IGL tips](https://www.vlr.gg/528188/igl-tips)
- [Red Bull — Spike guide for Valorant: How to carry, plant, and defuse](https://www.redbull.com/ca-en/spike-guide-valorant)
- [Valorant Fandom Wiki — Terminology](https://valorant.fandom.com/wiki/Terminology)
