"""Triple-digest artifact identity verification on download (T2).

T2 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
On every install / update / re-verify, the client computes three
independent digests of the downloaded bytes plus the byte length,
and compares each against published expected values. Any mismatch
raises -- the artifact is discarded BEFORE extraction.

Three digest families (preserved verbatim as API contracts; install
clients on either end of the wire must compute the same values):

* :func:`compute_sha256_hex` — hex-encoded SHA-256. The ClawHub
  primary identity field.
* :func:`compute_sha512_sri` — Subresource-Integrity-format SHA-512
  (``sha512-<base64>``). The npm integrity field shape.
* :func:`compute_sha1_shasum` — hex-encoded SHA-1. The npm shasum
  legacy field shape.

Plus byte length: a published artifact size that doesn't match
indicates the bytes-on-the-wire are not the bytes the registry
attests to (truncation, replacement, MITM).

For ClawPack tarballs (gzip-compressed npm-pack tarball), the
client ALSO extracts ``package/package.json`` from inside the
archive and verifies the embedded ``name`` + ``version`` match
what the registry said this version was. This catches a malicious
mirror that replaces the artifact's bytes with a different (still
ClawPack-shaped) package's contents.

Trust-pin support (TOFU): when an upstream digest is unknown (e.g.
a GitHub-tag fetch with no published manifest), the client computes
the identity on first fetch and records it via
:func:`pin_first_use_digests` to ``data/install/pinned_digests.jsonl``.
Subsequent fetches verify against the recorded pin and refuse
silent swaps.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import re
import tarfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional

LOGGER = logging.getLogger(__name__)

#: Prefix on the SRI-formatted SHA-512 integrity field.
SRI_SHA512_PREFIX: str = "sha512-"

#: Default path for the TOFU pin file (relative to PROJECT_ROOT).
DEFAULT_PIN_FILE_RELATIVE: str = "data/install/pinned_digests.jsonl"


# ---------------------------------------------------------------------------
# Digest computation


def compute_sha256_hex(blob: bytes) -> str:
    """Return hex-encoded SHA-256 of ``blob``."""
    return hashlib.sha256(blob).hexdigest()


def compute_sha1_shasum(blob: bytes) -> str:
    """Return hex-encoded SHA-1 of ``blob``."""
    return hashlib.sha1(blob).hexdigest()


def compute_sha512_sri(blob: bytes) -> str:
    """Return SRI-format SHA-512: ``sha512-<base64-of-digest>``.

    The integrity field upstream npm clients use. Base64 is standard
    (not URL-safe); padding preserved.
    """
    raw = hashlib.sha512(blob).digest()
    return SRI_SHA512_PREFIX + base64.b64encode(raw).decode("ascii")


# ---------------------------------------------------------------------------
# ArtifactIdentity dataclass


@dataclass(frozen=True)
class ArtifactIdentity:
    """Computed identity of one artifact's bytes.

    Fields:
        sha256_hex: hex SHA-256.
        sha512_sri: SRI-formatted SHA-512.
        sha1_shasum: hex SHA-1.
        byte_length: total bytes of the artifact.
    """

    sha256_hex: str
    sha512_sri: str
    sha1_shasum: str
    byte_length: int


def compute_identity(blob: bytes) -> ArtifactIdentity:
    """Compute the full :class:`ArtifactIdentity` for ``blob``."""
    return ArtifactIdentity(
        sha256_hex=compute_sha256_hex(blob),
        sha512_sri=compute_sha512_sri(blob),
        sha1_shasum=compute_sha1_shasum(blob),
        byte_length=len(blob),
    )


def compute_identity_from_path(path: Path) -> ArtifactIdentity:
    """Compute :class:`ArtifactIdentity` by reading ``path`` from disk.

    Streamed in 64 KB chunks via independent hashlib instances so
    large artifacts don't blow up RAM.
    """
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1()
    sha512 = hashlib.sha512()
    byte_length = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            sha256.update(chunk)
            sha1.update(chunk)
            sha512.update(chunk)
            byte_length += len(chunk)
    return ArtifactIdentity(
        sha256_hex=sha256.hexdigest(),
        sha512_sri=SRI_SHA512_PREFIX + base64.b64encode(sha512.digest()).decode("ascii"),
        sha1_shasum=sha1.hexdigest(),
        byte_length=byte_length,
    )


# ---------------------------------------------------------------------------
# Verification


@dataclass(frozen=True)
class IdentityMismatch:
    """One mismatched field in an identity comparison.

    Carries the field name + the two values (actual / expected) so
    audit-log consumers can show "actual sha256_hex was X; expected
    Y" without re-parsing the result tuple.
    """

    field: str
    actual: str
    expected: str


@dataclass(frozen=True)
class IdentityVerificationResult:
    """Outcome of :func:`verify_identity`.

    Fields:
        ok: True iff every supplied expected field matches the actual.
        mismatches: tuple of :class:`IdentityMismatch` for each field
            that diverged. Empty when ``ok=True``.
        compared_fields: tuple of field names that were actually
            compared (a field is skipped when the expected value is
            None / empty; ok=True with zero compared fields means
            "no expected digests supplied" -> the caller should treat
            this as a non-verification, not a pass).
    """

    ok: bool
    mismatches: tuple[IdentityMismatch, ...] = ()
    compared_fields: tuple[str, ...] = ()


def verify_identity(
    actual: ArtifactIdentity,
    *,
    expected_sha256_hex: Optional[str] = None,
    expected_sha512_sri: Optional[str] = None,
    expected_sha1_shasum: Optional[str] = None,
    expected_byte_length: Optional[int] = None,
) -> IdentityVerificationResult:
    """Compare ``actual`` to each non-None expected field.

    Each supplied expected value is compared case-insensitively for
    the hex fields, case-sensitively for the SRI field. Returns a
    :class:`IdentityVerificationResult` so callers can branch on
    ``.ok`` and render audit rows.

    Missing expected values are silently skipped (no mismatch
    raised). A caller that requires at least one digest comparison
    should inspect ``.compared_fields`` and fail when empty.
    """
    mismatches: list[IdentityMismatch] = []
    compared: list[str] = []

    if expected_sha256_hex:
        compared.append("sha256_hex")
        if actual.sha256_hex.casefold() != expected_sha256_hex.strip().casefold():
            mismatches.append(
                IdentityMismatch(
                    field="sha256_hex",
                    actual=actual.sha256_hex,
                    expected=expected_sha256_hex.strip(),
                )
            )
    if expected_sha512_sri:
        compared.append("sha512_sri")
        actual_value = actual.sha512_sri
        expected_value = expected_sha512_sri.strip()
        if actual_value != expected_value:
            mismatches.append(
                IdentityMismatch(
                    field="sha512_sri",
                    actual=actual_value,
                    expected=expected_value,
                )
            )
    if expected_sha1_shasum:
        compared.append("sha1_shasum")
        if actual.sha1_shasum.casefold() != expected_sha1_shasum.strip().casefold():
            mismatches.append(
                IdentityMismatch(
                    field="sha1_shasum",
                    actual=actual.sha1_shasum,
                    expected=expected_sha1_shasum.strip(),
                )
            )
    if expected_byte_length is not None:
        compared.append("byte_length")
        if actual.byte_length != expected_byte_length:
            mismatches.append(
                IdentityMismatch(
                    field="byte_length",
                    actual=str(actual.byte_length),
                    expected=str(expected_byte_length),
                )
            )

    return IdentityVerificationResult(
        ok=not mismatches,
        mismatches=tuple(mismatches),
        compared_fields=tuple(compared),
    )


# ---------------------------------------------------------------------------
# ClawPack-style tarball-internal verification


class ClawPackParseError(RuntimeError):
    """Raised when a ClawPack tarball cannot be parsed for internal verification."""


@dataclass(frozen=True)
class ClawPackContents:
    """Subset of fields extracted from ``package/package.json`` inside a ClawPack tarball.

    Fields:
        name: the embedded package name.
        version: the embedded version.
        manifest: the full parsed JSON object (for callers that want
            to inspect additional fields like ``openclaw.compat``).
    """

    name: str
    version: str
    manifest: Mapping[str, object]


_PACKAGE_JSON_PATH_RE: re.Pattern[str] = re.compile(
    r"^package/package\.json$"
)


def parse_clawpack_contents(blob: bytes, *, max_manifest_bytes: int = 256 * 1024) -> ClawPackContents:
    """Extract + parse ``package/package.json`` from a ClawPack tarball.

    ``blob`` is the gzipped tarball bytes. Raises
    :class:`ClawPackParseError` on any structural failure (not a
    valid tar, no package.json under package/, oversized manifest,
    bad JSON, missing name/version fields).
    """
    try:
        bio = io.BytesIO(blob)
        with tarfile.open(fileobj=bio, mode="r:gz") as archive:
            target_member = None
            for member in archive.getmembers():
                if _PACKAGE_JSON_PATH_RE.match(member.name):
                    target_member = member
                    break
            if target_member is None:
                raise ClawPackParseError(
                    "no package/package.json found in tarball"
                )
            if target_member.size > max_manifest_bytes:
                raise ClawPackParseError(
                    f"package.json size {target_member.size} exceeds {max_manifest_bytes}"
                )
            handle = archive.extractfile(target_member)
            if handle is None:
                raise ClawPackParseError("package.json entry has no payload")
            raw = handle.read()
    except tarfile.TarError as exc:
        raise ClawPackParseError(f"tar parse failure: {exc}") from exc
    except OSError as exc:
        raise ClawPackParseError(f"tar read failure: {exc}") from exc

    try:
        manifest = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ClawPackParseError(f"package.json JSON parse failure: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ClawPackParseError("package.json top-level is not an object")
    name = manifest.get("name")
    version = manifest.get("version")
    if not isinstance(name, str) or not name.strip():
        raise ClawPackParseError("package.json missing required field 'name'")
    if not isinstance(version, str) or not version.strip():
        raise ClawPackParseError("package.json missing required field 'version'")
    return ClawPackContents(
        name=name.strip(),
        version=version.strip(),
        manifest=dict(manifest),
    )


def verify_clawpack_tarball(
    blob: bytes,
    *,
    expected_name: str,
    expected_version: str,
    expected_identity: Optional[ArtifactIdentity] = None,
) -> IdentityVerificationResult:
    """Verify a ClawPack tarball's identity AND its internal manifest.

    Computes the actual :class:`ArtifactIdentity`, compares it to
    ``expected_identity`` (when supplied), then parses
    ``package/package.json`` and confirms the embedded ``name`` +
    ``version`` match ``expected_name`` + ``expected_version``.

    Returns an :class:`IdentityVerificationResult` with internal-
    manifest mismatches surfaced as extra :class:`IdentityMismatch`
    rows under the synthetic ``manifest_name`` / ``manifest_version``
    field names.

    Raises :class:`ClawPackParseError` when the tarball is
    structurally invalid (the catalog's fail-closed contract: a
    refused parse is preferred to silently accepting an unparseable
    artifact).
    """
    actual = compute_identity(blob)
    identity_result = (
        verify_identity(
            actual,
            expected_sha256_hex=expected_identity.sha256_hex if expected_identity else None,
            expected_sha512_sri=expected_identity.sha512_sri if expected_identity else None,
            expected_sha1_shasum=expected_identity.sha1_shasum if expected_identity else None,
            expected_byte_length=expected_identity.byte_length if expected_identity else None,
        )
        if expected_identity is not None
        else IdentityVerificationResult(ok=True, compared_fields=())
    )

    contents = parse_clawpack_contents(blob)
    extra_mismatches: list[IdentityMismatch] = []
    extra_compared: list[str] = ["manifest_name", "manifest_version"]
    if contents.name != expected_name:
        extra_mismatches.append(
            IdentityMismatch(
                field="manifest_name",
                actual=contents.name,
                expected=expected_name,
            )
        )
    if contents.version != expected_version:
        extra_mismatches.append(
            IdentityMismatch(
                field="manifest_version",
                actual=contents.version,
                expected=expected_version,
            )
        )

    combined_mismatches = identity_result.mismatches + tuple(extra_mismatches)
    combined_compared = identity_result.compared_fields + tuple(extra_compared)
    return IdentityVerificationResult(
        ok=not combined_mismatches,
        mismatches=combined_mismatches,
        compared_fields=combined_compared,
    )


# ---------------------------------------------------------------------------
# TOFU pin file


@dataclass(frozen=True)
class PinnedDigest:
    """One row in the trust-pin file.

    Fields:
        identifier: caller-supplied key. Convention: a stable
            string like ``"github:owner/repo@v1.2.3"`` or
            ``"voicepack:kenning"``.
        sha256_hex: pinned SHA-256.
        sha512_sri: pinned SHA-512 SRI.
        sha1_shasum: pinned SHA-1.
        byte_length: pinned byte length.
        pinned_at_iso: ISO-8601 timestamp of when the pin was written.
        notes: free-form annotation (optional).
    """

    identifier: str
    sha256_hex: str
    sha512_sri: str
    sha1_shasum: str
    byte_length: int
    pinned_at_iso: str = ""
    notes: str = ""


def _atomic_append_jsonl(path: Path, row: Mapping[str, object]) -> None:
    """Append ``row`` to ``path`` as one JSON line. Creates parent on demand."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def pin_first_use_digests(
    identity: ArtifactIdentity,
    identifier: str,
    *,
    pin_file: Path,
    notes: str = "",
    now: Optional[datetime] = None,
) -> PinnedDigest:
    """Record ``identity`` as the trust pin for ``identifier``.

    Subsequent :func:`load_pinned_digest` calls return the recorded
    digests so :func:`verify_identity` can compare and refuse
    swap-on-rotate attempts.

    ``now`` may be supplied for deterministic tests. Identifier is
    a freeform string the caller chooses (one convention:
    ``"<scheme>:<spec>"`` so multiple kinds coexist in one pin
    file).
    """
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    pinned = PinnedDigest(
        identifier=identifier,
        sha256_hex=identity.sha256_hex,
        sha512_sri=identity.sha512_sri,
        sha1_shasum=identity.sha1_shasum,
        byte_length=identity.byte_length,
        pinned_at_iso=timestamp,
        notes=notes,
    )
    row = {
        "identifier": pinned.identifier,
        "sha256_hex": pinned.sha256_hex,
        "sha512_sri": pinned.sha512_sri,
        "sha1_shasum": pinned.sha1_shasum,
        "byte_length": pinned.byte_length,
        "pinned_at": pinned.pinned_at_iso,
        "notes": pinned.notes,
    }
    _atomic_append_jsonl(pin_file, row)
    return pinned


