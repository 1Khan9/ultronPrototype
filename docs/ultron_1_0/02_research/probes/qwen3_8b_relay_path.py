"""Ultron 1.0 M1 — probe the 8B through the EXISTING relay-rephrase LLM path.

Uses the relay-specific prompt (_RELAY_REPHRASE_SYSTEM + _build_rephrase_prompt + _RELAY_SAMPLING),
NOT the conversational persona. Reveals how well the current relay prompt + the 8B already authors
in-character relays (the M1 baseline) and what exemplar/verbosity injection must add.
"""
import os, time
os.environ.setdefault("KENNING_LLM_PRESET", "josiefied-qwen3-8b")
os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")

import kenning  # noqa: F401  (CUDA DLL path)
from kenning.llm.inference import LLMEngine
from kenning.audio import relay_speech as rs


def main():
    eng = LLMEngine(n_ctx=8192)  # probe-only: observe output + measure the legacy prompt size
    # (payload, addressee, context, directive, compose)
    cases = [
        ("Sova hit 84 on A main", "team", None, None, False),
        ("they have no smokes left", "team", None, None, False),
        ("rush B", "team", None, None, False),
        ("I'm planting", "team", None, None, False),
        ("Jett hit 84 and Breach hit 97", "team", None, None, False),
        ("tell Sage to heal me", "Sage", None, None, False),
        ("we lost that round but reset", "team", None, None, True),  # compose morale
    ]
    sys_p = rs._RELAY_REPHRASE_SYSTEM
    samp = dict(rs._RELAY_SAMPLING)
    samp["max_tokens"] = 64
    for payload, addr, ctx, directive, compose in cases:
        cmd = rs.RelayCommand(payload=payload, raw_text=payload, addressee=addr,
                              context=ctx, directive=directive, compose=compose)
        prompt = rs._build_rephrase_prompt(cmd, recent_lines=[])
        print(f"\n[{payload}] addr={addr} compose={compose}  PROMPT chars={len(prompt)} ~words={len(prompt.split())} sys_words={len(sys_p.split())}")
        t = time.time()
        try:
            out = "".join(eng.generate_stream(
                prompt, system_prompt=sys_p, enable_thinking=False, sampling=samp,
                suppress_memory_context=True, record_history=False))
        except Exception as e:  # noqa: BLE001
            out = f"ERROR: {e!r}"
        print(f"\n[{payload}] addr={addr} compose={compose}  ({time.time()-t:.1f}s)\n  -> {out.strip()!r}")
    print("\n=== done ===")


if __name__ == "__main__":
    main()
