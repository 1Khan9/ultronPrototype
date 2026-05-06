"""Download datasets the openWakeWord auto-training pipeline needs.

Idempotent: each section checks whether the target already exists. Run with the
training venv:

    ..\\.venv-train\\Scripts\\python.exe download_training_data.py

The user's machine has stale HF cache env vars pointing at D:\\ (which doesn't
exist). We override them up here, before any HF library is imported, so
huggingface_hub initializes its cache in a writable location.
"""

from __future__ import annotations

# --- Cache redirects must come before any HF / datasets / hf_xet import ---
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".hf-cache"
for sub in ("datasets", "hub", "xet"):
    (CACHE / sub).mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(CACHE)
os.environ["HF_DATASETS_CACHE"] = str(CACHE / "datasets")
os.environ["HF_HUB_CACHE"] = str(CACHE / "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE / "hub")
os.environ["XET_CACHE_DIR"] = str(CACHE / "xet")

import sys
import urllib.request

# Force UTF-8 stdout so the status glyphs below print without UnicodeEncodeError on Windows.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

import numpy as np
import scipy.io.wavfile
from tqdm import tqdm

DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)


def _have(path: Path, min_bytes: int = 1024) -> bool:
    return path.is_file() and path.stat().st_size >= min_bytes


def _download(url: str, dest: Path) -> None:
    if _have(dest):
        print(f"  ✓ already present: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"  → downloading {dest.name}")
    try:
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dest)
        print(f"  ✓ saved {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    except Exception as e:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        print(f"  ✗ failed: {e}")
        raise


def _resample_to_16k(arr: np.ndarray, src_sr: int) -> np.ndarray:
    """Cheap resampler via scipy.signal.resample_poly."""
    if src_sr == 16000:
        return arr.astype(np.float32, copy=False)
    from scipy.signal import resample_poly
    from math import gcd

    g = gcd(int(src_sr), 16000)
    up = 16000 // g
    down = int(src_sr) // g
    return resample_poly(arr.astype(np.float32, copy=False), up, down)


def fetch_mit_rirs() -> None:
    out_dir = DATA / "mit_rirs"
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.glob("*.wav")):
        print(f"  ✓ MIT RIRs already present in {out_dir} ({len(list(out_dir.glob('*.wav')))} files)")
        return
    import datasets

    print("  → streaming davidscripka/MIT_environmental_impulse_responses")
    rir = datasets.load_dataset(
        "davidscripka/MIT_environmental_impulse_responses",
        split="train",
        streaming=True,
    )
    for row in tqdm(rir, desc="RIRs"):
        name = row["audio"]["path"].split("/")[-1]
        scipy.io.wavfile.write(
            out_dir / name,
            16000,
            (row["audio"]["array"] * 32767).astype(np.int16),
        )


def fetch_urbansound() -> None:
    out_dir = DATA / "urbansound"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_files = 600  # ~50 minutes @ avg 5 s clips
    have = len(list(out_dir.glob("*.wav")))
    if have >= target_files:
        print(f"  ✓ UrbanSound8K already has {have} clips in {out_dir}")
        return
    import datasets

    print(f"  → streaming danavery/urbansound8K (target {target_files} clips)")
    ds = datasets.load_dataset("danavery/urbansound8K", split="train", streaming=True)
    written = have
    for row in tqdm(ds, total=target_files - have, desc="UrbanSound8K"):
        if written >= target_files:
            break
        a = row["audio"]
        arr = np.asarray(a["array"], dtype=np.float32)
        sr = int(a["sampling_rate"])
        arr16 = _resample_to_16k(arr, sr)
        name = (
            row.get("slice_file_name")
            or a.get("path", f"clip_{written}.wav").split("/")[-1]
        )
        if not name.endswith(".wav"):
            name += ".wav"
        scipy.io.wavfile.write(
            out_dir / name,
            16000,
            np.clip(arr16 * 32767, -32768, 32767).astype(np.int16),
        )
        written += 1


def fetch_features() -> None:
    base = (
        "https://huggingface.co/datasets/davidscripka/"
        "openwakeword_features/resolve/main/"
    )
    targets = [
        ("openwakeword_features_ACAV100M_2000_hrs_16bit.npy", DATA),
        ("validation_set_features.npy", DATA),
    ]
    for name, parent in targets:
        _download(base + name, parent / name)


def main() -> int:
    print(f"\nCache root: {CACHE}")
    print(f"Data root:  {DATA}\n")

    print("[1/3] MIT room impulse responses")
    fetch_mit_rirs()

    print("\n[2/3] UrbanSound8K background clips")
    fetch_urbansound()

    print("\n[3/3] ACAV100M features + validation features (large; ~16 GB total)")
    fetch_features()

    print("\nAll done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
