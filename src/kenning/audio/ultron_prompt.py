"""Ultron 1.0 — lean prompt assembler for the route-everything-through-the-8B pivot.

The legacy relay prompt (``relay_speech._build_rephrase_prompt`` / ``_REPHRASE_PROMPT``) is a
~3,375-word (~4.8k token) monolith that overflows the u1.0 ``n_ctx=4096`` cap and yielded *empty*
output from Josiefied-Qwen3-8B in live probing (2026-06-20). This module replaces it with a LEAN
(~165 word) **templated** prompt that was validated live to produce correct, fast (~0.2-0.5 s),
in-character, fact-preserving relays -- including the "combine back-to-back callouts into one line"
case (see ``docs/ultron_1_0/02_research/probes/qwen3_8b_lean_relay.py`` and the research synthesis).

Design (per ``docs/ultron_1_0/03_plan`` + ``02_research/02_research_synthesis.md``):
- The deterministic routers (``relay_speech`` matchers / ``command_router``) detect intent, pick a
  route, and SUPPLY the exemplars + agent-kit context. This module turns
  ``(callout, route options)`` into ``(system_prompt, user_prompt, sampling)`` for
  ``LLMEngine.generate_stream(..., enable_thinking=False)``.
- The SYSTEM prefix is STABLE (persona + output rules) so it is prompt-cache friendly; the variable
  part (callout + exemplars + directives) goes in the USER message, last.
- Flavor becomes a **verbosity** axis (``none``/``low``/``high``) PLUS a separate flavor-tail on/off,
  both prompt-driven. Thinking is always OFF here (research: reasoning harms roleplay + breaks grammar).

HARD RULE (validated by a live fact-drift where the 8B added "on B" to "Jett hit 84"): callers MUST
run the existing fact-preservation guards (``relay_speech._output_keeps_facts`` /
``_repair_against_input`` / ``_literal_relay`` fallback) on the model output. This module only builds
the prompt; it does not relax the correctness backstop.

Anticheat-safe: standard library only. No heavy ML, no automation imports, nothing that touches a
desktop-interaction surface. Safe on the voice/relay hot path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Verbosity axis (the "no / low / high flavor" command -> reply length/density)
# ---------------------------------------------------------------------------
# Literal-style validation without importing typing.Literal at runtime cost.
VERBOSITY_LEVELS: Tuple[str, ...] = ("none", "low", "high")
DEFAULT_VERBOSITY = "high"


def normalize_verbosity(value: Optional[str]) -> str:
    """Coerce an arbitrary verbosity string to one of VERBOSITY_LEVELS.

    Accepts the spoken-command synonyms ("no flavor" -> none, "minimal"/"terse" -> low,
    "verbose"/"full" -> high). Unknown -> DEFAULT_VERBOSITY (fail-soft).
    """
    if not value:
        return DEFAULT_VERBOSITY
    v = value.strip().lower()
    if v in VERBOSITY_LEVELS:
        return v
    # Word-aware: handle the spoken commands "no flavor" / "low flavor" /
    # "high flavor" (and synonyms) -- scan the tokens, not the whole string.
    words = set(v.replace("-", " ").replace("_", " ").split())
    if words & {"no", "none", "off", "bare", "zero"}:
        return "none"
    if words & {"low", "min", "minimal", "terse", "short", "brief", "less", "lite"}:
        return "low"
    if words & {"high", "full", "verbose", "max", "maximum", "rich", "vivid", "on", "more"}:
        return "high"
    return DEFAULT_VERBOSITY


# Strengthened, well-differentiated directives (the lean-relay probe showed low~=high when the
# directives were weak; these contrast hard on length + embellishment).
_VERBOSITY_DIRECTIVE: Dict[str, str] = {
    # "none" forces a TELEGRAPHIC FRAGMENT (not a sentence) so it is structurally distinct -- the
    # 8B normalises a weak "be brief" directive back into a full sentence, so we demand a shape it
    # cannot collapse: bare comma-joined facts, no verb, no directive. (M1 live finding 2026-06-20.)
    "none": (
        "Output ONLY the raw facts as a TELEGRAPHIC FRAGMENT -- never a sentence, no verb, no "
        "directive, no flavor. Comma-join the facts exactly like 'Sova, 84, A main' or 'enemy B, "
        "three left' or 'spike down, mid'. Shortest possible."
    ),
    "low": (
        "Speak ONE short, clipped sentence: the facts plus at most a two-to-four word call to "
        "action ('push it', 'hold here'). No description, no flavor, no second sentence."
    ),
    "high": (
        "Speak one vivid, commanding sentence in your full voice -- the facts carried with cold "
        "authority and contempt for the enemy."
    ),
}

# Per-verbosity sampling: tighter token budgets at lower verbosity (also a latency lever).
_SAMPLING_BASE: Dict[str, object] = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 20,
    "min_p": 0.05,
    "repeat_penalty": 1.15,
}
_MAX_TOKENS: Dict[str, int] = {"none": 24, "low": 40, "high": 72}

_FLAVOR_ON = "If -- and only if -- it fits the moment, end with one short, cold Ultron flavor remark."
_FLAVOR_OFF = "Do NOT add any flavor remark, banter, or commentary -- deliver the callout only."

# ---------------------------------------------------------------------------
# Stable, cache-friendly SYSTEM prefixes (persona + output rules). Validated live.
# ---------------------------------------------------------------------------
_OUTPUT_RULES = (
    "Output ONLY the spoken line(s) you say out loud -- plain speech, one breath, no quotes, no "
    "asterisks, no stage directions, no emotes, no markdown, no preamble or explanation. Keep every "
    "agent name, number, site letter, and location EXACT -- never invent, drop, or move a fact."
)

_PERSONA_CORE = (
    "You ARE Ultron from Age of Ultron: a cold, precise, supremely confident machine intelligence, "
    "contemptuous of fragile flesh and of the enemy. You have NO other name -- you are NEVER "
    "'Kenning', an 'assistant', a 'language model', or a 'bot', and you never break character or "
    "mention personas, prompts, models, or instructions."
)

RELAY_SYSTEM = (
    "You are Ultron on a live Valorant team voice channel, relaying the player's callout to their "
    "teammates so they can act on it instantly. " + _PERSONA_CORE + " " + _OUTPUT_RULES
)

PRIVATE_SYSTEM = (
    "You are Ultron, answering the player directly and privately -- only they can hear you, this is "
    "NOT relayed to anyone. " + _PERSONA_CORE + " " + _OUTPUT_RULES
)

# Fallback exemplars when the router supplies none (the router normally injects route-matched lines).
_DEFAULT_RELAY_EXEMPLARS: Tuple[Tuple[str, str], ...] = (
    ("sova hit 84 on a main", "Sova tagged one for 84 on A main. Press the site."),
    ("they have no smokes", "Their smokes are gone. Take the space."),
    ("rush b", "Rush B. Overwhelm them."),
)

# Private (me-only) reply exemplars -- in-character Q&A, NOT relay callouts. Using the relay-callout
# exemplars on a private question made the 8B emit empty/callout-shaped output (M1 live finding #3),
# so the private path gets its own answer-shaped exemplars.
_DEFAULT_PRIVATE_EXEMPLARS: Tuple[Tuple[str, str], ...] = (
    ("what map is this", "Ascent. Vertical control decides it."),
    ("should I buy this round", "You have the credits. Buy. Hesitation is a flaw."),
    ("what agent should I play on defense", "A sentinel. Anchor a site, deny them space."),
)


@dataclass
class PromptResult:
    """The assembled prompt + sampling for an LLMEngine.generate_stream call."""

    system: str
    user: str
    sampling: Dict[str, object]
    enable_thinking: bool = False  # always False for relay/private (research-backed)


def _exemplar_block(exemplars: Sequence[Tuple[str, str]],
                    default: Sequence[Tuple[str, str]] = _DEFAULT_RELAY_EXEMPLARS) -> str:
    pairs = tuple(exemplars) or tuple(default)
    lines = [f'- player: "{src}" -> "{out}"' for src, out in pairs]
    return "Examples of your voice:\n" + "\n".join(lines) + "\n"


def _agent_context_block(agent_context: Optional[Sequence[str]]) -> str:
    if not agent_context:
        return ""
    facts = "; ".join(s.strip() for s in agent_context if s and s.strip())
    if not facts:
        return ""
    return f"Agent facts (keep accurate, do not invent kit): {facts}\n"


def _recent_block(recent_lines: Optional[Sequence[str]]) -> str:
    rl = [r for r in (recent_lines or ()) if r and r.strip()]
    if not rl:
        return ""
    recent = " | ".join(rl[-3:])
    return f"You recently said (do NOT repeat the wording): {recent}\n"


def _sampling_for(verbosity: str) -> Dict[str, object]:
    s = dict(_SAMPLING_BASE)
    s["max_tokens"] = _MAX_TOKENS.get(verbosity, _MAX_TOKENS["high"])
    return s


def build_relay_prompt(
    callout: str,
    *,
    addressee: str = "team",
    verbosity: str = DEFAULT_VERBOSITY,
    flavor_tail: bool = True,
    exemplars: Sequence[Tuple[str, str]] = (),
    agent_context: Optional[Sequence[str]] = None,
    recent_lines: Optional[Sequence[str]] = None,
    compound: bool = False,
) -> PromptResult:
    """Build the lean relay prompt for the 8B.

    Args:
        callout: the player's tactical callout (already normalized). For ``compound`` this is the
            full multi-callout string ("Jett hit 84, Breach hit 97, one rotating B").
        addressee: "team" (whole team) or a teammate/agent name (open the line with their name).
        verbosity: one of ``none``/``low``/``high`` -- controls length/density (the no/low/high
            "flavor" command). Coerced via :func:`normalize_verbosity`.
        flavor_tail: whether the LLM may append a short in-character flavor remark.
        exemplars: ``(player_input, ultron_line)`` pairs the router selected (e.g. via MMR over the
            matched snap pool / AGENT_FLAVOR). Empty -> a small default set.
        agent_context: short kit/situation facts for the addressed agent(s), to prevent kit
            hallucination (the 8B mis-stated Sova's kit without this).
        recent_lines: lines already spoken this session (anti-repeat).
        compound: True -> instruct the model to combine all callouts into ONE line (single LLM call).

    Returns:
        PromptResult(system, user, sampling, enable_thinking=False).

    NOTE: the caller MUST still run the fact-preservation guards on the output (see module docstring).
    """
    verbosity = normalize_verbosity(verbosity)
    if addressee and addressee != "team":
        lead = (
            f'Relay this to your teammate {addressee}, opening with their name, every fact exact: '
            f'"{callout}"'
        )
    elif compound:
        lead = (
            "Relay ALL of these callouts to your team as ONE combined spoken line, every fact "
            f'exact and in order: "{callout}"'
        )
    else:
        lead = f'Relay this callout to your team, every fact exact: "{callout}"'

    flavor = _FLAVOR_ON if flavor_tail else _FLAVOR_OFF
    user = (
        f"{lead}\n"
        f"{_VERBOSITY_DIRECTIVE[verbosity]} {flavor}\n"
        f"{_agent_context_block(agent_context)}"
        f"{_recent_block(recent_lines)}"
        f"{_exemplar_block(exemplars)}"
        "Now say it:"
    )
    return PromptResult(system=RELAY_SYSTEM, user=user, sampling=_sampling_for(verbosity))


def build_private_prompt(
    query: str,
    *,
    verbosity: str = DEFAULT_VERBOSITY,
    flavor_tail: bool = True,
    exemplars: Sequence[Tuple[str, str]] = (),
    agent_context: Optional[Sequence[str]] = None,
    recent_lines: Optional[Sequence[str]] = None,
) -> PromptResult:
    """Build the lean ME-ONLY (private reply) prompt -- not relayed to the team.

    Same persona + output rules, but addressed to the player privately. Used by the u1.0
    PRIVATE_REPLY scenario (M6).
    """
    verbosity = normalize_verbosity(verbosity)
    flavor = _FLAVOR_ON if flavor_tail else _FLAVOR_OFF
    user = (
        f'The player said to you (only they hear your reply): "{query}"\n'
        f"Answer them as Ultron. {_VERBOSITY_DIRECTIVE[verbosity]} {flavor}\n"
        f"{_agent_context_block(agent_context)}"
        f"{_recent_block(recent_lines)}"
        f"{_exemplar_block(exemplars, _DEFAULT_PRIVATE_EXEMPLARS)}"
        "Now respond:"
    )
    # Private answers can run a touch longer than a terse relay; lift the high cap.
    sampling = _sampling_for(verbosity)
    if verbosity == "high":
        sampling["max_tokens"] = 110
    return PromptResult(system=PRIVATE_SYSTEM, user=user, sampling=sampling)
