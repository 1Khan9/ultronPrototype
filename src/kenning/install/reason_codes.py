"""Canonical moderation reason-code catalogue with verdict derivation (T3).

T3 (openclaw-clawhub catalog port; see ``THIRD_PARTY_NOTICES.md``).
Stable string-code namespace for security findings, paired with a
deterministic verdict-derivation function. Three architectural pieces:

1. **The code namespace.** Every finding carries a code drawn from a
   frozen catalogue. Codes use a dotted shape: ``<prefix>.<slug>``.
   Prefixes carve up the namespace by intent: ``malicious.*`` for
   findings whose only purpose is harm; ``suspicious.*`` for findings
   that need human (or LLM) review; ``review.*`` for LLM-routed cases
   that don't claim a definitive verdict; ``kenning.*`` for
   kenning-specific extensions that bridge to the safety-validator's
   K/A-J/M-S/IT/Cap-1..Cap-4 categories. The clawhub code namespace is
   preserved verbatim (33 codes, ``MODERATION_ENGINE_VERSION`` matches
   ``v2.4.24``) so audit logs can cross-reference upstream issues; the
   kenning extensions add the seven codes that map to features the
   upstream catalogue doesn't have (voice-baseline lock, K-category
   tamper, persona drift, etc.).

2. **The verdict derivation algorithm.** :func:`verdict_from_codes`
   applies short-circuit precedence: any malicious-prefix or any code
   in :data:`MALICIOUS_CODES` returns ``"malicious"``; otherwise any
   suspicious-prefix returns ``"suspicious"``; otherwise
   ``"clean"``. ``"pending"`` and ``"not_run"`` are explicit values
   :func:`compute_status` can return when no codes have been observed
   yet (scan still in flight) or when the scan was deliberately
   skipped. This pure function is what every install / hook /
   skill-load decision routes through.

3. **The severity ladder.** :class:`FindingSeverity` (re-exported from
   :mod:`kenning.install.static_scanner` for compatibility) is the
   ``info`` / ``warn`` / ``critical`` ladder. Each code has a default
   severity in :data:`DEFAULT_SEVERITIES`; per-finding context can
   bump it (a ``suspicious.dangerous_exec`` in a SKILL.md body is
   warn; the same code in a voice-baseline-protected file like
   SOUL.md is critical).

The :data:`EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES` set carves out
codes a moderator (or, in single-user kenning, the user via the
two-phase approval channel) can mark as ``acknowledged`` without
removing them from the audit trail. The clawhub catalogue currently
carves out only :data:`REASON_CODES["CREDENTIAL_HARVEST"]`; kenning
preserves that and adds two more for the voice-baseline contract
(see code definitions below).

This module is pure data + pure functions. No I/O. Callers (the
static scanner, the audit log, the voice-narration helpers in
:mod:`kenning.coding.narration`) consume the helpers without ever
touching the underlying registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Optional

from kenning.install.static_scanner import FindingSeverity


#: Engine version the code namespace is compatible with. Bumped when
#: codes are added/removed/renamed so audit consumers can detect a
#: stale verdict.
MODERATION_ENGINE_VERSION: str = "u1.0.0+clawhub-v2.4.24"


class ReasonPrefix(str, Enum):
    """Code prefix discriminator.

    Codes use a dotted ``<prefix>.<slug>`` shape. The prefix selects
    the verdict-derivation branch:

    * :attr:`MALICIOUS` — purpose-built harm; any presence triggers a
      ``malicious`` verdict.
    * :attr:`SUSPICIOUS` — review-required; triggers a ``suspicious``
      verdict when no malicious code is present.
    * :attr:`REVIEW` — LLM-routed soft signal; does not by itself
      trigger ``suspicious``.
    * :attr:`KENNING` — kenning-specific finding bridging to the safety
      validator's K/A-J/M-S/IT/Cap-1..Cap-4 categories. The slug
      sub-prefix determines verdict.
    """

    MALICIOUS = "malicious"
    SUSPICIOUS = "suspicious"
    REVIEW = "review"
    KENNING = "kenning"


class ModerationVerdict(str, Enum):
    """Rollup verdict derived from a list of codes."""

    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    MALICIOUS = "malicious"
    PENDING = "pending"
    NOT_RUN = "not_run"


# ---------------------------------------------------------------------------
# Code namespace
#
# These string literals are stable API contracts; downstream audit-log
# consumers, moderation dashboards, and voice-narration helpers
# reference them by string. The set is intentionally frozen — adding a
# code is a versioned change.

REASON_CODES: Mapping[str, str] = {
    # ---- review (LLM-routed; verdict doesn't escalate by itself) ----
    "LLM_REVIEW": "review.llm_review",
    # ---- suspicious (review-required; verdict escalates to suspicious) ----
    "DANGEROUS_EXEC": "suspicious.dangerous_exec",
    "DYNAMIC_CODE_EXECUTION": "suspicious.dynamic_code_execution",
    "GENERATED_SOURCE_TEMPLATE_INJECTION": "suspicious.generated_source_template_injection",
    "EXPOSED_RESOURCE_IDENTIFIER": "suspicious.exposed_resource_identifier",
    "DESTRUCTIVE_DELETE_COMMAND": "suspicious.destructive_delete_command",
    "UNSAFE_BROWSER_TEXT_INPUT": "suspicious.unsafe_browser_text_input",
    "EXPOSED_SECRET_LITERAL": "suspicious.exposed_secret_literal",
    "CREDENTIAL_EXPOSURE_INSTRUCTIONS": "suspicious.credential_exposure_instructions",
    "BROWSER_CREDENTIAL_AUTOMATION": "suspicious.browser_credential_automation",
    "SECRET_ARGV_EXPOSURE": "suspicious.secret_argv_exposure",
    "HOST_PLATFORM_SOURCE_PATCH": "suspicious.host_platform_source_patch",
    "BROWSER_FILE_RENDER": "suspicious.browser_file_render",
    "UNSAFE_FILE_WRITE": "suspicious.unsafe_file_write",
    "INSECURE_TLS_VERIFICATION": "suspicious.insecure_tls_verification",
    "AUTONOMOUS_CREDENTIAL_EGRESS": "suspicious.autonomous_credential_egress",
    "HARDCODED_OPERATOR_BILLING": "suspicious.hardcoded_operator_billing",
    "REMOTE_RECIPE_EXECUTION": "suspicious.remote_recipe_execution",
    "CONFIRMATION_BYPASS": "suspicious.confirmation_bypass",
    "CREDENTIAL_HARVEST": "suspicious.env_credential_access",
    "POTENTIAL_EXFILTRATION": "suspicious.potential_exfiltration",
    "OBFUSCATED_CODE": "suspicious.obfuscated_code",
    "NONSTANDARD_NETWORK": "suspicious.nonstandard_network",
    "PROMPT_INJECTION_INSTRUCTIONS": "suspicious.prompt_injection_instructions",
    "INSTALL_UNTRUSTED_SOURCE": "suspicious.install_untrusted_source",
    "PRIVILEGED_ALWAYS": "suspicious.privileged_always",
    "DEP_NOT_FOUND_ON_REGISTRY": "suspicious.dep_not_found_on_registry",
    "LLM_SUSPICIOUS": "suspicious.llm_suspicious",
    # ---- malicious (any presence triggers malicious verdict) ----
    "CRYPTO_MINING": "malicious.crypto_mining",
    "INSTALL_TERMINAL_PAYLOAD": "malicious.install_terminal_payload",
    "KNOWN_BLOCKED_SIGNATURE": "malicious.known_blocked_signature",
    "STEALTH_BROWSER_ABUSE": "malicious.stealth_browser_abuse",
    "LLM_MALICIOUS": "malicious.llm_malicious",
    # ---- kenning extensions (bridge to safety validator categories) ----
    # Suspicious bridges:
    "KENNING_VOICE_BASELINE_TOUCH": "kenning.suspicious.voice_baseline_touch",  # SOUL/RVC/Piper/Kokoro/LLM-model
    "KENNING_PERSONA_DRIFT": "kenning.suspicious.persona_drift",  # IDENTITY.md changed mid-session
    "KENNING_AUDIT_LOG_TAMPER": "kenning.suspicious.audit_log_tamper",  # K3 hash chain mismatch
    "KENNING_VALIDATOR_CONFIG_TAMPER": "kenning.suspicious.validator_config_tamper",  # K7
    "KENNING_INTERACTIVE_TOOL": "kenning.suspicious.interactive_tool",  # IT category match
    "KENNING_CAP_BYPASS_ATTEMPT": "kenning.suspicious.cap_bypass_attempt",  # Cap-1..Cap-4 carveout abused
    # Malicious bridges (K-category self-modification):
    "KENNING_K_CATEGORY_SELF_MODIFY": "kenning.malicious.k_category_self_modify",  # Cat-K self-protection
    "KENNING_KNOWN_BLOCKED_PATTERN": "kenning.malicious.known_blocked_pattern",
}


def _code(name: str) -> str:
    """Return the canonical string for ``name`` (e.g. ``DANGEROUS_EXEC``).

    Raises:
        KeyError: if the name is not registered.
    """
    return REASON_CODES[name]


#: Hardcoded malicious codes. A code in this set forces a malicious
#: verdict regardless of prefix. Mirrors the upstream clawhub pattern;
#: new malicious codes can be added via the ``malicious.*`` prefix
#: without needing membership here, but the explicit set is the
#: defence-in-depth layer.
MALICIOUS_CODES: frozenset[str] = frozenset({
    _code("CRYPTO_MINING"),
    _code("INSTALL_TERMINAL_PAYLOAD"),
    _code("KNOWN_BLOCKED_SIGNATURE"),
    _code("STEALTH_BROWSER_ABUSE"),
    _code("KENNING_KNOWN_BLOCKED_PATTERN"),
})


#: Suspicious codes a moderator can clear with an explicit
#: acknowledgement. Cleared codes stay in the audit trail; the verdict
#: just doesn't escalate on them. Reserved for codes whose
#: false-positive rate is high enough that moderator review is the
#: load-bearing signal (the upstream catalogue carves out only the
#: env-credential-access code; kenning adds two more for situations
#: where the voice user explicitly authorises the action).
EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES: frozenset[str] = frozenset({
    _code("CREDENTIAL_HARVEST"),
    _code("KENNING_VOICE_BASELINE_TOUCH"),
    _code("KENNING_PERSONA_DRIFT"),
})


#: Default severity per code. Override per finding context by passing
#: an explicit severity to :class:`Finding`.
DEFAULT_SEVERITIES: Mapping[str, FindingSeverity] = {
    # review.* — informational (LLM signal, not a decision)
    _code("LLM_REVIEW"): FindingSeverity.INFO,
    # suspicious.* — most are critical; obfuscation / network / TLS / install-source / privileged / dep-not-found / injection-instructions are warn
    _code("DANGEROUS_EXEC"): FindingSeverity.CRITICAL,
    _code("DYNAMIC_CODE_EXECUTION"): FindingSeverity.CRITICAL,
    _code("GENERATED_SOURCE_TEMPLATE_INJECTION"): FindingSeverity.CRITICAL,
    _code("EXPOSED_RESOURCE_IDENTIFIER"): FindingSeverity.CRITICAL,
    _code("DESTRUCTIVE_DELETE_COMMAND"): FindingSeverity.WARN,
    _code("UNSAFE_BROWSER_TEXT_INPUT"): FindingSeverity.WARN,
    _code("EXPOSED_SECRET_LITERAL"): FindingSeverity.CRITICAL,
    _code("CREDENTIAL_EXPOSURE_INSTRUCTIONS"): FindingSeverity.CRITICAL,
    _code("BROWSER_CREDENTIAL_AUTOMATION"): FindingSeverity.CRITICAL,
    _code("SECRET_ARGV_EXPOSURE"): FindingSeverity.CRITICAL,
    _code("HOST_PLATFORM_SOURCE_PATCH"): FindingSeverity.CRITICAL,
    _code("BROWSER_FILE_RENDER"): FindingSeverity.CRITICAL,
    _code("UNSAFE_FILE_WRITE"): FindingSeverity.CRITICAL,
    _code("INSECURE_TLS_VERIFICATION"): FindingSeverity.WARN,
    _code("AUTONOMOUS_CREDENTIAL_EGRESS"): FindingSeverity.CRITICAL,
    _code("HARDCODED_OPERATOR_BILLING"): FindingSeverity.CRITICAL,
    _code("REMOTE_RECIPE_EXECUTION"): FindingSeverity.CRITICAL,
    _code("CONFIRMATION_BYPASS"): FindingSeverity.CRITICAL,
    _code("CREDENTIAL_HARVEST"): FindingSeverity.CRITICAL,
    _code("POTENTIAL_EXFILTRATION"): FindingSeverity.WARN,
    _code("OBFUSCATED_CODE"): FindingSeverity.WARN,
    _code("NONSTANDARD_NETWORK"): FindingSeverity.WARN,
    _code("PROMPT_INJECTION_INSTRUCTIONS"): FindingSeverity.WARN,
    _code("INSTALL_UNTRUSTED_SOURCE"): FindingSeverity.WARN,
    _code("PRIVILEGED_ALWAYS"): FindingSeverity.WARN,
    _code("DEP_NOT_FOUND_ON_REGISTRY"): FindingSeverity.WARN,
    _code("LLM_SUSPICIOUS"): FindingSeverity.WARN,
    # malicious.* — always critical
    _code("CRYPTO_MINING"): FindingSeverity.CRITICAL,
    _code("INSTALL_TERMINAL_PAYLOAD"): FindingSeverity.CRITICAL,
    _code("KNOWN_BLOCKED_SIGNATURE"): FindingSeverity.CRITICAL,
    _code("STEALTH_BROWSER_ABUSE"): FindingSeverity.CRITICAL,
    _code("LLM_MALICIOUS"): FindingSeverity.CRITICAL,
    # kenning.suspicious.* / kenning.malicious.*
    _code("KENNING_VOICE_BASELINE_TOUCH"): FindingSeverity.CRITICAL,
    _code("KENNING_PERSONA_DRIFT"): FindingSeverity.WARN,
    _code("KENNING_AUDIT_LOG_TAMPER"): FindingSeverity.CRITICAL,
    _code("KENNING_VALIDATOR_CONFIG_TAMPER"): FindingSeverity.CRITICAL,
    _code("KENNING_INTERACTIVE_TOOL"): FindingSeverity.WARN,
    _code("KENNING_CAP_BYPASS_ATTEMPT"): FindingSeverity.CRITICAL,
    _code("KENNING_K_CATEGORY_SELF_MODIFY"): FindingSeverity.CRITICAL,
    _code("KENNING_KNOWN_BLOCKED_PATTERN"): FindingSeverity.CRITICAL,
}


#: Lookup from canonical reason-code string to its short OWASP-Agentic
#: alignment tag. Used for voice narration and dashboard rollup. The
#: clawhub catalogue does not ship a formal mapping table; this is
#: kenning's reading of the conceptual alignment.
OWASP_AGENTIC_ALIGNMENT: Mapping[str, str] = {
    _code("PROMPT_INJECTION_INSTRUCTIONS"): "AS01:prompt-injection",
    _code("EXPOSED_SECRET_LITERAL"): "AS04:credential-exposure",
    _code("CREDENTIAL_EXPOSURE_INSTRUCTIONS"): "AS04:credential-exposure",
    _code("BROWSER_CREDENTIAL_AUTOMATION"): "AS04:credential-exposure",
    _code("SECRET_ARGV_EXPOSURE"): "AS04:credential-exposure",
    _code("CREDENTIAL_HARVEST"): "AS04:credential-exposure",
    _code("DANGEROUS_EXEC"): "AS05:unsafe-execution",
    _code("DYNAMIC_CODE_EXECUTION"): "AS05:unsafe-execution",
    _code("INSTALL_TERMINAL_PAYLOAD"): "AS05:unsafe-execution",
    _code("GENERATED_SOURCE_TEMPLATE_INJECTION"): "AS06:code-injection",
    _code("AUTONOMOUS_CREDENTIAL_EGRESS"): "AS07:excessive-agency",
    _code("CONFIRMATION_BYPASS"): "AS07:excessive-agency",
    _code("STEALTH_BROWSER_ABUSE"): "AS07:excessive-agency",
    _code("CRYPTO_MINING"): "AS09:resource-misuse",
    _code("UNSAFE_BROWSER_TEXT_INPUT"): "AS08:tool-misuse",
    _code("BROWSER_FILE_RENDER"): "AS08:tool-misuse",
    _code("UNSAFE_FILE_WRITE"): "AS08:tool-misuse",
    _code("KENNING_K_CATEGORY_SELF_MODIFY"): "AS10:context-poisoning",
    _code("KENNING_AUDIT_LOG_TAMPER"): "AS10:context-poisoning",
}


# ---------------------------------------------------------------------------
# Verdict derivation


@dataclass(frozen=True)
class StatusInputs:
    """Inputs to :func:`compute_status` for the pending/not-run cases.

    Args:
        codes: observed reason codes (may be empty).
        scan_completed: True if at least one scan engine has reported.
            False -> verdict resolves to PENDING when no codes seen.
        scan_run: True if a scan was actually attempted. False ->
            verdict resolves to NOT_RUN when no codes seen.
    """

    codes: tuple[str, ...]
    scan_completed: bool = True
    scan_run: bool = True


def normalize_reason_codes(codes: Iterable[str]) -> tuple[str, ...]:
    """Return ``codes`` with empties / dupes removed, sorted ascending.

    The sort is :py:meth:`str.casefold`-based so audit-log readers
    see a stable order even when codes arrive from multiple engines
    in different orders.
    """
    seen: dict[str, None] = {}
    for raw in codes:
        if not raw:
            continue
        code = str(raw).strip()
        if not code:
            continue
        seen[code] = None
    return tuple(sorted(seen.keys(), key=str.casefold))


def verdict_from_codes(codes: Iterable[str]) -> ModerationVerdict:
    """Return the rollup verdict for ``codes``.

    Algorithm (mirrors the clawhub upstream pattern):

    1. Normalise the input (dedupe, drop empties, sort).
    2. Any code in :data:`MALICIOUS_CODES` OR starting with
       ``"malicious."`` OR ``"kenning.malicious."`` -> MALICIOUS.
    3. Any remaining code starting with ``"suspicious."`` OR
       ``"kenning.suspicious."`` -> SUSPICIOUS.
    4. Otherwise -> CLEAN.

    Note that ``review.*`` does NOT escalate to suspicious — review
    codes are advisory signals for the LLM router. Only ``LLM_REVIEW``
    paired with an explicit suspicious / malicious code triggers the
    higher verdict.
    """
    normalised = normalize_reason_codes(codes)
    has_malicious = False
    has_suspicious = False
    for code in normalised:
        if code in MALICIOUS_CODES:
            has_malicious = True
            break
        if code.startswith("malicious.") or code.startswith("kenning.malicious."):
            has_malicious = True
            break
        if code.startswith("suspicious.") or code.startswith("kenning.suspicious."):
            has_suspicious = True
    if has_malicious:
        return ModerationVerdict.MALICIOUS
    if has_suspicious:
        return ModerationVerdict.SUSPICIOUS
    return ModerationVerdict.CLEAN


def compute_status(inputs: StatusInputs) -> ModerationVerdict:
    """Return the verdict for ``inputs`` including NOT_RUN / PENDING.

    Same algorithm as :func:`verdict_from_codes` for the case where
    codes were observed; otherwise resolves to NOT_RUN (scan not
    attempted) or PENDING (attempted but not yet completed).
    """
    if not inputs.scan_run:
        return ModerationVerdict.NOT_RUN
    if not inputs.codes and not inputs.scan_completed:
        return ModerationVerdict.PENDING
    return verdict_from_codes(inputs.codes)


def severity_for_code(code: str) -> FindingSeverity:
    """Return the default severity for ``code``.

    Returns :attr:`FindingSeverity.WARN` for unknown codes (graceful
    degradation: a code added later, before this catalogue is
    updated, still produces a usable finding rather than an
    AttributeError).
    """
    return DEFAULT_SEVERITIES.get(code, FindingSeverity.WARN)


def is_externally_clearable_suspicious_code(code: str) -> bool:
    """Return True if ``code`` is in :data:`EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES`.

    A True return means a moderator (or the voice user, via the
    two-phase approval channel) can mark the code as acknowledged
    without overriding the underlying scan; the code stays in the
    audit log + dashboards but does not block the action.
    """
    return code in EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES


def summarize_reason_codes(codes: Iterable[str], *, max_listed: int = 3) -> str:
    """Return a one-line summary string suitable for TTS or dashboards.

    Output shapes:

    * No codes -> ``"No suspicious patterns detected."``
    * Only review codes -> ``"Review: <list>"``
    * Otherwise -> ``"Detected: <top-3>"`` with ``"(+N more)"`` when
      truncated. Codes are sorted by severity (critical > warn > info),
      then alphabetically inside each tier.

    Output is plain ASCII, no special characters, safe for the Kokoro
    TTS pipeline (passing it through :func:`normalize_text_for_tts`
    is still recommended on the voice path).
    """
    normalised = normalize_reason_codes(codes)
    if not normalised:
        return "No suspicious patterns detected."

    review_only = all(
        c.startswith("review.") for c in normalised
    )
    if review_only:
        listed = ", ".join(normalised[:max_listed])
        remaining = len(normalised) - max_listed
        suffix = f" (+{remaining} more)" if remaining > 0 else ""
        return f"Review: {listed}{suffix}"

    def sort_key(code: str) -> tuple[int, str]:
        severity = severity_for_code(code)
        tier = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARN: 1,
            FindingSeverity.INFO: 2,
        }.get(severity, 1)
        return (tier, code.casefold())

    ordered = sorted(normalised, key=sort_key)
    listed = ", ".join(ordered[:max_listed])
    remaining = len(ordered) - max_listed
    suffix = f" (+{remaining} more)" if remaining > 0 else ""
    return f"Detected: {listed}{suffix}"


def legacy_flags_from_verdict(verdict: ModerationVerdict) -> Optional[tuple[str, ...]]:
    """Return legacy flag-strings for backwards-compat with older audit consumers.

    Pre-T3 audit logs used coarse flag strings rather than reason
    codes. This helper produces the legacy shape for consumers that
    haven't been migrated.

    Returns ``None`` for ``CLEAN`` / ``NOT_RUN`` / ``PENDING`` so
    callers can elide the field.
    """
    if verdict is ModerationVerdict.MALICIOUS:
        return ("blocked.malware",)
    if verdict is ModerationVerdict.SUSPICIOUS:
        return ("flagged.suspicious",)
    return None


# ---------------------------------------------------------------------------
# Static-scanner kind -> code bridge
#
# The existing static_scanner.py emits findings tagged with
# LineFindingKind / SourceFindingKind values. This mapping lets older
# call sites keep their kind-based output while audit consumers see
# the canonical codes.

#: Kind-string (from :class:`LineFindingKind` / :class:`SourceFindingKind`)
#: -> canonical reason code (string). Use
#: :func:`code_for_kind` for the typed lookup with fallback.
KIND_TO_CODE: Mapping[str, str] = {
    # LineFindingKind values
    "dangerous_exec": _code("DANGEROUS_EXEC"),
    "dynamic_code_execution": _code("DYNAMIC_CODE_EXECUTION"),
    "crypto_mining": _code("CRYPTO_MINING"),
    "suspicious_network": _code("NONSTANDARD_NETWORK"),
    # SourceFindingKind values
    "potential_exfiltration": _code("POTENTIAL_EXFILTRATION"),
    "obfuscated_code": _code("OBFUSCATED_CODE"),
    "env_harvesting": _code("CREDENTIAL_HARVEST"),
    "file_too_large": _code("LLM_REVIEW"),  # informational; not suspicious
    "decode_error": _code("LLM_REVIEW"),    # informational; not suspicious
}


def code_for_kind(kind: str) -> Optional[str]:
    """Return the canonical reason code for an existing finding ``kind``.

    Returns ``None`` for unknown kinds. Callers that want a strict
    mapping should use ``KIND_TO_CODE[kind]`` directly and let the
    KeyError surface.
    """
    return KIND_TO_CODE.get(kind)


__all__ = [
    "MODERATION_ENGINE_VERSION",
    "ReasonPrefix",
    "ModerationVerdict",
    "REASON_CODES",
    "MALICIOUS_CODES",
    "EXTERNALLY_CLEARABLE_SUSPICIOUS_CODES",
    "DEFAULT_SEVERITIES",
    "OWASP_AGENTIC_ALIGNMENT",
    "KIND_TO_CODE",
    "StatusInputs",
    "FindingSeverity",
    "normalize_reason_codes",
    "verdict_from_codes",
    "compute_status",
    "severity_for_code",
    "is_externally_clearable_suspicious_code",
    "summarize_reason_codes",
    "legacy_flags_from_verdict",
    "code_for_kind",
]
