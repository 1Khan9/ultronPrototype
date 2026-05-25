"""4B optimization plan — LLMEngine.reload_for_preset() tests.

Verifies the hot-swap semantics:

- New ``Llama`` is built BEFORE the old is released (failure-safe).
- On success: history cleared, env vars updated, ``self._llm`` swapped.
- On failure: old ``Llama`` survives, env vars restored, error returned.
- Idempotent on same-preset call.
- HTTP runtime rejects the call (in_process only).
- Unknown preset rejected.

Mocks the underlying ``Llama`` so no GGUF or GPU is needed. The actual
VRAM cycle on real hardware is exercised in Stage H's interactive
smoke test.
"""
from __future__ import annotations

import os
from collections import deque
from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from ultron.llm.inference import LLMEngine


def _make_engine(runtime: str = "in_process") -> LLMEngine:
    """Manual LLMEngine construction that bypasses the real Llama load."""
    eng = LLMEngine.__new__(LLMEngine)
    eng._runtime = runtime
    eng._llm = MagicMock(name="initial_llm")
    eng._cancel = Event()
    eng._history = deque(maxlen=12)
    eng._memory = None
    eng._explicit_system_prompt = None
    eng._persona_loader = None
    eng._static_system_prompt = "test"
    eng.system_prompt = "test"
    eng.history_turns = 6
    eng.model_path = None
    eng._logged_initial_persona = True
    return eng


# ---------------------------------------------------------------------------
# Idempotent / validation guards
# ---------------------------------------------------------------------------


def test_reload_rejects_http_runtime() -> None:
    eng = _make_engine(runtime="http_server")
    ok, msg = eng.reload_for_preset("qwen3.5-4b")
    assert ok is False
    assert "in_process" in msg


def test_reload_rejects_unknown_preset() -> None:
    eng = _make_engine()
    ok, msg = eng.reload_for_preset("definitely-not-a-preset")
    assert ok is False
    assert "unknown preset" in msg


def test_reload_idempotent_on_same_preset() -> None:
    eng = _make_engine()
    initial_llm = eng._llm
    with patch("ultron.config.get_config") as gc:
        gc.return_value.llm.preset = "qwen3.5-9b"
        ok, msg = eng.reload_for_preset("qwen3.5-9b")
    assert ok is True
    assert "already on" in msg
    # _llm must NOT have been replaced
    assert eng._llm is initial_llm


# ---------------------------------------------------------------------------
# Successful swap
# ---------------------------------------------------------------------------


def test_reload_swaps_to_new_llama_on_success() -> None:
    eng = _make_engine()
    initial_llm = eng._llm
    eng._history.append(("user", "earlier"))  # populated; should clear

    new_mock = MagicMock(name="new_llm")
    new_path = MagicMock(name="new_path")

    def fake_build(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None):
        return new_mock, new_path

    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc, \
         patch.object(eng, "_build_llama", side_effect=fake_build), \
         patch.dict(os.environ, {}, clear=False):
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_preset("qwen3.5-4b")

    assert ok is True
    assert "loaded qwen3.5-4b" in msg
    # _llm replaced; history reset
    assert eng._llm is new_mock
    assert eng._llm is not initial_llm
    assert eng.model_path is new_path
    assert len(eng._history) == 0
    # Cancel flag cleared (no leftover stop signal)
    assert not eng._cancel.is_set()


def test_reload_sets_env_for_new_preset() -> None:
    """The env var is the authoritative path the loader reads on
    reload_config(). Keeping it in sync makes a follow-up explicit
    reload_config() call see the same preset."""
    eng = _make_engine()
    new_mock = MagicMock(name="new_llm")
    new_path = MagicMock(name="new_path")

    def fake_build(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None):
        return new_mock, new_path

    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc, \
         patch.object(eng, "_build_llama", side_effect=fake_build), \
         patch.dict(os.environ, {}, clear=False):
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        eng.reload_for_preset("qwen3.5-4b")
        assert os.environ.get("ULTRON_LLM_PRESET") == "qwen3.5-4b"


def test_reload_clears_stale_model_path_env() -> None:
    """ULTRON_LLM_MODEL_PATH would override the preset's auto-fill —
    a stale value from earlier swaps would silently keep the old
    model. reload_for_preset clears it."""
    eng = _make_engine()
    new_mock = MagicMock(name="new_llm")
    new_path = MagicMock(name="new_path")

    def fake_build(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None):
        return new_mock, new_path

    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc, \
         patch.object(eng, "_build_llama", side_effect=fake_build), \
         patch.dict(os.environ, {"ULTRON_LLM_MODEL_PATH": "/some/stale.gguf"}, clear=False):
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        eng.reload_for_preset("qwen3.5-4b")
        assert "ULTRON_LLM_MODEL_PATH" not in os.environ


# ---------------------------------------------------------------------------
# Failure path — old engine survives intact
# ---------------------------------------------------------------------------


def test_reload_failure_keeps_old_engine() -> None:
    eng = _make_engine()
    initial_llm = eng._llm
    eng._history.append(("user", "earlier"))

    def fake_build_raises(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None):
        raise FileNotFoundError("the new GGUF doesn't exist")

    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc, \
         patch.object(eng, "_build_llama", side_effect=fake_build_raises), \
         patch.dict(os.environ, {}, clear=False):
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_preset("qwen3.5-4b")

    assert ok is False
    assert "failed to load qwen3.5-4b" in msg
    # Old engine intact
    assert eng._llm is initial_llm
    # History preserved (not torn down on failure)
    assert len(eng._history) == 1
    # Cancel flag cleared so subsequent generate calls work
    assert not eng._cancel.is_set()


