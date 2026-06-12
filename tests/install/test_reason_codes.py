"""Tests for the canonical moderation reason-code catalogue (T3).

Covers:

* The catalogue's structural invariants (every code has a known
  prefix; every code has a default severity; the malicious-codes set
  is a subset of the catalogue).
* :func:`verdict_from_codes` short-circuit precedence across the four
  prefixes plus kenning's malicious/suspicious bridges.
* :func:`compute_status` with PENDING / NOT_RUN cases.
* :func:`normalize_reason_codes` deduplication + sort.
* :func:`summarize_reason_codes` output shapes.
* :func:`is_externally_clearable_suspicious_code` membership.
* :func:`severity_for_code` graceful fallback.
* :func:`legacy_flags_from_verdict` round-trip.
* :func:`code_for_kind` mapping from the existing scanner kinds.
"""

from __future__ import annotations

import pytest

from kenning.install.reason_codes import (
    DEFAULT_SEVERITIES,
    EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES,
    KIND_TO_CODE,
    MALICIOUS_CODES,
    MODERATION_ENGINE_VERSION,
    OWASP_AGENTIC_ALIGNMENT,
    REASON_CODES,
    FindingSeverity,
    ModerationVerdict,
    StatusInputs,
    code_for_kind,
    compute_status,
    is_externally_clearable_suspicious_code,
    legacy_flags_from_verdict,
    normalize_reason_codes,
    severity_for_code,
    summarize_reason_codes,
    verdict_from_codes,
)


# ---------------------------------------------------------------------------
# Structural invariants


def test_engine_version_constant_is_set() -> None:
    assert MODERATION_ENGINE_VERSION.startswith("u")
    assert "clawhub-v" in MODERATION_ENGINE_VERSION


def test_every_code_has_recognised_prefix() -> None:
    allowed_prefixes = ("review.", "suspicious.", "malicious.", "kenning.")
    for name, code in REASON_CODES.items():
        assert any(
            code.startswith(p) for p in allowed_prefixes
        ), f"code {name}={code!r} has no recognised prefix"


def test_every_code_has_default_severity() -> None:
    for name, code in REASON_CODES.items():
        assert code in DEFAULT_SEVERITIES, f"{name}={code!r} missing default severity"


def test_malicious_codes_subset_of_catalogue() -> None:
    all_codes = set(REASON_CODES.values())
    for code in MALICIOUS_CODES:
        assert code in all_codes, f"{code!r} not in REASON_CODES catalogue"


def test_externally_clearable_subset_of_suspicious() -> None:
    all_codes = set(REASON_CODES.values())
    for code in EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES:
        assert code in all_codes, f"{code!r} not in REASON_CODES"
        assert (
            code.startswith("suspicious.") or code.startswith("kenning.suspicious.")
        ), f"{code!r} is not a suspicious-tier code"


def test_owasp_alignment_codes_are_known() -> None:
    all_codes = set(REASON_CODES.values())
    for code in OWASP_AGENTIC_ALIGNMENT.keys():
        assert code in all_codes, f"OWASP map references unknown code {code!r}"


def test_kind_to_code_targets_known_codes() -> None:
    all_codes = set(REASON_CODES.values())
    for kind, code in KIND_TO_CODE.items():
        assert code in all_codes, f"kind {kind!r} maps to unknown code {code!r}"


# ---------------------------------------------------------------------------
# verdict_from_codes


def test_empty_codes_returns_clean() -> None:
    assert verdict_from_codes([]) is ModerationVerdict.CLEAN


def test_pure_review_codes_return_clean() -> None:
    assert verdict_from_codes(["review.llm_review"]) is ModerationVerdict.CLEAN


def test_single_suspicious_returns_suspicious() -> None:
    assert verdict_from_codes(
        [REASON_CODES["DANGEROUS_EXEC"]]
    ) is ModerationVerdict.SUSPICIOUS


def test_single_malicious_returns_malicious() -> None:
    assert verdict_from_codes(
        [REASON_CODES["CRYPTO_MINING"]]
    ) is ModerationVerdict.MALICIOUS


def test_malicious_overrides_suspicious() -> None:
    codes = [
        REASON_CODES["DANGEROUS_EXEC"],
        REASON_CODES["CRYPTO_MINING"],
    ]
    assert verdict_from_codes(codes) is ModerationVerdict.MALICIOUS


def test_unknown_malicious_prefix_still_escalates() -> None:
    # A future code with malicious. prefix but not in the hardcoded
    # set MUST still escalate.
    assert verdict_from_codes(
        ["malicious.brand_new_unknown_pattern"]
    ) is ModerationVerdict.MALICIOUS


