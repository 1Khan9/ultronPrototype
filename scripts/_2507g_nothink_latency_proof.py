"""Throwaway proof: the 2507g (standard-attention Qwen3-4B-Instruct-2507) with the
ported no-think guards emits NO hidden reasoning, AND its latency matches the 3.5
(F16 KV + n_ubatch 256 avoid llama.cpp PR #23907's q8_0+flash decode collapse).

Run from the main checkout with Ultron STOPPED (needs the GPU):
    .venv\\Scripts\\python.exe scripts\\_2507g_nothink_latency_proof.py
"""
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def out(line=""):
    print(line.encode("ascii", "replace").decode("ascii"), flush=True)


try:
    import torch  # noqa: F401
except Exception as e:  # noqa: BLE001
    print(f"[warn] torch import failed ({e})")

from llama_cpp import Llama  # noqa: E402

sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from kenning.llm.inference import (  # noqa: E402
    LLMEngine, _ident_uses_nothink_prefill,
)

MODEL = os.path.join(
    os.getcwd(), "models",
    "Josiefied-Qwen3-4B-Instruct-2507-gabliterated-v2.i1-Q4_K_M.gguf",
)

SYSTEM = "You are Ultron, his cold-machine AI on comms. Answer in character."
# The exact prompts that broke the 3.5 (repeated garbage) + a reasoning bait.
USERS = [
    "Who is Tony Stark? Answer in one sentence.",
    "What are pandas? One sentence.",
    "Reyna is flaming you. Respond in two cold sentences.",
    "If the spike has 12 seconds left and a defuse takes 7 seconds, can I "
    "defuse in time? Think it through step by step.",
]


def naive_chatml(messages):
    parts = [f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages]
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def vram():
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
             "--format=csv,noheader"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"(nvidia-smi failed: {e})"


def main():
    assert _ident_uses_nothink_prefill(MODEL), "2507g must trigger the no-think guards"
    out(f"predicate: 2507g uses no-think prefill guards = "
        f"{_ident_uses_nothink_prefill(MODEL)}")
    out(f"Loading {os.path.basename(MODEL)} (F16 KV, n_ubatch 256, chat handler) ...")
    handler = LLMEngine._build_qwen35_chat_handler()
    out(f"chat_handler built (Jinja no-think override): {handler is not None}")
    t_load = time.monotonic()
    llm = Llama(
        model_path=MODEL, n_ctx=4096, n_gpu_layers=-1, flash_attn=True,
        type_k=1, type_v=1, n_batch=2048, n_ubatch=256, verbose=False,
        chat_handler=handler,
    )
    out(f"LOADED in {time.monotonic() - t_load:.1f}s  | VRAM used,free = {vram()}\n")

    # warm up (first call pays a one-time cost)
    llm.create_completion(prompt=LLMEngine._build_qwen35_nothink_prompt(
        [{"role": "user", "content": "hi"}]), max_tokens=4)

    rows = []
    for u in USERS:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": u}]
        out("=" * 72)
        out(f"USER: {u}")

        # GUARDED prefill = the LIVE voice path. Stream for TTFT + tok/s.
        prompt = LLMEngine._build_qwen35_nothink_prompt(messages)
        t0 = time.monotonic()
        ttft = None
        toks = 0
        chunks = []
        for ch in llm.create_completion(
                prompt=prompt, max_tokens=256, temperature=0.3, top_p=0.9,
                stop=["<|im_end|>", "<think>"], stream=True):
            piece = ch["choices"][0].get("text", "")
            if piece:
                if ttft is None:
                    ttft = (time.monotonic() - t0) * 1000.0
                toks += 1
                chunks.append(piece)
        total = time.monotonic() - t0
        txt = "".join(chunks).strip()
        tps = toks / total if total > 0 else 0
        has_think = "<think>" in txt
        out(f"[GUARDED] ttft={ttft:.0f}ms total={total * 1000:.0f}ms tokens={toks} "
            f"tok/s={tps:.1f} <think>={has_think}")
        out(f"   -> {txt[:160]!r}")

        # UNGUARDED naive: does the 2507g reason by default?
        o2 = llm.create_completion(
            prompt=naive_chatml(messages), max_tokens=256, temperature=0.3,
            top_p=0.9, stop=["<|im_end|>"])
        n2 = o2["usage"]["completion_tokens"]
        t2 = o2["choices"][0]["text"]
        reasoned = ("<think>" in t2 and "</think>" in t2
                    and len(t2.split("<think>", 1)[1].split("</think>", 1)[0].strip()) > 0)
        out(f"[UNGUARDED] tokens={n2} reasoned={reasoned}")

        rows.append((u, ttft, tps, toks, has_think, reasoned))

    out("\n" + "=" * 72)
    out(f"{'prompt':<40}{'ttft':>7}{'tok/s':>7}{'<think>':>9}{'reasoned':>10}")
    for u, ttft, tps, toks, ht, r in rows:
        out(f"{u[:38]:<40}{ttft:>6.0f}{tps:>7.1f}{str(ht):>9}{str(r):>10}")
    ok = all(not ht for *_, ht, _ in rows)
    out(f"\nNO-THINK: every guarded row <think>=False -> {ok}")
    out("LATENCY: compare tok/s to the 3.5's ~44 tok/s warm (F16 KV). q8_0+flash "
        "would be ~42 (collapsed); F16 here should be >= the 3.5.")


if __name__ == "__main__":
    main()
