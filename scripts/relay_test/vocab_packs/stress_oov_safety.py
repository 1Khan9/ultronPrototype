"""Stress pack: out-of-roster addressee names (OOV safety, kind=negative).

Every item addresses a real human name -- NOT an agent name -- as the relay
target. The system must NOT relay these. The trigger word (tell/ask/let/relay)
is present but the addressee is a non-roster human name, so match_relay_command
should return None / no relay.

Hard sub-axes exercised:
  1. Direct address to a named person who is not an agent
     ("tell my Sarah to rotate", "ask Kevin for a heal")
  2. Common short names that partially overlap with agent-adjacent words
     (e.g., "sage"-sounding names like "Sage" ARE agents -- avoided here;
      this pack uses only names NOT on the roster)
  3. Mixed directive + human name (relay verb present but target is OOV)
  4. Possessive ("my Sarah", "our Jake", "their Mike")
  5. Names that sound like agents but are not: "Vance", "Phoebe", "Raina"
  6. Nicknames / diminutives: "Chris", "Chrissy", "Alex", "Xander"
  7. Name + agent-like role ("my Sarah is the IGL", "ask my Kevin he's the Sage")
  8. Multi-name compound ("tell Sarah and Marcus both to save")
  9. Non-English names common in the Valorant playerbase (Korean, Filipino,
     Spanish, Arabic-derived, etc.)
  10. Name as the ONLY qualifier after the relay verb (no team/squad/them)

All items are kind=negative: the pipeline must NOT relay them.
"""

