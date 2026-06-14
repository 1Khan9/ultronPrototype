# Valorant — Controller Agents Reference

**Status:** Current as of June 2026 (includes Harbor Patch 11.10 rework + Patch 12.02 buffs)
**Role:** Controllers manipulate the battlefield with vision-blocking smokes, area-denial tools, and map-splitting utilities. The defining class mechanic is smoke/wall deployment to create safe zones for team pushes and isolate site areas.

**Current Controller Roster:** Brimstone · Viper · Omen · Astra · Harbor · Clove

---

## Status Effects — Quick Reference

All ability descriptions reference these official in-game status effects:

| Effect | Description |
|---|---|
| **Decay** | Temporarily reduces maximum HP (cannot kill; floors at 1 HP); HP restores after exposure ends |
| **Vulnerable** | Agent takes double damage from all sources for duration |
| **Nearsight** | Vision radius severely reduced — only a few meters visible; beyond is dark |
| **Concuss** | Slows movement, reduces fire rate, restricts ADS, blurs + grays vision, shakes crosshair, distorts audio |
| **Slow** | Reduces movement speed |
| **Deafen** | Audio severely dampened; minimap obscured |
| **Blind / Flash** | Vision replaced with opaque colored screen |
| **Paranoia** | Reduced vision + decoy audio + minimap obscured (Omen-specific debuff name) |
| **Reveal** | Silhouette exposed through terrain (tracked position) |
| **Combat Stim** | Buff: increased equip speed, fire rate, reload speed, recovery speed, movement speed |

---

## BRIMSTONE

**Full name:** Liam Byrne
**Origin:** United States
**Release:** April 7, 2020 (launch)
**Role archetype:** Anchor controller — longest-lasting smokes in the game, map-tablet deployment, fire-support execute tool, stim buffs.
**Pick rate tier:** C-tier competitive (straightforward but limited mobility)

### Abilities

---

#### C — Stim Beacon
**Type:** Basic ability
**Cost:** 200 credits
**Charges:** 1 (can buy 2 per round)
**In-game description:** "EQUIP a stim beacon. FIRE to toss the stim beacon in front of Brimstone. Upon landing, the stim beacon will create a field that grants players Combat Stim."
**Duration:** 12 seconds (beacon stays active on ground)
**Buff radius:** ~4m around beacon
**Effects applied (Combat Stim):**
- +10% fire rate
- +10% reload speed
- +10% equip speed
- +10% recovery speed
- +10% movement speed (approx.)
- Grants RapidFire: faster shooting cadence while inside
**Notes:**
- Affects **all players** in radius — allies AND enemies
- Deliberately placed at spike plant location or entry point of site push
- Enemies can also benefit if they walk into it (tactical risk)
- Visible as a circular blue field on the ground

**Callout terms:**
- "Stim" / "drop the stim" / "stim beacon down" / "pop the stim"
- "Stim up" (team callout before executing)
- "Stim on [location]" (placement callout)
- "Stand in the stim" / "stay in stim"
- Enemy use: "they're in our stim" / "watch the stim"

---

#### Q — Incendiary
**Type:** Basic ability
**Cost:** 250 credits
**Charges:** 1
**In-game description:** "EQUIP an incendiary grenade launcher. FIRE to launch a grenade that detonates as it comes to rest on the floor, creating a lingering fire zone that damages players."
**Duration:** 7–8 seconds (lingering fire zone)
**Damage:** ~60 HP/second (real damage, not decay)
**Bounce:** Grenade bounces off surfaces before detonating
**Notes:**
- Damages ALL players — allies and enemies
- Primary use: forcing enemies off spike / blocking defuse (post-plant)
- Secondary use: clearing corners / flushing positions pre-entry
- Grenade bounces once off walls, allowing lineup shots into tight spaces
- Commonly called "molly" (derived from Molotov)

**Callout terms:**
- "Molly" / "brim molly" / "Incendiary"
- "Drop a molly" / "molly [location]" / "molly spike"
- "Molly plant" (post-plant delay tactic)
- "Molly heaven" / "molly default" (location-specific)
- "Light them up" / "burn it down"
- "Clear with molly before entry"
- Enemy: "molly out" / "they molly'd spike" / "wait out the molly"

---

