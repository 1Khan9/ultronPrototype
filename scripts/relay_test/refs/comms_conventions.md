# Valorant — Team Communication Conventions
## Standard Callout Structure, Voice-Comm Vocabulary, Shotcalling, and Round Comms

> **Scope:** How competitive Valorant players communicate in real time — the structure of a
> callout, what information is relayed and when, IGL/shotcalling language, damage and
> economy calls, spike/plant/defuse calls, utility calls, and all shared vocabulary.
> This document grounds the Ultron relay corpus generation board for the `comms_conventions`
> slice. It does NOT replace per-map or per-agent ref files; cross-reference those for
> specific callout names and ability details.
>
> **Last verified:** June 2026. Sources: oneesports.gg, diamondlobby.com, gankster.gg,
> boosteria.org, esportsdriven.com, vlr.gg, redbull.com (IGL guide), progameguides.com,
> thespike.gg, gametree.me, thegamer.com, blix.gg, vocal.media, dignitas.gg, nerdaimers.com

---

## 1. ANATOMY OF A CALLOUT

A callout is the most fundamental communication unit in Valorant. The gold standard
structure is:

```
[COUNT] + [LOCATION] + [ACTION/STATE] + [CONDITION]
```

Each slot is optional but ordered by priority — drop from the right if time-pressed.

### 1a. Count

Always lead with the number of enemies:

| Phrase | Meaning |
|---|---|
| `"One ___"` | 1 enemy |
| `"Two ___"` | 2 enemies |
| `"Three ___"` / `"Multiple ___"` | 3+ enemies |
| `"Full send B"` / `"Five B"` | Full 5-stack pushing one site |
| `"Last one ___"` | 1 enemy alive (clutch context) |

Always state count first — "Two B Long" is more actionable than "B Long, two."

### 1b. Location

Use the exact map callout name. If the enemy is between two known positions:

- `"Pushing from Main into Site"` — direction of movement
- `"Between Heaven and Site"` — intermediate position
- `"Off-angle on site"` — unusual position on the site itself

**Elevation modifiers:** `upper`, `lower`, `top`, `bottom`, `heaven` (high), `hell` (below heaven).

**Distance modifiers:** `close`, `deep`, `far`, `mid-range`, `pushing`.

### 1c. Action / State

What the enemy is doing or what happened:

| Action Call | Meaning |
|---|---|
| `"Pushing"` | Actively moving toward you |
| `"Holding"` | Stationary, waiting |
| `"Peeking"` | Exposing briefly from cover |
| `"Rotating"` / `"Rotating off"` | Moving to another position/site |
| `"Lurking"` | One isolated player off main action |
| `"Rushing"` | Fast aggressive push, all in |
| `"Walking"` | Moving slowly / no sound |
| `"Planting"` | In spike-plant animation |
| `"Defusing"` | In spike-defuse animation |
| `"Baiting"` | Not trading; waiting for teammate to die first |
| `"Dropping"` / `"Dropping off"` | Leaving a position |

### 1d. Condition

Optional extra information:

- `"...one shot"` — enemy has very low HP, one bullet will kill
- `"...low"` / `"...lit"` — enemy is damaged
- `"...no armor"` — enemy has no shields
- `"...with Op"` — enemy has an Operator (sniper rifle)
- `"...used flash"` / `"...no flash"` — ability spent state
- `"...no util"` — enemy has no abilities remaining
- `"...on eco"` — enemy is on a save round (cheap loadout)

### 1e. Complete Examples

```
"Two B Long, one shot."                     → 2 enemies at B Long; one is nearly dead
"One CT, Op."                               → 1 defender at CT side holding Operator
"Three pushing A Main, rushed."             → 3 attackers fast-pushing A Main
"Last one site, defusing."                  → 1 enemy alive, actively defusing spike
"One close right, no armor."               → 1 enemy nearby to the right, no shields
"One tucked cubby, tagged 80."             → 1 enemy hiding in cubby, took 80 damage
"Two walking mid, no contact yet."         → 2 enemies moving quietly through mid
"They gave mid. No one mid 30 seconds."   → Negative info: mid is clear
```

---

## 2. INFORMATION PRIORITY HIERARCHY

Not all information is equal. When multiple things happen simultaneously, call in this
order:

1. **Enemy positions with counts** — the highest-value callout; enables teammates to rotate
2. **Spike status** — plant / defuse / carry location
3. **Utility deployed** — flash going in, smoke fading, drone out
4. **Damage dealt** — enemy HP state, especially "one shot"
5. **Your own status** — health, armor, ultimate readiness
6. **Economy** — what the enemy team is buying

### The Negative Info Rule

Calling what is NOT there is as valuable as calling what is:

```
"No one B Main, 30 seconds in."     → IGL can rule out B and commit A
"Nobody mid, their whole team A."   → Safe to rotate CT through mid
"They burned smoke — site is clear" → Utility depleted, push is safer
```

---

## 3. DAMAGE REPORTING

Damage calls are fast, numeric, and shared immediately after trading shots.

### 3a. Standard Damage Calls

| Call | Meaning |
|---|---|
| `"Tagged [X]"` / `"Hit him [X]"` | Dealt X damage to enemy |
| `"One shot"` / `"He's one shot"` | Enemy can be killed with one bullet to body |
| `"Low"` / `"He's low"` | Enemy has low HP (rough — not a specific number) |
| `"Dink"` / `"Dinked him"` | Landed a headshot that did NOT kill; enemy is very low |
| `"He's 100"` | Enemy is at full HP, undamaged |
| `"No armor"` | Enemy has no shields (body shots deal full HP damage) |
| `"100 HP no armor"` | Enemy is full HP but completely unshielded |
| `"Lit up"` / `"He's lit"` | Enemy took significant damage |

