"""Vocab pack: stress_stt_homophones (kind=relay, ~600 items).

CHARGE: STT-garble + homophones — the core FACT (count, location, ability, agent,
directive, ownership) must survive the garble. Every item is a STREAMER relay command
that arrived at the ASR layer with one or more of these distortions:

  HOMOPHONE / MISHEAR CLASSES (mix across every item):
  - cipher  ↔  cypher  (Cypher; both spellings the STT may produce)
  - kay o / k-a-y-o / kayo / k.a.y.o  (KAY/O — slash-name drops to many forms)
  - mix / miks / micks  (Miks — new controller agent, phonetically ambiguous)
  - gecko / gekko / geko  (Gekko — single vs double-k)
  - way lay / waylay / weigh lay  (Waylay — space/no-space, homophone)
  - tea joe / tejo / tay-ho  (Tejo — two-syllable Latin name, varied pronunciation)
  - breach / breech  (Breach — homophone with gun term)
  - skye / sky  (Skye — trivial drop)
  - viper / vipr  (quick speech drop)
  - jett / jet  (double-t drop)
  - chamber / chaymbur  (subtle vowel shift)
  - fade / fayed  (STT phonetic ambiguity)
  - iso / i-so / eye-so  (Iso — spacing artifacts)
  - sova / sofa / soave  (Sova — common STT drift to 'sofa')
  - astra / astre / aster  (Astra — final vowel drop)
  - neon / knee-on / nee-on  (Neon — prosodic stress shift)
  - clove / clov  (Clove — final vowel drop)
  - brimstone / brim stone (split word)
  - veto / vee-to  (Veto — vowel stress)
  - vyse / vice / vise  (Vyse — homophone with 'vice')
  - dead lock / deadlock  (Deadlock — split)
  - killjoy / kill joy  (split)
  - raze / raise / rays  (Raze — multiple homophones)
  - yoru / yoroo / yoru-u  (Yoru — vowel elongation)
  - reyna / raina / reina  (Reyna — phonetic variants)
  - phoenix / fenix / pheonix  (Phoenix — spelling/STT confusion)
  - harbor / harbour  (Harbor/Harbour — UK spelling STT)
  - dropped word: article, preposition, or filler word omitted
  - repeated word: word appears twice ('two two B', 'push push main')
  - transposed syllables: slight garble mid-word

Every item MUST still read as an unambiguous relay command with all key facts
intact (the garbled spelling doesn't change the meaning — that IS the stress test:
the parser must normalise the spelling and extract the fact correctly).

Kind: relay.
No wake-word prefix. Double-quoted strings only; apostrophes fine inside.
"""

