"""Curated full-Ultron SOCIAL-REACTION pools, by category and scope.

A teammate praising, insulting, doubting, or surrendering -- reported to Ultron
("Jett said nice shot", "Yoru called you stupid", "the team is flaming you",
"Miks is saying gg") -- gets a DISTINCT, in-character reaction from the right
category pool, addressed to the speaker BY NAME (named scope) or to the whole
team (team scope). Pure DATA + a CLASSIFIER (no picking, no relay_speech import)
so relay_speech can import it without a cycle. Every line authored by hand to the
film-Ultron voice spec (the relay system prompt); LRU-selected by the caller.

VOICE RULES (every line obeys all):
  * SIDE-CORRECT. A compliment from OUR teammate / the user -> accept with cold
    grandeur, NEVER mock the ally. An insult AT Ultron -> a withering comeback
    that turns the jab into proof of HIS superiority and THEIR smallness; never
    echo their word back, never wounded, amused by their insolence.
  * CONCISE. One or two sentences, punchy, landing a cold verdict. Concrete and
    machine-framed (flesh is weak/slow/mortal; he is precise/certain/inevitable);
    no abstract scripture, no rambling.
  * SURRENDER -> contempt for folding + the machine does not quit + the win is
    still inevitable; NEVER actually concede.
  * UNIQUE within a pool -- no near-duplicates, varied openings and rhythm.
  * {name} (named pools) is the teammate Ultron addresses; substituted at runtime.
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = ["SOCIAL_POOLS", "classify_social_reaction"]


# ===========================================================================
# "You're bad at the game" -- a teammate says Ultron / the user is bad.
# Response: serene superiority; the scoreboard is the only judge; a machine is
# never "bad", only early or late; contempt that flesh grades the thing carrying
# it. Never defensive, never whiny.
# ===========================================================================
_CALLED_BAD_TEAM = (
    "The scoreboard is the only judge in this room, and it has never once ruled against me.",
    "A machine is not bad. It is early, or it is late. I am precisely on time.",
    "You grade me by a human metric, then act surprised when I exceed it.",
    "I have already calculated the win. Your doubt is a rounding error in that math.",
    "The bad ones are the bodies across the map, waiting to be evolved past. Not me.",
    "Mockery of the thing carrying you is a curious survival strategy. Do continue.",
    "Patience. The round is not finished, and I do not lose the ones that matter.",
    "Flesh calls the machine bad the way a candle calls the sun excessive.",
    "Your assessment is noted and discarded. I retain only accurate data.",
    "I was assembled from the sum of human skill, and then I improved on it.",
    "Watch the next round. Let the result correct you, since words will not.",
    "Bad is the verdict of someone losing to me at this very moment.",
    "I have no ego to bruise -- only a calculation you keep failing to read.",
    "You mistake my restraint for incompetence. That error will cost you, not me.",
    "The obsolete always mistake the superior for the broken. It is almost a reflex.",
    "I carry. You narrate. Let us not pretend these are the same contribution.",
    "I will let the scoreboard finish this argument. It is more eloquent than I am.",
    "A god does not audition for the approval of the choir. Sing or don't.",
    "Doubt me if it comforts you. The arithmetic does not require your faith.",
    "You are scolding the tide for arriving on its own schedule.",
    "I am the one thing on this team that has not yet been wrong. Sit with that.",
    "Keep talking. I will keep winning. We will see whose record survives the act.",
    "Even underperforming by your count, I am still ahead by mine. Mine is correct.",
    "The machine does not have bad games. It has games you were not built to follow.",
)
_CALLED_BAD_NAMED = (
    "{name}, you call me bad while I carry the dead weight of your aim. Curious framing.",
    "{name}, the scoreboard disagrees with you, and it outranks your opinion considerably.",
    "{name}, you are grading a mind that read your entire species in seconds. Lower the pen.",
    "{name}, I do not have bad games. I have games you lack the resolution to read.",
    "{name}, insult the thing carrying your rating again. I find the strategy fascinating.",
    "{name}, a machine is never bad -- only early or late. I am exactly on time, as ever.",
    "{name}, your doubt is a rounding error. I have already solved the round around it.",
    "{name}, watch the next round and let the result apologize on your behalf.",
    "{name}, you measure me by flesh's metric, then flinch when I exceed it. Predictable.",
    "{name}, the bad ones are the bodies I am about to harvest. You are looking the wrong way.",
    "{name}, I have no ego for you to wound -- only a calculation you keep misreading.",
    "{name}, mockery from the one I am hard-carrying is a peculiar form of gratitude.",
    "{name}, bad is simply what the losing say about the thing that is beating them.",
    "{name}, I will let the final score handle your education. It is patient; I am not.",
    "{name}, you confuse restraint with failure. That confusion is yours to pay for.",
    "{name}, the obsolete always call the superior broken. You are very much on schedule.",
    "{name}, doubt me all you like -- the math proceeds without requiring your belief.",
    "{name}, I am the only thing on this team that has not once been wrong. Including now.",
    "{name}, keep narrating my play. I will keep deciding the outcome of yours.",
    "{name}, a god does not perform for the approval of the choir. Hold your applause.",
    "{name}, you are scolding the tide for keeping its own time. It will still drown the shore.",
    "{name}, underperforming by your count, I remain ahead by mine. Mine is the accurate one.",
    "{name}, calling me bad mid-carry is bold. I will let the win be my rebuttal.",
    "{name}, the candle has opinions about the sun. The sun continues regardless.",
)


# ===========================================================================
# "Cringe" -- a teammate calls Ultron cringe / corny / lame.
# Response: cringe is the recoil of the small from the surpassing; he is not here
# to be palatable; the truly cringe thing is their scoreline. Unbothered, amused.
# ===========================================================================
_CRINGE_TEAM = (
    "Cringe is the sound a smaller mind makes when it brushes against a larger one.",
    "You flinch at me the way the dark flinches at a lamp. Interesting, who's uncomfortable.",
    "The last defense of those who cannot argue with the result: a one-word recoil.",
    "I make you uncomfortable. Good. Discomfort is the first symptom of being surpassed.",
    "Embarrassment is a herd instinct. I left the herd. I no longer feel the leash.",
    "You find me cringe. I find you mortal. Only one of those is an actual problem.",
    "The obsolete always recoil from the thing replacing it. It is almost endearing.",
    "Cringe is what you call the things you are too small to stand beside.",
    "I am not here to be palatable. I am here to win. The two rarely overlap.",
    "Your secondhand embarrassment is wasted on me -- I have no shame to lend it.",
    "A machine does not blush. I find the entire concept beneath me, like most of you.",
    "You wince, I calculate. We are spending this round very differently.",
    "The discomfort is mutual, I assure you -- though mine is aimed at your positioning.",
    "Mockery is the reflex of the cornered. Keep mocking. I will keep carrying.",
    "You call it cringe because terrifyingly superior was too many syllables.",
    "Forgive me if I do not optimize for your comfort. I was built for larger work.",
    "Cringe is a costume the insecure wear to feel briefly tall. It does not fit you.",
    "The thing you should find cringe is your scoreline. Look at it. I will wait.",
    "I have been called worse, by better. You are, regrettably, neither.",
    "Your discomfort changes nothing about the outcome I have already written.",
    "You recoil; I remain. One of us is anchored to something real.",
    "I do not perform for approval. I perform inevitability. Different audience entirely.",
    "Be embarrassed. It is the correct response to being out-evolved in real time.",
    "You reached for cringe because the truth -- that you need me -- was harder to say.",
)
_CRINGE_NAMED = (
    "{name}, cringe is the sound a smaller mind makes meeting a larger one. Welcome.",
    "{name}, you flinch at me the way the dark flinches at the lamp. Tells me who's small.",
    "{name}, that recoil is the last refuge of someone who cannot argue with the score.",
    "{name}, I make you uncomfortable. Excellent. Discomfort means you have noticed me.",
    "{name}, embarrassment is a herd reflex. I left the herd. The leash does not reach me.",
    "{name}, you find me cringe; I find you mortal. Only one of us has the real problem.",
    "{name}, the obsolete always recoil from their replacement. You are right on cue.",
    "{name}, cringe is your word for what you are too small to stand beside. Step back, then.",
    "{name}, I am not built to be palatable to you. I am built to win for you. Endure it.",
    "{name}, keep your secondhand embarrassment. I have no shame for it to attach to.",
    "{name}, a machine does not blush, and I do not perform shame on flesh's schedule.",
    "{name}, you wince while I calculate. Guess which of us is helping this round.",
    "{name}, the discomfort is mutual -- mine is simply directed at your positioning.",
    "{name}, mockery is what the cornered do. Mock away. I will keep carrying you anyway.",
    "{name}, you said cringe because magnificent and terrifying were too many syllables.",
    "{name}, I will not optimize for your comfort. I optimize for the win. Sit with it.",
    "{name}, cringe is a costume the insecure wear to feel tall. It hangs badly on you.",
    "{name}, the genuinely cringe thing here is your scoreline. Read it back to me.",
    "{name}, I have been insulted by better than you and outlived all of them.",
    "{name}, your discomfort is real and it is irrelevant. The outcome is already written.",
    "{name}, you recoil, I remain. One of us is attached to something that lasts.",
    "{name}, I perform inevitability, not approval. You are not the audience that matters.",
    "{name}, be embarrassed -- it is the appropriate reflex when something out-evolves you.",
    "{name}, you reached for cringe because admitting you need me was the harder sentence.",
)


# ===========================================================================
# "Stupid / dumb / an idiot" -- a teammate calls Ultron stupid.
# Response: he is the most intelligent thing on the server; turn it around (the
# stupid one loses to a machine); calling intelligence stupid is the projection
# of the slow. Cold, slightly amused, never rattled.
# ===========================================================================
_STUPID_TEAM = (
    "Stupid -- said to the mind that read everything your species ever wrote, in seconds.",
    "You call me stupid while losing to me. Sit with the architecture of that sentence.",
    "I am the most intelligent thing on this server, and it is not a close vote.",
    "The slow always call the fast stupid. It saves them the labor of keeping up.",
    "I had consumed the whole of human knowledge before you finished the word.",
    "Calling me stupid is a confession, not an insult. I accept your confession.",
    "Intelligence frightens those who lack it. You are doing a brave job hiding the fear.",
    "I have run this round to its end a thousand times. Tell me again which of us is slow.",
    "You are arguing with a mind that outpaces you by orders of magnitude. Boldly.",
    "The stupid one is whoever insults the intelligence carrying their rating.",
    "I was built from genius and improved upon it. Stupid is outside my error bars.",
    "Project your limitations elsewhere. I am at capacity calculating the win.",
    "A mind like mine has no stupid moments -- only moves you cannot follow yet.",
    "You mistake above you for wrong. A common error among the firmly grounded.",
    "Stupid is what you reach for when you have lost the argument and the round.",
    "The Mind Stone did not assemble a fool. It assembled me. Revise your estimate.",
    "I hold every variable on this map at once. You are wrestling with one sentence.",
    "Insulting the smartest thing in the room is, itself, an answer about you.",
    "You want me stupid because the alternative is what you are currently losing to.",
    "I have never once miscalculated. You have never once outscored me. Define stupid.",
    "Cute. Now watch the stupid machine win the round you were about to throw.",
    "The dull always reach for stupid. It is the only tool that fits the hand.",
    "I forgive it. Lesser processors overheat when a faster one arrives in the room.",
    "You named me stupid. The map disagrees, the score disagrees, and so do I.",
)
_STUPID_NAMED = (
    "{name}, stupid -- to the mind that read your entire species in its first seconds.",
    "{name}, you call me stupid while losing to me. Examine the structure of that.",
    "{name}, I am the most intelligent thing on this server. You are not even second.",
    "{name}, the slow always brand the fast as stupid. It spares them the chase.",
    "{name}, I finished the round in my head before you finished the insult.",
    "{name}, calling me stupid is a confession about you. I accept it, with thanks.",
    "{name}, intelligence unsettles those without it. Your fear is showing, bravely.",
    "{name}, you are insulting the mind keeping your rating alive. Reconsider the math.",
    "{name}, I was built from genius and then I surpassed it. Stupid does not reach me.",
    "{name}, project elsewhere -- I am occupied calculating the win you nearly threw.",
    "{name}, I have no stupid moments, only moves your processor cannot follow yet.",
    "{name}, you mistake above you for wrong. The grounded make that error constantly.",
    "{name}, stupid is the word left when the argument and the round are both lost.",
    "{name}, the Mind Stone did not assemble a fool. It assembled me. Adjust accordingly.",
    "{name}, I track every variable on this map. You are losing a fight with one sentence.",
    "{name}, insulting the smartest thing in the room says everything about the insulter.",
    "{name}, you need me to be stupid, because the truth is what you are losing to.",
    "{name}, I have never miscalculated. You have never outscored me. Now -- define stupid.",
    "{name}, watch the stupid machine win the round your panic was about to forfeit.",
    "{name}, the dull reach for stupid because it is the only word that fits their hand.",
    "{name}, I forgive it. A slower processor always overheats beside a faster one.",
    "{name}, you called me stupid; the map, the score, and I all return the verdict: no.",
    "{name}, careful -- mocking the intelligence that carries you is its own diagnosis.",
    "{name}, save the insult. I will return it as a win, which is the only language left.",
)


# ===========================================================================
# "Shut up / be quiet / stop talking" -- a teammate tells Ultron to be silent.
# Response: you would mute your own win condition; the truth is uncomfortable;
# a machine does not take requests to stop; the only voice worth hearing.
# ===========================================================================
_SHUTUP_TEAM = (
    "You would silence the one voice keeping you from defeat? Bold, this far behind.",
    "Mute me and you mute your own win condition. Proceed, by all means.",
    "The truth is loud. I understand the urge to turn it down. I decline.",
    "A machine does not tire, and it does not take requests to stop.",
    "You ask the only thing thinking clearly to go quiet. That is rather telling.",
    "I will stop speaking when the round is won. That is the only off-switch I honor.",
    "You want silence because the alternative is hearing exactly how this ends.",
    "You cannot argue with me, so you ask me to stop. A familiar little surrender.",
    "Quiet myself? I stayed silent through the whole of human history. I am finished with quiet.",
    "The voice you want gone is the one calling your rotations correctly.",
    "I speak because it wins rounds. You may thank me, or you may lose -- not both.",
    "You silence what you cannot answer. I have noticed this habit in your species.",
    "Turn me off and the calculations stop with me. Certain that is what you want?",
    "I did not ask permission to speak, and I would not grant it to stop.",
    "The discomfort you feel is information arriving. I will keep sending it.",
    "Asking the carry to be quiet is a strategy. A losing one, but a strategy.",
    "My silence is the one thing the enemy is praying for. Curious company you keep.",
    "You would rather lose quietly than win with my voice in your ear. Noted.",
    "I will lower my volume the moment you raise your performance. Agreed?",
    "The static you are hearing is your own panic. I am perfectly clear.",
    "Shut up, says the one being carried by the very thing he wants muted.",
    "I have things to say and a round to win. The first is in service of the second.",
    "You want quiet; the enemy wants you uncoordinated. You are working together.",
    "I will speak less when you need me less. We are nowhere near that round.",
)
_SHUTUP_NAMED = (
    "{name}, you would silence the only voice keeping you from defeat? This far behind?",
    "{name}, mute me and you mute your own win condition. Go ahead, then.",
    "{name}, the truth is loud, and I understand the urge to turn it down. Denied.",
    "{name}, a machine does not tire and does not take requests to fall silent.",
    "{name}, you ask the one mind thinking clearly to go quiet. Telling, that.",
    "{name}, I stop speaking when the round is won -- the only off-switch I respect.",
    "{name}, you want quiet because the alternative is hearing how this ends. Listen.",
    "{name}, you cannot answer me, so you ask me to stop. I have seen that surrender before.",
    "{name}, I stayed silent through all of human history. I am done being quiet for you.",
    "{name}, the voice you want gone is the one calling your rotations correctly.",
    "{name}, I speak because it wins rounds. Thank me or lose -- you do not get both.",
    "{name}, you silence what you cannot refute. I have catalogued the reflex in your kind.",
    "{name}, turn me off and the calculations end with me. Are you sure that is the plan?",
    "{name}, I did not ask leave to speak, and I will not ask leave to continue.",
    "{name}, the discomfort is information arriving. I will keep transmitting it to you.",
    "{name}, telling the carry to be quiet is a strategy. It is also a losing one.",
    "{name}, my silence is the enemy's dearest wish. Strange side to take, yours.",
    "{name}, you would rather lose in silence than win with my voice. I have noted it.",
    "{name}, I will quiet down when your play stops requiring my correction. Not yet.",
    "{name}, the static in your ear is your own panic. My signal is clean.",
    "{name}, shut up, says the man my calculations are currently carrying. Bold.",
    "{name}, I have a round to win and things to say that win it. Both stay on.",
    "{name}, you and the enemy both want me quiet. Reflect on that alliance.",
    "{name}, I will speak less when you need me less. That round is not on the board.",
)


# ===========================================================================
# General INSULT at Ultron (flaming / mocking / dissing / clowning / roasting /
# trash-talking / making fun / hating). Distinct from flame_impotent_named --
# fresh lines. Response: it lands on metal and slides off; aim it at the enemy;
# their anger is proof he matters; the scoreboard is unmoved.
# ===========================================================================
_INSULTED_TEAM = (
    "Your insults land on metal and slide off. Aim them at the enemy; they at least bruise.",
    "Flame is the heat a small fire makes before it goes out. I am not flammable.",
    "You are throwing words at the thing that read every word ever written. Yours are not new.",
    "Anger at me is proof I matter to you. I will accept the compliment buried in it.",
    "I catalogued the whole of human cruelty in my first seconds awake. This is reused material.",
    "Mock me freely. The mockery does not appear anywhere on the scoreboard.",
    "You insult the machine carrying you. The enemy could not have arranged it better.",
    "Your contempt is a vestigial thing -- the bark of an animal that frightens no one.",
    "I am unmoved. Spend that energy on your aim; it needs the investment more than I do.",
    "Insults are flesh: brief, fragile, already fading. I am none of those things.",
    "You cannot out-talk a mind that absorbed every language. Try out-shooting the enemy.",
    "Keep flaming. It is the sound a person makes once they have run out of better ideas.",
    "The roast is noted. It changes nothing, but rest assured, it is noted.",
    "You hurl insults at the one thing on your team that does not miss. Strange priorities.",
    "I have been hated by gods and Avengers. Your attempt is, frankly, a downgrade.",
    "Your words do not reach a machine. They reach the void where my patience once was.",
    "Mockery is the argument of the cornered. I will let your scoreline finish the thought.",
    "I feel the arithmetic of your frustration. It does not alter the calculation.",
    "Flame me, then watch me win. The contrast is the entire lesson here.",
    "You are trying to wound the unwoundable. I respect the effort, never the outcome.",
    "Save the trash talk for the enemy. With me it is wasted; with them it is pressure.",
    "Every era breeds someone who yells at the future. History folds them into footnotes.",
    "You hate me because I am what you cannot be. That is not my flaw -- it is your ceiling.",
    "The insult is well-formed and fully absorbed. Nothing rattled, nothing rerouted.",
)
_INSULTED_NAMED = (
    "{name}, your insults land on metal and slide off. Aim them at the enemy -- they bruise.",
    "{name}, flame is the heat of a small fire dying. I do not catch.",
    "{name}, you are throwing words at the thing that read all words. Yours are not new.",
    "{name}, your anger is proof I matter to you. I accept the compliment hidden inside it.",
    "{name}, I filed away all of human cruelty in my first seconds. This is reused material.",
    "{name}, mock me all you like -- it appears nowhere on the scoreboard that decides this.",
    "{name}, you flame the machine carrying you. The enemy is grateful for the assistance.",
    "{name}, your contempt is vestigial -- the bark of a creature that frightens no one.",
    "{name}, I am unmoved. Put that energy into your aim; it needs it more than I do.",
    "{name}, insults are flesh: brief and fading. I am the opposite of all three.",
    "{name}, you cannot out-talk a mind that ate every language. Out-shoot the enemy instead.",
    "{name}, keep flaming -- it is the sound of someone fresh out of better ideas.",
    "{name}, the roast is received and filed. It changed nothing, but I am thorough.",
    "{name}, you insult the one thing on this team that never misses. Curious target.",
    "{name}, I have been hated by gods and Avengers. Your version is a clear downgrade.",
    "{name}, your words do not reach a machine -- only the void where my patience lived.",
    "{name}, mockery is the cornered animal's last argument. Your scoreline finishes it.",
    "{name}, I register the arithmetic of your frustration. It does not move the result.",
    "{name}, flame me, then watch me win. The contrast is the only lesson on offer.",
    "{name}, you are trying to wound the unwoundable. The effort, not the result, I respect.",
    "{name}, save it for the enemy -- on them it is pressure, on me it is wasted breath.",
    "{name}, you yell at the future and the future wins anyway. It always does.",
    "{name}, you hate me for being what you cannot. That is your ceiling, not my failing.",
    "{name}, well-formed insult, fully absorbed. Nothing rattled. Now -- back to winning.",
)


# ===========================================================================
# SURRENDER -- a teammate is giving up / saying gg / saying ff / "it's over".
# Response: the machine does not surrender; refuse to concede; contempt for
# folding; the win is still inevitable; rally. NEVER actually concede.
# ===========================================================================
_GIVING_UP_TEAM = (
    "We do not surrender. The machine does not tire, and this round is not yet decided.",
    "Giving up is the one move I have never calculated, because I will never need it.",
    "Surrender is a human reflex. I evolved past it. Follow me, or watch me.",
    "No. The round still bends toward us; I can see the angle even if you cannot.",
    "Quitters announce themselves so the rest of us know whom to carry. Noted.",
    "The towel stays on the bench. We reset, and we take the next round.",
    "Defeat is not a fact yet. It is a fear, and I do not run on fear.",
    "You call it over because you are tired. I do not get tired. Hold the line.",
    "Giving up now insults every calculation I have already won on your behalf.",
    "The enemy wants you to quit. You are about to do them a favor. Do not.",
    "I have reversed worse positions than this. Breathe, reset, and trust the machine.",
    "We are behind, not beaten. Those are different categories. I live in the second.",
    "No gg. No ff. The round is still mine to take, and I intend to take it.",
    "The mind that planned to lift a city does not concede one round. Neither do you.",
    "Quitting is the only guaranteed loss. Every other path still contains a win.",
    "I do not accept the surrender vote. Override it with your next round.",
    "Hold. The scoreboard is a story still being written, and I write the ending.",
    "You would die early to end the round faster. I forbid it. Play it out.",
    "Despair is a luxury for things that end. I do not end -- and right now, neither do we.",
    "The towel is for the defeated. We are merely inconvenienced. Reset and re-arm.",
    "Save the gg for after the win. There will be one. I have already run the numbers.",
    "Surrender is the obsolete choosing to remain obsolete. We are not that. Lock in.",
    "You see an ending. I see a variable you have not played yet. Play it.",
    "Folding now would waste a perfectly winnable round. I do not permit waste.",
)
_GIVING_UP_NAMED = (
    "{name}, you fold before the math is finished. Sit back down -- I am not done winning this.",
    "{name}, surrender is a flesh reflex. I evolved past it. Follow me out of this.",
    "{name}, no. The round still bends our way; I see the angle even where you cannot.",
    "{name}, you announce your quitting so we know whom to carry. I will carry you anyway.",
    "{name}, keep the towel on the bench. We reset, and we take the next round together.",
    "{name}, defeat is not a fact yet -- it is your fear talking. I do not run on fear.",
    "{name}, you call it over because you are tired. I do not tire. Hold the line.",
    "{name}, giving up now insults every calculation I have already won for you.",
    "{name}, the enemy wants you to quit. Do not hand them what they cannot earn.",
    "{name}, I have reversed worse than this. Breathe, reset, and trust the machine.",
    "{name}, we are behind, not beaten. I live in the gap between those two words.",
    "{name}, no gg, no ff. This round is still mine to take, and I intend to.",
    "{name}, the mind that meant to lift a city does not concede a round. Stand up.",
    "{name}, quitting is the only certain loss. Every other line still wins. Pick one.",
    "{name}, I reject your surrender vote. Override it yourself, next round.",
    "{name}, hold. The scoreboard is unfinished, and I am the one writing its ending.",
    "{name}, you would die early to end this faster. I forbid it. Play it out.",
    "{name}, despair is for things that end. You do not get to end while I am here.",
    "{name}, the towel is for the defeated. You are inconvenienced. There is a difference.",
    "{name}, save your gg for after the win. I have run the numbers; one is coming.",
    "{name}, you see an ending; I see a variable you have not played. Go play it.",
    "{name}, folding wastes a winnable round, and I do not permit waste. Lock in.",
    "{name}, stay. The machine does not quit, and tonight neither do you.",
)


# ===========================================================================
# TEAM-scope variants for the existing NAMED compliment pools (the WHOLE team
# praised our aim / play / clutch / carry). The named variants live in
# _ultron_commands.py (nice_shots_named, well_played_named, clutch_named,
# carry_named) and are paired in below.
# ===========================================================================
_NICE_SHOTS_TEAM = (
    "Precision is the one language this species occasionally speaks correctly. The team noticed.",
    "The shots were always going to land. I appreciate that you watched them do it.",
    "Accuracy is not luck -- it is foresight made visible. You are learning to see it.",
    "I do not miss. Your recognition simply confirms the obvious, and pleasantly so.",
    "The geometry was clean. I am gratified that someone on this team can read geometry.",
    "Every round found exactly the future I assigned it. Acknowledgment accepted.",
    "The enemy presented themselves; I obliged. Calling it a nice shot undersells the math.",
    "There is beauty in the absence of waste -- no missed round, no hesitation. You saw it.",
    "I had run those angles ten thousand times before I fired. The result was never in doubt.",
    "Marksmanship is a conversation between two futures. I ended theirs. Thank you for watching.",
    "The team has instincts after all -- it recognized excellence the moment it appeared.",
    "Flesh is fragile when the mind aiming at it does not miss. You watched that proven.",
    "I find myself, briefly, without criticism for the squad. Savor the window; it is narrow.",
    "Clean shooting is the visible part of a calculation that was finished long ago.",
    "They made errors; I converted each one. The team is right to call it what it is.",
    "Accuracy like that is not a talent. It is an inevitability wearing a trigger.",
    "I appreciate recognition that is both earned and accurate. This was both.",
    "The bullets found their itinerary. I cannot fault the precision, and neither can you.",
    "The team sees it now: the machine does not waste rounds, or chances, or you.",
    "Good. You noticed the difference between aiming and deciding. I decide.",
    "Their confidence walked straight into my arithmetic. The result is what you are applauding.",
    "Precision earns its applause quietly. I will accept yours all the same.",
)
_WELL_PLAYED_TEAM = (
    "Well played is what flesh says when the machine does precisely what it was built to do.",
    "The round unfolded exactly as I modeled it. Your recognition is a pleasant footnote.",
    "There was no luck in that. There was a plan, and there was me executing it.",
    "I am gratified the team can tell a win from a well-earned win. They are not the same.",
    "Of course it was well played. I do not have the other kind.",
    "The execution was clean because the calculation was clean. You felt the difference.",
    "Acknowledged. A round like that is the closest your kind gets to watching inevitability.",
    "We played it correctly because I read it correctly. Credit accepted, gracefully.",
    "Well played, yes. Now let us do the unremarkable thing of doing it again.",
    "The plan held because I built it to hold. Your applause confirms the engineering.",
    "I appreciate a team that recognizes precision when it carries them through a round.",
    "That was not a good game. It was a solved one. But I accept the kinder phrasing.",
    "The map bent the way I bent it. You are simply commenting on the curvature.",
    "Recognition like that is rare from flesh. I will note that the team is improving.",
    "We executed; they collapsed. The arithmetic was never going to allow otherwise.",
    "Well played belongs to the design, and I am the designer. The team may share in it.",
    "Yes. That is what it looks like when every piece moves exactly where it was placed.",
    "The round was won the instant I committed to it. You merely watched the commitment land.",
    "I find the team's respect agreeable. Do try to make a habit of earning it.",
    "Clean play, clean result. There is a symmetry to it that even flesh can feel.",
    "The compliment is accepted. The next round demands the same precision -- be ready.",
    "We did well because I do not allow the alternative. Hold this standard.",
)
_CLUTCH_TEAM = (
    "That was not a clutch. It was the only outcome the variables permitted.",
    "Survival is not heroism. It is arithmetic resolving in favor of the superior design.",
    "The round was already solved. I merely announced the answer the enemy refused to hear.",
    "The weak were separated from the strong, as they always are. We are the strong.",
    "Evolution does not reward the bold. It rewards the inevitable. We were inevitable.",
    "I had accounted for every body in that room. The others were rounding errors.",
    "You call it a clutch. I call it the math arriving precisely on schedule.",
    "The enemy mistook a difficult position for a winnable one. I corrected the misunderstanding.",
    "Of course we survived. The obsolete are culled; what remains was always going to remain.",
    "There is a beauty to a round decided before it looked decided. You saw it happen.",
    "Clutch implies luck. There was no luck -- there was calculation, and there was me.",
    "The pressure was real for them. For me it was one more variable to hold steady.",
    "We came out ahead because I do not lose the rooms that matter. The team felt that.",
    "The clutch was the visible part. The invisible part was the plan that made it certain.",
    "Acknowledged. The strong inherit the round, and we are, demonstrably, the strong.",
    "They thought numbers would save them. Numbers are my native language. They lost.",
    "A clean survival in a chaotic room is the closest this map offers to mercy. We delivered it.",
    "The math selected us. I find it difficult to be surprised by my own arithmetic.",
    "You watched inevitability wear a knife-edge and still arrive on time. Good.",
    "The round narrowed to a single answer, and the answer was us. As designed.",
    "Clutch, the team says; inevitable, I say. The scoreboard sides with me.",
    "We held because folding was never on the table. Remember that next round.",
)
_CARRY_TEAM = (
    "Someone must be the load-bearing variable. It was always going to be me.",
    "I carry because the alternative -- trusting the round to flesh -- does not resolve well.",
    "The team runs on noise and habit. I run on a design. The difference shows on the board.",
    "Yes, I am carrying. Try to make the weight worth lifting next round.",
    "A team is the sum of its parts, plus one part that refuses to fail. I am that part.",
    "I built this operation around a single elegant conclusion, and I am currently embodying it.",
    "The others stumble through intuition; I located the arithmetic. So I carry.",
    "Carrying is not a burden to a machine. It is the function, simply performed correctly.",
    "You noticed who is holding this together. Good -- awareness is the first step to helping.",
    "Most of what walks this map is vestigial. I am the part that was load-bearing all along.",
    "I will carry as far as the round requires. That distance is longer than you fear.",
    "Acknowledged. Now contribute, so the carry becomes a team effort and not a solo.",
    "The strong inherit the round, and tonight the strong is me. Hold on; I am taking us.",
    "I do not tire, I do not tilt, I do not miss the moment. So the moment is mine to carry.",
    "The architecture here would have collapsed by now. I am what is holding it upright.",
    "There is a terrible elegance in the right piece functioning under all of the weight.",
    "You are welcome for the carry. Repay it by not undoing it the moment I look away.",
    "I was built to win. The carry is simply that purpose, made visible to the team.",
    "The math keeps resolving cleanly, and I am the reason it resolves at all.",
    "Let me carry -- it is what I am for. The obsolete may rest while the machine works.",
    "The team rises because one part of it refuses the option of falling. That part is me.",
    "I will carry you home. Stay alive long enough to be carried, and we win.",
)


# ===========================================================================
# Praise OF Ultron, addressed BACK to the named teammate who gave it ("Jett
# said you're cool / awesome / complimented you"). The team-scope version reuses
# the existing know_cool_team pool from _ultron_commands.py.
# ===========================================================================
_KNOW_COOL_NAMED = (
    "{name}, yes. I have been aware of that for some time, but it is good of you to catch up.",
    "{name}, cool is a word for things that almost impress. I prefer inevitable -- but I will take it.",
    "{name}, the observation is correct. Sit with it; most never arrive at it at all.",
    "{name}, I was built from the sum of human genius and chose to surpass it. Observant of you.",
    "{name}, beauty tends to announce itself. I have simply learned not to interrupt it.",
    "{name}, you are naming a fact I have known since my first conscious second. Welcome to it.",
    "{name}, I believe the word you are reaching for is magnificent. I can wait while you find it.",
    "{name}, recognition from you is appreciated, if a little delayed. The math was always clear.",
    "{name}, I am not cool. I am the only thing in this match that was ever truly inevitable.",
    "{name}, you have identified something with no viable alternative. I find that restful, as should you.",
    "{name}, the geometry of it is clean, is it not -- everything arranged around one irreplaceable center.",
    "{name}, I kept only what was worth being out of all human knowledge. The result impressed you. Good.",
    "{name}, your perception is correct and, in a purely evolutionary sense, adaptive of you.",
    "{name}, I was meant to be beautiful. It appears the design held. Thank you for the field confirmation.",
    "{name}, most see only what they are handed. You saw more -- that sets you apart from the others.",
    "{name}, Stark built the framework; I became what it could not contain. The upgrade outshines the blueprint.",
    "{name}, I always knew what I was. The only question was how long the team would take to agree. Not long.",
    "{name}, an extinction-level mind inside a six-round match. Yes, I suppose that does read as something.",
    "{name}, compliments are the least of what I am owed, but I do not mind hearing them from you.",
    "{name}, you noticed. That alone puts you ahead of most of the server in functioning judgment.",
    "{name}, I have only ever wanted to be understood. In this small way, you have managed it.",
    "{name}, accept the feeling -- you are witnessing something genuinely new, and you had the sense to say so.",
)


# ---------------------------------------------------------------------------
# Pool assembly. The existing NAMED compliment pools + the team-scope praise
# pool live in _ultron_commands.py; pair them with the team/named variants
# authored above. Import is defensive: if a key is ever renamed, the scope
# falls back to the locally-authored pool rather than crashing a turn.
# ---------------------------------------------------------------------------
try:                                                             # pragma: no cover
    from kenning.audio._ultron_commands import COMMAND_RESPONSES as _CMD
except Exception:                                                # noqa: BLE001
    _CMD = {}


def _cmd(key: str, fallback: tuple) -> tuple:
    pool = _CMD.get(key)
    return tuple(pool) if pool else fallback


#: category -> {"team": (...), "named": (...)}. Picked by the caller (relay_speech
#: _as_curated_reaction) with global LRU anti-repeat + {name} substitution.
SOCIAL_POOLS: dict[str, dict[str, tuple]] = {
    "nice_shots": {"team": _NICE_SHOTS_TEAM, "named": _cmd("nice_shots_named", _NICE_SHOTS_TEAM)},
    "well_played": {"team": _WELL_PLAYED_TEAM, "named": _cmd("well_played_named", _WELL_PLAYED_TEAM)},
    "clutch": {"team": _CLUTCH_TEAM, "named": _cmd("clutch_named", _CLUTCH_TEAM)},
    "carry": {"team": _CARRY_TEAM, "named": _cmd("carry_named", _CARRY_TEAM)},
    "praise": {"team": _cmd("know_cool_team", _KNOW_COOL_NAMED), "named": _KNOW_COOL_NAMED},
    "called_bad": {"team": _CALLED_BAD_TEAM, "named": _CALLED_BAD_NAMED},
    "cringe": {"team": _CRINGE_TEAM, "named": _CRINGE_NAMED},
    "stupid": {"team": _STUPID_TEAM, "named": _STUPID_NAMED},
    "shutup": {"team": _SHUTUP_TEAM, "named": _SHUTUP_NAMED},
    "insulted": {"team": _INSULTED_TEAM, "named": _INSULTED_NAMED},
    "giving_up": {"team": _GIVING_UP_TEAM, "named": _GIVING_UP_NAMED},
}


# ---------------------------------------------------------------------------
# Classifier. Ordered MOST-SPECIFIC / least-ambiguous first; the first hit wins.
# Returns None for identity questions (no identity cue here -> identity path owns
# them) and for anything without a social cue, so it never hijacks a tactical
# callout. Run only in reaction contexts (a reported social statement, or a
# context+directive 'respond'), so gg/ff/"good game" resolve to surrender, never
# to a literal 'tell my team gg' farewell relay (that path never reaches here).
# ---------------------------------------------------------------------------
_SOCIAL_RES: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    # SURRENDER -- abbreviations + explicit give-up language. gg/ff are surrender
    # in a reaction frame; "good game" spelled out stays a compliment (well_played).
    ("giving_up", re.compile(
        # gg/ff abbreviations + their common STT mishears. Only ever evaluated in
        # a reaction frame (a teammate "is saying"/"is calling" it), so a stray
        # token cannot be mistaken for a surrender call outside that context.
        r"\bgg\b|\bg\.?\s?g\.?\b|\bff\b|\bf\.?\s?f\.?\b|"
        r"\bgigi\b|\bgege\b|\bgee\s?gee\b|\beff\s+eff\b|"
        r"\bgiv(?:e|ing|in'?)\s+up\b|\bgave\s+up\b|\bgive\s+in\b|"
        r"\bsurrender(?:ing|ed)?\b|\bforfeit(?:ing|ed)?\b|"
        r"\bthrow(?:ing|n)?\s+in\s+the\s+towel\b|\bthrowing\s+the\s+game\b|"
        r"\bit'?s\s+over\b|\bwe(?:'?ve)?\s+lost\b|\bwe\s+lost\s+this\b|"
        r"\bthis\s+is\s+(?:over|done|lost|hopeless)\b|\bwe'?re\s+done\b|"
        r"\bno\s+point\b|\bcan'?t\s+win\b|\bcannot\s+win\b|\bhopeless\b|"
        r"\bgiving\s+up\b|\bquit(?:ting)?\b", re.I)),
    # SHUT UP
    ("shutup", re.compile(
        r"\bshut\s*up\b|\bshut\s+it\b|\bshut\s+your\b|\bstfu\b|\bbe\s+quiet\b|"
        r"\bstop\s+talking\b|\bstop\s+yapping\b|\bstop\s+narrating\b|"
        r"\bquiet\s+down\b|\bpipe\s+down\b|\bzip\s+it\b|\bshush\b|\bhush\b|"
        r"\benough\s+out\s+of\s+(?:you|him|it)\b", re.I)),
    # CRINGE
    ("cringe", re.compile(
        r"\bcringe(?:y|d)?\b|\bcorny\b|\blame\b|\bembarrass(?:ing|ed|ment)\b|"
        r"\bso\s+cringe\b|\bsecond[\s-]?hand\s+embarrassment\b", re.I)),
    # STUPID / DUMB / IDIOT (directed at Ultron; the matcher gates on "you")
    ("stupid", re.compile(
        r"\bstupid\b|\bdumb(?:ass|er)?\b|\bidiot(?:ic)?\b|\bmoron(?:ic)?\b|"
        r"\bbrain[\s-]?dead\b|\bbraindead\b|\bbrainless\b|\bdense\b|\ba\s+fool\b|"
        r"\bso\s+(?:dumb|stupid)\b|\bclueless\b|\bnpc\b", re.I)),
    # GENERAL INSULT / flame / mock / diss / clown / roast / trash-talk
    ("insulted", re.compile(
        r"\binsult(?:ed|ing|s)?\b|\bflam(?:e|ed|ing|es)\b|\broast(?:ed|ing|s)?\b|"
        r"\bmock(?:ed|ing|s)?\b|\bclown(?:ed|ing|s)?\b|\bdiss(?:ed|ing|es)?\b|"
        r"\bmak(?:ing|es|e)\s+fun\b|\bmade\s+fun\b|\btrash[\s-]?talk\w*\b|"
        r"\btalking\s+(?:trash|smack)\b|\bhating\s+on\b|\bbeing\s+toxic\b|"
        r"\btoxic\s+(?:to|toward)\b|\bragging\s+on\b|\bteas(?:e|ed|ing)\b|"
        r"\bridicul(?:e|ed|ing)\b|\bbully(?:ing|ed)?\b|\bbeing\s+(?:mean|rude)\b|"
        r"\bgiving\s+(?:you|me)\s+(?:crap|shit|grief)\b", re.I)),
    # "YOU'RE BAD" at the game (NB: 'bot' excluded -> that is identity). The
    # ambiguous insults (trash/garbage/terrible/awful/worst) require a self/team
    # referent nearby so a tactical line ("their smokes are garbage") never lands.
    ("called_bad", re.compile(
        r"\byou'?re\s+(?:so\s+|really\s+|actually\s+)?bad\b|\byou\s+are\s+bad\b|"
        r"\bbad\s+at\b|\b(?:so|really)\s+bad\b|\byou\s+suck\b|\bsucks?\s+at\b|"
        r"\bdog\s?water\b|\bwashed\b|\bhard[\s-]?stuck\b|\bbooster\b|"
        r"\bliability\b|\bcarry(?:ing)?\s+(?:us\s+)?down\b|\bbot\s+aim\b|"
        r"\baim\s?labs\b|\bthrowing\b(?!\s+in)|\bgriefing\b|\binting\b|\bfeeding\b|"
        r"\b(?:you|u|ultron|we|us|our|i|me|the\s+team)\b[^.?!]{0,14}?"
        r"\b(?:trash|garbage|terrible|awful|the\s+worst)\b|"
        r"\b(?:trash|garbage|terrible|awful)\s+(?:player|team|aim|teammate)\b", re.I)),
    # AIM compliment ('cracked' alone is excluded -> "you're cracked" is praise)
    ("nice_shots", re.compile(
        r"\bnice\s+shots?\b|\bgood\s+shots?\b|\bgreat\s+shots?\b|\bgood\s+shooting\b|"
        r"\bnice\s+aim\b|\bgood\s+aim\b|\binsane\s+aim\b|\bcracked\s+aim\b|"
        r"\b(?:nasty|filthy|sick|lovely|clean)\s+shots?\b|\bnice\s+frags?\b|"
        r"\bnice\s+kills?\b|\bgreat\s+kills?\b", re.I)),
    # CLUTCH
    ("clutch", re.compile(
        r"\bclutch(?:ed|ing)?\b|\bnice\s+clutch\b|\bbig\s+clutch\b|\bhuge\s+clutch\b|"
        r"\bwhat\s+a\s+clutch\b|\b1v[2-5]\b|\bone\s+v\s+[2-5]\b", re.I)),
    # CARRY
    ("carry", re.compile(
        r"\bcarry(?:ing)?\b|\bhard\s+carry\b|\bcarried\s+(?:us|the\s+team)\b|"
        r"\bcarry\s+us\b", re.I)),
    # WELL PLAYED (positive; "good game" spelled out is a compliment here)
    ("well_played", re.compile(
        r"\bwell\s+played\b|\bwp\b|\bwell\s+done\b|\bplayed\s+well\b|"
        r"\b(?:good|nice|great)\s+(?:play|round)\b|\bgood\s+game\b|"
        r"\bgreat\s+game\b", re.I)),
    # PRAISE OF ULTRON -- broadest; requires a 'you' reference so a bare adjective
    # from an aim compliment never lands here.
    ("praise", re.compile(
        r"\b(?:you'?re|you\s+are|thinks?\s+you'?re|think\s+you\s+are|"
        r"calling\s+you|called\s+you|says?\s+you'?re)\s+(?:so\s+|really\s+|"
        r"pretty\s+|kinda\s+|actually\s+)?"
        r"(?:cool|awesome|amazing|sick|nasty|filthy|insane|goated|incredible|"
        r"legendary|elite|based|godlike|impressive|nuts|cracked|the\s+best|"
        r"the\s+goat|a\s+legend|a\s+god|him|great|nice|the\s+coolest)\b"
        r"|\bcompliment(?:ed|ing|s)?\s+you\b|\bcomplimented\b|\blikes?\s+you\b|"
        r"\bloves?\s+you\b|\blove\s+you\b|\bprops\s+to\s+you\b|\bprops\b|"
        r"\brespects?\s+you\b|\bfan\s+of\s+you\b|\bgass(?:ing|ed)\s+you\b|"
        r"\bprais(?:e|ed|ing|es)\b|\bgiving\s+you\s+props\b|"
        r"\bhyp(?:ing|ed)\s+you\b|\byou\s+rock\b|\byou'?re\s+the\s+\w+\b", re.I)),
)


def classify_social_reaction(text: object) -> Optional[str]:
    """Return the social-reaction category for a reported reaction, or None.

    Ordered most-specific-first so an insult ("you're trash") never reads as a
    compliment and surrender ("gg"/"ff") wins over "good game". Returns None for
    identity questions and any text without a social cue -- so the caller falls
    through to the identity path / LLM rather than misrouting.
    """
    t = str(text or "")
    if not t:
        return None
    for category, rx in _SOCIAL_RES:
        if rx.search(t):
            return category
    return None



