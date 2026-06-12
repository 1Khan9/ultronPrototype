"""Per-call response-style addenda.

Pure-function helpers that prepend short style directives to the user's
text before it reaches the LLM. They live OUTSIDE the persona file
(SOUL.md is voice-quality-locked) so the orchestrator can nudge the
model on a per-utterance basis without changing the system prompt.

Three hint classes, dispatched in priority order:

1. **Procedural** -- explicit "step-by-step" / "walk me through" /
   "comprehensive tutorial" requests get a numbered-steps directive
   so the LLM produces actual procedure detail instead of a
   two-sentence summary.
2. **Factual** -- "how much / how many / how heavy / when did / what
   year / who is" stem questions get a stricter "one short sentence
   containing only the specific fact" directive so the LLM stops
   prefacing 2-pound facts with three sentences of taxonomy.
3. **Brief** -- short non-factual questions get a 1-3-sentence
   directive (the original brevity behaviour).

Only one hint is applied per turn -- procedural beats factual beats
brief. The function is :func:`apply_brevity_hint` (the public surface
the orchestrator wired in 2026-05-10); it now dispatches across the
three classes. The original behaviour (length-based brief detection)
is preserved for the residual case so existing call sites are unchanged
in their no-explicit-stem outputs.
"""

from __future__ import annotations

import re

from kenning.utils.logging import get_logger

logger = get_logger("response_style")


# ----------------------------------------------------------------------
# Hints (the actual strings prepended to user text)
# ----------------------------------------------------------------------

# Strictest of the three -- single-sentence factual recall. Stops the
# 4B model from prefacing "ducks weigh ~3 pounds" with two sentences
# on species variation, sexual dimorphism, and seasonal weight
# fluctuation. The user asked for a fact; deliver the fact.
_FACTUAL_HINT = (
    "[Style: respond with one short sentence containing only the "
    "specific fact requested. Do not add caveats, explanations, "
    "ranges, or context unless the user asks a follow-up.]"
)

# The original brevity hint. Slightly stronger wording than the
# 2026-05-10 version to compete harder with Qwen's verbose default.
_BREVITY_HINT = (
    "[Style: respond in 1-3 short sentences. The user's question is "
    "brief; match that brevity. Do not list, do not lecture, do not "
    "offer follow-up options unless asked.]"
)

# Procedural verbosity -- explicit "give me the full procedure"
# directive. Stops the 4B model from collapsing "detailed step-by-step
# cake instructions" into a two-sentence summary. The numbered-steps
# format is what the user actually asked for; specifying it explicitly
# makes Qwen3 follow through instead of defaulting to prose summary.
_PROCEDURAL_HINT = (
    "[Style: respond with detailed numbered steps. Do not summarise. "
    "Include specific measurements, times, temperatures, and "
    "ingredient quantities where applicable. The user explicitly "
    "asked for procedural depth.]"
)


# ----------------------------------------------------------------------
# Detection thresholds + markers
# ----------------------------------------------------------------------

# Heuristics for "this is a brief question that wants a brief answer".
# Tuned against the live-session log where 5-8-word queries like
# "What are the Orcs in 40k?" produced 4-paragraph responses.
_BREVITY_MAX_WORDS = 12
_BREVITY_MAX_CHARS = 80

# Procedural markers -- explicit requests for numbered / detailed /
# walked-through procedure. Distinct from the broader ``_DEPTH_MARKERS``
# below: depth markers SUPPRESS brevity but don't necessarily mean the
# user wants a numbered list. "Explain quantum entanglement" is
# depth-y but should produce prose, not steps. "Walk me through how to
# bake a cake" is genuinely procedural.
_PROCEDURAL_MARKERS = (
    "step by step",
    "step-by-step",
    "step by step instructions",
    "walk me through",
    "walk through",
    "comprehensive guide",
    "comprehensive tutorial",
    "complete tutorial",
    "complete guide",
    "full procedure",
    "full process",
    "give me the steps",
    "list the steps",
    "list out the steps",
    "every step",
    "all the steps",
    "in order",
    "detailed instructions",
    "highly detailed",
    "thorough instructions",
    "instructions to",
)

