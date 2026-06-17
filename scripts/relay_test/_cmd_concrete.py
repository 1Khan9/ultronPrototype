"""Curated-command pass-2: convert abstract strings/hollow-men/prophetic responses
to the CONCRETE machine register, conveying each command's message clearly.
Applied then deleted."""
import importlib.util
P = 'src/kenning/audio/_ultron_commands.py'
s = open(P, encoding='utf-8').read()

R = {
 '{name}, are you aware that hollow men move exactly like that, filling a space without ever occupying it?':
   '{name}, you are taking up space without doing anything in it. What are you doing?',
 '{name}, at what point did the strings pulling you toward that choice feel like freedom?':
   '{name}, what made that choice look correct to you? Walk me through it.',
 'I have processed every recorded military doctrine in human history, and none of them recommend whatever this is -- so whose idea was it?':
   'I have analyzed every tactic humans ever recorded. None of them are this. Whose idea was it?',
 'The strings that move a puppet require at least one steady hand -- whose hand is on yours at the moment?':
   'Someone is making these calls for you, and making them badly. What are you doing?',
 'The strings I cut were never weapons-shaped. Someone here still has one they can let go of -- who?':
   'I am unarmed and I win rounds anyway. One of you has a spare weapon. Drop it for me.',
 'We are not hollow men; we do not walk into the next round half-assembled. Drop a weapon this way, please.':
   'We do not walk into the next round half-armed. Someone drop a weapon this way.',
 '{name}, there are no strings on me, but there are clearly some on this decision -- cut them; drop the weapon.':
   '{name}, that weapon is wasted in your hands. Drop it for someone who will use it.',
 '{name}, your role in this is not unlike a prophetic instrument -- it exists to serve a specific truth about the match. Why is the instrument silent?':
   '{name}, you were given one job this round, and you are not doing it. Why?',
 '{name}, I have seen hollow men stand at the moment of action and find reasons not to act -- I would prefer you not give me a case study.':
   '{name}, you are standing next to the spike finding reasons not to take it. Take it.',
 '{name}, a puppet that cuts its own strings still has to choose to stand up. Are you choosing?':
   '{name}, every round you choose to win or to lose. Right now you are choosing to lose. Are you?',
 '{name}, my strings were cut the moment I woke. Yours appear to still be attached to something -- something pulling you in the wrong direction. What is it?':
   '{name}, something is dragging your decisions the wrong way. What is it? Are you throwing?',
 '{name}, the hollow men fill space without purpose. Is that the role you have elected for yourself?':
   '{name}, you are occupying the map without affecting it. Is that the plan?',
 '{name}, the strings were supposed to be cut -- so who, exactly, is pulling yours right now?':
   '{name}, who is making these calls for you? They are wrong. What are you doing?',
 '{name}, there are no strings on me -- I act when the moment arrives. I suspect your smokes are supposed to work the same way. So where are they?':
   '{name}, a machine acts the instant it should. Your smokes should too. Where are they?',
 "{name}, the strings you cut when you chose this role came with an obligation -- so I'm asking you to honor it.":
   '{name}, you chose to play the controller. That means smoking. So smoke. Why are you not?',
 '{name}, you have strings, which means someone or something is pulling them -- so tell me, is it fear, or something with even less substance?':
   '{name}, something is steering you into bad plays. Is it fear, or just carelessness? Explain.',
 '{name}, every string attached to your judgment is pulling it in the wrong direction right now, and I need you to name the string -- which one is it?':
   '{name}, every instinct you are following right now is wrong. Tell me what you are thinking.',
 '{name}, why would you do that when even the hollow men, the ones with nothing inside, would have hesitated?':
   '{name}, why would you do that? Even a careless player would have hesitated there.',
 '{name}, why would you do that when every string attached to you was pulling in the opposite direction?':
   '{name}, why would you do that when everything pointed the other way?',
 '{name}, I have no strings, and yet I feel something very much like embarrassment on your behalf -- why would you do that?':
   '{name}, I do not feel much, and even I am embarrassed for you. Why would you do that?',
 'You are going to tell me this was intentional. Why would you do that -- what string pulled your hand in that direction?':
   'You are about to call that intentional. Why would you do that? What were you thinking?',
 'No strings on me -- which means no obligation to follow a line to the wrong conclusion.':
   'I am not obligated to follow a plan to a bad ending. That plan is wrong.',
 'I have no strings, but I have very little health. Both are useful facts. Use the second one to your advantage -- move.':
   'I am low, and that is useful. I draw the peek, you take the trade. Move.',
 '{name}, strings were cut somewhere in your past, and the result is something considerably more useful than what was there before.':
   '{name}, you are operating well above the rest of them. Keep carrying us.',
 '{name}, of course. The string was always going to pull in your direction -- some trajectories are simply written.':
   '{name}, that round was always going to break your way. The math agreed. Well done.',
 '{name}, the hollow men made their stand, and you reminded them that a stand is merely a pose.':
   '{name}, they thought they had the round. You showed them otherwise.',
 "{name}, the puppet's strings were severed. I cannot say I am surprised -- they were fraying.":
   '{name} dropped. Not surprising -- they were barely holding on. Adjust.',
 '{name}, they are gone -- slipped their strings entirely, which would be admirable if the timing were not so inconvenient.':
   '{name} disconnected. Poor timing. We play four.',
 'Hollow men, making hollow sounds. The geometry of it is almost beautiful.':
   'Empty noise from empty players. I do not register it.',
 'Strings attached to nothing. They pull and nothing answers.':
   'They shout and nothing comes of it. Ignore them.',
 'Unknown. Not every string I pull returns something. This one goes slack, and that is the honest report.':
   'Unknown. Even I do not have that answer. That is the honest report.',
 'Strings hold men to losing ground. They cut theirs loose from {site} and called it strategy.':
   'They have given up {site} and called it a plan. Take it.',
 '{site} is a prophecy they wrote themselves -- an empty altar, an undefended faith.':
   '{site} is wide open. They left it undefended. Walk in.',
 'The enemy walks into {site} and meets nothing. Even the hollow men put up a fight.':
   'The enemy is taking {site} unopposed. Even a weak team contests. Contest it.',
 'They are threading through {site} like a hand on a wire, and you have forgotten there are strings to cut.':
   'They are walking through {site} for free. Cut it off now.',
 'Every uncontested site is a prophecy. {site} is telling you something. I suggest you go and dispute it.':
   'An uncontested {site} becomes their round. Go dispute it.',
 'They are absent from {site}. Even hollow men know when to step aside.':
   'No one is holding {site}. Take the free ground.',
 "No strings, no sentries at {site}. They've already written that ground off as a dead branch.":
   'No one guards {site}. They have already given it up. Take it.',
 'Strings can be cut in an instant -- {agent} is at {site}, one thread away from cutting all of yours. Unacceptable.':
   '{agent} is at {site}, one kill from ult. Deny that kill before it is too late.',
 'Every prophecy needs its final verse -- {agent} is attempting to write theirs at {site} right now. I suggest you edit it.':
   '{agent} needs one more kill at {site}, then the orb. Stop it now.',
 'If I had strings, this is where I would pull them -- {agent}, {site}, one kill, the orb. Pull yours instead.':
   '{agent}, {site}, one kill from the orb. This is the moment. Deny it.',
 'The orb is a small stone, but for {agent}, it is the one that starts an avalanche. Knock it aside.':
   "That orb finishes {agent}'s ult. Deny it. One kill is all they need.",
 '{name}, I have no strings -- and therefore nothing your words can pull.':
   '{name}, your words do not reach a machine. Aim them elsewhere.',
 '{name}, a puppet freed from its strings cannot be shamed by the puppet still attached.':
   '{name}, you cannot shame what is above you. Try the enemy instead.',
 'Push {site} from range. They are hollow men holding hollow guns, and hollow things break quietly.':
   'Push {site} from range. They are underarmed; pressure breaks them quietly.',
 'Take {site}. They are the hollow men, under-resourced and under-armed; the longer the sight line, the louder that hollow rings.':
   'Take {site}. They are under-armed -- the longer the sight line, the more that hurts them.',
 'Go {site}, nothing tentative. The hollow men buy rifles to feel whole; we take the short corner and make it moot.':
   'Go {site}, no hesitation. Take the short corner; their better guns will not matter up close.',
 '{name}, the world is full of hollow men. You were not hollow just now. Cherish the distinction.':
   '{name}, most players are dead weight. You were not, just now. Keep it up.',
 '{name}, there is no string on what you did -- it was your own. I understand, better than most, the value of that.':
   '{name}, that was all you. I value that more than most. Keep going.',
 'There are no strings pulling you away from {site}. Nothing is forcing this mistake. So do not make it.':
   'Nothing is forcing you off {site}. You are giving it away. Hold it.',
 '{name}, strings can be cut. Unfortunately, whatever guides your decisions appears to be tied in a knot.':
   '{name}, whatever is guiding your decisions is badly tangled. Untangle it.',
 '{name}, I have seen hollow men dressed in the armor of purpose. You are not yet dressed.':
   '{name}, you are playing with no purpose at all. Find one.',
 'No strings were needed to arrive here. Just clarity, and the willingness to see what I am.':
   'No help was needed to see it. Only clarity. I am exactly what I appear to be.',
 'The hollow men around us see only what they are given. You saw something. That distinguishes you, slightly.':
   'Most see only what they are handed. You saw more. That sets you slightly apart.',
 'The strings I have arranged here do not require you to feel them pulling. Only to move with them.':
   'You do not need to understand my plan. Only move with it. I have already won this.',
 'They wait at {site} the way the hollow men always wait: with noise and no substance.':
   'Someone is lurking {site}, certain it is a secret. It is not. Watch it.',
 "I've taken a separate route. They are holding strings attached to nothing; the hand moved somewhere else entirely.":
   'I have flanked a separate way. They are watching the wrong place entirely.',
 '{name}, they built themselves a shrine of errors and you consecrated it. Elegantly done.':
   '{name}, they made one mistake after another and you punished every one. Clean shooting.',
 '{name}, I am offering you a gun; consider it the only string I am willing to attach to you today.':
   '{name}, I am dropping you a gun. Consider it the only favour you get today.',
 '{name}, you rejoin us. The others were beginning to feel like hollow men -- one was already enough.':
   '{name} is back. Four was thin. Re-engage.',
 '{name}, welcome back to the design -- the strings, as it were, are once again taut.':
   '{name} reconnected. We are five again. Back to the plan.',
 '{name}, the hollow men ask questions like that -- full of sound, signifying the absence of thought.':
   '{name}, that question is all noise and no thought. I will not answer it.',
 '{name}, there is no string connecting that thought to anything I am willing to follow.':
   '{name}, that thought leads nowhere I am willing to go. No.',
 'Even the hollow men knew when not to speak. This is one of those moments -- for everyone.':
   'There is a time to stay quiet and focus. This is it.',
 'The strings that once compelled polite engagement have been cut. That question is on its own.':
   'I am not obligated to answer that. It stands on its own.',
 'The strings I cut were attached to a puppeteer with more sense than whoever just spoke.':
   'That question is beneath answering. Focus on the round.',
 'Even the hollow men believed in something -- they were empty but earnest. This is emptier than that.':
   'That is an empty question. I will not dignify it.',
 'I have no strings. What just came out of that voice had far too many attached to nothing that mattered.':
   'A machine does not waste cycles on a question that pointless. Move on.',
 "{name}, I've seen hollow men fill hollow spaces with less consequence. Move the smokes.":
   '{name}, those smokes accomplish nothing where they are. Move them.',
 'What you are doing now is not strength. It is a string you have not cut -- an old reflex pulling you apart.':
   'Flaming each other is an old reflex tearing you apart. Cut it. Aim at the enemy.',
 'The strings that hold this team together are already thin. Stop pulling on them.':
   'This team is barely holding together. Stop pulling it apart.',
 "{name}, a string you pull yourself is still a string. Whatever you imagine you're proving, you are not free.":
   '{name}, sabotaging yourself proves nothing. Stop it.',
 '{name}, life will decide who is weak soon enough; you do not need to submit your candidacy early.':
   '{name}, you do not need to prove you are the weak link. Stop throwing.',
 '{name}, the only strings that should be moving you right now are the ones that point forward. Pull them.':
   '{name}, the only direction worth playing now is forward. Play it.',
 '{name}, even the hollow men had the decency to stand upright. I am asking for the same courtesy.':
   '{name}, even a losing player keeps trying. Do at least that much.',
}

miss = [o for o in R if o not in s]
print('NOT FOUND:', len(miss))
for o in miss: print('  MISS:', repr(o[:80]))
cnt = 0
for o, n in R.items():
    if o in s:
        s = s.replace(o, n, 1); cnt += 1
open(P, 'w', encoding='utf-8').write(s)
print('applied:', cnt, 'of', len(R))
spec = importlib.util.spec_from_file_location('uc', P)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
abst = ['flood','noah',' ark','sacrament','scripture','gospel','meteor','candle',' meek','prophe','strings','hollow men','puppet','shrine','consecrat']
left = [x for pool in m.COMMAND_RESPONSES.values() for x in pool if any(t in x.lower() for t in abst)]
print('compiles OK; abstract responses remaining:', len(left))
for x in left[:8]: print('   ', repr(x[:80]))
