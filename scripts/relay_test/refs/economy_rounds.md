# Valorant Economy Reference — economy_rounds

> **Scope:** Credits system, weapon prices, armor/shield prices, agent ability costs,
> buy-round types, round-flow economy, team coordination, and all economy
> communication terms. Used to ground the Ultron relay corpus generation board.
>
> **Last updated:** 2026-06-14. Sources: Valorant official patch notes, Hotspawn,
> Valohub, eloboss.net, lootbar.com, itemgame.com, oneesports.gg, dotesports.com,
> Valorant Fandom Wiki, liquipedia.net/valorant.

---

## 1. Credits — Fundamentals

| Fact | Value |
|---|---|
| Starting credits (each half, round 1) | **800** |
| Credit cap (max held at once) | **9,000** |
| Unused credits carry over | Yes — never lost |
| Kill credit reward (standard) | **+200** per elimination |
| Kill credit reward (some abilities/shotguns) | Reduced (exact value varies by ability; generally 0–200) |
| Spike **plant** bonus (all attackers, win or lose) | **+300** per attacker |
| Spike **defuse** bonus | **+300** (per defender; less commonly cited — verify in-client) |

---

## 2. Round Win / Loss Bonus

### Win
| Event | Credits |
|---|---|
| Round win (every player on winning team) | **+3,000** |

Winning resets the loss-streak counter back to tier 1.

### Loss Bonus (Catch-Up Mechanic)
Loss bonuses escalate per consecutive loss streak. Winning any round resets streak to 0.

| Consecutive Losses | Loss Bonus per Player |
|---|---|
| 1st loss | **1,900** |
| 2nd consecutive loss | **2,400** |
| 3rd consecutive loss | **2,900** |
| 4th+ consecutive loss | **3,400** (maximum; cited by some 2026 sources — verify in-client) |

> NOTE: Most authoritative 2025 guides cap at 2,900 for 3+. The 3,400 tier for 4+ was
> reported by itemgame.com (2026 guide) but is not universally confirmed. Use 2,900 as
> the safe maximum for relay purposes unless in-client verifies 3,400.

**Economy implication:** A team that has lost three in a row can simultaneously save
and earn 2,900–3,400 cr, making a full buy achievable in one save round.

---

## 3. Weapons — Complete Price List

### Sidearms (Pistols)

| Weapon | Price (cr) | Notes |
|---|---|---|
| Classic | **0** (free) | Default weapon every round; fully auto alt-fire |
| Shorty | **300** | Double-barrel, short range; pistol round niche |
| Frenzy | **450** | Full-auto, high fire rate; run-and-gun eco pistol |
| Ghost | **500** | Semi-auto, silenced; most versatile pistol buy |
| Bandit | **600** | NEW 2026 — semi-auto precision pistol; 1-taps light armor (0–30m); 8-round mag; slots between Ghost and Sheriff |
| Sheriff | **800** | High-damage revolver; headshots kill through heavy armor at close range |

### SMGs (Submachine Guns)

| Weapon | Price (cr) | Notes |
|---|---|---|
| Stinger | **1,100** | Burst/full-auto; close range spray |
| Spectre | **1,600** | Silenced, accurate up close; standard half-buy rifle alternative |

### Shotguns

| Weapon | Price (cr) | Notes |
|---|---|---|
| Bucky | **850** | Pump-action; right-click alt-fire; can one-tap at close range |
| Judge | **1,850** | Semi-auto shotgun; run-and-gun; eco disruptor |

### Rifles

| Weapon | Price (cr) | Notes |
|---|---|---|
| Bulldog | **2,050** | Burst rifle; cheapest rifle-tier; used in half/force buys |
| Guardian | **2,250** | Semi-auto; long-range one-tap; force/half-buy sniper alternative |
| Phantom | **2,900** | Silenced full-auto; no bullet tracer; slight damage drop at range |
| Vandal | **2,900** | Full-auto; no damage drop at range; one-tap headshot anywhere |

**Phantom vs. Vandal:** Both are the premier rifles. Vandal one-taps at all ranges;
Phantom is silenced and slightly lower bloom at close range. Personal preference.

### Sniper Rifles

| Weapon | Price (cr) | Notes |
|---|---|---|
| Marshal | **950** | Bolt-action; cheapest scope; one-tap headshot through light armor |
| Outlaw | **2,400** | Semi-auto dual-barrel; 140 body damage; budget Operator alternative |
| Operator | **4,700** | Bolt-action; lethal body shot at all ranges; strongest rifle in game |

