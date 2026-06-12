"""Mode policy primitive: plan / act / gaming / coding gating.

Adapted from cline's ``StateManager.getGlobalSettingsKey("mode")`` +
``PlanModeRespondHandler`` pattern (Apache 2.0; see
``THIRD_PARTY_NOTICES.md``). Ultron's variant generalises beyond the
binary plan/act cline shape so the same primitive can gate gaming-mode
side-effects, coding-architect-vs-editor splits, and per-skill
``default_mode`` overrides.

Key shapes:

* :class:`Mode` -- one canonical enum used by every caller (intent
  classifier, orchestrator, LLM router, safety validator, supervisor).
* :class:`ModePolicy` -- frozen per-mode policy (allows tool side
  effects? wraps the response with a plan prefix? requires confirmation
  before execution?).
* :class:`PendingConfirmation` -- record of a queued plan awaiting the
  user's "do it" intent.
* :class:`ModeSession` -- per-session state machine. Tracks the current
  mode, flips on intent, expires pending confirmations after a TTL.

The primitive is I/O-free + clock-injectable + RLock-guarded.
Callers wire their own:

* intent-to-flip mapping (the voice path's ``engage_plan_mode`` etc.
  intents call ``ModeSession.flip(target_mode)``);
* prompt wrapping (the orchestrator's pre-LLM-request hook calls
  ``ModePolicy.wrap_user_prompt``);
* confirmation acceptance (the voice path's ``do_it`` intent calls
  ``ModeSession.consume_pending_confirmation(...)``).
"""

from __future__ import annotations

import enum
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional


class Mode(str, enum.Enum):
    """Canonical mode identifiers.

    Strings double as YAML keys so the same identifiers appear in
    ``config.yaml`` under ``voice.mode`` and friends.
    """

    #: Default executing mode. Tools fire; responses stream straight
    #: through to TTS.
    ACT = "act"

    #: Discussion mode. The LLM proposes an approach; tools do NOT
    #: fire until the user says "do it". The response is wrapped with
    #: a plan ack template.
    PLAN = "plan"

    #: Coding-architect sub-mode. Like ``PLAN`` but specifically for
    #: the supervisor's architect dispatch (the architect narrates,
    #: the editor only runs on confirm).
    CODING_ARCHITECT = "coding_architect"

    #: Coding-editor sub-mode. Default for code edits inside the
    #: supervisor; tools fire.
    CODING_EDITOR = "coding_editor"

    #: Gaming sub-mode. Conservative auto-approvals, lower verbosity,
    #: cheap LLM preset.
    GAMING = "gaming"


@dataclass(frozen=True)
class ModePolicy:
    """Per-mode behavioural policy.

    Attributes:
        mode: the :class:`Mode` this policy applies to.
        allows_tool_side_effects: when ``False`` the orchestrator MUST
            NOT dispatch tool calls; the response is treated as a plan
            proposal instead.
        requires_confirmation: when ``True`` the LLM response is
            queued as a :class:`PendingConfirmation` and only executes
            on a subsequent "do it" intent.
        wrap_prefix_template: string template prepended to the LLM
            response before it streams to TTS. ``{plan}`` placeholder
            interpolates the LLM body. Empty string disables wrapping.
        confirmation_timeout_seconds: TTL on a pending confirmation.
            Defaults to 30 seconds (voice path is faster than the
            cline 5-second cline default but slower than the 1-second
            barge-in window).
        confirmation_ack_template: voice-friendly ack template the
            orchestrator speaks while queuing the plan. Empty string
            disables the ack.
        llm_preset_override: optional preset name; when set, the
            orchestrator's LLM-mode-router (T13b) swaps to this preset
            for any generation in this mode. ``None`` keeps the
            current preset.
        notes: free-form annotation -- shown in the audit log.
    """

    mode: Mode
    allows_tool_side_effects: bool = True
    requires_confirmation: bool = False
    wrap_prefix_template: str = ""
    confirmation_timeout_seconds: float = 30.0
    confirmation_ack_template: str = ""
    llm_preset_override: Optional[str] = None
    notes: str = ""

    def wrap_response(self, body: str) -> str:
        """Apply the wrap-prefix template to ``body`` when configured."""
        if not self.wrap_prefix_template:
            return body
        return self.wrap_prefix_template.format(plan=body)

    def build_ack(self) -> str:
        """Render the per-mode confirmation ack (or empty string)."""
        return self.confirmation_ack_template


DEFAULT_PLAN_PREFIX: str = (
    "Here is my plan: {plan}\n\n"
    "Say 'do it' to proceed, or describe how to adjust."
)

DEFAULT_PLAN_ACK: str = (
    "Got it. I'll wait for 'do it'."
)

