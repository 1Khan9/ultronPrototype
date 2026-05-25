"""Tests for ultron.llm.mode_router."""

from __future__ import annotations

import pytest

from ultron.agent_loop.mode import Mode
from ultron.llm import mode_router as mr


class FakeEngine:
    """Records preset reload calls for assertion."""

    def __init__(self, *, initial: str = "qwen3.5-4b", succeed: bool = True) -> None:
        self.current = initial
        self.calls: list[str] = []
        self.succeed = succeed
        self.error_message = ""

    def probe(self) -> str:
        return self.current

    def reload(self, preset: str) -> tuple[bool, str]:
        self.calls.append(preset)
        if not self.succeed:
            return False, self.error_message or "fake failure"
        self.current = preset
        return True, ""


# ---------------------------------------------------------------------------
# PresetEntry
# ---------------------------------------------------------------------------

class TestPresetEntry:
    def test_default_routes_cover_all_modes(self) -> None:
        for mode in Mode:
            assert mode in mr.DEFAULT_ROUTES

    def test_act_uses_standby_preset(self) -> None:
        entry = mr.DEFAULT_ROUTES[Mode.ACT]
        assert entry.preset_name == "qwen3.5-4b"

    def test_gaming_uses_cheap_preset(self) -> None:
        entry = mr.DEFAULT_ROUTES[Mode.GAMING]
        assert entry.preset_name == "llama-3.2-3b-abliterated"


# ---------------------------------------------------------------------------
# get_preset / set_preset
# ---------------------------------------------------------------------------

class TestRouteManagement:
    def test_set_preset_overrides(self) -> None:
        eng = FakeEngine()
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        new = mr.PresetEntry(preset_name="phi-4")
        router.set_preset(Mode.ACT, new)
        assert router.get_preset(Mode.ACT).preset_name == "phi-4"

    def test_routes_snapshot_is_copy(self) -> None:
        eng = FakeEngine()
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        snap = router.routes()
        snap[Mode.ACT] = mr.PresetEntry(preset_name="poisoned")
        # Internal routes unchanged.
        assert router.get_preset(Mode.ACT).preset_name == "qwen3.5-4b"


# ---------------------------------------------------------------------------
# ensure_preset_for -- happy paths
# ---------------------------------------------------------------------------

class TestEnsurePresetHappy:
    def test_no_op_when_already_active(self) -> None:
        eng = FakeEngine(initial="qwen3.5-4b")
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        result = router.ensure_preset_for(Mode.ACT)
        assert result.succeeded is True
        assert result.was_already_active is True
        assert eng.calls == []

    def test_swap_when_different_preset(self) -> None:
        eng = FakeEngine(initial="qwen3.5-4b")
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        result = router.ensure_preset_for(Mode.GAMING)
        assert result.succeeded is True
        assert result.was_already_active is False
        assert result.target_preset == "llama-3.2-3b-abliterated"
        assert eng.calls == ["llama-3.2-3b-abliterated"]
        assert eng.current == "llama-3.2-3b-abliterated"

    def test_swap_propagates_sampling_overrides(self) -> None:
        eng = FakeEngine(initial="qwen3.5-4b")
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        result = router.ensure_preset_for(Mode.CODING_EDITOR)
        assert result.sampling_overrides == {"temperature": 0.2}


# ---------------------------------------------------------------------------
# ensure_preset_for -- failure paths
# ---------------------------------------------------------------------------

class TestEnsurePresetFailure:
    def test_failed_reload_reports_reason(self) -> None:
        eng = FakeEngine(initial="qwen3.5-4b", succeed=False)
        eng.error_message = "GGUF not found"
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        result = router.ensure_preset_for(Mode.GAMING)
        assert result.succeeded is False
        assert "GGUF not found" in result.failure_reason

    def test_reloader_exception_fail_open(self) -> None:
        def reloader(preset):
            raise RuntimeError("kaboom")
        router = mr.ModeLLMRouter(
            reloader=reloader,
            active_preset_probe=lambda: "qwen3.5-4b",
        )
        result = router.ensure_preset_for(Mode.GAMING)
        assert result.succeeded is False
        assert "RuntimeError" in result.failure_reason
        assert "kaboom" in result.failure_reason

    def test_probe_exception_does_not_crash(self) -> None:
        def probe():
            raise RuntimeError("probe broken")
        eng = FakeEngine()
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=probe)
        result = router.ensure_preset_for(Mode.GAMING)
        # Probe failure means we don't know current state -> attempt swap.
        assert eng.calls == ["llama-3.2-3b-abliterated"]
        assert result.succeeded is True


# ---------------------------------------------------------------------------
# Protected modes
# ---------------------------------------------------------------------------

class TestProtectedModes:
    def test_protected_mode_skips_swap(self) -> None:
        eng = FakeEngine(initial="qwen3.5-4b")
        router = mr.ModeLLMRouter(
            reloader=eng.reload,
            active_preset_probe=eng.probe,
            protected_modes=(Mode.GAMING,),
        )
        result = router.ensure_preset_for(Mode.GAMING)
        assert result.was_already_active is True
        assert eng.calls == []

    def test_mark_protected_runtime(self) -> None:
        eng = FakeEngine()
        router = mr.ModeLLMRouter(reloader=eng.reload, active_preset_probe=eng.probe)
        router.mark_protected(Mode.GAMING)
        router.ensure_preset_for(Mode.GAMING)
        assert eng.calls == []

    def test_unmark_protected_restores_swap(self) -> None:
        eng = FakeEngine()
        router = mr.ModeLLMRouter(
            reloader=eng.reload,
            active_preset_probe=eng.probe,
            protected_modes=(Mode.GAMING,),
        )
        router.unmark_protected(Mode.GAMING)
        router.ensure_preset_for(Mode.GAMING)
        assert eng.calls == ["llama-3.2-3b-abliterated"]


# ---------------------------------------------------------------------------
# on_swap callback
# ---------------------------------------------------------------------------

class TestOnSwapCallback:
    def test_callback_fires_on_success(self) -> None:
        seen: list[mr.SwapResult] = []
        eng = FakeEngine()
        router = mr.ModeLLMRouter(
            reloader=eng.reload,
            active_preset_probe=eng.probe,
            on_swap=seen.append,
        )
        router.ensure_preset_for(Mode.GAMING)
        assert len(seen) == 1
        assert seen[0].succeeded is True

    def test_callback_fires_on_failure(self) -> None:
        seen: list[mr.SwapResult] = []
        eng = FakeEngine(succeed=False)
        router = mr.ModeLLMRouter(
            reloader=eng.reload,
            active_preset_probe=eng.probe,
            on_swap=seen.append,
        )
        router.ensure_preset_for(Mode.GAMING)
        assert len(seen) == 1
        assert seen[0].succeeded is False

    def test_callback_exception_swallowed(self) -> None:
        def boom(_result):
            raise RuntimeError("callback bug")
        eng = FakeEngine()
        router = mr.ModeLLMRouter(
            reloader=eng.reload,
            active_preset_probe=eng.probe,
            on_swap=boom,
        )
        # Must not raise -- callback failure cannot kill the swap.
        result = router.ensure_preset_for(Mode.GAMING)
        assert result.succeeded is True
