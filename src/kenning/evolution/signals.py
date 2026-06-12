"""Opportunity-signal extraction for ultron's self-improvement loop.

Catalog 13 (clawhub-capability-evolver) clean-room synthesis -- the
GREEN, local-only signal layer. The upstream's three-layer detector had
a third layer that POSTed a corpus summary to a remote hub LLM
(``/a2a/signal/analyze``) every fifth cycle; that layer is **deliberately
NOT implemented** -- it is a network egress + paid-API path that violates
ultron's local-only contract. ultron keeps only the two local layers
(deterministic regex + weighted-keyword scoring) plus the genuinely
clever, fully-local **history-aware post-processing** the catalog flagged
as the real intellectual value:

* **anti-thrash dedup** -- a signal seen in 3+ of the last 8 cycles is
  suppressed so the loop stops re-acting on the same thing;
* **repair-loop break-out** -- 3+ consecutive repair cycles strip the
  error signals and force an innovation cycle instead;
* **saturation detection** -- consecutive zero-change cycles inject a
  steady-state signal that throttles the loop;
* **failure-streak escalation** -- 5+ consecutive failures ban the
  most-used failing gene so a bad strategy quarantines itself.

A "signal" is a short string. Most are bare names from
:data:`OPPORTUNITY_SIGNALS`; a few carry a ``:payload`` suffix (an error
line, a user-request snippet, a banned gene id). :func:`signal_base`
strips the suffix.

Everything here is a pure function over text + a list of prior cycle
records. No IO, no network, no model loads.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from ultron.evolution.models import (
    CommandFailureSignal,
    ComplexityHint,
    CorrectionCapsule,
    FeatureRequestCapsule,
    FeatureRequestStatus,
    KnowledgeGapCapsule,
    KnowledgeSource,
    derive_pattern_key,
    new_record_id,
)

# --- the canonical taxonomy -------------------------------------------------

#: The 18 named opportunity signals (the stable vocabulary the loop reasons
#: over). Dynamic detail signals (``errsig:``, ``user_feature_request:``,
#: ``ban_gene:`` ...) carry a ``:payload`` suffix and are not listed here.
#: ``coding_task_success`` (production-hardening #66) is emitted by the
#: orchestrator's coding-success drain, not by text extraction -- a
#: successfully-completed voice coding task is a positive pattern worth
#: distilling once it recurs.
OPPORTUNITY_SIGNALS: tuple[str, ...] = (
    "user_feature_request",
    "user_improvement_suggestion",
    "perf_bottleneck",
    "capability_gap",
    "stable_success_plateau",
    "external_opportunity",
    "recurring_error",
    "unsupported_input_type",
    "evolution_stagnation_detected",
    "repair_loop_detected",
    "force_innovation_after_repair_loop",
    "tool_bypass",
    "curriculum_target",
    "issue_already_resolved",
    "openclaw_self_healed",
    "empty_cycle_loop_detected",
    "explore_opportunity",
    "coding_task_success",
)

#: Signals that describe a missing input rather than an actionable
#: opportunity. When ANY actionable signal is present these are dropped, so
#: a missing log file never crowds out a real error.
COSMETIC_SIGNALS: frozenset[str] = frozenset(
    {
        "user_missing",
        "memory_missing",
        "session_logs_missing",
        "windows_shell_incompatible",
    }
)

# --- thresholds (ultron-calibrated; documented constants) -------------------

REPAIR_LOOP_THRESHOLD: int = 3
RECENT_WINDOW: int = 8
EMPTY_CYCLE_THRESHOLD: int = 4  # of the last RECENT_WINDOW cycles
SATURATION_THRESHOLD: int = 3  # consecutive empty cycles
STEADY_STATE_THRESHOLD: int = 5  # consecutive empty cycles
FAILURE_STREAK_THRESHOLD: int = 3
FAILURE_LOOP_THRESHOLD: int = 5
HIGH_FAILURE_RATIO: float = 0.75
SUPPRESS_OCCURRENCE_THRESHOLD: int = 3  # appears in N+ of the last window
RECURRING_ERROR_THRESHOLD: int = 3

SNIPPET_MAX_CHARS: int = 200
ERRSIG_MAX_CHARS: int = 260
RECURRING_ERRSIG_KEY_CHARS: int = 100
HIGH_TOOL_USAGE_THRESHOLD: int = 10
REPEATED_EXEC_THRESHOLD: int = 5


class SignalLayer(str, Enum):
    """Which extraction layer produced a signal (for diagnostics)."""

    REGEX = "regex"
    KEYWORD = "keyword"
    USER_REQUEST = "user_request"
    POST_PROCESSING = "post_processing"


@dataclass(frozen=True)
class SignalProfile:
    """A weighted-keyword profile for layer-2 scoring.

    A signal fires when the sum of ``count * weight`` across all matched
    keywords in the lowercased corpus reaches :attr:`threshold`. This is
    what lets several individually-weak cues accumulate into a confident
    detection (e.g. "lag" + "delay" + "sluggish" -> ``perf_bottleneck``)
    while a single weak cue does not trip it.
    """

    keywords: Mapping[str, float]
    threshold: float = 1.0


#: Layer-2 weighted-keyword profiles, calibrated for ultron's voice /
#: assistant corpus. Weights + thresholds are clean-room ultron values
#: (the upstream's lived in obfuscated data); the SHAPE -- accumulate
#: weak cues to a threshold -- is the ported pattern.
SIGNAL_PROFILES: dict[str, SignalProfile] = {
    "perf_bottleneck": SignalProfile(
        keywords={
            "slow": 0.5,
            "lag": 0.4,
            "laggy": 0.4,
            "latency": 0.5,
            "delay": 0.4,
            "sluggish": 0.4,
            "throttle": 0.4,
            "timeout": 0.6,
            "timed out": 0.6,
            "bottleneck": 0.8,
            "too slow": 0.9,
            "takes forever": 0.8,
            "freezing": 0.5,
        },
        threshold=1.0,
    ),
    "capability_gap": SignalProfile(
        keywords={
            "can't": 0.4,
            "cannot": 0.4,
            "unable to": 0.5,
            "not supported": 0.8,
            "no way to": 0.7,
            "missing feature": 0.9,
            "doesn't support": 0.8,
            "unsupported": 0.6,
            "i don't know how": 0.6,
            "not capable": 0.8,
        },
        threshold=1.0,
    ),
    "user_feature_request": SignalProfile(
        keywords={
            "please add": 0.9,
            "i want": 0.6,
            "can you add": 0.8,
            "it would be nice": 0.7,
            "feature request": 1.0,
            "add support": 0.8,
            "wish it could": 0.7,
            "i'd like": 0.6,
            "would love": 0.6,
        },
        threshold=1.0,
    ),
    "user_improvement_suggestion": SignalProfile(
        keywords={
            "could be better": 0.8,
            "improve": 0.5,
            "make it faster": 0.8,
            "would be better": 0.7,
            "suggestion": 0.6,
            "you should": 0.5,
            "should really": 0.6,
            "needs work": 0.7,
        },
        threshold=1.0,
    ),
    "recurring_error": SignalProfile(
        keywords={
            "still failing": 0.8,
            "keeps failing": 0.9,
            "every time": 0.6,
            "repeatedly": 0.7,
            "same error": 0.9,
            "again": 0.3,
            "once more": 0.4,
        },
        threshold=1.0,
    ),
    "tool_bypass": SignalProfile(
        keywords={
            "manually ran": 0.7,
            "bypass": 0.7,
            "workaround": 0.6,
            "had to use": 0.5,
            "instead of the tool": 0.9,
            "did it by hand": 0.8,
        },
        threshold=1.0,
    ),
    "evolution_stagnation_detected": SignalProfile(
        keywords={
            "no progress": 0.8,
            "stuck": 0.6,
            "stagnant": 0.9,
            "not improving": 0.8,
            "plateau": 0.7,
            "going in circles": 0.9,
            "nothing changed": 0.6,
        },
        threshold=1.0,
    ),
}


# --- multilingual user-request triggers (layer 1, local, GREEN) -------------
#
# The upstream detected feature requests / improvement suggestions in four
# languages with a verbatim snippet. ultron is an English voice assistant,
# so English coverage is primary; the documented CJK literal triggers are
# kept for fidelity (they are harmless extra matches).

_FEATURE_REQUEST_TRIGGERS: tuple[str, ...] = (
    "please add",
    "can you add",
    "could you add",
    "i want you to",
    "i wish you could",
    "it would be nice if",
    "add support for",
    "i'd like you to",
    "would love it if",
    "我想",  # ZH-CN "I want"
    "請加",  # ZH-TW "please add"
    "追加してほしい",  # JA "please add"
)

_IMPROVEMENT_TRIGGERS: tuple[str, ...] = (
    "you should",
    "it would be better",
    "could be improved",
    "make it better",
    "make it faster",
    "i suggest",
    "my suggestion is",
    "改进",  # ZH-CN "improve"
    "改善",  # ZH-TW "improve"
    "改善して",  # JA "please improve"
)


# --- compiled regexes -------------------------------------------------------

_ERROR_LINE_RE = re.compile(
    r"^.*?(?:\b\w*(?:Error|Exception)\b|Traceback|\[error\]|error:).*$",
    re.IGNORECASE | re.MULTILINE,
)
_TOOL_USE_RE = re.compile(r"\[TOOL:\s*([A-Za-z0-9_.\-]+)\s*\]")
_EXEC_BYPASS_RE = re.compile(
    r"^\s*(?:>|\$|PS>|cmd>)?\s*(node|npx|curl|wget|python|python3|bash|sh|powershell)\b",
    re.IGNORECASE | re.MULTILINE,
)
_PATH_ESCAPE_RE = re.compile(r"(?:\.\./){2,}|(?:\.\.\\){2,}")
_UNIX_ONLY_RE = re.compile(
    r"\bpgrep\b|\bps\s+aux\b|\bcat\s*>|<<\s*\w+|^\s*grep\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class RecentHistoryAnalysis:
    """Aggregated stats over the recent cycle history, driving the
    history-aware post-processing.

    Attributes:
        suppressed_signals: signals that appeared in
            :data:`SUPPRESS_OCCURRENCE_THRESHOLD`+ of the recent window.
        recent_intents: the intent of each cycle in the recent window.
        consecutive_repair_count: repair cycles at the tail (newest-first).
        empty_cycle_count: zero-change cycles in the recent window.
        consecutive_empty_cycles: zero-change cycles at the tail.
        consecutive_failure_count: failed cycles at the tail.
        recent_failure_count: failed cycles in the recent window.
        recent_failure_ratio: ``recent_failure_count / window size``.
        signal_freq: per-signal occurrence counts in the recent window.
        gene_freq: per-gene counts among recent FAILING cycles.
        top_failing_gene: the most-used gene among recent failures (or "").
    """

    suppressed_signals: frozenset[str] = frozenset()
    recent_intents: tuple[str, ...] = ()
    consecutive_repair_count: int = 0
    empty_cycle_count: int = 0
    consecutive_empty_cycles: int = 0
    consecutive_failure_count: int = 0
    recent_failure_count: int = 0
    recent_failure_ratio: float = 0.0
    signal_freq: Mapping[str, int] = field(default_factory=dict)
    gene_freq: Mapping[str, int] = field(default_factory=dict)
    top_failing_gene: str = ""


# --- small accessors over heterogeneous cycle records -----------------------


def _get(event: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a Mapping or attribute from an object."""
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def _outcome_status(event: Any) -> str:
    """Normalise a cycle's outcome to ``"success"`` / ``"failed"`` / ``""``."""
    outcome = _get(event, "outcome")
    if outcome is None:
        return ""
    if isinstance(outcome, str):
        return outcome.lower()
    status = _get(outcome, "status", "")
    status = getattr(status, "value", status)
    return str(status).lower() if status else ""


