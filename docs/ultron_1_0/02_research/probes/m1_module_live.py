"""Ultron 1.0 M1 end-to-end: drive the 8B through the FORMALIZED ultron_prompt module.

Closes the loop: build_relay_prompt/build_private_prompt -> LLMEngine.generate_stream -> output.
Confirms the committed module (not just the probe) yields correct, in-character, fact-preserving
relays across no/low/high verbosity + compound + named-addressee + private.
"""
import os, time
os.environ.setdefault("KENNING_LLM_PRESET", "josiefied-qwen3-8b")
os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")
import kenning  # noqa: F401
from kenning.llm.inference import LLMEngine
from kenning.audio import ultron_prompt as up


def run(eng, label, pr):
    t = time.time()
    out = "".join(eng.generate_stream(
        pr.user, system_prompt=pr.system, enable_thinking=pr.enable_thinking,
        sampling=pr.sampling, suppress_memory_context=True, record_history=False)).strip()
    leak = "<think>" in out or "</think>" in out
    print(f"\n[{label}]  ({time.time()-t:.1f}s, think_leak={leak})\n  -> {out!r}")


def main():
    eng = LLMEngine(n_ctx=4096)
    run(eng, "relay/high", up.build_relay_prompt("Sova hit 84 on A main", verbosity="high"))
    run(eng, "relay/low", up.build_relay_prompt("Sova hit 84 on A main", verbosity="low"))
    run(eng, "relay/none", up.build_relay_prompt("Sova hit 84 on A main", verbosity="none"))
    run(eng, "relay/no-flavor", up.build_relay_prompt("they have no smokes left", flavor_tail=False))
    run(eng, "relay/named", up.build_relay_prompt("heal me", addressee="Sage"))
    run(eng, "relay/compound", up.build_relay_prompt(
        "Jett hit 84, Breach hit 97, one rotating to B", compound=True))
    run(eng, "relay/agentctx", up.build_relay_prompt(
        "their sova ulted", agent_context=["Sova: initiator; ult = Hunter's Fury, 3 lethal energy blasts through walls"]))
    run(eng, "private", up.build_private_prompt("what agent should I pick on defense"))
    print("\n=== done ===")


if __name__ == "__main__":
    main()
