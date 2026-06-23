"""Tests for Ultron 1.0 TURBO MODE -- the flag-gated auto-relay of inferred team
callouts WITHOUT a "tell my team" prefix (2026-06-23).

Covers: the runtime flag + sensitivity triplets; the voice matchers
(match_turbo_toggle / match_turbo_sensitivity) incl. non-collision; the config
defaults (default OFF); the intent-gate turbo branch (a bare callout relays only
when turbo is ON, OFF is byte-identical) incl. the COMMAND_LOCAL precedence that
keeps the "turbo mode off" command reachable in always-listening; the dual-path
dispatch wiring; and the STOP-window TURBO button plumbing.

Hermetic: the gate's turbo branch runs the lexical recovery (recover_relay_lead),
whose semantic relay-intent gate is monkeypatched so the tests never need the
embedder sidecar and are deterministic regardless of whether one is running.
"""
import inspect

import pytest

from kenning.audio import relay_speech as rs
from kenning.audio import intent_gate as ig
from kenning.audio.intent_gate import Scenario


@pytest.fixture(autouse=True)
def _reset_turbo_flags():
    """Save/restore the process-global turbo flags so tests don't leak state."""
    t0 = rs.turbo_mode_enabled()
    a0 = rs.turbo_aggressive()
    yield
    rs.set_turbo_mode_enabled(t0)
    rs.set_turbo_aggressive(a0)


@pytest.fixture
def _relay_intent_none(monkeypatch):
    """Force the semantic relay-intent gate to the sidecar-DOWN fail-open (None) in
    BOTH bound references, so the lexical recovery deterministically prepends for
    callout-signal lines (its None-keeps-keyword-behaviour path) and the tests
    never depend on a running embedder."""
    monkeypatch.setattr("kenning.audio.command_normalizer.relay_intent_ok",
                        lambda *_a, **_k: None, raising=True)
    monkeypatch.setattr("kenning.audio._relay_intent.relay_intent_ok",
                        lambda *_a, **_k: None, raising=True)


# ---------------------------------------------------------------------------
# Flag + sensitivity triplets
# ---------------------------------------------------------------------------

def test_turbo_flag_default_off_and_setters():
    # The MODULE default is OFF (test-friendly); the orchestrator applies the
    # config default at boot. Setters round-trip.
    rs.set_turbo_mode_enabled(False)
    assert rs.turbo_mode_enabled() is False
    rs.set_turbo_mode_enabled(True)
    assert rs.turbo_mode_enabled() is True
    rs.set_turbo_aggressive(False)
    assert rs.turbo_aggressive() is False
    rs.set_turbo_aggressive(True)
    assert rs.turbo_aggressive() is True


def test_config_turbo_defaults_off():
    from kenning.config import RelaySpeechConfig, StopButtonConfig
    c = RelaySpeechConfig()
    assert c.turbo_mode is False
    assert c.turbo_aggressive is False
    sb = StopButtonConfig()
    assert sb.turbo_height == 26
    assert sb.turbo_label == "TURBO"


# ---------------------------------------------------------------------------
# Voice matchers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("turbo mode on", True),
    ("turbo on", True),
    ("turbo time", True),
    ("enable turbo", True),
    ("turn on turbo mode", True),
    ("activate turbo", True),
    ("ultron, turbo mode on", True),
    ("turbo mode off", False),
    ("turbo off", False),
    ("disable turbo", False),
    ("turn off turbo mode", False),
    ("kill turbo", False),
    ("ultron, turbo mode off", False),
    ("no more turbo", False),
])
def test_match_turbo_toggle_hits(text, expected):
    assert rs.match_turbo_toggle(text) is expected


@pytest.mark.parametrize("text", [
    "rush B",
    "they have no smokes",
    "rotate to A",
    "turbo into B then plant",   # a callout that merely says "turbo" -> not a toggle
    "the turbo is broken",
    "tell my team to rotate",
    "thinking mode on",          # other toggle
    "switch to deterministic callouts",  # route toggle
    "turbo aggressive",          # sensitivity, not on/off
    "turbo balanced",            # sensitivity, not on/off
    "",
])
def test_match_turbo_toggle_misses(text):
    assert rs.match_turbo_toggle(text) is None


@pytest.mark.parametrize("text,expected", [
    ("turbo aggressive", True),
    ("turbo mode aggressive", True),
    ("turbo high", True),
    ("turbo sensitive", True),
    ("turbo balanced", False),
    ("turbo mode balanced", False),
    ("turbo safe", False),
    ("turbo conservative", False),
    ("turbo tight", False),
])
def test_match_turbo_sensitivity_hits(text, expected):
    assert rs.match_turbo_sensitivity(text) is expected


@pytest.mark.parametrize("text", [
    "turbo on",
    "turbo off",
    "turbo mode on",
    "rush B",
    "aggressive push A",   # "aggressive" without a leading "turbo" -> not a sensitivity cmd
    "",
])
def test_match_turbo_sensitivity_misses(text):
    assert rs.match_turbo_sensitivity(text) is None


