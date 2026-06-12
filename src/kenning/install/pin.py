"""Pin / unpin primitives extending the T10 lockfile (T11).

T11 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Formalises the user's existing voice-baseline lock contract into a
data-backed primitive any subsystem can consume.

Pinned entries:

* Cannot be force-overwritten by ``install --force`` / ``update``.
* Carry a free-form ``reason`` field that surfaces in voice
  narration + dashboards (so a user six months later remembers WHY
  they pinned).
* Live in the same :class:`Lockfile` carried by T10 so callers don't
  need to track two sources of truth.

The ``pin`` operation is idempotent on identical reason (no-op when
already pinned with the same reason; otherwise updates the reason).
The ``unpin`` operation is strict (rejects already-unpinned entries
so callers get an explicit error rather than silent no-op).

A small KENNING_DEFAULT_PINS list mirrors the voice-baseline lock:
attempting to install or update entries in that list with no
explicit pin entry materialises the pin on demand so the catalog's
ship-default behaviour matches the binding voice-baseline contract.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from kenning.install.lockfile import (
    Lockfile,
    LockfileEntry,
    read_lockfile,
    write_lockfile,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PinResult:
    """Outcome of one :func:`pin` / :func:`unpin` call.

    Fields:
        slug: the slug acted on.
        was_pinned_before: True iff the entry was already pinned at
            call time.
        is_pinned_after: True iff the entry is pinned after the call.
        reason_before: the pin reason at call time (None when not
            previously pinned).
        reason_after: the pin reason after the call (None when
            unpinned).
        idempotent_noop: True when the call landed on an already-
            matching state (pin with same reason, or unpin of an
            unpinned entry that was tolerated). When False, the
            lockfile was rewritten.
    """

    slug: str
    was_pinned_before: bool
    is_pinned_after: bool
    reason_before: Optional[str]
    reason_after: Optional[str]
    idempotent_noop: bool


#: Kenning's default-pinned resources. Each entry's reason is the
#: contract sentence shown in ``list_pinned`` output + voice
#: narration. Materialised on demand by :func:`materialise_default_pins`.
KENNING_DEFAULT_PINS: Mapping[str, str] = {
    "voicepack:kenning": (
        "Voice character anchor (SOUL.md/RVC/Piper/Kokoro voicepack);"
        " do not auto-update without an explicit voice unpin."
    ),
    "voicepack:kokoro_finetune": (
        "Kokoro fine-tune weights anchor; do not auto-update without"
        " explicit voice unpin (would break Kenning mechanical voice character)."
    ),
    "llm:qwen3.5-4b": (
        "Voice-path latency anchor (TTFT contract);"
        " preset swap requires explicit voice command."
    ),
    "persona:identity": (
        "IDENTITY.md capability anchor; manual edits are intentional"
        " and should survive auto-updates."
    ),
    "validator:k_category": (
        "Safety validator K-category self-protection rules;"
        " never auto-update without explicit operator step."
    ),
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ensure_entry(lockfile: Lockfile, slug: str) -> LockfileEntry:
    """Return ``lockfile.skills[slug]`` or materialise a default entry."""
    existing = lockfile.entry(slug)
    if existing is not None:
        return existing
    return LockfileEntry(installed_at=_now_ms())


def is_pinned(workdir: Path, slug: str) -> tuple[bool, Optional[str]]:
    """Return ``(pinned, reason)`` for ``slug`` in the workdir lockfile.

    Returns ``(False, None)`` when the slug isn't tracked yet (so
    callers can branch on the boolean without needing existence
    checks).
    """
    lockfile = read_lockfile(workdir)
    entry = lockfile.entry(slug)
    if entry is None:
        return (False, None)
    return (entry.pinned, entry.pin_reason)


def list_pinned(workdir: Path) -> dict[str, str]:
    """Return ``{slug: reason}`` for every pinned entry in the workdir lockfile.

    Reason is the empty string when the entry was pinned without an
    explicit reason (the catalog allows that even though most
    callers should supply one).
    """
    lockfile = read_lockfile(workdir)
    return {
        slug: entry.pin_reason or ""
        for slug, entry in lockfile.skills.items()
        if entry.pinned
    }


def pin(
    workdir: Path,
    slug: str,
    *,
    reason: Optional[str] = None,
    create_if_missing: bool = True,
) -> PinResult:
    """Pin ``slug`` in the workdir lockfile.

    Behaviour:

    * If the entry is already pinned with the same reason -> idempotent
      no-op (returns the matching :class:`PinResult` with
      ``idempotent_noop=True``).
    * If the entry is pinned with a DIFFERENT reason -> updates the
      reason in place (returns ``idempotent_noop=False``).
    * If the entry exists but is unpinned -> sets ``pinned=True`` +
      ``pin_reason=reason``.
    * If the entry doesn't exist:

      - When ``create_if_missing=True`` (default) -> materialises a
        new entry with ``installed_at=now_ms()`` + pin metadata.
      - When ``create_if_missing=False`` -> raises ``KeyError``.

    Empty / whitespace-only ``reason`` is treated as no-reason (None)
    so callers can pass user input through ``.strip()`` without
    branching.
    """
    cleaned_reason: Optional[str] = None
    if reason is not None:
        stripped = reason.strip()
        cleaned_reason = stripped or None

    lockfile = read_lockfile(workdir)
    existing = lockfile.entry(slug)

    if existing is None and not create_if_missing:
        raise KeyError(
            f"Cannot pin {slug!r}: entry not present in lockfile and "
            "create_if_missing=False"
        )

    base_entry = _ensure_entry(lockfile, slug)
    was_pinned = base_entry.pinned
    reason_before = base_entry.pin_reason

    if was_pinned and reason_before == cleaned_reason:
        # Idempotent: do not rewrite the file.
        return PinResult(
            slug=slug,
            was_pinned_before=True,
            is_pinned_after=True,
            reason_before=reason_before,
            reason_after=reason_before,
            idempotent_noop=True,
        )

    new_entry = LockfileEntry(
        version=base_entry.version,
        installed_at=base_entry.installed_at or _now_ms(),
        pinned=True,
        pin_reason=cleaned_reason,
    )
    new_lockfile = lockfile.with_entry(slug, new_entry)
    write_lockfile(workdir, new_lockfile)
    return PinResult(
        slug=slug,
        was_pinned_before=was_pinned,
        is_pinned_after=True,
        reason_before=reason_before,
        reason_after=cleaned_reason,
        idempotent_noop=False,
    )


def unpin(workdir: Path, slug: str, *, tolerate_unpinned: bool = False) -> PinResult:
    """Unpin ``slug`` in the workdir lockfile.

    Default behaviour (matches the upstream strict contract): raises
    ``KeyError`` when the slug isn't tracked, or :class:`UnpinNotPinnedError`
    when the slug is tracked but already unpinned. Callers that want
    a softer behaviour pass ``tolerate_unpinned=True``, which makes
    the already-unpinned case an idempotent no-op.
    """
    lockfile = read_lockfile(workdir)
    existing = lockfile.entry(slug)
    if existing is None:
        raise KeyError(f"Cannot unpin {slug!r}: entry not present in lockfile")
    if not existing.pinned:
        if not tolerate_unpinned:
            raise UnpinNotPinnedError(slug)
        return PinResult(
            slug=slug,
            was_pinned_before=False,
            is_pinned_after=False,
            reason_before=None,
            reason_after=None,
            idempotent_noop=True,
        )

    reason_before = existing.pin_reason
    new_entry = LockfileEntry(
        version=existing.version,
        installed_at=existing.installed_at,
        pinned=False,
        pin_reason=None,
    )
    new_lockfile = lockfile.with_entry(slug, new_entry)
    write_lockfile(workdir, new_lockfile)
    return PinResult(
        slug=slug,
        was_pinned_before=True,
        is_pinned_after=False,
        reason_before=reason_before,
        reason_after=None,
        idempotent_noop=False,
    )


def is_default_pin(slug: str) -> bool:
    """Return True iff ``slug`` is in :data:`KENNING_DEFAULT_PINS`."""
    return slug in KENNING_DEFAULT_PINS


def materialise_default_pins(workdir: Path) -> tuple[PinResult, ...]:
    """Ensure every :data:`KENNING_DEFAULT_PINS` entry is pinned.

    Walks the default-pin list and calls :func:`pin` for each slug
    not already pinned in the workdir lockfile. Returns one
    :class:`PinResult` per slug acted on. Idempotent on subsequent
    invocations (every result will be ``idempotent_noop=True``).
    """
    results: list[PinResult] = []
    for slug, reason in KENNING_DEFAULT_PINS.items():
        results.append(pin(workdir, slug, reason=reason))
    return tuple(results)


def refuses_update(workdir: Path, slug: str) -> tuple[bool, Optional[str]]:
    """Return ``(should_refuse, reason)`` for an update on ``slug``.

    ``should_refuse=True`` when the slug is pinned. Callers (the
    install / update CLI, the skill registry's hot-reload loop)
    branch on this to surface a clear refusal message rather than
    silently overwriting a pinned skill.
    """
    pinned, reason = is_pinned(workdir, slug)
    return (pinned, reason)


class UnpinNotPinnedError(RuntimeError):
    """Raised when :func:`unpin` is called against a non-pinned entry.

    Carries the slug as a public ``.slug`` attribute so callers can
    render a clean error message without re-parsing the exception
    text.
    """

    def __init__(self, slug: str) -> None:
        super().__init__(f"Cannot unpin {slug!r}: entry is not currently pinned")
        self.slug = slug


__all__ = [
    "PinResult",
    "UnpinNotPinnedError",
    "KENNING_DEFAULT_PINS",
    "is_pinned",
    "list_pinned",
    "pin",
    "unpin",
    "is_default_pin",
    "materialise_default_pins",
    "refuses_update",
]
