"""Skills marketplace: manifest + source discrimination + install pipeline (T9).

T9 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Lets a
user point ultron at a community skills pack via one of five source
shapes:

* :class:`SourceKind.PATH` — local directory (development).
* :class:`SourceKind.GITHUB` — ``owner/repo[#ref]`` shorthand
  (community packs).
* :class:`SourceKind.GIT` — generic git URL with optional ref / subdir
  (private repos, alternative hosts).
* :class:`SourceKind.GIT_SUBDIR` — explicit subdir inside a larger
  mono-repo.
* :class:`SourceKind.URL` — generic HTTP archive (tarball / zip).

Each marketplace manifest is JSON (with JSON5-lite tolerance: trailing
commas + ``//`` line comments stripped before :func:`json.loads`),
capped at 256 KB, and validated against a frozen
:class:`MarketplaceManifest` shape. The install driver pulls the
manifest, walks every entry, dispatches to the per-source resolver,
and runs the resolved content through the T5 static scanner before
the skill's body becomes loadable.

This module ships the data shapes + the source-kind resolution +
the manifest loader + the GitHub-shorthand detector. The actual
network IO is INJECTED via callables so tests stay hermetic and so
caller-side credentials / SSRF-guard policies layer cleanly on top.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

LOGGER = logging.getLogger(__name__)


#: Max bytes accepted for a marketplace manifest.
DEFAULT_MAX_MANIFEST_BYTES: int = 256 * 1024

#: Default git hosts trusted for shorthand resolution. Operators
#: extend per-deployment.
DEFAULT_TRUSTED_GIT_HOSTS: frozenset[str] = frozenset({
    "github.com",
    "gitlab.com",
    "codeberg.org",
    "bitbucket.org",
})


class SourceKind(str, Enum):
    """Discriminator for the five marketplace source variants."""

    PATH = "path"
    GITHUB = "github"
    GIT = "git"
    GIT_SUBDIR = "git_subdir"
    URL = "url"


@dataclass(frozen=True)
class MarketplaceSource:
    """One entry's install source.

    Exactly one of ``path`` / ``github`` / ``git_url`` / ``url`` is
    typically set; the discriminator is :attr:`kind`.
    """

    kind: SourceKind
    path: str = ""
    github: str = ""
    git_url: str = ""
    url: str = ""
    ref: str = ""
    subdir: str = ""
    integrity_sha256: str = ""


@dataclass(frozen=True)
class MarketplacePluginEntry:
    """One installable entry in a marketplace manifest."""

    name: str
    source: MarketplaceSource
    version: str = ""
    description: str = ""
    enabled_by_default: bool = False
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketplaceManifest:
    """Top-level marketplace manifest."""

    name: str = ""
    version: str = ""
    plugins: tuple[MarketplacePluginEntry, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------
# JSON5-lite parser


_JSON_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _strip_json_line_comments(text: str) -> str:
    """Remove ``// ...`` line comments while preserving string literals.

    Walks the text char-by-char respecting string-literal boundaries
    (and the backslash escape inside strings) so ``https://`` inside
    a URL string survives. Comment scan only fires when ``//`` appears
    outside a string.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    string_quote = ""
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == string_quote:
                in_string = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_string = True
            string_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            # Skip until newline.
            j = i + 2
            while j < n and text[j] not in ("\n", "\r"):
                j += 1
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_json_with_tolerance(text: str) -> Any:
    """Parse JSON with JSON5-lite tolerance: line comments + trailing commas.

    Strips ``// ...`` line comments OUTSIDE string literals (the
    walker respects double + single quotes and the backslash escape)
    and drops trailing commas before ``}`` / ``]``. Strict JSON
    inputs are unchanged. Raises :class:`ValueError` on parse failure.
    """
    if not text:
        return {}
    cleaned = _strip_json_line_comments(text)
    cleaned = _JSON_TRAILING_COMMA_RE.sub(r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest parse failed: {exc}") from exc


# ----------------------------------------------------------------------
# GitHub shorthand


#: Regex for ``owner/repo[#ref]`` shorthand. The character class is
#: deliberately conservative (GitHub allows alnum + - + _ + . in repo
#: names; refs allow / for branch hierarchy + the additional - _ . /
#: characters).
_GITHUB_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)(?:#(?P<ref>[A-Za-z0-9._/-]+))?$"
)


def looks_like_github_shorthand(value: str) -> bool:
    """``True`` when ``value`` matches ``owner/repo[#ref]``."""
    if not value:
        return False
    if "://" in value or value.startswith("git@"):
        return False
    return _GITHUB_SHORTHAND_RE.match(value) is not None


def parse_github_shorthand(value: str) -> Optional[tuple[str, str, str]]:
    """Parse ``owner/repo[#ref]``; returns ``(owner, repo, ref)`` or None."""
    if not value:
        return None
    match = _GITHUB_SHORTHAND_RE.match(value)
    if not match:
        return None
    return (match.group("owner"), match.group("repo"), match.group("ref") or "")


