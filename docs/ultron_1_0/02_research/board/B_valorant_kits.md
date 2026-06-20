# Authoritative Valorant Agent Roster & Full Kit Reference (2026)

**Research date:** 2026-06-20  
**Question:** What is the current Valorant agent roster with each agent's full kit (all abilities + signature + ultimate) — accurate enough to inject as agent-context into the Ultron 1.0 LLM to prevent hallucinated kits?

---

## TL;DR Recommendation for Ultron 1.0

Inject the kit reference below as a **system-prompt context block** (or retrieved-on-demand RAG chunk) so that the 8B LLM never hallucinate ability names, slots, or effects when generating relay lines, callouts, or flavor commentary about specific agents.

Key facts:
- **29 agents** as of June 2026 (8 Duelists, 7 Initiators, 7 Controllers, 7 Sentinels).
- **Newest:** Miks (Controller, March 18 2026 — Act 2 Season 2026). Agent 30 by some counts.
- **Agent 29:** Veto (Sentinel, October 2025).
- **Agent 28:** Waylay (Duelist, March 2025).
- **Notable rework:** Harbor received a major kit overhaul in Patch 11.10 (late 2025); Cascade was replaced by Storm Surge and Cove moved to signature.
- For the relay path, only ability NAMES matter (e.g., "Sage wall", "Sova bolt", "Viper pit") — the LLM does not need to generate full mechanical descriptions during a relay. Full mechanical data is useful for PRIVATE_REPLY answers to questions like "What does Veto's E do?"
- Keep the injected context concise: agent name → role → 4 ability names (slot: name) is enough for relay accuracy. Full descriptions are in this doc for lookup/RAG retrieval.

**Recommended injection format** (per-agent token cost: ~30 tokens each, ~870 total for all 29):
```
Jett [Duelist]: C=Cloudburst, Q=Updraft, E=Tailwind, X=Blade Storm
```

---

## Findings

### Roster overview

Total: **29 agents** (June 2026). Distribution:
- Duelists: 8 (Iso, Jett, Neon, Phoenix, Raze, Reyna, Waylay, Yoru)
- Initiators: 7 (Breach, Fade, Gekko, KAY/O, Skye, Sova, Tejo)
- Controllers: 7 (Astra, Brimstone, Clove, Harbor, Miks, Omen, Viper)
- Sentinels: 7 (Chamber, Cypher, Deadlock, Killjoy, Sage, Veto, Vyse)

---

### DUELISTS (8 agents)

Role: entry agents built to take first contact, create space, and convert openings into site control.

#### Jett
- **C – Cloudburst**: Throw a smoke cloud that briefly obscures vision.
- **Q – Updraft**: Launch upward into the air.
- **E – Tailwind (Signature)**: Instantly dash in the direction of movement. Recharges on two kills.
- **X – Blade Storm (Ultimate, 7 pts)**: Equip a set of deadly knives that deal moderate damage and kill on headshot. Kills refresh the knives.

#### Phoenix
- **C – Blaze**: Throw a wall of fire that blocks vision and damages enemies passing through it; heals Phoenix.
- **Q – Hot Hands**: Throw a fireball that explodes on impact or delayed fuse, damaging enemies and healing Phoenix in the flames.
- **E – Curveball (Signature)**: Throw a curving flash that blinds all players looking at it.
- **X – Run it Back (Ultimate, 8 pts)**: Mark current position; if Phoenix dies or the ultimate timer expires, he is reborn at the marked position with full health.

#### Raze
- **C – Boom Bot**: Deploy a bot that travels forward, bouncing off walls, and explodes on enemy contact.
- **Q – Blast Pack**: Throw an explosive pack that adheres to surfaces; can be detonated for movement boost or to damage enemies.
- **E – Paint Shells (Signature)**: Throw a cluster grenade that detonates into sub-munitions.
- **X – Showstopper (Ultimate, 8 pts)**: Equip a rocket launcher; fire a rocket that deals massive area damage.

