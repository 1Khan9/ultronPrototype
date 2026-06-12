"""Tests for the latency hygiene helpers (Track 2 sub-items)."""

from __future__ import annotations

import gc
from typing import Any, List

import pytest

from kenning import latency_hygiene


# ---------------------------------------------------------------------------
# pause_gc / resume_gc
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_gc_state():
    """Always start with GC enabled + paused-flag cleared."""
    # Reset module state.
    latency_hygiene._GC_PAUSED = False
    if not gc.isenabled():
        gc.enable()
    yield
    if not gc.isenabled():
        gc.enable()
    latency_hygiene._GC_PAUSED = False


def test_pause_gc_disables_collector():
    assert gc.isenabled() is True
    assert latency_hygiene.pause_gc() is True
    assert gc.isenabled() is False
    assert latency_hygiene.is_gc_paused() is True


def test_pause_gc_idempotent():
    latency_hygiene.pause_gc()
    second_call = latency_hygiene.pause_gc()
    assert second_call is False
    assert gc.isenabled() is False


def test_resume_gc_re_enables_collector():
    latency_hygiene.pause_gc()
    assert latency_hygiene.resume_gc(collect_now=False) is True
    assert gc.isenabled() is True
    assert latency_hygiene.is_gc_paused() is False


def test_resume_gc_when_not_paused_returns_false():
    """Calling resume without a prior pause is a no-op."""
    assert latency_hygiene.resume_gc() is False


def test_resume_gc_collect_now_runs_sweep():
    """``collect_now=True`` actually runs gc.collect (no exception
    surface; just verify it doesn't crash + leaves GC enabled)."""
    latency_hygiene.pause_gc()
    assert latency_hygiene.resume_gc(collect_now=True) is True
    assert gc.isenabled() is True


# ---------------------------------------------------------------------------
# raise_process_priority
# ---------------------------------------------------------------------------


def test_raise_priority_rejects_unsupported_level():
    """Only ``above_normal`` and ``normal`` are accepted -- the
    helper deliberately doesn't expose ``high`` or ``realtime``."""
    assert latency_hygiene.raise_process_priority("high") is False
    assert latency_hygiene.raise_process_priority("realtime") is False
    assert latency_hygiene.raise_process_priority("") is False


def test_raise_priority_succeeds_or_fails_gracefully():
    """Should never raise -- returns True on success, False on any
    failure (permission denied, psutil missing, etc.)."""
    result = latency_hygiene.raise_process_priority("above_normal")
    assert result in (True, False)


def test_raise_priority_revert_to_normal_does_not_raise():
    """Even if the elevation failed, revert should be safe."""
    latency_hygiene.raise_process_priority("above_normal")
    result = latency_hygiene.raise_process_priority("normal")
    assert result in (True, False)


# ---------------------------------------------------------------------------
# warmup_llm
# ---------------------------------------------------------------------------


def test_warmup_llm_returns_elapsed_on_success():
    """Successful warmup returns wall-clock elapsed in seconds."""
    calls: List[str] = []

    def fake_gen(prompt):
        calls.append(prompt)
        return "ok"

    elapsed = latency_hygiene.warmup_llm(fake_gen)
    assert elapsed is not None
    assert elapsed >= 0.0
    assert calls == [latency_hygiene.DEFAULT_LLM_WARMUP_PROMPT]


def test_warmup_llm_returns_none_on_exception():
    """Exceptions in the generate fn are swallowed; return is None."""
    def broken(_prompt):
        raise RuntimeError("model not ready")

    result = latency_hygiene.warmup_llm(broken)
    assert result is None


def test_warmup_llm_custom_prompt_passed_through():
    calls: List[str] = []

    def fake_gen(prompt):
        calls.append(prompt)

    latency_hygiene.warmup_llm(fake_gen, prompt="Online.")
    assert calls == ["Online."]


# ---------------------------------------------------------------------------
# warmup_embedder
# ---------------------------------------------------------------------------


def test_warmup_embedder_returns_elapsed_on_success():
    encode_calls: List[str] = []

    def fake_encode(text):
        encode_calls.append(text)
        return [0.0] * 384

    elapsed = latency_hygiene.warmup_embedder(fake_encode)
    assert elapsed is not None
    assert elapsed >= 0.0
    assert encode_calls == ["warmup"]


def test_warmup_embedder_returns_none_on_exception():
    def broken(_text):
        raise RuntimeError("embedder not loaded")

    assert latency_hygiene.warmup_embedder(broken) is None
