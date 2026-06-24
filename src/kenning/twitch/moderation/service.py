"""S11 — ModerationService: the deterministic propose/confirm bridge that turns a
SPOKEN moderation command into a safe Helix write.

This is the in-process glue between the two existing isolated libraries:

  * :class:`~kenning.twitch.moderation.helix.HelixClient` — the self-idempotent
    Helix write shim (ban / timeout / delete-message), and
  * :class:`~kenning.twitch.moderation.guard.ModerationGuard` — the
    server-authoritative resolve(name)->user_id + authorize(action, target)
    + audit + mass-action breaker gate.

It exposes a TWO-PHASE flow so a misheard "ban" never fires without the
streamer's explicit confirmation:

    parse(text)   -> ModCommand | None     (pure, deterministic)
    prepare(text) -> ModProposal | None     (parse + resolve + authorize -> readback)
    confirm(prop) -> dict                    (re-check + the single Helix write)

and a one-shot ``execute(text)`` for the ``require_readback_confirm=False`` mode
(prepare immediately followed by confirm).

DETERMINISM / SAFETY invariants (CLAUDE.md BR-P1 + the S11 board):
  * The abliterated LLM is NEVER in the moderation decision path. Parsing is pure
    regex/keyword; authorization is the guard. NO model is imported or called
    here.
  * Ambiguous resolution NEVER auto-picks — the candidates are surfaced and the
    proposal is blocked until the human disambiguates.
  * Every public method is FAIL-SAFE: it never raises into the caller. A parse /
    resolve / authorize / Helix fault degrades to a not-ready proposal or an
    ``{"ok": False, ...}`` result, logged at WARNING.
  * The guard owns the audit + breaker; :meth:`confirm` advances the breaker via
    ``guard.authorize`` (done in :meth:`prepare`) and records the applied action
    via ``guard.record_applied`` exactly once — no double logging.

ANTICHEAT (BR-P1): stdlib + rapidfuzz + ``kenning.twitch.*`` only. No
``requests``/``aiohttp``/``websockets``/``transformers``/``torch`` and no
desktop/input/screen libs. HTTP is the HelixClient's concern; this module never
opens a socket.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from kenning.twitch.moderation.guard import ModerationGuard
from kenning.twitch.moderation.helix import HelixClient, HelixError

logger = logging.getLogger("kenning.twitch.moderation.service")

__all__ = [
    "ModCommand",
    "ModProposal",
    "ModerationService",
]

# Twitch timeout bounds (seconds): 1 .. 1_209_600 (14 days). Mirrors
# HelixClient.timeout_user's own validation so a clamp upstream never trips it.
_MIN_TIMEOUT_S = 1
_MAX_TIMEOUT_S = 1_209_600
_DEFAULT_TIMEOUT_S = 600  # the spec default when a timeout names no duration

# Time-unit -> seconds for duration parsing.
_UNIT_SECONDS = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "s": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "m": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
    "h": 3600,
    "day": 86400,
    "days": 86400,
    "d": 86400,
}
_UNIT_ALT = "|".join(sorted(_UNIT_SECONDS, key=len, reverse=True))

# A leading mod verb is REQUIRED — we never infer a moderation action from a bare
# name. Each pattern is anchored at the start of the (stripped, lowercased) text.
#
# Order matters: more specific verbs (untimeout / remove timeout) are matched
# before the generic ones so "remove timeout bob" is not read as a "timeout".
_RE_UNTIMEOUT = re.compile(
    r"^(?:un[\s-]?timeout|remove(?:\s+the)?\s+timeout(?:\s+on|\s+for)?)\s+(?P<name>.+?)\s*$"
)
_RE_UNBAN = re.compile(
    r"^(?:un[\s-]?ban|remove(?:\s+the)?\s+ban(?:\s+on|\s+for)?|lift(?:\s+the)?\s+ban(?:\s+on|\s+for)?)\s+(?P<name>.+?)\s*$"
)
# delete <name>['s] (last|that) message  — the target is a chatter; the actual
# message_id is supplied upstream by the caller at confirm time.
_RE_DELETE = re.compile(
    r"^(?:delete|remove|purge)\s+(?P<name>.+?)(?:'s|s')?\s+(?:last|latest|that|this|the)?\s*message\s*$"
)
# timeout / time out <name> [for] [<N> <unit>] [reason ...]
_RE_TIMEOUT = re.compile(
    r"^(?:time[\s-]?out|to)\s+(?P<rest>.+?)\s*$"
)
# ban <name> [for <reason...>]
_RE_BAN = re.compile(
    r"^(?:ban|permaban|perma[\s-]?ban)\s+(?P<rest>.+?)\s*$"
)

# Inside a timeout body: pull a duration ("for 10 minutes", "10 min", "600 s") and
# (separately) an optional reason that is NOT the duration. The duration token may
# be absent (=> default).
_RE_DURATION = re.compile(
    r"(?:\bfor\s+)?(?P<num>\d+)\s*(?P<unit>" + _UNIT_ALT + r")\b",
    re.IGNORECASE,
)
# A trailing "for <reason>" clause (only when it is NOT a duration phrase).
_RE_REASON = re.compile(r"\bfor\s+(?P<reason>.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ModCommand:
    """A parsed, deterministic moderation command (no resolution / authz yet).

    Attributes:
        action: one of ``"ban" | "timeout" | "untimeout" | "unban" | "delete"``.
        target_name: the RAW spoken/typed chatter name (un-resolved).
        duration_seconds: timeout duration in seconds (clamped to Twitch bounds);
            ``0`` for every non-timeout action.
        reason: optional human reason (``""`` when none was spoken).
    """

    action: str
    target_name: str
    duration_seconds: int = 0
    reason: str = ""


@dataclass
class ModProposal:
    """A prepared proposal: the parsed command plus its resolution / authz state
    and the exact spoken read-back the streamer confirms.

    ``ok`` is True ONLY when the target resolved to a single user AND the guard
    authorized the action — i.e. the proposal is ready to execute. When ``ok`` is
    False, ``reason_blocked`` says why ("ambiguous" / "not_found" / "protected" /
    "rate_limited" / "parse" / "empty_target") and ``candidates`` lists the
    possible logins on the ambiguous path (NEVER auto-picked).
    """

    command: ModCommand
    target_user_id: Optional[str] = None
    resolved_name: str = ""
    readback: str = ""
    ok: bool = False
    reason_blocked: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)


class ModerationService:
    """Deterministic propose/confirm moderation service over Helix + the guard.

    Args:
        helix: a :class:`HelixClient` (injected; tests pass a recording mock).
        guard: a :class:`ModerationGuard` (resolution + authorization + audit).
        broadcaster_id: the channel owner's user id (the ``broadcaster_id`` Helix
            scope; also the acting channel).
        moderator_id: the bot/moderator user id performing the action.
        roster_provider: a zero-arg callable returning ``{name: user_id}`` of
            recent chatters (the read-sidecar buffer feeds this upstream). It is
            informational here — the guard does its OWN fresh roster lookup on
            resolve — but it lets the service short-circuit to "not_found" when the
            roster is empty/unavailable and is surfaced for logging.
        require_readback_confirm: when True (default) callers MUST go
            prepare -> (streamer says yes) -> confirm. When False, :meth:`execute`
            runs both back to back.

    Every public method is fail-safe; none raises into the caller.
    """

    # The set of recognized actions and the matching Helix verb.
    _ACTIONS = frozenset({"ban", "timeout", "untimeout", "unban", "delete"})

    def __init__(
        self,
        helix: HelixClient,
        guard: ModerationGuard,
        *,
        broadcaster_id: str,
        moderator_id: str,
        roster_provider: Callable[[], dict[str, str]],
        require_readback_confirm: bool = True,
        message_id_lookup: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        if helix is None:
            raise ValueError("helix is required")
        if guard is None:
            raise ValueError("guard is required")
        if not broadcaster_id or not moderator_id:
            raise ValueError("broadcaster_id and moderator_id are required")
        if not callable(roster_provider):
            raise ValueError("roster_provider must be callable")
        self._helix = helix
        self._guard = guard
        self._broadcaster_id = str(broadcaster_id)
        self._moderator_id = str(moderator_id)
        self._roster_provider = roster_provider
        self._require_confirm = bool(require_readback_confirm)
        # Optional ``login -> last message_id`` resolver (the write sidecar wires
        # this to the read sidecar's ``/last_message`` index). When present, the
        # confirm() delete branch resolves the target's last message id and issues
        # the real Helix delete; absent -> delete stays an "unsupported" no-op.
        self._message_id_lookup = message_id_lookup

    # ------------------------------------------------------------------ #
    # Phase 1 — deterministic parse
    # ------------------------------------------------------------------ #
    def parse(self, text: str) -> Optional[ModCommand]:
        """Deterministically parse ``text`` into a :class:`ModCommand`, or return
        ``None`` when it is NOT a moderation command (so the caller routes it
        elsewhere).

        Conservative by design: an explicit mod verb is REQUIRED — a bare name or
        an unrelated sentence yields ``None``. Never raises.
        """
        try:
            raw = (text or "").strip()
            if not raw:
                return None
            low = raw.lower()

            # 1) un-timeout / remove timeout  (before the generic timeout verb).
            m = _RE_UNTIMEOUT.match(low)
            if m:
                name = self._clean_name(raw, m, "name")
                return ModCommand(action="untimeout", target_name=name) if name else None

            # 2) unban / lift ban.
            m = _RE_UNBAN.match(low)
            if m:
                name = self._clean_name(raw, m, "name")
                return ModCommand(action="unban", target_name=name) if name else None

            # 3) delete <name>['s] (last|that) message.
            m = _RE_DELETE.match(low)
            if m:
                name = self._clean_name(raw, m, "name")
                return ModCommand(action="delete", target_name=name) if name else None

            # 4) timeout / time out <name> [for] [<N> <unit>] [reason].
            m = _RE_TIMEOUT.match(low)
            if m:
                return self._parse_timeout(raw, m.group("rest"))

            # 5) ban <name> [for <reason>].
            m = _RE_BAN.match(low)
            if m:
                return self._parse_ban(raw, m.group("rest"))

            return None
        except Exception as e:  # noqa: BLE001 - parse is fail-safe; never raises
            logger.warning("moderation parse failed for %r (%s); routing elsewhere", text, e)
            return None

    def _parse_ban(self, raw: str, rest_low: str) -> Optional[ModCommand]:
        """``rest_low`` is the lowercased remainder after the ban verb. Split off a
        trailing ``for <reason>`` clause; the rest is the name."""
        name_low, reason = self._split_reason(rest_low)
        name = self._slice_original(raw, name_low)
        if not name:
            return None
        return ModCommand(action="ban", target_name=name, reason=reason)

    def _parse_timeout(self, raw: str, rest_low: str) -> Optional[ModCommand]:
        """Parse the timeout body: extract a duration (default 600s) and, if a
        ``for <text>`` clause survives that is NOT the duration, a reason."""
        duration = _DEFAULT_TIMEOUT_S
        dur_match = _RE_DURATION.search(rest_low)
        consumed_span = None
        if dur_match:
            try:
                num = int(dur_match.group("num"))
            except (ValueError, TypeError):
                num = 0
            unit = dur_match.group("unit").lower()
            secs = num * _UNIT_SECONDS.get(unit, 1)
            duration = self._clamp_timeout(secs)
            consumed_span = dur_match.span()

        # Strip the duration phrase out of the body to find the name + reason.
        if consumed_span is not None:
            body = (rest_low[: consumed_span[0]] + " " + rest_low[consumed_span[1] :]).strip()
        else:
            body = rest_low
        body = re.sub(r"\bfor\b\s*$", "", body).strip()  # dangling "for" left by a removed duration

        name_low, reason = self._split_reason(body)
        name = self._slice_original(raw, name_low)
        if not name:
            # If duration ate the whole tail, the name may be the leading token.
            name_low = body.strip()
            name = self._slice_original(raw, name_low)
        if not name:
            return None
        return ModCommand(
            action="timeout",
            target_name=name,
            duration_seconds=duration,
            reason=reason,
        )

    @staticmethod
    def _split_reason(body_low: str) -> tuple[str, str]:
        """Split a ``<name> for <reason>`` body into (name, reason). When there is
        no ``for`` clause the whole body is the name and reason is ``""``."""
        m = _RE_REASON.search(body_low)
        if not m:
            return body_low.strip(), ""
        reason = m.group("reason").strip()
        name = body_low[: m.start()].strip()
        if not name:
            # "ban for ..." with no name before the clause => treat the lot as a name
            # (degenerate); caller resolution will fail it.
            return body_low.strip(), ""
        return name, reason

    @staticmethod
    def _clamp_timeout(secs: int) -> int:
        if secs < _MIN_TIMEOUT_S:
            return _MIN_TIMEOUT_S
        if secs > _MAX_TIMEOUT_S:
            return _MAX_TIMEOUT_S
        return int(secs)

    @staticmethod
    def _clean_name(raw: str, match: re.Match[str], group: str) -> str:
        """Map a lowercased regex group back onto the ORIGINAL text so the spoken
        casing/display is preserved for the read-back, then strip trailing
        possessive/punctuation noise."""
        name_low = match.group(group).strip()
        name = ModerationService._slice_original(raw, name_low)
        return name

    @staticmethod
    def _slice_original(raw: str, name_low: str) -> str:
        """Find ``name_low`` (a lowercased fragment) inside ``raw`` and return the
        original-cased slice, trimmed of surrounding punctuation. Falls back to the
        lowercased fragment when it can't be located."""
        name_low = (name_low or "").strip().strip(".,!?")
        if not name_low:
            return ""
        idx = raw.lower().find(name_low)
        if idx >= 0:
            original = raw[idx : idx + len(name_low)]
        else:
            original = name_low
        # Drop a trailing possessive and stray punctuation.
        original = re.sub(r"(?:'s|s')$", "", original.strip())
        original = original.strip(" .,!?'\"")
        return original

    # ------------------------------------------------------------------ #
    # Phase 2 — resolve + authorize -> a confirmable proposal
    # ------------------------------------------------------------------ #
    def prepare(self, text: str) -> Optional[ModProposal]:
        """Parse ``text``, resolve the target via the guard, authorize the action,
        and build the spoken read-back.

        Returns ``None`` ONLY when :meth:`parse` returns ``None`` (not a mod
        command). Otherwise always returns a :class:`ModProposal`; ``ok`` is True
        only when resolved + authorized. Never raises.
        """
        cmd = self.parse(text)
        if cmd is None:
            return None
        try:
            return self._prepare_command(cmd)
        except Exception as e:  # noqa: BLE001 - prepare is fail-safe
            logger.warning("moderation prepare failed for %r (%s)", text, e)
            return ModProposal(
                command=cmd,
                resolved_name=cmd.target_name,
                readback=self._readback(cmd, cmd.target_name, ok=False, reason="error"),
                ok=False,
                reason_blocked="error",
            )

    def _prepare_command(self, cmd: ModCommand) -> ModProposal:
        # The roster_provider is informational; the guard does its own fresh
        # lookup. We surface an empty/failed roster as a quick "not_found".
        try:
            roster = self._roster_provider() or {}
        except Exception as e:  # noqa: BLE001 - a failing provider fails CLOSED
            logger.warning("roster_provider raised (%s); treating roster as empty", e)
            roster = {}

        resolution = self._guard.resolve(cmd.target_name)
        candidates = [dict(c) for c in (resolution.candidates or ())]

        # Ambiguous -> surface candidates, NEVER auto-pick.
        if resolution.ambiguous:
            return ModProposal(
                command=cmd,
                target_user_id=None,
                resolved_name=cmd.target_name,
                readback=self._readback(cmd, cmd.target_name, ok=False, reason="ambiguous"),
                ok=False,
                reason_blocked="ambiguous",
                candidates=candidates,
            )

        # No match.
        if not resolution.user_id:
            # If we had a non-empty roster but still no match, it's a genuine miss;
            # an empty roster is also "not_found" from the caller's perspective.
            _ = roster  # surfaced for logging/diagnostics; resolution is authoritative
            return ModProposal(
                command=cmd,
                target_user_id=None,
                resolved_name=cmd.target_name,
                readback=self._readback(cmd, cmd.target_name, ok=False, reason="not_found"),
                ok=False,
                reason_blocked="not_found",
                candidates=candidates,
            )

        target_id = str(resolution.user_id)
        resolved_login = self._login_for(candidates, target_id, cmd.target_name)

        # Authorize (this also advances the mass-action breaker window + audits).
        verdict = self._guard.authorize(cmd.action, target_id)
        if not verdict.allowed:
            blocked = self._map_block_reason(verdict.reason)
            return ModProposal(
                command=cmd,
                target_user_id=target_id,
                resolved_name=resolved_login,
                readback=self._readback(cmd, resolved_login, ok=False, reason=blocked),
                ok=False,
                reason_blocked=blocked,
                candidates=candidates,
            )

        return ModProposal(
            command=cmd,
            target_user_id=target_id,
            resolved_name=resolved_login,
            readback=self._readback(cmd, resolved_login, ok=True, reason=""),
            ok=True,
            reason_blocked="",
            candidates=candidates,
        )

    @staticmethod
    def _login_for(candidates: list[dict[str, Any]], target_id: str, fallback: str) -> str:
        for c in candidates:
            if str(c.get("user_id")) == target_id:
                login = c.get("login") or c.get("display_name")
                if login:
                    return str(login)
        return fallback

    @staticmethod
    def _map_block_reason(guard_reason: str) -> str:
        """Map the guard's authorize reason onto the proposal's vocabulary."""
        if guard_reason == "protected_target":
            return "protected"
        if guard_reason == "mass_action_breaker":
            return "rate_limited"
        if guard_reason == "empty_target":
            return "not_found"
        return guard_reason or "blocked"

    # ------------------------------------------------------------------ #
    # read-back rendering
    # ------------------------------------------------------------------ #
    def _readback(self, cmd: ModCommand, name: str, *, ok: bool, reason: str) -> str:
        """The exact spoken confirmation/feedback string.

        On the happy path this is the "Confirm?" prompt the streamer answers; on a
        blocked path it states why no action will be taken.
        """
        who = name or cmd.target_name or "that user"
        if ok:
            if cmd.action == "ban":
                base = f"Ban viewer {who}"
                if cmd.reason:
                    base += f" for {cmd.reason}"
                return base + ". Confirm?"
            if cmd.action == "timeout":
                return f"Timeout viewer {who} for {self._humanize_duration(cmd.duration_seconds)}. Confirm?"
            if cmd.action == "untimeout":
                return f"Remove the timeout on viewer {who}. Confirm?"
            if cmd.action == "unban":
                return f"Unban viewer {who}. Confirm?"
            if cmd.action == "delete":
                return f"Delete {who}'s last message. Confirm?"
            return f"{cmd.action} viewer {who}. Confirm?"

        # Blocked read-backs.
        if reason == "ambiguous":
            return f"More than one chatter matches {who}. Which one?"
        if reason == "not_found":
            return f"No recent chatter named {who}. Nothing done."
        if reason == "protected":
            return f"{who} is protected. Refusing."
        if reason == "rate_limited":
            return "Too many moderation actions in a row. Holding off."
        return f"Cannot {cmd.action} {who}. Nothing done."

    @staticmethod
    def _humanize_duration(seconds: int) -> str:
        if seconds % 86400 == 0 and seconds >= 86400:
            n = seconds // 86400
            return f"{n} day" + ("s" if n != 1 else "")
        if seconds % 3600 == 0 and seconds >= 3600:
            n = seconds // 3600
            return f"{n} hour" + ("s" if n != 1 else "")
        if seconds % 60 == 0 and seconds >= 60:
            n = seconds // 60
            return f"{n} minute" + ("s" if n != 1 else "")
        return f"{seconds} second" + ("s" if seconds != 1 else "")

    def _lookup_message_id(self, login: str) -> Optional[str]:
        """Resolve the target's most-recent message_id via the injected lookup.
        Fail-safe: a missing lookup / a raise / an empty result -> ``None``."""
        if self._message_id_lookup is None or not login:
            return None
        try:
            mid = self._message_id_lookup(login)
        except Exception as e:  # noqa: BLE001 - a lookup fault never raises into confirm
            logger.warning("message_id_lookup raised for %r (%s)", login, e)
            return None
        return str(mid) if mid else None

    # ------------------------------------------------------------------ #
    # Phase 3 — confirm -> the single Helix write
    # ------------------------------------------------------------------ #
    def confirm(self, proposal: ModProposal) -> dict[str, Any]:
        """Execute a previously prepared, READY proposal against Helix.

        Re-checks ``proposal.ok`` (a stale/blocked proposal performs NO write) and
        dispatches the matching HelixClient method with the configured
        broadcaster/moderator ids. On success the guard records the applied action
        (single audit row — the guard already logged the ALLOWED verdict at
        authorize time). Catches :class:`HelixError` and any unexpected fault and
        returns a structured ``{"ok": False, ...}`` — never raises.

        Returns a dict: ``{"ok", "action", "target", "detail"}`` (plus ``"error"``
        on failure).
        """
        if proposal is None:
            return {"ok": False, "action": "", "target": "", "error": "no_proposal"}
        cmd = proposal.command
        action = cmd.action
        target = proposal.target_user_id or ""
        if not proposal.ok:
            reason = proposal.reason_blocked or "not_ready"
            logger.info("moderation confirm skipped (not ok: %s) action=%s", reason, action)
            return {
                "ok": False,
                "action": action,
                "target": proposal.resolved_name or cmd.target_name,
                "error": reason,
            }

        # untimeout / unban / delete are surfaced but require an unban / message-id
        # endpoint that the injected HelixClient in scope does not expose as a
        # write here (delete needs a message_id supplied upstream; unban/untimeout
        # map to the unban endpoint not in this client). We dispatch what the
        # client CAN do (ban / timeout) and report a clear, non-raising result for
        # the rest so the caller can route those to the appropriate handler.
        try:
            if action == "ban":
                result = self._helix.ban_user(
                    self._broadcaster_id, self._moderator_id, target, reason=cmd.reason
                )
            elif action == "timeout":
                result = self._helix.timeout_user(
                    self._broadcaster_id,
                    self._moderator_id,
                    target,
                    duration_s=cmd.duration_seconds or _DEFAULT_TIMEOUT_S,
                    reason=cmd.reason,
                )
            elif action in ("unban", "untimeout"):
                # Twitch has no separate untimeout endpoint — a timeout is a
                # temporary ban, so DELETE /moderation/bans lifts either one.
                result = self._helix.unban_user(
                    self._broadcaster_id, self._moderator_id, target
                )
            else:
                # delete: resolve the target's LAST message id via the injected
                # lookup (the read sidecar's /last_message index) and issue the real
                # Helix single-message delete. Without a lookup, or with no recent
                # message, report a clear non-raising result.
                message_id = self._lookup_message_id(proposal.resolved_name or cmd.target_name)
                if not message_id:
                    reason = "unsupported_action" if self._message_id_lookup is None else "no_message"
                    detail = (
                        "delete needs a message_id lookup (not configured)"
                        if self._message_id_lookup is None
                        else "no recent message found for that user to delete"
                    )
                    logger.info(
                        "moderation confirm: delete for target=%s -> %s", target, reason,
                    )
                    return {
                        "ok": False,
                        "action": action,
                        "target": proposal.resolved_name or target,
                        "error": reason,
                        "detail": detail,
                    }
                result = self._helix.delete_message(
                    self._broadcaster_id, self._moderator_id, message_id,
                )
        except HelixError as e:
            logger.warning(
                "helix %s failed for target=%s: status=%s (%s)",
                action, target, getattr(e, "status", None), e,
            )
            return {
                "ok": False,
                "action": action,
                "target": proposal.resolved_name or target,
                "error": "helix_error",
                "detail": str(e),
            }
        except Exception as e:  # noqa: BLE001 - confirm is fail-safe
            logger.warning("moderation confirm unexpected failure (%s)", e)
            return {
                "ok": False,
                "action": action,
                "target": proposal.resolved_name or target,
                "error": "unexpected_error",
                "detail": str(e),
            }

        # Record the applied action exactly once (the guard logged ALLOWED already).
        try:
            self._guard.record_applied(
                action,
                target,
                idempotent=getattr(result, "idempotent", False),
                status=getattr(result, "status", None),
            )
        except Exception as e:  # noqa: BLE001 - audit must never break the result
            logger.warning("record_applied failed (%s); action already applied", e)

        return {
            "ok": bool(getattr(result, "ok", False)),
            "action": action,
            "target": proposal.resolved_name or target,
            "detail": {
                "idempotent": bool(getattr(result, "idempotent", False)),
                "status": getattr(result, "status", None),
                "target_user_id": target,
            },
        }

    # ------------------------------------------------------------------ #
    # one-shot path (only when readback confirmation is disabled)
    # ------------------------------------------------------------------ #
    def apply_chat_settings(self, cmd: Any) -> dict[str, Any]:
        """Apply a parsed chat-settings command (clear / slow / follower / sub /
        emote / unique) directly to Helix. Channel-scoped + reversible, so no
        per-target resolve / read-back. Fail-safe: a HelixError / unexpected fault
        degrades to a structured ``{"ok": False, ...}`` — never raises."""
        try:
            if getattr(cmd, "clear", False):
                result = self._helix.clear_chat(self._broadcaster_id, self._moderator_id)
            else:
                settings = dict(getattr(cmd, "settings", None) or {})
                if not settings:
                    return {"ok": False, "error": "empty_settings"}
                result = self._helix.update_chat_settings(
                    self._broadcaster_id, self._moderator_id, settings)
        except HelixError as e:
            logger.warning("chat-settings helix failed: status=%s (%s)",
                           getattr(e, "status", None), e)
            return {"ok": False, "error": "helix_error", "detail": str(e),
                    "readback": getattr(cmd, "readback", "")}
        except Exception as e:  # noqa: BLE001 - apply is fail-safe
            logger.warning("chat-settings apply unexpected failure (%s)", e)
            return {"ok": False, "error": "unexpected_error", "detail": str(e)}
        return {
            "ok": bool(getattr(result, "ok", False)),
            "readback": getattr(cmd, "readback", ""),
            "detail": {"status": getattr(result, "status", None)},
        }

    def execute(self, text: str) -> dict[str, Any]:
        """prepare + immediately confirm — for ``require_readback_confirm=False``.

        When confirmation is REQUIRED (the default), this refuses with
        ``{"ok": False, "error": "confirmation_required"}`` and the read-back so a
        caller can't bypass the two-phase guard by accident. When ``text`` is not a
        moderation command, returns ``{"ok": False, "error": "not_a_command"}``.
        Never raises.
        """
        proposal = self.prepare(text)
        if proposal is None:
            return {"ok": False, "action": "", "target": "", "error": "not_a_command"}
        if self._require_confirm:
            logger.info("execute() called but readback confirmation is required")
            return {
                "ok": False,
                "action": proposal.command.action,
                "target": proposal.resolved_name or proposal.command.target_name,
                "error": "confirmation_required",
                "readback": proposal.readback,
            }
        return self.confirm(proposal)
