"""Wrapper that runs openWakeWord's train.py with the right environment.

Sets HF / Xet cache dirs to a writable local path (the user's machine has
stale env vars pointing at D:\\), monkey-patches torch.load to default
weights_only=False (DeepPhonemizer + Piper checkpoints are full-pickle), then
launches train.py as a subprocess so PyTorch's DataLoader spawn workers can
re-import the proper __main__ module cleanly on Windows.

Usage:
    ..\\.venv-train\\Scripts\\python.exe run_training.py --training_config kenning_model.yaml --generate_clips
    ..\\.venv-train\\Scripts\\python.exe run_training.py --training_config kenning_model.yaml --augment_clips
    ..\\.venv-train\\Scripts\\python.exe run_training.py --training_config kenning_model.yaml --train_model
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".hf-cache"
for sub in ("datasets", "hub", "xet"):
    (CACHE / sub).mkdir(parents=True, exist_ok=True)

env = os.environ.copy()
env["HF_HOME"] = str(CACHE)
env["HF_DATASETS_CACHE"] = str(CACHE / "datasets")
env["HF_HUB_CACHE"] = str(CACHE / "hub")
env["HUGGINGFACE_HUB_CACHE"] = str(CACHE / "hub")
env["XET_CACHE_DIR"] = str(CACHE / "xet")
env["PYTHONUTF8"] = "1"

# A small bootstrapping snippet that runs in the child before train.py:
#   - patches torch.load default to weights_only=False
# Saved next to train.py and imported via -X usercustomize via PYTHONSTARTUP-style
# `python -c "<bootstrap>; runpy.run_path(...)"`.
TRAIN_PY = ROOT / "openwakeword" / "openwakeword" / "train.py"
if not TRAIN_PY.is_file():
    raise SystemExit(f"train.py not found at {TRAIN_PY}")

bootstrap = (
    "import torch as _torch; _orig = _torch.load; "
    "def _patched(*a, **k): k.setdefault('weights_only', False); return _orig(*a, **k); "
    "_torch.load = _patched; "
    "import sys, runpy; sys.argv = [r'%s'] + sys.argv[1:]; "
    "runpy.run_path(r'%s', run_name='__main__')"
) % (str(TRAIN_PY), str(TRAIN_PY))

# Define helper at module scope so subprocess inherits a sane bootstrap
# (multi-line def can't live in one -c expression). Use a tempfile instead.
import tempfile

bootstrap_src = f"""\
import torch as _torch
_orig_load = _torch.load
def _patched_load(*a, **k):
    k.setdefault('weights_only', False)
    return _orig_load(*a, **k)
_torch.load = _patched_load

import runpy, sys
sys.argv = [r'{TRAIN_PY}'] + sys.argv[1:]
runpy.run_path(r'{TRAIN_PY}', run_name='__main__')
"""

with tempfile.NamedTemporaryFile(
    "w", suffix="_bootstrap.py", delete=False, encoding="utf-8"
) as f:
    f.write(bootstrap_src)
    bootstrap_path = f.name

cmd = [sys.executable, "-X", "utf8", bootstrap_path, *sys.argv[1:]]
try:
    proc = subprocess.run(cmd, env=env, cwd=str(ROOT))
finally:
    try:
        os.unlink(bootstrap_path)
    except OSError:
        pass

sys.exit(proc.returncode)
