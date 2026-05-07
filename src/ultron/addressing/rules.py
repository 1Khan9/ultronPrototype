"""Rule-based addressing classifier.

A small set of regex / keyword rules that fire when the signal is strong
enough to short-circuit the zero-shot fallback. Goal: handle 70-90 % of
WARM-mode utterances at near-zero latency, so the slower zero-shot model
only touches genuinely ambiguous speech.

Each rule returns a (decision, confidence, reason) triple. The dispatcher
takes the highest-confidence rule per utterance. If no rule clears the
0.8 confidence bar the dispatcher falls through to zero-shot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class AddressingDecision(str, Enum):
    ADDRESSED = "ADDRESSED"
    NOT_ADDRESSED = "NOT_ADDRESSED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class RuleHit:
    decision: AddressingDecision
    confidence: float
    reason: str


# ---------------------------------------------------------------------------
# Strong YES signals: utterances that look like direct address to Ultron.
# Word boundaries (\b) keep "what" from matching "somewhat".
# ---------------------------------------------------------------------------

# Factual / informational question stems -- almost always a query the
# assistant should handle. We bias these high because mistakenly routing a
# "what time is it?" through the zero-shot fallback adds ~90 ms for no gain.
_FACTUAL_QUESTION_STEMS = re.compile(
    r"^\s*(?:"
    r"what(?:'s|s|\s+is|\s+are|\s+was|\s+were)?"
    r"|who(?:'s|s|\s+is|\s+are|\s+was)?"
    r"|when(?:'s|s|\s+is|\s+was)?"
    r"|where(?:'s|s|\s+is|\s+are)?"
    r"|why(?:'s|s|\s+is)?"
    r"|how(?:'s|s|\s+is|\s+do(?:es)?|\s+did|\s+much|\s+many|\s+long|\s+far|\s+old)?"
    r"|which"
    r"|is\s+(?:there|that|this)"
    r")\b",
    re.IGNORECASE,
)

# Second-person-target questions ("did you...", "are you..."). These are
# genuinely ambiguous between "directed at Ultron" and "directed at a human"
# (roommate, partner, child). We deliberately keep them below the 0.8
# threshold so the zero-shot model gets the final call using context.
_SECOND_PERSON_QUESTIONS = re.compile(
    r"^\s*(?:"
    r"do\s+you|did\s+you|don't\s+you|didn't\s+you"
    r"|are\s+you|aren't\s+you"
    r"|have\s+you|haven't\s+you"
    r"|were\s+you|weren't\s+you"
    r"|will\s+you|won't\s+you"
    r"|can\s+you|can't\s+you"
    r"|could\s+you"
    r"|would\s+you"
    r"|should\s+you"
    r"|how\s+(?:can|could|would|should)\s+you"
    r")\b",
    re.IGNORECASE,
)

# Imperative second-person commands. Conservative list -- we match the verb at
# the START of the utterance to avoid catching things like "I'll play later".
_IMPERATIVE_VERBS = re.compile(
    r"^\s*(?:"
    r"tell\s+me|show\s+me|find|search|look\s+up|look\s+for|google|"
    r"play|pause|stop|skip|resume|"
    r"turn\s+(?:on|off|up|down)|set|"
    r"open|close|launch|run|start|kill|"
    r"call|text|message|send|"
    r"remind\s+me|set\s+a\s+(?:reminder|timer|alarm)|"
    r"add\s+to|put\s+on|"
    r"explain|describe|summarize|translate|"
    r"draft|write|compose|"
    r"give\s+me"
    r")\b",
    re.IGNORECASE,
)

# Direct address by name. "Ultron, ..." in the second-person sense.
# We detect "ultron" at the START followed by a comma / vocative pause.
# Mid-sentence "ultron" (third-person mention) is handled by NO rules below.
_DIRECT_ADDRESS = re.compile(
    r"^\s*(?:hey\s+|okay\s+|alright\s+)?ultron\b[\s,.\-:]+",
    re.IGNORECASE,
)

# Short continuation answers most likely directed at us when said in a
# follow-up window after Ultron asked / proposed something. Standalone
# YES/NO are easy to misclassify so we keep this pool tight.
_CONTINUATION_TOKENS = {
    "yes", "yeah", "yep", "yup", "sure", "correct", "right",
    "no", "nope", "nah",
    "okay", "ok",
    "go", "go ahead", "do it", "do that", "proceed",
    "stop", "cancel",
    "more", "continue", "keep going",
    "next", "the next one", "the first one", "the second one", "the third one",
    "thanks", "thank you",
}


# ---------------------------------------------------------------------------
# Strong NO signals: utterances that clearly aren't directed at Ultron.
# ---------------------------------------------------------------------------

# Third-person mention of Ultron ("Ultron said X", "ultron's response was..."),
# i.e. the speaker is talking ABOUT Ultron, not TO Ultron. Anchored
# mid-sentence to avoid catching the YES "ultron, what's..." case which is
# matched by _DIRECT_ADDRESS first.
_THIRD_PERSON_MENTION = re.compile(
    r"\bultron\s+(?:just|already|previously|earlier|said|thinks|told|wrote|claimed|reported|mentioned)\b",
    re.IGNORECASE,
)

# Phone-call / interpersonal openers. If we hear these in WARM mode the user
# is almost certainly addressing another human.
_PHONE_OPENERS = re.compile(
    r"^\s*(?:"
    r"hello\?+|hey\s+(?:dude|man|bro|babe|honey|mom|dad|sis|guys)|"
    r"hi\s+(?:there\s+)?(?:dude|man|bro|babe|honey|mom|dad|sis|guys)|"
    r"yo\b|"
    r"what\s+up\s+(?:dude|man|bro|guys)|"
    r"it'?s\s+me\b"
    r")",
    re.IGNORECASE,
)

# Self-talk / exclamations. Short interjections almost never directed at us.
_INTERJECTIONS = {
    "oh god", "oh no", "oh shit", "oh fuck", "oh damn", "oh boy",
    "jesus", "jesus christ", "christ",
    "fuck", "shit", "damn", "crap",
    "lol", "haha", "lmao",
    "huh", "wat", "what the", "what the hell", "what the fuck",
    "wow", "whoa", "oof", "yikes",
    "ow", "ouch",
    "ugh", "argh", "hmm", "uhh", "umm", "uhhh", "err",
}


def classify(
    utterance: str,
    seconds_since_response: float = 0.0,
) -> Optional[RuleHit]:
    """Run rule-based classification on ``utterance``.

    Returns the best matching :class:`RuleHit`, or ``None`` if no rule fired
    with confidence >= 0.5 (caller should fall through to zero-shot).

    ``seconds_since_response`` slightly biases the continuation pool: short
    answers are more likely to be a real continuation if the user spoke
    within ~5 s of Ultron's last response.
    """
    text = utterance.strip()
    if not text:
        return RuleHit(AddressingDecision.NOT_ADDRESSED, 0.95, "empty utterance")

    lowered = text.lower().rstrip(".!?,")

    # NO rules fire first: a direct phone opener wins over a question stem
    # ("hey mom, what time is it?" is not for Ultron).
    if _PHONE_OPENERS.search(text):
        return RuleHit(
            AddressingDecision.NOT_ADDRESSED, 0.92, "phone-call / interpersonal opener"
        )
    if _THIRD_PERSON_MENTION.search(text):
        return RuleHit(
            AddressingDecision.NOT_ADDRESSED, 0.85, "third-person mention of Ultron"
        )
    if lowered in _INTERJECTIONS:
        return RuleHit(
            AddressingDecision.NOT_ADDRESSED, 0.85, "standalone interjection / self-talk"
        )

    # YES rules.
    if _DIRECT_ADDRESS.match(text):
        return RuleHit(
            AddressingDecision.ADDRESSED, 0.95, "direct address by name"
        )
    if _IMPERATIVE_VERBS.match(text):
        return RuleHit(
            AddressingDecision.ADDRESSED, 0.88, "imperative command stem"
        )
    if _FACTUAL_QUESTION_STEMS.match(text):
        # Factual question stems are a strong YES signal: "what time is it",
        # "who wrote X", "how does Y work" -- almost always directed at us.
        return RuleHit(
            AddressingDecision.ADDRESSED, 0.85, "factual question stem"
        )
    if _SECOND_PERSON_QUESTIONS.match(text):
        # Second-person-target questions are ambiguous between addressing
        # Ultron and addressing a human in the room. Stay below the 0.8
        # short-circuit threshold so the zero-shot fallback can decide.
        return RuleHit(
            AddressingDecision.UNCERTAIN, 0.55, "second-person question (ambiguous)"
        )

    # Continuation tokens are bumped slightly higher when we just spoke.
    if lowered in _CONTINUATION_TOKENS:
        bias = 0.05 if seconds_since_response < 5.0 else 0.0
        return RuleHit(
            AddressingDecision.ADDRESSED, 0.78 + bias, "continuation token"
        )

    return None  # No confident rule -- caller should escalate to zero-shot.


def explain_rules() -> List[Tuple[str, str]]:
    """Lightweight introspection for the review tool. Returns a list of
    ``(rule_name, summary)`` for documentation."""
    return [
        ("phone_openers", "interpersonal openers like 'hey mom', 'yo', \"it's me\""),
        ("third_person_mention", "'Ultron said ...', talking about Ultron not to him"),
        ("interjections", "'oh god', 'lol', 'shit' -- self-talk"),
        ("direct_address", "starts with 'Ultron, ...' (vocative)"),
        ("imperative_verbs", "starts with command verb: play, find, turn on, ..."),
        ("question_stems", "starts with what/who/how/why/can you/..."),
        ("continuation_tokens", "single-word answers: yes, no, ok, do that, ..."),
    ]
