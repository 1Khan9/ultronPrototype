"""Relay corpus: stress_clutch_dense (kind=relay, ~600 cases).

CHARGE: Clutch / time-pressure DENSE callouts — post-plant, retake, 1vX,
last-alive, spike-down-in-N scenarios.  Every count / location / timer MUST
survive under urgency.  These are the hardest realistic utterances a streamer
fires into voice chat when the round is on the line.

Metrics stressed:
  - fact-token retention: counts, agent names, map callouts, timers, HP values
  - compound zero-fact-loss under urgency (streamer elides words mid-sentence)
  - ownership inversion: "I" vs "he/she/they" vs "our/their"
  - timer precision: "30", "20", "10", "5 seconds", "spike in X"
  - directive fidelity: "don't peek", "play for time", "stick it"
  - first-person traps: "I'm the last one" must relay correctly
  - hallucination guard: no invented cooldown numbers
  - 1vX structure: "one vs two", "1v3", "last alive" framing
  - post-plant role split: hold spike vs play time vs fake defuse
  - ability state under clutch: KJ nano, KAY/O suppressed, Sage wall, molly on spike
"""

ITEMS = [
    # ================================================================
    # POST-PLANT — SPIKE TIMER CALLOUTS (all maps, urgent)
    # ================================================================
    "spike down A, 40 seconds, play off generator",
    "spike is planted B default, 35 seconds left, watch market stairs",
    "spike A, 30 seconds, he's in hell, don't peek",
    "planted C, 25 seconds, two of them left, one is in garage",
    "spike B, 20 seconds, one defusing, molly him",
    "spike is down, 15 seconds, let it blow",
    "spike A, 10 seconds, don't go in, play for detonation",
    "spike B, 45 seconds, play crossfire from boathouse and stairs",
    "planted for main A, 38 seconds, they're retaking through garden",
    "spike C, 32 seconds, last two alive on their side, both pushing long",
    "planted default B, 28 seconds, one's in alley, one's on stairs",
    "spike A generator, 22 seconds, he's low, one shot, don't let him defuse",
    "spike down, 18 seconds, two of them at CT entry, we need kills now",
    "spike B triple box, 12 seconds, last one trying ninja defuse, smoke him",
    "planted for CT, 40 seconds, three retaking, hold catwalk and garden",
    "spike A, 36 seconds, their Killjoy lockdown just went off, scatter",
    "spike B, 29 seconds, he started defusing, tap it out",
    "planted for heaven, 24 seconds, two of them pushing from CT",
    "spike C platform, 19 seconds, their Viper pit is up, watch the wall",
    "spike A back gen, 14 seconds, fake defuse, see if he peeks",
    "spike B workshop, 42 seconds, four alive on their side, all retaking",
    "planted default A, 31 seconds, one unaccounted, check hell",
    "spike C, 27 seconds, KJ has nano on spike, they can't defuse through it",
    "spike B, 23 seconds, sage walled the alley, we're safe to play for time",
    "planted A, 17 seconds, he's 1 hp, just tap spike and he'll peek",
    "spike down B, 11 seconds, do not engage, let it detonate",
    "spike C, 9 seconds, stick it now or let it go, your call",
    "spike A, 43 seconds, their Jett dashed to heaven, she has ult",
    "planted B, 37 seconds, two pushing from market door and alley at same time",
    "spike A default, 26 seconds, one in tree, one in garden, crossfire the spike",

    # ================================================================
    # 1vX — LAST ALIVE CLUTCH FRAMING
    # ================================================================
    "I'm last alive, one vs three, spike's in B workshop, 25 seconds",
    "last one alive, 1v2, spike A generator, 30 seconds on the clock",
    "1v4, I have spike, they don't know where I am, going for plant",
    "I'm 1v1, he's low, I dinked him, going for it",
    "last alive 1v2, both are in garage, I'm planting C",
    "1v3, spike down B default, 20 seconds, I'm hiding in boathouse",
    "last one alive vs four, no util, spike not planted, 35 seconds",
    "I'm the last, 1v2, one is in hell, one is in garden, spike A",
    "1v1 post-plant, spike B, he's defusing, I see him, swinging",
    "last alive, four versus me, spike down, 18 seconds, playing for time",
    "1v2, their Reyna has dismiss and devour, be careful with the call",
    "last player alive, 1v3, spike not planted, I have 30 seconds to plant",
    "1v1, I'm on 15 HP no armor, he's full health, playing off spike",
    "I'm the last one, 1v2, they're pushing me from two sides, spike B",
    "last alive 1v2, Sage walled behind me, I'm locked into B site",
    "1v3, all three are retaking through CT, spike is down A default, 28 seconds",
    "1v1 clutch, he's in wine, I'm at generator, spike A, 15 seconds",
    "I'm last alive, 1v4, spike's not planted, I'm trying to find a pick",
    "1v2, spike B, molly is on spike already, they can't defuse, 22 seconds",
    "last one, 1v3, I'm pushing through catwalk, trying to find an angle",
    "1v1, he's camping hell, spike A, 10 seconds, I have to push",
    "1v2, I'm at tree, spike A generator, 20 seconds, I need two kills",
    "last alive, their Yoru used dimensional drift, 1v1 but I can't see him",
    "1v2, spike is B, I dropped the Op, running ghost now, 30 seconds",
    "1v3, no abilities left, spike B default, 25 seconds, it might just blow",
    "I'm last alive 1v1, he's on 50 HP, I'm on 100 full, going in",
    "1v2, spike A, planted for main, I'm in hell, waiting for them to push",
    "last player, 1v4, I tapped him for 60, spike not down, 38 seconds",
    "1v1, defusing, he's somewhere in garden, half done, going to stick it",
    "I'm the last alive, 1v3, they're all B, I'm going to sneak to A",

    # ================================================================
    # RETAKE CALLOUTS — DENSE LOCATION + COUNT + STATE
    # ================================================================
    "three on B site, spike B default, two seconds ago, retake through market",
    "two took A, spike not down yet, retake through garden and tree",
    "they're on site, two of them, spike A, 40 seconds, fast retake CT",
    "full five hit B, spike is planted, 35 seconds, retake with ult",
    "two left alive on their side, spike C, retake through garage and C short",
    "one anchoring A, spike generator, 30 seconds, he has an Op",
    "they planted B default, 28 seconds, KJ has nano on it, clear nano first",
    "retake A, one in heaven, one deep site, spike 25 seconds",
    "they planted, 22 seconds, two retaking on our side, go through CT",
    "spike B workshop, 20 seconds, Viper's pit is covering defuse spot",
    "one defending spike A, he's in hell, 18 seconds, smoke hell and push",
    "planted C platform, 15 seconds, he's holding the defuse from plat",
    "retake B, 12 seconds, not enough time, just play for ace next round",
    "two covering spike B, one from stairs, one from alley, 25 seconds",
    "they have four alive, planted A, 35 seconds, we need utility for retake",
    "spike A back gen, 30 seconds, he's playing off tree angle, cut him off",
    "retake B now, 28 seconds, their Sage walled market, go through alley",
    "three of them anchoring B, spike down, 22 seconds, we need KO knife",
    "retake C, two left on their side, one in garage, one on platform, 20 seconds",
    "spike A, 18 seconds, I have flash, I'll push, you hold garden",
    "retake B default, 16 seconds, fake tap spike and see who peeks",
    "spike C default, 14 seconds, their Omen still has two smokes, be careful",
    "planted A, two holding it, 30 seconds, we have lockdown, use it now",
    "spike B, 26 seconds, three alive their side, retake is risky, assess",
    "retake A, 24 seconds, I'm coming garden, you push long, crossfire site",
    "spike down B, 20 seconds, their Raze showstopper is charged, watch out",
    "retake C, 17 seconds, he's low, I dinked him for 70, push now",
    "planted for CT, 15 seconds, two of them, I need a trade at minimum",
    "spike B, 13 seconds, one is down, one left, he's in boathouse",
    "retake A, 40 seconds, their Killjoy turret is still up in hell",

    # ================================================================
    # DEFUSE RACE — TIMING, FAKE, STICK IT
    # ================================================================
    "he's defusing, tap him out, someone push from CT",
    "they're on spike, 10 seconds, molly the defuse spot",
    "he started defuse, 8 seconds on spike, I'm going",
    "defusing, almost done, two alive but they don't know where I am",
    "he's halfway through defuse, swing him from garden",
    "I'm defusing spike A, watch heaven, 15 seconds on spike",
    "defusing B default, cover my back from stairs and alley",
    "he's defusing, flash him out, two seconds left on defuse",
    "I started defuse, tap it to bait him, then I'll swing",
    "ninja defuse attempt, B workshop, they haven't found me yet",
    "I'm defusing, one alive, he's in hell, someone spot him",
    "defuse almost done, spike in 5 seconds, stick or go, deciding now",
    "he tapped spike, baiting me out, don't swing, wait for the peek",
    "defusing B, their Killjoy nano on spike, I'm taking damage, need a clear",
    "I'm doing the defuse, 12 seconds left, KJ lockdown just ended",
    "he's defusing, viper wall is blocking my shot, need someone to get through",
    "half defuse done, their Omen teleported behind me, I have to swing",
    "defusing A generator, Sage wall between me and their last alive",
    "I'm on the spike, 7 seconds left on defuse, one alive, he's in tree",
    "stick it, you have enough time, 6 seconds on spike, don't stop",
    "defusing C default, platform is clear, he's in logs corner, watch it",
    "he's defusing, Phoenix molly on spike, he'll die on it if we wait",
    "half defused B, two coming from market, I can't fight and defuse",
    "defusing A, heaven is clear, hell is clear, one unaccounted, be ready",
    "I'm on it, 4 seconds, don't come to me, I might die and we lose spike",
    "defuse race, he's planting, I'm rushing in, 10 seconds till plant finishes",
    "he just started defuse on B, nano him, KJ, nano the spike now",
    "defusing, sage walled behind the spike, I'm safe, 8 seconds left",
    "tap it once, let him peek, then full commit, 18 seconds",
    "stuck on defuse, two alive their side, I need everyone to hold angles",

    # ================================================================
    # HAVEN (3-SITE) — CLUTCH POST-PLANT COMPLEXITY
    # ================================================================
    "spike C, 30 seconds, two of them left, one in garage, one on platform",
    "planted B, 25 seconds, their Cypher is alive, watch for cam on spike",
    "spike A, 22 seconds, one in heaven, one in hell, we're in a crossfire",
    "planted C default, 28 seconds, three retaking, two through long, one short",
    "spike B, 18 seconds, gong player has ult, he's Reyna Empress activated",
    "planted A long, 15 seconds, he's in heaven with Op, smoke it",
    "spike C platform, 32 seconds, KJ lockdown placed near spike",
    "planted B gong, 20 seconds, he's faking defuse, don't swing blind",
    "spike A, 35 seconds, their whole team is retaking from CT corridor",
    "planted C, 12 seconds, single alive their side, he's in garage with a vandal",
    "spike A heaven position, 27 seconds, one in hell, one coming from link",
    "B default spike, 23 seconds, four alive retaking, abort defuse if possible",
    "planted C, 40 seconds, two unaccounted, one confirmed C long, one missing",
    "spike A, 10 seconds, last one alive their side, he's in A link, let it go",
    "planted B gong, 38 seconds, Viper wall through CT, blocking our rotation",

    # ================================================================
    # ASCENT — CLUTCH SPECIFIC CALLOUTS (Generator, Hell, Heaven, Catwalk)
    # ================================================================
    "spike A generator, 20 seconds, one in hell, one in tree, crossfire",
    "planted B triple box, 25 seconds, KJ nano on spike already",
    "spike A, he's in hell, 18 seconds, need a molly into hell",
    "planted default B, 30 seconds, market door is closed, they're coming through alley",
    "spike A back gen, 22 seconds, Sage walled garden, we're buying time",
    "spike B workshop, 28 seconds, two pushing from CT stairs and alley",
    "planted A dice, 15 seconds, one in heaven with Op, smoke rafters",
    "spike B, 20 seconds, B door is closed, someone break it or go alley",
    "planted A, catwalk player is rotating to garden, 35 seconds",
    "spike B boathouse, 12 seconds, one tapping spike from stairs angle",
    "planted A generator, 40 seconds, three alive retaking, flash garden and push",
    "spike A, 17 seconds, hell is a death trap, don't go in, play from pillar",
    "planted B default, 26 seconds, their Jett has blade storm, she'll dash out",
    "spike A, 10 seconds, it's over unless you're already at garden entry",
    "planted B, 33 seconds, four retakers, lockdown would win this",

    # ================================================================
    # SPLIT — CLUTCH CALLOUTS (Heaven, Hell, Ropes, Mid Vent)
    # ================================================================
    "spike A, 22 seconds, one on A tower with op, smoke the tower",
    "planted B default, 28 seconds, he's in B hell, can't defuse safely",
    "spike A, 18 seconds, they used the mid vent rope, someone's flanking",
    "planted B, 25 seconds, two on rafters, crossfire from below",
    "spike A screens, 15 seconds, one came through vent to A tower",
    "planted B, 30 seconds, KAY/O suppressed their Sage, no wall this round",
    "spike A back site, 20 seconds, two pushing from A lobby ropes",
    "planted B default, 12 seconds, he's defusing from the pillar side",
    "spike A, 38 seconds, their Viper wall splits us at A main",
    "planted B hell, 24 seconds, one playing from B rafters, hard angle",
    "spike A, 19 seconds, sage walled A main entry, they bought time",
    "planted B, 14 seconds, two retaking through B alley and CT",
    "spike A heaven, 27 seconds, one in A tower, one under heaven",
    "planted B default, 21 seconds, he's in the TV corner, pre-aim it",
    "spike A, 35 seconds, Breach rolling thunder coming through mid vent",

    # ================================================================
    # FRACTURE — CLUTCH CALLOUTS (Dual spawn, Rope, Dish)
    # ================================================================
    "spike A, 22 seconds, two came from attacker B rope, flanking A",
    "planted B, 28 seconds, their Neon is running the rope side",
    "spike A, 18 seconds, Sova recon on site, he knows where I am",
    "planted B, 25 seconds, one in B arcade, one pushing from dish",
    "spike A default, 20 seconds, their KAY/O used null, everyone's suppressed",
    "planted B, 15 seconds, three retaking, one from each rope entry",
    "spike A dish side, 30 seconds, he has an Op in dish, smoke it",
    "planted B hall, 23 seconds, Fade seize landed on our defuser",
    "spike A, 38 seconds, Brimstone orbital coming down on default plant",
    "planted B, 12 seconds, one tapping spike, not committing, bait swing",

    # ================================================================
    # LOTUS — CLUTCH CALLOUTS (3 sites, rotating doors, ziplines)
    # ================================================================
    "spike A, 22 seconds, one in A root, rotating door open, retaking",
    "planted B, 28 seconds, their Killjoy Lockdown covering the defuse spot",
    "spike C, 18 seconds, two alive their side, both in C mound area",
    "planted A, 25 seconds, he's playing off the tree side of site",
    "spike B, 20 seconds, rotating door between B and C just opened",
    "planted C, 15 seconds, two pushing from C link, crossfire the plant",
    "spike A, 30 seconds, one in A alcove with op, long hold",
    "planted B default, 23 seconds, KJ nano placed on spike directly",
    "spike C, 17 seconds, their Clove just used Not Dead Yet, she revived",
    "planted A, 12 seconds, four retaking, we only have two alive",
    "spike B, 40 seconds, Astra gravity well on our rotation path",
    "planted C mound, 27 seconds, one anchoring from C corner",
    "spike A, 35 seconds, sage walled between A site and CT entry",
    "planted B, 19 seconds, Harbor cove covered the spike, can't molly it",
    "spike C, 10 seconds, last one defusing, he's almost done",

    # ================================================================
    # PEARL — CLUTCH CALLOUTS (Underground, Art, Mid)
    # ================================================================
    "spike A, 22 seconds, one hiding in A art, watching the plant",
    "planted B, 28 seconds, their Viper pit is on B site",
    "spike A, 18 seconds, two retaking through mid link",
    "planted B default, 25 seconds, one in B market, one in B link",
    "spike A, 20 seconds, Astra cosmic divide cut our rotation",
    "planted B, 15 seconds, he's defusing from behind the boxes",
    "spike A art, 30 seconds, one came through A short, check it",
    "planted B, 12 seconds, Sova recon tagged both defenders",
    "spike A, 38 seconds, three alive retaking, flash A short and push",
    "planted B, 23 seconds, Killjoy turret still watching the defuse spot",
    "spike A, 17 seconds, he's low, 25 HP, dinked from art side",
    "planted B market, 27 seconds, two crossfiring from B link and B main",
    "spike A, 10 seconds, don't risk it, let the spike blow",
    "planted B, 35 seconds, their Sage used rez on the Jett",
    "spike A, 14 seconds, their Cypher neural theft confirmed two of us alive",

    # ================================================================
    # BREEZE — CLUTCH CALLOUTS (Long halls, Mid, Cave)
    # ================================================================
    "spike A, 22 seconds, Op on A main holding the defuse angle",
    "planted B, 28 seconds, he's in B cave with a judge",
    "spike A, 18 seconds, two retaking through mid and A hall",
    "planted B default, 25 seconds, Viper wall blocking B cave entry",
    "spike A, 20 seconds, one in A pyramids, one in A main",
    "planted B, 15 seconds, Sova shock dart on spike, clearing nano style",
    "spike A, 30 seconds, their Jett dashed to elbow, she has blade storm",
    "planted B, 12 seconds, he started defuse, KAY/O flash him",
    "spike A, 38 seconds, four alive, retake through mid urgently",
    "planted B, 23 seconds, their Killjoy placed nano under the spike plant",
    "spike A, 17 seconds, one tapping defuse from pyramids angle",
    "planted B cave, 27 seconds, two pushing from hall side",
    "spike A, 10 seconds, let it go, save the gun instead",
    "planted B, 35 seconds, Harbor wall splits the retake push",
    "spike A, 14 seconds, last one alive, 1v1, he's in A hall",

    # ================================================================
    # COMPOUND — MULTIPLE FACTS UNDER CLUTCH URGENCY
    # ================================================================
    "spike A generator, 20 seconds, one in hell at 30 HP no armor, push him",
    "planted B triple box, 25 seconds, two alive, one tapping, one covering at stairs",
    "last alive, 1v2, spike B workshop, 18 seconds, one has Op one has vandal",
    "spike A dice, 22 seconds, KJ nano and her lockdown both down, we're clean",
    "planted B, 30 seconds, three retaking, sage resed the Jett, now four",
    "spike C platform, 28 seconds, two crossfiring, one on plat one in logs",
    "1v3, spike A, 35 seconds, I'm in heaven, they're all pushing from garden",
    "planted B, 15 seconds, Clove just ulted, Not Dead Yet, she's alive again",
    "spike A, 20 seconds, one in tree at full HP, one in hell at one shot",
    "planted B boathouse, 25 seconds, KAY/O suppressed their Killjoy, no nano",
    "last alive 1v2, spike B, 22 seconds, one is defusing, one watching stairs",
    "spike A back gen, 18 seconds, Viper wall between CT and site still up",
    "planted B market stairs, 30 seconds, Breach rolling thunder stunned two",
    "1v1, spike A, 12 seconds, he's in hell, I'm at pillar, neither can peek safe",
    "planted B, 28 seconds, four retaking, KJ lockdown is the only win",
    "spike C, 20 seconds, Astra's nova pulse landed on our defuser, stunned",
    "planted A, 15 seconds, their Yoru in dimensional drift, 1v1 invisible",
    "spike B default, 23 seconds, two low HP players defusing, rush them",
    "1v3 post-plant, spike A, 38 seconds, I have Jett blade storm, going in",
    "planted B, 12 seconds, Sova ult fired at spike, hit their defuser 120",
    "spike A heaven, 25 seconds, one in hell, one on rafters, crossfire incoming",
    "planted C, 20 seconds, rotating door closed between us, buying 4 seconds",
    "1v2, spike B, 17 seconds, I'm in workshop, they're on stairs and alley",
    "planted A, 30 seconds, four retaking through garden, I need a miracle",
    "spike B, 22 seconds, their Reyna empressed, she's going for ult ace",
    "planted A generator, 28 seconds, KJ nano set on default, and one in tree",
    "1v4 post-plant, spike B, 35 seconds, Killjoy lockdown up, we lose if placed",
    "spike C, 15 seconds, Tejo armageddon targeted on the defuse point",
    "planted B, 20 seconds, he's fake defusing to bait me, I see his gun",
    "spike A, 18 seconds, Skye seekers locked on to me, can't hide anymore",

    # ================================================================
    # 1vX — AGENT-SPECIFIC CLUTCH SCENARIOS
    # ================================================================
    "1v1, their Reyna is in Empress, she has full Devour charges, be ready",
    "1v2, Jett used both dashes, she's grounded now, push her",
    "1v1, their Phoenix used Run It Back before dying, he gets another life",
    "1v2, Yoru placed a gate near C, don't chase the clone",
    "1v3, their Neon has Overdrive still, she's fast and can slide",
    "1v1, their Raze has Showstopper up, don't peek into the open",
    "1v2, Waylay used Convergent Paths, two copies of her are on site",
    "1v3, I'm Iso in Kill Contract, I'm taking one out, cover when I'm done",
    "1v1, their Omen TPed into market, listen for the sound",
    "1v2, Brimstone has Orbital incoming, get off the plant spot",
    "1v1, their Viper pit is still up, play around the wall edges",
    "1v2, Astra in astral form, she's setting up stars behind us",
    "1v3, Harbor Reckoning going down on site, scatter off the spike",
    "1v1, their Clove used Not Dead Yet, she'll respawn if she gets a kill",
    "1v2, KAY/O pressed NULL, both of them are suppressed right now",
    "1v1, their Sova Owl Drone is up, he sees me through the drone",
    "1v2, Breach's Rolling Thunder just launched, everyone get out of mid",
    "1v3, Skye Seekers are homing to me, I can't hide, going aggressive",
    "1v1, their Fade Nightfall is active, I'm marked and deafened",
    "1v2, Gekko Thrash deployed, it's hunting in site right now",
    "1v3, Tejo Armageddon fired at A site, don't go in for 3 seconds",
    "1v1, their Cypher cam is watching the defuse spot, he has info on me",
    "1v2, Killjoy lockdown placed near spike, 13 seconds till it detains",
    "1v1, their Chamber has Tour De Force, Op angle from heaven",
    "1v3, Deadlock Annihilation captured one of ours, pull him out",
    "1v2, Vyse Steel Garden is covering B site, don't run through it",
    "1v1, their Veto used Evolution, upgraded abilities for 10 seconds",
    "1v2, Sage walled B market, buying herself time, go around through alley",
    "1v3, their Reyna dismissed into the corner, she's invisible for a sec",
    "1v1, Iso used Kill Contract, he's pulling me into a duel dimension",

    # ================================================================
    # EXTREME TIME PRESSURE — UNDER 10 SECONDS
    # ================================================================
    "5 seconds on spike, go now or let it blow",
    "4 seconds left, stick the defuse",
    "spike in 3, he's halfway done defusing, rush him",
    "2 seconds on spike, we lose this round",
    "he's defusing, 6 seconds left, I can't stop him",
    "spike in 8, tap it and bait the peek",
    "7 seconds left, he's not defusing yet, we win",
    "6 seconds, abort defuse, save the gun",
    "spike in 5, plant or die trying",
    "9 seconds left, he found me, I'm going down, someone else defuse",
    "8 seconds, they can't defuse in time, hold tight",
    "3 seconds on spike, no one's defusing, we win",
    "7 seconds, I'm defusing, cover me one second",
    "spike in 4, he's at the entrance, I'm not making it",
    "6 seconds on the bomb, stick it",
    "10 seconds, last one defusing, he's gonna make it, rush him now",
    "5 seconds left, he's at half defuse, he might get it",
    "8 seconds, two alive, can't fight and defuse, pick your battle",
    "9 seconds on spike, I'm full committing the defuse",
    "4 seconds, I'm one shot, can't take a hit while defusing",

    # ================================================================
    # CLUTCH ECONOMY CONTEXT — TIMING DECISIONS
    # ================================================================
    "1v2 post-plant, save the rifle, don't fight, let the spike blow",
    "last alive with Op, don't die here, play for the weapon",
    "spike B, 15 seconds, I'm low, not worth dying for the defuse, saving gun",
    "1v3, spike planted, let it go, save the Vandal for next round",
    "I'm 1v1, 8 seconds, he has my gun if I die, going for it anyway",
    "spike in 20, I'm the last alive with a rifle, play for time and gun",
    "1v2, spike A, they're full buy, I have a judge, let the spike blow",
    "post-plant, last alive, they're both full health, I'm saving the Op",
    "spike B, 12 seconds, knife it and get out, not worth losing the rifle",
    "1v3, no gun worth saving, going full aggro for the ace",
    "spike A, 18 seconds, I have the only rifle alive, don't feed it",
    "1v1, he has an eco pistol, I have a Phantom, I should win this",
    "spike in 25, we're both saving, don't engage, let it blow on both ends",
    "1v2, both of them are on sheriffs, I have a Vandal, this is winnable",
    "spike B, 20 seconds, drop the gun at entrance and defuse, gun saves us next",

    # ================================================================
    # CLUTCH UTILITY USAGE — POST-PLANT SPECIFIC
    # ================================================================
    "spike A, 25 seconds, KJ, put nano on default now",
    "spike is down, molly the spike immediately, Brimstone",
    "planted B, 22 seconds, Viper snake bite the defuse point",
    "spike A, one is defusing, KAY/O flash him out now",
    "planted B, Phoenix molly on the spike right now",
    "spike C, Brimstone orbital the defuse spot, 20 seconds left",
    "planted A, Sova shock dart on triple boxes, flush him out",
    "spike B, 18 seconds, Killjoy swarm the plant, he can't defuse through nano",
    "planted A gen, smoke the tree angle, Omen, two clouds",
    "spike B, their defuser is at default, Raze paint shells on him",
    "planted C, 25 seconds, Harbor cove the spike so they can't molly it",
    "spike A, 20 seconds, Breach aftershock through the wall, he's on other side",
    "planted B, Skye guiding light into alley, blind the defuser",
    "spike A, 15 seconds, Astra gravity well on the defuse spot",
    "planted B, 22 seconds, Deadlock gravnet him before he defuses",
    "spike C, Tejo guided salvo on defuse spot, 18 seconds",
    "planted A, Vyse razorvine on the path to the spike",
    "spike B, 20 seconds, Gekko Mosh Pit on the plant point",
    "planted A, 25 seconds, Fade seize the defuser, root him",
    "spike B, Sova hunter's fury on triple box, hit the defuser",

    # ================================================================
    # CLUTCH COMMS — COORDINATION UNDER PRESSURE (RELAY THESE)
    # ================================================================
    "tell them spike B, two alive our side, hold stairs and alley crossfire",
    "tell my team last alive their side is in hell, 20 seconds on spike",
    "let them know I'm defusing, 25 seconds, I need cover in garden",
    "tell them the retake is off, not enough time, save rifles",
    "tell team spike in 15, do not defuse, play for detonation",
    "tell them he's 1 HP on spike, any damage wins, 12 seconds",
    "tell my team their Killjoy lockdown is up, get off site",
    "relay that I'm 1v2, spike A, 22 seconds, need them to distract",
    "tell them I'm planting C, cover the long side, 30 seconds",
    "let them know Sage just rezzed their Jett, now it's 1v2 again",
    "tell my team spike A default, KJ nano on it, hold the retake angles",
    "tell them I tapped him for 80, he's one shot at the defuse spot",
    "relay that their Reyna dismissed, she's repositioning, wait for her",
    "tell them spike in 10, don't trade, play for time",
    "let them know I see two coming garden, they're both full HP",

    # ================================================================
    # POST-PLANT POSITIONING CALLS (SPECIFIC ANGLES)
    # ================================================================
    "spike A gen, play heaven and hell crossfire, 30 seconds",
    "planted B, one from stairs, one from alley, don't clump at spike",
    "spike A, play tree and garden, cut off CT rotation, 25 seconds",
    "planted B, watch market door and workshop angles simultaneously",
    "spike C, two angles: platform and logs, play crossfire",
    "planted A, hell is the hard angle, someone has to hold it",
    "spike B, boathouse and alley crossfire, let them come to us",
    "planted A gen, play off tree, cut retakers before they reach site",
    "spike B, hold the market stairs, don't let them get elevation",
    "planted C, two of us at logs, one at platform, three angles covered",
    "spike A, heaven angle shuts down the whole retake, hold it",
    "planted B, workshop holds the back, stairs holds the CT, standard",
    "spike C, long side and link are the two retake paths, watch both",
    "planted A, garden player must die before they reach heaven, stop him",
    "spike B, alley is the sneaky retake, someone camp it, 28 seconds",

    # ================================================================
    # FALSE-PRESSURE / NEGATIVE CALLOUT SAVES (STILL RELAY)
    # ================================================================
    "spike A, 30 seconds, nothing else, they gave up the retake",
    "planted B, 25 seconds, nobody retaking, we win this, play it out",
    "spike B, they all died, two seconds ago, defuse freely",
    "planted C, 22 seconds, last retaker is dead, I saw the kill feed",
    "spike A, 40 seconds, one of them AFKed, they have four alive",
    "planted B, 35 seconds, tell them Sage can't rez this round, she used ult",
    "spike A, 28 seconds, their Killjoy lockdown is on cooldown, no threat",
    "planted B, 20 seconds, KJ lockdown expired, push now",
    "spike A, 15 seconds, their Viper pit is fading, get ready to defuse",
    "planted B, 18 seconds, smoke went away, defuse window just opened",
    "spike A, 22 seconds, they have no utility left, raw retake only",
    "planted C, 30 seconds, two of them tilt-saving, they won't fight",
    "spike B, 25 seconds, their only alive player is 12 HP no armor",
    "planted A, 20 seconds, their Jett has no dashes left, she's grounded",
    "spike B, 15 seconds, KAY/O suppressed both of their last two players",

    # ================================================================
    # CLUTCH CALLOUTS WITH STREAMER SELF-REPORT
    # ================================================================
    "I'm 30 HP no armor, defusing spike B, 12 seconds, covering me would help",
    "I have 50 HP, Op in hand, holding hell, 25 seconds on spike",
    "I'm full HP full armor, 1v1, spike A, 20 seconds, I take this",
    "I'm out of abilities, 1v3, spike B, 18 seconds, raw aim only",
    "I have one vandal mag left, 1v2, making it count",
    "I'm on knife, 100 HP, sprinting to plant, 15 seconds left",
    "I have 12 HP, he's one shot, I need to trade before I drop",
    "I'm behind generator, full HP, he doesn't know I'm alive",
    "I have no smokes left, 1v2, going in raw",
    "I'm 5 HP, defusing, he's somewhere in garden, praying",
    "I have Jett ult charged, 1v3, sending it right now",
    "I'm holding B stairs, 80 HP, they have to come through me",
    "I have Op, 1v2, playing the corner in boathouse, 22 seconds",
    "I'm 60 HP, defusing A, one alive somewhere on the map",
    "I have Reyna empress active, 1v3, going for the ace clutch",

    # ================================================================
    # MIXED URGENCY — DISFLUENT / CLIPPED STREAM CALLOUTS
    # ================================================================
    "spike, 20 seconds, two of them, one in hell one in tree",
    "planted, 25 left, he's defusing, nano him KJ",
    "last alive, spike B, 18, two coming market",
    "1v3, 30 seconds, spike down, I need picks",
    "spike A, 15, one shot in hell, push him before he heals",
    "planted B, 22, defuser, flash him, Breach",
    "1v2, spike, 20, both full, I'm at 30 HP",
    "30 seconds on bomb, two alive, retake or let it blow",
    "spike down, 12, he's on it, rush him from garden",
    "last alive, 1v1, 8 seconds, spike not planted yet, going",
    "planted, 25, no nano, no lockdown, we're playing raw",
    "spike A gen, 18, three retaking, I can't hold all angles",
    "1v2, B, 22 seconds, Op in my hands, playing corner",
    "planted, 15, sage walled, they bought 6 seconds",
    "spike, 10, last one, he's going for defuse",
    "1v3, 35 seconds, spike B, I have KJ lockdown",
    "planted A, 20, heaven player, Op, smoking it now",
    "spike in 28, three alive, everyone hold your angle",
    "last alive, 1v2, 18 seconds, spike not down, this is ugly",
    "planted B, 22 seconds, three retaking, KJ lockdown is the play",

    # ================================================================
    # MULTI-ROUND STATE CONTEXT — CLUTCH WITH ECO STAKES
    # ================================================================
    "1v3, eco round, spike B, they're full buy, let the spike blow and save",
    "spike A, 20 seconds, we're on guns, they're on pistols, take the fight",
    "last alive, full buy, 1v2, they're on eco, don't let them get the weapon",
    "spike B, 25 seconds, if we lose this we're in eco hell, need the win",
    "1v1, their Jett has the Op, I can't duel that, stall and let spike blow",
    "planted A, 18 seconds, we're all pistol vs their rifles, miracle retake",
    "spike B, 30 seconds, if we can get this round we're match point",
    "last alive, 1v2, match point for them, spike not planted, 25 seconds",
    "1v3, spike A, 20 seconds, this is match point, giving it everything",
    "planted, 15 seconds, if we win this it's 12-12, overtime on the table",
    "spike B, 22 seconds, last chance before pistol, hold it",
    "1v2, spike A, 28 seconds, I have a rifle, they don't, this is winnable",
    "last alive, force buy round, 1v3, spike planted, 18 seconds",
    "planted B, 25 seconds, we saved our guns, they didn't, now we retake",
    "spike A, 20 seconds, Thrifty win incoming if we hold this",

    # ================================================================
    # RAPID-FIRE CLUTCH PHRASES (MAXIMUM BREVITY UNDER STRESS)
    # ================================================================
    "spike A, 20 left, one alive, play it",
    "planted, 18, defusing, rush him",
    "1v2, spike B, 25, both CT entry",
    "last alive, 30, spike down, hold",
    "spike A, 10, let it blow",
    "planted, 15, no retake, we got it",
    "1v1, spike B, 12, he's one shot",
    "spike A, 20, nano on it, safe",
    "planted, 22, four coming, rotate",
    "1v3, 35, spike A, need picks",
    "spike B, 8, stick or go",
    "planted, 18, garden, tree, two angles",
    "1v2, 20, both full, I'm low",
    "spike A, 12, he's defusing, flash",
    "planted B, 25, alley and stairs",
    "1v1, spike, 10, I'm going for it",
    "spike A, 30, sage wall blocked garden",
    "planted, 20, KJ lockdown, scatter",
    "1v2, B, 18, Op in hand, playing corner",
    "spike, 15, nobody retaking, win",

    # ================================================================
    # ABILITY-GATED CLUTCH — ABILITY STATE DETERMINES WIN CONDITION
    # ================================================================
    "spike A, 20 seconds, their KJ used lockdown, we can't retake for 13 seconds",
    "planted B, 25 seconds, their Viper used pit, site is toxic, wait for wall",
    "spike A, 18 seconds, Astra cosmic divide cut us off from garden rotation",
    "planted B, 22 seconds, Sage used wall, market entry is sealed for now",
    "spike A, 30 seconds, Breach's rolling thunder just cleared A main, push",
    "planted B, 15 seconds, KAY/O NULL suppressed all three retakers",
    "spike A, 20 seconds, Skye seekers locked one of them, rush that side",
    "planted B, 25 seconds, Sova recon lit up the defuser, he's in workshop",
    "spike A, 18 seconds, Fade Nightfall marked and deafened the retakers",
    "planted B, 22 seconds, Tejo armageddon on the retake path, blocked",
    "spike A, 30 seconds, Harbor Reckoning placed on site, can't retake yet",
    "planted B, 15 seconds, Gekko Thrash hunting in CT entry, retake blocked",
    "spike A, 20 seconds, Veto Evolution charged, he has buffed abilities now",
    "planted B, 25 seconds, Deadlock Annihilation thread caught the entry fragger",
    "spike A, 18 seconds, Vyse Steel Garden covering the spike, can't get close",
    "planted B, 22 seconds, Clove picked up health, she's back to 75, careful",
    "spike A, 15 seconds, their Cypher cam watching from garden window angle",
    "planted B, 28 seconds, Chamber Tour De Force op deleted our second player",
    "spike A, 20 seconds, Iso Kill Contract pulled our best player out of site",
    "planted B, 18 seconds, Waylay split into two, two fake versions covering spike",

    # ================================================================
    # ENVIRONMENTAL + MAP-MECHANIC CLUTCH
    # ================================================================
    "spike A, 20 seconds, A door just broke, they're flooding through",
    "planted B, 25 seconds, B market door is closed, forces alley retake",
    "spike A, 18 seconds, mid panel broken, new sightline opens on tree",
    "planted B, 22 seconds, A vent door broken on Split, someone's flanking",
    "spike A, 30 seconds, rope ascender on B hell, defender taking high ground",
    "planted C, 20 seconds, rotating door on Lotus closed, blocked one path",
    "spike B, 25 seconds, fall edge on Abyss, pushed him off the bridge",
    "planted A, 18 seconds, Abyss vent door intact, he can't get through fast",
    "spike B, 22 seconds, Lotus zipline used, quick rotation to B possible",
    "planted A, 15 seconds, garden window is broken, new angle into heaven",
    "spike A, 28 seconds, B door on Ascent still intact, buying rotation time",
    "planted B, 20 seconds, Corrode flooded path slows the retake down",
    "spike A, 18 seconds, split rope gives heaven access fast, watch top",
    "planted B, 25 seconds, Fracture's dual rope flanks complicate the retake",
    "spike A, 22 seconds, Lotus third door just rotated open between B and C",

    # ================================================================
    # HIGH-VARIANCE CLUTCH — UNUSUAL SCENARIOS
    # ================================================================
    "1v5, they have full utility, spike planted, 40 seconds, miracle needed",
    "five alive their side, spike B, 35 seconds, no util on our side",
    "1v1 ace attempt, I've killed four, last one in hell, spike A, 20 seconds",
    "spike A, 30 seconds, I just got an ace and I'm still planting",
    "last alive, spike planted, 25 seconds, I'm watching all five retake paths alone",
    "1v4, I have KJ lockdown, placing it on spike, win condition right here",
    "spike B, 20 seconds, their last alive has the Op and is in heaven",
    "1v3, spike A, 28 seconds, I have Sage ult, rezzing myself not an option",
    "planted B, 15 seconds, their whole team is alive, we have two alive only",
    "spike A, 22 seconds, KAY/O in NULL mode, all five enemies suppressed",
    "1v2, both on sheriff on eco, I have Phantom, they can still two-tap me",
    "spike C platform, 18 seconds, they have four alive and all abilities",
    "planted B, 25 seconds, I'm the only one alive and I have the rifle",
    "1v5, spike not planted yet, 30 seconds, going for the most impressive play",
    "spike A, 20 seconds, Sova ultimate hunterís fury incoming through the wall",

    # ================================================================
    # RETAKE ABORT / WAVE-OFF CALLS
    # ================================================================
    "spike B, 8 seconds, do not retake, save weapons",
    "planted A, 5 seconds, let it blow, not worth dying",
    "spike B, 10 seconds, retake is off, too many of them, save",
    "planted C, 7 seconds, one retaker, two alive their side, abort",
    "spike A, 6 seconds, KJ lockdown is still active, don't go in",
    "planted B, 9 seconds, Viper pit will kill us before we defuse, wave off",
    "spike C, 4 seconds, let it detonate, we have rifles, that matters more",
    "planted A, 11 seconds, their Sage is rezzing, it'll be 2v1 by the time you land",
    "spike B, 7 seconds, I'm the only one alive, not going to make it",
    "planted C, 6 seconds, I have no hp to survive the push, letting it go",

    # ================================================================
    # FINAL EDGE CASES — WEIRD BUT REAL CLUTCH MOMENTS
    # ================================================================
    "1v1, he's defusing and doesn't know I'm alive, sneaking up",
    "spike A, I lost track of the timer, someone call it",
    "planted B, I see him but I'm out of ammo, knife rush",
    "1v2, spike, I accidentally popped my ult early, now I'm in the duel",
    "last alive, Clove here, I died, waiting on Not Dead Yet trigger",
    "spike B, their Yoru clone just walked past spike, don't shoot it",
    "planted A, 20 seconds, I have 1 HP, playing around info only",
    "1v3, spike not planted, 30 seconds, looking for an off-angle pick",
    "spike B, I tapped defuse, he peeked, I killed him, now I'm sticking it",
    "planted A, 18 seconds, Gekko Wingman is defusing, Wingman kill needed",
    "1v1, spike B, 15 seconds, he's fake defusing, I see the animation stopped",
    "spike A, 22 seconds, I killed three but they were on eco, their two rifles alive",
    "planted B, 20 seconds, I'm behind the spike, he'll step on me to defuse",
    "1v2, spike A, 25 seconds, one of them is 1 HP confirmed from kill feed",
    "spike B, 18 seconds, I hear him sprinting, he's rushing the defuse",

    # ================================================================
    # ADDITIONAL CLUTCH — POST-PLANT READS AND COUNTER-PLAYS
    # ================================================================
    "spike A, 23 seconds, he's using the window angle to watch the defuse",
    "planted B, 27 seconds, their last player has the Operator from heaven",
    "spike B, 21 seconds, Killjoy turret still alive watching the plant spot",
    "planted A, 16 seconds, one in hell, one at garden entry, both covering spike",
    "spike C, 33 seconds, their Harbor hasn't used Reckoning yet, save room",
    "planted B, 19 seconds, he's behind the boathouse pillar, flush him out",
    "spike A, 24 seconds, smoke is fading on the garden angle, be ready",
    "planted B, 13 seconds, two alive, but their Sage used ult already",
    "spike A, 29 seconds, Sova recon arrow still active, tagged my position",
    "planted B, 26 seconds, one tapping spike, one in alley, don't let him bait you",
    "spike A, 11 seconds, one alive, 12 HP, he can't fight just defuse",
    "planted B, 36 seconds, KJ lockdown landing in 8 seconds, scatter",
    "spike C, 16 seconds, Clove meddle landed on our defuser, ability blocked",
    "planted A, 21 seconds, Fade haunt spotted me behind generator",
    "spike B, 34 seconds, Cypher tripwire on the approach to defuse spot",
    "planted A, 17 seconds, Viper snake bite ticking on default plant position",
    "spike B, 29 seconds, Harbor cove protecting spike, they played it well",
    "planted C, 13 seconds, I can defuse but the Nano will kill me mid-way",
    "spike A, 31 seconds, two playing crossfire from heaven and hell simultaneously",
    "planted B, 23 seconds, one in workshop, Op angle into site, can't push blind",

    # ================================================================
    # ADDITIONAL 1vX — SPECIFIC COUNT AND CONDITION
    # ================================================================
    "1v2, spike A, 24 seconds, one is 40 HP, one is full health",
    "last alive 1v3, spike B, 31 seconds, all three near market entry",
    "1v2, spike C, 19 seconds, one on platform, one on logs",
    "1v1, spike A, 26 seconds, he's behind generator with a ghost pistol",
    "1v3, spike B, 22 seconds, two have rifles, one is on a judge",
    "last alive, 1v2, spike A, 17 seconds, both holding defuse from garden",
    "1v1, spike C, 28 seconds, he used Reyna leer, don't peek into it",
    "1v2, spike A, 13 seconds, one is 5 HP kill-feed confirmed, find him",
    "last alive 1v3, spike B, 35 seconds, I have two bullets in the vandal",
    "1v1, spike A, 20 seconds, he has Omen paranoia, don't chase blind",
    "1v2, spike B, 16 seconds, one is defusing, one covering from stairs",
    "last alive 1v3, planted C, 30 seconds, going for the plays",
    "1v1, spike A, 22 seconds, I baited him to shoot the Sage wall, he's reloading",
    "1v2, spike B, 27 seconds, both Dismissing and Devour charges used on Reyna",
    "last alive 1v4, spike A, 38 seconds, I have four bullets and a dream",

    # ================================================================
    # ADDITIONAL TIMER-CRITICAL — EXACT SECOND CALLOUTS
    # ================================================================
    "spike in 45 seconds, they haven't planted yet, we're stalling them",
    "spike in 40 seconds, they're walking toward default, stay back",
    "spike in 35 seconds, they're trying to force plant under pressure",
    "planted, 33 seconds, play patient, let them overextend to defuse",
    "spike in 28 seconds, two alive their side, one might lurk to plant",
    "planted B, 24 seconds, don't push yet, let them come to the angles",
    "spike A, 21 seconds, I hear footsteps in garden, someone's flanking",
    "planted, 19 seconds, fake tap spike and hide beside the generator",
    "spike B, 16 seconds, their defuser is crouching to the plant",
    "planted, 11 seconds, if he doesn't defuse in 3 seconds we win",
    "spike A, 8 seconds, I started defuse, 4 seconds to finish, spike 8 left",
    "planted B, 6 seconds, he's at half defuse, stopping, I lost comms",
    "spike in 3 seconds, plant just finished, they're too late to defuse",

    # ================================================================
    # ADDITIONAL CLUTCH — AGENT CALLOUTS UNDER PRESSURE
    # ================================================================
    "1v2, their Iso used Kill Contract, now it's a 1v1 duel, spike A, 22 seconds",
    "spike B, 20 seconds, their Waylay used Convergent Paths, two of her on site",
    "1v1, planted A, 18 seconds, he's Phoenix and used Run It Back, he gets another life",
    "spike B, 25 seconds, Neon has Overdrive, she's sliding around at full speed",
    "1v3, planted A, 30 seconds, Sova Owl Drone up, he sees everything I do",
    "spike B, 22 seconds, Tejo Stealth Drone confirmed one of us at stairs",
    "1v2, planted C, 17 seconds, Fade Haunt tracked me to my hiding spot",
    "spike A, 28 seconds, Gekko Wingman started defusing, kill the Wingman",
    "1v1, planted B, 20 seconds, KAY/O used NULL, he's suppressed, pushing",
    "spike A, 15 seconds, Breach Fault Line stunned me mid-defuse, abort",
    "1v2, planted B, 24 seconds, Skye Seekers locked on to me, running",
    "spike A, 19 seconds, Veto Chokehold deafened, I can't hear footsteps",
    "1v3, planted B, 33 seconds, Miks Bassquake going off, disorienting the retake",
    "spike A, 21 seconds, Deadlock Sonic Sensor near the plant, don't make noise",
    "1v1, planted B, 26 seconds, Chamber Trademark trip right at the defuse spot",
]