#### Reyna
- **C – Leer**: Throw an ethereal eye that nearsights all enemies who look at it.
- **Q – Devour**: Consume a Soul Orb dropped by a recently-killed enemy to rapidly heal.
- **E – Dismiss (Signature)**: Consume a Soul Orb to become briefly intangible (invulnerable). In Empress, also turns invisible.
- **X – Empress (Ultimate, 7 pts)**: Enter a frenzied state with increased fire rate, faster equip/reload, and kill-triggered overheal. All kills refresh the duration.

#### Neon
- **C – Fast Lane**: Send out two electric lines forward on the ground, creating tall walls of static electricity for cover.
- **Q – Relay Bolt**: Throw a bouncing bolt of electricity that creates a concussive burst on each bounce.
- **E – High Gear (Signature)**: Channel Neon's energy to sprint faster than any other agent. Sliding recharges on 2 kills.
- **X – Overdrive (Ultimate, 8 pts)**: Unleash Neon's full power with an electric beam that can be aimed; kills refresh the duration.

#### Yoru
- **C – Fakeout**: Send forward an echo that mimics Yoru's footsteps; activate to trigger a decoy that runs in the direction cast, drawing enemy fire.
- **Q – Blindside**: Tear a hole in reality and throw a portal-based flash that blinds all players looking at it when it deploys.
- **E – Gatecrash (Signature)**: Send out a tether in a direction; activate to teleport to its location. Can be faked.
- **X – Dimensional Drift (Ultimate, 7 pts)**: Equip a mask that renders Yoru invisible to enemies; he can freely roam and use non-damaging abilities.

#### Iso
- **C – Contingency**: Assemble a wall of prismatic energy that fires forward and blocks bullets.
- **Q – Undercut**: Throw a molecular bolt that briefly applies Fragile (increased damage taken) to enemies it passes through.
- **E – Double Tap (Signature)**: Enter a focus state; kills or damage on downed enemies generate energy orbs, collecting one grants a shield absorbing one instance of damage. Recharges on 2 kills.
- **X – Kill Contract (Ultimate, 7 pts)**: Throw a column of energy that pulls Iso and the first enemy hit into a 1v1 arena; the loser is eliminated.

#### Waylay (Agent 28, released March 2025)
- **C – Saturate** (300 creds, 1 charge): Instantly throw a cluster of light that explodes on the ground, **Hindering** (slows movement speed, fire rate, reload, recoil recovery, jump) all nearby enemies.
- **Q – Light Speed** (300 creds, 2 charges): Double-dash; the first dash can send Waylay upward.
- **E – Refract (Signature, free, 2-kill recharge)**: Place a beacon of light on the ground; reactivate at any point to instantly teleport back to it while **invulnerable** during travel.
- **X – Convergent Paths (Ultimate, 8 pts)**: Create an afterimage that projects a beam of light across the battlefield; after a delay, Waylay gains a powerful speed boost and the beam expands, **Hindering** all players in its range. No direct damage — pure zone denial.

Note: **Hinder** is Waylay's debuff mechanic — it reduces movement speed, fire rate, reload time, recoil recovery, and jump height simultaneously.

---

### INITIATORS (7 agents)

Role: information and setup agents who reveal defenders, clear angles, and make entries safer.

#### Sova
- **C – Owl Drone**: Deploy a flying drone you can pilot; fire a tagging dart to reveal and track enemies hit.
- **Q – Shock Bolt**: Shoot an electric bolt that bounces off surfaces and deals damage; can hold fire to add up to two extra bounces.
- **E – Recon Bolt (Signature)**: Fire a recon bolt that attaches to surfaces and pulses, revealing all enemies in LoS (sonar scan). Enemies can destroy it.
- **X – Hunter's Fury (Ultimate, 8 pts)**: Fire up to three wall-penetrating energy blasts across the entire map; each blast deals heavy damage and tags enemies hit.

