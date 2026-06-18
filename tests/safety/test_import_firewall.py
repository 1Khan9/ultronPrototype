"""Pins the anticheat import firewall.

The firewall is the loader-level backstop guaranteeing that no lazy/conditional
import anywhere can pull a desktop/browser/input/capture/automation module into
the process while anticheat-safe mode is active. These tests assert: the block
list is correct (dangerous blocked, benign allowed), find_spec refuses blocked
imports ONLY while the mode is active, and install is idempotent.
"""

import pytest

from kenning.safety import import_firewall as fw
from kenning.safety import anticheat


DANGEROUS = [
    "kenning.desktop",
    "kenning.desktop.launcher",
    "kenning.desktop.screen_context",
    "kenning.desktop.vlm",
    "kenning.desktop.input_control",
    "kenning.desktop.capture",
    "kenning.openclaw_bridge.browser",
    "kenning.openclaw_bridge.desktop",
    "pyautogui",
    "mss",
    "dxcam",
    "d3dshot",
    "PIL.ImageGrab",
    "keyboard",
    "mouse",
    "pydirectinput",
    "playwright",
    "playwright.sync_api",
    "browser_use",
    "selenium",
    "pywinauto",
    "pynput",
    "pyscreeze",
    "uiautomation",
    # 2026-06-15 audit: the stale src/ultron mirror's desktop/browser submodules.
    "ultron.desktop",
    "ultron.desktop.input_control",
    "ultron.openclaw_bridge.browser",
]

BENIGN = [
    "win32gui",            # overlay window styling (OBS-capturable)
    "win32con",
    "PIL",                 # nameplate
    "PIL.Image",
    "numpy",
    "torch",
    "transformers",
    "faster_whisper",
    "kenning.config",
    "kenning.audio.waveform",
    "kenning.openclaw_bridge",        # the HTTP client package itself
    "kenning.openclaw_routing",       # routing logic, no in-process automation
    "kenning.safety.anticheat",
]


def test_is_blocked_module_dangerous():
    for m in DANGEROUS:
        assert fw.is_blocked_module(m), f"should be blocked: {m}"


def test_is_blocked_module_benign():
    for m in BENIGN:
        assert not fw.is_blocked_module(m), f"should NOT be blocked: {m}"


def test_find_spec_refuses_when_active(monkeypatch):
    monkeypatch.setattr(anticheat, "anticheat_active", lambda: True)
    finder = fw.AnticheatImportFirewall()
    # 2026-06-18 PROBE-SAFE: find_spec hard-blocks (raises) a blocked module only
    # when it is actually INSTALLED -- the case the anticheat guarantee cares about
    # (a dangerous lib that could really load). These are all blocked AND present
    # in the venv.
    for m in ("pyautogui", "mss", "pyperclip", "win32clipboard"):
        with pytest.raises(ImportError):
            finder.find_spec(m)
    # Benign modules defer to the normal finders (return None) even when active.
    for m in ("win32gui", "PIL", "kenning.config", "numpy"):
        assert finder.find_spec(m) is None


def test_find_spec_defers_for_absent_blocked_when_active(monkeypatch):
    """2026-06-18 PROBE-SAFE regression test (would have caught the pytesseract
    incident): a blocked module that is NOT installed must DEFER -- find_spec
    returns None instead of raising -- so a library probing for an optional
    dependency via ``importlib.util.find_spec`` is not broken by the firewall.
    (transformers probes pytesseract at import time; the firewall raising there
    cascaded and silenced Kokoro/Whisper/Smart-Turn.)"""
    monkeypatch.setattr(anticheat, "anticheat_active", lambda: True)
    finder = fw.AnticheatImportFirewall()
    for m in ("interception", "vgamepad", "pyvjoy", "pydivert", "d3dshot"):
        assert fw.is_blocked_module(m), f"{m} should be on the blocklist"
        assert finder.find_spec(m) is None, f"absent {m} must DEFER, not raise"


def test_find_spec_noop_when_inactive(monkeypatch):
    monkeypatch.setattr(anticheat, "anticheat_active", lambda: False)
    finder = fw.AnticheatImportFirewall()
    # While the mode is OFF, even blocked modules defer to normal import
    # (non-gaming sessions keep full desktop/browser capability).
    for m in ("kenning.desktop.launcher", "pyautogui", "playwright"):
        assert finder.find_spec(m) is None


def test_install_is_idempotent():
    assert fw.install_import_firewall() is True
    assert fw.install_import_firewall() is True
    assert fw.is_firewall_installed() is True


def test_real_import_blocked_when_active(monkeypatch):
    """End-to-end: an actual `import` of a not-yet-loaded blocked+INSTALLED module
    raises the firewall's ImportError while anticheat is active (the firewall must
    be installed on sys.meta_path)."""
    import importlib
    import sys
    fw.install_import_firewall()
    monkeypatch.setattr(anticheat, "anticheat_active", lambda: True)
    # Evict any cached kenning.desktop[.*] so import_module actually runs find_spec
    # (another test may have imported it earlier with anticheat OFF). It is
    # prefix-blocked AND always installed, so the re-import is refused at the parent.
    for _m in [k for k in list(sys.modules) if k == "kenning.desktop"
               or k.startswith("kenning.desktop.")]:
        sys.modules.pop(_m, None)
    with pytest.raises(ImportError) as ei:
        importlib.import_module("kenning.desktop")
    assert "anticheat import firewall" in str(ei.value)


def test_absent_blocked_real_import_is_natural_not_firewall(monkeypatch):
    """A blocked-but-ABSENT module fails with the NATURAL ModuleNotFoundError, not
    the firewall's -- the probe-safe defer, so optional-dependency resolution
    behaves exactly as on a firewall-free machine."""
    import importlib
    fw.install_import_firewall()
    monkeypatch.setattr(anticheat, "anticheat_active", lambda: True)
    with pytest.raises(ImportError) as ei:
        importlib.import_module("interception")
    assert "anticheat import firewall" not in str(ei.value)


def test_enforcement_self_check_passes_when_active(monkeypatch):
    """assert_firewall_enforces() must verify via a blocked+INSTALLED sentinel
    (kenning.desktop), NOT the old absent 'interception' which now correctly
    defers. A False here would make __main__ refuse to start."""
    fw.install_import_firewall()
    monkeypatch.setattr(anticheat, "anticheat_active", lambda: True)
    assert fw.assert_firewall_enforces() is True
