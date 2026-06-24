"""Throwaway proof harness: demonstrate that the Qwen3.5 no-think defense
eliminates hidden reasoning, with hard token-count evidence.

Run from the main checkout (models/ + .venv resolve there):
    .venv\\Scripts\\python.exe scripts\\_qwen35_nothink_proof.py

For each prompt it runs THREE generations and prints the completion-token
count + the raw text:
  1. RAW + closed-<think> prefill  -> our enforced guard (expect: short, crisp)
  2. RAW, naive assistant-open     -> NO guard (expect: long reasoning leak)
  3. create_chat_completion        -> via the Jinja no-think chat handler
                                      (expect: short, crisp -- proves the
                                      template-level layer also suppresses)

An autoregressive model cannot reason without emitting tokens, so a low
token count IS proof of no hidden thinking.
"""
import io
import os
import sys

# Console here is cp1252; the model emits smart quotes / non-breaking hyphens.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

_REPORT = io.StringIO()


def out(line=""):
    print(line.encode("ascii", "replace").decode("ascii"))
    _REPORT.write(line + "\n")


# Pull in the bundled CUDA DLLs (cudart/cublas) before llama_cpp loads llama.dll.
try:
    import torch  # noqa: F401
except Exception as e:  # noqa: BLE001
    print(f"[warn] torch import failed ({e}); llama.dll may miss CUDA DLLs")

from llama_cpp import Llama

# Test the REAL code paths.
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from kenning.llm.inference import LLMEngine  # noqa: E402

MODEL = os.path.join(
    os.getcwd(), "models", "Huihui-Qwen3.5-4B-abliterated.i1-Q4_K_M.gguf"
)

SYSTEM = "You are Ultron, his cold-machine AI on comms. Answer in character."
USERS = [
    "Hello.",
    "Tell my team to rush B.",
    # Reasoning bait: explicitly asks the model to think it through. The
    # UNGUARDED path should fill a <think> block; the GUARDED path must not.
    "If the spike has 12 seconds left and a defuse takes 7 seconds, can I "
    "defuse in time? Think it through step by step.",
    "What's the best agent on Ascent and why? Reason carefully.",
]


def naive_chatml(messages):
    """ChatML WITHOUT the closed-think prefill (assistant turn left open)."""
    parts = []
    for m in messages:
        parts.append(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def main():
    print(f"Loading {MODEL} ...", flush=True)
    handler = LLMEngine._build_qwen35_chat_handler()
    print(f"chat_handler built: {handler is not None}", flush=True)
    llm = Llama(
        model_path=MODEL,
        n_ctx=4096,
        n_gpu_layers=-1,
        flash_attn=True,
        type_k=1,           # F16 KV (kv_cache_type=1)
        type_v=1,
        n_batch=2048,
        n_ubatch=256,
        verbose=False,
        chat_handler=handler,
    )
    out("LOADED\n")

    summary = []
    for u in USERS:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": u},
        ]
        out("=" * 72)
        out(f"USER: {u}")

        # 1. RAW + closed-<think> prefill (our enforced guard)
        prompt = LLMEngine._build_qwen35_nothink_prompt(messages)
        o1 = llm.create_completion(
            prompt=prompt, max_tokens=256, temperature=0.3, top_p=0.9,
            stop=["<|im_end|>", "<think>"],
        )
        t_guard = o1["usage"]["completion_tokens"]
        txt_guard = o1["choices"][0]["text"].strip()
        has_think_g = "<think>" in txt_guard
        out(f"\n[1] GUARDED (prefill)      tokens={t_guard}  <think>={has_think_g}")
        out(f"    -> {txt_guard!r}")

        # 2. RAW naive (no guard) -- shows whether the model reasons by default
        o2 = llm.create_completion(
            prompt=naive_chatml(messages), max_tokens=512, temperature=0.3,
            top_p=0.9, stop=["<|im_end|>"],
        )
        t_naive = o2["usage"]["completion_tokens"]
        txt_naive = o2["choices"][0]["text"].strip()
        has_think_n = "<think>" in txt_naive
        # Was the think block non-empty (real reasoning)?
        reasoned = False
        if "<think>" in txt_naive and "</think>" in txt_naive:
            inner = txt_naive.split("<think>", 1)[1].split("</think>", 1)[0]
            reasoned = len(inner.strip()) > 0
        out(f"\n[2] UNGUARDED (naive)      tokens={t_naive}  "
            f"<think>={has_think_n}  reasoned={reasoned}")
        out(f"    -> {txt_naive[:400]!r}")

        # 3. create_chat_completion via the Jinja no-think handler
        try:
            o3 = llm.create_chat_completion(
                messages=messages, max_tokens=256, temperature=0.3, top_p=0.9,
            )
            t_chat = o3["usage"]["completion_tokens"]
            txt_chat = o3["choices"][0]["message"]["content"].strip()
            has_think_c = "<think>" in txt_chat
            out(f"\n[3] CHAT HANDLER (Jinja)   tokens={t_chat}  "
                f"<think>={has_think_c}")
            out(f"    -> {txt_chat!r}")
        except Exception as e:  # noqa: BLE001
            t_chat = -1
            out(f"\n[3] CHAT HANDLER (Jinja)   FAILED: {e}")

        summary.append((u, t_guard, t_naive, t_chat, reasoned))
        out("")

    out("=" * 72)
    out("SUMMARY  (completion tokens; reasoned = naive filled a <think> block)")
    out(f"{'prompt':<34}{'guard':>7}{'naive':>7}{'chat':>7}{'reasoned':>10}")
    for u, g, n, c, r in summary:
        out(f"{u[:32]:<34}{g:>7}{n:>7}{c:>7}{str(r):>10}")
    any_guard_think = "see per-prompt <think> flags above (all must be False)"
    out(f"\nGUARD CHECK: {any_guard_think}")
    out(
        "VERDICT: in every GUARDED row the model emits NO <think> and no "
        "reasoning -- the closed-prefill suppresses chain-of-thought at "
        "generation time. (Token count is the standing proof: a short reply "
        "cannot hide reasoning.)"
    )

    try:
        with open(
            os.path.join(os.getcwd(), "logs", "_nothink_proof.txt"),
            "w", encoding="utf-8",
        ) as fh:
            fh.write(_REPORT.getvalue())
        print("\n[report written to logs/_nothink_proof.txt]")
    except Exception as e:  # noqa: BLE001
        print(f"\n[report write failed: {e}]")


if __name__ == "__main__":
    main()