#### Breach
- **C – Aftershock**: Send a burst of ground-moving explosive through walls on a brief delay.
- **Q – Flashpoint**: Charge a wall-penetrating flash through a surface; all players looking at the surface on the other side are blinded.
- **E – Fault Line (Signature)**: Send a seismic pulse forward through walls; all enemies in its path are dazed (vision disrupted/slowed).
- **X – Rolling Thunder (Ultimate, 8 pts)**: Trigger a cascading seismic push that travels in a cone, dazing and knocking back all enemies hit.

#### Skye
- **C – Regrowth**: Channel to heal nearby allies (not yourself). Holds a rechargeable pool of healing.
- **Q – Trailblazer**: Control a Tasmanian tiger that can charge and concuss enemies; damages and concusses on hit.
- **E – Guiding Light (Signature)**: Throw a hawk that you can steer; activate to transform it into a flash. Recharges on 1 kill.
- **X – Seekers (Ultimate, 7 pts)**: Release three seekers that track down the three nearest enemies, near-sighting them on contact.

#### KAY/O
- **C – FRAG/ment**: Throw an explosive fragment that bounces off surfaces and detonates repeatedly on the final bounce, dealing damage.
- **Q – FLASH/drive**: Throw a flash grenade (can be cooked) that blinds players looking at it on detonation.
- **E – ZERO/point (Signature)**: Throw a suppression blade that sticks to surfaces and pulses; enemies caught in its range have all abilities suppressed for a duration.
- **X – NULL/cmd (Ultimate, 8 pts)**: Emit an energy pulse suppressing all enemies in range (suppressed enemies cannot use abilities). While active KAY/O is also overloaded and cannot die (goes into an injured state that allies can revive).

#### Fade
- **C – Prowler**: Send a prowler that can be steered to chase enemies; on contact it nearsights them.
- **Q – Seize**: Throw a canister that releases a sphere of nightmare energy; enemies caught are tethered, deafened, and then decay.
- **E – Haunt (Signature)**: Throw a creature that lands and surveys the area, revealing enemies in its range with a trail that remains for the duration. Can be destroyed.
- **X – Nightfall (Ultimate, 8 pts)**: Send a wave of nightmare energy across the full map; enemies hit are marked, deafened, and decay.

#### Gekko
- **C – Mosh Pit**: Throw Mosh, who explodes after a delay dealing damage in a wide area (alternative: holds spike for a delay detonation).
- **Q – Dizzy**: Launch Dizzy who bounces off walls; enemies hit directly in his path are blinded.
- **E – Wingman (Signature)**: Send Wingman to clear a site, deal a burst hit to enemies, or even plant/defuse the spike. Recharges on 1 kill.
- **X – Thrash (Ultimate, 7 pts)**: Link with Thrash to pilot it and detain any enemy it lunges and catches; the detained enemy is immobilized briefly.

Unique mechanic: Mosh, Dizzy, and Thrash can be **recollected** after use, returning a portion of their charge.

#### Tejo (Agent 27, released early 2025)
- **C – Stealth Drone**: Deploy a drone with a dart that can be fired at enemies; tagged enemies are revealed.
- **Q – Special Delivery**: Hold to aim; throw a sticky grenade that adheres to surfaces and concusses enemies after a delay.
- **E – Guided Salvo (Signature)**: Fire guided missiles at two designated targets on the map (one or two can be selected).
- **X – Armageddon (Ultimate, 8 pts)**: Launch a devastating airstrike across a large diagonal strip of the map, dealing massive damage to all enemies in the zone.

---

### CONTROLLERS (7 agents)

Role: smoke and vision-denial agents who shape the map, block sightlines, and slow rotations.

#### Brimstone
- **C – Stim Beacon**: Throw a Stim Beacon that creates a zone granting allies Rapid Fire (increased fire rate) inside.
- **Q – Incendiary**: Launch an incendiary grenade that sets the ground on fire, dealing damage over time.
- **E – Sky Smoke (Signature)**: Use a map targeting tablet to call in long-lasting smoke grenades at selected locations (up to 3 simultaneously).
- **X – Orbital Strike (Ultimate, 7 pts)**: Use a targeting laser to mark a location; an orbital strike bombards that location continuously, dealing massive damage.