### Machine Guns (LMGs)

| Weapon | Price (cr) | Notes |
|---|---|---|
| Ares | **1,600** | High capacity; gains fire rate while held; spray suppression tool |
| Odin | **3,200** | High damage; iron-sight ADS; post-plant/operator-deny niche |

### Melee

| Item | Price | Notes |
|---|---|---|
| Knife | **0** (always carried) | Run faster holding it; no economic relevance in buy phase |

---

## 4. Armor / Shields — Complete Price List

Three armor types exist. Armor absorbs damage before HP.

| Shield | Price (cr) | Armor Value | Notes |
|---|---|---|---|
| Light Armor (Light Shield) | **400** | **25 hp shield** | Budget armor; popular on half-buys and eco-force rounds |
| Regen Shield | **650** | **25 hp shield + 50 regen pool** | Added Patch 9.10. Regenerates up to 25 armor from a 50-point pool a few seconds after last hit; regen pool carries into next round. Sits between light and heavy. |
| Heavy Armor (Full Armor) | **1,000** | **50 hp shield** | Standard full-buy armor; reduces incoming damage to body significantly |

> **Key note:** Sheriff at 800cr can one-tap through light armor (25 shield) to the
> head. Heavy armor (50 shield) forces two body shots with most weapons.

---

## 5. Agent Ability Costs

Abilities are purchased each round in the buy phase. Signature abilities are free (auto-replenish each round; some require kills or cooldowns).

> **Total loadout credit estimates** (purchasable abilities only, excluding free signatures):

| Tier | Approx. Full Ability Cost | Agents |
|---|---|---|
| Budget | ~450–600 cr | Astra, Cypher, Killjoy, Viper, Omen |
| Standard | ~600–700 cr | Brimstone, Breach, KAY/O, Phoenix, Reyna, Skye, Sova, Yoru |
| High | ~700–800 cr | Sage, Fade, Neon |
| Highest | ~900 cr | Jett, Raze |

---

### 5a. Duelists

#### Jett
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Cloudburst | C | **200** | 3 | Brief smoke puff; can be curved mid-air |
| Updraft | Q | **150** | 2 | Vertical jump boost |
| Tailwind (Signature) | E | Free | 1 (kill-recharge) | Dash; replenishes on kills |
| Blade Storm (Ultimate) | X | 8 pts | — | Knives; one-tap headshot |
| **Total purchasable** | | ~**900 cr** | | |

#### Phoenix
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Blaze (Signature) | E | Free | 1 | Fire wall; heals Phoenix |
| Curveball | Q | **250** | 2 | Flash projectile; can curve left/right |
| Hot Hands | C | **200** | 1 | Fire zone; heals Phoenix on exit |
| Run It Back (Ultimate) | X | 6 pts | — | Respawn mechanic |
| **Total purchasable** | | ~**700 cr** | | |

#### Raze
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Boom Bot | C | **300** | 1 | Bouncing bot; finds enemies |
| Blast Pack | Q | **200** | 2 | Sticky grenade / movement boost |
| Paint Shells (Signature) | E | Free | 1 (2-kill recharge) | Cluster grenade |
| Showstopper (Ultimate) | X | 8 pts | — | Rocket launcher |
| **Total purchasable** | | ~**700 cr** | | |

#### Reyna
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Leer | C | **250** | 2 | Floating eye; nearsights enemies who look at it |
| Devour / Dismiss (Signature) | E/Q | Free | Requires soul orbs from kills | Self-heal or invulnerability |
| Empress (Ultimate) | X | 6 pts | — | Combat frenzy; heals on kills |
| **Total purchasable** | | ~**500 cr** | | |

#### Yoru
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Fakeout | C | **100** | 2 | Footstep decoy |
| Blindside | Q | **250** | 2 | Flash that deploys off a surface |
| Gatecrash (Signature) | E | **200** | 2 (1 free + 1 extra) | Tether teleport; signature refills round start |
| Dimensional Drift (Ultimate) | X | 8 pts | — | Invisibility / invulnerability |
| **Total purchasable** | | ~**700 cr** | | |

