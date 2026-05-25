"""Tests for the T2 triple-digest artifact identity verification."""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from ultron.install.artifact_identity import (
    SRI_SHA512_PREFIX,
    ArtifactIdentity,
    ClawPackContents,
    ClawPackParseError,
    IdentityMismatch,
    IdentityVerificationResult,
    PinnedDigest,
    compute_identity,
    compute_identity_from_path,
    compute_sha1_shasum,
    compute_sha256_hex,
    compute_sha512_sri,
    load_pinned_digest,
    parse_clawpack_contents,
    pin_first_use_digests,
    verify_against_pin,
    verify_clawpack_tarball,
    verify_identity,
)


SAMPLE = b"hello clawhub world"


# ---------------------------------------------------------------------------
# Digest computation


def test_sha256_hex_matches_hashlib() -> None:
    assert compute_sha256_hex(SAMPLE) == hashlib.sha256(SAMPLE).hexdigest()


def test_sha1_shasum_matches_hashlib() -> None:
    assert compute_sha1_shasum(SAMPLE) == hashlib.sha1(SAMPLE).hexdigest()


def test_sha512_sri_has_prefix_and_base64_body() -> None:
    sri = compute_sha512_sri(SAMPLE)
    assert sri.startswith(SRI_SHA512_PREFIX)
    body = sri[len(SRI_SHA512_PREFIX):]
    # Decodes back to the actual sha512 bytes.
    decoded = base64.b64decode(body)
    assert decoded == hashlib.sha512(SAMPLE).digest()


def test_compute_identity_round_trip() -> None:
    identity = compute_identity(SAMPLE)
    assert identity.sha256_hex == compute_sha256_hex(SAMPLE)
    assert identity.sha1_shasum == compute_sha1_shasum(SAMPLE)
    assert identity.sha512_sri == compute_sha512_sri(SAMPLE)
    assert identity.byte_length == len(SAMPLE)


def test_compute_identity_from_path_matches_blob(tmp_path: Path) -> None:
    p = tmp_path / "blob.bin"
    p.write_bytes(SAMPLE)
    by_blob = compute_identity(SAMPLE)
    by_path = compute_identity_from_path(p)
    assert by_blob == by_path


def test_compute_identity_empty_bytes() -> None:
    identity = compute_identity(b"")
    assert identity.byte_length == 0
    assert identity.sha256_hex == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# verify_identity


def test_verify_identity_all_match() -> None:
    identity = compute_identity(SAMPLE)
    result = verify_identity(
        identity,
        expected_sha256_hex=identity.sha256_hex,
        expected_sha512_sri=identity.sha512_sri,
        expected_sha1_shasum=identity.sha1_shasum,
        expected_byte_length=identity.byte_length,
    )
    assert result.ok
    assert result.mismatches == ()
    assert set(result.compared_fields) == {
        "sha256_hex",
        "sha512_sri",
        "sha1_shasum",
        "byte_length",
    }


def test_verify_identity_sha256_mismatch() -> None:
    identity = compute_identity(SAMPLE)
    result = verify_identity(
        identity,
        expected_sha256_hex="a" * 64,
    )
    assert not result.ok
    assert len(result.mismatches) == 1
    assert result.mismatches[0].field == "sha256_hex"


def test_verify_identity_size_mismatch() -> None:
    identity = compute_identity(SAMPLE)
    result = verify_identity(
        identity,
        expected_byte_length=999,
    )
    assert not result.ok
    assert result.mismatches[0].field == "byte_length"


def test_verify_identity_no_expected_returns_ok_with_zero_compared() -> None:
    identity = compute_identity(SAMPLE)
    result = verify_identity(identity)
    assert result.ok
    assert result.compared_fields == ()


def test_verify_identity_case_insensitive_hex() -> None:
    identity = compute_identity(SAMPLE)
    result = verify_identity(
        identity,
        expected_sha256_hex=identity.sha256_hex.upper(),
    )
    assert result.ok


def test_verify_identity_sri_case_sensitive() -> None:
    """SRI is base64 (case-sensitive) so different-case rejects."""
    identity = compute_identity(SAMPLE)
    # Flip case of one character of the base64 body.
    sri = identity.sha512_sri
    body = sri[len(SRI_SHA512_PREFIX):]
    flipped_char = body[0].upper() if body[0].islower() else body[0].lower()
    if flipped_char != body[0]:
        tampered = SRI_SHA512_PREFIX + flipped_char + body[1:]
        result = verify_identity(identity, expected_sha512_sri=tampered)
        assert not result.ok


