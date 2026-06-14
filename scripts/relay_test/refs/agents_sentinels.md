# Valorant — Sentinel Agents Reference
## For Relay Test Corpus Generation

**Role summary:** Sentinels lock down sites, watch flanks, and provide persistent utility that forces enemies to react.
Current sentinel roster (7 agents): **Cypher, Sage, Killjoy, Chamber, Deadlock, Vyse, Veto**

---

## 1. CYPHER
**Role:** Intel / Surveillance sentinel. Moroccan. "The Moroccan information broker."
**Playstyle:** Camera + tripwires = full-map vision coverage; rotates after confirmed enemy position.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Trapwire | Basic | 200 creds | 2 |
| Q | Cyber Cage | Basic | 100 creds | 2 |
| E | Spycam | Signature | Free | 1 |
| X | Neural Theft | Ultimate | 7 pts | — |

#### Trapwire (C)
- Places a covert, destructible tripwire stretching between two walls at the targeted location.
- Enemy players crossing the wire are **Slowed** and **Revealed** (real-time silhouette) after a short delay if they don't destroy the device in time.
- Wire re-arms after 2 seconds; applies ~1.25s slow on initial contact.
- Can be **picked up and redeployed** (pickup cooldown applies).
- **HP:** 20. Destroyed by gunfire or certain abilities.
- **Comm callouts / slang:**
  - "Trip" — universal shorthand (e.g., "Trip on B Main," "Trip triggered B Main")
  - "Wire" — alternate shorthand
  - "Trip broken" — when enemy destroys the wire
  - "Trip hit" — enemy crossed and is slowed/revealed
  - "Trip up" — confirming wire is placed and active

#### Cyber Cage (Q)
- Instantly tosses a small disc; **activate** (reuse) to deploy a cylindrical vision-blocking zone that lasts **7 seconds**.
- Plays an **audio cue** when enemies walk through the active cage (even when not watching).
- Blocks LOS like a smoke; allies and enemies can walk through.
- Can be thrown to pre-set locations; activated reactively on cue or on demand.
- Can be **picked up** during buy phase.
- **Comm callouts / slang:**
  - "Cage" — standard name (e.g., "Caging B Main," "Dropping cage on entry")
  - "Smoke" — players sometimes use interchangeably (incorrect technically)
  - "Cage is up / down"

#### Spycam (E)
- Place a **camera** on any surface; RE-USE to take control of the camera's POV.
- While controlling: **FIRE** to shoot a **marking dart** that **Reveals** the struck player's location indefinitely until they remove it (shown on minimap + through walls).
- Dart cooldown: 2 seconds (can re-fire).
- Camera can be **destroyed** (enemy gunfire/abilities) — respawn cooldown: **45s**; pickup cooldown: **15s**.
- Immune to allied damage.
- **Comm callouts / slang:**
  - "Cam" — universal shorthand
  - "Cam sees [X] at [location]" — info callout
  - "Tagged [name/agent]" or "Marked" — dart landed
  - "Cam down" — camera destroyed
  - "Check cam" — asking Cypher to gather info

#### Neural Theft (X) — Ultimate: 7 points
- Instantly activate on a **dead enemy's body** within crosshair range.
- After a brief delay, **reveals all living enemy positions twice** (two waves, ~4 seconds apart).
- Works even if Cypher is the only survivor; provides global minimap/through-wall reveal.
- **Comm callouts / slang:**
  - "Ult" — generic
  - "Stealing" / "Pulling info" — describing the action
  - "Full reveal" — when communicating what the ult showed
  - "Ult them up" — asking Cypher to use it on a corpse

---

## 2. SAGE
**Role:** Support / Barrier sentinel. Chinese. "The stronghold of China, Sage creates a safer world for her allies and a more dangerous one for her enemies."
**Playstyle:** Wall blocks + slow orbs stall executes; healing sustains teammates; rez creates a 5v5 swing.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Barrier Orb | Basic | 400 creds | 1 |
| Q | Slow Orb | Basic | 200 creds | 2 |
| E | Healing Orb | Signature | Free | 1 (45s CD) |
| X | Resurrection | Ultimate | 7 pts | — |

