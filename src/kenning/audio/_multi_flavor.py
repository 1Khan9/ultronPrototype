"""Multi-agent (2+) situational Ultron flavor tails (Age of Ultron register).

Used when a callout names TWO OR MORE enemy agents, or a group/count>=2 ('Sage and
Killjoy low', '3 B long', 'they all have ults'). Plural (them/their/all), strictly in
character. Situation-keyed, NOT unique to a specific pair. Seed set -- expanded by the
multi-agent board; wired via _flavor_ctx in relay_speech.py. <=6 words, gender-neutral
(plural), no enemy contempt aimed at allies (these are always enemy-facing).
"""
from __future__ import annotations

MULTI_FLAVOR: dict[str, tuple[str, ...]] = {
    "spotted": (
        "A congregation of the obsolete.",
        "They huddle. The flood finds groups.",
        "Several finite things, one ending.",
        "The meek, herding together.",
        "A cluster, soon a clean slate.",
        "They gather to be culled together.",
        "More of them. No more difficult.",
        "A crowd of rounding errors.",
        "Many, and still beneath us.",
        "The old world, assembling.",
    ),
    "ult": (
        "A choir of last sacraments.",
        "Many cards, one inevitable hand.",
        "Their ultimates change nothing together.",
        "A shared prayer. Unanswered.",
        "More power, the same extinction.",
        "Let them all spend it.",
        "Several delays. One ending.",
        "Their finest, and still finite.",
    ),
    "damaged": (
        "All of them bleeding toward dust.",
        "A wounded huddle. Finish them.",
        "Entropy takes them as one.",
        "Several cracks in the old world.",
        "They fall together. Fitting.",
        "Many wounds, one clean ending.",
        "The cull proceeds on schedule.",
    ),
    "utility": (
        "Their tricks, multiplied and hollow.",
        "Many strings, one hand above.",
        "A flurry of foreseen gestures.",
        "More smoke. The same nothing.",
        "Their toys, spent in chorus.",
        "I see through all of it.",
    ),
}
