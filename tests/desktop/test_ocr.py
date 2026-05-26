"""Tests for ultron.desktop.ocr (catalog 08 T7 deferred)."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

from ultron.desktop.ocr import (
    DEFAULT_LANG,
    DEFAULT_PSM,
    TESSERACT_CMD_ENV,
    OCRResult,
    is_ocr_available,
    ocr_image_bytes,
    ocr_screen_monitor,
    ocr_screen_region,
    reset_pytesseract_cache_for_testing,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeShot:
    image_bytes: Optional[bytes]
    width: int = 100
    height: int = 50
    origin_x: int = 0
    origin_y: int = 0
    monitor_index: int = 0
    timestamp: float = 0.0
    bytes_discarded: bool = False


def _install_fake_pytesseract(monkeypatch, *, returns="extracted text", raises=None):
    """Install a fake pytesseract module so the lazy import picks it up."""
    fake_pyt = types.SimpleNamespace()
    fake_pyt_sub = types.SimpleNamespace(tesseract_cmd="tesseract")
    fake_pyt.pytesseract = fake_pyt_sub

    def _img_to_str(image, *, lang=None, config=None):
        if raises is not None:
            raise raises
        return returns

    fake_pyt.image_to_string = _img_to_str
    fake_pyt.get_tesseract_version = lambda: "5.3.3"
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pyt)
    reset_pytesseract_cache_for_testing()
    return fake_pyt


def _install_missing_pytesseract(monkeypatch):
    """Force pytesseract import to fail."""
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    reset_pytesseract_cache_for_testing()


def _install_broken_tesseract_binary(monkeypatch):
    """pytesseract is importable but binary lookup raises."""
    fake_pyt = types.SimpleNamespace()
    fake_pyt_sub = types.SimpleNamespace(tesseract_cmd="tesseract")
    fake_pyt.pytesseract = fake_pyt_sub

    class TesseractNotFoundError(Exception):
        pass

    fake_pyt.TesseractNotFoundError = TesseractNotFoundError

    def _missing(*a, **kw):
        raise TesseractNotFoundError("not on PATH")

    fake_pyt.get_tesseract_version = _missing
    fake_pyt.image_to_string = _missing
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pyt)
    reset_pytesseract_cache_for_testing()
    return fake_pyt


# Minimal 1x1 PNG bytes (transparent black pixel).
_TINY_PNG_BYTES = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452"
    "0000000100000001010300000025DB56"
    "CA00000003504C5445000000A77A3DDA"
    "0000000174524E530040E6D8660000000A"
    "49444154789C636000000000020001E2"
    "21BC330000000049454E44AE426082"
)


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_default_constants():
    assert DEFAULT_PSM == 6
    assert DEFAULT_LANG == "eng"
    assert TESSERACT_CMD_ENV == "ULTRON_TESSERACT_CMD"


def test_ocr_result_is_frozen():
    r = OCRResult(success=True, text="hi")
    with pytest.raises(Exception):
        r.success = False


# ---------------------------------------------------------------------------
# is_ocr_available
# ---------------------------------------------------------------------------


def test_is_ocr_available_false_when_pytesseract_missing(monkeypatch):
    _install_missing_pytesseract(monkeypatch)
    assert is_ocr_available() is False


def test_is_ocr_available_false_when_binary_missing(monkeypatch):
    _install_broken_tesseract_binary(monkeypatch)
    assert is_ocr_available() is False


def test_is_ocr_available_true_when_both_present(monkeypatch):
    _install_fake_pytesseract(monkeypatch)
    assert is_ocr_available() is True


# ---------------------------------------------------------------------------
# ocr_image_bytes
# ---------------------------------------------------------------------------


def test_ocr_image_bytes_happy_path(monkeypatch):
    _install_fake_pytesseract(monkeypatch, returns="hello world")
    result = ocr_image_bytes(_TINY_PNG_BYTES)
    assert result.success is True
    assert result.text == "hello world"
    assert result.engine == "tesseract"
    assert result.psm == DEFAULT_PSM
    assert result.lang == DEFAULT_LANG
    assert result.elapsed_ms >= 0


def test_ocr_image_bytes_strips_whitespace(monkeypatch):
    _install_fake_pytesseract(monkeypatch, returns="  \n  trimmed  \n  ")
    result = ocr_image_bytes(_TINY_PNG_BYTES)
    assert result.success is True
    assert result.text == "trimmed"


def test_ocr_image_bytes_rejects_empty_bytes():
    result = ocr_image_bytes(b"")
    assert result.success is False
    assert "non-empty bytes" in (result.error or "")


def test_ocr_image_bytes_rejects_non_bytes():
    result = ocr_image_bytes("not bytes")  # type: ignore[arg-type]
    assert result.success is False
    assert "non-empty bytes" in (result.error or "")


def test_ocr_image_bytes_returns_unavailable_when_pytesseract_missing(monkeypatch):
    _install_missing_pytesseract(monkeypatch)
    result = ocr_image_bytes(_TINY_PNG_BYTES)
    assert result.success is False
    assert result.engine == "unavailable"
    assert "pytesseract unavailable" in (result.error or "")


def test_ocr_image_bytes_returns_unavailable_when_tesseract_raises(monkeypatch):
    _install_fake_pytesseract(
        monkeypatch, raises=RuntimeError("binary segfault"),
    )
    result = ocr_image_bytes(_TINY_PNG_BYTES)
    assert result.success is False
    assert result.engine == "unavailable"
    assert "tesseract error" in (result.error or "")


def test_ocr_image_bytes_psm_and_lang_forwarded(monkeypatch):
    seen = {}

    def _fake_img_to_string(image, *, lang=None, config=None):
        seen["lang"] = lang
        seen["config"] = config
        return "x"

    fake_pyt = types.SimpleNamespace(
        pytesseract=types.SimpleNamespace(tesseract_cmd="t"),
        image_to_string=_fake_img_to_string,
        get_tesseract_version=lambda: "5.0",
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pyt)
    reset_pytesseract_cache_for_testing()

    result = ocr_image_bytes(_TINY_PNG_BYTES, psm=11, lang="eng+spa")
    assert result.success is True
    assert seen["lang"] == "eng+spa"
    assert seen["config"] == "--psm 11"
    assert result.psm == 11
    assert result.lang == "eng+spa"


def test_ocr_image_bytes_pil_decode_failure_returns_unavailable(monkeypatch):
    _install_fake_pytesseract(monkeypatch)
    # Bogus bytes can't be decoded by PIL.
    result = ocr_image_bytes(b"not a png")
    assert result.success is False
    assert "PIL decode failed" in (result.error or "")


def test_ocr_image_bytes_preserves_region_metadata(monkeypatch):
    _install_fake_pytesseract(monkeypatch, returns="x")
    region = (10, 20, 100, 50)
    result = ocr_image_bytes(_TINY_PNG_BYTES, region=region)
    assert result.success is True
    assert result.region == region


def test_ocr_image_bytes_uses_env_override_for_binary(monkeypatch):
    monkeypatch.setenv(TESSERACT_CMD_ENV, "/custom/path/to/tesseract")
    fake_pyt = _install_fake_pytesseract(monkeypatch)
    ocr_image_bytes(_TINY_PNG_BYTES)
    assert fake_pyt.pytesseract.tesseract_cmd == "/custom/path/to/tesseract"


# ---------------------------------------------------------------------------
# ocr_screen_region
# ---------------------------------------------------------------------------


def test_ocr_screen_region_rejects_non_positive_dimensions():
    result = ocr_screen_region(x=0, y=0, width=0, height=50)
    assert result.success is False
    assert "must be > 0" in (result.error or "")
    result = ocr_screen_region(x=0, y=0, width=10, height=-1)
    assert result.success is False
    assert "must be > 0" in (result.error or "")


def test_ocr_screen_region_happy_path(monkeypatch):
    _install_fake_pytesseract(monkeypatch, returns="from region")
    cap = MagicMock()
    cap.capture_region.return_value = _FakeShot(
        image_bytes=_TINY_PNG_BYTES, width=200, height=100,
    )
    result = ocr_screen_region(
        x=10, y=20, width=200, height=100, capture=cap,
    )
    assert result.success is True
    assert result.text == "from region"
    assert result.region == (10, 20, 200, 100)
    cap.capture_region.assert_called_once()


def test_ocr_screen_region_capture_returns_none(monkeypatch):
    _install_fake_pytesseract(monkeypatch)
    cap = MagicMock()
    cap.capture_region.return_value = None
    result = ocr_screen_region(
        x=0, y=0, width=10, height=10, capture=cap,
    )
    assert result.success is False
    assert "no image" in (result.error or "")


def test_ocr_screen_region_capture_no_bytes(monkeypatch):
    _install_fake_pytesseract(monkeypatch)
    cap = MagicMock()
    cap.capture_region.return_value = _FakeShot(image_bytes=None)
    result = ocr_screen_region(
        x=0, y=0, width=10, height=10, capture=cap,
    )
    assert result.success is False
    assert "no image" in (result.error or "")


def test_ocr_screen_region_capture_raises(monkeypatch):
    _install_fake_pytesseract(monkeypatch)
    cap = MagicMock()
    cap.capture_region.side_effect = RuntimeError("display gone")
    result = ocr_screen_region(
        x=0, y=0, width=10, height=10, capture=cap,
    )
    assert result.success is False
    assert "capture raised" in (result.error or "")


# ---------------------------------------------------------------------------
# ocr_screen_monitor
# ---------------------------------------------------------------------------


def test_ocr_screen_monitor_happy_path(monkeypatch):
    _install_fake_pytesseract(monkeypatch, returns="full screen")
    cap = MagicMock()
    cap.capture_monitor.return_value = _FakeShot(
        image_bytes=_TINY_PNG_BYTES,
        width=1920, height=1080,
        origin_x=0, origin_y=0,
        monitor_index=0,
    )
    result = ocr_screen_monitor(monitor_index=0, capture=cap)
    assert result.success is True
    assert result.text == "full screen"
    assert result.region == (0, 0, 1920, 1080)


def test_ocr_screen_monitor_capture_returns_none(monkeypatch):
    _install_fake_pytesseract(monkeypatch)
    cap = MagicMock()
    cap.capture_monitor.return_value = None
    result = ocr_screen_monitor(monitor_index=0, capture=cap)
    assert result.success is False


def test_ocr_screen_monitor_uses_capture_singleton_when_not_injected(monkeypatch):
    _install_fake_pytesseract(monkeypatch, returns="from singleton")
    fake_cap = MagicMock()
    fake_cap.capture_monitor.return_value = _FakeShot(
        image_bytes=_TINY_PNG_BYTES, width=1920, height=1080,
    )
    monkeypatch.setattr(
        "ultron.desktop.capture.get_screen_capture", lambda: fake_cap,
    )
    result = ocr_screen_monitor(monitor_index=0)
    assert result.success is True
    assert result.text == "from singleton"
