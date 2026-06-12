"""Observation-stream formatters for the supervisor + narration channels.

Adapted from SWE-Agent's observation-template pattern
(``sweagent/agent/agents.py:TemplateConfig.next_step_truncated_observation_template``
and ``next_step_no_output_template``). Two canonical ACI features land
here:

* **Truncated-observation template (T10).** When a tool's stdout
  exceeds ``max_chars``, return the FIRST ``max_chars // 2`` characters
  + an ``<elided_chars>N characters elided</elided_chars>`` marker +
  the LAST ``max_chars // 2`` characters, wrapped in a warning
  template that suggests ``head``, ``tail``, ``grep``, and output
  redirection as remediation. Head + tail (not head-only) so failure
  summaries at the end of test runs survive truncation.
* **Empty-output template (T19).** When a tool runs successfully but
  produces no output, replace the empty string with an explicit
  ``Your command ran successfully and did not produce any output.``
  message. Silence is itself an observation; without the explicit
  message the LLM frequently misinterprets the empty buffer as a
  silent error.

Both helpers are pure (no I/O, no globals) and run in sub-millisecond
time on the typical observation. They are applied at the LAST step
before forwarding to the LLM so other consumers (audit log, narrator)
see the unfiltered text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default observation cap for the coding supervisor's history. Mirrors
#: SWE-Agent's ``bash_only.yaml`` (10 000 chars). Tight enough that a
#: single long observation can't dominate Claude's context budget.
DEFAULT_MAX_OBSERVATION_CHARS: int = 10_000

#: Conservative cap used when forwarding to the in-process 4B LLM
#: (memory + intent paths). The 4B's effective attention window is
#: smaller than Claude's; this keeps stdin + RAG snippets manageable.
COMPACT_MAX_OBSERVATION_CHARS: int = 4_000

#: Empty-output replacement string (T19). Adapted verbatim from
#: SWE-Agent's ``config/default.yaml`` `next_step_no_output_template`.
EMPTY_OUTPUT_MESSAGE: str = (
    "Your command ran successfully and did not produce any output."
)

#: Empty-output message used when the supervisor's own narrator-gate
#: suppressed the output (distinct from "the tool emitted nothing").
#: Documented in T19 creative extensions.
SUPPRESSED_OUTPUT_MESSAGE: str = (
    "Your command ran successfully; the orchestrator suppressed the "
    "output. Ask for a re-run if you need to see it."
)

_TRUNCATED_TEMPLATE = (
    "<warning>\n"
    "The output of your last command was too long ({total_chars} characters "
    "exceeds the {max_chars}-character cap).\n"
    "Please try a different command that produces less output. If you're "
    "looking at a file you can try use head, tail, or sed to view a smaller "
    "number of lines selectively. If you're using grep or find and it "
    "produced too much output, you can use a more selective search pattern. "
    "If you really need to see something from the full command's output, "
    "you can redirect output to a file and then search in that file.\n"
    "</warning>\n"
    "\n"
    "<observation_head>\n"
    "{head}\n"
    "</observation_head>\n"
    "\n"
    "<elided_chars>{elided} characters elided</elided_chars>\n"
    "\n"
    "<observation_tail>\n"
    "{tail}\n"
    "</observation_tail>"
)


# ---------------------------------------------------------------------------
# Output records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TruncationResult:
    """Result of :func:`truncate_observation`.

    ``text`` is the formatted output ready to forward to the LLM.
    ``original_chars`` / ``kept_chars`` / ``elided_chars`` let callers
    audit the trim (e.g., record in the trajectory or surface to the
    operator if elision is becoming pathological).
    """

    text: str
    truncated: bool
    original_chars: int
    kept_chars: int
    elided_chars: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def truncate_observation(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_OBSERVATION_CHARS,
    template: Optional[str] = None,
) -> TruncationResult:
    """Apply the head + tail + elided-chars template if ``text`` exceeds ``max_chars``.

    Mirrors SWE-Agent's ``next_step_truncated_observation_template`` shape
    so the model sees a consistent error / remediation block. ``max_chars``
    is the TOTAL cap; on truncation the head + tail each get
    ``max_chars // 2`` characters. The remediation hints in the template
    direct the model toward ``head``, ``tail``, ``grep``, and output
    redirection -- the model can satisfy the same information need with
    a smaller observation in one extra turn.

    :param text: raw tool output.
    :param max_chars: total character cap (must be >=10 to allow at
        least 5 head + 5 tail). Default
        :data:`DEFAULT_MAX_OBSERVATION_CHARS`.
    :param template: override the warning template; ``None`` uses
        the default. The template MUST contain the placeholders
        ``{head}``, ``{tail}``, ``{elided}``, ``{total_chars}``,
        ``{max_chars}``.
    :returns: a :class:`TruncationResult` whose ``text`` is safe to
        forward verbatim to the LLM.
    """
    if text is None:
        text = ""
    if max_chars < 10:
        raise ValueError(
            f"max_chars must be >= 10 (got {max_chars}); "
            "smaller caps don't leave room for head + tail"
        )

    original_chars = len(text)
    if original_chars <= max_chars:
        return TruncationResult(
            text=text,
            truncated=False,
            original_chars=original_chars,
            kept_chars=original_chars,
            elided_chars=0,
        )

    half = max_chars // 2
    head = text[:half]
    tail = text[-half:] if half > 0 else ""
    elided = original_chars - len(head) - len(tail)
    if elided < 0:
        elided = 0
    chosen_template = template if template is not None else _TRUNCATED_TEMPLATE
    rendered = chosen_template.format(
        head=head,
        tail=tail,
        elided=elided,
        total_chars=original_chars,
        max_chars=max_chars,
    )
    return TruncationResult(
        text=rendered,
        truncated=True,
        original_chars=original_chars,
        kept_chars=len(head) + len(tail),
        elided_chars=elided,
    )


def wrap_empty_observation(
    text: Optional[str],
    *,
    suppressed: bool = False,
    empty_message: str = EMPTY_OUTPUT_MESSAGE,
    suppressed_message: str = SUPPRESSED_OUTPUT_MESSAGE,
) -> str:
    """Replace an empty observation with an explicit "no output" message.

    Per SWE-Agent's ACI rationale, empty observations are an explicit
    signal -- not a degenerate case -- and the model needs a sentence
    to parse. Without this wrapper the model sees an empty string and
    frequently misinterprets it as a silent tool failure or a hung
    process.

    :param text: raw observation. ``None``, ``""``, or whitespace-only
        all count as empty.
    :param suppressed: when True, returns the SUPPRESSED-output message
        instead of the EMPTY-output message. Callers set this when the
        narrator gate intentionally dropped the output (distinct from
        the tool emitting nothing).
    :param empty_message: override the default empty message.
    :param suppressed_message: override the default suppressed message.
    :returns: ``text`` unchanged if non-empty; otherwise the chosen
        substitute message.
    """
    if text is None or not str(text).strip():
        return suppressed_message if suppressed else empty_message
    return text


def format_observation(
    text: Optional[str],
    *,
    max_chars: int = DEFAULT_MAX_OBSERVATION_CHARS,
    suppressed: bool = False,
) -> str:
    """End-to-end observation formatter.

    Convenience wrapper combining :func:`wrap_empty_observation` and
    :func:`truncate_observation` in the order callers want for the
    LLM-facing channel: replace empty with an explicit message,
    then enforce the head + tail cap. Returns the final string the
    LLM should see.
    """
    cleaned = wrap_empty_observation(text, suppressed=suppressed)
    return truncate_observation(cleaned, max_chars=max_chars).text


__all__ = [
    "COMPACT_MAX_OBSERVATION_CHARS",
    "DEFAULT_MAX_OBSERVATION_CHARS",
    "EMPTY_OUTPUT_MESSAGE",
    "SUPPRESSED_OUTPUT_MESSAGE",
    "TruncationResult",
    "format_observation",
    "truncate_observation",
    "wrap_empty_observation",
]