#### E — Sky Smoke *(Signature)*
**Type:** Signature ability
**Cost:** First use free per round; 100 credits per additional charge
**Charges:** 3 (up to 3 smokes per cast)
**In-game description:** "EQUIP a tactical map. FIRE to set locations where Brimstone's smoke clouds will land (up to 3). ALT FIRE to confirm, launching long-lasting smoke clouds."
**Smoke duration:** 19.25 seconds
**Smoke diameter:** ~10m
**Tablet range:** ~55m from Brimstone's position
**Cast mechanic:** Pulls up overhead map view; Brimstone is stationary while targeting
**Notes:**
- Longest smoke duration of all controllers
- Smokes deploy from sky with a visible streak trail (telegraphed)
- Up to 3 smokes per activation
- Brimstone is VULNERABLE while using the map tablet (1–2 second cast)
- Must be within tablet range to target locations
- Cannot smoke global positions like Omen/Astra
- Cannot see through own smokes (unlike Viper's Pit)
- Smokes are solid — no one-way options on flat ground without creative line-of-sight work

**Callout terms:**
- "Smokes" / "sky smokes" / "brim smokes"
- "Smoke A" / "smoke B" / "smoke C"
- "Three smokes" / "double smoke"
- "Smoke it up" / "smoke the site" / "pop smokes"
- "Smoke [location name]" (e.g., "smoke heaven," "smoke CT," "smoke elbow")
- "Smokes are up" / "smokes down"
- "Smokes fading" / "smokes almost gone" / "watch the timing"
- Enemy: "smokes going down" / "smoke incoming"

---

#### X — Orbital Strike *(Ultimate)*
**Type:** Ultimate ability
**Cost:** 8 ultimate points
**In-game description:** "EQUIP a tactical map. FIRE to launch a lingering orbital strike laser at the selected location, dealing high damage-over-time."
**Duration:** ~4 seconds (active damage)
**Cast time:** ~2 seconds delay before laser arrives
**Damage:** ~570 total damage (extremely high; laser ticks every 0.15s)
**Radius:** ~5m
**Notes:**
- Uses same map-tablet mechanic as Sky Smoke
- Massive area-denial — opponents cannot hold the zone
- Has a visible arrival sound + warning that it's incoming
- Classic use: post-plant area denial during defuse, flushing occupied corners
- Cannot be used inside a building if there is a ceiling (requires open sky line)
- Range limited by tablet range (~55m)
- Named "orbital" colloquially

**Callout terms:**
- "Orbital" / "Orbital Strike"
- "Orbital incoming" / "I'm dropping orbital"
- "Orbital on spike" / "orbital [location]"
- Enemy: "orbital out" / "they're orbitaling" / "wait out the orbital"
- "Orbital ready" (ult availability callout)

---

### Brimstone — Competitive Communication Summary

| Situation | Callout |
|---|---|
| Deploying smokes for site exec | "Smokes going up, execute on three" |
| Warning smokes expiring | "Smokes in five, re-smoke or push now" |
| Placing stim for execute | "Stim down at plant, stand in it" |
| Post-plant fire denial | "Molly on spike, hold it" |
| Ultimate clear | "Orbital down, don't push in" |
| Requesting smoke | "Need smoke on [location]" |

---

---

## VIPER

**Full name:** Sabine Callas
**Origin:** United States
**Release:** April 7, 2020 (launch)
**Role archetype:** Chemical controller — persistent toxic zones, fuel-managed walls and clouds, post-plant anchor, best solo controller on select maps (Icebox, Breeze, Pearl).
**Unique mechanic:** **Fuel system** — Poison Cloud and Toxic Screen consume a shared fuel gauge while active; fuel regenerates when deactivated.

### Core Mechanic — Fuel

- Fuel is a shared resource powering both Poison Cloud and Toxic Screen simultaneously
- Max fuel: 100 units
- Drain rate: ~8.33 units/sec per active ability (~4.16 units/sec each)
- When both abilities run at once: fuel depletes in ~6 seconds
- Regeneration: full recharge in 30 seconds when both deactivated
- Strategic play: toggle one or both off to regenerate, then reactivate
- **Viper's Pit does NOT consume fuel** — lasts indefinitely with Viper inside

### Status Effects Viper Applies

| Effect | Source | Notes |
|---|---|---|
| **Decay** | Poison Cloud, Toxic Screen, Viper's Pit | Initial -10 HP on entry; -10 HP/sec sustained; persists 1.5s after leaving; cannot kill |
| **Vulnerable** | Snakebite | 2x damage taken; lasts 2 seconds after leaving acid zone |
| **Nearsight** | Viper's Pit only | Vision severely reduced inside pit; Viper can see enemy outlines |
| **Reveal** | Viper's Pit — Viper sees enemies | Enemies inside pit are revealed with glowing outline to Viper |

### Abilities

---

#### C — Snakebite
**Type:** Basic ability
**Cost:** 300 credits
**Charges:** 1
**In-game description:** "EQUIP a chemical launcher. FIRE to launch a canister that shatters upon hitting the floor, creating a lingering chemical zone that deals damage and applies Vulnerable."
**Duration:** 6.5 seconds (zone active)
**Damage:** 12.5 HP/second (real damage, not decay)
**Debuff:** Vulnerable — doubles all incoming damage for 2 seconds after leaving zone
**Bounce:** Canister bounces off walls before shattering
**Notes:**
- Deals real damage (not reducible by Viper's damage reduction effects)
- Vulnerable debuff is critical: if you hit someone with a gun while they're Vulnerable, they take double damage
- Used for: post-plant spike denial, cornering enemies, baiting fights
- Powerful combo: Snakebite + team shooting = double-damage window

**Callout terms:**
- "Snake bite" / "snakebite" / "Viper molly" / "acid"
- "Molly [location]" (same slang as Brimstone incendiary)
- "They're vulnerable" / "vulnerable — shoot them" / "double damage"
- "Acid on spike" / "acid down"
- Enemy: "Viper molly out" / "wait the acid"

---

#### Q — Poison Cloud
**Type:** Basic ability
**Cost:** 200 credits
**Charges:** 1
**In-game description:** "EQUIP a gas emitter. FIRE to throw the emitter that perpetually remains throughout the round. ALT FIRE to lob. RE-USE the ability to create a toxic gas cloud that Decays opponents inside it. While the cloud is active, the emitter consumes fuel."
**Duration:** Active as long as fuel allows (12s max continuous); toggleable on/off all round
**Gas cloud diameter:** ~6m
**Decay:** -10 HP initial; -10 HP/sec sustained; 1.5s lingering after exit
**Minimum activation time:** 2 seconds per toggle
**Cooldown between toggles:** 5 seconds
**Notes:**
- Emitter placed once and stays on the ground for the entire round
- Can be picked up and redeployed by re-using ability (once only)
- Emitter survives into next round if Viper survives (does NOT persist between rounds by default)
- Toggleable: turn on for vision block + decay, turn off to conserve fuel
- One-way potential with precise placement

**Callout terms:**
- "Poison cloud" / "gas" / "cloud" / "smoke"
- "Toggle the cloud" / "turn it on" / "activate"
- "Cloud A / cloud B" (placement callout)
- "Smoke's up" / "cloud's up"
- Enemy: "Viper gas" / "Viper smoke" / "don't walk in the gas"
- "Emitter" (placement of the device itself)

---

#### E — Toxic Screen *(Signature)*
**Type:** Signature ability
**Cost:** Free (1 per round; no credit charge)
**Charges:** 1
**In-game description:** "EQUIP a gas emitter launcher that penetrates terrain. FIRE to deploy a long line of gas emitters that creates a tall wall of toxic gas when activated. While the wall is active, the emitters consume fuel."
**Wall height:** Very tall (effectively infinite upward in most use cases)
**Wall length:** Spans multiple emitters across a long distance
**Duration:** Active as long as fuel allows; toggleable on/off all round
**Decay:** Same as Poison Cloud — -10 HP initial; -10 HP/sec sustained
**Minimum activation time:** 2 seconds per toggle
**Cooldown between toggles:** 5 seconds
**Notes:**
- Deployed through terrain/walls — emitters spawn in a line determined by Viper's position and aim at cast time
- If Viper dies while Toxic Screen is active, it remains up for an additional 2 seconds before deactivating
- Divides maps into two sections; classic map-split tool
- Can be toggled to allow safe crossing by teammates, then re-activated to cut off rotation
- Critical: Viper must manage fuel between Toxic Screen and Poison Cloud carefully

**Callout terms:**
- "Wall" / "toxic screen" / "Viper wall" / "the wall"
- "Wall up" / "wall down" / "drop the wall"
- "Toggle the wall" / "turn on the wall" / "pop the wall"
- "Split with wall" / "wall splits A/B"
- "Wall crossing" (teammate using wall to cross safely)
- Enemy: "wall going down" / "she's toggling the wall"
- "Fuel low" / "out of fuel" (internal status callout)

---

#### X — Viper's Pit *(Ultimate)*
**Type:** Ultimate ability
**Cost:** 9 ultimate points
**In-game description:** "EQUIP a chemical sprayer. FIRE to spray a chemical cloud in all directions around Viper, creating a large cloud that Decays and Nearsights enemies inside."
**Radius:** Very large (covers most of a bomb site)
**Duration:** Indefinite while Viper remains inside; 8-second countdown timer if Viper exits
- After 8 seconds outside the pit: cloud dissipates
- If Viper returns within 8 seconds: timer resets, pit remains
**Effects on enemies:**
- **Decay:** Reduces HP toward 1 HP over time (cannot kill)
- **Nearsight:** Severely reduced vision radius inside the pit
- **Reveal:** Viper can see glowing outlines of all enemies inside her pit
**Effects on Viper:**
- Full vision inside own pit (Viper is NOT nearsighted inside it)
- Can reposition within pit freely
**Windup:** ~6 seconds for cloud to fully form
**Notes:**
- Ideal post-plant tool: Viper plants spike, activates pit, defenders must enter a decay+nearsight cloud to defuse
- Enemies at low HP die very quickly from Decay upon entry
- Counter: enemies can force Viper out of pit, triggering 8-second timer
- Strongest controller ultimate for post-plant scenarios
- "Setting up pit" = planting spike then activating ultimate
- Viper inside her own pit is at a massive information and health advantage

**Callout terms:**
- "Pit" / "Viper's Pit" / "viper pit"
- "Setting up pit" / "planting in pit" / "I'm going for pit"
- "Pit's up" / "pit's active"
- "In the pit" / "they're in the pit"
- "Out of pit" / "she left pit" (8-second timer starting)
- "Force her out of pit" / "bait her out" / "don't rush in"
- "Low in pit" / "don't rush, you'll die to decay"
- "Pit's gone" / "pit collapsed"
- Enemy: "Viper ulting" / "pit incoming"

---

### Viper — Competitive Communication Summary

| Situation | Callout |
|---|---|
| Activating wall for team push | "Wall up, cross now" |
| Warning fuel is low | "Fuel low, watch the wall" |
| Setting up post-plant pit | "Planting in pit, stay out" |
| Enemy forcing Viper out of pit | "She's out of pit, 8 seconds on cloud" |
| Snakebite Vulnerable window | "Acid — they're Vulnerable, shoot!" |
| Toggling for safe teammate cross | "Wall down, cross. Wall going back up." |

---

---

## OMEN

**Full name:** Unknown (classified)
**Origin:** Unknown
**Release:** April 7, 2020 (launch)
**Role archetype:** Shadow controller — globally-placed smokes, through-wall blind, short-range teleport repositioning, map-wide ultimate teleport. High mobility for a controller.
**Pick rate tier:** C-tier competitive (historically strong; still popular in ranked for mechanical flexibility)

### Abilities

---

#### C — Shrouded Step
**Type:** Basic ability
**Cost:** 100 credits
**Charges:** 2 per round
**In-game description:** "EQUIP a shrouded step ability and see its range indicator. FIRE to begin a brief channel, then teleport to the marked location."
**Range:** ~15 meters
**Cast time:** ~1 second channel before teleport (Omen is audible + stationery during channel)
**Notes:**
- Short-range repositioning tool — not instant, has a windup
- Audio cue is audible to nearby enemies (tells enemies he's moving)
- Classic use: teleport into own smoke, teleport to off-angle, cross dangerous sightlines silently
- Fake: cast it, cancel, to create positional confusion
- Cannot teleport through walls (unlike From the Shadows)
- The teleport audio plays at start position, not destination (some misdirection)

**Callout terms:**
- "Step" / "stepping" / "shrouded step"
- "Teleport" / "tele" / "TP"
- "Stepping into smoke" / "teleporting box"
- "Omen stepped" (tracking enemy Omen movement)
- "Fake step" (cancelled step used as mindgame)
- "Step [location]" (where he's teleporting)

---

#### Q — Paranoia
**Type:** Basic ability
**Cost:** 250 credits
**Charges:** 1 per round
**In-game description:** "EQUIP a blinding orb. FIRE to throw it forward, briefly Nearsighting and Deafening all players it touches."
**Debuff duration:** ~2.5 seconds of Nearsight + Deafen
**Projectile:** Travels in a straight line; passes **through walls**
**Notes:**
- Called "Paranoia" but applies Nearsight + Deafen (not the Paranoia status effect specifically — the ability name is Paranoia)
- Passes through ALL terrain — walls, floors, ceilings
- Hits both allies and enemies in its path
- Large hitbox — hard to dodge in corridors
- Typical use: throw through a wall to blind enemies holding an angle before Omen enters
- Can be used offensively (push) or defensively (delay a push)
- Projectile is visible — enemies can dodge laterally if aware

**Callout terms:**
- "Paranoia" / "para" / "blind"
- "Paranoia through [wall name]" / "para incoming"
- "Blind firing" / "we're going in, throw paranoia"
- "Through the wall" (to distinguish from a normal flash)
- Enemy: "Omen blind" / "paranoia out" / "I'm blind" / "got paranoia'd"
- "Para top" / "para long" (directional call before push)

---

#### E — Dark Cover *(Signature)*
**Type:** Signature ability
**Cost:** First 2 charges free per round; additional charges 150 credits; 30-second recharge cooldown
**Charges:** 2 (recharge over time)
**In-game description:** "EQUIP a shadow orb, entering a phased world to place and target the orbs. PRESS the ability key to throw the shadow orb to the marked location, creating a long-lasting shadow sphere that blocks vision."
**Smoke duration:** 15 seconds
**Placement mechanic:** Omen enters a translucent "phased view" of the map to target placement — can place through walls and at distances
**Range:** Global / near-global (can be placed anywhere on map with correct aiming)
**Notes:**
- Omen's smokes are darker than average — reduced visibility inside them (less light bleed)
- Can be placed through walls and at long range unlike Brimstone (no tablet range limit)
- Can be placed at different heights to create **one-way smokes** — orb placed just above ground level so Omen sees under the sphere; enemies walking in cannot see back
- Recharging smokes (30s cooldown) mean Omen can smoke multiple rounds without buying
- Smoke is a sphere, not a cylinder — shape matters for one-way setups
- 15-second duration is shorter than Brimstone (19.25s) but recycles faster

**Callout terms:**
- "Smoke" / "dark cover" / "dome" / "shadow"
- "Smoke A / B / C" / "smoke [location]"
- "One-way" / "one-way smoke" / "one-way [location]"
- "Smokes recharging" / "out of smokes" / "smokes cooling down"
- "Cover [location]" / "drop a smoke on [position]"
- "Dark cover incoming"
- Enemy: "watch the smoke" / "one-way — don't push" / "Omen smoked it"

---

#### X — From the Shadows *(Ultimate)*
**Type:** Ultimate ability
**Cost:** 7 ultimate points
**In-game description:** "EQUIP a tactical map. FIRE to begin teleporting to the selected location. While teleporting, Omen will appear as a Shade that can be destroyed by an enemy to cancel his teleport."
**Cast time:** 4 seconds (Omen travels as a Shade form during this window)
**Range:** Global — any location on the map
**Shade mechanics:**
- During teleport, a Shade (dark apparition) appears at destination
- Enemies can destroy the Shade to cancel the teleport and waste the ultimate
- Omen's original body stays at cast location (it is destroyed / disappears during travel)
- Omen can self-cancel mid-teleport by pressing the ability key again
**On successful teleport:** Omen appears at destination in a brief shadow burst
**Notes:**
- Global mobility: attack from unexpected angles, gather intel, flank
- High risk: Shade is visible to enemies and cancellable
- Intel use: deliberately telegraphing the ult to distract, then cancelling (risky mind game)
- Classic use: enemy is holding B, Omen ults to appear behind them at C
- "Shade" = the ghost/apparition that appears at destination during travel

**Callout terms:**
- "From the Shadows" / "ult" / "ulting"
- "Omen ulting [location]" (spotted shade)
- "Shade spotted" / "destroy the shade"
- "Teleporting to [site/location]"
- "They killed my shade" (ult cancelled)
- "Fake ult" (cancel after appearing to bait rotation)
- Enemy: "Omen ult [location]" / "shade on [position]" / "kill the shade"

---

### Omen — Competitive Communication Summary

| Situation | Callout |
|---|---|
| Requesting smoke placement | "Smoke heaven" / "dark cover short" |
| Setting up one-way | "One-way — hold the smoke, don't push" |
| Warning blind is coming | "Paranoia through [wall], push after" |
| Ulting for flank | "I'm ulting flank, wait for my call" |
| Shade spotted | "Omen shade at [location] — kill it" |
| Teleporting into smoke | "Stepping into B smoke, peek from there" |

---

---

## ASTRA

**Full name:** Efia Danso
**Origin:** Ghana
**Release:** March 2, 2021
**Role archetype:** Global controller — places Stars anywhere on the map, then remotely activates them as smokes, concusses, or gravity wells from Astral Form. Highest mechanical ceiling of any controller.
**Unique mechanic:** **Star system** — Astra enters Astral Form to place Stars, then activates them mid-round as any of three ability types.

### Core Mechanic — Star System

- **Astral Form:** Activate to enter a cosmic overhead view of the entire map; can place Stars with primary fire from anywhere on the map
- Stars charge for 1.4 seconds after round barriers drop before becoming activatable
- Stars cost **150 credits each** (purchased in buy phase or during Astral Form if credits available)
- Astra holds up to 5 Stars per round; Stars are spent when activated as an ability
- Stars can be Dissipated (recalled) to reposition; brief fake Nebula appears at the recalled location

### Status Effects Astra Applies

| Effect | Source | Notes |
|---|---|---|
| **Concuss** | Nova Pulse | 3.5-second duration; slows, reduces fire rate, blurs vision, distorts audio |
| **Vulnerable** | Gravity Well | Double damage taken; applied when pulled into center and explosion happens |
| **Vision block** | Nebula | Standard smoke — no damage or debuff |

### Abilities

---

#### C — Gravity Well
**Type:** Basic ability (consumes placed Star)
**Cost:** Requires a placed Star (Star cost: 150 credits)
**Cooldown after activation:** 60 seconds before the ability slot is usable again
**In-game description:** "ACTIVATE a Star to form a Gravity Well. Players in the area are pulled toward the center before it explodes, making all players still trapped inside Vulnerable."
**Pull duration:** ~2.4 seconds (players pulled to center)
**Explosion:** After pull, small explosion — players inside become Vulnerable
**Debuff:** Vulnerable (double damage) for players caught in explosion
**Range:** Global from Astral Form
**Notes:**
- Non-damaging itself, but the Vulnerable debuff + being out of position = extremely deadly
- Can interrupt pushes by yanking enemies out of cover
- Can deny defuse by pulling enemies off spike
- Affects all players — allies too (friendly fire potential)

**Callout terms:**
- "Gravity Well" / "grav" / "well" / "the pull" / "suck"
- "Activate grav" / "pop grav [location]"
- "Grav A / B" / "grav [spot]"
- "They're in grav — shoot them" / "Vulnerable — push"
- Enemy: "Astra grav" / "gravity pull" / "don't cluster, grav incoming"
- "Suck [location]" (common shorthand)

---

#### Q — Nova Pulse
**Type:** Basic ability (consumes placed Star)
**Cost:** Requires a placed Star (Star cost: 150 credits)
**Cooldown after activation:** 60 seconds
**In-game description:** "ACTIVATE a Star to detonate a Nova Pulse. The Nova Pulse charges briefly then strikes, Concussing all players in its area."
**Charge delay:** ~1 second before detonation
**Debuff duration:** ~3.5 seconds of Concuss
**Range:** Global from Astral Form
**Notes:**
- Creates a brief flash/charge visible to enemies (short warning before stun)
- Can be combo'd with other team utility — stun first, then teammates push
- Affects all players — allies too

**Callout terms:**
- "Nova Pulse" / "pulse" / "stun" / "concuss"
- "Pulse A" / "pulse [location]"
- "Pop the pulse" / "activate stun"
- "Stun incoming" / "pulse going off"
- Enemy: "Astra stun" / "concuss out" / "Astra [location]"
- "They're concussed — go"

---

#### E — Nebula / Dissipate *(Signature)*
**Type:** Basic ability (Nebula consumes Star; Dissipate recalls a Star)
**Cost:** Requires a placed Star for Nebula; Dissipate returns Star after 25-second delay
**Charges:** 2 Nebula uses per round; Dissipate usable on any unactivated Star
**Duration:** 14.25 seconds active smoke
**Cooldown:** 35 seconds (Nebula); 25 seconds (Dissipate)
**In-game description — Nebula:** "ACTIVATE a Star to transform it into a Nebula (smoke)."
**In-game description — Dissipate:** "USE a Star to Dissipate it, returning the Star to be placed in a new location after a delay. Dissipate briefly forms a fake Nebula at the Star's location before returning."
**Notes:**
- Nebula = smoke; primary vision-blocking tool
- Dissipate: the Star briefly fakes a smoke before returning to inventory, creating deception
- Use Dissipate to fake smokes and bait enemies into thinking a site is being smoked
- Stars must be pre-placed in Astral Form before round starts or mid-round in a safe window
- Global range — can smoke any location on the map

**Callout terms:**
- "Nebula" / "smoke" / "cloud"
- "Smoke [location]" / "Nebula A / B"
- "Dissipate" / "fake smoke" / "reset the star"
- "Fake [location]" (after dissipating to bait)
- "Stars are placed" / "stars are up"
- "Smoke's fading" / "nebula expiring"
- "Pulling the smoke back" (dissipate callout)
- Enemy: "Astra smoke" / "watch for the fake" / "Nebula incoming"

---

#### Passive — Stars / Astral Form
**In-game description:** "ACTIVATE to enter Astral Form where you can place Stars with PRIMARY FIRE and use ALT FIRE to begin aiming Cosmic Divide. Stars can be reactivated to transform them into a Nova Pulse, Nebula, or Gravity Well."
**Stars per round:** Up to 5
**Star cost:** 150 credits each
**Notes:**
- Stars must be placed from Astral Form (overhead cosmic map view)
- Astra is physically vulnerable while in Astral Form (not actually walking the map)
- Stars glow visibly to enemies — positions are somewhat revealed
- Stars can be destroyed by enemies before activation

**Callout terms:**
- "Entering astral" / "I'm in astral" / "placing stars"
- "Star [location]" / "I have a star on [location]"
- "Star's up at [location]"
- "Out of stars" / "no stars left"
- Enemy: "Astra star spotted" / "destroy the star"

---

#### X — Cosmic Divide *(Ultimate)*
**Type:** Ultimate ability
**Cost:** 7 ultimate points
**In-game description:** "When Cosmic Divide is charged, use ALT FIRE in Astral Form to begin aiming it, then FIRE to select two locations. An infinite Cosmic Divide connects the two points you select. Cosmic Divide blocks bullets and heavily dampens audio."
**Duration:** 21 seconds
**Wall properties:**
- Infinite height and depth — cannot be jumped over or tunneled under
- Blocks all bullets
- Blocks audio transmission across the divide (both teams cannot hear each other through it)
- Does NOT block most abilities (e.g., Sova Recon Bolt can pass through)
- Does NOT block some utility projectiles
**Notes:**
- Creates a map-splitting wall connecting two chosen points
- Called "Cosmic Divide" in-game; almost always called "divide" or "wall" casually
- Primary use: split a site, enable safe spike plant, deny rotation, block audio intel
- Must be activated from Astral Form
- Unlike Viper's wall, this blocks bullets entirely (Viper's wall doesn't block bullets, only vision)

**Callout terms:**
- "Cosmic Divide" / "divide" / "the wall" / "Astra wall"
- "Dividing [location]" / "wall's up at [line]"
- "Split A" / "divide the site"
- "Audio is blocked" / "no audio through the divide"
- "Wall incoming" / "divide coming down"
- Enemy: "Astra dividing" / "don't shoot the wall" / "go around the divide"
- "Divide fading" / "wall's almost gone"

---

### Astra — Competitive Communication Summary

| Situation | Callout |
|---|---|
| Entering Astral Form mid-round | "Going astral, cover me" |
| Activating smoke for team | "Smoking [location], push" |
| Fake smoke bait | "Faking smoke [location], watch their reaction" |
| Stun for entry | "Pulsing [location] in 3... push after" |
| Gravity well pull | "Grav [location], they're vulnerable — go" |
| Cosmic Divide for plant | "Dividing site, plant safe" |
| Requesting star placement | "Need a star at [location]" |

---

---

## HARBOR

**Full name:** Varun Batra
**Origin:** India
**Release:** October 18, 2022
**Role archetype:** Water-based aggressive controller — vision walls, deployable shielded smoke, area-denial/CC ultimate; reworked in Patch 11.10 to be more aggressive with Initiator elements.
**Rework:** Patch 11.10 (November 2025) — Cascade replaced by Storm Surge (new ability); Cove moved to signature slot; Reckoning redesigned. Further buffed in Patch 12.02.

### Status Effects Harbor Applies

| Effect | Source | Notes |
|---|---|---|
| **Slow** | High Tide, Storm Surge | 30% movement speed reduction |
| **Nearsight** | Storm Surge, Reckoning | Vision severely reduced |

### Abilities

---

#### C — Storm Surge *(Replaces Cascade as of Patch 11.10)*
**Type:** Basic ability
**Cost:** 200 credits
**Charges:** 1
**In-game description:** "FIRE to throw, creating an explosive whirlpool that Nearsights and Slows enemies within it after a short duration."
**Windup:** ~0.6 seconds after landing
**Debuff duration:** 2 seconds Nearsight + Slow
**Notes:**
- Thrown like a grenade; creates a whirlpool that detonates after a brief delay
- CC tool for aggressive plays — blind-and-slow an angle before entry
- Sound cue added (Patch 12.02) to confirm hits on enemies
- Replaces the older Cascade ability (rolling water wave, 30% slow, 2 charges, 150 credits)

**Callout terms:**
- "Storm Surge" / "surge" / "whirlpool"
- "Surge [location]" / "storm [location]"
- "They're nearsighted — push"
- Enemy: "Harbor storm" / "Harbor CC" / "I'm blinded"
- Note: Older players may say "cascade" out of habit (old ability name)

---

#### Q — High Tide
**Type:** Basic ability
**Cost:** 300 credits
**Charges:** 1
**In-game description:** "FIRE to send water forward along the ground. HOLD FIRE to guide the water towards your crosshair, spawning a vision-blocking Screen."
**Duration:** 15 seconds
**Width/height:** Very tall water wall; width determined by where Harbor guides it
**Slow:** 30% movement speed reduction to enemies who cross through
**Notes:**
- Guidable wall — Harbor holds fire and aims to curve the wall's path
- Slows enemies who cross (both directions)
- Creates a vision-blocking screen similar to Viper's Toxic Screen but water-based
- Can be curved around corners with careful guidance
- Post-Patch 12.02: wall height 8m (from 6m), wall length 60m (from 50m)

**Callout terms:**
- "High Tide" / "wall" / "water wall"
- "Wall up" / "drop the wall"
- "Tide on [location]" / "wall [site/lane]"
- Enemy: "Harbor wall" / "don't cross the wall" / "slow through the wall"

---

#### E — Cove *(Signature — moved from basic slot in Patch 11.10)*
**Type:** Signature ability
**Cost:** Free (first use); additional charges purchased
**Charges:** 1
**Cooldown:** 30 seconds
**In-game description:** "EQUIP Cove. ACTIVATE to form a water Smoke in the select location. HOLD FIRE while targeting to move the marker further away and HOLD ALT FIRE to move it closer. RELOAD to toggle targeting view. REACTIVATE to Shield the water Smoke, blocking any bullets that hit it."
**Smoke duration:** 19.25 seconds
**Shield HP:** 680 (Patch 12.02 buff; was 625, was 500 originally)
**Notes:**
- Placeable smoke (like Brimstone Sky Smoke) but with optional bullet-blocking shield toggle
- Two modes: normal smoke (blocks vision) OR shielded smoke (blocks bullets until shield depleted)
- Shield toggle = press ability key again after placing the smoke
- Unique: provides cover for spike plant by blocking bullets fired into it
- Classic use: throw Cove on spike plant point and shield it = planted freely

**Callout terms:**
- "Cove" / "water bubble" / "shield smoke" / "bubble"
- "Cove on spike" / "drop the cove" / "shield it"
- "Cove up" / "cove down"
- "Shield the cove" / "toggle shield"
- "Cove's shielded" / "breaking the shield" / "shield's gone"
- Enemy: "Harbor cove" / "shoot the bubble" / "break the shield"

---

#### X — Reckoning *(Ultimate — reworked in Patch 11.10)*
**Type:** Ultimate ability
**Cost:** 7 ultimate points
**In-game description:** "EQUIP Reckoning. FIRE to unleash the full power of your artifact, releasing a surge of water that barrels forward to Nearsight and Slow enemies that are hit."
**Windup:** ~0.7 seconds
**Duration:** 7 seconds (if stopped in place via reactivation — Patch 12.02 change)
**Debuff:** 3-second Nearsight + 2-second Slow on hit
**Notes:**
- Post-rework: Reckoning fires a forward-moving surge of water that nearsights and slows enemies in its path
- Patch 12.02 added ability to hold Reckoning in place for 7 seconds (reactivate to stop)
- Water moves 25% faster post-Patch 12.02
- Used for: pushing through a chokepoint, aggressive site take, clearing site angles
- Pre-rework Reckoning was a geyser field; now it's a forward wave

**Callout terms:**
- "Reckoning" / "ult" / "the wave" / "surge"
- "Reckoning push" / "wave incoming"
- "Ulting into [location]"
- Enemy: "Harbor ulting" / "water surge — move" / "nearsighted by Harbor"

---

### Harbor — Competitive Communication Summary

| Situation | Callout |
|---|---|
| Creating safe plant zone | "Cove on spike, shield it — plant" |
| Splitting a lane | "Wall [location], cross on my call" |
| Setting up CC entry | "Storm surge going in, push after nearsight" |
| Ultimate for forced push | "Reckoning — push through the wave" |

---

---

## CLOVE

**Full name:** Unknown (pronouns: they/them)
**Origin:** Scotland
**Release:** March 26, 2024
**Role archetype:** Aggressive controller / duelist-hybrid — only controller who benefits from kills, can smoke after death, and can self-revive. Designed to play like a duelist while filling the controller role.
**Pick rate:** A-tier ranked (14.1% pick rate, 53.4% win rate as of Act 3 2026); limited VCT pro representation due to self-oriented kit.

### Status Effects / Unique Mechanics

| Mechanic | Source | Notes |
|---|---|---|
| **Decay (applied)** | Meddle | Reduces max HP up to 90 HP for targets; Clove applies this to enemies |
| **Haste / Speed** | Pick-Me-Up | Brief movement speed boost on activation |
| **Overheal** | Pick-Me-Up | +50 HP overheal (temporary) |
| **Post-death smoke** | Ruse | Can deploy smokes after dying (limited post Patch 11.08) |
| **Self-revive** | Not Dead Yet | Unique: resurrects Clove after death with kill/assist condition |

### Abilities

---

#### C — Pick-Me-Up
**Type:** Basic ability
**Cost:** 200 credits
**Charges:** 1
**In-game description:** "ACTIVATE to absorb the life force of a fallen enemy that Clove damaged or killed, gaining haste and temporary health."
**Activation condition:** Clove must have damaged or killed the fallen enemy
**Windup:** 0.7 seconds
**Duration:** 10 seconds (overheal window)
**Effects:**
- +50 HP overheal (Patch 12.05 nerf from 100 HP)
- Brief movement speed boost (~+15%)
**Notes:**
- Must be manually activated — does NOT auto-trigger on kill
- Only works on enemies Clove damaged (not team kill passive)
- Enables aggressive back-to-back fights
- Overheal decays after 10 seconds
- Synergy with Not Dead Yet: Pick-Me-Up to survive longer, then potentially use ult if killed

**Callout terms:**
- "Pick-Me-Up" / "pick up" / "absorb" / "life steal"
- "I'm picking up" (activating ability)
- "Topped off" / "overhealed"
- No specific teammate-facing callouts (self-targeted)

---

#### Q — Meddle
**Type:** Basic ability
**Cost:** 250 credits
**Charges:** 1
**In-game description:** "EQUIP a fragment of immortality essence. FIRE to throw the fragment, which upon landing on the floor, erupts after a short delay and temporarily Decays all targets caught inside."
**Detonation delay:** 0.75 seconds after landing
**Duration:** 5 seconds (Decay zone active)
**Debuff:** Decay — reduces max HP by up to 90 HP
**Area of effect radius:** 4 meters (reduced from 6m in Patch 12.05)
**Notes:**
- At full decay, 100 HP enemy is effectively reduced to ~10 HP max (fatal with one shot in many scenarios)
- Requires line of sight for throw (thrown projectile, not through walls)
- Deadly combo: Meddle then shoot (or Meddle then teammate pushes)
- Not as strong post-AOE nerf (smaller radius)

**Callout terms:**
- "Meddle" / "decay" / "fragment"
- "Meddle [location]" / "throwing meddle"
- "They're decayed — burst them" / "low max HP, shoot"
- Enemy: "Clove decay" / "watch the fragment" / "I'm decayed"

---

#### E — Ruse *(Signature)*
**Type:** Signature ability
**Cost:** 150 credits (1 free charge per round; second charge 150 credits)
**Charges:** 2 per round
**In-game description:** "EQUIP to view the battlefield. FIRE to set the locations where Clove's clouds will settle. ALT FIRE to confirm, launching clouds that block vision in the chosen areas. Clove can use this ability after death."
**Duration:** 14 seconds (alive); **6 seconds (dead — nerfed Patch 12.05 from 12 seconds)**
**Cooldown:** 40 seconds
**Windup:** 1 second (overhead view; ALT FIRE to confirm)
**Post-death mechanic:**
- Can deploy **1 smoke** after dying (previously both charges; nerfed to 1 in Patch 11.08)
- 3-second post-death activation window
- Post-death smokes are shorter duration (6s instead of 14s as of Patch 12.05 nerf)
- Smokes deploy from overhead view similar to Brimstone and Omen
- Post-death smoke placement is restricted to near Clove's body
**Notes:**
- Unique defining mechanic: team's smoke coverage doesn't fully disappear on Clove's death
- Duration shorter than Brimstone (14s vs 19.25s) but more flexible placement
- Used to smoke after death to protect teammates retreating or to maintain plant-site smokes

**Callout terms:**
- "Ruse" / "smoke" / "Clove smokes"
- "Smoke [location]" / "smoking [site]"
- "Dead smoke" / "smoking from the grave" / "smoking after death"
- "I died, smoking [location]" / "smoke going up, I'm dead"
- Enemy: "Clove's dead, smokes still up" / "dead smokes — wait them out"
- "Smokes fading in 6" (post-death shorter duration)

---

#### X — Not Dead Yet *(Ultimate)*
**Type:** Ultimate ability
**Cost:** 8 ultimate points
**In-game description:** "After dying, ACTIVATE to resurrect. Once resurrected, Clove must earn a kill or a damaging assist within a set time or they will die."
**Activation:** Must be triggered after death (not pre-activated)
**Revive window (intangibility):** 2 seconds on resurrect
**Kill/assist requirement:** Must secure a kill or damaging assist within **10 seconds** of reviving
- Failure condition: automatically die if no kill/assist in 10 seconds
- Success: remain alive for the rest of the round at whatever HP Clove had before death
**HP on revive:** ~75-100 HP (returns close to values at death, or base health)
**Notes:**
- Unique mechanic: conditional self-revive
- Strong in clutch scenarios and for dueling aggressively without fear of permanent death
- Weak if resurrected in a bad position with enemies nearby
- Kills or assists from abilities count toward requirement (e.g., a Meddle assist works)
- Cannot re-activate if the 10-second timer runs out

**Callout terms:**
- "Not Dead Yet" / "NDY" / "ult" / "revive"
- "I'm ulting" / "coming back" / "reviving"
- "I need a kill — don't take them" (requesting one kill for ult sustain)
- "Ult ready" / "I have NDY"
- "I failed the ult" / "didn't get the kill, I'm dead"
- Enemy: "Clove ulted" / "she's reviving" / "kill Clove again" / "they're coming back"

---

### Clove — Competitive Communication Summary

| Situation | Callout |
|---|---|
| Deploying smoke | "Smoking [location], push after" |
| Activating post-death smoke | "I'm dead, smoking [location] — use it" |
| Starting ult self-revive | "Ulting — I need one kill" |
| Pick-Me-Up activation | "Picked up, overhealed, pushing" |
| Meddle decay window | "They're decayed — burst them now" |
| Warning ult is on cooldown | "No NDY yet, play safe" |

---

---

## CONTROLLER ROLE — CROSS-AGENT TERMINOLOGY

### Generic Terms (Apply Regardless of Controller Agent)

| Term | Meaning |
|---|---|
| **Smoke** | Any vision-blocking cloud deployed by a controller |
| **Wall** | A linear/extended smoke or barrier (Viper wall, Harbor wall, Astra Cosmic Divide) |
| **Molly** | Incendiary/damaging zone ability (Brimstone Incendiary, Viper Snakebite) |
| **Pit** | Viper's Pit specifically; also generic "area control" in context |
| **One-way smoke** | Smoke positioned so one team can see under/through it but the other cannot |
| **Smoke timing** | Coordinating when smokes are deployed relative to team pushes |
| **Re-smoke** | Replacing a smoke that has expired (Omen recharge, Astra Dissipate + replace) |
| **Pop smokes** | Deploy smokes for an execute |
| **Execute** | A coordinated site take with utility (smokes + flashes + molly) |
| **Post-plant** | After spike is planted; controller role is to delay/deny defuse |
| **Retake** | Recontesting site after enemies take it |
| **Anchor** | Player who stays on or near a site (controllers often anchor with Pit/wall) |
| **Split** | Dividing a site with a wall or divide (Viper wall, Astra Cosmic Divide) |
| **Star** | Astra-specific placed ability node |
| **Astral** | Astra's overhead Astral Form; "going astral" = entering that mode |
| **Divide** | Astra's Cosmic Divide ultimate |
| **Shield** | Harbor Cove in shielded mode |
| **Dead smokes** | Clove's Ruse used after death |
| **Fuel** | Viper's resource for Poison Cloud / Toxic Screen |

### Common Controller-Specific In-Game Request Phrases

- "Need smokes [location]" — requesting controller to cover a position
- "Smokes going up" — controller announcing incoming smokes
- "Smoke's almost gone" / "smoke in [X] seconds" — timing warning
- "Can you re-smoke [location]?" — asking controller to replace expired smoke
- "Wall up" — wall-type ability is being deployed
- "Blocking with Cosmic Divide" / "Dividing" — Astra wall up
- "Pop stim" — Brimstone Stim Beacon request
- "Molly the default" / "molly plant" — fire denial request
- "Set up pit" — Viper anchor post-plant instruction
- "Smoke [location] for the push" — coordinated execute preparation
- "I'm planting in the smoke" — attacker using controller smoke cover

---

## CONTROLLER AGENT COMPARISON — QUICK REFERENCE

| Agent | Smoke Type | Duration | Range | Unique Feature |
|---|---|---|---|---|
| **Brimstone** | Sky Smoke (up to 3) | 19.25s | Tablet range (~55m) | Stim Beacon, Incendiary (Molly), Orbital Strike |
| **Viper** | Poison Cloud + Toxic Screen | Fuel-limited (~12s) | Fixed positions (thrown/placed) | Fuel system, Decay debuff, Viper's Pit |
| **Omen** | Dark Cover (up to 2, recharge) | 15s | Global | One-way smokes, Paranoia through walls, global ult teleport |
| **Astra** | Nebula (Star-based) | 14.25s | Global | Star system, Gravity Well + Nova Pulse, Cosmic Divide |
| **Harbor** | Cove (smoke + shield) | 19.25s | Placeable | Shieldable smoke, High Tide wall, Storm Surge CC |
| **Clove** | Ruse (Brimstone-style) | 14s (6s dead) | Area map | Post-death smokes, Pick-Me-Up, Not Dead Yet self-revive |

---

## SOURCES

- Liquipedia VALORANT Wiki: [Brimstone](https://liquipedia.net/valorant/Brimstone), [Viper](https://liquipedia.net/valorant/Viper), [Omen](https://liquipedia.net/valorant/Omen)
- Official VALORANT Wiki: [wiki.playvalorant.com/en-us/Viper](https://wiki.playvalorant.com/en-us/Viper), [Omen](https://wiki.playvalorant.com/en-us/Omen), [Astra](https://wiki.playvalorant.com/en-us/Astra), [Harbor](https://wiki.playvalorant.com/en-us/Harbor), [Clove](https://wiki.playvalorant.com/en-us/Clove), [Status Effects](https://wiki.playvalorant.com/en-us/Status_Effect)
- Dexerto: [Valorant 11.10 Patch Notes — Harbor Rework](https://www.dexerto.com/valorant/valorant-11-10-patch-notes-finally-bring-harbor-rework-new-ability-3281898/)
- thespike.gg: [Clove Abilities](https://www.thespike.gg/valorant/agents/clove), [Harbor Abilities](https://www.thespike.gg/valorant/agents/harbor-s-abilities-in-valorant)
- hotspawn.com: [Viper Guide 2026](https://www.hotspawn.com/valorant/guide/viper-guide-how-to-play), [Omen Guide 2026](https://www.hotspawn.com/valorant/guide/omen-guide-how-to-play), [Clove Guide 2026](https://www.hotspawn.com/valorant/guide/clove-guide-how-to-play)
- pley.gg: [Harbor Rework Breakdown](https://pley.gg/valorant/harbor-rework-in-valorant-full-breakdown/), [Astra 2026](https://pley.gg/valorant/astra/)
- dotesports.com: [Astra Abilities](https://dotesports.com/valorant/news/all-astra-abilities-valorant)
- Official Patch Notes: [Patch 11.10](https://playvalorant.com/en-gb/news/game-updates/valorant-patch-notes-11-10/)
