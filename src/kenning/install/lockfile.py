"""Lockfile + per-skill origin manifest with content fingerprinting (T10).

T10 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Closes the "did anyone edit this skill since install?" gap. Every
install writes two files:

1. **Lockfile** at ``<workdir>/.kenning/lock.json`` — the workdir-scoped
   "what's currently installed" registry. Keyed by slug; each entry
   carries ``version``, ``installedAt`` (Unix milliseconds), and the
   optional T11 ``pinned`` / ``pinReason`` fields.
2. **Per-skill origin manifest** at
   ``<skill_dir>/.kenning/origin.json`` — the skill-self-attestation:
   where did I come from, what version did I install as, what content
   fingerprint did I have. Used for drift detection: at load time the
   registry recomputes the fingerprint and compares to the origin; a
   mismatch flags the skill as ``tampered`` and the safety validator
   refuses to blindly re-inject its body into the LLM system prompt.

Both files are versioned (``version: 1``). Writes are atomic via
``tmp -> os.replace`` so a crash mid-write can't leave a partially
written file. Read paths return a default empty lockfile when the
file is absent rather than raising, so callers don't need a separate
"first-install" branch.

Content fingerprint algorithm (matches the upstream pattern):

1. Walk the skill directory; collect every text file. Skip
   ``.git/``, ``.kenning/``, ``node_modules/``, ``.venv/``,
   ``__pycache__/``, hidden files (``.foo``), and known binary
   extensions.
2. For each surviving file, compute ``sha256(bytes)``.
3. Build a list of ``(path, sha256)`` tuples sorted by path under a
   case-insensitive comparison. The canonical payload is the lines
   ``"<rel-path>:<sha256-hex>"`` joined by ``"\n"``.
4. The fingerprint is ``sha256(payload).hexdigest()``.

This module is pure data + pure IO. No catalog logic; callers
(:mod:`kenning.skills.registry`, the future install scanner, the
voice-baseline-lock guard at orchestrator startup) compose the
helpers without touching the underlying schema.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional

LOGGER = logging.getLogger(__name__)

#: Schema version for both lockfile + origin manifest. Bumped only
#: when the on-disk shape changes incompatibly.
LOCKFILE_SCHEMA_VERSION: int = 1

#: Directory name carrying kenning-managed install state. Sibling to
#: any upstream ``.clawhub/`` / ``.clawdhub/`` directories which we
#: do NOT consume (kenning runs its own state).
KENNING_STATE_DIRNAME: str = ".kenning"

#: Filename for the workdir-scoped lockfile.
LOCKFILE_NAME: str = "lock.json"

#: Filename for the per-skill origin manifest.
ORIGIN_NAME: str = "origin.json"

#: Directory names skipped during content-fingerprint walks.
_FINGERPRINT_SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    ".hg",
    ".svn",
    ".kenning",
    ".clawhub",
    ".clawdhub",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "dist",
    "build",
})

#: File extensions skipped during content-fingerprint walks. These
#: are well-known binary blobs whose contents are deterministic
#: enough that drift detection is better served by file-listing
#: presence checks (caught by the path:sha256 layer) than by raw
#: SHA-256.
_FINGERPRINT_BINARY_SUFFIXES: frozenset[str] = frozenset({
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".gguf",
    ".pth",
    ".pt",
    ".onnx",
    ".bin",
    ".zip",
    ".gz",
    ".tar",
    ".tgz",
    ".7z",
    ".whl",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".webm",
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
})

#: First-bytes peek to detect "actually a binary even though the
#: extension is text-shaped". A NUL byte in the first 4 KB is the
#: load-bearing heuristic.
_BINARY_PEEK_BYTES: int = 4096


@dataclass(frozen=True)
class LockfileEntry:
    """One row in the lockfile keyed by ``slug``.

    Fields:
        version: installed version string. May be the empty string
            when the source had no explicit version (e.g. a local
            development path).
        installed_at: Unix-epoch *milliseconds* when the install
            landed. Matches the upstream serialisation so audit
            consumers can compare across ecosystems.
        pinned: True when the entry is pinned (T11). Pinned entries
            refuse update / force-overwrite operations.
        pin_reason: Free-form text shown in dashboards + voice ack
            ("voice baseline anchor; do not auto-update."). Stored
            only when ``pinned=True``; defaults to None.
    """

    version: str = ""
    installed_at: int = 0
    pinned: bool = False
    pin_reason: Optional[str] = None

    def to_json_dict(self) -> dict[str, object]:
        """Return the dict shape serialised to disk.

        Omits ``pinned`` / ``pin_reason`` when not set so the JSON
        stays compact and matches the upstream omit-when-absent
        convention.
        """
        out: dict[str, object] = {
            "version": self.version,
            "installedAt": self.installed_at,
        }
        if self.pinned:
            out["pinned"] = True
            if self.pin_reason:
                out["pinReason"] = self.pin_reason
        return out

    @classmethod
    def from_json_dict(cls, raw: Mapping[str, object]) -> "LockfileEntry":
        """Construct from the on-disk dict shape (with fail-open defaults)."""
        version = str(raw.get("version") or "")
        installed_at = _to_int(raw.get("installedAt"), default=0)
        pinned = bool(raw.get("pinned"))
        pin_reason = raw.get("pinReason")
        pin_reason_str = str(pin_reason) if pin_reason else None
        return cls(
            version=version,
            installed_at=installed_at,
            pinned=pinned,
            pin_reason=pin_reason_str if pinned else None,
        )


@dataclass(frozen=True)
class Lockfile:
    """Workdir-scoped lockfile.

    Fields:
        version: schema version (currently 1).
        skills: per-slug entries.
    """

    version: int = LOCKFILE_SCHEMA_VERSION
    skills: Mapping[str, LockfileEntry] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        """Return the dict shape serialised to disk."""
        return {
            "version": self.version,
            "skills": {
                slug: entry.to_json_dict() for slug, entry in self.skills.items()
            },
        }

    @classmethod
    def from_json_dict(cls, raw: Mapping[str, object]) -> "Lockfile":
        """Construct from the on-disk dict shape (with fail-open defaults)."""
        version = _to_int(raw.get("version"), default=LOCKFILE_SCHEMA_VERSION)
        raw_skills = raw.get("skills") or {}
        skills: dict[str, LockfileEntry] = {}
        if isinstance(raw_skills, Mapping):
            for slug, entry_raw in raw_skills.items():
                if not isinstance(entry_raw, Mapping):
                    continue
                skills[str(slug)] = LockfileEntry.from_json_dict(entry_raw)
        return cls(version=version, skills=skills)

    def with_entry(self, slug: str, entry: LockfileEntry) -> "Lockfile":
        """Return a copy with ``slug`` updated to ``entry``."""
        new_skills = dict(self.skills)
        new_skills[slug] = entry
        return Lockfile(version=self.version, skills=new_skills)

    def without_slug(self, slug: str) -> "Lockfile":
        """Return a copy with ``slug`` removed (no-op when absent)."""
        if slug not in self.skills:
            return self
        new_skills = dict(self.skills)
        new_skills.pop(slug)
        return Lockfile(version=self.version, skills=new_skills)

    def entry(self, slug: str) -> Optional[LockfileEntry]:
        """Return the entry for ``slug`` or None."""
        return self.skills.get(slug)


@dataclass(frozen=True)
class SkillOrigin:
    """Per-skill origin manifest written at install time.

    Fields:
        version: schema version (currently 1).
        registry: human-readable identifier for the install source
            (e.g. ``"github:owner/repo@v1.2.3"`` or
            ``"path:/local/dev/skills"``).
        slug: the canonical slug the skill was installed under.
        installed_version: exact version installed (may be empty for
            untagged sources).
        installed_at: Unix-epoch *milliseconds* when the install
            landed.
        fingerprint: SHA-256 hex digest of the canonical content
            fingerprint payload. None when the install code didn't
            compute one (legacy installs).
    """

    version: int = LOCKFILE_SCHEMA_VERSION
    registry: str = ""
    slug: str = ""
    installed_version: str = ""
    installed_at: int = 0
    fingerprint: Optional[str] = None

    def to_json_dict(self) -> dict[str, object]:
        """Return the dict shape serialised to disk."""
        out: dict[str, object] = {
            "version": self.version,
            "registry": self.registry,
            "slug": self.slug,
            "installedVersion": self.installed_version,
            "installedAt": self.installed_at,
        }
        if self.fingerprint:
            out["fingerprint"] = self.fingerprint
        return out

    @classmethod
    def from_json_dict(cls, raw: Mapping[str, object]) -> "SkillOrigin":
        """Construct from the on-disk dict shape."""
        version = _to_int(raw.get("version"), default=LOCKFILE_SCHEMA_VERSION)
        fingerprint = raw.get("fingerprint")
        return cls(
            version=version,
            registry=str(raw.get("registry") or ""),
            slug=str(raw.get("slug") or ""),
            installed_version=str(raw.get("installedVersion") or ""),
            installed_at=_to_int(raw.get("installedAt"), default=0),
            fingerprint=str(fingerprint) if fingerprint else None,
        )


# ---------------------------------------------------------------------------
# Path resolution


def workdir_lockfile_path(workdir: Path) -> Path:
    """Return the canonical lockfile path under ``<workdir>/.kenning/``."""
    return Path(workdir) / KENNING_STATE_DIRNAME / LOCKFILE_NAME


def skill_origin_path(skill_dir: Path) -> Path:
    """Return the canonical origin manifest path under ``<skill_dir>/.kenning/``."""
    return Path(skill_dir) / KENNING_STATE_DIRNAME / ORIGIN_NAME


# ---------------------------------------------------------------------------
# Atomic disk operations


def _atomic_write_json(path: Path, data: object) -> None:
    """Write ``data`` to ``path`` atomically (tmp + ``os.replace``).

    Always trailing-newline'd; pretty-printed with 2-space indent so
    diffs read cleanly. The parent directory is created on demand.
    """
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_path = parent / f"{path.name}.tmp"
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    tmp_path.write_text(payload + "\n", encoding="utf-8")
    os.replace(str(tmp_path), str(path))


def _safe_read_json(path: Path) -> Optional[dict]:
    """Return the parsed JSON object at ``path``, or None on absence / error.

    Errors log at WARN and the function returns None so callers fall
    back to default-empty state. Matches the upstream fail-open
    contract.
    """
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("Cannot read lockfile-shaped file %s: %s", path, exc)
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        LOGGER.warning("Malformed JSON in %s: %s", path, exc)
        return None
    if not isinstance(parsed, dict):
        LOGGER.warning("Expected JSON object at top of %s, got %s", path, type(parsed))
        return None
    return parsed


def _to_int(value: object, *, default: int) -> int:
    """Parse an int from a JSON value with ``default`` fallback on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Lockfile read / write


