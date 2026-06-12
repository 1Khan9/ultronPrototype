"""Typed artifact-kind resolver (T13).

T13 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Replaces the conditional ``if kind == github / elif kind == git / ...``
branches in :mod:`ultron.skills.marketplace` with a typed
:class:`ResolvedArtifact` envelope per source. Each variant carries
the format-specific fetch URL plus the kind-specific verification
rules so the install driver doesn't have to guess archive format
from a shared URL string.

The resolver pattern (mirrored from the upstream marketplace):

1. **Resolve.** Walk the manifest entry; produce a typed
   :class:`ResolvedArtifact` describing the source.
2. **Fetch.** Driver invokes the kind's fetch_url (HTTP for
   TARBALL_URL / GITHUB; local copy for LOCAL_PATH; git CLI for
   GIT_REF).
3. **Verify.** Per-kind verification rules: NPM_PACK + ClawPack
   add manifest-name + manifest-version + npm-integrity checks;
   GITHUB sources verify against the commit-SHA-implied tag;
   LOCAL_PATH verifies content fingerprint via :mod:`ultron.install.lockfile`.
4. **Extract.** Driver materialises bytes into the target dir
   using the per-kind :class:`ExtractStrategy` hint.

This module ships the envelope + the per-kind verifier dispatch.
The actual fetch / extract IO is INJECTED by the marketplace so
tests stay hermetic and SSRF-guard policies layer cleanly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable, Mapping, Optional

from ultron.install.artifact_identity import (
    ArtifactIdentity,
    ClawPackParseError,
    IdentityMismatch,
    IdentityVerificationResult,
    compute_identity,
    verify_clawpack_tarball,
    verify_identity,
)
from ultron.install.trust_envelope import ArtifactKind

LOGGER = logging.getLogger(__name__)


class ExtractStrategy(str, Enum):
    """How the install driver should materialise the artifact's bytes."""

    NONE = "none"  # LOCAL_PATH: nothing to extract; verify in-place
    TAR_GZ = "tar_gz"
    ZIP = "zip"
    GIT_CLONE = "git_clone"
    INLINE_TEXT = "inline_text"  # write blob verbatim to expected_root


class ResolverError(RuntimeError):
    """Raised when a manifest entry cannot be resolved to a typed artifact."""


@dataclass(frozen=True)
class ResolvedArtifact:
    """Typed envelope describing one resolved artifact.

    Fields:
        kind: which :class:`ArtifactKind` discriminator this is.
        fetch_url: URL the driver fetches (file:// for LOCAL_PATH,
            https:// for tarballs, git+https:// or git@ for GIT_REF).
        sha256_hex: expected SHA-256 hex (None when unknown -- TOFU
            pin path applies).
        sha512_sri: expected SHA-512 SRI (None when unknown).
        sha1_shasum: expected SHA-1 (None when unknown).
        byte_length: expected byte length (None when unknown).
        extract_strategy: how to materialise the bytes.
        expected_root: directory under the install root the
            artifact should populate.
        npm_tarball_name: when present, the expected name of the
            inner tarball (for ClawPack format checks).
        manifest_name: when present, the expected
            ``package/package.json``'s ``name`` for ClawPack
            internal verification.
        manifest_version: same for ``version``.
        trusted_publisher: True when the source maps to a
            pre-registered trusted publisher tuple (T7 territory).
        metadata: opaque per-source extras (e.g. git ref).
    """

    kind: ArtifactKind
    fetch_url: str
    extract_strategy: ExtractStrategy
    expected_root: str
    sha256_hex: Optional[str] = None
    sha512_sri: Optional[str] = None
    sha1_shasum: Optional[str] = None
    byte_length: Optional[int] = None
    npm_tarball_name: Optional[str] = None
    manifest_name: Optional[str] = None
    manifest_version: Optional[str] = None
    trusted_publisher: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-kind builders


def build_local_path_artifact(
    *,
    path: str,
    expected_root: str,
    fingerprint: Optional[str] = None,
    metadata: Optional[Mapping[str, object]] = None,
) -> ResolvedArtifact:
    """Build a LOCAL_PATH ResolvedArtifact.

    Local-path sources have no fetch IO -- the artifact's bytes are
    on the local filesystem already. ``fingerprint`` (when supplied)
    is the SHA-256 of the canonical content payload computed by
    :func:`ultron.install.lockfile.compute_skill_fingerprint`; the
    install driver uses it as the sha256 for verification.
    """
    return ResolvedArtifact(
        kind=ArtifactKind.LOCAL_PATH,
        fetch_url=f"file://{path}",
        sha256_hex=fingerprint,
        extract_strategy=ExtractStrategy.NONE,
        expected_root=expected_root,
        metadata=dict(metadata or {}),
    )


