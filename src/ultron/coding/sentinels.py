"""Sentinel markers for inter-tool outcome signalling.

Adapted from SWE-Agent's sentinel-based observation-channel pattern
(``tools/submit/bin/submit``, ``tools/forfeit/bin/exit_forfeit``,
``tools/windowed_edit_replace/bin/edit``). The pattern: tools embed
a non-natural ASCII string in their stdout; consumers grep the output
for the sentinel and dispatch on the match without requiring an
in-process import.

For ultron the sentinels let bash-only utilities (``scripts/run_tests.py``,
operator-side smoke scripts, future shell-only readers) report
structured outcomes to the supervisor + observation channel without
coupling to ultron's Python internals.

The pair-marker shape ``<<TOKEN>> ... <<TOKEN>>`` brackets an optional
payload between two copies of the same sentinel; ``observation_scan``
splits this into ``(sentinel, payload_or_none)``.

All sentinel strings are intentionally:

* ASCII-only so PowerShell + cmd + bash + Python repr round-trip safely.
* Surrounded by angle-bracket pairs or hash triples (matches SWE-Agent's
  shape so the same scanners work on both ecosystems).
* Improbable in natural language or code.

This module ships ONLY constants + the pure :func:`observation_scan`
helper. Callers (supervisor, runner, narration) decide how to react
to each match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


# ---------------------------------------------------------------------------
# Pair-marker sentinels (``<<TOKEN>> payload <<TOKEN>>``)
# ---------------------------------------------------------------------------

#: Bracket a final submission (T17 mirror). Mirrors SWE-Agent's
#: ``<<SWE_AGENT_SUBMISSION>>`` exactly in shape; namespaced for ultron.
ULTRON_SUBMIT: str = "<<ULTRON_SUBMIT>>"

#: Bracket a model.patch payload emitted by the coding supervisor on
#: salvage / autosubmission / clean exit.
ULTRON_SUBMIT_DIFF: str = "<<ULTRON_SUBMIT_DIFF>>"

#: Bracket a clean test-sweep banner. ``scripts/run_tests.py`` can print
#: this when the sweep finishes 0 failures so a wrapping orchestrator
#: knows the run was good without re-parsing pytest stdout.
ULTRON_TEST_SWEEP_PASS: str = "<<ULTRON_TEST_SWEEP_PASS>>"

#: Bracket a failed test-sweep banner. Includes the failure count as
#: the payload, e.g. ``<<ULTRON_TEST_SWEEP_FAIL>>3<<ULTRON_TEST_SWEEP_FAIL>>``.
ULTRON_TEST_SWEEP_FAIL: str = "<<ULTRON_TEST_SWEEP_FAIL>>"


# ---------------------------------------------------------------------------
# Single-fire sentinels (``###TOKEN###`` -- no payload)
# ---------------------------------------------------------------------------

#: Mirrors SWE-Agent's ``###SWE-AGENT-EXIT-FORFEIT###``. Emitted by
#: the forfeit tool (T8) and by any subprocess that wants to abandon
#: the current coding task without burning more tokens.
ULTRON_EXIT_FORFEIT: str = "###ULTRON-EXIT-FORFEIT###"

#: Mirrors SWE-Agent's ``###SWE-AGENT-RETRY-WITH-OUTPUT###`` (T12).
#: Indicates a tool's error output is itself the next prompt -- the
#: harness should re-query the model without advancing the action
#: counter.
ULTRON_RETRY_WITH_OUTPUT: str = "###ULTRON-RETRY-WITH-OUTPUT###"

#: Mirrors SWE-Agent's silent-retry sentinel. Same as above but
#: instructs the harness to drop the offending output entirely before
#: re-querying.
ULTRON_RETRY_WITHOUT_OUTPUT: str = "###ULTRON-RETRY-WITHOUT-OUTPUT###"

#: Emitted by the lint-revert path (T1) when the supervisor reverted
#: a Claude edit because it introduced a new syntax error. Lets the
#: completion narrator avoid claiming success on a file Claude touched
#: and lost.
ULTRON_LINT_REVERT: str = "###ULTRON-LINT-REVERT###"

#: Bracket a per-session signal that the safety validator blocked an
#: action. Mirrors the ``BLOCKED_COMMAND`` shape from SWE-Agent's
#: tool-filter error template.
ULTRON_BLOCKED_TOOL: str = "###ULTRON-BLOCKED-TOOL###"

#: All pair-marker sentinels, exported so :func:`observation_scan`
#: can iterate over them in a stable order. Ordered most-specific
#: first so the scanner prefers ``ULTRON_SUBMIT_DIFF`` over
#: ``ULTRON_SUBMIT`` when both could match a fragment.
PAIR_SENTINELS: tuple[str, ...] = (
    ULTRON_SUBMIT_DIFF,
    ULTRON_SUBMIT,
    ULTRON_TEST_SWEEP_PASS,
    ULTRON_TEST_SWEEP_FAIL,
)

#: All single-fire sentinels.
SINGLE_SENTINELS: tuple[str, ...] = (
    ULTRON_EXIT_FORFEIT,
    ULTRON_RETRY_WITH_OUTPUT,
    ULTRON_RETRY_WITHOUT_OUTPUT,
    ULTRON_LINT_REVERT,
    ULTRON_BLOCKED_TOOL,
)


@dataclass(frozen=True)
class SentinelMatch:
    """One sentinel found in an observation stream.

    :param sentinel: the matched sentinel constant (e.g.
        :data:`ULTRON_SUBMIT_DIFF`).
    :param payload: the text BETWEEN two pair-marker copies, or ``None``
        for single-fire sentinels.
    :param start: 0-indexed byte offset of the first sentinel
        character in the source string.
    :param end: 0-indexed byte offset one past the LAST sentinel
        character (for pair markers, the closing copy's last char + 1;
        for single fires, the only copy's last char + 1). This lets
        callers slice the source if they need surrounding context.
    """

    sentinel: str
    payload: Optional[str]
    start: int
    end: int


def observation_scan(
    text: str,
    *,
    pair_sentinels: Sequence[str] = PAIR_SENTINELS,
    single_sentinels: Sequence[str] = SINGLE_SENTINELS,
) -> list[SentinelMatch]:
    """Walk ``text`` left-to-right and return every sentinel hit.

    The scan handles:

    * Pair markers (``<<TOKEN>> payload <<TOKEN>>``). The payload is
      everything between the two copies. Nested pair markers of the
      same kind are not supported (the FIRST closing copy wins).
    * Single-fire sentinels (``###TOKEN###``). One match per occurrence,
      no payload.

    A pair-marker without its closing copy is treated as a single fire:
    the match's ``payload`` is the empty string and ``end`` lands just
    past the opening sentinel. This mirrors how SWE-Agent's submission
    parser treats truncated output -- the partial signal is still
    visible to the operator.

    Matches are returned in the order they appear in the source.
    Pair markers are tried before single fires at any given position so
    a longer prefix wins when both could match.

    :param text: the observation stream to scan; typically tool stdout
        or a captured subprocess output buffer.
    :param pair_sentinels: override the pair-marker set for testing.
        Default :data:`PAIR_SENTINELS`.
    :param single_sentinels: override the single-fire set for testing.
        Default :data:`SINGLE_SENTINELS`.
    :returns: a list of :class:`SentinelMatch` records, possibly empty.
    """
    if not text:
        return []

    out: list[SentinelMatch] = []
    pos = 0
    n = len(text)
    pair_ordered = sorted(pair_sentinels, key=len, reverse=True)
    single_ordered = sorted(single_sentinels, key=len, reverse=True)

    while pos < n:
        # Try pair markers first (longest prefix).
        matched = False
        for marker in pair_ordered:
            if not marker:
                continue
            if not text.startswith(marker, pos):
                continue
            close_at = text.find(marker, pos + len(marker))
            if close_at == -1:
                out.append(
                    SentinelMatch(
                        sentinel=marker,
                        payload="",
                        start=pos,
                        end=pos + len(marker),
                    )
                )
                pos += len(marker)
            else:
                payload_start = pos + len(marker)
                end = close_at + len(marker)
                out.append(
                    SentinelMatch(
                        sentinel=marker,
                        payload=text[payload_start:close_at],
                        start=pos,
                        end=end,
                    )
                )
                pos = end
            matched = True
            break

        if matched:
            continue

        for marker in single_ordered:
            if not marker:
                continue
            if not text.startswith(marker, pos):
                continue
            out.append(
                SentinelMatch(
                    sentinel=marker,
                    payload=None,
                    start=pos,
                    end=pos + len(marker),
                )
            )
            pos += len(marker)
            matched = True
            break

        if matched:
            continue

        pos += 1

    return out


def first_match(
    text: str,
    *,
    sentinel: str,
) -> Optional[SentinelMatch]:
    """Return the first match for ``sentinel`` in ``text``, or ``None``.

    Convenience wrapper used by callers that only care about a specific
    sentinel (e.g. the forfeit watcher only looks for
    :data:`ULTRON_EXIT_FORFEIT`).
    """
    if sentinel in PAIR_SENTINELS:
        matches = observation_scan(
            text, pair_sentinels=(sentinel,), single_sentinels=()
        )
    elif sentinel in SINGLE_SENTINELS:
        matches = observation_scan(
            text, pair_sentinels=(), single_sentinels=(sentinel,)
        )
    else:
        # Treat unknown sentinels as single-fire so callers can use the
        # helper for ad-hoc markers.
        matches = observation_scan(
            text, pair_sentinels=(), single_sentinels=(sentinel,)
        )
    return matches[0] if matches else None


def strip_sentinels(text: str) -> str:
    """Return ``text`` with every sentinel match (and any pair payload)
    removed.

    Used by the supervisor before forwarding tool output to the LLM so
    the model never sees the sentinels themselves -- they're a private
    channel between ultron's tools and the orchestrator.
    """
    if not text:
        return ""

    matches = observation_scan(text)
    if not matches:
        return text

    parts: list[str] = []
    prev = 0
    for match in matches:
        parts.append(text[prev:match.start])
        prev = match.end
    parts.append(text[prev:])
    return "".join(parts)


__all__ = [
    "PAIR_SENTINELS",
    "SINGLE_SENTINELS",
    "SentinelMatch",
    "ULTRON_BLOCKED_TOOL",
    "ULTRON_EXIT_FORFEIT",
    "ULTRON_LINT_REVERT",
    "ULTRON_RETRY_WITH_OUTPUT",
    "ULTRON_RETRY_WITHOUT_OUTPUT",
    "ULTRON_SUBMIT",
    "ULTRON_SUBMIT_DIFF",
    "ULTRON_TEST_SWEEP_FAIL",
    "ULTRON_TEST_SWEEP_PASS",
    "first_match",
    "observation_scan",
    "strip_sentinels",
]