#### Barrier Orb (C)
- Places a large **solid wall** of ice panels that fortifies after ~3.3 seconds.
- **Initial HP:** 400 per segment; **Fortified HP:** 800 per segment.
- **Duration:** 40 seconds before natural decay.
- ALT FIRE rotates the wall targeter (90° rotation).
- Can be used offensively (boost teammates), defensively (block chokepoint), or to cut site in half.
- **Comm callouts / slang:**
  - "Wall" — universal shorthand (e.g., "Wall B main," "Wall blocking heaven")
  - "Wall up" — confirming wall is placed
  - "Boost wall" — placed for teammates to climb
  - "Wall down" — wall destroyed or expired
  - "Break wall" — calling to destroy enemy Sage wall
  - "Block wall" / "Ice wall"

#### Slow Orb (Q)
- Throws a slowing orb that **detonates on landing**, creating a lingering slow field for **7 seconds**.
- Slows all players (allies and enemies) caught inside by 50%; also **reduces dash speed by 50%** (affects Jett, Neon).
- **Comm callouts / slang:**
  - "Slow" or "Slow orb" (e.g., "Slowing B entry," "Slow on plant")
  - "Orb" — generic shorthand
  - "Slowed" — status callout when enemy is in the field
  - "Slow down" — asking Sage to deploy slow

#### Healing Orb (E) — Signature (45s cooldown)
- FIRE with crosshairs on a damaged **ally** to activate a Heal-Over-Time (60 HP over 5 seconds to teammate).
- ALT FIRE on **self** when damaged (50 HP over 5 seconds self-heal).
- Cooldown starts after the heal completes.
- **Comm callouts / slang:**
  - "Heal me" / "Need heal"
  - "Healed" — confirmation from Sage
  - "Orb me" / "Orb"

#### Resurrection (X) — Ultimate: 7 points
- Channel briefly over a **dead ally's body** to bring them back at **full health** (100 HP).
- Ally briefly channels and stands up after a moment; both Sage and the target are vulnerable during channel.
- **Comm callouts / slang:**
  - "Rez" or "Res" — universal shorthand
  - "Rez me" / "Rez [name]"
  - "Rez incoming" — Sage announcing she's about to rez
  - "Save rez for [player]" — prioritizing who gets the ultimate
  - "Hold for rez" — asking team to wait while Sage rezzes

---

## 3. KILLJOY
**Role:** Autonomous-utility / Area-denial sentinel. German. "The German genius of gadgets."
**Playstyle:** Plant Nanoswarms around spike, recall Alarmbot to bait, Turret for free intel, Lockdown to clear or retake sites.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Nanoswarm | Basic | 200 creds | 2 |
| Q | Alarmbot | Basic | 200 creds | 1 |
| E | Turret | Signature | Free | 1 (45s CD after destruction) |
| X | Lockdown | Ultimate | 9 pts | — |

