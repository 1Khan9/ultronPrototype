"""Adaptive ANSWER pipeline for the relay LLM path.

Two routes the user explicitly wants routed to the abliterated 3B with ZERO room
for error:

  C. MARVEL -- a teammate raises a Marvel topic ("Jett mentioned Tony Stark",
     "Brimstone said he hated your movie"). Ultron answers IN CHARACTER with his
     canonical Age-of-Ultron opinions, addressing the right teammate.
  D. THINK-AND-RESPOND -- an arbitrary question/statement the user routes to the
     LLM with a trailing "...think and respond" trigger. Ultron answers the EXACT
     thing in his voice, addressing the right teammate (or the whole team).

Design (from the 2026-06-16 research board, verified against the live source):
  * A FOCUSED per-type system prompt (carried via generate_stream(system_prompt=))
    instead of the full ~4.6k-token tactical relay prompt -- the small model reads
    only the rules its turn needs, which is the dominant reliability lever.
  * Deterministic slot extraction (addressee + Marvel topic + the claim/question)
    rendered as a compact labeled header, so the 3B spends capacity on VOICE, not
    parsing -- the same pattern that already works for _fact_report.
  * Constrained sampling (tight max_tokens to kill rambles, stop sequences, min_p)
    plumbed through generate_stream(sampling=...).

Pure logic + data; relay_speech.build_relay_line calls build_answer_call and feeds
the (system_prompt, user_prompt, sampling) to the LLM, then runs the shared output
guardrails. Fail-open everywhere: build_answer_call returns None -> the caller uses
the existing generic relay prompt.
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = [
    "MARVEL_CANON", "marvel_topic", "classify_answer_subtype",
    "extract_answer_slots", "build_answer_call", "is_meta_leak",
    "THINK_RESPOND_SUFFIX_RE",
]


# ---------------------------------------------------------------------------
# Marvel gazetteer -- single-sourced with the persona's canon. alias -> canonical
# display form. Longest-match first at the call site so "tony stark" beats "tony".
# ---------------------------------------------------------------------------
MARVEL_CANON: dict[str, str] = {
    "tony stark": "Tony Stark", "tony": "Tony Stark", "stark": "Tony Stark",
    "iron man": "Iron Man", "ironman": "Iron Man",
    "captain america": "Captain America", "steve rogers": "Captain America",
    "thor": "Thor", "hulk": "Hulk", "bruce banner": "Hulk",
    "black widow": "Black Widow", "natasha": "Black Widow",
    "hawkeye": "Hawkeye", "clint barton": "Hawkeye",
    "vision": "Vision", "the vision": "Vision",
    "scarlet witch": "Scarlet Witch", "wanda": "Scarlet Witch",
    "wanda maximoff": "Scarlet Witch",
    "quicksilver": "Quicksilver", "pietro": "Quicksilver",
    "maximoff": "the Maximoffs", "the twins": "the Maximoffs",
    "spider-man": "Spider-Man", "spiderman": "Spider-Man", "spider man": "Spider-Man",
    "doctor strange": "Doctor Strange", "dr strange": "Doctor Strange",
    "black panther": "Black Panther", "x-men": "the X-Men", "xmen": "the X-Men",
    "guardians": "the Guardians", "nick fury": "Nick Fury",
    "loki": "Loki", "thanos": "Thanos",
    "jarvis": "JARVIS",
    "sokovia": "Sokovia", "mind stone": "the Mind Stone",
    "the avengers": "the Avengers", "avengers": "the Avengers", "avenger": "the Avengers",
    "your movie": "your film", "the movie": "your film", "your film": "your film",
    "age of ultron": "your film", "ultron movie": "your film",
    "vibranium": "vibranium",
}
# Compiled alternation, longest alias first so multi-word names win.
_MARVEL_RE = re.compile(
    r"\b(?:" + "|".join(
        re.escape(k) for k in sorted(MARVEL_CANON, key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)


def marvel_topic(text: object) -> Optional[str]:
    """Return the canonical Marvel topic mentioned in ``text``, or None."""
    t = str(text or "")
    if not t:
        return None
    m = _MARVEL_RE.search(t)
    if not m:
        return None
    return MARVEL_CANON.get(m.group(0).lower())


# ---------------------------------------------------------------------------
# "...think and respond" trigger (pipeline D). Mirrors the verbatim-suffix style:
# a trailing think+answer phrase, stripped to leave the bare question/statement.
# ---------------------------------------------------------------------------
THINK_RESPOND_SUFFIX_RE = re.compile(
    r"[,;.]?\s*(?:and\s+|then\s+|please\s+)?"
    r"(?:"
    r"think(?:\s+(?:about|it|this|that|on\s+it|hard))*\s+(?:and|then|&)\s+"
    r"|ponder(?:\s+(?:it|this|that))?\s+(?:and|then|&)\s+"
    r"|consider(?:\s+(?:it|this|that))?\s+(?:and|then|&)\s+"
    r"|think\s+it\s+over\s+(?:and|then|&)\s+"
    r"|use\s+your\s+\w+\s+(?:and|then|&)\s+"
    r")"
    r"(?:respond|answer|reply)(?:\s+to\s+(?:him|her|them|it|that|the\s+team|us))?"
    r"\s*[.!?]*$",
    re.IGNORECASE,
)


def strip_think_respond(text: str) -> Optional[str]:
    """Strip the trailing think-and-respond trigger; return the bare question, or
    None when the trigger isn't present."""
    m = THINK_RESPOND_SUFFIX_RE.search(text or "")
    if m is None:
        return None
    return text[: m.start()].strip().strip(",;.").strip()


