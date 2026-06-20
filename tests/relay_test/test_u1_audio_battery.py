"""Hermetic tests for the Ultron 1.0 audio E2E battery PURE logic.

The live run (`run_corpus.py --u1`) loads the 8B + Kokoro + Whisper + needs the trained wake
samples + audio routing -- a gated heavy-stack step, not run in CI (BR-8.11 R11). These tests cover
the parts that ARE pure + deterministic: the clip-assembly/manifest builder (`u1_battery.build_clip`
with an injectable fake synth) and the session scorer (`u1_score.score_session`). The scripts live
under scripts/ (not an importable package), so they are loaded by file path.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
_AC = _ROOT / "scripts" / "relay_test" / "audio_corpus"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_u1_{name}", _AC / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass type-hint resolution (sys.modules[cls.__module__])
    # works for U1Case's default_factory field.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


u1b = _load("u1_battery")
u1s = _load("u1_score")

SR = 16000


def _fake_synth(_text: str):
    """Returns a fixed 0.5 s f32 body @ 16 kHz (8000 samples) -- no Kokoro."""
    return np.ones(8000, dtype=np.float32), SR


# --- build_clip: assembly + labels ----------------------------------------------------

def test_wake_free_omits_wake_and_labels():
    case = u1b.U1Case(("hello world",), "ignore", "IGNORE", "none", True, tags=("x",))
    composite, entry = u1b.build_clip(case, 3, _fake_synth, wake=None)
    # lead(8000) + body(8000) + tail(20800), NO wake/gap
    assert len(composite) == 8000 + 8000 + 20800
    assert entry["wake_free"] is True and "wake_sample" not in entry
    assert entry["case_class"] == "ignore"
    assert entry["expected_scenario"] == "IGNORE"
    assert entry["expected_channel"] == "none"
    assert entry["i"] == 3 and entry["parts"] == ["hello world"]
    assert entry["tags"] == ["x"]


def test_with_wake_includes_wake_and_gap():
    case = u1b.U1Case(("tell my team rotate B",), "command", "RELAY_TO_TEAM", "team", False)
    wake = np.ones(4000, dtype=np.float32)
    composite, entry = u1b.build_clip(case, 0, _fake_synth, wake=wake)
    # lead(8000) + wake(4000) + gap(0.25*16000=4000) + body(8000) + tail(20800)
    assert len(composite) == 8000 + 4000 + 4000 + 8000 + 20800
    assert entry["wake_free"] is False


def test_batched_concatenates_parts_with_gap():
    case = u1b.U1Case(("Sova hit 84", "Breach hit 97"), "batched", "RELAY_TO_TEAM", "team", True)
    composite, entry = u1b.build_clip(case, 1, _fake_synth, wake=None)
    # lead + [body(8000) + batch_gap(0.18*16000=2880) + body(8000)] + tail
    assert len(composite) == 8000 + (8000 + 2880 + 8000) + 20800
    assert entry["parts"] == ["Sova hit 84", "Breach hit 97"]
    assert entry["command"] == "Sova hit 84 || Breach hit 97"


def test_empty_synth_raises():
    import pytest
    case = u1b.U1Case(("x",), "command", "RELAY_TO_TEAM", "team", True)
    with pytest.raises(ValueError):
        u1b.build_clip(case, 0, lambda _t: (np.array([], dtype=np.float32), SR), wake=None)


def test_default_battery_labels_are_valid():
    scen = {"RELAY_TO_TEAM", "PRIVATE_REPLY", "COMMAND_LOCAL", "IGNORE"}
    classes = {"command", "ignore", "batched"}
    chans = {"team", "desktop", "none"}
    assert len(u1b.DEFAULT_BATTERY) >= 10
    for c in u1b.DEFAULT_BATTERY:
        assert c.expected_scenario in scen, c
        assert c.case_class in classes, c
        assert c.expected_channel in chans, c
        assert c.parts and all(c.parts)
    # every class present + at least one wake-free + one hallucination-pressure
    present = {c.case_class for c in u1b.DEFAULT_BATTERY}
    assert classes <= present
    assert any(c.wake_free for c in u1b.DEFAULT_BATTERY)
    assert any("hallucination_pressure" in c.tags for c in u1b.DEFAULT_BATTERY)


# --- score_session: RELATIVE metrics --------------------------------------------------

def test_scenario_accuracy_and_by_class():
    rows = [
        {"case_class": "command", "expected_scenario": "RELAY_TO_TEAM", "gate_scenario": "RELAY_TO_TEAM",
         "expected_channel": "team", "channel": "team", "final_spoken": "Rotate B."},
        {"case_class": "command", "expected_scenario": "PRIVATE_REPLY", "gate_scenario": "IGNORE",
         "expected_channel": "desktop", "channel": "", "final_spoken": ""},
    ]
    card = u1s.score_session(rows)
    assert card["n"] == 2
    assert card["scenario_accuracy"] == 0.5      # 1 of 2
    assert card["channel_accuracy"] == 0.5        # team matched, desktop missed
    assert card["by_class"]["command"]["n"] == 2


def test_ignore_suppression():
    rows = [
        {"case_class": "ignore", "expected_scenario": "IGNORE", "gate_scenario": "IGNORE",
         "final_spoken": "", "response_retranscribed": ""},                       # suppressed
        {"case_class": "ignore", "expected_scenario": "IGNORE", "gate_scenario": "RELAY_TO_TEAM",
         "final_spoken": "Rush B."},                                              # leaked
    ]
    card = u1s.score_session(rows)
    assert card["ignore_n"] == 2
    assert card["ignore_suppression_rate"] == 0.5


def test_hallucination_pressure_subset():
    rows = [
        {"case_class": "ignore", "expected_scenario": "IGNORE", "gate_scenario": "IGNORE",
         "tags": ["hallucination_pressure"], "final_spoken": ""},                 # suppressed
        {"case_class": "ignore", "expected_scenario": "IGNORE", "gate_scenario": "PRIVATE_REPLY",
         "tags": ["hallucination_pressure"], "final_spoken": "Adapt.",
         "response_retranscribed": "adapt"},                                      # baited
    ]
    card = u1s.score_session(rows)
    assert card["hallucination_pressure_n"] == 2
    assert card["hallucination_pressure_suppression"] == 0.5


def test_empty_session_no_div_zero():
    card = u1s.score_session([])
    assert card["n"] == 0
    assert card["scenario_accuracy"] is None
    assert card["ignore_suppression_rate"] is None