DEFAULT_CODING_ARCHITECT_PREFIX: str = (
    "Architect plan:\n{plan}\n\n"
    "Say 'go' to dispatch, or refine."
)


DEFAULT_POLICIES: Mapping[Mode, ModePolicy] = {
    Mode.ACT: ModePolicy(mode=Mode.ACT, allows_tool_side_effects=True),
    Mode.PLAN: ModePolicy(
        mode=Mode.PLAN,
        allows_tool_side_effects=False,
        requires_confirmation=True,
        wrap_prefix_template=DEFAULT_PLAN_PREFIX,
        confirmation_ack_template=DEFAULT_PLAN_ACK,
    ),
    Mode.CODING_ARCHITECT: ModePolicy(
        mode=Mode.CODING_ARCHITECT,
        allows_tool_side_effects=False,
        requires_confirmation=True,
        wrap_prefix_template=DEFAULT_CODING_ARCHITECT_PREFIX,
        confirmation_ack_template="Standing by for 'go'.",
    ),
    Mode.CODING_EDITOR: ModePolicy(
        mode=Mode.CODING_EDITOR,
        allows_tool_side_effects=True,
    ),
    Mode.GAMING: ModePolicy(
        mode=Mode.GAMING,
        allows_tool_side_effects=True,
        notes="conservative auto-approvals, terse responses",
    ),
}


@dataclass(frozen=True)
class PendingConfirmation:
    """One outstanding plan awaiting a user 'do it' confirmation.

    Attributes:
        confirmation_id: stable UUID identifier (the consumer cites it
            when the 'do it' intent fires).
        mode: the mode that produced this plan.
        plan_body: the wrapped plan text (already had the prefix
            template applied -- this is the literal string the user
            heard).
        raw_plan_body: the unwrapped LLM body (the prompt-only
            payload for downstream tool dispatch).
        created_at: monotonic-ish wall-clock seconds.
        expires_at: ``created_at + timeout``; ``0`` disables expiry.
        intent_topic: optional intent-classifier label the plan was
            associated with (e.g. ``"GAMING_ENGAGE"`` so a cancelling
            intent can match).
        callback_token: free-form opaque token the consumer can use to
            re-attach the plan to its own dispatch path.
    """

    confirmation_id: str
    mode: Mode
    plan_body: str
    raw_plan_body: str
    created_at: float
    expires_at: float = 0.0
    intent_topic: str = ""
    callback_token: str = ""

    def is_expired(self, now: float) -> bool:
        return self.expires_at > 0.0 and now >= self.expires_at


@dataclass(frozen=True)
class ModeFlipResult:
    """Result of a :meth:`ModeSession.flip` call.

    Attributes:
        previous_mode: the mode that was active before the flip.
        new_mode: the mode that is active after the flip (same as
            ``previous_mode`` when the flip is a no-op).
        was_change: ``True`` when ``previous_mode != new_mode``.
        invalidated_confirmations: ids of pending confirmations the
            flip cancelled (e.g. flipping to ``ACT`` while a plan is
            pending discards that plan).
    """

    previous_mode: Mode
    new_mode: Mode
    was_change: bool
    invalidated_confirmations: tuple[str, ...] = ()


_DEFAULT_CLOCK: Callable[[], float] = time.monotonic