#### Viper
- **C – Snake Bite**: Fire an acidic canister that breaks on the ground, creating a pool of corrosive acid that damages and applies Fragile to enemies.
- **Q – Poison Cloud**: Throw a gas emitter; activate/deactivate it to create a cloud of toxic gas that nearsights and decays enemies inside.
- **E – Toxic Screen (Signature)**: Place a line of emitters across the map; activate to create a tall wall of toxic gas.
- **X – Viper's Pit (Ultimate, 8 pts)**: Spray a massive cloud of toxic gas that covers a large area; Viper and her pit persist — she can see enemies who enter as skull markers. Enemies inside are heavily decayed. Pit dissipates if Viper leaves it.

#### Omen
- **C – Shrouded Step**: Set a destination and teleport there (short range).
- **Q – Paranoia**: Send a shadow orb forward that passes through walls and temporarily nearsights all enemies it hits.
- **E – Dark Cover (Signature)**: Summon and throw a shadow orb that obscures vision (long-lasting smoke). Can be curved and placed anywhere on map during Astral-like preview.
- **X – From the Shadows (Ultimate, 7 pts)**: Choose any location on the map and teleport there after a cast animation (can be canceled mid-cast).

#### Astra
- **C – Gravity Well**: Place a star on the map; activate to create a gravity well that pulls enemies toward the center, then explodes.
- **Q – Nova Pulse**: Place a star on the map; activate to detonate it, concussing all players in the area.
- **E – Nebula / Dissipate (Signature)**: Place a star that becomes a smoke (Nebula). Can recall it as Dissipate — briefly showing a fake smoke before disappearing.
- **X – Astral Form / Cosmic Divide (Ultimate, 8 pts)**: Enter Astral Form to place stars anywhere on the map. Ultimate: create a massive infinite-length barrier wall that blocks bullets and heavily dampens audio through it.

#### Harbor (Post-rework, Patch 11.10, late 2025)
*Note: Cascade was removed and replaced by Storm Surge in this rework.*
- **C – High Tide** (300 creds, now purchasable — no longer signature): Create a long wall of water that slows any player passing through it.
- **Q – Storm Surge (New ability)**: Throw an explosive device that creates a whirlpool after a brief delay; nearsights and slows enemies caught in it.
- **E – Cove (Now the Signature)**: Remotely place a sphere of shielding water (acts like a smoke); reactivate to shield it, making it bulletproof.
- **X – Reckoning (Ultimate, 8 pts)**: Unleash a surge of water that barrels forward in a cone, nearsighting and slowing all enemies hit. Significantly more directional than the previous geyser version.

#### Clove (Agent 25, released 2024)
- **C – Pick-Me-Up**: Activate after getting a kill or assist to gain a burst of health (overheal) for a limited duration.
- **Q – Meddle**: Throw a fragment that decays a specific target area; enemies inside take decay damage.
- **E – Ruse (Signature)**: Deploy smokes at selected map locations. Unique: can be used **after death** for a limited window.
- **X – Not Dead Yet (Ultimate, 6 pts)**: After dying, activate the ultimate to be **revived at a random nearby location** with some health. All smokes and abilities persist during the revive window.

Note: Clove is the only agent who can use abilities after death and self-revive.

#### Miks (Agent 30, released March 18, 2026 — Season 2026 Act 2)
- **C – M-Pulse** (250 creds, 2 charges): Throw a dual-mode sonic device; ALT-FIRE toggles between **Concuss** output (stuns enemies hit by waves) and **Healing** output (restores health to teammates in range). FIRE to throw.
- **Q – Harmonize** (200 creds, 1 charge): Target an ally and FIRE to grant both yourself and the ally a **Combat Stim** that refreshes on each kill. ALT-FIRE to self-cast only.
- **E – Waveform (Signature)**: Equip a map targeter. FIRE to set locations. ALT-FIRE to spawn smokes at all selected locations simultaneously. 2 charges, 40-second cooldown, 100 creds (1 free per round).
- **X – Bassquake (Ultimate, 8 pts)**: Charge then unleash Sonic Radiance forward in a cone — knocks back, **Deafens**, and **Slows** all players hit.

