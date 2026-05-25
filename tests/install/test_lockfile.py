"""Tests for the T10 lockfile + per-skill origin manifest + content fingerprint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ultron.install.lockfile import (
    LOCKFILE_NAME,
    LOCKFILE_SCHEMA_VERSION,
    ORIGIN_NAME,
    ULTRON_STATE_DIRNAME,
    FingerprintDriftReport,
    Lockfile,
    LockfileEntry,
    SkillOrigin,
    check_drift,
    compute_file_sha256,
    compute_skill_fingerprint,
    is_likely_text_file,
    iter_text_files,
    read_lockfile,
    read_origin,
    skill_origin_path,
    workdir_lockfile_path,
    write_lockfile,
    write_origin,
)


# ---------------------------------------------------------------------------
# Path resolution


def test_workdir_lockfile_path_uses_ultron_dir(tmp_path: Path) -> None:
    path = workdir_lockfile_path(tmp_path)
    assert path == tmp_path / ULTRON_STATE_DIRNAME / LOCKFILE_NAME


def test_skill_origin_path_uses_ultron_dir(tmp_path: Path) -> None:
    skill = tmp_path / "my-skill"
    path = skill_origin_path(skill)
    assert path == skill / ULTRON_STATE_DIRNAME / ORIGIN_NAME


# ---------------------------------------------------------------------------
# LockfileEntry round-trip


def test_lockfile_entry_default_round_trip() -> None:
    entry = LockfileEntry()
    out = entry.to_json_dict()
    assert "pinned" not in out
    assert "pinReason" not in out
    assert out["version"] == ""
    restored = LockfileEntry.from_json_dict(out)
    assert restored == entry


def test_lockfile_entry_pinned_round_trip() -> None:
    entry = LockfileEntry(
        version="1.2.3",
        installed_at=1_700_000_000_000,
        pinned=True,
        pin_reason="frozen for prod",
    )
    out = entry.to_json_dict()
    assert out["pinned"] is True
    assert out["pinReason"] == "frozen for prod"
    restored = LockfileEntry.from_json_dict(out)
    assert restored == entry


def test_lockfile_entry_pinned_without_reason_round_trip() -> None:
    entry = LockfileEntry(version="1.0.0", pinned=True, pin_reason=None)
    out = entry.to_json_dict()
    assert out["pinned"] is True
    assert "pinReason" not in out
    restored = LockfileEntry.from_json_dict(out)
    assert restored == entry


def test_lockfile_entry_unpinned_ignores_reason_on_load() -> None:
    raw = {"version": "1", "installedAt": 0, "pinReason": "ghost reason"}
    restored = LockfileEntry.from_json_dict(raw)
    assert restored.pinned is False
    assert restored.pin_reason is None


# ---------------------------------------------------------------------------
# Lockfile round-trip


def test_lockfile_default_is_empty() -> None:
    lf = Lockfile()
    assert lf.version == LOCKFILE_SCHEMA_VERSION
    assert lf.skills == {}


def test_lockfile_read_empty_returns_default(tmp_path: Path) -> None:
    lf = read_lockfile(tmp_path)
    assert lf == Lockfile()


def test_lockfile_write_then_read_round_trip(tmp_path: Path) -> None:
    lf = Lockfile(
        skills={
            "alpha": LockfileEntry(version="1.0.0", installed_at=1_000),
            "beta": LockfileEntry(
                version="2.0.0",
                installed_at=2_000,
                pinned=True,
                pin_reason="prod",
            ),
        }
    )
    write_lockfile(tmp_path, lf)
    restored = read_lockfile(tmp_path)
    assert restored == lf


def test_lockfile_malformed_returns_default(tmp_path: Path) -> None:
    path = workdir_lockfile_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert read_lockfile(tmp_path) == Lockfile()


def test_lockfile_write_creates_state_dir(tmp_path: Path) -> None:
    write_lockfile(tmp_path, Lockfile())
    assert (tmp_path / ULTRON_STATE_DIRNAME).is_dir()
    assert (tmp_path / ULTRON_STATE_DIRNAME / LOCKFILE_NAME).is_file()


def test_lockfile_atomic_no_partial_artifact(tmp_path: Path) -> None:
    write_lockfile(tmp_path, Lockfile(skills={"x": LockfileEntry(version="1")}))
    state_dir = tmp_path / ULTRON_STATE_DIRNAME
    leftover = [p for p in state_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []


def test_lockfile_with_entry_returns_new_instance() -> None:
    lf = Lockfile(skills={"a": LockfileEntry(version="1")})
    next_lf = lf.with_entry("b", LockfileEntry(version="2"))
    assert "b" not in lf.skills
    assert next_lf.skills["b"].version == "2"
    assert next_lf.skills["a"].version == "1"


def test_lockfile_without_slug_idempotent_when_absent() -> None:
    lf = Lockfile(skills={"a": LockfileEntry(version="1")})
    assert lf.without_slug("z") is lf  # short-circuit


def test_lockfile_entry_lookup() -> None:
    lf = Lockfile(skills={"a": LockfileEntry(version="1.0")})
    assert lf.entry("a") is not None
    assert lf.entry("nope") is None


# ---------------------------------------------------------------------------
# SkillOrigin round-trip


def test_skill_origin_round_trip(tmp_path: Path) -> None:
    skill = tmp_path / "my-skill"
    skill.mkdir()
    origin = SkillOrigin(
        registry="github:owner/repo@v1.0",
        slug="my-skill",
        installed_version="1.0.0",
        installed_at=1_700_000_000_000,
        fingerprint="abc123",
    )
    write_origin(skill, origin)
    restored = read_origin(skill)
    assert restored == origin


def test_skill_origin_missing_returns_none(tmp_path: Path) -> None:
    skill = tmp_path / "no-origin"
    skill.mkdir()
    assert read_origin(skill) is None


def test_skill_origin_without_fingerprint(tmp_path: Path) -> None:
    skill = tmp_path / "legacy-skill"
    skill.mkdir()
    origin = SkillOrigin(registry="path:/local", slug="legacy-skill")
    write_origin(skill, origin)
    out_path = skill_origin_path(skill)
    payload = json.loads(out_path.read_text())
    assert "fingerprint" not in payload
    restored = read_origin(skill)
    assert restored is not None
    assert restored.fingerprint is None


# ---------------------------------------------------------------------------
# Fingerprinting


def test_compute_file_sha256_matches_hashlib(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert compute_file_sha256(p) == expected


def test_is_likely_text_file_rejects_nul(tmp_path: Path) -> None:
    p = tmp_path / "blob.txt"
    p.write_bytes(b"abc\x00def")
    assert not is_likely_text_file(p)


def test_is_likely_text_file_rejects_binary_suffix(tmp_path: Path) -> None:
    p = tmp_path / "weights.gguf"
    p.write_text("totally text but extension says binary")
    assert not is_likely_text_file(p)


def test_is_likely_text_file_accepts_plain_text(tmp_path: Path) -> None:
    p = tmp_path / "skill.md"
    p.write_text("# heading\nbody")
    assert is_likely_text_file(p)


def test_iter_text_files_skips_blocked_dirs(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    (skill / ".ultron").mkdir(parents=True)
    (skill / ".git").mkdir()
    (skill / "node_modules").mkdir()
    (skill / "src").mkdir()
    (skill / ".ultron" / "origin.json").write_text("{}")
    (skill / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (skill / "node_modules" / "pkg.txt").write_text("dep")
    (skill / "src" / "main.py").write_text("print('hi')")
    (skill / "README.md").write_text("# readme")
    files = list(iter_text_files(skill))
    rel = {p.relative_to(skill).as_posix() for p in files}
    assert rel == {"src/main.py", "README.md"}


def test_iter_text_files_skips_hidden(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / ".env").write_text("SECRET=1")
    (skill / "README.md").write_text("# readme")
    files = list(iter_text_files(skill))
    rel = {p.relative_to(skill).as_posix() for p in files}
    assert rel == {"README.md"}


def test_fingerprint_deterministic(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    (skill / "b.py").write_text("beta")
    fp1 = compute_skill_fingerprint(skill)
    fp2 = compute_skill_fingerprint(skill)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_changes_on_edit(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    fp1 = compute_skill_fingerprint(skill)
    (skill / "a.md").write_text("alpha + delta")
    fp2 = compute_skill_fingerprint(skill)
    assert fp1 != fp2


def test_fingerprint_changes_on_new_file(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    fp1 = compute_skill_fingerprint(skill)
    (skill / "b.md").write_text("beta")
    fp2 = compute_skill_fingerprint(skill)
    assert fp1 != fp2


def test_fingerprint_changes_on_rename(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    fp1 = compute_skill_fingerprint(skill)
    (skill / "a.md").rename(skill / "renamed.md")
    fp2 = compute_skill_fingerprint(skill)
    assert fp1 != fp2


def test_fingerprint_empty_dir_is_stable(tmp_path: Path) -> None:
    skill = tmp_path / "empty-skill"
    skill.mkdir()
    fp = compute_skill_fingerprint(skill)
    # SHA-256 of the empty string
    assert fp == hashlib.sha256(b"").hexdigest()


def test_fingerprint_ignores_state_dir(tmp_path: Path) -> None:
    """Writing the origin manifest after a fingerprint must NOT change it."""
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    fp1 = compute_skill_fingerprint(skill)
    origin = SkillOrigin(registry="path:/local", slug="s", fingerprint=fp1)
    write_origin(skill, origin)
    fp2 = compute_skill_fingerprint(skill)
    assert fp1 == fp2


# ---------------------------------------------------------------------------
# check_drift


def test_check_drift_clean(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    fp = compute_skill_fingerprint(skill)
    write_origin(skill, SkillOrigin(registry="x", slug="s", fingerprint=fp))
    report = check_drift(skill)
    assert report.status == "clean"
    assert not report.is_drifted


def test_check_drift_detects_drift(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    fp = compute_skill_fingerprint(skill)
    write_origin(skill, SkillOrigin(registry="x", slug="s", fingerprint=fp))
    (skill / "a.md").write_text("alpha + tampered")
    report = check_drift(skill)
    assert report.status == "drifted"
    assert report.is_drifted


def test_check_drift_missing_origin(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    report = check_drift(skill)
    assert report.status == "missing_origin"
    assert not report.is_drifted


def test_check_drift_legacy_origin_without_fingerprint(tmp_path: Path) -> None:
    skill = tmp_path / "s"
    skill.mkdir()
    (skill / "a.md").write_text("alpha")
    write_origin(skill, SkillOrigin(registry="x", slug="s"))
    report = check_drift(skill)
    assert report.status == "legacy_origin"
    assert not report.is_drifted