def load_pinned_digest(identifier: str, *, pin_file: Path) -> Optional[PinnedDigest]:
    """Return the most recent :class:`PinnedDigest` for ``identifier``.

    The pin file is JSONL append-only; later rows for the same
    identifier supersede earlier ones (the caller decides whether
    rotation is permitted -- this is purely the lookup primitive).
    """
    if not pin_file.is_file():
        return None
    latest: Optional[PinnedDigest] = None
    try:
        with pin_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError:
                    LOGGER.warning("Skipping malformed pin row in %s", pin_file)
                    continue
                if not isinstance(row, dict):
                    continue
                if str(row.get("identifier") or "") != identifier:
                    continue
                try:
                    latest = PinnedDigest(
                        identifier=str(row["identifier"]),
                        sha256_hex=str(row["sha256_hex"]),
                        sha512_sri=str(row["sha512_sri"]),
                        sha1_shasum=str(row["sha1_shasum"]),
                        byte_length=int(row["byte_length"]),
                        pinned_at_iso=str(row.get("pinned_at", "")),
                        notes=str(row.get("notes", "")),
                    )
                except (KeyError, ValueError, TypeError):
                    continue
    except OSError as exc:
        LOGGER.warning("Cannot read pin file %s: %s", pin_file, exc)
        return None
    return latest