### 3b. When to Call Damage

- **Always** when you trade shots and survive — your team needs to know the enemy health
- **Always** when you dink — it signals a teammate should commit the kill
- **When exact** — say the number, not just "low" if you know it
- **During duels** — call before you die so teammates know to push

### 3c. What NOT to Do

- Do not give vague calls like "I hit him" without a number
- Do not call damage long after the shot — stale info is noise
- Do not report self-damage (from Snakebite / molly) as enemy damage

---

## 4. SPIKE / PLANT / DEFUSE CALLS

### 4a. Plant Phase Calls

| Call | When Used |
|---|---|
| `"Planting"` | You are beginning the plant animation |
| `"Spike down"` / `"Planted"` | Plant animation completed; round enters post-plant |
| `"Spike A"` / `"Spike B"` | Spike is planted on A Site or B Site |
| `"Safe plant"` / `"Planting safe"` | Planting in a protected/covered position |
| `"Plant for [location]"` | Orienting the spike toward a specific side, e.g., `"plant for main"` |
| `"Plant default"` | Using the most common/central plant position on that site |
| `"Plant open"` | Planting in the open (fast plant, higher risk, defender-facing) |
| `"Plant main"` / `"Plant CT"` | Planting toward the enemy's typical approach (creates line-of-sight post-plant) |
| `"Need a plant"` | Asking someone to initiate the plant animation; you're covering |
| `"I'm planting"` / `"Let me plant"` | Self-declaring your role in the sub-round |
| `"Spike A, 45 seconds"` | Post-plant time update with seconds remaining on spike |

### 4b. Post-Plant Phase Calls

After the spike is planted, roles shift:

| Call | When Used |
|---|---|
| `"Play retake"` | Defenders: regroup and reclaim the site before detonation |
| `"Play for time"` | Attackers: don't engage; delay until spike detonates; avoid risks |
| `"Play crossfire"` | Set up angles covering the defuse spot from two directions |
| `"Hold spike"` | Stay near the spike location; prioritize watching the defuse |
| `"They're defusing"` / `"Defusing"` | Enemy has begun defusing — call this immediately |
| `"Tap it"` / `"Tap spike"` | Partially defuse to bait the attacker into revealing position (fake defuse) |
| `"Half it"` | Defuse for half the defuse time, then stop — timing play |
| `"Full it"` / `"Stick it"` | Commit to full defuse; do not stop |
| `"Ninja defuse"` | Sneaking past attackers to defuse undetected |
| `"Fake defuse"` | Begin defusing to force attacker to peek or reveal; then stop and shoot |
| `"Molly spike"` / `"Util spike"` | Post-plant utility placed on or near spike to deny defuse |
| `"30 seconds"` / `"20 seconds"` | Spike timer countdown — call these for team awareness |
| `"Save it"` | 5 seconds or fewer on spike; not worth risking a defuse — let it blow |

### 4c. Spike Carrier Calls

| Call | Meaning |
|---|---|
| `"Who has spike?"` | Asking team to identify the spike carrier |
| `"I have spike"` | Self-identification as carrier |
| `"Drop spike"` | Asking carrier to drop it for another player to pick up |
| `"Pick up spike"` | Instruction to grab the dropped spike |
| `"Drop spike, I'll plant"` | Requesting the spike to personally handle the plant |

---

## 5. ECONOMY VOICE CALLS

Economy is a team system. Economy communication happens in the buy phase.

### 5a. Round Type Calls

| Call | Meaning |
|---|---|
| `"Full buy"` / `"We're buying"` | Team buys rifles + heavy armor + utility (≥3,900 cr) |
| `"Save"` / `"Eco"` / `"Save round"` | Minimal spend; bank credits |
| `"Force"` / `"Force buy"` / `"Forcing"` | Spend everything available even if below threshold |
| `"Half buy"` / `"Light buy"` | Mid-tier spend; SMG or cheap rifle + light armor |
| `"Bonus"` / `"Bonus round"` | Round 2 after pistol win; SMG + carry pistol gun |
| `"Anti-eco"` / `"They're saving"` | Adjust buy down since enemy is on eco |
| `"All Spectre force"` | Coordinated force: everyone buys the same cheap weapon |

### 5b. Credit / Drop Calls

| Call | Meaning |
|---|---|
| `"Econ check"` / `"What's everyone's econ?"` | Ask team to report their credits |
| `"I have 4,200, full buy"` | Self-reporting credits + intended action |
| `"I'm short, need a rifle"` | Requesting a drop |
| `"Drop me a Vandal/Phantom"` | Specific weapon request |
| `"I'll drop you a gun"` | Offering to buy for a short teammate |
| `"I got you"` | Confirming you'll drop |
| `"Can we drop?"` | Asking if anyone can afford to drop |
| `"Save next"` | After losing: call to eco next round |
| `"We're at full buy next"` | Confirming team can afford next round after this eco |

### 5c. Enemy Economy Intelligence

