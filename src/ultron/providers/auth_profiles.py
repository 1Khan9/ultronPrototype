"""Auth-profile state + per-provider cooldown registry.

T6 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Each
provider chain (STT, TTS, web search, reader, future LLM cascade)
maintains a set of :class:`AuthProfile` entries — one per
credential / endpoint variant. The profile records last-good
timestamp, current failure count, last failure reason, and
cooldown-until timestamp.

Lifecycle:

1. Profile starts in :attr:`AuthProfileState.READY`.
2. On success — :meth:`AuthProfileStore.record_success` clears
   failures and the cooldown timer.
3. On failure — :meth:`AuthProfileStore.record_failure` increments
   the failure counter and, if the reason allows cooldown-probe,
   sets a cooldown-until timestamp.
4. After ``MAX_FAILURE_COUNT`` consecutive failures the profile
   transitions to :attr:`AuthProfileState.DISABLED` until the
   operator explicitly re-enables it via :meth:`reset_profile`.

The store is thread-safe + per-provider scoped. The orchestrator
holds one shared store; each provider chain queries it via
:meth:`AuthProfileStore.list_eligible` to pick the next profile to
attempt.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .failover_policy import FailoverReason, should_allow_cooldown_probe

LOGGER = logging.getLogger(__name__)

#: Default cooldown applied after a probe-eligible failure (seconds).
#: The orchestrator can override per-provider via the
#: :meth:`record_failure` call.
DEFAULT_COOLDOWN_SECONDS: float = 30.0

#: Max consecutive failures before a profile is auto-disabled.
#: Once reached, the profile stays disabled until the operator
#: clears it via :meth:`reset_profile` — defends against runaway
#: retry loops on a fundamentally-broken provider.
MAX_FAILURE_COUNT: int = 5

#: Default cap on per-key transient retries (used by
#: :func:`execute_with_rotation` in :mod:`ultron.providers.rotation`).
DEFAULT_MAX_TRANSIENT_RETRIES: int = 3


class AuthProfileState(str, Enum):
    """Lifecycle state of an auth profile."""

    READY = "ready"
    COOLING_DOWN = "cooling_down"
    DISABLED = "disabled"


@dataclass
class AuthProfile:
    """One provider credential variant + its rotation state.

    Attributes:
        profile_id: caller-supplied identifier (typically the
            ``(provider, credential_hash)`` tuple flattened to string).
        provider: the provider chain this profile belongs to
            (``"brave"`` / ``"parakeet"`` / etc.). Used by the store
            to scope listings.
        priority: lower value = earlier in rotation. Profiles with
            equal priority are rotated round-robin.
        state: current :class:`AuthProfileState`.
        failure_count: consecutive failures since last success.
        last_failure_reason: most recent :class:`FailoverReason`.
        cooldown_until_seconds: monotonic deadline before which the
            profile is COOLING_DOWN. ``None`` when ready.
        transient_slots_remaining: per-window cap on transient retries.
            Decremented when a transient-eligible failure consumes a
            slot. Replenished on success.
        last_attempt_seconds / last_success_seconds: monotonic timestamps.
        metadata: free-form per-profile state.
    """

    profile_id: str
    provider: str
    priority: int = 0
    state: AuthProfileState = AuthProfileState.READY
    failure_count: int = 0
    last_failure_reason: Optional[FailoverReason] = None
    cooldown_until_seconds: Optional[float] = None
    transient_slots_remaining: int = DEFAULT_MAX_TRANSIENT_RETRIES
    last_attempt_seconds: Optional[float] = None
    last_success_seconds: Optional[float] = None
    metadata: dict = field(default_factory=dict)


class AuthProfileStore:
    """Thread-safe per-provider auth-profile registry.

    Constructor accepts optional ``clock`` for deterministic tests.
    All public methods are thread-safe.
    """

    def __init__(
        self,
        *,
        clock: Optional[callable] = None,
        max_failure_count: int = MAX_FAILURE_COUNT,
        default_cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        default_transient_slots: int = DEFAULT_MAX_TRANSIENT_RETRIES,
    ) -> None:
        self._clock = clock or time.monotonic
        self._max_failures = int(max_failure_count)
        self._default_cooldown = float(default_cooldown_seconds)
        self._default_transient = int(default_transient_slots)
        self._profiles: dict[str, AuthProfile] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration / lookup

    def register(
        self,
        profile: AuthProfile,
    ) -> AuthProfile:
        """Add or replace a profile under its ``profile_id``."""
        if not profile.profile_id:
            raise ValueError("profile_id must be non-empty")
        if not profile.provider:
            raise ValueError("provider must be non-empty")
        with self._lock:
            self._profiles[profile.profile_id] = profile
            return profile

    def unregister(self, profile_id: str) -> bool:
        """Drop the profile if present."""
        with self._lock:
            return self._profiles.pop(profile_id, None) is not None

    def get(self, profile_id: str) -> Optional[AuthProfile]:
        with self._lock:
            return self._profiles.get(profile_id)

    def list_for_provider(self, provider: str) -> tuple[AuthProfile, ...]:
        """All profiles for ``provider`` (any state), sorted by priority."""
        with self._lock:
            matches = [p for p in self._profiles.values() if p.provider == provider]
        return tuple(sorted(matches, key=lambda p: (p.priority, p.profile_id)))

    def list_eligible(self, provider: str) -> tuple[AuthProfile, ...]:
        """READY profiles for ``provider`` (or cooled-down past deadline).

        Side effect: a profile in COOLING_DOWN whose deadline has
        passed transitions back to READY before being returned.
        """
        now = self._clock()
        with self._lock:
            out: list[AuthProfile] = []
            for profile in self._profiles.values():
                if profile.provider != provider:
                    continue
                if profile.state == AuthProfileState.DISABLED:
                    continue
                if profile.state == AuthProfileState.COOLING_DOWN:
                    if (
                        profile.cooldown_until_seconds is not None
                        and now >= profile.cooldown_until_seconds
                    ):
                        # Cooldown elapsed — promote back to READY.
                        profile.state = AuthProfileState.READY
                        profile.cooldown_until_seconds = None
                    else:
                        continue
                out.append(profile)
        return tuple(sorted(out, key=lambda p: (p.priority, p.profile_id)))

    # ------------------------------------------------------------------
    # Lifecycle helpers

    def record_attempt(self, profile_id: str) -> None:
        """Mark an attempt timestamp (does not change state)."""
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                return
            profile.last_attempt_seconds = self._clock()

    def record_success(self, profile_id: str) -> None:
        """Clear failure counter + cooldown + transient slot count."""
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                return
            profile.failure_count = 0
            profile.last_failure_reason = None
            profile.cooldown_until_seconds = None
            profile.state = AuthProfileState.READY
            profile.transient_slots_remaining = self._default_transient
            profile.last_success_seconds = self._clock()

    def record_failure(
        self,
        profile_id: str,
        reason: FailoverReason,
        *,
        cooldown_seconds: Optional[float] = None,
    ) -> AuthProfileState:
        """Record a failure; transition state per policy.

        Returns the new state for the caller's convenience.
        """
        now = self._clock()
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                return AuthProfileState.READY
            profile.failure_count += 1
            profile.last_failure_reason = reason
            profile.last_attempt_seconds = now
            if profile.failure_count >= self._max_failures:
                profile.state = AuthProfileState.DISABLED
                profile.cooldown_until_seconds = None
                return AuthProfileState.DISABLED
            if should_allow_cooldown_probe(reason):
                cooldown = cooldown_seconds if cooldown_seconds is not None else self._default_cooldown
                profile.state = AuthProfileState.COOLING_DOWN
                profile.cooldown_until_seconds = now + max(0.0, float(cooldown))
            else:
                # Permanent-structural reasons disable immediately.
                profile.state = AuthProfileState.DISABLED
                profile.cooldown_until_seconds = None
            return profile.state

    def consume_transient_slot(self, profile_id: str) -> int:
        """Decrement the per-profile transient retry counter.

        Returns the slots remaining after the decrement.
        """
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                return 0
            if profile.transient_slots_remaining > 0:
                profile.transient_slots_remaining -= 1
            return profile.transient_slots_remaining

    def reset_profile(self, profile_id: str) -> bool:
        """Operator-driven re-enable. Returns ``True`` on hit."""
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                return False
            profile.state = AuthProfileState.READY
            profile.failure_count = 0
            profile.last_failure_reason = None
            profile.cooldown_until_seconds = None
            profile.transient_slots_remaining = self._default_transient
            return True

    def clear(self) -> None:
        """Test helper: drop every profile."""
        with self._lock:
            self._profiles.clear()


# ----------------------------------------------------------------------
# Module-level singleton


_store_singleton: Optional[AuthProfileStore] = None
_store_lock = threading.Lock()


def get_profile_store() -> AuthProfileStore:
    """Return the module-level singleton (lazy-construct on first call)."""
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            _store_singleton = AuthProfileStore()
        return _store_singleton


def set_profile_store(store: AuthProfileStore) -> None:
    """Replace the singleton; orchestrator init / tests use this."""
    global _store_singleton
    with _store_lock:
        _store_singleton = store


def reset_profile_store_for_testing() -> None:
    """Drop the singleton; next :func:`get_profile_store` returns fresh."""
    global _store_singleton
    with _store_lock:
        _store_singleton = None


__all__ = [
    "AuthProfile",
    "AuthProfileState",
    "AuthProfileStore",
    "DEFAULT_COOLDOWN_SECONDS",
    "DEFAULT_MAX_TRANSIENT_RETRIES",
    "MAX_FAILURE_COUNT",
    "get_profile_store",
    "reset_profile_store_for_testing",
    "set_profile_store",
]