# ----------------------------------------------------------------------
# Manifest loading


def load_manifest_text(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
) -> MarketplaceManifest:
    """Parse + validate a manifest from raw text.

    Args:
        text: manifest body (JSON / JSON5-lite).
        max_bytes: cap on text length (UTF-8 byte count, approximate
            via ``len(text.encode("utf-8"))``). Larger inputs raise
            :class:`ValueError`.

    Returns:
        :class:`MarketplaceManifest`.
    """
    if not text:
        return MarketplaceManifest()
    if len(text.encode("utf-8")) > max_bytes:
        raise ValueError(f"manifest exceeds {max_bytes} bytes")
    data = parse_json_with_tolerance(text)
    if not isinstance(data, Mapping):
        raise ValueError("manifest root must be an object")
    plugins_raw = data.get("plugins") or []
    if not isinstance(plugins_raw, Sequence) or isinstance(plugins_raw, (str, bytes)):
        raise ValueError("manifest.plugins must be an array")
    entries: list[MarketplacePluginEntry] = []
    for entry_raw in plugins_raw:
        if not isinstance(entry_raw, Mapping):
            raise ValueError("manifest.plugins[*] must be an object")
        name = str(entry_raw.get("name") or "").strip()
        if not name:
            raise ValueError("manifest.plugins[*].name is required")
        source = _build_source(entry_raw)
        entries.append(MarketplacePluginEntry(
            name=name,
            source=source,
            version=str(entry_raw.get("version") or ""),
            description=str(entry_raw.get("description") or ""),
            enabled_by_default=bool(entry_raw.get("enabled_by_default", False)),
            tags=tuple(str(t) for t in (entry_raw.get("tags") or [])),
            metadata={k: v for k, v in entry_raw.items() if k not in (
                "name", "version", "description", "enabled_by_default",
                "tags", "source", "path", "github", "git", "git_subdir", "url",
            )},
        ))
    return MarketplaceManifest(
        name=str(data.get("name") or ""),
        version=str(data.get("version") or ""),
        plugins=tuple(entries),
        metadata={k: v for k, v in data.items() if k not in ("name", "version", "plugins")},
    )


def _build_source(entry_raw: Mapping[str, Any]) -> MarketplaceSource:
    """Discriminate the source variant from a manifest entry."""
    # Explicit `source` object (preferred).
    src = entry_raw.get("source")
    if isinstance(src, Mapping):
        kind_raw = str(src.get("kind") or "").lower()
        if kind_raw == SourceKind.PATH.value:
            return MarketplaceSource(
                kind=SourceKind.PATH,
                path=str(src.get("path") or ""),
            )
        if kind_raw == SourceKind.GITHUB.value:
            return MarketplaceSource(
                kind=SourceKind.GITHUB,
                github=str(src.get("repo") or src.get("github") or ""),
                ref=str(src.get("ref") or ""),
                subdir=str(src.get("path") or src.get("subdir") or ""),
                integrity_sha256=str(src.get("integrity_sha256") or ""),
            )
        if kind_raw in (SourceKind.GIT.value, SourceKind.GIT_SUBDIR.value):
            kind = SourceKind.GIT_SUBDIR if (src.get("subdir") or kind_raw == SourceKind.GIT_SUBDIR.value) else SourceKind.GIT
            return MarketplaceSource(
                kind=kind,
                git_url=str(src.get("url") or src.get("git_url") or ""),
                ref=str(src.get("ref") or ""),
                subdir=str(src.get("subdir") or src.get("path") or ""),
                integrity_sha256=str(src.get("integrity_sha256") or ""),
            )
        if kind_raw == SourceKind.URL.value:
            return MarketplaceSource(
                kind=SourceKind.URL,
                url=str(src.get("url") or ""),
                integrity_sha256=str(src.get("integrity_sha256") or ""),
            )
    # Convenience shortcuts at the entry level.
    if isinstance(entry_raw.get("path"), str):
        return MarketplaceSource(kind=SourceKind.PATH, path=str(entry_raw["path"]))
    if isinstance(entry_raw.get("github"), str):
        gh = str(entry_raw["github"])
        parsed = parse_github_shorthand(gh)
        if parsed:
            owner, repo, ref = parsed
            return MarketplaceSource(
                kind=SourceKind.GITHUB,
                github=f"{owner}/{repo}",
                ref=ref,
            )
        return MarketplaceSource(kind=SourceKind.GITHUB, github=gh)
    if isinstance(entry_raw.get("git"), str):
        return MarketplaceSource(kind=SourceKind.GIT, git_url=str(entry_raw["git"]))
    if isinstance(entry_raw.get("url"), str):
        url = str(entry_raw["url"])
        if looks_like_github_shorthand(url):
            owner, repo, ref = parse_github_shorthand(url) or ("", "", "")
            return MarketplaceSource(
                kind=SourceKind.GITHUB,
                github=f"{owner}/{repo}",
                ref=ref,
            )
        return MarketplaceSource(kind=SourceKind.URL, url=url)
    raise ValueError(f"unable to determine source for entry {entry_raw.get('name')!r}")


