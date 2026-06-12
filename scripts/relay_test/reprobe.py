r"""Focused re-probe of the cases that failed manual review, each run N times
(several failures were intermittent), plus regression checks on the snap
callouts that already worked. Loads the gaming 3B once.

    python scripts/relay_test/reprobe.py
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "relay_test"))
from kenning.audio.relay_speech import match_relay_command, build_relay_line
from harness import _load_llm

N = 3

# (label, command, what to look for)
CASES = [
    # first-person self-status MUST keep "I'm ..."
    ("FP retake",   "tell my team I am playing for retake", "I'm playing for retake"),
    ("FP main",     "tell my team I am fighting for main control", "I'm fighting for main control"),
    ("FP offsite",  "tell my team I am playing off site", "I'm playing off site"),
    ("FP aggro",    "tell my team I am playing aggressive", "I'm playing aggressive"),
    ("FP force",    "tell my team I am force buying a gun", "I'm force buying"),
    # directive FORMS of the same verbs MUST stay imperative commands
    ("DIR retake",  "tell my team to play for retake", "Play for retake (command)"),
    ("DIR main",    "tell my team to fight for main control", "Fight for main control (command)"),
    ("DIR offsite", "tell my team to play off site", "Play off site (command)"),
]

llm = _load_llm()
for label, text, want in CASES:
    cmd = match_relay_command(text)
    print(f"\n### {label}  | want: {want}")
    print(f"    IN: {text!r}")
    if cmd is None:
        print("    -> NONE (no match!)"); continue
    for i in range(N):
        line = build_relay_line(cmd, llm=llm, rephrase=True, recent_lines=[])
        print(f"    -> {line!r}")