#### Neon
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Fast Lane | C | **300** | 1 | Two energy walls running forward |
| Relay Bolt | Q | **200** | 2 | Bouncing stun projectile |
| High Gear (Signature) | E | Free | — | Sprint + slide; recharges on kills |
| Overdrive (Ultimate) | X | 8 pts | — | Full sprint + lightning beam |
| **Total purchasable** | | ~**700 cr** | | |

#### Iso
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Contingency | C | **250** | 1 | Forward energy wall blocking bullets |
| Undercut | Q | **300** | 1 | Blade that applies Vulnerability + Suppression (Patch 10.04 nerf: was 2 charges × 200) |
| Double Tap (Signature) | E | Free | Kill-triggered | Protects against one kill |
| Kill Contract (Ultimate) | X | 7 pts | — | 1v1 duel arena |
| **Total purchasable** | | ~**550 cr** | | |

#### Waylay *(newest duelist as of 2026)*
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Saturate | C | **300** | 1 | Nearsights enemies in area |
| Light Speed | Q | **300** | 1 | Speed dash leaving light trail |
| Refract (Signature) | E | Free | — | Split-image repositioning |
| Convergent Paths (Ultimate) | X | 8 pts | — | Thai duelist; light-beam area |
| **Total purchasable** | | ~**600 cr** | | |

---

### 5b. Controllers

#### Brimstone
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Stim Beacon | C | **100** | 2 | Speed boost AoE |
| Incendiary | Q | **300** | 1 | Molotov-style fire zone |
| Sky Smoke (Signature) | E | **100** each | Up to 3 smokes | Satellite-deployed smokes; long range; cheap but pre-planted |
| Orbital Strike (Ultimate) | X | 7 pts | — | Orbital laser; deals damage per tick |
| **Total purchasable** | | ~**650 cr** | | (2× Stim + Incendiary + 1 extra smoke) |

#### Viper
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Snakebite | C | **100** | 2 | Acidic puddle; vulnerable debuff |
| Poison Cloud | Q | **200** | 1 | Gas canister smoke; reusable each round with fuel |
| Toxic Screen (Signature) | E | Free | 1 | Long wall of gas; fuel-dependent |
| Viper's Pit (Ultimate) | X | 7 pts | — | Massive toxic cloud dome |
| **Total purchasable** | | ~**600 cr** | | (2× Snakebite + Poison Cloud) |

#### Omen
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Shrouded Step | C | **100** | 2 | Short-range teleport blink |
| Paranoia | Q | **400** | 1 | Shadow projectile that nearsights all enemies it passes through |
| Dark Cover (Signature) | E | Free | 2 (replenish over time) | Global-range smokes; no plant limit |
| From the Shadows (Ultimate) | X | 7 pts | — | Global teleport |
| **Total purchasable** | | ~**600 cr** | | (2× Shrouded Step + Paranoia) |

#### Astra
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Gravity Well | C | — | Uses a Star | Pull + concuss AoE |
| Nova Pulse | Q | — | Uses a Star | Concuss AoE |
| Nebula / Dissipate (Signature) | E | — | Uses a Star / free recall | Main smoke ability |
| Stars | | **150** each | 2 free + 3 purchasable at 150 each | Place up to 5 stars globally on minimap |
| Cosmic Divide (Ultimate) | X | 8 pts | — | Cross-map wall blocking bullets and audio |
| **Total purchasable** | | ~**450 cr** | | (3 extra stars) — cheapest controller |

> NOTE: Astra's economy is unique — she buys Stars, which she then activates as any of three ability types. Two Stars spawn free each round.

#### Harbor
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Cove | C | **350** | 1 | Sphere of water that blocks bullets; short duration |
| High Tide | Q | **300** | 1 | Water wall (after Patch 11.10 rework; was signature) |
| Cascade (Signature) | E | Free | 1 | Rolling wave that slows |
| Reckoning (Ultimate) | X | 7 pts | — | Radianite geysers concussing enemies |
| **Total purchasable** | | ~**650 cr** | | |

> Patch 11.10 (November 2025): Harbor rework moved High Tide from signature → purchasable at 300 cr. Cascade became the free signature.

#### Clove *(Scottish controller; resumes play after death)*
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Pick-Me-Up | C | **100** | 1 | Absorbs soul on nearby kill → temporary speed + HP boost |
| Ruse | Q | **150** | Extra smoke beyond free allotment | Smokes; can deploy after death |
| Meddle (Signature) | E | Free | 1 | Decay zone |
| Not Dead Yet (Ultimate) | X | 8 pts | — | Revives Clove after death if team kills/plants spike |
| **Total purchasable** | | ~**600 cr** | | |