def test_verify_identity_strips_whitespace_in_expected() -> None:
    identity = compute_identity(SAMPLE)
    result = verify_identity(
        identity,
        expected_sha256_hex="  " + identity.sha256_hex + "  ",
    )
    assert result.ok


# ---------------------------------------------------------------------------
# ClawPack-style tarball parsing


def _make_clawpack_tarball(*, name: str, version: str, body_files: dict[str, bytes]) -> bytes:
    """Construct an in-memory ClawPack-shaped tar.gz with the given files.

    ``body_files`` keys are filenames under ``package/`` (excluding the
    package.json the helper adds automatically).
    """
    manifest = {"name": name, "version": version}
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as archive:
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(manifest_bytes)
        archive.addfile(info, io.BytesIO(manifest_bytes))
        for path, content in body_files.items():
            full = f"package/{path}"
            info = tarfile.TarInfo(name=full)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return bio.getvalue()


def test_parse_clawpack_contents_basic() -> None:
    blob = _make_clawpack_tarball(
        name="@user/example", version="1.2.3",
        body_files={"README.md": b"# hello"},
    )
    contents = parse_clawpack_contents(blob)
    assert contents.name == "@user/example"
    assert contents.version == "1.2.3"
    assert contents.manifest["name"] == "@user/example"


def test_parse_clawpack_contents_no_package_json_raises() -> None:
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as archive:
        info = tarfile.TarInfo(name="package/README.md")
        body = b"# nothing\n"
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    with pytest.raises(ClawPackParseError):
        parse_clawpack_contents(bio.getvalue())


def test_parse_clawpack_contents_oversized_manifest_raises() -> None:
    big_manifest = (b"x" * (1024 * 1024 + 1))
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as archive:
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(big_manifest)
        archive.addfile(info, io.BytesIO(big_manifest))
    with pytest.raises(ClawPackParseError):
        parse_clawpack_contents(bio.getvalue(), max_manifest_bytes=256 * 1024)


def test_parse_clawpack_contents_bad_json_raises() -> None:
    bio = io.BytesIO()
    with tarfile.open(fileobj=bio, mode="w:gz") as archive:
        body = b"{ not json"
        info = tarfile.TarInfo(name="package/package.json")
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    with pytest.raises(ClawPackParseError):
        parse_clawpack_contents(bio.getvalue())


def test_parse_clawpack_missing_name_raises() -> None:
    blob = _make_clawpack_tarball(
        name="", version="1.0.0", body_files={},
    )
    with pytest.raises(ClawPackParseError):
        parse_clawpack_contents(blob)


def test_parse_clawpack_missing_version_raises() -> None:
    blob = _make_clawpack_tarball(
        name="x", version="", body_files={},
    )
    with pytest.raises(ClawPackParseError):
        parse_clawpack_contents(blob)


def test_parse_clawpack_non_gzip_raises() -> None:
    # Plain bytes; not a gzipped tarball
    with pytest.raises(ClawPackParseError):
        parse_clawpack_contents(b"\x00\x01\x02 not a tarball")


# ---------------------------------------------------------------------------
# verify_clawpack_tarball


def test_verify_clawpack_pass() -> None:
    blob = _make_clawpack_tarball(
        name="@user/example", version="1.0.0",
        body_files={"main.py": b"print('hi')\n"},
    )
    identity = compute_identity(blob)
    result = verify_clawpack_tarball(
        blob,
        expected_name="@user/example",
        expected_version="1.0.0",
        expected_identity=identity,
    )
    assert result.ok


def test_verify_clawpack_manifest_name_mismatch() -> None:
    blob = _make_clawpack_tarball(
        name="@user/example", version="1.0.0",
        body_files={"main.py": b"x"},
    )
    result = verify_clawpack_tarball(
        blob,
        expected_name="@other/different",
        expected_version="1.0.0",
    )
    assert not result.ok
    field_names = {m.field for m in result.mismatches}
    assert "manifest_name" in field_names


def test_verify_clawpack_manifest_version_mismatch() -> None:
    blob = _make_clawpack_tarball(
        name="@user/example", version="1.0.0",
        body_files={"main.py": b"x"},
    )
    result = verify_clawpack_tarball(
        blob,
        expected_name="@user/example",
        expected_version="2.0.0",
    )
    assert not result.ok
    field_names = {m.field for m in result.mismatches}
    assert "manifest_version" in field_names