def _blast(event: Any) -> tuple[int, int]:
    """Return ``(files, lines)`` for a cycle's blast radius."""
    br = _get(event, "blast_radius")
    if br is None:
        return (0, 0)
    files = _get(br, "files", 0) or 0
    lines = _get(br, "lines", 0) or 0
    try:
        return (int(files), int(lines))
    except (TypeError, ValueError):
        return (0, 0)


def _gene(event: Any) -> str:
    """Return the gene id a cycle used (or "")."""
    gene = _get(event, "gene")
    if gene:
        return str(gene)
    used = _get(event, "genes_used") or ()
    if used:
        try:
            return str(list(used)[0])
        except (TypeError, IndexError):
            return ""
    return ""


def _signals_of(event: Any) -> tuple[str, ...]:
    """Return the signals recorded on a cycle."""
    sigs = _get(event, "signals") or ()
    if isinstance(sigs, str):
        return (sigs,)
    return tuple(str(s) for s in sigs)


def signal_base(signal: str) -> str:
    """Return a signal's base name, stripping any ``:payload`` suffix."""
    return signal.split(":", 1)[0]


# --- corpus assembly --------------------------------------------------------


def assemble_corpus(
    *,
    recent_session_transcript: str = "",
    today_log: str = "",
    memory_snippet: str = "",
    user_snippet: str = "",
) -> str:
    """Join the available text sources into one corpus for extraction."""
    parts = [recent_session_transcript, today_log, memory_snippet, user_snippet]
    return "\n".join(p for p in parts if p)