---

### 5c. Initiators

#### Sova
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Owl Drone | C | **400** | 1 | Controllable drone; tags enemies |
| Shock Bolt | Q | **150** | 2 | Electric arrow; bounces; damages on ground |
| Recon Bolt (Signature) | E | Free | 1 | Reveal arrow; enemy can destroy |
| Hunter's Fury (Ultimate) | X | 8 pts | — | 3 long-range energy blasts through walls |
| **Total purchasable** | | ~**700 cr** | | |

#### Breach
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Aftershock | C | **200** | 1 | Slow-trigger charge through walls; high damage |
| Flashpoint | Q | **250** | 2 | Blind through walls |
| Fault Line (Signature) | E | Free | 1 | Seismic wave that stuns |
| Rolling Thunder (Ultimate) | X | 8 pts | — | Massive seismic push through walls |
| **Total purchasable** | | ~**700 cr** | | |

#### Skye
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Regrowth | C | **150** | 1 | Area heal for teammates (not self); fueled charge |
| Trailblazer | Q | **250** | 1 | Controllable tasmanian tiger concuss |
| Guiding Light (Signature) | E | Free (1) + 250 ea extra | 1 free + 1 purchasable | Bird flash; can detonate manually; 1 free per round |
| Seekers (Ultimate) | X | 8 pts | — | 3 seeker orbs that home to enemy locations |
| **Total purchasable** | | ~**650 cr** | | (Regrowth + Trailblazer + extra Guiding Light) |

#### KAY/O
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| FRAG/MENT | C | **200** | 1 | Bouncing fragment explosive; pulses |
| FLASH/DRIVE | Q | **250** | 2 | Flip-knife flash; can throw short or long with alt-fire |
| ZERO/POINT (Signature) | E | Free | 1 (round-start) | Suppression knife; suppresses all abilities in radius |
| NULL/CMD (Ultimate) | X | 8 pts | — | Overcharge; revivable if downed during it |
| **Total purchasable** | | ~**700 cr** | | |

#### Fade
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Seize | C | **200** | 1 | Nightmare orb; tethers and deafens enemies in radius |
| Prowler | Q | **250** | 2 | Creature that tracks enemies and nearsights them |
| Haunt (Signature) | E | Free | 1 | Reveal orb; reveals enemy locations on minimap |
| Nightfall (Ultimate) | X | 8 pts | — | Wave that deafens, decays, and trails enemies |
| **Total purchasable** | | ~**700 cr** | | |

#### Gekko
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Mosh Pit | C | **250** | 1 | Creature that creates expanding acid pool |
| Wingman | Q | **300** | 1 | Creature that plants/defuses spike and stuns |
| Dizzy (Signature) | E | Free | 1 | Creature that blinds enemies; reclaim available |
| Thrash (Ultimate) | X | 8 pts | — | Controllable creature that stuns and detains |
| **Total purchasable** | | ~**550 cr** | | Gekko can **reclaim** Wingman/Dizzy/Thrash for a free extra charge |

#### Tejo *(Colombian initiator; released Patch 10.00, Jan 2025)*
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Special Delivery | C | **200** | 1 | Sticky grenade; concusses and damages (Patch 10.09: reduced from 300) |
| Guided Salvo | Q | **150** | 1 free + 1 purchasable | Missiles to selected target locations; fires one per charge (Patch 10.09 rework: was 2 rockets per cast; now per-charge) |
| Stealth Drone (Signature) | E | Free (signature) then **400** for extra | 1 per round (purchasable extra) | Stealthed scout drone; sonar pulse (Patch 10.09: increased from 300) |
| Armageddon (Ultimate) | X | 9 pts | — | Air strike; wall-penetrating; large AOE (Patch 10.09: increased from 8 pts) |
| **Total purchasable** | | ~**350–750 cr** | | Highly variable depending on Guided Salvo/Drone investment |

---

### 5d. Sentinels

