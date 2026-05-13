"""Tests for ultron.desktop.vlm."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ultron.desktop.vlm import (
    DEFAULT_DESCRIBE_PROMPT,
    DEFAULT_MOONDREAM_REPO,
    Moondream2VLM,
    VLMLoadError,
    VLMResult,
    build_vlm_from_config,
    get_vlm,
    set_vlm,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


def test_vlm_result_is_frozen():
    r = VLMResult(success=True, description="x")
    with pytest.raises(Exception):
        r.success = False


def test_vlm_result_defaults():
    r = VLMResult(success=False)
    assert r.description is None
    assert r.elapsed_ms == 0.0
    assert r.error is None


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


def test_construction_rejects_unsupported_device():
    with pytest.raises(VLMLoadError):
        Moondream2VLM(device="tpu")


def test_construction_rejects_bad_max_tokens():
    with pytest.raises(VLMLoadError):
        Moondream2VLM(max_tokens=0)
    with pytest.raises(VLMLoadError):
        Moondream2VLM(max_tokens=99999)


def test_construction_when_backend_missing(monkeypatch):
    monkeypatch.setattr(
        "ultron.desktop.vlm._import_backend", lambda: None,
    )
    with pytest.raises(VLMLoadError):
        Moondream2VLM()


def test_loaded_starts_false():
    # Don't actually load -- just construct.
    # Without _ensure_loaded mocked, the backend lazy import succeeds
    # (transformers IS installed) and Moondream2VLM constructs fine.
    vlm = Moondream2VLM()
    assert vlm.loaded is False


# ---------------------------------------------------------------------------
# describe() fail-open paths (no real model load)
# ---------------------------------------------------------------------------


def test_describe_empty_bytes_returns_failure():
    vlm = Moondream2VLM()
    r = vlm.describe(b"")
    assert r.success is False
    assert "empty image" in (r.error or "")


def test_describe_returns_failure_when_load_fails(monkeypatch):
    """When _ensure_loaded raises VLMLoadError, describe returns a failure result."""
    vlm = Moondream2VLM()

    def boom():
        raise VLMLoadError("simulated load failure")

    monkeypatch.setattr(vlm, "_ensure_loaded", boom)
    r = vlm.describe(b"\x89PNG\r\n\x1a\n0123")
    assert r.success is False
    assert "load failure" in (r.error or "")


def test_describe_returns_failure_on_image_decode(monkeypatch):
    vlm = Moondream2VLM()
    monkeypatch.setattr(vlm, "_ensure_loaded", lambda: None)
    # Pillow can't open this; should report image decode failure.
    r = vlm.describe(b"not a real image")
    assert r.success is False
    assert "image decode failed" in (r.error or "")


def test_describe_returns_failure_on_inference_exception(monkeypatch):
    vlm = Moondream2VLM()
    monkeypatch.setattr(vlm, "_ensure_loaded", lambda: None)
    # Make the model + tokenizer present so describe gets past the load gate.
    fake_model = MagicMock()
    fake_model.encode_image.side_effect = RuntimeError("simulated inference fail")
    vlm._model = fake_model
    vlm._tokenizer = MagicMock()

    # Build a tiny real PNG so PIL can open it.
    from PIL import Image
    import io
    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = vlm.describe(buf.getvalue())
    assert r.success is False
    assert "inference failed" in (r.error or "")


def test_describe_returns_success_with_valid_output(monkeypatch):
    vlm = Moondream2VLM()
    monkeypatch.setattr(vlm, "_ensure_loaded", lambda: None)
    fake_model = MagicMock()
    fake_model.encode_image.return_value = "encoded"
    fake_model.answer_question.return_value = "A red square."
    vlm._model = fake_model
    vlm._tokenizer = MagicMock()

    from PIL import Image
    import io
    img = Image.new("RGB", (8, 8), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = vlm.describe(buf.getvalue(), prompt="What's in this?")
    assert r.success is True
    assert r.description == "A red square."
    fake_model.answer_question.assert_called_once_with(
        "encoded", "What's in this?", vlm._tokenizer,
    )


def test_describe_empty_model_output_returns_failure(monkeypatch):
    vlm = Moondream2VLM()
    monkeypatch.setattr(vlm, "_ensure_loaded", lambda: None)
    fake_model = MagicMock()
    fake_model.encode_image.return_value = "encoded"
    fake_model.answer_question.return_value = "   "
    vlm._model = fake_model
    vlm._tokenizer = MagicMock()

    from PIL import Image
    import io
    img = Image.new("RGB", (4, 4), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = vlm.describe(buf.getvalue())
    assert r.success is False
    assert "empty model output" in (r.error or "")


def test_describe_uses_default_prompt_when_none(monkeypatch):
    vlm = Moondream2VLM()
    monkeypatch.setattr(vlm, "_ensure_loaded", lambda: None)
    captured = []
    fake_model = MagicMock()
    fake_model.encode_image.return_value = "encoded"
    fake_model.answer_question.side_effect = (
        lambda enc, q, tok: captured.append(q) or "ok"
    )
    vlm._model = fake_model
    vlm._tokenizer = MagicMock()

    from PIL import Image
    import io
    img = Image.new("RGB", (4, 4))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    vlm.describe(buf.getvalue(), prompt=None)
    assert captured == [DEFAULT_DESCRIBE_PROMPT]


# ---------------------------------------------------------------------------
# _ensure_loaded caches failure
# ---------------------------------------------------------------------------


def test_ensure_loaded_caches_failure(monkeypatch):
    """A failing first load shouldn't retry the load on every subsequent call.

    The flag _load_failed is set so we don't repeatedly hit a slow
    network / disk error when the model file is missing.
    """
    vlm = Moondream2VLM()
    # Replace AutoModelForCausalLM.from_pretrained with a failing stub.
    fake_backend = dict(vlm._backend)
    call_count = [0]

    class FailingTokenizer:
        @classmethod
        def from_pretrained(cls, *a, **kw):
            call_count[0] += 1
            raise RuntimeError("network unavailable")

    fake_backend["AutoTokenizer"] = FailingTokenizer
    vlm._backend = fake_backend

    # First call -- should raise.
    with pytest.raises(VLMLoadError):
        vlm._ensure_loaded()
    # Second call -- should re-raise WITHOUT re-running from_pretrained.
    with pytest.raises(VLMLoadError):
        vlm._ensure_loaded()
    assert call_count[0] == 1, "load should not be retried after first failure"


# ---------------------------------------------------------------------------
# Singleton + screen_context wiring
# ---------------------------------------------------------------------------


def test_get_vlm_starts_none():
    set_vlm(None)
    try:
        assert get_vlm() is None
    finally:
        set_vlm(None)


def test_set_vlm_wires_screen_context_hook(monkeypatch):
    from ultron.desktop import screen_context

    set_vlm(None)
    try:
        custom = Moondream2VLM.__new__(Moondream2VLM)
        custom._model = MagicMock()
        custom._tokenizer = MagicMock()

        def fake_describe(self, image_bytes, *, prompt=None):
            return VLMResult(success=True, description="from custom")

        custom.describe = fake_describe.__get__(custom, Moondream2VLM)
        set_vlm(custom)
        assert get_vlm() is custom
        # screen_context hook is now wired
        hook = screen_context.get_vlm_describe()
        assert hook is not None
        # It should call through to our custom VLM.
        out = hook(b"\x89PNG_DUMMY")
        assert out == "from custom"
    finally:
        set_vlm(None)


def test_set_vlm_none_clears_hook():
    from ultron.desktop import screen_context

    custom = Moondream2VLM.__new__(Moondream2VLM)
    set_vlm(custom)
    set_vlm(None)
    assert get_vlm() is None
    assert screen_context.get_vlm_describe() is None


def test_describe_via_singleton_returns_none_when_unset():
    from ultron.desktop.vlm import _describe_via_singleton

    set_vlm(None)
    assert _describe_via_singleton(b"\x89PNG") is None


# ---------------------------------------------------------------------------
# build_vlm_from_config
# ---------------------------------------------------------------------------


def test_build_vlm_from_config_disabled_returns_none():
    assert build_vlm_from_config(enabled=False) is None


def test_build_vlm_from_config_returns_instance_when_enabled():
    vlm = build_vlm_from_config(enabled=True, device="cpu")
    assert vlm is not None
    assert isinstance(vlm, Moondream2VLM)
    assert vlm.device == "cpu"


def test_build_vlm_from_config_returns_none_on_construction_failure():
    vlm = build_vlm_from_config(enabled=True, device="tpu")  # bad device
    assert vlm is None
