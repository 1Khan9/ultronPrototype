"""Relay corpus: stress_disfluency (kind=relay, ~600 cases).

CHARGE: Self-correction + disfluency. The streamer stutters, restarts, pivots
mid-sentence, inserts filler, or explicitly overrides their own words — but the
FINAL intent must be preserved faithfully by the relay pipeline.

Patterns exercised:
  - Hard restarts  ("tell my -- no wait, rotate B not A")
  - Self-corrections with "I mean" / "actually" / "scratch that" / "wait no"
  - Filler islands  (um, uh, like, so, y'know, I mean)
  - Mid-sentence pivots that flip site, agent, ownership, count, directive
  - Trailing repair  ("...B site -- actually no, A site, tell them A")
  - Double negation + repair  ("don't rotate -- wait yes do rotate")
  - Count pivots  ("two -- no, three -- yeah three B long")
  - Ability-name corrections  ("her dash -- no her ult, blade storm")
  - Location upgrades  ("main -- no, past main, garden")
  - Economy flips  ("force -- nah save, tell them to save")
  - Agent name corrections  ("their Reyna -- wait Iso, it's Iso")
  - Stacked fillers before a real callout
  - Abandoned opener + fresh start mid-utterance

Metrics stressed:
  - Final-intent extraction across mid-sentence flips
  - Filler removal without discarding payload
  - Self-correction override: discarded branch must NOT appear in relay output
  - Ownership: correction must carry to the right team side
  - Count retention after pivot
  - No hallucination from ambiguous partial abandoned branch
  - Directive vs observation after pivot
  - Ecobleed: corrected round-type must dominate

Agents, ability names, map callouts verified against refs/*.md.
All items are relay commands — the streamer is instructing the system to relay.
Kind: relay. Target: 600 cases.
"""

