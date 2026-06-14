ITEMS = [
    # =========================================================================
    # DUELISTS
    # =========================================================================

    # --- Jett: Cloudburst (C) ---
    "our Jett used her cloudburst to cross A main, the smoke is hers not theirs",
    "their Jett threw a cloudburst at heaven, her own personal smoke, push before it fades",
    "our Jett has both cloudbursts left, she can self-smoke the op angle twice",
    "their Jett deployed cloudburst in the doorway, that is her smoke covering her peek",
    "tell them our Jett curved her cloudburst around the corner at A short, cross behind it",
    "their Jett has no cloudbursts remaining, she has zero self-smoke for the rest of the round",

    # --- Jett: Updraft (Q) ---
    "our Jett updrafted to the box on B site, she has the high angle, she is up there",
    "their Jett used updraft to reach catwalk roof, one charge gone, she has one left",
    "tell the team their Jett double-updrafted to the rafters, both charges spent, she is on top",
    "our Jett used her last updraft on the ascend, no more elevation plays from her this round",
    "their Jett updrafted behind our smoke, she has the aerial angle, shoot upward",

    # --- Jett: Tailwind (E) ---
    "our Jett burned her tailwind on that retreat, she has no dash left this round",
    "their Jett dashed into the smoke, dash is now spent, she cannot escape a second peek",
    "tell them our Jett still has her tailwind saved, she can dash out of any bad trade",
    "their Jett has tailwind ready, she will dash through mid and peek op angle",
    "our Jett just dashed through and got the frag, her tailwind recharged on that kill",
    "tell my team their Jett used tailwind on the entry peek, no more dashes, push her now",

    # --- Jett: Blade Storm (X) ---
    "their Jett has blade storm ult up, she will knife-op the angle without needing to buy a gun",
    "our Jett activated blade storm this round, she has eight ultimate points spent on those knives",
    "tell them their Jett used blade storm, both knives and fan throw, ult is now fully spent",
    "our Jett has blade storm ready, let her entry on ult so she does not risk her rifle",
    "their Jett is running blade storm, alt-fire fan throw coming, watch the cluster",
    "tell my team their Jett blade storm ult is active, knives recharge on each kill she gets",

    # --- Reyna: Leer (C) ---
    "their Reyna threw a leer eyeball through the smoke, do not look at it or you lose all vision",
    "our Reyna leer is in the air toward mid, look away from the eye right now",
    "tell them our Reyna placed both leer charges through the wall, shoot the eyes fast",
    "their Reyna leer is floating at A main, shoot it before it nearsights you",
    "our Reyna has two leer charges left, she can nearsight both angles before the push",

    # --- Reyna: Devour (Q) ---
    "their Reyna devoured a soul orb after that kill, she healed back to full HP",
    "our Reyna is devouring the orb right now, she is healing herself mid-fight",
    "tell them their Reyna has no soul orbs to devour, she cannot self-heal this fight",
    "our Reyna overhealed to one-fifty using devour, she has fifty bonus HP right now",
    "their Reyna devoured two orbs already this round, she is unkillable while she has kills",

    # --- Reyna: Dismiss (E) ---
    "their Reyna dismissed after taking damage, she went intangible, do not shoot at her",
    "our Reyna dismissed during empress, she is invisible and repositioning right now",
    "tell them their Reyna dismissed into the smoke, she is intangible for one and a half seconds",
    "our Reyna has no soul orbs so she cannot dismiss, she is stuck in this fight",
    "their Reyna during empress auto-dismissed and vanished into the flank position",

    # --- Reyna: Empress (X) ---
    "their Reyna popped empress, she gets faster fire rate reload and equip, play safe until she stops killing",
    "our Reyna has empress ready with six ultimate points, we execute when she goes in first",
    "tell them their empress is active and she just got the first kill, the timer refreshed",
    "their Reyna empress faded without a kill, she wasted her ult this round",
    "our Reyna has empress active, infinite devour and dismiss while she keeps getting kills",
    "tell my team their Reyna is in empress right now, she auto-heals on every kill without consuming orbs",

    # --- Raze: Boom Bot (C) ---
    "their Raze sent a boom bot rolling down mid, it has one hundred HP, shoot it before it locks on",
    "our Raze deployed boom bot at A main, it is tracking someone, they are near A lobby",
    "tell them their boom bot locked onto our initiator, explosive incoming, dodge it",
    "our Raze boom bot got destroyed, intel gathered, one enemy at B long from the audio",
    "their Raze boom bot is hunting at B site, it will explode on contact with the first person it finds",

    # --- Raze: Blast Pack (Q) ---
    "their Raze used one blast pack to rocket-jump to box, she still has one charge left",
    "our Raze self-detonated both blast packs to reach the rafters, no satchels remaining",
    "tell them our Raze is launching with blast pack right now, she is airborne at A lobby",
    "their Raze has two blast packs ready, she can double-boost through mid to get elevation",
    "our Raze threw a blast pack on the enemy, detonating to knockback, not for mobility",

    # --- Raze: Paint Shells (E) ---
    "their Raze threw paint shells at B main, cluster grenade splitting into four sub-munitions",
    "our Raze paint shells landed at A elbow, four grenades spreading unpredictably in the corridor",
    "tell them their Raze has no paint shells left, two kills needed to recharge the grenade",
    "our Raze paint shells cleared the corner, cluster grenade detonated, A main is open",
    "their Raze just threw paint shells and the clusters got two of them at once",

    # --- Raze: Showstopper (X) ---
    "their Raze has showstopper ult up, eight ultimate points, rocket launcher ready",
    "our Raze fired showstopper into B site, the rocket is in the air right now, dodge it",
    "tell them their Raze showstopper is active, she will rocket the entry point, do not stack",
    "their Raze showstopper connected on the plant, direct hit, it is essentially a one-shot kill",
    "our Raze has no showstopper this round, she spent it last fight, ult is completely gone",

    # --- Phoenix: Blaze (C) ---
    "their Phoenix cast blaze wall at A elbow, he is healing inside his own fire wall",
    "our Phoenix blaze wall is up at B door, he is healing while holding the angle",
    "tell them their Phoenix is standing in his blaze right now, he is recovering HP mid-fight",
    "our Phoenix has blaze left, one curving fire wall he can use to block sightlines",
    "their Phoenix blaze curved around the corner, he blocked our sightline and healed simultaneously",

    # --- Phoenix: Hot Hands (Q) ---
    "their Phoenix hot hands is on the spike, he is healing inside the fire zone while it blocks our defuse",
    "our Phoenix threw hot hands on A main, the fire zone damages enemies for seven seconds",
    "tell them their Phoenix hot hands zone at B default heals him and damages us, do not step in",
    "our Phoenix has hot hands left, one fireball charge to zone an angle or self-heal",
    "their Phoenix alt-fired hot hands for a lob trajectory over the boxes",

    # --- Phoenix: Curveball (E) ---
    "their Phoenix curved his flash left from CT, left-click curveball popped around the corner",
    "our Phoenix has two curveballs ready, both flash charges available for the double-flash execute",
    "tell them our Phoenix flashed right-side with alt-fire curveball, everyone on the right look away",
    "their Phoenix used both curveballs, out of flashes for the rest of this round",
    "our Phoenix has one curveball left after burning the first one on the peekers",

    # --- Phoenix: Run it Back (X) ---
    "their Phoenix activated run it back, he placed the marker at CT, if he dies he respawns there",
    "our Phoenix has run it back ult up with six points, let him entry and take risks",
    "tell them their Phoenix ult died with him before the timer expired, no respawn this time",
    "their Phoenix ult ran out without a respawn, the ten seconds passed, he is actually dead",
    "our Phoenix run it back marker is at tree on A, he will come back there at full HP if he dies",
    "tell my team their Phoenix is inside run it back right now, clock him before the timer expires",

    # --- Yoru: Fakeout (C) ---
    "their Yoru sent fakeout footsteps running toward A, ignore the audio, they are on B",
    "our Yoru triggered a dormant fakeout echo, it is now running toward their position",
    "tell them their Yoru fakeout clone got shot by them, blind detonation is going off at that position",
    "our Yoru placed two fakeout echoes, one at A lobby and one at mid, for misdirection",
    "their Yoru alt-fired fakeout to place it dormant at CT, he will trigger it later",

    # --- Yoru: Blindside (Q) ---
    "their Yoru blindside bounced off the first wall and is about to pop, look away now",
    "our Yoru has two blindsides ready, both flash charges for the double-bounce execute",
    "tell them their Yoru threw blindside, it bounced off the mid wall, detonating in zero-point-six seconds",
    "our Yoru has no blindsides left this round, both dimensional flashes are consumed",
    "their Yoru blindside is in the air, zero-point-six second windup after the bounce, brace",

    # --- Yoru: Gatecrash (E) ---
    "their Yoru deployed a gatecrash tether at B main, shoot the rift before he teleports through",
    "our Yoru teleported to the tether at back site, he is flanking their CT anchor right now",
    "tell them their Yoru triggered a fake teleport audio, he did not actually move, do not rotate",
    "our Yoru has gatecrash on cooldown, no teleport available for thirty seconds",
    "their Yoru set a stationary tether at mid, it reveals enemies within four meters of the rift",
    "our Yoru has both gatecrash charges, he can send and teleport to two different positions this round",

    # --- Yoru: Dimensional Drift (X) ---
    "their Yoru activated dimensional drift, he is invisible and roaming for ten seconds",
    "our Yoru has dimensional drift ult up, eight ultimate points, he is scouting while invisible",
    "tell them their Yoru is inside dimensional drift right now, cannot shoot him, he is gathering info",
    "their Yoru is about to exit dimensional drift, flash warning will play, hold your crosshair",
    "our Yoru used dimensional drift to walk through the middle of their stack undetected",

    # --- Neon: Fast Lane (C) ---
    "our Neon deployed fast lane, two electric walls running through mid, cross between them",
    "their Neon placed fast lane walls across B main, those walls damage anyone walking through",
    "tell them our Neon fast lane is up, three hundred credits, the twin static walls block vision",
    "their Neon has no fast lane left, she cannot split the site this round",
    "our Neon fast lane covers the A main cross, move through the corridor between the two walls",

    # --- Neon: Relay Bolt (Q) ---
    "their Neon relay bolt bounced off mid wall and hit two of us, we are stunned for three seconds",
    "our Neon relay bolt is bouncing, both contact points produce the concussive stun",
    "tell them our Neon relay bolt hit B lobby, two enemies concussed, push immediately",
    "their Neon relay bolt got one person at CT, three second stun, go get the angle",
    "our Neon has relay bolt ready, she can stun around the corner before the peek",

    # --- Neon: High Gear (E) ---
    "their Neon activated high gear and is sprinting through B main right now, do not chase her",
    "our Neon is in high gear sprint, she is significantly faster than anyone else on the map",
    "tell them their Neon slid in on high gear, slide charge used, she needs a kill to reset it",
    "our Neon slide reset on the kill, she has another slide charge this round",
    "their Neon has no high gear left this round, she burned it on the mid peek",

    # --- Neon: Overdrive (X) ---
    "their Neon popped overdrive ult, do not peek her straight on, she beams while sprinting",
    "our Neon has overdrive ready, seven ultimate points, she goes in first and beams everything",
    "tell them their Neon overdrive timer reset on the kill, the beam goes on indefinitely while she kills",
    "their Neon overdrive ran out, she got zero kills and the ten seconds expired",
    "our Neon overdrive is active, lightning beam has zero spread while she moves, play off angles",

    # --- Iso: Contingency (C) ---
    "their Iso cast contingency wall, that is an indestructible bullet-blocking energy wall",
    "our Iso contingency wall is moving forward at B main, cover behind it, nothing penetrates it",
    "tell them their Iso contingency blocks both bullets and vision, unlike Sage wall which only blocks bodies",
    "our Iso has contingency left, one wall charge to block the op angle",
    "their Iso used contingency to push through mid, the wall protected him from all operator shots",

    # --- Iso: Undercut (Q) ---
    "their Iso threw undercut through the wall, the molecular bolt passed through terrain and hit two of us",
    "our Iso undercut suppressed their Killjoy, her nanoswarms and turret are all offline for four seconds",
    "tell them our Iso undercut hit the Jett, she is fragile and suppressed, double damage and no dash",
    "their Iso undercut hit our initiator, he is fragile right now, trade him immediately",
    "our Iso has undercut left, one bolt that passes through surfaces to suppress and fragile the target",

    # --- Iso: Double Tap (E) ---
    "our Iso activated double tap, he is in flow state, a kill generates the shield orb above the body",
    "their Iso shot the double tap orb above the dead enemy, he now has a one-shot-absorbing shield",
    "tell them our Iso double tap shield blocked the op shot, one damage instance absorbed",
    "their Iso has double tap ready, two kills recharge it, he can get a shield every fight",
    "our Iso has no double tap this round, he spent the two kills needed and activated it already",

    # --- Iso: Kill Contract (X) ---
    "their Iso fired kill contract, he pulled our Jett into the arena, one-versus-one is happening now",
    "our Iso has kill contract ult up, seven ultimate points, he can pull anyone into a private duel",
    "tell them their Iso is inside kill contract right now, if he wins he comes back at one hundred HP",
    "our Iso lost the kill contract duel, he is dead inside the arena, we are in a four-versus-five",
    "their Iso kill contract started with double tap active post-patch, he already has the shield in there",

    # --- Waylay: Saturate (C) ---
    "their Waylay threw saturate onto B main, enemies in that zone are hindered, fire rate reduced",
    "our Waylay saturate is on the ground at A lobby, the hinder slows movement fire rate equip and reload",
    "tell them their Waylay saturate does not blind, it only hinders, you can see but you are slowed",
    "our Waylay has saturate left, one cluster of light to hinder the defenders on site",
    "their Waylay saturate zone is still active at mid, do not push through until it expires",

    # --- Waylay: Lightspeed (Q) ---
    "their Waylay used lightspeed, both dashes fired in sequence, first one went upward for elevation",
    "our Waylay dashed twice with lightspeed, both charges consumed, no more dashes this round",
    "tell them their Waylay used alt-fire lightspeed for a single dash, she still has one dash left",
    "our Waylay has lightspeed ready, two dashes as a sequence, the first can go upward",
    "their Waylay double-dashed through mid, she has no mobility until next round",

    # --- Waylay: Refract (E) ---
    "their Waylay placed a refract beacon at CT before peeking, she will recall back to it if she gets hit",
    "our Waylay recalled to her refract beacon, she is invulnerable during the transit",
    "tell them shoot the Waylay refract beacon, it is visible on the ground, destroy it to deny her escape",
    "our Waylay beacon is at tree, she peeks the angle and snaps back if the trade is bad",
    "their Waylay reactivated refract and teleported back to the beacon, she escaped",

    # --- Waylay: Convergent Paths (X) ---
    "their Waylay activated convergent paths ult, the afterimage beam is expanding to hinder everyone",
    "our Waylay has convergent paths ready, eight ultimate points, expanding beam plus speed boost",
    "tell them their Waylay ult beam is expanding on B site, everyone in the zone gets hindered",
    "our Waylay ult gave her a speed boost plus the hinder zone on the enemies, push through it",
    "their Waylay convergent paths beam expanding, move out of the expansion area before it locks you",

    # =========================================================================
    # CONTROLLERS
    # =========================================================================

    # --- Brimstone: Stim Beacon (C) ---
    "our Brimstone dropped a stim beacon at the plant point, stand inside it for the fire rate buff",
    "their Brimstone placed a stim beacon at B entry, that thing buffs enemies too if they walk in",
    "tell them our Brimstone stim beacon is active, ten percent faster fire rate reload and equip in the zone",
    "their Brimstone has no stim beacons left this round, no combat stim for their execute",
    "our Brimstone stim is down at plant, stay inside the blue field while planting",

    # --- Brimstone: Incendiary (Q) ---
    "their Brimstone incendiary is on the spike, sixty damage per second, that is their molly on our plant",
    "our Brimstone molly landed at A lobby corner, seven seconds of fire zone flushing that angle",
    "tell them our Brimstone incendiary bounced off the door and landed at CT stairs, wait it out",
    "their Brimstone incendiary damage is real damage not decay, it will actually kill you",
    "our Brimstone has incendiary left, one molly for post-plant or clearing a corner",

    # --- Brimstone: Sky Smoke (E) ---
    "our Brimstone is on the map tablet deploying three sky smokes, he is stationary and vulnerable right now",
    "their Brimstone dropped sky smokes at heaven A and CT, three smokes lasting over nineteen seconds",
    "tell them our Brimstone smokes have the longest duration of any controller, nineteen-point-two-five seconds",
    "their Brimstone has no sky smokes left and he cannot range to the position from here",
    "our Brimstone three smokes are up, execute on drop, hit it now",

    # --- Brimstone: Orbital Strike (X) ---
    "their Brimstone has orbital strike ult, eight ultimate points, five hundred seventy damage over four seconds",
    "our Brimstone is dropping orbital on B spike, do not step into the laser zone",
    "tell them their orbital strike has a two second arrival delay after the laser is called in",
    "our Brimstone orbital cannot hit inside buildings with a ceiling, only open-sky positions",
    "their Brimstone used orbital on the defuse window, nobody can touch the spike for four seconds",

    # --- Viper: Snakebite (C) ---
    "their Viper snakebite landed at B default, the acid zone makes anyone inside vulnerable to double damage",
    "our Viper snakebite is on the spike, six-point-five seconds of vulnerable window, shoot through the acid",
    "tell them their Viper snakebite at A lobby, if you step in you take double damage for two seconds after",
    "our Viper has snakebite left, one acid canister, bounce it off the wall for the around-corner plant denial",
    "their Viper vulnerable window from snakebite is still active, shoot them while they are in the acid",

    # --- Viper: Poison Cloud (Q) ---
    "their Viper activated her poison cloud emitter, it is consuming fuel and blocking vision at A main",
    "our Viper toggled the poison cloud off to conserve fuel, she will toggle it back on when they push",
    "tell them our Viper poison cloud decays enemies inside, ten HP per second cannot kill but floors at one",
    "their Viper emitter is placed at CT, she will toggle the gas on and off based on fuel management",
    "our Viper has her poison cloud emitter placed, she can toggle vision and decay at that position all round",

    # --- Viper: Toxic Screen (E) ---
    "our Viper toxic screen is up splitting mid, she toggled it on, cross now before fuel runs low",
    "their Viper toggled the toxic screen off to regenerate fuel, it will come back up in five seconds",
    "tell them our Viper toxic screen goes through terrain, the emitters spawn across the wall line she aimed at",
    "their Viper toxic screen is cutting A site in two, their wall splits the angle for both teams",
    "our Viper has low fuel from running both cloud and screen simultaneously, one of them will drop",

    # --- Viper: Viper's Pit (X) ---
    "their Viper activated viper's pit, nine ultimate points, that entire site is nearsight and decay now",
    "our Viper has her pit up, she is inside with full vision while enemies are nearsighted around the spike",
    "tell them their Viper just stepped outside her own pit, eight second timer, the cloud collapses if she stays out",
    "their Viper pit collapses, the eight second timer ran out while she was outside, pit is gone",
    "our Viper pit covers the entire B site, decay floors at one HP, she can see enemy outlines inside the cloud",
    "tell my team their Viper returned inside her pit before the timer, it is still active, do not rush in",

    # --- Omen: Shrouded Step (C) ---
    "their Omen shrouded stepped into the B smoke, listen for the teleport audio at the start position",
    "our Omen is channeling a shrouded step, fifteen meter range, one second windup before teleport",
    "tell them their Omen has two shrouded step charges, he can reposition twice this round",
    "our Omen fake-stepped to bait a positional reaction, he did not actually move",
    "their Omen shrouded stepped to the off-angle in the smoke, watch the unexpected position",

    # --- Omen: Paranoia (Q) ---
    "their Omen paranoia passed through the wall and hit two of us, nearsight and deafen for two-and-a-half seconds",
    "our Omen paranoia goes through all terrain, he can blind around corners without exposing himself",
    "tell them their Omen paranoia hits allies too if they stand in its path",
    "our Omen threw paranoia through the mid wall, enemies on the other side are nearsighted",
    "their Omen paranoia is in the air, it is visible, dodge laterally to avoid it",

    # --- Omen: Dark Cover (E) ---
    "their Omen deployed dark cover globally, he can place smokes through walls from anywhere on the map",
    "our Omen set up a one-way dark cover at catwalk, hold through the bottom of the sphere",
    "tell them their Omen dark cover smokes last fifteen seconds, shorter than Brimstone but they recharge",
    "our Omen has two dark cover charges ready, both smokes are off cooldown",
    "their Omen placed a one-way dark cover at mid, the sphere shape allows vision underneath for their team",

    # --- Omen: From the Shadows (X) ---
    "their Omen is from-the-shadows ulting, seven ultimate points, shade appeared at A garden, destroy it",
    "our Omen is teleporting globally, he entered as a shade, enemies can cancel it if they shoot the shade",
    "tell them their Omen shade is visible at B main, shoot the shade to cancel his teleport and waste the ult",
    "their Omen cancelled his from the shadows mid-teleport to fake a rotation",
    "our Omen successfully teleported to the flanking position, shade was not destroyed, he arrived",

    # --- Astra: Gravity Well (C) ---
    "their Astra activated gravity well at B elbow, everyone inside is pulled to center then made vulnerable",
    "our Astra gravity well is pulling enemies off the spike, vulnerable on explosion, shoot them through it",
    "tell them their Astra grav well stars cost one-fifty credits each to place, and then they must be activated",
    "our Astra gravity well yanked two defenders out of their corner positions, they are vulnerable now",
    "their Astra activated grav on our initiator, he got pulled and is now vulnerable to double damage",

    # --- Astra: Nova Pulse (Q) ---
    "their Astra nova pulsed A site, one second charge delay then concuss, three-and-a-half second stun",
    "our Astra is activating nova pulse at B main in two seconds, push immediately after the concuss",
    "tell them their Astra nova pulse charges briefly before detonating, you can see the flash warning",
    "our Astra nova pulse concussed three at CT, they are stunned, execute now",
    "their Astra spent her last nova pulse star at mid, no more stuns from that position this round",

    # --- Astra: Nebula / Dissipate (E) ---
    "their Astra nebula smoke is blocking heaven and CT, fourteen-second duration smoke from pre-placed stars",
    "our Astra dissipated the A star to fake a smoke, it briefly appeared then returned to her inventory",
    "tell them their Astra nebula smoke is shorter than Brimstone, fourteen-point-two-five seconds not nineteen",
    "our Astra is entering astral form to reposition a star, cover her body while she is in astral",
    "their Astra has no stars left, she is in astral getting new placements, she is physically vulnerable",

    # --- Astra: Cosmic Divide (X) ---
    "their Astra has cosmic divide ult, seven ultimate points, infinite height bullet-blocking wall coming",
    "our Astra is dividing A site with cosmic divide, bullets cannot cross and audio is completely blocked",
    "tell them their Astra cosmic divide blocks bullets unlike Viper wall which only blocks vision",
    "our Astra wall is up mid, they cannot hear our audio through the divide, communication severed",
    "their Astra cosmic divide is fading, twenty-one second duration, wall is almost gone",

    # --- Harbor: Storm Surge (C) ---
    "their Harbor threw storm surge, whirlpool landing at B, nearsight and slow on detonation",
    "our Harbor storm surge replaced cascade in the patch eleven-ten rework, it now blinds and slows",
    "tell them their Harbor storm surge has a half-second windup after landing, then the CC activates",
    "our Harbor storm surge hit two at mid, they are nearsighted for two seconds, push now",
    "their Harbor has storm surge left, one whirlpool grenade to nearsight the entry",

    # --- Harbor: High Tide (Q) ---
    "their Harbor deployed high tide, guiding the water wall across A main, sixty meter wall post-patch",
    "our Harbor high tide is up and splitting B, anyone crossing through it gets slowed thirty percent",
    "tell them their Harbor high tide wall slows enemies but does not stop bullets, play angles through it",
    "our Harbor curved the high tide around the corner at B, the water wall is now eight meters tall",
    "their Harbor has high tide left, three hundred credits, one guidable water wall for the split",

    # --- Harbor: Cove (E) ---
    "their Harbor cove bubble is on the spike, he activated the shield, six-eighty HP before bullets break it",
    "our Harbor threw cove then shielded it, they need to break six-eighty HP of shield to shoot through",
    "tell them their Harbor cove without the shield is just a smoke, it only blocks bullets when shielded",
    "our Harbor cove is shielded at the plant position, plant safely inside the bubble",
    "their Harbor cove shield broke, they spent enough bullets on it, now the smoke remains but no bullet block",

    # --- Harbor: Reckoning (X) ---
    "their Harbor fired reckoning ult, forward wave of water pushing through B main, three second nearsight on hit",
    "our Harbor has reckoning with seven ultimate points, the wave moves twenty-five percent faster post-patch",
    "tell them their Harbor can hold reckoning in place after activation by reactivating, seven second stationary wave",
    "our Harbor reckoning wave hit three of them at CT, all three are nearsighted and slowed",
    "their Harbor reckoning forward surge is coming, step perpendicular to the wave to avoid it",

    # --- Clove: Pick-Me-Up (C) ---
    "our Clove activated pick-me-up after damaging that kill, fifty HP overheal and a speed boost",
    "their Clove triggered pick-me-up manually, it does not auto-activate, she gained fifty overheal",
    "tell them their Clove pick-me-up only works on enemies she personally damaged, not team kills",
    "our Clove has fifty temporary overheal from pick-me-up, it decays after ten seconds",
    "their Clove has pick-me-up ready, she can absorb one fight kill and instantly top up fifty HP",

    # --- Clove: Meddle (Q) ---
    "their Clove threw meddle at B site, decay zone erupts after zero-point-seven-five seconds, ninety max HP reduction",
    "our Clove meddle landed at CT, that four meter radius reduces max HP by ninety, one bullet kills them",
    "tell them their Clove meddle radius was nerfed to four meters, smaller zone than before the patch",
    "our Clove meddle hit their initiator, he is decayed to ten max HP, one shot him",
    "their Clove has meddle left, two-fifty credits, decay grenade with ninety HP drain effect",

    # --- Clove: Ruse (E) ---
    "our Clove is smoking two sites from overhead, fourteen second duration while alive",
    "their Clove is dead but she is still deploying ruse smoke, six second duration post-death per the nerf",
    "tell them our Clove can throw ruse smokes after dying, one smoke from the grave per the current patch",
    "their Clove died and is now smoking A from the grave, six second dead smoke, shorter than live duration",
    "our Clove has two ruse charges, she can smoke two positions this round while alive",

    # --- Clove: Not Dead Yet (X) ---
    "their Clove activated not dead yet, eight ultimate points, she revived and has ten seconds to get a kill",
    "our Clove revived with not dead yet, she needs one kill or assist in ten seconds or she dies again",
    "tell them their Clove is reviving right now, she comes back near her death location, kill her again",
    "our Clove revived successfully with an assist, she stays alive for the rest of the round",
    "their Clove failed the not dead yet ult, ten seconds passed with no kill, she auto-died",

    # =========================================================================
    # INITIATORS
    # =========================================================================

    # --- Sova: Owl Drone (C) ---
    "our Sova is piloting the owl drone at A right now, cover his body while he is in drone POV",
    "their Sova fired a marking dart from the owl drone, one of us is tagged and revealed",
    "tell them our Sova drone got shot down, forty HP, one rifle hit kills it, intel is gone",
    "their Sova owl drone buzzed through B main, everyone heard the distinctive audio cue",
    "our Sova marked their Jett through the owl drone dart, she is revealed to the whole team",

    # --- Sova: Shock Bolt (Q) ---
    "their Sova lined up a double-shock on B default, two shock bolts hitting the same spot",
    "our Sova shock bolt is set up at two-bounce two-bar trajectory for A generator lineup",
    "tell them their Sova shock bolt deals one to seventy-five damage depending on proximity",
    "our Sova has two shock bolt charges, both available for post-plant double-tap setup",
    "their Sova alt-fired the shock bolt for two bounces, zero-bounce full-charge for the straight shot",

    # --- Sova: Recon Bolt (E) ---
    "their Sova recon bolt is pinging B site right now, two scans one second apart, we are revealed",
    "our Sova dart hit two enemies at A, they know they are spotted, adjust positions immediately",
    "tell them our Sova recon is destroyable, one HP, enemies will shoot it immediately to deny info",
    "their Sova recon bolt is on cooldown, forty seconds until the next dart, go in blind",
    "our Sova recon hit three at B, full B stack, rotate off immediately",

    # --- Sova: Hunter's Fury (X) ---
    "their Sova has hunter's fury up, eight ultimate points, three wall-piercing eighty-damage beams",
    "our Sova is firing hunter's fury, three sequential beams down A long, do not bunch up",
    "tell them their Sova fury hit one player through mid wall, eighty damage and revealed",
    "our Sova has hunter's fury ready, six-and-a-half second window to fire all three beams",
    "their Sova fury blasts are coming one at a time, visible red beam telegraphs the direction",

    # --- Breach: Aftershock (C) ---
    "their Breach set aftershock through the plant-side wall, two damage ticks through the surface",
    "our Breach aftershocked the defuser position, eighty damage per tick times two ticks, near-lethal",
    "tell them their Breach aftershock goes through walls, team-safe from his side but still hits us",
    "our Breach has aftershock left, two hundred credits, one through-wall charge for post-plant denial",
    "their Breach aftershocked the corner at A elbow, forcing our holder off position",

    # --- Breach: Flashpoint (Q) ---
    "their Breach flashpoint fired through the left wall, two second blind, it cannot miss in that corridor",
    "our Breach has two flashpoint charges, hard flash and soft flash both available",
    "tell them their Breach left-click flashpoint is the slow cook, one-point-six second fuse, look away fast",
    "our Breach right-click flashpoint is the fast flash, one second fuse, almost instant, eyes down",
    "their Breach has one flashpoint left, used one on the peek already, one slow-cook remaining",

    # --- Breach: Fault Line (E) ---
    "their Breach fault line is rolling A main, hold fire to extend the length, three-and-a-half second daze",
    "our Breach is charging fault line at B main, hold position for two seconds while he charges",
    "tell them their Breach fault line can travel fifty-five meters and goes through walls, seven-and-a-half meter width",
    "our Breach fault line concussed three at CT, they are dazed, execute on the concuss now",
    "their Breach fault line is on cooldown, thirty-five seconds until the next seismic wave",

    # --- Breach: Rolling Thunder (X) ---
    "their Breach has rolling thunder ult, nine ultimate points, six second concuss and a knockup",
    "our Breach rolling thunder is going off at A site right now, get clear if you are in the cone",
    "tell them their Breach ult covers a twenty-five meter wide thirty meter long cone forward",
    "our Breach rolling thunder hit four of them on site, massive concuss, retake right now",
    "their Breach used rolling thunder mid, everyone in the corridor is airborne and stunned",

    # --- Skye: Regrowth (C) ---
    "our Skye is channeling regrowth, heal radiating to all allies in line of sight, finite healing pool",
    "their Skye has no regrowth left this round, the healing pool is depleted",
    "tell them our Skye regrowth cannot heal above one hundred HP, no overheal from this ability",
    "their Skye is trying to heal through the smoke, she needs line of sight, she cannot heal through it",
    "our Skye has regrowth charges left, one-fifty credits, she is the only initiator with healing",

    # --- Skye: Trailblazer (Q) ---
    "their Skye sent trailblazer, the Tasmanian tiger is rolling toward A, shoot it before it concusses",
    "our Skye is piloting the trailblazer tiger, direct the leap to concuss the corner holder",
    "tell them their Skye tiger has eighty HP, one rifle shot destroys it, shoot on the audio cue",
    "our Skye trailblazer tiger concussed the B main holder, four second concuss, push through",
    "their Skye tiger got destroyed at mid, audio revealed one enemy behind the tiger path",

    # --- Skye: Guiding Light (E) ---
    "their Skye sent the guiding light hawk to A, she will manually detonate for a flash",
    "our Skye has two guiding light charges, both hawks available for a double flash on B",
    "tell them their Skye hawk auto-flashes at the end of its path if she does not manually pop it",
    "our Skye popped both hawks, both flash charges consumed, no more hawks this round",
    "their Skye hawk is in the air and about to pop, look away from the bird right now",

    # --- Skye: Seekers (X) ---
    "their Skye sent seekers, three seekers homing on the three nearest enemies, each has one-twenty HP",
    "our Skye has seekers ult with eight points, three nearsight seekers targeting their entire team",
    "tell them their Skye seekers apply nearsight on contact for approximately three seconds",
    "our Skye seekers hit all three, they are all nearsighted, push immediately",
    "their Skye seeker is coming for you, shoot it down before it makes contact",

    # --- KAY/O: FRAG/ment (C) ---
    "their KAY/O threw a FRAG/ment grenade, it sticks to the floor and pulses multiple times for four seconds",
    "our KAY/O frag stuck at B default, do not stand on the detonation zone, near-lethal at center",
    "tell them their KAY/O FRAG/ment cannot bounce, it sticks immediately on first floor contact",
    "our KAY/O frag is down post-plant, pulsing every tick on the defuser window",
    "their KAY/O frag is pulsing at mid tiles, eight meter diameter, three more ticks remaining",

    # --- KAY/O: FLASH/drive (Q) ---
    "their KAY/O left-click flash has a one-point-six second cook, you have time to look away",
    "our KAY/O right-click pop flash is one second cook, almost instant, eyes down at A short",
    "tell them their KAY/O FLASH/drive does not go through walls unlike Breach flashpoint",
    "our KAY/O has both flash charges ready, two FLASH/drives available for the B execute",
    "their KAY/O self-blinds with his own flash, Breach does not self-blind, that is the difference",

    # --- KAY/O: ZERO/point (E) ---
    "their KAY/O knife is in the air, twenty-meter suppression sphere, destroy the blade before it pops",
    "our KAY/O knife hit three at B, all three are suppressed for eight seconds, no abilities at all",
    "tell them our KAY/O ZERO/point suppressed their Killjoy, her nanoswarms turret and bot are all offline",
    "their KAY/O knife is on cooldown, forty seconds until the next blade, abilities are back",
    "our KAY/O knife hit the Jett, she cannot dash for eight seconds, she is stuck in position",

    # --- KAY/O: NULL/cmd (X) ---
    "their KAY/O is overloading with NULL/cmd, seven ultimate points, pulsing every three seconds for fifteen",
    "our KAY/O is in null, he is downed, someone revive him with a one-and-a-half second interact",
    "tell them their KAY/O null suppresses all enemies in range every three seconds during the fifteen second window",
    "our KAY/O got downed during null, we can still revive him, his body is at B main",
    "their KAY/O null ended, no more pulses, abilities are fully restored for both teams",

    # --- Fade: Prowler (C) ---
    "their Fade prowler is rolling toward us, it chases enemies and nearsights on contact for two-point-seven-five seconds",
    "our Fade sent prowlers on the nightfall trails, locked-on prowlers accelerate and cannot be escaped",
    "tell them their Fade prowler has one hundred HP, two rifle shots to kill it, prioritize shooting it",
    "our Fade prowler is steering toward their lurker at garage, he guided it left with the hold-fire control",
    "their Fade prowler nearsighted two of us, both blind for almost three seconds, we cannot see",

    # --- Fade: Seize (Q) ---
    "their Fade seize landed at B site, enemies inside are tethered for four-and-a-half seconds",
    "our Fade seize tethered their defuser, he cannot move off the spike, kill him now",
    "tell them their Fade seize applies deafen and decay alongside the tether, decay drops max HP by seventy-five",
    "our Fade seize is destroyable, enemies can shoot it before it activates to deny the tether",
    "their Fade seize tether wore off, players can move again, push when the four-point-five seconds expire",

    # --- Fade: Haunt (E) ---
    "their Fade haunt eye is floating at A main, it has one HP, shoot it before it reveals us",
    "our Fade haunt revealed two at B, terror trails on both of them for twelve seconds",
    "tell them their Fade haunt eye reveals enemies in line of sight for two seconds then terror trails persist",
    "our Fade haunt eye was destroyed before the reveal, we lost the intel, forty second cooldown now",
    "their Fade haunt terror trails are on two of us, their prowlers will rocket toward those trails",

    # --- Fade: Nightfall (X) ---
    "their Fade activated nightfall ult, eight ultimate points, wave forward applying deafen decay and terror trails",
    "our Fade nightfall hit three, she received a voice callout confirming three hit by the wave",
    "tell them their Fade nightfall wave passes through walls, they cannot avoid it by hiding behind cover",
    "our Fade nightfall trails plus prowlers equals guaranteed nearsight chain on anyone trailed",
    "their Fade nightfall decayed us and left trails, push the trails with our prowlers",

    # --- Gekko: Mosh Pit (C) ---
    "their Gekko mosh pit is expanding at B site, ten damage per second then detonation, not reclaimable",
    "our Gekko mosh pit landed with alt-fire underhand throw for close range, expanding zone active",
    "tell them their Gekko mosh pit cannot be picked up unlike his other creatures, it detonates and is gone",
    "our Gekko mosh pit is pulsing at the spike position, do not defuse yet, it will detonate",
    "their Gekko mosh pit covered the B default corner, that zone clears corner holders fast",

    # --- Gekko: Wingman (Q) ---
    "their Gekko wingman is rolling toward us, it will concuss the first person it finds",
    "our Gekko sent wingman with alt-fire to plant the spike, wingman is planting right now",
    "tell them their Gekko wingman can both plant and defuse the spike, he does not need to expose himself",
    "our Gekko wingman concussed their sentinel, dazed for a moment, push through the concuss",
    "their Gekko wingman got destroyed, eighty HP, we got the kill, globule is on the ground, he can reclaim it",

    # --- Gekko: Dizzy (E) ---
    "their Gekko dizzy is flying toward A, it fires plasma blasts that blind anyone in line of sight",
    "our Gekko dizzy blinded two at CT, the plasma blind also hides the minimap unlike a regular flash",
    "tell them their Gekko dizzy is projectile-based not instant, break line of sight before it fires plasma",
    "our Gekko reclaimed dizzy globule, it will be back as a charge in fifteen seconds",
    "their Gekko dizzy is in the air, arc it over the smoke, everyone behind cover until the plasma bursts",

    # --- Gekko: Thrash (X) ---
    "their Gekko is piloting thrash ult, seven ultimate points, he will lunge to detain everyone in radius",
    "our Gekko thrash detonated on their defuser, three second detain, cannot move shoot or use abilities",
    "tell them their Gekko thrash is still reclaimable after the detain, one reclaim per ult available",
    "our Gekko thrash is flying through B site, shoot the creature before it detonates and detains us",
    "their Gekko thrash detonated and detained two of us, we cannot fight back for three seconds",

    # --- Tejo: Stealth Drone (C) ---
    "their Tejo is piloting stealth drone at A, forty-two HP, shoot it before it detonates suppression",
    "our Tejo popped the stealth drone at B site, continuous reveal plus eight second suppression on everyone hit",
    "tell them their Tejo drone suppression locks out ALL abilities for eight seconds on contact",
    "our Tejo drone is harder to hear than Sova owl drone, the stealth drone has a quieter audio profile",
    "their Tejo drone got shot down, we prevented the eight second suppression, great trade",

    # --- Tejo: Special Delivery (Q) ---
    "their Tejo special delivery bounced off the wall with alt-fire and stuck to the corner holder",
    "our Tejo special delivery concussed two at B elbow, two-point-five second concuss post-nerf",
    "tell them their Tejo sticky grenade concuss was nerfed from four seconds to two-point-five seconds",
    "our Tejo has special delivery left, two hundred credits, one bounce or direct sticky concuss grenade",
    "their Tejo special delivery stuck to mid tiles, detonating in zero-point-nine seconds, get clear",

    # --- Tejo: Guided Salvo (E) ---
    "their Tejo opened guided salvo targeting and launched two missiles at B site",
    "our Tejo is sending guided salvo, forty-five meter range cap, both missiles landing A main",
    "tell them their Tejo guided salvo first charge is free each round, second charge costs one-fifty credits",
    "our Tejo fired both salvo missiles at the same location, compounding pressure on B default",
    "their Tejo guided salvo missiles are landing in two seconds, get off the default position",

    # --- Tejo: Armageddon (X) ---
    "their Tejo has armageddon ult, nine ultimate points, directional airstrike line sweep incoming",
    "our Tejo selected the strike path down A main, the wave is sweeping now, exit perpendicular",
    "tell them their Tejo armageddon sweep can be dodged by moving perpendicular to the strike direction",
    "our Tejo armageddon is clearing the mid corridor, sixty damage per tick times four ticks per segment",
    "their Tejo fired armageddon down B lane, get off the line, do not run along the wave path",

    # =========================================================================
    # SENTINELS
    # =========================================================================

    # --- Cypher: Trapwire (C) ---
    "their Cypher trip triggered at A lobby, one of us crossed it, we are slowed and revealed",
    "our Cypher placed two tripwires at B long and the flank route, both are active and watching",
    "tell them their Cypher tripwire has twenty HP, shoot the wire device to destroy it",
    "our Cypher picked up the trapwire to redeploy it at a better angle, pickup cooldown is fifteen seconds",
    "their Cypher trip hit our rotator, he is slowed and revealed on their minimap right now",

    # --- Cypher: Cyber Cage (Q) ---
    "their Cypher activated cyber cage at B door, seven second vision block, audio cue if we walk through",
    "our Cypher placed cages pre-round and will activate them reactively when the audio triggers",
    "tell them their Cypher cyber cage plays an audio cue when anyone walks through even if nobody is watching",
    "our Cypher has two cyber cage charges, both can be pre-placed and activated on demand",
    "their Cypher cage is up at garage, the footstep audio will alert him if we push through it",

    # --- Cypher: Spycam (E) ---
    "their Cypher spycam is watching B main from the box, he can fire marking darts from the camera",
    "our Cypher tagged their Viper through the spycam dart, she is revealed indefinitely until she removes it",
    "tell them their Cypher cam has a forty-five second respawn if destroyed, fifteen second pickup cooldown",
    "our Cypher spycam is down, destroyed, no vision from that angle for forty-five seconds",
    "their Cypher cam marked our entry fragger, they know his position through walls right now",

    # --- Cypher: Neural Theft (X) ---
    "their Cypher activated neural theft on our body, full enemy reveal twice, four seconds apart",
    "our Cypher has neural theft ready, seven ultimate points, full-team reveal through walls twice",
    "tell them their Cypher ult reveals all living enemy positions twice, the two waves are four seconds apart",
    "our Cypher stole info from the body, full reveal showed two on B and one rotating mid",
    "their Cypher must be within crosshair range of the dead body to activate neural theft",

    # --- Sage: Barrier Orb (C) ---
    "their Sage placed barrier orb at A main, four hundred HP per panel while fortifying to eight hundred",
    "our Sage wall is up at B door, it takes forty seconds to decay naturally, break it or wait it out",
    "tell them their Sage wall fortifies after three-point-three seconds to eight hundred HP per panel",
    "our Sage wall is boost position, climb over it to access the elevated angle on the left",
    "their Sage broke our A main wall, the entrance is open, no more wall block this round",

    # --- Sage: Slow Orb (Q) ---
    "their Sage threw slow orb at A link, seven second slow field, fifty percent speed reduction inside",
    "our Sage slow orb also reduces Jett and Neon dash speed by fifty percent, not just movement",
    "tell them their Sage slow orb hits allies too, everyone in the field is slowed equally",
    "our Sage has two slow orb charges, both available for the retake slow chain",
    "their Sage slow field is at B elbow, walk around it, do not push through the slow",

    # --- Sage: Healing Orb (E) ---
    "our Sage fired healing orb at the Jett, sixty HP heal over five seconds to our teammate",
    "their Sage self-healed with alt-fire healing orb, fifty HP over five seconds to herself",
    "tell them their Sage healing orb has a forty-five second cooldown after the heal completes",
    "our Sage has no healing orb left, cooldown running, buy a heavy shield instead",
    "their Sage healed herself to full after the gunfight, healing orb alt-fire self-heal",

    # --- Sage: Resurrection (X) ---
    "their Sage activated resurrection on their dead player, full health revive, both are vulnerable during channel",
    "our Sage has resurrection ult, seven points, cover her while she rezzes, she cannot fight during channel",
    "tell them their Sage rez requires her to stand over the body, both she and the target are exposed",
    "our Sage rezzing right now, hold this position, she is channeling the resurrection",
    "their Sage rezzed their star player at full one hundred HP, we have to kill them again",

    # --- Killjoy: Nanoswarm (C) ---
    "their Killjoy nanoswarm is planted near the spike, she will activate it when we defuse",
    "our Killjoy popped two nanoswarms around the spike, forty-five damage per second, do not defuse",
    "tell them their Killjoy nanoswarm goes covert on landing, invisible until three-point-five meters or activated",
    "our Killjoy nano is on cooldown, both charges spent, she bought two this round",
    "their Killjoy activated nano on our defuser, he is taking massive damage right now",

    # --- Killjoy: Alarmbot (Q) ---
    "their Killjoy alarmbot detonated on our flank entry, he is vulnerable for four seconds",
    "our Killjoy bot triggered at A lobby, one enemy confirmed at the entrance, they are vulnerable",
    "tell them their Killjoy alarmbot stays hidden until enemies come within seven meters of it",
    "our Killjoy recalled her alarmbot, twenty second pickup cooldown, she is repositioning it",
    "their Killjoy bot applied vulnerable, shoot him right now while the four second window is active",

    # --- Killjoy: Turret (E) ---
    "their Killjoy turret is watching B main from logs position, it gives free intel on pushers",
    "our Killjoy turret has one hundred HP, shoot it to destroy and remove the intel source",
    "tell them their Killjoy turret fires within a one hundred degree cone, it is a fan-shaped detection zone",
    "our Killjoy turret respawns after forty-five seconds if destroyed, she gets it back free",
    "their Killjoy turret spotted our entry in mid, she knows someone pushed",

    # --- Killjoy: Lockdown (X) ---
    "their Killjoy deployed lockdown device, nine ultimate points, thirteen second windup before detain",
    "our Killjoy lockdown device is out, protect it, if they destroy it we lose the ult",
    "tell them their Killjoy lockdown detains all enemies in its massive radius for eight seconds on activation",
    "our Killjoy lockdown is about to pop in three seconds, nobody can fight during detain, hold",
    "their Killjoy lockdown device was destroyed during the thirteen second windup, ult wasted",

    # --- Chamber: Trademark (C) ---
    "their Chamber trademark triggered at A lobby, the player who crossed it is now in a slow field",
    "our Chamber placed trademark at B entry, the trap scans then destabilizes terrain creating a slow zone",
    "tell them their Chamber trademark is redeployable, he picks it up and moves it if the push changes",
    "our Chamber trap went off at CT, someone stepped into range, slow field is active",
    "their Chamber trap is down, destroyed, no more slow field intel from that position",

    # --- Chamber: Headhunter (Q) ---
    "their Chamber is running headhunter pistol, one-tap headshot for one hundred fifty-nine damage",
    "our Chamber has eight headhunter bullets max, each bullet costs one hundred credits individually",
    "tell them their Chamber headhunter one-taps heads, it is not the sheriff, it is his custom pistol",
    "our Chamber has no headhunter bullets left this round, he bought his allotment and spent them",
    "their Chamber aimed down sights with headhunter, ADS tightens accuracy significantly on that pistol",

    # --- Chamber: Rendezvous (E) ---
    "their Chamber rendezvous anchor is visible on the ground at CT, he will teleport back to it if he peeks",
    "our Chamber TP'd back to his rendezvous anchor, he escaped the bad angle instantly",
    "tell them their Chamber rendezvous anchor was destroyed, forty-five second cooldown, he cannot escape",
    "our Chamber has rendezvous ready, thirty second cooldown, one anchor for the entire round",
    "their Chamber repositioned by teleporting to the anchor, he is now at a completely different angle",

    # --- Chamber: Tour De Force (X) ---
    "their Chamber has tour de force ult, eight points, powerful custom sniper with five one-tap shots",
    "our Chamber activated tour de force, five bullets each one-shots upper body or head at any range",
    "tell them their Chamber tour de force leaves a slow field where each kill lands",
    "our Chamber is using tour de force like an op, hitscan, same mechanics as the Operator",
    "their Chamber tour de force is active and he killed our initiator, slow field at the kill location",

    # --- Deadlock: Barrier Mesh (C) ---
    "their Deadlock deployed barrier mesh, three hundred twenty HP side orbs, blocks player bodies but not bullets",
    "our Deadlock mesh is up at B elbow, the center orb has twelve hundred HP fortified after three seconds",
    "tell them their Deadlock barrier mesh blocks movement but allows bullets and abilities to pass through",
    "our Deadlock mesh has a thirty second duration, it fortifies to full HP after three point zero seconds",
    "their Deadlock mesh cut off B main, they cannot push bodies through but they can shoot through it",

    # --- Deadlock: Sonic Sensor (Q) ---
    "their Deadlock sonic sensor triggered at mid, someone made noise, three-point-five second concuss in the area",
    "our Deadlock placed two sonic sensors at A main and the flank route, both watching for audio",
    "tell them their Deadlock sonic sensor has twenty HP and is invisible until enemies approach within three meters",
    "our Deadlock sensor concussed the B push, three-and-a-half second stun triggered by their footsteps",
    "their Deadlock sonic sensor went off at garage, they know someone is rotating through there",

    # --- Deadlock: GravNet (E) ---
    "their Deadlock gravnet landed at A lobby, everyone inside is crouching and moving at thirty percent speed",
    "our Deadlock grav net hit two at mid, both pinned, they cannot jump or run, push through them",
    "tell them their Deadlock gravnet forces a crouch and seventy percent slow for six seconds in a six-point-five meter radius",
    "our Deadlock has gravnet ready, forty second cooldown, one net grenade to pin the retake push",
    "their Deadlock gravnet hit the entry player, he is crouching and moving at thirty percent, one-tap him",

    # --- Deadlock: Annihilation (X) ---
    "their Deadlock fired annihilation, first enemy hit is cocooned in a six hundred HP cocoon",
    "our Deadlock cocooned their Jett, break it to free her, she dies if the cocoon reaches the kill point",
    "tell them their Deadlock cocoon can be destroyed by teammates, six hundred HP to break the nanowire",
    "our Deadlock annihilation is dragging them toward the kill point, seven seconds to destroy the cocoon",
    "their Deadlock ult cocooned our star player, break the cocoon now before they pull him in",

    # --- Vyse: Razorvine (C) ---
    "their Vyse planted razorvine near the spike, it goes invisible on landing, do not rush the defuse",
    "our Vyse activated razorvine at B elbow, anyone moving through it takes ten damage per tick and is slowed",
    "tell them their Vyse razorvine also slows Jett and Neon dash speed, even dashes are affected",
    "our Vyse has two razorvine charges, both placed around the spike for post-plant denial",
    "their Vyse razorvine is active near the plant, it is only visible after she activates it remotely",

    # --- Vyse: Shear (Q) ---
    "their Vyse shear triggered at B main, an indestructible wall burst up behind the player who crossed",
    "our Vyse shear isolated the lurker at CT, the wall blocks his retreat for six seconds",
    "tell them their Vyse shear wall is indestructible unlike Sage wall, it cannot be broken",
    "our Vyse shear trap is set near the CT exit, any enemy crossing gets walled off from retreating",
    "their Vyse shear activated, the enemy at B elbow is cut off and cannot go backward",

    # --- Vyse: Arc Rose (E) ---
    "their Vyse placed arc rose on CT wall, she is about to pop the flash, look away",
    "our Vyse activated arc rose, max two-point-two-five second blind on anyone looking at it",
    "tell them their Vyse arc rose has a twenty second cooldown after use, she gets it back fast",
    "our Vyse placed arc rose with alt-fire through the surface, it is on the other side of the wall",
    "their Vyse is about to pop the arc rose, half-second windup delay, heads down on your side",

    # --- Vyse: Steel Garden (X) ---
    "their Vyse has steel garden ult, eight points, she jams primary weapons for eight seconds in the radius",
    "our Vyse steel garden is going off, their primary guns are all jammed, pistols and abilities only",
    "tell them their Vyse steel garden does not affect Chamber tour de force Jett bladestorm or Neon overdrive",
    "our Vyse steel garden jammed their whole team on site, rush them while they have no primaries",
    "their Vyse steel garden jam is still active, three seconds left, hold and do not peek yet",

    # --- Veto: Crosscut (C) ---
    "their Veto placed a crosscut vortex at B main, he will teleport to it if he needs to escape",
    "our Veto teleported to his crosscut vortex, slight delay unlike old Chamber rendezvous which was instant",
    "tell them their Veto crosscut requires line of sight to the vortex, block the sightline and he cannot TP",
    "our Veto has two crosscut charges, both vortexes placed, he can reposition twice",
    "their Veto picked up the crosscut vortex during buy phase to redeploy at a better angle",

    # --- Veto: Chokehold (Q) ---
    "their Veto chokehold tethered our lurker at mid, he is immobilized deafened and decaying",
    "our Veto chokehold trap is down at B elbow, any enemy entering gets tethered deafened and decayed",
    "tell them their Veto chokehold can be destroyed before it activates, shoot it on the way in",
    "our Veto hit their Neon with chokehold, she cannot sprint or hear anything, kill her now",
    "their Veto chokehold wore off, four-point-five seconds of tether is done, player can move again",

    # --- Veto: Interceptor (E) ---
    "their Veto interceptor is active at mid, it will destroy any utility that enters its range",
    "our Veto interceptor destroyed their Sova recon dart mid-flight, ten HP of the interceptor remains",
    "tell them their Veto interceptor has twenty HP, forty second cooldown, shoot it before Sova fires",
    "our Veto interceptor blocked their Raze grenade, the paint shells were eaten by the device",
    "their Veto activated interceptor, it will nullify our utility in that mid area for ten seconds",

    # --- Veto: Evolution (X) ---
    "their Veto evolved with evolution ult, seven points, he is now immune to all debuffs, do not flash him",
    "our Veto evolution gives immunity to flashes stuns slows concuss decay and any negative status",
    "tell them their Veto evolution also gives combat stim and regen on top of the immunity",
    "our Veto ult lasts until he dies, no timer on the mutation, he is immune until dead",
    "their Veto is evolved, no point using utility on him, go to a pure gunfight",

    # =========================================================================
    # COMPOUND OUR/THEIR OWNERSHIP STRESS
    # =========================================================================

    "tell them our Jett has her cloudburst and tailwind both saved, their Jett burned her dash and smokes already",
    "relay that their Reyna is in empress while our Reyna has no soul orbs and cannot dismiss or devour",
    "tell the team our Sova dart hit two of them while their Sova recon is still on cooldown",
    "relay their Killjoy has lockdown and ours does not, our Killjoy burned it last round",
    "tell them their Viper pit is up on B while our Viper toggled off the wall to save fuel",
    "relay our KAY/O knife suppressed three of theirs while their KAY/O has no knife this round",
    "tell the team their Sage has resurrection and our Sage already used rez on the Jett",
    "relay their Breach rolling thunder is up but our Breach has no ult, different cooldown windows",
    "tell them our Clove is smoking from the grave post-death while their Clove died with no smokes left",
    "relay their Omen has from the shadows ready while our Omen has both dark covers on cooldown",
    "tell the team our Astra gravity well hit their cluster while their Astra has no stars for thirty seconds",
    "relay their Deadlock grav net pinned two of us while our Deadlock has no gravnet left this round",
    "tell them their Chamber tour de force is active with five bullets while our Chamber has no ult",
    "relay our Gekko reclaimed dizzy and wingman globules while their Gekko cannot reclaim mosh pit",
    "tell the team their Fade nightfall trailed three of us while our Fade haunt is on cooldown",
    "relay their Iso contingency wall is blocking bullets while our Iso undercut is the only ability he has left",
    "tell them their Neon has overdrive and our Neon burned it two rounds ago and is one point off",
    "relay our Tejo stealth drone suppressed their initiator while their Tejo drone got shot down",
    "tell the team their Skye has two hawk charges while our Skye is out of guiding light entirely",
    "relay their Vyse has steel garden ready while our Vyse already used the jam and eight seconds are up",

    # =========================================================================
    # ULT STATE EXHAUSTIVE (THEIR ULT UP / OUR ULT UP / ULT DOWN / ULT PARTIAL)
    # =========================================================================

    "their Jett has blade storm, eight points, she will ult-op the angle",
    "our Jett is one kill off blade storm, one orb away from the knives",
    "their Jett used blade storm and burned all knives, ult is completely spent",
    "our Reyna has empress ready, she executes first on six points",
    "their Reyna empress expired without a kill chain, ult wasted",
    "our Raze showstopper is up, hold until the rocket fires then rush",
    "their Raze used showstopper, do not worry about the rocket this round",
    "our Phoenix has run it back, let him entry, he comes back if he dies",
    "their Phoenix ult ran out before he got a kill, no respawn, he is actually dead",
    "our Yoru dimensional drift is active, he is invisible, gathering info for us",
    "their Yoru is inside dimensional drift, cannot shoot him, wait for the exit flash",
    "our Neon overdrive is up, she goes in first with the beam",
    "their Neon overdrive died before she got a chain-kill refresh, ult down",
    "our Iso kill contract is up, he can remove their best duelist from the round",
    "their Iso lost the kill contract duel, four versus five now",
    "our Waylay convergent paths is up, expanding beam plus speed boost ready",
    "their Waylay used convergent paths but the beam missed all of us",
    "our Brimstone has orbital, eight points, post-plant laser ready",
    "their Brimstone orbital already went off, it will not be back for several rounds",
    "our Viper pit is up, she is nine points in and planting for the pit hold",
    "their Viper has no pit this round, one point short, she is playing without ult",
    "our Omen from the shadows is ready, seven points, global TP flanking position",
    "their Omen ult shade got destroyed, teleport cancelled, seven points wasted",
    "our Astra has cosmic divide, seven points, bullet-blocking infinite wall ready",
    "their Astra divide is fading, twenty-one second duration almost gone",
    "our Harbor reckoning is up, seven points, forward nearsight wave for the push",
    "their Harbor reckoning was dodged because we moved perpendicular to the wave",
    "our Clove not dead yet is charged, she can revive once after dying this round",
    "their Clove failed not dead yet, no kill in ten seconds, she died again",
    "our Sova hunter's fury is up, eight points, three map-piercing beams ready",
    "their Sova fury used two of three beams, one beam charge remaining",
    "our Breach rolling thunder is ready, nine points, site-wide knockup and concuss",
    "their Breach ult hit us, everyone at A is airborne and concussed for six seconds",
    "our Skye has seekers, eight points, three homing nearsight seekers for the push",
    "their Skye seekers missed because we shot two of the three down",
    "our KAY/O null is up, seven points, he pulse-suppresses all enemies every three seconds",
    "their KAY/O is downed in null, one point five second revive, someone go get him",
    "our Fade nightfall is ready, eight points, map-wide deafen decay and terror trail wave",
    "their Fade nightfall hit two of us, both trailed and decayed, watch for prowlers on the trails",
    "our Gekko thrash is up, seven points, he pilots and detonates for a detain",
    "their Gekko thrash failed to detain because we shot it down before it connected",
    "our Tejo armageddon is ready, nine points, directional line sweep",
    "their Tejo armageddon swept down mid, get perpendicular to the strike path",
    "our Cypher neural theft is up, seven points, double full-team reveal",
    "their Cypher ult revealed our full positions twice, four seconds apart",
    "our Sage has resurrection, seven points, cover her while she rezzes",
    "their Sage used rez on the Killjoy, we have to kill that Killjoy again",
    "our Killjoy lockdown is up, nine points, covers the entire site for eight seconds",
    "their Killjoy lockdown device is being protected by two of them, break it in thirteen seconds",
    "our Chamber tour de force is active, five one-tap shots, five ult bullets remaining",
    "their Chamber tour de force left slow fields at three kill locations on site",
    "our Deadlock annihilation is charged, seven points, she will cocoon their entry",
    "their Deadlock cocooned our Jett, allies break the cocoon or she dies in seven seconds",
    "our Vyse steel garden is up, eight points, primary jam for eight seconds",
    "their Vyse steel garden going off, drop to pistols for eight seconds",
    "our Veto evolution is active, immune and regenerating, no util works on him",
    "their Veto evolution lasts until he dies, only a straight gunfight will kill him",
]