def test_turbo_toggle_distinct_from_other_toggles():
    # Disjoint vocabulary -- "turbo" never means thinking/route/flavor and vice versa.
    assert rs.match_thinking_toggle("turbo mode on") is None
    assert rs.match_llm_route_toggle("turbo mode on") is None
    assert rs.match_flavor_toggle("turbo mode on") is None
    assert rs.match_turbo_toggle("thinking mode on") is None
    assert rs.match_turbo_toggle("switch to deterministic callouts") is None
    assert rs.match_turbo_toggle("flavor off") is None


# ---------------------------------------------------------------------------
# Intent-gate turbo branch: OFF byte-identical, ON relays inferred callouts
# ---------------------------------------------------------------------------

def test_directive_callout_ignored_when_turbo_off():
    # OFF (the default): a bare directive-only callout the strict bands can't
    # structure is NOT a relay -> IGNORE (the stream/chat-safe default, unchanged).
    v = ig.classify_scenario("rotate", turbo=False)
    assert v.scenario is Scenario.IGNORE, v
    # default arg is also OFF -> identical
    assert ig.classify_scenario("rotate").scenario is Scenario.IGNORE


def test_directive_callout_relays_when_turbo_on(_relay_intent_none):
    # ON: the same bare directive relays via the lexical recovery, no prefix needed.
    v = ig.classify_scenario("rotate", turbo=True)
    assert v.scenario is Scenario.RELAY_TO_TEAM, v
    assert "turbo" in v.reason


# Clear callouts the BALANCED turbo must relay (signals / agents / facts / strong
# shapes the lexical recovery structures into a team callout).
_MUST_RELAY_BALANCED = [
    "sova hit 84",
    "rotate",
    "they are rotating",
    "planting A",
    "raze boombot A",
    "they have breach ult and fade ult",
    "I hear footsteps B",
    "cypher cam B",
    "sage do you have a heal",
    "I have A site",
    "they have kayo ult, play off site",
]


@pytest.mark.parametrize("text", _MUST_RELAY_BALANCED)
def test_balanced_turbo_relays_clear_callouts(text, _relay_intent_none):
    rs.set_turbo_aggressive(False)
    v = ig.classify_scenario(text, turbo=True)
    assert v.scenario is Scenario.RELAY_TO_TEAM, (text, v)


# Ambiguous one-word / social lines the BALANCED default deliberately HOLDS BACK
# (the user's chosen trade-off: dial up to aggressive to catch these).
_HOLD_BALANCED = ["yes", "no", "thank you", "I agree", "I disagree"]


@pytest.mark.parametrize("text", _HOLD_BALANCED)
def test_balanced_turbo_holds_back_ambiguous_social(text, _relay_intent_none):
    rs.set_turbo_aggressive(False)
    v = ig.classify_scenario(text, turbo=True)
    assert v.scenario is not Scenario.RELAY_TO_TEAM, (text, v)


def test_aggressive_turbo_gate_verdict_semantic_positive(monkeypatch):
    # AGGRESSIVE: the GATE returns RELAY_TO_TEAM for a line the lexical recovery
    # abstains on, when the semantic relay-intent gate scores it a relay; balanced
    # does NOT. (The strict matcher abstains here, so the dispatch RELAY is carried
    # by the turbo_relay_backstop -- see test_turbo_relay_backstop_wired -- not the
    # normal relay handler.)
    monkeypatch.setattr("kenning.audio.command_normalizer.relay_intent_ok",
                        lambda *_a, **_k: False)  # lexical recovery abstains
    monkeypatch.setattr("kenning.audio._relay_intent.relay_intent_ok",
                        lambda *_a, **_k: True)    # semantic gate says relay
    text = "we should probably play a bit slower this round"
    rs.set_turbo_aggressive(False)
    assert ig.classify_scenario(text, turbo=True).scenario is not Scenario.RELAY_TO_TEAM
    rs.set_turbo_aggressive(True)
    assert ig.classify_scenario(text, turbo=True).scenario is Scenario.RELAY_TO_TEAM


def test_turbo_keeps_command_local_precedence():
    # The "turbo mode off/on" + sensitivity commands must classify as COMMAND_LOCAL
    # so they survive the gate (turbo turns the loop always-listening); otherwise
    # the user could never turn turbo OFF by voice.
    for text in ("turbo mode off", "turbo mode on", "turbo aggressive", "turbo balanced"):
        v = ig.classify_scenario(text, turbo=True)
        assert v.scenario is Scenario.COMMAND_LOCAL, (text, v)


def test_turbo_does_not_relay_banter_in_balanced(_relay_intent_none):
    # A phone-opener / clearly-not-a-callout line stays IGNORE even under turbo
    # (balanced), so turbo doesn't blast conversation to the team.
    rs.set_turbo_aggressive(False)
    for text in ("hey mom how are you doing today", "I'm talking to him right now"):
        v = ig.classify_scenario(text, turbo=True)
        assert v.scenario is not Scenario.RELAY_TO_TEAM, (text, v)