| Call | Meaning |
|---|---|
| `"They're on eco"` | Enemy is saving; expect cheap weapons |
| `"They have rifles"` | Enemy bought; full confrontation expected |
| `"Jett has Op"` | Specific weapon intel on specific enemy agent |
| `"Watch for eco rush"` | Warning team that eco teams often rush aggro to compensate |
| `"Don't feed them guns"` | Reminder not to die with expensive weapon on eco round |

---

## 6. UTILITY / ABILITY CALLS

### 6a. Announcing Outgoing Utility

Always announce utility BEFORE it lands — teammates need time to act.

| Template | Example |
|---|---|
| `"Flash in [direction]"` | `"Flash A Main in three, two, one"` |
| `"Flash [location], look away"` | `"Flash going into B, look away"` |
| `"Smoking [location]"` | `"Smoking CT, smoking main"` |
| `"[Ability] out [location]"` | `"Molly out B lobby"` |
| `"Drone out [location]"` | `"Drone pushing mid"` |
| `"Drone me"` | `"I'm in owl drone, protect my body"` |
| `"Shock [location]"` | `"Shocking Heaven on the back of Jett"` |
| `"Lineup [location]"` | `"Lineup for B site, ready"` |
| `"[Agent], flash me in"` | `"Phoenix, flash me in main"` |
| `"Throwing utility"` / `"Util in"` | Short generic warning |

### 6b. Counting Down Flash

Any flash call should include a countdown to synchronize the push:

```
"Flash Main in three... two... one... go."
```

### 6c. Ultimate Readiness

| Call | Meaning |
|---|---|
| `"Ult ready"` | My ultimate is charged and available |
| `"Ult up"` | Same as above |
| `"Ult [X] away"` / `"Need [X] more"` | X kills/orbs needed to charge ult |
| `"Using ult"` | Declaring you are activating ultimate this round |
| `"Save ult"` | Instruction to NOT use ultimate this round |
| `"Ult for execute"` | Saving ult for a coordinated site execution |

### 6d. Ability Status Calls

| Call | Meaning |
|---|---|
| `"No flash"` | Teammate/enemy has used their flash ability |
| `"Flash used"` | Flash ability is spent (cooldown or permanent for this round) |
| `"Smoke fading"` | A deployed smoke is about to expire — team can time a push |
| `"Smoke's gone"` / `"Smoke clear"` | Smoke has ended |
| `"Drone out"` | An Owl Drone / Skye creature / Tejo drone is active |
| `"Trap here"` | Enemy trap/tripwire detected at this location |
| `"Nanoswarm spike"` | KJ Nanoswarm on the spike (denial tool) |
| `"He's suppressed"` | KAY/O ZERO/POINT hit — enemy abilities are disabled |
| `"Lockdown coming"` | Killjoy ultimate deployed — detain zone incoming |
| `"Wall going"` / `"Wall's up"` | Viper Toxic Screen / Sage Barrier / Iso Contingency active |
| `"Sage wall broken"` | Sage's barrier was destroyed |
| `"Pit going"` | Viper's Pit ultimate deployed |
| `"Seekers out"` | Skye Seekers homing to enemy locations |
| `"Fade is haunting"` | Fade Haunt reveal orb is active |
| `"Prowler chasing"` | Fade Prowler tracking an enemy |
| `"Wingman planting"` | Gekko Wingman is in plant animation |
| `"Wingman defusing"` | Gekko Wingman is in defuse animation |

### 6e. Generic Ability Noun Calls

These are short in-game shorthand terms for abilities used as callout references:

| Term | Refers To |
|---|---|
| **Flash** | Any blinding ability (Phoenix Curveball, Breach Flashpoint, Skye Guiding Light, KAY/O FLASH/DRIVE, Reyna Leer, Yoru Blindside) |
| **Smoke** / **Smokes** | Any vision-blocking smoke (Omen Dark Cover, Brimstone Sky Smoke, Viper Poison Cloud/Toxic Screen, Astra Nebula, Harbor High Tide, Clove Ruse) |
| **Molly** | Any lingering damage ability (Brimstone Incendiary, Viper Snakebite, KAY/O FRAG/MENT, KJ Nanoswarm, Raze Paint Shells) |
| **Wall** | Any deployable wall (Sage Barrier Orb, Viper Toxic Screen, Iso Contingency, Deadlock Barrier Mesh, Harbor High Tide wall orientation) |
| **Stun** | Any concussive / stun (Breach Fault Line/Aftershock, Raze Blast Pack, Neon Relay Bolt, Gekko Dizzy/Wingman) |
| **Drone** | Sova Owl Drone; also Tejo Stealth Drone or Gekko (generic recon creature) |
| **Dog** | Skye Trailblazer |
| **Car** / **Roomba** | Raze Boom Bot |
| **Dart** | Sova Spycam dart OR Cypher Spycam dart |
| **Flash-plant** | Using a flash to cover the plant animation |
| **One-way** | A smoke that provides asymmetric visibility (you see through it, enemies do not) |

---

## 7. ROTATION CALLS

### 7a. Calling Rotations

| Call | Meaning |
|---|---|
| `"Rotate B"` | Everyone move to B site |
| `"Rotate A"` | Everyone move to A site |
| `"Rotate CT"` | Rotate through defender spawn (CT-side rotation route) |
| `"Rotate mid"` | Move through mid for a pivot |
| `"Hold rotate"` | Do NOT rotate yet; wait for confirmation |
| `"Don't rotate"` | Specific instruction: stay put |
| `"Fake rotate"` | Make noise of rotating, then return; bait the enemy |
| `"Slow rotate"` | Move to other site but take time / don't sprint |
| `"Fast rotate"` | Move to other site immediately |
| `"They rotated"` | Enemy has left their current position and gone elsewhere |
| `"They rotated off"` | Enemy has abandoned a site/position |
| `"They didn't rotate"` | Enemy stayed; site is undefended after rotation warning |
| `"Falling back"` | Moving away from current position toward spawn/safe area |