def _normalise_snippet(text: str) -> str:
    """Collapse whitespace + truncate a user snippet for a signal payload."""
    flat = " ".join(text.split())
    if len(flat) > SNIPPET_MAX_CHARS:
        return flat[:SNIPPET_MAX_CHARS]
    return flat


# --- layer 1: deterministic regex ------------------------------------------


def extract_regex_signals(
    corpus: str,
    *,
    is_windows: Optional[bool] = None,
) -> list[str]:
    """Layer 1: deterministic regex/keyword presence detection.

    Detects error lines (+ recurring-error aggregation), missing files,
    path-escape, tool-usage analytics, shell bypass, and Windows shell
    incompatibility. Returns a de-duplicated list of signals (errsig lines
    may appear multiple times, distinguished by payload).
    """
    if is_windows is None:
        is_windows = sys.platform.startswith("win")
    lower = corpus.lower()
    out: list[str] = []

    error_lines = [m.group(0).strip() for m in _ERROR_LINE_RE.finditer(corpus)]
    if error_lines:
        out.append("log_error")
        # errsig per distinct error line (cap to avoid flooding).
        seen_sig: set[str] = set()
        for line in error_lines:
            clipped = line[:ERRSIG_MAX_CHARS]
            if clipped not in seen_sig:
                seen_sig.add(clipped)
                out.append(f"errsig:{clipped}")
            if len(seen_sig) >= 10:
                break
        # recurring-error aggregation by a coarse key.
        key_counts = Counter(line[:RECURRING_ERRSIG_KEY_CHARS].lower() for line in error_lines)
        top_key, top_count = key_counts.most_common(1)[0]
        if top_count >= RECURRING_ERROR_THRESHOLD:
            out.append("recurring_error")
            out.append(f"recurring_errsig({top_count}x):{top_key}")

    if "memory.md missing" in lower or "memory.md not found" in lower:
        out.append("memory_missing")
    if "user.md missing" in lower or "user.md not found" in lower:
        out.append("user_missing")
    if "no session logs" in lower or "session logs missing" in lower:
        out.append("session_logs_missing")
    if "key missing" in lower or "integration key" in lower and "missing" in lower:
        out.append("integration_key_missing")

    if "timeout" in lower and "slow" in lower:
        out.append("perf_bottleneck")
    if "unsupported" in lower and ("type" in lower or "format" in lower or "mime" in lower):
        out.append("unsupported_input_type")

    if _PATH_ESCAPE_RE.search(corpus):
        out.append("path_outside_workspace")
    if is_windows and _UNIX_ONLY_RE.search(corpus):
        out.append("windows_shell_incompatible")

    # tool-usage analytics
    tool_counts = Counter(m.group(1).lower() for m in _TOOL_USE_RE.finditer(corpus))
    for tool, count in tool_counts.items():
        if count >= HIGH_TOOL_USAGE_THRESHOLD:
            out.append(f"high_tool_usage:{tool}")
        if tool in {"exec", "shell", "bash", "run"} and count >= REPEATED_EXEC_THRESHOLD:
            out.append("repeated_tool_usage:exec")
    if _EXEC_BYPASS_RE.search(corpus):
        out.append("tool_bypass")

    return _dedupe(out)


