"""GOLDEN gate for the voice-line / routing / LLM-prompt aggregates.

The aggregates (voice_lines, routing_rules, llm_prompts + the curated pools they
re-export) are PURE DATA relocated out of the pipeline. ``scripts/
_voice_lines_verify.py`` digests every relocated pool, regex, threshold and
data-driven registry rule; this test runs its ``check`` mode against a committed
GOLDEN digest so any *accidental* edit to a voice line, matching regex, routing
threshold, or registry rule fails CI loudly.

When a change to those values is INTENTIONAL, re-bless the golden:

    PYTHONHASHSEED=0 \\
    KENNING_VOICE_LINES_DIGEST=tests/data/voice_lines_golden_digest.json \\
    python scripts/_voice_lines_verify.py baseline

and commit the updated tests/data/voice_lines_golden_digest.json with the change.

The harness is run in a SUBPROCESS with PYTHONHASHSEED=0 because some regexes are
compiled from sets, whose iteration order (and therefore the alternation order in
the compiled pattern string) is only stable under a fixed hash seed. PYTHONHASHSEED
cannot be changed inside a running interpreter, so the subprocess is required.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_HARNESS = _ROOT / "scripts" / "_voice_lines_verify.py"
_GOLDEN = _ROOT / "tests" / "data" / "voice_lines_golden_digest.json"


@pytest.mark.skipif(not _HARNESS.is_file(), reason="verify harness missing")
def test_aggregates_match_golden_digest() -> None:
    assert _GOLDEN.is_file(), (
        f"golden digest missing at {_GOLDEN}; generate it with "
        f"PYTHONHASHSEED=0 KENNING_VOICE_LINES_DIGEST={_GOLDEN} "
        f"python scripts/_voice_lines_verify.py baseline"
    )
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["KENNING_VOICE_LINES_DIGEST"] = str(_GOLDEN)
    proc = subprocess.run(
        [sys.executable, str(_HARNESS), "check"],
        cwd=str(_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        "voice-line / routing / prompt aggregates diverged from the golden "
        "digest. If this change is INTENTIONAL, re-bless the golden (see this "
        "file's docstring) and commit it.\n\n" + out
    )