def build_tarball_url_artifact(
    *,
    url: str,
    expected_root: str,
    sha256_hex: Optional[str] = None,
    sha512_sri: Optional[str] = None,
    sha1_shasum: Optional[str] = None,
    byte_length: Optional[int] = None,
    metadata: Optional[Mapping[str, object]] = None,
) -> ResolvedArtifact:
    """Build a TARBALL_URL ResolvedArtifact (generic HTTP tarball)."""
    return ResolvedArtifact(
        kind=ArtifactKind.TARBALL_URL,
        fetch_url=url,
        sha256_hex=sha256_hex,
        sha512_sri=sha512_sri,
        sha1_shasum=sha1_shasum,
        byte_length=byte_length,
        extract_strategy=ExtractStrategy.TAR_GZ,
        expected_root=expected_root,
        metadata=dict(metadata or {}),
    )


def build_git_ref_artifact(
    *,
    repo_url: str,
    ref: str,
    expected_root: str,
    subdir: str = "",
    metadata: Optional[Mapping[str, object]] = None,
) -> ResolvedArtifact:
    """Build a GIT_REF ResolvedArtifact.

    ``ref`` may be a commit SHA, a tag, or a branch. The trust
    contract is strongest with commit SHA (content-addressed).
    Tags are mutable; the driver should warn when ``ref`` is not
    SHA-shaped and TOFU-pin the resolved SHA on first fetch.
    """
    meta = dict(metadata or {})
    meta.setdefault("ref", ref)
    if subdir:
        meta.setdefault("subdir", subdir)
    return ResolvedArtifact(
        kind=ArtifactKind.GIT_REF,
        fetch_url=repo_url,
        extract_strategy=ExtractStrategy.GIT_CLONE,
        expected_root=expected_root,
        metadata=meta,
    )


def build_npm_pack_artifact(
    *,
    download_url: str,
    expected_root: str,
    sha256_hex: str,
    sha512_sri: str,
    sha1_shasum: str,
    byte_length: int,
    npm_tarball_name: str,
    manifest_name: str,
    manifest_version: str,
    trusted_publisher: bool = False,
    metadata: Optional[Mapping[str, object]] = None,
) -> ResolvedArtifact:
    """Build an NPM_PACK ResolvedArtifact (ClawPack-style).

    All digests required; verification is fail-closed.
    """
    return ResolvedArtifact(
        kind=ArtifactKind.NPM_PACK,
        fetch_url=download_url,
        sha256_hex=sha256_hex,
        sha512_sri=sha512_sri,
        sha1_shasum=sha1_shasum,
        byte_length=byte_length,
        extract_strategy=ExtractStrategy.TAR_GZ,
        expected_root=expected_root,
        npm_tarball_name=npm_tarball_name,
        manifest_name=manifest_name,
        manifest_version=manifest_version,
        trusted_publisher=trusted_publisher,
        metadata=dict(metadata or {}),
    )


