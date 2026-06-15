"""Exemplar command libraries for the semantic command router.

Each ROUTE FAMILY is defined by a curated set of canonical example commands.
The router embeds the (post-normalizer) utterance and routes it to the family
whose best exemplar is most similar -- but ONLY when it clears that family's
threshold AND beats the runner-up by a margin; otherwise it ABSTAINS to the LLM.

Design rules (from the research board):
  * exemplars are SPECIFIC + DISCRIMINATIVE -- phrasings unique to their family
    so a Spotify line never looks like a callout, etc.;
  * the CONVERSATIONAL family is a first-class competitor (the abstention
    anchor) -- if an utterance is closest to these, it goes to the LLM;
  * families map to EXISTING handlers (this router only makes the COARSE
    decision for utterances the exact matchers missed; the chosen handler still
    does its own fine matching + slot extraction), so nothing downstream is
    bypassed or lost.

Keep these lists broad (many surface forms per family). They are embedded ONCE
at startup; adding/removing exemplars is cheap.
"""

from __future__ import annotations

# --- TEAM CALLOUT: relayed to the team (enemy spotting, abilities, utility,
#     self-status, orders, morale, soundboard). Routes to the relay handler. ---
_TEAM_CALLOUT = [
    # enemy spotted (agent x location)
    "tell my team there's a Jett on A main",
    "enemy Sova in heaven",
    "their Reyna is pushing B",
    "Cypher is holding long",
    "there's a Raze on B site",
    "tell the team Phoenix on A",
    "warn my team Omen is lurking",
    "there's a Chamber holding long",
    "I see a Breach on A",
    "two enemies B main",
    "one in heaven",
    "three of them pushing B",
    "they're stacked on A",
    "nobody's on B",
    "enemy on the flank",
    "Jett and Reyna both on A",
    # abilities / ult / utility
    "their Neon has ult",
    "Sova has his ult",
    "Jett ulted",
    "Killjoy has her ult",
    "Raze has her ult",
    "Viper ult",
    "their Omen has ult",
    "KAY/O knife is up",
    "Killjoy dropped her turret",
    "there's a Sova drone in B",
    "Cypher cage on A",
    "Viper wall is up",
    "there's a Breach stun",
    "Sage walled mid",
    "smoke just popped on A",
    "Brimstone smoked B",
    # self status
    "I'm flanking through mid",
    "I'm pushing B",
    "I have A site",
    "I'm planting",
    "I'm low",
    "I'm one shot",
    "I died",
    "I'm rotating to A",
    "I'm holding angle",
    "I'm out of smokes",
    # orders to the team
    "rotate to A",
    "push B",
    "hold for picks",
    "save this round",
    "fall back",
    "play retake",
    "group up mid",
    "stack A",
    "plant for CT",
    "watch the flank",
    "be careful someone's lurking",
    # morale / greet / farewell
    "good game everyone",
    "we're winning this",
    "we lost that one",
    "nice round team",
    "let's lock in",
    "good luck have fun",
    # soundboard / verbatim relay
    "repeat to my team mic check one two",
    "tell my team rotating now",
    "say to my team spike is down",
    "call out a Raze on B",
    "tell my team to be careful",
]

# --- SPOTIFY: music playback control. Routes to the Spotify handler. ---
_SPOTIFY = [
    "play some Daft Punk",
    "put on some lo-fi",
    "throw on Metallica",
    "start playing Radiohead",
    "play despacito",
    "I want to hear Hotel California",
    "play the album Discovery",
    "play the playlist focus flow",
    "queue Blinding Lights",
    "add Toxicity to the queue",
    "play Californication next",
    "pause the music",
    "pause",
    "stop the music",
    "resume",
    "keep playing",
    "skip",
    "skip this song",
    "next song",
    "previous song",
    "go back a track",
    "restart the song",
    "start it over",
    "what's playing",
    "what song is this",
    "who sings this",
    "turn it up",
    "louder",
    "crank it up",
    "turn it down",
    "quieter",
    "set the volume to 40",
    "make the volume 60",
    "volume 70",
    "lower the volume by 10 percent",
    "raise the volume by 20",
    "turn it up by 15 percent",
    "mute",
    "unmute",
    "shuffle on",
    "shuffle off",
    "turn on shuffle",
    "repeat this song",
    "repeat off",
    "loop this",
    "like this song",
    "thumbs up",
    "save this track",
    "unlike this song",
]

# --- IDENTITY: who/what is Ultron. Routes to the greeting set-piece. ---
_IDENTITY = [
    "introduce yourself",
    "who are you",
    "what are you",
    "are you there",
    "you there",
    "say hello",
    "tell me who you are",
    "state your name",
    "what's your name",
    "identify yourself",
    "are you online",
    "are you ready",
    "introduce yourself to my team",
    "say hi to the squad",
]

# --- DESKTOP / AUTOMATION: refused while gaming (anticheat). ---
_DESKTOP_REFUSE = [
    "take a screenshot",
    "click on that",
    "click the button",
    "type hello",
    "open Discord",
    "open Chrome",
    "launch Spotify",
    "move the mouse",
    "minimize the window",
    "maximize this",
    "close that window",
    "switch to my browser",
    "scroll down",
    "open my email",
]

# --- CONVERSATIONAL: the ABSTENTION ANCHOR -> route to the LLM. Marvel/banter,
#     opinions, meta-questions, strategy talk, anything nuanced. These compete
#     with the deterministic families; if an utterance is closest here (or no
#     family is confident), it falls through to the conversational LLM. ---
_CONVERSATIONAL = [
    "tell me about Tony Stark",
    "tell me about Black Widow",
    "what do you think of the enemy team",
    "are we going to win",
    "are you a robot",
    "do you have strings",
    "what time is it",
    "what's the date",
    "tell me a joke",
    "what do you think about my aim",
    "how should I play this round",
    "what's the strategy here",
    "who's your favorite agent",
    "do you think we can comeback",
    "what's the meta right now",
    "are you sentient",
    "what's it like being an AI",
    "how are you feeling",
    "what should I buy this round",
    "do you believe in fate",
    "tell me something interesting",
    "what would Tony Stark do",
    "explain the spike timer to me",
    "why did we lose that round",
    "what's your opinion on Jett",
    "can you give me some advice",
    "what do you think happens next",
    "how good is the enemy duelist",
]

# Family -> exemplar list.  Order is only documentation; the router treats them
# as a flat set grouped by family name.
FAMILIES: "dict[str, list[str]]" = {
    "team_callout": _TEAM_CALLOUT,
    "spotify": _SPOTIFY,
    "identity": _IDENTITY,
    "desktop_refuse": _DESKTOP_REFUSE,
    "conversational": _CONVERSATIONAL,
}

# Families whose best match means "hand to the LLM" (no deterministic handler).
# Selecting one of these (or abstaining) routes to the conversational path.
ABSTAIN_FAMILIES = frozenset({"conversational"})

# Deterministic families that, when confidently chosen, the router dispatches to
# a handler (it never bypasses the handler's own matching). "spotify" is
# INTENTIONALLY EXCLUDED: the wide exact Spotify matcher runs first (L0) so
# Spotify misses are rare, and the Spotify exemplars here exist ONLY so a music
# command never mis-routes to a callout -- a Spotify-family hit simply abstains
# to the LLM. team_callout / identity / desktop_refuse have explicit router
# dispatch branches in the orchestrator.
DETERMINISTIC_FAMILIES = frozenset({
    "team_callout", "identity", "desktop_refuse",
})
