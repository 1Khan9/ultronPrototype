"""Catalog 14 (clawhub-self-improving-agent) -- qualitative capture data model.

Covers the new capsule / signal types, PII redaction, stable recurrence keys,
``to_failure_record`` projection, ``bump_recurrence``, and the default-ON
``EvolutionConfig`` knobs. Hermetic + pure-data (no IO, no network).
"""

from __future__ import annotations

import pytest

from ultron.evolution.models import (
    CommandFailureSignal,
    ComplexityHint,
    CorrectionCapsule,
    FeatureRequestCapsule,
    FeatureRequestStatus,
    KnowledgeGapCapsule,
    KnowledgeSource,
    bump_recurrence,
    derive_pattern_key,
    new_record_id,
    redact_fragment,
    verify_asset_id,
)


def test_new_record_id_unique_and_prefixed():
    a = new_record_id("correction_")
    b = new_record_id("correction_")
    assert a.startswith("correction_") and b.startswith("correction_")
    assert a != b  # 6-hex suffix guarantees uniqueness within a millisecond


def test_redact_fragment_scrubs_email_and_phone():
    out = redact_fragment("email me at a.b@example.com or call 555-123-4567 now")
    assert "[redacted-email]" in out
    assert "[redacted-phone]" in out
    assert "@example.com" not in out


def test_redact_fragment_scrubs_secret_ip_and_long_digits():
    out = redact_fragment("key sk-abcdefgh12345678 host 10.0.0.1 id 1234567")
    assert "[redacted-token]" in out
    assert "[redacted-ip]" in out
    assert "[redacted-number]" in out


def test_redact_fragment_truncates_and_empty():
    assert redact_fragment("") == ""
    assert redact_fragment(None) == ""
    assert len(redact_fragment("x " * 500, max_chars=40)) <= 40


def test_derive_pattern_key_deterministic_order_independent_kinded():
    k1 = derive_pattern_key(signals=["perf_bottleneck", "log_error:boom"], kind="capsule")
    k2 = derive_pattern_key(signals=["log_error:zzz", "perf_bottleneck"], kind="capsule")
    assert k1 == k2  # sorted bases, :payload stripped -> order/payload independent
    assert k1.startswith("capsule:")
    assert derive_pattern_key(kind="correction", topic="pytest fixtures").startswith("correction:")
    assert derive_pattern_key(kind="x").endswith(":general")


def test_correction_capsule_redacts_keys_hashes_and_projects():
    c = CorrectionCapsule(
        id="x",
        user_utterance_fragment="No that is wrong, email a@b.com",
        topic_area="pytest fixtures",
        prior_agent_claim_summary="they are session scoped",
        confidence=1.5,
    )
    assert "[redacted-email]" in c.user_utterance_fragment
    assert c.confidence == 1.0  # clamped
    assert c.pattern_key.startswith("correction:")
    assert c.created_at  # auto-stamped
    assert c.asset_id.startswith("sha256:") and verify_asset_id(c)
    fr = c.to_failure_record()
    assert fr["reason_class"] == "user_correction" and fr["gene"] == "ad_hoc"
    assert any(t.startswith("area:") for t in fr["trigger"])


def test_knowledge_gap_source_enum_and_failure_record():
    g = KnowledgeGapCapsule(
        id="x", topic_area="package manager", gap_description="uses pnpm", source="tool"
    )
    assert g.source is KnowledgeSource.TOOL
    assert g.pattern_key.startswith("knowledge_gap:")
    assert verify_asset_id(g)
    assert g.to_failure_record()["reason_class"] == "knowledge_gap"


def test_command_failure_exit_code_coercion_and_record():
    s = CommandFailureSignal(
        id="x", command="pytest", error_summary="Traceback: boom", topic_area="tests", exit_code="3"
    )
    assert s.exit_code == 3  # coerced from str
    assert s.pattern_key.startswith("command_failure:")
    assert verify_asset_id(s)
    assert s.to_failure_record()["reason_class"] == "command_failure"
    assert CommandFailureSignal(id="y", command="ls", error_summary="boom").exit_code is None


def test_feature_request_enums_keys_and_not_distillable():
    f = FeatureRequestCapsule(
        id="x", requested_capability="export to CSV", complexity_hint="complex", status="pending"
    )
    assert f.complexity_hint is ComplexityHint.COMPLEX
    assert f.status is FeatureRequestStatus.PENDING
    assert f.pattern_key.startswith("feature_request:")
    assert verify_asset_id(f)
    # Feature requests are NEVER distilled -- deliberately no failure projection.
    assert not hasattr(f, "to_failure_record")


def test_bump_recurrence_increments_stamps_and_rehashes():
    f = FeatureRequestCapsule(id="x", requested_capability="export to CSV")
    b = bump_recurrence(f, at="2026-06-03T00:00:00Z")
    assert b.recurrence_count == f.recurrence_count + 1
    assert b.last_seen == "2026-06-03T00:00:00Z"
    assert verify_asset_id(b)  # asset_id recomputed for the new content
    assert b.asset_id != f.asset_id


def test_invalid_enum_values_raise():
    with pytest.raises(ValueError):
        KnowledgeGapCapsule(id="x", source="bogus")
    with pytest.raises(ValueError):
        FeatureRequestCapsule(id="x", complexity_hint="bogus")


def test_evolution_config_catalog14_defaults_on():
    from ultron.config import EvolutionConfig

    cfg = EvolutionConfig()
    assert cfg.correction_detection_enabled is True
    assert cfg.feature_request_capture_enabled is True
    assert cfg.command_failure_capture_enabled is True
    assert cfg.pre_turn_nudge_enabled is True
    assert cfg.pre_turn_nudge_max_chars == 240
    assert cfg.recurrence_threshold == 3


def test_evolution_config_bounds_enforced():
    from pydantic import ValidationError

    from ultron.config import EvolutionConfig

    with pytest.raises(ValidationError):
        EvolutionConfig(recurrence_threshold=1)  # ge=2
    with pytest.raises(ValidationError):
        EvolutionConfig(pre_turn_nudge_max_chars=-1)  # ge=0