Note: Miks is the first Controller with team-healing capability (via M-Pulse healing mode). The Combat Stim from Harmonize refreshes on kills, rewarding aggressive play.

---

### SENTINELS (7 agents)

Role: defensive anchors who hold space, watch flanks, and punish opponents for rushing into utility.

#### Sage
- **C – Barrier Orb**: Summon a large wall of ice that blocks movement and LoS; teammates can break it from their side.
- **Q – Slow Orb**: Throw an orb that shatters on ground impact, creating a field of slowing crystals.
- **E – Healing Orb (Signature)**: Heal a targeted ally or yourself over a brief channel.
- **X – Resurrection (Ultimate, 8 pts)**: Target a dead ally and revive them with partial health.

#### Cypher
- **C – Trapwire**: Place a stealthy tripwire between two walls; triggered wire reveals and shortly roots the enemy.
- **Q – Cyber Cage**: Throw a remote-activated cage that creates a vision-blocking and sound-masking zone.
- **E – Spycam (Signature)**: Place a concealed camera; view it remotely and fire tracking darts from it.
- **X – Neural Theft (Ultimate, 7 pts)**: Use on a dead enemy body to reveal all living enemies' locations once.

#### Killjoy
- **C – Nanoswarm**: Throw a grenade that lies dormant until activated; detonates in a small, high-damage swarm.
- **Q – ALARMBOT**: Deploy a bot that hunts nearby enemies, alerting and applying Vulnerable (increased damage) when it reaches them.
- **E – TURRET (Signature)**: Deploy a turret that fires at enemies in its 180° cone.
- **X – Lockdown (Ultimate, 8 pts)**: Deploy a device; after a long wind-up, it detains all enemies in a massive radius.

#### Chamber
- **C – Trademark**: Place a trap that slows and damages the first enemy who enters its range.
- **Q – Headhunter**: Equip a high-powered pistol; tap or hold to aim and fire precise shots (headshots instantly kill).
- **E – Rendezvous (Signature)**: Place two teleport anchors; while standing near one, immediately teleport to the other.
- **X – Tour De Force (Ultimate, 8 pts)**: Summon a powerful sniper rifle; direct kills create a slowing zone at the victim's position.

#### Deadlock
- **C – GravNet**: Throw a grenade that forces all caught enemies to crouch and be vulnerable briefly.
- **Q – Sonic Sensor**: Deploy a sensor that triggers on nearby sounds (footsteps/gunfire), stunning enemies in range.
- **E – Barrier Mesh (Signature)**: Throw a disk that creates impassable walls extending outward.
- **X – Annihilation (Ultimate, 8 pts)**: Fire a pulse of nanowires that cocoon the first enemy hit, dragging them toward the team's side; the cocooned enemy dies if they reach the edge.

#### Vyse (Agent 26, released 2024)
- **C – Razorvine**: Throw a device that creates a patch of slowing, damaging metal brambles on the ground.
- **Q – Shear**: Place a wall trap under the ground; when an enemy triggers it, a wall of metal spikes erupts to block their path.
- **E – Arc Rose (Signature)**: Place a wall-mounted flash device that flashes all enemies who trigger it. Recharges on 2 kills.
- **X – Steel Garden (Ultimate, 7 pts)**: Deploy a pulse that **jams all enemy weapons** in a large area for a duration — enemies cannot fire.