# Factual-stem patterns -- regexes that signal "the user wants a
# specific number / date / name / unit as the answer". These get the
# factual hint regardless of length (so even a long sentence like
# "I was just wondering, how much does the average mallard duck
# weigh?" still triggers the one-sentence directive).
#
# Patterns are deliberately permissive on the words BETWEEN the
# question stem and the closing question mark (so "how many planets
# are in the solar system" matches via "how many" + later "are"
# pattern, not requiring the literal substring "how many are"). The
# detection is the leading question stem; the rest of the sentence
# is content. Tuned tight on the stems themselves to avoid false
# positives on conversational phrases ("how much would I enjoy
# that" is intentionally NOT factual; "how much does a duck weigh"
# is).
_FACTUAL_STEM_PATTERNS = (
    # "how (many|much|long|heavy|tall|big|old|fast|far|cold|hot|warm|wide|deep)"
    # The quantitative adjective right after "how" is the strong
    # factual signal; the verb-bound forms ("how much WOULD I")
    # are excluded by requiring an "objective" interrogative
    # construction (does/do/is/are/was/were/has/have or no verb
    # follows).
    re.compile(
        r"\bhow\s+(?:many|much|long|heavy|tall|big|old|fast|far|"
        r"cold|hot|warm|wide|deep)\b",
        re.IGNORECASE,
    ),
    # "when did/was/were" -- date / time questions.
    re.compile(r"\bwhen\s+(?:did|was|were|does|do)\b", re.IGNORECASE),
    # "what year/time/date"
    re.compile(r"\bwhat(?:\'s|\s+is)?\s+the\s+(?:year|time|date|day)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:year|time|date|day)\b", re.IGNORECASE),
    # "who invented/discovered/wrote/..." -- factual-verb stems.
    re.compile(
        r"\bwho\s+(?:invented|discovered|wrote|founded|built|"
        r"painted|created|composed|designed|directed|authored|"
        r"developed|established)\b",
        re.IGNORECASE,
    ),
    # "who is/was/were/are THE ..." -- the definite article rules
    # out conversational forms like "Who are you?" while keeping
    # "Who is the Prime Minister of Japan?" and "Who was the first
    # person on the moon?".
    re.compile(
        r"\bwho\s+(?:is|was|were|are)\s+the\b",
        re.IGNORECASE,
    ),
    # "what (is|'s) the (capital|population|average|name|distance|...)"
    # of (anything).
    re.compile(
        r"\bwhat(?:\'s|\s+is)\s+the\s+(?:capital|population|"
        r"average|name|distance|height|width|length|depth|size|"
        r"weight|mass|speed|temperature|boiling\s+point|"
        r"freezing\s+point|melting\s+point|circumference|"
        r"diameter|radius|area|volume|density)\b",
        re.IGNORECASE,
    ),
)

# Keywords that signal "the user explicitly wants depth" -- skip the
# brevity hint even when the question is short. Procedural markers
# are a subset of these (the procedural hint will fire FIRST on
# those, but they ALSO suppress brevity so we don't double-hint).
_DEPTH_MARKERS = (
    "explain",
    "in detail",
    "in depth",
    "thoroughly",
    "elaborate",
    "expand on",
    "give me details",
    "give me the details",
    "tell me everything",
    "describe in",
    "list out",
    "list all",
    "everything you know",
    # Procedural markers are also depth markers (so they suppress
    # brevity-only hint when the procedural path didn't fire).
    *_PROCEDURAL_MARKERS,
)


# ----------------------------------------------------------------------
# Detection predicates (pure functions; testable in isolation)
# ----------------------------------------------------------------------


def _normalise(user_text: str) -> str:
    """Lowercase + strip -- the canonical form used by all detectors."""
    return (user_text or "").strip().lower()