def extract_user_requests(corpus: str) -> list[str]:
    """Layer 1 (multilingual): detect feature requests / improvement
    suggestions and attach the triggering sentence as a snippet payload."""
    out: list[str] = []
    lower = corpus.lower()
    # Find the first triggering sentence for the snippet.
    sentences = re.split(r"(?<=[.!?\n])\s+", corpus)
    for trigger in _FEATURE_REQUEST_TRIGGERS:
        if trigger in lower or trigger in corpus:
            snippet = _first_sentence_with(sentences, trigger)
            out.append(f"user_feature_request:{_normalise_snippet(snippet)}")
            break
    for trigger in _IMPROVEMENT_TRIGGERS:
        if trigger in lower or trigger in corpus:
            snippet = _first_sentence_with(sentences, trigger)
            out.append(f"user_improvement_suggestion:{_normalise_snippet(snippet)}")
            break
    return out


def _first_sentence_with(sentences: Sequence[str], trigger: str) -> str:
    """Return the first sentence containing ``trigger`` (case-insensitive),
    falling back to the trigger itself."""
    for sent in sentences:
        if trigger in sent.lower() or trigger in sent:
            return sent.strip()
    return trigger


# --- layer 2: weighted-keyword scoring -------------------------------------


def extract_keyword_signals(corpus_lower: str) -> list[str]:
    """Layer 2: fire each signal whose accumulated keyword weight reaches
    its profile threshold."""
    out: list[str] = []
    for name, profile in SIGNAL_PROFILES.items():
        score = 0.0
        for keyword, weight in profile.keywords.items():
            count = corpus_lower.count(keyword)
            if count:
                score += count * weight
        if score >= profile.threshold:
            out.append(name)
    return out


# --- merge ------------------------------------------------------------------