#### Veto (Agent 29, released October 2025)
- **C – Crosscut**: Place a vortex anchor on the ground; while in range and line of sight of it, reactivate to teleport to it instantly (no range limit mentioned in some sources; has a visual animation delay).
- **Q – Chokehold**: Throw a viscous fragment that becomes a proximity trap; when triggered it tethers, decays, and deafens nearby enemies.
- **E – Interceptor (Signature)**: Deploy an active interceptor that **destroys any physical enemy utility** in line of sight (grenades, drones, breakable walls like Sage/Deadlock, projectile recon tools). Cannot destroy smokes. Can be destroyed by gunfire or blocked by smokes.
- **X – Evolution (Ultimate, cost TBC)**: Enter a supercharged state with increased fire rate, health regeneration, and **full immunity to all debuffs** (cannot be flashed, stunned, slowed, decayed, or damaged by explosions). Only direct weapon damage and ability-based weapons can eliminate Veto in this state.

Note: Veto is uniquely designed as a **utility-counter** Sentinel — his Interceptor E is the most aggressive anti-equipment tool in the game, countering heavy utility-dependent agents (Sova, Cypher, Deadlock, Killjoy, Tejo).

---

## Concrete Techniques/Params We Should Adopt for Ultron 1.0

### 1. Compact kit injection format
Inject the roster as a compact reference block in the LLM system prompt. Suggested format (all 29 agents, ~870 tokens):

```
# VALORANT AGENT KITS (June 2026)
## Duelists
Jett: C=Cloudburst(smoke), Q=Updraft(jump), E=Tailwind(dash/sig), X=Blade Storm(knives ult)
Phoenix: C=Blaze(firewall), Q=Hot Hands(fireball), E=Curveball(flash/sig), X=Run it Back(respawn ult)
Raze: C=Boom Bot(bot), Q=Blast Pack(explosive), E=Paint Shells(cluster/sig), X=Showstopper(rocket ult)
Reyna: C=Leer(nearsight), Q=Devour(heal), E=Dismiss(invuln/sig), X=Empress(frenzy ult)
Neon: C=Fast Lane(walls), Q=Relay Bolt(concuss), E=High Gear(sprint/sig), X=Overdrive(beam ult)
Yoru: C=Fakeout(decoy), Q=Blindside(flash), E=Gatecrash(teleport/sig), X=Dimensional Drift(invis ult)
Iso: C=Contingency(wall), Q=Undercut(fragile), E=Double Tap(shield/sig), X=Kill Contract(1v1 ult)
Waylay: C=Saturate(hinder AoE), Q=Light Speed(double dash), E=Refract(beacon teleport/sig), X=Convergent Paths(hinder zone ult)

## Initiators
Sova: C=Owl Drone, Q=Shock Bolt, E=Recon Bolt(scan/sig), X=Hunter's Fury(3-arrow ult)
Breach: C=Aftershock(through-wall burst), Q=Flashpoint(through-wall flash), E=Fault Line(daze/sig), X=Rolling Thunder(quake ult)
Skye: C=Regrowth(heal), Q=Trailblazer(tiger), E=Guiding Light(hawk flash/sig), X=Seekers(tracking ult)
KAY/O: C=FRAG/ment(explosive), Q=FLASH/drive(flash), E=ZERO/point(suppress/sig), X=NULL/cmd(suppress+overload ult)
Fade: C=Prowler(nearsight), Q=Seize(tether+decay), E=Haunt(reveal/sig), X=Nightfall(mark+decay ult)
Gekko: C=Mosh Pit(AoE explosion), Q=Dizzy(blind), E=Wingman(site clear/sig), X=Thrash(detain ult)
Tejo: C=Stealth Drone, Q=Special Delivery(sticky concuss), E=Guided Salvo(missiles/sig), X=Armageddon(airstrike ult)

## Controllers
Brimstone: C=Stim Beacon(rapidfire), Q=Incendiary(fire), E=Sky Smoke(3 smokes/sig), X=Orbital Strike(ult)
Viper: C=Snake Bite(acid), Q=Poison Cloud(gas emitter), E=Toxic Screen(wall/sig), X=Viper's Pit(pit ult)
Omen: C=Shrouded Step(teleport), Q=Paranoia(nearsight), E=Dark Cover(smoke/sig), X=From the Shadows(global TP ult)
Astra: C=Gravity Well(pull), Q=Nova Pulse(concuss), E=Nebula/Dissipate(smoke/sig), X=Cosmic Divide(wall ult)
Harbor: C=High Tide(slow wall), Q=Storm Surge(whirlpool nearsight), E=Cove(water smoke/sig), X=Reckoning(surge ult)
Clove: C=Pick-Me-Up(overheal), Q=Meddle(decay), E=Ruse(smokes/sig - usable after death), X=Not Dead Yet(self-revive ult)
Miks: C=M-Pulse(concuss OR heal waves), Q=Harmonize(combat stim ally), E=Waveform(map smokes/sig), X=Bassquake(knockback+deafen+slow ult)

## Sentinels
Sage: C=Barrier Orb(ice wall), Q=Slow Orb(slow field), E=Healing Orb(heal/sig), X=Resurrection(revive ult)
Cypher: C=Trapwire(trip), Q=Cyber Cage(vision block), E=Spycam(camera/sig), X=Neural Theft(reveal ult)
Killjoy: C=Nanoswarm(damage field), Q=ALARMBOT(detect bot), E=TURRET(auto-turret/sig), X=Lockdown(detain ult)
Chamber: C=Trademark(slow trap), Q=Headhunter(pistol), E=Rendezvous(teleport/sig), X=Tour De Force(sniper ult)
Deadlock: C=GravNet(force-crouch), Q=Sonic Sensor(sound stun), E=Barrier Mesh(wall/sig), X=Annihilation(cocoon ult)
Vyse: C=Razorvine(slow+dmg), Q=Shear(spike wall trap), E=Arc Rose(wall flash/sig), X=Steel Garden(weapon jam ult)
Veto: C=Crosscut(teleport anchor), Q=Chokehold(tether+decay trap), E=Interceptor(destroys enemy util/sig), X=Evolution(debuff immunity+regen ult)
```

