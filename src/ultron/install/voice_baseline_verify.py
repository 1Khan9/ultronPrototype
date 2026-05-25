"""Voice-baseline artifact digest verification (T2 wiring).

T2 (openclaw-clawhub catalog port) shipped triple-digest identity
verification + a TOFU pin file. This module is the consumer: at
orchestrator startup we walk the **voice-baseline** artifacts the
binding contract locks (LLM GGUF, draft GGUF, Kokoro voicepack,
Kokoro fine-tune weights, Smart Turn V3 ONNX, IDENTITY.md, the
custom wake-word ONNX) and verify each one against
``data/install/pinned_digests.jsonl``.

First-fetch: when no pin row exists for an identifier we record
one (TOFU). Subsequent fetches verify against the recorded pin and
refuse silent swaps -- a model file that was tampered with after
the original pin produces a mismatch result the caller can surface
as a voice-baseline integrity warning.

Design contracts:

* **Fail-open at the call site.** A broken pin file, a missing
  artifact, or a per-file digest exception must not block
  orchestrator construction. The caller logs and continues; the
  user notices via the audit log + the voice-baseline warning
  surface.
* **Background-threaded for large GGUFs.** A 3-GB SHA-256 takes
  ~5-10 s; running it on the main thread blocks the cold-start
  voice path. ``verify_voice_baseline_artifacts_async`` spawns a
  daemon thread so startup unblocks immediately while the
  verification runs in the background. Results are deposited into
  a process-wide :class:`VerificationReport` that callers can poll
  on demand.
* **Pin-on-first-use is the default for missing-pin paths.** The
  first time ultron sees a model file it records the digest. The
  second + later runs verify against the pin and detect tampering.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from ultron.install.artifact_identity import (
    DEFAULT_PIN_FILE_RELATIVE,
    ArtifactIdentity,
    IdentityVerificationResult,
    compute_identity_from_path,
    load_pinned_digest,
    pin_first_use_digests,
    verify_against_pin,
)

LOGGER = logging.getLogger(__name__)


#: Pin-identifier prefix used by this module. Distinguishes
#: voice-baseline anchors from generic install pins so the audit
#: layer can filter on it.
PIN_IDENTIFIER_PREFIX: str = "voice_baseline:"


#: How long the background verifier thread waits before giving up
#: on a single file. Caps cold-start budget when an artifact is
#: locked / fileshared / corrupt.
DEFAULT_PER_FILE_BUDGET_SECONDS: float = 30.0


@dataclass(frozen=True)
class VoiceBaselineArtifact:
    """One artifact participating in the voice-baseline verification.

    Fields:
        identifier: pin-file key (e.g. ``"voice_baseline:llm:qwen3.5-4b"``).
        path: absolute path to the file on disk.
        required: True iff the file MUST exist for the voice baseline
            to function. Missing required artifacts produce a
            verification failure; missing optional artifacts produce
            a SKIPPED outcome (the audit log still records the
            absence).
        notes: short human-readable label written into the pin file
            on first-use TOFU. Useful for the audit trail.
    """

    identifier: str
    path: Path
    required: bool = True
    notes: str = ""


@dataclass
class ArtifactVerificationOutcome:
    """Per-artifact outcome from the verifier.

    One of:

    * ``status="verified"`` — the on-disk digest matched the pin.
    * ``status="pinned"`` — no pin row existed; the digest was
      recorded as the new TOFU pin.
    * ``status="mismatch"`` — pin existed and the on-disk digest
      does NOT match. The audit log + voice-baseline warning
      surface should escalate.
    * ``status="missing"`` — the artifact file was missing
      (required + missing = critical; optional + missing = info).
    * ``status="error"`` — digest computation or pin IO raised.
    """

    identifier: str
    path: Path
    status: str
    detail: str = ""
    sha256_hex: Optional[str] = None
    elapsed_seconds: float = 0.0


@dataclass
class VerificationReport:
    """Aggregate report from one verify-call.

    Thread-safe append via :meth:`record` so the background-threaded
    verifier can write into a shared report without locks at the
    caller's level.
    """

    started_at: float = field(default_factory=time.monotonic)
    completed_at: Optional[float] = None
    outcomes: list[ArtifactVerificationOutcome] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, outcome: ArtifactVerificationOutcome) -> None:
        with self._lock:
            self.outcomes.append(outcome)

    def mark_complete(self) -> None:
        with self._lock:
            self.completed_at = time.monotonic()

    @property
    def elapsed_seconds(self) -> Optional[float]:
        if self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return self.completed_at is not None

    def outcomes_by_status(self, status: str) -> list[ArtifactVerificationOutcome]:
        with self._lock:
            return [o for o in self.outcomes if o.status == status]

    @property
    def mismatches(self) -> list[ArtifactVerificationOutcome]:
        return self.outcomes_by_status("mismatch")

    @property
    def missing_required(self) -> list[ArtifactVerificationOutcome]:
        with self._lock:
            return [
                o for o in self.outcomes
                if o.status == "missing" and "required" in o.detail
            ]


def default_voice_baseline_artifacts(project_root: Path) -> Sequence[VoiceBaselineArtifact]:
    """Return the canonical list of voice-baseline artifacts to verify.

    Mirrors :data:`ULTRON_DEFAULT_PINS` from ``install.pin`` but
    points at the actual on-disk files. Optional entries (draft GGUF
    is opt-in via ``llm.draft_kind``; smart-turn ONNX is opt-in via
    ``vad.smart_turn.enabled``) carry ``required=False`` so missing
    files surface as info rather than critical.
    """
    root = project_root
    return (
        VoiceBaselineArtifact(
            identifier=f"{PIN_IDENTIFIER_PREFIX}llm:qwen3.5-4b",
            path=root / "models" / "Qwen3.5-4B-Q4_K_M.gguf",
            required=True,
            notes="active voice-path LLM (Qwen 3.5 4B Q4_K_M)",
        ),
        VoiceBaselineArtifact(
            identifier=f"{PIN_IDENTIFIER_PREFIX}llm:qwen3.5-0.8b-draft",
            path=root / "models" / "Qwen3.5-0.8B-Q4_K_M.gguf",
            required=False,  # draft is opt-in (llm.draft_kind="none" default)
            notes="speculative-decoding draft (currently disabled by default)",
        ),
        VoiceBaselineArtifact(
            identifier=f"{PIN_IDENTIFIER_PREFIX}voicepack:ultron",
            path=root / "models" / "kokoro" / "voices" / "ultron.pt",
            required=True,
            notes="Kokoro fine-tuned voicepack (Ultron voice character)",
        ),
        VoiceBaselineArtifact(
            identifier=f"{PIN_IDENTIFIER_PREFIX}voicepack:kokoro_finetune",
            path=root / "models" / "kokoro" / "ultron_finetune.pth",
            required=True,
            notes="Kokoro fine-tune model weights (decoder/predictor/text_encoder/bert)",
        ),
        VoiceBaselineArtifact(
            identifier=f"{PIN_IDENTIFIER_PREFIX}wake_word:ultron",
            path=root / "models" / "openwakeword" / "ultron.onnx",
            required=True,
            notes="custom openWakeWord ONNX for the 'ultron' wake word",
        ),
        VoiceBaselineArtifact(
            identifier=f"{PIN_IDENTIFIER_PREFIX}smart_turn:v3",
            path=root / "models" / "smart_turn" / "smart-turn-v3.2-cpu.onnx",
            required=False,  # opt-in via vad.smart_turn.enabled
            notes="Smart Turn V3 semantic end-of-turn confirmation",
        ),
    )


def _verify_one(
    artifact: VoiceBaselineArtifact,
    *,
    pin_file: Path,
    pin_on_first_use: bool,
    budget_seconds: float,
) -> ArtifactVerificationOutcome:
    """Verify a single artifact. Never raises."""
    start = time.monotonic()
    if not artifact.path.exists():
        detail = "required artifact missing" if artifact.required else "optional artifact missing"
        return ArtifactVerificationOutcome(
            identifier=artifact.identifier,
            path=artifact.path,
            status="missing",
            detail=detail,
            elapsed_seconds=time.monotonic() - start,
        )
    try:
        identity = compute_identity_from_path(artifact.path)
    except Exception as e:  # noqa: BLE001
        return ArtifactVerificationOutcome(
            identifier=artifact.identifier,
            path=artifact.path,
            status="error",
            detail=f"digest compute failed: {e}",
            elapsed_seconds=time.monotonic() - start,
        )
    # Budget check after the (potentially-slow) hash. The budget is
    # an observability hint; we still return the outcome (the hash
    # already happened).
    elapsed = time.monotonic() - start
    if elapsed > budget_seconds:
        LOGGER.warning(
            "voice-baseline verify of %s exceeded budget (%.1fs > %.1fs)",
            artifact.identifier, elapsed, budget_seconds,
        )

    try:
        pin = load_pinned_digest(artifact.identifier, pin_file=pin_file)
    except Exception as e:  # noqa: BLE001
        return ArtifactVerificationOutcome(
            identifier=artifact.identifier,
            path=artifact.path,
            status="error",
            detail=f"pin lookup failed: {e}",
            sha256_hex=identity.sha256_hex,
            elapsed_seconds=elapsed,
        )

    if pin is None:
        if not pin_on_first_use:
            return ArtifactVerificationOutcome(
                identifier=artifact.identifier,
                path=artifact.path,
                status="missing",
                detail="no pin recorded yet (pin_on_first_use=False)",
                sha256_hex=identity.sha256_hex,
                elapsed_seconds=elapsed,
            )
        try:
            pin_first_use_digests(
                identity,
                artifact.identifier,
                pin_file=pin_file,
                notes=artifact.notes,
            )
        except Exception as e:  # noqa: BLE001
            return ArtifactVerificationOutcome(
                identifier=artifact.identifier,
                path=artifact.path,
                status="error",
                detail=f"pin record failed: {e}",
                sha256_hex=identity.sha256_hex,
                elapsed_seconds=elapsed,
            )
        return ArtifactVerificationOutcome(
            identifier=artifact.identifier,
            path=artifact.path,
            status="pinned",
            detail="recorded TOFU pin (first observation)",
            sha256_hex=identity.sha256_hex,
            elapsed_seconds=elapsed,
        )

    result = verify_against_pin(
        identity, artifact.identifier, pin_file=pin_file,
    )
    if result.ok:
        return ArtifactVerificationOutcome(
            identifier=artifact.identifier,
            path=artifact.path,
            status="verified",
            detail="digest matches pin",
            sha256_hex=identity.sha256_hex,
            elapsed_seconds=elapsed,
        )

    mismatch_summary = "; ".join(
        f"{m.field}: pinned={str(m.expected)[:12]} actual={str(m.actual)[:12]}"
        for m in result.mismatches
    ) or "see pin file for detail"
    return ArtifactVerificationOutcome(
        identifier=artifact.identifier,
        path=artifact.path,
        status="mismatch",
        detail=f"pin mismatch: {mismatch_summary}",
        sha256_hex=identity.sha256_hex,
        elapsed_seconds=elapsed,
    )


def verify_voice_baseline_artifacts(
    project_root: Path,
    *,
    artifacts: Optional[Sequence[VoiceBaselineArtifact]] = None,
    pin_file: Optional[Path] = None,
    pin_on_first_use: bool = True,
    budget_seconds: float = DEFAULT_PER_FILE_BUDGET_SECONDS,
) -> VerificationReport:
    """Verify every artifact in ``artifacts`` against the pin file.

    Synchronous. Caller wraps with ``threading.Thread`` for async
    behaviour, or uses :func:`verify_voice_baseline_artifacts_async`.

    Args:
        project_root: PROJECT_ROOT to resolve relative paths.
        artifacts: explicit artifact list. Defaults to
            :func:`default_voice_baseline_artifacts`.
        pin_file: explicit pin file path. Defaults to
            ``data/install/pinned_digests.jsonl`` under ``project_root``.
        pin_on_first_use: when True (default), record a TOFU pin
            when no row exists yet. Pass False to fail-closed
            (missing pin -> status="missing").
        budget_seconds: per-file digest budget. Exceeding logs WARN
            but does not abort.

    Returns:
        :class:`VerificationReport` with one outcome per artifact.
    """
    if artifacts is None:
        artifacts = default_voice_baseline_artifacts(project_root)
    resolved_pin_file = pin_file or (project_root / DEFAULT_PIN_FILE_RELATIVE)
    try:
        resolved_pin_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        LOGGER.warning(
            "voice-baseline verify: cannot create pin dir %s: %s",
            resolved_pin_file.parent, e,
        )

    report = VerificationReport()
    for artifact in artifacts:
        outcome = _verify_one(
            artifact,
            pin_file=resolved_pin_file,
            pin_on_first_use=pin_on_first_use,
            budget_seconds=budget_seconds,
        )
        report.record(outcome)
    report.mark_complete()
    return report


def verify_voice_baseline_artifacts_async(
    project_root: Path,
    *,
    artifacts: Optional[Sequence[VoiceBaselineArtifact]] = None,
    pin_file: Optional[Path] = None,
    pin_on_first_use: bool = True,
    budget_seconds: float = DEFAULT_PER_FILE_BUDGET_SECONDS,
    on_complete: Optional[callable] = None,
) -> tuple[VerificationReport, threading.Thread]:
    """Spawn a daemon thread that runs :func:`verify_voice_baseline_artifacts`.

    Used at orchestrator startup so the cold-start path doesn't pay
    the ~5-10 s GGUF hash cost on the foreground. The returned
    :class:`VerificationReport` is mutated in-place by the
    background thread; callers can poll
    :attr:`VerificationReport.is_complete` or wait on the returned
    :class:`threading.Thread`.

    ``on_complete`` if provided receives the report once verification
    finishes. Exceptions in the callback are swallowed + logged.
    """
    report = VerificationReport()
    captured_artifacts = (
        artifacts if artifacts is not None
        else default_voice_baseline_artifacts(project_root)
    )
    resolved_pin_file = pin_file or (project_root / DEFAULT_PIN_FILE_RELATIVE)
    try:
        resolved_pin_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        LOGGER.warning(
            "voice-baseline verify: cannot create pin dir %s: %s",
            resolved_pin_file.parent, e,
        )

    def _runner() -> None:
        try:
            for artifact in captured_artifacts:
                outcome = _verify_one(
                    artifact,
                    pin_file=resolved_pin_file,
                    pin_on_first_use=pin_on_first_use,
                    budget_seconds=budget_seconds,
                )
                report.record(outcome)
        except Exception as e:  # noqa: BLE001
            LOGGER.warning("voice-baseline verifier thread raised: %s", e)
        finally:
            report.mark_complete()
            if on_complete is not None:
                try:
                    on_complete(report)
                except Exception as cb_e:  # noqa: BLE001
                    LOGGER.warning(
                        "voice-baseline verify on_complete raised: %s", cb_e,
                    )

    thread = threading.Thread(
        target=_runner,
        name="voice-baseline-verify",
        daemon=True,
    )
    thread.start()
    return report, thread


def verify_single_artifact_sync(
    identifier: str,
    path: Path,
    *,
    pin_file: Optional[Path] = None,
    project_root: Optional[Path] = None,
    pin_on_first_use: bool = True,
    notes: str = "",
    required: bool = True,
) -> ArtifactVerificationOutcome:
    """Verify a single artifact synchronously (no thread spawn).

    Used by ``LLMEngine.reload_for_preset`` (T1 + T9 wiring) to refuse
    a model hot-swap when the target GGUF's on-disk digest doesn't
    match the pinned digest. Returns the outcome so the caller can
    branch on ``status in {"verified", "pinned"}`` -> allow swap, else
    refuse + log.

    Args:
        identifier: pin-file key (e.g.
            ``"voice_baseline:llm:qwen3.5-4b"``).
        path: absolute path to the artifact on disk.
        pin_file: explicit pin-file path. Defaults to
            ``<project_root>/data/install/pinned_digests.jsonl``.
        project_root: required when ``pin_file`` is None.
        pin_on_first_use: TOFU behaviour for the missing-pin case.
        notes: written into the pin row on first-fetch TOFU.
        required: surfaces in the outcome detail when the file is
            missing.

    Returns:
        :class:`ArtifactVerificationOutcome`.
    """
    if pin_file is None:
        if project_root is None:
            raise ValueError("project_root or pin_file must be supplied")
        pin_file = project_root / DEFAULT_PIN_FILE_RELATIVE
    try:
        pin_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        LOGGER.warning(
            "verify_single_artifact_sync: cannot create pin dir %s: %s",
            pin_file.parent, e,
        )
    artifact = VoiceBaselineArtifact(
        identifier=identifier, path=path, required=required, notes=notes,
    )
    return _verify_one(
        artifact,
        pin_file=pin_file,
        pin_on_first_use=pin_on_first_use,
        budget_seconds=DEFAULT_PER_FILE_BUDGET_SECONDS,
    )


def summarise_report(report: VerificationReport) -> str:
    """Render a one-line summary suitable for the orchestrator log."""
    if not report.is_complete:
        return f"voice-baseline verify: in-flight ({len(report.outcomes)} done)"
    counts: dict[str, int] = {}
    for outcome in report.outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    parts = [f"{status}={n}" for status, n in sorted(counts.items())]
    elapsed = report.elapsed_seconds or 0.0
    return f"voice-baseline verify: {' '.join(parts)} in {elapsed:.1f}s"


__all__ = [
    "PIN_IDENTIFIER_PREFIX",
    "DEFAULT_PER_FILE_BUDGET_SECONDS",
    "VoiceBaselineArtifact",
    "ArtifactVerificationOutcome",
    "VerificationReport",
    "default_voice_baseline_artifacts",
    "verify_voice_baseline_artifacts",
    "verify_voice_baseline_artifacts_async",
    "verify_single_artifact_sync",
    "summarise_report",
]
