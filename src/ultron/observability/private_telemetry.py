"""Privacy-by-construction aggregate-only telemetry (T15).

T15 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
The upstream marketplace's privacy-preserving telemetry shape
generalised into ultron's internal per-session metrics. The
contract: every identifier that could leak into outbound or
log-readable surfaces is **hashed at the type boundary**; raw
paths / user text / response bodies never become :class:`HashedRootId`
/ :class:`HashedSkillId` values.

Five architectural pieces:

1. **Hashed-identifier NewTypes** (:class:`HashedRootId`,
   :class:`HashedSkillId`). Distinct ``str`` subclasses so a
   ``hash_root(raw_path)`` -> :class:`HashedRootId` assignment is
   the ONLY way the identifier reaches the metrics store; an
   accidental ``raw_path`` -> store path raises
   :class:`RawPathLeakError` at the validator boundary.

2. **Hash primitives** (:func:`hash_root`, :func:`hash_skill_slug`).
   Stable SHA-256 with a deployment-specific salt so the same
   root path on a different ultron install hashes differently
   (prevents cross-install correlation if a future federation
   endpoint ships). Salt lives in
   ``data/observability/telemetry_salt.txt`` -- generated on first
   call.

3. **Tilde-normalised labels** (:func:`canonical_label_root`).
   For dashboards: when audit reviewers want a recognisable
   label ("~/STC/ultronPrototype" instead of a raw hex hash),
   the label is the last-two-segments-with-tilde of the path.
   Labels are STILL safe to expose -- they don't reveal the
   absolute path.

4. **Local-only :class:`PrivateMetricsStore`**. Append-only JSONL
   at ``data/observability/private_metrics.jsonl``. No federation
   driver. :meth:`record_event` enforces the type boundary;
   raw-string identifiers raise :class:`RawPathLeakError`.

5. **Staleness detection**. The upstream "roots stale after 120
   days of no sync" pattern -- :func:`stale_root_ids(store,
   now=...)` returns the :class:`HashedRootId` set that should
   stop counting toward Current install metrics.

The architecture mirrors the upstream by-design privacy contract:
fail-private (anything that isn't hashed + typed can't reach the
store). Tests verify the type boundary via mock-fetch round
trips.

Module-level :func:`is_telemetry_enabled` consults
``ULTRON_TELEMETRY`` env var; default is fail-private (telemetry
disabled). Operators opt in by setting ``ULTRON_TELEMETRY=opt-in``
explicitly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, NewType, Optional

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NewType identifiers


HashedRootId = NewType("HashedRootId", str)
"""SHA-256 hex of a salted root path; safe to log / persist / share."""

HashedSkillId = NewType("HashedSkillId", str)
"""SHA-256 hex of a skill slug; safe to log / persist / share."""


# ---------------------------------------------------------------------------
# Constants


#: Roots stale after this many days of no recorded events.
DEFAULT_STALE_DAYS: int = 120

#: Default subdir under PROJECT_ROOT where telemetry artefacts live.
DEFAULT_TELEMETRY_SUBDIR: str = "data/observability"

#: Salt filename. Generated on first call; persisted across runs.
TELEMETRY_SALT_FILENAME: str = "telemetry_salt.txt"

#: JSONL filename for the event store.
TELEMETRY_EVENTS_FILENAME: str = "private_metrics.jsonl"

#: Env var operators set to opt in to telemetry collection. Default
#: behaviour (env unset or any other value) is telemetry-disabled.
TELEMETRY_ENABLE_ENV: str = "ULTRON_TELEMETRY"

#: Explicit opt-in token. Anything else (incl. the legacy
#: ``ULTRON_DISABLE_TELEMETRY`` style) leaves telemetry off.
TELEMETRY_ENABLE_OPT_IN_TOKEN: str = "opt-in"


# ---------------------------------------------------------------------------
# Exceptions


class RawPathLeakError(RuntimeError):
    """Raised when a raw string is passed where a HashedRootId/SkillId is required.

    The carrier of the type-boundary invariant. Tests verify the
    invariant by exercising the negative path: a raw path /
    user-text string passed to :meth:`PrivateMetricsStore.record_event`
    raises here BEFORE the value is written.
    """

    def __init__(self, field_name: str, value: str) -> None:
        super().__init__(
            f"raw value supplied for hashed field {field_name!r}: "
            f"len={len(value)} chars. Hash via "
            "ultron.observability.hash_root/hash_skill_slug first."
        )
        self.field_name = field_name


# ---------------------------------------------------------------------------
# Salt management


def _telemetry_dir(project_root: Path) -> Path:
    return Path(project_root) / DEFAULT_TELEMETRY_SUBDIR


def _salt_path(project_root: Path) -> Path:
    return _telemetry_dir(project_root) / TELEMETRY_SALT_FILENAME


def _events_path(project_root: Path) -> Path:
    return _telemetry_dir(project_root) / TELEMETRY_EVENTS_FILENAME


def _read_or_create_salt(project_root: Path) -> str:
    """Return the per-install telemetry salt.

    Generated on first call (32-byte URL-safe random hex) and
    persisted to ``data/observability/telemetry_salt.txt``.
    Subsequent calls read the cached value. Salt prevents cross-
    install correlation if telemetry ever ships off-machine: the
    same root path on two different ultron installs hashes
    differently.
    """
    path = _salt_path(project_root)
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError as exc:
            LOGGER.warning("Cannot read telemetry salt at %s: %s", path, exc)
    salt = uuid.uuid4().hex + uuid.uuid4().hex
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(salt + "\n", encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("Cannot persist telemetry salt to %s: %s", path, exc)
    return salt


# ---------------------------------------------------------------------------
# Hash primitives


def _canonicalise_path(value: str) -> str:
    """Return a canonical lowercase forward-slash form of ``value``.

    Used as the input to :func:`hash_root`. Drops drive case + slash
    direction so ``C:\\STC\\ultronPrototype`` and
    ``c:/stc/ultronprototype`` produce the same hash.
    """
    cleaned = value.replace("\\", "/").strip().rstrip("/")
    return cleaned.casefold()


def hash_root(path: str | Path, *, project_root: Path) -> HashedRootId:
    """Return the salted SHA-256 of ``path``.

    The salt is read (or generated) from
    ``<project_root>/data/observability/telemetry_salt.txt`` so the
    same root path on a different ultron install hashes
    differently. Empty / whitespace-only paths return the all-zeros
    hash (never raises) so callers don't need a separate empty
    branch.
    """
    canonical = _canonicalise_path(str(path))
    if not canonical:
        return HashedRootId("0" * 64)
    salt = _read_or_create_salt(project_root)
    digest = hashlib.sha256((salt + ":" + canonical).encode("utf-8")).hexdigest()
    return HashedRootId(digest)


def hash_skill_slug(slug: str, *, project_root: Path) -> HashedSkillId:
    """Return the salted SHA-256 of ``slug``.

    Same shape as :func:`hash_root` -- prevents skill-slug
    correlation across installs.
    """
    canonical = (slug or "").strip().casefold()
    if not canonical:
        return HashedSkillId("0" * 64)
    salt = _read_or_create_salt(project_root)
    digest = hashlib.sha256((salt + ":skill:" + canonical).encode("utf-8")).hexdigest()
    return HashedSkillId(digest)


def canonical_label_root(path: str | Path) -> str:
    """Return the tilde-homed last-two-segments label.

    Example: ``C:\\STC\\ultronPrototype`` -> ``~/STC/ultronPrototype``
    (the home prefix is purely cosmetic for dashboards; ``~`` is
    used regardless of whether the path is actually under HOME so
    audit reviewers see a recognisable shape without the absolute
    path).

    Empty input returns the empty string.
    """
    cleaned = str(path).replace("\\", "/").strip().rstrip("/")
    if not cleaned:
        return ""
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) < 2:
        return f"~/{parts[-1]}" if parts else ""
    return f"~/{parts[-2]}/{parts[-1]}"


# ---------------------------------------------------------------------------
# Records + events


@dataclass(frozen=True)
class RootRecord:
    """One observed root (a project / sandbox / install directory).

    Fields:
        root_id: :class:`HashedRootId` value.
        label: tilde-normalised dashboard label.
        first_seen_iso: ISO-8601 of the first observation.
        last_seen_iso: ISO-8601 of the most recent observation.
        skill_count: number of distinct hashed skills observed at
            this root.
    """

    root_id: HashedRootId
    label: str = ""
    first_seen_iso: str = ""
    last_seen_iso: str = ""
    skill_count: int = 0


@dataclass(frozen=True)
class SkillRecord:
    """One observed skill match.

    Fields:
        root_id: which root the skill matched at.
        skill_id: :class:`HashedSkillId` value.
        last_version: optional version string (empty when not
            tracked).
        last_seen_iso: ISO-8601 of the most recent observation.
        match_count: total observed matches.
    """

    root_id: HashedRootId
    skill_id: HashedSkillId
    last_version: str = ""
    last_seen_iso: str = ""
    match_count: int = 0


@dataclass(frozen=True)
class HashedEvent:
    """One private-telemetry event.

    Fields:
        kind: free-form event-class string ("intent_fire" /
            "skill_match" / "provider_win" / "memory_retrieve" /
            "tts_synth" / etc.). NEVER contains user-readable
            content.
        root_id: which root the event happened at.
        skill_id: optional :class:`HashedSkillId`.
        attributes: free-form bag of int / float / bool / hashed
            string values; the validator rejects raw-string fields
            longer than 12 chars unless the field name ends with
            ``_id`` or is a known-safe metadata key.
        recorded_iso: ISO-8601 timestamp.
    """

    kind: str
    root_id: HashedRootId
    skill_id: Optional[HashedSkillId] = None
    attributes: Mapping[str, object] = field(default_factory=dict)
    recorded_iso: str = ""


# Known-safe attribute keys whose values may be free-form strings
# without triggering the raw-path leak check. Extend cautiously.
SAFE_ATTRIBUTE_KEYS: frozenset[str] = frozenset({
    "outcome",   # short enum value
    "tier",      # severity tier name
    "verdict",   # short enum value
    "channel",   # short enum value
    "kind",      # already explicit
    "status",    # short enum value
    "category",  # short enum value
    "result",    # short enum value
})


def _is_safe_attribute(key: str, value: object) -> bool:
    """Return False if ``(key, value)`` looks like a raw-string leak."""
    if not isinstance(value, str):
        return True
    if key in SAFE_ATTRIBUTE_KEYS:
        return True
    if key.endswith("_id"):
        return True
    if key.endswith("_hash"):
        return True
    if len(value) <= 12:
        return True
    return False


# ---------------------------------------------------------------------------
# Telemetry enable check


def is_telemetry_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return True iff the operator has explicitly opted in.

    Reads :data:`TELEMETRY_ENABLE_ENV` (``ULTRON_TELEMETRY``).
    Default behaviour (env unset, set to empty, or set to anything
    other than :data:`TELEMETRY_ENABLE_OPT_IN_TOKEN`) is
    telemetry-disabled.

    ``env`` defaults to :data:`os.environ`; callers pass a custom
    mapping for hermetic tests.
    """
    env_map = env if env is not None else os.environ
    return env_map.get(TELEMETRY_ENABLE_ENV, "").strip().casefold() == TELEMETRY_ENABLE_OPT_IN_TOKEN