def test_verify_clawpack_digest_mismatch() -> None:
    blob = _make_clawpack_tarball(
        name="@user/example", version="1.0.0",
        body_files={"main.py": b"x"},
    )
    fake_id = ArtifactIdentity(
        sha256_hex="a" * 64,
        sha512_sri=SRI_SHA512_PREFIX + base64.b64encode(b"x" * 64).decode("ascii"),
        sha1_shasum="b" * 40,
        byte_length=99999,
    )
    result = verify_clawpack_tarball(
        blob,
        expected_name="@user/example",
        expected_version="1.0.0",
        expected_identity=fake_id,
    )
    assert not result.ok


def test_verify_clawpack_parse_error_propagates() -> None:
    with pytest.raises(ClawPackParseError):
        verify_clawpack_tarball(
            b"\x00 not a tarball",
            expected_name="x",
            expected_version="1.0.0",
        )


# ---------------------------------------------------------------------------
# TOFU pin file


def test_pin_first_use_creates_file(tmp_path: Path) -> None:
    pin_file = tmp_path / "pins.jsonl"
    identity = compute_identity(SAMPLE)
    pinned = pin_first_use_digests(identity, "test:identifier", pin_file=pin_file)
    assert pinned.identifier == "test:identifier"
    assert pin_file.is_file()
    lines = pin_file.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["identifier"] == "test:identifier"


def test_load_pinned_digest_returns_latest(tmp_path: Path) -> None:
    pin_file = tmp_path / "pins.jsonl"
    id_a = compute_identity(b"alpha")
    id_b = compute_identity(b"beta")
    pin_first_use_digests(id_a, "x", pin_file=pin_file, notes="first")
    pin_first_use_digests(id_b, "x", pin_file=pin_file, notes="rotated")
    pinned = load_pinned_digest("x", pin_file=pin_file)
    assert pinned is not None
    assert pinned.notes == "rotated"
    assert pinned.sha256_hex == id_b.sha256_hex


def test_load_pinned_digest_missing_returns_none(tmp_path: Path) -> None:
    pin_file = tmp_path / "missing.jsonl"
    assert load_pinned_digest("x", pin_file=pin_file) is None


def test_load_pinned_digest_unknown_id_returns_none(tmp_path: Path) -> None:
    pin_file = tmp_path / "pins.jsonl"
    pin_first_use_digests(compute_identity(SAMPLE), "x", pin_file=pin_file)
    assert load_pinned_digest("not-recorded", pin_file=pin_file) is None


def test_load_pinned_digest_skips_malformed_rows(tmp_path: Path) -> None:
    pin_file = tmp_path / "pins.jsonl"
    pin_file.parent.mkdir(parents=True, exist_ok=True)
    pin_file.write_text(
        "{ not json\n"
        + json.dumps({
            "identifier": "x",
            "sha256_hex": "a" * 64,
            "sha512_sri": "sha512-aaa",
            "sha1_shasum": "b" * 40,
            "byte_length": 10,
            "pinned_at": "2026-01-01T00:00:00+00:00",
        })
        + "\n",
        encoding="utf-8",
    )
    pinned = load_pinned_digest("x", pin_file=pin_file)
    assert pinned is not None
    assert pinned.identifier == "x"


def test_verify_against_pin_no_pin_returns_ok_with_zero_compared(tmp_path: Path) -> None:
    pin_file = tmp_path / "empty.jsonl"
    identity = compute_identity(SAMPLE)
    result = verify_against_pin(identity, "x", pin_file=pin_file)
    assert result.ok
    assert result.compared_fields == ()


def test_verify_against_pin_matching(tmp_path: Path) -> None:
    pin_file = tmp_path / "pins.jsonl"
    identity = compute_identity(SAMPLE)
    pin_first_use_digests(identity, "x", pin_file=pin_file)
    result = verify_against_pin(identity, "x", pin_file=pin_file)
    assert result.ok


def test_verify_against_pin_mismatch_detected(tmp_path: Path) -> None:
    pin_file = tmp_path / "pins.jsonl"
    identity_a = compute_identity(b"alpha")
    pin_first_use_digests(identity_a, "x", pin_file=pin_file)
    # Now verify with different bytes.
    identity_b = compute_identity(b"beta")
    result = verify_against_pin(identity_b, "x", pin_file=pin_file)
    assert not result.ok
