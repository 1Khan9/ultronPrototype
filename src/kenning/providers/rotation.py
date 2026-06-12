"""Provider rotation driver with cooldown-aware retries.

T6 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). The
public function :func:`execute_with_rotation` mirrors OpenClaw's
``executeWithApiKeyRotation``: a nested loop with rate-limit-rotates
+ transient-retry-same-key semantics, augmented with the failover
taxonomy from :mod:`ultron.providers.failover_policy`.

Algorithm:

1. Pull eligible profiles from the store (READY or cooled-down).
2. Outer loop: iterate over the eligible profiles in priority order.
3. Inner loop: retry the SAME profile up to ``max_transient_retries``
   times when the error is transient (timeout / empty response).
4. ``RATE_LIMIT`` errors immediately break inner loop + rotate to
   the next profile (don't burn transient slots on a known-saturated
   provider).
5. ``AUTH`` / ``MODEL_NOT_FOUND`` / ``FORMAT`` errors disable the
   profile without rotation; raise to caller.
6. Each transient-eligible failure consumes one transient slot.

The classifier :func:`classify_provider_error` lets callers map
domain-specific errors to :class:`FailoverReason` values; pass a
custom classifier for non-standard HTTP-status mappings.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Optional, Sequence

from .auth_profiles import (
    AuthProfile,
    AuthProfileState,
    AuthProfileStore,
    DEFAULT_MAX_TRANSIENT_RETRIES,
    get_profile_store,
)
from .failover_policy import FailoverReason, should_use_transient_cooldown_slot

LOGGER = logging.getLogger(__name__)


#: Per-attempt transient retry delay (seconds). Mirrors the OpenClaw
#: simple sleep-then-retry pattern; callers that need exponential
#: backoff should pass a custom ``delay_fn``.
DEFAULT_TRANSIENT_DELAY_SECONDS: float = 0.5


class RotationOutcome(str, Enum):
    """Final outcome of :func:`execute_with_rotation`."""

    SUCCESS = "success"
    EXHAUSTED = "exhausted"
    DISABLED_ALL = "disabled_all"


@dataclass
class RotationAttempt:
    """One per-attempt record kept for the audit log."""

    profile_id: str
    succeeded: bool
    reason: Optional[FailoverReason] = None
    elapsed_seconds: float = 0.0


@dataclass
class RotationResult:
    """Outcome of one :func:`execute_with_rotation` call."""

    outcome: RotationOutcome
    value: Any = None
    attempts: tuple[RotationAttempt, ...] = field(default_factory=tuple)
    last_error: Optional[BaseException] = None
    last_reason: Optional[FailoverReason] = None

    @property
    def succeeded(self) -> bool:
        return self.outcome == RotationOutcome.SUCCESS


# ----------------------------------------------------------------------
# Classifier


def classify_provider_error(error: BaseException) -> FailoverReason:
    """Best-effort default classifier from exception text.

    Looks for HTTP-status hints + common error-message substrings.
    Callers with structured error types should pass a custom
    classifier to :func:`execute_with_rotation` rather than rely on
    text matching.
    """
    text = str(error).lower()
    # Order matters — most specific first.
    if "rate limit" in text or "rate_limit" in text or " 429" in text or "too many requests" in text:
        return FailoverReason.RATE_LIMIT
    if "overload" in text or " 503" in text or "service unavailable" in text:
        return FailoverReason.OVERLOADED
    if "billing" in text or "payment" in text or "quota" in text or " 402" in text:
        return FailoverReason.BILLING
    if "unauthorised" in text or "unauthorized" in text or " 401" in text:
        return FailoverReason.AUTH
    if "forbidden" in text or " 403" in text:
        return FailoverReason.AUTH_PERMANENT
    if "session" in text and "expired" in text:
        return FailoverReason.SESSION_EXPIRED
    if "model" in text and ("not found" in text or "unknown" in text):
        return FailoverReason.MODEL_NOT_FOUND
    if "format" in text or "schema" in text or "validation" in text or " 422" in text:
        return FailoverReason.FORMAT
    if "timeout" in text or "timed out" in text:
        return FailoverReason.TIMEOUT
    if "empty" in text and "response" in text:
        return FailoverReason.EMPTY_RESPONSE
    if not text or text in ("error", "exception", "failed"):
        return FailoverReason.NO_ERROR_DETAILS
    return FailoverReason.UNCLASSIFIED


# ----------------------------------------------------------------------
# Driver


def execute_with_rotation(
    *,
    provider: str,
    operation: Callable[[AuthProfile], Any],
    store: Optional[AuthProfileStore] = None,
    classifier: Callable[[BaseException], FailoverReason] = classify_provider_error,
    max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES,
    transient_delay_seconds: float = DEFAULT_TRANSIENT_DELAY_SECONDS,
    delay_fn: Optional[Callable[[float], None]] = None,
    cooldown_seconds: Optional[float] = None,
    clock: Optional[Callable[[], float]] = None,
) -> RotationResult:
    """Run ``operation`` against the eligible profiles in rotation.

    Args:
        provider: provider name (filters which profiles compete).
        operation: callable taking an :class:`AuthProfile` and
            returning the operation's value. Raises on failure.
        store: profile store (defaults to module singleton).
        classifier: error -> :class:`FailoverReason` mapping.
        max_transient_retries: per-profile transient retry cap.
        transient_delay_seconds: sleep between transient retries.
        delay_fn: optional sleep callable (defaults to
            :func:`time.sleep`); tests pass a no-op.
        cooldown_seconds: per-call override for profile cooldown
            when a probe-eligible failure fires. ``None`` uses the
            store's default.
        clock: optional time source for the attempt-elapsed metric.

    Returns:
        :class:`RotationResult`.
    """
    s = store or get_profile_store()
    sleep = delay_fn or time.sleep
    now = clock or time.monotonic
    eligible: Sequence[AuthProfile] = s.list_eligible(provider)
    if not eligible:
        return RotationResult(
            outcome=RotationOutcome.DISABLED_ALL,
            attempts=(),
            last_reason=None,
        )
    attempts: list[RotationAttempt] = []
    last_error: Optional[BaseException] = None
    last_reason: Optional[FailoverReason] = None
    for profile in eligible:
        # Per-profile transient retry loop.
        transient_left = min(max_transient_retries, profile.transient_slots_remaining)
        while True:
            start = now()
            s.record_attempt(profile.profile_id)
            try:
                value = operation(profile)
            except BaseException as exc:  # noqa: BLE001 — classifier decides
                elapsed = max(0.0, now() - start)
                reason = classifier(exc)
                attempts.append(
                    RotationAttempt(
                        profile_id=profile.profile_id,
                        succeeded=False,
                        reason=reason,
                        elapsed_seconds=elapsed,
                    )
                )
                last_error = exc
                last_reason = reason
                new_state = s.record_failure(
                    profile.profile_id,
                    reason,
                    cooldown_seconds=cooldown_seconds,
                )
                # Rate-limit immediately rotates (don't burn transient
                # slots on a known-saturated provider).
                if reason == FailoverReason.RATE_LIMIT:
                    break
                # Permanent reasons disable + rotate.
                if new_state == AuthProfileState.DISABLED:
                    break
                # Transient — consume a slot if reason qualifies.
                if should_use_transient_cooldown_slot(reason):
                    transient_left -= 1
                    s.consume_transient_slot(profile.profile_id)
                else:
                    # No transient slot consumed (e.g. BILLING) but also
                    # don't retry same key — rotate.
                    break
                if transient_left <= 0:
                    break
                sleep(max(0.0, transient_delay_seconds))
                # Retry SAME profile.
                continue
            else:
                elapsed = max(0.0, now() - start)
                attempts.append(
                    RotationAttempt(
                        profile_id=profile.profile_id,
                        succeeded=True,
                        reason=None,
                        elapsed_seconds=elapsed,
                    )
                )
                s.record_success(profile.profile_id)
                return RotationResult(
                    outcome=RotationOutcome.SUCCESS,
                    value=value,
                    attempts=tuple(attempts),
                )
    return RotationResult(
        outcome=RotationOutcome.EXHAUSTED,
        attempts=tuple(attempts),
        last_error=last_error,
        last_reason=last_reason,
    )


__all__ = [
    "DEFAULT_TRANSIENT_DELAY_SECONDS",
    "RotationAttempt",
    "RotationOutcome",
    "RotationResult",
    "classify_provider_error",
    "execute_with_rotation",
]