def build_inline_markdown_artifact(
    *,
    blob: bytes,
    expected_root: str,
    filename: str = "SKILL.md",
    sha256_hex: Optional[str] = None,
    metadata: Optional[Mapping[str, object]] = None,
) -> ResolvedArtifact:
    """Build an INLINE_MARKDOWN ResolvedArtifact.

    Trigger-loaded skill bodies that ship as a single .md file (no
    archive). The blob is the verbatim file contents; computed
    sha256 is recorded so subsequent fetches verify identity.
    """
    sha = sha256_hex
    if sha is None:
        sha = compute_identity(blob).sha256_hex
    meta = dict(metadata or {})
    meta.setdefault("filename", filename)
    meta.setdefault("blob_length", len(blob))
    return ResolvedArtifact(
        kind=ArtifactKind.INLINE_MARKDOWN,
        fetch_url=f"inline:{filename}",
        sha256_hex=sha,
        byte_length=len(blob),
        extract_strategy=ExtractStrategy.INLINE_TEXT,
        expected_root=expected_root,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# Per-kind verifier dispatch


@dataclass(frozen=True)
class ArtifactVerificationOutcome:
    """Result of running an artifact's full per-kind verifier chain."""

    artifact: ResolvedArtifact
    identity: ArtifactIdentity
    result: IdentityVerificationResult


def verify_artifact_bytes(
    artifact: ResolvedArtifact,
    blob: bytes,
) -> ArtifactVerificationOutcome:
    """Run the per-kind verifier chain against ``blob``.

    Dispatch by :attr:`ResolvedArtifact.kind`:

    * **NPM_PACK** -- digest + size + tarball-internal name/version
      via :func:`verify_clawpack_tarball`.
    * **TARBALL_URL** -- digest + size only.
    * **GIT_REF** -- not applicable (git clone happens out-of-band;
      use :func:`compute_identity_from_path` post-checkout).
    * **LOCAL_PATH** -- digest only (fingerprint is the content
      attestation).
    * **INLINE_MARKDOWN** -- digest + byte_length.

    Returns the outcome with the computed identity attached so
    callers (the install driver, audit log) can record it
    regardless of pass/fail.

    Raises :class:`ResolverError` for kinds that don't take raw
    bytes (currently GIT_REF -- callers should verify after the
    clone+checkout).
    """
    if artifact.kind is ArtifactKind.GIT_REF:
        raise ResolverError(
            "GIT_REF artifacts do not support byte-level verification; "
            "verify post-checkout via compute_identity_from_path"
        )
    identity = compute_identity(blob)

    if artifact.kind is ArtifactKind.NPM_PACK:
        expected_id = ArtifactIdentity(
            sha256_hex=artifact.sha256_hex or "",
            sha512_sri=artifact.sha512_sri or "",
            sha1_shasum=artifact.sha1_shasum or "",
            byte_length=artifact.byte_length or 0,
        )
        if not artifact.manifest_name or not artifact.manifest_version:
            raise ResolverError(
                "NPM_PACK ResolvedArtifact missing manifest_name / manifest_version"
            )
        try:
            result = verify_clawpack_tarball(
                blob,
                expected_name=artifact.manifest_name,
                expected_version=artifact.manifest_version,
                expected_identity=expected_id if artifact.sha256_hex else None,
            )
        except ClawPackParseError as exc:
            # Represent parse failure as a synthetic mismatch so audit
            # consumers branch on .ok rather than catching the
            # exception themselves.
            return ArtifactVerificationOutcome(
                artifact=artifact,
                identity=identity,
                result=IdentityVerificationResult(
                    ok=False,
                    mismatches=(
                        IdentityMismatch(
                            field="tarball_parse",
                            actual=str(exc),
                            expected="valid ClawPack tarball",
                        ),
                    ),
                    compared_fields=("tarball_parse",),
                ),
            )
        return ArtifactVerificationOutcome(
            artifact=artifact, identity=identity, result=result
        )

    # TARBALL_URL / LOCAL_PATH / INLINE_MARKDOWN -- digest-only path
    result = verify_identity(
        identity,
        expected_sha256_hex=artifact.sha256_hex,
        expected_sha512_sri=artifact.sha512_sri,
        expected_sha1_shasum=artifact.sha1_shasum,
        expected_byte_length=artifact.byte_length,
    )
    return ArtifactVerificationOutcome(
        artifact=artifact, identity=identity, result=result
    )


# ---------------------------------------------------------------------------
# ArtifactResolver protocol + reference impl


@dataclass
class ArtifactResolver:
    """Marketplace-facing resolver.

    Wraps the per-kind builders behind a single ``resolve(entry)``
    surface so callers don't need to know which builder applies to
    which source. Subclass for custom resolution (e.g. fetching
    registry metadata to populate npm-pack expected digests).
    """

    builders: Mapping[ArtifactKind, Callable[..., ResolvedArtifact]] = field(
        default_factory=lambda: {
            ArtifactKind.LOCAL_PATH: build_local_path_artifact,
            ArtifactKind.TARBALL_URL: build_tarball_url_artifact,
            ArtifactKind.GIT_REF: build_git_ref_artifact,
            ArtifactKind.NPM_PACK: build_npm_pack_artifact,
            ArtifactKind.INLINE_MARKDOWN: build_inline_markdown_artifact,
        }
    )

    def resolve(self, kind: ArtifactKind, /, **kwargs: object) -> ResolvedArtifact:
        """Dispatch to the appropriate builder for ``kind``.

        Raises :class:`ResolverError` for unsupported kinds.
        """
        builder = self.builders.get(kind)
        if builder is None:
            raise ResolverError(f"No builder registered for ArtifactKind.{kind.name}")
        return builder(**kwargs)


__all__ = [
    "ExtractStrategy",
    "ResolverError",
    "ResolvedArtifact",
    "ArtifactVerificationOutcome",
    "ArtifactResolver",
    "build_local_path_artifact",
    "build_tarball_url_artifact",
    "build_git_ref_artifact",
    "build_npm_pack_artifact",
    "build_inline_markdown_artifact",
    "verify_artifact_bytes",
]