### 2. RAG retrieval for detailed ability questions
For PRIVATE_REPLY responses to questions like "what does X agent's ability do?", pull the full-text description from this doc (or a derivative). This keeps full-detail descriptions OUT of the base system prompt to save tokens, while still being accessible when needed.

### 3. Relay path: agent name normalization
The existing RapidFuzz + Metaphone lexical layer should handle ASR mishears of agent names. Known ASR hazards:
- "Sova" → "Sofa", "Nova"
- "Omen" → "Owen", "Oh man"
- "Tejo" → "Techo", "Teco"  
- "Veto" → "Vito", "Veta"
- "Miks" → "Mix", "Mics", "Nix"
- "Waylay" → "Way-lay", "Wayla", "Relay"
- "KAY/O" → "Kayo", "K-O", "Kayno"
- "Gekko" → "Gecko", "Geko"
- "Clove" → (usually clean)

The existing Metaphone+RapidFuzz layer in `_common_words.py` / the relay slot parser should handle these already. Update the agent gazetteer to include Waylay, Veto, Miks with their ASR variants.

### 4. Ability name normalization
Players often say ability slang rather than official names:
- "Sova bolt/arrow/scan" = Recon Bolt (E)
- "Jett dash" = Tailwind (E)
- "Jett smokes" = Cloudburst (C)
- "Killjoy ult/lockdown" = Lockdown (X)
- "Sage wall" = Barrier Orb (C)
- "Omen smoke" = Dark Cover (E)
- "Raze nade/satchel" = Paint Shells (E) / Blast Pack (Q)
- "Reyna orbs" = Devour/Dismiss souls
- "Viper wall" = Toxic Screen (E)
- "Cypher cam" = Spycam (E)
- "Harbor wall" = High Tide (C) — note: post-rework it's now a purchasable, not signature
- "Veto util-destroy/interceptor" = E

---

## Risks/Caveats for Our Constraints

