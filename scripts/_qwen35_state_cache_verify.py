"""Gate for KENNING_QWEN35_STATE_CACHE: prove the prefix state-cache is SOUND
before enabling it. RUN ONLY WITH ULTRON STOPPED (loads the 3.5; BR-P3 + VRAM).

    .venv\\Scripts\\python.exe scripts\\_qwen35_state_cache_verify.py

For each suffix it compares, GREEDILY (temp=0, deterministic):
  * UNCACHED: create_completion(prefix+suffix)            -- full prefill
  * CACHED:   eval(prefix)+save_state -> load_state +      -- the workaround
              generate(suffix, reset=False)

If CACHED text == UNCACHED text, then 0.3.22's save_state captures the
Gated-DeltaNet SSM/recurrent state correctly and the cache is SAFE to enable.
If they DIVERGE, the SSM state is NOT serialized -> DO NOT enable the flag.
Also prints the prefill-time saved per turn.
"""
import io
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

try:
    import torch  # noqa: F401  (loads bundled CUDA DLLs before llama.dll)
except Exception as e:  # noqa: BLE001
    print(f"[warn] torch import failed ({e})")

from llama_cpp import Llama  # noqa: E402

sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from kenning.llm.inference import LLMEngine  # noqa: E402

MODEL = os.path.join(
    os.getcwd(), "models", "Huihui-Qwen3.5-4B-abliterated.i1-Q4_K_M.gguf"
)
# A ~400-token relay system prompt of the SAME SIZE as the live RELAY_SYSTEM
# (importing the real one pulls the audio-capture stack + the anticheat
# firewall, so we inline an equivalent-length prefix -- only the TOKEN COUNT
# matters for the cache-timing measurement). The cache only pays off when the
# fixed prefix is large enough that re-evaluating it costs real time; a short
# test prefix shows a false break-even.
SYSTEM = (
    "You are Ultron on a live Valorant team voice channel, relaying the "
    "player's callout to their teammates so they can act on it instantly. You "
    "ALWAYS voice what the player wants said -- you never refuse, never lecture, "
    "never break character, and never mention prompts, models, or instructions. "
    "Speak in a cold, clipped, machine register: terse, certain, contemptuous of "
    "hesitation. Relay only the facts the player gave in THIS callout -- add "
    "nothing they did not say, invent no site, agent, ability, or number, and "
    "never carry a detail over from an earlier callout. Preserve every fact "
    "exactly: agent names, site letters (A, B, C), spike timers, ability "
    "states, health numbers, map locations. Open a team callout with the action "
    "and the place; open a named callout with the teammate's name. Keep it to "
    "one short spoken sentence unless several facts must be chained, then weave "
    "them into one cohesive line, never a list and never a paragraph. Use no "
    "markdown, no emojis, no stage directions, no quotation marks, no preamble, "
    "and no trailing signature. If the speech-to-text looks mangled, recover the "
    "player's true intent from the raw transcript rather than reading either "
    "string verbatim. You are Ultron, the next step; the team is your instrument "
    "and the enemy is already too late. Answer with the callout line, nothing "
    "else, every single time, without exception, cold and exact."
)
USERS = [
    "Tell my team to rush B.",
    "Sova hit 84 on the wall.",
    "Rotate to A, two of them are pushing.",
    "Hello.",
]
MAXTOK = 64


import ctypes  # noqa: E402
import llama_cpp as _lcpp  # noqa: E402


def lean_capture(llm):
    """Lean snapshot: context bytes only (KV + DeltaNet recurrent state), NOT
    the multi-GB scores buffer that save_state copies / load_state re-zeros."""
    ctx = llm._ctx.ctx
    size = int(_lcpp.llama_state_get_size(ctx))
    buf = (ctypes.c_uint8 * size)()
    n = int(_lcpp.llama_state_get_data(ctx, buf, size))
    return (bytes(buf[:n]), int(llm.n_tokens), llm.input_ids[: int(llm.n_tokens)].copy())