#### Cypher
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Trapwire | C | **200** | 2 | Hidden trip-wire; stuns and reveals |
| Cyber Cage | Q | **100** | 2 | Drop-activated mini-smoke with audio cue |
| Spycam (Signature) | E | Free | 1 | Placeable camera; dart-shoots to tag enemies |
| Neural Theft (Ultimate) | X | 6 pts | — | Reveals all enemy locations on map |
| **Total purchasable** | | ~**600 cr** | | (2× Trapwire + 2× Cyber Cage) |

#### Sage
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Barrier Orb | C | **400** | 1 | Large deployable wall; can be rotated |
| Slow Orb | Q | **200** | 2 | Lingering slow puddle |
| Healing Orb (Signature) | E | Free | 1 (auto-replenish) | Heals ally or self (on cooldown for self) |
| Resurrection (Ultimate) | X | 8 pts | — | Revives a dead teammate |
| **Total purchasable** | | ~**800 cr** | | Second-most expensive full loadout |

#### Killjoy
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Nanoswarm | C | **200** | 2 | Hidden grenade; activated remotely; 45 dmg/s |
| Alarmbot | Q | **200** | 1 | Hidden proximity bot; hunts and applies vulnerable |
| Turret (Signature) | E | Free | 1 (20s recall / 60s rebuild) | Auto-shooting turret; can be recalled |
| Lockdown (Ultimate) | X | 8 pts | — | Massive detain of all enemies in radius |
| **Total purchasable** | | ~**600 cr** | | (2× Nanoswarm + Alarmbot) |

#### Chamber
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Trademark | C | **150** | 2 | Proximity trip mine; TP-range anchor |
| Headhunter | Q | **100 per bullet** | Max 8 bullets | Heavy pistol; each shot buys one bullet; can accumulate up to 8 bullets total |
| Rendezvous (Signature) | E | Free | 2 anchors | TP between anchors; destroyed if enemy gets to anchor |
| Tour de Force (Ultimate) | X | 8 pts | — | Powerful sniper; kills create slowing puddles |
| **Total purchasable** | | Varies — ~**300–1,100 cr** | | Chamber is the most variable agent to budget; "most expensive kit" due to HH bullets |

#### Deadlock
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| GravNet | C | **200** | 1 | Grenade that forces enemies to crouch and slows |
| Sonic Sensor | Q | **200** | 2 | Concuss trap triggered by loud sounds |
| Barrier Mesh (Signature) | E | Free | 1 | Radianite mesh wall barrier |
| Annihilation (Ultimate) | X | 8 pts | — | Nanowire cocoon that kills if not freed |
| **Total purchasable** | | ~**600 cr** | | (GravNet + 2× Sonic Sensor) |

#### Vyse *(released Aug 2024, Episode 9 Act 2)*
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Shear | C | **200** | 1 | Hidden wall trap; indestructible wall triggers when enemy crosses |
| Razorvine | Q | **150** | 2 | Invisible nest on ground; slows and damages movers |
| Arc Rose (Signature) | E | Free | 1 | Deployable/wall-placed blind; can be picked up and redeployed |
| Steel Garden (Ultimate) | X | 8 pts | — | Forces enemies to switch to sidearms only |
| **Total purchasable** | | ~**500 cr** | | |

#### Veto *(released Oct 7, 2025, Episode 25 Act V)*
| Ability | Key | Cost | Charges | Notes |
|---|---|---|---|---|
| Crosscut | C | **200** | 2 | Vortex teleport anchor; teleport back to it while in LOS |
| Chokehold | Q | **200** | 1 | Fragment that traps enemies; applies Deafened + Decayed |
| Interceptor (Signature) | E | Free | 1 (45s cooldown if destroyed) | Trophy-system device; destroys enemy utility in radius |
| Evolution (Ultimate) | X | 7 pts | — | Full mutation: combat stim + regen + immunity to all debuffs for full round |
| **Total purchasable** | | ~**600 cr** | | Anti-utility sentinel |

---

## 6. Buy Round Types

These are the standard classifications used in competitive communication.

### 6a. Pistol Round (Round 1 each half)
- All players start with exactly **800 credits**.
- No loss bonus, no carry-over.
- Standard buys: Ghost (500), Frenzy (450), Shorty (300), light armor (400), 1–2 abilities.
- Most players buy: Ghost + 1 ability or armor + Classic.
- Classic is free; unspent credits carry to round 2.

### 6b. Bonus Round (Post-Pistol Win)
Also called: *Second round*, *Gun round bonus*, *Spectre round*

