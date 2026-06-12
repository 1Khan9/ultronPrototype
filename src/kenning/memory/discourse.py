"""Discourse-type tagging for conversation memory (2026-05-19, Track 1b).

Conversations have structure that's not captured by treating each
turn as independent. There are turn types -- questions, statements,
decisions, clarification requests, acknowledgments, topic shifts --
and retrieval can be smarter when each Qdrant payload carries that
tag. "What did we decide about the LLM swap?" can specifically
retrieve DECISION-tagged turns instead of relying purely on
embedding similarity to surface the right ones.

The classifier has two layers:

1. **Rule layer** -- regex / pattern-based dispatch that resolves
   60-70% of turns at high accuracy. Question marks, acknowledgment
   words, decision verbs, etc. Pure CPU, ~5 ms per turn.
2. **Embedding-centroid fallback** -- for the residual 30-40% the
   rule layer punts on, the classifier embeds the turn via the
   existing bge-small encoder + compares against precomputed
   centroids for each class. Nearest centroid wins. ~5-20 ms CPU.
   No new model load -- reuses the HybridEmbedder the memory layer
   already maintains.

Default-OFF via ``memory.discourse_tagging.enabled``. With the flag
off, the rule layer doesn't run and no discourse_type metadata is
attached to turns -- legacy retrieval is byte-for-byte unchanged.

Pure helpers (``classify_by_rules``, ``DiscourseType`` enum) are
exposed so tests + future consumers (ranking layer, observation
audit) can import them without instantiating the full classifier.
"""

from __future__ import annotations

import enum
import re
import threading
from typing import Callable, Dict, List, Optional, Sequence


# ----------------------------------------------------------------------
# Public taxonomy
# ----------------------------------------------------------------------


class DiscourseType(str, enum.Enum):
    """Six-way classification matching the 2026-05-19 design doc."""

    QUESTION = "question"
    """Asks for information ("What is X?", "How do I Y?")."""

    STATEMENT = "statement"
    """Provides information / opinion / observation without
    explicitly requesting an answer."""

    DECISION = "decision"
    """User commits to an action or outcome ("let's go with X",
    "I'll use Y", "we'll do Z")."""

    CLARIFICATION_REQUEST = "clarification_request"
    """User asks the assistant to disambiguate / repeat / explain
    something previously said ("wait what?", "say that again",
    "can you clarify Z?")."""

    ACKNOWLEDGMENT = "acknowledgment"
    """Short conversational glue with no information content
    ("yeah", "ok", "got it", "thanks", "sounds good")."""

    TOPIC_SHIFT = "topic_shift"
    """User explicitly changes subject ("anyway", "moving on",
    "different question", "actually let's talk about")."""


# ----------------------------------------------------------------------
# Rule patterns
# ----------------------------------------------------------------------


# Acknowledgments -- very short turns whose content is purely
# conversational glue. Tight pattern set: anything matching here is
# almost certainly an ack regardless of context.
_ACK_PATTERNS: tuple = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"^\s*(?:yeah|yep|yup|yes|ok|okay|sure|right|got it|gotcha|"
        r"thanks|thank you|cool|nice|great|perfect|awesome|sweet|"
        r"sounds good|alright|fine|noted|copy that|copy|"
        r"roger(?:\s+that)?|aye|"
        r"agreed|exactly|true)[\s.!,]*$",
        # ``mm`` / ``hm`` / ``uh-huh`` / ``mhm`` style filler-acks.
        r"^\s*(?:mm+|hm+|uh-?huh|mhm+|hmm+|ah+)[\s.!,]*$",
    )
)


# Topic shifts -- explicit "let's change subject" markers.
_TOPIC_SHIFT_PATTERNS: tuple = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"^\s*(?:anyway|anyways|moving on|new topic|different topic|"
        r"different question|changing (?:the )?subject|on (?:a |an "
        r"|another )?(?:different |unrelated )?(?:note|topic|"
        r"subject)|actually,? let's (?:talk|discuss|focus|move|"
        r"switch)|let's (?:switch|move|change)|by the way|btw,?\s)",
        r"\b(?:unrelated|separate question|different question)\b",
    )
)


