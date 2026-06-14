# Valorant — Initiators: Ability & Callout Reference

> **Scope:** Ground-truth reference for relay-speech corpus generation.
> Covers all 7 Initiator agents as of patch 12.x (2026).
> Every ability name is the exact in-game string. Callout/comm terms reflect
> competitive usage — what players actually say mid-round.
>
> **Initiator roster (7):** Sova · Breach · Skye · KAY/O · Fade · Gekko · Tejo

---

## 1. SOVA

**Role:** Initiator | **Origin:** Russia
**Archetype:** Long-range recon; arrow-based information; poke/clear damage.
Heavily map-knowledge dependent — lineups for Recon Bolt and Shock Bolt are site-specific.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **Owl Drone** | 400 cr | 1 | 7 s fuel; drone HP ~40; fires a **marking dart** |
| Q | **Shock Bolt** | 150 cr | 2 | 1–75 dmg; detonates on collision; up to **2 bounces** via alt-fire |
| E (sig) | **Recon Bolt** | Free | 1 | 40 s cooldown; 5 s duration; **2 scans** (1 s apart); destroyable |
| X (ult) | **Hunter's Fury** | 8 pts | — | 3 charges; 80 dmg/blast; wall-piercing; reveals hit enemies |

### Ability Detail

**Owl Drone (C)**
- Deploy and pilot a drone; free-look from drone's POV.
- Alt-fire while controlling: launch a **marking dart** that sticks to and reveals the struck enemy's position to all teammates.
- Drone is destroyable. One-shot by a rifle hit.
- Drone emits a distinctive buzzing audio cue — enemies can hear it.

**Shock Bolt (Q)**
- Explosive arrow; detonates on first surface hit (or after max range).
- **Bounce mechanic:** Hold alt-fire to add 1 or 2 bounces before release.
- **Charge mechanic:** Hold primary fire to increase power (range/speed) — 4 distinct charge levels readable on the HUD.
- Ideal for double-Shock lineups to near-lethal a defuser or force off a corner.
- Deals 1–75 dmg depending on proximity; center is near-lethal.

**Recon Bolt (E — Signature)**
- Fires a sonar arrow; bounces possible (same mechanic as Shock Bolt).
- On impact, pings twice (1 s interval), revealing all enemies in LoS within a ~50 m radius via wall-hack outlines visible to the whole team.
- Enemies can **destroy** it (1 HP) — they will shoot it immediately.
- The scan makes a distinctive "ping" sound; enemies know they've been spotted.
- **Key call:** announce how many enemies were revealed ("recon hit two").

**Hunter's Fury (X — Ultimate)**
- Three sequential wall-piercing energy beams fired in a horizontal line from Sova's position.
- Each blast: 80 damage, traverses the full map, reveals enemies struck.
- 6.5 s window to fire all three.
- Can be fired in rapid succession or spaced out.
- Visually telegraphed — a red beam appears; enemies can dodge if not in a narrow corridor.

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **dart / recon / arrow** | Generic for Recon Bolt |
| **drone** | Owl Drone |
| **marking dart** | The dart fired FROM the drone |
| **shock dart / shock** | Shock Bolt |
| **fury / ult** | Hunter's Fury |
| **one bounce / two bounce** | Bounce count on Shock or Recon Bolt |
| **full charge / two-bar** | Power level for lineup |
| **recon up** | Recon Bolt in flight / active |
| **recon hit [N]** | N enemies scanned / revealed |
| **drone him** | Tag an enemy with the marking dart from Owl Drone |
| **double shock** | Two Shock Bolts on same spot (kill-setup) |
| **lineup** | A memorized trajectory for Shock/Recon off-angle |
| **destroy the dart** | Instruction to shoot the Recon Bolt to deny info |

---

## 2. BREACH

**Role:** Initiator | **Origin:** Sweden
**Archetype:** Through-wall initiator; daze/concuss team enabler; requires spatial awareness of enemy positions relative to walls and geometry.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **Aftershock** | 200 cr | 1 | 80 dmg × 2 ticks = 160 total; blast radius 300 cm |
| Q | **Flashpoint** | 250 cr | 2 | 2 s max blind; 0.5 s windup; fires through wall |
| E (sig) | **Fault Line** | Free | 1 | 35 s cooldown; 3.5 s daze; 7.5 m wide, up to 55 m long |
| X (ult) | **Rolling Thunder** | 9 pts | — | 6 s concuss; 25 m wide, 30 m long cone; knocks up |

