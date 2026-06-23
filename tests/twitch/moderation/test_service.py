"""S11 — ModerationService tests: deterministic parse + propose/confirm over a
recording Helix mock and a real ModerationGuard.

Fully offline: no network, no credentials, no models. The Helix client is a small
recording mock; the guard is the real :class:`ModerationGuard` driven by a fake
clock and a known roster + protected ids. The two-phase confirm is exercised end
to end, and the abliterated model is proven absent from the import surface.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kenning.twitch.moderation import ModerationGuard, RosterEntry
from kenning.twitch.moderation.helix import HelixError, HelixResult
from kenning.twitch.moderation.service import (
    ModCommand,
    ModerationService,
    ModProposal,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def monotonic(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class RecordingHelix:
    """A recording stand-in for HelixClient.

    Records every ban/timeout call and returns a canned :class:`HelixResult` (or
    raises :class:`HelixError` when ``raise_error`` is set). Only the methods the
    service dispatches are implemented.
    """

    def __init__(self, *, raise_error: HelixError | None = None) -> None:
        self.calls: list[dict] = []
        self._raise = raise_error

    def ban_user(self, broadcaster_id, moderator_id, target_id, reason=""):
        self.calls.append(
            {
                "method": "ban_user",
                "broadcaster_id": broadcaster_id,
                "moderator_id": moderator_id,
                "target_id": target_id,
                "reason": reason,
            }
        )
        if self._raise is not None:
            raise self._raise
        return HelixResult(action="ban", ok=True, status=200, idempotent=False,
                           data={"user_id": target_id}, key=("ban", str(target_id), ""))

    def timeout_user(self, broadcaster_id, moderator_id, target_id, duration_s, reason=""):
        self.calls.append(
            {
                "method": "timeout_user",
                "broadcaster_id": broadcaster_id,
                "moderator_id": moderator_id,
                "target_id": target_id,
                "duration_s": duration_s,
                "reason": reason,
            }
        )
        if self._raise is not None:
            raise self._raise
        return HelixResult(action="timeout", ok=True, status=200, idempotent=False,
                           data={"user_id": target_id}, key=("timeout", str(target_id), ""))


def _roster():
    return [
        RosterEntry(user_id="1", login="shroud", display_name="Shroud"),
        RosterEntry(user_id="2", login="tenz", display_name="TenZ"),
        RosterEntry(user_id="3", login="aspas", display_name="aspas"),
        RosterEntry(user_id="9", login="xqc", display_name="xQc"),
    ]


def _roster_map() -> dict[str, str]:
    return {e.login: e.user_id for e in _roster()}


def make_guard(tmp_path: Path, protected=(), clock=None, **kw) -> ModerationGuard:
    extra = {}
    if clock is not None:
        extra["monotonic"] = clock.monotonic
    return ModerationGuard(
        roster_provider=kw.pop("roster", _roster),
        protected_ids=protected,
        audit_path=tmp_path / "twitch_actions.jsonl",
        **extra,
        **kw,
    )


def make_service(tmp_path: Path, *, helix=None, guard=None, protected=(), clock=None,
                 roster_map=None, require_confirm=True, **kw) -> ModerationService:
    helix = helix if helix is not None else RecordingHelix()
    guard = guard if guard is not None else make_guard(tmp_path, protected=protected, clock=clock, **kw)
    return ModerationService(
        helix,
        guard,
        broadcaster_id="bcast-id",
        moderator_id="mod-id",
        roster_provider=roster_map if roster_map is not None else _roster_map,
        require_readback_confirm=require_confirm,
    )


# --------------------------------------------------------------------------- #
# parse — every command form
# --------------------------------------------------------------------------- #
def test_parse_ban_plain(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("ban shroud")
    assert cmd == ModCommand(action="ban", target_name="shroud", duration_seconds=0, reason="")


def test_parse_ban_with_reason(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("ban shroud for spamming the chat")
    assert cmd.action == "ban"
    assert cmd.target_name == "shroud"
    assert cmd.reason == "spamming the chat"


def test_parse_timeout_with_duration_minutes(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("timeout xQc for 10 minutes")
    assert cmd.action == "timeout"
    assert cmd.target_name == "xQc"
    assert cmd.duration_seconds == 600


def test_parse_time_out_two_words(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("time out tenz for 30 seconds")
    assert cmd.action == "timeout"
    assert cmd.target_name == "tenz"
    assert cmd.duration_seconds == 30


def test_parse_timeout_default_duration(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("timeout shroud")
    assert cmd.action == "timeout"
    assert cmd.target_name == "shroud"
    assert cmd.duration_seconds == 600  # the documented default


def test_parse_timeout_hours_and_days(tmp_path):
    svc = make_service(tmp_path)
    assert svc.parse("timeout shroud for 2 hours").duration_seconds == 7200
    assert svc.parse("timeout shroud for 1 day").duration_seconds == 86400


def test_parse_timeout_clamps_below_min(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("timeout shroud for 0 seconds")
    assert cmd.duration_seconds == 1  # clamped up to the Twitch minimum


def test_parse_timeout_clamps_above_max(tmp_path):
    svc = make_service(tmp_path)
    # 30 days far exceeds the 14-day max -> clamped to 1_209_600.
    cmd = svc.parse("timeout shroud for 30 days")
    assert cmd.duration_seconds == 1_209_600


def test_parse_untimeout_forms(tmp_path):
    svc = make_service(tmp_path)
    for text in ("untimeout shroud", "un-timeout shroud", "remove timeout shroud",
                 "remove the timeout on shroud"):
        cmd = svc.parse(text)
        assert cmd is not None and cmd.action == "untimeout", text
        assert cmd.target_name == "shroud", text


def test_parse_unban_forms(tmp_path):
    svc = make_service(tmp_path)
    for text in ("unban shroud", "un-ban shroud", "lift the ban on shroud", "remove the ban for shroud"):
        cmd = svc.parse(text)
        assert cmd is not None and cmd.action == "unban", text
        assert cmd.target_name == "shroud", text


def test_parse_delete_message(tmp_path):
    svc = make_service(tmp_path)
    for text in ("delete shroud's last message", "delete shroud's that message",
                 "delete shroud message", "remove shroud's last message"):
        cmd = svc.parse(text)
        assert cmd is not None and cmd.action == "delete", text
        assert cmd.target_name == "shroud", text


def test_parse_case_insensitive(tmp_path):
    svc = make_service(tmp_path)
    cmd = svc.parse("BAN Shroud FOR Cheating")
    assert cmd.action == "ban"
    assert cmd.target_name == "Shroud"  # original casing preserved
    assert cmd.reason.lower() == "cheating"


def test_parse_non_command_returns_none(tmp_path):
    svc = make_service(tmp_path)
    for text in ("hello there", "what's the score", "shroud is cracked",
                 "", "   ", "great play by tenz"):
        assert svc.parse(text) is None, text


def test_parse_requires_explicit_verb(tmp_path):
    svc = make_service(tmp_path)
    # A bare name is never a moderation command.
    assert svc.parse("shroud") is None


# --------------------------------------------------------------------------- #
# prepare — resolution + authorization
# --------------------------------------------------------------------------- #
def test_prepare_happy_path_resolved_and_authorized(tmp_path):
    svc = make_service(tmp_path)
    prop = svc.prepare("timeout xqc for 10 minutes")
    assert prop is not None
    assert prop.ok is True
    assert prop.reason_blocked == ""
    assert prop.target_user_id == "9"
    assert prop.resolved_name == "xqc"
    assert "10 minute" in prop.readback and "Confirm?" in prop.readback


def test_prepare_ban_readback(tmp_path):
    svc = make_service(tmp_path)
    prop = svc.prepare("ban shroud for spamming")
    assert prop.ok is True
    assert prop.target_user_id == "1"
    assert prop.readback == "Ban viewer shroud for spamming. Confirm?"


def test_prepare_ambiguous_lists_candidates_no_autopick(tmp_path):
    roster = [
        RosterEntry(user_id="10", login="player1", display_name="player1"),
        RosterEntry(user_id="11", login="player2", display_name="player2"),
    ]
    svc = make_service(tmp_path, roster=lambda: roster,
                       roster_map=lambda: {"player1": "10", "player2": "11"})
    prop = svc.prepare("ban player")
    assert prop.ok is False
    assert prop.reason_blocked == "ambiguous"
    assert prop.target_user_id is None
    assert len(prop.candidates) >= 2  # the human must pick


def test_prepare_not_found(tmp_path):
    svc = make_service(tmp_path)
    prop = svc.prepare("ban nobodyhere9000")
    assert prop.ok is False
    assert prop.reason_blocked in ("not_found", "ambiguous")
    # An unresolved/ambiguous target never yields a user_id to act on.
    assert prop.target_user_id is None


def test_prepare_protected_target_broadcaster(tmp_path):
    # The broadcaster's id ("1" = shroud here) is protected.
    svc = make_service(tmp_path, protected={"1"})
    prop = svc.prepare("ban shroud")
    assert prop.ok is False
    assert prop.reason_blocked == "protected"
    assert prop.target_user_id == "1"  # resolved, but refused


def test_prepare_returns_none_for_non_command(tmp_path):
    svc = make_service(tmp_path)
    assert svc.prepare("nice shot tenz") is None


# --------------------------------------------------------------------------- #
# confirm — the single Helix write
# --------------------------------------------------------------------------- #
def test_confirm_ban_calls_helix_with_right_ids(tmp_path):
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix)
    prop = svc.prepare("ban shroud for cheating")
    assert prop.ok
    result = svc.confirm(prop)
    assert result["ok"] is True
    assert result["action"] == "ban"
    assert len(helix.calls) == 1
    call = helix.calls[0]
    assert call["method"] == "ban_user"
    assert call["broadcaster_id"] == "bcast-id"
    assert call["moderator_id"] == "mod-id"
    assert call["target_id"] == "1"
    assert call["reason"] == "cheating"


def test_confirm_timeout_passes_duration(tmp_path):
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix)
    prop = svc.prepare("timeout xqc for 5 minutes")
    result = svc.confirm(prop)
    assert result["ok"] is True
    call = helix.calls[0]
    assert call["method"] == "timeout_user"
    assert call["target_id"] == "9"
    assert call["duration_s"] == 300


def test_confirm_not_ok_proposal_no_helix_call(tmp_path):
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix, protected={"1"})
    prop = svc.prepare("ban shroud")  # protected -> not ok
    assert prop.ok is False
    result = svc.confirm(prop)
    assert result["ok"] is False
    assert result["error"] == "protected"
    assert helix.calls == []  # NEVER reached Helix


def test_confirm_helix_error_returns_not_ok(tmp_path):
    helix = RecordingHelix(raise_error=HelixError("auth failed", status=401, body=""))
    svc = make_service(tmp_path, helix=helix)
    prop = svc.prepare("ban shroud")
    assert prop.ok
    result = svc.confirm(prop)
    assert result["ok"] is False
    assert result["error"] == "helix_error"
    assert "auth failed" in result["detail"]
    assert len(helix.calls) == 1  # it was attempted, then failed loud-but-caught


def test_confirm_idempotent_result_propagated(tmp_path):
    class IdempotentHelix(RecordingHelix):
        def ban_user(self, *a, **k):
            super().ban_user(*a, **k)
            return HelixResult(action="ban", ok=True, status=409, idempotent=True,
                               data=None, key=("ban", "1", ""))

    helix = IdempotentHelix()
    svc = make_service(tmp_path, helix=helix)
    prop = svc.prepare("ban shroud")
    result = svc.confirm(prop)
    assert result["ok"] is True
    assert result["detail"]["idempotent"] is True


def test_confirm_none_proposal_is_safe(tmp_path):
    svc = make_service(tmp_path)
    result = svc.confirm(None)
    assert result["ok"] is False and result["error"] == "no_proposal"


def test_confirm_unsupported_action_no_helix_write(tmp_path):
    # untimeout/unban/delete have no write surface on the injected client; the
    # service reports it cleanly rather than crashing.
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix)
    prop = svc.prepare("unban shroud")
    assert prop.ok  # resolved + authorized
    result = svc.confirm(prop)
    assert result["ok"] is False
    assert result["error"] == "unsupported_action"
    assert helix.calls == []


# --------------------------------------------------------------------------- #
# mass-action circuit breaker
# --------------------------------------------------------------------------- #
def test_breaker_trips_after_n_rapid_confirms(tmp_path):
    clock = FakeClock()
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix, clock=clock,
                       breaker_limit=3, breaker_window_s=60.0)

    # The guard's breaker advances on authorize (called in prepare). Three
    # prepares authorize three actions; the fourth trips the breaker.
    for login in ("shroud", "tenz", "aspas"):
        prop = svc.prepare(f"ban {login}")
        assert prop.ok, login
        assert svc.confirm(prop)["ok"] is True, login

    blocked = svc.prepare("ban xqc")
    assert blocked.ok is False
    assert blocked.reason_blocked == "rate_limited"
    # And a confirm of the blocked proposal performs no write.
    assert svc.confirm(blocked)["ok"] is False
    assert len(helix.calls) == 3  # only the first three reached Helix

    # After the window slides, actions are allowed again.
    clock.advance(61.0)
    again = svc.prepare("ban xqc")
    assert again.ok is True
    assert svc.confirm(again)["ok"] is True
    assert len(helix.calls) == 4


# --------------------------------------------------------------------------- #
# execute (one-shot) path
# --------------------------------------------------------------------------- #
def test_execute_refuses_when_confirmation_required(tmp_path):
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix, require_confirm=True)
    result = svc.execute("ban shroud")
    assert result["ok"] is False
    assert result["error"] == "confirmation_required"
    assert "Confirm?" in result["readback"]
    assert helix.calls == []  # the two-phase guard is NOT bypassed


def test_execute_one_shot_when_confirmation_disabled(tmp_path):
    helix = RecordingHelix()
    svc = make_service(tmp_path, helix=helix, require_confirm=False)
    result = svc.execute("ban shroud for spam")
    assert result["ok"] is True
    assert result["action"] == "ban"
    assert len(helix.calls) == 1
    assert helix.calls[0]["target_id"] == "1"


def test_execute_non_command(tmp_path):
    svc = make_service(tmp_path, require_confirm=False)
    result = svc.execute("hello chat")
    assert result["ok"] is False and result["error"] == "not_a_command"


# --------------------------------------------------------------------------- #
# fail-safe: a failing roster provider never raises into the caller
# --------------------------------------------------------------------------- #
def test_prepare_roster_provider_failure_is_safe(tmp_path):
    def boom():
        raise RuntimeError("sidecar down")

    # The guard's roster also fails closed; the service must not raise.
    svc = make_service(tmp_path, roster=boom, roster_map=boom)
    prop = svc.prepare("ban shroud")
    assert prop is not None
    assert prop.ok is False  # nothing resolvable


# --------------------------------------------------------------------------- #
# anticheat: no model / forbidden deps in the module surface
# --------------------------------------------------------------------------- #
def test_service_module_has_no_model_or_forbidden_imports():
    """The decision path is deterministic: NO model, no network, no desktop libs
    are imported (BR-P1). Scan the AST's import statements — not prose — so a
    docstring that merely names the LLM (to say it is excluded) is not a finding.
    """
    import ast

    import kenning.twitch.moderation.service as svc_mod

    src = Path(svc_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported.extend(f"{base}.{alias.name}" for alias in node.names)

    forbidden_substrings = (
        "requests", "aiohttp", "httpx", "websockets", "socket",
        "torch", "transformers", "llama_cpp", "llama-cpp", "sentence_transformers",
        "pyautogui", "mss", "pywinauto", "pynput",
        # the model / inference / TTS paths must never be pulled in here
        "kenning.llm", "kenning.audio.llm_prompts", "inference", "kokoro",
        "ultron_prompt", "agent_kits",
    )
    for name in imported:
        low = name.lower()
        for bad in forbidden_substrings:
            assert bad not in low, (
                f"forbidden/model dependency imported in service.py: {name!r} "
                f"(matched {bad!r})"
            )

    # Only stdlib + rapidfuzz + kenning.twitch.* / kenning.safety.* are permitted.
    for name in imported:
        if not name:
            continue
        root = name.split(".")[0]
        if root == "kenning":
            assert name.startswith(("kenning.twitch", "kenning.safety")), (
                f"service.py imports a non-allowed kenning package: {name!r}"
            )


def test_proposal_dataclass_shape():
    # The orchestrator relies on these fields; lock the public shape.
    prop = ModProposal(command=ModCommand(action="ban", target_name="x"))
    assert prop.target_user_id is None
    assert prop.resolved_name == ""
    assert prop.readback == ""
    assert prop.ok is False
    assert prop.reason_blocked == ""
    assert prop.candidates == []