def test_kenning_malicious_bridge_escalates() -> None:
    assert verdict_from_codes(
        [REASON_CODES["KENNING_K_CATEGORY_SELF_MODIFY"]]
    ) is ModerationVerdict.MALICIOUS


def test_kenning_suspicious_bridge_escalates() -> None:
    assert verdict_from_codes(
        [REASON_CODES["KENNING_VOICE_BASELINE_TOUCH"]]
    ) is ModerationVerdict.SUSPICIOUS


def test_review_with_suspicious_returns_suspicious() -> None:
    codes = [REASON_CODES["LLM_REVIEW"], REASON_CODES["OBFUSCATED_CODE"]]
    assert verdict_from_codes(codes) is ModerationVerdict.SUSPICIOUS


def test_duplicate_codes_dont_affect_verdict() -> None:
    codes = [REASON_CODES["DANGEROUS_EXEC"]] * 5
    assert verdict_from_codes(codes) is ModerationVerdict.SUSPICIOUS


def test_empty_strings_are_ignored() -> None:
    codes = ["", "  ", REASON_CODES["DANGEROUS_EXEC"]]
    assert verdict_from_codes(codes) is ModerationVerdict.SUSPICIOUS


# ---------------------------------------------------------------------------
# compute_status (PENDING / NOT_RUN cases)


def test_status_not_run_when_scan_skipped() -> None:
    inputs = StatusInputs(codes=(), scan_completed=False, scan_run=False)
    assert compute_status(inputs) is ModerationVerdict.NOT_RUN


def test_status_pending_when_scan_in_flight() -> None:
    inputs = StatusInputs(codes=(), scan_completed=False, scan_run=True)
    assert compute_status(inputs) is ModerationVerdict.PENDING


def test_status_clean_when_complete_with_no_codes() -> None:
    inputs = StatusInputs(codes=(), scan_completed=True, scan_run=True)
    assert compute_status(inputs) is ModerationVerdict.CLEAN


def test_status_malicious_overrides_pending_when_codes_present() -> None:
    inputs = StatusInputs(
        codes=(REASON_CODES["CRYPTO_MINING"],),
        scan_completed=False,
        scan_run=True,
    )
    assert compute_status(inputs) is ModerationVerdict.MALICIOUS


# ---------------------------------------------------------------------------
# normalize_reason_codes


def test_normalize_deduplicates_and_sorts() -> None:
    codes = [
        REASON_CODES["OBFUSCATED_CODE"],
        REASON_CODES["DANGEROUS_EXEC"],
        REASON_CODES["DANGEROUS_EXEC"],
    ]
    result = normalize_reason_codes(codes)
    assert len(result) == 2
    assert result == tuple(sorted(result, key=str.casefold))


def test_normalize_drops_empties_and_whitespace() -> None:
    result = normalize_reason_codes(["", "   ", REASON_CODES["DANGEROUS_EXEC"]])
    assert result == (REASON_CODES["DANGEROUS_EXEC"],)


def test_normalize_strips_whitespace() -> None:
    spaced = f"  {REASON_CODES['DANGEROUS_EXEC']}  "
    assert normalize_reason_codes([spaced]) == (REASON_CODES["DANGEROUS_EXEC"],)


# ---------------------------------------------------------------------------
# summarize_reason_codes


def test_summary_empty_returns_clean_message() -> None:
    assert summarize_reason_codes([]) == "No suspicious patterns detected."


def test_summary_review_only_uses_review_prefix() -> None:
    result = summarize_reason_codes([REASON_CODES["LLM_REVIEW"]])
    assert result.startswith("Review:")


def test_summary_mixed_uses_detected_prefix() -> None:
    result = summarize_reason_codes(
        [REASON_CODES["DANGEROUS_EXEC"], REASON_CODES["OBFUSCATED_CODE"]]
    )
    assert result.startswith("Detected:")


def test_summary_truncates_beyond_max_listed() -> None:
    codes = [
        REASON_CODES["DANGEROUS_EXEC"],
        REASON_CODES["DYNAMIC_CODE_EXECUTION"],
        REASON_CODES["OBFUSCATED_CODE"],
        REASON_CODES["NONSTANDARD_NETWORK"],
        REASON_CODES["PROMPT_INJECTION_INSTRUCTIONS"],
    ]
    result = summarize_reason_codes(codes, max_listed=3)
    assert "(+2 more)" in result