ITEMS = [
    # ================================================================
    # SECTION 1 — SITE / LOCATION PIVOTS (corrections that flip the target site)
    # ================================================================
    "tell them rotate A -- no wait, rotate B, everyone rotate B",
    "say go A -- actually scratch that, go B, execute B",
    "smoke A main -- no, smoke B main, smoke B",
    "push A -- uh -- push B, push B site",
    "tell them stack A -- no wait -- stack B this round",
    "execute A -- I mean execute B, tell them execute B",
    "rotate A site -- actually no, C site, rotate C",
    "spike A -- wait no, spike B, it's B site",
    "flash A main -- no flash B main, look away B",
    "tell the team hold A -- scratch that, hold B, hold B door",
    "anchor A -- no anchor B, anchor B long",
    "rush A -- wait -- rush B, everyone rush B",
    "fall back to A -- no C, fall back to C site",
    "lurk A -- actually lurk B, tell them lurk B",
    "say spike A -- no it's B, planted B, spike B",
    "entry A -- actually entry B, tell them entry B",
    "they're pushing A -- no wait -- tell them B, two B",
    "go A short -- I mean C short, tell them C short",
    "plant A default -- no plant B, tell them plant B default",
    "commit A -- um -- commit B, full commit B",
    "say retake A -- hold on -- retake B, retake B site",
    "tell them spike A garden -- I mean -- A site, spike A site",
    "peek A main -- no -- peek B main, jiggle peek B main",
    "clear A -- scratch that -- clear C, clear C site first",
    "tell them anchor A cubby -- wait A switch, anchor A switch",
    # ================================================================
    # SECTION 2 — COUNT PIVOTS (corrections that change the number)
    # ================================================================
    "two B main -- wait -- three B main, three of them",
    "one A long -- no two, two A long",
    "three mid -- wait -- four mid, four people mid",
    "five B -- well -- three B, three B site, tell them three",
    "one lurking -- I think two -- yeah two, two lurking CT",
    "say two C -- actually one, one C long",
    "four pushing -- nah -- two, two A main",
    "three rotating -- wait -- they're all rotating, five rotating B",
    "one last -- no two last -- yeah two alive their side",
    "two on site -- make it three, three on A site",
    "one -- um -- two, two B lobby, tell them two B lobby",
    "say three A -- one came short -- two A main, two A main",
    "five rushing -- wait, two -- no five, full send B, five B",
    "four -- I mean five -- yeah five, they're all B, full send",
    "one planting -- actually two are planting, two planting B",
    "three -- no -- two, two left alive their team",
    "say one defusing -- wait two defusing, two defusing spike",
    "two holding heaven -- one, one heaven, one heaven A",
    "four eco -- no -- five eco, all five saving",
    "one -- one more -- wait two, two B long no armor",
    # ================================================================
    # SECTION 3 — AGENT IDENTITY CORRECTIONS
    # ================================================================
    "their Reyna -- wait no, Iso, it's Iso pushing",
    "tell them Jett has no dash -- wait that's Waylay, Waylay has no beacon",
    "their Sage -- I mean Clove -- Clove is smoking from grave",
    "Sova used his ult -- no that's KAY/O, KAY/O overloaded",
    "Viper pit on site -- actually Clove, Clove's pit, Clove ult",
    "say Neon sprinting -- wait Jett, Jett's dashing",
    "their Killjoy ult -- no Deadlock, Deadlock lockdown incoming",
    "Skye flash -- no Breach, Breach flash incoming, look away",
    "Raze boost -- I mean Waylay, Waylay dashing in",
    "Fade haunt -- wait Sova, Sova recon bolt up",
    "Iso wall -- scratch that -- Sage wall, Sage walling B main",
    "Gekko wingman -- no Tejo drone, Tejo drone pushed mid",
    "Cypher cam -- wait Fade, Fade eye revealed two B",
    "KAY/O knife -- no, Tejo drone suppressed, abilities gone",
    "say Reyna ult -- I mean Empress -- wait Viper pit, it's Viper pit",
    "their Omen -- wait Astra, Astra dividing site",
    "Brimstone orbital -- no Tejo airstrike, Tejo armageddon",
    "Yoru teleporting -- wait it's a fake, Yoru faked the TP",
    "their Phoenix -- I mean Raze, Raze showstopper, rocket out",
    "Sage rez -- no Clove ult, Clove is not dead yet",
    "Veto ult -- I mean Evolution, Veto evolved, he's immune",
    "tell them Vyse garden -- wait, Steel Garden, primaries jammed",
    "Deadlock cocooned -- actually GravNets down, netted mid",
    "Chamber tour de force -- I mean op, Chamber has op, watch op",
    "Gekko thrash -- wait -- Dizzy, Dizzy out, look away B",
    # ================================================================
    # SECTION 4 — ABILITY NAME CORRECTIONS
    # ================================================================
    "tell them Jett smoked -- I mean dashed, Jett used her dash",
    "her ult -- no her dash -- her ult, blade storm, Jett blade storm",
    "his flash -- wait his wall, Phoenix walled up not flashed",
    "Raze grenade -- no her bot, Boom Bot out mid",
    "say Reyna dismissed -- no she leer'd, Leer out, shoot the eye",
    "KAY/O flash -- wait his knife, zero point knife, suppress on B",
    "Breach stun -- I mean his roll -- Rolling Thunder, ult incoming",
    "Viper wall -- no her pit, pit going up, Viper pit",
    "Sage wall -- wait slow orb, Sage slowed B main",
    "Sova drone -- actually shock bolt, two shock bolts B site",
    "their -- Fade seize -- wait prowler, prowler chasing A long",
    "Omen step -- I mean ult -- From the Shadows, he's ulting C",
    "Neon stun -- no sprint, High Gear, she's sprinting in",
    "Iso contract -- wait shield -- Double Tap, he has shield up",
    "Skye tiger -- I mean seekers, Seekers out, watch for nearsight",
    "Clove smoke -- wait NDY, Not Dead Yet, Clove is coming back",
    "Harbor wave -- no cove -- Cove, Harbor cove on spike",
    "Brimstone molly -- wait orbital, orbital on site, move",
    "say Waylay slowed -- I mean -- hindered, Saturate on B site",
    "Gekko mosh -- wait wingman, Wingman is planting spike",
    "KAY/O frag -- no flash -- pop flash, KAY/O pop flash mid",
    "Deadlock net -- I mean sensor -- Sonic Sensor popped B long",
    "Vyse rose -- no shear -- Shear triggered, enemy cut off",
    "Astra pulse -- I mean grav -- Gravity Well, pop the grav mid",
    "Tejo sticky -- no missiles -- Salvo on site, move from default",
    # ================================================================
    # SECTION 5 — OWNERSHIP / SIDE CORRECTIONS (our vs their)
    # ================================================================
    "tell them our Sage is walling -- wait their Sage, their Sage walled A",
    "say our Killjoy lockdown -- I mean enemy KJ, their KJ ult incoming",
    "our Jett used her dash -- no their Jett, their Jett no dash",
    "we used Sova drone -- wait they droned us, enemy drone pushed mid",
    "our smoke on B -- no their smoke, they smoked B main",
    "say their Viper wall -- wait ours, our Viper walled off CT",
    "our Clove is dead -- no their Clove, their Clove is ulting",
    "say our ult is up -- wait that's their ult, enemy Reyna empress'd",
    "tell them I placed the trip -- wait their Cypher trip, trip on B",
    "our Breach flashed -- scratch that -- enemy flashed us, breach flash",
    "our Neon sprinting -- actually their Neon, their Neon sprinting A main",
    "say we suppressed them -- no they suppressed us, KAY/O knife hit team",
    "our Gekko thrash -- wait their Thrash, their Thrash detained mid",
    "tell them our orbital -- no their Brimstone ult, orbital landing A",
    "say our turret spotted -- wait enemy bot, their KJ bot is on B",
    # ================================================================
    # SECTION 6 — DIRECTIVE vs OBSERVATION PIVOTS
    # ================================================================
    "tell them rotate B -- wait, they already rotated, two B came from CT",
    "say flash A main -- I mean they're flashing, enemy flash incoming A",
    "tell team smoke CT -- no they smoked CT, CT is smoked, rotate now",
    "push B -- wait they're pushing B, two B, fall back",
    "play retake -- I mean they're retaking, they're retaking A, hold",
    "say rush mid -- wait they rushed, they rushed mid already, adjust",
    "anchor site -- oh wait, site's lost, they took A, rotate",
    "say entry B -- wait they're entering, they're on B site already",
    "defuse spike -- uh -- they're defusing, stop the defuse, push",
    "tell them plant -- wait it's planted, spike B already down",
    "lurk mid -- actually they're lurking, one lurking through mid",
    "contest heaven -- wait they have heaven, two heaven holding A",
    "say hold B main -- no they pushed, they broke through B main",
    "peek long -- wait no, they're peeking, Jett peeking A long",
    "tell them execute A -- they're executing, they're executing A now",
    # ================================================================
    # SECTION 7 — ECONOMY / ROUND-TYPE PIVOTS
    # ================================================================
    "tell them force -- no wait -- save, we should save this round",
    "say eco -- actually force -- force this round, everyone force",
    "full buy -- wait -- half buy, half buy this round guys",
    "say save -- no buy -- full buy, we can afford full buy",
    "force B -- I mean -- eco, eco this round, bank it",
    "drop Vandal -- actually Phantom -- drop a Phantom, drop me Phantom",
    "say they're on eco -- wait full buy, they have rifles, full buy",
    "anti-eco -- no -- full buy for them, they bought, full rifles",
    "tell them bonus round -- I mean -- force, force this round",
    "half buy -- scratch that -- full buy, econ check, we can full buy",
    "save utility -- wait -- buy util, buy all your util this round",
    "say save next -- actually buy next -- we can full buy next round",
    "force rifles -- I mean -- Spectres, everyone buy Spectre, force Spectre",
    "tell them drop op -- wait Sheriff -- drop a Sheriff to the Jett",
    "anti-eco setup -- no -- we're on eco, save this round, save",
    # ================================================================
    # SECTION 8 — STACKED FILLERS + LATE PAYLOAD
    # ================================================================
    "uh -- um -- so -- two A long, two A long, tell them",
    "I mean -- like -- so -- rotate B, rotate B now",
    "um -- wait -- uh -- they're defusing, stop the defuse",
    "like -- I mean -- y'know -- spike is B, spike B site",
    "so uh -- hmm -- I think -- three mid, three holding mid",
    "well -- I mean -- let's see -- one shot CT, one shot CT push",
    "y'know like -- kind of -- just -- rotate off A, tell them rotate",
    "uh -- actually -- y'know -- no ult their side, safe to push",
    "um -- so -- yeah -- just tell them full send B, everyone go B",
    "like -- okay so -- basically -- Jett no dash, Jett has no dash",
    "I mean -- uh -- like -- their KJ has ult, be careful",
    "so um -- kind of -- basically -- we eco this round, eco",
    "y'know um -- I guess -- three of them on site, three A",
    "hmm -- like -- actually -- tell them smoke B main, smoke B",
    "uh y'know -- like -- okay -- entry on my flash, entry B",
    "so uh -- I mean -- basically -- viper pit, Viper has pit",
    "like honestly -- uh -- okay -- one last, last one defusing",
    "um, wait, so -- y'know -- execute A, execute A now",
    "well uh -- let me think -- okay two B no armor, two B no armor",
    "honestly like -- y'know -- just -- rotate CT, rotate through CT",
    # ================================================================
    # SECTION 9 — ABANDONED OPENER + FRESH RESTART
    # ================================================================
    "tell my -- no wait -- tell the whole team to hold B, hold B",
    "say to -- uh -- just say two A main, two A main, say that",
    "I want -- I want you to -- just flash B, flash B entry",
    "can you -- can you say -- rotate off A, rotate off A, go B",
    "tell them that -- tell them three B, three B main",
    "can you relay -- I mean just tell them -- eco round, eco",
    "say that -- I mean -- say their Sage is walling, Sage wall B",
    "tell my team -- no forget it -- spike A, just say spike A",
    "I think -- I think they're -- just two CT, two CT spinning",
    "tell the guys -- tell them -- rotate B long, B long rotate",
    "can you -- can you say -- Jett has op, op at A long",
    "I want to say -- actually just relay -- KJ ult, KJ lockdown",
    "so just -- tell them -- force buy, force this round",
    "you know -- can you say -- smoke B, smoke both mids",
    "I meant to say -- uh -- just tell them -- full send A, go A",
    "relay that -- no wait -- relay this -- one A site back wall",
    "tell my team -- y'know -- just -- orbital in, move from spike",
    "can you say -- actually -- tell them Clove smoked from death",
    "I need you to -- uh -- just say -- rush B, rush B now",
    "just tell them -- I mean -- lurk CT, one lurking CT link",
    # ================================================================
    # SECTION 10 — EXPLICIT OVERRIDE PHRASES
    # ================================================================
    "rotate A -- scratch that -- B, I mean B, tell them B",
    "actually no -- B site -- I said B, not A, tell them B site",
    "forget what I said -- rotate C, C site, rotate C",
    "disregard -- push B main, tell them push B main",
    "no wait I was wrong -- three A long not two, three A long",
    "correction -- spike is B not A, planted B, spike B",
    "undo that -- tell them force not eco, force this round",
    "overriding -- entry B not A, entry B, entry B",
    "ignore previous -- smoke A not B, smoke A lobby",
    "flip that -- I meant B, rotate B, B rotation",
    "no actually -- Jett has ult not no ult -- Jett blade storm ready",
    "update -- four B not three, four B main pushing",
    "correct myself -- one shot not dead, one shot B main",
    "my bad -- eco not force, tell them eco, save this round",
    "scratch everything -- two defusing, two on spike, tell them",
    "I misspoke -- their Clove not our Clove -- their Clove ulted",
    "retract that -- spike is A not B, planted A, relay spike A",
    "I said -- no wait -- tell them hold not push, hold A site",
    "delete that -- Viper wall is down, wall faded, B main open",
    "no no no -- one not two -- one B not two, last one B",
    # ================================================================
    # SECTION 11 — MID-SENTENCE FLIP + LOCATION UPGRADE
    # ================================================================
    "push A main -- no past main -- push A site, they're cleared out",
    "hold B long -- I mean B site, hold B site not just long",
    "smoke mid -- actually smoke mid and A main, both smokes",
    "lurk short -- past short into site, lurk onto B site",
    "flash A short -- I mean A long, flash A long entry",
    "rotate B link -- actually rotate all the way B, B site rotate",
    "play A lobby -- no -- all the way to A main, push A main",
    "smoke heaven -- no elbow, smoke elbow not heaven, smoke elbow",
    "hold CT -- actually hold B CT, B CT not A CT",
    "push garage -- I mean mid garage, tell them mid garage two B",
    "anchor C link -- no C site, anchor on C site itself",
    "peek A short -- I mean A short into site, clear A before peeking",
    "clear B lobby -- actually B main too, clear B lobby and B main",
    "smoke B entrance -- no B main and CT, smoke both B main and CT",
    "push A short sewer -- all the way to A site, entry A site now",
    "from market -- push through market to B site, market to B site",
    "hold A ramp -- past ramp on site, hold A site from ramp position",
    "play B entrance -- all the way in, commit B site",
    "clear A garden -- all the way to A site, garden then site",
    "hold C long -- I mean C site, anchor on C site, play C",
    # ================================================================
    # SECTION 12 — DOUBLE NEGATION + REPAIR
    # ================================================================
    "don't rotate -- wait do rotate, actually rotate B, rotate B now",
    "don't push -- wait push, they're low, push B main",
    "save it -- no spend it -- buy this round, full buy",
    "don't eco -- wait eco -- save this round, eco",
    "don't entry -- wait entry now, entry on flash, go",
    "hold off -- wait go -- commit A, execute A now",
    "don't flash -- wait flash, flash B main, look away",
    "don't smoke -- wait smoke mid -- smoke mid and go",
    "stand still -- no rush, rush B, everyone rush B",
    "don't rotate -- wait they're all B -- rotate, rotate B",
    "don't plant -- wait plant -- plant default, plant now",
    "cancel the ult -- no use the ult -- Sage rez, rez now",
    "don't push heaven -- wait two heaven, two heaven holding, clear",
    "don't defuse yet -- wait defuse, stick it, full defuse",
    "don't save -- wait save -- eco this round, save credits",
    # ================================================================
    # SECTION 13 — DAMAGE / HP CORRECTIONS
    # ================================================================
    "say one shot -- wait he's full -- no one shot, 10 HP A main",
    "tagged 50 -- no 80 -- hit him 80, he's lit 80",
    "he's low -- actually dead -- he's dead, A main kill confirmed",
    "one shot -- wait two shot -- nah one shot, 25 HP no armor",
    "no armor -- wait light armor -- light armor B long, still lit",
    "hit him 30 -- no 60 -- I hit him 60, lit 60 A short",
    "he's 100 -- wait -- no he's low, hit 90, he's 10 HP",
    "full health -- wait no -- lit 70, he's 30 HP B main",
    "I dink'd -- wait it was a body -- no dink, he's low tho, 15 HP",
    "he's tagged -- wait dead -- he's dead, mid kill confirmed",
    "say he's low -- I mean one shot -- one shot C long",
    "hit 40 -- wait 70 -- I think 70, he's lit 70 A lobby",
    "no armor -- wait heavy -- he has full armor B site",
    "say he's dead -- wait -- no he's alive, dink'd him, low B",
    "one shot A -- wait two shot -- nah one shot, 20 HP",
    # ================================================================
    # SECTION 14 — COMPLEX MULTI-CORRECTION CHAINS
    # ================================================================
    "tell my -- no wait, tell the whole team to rotate B not A, and smoke the CT",
    "uh Jett -- I mean Raze -- wait Waylay, Waylay dashing B main",
    "say three -- no two -- actually three, three A long with op",
    "eco -- force -- eco -- no force, force this round, just force it",
    "smoke A -- no B -- actually A and B, smoke both A main and B main",
    "their Reyna -- no Empress -- I mean Reyna's in empress, she's chaining",
    "two B -- wait one -- no two, two B long one shot",
    "rotate C -- no stay A -- no go C, rotate C link, they're C",
    "say push -- I mean hold -- no push, push B on my smoke",
    "Flash -- wait stun -- actually his ult, Breach rolling thunder incoming",
    "say anchor A -- wait lurk -- anchor A site then lurk mid",
    "spike A -- wait B -- uh A -- no B, spike B, spike is B",
    "their Clove -- no Sage -- uh Sage rez, Sage rez on B site",
    "entry B -- wait -- entry A -- I mean B, entry B site now",
    "save -- force -- buy -- ugh -- force buy, force this round",
    "one -- two -- three -- three B long, three B long definitely",
    "smoke mid -- actually no -- smoke A main -- both, smoke mid and A main",
    "their Iso -- wait Yoru -- Yoru ulting, he's in dimensional drift",
    "go B -- wait -- go A -- I said go B, execute B, execute B",
    "Sova dart -- I mean drone -- no dart, Sova recon bolt A site",
    # ================================================================
    # SECTION 15 — ABILITY STATE CORRECTIONS (up vs down)
    # ================================================================
    "say Jett has no dash -- wait she has it -- dash up, Jett dash ready",
    "KJ no ult -- wait she has ult -- KJ lockdown ready, watch out",
    "Reyna ult down -- no wait -- she's in empress, empress active",
    "say Phoenix ult down -- wait he's ulting -- run it back active, kill him",
    "Breach no ult -- wait rolling thunder -- Breach ult up, watch CT",
    "tell them op gone -- wait -- no Jett has op, op still up",
    "say Skye no flash -- wait two flashes -- Skye two hawks ready",
    "Sage no wall -- wait she just walled -- Sage wall B, wall up",
    "KAY/O knife down -- wait -- knife is up, Kayo knife up A short",
    "say Viper no pit -- she's setting it up -- Viper pit incoming",
    "Clove ult not ready -- wait -- she has NDY -- Clove ult up, careful",
    "tell them no orbital -- wait Brimstone ult ready -- orbital ready",
    "Yoru no ult -- wait -- he drifted -- Yoru in ult, he's invisible",
    "say Fade no haunt -- wait -- haunt up -- Fade haunt out A site",
    "Harbor cove down -- wait -- cove up -- Harbor cove on spike now",
    # ================================================================
    # SECTION 16 — MAP-SPECIFIC LOCATION CORRECTIONS
    # ================================================================
    # Ascent
    "two A main -- wait A peek, A peek not main, they're at A peek",
    "clear garden -- I mean wine, Wine shelf, they're at wine",
    "smoke catwalk -- no -- smoke market, smoke market entry",
    "hold tiles -- wait mid top, mid top not tiles, two mid top",
    "push B main -- no pizza -- they're at pizza, three pizza",
    # Haven
    "two C long -- wait A long, A long not C long, two A long",
    "rotate garage -- no nest -- Nest, two on nest, Nest Haven",
    "hold C short -- wait C link, C link, rotate C link",
    "three A short -- I mean sewer -- A sewer, three A sewer",
    "smoke double doors -- wait -- mid courtyard, smoke courtyard",
    # Split
    "hold mid mail -- no -- mid ramp, mid ramp, two mid ramp",
    "rotate vent -- wait -- rotate heaven, B heaven not vent",
    "smoke A main -- I mean A ramps, smoke A ramps entry",
    "three B back -- wait alley, B alley, three B alley",
    "lurk mid link -- no mid mail, mid mail, lurk mid mail",
    # Breeze
    "two A main -- wait -- A hall, hall not main, two A hall",
    "smoke mid -- I mean mid nest -- mid nest, smoke mid nest",
    "push B main -- no B back -- B back site, three B back",
    "hold A pyramids -- wait A cave, A cave not pyramids",
    "rotate from elbow -- wait east, east mid, rotate east mid",
    # Fracture
    "rush A main -- no A dish, A dish, three A dish",
    "smoke B arcade -- wait B entrance, B entrance not arcade",
    "hold rope -- wait pillar, rope pillar, anchor rope pillar",
    "rotate CT -- wait cantina, cantina, rotate cantina Fracture",
    "lurk B main -- I mean B tree, B tree, lurk B tree",
    # ================================================================
    # SECTION 17 — DIRECTIVE RECEIVER PIVOTS (who to tell)
    # ================================================================
    "tell Raze -- no tell Jett -- tell Jett to save her dash",
    "tell the Sova -- wait Fade, tell Fade to use her haunt A",
    "tell our Sage -- I mean Clove -- tell Clove to smoke from death",
    "tell Killjoy -- wait Cypher -- tell Cypher check cam B",
    "tell the entry -- no tell the lurker -- lurker push now",
    "tell the whole team -- well just Jett -- tell Jett go B",
    "tell support -- wait tell everyone, tell the whole team rotate",
    "just tell Neon -- no the Breach -- Breach flash now B main",
    "tell them all -- I mean tell IGL -- tell the IGL switch B",
    "tell Omen -- wait Brimstone -- tell Brim smoke A and B main",
    # ================================================================
    # SECTION 18 — TENSE / STATE CORRECTIONS
    # ================================================================
    "say they're pushing -- wait they pushed, they already took B",
    "they're planting -- wait planted, spike B already down",
    "they're rotating -- wait they rotated, two came from CT already",
    "she's healing -- wait healed already, Sage heal done, push now",
    "they're rushing -- wait they rushed, they're on B site now",
    "Yoru is teleporting -- wait he already TP'd, Yoru B site",
    "they're using ult -- wait ult is down, Reyna empress faded",
    "she's walling -- wait wall's up, Sage wall B main already up",
    "they're forcing -- wait they bought, they have rifles this round",
    "KJ is ulting -- wait lockdown landed, Lockdown down, fall back",
    # ================================================================
    # SECTION 19 — NEAR-IDENTICAL DOUBLES (stress uniqueness + correction carry)
    # ================================================================
    "say two B main -- no two B long, two B long is what I mean",
    "smoke A site -- I mean smoke A main, smoke A main not site",
    "their Jett -- uh no their Raze, Raze no Jett, Raze pushing B",
    "hit him 50 -- wait I mean tagged him 50, tagged 50 B long",
    "tell them rotate -- rotate B not mid, B, rotate B not mid",
    "one on heaven -- wait two heaven -- two heaven not one, two heaven",
    "Viper pit -- wait poison cloud -- no pit, Viper pit on A site",
    "entry A on flash -- on smoke -- on flash, entry A on flash",
    "full send -- rush -- full send, same thing, full send B",
    "lurk mid -- one lurking mid -- yeah one lurking mid, relay that",
    # ================================================================
    # SECTION 20 — SPIKE / DEFUSE CORRECTIONS
    # ================================================================
    "spike A -- wait B -- spike B, planted B site",
    "planted default -- no -- planted for CT, for CT not default",
    "tell them defuse -- wait -- spike's gonna blow, don't defuse",
    "ninja defuse -- wait -- fake defuse, tap it and pull back",
    "say plant now -- wait -- let Wingman plant, Wingman planting",
    "spike A main -- wait no -- A default, spike A default plant",
    "they're defusing -- wait -- they tapped -- tap defuse, half defuse",
    "spike open plant -- no -- safe plant -- they moved to safe plant",
    "defuse stuck -- wait -- enemy sitting -- one B spike holding",
    "planted B -- wait A -- no B, planted B site, spike B",
    "spike main -- I mean site -- spike mid B -- spike default B",
    "say stop defuse -- wait let him -- fake it, let them start then kill",
    "one defusing -- two defusing -- wait one, one defusing spike",
    "drop spike -- I mean pick up -- someone pick up spike",
    "spike carried -- wait dropped -- spike dropped A main, pick up",
    # ================================================================
    # SECTION 21 — ROTATION TIMING CORRECTIONS
    # ================================================================
    "rotate now -- wait -- hold, don't rotate yet, wait for info",
    "fast rotate -- I mean slow -- slow rotate B, don't sprint",
    "rotate A -- too late -- rotate B, swing to B, B rotation",
    "don't rotate yet -- wait -- rotate, they committed B, rotate B",
    "hold rotate -- wait go -- they're all B, go B, rotate B",
    "early rotate -- no late -- play late rotation, don't go early",
    "rotate CT -- wait -- rotate B long, B long not CT",
    "fake rotate -- no real rotate -- real rotate B, commit B",
    "rotate off -- wait one A -- one A long, don't rotate yet",
    "rotate mid -- I mean hard rotate -- full rotate B, everyone B",
    # ================================================================
    # SECTION 22 — STUTTER + WORD-LEVEL DISFLUENCY
    # ================================================================
    "ro -- rotate B, rotate B site",
    "two -- two -- two B, two B main, tell them two B main",
    "fl -- flash -- flash A main, close your eyes",
    "sm -- smoke -- smoke mid, tell them smoke mid",
    "Jett -- Je -- Jett no dash, Jett has no dash",
    "three -- th -- three B, tell them three B long",
    "spike -- sp -- spike A, planted A, tell them spike A",
    "KJ -- K -- KJ lockdown, KJ ult, be careful",
    "ult -- ul -- ult up, Reyna ult up, empress ready",
    "de -- defuse -- they're defusing, stop the defuse push",
    "ro -- ro -- rotate -- rotate C, they're going C",
    "entry -- ent -- entry B, entry B on my flash",
    "eco -- ec -- eco this round, tell them save",
    "Phi -- Phoenix -- Phoenix ult down, safe to push",
    "re -- rez -- Sage rez, save Sage ult for Raze",
    # ================================================================
    # SECTION 23 — OPINION / STRATEGY PIVOTS (off-snap flavour)
    # ================================================================
    "tell them stack B -- actually you know what -- stack A, they love B",
    "say play passive -- wait -- play aggressive, they're low eco",
    "tell them default -- no execute -- execute A this round",
    "say fake B hit A -- wait -- fake A hit B, fake A hit B",
    "tell them they're stacking A -- wait B -- they stack B every round",
    "say anti-eco setup -- wait they bought -- they full bought, play normal",
    "tell them their KJ anchors A -- wait B -- KJ anchors B every round",
    "say we should split -- wait -- stack, stack B, don't split",
    "tell them slow play -- no -- quick exec, quick exec before util",
    "say play for time -- wait -- force it, clock's low, force the push",
    "tell them he lurks -- wait -- he's anchoring, their Cypher anchors B",
    "say play crossfire -- wait play off -- play off their support angle",
    "tell them stack mid -- no -- ignore mid, fast hit B ignoring mid",
    "say play retake -- wait plant -- plant first then play retake angles",
    "tell them absorb util -- wait -- punish eco, punish the eco rush",
    # ================================================================
    # SECTION 24 — MIXED / COMPOUND DISFLUENCY (hardest cases)
    # ================================================================
    "um so like uh -- tell -- tell my -- just say two B main and they have op, two B op",
    "uh Raze -- I mean Jett -- no Raze -- Raze boost B main, three with Raze boosting",
    "eco -- force -- you know what -- full buy, we can full buy, tell them full buy",
    "tell them -- um -- actually -- rotate B, no A, I mean B -- B, rotate B, definitely B",
    "so three -- wait -- four -- no three -- definitely three A long, one shot",
    "say their Viper -- I mean Clove -- their Clove smoked from death, dead smokes B",
    "tell -- okay so -- two B -- two A -- ugh -- two split, one A one B",
    "Sova drone -- wait Fade -- no Sova -- Sova drone pushed mid, they saw us",
    "spike A -- planted -- wait -- default or for CT -- planted A for main, spike A main",
    "rotate now -- wait hold -- ugh -- rotate, yes rotate, rotate B it's clear",
    "force -- eco -- force -- ugh tell them force, just force this round",
    "say Jett -- no Waylay -- um -- it's Waylay, Waylay dashing, two dashes B",
    "three -- two -- three -- final answer three, three B lobby",
    "KJ ult -- wait lockdown -- same thing -- KJ lockdown, fall back from B",
    "uh so tell them -- um -- flash the main -- flash A main and then go",
    "two A -- wait three A -- no wait two A and one B -- two A one B split",
    "tell them smoke -- both smokes -- smoke A main and B CT, smoke both",
    "rotate B -- wait retake -- rotate B and retake, retake B from CT",
    "say their Iso -- I mean Yoru -- Yoru, Yoru fake TP, don't get baited",
    "eco round for us -- wait -- anti-eco for us, they're saving, anti-eco",
    "say entry -- wait the flash first -- flash then entry B, flash then entry",
    "uh orbital -- airstrike -- I mean orbital, Brimstone orbital on spike",
    "their Killjoy -- has ult -- I mean Lockdown ready -- KJ lockdown ready",
    "say wall B -- actually wall mid -- Viper wall mid, cut mid with wall",
    "you know like -- hmm -- three B no armor -- just say three B no armor",
    "tell them -- um -- Gekko wingman planting -- actually Raze -- wait Gekko -- Gekko Wingman is planting spike B",
    "rotate -- fall back -- rotate no fall back -- fall back to CT, then rotate B",
    "say two -- uh three -- I don't know -- two, two B long, two",
    "Fade ult -- nightfall -- same thing -- Nightfall going off, trails on three",
    "um so uh -- just relay -- two A site one shot and their Sage has no wall",
    # ================================================================
    # SECTION 25 — EDGE CASES: NEAR-NEGATIVES (look like negatives but ARE relays)
    # ================================================================
    "I should've said rotate B, tell them rotate B",
    "I was going to say eco but actually tell them force, force this round",
    "I almost missed it -- two A, tell them two A long",
    "I should've called spike B earlier, just say spike B now",
    "I forgot to say Jett no dash, say Jett has no dash now",
    "I meant to relay -- one CT lurking -- one lurking CT, say it",
    "I nearly said rotate -- say rotate B, rotate B site now",
    "should have called this earlier -- KJ ult ready, tell them",
    "I was going to say save -- but no -- force, tell them force",
    "I almost called three B -- yeah three B, tell them three B long",
    "I wanted to relay -- two split -- tell them two A two B",
    "I should say -- Reyna empress active -- tell them empress up",
    "I meant to say Viper pit -- say Viper pit on A site",
    "I nearly said smoke mid -- yeah smoke mid, tell them smoke mid",
    "I wanted to call -- orbital incoming -- orbital on site, tell them",
    # ================================================================
    # SECTION 26 — RAPID BACK-AND-FORTH CORRECTIONS (4+ flips)
    # ================================================================
    "A -- no B -- no A -- B, definitely B, tell them B site",
    "rotate -- hold -- rotate -- hold -- rotate, rotate B, final",
    "eco -- force -- eco -- eco, tell them eco, save round",
    "two -- three -- two -- two, two B main, two B",
    "her ult -- her dash -- her ult -- blade storm, Jett ult",
    "push A -- push B -- push A -- push B, push B, commit B",
    "save -- buy -- save -- buy, full buy, just full buy",
    "one shot -- dead -- alive -- one shot, 15 HP B main",
    "stack A -- stack B -- stack A -- stack B, stack B, they go A",
    "flash -- smoke -- flash -- flash B, flash B entry, look away",
    "spike A -- spike B -- spike A -- no B, planted B, spike B",
    "lurk -- entry -- lurk -- entry, entry B, entry B on smoke",
    "Raze -- Jett -- Raze -- Jett, Jett, Jett no dash",
    "rotate now -- wait -- go -- rotate now, rotate B now",
    "force -- eco -- force -- eco, eco, save this round",
    # ================================================================
    # SECTION 27 — SENTINEL UTILITY CORRECTIONS
    # ================================================================
    "tell them Cypher cam -- wait Spycam -- same thing, cam on B main",
    "say KJ nano -- wait alarmbot -- no nano, Nanoswarm on spike",
    "Cypher trip -- wait Deadlock sensor -- Sonic Sensor B entry",
    "Vyse flash -- wait Arc Rose -- same thing, Arc Rose popped B",
    "say Chamber trap -- Trademark -- Chamber trap B long",
    "tell them Deadlock net -- GravNet -- GravNet B site, they're pinned",
    "Vyse wall -- Shear -- Shear triggered, enemy cut off B main",
    "say Veto trap -- Chokehold -- Chokehold mid, they're tethered",
    "KJ turret -- wait Alarmbot -- turret, KJ turret watching A main",
    "say Deadlock cocoon -- Annihilation -- cocooned mid, break the cocoon",
    "Cypher cage -- Cyber Cage -- cage up B entrance",
    "Steel Garden -- Vyse ult -- primaries jammed, push now",
    "Neural Theft -- Cypher ult -- Cypher ulting, full reveal incoming",
    "Veto ult -- Evolution -- Veto evolved, he's immune, can't flash him",
    "Chamber op -- Tour de Force -- TDF, Chamber has sniper ult",
    # ================================================================
    # SECTION 28 — INITIATOR UTILITY CORRECTIONS
    # ================================================================
    "say Sova dart -- recon bolt -- Recon Bolt A site, two revealed",
    "KAY/O -- wait Tejo -- KAY/O knife not Tejo, Kayo suppressed B",
    "Fade cat -- prowler -- Prowler, Prowler chasing A long",
    "Skye bird -- hawk -- Guiding Light, hawk flashing B main",
    "say Gekko flash -- Dizzy -- Dizzy out, look away B short",
    "Breach fault -- fault line -- Fault Line A main, stunned",
    "Tejo sticky -- Special Delivery -- sticky B entrance concussed",
    "say Fade tether -- Seize -- Seize on B, they're tethered CT",
    "Sova shock -- two shocks -- double Shock Bolt B site",
    "Breach aftershock -- aftershock spike -- Aftershock on spike post-plant",
    "say Tejo salvo -- missiles -- Guided Salvo A site, move",
    "Skye tiger -- Trailblazer -- Trailblazer B main, concussed",
    "Gekko mosh -- Mosh Pit -- Mosh Pit B site, post-plant",
    "Sova fury -- Hunter's Fury -- fury ult, three beams, get down",
    "Fade nightfall -- trails on -- Nightfall hit three, trails active",
    # ================================================================
    # SECTION 29 — CONTROLLER UTILITY CORRECTIONS
    # ================================================================
    "say Brim orbital -- Orbital Strike -- Orbital on B spike, move",
    "Viper snake -- Snakebite -- Snakebite B default, vulnerable",
    "say Omen step -- Shrouded Step -- Omen stepped into smoke B",
    "Astra stun -- Nova Pulse -- Nova Pulse CT, stunned three seconds",
    "Harbor cove shield -- wait no shield -- Cove up, toggle the shield",
    "Clove meddle -- decay -- Meddle A site, they're decayed, burst them",
    "say Omen blind -- Paranoia -- Paranoia through A main wall",
    "Astra grav -- Gravity Well -- Gravity Well B, they're vulnerable",
    "say Harbor wall -- High Tide -- High Tide B main, slows through",
    "Brimstone stim -- Stim Beacon -- stim down A site, stand in it",
    "Clove pickup -- Pick-Me-Up -- Pick-Me-Up active, Clove overhealed",
    "Astra divide -- Cosmic Divide -- Cosmic Divide up, split A",
    "Harbor surge -- Storm Surge -- Storm Surge B entry, nearsighted",
    "say Omen ult -- From the Shadows -- Omen ulting C, shade spotted",
    "Viper cloud -- Poison Cloud -- Poison Cloud toggled A main",
    # ================================================================
    # SECTION 30 — FINAL INTENT STRESS: PRONOUN + REPAIR
    # ================================================================
    "tell them he's -- wait she's -- she's one shot, one shot CT",
    "their she -- wait he -- he's op, he has op A long",
    "say she flashed -- wait he -- he flashed B, Phoenix flash B",
    "he rotated -- wait she -- she rotated, Neon rotated mid",
    "their guy -- their girl -- their Jett -- Jett no dash, Jett",
    "he has ult -- wait she -- she has Empress, Reyna ult up",
    "she walled -- wait he -- he walled, Sage walled B main",
    "he ulted -- she -- wait him -- their Iso kill contract mid",
    "say they're -- he's -- they're all B, five B site",
    "she took A -- wait he -- wait both, two A site",
    # ================================================================
    # SECTION 31 — INDIRECT COMMAND + REPAIR
    # ================================================================
    "you might want to -- tell them -- rotate B, rotate B",
    "probably should -- just say -- eco round, tell them eco",
    "I think we should relay -- two A main -- yeah two A main",
    "might be worth saying -- spike B -- say spike B",
    "they need to know -- flash incoming -- tell them flash B",
    "you should probably -- relay three mid -- three mid, say it",
    "maybe just say -- Jett op -- Jett has op A long",
    "we should tell them -- KJ ult -- KJ lockdown incoming",
    "it would help to say -- Viper pit -- Viper pit on A",
    "let them know -- two defusing -- two on spike, tell them",
    # ================================================================
    # SECTION 32 — TIME-PRESSURE REPAIRS
    # ================================================================
    "quick say -- no wait -- two B, two B main, quick",
    "fast -- uh -- tell them rotate B, rotate B, fast",
    "hurry -- I mean -- spike A, spike A, say it quick",
    "now now -- uh -- three B, three B pushing, say now",
    "go go -- wait -- flash first -- flash then go B",
    "tell them fast -- uh -- one shot CT, one shot CT now",
    "say quick -- no wait -- eco, eco, say eco fast",
    "before round ends -- uh -- rotate C, rotate C site",
    "say it quick -- spike B -- spike planted B, quick",
    "hurry say -- uh -- last one site -- last one B site defusing",
    # ================================================================
    # SECTION 33 — SECOND-THOUGHTS ON TARGETS (relay to who)
    # ================================================================
    "tell the team -- no just tell Jett -- Jett go B, entry B",
    "relay to Raze -- wait the whole team -- everyone go B",
    "tell Breach -- no tell Sage -- Sage wall B main please",
    "just relay to Clove -- to everyone -- everyone eco this round",
    "tell Sova -- wait all -- all rotate B, rotate B",
    "tell the Viper -- no tell the IGL -- IGL eco this round",
    "just tell KJ -- tell everyone -- KJ lockdown, everyone fall back",
    "relay to Neon -- to all -- all entry B on Neon sprint",
    "tell Fade -- no everyone -- Fade haunt and everyone push",
    "tell the entry -- no support -- support flash then entry A",
    # ================================================================
    # SECTION 34 — LATE-ROUND CONTEXT CORRECTIONS
    # ================================================================
    "say save rifles -- wait eco, save rifles and eco",
    "tell them retake -- no plant -- they have spike, retake",
    "say clutch it -- no rotate -- can't clutch, rotate off",
    "tell them play for time -- wait force -- force defuse, stick it",
    "say let it blow -- wait defuse -- defuse, three seconds, defuse",
    "tell them reset -- wait last chance -- one chance, push now",
    "say forfeit -- wait play -- play it out, don't FF",
    "tell them anchor -- no rotate -- rotate off, lost the site",
    "say time out -- no they're defusing -- stop defuse, push",
    "tell them wait for spike -- wait it's over -- let it go, 3 sec",
    # ================================================================
    # SECTION 35 — ULTIMATE TRACKING + CORRECTION
    # ================================================================
    "say Jett ult -- wait down -- Jett ult down, blade storm used",
    "KAY/O overloaded -- wait ult used -- NULL/cmd over, revive done",
    "tell them Sage rez ready -- wait used -- Sage rez used, no rez",
    "say Chamber tour de force up -- wait down -- TDF down, safe to push",
    "tell them Clove NDY -- wait she used it -- Clove ult used",
    "Brimstone orbital ready -- wait -- used it -- orbital gone, spike clear",
    "say Reyna empress ready -- wait she already used -- empress down",
    "tell them Viper pit ready -- wait it's up -- Viper pit up on A",
    "KJ lockdown up -- wait used -- Lockdown used last round, no ult",
    "say Yoru drift ready -- wait he used it -- Yoru ult down",
    "Breach thunder up -- wait -- rolling thunder used -- no ult Breach",
    "say Raze rocket up -- wait showstopper used -- Raze no ult",
    "tell them Deadlock ult up -- wait -- Annihilation fired -- no ult DL",
    "say Astra divide ready -- wait cosmic divide up -- divide active",
    "Skye seekers up -- wait -- used seekers -- Skye no ult, seekers gone",
    # ================================================================
    # SECTION 36 — WEAPON CORRECTIONS
    # ================================================================
    "say they have op -- wait Vandal -- they have Vandals, rifles",
    "tell them Sheriff -- wait Ghost -- he has Ghost not Sheriff",
    "drop Vandal -- wait Phantom -- drop a Phantom, Phantom",
    "they're on Spectre -- wait rifles -- they bought, rifles this round",
    "say Marshal force -- wait Outlaw -- Outlaw, 2400, budget op",
    "say they have Odin -- wait Ares -- Ares, spray machine, Ares",
    "tell them he's op -- wait Guardian -- Guardian, he's on Guardian",
    "eco Shorty -- wait Bucky -- Bucky, they have Buckys on eco",
    "force Spectre -- wait Stinger -- Stinger force, everyone Stinger",
    "say drop Sheriff -- wait Vandal -- drop Vandal not Sheriff",
    # ================================================================
    # SECTION 37 — FINAL MIXED HARD CASES
    # ================================================================
    "uh -- so -- like -- their Clove -- wait Sage -- Sage rez B, Sage has ult",
    "two A -- wait three A no armor -- three A long no armor, relay",
    "tell team -- Omen blind through -- Paranoia through A main, push after",
    "KJ -- wait Veto -- Veto trap B, Chokehold B entry",
    "eco next -- I mean -- force next -- full buy next round actually",
    "say entry A on Breach flash -- wait Skye -- Skye hawk then entry A",
    "three site -- two site one off-angle -- two A site one off-angle, careful",
    "tell the guys -- their Raze has no paint shells -- no Showstopper -- Raze no ult",
    "tell them spike -- planted A or B -- planted B, spike B default",
    "rotate mid -- no rotate CT -- rotate through CT to B, CT rotation",
    "say two -- three -- I think two, two B and one lurking, relay two B one lurk",
    "their Viper -- wait Omen -- Omen smoked CT not Viper, Omen dark cover CT",
    "uh full buy -- well no -- half buy, everyone light buy this round",
    "say Wyalay -- Waylay, sorry -- Waylay dashing in B, two dashes",
    "entry on smoke -- on flash -- entry on flash B, flash first then entry",
    "say last one -- he's A -- B -- last one switching A to B, watch B",
    "GravNet -- wait Chokehold -- GravNet, Deadlock GravNet B site",
    "their Tejo -- wait Sova -- Sova recon revealed two B short",
    "tell them slow -- no fast -- quick execute B before Viper walls",
    "one defusing -- wait three -- one defusing, I see one, spike B",
    "say -- um -- rotation -- uh -- they rotated, three rotated to B",
    "Iso wall -- not Iso -- Sage wall, Sage barrier B main",
    "anchor B -- wait anchor CT -- anchor CT side for crossfire B",
    "smoke CT -- I mean smoke B main and CT -- smoke B main first then CT",
    "tell them Veto TP -- Crosscut -- Veto Crosscut B, watch the TP",
]
