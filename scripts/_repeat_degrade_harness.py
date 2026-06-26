#!/usr/bin/env python
"""Repeat-degradation reproduction harness (offline, single-threaded, end-to-end).

Drives a finalized-STT string through the REAL relay/answer pipeline K times
against ONE shared LLMEngine so cross-turn KV / recent-lines state is reproduced.
Prints per-turn [route, primary token-count, spoken line] + the underlying
llama-cpp prefix-match state each turn (verbose stderr 'N prefix-match hit,
remaining M prompt tokens to eval').

ROOT HYPOTHESIS under test: two DIFFERENT prompts (qa-answer ~2845 chars vs
tactical-relay ~2298 chars) alternate against one Llama KV cache; each call
prefix-matches only ~7 of ~850 tokens against the OTHER prompt's leftover
input_ids, re-evals on a thrashed context -> the relay generation starves
(21 -> 3 -> 5 tokens), goes empty, triggers the echo-net + wrong-prompt retry.

RUN FROM  C:\\STC\\ultronPrototype  WITH ULTRON STOPPED (loads the model on the
GPU -- one instance only, BR-P3). Audio/PTT/TTS/Twitch/desktop are stubbed or
never imported; only the anticheat-clean kenning.audio.*/kenning.llm load.

  .venv\\Scripts\\python.exe scripts\\_repeat_degrade_harness.py [optional input]
  HARNESS_HARDCLEAR=1 .venv\\Scripts\\python.exe scripts\\_repeat_degrade_harness.py   # A/B
"""
from __future__ import annotations

import os
import sys
from collections import deque

