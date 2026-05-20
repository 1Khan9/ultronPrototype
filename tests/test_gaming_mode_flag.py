"""Tests for the gaming-mode-active process-global flag (Track 6).

Covers ``is_gaming_mode_active`` / ``set_gaming_mode_active`` +
the GamingModeManager engage/disengage hook into the flag.
"""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from ultron.openclaw_routing.gaming_mode import (
    GamingModeManager,
    GamingModeStatus,
    is_gaming_mode_active,
    set_gaming_mode_active,
)


# ---------------------------------------------------------------------------
# Direct flag accessor
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_flag():
    """Always start a test with the flag cleared; restore on exit."""
    set_gaming_mode_active(False)
    yield
    set_gaming_mode_active(False)


def test_default_flag_is_false():
    assert is_gaming_mode_active() is False


def test_set_and_query_flag():
    set_gaming_mode_active(True)
    assert is_gaming_mode_active() is True
    set_gaming_mode_active(False)
    assert is_gaming_mode_active() is False


def test_set_coerces_truthy_values():
    set_gaming_mode_active(1)  # type: ignore[arg-type]
    assert is_gaming_mode_active() is True
    set_gaming_mode_active(0)  # type: ignore[arg-type]
    assert is_gaming_mode_active() is False


# ---------------------------------------------------------------------------
# GamingModeManager <-> flag wiring
# ---------------------------------------------------------------------------


class _StubClient:
    """Minimal async client stub for the plugin toggle path."""

    def __init__(self):
        self.disabled: List[str] = []
        self.enabled: List[str] = []

    async def disable_plugin(self, slug: str) -> Any:
        self.disabled.append(slug)
        return _StubResult()

    async def enable_plugin(self, slug: str) -> Any:
        self.enabled.append(slug)
        return _StubResult()


class _StubResult:
    success: bool = True
    error: str = ""


def test_engage_sets_flag(tmp_path):
    """GamingModeManager.engage() flips the process-global flag True."""
    client = _StubClient()
    mgr = GamingModeManager(
        client=client,
        plugins_to_disable=["desktop-control"],
        toggle_docker=False,
        log_path=tmp_path / "gaming.log",
    )
    assert is_gaming_mode_active() is False
    asyncio.run(mgr.engage())
    assert mgr.status() == GamingModeStatus.ENGAGED
    assert is_gaming_mode_active() is True


def test_disengage_clears_flag(tmp_path):
    """Disengage flips the flag back to False."""
    client = _StubClient()
    mgr = GamingModeManager(
        client=client,
        plugins_to_disable=["desktop-control"],
        toggle_docker=False,
        log_path=tmp_path / "gaming.log",
    )
    asyncio.run(mgr.engage())
    assert is_gaming_mode_active() is True
    asyncio.run(mgr.disengage())
    assert mgr.status() == GamingModeStatus.IDLE
    assert is_gaming_mode_active() is False


def test_engage_sets_flag_even_on_partial_failure(tmp_path):
    """If a plugin disable fails mid-engage, the flag still flips so
    the desktop primitives are gated regardless. The whole point is
    Vanguard safety -- we err on the side of MORE gating."""

    class _PartialFailureClient:
        def __init__(self):
            self.attempts = 0

        async def disable_plugin(self, slug: str):
            self.attempts += 1
            if self.attempts == 2:
                raise RuntimeError("disabler glitched")
            return _StubResult()

        async def enable_plugin(self, slug: str):
            return _StubResult()

    client = _PartialFailureClient()
    mgr = GamingModeManager(
        client=client,
        plugins_to_disable=["desktop-control", "windows-control"],
        toggle_docker=False,
        log_path=tmp_path / "gaming.log",
    )
    asyncio.run(mgr.engage())
    # Even though one plugin failed, the flag is set.
    assert is_gaming_mode_active() is True


def test_engage_idempotent_does_not_re_flip(tmp_path):
    """Calling engage twice doesn't re-toggle anything strange."""
    client = _StubClient()
    mgr = GamingModeManager(
        client=client,
        plugins_to_disable=["desktop-control"],
        log_path=tmp_path / "gaming.log",
    )
    asyncio.run(mgr.engage())
    asyncio.run(mgr.engage())  # second call is no-op
    assert is_gaming_mode_active() is True
    assert mgr.status() == GamingModeStatus.ENGAGED