def verify_against_pin(
    identity: ArtifactIdentity,
    identifier: str,
    *,
    pin_file: Path,
) -> IdentityVerificationResult:
    """Convenience: load pin for ``identifier`` and verify ``identity``.

    When no pin row exists for the identifier, returns
    ``IdentityVerificationResult(ok=True, compared_fields=())`` --
    caller should treat zero compared fields as "no pin recorded
    yet" and decide whether to pin on first use.
    """
    pin = load_pinned_digest(identifier, pin_file=pin_file)
    if pin is None:
        return IdentityVerificationResult(ok=True, compared_fields=())
    return verify_identity(
        identity,
        expected_sha256_hex=pin.sha256_hex,
        expected_sha512_sri=pin.sha512_sri,
        expected_sha1_shasum=pin.sha1_shasum,
        expected_byte_length=pin.byte_length,
    )


__all__ = [
    "SRI_SHA512_PREFIX",
    "DEFAULT_PIN_FILE_RELATIVE",
    "ArtifactIdentity",
    "IdentityMismatch",
    "IdentityVerificationResult",
    "ClawPackContents",
    "ClawPackParseError",
    "PinnedDigest",
    "compute_sha256_hex",
    "compute_sha1_shasum",
    "compute_sha512_sri",
    "compute_identity",
    "compute_identity_from_path",
    "verify_identity",
    "parse_clawpack_contents",
    "verify_clawpack_tarball",
    "pin_first_use_digests",
    "load_pinned_digest",
    "verify_against_pin",
]