# ----------------------------------------------------------------------
# Resolved source URLs (for the network drivers downstream)


def resolve_github_archive_url(
    source: MarketplaceSource,
    *,
    archive_format: str = "tarball",
) -> str:
    """Build a GitHub archive URL from a GITHUB-source entry.

    Args:
        source: must be ``kind == SourceKind.GITHUB``.
        archive_format: ``"tarball"`` or ``"zipball"`` (the two
            GitHub-hosted archive endpoints).

    Returns:
        Fully-qualified ``https://api.github.com`` URL pointing at the
        repo's archive at ``ref`` (or default branch when ref is empty).
    """
    if source.kind != SourceKind.GITHUB:
        raise ValueError("resolve_github_archive_url requires GITHUB source")
    if archive_format not in ("tarball", "zipball"):
        raise ValueError("archive_format must be 'tarball' or 'zipball'")
    parsed = parse_github_shorthand(source.github)
    if not parsed:
        raise ValueError(f"github source not in owner/repo shape: {source.github!r}")
    owner, repo, _ = parsed
    ref = source.ref or ""
    suffix = f"/{ref}" if ref else ""
    return f"https://api.github.com/repos/{owner}/{repo}/{archive_format}{suffix}"


def host_for_git_url(url: str) -> str:
    """Extract host from an ``https://...`` or ``git@host:...`` URL."""
    if not url:
        return ""
    if url.startswith("git@") and ":" in url:
        # ``git@github.com:owner/repo.git``
        host_part = url[len("git@"):]
        host = host_part.split(":", 1)[0]
        return host.lower()
    if "://" in url:
        # ``https://github.com/owner/repo.git``
        after_scheme = url.split("://", 1)[1]
        host = after_scheme.split("/", 1)[0]
        # Strip optional port suffix.
        host = host.split(":", 1)[0]
        return host.lower()
    return ""


def is_trusted_git_host(
    url: str,
    *,
    trusted: Optional[frozenset[str]] = None,
) -> bool:
    """``True`` when ``url`` resolves to a host in the trusted set."""
    trusted = trusted if trusted is not None else DEFAULT_TRUSTED_GIT_HOSTS
    host = host_for_git_url(url)
    if not host:
        return False
    return host in trusted


# ----------------------------------------------------------------------
# Install plan


@dataclass(frozen=True)
class InstallPlanEntry:
    """One resolved entry ready for the network-driver step."""

    name: str
    source: MarketplaceSource
    resolved_url: str = ""
    archive_format: str = "tarball"
    enabled_by_default: bool = False
    tags: tuple[str, ...] = ()


def build_install_plan(
    manifest: MarketplaceManifest,
    *,
    archive_format: str = "tarball",
    trusted_git_hosts: Optional[frozenset[str]] = None,
) -> tuple[InstallPlanEntry, ...]:
    """Resolve every manifest entry into an :class:`InstallPlanEntry`.

    Raises:
        ValueError: when an entry references an untrusted git host or
            the source cannot be resolved.
    """
    trusted = trusted_git_hosts if trusted_git_hosts is not None else DEFAULT_TRUSTED_GIT_HOSTS
    entries: list[InstallPlanEntry] = []
    for entry in manifest.plugins:
        src = entry.source
        resolved_url = ""
        if src.kind == SourceKind.PATH:
            resolved_url = src.path
        elif src.kind == SourceKind.GITHUB:
            resolved_url = resolve_github_archive_url(src, archive_format=archive_format)
        elif src.kind in (SourceKind.GIT, SourceKind.GIT_SUBDIR):
            if not is_trusted_git_host(src.git_url, trusted=trusted):
                raise ValueError(
                    f"entry {entry.name!r} references untrusted git host: {src.git_url!r}"
                )
            resolved_url = src.git_url
        elif src.kind == SourceKind.URL:
            resolved_url = src.url
        else:
            raise ValueError(f"entry {entry.name!r} has unknown source kind {src.kind!r}")
        entries.append(InstallPlanEntry(
            name=entry.name,
            source=src,
            resolved_url=resolved_url,
            archive_format=archive_format,
            enabled_by_default=entry.enabled_by_default,
            tags=entry.tags,
        ))
    return tuple(entries)


__all__ = [
    "DEFAULT_MAX_MANIFEST_BYTES",
    "DEFAULT_TRUSTED_GIT_HOSTS",
    "InstallPlanEntry",
    "MarketplaceManifest",
    "MarketplacePluginEntry",
    "MarketplaceSource",
    "SourceKind",
    "build_install_plan",
    "host_for_git_url",
    "is_trusted_git_host",
    "load_manifest_text",
    "looks_like_github_shorthand",
    "parse_github_shorthand",
    "parse_json_with_tolerance",
    "resolve_github_archive_url",
]
