"""Curated SOCIAL-REACTION pathway (2026-06-16): a teammate's compliment / insult
/ surrender / praise reported to Ultron. Full post-wake utterances, used VERBATIM
(registered in corpus_packs _VERBATIM_PACKS).
"""

_AGENTS = ("Jett", "Sage", "Reyna", "Brimstone", "Omen", "Killjoy", "Cypher",
           "Sova", "Phoenix", "Viper", "Breach", "Fade", "Skye", "Neon",
           "Chamber", "Gekko", "Yoru", "Astra", "Harbor", "Miks", "Clove")

_COMPLIMENT = ("said nice shot", "said good shooting", "said well played",
               "said nice clutch", "said you're carrying", "said great job",
               "said you're cracked", "said you're insane")
_PRAISE = ("thinks you're cool", "said you're awesome", "just complimented you",
           "thinks you're the best", "said you're a legend", "thinks you're goated")
_INSULT = ("called you cringe", "called you stupid", "called you a moron",
           "just insulted you", "is flaming you", "is making fun of you",
           "told you to shut up", "said shut up", "is roasting you",
           "thinks you're bad", "said you're trash", "said you're washed")
_SURRENDER = ("is giving up", "is saying gg", "is saying ff", "wants to ff",
              "is throwing in the towel", "thinks it's over")

ITEMS = []
for i, ag in enumerate(_AGENTS):
    ITEMS.append(f"{ag} {_COMPLIMENT[i % len(_COMPLIMENT)]}")
    ITEMS.append(f"{ag} {_INSULT[i % len(_INSULT)]}")
for i, ag in enumerate(_AGENTS[:12]):
    ITEMS.append(f"{ag} {_SURRENDER[i % len(_SURRENDER)]}")
    ITEMS.append(f"{ag} {_PRAISE[i % len(_PRAISE)]}")
# explicit ", respond" variants (the directive form)
for i, ag in enumerate(_AGENTS[:10]):
    ITEMS.append(f"{ag} {_INSULT[i % len(_INSULT)]}, respond")
# team-scope reactions
ITEMS += [
    "the team thinks you are cool", "the team thinks you are bad",
    "the team just complimented you", "the team is flaming you",
    "the team is giving up", "the team is saying gg", "the team is making fun of you",
    "the team thinks you're cringe", "the whole team is praising you",
    "the team is roasting you, respond", "the team says you're washed",
    # surrender mishears for gg/ff
    "miks is saying g g", "chamber is saying eff eff", "neon is saying gigi",
]