# ---------------------------------------------------------------------------
# Store


class PrivateMetricsStore:
    """Local-only append-only JSONL metrics store.

    Constructor:
        project_root: PROJECT_ROOT path; controls salt + log
            locations.
        events_path: optional explicit override for the events
            file (defaults to
            ``<project_root>/data/observability/private_metrics.jsonl``).
        now_fn: clock-injectable.
        enforce_enable_check: when True (default), :meth:`record_event`
            no-ops unless :func:`is_telemetry_enabled` returns True
            for the current environment. Tests can pass False to
            exercise the type-boundary checks without setting the
            env var.

    Methods:
        record_event(event) — persist one HashedEvent. Raises
            :class:`RawPathLeakError` if the event carries
            non-hashed identifiers or an unsafe attribute string.
        read_events() — iterate over persisted events.
        root_records() — derive RootRecord per observed root_id.
        skill_records() — derive SkillRecord per (root_id, skill_id).
    """

    def __init__(
        self,
        *,
        project_root: Path,
        events_path: Optional[Path] = None,
        now_fn: Optional["object"] = None,
        enforce_enable_check: bool = True,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._project_root = Path(project_root)
        self._events_path = (
            Path(events_path)
            if events_path is not None
            else _events_path(self._project_root)
        )
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._enforce_enable_check = enforce_enable_check
        self._env = env

    def _now(self) -> datetime:
        result = self._now_fn()
        if isinstance(result, datetime):
            return result if result.tzinfo else result.replace(tzinfo=timezone.utc)
        return datetime.fromtimestamp(float(result), tz=timezone.utc)

    @property
    def events_path(self) -> Path:
        return self._events_path

    def record_event(self, event: HashedEvent) -> bool:
        """Persist ``event`` if telemetry is enabled. Returns True iff written.

        Type-boundary check:

        * ``event.root_id`` must be :class:`HashedRootId` (a 64-char
          hex string). Anything that doesn't look hex raises
          :class:`RawPathLeakError`.
        * ``event.skill_id`` (when set) must be
          :class:`HashedSkillId`.
        * Each attribute value passes :func:`_is_safe_attribute`
          (only known-safe keys / id-suffixed keys / hash-suffixed
          keys / short strings allowed).

        ``enforce_enable_check=True`` (default) causes the call to
        no-op when :func:`is_telemetry_enabled` returns False.
        Returns False in that case so callers can branch.
        """
        if self._enforce_enable_check and not is_telemetry_enabled(self._env):
            return False
        self._validate_event(event)

        with self._lock:
            try:
                self._events_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                LOGGER.warning("Cannot create telemetry dir: %s", exc)
                return False
            recorded_iso = event.recorded_iso or self._now().isoformat()
            row: dict[str, object] = {
                "kind": event.kind,
                "root_id": str(event.root_id),
                "recorded_at": recorded_iso,
            }
            if event.skill_id is not None:
                row["skill_id"] = str(event.skill_id)
            if event.attributes:
                row["attributes"] = dict(event.attributes)
            try:
                with self._events_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            except OSError as exc:
                LOGGER.warning(
                    "Cannot append private-telemetry event to %s: %s",
                    self._events_path,
                    exc,
                )
                return False
            return True

    def _validate_event(self, event: HashedEvent) -> None:
        """Type-boundary check: raise on any raw-path leak."""
        if not _looks_like_hashed_id(str(event.root_id)):
            raise RawPathLeakError("root_id", str(event.root_id))
        if event.skill_id is not None and not _looks_like_hashed_id(
            str(event.skill_id)
        ):
            raise RawPathLeakError("skill_id", str(event.skill_id))
        for key, value in event.attributes.items():
            if not _is_safe_attribute(key, value):
                raise RawPathLeakError(f"attributes[{key!r}]", str(value))

    def read_events(self) -> Iterable[HashedEvent]:
        """Yield :class:`HashedEvent` rows reconstructed from the JSONL.

        Malformed rows are silently skipped (logged at debug).
        """
        if not self._events_path.is_file():
            return
        try:
            with self._events_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        record = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    yield HashedEvent(
                        kind=str(record.get("kind") or ""),
                        root_id=HashedRootId(str(record.get("root_id") or "")),
                        skill_id=(
                            HashedSkillId(str(record["skill_id"]))
                            if "skill_id" in record
                            else None
                        ),
                        attributes=(
                            dict(record.get("attributes") or {})
                        ),
                        recorded_iso=str(record.get("recorded_at") or ""),
                    )
        except OSError as exc:
            LOGGER.warning("Cannot read telemetry events at %s: %s", self._events_path, exc)
            return

    def root_records(self) -> tuple[RootRecord, ...]:
        """Aggregate observed events into per-root summaries.

        ``label`` is NOT recovered from the store (we never store
        raw labels in the event row; callers can attach them via
        the future federation surface).
        """
        per_root: dict[str, dict] = {}
        for event in self.read_events():
            key = str(event.root_id)
            entry = per_root.setdefault(
                key,
                {
                    "root_id": event.root_id,
                    "first_seen_iso": event.recorded_iso,
                    "last_seen_iso": event.recorded_iso,
                    "skills": set(),
                },
            )
            if event.recorded_iso < entry["first_seen_iso"] or not entry["first_seen_iso"]:
                entry["first_seen_iso"] = event.recorded_iso
            if event.recorded_iso > entry["last_seen_iso"]:
                entry["last_seen_iso"] = event.recorded_iso
            if event.skill_id is not None:
                entry["skills"].add(str(event.skill_id))
        out: list[RootRecord] = []
        for entry in per_root.values():
            out.append(RootRecord(
                root_id=entry["root_id"],
                first_seen_iso=entry["first_seen_iso"],
                last_seen_iso=entry["last_seen_iso"],
                skill_count=len(entry["skills"]),
            ))
        out.sort(key=lambda r: r.root_id)
        return tuple(out)

    def skill_records(self) -> tuple[SkillRecord, ...]:
        """Aggregate per-(root, skill) pairs."""
        per_pair: dict[tuple[str, str], dict] = {}
        for event in self.read_events():
            if event.skill_id is None:
                continue
            key = (str(event.root_id), str(event.skill_id))
            entry = per_pair.setdefault(
                key,
                {
                    "root_id": event.root_id,
                    "skill_id": event.skill_id,
                    "last_seen_iso": event.recorded_iso,
                    "match_count": 0,
                    "last_version": str(
                        (event.attributes or {}).get("version", "")
                    ),
                },
            )
            entry["match_count"] += 1
            if event.recorded_iso > entry["last_seen_iso"]:
                entry["last_seen_iso"] = event.recorded_iso
                version = (event.attributes or {}).get("version")
                if isinstance(version, str) and version:
                    entry["last_version"] = version
        out: list[SkillRecord] = []
        for entry in per_pair.values():
            out.append(SkillRecord(
                root_id=entry["root_id"],
                skill_id=entry["skill_id"],
                last_version=entry["last_version"],
                last_seen_iso=entry["last_seen_iso"],
                match_count=entry["match_count"],
            ))
        out.sort(key=lambda s: (s.root_id, s.skill_id))
        return tuple(out)

    def delete_all(self) -> None:
        """Delete the events file (caller-side "delete my telemetry" surface).

        Audit-log integration is the caller's responsibility -- the
        catalog's discipline is "deletion logs the deletion event
        itself but removes every other row". The minimal primitive
        here is the deletion; audit-log integration layered on top.
        """
        with self._lock:
            try:
                if self._events_path.is_file():
                    self._events_path.unlink()
            except OSError as exc:
                LOGGER.warning(
                    "Cannot delete telemetry events at %s: %s",
                    self._events_path,
                    exc,
                )


# ---------------------------------------------------------------------------
# Staleness


def stale_root_ids(
    store: PrivateMetricsStore,
    *,
    now: Optional[datetime] = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> tuple[HashedRootId, ...]:
    """Return the :class:`HashedRootId` set considered stale.

    A root is stale when its most recent observation is older than
    ``stale_days`` days. Stale roots stop counting toward
    "currently installed" aggregates per the upstream pattern.
    """
    reference = now or datetime.now(timezone.utc)
    threshold = reference - timedelta(days=max(0, stale_days))
    out: list[HashedRootId] = []
    for record in store.root_records():
        if not record.last_seen_iso:
            continue
        try:
            last = datetime.fromisoformat(record.last_seen_iso)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if last < threshold:
            out.append(record.root_id)
    return tuple(out)


# ---------------------------------------------------------------------------
# Helpers


def _looks_like_hashed_id(value: str) -> bool:
    """Return True iff ``value`` is a 64-char lowercase hex string.

    The cheapest possible "this came from :func:`hash_root` /
    :func:`hash_skill_slug`" check. Treats absolute paths, slashes,
    user-text, and any non-hex character as instant rejection.
    """
    if not isinstance(value, str):
        return False
    if len(value) != 64:
        return False
    for char in value:
        if char not in "0123456789abcdef":
            return False
    return True


__all__ = [
    "DEFAULT_STALE_DAYS",
    "HashedEvent",
    "HashedRootId",
    "HashedSkillId",
    "PrivateMetricsStore",
    "RawPathLeakError",
    "RootRecord",
    "SAFE_ATTRIBUTE_KEYS",
    "SkillRecord",
    "TELEMETRY_ENABLE_ENV",
    "TELEMETRY_ENABLE_OPT_IN_TOKEN",
    "TELEMETRY_EVENTS_FILENAME",
    "TELEMETRY_SALT_FILENAME",
    "canonical_label_root",
    "hash_root",
    "hash_skill_slug",
    "is_telemetry_enabled",
    "stale_root_ids",
]