# Decisions -- user committing to an action / choice. The pronoun +
# committal-verb structure is the key signal. Past-tense forms
# ("I went with X") count too because they're communicating a
# decision that's already been made.
_DECISION_PATTERNS: tuple = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"\b(?:i'?ll|i will|we'?ll|we will|let'?s)\s+(?:go|use|use|"
        r"take|pick|choose|select|run|do|try|build|implement|wire|"
        r"ship|merge|land|swap|switch|move|adopt|enable|disable|"
        r"deploy|push|cut)\b",
        r"\b(?:decided?|decision)\s+(?:to|on)\b",
        r"\b(?:going with|sticking with|gonna (?:go|use|take|do|"
        r"build|implement))\b",
        r"\b(?:final answer|final call|settled on|locked in|locked it"
        r" in)\b",
    )
)


# Clarification requests -- user wants the assistant to disambiguate
# or repeat. Tight patterns; many lookups overlap with QUESTION but
# the explicit "say again" / "what do you mean" structure is
# distinctly clarification.
_CLARIFICATION_PATTERNS: tuple = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"\b(?:what do you mean|what does that mean|"
        r"(?:can|could|would) you (?:re)?phrase|"
        r"say (?:that )?again|(?:can|could) you (?:re)?explain|"
        r"i don'?t (?:understand|follow|get it)|wait,?\s+what|"
        r"wait,?\s+can you|hold on,?\s+what|sorry,?\s+(?:what|"
        r"could you))\b",
        # Standalone "clarify" as a verb (any object follows).
        r"\bclarify\b",
        # Anything after "could/can/please/would you" + "clarify"
        r"\b(?:could|can|please|would) you clarify\b",
        # Generic "I'm not understanding/following/getting" with any
        # trailing object.
        r"\bi'?m (?:not (?:following|understanding|getting|"
        r"sure what|sure i)|lost|confused)\b",
        # ``come again?`` informal re-ask.
        r"\bcome again\b",
        # "you said X?" with an implicit re-ask
        r"^you said\b",
    )
)


# Questions -- the catch-all. Either ends with ? or starts with a
# question word. Many of these also overlap with the more-specific
# patterns above; the dispatcher runs more-specific patterns FIRST so
# CLARIFICATION_REQUEST beats QUESTION when both match.
_QUESTION_PATTERNS: tuple = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"\?\s*$",  # ends with question mark
        # WH-words at sentence start
        r"^\s*(?:what|how|why|when|where|who|whose|whom|which|"
        r"do|does|did|is|are|was|were|will|would|should|could|"
        r"can|may|might|shall|am)\b",
    )
)


# ----------------------------------------------------------------------
# Embedding-centroid examples (Track 1b: embedding fallback)
# ----------------------------------------------------------------------