### Ability Detail

**Aftershock (C)**
- Sets a slow fusion charge through a wall/floor/ceiling.
- Two damage ticks after a short delay — designed to force enemies off post-plant defuse positions.
- Cannot self-damage. Team-safe through-wall delivery.
- Primarily used to clear tight one-way corners or deny spike defuse.

**Flashpoint (Q)**
- A flash burst fires through the contacted surface.
- **Left-click:** 1.6 s cook — gives enemies more time to look away.
- **Right-click:** 1.0 s cook — fast flash, less warning.
- Full blind = 2 s; does NOT self-blind.
- Can flash from complete safety — fire into a wall on the same side as the enemy.
- **Friendly fire:** blinds allies too — communicate before throwing.

**Fault Line (E — Signature)**
- Hold fire to increase the length of the seismic wave (up to 55 m).
- Release to trigger: ground shockwave travels in a straight line.
- Enemies in the wave zone are **dazed** (concussed) — blurred vision, reduced accuracy.
- 3.5 s daze. Travels through walls. Team can also be dazed.

**Rolling Thunder (X — Ultimate)**
- Fires a cascading quake in a wide forward cone.
- Enemies hit are **concussed for 6 s** and knocked airborne.
- Covers a large area — strong for clearing sites, post-plant.
- Extremely powerful combined with smokes and team entry.

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **flash / flashpoint** | Flashpoint ability |
| **hard flash / fast flash** | Right-click (fast cook) |
| **soft flash / slow flash** | Left-click (slow cook) |
| **daze / stun / concuss** | Effect from Fault Line or Rolling Thunder |
| **fault / fault line** | Fault Line signature |
| **aftershock / shock** | Aftershock ability |
| **thunder / rolling / ult** | Rolling Thunder |
| **through the wall** | Characteristic of Breach's kit generally |
| **close your eyes** | Alert: Flashpoint incoming, look away |
| **flashing [location]** | Flashpoint aimed at a callout |
| **stunning [location]** | Fault Line aimed at a callout |
| **ulting / ult out** | Rolling Thunder initiated |

---

## 3. SKYE

**Role:** Initiator | **Origin:** Australia
**Archetype:** Animal-companion initiator; self-limited healing support; aggressive flashes and scouts; the only Initiator with a healing ability.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **Regrowth** | 150 cr | 1 | Channelled; heals allies in LoS; depleting pool; no self-heal |
| Q | **Trailblazer** | 300 cr | 1 | Tasmanian tiger; 80 HP; 6.5 s; concuss 4 s on leap |
| E (sig) | **Guiding Light** | 250 cr | 2 | Hawk; guided flash; 2 charges/round |
| X (ult) | **Seekers** | 8 pts | — | 3 seekers; 120 HP each; nearsight on hit |

### Ability Detail

**Regrowth (C)**
- Hold fire to channel a heal that radiates to all allies within range and LoS.
- Uses a shared healing pool (finite per purchase). Cannot heal self.
- Does not heal above 100 HP — cannot overheal to armor equivalent.
- Channelling is interruptible and noisy.

