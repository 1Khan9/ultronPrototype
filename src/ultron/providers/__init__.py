"""Provider auth-profile + rotation + failover-reason taxonomy (T6).

T6 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). The three
interlocking primitives that let ultron's STT / TTS / web-search /
reader / future LLM-cascade chains rotate between providers with
cooldown memory and a typed failover-reason taxonomy:

* :mod:`ultron.providers.failover_policy` — :class:`FailoverReason`
  enum + per-reason probe / transient-slot policy table.
* :mod:`ultron.providers.auth_profiles` — :class:`AuthProfile`
  state (credential + failure counter + cooldown timestamp), the
  :class:`AuthProfileStore` registry, and the failure-recording
  helpers.
* :mod:`ultron.providers.rotation` — round-robin + cooldown-aware
  key rotation; the ``execute_with_rotation`` driver mirroring
  OpenClaw's ``executeWithApiKeyRotation``.

Generalises beyond LLM API keys to ANY chain where one provider
might fail transiently AND a fallback exists. Each provider chain
in ultron consumes the same primitives:

* STT (Parakeet primary -> Moonshine gaming).
* TTS (Kokoro CUDA -> Kokoro CPU -> Piper emergency).
* Web search (SearxNG -> Brave -> DuckDuckGo).
* Reader (Trafilatura -> Jina).
* Future remote-LLM cascade.
"""

from __future__ import annotations

from .auth_profiles import (
    AuthProfile,
    AuthProfileState,
    AuthProfileStore,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_MAX_TRANSIENT_RETRIES,
    MAX_FAILURE_COUNT,
    get_profile_store,
    reset_profile_store_for_testing,
    set_profile_store,
)
from .failover_policy import (
    FAILOVER_PROBE_REASONS,
    FAILOVER_REASON_DESCRIPTIONS,
    FAILOVER_TRANSIENT_SLOT_REASONS,
    FailoverReason,
    should_allow_cooldown_probe,
    should_use_transient_cooldown_slot,
)
from .rotation import (
    DEFAULT_TRANSIENT_DELAY_SECONDS,
    RotationOutcome,
    RotationResult,
    classify_provider_error,
    execute_with_rotation,
)

__all__ = [
    "AuthProfile",
    "AuthProfileState",
    "AuthProfileStore",
    "DEFAULT_COOLDOWN_SECONDS",
    "DEFAULT_MAX_TRANSIENT_RETRIES",
    "DEFAULT_TRANSIENT_DELAY_SECONDS",
    "FAILOVER_PROBE_REASONS",
    "FAILOVER_REASON_DESCRIPTIONS",
    "FAILOVER_TRANSIENT_SLOT_REASONS",
    "FailoverReason",
    "MAX_FAILURE_COUNT",
    "RotationOutcome",
    "RotationResult",
    "classify_provider_error",
    "execute_with_rotation",
    "get_profile_store",
    "reset_profile_store_for_testing",
    "set_profile_store",
    "should_allow_cooldown_probe",
    "should_use_transient_cooldown_slot",
]
