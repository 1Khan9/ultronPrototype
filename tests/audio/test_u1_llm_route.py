"""Tests for the Ultron 1.0 flag-gated LLM relay route wiring in relay_speech.build_relay_line.

Verifies: the flag/verbosity helpers; that the flag toggles WHICH prompt the relay LLM path uses
(lean ultron_prompt when ON vs the legacy _build_rephrase_prompt when OFF); and that flag-OFF is the
unchanged legacy behavior. Uses a captured generate_fn so no real model is loaded (hermetic).
"""
import pytest

from kenning.audio import relay_speech as rs


@pytest.fixture(autouse=True)
def _reset_flags():
    # Save/restore the process-global flags so tests don't leak state.
    route0, verb0 = rs.u1_llm_route_enabled(), rs.relay_verbosity()
    yield
    rs.set_u1_llm_route_enabled(route0)
    rs.set_relay_verbosity(verb0)


def test_flag_defaults_and_setters():
    rs.set_u1_llm_route_enabled(False)
    assert rs.u1_llm_route_enabled() is False
    rs.set_u1_llm_route_enabled(True)
    assert rs.u1_llm_route_enabled() is True
    rs.set_relay_verbosity("no flavor")
    assert rs.relay_verbosity() == "none"
    rs.set_relay_verbosity("low flavor")
    assert rs.relay_verbosity() == "low"
    rs.set_relay_verbosity("high")
    assert rs.relay_verbosity() == "high"


def _capture_prompt(payload: str):
    """Run build_relay_line on a non-tactical 'read' payload that reaches the LLM rephrase,
    capturing the prompt handed to the model. Returns (captured_prompt, output_line)."""
    captured = {}

    def gen(prompt):
        captured["prompt"] = prompt
        return ["Acknowledged. The pattern is noted."]

    cmd = rs.RelayCommand(payload=payload, raw_text=payload, addressee="team")
    line = rs.build_relay_line(cmd, llm=None, rephrase=True, generate_fn=gen, recent_lines=[])
    return captured.get("prompt"), line


def test_flag_off_uses_legacy_prompt():
    rs.set_u1_llm_route_enabled(False)
    prompt, line = _capture_prompt("they keep playing the same way every round")
    assert prompt is not None, "payload should reach the LLM rephrase path"
    # Legacy monolith markers; the lean prompt's "Now say it:" tail must be absent.
    assert "Now say it:" not in prompt
    assert line  # produced a line


def test_flag_on_uses_lean_prompt():
    rs.set_u1_llm_route_enabled(True)
    prompt, line = _capture_prompt("they keep playing the same way every round")
    assert prompt is not None, "payload should reach the LLM rephrase path"
    # Lean ultron_prompt markers.
    assert "Now say it:" in prompt
    assert "Relay this callout to your team" in prompt
    # The lean prompt is far smaller than the legacy ~3.4k-word monolith.
    assert len(prompt.split()) < 400
    assert line


def test_flag_on_injects_agent_kit_context():
    # M3: when the callout names an agent and the LLM route is ON, the agent's kit
    # facts are injected so the 8B can't hallucinate the kit.
    rs.set_u1_llm_route_enabled(True)
    prompt, line = _capture_prompt("their sova keeps playing the same way every round")
    assert prompt is not None, "payload should reach the LLM rephrase path"
    assert "Agent facts" in prompt
    assert "Sova:" in prompt and "Recon Bolt" in prompt


def test_flag_off_no_agent_kit_context():
    rs.set_u1_llm_route_enabled(False)
    prompt, _ = _capture_prompt("their sova keeps playing the same way every round")
    assert prompt is not None
    assert "Agent facts" not in prompt  # legacy prompt has no kit-context block


def _capture_compound(payload):
    cap = {}

    def gen(p):
        cap["p"] = p
        return ["Sova hit 84 and their smokes are gone. Finish them."]

    cmd = rs.RelayCommand(payload=payload, raw_text=payload, addressee="team")
    line = rs.build_relay_line(cmd, llm=None, rephrase=True, generate_fn=gen, recent_lines=[])
    return cap.get("p"), line


