"""Vocab pack: directive vs observation traps.

Domain: RELAY commands that are directive-shaped observations (easily confused with orders)
vs genuine directives; also pairs where the same surface form flips meaning depending on
subject/verb. Engineered to BREAK directive-vs-observation discrimination in the relay
pipeline — hardest realistic versions a streamer/teammate actually says.

Stress targets:
  - "smoke A" (order) vs "they smoked A" (report)
  - "crossfire this corner" (order) vs "they are crossfiring" (report)
  - "rotate B" (order) vs "they rotated B" (report)
  - "flash entry" (order) vs "they flashed entry" (report)
  - "rush mid" (order) vs "they rushed mid" (report)
  - "play retake" (order) vs "they're retaking" (report)
  - first-person narration shaped like a directive
  - passive-voice observations that look like directives
  - third-person directive ("he should anchor") vs actual anchor order
  - near-identical pairs stress-tested across every map, ability, utility, and agent

All items are genuine relay commands (kind=relay) — a streamer issuing the instruction
or a raw callout the system wraps. Observations that are NOT for relay are excluded
(those are negative-kind cases).

Agents, ability names, and map callouts verified against refs/*.md. June 2026.

Kind: relay (~600 cases)
"""

ITEMS = [
    # =========================================================
    # SMOKE DIRECTIVE (order) vs SMOKE OBSERVATION TRAPS
    # The item is a RELAY — the streamer wants it sent to team.
    # Challenge: system must relay the directive, not mishear
    # "smoke A" as merely reporting that A is smoked.
    # =========================================================
    "tell them smoke A main before we push",
    "relay: smoke both entrances to B site",
    "let my team know to smoke CT so I can plant safely",
    "tell them smoke the spike before they defuse it",
    "relay to my squad: smoke heaven on Haven A site",
    "tell them pop smokes on elbow before we entry",
    "let my team know smoke the default plant and we go",
    "tell them smoke mid doors so we can cross safely",
    "relay: smoke short on Split before the ropes push",
    "tell my teammates to smoke screens on A so we walk in clean",
    "relay to the team: smoke Catwalk connector before we execute",
    "tell them smoke garage entry on B Split so we don't get picked",
    "let my squad know smoke the B link so the lurk doesn't get caught",
    "tell my team smoke heaven and Catwalk so we split A on Ascent",
    "relay: smoke the A door window before we break through",
    "tell them smoke CT rotation path so we can plant default",
    "let my team know smoke both angles on B heaven on Split",
    "tell them smoke the tree room on Ascent so we take A together",
    "relay to teammates: Brimstone needs to smoke B main and back site",
    "tell my squad to smoke the hookah and short simultaneously on Bind",

    # =========================================================
    # OBSERVATION TRAP — "they smoked X" / "their smoke on X"
    # These ARE relay commands (reporting info the streamer
    # wants passed to the team), but they are OBSERVATIONAL —
    # the pipe must not treat them as instructions to place smoke.
    # =========================================================
    "tell my team they smoked A main so watch for a push",
    "relay: they smoked CT, they're probably executing B",
    "let my teammates know they smoked both entries, execute is coming",
    "tell my team their Brimstone smoked heaven and elbow on A",
    "relay to my squad: they smoked short and screens, expect A execute",
    "tell them their Omen smoked the link, someone's lurking",
    "let my team know their Viper walled mid and they're pushing B",
    "tell my squad their Astra smoked every angle on B site",
    "relay: they smoked catwalk and tree, they're all going A",
    "tell my teammates their smoke on garage is up, expect B push",
    "relay to team: their controller smoked off our rotation, be ready",
    "tell them they smoked B long and are trading through it",
    "let my team know their Clove smoked from the grave, smokes still up",
    "tell my squad they popped smokes on B and they're running it",
    "relay: three smokes went down on A, full execute incoming",
    "tell them one smoke dropped on C heaven, someone's watching CT",
    "let my teammates know their Viper's Pit is up on B, don't rush in",
    "tell my team their Omen dropped a one-way smoke on short",
    "relay: they smoked the spike, they're setting up post-plant",
    "tell my squad their smokes are fading, we have a push window",

    # =========================================================
    # CROSSFIRE DIRECTIVE vs CROSSFIRE OBSERVATION TRAPS
    # =========================================================
    "tell them set up a crossfire on the defuse spot",
    "relay: crossfire the B main entry from heaven and garage",
    "let my team know crossfire this corner from both sides",
    "tell them play crossfire on heaven and elbow for the retake",
    "relay to my squad: crossfire CT with two players, third covers flank",
    "tell them crossfire the A door from pillar and gen",
    "let my team know we play crossfire on the spike, don't fight in open",
    "tell my teammates set up a crossfire from B tower and back B",
    "relay: crossfire A long from short and window simultaneously",
    "tell my squad crossfire the bomb from split angles so they can't peek",
    "tell them they have a crossfire set up on the defuse, don't peek it",
    "relay: they're crossfiring the spike from heaven and back site",
    "let my team know they have a crossfire waiting at CT, don't rotate blind",
    "tell them their crossfire is on B site, two angles covered",
    "relay to teammates: they're playing crossfire on the default, find them first",
    "tell my squad they set up crossfires on every retake angle, play slow",
    "let my team know their KJ placed nanos and they're crossfiring on top",
    "tell them the two players alive are crossfiring our defuse",
    "relay: they have a crossfire from B rafters and B back, don't peek together",
    "tell my team their crossfire covers both entry points, we need util first",

    # =========================================================
    # ROTATE DIRECTIVE vs ROTATE OBSERVATION TRAPS
    # =========================================================
    "tell my team rotate B right now",
    "relay: rotate through CT, don't go mid",
    "let my teammates know rotate A immediately, B is clear",
    "tell my squad rotate fast, spike is A",
    "relay to team: everyone rotate C on Haven, they're all C",
    "tell them slow rotate through mid, don't sprint",
    "let my team know rotate off B, they faked us",
    "tell my teammates rotate now while their smokes are covering",
    "relay: three of us rotate A, two anchor B just in case",
    "tell my squad fake rotate then hold mid, let them waste util",
    "tell my team they rotated B, A is probably open",
    "relay: their whole squad rotated, site is unguarded",
    "let my teammates know they rotated off C, hit C now",
    "tell them their controller rotated early, they took the bait",
    "relay to teammates: they rotated A, don't execute B yet",
    "tell my squad they rotated through mid, they know we're B",
    "let my team know they rotated fast, they had info on our push",
    "tell them two of them rotated, three still on site",
    "relay: they didn't rotate, they're stacked B, go A",
    "tell my team their rotate is too slow, push now before they arrive",

    # =========================================================
    # RUSH / PUSH DIRECTIVE vs RUSH OBSERVATION TRAPS
    # =========================================================
    "tell them rush B this round, no slow play",
    "relay: rush A main all five, catch them off guard",
    "let my team know rush mid before they take control",
    "tell my squad rush B garage on Split, full commitment",
    "relay to team: rush through hookah into B on Bind, fast",
    "tell them rush CT immediately after the knife pop",
    "let my teammates know rush the site, we have full buy they don't",
    "tell my squad rush A long on Haven, they're all watching B",
    "relay: rush B site through the wall on Split with the sage wall break",
    "tell my team rush now while they're eco",
    "tell them they rushed B main, fall back and set up",
    "relay: they rushed A, three coming through main right now",
    "let my teammates know they're rushing mid, don't let them take it",
    "tell them full rush incoming on B, hold the entry",
    "relay to team: they rushed C on Haven with five, rotate immediately",
    "tell my squad they rushed through hookah on Bind, anchor B site",
    "let my team know they ran a full eco rush on A, hold your positions",
    "tell them they rushed A ramps on Split, need backup",
    "relay: they're rushing our spawn, watch the flank",
    "tell my team they rushed the site before our smokes even landed",

    # =========================================================
    # FLASH DIRECTIVE vs FLASH OBSERVATION TRAPS
    # =========================================================
    "tell them flash A main entry before we push",
    "relay: flash into B on my call, three two one",
    "let my team know flash the corner before I peek",
    "tell my squad flash heaven so I can take the angle",
    "relay to team: Breach, flash through the wall into CT",
    "tell them flash both angles on B site then we entry",
    "let my teammates know flash short before we swing long on Haven",
    "tell my squad Skye, pop your hawk into A and flash the Jett",
    "relay: flash the lurk position mid before he disappears",
    "tell my team flash site and I'll entry off the pop",
    "tell my team they flashed A, our entry is blind going in",
    "relay: they threw a flash over the wall, look away",
    "let my teammates know their Breach flashed through the screen, we're blind",
    "tell them they flashed mid and they're pushing, rotate back",
    "relay to team: Phoenix flashed the corner, he's going in",
    "tell my squad their KAY/O pop flashed the entry, everyone's blinded",
    "let my team know they flashed our retake angle, don't peek now",
    "tell them their Skye hawk flashed two of us, we're down",
    "relay: they're flashing B from outside, execute is on us",
    "tell my team their Yoru blindside already popped, we're clear",

    # =========================================================
    # ANCHOR DIRECTIVE vs ANCHOR OBSERVATION TRAPS
    # =========================================================
    "tell them anchor B, I'll lurk through mid",
    "relay: someone anchor A while the rest of us rotate C on Haven",
    "let my team know anchor the site and wait for retake info",
    "tell my squad anchor default plant position, we have utility left",
    "relay to team: anchor B heaven and wait for my call",
    "tell them anchor the spike and play for time",
    "let my teammates know anchor CT and don't over-rotate",
    "tell my squad anchor here, let them come to you",
    "relay: one anchor A, two rotate B, two go C on Haven",
    "tell my team anchor the corner and play passive, they're tilted",
    "tell my team their Killjoy is anchoring B alone, rush her",
    "relay: they left one anchoring A, four are all C on Haven",
    "let my teammates know their anchor player is sitting heaven, don't peek",
    "tell them their sentinel is anchoring the site with lockdown ready",
    "relay to team: their Chamber is anchoring B rafters with op",
    "tell my squad their anchor is really passive, we can take space early",
    "let my team know their anchor pulled back, site is soft",
    "tell them their Cypher is anchoring alone but has cam up",
    "relay: their anchor is deep in the back of B, don't check short",
    "tell my team their KJ anchored B all game, expect nanos on plant",

    # =========================================================
    # RETAKE DIRECTIVE vs RETAKE OBSERVATION TRAPS
    # =========================================================
    "tell them play retake, don't let them plant safe",
    "relay: retake A the second they plant, use everything",
    "let my team know retake B through CT, not through main",
    "tell my squad retake together, no solo peeking",
    "relay to team: retake now while they're spread out post-plant",
    "tell them retake through the smoke, the spike is at default",
    "let my teammates know retake A site from Catwalk side on Ascent",
    "tell my squad retake B site while only two of them are alive",
    "relay: retake with utility, they have a Viper Pit up",
    "tell my team retake on my call, set positions first",
    "tell my team they're retaking B right now, hold spike",
    "relay: they're retaking A with three players, watch the flank",
    "let my teammates know they're retaking, play for time on the defuse",
    "tell them the retake is coming from CT and Catwalk simultaneously",
    "relay to team: they're retaking B fast, plant was spotted",
    "tell my squad their retake has two players from mid, one from CT",
    "let my team know they're retaking and they have KJ lockdown saved",
    "tell them the retake is here, activate the nano on spike now",
    "relay: they're retaking with Sage rez still available, be careful",
    "tell my team their retake has three alive, spike is at default",

    # =========================================================
    # LURK DIRECTIVE vs LURK OBSERVATION TRAPS
    # =========================================================
    "tell them lurk through mid while we fake B",
    "relay: send someone to lurk CT while we pressure A",
    "let my team know lurk B link while we hit A",
    "tell my squad lurk the flank before they rotate",
    "relay to team: someone lurk through vent and cut their rotation",
    "tell them one player lurk mid, rest hit B together",
    "let my teammates know lurk Catwalk and get picks as they rotate",
    "tell my squad lurk spawn on Haven while we execute C",
    "relay: lurk sewers on Ascent while two of us take mid",
    "tell my team one person lurk, but not too long — spike in hand",
    "tell my team their Yoru is lurking through mid, watch the flank",
    "relay: they have a lurker on CT, careful rotating that way",
    "let my teammates know their lurk is using the teleporter on Bind",
    "tell them their Jett is lurking spawn, don't let her cut you off",
    "relay to team: their Reyna lurked through and she has souls, play safe",
    "tell my squad their lurker is mid and she has dash ready",
    "let my team know their lurk already cut rotation, don't go CT",
    "tell them the lurker got two of us, we're playing 3v5 now",
    "relay: their lurk flanked post-plant and killed our spike holders",
    "tell my team their lurker is really aggressive this half, watch your six",

    # =========================================================
    # PLANT DIRECTIVE vs PLANT OBSERVATION TRAPS
    # =========================================================
    "tell them plant for CT so we can hold the angle post-plant",
    "relay: plant default and then we spread out",
    "let my team know plant in the smoke, don't plant open",
    "tell my squad plant main side so we can hold the wall",
    "relay to team: plant quick, we only have 25 seconds",
    "tell them plant for heaven so they can't defuse from above",
    "let my teammates know plant spike and then scatter to three spots",
    "tell my squad plant safe behind the box, not in the open",
    "relay: plant the spike and I'll molly after, hold your angles",
    "tell my team plant behind generator on A Ascent, not in the open",
    "tell my team they're planting behind the boxes, B default",
    "relay: they planted at A main side, watch the angle",
    "let my teammates know spike is down, they planted for CT side",
    "tell them they planted and two are holding heaven, don't rush it",
    "relay to team: planted B, three of them alive still, wait for info",
    "tell my squad they planted at default and they have a pit going up",
    "let my team know they planted in the open, push the defuse",
    "tell them spike is planted heaven side A, Ascent — adjust crossfires",
    "relay: they planted behind generator and Viper is setting up pit",
    "tell my team the plant was behind orb and they're spreading",

    # =========================================================
    # DEFUSE DIRECTIVE vs DEFUSE OBSERVATION TRAPS
    # =========================================================
    "tell them full defuse, don't fake it, we don't have time",
    "relay: tap spike and bait the peek then full it",
    "let my team know ninja defuse through the smoke while they reload",
    "tell my squad defuse now while they're distracted by the kill",
    "relay to team: fake defuse to draw the Jett out then full it",
    "tell them tap spike to bait the peak from behind generator",
    "let my teammates know half defuse then let the molly expire then full it",
    "tell my squad defuse on my signal, I'm about to throw the flashpoint",
    "relay: stick the defuse, don't stop — we win on time",
    "tell my team go for the defuse while their Clove smokes are short",
    "tell my team they're defusing, someone kill them",
    "relay: last one is on the spike, defusing right now",
    "let my teammates know they're going for a fake defuse to bait your peek",
    "tell them they tapped the spike and retreated to draw us out",
    "relay to team: they're defusing through the pit, Viper can see them",
    "tell my squad he started defusing at default, shoot through the spike",
    "let my team know they're committing to full defuse, push the angle",
    "tell them they're defusing the spike, we have ten seconds left",
    "relay: he's ninja defusing from behind the box, we didn't see him",
    "tell my team they fake defused to bait a peek from our last player",

    # =========================================================
    # HOLD / PLAY PASSIVE DIRECTIVE vs OBSERVATION TRAPS
    # =========================================================
    "tell them hold this angle and don't peek",
    "relay: hold B heaven and don't over-rotate",
    "let my team know play passive, let them come to you",
    "tell my squad hold mid doors on Haven, do not let them through",
    "relay to team: hold default and wait for them to commit",
    "tell them don't peek, play passive this round",
    "let my teammates know hold the corner, don't swing it",
    "tell my squad hold B link and watch for the lurk",
    "relay: hold retake position until we're all ready",
    "tell my team hold the angle on A long, don't peek — they have op",
    "tell my team they're holding A heaven with op, don't push the angle",
    "relay: they're playing passive, holding every angle, don't peek blind",
    "let my teammates know they held B link all round, they knew we'd lurk",
    "tell them they're holding CT and not rotating, they're stacking",
    "relay to team: they held the corner and baited the entry, fall back",
    "tell my squad they played super passive this round, change the strat",
    "let my team know they held aggressive off-angles, play default",
    "tell them one player is holding heaven with a tourist, it's deadly",
    "relay: they held the B ramp rope all round, they had info",
    "tell my team they're holding every angle on Haven A simultaneously",

    # =========================================================
    # AGGRESSIVE PEEK DIRECTIVE vs OBSERVATION TRAPS
    # =========================================================
    "tell them peek A long, he might be low",
    "relay: shoulder peek that corner before you commit",
    "let my team know peek mid for a jiggle and gather info",
    "tell my squad swing A main, catch the off-angle holder",
    "relay to team: wide swing B short, don't let them set",
    "tell them dry peek the entry, burn their flash before we go",
    "let my teammates know swing the corner fast, he's one shot",
    "tell my squad peek window on Split from mid, get a pick",
    "relay: force a peek, we have the numbers and they're low utility",
    "tell my team aggressive peek long and punish the Jett if she peeks",
    "tell my team they peeked aggressive out of B main, hold the angle",
    "relay: their Neon peeked early and got two of our teammates",
    "let my teammates know they peaked aggressive out of CT on A",
    "tell them their Jett peeked A long with op, don't push that",
    "relay to team: they peeked mid aggressively and took control",
    "tell my squad they dry peeked our corner and punished the play",
    "let my team know their Raze peeked from boxes and has full HP",
    "tell them their peeking has been way too aggressive, they're gambling",
    "relay: they peeked through our smoke and got two before dying",
    "tell my team their aggressive peeks cost them — they're down two",

    # =========================================================
    # UTILITY DEPLOYMENT DIRECTIVE vs OBSERVATION TRAPS
    # =========================================================
    "tell them throw the Sova recon before we execute A",
    "relay: drone out mid before we push, get info",
    "let my team know KAY/O knife into B, strip their abilities",
    "tell my squad Gekko send Wingman first to stun the corner",
    "relay to team: Fade haunt into A site before the flash execute",
    "tell them drop the Killjoy lockdown and then rush them",
    "let my teammates know throw Tejo sticky into CT before entry",
    "tell my squad Breach fault line into site and we go immediately after",
    "relay: Skye send the dog into B main and then we push",
    "tell my team Deadlock throw grav net into the entry to slow the push",
    "tell my team their Sova darted A, they know our positions",
    "relay: their KAY/O threw the knife into B, abilities locked for eight seconds",
    "let my teammates know their Fade haunted and she has a trail on you",
    "tell them their Gekko wingman went plant, they're hands-free",
    "relay to team: their Breach faulted the entry, we're concussed",
    "tell my squad their Killjoy lockdown landed, get out of the radius now",
    "let my team know their Tejo sent missiles, take cover on site",
    "tell them their Skye hawk flashed into our site, she's following up",
    "relay: their Sova hunter's fury is being used now, hug the walls",
    "tell my team their Deadlock grav net is slowing our push into B",

    # =========================================================
    # ECONOMY DIRECTIVE vs ECONOMY OBSERVATION TRAPS
    # =========================================================
    "tell them save this round, we need a full buy next",
    "relay: everyone force buy, we have enough for Spectres",
    "let my team know eco round, don't spend over a thousand",
    "tell my squad drop me a rifle, I'm two hundred short",
    "relay to team: all buy Phantoms this round, we have the creds",
    "tell them eco and rush B, they won't expect a full five eco rush",
    "let my teammates know force buy this round, don't save",
    "tell my squad buy shields at least, don't run light armor",
    "relay: save your ult for next round, this is a throwaway",
    "tell my team anti-eco this round, don't overspend on rifles",
    "tell my team they're on eco, rush them before they get into position",
    "relay: they forced this round, expect cheap weapons and aggression",
    "let my teammates know they're saving, anti-eco round for us",
    "tell them their Jett bought an Op on a force, she has no util",
    "relay to team: they have rifles this round, don't rush blind",
    "tell my squad they're full buy, play it slow and safe",
    "let my team know they're forcing with Spectres, play off the angles",
    "tell them their economy is broken, third straight save next round too",
    "relay: they have two guns total, five of us full buy — rush and win",
    "tell my team they bought Judges on the force, don't play close range",

    # =========================================================
    # ENTRY DIRECTIVE vs ENTRY OBSERVATION TRAPS
    # =========================================================
    "tell them entry on my flash, I throw in three seconds",
    "relay: entry fragger go first, rest follow immediately",
    "let my team know entry through garage, second player trade immediately",
    "tell my squad I'm entrying on the hawk, jump in behind me",
    "relay to team: entry A main hard on the stun, don't hesitate",
    "tell them entry through smoke and someone trade me if I fall",
    "let my teammates know entry B heaven and then clear the default",
    "tell my squad you entry first and I'm right behind to trade",
    "relay: entry off the Tejo concuss, he's blinded for two-point-five seconds",
    "tell my team aggressive entry on the knife pop, go right now",
    "tell my team their entry fragger is going in, trade him out",
    "relay: their Neon entried and slid all the way through, two down",
    "let my teammates know their entry got traded, two alive each side",
    "tell them their entry died at the corner, push now while they reset",
    "relay to team: their entry took site and the rest are flooding in",
    "tell my squad their Jett entried off the flash and escaped with dash",
    "let my team know their Raze entried with a rocket — one of ours died",
    "tell them their entry died in one-vs-one, their team is hesitating",
    "relay: their entry went in without util — lucky, no trade",
    "tell my team their whole team followed the entry, B site lost",

    # =========================================================
    # SPLIT EXECUTE DIRECTIVE vs SPLIT OBSERVATION TRAPS
    # =========================================================
    "tell them split A, two from short and three from long on Haven",
    "relay: split execute B, garage and main simultaneously",
    "let my team know split the execute, half Catwalk half A main",
    "tell my squad split B on Split map, hell and B main at once",
    "relay to team: split A by going both sewers and ramps on Split",
    "tell them two hold B link and three split A from both angles",
    "let my teammates know split the push so they can't crossfire us",
    "tell my squad split C on Haven, one from C long one from C short",
    "relay: split execute means no one sits in a choke point together",
    "tell my team split the site so they can't play a single crossfire",
    "tell my team they split us — two hit A and three hit B simultaneously",
    "relay: they split us from garage and main, caught us out of position",
    "let my teammates know they split the execute, we couldn't cover both",
    "tell them they split A from both angles, we got pinched",
    "relay to team: their split execute worked perfectly, watch for it again",
    "tell my squad they split the push and we didn't rotate in time",
    "let my team know they're running a split to kill our crossfire setups",
    "tell them their split approach caught two of us in the mid angle",
    "relay: they split and our two anchors couldn't cover both entries",
    "tell my team their split execute won the site, change our defense",

    # =========================================================
    # POST-PLANT DIRECTIVE vs POST-PLANT OBSERVATION TRAPS
    # =========================================================
    "tell them play for time, spike is planted — don't fight in the open",
    "relay: post-plant, spread to three angles and cover the defuse",
    "let my team know post-plant hold, let them come to you",
    "tell my squad post-plant — play around the spike, not around kills",
    "relay to team: molly the spike every fifteen seconds to deny defuse",
    "tell them post-plant hold from heaven and hell simultaneously",
    "let my teammates know post-plant, use Viper's pit and sit inside",
    "tell my squad post-plant positions: one on height, one deep site",
    "relay: activate the KJ nanos on the spike now they're defusing",
    "tell my team post-plant play, use the Brimstone orbital if they rush",
    "tell my team they're playing post-plant, don't push into them",
    "relay: they're in post-plant and they molly'd the spike, wait it out",
    "let my teammates know they're playing post-plant with Viper pit on B",
    "tell them their post-plant setup has heaven and a deep site hold",
    "relay to team: they're post-plant with KJ nanos already set on spike",
    "tell my squad their post-plant kills both angles, we need utility",
    "let my team know they set up a crossfire in post-plant at A gen",
    "tell them their post-plant has one player running in to watch the tap",
    "relay: their post-plant is only two alive, retake should be doable",
    "tell my team their Clove died but she's still smoking post-plant, don't rush",

    # =========================================================
    # STACK DIRECTIVE vs STACK OBSERVATION TRAPS
    # =========================================================
    "tell them stack B, I have a read they're going B all round",
    "relay: stack A this round, put everyone on site early",
    "let my team know stack the site, it's a pistol round so rush the read",
    "tell my squad stack C on Haven, three there and two B",
    "relay to team: stack the site with three and two rotate ready",
    "tell them stack B early before their Sova darts it",
    "let my teammates know stack heaven with two players this round",
    "tell my squad stack mid and contest their Neon before she runs it",
    "relay: stack A short this round, their lurker is always mid",
    "tell my team stack the side they go every first round",
    "tell my team they stacked A with four, B is wide open — go",
    "relay: they stacked B again this round, fake B and hit A",
    "let my teammates know they stack C every pistol round on Haven",
    "tell them four stacked A and their Cypher is alone on B",
    "relay to team: they stacked mid and took control before we got there",
    "tell my squad they stack the site every eco round so anti-eco push",
    "let my team know they stacked A main and we walked into five",
    "tell them they stacked C heaven on Haven with their whole team",
    "relay: they stacked B garage and popped out on five of us",
    "tell my team they stack A every second round — mixed it up this time",

    # =========================================================
    # MOLLY / INCENDIARY DIRECTIVE vs OBSERVATION TRAPS
    # =========================================================
    "tell them molly the spike before they defuse",
    "relay: throw the Brimstone incendiary on the default plant after we spike it",
    "let my team know molly the defuse angle so they can't stand there",
    "tell my squad KJ activate the nano on the spike, they're going for it",
    "relay to team: Viper throw snakebite on the spike every cycle",
    "tell them molly the entry so they can't push right away",
    "let my teammates know drop molly on the chokepoint before they rush",
    "tell my squad Brimstone molly heaven and we'll push under it",
    "relay: throw the KJ nano on spike post-plant and then scatter",
    "tell my team molly B default the second we hear defuse start",
    "tell my team they molly'd the spike, wait for it to burn out",
    "relay: their Viper snakebite is on the spike, don't go in now",
    "let my teammates know they dropped a KJ nano on default, avoid it",
    "tell them their Brimstone incendiary is on the B plant area",
    "relay to team: they molly'd the defuse spot and they're watching angles",
    "tell my squad their KJ has nanos already pre-placed on B site",
    "let my team know they threw molly heaven to stop our descent",
    "tell them their Clove hit me with meddle decay, I'm low max HP",
    "relay: they molly'd the CT rotation path, don't cut through there",
    "tell my team their post-plant molly is on spike, we need a lineup",

    # =========================================================
    # SUPPRESS / KNIFE DIRECTIVE vs OBSERVATION TRAPS
    # =========================================================
    "tell them KAY/O knife into site to strip their abilities",
    "relay: throw the zero-point at the KJ lockdown device to suppress it",
    "let my team know knife into B main, their Killjoy has nanos set up",
    "tell my squad tejo drone into site and pop it to suppress before entry",
    "relay to team: KAY/O knife and we immediately entry, eight seconds no util",
    "tell them pop the Tejo drone and detonate it when you see two of them",
    "let my teammates know KAY/O flash first then knife second so they can't dodge",
    "tell my squad if the knife suppresses more than two, we execute",
    "relay: knife hits — all four of us entry, they're completely utility-locked",
    "tell my team knife before Breach rolls thunder so they can't dash out",
    "tell my team their KAY/O threw the knife, abilities locked eight seconds",
    "relay: Kayo knife suppressed three of us, they're executing now",
    "let my teammates know their Tejo drone popped — we're suppressed and revealed",
    "tell them their KAY/O null cmd is active, he can be revived if he dies",
    "relay to team: their knife hit B main, their team is executing on us",
    "tell my squad KAY/O is suppressed by a second knife — double knife this round",
    "let my team know their knife missed, abilities are still live — hold positions",
    "tell them two of us got suppressed by the Tejo drone — abilities offline",
    "relay: they used the knife to counter our Killjoy setup — lockdown cancelled",
    "tell my team their KAY/O knife hit our Jett — no dash for eight seconds",

    # =========================================================
    # WALL DIRECTIVE vs WALL OBSERVATION TRAPS
    # =========================================================
    "tell them Sage wall the ramp entry so they can't rush us",
    "relay: Viper toggle the wall so I can cross safely",
    "let my team know Iso put up the contingency wall, we can push through",
    "tell my squad Deadlock mesh the B entry to stop them rushing",
    "relay to team: Harbor wall the A main so we cross for free",
    "tell them Astra divide the site so they can't rotate through mid",
    "let my teammates know Sage wall the B main entry and we buy time",
    "tell my squad break the Sage wall, they're delaying with it",
    "relay: Viper drop the wall on CT rotation and toggle off when I cross",
    "tell my team Vyse shear the entry so the first person through gets trapped",
    "tell my team their Sage walled A ramps, we can't push without breaking it",
    "relay: Viper's Toxic Screen is up on mid, can't see through it",
    "let my teammates know their Iso wall went up, bullets won't penetrate it",
    "tell them their Deadlock mesh is blocking B entry, we need to break it",
    "relay to team: Astra's Cosmic Divide is up, audio is blocked through it",
    "tell my squad their Harbor wall is slowing everyone who crosses it",
    "let my team know their Sage wall is at full HP, break it before pushing",
    "tell them their Vyse shear trapped their own teammate by accident",
    "relay: their Viper wall is down, fuel depleted — push now",
    "tell my team their Sage wall broke, A ramps is open — go",

    # =========================================================
    # JETT-SPECIFIC DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them save Jett's dash for when she actually needs to escape",
    "relay: Jett smoke the CT corner and Updraft for the high angle",
    "let my team know Jett take the Op angle and dash if they swing",
    "tell my squad Jett ult and start beaming — she has Blade Storm up",
    "relay to team: Jett dash through the smoke and hold the back site angle",
    "tell them Jett updraft to the box and hold from above",
    "let my teammates know Jett ult means she keeps accuracy while moving",
    "tell my squad Jett activate Tailwind and reposition before they push",
    "relay: Jett ult and rush in with knives, kills recharge them",
    "tell my team Jett save the dash, don't burn it on a bad peek",
    "tell my team their Jett dashed away, she burned her escape tool",
    "relay: Jett popped Blade Storm, she's opping with knives now",
    "let my teammates know their Jett no dash — she's exposed, take the duel",
    "tell them Jett went up with updraft, she's holding from the box",
    "relay to team: Jett smoked the corner with Cloudburst before peeking",
    "tell my squad Jett ult is down, she died to the Op in contract",
    "let my team know their Jett has dash up again — she got a kill",
    "tell them their Jett used all her Cloudburst charges crossing long",
    "relay: their Jett ult ran out without a kill, now she's vulnerable",
    "tell my team Jett dash burned early, she won't escape this round",

    # =========================================================
    # REYNA-SPECIFIC DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them kill Reyna before she gets souls — she can't dismiss without kills",
    "relay: focus Reyna so she can't snowball into Empress",
    "let my team know shoot the Leer eye immediately so our entry isn't blinded",
    "tell my squad burst Reyna during Empress before she chains kills",
    "relay to team: Reyna no souls yet, she can't use Dismiss or Devour",
    "tell them kill Reyna first — she heals on kills, don't let her chain",
    "let my teammates know Reyna ult is only value if she's winning duels",
    "tell my squad force the duel on Reyna when she has no orbs available",
    "relay: Reyna Empress is active — play passive, she'll run herself out",
    "tell my team Reyna can't Dismiss, she didn't get a kill — push her",
    "tell my team Reyna Dismissed, she's intangible and repositioning",
    "relay: their Reyna Empress'd up, she got three in a row, careful",
    "let my teammates know Reyna Devoured, she healed back to full in seconds",
    "tell them their Reyna has souls, she'll Dismiss if you duel her",
    "relay to team: Reyna Empress is chain-killing, she's coming this way",
    "tell my squad their Reyna needs kills and isn't getting them, rush her",
    "let my team know Reyna Dismissed into the smoke and repositioned behind us",
    "tell them their Reyna went for the duel and missed it — she's low no souls",
    "relay: Reyna Empress expired, she ran out of kills to chain",
    "tell my team their Reyna threw the Leer through the wall at us",

    # =========================================================
    # KILLJOY DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them shoot the KJ turret before we push B main",
    "relay: activate the nano on the spike the second they start defusing",
    "let my team know place Alarmbot on the flank before the round starts",
    "tell my squad KJ lockdown the site to detain all of them",
    "relay to team: recall the turret and deploy it at a different angle",
    "tell them set up the KJ lockdown early and defend it",
    "let my teammates know KJ nano covers the default, don't walk through it",
    "tell my squad protect the lockdown device — if they break it, ult is wasted",
    "relay: KJ nano activate now, they're committing to the defuse",
    "tell my team KJ save lockdown for the retake, use it on their full team",
    "tell my team their KJ turret spotted you at B main, she knows you're there",
    "relay: KJ alarmbot triggered at CT flank, someone's lurking",
    "let my teammates know their KJ lockdown is going off, get out of B site",
    "tell them KJ lockdown device is down mid site — destroy it fast",
    "relay to team: their KJ nanoswarmed the spike, wait before you defuse",
    "tell my squad their KJ bot triggered, they know we're rotating",
    "let my team know KJ lockdown is active in 13 seconds — bail from site",
    "tell them their KJ had three nanos pre-placed on every plant spot",
    "relay: KJ turret is watching B main from back site angle",
    "tell my team their KJ recalled the turret — she repositioned it mid-round",

    # =========================================================
    # CYPHER DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them shoot Cypher's cam on B main before we push",
    "relay: watch for the tripwire in B lobby, walk slow to hear it",
    "let my team know Cypher marked someone with the dart, they have info",
    "tell my squad destroy Cypher's cage before it goes off",
    "relay to team: neural theft the body — we need full team positions",
    "tell them Cypher cam is watching A short, don't push that angle",
    "let my teammates know Cypher is running cam from safety, take the cam out",
    "tell my squad trip wire in B main entry — shoot it before rushing",
    "relay: Cypher ult the nearest corpse, we need to know where they all are",
    "tell my team take out the Cypher camera before she darts someone",
    "tell my team their Cypher darted you, they can track you through walls",
    "relay: Cypher tripwire triggered B main, they know someone's there",
    "let my teammates know Cypher cage activated, someone crossed the B lobby",
    "tell them their Cypher popped neural theft, they're seeing all our positions",
    "relay to team: Cypher's cam went down, she doesn't have vision anymore",
    "tell my squad their trip triggered in sewers, they know our rotation",
    "let my team know their Cypher darted our Fade, she's marked and tracked",
    "tell them Cypher's camera is at the garden position on A, not normal spot",
    "relay: Cypher tripwire in an off-angle spot by the bins on CT entry",
    "tell my team their Cypher cam is off for now, push the window",

    # =========================================================
    # CHAMBER DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them push Chamber's anchor and blow it up before he TPs to it",
    "relay: don't take the long angle — Chamber has Op and Tour de Force",
    "let my team know force Chamber off his TP anchor so he can't escape",
    "tell my squad destroy Chamber's teleport anchor before he peeks",
    "relay to team: rush Chamber before he can set up his angles with headhunter",
    "tell them bait the Chamber peek and when he TPs, push the TP spot",
    "let my teammates know Chamber slow field is on B default, don't stand in it",
    "tell my squad shoot the Chamber trap that's slowing people at B entry",
    "relay: Chamber TP anchor is behind the box, shoot it",
    "tell my team rush Chamber's position, he only has Headhunter left",
    "tell my team Chamber TPs back to anchor, don't chase the peek",
    "relay: Chamber Tour de Force is active, he's sniping from B rafters",
    "let my teammates know Chamber slow field spawned at his kill on site",
    "tell them Chamber's trap triggered near their CT rotation path",
    "relay to team: Chamber's anchor was destroyed, he's stuck in position",
    "tell my squad Chamber went for the peek and TPs back — don't push",
    "let my team know Chamber Trademark slowed two of our team at B entry",
    "tell them Chamber's Tour de Force has three bullets left",
    "relay: Chamber's anchor is in a weird spot behind him, near mid",
    "tell my team Chamber held the Op angle and his TP saved him — again",

    # =========================================================
    # SAGE DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them Sage wall the ramp to stop their entry push",
    "relay: Sage rez the entry fragger immediately, we need five",
    "let my team know Sage heal me first, I have the spike",
    "tell my squad Sage slow the entry with orbs, buy us two seconds",
    "relay to team: Sage wall mid so they can't split our defense",
    "tell them Sage wall the B entry and we buy fifty seconds easily",
    "let my teammates know save Sage rez for our Killjoy, she has lockdown",
    "tell my squad Sage boost us on the wall to get the high angle",
    "relay: Sage rez the spike carrier if they die planting",
    "tell my team Sage slow the A short entry before they flood through",
    "tell my team their Sage walled B entry to stall our push",
    "relay: Sage slow orb is on the A site entry, don't run through it",
    "let my teammates know their Sage rezed their entry fragger — five again",
    "tell them their Sage healed two teammates, both are back to full HP",
    "relay to team: Sage rez incoming, hold fire until they stand up",
    "tell my squad their Sage wall is at full HP on the ramp approach",
    "let my team know Sage boosted their KAY/O onto heaven with the wall",
    "tell them their Sage is out of heal, she used it two rounds straight",
    "relay: Sage ult is up on their team, play it safe on this round",
    "tell my team their Sage walled the mid short route off completely",

    # =========================================================
    # SOVA DIRECTIVE / OBSERVATION TRAPS
    # =========================================================
    "tell them Sova dart A site before we execute to get positions",
    "relay: Sova drone the site, tag someone before the execute",
    "let my team know Sova shock dart the default plant after we spike",
    "tell my squad Sova use Hunter's Fury along B main while they're pushing",
    "relay to team: Sova double shock the defuse spot if they go for it",
    "tell them Sova recon B and then we commit the execute on the info",
    "let my teammates know Sova drone out mid before we take it",
    "tell my squad Sova dart C on Haven to see if they're stacking",
    "relay: Sova fury through the wall across B main, beam all of them",
    "tell my team Sova shoot the dart before they rotate off B",
    "tell my team their Sova darted A, she knows our positions",
    "relay: Sova recon hit three of us — they know we're executing",
    "let my teammates know their drone is out, they're trying to get a tag",
    "tell them Sova Hunter's Fury is going through B main right now",
    "relay to team: Sova double shock set up on the default, don't stand there",
    "tell my squad their Sova dart is up and she has LOS on the site",
    "let my team know their Sova drone got shot down before tagging anyone",
    "tell them their recon bolt scanned two of us on A main",
    "relay: Sova fury hit someone mid who was peeking — one beam used",
    "tell my team their Sova doesn't have recon up, she used it for info",

    # =========================================================
    # SECOND-PERSON vs THIRD-PERSON SUBJECT TRAPS
    # "tell them X" (directive to team) vs "tell them Y happened" (obs)
    # where Y is grammatically close to X
    # =========================================================
    "tell them play the A site default this round",
    "tell them they played the A site default all last half",
    "relay: set up a one-way smoke on B main before they push",
    "relay: they had a one-way smoke on B main before we pushed",
    "let my team know hold the off-angle on short so they expect default",
    "let my team know they were holding an off-angle on short this whole round",
    "tell my squad swing the corner before the flash expires",
    "tell my squad they swung the corner before our flash expired",
    "relay to team: play off A heaven, don't stand on site open",
    "relay to team: they played off A heaven the whole round",
    "tell my team get aggressive early on mid, don't let them set",
    "tell my team they got aggressive early on mid and took control",
    "let my teammates know take the rope on B hell before they set heaven",
    "let my teammates know they took the rope to B heaven before our rotation",
    "tell my squad go long and bait the Op shot before committing",
    "tell my squad they went long and baited our Op shot before pushing",
    "relay: contest mid fast, don't let them free roam",
    "relay: they contested mid fast and we didn't have numbers for it",
    "tell my team fire at the smoke to widen it before walking in",
    "tell my team they fired at the smoke to widen the one-way angle",

    # =========================================================
    # ABILITY SPECIFIC OWNERSHIP TRAPS (our vs their)
    # =========================================================
    "tell them use Breach rolling thunder on the retake, stun them all",
    "relay: their Breach used rolling thunder, we're concussed — move",
    "let my team know pop KAY/O null cmd while we push B",
    "let my team know their KAY/O null cmd is active, revive him if down",
    "tell my squad activate Astra grav well on the spike, pull them off it",
    "tell my squad their Astra grav well pulled two of us off plant",
    "relay to team: Fade seize the chokepoint to tether them in place",
    "relay to team: their Fade seized our entry, she's tethered them",
    "tell my team drop Brimstone orbital on the B default post-plant",
    "tell my team their Brimstone orbital is incoming on B default",
    "let my teammates know use Harbor storm surge to CC their entry push",
    "let my teammates know their Harbor hit us with storm surge at B main",
    "tell my squad use Gekko Thrash to detain the clutch player",
    "tell my squad their Gekko Thrash detained our last player alive",
    "relay: Neon walls on the push to protect the crossing",
    "relay: their Neon put up Fast Lane walls to protect her crossing",
    "tell my team Viper toggle off the screen so we can cross safely",
    "tell my team their Viper toggled the Toxic Screen off — cross window is now",
    "let my teammates know Omen paranoia through the wall into their flank",
    "let my teammates know their Omen sent paranoia through the wall at us",

    # =========================================================
    # TIMING / CLOCK DIRECTIVE vs TIMING OBSERVATION TRAPS
    # =========================================================
    "tell them we have 30 seconds, execute now or we lose on time",
    "relay: they're burning the clock, don't let them stall",
    "let my team know push before 20 seconds left, plant ASAP",
    "tell my squad plant quick, we have 18 seconds on the clock",
    "relay to team: force it, time is out — rush B",
    "tell them we're running out of time, don't slow play this",
    "let my teammates know 25 seconds, this is our last window",
    "tell my squad don't wait for the perfect setup, we're late round",
    "relay: late round, play for a pick and then execute",
    "tell my team if we don't plant in 10 seconds, we lose the round",
    "tell my team they burned 40 seconds in a stall, we have time to retake",
    "relay: they're burning the clock deliberately on the A site entry",
    "let my teammates know they pushed late round with 20 seconds left",
    "tell them they stalled mid for 30 seconds before committing B",
    "relay to team: they planted with 15 seconds left on the clock",
    "tell my squad they're timing us out post-plant, don't rush",
    "let my team know they forced it with 8 seconds and caught us rotating",
    "tell them they waited for 45 seconds before executing",
    "relay: they played so slow we almost ran out of time on the A execute",
    "tell my team they timed the push perfectly with our smoke cycling out",

    # =========================================================
    # CLUTCH DIRECTIVE vs CLUTCH OBSERVATION TRAPS
    # =========================================================
    "tell them play for spike, not for kills in the clutch",
    "relay: one vs two, tap the defuse to bait their peek",
    "let my team know clutch player — go silent, no comms from dead",
    "tell my squad play for time, spike detonation wins this clutch",
    "relay to team: no comms from anyone, last player is clutching",
    "tell them fake defuse then punish whoever peeks",
    "let my teammates know last player alive, we go quiet now",
    "tell my squad tap, reset, look for the angle then stick it",
    "relay: one player left — no more callouts from dead players",
    "tell my team play crossfire with the last two alive on the defuse",
    "tell my team their clutch player is alone at A, last one",
    "relay: they're clutching a one-versus-three, give them time",
    "let my teammates know their last player played the clutch perfectly",
    "tell them their one alive is faking the defuse to bait your peek",
    "relay to team: their clutch player got two picks, it's a one-vs-one",
    "tell my squad their last player has op and is on the box",
    "let my team know their clutch attempt failed, push the defuse",
    "tell them their one alive used ult to try the clutch",
    "relay: their clutch player died to the spike detonation, we win",
    "tell my team their clutch player just won a 1v3, that was insane",
]