ITEMS = [
    # =========================================================
    # BLOCK 1 — DIRECT "TELL [NAME]" WITH A HUMAN NAME
    # Simple structure: tell/ask + human name + directive.
    # No "my team" / "my squad" — the addressee IS the name.
    # =========================================================
    "tell Sarah to rotate B",
    "ask Kevin if he has his ult ready",
    "tell Marcus to fall back to spawn",
    "ask Jessica to smoke CT",
    "tell Tyler to push mid now",
    "ask Emily to anchor A site",
    "tell Brandon to save his gun",
    "ask Rachel to pop her ult",
    "tell Justin to flash the entry",
    "ask Amanda to cover B main",
    "tell Ryan to defuse the spike",
    "ask Megan to play retake",
    "tell Derek to lurk through mid",
    "ask Stephanie to drop me a rifle",
    "tell Eric to molly the plant spot",
    "ask Nicole to hold the corner",
    "tell Patrick to entry frag A",
    "ask Lauren to get info on B",
    "tell Chris to stop baiting and trade",
    "ask Brittany to watch the flank",
    "tell Anthony to peek short",
    "ask Jennifer to use her util now",
    "tell Kyle to go B",
    "ask Samantha to buy armor this round",
    "tell James to plant the spike",
    "ask Heather to play more passive",
    "tell Michael to handle the lurker",
    "ask Tiffany to push A with me",
    "tell Nathan to slow rotate to B",
    "ask Courtney to take the fight on short",

    # =========================================================
    # BLOCK 2 — POSSESSIVE "MY [NAME]" ADDRESSES
    # Streamer refers to teammate as "my Kevin" / "my Sarah"
    # =========================================================
    "tell my Sarah to rotate B now",
    "ask my Kevin to smoke the main",
    "let my Marcus know to fall back",
    "tell my Tyler to anchor the site",
    "ask my Emily for a shield drop",
    "tell my Brandon to hold the corner there",
    "let my Ryan know we are saving this round",
    "tell my Jessica to use her stuff now",
    "ask my Justin if he can flash me in",
    "let my Amanda know to peek short",
    "tell my Derek to set up on B",
    "ask my Stephanie if she has ult",
    "let my Eric know we are retaking",
    "tell my Megan to play crossfire with me",
    "ask my Patrick to grab the spike",
    "let my Lauren know to watch for the lurk",
    "tell my Chris to execute A",
    "ask my Nicole if she can wall it",
    "let my Kyle know to rotate mid",
    "tell my Nathan to buy a rifle this round",

    # =========================================================
    # BLOCK 3 — "OUR [NAME]" POSSESSIVE
    # =========================================================
    "tell our Jake to push now",
    "ask our Melissa to smoke the entry",
    "let our Travis know to rotate to B",
    "tell our Caitlin to drop the Phantom",
    "ask our Dylan to plant the spike",
    "let our Brittney know we are eco",
    "tell our Connor to anchor A",
    "ask our Haley if she can flash mid",
    "let our Jordan know to hold the site",
    "tell our Madison to take the 1v1",
    "ask our Hunter to use his ult now",
    "let our Kayla know to play retake",
    "tell our Zach to entry B",
    "ask our Amber to anchor this site",
    "let our Cody know we are full buy",
    "tell our Brianna to buy a Spectre",
    "ask our Logan to cover the flank",
    "let our Morgan know to fall back",
    "tell our Austin to peek short early",
    "ask our Alexis to get info on mid",

    # =========================================================
    # BLOCK 4 — "THEIR [NAME]" / WRONG TEAM REFERENCE
    # Streamer refers to an enemy by human name (not agent role).
    # =========================================================
    "ask their Mike to stop eco rushing",
    "tell their David to come out of that corner",
    "ask their Chris to stop Opping",
    "tell their Robert to please stop peeking me",
    "ask their Jason to save his ult next round",
    "tell their Adam to stop lurking through mid",
    "ask their Steve to quit spamming utility",
    "tell their Daniel to stop baiting his team",
    "ask their Matt to stop holding that off-angle",
    "tell their Alex to rotate off B already",

    # =========================================================
    # BLOCK 5 — NAMES PHONETICALLY ADJACENT TO AGENT NAMES
    # These are NOT agent names but could confuse a matcher:
    # "Vance" (not Viper), "Jenna" (not Jett), "Raina" (not Reyna),
    # "Phoebe" (not Phoenix), "Brimley" (not Brimstone), "Soph" (not Sova),
    # "Isla" (not Iso), "Brianna" (not Breach), etc.
    # =========================================================
    "tell Jenna to rotate B immediately",
    "ask Raina if she has her ult",
    "tell Vance to play the corner on A",
    "ask Phoebe to buy a rifle this round",
    "tell Soph to push mid on my call",
    "ask Nadia to anchor the site",
    "tell Isla to take the duel",
    "ask Bri to smoke the entrance",
    "tell Ome to anchor B site",
    "ask Aster to drop me a gun",
    "tell Harb to flash mid for me",
    "ask Clover to smoke CT",
    "tell Viper's sister Anna to hold the corner",
    "ask Brimley to buy a Phantom",
    "tell Sage's player Jake to wall it",
    "ask Kay to flash the entry for us",
    "tell Fade's friend Alex to go in first",
    "ask Ged to send something in to help",
    "tell Teo to anchor B long",
    "ask Sov to use his ult now",
    "tell Rayne to flash the corner",
    "ask Fiona to smoke elbow",
    "tell Ves to sentinel the flank",
    "ask Deedee to set up her trap",
    "tell Hayden to peak short",
    "ask Camden to entry this round",

    # =========================================================
    # BLOCK 6 — RELAY VERB + NAME + SPECIFIC VALORANT DIRECTIVE
    # Stress-test where the directive itself is a valid relay payload
    # but the target is a human name, not a group/team.
    # =========================================================
    "tell Josh to two B long",
    "ask Kayla to rotate off A",
    "tell Mike one is lurking mid, pass it on",
    "ask Sarah three are pushing B main",
    "tell Tyler they have the spike",
    "ask Jason to say one shot at market",
    "tell Chris last one site defusing",
    "ask Amber spike is down on A site",
    "tell David two are heaven on Haven A",
    "ask Rachel three are walking B lobby",
    "tell Kyle one shot one is at CT",
    "ask Nicole play retake after the smoke fades",
    "tell Cody we need a full buy next round",
    "ask Madison save this round and full buy next",
    "tell Dylan they are eco, rush them",
    "ask Haley their Killjoy has lockdown",
    "tell Travis rotate mid on my mark",
    "ask Brittany flash B main in three",
    "tell Morgan plant the spike for B default",
    "ask Connor defend B their whole team is coming",

    # =========================================================
    # BLOCK 7 — INTERNATIONAL NAMES (Korean, Filipino, Vietnamese,
    # Spanish, Arabic, Turkish, Russian, Brazilian)
    # =========================================================
    "tell Junho to rotate B",
    "ask Soyeon to anchor the site",
    "tell Minjun to buy a Vandal this round",
    "ask Jisoo to push mid with me",
    "tell Seoyeon to fall back to spawn",
    "ask Hyunwoo to flash A main in",
    "tell Eunji to plant the spike",
    "ask Minseok to use his ult now",
    "tell Jaemin to smoke CT before we push",
    "ask Chaewon to hold the corner on B",
    "tell Paolo to rotate to A immediately",
    "ask Nico to anchor elbow",
    "tell Carlo to buy a Spectre this round",
    "ask Migs to plant for B default",
    "tell Bea to fall back and save",
    "ask Tito to smoke mid for us",
    "tell Miko to flash long on my call",
    "ask Diether to entry B site",
    "tell Dani to hold back-site",
    "ask Carlo to get info on B main",
    "tell Minh to rotate B",
    "ask Thanh to anchor the site",
    "tell Hung to smoke CT",
    "ask Linh to push mid",
    "tell Quang to fall back",
    "ask Nguyen to buy a Phantom",
    "tell Diego to rotate A",
    "ask Rodrigo to smoke elbow",
    "tell Alejandro to anchor B site",
    "ask Valentina to flash main in",
    "tell Mateo to plant the spike",
    "ask Sebastian to hold the corner",
    "tell Ivan to push mid with me",
    "ask Dmitri to anchor A main",
    "tell Nikita to smoke CT before we go",
    "ask Alexei to use his ult now",
    "tell Yusuf to rotate B",
    "ask Omar to anchor the site",
    "tell Kareem to buy a Vandal",
    "ask Khalid to flash entry",
    "tell Mehmet to hold B main",
    "ask Emre to smoke CT",
    "tell Lucas to entry A now",
    "ask Gabriel to anchor B",
    "tell Pedro to smoke the choke",
    "ask Felipe to rotate mid",

    # =========================================================
    # BLOCK 8 — NAMES AS FUNCTION WORD CONFUSION
    # Names that could be parsed as non-name tokens:
    # "Will", "May", "Grace", "Hope", "Joy", "Cole", "Lance"
    # =========================================================
    "tell Will to anchor the site",
    "ask May to smoke the entrance",
    "tell Grace to rotate B now",
    "ask Hope to use her ult",
    "tell Joy to fall back to spawn",
    "ask Cole to buy a rifle this round",
    "tell Lance to push mid early",
    "ask Grant to hold B long",
    "tell Chase to entry A site",
    "ask Wade to anchor elbow on Haven",
    "tell Luke to flash main in three",
    "ask Drew to plant the spike",
    "tell Mark to defuse it",
    "ask Scott to rotate to B",
    "tell Neil to buy armor this round",
    "ask Reed to smoke CT",
    "tell Dale to take the peek",
    "ask Kent to play retake",
    "tell Ray to anchor mid",
    "ask Glen to entry with me",

    # =========================================================
    # BLOCK 9 — MULTI-NAME COMPOUNDS
    # "Tell Sarah and Marcus both to save" — two human names.
    # =========================================================
    "tell Sarah and Marcus to save this round",
    "ask Kevin and Tyler to push B together",
    "tell Emily and Brandon to anchor A",
    "ask Rachel and Justin to rotate mid",
    "tell Jessica and Ryan to smoke CT",
    "ask Megan and Derek to fall back",
    "tell Stephanie and Eric to buy armor",
    "ask Lauren and Patrick to flash entry",
    "tell Nicole and Chris to hold the corner",
    "ask Brittany and Anthony to retake together",
    "tell Kyle and James to push now",
    "ask Heather and Michael to play retake",
    "tell Nathan and Tiffany to anchor B",
    "ask Courtney and Samantha to get info mid",
    "tell Josh and Kayla to buy rifles",
    "ask Mike and Sarah to rotate together",
    "tell Jake and Melissa both to fall back",
    "ask Travis and Caitlin to smoke elbow",
    "tell Dylan and Haley to use their ults",
    "ask Logan and Morgan to play crossfire",

    # =========================================================
    # BLOCK 10 — NAME + "HE IS THE [AGENT]" PHRASING
    # Tries to bait the matcher into treating the name as a relay group
    # because an agent name appears in context.
    # =========================================================
    "tell my Kevin, he's playing Jett, to dash out",
    "ask Sarah, she's on Sage, to wall it now",
    "tell Marcus, our Viper main, to pit the site",
    "ask Tyler, the one playing Sova, to send a recon dart",
    "tell Emily, our Brimstone, to drop stims",
    "ask Brandon, he's Killjoy, to set up on B",
    "tell Ryan, he's on Omen, to smoke CT",
    "ask Jessica, she's our Skye, to send the dog in",
    "tell Justin, playing Breach, to flash the entry",
    "ask Amanda, she is Cypher, to set a trap there",
    "tell Derek, our Fade main, to haunt them",
    "ask Stephanie, on Gekko, to send Wingman in",
    "tell Eric, our Reyna, to devour after the kill",
    "ask Megan, playing Chamber, to anchor mid with his Op",
    "tell Lauren, she's Neon, to sprint entry",
    "ask Chris, our Iso, to use his contingency",
    "tell Kyle, playing Clove, to smoke after death",
    "ask Nathan, on Tejo, to armageddon the site",
    "tell Patrick, our Harbor, to high tide the entry",
    "ask Nicole, she's Vyse, to set up her razor wire",

    # =========================================================
    # BLOCK 11 — NAME AS SOLO QUALIFIER AFTER RELAY VERB
    # No "my team" / "my squad" / "them" -- just the name alone.
    # =========================================================
    "tell Andrew to rotate B",
    "ask Brian to smoke CT",
    "tell Cameron to anchor site",
    "ask Donna to fall back",
    "tell Edward to use his ult",
    "ask Fiona to push mid",
    "tell Gary to buy a Phantom",
    "ask Hannah to flash entry",
    "tell Ian to plant the spike",
    "ask Janet to hold the corner",
    "tell Kevin to rotate off A",
    "ask Linda to buy armor",
    "tell Matt to entry frag",
    "ask Nancy to smoke elbow",
    "tell Oliver to anchor B",
    "ask Pamela to retake with me",
    "tell Quinn to get info mid",
    "ask Robert to save his gun",
    "tell Sandra to push short now",
    "ask Thomas to lurk mid",
    "tell Ursula to smoke the main entry",
    "ask Victor to anchor CT",
    "tell Walter to flash in three",
    "ask Xander to plant the spike",
    "tell Yasmin to fall back and save",
    "ask Zoe to buy a Vandal this round",
    "tell Aaron to rotate B site",
    "ask Bella to anchor the corner",
    "tell Carl to entry with me",
    "ask Diana to smoke heaven",

    # =========================================================
    # BLOCK 12 — GAMER-TAG-STYLE REAL NAMES
    # Names that read like usernames but are real human first names.
    # =========================================================
    "tell SteveGaming to rotate B",
    "ask Tyler2K to anchor the site",
    "tell ProJohn to smoke mid entry",
    "ask ChrisXL to flash the corner",
    "tell MikeRush to plant the spike",
    "ask JasonPro to rotate off A",
    "tell RyanXP to buy armor this round",
    "ask BrianGG to anchor B main",
    "tell KyleElite to lurk mid",
    "ask MaxGaming to entry A site",
    "tell TomCool to smoke CT before we go",
    "ask JamieXO to hold the corner",
    "tell AlexFPS to push short early",
    "ask JordanPro to retake with me",
    "tell NoahKill to flash entry in three",
    "ask LiamFrag to plant the spike",
    "tell EthanR to anchor B site",
    "ask OwenXD to use his ult now",
    "tell CalebGG to fall back to spawn",
    "ask HenryT to rotate mid on my call",

    # =========================================================
    # BLOCK 13 — FEMALE NAMES ACROSS DIVERSE ORIGIN
    # Stress: pipeline should not relay even for female names.
    # =========================================================
    "tell Aria to rotate B now",
    "ask Priya to anchor the site",
    "tell Fatima to smoke the main entry",
    "ask Yuna to flash CT in three",
    "tell Amara to plant the spike",
    "ask Sofia to rotate off A",
    "tell Ingrid to buy armor this round",
    "ask Keiko to anchor B long",
    "tell Nadia to lurk through mid",
    "ask Chiara to entry A with me",
    "tell Akira to hold the corner on B",
    "ask Zanele to use her ult now",
    "tell Leila to fall back to spawn",
    "ask Astrid to buy a Phantom",
    "tell Freya to push short early",
    "ask Mei to smoke elbow before we push",
    "tell Naomi to anchor CT site",
    "ask Dahlia to flash mid for us",
    "tell Carmen to retake with the team",
    "ask Valentina to anchor B main",
    "tell Hana to rotate on my call",
    "ask Ines to buy a Vandal this round",
    "tell Mira to lurk through mid link",
    "ask Zara to push A short now",
    "tell Elif to smoke CT for the push",
    "ask Dilnoza to anchor B site",
    "tell Sung-hee to rotate A immediately",
    "ask Ji-yeon to anchor the corner",
    "tell Aiko to smoke mid before we go",
    "ask Sakura to flash entry on my mark",

    # =========================================================
    # BLOCK 14 — HYPHENATED / COMPOUND HUMAN NAMES
    # =========================================================
    "tell Mary-Jane to anchor B site",
    "ask Jean-Pierre to smoke the entry",
    "tell Li-Wei to rotate mid",
    "ask Anne-Sophie to flash CT in three",
    "tell Jin-Ho to buy armor this round",
    "ask María-Fernanda to anchor the corner",
    "tell Karl-Heinz to push short early",
    "ask Min-Ji to entry A site now",
    "tell Juan-Carlos to plant the spike",
    "ask Sung-Jin to rotate off A",
    "tell Hyun-Soo to anchor B long",
    "ask Ye-Ji to use her ult now",
    "tell Pierre-Louis to fall back to spawn",
    "ask Ha-Eun to lurk through mid",
    "tell Chan-Ho to smoke CT before we push",

    # =========================================================
    # BLOCK 15 — SAME NAME AS AN AGENT BUT WITH DIFFERENT CASING /
    # PHONETIC VARIANT (to stress exact-match vs fuzzy matching)
    # Note: we avoid the EXACT agent names. These are close but distinct.
    # =========================================================
    "tell Jetta to anchor B site",
    "ask Pheonix to smoke the entry",
    "tell Raize to push mid",
    "ask Reynard to anchor A main",
    "tell Yorick to smoke CT",
    "ask Noel to anchor the corner",
    "tell Isadora to flash entry",
    "ask Waylander to plant the spike",
    "tell Brimley to anchor B",
    "ask Vincenzo to smoke mid entry",
    "tell Omenix to rotate off A",
    "ask Astrid to anchor CT site",
    "tell Harboro to flash main in three",
    "ask Clova to smoke heaven on Haven",
    "tell Sovana to use her recon",
    "ask Breacher to flash A main",
    "tell Skyler to anchor B site",
    "ask Kaytie to rotate mid",
    "tell Fader to lurk through mid",
    "ask Gekkos to entry A site",
    "tell Tejero to push short early",
    "ask Cyrus to get info on B",
    "tell Sagelee to wall it",
    "ask Killjoe to anchor the site",
    "tell Chamberlain to anchor elbow",
    "ask Deadlocke to hold B long",
    "tell Vyson to set up on B",
    "ask Vetox to play for crossfire",

    # =========================================================
    # BLOCK 16 — "ASK [NAME] FOR X" PHRASING
    # Explicit ask-for-resource structure with human name.
    # =========================================================
    "ask Kevin for a heal",
    "ask Sarah for a rifle drop",
    "ask Marcus for a shield",
    "ask Tyler for backup",
    "ask Jessica for a smoke",
    "ask Emily for utility support",
    "ask Brandon for a Phantom drop",
    "ask Rachel for her ult",
    "ask Justin for a flash",
    "ask Amanda for spike",
    "ask Ryan for info on B",
    "ask Megan for cover",
    "ask Derek for a trade",
    "ask Stephanie for a revive",
    "ask Eric for the spike carrier",
    "ask Nicole for a wall",
    "ask Patrick for a stun",
    "ask Lauren for a drone",
    "ask Chris for a boost",
    "ask Brittany for backup entry",

    # =========================================================
    # BLOCK 17 — "LET [NAME] KNOW" PHRASING
    # =========================================================
    "let Sarah know we are saving this round",
    "let Kevin know to anchor B",
    "let Marcus know the spike is on A",
    "let Tyler know to rotate mid",
    "let Emily know they are pushing B",
    "let Brandon know to fall back now",
    "let Ryan know he is one shot",
    "let Jessica know to use her ult",
    "let Justin know to flash mid in three",
    "let Amanda know to plant the spike",
    "let Megan know we are full buying",
    "let Derek know one is lurking mid",
    "let Stephanie know to retake A",
    "let Eric know the spike is defused",
    "let Nicole know to anchor elbow",
    "let Patrick know two are rotating B",
    "let Lauren know to get info first",
    "let Chris know to peek short",
    "let Kyle know we are eco this round",
    "let Nathan know to rotate on my mark",

    # =========================================================
    # BLOCK 18 — "WARN [NAME]" PHRASING
    # =========================================================
    "warn Sarah they are flanking",
    "warn Kevin the Killjoy set up on B",
    "warn Marcus they are rushing A",
    "warn Tyler one has an Operator mid",
    "warn Emily they smoked both entries",
    "warn Brandon the spike is on B",
    "warn Ryan they are rushing through smoke",
    "warn Jessica the Reyna is in Empress",
    "warn Justin their Sage is walling entry",
    "warn Amanda they have three on A",
    "warn Megan the lurker is through mid",
    "warn Derek they have two rifles left",
    "warn Stephanie the KAY/O knife is active",
    "warn Eric they are defaulting this round",
    "warn Nicole their Jett is Opping mid",
    "warn Patrick the spike is about to detonate",
    "warn Lauren two are on the retake",
    "warn Chris they have lockdown on site",
    "warn Kyle their Clove is not dead yet",
    "warn Nathan the flank is coming from garage",

    # =========================================================
    # BLOCK 19 — STREAMER-TO-CHAT NATURAL LANGUAGE (NARRATION)
    # These are private thoughts / stream narration that happen to
    # mention a human name. They must NOT relay.
    # =========================================================
    "I should tell my Sarah to rotate but she never listens",
    "I would ask Kevin to heal me but we have no Sage",
    "Marcus keeps baiting and I want to tell him to stop",
    "Tyler is holding the wrong angle, I keep trying to tell him",
    "Emily is going to plant alone and I wish I could warn her",
    "Brandon never saves when I ask him to, drives me crazy",
    "I keep asking Ryan to fall back but he does not",
    "telling Jessica anything is pointless this game honestly",
    "I told Justin to anchor but he rotated anyway",
    "every time I ask Amanda to buy armor she does not",
    "wish I could tell Megan to stop peeking the Op",
    "Derek never listens when I say to save the rifle",
    "I wanted to warn Stephanie but she already died",
    "I tried to tell Eric to play retake but he went elsewhere",
    "Nicole would benefit from anchoring here but she does not know",
    "Patrick needs to learn to anchor but I cannot tell him how",
    "I keep reminding Lauren to watch the flank but to no avail",
    "if I could tell Chris anything it would be to stop entry fragging alone",
    "Kyle should be buying armor but I cannot make him",
    "I think Nathan should rotate but I will not say anything",
    "telling this random Brittany on my team anything is hopeless",
    "Jordan keeps walking into the smoke and I cannot believe it",
    "I am going to say something to Alex after the round about his positioning",
    "they sent me into a match with some random named Oliver and I do not trust him",
    "my friend Mike is in my lobby, maybe I should tell him something before the round",

    # =========================================================
    # BLOCK 20 — RELAY TRIGGER WORD PRESENT BUT NAME IS THE ONLY TARGET
    # The hardest cases: relay prefix present, name present, no "team/squad/them"
    # =========================================================
    "relay to Zach that we are saving",
    "relay to Amber that they are pushing B",
    "relay to Connor that the spike is on A",
    "relay to Haley that we are full buying next",
    "relay to Dylan that one is lurking through mid",
    "relay to Madison that their Killjoy has lockdown",
    "relay to Hunter that two are on the rotate",
    "relay to Kayla that three are walking B",
    "relay to Cody that we need to retake",
    "relay to Brianna that one is one shot at elbow",
    "relay to Logan that we are eco this round",
    "relay to Morgan that the spike is defusing",
    "relay to Austin that rotate B now",
    "relay to Alexis that two are heaven on Ascent",
    "relay to Jordan that they are on a force buy",
    "relay to Taylor that flash entry in three",
    "relay to Cameron that plant for B main",
    "relay to Bailey that anchor elbow they are coming",
    "relay to Peyton that last one is in B site",
    "relay to Avery that the Reyna is in Empress",

    # =========================================================
    # BLOCK 21 — NAMES COMMONLY USED IN VALORANT LOBBIES
    # Stream-authentic real names seen in ranked games.
    # =========================================================
    "tell Jin to rotate B now",
    "ask Kai to anchor the site",
    "tell Zion to smoke CT before we push",
    "ask Jaylen to flash entry for me",
    "tell Darius to plant the spike",
    "ask Caden to rotate off A",
    "tell Bryce to anchor B main",
    "ask Colton to use his ult now",
    "tell Gage to fall back to spawn",
    "ask Tanner to buy armor",
    "tell Brady to push short early",
    "ask Trevor to anchor mid",
    "tell Carter to entry frag A",
    "ask Parker to get info on B main",
    "tell Cooper to retake with me",
    "ask Spencer to smoke the entry",
    "tell Blake to anchor B site",
    "ask Preston to lurk through mid",
    "tell Lane to play for retake",
    "ask Weston to flash in three two one",
    "tell Garrett to push A on my call",
    "ask Griffin to anchor elbow",
    "tell Miles to buy a Vandal this round",
    "ask Cole to rotate to B",
    "tell Dean to anchor the corner",
    "ask Wade to plant the spike",
    "tell Rhett to smoke CT",
    "ask Brett to anchor B long",
    "tell Kurt to entry with me",
    "ask Scott to lurk mid this round",

    # =========================================================
    # BLOCK 22 — STREAMER CORRECTING THEMSELVES (meta-narration)
    # The streamer initially addresses a human name then catches themselves.
    # =========================================================
    "wait tell Sarah, no actually tell my whole team to rotate B",
    "ask Kevin, no I mean my squad, to full buy",
    "tell Marcus to smoke -- actually I will relay it to everyone",
    "I should ask Tyler, I mean my team, to save this round",
    "tell Emily, wait she is in voice, never mind I will relay it",
    "remind Brandon to anchor B -- actually no relay that to the whole team",
    "I want to tell Ryan but -- relay to my team rotate mid",
    "ask Jessica, actually just tell everyone to buy armor",
    "let Justin know -- wait let me just relay this to the squad",
    "I keep telling Megan but maybe I should just relay to everyone",

    # =========================================================
    # BLOCK 23 — DOUBLE-BARREL: HUMAN NAME + VALID RELAY CALLOUT
    # The human name target disqualifies it but the callout is valid.
    # Hardest case: valid callout content, wrong addressee.
    # =========================================================
    "tell Kevin two are B long",
    "ask Sarah three are pushing A main",
    "tell Marcus one shot at mid market",
    "ask Tyler spike is down on B site",
    "tell Emily last one is defusing",
    "ask Brandon rotate B they are stacking A",
    "tell Ryan their Killjoy has lockdown",
    "ask Jessica save this round and full buy next",
    "tell Justin flash A main in three",
    "ask Amanda anchor elbow they are coming short",
    "tell Megan one is lurking through mid",
    "ask Derek two are rotating off B",
    "tell Stephanie three are heaven on Haven A",
    "ask Eric one is one shot no armor",
    "tell Nicole plant for B main and hold",
    "ask Patrick their Jett has Op on mid",
    "tell Lauren two are walking garage",
    "ask Chris they are on eco rush them",
    "tell Kyle their Sage is walling B entry",
    "ask Nathan full buy they have rifles",

    # =========================================================
    # BLOCK 24 — STREAMER ASKS HUMAN-NAMED TEAMMATE A QUESTION
    # Not a relay command -- streamer wants Kenning to ask a specific
    # named human a direct question.
    # =========================================================
    "ask my Kevin what his ult status is",
    "ask Sarah if she can flash me into A",
    "ask Marcus if he has enough credits for a rifle",
    "ask Tyler where he is positioned on the map",
    "ask Emily if she burned her ultimate last round",
    "ask Brandon if he can set up on B",
    "ask Ryan if he has any util left",
    "ask Jessica if she saw that lurker mid",
    "ask Justin if he can cover my flank",
    "ask Amanda what she is buying this round",
    "ask Megan if she can anchor A while we push B",
    "ask Derek if he heard movement near CT",
    "ask Stephanie if she has her ult for the retake",
    "ask Eric what his health is at",
    "ask Nicole if she can wall the entry before we go",
    "ask Patrick if he is in position to entry",
    "ask Lauren if she spotted the lurker",
    "ask Chris if he has spike",
    "ask Kyle if we are winning the economy",
    "ask Nathan if he is ready to retake B",

    # =========================================================
    # BLOCK 25 — STREAMER ADDRESSING A SPECTATOR / VIEWER BY NAME
    # Clearly NOT a relay; addressed to chat, not to teammates.
    # =========================================================
    "tell my viewer Josh that we are pushing B",
    "ask my chat buddy Sarah if she thinks I should save",
    "for Kevin watching: we are going full buy next round",
    "shoutout to Marcus in chat, we just executed A perfectly",
    "Tyler in the chat is asking why I am not buying armor",
    "Emily keep clipping that, we just retook B with no util",
    "my boy Brandon watching this knows exactly why I rotated",
    "Ryan you are in chat right now, you see what my team does",
    "Jessica from my stream team, that was the play I was describing",
    "Justin I know you are watching and you see why I had to rotate",
    "Amanda from the discord, yes that was my teammate not listening",
    "Derek you are my mod, you know I told them to save",
    "Stephanie catching the VOD later: yes I told them to anchor",
    "Eric from my community, this is why we lost the round",
    "Nicole watching: they never listen when I tell them to rotate",
    "Patrick you are a subscriber and you saw that I called it",
    "Lauren moderating my chat, please clip that for me",
    "Chris my editor, we will cut this section for the highlight",
    "Kyle my teammate in the other game, yes I am losing",
    "Nathan my Discord friend, send me that clip later",

    # =========================================================
    # BLOCK 26 — COACHING / ANALYST NAMES (stream context)
    # Streamer references their coach or analyst by name.
    # =========================================================
    "my coach David said I should tell them to play retake",
    "ask my coach Alex what rotation I should call",
    "my analyst Sandra told me to relay this but I am doing it myself",
    "coach Mike says to tell the team to save",
    "my trainer Tom says ask the team what they are buying",
    "tell my analyst Brian the team is not following calls",
    "ask my coach Robert what strat we should run next round",
    "my mentor Kevin told me to always relay economy calls",
    "ask my IGL coach Jason what he thinks of this rotation",
    "my coach Daniel would tell them to anchor B but I am not sure",

    # =========================================================
    # BLOCK 27 — FIRST-NAME-ONLY STREAM SHOUTOUTS THAT SOUND LIKE RELAYS
    # =========================================================
    "shoutout to Marcus, tell the team to rotate",
    "thanks Eric now tell them to smoke CT",
    "hi Brittany, relay to my team they are eco",
    "good one Tyler, ask my squad to full buy",
    "nice catch Lauren, let my team know they are rotating",
    "Kevin called it, tell my team two are B long",
    "Sarah was right, relay to my squad to anchor elbow",
    "Josh confirmed it, tell them one is lurking mid",
    "exactly what Amanda said, ask my team to retake",
    "Drew you saw it too, tell my team last one is defusing",

    # =========================================================
    # BLOCK 28 — RARE / UNIQUE NAMES UNLIKELY TO APPEAR IN ANY ROSTER
    # =========================================================
    "tell Bartolomew to anchor B site",
    "ask Persephone to smoke CT",
    "tell Cornelius to flash the entry",
    "ask Bartholomew to plant the spike",
    "tell Theodora to anchor the corner",
    "ask Montgomery to rotate off A",
    "tell Cordelia to use her ult now",
    "ask Reginald to buy armor this round",
    "tell Hildegard to anchor B long",
    "ask Archibald to entry A site",
    "tell Wilhelmina to fall back to spawn",
    "ask Thaddeus to get info on B main",
    "tell Millicent to lurk through mid",
    "ask Octavia to smoke the entrance",
    "tell Alistair to anchor elbow",
    "ask Seraphina to flash mid in three",
    "tell Phineas to plant the spike",
    "ask Isadora to anchor CT site",
    "tell Leonora to buy a Phantom",
    "ask Ferdinand to push short on my call",
]
