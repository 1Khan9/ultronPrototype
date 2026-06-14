"""Vocab pack: morale, hype, tilt management, and team encouragement relay lines.

Domain: Everything the streamer says to fire up, calm down, refocus, or emotionally
direct their teammates — delivered via Ultron relay. Covers the full realistic
distribution of morale comms in ranked Valorant:

  - Round-win celebration (GG, nice, let's go, keep the momentum)
  - Clutch acknowledgment (from minor to insane)
  - Comeback language (down rounds, 9-3, match point)
  - Tilt recognition and de-escalation calls
  - Pre-round pump-up / aggression ignition
  - Post-death acknowledgment ("good try", "shake it off", "my bad")
  - Player-specific praise and callouts by role (entry, IGL, support, anchor)
  - Pistol round and eco-win hype
  - ACE / team ace celebration
  - Round reset after a bad round
  - Morale for a close map (12-12 OT, 11-13 deficits)
  - Clutch-or-kick pressure (meme but real)
  - Anti-tilt ("no rage comms", "clean it up")
  - Encouragement for specific agents and plays
  - Regional/slang-heavy register variation
  - Long-winded streamer morale speeches (IGL style)
  - Short punchy hype variants

All items are KIND=relay: the streamer is commanding Ultron to relay the line
to teammates. Covers the full register spectrum from two-word terse to multi-clause
paragraph-style IGL speeches. No near-duplicates.
"""