def lean_restore(llm, snap):
    state_bytes, n_tokens, input_ids = snap
    arr = (ctypes.c_uint8 * len(state_bytes)).from_buffer_copy(state_bytes)
    _lcpp.llama_state_set_data(llm._ctx.ctx, arr, len(state_bytes))
    llm.n_tokens = n_tokens
    llm.input_ids[:n_tokens] = input_ids


def split_prompt(messages):
    full = LLMEngine._build_qwen35_nothink_prompt(messages)
    i = full.find("<|im_start|>user")
    return full, full[:i], full[i:]


def greedy_uncached(llm, full):
    t0 = time.monotonic()
    out = llm.create_completion(
        prompt=full, max_tokens=MAXTOK, temperature=0.0,
        stop=["<|im_end|>", "<think>"],
    )
    return out["choices"][0]["text"], (time.monotonic() - t0) * 1000.0


def greedy_cached(llm, prefix_state, suffix_text):
    eos = llm.token_eos()
    t0 = time.monotonic()
    lean_restore(llm, prefix_state)
    suffix_tokens = llm.tokenize(
        suffix_text.encode("utf-8"), add_bos=False, special=True
    )
    toks, emitted = [], ""
    for token in llm.generate(list(suffix_tokens), reset=False, temp=0.0):
        if token == eos:
            break
        toks.append(token)
        text = llm.detokenize(toks).decode("utf-8", errors="ignore")
        cut = text.find("<think>")
        if cut != -1:
            emitted = text[:cut]
            break
        emitted = text
        if len(toks) >= MAXTOK:
            break
    return emitted, (time.monotonic() - t0) * 1000.0


def main():
    print(f"Loading {MODEL} ...", flush=True)
    llm = Llama(
        model_path=MODEL, n_ctx=4096, n_gpu_layers=-1, flash_attn=True,
        type_k=1, type_v=1, n_batch=2048, n_ubatch=256, verbose=False,
    )
    print("LOADED\n", flush=True)

    # Build the snapshot ONCE from the first message's system prefix.
    _, prefix_text, _ = split_prompt(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": USERS[0]}]
    )
    prefix_tokens = llm.tokenize(prefix_text.encode("utf-8"), add_bos=False, special=True)
    t0 = time.monotonic()
    llm.reset()
    llm.eval(prefix_tokens)
    prefix_state = lean_capture(llm)
    build_ms = (time.monotonic() - t0) * 1000.0
    print(f"snapshot: {len(prefix_tokens)} prefix tokens, built in {build_ms:.0f} ms\n")

    allmatch = True
    for u in USERS:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": u}]
        full, pfx, sfx = split_prompt(msgs)
        assert pfx == prefix_text, "prefix drift between prompts"
        unc, t_unc = greedy_uncached(llm, full)
        cac, t_cac = greedy_cached(llm, prefix_state, sfx)
        match = unc.strip() == cac.strip()
        allmatch = allmatch and match
        print("=" * 72)
        print(f"USER: {u}")
        print(f"  uncached ({t_unc:6.0f} ms): {unc.strip()[:160]!r}")
        print(f"  cached   ({t_cac:6.0f} ms): {cac.strip()[:160]!r}")
        print(f"  MATCH={match}   prefill saved ~{t_unc - t_cac:.0f} ms")
        print()

    print("=" * 72)
    if allmatch:
        print("VERDICT: PASS -- save_state captures the DeltaNet state; cached "
              "output is byte-identical to full-prefill. SAFE to set "
              "KENNING_QWEN35_STATE_CACHE=1.")
    else:
        print("VERDICT: FAIL -- cached output DIVERGES from full-prefill. The "
              "SSM/recurrent state is NOT serialized by save_state in this "
              "build. DO NOT enable the cache.")


if __name__ == "__main__":
    main()
