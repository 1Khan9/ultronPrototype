"""Relay corpus: positions + counts (kind=relay, ~700 cases).

Domain: enemy/ally position callouts with explicit or implied counts across all
12 Valorant maps. Exercises:
  - count retention (1-5, "last", "full stack", implied all)
  - map-location accuracy (per-map callout names from refs)
  - ownership / subject (their vs our, enemy vs teammate)
  - action state (pushing, holding, rushing, lurking, planting, defusing, etc.)
  - compound multi-location callouts (two places at once)
  - negative info (nobody at X)
  - damage + position combo
  - elevation (heaven, hell, top, upper, lower, ramp, tower)
  - direction of movement (rotating, flanking, walking, rushing)
  - phrasing register: snap/terse to conversational/streamer-slang
  - regional/slang variation in count words
"""

ITEMS = [
    # ================================================================
    # ASCENT — A site area
    # ================================================================
    "two A main",
    "one in wine",
    "three pushing A main right now",
    "one holding wine, another peeking long",
    "four going A, full stack A main",
    "one tucked in the A peek spot, be careful",
    "two A main, one is heaven",
    "last one is somewhere in garden",
    "there's a guy deep in heaven watching main",
    "one holding generator, post plant",
    "two back site A, generator side",
    "one playing hell, under heaven",
    "three A, two main one heaven",
    "one close right at the A door",
    "two pushing through the A door, door is down",
    "one a main one shot, he's right there",
    "they've got someone in hell, can't defuse",
    "four A site, they took it, last one rotating",
    "one holding from heaven, has the Op angle on main",
    "two at A peek, one with Op",
    "one lurking through tree trying to flank",
    "one rotating through garden to flank us",
    "three A main, one is already on site",
    "two splitting A, one main one short through garden",
    "nobody A main, they all went B",
    "nothing A long, they gave us the space",
    "A is clear, no one for thirty seconds",

    # ================================================================
    # ASCENT — B site area
    # ================================================================
    "two B main",
    "one in logs",
    "three pushing B main",
    "one holding logs, one back B",
    "two B main, one more coming from market",
    "one on the triple box, post plant",
    "four B site, they stacked it",
    "one in the workshop, watching the B door",
    "two B, one logs one workshop",
    "last one hiding back B near the switch",
    "one B stairs, CT side",
    "three entered B, one is already planting",
    "two B main one shot between them",
    "one lurking through B market trying to catch our rotation",
    "B is clear, nobody B for thirty seconds",
    "nothing B, they went A",
    "one holding behind boathouse wall",
    "two B main, they've got a Jett with the Op on B",
    "three on B site already, last two rotating from CT",

    # ================================================================
    # ASCENT — mid area
    # ================================================================
    "two top mid",
    "one catwalk",
    "three mid, two top one bottom",
    "one in pizza, watching the market push",
    "two mid, one tiles one catwalk",
    "one hiding in the subroza spot",
    "three going through mid towards catwalk",
    "one holding from mid cubby",
    "two walking through tiles, slow push",
    "nobody mid, they committed A",
    "mid is open, they gave it",
    "one lurking mid, separate from main push",
    "two mid, one on catwalk one crossing to pizza",

    # ================================================================
    # HAVEN — A site
    # ================================================================
    "two A long",
    "one A short, sewer side",
    "three going A long",
    "one holding from heaven, A tower",
    "two A, one long one short",
    "last one is in hell, under A tower",
    "four A long, full send",
    "one camping at the A cubby long",
    "two A long, both have rifles",
    "one Heaven, watching both A long and short with Op",
    "three A, heaven and hell both covered",
    "one at A link, cutting our rotation",
    "two A long, one is already one shot",
    "nothing A, haven gave it up",

    # ================================================================
    # HAVEN — B site
    # ================================================================
    "two B main Haven",
    "one holding back B, gong side",
    "three B, rushing through mid doors",
    "one at B pillars, close angle",
    "two B site, they've taken it",
    "one behind the B box",
    "three B, one gong two pillars",
    "last one defusing B",
    "two B site, one is planting",
    "one lurking A link from B side",

    # ================================================================
    # HAVEN — C site and garage
    # ================================================================
    "two C long",
    "one in garage",
    "three C long, full push",
    "one holding nest above garage",
    "two C, one long one short through garage",
    "one on the C platform",
    "four C long, they stacked C hard",
    "one at C link, rotating to B",
    "two garage, one nest one inside",
    "last one somewhere C long, one shot",
    "three garage, pushing into C short",
    "one C lobby, not committed yet",
    "nothing C, they rotated mid",
    "nobody garage, free to push",
    "one holding from logs, C site",
    "two C plat, post plant angles",

    # ================================================================
    # SPLIT — A site
    # ================================================================
    "two A main Split",
    "one on the ramps",
    "three going A ramps",
    "one holding A heaven, A tower",
    "two A, one main one ramps",
    "one on A rafters, watching from behind",
    "three A, heaven covered, one lurking screens",
    "one at screens, holding A main angle",
    "two A heaven, both up there",
    "last one hiding in the flowerpot",
    "one under heaven, A site",
    "four A, they committed hard",
    "one holding elbow at screens exit",
    "two A main, mid vent rope might have a third",
    "nothing A ramps, they're all B",

    # ================================================================
    # SPLIT — B site
    # ================================================================
    "two B main Split",
    "one in B garage Split",
    "three pushing B garage",
    "one B heaven, top of the tower",
    "two B, one heaven one site",
    "one hiding B hell, has the rope",
    "three B, heaven garage and back site",
    "last one is deep B alley",
    "one B heaven watching garage cross",
    "two B site, planted, playing post",
    "one on the double box B site",
    "four B, they stacked B",
    "nothing B garage, they pushed A",
    "one playing aggressive garage, watch left",
    "two B main, both walking slow",

    # ================================================================
    # SPLIT — mid
    # ================================================================
    "two top mid on Split",
    "one in mail room",
    "three mid on Split, contesting top",
    "one hiding in orange, Split mid",
    "two mid Split, one top one bottom",
    "one in the Split mid cubby",
    "nobody Split mid, they went straight B",
    "one in sewer rotating from A to mid on Split",
    "two bottom mid, taking vents on Split",

    # ================================================================
    # PEARL — A site
    # ================================================================
    "two A main Pearl",
    "one in A art, flanking from mid",
    "three pushing A main",
    "one holding A link close",
    "two A, one main one art",
    "one hiding in A dugout",
    "three A, link and dugout covered",
    "last one is in A flowers",
    "one at A cafe, post plant",
    "two A main, both one shot",
    "four A, full execute A",
    "one at A secret, playing off the window",
    "nothing A main, they went B",
    "one lurking through A art from mid",
    "two A main, one with Op one with Vandal",

    # ================================================================
    # PEARL — B site
    # ================================================================
    "two B main Pearl",
    "one on B ramp",
    "three B main, rushing",
    "one B tower, has the angle on main",
    "two B, one ramp one tower",
    "one in B hall",
    "three B, tower hall and screen",
    "last one defusing B site",
    "one lurking through B link from mid",
    "two B, planted default, playing post plant",
    "one hiding behind B radianite boxes",
    "four B, they hit B hard",
    "nothing B main, free push",
    "two B main walking slowly",
    "one B screen, holding peek",

    # ================================================================
    # PEARL — mid
    # ================================================================
    "two mid doors",
    "one in mid plaza",
    "three pushing mid",
    "one holding from mid top",
    "two mid, one top one shops",
    "nothing mid plaza, they committed A",
    "one lurking mid connector going for our flank",
    "two mid, contesting the orb",
    "one at mid doors, defender holding early",

    # ================================================================
    # LOTUS — A site
    # ================================================================
    "two A root",
    "one holding A main",
    "three A, root and main",
    "one at A top, heaven side",
    "two A main, one is pushing for the drop",
    "last one in A hut, post plant",
    "one at A link, watching the B door wall",
    "three A, they hit A main",
    "one hiding A cubby near the stairs",
    "two A, one high box one pillar",
    "nothing A root, they opened B",
    "one coming through A door rotating shortcut",

    # ================================================================
    # LOTUS — B site
    # ================================================================
    "two B pillars",
    "one holding B upper",
    "three B main",
    "one on the B default, post plant",
    "two B, one upper one site",
    "last one lurking B link",
    "nothing B, they stacked A",
    "one holding close B link, gonna flank",
    "three B, they broke the wall, coming through A link",
    "two B pillars, walking in",

    # ================================================================
    # LOTUS — C site
    # ================================================================
    "two C main",
    "one at C mound",
    "three C long, rushing",
    "one holding C bend",
    "two C, one mound one bend",
    "one at C waterfall, defender rotating",
    "three C, they stacked C site",
    "last one is C hall, playing post plant",
    "one at C gravel, watching site",
    "four C, they committed C hard",
    "nothing C, all B this round",
    "one rotating through the C door shortcut",
    "two C, one playing off C link to CT",

    # ================================================================
    # BREEZE — A side
    # ================================================================
    "two A main Breeze",
    "one holding A hall",
    "three A, rushing A main",
    "one on A elbow",
    "two A, one hall one elbow",
    "last one deep A site",
    "one holding from A cave",
    "three A, pushed through A main hard",
    "nothing A, they went mid",
    "two A, one with Op on the long angle",

    # ================================================================
    # BREEZE — B side
    # ================================================================
    "two B main Breeze",
    "one holding B pillar",
    "three B rushing Breeze",
    "one on B tower Breeze",
    "two B Breeze, one main one tower",
    "last one defusing B on Breeze",
    "nothing B Breeze, they stacked A",
    "three B site, planted, playing post",
    "one lurking through B tunnel",
    "two B, both rifles",
    "one holding back B, can't push",

    # ================================================================
    # BREEZE — mid
    # ================================================================
    "two mid",
    "one holding mid nest",
    "three mid, rushing",
    "nothing mid, they went straight sites",
    "one mid, peeking for info",
    "two mid going for the split",

    # ================================================================
    # FRACTURE — A site
    # ================================================================
    "two A hall",
    "one holding A rope",
    "three going A, split from both spawns",
    "one at A link cutting CT",
    "two A, one hall one drop",
    "last one A heaven top site",
    "one hiding in A dish area",
    "three A, two hall one dropped from top",
    "nothing A hall, they rode the zip to B",
    "one at A door crossing, watch for sand",
    "two A main, one already up the rope",

    # ================================================================
    # FRACTURE — B site
    # ================================================================
    "two B main Fracture",
    "one at B arcade",
    "three B, split from B arcade and main",
    "one holding B tower",
    "two B, one tower one arcade",
    "last one hiding B tree side",
    "nothing B, they flipped to A on the zip",
    "one B generator, post plant",
    "three B pushing from B arcade hard",
    "two B main, both no armor, eco rush",

    # ================================================================
    # ICEBOX — A site
    # ================================================================
    "two A main Icebox",
    "one holding A belt",
    "three A Icebox, pushing hard",
    "one in A rafters, top",
    "two A Icebox, one belt one site",
    "last one A nest",
    "one on A pipes, elevated angle",
    "nothing A Icebox, they stacked B",
    "two A main, one shot between them on Icebox",
    "three A site Icebox, took it, planted default",

    # ================================================================
    # ICEBOX — B site
    # ================================================================
    "two B main Icebox",
    "one holding B orange",
    "three B Icebox pushing",
    "one on B yellow",
    "two B Icebox, one orange one yellow",
    "last one defusing B Icebox",
    "nothing B Icebox, free to plant",
    "three B Icebox, stacked hard",
    "one lurking B spawn stairs",
    "two B site Icebox, planted, playing post",

    # ================================================================
    # BIND — A side
    # ================================================================
    "two A main Bind",
    "one holding showers",
    "three A Bind, two main one showers",
    "one at A short Bind",
    "last one in A lamps",
    "two A Bind, one with Op playing main angle",
    "nothing A Bind, they went B",
    "one lurking through the A tp",
    "three A main Bind, rushing",
    "two A Bind, both pushing showers",
    "one deep A site, post plant under lamps",

    # ================================================================
    # BIND — B side
    # ================================================================
    "two B main Bind",
    "one in hookah",
    "three B Bind, hookah and main",
    "one holding elbow B on Bind",
    "two B hookah, both coming in",
    "last one defusing B on Bind",
    "nothing B hookah, they faked",
    "three B Bind, one hookah two main",
    "one lurking through the B tp",
    "two B main Bind, walking slow",
    "one on B long Bind, waiting",

    # ================================================================
    # SUNSET — A side
    # ================================================================
    "two A main Sunset",
    "one holding A lobby on Sunset",
    "three A Sunset pushing",
    "one at A mid link Sunset",
    "last one on A site Sunset",
    "nothing A Sunset, they stacked B",
    "two A Sunset, one shot each",

    # ================================================================
    # SUNSET — B side
    # ================================================================
    "two B main Sunset",
    "one holding B market Sunset",
    "three B Sunset pushing hard",
    "last one defusing B Sunset",
    "nothing B Sunset, went A",
    "two B main Sunset, full buy",

    # ================================================================
    # ABYSS — both sites
    # ================================================================
    "two A main Abyss",
    "one holding A bridge",
    "three A Abyss, bridge and main",
    "two B main Abyss",
    "one at B cliff edge",
    "last one is B site Abyss",
    "nothing A Abyss, they committed B",

    # ================================================================
    # CORRODE — both sites
    # ================================================================
    "two A main Corrode",
    "one in the flooded path",
    "three B pushing Corrode",
    "last one B site Corrode",
    "nothing A Corrode, all B",

    # ================================================================
    # COMPOUND / MULTI-LOCATION (cross-map, cross-site)
    # ================================================================
    "two A one B",
    "three A two B",
    "they're split, two going A two going B",
    "one A main one B main and one lurking mid",
    "two on each site, they split five ways",
    "three A two rotating B through mid",
    "four A one B anchor",
    "two B one A one mid, total four",
    "they split perfectly, two and two and one mid",
    "five A, full stack",
    "five B, they all went B",
    "three A one B, think one is lurking still",
    "two A long two C long on Haven, nobody B",
    "three C two A, Haven, B is open",
    "A and B both getting hit at the same time, two each",
    "one main one rotating through link, they're splitting site",
    "two heaven one site, hard to clear",
    "three pushing one lane and one lurking behind us",
    "two from front one flanking from CT, pinch",
    "four site one entry-fragged, three alive on site",

    # ================================================================
    # COUNT VARIETY — exact numbers, approximations, slang
    # ================================================================
    "five B, full rush B",
    "three and two, three A two B",
    "couple of them A main",
    "like four of them just rotated B",
    "both of them B, last two",
    "one guy left, he's somewhere site",
    "a pair pushing mid",
    "the whole team is A, give them nothing",
    "it's just one, don't panic",
    "three alive, two of them are on site",
    "four of them committed, only one mid",
    "just the two of us and there's three of them site",
    "there's only one but he's one shot",
    "one guy, full HP, no armor",
    "two left, one A one B, split for the retake",
    "last man, he's somewhere in heaven I think",
    "one down already, four of them pushing",
    "all five are coming A, full send",

    # ================================================================
    # NEGATIVE INFO callouts (also relay-worthy)
    # ================================================================
    "nobody A main",
    "nothing mid for thirty seconds",
    "B is empty, they abandoned it",
    "they gave us A, no contact",
    "nothing short, nobody took short at all",
    "no one mid the whole round",
    "C clear, nobody C long",
    "they didn't take garage, it's free",
    "nothing B long, given",
    "A main is clear, pushed up and nothing",
    "nobody heaven this round, they didn't contest up",
    "mid open, they defaulted sites only",
    "nothing A lobby, they skipped it",
    "no contact B for forty five seconds",
    "they haven't touched mid, it's ours",

    # ================================================================
    # DAMAGE + POSITION combo (position-count focus with damage)
    # ================================================================
    "one A main, I hit him sixty",
    "two B main, I tagged the lead one eighty",
    "one heaven, hit him forty through the smoke",
    "two site, both lit, I got em both",
    "one mid, dinked him, he's one shot",
    "three A, I hit one for ninety, two others full health",
    "one B long, tagged him a hundred and ten, no armor",
    "two CT side, I hit one for fifty",
    "one garage, I got him for forty head",
    "one lurker, tagged him sixty five through the wall",
    "two hookah, hit both of them, one is low",
    "last one site, I dinked him, someone clean it up",
    "one A peak, hit him eighty, he's one shot",
    "three pushing, I traded one, two more full hp",
    "one heaven, hit him thirty through smoke, still alive",

    # ================================================================
    # ELEVATION / HIGH GROUND callouts
    # ================================================================
    "one heaven A",
    "two top B tower",
    "one upper platform C",
    "one rafters A",
    "one on top of box",
    "two heaven, one upper one lower platform",
    "one B tower watching down",
    "one high ground, A top on Lotus",
    "one on the elevated, can't push yet",
    "two in rafters, B side",
    "one boosted up to the high angle",
    "one on top of logs C site",
    "three heaven, they own high ground",
    "one off-angle heaven, not the usual spot",
    "two upper site, they own elevation",
    "one dropped from heaven to hell",
    "last one playing hell under heaven",
    "someone in hell, can't see them from site",
    "one just jumped down from B tower",

    # ================================================================
    # MOVEMENT / DIRECTION callouts (position + action)
    # ================================================================
    "two pushing A main, they're rushing",
    "one walking mid slowly",
    "three rotating B fast",
    "one lurking through sewer to flank",
    "two holding angles, passive play",
    "three entered site already",
    "one flanking through CT",
    "two rotating off A to B through mid",
    "one peeking mid from garage",
    "three walking in single file B main",
    "two rotating and they're fast",
    "one dropping from heaven onto site",
    "three entered from two angles simultaneously",
    "one climbing the rope in B hell",
    "two jiggle peeking main, not committing",
    "one shoulder peeking mid, fishing for info",
    "three exploding site, coming all at once",
    "two fell back off site, resetting",
    "one flank incoming from behind us",
    "three pushing and one of them is boosted",

    # ================================================================
    # SPIKE / PLANT position callouts (position-count emphasis)
    # ================================================================
    "they're planting A",
    "spike down A main side",
    "planted B default",
    "spike is A, one defending it",
    "two sitting on spike, can't defuse",
    "spike B, three on site defending",
    "planted deep A, toward CT",
    "spike A, two of them holding from heaven",
    "one defusing B, two covering him",
    "spike down, two left, one heaven one hell",
    "planted for main, they're playing post behind boxes",
    "spike C on Haven, two defending, one rotating",
    "planted B site, one playing tower one playing hall",
    "spike is A, last one playing from garden",
    "they planted open, no cover, go defuse",

    # ================================================================
    # PHRASING VARIETY — register from snap to conversational
    # ================================================================
    "two B",
    "three A",
    "last heaven",
    "one mid",
    "site",
    "four pushing",
    "one shot B long",
    "yo there are two of them in A main already",
    "bro three guys just ran into B hookah",
    "they're stacked A, like four maybe all five",
    "I can see two in mid, one is lurking I think",
    "dude someone is in my logs, I can't move",
    "watch out there's one playing off-angle in heaven",
    "I'm telling you there are three in garage right now",
    "one guy holding the Op from B tower, careful",
    "they've got both heaven and hell covered, we're cooked",
    "two of them in catwalk, one has already crossed to tree",
    "I saw four going B but one might have peeled off mid",
    "someone is in that corner, I heard footsteps",
    "three rotating B, they're going fast, no time",
    "I peeked and I can confirm two on site, minimum",
    "checked mid, nothing there, safe to cross",
    "two B main both no armor, eco rush incoming",
    "one guy holding from a weird off-angle, not the usual spot",
    "three of them are just camping on site waiting for us",
    "both of the last ones are on site, close together",
    "they split, two A three B and they hit simultaneously",
    "one is holding the entry, second one is deep site",
    "got info from cam, two B main one rotating",
    "drone spotted three in A main, they're about to execute",
    "two in mid and they've got smoke ready, expect execute",
    "one playing the cubby, one in the open, different angles",
    "arrow landed, shows two B, one A, and one mid",
    "seekers went for three of them in B main",
    "cam caught one rotating CT toward B, heads up",
    "haunt revealed two on site, already planted",
    "tracked two through the wall, they're in my lane",

    # ================================================================
    # FIRST-PERSON OWNED POSITIONS (our teammates)
    # ================================================================
    "our Jett is holding A heaven",
    "our Sova is in mid with recon up",
    "our Killjoy is anchoring B",
    "our Cypher is watching from cam at A main",
    "I'm holding B main, one guy left",
    "we've got two anchoring A, three rotating B",
    "our Viper is playing off site B",
    "our last two are on site, holding for retake",
    "I'm in heaven, I've got eyes on two of them",
    "our Fade is lurking mid CT side",
    "we've got one player in every lane right now",
    "our guys are split, three A two B",
    "I'm the only one left on site",

    # ================================================================
    # ENEMY POSITION PHRASING — ownership clarity
    # ================================================================
    "their entry is already on site",
    "their Jett is in heaven",
    "their lurker is mid, separate from main push",
    "their anchor is still on A, he's the last one",
    "their whole team rotated B",
    "their Sova is using drone in mid",
    "their Omen just TPs into heaven",
    "their Killjoy is holding B from off-site",
    "their Reyna is pushing alone, second site",
    "their Chamber has an Op at B tower",
    "their team all went A except one anchor B",
    "their Yoru teleported into our flank",
    "their last one is somewhere in CT, can't find him",
    "their entry died, four of them left on site",
    "their Fade was on mid but rotated A after haunt",

    # ================================================================
    # TIME / ROUND PHASE + POSITION
    # ================================================================
    "two A main at round start",
    "they're taking mid early, two already",
    "three committed site with thirty seconds left",
    "one lurking for two minutes now",
    "spike down, twenty seconds, one defending",
    "three site with ten seconds on spike",
    "one peeking with five seconds on clock",
    "last one, spike's at thirty, he's site",
    "they rushed at fifteen seconds, full stack B",
    "two holding for the last ten seconds",
    "one camping with spike at five seconds",
    "they've been camping heaven for a full minute",
    "nobody contested mid until forty seconds in",
    "they just committed A at the one minute mark",
    "three site, spike planted, playing for time",

    # ================================================================
    # CLUTCH / LAST-ONE scenarios
    # ================================================================
    "last one, he's A somewhere",
    "final guy, somewhere mid I think",
    "one left, he's in heaven",
    "last man alive on their team, lurking CT",
    "one left and he's defusing",
    "it's just him now, holding B main",
    "last player, no idea where he is",
    "one left, heard him walking A long",
    "final enemy, he's camping somewhere site",
    "last guy, played off the spike, careful",
    "one remaining, he pulled back to CT",
    "last two on their side, both site",
    "final two, one heaven one hell, can't get in",
    "last one alive, buying time at B main",
    "their last player is in a ninja spot",

    # ================================================================
    # ECONOMY / WEAPON INTEL + POSITION
    # ================================================================
    "two A main both Vandals, full buy",
    "three B main, eco round, pistols",
    "two mid, one has Op on the long angle",
    "four A, rifles and heavy shields",
    "last one site, has an Op, be careful",
    "two B, both on Spectre, half buy",
    "three pushing A, two rifles one Op",
    "one heaven with Op, can't peek at all",
    "two mid, one Marshal one Vandal",
    "three site, they're on eco, might rush",
    "one A main, eco player, just a Sheriff",
    "two B main no armor, glass cannon setup",
    "one lurking, full buy, dangerous",
    "four A, they're on eco, rush incoming",
    "one holding B with the Op, ECO but still a threat",

    # ================================================================
    # RELAY-PHRASED (tell my team / let them know / etc.)
    # ================================================================
    "tell my team two A main",
    "let my squad know three B pushing",
    "tell my teammates one is lurking mid",
    "let them know four on site already",
    "tell my team last one heaven",
    "tell them two B one A",
    "let my team know they split the map",
    "tell my teammates one is holding with an Op",
    "tell my team two lurkers, one mid one CT",
    "let them know full five B rush",
    "tell my squad three site, planted, playing post",
    "tell my team they stacked A, nobody B",
    "let them know one player is camping the spike",
    "tell my teammates the guy in heaven is one shot",
    "tell them last one somewhere short",
    "let my squad know two in garage approaching B",
    "tell my team one is defusing right now",
    "tell them three A two B, they split evenly",
    "let my team know mid is clear, free to rotate",
    "tell my teammates four committed site, last one lurking",
    "tell them one playing off-angle heaven, watch out",
    "let my squad know B is empty, fake B rotate",
    "tell my team the lurker is behind us through CT",
    "tell them one on site, one shot, someone push",
    "let my team know three A last seen, they might rotate",

    # ================================================================
    # EXTENDED: LOTUS / BREEZE / FRACTURE additional variety
    # ================================================================
    "one at A root watching the door",
    "two A root one A main, Lotus three man hit",
    "three A Lotus, came through the rotating door shortcut",
    "one sitting A top on Lotus, rope up there",
    "two B pillars one B upper, Lotus B stack",
    "one just broke the wall, A link open on Lotus",
    "three C Lotus, came from C mound angle",
    "one at C bend waiting for us",
    "two C Lotus, one mound one bend, they have the angles",
    "one lurking C waterfall, haven't committed yet",
    "one A hall Fracture, long entry",
    "two A, one dropped top site one came A main, Fracture",
    "one holding sand on Fracture A",
    "one at A gate watching Fracture A dish",
    "three B arcade Fracture, rushed",
    "one on B tower Fracture watching main",
    "two B Fracture, one tree side one generator",
    "two A Breeze, long corridor, one Op angle",
    "one in A cave Breeze, peeking elbow",
    "three A Breeze, they committed main",
    "two B Breeze, tower and pillar covered",
    "one holding far B tower Breeze",
    "three mid Breeze, they own mid nest",

    # ================================================================
    # EXTENDED: HAVEN multi-site complexity
    # ================================================================
    "one A long one C long, Heaven split pressure",
    "three C two B on Haven",
    "two garage one nest, Haven C side stacked",
    "nobody C, nobody B, they five stacked A on Haven",
    "two A link rotating to B, Haven",
    "one lurking C link trying to cut off CT on Haven",
    "three C one B anchor one A lurker, Haven full spread",
    "four C on Haven, rare all-in C",
    "one sitting Nest above Haven garage",
    "two at Haven mid doors, controlling pivot",

    # ================================================================
    # EXTENDED: ASCENT mid-site complexity
    # ================================================================
    "one at A peek, another crossing to catwalk, Ascent",
    "two catwalk Ascent, contesting mid to A",
    "one tiles, one pizza, they split Ascent mid",
    "one hiding subroza spot on Ascent",
    "three Ascent A, heaven generator and hell all covered",
    "two Ascent B, logs and back boathouse",
    "one workshop Ascent, playing the B switch",
    "last one B alley Ascent, CT side",

    # ================================================================
    # EXTENDED: SPLIT elevation and rope calls
    # ================================================================
    "one climbing the A rope on Split, vulnerable",
    "one going through sewer A toward mid on Split",
    "two A heaven Split, they own the top",
    "one in the A rafters watching from behind, Split",
    "three A, cleared ramps, going up Split",
    "two B, B heaven and back site Split",
    "one in B hell Split, has the rope to heaven",
    "one riding vent rope toward A tower from mid, Split",

    # ================================================================
    # EXTENDED: PEARL corridor calls
    # ================================================================
    "one at Pearl A restaurant holding early",
    "two A Pearl, restaurant and main",
    "one A dugout Pearl, can't defuse",
    "one A secret Pearl, window angle",
    "two B Pearl, ramp and screen",
    "one B hall Pearl, flanking post-plant",
    "one B tunnel Pearl, going for tower",
    "two mid doors Pearl, defender early hold",
    "one mid connector Pearl, rotating defender water",
    "three B Pearl, stacked tower hall and screen",

    # ================================================================
    # EXTENDED: ICEBOX and BIND additional calls
    # ================================================================
    "two A belt Icebox",
    "one A nest Icebox, high angle",
    "three A Icebox, both lanes plus rafters",
    "one B orange Icebox, watching corner",
    "two B yellow Icebox, playing post plant",
    "one A main Bind, Op waiting at the corner",
    "three A Bind, main and showers both pushed",
    "one hookah Bind, sat in there",
    "two B Bind, both from long not hookah",
    "last one lurking through tp Bind, watch out",

    # ================================================================
    # EXTENDED: UTILITY SCAN position reveals
    # ================================================================
    "recon dart hit, shows two on B site",
    "drone scanned A main, one defender holding wine",
    "Fade haunt tracked two in mid, they're crossing",
    "seekers chased three into B main",
    "Cypher cam on heaven, one up there has an Op",
    "Tejo drone spotted two on A site already",
    "KAY/O knife hit mid, two suppressed in catwalk area",
    "Sova arrow landed B site, shows three already in",
    "Gekko thrash tagged one in the corner, they're A short",
    "Veto interceptor triggered, one rushing B main",

    # ================================================================
    # EXTENDED: STREAMER voice / slang register
    # ================================================================
    "bro there's literally five of them going B",
    "dude I can see three of them from here, all A",
    "nah nah there's one heaven and he's cooking us",
    "lowkey think one is still mid, didn't hear a rotate",
    "they're yapping around A, like two three somewhere there",
    "the whole lobby decided B this round",
    "one dude just won't leave garage, he's been there all round",
    "ight so one in heaven, one site, and I lost the third",
    "wait there's two? I only see one from here",
    "yo the last guy is definitely in one of these corners",
    "three came flying out of hookah, didn't expect that",
    "chat said two B main, I can confirm",
    "I am going to check heaven, I bet there's one there",
    "not sure if it's two or three, minimum two A",
    "one walked past mid and just ignored us, lurking hard",
]