def read_lockfile(workdir: Path) -> Lockfile:
    """Return the lockfile at ``<workdir>/.kenning/lock.json`` (default if absent).

    Fail-open: malformed / unreadable files return a default-empty
    lockfile and log WARN. Callers don't need to special-case
    first-install.
    """
    path = workdir_lockfile_path(workdir)
    raw = _safe_read_json(path)
    if raw is None:
        return Lockfile()
    return Lockfile.from_json_dict(raw)


def write_lockfile(workdir: Path, lockfile: Lockfile) -> Path:
    """Persist ``lockfile`` atomically. Returns the written path."""
    path = workdir_lockfile_path(workdir)
    _atomic_write_json(path, lockfile.to_json_dict())
    return path


# ---------------------------------------------------------------------------
# SkillOrigin read / write


def read_origin(skill_dir: Path) -> Optional[SkillOrigin]:
    """Return the origin manifest for ``skill_dir`` (None if absent)."""
    path = skill_origin_path(skill_dir)
    raw = _safe_read_json(path)
    if raw is None:
        return None
    return SkillOrigin.from_json_dict(raw)


def write_origin(skill_dir: Path, origin: SkillOrigin) -> Path:
    """Persist ``origin`` atomically. Returns the written path."""
    path = skill_origin_path(skill_dir)
    _atomic_write_json(path, origin.to_json_dict())
    return path