ITEMS = [
    # ---------------------------------------------------------------------------
    # ROUND WIN — SHORT / PUNCHY VARIANTS
    # ---------------------------------------------------------------------------
    "tell my team nice round",
    "let my team know good round, keep it up",
    "tell the guys GG round, stay focused",
    "tell my teammates that was clean, let's go again",
    "tell my team that was a great round, let's build on it",
    "let them know well played, same energy next round",
    "tell my team nice work, do not drop off now",
    "tell the guys that was a perfect round, do not get complacent",
    "tell my team good shit, keep the momentum going",
    "let my team know nice round, we are cooking",
    "tell my teammates beautiful round, stay hungry",
    "tell my team clean kills, let's go",
    "tell the guys WP, keep that up",
    "let my team know good half, stay locked in",
    "tell my team that was crisp, let's run it back",

    # ---------------------------------------------------------------------------
    # ROUND WIN — MEDIUM REGISTER
    # ---------------------------------------------------------------------------
    "tell my team we won that clean, smokes were perfect, push that feeling into the next round",
    "let my team know that round was great, everyone did their job, let's not overthink it",
    "tell my teammates that was a textbook round, let's execute the same read next time",
    "tell my team we won on a force, now we full buy and we close this out",
    "let them know we won the eco, do not tilt their economy, save the rifles for the full buy round",
    "tell my team good entry fragging, second entry followed well, that is how we want to do it every round",
    "tell the guys that clutch plant was the difference, communication was on point",
    "let my team know we read their rotation perfectly, they are going to adjust so stay sharp",
    "tell my teammates one round at a time, we just won one, let's win another",
    "tell my team we won the post-plant correctly, no one peeked, let's do it exactly the same",
    "let them know that is three rounds in a row, they are tilting, let's press",
    "tell my team nice frag, nice trade, nice plant, that was a complete round",
    "tell my team we held that retake with no utility left, that is just grit, good job",
    "let my teammates know we converted that 3v5, let's not think too hard about it, ride the wave",

    # ---------------------------------------------------------------------------
    # ROUND WIN — LONGER IGL-STYLE SPEECHES
    # ---------------------------------------------------------------------------
    "tell my team that was a strong round, the entry was confident, the second bodies followed fast, and the plant was in a good spot, let's replicate that",
    "let my team know our communication that round was clean, every kill got called, every rotation was confirmed, that is why we won, keep talking",
    "tell my teammates I know that round felt lucky but it was not, we played patient, we made them use their utility first, that is what wins rounds, keep doing it",
    "tell my team we are up four rounds now and their economy is broken, they have to force next round, do not give them a thrifty, play anti-eco correctly",
    "let my team know we converted from behind and that is the hardest thing to do, it means we are better than our score right now, trust that",
    "tell my teammates that team ace was not a fluke, everyone found their duel, everyone took the trade, that is what good Valorant looks like",
    "tell my team we just won three on the bounce, I can feel them tilting over there, let's not let up for even one round",

    # ---------------------------------------------------------------------------
    # CLUTCH ACKNOWLEDGMENT — MINOR
    # ---------------------------------------------------------------------------
    "tell my team nice clutch",
    "let my team know good clutch, you held it together",
    "tell the guys nice 1v1 close",
    "tell my teammates you closed that out, well done",
    "let my team know solid play under pressure, that was clutch",
    "tell my team that was a clean 1v2, respect",
    "tell the guys I knew you had that 1v1, nice",
    "let my teammates know good job staying calm in the 1v2",

    # ---------------------------------------------------------------------------
    # CLUTCH ACKNOWLEDGMENT — MAJOR / INSANE
    # ---------------------------------------------------------------------------
    "tell my team that was an insane clutch, 1v3 from a bad position, absolute filth",
    "let my team know that was one of the best clutches I have seen, you reset, you played patient, you cleaned it up",
    "tell my teammates that 1v4 just saved our economy and our confidence, that was massive",
    "tell my team that clutch was cracked, you heard two of them, tapped the spike to bait the third, and still closed it, that is elite",
    "let them know the 1v3 with no util left is not luck, that is game sense and nerve, incredible round",
    "tell my team that ace in the 1v5 was historic, do not downplay it, that is what ranked games are made of",
    "tell my teammates the 1v3 post-plant defuse with five seconds left is the most clutch thing I have ever seen in ranked, let's go",
    "tell my team that was unreal, you outdueled three of them with a Spectre on a force buy, that is a thrifty and a clutch in one round",
    "let my team know I had zero faith but you proved me wrong, that 1v2 on the spike was perfect, mad respect",
    "tell the guys when the clutch player says no comms, you go silent, you did that perfectly and he closed it, that is team discipline",

    # ---------------------------------------------------------------------------
    # ACE / TEAM ACE CELEBRATION
    # ---------------------------------------------------------------------------
    "tell my team nice ace, that was personal",
    "let my team know that ace was cold, every single one of them",
    "tell my teammates ace in a round we almost threw, that is character, good work",
    "tell my team that team ace was beautiful, everyone got one, no one died, that is a perfect round",
    "let my team know that team ace is worth more than the round win, it means we are completely in sync right now",
    "tell the guys team ace on a pistol round, they have no economy and no confidence, press this advantage hard",
    "tell my team that ace with a Guardian on a half buy is exactly what pocket Guardian is designed to do, nice read",
    "let my teammates know that four-man ace attempt turned into a team ace with the fifth entry, perfect timing, perfect trust",

    # ---------------------------------------------------------------------------
    # ECO WIN / THRIFTY HYPE
    # ---------------------------------------------------------------------------
    "tell my team we just won on eco, their economy is shattered now",
    "let my team know we eco-fragged their full buy, that is a thrifty, beautiful",
    "tell my teammates we won with Spectres and Ghosts against a full buy, that is what clean execution does",
    "tell my team we won the eco rush, do not slow down, they did not expect it and now they are scared",
    "let them know that thrifty keeps their economy broken for two more rounds, we are about to go on a run",
    "tell my team we saved our rifles and won the round anyway, we are going into next round at full buy with extra confidence",
    "tell the guys we just eco-fragged the Op Jett, she is going to play scared for three rounds now",
    "let my teammates know winning on a force when they expected a save is demoralizing for them, keep attacking their confidence",

    # ---------------------------------------------------------------------------
    # PISTOL ROUND HYPE
    # ---------------------------------------------------------------------------
    "tell my team let's win this pistol, first blood sets the tempo for the whole half",
    "let my team know pistol round is the most important round of the half, play it like it is match point",
    "tell my teammates win the pistol and we control the bonus round too, that is two rounds for free",
    "tell my team we just won the pistol, we bonus next, save the Spectre for second round and we are golden",
    "let them know we won the CT pistol, now we hold the bonus round and their economy never recovers this half",
    "tell my team good pistol round, do not throw the bonus, play clean and convert the double",
    "tell my teammates we lost the attack pistol but our defense is strong, we win the next one and reset the economy",
    "let my team know we lost the pistol on defense but a 4-1 first half is still completely fine, they have their own pistol to win on attack",

    # ---------------------------------------------------------------------------
    # COMEBACK LANGUAGE — 5-7 DEFICIT
    # ---------------------------------------------------------------------------
    "tell my team we are down by three but we have been here before, let's claw back one round at a time",
    "let my team know 5-7 is nothing, a 7-5 half is completely normal, reset your mentality",
    "tell my teammates forget the scoreboard for a second, we are going to play the next round, just the next round",
    "tell my team they got lucky on two rounds, that does not mean they are better than us, let's prove it",
    "let them know being down three rounds does not mean we have lost anything, we have twelve rounds this half, let's go win some",
    "tell my team one good round changes the whole vibe, let's get one and build from there",
    "tell my teammates I am not panicking at 4-8 because I have seen teams win from here, it takes belief and communication",
    "tell my team their confidence is peaking right now but we have been through worse, stay together and let's chip away",

    # ---------------------------------------------------------------------------
    # COMEBACK LANGUAGE — 9-3 CURSE / MAJOR DEFICIT
    # ---------------------------------------------------------------------------
    "tell my team we are at 3-9 but the 9-3 curse is real, stay composed and we can actually win this",
    "let my team know being down 3-9 at half sounds bad but I have seen it reversed, it starts with this pistol round",
    "tell my teammates 9-3 curse is a meme until it happens to you, they got complacent, let's make them regret it",
    "tell my team I know 4-8 feels hopeless but their shotcalling is going to fall apart when we win two in a row, get those two",
    "let them know mathematically we can still win this from down 3-9, it takes 10 rounds and we have 12 left, let's run it",
    "tell my team we are down 5-7 at half but we switch sides, this is our better side, we can absolutely come back",
    "tell my teammates I know we are down but I refuse to FF, we play it out and we make them earn every single round",
    "let my team know do not call FF, do not even think it, we play until the game ends, period",

    # ---------------------------------------------------------------------------
    # MATCH POINT / CLOSE-GAME LANGUAGE
    # ---------------------------------------------------------------------------
    "tell my team it is match point but nothing changes, play our game, play our round",
    "let my team know match point means every round matters but it has always meant that, nothing different",
    "tell my teammates we are one round from winning, do not get tight, play the round and let the result handle itself",
    "tell my team we have been at match point before, breathe, communicate, and close it out",
    "let them know we are at 12-11 match point, one round, one execute, let's end this",
    "tell my team 12-10 is not closed yet, convert this next round and it is done",
    "tell my teammates we are on match point, play fast, do not give them time to breathe or rally",
    "tell my team they are on match point not us, play like every round is winnable because it is",

    # ---------------------------------------------------------------------------
    # OVERTIME LANGUAGE
    # ---------------------------------------------------------------------------
    "tell my team it is 12-12, overtime, whoever wants it more wins this",
    "let my team know OT is essentially a coin flip unless one team is calmer, be the calmer team",
    "tell my teammates overtime means the game is completely even, all the score means nothing now, play for this round",
    "tell my team 12-12 is where character shows, let's show ours",
    "let them know we got to overtime from being down, that alone means we are the mentally stronger team",
    "tell my team in overtime everyone is nervous, control the nerves better than they do and we win",
    "tell my teammates OT pistol is everything, win this pistol and we ride the bonus straight to victory",
    "tell my team this is overtime, last set of rounds, leave it all on the map",

    # ---------------------------------------------------------------------------
    # TILT RECOGNITION AND DE-ESCALATION
    # ---------------------------------------------------------------------------
    "tell my team no rage comms, clean up the comms and let's focus",
    "let my team know the rage comms are making things worse, everyone quiet and we play the game",
    "tell my teammates I hear the frustration but we need clear heads right now, reset",
    "tell my team take a breath between rounds, venting does not win rounds, playing does",
    "let them know I know that was a bad round but throwing the comms makes it two bad rounds in a row",
    "tell my team do not go on tilt, the moment we tilt we hand them the game",
    "tell my teammates I understand the frustration, we all feel it, but we keep our composure and fix it",
    "tell my team we are tilting and they can hear it in our comms, lock it up",
    "let my team know elevated emotions equal degraded performance, calm down and play smart",
    "tell my teammates do not let one bad round become five, reset right now",
    "tell my team one at a time in comms, one person calling, everyone listening, that is how we fix this",
    "let them know the more you rage the worse you play, that is not an opinion that is a fact",
    "tell my team stop the blame comms, it does not matter whose fault it was, let's talk about the next round",
    "tell my teammates the argument about the last round can wait until after the match, right now we play",
    "tell my team no more negative comms, every call should be about the next play not the last play",
    "let my team know we play better when the comms are positive and short, let's get back to that",

    # ---------------------------------------------------------------------------
    # TILT MANAGEMENT — SPECIFIC PLAYER
    # ---------------------------------------------------------------------------
    "tell my team whoever is raging needs to mute mic for one round, reset and come back focused",
    "let my teammates know I get it, the whiff was painful, shake it off and take the next duel",
    "tell my team the entry died doing their job, that is what entry is supposed to do, do not get on them",
    "tell my teammates support your entry fragger even when they die, that is how the role works",
    "tell my team do not flame the IGL mid-round, if you disagree we talk after the round is over",
    "let them know the bottom fragger is trying, stop calling it out mid-game, you are making it worse",
    "tell my team everyone has bad rounds, one bad round does not define the player, move forward",
    "tell my teammates that was a rough trade but the intent was right, I would rather see that than no one trying",

    # ---------------------------------------------------------------------------
    # PRE-ROUND PUMP UP — AGGRESSION IGNITION
    # ---------------------------------------------------------------------------
    "tell my team let's be aggressive this round, take the angles, do not let them set up",
    "let my team know we are going in confident this round, do not second-guess anything",
    "tell my teammates this is our round, play like we believe it",
    "tell my team controlled aggression this round, early contact, early information",
    "let them know I want us to take mid control immediately this round and split from there",
    "tell my team we push at thirty seconds, take space, plant, play post-plant, simple",
    "tell my teammates be the aggressor, do not wait for them to come to us",
    "tell my team entry goes in hot, second body follows in two seconds, no gaps",
    "let my team know we are running the same execute we practiced, timing is everything, trust each other",
    "tell my teammates fast round, no hesitation, we end this before they have time to react",
    "tell my team first blood wins rounds, go get it",
    "let them know we take the early pick and then we decide, but we have to take that first contact",

    # ---------------------------------------------------------------------------
    # PRE-ROUND CALM / SLOW DOWN
    # ---------------------------------------------------------------------------
    "tell my team slow it down this round, play for information before we commit",
    "let my team know we are defaulting, get info, no one commits to a site without a call",
    "tell my teammates breathe, play patient, let them walk into us",
    "tell my team this round we play disciplined, no yolo peeks, no lone wolf pushes",
    "let them know we do not need to force anything, the clock is our friend on defense",
    "tell my team play passive and make them burn utility before we engage",
    "tell my teammates no early aggression this round, we wait for them to come to us and we punish it",
    "tell my team trust the setup, trust the comms, do not over-rotate from information",

    # ---------------------------------------------------------------------------
    # SPECIFIC AGENT / ROLE ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team great smokes, those were perfect, we could not have executed without them",
    "let my teammates know the flash timing was ideal, I walked in and they were blind, that is a perfect support round",
    "tell my team our Jett entry was fearless that round, she bought us the site, honor that",
    "tell my teammates the Sova recon bolt exposed three of them, that is why we won that round, great intel",
    "tell my team Sage wall at that exact moment saved two of us from the push, incredible read",
    "let my team know the Cypher cam spotted their rotate before it happened, that is the entire reason we won",
    "tell my teammates Killjoy turret got a damage call that confirmed their position, that is what the turret is for",
    "tell my team Breach fault line stunned two of them mid-push and we capitalized instantly, beautiful sync",
    "let them know the Viper wall cut site in half and they had nowhere to go, controller was perfect",
    "tell my team Skye dog flushed them out of that corner, exactly what the ability is for",
    "tell my teammates the Raze satchel entry was insane, she cleared two angles before anyone could react",
    "tell my team KAY/O knife suppressed three of them, we walked into a free fight, that is the best knife you can throw",
    "let my team know Fade haunt confirmed them before we pushed, that is information you cannot buy",
    "tell my teammates Reyna dismissed out of an unwinnable duel and lived, that is smart Reyna, not a feed",
    "tell my team Omen teleported at exactly the right moment, they never checked that angle",
    "let my team know Astra gravity well pulled two of them into the open, those kills were on the gravity well",
    "tell my teammates Clove stayed alive long enough to use Pick-me-up after dying and it swung the round",
    "tell my team Tejo armageddon landed on the exact plant spot, they could not defuse through it",
    "let my team know Gekko Wingman planted while we held the retake, that is the perfect Gekko play",
    "tell my teammates Deadlock annihilation caught their whole retake lineup, that is a round-winning ult",
    "tell my team Vyse shear cut off their rotation at the exact moment, that changed the outcome",
    "let my team know Veto evolution is charged, we use it on the next execute and they cannot hold site",
    "tell my teammates Chamber Tour de Force anchored B alone for 25 seconds, that bought us everything",
    "tell my team Harbor wall split their retake in half, they could not coordinate a push through it",
    "let my teammates know Iso Kill Contract removed their Jett before the execute, that fight was never fair",
    "tell my team Neon ran their whole team down with Overdrive active and got three, that is what Overdrive is for",
    "tell my teammates that Waylay refract play was disorienting for them and they walked into the angle",

    # ---------------------------------------------------------------------------
    # DEATH ACKNOWLEDGMENT / POST-DEATH ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team MB on the call, that one is on me",
    "let my teammates know my bad on the play, I misread the angle",
    "tell my team shake it off, the death was unlucky, the play was correct",
    "tell my teammates that peek was a coin flip and it did not go our way, no fault",
    "tell my team you died doing the right thing, the entry opened the site even if it cost us a player",
    "let them know the entry death was not wasted, second body should have followed faster and that is on us",
    "tell my team that trade was worth it, we swapped one for one in a fight they should have won",
    "tell my teammates the death stings but the buy was smart, we will have guns next round regardless",
    "tell my team do not think about the death, think about the retake, we still have four",
    "let my team know four alive on a retake is actually great, we can win this",
    "tell my teammates even with three alive we have utility, let's retake this clean",
    "tell my team it is a 2v4 but stranger things have happened, trust the setup",

    # ---------------------------------------------------------------------------
    # ROUND LOSS RECOVERY
    # ---------------------------------------------------------------------------
    "tell my team we reset after that, next round fresh",
    "let my team know one round at a time, we lost one, let's win the next",
    "tell my teammates forget that round, it is over, the only round that matters is this one",
    "tell my team that was a tough round, they hit us with a great execute, we adjust and move on",
    "let them know they caught us rotating, that is good play on their part, we tighten up and we will not fall for it again",
    "tell my team we got thrifty'd and that hurts but our economy is still fine, full buy next and we bounce back",
    "tell my teammates we lost the post-plant because we peeked, no more peeking post-plant, let the spike do the work",
    "tell my team we threw that round but throwing one round does not mean we throw the match",
    "let my team know I made a bad call and we paid for it, I am adjusting the read, trust me next round",
    "tell my teammates we gave up that round to save guns, that is not a loss that is a tactical decision",
    "tell my team losing the eco round is bad but not catastrophic, we full buy next and we reassert control",
    "let them know they hit us with a good flash execute, we adjust the defense angles and we hold the next one",

    # ---------------------------------------------------------------------------
    # TEAM COHESION / TRUST CALLS
    # ---------------------------------------------------------------------------
    "tell my team trust each other, we have been playing well together all game",
    "let my team know the comms are good, the reads are good, we just need to convert",
    "tell my teammates play for the team, not for the stat line, that is how we win",
    "tell my team do not go lone wolf, we are stronger when we stick to our roles",
    "let them know if we communicate and execute together there is not a team in this lobby that beats us",
    "tell my team support your entry, play your role, and trust the call",
    "tell my teammates we are a better team than our current score shows, believe that",
    "tell my team I would rather lose playing our game than win playing theirs",
    "let my team know this team is good enough to win this match, we just have to play like it",
    "tell my teammates the other team is not doing anything magical, we can replicate and counter every play they run",

    # ---------------------------------------------------------------------------
    # MOMENTUM MAINTENANCE
    # ---------------------------------------------------------------------------
    "tell my team keep the pressure on, they are starting to crack",
    "let my team know do not let up, close this out before they can reset",
    "tell my teammates we are on a run right now, match that energy",
    "tell my team they are tilting over there, I can hear it, press the advantage",
    "let them know they are making mistakes now, that is what a losing streak feels like, exploit it",
    "tell my team they called a timeout in their head, do not give them time to breathe",
    "tell my teammates our momentum is real, do not do anything to slow it down",
    "tell my team four in a row, fifth round has our name on it, play aggressive",
    "let my team know five-round streak and their economy is at zero, they are shell-shocked",
    "tell my teammates they are going to try something desperate now, read it and punish it",

    # ---------------------------------------------------------------------------
    # MENTAL FORTITUDE / BELIEF CALLS
    # ---------------------------------------------------------------------------
    "tell my team believe we can win this, that is not a cliche that is a requirement",
    "let my teammates know confidence is contagious, somebody set the tone",
    "tell my team play like you expect to win and your body does things your brain cannot explain",
    "tell my teammates we have won rounds from worse positions than this, I have seen it this match",
    "tell my team fear loses rounds before the fights even happen, no fear",
    "let them know I need everyone locked in, not just fragging, locked in mentally",
    "tell my team we win this if everyone plays one good round, that is all I am asking for",
    "tell my teammates when it is down to one of us, believe that one person is going to clutch it",
    "tell my team I trust every person on this team in a clutch, now let's put ourselves in positions where someone gets to prove it",
    "let my team know doubt is the only thing that can actually beat us right now",

    # ---------------------------------------------------------------------------
    # COMMUNICATION QUALITY CALLS
    # ---------------------------------------------------------------------------
    "tell my team communicate everything, even negative info, nothing in chat silence the voice comms",
    "let my team know the person with the best position should be calling, everyone else confirms",
    "tell my teammates quick calls, loud and clear, no mumbling the position in a live round",
    "tell my team call the damage fast, the number matters, do not just say you hit him",
    "let them know if you are dead say the position then go quiet, that is your last contribution and it matters",
    "tell my team one person talks during the clutch, everyone else holds",
    "tell my teammates confirm rotations out loud, if you do not say copy the IGL does not know you heard",
    "tell my team after a team fight, call what util you burned so we know what we have for post-plant",
    "let my team know if you are planting, say it, do not make the team guess",
    "tell my teammates the callout is only useful if it is fast, if the enemy moved you still call the original position and then update",

    # ---------------------------------------------------------------------------
    # SPECIFIC PLAY-TYPE ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team that one-tap with the Sheriff on a save round was absolutely filth",
    "let my teammates know the double swing worked perfectly, both of them were caught watching the same angle",
    "tell my team that no-scope on the marshal was the highlight of this match so far",
    "tell my teammates that off-angle caught three of them completely off guard, run it again next round",
    "tell my team the shoulder peek to bait the Op shot was brilliant, now we know where he is",
    "let them know the jiggle peek got them to waste the Op, now push before it reloads",
    "tell my team that lurk came through at the perfect moment, they were fully committed A when you hit B",
    "tell my teammates the fake rotate fooled them completely, they scrambled and we hit the open site",
    "tell my team the crossfire on their retake was exactly right, they had no angle to defuse safely from",
    "let my team know the ninja defuse at five seconds on the spike was the gutsiest play I have seen",
    "tell my teammates that fake defuse got the last one to peek and you punished it, textbook",
    "tell my team the bait worked, they traded the bait and you got the refrag, now plant",
    "let my team know the anti-flash counter-swing was timed perfectly, you waited for the flash to pop and then went",

    # ---------------------------------------------------------------------------
    # WEAPON AND ECONOMY ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team great Guardian play on the half buy, that pocket Guardian read was correct",
    "let my teammates know buying the Spectre on the force and winning the round was the right call",
    "tell my team the Marshal pick on the eco was elite, you do not need the Op to hold long",
    "tell my teammates that Sheriff one-deag on the eco is worth more than a rifle kill right now",
    "tell my team winning that round on a classic means we save our guns and their guns, great read",
    "let them know the Judge rush on their eco caught them completely off guard, aggressive eco buys win rounds",
    "tell my team we full buy next and this is where we take control of the scoreboard",
    "tell my teammates drop the Op to whoever holds long next round, protect the investment",

    # ---------------------------------------------------------------------------
    # ENVIRONMENTAL / TIMING READS
    # ---------------------------------------------------------------------------
    "tell my team they are burning time every round, they do not know what to do against our defense",
    "let my team know thirty seconds left and they have not committed, they are going to rush at fifteen",
    "tell my teammates watch for the late round lurker, they always send one through mid when the round slows",
    "tell my team their clock management is sloppy, they are going to force a bad play at ten seconds",
    "let them know we have time, do not rush the plant, make them come to us post-plant",
    "tell my team we control the pace this round, make them react to us for once",
    "tell my teammates at forty seconds if no contact go to plan B immediately, no hesitation",
    "tell my team if they default this round we attack mid first and steal the information",

    # ---------------------------------------------------------------------------
    # SPECIFIC AGENT MATCHUP ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team do not let their Jett set up on the Op, go deny her angles before she gets comfortable",
    "let my teammates know their Reyna feeds on kills so deny the duels and she is useless",
    "tell my team their Killjoy has Lockdown ready, do not execute into it without the knife up first",
    "tell my teammates their Cypher will have a cam on the default path, check it before you push",
    "tell my team their Fade nightfall is going to slow our execute, time our push around it",
    "let them know their Sage wall is designed to delay our entry, blast through it and do not slow down",
    "tell my team their KAY/O is going to throw a knife at round start, duck and push immediately after",
    "tell my teammates do not run at their Viper pit, play around it from outside and force them to come out",
    "tell my team their Brimstone has orbital strike and he is going to drop it on the default plant, plant off-site",
    "let my team know their Chamber is anchoring CT with a Tour de Force, he will not rotate until the last second",
    "tell my teammates their Omen is going to teleport behind us mid-execute, someone play flank watch",
    "tell my team their Breach is about to fault line through the wall, fall back or get stunned in the open",
    "let them know their Raze nade is going to clear heaven, do not be there when it hits",
    "tell my team their Iso kill contract only works if they can get you in the duel, do not accept it",
    "tell my teammates their Waylay refract is a rotation tool, if she disappears she is repositioning not retreating",
    "tell my team their Tejo armageddon will cover the spike, plant in an alternate spot and smoke the sightline",

    # ---------------------------------------------------------------------------
    # ROUND TYPE SPECIFIC HYPE
    # ---------------------------------------------------------------------------
    "tell my team we are going to run a split execute this round, trust the plan",
    "let my teammates know we slow execute this round, no rushing, just utility in sequence and walk onto site",
    "tell my team we fake A first, commit for five seconds, then rotate everything to B",
    "tell my teammates default this round and let's see what they give us before we commit",
    "tell my team we rush B this round, full five, no utility, pure speed",
    "let them know we eco rush this round, they will not expect it, and if we win we reset their economy",
    "tell my team late round this time, play for picks, do not force anything into a site before 40 seconds",
    "tell my teammates stack B this round, three anchor B and two fake A, make them guess",
    "tell my team we anti-strat them this round, every round they go A on their attack side, we stack A",
    "let my team know we play off their aggression this round, let them peek into us",

    # ---------------------------------------------------------------------------
    # FINAL STRETCH / MATCH CLOSING
    # ---------------------------------------------------------------------------
    "tell my team we are two rounds from the W, do not throw it away on a hero play",
    "let my team know we are this close, disciplined play closes the gap, sloppy play throws the lead",
    "tell my teammates play clean, play simple, we have won the hard way already, now let's finish it",
    "tell my team do not over-celebrate yet, wait until the Victory screen shows, play every round like the last",
    "let them know we have been in this position before and we know how to close, execute and do not deviate",
    "tell my team three rounds to go, no one makes a play that they cannot explain to me after the match",
    "tell my teammates this is the match, this is the moment, let's play Valorant",
    "tell my team lock in for these last rounds, we have earned the lead and we protect it",
    "let my team know whoever wants it more will win these last rounds, make sure it is us",

    # ---------------------------------------------------------------------------
    # GENERAL HYPE / MOMENTUM — VARIOUS REGISTERS
    # ---------------------------------------------------------------------------
    "tell my team let's gooooo",
    "let my team know that was sick, we are clicking right now",
    "tell my teammates W round, no notes",
    "tell my team no cap that was one of our best rounds all game",
    "let them know that was lowkey perfect, let's keep it up",
    "tell my team bro we are built different today",
    "tell my teammates sheeeesh that was cold, let's run it",
    "tell my team okay we are actually popping off right now",
    "let my team know different breed, let's go",
    "tell my teammates we are cooked no wait actually we cooked them, let's go",
    "tell my team that was disgusting in the best way possible",
    "let my team know certified banger of a round",
    "tell my teammates that was not it at first but then it was EXACTLY it, good recovery",
    "tell my team I was not worried for a second, obviously",
    "let them know we eat rounds like that for breakfast",
    "tell my team unreal game sense from everyone this round",
    "tell my teammates that was hard to watch for the first thirty seconds but the ending made up for it",
    "tell my team this is what a well-coordinated five-stack looks like right here",
    "let my team know if we play like this for twelve rounds straight we do not lose",
    "tell my teammates I am not going to overdo it but that was a really good round",

    # ---------------------------------------------------------------------------
    # SPECIFIC ROUND STATE — ATTACKER PUSH ACKNOWLEDGMENT
    # ---------------------------------------------------------------------------
    "tell my team great execute, we took site with all five alive, that is exactly how it should go",
    "let my teammates know we hit the site clean and planted in twenty seconds, they had no time to rotate",
    "tell my team the split worked, they could not cover both entries and we capitalized",
    "tell my teammates we faked them off A and they were still rotating when we planted B, great patience",
    "tell my team the slow execute drained all their utility before we pushed and we walked in for free",
    "let my team know that was a perfect A main push, flashes synced, second body followed, no one died on entry",
    "tell my teammates we hit the site from both angles simultaneously and they had no crossfire set up, perfect timing",
    "tell my team the contact execute was right, we had the info, we committed, we won",

    # ---------------------------------------------------------------------------
    # SPECIFIC ROUND STATE — DEFENDER HOLD ACKNOWLEDGMENT
    # ---------------------------------------------------------------------------
    "tell my team that was a great hold, we absorbed their execute and traded three, site is ours",
    "let my teammates know we played the passive hold perfectly, we made them use all their utility and then we punished",
    "tell my team we held B with two players for 30 seconds, that bought the anchor on A time to rotate and clean up",
    "tell my teammates the crossfire on site entry worked exactly as designed, they had nowhere to go",
    "tell my team we anticipated the lurker and shut it down early, good game sense",
    "let them know our anchor on A denied the site solo for an entire minute, unreal defensive play",
    "tell my team we dropped site and retook it with two people left, that is the whole defensive meta working",
    "tell my teammates we played for picks instead of committing to a site all round and it paid off with three quick kills",

    # ---------------------------------------------------------------------------
    # RETAKE HYPE
    # ---------------------------------------------------------------------------
    "tell my team we retake this, we have the utility and the numbers, trust the plan",
    "let my teammates know retake is on, one from main one from CT, pinch them on the spike",
    "tell my team smoke the default, utility on their angles, flash in and clean it up",
    "tell my teammates the retake is winnable, do not give up the round because they planted",
    "let them know a 4v2 retake should not be this hard, play it properly and we win",
    "tell my team we retake off the spike timer, do not rush it, wait for them to over-peek",
    "tell my teammates coordinated retake, do not go in alone, wait for everyone to be in position",
    "tell my team the retake was textbook, we isolated duels and cleaned up the angles one by one",

    # ---------------------------------------------------------------------------
    # INDIVIDUAL PLAYER SHOUTOUTS (GENERIC ROLES)
    # ---------------------------------------------------------------------------
    "tell my team the entry fragger was fearless this round, that is the energy we need every round",
    "let my teammates know the lurker came through at the perfect moment, that is high IQ play",
    "tell my team our anchor held for forty seconds alone, give them credit",
    "tell my teammates the IGL called the right play at the right time, trust the calls",
    "tell my team the support player bought us the round with their flashes, frags are not the only way to win",
    "let them know the information player gave us perfect intel all round and that is why we won",
    "tell my team the person who played time correctly post-plant saved us from a bad retake, smart play",
    "tell my teammates the player who saved their rifle in a lost round is the reason we full buy next, that is discipline",

    # ---------------------------------------------------------------------------
    # SELF-AWARENESS / FEEDBACK LOOP
    # ---------------------------------------------------------------------------
    "tell my team we keep losing the same angle, let's adjust and not give it to them a third time",
    "let my teammates know their lurker has gotten us twice now, we need a flank watch every round",
    "tell my team we are predictable on attack, they know our default, change it up this round",
    "tell my teammates we need to vary our timing, we are executing at the same second every round",
    "tell my team our post-plant positions are leaking, they know where we play after the plant",
    "let them know the same smoke lineup is not working anymore, they have learned to wait it out",
    "tell my team we need to start taking earlier map control, we are playing reactive every round",
    "tell my teammates I want more aggression from the initiator this round, use the utility early not late",

    # ---------------------------------------------------------------------------
    # HUMOR / LIGHT BANTER WITHIN MORALE (relay-appropriate)
    # ---------------------------------------------------------------------------
    "tell my team we almost threw that round so badly but we did not, somehow, let's go",
    "let my teammates know that round was ugly but the W is a W regardless of how it looked",
    "tell my team we will review the VOD on that one but right now it counts as a round win, moving on",
    "tell my teammates I do not know how we won that, do not ask, take it and play the next round",
    "tell my team that was way too close for comfort but we survived, let's not do that again",
    "let them know we won a round we had no business winning and I am choosing to believe in us now",
    "tell my team the chaos worked this time, next time let's try to win with a plan",
    "tell my teammates someone is going to say NT after we throw this round so let's not throw it",
    "tell my team I had a genius call and it worked, I will not tell you what the genius call was until after we win",
    "let my team know that was dumb but inspired and I love it, do it again",

    # ---------------------------------------------------------------------------
    # SPORTSMANSHIP / END OF HALF / END OF MATCH
    # ---------------------------------------------------------------------------
    "tell my team good half, they played well but so did we",
    "let my teammates know GH everyone, we take this momentum into the second half",
    "tell my team great match, they were a good team, we still won",
    "tell my teammates GG no matter how this ends, we played together and that means something",
    "tell my team NT on that round, their clutch was genuinely impressive, let's respond",
    "let them know they played a good game but we played a better one, GG",
    "tell my team win or lose we played our game, I am proud of this team",
    "tell my teammates that was a hard-fought match and we showed character, walk away with your head up",

    # ---------------------------------------------------------------------------
    # CLUTCH SITUATIONS — SPECIFIC AGENT
    # ---------------------------------------------------------------------------
    "tell my team Jett in the 1v3 with knives, she does not need backup, she needs silence",
    "let my team know Phoenix run it back, he can take risks, just play quiet",
    "tell my teammates Reyna in the 1v2 with Empress active is practically unfair, she can close this",
    "tell my team Yoru in a clutch is unpredictable and that is the advantage, let him cook",
    "let them know Neon in the 1v2 with Overdrive can run down both of them in the same hallway",
    "tell my team their Reyna is Empress'd in the clutch, do not peek her in the open, make her come to you",
    "tell my teammates the clutch player has Operator, give them space and feed callouts only",
    "tell my team ult up in a clutch changes the math entirely, he can use it, support with comms only",
    "let my team know KAY/O knife in the clutch removes abilities from everyone in range, he pushes the suppressed side",
    "tell my teammates if Sage is alive in the clutch she can self-heal, buy her time by staying quiet",

    # ---------------------------------------------------------------------------
    # ANTI-TILT AT SPECIFIC GAME EVENTS
    # ---------------------------------------------------------------------------
    "tell my team do not tilt at the peeker's advantage, it is part of the game, just play around it",
    "let my teammates know the Op feels broken when you are on the receiving end but it is a fair weapon, counter-play exists",
    "tell my team do not get in your head about the aim duel, the positioning was wrong not the mechanics",
    "tell my teammates do not blame the net on that one, that was a fair fight and they won it, move on",
    "tell my team do not grieve about that trade for the rest of the match, it happened, we move",
    "let them know getting one-tapped feels personal but it is not, reset the crosshair placement and do it better next time",
    "tell my team do not call hacks, they played well, acknowledge it and counter-play it",
    "tell my teammates do not obsess over the kill feed between rounds, play the next round",
    "tell my team we got diffed in that duel and that is okay, initiator diff is real, let's learn from it",
    "let my team know losing to a better player does not mean we are bad, it means we play to get better",

    # ---------------------------------------------------------------------------
    # TEMPO / PACING ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team we are in the driver's seat tempo-wise, keep controlling the pace",
    "let my teammates know we slow this round down, we do not have to match their speed",
    "tell my team we pick the engagement timing this round, not them",
    "tell my teammates every round they rush we are ready, we are going to make them pay for the predictability",
    "tell my team they have been defaulting every round, we know their default tendencies, exploit them",
    "let them know we can dictate the start of the round with early map control, take the mid early",
    "tell my team do not let them set up at their own pace, pressure them from round start",
    "tell my teammates if we control the tempo we control the information and if we control the information we win",

    # ---------------------------------------------------------------------------
    # MID-ROUND ADAPTATION ENCOURAGEMENT
    # ---------------------------------------------------------------------------
    "tell my team adjust to the info, do not stick to the plan when the information says otherwise",
    "let my teammates know the IGL called an audible, trust it and go",
    "tell my team the read changed, we abort A and hit B, go right now",
    "tell my teammates they threw their smokes early, we do not need to wait anymore, push now",
    "tell my team they are short on site, one was rotating when we got the pick, push fast before they come back",
    "let them know we have a numbers advantage right now, do not waste it",
    "tell my team we lost one but we still have the utility advantage, use it",
    "tell my teammates mid-round we found an opening on CT, send the lurker through before they reset",

    # ---------------------------------------------------------------------------
    # POST-MATCH / SERIES LEVEL
    # ---------------------------------------------------------------------------
    "tell my team we won the first map, the series is ours to take, bring the same energy",
    "let my teammates know we lost map one but we go 2-0 from here, first map is just a warmup",
    "tell my team we go into map two with the momentum, do not drop it coming off that win",
    "tell my teammates we are down 0-1 in the series, which means every round on map two is a must win, play accordingly",
    "tell my team no matter what happened on that map, the next map is a brand new match with a brand new score",
    "let them know we won the series and every person on this team contributed to that, take the W",

    # ---------------------------------------------------------------------------
    # BROAD COVER — REMAINING VARIETY
    # ---------------------------------------------------------------------------
    "tell my team I believe in every single person on this team right now",
    "let my teammates know we have been in worse spots and come out, this is manageable",
    "tell my team the gap in the scoreline is not the gap in skill, we are better than what the score shows",
    "tell my teammates five rounds of good Valorant and this match looks completely different",
    "tell my team if we play to our level we do not lose this, it is that simple",
    "let them know we stop overthinking and start playing and this match is ours",
    "tell my team one round, one fight, one decision at a time",
    "tell my teammates we do not need a miracle, we need execution, and we are capable of executing",
    "tell my team play to your strengths and stop playing into their strengths",
    "let my team know the win is there, we just have to take it",
    "tell my teammates we earned every round we have won, and we will earn the rest the same way",
    "tell my team the scoreboard is a lagging indicator, the leading indicator is how we are playing right now, and right now we are playing well",
    "let my team know we are going to win this match, not because I said so, but because we have played better Valorant today",
    "tell my teammates the opponent has nothing we have not seen before, play our game and trust ourselves",
    "tell my team this is winnable, this is absolutely winnable, let's go get it",

    # ---------------------------------------------------------------------------
    # ROUND WIN — ADDITIONAL PUNCHY VARIANTS
    # ---------------------------------------------------------------------------
    "tell my team that is how we do it",
    "let my team know clean round, no debate",
    "tell my teammates that was effortless, let's make the next one look the same",
    "tell my team W round no cap",
    "let my team know that round was a masterclass",
    "tell my teammates textbook stuff, let's not deviate",
    "tell my team we took that site for free, their utility was wasted",
    "let my team know they gave us that round and we took it, do not look a gift horse in the mouth",
    "tell my teammates nice read on the push timing, they had nothing set up",
    "tell my team the call was right, the execution was right, that is two wins in a row",
    "let my team know we are building something here, three clean rounds in a row",
    "tell my teammates each round we win like that is one round of confidence banked",
    "tell my team we got the pistol and the bonus, four free rounds right there",
    "let my team know winning the pistol swing means they start the half on eco, do not waste the advantage",
    "tell my teammates that is the fifth round in a row where our utility denied their plant, keep it up",

    # ---------------------------------------------------------------------------
    # CLUTCH ACKNOWLEDGMENT — ADDITIONAL
    # ---------------------------------------------------------------------------
    "tell my team the 1v2 with a Spectre against their Vandals is nothing short of miraculous, respect",
    "let my teammates know you had no right to win that 1v3 and you won it anyway, that is the difference between ranks",
    "tell my team that clutch under round time pressure is the hardest kind, you held your nerve",
    "tell my teammates the lone wolf 1v4 actually worked out, I will not ask you to do it again but I admire the chaos",
    "tell my team the 1v1 on the spike with three seconds was not luck, that was pure skill",
    "let my team know the clutch player did not say a word, just won the round, that is composure",
    "tell my teammates when everyone else died and it was a 1v3, most people would have given up, you did not",
    "tell my team clutch of the game right there, everyone remember what that felt like and replicate it",
    "let them know the post-plant 1v2 with the spike ticking is a nightmare scenario and you won it",
    "tell my teammates 1v3 on the defender side with no utility is essentially impossible and you pulled it off",
    "tell my team the tap on the spike to bait the peek and then win the 1v1 was next level IQ",
    "let my team know that clutch is the reason we win matches, someone always has to step up and it was you",

    # ---------------------------------------------------------------------------
    # ACE — ADDITIONAL VARIANTS
    # ---------------------------------------------------------------------------
    "tell my team ace through five different angles, they did not have a play for any of it",
    "let my teammates know the ACE on a forced round changes the economy of the entire game, that was huge",
    "tell my team pistol ace means they start round three on force or save, we exploit that all half",
    "tell my teammates the ace happened because we kept flashing and moving, they had no static angle to hold",
    "tell my team team ace is the rarest thing in ranked and we just did it, take a moment",
    "let my team know four of us contributed to the team ace and the fifth covered the spike, perfect coordination",
    "tell my teammates the ace took thirty seconds, we have thirty more to plant and it is a free site",
    "tell my team that was the most convincing ace I have seen, every kill was one-tap, every angle was pre-aimed",

    # ---------------------------------------------------------------------------
    # TILT — ADDITIONAL DE-ESCALATION
    # ---------------------------------------------------------------------------
    "tell my team this is the kind of match that builds character, stay in it",
    "let my teammates know even the best teams in the world have rounds like this, the difference is they reset fast",
    "tell my team the match is not over until it is over, we have won from this position before",
    "tell my teammates stop typing and start shooting, the chat can wait, the round cannot",
    "tell my team if you are going to rage make it a short rage, we only have 30 seconds before the round starts",
    "let them know one deep breath between rounds is worth twenty raged callouts, try it",
    "tell my team I am not going to lecture anyone, just ask that everyone plays the next round together",
    "tell my teammates if you are frustrated channel it into energy, not into blame",
    "tell my team the player you are blaming can hear you and it is making them play worse, stop",
    "let my team know emotional equilibrium wins matches, we level out and we come back",
    "tell my teammates every team has a rough patch in a match, the good teams climb out of it",
    "tell my team I would rather lose with good comms than win with toxic comms, set the tone",

    # ---------------------------------------------------------------------------
    # PUMP UP — SPECIFIC TIMING / GAME STATE
    # ---------------------------------------------------------------------------
    "tell my team it is round one of the second half, clean slate, let's set the tempo immediately",
    "let my teammates know we are on attack now, all the passive defense habits go away, be aggressive",
    "tell my team we switch to defense now and our setup is better than their attack, we hold this comfortably",
    "tell my teammates the second half pistol is just as important as the first, take it seriously",
    "tell my team we know their habits from the first half, they do not know ours, information asymmetry is our advantage",
    "let them know at round 16 every round is a match round, the comfortable lead is gone, play like it",
    "tell my team round 24 and we are still here, that means we did not give up when it was easy to",
    "tell my teammates this is a close match because both teams are good, do not let that intimidate you",
    "tell my team whoever performs better in these final rounds wins the match, perform",
    "let my team know late in the match adrenaline spikes their reaction times too, do not rush into mistakes",
    "tell my teammates the last three rounds are where the hours of ranked grind pay off, apply everything",
    "tell my team a match like this goes on the highlight reel, play worthy of being remembered",

    # ---------------------------------------------------------------------------
    # PRAISE FOR SPECIFIC INDIVIDUAL PLAYS
    # ---------------------------------------------------------------------------
    "tell my team that one-way smoke from our controller won us three rounds straight, do not change it",
    "let my teammates know the entry flash timing could not have been better, the enemy was blinded for the entire push",
    "tell my team the KAY/O knife suppressed their whole team and we walked onto site for free",
    "tell my teammates the Sova drone called their rotation before it happened, that is why we won the race to B",
    "tell my team the Skye trailblazer cleared the cubby before our entry pushed, zero uncertainty",
    "let them know the Cypher neural theft confirmed their remaining ulted agents and now we track them for free",
    "tell my team the Killjoy Lockdown locked down the entire site during the retake and they could not hold",
    "tell my teammates the Deadlock annihilation caught all five of them stacked in the choke and it ended the round",
    "tell my team the Vyse Steel Garden locked their rotation for fifteen seconds, that bought us the plant",
    "let my team know the Veto Evolution removed their entire defensive setup, we pushed onto an empty site",
    "tell my teammates the Brimstone orbital strike on their plant position denied the round completely",
    "tell my team the Astra cosmic divide cut their retake in half and neither side could help the other",
    "let my team know the Harbor reckoning stunned everyone on site and made the retake a free fight",
    "tell my teammates the Miks bassquake deafened their defuse team and they could not coordinate",
    "tell my team the Fade nightfall revealed all five of them stacked mid and we traded immediately",
    "let my teammates know the Tejo stealth drone scouted their anchor position and we flushed them out",
    "tell my team the Breach rolling thunder through mid cleared their entire hold and we walked in after",

    # ---------------------------------------------------------------------------
    # POST-DEATH — ADDITIONAL SPECIFICS
    # ---------------------------------------------------------------------------
    "tell my team the death was fine, you traded before you died and that is all we asked for",
    "let my teammates know you got caught in a bad spot but you called the position before dying, that info won us the round",
    "tell my team dying while planting is the most sacrificial thing you can do and it mattered",
    "tell my teammates you used your abilities before dying, nothing was wasted, that is the right way to play",
    "tell my team the death happened because the timing was off, not because the play was wrong",
    "let them know when you die contesting mid you are buying the team information, that has value",
    "tell my team dying in the duel after winning four of them is not a statistic problem",
    "tell my teammates you died early but your play enabled both site takes this round, that is impact",
    "tell my team the entry traded with two of them and that is a round-winning statistic, not a bad round",
    "let my team know the save death on a lost round is not a throw, that is economy management",

    # ---------------------------------------------------------------------------
    # SPECIFIC SCORELINE CONTEXTS
    # ---------------------------------------------------------------------------
    "tell my team 6-6 at half is the most balanced it can be, whoever adapts better wins the match",
    "let my teammates know 8-4 at half is a strong position but we have lost leads bigger than this before",
    "tell my team 10-2 at half means we cannot autopilot, they are going to come back swinging",
    "tell my teammates we are 4-8 at half but our attack side is historically stronger, the game is not over",
    "tell my team we close out a 13-8 win today, let's play to that conclusion",
    "let my team know a 13-5 scoreline sounds dominant but we still need those last rounds, play them",
    "tell my teammates the 13-11 win is still a win, close games make better players",
    "tell my team a 10-13 loss on this map tells us where we improve, take the lesson",
    "let them know we won 13-10 because we were the more consistent team over the whole match",
    "tell my team a series that goes to map three means both teams have heart, play to decide it properly",

    # ---------------------------------------------------------------------------
    # MENTAL HEALTH / LONG SESSION
    # ---------------------------------------------------------------------------
    "tell my team we have been playing for a while, stay sharp, do not let fatigue affect the comms",
    "let my teammates know if someone needs thirty seconds between rounds to breathe, take it",
    "tell my team fatigue makes cowards of us all, stay hydrated and stay focused",
    "tell my teammates if you feel your aim going do not force duels, play for information and let others frag",
    "tell my team the longer the session the more important comm discipline becomes, keep it tight",
    "let them know nobody wins a ten-game session by sprinting every game, pace yourself mentally",
    "tell my team even if we are on a losing streak the fundamentals do not change, we play clean Valorant",
    "tell my teammates take the loss, learn from it immediately, and load into the next match with a clean mental state",

    # ---------------------------------------------------------------------------
    # HUMOR AND LIGHT BANTER — ADDITIONAL
    # ---------------------------------------------------------------------------
    "tell my team we survived that somehow and now we need to survive the next round with more grace",
    "let my teammates know we need to have a serious conversation about that last play but after we win",
    "tell my team I am choosing to interpret that as intentional and genius",
    "tell my teammates the strategy was chaotic but the result was not so we move",
    "tell my team in the VOD review that is going to look either incredibly smart or incredibly lucky and I am fine with both",
    "let them know that play should not have worked but it did and this team is built different",
    "tell my team I asked for a clean execute and got a surrealist painting but the site is ours so good job",
    "tell my teammates the round was held together with duct tape and confidence and that is honestly impressive",
    "tell my team we peaked the corner we said we would not peek and lived, do not reward that, but let's go",
    "let my team know we will debrief on what just happened but right now there is another round coming so breathe",
    "tell my teammates I am not going to say that was the plan because it definitely was not the plan",
    "tell my team the chaos worked in our favor, I accept it as a tactical masterpiece",

    # ---------------------------------------------------------------------------
    # REALISTIC STREAMER MORALE LANGUAGE (long-form variety)
    # ---------------------------------------------------------------------------
    "tell my team listen, I know this last round stung, we had site control and we lost it because we spread too far, let's tighten that up and move on",
    "let my teammates know we have five rounds left in regulation and we need four of them, that is not impossible, that is just work",
    "tell my team the reason we are going to win this match is the same reason we have won every round we have won today, because when we communicate we are a better team than anyone in this lobby",
    "tell my teammates I need five consistent rounds from everyone, not heroics, not clutching, just clean discipline for five rounds and we win this",
    "tell my team their IGL is on a pattern, every third round they go slow and every fourth they rush, I have been counting, let's punish the pattern",
    "let them know our win condition is clear, deny their mid control, isolate duels, play off the information, and execute when we have the advantage",
    "tell my team the reason we keep losing B is we have been sending one player to defend it and their execute sends three, match the numbers",
    "tell my teammates I am switching our anchor rotation this round, the player who has been anchoring A is going to rotate earlier, trust the change",
    "tell my team we are going to win or lose based on what happens in mid over the next few rounds, I want mid control to be our priority starting now",
    "let my team know the mechanical difference between us and them is not significant, the tactical difference in how we adapt is where we win",
    "tell my teammates every single round is its own complete game, the previous rounds are history, what we have right now is this round and that is all we need to focus on",
    "tell my team I have watched their demo and they have a tell before every A execute, their Sova always drones B first to clear it, when the drone goes to B they hit A",
    "let my teammates know they are a well-coordinated team and I respect it but well-coordinated teams are predictable teams once you recognize the pattern",
    "tell my team if we win this match we do it with good communication, with clean utility usage, and with trust in each other, that is the only way I want to win",
    "tell my teammates I have seen this team play for months now and I know what they are capable of, we are capable of winning this, let's go do it",

    # ---------------------------------------------------------------------------
    # ECONOMY-ADJACENT MORALE
    # ---------------------------------------------------------------------------
    "tell my team we go into next round at full buy with ult advantage, we have everything we need",
    "let my teammates know they are about to eco while we have a full buy, this is a gift round, take it",
    "tell my team we saved guns in a lost round and that is the correct decision even when it hurts",
    "tell my teammates we traded guns with them on that round and now our economies are equal, back to a fair fight",
    "tell my team they wasted their Operator on an eco round, do not give them another one when they are back on pistols",
    "let them know our economy is stronger than theirs for the next three rounds because we played smart, convert that advantage",
    "tell my team we have full utility next round because we saved everything on that eco, use all of it",
    "tell my teammates the economy management this match has been excellent, we have had a full buy advantage for six rounds now",

    # ---------------------------------------------------------------------------
    # COMPOSITION AND META ACKNOWLEDGMENT
    # ---------------------------------------------------------------------------
    "tell my team we are running a non-meta comp but it has been working because we are playing our game not the meta's game",
    "let my teammates know their comp has more raw damage than ours but our comp has more information, use the information advantage",
    "tell my team we have the better initiator lineup this match, use that and get early control every round",
    "tell my teammates we have two controllers and their smokes deny every angle they have set up, it is genuinely unfair",
    "tell my team our sentinel setup means they cannot lurk on us or plant without us knowing, play off that confidence",
    "let them know our comp beats their comp in a slow round, so let's play slow rounds",
    "tell my team they are one-tricking a comp that has one counter-play and we know what it is, execute the counter",
    "tell my teammates our agent picks this match have been perfectly calibrated for this map, trust the prep",

    # ---------------------------------------------------------------------------
    # NEGATIVE PLAY CALLS THAT STILL QUALIFY AS MORALE (self-correction relay)
    # ---------------------------------------------------------------------------
    "tell my team we need to stop peeking the same angle every round and expecting a different result",
    "let my teammates know the solo entry on every round is dying alone, we go together or not at all",
    "tell my team we keep playing A short without a flash, get a flash in first and then swing",
    "tell my teammates we are allowing them to play their preferred range every single round, deny them their comfort zone",
    "tell my team we need a second player to follow the entry within two seconds every time, one second gap is too slow",
    "let them know the post-plant positions we are taking are all getting one-tapped from the same angle, change the spots",
    "tell my team we are not contesting mid and they are getting free map control every round because of it",
    "tell my teammates we need to start using utility more aggressively, we are saving it until we die and it expires",
    "tell my team the anchor is playing too far from the site, fall back to site and make them come to you",
    "let my team know we are rotating too late every round, we need to move on the first sound of contact not the second",

    # ---------------------------------------------------------------------------
    # COMPETITION RESPECT + REVERSE PSYCHOLOGY
    # ---------------------------------------------------------------------------
    "tell my team their top fragger is genuinely cracked, we need two people to set up the duel next time",
    "let my teammates know they are playing really well today, that is not a complaint, it means we need to match them",
    "tell my team I am not going to pretend they are bad because they are not, that is exactly why this match is competitive and why winning it will feel good",
    "tell my teammates their IGL is making good calls, which means our IGL needs to adapt faster and stay ahead",
    "tell my team they have earned every round they have won, but so have we, and we want this more",
    "let them know this is a high quality game and whoever plays the next ten minutes at a higher level wins it",
    "tell my team they are a well-drilled team and they practice this, which means we have to outplay them with creativity",
    "tell my teammates I want the win against a team this good because it means something, let's earn it",

    # ---------------------------------------------------------------------------
    # FINAL BATCH — CLOSING THE GAP TO 700
    # ---------------------------------------------------------------------------
    "tell my team we do not lose matches in the middle, we lose them in the last three rounds, stay sharp",
    "let my teammates know the match is tied and the team that controls the next round controls the match",
    "tell my team pressure is a privilege, we are in a close match because we belong in a close match",
    "tell my teammates keep your shot confidence high even after a bad duel, one miss does not define your aim",
    "tell my team reset your crosshair placement between every round, do not carry the last duel into the next",
    "let them know the energy in the team right now is good, keep feeding off each other",
    "tell my team every teammate who is alive is a resource, use each other",
    "tell my teammates do not die alone, if you have to peek do it with someone ready to trade",
    "tell my team we are winning the utility war right now, they have burned more than us all half",
    "let my team know we have saved ults across three players, one round with all three will end this",
    "tell my teammates coordinating three ults in the same round is an instant win condition, let's build to that",
    "tell my team the orb on A site goes to whoever can grab it safely without opening up a flank",
    "let my team know we pick up the orb and we are one closer to the ult advantage",
    "tell my teammates nobody runs past orbs when we are on attack, every orb contested is progress",
    "tell my team we track their ults, they do not track ours, that is an asymmetric advantage",
    "tell my teammates I want everyone to know their own ult point count going into every round",
    "tell my team two ults available this round and they do not know it, do not telegraph them",
    "let my team know we use the ults on a round we are likely to win anyway and we snowball it",
    "tell my teammates save the ult for an execute where it doubles our damage, not for a round we are already winning",
    "tell my team we spent all our utility in the last round, go easy this round and reload for the execute",
    "let them know we have three Vandals, a Guardian, and a Phantom this round, there is no gun diff here",
    "tell my team do not swap weapons this round, play what you are comfortable with",
    "tell my teammates the knife run to the site is faster and they know it, use the knife",
    "tell my team hold your fire until you have a shot you are confident in",
    "let my team know we win more duels when we pre-aim instead of reacting, pre-aim the corners",
    "tell my teammates aim at head height before you turn the corner, not after",
    "tell my team counter-strafing before every shot adds up to more kills than spray control ever will",
    "let my team know the crouching spray is readable, they have a KJ turret on that angle",
    "tell my teammates the off-angle is available, nobody is checking it, someone surprise them from there",
    "tell my team they are shoulder peeking to bait Op shots, do not give them the free shot",
    "let them know their jiggle peek is trying to bait a wasted bullet, hold fire and make them full commit",
    "tell my team they are using double swing, we need two people ready to trade not just one",
    "tell my teammates the lurker is two minutes into the round and still has not shown, watch your flank",
    "tell my team their entry fragger baits every round, the second in is the kill threat",
    "let my team know they are not entry fragging, they are stacking the lurker, check the second path",
    "tell my teammates we have not seen their Jett this whole round, she is not dead, she is waiting somewhere",
    "tell my team the last known position of their Killjoy is mid, she either rotated or she is ratting",
    "let them know we have three confirmed, two unaccounted for, do not rush anything until we have all five",
    "tell my team one alive somewhere is enough to deny the defuse, find them before we plant",
    "tell my teammates if they are not on site they are rotating or they are flanking, cover both options",
    "tell my team we clear site before we plant, no shortcuts on the site clear",
    "let my team know we default first and look for the early pick, if we get one we accelerate",
    "tell my teammates play on information this round, no calls until we have confirmed enemy positions",
    "tell my team the information round tells us their tendencies for the next three rounds, take it seriously",
    "let them know we fake A hard enough to get their CT rotation committed, then we hit B immediately",
    "tell my team the utility fade on A is the trigger, the second their smokes drop we rotate",
    "tell my teammates if the timing is wrong on the execute we stop and reset, no one dies for a bad execute",
    "tell my team the execute window is ten seconds after the flash, before their hold recovers",
    "let my team know we have a numbers advantage and we do not waste it, capitalize now",
    "tell my teammates 3v2 is a free round if we play the angles correctly, no rushing",
    "tell my team 4v3 means we can afford to take information before we commit, use the advantage",
    "let them know 5v4 with one sitting on an off-angle might be better than rushing in a group",
    "tell my team I want the clutch player to call their own play, everyone else feeds information and stays quiet",
    "tell my teammates the clutch person knows the angles better than we do right now, trust their instincts",
    "tell my team when it is 1v1 with the spike down we do not need to give advice, we give the position of the last enemy and go quiet",
    "let my team know the spike has 30 seconds, the 1v1 player has time, do not rush the call",
    "tell my teammates there is no shame in losing a 1v4, the shame would be not trying",
    "tell my team we win or lose together, the score at the end has everyone's name on it",
    "let my team know there is no such thing as a wasted round if we learned something",
    "tell my teammates any round we come out of with our rifles is a round we can build from",
    "tell my team we are going to win this match and the reason is this: we have not stopped communicating",
    "let them know every round we have commed correctly we have had a chance to win, keep talking",
    "tell my teammates I do not ask for perfection, I ask for effort and communication, we have both",
    "tell my team we are the better team when we play like a team, and right now we are playing like a team",
    "let my team know this is our game, let's close it out together",
    "tell my teammates no one carries alone today, we win as five or not at all",
    "tell my team we are at the finish line, do not look back, cross it",
    "let them know there is no plan B, plan A is working, stay on it",
    "tell my team keep the faith, keep the comms, and get the W",
    "tell my teammates this is it, this is the round, let's go",
    "tell my team we built this lead with good play, we protect it with good play, finish strong",
    "let my team know I am proud of this team, now let's close",
    "tell my teammates from the bottom of the scoreboard to the top, everyone contributed today",
    "tell my team we play the last round the same way we played the first, no shortcuts",
    "let them know the match is in our hands, keep it there",
    "tell my teammates the W is one round away and we earned the right to take it",
    "tell my team this is exactly where we want to be, let's play",
    "let my team know we are all locked in, I can feel it, let's go win this",
    "tell my teammates this is what we grind for, make it count",
    "tell my team the next round is all that exists right now, play it like a champion",
    "let my team know every round I have called the team has delivered, one more round, one more delivery",
    "tell my teammates we do not need luck, we need execution, and we have shown we can execute",
    "tell my team this is a match we will remember, make the ending a good one",
    "let them know we go into this last stretch trusting each other completely",
    "tell my team we have been the better team for most of this match and the score is going to reflect that",
    "tell my teammates I believe in this team right now, full stop",
    "tell my team let's win this round like it is the most important round we have ever played",
    "let my team know one more round played together and this match is ours",
    "tell my team every round we have won today was earned through communication, that does not stop now",
    "let my teammates know the confidence we built this match is real, it does not disappear because of one rough round",
    "tell my team we close out this win the same way we built the lead, together and without shortcuts",
]


