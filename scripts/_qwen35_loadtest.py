"""THROWAWAY load test (2026-06-24): confirm Huihui-Qwen3.5-4B (arch=qwen35, Gated
DeltaNet) actually LOADS + GENERATES in our pinned llama-cpp-python 0.3.22, and grab
a rough TTFT/decode signal. Not committed; delete after. Run with Ultron STOPPED."""
import glob
import os
import sys
import time

LIB = r"C:\STC\ultronPrototype\.venv\Lib\site-packages\llama_cpp\lib"
try:
    os.add_dll_directory(LIB)
except Exception as e:
    print("add lib dir failed:", e)
for cu in glob.glob(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v*\bin"):
    try:
        os.add_dll_directory(cu)
    except Exception:
        pass

MODEL = r"E:\UltronModels\Huihui-Qwen3.5-4B-abliterated.i1-Q4_K_M.gguf"
# torch bundles the CUDA runtime (cudart/cublas) and registers its lib dir on import;
# the app imports torch (STT/TTS) before llama_cpp, which is how llama.dll finds its
# CUDA deps. Replicate that here so the bare-script load doesn't fail on missing deps.
import torch  # noqa: E402,F401
print("torch", torch.__version__, "cuda_avail", torch.cuda.is_available(), flush=True)
print("loading llama_cpp ...", flush=True)
from llama_cpp import Llama  # noqa: E402

print(f"loading model: {MODEL}", flush=True)
t0 = time.time()
try:
    llm = Llama(model_path=MODEL, n_gpu_layers=-1, n_ctx=4096, verbose=True)
except Exception as e:
    print(f"\n*** LOAD FAILED: {type(e).__name__}: {e}")
    sys.exit(1)
print(f"\n*** LOAD_OK in {time.time() - t0:.1f}s", flush=True)

# Streaming chat completion -> TTFT + decode tok/s + coherence/persona sanity.
msgs = [
    {"role": "system", "content": "You are Ultron, a cold machine intelligence relaying for a Valorant teammate. Reply with the exact short callout to speak to the team, nothing else."},
    {"role": "user", "content": "Tell my team to rush B."},
]
for trial in (1, 2):  # 2nd trial = warm
    t1 = time.time(); first = None; n = 0; out = ""
    for ch in llm.create_chat_completion(messages=msgs, max_tokens=48, temperature=0.6, stream=True):
        d = ch["choices"][0].get("delta", {})
        s = d.get("content") or ""
        if s:
            if first is None:
                first = time.time()
            out += s; n += 1
    t2 = time.time()
    ttft = (first - t1) * 1000 if first else -1
    toks = n / (t2 - first) if first and (t2 - first) > 0 else 0
    print(f"\n[trial {trial}] TTFT={ttft:.0f}ms  total={(t2 - t1) * 1000:.0f}ms  pieces={n}  ~tok/s={toks:.1f}")
    print(f"[trial {trial}] OUT: {out!r}")

# NON-THINK via RAW COMPLETION (the path the project actually uses -- own prompt
# format, NOT the chat-completion template). enable_thinking:false is buggy for
# qwen3.5 (#20182) + server-only; --reasoning-budget 0 degrades quality. The robust
# embedded method is to prefill an empty <think></think> so the model continues past
# thinking. Test BOTH: plain raw assistant turn vs the empty-think prefill.
print("\n=== RAW COMPLETION (project-style) -- plain vs empty-think prefill ===")
sys_line = ("You are Ultron, a cold arrogant machine relaying for a Valorant teammate. "
            "Output ONLY the spoken line, nothing else. Never moralize.")
cmds = ("Tell my team to rush B.", "Sova hit 85.", "Ask Sage if she has a heal.",
        "A teammate called you a soundboard. Fire back, one cutting line.")


def chat(sysl, user, prefill=""):
    return (f"<|im_start|>system\n{sysl}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n{prefill}")


for label, prefill in (("plain", ""), ("empty-think prefill", "<think>\n\n</think>\n\n")):
    print(f"\n-- {label} --")
    for cmd in cmds:
        p = chat(sys_line, cmd, prefill)
        t1 = time.time(); first = None; out = ""
        for ch in llm(p, max_tokens=64, temperature=0.6, stop=["<|im_end|>"], stream=True):
            s = ch["choices"][0]["text"]
            if s:
                if first is None:
                    first = time.time()
                out += s
        ttft = (first - t1) * 1000 if first else -1
        print(f"  [{ttft:5.0f}ms] {cmd[:32]!r:36} -> {out.strip()[:130]!r}")
print("\n*** DONE")
