"""Ultron 1.0 M0 — verify the 8B serves IN-CHARACTER through the real LLMEngine wrapper.

Loads Josiefied-Qwen3-8B via the project's LLMEngine (not raw llama_cpp) at the VRAM-safe
n_ctx=4096 cap, generates relay-style lines with the Ultron persona + enable_thinking=False,
asserts no <think> leak, and reports resident VRAM. Run from the worktree:
  $env:PYTHONPATH="<worktree>\\src"; .venv\\python.exe <thispath>
"""
import os, subprocess, time
os.environ.setdefault("KENNING_LLM_PRESET", "josiefied-qwen3-8b")
os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")

import kenning  # noqa: F401  (registers the torch/lib CUDA DLL path)
from kenning.config import get_config
from kenning.llm.inference import LLMEngine
from kenning.audio.llm_prompts import ULTRON_GAMING_PERSONA


def vram():
    try:
        return subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader"],
            text=True).strip()
    except Exception as e:  # noqa: BLE001
        return f"vram? {e!r}"


def main():
    cfg = get_config().llm
    print(f"preset={cfg.preset}  model_path={cfg.model_path}  n_ctx(cfg)={cfg.n_ctx}  gpu_layers={cfg.gpu_layers}")
    print(f"vram before load: {vram()}")
    t0 = time.time()
    eng = LLMEngine(n_ctx=4096)  # hard VRAM cap per research synthesis
    print(f"LLMEngine loaded in {time.time()-t0:.1f}s; vram after load: {vram()}")

    sampling = {"max_tokens": 64, "temperature": 0.8, "top_p": 0.92, "top_k": 40,
                "min_p": 0.08, "repeat_penalty": 1.18}
    cases = [
        "Sova hit 84 on A main",
        "tell my team to rush B",
        "they have no smokes left",
        "Jett hit 84, Breach hit 97",
        "what do you think of Tony Stark",
    ]
    leak = False
    for c in cases:
        t1 = time.time()
        try:
            text = "".join(eng.generate_stream(
                c, system_prompt=ULTRON_GAMING_PERSONA, enable_thinking=False,
                sampling=sampling, suppress_memory_context=True, record_history=False))
        except Exception as e:  # noqa: BLE001
            print(f"\n[{c}] GENERATION ERROR: {e!r}")
            continue
        if "<think>" in text or "</think>" in text:
            leak = True
        print(f"\n[{c}]  ({time.time()-t1:.1f}s)\n  -> {text.strip()!r}")
    print(f"\nvram after gen: {vram()}")
    print(f"THINK-LEAK in relay output: {leak}  (must be False)")
    print("=== done ===")


if __name__ == "__main__":
    main()