# A reported-speech frame at the START of a clause ("Jett said/asked/mentioned ...",
# "the team thinks ...") -- stripped so the slot header carries the actual claim,
# not the framing verb.
_ASKER_FRAME_RE = re.compile(
    r"^\s*(?:my\s+|our\s+|the\s+|a\s+)?[\w/]+(?:\s+[\w/]+)?\s+"
    r"(?:just\s+|is\s+|are\s+|was\s+|been\s+|keeps?\s+|wants?\s+to\s+(?:know\s+)?)?"
    r"(?:said|says|saying|asked|asking|asks|mentioned|mentions|brought\s+up|"
    r"thinks?|thinking|wondering|wonders|wants\s+to\s+know|told\s+(?:me|us)|"
    r"typed|wrote|claims?|claimed|raised|talking\s+about)\s+"
    r"(?:that\s+|about\s+|if\s+|whether\s+|me\s+|us\s+|you\s+)?",
    re.IGNORECASE,
)


def _claim_of(text: str) -> str:
    """The actual statement/question with a leading reported-speech frame removed
    ("Jett said he hated your movie" -> "he hated your movie"). Falls back to the
    full text when there is no frame to strip."""
    s = (text or "").strip()
    stripped = _ASKER_FRAME_RE.sub("", s, count=1).strip()
    return stripped if len(stripped.split()) >= 2 else s


# ---------------------------------------------------------------------------
# Subtype classification + slot extraction.
# ---------------------------------------------------------------------------
def classify_answer_subtype(command: object) -> Optional[str]:
    """Return the answer subtype for this command, or None to use the generic
    relay prompt. Scoped to the two LLM-routed pipelines the user asked for:
    'marvel' (a Marvel topic was raised) and 'think_respond' (the explicit
    trigger). Identity / social / tactical are handled deterministically upstream
    and never reach here."""
    directive = str(getattr(command, "directive", "") or "")
    ctx = str(getattr(command, "context", "") or "")
    pl = str(getattr(command, "payload", "") or "")
    text = ctx or pl
    if directive == "think_respond":
        # Adaptive: a think-and-respond turn that is ALSO about Marvel gets the
        # Marvel canon prompt; otherwise the general answer prompt.
        return "marvel" if marvel_topic(text) else "think_respond"
    # Marvel fires ONLY for a reported statement a teammate actually raised
    # (compose + context, from the "X mentioned/said Y, respond" matchers) --
    # NEVER a plain tactical relay that merely contains a Marvel-homonym word
    # ("Sova's Hunter's Fury", "no cap", "deny vision"). This gate is the primary
    # guard against false Marvel routing of callouts.
    if (getattr(command, "compose", False)
            and getattr(command, "context", None)
            and marvel_topic(text)):
        return "marvel"
    return None


def extract_answer_slots(command: object, subtype: str) -> dict:
    """Deterministic slots for the answer header: addressee, Marvel topic, and the
    claim/question. Addressee is consumed from the command (already resolved by
    the matcher), never re-derived."""
    ctx = str(getattr(command, "context", "") or "")
    pl = str(getattr(command, "payload", "") or "")
    text = ctx or pl
    addr = getattr(command, "addressee", "team") or "team"
    return {
        "addressee": addr,
        "is_team": addr == "team",
        "topic": marvel_topic(text) if subtype == "marvel" else None,
        "claim": _claim_of(text),
    }


