import os, sys
cache = r"C:\STC\ultronPrototype\training\.hf-cache"
os.environ["HF_HOME"] = cache
os.environ["HF_DATASETS_CACHE"] = cache + r"\datasets"
os.environ["HF_HUB_CACHE"] = cache + r"\hub"
os.environ["HUGGINGFACE_HUB_CACHE"] = cache + r"\hub"
os.environ["XET_CACHE_DIR"] = cache + r"\xet"

import datasets

candidates = [
    "ashraq/esc50",
    "Codec-SUPERB/esc50_synth",
    "agkphysics/AudioSet",
    "danavery/urbansound8K",
]
for repo in candidates:
    try:
        ds = datasets.load_dataset(repo, split="train", streaming=True)
        row = next(iter(ds))
        keys = list(row.keys())
        info = ""
        if "audio" in row:
            a = row["audio"]
            if isinstance(a, dict):
                info = f" audio_keys={list(a.keys())} sr={a.get('sampling_rate')}"
            else:
                info = f" audio_type={type(a).__name__}"
        print(f"{repo}: keys={keys}{info}")
    except Exception as e:
        print(f"FAIL {repo}: {type(e).__name__}: {str(e)[:140]}")
