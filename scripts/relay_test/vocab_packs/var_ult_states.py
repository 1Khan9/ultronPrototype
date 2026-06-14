"""Vocab pack: ultimate ability states for the relay test corpus.

Domain: Ult readiness, ult activation, ult expiry/burn, ult tracking (own team
and enemy), orb counts, save-ult directives, ult-for-execute coordination, ult
economy calls, ult-status questions, and ult-impact reads — across all 29
Valorant agents.

All items are KIND=relay: the streamer is commanding Ultron to relay the
information or directive to teammates. Covers the full register spectrum:
terse snap-adjacent ("their Clove has ult"), mid-length tactical reads,
longer opinion/strategy lines, slang-heavy, region-neutral, multi-fact
compound lines, and first-person streamer self-reports.

Phrasing variety maximized: imperative relay triggers ("tell my team", "let my
team know", "warn my team", "tell everyone", "tell them", "tell the guys",
"remind our team", "call out", "let the team know", "pass on"), no near-dupes.
"""

ITEMS = [
    # -----------------------------------------------------------------------
    # JETT — Blade Storm (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Jett has blade storm ready, she is going to op without penalty",
    "let my team know Jett just used her ult, no more free knives this round",
    "tell the guys Jett blade stormed and whiffed, her ult is gone",
    "warn my team the enemy Jett has ult up and an operator, she is a two-shot machine right now",
    "tell my teammates our Jett is one orb away from blade storm",
    "tell my team Jett burned her ult on that last duel and died, pure waste",
    "let them know their Jett has knives, do not peek long",
    "call out that Jett has full ult this round, she anchors heaven",
    "tell my team we tracked their Jett using blade storm, safe to peek now",
    "remind the team to watch for Jett opping with her ult after she killed last round",
    "tell my team Jett has no ult, her aggression on long is just raw aim now",
    "let everyone know their Jett used blade storm bot side and is out of charges",
    "tell my team that kill gave Jett her ult back, she has knives again",
    "warn them Jett just activated blade storm, do not dry peek any long angles",
    "tell the squad their Jett is two kills off her ult, she is nearly there",

    # -----------------------------------------------------------------------
    # PHOENIX — Run it Back (6 pts)
    # -----------------------------------------------------------------------
    "tell my team their Phoenix has run it back up, engage him and kill him fast or he respawns",
    "let my team know Phoenix ulted into site, we have ten seconds to kill him before he comes back",
    "tell them Phoenix run it back just expired without him dying, he got a safe entry for nothing",
    "warn my team Phoenix has ult, treat every duel with him like it costs us two lives",
    "tell the squad Phoenix ult is down, he died and did not respawn, we are even",
    "call out that our Phoenix has ult and will entry if he dies he just resets full HP",
    "tell my team Phoenix used run it back and we killed him in ult so he is gone for real",
    "let my teammates know their Phoenix has ult saved for this execute, expect him to int in",
    "remind our team that Phoenix ult timer ran out without a kill, free ult wasted",
    "tell my team their Phoenix is one kill away from ult, deny him the frag",

    # -----------------------------------------------------------------------
    # RAZE — Showstopper (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Raze has showstopper up, do not clump in the doorway",
    "let my team know Raze rocket just went off, her ult is burned and she has no escape",
    "warn them Raze has ult this round, she is going to blast into site",
    "tell my teammates our Raze fired showstopper and cleared the corner, push now",
    "call out Raze ult is gone, she used it mid last round getting one kill, terrible value",
    "tell them Raze has showstopper and satchels, she can boost and fire in one move",
    "let my team know our Raze saved ult all pistol round and has it banked for this full buy",
    "tell the squad enemy Raze used her rocket into smoke and missed, ult wasted",
    "remind my team Raze showstopper is up, she takes heaven with a boost and fires down",
    "tell my team their Raze has ult, she one-taps the entry before we even get through the smoke",

    # -----------------------------------------------------------------------
    # REYNA — Empress (6 pts)
    # -----------------------------------------------------------------------
    "tell my team their Reyna has empress ready, one kill and she goes infinite",
    "let them know Reyna popped empress on the B push, she is in chain-kill mode right now",
    "warn my team Reyna has ult and just took a fight, if she gets that frag she will clear the site",
    "tell my teammates empress faded, she never got a second kill, ult totally wasted",
    "call out Reyna empress is active, do not peek her one at a time, trade immediately or bail",
    "tell the guys their Reyna has ult banked every round, she saves it for retakes",
    "let my team know our Reyna lost empress without a kill this round, no sustain",
    "tell my team Reyna dismissed out of empress because she had no souls, ult is still running",
    "warn them Reyna is in empress and invisible after that dismiss, she is flanking",
    "tell my team empress timed out, she is back to normal, push her now",
    "let them know Reyna needs one more orb for empress, do not let her get that kill",
    "tell my teammates our Reyna has ult and is two kills off syncing it with site entry",

    # -----------------------------------------------------------------------
    # YORU — Dimensional Drift (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Yoru just went into dimensional drift, he is invisible and gathering info",
    "let them know Yoru ult is active, he cannot shoot but he can see our positions",
    "warn my team Yoru is ulting near B, he will exit with a flash, do not look toward B site",
    "tell my teammates Yoru dimensional drift just ended, he came out and flashed heaven",
    "call out Yoru ult is down, he exited and we can see him now",
    "tell my team their Yoru has ult every round, he runs into site invisible to get info and leaves",
    "let my team know Yoru is coming out of his ult at their flank, he is behind A main",
    "tell the squad Yoru dimensional drift used, no recon invisibility for the rest of the round",
    "remind them Yoru cannot take damage in ult, do not waste your bullets on the roaming shadow",
    "tell my team Yoru ult cooldown done, he has drift again going into overtime",

    # -----------------------------------------------------------------------
    # NEON — Overdrive (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Neon just hit overdrive, she is beaming and sprinting simultaneously",
    "let them know Neon ult is active, she has perfect accuracy while running at full speed",
    "warn my team Neon overdrive is up and she is pushing short, play off the smoke or she deletes you",
    "tell my teammates our Neon used overdrive to clear the site entry, push through now",
    "call out Neon ult down, she got the two kills but overdrive ran out",
    "tell my team Neon is beaming through the smoke, stay out of the center line",
    "let them know their Neon has ult banked and smokes are up, she is doing a solo A execute",
    "tell the guys Neon slide reset during overdrive, she has another slide charge right now",
    "remind my team overdrive timer extends on kills, she is still beaming after two frags",
    "tell my team Neon ult is on cooldown, this is our window to take site without the beam",

    # -----------------------------------------------------------------------
    # ISO — Kill Contract (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Iso has kill contract ready, he is going to pull one of us into the arena",
    "let them know Iso launched kill contract and pulled our Jett, it is a 1v1 right now",
    "warn my team Iso has ult, if he contracts you it is a 4v4 on site while you duel",
    "tell my teammates Iso lost the kill contract, he is dead and we are full five again",
    "call out our Iso won the duel inside contract, he comes back at 100 HP",
    "tell my team their Iso has ult and double tap shield, he is a full tank duelist right now",
    "let them know Iso contracted Sage, they are both in the arena, push site now with the 5v3",
    "tell my team Iso kill contract expired with no one inside, he failed to pull anyone",
    "remind them Iso ult does not cost the team a player if he wins, he comes back alive",
    "tell my team Iso has ult and undercut, he will suppress us before he contracts someone",

    # -----------------------------------------------------------------------
    # WAYLAY — Convergent Paths (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Waylay has convergent paths ready, she zones the whole site entry",
    "let them know Waylay just used her ult, the beam is expanding and slowing everyone in the radius",
    "warn my team Waylay ult is active on A site, the hinder debuff is in the entire entry corridor",
    "tell my teammates our Waylay has convergent paths up, she fires it before the flash and we go in",
    "call out Waylay ult is down after she got two kills with it and the beam expired",
    "tell the guys their Waylay used convergent paths to zone our rotation, that bought them the plant",
    "let my team know Waylay ult is banked, she has beacon and ult, she can beam and snap back",
    "tell my team Waylay is boosted from convergent paths speed, she is closing in fast",
    "remind my teammates the hinder from Waylay ult reduces fire rate too, not just movement",
    "tell them Waylay has ult up plus two dashes, she is at full kit this round",

    # -----------------------------------------------------------------------
    # SOVA — Hunter's Fury (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Sova has hunter's fury ready, do not stack in any single corridor",
    "let them know Sova fired his ult through the wall and hit two of our team",
    "warn my team Sova fury is active, three beams left, stay off the long angles where he can line up",
    "tell my teammates Sova used all three beams and got zero hits, his ult is wasted",
    "call out Sova hunter's fury is down after the plant, we can retake without worrying about beams",
    "tell my team our Sova has ult and a recon bolt on spike, we can coordinate the fury with info",
    "let them know Sova needs two more orbs for hunter's fury, he almost has it",
    "tell my team their Sova saved ult all first half and now has it charged plus the bonus",
    "remind my team Sova fury hits through every wall on this map, do not hide behind cover",
    "tell them Sova fury revealed someone it hit, they are lit up on our screens",

    # -----------------------------------------------------------------------
    # BREACH — Rolling Thunder (9 pts)
    # -----------------------------------------------------------------------
    "tell my team their Breach has rolling thunder, massive concuss zone on any site entry",
    "let them know Breach ult just went off under the smoke, our whole team is knocked up and concussed",
    "warn my team Breach has rolling thunder ready, do not group in the B chokepoint",
    "tell my teammates our Breach has ult, we time it for when they push and they are all airborne",
    "call out rolling thunder is done, Breach fired it into nothing in mid trying to clear the box",
    "tell my team Breach ult needs one more point, he is almost there after that last kill",
    "let them know the rolling thunder concuss duration is six seconds, do not push back until it ends",
    "tell the squad Breach ult is expensive at nine points, he has been saving four rounds",
    "remind my team our Breach rolling thunder goes wide, we execute A after he ults the entry",
    "tell them Breach ult knocked everyone up at short and they all took fall damage",

    # -----------------------------------------------------------------------
    # SKYE — Seekers (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Skye has seekers up, three homing birds that nearsight on contact",
    "let them know Skye launched seekers and all three hit, every enemy is nearsighted right now",
    "warn my team Skye ult is active, do not push without cover or you will be blinded mid-fight",
    "tell my teammates our Skye used seekers for info, we know where all three enemies are",
    "call out Skye seekers are down after they shot two of them out of the air",
    "tell my team their Skye has ult and double hawk, she has so much flash this round",
    "let them know one seeker slipped through and nearsighted our entry, he is fighting blind",
    "tell my team Skye seekers track the nearest three enemies, split up or you all get hit",
    "remind them Skye needs eight orbs, she has been picking up every one on the map",
    "tell my team their Skye just hit seekers for two, one enemy is full vision and one is nearsighted",

    # -----------------------------------------------------------------------
    # KAY/O — NULL/cmd (7 pts)
    # -----------------------------------------------------------------------
    "tell my team Kayo just overloaded, all enemies in range are suppressed every three seconds",
    "let them know Kayo null command is active, their side cannot use any abilities for fifteen seconds",
    "warn my team Kayo has null cmd ready, he fires it and then we all rush while they have no util",
    "tell my teammates Kayo went down during his ult, get to his body and revive him",
    "call out Kayo ult is over, he lived through null cmd and we won the fight in the suppression window",
    "tell my team their Kayo has ult and already placed his knife, they have double suppression ready",
    "let them know Kayo needs one more orb for null cmd, stop letting him pick up mid orb",
    "tell my team Kayo overloaded and pushed with us but died before we got a revive, ult wasted",
    "remind them Kayo gets a combat stim inside null cmd so he is faster and shoots faster",
    "tell them null cmd pulses every three seconds, the suppress is not constant, listen for the pulse",
    "tell my team Kayo has ult banked from last round pistol win, he has null cmd ready round three",

    # -----------------------------------------------------------------------
    # FADE — Nightfall (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Fade has nightfall ready, that wave deafens and decays everyone it touches",
    "let them know Fade ult hit three of them on retake, they are all trailed and decayed",
    "warn my team Fade nightfall is active on site, their prowlers will lock onto our terror trails",
    "tell my teammates our Fade used nightfall for info and confirmed four enemies A, execute B",
    "call out Fade nightfall is done, she told us how many it hit and we rush now",
    "tell my team their Fade has ult plus prowlers, that is a guaranteed nearsight chain on any trailed enemy",
    "let them know Fade needs nightfall and still has two rounds of orb grinding ahead",
    "tell my team Fade fired nightfall into the smoke but the wave passed without hitting anyone",
    "remind my team terror trails from Fade ult last twelve seconds, do not move predictably",
    "tell them Fade nightfall hit four and she called it on voice, they are all deafened and trailing",

    # -----------------------------------------------------------------------
    # GEKKO — Thrash (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Gekko has thrash ready, if it lunges into a group all those players are detained",
    "let them know Gekko launched thrash and piloted it into their CT stack, three detained right now",
    "warn my team Gekko ult is active, he is driving thrash toward site and will detain whoever it hits",
    "tell my teammates our Gekko used thrash and detained two defenders, push now before the three seconds end",
    "call out Gekko thrash is done, he drove it into a smoke and it detonated on nothing",
    "tell my team Gekko will try to reclaim the thrash globule after detonation, save him time to grab it",
    "let them know Gekko has ult and can reclaim it for a second thrash later in the round",
    "tell my team enemy Gekko piloting thrash is vulnerable, his body is in spawn and he can be traded",
    "remind my team Gekko thrash detain lasts three seconds, burst them down before they break free",
    "tell them Gekko reclaimed thrash globule already, he has his ult charge back in fifteen seconds",

    # -----------------------------------------------------------------------
    # TEJO — Armageddon (9 pts)
    # -----------------------------------------------------------------------
    "tell my team their Tejo has armageddon ready, that airstrike sweeps a full corridor",
    "let them know Tejo ult is going off on A main, the damage wave is moving toward short",
    "warn my team Tejo armageddon is active, he is drawing the line through the chokepoint right now",
    "tell my teammates our Tejo used armageddon post-plant on the spike and no one could defuse",
    "call out Tejo ult is burned, he swept mid but they moved perpendicular and only took one hit",
    "tell my team their Tejo has ult and guided salvo, he can hit two locations simultaneously then drop airstrike",
    "let them know Tejo needs nine orbs for armageddon, most expensive initiator ult in the game",
    "tell my team Tejo fired armageddon across the site and cleared everyone in the back corner",
    "remind them move perpendicular to the airstrike line or take 60 times four damage per segment",
    "tell my team Tejo armageddon is up and he is saving it for the post-plant hold on B",

    # -----------------------------------------------------------------------
    # CYPHER — Neural Theft (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Cypher has neural theft, he will activate it on any corpse and reveal us all",
    "let them know Cypher just stole intel, two reveal waves going out, get off your positions",
    "warn my team Cypher ult is active on that body, change positions immediately after the first scan",
    "tell my teammates our Cypher used neural theft and confirmed three enemies in garage plus two B",
    "call out Cypher neural theft is done, two full waves revealed, now we know their setup",
    "tell my team enemy Cypher needs our corpses to ult, do not die in exposed positions",
    "let them know Cypher ult gave away their entire back-line positions, rotate accordingly",
    "tell my team Cypher has ult ready, he will pull it on the first kill we get and get full read",
    "remind my team neural theft reveals in two waves, move between the two scans to throw off the info",
    "tell them Cypher ult is on cooldown after that steal, we have a window to reset positions",

    # -----------------------------------------------------------------------
    # SAGE — Resurrection (7 pts)
    # -----------------------------------------------------------------------
    "tell my team our Sage has rez ready, if anyone dies on site entry she brings them back full HP",
    "let them know Sage is rezzing our Sova at the back of site right now, hold the line for four seconds",
    "warn my team their Sage has resurrection, do not let her stand next to any body uncontested",
    "tell my teammates Sage rez is done, our Cypher is back up and he has his turret available",
    "call out Sage just rezzed their carry Jett, do not give up the trade",
    "tell my team their Sage has ult banked and is anchoring B site, kills there are not permanent",
    "let them know save our Sage rez for the best player alive, not the first body you see",
    "tell my team Sage does not have ult yet, she is three kills short, kills this round matter",
    "remind my team Sage and target are both vulnerable during the rez animation, flash the rez",
    "tell them Sage ult is on seven points, she saves rez until the round gets critical",
    "tell my team their Sage just rezzed with no backup and our team killed both of them, nice",

    # -----------------------------------------------------------------------
    # KILLJOY — Lockdown (9 pts)
    # -----------------------------------------------------------------------
    "tell my team their Killjoy has lockdown, if she places it on site all attackers are detained in 13 seconds",
    "let them know Killjoy placed lockdown at the spike, protect the box or we all get detained",
    "warn my team Killjoy ult is ticking, shoot the device or we cannot move or shoot for eight seconds",
    "tell my teammates our Killjoy has lockdown and is going to force a retake with it, fall back to safety",
    "call out Killjoy lockdown was destroyed before it went off, great timing on that",
    "tell my team enemy Killjoy has ult ready and is waiting for us to push before she plants it",
    "let them know Killjoy ult went off while they were on site, all three enemies were detained, go",
    "tell my team Killjoy lockdown covers the entire bomb site radius, there is no safe corner inside",
    "remind my team protect the KJ device once it is down, one bullet destroys the whole lockdown",
    "tell them Killjoy has ult every two rounds because she keeps dying for nothing, bad ult economy",
    "tell my team their Killjoy ult is burned, she panicked and planted it with no enemies on site",

    # -----------------------------------------------------------------------
    # CHAMBER — Tour De Force (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Chamber has tour de force ready, he has a custom sniper that one-shots anywhere",
    "let them know Chamber just activated his ult, five shots and every body shot through shield is a kill",
    "warn my team Chamber ult is up and he is holding A long, he two-taps our whole team before we cross",
    "tell my teammates our Chamber used tour de force and cleared heaven, push the site now",
    "call out Chamber ult is done, he fired all five shots and got two kills, we can rotate op-side safely",
    "tell my team Chamber has ult plus trademark plus rendezvous, he is completely self-sufficient on that angle",
    "let them know Chamber opped someone with ult and a slow field just appeared at the kill location",
    "tell my team enemy Chamber needs his ult and we should deny him orb picks whenever possible",
    "remind them Chamber slow field from ult kills lands at every body, watch your feet",
    "tell my team their Chamber burned ult on an eco with full buy, terrible decision",

    # -----------------------------------------------------------------------
    # DEADLOCK — Annihilation (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Deadlock has annihilation ready, do not let her get a close-range shot on anyone",
    "let them know Deadlock hit the nanowire and our Raze is cocooned and being pulled",
    "warn my team Deadlock ult is active, her nanowire cocoon pulls whoever it hits toward death, shoot the cocoon",
    "tell my teammates our team broke the cocoon before it hit the endpoint, Raze is free",
    "call out Deadlock annihilation is done, she missed the initial shot completely",
    "tell my team enemy Deadlock has ult saved for the plant phase, she cocoons anyone trying to defuse",
    "let them know Deadlock launched annihilation from behind their smoke and cocooned Sage mid-rez",
    "tell my team Deadlock ult is on cooldown after that fire, we have this round safe",
    "remind my team break the cocoon fast, it pulls toward the kill point in seven seconds",
    "tell them Deadlock has ult and barrier mesh and gravnet, she is a full lockdown sentinel this round",

    # -----------------------------------------------------------------------
    # VYSE — Steel Garden (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Vyse has steel garden ready, if it goes off all our primaries are jammed for eight seconds",
    "let them know Vyse just fired steel garden, all rifles are jammed, swap to pistols and keep moving",
    "warn my team Vyse ult is active on B site, primaries are useless in there right now",
    "tell my teammates our Vyse used steel garden on the A rush and four rifles jammed instantly",
    "call out steel garden is done, the eight second jam expired, rifles are back online",
    "tell my team enemy Vyse has ult banked and has been saving razorvines on spike, it is a death trap site",
    "let them know Vyse ult does not jam Jett knives, Neon beam, or Chamber ult gun, those still work",
    "tell my team their Vyse used steel garden on eco and did not kill anyone, terrible ult waste",
    "remind my team the jam lasts eight seconds, do not try to push into the site with primaries locked",
    "tell them Vyse has ult ready and is defending with arc rose flash and shear wall, do not dry push",

    # -----------------------------------------------------------------------
    # VETO — Evolution (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Veto just evolved, he is immune to every status effect and regenerating",
    "let them know Veto ult is active, do not flash him, do not stun him, just aim for the head",
    "warn my team Veto has evolution ready, if he pops it during our push every util we throw is useless",
    "tell my teammates our Veto evolved and held the retake alone, nothing we threw stuck to him",
    "call out Veto ult is done, he died mid-fight and evolution ended with him",
    "tell my team enemy Veto has ult and is going to absorb our full execute utility and fight through it",
    "let them know Veto evolved before our breach thunder went off so the concuss did nothing",
    "tell my team their Veto ult lasts until he dies, it has no timer so he sits in evolved state all post-plant",
    "remind my team evolution does not stop Jett knives or Neon beam damage, still aim true",
    "tell them Veto has ult banked two rounds in a row, he keeps getting eco kills and building charges",

    # -----------------------------------------------------------------------
    # BRIMSTONE — Orbital Strike (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Brimstone has orbital strike ready, he drops it and the zone is unenterable for four seconds",
    "let them know Brimstone is dropping orbital on spike, do not try to defuse for the next five seconds",
    "warn my team Brimstone orbital is incoming on B site, clear the zone or take 570 damage",
    "tell my teammates our Brimstone used orbital to clear CT corner and they had to bail",
    "call out Brimstone orbital strike is done, zone is safe again",
    "tell my team enemy Brimstone has ult saved for post-plant, he will drop it the moment we start defusing",
    "let them know Brimstone fired orbital into his own team's smoke by accident, total friendly fire zone",
    "tell my team their Brimstone used orbital mid to force us off the box and it worked",
    "remind my team Brimstone orbital has a two-second delay after he places it before damage starts",
    "tell them Brimstone ult is on eight points, he is always close to having it because of all those deaths",

    # -----------------------------------------------------------------------
    # VIPER — Viper's Pit (9 pts)
    # -----------------------------------------------------------------------
    "tell my team their Viper has pit ready, she will plant inside it and the whole site decays and nearsights",
    "let them know Viper pit is up on A site, do not push in, she sees you but you are nearly blind in there",
    "warn my team Viper is leaving her pit, we have an eight-second window before the cloud collapses",
    "tell my teammates our Viper used her pit post-plant and the defenders could not get in without dying to decay",
    "call out Viper pit is down, she left for more than eight seconds and it collapsed",
    "tell my team enemy Viper has ult and is going to set up the post-plant hold we cannot beat without rushing",
    "let them know force Viper out of pit, she loses advantage in eight seconds after she exits",
    "tell my team Viper pit nearsights everyone inside except her, she has full vision while you have none",
    "remind my team Viper needs nine orbs for pit, she has been playing for economy all half",
    "tell them Viper pit is active and the spike is inside it, this defuse is a death sentence without a full rush",
    "tell my team Viper burned pit early on the B rush and now has no ult for post-plant, exploit that",

    # -----------------------------------------------------------------------
    # OMEN — From the Shadows (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Omen has from the shadows ready, he can teleport anywhere on the map",
    "let them know Omen is ulting B site, destroy the shade that appears or he arrives and flanks us",
    "warn my team Omen shade appeared at CT, he is trying to teleport in behind us, kill the shade",
    "tell my teammates our Omen ulted flank and distracted them while we executed A",
    "call out we killed the Omen shade, his ult is wasted and he is stuck wherever he cast it",
    "tell my team enemy Omen used from the shadows as a fake and cancelled it, pure mindgame",
    "let them know Omen ult puts a shade at the destination for four seconds before he arrives",
    "tell my team their Omen has ult up and seven smokes ready, he is a full utility controller right now",
    "remind my team Omen fake ult cancel is a real tactic, do not rotate just because you hear the cast",
    "tell them Omen ult is on seven points, he gets it fast because his smokes recharge and he lives long",

    # -----------------------------------------------------------------------
    # ASTRA — Cosmic Divide (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Astra has cosmic divide ready, she can wall the entire site in half with bullet-blocking",
    "let them know Astra just placed cosmic divide, that wall lasts twenty-one seconds and blocks every bullet",
    "warn my team Astra divide is up, no wallbangs, no intel through the wall, and audio is cut",
    "tell my teammates our Astra used divide to split A site and cut off the CT rotation",
    "call out cosmic divide is fading, we have about five seconds before the wall drops",
    "tell my team enemy Astra has ult and four stars placed, she controls five positions simultaneously",
    "let them know Astra divide audio block is real, they cannot hear our spike timer countdown through the wall",
    "tell my team their Astra fired cosmic divide in a bad angle and split two non-critical areas",
    "remind my team Astra divide blocks bullets from both sides, our riflers cannot shoot through it either",
    "tell them Astra has divide and nova pulse, she stuns then splits, our whole execute collapses",

    # -----------------------------------------------------------------------
    # HARBOR — Reckoning (7 pts)
    # -----------------------------------------------------------------------
    "tell my team their Harbor has reckoning up, that water surge nearsights and slows everything in its path",
    "let them know Harbor ult is active, the water wave is pushing through B main and we are all nearsighted",
    "warn my team Harbor reckoning is incoming, it moves fast now, get off the main corridor",
    "tell my teammates our Harbor used reckoning to push through short and it hit four enemies",
    "call out Harbor ult is done, the wave passed and three enemies are nearsighted for three seconds",
    "tell my team enemy Harbor has ult banked for the forced push into our smoke wall, be ready",
    "let them know Harbor stopped his reckoning in place after hitting the choke, it lingers there now",
    "tell my team their Harbor used ult as a distraction while Jett entry fragged from heaven",
    "remind my team Harbor reckoning nearsight lasts three seconds per enemy hit, rush after it clears",
    "tell them Harbor has ult and cove and high tide, he can plant through anything",

    # -----------------------------------------------------------------------
    # CLOVE — Not Dead Yet (8 pts)
    # -----------------------------------------------------------------------
    "tell my team their Clove has not dead yet ready, kills on her this round are provisional",
    "let them know Clove just died and she is ulting, she is coming back and needs a kill in ten seconds",
    "warn my team Clove is reviving, kill her before she gets a frag or she stays alive the rest of the round",
    "tell my teammates our Clove rezzed herself on B site and immediately headshot the last defender",
    "call out Clove not dead yet failed, timer ran out with no kill, she is permanently dead",
    "tell my team enemy Clove has ult every round at eight points, she plays recklessly because death means nothing",
    "let them know Clove is back and she smoked from her grave too, she is smoker and reviver in one",
    "tell my team their Clove activated not dead yet but we are all alive and we outnumber her 5v1",
    "remind my team the Clove ult timer is ten seconds, pressure her before she can secure a kill",
    "tell them Clove ult down, she got the kill but she is at 30 HP and has no support",
    "tell my team Clove has not dead yet and still has her ruse smokes, she is an anchor nightmare",

    # -----------------------------------------------------------------------
    # CROSS-AGENT ULT TRACKING — GENERAL STATE CALLS
    # -----------------------------------------------------------------------
    "tell my team nobody on their side has ult right now, this is our clean execute window",
    "let them know three enemies have ult charged, do not force a fight this round",
    "warn my team that their Killjoy and Viper both have ult, the post-plant will be a disaster",
    "tell my teammates we need to track their ult economy, they have been saving orbs all half",
    "call out we won every ult duel this half, their ult econ is crushed going into second half",
    "tell my team two of their ults are one kill off, deny them the frags on B main",
    "let them know half their roster has ult and they are going to execute in the next two rounds",
    "tell my team we have four ults available, this is the round to spend them all coordinated",
    "remind my team do not save ult all game, it costs us rounds when we are too scared to pop them",
    "tell them one player on their team has been holding ult for six rounds, it is probably a big play",

    # -----------------------------------------------------------------------
    # ULT ECONOMY — SAVE AND SPEND DIRECTIVES
    # -----------------------------------------------------------------------
    "tell my team save ult for when we are on a buy round, do not pop it on eco",
    "let my teammates know pop your ult this round, we have nothing to lose on this force",
    "tell my team save Chamber ult for the A long angle, do not waste it on a close fight",
    "warn my team do not use Sage rez until we absolutely need it, save it for the carrier",
    "tell them hold Kayo ult for the execute, we need the suppression window to get on site clean",
    "tell my team Sova fury is worth spending now, they are all stacked at the default plant",
    "let them know do not waste Breach thunder on one person, wait until they cluster",
    "tell my team burn your ult this round, it resets on the buy round and we are not buying",
    "remind my team picking up every orb on the map makes our ult econ significantly better",
    "tell my team save Viper pit for defense this round, we should not eco with our strongest post-plant tool",
    "tell them do not pop ult until Sage confirms she has rez, so if you die on entry she brings you back",

    # -----------------------------------------------------------------------
    # ULT READINESS ANNOUNCEMENTS — ATTACKER EXECUTES
    # -----------------------------------------------------------------------
    "tell my team I have ult ready, I will blade storm into site on the execute call",
    "let them know Sova just confirmed ult, recon bolt shows four A, execute B on my go",
    "tell my teammates all four of us have ult this round, we hardforce B with everything",
    "call out our ult count is stronger, we go now before they save up to match us",
    "tell my team ult up, everyone ready, we execute A in five seconds on the flash",
    "let them know we have Breach ult and Jett ult, Breach rolling thunder first then Jett blades in",
    "tell my team Gekko has thrash and I have showstopper, we double ult into B and they cannot survive it",
    "remind my team coordinate ults before the execute, popping them one at a time wastes the impact",
    "tell them I am one kill away from ult, let me get a pick before we run the execute",
    "tell my team Sage has rez and Kayo has null cmd, if I die on entry Sage rezzes and Kayo suppresses retake",

    # -----------------------------------------------------------------------
    # ULT READINESS ANNOUNCEMENTS — DEFENDER RETAKE
    # -----------------------------------------------------------------------
    "tell my team save Astra divide for the retake, drop it to split site as we push back in",
    "let my team know Killjoy will drop lockdown on retake, we need three seconds to let it tick",
    "tell my teammates I have Viper pit on retake, let me get to the spike before they defuse",
    "warn my team Yoru has ult, he will drift in during the retake and gather positions on all of us",
    "tell my team use Sage rez on retake if we can get the body safely, that is a 6v4 trade",
    "let them know I am popping Chamber ult on retake, five shots in the narrow site entry",
    "tell my team Skye seekers on retake will nearsight anyone holding the site angles",
    "remind my team KJ lockdown forces them off spike on retake without us even being on site",
    "tell them we have two ults for retake, Breach thunder to clear the site, then KJ lockdown to freeze them",
    "tell my team this is a no-ult retake, we go in raw and rely on crossfires, ults are saved for next round",

    # -----------------------------------------------------------------------
    # ULT ORB PICKUP INSTRUCTIONS
    # -----------------------------------------------------------------------
    "tell my team grab the A site orb on your way in, one of us needs ult this round",
    "let them know the orb is still up mid, someone should grab it before they take mid control",
    "tell my teammates pick up B orb before we plant, Sage needs one more point for rez",
    "call out the top mid orb is available and their Sova runs past it every round without grabbing",
    "tell my team deny them the A site orb this round, it gives their KJ lockdown too fast",
    "let them know Kayo grabbed both orbs on his push and has null cmd already round four",
    "tell my team Raze is sitting on the B orb every round, she has been full ult since round two",
    "remind my teammates orbs give one point each and the free charge from round start is one point, plan around it",
    "tell them stop letting their Reyna take B site orb unchallenged, that is empress on round three",
    "tell my team grab the B site orb while we plant, we need Sage ult before the next buy round",

    # -----------------------------------------------------------------------
    # ENEMY ULT INTEL CALLS — SPECIFIC PATTERN READS
    # -----------------------------------------------------------------------
    "tell my team their Killjoy saves ult for three rounds then spends it, we are at round three",
    "let them know their Jett has ult every round because she picks up every orb on map, deny her A main",
    "warn my team their Sage saves rez specifically for their carry player, do not let that trade happen",
    "tell my teammates their Omen fake ults at the start of every execute to trigger a rotation, do not fall for it",
    "call out their Phoenix uses run it back aggressively on every pistol, play passive pistol round",
    "tell my team their Viper has never had ult before round six this half, she uses it early and cannot reload",
    "let them know their Clove pops not dead yet the instant she dies, call her out immediately so we kill her again",
    "tell my team their Breach thunder is always paired with an Omen smoke, expect them together",
    "remind my team their Deadlock saved annihilation three rounds in a row, she fires it on retake this round",
    "tell them their Fade nightfall is always combined with prowlers, trail hit means a nearsight is coming",

    # -----------------------------------------------------------------------
    # POST-ULT CALLS — BURNT ULT CONFIRMS
    # -----------------------------------------------------------------------
    "tell my team their Killjoy ult was burned and only hit one player, terrible value, rush now",
    "let them know Viper pit collapsed after they baited her out of it, site is contestable",
    "tell my teammates Breach rolling thunder went off but all four of us were behind the smoke, clean dodge",
    "call out enemy Omen ult shade was killed, he wasted from the shadows and is stuck at the start",
    "tell my team Raze showstopper missed completely, no ult pressure left this round",
    "let them know Skye seekers were all shot down before hitting anyone, full waste",
    "tell my team Reyna empress faded after two kills, she never got the third and the timer ran dry",
    "remind my team their Phoenix run it back was used and he died in it, that is a full ult gone",
    "tell them Harbor reckoning hit zero people because we peeled out of the corridor, now push",
    "tell my team their Astra divide ended, wall is down, rifles work on both sides again, go now",
    "tell my teammates Kayo went down in null cmd and no one revived him in time, ult gone and down a man",

    # -----------------------------------------------------------------------
    # OWN TEAM ULT WASTE / COMMUNICATION ISSUES
    # -----------------------------------------------------------------------
    "tell my team we need to coordinate ults before using them, two people burned theirs for one kill total",
    "let them know we burned Sage rez on someone who was about to die anyway, save rez for round-defining moments",
    "tell my teammates do not pop Breach ult when there is only one enemy in range, it costs nine orbs",
    "warn my team Jett used blade storm on an eco and got the same result a Vandal would have, ult wasted",
    "tell my team use your ult before you die with it, you burn nothing keeping it at end of round",
    "let them know we lost three ults this half because players died with them saved, use your util",
    "tell my team Sova fury was burned when they were behind solid cover, three beams zero hits",
    "remind my team Cypher neural theft only works on a dead body within range, do not use it from spawn",
    "tell my team KJ lockdown was planted outside the spike range, the detained enemies could not defuse anyway",
    "tell them we need to decide ult order before round start, not in the middle of the push",

    # -----------------------------------------------------------------------
    # MULTI-AGENT ULT STACK READS
    # -----------------------------------------------------------------------
    "tell my team they have Breach ult and Astra divide and Viper pit all ready, do not execute this round",
    "let them know we have Sage rez, Kayo null cmd, and Jett blade storm, this is our power spike round",
    "tell my team four of them have ult, including Killjoy lockdown, this is not our round to force",
    "warn my teammates their combined ult value this round is five versus our zero, take a slow round",
    "call out both ult carriers on their side have it charged at the same time for the first time this game",
    "tell my team we should spend our three ults on this execute since they have no ults to answer with",
    "let them know their double ult with Phoenix run it back plus Sage rez means kills are temporary this round",
    "tell my team their Killjoy and Cypher both have ult, that is detain plus full reveal, information nightmare",
    "remind my team if we burn both ults and lose the round we go into overtime ult-poor, pick the timing carefully",
    "tell them stack our ults on B this round, they have no ult on B side and we overwhelm them",

    # -----------------------------------------------------------------------
    # ULT TRACKING BETWEEN HALVES
    # -----------------------------------------------------------------------
    "tell my team their Jett goes into second half with ult banked from pistol, watch round thirteen",
    "let them know we should note who on their team built ult on the last round of the half",
    "tell my teammates track which of their agents have ult going into round thirteen, it changes the read",
    "warn my team their KJ was one kill off ult at halftime, she charges it round one defense",
    "tell my team their Sova picks up every orb and starts second half ready to fury round one",
    "let them know our Sage died with ult on round twelve, she does not carry it into second half",
    "tell my team in overtime both teams start with clean ult states, do not assume anyone has it charged",
    "remind my team some ults carry between halves if the player is alive at round end, pay attention",
    "tell my team their Reyna was one frag short of empress at halftime, she charges it during the pistol",
    "tell them going into overtime we need to track ult orbs earned per round from scratch, reset your counts",

    # -----------------------------------------------------------------------
    # UNUSUAL / NICHE ULT STATE SCENARIOS
    # -----------------------------------------------------------------------
    "tell my team Clove used not dead yet but got the kill at nine point nine seconds, she is alive on one HP",
    "let them know Iso contracted someone and won the duel inside, he is back with 100 HP and no ult",
    "tell my teammates Gekko reclaimed his thrash globule, he can use it again after a fifteen second cooldown",
    "warn my team Yoru is in dimensional drift and he is placing his tether behind B site, expect a teleport",
    "tell my team Phoenix run it back respawned him at the back of site right behind our defuse position",
    "let them know their Neon overdrive timer reset twice on kills, she has been in ult for twenty-five seconds",
    "tell my team KJ lockdown is down but no one on site was detained because we all moved outside the radius",
    "call out Reyna empress does not expire on kills, it only ends if she stops getting frags, she is still active",
    "tell my teammates Deadlock cocooned our Jett and their team is shooting the cocoon to free her, help",
    "tell my team Cypher activated neural theft in the middle of a firefight, the two reveal waves are going out now",
    "tell my team Astra tried to use cosmic divide but she was not in astral form, ult on cooldown but never fired",

    # -----------------------------------------------------------------------
    # PHRASING VARIETY — DIFFERENT RELAY TRIGGERS
    # -----------------------------------------------------------------------
    "warn my team the enemy Viper just used her pit, site is locked",
    "pass on that Jett has blade storm, we wait before peeking A long",
    "tell everyone Sage has rez and is guarding the main plant point",
    "let the guys know their Phoenix is running it back right now, hold fire",
    "tell the team Kayo null cmd is active, all enemy abilities are suppressed",
    "shout out that Astra divide just dropped, bullets are blocked",
    "call out Clove is reviving, kill her in the next eight seconds",
    "give my team the heads up that Harbor has reckoning up this round",
    "let them know our Breach is two kills off rolling thunder, it is close",
    "make sure my team knows Chamber has tour de force this round",
    "tell the squad Killjoy ult ticking, protect the box or we all get detained",
    "let my teammates know their Reyna popped empress with no kills available, bad timing on her part",
    "tell my team Sova fury is charged and we have recon confirming four B, we execute A clean",
    "pass along that our KJ lockdown is ready and she is going to retake A site with it",
    "let everyone know Yoru finished his drift, he is visible now and on our right flank",
    "relay to my team that Viper pit collapsed because she chased someone off site",
    "tell my team Skye used seekers for information and all three hit, we have full enemy map read",
    "give the team the heads up that Tejo has armageddon but he needs a clear line on the corridor",
    "tell my squad Deadlock cocooned their best player, break the thread and free him immediately",
    "tell my teammates their Waylay has convergent paths, do not stack the chokepoint this execute",

    # -----------------------------------------------------------------------
    # FIRST-PERSON STREAMER ULT SELF-REPORTS (RELAY TO TEAM)
    # -----------------------------------------------------------------------
    "tell my team I have my ult ready this round, Jett blade storm, I will entry on your flash",
    "let my team know I just used blade storm and burned through their whole site stack",
    "tell my teammates I am one kill away from ult, give me the first fight",
    "tell my team I have ult but I am saving it for if they get on site, do not rush me",
    "let them know I just wasted my ult on a phantom in the smoke, I am sorry, pushing without it",
    "tell my team I have Reyna empress ready, if I get one kill I chain them all",
    "tell them I burned my ult on the pistol to save the round, I have no ult this buy round",
    "tell my team I have Sage rez ready, tell me who should get priority if we need it",
    "let my team know I have Kayo null cmd and I will use it on the A execute, go in behind the suppression",
    "tell my team I am three kills off my ult, I need those frags before we commit",
    "tell my teammates I have Viper pit and I want to anchor B, let me set up post-plant",
    "let them know I spent my ult getting us out of that eco clutch, I rebuild it this round",
    "tell my team I have Breach ult for the force buy, we use it on the rush and win on raw util",
    "tell them I have Skye seekers up and I will launch them before our entry goes in",
    "let my team know I have ult but if I die saving it I lose it forever, let me pop it now",

    # -----------------------------------------------------------------------
    # SLANG-HEAVY REGISTER
    # -----------------------------------------------------------------------
    "tell my team their Jett has knives, do not dry peek anything",
    "let them know Reyna is in empress mode, she is snowballing right now",
    "tell my squad KJ box is ticking, break it or get detained",
    "warn my team Breach is about to ult, get out of the line",
    "tell my guys Viper pit is active, do not int into the site",
    "let my team know their KAY/O is overloading, abilities are off for 15",
    "tell my team Sage is rezzing, buy her four seconds",
    "warn them Phoenix is running it back, do not assume he is dead yet",
    "tell my team Deadlock cocooned him, shoot the thread",
    "let my team know Clove is NDY-ing, kill her again before she gets a frag",
    "tell my squad Yoru went invis, he is gathering info right now",
    "warn my team Harbor ult is active, the wave is moving through short",
    "tell my team Raze just shot the showstopper into the lobby, nobody in there anymore",
    "let them know Astra divide is up, audio is cut and bullets are blocked on both sides",
    "tell my team Skye seekers popped on three of them simultaneously, rush while they are blind",

    # -----------------------------------------------------------------------
    # LONGER STRATEGIC / OPINION ULT LINES (OFF-SNAP REGISTER)
    # -----------------------------------------------------------------------
    "tell my team honestly their Sage has been holding rez four rounds straight waiting for the clutch moment",
    "let my team know I think they are saving every ult they have for a force buy round soon",
    "tell my teammates in my opinion we should hold our Breach ult for two more rounds and use it on a full buy",
    "tell my team the reason we keep losing site retakes is that their KJ pops lockdown the moment we enter",
    "let them know I have been tracking their ult orb pickups and their Sova hits fury every other round",
    "tell my team going into overtime we should spend our first ult on the pistol if we get a good angle",
    "tell my teammates honestly I messed up burning showstopper on that eco push, I own that fully",
    "let my team know if we can force them to burn Viper pit on this round then the next round is clean",
    "tell my team in my read their Chamber saves tour de force specifically for whenever we try to take A long",
    "tell my team I think Sage and Kayo should coordinate ult together because rez plus suppression is brutal",
    "let them know I feel like we have not been picking up the A orb enough, it is costing us ult economy",
    "tell my team their Reyna is a one-trick who only knows how to play with empress active, force her to fight without it",
    "tell my teammates I want to call a timeout because our ult timings are completely out of sync this half",
    "let my team know the longer we let this go the more ults stack on their side, we need to force now",
    "tell my team they are playing around having five ults on the same round and we need to deny them that moment",

    # -----------------------------------------------------------------------
    # ADDITIONAL ULT STATES — AGENT-SPECIFIC DEPTH
    # -----------------------------------------------------------------------

    # Jett extra
    "tell my team their Jett burned blade storm trying to get an entry on A main and got traded instantly",
    "let my teammates know our Jett has ult and will activate knives the moment the flash lands",
    "tell them Jett has blade storm but she is shaking and will probably whiff all of them",
    "tell my team Jett no ult this round, her blade storm charges reset next round after that kill",
    "let my team know their Jett stockpiles ult and only uses it with operator in hand for a double threat",

    # Reyna extra
    "tell my team their Reyna just started empress without any soul orbs in range, she cannot sustain it",
    "let them know Reyna empress refreshed on that kill, she has two more soul orbs floating near her body",
    "tell my team their Reyna has empress ready but she is not getting kills today so it is a dead ability",
    "warn my team Reyna empress and dismiss together make her untouchable for a few seconds",
    "tell my teammates Reyna is out of empress, timer ran dry and she has zero orbs now",

    # Raze extra
    "tell my team Raze showstopper is primed but she is waiting for their smoke to fade before firing",
    "let them know Raze saved showstopper all eco half, she has had it charged since round four",
    "tell my team their Raze fired the rocket at the wall corner and it bounced back, full ult wasted",
    "tell my teammates our Raze has ult this force, we go B with showstopper leading the way",
    "let my team know Raze showstopper clears boxes on site, rush in right after the explosion settles",

    # Phoenix extra
    "tell my team their Phoenix is going to int the first fight because run it back makes death consequence-free",
    "let them know Phoenix run it back timer is almost out, six seconds, kill him before it expires naturally",
    "tell my team Phoenix used his ult solely for information this round, he drifted into site and came back",
    "warn my team their Phoenix will flash and wall before he activates run it back on every big fight",
    "tell my teammates Phoenix ult is charged on round two because he picked up both orbs pistol round",

    # Neon extra
    "tell my team their Neon has overdrive and is pairing it with fast lane walls for a solo double execute",
    "let them know Neon overdrive beam does not need to stop moving, it has zero spread while sprinting",
    "tell my team Neon burned overdrive getting one kill and two misses, horrendous ult value",
    "warn my team Neon has ult and relay bolt stun, she stuns then beams through the smoke",
    "tell my teammates our Neon has overdrive ready, she goes in first and clears the corridor before we follow",

    # Iso extra
    "tell my team Iso launched kill contract at our Reyna, classic double duel elimination attempt",
    "let them know Iso kill contract is a 1v1 duel, whoever loses is gone for the rest of the round",
    "tell my team their Iso has kill contract and double tap shield stacked, he is a full duelist kit right now",
    "warn my team Iso has ult and Iso starts kill contract with double tap active now after the patch",
    "tell my teammates our Iso won the contract and is back at 100 HP, that is a net positive trade",

    # Waylay extra
    "tell my team their Waylay has convergent paths but she uses it defensively to zone attackers off the site entry",
    "let them know Waylay ult speed boost makes her close distance faster than almost any agent",
    "tell my team Waylay hinder from convergent paths reduces jump speed so they cannot climb boxes to escape the beam",
    "warn my team Waylay has ult ready and she has refract beacon placed at CT, she beams then snaps back",
    "tell my teammates their Waylay used convergent paths to slow our whole execute team at the entry simultaneously",

    # Sova extra
    "tell my team Sova hunter's fury can be spaced, he does not have to fire all three beams at once",
    "let them know their Sova fired fury one at a time to avoid wasting beams, he still has two left",
    "tell my team Sova fury second beam hit two of us, we are both lit and revealed through the wall",
    "warn my team Sova ult reveals on hit, if you get hit by a beam your position broadcasts to them",
    "tell my teammates Sova has ult and owl drone ready, he droned for info then fires fury to confirm the kills",

    # Breach extra
    "tell my team their Breach rolling thunder covers a 25 meter wide cone, the whole entry is inside the zone",
    "let them know Breach ult knocked our entire team airborne simultaneously, they pushed freely through it",
    "tell my team Breach thunder plus Neon beam is a deadly combo, stunned and beamed with no counterplay",
    "warn my team their Breach saves rolling thunder for the retake push every time, not the execute",
    "tell my teammates our Breach should fire rolling thunder to the left of the choke so it catches more bodies",

    # Skye extra
    "tell my team their Skye seekers home to the three nearest enemies, split into separate rooms to waste them",
    "let them know Skye ult used, three seekers out, they hit two of us before we could shoot them down",
    "tell my team Skye seekers slow Jett dash now, her escape is gimped when seekers are active",
    "warn my team Skye has ult and two hawk flashes, she can clear site with information and vision before entry",
    "tell my teammates Skye seekers confirmed three enemies back site, they are not playing aggressive",

    # KAY/O extra
    "tell my team null cmd suppresses enemies every three seconds on a pulse, they do not stay suppressed the full fifteen",
    "let them know their Kayo overloaded and is now in combat stim, he is faster and shoots faster during ult",
    "tell my team Kayo went down in null cmd at B site, revive him or we lose the suppression halfway through",
    "warn my team their Kayo uses null cmd defensively on retake to wipe our abilities off site",
    "tell my teammates Kayo has ult and knife, he suppresses then null cmds for double ability lockout",

    # Fade extra
    "tell my team Fade nightfall hit and four enemies are trailed, her prowlers will lock onto those trails instantly",
    "let them know their Fade uses nightfall as an information tool, not a damage tool, she always has more details than us",
    "tell my team Fade ult deafened our team too, we cannot hear footsteps or ability sounds for the duration",
    "warn my team Fade nightfall plus prowlers is a guaranteed nearsight chain on anyone who takes a trail hit",
    "tell my teammates Fade burned nightfall on one person who immediately died, zero tempo from that ult",

    # Gekko extra
    "tell my team Gekko is piloting thrash right now, his body is exposed in attacker spawn, someone flank him",
    "let them know their Gekko reclaimed the thrash globule, he can thrash again in fifteen seconds",
    "tell my team Gekko thrash detained three defenders simultaneously, we have a free plant window",
    "warn my team Gekko ult is back up from reclaiming the globule, he can use it a second time this round",
    "tell my teammates our Gekko has ult and dizzy, he blinds with dizzy then detains with thrash for a free site take",

    # Tejo extra
    "tell my team Tejo armageddon sweeps along a drawn line, move perpendicular to the strike direction",
    "let them know their Tejo uses armageddon to clear the back of site so defenders cannot hold post-plant",
    "tell my team Tejo ult costs nine points, he barely has it and will not have it again for two rounds",
    "warn my team Tejo fired armageddon along the B corridor wall, the entire lane is a damage zone right now",
    "tell my teammates our Tejo has armageddon and guided salvo both ready, we have massive post-plant capability",

    # Cypher extra
    "tell my team Cypher neural theft reveals all living enemies in two waves, change positions between the scans",
    "let them know Cypher needs a body in range for his ult, he cannot activate it from spawn distance",
    "tell my team their Cypher ult confirmed two enemies B site and three at CT, full info read",
    "warn my team Cypher neural theft is available and he has a body to use it on near mid,  move positions now",
    "tell my teammates Cypher has ult every round because he stays alive behind his camera the whole game",

    # Sage extra
    "tell my team Sage rez prioritizes the best player alive, do not use it on someone who will die again immediately",
    "let them know their Sage is stalling the rez until her team clears the angle on the body",
    "tell my team Sage rez at full HP means we trade one dead player for a living one at max health",
    "warn my team their Sage is anchoring C site with rez ready, killing one of our players there is not permanent",
    "tell my teammates Sage rez is on cooldown after she just used it, no more revivals this round",

    # Killjoy extra
    "tell my team Killjoy lockdown radius covers an entire bomb site, there is no corner safe from detention",
    "let them know their Killjoy planted the lockdown device then immediately died, it still goes off in thirteen seconds",
    "tell my team KJ lockdown device can be destroyed before it triggers, focus fire on the box",
    "warn my team Killjoy ult device can be placed through her own team smokes, they cannot see where it landed",
    "tell my teammates KJ lockdown is going off in five seconds, we all need to be off site or we cannot shoot",

    # Chamber extra
    "tell my team Chamber tour de force gives him five shots and any upper body hit is a one-shot kill",
    "let them know their Chamber has ult and is playing the same A long angle he has held all game",
    "tell my team Chamber ult slow field from kills covers the spike and prevents defuse even after he dies",
    "warn my team Chamber has tour de force and full teleport anchors, he is a fortress on that angle",
    "tell my teammates Chamber ult is down, he used all five shots getting two kills, rush A long now",

    # Deadlock extra
    "tell my team Deadlock annihilation cocoon has 600 HP, shoot it fast or the target dies at the endpoint",
    "let them know their Deadlock uses annihilation on the defuser who starts the animation, not the entry fragger",
    "tell my team Deadlock ult pull lasts seven seconds, break the cocoon before it reaches the kill point",
    "warn my team Deadlock has annihilation and is waiting for one of us to start defusing before she fires it",
    "tell my teammates our team broke the cocoon just in time, Jett is free and the ult was wasted",

    # Vyse extra
    "tell my team Vyse steel garden jams primary weapons but players can still use pistols and abilities",
    "let them know their Vyse ult lasts eight seconds, stay on pistols and do not peek until primaries come back",
    "tell my team Vyse steel garden hit mid-push and four of our rifles locked up simultaneously",
    "warn my team their Vyse has ult and shear wall and razorvines, her kit literally traps the entry player",
    "tell my teammates Vyse ult is done, eight second jam expired, rifles are back, push immediately",

    # Veto extra
    "tell my team Veto evolution is indefinite, it does not have a timer, it lasts until he dies",
    "let them know their Veto evolved and walked through our entire stun and slow and flash and nothing landed",
    "tell my team Veto ult immunity does not cover Jett blade storm damage, knives still hit him for full damage",
    "warn my team their Veto has evolution banked and is about to push through our full utility execute",
    "tell my teammates Veto ult down, he died mid-fight and evolution ended, good trade on that",

    # Brimstone extra
    "tell my team Brimstone orbital requires line of sight to the sky, he cannot use it inside any roofed structure",
    "let them know Brimstone orbital landed right on spike, nobody can defuse until the four second window ends",
    "tell my team their Brimstone uses orbital every round on the same post-plant position, adjust the plant",
    "warn my team Brimstone orbital strike is incoming on B site, run left or right out of the zone",
    "tell my teammates Brimstone ult has a two-second arrival delay, start moving the moment you hear the audio cue",

    # Viper extra
    "tell my team Viper pit is the best post-plant ult in the game and they are about to prove it again",
    "let them know Viper went outside her pit, she has eight seconds before the cloud dies, push now",
    "tell my team Viper pit nearsight reduces vision to a few meters, she can see our glowing outlines inside it",
    "warn my team inside Viper pit her Decay floors us at 1 HP, a single bullet from anywhere finishes us",
    "tell my teammates Viper pit is gone, she stayed out too long, site is fully open now",

    # Omen extra
    "tell my team their Omen fake-ulted to B to trigger our rotation then is hitting A, do not bite",
    "let them know Omen is teleporting through the wall to CT, destroy the shade in four seconds",
    "tell my team Omen from the shadows has a four-second window where the shade is visible and destroyable",
    "warn my team their Omen saves from the shadows specifically to appear behind our post-plant lineup",
    "tell my teammates Omen ult shade is destroyed, he is locked in place, good denial on that",

    # Astra extra
    "tell my team Astra cosmic divide lasts twenty-one seconds, it is the longest wall ability in the game",
    "let them know Astra divide blocks audio too, their spike timer countdown cannot be heard through it",
    "tell my team their Astra uses divide to split A site and force one side to fight through closed angles",
    "warn my team Astra divide is up and she has stars on both entry points, she controls both sides simultaneously",
    "tell my teammates Astra ult is down, divide expired, both sightlines are open and bullets fly again",

    # Harbor extra
    "tell my team Harbor reckoning moves 25 percent faster now after the recent patch",
    "let them know their Harbor held reckoning in place this time by reactivating it mid-wave",
    "tell my team Harbor ult nearsight lasts three seconds per target, do not rush into the site mid-nearsight",
    "warn my team Harbor has reckoning and storm surge, he stuns then waves and we have no util to answer",
    "tell my teammates Harbor ult hit zero people because we all rotated away from the corridor in time",

    # Clove extra
    "tell my team their Clove abuses not dead yet on every entry attempt, she dies five times a game and revives twice",
    "let them know Clove ult activation is manual after death, she chooses whether to revive or concede the kill",
    "tell my team their Clove rezzed herself in a 1v3 and somehow got the kill to sustain, we need to focus her",
    "warn my team Clove can still smoke after she activates not dead yet while she is in the revival window",
    "tell my teammates Clove ult failed because we killed her instantly after the revival before she could frag",

    # -----------------------------------------------------------------------
    # EXTENDED CROSS-AGENT AND SITUATIONAL VARIETY
    # -----------------------------------------------------------------------
    "tell my team their support players all have ult charged, this is a coordinated utility round incoming",
    "let them know both teams go into overtime with equal ult counts for the first time this match",
    "tell my team we should try to make them spend ults defending eco rounds so we face clean buys",
    "warn my teammates three of them have ult and we have zero, play slow and let one tick out before engaging",
    "tell my team pick up the B orb on every push even if it costs half a second, the ult economy shift matters",
    "let them know their carry has had ult six out of twelve rounds this half, they prioritize orbs for her",
    "tell my team we go hard this round specifically because neither of their ult players has it charged",
    "tell my teammates track their Jett ult because she spends it freely and we should exploit the cooldown window",
    "let my team know I think they are planning a full five-ult spend on round fifteen, hold back this round",
    "tell my team our ult usage was terrible that half, we spent nine ults for four total kills across all of them",
    "warn my team they baited us into popping four ults on a fake execute and hit B completely clean",
    "tell my teammates we are winning the ult economy right now, do not throw it by forcing bad rounds",
    "let them know their Sage has kept rez alive for five rounds without using it, she is waiting for the perfect moment",
    "tell my team Clove and Sage on the same team means kills are doubly provisional, every frag could come back",
    "tell my team their Killjoy and Cypher both have ult, a full site take this round gives us lockdown and full reveal",
    "let my team know we should deny them the A long orb every round because Chamber ult on A long is game-losing",
    "tell my team we have more ults than them right now, we need to spend them before the round balance shifts",
    "warn my teammates their entire strategy this half has been banking ults and spending them in pairs",
    "tell them I want to reset ult economy this half by playing passive and forcing them to spend theirs first",
    "tell my team we won because their key ults expired with no value spent, do not let that happen to us",
    "let my team know I have been tracking every orb pickup on their side and their Raze has ult every round",
    "tell my team we need at least two ults ready before we attempt to retake B site against their setup",
    "warn my teammates we are running into overtime where ult states reset and they have a stronger first-round kit",
    "tell my team going forward we should assign one player to call enemy ult status after every round",
    "tell my team if we can get two back-to-back ult-clean rounds we win without needing to force anything",

    # -----------------------------------------------------------------------
    # FINAL BATCH — ROUND STRUCTURE, NUANCE, REGIONAL REGISTER
    # -----------------------------------------------------------------------
    "tell my team Vyse has steel garden and the round just started, she will hold it for the entry player",
    "let them know their Omen bought from the shadows on round two which is wild economy timing",
    "tell my team Clove died round one and immediately not dead yet-ed, she is back with zero ult economy spent",
    "warn them Deadlock annihilation was charged since round four, she has been patient, expect it on plant",
    "tell my team Skye has seekers ready and she times it so all three hit before we land on site",
    "let my team know their Reyna has empress but she has not gotten a kill in three rounds, she is tilted",
    "tell my team we burned four ults this round and they had zero to answer with, that is how you break economy",
    "let my teammates know their Sova needs two more orbs for fury, deny him the mid orb each round",
    "tell my team do not give Killjoy a clean lockdown placement, rush through and eat the detention window",
    "warn my team Viper has pit ready and is anchoring B post-plant, we cannot defuse through that cloud",
    "tell my team Chamber opped our entry with tour de force and the slow field covered the whole plant zone",
    "let them know their Harbor has reckoning and they will push reckoning then execute, it is always the same",
    "tell my team Sage rez is being saved for our duelist, she told me on voice, let him go in first",
    "tell my teammates Gekko thrash detained four people on the retake and we won the round purely off the ult",
    "let my team know their KAY/O has null cmd and he will overload on B site entry, all abilities cut off",
    "tell my team Fade nightfall is a zoning tool this round, she fires it to force them to reposition then we push",
    "warn them Phoenix run it back means two bodies to kill this round, plan for it",
    "tell my team Iso kill contract puts both players in a dimension, a 1v1 where our player starts at disadvantage",
    "let my team know Waylay has convergent paths and it hinders fire rate not just movement, our aim will feel slow",
    "tell my team their Breach has rolling thunder every two rounds on average, we are due for one soon",
    "tell my teammates Tejo armageddon path can be set diagonal, it is not just horizontal lines, watch the angle",
    "let them know Astra went into astral form to fire her ult and was briefly vulnerable in real space",
    "tell my team Brimstone cannot orbital if there is a ceiling above the target, they are safe inside the building",
    "warn my team their Jett has blade storm ready and she is paired with op, stay off long absolutely",
    "tell my team Reyna empress is not a flash ult, it is a chain-kill stat boost, without kills it does nothing",
    "let them know Yoru came out of dimensional drift with a flash and two of us looked directly at it",
    "tell my team Killjoy lockdown device can be placed through a smoke, we will not see where it landed",
    "warn my teammates Viper pit nearsight means you cannot see them coming in until they are point blank",
    "tell my team Clove NDY timer is ten seconds, that is a full ten seconds to find a kill or she dies again",
    "let them know Harbor reckoning can be held in place now, it is not just a forward wave anymore",
    "tell my team their Cypher ult pulled full information both waves, they know every position we are holding",
    "warn my team Omen shade appeared heaven side, he is teleporting to heaven to shoot down on our plant",
    "tell my teammates Sage just used resurrection and our best player is alive again, the round is not over",
    "let my team know Neon overdrive beam accuracy does not drop while she is moving at full sprint",
    "tell my team Deadlock barrier mesh plus annihilation means entry players get walled then cocooned",
    "warn them Skye seeker hit slows Jett dash now, their Jett cannot escape with tailwind if a seeker touches her",
    "tell my team Vyse steel garden does not affect Neon overdrive beam, she can still beam through the jam",
    "let my teammates know Veto evolved and walked into Breach rolling thunder completely unaffected",
    "tell my team Astra divide lasts twenty-one seconds which is longer than most defuse timers allow",
    "tell my team their Fade used nightfall and we all got terror trails, prowlers are locking onto the trails now",
    "warn my team Iso has kill contract and he targets whoever has the best stats on our team based on what I see",
    "let them know Raze showstopper plus two satchels means she can boost over the wall and fire mid-air",
    "tell my team Brimstone orbital and KJ nanoswarm stacked on spike is a total defuse denial setup",
    "tell my teammates Omen has ult and two recharging smokes, his utility budget is enormous right now",
    "let my team know Breach rolling thunder plus Astra grav well is a double CC combo we need to fear",
    "tell my team their Phoenix and Clove both have ults, two potential self-revivals in the same round",
    "warn my team Sova fury beams reveal on hit, after a beam you are visible through all walls until round end",
    "tell my team the moment Kayo goes down in null cmd we need someone to sprint to his body and revive",
    "tell my teammates Clove is the only controller who benefits from kills because pick-me-up heals on eliminations",
    "let them know Harbor reckoning wave speed increased in the last patch, it reaches the site faster now",
    "tell my team Gekko ult lunge is the activation, steering thrash without lunging does not detain anyone",
    "warn my team their Deadlock placed annihilation device in the smoke and we cannot see where it is aimed",
    "tell my team we won the ult economy battle this half by picking up every single orb on the map",
    "let my teammates know Tejo armageddon needs a valid line-of-sight path on the target map area",
    "tell my team Veto evolution plus Viper pit means their anchor is immune and the site is a death zone",
    "tell my teammates Chamber tour de force slow field appears at the exact kill location and lingers there",
    "let them know Killjoy ult is the most expensive in the game at nine points alongside Breach thunder",
    "tell my team Cypher neural theft gives two reveal waves four seconds apart, there is a gap to reposition in",
    "warn my teammates Fade haunt eye reveals first then trails the enemy for twelve seconds, nightfall makes trails permanent",
    "tell my team Astra cosmic divide audio block is huge, the defenders cannot hear us plant on the other side",
    "let them know Yoru dimensional drift lasts ten seconds, his entire flank cycle happens in that window",
    "tell my team Neon overdrive kills reset the timer so a chain-kill extends the ult indefinitely",
    "tell my teammates Reyna empress and overdrive on Neon mean two chain-kill ults are active simultaneously",
    "warn my team their Sage has resurrection and is standing twelve meters from the body, she rezzes in four seconds",
    "tell my team Raze used showstopper to clear heaven and the slow AoE from the explosion covered the plant",
]
