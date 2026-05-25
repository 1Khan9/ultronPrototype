"""Tests for the T13 typed artifact-kind resolver."""

from __future__ import annotations

import base64
import io
import json
import tarfile

import pytest

from ultron.install.artifact_identity import (
    ArtifactIdentity,
    compute_identity,
)
from ultron.install.resolver import (
    ArtifactResolver,
    ArtifactVerificationOutcome,
    ExtractStrategy,
    ResolvedArtifact,
    ResolverError,
    build_git_ref_artifact,
    build_inline_markdown_artifact,
    build_local_path_artifact,
    build_npm_pack_artifact,
    build_tarball_url_artifact,
    verify_artifact_bytes,
)
from ultron.install.trust_envelope import ArtifactKind


def _make_tarball(*, name: str, version: str) -> bytes:
    """Construct a minimal ClawPack-shaped tar.gz for tests."""
    manifest = json.dumps({"name": name, "version": version}).encode("utf-8")
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as archive:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))
    return bio.getvalue()


# ---------------------------------------------------------------------------
# Builders


def test_build_local_path_artifact() -> None:
    art = build_local_path_artifact(
        path="/local/skill",
        expected_root="skills/local-skill",
        fingerprint="abc123",
    )
    assert art.kind is ArtifactKind.LOCAL_PATH
    assert art.fetch_url.startswith("file://")
    assert art.sha256_hex == "abc123"
    assert art.extract_strategy is ExtractStrategy.NONE


def test_build_tarball_url_artifact() -> None:
    art = build_tarball_url_artifact(
        url="https://example.test/foo.tgz",
        expected_root="skills/foo",
        sha256_hex="deadbeef",
        byte_length=1024,
    )
    assert art.kind is ArtifactKind.TARBALL_URL
    assert art.fetch_url == "https://example.test/foo.tgz"
    assert art.sha256_hex == "deadbeef"
    assert art.byte_length == 1024
    assert art.extract_strategy is ExtractStrategy.TAR_GZ


def test_build_git_ref_artifact_records_ref() -> None:
    art = build_git_ref_artifact(
        repo_url="https://github.com/owner/repo.git",
        ref="v1.2.3",
        expected_root="skills/repo",
    )
    assert art.kind is ArtifactKind.GIT_REF
    assert art.extract_strategy is ExtractStrategy.GIT_CLONE
    assert art.metadata["ref"] == "v1.2.3"


def test_build_git_ref_artifact_records_subdir() -> None:
    art = build_git_ref_artifact(
        repo_url="https://github.com/owner/repo.git",
        ref="abc123",
        expected_root="skills/repo",
        subdir="subdir/skill",
    )
    assert art.metadata["subdir"] == "subdir/skill"


def test_build_npm_pack_artifact_all_fields() -> None:
    art = build_npm_pack_artifact(
        download_url="https://registry.test/pkg-1.0.tgz",
        expected_root="plugins/pkg",
        sha256_hex="a" * 64,
        sha512_sri="sha512-AAA",
        sha1_shasum="b" * 40,
        byte_length=12345,
        npm_tarball_name="pkg-1.0.tgz",
        manifest_name="@user/pkg",
        manifest_version="1.0.0",
        trusted_publisher=True,
    )
    assert art.kind is ArtifactKind.NPM_PACK
    assert art.manifest_name == "@user/pkg"
    assert art.manifest_version == "1.0.0"
    assert art.trusted_publisher is True


def test_build_inline_markdown_artifact_auto_hashes() -> None:
    art = build_inline_markdown_artifact(
        blob=b"# heading",
        expected_root="skills/inline",
    )
    assert art.kind is ArtifactKind.INLINE_MARKDOWN
    assert art.extract_strategy is ExtractStrategy.INLINE_TEXT
    # sha256 was computed automatically
    expected = compute_identity(b"# heading").sha256_hex
    assert art.sha256_hex == expected
    assert art.byte_length == 9


# ---------------------------------------------------------------------------
# verify_artifact_bytes


def test_verify_local_path_passes_on_matching_fingerprint() -> None:
    blob = b"some skill body"
    fp = compute_identity(blob).sha256_hex
    art = build_local_path_artifact(
        path="/local",
        expected_root="skills/local",
        fingerprint=fp,
    )
    outcome = verify_artifact_bytes(art, blob)
    assert outcome.result.ok


def test_verify_local_path_fails_on_drift() -> None:
    art = build_local_path_artifact(
        path="/local",
        expected_root="skills/local",
        fingerprint="a" * 64,
    )
    outcome = verify_artifact_bytes(art, b"different bytes")
    assert not outcome.result.ok


def test_verify_tarball_url_digest_check() -> None:
    blob = b"tar.gz pretend bytes"
    identity = compute_identity(blob)
    art = build_tarball_url_artifact(
        url="https://example/foo.tgz",
        expected_root="skills/foo",
        sha256_hex=identity.sha256_hex,
        sha512_sri=identity.sha512_sri,
        sha1_shasum=identity.sha1_shasum,
        byte_length=identity.byte_length,
    )
    outcome = verify_artifact_bytes(art, blob)
    assert outcome.result.ok


def test_verify_tarball_url_size_mismatch() -> None:
    blob = b"hello"
    art = build_tarball_url_artifact(
        url="https://example/foo.tgz",
        expected_root="skills/foo",
        byte_length=999,
    )
    outcome = verify_artifact_bytes(art, blob)
    assert not outcome.result.ok