# Few-shot examples per class. The classifier embeds these once,
# averages each class's vectors into a centroid, and dispatches new
# turns by nearest centroid. 6-12 examples per class is the sweet
# spot for nearest-centroid classification on a small label set --
# enough to span phrasings, not so many that one outlier example
# pulls the centroid off-target.
_CENTROID_EXAMPLES: Dict[DiscourseType, List[str]] = {
    DiscourseType.QUESTION: [
        "What is the boiling point of water?",
        "How does TLS handshake work?",
        "Why is the sky blue?",
        "When did World War 2 end?",
        "Where is the kitchen?",
        "Who invented the telephone?",
        "Which model should I use for this?",
        "Can you tell me what time it is?",
        "What's the difference between TCP and UDP?",
    ],
    DiscourseType.STATEMENT: [
        "The kitchen is on the second floor.",
        "I think the new design is better than the old one.",
        "Pandas are native to China.",
        "Most software bugs are caused by null references.",
        "It's raining outside today.",
        "The build passed all tests on the first try.",
        "I just got back from the store.",
        "The car needs an oil change.",
        "That documentary was really well made.",
    ],
    DiscourseType.DECISION: [
        "Let's go with the Llama 3.2 preset for gaming.",
        "I'll use Postgres for this project.",
        "We'll ship the feature on Friday.",
        "I'm gonna take the Llama option.",
        "Going with React on the frontend.",
        "Decision: we're moving to the new build system.",
        "Locked in. Wire up the Gemma swap.",
        "Final answer: skip the Kokoro fine-tune for now.",
        "I'll implement the brevity hint first, model swap second.",
    ],
    DiscourseType.CLARIFICATION_REQUEST: [
        "Wait what?",
        "What do you mean by that?",
        "Can you say that again?",
        "I don't follow.",
        "Could you rephrase that?",
        "I'm not understanding the second part.",
        "Could you clarify what you meant by 'invalidated'?",
        "Sorry, I lost you at the part about Kokoro.",
        "Hold on, what was that about the embedder?",
    ],
    DiscourseType.ACKNOWLEDGMENT: [
        "Got it.",
        "Sounds good.",
        "Thanks.",
        "Yeah.",
        "Cool, that works.",
        "Right.",
        "Mhm.",
        "Perfect.",
        "Roger that.",
    ],
    DiscourseType.TOPIC_SHIFT: [
        "Anyway, on to something else.",
        "Moving on.",
        "Different question entirely.",
        "Unrelated, but how does the Kokoro corpus look?",
        "Actually let's talk about gaming mode instead.",
        "Changing the subject -- what's the VRAM situation?",
        "By the way, did you see the new benchmark?",
        "On a different note, how is the build going?",
    ],
}


# ----------------------------------------------------------------------
# Rule layer (pure function)
# ----------------------------------------------------------------------


def classify_by_rules(text: str) -> Optional[DiscourseType]:
    """Rule-based classification. Returns None when no rule applies.

    Dispatch order (most-specific first):

    1. Acknowledgments (tight; short fillers)
    2. Topic shifts (explicit pivot markers)
    3. Decisions (committal verbs + pronouns)
    4. Clarification requests (explicit disambiguation asks)
    5. Questions (ends with ? or starts with WH-word)

    A turn that doesn't match any pattern returns None -- the caller
    falls back to the embedding-centroid layer.

    Empty / whitespace input returns None (no class to assign).
    """
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None

    # Specific patterns first; QUESTION is the catch-all and would
    # otherwise eat clarifications + decisions phrased as questions.
    if any(p.search(stripped) for p in _ACK_PATTERNS):
        return DiscourseType.ACKNOWLEDGMENT
    if any(p.search(stripped) for p in _TOPIC_SHIFT_PATTERNS):
        return DiscourseType.TOPIC_SHIFT
    if any(p.search(stripped) for p in _CLARIFICATION_PATTERNS):
        return DiscourseType.CLARIFICATION_REQUEST
    if any(p.search(stripped) for p in _DECISION_PATTERNS):
        return DiscourseType.DECISION
    if any(p.search(stripped) for p in _QUESTION_PATTERNS):
        return DiscourseType.QUESTION
    return None


# ----------------------------------------------------------------------
# Embedding-centroid fallback
# ----------------------------------------------------------------------


def _cosine_similarity_seq(
    a: Sequence[float], b: Sequence[float],
) -> float:
    """Local cosine helper -- avoids cross-module import."""
    if a is None or b is None:
        return 0.0
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na == 0 or nb == 0:
        return 0.0
    import math as _math
    return dot / (_math.sqrt(na) * _math.sqrt(nb))


def _mean_vector(vectors: Sequence[Sequence[float]]) -> List[float]:
    """Element-wise mean of a non-empty list of equal-length vectors."""
    if not vectors:
        return []
    n = len(vectors[0])
    acc = [0.0] * n
    for v in vectors:
        for i, x in enumerate(v):
            acc[i] += float(x)
    cnt = float(len(vectors))
    return [a / cnt for a in acc]


