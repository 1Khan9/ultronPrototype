"""Stable-identity infrastructure: alias graph, slug validation, reservation.

T6 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Generalises the marketplace's slug-rename / merge / transfer +
30-day reservation pattern into a primitive any ultron subsystem
exposing a user-facing namespace can reuse (skill registry, voice
intent labels, sandbox project names, gaming-mode profile names,
persona overlays, voicepack ids, memory backend selectors).

Public surface lives in :mod:`ultron.identity.alias_graph`:

* :class:`AliasGraphEntry` — one alias graph node (canonical slug
  with redirects + reservation window).
* :class:`AliasGraph` — the in-memory + persistent alias graph;
  resolve / rename / merge / transfer / soft_delete / hard_delete
  operations.
* :func:`validate_slug` / :func:`normalize_slug` — slug shape rules.
* :data:`RESERVED_SLUGS` — names that can never be claimed.
"""

from ultron.identity.alias_graph import (
    DEFAULT_RESERVATION_DAYS,
    RESERVED_SLUGS,
    SLUG_PATTERN,
    AliasGraph,
    AliasGraphEntry,
    AliasOperation,
    AliasResolveError,
    InvalidSlugError,
    SlugReservedError,
    normalize_slug,
    validate_slug,
)

__all__ = [
    "AliasGraph",
    "AliasGraphEntry",
    "AliasOperation",
    "AliasResolveError",
    "DEFAULT_RESERVATION_DAYS",
    "InvalidSlugError",
    "RESERVED_SLUGS",
    "SLUG_PATTERN",
    "SlugReservedError",
    "normalize_slug",
    "validate_slug",
]