# ---------------------------------------------------------------------------
# Content fingerprint


def is_likely_text_file(path: Path) -> bool:
    """Return True iff ``path`` is plausibly a text file worth hashing.

    Combines a suffix-allowlist (cheap) with a first-bytes NUL-byte
    peek (catches mis-extension-d binaries). Returns False on read
    errors so the walker silently skips unreadable files rather than
    blowing up.
    """
    suffix = path.suffix.lower()
    if suffix in _FINGERPRINT_BINARY_SUFFIXES:
        return False
    try:
        with path.open("rb") as handle:
            peek = handle.read(_BINARY_PEEK_BYTES)
    except OSError:
        return False
    if b"\x00" in peek:
        return False
    return True


def iter_text_files(root: Path) -> Iterable[Path]:
    """Yield every text file under ``root`` in deterministic order.

    Skips the directory blocklist (``.git``, ``.kenning``,
    ``node_modules``, etc.), hidden filenames (``.foo``), and
    suspected binaries (via :func:`is_likely_text_file`).
    """
    root = Path(root)
    if not root.is_dir():
        return
    # rglob walks in os-dependent order; sort for determinism.
    candidates = sorted(
        root.rglob("*"),
        key=lambda p: str(p).casefold(),
    )
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
        except OSError:
            continue
        # Skip if any path part is in the blocklist or hidden.
        rel = candidate.relative_to(root)
        parts = rel.parts
        if any(part in _FINGERPRINT_SKIP_DIRS for part in parts[:-1]):
            continue
        # Hidden files (.foo) or any hidden directory along the path.
        if any(part.startswith(".") for part in parts):
            continue
        if not is_likely_text_file(candidate):
            continue
        yield candidate