def test_summary_severity_order() -> None:
    codes = [
        REASON_CODES["OBFUSCATED_CODE"],  # warn
        REASON_CODES["DANGEROUS_EXEC"],  # critical
    ]
    result = summarize_reason_codes(codes)
    # critical should be listed before warn
    crit_pos = result.find(REASON_CODES["DANGEROUS_EXEC"])
    warn_pos = result.find(REASON_CODES["OBFUSCATED_CODE"])
    assert crit_pos < warn_pos


# ---------------------------------------------------------------------------
# is_externally_clearable_suspicious_code


def test_credential_harvest_is_clearable() -> None:
    assert is_externally_clearable_suspicious_code(REASON_CODES["CREDENTIAL_HARVEST"])


def test_kenning_voice_baseline_is_clearable() -> None:
    assert is_externally_clearable_suspicious_code(
        REASON_CODES["KENNING_VOICE_BASELINE_TOUCH"]
    )


def test_dangerous_exec_is_not_clearable() -> None:
    assert not is_externally_clearable_suspicious_code(
        REASON_CODES["DANGEROUS_EXEC"]
    )


def test_unknown_code_is_not_clearable() -> None:
    assert not is_externally_clearable_suspicious_code("suspicious.brand_new_unseen")


# ---------------------------------------------------------------------------
# severity_for_code


def test_severity_known_code() -> None:
    assert severity_for_code(REASON_CODES["DANGEROUS_EXEC"]) is FindingSeverity.CRITICAL


def test_severity_unknown_code_returns_warn() -> None:
    assert severity_for_code("suspicious.future_code_not_here") is FindingSeverity.WARN


# ---------------------------------------------------------------------------
# legacy_flags_from_verdict


def test_legacy_flags_malicious() -> None:
    assert legacy_flags_from_verdict(ModerationVerdict.MALICIOUS) == (
        "blocked.malware",
    )


def test_legacy_flags_suspicious() -> None:
    assert legacy_flags_from_verdict(ModerationVerdict.SUSPICIOUS) == (
        "flagged.suspicious",
    )


def test_legacy_flags_clean_returns_none() -> None:
    assert legacy_flags_from_verdict(ModerationVerdict.CLEAN) is None


def test_legacy_flags_pending_returns_none() -> None:
    assert legacy_flags_from_verdict(ModerationVerdict.PENDING) is None


def test_legacy_flags_not_run_returns_none() -> None:
    assert legacy_flags_from_verdict(ModerationVerdict.NOT_RUN) is None


# ---------------------------------------------------------------------------
# code_for_kind


def test_code_for_kind_dangerous_exec() -> None:
    assert code_for_kind("dangerous_exec") == REASON_CODES["DANGEROUS_EXEC"]


def test_code_for_kind_env_harvesting_maps_to_credential_harvest() -> None:
    # env_harvesting (the scanner's local label) -> CREDENTIAL_HARVEST
    # (the canonical clawhub code).
    assert code_for_kind("env_harvesting") == REASON_CODES["CREDENTIAL_HARVEST"]


def test_code_for_kind_unknown_returns_none() -> None:
    assert code_for_kind("not_a_real_kind") is None


def test_code_for_kind_keeps_existing_scanner_kinds() -> None:
    # Static scanner kinds the scanner already emits. All must have
    # a canonical code so audit log enrichment never drops a finding.
    required_kinds = {
        "dangerous_exec",
        "dynamic_code_execution",
        "crypto_mining",
        "suspicious_network",
        "potential_exfiltration",
        "obfuscated_code",
        "env_harvesting",
    }
    for kind in required_kinds:
        assert code_for_kind(kind) is not None, f"kind {kind!r} missing canonical code"


# ---------------------------------------------------------------------------
# Edge cases


def test_verdict_with_only_kenning_review_codes_returns_clean() -> None:
    # kenning.review.* never escalates by itself.
    assert verdict_from_codes(["kenning.review.something"]) is ModerationVerdict.CLEAN


@pytest.mark.parametrize(
    "verdict, expected_label",
    [
        (ModerationVerdict.CLEAN, "clean"),
        (ModerationVerdict.SUSPICIOUS, "suspicious"),
        (ModerationVerdict.MALICIOUS, "malicious"),
        (ModerationVerdict.PENDING, "pending"),
        (ModerationVerdict.NOT_RUN, "not_run"),
    ],
)
def test_verdict_value_is_stable_string(
    verdict: ModerationVerdict, expected_label: str
) -> None:
    assert verdict.value == expected_label
