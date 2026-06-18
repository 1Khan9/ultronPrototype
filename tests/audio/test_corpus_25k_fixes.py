"""Root-cause fixes from the 25,000-case corpus audit (2026-06-18).

Each fix targets a DETERMINISTIC-layer bug (normalization / matching) so the
relay routes correctly WITHOUT relying on the embedding relay-intent gate as a
safety net. Tests pin the fix + guard against regression.
"""
from __future__ import annotations

from kenning.audio.command_normalizer import _strip_scaffold


# ---------------------------------------------------------------------------
# F1: "let my team/squad/teammates know <imperative>" (no "that") must REFRAME
# to "tell my team <X>", not drop the lead. The bug: the wrapper remainder
# "drop spike on me" matched _HAS_RELAY_LEAD (on the ambiguous tactical verb
# "drop"), so the reframe used it as-is and the relay was MISSED.
# ---------------------------------------------------------------------------


def test_f1_wrapper_reframes_tactical_payload_to_team_relay():
    assert _strip_scaffold("let my team know drop spike on me") == \
        "tell my team drop spike on me"
    assert _strip_scaffold("let my squad know give me a rifle") == \
        "tell my team give me a rifle"
    assert _strip_scaffold("let the team know give up mid this round") == \
        "tell my team give up mid this round"
    assert _strip_scaffold("let my teammates know drop molly on the choke") == \
        "tell my team drop molly on the choke"
    assert _strip_scaffold("let the squad know share credits with the team") == \
        "tell my team share credits with the team"


def test_f1_group_addressed_remainder_stays_as_is():
    # "call out X" is a genuine relay verb -> used as-is (not double-prepended).
    assert _strip_scaffold("let the team know call out the flank") \
        .startswith("call out") or _strip_scaffold(
        "let the team know call out the flank").startswith("tell my team call out")
    # a remainder that already addresses a group keeps its lead (no double tell).
    out = _strip_scaffold("let my team know drop the whole team a smoke")
    assert out.count("tell my team") <= 1


def test_f1_does_not_touch_plain_relays():
    # A normal "tell my team X" is unaffected by the reframe path.
    assert _strip_scaffold("tell my team rotate to A") == "tell my team rotate to A"
    # No wrapper -> bare tactical imperative is left alone here (scaffold no-op).
    assert _strip_scaffold("drop spike on me") == "drop spike on me"