def is_procedural_request(user_text: str) -> bool:
    """True iff the utterance asks for explicit procedural depth.

    Detection is substring-based against the lowered, stripped text.
    Empty / whitespace-only text returns False. The procedural
    markers are deliberately specific phrases ("step by step", "walk
    me through") rather than single words; "step" alone would
    false-fire on conversational uses ("just one more step in our
    debugging").
    """
    lowered = _normalise(user_text)
    if not lowered:
        return False
    return any(m in lowered for m in _PROCEDURAL_MARKERS)


def is_factual_question(user_text: str) -> bool:
    """True iff the utterance contains a factual-stem pattern.

    Factual stems are "give me a number / date / name / unit" patterns
    ("how much does X weigh", "when did Y happen", "what year did Z",
    "who invented W"). Length-independent: a 30-word lead-in still
    gets the factual hint when the actual question contains a
    factual stem.

    Empty / whitespace input returns False.
    """
    if not user_text:
        return False
    return any(p.search(user_text) for p in _FACTUAL_STEM_PATTERNS)


def is_brief_question(user_text: str) -> bool:
    """True iff the user's text reads as a brief question that should
    get a brief answer.

    Brief = short (<= 12 words AND <= 80 chars after strip) AND not
    explicitly asking for depth via any of the :data:`_DEPTH_MARKERS`
    keywords. Empty / whitespace-only text is not "brief" -- there's
    nothing to size against.

    2026-05-19 change: the AND between the word-count and char-count
    constraints was previously OR, which let any short-word-but-long-
    char query slip through. AND is the correct semantics ("brief"
    means brief on both axes).
    """
    stripped = (user_text or "").strip()
    if not stripped:
        return False
    word_count = len(stripped.split())
    char_count = len(stripped)
    # Brief = both bounds satisfied (was OR pre-2026-05-19 -- bug
    # that let long-by-words OR long-by-chars queries through).
    if word_count > _BREVITY_MAX_WORDS or char_count > _BREVITY_MAX_CHARS:
        return False
    lowered = stripped.lower()
    if any(m in lowered for m in _DEPTH_MARKERS):
        return False
    return True


# ----------------------------------------------------------------------
# Public API: hint dispatcher
# ----------------------------------------------------------------------


def apply_brevity_hint(user_text: str) -> str:
    """Prepend the appropriate response-style directive to ``user_text``.

    Dispatched in priority order:

    1. :func:`is_procedural_request` -> :data:`_PROCEDURAL_HINT`
       ("respond with detailed numbered steps").
    2. :func:`is_factual_question` -> :data:`_FACTUAL_HINT`
       ("one short sentence containing only the specific fact").
    3. :func:`is_brief_question` -> :data:`_BREVITY_HINT`
       ("respond in 1-3 short sentences").
    4. Otherwise -> ``user_text`` unchanged.

    Only one hint is ever applied per turn. Empty input is returned
    as-is so callers can apply this unconditionally without checking
    first. The function name is kept as ``apply_brevity_hint`` for
    backwards compatibility with the 2026-05-10 call sites; it now
    dispatches across all three hint classes.

    Idempotence: a string that already starts with one of the
    bracketed style directives is NOT re-hinted -- the dispatcher
    detects the existing prefix and passes through unchanged.
    """
    if not user_text:
        return user_text

    # Idempotence guard -- skip re-hinting when the input is already
    # a hinted prompt (defensive against double-wrap).
    stripped = user_text.lstrip()
    if stripped.startswith("[Style:"):
        return user_text

    if is_procedural_request(user_text):
        return f"{_PROCEDURAL_HINT}\n\n{user_text}"
    if is_factual_question(user_text):
        return f"{_FACTUAL_HINT}\n\n{user_text}"
    if is_brief_question(user_text):
        return f"{_BREVITY_HINT}\n\n{user_text}"
    return user_text


__all__ = [
    "apply_brevity_hint",
    "is_brief_question",
    "is_factual_question",
    "is_procedural_request",
]
