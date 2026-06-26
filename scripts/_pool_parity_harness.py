"""Curated-pool PARITY harness (2026-06-26).

For every deterministic route, drive the REAL build_relay_line pipeline twice:
  * route OFF -> the curated/deterministic line (the TARGET style + variety)
  * route ON  -> the LLM-authored line (what we are trying to bring to parity)
Capture N samples of each (LRU-varied) so we can compare the LLM output against
the curated pool it is meant to resemble. Writes logs/_pool_parity.json + a
readable console report. Loads ONLY the LLMEngine (the configured 4B) -- run with
the live instance STOPPED (BR-P3).
"""
import os
import re
import sys
import json

os.environ.setdefault("KENNING_U1_LLM_ROUTE", "1")
os.environ.setdefault("KENNING_FLAVOR_TAILS", "1")
os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")
for _p in (os.path.join(os.getcwd(), "src"), os.getcwd()):
    if _p not in sys.path:
        sys.path.insert(0, _p)
try:
    import torch  # noqa: F401  (registers CUDA dll dirs via kenning.__init__)
except Exception:
    pass

from kenning.llm.inference import LLMEngine
from kenning.audio.relay_speech import (
    match_relay_command, build_relay_line, set_u1_llm_route_enabled,
)


def R(s):
    return (s or "").encode("ascii", "replace").decode("ascii")


def ns(s):
    return len([x for x in re.split(r"[.!?]+", s or "") if x.strip()])


# label -> a command that exercises that deterministic route. Harvested from the
# matchers + the test corpus so each PARSES; the harness reports NO_PARSE for any
# miss so coverage gaps are visible.
BATTERY = [
    ("identity:soundboard", "sage asked if you're a soundboard"),
    ("identity:voicechanger", "jett asked if you're a voice changer"),
    ("identity:bot_ai", "my teammate asked if you are an AI, respond"),
    ("identity:recording", "reyna asked if you are a recording, respond"),
    ("identity:realperson", "jett asked if you are a real person, respond"),
    ("identity:streamer", "are you a streamer"),
    ("respond:trash", "reyna called you trash, respond"),
    ("respond:cringe", "reyna called you cringe, respond"),
    ("respond:stupid", "jett said you're stupid, respond"),
    ("respond:flaming", "jett is flaming me, respond"),
    ("reaction:niceshot_recv", "jett said nice shot, respond"),
    ("reaction:wellplayed_recv", "the team said well played, respond"),
    ("compliment:niceshot", "tell jett nice shot"),
    ("compliment:nicejob", "tell sage nice job"),
    ("criticize", "tell my team they are terrible"),
    ("encouragement", "tell my team to lock in"),
    ("clutch", "tell my team I got this"),
    ("defiance:stop", "sage told you to stop"),
    ("calm", "tell my fade to calm down"),
    ("surrender", "tell my team unlucky"),
    ("greet", "greet my team"),
    ("farewell_win", "we won, say goodbye to my team"),
    ("farewell_loss", "we lost, say goodbye to my team"),
    ("hello", "say hello to my team"),
    ("ask_day", "ask my reyna how their day was"),
    ("qa:pandas", "explain to my team what pandas are"),
    ("qa:pandas_concept", "Explain the concept of pandas to my team."),
    ("qa:eiffel", "Explain how the Eiffel Tower was built to my team."),
    ("qa:dolphins", "Explain dolphins to my team."),
    ("qa:capital", "ask my team what the capital of france is"),
    ("qa:favcolor", "answer my team what is your favorite color"),
    ("marvel:ironman", "my teammate asked about iron man, respond"),
    ("marvel:stark", "answer my team who is Tony Stark to you"),
    ("think_respond", "reyna told me the plan, respond"),
]

N = 3


def sample(cmd, eng, route_on, n=N):
    set_u1_llm_route_enabled(route_on)
    out, recent = [], []
    for _ in range(n):
        try:
            line = build_relay_line(cmd, eng, recent_lines=list(recent))
        except Exception as e:                                       # noqa: BLE001
            line = f"<ERROR: {type(e).__name__}: {e}>"
        out.append(line)
        if line:
            recent.append(line)
    return out


def main():
    eng = LLMEngine()
    report = []
    for label, text in BATTERY:
        cmd = match_relay_command(text)
        entry = {"label": label, "command": text}
        if cmd is None:
            entry["parse"] = "NO_PARSE"
            report.append(entry)
            continue
        entry["directive"] = getattr(cmd, "directive", None)
        entry["context"] = getattr(cmd, "context", None)
        entry["payload"] = getattr(cmd, "payload", None)
        entry["det"] = sample(cmd, eng, route_on=False)
        entry["llm"] = sample(cmd, eng, route_on=True)
        report.append(entry)

    for e in report:
        print("\n### %s :: %r" % (e["label"], R(e["command"])))
        if e.get("parse") == "NO_PARSE":
            print("    !! NO PARSE")
            continue
        print("    dir=%s ctx=%r pay=%r" % (
            e.get("directive"), R(str(e.get("context")))[:46],
            R(str(e.get("payload")))[:46]))
        print("    -- DETERMINISTIC (curated target) --")
        for d in e["det"]:
            print("       [det ch=%3d] %r" % (len(d or ""), R(d)))
        print("    -- LLM (route-all) --")
        for ln in e["llm"]:
            print("       [llm s=%d ch=%3d] %r" % (ns(ln), len(ln or ""), R(ln)))

    with open("logs/_pool_parity.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    n_parse = sum(1 for e in report if e.get("parse") == "NO_PARSE")
    print("\nSAVED logs/_pool_parity.json  | %d routes, %d NO_PARSE"
          % (len(report), n_parse))


if __name__ == "__main__":
    main()