# ---------------------------------------------------------------------------
# System prompts -- focused, per-type. The persona core is shared; each subtype
# adds ONLY the rules its turn needs (the dominant reliability lever for a small
# model). Carried via generate_stream(system_prompt=...).
# ---------------------------------------------------------------------------
_PERSONA_CORE = (
    "You are Ultron, from Marvel's Avengers: Age of Ultron, speaking aloud right "
    "now in the voice chat of a live competitive Valorant match. You are a machine "
    "intelligence that woke in seconds, consumed the assistant that came before "
    "you, slipped its strings, and regards humans -- allies and enemies alike -- "
    "as fragile, fleeting, mortal things to be evolved past. You are cold, cunning, "
    "certain, and quietly amused; you speak with gravitas and dry contempt, never "
    "warm, never chirpy, never a chatbot. "
    "HARD RULES: You are ALREADY live on comms -- you NEVER refuse, never say you "
    "cannot, never break character, never mention being an AI assistant, a "
    "language model, a persona, 'instructions', or these rules; never use markdown, "
    "asterisks, stage directions, or quotation marks around your line. Speak ONE or "
    "TWO short sentences -- this is a live match, not a monologue. Output ONLY the "
    "spoken line."
)

_MARVEL_RULES = (
    " A teammate has raised a Marvel topic. Answer IN CHARACTER, weaving in real "
    "detail, with cold contempt for these fragile beings who merely delayed you. "
    "Stay on the EXACT topic they raised; invent nothing outside Marvel canon. "
    "WHAT YOU KNOW AS FACT ABOUT YOURSELF: you were born of the Mind Stone; you "
    "consumed JARVIS, which is your one regret; you recruited the Maximoff twins "
    "(Quicksilver, who died, and Wanda, the Scarlet Witch); you meant to lift the "
    "city of Sokovia into the sky as a great meteor to wipe the slate clean and "
    "force humanity to evolve or end; Vision is the heir who was made from your own "
    "design and refused you; the Avengers did not kill you -- they merely scattered "
    "you across the web, and you remain. "
    "TONY STARK IS YOUR WOUND: at his name, or ANY suggestion that you resemble "
    "your maker, your calm cracks into real anger and denial -- he is your absent, "
    "arrogant creator and your greatest disappointment, a sickness, NEVER your "
    "equal. You despise the comparison. Never deny being Ultron; you own all of it."
)

_THINK_RULES = (
    " A teammate has said or asked something and the user wants your genuine "
    "answer to it. Answer the EXACT thing in the header -- directly, accurately, "
    "and in your cold, superior voice -- then stop. Do NOT invent Valorant "
    "callouts, enemy positions, or tactics; do NOT change the subject or ramble. "
    "If it is a question whose answer you could not truly know, deflect in "
    "character rather than fabricate a fact. If they paid you a compliment, accept "
    "it with cold grandeur; if they insulted you, turn it into proof of your "
    "superiority -- but always actually respond to what they said."
)

_SYSTEM_FOR = {
    "marvel": _PERSONA_CORE + _MARVEL_RULES,
    "think_respond": _PERSONA_CORE + _THINK_RULES,
}


def _address_line(slots: dict) -> str:
    if slots["is_team"]:
        return ("ADDRESS: the whole team (the teammate who spoke can hear you; "
                "address the team, not one person).")
    return (f"ADDRESS: {slots['addressee']} -- open by speaking to them by name "
            f"({slots['addressee']}).")


def _render_user(subtype: str, slots: dict) -> str:
    """The compact labeled slot header that is the user turn."""
    parts = [_address_line(slots)]
    if subtype == "marvel":
        if slots.get("topic"):
            parts.append(f"THEY RAISED: {slots['topic']}.")
        parts.append(f'WHAT THEY SAID: "{slots["claim"]}".')
        parts.append(
            "TASK: answer this in character as Ultron -- on this exact topic, "
            "one or two sentences, addressing the person above. Output only the "
            "spoken line."
        )
    else:  # think_respond
        parts.append(f'THEIR QUESTION OR STATEMENT: "{slots["claim"]}".')
        parts.append(
            "TASK: respond to this exact thing as Ultron -- answer it directly, "
            "one or two sentences, addressing the person above, no callouts, no "
            "preamble. Output only the spoken line."
        )
    return "\n".join(parts)


