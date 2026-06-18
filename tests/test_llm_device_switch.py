"""LLM CPU<->GPU hot-switch tests (2026-06-18).

Two surfaces:

1. ``relay_speech.match_llm_device_switch`` — the strict voice matcher that
   returns "gpu" / "cpu" / None. Must fire on explicit move-the-model phrasings
   and abstain on game callouts / chatter that merely mention "gpu"/"cpu".

2. ``LLMEngine.reload_for_device`` — the device-optimized hot reload. Mocks
   ``_build_llama`` so no GGUF/GPU is needed; verifies the no-op guard, the
   device-profile kwargs passed to the loader, the load-new-then-release-old
   swap, history reset, device tracking, and the failure path (old engine
   survives).
"""
from __future__ import annotations

from collections import deque
from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from kenning.audio.relay_speech import match_llm_device_switch
from kenning.llm.inference import LLMEngine, _DEVICE_PROFILES


# ---------------------------------------------------------------------------
# Voice matcher
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("switch to the gpu", "gpu"),
        ("switch to gpu", "gpu"),
        ("move the model to the gpu", "gpu"),
        ("run the llm on the gpu", "gpu"),
        ("offload the model to the gpu", "gpu"),
        ("use the gpu for the model", "gpu"),
        ("use the gpu", "gpu"),
        ("put the brain on the graphics card", "gpu"),
        ("load the 3b on cuda", "gpu"),
        ("switch the model back to the cpu", "cpu"),
        ("move to the cpu", "cpu"),
        ("run the llm on the cpu", "cpu"),
        ("use the cpu", "cpu"),
        ("put the model back to the cpu", "cpu"),
        ("switch back to cpu", "cpu"),
        # negatives: callouts / chatter / questions / empty
        ("enemy on a site gpu burning", None),
        ("tell my team the cpu guy is pushing", None),
        ("what is a gpu", None),
        ("i should switch agents", None),
        ("flavor off", None),
        ("mute the relay", None),
        ("", None),
        ("the gpu is overheating", None),
    ],
)
def test_match_llm_device_switch(text, expected):
    assert match_llm_device_switch(text) == expected


# ---------------------------------------------------------------------------
# reload_for_device
# ---------------------------------------------------------------------------


def _make_engine(device: str = "cpu", runtime: str = "in_process") -> LLMEngine:
    eng = LLMEngine.__new__(LLMEngine)
    eng._runtime = runtime
    eng._llm = MagicMock(name="initial_llm")
    eng._cancel = Event()
    eng._history = deque(maxlen=12)
    eng._memory = None
    eng.model_path = "models/Llama-3.2-3B-Instruct-abliterated.Q4_K_M.gguf"
    eng._device = device
    eng._n_gpu_layers = 0 if device == "cpu" else -1
    eng.n_ctx = 6144
    return eng


def test_device_switch_rejects_http_runtime():
    eng = _make_engine(runtime="http_server")
    ok, msg = eng.reload_for_device("gpu")
    assert ok is False
    assert "in_process" in msg


def test_device_switch_rejects_unknown_device():
    eng = _make_engine()
    ok, msg = eng.reload_for_device("quantum")
    assert ok is False
    assert "unknown device" in msg


def test_device_switch_noop_when_already_on_target():
    eng = _make_engine(device="cpu")
    initial = eng._llm
    with patch.object(eng, "_build_llama") as build:
        ok, msg = eng.reload_for_device("cpu")
    assert ok is True
    assert "already on cpu" in msg
    build.assert_not_called()
    assert eng._llm is initial  # untouched


def test_device_switch_to_gpu_uses_gpu_profile(monkeypatch):
    eng = _make_engine(device="cpu")
    initial = eng._llm
    eng._history.append(("user", "earlier"))  # should clear on success

    new_llm = MagicMock(name="new_llm")
    captured = {}

    def fake_build(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None,
                   flash_attn=None, kv_cache_type=None, n_batch=None,
                   n_ubatch=None):
        captured.update(
            model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
            flash_attn=flash_attn, kv_cache_type=kv_cache_type,
            n_batch=n_batch, n_ubatch=n_ubatch,
        )
        return new_llm, "models/x.gguf", n_gpu_layers, n_ctx

    # Pretend CUDA is available so the GPU guard passes.
    fake_torch = MagicMock()
    fake_torch.cuda.is_available.return_value = True
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setattr(eng, "_build_llama", fake_build)

    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_device("gpu")

    assert ok is True
    assert msg == "moved to gpu"
    prof = _DEVICE_PROFILES["gpu"]
    assert captured["n_gpu_layers"] == prof["n_gpu_layers"] == -1
    assert captured["flash_attn"] == prof["flash_attn"] is True
    assert captured["kv_cache_type"] == prof["kv_cache_type"] == 8
    assert captured["n_batch"] == prof["n_batch"]
    assert captured["n_ubatch"] == prof["n_ubatch"]
    # Reloads on the SAME ctx the model was on.
    assert captured["n_ctx"] == 6144
    # Swapped + tracked + history reset.
    assert eng._llm is new_llm
    assert eng._llm is not initial
    assert eng._device == "gpu"
    assert eng._n_gpu_layers == -1
    assert len(eng._history) == 0
    assert not eng._cancel.is_set()


