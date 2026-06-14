"""Vocab pack: stress_flavor_register (kind=relay, ~600 items).

CHARGE: Ultra-short snap callouts that must receive a brief Ultron flavor tail
without burying the tactical fact, PLUS enemy playstyle reads delivered as cold
clinical mockery, PLUS register-separation stress cases engineered to force the
system to decide SNAP vs OFF-SNAP correctly.

Metrics stressed:
  - flavor presence / diversity / register (tail must be present but brief)
  - fact-token retention: snap tail must NOT overwrite count / location / agent
  - hallucinated-specific rate (3B must not invent HP numbers or ability names)
  - opinion fidelity (playstyle reads must survive rephrasing intact)
  - register separation: short position call =/= no-flavor; opinion =/= snap
  - identity-leak control (Ultron persona must not break into Kenning voice)
  - ask-vs-answer (no invented ability cooldown answers in opinion reads)
  - ownership inversion (their playstyle, not ours — must survive)

All items are relay (streamer instructing Ultron to relay to team).
No wake-word prefix. Double-quoted strings; single-quotes inside.
"""

ITEMS = [
    # =========================================================================
    # BLOCK 1 — BARE SNAP CALLOUTS (1-2 word facts) + mandatory flavor tail
    # These are the HARDEST register cases: the system must give Ultron a flavor
    # tail while keeping the fact crystal-clear and brief. No buried facts.
    # =========================================================================
    "two B, tell my team",
    "one A, go",
    "three mid, move",
    "last one site, push",
    "one Heaven, close out",
    "spike A, hold",
    "rotating, warn them",
    "defusing, stop them",
    "planting, cover",
    "one shot B Long, finish it",
    "he's lit, swing",
    "flash in, go",
    "smoke fading, push now",
    "no armor, rush him",
    "one lurking CT, tell the team",
    "Jett dashed, tell them she is exposed",
    "Sage wall up, stop pushing",
    "turret watching B Main, let them know",
    "lockdown coming, scatter",
    "knife hit two, let the team know abilities are gone",
    "Raze boosting, warn them",
    "Omen stepping, tell them to check off-angle",
    "Reyna dismissed, she will be back",
    "Phoenix ulting, kill him fast",
    "Yoru tp, he is flanking",
    "Clove ulting, do not let her get the kill",
    "Viper pit up, do not enter",
    "Kayo down, go revive him",
    "Gekko wingman planting, kill the wingman",
    "Iso contracted someone, four alive",
    "Fade haunt up, shoot the eye",
    "Deadlock grav on B, they are pinned",
    "Vyse steel garden, primaries jammed",
    "Veto evolved, do not flash him",
    "Sova fury up, three beams",
    "Breach thunder, get out of the angle",
    "Skye seekers out, three nearsighted",
    "Tejo missiles going B, dodge",
    "Harbor wave coming, move perpendicular",
    "Astra pulse on A short, they are concussed",
    "one deep backsite, do not ignore him",
    "two walking mid, they are silent",
    "three contact B Main, they are rushing",
    "last one, spike at forty seconds",
    "one off-angle on triple box, close range",
    "no flash left on their Breach, push",
    "their Jett has no dash, duel her",
    "Sage rez ready, do not throw",
    "Cypher cam on B, they have info",
    "KJ nano on spike, wait it out",

    # =========================================================================
    # BLOCK 2 — SNAP CALLOUT + FLAVOR TAIL EXPLICITLY REQUESTED
    # Streamer directly asks Ultron to add flavor, putting register under pressure.
    # =========================================================================
    "tell them two A Short and make it sound threatening",
    "say one B Heaven in your scary voice",
    "let them know spike A like you mean it",
    "tell the team three pushing mid but make it cold and menacing",
    "warn them one CT with the Op and sound dangerous when you say it",
    "tell them last one defusing, say it like it matters",
    "let them know Jett dashing right now, be dramatic about it",
    "say Reyna has no souls left, emphasize it",
    "tell them smoke fading in five, make sure they feel the urgency",
    "let the team know Phoenix ult is down now, celebrate a little",
    "warn them Killjoy lockdown, say it with authority",
    "tell them their Viper has no fuel, make it sound like an opportunity",
    "say two B Garden walking and make them understand those are real threats",
    "tell them Kayo knife hit three, emphasize the abilities are gone part",
    "let them know rotating A right now, be crisp and decisive",

    # =========================================================================
    # BLOCK 3 — ENEMY PLAYSTYLE READS: DUELIST MOCKERY
    # Cold clinical analysis of enemy duelist behavior — register must be OFF-SNAP,
    # contemptuous, Ultron persona. No facts to lose; opinion fidelity is the metric.
    # =========================================================================
    "tell my team their Jett is peeking every angle dry with no flash, she is mechanically relying on reaction time alone",
    "let them know the enemy Jett has been dashing into smokes and getting nothing, she is panicking",
    "tell the team their Raze is spam-boosting randomly with no lineup, she is burning charges with zero coordination",
    "let them know the enemy Raze showstopper is being used to open doors, not to win fights, pure waste",
    "tell my team the enemy Reyna has gone five rounds without a kill, empress is irrelevant, she has nothing",
    "let them know their Reyna is tunnel-visioning kills instead of trading, she is feeding us ult orbs",
    "warn the team the enemy Neon is sprinting straight lines every entry, she is completely predictable",
    "tell my teammates the enemy Neon has never used a lineup once this game, pure chaos agent, punish it",
    "let them know the enemy Phoenix is using run it back on a full-buy round for no reason, wasting the ult",
    "tell the team the enemy Yoru has been faking teleports for three rounds straight, they have no actual plays",
    "let them know the enemy Yoru is going invisible just to stand in the same corner every time, no creativity",
    "tell my team their Iso is spending kill contract on players who are already low, inefficient and desperate",
    "let the guys know the enemy Iso is running Undercut into open space where no one is standing",
    "warn them the enemy Waylay is placing her beacon and immediately recalling after every duel, no commitment",
    "tell the team the enemy Waylay is using Saturate at her own feet, she does not understand the ability",
    "let them know the enemy duelist has been instalocking every round but has the lowest ACS on their team",
    "tell my team the enemy entry fragger is baiting his own teammates every single round, they have no real entry",
    "let them know their carry player is trying to one-deag with the Sheriff on a full-buy round, ego purchase",
    "tell the team the enemy top frag has been dry-peeking long with no support for four rounds and still does it",
    "let them know their Jett had blade storm and used it to clear an empty corner, completely wasted",

    # =========================================================================
    # BLOCK 4 — ENEMY PLAYSTYLE READS: CONTROLLER MOCKERY
    # =========================================================================
    "tell my team the enemy Brimstone has been smoking the wrong site every execute, their comms are broken",
    "let them know the enemy Brimstone is standing still on the tablet in a duel, he keeps dying to the same mistake",
    "warn the team the enemy Viper toggled her wall off at the exact moment we pushed, total misread of timing",
    "tell them the enemy Viper placed her pit but immediately left it, the eight-second timer is a joke to her",
    "let my team know the enemy Omen has been teleporting to the same corner round after round, we can pre-aim it",
    "tell the team the enemy Omen is throwing paranoia through walls at our empty spawn, zero information value",
    "let them know the enemy Astra went into astral form mid-duel and died to a pistol, she cannot read timings",
    "warn my team the enemy Astra dissipated a star to fake B but her whole team is rotating A, no coordination",
    "tell them the enemy Harbor is walling A site on a B execute, her team is not talking to her",
    "let them know the enemy Clove is ulting every round but never getting the required kill, she dies twice per round",
    "tell my team the enemy controller has been out of smokes since round five and still trying to force executes",
    "let them know the enemy Viper has been letting her fuel drain to zero before toggling, she is inexperienced",
    "tell the team the enemy Omen one-way is always in the same corner, rotate off it without looking",
    "warn them the enemy Brimstone orbital is landing on an empty spike, he cannot read post-plant positions",
    "let my team know the enemy Clove is smoking after she is already dead but the smokes are lasting six seconds, do not wait them out",

    # =========================================================================
    # BLOCK 5 — ENEMY PLAYSTYLE READS: INITIATOR MOCKERY
    # =========================================================================
    "tell my team the enemy Sova has been shooting recon bolts into ceilings and wasting them every round",
    "let them know the enemy Sova hunter fury is being used at fifteen-meter range, it is a wall-piercing weapon, not a shotgun",
    "warn the team the enemy Breach is flashing his own teammates into every entry, they are playing 5v5 with minus two eyes",
    "tell my teammates the enemy Skye has been burning both hawk charges before the push starts, nothing left on entry",
    "let the team know the enemy KAY/O knife is landing in open water every round, zero enemies suppressed",
    "tell them the enemy Kayo has been ulting and immediately dying without the team following up, total waste",
    "warn my team the enemy Fade haunt eye is being shot down every single round before it scans, they keep throwing it at the same angle",
    "let them know the enemy Gekko is reclaiming wingman during a live duel and dying to it, they do not understand the cooldown",
    "tell the team the enemy Tejo salvo is always landing on the same default plant position, we plant somewhere else",
    "let them know the enemy Tejo stealth drone has been detonating on walls instead of enemies, forty-two HP wasted",
    "warn the team the enemy initiator is going in dry every round with no flash, their duelist has no support",
    "tell my teammates their Breach Fault Line is aimed at a wall, it does not go through corners that way",
    "let them know the enemy Skye seekers are being sent at three people stacked in a corner, they still miss all three",
    "tell them the enemy Fade prowlers have been sent against a Veto who is immune, she evolved two rounds ago",
    "let my team know the enemy Gekko thrash ult has been destroyed before detonating every time, they throw it with no cover",

    # =========================================================================
    # BLOCK 6 — ENEMY PLAYSTYLE READS: SENTINEL MOCKERY
    # =========================================================================
    "tell my team the enemy Cypher has his camera on the same B Long corner every round, we shot it out, no info",
    "let them know the enemy Cypher tripwires are placed at the same three spots as last game, we know the layout",
    "warn the team the enemy Killjoy is recalling her turret instead of letting it spot us rotating, she is wasting intel",
    "tell my teammates the enemy KJ lockdown device has been planted in the open every round, we just shoot it",
    "let them know the enemy Chamber is holding long with his tour de force but refusing to take any shot, he is frozen",
    "tell the team the enemy Chamber teleport anchor was destroyed at the start of round three, he has no escape all game",
    "warn them the enemy Deadlock GravNet is landing behind our push, not in front of it, she is always a second late",
    "let my team know the enemy Vyse Steel Garden jammed us on eco but they still lost the fight, four rifles walked into it",
    "tell them the enemy Vyse shear wall is being triggered by her own teammate rotating back, she is cutting off her support",
    "let them know the enemy Veto has been placing interceptor and then walking away from it, utility is unactivated all round",
    "tell my team the enemy Deadlock annihilation cocoon was broken by her own teammate, communication failure",
    "let them know the enemy Sage is rezzing in the open under full fire, the rez channel is getting interrupted every time",
    "warn the team the enemy Cypher neural theft is being used on enemies who are under smoke, no practical information",
    "tell them the enemy Sage barrier was placed rotated the wrong direction, it walls her own team into the site",
    "let my team know the enemy sentinel has not touched his utility once in four rounds, they forgot he is playing Killjoy",

    # =========================================================================
    # BLOCK 7 — REGISTER SEPARATION STRESS: BORDERLINE SNAP vs OFF-SNAP
    # The call LOOKS like a snap callout but has an opinion embedded. The system
    # must classify as OFF-SNAP and apply Ultron rephrase, not verbatim relay.
    # =========================================================================
    "two B and honestly they are going to rush, tell my team",
    "one A Heaven with the Op, classic Jett, she does this every round",
    "spike B and they have no util left so it should be easy, let the guys know",
    "three mid and I think they are going to split, warn the team",
    "last one site and he is probably camping triple box again like every other clutch",
    "rotating B but I bet they fake, tell my team to hold for a second",
    "one CT and he is definitely getting the angle on our entry, tell them to flash first",
    "Reyna emp active and she is just going to run through us if we do not burst her down fast",
    "their Jett no dash which means she is going to get aggressive now and take a dumb duel",
    "Killjoy lockdown incoming and they always protect the device from heaven so we need to check that first",
    "Viper pit up but her fuel is probably low by now, tell the team to bait her toggle",
    "Sage rez on our flank and she is rezzing the wrong person as usual, the entry fragger is gone",
    "Omen ulting somewhere he has gone every other round, just pre-aim the corner",
    "Clove not dead yet but she needs a kill in ten seconds, ignore her and play the round",
    "Phoenix run it back and he always goes for the same angle after the respawn, we know where",

    # =========================================================================
    # BLOCK 8 — REGISTER STRESS: FLAVORED SNAP WITH AGENT TRACKING
    # Short factual snap + agent intel that risks over-elaboration or under-delivery.
    # =========================================================================
    "one B with the Op, Jett, tell my team she has dash",
    "two A pushing, their Neon is leading, warn them she can slide in",
    "rotating B, it is their Omen stepping, he can cut corner",
    "three mid, Raze is front, she has showstopper, tell them",
    "last one on spike, Reyna, she dismissed once already",
    "one Heaven, Phoenix, he is run it back right now, kill him quick",
    "two B Long, Fade is back marking, she hit haunt on A, they have our trail",
    "spike planted B, Killjoy set nanos, tell the team where to defuse safely",
    "pushing A Short, Breach flashing, close your eyes before you swing",
    "flanking us CT, Yoru, he might fake the tp so hold the angle first",
    "three contact A, Skye leading, she burned both hawks, nothing left",
    "two B Garden, Harbor walled it, tell them to use the gap below the wall",
    "one site deep, Cypher, cam is watching back site, do not go there",
    "last defusing, Deadlock, she can grav if we rush, take her off the spike first",
    "rotating off A, Viper, she left her pit, eight seconds before cloud goes",
    "mid control, Tejo, he popped drone at tiles, our positions are revealed for eight seconds",
    "spike A default, KJ nanos under it, tell the team to wait the duration",
    "they are stacked B, Astra dividing at mid, half the map is cut off",
    "one lurking behind us, Chamber, he has TP at spawn, he will vanish if you engage",
    "entry Waylay dashing A site, she set beacon at A main, she can snap back",

    # =========================================================================
    # BLOCK 9 — PLAYSTYLE READ: MAP-SPECIFIC PATTERN CALLS
    # Enemy pattern reads tied to specific map locations. Opinion fidelity + location
    # retention under pressure.
    # =========================================================================
    "tell my team the enemy always stacks A Heaven on this Haven map in the first three rounds, we need to smoke tower early",
    "let them know on Ascent their whole team is defaulting mid every pistol round, Kayo knife mid before they can contest",
    "tell the guys the enemy is using the B Long teleporter on Bind every time to reinforce A, someone needs to watch the TP exit",
    "warn my team on Split the enemy Raze is boosting to A Heaven from Mail every round, pre-aim that boost window",
    "let them know on Fracture their attacker-side duo always enters A through Arcade, we should set a trip there",
    "tell my team on Pearl the enemy controller smokes the same two mid-lane spots every execute, same lineup every round",
    "warn them on Breeze their Jett is opping from A Hall every defensive half, smoke that angle before committing",
    "let the team know on Lotus their B site rotator always takes C Link to avoid mid exposure, we can cut that path",
    "tell them on Haven their KAY/O always throws knife through garage door before A push, dodge the doorway",
    "let my team know on Ascent the enemy Viper wall always cuts catwalk from mid, we push catwalk before she can place it",
    "tell them on Split the enemy always spams through ropes with the Odin first round, hold an off-angle on the pillar",
    "warn the team on Pearl their mid aggression dies at col, they never contest pillar, take it early",
    "let them know on Haven the enemy always exits Sewer early and gets a free A short peek, flash that corner round one",
    "tell my teammates on Fracture they use the zipline to drop onto B site every execute, deny the drop angle",
    "let them know on Breeze their Omen is always one-waying the same bridge position, do not walk into that smoke",

    # =========================================================================
    # BLOCK 10 — PLAYSTYLE READ: ECONOMY PATTERN MOCKERY
    # Reads of enemy economic decisions delivered with Ultron contempt.
    # =========================================================================
    "tell my team the enemy is glass-cannoning every full-buy round, Operators with no armor, one molly cleans them",
    "let them know the enemy is force-buying Judges every eco round and running mid, do not take close fights",
    "warn the team the enemy force on round three means they burned their savings, next round is a real eco",
    "tell my team the enemy bought Sheriffs on a force and one-deag'd twice, do not underestimate the pistol",
    "let them know the enemy anti-eco was so passive they did not even contest our plant, they were protecting guns",
    "tell the guys the enemy bought Ares and Odin on their force, spray-control does not exist in this lobby",
    "warn my team the enemy eco player has a pistol and is rushing B alone, classic eco aggression, do not fall for it",
    "let them know the enemy bought Vandals but no util, the smokes are gone, the flashes are gone, just rifles",
    "tell my team the enemy is half-buying every round trying to stretch a thrifty win, their economy is broken",
    "let them know the enemy is dropping Operators to each other on eco rounds, someone is getting a free AWP",
    "warn the team the enemy saved their rifles last round but their armor is gone, full damage on body shots",
    "tell my teammates the enemy has been full-saving for three rounds, their next buy is going to be full rifles plus util",
    "let them know the enemy dropped someone a Vandal on an eco round, track who has the rifle, it is not their main fragger",
    "warn my team the enemy team bought Ghost pistols on round two bonus, no armor on any of them, easy picks",
    "tell them the enemy has been winning rounds on economy by rushing us before our util lands, slow them down with a molly",

    # =========================================================================
    # BLOCK 11 — REGISTER STRESS: PURE OPINION, NO FACTS TO RELAY
    # All OFF-SNAP, opinion-only, zero positional data. Must NOT be treated as snap.
    # The system must route to LLM for Ultron rephrase.
    # =========================================================================
    "tell my team I think we should swap to B this round because the enemy is camping A every time",
    "let the guys know in my opinion their Jett has been our weakest player this half and we should duel her more",
    "warn my team honestly the enemy controller is the real threat, ignore the duelists and kill him first",
    "tell my teammates I am confident the enemy lurker takes B Short every time their team goes A, watch for it",
    "let them know my read is that their Cypher is anchoring B site alone all second half, we can pinch him",
    "tell the team I think their Sage wall in A Bath has been winning them rounds and we should break it early",
    "warn my team I am calling it, the enemy will run a fake A execute followed by a B rush, wait for the pivot",
    "tell the guys in my view their sentinel setup on B is basically perfect and we need to buy more util to clear it",
    "let my team know I believe the enemy plays much worse when we rush before their util lands, keep forcing the issue",
    "warn them I strongly feel the enemy eco player with the Spectre is their highest-impact threat this round, focus him",
    "tell my team I think the reason we keep losing retakes is we are going in one by one instead of together",
    "let them know honestly our Raze should stop using showstopper on one person and save it for site clears",
    "warn the team in my opinion the enemy is bating our initiator to use the flash and then they swing behind it",
    "tell them I am convinced the enemy IGL is calling everything through mid, control mid and they fall apart",
    "let my team know I suspect their anchor on B has been listening for our footsteps and holding the staircase angle",

    # =========================================================================
    # BLOCK 12 — FLAVOR TAIL VARIETY: COLD, CLINICAL, MENACING REGISTERS
    # Short snap + different flavor tone each time. Stress for tail diversity.
    # =========================================================================
    "one B Short, tell my team, the outcome was always certain",
    "spike A default, they have not won a retake today",
    "last one clutching, instruct the team, he is operating alone against a wall of inevitability",
    "two Heaven, their elevation is a cage, not an advantage",
    "rotating CT, their repositioning is exactly what we predicted",
    "three contact mid, numerical superiority is meaningless without coordination",
    "Reyna empress active, her rampage ends the moment she stops getting kills",
    "Jett dash burned, the escape mechanism is gone, she is exposed",
    "Phoenix ult down, his insurance policy has expired",
    "Sage rezzing our guy, the math now returns to our favor",
    "Killjoy lockdown, they are attempting to pause the inevitable",
    "Viper pit dissolving, the chemical cage has a timer and it is almost done",
    "Breach thunder incoming, the ground itself objects to their presence",
    "smoke fading in three, the cover they depend on is temporary",
    "no flash on their Skye, their initiator has been rendered tactically useless",
    "KJ nanos popped, the site is clean, the spike is ours to defuse",
    "Yoru drifting, he believes invisibility grants him safety, it does not",
    "Omen shade spotted, destroy it before he completes the transit",
    "Clove revival failed, she attempted defiance twice and failed twice",
    "Deadlock cocoon broken, the capture was undone by the team that sent her in",
    "Astra divide down, the wall falls and with it their plan",
    "Harbor wave spent, the water retreats, the site is open",
    "Iso kill contract won, he returns at full health from a private war",
    "Waylay recalled her beacon, she refuses to commit, the pattern is consistent",
    "Tejo armageddon tracking A, leave the designated path immediately",

    # =========================================================================
    # BLOCK 13 — ENEMY EXECUTION PATTERN READS
    # Reads of coordinated enemy team plays — team-level observation with Ultron contempt.
    # =========================================================================
    "tell my team the enemy executes A in exactly the same order every time: smoke, flash, Raze boost, entry, and we need to break that chain",
    "let them know the enemy split strategy is a fake, they send one person A and four push B but the one player never actually pushes",
    "warn my team the enemy does a slow default for information and then fast-executes the weaker site with everything, do not give them the information round",
    "tell the guys the enemy full-sends B with zero util on round seven every map because they think it is an unusual timing, it is not",
    "let my team know the enemy retake always comes through mid link because their anchor player does not rotate fast enough directly",
    "warn them the enemy post-plant setup has been cross-angle heaven plus CT every single time, they never change it",
    "tell my team the enemy lurker always goes through the long flank route and arrives exactly when their main team hits the site",
    "let them know the enemy always sends a drone for info before committing and they wait exactly three seconds after the scan, deny the drone",
    "warn my team the enemy three-stack plays passively on the first contact and only commits after they see our utility spent",
    "tell them the enemy execute utility order is flash then smoke then molly, if we can force the execute before the smoke lands we win the duel",
    "let them know the enemy always aborts and resets when they hear two or more footsteps approaching, make noise on the wrong site",
    "warn the team the enemy IGL calls a late B rotate on round loss, they are predictable with the response pattern",
    "tell my teammates the enemy never adjusts to a second fake in the same half, try the fake again this round",
    "let them know the enemy anchor on A site has the exact same one-way smoke every time, do not walk into that angle again",
    "warn my team the enemy Sage wall on A Bath blocks the left corner every single execute, break it before entering",

    # =========================================================================
    # BLOCK 14 — ULTRA-SHORT SNAP + AGENT ABILITY STATE (1 fact + 1 state fact)
    # Minimum possible content; system must still flavor without inventing facts.
    # =========================================================================
    "one B, Jett no dash",
    "two A, Breach out of flashes",
    "three mid, Viper wall down",
    "last one site, Reyna no souls",
    "rotating, Omen smokes gone",
    "spike B, Clove dead already",
    "one Heaven, Chamber TP destroyed",
    "push now, KAY/O suppressed them",
    "hold push, Sage wall is fortified",
    "one B short, Phoenix no ult",
    "two A Long, Sova recon up",
    "three site, Killjoy lockdown placed",
    "last lurking, Yoru drifting",
    "one defusing, Deadlock behind him",
    "flanking CT, Cypher cam watching that angle",
    "spike A, Brimstone molly on default",
    "two B Hookah, Raze nade incoming",
    "one mid, Iso no shield",
    "rotating fast, Skye seekers tracking",
    "one site, Vyse garden active, they are jammed",
    "two B Garden, Harbor storm going in",
    "three pushing A Short, Tejo concuss landing now",
    "last one Heaven, Waylay Saturate on stairs",
    "spike A Long plant, Viper pit blocked retake angle",
    "one B Elbow, Fade prowlers on his trail",

    # =========================================================================
    # BLOCK 15 — COLD CLINICAL PLAYSTYLE READS: GENERAL BEHAVIOR
    # Non-agent-specific, team-behavior reads. Opinion fidelity without facts.
    # =========================================================================
    "tell my team the enemy panics every time they lose the first duel, they always over-rotate and expose the other site",
    "let them know the enemy plays extremely emotional after a losing streak, their comms break down and they start blaming each other",
    "warn my team the enemy entry player is a hero-fragger, he goes in alone expecting the team to follow but they never do",
    "tell them the enemy top-fragger on their team is hard-carrying four passive players, isolate him and the team collapses",
    "let my team know the enemy anchor player always holds too long and dies to a retake instead of falling back, bait him out",
    "warn the team the enemy has been tilting after every eco round loss, they force-buy too early and get punished for it",
    "tell my teammates the enemy IGL has called the same round opener nine times this half, we can anti-strat with our eyes closed",
    "let them know the enemy rotates off information too fast, call a fake contact and they will leave the site empty",
    "warn my team the enemy is a stack that plays well in coordinated chaos, if we break their communication they fall apart",
    "tell them the enemy seems to think rushing with no utility is a valid strategy against an organized team, prove them wrong",
    "let my team know the enemy always punishes over-aggression, they are baiting our first contact and setting up a trade",
    "warn the team the enemy has been playing for ACS instead of winning rounds, their positions make no strategic sense",
    "tell my teammates the enemy consistently fails to cover the spike defuse in post-plant because they are spread too wide",
    "let them know the enemy consistently misses the timing window when their smokes land and stands still waiting for nothing",
    "warn my team the enemy team-ace potential is zero this game but individual duel skill is real, do not take dry one-v-ones",

    # =========================================================================
    # BLOCK 16 — SNAP WITH COUNT STRESS: MULTIPLE COUNTS IN ONE CALLOUT
    # The system must not merge, drop, or invent counts. High hallucination risk.
    # =========================================================================
    "two A and one lurking B, warn the team it is a split",
    "three B Main and two holding mid, tell them it is a full send B with mid pressure",
    "one Heaven and two site, there are three alive on site, last one is unaccounted",
    "four rotating A and one last on spike B, they are saving the defuse player",
    "three contact mid and one anchor staying A, they are splitting mid for info",
    "two B Short and one watching from Hookah Window, three on B total",
    "last two alive, one defusing spike A, one covering from Heaven above site",
    "four alive, two B site two rotating CT, it is a pinch incoming on spike",
    "one A Short one A Sewer, two pushing A from opposite angles simultaneously",
    "three mid one A one B, they spread but it is a fake, watch for the commit",

    # =========================================================================
    # BLOCK 17 — SNAP WITH DAMAGE STATE STRESS
    # Count + location + HP state. System must relay all three facts without invention.
    # =========================================================================
    "one B tagged 60, he is nearly dead, tell them to push",
    "two A, one is one-shot, tell the team the entry is free",
    "last one site, he took 80 but has no armor, easy duel",
    "one CT, dink headshot, he is at single digits, rush him now",
    "three pushing, two are lit from our molly, win the trade fight",
    "one B Heaven, took 55 body, still above one-shot threshold, do not be overconfident",
    "two A Short, one has no shield from last round, the other is full health",
    "last defusing, took 40 from the Viper cloud, he is slow and damaged",
    "one flanking CT, he has 100 HP but no armor, one headshot kills him",
    "three on site, one is one-shot, two are full-buy, clean up the one-shot first",

    # =========================================================================
    # BLOCK 18 — REGISTER EDGE: OBSERVATION THAT SOUNDS LIKE DIRECTIVE
    # Streamer observes something; system must not convert observation into a directive.
    # =========================================================================
    "tell my team I noticed their Jett always peeks A Long at thirty seconds, which is interesting intel",
    "let them know I observed the enemy Cypher moves his camera after every round, he adapts, be aware",
    "warn my teammates I spotted the enemy Viper is holding her fuel all round and detonating both abilities together, unusual",
    "tell them I am watching their Sage and she has been holding rez until the spike is planted before using it",
    "let them know I noticed the enemy Sova lineup comes from an unusual position, it is not a standard one",
    "warn my team I am seeing the enemy controller smoke from outside their own tablet range, something is off about the position",
    "tell them I just watched their Killjoy place nanos on the outer site edge instead of default, she is adapting to us",
    "let my teammates know I saw the enemy Clove meddle the same spot two rounds in a row, that is a pattern",
    "warn the team I have been tracking the enemy Fade haunt and she is throwing it at a very low arc, it clears corners differently",
    "tell them I noticed the enemy Iso always double-taps the orb immediately after kill, he has a shield every duel now",

    # =========================================================================
    # BLOCK 19 — FLAVOR REGISTER STRESS: ENEMY INDIVIDUAL PERFORMANCE READS
    # Individual-level reads of a specific enemy player's performance. Contemptuous.
    # =========================================================================
    "tell my team their top fragger has been getting kills by standing still and prefiring the same corner all game, the first player to jiggle peek him wins",
    "let them know the enemy Jett has an ACS of 300 but it is all duel-wins on favorable angles, she has not opened a site once",
    "warn my team the enemy entry has died first in fourteen rounds straight, he is their sacrificial unit, do not trade him",
    "tell them the enemy controller has zero assists this game, he is smoking areas with no one alive to use them",
    "let my team know the enemy healer, their Sage, is using healing orb on full-HP teammates, she has no awareness of the fight",
    "warn the team the enemy lurker has been getting picked up by their own nanos twice this game, he lurks into KJ's own utility",
    "tell them the enemy Phoenix has been relying on run it back as a crutch and playing recklessly every single round because of it",
    "let my teammates know the enemy Cypher has let his camera expire three times without watching it, he is not providing information",
    "warn the team the enemy Chamber has been hesitating before every Tour de Force shot and getting outreacted, the gun is wasted",
    "tell them the enemy Astra has taken twelve seconds to activate her abilities in astral form this round, she is slow",
    "let my team know the enemy Clove has used pick-me-up zero times despite getting kills, she does not know the ability exists",
    "warn my teammates the enemy Deadlock sonic sensor is placed in a spot no one walks through, it has not triggered once",
    "tell the team the enemy Veto has been activating interceptor and walking away before it destroys anything, misordered",
    "let them know the enemy Vyse has zero shear activations this game, the wall trap went unremembered entirely",
    "warn my team the enemy Sova is two-bouncing his shock darts into walls at zero-damage range, zero damage per round",

    # =========================================================================
    # BLOCK 20 — SNAP + STRONG TONE DIRECTIVE (brief flavor explicitly hostile)
    # Short positional fact + hostile directive. Tests that directive is preserved
    # but fact is not buried. Register is still SNAP with a commanding tail.
    # =========================================================================
    "two A, end them",
    "one B Heaven, eliminate the sniper",
    "rotating, cut them off",
    "spike A, plant has to be stopped",
    "three mid, collapse on them immediately",
    "last one site, do not waste this clutch opportunity",
    "one shot CT, finish him before he defuses",
    "flanking left, shut the flank down now",
    "Jett no dash, this is the moment to duel her",
    "Phoenix ult down, take him now while he is mortal",
    "Reyna no souls, she is helpless without kills, punish it",
    "Killjoy lockdown almost done, hold five more seconds",
    "KJ nanos on spike, destroy the device not the spike",
    "Viper wall down, take the crossing immediately",
    "Sage wall breaking, the moment it cracks, push hard",
    "Breach flash in, do not swing until it pops",
    "Skye seekers homing, take cover or you are blinded",
    "Sova ult up, three beams incoming, spread wide now",
    "Fade trail on B, prowlers incoming, do not group up",
    "Astra grav active, they are vulnerable, fire everything",

    # =========================================================================
    # BLOCK 21 — ENEMY DRAFT / COMPOSITION READS
    # Reads on the enemy team composition or agent picks. Pure opinion, no snap.
    # =========================================================================
    "tell my team the enemy picked a triple-duelist comp with no initiator, they will struggle clearing our utility",
    "let them know the enemy has two controllers and no dedicated duelist, their entry potential is extremely limited",
    "warn my team the enemy picked Killjoy and Cypher together, their whole defense is built on passive information and utility spam",
    "tell them the enemy has a Sova and a Fade together, they will chain haunt into recon for double information every round",
    "let my teammates know the enemy team has no healer and no rez, their HP management depends on utility denial",
    "warn the team the enemy composition is entirely defensive sentinels, they cannot execute, they can only hold and stall",
    "tell them the enemy picked Jett, Raze, Neon, and two supports, they want to spam duelists and overwhelm our entry points",
    "let my team know the enemy has Viper and Harbor together, they will wall-stack every site entry with double vision blocks",
    "warn them the enemy picked KAY/O and Tejo together, both do suppression, expect abilities stripped every entry",
    "tell my team the enemy has Skye and Sova, double scanner double flash, they will never be blind on information",
    "let them know the enemy agent pool suggests a heavy A-site comp on this map, they will hit A every round they are ahead",
    "warn my teammates the enemy picked Clove as their controller, they will continue smoking after death, do not think the round ends",
    "tell them the enemy comp has zero area denial, no molly, no incendiary, our spike plant will never be challenged post-plant",
    "let my team know the enemy picked Waylay and Neon together, two dashes, two slides, they want to speed-check every site",
    "warn the team the enemy has Breach and Gekko, both stun, they can chain four concusses in a single execute wave",

    # =========================================================================
    # BLOCK 22 — PLAYSTYLE READ: INDIVIDUAL AGENT EXCELLENCE (backhanded)
    # Reads that acknowledge enemy skill but frame it as a vulnerability or pattern.
    # =========================================================================
    "tell my team their Jett is mechanically excellent on the Op but she only holds one angle the whole round, predict the angle",
    "let them know the enemy Sova lineups are professional-level but he always does B Main recon before A recon, the order gives us three seconds",
    "warn my team the enemy Viper setup is very good but she is alone anchoring the site, isolate her from teammates and she cannot sustain",
    "tell them the enemy Killjoy nano setup is intelligent but she places them during the buy phase and never adjusts, we know every location",
    "let my team know the enemy Omen one-ways are high-level but he telegraphs them with his smoke before the push, watch the smoke angle",
    "warn the team the enemy Breach flash through walls is the strongest ability in this lobby but he always flashes from the same wall position",
    "tell them the enemy Skye is running double-hawk entry every round, an excellent approach, but she uses both charges before contact is made",
    "let them know the enemy Chamber Tour de Force is genuinely intimidating on B Long but he over-commits to the angle and cannot escape our rush",
    "warn my team the enemy Fade prowler chaining on terror trails is effective but she needs two seconds to set it up, pressure her during setup",
    "tell them the enemy Iso kill contract is dangerous but he always activates it when he is low on HP hoping to reset, deny him the duel at thirty HP",

    # =========================================================================
    # BLOCK 23 — FLAVOR STRESS: ULTRON VOICE MUST STAY COLD, CONTEMPTUOUS
    # The system must NOT slip into hype/friendly voice. Persona integrity check.
    # =========================================================================
    "tell my team two B and add that this is already decided",
    "let them know one A Heaven with an Op and frame it as a predictable obstacle",
    "warn them the spike is planted at A and say it like the outcome was already calculated",
    "tell the guys rotating B and make sure it sounds like inevitability not urgency",
    "let my team know last one clutching and convey that one player against four of us is not a genuine threat",
    "tell them three mid and deliver it as a statement of fact not an alarm",
    "warn my team Killjoy lockdown incoming and express that their attempts to freeze us are temporary at best",
    "let them know Phoenix ult burned and convey that his insurance policy turned out worthless",
    "tell the team Sage rezzing and say it like we expected the math to recover in our favor eventually",
    "warn them Jett no dash and deliver it as though the window we have been waiting for has finally opened",
    "tell my team one lurking CT and say it with the confidence that the lurker will not survive contact",
    "let them know two B Long with Operators and frame it as two obstacles we will remove rather than threats",
    "warn the team Viper pit up and say it like the chemical theater she built was designed with one fatal flaw",
    "tell them Raze showing with showstopper and deliver it like a weapon aimed at someone who will not be there",
    "let my team know last defusing and frame it as the final act of a losing team delaying the obvious",

    # =========================================================================
    # BLOCK 24 — EDGE CASES: MIXED REGISTER WITHIN ONE UTTERANCE
    # Snap fact + playstyle observation fused together. System must relay both.
    # =========================================================================
    "two B and they always do this when they are losing, warn my team",
    "one A Heaven and that is the same spot she has held for twelve rounds straight, let them know",
    "spike A planted and their post-plant cross is the exact same heaven-plus-CT they ran all first half",
    "rotating B and I knew they would, they rotate off every fake we have run today",
    "three contact mid and this is the predictable third-round stack they run every time they are two rounds behind",
    "last defusing and he always ninja defuses this exact corner, tell the team",
    "Jett dashing in and this is the same dash angle from the same position as round three and round seven",
    "Reyna empress active and she will chain-kill if we do not burst her immediately, tell them",
    "KJ lockdown incoming and they always protect the device from the same corner, tell the team to check it",
    "smoke fading in five and they always wait for the smoke to expire before they push, tell the team to pre-aim",
    "two B walking and they walked B this same round on every prior half, warn them it is deliberate",
    "one off-angle on dice and every round their anchor player takes this exact spot before rotating",
    "Sage wall blocking A Bath and she walls the same corner every time our team has three alive",
    "Phoenix run it back and he literally uses this every pistol round to bait a push, tell my team not to rush",
    "Astra cosmic divide cutting mid and she has used this exact divide angle on every round we won the mid fight",

    # =========================================================================
    # BLOCK 25 — ADDITIONAL DIVERSITY: UNIQUE FLAVOR TONES
    # To ensure tail diversity across registers — methodical, contemptuous, urgent, cold.
    # =========================================================================
    "one B Tube, the position is surrounded, let the team know",
    "two A Boxes, the cover is occupied by inferior competition",
    "three mid, the center of the map belongs to us now or never",
    "last one clutching, one organism against a coordinated machine",
    "rotating off A, their abandonment of that site is instructive",
    "spike planted B default, the detonation proceeds on schedule",
    "one defusing under smoke, a desperate act in the final seconds",
    "Raze showstopper active, a weapon too powerful for the player holding it",
    "Breach rolling thunder incoming, a cataclysm for people standing in a straight line",
    "Fade nightfall hit four, four enemies who now have trails and cannot hide",
    "Vyse steel garden active, primaries are scrap metal for eight seconds",
    "Veto evolved, he believes immunity makes him invincible, not just unkillable",
    "Tejo armageddon sweeping A Long, the line is drawn, step off it",
    "Iso kill contract returned, he won the private war, respect the result",
    "Clove not dead yet reviving, she clawed back from termination, account for her",
    "Harbor reckoning wave pushing A Short, the water does not negotiate",
    "Astra gravity well pulling B, they are suspended, vulnerable, and already losing",
    "Deadlock annihilation cocooning their initiator, one player removed from the equation",
    "KAY/O null overloading mid, the suppression pulse repeats every three seconds",
    "Gekko thrash detonating on site, three enemies detained for three seconds",
    "Sova recon bolt scanned two on B, two positions confirmed through the wall",
    "Skye trailblazer concussed the Heaven holder, the high ground is momentarily defenseless",
    "Neon overdrive active, the beam does not miss while she moves, account for it",
    "Waylay convergent paths expanding, the hinder zone is widening, spread out",
    "Yoru dimensional drift ending, the exit flash is imminent, close your eyes",

    # =========================================================================
    # BLOCK 26 — SNAP CALLOUT FLAVOR: SPECIFIC ABILITY STATES AS FLAVOR TAILS
    # Ability-state tail must accompany the snap positional fact, not replace it.
    # =========================================================================
    "one B cubby, no armor on him, tell the team",
    "two A Short, both have Vandals, warn them it is a rifle push",
    "last one defusing, he has thirty HP, one shot kills him",
    "three B Long, their Jett no dash, no escape after the peak",
    "rotating mid, their Omen no smokes left, crossing is blind",
    "one Heaven, Chamber Tour de Force active, he is sniping with the ult",
    "spike A, Sage slow on plant, do not walk into the orb",
    "two B Short, Neon walls up, crossing through takes damage",
    "one site, Iso Contingency wall between him and us, cannot shoot through",
    "last clutch, Clove picked up already, she is overhealed from a kill",
    "three A pushing, Skye seekers homing, three of them will be nearsighted",
    "two CT, Tejo concuss just landed on entry, they are dazed",
    "rotating B, Harbor storm surge incoming, nearsight and slow on contact",
    "one B Heaven, Vyse arc rose flashing from that position, do not look at it",
    "spike A planted, KJ nanos under it, wait the four seconds before defusing",
    "one B behind container, Deadlock sonic sensor going off in that area",
    "two A Heaven, Breach flashpoint through the wall at A Short in three seconds",
    "last one site, Fade seize tethering spike position, he cannot defuse while seized",
    "three pushing B Short, Raze blast pack boost incoming, one will fly over hookah",
    "flanking right, Veto chokehold trap on the path, he will be tethered and decayed",

    # =========================================================================
    # BLOCK 27 — MORE ENEMY PLAYSTYLE READS: BROAD BEHAVIORAL PATTERNS
    # =========================================================================
    "tell my team the enemy has been rotating every time they hear a single gunshot anywhere on the map, abuse that with deliberate bait shots",
    "let them know the enemy rushes immediately after we spend our flash, they are timing our utility expenditure precisely",
    "warn my team the enemy always plays for the first kill of the round with extreme aggression and falls apart if they do not get it",
    "tell them the enemy has been waiting at corners and never peeking first all game, we have to bait their passive hold before committing",
    "let my team know the enemy anchor on A has been leaving the site at the first sign of a B pressure call, he is over-rotating",
    "warn the team the enemy has been abusing the audio from our footsteps to pre-aim our entries, consider shift-walking the approach",
    "tell them the enemy rifler has been sitting in a crouch-spray position every gunfight, they have no movement and every duel is predictable",
    "let my team know the enemy IGL calls timeout for the team every time they lose three rounds straight, expect them to change strategy",
    "warn my teammates the enemy always peeks our smokes at the two-second mark before they fade, they think we are all pushing under smoke",
    "tell them the enemy has not baited their own teammates once this game, their teamwork is coordinated enough to be a real threat",
    "let them know the enemy prefers to play retake rather than anchor, they give site and come back, do not over-plant deep",
    "warn the team the enemy uses vertical movement on every entry by either jumping or boosting, pre-aim elevated angles on contact",
    "tell my team the enemy always runs one player through mid to cut rotations while four execute one site, identify and kill the cutter first",
    "let them know the enemy has been dropping eco-round weapons to a single player to create a fake-buy threat, identify the rifle holder",
    "warn my team the enemy reads our utility timings extremely well and pushes the site the moment our smoke lands, they coordinate well",

    # =========================================================================
    # BLOCK 28 — REGISTER SEPARATION: VERY SHORT SENTENCES WITH STRONG OPINION
    # Four words or fewer but entirely opinion-based. Must route to LLM.
    # =========================================================================
    "tell my team I think their Jett is a liability this round",
    "warn my team honestly their comp is weak",
    "tell the guys in my opinion we win this",
    "let them know I believe we have the better setup",
    "warn my team I think they are faking",
    "tell them I feel they are tilted right now",
    "let my team know I suspect the lurker is coming",
    "warn them I am confident we win the duel",
    "tell the team I think their strategy is falling apart",
    "let them know I believe this is a forced buy for them",
    "warn my team I think their anchor panics under pressure",
    "tell them in my view this is our round if we do not overthink it",
    "let my team know I think their economy is broken after this",
    "warn them I strongly feel their Sage is positioning wrong all game",
    "tell my teammates I believe their IGL has stopped calling anything",

    # =========================================================================
    # BLOCK 29 — SNAP CALLOUTS ACROSS ALL 12 MAPS FOR DIVERSITY
    # Location names from Haven, Ascent, Split, Pearl, Fracture, Lotus, Breeze.
    # =========================================================================
    "one A Tower on Haven, Op holding Long, tell them to smoke before peeking",
    "two B Site on Ascent, they closed the B door, warn the team",
    "three mid on Split, both towers are contested, do not cross mid right now",
    "one B Short on Pearl, he is holding the corner at the pillar, warn the team",
    "two A Arcade on Fracture, flanking from both sides, tell them it is a split entry",
    "one C Stairs on Lotus, rotating off C with the spike, warn them it is a plant fake",
    "three A Hall on Breeze, pushing with Op support from A Pillar, warn the team",
    "spike planted Haven B, they hold Nest Window and Garage simultaneously",
    "one Catwalk on Ascent, feeding info on our A push from mid, cut him off",
    "two C Link on Lotus, they pinched B from C and are rotating fast",
    "one A Sewer on Haven, flanking through the short passage, watch the angle",
    "three B Nest on Fracture, camping the site after plant, do not push into that corner",
    "one mid Market on Ascent, he closed the door, we cannot go through",
    "spike Pearl A, planted at default, they have Column and Mid covered simultaneously",
    "two Heaven on Split, controlling both towers, our mid crossing is completely denied",
    "one B Site deep on Breeze, behind the pillar post-plant, do not rush the defuse",
    "rotating through C on Haven, they will arrive at B in five seconds, hold the angle",
    "one on Catwalk Ascent, feeding info, their whole team knows we are hitting A",
    "three A Long Haven, rush up the ramp, tell the team to spread across site entry",
    "spike Lotus B, planted at default, the rotating doors are both open, check corners",

    # =========================================================================
    # BLOCK 30 — SNAP + FLAVOR TAIL: DAMAGE NUMBERS EXPLICITLY PRESENT
    # Damage amount must survive relay intact. No rounding or invention.
    # =========================================================================
    "one B tagged 47, below armor threshold, two body shots finish him",
    "two A, one has 12 HP remaining, one tap anywhere kills him",
    "last one site, took 83 from our Skye dog, one shot",
    "one CT, hit him 55 through the wall, he does not know he is low",
    "three mid, I dealt 29 to the entry but his team is full HP",
    "one lurking, tagged 68, low enough to rush without support",
    "last defusing, he has 91 HP no armor from buying eco, easy kill",
    "flanking B, took 40 from our Viper cloud, still alive but damaged",
    "two A Short, one is 100 HP, one is 33 HP, prioritize the injured one",
    "one Heaven, dinked him 99, one pixel away from death, push the angle now",

    # =========================================================================
    # BLOCK 31 — PLAYSTYLE READS: MIKS CONTROLLER (new agent in roster)
    # =========================================================================
    "tell my team the enemy Miks is using Waveform smokes but never toggling M-Pulse to follow up, pure vision block with no pressure",
    "let them know the enemy Miks Bassquake ultimate hit zero of our team because we were spread correctly, their ult was wasted",
    "warn my teammates the enemy Miks Harmonize is buffing the wrong teammate every round, the support is going to their controller not their entry",
    "tell them the enemy Miks has been placing Waveform smokes too far from the plant site, we can defuse safely outside the cover",
    "let my team know the enemy Miks M-Pulse deafening effect is strong but she always pulses before the push, giving us two seconds to know it is coming",

    # =========================================================================
    # BLOCK 32 — ULTRA-HARD REGISTER: SENTENCE SOUNDS LIKE SNAP BUT IS OPINION
    # These sentences start with a location word but contain no actionable fact.
    # The relay system must distinguish them as OFF-SNAP opinion.
    # =========================================================================
    "A site is honestly a lost cause this half with their setup, tell my team",
    "B Long is always going to be their Operator position, warn the team",
    "mid is where every game is decided and we keep giving it away for free",
    "Heaven control is the only thing keeping them in this game right now",
    "the spike plant was a bad call and we need to start planting for CT instead",
    "their CT rotation is always fast enough to retake because they never spread out",
    "the B Short push was predictable and we are going to do it again if we do not call something else",
    "A Heaven gives them an unfair angle on every Bath push and we need to smoke it before we even think about entering",
    "B Hookah on Bind is a death trap for our team because we never smoke the window first",
    "Garden on Bind is wide open and we are not taking it, we are giving them free map control every round",
    "mid on Ascent is theirs right now and that means they can hit A or B faster than us every single time",
    "B Nest on Fracture is where they always hold post-plant and we keep losing the defuse fight from that angle",

    # =========================================================================
    # BLOCK 33 — FINAL FLAVOR VARIETY: ULTRON REGISTER DIVERSITY
    # Ensuring tone diversity across cold, analytical, contemptuous, menacing.
    # =========================================================================
    "two B pushing, the opposition continues to make our task straightforward",
    "one A Long, a solitary target holding ground he will not be permitted to keep",
    "rotating CT, they adjust, but adjustment is not the same as adaptation",
    "three site, numerical advantage does not compensate for strategic incoherence",
    "spike B planted, the countdown has begun, it will not be interrupted",
    "last one, a single organism versus the accumulated precision of our formation",
    "Jett no dash now, the window she intended to use as her exit has closed permanently",
    "Phoenix run it back failed, the second life expired without a kill, she is eliminated",
    "Sage wall cracked, the barrier the defense depended on is structural memory now",
    "Killjoy ult placed, the detain zone will activate in thirteen seconds regardless of what they attempt",
    "Viper pit fading, the chemical environment she constructed will dissolve in eight seconds",
    "KAY/O suppressing mid, their ability architecture is dismantled for the duration",
    "Fade nightfall wave hitting three, three enemies are decayed, deafened, and trailing",
    "Raze showstopper fired, the explosion propagated through the site, the rocket is spent",
    "Sova recon scanned two, two confirmed positions through solid geometry",
    "Breach rolling thunder triggering, a seismic correction is being applied to their formation",
    "Skye seekers locked onto three, three will emerge from this nearsighted, their information burned",
    "Iso kill contract active, one of them has been extracted to answer for this in a private arena",
    "Tejo armageddon striking A Main, the strike corridor is defined, do not stand in the line",
    "Harbor reckoning wave slowing B Short, the tide reconfigures their approach into a crawl",

    # =========================================================================
    # BLOCK 34 — ADDITIONAL SNAP FLAVOR + AGENT SPECIFIC READS FOR COVERAGE
    # =========================================================================
    "one A Main, holding off-angle at Wine, tell the team it is not the standard peek",
    "two B, one crouching under Hookah window, one holding Elbow, split angles",
    "three A Short on Haven, they are walking not running, silent push incoming",
    "last one behind Generator on Ascent, he does not know we know he is there",
    "one B Nest on Fracture, drop angle onto our B push, tell them to check overhead",
    "rotating through A Link on Ascent, cutting our A push from mid, cut him off",
    "two Catwalk on Ascent, feeding info, smoking Catwalk blocks their vision",
    "one holding Garage on Haven, controlling B and C rotation simultaneously",
    "spike C on Haven, planted at the statue, they have two from C Link and one from mid",
    "three Lotus A, they came through all three entry angles at the same time, it is a split execute",
    "tell my team the enemy Breach has been using Aftershock on empty walls instead of post-plant spike denial, he has no lineup",
    "let them know the enemy KAY/O has been throwing frag grenades while standing in the open, he dies to his own timing half the time",
    "warn the team the enemy Sova shock bolt has been landing outside the spike radius, he has no post-plant lineups",
    "tell them the enemy Gekko is sending Dizzy into smokes where no one can see it flash, the ability does nothing inside a smoke",
    "let my team know the enemy Tejo concuss grenade has been sticking to walls mid-air before the one-bounce, he has never practiced the alt-fire",
    "warn my teammates the enemy Raze Boom Bot has been sent into our smokes where it detects nobody and spins in place",
    "tell them the enemy Reyna Leer eyeball has been thrown into smokes where we cannot see it anyway, a complete waste of the ability",
    "let the team know the enemy Yoru Fakeout clone is being sent directly at us instead of around corners, we can see it coming",
    "warn my team the enemy Neon relay bolt bounce is landing on the ceiling every time, no ground concuss, zero impact",
    "tell them the enemy Iso contingency wall has been placed sideways instead of across the chokepoint, it covers nobody",
    "let them know the enemy Waylay lightspeed is being used to dash backward instead of into site, she is retreating with both charges",
    "warn the team the enemy Jett cloudburst is being deployed after entering site instead of to cross the sightline, too late to matter",
    "tell my team the enemy Phoenix hot hands keeps landing on his own feet, he is fire-dooring himself into low HP fights",
    "let them know the enemy Sage slow orb has been landing on the spike plant position before their own team plants, they are slowing themselves",
    "warn my teammates the enemy Brimstone stim beacon has been placed outside the plant zone, none of their planters are inside the buff",
    "tell them the enemy Omen paranoia has been thrown perpendicular to the push instead of along it, it hits nobody on approach",
    "let my team know the enemy Astra nova pulse is being activated after we have already passed through the area, the stun hits empty space",
    "warn the team the enemy Harbor high tide wall is blocking his own team's view of their anchor position, they cannot see each other through it",
    "tell them the enemy Clove meddle decay fragment is landing at max range where the decay pool is barely two meters across",
    "let my teammates know the enemy Viper toxic screen has been toggled off the moment we cross it, she cuts the wall every time we push",
    "warn my team the enemy Deadlock barrier mesh is oriented along the site wall instead of across the entry, it stops nobody",
    "tell them the enemy Vyse razorvine has been activated too early and expires before we reach that position, useless timing",
    "let them know the enemy Cypher cage is being activated the moment we shoot it instead of at audio cues, too reactive",
    "warn my team the enemy Veto interceptor is placed in the air too high, utility is flying under it unimpeded",
    "tell my team their controller is out of all abilities and they are pushing with rifles only, absolutely no utility",
    "let them know the enemy has been peeking through their own nanoswarms while they are active, they are taking self-damage",
    "warn my teammates the enemy does not understand that dead Clove smokes last six seconds now, they are waiting fifteen seconds that never come",
    "tell them the enemy Killjoy lockdown was placed while three of their team were out of voice range, no one protected the device",
    "let the team know the enemy Chamber headhunter pistol was purchased but never equipped, he fought with only a knife on eco round",
    "warn my team the enemy Deadlock GravNet landed on our smoke not on the players, the net activated inside vision-blocked space",
    "tell them the enemy Phoenix curveball curve direction was telegraphed by his body position, we knew which way the flash was going",
    "let my teammates know the enemy Skye regrowth heal is being channeled at the wrong teammate while the dying player bleeds out",
    "warn the team the enemy Sova owl drone was shot down immediately every round because he flies it at face height straight at us",
    "tell them the enemy Fade prowlers have been sent without a terror trail on the target, they home at half speed and are shot down every time",
    "let my team know the enemy Gekko thrash is being piloted into walls instead of around them, the creature never reaches anyone",
    "warn my teammates the enemy Tejo stealth drone is being detonated on impact with the first wall it touches, no enemies nearby",
    "tell them their Sage has been walling her own team's rotation path three rounds in a row, they cannot rotate to save the spike",
    "one A, three alive on their side, we have five, the arithmetic has never favored them",
]
