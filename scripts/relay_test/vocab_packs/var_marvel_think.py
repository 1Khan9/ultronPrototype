"""New LLM-routed pathways (2026-06-16): Marvel questions (pipeline C) and the
'...think and respond' arbitrary-routing trigger (pipeline D). Full post-wake
utterances -- used VERBATIM by the corpus (registered in corpus_packs
_VERBATIM_PACKS), since the routing depends on the exact reported-speech frame.
"""

_AGENTS = ("Jett", "Sage", "Reyna", "Brimstone", "Omen", "Killjoy", "Cypher",
           "Sova", "Phoenix", "Viper", "Breach", "Fade", "Skye", "Neon",
           "Chamber", "KAY/O", "Gekko", "Yoru", "Astra", "Harbor")

_MARVEL_TOPICS = (
    "tony stark", "iron man", "the avengers", "vision", "jarvis", "thanos",
    "captain america", "thor", "the hulk", "scarlet witch", "wanda",
    "quicksilver", "sokovia", "the mind stone", "your movie", "your film",
    "loki", "black widow", "hawkeye", "spider-man",
)
_MARVEL_VERBS = ("mentioned", "asked about", "brought up", "said something about",
                 "was talking about", "asked you about", "just mentioned")
_MARVEL_CLAIMS = (
    "said he hated your movie", "thinks you look like iron man",
    "said the avengers beat you", "asked if you regret killing jarvis",
    "said you're just a knockoff of tony stark", "asked what sokovia was like",
    "thinks vision is cooler than you", "said your plan was stupid",
    "asked if you miss the twins", "said thanos is scarier than you",
)
_THINK_QS = (
    "what is the best agent on ascent", "should we ban icebox",
    "what is the meaning of life", "how far away is the moon",
    "who is the best duelist right now", "what is the fastest way to rank up",
    "is the vandal better than the phantom", "what should I eat for dinner",
    "what time is it in tokyo", "why is the sky blue",
    "do you think we can win this", "what is your favorite map",
    "how many rounds do we need", "what is the capital of france",
    "is a operator worth buying on eco", "what is the best crosshair",
)

ITEMS = []

# Pipeline C -- Marvel "X mentioned/asked about Y, respond"
for i, ag in enumerate(_AGENTS):
    topic = _MARVEL_TOPICS[i % len(_MARVEL_TOPICS)]
    verb = _MARVEL_VERBS[i % len(_MARVEL_VERBS)]
    ITEMS.append(f"{ag} {verb} {topic}, respond")
for i, claim in enumerate(_MARVEL_CLAIMS):
    ag = _AGENTS[i % len(_AGENTS)]
    ITEMS.append(f"{ag} {claim}, respond")
# team-scope + bare-respond Marvel
ITEMS += [
    "the team is asking about tony stark, respond",
    "my team wants to know if you regret jarvis, respond",
    "brimstone said he hated your movie, respond",
    "jett mentioned tony stark, respond",
    "someone asked about the avengers, respond",
    "the team brought up sokovia, respond",
]

# Pipeline D -- "...think and respond"
for i, q in enumerate(_THINK_QS):
    ITEMS.append(f"{q}, think and respond")
for i, q in enumerate(_THINK_QS[:8]):
    ag = _AGENTS[i % len(_AGENTS)]
    ITEMS.append(f"{ag} asked {q}, think and respond")
ITEMS += [
    "what is the best agent on ascent, think about it and respond",
    "should we save this round, ponder it and answer",
    "the team wants to know if we can win, think and respond",
    "tell my team what i should do here, think and respond",
    "is this a good time to push, think and respond",
]