def test_device_switch_to_cpu_uses_cpu_profile(monkeypatch):
    eng = _make_engine(device="gpu")
    new_llm = MagicMock(name="new_llm")
    captured = {}

    def fake_build(cfg, *, model_path=None, n_ctx=None, n_gpu_layers=None,
                   flash_attn=None, kv_cache_type=None, n_batch=None,
                   n_ubatch=None):
        captured.update(
            n_gpu_layers=n_gpu_layers, flash_attn=flash_attn,
            kv_cache_type=kv_cache_type, n_ubatch=n_ubatch,
        )
        return new_llm, "models/x.gguf", n_gpu_layers, n_ctx

    monkeypatch.setattr(eng, "_build_llama", fake_build)
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_device("cpu")

    assert ok is True
    assert msg == "moved to cpu"
    prof = _DEVICE_PROFILES["cpu"]
    assert captured["n_gpu_layers"] == 0
    # CPU MUST disable flash-attn and use F16 KV (flash-off requires F16).
    assert captured["flash_attn"] is False
    assert captured["kv_cache_type"] == 1
    assert captured["n_ubatch"] == prof["n_ubatch"] == 256
    assert eng._device == "cpu"


def test_device_switch_gpu_refused_without_cuda(monkeypatch):
    eng = _make_engine(device="cpu")
    fake_torch = MagicMock()
    fake_torch.cuda.is_available.return_value = False
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    build = MagicMock()
    monkeypatch.setattr(eng, "_build_llama", build)

    ok, msg = eng.reload_for_device("gpu")
    assert ok is False
    assert "CUDA" in msg
    build.assert_not_called()  # refused before the load


def test_device_switch_failure_keeps_old_engine(monkeypatch):
    eng = _make_engine(device="cpu")
    initial = eng._llm
    eng._history.append(("user", "earlier"))

    def boom(*a, **kw):
        raise RuntimeError("load failed")

    # CPU target -> no CUDA guard, goes straight to the load.
    monkeypatch.setattr(eng, "_build_llama", boom)
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_device("gpu", force=True)  # force past no-op

    assert ok is False
    assert "failed to move" in msg
    assert eng._llm is initial          # old engine survives
    assert eng._device == "cpu"         # tracking unchanged
    assert len(eng._history) == 1       # history not torn down
    assert not eng._cancel.is_set()


def test_device_switch_partial_offload_reapplies_full_profile(monkeypatch):
    # A user on PARTIAL GPU offload (label "gpu", but 20 layers) saying
    # "switch to gpu" must NOT no-op -- it must reload to the full-offload
    # profile (-1), because the no-op guard compares the resolved n_gpu_layers
    # against the profile target, not just the coarse device label.
    eng = _make_engine(device="gpu")
    eng._n_gpu_layers = 20  # partial offload
    new_llm = MagicMock(name="new_llm")
    captured = {}

    def fake_build(cfg, **kw):
        captured.update(kw)
        return new_llm, "models/x.gguf", kw["n_gpu_layers"], kw["n_ctx"]

    fake_torch = MagicMock()
    fake_torch.cuda.is_available.return_value = True
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    monkeypatch.setattr(eng, "_build_llama", fake_build)
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_device("gpu")

    assert ok is True
    assert msg == "moved to gpu", "partial offload must reload, not no-op"
    assert captured["n_gpu_layers"] == -1  # full profile applied
    assert eng._n_gpu_layers == -1


def test_device_switch_exact_profile_noops(monkeypatch):
    # Already on the EXACT full-GPU profile (-1) -> no-op.
    eng = _make_engine(device="gpu")
    eng._n_gpu_layers = -1
    with patch.object(eng, "_build_llama") as build:
        ok, msg = eng.reload_for_device("gpu")
    assert ok is True
    assert "already on gpu" in msg
    build.assert_not_called()


def test_device_switch_force_reloads_same_device(monkeypatch):
    eng = _make_engine(device="cpu")
    initial = eng._llm
    new_llm = MagicMock(name="new_llm")

    def fake_build(cfg, **kw):
        return new_llm, "models/x.gguf", kw["n_gpu_layers"], kw["n_ctx"]

    monkeypatch.setattr(eng, "_build_llama", fake_build)
    with patch("kenning.llm.inference.get_config") as gc:
        gc.return_value.llm = MagicMock()
        ok, msg = eng.reload_for_device("cpu", force=True)

    assert ok is True
    assert msg == "moved to cpu"
    assert eng._llm is new_llm
    assert eng._llm is not initial