def test_reload_failure_restores_env_vars() -> None:
    """If reload fails, the env vars must rewind so subsequent
    get_config() calls don't pick up the half-applied state."""
    eng = _make_engine()

    def fake_build_raises(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None):
        raise FileNotFoundError("nope")

    initial_env = {
        "ULTRON_LLM_PRESET": "qwen3.5-9b",
        "ULTRON_LLM_MODEL_PATH": "/initial/path.gguf",
    }
    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc, \
         patch.object(eng, "_build_llama", side_effect=fake_build_raises), \
         patch.dict(os.environ, initial_env, clear=False):
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        eng.reload_for_preset("qwen3.5-4b")

        assert os.environ["ULTRON_LLM_PRESET"] == "qwen3.5-9b"
        assert os.environ["ULTRON_LLM_MODEL_PATH"] == "/initial/path.gguf"


def test_reload_failure_when_env_was_unset_clears_it() -> None:
    """If ULTRON_LLM_PRESET wasn't set going in, a failed reload must
    leave it unset (not stuck at the failed target)."""
    eng = _make_engine()

    def fake_build_raises(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None):
        raise FileNotFoundError("nope")

    env_clean = {k: v for k, v in os.environ.items()
                 if k not in ("ULTRON_LLM_PRESET", "ULTRON_LLM_MODEL_PATH")}
    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc, \
         patch.object(eng, "_build_llama", side_effect=fake_build_raises), \
         patch.dict(os.environ, env_clean, clear=True):
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        eng.reload_for_preset("qwen3.5-4b")
        assert "ULTRON_LLM_PRESET" not in os.environ


# ---------------------------------------------------------------------------
# 2026-05-26 openclaw-clawhub T1 + T9 wiring: trust pre-check
# ---------------------------------------------------------------------------


def test_reload_refuses_on_digest_mismatch(monkeypatch, tmp_path) -> None:
    """Tampered GGUF -> reload_for_preset refuses BEFORE the Llama load.

    Verifies the trust pre-check: when verify_single_artifact_sync
    returns status='mismatch', reload bails out with a clear error
    and does NOT call _build_llama.
    """
    eng = _make_engine()

    # Patch the verifier to claim a mismatch.
    from ultron.install import voice_baseline_verify as vbv

    def _fake_verify(*a, **kw):
        return vbv.ArtifactVerificationOutcome(
            identifier=kw["identifier"],
            path=kw["path"],
            status="mismatch",
            detail="pinned=aaa actual=bbb",
        )

    monkeypatch.setattr(vbv, "verify_single_artifact_sync", _fake_verify)

    # Ensure _build_llama is NOT reached.
    build_calls = []
    monkeypatch.setattr(
        eng, "_build_llama",
        lambda *a, **kw: build_calls.append((a, kw)),
    )

    with patch("ultron.config.get_config") as gc:
        gc.return_value.llm.preset = "qwen3.5-9b"
        ok, msg = eng.reload_for_preset("qwen3.5-4b")

    assert ok is False
    assert "digest mismatch" in msg.lower() or "tampered" in msg.lower()
    assert build_calls == []  # never called


def test_reload_proceeds_when_digest_verified(monkeypatch) -> None:
    """status='verified' / 'pinned' / 'missing' / 'error' all allow
    the swap to proceed.
    """
    from ultron.install import voice_baseline_verify as vbv

    # 'verified' outcome -> proceed
    def _fake_verify_ok(*a, **kw):
        return vbv.ArtifactVerificationOutcome(
            identifier=kw["identifier"],
            path=kw["path"],
            status="verified",
            detail="digest matches pin",
        )

    eng = _make_engine()
    monkeypatch.setattr(vbv, "verify_single_artifact_sync", _fake_verify_ok)

    fake_llm = MagicMock(name="new_llm")
    monkeypatch.setattr(
        eng, "_build_llama",
        lambda *a, **kw: (fake_llm, "models/Qwen3.5-4B-Q4_K_M.gguf"),
    )

    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc:
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        ok, _ = eng.reload_for_preset("qwen3.5-4b")
    assert ok is True


def test_reload_continues_when_pre_check_raises(monkeypatch) -> None:
    """Fail-open: a broken trust pre-check must NOT block the swap.

    The actual Llama load + the async voice-baseline verifier provide
    defence in depth.
    """
    from ultron.install import voice_baseline_verify as vbv

    def _boom(*a, **kw):
        raise RuntimeError("simulated pre-check failure")

    monkeypatch.setattr(vbv, "verify_single_artifact_sync", _boom)

    eng = _make_engine()
    fake_llm = MagicMock(name="new_llm")
    monkeypatch.setattr(
        eng, "_build_llama",
        lambda *a, **kw: (fake_llm, "models/Qwen3.5-4B-Q4_K_M.gguf"),
    )

    with patch("ultron.config.get_config") as gc, \
         patch("ultron.config.reload_config") as rc:
        gc.return_value.llm.preset = "qwen3.5-9b"
        rc.return_value.llm = MagicMock()
        ok, _ = eng.reload_for_preset("qwen3.5-4b")
    # Pre-check failure was swallowed -> swap proceeded.
    assert ok is True
