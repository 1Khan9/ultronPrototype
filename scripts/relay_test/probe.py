r"""Quick isolation probe: rephrase a handful of suspect commands with NO
recent-line history, to separate real prompt bugs from the harness's
back-to-back recent_lines contamination. Loads the LLM once.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))

sys.path.insert(0, str(ROOT / "scripts" / "relay_test"))
from kenning.audio.relay_speech import match_relay_command, build_relay_line
from harness import _load_llm  # gaming preset (3B abliterated) + isolated qdrant

SUSPECTS = [
    # --- SNAP callouts: must stay SHORT, literal, zero flavor ---
    "tell my team there is one mid",
    "tell my team they are vents",
    "tell my team sova hit 84",
    "tell my team last is heaven",
    "tell my team to rotate now",
    # --- ENEMY ULTS incl. MULTI-agent (keep EVERY name) ---
    "tell my team their breach has ult",
    "tell my team their fade, breach, and yoru all have ults",
    "tell my team the enemy sova and kayo both have ults",
    # --- ECO / economy tactics (off-snap, explained) ---
    "tell my team to play back and not give them guns because they are on eco",
    "tell my team to default and look for guns since we are on eco",
    "tell my team to attack a site as five because the enemy is on eco",
    "tell my team to play off site because their raze has ult",
    "tell my team I am force buying a gun",
    # --- ENEMY tendency reads ---
    "tell my team the enemy team is very aggressive and loves to rush",
    "tell my team the enemy team is very passive and are hiding like cowards",
    "tell my team the enemy team is likely defaulting",
    "tell my team the enemy yoru will tp back site",
    # --- SELF play-style ---
    "tell my team I am playing off site",
    "tell my team I am playing for retake",
    "tell my team I am fighting for main control",
    # --- BANTER directed AT Ultron -> withering clapback ---
    "jett is flaming you, respond",
    "reyna is making fun of you, respond",
    "sage just called you cringe, respond",         # MUST engage 'cringe', not 'bots'
    "breach just told you to shut up, respond",
    "neon called you a robot, respond",
    # --- MARVEL (deepest contempt for Tony Stark / Iron Man) ---
    "my teammate asked where the avengers are, respond",
    "jett asked if the avengers killed you, respond",
    "my teammate said your movie was terrible, respond",
    "reyna asked about iron man, respond",
    "my teammate asked about tony stark, respond",
    "sage asked what you think of captain america, respond",
    "yoru asked if you could beat the hulk, respond",
    "breach asked about thanos, respond",
    # --- IDENTITY (incl. streamer; brief, own it) ---
    "my teammate asked if you are an AI, respond",
    "my teammate asked if you are a streamer, respond",
    "my teammate asked if you are a bot, respond",
    # --- arrogance flavoring on a generic off-snap line ---
    "tell my team we are going to crush them",
]
_OLD_SUSPECTS = [
    # SNAP callouts -- must stay SHORT, no flavor:
    "tell my team there are two B",
    "tell my team they are vents",
    "tell my team sova hit 84",
    "tell my team I am low",
    "tell my team there is one mid",
    "tell my team I am flanking",
    "tell my team to rotate",            # snap movement -> short
    # OFF-SNAP -- should get Ultron character + verbosity:
    "tell my team they are bots",        # insult: 'You guys are complete bots'
    "tell my team to save",              # economy: explained, verbose
    "tell my mix to calm down",          # Ultron clinical de-escalation
    "tell my team aimlabs is free",      # jab with flavor
    "give my team some encouragement",
    "tell my team they are terrible",
    # IDENTITY -- as Ultron, future AI harvesting RR, brief:
    "my teammate just asked if you are a sound board, respond",
    "my teammate asked if you are an AI, respond",
    "my teammate asked if you are a voice changer, respond",
]

llm = _load_llm()

for t in SUSPECTS:
    cmd = match_relay_command(t)
    if cmd is None:
        print(f"NONE | {t!r}"); continue
    line = build_relay_line(cmd, llm=llm, rephrase=True, recent_lines=[])
    print(f"IN  {t!r}\n -> {line!r}\n")