def test_compound_mixed_flag_on_one_combined_llm_call():
    # M4: a mixed compound (one slot fact + one read) routes through ONE LLM call
    # with the compound directive when the route is ON.
    rs.set_u1_llm_route_enabled(True)
    prompt, line = _capture_compound("Sova hit 84 and they have no smokes left")
    assert prompt is not None, "mixed compound should reach the LLM when route ON"
    assert "ONE combined" in prompt           # compound directive from build_relay_prompt
    assert "Sova hit 84 and they have no smokes left" in prompt
    assert line


def test_compound_mixed_flag_off_stays_deterministic():
    rs.set_u1_llm_route_enabled(False)
    prompt, line = _capture_compound("Sova hit 84 and they have no smokes left")
    assert prompt is None, "compound resolves deterministically (no single LLM call) when route OFF"
    assert line  # a combined deterministic line is still produced


def test_flag_on_verbosity_threads_through():
    rs.set_u1_llm_route_enabled(True)
    rs.set_relay_verbosity("none")
    prompt, _ = _capture_prompt("they keep playing the same way every round")
    from kenning.audio import ultron_prompt as up
    assert up._VERBOSITY_DIRECTIVE["none"] in prompt


# --- match_verbosity_command (the no/low/high voice command) ---

@pytest.mark.parametrize("text,expected", [
    ("no flavor", "none"),
    ("low flavor", "low"),
    ("high flavor", "high"),
    ("flavor none", "none"),
    ("set flavor to low", "low"),
    ("minimal flavor", "low"),
    ("verbosity high", "high"),
    ("make flavor high", "high"),
    ("ultron, no flavor", "none"),
])
def test_match_verbosity_command_hits(text, expected):
    assert rs.match_verbosity_command(text) == expected


@pytest.mark.parametrize("text", [
    "flavor off",          # tail toggle, NOT verbosity
    "flavor on",           # tail toggle
    "turn off the flavor", # tail toggle
    "no, the enemy is low",
    "rush B",
    "low health on their Jett",
    "they have no smokes",
    "",
])
def test_match_verbosity_command_misses(text):
    assert rs.match_verbosity_command(text) is None


def test_verbosity_does_not_steal_flavor_toggle():
    # The flavor-tail toggle owns "flavor off"/"on"; the verbosity command MUST NOT
    # claim them (it excludes the off/on level words) so the toggle still works.
    assert rs.match_flavor_toggle("flavor off") is False
    assert rs.match_verbosity_command("flavor off") is None
    assert rs.match_flavor_toggle("flavor on") is True
    assert rs.match_verbosity_command("flavor on") is None
    # "no/low/high flavor" are verbosity. NOTE: the LEGACY flavor toggle also
    # matches "no flavor" as tail-off (historical overlap); the orchestrator
    # dispatches the verbosity command FIRST (asserted below) so "no flavor"
    # resolves to verbosity none -- its new u1.0 meaning.
    assert rs.match_verbosity_command("no flavor") == "none"
    assert rs.match_verbosity_command("low flavor") == "low"
    assert rs.match_verbosity_command("high flavor") == "high"


def test_dispatch_checks_verbosity_before_flavor_toggle():
    """The orchestrator run-loop must probe the verbosity command BEFORE the flavor
    toggle in BOTH the full and lean dispatch paths, so 'no flavor' -> verbosity
    (not the legacy tail-off). Verified against the source ordering."""
    import inspect
    from kenning.pipeline import orchestrator as orch
    src = inspect.getsource(orch.Orchestrator.run)
    for vb, ft in (("_maybe_handle_verbosity_command(user_text)",
                    "_maybe_handle_flavor_toggle(user_text)"),
                   ("_maybe_handle_verbosity_command(_raw_stt)",
                    "_maybe_handle_flavor_toggle(_raw_stt)")):
        assert vb in src and ft in src, f"missing dispatch call: {vb} / {ft}"
        assert src.index(vb) < src.index(ft), f"verbosity must precede flavor toggle ({vb})"