**Trailblazer (Q)**
- Throws a trinket that transforms into a controllable Tasmanian tiger.
- Player controls the tiger directly (FPV piloting, similar to Sova's drone).
- 80 HP — one rifle shot destroys it.
- **Fire while controlling:** tiger leaps forward in a short dash, explodes in a concussive blast on impact (4 s concuss).
- Vision range 15 m. Audio cue alerts enemies.

**Guiding Light (E — Signature)**
- Throws a hawk that flies forward; player can guide its path by holding fire.
- **Re-use key while hawk is in flight** → hawk detonates into a bright flash.
- If not detonated, hawk auto-flashes at end of flight path.
- Flash can self-blind Skye. Duration: up to 2.5 s depending on proximity.
- Two charges per round — exceptional flash volume.
- The hawk makes an audio cue; enemies can look away if they hear it in time.

**Seekers (X — Ultimate)**
- Releases three homing seekers that track the three nearest enemies.
- Each seeker has 120 HP — can be shot down.
- On contact with an enemy: applies **nearsight** (severe vision reduction for ~3 s).
- Seekers can be steered slightly but home automatically.
- Post-patch: seekers also slow dashes (partially counter Jett/Neon dashes).
- Skye's voice callout identifies how many enemies were targeted.

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **hawk / bird** | Guiding Light |
| **flash / flashing** | Guiding Light detonated as a flash |
| **tiger / dog** | Trailblazer (community uses both) |
| **seeking / seekers** | Seekers ultimate |
| **heal / healing up** | Regrowth in use |
| **concuss / stunned** | Effect from Trailblazer leap |
| **nearsighted** | Effect from Seekers |
| **popped / burst the hawk** | Manually detonated Guiding Light |
| **auto flash** | Guiding Light reached end of path and self-detonated |
| **seeker hit [N]** | N enemies nearsighted |
| **close your eyes** | Warning before Guiding Light flash |

---

## 4. KAY/O

**Role:** Initiator | **Origin:** Earth (future timeline, robot)
**Archetype:** Ability-suppression machine; anti-ability initiator; enables team to fight through suppressed utility; unique revive mechanic on ult.

> **Name note:** In-game styled as **KAY/O** (with slash, all caps). Fandom wiki
> and official sources: `KAYO`. Common community shorthand: **Kayo**.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **FRAG/ment** | 200 cr | 1 | Sticks to floor; 4 s; multiple explosions; 65–80+ dmg/tick center |
| Q | **FLASH/drive** | 250 cr | 2 | 2.25 s max blind; left-click 1.6 s fuse, right-click 1.0 s fuse |
| E (sig) | **ZERO/point** | Free | 1 | 40 s cooldown; 30 m sphere (diameter); 8 s suppress |
| X (ult) | **NULL/cmd** | 7 pts | — | 15 s; pulses every 3 s; suppresses all enemies in range; KAY/O becomes revivable if downed |

### Ability Detail

**FRAG/ment (C)**
- Thrown like a grenade; sticks to the floor on landing.
- Explodes in multiple pulses over ~4 s — like Viper's Molotov crossed with a burst.
- Near-lethal at center per tick. Effective for denying defuse, clearing corners.
- Cannot bounce/roll — sticks immediately on first floor contact.
- Diameter: ~8 m.

**FLASH/drive (Q)**
- Standard flash grenade; does NOT go through walls (unlike Breach Flashpoint).
- **Left-click:** ~1.6 s cook — throw then explode; good for over-the-shoulder corner flashes.
- **Right-click:** ~1.0 s cook — pop flash for aggressive peeks.
- 2.25 s max blind. Self-blinds.
- Shares flash behavior with classic grenades — can be bounced off walls.

**ZERO/point (E — Signature)**
- Throws a suppression blade that sticks to the first surface hit.
- After a short windup, explodes and emits a terrain-piercing suppression pulse.
- **Suppression:** enemies within the 30 m sphere diameter cannot use any abilities for **8 s**.
- Suppressed players' HUD shows their abilities are locked out. Teammates can see who got suppressed.
- The blade itself can be destroyed (shoot it before it explodes to deny suppression).
- Primary tactic: throw onto site or choke point before entry to strip all utility.

**NULL/cmd (X — Ultimate)**
- KAY/O instantly overloads and begins pulsing suppression waves.
- **15 s duration**; pulses suppress nearby enemies **every 3 s**.
- During NULL/cmd, KAY/O gains a **combat stim** (movement speed boost).
- If KAY/O is killed while NULL/cmd is active, he enters a **downed state** (not dead) — teammates can revive him with a 1.5 s interact at his body.
- Revived KAY/O returns with partial HP (30 HP).

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **knife / blade** | ZERO/point suppression blade |
| **suppress / suppressed** | ZERO/point or NULL/cmd effect applied |
| **suppressed [agent name]** | Specific enemy suppressed |
| **flash / kayo flash** | FLASH/drive |
| **pop flash** | Right-click fast-cook FLASH/drive |
| **frag / molly / fragment** | FRAG/ment ability |
| **ult / overload / null** | NULL/cmd |
| **he's down / revive kayo** | KAY/O downed during NULL/cmd |
| **knife hit [N]** | N enemies suppressed by ZERO/point |
| **abilities gone** | Enemies suppressed, enter site now |
| **destroy the knife** | Enemy instruction to shoot ZERO/point blade |

---

## 5. FADE

**Role:** Initiator | **Origin:** Turkey
**Archetype:** Terror-trail tracker; nightmare-based reveal, deafen, decay; synergy between abilities (Nightfall trails amplify Prowler speed); information warfare.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **Prowler** | 250 cr | 2 | 100 HP; travels forward, chases enemies; nearsight 2.75 s; search 2.5 s |
| Q | **Seize** | 200 cr | 1 | 14 m diameter; 4.5 s hold; deafened + decay (−75 HP over 5 s) |
| E (sig) | **Haunt** | Free | 1 | 40 s cooldown; 1 HP (destroyable); 2 s reveal + 12 s terror trail |
| X (ult) | **Nightfall** | 8 pts | — | Wave forward; deafen + decay + 12 s terror trail; Fade receives count of enemies hit |

### Ability Detail

**Prowler (C)**
- Throw orb that becomes a small creature travelling in a straight line.
- **Steer:** Hold primary fire during flight to guide toward crosshair.
- Chases enemies it detects within 15 m (10 m if following a terror trail).
- On contact: **nearsight for 2.75 s**.
- 100 HP — can be shot down.
- When enemies are marked with Nightfall trails, Prowlers lock onto trails and accelerate, making them near-impossible to avoid.

**Seize (Q)**
- Thrown projectile that drops and detonates at ground level after 1.5 s air time.
- Creates an area that **tethers** enemies inside: they cannot move out of the zone.
- Applies **deafen** (muffled audio) and **decay** (−75 HP over 5 s, cannot kill).
- Tether duration: 4.5 s.
- Destroyable (enemies can shoot it).
- Main use: trap a defender in a corner or deny spike defuse movement.

**Haunt (E — Signature)**
- Thrown orb that falls to the ground and summons a nightmarish floating eye.
- The eye **reveals** all enemies in its LoS for 2 s.
- After the reveal, a **terror trail** persists on each revealed enemy for 12 s — a dark ground trail tracking their movement.
- The eye itself has 1 HP — immediately destroyed if shot.
- Enemies that see the eye glow know they've been revealed and will try to shoot it.

**Nightfall (X — Ultimate)**
- Releases a wide forward wave of nightmare energy.
- Enemies hit receive: **deafen**, **decay** (HP drain), and a **terror trail** (12 s).
- Fade receives a voice/HUD callout indicating how many enemies were hit by the wave.
- The wave passes through walls.
- Terror trails + Prowlers = combo: Prowlers rocket toward trailed enemies.

### Status Effect Glossary (Fade-specific)

| Term | Effect |
|------|--------|
| **Nearsight** | Vision severely reduced (tunnel vision) |
| **Deafen** | Audio heavily muffled; footstep/audio cues lost |
| **Decay** | HP drain (cannot kill; stops at 1 HP) |
| **Terror Trail** | Ground marking following enemy movement for 12 s; visible to Fade's team; turbocharges Prowler tracking |
| **Tether / Seize** | Enemy locked in position, cannot escape zone |
| **Reveal** | Enemy location shown through walls to team |

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **prowler / cat / creature** | Prowler ability |
| **seize / tether / knot** | Seize ability |
| **haunt / eye / reveal orb** | Haunt ability |
| **nightfall / ult** | Nightfall ultimate |
| **trail / trailed** | Enemy marked with terror trail |
| **decayed** | Enemy under decay effect |
| **deafened** | Enemy deafened |
| **nearsighted** | Enemy nearsighted by Prowler |
| **haunt hit [N]** | N enemies revealed by Haunt |
| **nightfall hit [N]** | Fade's voice indicator, relayed to team |
| **shoot the eye** | Destroy Haunt before it reveals |
| **prowler locked on** | Prowler following a terror trail toward enemy |

---

## 6. GEKKO

**Role:** Initiator | **Origin:** Los Angeles, USA
**Archetype:** Creature-companion initiator; reclaim mechanic gives effectively more charges per round than any other agent; can plant/defuse spike via Wingman; unique for combining flash + scout + detain in one kit.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **Mosh Pit** | 250 cr | 1 | Thrown; large AoE; 10 dmg/s before detonation; explodes once; **not reclaimable** |
| Q | **Wingman** | 300 cr | 1 | 80 HP; concuss; can **plant/defuse** spike; reclaimable globule |
| E (sig) | **Dizzy** | Free | 1 | Flies forward; plasma blasts; **blind** (not flash); reclaimable globule |
| X (ult) | **Thrash** | 7 pts | — | Pilotable; lunges into enemies; **detain** radius; reclaimable globule (1 per ult) |

### The Reclaim Mechanic

When **Wingman**, **Dizzy**, or **Thrash** expire or complete their action, they revert to a dormant **globule** on the ground. Gekko can interact (hold interact key) for **1.5 s** to reclaim the globule, restoring that ability charge after a **15 s cooldown**. Globules vanish if not reclaimed within ~15 s.

**Mosh Pit is the only ability that CANNOT be reclaimed.**

### Ability Detail

**Mosh Pit (C)**
- Thrown like a grenade; can be thrown underhand (alt-fire) for close range.
- On landing, Mosh duplicates across a large area — expands the zone.
- 10 dmg/s while active, then detonates for high damage.
- Effective for post-plant denial, clearing close angles, flushing corners.
- Cannot be picked up. Destroyable.

**Wingman (Q)**
- Gekko sends Wingman forward; creature autonomously seeks the nearest visible enemy.
- On detecting an enemy: Wingman emits a **concussive blast** (dazed/disoriented).
- **Plant mechanic:** Alt-fire when targeting a spike site (or planted spike) → Wingman will plant the spike (Gekko must have spike in inventory) OR defuse it.
- 80 HP — rifle shot destroys Wingman.
- After completing its mission or expiring: drops as a reclaimable globule.

**Dizzy (E — Signature)**
- Gekko sends Dizzy soaring forward through the air in an arc.
- Dizzy charges and fires **plasma blasts** at all enemies in LoS.
- Enemies hit are **blinded** (not a standard flash — a unique status that also blinds the minimap).
- Dizzy then expires into a reclaimable globule.
- Because Dizzy is projectile-based (not an instant flash), enemies can break LoS by ducking or dodging.

**Thrash (X — Ultimate)**
- Gekko links with Thrash and pilots her (FPV control, similar to Sova's drone).
- Steer Thrash through enemy territory; she can be destroyed (HP not publicly confirmed, but can be shot).
- **Activate:** Thrash lunges forward and explodes, **detaining** all enemies in a small radius.
- Detained enemies cannot move, shoot, or use abilities for ~3 s.
- After Thrash detonates (or expires without detaining), she drops as a reclaimable globule.
- **Important:** Thrash can only detain with the lunge explosion — steering alone does nothing.

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **dizzy / flash** | Dizzy ability (causes blind, called a flash colloquially) |
| **wingman / wing** | Wingman ability |
| **concussed / stunned** | Wingman concuss effect |
| **mosh / pit / molly** | Mosh Pit ability |
| **thrash / ult** | Thrash ultimate |
| **detained** | Thrash detain effect on enemy |
| **globule / glob / reclaimable** | Dormant creature after expiry |
| **reclaim / pick up** | Recovering a globule for ability reuse |
| **wingman plant** | Using Wingman to plant the spike |
| **wingman defuse** | Using Wingman to defuse the spike |
| **blinded** | Enemy hit by Dizzy's plasma |
| **plasma / shot** | Dizzy's plasma blast attack |

---

## 7. TEJO

**Role:** Initiator | **Origin:** Colombia
**Archetype:** Long-range gadget initiator; suppression + concuss + damage via tech-based drone, sticky grenade, and guided missiles; heavy post-patch (10.09) nerfs shifted from free-salvo machine to bought utility. Signature is now missiles (Guided Salvo). Only Initiator whose signature deals direct damage.

### Abilities

| Slot | Name | Cost | Charges | Key Stats |
|------|------|------|---------|-----------|
| C | **Stealth Drone** | 400 cr | 1 | Drone; 42 HP; 6 s control; detonates → 16 m pulse; **8 s suppress** + reveal |
| Q | **Special Delivery** | 200 cr | 1 | Sticky grenade; 20–35 dmg; **2.5 s concuss**; alt-fire for 1-bounce throw |
| E (sig) | **Guided Salvo** | 150 cr (2nd) | 2 | Free 1st charge/round; 45 m range; missiles: 50–65 dmg × 3 ticks in 1.6 s |
| X (ult) | **Armageddon** | 9 pts | — | Directional airstrike map; 60 dmg × 4 ticks/segment over 1 s; multiple segments along path |

### Ability Detail

**Stealth Drone (C)**
- Tejo throws the drone forward, then pilots it (FPV, similar to Sova's Owl Drone).
- Duration: 6 s of controlled flight. Drone HP: 42 — fragile, one rifle hit destroys it.
- Windup: 0.4 s.
- **"Stealth":** the drone is harder to see/hear at range than Sova's Owl Drone.
- **Detonate:** press fire while controlling → drone explodes, emitting a **16 m radius pulse**.
- Pulse effects on enemies hit: **fully revealed** (not snapshot — continuous reveal) and **suppressed for 8 s**.
- After patch 12.x: reveal changed from snapshot to full continuous reveal while suppress is active.
- Primary use: fly into a site, detonate on a cluster of defenders → team rushes in with abilities locked.

**Special Delivery (Q)**
- Sticky grenade; throws in an arc.
- Sticks to the first surface it contacts.
- **Primary fire:** direct arc throw (immediate stick).
- **Alt-fire:** single-bounce throw — bounces once before sticking (for over-wall or around-corner delivery).
- Explosion: 20–35 dmg (outer to inner radius) + **2.5 s concuss**.
- Windup: 0.9 s.
- Post-nerf: concuss down from 4 s → 2.5 s. Damage cap introduced.
- Main use: concuss a corner or doorway to enable safe entry.

**Guided Salvo (E — Signature)**
- Tejo opens a map targeting UI and selects up to two target locations.
- Alt-fire to launch: missiles autonomously navigate to the selected locations.
- **Charges:** 1 free charge per round (regenerates); 2nd charge costs 150 cr.
- No cooldown (post patch 10.09).
- **Range:** 45 m maximum targeting distance (down from 55 m post-nerf).
- **Damage:** 50–65 per explosion tick (outer to inner); each missile detonates 3 times over ~1.6 s.
- Missiles deal damage and concuss. Strong for forcing enemies off post-plant positions.
- Can fire both missiles at the same location for compounding pressure.
- Map range limitation means targets must be within 45 m of Tejo.

**Armageddon (X — Ultimate)**
- Tejo opens a tactical strike map targeting overlay.
- Select an **origin point** and an **end point** to define the strike path and direction.
- Alt-fire during targeting cancels origin point selection.
- A wave of explosions sweeps along the selected line path.
- **Damage:** 60 dmg × 4 ticks over ~1 s per zone segment, multiple segments along the path.
- 9 ultimate points (increased from 8 in patch 10.09 nerf).
- Effective for: clearing long corridors, forcing enemies off spike, site-wide pressure post-plant.
- Enemies can move perpendicular to escape the wave if they react quickly.

### Comm Phrasing / Callout Terms

| Term | Meaning |
|------|---------|
| **drone / stealth drone** | Stealth Drone ability |
| **suppressed / suppression** | 8 s suppress from drone detonation |
| **revealed** | Drone pulse reveal effect |
| **detonate / pop the drone** | Firing the drone's suppression pulse |
| **sticky / delivery / concuss grenade** | Special Delivery |
| **concussed** | Special Delivery effect |
| **bounce / one bounce** | Alt-fire throw on Special Delivery |
| **missiles / rockets / salvo** | Guided Salvo |
| **salvo up / sending missiles** | Guided Salvo in use |
| **armageddon / airstrike / ult** | Armageddon ultimate |
| **strike path / line** | The direction of Armageddon sweep |
| **move perpendicular** | How to escape Armageddon wave |

---

## Cross-Agent Status Effect Reference

| Status | Source agents | Description |
|--------|--------------|-------------|
| **Suppressed** | KAY/O (ZERO/point, NULL/cmd), Tejo (Stealth Drone) | All abilities locked; cannot use any agent utility |
| **Concussed / Dazed** | Breach (Fault Line, Rolling Thunder), Skye (Trailblazer), Tejo (Special Delivery, Guided Salvo), Gekko (Wingman) | Blurred vision, reduced accuracy, slowed reaction |
| **Blinded / Flashed** | Breach (Flashpoint), KAY/O (FLASH/drive), Skye (Guiding Light), Gekko (Dizzy) | Full white-out; cannot see anything |
| **Nearsighted** | Skye (Seekers), Fade (Prowler) | Vision tunneled to a small central cone |
| **Deafened** | Fade (Seize, Nightfall) | Audio severely muffled; footsteps inaudible |
| **Decay** | Fade (Seize, Nightfall) | HP drains; stops at 1 HP (cannot kill alone) |
| **Detained** | Gekko (Thrash) | Cannot move, shoot, or use abilities; ~3 s |
| **Tethered** | Fade (Seize) | Cannot exit the Seize zone; forced to stay put |
| **Terror Trail** | Fade (Haunt, Nightfall) | Ground trail marks enemy movement for 12 s; turbocharges Prowlers |
| **Marked / Tagged** | Sova (Owl Drone dart, Recon Bolt), KAY/O (NULL/cmd team-side reveal) | Enemy position revealed through walls to team |
| **Revealed** | Sova (Recon Bolt, Hunter's Fury), Fade (Haunt, Nightfall), Tejo (Stealth Drone) | Enemy shown on map/outlines to team |

---

## Comp / Relay Comm Quick-Reference (All Initiators)

Below: every ability in short relay-comm form, as a Valorant player would call it mid-round.

### Sova
- "Recon bolt up" / "Recon on [site]" / "Dart's out" / "Dart hit two"
- "Drone up" / "Droning A" / "Marked him"
- "Shocking [location]" / "Double shock setup" / "One bounce, full charge"
- "Fury up, don't peek" / "Three beams, line up"

### Breach
- "Flashing [location] — close your eyes" / "Hard flash [location]"
- "Faulting / Stunning [location]" / "Fault [location], go in"
- "Shocking the wall" / "Aftershock post-plant"
- "Ulting — Rolling Thunder" / "Move out, ult going off"

### Skye
- "Hawk up / Flashing [location] — look away" / "Bird out"
- "Tiger [location]" / "Concussed, go" / "Dog in, he's stunned"
- "Seeking / Seekers out" / "Seeker hit three"
- "Healing — group up"

### KAY/O
- "Knife out [location]" / "Knife hit [N] — abilities gone, go"
- "Flashing [location]" / "Pop flash"
- "Frag down [location]" / "Molly post-plant"
- "Overloading / Null up" / "I'm down, revive me"

### Fade
- "Haunt up / Eye up" / "Haunt hit [N] / Shoot the eye"
- "Prowler out" / "Prowler on trail, can't escape"
- "Seize [location]" / "He's tethered, go"
- "Nightfall — [N] hit" / "Trailed, push the trail"

### Gekko
- "Dizzy out / Flashing [location]" / "He's blinded"
- "Wingman out / Wingman planting"
- "Mosh down / Molly post-plant"
- "Thrashing / Ult out" / "He's detained, go" / "Reclaiming globule"

### Tejo
- "Drone out" / "Popping drone / He's suppressed eight seconds, go"
- "Sticky [location] / Concussed"
- "Missiles up / Salvo on [location]" / "Both rockets [location]"
- "Armageddon / Airstrike [site]" / "Get out of the line"

---

## Notes for Corpus Generation

1. **KAY/O:** In relay speech, say "Kayo" (not "K-A-Y-slash-O"). Ability names pronounced literally: "Zero-point", "Null-cmd" ("null command"), "Flash-drive", "Frag-ment".
2. **Ability name variants:** Players use abbreviated/informal names constantly. Sova's Recon Bolt = "dart"; Skye's Guiding Light = "hawk"; Breach's Flashpoint = "flash through wall"; Fade's Haunt = "eye"; Gekko's Dizzy = "flash" even though it's technically plasma blind.
3. **Suppression vs. Concuss:** These are different. Suppression (KAY/O, Tejo) = abilities locked entirely. Concuss (Breach, Skye, Tejo, Gekko) = blurred vision/reduced accuracy but abilities still work.
4. **Reclaim (Gekko):** The globule mechanic is unique. "Reclaiming wingman" is a legitimate mid-round callout.
5. **Tejo missile range:** 45 m limit means Tejo must be within 45 m of target. Cross-map use is NOT possible.
6. **Skye double-flash:** 2 Guiding Light charges per round means Skye can flash the same site twice. Callout: "Two hawks ready."
7. **Sova bounce notation:** "Zero-bounce full charge" = straight shot max power; "Two-bounce two-bar" = lineup-specific.
8. **KAY/O revive:** Only revivable during NULL/cmd. "Kayo's down" is a priority callout — a teammate must leave position to revive.
9. **Tejo signature is damage:** Unlike other initiator sigs (which are free recon/flash), Guided Salvo costs 150 for the 2nd missile and deals real damage. It's an offensive signature.
10. **Fade terror trail synergy:** Nightfall + Prowlers = guaranteed nearsight chain. "Trails up, sending prowlers" is a compound-action callout.
