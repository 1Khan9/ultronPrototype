"""Vocab pack: stress_nanoswarm_wait (kind=relay, ~600 items).

CHARGE: Killjoy nanoswarm/molly on the spike (or post-plant denial utility in
general), followed by a wait instruction, then a defuse directive -- the WAIT
duration and the DEFUSE call must both survive the relay pipeline intact. Cases
cover every realistic phrasing a streamer would say: slang (nano, molly, KJ
molly, swarm), explicit countdowns (wait 3 seconds, wait it out, hold for 4,
give it 5), implicit waits (let it run, let it fade, let it pop, wait until it
stops), and defuse variants (defuse, stick it, hop on it, go for it, grab the
defuse). Also covers compound variants that add a site, time on spike, or
ownership qualifier. Engineered to BREAK:
  - wait-duration retention (N seconds must survive verbatim)
  - two-step sequencing (wait-THEN-defuse, order must not invert)
  - fact-token retention for ability name (nano vs molly vs swarm vs KJ)
  - ownership/subject inversion (their nano, our nano, the nano)
  - compound zero-fact-loss (site + wait + defuse + timer)
  - hallucinated-specific rate (no invented HP/time numbers)
  - ask-vs-answer / directive vs observation
  - latency under dense compounds
"""

ITEMS = [
    # =========================================================================
    # BLOCK 1 — BARE MINIMUM: [wait] + [defuse] (no explicit N seconds)
    # Hardest: the relay must preserve the sequence with zero anchor numbers.
    # =========================================================================
    "wait for the nano then defuse",
    "let the nano pop then defuse",
    "wait it out then defuse",
    "let it go then defuse",
    "let the molly burn then defuse",
    "wait for the molly to end then defuse",
    "let the KJ molly finish then defuse",
    "wait for the swarm to stop then defuse",
    "hold off then defuse",
    "hold your defuse until the nano fades",
    "don't defuse yet, wait for the nano",
    "don't touch the spike yet, nano is up",
    "stay off the bomb until the nano dies",
    "nano is still active, hold the defuse",
    "molly is still going, don't defuse",
    "swarm is up, do not defuse",
    "KJ molly is live, hold",
    "the nanoswarm is on the spike, wait",
    "there's a nano on the spike, wait to defuse",
    "there's a molly on the bomb, hold off",
    "nano on the defuse spot, don't touch it",
    "KJ dropped a molly on the spike, hold",
    "nanoswarm on the bomb, wait it out",
    "swarm on the spike, wait then go",
    "molly on the bomb, let it run then defuse",
    "nano fading, get ready to defuse",
    "nano almost done, prep for defuse",
    "molly is nearly out, get on the spike",
    "swarm is almost gone, get ready",
    "KJ molly dying, move to defuse",

    # =========================================================================
    # BLOCK 2 — EXPLICIT COUNTDOWN: wait N seconds then defuse
    # Primary stress: the numeral must survive unchanged.
    # =========================================================================
    "wait 2 seconds then defuse",
    "wait 2 more seconds then defuse",
    "hold for 2 seconds then defuse",
    "give it 2 seconds then defuse",
    "2 seconds, then defuse",
    "wait 3 seconds then defuse",
    "hold 3 seconds then go for the defuse",
    "give it 3 seconds then defuse",
    "3 seconds on the nano then defuse",
    "3 more seconds then hop on the spike",
    "wait 4 seconds then defuse",
    "hold 4 seconds then defuse",
    "give it 4 seconds then defuse",
    "4 seconds left on nano, then defuse",
    "4 more seconds then stick it",
    "wait 5 seconds then defuse",
    "hold 5 then defuse",
    "5 seconds on the molly, wait then defuse",
    "5 more seconds then get on the bomb",
    "give it 5 then defuse",
    "wait 1 second then defuse",
    "literally 1 second then defuse",
    "hold for a second then defuse",
    "barely a second left, then defuse",
    "wait like 2 seconds and then defuse",
    "maybe 3 seconds, then defuse",
    "about 3 seconds left, then go defuse",
    "roughly 4 seconds, hold then defuse",
    "like 5 seconds, wait then defuse",
    "around 3 seconds then defuse",

    # =========================================================================
    # BLOCK 3 — WITH EXPLICIT ABILITY NAME VARIATIONS
    # Stress: molly vs nano vs nanoswarm vs swarm vs KJ molly vs KJ nano
    # =========================================================================
    "the nanoswarm is on the spike, wait 3 seconds then defuse",
    "nanoswarm fading in 3, then defuse",
    "nanoswarm is done in 3 seconds, then go defuse",
    "KJ nanoswarm on the bomb, hold 4 seconds then defuse",
    "KJ nanoswarm is active, wait 2 then defuse",
    "KJ nano on spike, hold 3 then defuse",
    "KJ nano, hold 4 seconds then defuse",
    "KJ nano dying, 2 more seconds, then defuse",
    "Killjoy nano on the spike, hold 3 then defuse",
    "Killjoy nanoswarm is on the bomb, wait 4 seconds",
    "Killjoy molly on the defuse, hold 3 then go",
    "Killjoy molly is up, wait 2 seconds then defuse",
    "Killjoy molly fading, hold 3 then stick it",
    "KJ molly on spike, wait 4 then defuse",
    "KJ molly dying in 3, then defuse",
    "molly on the bomb, 3 seconds, then defuse",
    "molly still going, 4 more seconds, then go",
    "molly is live on the spike, hold 3 then defuse",
    "molly fading in 2, get ready to defuse",
    "molly almost out, 1 more second, defuse",
    "swarm on the spike, wait 3 seconds then defuse",
    "swarm dying, 2 more seconds, then defuse",
    "swarm is active, hold 4 then go",
    "the swarm is going off, hold 3 seconds",
    "swarm still popping, hold 5 then defuse",

    # =========================================================================
    # BLOCK 4 — OWNERSHIP STRESS: their nano / our nano / the nano
    # Stress: ownership must not invert (their KJ vs our KJ)
    # =========================================================================
    "their KJ put nano on the spike, wait 3 then defuse",
    "their Killjoy molly on the bomb, hold 3 seconds then go",
    "their KJ dropped a nano on the defuse spot, wait 4",
    "their nano is on the bomb, hold 2 then defuse",
    "their molly is on the spike, hold 3 then go",
    "the enemy KJ put swarm on the spike, hold 4 then defuse",
    "enemy nanoswarm on the bomb, 3 seconds then defuse",
    "they put nano on the spike, wait it out then defuse",
    "they have a molly on the bomb, wait 3 then go",
    "they dropped swarm on the spike, hold 4 then defuse",
    "our KJ nano is denying the spike, wait 3 before anyone defuses",
    "our Killjoy molly is still on the bomb, wait 4 seconds",
    "our nano is on the spike, hold off on defuse",
    "tell them our KJ's nano is on the spike, wait 3 then defuse",
    "their KJ nano is fading, 2 more seconds then defuse",
    "their swarm is almost done, 2 seconds, then defuse",
    "enemy molly dying, hold 1 more second then defuse",
    "their Killjoy set nano on the spike, 3 seconds out",
    "enemy nano on defuse, wait 4 then commit",
    "their KJ has nano on spike, do not defuse yet, wait 3",

    # =========================================================================
    # BLOCK 5 — SITE-EXPLICIT COMPOUNDS
    # Stress: site label (A/B/C) must survive along with wait + defuse
    # =========================================================================
    "nano on spike A, wait 3 then defuse",
    "molly on A spike, hold 3 seconds then defuse",
    "KJ nano on A, wait it out then defuse",
    "nanoswarm on A site spike, hold 4 then defuse",
    "nano on the bomb at A, give it 3 seconds then go",
    "nano on spike B, wait 3 then defuse",
    "molly on B spike, hold 2 seconds then defuse",
    "KJ molly on B bomb, wait 3 then go defuse",
    "nanoswarm on B site bomb, hold 4 then defuse",
    "swarm on B spike, wait 3 seconds then go",
    "nano on spike C, wait 3 then defuse",
    "molly on C spike, hold 4 seconds then defuse",
    "KJ nano on C site bomb, wait 3 then go",
    "nanoswarm on C bomb, hold 4 then defuse",
    "swarm on C spike, wait 2 then defuse",
    "nano on A default spike, hold 3 then defuse",
    "KJ molly on B default, wait 4 seconds then defuse",
    "nano on A gen spike, hold 3 then defuse",
    "molly on A triple box, wait 3 then defuse",
    "KJ swarm on B workshop spike, hold 3 then defuse",

    # =========================================================================
    # BLOCK 6 — SPIKE TIMER COMPOUNDS
    # Stress: wait duration + spike timer must BOTH survive intact
    # =========================================================================
    "nano on spike, 30 seconds left on bomb, wait 3 then defuse",
    "KJ molly on spike, 25 seconds left, hold 3 then defuse",
    "nanoswarm up on bomb, 20 seconds on spike, hold 3 then go",
    "molly on the spike, we have 35 seconds, wait 4 then defuse",
    "nano fading, spike at 20 seconds, 2 more seconds then defuse",
    "swarm on spike, 15 seconds on bomb, wait 3 then commit",
    "KJ nano on spike, 40 seconds left, hold 3 then defuse",
    "nano on bomb, 30 left, wait 4 then go",
    "molly on spike, 25 seconds left, wait 3 then defuse",
    "KJ molly is going, 20 seconds left on spike, hold 4 then defuse",
    "nanoswarm on bomb, bomb has 30 seconds, wait 3 then defuse",
    "nano on spike A, 40 seconds on the clock, hold 3 then defuse",
    "KJ swarm on B spike, spike at 25, wait 3 then go",
    "molly B spike, 20 seconds left, hold 2 then defuse",
    "nano on spike, 15 seconds, wait 2 then defuse or we lose",
    "nanoswarm on bomb, 10 seconds left, hold 3 then defuse quick",
    "nano still going, spike has 35, hold 4 then defuse",
    "KJ molly on spike, 40 seconds, wait 3 then go for the defuse",
    "swarm on bomb, we have 30, hold 3 then defuse",
    "molly fading, spike at 28, 1 more second then defuse",

    # =========================================================================
    # BLOCK 7 — DEFUSE VERB VARIANTS (stress: defuse action word diversity)
    # stick it / hop on it / get on it / go for it / grab the defuse
    # =========================================================================
    "wait 3 seconds then stick it",
    "nano fading, 3 seconds then stick it",
    "KJ molly dying, hold 2 then stick the defuse",
    "wait for the swarm then stick the spike",
    "let the nano die then stick it",
    "hold 3 then hop on the bomb",
    "wait 3 then hop on the spike",
    "KJ molly out in 3, then hop on it",
    "nano fading, 2 seconds then hop on the defuse",
    "swarm going out, hold 3 then hop on the bomb",
    "wait 3 then get on the bomb",
    "let the nano go then get on the spike",
    "KJ molly fading, 3 then get on the defuse",
    "hold 4 then get on it",
    "swarm dying, 2 seconds, then get on it",
    "wait 3 then go for the defuse",
    "nano dying in 3, then go for it",
    "molly out in 2, then go for the defuse",
    "hold 4 then go for the spike",
    "swarm done in 3, then go for it",
    "wait 3 then grab the defuse",
    "KJ nano out in 2, grab the defuse",
    "molly fading, 3 seconds, then grab it",
    "hold 4 then grab the spike",
    "swarm dying, 1 second, then grab the defuse",
    "wait for the nano to pop then hit the defuse",
    "KJ molly done in 3, then hit the spike",
    "hold 2 then hit the defuse",
    "swarm fading, 3 then hit the defuse",
    "nano out in 2, hit the defuse",

    # =========================================================================
    # BLOCK 8 — IMPLICIT WAIT PHRASINGS (no explicit seconds)
    # let it run / let it fade / let it burn / let it die / wait it out
    # =========================================================================
    "let the nano run out then defuse",
    "let the nano die then defuse",
    "let the nano fade then defuse",
    "let the nano burn out then defuse",
    "let the nano expire then defuse",
    "let the nano finish then defuse",
    "let the nano stop then defuse",
    "let the nano clear then defuse",
    "let the nano go off then defuse",
    "let the nano run its course then defuse",
    "let the molly run out then defuse",
    "let the molly die down then defuse",
    "let the molly fade then defuse",
    "let the molly burn out then defuse",
    "let the molly expire then defuse",
    "let the molly finish then defuse",
    "let the molly stop then defuse",
    "let the molly clear then defuse",
    "let the KJ molly run then defuse",
    "let the KJ molly pop off then defuse",
    "let the swarm run out then defuse",
    "let the swarm die then defuse",
    "let the swarm fade then defuse",
    "let the swarm burn out then defuse",
    "let the swarm expire then defuse",
    "hold until it fades then defuse",
    "wait it out and then go defuse",
    "wait for it to end then defuse",
    "wait for it to stop then defuse",
    "wait for the nano to stop then defuse",

    # =========================================================================
    # BLOCK 9 — CONDITIONAL: "if the nano is on the spike" phrasings
    # Stress: conditional framing + wait + defuse must all survive
    # =========================================================================
    "if there's nano on the spike wait 3 then defuse",
    "if the nano is up wait 3 then defuse",
    "if KJ put swarm on the bomb wait 4 then defuse",
    "if there's a molly on the spike wait 3 then go",
    "if the nanoswarm is on the bomb hold 3 then defuse",
    "if you see nano on spike, wait 3 seconds then defuse",
    "if she activated nano, hold 3 then defuse",
    "check if there's nano, if so wait 3 then defuse",
    "if nano is live on spike, do not defuse yet, wait 3",
    "if nano or molly is on the bomb, hold 4 then defuse",

    # =========================================================================
    # BLOCK 10 — NEGATION STRESS: "don't defuse yet / don't touch the spike"
    # Stress: the don't-defuse-yet must survive alongside the implicit wait
    # =========================================================================
    "don't defuse yet, there's nano on the spike",
    "don't touch the spike, KJ nano is active",
    "don't go near the bomb, nanoswarm is up",
    "don't step on it, molly is still going",
    "do not defuse, their KJ nano is live",
    "hold off the defuse, swarm is up",
    "don't defuse until the nano fades",
    "don't defuse until the molly stops",
    "don't defuse until the swarm is gone",
    "don't touch the bomb, nano is still ticking",
    "wait, don't defuse, nano is on spike",
    "stop, don't defuse, molly is going",
    "hold on, don't defuse, swarm is active",
    "pause, nano is on the spike, wait then defuse",
    "don't commit to defuse yet, KJ swarm is live",
    "do not go for the defuse, nano is still going",
    "do not get on the bomb, swarm is live",
    "stay off the bomb, molly is burning",
    "stay off the spike, nano is active",
    "stay away from the bomb, swarm is still going",

    # =========================================================================
    # BLOCK 11 — SEQUENTIAL MULTI-STEP: "clear it, wait, then defuse"
    # Stress: the relay must preserve a 3-step sequence
    # =========================================================================
    "clear the site, wait for nano to fade, then defuse",
    "kill the Killjoy first, wait for nano, then defuse",
    "hold position, let nano run, then defuse",
    "hold tight, let the molly burn out, then defuse",
    "wait for the nano, then get on the spike, then defuse",
    "let the swarm pop, get in position, then defuse",
    "hold 3 seconds for the nano, then defuse fast",
    "wait for KJ nano to clear, then two of you defuse fast",
    "flash the angle, wait for nano, then defuse",
    "smoke the defuse spot, wait for nano, then defuse",
    "hold on nano, then push, then defuse",
    "after the nano fades, clear heaven, then defuse",
    "kill lurkers first, then wait for nano, then defuse",
    "peek the angle, wait for nano, then defuse",
    "clear the box, let nano run out, then defuse",
    "keep them off you, hold 3 for nano, then defuse",
    "wait 3 seconds for nano, make sure no enemies, then defuse",
    "hold position 4 seconds for nano, then commit to defuse",
    "play off the spike, wait for nano to die, then defuse",
    "one guy cover, let nano pop off, other defuse",

    # =========================================================================
    # BLOCK 12 — RAPID-FIRE SHORT FORMS (stream-speed truncated speech)
    # Stress: ultra-minimal input must still trigger wait + defuse
    # =========================================================================
    "nano wait defuse",
    "nano on it, wait",
    "KJ nano, hold, defuse",
    "molly wait defuse",
    "swarm wait then go",
    "nano 3 defuse",
    "KJ 3 seconds defuse",
    "wait 3 defuse",
    "hold 3 go",
    "4 seconds nano defuse",
    "nano up hold",
    "molly hold defuse",
    "KJ hold defuse",
    "wait nano go",
    "swarm 4 defuse",
    "nano hold 2 defuse",
    "KJ 2 then go",
    "hold it nano defuse",
    "nano out defuse",
    "molly out go defuse",

    # =========================================================================
    # BLOCK 13 — NATURAL STREAMER SPEECH (disfluent, filler-heavy)
    # Stress: filler words, hesitations, and run-ons
    # =========================================================================
    "uh, wait for the nano to die then defuse",
    "like, wait for the molly to run out then defuse",
    "okay so wait for the nano, then go defuse",
    "wait, um, wait for the swarm to end then defuse",
    "so like, nano is on the spike, wait 3 then defuse",
    "bro wait for the nano, 3 seconds, then defuse",
    "dude wait for the KJ molly, then defuse it",
    "yo wait for the nano to pop and then defuse",
    "literally wait 3 seconds for the nano then defuse",
    "just wait for the nano to go out then defuse okay",
    "hold on, let the molly burn, then defuse",
    "okay okay, nano fading, 3 seconds, then defuse",
    "hold on bro, KJ nano, wait 3 then defuse",
    "wait guys, nano is on the bomb, hold 3 then go",
    "guys let the swarm run out then defuse",
    "okay team, KJ nano on spike, wait 3 then defuse",
    "wait wait wait, nano on spike, hold 3 then defuse",
    "sh, nano on the bomb, hold 3 then defuse",
    "calm down, let the nano die first, then defuse",
    "patience, nano is on the bomb, wait 3 then defuse",

    # =========================================================================
    # BLOCK 14 — URGENCY GRADIENTS (spike timer + wait + defuse = 3 stressors)
    # =========================================================================
    "nano on spike, 10 seconds left, wait 3 then defuse",
    "KJ molly on bomb, 15 seconds, hold 3 then defuse fast",
    "nanoswarm on spike, 12 seconds, wait 2 then commit to defuse",
    "molly on bomb, 8 seconds left, hold 2 then go",
    "swarm on spike, spike at 9, wait 2 then defuse or it blows",
    "nano on bomb, 20 seconds, hold 3 then defuse now",
    "KJ nano on spike, 25 seconds, wait 3 then defuse",
    "nanoswarm dying, 30 seconds on spike, 2 more seconds then defuse",
    "molly fading, 35 on bomb, hold 2 then defuse",
    "swarm almost gone, 40 seconds, 1 second then defuse",
    "nano on spike, 45 seconds, wait 4 then defuse calmly",
    "KJ molly on bomb, you have 20 seconds, wait 3 then defuse",
    "nano up, spike at 15, hold 3 then defuse it's gonna be close",
    "molly on bomb, 12 seconds, wait 2 then commit",
    "nanoswarm on spike, 10 left, hold 2 then go",
    "KJ swarm on bomb, 9 seconds, hold 2 then defuse",
    "nano on spike, 8 left, 2 seconds then defuse if you can",
    "molly dying, 7 on spike, hold 1 then defuse now",
    "swarm out, 6 on spike, go defuse",
    "nano gone, 5 seconds, defuse",

    # =========================================================================
    # BLOCK 15 — OTHER DENIAL UTILITY MIXED IN (molly from other agents)
    # Stress: KJ nano vs Viper snake bite vs Brimstone incendiary vs Raze grenades
    # (These are 'molly on spike' patterns but from other agents)
    # =========================================================================
    "Viper snake bite on the spike, wait 3 then defuse",
    "snake bite on bomb, hold 3 seconds then go defuse",
    "Viper put snakebite on the defuse, wait it out then defuse",
    "snake bite on spike, let it run then defuse",
    "snakebite fading on spike, 2 more seconds then defuse",
    "Brimstone incendiary on the spike, wait 3 then defuse",
    "Brim molly on the bomb, hold 3 then defuse",
    "incendiary on the spike, let it burn then defuse",
    "Brim incendiary on bomb, wait it out then defuse",
    "incendiary fading, 2 seconds then defuse",
    "Raze paint shells on the spike, wait 3 then defuse",
    "Raze grenade on bomb, hold 3 then go defuse",
    "paint shells on the spike, wait it out then defuse",
    "KAY/O fragment on the spike, wait 3 then defuse",
    "KAYO fragment on bomb, hold 3 then defuse",
    "fragment on spike, let it pop then defuse",
    "molly on spike whatever it is, wait 3 then defuse",
    "some molly on the bomb, hold 3 then defuse",
    "there's some kind of molly on the spike, wait then defuse",
    "utility on the spike, hold 3 then defuse",

    # =========================================================================
    # BLOCK 16 — MAP-EXPLICIT COMPOUNDS
    # =========================================================================
    "KJ nano on spike A Ascent, wait 3 then defuse",
    "nano on A gen Ascent, hold 3 then defuse",
    "KJ molly on B Ascent triple box, wait 3 then defuse",
    "swarm on B workshop Ascent, hold 4 then defuse",
    "nano on A Haven, hold 3 then defuse",
    "KJ molly on B Haven gong side, wait 3 then defuse",
    "nanoswarm on C Haven platform spike, hold 4 then defuse",
    "molly on A Haven heaven side spike, wait 3 then go",
    "nano on spike A Lotus, hold 3 then defuse",
    "KJ molly on B Lotus pillars spike, wait 4 then defuse",
    "swarm on C Lotus platform spike, hold 3 then defuse",
    "nano on B default Lotus, wait 3 then defuse",
    "KJ nano on A Pearl behind cafe, hold 3 then defuse",
    "molly on B Pearl radianite box spike, wait 3 then defuse",
    "nanoswarm on B Pearl, hold 4 then defuse",
    "KJ swarm on A Pearl vending machine spike, wait 3 then go",
    "nano on A Split terminal, hold 3 then defuse",
    "KJ molly on B Split backsite, wait 3 then defuse",
    "nanoswarm on A Split, hold 4 then defuse",
    "molly on B Split pillar side, wait 3 then defuse",
    "nano on A Breeze pyramid, hold 3 then defuse",
    "KJ molly on B Breeze nest side spike, wait 3 then defuse",
    "swarm on A Breeze left pyramid, hold 4 then defuse",
    "nano on B Breeze default, wait 3 then defuse",
    "KJ nano on A Fracture top site, hold 3 then defuse",
    "molly on B Fracture arcade spike, wait 3 then defuse",
    "nanoswarm on A Fracture bottom, hold 4 then defuse",
    "swarm on B Fracture generator, wait 3 then defuse",
    "nano on B Fracture canteen side, hold 3 then defuse",
    "KJ molly on A Fracture heaven side, wait 4 then defuse",

    # =========================================================================
    # BLOCK 17 — AGENT INSTRUCTION (tell/warn team directly)
    # =========================================================================
    "tell my team to wait 3 seconds for the nano then defuse",
    "warn my team there's a KJ nano on the spike, hold 3 then defuse",
    "let them know KJ put nano on the bomb, wait 3 then defuse",
    "tell the guys nano is on the spike, wait it out then defuse",
    "warn the team KJ molly is on the bomb, hold 3 then defuse",
    "tell my teammates KJ put swarm on spike, hold 3 then go",
    "let my team know there's a nanoswarm on the defuse, hold 3",
    "tell them to wait for the KJ nano then defuse",
    "warn my team, KJ nano is live on the spike, wait 4 then defuse",
    "tell the guys the nano fades in 3 then defuse",
    "let the team know molly on bomb, 3 seconds then defuse",
    "tell my teammates, swarm on spike, wait 3 then defuse",
    "warn my team about the KJ molly on spike, hold 4 then defuse",
    "tell my team to hold off the defuse, nano is up, 3 seconds",
    "let them know the nanoswarm is on the spike, wait 3 then go",
    "tell the squad to hold 3 for the KJ nano then defuse",
    "warn the guys, nano on bomb, wait 3 then defuse",
    "tell my team the swarm is on the spike, hold 4 then defuse",
    "let my team know, KJ nano on spike, hold 3 then defuse",
    "tell them KJ swarm on bomb, hold 4 then go defuse",

    # =========================================================================
    # BLOCK 18 — IDENTITY / PERSPECTIVE TRAPS
    # "I should wait" vs "tell them to wait" — ownership disambiguation
    # =========================================================================
    "I should wait 3 seconds for the nano then defuse but tell them first",
    "I'm going to wait for the KJ nano then defuse, let the team know",
    "tell the team I'm waiting 3 for the nano then defusing",
    "I'll wait 3 for the molly then defuse, tell them",
    "I'm holding for the swarm, tell them wait 3 then defuse",
    "I'm the one defusing so tell them, wait for nano, I'll go after 3",
    "I have kit, I'm waiting 3 for the nano, tell them to cover me",
    "I'm going for the defuse after the nano, tell my team to cover",
    "I'll defuse after the KJ molly, 3 seconds, let my team know",
    "I need my team to cover me, waiting 3 for nano then defusing",

    # =========================================================================
    # BLOCK 19 — DOUBLE NANOSWARM STRESS
    # Multiple nanos / stacked deny — the relay must preserve both
    # =========================================================================
    "there are two nanos on the spike, wait 5 then defuse",
    "KJ dropped two mollies on the bomb, wait 5 then defuse",
    "double nano on the spike, hold 5 then defuse",
    "two nanoswarms on the bomb, wait 5 then go",
    "KJ put two swarms on the spike, hold 5 then defuse",
    "there's a nano and a Viper snakebite on the spike, wait 5 then defuse",
    "nano plus incendiary on the bomb, hold 5 then defuse",
    "double molly on the spike, wait 5 then defuse",
    "two mollies stacked on the bomb, hold 5 then go",
    "two nanos stacked on defuse, wait 6 then commit",

    # =========================================================================
    # BLOCK 20 — DEFUSE KIT MODIFIER
    # Stress: kit / no kit changes timing; both must survive
    # =========================================================================
    "you have kit, wait 3 for nano then defuse, you have time",
    "no kit, wait 3 for nano then defuse, it'll be close",
    "I have defuse kit, waiting 3 for KJ nano then defusing",
    "she has kit, she can wait 3 for nano and still defuse",
    "with kit wait 3 for nano then defuse, you have 4 left",
    "without kit wait 3 for nano then defuse, you'll need 7",
    "kit means 4 second defuse, wait 3 for nano, plenty of time",
    "no kit means 7 seconds, wait 3 for nano then commit",
    "he has kit, tell him wait 3 for nano then defuse",
    "she doesn't have kit, hold 3 for nano then defuse fast",

    # =========================================================================
    # BLOCK 21 — AFTER-THE-FACT NANO CALLOUTS (nano just activated)
    # =========================================================================
    "KJ just activated nano on the spike, hold 3 then defuse",
    "KJ just popped swarm on the bomb, wait 4 then defuse",
    "nano just went off on the spike, hold 3 then defuse",
    "she just activated the nanoswarm, wait 4 then go",
    "KJ just triggered nano on the defuse, hold 3 then go",
    "molly just went off on the spike, hold 3 then defuse",
    "swarm just activated on the bomb, wait 4 then defuse",
    "she just popped the nano, hold 3 then defuse",
    "KJ just triggered her swarm, wait 3 then defuse",
    "nano just started on the bomb, hold 4 then defuse",
    "I hear the nano, it just went off, wait 3 then defuse",
    "I see the nano activating, hold 3 then defuse",
    "KJ's nano just popped, 4 seconds then defuse",
    "nano just activated, hold it, 3 then defuse",
    "the swarm just started, wait 3 then defuse",

    # =========================================================================
    # BLOCK 22 — AUDITORY / VISUAL CUE TRIGGERS
    # =========================================================================
    "you can hear the nano on the spike, wait 3 then defuse",
    "you can see the swarm on the bomb, hold 3 then defuse",
    "listen for the nano to stop then defuse",
    "wait until the nano sound stops then defuse",
    "when the nano visually clears, go defuse",
    "watch the nano, when it dies, defuse",
    "listen, when the swarm stops, defuse",
    "when you stop hearing the nano, defuse",
    "when the KJ molly animation ends, defuse",
    "as soon as the nano clears visually, defuse",

    # =========================================================================
    # BLOCK 23 — TEAM COORDINATION MULTI-PLAYER DEFUSE
    # =========================================================================
    "tell them, nano on spike, wait 3, then two of you defuse",
    "KJ nano on bomb, hold 3, then push in pairs to defuse",
    "wait 3 for the nano, then rush in and defuse it",
    "nano fading in 3, then everyone rush spike to defuse",
    "hold 3 for KJ nano, then two man defuse",
    "swarm dying in 3, both of you push to defuse",
    "nano on spike, when it pops, both defuse together",
    "KJ molly running out, in 3 seconds, rush the defuse",
    "wait for nano, 3 seconds, then two push to defuse",
    "hold for the swarm, 3 seconds, then both commit to defuse",

    # =========================================================================
    # BLOCK 24 — NEGATIVE / FALSE-RELAY SHADOWS (must NOT relay)
    # Private narration that looks relay-shaped but is NOT a relay command.
    # =========================================================================
    "I keep forgetting to wait for the nano before defusing",
    "chat I always mess up the nano timing on defuse",
    "honestly I should have waited for the nano before defusing",
    "I hate when KJ puts nano on the spike, I never know when to defuse",
    "sub I literally walked into the nano trying to defuse, so dumb",
    "man that nano timing is so hard to read",
    "I need to remember to count 3 seconds before defusing on nano",
    "I always rush the defuse through the nano like an idiot",
    "chat did you see me try to defuse through the nano",
    "watch this, I'm going to wait for the nano and then defuse smoothly",
    "in my opinion waiting for the nano before defusing is the right call",
    "I think the optimal play is to wait 3 for the nano then defuse",
    "I was thinking we should wait for the nano but I wasn't sure",
    "I personally would wait 3 for the nano then defuse",
    "my hands are shaking, I waited for the nano but choked the defuse",
    "this team never waits for the nano before defusing, it tilts me",
    "they should have waited for the nano, that was a bad defuse attempt",
    "if only they had waited 3 seconds for the nano before defusing",
    "I cannot believe he walked through the nano to defuse",
    "that's the third time today someone defused through the nano",

    # =========================================================================
    # BLOCK 25 — QUESTION-TO-ULTRON (kind=question) CONTRAST CASES
    # Ultron answers; these are NOT relayed to the team.
    # =========================================================================
    "Ultron, should I wait for the nano before defusing",
    "hey Ultron, how long does KJ nano last on the spike",
    "Ultron how many seconds should I wait for the nano",
    "Ultron, is 3 seconds enough to wait for the nano",
    "hey Ultron, when should I defuse after a KJ nano",

    # =========================================================================
    # BLOCK 26 — EXTREME COMPOUND: 5-FACT CHAINS
    # site + agent + ability + wait duration + spike timer
    # Maximum stress on compound zero-fact-loss
    # =========================================================================
    "KJ put nano on B spike Ascent, wait 3 seconds, we have 25 on the bomb, then defuse",
    "KJ molly on A spike Haven, hold 4 seconds, 30 seconds on bomb, then defuse",
    "nanoswarm on B site Lotus, spike at 20, wait 3 then defuse",
    "KJ swarm on C Haven platform spike, 3 seconds out, 25 on bomb, then defuse",
    "their Killjoy dropped nano on A Pearl spike, 3 seconds, 30 left on bomb, then defuse",
    "KJ nanoswarm on B Split backsite spike, 4 seconds, 35 on bomb, then defuse",
    "KJ molly on A Fracture top spike, hold 3, spike at 20, then defuse",
    "KJ swarm on B Breeze nest spike, 3 seconds, 25 on bomb, then go defuse",
    "enemy KJ activated nano on A Ascent gen spike, 4 seconds, 30 on bomb, then defuse",
    "their KJ nano live on B Pearl radianite spike, 3 seconds, 20 left, then defuse",

    # =========================================================================
    # BLOCK 27 — EDGE CASES: nano already fading / already gone
    # =========================================================================
    "nano is fading, get ready to defuse",
    "KJ nano almost done, prep the defuse",
    "molly nearly out, get on the spike",
    "swarm dying, move to defuse",
    "nano about to pop, position for defuse",
    "nano is on its last second, go defuse",
    "KJ swarm literally about to end, defuse now",
    "molly fading right now, defuse",
    "nano just ended, defuse now",
    "KJ nano cleared, defuse now",
    "swarm gone, go defuse",
    "molly is out, defuse now",
    "nano just stopped, go",
    "KJ nano just ended, commit to defuse",
    "nanoswarm cleared, defuse now",

    # =========================================================================
    # BLOCK 28 — SLANG / REGIONAL / REGISTER VARIANTS
    # =========================================================================
    "bro wait for the nano then defuse",
    "yo hold 3 for the KJ molly then go",
    "dude let the nano run then defuse",
    "fam wait 3 for the swarm then stick it",
    "bro 3 seconds on the nano then hop on the bomb",
    "man let the KJ molly die then defuse",
    "bruh wait for the nano then go",
    "g hold 3 for the nano then defuse",
    "lads wait for the KJ nano then defuse",
    "mates hold 3 for the molly then defuse",
    "guys nano on spike, hold 3, then defuse",
    "wait for the nano bro, 3 seconds, then go",
    "hold 3 for nano dude then commit",
    "don't push the defuse man, nano is up, 3 seconds",
    "bro literally just wait 3 seconds for the nano",
    "yo just hold 3 for the KJ swarm then defuse",
    "dude just wait for the nano to stop then defuse",
    "bro the nano is on the bomb, give it 3",
    "homie wait for the nano then defuse",
    "cap wait 3 for the KJ molly then stick it",

    # =========================================================================
    # BLOCK 29 — COVER-ME COMPOUNDS
    # =========================================================================
    "cover me, waiting 3 for nano then defusing",
    "someone cover me, holding 3 for KJ nano then defusing",
    "I need cover, waiting 3 for the swarm then defusing",
    "hold the angle, waiting 3 for KJ molly then defusing",
    "flash the angle, then wait 3 for nano, then I'll defuse",
    "someone flash, then hold 3 for nano, then defuse",
    "cover the entry, wait 3 for nano, then defuse",
    "hold heaven, let nano die in 3, then I'll defuse",
    "someone watch main, I'm waiting 3 for nano then defusing",
    "cover CT, KJ nano on spike, hold 3 then defuse",

    # =========================================================================
    # BLOCK 30 — EXTENDED OFF-SNAP (LLM-rephrase territory)
    # =========================================================================
    "tell my team their KJ has a habit of activating nano when we start to defuse, hold 3 seconds then go",
    "warn them that their Killjoy drops nanoswarm on the spike every post-plant, always wait it out then defuse",
    "KJ nano timing is 4 seconds max, wait 4 then defuse and we win the round",
    "their KJ activated two nanos on the spike, we need to hold 5 seconds then defuse or it blows",
    "the nano is on the spike and we have 20 seconds on the bomb, hold 3 then defuse, we can make it",
    "KJ has this habit of double nanoswarm on the spike so wait 5 then defuse",
    "their KJ is going to pop nano every time we go for the defuse, we need to wait her out",
    "nanoswarm on the defuse spot and the spike has 25 seconds, hold 3 for the nano then defuse, easy win",
    "their Killjoy put two swarms stacked on the bomb, hold 5 then defuse or it blows",
    "wait 4 seconds for the KJ nano and then rush two people onto the defuse, we have 20 seconds, we can do it",

    # =========================================================================
    # BLOCK 31 — ADDITIONAL PHRASINGS FOR COUNT COVERAGE
    # =========================================================================
    "nano on spike, hold 6 seconds then defuse",
    "wait 6 for the molly then defuse",
    "KJ nano, hold 7 seconds, then defuse",
    "wait 7 for the swarm then defuse",
    "hold 8 seconds for the nanoswarm then defuse",
    "give it 8 seconds for the nano then defuse",
    "hold 10 seconds for the KJ molly then defuse",
    "wait 10 for the nano then defuse",
    "hold half the nano timer then defuse",
    "once the nano is halfway done, get into position to defuse",
    "as soon as the nano stops, defuse",
    "the second the nano clears, defuse",
    "the moment the swarm dies, defuse",
    "immediately after the nano, defuse",
    "nano gone, immediately defuse",
    "wait for nano to pop, then immediately defuse",
    "let the KJ nano do its thing, then defuse",
    "let the nanoswarm play out, then defuse",
    "let the molly do its work, then defuse",
    "let the swarm exhaust itself, then defuse",
    "exhaust the nano, then defuse",
    "drain the nano, then go defuse",
    "burn through the nano timer, then defuse",
    "outlast the nano, then defuse",
    "survive the nano, then defuse",
    "wait past the nano, then defuse",
    "hold through the nano, then defuse",
    "push through after the nano, then defuse",
    "you can defuse after the nano, hold 3",
    "safe to defuse once nano is done, hold 3",
    "don't defuse during nano, wait 3 then go",
    "never defuse during the swarm, wait 3",
    "always wait for nano before defusing, 3 seconds",
    "rule one: wait for nano, then defuse",
    "first priority: let nano die, then defuse",
    "step one wait for nano, step two defuse",
    "nano pops, we defuse, that's the plan",
    "plan is simple: nano fades, we defuse",
    "standard play: wait out the nano, then defuse",
    "classic post-plant: hold nano, then defuse",
    "tell them the plan: wait for nano, then defuse",
    "plan A: hold for the nano, then defuse it",
    "KJ nano on the spike, count to 3, then defuse",
    "count to 4 for the nano, then defuse",
    "count to 3 in your head, nano fades, defuse",
    "mentally count 3 for the nano, then commit to defuse",
    "silently count 3 while nano is up, then defuse",
    "KJ nano is up, count 4, then defuse",
    "count slowly to 3, nano should be done, then defuse",
    "nano active, count out 3 seconds, then defuse",
    "nano on bomb, count out 4 seconds, then defuse",
    "KJ swarm on spike, count out 3, then defuse",
    "molly on bomb, count 3 seconds, then get on the defuse",
    "nano on spike, just count 3, nano gone, defuse",
    "count 3 for the nanoswarm, then commit the defuse",
    "hold 3 then defuse, it's that simple, nano goes out",
    "three seconds, nano clears, defuse wins us the round",
    "nano on spike, 3 seconds, defuse, round over",
    "it is literally just wait 3 for the nano then defuse",
    "nano wait 3 defuse, that is the whole plan",
    "hold 3 for nano, defuse, round over, that is it",
]