def test_verify_npm_pack_full_pass() -> None:
    blob = _make_tarball(name="@user/example", version="1.0.0")
    identity = compute_identity(blob)
    art = build_npm_pack_artifact(
        download_url="https://example/pkg.tgz",
        expected_root="plugins/example",
        sha256_hex=identity.sha256_hex,
        sha512_sri=identity.sha512_sri,
        sha1_shasum=identity.sha1_shasum,
        byte_length=identity.byte_length,
        npm_tarball_name="pkg.tgz",
        manifest_name="@user/example",
        manifest_version="1.0.0",
    )
    outcome = verify_artifact_bytes(art, blob)
    assert outcome.result.ok


def test_verify_npm_pack_manifest_mismatch_caught() -> None:
    blob = _make_tarball(name="@user/example", version="1.0.0")
    art = build_npm_pack_artifact(
        download_url="https://example/pkg.tgz",
        expected_root="plugins/example",
        sha256_hex="0" * 64,
        sha512_sri="sha512-zero",
        sha1_shasum="0" * 40,
        byte_length=len(blob),
        npm_tarball_name="pkg.tgz",
        manifest_name="@user/different-pkg",  # diverges from manifest
        manifest_version="1.0.0",
    )
    outcome = verify_artifact_bytes(art, blob)
    assert not outcome.result.ok


def test_verify_npm_pack_unparseable_tarball() -> None:
    art = build_npm_pack_artifact(
        download_url="https://example/pkg.tgz",
        expected_root="plugins/example",
        sha256_hex="a" * 64,
        sha512_sri="sha512-aaa",
        sha1_shasum="b" * 40,
        byte_length=20,
        npm_tarball_name="pkg.tgz",
        manifest_name="@user/example",
        manifest_version="1.0.0",
    )
    outcome = verify_artifact_bytes(art, b"\x00 not a real tarball")
    assert not outcome.result.ok
    # Synthetic mismatch for parse failure
    field_names = {m.field for m in outcome.result.mismatches}
    assert "tarball_parse" in field_names


def test_verify_git_ref_raises() -> None:
    art = build_git_ref_artifact(
        repo_url="https://github.com/owner/repo.git",
        ref="abc123",
        expected_root="skills/repo",
    )
    with pytest.raises(ResolverError):
        verify_artifact_bytes(art, b"any bytes")


def test_verify_inline_markdown_pass() -> None:
    blob = b"# title\nbody"
    art = build_inline_markdown_artifact(
        blob=blob,
        expected_root="skills/inline",
    )
    outcome = verify_artifact_bytes(art, blob)
    assert outcome.result.ok


def test_verify_inline_markdown_drift() -> None:
    blob_a = b"# original"
    art = build_inline_markdown_artifact(
        blob=blob_a,
        expected_root="skills/inline",
    )
    blob_b = b"# tampered body"
    outcome = verify_artifact_bytes(art, blob_b)
    assert not outcome.result.ok


# ---------------------------------------------------------------------------
# ArtifactResolver dispatch


def test_artifact_resolver_dispatches_to_local_path() -> None:
    resolver = ArtifactResolver()
    art = resolver.resolve(
        ArtifactKind.LOCAL_PATH,
        path="/local",
        expected_root="skills/x",
        fingerprint="a" * 64,
    )
    assert art.kind is ArtifactKind.LOCAL_PATH


def test_artifact_resolver_dispatches_to_tarball_url() -> None:
    resolver = ArtifactResolver()
    art = resolver.resolve(
        ArtifactKind.TARBALL_URL,
        url="https://example/foo.tgz",
        expected_root="skills/foo",
    )
    assert art.kind is ArtifactKind.TARBALL_URL


def test_artifact_resolver_dispatches_to_git_ref() -> None:
    resolver = ArtifactResolver()
    art = resolver.resolve(
        ArtifactKind.GIT_REF,
        repo_url="https://github.com/owner/repo.git",
        ref="v1.0",
        expected_root="skills/repo",
    )
    assert art.kind is ArtifactKind.GIT_REF


def test_artifact_resolver_dispatches_to_npm_pack() -> None:
    resolver = ArtifactResolver()
    art = resolver.resolve(
        ArtifactKind.NPM_PACK,
        download_url="https://reg/pkg.tgz",
        expected_root="plugins/x",
        sha256_hex="a" * 64,
        sha512_sri="sha512-aaa",
        sha1_shasum="b" * 40,
        byte_length=100,
        npm_tarball_name="pkg.tgz",
        manifest_name="@user/x",
        manifest_version="1.0.0",
    )
    assert art.kind is ArtifactKind.NPM_PACK


def test_artifact_resolver_dispatches_to_inline_markdown() -> None:
    resolver = ArtifactResolver()
    art = resolver.resolve(
        ArtifactKind.INLINE_MARKDOWN,
        blob=b"# hello",
        expected_root="skills/x",
    )
    assert art.kind is ArtifactKind.INLINE_MARKDOWN


def test_artifact_resolver_unknown_kind_raises() -> None:
    """Removing the LOCAL_PATH builder makes that kind unresolvable."""
    resolver = ArtifactResolver(builders={})
    with pytest.raises(ResolverError):
        resolver.resolve(ArtifactKind.LOCAL_PATH, path="/x", expected_root="y")


# ---------------------------------------------------------------------------
# ArtifactVerificationOutcome


def test_outcome_includes_computed_identity() -> None:
    blob = b"any bytes"
    art = build_inline_markdown_artifact(blob=blob, expected_root="skills/x")
    outcome = verify_artifact_bytes(art, blob)
    assert outcome.identity == compute_identity(blob)
    assert outcome.artifact == art