### 7b. Confirmation Protocol

After an IGL calls a rotation, teammates should confirm verbally:

```
IGL: "Rotate B, let's go."
Team: "Copy." / "On my way." / "B, copy."
```

Unconfirmed calls lead to disorganized rotations and site-abandonment disasters.

---

## 8. CONTACT AND POSITION CALLS

### 8a. Contact Calls

| Call | Meaning |
|---|---|
| `"Contact"` / `"Contact [location]"` | First enemy spotted or heard |
| `"I see one"` | Enemy spotted |
| `"They're here"` | Enemies arriving at your position |
| `"Entering site"` / `"On site"` | Enemies are entering or already on the bomb site |
| `"They're on site"` | All or some enemies have taken site control |
| `"Site lost"` | Defenders have ceded site control to attackers |
| `"No contact"` | No enemies at your position (negative info) |
| `"Nothing B"` | B side is clear (negative info) |

### 8b. Movement Intel Calls

| Call | Meaning |
|---|---|
| `"They're walking"` | Enemies moving slowly / silently — deliberate/quiet approach |
| `"They're rushing"` | Enemies fast-pushing — all-in aggressive play |
| `"Default" / "Defaulting"` | Enemy spreading for info-gathering round (no committed push) |
| `"They gave space"` | Enemy backing off unexpectedly |
| `"They're baiting"` | Enemy is using one player to draw attention while others flank |
| `"Mid control"` | Enemy has taken mid; likely to split to either site |
| `"Mid open"` / `"Mid is open"` | Mid is uncontested — either side can take it |

### 8c. Positioning Calls

| Call | Meaning |
|---|---|
| `"Close [direction]"` | Enemy within close range — `"Close left"`, `"Close right"` |
| `"Wide"` | Enemy is further out from the angle than expected |
| `"Off-angle"` | Enemy holding an unusual position (not the default hold) |
| `"Tucked"` / `"In the cubby"` | Enemy hiding in a tight corner/hidden spot |
| `"Heaven"` | Enemy on elevated platform (see per-map callouts) |
| `"Hell"` | Enemy in the position below Heaven |
| `"Deep site"` | Enemy is deep in the bomb site / back-site position |
| `"Back site"` | Enemy at the far side of site, away from entry |
| `"Front site"` | Enemy close to site entry |
| `"On the box"` | Enemy using a box as cover (common) |
| `"Boosted"` | Enemy player is crouching to boost another onto an elevation |

---

## 9. IGL / SHOTCALLING

### 9a. What an IGL Does

The In-Game Leader (IGL) is the player whose primary job is making strategic decisions in
real time. On organized teams, the IGL is one specific player; in ranked, any player can
assume the role.

**IGL responsibilities:**
- Call the round's opening strategy before it begins
- Adjust the plan mid-round based on information received
- Call rotations and commits
- Manage utility usage (who uses what, when)
- Maintain ultimate tracking (team and enemy)
- Set economic strategy in buy phase

**The IGL authority rule:** When the IGL calls something, teammates confirm and execute.
Arguing during a live round destroys timing and coordination. Save feedback for between
rounds.

### 9b. IGL Call Types

#### Pre-Round Calls (buy phase / round start)

| Call | Meaning |
|---|---|
| `"Default this round"` | Spread for info; no committed push; gather data |
| `"We're executing A/B"` | Full team execute onto a named site |
| `"Split A/B"` | Half team takes one approach, half takes another simultaneously |
| `"Fake A, hit B"` | Send noise/utility toward A, then full push B |
| `"Early mid control"` | Priority: contest mid before doing anything else |
| `"We're rushing [site]"` | All five fast-push the named site |
| `"Anti-strat [play]"` | Counter a known enemy tendency |
| `"Play on information"` | No preset; adapt to whatever contact is made |
| `"Slow play"` | Deliberate pacing; burn enemy utility before committing |
| `"Passive A, force B"` | One player holds A attention; full team commits B |
| `"Stack B"` | 3-4 players post at B; 1 lurks elsewhere |

#### Mid-Round Adjustments

| Call | Meaning |
|---|---|
| `"Commit [site]"` / `"Go now"` | Execute the site push immediately |
| `"Abort"` / `"Pull back"` | Cancel the execute; do not push |
| `"Reset"` | Pull back completely; regroup; start again |
| `"Late round"` | Don't force anything; delay and pick for time |
| `"Play for picks"` | Spread out; look for 1v1 duels rather than grouped pushes |
| `"Adjust to B"` | Originally going A — switch to B now |
| `"Send it"` / `"Go"` | Execute immediately without further delay |
| `"Wait for smoke"` | Hold the push until smoke is in place |
| `"One more"` | Wait for one more piece of info before committing |
| `"They're short"` | Enemy is down one player; push now |
| `"Take the trade"` | If one of us dies pushing, a teammate must immediately follow |
| `"Don't go"` | Specific cancel instruction to one player |

#### Post-Round Calls (brief, between rounds)