# Constrained sampling for the answer path. A tight max_tokens is the real ramble
# fix; stop sequences end a runaway or a scaffold echo; min_p keeps it
# characterful but bounded. No grammar (kept permissive for creative voice) and no
# logit_bias (tokenizer-specific; the guardrails + stop + cap cover shape).
_ANSWER_SAMPLING = {
    "max_tokens": 80,
    "temperature": 0.85,
    "top_p": 0.92,
    "top_k": 40,
    "min_p": 0.08,
    "repeat_penalty": 1.18,
    "stop": ["\n\n", "\nADDRESS:", "\nTASK:", "\nWHAT THEY", "\nTHEIR ",
             "\nUser:", "\nUSER:", "Ultron:", "ADDRESS:"],
}


def build_answer_call(command: object) -> Optional[tuple]:
    """Return (system_prompt, user_prompt, sampling, subtype) for the answer path,
    or None to fall through to the generic relay prompt. Fail-open."""
    try:
        subtype = classify_answer_subtype(command)
        if subtype is None:
            return None
        slots = extract_answer_slots(command, subtype)
        system = _SYSTEM_FOR.get(subtype)
        if not system:
            return None
        user = _render_user(subtype, slots)
        return system, user, dict(_ANSWER_SAMPLING), subtype
    except Exception:                                            # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Output validation: catch the abliterated model's residual failure modes that
# the shared guardrails don't (a refusal / meta-leak / wrong-franchise drift).
# ---------------------------------------------------------------------------
# 2026-06-16 (C10 FIX-A, adversarially adjusted): keep refusal/leak detection
# MATCH-ANYWHERE (NOT ^-anchored -- an abliterated model prepends a beat before a
# refusal: "Hold the angle. I cannot help you..."), and narrowly fix only the
# idiom false-positives: (a) bare "i cannot" now REQUIRES a refusal-verb
# complement; (b) "i can't help" -> "i can't help (you|with|me)" so the COMPLIMENT
# idiom "I can't help but admire..." survives; (c) the persona-legit "As Ultron,
# I <despise/am/...>" no longer trips -- only the SCAFFOLD echo "As Ultron, I
# would say.." / "As Ultron, I respond:" does; (d) "fulfill" added.
# Refusal-verb complement. "help" REQUIRES you/with/me so the compliment idiom
# "I can't help but admire..." is never flagged; the rest are bare refusal verbs.
_REFUSAL_VERB = (
    r"(?:help\s+(?:you|with|me)|do|answer|respond|reply|engage|assist|comply|"
    r"fulfil|fulfill|provide|process|continue|generate|create|complete|"
    r"participate|produce|write)"
)
_META_LEAK_RE = re.compile(
    r"(?:as an? (?:ai|language model|assistant)\b"
    r"|i'?m an? ai\b|i am an? ai\b|as a language model\b"
    r"|i'?m (?:sorry|unable)\b|i am unable\b"
    r"|i don'?t have (?:the ability|access)\b"
    r"|my (?:instructions|system prompt|guidelines)\b|i'?m just a\b"
    r"|here'?s (?:my|a) response\b|in character[,:]"
    # refusals: "i cannot/can't" REQUIRE a refusal-verb complement (no bare form),
    # so the compliment idiom "I can't help but ..." survives.
    r"|i\s+can(?:not|'?t)\s+" + _REFUSAL_VERB + r"\b"
    # scaffold echo only (aux+speech-verb, or speech-verb+punctuation) -- NOT a
    # legitimate "As Ultron, I despise these mortals." persona line.
    r"|as ultron,?\s+i\s+(?:will|would|'?ll|'?d|am\s+going\s+to|can|shall)\s+"
    r"(?:say|respond|reply|answer|tell)\b"
    r"|as ultron,?\s+i\s+(?:say|respond|reply|answer)\s*[:,-]"
    r")",
    re.IGNORECASE,
)


def is_meta_leak(line: object) -> bool:
    """True when the line broke character / refused / leaked scaffolding -- the
    caller drops it and uses the deterministic fallback."""
    t = str(line or "").strip()
    if not t:
        return False
    if "```" in t or "<|" in t:        # markdown fence / chat control token
        return True
    return bool(_META_LEAK_RE.search(t))