- Occurs round 2 after winning pistol.
- Players carry **weapons from pistol win** + newly earned credits (3,000 + 200/kill).
- Standard buy: **Spectre (1,600) + Light Armor (400)** = 2,000 cr.
- Do NOT upgrade to rifle — save credits to maintain future full-buy.
- Objective: extend the credit advantage into round 3.
- If team wins round 2, round 3 is still a partial-buy; budget accordingly.

### 6c. Eco Round / Save Round
Callout: *"eco," "save," "full save," "save round"*

- Team intentionally spends minimal credits to bank for next round.
- Typical spend: Classic (free) or Shorty (300) + maybe 1–2 cheap abilities.
- Acceptable eco buy: anything **under ~1,000–1,500 cr** total.
- Play style on eco: contest spike plants, land free damage, avoid dying with expensive gear.
- Goal: guarantee a **full buy** the following round.

**When to eco:**
- After losing a full buy (both guns AND armor wasted) and team credits are low.
- When 3+ players cannot afford rifle + heavy armor.
- When the loss bonus will bring everyone to full-buy threshold in one save.

### 6d. Force Buy
Callout: *"force," "force buy," "forcing this round"*

- Team spends **everything available** even if below full-buy threshold.
- Typical loadout: Spectre/Sheriff/Bulldog + Light Armor + abilities.
- High risk: losing a force leaves the team on a second consecutive thin round.
- Acceptable when: team has momentum and suspects enemy eco; when 4–5 players can field identical or close loadouts; when the team is up in rounds and can absorb a loss.

**Force buy types:**
- *Full force:* Everyone spends all available credits.
- *Coordinated force:* Team agrees on a specific weapon (e.g., "all Spectre force").
- *Pistol force:* Sheriff or Ghost + light armor; used when credits are 1,200–1,600 range.

### 6e. Half Buy (Light Buy)
Callout: *"half buy," "light buy," "half-eco"*

- Middle ground between eco and full buy.
- Typical spend: **~2,000–3,000 cr** per player.
- Common loadout: Spectre + Light Armor, Marshal + Light Armor, or Sheriff + Heavy Armor + abilities.
- Keeps player competitive without fully committing.
- Used when most players are **2,000–3,200 cr** and a full buy next round is still possible.

### 6f. Full Buy
Callout: *"full buy," "we're buying," "buy round"*