class DiscourseClassifier:
    """Rule + embedding-centroid classifier.

    Args:
        embedder_fn: callable that encodes a single string to a dense
            vector (typically ``HybridEmbedder.encode_query_dense``).
            Required for the embedding fallback to fire.
        confidence_floor: minimum cosine similarity between the query
            embedding and the winning centroid for the embedding
            result to be trusted. Below this floor, the classifier
            returns None (indicating "no reliable classification").
        centroid_examples: optional override for the per-class
            example set. Useful for tests + custom domains.
    """

    def __init__(
        self,
        *,
        embedder_fn: Optional[Callable[[str], Sequence[float]]] = None,
        confidence_floor: float = 0.25,
        centroid_examples: Optional[Dict[DiscourseType, List[str]]] = None,
    ) -> None:
        self._embedder_fn = embedder_fn
        self._confidence_floor = float(confidence_floor)
        self._examples = centroid_examples or _CENTROID_EXAMPLES
        self._centroids: Dict[DiscourseType, List[float]] = {}
        self._centroids_lock = threading.Lock()
        self._centroids_built = False

    # ------------------------------------------------------------------

    def _ensure_centroids(self) -> bool:
        """Lazy-build the per-class centroid embeddings.

        Returns True iff the centroids are populated (i.e. the embedder
        is available and at least one example per class produced a
        valid embedding). False means the fallback isn't usable on
        this call.
        """
        if self._centroids_built:
            return True
        if self._embedder_fn is None:
            return False
        with self._centroids_lock:
            if self._centroids_built:
                return True
            try:
                for cls, examples in self._examples.items():
                    vecs: List[Sequence[float]] = []
                    for ex in examples:
                        v = self._embedder_fn(ex)
                        if v is None or len(v) == 0:
                            continue
                        vecs.append(list(v))
                    if vecs:
                        self._centroids[cls] = _mean_vector(vecs)
                self._centroids_built = True
                return bool(self._centroids)
            except Exception:
                # Defensive: any failure in the embedder pipeline
                # leaves the classifier in fallback-disabled state.
                # We don't raise -- the rule layer alone is enough
                # for the high-confidence cases.
                self._centroids_built = True  # don't retry on every call
                return False

    def _classify_by_centroid(
        self, text: str,
    ) -> Optional[DiscourseType]:
        """Embedding-centroid classification.

        Returns None if the embedder isn't wired, centroids aren't
        built, or the best match's similarity is below
        ``confidence_floor``. Otherwise returns the nearest-centroid
        class.
        """
        if not self._ensure_centroids():
            return None
        if not text or not text.strip():
            return None
        try:
            assert self._embedder_fn is not None
            qvec = list(self._embedder_fn(text))
        except Exception:
            return None
        if not qvec:
            return None
        best_cls: Optional[DiscourseType] = None
        best_sim = -1.0
        for cls, centroid in self._centroids.items():
            sim = _cosine_similarity_seq(qvec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_cls = cls
        if best_cls is None or best_sim < self._confidence_floor:
            return None
        return best_cls

    # ------------------------------------------------------------------

    def classify(self, text: str) -> Optional[DiscourseType]:
        """Classify ``text`` into a :class:`DiscourseType`.

        Dispatch order:

        1. Rule layer (:func:`classify_by_rules`). Resolves the
           majority of turns; returns the class on hit.
        2. Embedding-centroid fallback. Runs only when the rule layer
           returns None AND the embedder is wired.

        Returns None when neither layer can confidently classify
        (empty input, embedder unavailable, low-confidence match).
        Callers should treat None as "leave the discourse_type
        metadata empty" rather than fabricating a class.
        """
        rule_verdict = classify_by_rules(text)
        if rule_verdict is not None:
            return rule_verdict
        return self._classify_by_centroid(text)


__all__ = [
    "DiscourseClassifier",
    "DiscourseType",
    "classify_by_rules",
]