def _dedupe(values: Sequence[str]) -> list[str]:
    """Order-preserving exact de-duplication."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def merge_signals(*arrays: Sequence[str]) -> list[str]:
    """Order-preserving union of several signal arrays. Distinct payload
    variants (``errsig:a`` vs ``errsig:b``) are preserved; exact repeats
    are dropped."""
    merged: list[str] = []
    for arr in arrays:
        merged.extend(arr)
    return _dedupe(merged)


# --- history analysis -------------------------------------------------------


def analyze_recent_history(recent_events: Sequence[Any]) -> RecentHistoryAnalysis:
    """Aggregate the recent cycle history into the stats the
    post-processing needs. ``recent_events`` is chronological (oldest
    first); the tail is the newest cycle. Never raises."""
    cycles = list(recent_events or ())
    window = cycles[-RECENT_WINDOW:]
    window_size = len(window)

    # tail (newest-first) consecutive counts
    consec_repair = 0
    consec_empty = 0
    consec_fail = 0
    for cyc in reversed(cycles):
        intent = str(_get(cyc, "intent", "") or "").lower()
        if intent == "repair":
            consec_repair += 1
        else:
            break
    for cyc in reversed(cycles):
        files, lines = _blast(cyc)
        if files == 0 and lines == 0:
            consec_empty += 1
        else:
            break
    for cyc in reversed(cycles):
        if _outcome_status(cyc) == "failed":
            consec_fail += 1
        else:
            break

    # window aggregates
    empty_in_window = sum(1 for c in window if _blast(c) == (0, 0))
    fail_in_window = sum(1 for c in window if _outcome_status(c) == "failed")
    intents = tuple(str(_get(c, "intent", "") or "") for c in window)

    signal_freq: Counter[str] = Counter()
    for c in window:
        for s in set(_signals_of(c)):
            signal_freq[s] += 1
    suppressed = frozenset(
        s for s, n in signal_freq.items() if n >= SUPPRESS_OCCURRENCE_THRESHOLD
    )

    gene_freq: Counter[str] = Counter()
    for c in window:
        if _outcome_status(c) == "failed":
            g = _gene(c)
            if g and g != "ad_hoc":
                gene_freq[g] += 1
    top_failing_gene = gene_freq.most_common(1)[0][0] if gene_freq else ""

    ratio = (fail_in_window / window_size) if window_size else 0.0

    return RecentHistoryAnalysis(
        suppressed_signals=suppressed,
        recent_intents=intents,
        consecutive_repair_count=consec_repair,
        empty_cycle_count=empty_in_window,
        consecutive_empty_cycles=consec_empty,
        consecutive_failure_count=consec_fail,
        recent_failure_count=fail_in_window,
        recent_failure_ratio=ratio,
        signal_freq=dict(signal_freq),
        gene_freq=dict(gene_freq),
        top_failing_gene=top_failing_gene,
    )


# --- post-processing --------------------------------------------------------

_ERROR_SIGNAL_BASES = frozenset({"log_error", "recurring_error"})


def _is_error_signal(signal: str) -> bool:
    base = signal_base(signal)
    return base in _ERROR_SIGNAL_BASES or base in ("errsig", "recurring_errsig")


def apply_post_processing(
    signals: Sequence[str],
    analysis: RecentHistoryAnalysis,
) -> list[str]:
    """Apply the history-aware post-processing rules to a merged signal set.

    Order matters; each step layers on the previous (faithful to the
    upstream's ``analyzeRecentHistory`` pipeline):

    1. drop cosmetic signals when any actionable signal is present;
    2. suppress signals seen in 3+ of the recent window (anti-thrash);
    3. on a 3+ repair streak, strip error signals + force innovation;
    4. on 4+ empty cycles in the window, flag an empty-cycle loop;
    5. on 3+/5+ consecutive empty cycles, inject saturation / steady-state;
    6. on 3+/5+ consecutive failures, escalate + ban the worst gene;
    7. on a >=75% recent failure ratio, force innovation;
    8. if nothing remains, fall back to a stable-success-plateau signal.
    """
    result = list(signals)

    # 1. prioritisation -- drop cosmetic when an actionable signal exists
    actionable = [s for s in result if signal_base(s) not in COSMETIC_SIGNALS]
    if actionable:
        result = actionable

    # 2. anti-thrash dedup against recent history
    if analysis.suppressed_signals:
        result = [s for s in result if s not in analysis.suppressed_signals]
        if not result:
            result = ["evolution_stagnation_detected", "stable_success_plateau"]

    # 3. repair-loop break-out
    if analysis.consecutive_repair_count >= REPAIR_LOOP_THRESHOLD:
        result = [s for s in result if not _is_error_signal(s)]
        result += [
            "repair_loop_detected",
            "stable_success_plateau",
            "force_innovation_after_repair_loop",
        ]

    # 4. empty-cycle loop
    if analysis.empty_cycle_count >= EMPTY_CYCLE_THRESHOLD:
        result += ["empty_cycle_loop_detected", "stable_success_plateau"]

    # 5. saturation / steady-state
    if analysis.consecutive_empty_cycles >= SATURATION_THRESHOLD:
        result += ["evolution_saturation", "explore_opportunity"]
        if analysis.consecutive_empty_cycles >= STEADY_STATE_THRESHOLD:
            result.append("force_steady_state")

    # 6. failure-streak escalation
    if analysis.consecutive_failure_count >= FAILURE_STREAK_THRESHOLD:
        result.append(f"consecutive_failure_streak_{analysis.consecutive_failure_count}")
        if analysis.consecutive_failure_count >= FAILURE_LOOP_THRESHOLD:
            result.append("failure_loop_detected")
            if analysis.top_failing_gene:
                result.append(f"ban_gene:{analysis.top_failing_gene}")

    # 7. high failure ratio
    if analysis.recent_failure_ratio >= HIGH_FAILURE_RATIO and analysis.recent_intents:
        result += ["high_failure_ratio", "force_innovation_after_repair_loop"]

    result = _dedupe(result)

    # 8. empty fallback
    if not result:
        result = ["stable_success_plateau"]
    return result


# ---------------------------------------------------------------------------
# Catalog 14 (clawhub-self-improving-agent) -- qualitative conversation-event
# detectors. Pure functions over turn text producing the structured capture
# records in :mod:`ultron.evolution.models`; never raise; zero IO / network.
# Correction detection is gated on a non-empty ``prior_response`` so a bare
# "actually..." with no preceding ultron claim is not mistaken for a
# correction. Only the detect-the-event-in-text BEHAVIOUR is ported -- the
# upstream's dangerous PostToolUse BASH-hook mechanism is excluded.
# ---------------------------------------------------------------------------

#: Named qualitative signals -- kept SEPARATE from :data:`OPPORTUNITY_SIGNALS`
#: so the documented 17-signal taxonomy count is unchanged; recognised as
#: actionable by :func:`has_opportunity_signal`.
QUALITATIVE_CAPTURE_SIGNALS: tuple[str, ...] = (
    "user_correction",
    "knowledge_gap",
    "command_failure",
)

#: Known command / tool failure tokens (clean-room list; the in-process,
#: zero-shell analogue of the upstream error detector's hardcoded set).
COMMAND_FAILURE_TOKENS: tuple[str, ...] = (
    "traceback (most recent call last)",
    "npm err!",
    "permission denied",
    "command not found",
    "no such file or directory",
    "segmentation fault",
    "fatal error",
    "fatal:",
    "error:",
    "exception:",
    "exited with code",
    "non-zero exit",
    "cannot find module",
    "modulenotfounderror",
    "syntaxerror",
    "build failed",
    "compilation failed",
    "operation not permitted",
    "access is denied",
    "connection refused",
    "killed",
)

_TOPIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "into", "your", "you",
        "are", "was", "but", "not", "what", "why", "how", "when", "its", "really",
        "just", "please", "can", "could", "would", "should", "about", "there",
        "here", "they", "them", "were", "have", "has", "had", "did", "does", "done",
        "get", "got", "use", "uses", "using", "know", "knew", "actually", "wrong",
        "incorrect", "meant", "said", "thing", "things", "want", "wanted", "fyi",
        "wish", "like", "love", "also", "ever", "able", "way",
    }
)


def derive_topic_area(text: str, *, max_words: int = 4) -> str:
    """Extract a short, human-readable subject from ``text`` (a few content
    words; stopwords + punctuation stripped). Labels a correction /
    knowledge-gap / feature-request record."""
    words: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9_+.\-]*", text.lower()):
        w = raw.strip("-._+")
        if len(w) >= 3 and w not in _TOPIC_STOPWORDS:
            words.append(w)
        if len(words) >= max_words:
            break
    return " ".join(words)


#: Strong correction phrases -- an explicit "you were wrong" that always
#: counts as a correction.
_CORRECTION_STRONG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:that'?s|that\s+is|you'?re|you\s+are|it'?s|it\s+is)\s+"
        r"(?:wrong|incorrect|not\s+right|mistaken|inaccurate|outdated)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnot\s+what\s+i\s+(?:asked|meant|said|wanted)\b", re.IGNORECASE),
    re.compile(r"\bthat'?s\s+not\s+(?:what\s+i|right|correct)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:got|have)\s+(?:it|that|this)\s+wrong\b", re.IGNORECASE),
    re.compile(r"\b(?:correction|i\s+stand\s+corrected)\b", re.IGNORECASE),
)

#: Weak openers -- only count as a correction when the utterance does NOT
#: also read as a positive acknowledgement (see :data:`_POSITIVE_ACK_RE`).
_CORRECTION_WEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:no|nope)[,.\s]+(?:actually|that|you|it|i)\b", re.IGNORECASE),
    re.compile(r"^\s*actually[,\s]", re.IGNORECASE),
    re.compile(r"\bi\s+meant\b", re.IGNORECASE),
)

#: Positive-acknowledgement cues. When ONLY a weak opener matched and one of
#: these is present, the turn is praise/agreement, not a correction.
_POSITIVE_ACK_RE = re.compile(
    r"\b(?:thanks|thank\s+you|great|perfect|awesome|excellent|brilliant|"
    r"nice(?:\s+one)?|love\s+it|loved\s+it|agree|agreed|exactly|makes\s+sense|"
    r"sounds\s+good|that'?s\s+right|you'?re\s+right|appreciate|"
    r"good\s+(?:job|idea|call|work|one))\b",
    re.IGNORECASE,
)

_KNOWLEDGE_GAP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfor\s+(?:future\s+reference|the\s+record)\b", re.IGNORECASE),
    re.compile(r"\bjust\s+so\s+you\s+know\b", re.IGNORECASE),
    re.compile(r"\bf\.?y\.?i\.?\b", re.IGNORECASE),
    re.compile(r"\bfor\s+your\s+information\b", re.IGNORECASE),
    re.compile(r"\bthe\s+correct\s+\w+\s+(?:is|are|was|were)\b", re.IGNORECASE),
    re.compile(r"\bactually\s+it'?s\b", re.IGNORECASE),
    re.compile(
        r"\bthis\s+(?:project|repo|repository|codebase|machine|system|app)\s+uses\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:keep\s+in\s+mind|note\s+that|remember\s+that|bear\s+in\s+mind)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:didn'?t|did\s+not|don'?t|do\s+not)\s+know\b", re.IGNORECASE),
)

_FEATURE_REQUEST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bi\s+wish\s+you\s+could\b", re.IGNORECASE),
    re.compile(r"\bit\s+would\s+be\s+(?:nice|great|cool|helpful)\s+if\b", re.IGNORECASE),
    re.compile(
        r"\bcan\s+you\s+(?:also\s+|ever\s+|please\s+)?(?:add|support|build|make|create|integrate)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bcould\s+you\s+(?:add|support|build|make|create|integrate)\b", re.IGNORECASE),
    re.compile(r"\bis\s+there\s+a\s+way\s+(?:to|for\s+you\s+to)\b", re.IGNORECASE),
    re.compile(r"\bwhy\s+can'?t\s+you\b", re.IGNORECASE),
    re.compile(r"\b(?:please\s+)?add\s+support\s+for\b", re.IGNORECASE),
    re.compile(r"\bi'?d\s+(?:like|love)\s+(?:it\s+)?(?:if\s+)?you\s+(?:to|could|would)\b", re.IGNORECASE),
    re.compile(r"\bwould\s+love\s+(?:it\s+)?if\b", re.IGNORECASE),
)

_COMPLEXITY_COMPLEX_HINTS: tuple[str, ...] = (
    "integrate", "pipeline", "system", "framework", "architecture", "database",
    "real-time", "realtime", "train", "fine-tune", "distributed", "multi-step",
)
_COMPLEXITY_SIMPLE_HINTS: tuple[str, ...] = (
    "just", "simply", "quick", "toggle", "rename", "small", "minor", "button", "flag",
)


def _estimate_complexity(text: str) -> ComplexityHint:
    """Rough effort estimate for a feature request from keyword cues."""
    low = text.lower()
    if any(h in low for h in _COMPLEXITY_COMPLEX_HINTS):
        return ComplexityHint.COMPLEX
    if any(h in low for h in _COMPLEXITY_SIMPLE_HINTS):
        return ComplexityHint.SIMPLE
    return ComplexityHint.MEDIUM


def extract_correction(
    user_text: str, *, prior_response: str = ""
) -> Optional[CorrectionCapsule]:
    """Detect that the user corrected ultron on the turn FOLLOWING a
    response. Fires only when a correction phrase matches AND
    ``prior_response`` is non-empty (there was an agent claim to correct).
    Returns a :class:`CorrectionCapsule`, else ``None``. Never raises."""
    try:
        if not user_text or not user_text.strip() or not (prior_response or "").strip():
            return None
        strong = any(p.search(user_text) for p in _CORRECTION_STRONG_PATTERNS)
        weak = any(p.search(user_text) for p in _CORRECTION_WEAK_PATTERNS)
        if not (strong or weak):
            return None
        # A weak opener ("actually..." / "no, ...") that also reads as a
        # positive acknowledgement is praise, not a correction. A strong
        # phrase ("that's wrong") always counts even if praise is present.
        if not strong and _POSITIVE_ACK_RE.search(user_text):
            return None
        topic = derive_topic_area(user_text) or derive_topic_area(prior_response)
        return CorrectionCapsule(
            id=new_record_id("correction_"),
            user_utterance_fragment=user_text,
            topic_area=topic,
            prior_agent_claim_summary=prior_response,
            confidence=0.85,
        )
    except Exception:  # noqa: BLE001 -- detection never breaks a turn
        return None


def extract_knowledge_gap(
    user_text: str,
    *,
    prior_response: str = "",
    source: KnowledgeSource = KnowledgeSource.USER,
) -> Optional[KnowledgeGapCapsule]:
    """Detect the user supplying a fact ultron lacked / had wrong. Returns
    a :class:`KnowledgeGapCapsule`, else ``None``. Never raises."""
    try:
        if not user_text or not user_text.strip():
            return None
        if not any(p.search(user_text) for p in _KNOWLEDGE_GAP_PATTERNS):
            return None
        return KnowledgeGapCapsule(
            id=new_record_id("knowledge_gap_"),
            topic_area=derive_topic_area(user_text),
            gap_description=user_text,
            source=source,
            confidence=0.8,
        )
    except Exception:  # noqa: BLE001
        return None


def extract_feature_request(user_text: str) -> Optional[FeatureRequestCapsule]:
    """Detect a user-expressed wish for a capability that does not exist.
    Returns a :class:`FeatureRequestCapsule` (status PENDING), else
    ``None``. Reuses the existing multilingual feature-request triggers as a
    fallback. Never raises."""
    try:
        if not user_text or not user_text.strip():
            return None
        lower = user_text.lower()
        matched = any(p.search(user_text) for p in _FEATURE_REQUEST_PATTERNS) or any(
            t in lower for t in _FEATURE_REQUEST_TRIGGERS
        )
        if not matched:
            return None
        capability = user_text.strip()
        for sent in re.split(r"(?<=[.!?\n])\s+", user_text):
            sl = sent.lower()
            if any(p.search(sent) for p in _FEATURE_REQUEST_PATTERNS) or any(
                t in sl for t in _FEATURE_REQUEST_TRIGGERS
            ):
                capability = sent.strip()
                break
        context = user_text.strip()
        if context == capability:
            context = ""
        return FeatureRequestCapsule(
            id=new_record_id("feature_request_"),
            requested_capability=capability,
            user_context=context,
            complexity_hint=_estimate_complexity(capability),
            status=FeatureRequestStatus.PENDING,
            user_utterance_fragment=user_text,
            # Key on the stopword-stripped capability (not lead filler like
            # "i wish you") so distinct phrasings of the same wish can align.
            pattern_key=derive_pattern_key(
                kind="feature_request", topic=derive_topic_area(capability)
            ),
        )
    except Exception:  # noqa: BLE001
        return None


def extract_command_failure(
    output: str, *, command: str = "", exit_code: Optional[int] = None
) -> Optional[CommandFailureSignal]:
    """Detect a command / tool failure in ``output`` (or via a non-zero
    ``exit_code``). In-process, zero-shell analogue of the upstream's
    PostToolUse error detector. Returns a :class:`CommandFailureSignal`,
    else ``None``. Never raises."""
    try:
        has_nonzero = exit_code is not None and int(exit_code) != 0
        low = (output or "").lower()
        matched_token = next((t for t in COMMAND_FAILURE_TOKENS if t in low), "")
        if not has_nonzero and not matched_token:
            return None
        summary = ""
        for line in (output or "").splitlines():
            ls = line.strip()
            if not ls:
                continue
            ll = ls.lower()
            if matched_token and matched_token in ll:
                summary = ls
                break
            if _ERROR_LINE_RE.search(ls):
                summary = ls
                break
        if not summary:
            summary = " ".join((output or "").split())[:ERRSIG_MAX_CHARS] or (
                f"exit code {exit_code}" if has_nonzero else "command failed"
            )
        cmd_words = command.split()
        topic = derive_topic_area(command) or (cmd_words[0] if cmd_words else "tooling")
        return CommandFailureSignal(
            id=new_record_id("command_failure_"),
            command=command,
            error_summary=summary,
            topic_area=topic,
            exit_code=int(exit_code) if exit_code is not None else None,
        )
    except Exception:  # noqa: BLE001
        return None


# --- top-level --------------------------------------------------------------


def extract_signals(
    *,
    recent_session_transcript: str = "",
    today_log: str = "",
    memory_snippet: str = "",
    user_snippet: str = "",
    recent_events: Sequence[Any] = (),
    is_windows: Optional[bool] = None,
) -> list[str]:
    """Extract the active opportunity signals from the current corpus +
    recent history.

    Runs the two local layers (regex + keyword scoring + multilingual
    user-request detection), merges them, then applies the history-aware
    post-processing. Never raises; returns at least one signal (the
    stable-success-plateau fallback) when nothing else fires.
    """
    corpus = assemble_corpus(
        recent_session_transcript=recent_session_transcript,
        today_log=today_log,
        memory_snippet=memory_snippet,
        user_snippet=user_snippet,
    )
    lower = corpus.lower()
    layer1 = extract_regex_signals(corpus, is_windows=is_windows)
    layer1b = extract_user_requests(corpus)
    layer2 = extract_keyword_signals(lower)
    merged = merge_signals(layer1, layer1b, layer2)
    analysis = analyze_recent_history(recent_events)
    return apply_post_processing(merged, analysis)


def has_opportunity_signal(signals: Sequence[str]) -> bool:
    """True iff ``signals`` contains at least one actionable opportunity
    signal (a named opportunity signal or a dynamic error / user-request
    signal), as opposed to only cosmetic / plateau signals."""
    inert = COSMETIC_SIGNALS | {"stable_success_plateau"}
    for s in signals:
        base = signal_base(s)
        if base in inert:
            continue
        if base in OPPORTUNITY_SIGNALS or base in (
            "log_error",
            "errsig",
            "recurring_error",
            "recurring_errsig",
            "user_feature_request",
            "user_improvement_suggestion",
            "user_correction",
            "knowledge_gap",
            "command_failure",
        ):
            return True
    return False


__all__ = [
    "OPPORTUNITY_SIGNALS",
    "COSMETIC_SIGNALS",
    "SIGNAL_PROFILES",
    "SignalProfile",
    "SignalLayer",
    "RecentHistoryAnalysis",
    "REPAIR_LOOP_THRESHOLD",
    "RECENT_WINDOW",
    "EMPTY_CYCLE_THRESHOLD",
    "SATURATION_THRESHOLD",
    "STEADY_STATE_THRESHOLD",
    "FAILURE_STREAK_THRESHOLD",
    "FAILURE_LOOP_THRESHOLD",
    "HIGH_FAILURE_RATIO",
    "signal_base",
    "assemble_corpus",
    "extract_regex_signals",
    "extract_user_requests",
    "extract_keyword_signals",
    "merge_signals",
    "analyze_recent_history",
    "apply_post_processing",
    "extract_signals",
    "has_opportunity_signal",
    # catalog 14 -- qualitative conversation-event detectors
    "QUALITATIVE_CAPTURE_SIGNALS",
    "COMMAND_FAILURE_TOKENS",
    "derive_topic_area",
    "extract_correction",
    "extract_knowledge_gap",
    "extract_feature_request",
    "extract_command_failure",
]
