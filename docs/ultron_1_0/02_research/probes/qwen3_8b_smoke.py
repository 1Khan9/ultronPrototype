"""Ultron 1.0 — bounded smoke test for the chosen 8B model.

Confirms: (1) the GGUF loads via the installed llama-cpp-python (CUDA), (2) thinking mode
behavior + how <think> is emitted, (3) a Valorant-relay-style generation in-persona,
(4) rough timing + token counts. Bounded: small ctx, short max_tokens. Read-only probe.

Run:  C:\\STC\\ultronPrototype\\.venv\\Scripts\\python.exe <thispath>
"""
import json
import sys
import time

MODEL = r"E:\UltronModels\Josiefied-Qwen3-8B-abliterated-v1.Q5_K_M.gguf"

def line(s=""):
    print(s, flush=True)

def main():
    line(f"=== Qwen3-8B smoke test ===")
    line(f"model: {MODEL}")
    # Windows: llama_cpp's CUDA llama.dll needs the CUDA runtime DLLs (cudart/cublas)
    # on the DLL search path. PyTorch ships them under torch/lib.
    try:
        import os as _os, pathlib as _pl
        import torch as _torch
        _tl = str(_pl.Path(_torch.__file__).parent / "lib")
        if _os.path.isdir(_tl):
            _os.add_dll_directory(_tl)
            line(f"added torch lib to DLL path: {_tl}")
    except Exception as _e:  # noqa: BLE001
        line(f"torch dll-path setup warn: {_e!r}")
    try:
        import llama_cpp
        line(f"llama_cpp version: {getattr(llama_cpp, '__version__', '?')}")
    except Exception as e:  # noqa: BLE001
        line(f"FATAL: cannot import llama_cpp: {e!r}")
        sys.exit(2)

    t0 = time.time()
    try:
        llm = llama_cpp.Llama(
            model_path=MODEL,
            n_ctx=4096,
            n_gpu_layers=-1,   # full offload; 4070 Ti has headroom for an 8B Q5
            n_batch=512,
            verbose=False,
        )
    except Exception as e:  # noqa: BLE001
        line(f"FATAL: model load failed: {e!r}")
        sys.exit(3)
    line(f"load_ok in {time.time()-t0:.1f}s; n_ctx={llm.n_ctx()}")

    # Detect an embedded chat template (Qwen3 ships one with /think handling).
    try:
        md = llm.metadata or {}
        has_tmpl = any("chat_template" in k for k in md.keys())
        line(f"chat_template present in metadata: {has_tmpl}")
    except Exception as e:  # noqa: BLE001
        line(f"metadata read warn: {e!r}")

    system = (
        "You are Ultron — a cold, superior machine intelligence (an Age of Ultron clone) acting as a "
        "Valorant teammate-relay. Speak in-character: clipped, contemptuous of enemies, precise. "
        "Relay the tactical callout to the team, then add ONE short in-character flavor line."
    )
    user_callout = "Sova hit 84 on A main"

    for label, umsg in [("THINKING (default)", user_callout),
                        ("NO_THINK", user_callout + " /no_think")]:
        line("")
        line(f"--- {label} ---")
        t1 = time.time()
        try:
            out = llm.create_chat_completion(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": umsg}],
                max_tokens=300,
                temperature=0.7,
                top_p=0.8,
                top_k=20,
            )
        except Exception as e:  # noqa: BLE001
            line(f"  generation error: {e!r}")
            continue
        dt = time.time() - t1
        msg = out["choices"][0]["message"]
        content = msg.get("content") or ""
        usage = out.get("usage", {})
        has_think = "<think>" in content or "</think>" in content
        # llama-cpp may also expose reasoning separately on some builds:
        reasoning = msg.get("reasoning_content")
        line(f"  time={dt:.1f}s  usage={json.dumps(usage)}")
        line(f"  <think> tags in content: {has_think}  reasoning_content present: {reasoning is not None}")
        line(f"  RAW content:\n{content}")

    line("")
    line("=== done ===")

if __name__ == "__main__":
    main()