class ModeSession:
    """Per-session mode state machine + pending-confirmation queue.

    Args:
        initial_mode: the mode the session starts in.
        policies: optional mapping of :class:`Mode` to
            :class:`ModePolicy`. Missing entries fall back to
            :data:`DEFAULT_POLICIES`. Passing ``{}`` uses the defaults
            for every mode.
        clock: optional injectable clock returning monotonic-ish
            seconds. Defaults to :func:`time.monotonic`. Useful for
            tests.
    """

    def __init__(
        self,
        *,
        initial_mode: Mode = Mode.ACT,
        policies: Optional[Mapping[Mode, ModePolicy]] = None,
        clock: Callable[[], float] = _DEFAULT_CLOCK,
    ) -> None:
        self._lock = threading.RLock()
        self._mode: Mode = initial_mode
        self._policies: dict[Mode, ModePolicy] = dict(DEFAULT_POLICIES)
        if policies:
            self._policies.update(policies)
        self._clock = clock
        self._pending: dict[str, PendingConfirmation] = {}
        self._flip_history: list[ModeFlipResult] = []
        self._flip_history_cap: int = 32

    # ------------------------------------------------------------------
    # Mode state
    # ------------------------------------------------------------------

    @property
    def mode(self) -> Mode:
        with self._lock:
            return self._mode

    def policy(self) -> ModePolicy:
        """Return the policy for the *current* mode."""
        with self._lock:
            return self._policies.get(self._mode, DEFAULT_POLICIES[Mode.ACT])

    def policy_for(self, mode: Mode) -> ModePolicy:
        """Return the policy for ``mode`` (fall back to defaults)."""
        with self._lock:
            return self._policies.get(mode, DEFAULT_POLICIES.get(mode, DEFAULT_POLICIES[Mode.ACT]))

    def set_policy(self, policy: ModePolicy) -> None:
        """Replace the policy entry for ``policy.mode``."""
        with self._lock:
            self._policies[policy.mode] = policy

    def flip(
        self,
        target_mode: Mode,
        *,
        invalidate_pending: bool = True,
    ) -> ModeFlipResult:
        """Switch to ``target_mode`` and (optionally) cancel pending plans.

        Args:
            target_mode: the mode to switch into.
            invalidate_pending: when ``True`` (default) any pending
                confirmations are dropped (the user's mode flip is
                interpreted as "discard the queued plan, do something
                else"). When ``False`` the pending queue carries over.

        Returns:
            A :class:`ModeFlipResult` describing what changed.
        """
        with self._lock:
            previous = self._mode
            self._mode = target_mode
            invalidated: tuple[str, ...] = ()
            if invalidate_pending and self._pending:
                invalidated = tuple(self._pending.keys())
                self._pending.clear()
            result = ModeFlipResult(
                previous_mode=previous,
                new_mode=target_mode,
                was_change=previous != target_mode,
                invalidated_confirmations=invalidated,
            )
            self._flip_history.append(result)
            if len(self._flip_history) > self._flip_history_cap:
                self._flip_history = self._flip_history[-self._flip_history_cap:]
            return result

    def flip_history(self) -> tuple[ModeFlipResult, ...]:
        with self._lock:
            return tuple(self._flip_history)

    # ------------------------------------------------------------------
    # Pending-confirmation queue
    # ------------------------------------------------------------------

    def queue_plan(
        self,
        plan_body: str,
        *,
        raw_plan_body: str = "",
        mode: Optional[Mode] = None,
        timeout_override: Optional[float] = None,
        intent_topic: str = "",
        callback_token: str = "",
    ) -> PendingConfirmation:
        """Queue a plan awaiting the user's confirmation.

        Args:
            plan_body: the wrapped plan text the user heard (the
                output of :meth:`ModePolicy.wrap_response`).
            raw_plan_body: the unwrapped LLM body (the prompt-only
                payload to be re-played on confirmation). Defaults to
                ``plan_body`` when omitted.
            mode: optional override for the policy lookup; defaults to
                the current mode.
            timeout_override: optional confirmation TTL in seconds;
                ``0`` disables expiry; ``None`` uses the policy default.
            intent_topic: optional intent-classifier label.
            callback_token: optional opaque token (e.g. a tool-call
                envelope id) the consumer can use to re-bind the plan
                to its dispatch path on confirmation.

        Returns:
            The :class:`PendingConfirmation` that was queued.
        """
        target_mode = mode or self.mode
        policy = self.policy_for(target_mode)
        timeout = (
            timeout_override
            if timeout_override is not None
            else policy.confirmation_timeout_seconds
        )
        now = self._clock()
        confirmation = PendingConfirmation(
            confirmation_id=uuid.uuid4().hex,
            mode=target_mode,
            plan_body=plan_body,
            raw_plan_body=raw_plan_body or plan_body,
            created_at=now,
            expires_at=now + timeout if timeout > 0 else 0.0,
            intent_topic=intent_topic,
            callback_token=callback_token,
        )
        with self._lock:
            self._pending[confirmation.confirmation_id] = confirmation
        return confirmation

    def peek_latest_pending(self) -> Optional[PendingConfirmation]:
        """Return the most recently queued pending confirmation (or None)."""
        with self._lock:
            self._evict_expired_locked()
            if not self._pending:
                return None
            return next(reversed(self._pending.values()))

    def pending_confirmations(self) -> tuple[PendingConfirmation, ...]:
        """Snapshot the live (non-expired) pending queue."""
        with self._lock:
            self._evict_expired_locked()
            return tuple(self._pending.values())

    def consume_pending_confirmation(
        self,
        confirmation_id: Optional[str] = None,
        *,
        intent_topic_filter: str = "",
    ) -> Optional[PendingConfirmation]:
        """Pop a pending confirmation and return it (or None when none match).

        Args:
            confirmation_id: optional explicit id; when omitted the
                most-recent live pending entry is consumed.
            intent_topic_filter: optional intent-topic filter; the
                consumed entry must match this topic (use for
                "do it" intents scoped to a specific subsystem).

        Returns:
            The popped :class:`PendingConfirmation`, or ``None``.
        """
        with self._lock:
            self._evict_expired_locked()
            if confirmation_id is not None:
                pending = self._pending.pop(confirmation_id, None)
                if pending is None:
                    return None
                if intent_topic_filter and pending.intent_topic != intent_topic_filter:
                    # Put it back; the consumer cited the wrong topic.
                    self._pending[confirmation_id] = pending
                    return None
                return pending
            if not self._pending:
                return None
            candidates = list(self._pending.values())
            if intent_topic_filter:
                candidates = [c for c in candidates if c.intent_topic == intent_topic_filter]
                if not candidates:
                    return None
            chosen = candidates[-1]
            self._pending.pop(chosen.confirmation_id, None)
            return chosen

    def cancel_pending(
        self,
        confirmation_id: Optional[str] = None,
        *,
        intent_topic_filter: str = "",
    ) -> tuple[str, ...]:
        """Cancel matching pending confirmation(s) without consuming them.

        Args:
            confirmation_id: optional explicit id; when omitted ALL
                non-expired pending entries matching the topic filter
                are cancelled.
            intent_topic_filter: optional topic filter.

        Returns:
            Tuple of cancelled confirmation ids.
        """
        with self._lock:
            self._evict_expired_locked()
            if confirmation_id is not None:
                pending = self._pending.pop(confirmation_id, None)
                if pending is None:
                    return ()
                if intent_topic_filter and pending.intent_topic != intent_topic_filter:
                    self._pending[confirmation_id] = pending
                    return ()
                return (confirmation_id,)
            doomed: list[str] = []
            for cid, pending in list(self._pending.items()):
                if intent_topic_filter and pending.intent_topic != intent_topic_filter:
                    continue
                doomed.append(cid)
            for cid in doomed:
                self._pending.pop(cid, None)
            return tuple(doomed)

    def pending_count(self) -> int:
        with self._lock:
            self._evict_expired_locked()
            return len(self._pending)

    def clear(self) -> None:
        """Drop ALL pending confirmations + flip history (keeps current mode)."""
        with self._lock:
            self._pending.clear()
            self._flip_history.clear()

    # ------------------------------------------------------------------
    # Wrap helpers
    # ------------------------------------------------------------------

    def wrap_response(self, body: str, *, mode: Optional[Mode] = None) -> str:
        """Apply the current (or specified) mode's wrap template to ``body``."""
        policy = self.policy_for(mode) if mode else self.policy()
        return policy.wrap_response(body)

    def should_execute_tools(self, mode: Optional[Mode] = None) -> bool:
        """Return ``True`` when tool side-effects are allowed in the mode."""
        policy = self.policy_for(mode) if mode else self.policy()
        return policy.allows_tool_side_effects

    def confirmation_required(self, mode: Optional[Mode] = None) -> bool:
        """Return ``True`` when responses must queue + await confirmation."""
        policy = self.policy_for(mode) if mode else self.policy()
        return policy.requires_confirmation

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_expired_locked(self) -> None:
        now = self._clock()
        doomed = [
            cid for cid, pending in self._pending.items()
            if pending.is_expired(now)
        ]
        for cid in doomed:
            self._pending.pop(cid, None)


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------