os.environ.setdefault("KENNING_U1_LLM_ROUTE", "1")
os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")
os.environ.setdefault("KENNING_FLAVOR_TAILS", "1")
os.environ.setdefault("KENNING_THINK_AUDIT", "0")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (os.path.join(_ROOT, "src"), _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import torch  # noqa: F401  (claims a CUDA context early, like the app)
except Exception:
    pass

K = int(os.environ.get("HARNESS_REPEATS", "6"))
TEXT = sys.argv[1] if len(sys.argv) > 1 else "explain to my team what pandas are"
HARDCLEAR = os.environ.get("HARNESS_HARDCLEAR") == "1"

try:
    from kenning.llm.inference import LLMEngine
except Exception:
    from kenning.llm import LLMEngine  # type: ignore
from kenning.audio import relay_speech as rs

if hasattr(rs, "set_u1_llm_route_enabled"):
    rs.set_u1_llm_route_enabled(True)


def R(s):
    return (s or "").encode("ascii", "replace").decode("ascii")


def _tok(line):
    return len((line or "").split())


def _verbose(engine):
    llm = getattr(engine, "_llm", None)
    if llm is not None:
        try:
            llm.verbose = True
        except Exception:
            pass


def _dump(engine, turn):
    llm = getattr(engine, "_llm", None)
    if llm is None:
        return
    n = int(getattr(llm, "n_tokens", 0) or 0)
    try:
        ids = list(getattr(llm, "_input_ids", [])[:n])
    except Exception:
        ids = []
    print("  [t%d] BEFORE-call n_tokens=%d prior-ids=%s%s"
          % (turn, n, ids[:10], "..." if len(ids) > 10 else ""))


def _hard_clear(engine):
    """A/B knob: hard-clear KV + input_ids (NOT just reset()'s n_tokens)."""
    if not HARDCLEAR:
        return
    llm = getattr(engine, "_llm", None)
    if llm is None:
        return
    try:
        llm.reset()
        try:
            llm._ctx.kv_cache_seq_rm(-1, 0, -1)
        except Exception:
            try:
                llm._ctx.kv_cache_clear()
            except Exception:
                pass
        try:
            llm.n_tokens = 0
            llm._input_ids = llm._input_ids[:0]
        except Exception:
            pass
    except Exception as e:
        print("  hard-clear skipped:", e)


def layer_a(engine):
    """Drive the REAL relay/answer line builder K times (the leaf seam)."""
    _verbose(engine)
    for label, accumulate in (("A1 empty-recent (pure engine/KV)", False),
                              ("A2 accumulating-recent (engine + echo-net)", True)):
        print("\n" + "=" * 78)
        print("LAYER A :: %s :: HARDCLEAR=%s :: input=%r" % (label, HARDCLEAR, TEXT))
        print("=" * 78)
        recent: list = []
        cmd = rs.match_relay_command(TEXT)
        if cmd is None:
            print("  match_relay_command -> None (not a relay command); skipping")
            return
        route = rs.relay_route_info(cmd) if hasattr(rs, "relay_route_info") else "?"
        print("  route=%s" % (route,))
        for i in range(K):
            _hard_clear(engine)
            _dump(engine, i)
            try:
                line = rs.build_relay_line(cmd, engine, rephrase=True, max_chars=280,
                                           recent_lines=list(recent), raw_stt=TEXT)
            except TypeError:
                line = rs.build_relay_line(cmd, engine, recent_lines=list(recent))
            flag = "" if _tok(line) >= 6 else "   <-- DEGRADED"
            print("  [%d] tok~%2d line=%r%s" % (i, _tok(line), R(line), flag))
            if accumulate and line:
                recent.append(line)


def layer_c_alternating(engine):
    """Directly reproduce the DUAL-prompt KV-thrash: alternate two distinct
    ~850-token prompts (answer-style vs relay-style) sharing a short preamble."""
    print("\n" + "=" * 78)
    print("LAYER C :: ALTERNATING two distinct prompts (the live dual-prompt thrash)")
    print("           HARDCLEAR=%s" % HARDCLEAR)
    print("=" * 78)
    _verbose(engine)
    preamble = "You are Ultron, his cold-machine AI on comms. "
    pad = ("Context note: stay terse, in character, no vendor names. " * 18)
    sys_answer = preamble + "ANSWER the question for the team. " + pad
    sys_relay = preamble + "RELAY the callout to the team verbatim. " + pad
    samp = {"temperature": 0.8, "max_tokens": 56, "top_p": 0.9}
    pairs = [("ANSWER", sys_answer, "What are pandas? One short sentence."),
             ("RELAY", sys_relay, "Tell the team: they are pushing B.")]
    for i in range(K):
        kind, sysp, usr = pairs[i % 2]
        _hard_clear(engine)
        out = "".join(engine.generate_stream(
            usr, system_prompt=sysp, sampling=samp,
            record_history=False, enable_thinking=False))
        flag = "" if _tok(out) >= 4 else "   <-- DEGRADED/EMPTY"
        print("  [%d] %-6s tok~%2d -> %r%s" % (i, kind, _tok(out), R(out)[:80], flag))


def layer_d_different_questions(engine):
    """THE user bug (2026-06-25): DIFFERENT questions must get DIFFERENT, on-topic
    answers. The injected prior-answer made them byte-identical (every pandas
    question returned 'Pandas: black-and-white bears...'). One engine; recent_lines
    accumulates like live -- if injection is truly gone, the prior answer no longer
    contaminates the next, different question."""
    print("\n" + "=" * 78)
    print("LAYER D :: DIFFERENT questions, accumulating recent (the live bug)")
    print("=" * 78)
    qs = ["explain to my team what pandas are",
          "explain to my team why pandas suck",
          "explain to my team why pandas can't reproduce",
          "explain to my team what a transistor is"]
    recent, outs = [], []
    for q in qs:
        cmd = rs.match_relay_command(q)
        if cmd is None:
            print("  %r -> not a relay" % q); continue
        line = rs.build_relay_line(cmd, engine, rephrase=True, max_chars=280,
                                   recent_lines=list(recent), raw_stt=q)
        print("  Q=%r\n     -> %r" % (q.replace("explain to my team ", ""), R(line)))
        outs.append(line)
        if line:
            recent.append(line)
    distinct = len({o.strip().lower() for o in outs if o})
    print("\n  DISTINCT answers: %d/%d (want ALL distinct + each on-topic)"
          % (distinct, len(outs)))


def main():
    print("Loading LLMEngine (config.yaml preset) ... input=%r K=%d HARDCLEAR=%s"
          % (TEXT, K, HARDCLEAR))
    engine = LLMEngine()
    print("Engine loaded; reused across turns (cross-turn KV/input_ids/recent reproduced).")
    layer_d_different_questions(engine)
    layer_c_alternating(engine)
    layer_a(engine)
    print("\nDONE. Expect (no hardclear): turn[0] good; repeats collapse to 3-5 tok /")
    print("empty 'recovered' retry / unrelated callout. With HARNESS_HARDCLEAR=1 every")
    print("turn should stay full + on-topic -> confirms the KV-thrash + the fix.")
    print("Watch stderr 'Llama.generate: N prefix-match hit, remaining M prompt tokens':")
    print("small N + large M on a switch == the answer/relay prompts evicting each other.")


if __name__ == "__main__":
    main()