| Call | Meaning |
|---|---|
| `"Good round, same info next"` | Replicate the info-gathering; enemy pattern observed |
| `"They're stacking [site]"` | Enemies concentrated there; hit the other site |
| `"They rotated early"` | Defenders are rotating before confirmation; fake the rotate |
| `"Their [agent] is anchoring [site]"` | One specific agent is dedicated to holding |
| `"Watch for the lurk"` | Enemy lurker tendency identified |
| `"They're playing aggressive mid"` | Enemy contesting mid first |
| `"Save their ult patterns"` | Flag who on enemy team has ultimate charged |

### 9c. IGL Communication Style

**What makes a good IGL call:**
- Short (3–6 words maximum under pressure)
- Geographic (site + area, not individual player names)
- Confident (uncertainty is contagious)
- Timely (before the window closes, not during it)

**Bad IGL call:** `"I think maybe we should try going A but like let me know what you think,
should we flash the corner first though?"` — too long, uncertain, too late.

**Good IGL call:** `"Commit A on my smoke. Go."` — site, condition, trigger.

---

## 10. ROUND STRUCTURE AND ROLE VOCABULARY

### 10a. Attacker-Side Roles

| Role | Definition |
|---|---|
| **Entry fragger** | First player to push into site; takes the most risk; dies most often; enables the team |
| **Second entry** | Second player in behind entry; trades entry deaths; clears remaining angles |
| **Support** | Provides utility (flashes, smokes) for the entry players to use |
| **Lurker** | Solo player who delays, hangs back, or flanks; creates confusion and picks |
| **Anchor** (attack) | Player holding a taken angle while the rest of the team plants / consolidates |

### 10b. Defender-Side Roles

| Role | Definition |
|---|---|
| **Anchor** | Defender assigned to hold a specific site or chokepoint and stall as long as possible; does not rotate until necessary |
| **Rotator** | Defender assigned to move between sites; responds to contact and calls |
| **Flank watch** | Defender checking or holding against attacker flanks through the map |
| **Information agent** | Player (often Cypher, Sova, Fade) gathering intel without contesting directly |
| **Lurker** (defense) | Defender who waits near attacker spawn or mid to get a late pick and disrupt economy |

### 10c. Sub-Round Phases

| Phase | Description |
|---|---|
| **Buy phase** | 30 seconds before round; purchase weapons, armor, abilities |
| **Pre-round** | First 15–20 seconds; take opening positions, contest early picks |
| **Mid-round** | Information is flowing; IGL making adjustments |
| **Execute** | Committed push onto a site with utility support |
| **Post-plant** | After spike planted; defenders retaking, attackers holding |
| **Clutch** | 1 or 2 alive on one side vs. multiple enemies |
| **Eco phase** | Any round where one or both teams are on a save budget |

---

## 11. SPECIFIC TACTICAL PLAY CALLS

### 11a. Execution Calls

| Call | Meaning |
|---|---|
| `"Execute A"` / `"Full hit B"` | All five players commit to one site |
| `"Split execute"` | Team takes site from two different directions simultaneously |
| `"Contact execute"` | Execute only after spotting enemy commitment (not blind) |
| `"Fake execute"` | Use utility and noise as if executing one site; pivot to other |
| `"Flash execute"` | Flash blinds all angles before entry |
| `"Smoke and go"` | Plant smokes to block key angles, then push |
| `"Slow execute"` | Spread utility gradually; do not mass-push |
| `"Quick execute"` | Fast-pushing a site with minimal utility (speed advantage) |
| `"Eco execute"` | Rush one site on an eco round to win through surprise/numbers |

### 11b. Post-Execute Calls

| Call | Meaning |
|---|---|
| `"Spread out"` | Do not cluster; cover multiple angles on site |
| `"Clear site"` | Methodically check all angles before planting |
| `"One's unaccounted"` | Team killed 4, one enemy is not yet found |
| `"Watch for the flank"` | Enemy may come from behind after site is taken |
| `"They're retaking"` | Defenders are pushing back onto the site |
| `"Hold retake"` | Positioning to stop the retake; don't fight in the open |
| `"Let them retake, play around spike"` | Post-plant: don't fight, just protect spike angle |

### 11c. Defense Calls

| Call | Meaning |
|---|---|
| `"Fall back"` / `"Don't fight it"` | Cede map control; don't take unnecessary duels |
| `"Play passive"` | Hold angles; do not peek |
| `"Play aggressive"` | Push into the map early |
| `"Trade"` | Kill the person who just killed your teammate |
| `"Don't trade"` | Sometimes stated when intentionally baiting an opener |
| `"Play off [player]"` | Use a specific teammate's position as your setup |
| `"Play crossfire"` | Set up two players holding the same angle from different directions |
| `"Anchor [site]"` | One player stays at the site; others can rotate |
| `"Give up [area]"` | Deliberately cede that zone without fighting for it |
| `"Contest mid"` | Fight for mid control in the early round |

---

## 12. CLOCK / TIMING CALLS

Calling time prevents teams from holding too long or making reckless late-round pushes.

| Call | Meaning |
|---|---|
| `"30 seconds"` | 30 seconds left in the round |
| `"We have [X] seconds"` | General time update |
| `"Force it"` | Time is running out; must push now or lose on time |
| `"Plant quick"` | Time is critical; plant immediately |
| `"Don't have time to retake"` | Warning that spike timer is too low |
| `"They're burning time"` | Attackers deliberately delaying — watch for late rush |
| `"Spike at [X] seconds"` | Reporting how much time remains on planted spike |
| `"Let it go"` | 5 seconds or less on spike defuse — not worth dying for |

