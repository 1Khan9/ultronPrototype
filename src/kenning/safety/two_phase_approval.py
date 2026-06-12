"""Two-phase exec approval: register-then-wait with pre-resolved fast path.

T2 (OpenClaw catalog port; see ``THIRD_PARTY_NOTICES.md``). Splits
the approval handshake into two operations:

1. :meth:`ApprovalRegistry.register` — synchronously create an
   approval entry; returns an :class:`ApprovalHandle` carrying the
   approval id + expiry. If the policy engine already has a cached
   verdict for this exact call (auto-allow matrix hit, prior user
   approval, allowlist match), the handle ALSO carries a
   ``pre_resolved`` :class:`ApprovalDecision` and the caller can
   skip step 2 entirely.
2. :meth:`ApprovalRegistry.wait_for_decision` — long-poll the
   registry until a decision arrives OR the expiry deadline elapses.
   Returns the decision (``ALLOW`` / ``DENY``) or ``EXPIRED``.

This shape is the missing piece for any "wait for the user to say
yes/no" gate that today races the orchestrator's loop. Without
two-phase, an answer that arrives before the registration completes
hits an empty queue and the approval orphans.

Use cases:

* Voice confirmation for Cap-2/Cap-3/Cap-4 capabilities
  (orchestrator wants to fire the tool NOW but needs the user's
  "yes/no").
* Desktop automation click-preview gate (SWE-Agent T16): register
  click + screenshot, send to VLM, wait for verdict. If the VLM
  pre-computes confidence, the registration response carries the
  decision and step 2 is skipped.
* Subagent spawn confirmation, gaming-mode engage approval, memory
  ``forget`` confirmation, media-generation approval.

Composes with the trusted-tool-policy chain (T13): a chain policy
can return ``require_approval=<descriptor>`` which the orchestrator
forwards to this registry via :meth:`register`.

YELLOW gating: the registry is GREEN infrastructure; the YELLOW
concern is the channel that PRODUCES decisions (voice STT, GUI
prompt, etc.) and the policy engine that PRODUCES pre-resolved
verdicts. Both have their own gating elsewhere in the safety stack.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional

LOGGER = logging.getLogger(__name__)


#: Default per-approval timeout (seconds). Mirrors OpenClaw's 60 s
#: registration-side default; the user has 60 s to answer before
#: the request expires and the caller falls back to ``ask: on-miss``
#: semantics.
DEFAULT_APPROVAL_TIMEOUT_SECONDS: float = 60.0

#: Maximum approval timeout. Anything longer is suspect; the user
#: should not be expected to remember a yes/no question past 10 min.
MAX_APPROVAL_TIMEOUT_SECONDS: float = 600.0

#: Default polling interval used by :meth:`wait_for_decision` when no
#: condition variable is available. Should be small enough that the
#: caller doesn't perceive a wait but large enough that the busy loop
#: doesn't burn CPU.
DEFAULT_POLL_INTERVAL_SECONDS: float = 0.05


class ApprovalOutcome(str, Enum):
    """Final outcome of an approval cycle."""

    ALLOW = "allow"
    DENY = "deny"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"
    PENDING = "pending"


@dataclass(frozen=True)
class ApprovalRequest:
    """Caller-supplied request payload.

    Attributes:
        kind: short string describing the approval kind
            (``"voice_confirmation"`` / ``"cost_limit"`` /
            ``"click_preview"`` / ``"gaming_engage"``). Free-form;
            consumed by the channel router.
        prompt: human-readable description of what's being approved
            (spoken via TTS for voice confirmations; rendered as a
            chat message for text channels).
        actor: short identifier of the producing subsystem
            (``"voice"`` / ``"coding"`` / ``"supervisor"``).
        scope_key: typically the owning session id; lets the registry
            scope listings per-session.
        metadata: opaque per-request payload (cost estimate, target
            path, image bytes, etc.). Forwarded to the channel router.
        timeout_seconds: per-request timeout override. ``None`` uses
            :data:`DEFAULT_APPROVAL_TIMEOUT_SECONDS`. Clamped to
            ``[0, MAX_APPROVAL_TIMEOUT_SECONDS]``.
        delivery_channel: optional channel hint (``"voice"`` /
            ``"telegram"`` / ``"gui"``). The router decides based on
            the active mode but a request may pin to a specific channel.
    """

    kind: str
    prompt: str = ""
    actor: str = ""
    scope_key: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: Optional[float] = None
    delivery_channel: str = ""


@dataclass(frozen=True)
class ApprovalDecision:
    """The decision the channel / policy router supplied.

    Attributes:
        outcome: :class:`ApprovalOutcome` (ALLOW / DENY / EXPIRED).
        reason: optional free-form reason (logged in the audit trail).
        decided_at_seconds: monotonic timestamp of the decision.
        decider: short identifier of the source (``"user_voice"`` /
            ``"auto_allow_matrix"`` / ``"allowlist"``).
        metadata: opaque per-decision payload.
    """

    outcome: ApprovalOutcome
    reason: str = ""
    decided_at_seconds: float = 0.0
    decider: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome == ApprovalOutcome.ALLOW


@dataclass(frozen=True)
class ApprovalHandle:
    """Handle returned by :meth:`ApprovalRegistry.register`.

    When ``pre_resolved`` is non-None, the policy engine had a cached
    verdict and the caller can skip :meth:`wait_for_decision`.

    Attributes:
        approval_id: opaque registry key (UUID hex).
        expires_at_seconds: monotonic deadline.
        request: the original request (echoed for audit).
        pre_resolved: optional cached decision (``None`` when the
            caller must call ``wait_for_decision``).
    """

    approval_id: str
    expires_at_seconds: float
    request: ApprovalRequest
    pre_resolved: Optional[ApprovalDecision] = None


@dataclass
class _PendingApproval:
    """Internal registry entry."""

    approval_id: str
    request: ApprovalRequest
    created_at_seconds: float
    expires_at_seconds: float
    decision: Optional[ApprovalDecision] = None
    condition: threading.Condition = field(default_factory=threading.Condition)


PreResolver = Callable[[ApprovalRequest], Optional[ApprovalDecision]]


def _clamp_timeout(value: Optional[float]) -> float:
    """Clamp to ``[0.0, MAX_APPROVAL_TIMEOUT_SECONDS]``."""
    if value is None:
        return DEFAULT_APPROVAL_TIMEOUT_SECONDS
    if value < 0:
        return 0.0
    if value > MAX_APPROVAL_TIMEOUT_SECONDS:
        return MAX_APPROVAL_TIMEOUT_SECONDS
    return float(value)


class ApprovalRegistry:
    """Two-phase approval registry.

    Thread-safe. Construct one per orchestrator (or use
    :func:`get_approval_registry` for the module singleton).

    Args:
        clock: optional time source for tests; defaults to
            :func:`time.monotonic`.
        default_timeout_seconds: default per-request expiry.
        pre_resolver: optional callable consulted at registration time;
            if it returns an :class:`ApprovalDecision`, the registry
            stores it and the handle carries it as ``pre_resolved``
            so the caller can skip ``wait_for_decision``. Returns
            ``None`` to indicate "no cached verdict; wait for the
            channel router".
    """

    def __init__(
        self,
        *,
        clock: Optional[Callable[[], float]] = None,
        default_timeout_seconds: float = DEFAULT_APPROVAL_TIMEOUT_SECONDS,
        pre_resolver: Optional[PreResolver] = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self._default_timeout = _clamp_timeout(default_timeout_seconds)
        self._pre_resolver = pre_resolver
        self._pending: dict[str, _PendingApproval] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Phase 1: register

    def register(self, request: ApprovalRequest) -> ApprovalHandle:
        """Create a registry entry. Returns the handle.

        Side effects: consults the pre-resolver (if any) AND stores
        the verdict in the same critical section so a racing
        ``wait_for_decision`` either sees the decision or blocks
        cleanly until one arrives.
        """
        approval_id = uuid.uuid4().hex
        timeout = _clamp_timeout(request.timeout_seconds if request.timeout_seconds is not None else self._default_timeout)
        now = self._clock()
        expires_at = now + timeout
        # Compute pre-resolved verdict OUTSIDE the registry lock to
        # avoid holding it across user-supplied callable execution.
        pre_resolved: Optional[ApprovalDecision] = None
        if self._pre_resolver is not None:
            try:
                pre_resolved = self._pre_resolver(request)
            except Exception:  # noqa: BLE001 -- pre-resolver must not crash registration
                LOGGER.warning("pre-resolver raised; treating as no cached verdict", exc_info=True)
                pre_resolved = None
            if pre_resolved is not None:
                pre_resolved = ApprovalDecision(
                    outcome=pre_resolved.outcome,
                    reason=pre_resolved.reason,
                    decided_at_seconds=now,
                    decider=pre_resolved.decider or "pre_resolver",
                    metadata=pre_resolved.metadata,
                )
        entry = _PendingApproval(
            approval_id=approval_id,
            request=request,
            created_at_seconds=now,
            expires_at_seconds=expires_at,
            decision=pre_resolved,
        )
        with self._lock:
            self._pending[approval_id] = entry
        return ApprovalHandle(
            approval_id=approval_id,
            expires_at_seconds=expires_at,
            request=request,
            pre_resolved=pre_resolved,
        )

    # ------------------------------------------------------------------
    # Phase 2: wait

    def wait_for_decision(
        self,
        approval_id: str,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> ApprovalDecision:
        """Block until a decision arrives or the expiry deadline elapses.

        Returns:
            :class:`ApprovalDecision`. ``outcome`` is ``EXPIRED`` if
            no decision arrived in time, ``NOT_FOUND`` if the
            ``approval_id`` was never registered (or was already
            cleared).
        """
        with self._lock:
            entry = self._pending.get(approval_id)
            if entry is None:
                return ApprovalDecision(
                    outcome=ApprovalOutcome.NOT_FOUND,
                    decided_at_seconds=self._clock(),
                    reason="approval_id not found",
                )
        # Block on the per-entry condition until either decision is set
        # or the deadline passes. The condition is acquired without the
        # registry lock so multiple waiters don't block each other's
        # entries.
        with entry.condition:
            while entry.decision is None and self._clock() < entry.expires_at_seconds:
                remaining = entry.expires_at_seconds - self._clock()
                wait_for = min(max(poll_interval_seconds, 0.0), max(remaining, 0.0))
                if wait_for <= 0:
                    break
                entry.condition.wait(timeout=wait_for)
            decision = entry.decision
            now = self._clock()
        if decision is None:
            decision = ApprovalDecision(
                outcome=ApprovalOutcome.EXPIRED,
                decided_at_seconds=now,
                reason="approval expired before decision arrived",
            )
            with self._lock:
                # Mark the entry as expired so duplicate waits return
                # the same expiry.
                entry.decision = decision
        return decision

    # ------------------------------------------------------------------
    # Decision recording (called by channel routers)

    def record_decision(
        self,
        approval_id: str,
        outcome: ApprovalOutcome,
        *,
        reason: str = "",
        decider: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """Store the channel router's decision; wake any waiters.

        Returns:
            ``True`` when the entry was found and updated. ``False``
            when the approval id is unknown OR already decided.
        """
        with self._lock:
            entry = self._pending.get(approval_id)
            if entry is None:
                return False
        with entry.condition:
            if entry.decision is not None:
                # Idempotent: first decision wins.
                return False
            entry.decision = ApprovalDecision(
                outcome=outcome,
                reason=reason,
                decided_at_seconds=self._clock(),
                decider=decider,
                metadata=metadata or {},
            )
            entry.condition.notify_all()
        return True

    def record_allow(self, approval_id: str, *, decider: str = "", reason: str = "") -> bool:
        """Convenience: :meth:`record_decision` with ``ApprovalOutcome.ALLOW``."""
        return self.record_decision(
            approval_id, ApprovalOutcome.ALLOW, reason=reason, decider=decider,
        )

    def record_deny(self, approval_id: str, *, decider: str = "", reason: str = "") -> bool:
        return self.record_decision(
            approval_id, ApprovalOutcome.DENY, reason=reason, decider=decider,
        )

    # ------------------------------------------------------------------
    # Inspection

    def peek(self, approval_id: str) -> ApprovalOutcome:
        """Non-blocking status check.

        Returns ``PENDING`` while waiting, ``NOT_FOUND`` if the
        approval id is unknown, or the actual outcome once decided.
        """
        with self._lock:
            entry = self._pending.get(approval_id)
            if entry is None:
                return ApprovalOutcome.NOT_FOUND
            if entry.decision is not None:
                return entry.decision.outcome
            if self._clock() >= entry.expires_at_seconds:
                return ApprovalOutcome.EXPIRED
            return ApprovalOutcome.PENDING

    def list_pending(self, *, scope_key: Optional[str] = None) -> tuple[ApprovalHandle, ...]:
        """Snapshot of pending approvals (no decision yet, not expired)."""
        out: list[ApprovalHandle] = []
        with self._lock:
            now = self._clock()
            for entry in self._pending.values():
                if entry.decision is not None:
                    continue
                if now >= entry.expires_at_seconds:
                    continue
                if scope_key is not None and entry.request.scope_key != scope_key:
                    continue
                out.append(
                    ApprovalHandle(
                        approval_id=entry.approval_id,
                        expires_at_seconds=entry.expires_at_seconds,
                        request=entry.request,
                    )
                )
        return tuple(out)

    def cancel(self, approval_id: str, *, reason: str = "cancelled") -> bool:
        """Force-deny + wake any waiters (e.g. orchestrator shutdown)."""
        return self.record_decision(
            approval_id, ApprovalOutcome.DENY, reason=reason, decider="cancel",
        )

    def clear(self) -> None:
        """Test helper: drop every entry. Wakes any waiters with EXPIRED."""
        with self._lock:
            for entry in list(self._pending.values()):
                with entry.condition:
                    if entry.decision is None:
                        entry.decision = ApprovalDecision(
                            outcome=ApprovalOutcome.EXPIRED,
                            decided_at_seconds=self._clock(),
                            reason="registry cleared",
                        )
                        entry.condition.notify_all()
            self._pending.clear()

    # ------------------------------------------------------------------
    # Composite: register + (skip-or-wait)

    def request_decision(
        self,
        request: ApprovalRequest,
        *,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> ApprovalDecision:
        """Convenience: register + skip-when-pre-resolved + wait.

        Returns the final :class:`ApprovalDecision` directly. Use
        when the caller doesn't need the handle in between.
        """
        handle = self.register(request)
        if handle.pre_resolved is not None:
            return handle.pre_resolved
        return self.wait_for_decision(handle.approval_id, poll_interval_seconds=poll_interval_seconds)


# ----------------------------------------------------------------------
# Module-level singleton


_registry_singleton: Optional[ApprovalRegistry] = None
_registry_lock = threading.Lock()


def get_approval_registry() -> ApprovalRegistry:
    """Module-level singleton accessor."""
    global _registry_singleton
    with _registry_lock:
        if _registry_singleton is None:
            _registry_singleton = ApprovalRegistry()
        return _registry_singleton


def set_approval_registry(registry: ApprovalRegistry) -> None:
    """Replace the singleton (init / tests)."""
    global _registry_singleton
    with _registry_lock:
        _registry_singleton = registry


def reset_approval_registry_for_testing() -> None:
    """Drop the singleton; next :func:`get_approval_registry` returns fresh."""
    global _registry_singleton
    with _registry_lock:
        _registry_singleton = None


__all__ = [
    "ApprovalDecision",
    "ApprovalHandle",
    "ApprovalOutcome",
    "ApprovalRegistry",
    "ApprovalRequest",
    "DEFAULT_APPROVAL_TIMEOUT_SECONDS",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MAX_APPROVAL_TIMEOUT_SECONDS",
    "PreResolver",
    "get_approval_registry",
    "reset_approval_registry_for_testing",
    "set_approval_registry",
]