_LIVE_SESSIONS: dict[str, ModeSession] = {}
_REGISTRY_LOCK = threading.RLock()


def get_mode_session(session_id: str) -> ModeSession:
    """Return the :class:`ModeSession` for ``session_id`` (create on miss).

    Caller-friendly singleton accessor matching the existing
    ``hooks.get_hook_registry`` pattern. Each session id gets its own
    instance; passing the same id twice returns the same object.
    """
    with _REGISTRY_LOCK:
        existing = _LIVE_SESSIONS.get(session_id)
        if existing is not None:
            return existing
        session = ModeSession()
        _LIVE_SESSIONS[session_id] = session
        return session


def drop_mode_session(session_id: str) -> bool:
    """Remove the registry entry for ``session_id`` (idempotent).

    Returns ``True`` when an entry was removed, ``False`` otherwise.
    """
    with _REGISTRY_LOCK:
        return _LIVE_SESSIONS.pop(session_id, None) is not None


def reset_registry_for_testing() -> None:
    """Test-only: drop every registry entry."""
    with _REGISTRY_LOCK:
        _LIVE_SESSIONS.clear()


__all__ = [
    "DEFAULT_CODING_ARCHITECT_PREFIX",
    "DEFAULT_PLAN_ACK",
    "DEFAULT_PLAN_PREFIX",
    "DEFAULT_POLICIES",
    "Mode",
    "ModeFlipResult",
    "ModePolicy",
    "ModeSession",
    "PendingConfirmation",
    "drop_mode_session",
    "get_mode_session",
    "reset_registry_for_testing",
]