ITEMS = [
    # =========================================================================
    # BLOCK 1 — CIPHER / CYPHER (Cypher agent name homophone)
    # =========================================================================
    "tell my team their cipher has a camera watching A main, don't walk past it",
    "let them know cipher tagged the Raze in B lobby, she's lit 60",
    "tell my teammates the enemy cypher stole neural theft off our Neon, he knows where everyone is",
    "warn the team cipher is pulling info from his cam on C link, one player CT side",
    "tell them cipher's tripwire is set in hookah, don't cross it",
    "let my team know the enemy cipher placed a cam behind generator, he can see our rotation",
    "tell my team to shoot the cypher cam on A site before we push",
    "the enemy cipher just used neural theft, he pulled a full reveal, everyone reposition",
    "tell my team their cypher has two trapwires in B main, walk through carefully or go around",
    "cipher broke his own trip by accident, B main is clear, go",
    "let them know the enemy cipher cam is down, we can push A now",
    "tell my team to kill the cypher before he can ult, our Neon is the only body",
    "their cypher is using a cage to cut mid, do not walk through the cage",
    "tell them cipher is anchoring B with cage and trip, do not go in alone",
    "warn my team the enemy cypher just tagged Miks with his dart, she is fully revealed",

    # =========================================================================
    # BLOCK 2 — KAY O / KAYO / K-A-Y-O (KAY/O name STT fragmentation)
    # =========================================================================
    "tell my team their kay o threw his knife on A site, all abilities suppressed eight seconds, push now",
    "let them know kayo is down in mid, someone run up and revive him before null expires",
    "tell my teammates our k-a-y-o used his flash on B entry, close your eyes and go",
    "warn the team the enemy kayo overloaded null command, stay spread so he can't pulse everyone",
    "tell them kayo's knife hit two on B site, abilities are gone, execute",
    "our kay o is downed near tree, run and revive him, he still has null up",
    "tell my team their kayo flashed mid with a pop flash, do not peek yet",
    "let them know the enemy k.a.y.o used his frag on B short, the fragment is still pulsing",
    "tell my teammates kayo's null command is about to come online, wait for his push before going B",
    "their kayo threw the zero point knife on our Sova, his recon bolt is suppressed",
    "tell them kayo has his ult up this round, push hard before he overloads",
    "our kayo revived at CT after null, he is back with thirty HP, cover him",
    "tell my team the enemy kay-o popped a fast flash around hookah corner, look away",
    "let them know kayo suppressed their Killjoy, her nanoswarms and turret are locked out eight seconds",
    "tell my team kayo is running null command into B, follow the suppression pulse",
    "warn them the enemy kayo threw the frag on spike, do not defuse until it stops pulsing",

    # =========================================================================
    # BLOCK 3 — MIX / MIKS / MICKS (Miks controller agent)
    # =========================================================================
    "tell my team their mix is setting up waveform smoke on A main, wait for it to clear",
    "let them know miks used her bassquake ult on B site, everyone is concussed, hold retake",
    "tell my teammates the enemy micks placed her m-pulse on hookah, don't push through the deafen",
    "warn the team our miks needs to re-smoke A main, her waveform is fading in three seconds",
    "tell them mix put a harmonize on our Jett, she is linked and Miks can hear her footsteps",
    "our miks has bassquake ready this round, wait for her to ult before we execute B",
    "tell my team the enemy miks is using waveform as a one-way on C, shoot under the smoke",
    "let them know micks deafened two with her m-pulse in link, push link now while they can't hear",
    "tell my teammates our mix smoked both heaven and CT, go through site now",
    "their miks has bassquake on two kills, be ready for the ult on our next push",
    "tell my team to kill miks first, without her waveform they have no smoke coverage on B",
    "let them know the enemy mix just remoked mid with waveform, mid is covered again",
    "our micks is out of waveform charges, push before she regenerates the smoke",
    "tell them miks hit her harmonize on three of us, she has full positional audio on our team",
    "tell my team the enemy micks is anchoring A with bassquake up, do not rush site",

    # =========================================================================
    # BLOCK 4 — GECKO / GEKKO / GEKO (Gekko initiator)
    # =========================================================================
    "tell my team their gecko sent dizzy into B main, do not look at it",
    "let them know the enemy gekko is piloting thrash into site, kill it before it detains someone",
    "tell my teammates our geko reclaimed his wingman, he can flash again",
    "warn the team the enemy gecko used mosh pit on spike, do not defuse yet",
    "tell them gekko's wingman is walking toward our Cypher, shoot it before it concusses him",
    "our gecko planted the spike with wingman while he covered B lobby, great plant",
    "tell my team the enemy geko threw dizzy into A site, two players blinded",
    "let them know gecko reclaimed dizzy from B lobby, he has his flash back in fifteen seconds",
    "tell my teammates the enemy gecko sent thrash toward CT, it will detain anyone it reaches",
    "their gekko has mosh pit saved for post-plant, watch the spike when you defuse",
    "tell my team to shoot gecko's wingman before it reaches us, it has eighty HP",
    "let them know our gecko is going to wingman-plant, cover him while he controls wingman",
    "tell them the enemy geko popped dizzy on heaven, the player up top is blinded",
    "warn my team gecko's thrash is piloting toward mid tower, kill it now",
    "tell my teammates the enemy gecko reclaimed thrash globule, his ult charge is on cooldown fifteen seconds",

    # =========================================================================
    # BLOCK 5 — WAY LAY / WAYLAY / WEIGH LAY (Waylay duelist)
    # =========================================================================
    "tell my team their way lay dashed into A heaven with lightspeed, she is holding from above",
    "let them know waylay placed her refract beacon at CT before peeking, she will recall if she loses the duel",
    "tell my teammates the enemy weigh lay used saturate on B entry, everyone is hindered",
    "warn the team waylay has convergent paths ready, do not cluster when she ults",
    "tell them their way-lay recalled to her beacon after taking damage, she is back at CT at full speed",
    "our waylay is dashing into A site with double lightspeed, cover her landing angle",
    "tell my team the enemy weigh lay slowed our Neon with saturate, Neon's slide is hampered",
    "let them know waylay's refract beacon is at T-stairs, shoot it to deny her escape",
    "tell my teammates the enemy way lay activated convergent paths, the hinder beam is expanding on B site",
    "their waylay has two lightspeed charges, she can dash twice to reach heaven in one play",
    "tell my team to shoot waylay's beacon on B link, without it she can't recall",
    "let them know our weigh lay slowed three defenders with saturate in site, push immediately",
    "tell them the enemy way lay recalled through mid while we were chasing, she is now safe at beacon",
    "warn my team waylay's convergent paths gave her a speed boost, she is running toward us on site",
    "tell my teammates their weigh lay has refract and full ult this round, play around her beacon placement",

    # =========================================================================
    # BLOCK 6 — TEJO / TEA JOE / TAY-HO (Tejo initiator)
    # =========================================================================
    "tell my team their tea joe is sending guided salvo missiles on A site, two rockets incoming",
    "let them know the enemy tejo detonated his stealth drone over B, everyone suppressed eight seconds",
    "tell my teammates our tay-ho is launching armageddon along B main, get out of the corridor",
    "warn the team the enemy tejo threw a special delivery on hookah, concuss on the corner for two seconds",
    "tell them tea joe already used his drone this round, no more suppression until next round",
    "our tejo has armageddon ready, wait for his airstrike on A then we push",
    "tell my team the enemy tay-ho launched both guided salvo missiles at spike, defuse between the ticks",
    "let them know tejo's stealth drone is flying into B site, kill it before he detonates",
    "tell my teammates the enemy tea joe used his second missile charge, no more salvo this round",
    "their tejo concussed two players on B main with special delivery, push through the concuss",
    "tell my team to shoot tejo's stealth drone, it only has forty-two HP",
    "let them know our tay-ho is calling armageddon along A long, move perpendicular before it hits",
    "tell them the enemy tejo suppressed our KAY/O with the drone detonation, kayo's knife is locked",
    "warn my team tejo has both salvo charges this round, expect double missiles on a post-plant",
    "tell my teammates the enemy tea joe bounced his special delivery over the wall into B lobby",

    # =========================================================================
    # BLOCK 7 — BREACH / BREECH (Breach initiator vs. gun term homophone)
    # =========================================================================
    "tell my team their breech is faulting B main, stun incoming on the entry",
    "let them know breach rolled his thunder through mid, three players concussed six seconds",
    "tell my teammates the enemy breech flashed through the wall into A heaven, look away",
    "warn the team breach is pushing with aftershock on B window, do not hold the window",
    "tell them their breech has rolling thunder up this round, do not stack B main",
    "our breach faulted B lobby, all three defenders are concussed, rush in",
    "tell my team the enemy breech used a hard flash on A main, it came through the barrier wall",
    "let them know breach is stunting through the garage wall on Haven, defenders are dazed",
    "tell my teammates the enemy breech aftershocked our Killjoy off spike, she had to move",
    "their breech used rolling thunder to knock up A site defenders, push before they recover",
    "tell my team breach has two flashpoints left, he can double-flash C long",
    "let them know our breech faulted A heaven and the ramp, two defenders dazed",
    "tell them the enemy breech used his fault line on the push, go in immediately",
    "warn my team breech has his ult up, do not cluster on B lobby",
    "tell my teammates the enemy breech soft-flashed through the A cubby wall, one player blinded",

    # =========================================================================
    # BLOCK 8 — SOVA / SOFA (Sova initiator — STT drift)
    # =========================================================================
    "tell my team their sofa's recon bolt scanned two on A site, one is heaven one is default",
    "let them know sova's owl drone is flying mid, kill the drone before he marks anyone",
    "tell my teammates the enemy sofa has hunter's fury up, do not stand in a line",
    "warn the team sova fired a shock bolt at the spike plant point, two bounces",
    "tell them their sofa already used his drone, mid is safe to cross for thirty seconds",
    "our sova's recon bolt hit three, all three are on B site, rotate now",
    "tell my team the enemy sofa shot a marking dart at our Viper, she is fully tagged",
    "let them know sova's fury has two beams left, spread out so one beam can't hit two of us",
    "tell my teammates the enemy sofa is lining up a shock on spike, defuse from the left side",
    "their sofa shot a two-bounce full-charge recon bolt through the wall, it scanned our whole team",
    "tell my team to shoot sova's recon arrow, it only has one HP and the next scan is in one second",
    "let them know our sofa marked the Jett with the drone dart, she is revealed for the team",
    "tell them the enemy sova lined up a double shock on spike, wait for both to explode before defusing",
    "warn my team sofa has three beams on hunter's fury, do not stack the retake corridor",
    "tell my teammates the enemy sofa's dart missed, we are not marked, push B now",

    # =========================================================================
    # BLOCK 9 — RAZE / RAISE / RAYS (Raze duelist homophones)
    # =========================================================================
    "tell my team their raise is boosting into B with blast pack, track where she lands",
    "let them know rays fired showstopper into B main, the rocket is flying, scatter",
    "tell my teammates the enemy raze dropped a paint shells cluster on A default, sub-munitions everywhere",
    "warn the team their raise is launching boom bot down B long, shoot the bot",
    "tell them the enemy rays used both blast packs to reach heaven, she is holding from above",
    "our raze has showstopper up this round, she will rocket the site for us on execute",
    "tell my team the enemy raise cluster naded A main, four sub-grenades hit the corner",
    "let them know rays's boom bot locked onto our Sage in B lobby, it is chasing her",
    "tell my teammates the enemy raze rocket is in the air on C, everyone scatter now",
    "their raise fired her showstopper into the smoke, they are clearing B blind",
    "tell my team to shoot raze's boom bot in B link, it will lock on and chase someone",
    "let them know our rays boosted over C wall with double blast packs, she is on top of the box",
    "tell them the enemy raze has paint shells recharged after two kills, cluster nade incoming",
    "warn my team raise's rocket went into mid smoke, do not push mid yet",
    "tell my teammates the enemy rays has showstopper on six points, she is one orb from ulting",

    # =========================================================================
    # BLOCK 10 — REYNA / RAINA / REINA (Reyna duelist phonetic variants)
    # =========================================================================
    "tell my team the enemy reina dismissed after the kill, she is intangible, do not shoot",
    "let them know raina hit empress this round and she has chain healed twice already",
    "tell my teammates the enemy reyna threw a leer through the wall, do not look at the eye",
    "warn the team their reina is in empress and she has no soul orbs yet, push her now",
    "tell them reyna needs kills to use her devour, she is at low HP without orbs",
    "the enemy raina hit empress with four kills, she is unstoppable right now, fall back",
    "tell my team to shoot reyna's leer eye on A main before it nearsights everyone",
    "let them know the enemy reina dismissed toward CT, she is repositioning through the wall",
    "tell my teammates reyna's empress has expired, she is vulnerable now without the kill chain",
    "their raina has devour up and she just got a kill, she is healing to over a hundred HP",
    "tell my team reyna has no orbs this round, she cannot dismiss or devour without kills",
    "let them know the enemy reina is holding A with her leer pre-aimed through the cubby wall",
    "tell them reyna is in empress, she will dismiss if you get a hit so don't peek one at a time",
    "warn my team the enemy raina fired her leer through the garage door on Haven",
    "tell my teammates their reyna needs one more kill for soul orbs and she will be unkillable",

    # =========================================================================
    # BLOCK 11 — ISO / I-SO / EYE-SO (Iso duelist spacing artifacts)
    # =========================================================================
    "tell my team their i-so threw a kill contract at our Raze, she is in the arena",
    "let them know eye-so has his contingency wall up in A main, bullets are blocked",
    "tell my teammates the enemy iso undercut our Sage, she is suppressed and fragile four seconds",
    "warn the team their i so has kill contract ready, do not peek him alone",
    "tell them iso won the one-on-one contract, he came back at a hundred HP",
    "the enemy eye-so put up his contingency wall to block B entry, do not try to wallbang",
    "tell my team iso's double tap shield is active, he absorbed one burst already",
    "let them know our i-so suppressed and fragilised two players with undercut through the wall",
    "tell my teammates the enemy iso lost his kill contract, Neon won the duel, he is dead",
    "their i so put a contingency wall in mid to cut off our rotation to B",
    "tell my team iso has kill contract on seven points, he needs one more kill to ult",
    "let them know the enemy eye-so activated double tap after the kill, shoot the orb before he absorbs it",
    "tell them iso undercut bounced through the wall into our Killjoy, her abilities are suppressed",
    "warn my team their i-so tried to contract our KAY/O but kayo won and returned at full HP",
    "tell my teammates the enemy iso walls are bullet-blocking, use grenades not rifles on them",

    # =========================================================================
    # BLOCK 12 — SKYE / SKY (Skye initiator trivial drop)
    # =========================================================================
    "tell my team their sky is sending seekers after us, three orbs homing in right now",
    "let them know skye released her tiger into B lobby, concuss incoming on the corner",
    "tell my teammates the enemy sky sent a hawk to flash A heaven, look away when it pops",
    "warn the team skye has two hawk charges this round, she can flash B main twice",
    "tell them their sky dog is concussing our Jett in B short, go help her",
    "our skye used both guiding lights on A main, the defenders are blind twice over",
    "tell my team the enemy sky healed their Reyna to full HP in CT corridor",
    "let them know skye's seekers hit all three on B site, everyone is nearsighted",
    "tell my teammates the enemy sky released the tiger and it detonated on our Viper",
    "their sky has seekers up this round, spread out so the three seekers don't hit our whole team",
    "tell my team to shoot skye's tiger before it leaps, it only has eighty HP",
    "let them know the enemy sky auto-flashed A main at the end of her hawk's path",
    "tell them our skye healed our Sova back to full during the retake, both are alive",
    "warn my team the enemy sky popped the hawk flash manually around short corner, one player blinded",
    "tell my teammates skye used her seeker ult and all three targets are on A site",

    # =========================================================================
    # BLOCK 13 — VIPER / VIPR (Viper controller rapid-speech drop)
    # =========================================================================
    "tell my team their vipr toggled the toxic screen down to let her team cross, go now",
    "let them know viper's pit is up on B site, do not rush into the cloud",
    "tell my teammates the enemy vipr applied a snakebite on spike, wait for the vulnerable window before defusing",
    "warn the team viper is low on fuel, her wall will drop in two seconds, push the crossing",
    "tell them their vipr set up a post-plant pit on A and planted in the cloud",
    "our viper toggled her poison cloud on CT to block the rotation, rotate through mid instead",
    "tell my team the enemy vipr's toxic screen is the only split on B, if you kill her it goes down in two seconds",
    "let them know viper's pit expired because she left the cloud, she is outside, push B now",
    "tell my teammates the enemy vipr threw snakebite under hookah, three players are vulnerable",
    "their vipr has the pit ready for post-plant on A, we will need two players to clear the cloud",
    "tell my team viper's fuel is regenerating, she will toggle the wall back on in fifteen seconds",
    "let them know the enemy vipr is anchoring B inside her own pit, Viper can see our silhouettes",
    "tell them our viper placed her poison cloud to one-way short, you can see through from our side",
    "warn my team vipr threw a snakebite vulnerable window, push her while she heals through it",
    "tell my teammates the enemy viper wall is the only split on this site, destroying it opens the rotation",

    # =========================================================================
    # BLOCK 14 — VYSE / VICE / VISE (Vyse sentinel homophones)
    # =========================================================================
    "tell my team their vice used steel garden on B site, all primary weapons are jammed eight seconds",
    "let them know vise activated her arc rose flash on A main, look away",
    "tell my teammates the enemy vyse popped her shear trap, one defender is cut off behind the indestructible wall",
    "warn the team their vice has steel garden up, do not rush site or your rifles are useless",
    "tell them the enemy vise put two razorvines near spike, walking to defuse will shred you",
    "our vyse flashed A heaven with arc rose, the defender up top is blinded",
    "tell my team the enemy vice triggered shear in B main, our entry fragger is isolated",
    "let them know vise activated razorvine on the B plant, walking through will slow and damage you",
    "tell my teammates the enemy vyse deactivated her razorvine to let her team push through safely",
    "their vice has steel garden on seven points, she needs one more to jam all rifles",
    "tell my team to shoot vyse's arc rose before she pops it, it is on the left wall",
    "let them know the enemy vise triggered shear trap under the bridge on Pearl",
    "tell them our vyse planted two razorvines near C default before the round and they are still active",
    "warn my team vice's steel garden is making the site push a pistols-only fight for eight seconds",
    "tell my teammates the enemy vise used arc rose as a reactionary flash when we pushed short",

    # =========================================================================
    # BLOCK 15 — DROPPED WORDS (missing article, preposition, or filler)
    # =========================================================================
    "tell team two enemies B long both no armor",
    "let know their Killjoy ult going down site, push after detain",
    "tell my guys one shot CT no armor pick him",
    "warn team their Viper pit is up A, do not enter cloud",
    "tell them three pushing main all rifles go rotate B",
    "tell my team Sage rez target is our Jett, hold entry until she comes back",
    "let know kayo knife hit two B site, abilities suppressed, execute",
    "tell teammates one planting B default, two covering CT rotate now",
    "warn everyone Killjoy lockdown is B five seconds, protect device",
    "tell them enemy Neon running overdrive into site beam active now",
    "let my team know Fade nightfall hit all five, everyone is trailed push the trails",
    "tell teammates our Clove has not dead yet up, let her ult if she dies this round",
    "warn team enemy Jett has blade storm, do not peek sightlines alone",
    "tell my guys enemy Chamber touring de force one shot anybody body",
    "let team know their Deadlock annihilation trapped our Phoenix in a cocoon, break it",

    # =========================================================================
    # BLOCK 16 — REPEATED WORDS (stuttered / doubled words from STT)
    # =========================================================================
    "tell my team two two enemies are on B main right now pushing fast",
    "let them know one one player is left alive in the round, he is defusing",
    "tell my teammates push push mid with the smoke up before it fades",
    "warn the team their their Jett has no dash used up, she cannot escape",
    "tell them rotate rotate B now, all enemies committed A",
    "our Sova recon hit hit three players on B site, full team is there",
    "tell my team the enemy Sage wall wall is blocking A ramp, break it before push",
    "let them know kayo knife knife suppressed two players on site, push push now",
    "tell my teammates the enemy Reyna dismissed dismissed into CT, she used it twice somehow, track her",
    "warn the team their their Viper pit is up and she is inside inside the cloud",
    "tell them the enemy Raze boosted boosted using both blast packs to reach A heaven",
    "our Breach faulted faulted B main, two defenders concussed, go go",
    "tell my team one one shot enemy at hookah, finish him before he resets",
    "let them know their Killjoy set set two nanoswarms on the default plant spot",
    "tell my teammates push push A on the smoke timing, Miks is re-smoking now now",
    "warn the team the enemy Skye tiger tiger concussed our entry, trade immediately",

    # =========================================================================
    # BLOCK 17 — PHOENIX / FENIX / PHEONIX (Phoenix duelist STT confusion)
    # =========================================================================
    "tell my team their fenix activated run it back, kill him before the timer ends",
    "let them know pheonix curved a flash around the corner on A main, look away",
    "tell my teammates the enemy phoenix is healing in his blaze wall, push him out of it",
    "warn the team their fenix is using hot hands to zone the plant spot",
    "tell them phoenix ult down, he died in run it back without killing anyone",
    "the enemy pheonix ran it back after dying on B site, he is back at full HP at the marker",
    "tell my team to kill phoenix before his timer expires or he gets a free respawn",
    "let them know the enemy fenix curved his curveball left around mid tower, players are blind",
    "tell my teammates phoenix is standing in his own fire wall to regen HP",
    "their pheonix has run it back ready, be prepared for a second push after he dies",
    "tell my team phoenix only has one flash left, both curveballs have not been recharged",
    "let them know the enemy fenix flashed B main from safety through the wall setup",
    "tell them the enemy phoenix put hot hands directly on spike, wait for the zone to clear",
    "warn my team their fenix set up a run it back marker at CT before peeking A long",
    "tell my teammates the enemy phoenix used run it back and got one kill in the window",

    # =========================================================================
    # BLOCK 18 — YORU / YOROO / YORU-U (Yoru duelist vowel elongation)
    # =========================================================================
    "tell my team the enemy yoroo sent a fakeout clone toward A, it was decoy footsteps",
    "let them know yoru-u teleported onto B site from the rift tether on CT",
    "tell my teammates the enemy yoroo is in dimensional drift and is invisible, do not shoot at sounds",
    "warn the team yoru faked the teleport audio cue, he did not actually move",
    "tell them their yoru-u blindsided our Viper around the corner in B lobby",
    "the enemy yoroo placed a gatecrash tether on A site, he will teleport in or fake it",
    "tell my team to shoot yoru's tether on B short before he can teleport through it",
    "let them know the enemy yoru-u is coming out of dimensional drift, expect a flash on exit",
    "tell my teammates yoru sent clone footsteps toward B while he is actually flanking CT",
    "their yoroo has dimensional drift this round, he will scout our positions invisibly",
    "tell my team yoru flashed with blindside, it bounced once before popping, one player blinded",
    "let them know the enemy yoru-u placed the rift tether inside the smoke so we cannot see it",
    "tell them yoru's clone got shot and it exploded into a blind, two of our guys were facing it",
    "warn my team their yoroo can fake the TP audio to bait us into rotating early",
    "tell my teammates the enemy yoru-u used dimensional drift to scout our entire defensive setup",

    # =========================================================================
    # BLOCK 19 — OMEN / ASTRA / HARBOR / CLOVE (controller phonetic variants)
    # =========================================================================
    "tell my team the enemy omen is stepping into his own smoke with shrouded step on B",
    "let them know their astre is placing stars globally, she has a stun and a gravity well pre-planted",
    "tell my teammates the enemy harbour put a cove shield on spike, the bullets cannot pass through it",
    "warn the team their omen threw paranoia through the wall, everyone is nearsighted two seconds",
    "tell them the enemy astra pulled our entry with gravity well, he is vulnerable from the suction",
    "our clov smoked both from grave after she died, smokes are only up six seconds, push fast",
    "tell my team the enemy omen ulted from mid to appear behind us on A site",
    "let them know astra dissipated her star on B to fake a smoke, watch for the pivot",
    "tell my teammates the enemy harbour toggled cove shield to block our shots during the plant",
    "their astre has cosmic divide ready this round, she will wall-split A and we will not hear each other",
    "tell my team the enemy clov used not dead yet and revived on A, she needs one kill to stay alive",
    "let them know omen placed a one-way dark cover on B main, he can see our legs under the smoke",
    "tell them their astra nova pulsed B lobby, all three players rushing are concussed three seconds",
    "warn my team harbour reckoning is coming through A link, the surge is moving fast, scatter",
    "tell my teammates the enemy clov meddle decayed our Sage to ten max HP",

    # =========================================================================
    # BLOCK 20 — CHAMBER / KILLJOY / DEADLOCK / SAGE (sentinel phonetic variants)
    # =========================================================================
    "tell my team their chaymbur is holding A long with tour de force, do not peek the sightline",
    "let them know kill joy lockdown is out on B, protect the device before they destroy it",
    "tell my teammates the enemy dead lock fired annihilation and cocooned our Breach",
    "warn the team their chaymbur teleported back to his anchor after we pressured him",
    "tell them killjoy popped her nanoswarm on spike, it is doing forty-five damage per second",
    "the enemy dead lock's grav net hit two on A ramp, they are pinned and crouching",
    "tell my team chamber's headhunter pistol can one-tap our heads even through heavy armor",
    "let them know kill joy's alarmbot tagged our Jett in B lobby, she is vulnerable now",
    "tell my teammates the enemy deadlock barrier mesh is blocking B link, break the center orb first",
    "their chaymbur placed his tour de force sniper on A corner and got two picks already",
    "tell my team kill joy has lockdown on nine points, she is about to ult next round",
    "let them know the enemy deadlock sonic sensor is watching B main, any noise sets it off",
    "tell them sage is walling off A ramp to buy our team time, do not push the wall",
    "warn my team chaymbur trademark trap is on mid entrance, do not walk through it",
    "tell my teammates the enemy killjoy recalled her alarmbot, B flank is no longer watched",

    # =========================================================================
    # BLOCK 21 — NEON / KNEE-ON (Neon duelist prosodic shift)
    # =========================================================================
    "tell my team the enemy knee-on is sprinting into B with high gear, she will slide in on the corner",
    "let them know neon's relay bolt bounced twice and stunned two defenders on site",
    "tell my teammates the enemy knee-on activated overdrive and the lightning beam is sweeping B",
    "warn the team their neon put down two fast lane walls to cross A long safely",
    "tell them the enemy knee-on's slide reset because she got a kill during overdrive",
    "our neon is running overdrive into site, the beam is accurate while she sprints",
    "tell my team the enemy knee-on's high gear expired, she cannot sprint for two kills",
    "let them know neon's relay bolt concuss is three seconds long, push through it now",
    "tell my teammates the enemy knee-on slid into A heaven and is holding from the elevated angle",
    "their neon has overdrive on seven points, she needs one more to activate the lightning beam",
    "tell my team to kill neon before her slide resets from a kill, she is at low HP",
    "let them know the enemy knee-on sprinted through our smoke without stopping, she used speed to cross",
    "tell them our neon's fast lane walls are up on A long, cross in the covered corridor now",
    "warn my team the enemy knee-on's overdrive beam is hard to dodge at close range",
    "tell my teammates neon activated high gear, she is significantly faster than any of us right now",

    # =========================================================================
    # BLOCK 22 — VETO / VEE-TO (Veto sentinel)
    # =========================================================================
    "tell my team the enemy vee-to activated evolution, he is immune to all our flashes and stuns now",
    "let them know veto intercepted our Raze's boom bot with his interceptor device",
    "tell my teammates the enemy vee-to threw a chokehold trap in B main, it will tether and deafen anyone who steps in",
    "warn the team their veto placed crosscut vortex anchors at both ends of CT link",
    "tell them vee-to evolved and cannot be suppressed by kayo's knife or tejo's drone for the whole round",
    "our veto interceptor blocked the enemy Killjoy's nanoswarm before it activated",
    "tell my team the enemy vee-to teleported back to his crosscut vortex after peeking short",
    "let them know veto's evolution makes him immune to Fade's prowlers and Skye's seekers",
    "tell my teammates the enemy vee-to has evolution on seven points, one more kill and he ults",
    "their veto used chokehold in hookah, anyone entering is tethered and decayed",
    "tell my team to destroy veto's interceptor device, it has only twenty HP and will block our utility",
    "let them know the enemy vee-to teleported through crosscut into our flank, he came from behind",
    "tell them veto's chokehold trap went off on our Sage in B lobby, she cannot hear footsteps",
    "warn my team the enemy vee-to's evolution stim and regen means he fights better under pressure",
    "tell my teammates veto's interceptor is active, do not throw any bouncing utility near it",

    # =========================================================================
    # BLOCK 23 — JETT / JET (Jett duelist double-t drop)
    # =========================================================================
    "tell my team the enemy jet dashed away after the trade, she has no more tailwind this round",
    "let them know jett has blade storm up and she is holding A long with the knives",
    "tell my teammates the enemy jet updrafted to the box on A site and is holding from elevation",
    "warn the team their jett smoked across with cloudburst to cross B long safely",
    "tell them the enemy jet has no dash, her tailwind is used up, you can peek her safely now",
    "our jett used blade storm to clear B smoke and got two kills off the knives",
    "tell my team the enemy jet is holding with an operator and will dash to escape after the shot",
    "let them know jett used her updraft twice to reach the cubby on A heaven",
    "tell my teammates the enemy jet's dash is recharged after two kills, she can escape again",
    "their jett is opping from mid with blade storm knives as the weapon, peek wide not narrow",
    "tell my team jet has no cloud left, she cannot self-smoke to cross A long without controller help",
    "let them know the enemy jett updrafted into the air over B site and is holding the elevated angle",
    "tell them our jet is dashing aggressively into B, cover her entry before she gets traded",
    "warn my team the enemy jet dropped from heaven onto two of our players, watch the high ground",
    "tell my teammates their jett has save dash called out, she is preserving tailwind for an emergency",

    # =========================================================================
    # BLOCK 24 — FADE / FAYED (Fade initiator STT phonetic ambiguity)
    # =========================================================================
    "tell my team the enemy fayed's nightfall hit all five of us, everyone is trailed for twelve seconds",
    "let them know fade sent prowlers on the terror trails, they are locked on and cannot miss",
    "tell my teammates the enemy fayed threw her haunt eye on A site, shoot it before it reveals",
    "warn the team their fade seized our Neon on B, she is tethered and decayed for four seconds",
    "tell them the enemy fayed's nightfall hit three, fade knows how many we have on B",
    "our fade haunted A main and two players are revealed with active terror trails",
    "tell my team the enemy fayed launched a prowler in B link and it is tracking our Sage",
    "let them know fade's seize tether is blocking B lobby, do not enter the zone",
    "tell my teammates the enemy fayed uses nightfall every round, save your flashes to cancel the reveal",
    "their fade sent two prowlers chasing both trailed players in the corridor",
    "tell my team to shoot the fade haunt eye on CT, it has one HP, destroy it quickly",
    "let them know the enemy fayed decayed our Breach to ten max HP with seize",
    "tell them fade has nightfall ready this round, spread out so not all five get trailed at once",
    "warn my team the enemy fayed paired nightfall with prowlers, the prowlers home in perfectly on trails",
    "tell my teammates the enemy fade used haunt on a lineup so the eye revealed A back site",

    # =========================================================================
    # BLOCK 25 — MIXED AGENTS + TRANSPOSED SYLLABLES (subtle mid-word garble)
    # =========================================================================
    "tell my team their kayjo threw a zero point knife on B, all abilities suppressed",
    "let them know the enemy gekkoh sent dizzy into heaven, the plasma blind is flying",
    "tell my teammates our waylaay recalled her refract beacon after losing the duel in CT",
    "warn the team the enemy tey-jo launched guided salvo at spike, two missiles incoming",
    "tell them the enemy killjory's lockdown device is on B site, protect it or destroy it",
    "our skay released two guiding lights on A main, both flashed the entry angle",
    "tell my team the enemy kyo used null command mid and is revivable if downed",
    "let them know the enemy gekkow wingman is planting the spike on A default while he covers B lobby",
    "tell my teammates the enemy tepho threw a special delivery over the wall on a one-bounce arc",
    "warn the team their reza has showstopper up this round, one direct hit kills on impact",
    "tell them the enemy soyva's recon bolt scanned three on B site, push A",
    "let my team know the enemy waylaay hindered two of us with saturate on site entry",
    "tell them our kayoh is overloading null command into A, follow his suppression",
    "warn the team the enemy breech used rolling thunder into the execute, six seconds of concuss",
    "tell my teammates the enemy vyze triggered shear trap and isolated our Breach behind the wall",

    # =========================================================================
    # BLOCK 26 — ABILITY-NAME HOMOPHONES AND STT VARIANTS
    # =========================================================================
    "tell my team the enemy Jett's tale wind dash is up after her last two kills",
    "let them know the enemy Neon's relay bolt stun bounced twice and hit our sage in B",
    "tell my teammates the enemy KAY/O's null command keeps suppressing us every three seconds",
    "warn the team the enemy Viper's snake bite puddle is still on spike, wait it out before defusing",
    "tell them the enemy Sova's hunters fury has three charges, do not stack the retake hallway",
    "our Gekko reclaimed his dizzy globule, he has his flash available again in fifteen seconds",
    "tell my team the enemy Chamber's tour duh force sniper gives slow zones on every kill",
    "let them know the enemy Fade's night fall wave hit all three on B, trailed for twelve seconds",
    "tell my teammates the enemy KAY/O's flash drive grenade is a right-click pop flash, fast cook",
    "their Raze's paint shells cluster hit four sub-nades in A cubby, massive splash damage",
    "tell my team the enemy Deadlock's grav net hit two and they are crouching and pinned",
    "let them know the enemy Harbor's high tied wall is blocking B entry, slow if you cross",
    "tell them the enemy Killjoy's nano swarm is planted near default, it is invisible until popped",
    "warn my team the enemy Omen's dark cove smoke is a one-way, he can see us under it",
    "tell my teammates the enemy Breach's rolling thunder knocked our whole team airborne on A ramp",

    # =========================================================================
    # BLOCK 27 — OWNERSHIP TRAPS THROUGH STT GARBLE
    # =========================================================================
    "tell them our their Killjoy ult is going off on B, our side, protect it",
    "let my team know the enemies Viper pit is up not our Viper's pit, do not walk in",
    "tell my teammates our our Sage is rezzing our Jett at B, hold the line while she channels",
    "warn the team their Sova recon hit their our guys, he tagged us on the rotate",
    "tell them it is our KAY/O who is downed not theirs, revive our kayo at CT",
    "let my team know their Gekko wingman is defusing our spike not planting, stop it",
    "tell my teammates it was our Raze not their Raze who boosted into heaven, she is on our side",
    "warn the team their their Clove smoked from the grave, enemy smokes not ours, wait them out",
    "tell them our Cypher cam is still up not destroyed, cipher can still pull info",
    "let my team know the Viper pit on B is the enemy Viper's pit, do not go in",
    "tell my teammates our Breach fault line is about to go off on A main, turn away",
    "warn the team it is their Killjoy not ours running lockdown on B this round",
    "tell them our Omen stepped into his smoke not the enemy Omen, our player is in there",
    "let my team know their Sage rez target is their dead Jett not our Jett, do not push yet",
    "tell my teammates our Fade haunted A site, our haunt eye, shoot it if you see it blinking",

    # =========================================================================
    # BLOCK 28 — HEAVY GARBLE: MULTIPLE DISTORTIONS IN ONE ITEM
    # =========================================================================
    "tell my team the enemy kay o threw his knife on site and geko gecko sent dizzy at the same time, all abilities suppressed and two players blinded",
    "let know their way lay recalled back to beacon while the cypher cipher cam tagged our sage",
    "tell my teammates the enemy tek ko tejo launched both guided salvo missiles at the spike and the kayo null is still pulsing",
    "warn the team the enemy vyse vice activated steel garden while raze raise is boosting in with showstopper ready",
    "tell them the enemy sofa sova recon hit three on B and night fall fade trailed all of them, push the trails now",
    "our miks mix smoked A main but the enemy chamber chaymbur has tour de force sniper in the smoke gap",
    "tell my team two two enemies pushed hookah while their their cypher cipher camera is watching our flank",
    "let them know the enemy gecko gekkow wingman planted the spike while kayo kay-o was downed trying to revive",
    "tell my teammates their waylay weigh-lay used saturate and convergent paths at the same time, everyone is hindered and slowed",
    "warn the team the enemy iso i-so contracted our jett jet and she won the one-one-one in the arena",
    "tell my team the enemy phenix phoenix used run it back and the timer is running, kill him before the respawn",
    "let know their skye sky sent seekers at us while the enemy breach breech rolled thunder through mid, full wipe incoming",
    "tell them the enemy micks miks deafened our whole team with m-pulse and the deadlock dead lock grav net hit our ramp push",
    "warn my team the enemy yoru yoroo faked the teleport audio twice and the actual teleport put him on B site behind us",
    "tell my teammates the enemy raina reyna hit empress and dismissed twice and is at over a hundred HP with devour",

    # =========================================================================
    # BLOCK 29 — ABILITY NAMES + GARBLED AGENT COMBOS (RELAY DIRECTIVES)
    # =========================================================================
    "tell my team to push B when the mix miks waveform smoke fades in two seconds",
    "let them know to shoot the gekkow gekko wingman before it concusses our entry fragger",
    "tell my teammates to cover the kay o kayo body, revive him before null expires",
    "warn the team to scatter before the sofa sova fury beams hit, three charges left",
    "tell them to destroy the vee-to veto interceptor before we throw any grenades",
    "tell my team to peek A long while jett jet has no tailwind and no dash",
    "let them know to not walk into the cypher cipher cage on B, there is an audio cue trap",
    "tell my teammates to shoot the fade haunt eye before it scans A site",
    "warn the team to trade immediately when the phenix phoenix is in run it back timer",
    "tell them to push mid while the astre astra has no stars placed yet at round start",
    "tell my team to plant for main while the vipr viper wall is up splitting the site",
    "let them know to kill the gekkow gecko before he reclaims his thrash globule",
    "tell my teammates to rotate B now while the dead lock deadlock barrier mesh is down",
    "warn the team to push A on the miks mix bassquake ult so defenders are concussed",
    "tell them to swing CT while the enemy chaymbur chamber has no rendezvous anchor",
    "tell my team to rush B while kayo's kayjo's null suppression is still pulsing on site",
    "let them know to peek through the vipr viper smoke gap while she is out of fuel",
    "tell my teammates to avoid the gekkow gecko mosh pit, it detonates after the pulse",
    "warn the team to scatter from the sofa sova fury beam line, he can adjust angle",
    "tell them to push A lane while the enemy knee-on neon has no high gear for six seconds",

    # =========================================================================
    # BLOCK 30 — MAP CALLOUTS + GARBLED AGENT NAMES + FULL FACT RELAYS
    # =========================================================================
    "tell my team two players are in hookah and the cipher cypher cam is watching the exit",
    "let them know the enemy sova sofa recon hit three at B long, rotate to A now",
    "tell my teammates one gekkow gekko is planting at A default while two cover main",
    "warn the team the enemy breach breech rolling thunder is aimed at C entry on Haven",
    "tell them the enemy way lay waylay recalled her beacon on split mid tower",
    "our sofa sova owl drone tagged the enemy Killjoy in B lobby, she is fully revealed",
    "tell my team the enemy kayo kay-o has his knife suppressing A heaven and CT link both",
    "let them know the enemy micks miks waveform smoked A elbow and CT simultaneously",
    "tell my teammates the enemy geko gekko thrash is piloting into B site, three enemies behind it",
    "warn the team the enemy vee-to veto evolution makes him immune on the retake push",
    "tell my team the enemy fenix phoenix put his run it back marker at A lobby before peeking",
    "let them know the enemy jett jet has blade storm knives on the B long sightline",
    "tell them two enemies pushed B main and one is lurking CT, their kypher cypher has a cam on mid link",
    "warn my team the enemy iso i-so killed contract pulled our Breach and won the duel, he is back",
    "tell my teammates the enemy night fall fade trailed our entry, prowlers are coming from mid",

    # =========================================================================
    # BLOCK 31 — ECONOMY + GARBLED AGENT (ecobleed stress with STT)
    # =========================================================================
    "tell my team the enemy is on eco, their fenix phoenix has no curveball this round",
    "let them know to force buy this round because the enemies are saving and mix miks has no smoke",
    "tell my teammates their kayoh kayo has no frag and no flash on the eco, push him",
    "warn the team to save our rifles, we lost the round and their sofa sova still has drone",
    "tell them the enemy chaymbur chamber is going glass cannon with tour de force and no armor on the force",
    "our team should half buy because their vee-to veto is full util with evolution ready",
    "tell my team the enemy gekkow gekko has no wingman charge bought this round, check his economy",
    "let them know the enemy cypher cipher is skipping trap wires on eco but still has the cam up",
    "tell my teammates their knee-on neon has relay bolt but no fast lane on the half buy",
    "warn the team the enemy Raze raise bought both blast packs on force but has no paint shells",
    "tell my team the enemy breach breech is full util on a gun round with all flashpoints bought",
    "let them know the enemy waylay way-lay bought saturate but saved the lightspeed charges for next round",
    "tell them save this round because the enemy miks mix will full buy next with bassquake ready",
    "warn my team the enemy fayed fade bought two prowlers and haunt on a half buy",
    "tell my teammates the enemy ISO eye-so is buying kill contract with full util on a force round",

    # =========================================================================
    # BLOCK 32 — BRIMSTONE / BRIM STONE (split word) + ABILITY GARBLE
    # =========================================================================
    "tell my team the enemy brim stone is smoking all three sites on Haven with sky smokes",
    "let them know brimstone dropped an orbital strike on B spike, do not defuse until the laser ends",
    "tell my teammates the enemy brim stone put a stim beacon at A plant, do not stand in it",
    "warn the team their brimstone incendiary molly is burning the B default plant spot",
    "tell them the brim stone sky smokes are fading in five seconds, push now before he re-smokes",
    "our brimstone dropped stim at the entry point, stand in the field for the fire rate boost",
    "tell my team the enemy brim-stone orbital is aimed at mid, move off the mid position now",
    "let them know brimstone has only one incendiary left this round, push B on his smoke timing",
    "tell my teammates the enemy brim stone can still re-smoke A, his sky smokes have a hundred credit recharge",
    "warn the team their brimstone orbital strike is on seven points, one kill away from the laser this round",
    "tell my team brim stone's smokes last almost twenty seconds, do not try to time them out quickly",
    "let them know the enemy brimstone dropped stim at A elbow and their team will get combat stim on the push",
    "tell them the enemy brim stone re-smoked mid with his orbital targeting tablet, third smoke of the round",
    "warn my team the enemy brimstone incendiary is covering the spike, the fire deals sixty damage per second",
    "tell my teammates brim stone is ulting with orbital strike on A long, any player holding long angle must move",

    # =========================================================================
    # BLOCK 33 — DEADLOCK / DEAD LOCK (split + sonic sensor focus)
    # =========================================================================
    "tell my team the enemy dead lock sonic sensor is on hookah corner, any loud noise sets it off",
    "let them know deadlock grav-net hit our Sage on A ramp, she is pinned and crouching",
    "tell my teammates the enemy dead lock annihilation cocooned our Phoenix, break the cocoon now",
    "warn the team their deadlock barrier mesh is blocking B entry, shoot the center orb first",
    "tell them the enemy dead lock has annihilation up this round, do not peek her alone",
    "our deadlock placed two sonic sensors in hookah, anyone rushing through gets concussed",
    "tell my team the enemy dead-lock grav net pinned three of us on A main, we cannot jump or run",
    "let them know deadlock sonic sensor went off because our Sage used slow orb near it",
    "tell my teammates the enemy dead lock shot her annihilation nanowire at our Breach on B",
    "warn the team the deadlock barrier mesh does not block bullets, only bodies, peek through it",
    "tell my team the enemy dead lock's cocooned Breach will die unless we break the six-hundred HP cocoon",
    "let them know our deadlock is using grav net to pin the B main rush, push while they are crouching",
    "tell them the enemy dead lock placed her sonic sensor on the vent connector, do not fire near it",
    "warn my team deadlock annihilation pulls the target along a fixed path, break the cocoon early",
    "tell my teammates the enemy dead-lock reset her sonic sensor after we set it off, B main is watched again",

    # =========================================================================
    # BLOCK 34 — CLOVE / CLOV (Clove controller — post-death smoke garble)
    # =========================================================================
    "tell my team the enemy clov is smoking from the grave after dying, smokes last six seconds",
    "let them know clove activated not dead yet and needs one kill to stay alive, take the fight",
    "tell my teammates the enemy clov meddle-decayed our Viper to almost zero max HP",
    "warn the team their clov has not-dead-yet on eight points, she can revive if she dies",
    "tell them the enemy clov smoked from the grave while dead, the smoke is already fading",
    "our clove used pick-me-up after the kill, she is overhealed by fifty HP and running fast",
    "tell my team the enemy clov set up a meddle decay zone on spike before she died",
    "let them know the dead enemy clov placed one ruse smoke on A, only six seconds, push fast",
    "tell my teammates the enemy clove revived with not dead yet and got the kill to stay alive",
    "warn the team their clov is still alive after dying because she activated not-dead-yet",
    "tell my team the enemy clov's post-death smoke duration was nerfed, only six seconds, time it",
    "let them know the enemy clov absorbed a soul with pick-me-up and has temporary overheal",
    "tell them the enemy clov's meddle zone decays max HP by ninety, burst through it before she repositions",
    "warn my team the enemy clov is not dead, she is reviving from not dead yet, kill her again",
    "tell my teammates the enemy clov deployed two ruse smokes from the map view before dying",

    # =========================================================================
    # BLOCK 35 — HARBOR / HARBOUR (UK spelling STT output + reworked abilities)
    # =========================================================================
    "tell my team the enemy harbour is using storm surge to nearsight our B main push",
    "let them know harbor cove shield is protecting the spike plant, bullets cannot pass through it",
    "tell my teammates the enemy harbour rolled his high tide wall down mid to split the site",
    "warn the team their harbor activated reckoning water surge into A, the wave is moving fast",
    "tell them the enemy harbour cove is shielded with six-eighty HP, shoot through it before the plant",
    "our harbor threw storm surge onto B entry and nearsighted two of their defenders",
    "tell my team the enemy harbour wall on high tide is slowing anyone who crosses by thirty percent",
    "let them know harbor's cove shield broke, the plant spot is now open to bullets",
    "tell my teammates the enemy harbour is using reckoning to push through A link, move sideways",
    "warn the team their harbor cove smoke is almost at its nineteen-second duration, push after",
    "tell my team harbor reckoning water moves twenty-five percent faster after the patch, dodge perpendicular",
    "let them know the enemy harbour threw a storm surge whirlpool on the corner, two-second nearsight",
    "tell them our harbor shielded the cove on spike, we can plant in complete bullet safety",
    "warn my team the enemy harbour high tide wall slows our Neon's slide by thirty percent",
    "tell my teammates the enemy harbor reckoning can hold position on the site now if he reactivates it",

    # =========================================================================
    # BLOCK 36 — ASTRA / ASTRE / ASTER (Astra controller final vowel)
    # =========================================================================
    "tell my team the enemy astre is entering astral form, she is vulnerable while placing stars",
    "let them know astra nova pulsed B site, the concuss lasts three and a half seconds",
    "tell my teammates the enemy aster put a gravity well on A main, do not cluster near the star",
    "warn the team their astre has cosmic divide ready, she will wall-split the site with bullet blocking",
    "tell them the enemy astra dissipated her star to fake a smoke on B, watch for the pivot to A",
    "our aster placed stars at all three key angles, she has gravity well and pulse ready",
    "tell my team the enemy astre activated her gravity well on our entry, Neon is vulnerable now",
    "let them know astra's cosmic divide blocks bullets and audio, we cannot hear them through it",
    "tell my teammates the enemy aster pulled two players with gravity well and the team shot through the vulnerable window",
    "warn the team their astre has five stars placed this round, maximum utility lockdown",
    "tell my team the enemy astra dissipated and faked B, they are actually going A, rotate",
    "let them know the enemy astre nova pulsed through a star she placed on mid, three players concussed",
    "tell them the enemy aster's cosmic divide wall is up on B site, going around it adds ten seconds",
    "warn my team the enemy astra gravity well is activated on A lobby, spread out before you enter",
    "tell my teammates the enemy astre put a fake dissipate smoke on B to bait our rotation then hit A",

    # =========================================================================
    # BLOCK 37 — MULTIPLE HOMOPHONES, ULT STATES + COMPOUND FACTS
    # =========================================================================
    "tell my team their kayoh kayo has null command up and their geko gecko is piloting thrash into site at the same time",
    "let them know the enemy sofa sova recon scanned two on B and the enemy cipher cypher cam is watching mid link",
    "tell my teammates the enemy mix miks smoked A but the enemy jett jet has blade storm up and no dash left",
    "warn the team the enemy phenix phoenix is in run it back timer and the enemy vyse vice steel garden jammed all our rifles",
    "tell them the enemy breech breach rolled thunder and the enemy waylay way-lay recalled her beacon simultaneously on A execute",
    "our kayoh kayo is overloading null and our gekkow gekko is piloting thrash, double execute right now",
    "tell my team the enemy sofa sova marked our Viper with the drone dart while the enemy clov clove smoked from the grave",
    "let them know the enemy miks mix bassquake ult is going off and the enemy dead lock deadlock grav net hit our entry at the same time",
    "tell my teammates the enemy raina reyna hit empress and the enemy vee-to veto is in evolution, both are immune to debuffs",
    "warn the team the enemy kayoh kayo null suppression and the enemy astre astra cosmic divide combined to isolate our whole team on B",
    "tell my team their geko gekko wingman planted while their dead lock deadlock barrier mesh blocked our path to spike",
    "let them know the enemy breech breach flashpoint blinded our Sova while the enemy sofa sova recon scanned B at the same time",
    "tell them their miks mix waveform smoked two sites simultaneously and the enemy jett jet is dashing through mid with no dash left after",
    "warn my team the enemy waylay weigh-lay hindered our team with saturate while the enemy chaymbur chamber is holding A long with tour de force",
    "tell my teammates the enemy tea-joe tejo suppressed six players with drone detonate and the enemy phenix phoenix used run it back in the same round",

    # =========================================================================
    # BLOCK 38 — DIRECTIVE-HEAVY ITEMS + GARBLED NAMES (SNAP/OFF-SNAP BOUNDARY)
    # =========================================================================
    "tell my team to rotate A because the sofa sova recon hit three and none are on B",
    "let them know to push B on the mix miks smoke timing before she can re-smoke",
    "tell my teammates to not peek the jett jet when she has blade storm and no used tailwind",
    "warn the team to shoot the geko gekko thrash globule or he gets his ult back",
    "tell them to trade immediately because the phenix phoenix is in run it back",
    "tell my team to rush B while the dead lock deadlock has no grav net and no barrier mesh",
    "let them know to stay spread against the enemy astre astra who has nova pulse and gravity well on B",
    "tell my teammates to kill the enemy kayoh kayo quickly, he is downed but team can revive him",
    "warn the team to scatter before the sofa sova fury beam hits the corridor, three charges loaded",
    "tell them to push now while the enemy miks mix is out of waveform fuel",
    "tell my team to protect the dead lock deadlock lockdown device or it gets destroyed before the detain",
    "let them know to shoot the vyse vice arc rose flash device before she pops it on us",
    "tell my teammates to push A while the enemy chaymbur chamber has no anchor and his TP is on cooldown",
    "warn the team to break the cypher cipher cam on A site before the push or he has full info",
    "tell them to execute B before the enemy brim stone brimstone can re-smoke the entry with sky smoke",

    # =========================================================================
    # BLOCK 39 — FINAL FILL: VARIED GARBLE CLASSES TO HIT ~600
    # =========================================================================
    "tell my team the enemy cypher cipher neural theft pulled a full reveal on us after he used it on our Sova",
    "let them know the enemy gekkow wingman concussed our entry and then reclaimed to a globule, shoot it",
    "tell my teammates the enemy kayo kayoh null command pulse suppresses every three seconds, stay outside the radius",
    "warn the team the enemy sofa sova shock dart bounced twice and landed on our retake stack",
    "tell them the enemy breech breach fault line is charged to max range, stun covers all of B main",
    "our waylay weigh-lay convergent paths ult gave her a speed boost and hindered two defenders simultaneously",
    "tell my team the enemy micks miks waveform smoke is a one-way setup on A short",
    "let them know the enemy fenix phoenix curveball curved right and blinded two players in CT",
    "tell my teammates the enemy jett jet used both cloudburst smokes to cross B long solo",
    "warn the team the enemy dead lock deadlock sonic sensor is watching the plant area, do not fire near it",
    "tell my team the enemy vee-to veto chokehold tether trapped our Sage in hookah entry",
    "let them know their raise raze boom bot locked onto our Phoenix in A main, shoot the bot",
    "tell them their astre astra cosmic divide wall is blocking bullets on the entire B site entry line",
    "warn my team the enemy vyse vice shear triggered in B link and isolated one of our players",
    "tell my teammates our geko gekko mosh pit is covering the spike post-plant, wait for detonation",
    "tell my team the enemy kayyy-o kayo used his frag fragment on spike, it pulses, wait before defusing",
    "let them know the enemy chaymbur chamber's rendezvous anchor is at heaven, shoot it to deny his escape",
    "tell my teammates push right now while the enemy mix miks is out of waveform and bassquake is on cooldown",
    "warn the team the enemy yoroo yoru-u faked the gate crash audio again, do not rotate",
    "tell them the enemy raina reyna has dismiss available again after a kill, track her orb count",
    "tell my team the enemy brim-stone brimstone used his orbital strike ult and it is hitting A long now",
    "let them know the enemy tay-ho tejo fired guided salvo at our spike from across the map, missiles incoming",
    "tell my teammates the enemy isla i-so iso contingency wall went up at B entry, do not wallbang it",
]


