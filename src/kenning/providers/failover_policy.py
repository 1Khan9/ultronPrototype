"""Failover-reason taxonomy + per-reason probe / transient-slot rules.

T6 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Classifies
every provider-side error into one of 13 canonical reasons, and
encodes the policy rules for each:

* **Should we ever retry this provider?** (cooldown-probe permission)
* **Does this kind of failure consume a transient-retry slot?**

Reasons that are PERMANENT (auth misconfiguration, model not found,
session expired, format errors) are both probe-blocked and
transient-slot-skipping — once the orchestrator sees them the
provider stays disabled until manually reset. Reasons that are
TRANSIENT (rate limit, overload, timeout, empty response) get a
cooldown-probe and consume a transient slot — the provider returns
to rotation after the cooldown but loses one of its retry budget.
``BILLING`` is special: probe allowed (a payment problem can clear),
but no transient slot (one billing failure deserves operator attention
rather than another auto-retry).
"""

from __future__ import annotations

from enum import Enum


class FailoverReason(str, Enum):
    """Canonical taxonomy of provider failure reasons.

    Mirrors OpenClaw's ``FailoverReason`` enum at
    ``src/agents/failover-policy.ts``. 13 distinct reasons.
    """

    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    BILLING = "billing"
    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    SESSION_EXPIRED = "session_expired"
    MODEL_NOT_FOUND = "model_not_found"
    FORMAT = "format"
    TIMEOUT = "timeout"
    EMPTY_RESPONSE = "empty_response"
    NO_ERROR_DETAILS = "no_error_details"
    UNCLASSIFIED = "unclassified"
    UNKNOWN = "unknown"


#: Per-reason human-readable description (for logs / audit / voice
#: messages explaining why a provider was disabled).
FAILOVER_REASON_DESCRIPTIONS: dict[FailoverReason, str] = {
    FailoverReason.RATE_LIMIT: "Provider returned a rate-limit signal (HTTP 429 or equivalent).",
    FailoverReason.OVERLOADED: "Provider is temporarily overloaded; retry later.",
    FailoverReason.BILLING: "Provider reported a billing issue; clear the payment problem and resume.",
    FailoverReason.AUTH: "Provider rejected the credential.",
    FailoverReason.AUTH_PERMANENT: "Provider permanently rejected the credential.",
    FailoverReason.SESSION_EXPIRED: "Provider session expired; re-auth required.",
    FailoverReason.MODEL_NOT_FOUND: "Provider does not host the requested model.",
    FailoverReason.FORMAT: "Provider rejected the request format.",
    FailoverReason.TIMEOUT: "Provider exceeded the per-request timeout.",
    FailoverReason.EMPTY_RESPONSE: "Provider returned an empty response.",
    FailoverReason.NO_ERROR_DETAILS: "Provider failed without surfacing error details.",
    FailoverReason.UNCLASSIFIED: "Provider error did not match any taxonomy entry.",
    FailoverReason.UNKNOWN: "Provider error class is unknown to the classifier.",
}


#: Reasons that earn a cooldown-probe retry. Permanent / structural
#: failures (auth misconfiguration, model not found, format) are
#: deliberately excluded — probing them is just wasted requests
#: against a provider that won't recover without operator action.
FAILOVER_PROBE_REASONS: frozenset[FailoverReason] = frozenset({
    FailoverReason.RATE_LIMIT,
    FailoverReason.OVERLOADED,
    FailoverReason.BILLING,
    FailoverReason.TIMEOUT,
    FailoverReason.EMPTY_RESPONSE,
    FailoverReason.NO_ERROR_DETAILS,
    FailoverReason.UNCLASSIFIED,
    FailoverReason.UNKNOWN,
})


#: Reasons that consume a transient-retry slot when the provider is
#: probed. ``BILLING`` is deliberately excluded — one billing
#: failure should surface to the operator rather than burn another
#: auto-retry.
FAILOVER_TRANSIENT_SLOT_REASONS: frozenset[FailoverReason] = frozenset({
    FailoverReason.RATE_LIMIT,
    FailoverReason.OVERLOADED,
    FailoverReason.TIMEOUT,
    FailoverReason.EMPTY_RESPONSE,
    FailoverReason.NO_ERROR_DETAILS,
    FailoverReason.UNCLASSIFIED,
    FailoverReason.UNKNOWN,
})


def should_allow_cooldown_probe(reason: FailoverReason) -> bool:
    """Whether a provider with the given last failure may be probed.

    Returns ``True`` for transient-friendly reasons (rate-limit,
    overload, timeout, etc.) and ``False`` for permanent-structural
    ones (auth misconfiguration, model not found, format).
    """
    return reason in FAILOVER_PROBE_REASONS


def should_use_transient_cooldown_slot(reason: FailoverReason) -> bool:
    """Whether a probed failure consumes a transient retry slot.

    ``BILLING`` returns ``False`` — the catalog explicitly excludes
    billing from the transient-slot mechanism so operator review is
    forced after one billing-related disable.
    """
    return reason in FAILOVER_TRANSIENT_SLOT_REASONS


__all__ = [
    "FAILOVER_PROBE_REASONS",
    "FAILOVER_REASON_DESCRIPTIONS",
    "FAILOVER_TRANSIENT_SLOT_REASONS",
    "FailoverReason",
    "should_allow_cooldown_probe",
    "should_use_transient_cooldown_slot",
]