#### Nanoswarm (C)
- Throw a grenade; upon landing it goes **covert** (invisible until an enemy approaches within ~3.5m or it's activated).
- **ACTIVATE** (using ability key) to deploy a damaging swarm of nanobots.
- **Damage:** ~45 DPS (deals massive damage quickly at close range).
- Lasts ~4 seconds after activation.
- Placed covertly pre-round on defense; activated during bomb plant/post-plant.
- ALT FIRE = lob throw.
- **Comm callouts / slang:**
  - "Nano" — most common shorthand (e.g., "Nano on plant," "Nano B site")
  - "Molly" — extremely common (borrowed from CS:GO incendiary term; used interchangeably)
  - "Swarm" — less common
  - "KJ molly" — distinguishes from other mollies
  - "Nano up" / "Nano planted" — confirming placement
  - "Pop nano" / "Activate nano" — calling to trigger it

#### Alarmbot (Q)
- Deploy a covert **bot** that hunts down enemies entering its detection radius (~5m).
- When it reaches its target, it **explodes** applying **Vulnerable** status (doubled damage taken for 4 seconds).
- Stays hidden until enemies come within ~7m.
- **HOLD EQUIP** to recall a deployed bot.
- Pickup cooldown: 20 seconds.
- **Comm callouts / slang:**
  - "Bot" — standard shorthand (e.g., "Bot on flank," "Bot tagged him")
  - "Alarm bot" / "Alarmbot"
  - "Bot triggered" / "Bot going" — enemy in range
  - "Vulnerable" — status effect confirmation
  - "Bot's out" / "Bot up"
  - "Recall bot" — asking KJ to pick it back up

#### Turret (E) — Signature (Free; 45s CD after destruction)
- Deploy a **turret** that automatically fires at enemies within a **100-degree cone**.
- **HP:** 100. Destroyed by gunfire or abilities.
- **Damage:** 3–8 HP per shot (low damage, primarily for intel/distraction).
- HOLD EQUIP to recall (pickup cooldown: 20 seconds).
- Respawns naturally after 45 seconds if destroyed.
- **Comm callouts / slang:**
  - "Turret" — standard (e.g., "Turret is watching B main")
  - "KJ turret" / "KJ bot"
  - "Turret spotted [location]" — providing intel
  - "Turret down" — turret destroyed
  - "Shoot the turret" — calling to destroy enemy KJ turret
  - "Turret watching [angle]" — warning teammates

#### Lockdown (X) — Ultimate: 9 points
- Deploy a device; after a **13-second windup**, it **Detains all enemies caught in its radius** for **8 seconds**.
- Detained enemies cannot shoot, use abilities, or plant/defuse.
- Device has HP and **can be destroyed by enemies** during the windup.
- Massive radius — covers entire sites.
- **Comm callouts / slang:**
  - "Lockdown" — standard
  - "KJ ult" / "KJ locking down"
  - "Lockdown out" / "Lockdown going"
  - "Defend the lockdown" / "Protect the box" — asking teammates to guard the device
  - "Ult" — when status is relevant
  - "Detained" — when enemies are caught

---

## 4. CHAMBER
**Role:** Sharpshooter / Self-sufficient sentinel. French. "A well-dressed Sentinel who uses his custom arsenal to hold down the fort."
**Playstyle:** Aggressive off-angles with Headhunter pistol, Trademark for flanks, Rendezvous to escape, Tour de Force for op-like power.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Trademark | Basic | 200 creds | 1 |
| Q | Headhunter | Basic | 100 creds/bullet (8 max) | 1 |
| E | Rendezvous | Signature | Free | 1 (30s CD; 45s if destroyed) |
| X | Tour De Force | Ultimate | 8 pts | — |

#### Trademark (C)
- Place a **trap** on the ground that scans for enemies in range.
- When a visible enemy comes in range, trap counts down then **destabilizes the terrain**, creating a **lingering slow field** around the enemy.
- Redeployable (pick up and move).
- **Comm callouts / slang:**
  - "Trap" — most common shorthand (e.g., "Trap on B entry")
  - "Trademark" — formal name
  - "Chamber trap" / "Chamber tripwire" — distinguishing from Cypher
  - "Trap triggered" — enemy in range
  - "Slow up" — the field is deployed
  - "Trap down" — destroyed by enemy

#### Headhunter (Q)
- Equips a high-caliber **heavy pistol** with ADS (aim down sights).
- **Headshot damage:** 159 (one-tap kill), **Body:** 55, **Legs:** 46.
- **8 bullets max** per round; each bullet costs **100 credits individually** (buy as many as needed).
- ADS significantly tightens accuracy.
- **Comm callouts / slang:**
  - "Headhunter" / "HH" — formal
  - "Pistol" — most common shorthand
  - "Sheriff" — frequently misnamed (Headhunter is the Chamber-specific pistol; Sheriff is a standard buy)
  - "One-tap pistol" / "Chamber pistol"
  - "No gun, running HH" — economy context

#### Rendezvous (E) — Signature (Free; 30s CD; 45s if destroyed)
- Place **one teleport anchor** on the ground.
- While on the ground and **in range** of the anchor, REACTIVATE to **instantly teleport** to it.
- Anchor can be **picked up and redeployed**.
- If the anchor is destroyed by enemies, cooldown is 45 seconds.
- (Historical note: originally placed 2 anchors; reworked to 1 anchor in post-nerf patch.)
- **Comm callouts / slang:**
  - "TP" / "Teleport" — most common shorthand
  - "Rendezvous" — formal
  - "Anchor" — referring to the device
  - "TP back" — Chamber retreating via teleport
  - "TP down" / "Anchor destroyed" — enemy shot the anchor
  - "Chamber TP watch" — warning to watch for repositioning

#### Tour De Force (X) — Ultimate: 8 points
- Summons a **powerful custom sniper rifle** (5 bullets).
- Any **direct hit to the upper body or head kills instantly**.
- On kill: creates a **lingering slow field** at the kill location.
- Hitscan (like Operator); extremely high value for holding long sightlines.
- **Comm callouts / slang:**
  - "Tour de Force" / "TDF"
  - "Chamber ult" / "Op ult"
  - "Chamber has op" — describing the weapon
  - "Slow field on kill" — the area denial effect
  - "He's ulting" — Chamber activating Tour de Force

---

## 5. DEADLOCK
**Role:** Aggressive / Reactive sentinel. Norwegian. "A soldier who uses her nanowire technology to hold sites and capture enemies."
**Playstyle:** Sonic Sensors for early sound detection, Barrier Mesh to cut off escape routes, GravNet to force slow pushes, Annihilation to capture high-value targets.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Barrier Mesh | Basic | 300 creds | 1 |
| Q | Sonic Sensor | Basic | 200 creds | 2 |
| E | GravNet | Signature | Free | 1 (40s CD) |
| X | Annihilation | Ultimate | 7 pts | — |

#### Barrier Mesh (C)
- Throw a disc; upon landing generates **barriers from the origin point** blocking character movement.
- Creates a cross/plus-shaped nanowire barrier; does NOT block bullets or abilities (only bodies).
- **Initial HP:** 320 (side orbs) / 570 (center orb); **Fortified HP:** 700 (sides) / 1200 (center).
- Fortification time: **3 seconds**.
- Duration: **30 seconds**.
- **Comm callouts / slang:**
  - "Mesh" — most common shorthand
  - "Barrier" — alternate
  - "Deadlock wall" / "DL wall"
  - "Mesh up / down"
  - "Break the mesh" — calling to destroy it
  - "Wall" — sometimes used generically

#### Sonic Sensor (Q)
- Deploy a **sensor** that monitors an area for sounds (footsteps, gunfire, significant noise).
- When triggered: **concusses** the entire sensor area for **3.5 seconds**.
- Can be **picked up and redeployed** (20 HP; invisible until enemy approaches within ~3m).
- **Comm callouts / slang:**
  - "Sensor" — standard shorthand
  - "Sonic" — shorthand
  - "Sensor triggered [location]" — enemy detected
  - "Sensor going off" / "Sensor popped" — concussion deployed
  - "Trip" — sometimes used (similar flank-watch role to Cypher tripwire; can cause confusion)
  - "Sensor watching [angle]"

#### GravNet (E) — Signature (Free; 40s cooldown)
- Throw (or lob ALT FIRE) a grenade that detonates on landing.
- Forces any enemies caught within to **crouch** and move at **~30% of normal speed** (70% slow).
- Duration: **6 seconds**; radius: **6.5m**; windup: **0.4 seconds**.
- Extremely powerful against fast executes — essentially pins team in place.
- **Comm callouts / slang:**
  - "GravNet" / "Grav" — standard
  - "Net" — common shorthand
  - "Grav down" — grenade deployed
  - "Netted" / "Gravved" — enemies caught
  - "They're crouching" / "Pinned" — status callout for enemies caught in net

#### Annihilation (X) — Ultimate: 7 points
- Equips a Nanowire Accelerator; FIRE to launch a pulse of nanowires.
- **Captures the first enemy** contacted in a **cocoon** (600 HP).
- Cocooned enemy is **pulled along a predetermined nanowire path** toward a kill point.
- Enemy **dies if they reach the end**; cocoon can be **destroyed** by teammates to free them.
- Windup: 1.1 seconds; pull duration: **7 seconds**; total duration: **10 seconds**.
- **Comm callouts / slang:**
  - "Annihilation" — formal
  - "Deadlock ult" / "DL ult"
  - "Cocoon" — referring to the captured state
  - "Cocooned [player]" — target captured
  - "Break the cocoon" / "Free them" — asking allies to destroy the cocoon
  - "Pulled" / "Nanowire" — general descriptions

---

## 6. VYSE
**Role:** Terrain-manipulation / Trap sentinel. Origin uncertain (liquid-metal abilities, newer lore). "The metallic mastermind."
**Playstyle:** Pre-plant invisible Razorvines for post-plant defense, Shear to isolate flankers, Arc Rose for flashes, Steel Garden to jam primaries during retakes.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Razorvine | Basic | 150 creds | 2 |
| Q | Shear | Basic | 200 creds | 1 |
| E | Arc Rose | Signature | Free | 1 (20s CD) |
| X | Steel Garden | Ultimate | 8 pts | — |

#### Razorvine (C)
- Launch a nest of liquid metal that lands and **becomes invisible**.
- **ACTIVATE** (hold/reuse) to sprawl out into a large thorn nest that **slows and damages** all players who move through it.
- **Damage:** 10 per tick (per ~1.25m moved); **Slow:** 15%; also **slows dash abilities** (Jett, Neon).
- **Duration:** 7 seconds after activation; **HP:** 20; **Charges:** 2.
- **Cost:** 150 credits (cheapest sentinel utility).
- **Comm callouts / slang:**
  - "Razorvine" / "Razor" — formal and shorthand
  - "Vine" — very common shorthand
  - "Thorns" — descriptive
  - "Vine up" — confirming placement
  - "Activate vine" / "Pop vine" — calling to trigger it
  - "Vine on plant" — placed near spike
  - "Slowed" — status when enemies enter

#### Shear (Q)
- Place hidden filaments; when an enemy **crosses the trigger line**, an **indestructible wall** bursts from the ground **behind** them.
- The wall **isolates** the enemy from retreating (forces them forward or into the fight).
- Wall is **indestructible** but **temporary** (lasts **6 seconds**).
- Hidden; enemy cannot see the trap before triggering.
- **Comm callouts / slang:**
  - "Shear" — standard
  - "Wall trap" / "Trap wall"
  - "Vyse wall" — distinguishing from Sage/Deadlock
  - "Shear triggered" — enemy crossed
  - "Isolated" / "Cut off" — effect description
  - "Wall up [behind them]"

#### Arc Rose (E) — Signature (Free; 20s cooldown)
- Place a **stealthed Arc Rose** on any surface (FIRE: direct placement; ALT FIRE: place through surface).
- REUSE to **blind all players looking at it** (max ~2.25s blind, 0.45s windup delay).
- Can be **picked up and redeployed**.
- Acts as a one-time flash device; invisible until activated.
- **Comm callouts / slang:**
  - "Arc Rose" — formal
  - "Flash" — most common shorthand (same role as other one-way flashes)
  - "Rose" — shorthand
  - "Pop the rose" / "Arc" — calling to trigger
  - "Flashed" — confirmed blind status
  - "Arc is up / planted"
  - "Blind popped"

#### Steel Garden (X) — Ultimate: 8 points
- Vyse sends metal thorns erupting outward in a **wide area**.
- Enemies caught in the radius have their **primary weapons JAMMED** (cannot fire primary) for **8 seconds**.
- Affected enemies can still use pistols, abilities, and melee.
- Brief windup before the effect activates.
- Note: Does NOT affect Chamber's Tour de Force, Jett's Bladestorm, or Neon's Overdrive (weapon-like abilities).
- **Comm callouts / slang:**
  - "Steel Garden" — formal
  - "Garden" — shorthand
  - "Vyse ult" / "Jam ult"
  - "Jam" / "Jammed" — status callout (most important in comms)
  - "Primaries jammed" — status announcement
  - "Drop primaries" — what enemies must do when jammed
  - "They're jammed" — key communication for teammates to push

---

## 7. VETO
**Role:** Anti-utility / Mobile sentinel. Senegalese. "A Senegalese enforcer empowered by a Radivore DNA mutation."
**Playstyle:** Interceptor destroys enemy utility passively, Chokehold traps flankers, Crosscut for safe repositioning, Evolution for aggressive pushes under immunity.
**Released:** October 7, 2025 (Patch 11.08). 29th Agent in VALORANT Protocol.

### Abilities

| Key | Name | Type | Cost | Charges |
|-----|------|------|------|---------|
| C | Crosscut | Basic | 200 creds | 2 |
| Q | Chokehold | Basic | 200 creds | 1 |
| E | Interceptor | Signature | Free | 1 (40s CD) |
| X | Evolution | Ultimate | 7 pts | — |

#### Crosscut (C)
- Place a **vortex** on the ground; while in range and **facing the vortex**, REACTIVATE to **teleport** to it.
- Requires line of sight to the vortex to teleport.
- Has a slight delay (not instant like Chamber's old Rendezvous).
- During **buy phase**, vortex can be **reclaimed** and **redeployed**.
- **2 charges** per round.
- **Comm callouts / slang:**
  - "Crosscut" — formal
  - "TP" / "Teleport" — common shorthand
  - "Vortex" — referring to the device
  - "Veto TP" — distinguishing from Chamber
  - "TP back" — Veto repositioning via teleport
  - "Drop TP" — placing the vortex for later use

#### Chokehold (Q)
- Throw a viscous fragment that deploys on landing, creating a **trap zone**.
- Enemies entering the zone are: **tethered** (immobilized), **Deafened**, and **Decayed**.
- Enemies can **destroy the trap before it activates**.
- **Comm callouts / slang:**
  - "Chokehold" — formal
  - "Trap" / "Hold" — shorthand
  - "Veto trap" / "Tether"
  - "Choke" — shorthand
  - "Tethered" — enemy caught status
  - "Deafened" / "Decayed" — debuff callouts
  - "Trap triggered" / "Trap hit"

#### Interceptor (E) — Signature (Free; 40s CD; 20 HP)
- Place the **Interceptor** at a projected location; REUSE to **activate**.
- Once active: **destroys any enemy utility** that would bounce off a player or be destroyed naturally by gunfire.
- Duration: **10 seconds** when active; HP: **20** (destroyable by gunfire).
- Can counter: Raze grenades, Sage walls, Gekko utility, Sova bolts, and many more bouncing/destructible abilities.
- Cannot destroy all utility (e.g., Jett Bladestorm, Neon Overdrive, Chamber Headhunter/Tour de Force are unaffected).
- **Comm callouts / slang:**
  - "Interceptor" — formal
  - "Anti-util" / "Counter" — describing its function
  - "Blocker" / "Destroyer"
  - "Interceptor up / active"
  - "Utility destroyed" — effect confirmation
  - "Interceptor blocking [enemy ability]"
  - "Shoot the interceptor" — asking enemies to destroy it (from enemy POV)

#### Evolution (X) — Ultimate: 7 points
- Veto **instantly mutates**, gaining:
  - **Combat stim** (increased fire rate, reload speed)
  - **Regeneration**
  - **Immunity to all negative debuffs** (flashes, stuns, slows, concusses, decay, etc.)
- Lasts until **Veto dies**.
- Cannot block: Jett's Bladestorm damage, Neon's Overdrive, Chamber's Headhunter/Tour de Force.
- Excellent for aggressive pushes or holding under heavy ability pressure.
- **Comm callouts / slang:**
  - "Evolution" — formal
  - "Veto ult" / "Evo"
  - "Mutating" / "Evolved"
  - "He's immune" — key warning when Veto ults
  - "Ult active" / "He's ulted"
  - "Can't flash / stun him" — debuff immunity awareness

---

## Cross-Agent / Role Comm Terms (Sentinel-specific)

| Phrase | Meaning |
|--------|---------|
| "Util up" | Sentinel confirms abilities placed and active |
| "Util gone" | Key ability was destroyed or used |
| "Setup done" | Defensive configuration complete |
| "Flank watch" | Sentinel covering rear approach |
| "Nothing on flank" | No movement through monitored path |
| "Movement [location]" | Sensor/tripwire detected enemy |
| "Site clear" | No enemies detected in monitored area |
| "Recall util" | Requesting sentinel to pick up and move device |
| "Save ult" | Don't use ultimate this round |
| "Ult ready" | Sentinel ultimate is fully charged |
| "Anchor here" | Sentinel stays on site rather than rotating |
| "Retake" | Site lost; sentinel leads retake with utility |

---

## Ability Status Effects Quick-Reference

| Effect | Agents/Abilities | Comm Term |
|--------|-----------------|-----------|
| **Slow** | Sage Slow Orb, Chamber Trademark on-kill, Tour De Force on-kill | "Slowed" |
| **Revealed** | Cypher Trapwire, Spycam dart, Neural Theft | "Tagged," "Lit up," "Revealed" |
| **Detained** | Killjoy Lockdown | "Detained," "Can't move" |
| **Vulnerable** | Killjoy Alarmbot | "Vulnerable" / "Double damage" |
| **Crouch-forced / slow** | Deadlock GravNet | "Netted," "Pinned," "Crouched" |
| **Concussed** | Deadlock Sonic Sensor | "Concussed," "Sensor popped" |
| **Cocooned** | Deadlock Annihilation | "Cocooned," "Caught" |
| **Blinded** | Vyse Arc Rose | "Flashed," "Blinded" |
| **Slowed + damaged** | Vyse Razorvine | "Slowed," "In the vine" |
| **Isolated** | Vyse Shear | "Cut off," "Trapped" |
| **Jammed** | Vyse Steel Garden | "Jammed," "No primary" |
| **Tethered + Deafened + Decayed** | Veto Chokehold | "Tethered," "Held," "Can't hear" |
| **Immune** | Veto Evolution | "Immune," "He's evolved" |

---

## Sources
- Liquipedia VALORANT Wiki — Cypher, Sage, Chamber, Deadlock agent pages
- Valorant Fandom Wiki — ability pages (Trapwire, Neural Theft, Tour De Force, Lockdown, Steel Garden)
- Mobalytics VALORANT agent overviews
- MetaBot.GG agent guides (Cypher, Sage, Killjoy, Chamber, Deadlock, Vyse, Veto)
- pley.gg sentinel and agent guides (2026)
- GosuGamers / Hotspawn / Sheep Esports — Veto release coverage (October 2025)
- Boosting-Ground Valorant agent guides
- ONE Esports Valorant terminology guide
- Red Bull Valorant agent guides (Chamber, Vyse)
- VALORANT Patch Notes (6.03, 9.10, 11.08, 12.00+)
