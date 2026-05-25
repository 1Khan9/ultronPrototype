"""Tests for ``ultron.install.voice_baseline_verify``.

Validates the wired-at-startup T2 artifact-identity verification:

* First-run TOFU pin: missing pin records the on-disk digest.
* Second-run verification: pin exists, on-disk matches -> ``verified``.
* Tampered file: pin exists, on-disk mismatches -> ``mismatch``.
* Optional artifact missing: ``status="missing"`` with info detail
  (no required-missing flag).
* Required artifact missing: ``status="missing"`` with required
  detail.
* Async path: thread runs to completion; report mutated in place;
  ``on_complete`` callback fires.

Tests run hermetically — every path goes through ``tmp_path`` so
no real ``data/install/pinned_digests.jsonl`` is touched. No
voice-stack loading (R11).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ultron.install.voice_baseline_verify import (
    ArtifactVerificationOutcome,
    VerificationReport,
    VoiceBaselineArtifact,
    default_voice_baseline_artifacts,
    summarise_report,
    verify_voice_baseline_artifacts,
    verify_voice_baseline_artifacts_async,
)


def _make_artifact(tmp_path: Path, *, name: str, content: bytes,
                   required: bool = True) -> VoiceBaselineArtifact:
    target = tmp_path / "models" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return VoiceBaselineArtifact(
        identifier=f"voice_baseline:test:{name}",
        path=target,
        required=required,
        notes=f"test artifact {name}",
    )


def test_first_run_tofu_records_pin(tmp_path):
    artifact = _make_artifact(tmp_path, name="llm.bin", content=b"hello world")
    pin_file = tmp_path / "pin.jsonl"

    report = verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )

    assert report.is_complete
    assert len(report.outcomes) == 1
    outcome = report.outcomes[0]
    assert outcome.status == "pinned"
    assert outcome.sha256_hex is not None
    # Pin file now exists + has one row.
    assert pin_file.is_file()
    rows = pin_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(rows) == 1
    assert artifact.identifier in rows[0]


def test_second_run_verifies_against_pin(tmp_path):
    artifact = _make_artifact(tmp_path, name="llm.bin", content=b"hello world")
    pin_file = tmp_path / "pin.jsonl"

    # First run: records pin.
    verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    # Second run: verifies against pin.
    report = verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    assert report.outcomes[0].status == "verified"
    assert not report.mismatches


def test_tampered_file_produces_mismatch(tmp_path):
    artifact = _make_artifact(tmp_path, name="llm.bin", content=b"hello world")
    pin_file = tmp_path / "pin.jsonl"

    verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    # Tamper with file (different bytes).
    artifact.path.write_bytes(b"TAMPERED")

    report = verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    assert report.outcomes[0].status == "mismatch"
    assert report.mismatches
    assert "pinned=" in report.outcomes[0].detail


def test_missing_required_artifact_status(tmp_path):
    artifact = VoiceBaselineArtifact(
        identifier="voice_baseline:test:absent",
        path=tmp_path / "does-not-exist.gguf",
        required=True,
    )
    pin_file = tmp_path / "pin.jsonl"

    report = verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    outcome = report.outcomes[0]
    assert outcome.status == "missing"
    assert "required" in outcome.detail
    assert report.missing_required == [outcome]


def test_missing_optional_artifact_status(tmp_path):
    artifact = VoiceBaselineArtifact(
        identifier="voice_baseline:test:optional",
        path=tmp_path / "missing-optional.onnx",
        required=False,
    )
    pin_file = tmp_path / "pin.jsonl"

    report = verify_voice_baseline_artifacts(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    outcome = report.outcomes[0]
    assert outcome.status == "missing"
    assert "optional" in outcome.detail
    assert not report.missing_required  # optional missing does NOT escalate


def test_no_pin_on_first_use_when_disabled(tmp_path):
    artifact = _make_artifact(tmp_path, name="llm.bin", content=b"x")
    pin_file = tmp_path / "pin.jsonl"

    report = verify_voice_baseline_artifacts(
        tmp_path,
        artifacts=[artifact],
        pin_file=pin_file,
        pin_on_first_use=False,
    )
    assert report.outcomes[0].status == "missing"
    assert "no pin recorded" in report.outcomes[0].detail
    assert not pin_file.exists()


def test_async_path_completes_and_invokes_callback(tmp_path):
    artifact = _make_artifact(tmp_path, name="llm.bin", content=b"async-ok")
    pin_file = tmp_path / "pin.jsonl"
    callback_seen = threading.Event()
    captured = {}

    def _cb(report: VerificationReport) -> None:
        captured["report"] = report
        callback_seen.set()

    report, thread = verify_voice_baseline_artifacts_async(
        tmp_path,
        artifacts=[artifact],
        pin_file=pin_file,
        on_complete=_cb,
    )
    try:
        thread.join(timeout=5.0)
    finally:
        # Defensive: never let a thread leak out of the test (R2).
        if thread.is_alive():
            pytest.fail("verify_voice_baseline_artifacts_async thread leaked")

    assert callback_seen.wait(timeout=2.0)
    assert report.is_complete
    assert captured["report"] is report
    assert report.outcomes[0].status == "pinned"


def test_summarise_report_renders_counts(tmp_path):
    a = _make_artifact(tmp_path, name="ok.bin", content=b"good")
    b = VoiceBaselineArtifact(
        identifier="voice_baseline:test:gone",
        path=tmp_path / "gone.bin",
        required=False,
    )
    pin_file = tmp_path / "pin.jsonl"

    report = verify_voice_baseline_artifacts(
        tmp_path, artifacts=[a, b], pin_file=pin_file,
    )
    summary = summarise_report(report)
    assert "pinned=1" in summary
    assert "missing=1" in summary


def test_default_artifacts_resolves_project_paths(tmp_path):
    artifacts = default_voice_baseline_artifacts(tmp_path)
    assert len(artifacts) == 6
    paths = [a.path for a in artifacts]
    # All paths anchored to the supplied project_root.
    assert all(str(p).startswith(str(tmp_path)) for p in paths)
    # Voicepack + LLM + fine-tune + wake-word are REQUIRED;
    # draft + smart-turn are optional.
    required_ids = [a.identifier for a in artifacts if a.required]
    optional_ids = [a.identifier for a in artifacts if not a.required]
    assert "voice_baseline:llm:qwen3.5-4b" in required_ids
    assert "voice_baseline:voicepack:ultron" in required_ids
    assert "voice_baseline:voicepack:kokoro_finetune" in required_ids
    assert "voice_baseline:wake_word:ultron" in required_ids
    assert "voice_baseline:llm:qwen3.5-0.8b-draft" in optional_ids
    assert "voice_baseline:smart_turn:v3" in optional_ids


def test_async_swallows_pin_io_error(tmp_path, monkeypatch):
    """Pin-file IO errors must not crash the thread."""
    artifact = _make_artifact(tmp_path, name="llm.bin", content=b"ok")
    pin_file = tmp_path / "broken_dir" / "pin.jsonl"
    pin_file.parent.mkdir(parents=True, exist_ok=True)

    # Force the pin-file append helper to raise.
    import ultron.install.artifact_identity as ai

    def _boom(*a, **kw):
        raise OSError("simulated IO failure")

    monkeypatch.setattr(ai, "_atomic_append_jsonl", _boom)

    report, thread = verify_voice_baseline_artifacts_async(
        tmp_path, artifacts=[artifact], pin_file=pin_file,
    )
    thread.join(timeout=5.0)
    assert report.is_complete
    # Outcome must be present (not lost to the exception).
    assert len(report.outcomes) == 1
    assert report.outcomes[0].status in ("error", "pinned")