def compute_file_sha256(path: Path) -> str:
    """Return hex SHA-256 of ``path`` bytes.

    Streamed in 64 KB chunks so large files don't blow up RAM.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_skill_fingerprint(root: Path) -> str:
    """Return the canonical content fingerprint for ``root``.

    Implementation steps:

    1. Walk via :func:`iter_text_files`.
    2. Compute per-file SHA-256.
    3. Build ``(rel-path, sha256)`` tuples; sort by rel-path under
       case-insensitive comparison (so case-insensitive filesystems
       produce stable output).
    4. Canonical payload is lines ``"<rel>:<hash>"`` joined by ``\n``
       (rel uses forward slashes to avoid Windows-vs-POSIX drift).
    5. Return SHA-256 of the canonical payload.

    Empty directory -> SHA-256 of the empty string. Matches the
    upstream pattern verbatim.
    """
    root = Path(root)
    rows: list[str] = []
    for file_path in iter_text_files(root):
        rel = file_path.relative_to(root).as_posix()
        sha = compute_file_sha256(file_path)
        rows.append(f"{rel}:{sha}")
    rows.sort(key=str.casefold)
    payload = "\n".join(rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_drift(skill_dir: Path) -> "FingerprintDriftReport":
    """Return a structured drift report for ``skill_dir``.

    The report compares the recorded :class:`SkillOrigin` fingerprint
    to a freshly computed one. ``status`` resolves to:

    * ``"clean"`` — origin present, fingerprint matches.
    * ``"drifted"`` — origin present, fingerprint mismatch.
    * ``"missing_origin"`` — no origin manifest on disk.
    * ``"legacy_origin"`` — origin present without a recorded
      fingerprint field (older installs).
    """
    skill_dir = Path(skill_dir)
    origin = read_origin(skill_dir)
    current = compute_skill_fingerprint(skill_dir)
    if origin is None:
        return FingerprintDriftReport(
            status="missing_origin",
            current=current,
            recorded=None,
            skill_dir=skill_dir,
        )
    if not origin.fingerprint:
        return FingerprintDriftReport(
            status="legacy_origin",
            current=current,
            recorded=None,
            skill_dir=skill_dir,
        )
    if origin.fingerprint == current:
        return FingerprintDriftReport(
            status="clean",
            current=current,
            recorded=origin.fingerprint,
            skill_dir=skill_dir,
        )
    return FingerprintDriftReport(
        status="drifted",
        current=current,
        recorded=origin.fingerprint,
        skill_dir=skill_dir,
    )


@dataclass(frozen=True)
class FingerprintDriftReport:
    """Result of :func:`check_drift`.

    Fields:
        status: one of ``"clean"`` / ``"drifted"`` / ``"missing_origin"``
            / ``"legacy_origin"``.
        current: freshly computed fingerprint.
        recorded: fingerprint from the origin manifest (None for
            ``missing_origin`` / ``legacy_origin``).
        skill_dir: the directory inspected.
    """

    status: str
    current: str
    recorded: Optional[str]
    skill_dir: Path

    @property
    def is_drifted(self) -> bool:
        """True only when ``status == "drifted"`` (manifests with no
        recorded fingerprint don't count as drift)."""
        return self.status == "drifted"


__all__ = [
    "LOCKFILE_SCHEMA_VERSION",
    "KENNING_STATE_DIRNAME",
    "LOCKFILE_NAME",
    "ORIGIN_NAME",
    "LockfileEntry",
    "Lockfile",
    "SkillOrigin",
    "FingerprintDriftReport",
    "workdir_lockfile_path",
    "skill_origin_path",
    "read_lockfile",
    "write_lockfile",
    "read_origin",
    "write_origin",
    "is_likely_text_file",
    "iter_text_files",
    "compute_file_sha256",
    "compute_skill_fingerprint",
    "check_drift",
]