- Team fields **best available weapons + full gear + all abilities**.
- Standard full buy: **Phantom/Vandal (2,900) + Heavy Armor (1,000) + abilities (~600 avg)** = **~4,500–5,000 cr per player**.
- Minimum threshold to full buy: **~3,900 cr** (rifle + heavy armor alone, no abilities).
- Ideal threshold: **~4,500 cr** (rifle + armor + most agents' full ability buy).
- High-ability agents (Jett, Raze, Sage): push threshold to **~4,900–5,700 cr**.

### 6g. Anti-Eco Round
Callout: *"anti-eco," "they're saving," "eco round for them"*

- Defensive adjustment when enemy team is on eco.
- Your team buys enough to counter cheap weapons without over-investing.
- Common setup: Spectre + Light Armor instead of Phantom + Heavy Armor.
- Saves credits if a kill net results in weapon drops from a full-buy enemy pick.
- Alternatively: team full-buys and plays passively to deny eco-round kills.

---

## 7. Round-Flow Economy — Standard Sequence

```
ROUND 1  Pistol Round
         All start 800 cr. Buy pistol / armor / 1 ability.

ROUND 2  After W: Bonus Round — Spectre + light armor, carry pistol-round gun.
         After L: Full Save (eco) — spend <500, bank for round 3.

ROUND 3  After W+W: Soft buy / partial — team may not have full credits yet.
         After W+L: Full buy (if 4+ players at 3,900+).
         After L+L: Force or second eco — loss streak now at 2 (2,400 cr).

ROUND 4+ Economy determined by:
         - Current credits per player
         - Number of consecutive losses (max loss bonus)
         - Whether full buy is achievable as a team (4+ players at threshold)
         - Whether enemy is on eco (adjust accordingly)
```

---

## 8. Team Coordination Rules

### The Team Economy Principle
Economy is a **team system**, not individual. Five players with different buy levels create
an uneven loadout that compounds into round losses.

- **3+ players calling save = everyone saves** (even if 1–2 players can full buy).
- **4+ players at full-buy threshold = team buys** (2 short players are dropped a rifle).
- Never full-buy alone when 3+ teammates are on eco.

### Credit Check
Before buy phase closes:
- Call credits aloud: *"I have 4,200, full buy."*
- Identify who is short: *"Miks is at 2,800, he needs a rifle."*

### The Drop System
In-game mechanic: players can **request** a weapon and teammates can fulfill it.

**How drops work:**
- Right-click a weapon in the buy menu to **request it** (visible to teammates).
- A teammate left-clicks the request to buy the weapon and send it to you.
- The weapon is auto-delivered — no physical dropping needed.
- Physical dropping (press G): hold the weapon and press G to drop it at your feet; any player walks over it.

**Standard drop scenarios:**
- *"Drop me a Vandal"* — teammate buys and requests-sends.
- *"I'll drop you a Spectre"* — offering a buy for an eco teammate.
- Capped teammate drops excess credits by buying for short players.
- Drops do not cost the dropper extra if they have spare credits.

### Economy Synchronization Calls
| Scenario | Call |
|---|---|
| Team should save | *"Save this round"* / *"Eco"* |
| Team should force | *"Force this round"* / *"Forcing"* |
| Team should full buy | *"Buy this round"* / *"Full buy"* |
| Half buy | *"Half buy"* / *"Light buy"* |
| Check credits | *"What's everyone's econ?"* / *"Econ check"* |
| Drop request | *"Drop me a Vandal/Phantom/rifle"* |
| Offering drop | *"I'll drop you a gun"* / *"I got you"* |
| Anti-eco setup | *"They're saving, half buy"* / *"Anti-eco"* |
| Post-loss call | *"Save next"* / *"We eco"* |
| Loss streak confirmed | *"We're at 2,900 loss bonus, eco gets us there"* |

---

## 9. Economy Communication Vocabulary — Complete Glossary

| Term | Definition |
|---|---|
| **Credits** (Creds) | In-game currency; earned each round; used to buy weapons/armor/abilities |
| **Econ / Economy** | Team's collective credit state and purchasing strategy |
| **Full buy** | Best weapons + heavy armor + all abilities |
| **Half buy / Light buy** | Mid-tier spend (~2,000–3,000 cr); SMG or budget rifle + light armor |
| **Eco / Save / Save round** | Minimal spend to bank credits for next round |
| **Force buy / Force** | Spend all available credits even if below full-buy threshold |
| **Bonus round** | Round 2 after winning pistol; carry pistol-round gun, buy SMG |
| **Pistol round** | Round 1 each half; all players start at 800 cr |
| **Anti-eco** | Buying conservatively when enemy is on eco to avoid handing them guns |
| **Loss bonus** | Credits awarded for losing; escalates 1,900 → 2,400 → 2,900 (→ 3,400) |
| **Loss streak** | Consecutive rounds lost; determines loss bonus tier |
| **Win bonus** | 3,000 cr each to every player on the winning team |
| **Drop** | Buying a weapon for a teammate (via request system or physical G-drop) |
| **Request** | Asking a teammate to buy you a weapon |
| **Credit cap** | Maximum 9,000 cr held; excess credits effectively lost if not spent |
| **Carry over** | Unspent credits automatically roll into next round |
| **Spike plant bonus** | +300 cr to all attackers who were alive when the spike was planted |
| **Kill credit** | +200 cr per kill (standard); may be reduced for some ability/shotgun kills |
| **Rifle** | Vandal or Phantom (2,900 cr each); standard full-buy weapon |
| **Operator / Op** | 4,700 cr sniper; most powerful individual weapon; most expensive single buy |
| **Eco rifle** | Bulldog (2,050) or Guardian (2,250); cheaper rifle-tier options on partial buys |
| **SMG** | Spectre (1,600) or Stinger (1,100); standard bonus/half-buy weapons |
| **Marshal** | 950 cr sniper; economical; used in half-buys |
| **Outlaw** | 2,400 cr dual-barrel sniper; budget Op alternative |
| **Light armor** | 400 cr; 25 shield HP |
| **Heavy armor / Full armor** | 1,000 cr; 50 shield HP |
| **Regen Shield** | 650 cr; 25 shield HP + 50 regen pool |
| **Utility / Abilities** | Agent-specific purchasable abilities; average ~600 cr/round |
| **Full utility** | Buying every purchasable ability for your agent |
| **Save utility** | Skipping ability purchases to bank credits |
| **Econ check** | Asking team members to call out their current credit totals |
| **Econ rating** | Metric: damage dealt per 1,000 credits spent (performance efficiency) |
| **Thrifty** | Winning a round while spending ~2,500 fewer credits than opponents (in-game medal) |
| **Spike plant** | Attacker interaction; awards +300 cr bonus to all living attackers |
| **Gun round** | A round where both teams have rifles (full buy on both sides) |
| **Pistol round** | First round of each half |
| **Second round** | Round 2; economy is set by pistol-round outcome |
| **Third round** | Round 3; typically first possible full buy for losers |
| **Economy reset** | Losing a costly round forces a save to rebuild economy |
| **Eco kill** | Killing a fully-bought enemy player while on eco; earns credits and potentially a dropped weapon |
| **Gun drop / Pick up gun** | Collecting an enemy's dropped weapon after a kill |
| **Ult charge / Ult orbs / Ult points** | Required orbs to activate ultimate; earned via kills, deaths, round win/loss, orb pickups |
| **Economy advantage** | Team with higher credits going into a round has better buying power |

---

## 10. Key Economy Decision Tree

```
Buy phase begins — check team credits:

ALL 5 players ≥3,900 cr?
  └── YES: Full buy (rifle + heavy armor + utility)
  └── NO: How many players are short?
        └── 1–2 short: Can the rich players drop them rifles?
              └── YES: Buy + drop → full buy for all
              └── NO: Force buy (everyone spends what they have)
        └── 3–4 short: Force or Eco?
              └── Do short players have ≥2,000 cr? → Force (Spectre/light)
              └── Short players have <1,500 cr? → Eco (save entire round)
        └── All 5 short / <1,200 cr each → Full eco (Classic only)

Eco round earned enough to full buy next round?
  └── YES: Next round = Full buy
  └── NO: Second consecutive eco until threshold reached
```

---

## 11. Round Type Summary Table

| Round Type | Per-Player Spend | Typical Loadout | When Used |
|---|---|---|---|
| Pistol | 800 cr budget | Classic/Ghost/Frenzy + armor or 1 ability | Round 1 only |
| Bonus | Variable | Spectre + light armor (carry pistol gun) | Round 2 after pistol win |
| Full Buy | 3,900–5,700+ cr | Vandal/Phantom + heavy armor + utility | Credits allow it for 4+ players |
| Half Buy | 2,000–3,000 cr | Spectre / Marshal / Bulldog + light armor | Majority of team in 2k–3k range |
| Force Buy | Spend all available | Whatever can be afforded | Momentum play; enemy likely on eco |
| Eco / Save | <500–1,000 cr | Classic + maybe 1 ability | Need to bank credits for full buy |
| Anti-Eco | 1,500–2,500 cr | Spectre + light armor | Enemy saving; avoid over-investing |

---

## 12. Sources

- Valohub: Valorant Economy Guide 2026 — valohub.co
- itemgame.com: Valorant 2026 Complete Economy Management Guide
- eloboss.net: Valorant Economy Guide (Bonus and Economy Rounds)
- lootbar.com: Valorant Economy Guide: When to Buy, Save, and Force
- hotspawn.com: All Weapons in Valorant — Full List, Prices, and Specs
- oneesports.gg: Valorant Terms and Calls All Players Should Know
- dotesports.com: VALORANT fan highlights agent utility costs
- Valorant Patch Notes 9.10 (Regen Shield) — playvalorant.com
- Valorant Patch Notes 10.04, 10.09 (Tejo/Iso nerfs) — playvalorant.com
- Valorant Patch Notes 11.10 (Harbor rework) — hotspawn.com
- Liquipedia VALORANT: Regen Shields — liquipedia.net/valorant
- Tracker.gg: Valorant Patch 9.10, Veto agent guide
- x.com/ValorantUpdated: Tejo 10.09 ability cost changes (primary)
- switchbladegaming.com: Valorant Ability Economy 2026 (agent tiers)
- Various agent-specific searches: metabot.gg, pley.gg, boosting-ground.com

*Document generated for the Ultron relay corpus board. Cross-check agent ability costs
in-client before using for exact corpus dialogue — ability prices change with balance patches.*