### Accuracy risk: Kit changes are frequent
Valorant patches regularly modify ability mechanics, costs, and even replaces abilities (Harbor's Cascade→Storm Surge is a recent example). The kit data above is accurate as of June 2026 (Patch 12.x, Season 2026 Act 2). A new agent or significant rework could render injected context stale within a patch cycle (~3 weeks).

**Mitigation:** Version-stamp the injected context block; flag with `# VALORANT KITS v2026-06-20`. Consider a lightweight update script that re-fetches from a wiki API.

### Token cost risk
The compact format above (all 29 agents) costs ~870-1000 tokens in the system prompt. At Q5_K_M 8B with a 32k context, this is acceptable — approximately 2.7-3.1% of total context — but adds to base prompt overhead. If verbosity mode is "LOW" (snap path), consider skipping the full roster and only injecting the queried agent's kit on demand via retrieval.

### Hallucination risk: Ability EFFECT confusion
Even with correct names injected, the 8B LLM may confuse which agent has which mechanic (e.g., conflating Veto's Interceptor with KAY/O's ZERO/point — both suppress/destroy utility). The compact format mitigates name confusion; for deep ability questions, RAG the full description section above.

### New-agent blind spots
The LLM (Qwen3-8B, training data through ~late 2024) may have seen Vyse, Tejo, and Clove in pre-release coverage but is unlikely to have clean kit knowledge of Waylay (March 2025), Veto (October 2025), or Miks (March 2026). These three agents **must** be injected — the model will hallucinate their kits if not grounded.

### Anticheat safety
Kit injection is purely text in the LLM system prompt. Zero import risk. The relay path does not consume this — only the PRIVATE_REPLY and LLM-routed paths do. Safe.

### Harbor rework confusion
Both old and new Harbor kits appear in training data. The model may default to the old kit (Cascade + Cove as signature). Inject the reworked kit explicitly and label it `# Harbor (post-rework, Patch 11.10)`.

---

## Sources

1. **ValoHub — Agents list 2026 (roles + ability names):** https://valohub.co/agents
2. **The Spike GG — Valorant agents list (26 agents, ability descriptions):** https://www.thespike.gg/valorant/agents
3. **Beebom — All Valorant agents abilities (26 agents, slot-by-slot descriptions):** https://beebom.com/valorant-characters-agents-abilities/
4. **ProSettings — Waylay abilities breakdown:** https://prosettings.net/blog/valorant-waylay/
5. **ProSettings — Veto abilities breakdown:** https://prosettings.net/blog/valorant-veto-new-agent/
6. **The Spike GG — Miks abilities reveal (Act 2 2026):** https://www.thespike.gg/valorant/news/valorant-agent-miks-all-abilities/7762
7. **Beebom — Miks guide (Act 2 2026):** https://beebom.com/valorant-miks-guide/
8. **Liquipedia — Miks kit with costs:** https://liquipedia.net/valorant/Miks
9. **GameLeap — Waylay abilities detail:** https://www.gameleap.com/articles/valorant-new-agent-waylay-all-abilities
10. **Esports.gg — Veto agent abilities:** https://egamersworld.com/blog/new-valorant-agent-veto-details-abilities-role-rel-QHBZcpqZHn
11. **Esports.gg — Harbor rework Patch 11.10 patch notes:** https://esports.gg/news/valorant/valorant-patch-notes-11-10/
12. **Shane the Gamer — Patch 11.10 Harbor rework summary:** https://www.shanethegamer.com/esports-news/valorant-patch-11-10-harbor-rework-update/
13. **Fragster — Valorant characters complete list:** https://www.fragster.com/valorant-characters-list-all-agents-by-role-and-release-order/
14. **GameRiv — Harbor rework full ability breakdown:** https://gameriv.com/valorant-harbor-rework-full-ability-overhaul-release-date-tactical-breakdown/
15. **Sportskeeda — Miks abilities explored:** https://www.sportskeeda.com/valorant/valorant-miks-abilities-new-agent-explored
