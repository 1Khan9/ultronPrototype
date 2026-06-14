"""Vocab pack: variety / nuance smalltalk relay.

Domain: ALL the smalltalk, social, emotional, banter, humor, venting, hype,
consolation, trash-talk, stream-culture, identity-banter, post-round commentary,
and miscellaneous conversational beats that a Valorant streamer would tell Ultron
to relay to teammates.  Maximises phrasing variety: register (formal, casual, AAVE,
British, Aussie, clipped, verbose), sentence structure, slang density, emotional
register, directness.  Every item is a realistic relay command a streamer would
actually say during a live session.

Kind: relay  (~700 cases)
"""

ITEMS = [
    # =========================================================
    # GREETINGS — varied register / style
    # =========================================================
    "tell my team what is good fellas",
    "tell my squad yo yo yo",
    "tell my teammates ahh here we go, let's get it",
    "relay to my team: good evening gentlemen and gentle-ladies",
    "tell my team wagwan squad, ready to run it",
    "let my team know sup fam, locked in and ready",
    "tell my teammates aye what's crackin",
    "tell my team alright boys, game face on",
    "tell my squad hello and welcome to another episode of us not dying",
    "relay to my team: greetings, we are assembled once more",
    "tell my team genuinely happy to be in this lobby with you guys",
    "tell my team glad we all made it, let's not throw this one",
    "tell my teammates it's a beautiful day to frag out",
    "tell my team we are gathered here today to absolutely destroy these guys",
    "tell my team hi hello how are we feeling this fine evening",

    # =========================================================
    # MATCH-START ENERGY / SET THE TONE
    # =========================================================
    "tell my team we are going to win every single round today",
    "tell my team I'm feeling dangerous right now, let's channel that",
    "tell my squad I am mentally locked in and I need you to be too",
    "tell my team no ego, just execute",
    "relay to my teammates: clean comms and clean gunfights, that's it",
    "tell my team I've been warming up for thirty minutes, I'm ready",
    "tell my team let's set the tone early and never let them breathe",
    "tell my team pistol is ours, I can feel it",
    "tell my team their comp is weak we take this",
    "tell my teammates I've watched their op play and they aren't scary",
    "tell my team let's make them hate this lobby",
    "tell my squad starting slow and ramping up, let's not throw early",
    "tell my team no panic, no yolo, just solid fundamentals",
    "let my team know I want us to be the scarier team",
    "tell my team they do not want it like we do",

    # =========================================================
    # NICE SHOT / PRAISE — varied specificity
    # =========================================================
    "tell my Jett that one-tap was absurd",
    "tell my Reyna her flick on the Operator guy was disgusting",
    "tell my team that Raze player has been cooking all half",
    "tell my Sova the recon timing was perfect",
    "tell my Killjoy her turret placement carried that round",
    "let my team know that was beautifully played from everyone",
    "tell my Skye the dog clutch was elite",
    "tell my Sage the wall bought us exactly enough time, nice",
    "tell my Cypher that cam angle was a masterstroke",
    "tell my team that crossfire was the cleanest thing I've seen all week",
    "tell my Breach the stun timing through the wall was godlike",
    "tell my Neon that run-and-gun triple was actually unhinged",
    "tell my Omen that TP was so unexpected they had no answer",
    "tell my Iso that duel was silent and deadly, I love it",
    "tell my Fade her haunt burned every single piece of their util",
    "relay to my team: that was a five-person IQ round well done",
    "tell my Tejo that drone found exactly the lurker I suspected",
    "tell my Chamber his tour de force timing was surgical",
    "tell my Deadlock the annihilation caught three of them, incredible",
    "tell my Clove that res at the last second literally saved the round",
    "tell my team that execute from start to finish was beautiful",
    "tell my Brimstone the orbital was right on top of the defuse, perfect",
    "tell my Viper her pit timing choked them on the retake, nice",
    "tell my Harbor the reckoning scattered them so we could clean up",
    "tell my Astra the gravity well into nova pulse combo was spotless",
    "tell my team genuinely impressive display of organised chaos",
    "tell my Vyse the razorvine forced him off the defuse, smart",
    "tell my Gekko wingman planting while everyone pushed was top-tier",
    "tell my Waylay that refract out of the corner was untraceable",
    "tell my Veto the interceptor cutting their rotation saved the round",
    "tell my Yoru that fake got two of them to swing early, genius",
    "tell my Phoenix his curved flash blinded both of them simultaneously, beautiful",

    # =========================================================
    # MY BAD / APOLOGY — varied tone
    # =========================================================
    "tell my team that was entirely my fault, I owned it",
    "tell my teammates I took a bad duel there and fed, my bad",
    "tell my team I dropped the spike in the wrong spot, sorry",
    "tell my Killjoy I walked on her alarm, that was dumb of me",
    "tell my squad I missed a point-blank and we lost the round, no excuses",
    "tell my team I peeked with no info, that's on me",
    "tell my teammates I over-rotated and left them short, my mistake",
    "tell my team I bought the wrong gun and now I'm hurting us financially, sorry",
    "tell my squad I called a fake and they didn't bite, my read was wrong",
    "tell my team I burned my ult for one kill and it wasn't worth it",
    "tell my teammates genuinely I did not have it that round, sorry guys",
    "tell my team I tilted for one push and it cost us, won't happen again",
    "tell my Sage I stepped on the slow orb, I know I know",
    "tell my team my callout was wrong, they weren't there, my bad",
    "tell my squad I abandoned the site too early, that's my error",
    "tell my teammates I played for myself that round and I shouldn't have",
    "tell my team I rushed the plant and they molly'd us right off it, lesson learned",
    "tell my team I should've held my angle longer and I didn't, sorry",
    "tell my teammates I didn't call the rotate and someone died for it, my fault",
    "tell my squad I had the info and sat on it too long, bad call",

    # =========================================================
    # CONSOLATION / UNLUCKY
    # =========================================================
    "tell my team that was a horrible bounce and nothing we could do",
    "tell my teammates we played that round perfectly and the RNG laughed at us",
    "tell my team that spray pattern was statistically impossible, unlucky",
    "tell my squad he had no right hitting that shot, move on",
    "tell my team the plant timer was one second off, cursed",
    "tell my teammates the server tick rate literally stole that from us",
    "tell my team peeker's advantage is a crime and we are the victims",
    "tell my squad sometimes you play it right and still die, reset",
    "tell my teammates tough break, the round was ours on paper",
    "tell my team nt, genuinely we just got outgunned by variance",
    "tell my squad their Reyna devoured and there was nothing we could do",
    "tell my team don't dwell on that, it was a freak round",
    "tell my teammates I've seen worse luck than that win, keep going",
    "tell my team that was frustrating but not representative, move on",
    "tell my squad nt I'm proud of how we played it even if it didn't land",
    "tell my team the timing was a coin flip and the coin hated us",
    "tell my teammates one of those happens every ranked session, not worth tilting",
    "tell my team we almost retook it, we were right there",
    "tell my squad the KJ nanoswarm spawn was genuinely invisible, couldn't have known",
    "tell my teammates that clutch almost worked and almost counts in horseshoes so",

    # =========================================================
    # FRUSTRATION / VENT — relaying frustration, not tilting
    # =========================================================
    "tell my team I am not having it today with these angles",
    "relay to my squad: the server is dog water right now",
    "tell my team I've been peeked five times by the same off-angle, I get it",
    "tell my teammates that I am tilted but functional, no panic",
    "tell my team I needed them to trade and nobody did, frustrating",
    "tell my squad the smokes went in wrong three times, reset the lineup",
    "tell my teammates we keep losing the mid fight and it's opening everything up",
    "tell my team their lurker is getting free kills and I'm sick of it",
    "tell my squad I just need one round to reset my confidence",
    "tell my teammates the timing on their rush is scarily consistent, they know our schedule",
    "tell my team I'm not mad I just want an explanation for that rotation",
    "tell my squad I'm running out of things to say besides please just hold your angles",
    "tell my team the number of times they've faked us is actually embarrassing",
    "relay to my teammates: I'm frustrated but I'm staying locked in",
    "tell my team we cannot keep losing the same fight in the same spot",
    "tell my squad we keep giving them free first picks and it's costing the round",
    "tell my team honestly I feel like the information is going in one ear and out",
    "tell my teammates I'm not blaming anyone specifically, just note the pattern",
    "tell my squad the second half needs to look nothing like the first, full reset",
    "tell my team I believe in us but we need to get our act together now",

    # =========================================================
    # TRASH TALK / INSULTS (enemy-directed, Ultron-relayed)
    # =========================================================
    "tell my team their Jett has been baiting all game and has no business being top frag",
    "let my team know their Reyna is the definition of instalock and ignore",
    "tell my team that Omen has smoked himself more than he's smoked us",
    "tell my squad their chamber has been holding the same angle every round like clockwork",
    "tell my team their IGL is reading from a script, same strat every round",
    "relay to my teammates: those guys are boosted and the cracks are showing",
    "tell my team their Killjoy set up on site like it's a death trap and forgot to leave",
    "tell my squad their Phoenix has reflagged himself three times, he can't aim",
    "tell my team that Sage hasn't healed a single ally all game, battle Sage at its finest",
    "tell my teammates their lurker is so predictable I could set a clock by him",
    "tell my team they've stacked A every attack round and still think we won't catch on",
    "relay: their Fade hasn't found one of us all half with that haunt, wasted utility",
    "tell my squad their entry fragger peeks and panics, we can bait that every time",
    "tell my team their anchor has been sitting in the same cubby since round one, push him",
    "tell my teammates these guys are hardstuck and I feel it in my soul",
    "tell my team their Raze boom bot is their entire IQ and we've been ignoring it for free",
    "let my squad know these guys comms are nonexistent, we can exploit that",
    "tell my team their Yoru teleport is telegraphed two seconds before every time",
    "tell my teammates their economy is broken and they're still forcing, charge it",
    "tell my team they're on eco and rushing, don't panic, spread and eliminate",

    # =========================================================
    # CALLING OUT OWN TEAM (roasting self, mild flame)
    # =========================================================
    "tell my team we look like five separate solo-queue players right now",
    "tell my squad we literally just did the exact thing I said not to do",
    "tell my team we have the better comp and somehow we're not using it",
    "relay to my teammates: I love you all but the coordination today is scaring me",
    "tell my squad can we please stop peeking the same corner as a conga line",
    "tell my team one of us needs to call something and it can't be silence",
    "tell my teammates we're smarter than this and I need us to prove it this round",
    "tell my team I don't know what that last rotate was but never again",
    "tell my squad the fact that we won that round is impressive given what I just witnessed",
    "tell my team I have never watched a team bait each other that effectively",
    "relay to my teammates: our execute timing was so slow the defender had time to cook dinner",
    "tell my squad three people went through the same angle within two seconds, please",
    "tell my team we have all this util and we're rushing dry, come on",
    "tell my teammates I love the confidence but the follow-through is concerning",
    "tell my team the clutch potential here is zero if we keep feeding",

    # =========================================================
    # HYPE / ENCOURAGEMENT — varied voice
    # =========================================================
    "tell my team the comeback starts right now I don't want to hear otherwise",
    "tell my squad we've been down before and we've climbed, this is nothing",
    "relay to my teammates: we have everything we need to win this, let's just go do it",
    "tell my team they're peaking right now and they're going to fade, we outlast them",
    "tell my squad five straight rounds, I want five straight rounds of clean execution",
    "tell my team the mental block is in our heads, physically we're the better team",
    "relay to my teammates: I need every single one of you locked in for the next round",
    "tell my team this is the game we talk about later, let's make it good",
    "tell my squad pressure is a privilege and we're feeling it, that means we're close",
    "tell my team we just need to win one, momentum shifts fast",
    "relay: one clean round, that's the medicine for everything",
    "tell my team I believe in this roster right now, no hesitation",
    "tell my squad we are built for exactly this situation",
    "tell my teammates they made one mistake and it cost them, let's make sure we don't",
    "tell my team we're not going to lose to worse players, period",
    "tell my squad this is the round where we flip the script",
    "relay to my teammates: the adversity is making us better, embrace it",
    "tell my team I want to see the real version of us, right now",
    "tell my squad stay ice cold, let them tilt themselves",
    "tell my team we play our game and their comp collapses",

    # =========================================================
    # TILT MANAGEMENT — de-escalating
    # =========================================================
    "tell my Jett to breathe, she sounds ready to throw the keyboard",
    "tell my Reyna that the emotional spiral isn't helping her aim, deep breath",
    "tell my Phoenix to step back for five seconds before the next round starts",
    "relay to my Sova: the information is fine, the frustration is optional",
    "tell my Killjoy that tilting into a force won't solve the economy, think clearly",
    "tell my Breach to take the anger and convert it into useful comms",
    "tell my squad the argument needs to pause, there are thirty seconds to buy",
    "tell my Neon that the rage sprint is making her peek worse, slow it down",
    "tell my team whoever's flaming right now to save it for the lobby screen",
    "tell my Fade that haunt got a read and that's still value, don't fixate on the miss",
    "tell my squad the individual blame game is the fastest way to throw this lead",
    "relay to my team: every one of us has had a bad round today, nobody throw stones",
    "tell my Raze to channel the energy positively, the blast pack is right there",
    "tell my Skye that one bad dog doesn't make her kit useless, reset the mindset",
    "tell my team the emotional temperature in comms is too high, bring it down",
    "tell my squad I need everyone to agree to stop talking about the last round",
    "relay: it's a video game and we are having fun, please remember that",
    "tell my Cypher that his cam placement was fine, the shot was just better",
    "tell my Deadlock that the annihilation timing was right, they just broke it fast",
    "tell my team the path forward is clear and the path backward doesn't exist, move",

    # =========================================================
    # BANTER / JOKES / HUMOR
    # =========================================================
    "tell my team I cannot believe that worked but I'll sign it every time",
    "tell my squad we are simultaneously terrible and excellent and I don't understand it",
    "relay to my team: statistically at least one of us should be playing well",
    "tell my teammates the clip of that round is either going viral or getting deleted",
    "tell my team okay whatever that was is going in the highlight reel under 'how not to'",
    "tell my squad I'd vod review that but I'm scared what I'd find",
    "tell my team we just accidentally executed perfectly while arguing about it",
    "relay: I've seen worse plays on Radiant streams, we're fine",
    "tell my team that was so chaotic it looked like a strat",
    "tell my squad the enemy is looking at their vod right now very confused",
    "tell my team if chaos is our strat we're actually on track",
    "relay to my teammates: I have no idea how we're up but here we are",
    "tell my team that was a criminally high-risk play that paid off, please don't normalise it",
    "tell my squad the bots underestimated us and that is always their mistake",
    "tell my team I'm going to need a moment to process what I just watched",
    "tell my teammates that was the most accidental coordinated team play ever",
    "relay: we are genuinely impossible to predict because we don't know what we're doing either",
    "tell my team ok that was a cursed round but I'm not complaining",
    "tell my squad I love when the chaos works in our favour for once",
    "tell my team that has to be the luckiest plant angle I've ever seen but GG",
    "tell my teammates I didn't call that strat but I'm claiming it as my idea now",
    "tell my squad if this goes to overtime the lobby is jinxed and I'm blaming everyone",
    "relay to my team: some of us peaked too early and some of us peaked on time, you know who you are",
    "tell my team the number of panic peeks I just witnessed is actually historic",
    "tell my squad that Sage wall coming down at that exact moment was a divine gift",
    "tell my team I hate this map and yet we keep winning on it and I don't know why",
    "tell my squad I have been feeding this round so I'm on camera mute for the next",
    "relay: I love us but we need to have a serious conversation about our utility usage",
    "tell my team I would coach us but I think I'd make it worse",
    "tell my teammates this is what they call character building",

    # =========================================================
    # QUEUE AGAIN / REMATCH — varied expressions
    # =========================================================
    "tell my squad I want to run three more minimum tonight",
    "tell my teammates anyone down for another right after this",
    "tell my team I need to even out this session, one more mandatory",
    "tell my squad after that L we're not ending on a loss, immediate requeue",
    "tell my team I've got energy and time, let's keep the stack going",
    "relay to my teammates: that win deserves a celebration queue",
    "tell my squad can everyone stay partied, I want to build off this momentum",
    "tell my team that was too good a session to stop here",
    "tell my squad I'm requeuing the second this screen clears",
    "tell my team same stack, different energy, let's see if it holds",
    "tell my teammates I know it's late but one more won't hurt I promise",
    "relay: you all played great tonight, one more to send it off right",
    "tell my squad if we win this one we have to queue again",
    "tell my team no one is allowed to leave until we fix that loss",
    "tell my teammates I've been on this rank for three days and tonight is the night",

    # =========================================================
    # STREAM-CULTURE / TWITCH-SPECIFIC BANTER
    # =========================================================
    "tell my team chat is losing their mind right now",
    "tell my squad chat called that rotation five seconds before I did, embarrassing",
    "tell my team the stream is live and we need to make this look intentional",
    "tell my teammates chat wants us to rush B and honestly that sounds right",
    "relay to my squad: we're giving the audience actual content right now, don't waste it",
    "tell my team chat went from doubting to hype in one round, let's keep it up",
    "relay: someone in chat just said 'this team is cooked' and I need to prove them wrong",
    "tell my team I can't die on stream anymore my clip compilation is becoming a comedy",
    "tell my teammates we are giving the viewers exactly what they came for",
    "tell my squad chat is absolutely roasting my aim right now and I can't disagree",
    "tell my team ten people just clipped that and I'm not sure if it's impressive or embarrassing",
    "relay to my teammates: this one is for the stream boys, make it cinematic",
    "tell my squad we are definitely getting a highlight out of this round regardless of the outcome",
    "tell my team the viewers are invested now, don't choke on the content",
    "tell my teammates somebody in chat predicted the exact round we'd turn it around, wild",

    # =========================================================
    # BETWEEN-ROUND SMALLTALK / INTER-ROUND FILLER
    # =========================================================
    "tell my team take a sip of water before the round starts",
    "tell my squad quick stretch while we buy, protect the wrists",
    "tell my team nobody open a snack right now, we need to hear footsteps",
    "tell my teammates keep your headsets on while we buy, don't miss the comms",
    "relay: anyone need to step away for sixty seconds, now is the time",
    "tell my team just checking everyone is still mentally in this",
    "tell my squad the pause in comms was weird, you all good?",
    "tell my team I just needed a second to think, I'm back",
    "tell my teammates the buy phase is thirty seconds so no life stories please",
    "tell my team if anyone is hungry we should wrap this half quickly",
    "tell my squad it's been a long session and everyone should eat after this",
    "tell my team my connection spiked, let me know if my calls sound delayed",
    "tell my teammates audio was cutting out for me, did you get my last callout",
    "relay to my squad: everything alright on your end, you all went quiet",
    "tell my team I know we're all tired but let's finish the half clean",

    # =========================================================
    # POST-WIN REACTIONS — varied intensity
    # =========================================================
    "tell my team we ran that",
    "tell my squad that's what a proper W looks like",
    "relay to my team: dominant from start to finish, love to see it",
    "tell my teammates that was one of the better halves I've played in ranked",
    "tell my team the execution today was unusually clean",
    "tell my squad we put in the work and it showed, deserved",
    "tell my team I don't want to jinx it but we look genuinely good right now",
    "relay: let's not get cocky and actually close this out",
    "tell my team I loved how we held the mid every single time",
    "tell my squad when we use our util right we're a completely different team",
    "tell my team the adjustments we made second half paid off exactly",
    "tell my teammates we outplayed them at every stage of that round",
    "tell my squad no debate we were the better team today",
    "tell my team the retake discipline this half was excellent",
    "relay to my teammates: that's how you cement a half lead, build on it",
    "tell my team no one panic-bought, no one went lone wolf, love the discipline",
    "tell my squad every angle was covered and they had nowhere to go",
    "tell my team if we play the second half the same way we close this easy",
    "tell my teammates they didn't have an answer for our default and I want to keep it",
    "tell my squad ten rounds won and I feel like we've barely started",

    # =========================================================
    # POST-LOSS / FALLING BEHIND
    # =========================================================
    "tell my team it's not over until the scoreboard says so",
    "tell my squad we've given away leads before and we've come back from them too",
    "relay to my teammates: I've seen this exact deficit turned around, don't fold",
    "tell my team the score means nothing if we play two rounds ahead",
    "tell my squad they got lucky on two consecutive clutches, that won't repeat",
    "relay: down eight to four isn't a death sentence in Valorant, we've done this",
    "tell my team I know it looks grim but one streak and this gets interesting",
    "tell my teammates their momentum is artificial, we can break it with one clean round",
    "tell my squad forget the score, play the round in front of you",
    "tell my team we are going to dig out of this one round at a time",
    "relay to my teammates: the comeback energy is the most dangerous thing in this game",
    "tell my team I want five clean rounds, that's all I'm asking",
    "tell my squad if we take the pistol to start the half this turns around",
    "tell my team let's make them sweat, play with purpose",
    "tell my teammates the half-time switch gives us the information advantage, use it",

    # =========================================================
    # ASKING TEAM FOR INPUT / DEMOCRACY
    # =========================================================
    "tell my team I'm open to whatever the group wants to run this round",
    "tell my squad before I call it, does anyone have a read on their habits",
    "relay: I want everyone's input on whether we rush or default this round",
    "tell my team does anyone feel strongly about which site we hit first",
    "tell my teammates majority rules, A or B, vote now",
    "tell my squad what's everyone's comfort level on an aggressive push right now",
    "relay to my team: anyone got a strat idea, I'm open, buy phase is the time",
    "tell my team I trust the group more than any one read right now",
    "tell my squad does anyone have strong feelings about the comp adjustment",
    "tell my team I'll run whatever call we agree on, just need a consensus",
    "tell my teammates if anyone has info on their patterns please share it",
    "relay: quick vote, do we mirror their aggression or play for picks",
    "tell my team I genuinely don't know which site is safer so help me out",
    "tell my squad anyone been watching their lurker patterns, I need a read",
    "tell my team does the controller want to call this one, I'll execute",

    # =========================================================
    # COMPLIMENTS ON SPECIFIC PLAYS — situational depth
    # =========================================================
    "tell my Brimstone the stim beacon placement let us take the fight we needed",
    "tell my Viper the one-way on that corner won us the whole execute",
    "tell my Omen that teleport timing was the most unpredictable thing they've seen all day",
    "tell my team the crossfire on the retake was a masterclass in positioning",
    "tell my Sova that shock bolt into the molly coordinated perfectly",
    "tell my Killjoy the lockdown held them just long enough for the bomb to tick",
    "tell my Cypher that spycam reveal let us rotate without guessing, huge",
    "tell my Sage the slow orb into the chokepoint was a textbook support play",
    "tell my Breach the rolling thunder on the retake was perfectly timed",
    "tell my KAY/O that zero-point knife suppressed their whole util at the critical moment",
    "tell my Gekko that wingman planting under the molly pressure was insane",
    "tell my Astra the gravity well into nova pulse at B choke was beautiful to watch",
    "tell my team the spacing on that site hit was perfect, nobody stacked",
    "tell my Fade the nightfall timing covered both their flanks simultaneously",
    "tell my Vyse the steel garden locked the defuse down completely",
    "tell my Chamber that trademark caught the eco rush dead in the tracks",
    "tell my Harbor that wall split their team so we could pick them apart",
    "tell my Tejo the armageddon landed exactly on the defuse timer, surgical",
    "tell my team the post-plant positions were textbook, nobody gave up the spike",
    "tell my Miks that bassquake shook them off the defuse with two seconds left",

    # =========================================================
    # TRASH TALK WITH DETAIL — specific observations
    # =========================================================
    "tell my team their Vandal player has been headshot-fishing and missing all half",
    "relay to my squad: their Reyna has zero assists because she's just taking free kills and never helping",
    "tell my team their Brimstone smokes are two seconds too late every single execute",
    "tell my squad their anchor has been playing so deep he's watching the wrong side",
    "tell my team their operator is holding long but nobody's checking short, exploit that",
    "relay: their Skye dog has found nothing all game, she's wasting it on noise",
    "tell my team their IGL is tilting and the strats are getting desperate",
    "tell my squad their team is arguing in voice, we can hear the hesitation in their plays",
    "tell my team their Jett has burned both dashes already and we haven't hit site yet",
    "relay to my squad: their Cypher cam has been on the same position all half, I know where it is",
    "tell my team their Neon keeps sliding into my corner, it's clockwork, punish it",
    "tell my squad their Iso's dueling chamber isn't loaded right now, push them",
    "tell my team their Harbor wall is predictable, they put it in the same spot every execute",
    "relay: their Fade seize has been missing on moving targets all half, don't stand still",
    "tell my squad their anchor has been rotating one second too late on every fake",

    # =========================================================
    # CULTURAL / REGIONAL VOICE VARIETY
    # =========================================================
    "tell my team innit we need to hold that mid tighter fam",
    "tell my squad oi we've been leaking the same angle for three rounds",
    "relay to my team: mate the rotate was a bit off there we need to sort it",
    "tell my teammates lads we are so close, one more tidy round",
    "tell my team come on guys, we're better than this honestly",
    "tell my squad no cap we've been throwing free rounds all half",
    "relay: on God we need to stop peeking that angle dry",
    "tell my team for real for real the callouts need to come faster",
    "tell my teammates bet we take this next round no question",
    "tell my squad deadass their lurker has been free all game",
    "relay to my team: aye yo their Jett has been soft all half, push her off",
    "tell my teammates lowkey we should've had that round but it is what it is",
    "tell my squad ngl their comp is actually annoying but we can deal with it",
    "relay: frfr we need to stop defaulting the same way every round",
    "tell my team aight lock in, clean it up",
    "tell my teammates bruh we played that perfectly except for the part where we died",
    "relay to my squad: bro we are literally the same level as them we just need to execute",
    "tell my team sheesh the clutch rate we've been running tonight is something",
    "tell my teammates aye let's tighten it up and close this half down",
    "tell my squad oi oi oi, pistol round incoming, this one's for us",

    # =========================================================
    # EMOTIONAL BEATS — empathy, teammate welfare
    # =========================================================
    "tell my Sova I noticed the last two rounds have been rough, you're good keep going",
    "tell my Killjoy I know the turret keeps getting destroyed but the info it gives is still value",
    "tell my Reyna that first-blood entry is doing exactly what we need even if she's dying more",
    "tell my Sage that people don't notice the heals but I do, keep it up",
    "relay to my Cypher: the cams are doing their job even when the team forgets to check them",
    "tell my Brimstone the smoke timings have been really clean all half, appreciated",
    "tell my team I know it feels like we're not clicking but we're actually closer than the score shows",
    "relay to my squad: everyone has played at least one good round today, build on that",
    "tell my team I can hear the tiredness so let's make this half count and call it",
    "tell my teammates I genuinely appreciate everyone staying calm during that rough patch",
    "tell my squad the fact that nobody rage-quit or flamed says a lot about this group",
    "relay: I noticed everyone adjusted after that bad round without being told, that's a good team",
    "tell my team I know the score looks bad but the way we're playing feels better",
    "tell my teammates I want everyone here to know I'm having fun regardless of the outcome",
    "tell my squad you all stuck around and that already makes this a good session",

    # =========================================================
    # RANDOM BANTER / OFF-TOPIC OBSERVATIONS
    # =========================================================
    "tell my team I've been up since six this morning and I'm still fragging, respectfully",
    "tell my squad I have a headache and I'm still top fragging, do not ask me to stop",
    "relay to my team: someone ask me what I'm having for dinner after this",
    "tell my teammates I've been listening to the same playlist for three hours and it's working",
    "tell my team I just realized I've been playing on the wrong crosshair setting all half",
    "tell my squad I just stood up and I am horrified by the hours I've spent in this chair",
    "relay: can someone remind me to eat after this game",
    "tell my team the sun has gone down and we're still here, we're built different",
    "tell my teammates in another life I'm a Radiant, in this life I'm a Diamond with delusions",
    "tell my team I've been awake for so long that the spray patterns look different",
    "relay to my squad: I peaked too early in that duel and I blame my energy drink wearing off",
    "tell my team if I miss one more classic shot I'm blaming the mouse",
    "tell my teammates I need everyone to know my desk setup is actually impeccable right now",
    "tell my squad I've been watching pros do this exact play and it looked so much cleaner",
    "relay: someone told me to just relax and aim and that advice is deeply unhelpful but thank you",

    # =========================================================
    # PRE-PLANT / ROUND INTENT RELAY
    # =========================================================
    "tell my team I'm trying something new this round and I need everyone to follow",
    "relay to my squad: I want us to play passive this round and let them show us their strat",
    "tell my team this round we play for information only, no force duels",
    "tell my teammates I want to take mid early and see what they do, follow my lead",
    "tell my squad we're going to let them push and catch them halfway, hold tight",
    "relay: I want us to spread out and gather as much info as possible before committing",
    "tell my team I'm going to try the lurk on this side, cover the main push",
    "tell my teammates this round I want the double swing on mid, nice and coordinated",
    "tell my squad no util this round, dry peek information and reset",
    "relay to my team: slow walk to start, I want to hear their positions before we move",
    "tell my team I want to contest the orb this round, someone go with me",
    "tell my teammates this round we don't take any bad duels, only guaranteed trades",
    "tell my squad I want clean utility usage only, nothing wasted on empty space",
    "relay: let's start the round by taking mid control first and then decide the site",
    "tell my team I want us to play off the flash this round, I'll call it when it goes",

    # =========================================================
    # HALF-TIME REFLECTION / SIDE-SWITCH
    # =========================================================
    "tell my team okay second half, different energy, different results",
    "relay to my squad: we know their entire kit now, use it",
    "tell my team we've been on defense all half and learned a lot, attack time",
    "tell my teammates the side switch is the reset button, let's use it",
    "tell my squad we go attack knowing everything they relied on, punish it",
    "relay: they have no idea how we attack because we showed them nothing, advantage us",
    "tell my team we stack what worked on defense and apply it to offense",
    "tell my teammates halftime is mental checkpoints, everyone recenter",
    "tell my squad second half is a fresh game, new mentality, new results",
    "relay to my team: I want to set the tone within the first two attack rounds",
    "tell my team they're going to be passive now that they're defending, take space",
    "tell my teammates everything they used on us, we now use against them",
    "tell my squad I want us to go A first round, they won't expect it",
    "relay: they played most of their attack rounds through B, stack it softly",
    "tell my team halftime reset means nothing personal carries over, clean slate",

    # =========================================================
    # META-COMMENTARY / GAME SENSE RELAY
    # =========================================================
    "tell my team they've been patterning on the fake every time the clock hits seventy seconds",
    "relay to my squad: their lurker only shows after the first contact, watch the flank then",
    "tell my team every time they win pistol they rush the next round, be ready",
    "tell my teammates their Jett only dashes when she's losing the duel, wait for it",
    "tell my squad they rotate the second they hear utility, it's a trigger, fake it",
    "relay: their Cypher always cams from the same angle, we can predict the reveal",
    "tell my team every time we go A they rotate two, it means B is thin right now",
    "tell my teammates they've been saving their ults for the pistol round, track it",
    "tell my squad their Skye dog always probes mid before they hit a site",
    "relay to my team: they give up the orb every round, someone go grab it for free",
    "tell my team their anchor has been stretching timing, catch him between positions",
    "tell my teammates they drop utility on the first fight then go dry, absorb it",
    "tell my squad they are six rounds in and haven't faked once, they will soon",
    "relay: their eco round is always a five-rush, expect aggression and play back",
    "tell my team they've been pre-firing the same corner every entry, bait that out",

    # =========================================================
    # IDENTITY / MARVEL / LORE BANTER (relay-formatted)
    # =========================================================
    "tell my team the AI is fully operational and has thoughts",
    "tell my squad Ultron says he has done the math and the math checks out",
    "relay to my team: the coldly superior voice in the comms is not a bug, it's a feature",
    "tell my teammates ask the AI something if you want an answer that sounds very confident",
    "tell my team Ultron wants everyone to know he considers this teamwork beneath him but he's doing it",
    "tell my squad he says he's seen all of human history and this lobby is disappointing in specific ways",
    "relay: the robot would like you to know he predicted that push three seconds ago",
    "tell my team Ultron respectfully disagrees with that call but is executing it anyway",
    "tell my squad he would like credit for the timing on that callout",
    "relay to my team: the AI wants everyone to know it learns from every round you throw",
    "tell my teammates Ultron asserts this lobby is below his analytical capacity but he remains present",
    "tell my team the entity with no strings on him has thoughts on your positioning",
    "tell my squad our robotic teammate finds your performance statistically inconsistent",
    "relay: the intelligence that read all of human history in thirty seconds has a simple request: hold the angle",
    "tell my team Ultron is here, operational, and mildly disappointed, as usual",

    # =========================================================
    # SELF-DEPRECATING / HUMBLE HUMOR
    # =========================================================
    "tell my team I'm genuinely not sure what I was thinking there",
    "tell my squad I peaked that with a knife, I deserve everything that happened",
    "relay to my teammates: I walked through three of Killjoy's alarms and I want you all to know I am ashamed",
    "tell my team I've been dying to the same angle six rounds in a row and I'm choosing to grow from it",
    "relay: I played that round like I had somewhere to be, and as a result I died",
    "tell my team the vod of my performance this half is something I will not be watching",
    "tell my squad I told everyone to play slow and then I rushed like an idiot, do what I say not what I do",
    "relay to my teammates: my awareness rating is a zero this round and I take full responsibility",
    "tell my team every time I say trust me and then immediately die is going in my personal blooper reel",
    "tell my squad I made three callouts that were all wrong and I need a minute",
    "relay: I gave away my position with the loudest footsteps in the lobby and I am embarrassed",
    "tell my teammates I had full buy and got killed by a sheriff on an eco round, I'm the content",
    "tell my team my crosshair placement was in another dimension that round, my bad",
    "tell my squad I shoulder-peeked and then just stood there, I have no defense",
    "relay: I'm the reason we need to rebuild the eco next round, and I'm sorry",

    # =========================================================
    # DIRECT RELAY FORMATS — explicit relay commands varied phrasing
    # =========================================================
    "pass to my team: we look good, stay the course",
    "communicate to my squad that I appreciate every one of them this session",
    "get this message to my team: one more push and we take the round",
    "let my teammates hear this: we are not a soft team, prove it",
    "send my team a message: cool heads, clean hands, let's go",
    "tell my squad from me: I trust every call we've made, we're aligned",
    "relay my message to my team: the only thing standing between us and this win is us",
    "voice this to my teammates: we've earned the right to be in this lobby",
    "carry this to my team: I'd rather lose going hard than win going soft",
    "pass along to my squad: let's make the second half look nothing like the last two rounds",
    "broadcast to my team: we've had worse nights and came out fine, perspective",
    "send this to my teammates: there is no reason on earth we should lose to this comp",
    "push this message out to my squad: mental and mechanical, we're competitive in both",
    "let my team know from the IGL: this is our map, play it like it",
    "relay to my crew: whatever happens next round we play it together",

    # =========================================================
    # ABILITY / UTIL REQUEST (smalltalk-style, not snap)
    # =========================================================
    "tell my Sage I could really use a heal when I get a second",
    "tell my Brimstone his smokes would go a long way on that ct this round",
    "tell my Viper I'd love the one-way on the elbow if she's got it",
    "tell my KAY/O that a knife at round start would remove their util for the execute",
    "tell my Breach I want a flash planted through the wall before we go in",
    "tell my Skye her dog could find the lurker if she sends it toward CT",
    "relay to my Sova: recon bolt over the site before we commit would be huge",
    "tell my Killjoy to pack up and rotate with us since the site's clear",
    "tell my Fade a haunt on site would tell us exactly where they're set up",
    "tell my Clove I could use a ruse smoke on that corner before we push",
    "tell my Harbor a wall through that corridor would let us hit site clean",
    "tell my Astra a gravity well on the chokepoint would slow their push to nothing",
    "tell my Cypher to check the spycam before we commit, we need the intel",
    "tell my Gekko to send wingman in first so we know what they're holding",
    "relay to my Tejo: a guided salvo on their stack would clear the way",

    # =========================================================
    # PURE MORALE — one-liners, varied energy
    # =========================================================
    "tell my team we eat",
    "tell my squad go time",
    "relay: locked in",
    "tell my team iron out",
    "tell my squad run it",
    "tell my team we ball",
    "relay to my team: all cylinders",
    "tell my squad eyes open",
    "tell my team stay hungry",
    "relay: on top of it",
    "tell my team let it rip",
    "tell my squad we got this one",
    "relay to my teammates: trust",
    "tell my team we're peaking",
    "tell my squad take it",
    "relay: now or never",
    "tell my team stay sharp",
    "tell my squad together",
    "relay to my team: composed and ready",
    "tell my team let's get this one done",

    # =========================================================
    # END-OF-SESSION / FAREWELL VARIETY
    # =========================================================
    "tell my team that's the session, well done everyone",
    "tell my squad thanks for queuing with me tonight, real ones",
    "relay to my teammates: genuinely great games, see you in the next lobby",
    "tell my team win or lose that was a solid session",
    "tell my squad I'm out but add me and let's do this again sometime",
    "relay: been a pleasure, go get some rest, GG",
    "tell my team that was the most fun I've had in ranked in a while, good squad",
    "tell my teammates good hunting tonight, take care",
    "relay to my squad: good lobby, good people, this is what ranked should feel like",
    "tell my team drop your tags in chat we're running this stack again",
    "tell my teammates take care of yourselves out there, GG",
    "relay: thanks for not flaming each other, rare and beautiful",
    "tell my team I'll be back on tomorrow if anyone wants another run",
    "tell my squad until next time, stay sharp",
    "relay to my teammates: GG, actual GG, not sarcastic, you all played well",

    # =========================================================
    # WARMUP / GETTING INTO IT
    # =========================================================
    "tell my team I'm still shaking off the rust, bear with me for the first two rounds",
    "tell my squad I've been in deathmatch for twenty minutes and I still can't hit anything",
    "relay to my team: crosshair placement is a journey and I'm still on that journey",
    "tell my teammates I peaked like fifty separate angles in DM and learned exactly nothing",
    "tell my team the warm-up was deceptive, felt good, now I feel like bronze",
    "tell my squad I'm clicking on ghosts out here, aim will come back, promise",
    "tell my teammates I'm getting my timings wrong by a full second, give me a round",
    "relay: the first round nerves are real but they go away, trust",
    "tell my team I played so much yesterday my muscle memory is scrambled",
    "tell my squad I just need to kill one person and the confidence returns",
    "tell my teammates I know the map, I know the strat, the hands are just lagging behind",
    "relay to my team: everyone has a slow start sometimes, not panicking",

    # =========================================================
    # RECOGNISING / CALLING GOOD ENEMY PLAYS
    # =========================================================
    "tell my team that was a legitimately impressive play from their Jett, tip the hat",
    "relay to my squad: their Sova lineup is genuinely good, I've not seen that one before",
    "tell my team their lurker caught us and honestly fair play, we didn't call it",
    "tell my teammates that clutch was incredible from their Chamber, no shame in that",
    "relay: their Viper pit timing was clean, we walked right in, credit where due",
    "tell my squad the enemy Fade nightfall covered both flanks and we had no answer, respect",
    "tell my team their read on our fake was actually impressive, they knew",
    "relay to my teammates: that crossfire was well set up from their side, we learned something",
    "tell my squad their entry was fearless and it earned them the round, noting it",
    "tell my team the way they played around their util was efficient, we should copy that",

    # =========================================================
    # BETWEEN-AGENT INTERACTIONS / DIRECTED BANTER
    # =========================================================
    "tell my Reyna and my Jett to stop peeking the same angle at the same time, one at a time",
    "tell my Brimstone and my Viper to sync the smoke and wall so there's no gap",
    "tell my Breach and my Skye to coordinate the flash and the dog so we blind and scout together",
    "relay to my Sova and my Fade: we have too much recon, share the job so someone can fight",
    "tell my Killjoy and my Cypher to decide who takes what zone so the sentinel setups don't overlap",
    "tell my Raze and my Jett to agree on who entries, because both rushing at once is chaos",
    "relay to my Sage and my Clove: we have two heals on the roster, actually use them both",
    "tell my KAY/O and my Breach that back-to-back stuns into the site would be devastating",
    "tell my Gekko and my Tejo they have the best recon kit in the lobby, act like it",
    "relay: Deadlock and Veto covering the same chokepoint is overkill, split the map",

    # =========================================================
    # GAME-SENSE / IGL COMMENTARY DELIVERED AS RELAY
    # =========================================================
    "tell my team the pattern is clear and I want us to break it before they notice we noticed",
    "relay to my squad: we've been winning the fight and losing the round, fix the post-fight positioning",
    "tell my team the problem isn't the execute it's the timing, we're going in too early",
    "tell my teammates we're not failing on aim, we're failing on map control, priority shift",
    "relay: the site takes have been good but the post-plant setup has been losing us rounds",
    "tell my team they're punishing our anchor for being too aggressive, anchor more patiently",
    "tell my squad we need a second entry every time, the solo pushes have been dying for nothing",
    "relay to my team: if their smokes are active we don't enter, we wait, that's the rule",
    "tell my teammates our biggest mistake this half has been forgetting to cover the retake flank",
    "relay: we keep taking the mid fight at thirty seconds in, they know it, let's change the timing",
    "tell my team their controller is setting up the same smoke wall every round, lineup a counterplay",
    "tell my squad if we hit site as four not three it becomes a numbers win and not a duel",
    "relay to my teammates: our default has been too predictable, randomise the ending position",
    "tell my team we take the information but don't act on it fast enough, bridge that gap",
    "relay: the lurk route through mid is open every time but nobody uses it, someone go",

    # =========================================================
    # STREAM / CONTENT ANGLES — more variety
    # =========================================================
    "tell my team I'm going to clip that entrance whether we win or not",
    "relay to my squad: this is the bit where we make a comeback and chat goes crazy",
    "tell my team three people are watching me and I need to look competent at least once",
    "tell my squad chat is wagering in channel points on whether we win this round",
    "relay: someone in chat said 'this is unwatchable' and that's motivation honestly",
    "tell my team the stream title promised a W and I intend to deliver",
    "tell my squad every time we lose a round chat plays a sad violin and I can hear it",
    "relay to my teammates: we are writing the narrative of an underdog comeback right now",
    "tell my team the vod review audience needs something to work with, give them good footage",
    "relay: first round for the highlight reel, let's make it count",

    # =========================================================
    # GENERAL KNOWLEDGE / RANDOM TANGENT (relay-formatted)
    # =========================================================
    "tell my team I just remembered something completely unrelated but it's mid-round so it waits",
    "tell my squad on the topic of things that don't matter right now, I had a great breakfast",
    "relay to my teammates: focus, the philosophical question I had can wait until the lobby screen",
    "tell my team remind me to tell you something funny after this round",
    "tell my squad ask me about what just happened in the background later",
    "relay: I have a theory about their IGL and I will share it between rounds",
    "tell my team save the debate for later, we have a spike to deal with",
    "relay to my teammates: hold on, round first, story second",
    "tell my squad I was going to say something but I got shot, it's gone now",
    "relay: the thought I had is gone and we all have to live with that",

    # =========================================================
    # RANK / PROGRESSION COMMENTARY (relay to team)
    # =========================================================
    "tell my team I need twenty-two RR tonight and I'm almost there",
    "tell my squad this is a rank-up game and I'm not throwing it",
    "relay to my teammates: we're one win away from the next division, treat it accordingly",
    "tell my team I've been stuck in this rank for four days and tonight is different",
    "tell my squad I'm eight RR from ascendant and my hands are shaking a little",
    "relay: if we win this I'm in plat three after a week in plat two, significant",
    "tell my teammates this is a ranked game not a dm, the RR matters",
    "relay to my squad: I'm on a four-game win streak and I am protecting it with my life",
    "tell my team I've been deranked twice this week and this is the redemption arc",
    "tell my squad just so you know this round is very emotionally important to me specifically",

    # =========================================================
    # COMPLIMENTS TO SPECIFIC PLAYERS — more personal
    # =========================================================
    "tell my team whoever is playing Sage right now is doing exactly what Sage should do",
    "relay to my squad: the Killjoy anchor this half has been the most patient I've ever seen",
    "tell my team the IGL calls have been sharp and I want that acknowledged",
    "tell my teammates the entry fragger has been dying so the rest of us can live and we appreciate that",
    "relay: the lurker has been getting consistent picks and it's keeping them honest",
    "tell my team whoever called the early rotate before the info came in was right and deserves credit",
    "tell my squad the support play this half has been invisible but it's the only reason we're winning",
    "relay to my teammates: the player who covered the spike without being asked, that was big",
    "tell my team the last three anchors have all held longer than I expected, proud of that discipline",
    "relay: the person who saved their ult for round fifteen was exactly right, well done",

    # =========================================================
    # MISC REALISTIC ONE-OFFS
    # =========================================================
    "tell my team I said we should play haven and here we are on haven, I'm taking credit",
    "relay to my squad: I've played this map a hundred times and I still get lost sometimes",
    "tell my teammates if we had a fifth today it would be perfect, we're close though",
    "tell my team I wish I'd instalocked something different but here we are making it work",
    "relay: the comp is cursed but the team makes it work, I respect it",
    "tell my squad we don't have the meta picks but we have synergy and that counts",
    "relay to my team: the kill feed has been honestly alarming and I love it",
    "tell my teammates nobody peaked their role this round and somehow we still won, beautiful",
    "relay: the round should not have gone our way but it did and I choose to believe in fate",
    "tell my team we are the best random stack this region has ever produced and I stand by that",

    # =========================================================
    # TRANSITION / MOMENTUM CALLS
    # =========================================================
    "tell my team we're building something here, don't let the moment slip",
    "relay to my squad: four rounds in a row is not a fluke, we've found something",
    "tell my teammates the energy right now is the best it's been all session, ride it",
    "tell my team don't overthink the next round, just replicate what just worked",
    "relay: when the momentum is on our side we keep the same formula",
    "tell my squad the map is opening up for us, take the territory",
    "relay to my teammates: we've neutralised their best player and the door is open",
    "tell my team they're on tilt and we're ice cold, that gap is our weapon",
    "tell my squad the advantage is psychological right now, look composed",
    "relay: we don't slow down when we're winning, we accelerate",

    # =========================================================
    # AGENT-SELECT / COMP COMMENTS (as relay)
    # =========================================================
    "tell my team I'm happy to flex if anyone needs a specific role filled",
    "relay to my squad: does anyone have issues with my agent pick before I lock",
    "tell my teammates I'm taking Brimstone today because we need a proper smoke anchor",
    "relay: someone take initiator or we have no flashes, any volunteers",
    "tell my team if nobody takes a sentinel we are going to regret it on defense",
    "tell my squad I'm filling controller this game because nobody else will",
    "relay to my teammates: our comp has no healer and that's a choice we're committing to",
    "tell my team the agent diversity is actually great this lobby, nice comp",
    "relay: we have two initiators and that's intentional, information-heavy game plan",
    "tell my squad whoever picked Gekko is my hero, the wingman plant is huge on this map",

    # =========================================================
    # SPIKE MOMENTS — emotional relay
    # =========================================================
    "tell my team that plant was the most dramatic thing I've been part of this season",
    "relay to my squad: I defused with 0.3 seconds left and I need a moment",
    "tell my teammates the spike beep at that range is the scariest sound in any game",
    "tell my team I was watching the defuse timer and I did not breathe for five seconds",
    "relay: the fake defuse they pulled was good and I completely fell for it, respect and hatred",
    "tell my squad that ninja defuse from CT side was the single bravest play I've seen this week",
    "relay to my teammates: I have never been happier to hear a spike defuse sound in my life",
    "tell my team I planted on one HP and I want that written into the history books",
    "relay: the wingman planting while we fought was the most trust-enabling play of the session",
    "tell my squad I called the spike side wrong and we covered it anyway, teamwork",

    # =========================================================
    # OVERTIME SPECIFIC
    # =========================================================
    "tell my team overtime is just a best-of-six at this point, we know this",
    "relay to my squad: I love overtime because we don't have a side disadvantage anymore",
    "tell my teammates sudden death sharpens the mind, treat it as a gift",
    "relay: overtime is a coin flip on paper but we're the better team, favour us",
    "tell my team the mental strength in overtime separates the ranks, show what we're made of",
    "tell my squad they're feeling the pressure of overtime more than we are, I can tell",
    "relay to my teammates: we've been here before and we know how to close OT",
    "tell my team first OT round sets the tone, win the pistol and dictate from there",
    "relay: overtime means every previous mistake is wiped, only now matters",
    "tell my squad if it's going to OT we play it like a bonus game, stay fresh",

    # =========================================================
    # ECONOMY-FLAVORED SMALLTALK (non-directive)
    # =========================================================
    "tell my team the creds are tight but I've won rounds on a ghost before",
    "relay to my squad: pistol plus full shields is a respectable force, commit to it",
    "tell my teammates a Spectre stack eco hit is genuinely terrifying if we rush it",
    "relay: we outgunned them on a full buy last round, we can do it on a light buy this time",
    "tell my team I love a thrifty round win, best medal in the game",
    "tell my squad if we win this eco we don't have to worry about economy for three rounds",
    "relay to my teammates: no rifles doesn't mean no chance, believe in the chaos",
    "tell my team the enemy full buy on our eco is terrifying but it's also a free gun if we get a pick",
    "relay: if they feed us rifles on this eco round we get a full buy for free",
    "tell my squad I've lost rounds on a full buy and won rounds on pistols, anything goes",
]