---

## 13. POST-ROUND VERBAL CALLOUTS

Short mandatory calls immediately after a round ends:

| Call | Timing | Meaning |
|---|---|---|
| `"Their ult status"` | After enemy deaths | Track who on enemy team has ultimate ready next round |
| `"How many ults on their side?"` | Buy phase | Quick tally before buying |
| `"I have ult"` / `"Ult ready"` | Buy phase | Communicate own ultimate status |
| `"GG round"` / `"NT"` | Immediately after | Keep morale up |
| `"No comms"` / `"Clean comms"` | Ongoing | Reminder to reduce chatter |

---

## 14. CLUTCH COMMUNICATION RULES

When the round is down to 1 or 2 players alive, the rules change:

**Dead players:** Go silent. Do NOT call callouts. Do NOT give advice. You cannot see
relevant current information. Noise from dead players causes fatal hesitation.

**Sole surviving player:** Call your own position and what you know; team should be quiet.

| Call | Meaning |
|---|---|
| `"I got this, no comms"` | Clutch player requesting silence to focus |
| `"Last one [location]"` | Dead players relay last known position before going silent |
| `"I see the spike"` | Clutch player confirming spike position (if it hasn't been called) |
| `"Play for spike"` | Reminder: win condition is defuse, not kills |
| `"Play for time"` | Buy time; spike detonation wins the round |

---

## 15. GENERAL VOICE COMM PRINCIPLES

### 15a. Brevity Rules

| Principle | Practice |
|---|---|
| 3–5 words maximum during active combat | `"Two B long"` not `"There are two of them on B long right now"` |
| Call, then stop | Give the info; do not narrate what you're thinking about it |
| Numbers first | Always count first — `"Three mid"` not `"Mid, three of them"` |
| Use map names | `"They're at Window"` not `"They're like in that room with the window thing"` |
| Negative info is valid | `"Nothing A"` is a callout — say it |

### 15b. Comm Discipline

| Rule | Why |
|---|---|
| No rage comms | Tilted teammates play worse; enemy audio is also intel |
| No redundant callouts | If someone called it, don't repeat it unless updating |
| No ability spam | Don't call the name of every ability as you buy it |
| No post-death advice | Dead players lack current info; advice is noise |
| Call when relevant | If it's not actionable, it probably doesn't need a call |

### 15c. Push-to-Talk vs. Open Mic

- **Push-to-talk (PTT)** is preferred at organized play — eliminates background noise from
  feeding enemy audio cues to your team
- **Open mic** is common in casual/ranked but risks broadcasting keyboard sounds, mouse
  clicks, and footsteps from other games to your team

---

## 16. UNIVERSAL MAP POSITION VOCABULARY

These terms apply on every map; learn them as the base layer:

| Term | Universal Meaning |
|---|---|
| **Site** / **Bomb site** | The plant zone (A, B, or C) |
| **Main** | Primary attacker entry corridor into the site lane |
| **Lobby** | Staging area before Main, connecting attacker spawn to site lane |
| **Heaven** | Elevated platform above the site or lane |
| **Hell** | Position directly beneath Heaven |
| **CT** / **CT side** / **CT Spawn** | Defender spawn side; paths originating there |
| **T side** / **T Spawn** | Attacker spawn side; paths originating there |
| **Mid** | The center lane connecting or separating the two sites |
| **Link** | A connector passage between two named areas |
| **Elbow** | An L-shaped secondary passage or corner on approach to site |
| **Long** | An elongated alley or path; typically sniper territory |
| **Short** | A shorter/faster path between attacker and defender sides |
| **Cubby** | A small alcove or recessed corner used for hiding or peeking |
| **Window** | A sightline cutout through a wall or structure |
| **Back site** | The far end of a bomb site, away from entry; deepest defender position |
| **Default** | The standard plant position at the center of a bomb site |
| **Garden** | Open outdoor or planted area adjacent to a site or lane |
| **Ramp** / **Stairs** | Elevation changes leading to a site or elevated platform |
| **Garage** | Enclosed parking/storage structure (appears on Haven) |
| **Vent** | A crawl-space or breakable passage connecting two areas |
| **Hookah** | Specific B-lobby feature on Bind; also generic: a hookah-style passage |
| **Catwalk** | Narrow elevated walkway across mid or above a site |
| **Pipe** / **Pipes** | Industrial pipe structures; also a position name on Icebox |

---

## 17. QUICK-REFERENCE GLOSSARY — COMM TERMS

| Term | Definition |
|---|---|
| **IGL** | In-Game Leader; the shotcaller |
| **Shotcall** | Any strategic directive from the IGL during a live round |
| **Callout** | Naming an enemy position |
| **Contact** | First moment of enemy sighting or engagement |
| **Trade** | Killing an enemy who just killed your teammate |
| **Baiting** | Letting teammate die without trading back |
| **Entry** | First player into a contested area |
| **Lurk** | Solo player who delays and flanks away from main action |
| **Anchor** | Player assigned to hold a fixed position |
| **Rotate** | Move from current position to another area of the map |
| **Retake** | Pushing back onto a site that defenders have ceded |
| **Stack** | Concentrating 3–5 players on one site |
| **Default** | A spread, non-committal round with information-gathering as the goal |
| **Execute** | A coordinated, committed push onto a site with utility support |
| **Fake** | Committing utility/noise toward one site, then attacking another |
| **Flank** | Attacking from behind or an unexpected side angle |
| **Rush** | All five players fast-pushing one target simultaneously |
| **Peek** | Briefly exposing oneself to gain information or take a shot |
| **Jiggle peek** | Rapid in-and-out peek to bait a shot without committing |
| **Shoulder peek** | Exposing only a shoulder sliver to bait a shot |
| **Dry peek** | Peeking without ability support |
| **Swing** | A wider, more committed peek; stepping fully out |
| **Wallbang** | Shooting through a penetrable wall to hit an enemy |
| **Pre-fire** | Shooting a location before the enemy is visible — anticipating position |
| **Counter-strafe** | Stopping movement momentum before shooting for accuracy |
| `ADS` | Aim Down Sights (right-click with rifles/pistols) |
| **Dink** | Headshot that does not kill — enemy is critically low |
| **One-shot** / **Lit** | Enemy has very low HP — one bodyshot will kill |
| **One-tap** | Single-shot kill; usually a headshot |
| **Eco** | Economy round; save/minimal spend |
| **Full buy** | Full loadout: rifle + heavy armor + all abilities |
| **Force** | Spending all available credits below full-buy threshold |
| **Half buy** | Mid-tier spend; SMG or cheap rifle |
| **Drop** | Buying a weapon for a teammate |
| **Ult** | Ultimate ability; also used as verb: "I ulted" |
| **Util** | Utility — agent abilities |
| **One-way smoke** | Smoke placed so your side can see through it, enemy cannot |
| **Lineup** | Specific throw position for a smoke, molly, or Sova bolt to land exactly |
| **Plant** | Placing the spike |
| **Post-plant** | Round phase after spike is planted |
| **Ninja defuse** | Defusing the spike undetected, past all attackers |
| **Fake defuse** | Starting defuse to bait an attacker into revealing position |
| **Save** | (1) Economy: don't buy. (2) Weapon: don't die; preserve expensive gun |
| **Exit frag** | Kill on an attacker fleeing after spike detonation |
| **Thrifty** | Winning a round while spending significantly fewer credits than the enemy |
| **Eco frag** | Killing a fully-bought player while on a budget round |
| **Eco kill** | Same as eco frag |
| **Glass cannon** | Using a high-damage weapon without shields |
| **CT** | Counter-Terrorist (CS:GO origin); means defender side or defender spawn in Valorant |
| **T side** | Terrorist side (CS:GO origin); means attacker side in Valorant |
| **Spawn** | Starting position each round (Attacker Spawn / Defender Spawn) |
| **Game sense** | Intuitive understanding of where enemies are based on sound, timing, and probability |
| **Peeker's advantage** | Network latency advantage for the aggressive peeker |
| **Angle advantage** | Holding from distance while enemy must close the gap |
| **Crossfire** | Two players covering the same angle from different directions |
| **Off-angle** | A position not typically held; surprises enemies expecting the default |
| **Flawless** | Round won with zero deaths on the winning team |
| **Ace** | One player gets all 5 kills in a round |
| **Team ace** | Each player gets one kill in the same round |
| **Clutch** | One or two players winning from a numbers-deficit situation |
| **Anchor (the site)** | Hold the site alone while teammates rotate elsewhere |
| **Play for time** | Delay rather than engage; spike detonation or clock wins the round |
| **Play slow** | Deliberate pace; extract utility from enemy before committing |
| **Scale** | Take space step-by-step, trading for map control |
| **Explode** | Fast-push layered with utility; all in |
| **Pinch** | Attack a position from two directions simultaneously |
| **Reset** | Disengage entirely; return to spawn; start fresh |
| **Absorb** | Let enemy use utility while you hold; drain their kit |
| **Anti-strat** | Counter-strategy targeting a known enemy habit |
| **ACS** | Average Combat Score: in-game performance metric (damage + multi-kills + assists) |
| **ADR** | Average Damage per Round |
| **RR** | Rank Rating — competitive rank progression points |
| **FF** | Forfeit — vote to end the match early |
| **OT** | Overtime |
| **GG** | Good Game |
| **NT** | Nice Try |
| **MB** | My Bad |
| **NS** | Nice Shot |
| **WP** | Well Played |
| **GH** | Good Half |
| **GLHF** | Good Luck Have Fun |
| **AFK** | Away From Keyboard |
| **Instalock** | Immediately locking an agent in agent select (often frowned upon as prevents team comp coordination) |
| **Smurf** | High-skill player on a lower-ranked account |
| **Tilt** | Emotional frustration state degrading play |

---

## 18. WEAPON VOICE-COMM ABBREVIATIONS

Full weapon names are used in buy-phase economy comms. In-round, players use short forms:

| Full Name | Common Call | Category | Price |
|---|---|---|---|
| Classic | `"Classic"` | Sidearm | Free |
| Shorty | `"Shorty"` | Sidearm | 300 |
| Frenzy | `"Frenzy"` | Sidearm | 450 |
| Ghost | `"Ghost"` | Sidearm | 500 |
| Bandit | `"Bandit"` | Sidearm | 600 |
| Sheriff | `"Sheriff"` | Sidearm | 800 |
| Stinger | `"Stinger"` | SMG | 1,100 |
| Spectre | `"Spectre"` | SMG | 1,600 |
| Bucky | `"Bucky"` | Shotgun | 850 |
| Judge | `"Judge"` | Shotgun | 1,850 |
| Bulldog | `"Bulldog"` | Rifle | 2,050 |
| Guardian | `"Guardian"` / `"Gua"` | Rifle | 2,250 |
| Phantom | `"Phantom"` | Rifle | 2,900 |
| Vandal | `"Vandal"` / `"AK"` | Rifle | 2,900 |
| Marshal | `"Marshal"` | Sniper | 950 |
| Outlaw | `"Outlaw"` | Sniper | 2,400 |
| Operator | `"Op"` / `"AWP"` | Sniper | 4,700 |
| Ares | `"Ares"` | LMG | 1,600 |
| Odin | `"Odin"` | LMG | 3,200 |

**Enemy weapon intel calls:**
```
"Jett has Op."                 → Operator confirmed on Jett
"They have rifles."            → Full-buy enemy team
"He's on a Sheriff."          → Eco player with Sheriff
"Drop the Op, don't feed it." → Warning: don't die with the Operator
```

---

## 19. COMPLETE AGENT ROSTER (2026, all 29 agents)

For voice-comm purposes when calling agent picks or ability intel.

### Duelists (8)
Jett, Phoenix, Raze, Reyna, Yoru, Neon, Iso, Waylay

### Controllers (7)
Brimstone, Viper, Omen, Astra, Harbor, Clove, Miks

### Initiators (7)
Sova, Breach, Skye, KAY/O, Fade, Gekko, Tejo

### Sentinels (7)
Cypher, Sage, Killjoy, Chamber, Deadlock, Vyse, Veto

**Agent intel calls (examples):**
```
"KAY/O used his knife."           → ZERO/POINT suppression active
"Sage walling B."                 → Barrier Orb blocking B entry
"Clove is ulting."               → Not Dead Yet activated — she may revive
"Jett dashed away."              → Tailwind used; repositioned
"Reyna dismissed."               → Dismiss used; she's temporarily invulnerable/repositioning
"Gekko Wingman's planting."      → Wingman handling plant so Gekko can fight
"Their Killjoy has Lockdown."    → Ultimate charged; expect Lockdown on site
```

---

## 20. MAPS — CURRENT STATUS (June 2026)

For corpus generation: note which maps are in competitive rotation vs. off.

**In competitive rotation (Act 3, from Patch 12.08, April 29 2026):**
Ascent, Breeze, Fracture, Haven, Lotus, Pearl, Split

**Out of competitive rotation (available in casual modes only):**
Abyss, Bind, Corrode, Icebox, Sunset

**All 12 maps that exist:**
Bind, Haven, Split, Ascent, Icebox, Breeze, Fracture, Pearl, Lotus, Sunset, Abyss, Corrode

For per-map callout positions, see:
- `map_ascent.md`, `map_bind.md`, `map_breeze.md`, `map_fracture.md`
- `map_haven.md`, `map_icebox.md`, `map_lotus.md`, `map_pearl.md`
- `map_split.md`, `map_sunset.md`, `maps_newest.md` (Abyss + Corrode)

---

## 21. RELAY-SPECIFIC COMM PATTERNS

These are the voice patterns the Ultron relay system will rephrase most often:

### 21a. Snap Callouts (verbatim / near-verbatim relay)

These are short, literal, time-critical — relay preserves them exactly:

```
"Two B."
"Spike A."
"One shot mid."
"Rotating."
"Planting."
"Defusing."
"Flash in."
"Rotating B."
"One lurking CT."
"He's 30 HP, no armor."
"Last one site."
```

### 21b. Off-Snap (extended relay — sent to LLM for Ultron rephrasing)

These are observations, opinions, strategy, economy reads, banter — richer content:

```
"We should stack B this round."
"Their Killjoy has ult, be careful."
"They're on eco, rush them."
"I think he's lurking through mid."
"Save this round, we need a full buy next."
"Let's fake A and hit B."
"They're stacking A every round, we should go B."
"He's always in that off-angle by the window."
```

---

## SOURCES

- oneesports.gg — Valorant terms and calls all players should know
- diamondlobby.com — Valorant in-game comms glossary
- gankster.gg — Effective communication and callouts: the teamplay guide
- boosteria.org — Valorant communication playbook; 40 ranked-winning callouts; map callouts guide 2026
- esportsdriven.com — Valorant terms dictionary; keys to IGLing
- vlr.gg — IGL tips; important things to understand as an IGL
- redbull.com — IGL in Valorant: tips for being a great in-game leader
- progameguides.com — All Valorant callouts for each map (Abyss)
- thespike.gg — VALORANT callouts guide
- gametree.me — Valorant terms, slang and lingo; economy guide
- thegamer.com — Valorant slang terms and calls explained
- blix.gg — Valorant voice communication tips
- vocal.media — Exploring the role of communication in Valorant
- dignitas.gg — Playing post-plant in Valorant: strategies and tips
- nerdaimers.com — Effective team communication in Valorant
- valohub.co — Agents list 2026 (complete agent roster with abilities)
- dotesports.com — All weapons in VALORANT; all character abilities
- hotspawn.com — All weapons in Valorant: full list, prices, and specs
- egamersworld.com — Valorant competitive map pool 2026
- gfuel.com — Valorant Season 26 Act 1 competitive map rotation
- bo3.gg — Valorant agent release timeline (2020–2026)
