"""SIMPLE yes/no vs VERBOSE agreement/disagreement split (2026-06-16). Full
post-wake utterances, used VERBATIM (registered in corpus_packs _VERBATIM_PACKS).
"""

_NAMES = ("Brimstone", "Skye", "Sage", "Jett", "Omen", "Killjoy", "Cypher",
          "Sova", "Phoenix", "Viper", "Reyna", "Clove")

ITEMS = []
# SIMPLE yes/no (factual) -- bare commands
for n in _NAMES:
    ITEMS.append(f"tell {n} yes")
    ITEMS.append(f"tell {n} no")
ITEMS += [
    "say yes", "say no", "just say yes", "just say no",
    "tell my team yes", "tell my team no", "tell the team yes", "tell the team no",
    "answer is yes", "answer is no",
]
# VERBOSE agreement
_AGREE = ("good idea", "good call", "great call", "great idea", "solid call",
          "smart play", "that's the play", "makes sense", "I'm down", "sounds good",
          "I agree", "I do agree", "agreed")
for i, n in enumerate(_NAMES):
    ITEMS.append(f"tell {n} that's a {_AGREE[i % len(_AGREE)]}"
                 if _AGREE[i % len(_AGREE)].endswith("idea")
                 or _AGREE[i % len(_AGREE)].endswith("call")
                 else f"tell {n} {_AGREE[i % len(_AGREE)]}")
for a in _AGREE:
    ITEMS.append(f"tell my team {a}")
# VERBOSE disagreement
_DISAGREE = ("bad idea", "terrible idea", "awful idea", "horrible idea",
             "stupid idea", "dumb idea", "the dumbest idea", "bad call",
             "that's a mistake", "I disagree", "I don't agree", "I do not agree")
for i, n in enumerate(_NAMES):
    ITEMS.append(f"tell {n} that's a {_DISAGREE[i % len(_DISAGREE)]}"
                 if "idea" in _DISAGREE[i % len(_DISAGREE)]
                 or "call" in _DISAGREE[i % len(_DISAGREE)]
                 else f"tell {n} {_DISAGREE[i % len(_DISAGREE)]}")
for d in _DISAGREE:
    ITEMS.append(f"tell my team {d}")

# Identity meta-questions addressed (the curated identity pools, addressee-adapted)
_IDENT = ("are you a bot", "are you a soundboard", "are you a streamer",
          "are you a voice changer", "are you a real person", "are you a recording",
          "who is controlling you", "do you have strings")
for i, n in enumerate(_NAMES[:8]):
    ITEMS.append(f"{n} asked if you {_IDENT[i % len(_IDENT)][7:]}, respond"
                 if _IDENT[i % len(_IDENT)].startswith("are you")
                 else f"{n} asked {_IDENT[i % len(_IDENT)]}, respond")
ITEMS += [
    "the team is saying you are a voice changer, respond",
    "sage asked if you are a sound board, respond",
    "the team wants to know if you are a streamer",
    "reyna asked if you are a bot, respond",
    "the team thinks you are a recording, respond",
]
