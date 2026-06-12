"""Privacy-by-construction observability primitives (T15).

T15 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Public surface for kenning's internal aggregate-only metrics (which
intents fire, which skills match, which providers win the cascade)
in a shape that's privacy-by-construction: every identifier is
hashed at the type boundary, raw paths / user text / response
bodies never leave the local boundary even if a future federation
endpoint is added.

The package ships :mod:`kenning.observability.private_telemetry`
with :class:`HashedRootId` / :class:`HashedSkillId` NewType
wrappers, the hashing primitives, the local-only :class:`PrivateMetricsStore`,
and the staleness-detection helper.

NO federation endpoint is wired in this batch. The architecture
is in place for a future opt-in (``KENNING_TELEMETRY=opt-in``); the
default is fail-private (``KENNING_DISABLE_TELEMETRY=1`` semantics
baked in via the explicit-enable design).
"""

from kenning.observability.private_telemetry import (
    DEFAULT_STALE_DAYS,
    HashedEvent,
    HashedRootId,
    HashedSkillId,
    PrivateMetricsStore,
    RawPathLeakError,
    RootRecord,
    SkillRecord,
    canonical_label_root,
    hash_root,
    hash_skill_slug,
    is_telemetry_enabled,
)

__all__ = [
    "DEFAULT_STALE_DAYS",
    "HashedEvent",
    "HashedRootId",
    "HashedSkillId",
    "PrivateMetricsStore",
    "RawPathLeakError",
    "RootRecord",
    "SkillRecord",
    "canonical_label_root",
    "hash_root",
    "hash_skill_slug",
    "is_telemetry_enabled",
]
