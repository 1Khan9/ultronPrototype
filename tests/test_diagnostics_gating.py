"""Pin: operator audio-diagnostics monitoring is OFF by default and the
monitoring module (``kenning.audio.output_quality``) is NEVER imported into RAM
unless diagnostics is explicitly enabled.

This mirrors the anticheat never-load discipline for the desktop stack: code we
deliberately keep out of the process must not be imported by default. The audio
analysis only ever touches Kenning's OWN buffers (not an anticheat surface), but
the operator requires it stay unloaded unless they are actively testing.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_audio_diagnostics_off_by_default(monkeypatch, tmp_path) -> None:
    import kenning.diagnostics as diag

    # No sentinel + no config flag -> disabled.
    monkeypatch.setattr(diag, "_SENTINEL", tmp_path / "absent")
    monkeypatch.setattr(
        "kenning.config.get_config",
        lambda: type("C", (), {"diagnostics": None})(),
    )
    assert diag.audio_diagnostics_enabled() is False

    # Sentinel present -> enabled (the live, restart-free toggle).
    sentinel = tmp_path / "on"
    sentinel.touch()
    monkeypatch.setattr(diag, "_SENTINEL", sentinel)
    assert diag.audio_diagnostics_enabled() is True


def test_monitoring_module_not_loaded_by_importing_tts_engine() -> None:
    """Importing the TTS engine must NOT pull the output-quality monitoring
    module into RAM -- it is only imported inside the diagnostics-gated blocks.
    Run in a clean subprocess so suite-wide import pollution can't mask it."""
    code = (
        "import sys; sys.path[:0] = [r%r, r%r]\n" % (
            str(_ROOT / "src"), str(_ROOT))
    ) + textwrap.dedent(
        """
        import sys
        import kenning.tts.kokoro_engine          # the speak path
        assert "kenning.audio.output_quality" not in sys.modules, (
            "monitoring module imported just by loading the TTS engine")
        print("PROBE_PASS")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=180, cwd=str(_ROOT),
    )
    assert "PROBE_PASS" in proc.stdout, (
        f"probe failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