def test_explicit_relay_unaffected_by_turbo_off():
    # An explicit "tell my team X" relays with or without turbo (strict matcher).
    assert ig.classify_scenario("tell my team to rush B", turbo=False).scenario \
        is Scenario.RELAY_TO_TEAM
    assert ig.classify_scenario("tell my team to rush B", turbo=True).scenario \
        is Scenario.RELAY_TO_TEAM


# ---------------------------------------------------------------------------
# Dispatch wiring (source-order assertions, like the route/verbosity toggles)
# ---------------------------------------------------------------------------

def test_dispatch_wires_turbo_in_both_paths_on_raw_stt():
    """Both dispatch paths must probe the turbo command on the RAW STT (so
    normalize can't hide "kill turbo" by prepending a relay lead AND broadcasting
    it), AFTER the llm-route toggle and BEFORE the relay handler, so explicit
    commands keep precedence and the turbo phrase itself never relays."""
    src = inspect.getsource(__import__(
        "kenning.pipeline.orchestrator", fromlist=["Orchestrator"]).Orchestrator.run)
    # Wired in BOTH the full and lean blocks, both on _raw_stt (P2 fix: the full
    # block previously passed the normalized user_text -> "kill turbo" leaked).
    assert src.count("_maybe_handle_turbo_command(_raw_stt)") == 2, \
        "turbo command must be wired on _raw_stt in BOTH dispatch paths"
    assert "_maybe_handle_turbo_command(user_text)" not in src, \
        "turbo must NOT match on normalized text (normalize hides 'kill turbo')"
    # Each turbo call follows an llm-route toggle and precedes a relay handler.
    first_turbo = src.index("_maybe_handle_turbo_command(_raw_stt)")
    assert src.index("_maybe_handle_llm_route_toggle") < first_turbo
    assert src.index("_maybe_handle_relay_speech", first_turbo) > first_turbo


def test_turbo_relay_backstop_wired():
    """The aggressive band yields a RELAY_TO_TEAM gate verdict the strict relay
    handler can't parse; a turbo-gated force-relay backstop must guarantee it still
    reaches the team (closes the gate/dispatch mismatch). Gated on
    turbo_mode_enabled() so turbo-OFF is byte-identical."""
    src = inspect.getsource(__import__(
        "kenning.pipeline.orchestrator", fromlist=["Orchestrator"]).Orchestrator.run)
    assert 'via="turbo_relay_backstop"' in src
    assert "turbo_mode_enabled" in src
    assert "RELAY_TO_TEAM" in src
    assert "force=True" in src
    # The backstop sits AFTER the per-path relay handlers (explicit relay wins) and
    # BEFORE the semantic router (the gate's RELAY verdict is authoritative).
    bs = src.index('via="turbo_relay_backstop"')
    assert src.index("SEMANTIC COMMAND ROUTER") > bs, "backstop must precede the router"


def test_classify_always_listening_passes_turbo():
    """The always-listening wrapper must thread the live turbo flag into the gate."""
    from kenning.pipeline import orchestrator as orch
    src = inspect.getsource(orch.Orchestrator._classify_always_listening)
    assert "turbo_mode_enabled" in src
    assert "turbo=" in src


def test_run_loop_uses_listening_now_for_turbo_capture():
    """The run loop's effective always-listening must be live (turbo-aware), not the
    boot-captured _always_listening, so turbo ON drives continuous capture."""
    from kenning.pipeline import orchestrator as orch
    src = inspect.getsource(orch.Orchestrator.run)
    assert "_listening_now" in src
    assert "turbo_mode_enabled" in src


# ---------------------------------------------------------------------------
# STOP-window TURBO button plumbing
# ---------------------------------------------------------------------------

def test_stop_button_accepts_turbo_kwargs():
    # The overlay ctor stores the turbo wiring without building Tk (built on show()).
    from kenning.audio.stop_button import StopButtonOverlay
    flips = []
    ov = StopButtonOverlay(
        on_stop=lambda: None,
        on_toggle_turbo=lambda v: flips.append(v),
        turbo_enabled=False,
        turbo_height=26,
        turbo_label="TURBO",
    )
    assert ov._on_toggle_turbo is not None
    assert ov._turbo_enabled is False
    assert ov._turbo_h == 26
    assert ov._turbo_label == "TURBO"


def test_orchestrator_has_turbo_runtime_setter():
    from kenning.pipeline import orchestrator as orch
    assert hasattr(orch.Orchestrator, "_set_turbo_runtime_enabled")
    src = inspect.getsource(orch.Orchestrator._set_turbo_runtime_enabled)
    assert "set_turbo_mode_enabled" in src


def test_stop_button_overlay_wired_with_turbo_callback():
    """The orchestrator constructs the overlay with the turbo toggle callback so the
    GUI button and the voice command flip the SAME runtime flag."""
    from kenning.pipeline import orchestrator as orch
    src = inspect.getsource(orch.Orchestrator.__init__)
    assert "on_toggle_turbo=self._set_turbo_runtime_enabled" in src
