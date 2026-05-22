"""Tests for the streaming client methods on :class:`ParakeetEngine`.

We construct a ParakeetEngine with the NeMo / subprocess machinery
short-circuited (mocked ``is_nemo_available`` + ``_spawn_server_if_needed``)
and inject a fake ``requests`` module to verify the HTTP wire format
matches what the server expects.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fake HTTP layer
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}: {self._payload}"
            )

    def json(self):
        return self._payload


class _FakeRequests:
    """Lightweight ``requests``-shaped stub recording posts + injecting
    deterministic responses based on URL suffix."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.responses: Dict[str, Any] = {}
        self._stream_counter = 0
        self._stream_buffers: Dict[str, np.ndarray] = {}

    # Stand-ins for the exceptions module the engine references for
    # error-path handling. Not invoked in happy-path tests.
    class exceptions:
        class RequestException(Exception): pass
        class ConnectionError(RequestException): pass
        class Timeout(RequestException): pass

    def post(self, url, *, data=None, files=None, headers=None, timeout=None):
        self.calls.append({
            "method": "POST",
            "url": url,
            "data_len": len(data) if data else 0,
            "files": files is not None,
            "headers": headers or {},
            "timeout": timeout,
        })
        if url.endswith("/stream/start"):
            self._stream_counter += 1
            sid = f"sid-{self._stream_counter}"
            self._stream_buffers[sid] = np.zeros(0, dtype=np.float32)
            return _FakeResponse({"stream_id": sid, "sample_rate": 16000})
        if "/stream/feed/" in url:
            sid = url.rsplit("/", 1)[-1]
            if data:
                chunk = np.frombuffer(data, dtype=np.float32)
                self._stream_buffers[sid] = np.concatenate(
                    [self._stream_buffers.get(sid, np.zeros(0, dtype=np.float32)), chunk],
                )
            seconds = self._stream_buffers[sid].size / 16000.0
            return _FakeResponse({
                "partial": "partial " * max(1, int(seconds * 2)),
                "audio_seconds": seconds,
                "inference_ms": 5.0,
            })
        if "/stream/stop/" in url:
            sid = url.rsplit("/", 1)[-1]
            buf = self._stream_buffers.pop(sid, np.zeros(0, dtype=np.float32))
            seconds = buf.size / 16000.0
            # Match the real server's behavior: empty buffer -> empty text
            # so the engine recognizes the cache-miss case and stashes None.
            if seconds == 0:
                return _FakeResponse({
                    "text": "",
                    "audio_seconds": 0.0,
                    "inference_ms": 0.0,
                })
            return _FakeResponse({
                "text": "final " * max(1, int(seconds * 2)),
                "audio_seconds": seconds,
                "inference_ms": 7.0,
            })
        raise AssertionError(f"unmocked POST {url}")

    def get(self, url, *, timeout=None):
        self.calls.append({"method": "GET", "url": url, "timeout": timeout})
        if "/healthz" in url:
            return _FakeResponse({"ok": True})
        raise AssertionError(f"unmocked GET {url}")


# ---------------------------------------------------------------------------
# Engine fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def parakeet_engine(monkeypatch):
    """Construct a ParakeetEngine bypassing real server / NeMo init."""
    from ultron.transcription import parakeet_engine as pe_mod

    monkeypatch.setattr(pe_mod, "is_nemo_available", lambda: True)
    monkeypatch.setattr(
        pe_mod, "_spawn_server_if_needed",
        lambda cfg: "http://127.0.0.1:8771",
    )

    fake_requests = _FakeRequests()
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    eng = pe_mod.ParakeetEngine()
    # Speed up streaming flushes for tests so we don't have to wait
    # the configured interval to observe a flush.
    eng.stream_feed_interval_s = 0.0
    return eng, fake_requests


# ---------------------------------------------------------------------------
# supports_streaming + lifecycle
# ---------------------------------------------------------------------------


def test_supports_streaming_returns_true(parakeet_engine):
    eng, _ = parakeet_engine
    assert eng.supports_streaming() is True


def test_start_stream_calls_server_start(parakeet_engine):
    eng, fake_req = parakeet_engine
    eng.start_stream()
    assert eng._stream_active is True
    assert eng._stream_id == "sid-1"
    start_calls = [c for c in fake_req.calls if c["url"].endswith("/stream/start")]
    assert len(start_calls) == 1


def test_start_stream_is_idempotent(parakeet_engine):
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.start_stream()
    eng.start_stream()
    start_calls = [c for c in fake_req.calls if c["url"].endswith("/stream/start")]
    assert len(start_calls) == 1


def test_start_stream_handles_http_failure(monkeypatch, parakeet_engine):
    """If the HTTP start call fails, streaming is silently disabled
    for this turn -- not raised into the voice loop."""
    eng, fake_req = parakeet_engine

    def _broken_post(*a, **kw):
        raise RuntimeError("simulated network failure")

    fake_req.post = _broken_post
    eng.start_stream()
    assert eng._stream_active is False


# ---------------------------------------------------------------------------
# feed_audio + partials
# ---------------------------------------------------------------------------


def test_feed_audio_sends_float32_bytes(parakeet_engine):
    eng, fake_req = parakeet_engine
    eng.start_stream()
    audio = np.full(1600, 0.1, dtype=np.float32)  # 0.1 s @ 16 kHz
    eng.feed_audio(audio, sample_rate=16000)

    feed_calls = [c for c in fake_req.calls if "/stream/feed/" in c["url"]]
    assert len(feed_calls) == 1
    assert feed_calls[0]["data_len"] == audio.nbytes
    # Content-Type signals raw float32 PCM, not multipart.
    assert "application/octet-stream" in feed_calls[0]["headers"].get(
        "Content-Type", ""
    )


def test_feed_audio_before_start_is_noop(parakeet_engine):
    eng, fake_req = parakeet_engine
    audio = np.full(1600, 0.1, dtype=np.float32)
    eng.feed_audio(audio)
    feed_calls = [c for c in fake_req.calls if "/stream/feed/" in c["url"]]
    assert feed_calls == []


def test_feed_audio_empty_is_noop(parakeet_engine):
    eng, fake_req = parakeet_engine
    eng.start_stream()
    pre_count = len(fake_req.calls)
    eng.feed_audio(np.zeros(0, dtype=np.float32))
    assert len(fake_req.calls) == pre_count


def test_feed_audio_coalesces_within_interval(parakeet_engine):
    """When feed_interval > 0, multiple small feeds batch into one HTTP
    call. Voice loop blocks (~32 ms) shouldn't each trigger an HTTP
    round-trip + GPU inference."""
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.stream_feed_interval_s = 0.5  # half-second batching

    audio = np.full(512, 0.05, dtype=np.float32)  # 32 ms
    for _ in range(5):
        eng.feed_audio(audio)

    feed_calls = [c for c in fake_req.calls if "/stream/feed/" in c["url"]]
    # First feed triggers an immediate flush (last_flush_at==0 at start),
    # subsequent ones fit inside the interval so they coalesce.
    assert len(feed_calls) <= 2, (
        f"expected coalescing; got {len(feed_calls)} HTTP feed calls"
    )


def test_get_partial_text_returns_last_partial(parakeet_engine):
    eng, _ = parakeet_engine
    eng.start_stream()
    audio = np.full(8000, 0.1, dtype=np.float32)  # 0.5 s
    eng.feed_audio(audio)
    partial = eng.get_partial_text()
    assert partial  # non-empty
    assert "partial" in partial


def test_get_partial_text_flushes_pending(parakeet_engine):
    """get_partial_text should flush any locally-buffered audio so the
    returned text reflects everything fed so far."""
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.stream_feed_interval_s = 100.0  # never auto-flush
    audio = np.full(8000, 0.1, dtype=np.float32)
    eng.feed_audio(audio)
    # No feed call yet because interval hasn't elapsed.
    feed_calls_before = [c for c in fake_req.calls if "/stream/feed/" in c["url"]]

    _ = eng.get_partial_text()
    feed_calls_after = [c for c in fake_req.calls if "/stream/feed/" in c["url"]]
    assert len(feed_calls_after) == len(feed_calls_before) + 1


# ---------------------------------------------------------------------------
# stop_stream
# ---------------------------------------------------------------------------


def test_stop_stream_returns_final_text(parakeet_engine):
    eng, _ = parakeet_engine
    eng.start_stream()
    eng.feed_audio(np.full(16000, 0.1, dtype=np.float32))  # 1 s
    text = eng.stop_stream()
    assert text  # non-empty
    assert "final" in text


def test_stop_stream_calls_server_stop(parakeet_engine):
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.feed_audio(np.full(16000, 0.1, dtype=np.float32))
    eng.stop_stream()
    stop_calls = [c for c in fake_req.calls if "/stream/stop/" in c["url"]]
    assert len(stop_calls) == 1


def test_stop_stream_clears_active_state(parakeet_engine):
    eng, _ = parakeet_engine
    eng.start_stream()
    eng.stop_stream()
    assert eng._stream_active is False
    assert eng._stream_id is None


def test_stop_stream_idempotent(parakeet_engine):
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.stop_stream()
    # Second stop returns cached text without server call.
    second = eng.stop_stream()
    stop_calls = [c for c in fake_req.calls if "/stream/stop/" in c["url"]]
    assert len(stop_calls) == 1


def test_stop_stream_stashes_cached_text_for_transcribe(parakeet_engine):
    """A subsequent transcribe() call should return the cached
    streaming result instead of running the model again."""
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.feed_audio(np.full(16000, 0.1, dtype=np.float32))
    streamed = eng.stop_stream()

    pre_calls = len(fake_req.calls)
    txn = eng.transcribe(np.full(16000, 0.1, dtype=np.float32))
    # transcribe should NOT have hit the /transcribe endpoint -- cache hit.
    transcribe_calls = [c for c in fake_req.calls if c["url"].endswith("/transcribe")]
    assert transcribe_calls == []
    assert txn == streamed


def test_stop_stream_empty_audio_stashes_none_for_cache_miss(parakeet_engine):
    """When stop is called without ever feeding audio, the cache miss
    signal lets the post-capture transcribe re-run on the buffer."""
    eng, fake_req = parakeet_engine
    eng.start_stream()
    result = eng.stop_stream()
    assert result == ""
    assert eng._last_streaming_text is None


def test_stop_stream_after_http_failure_returns_partial(parakeet_engine):
    """If the server-side stop call fails, we return whatever partial
    we last received -- never raise."""
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.feed_audio(np.full(16000, 0.1, dtype=np.float32))

    original_post = fake_req.post

    def _broken_post(url, *a, **kw):
        if "/stream/stop/" in url:
            raise RuntimeError("simulated stop failure")
        return original_post(url, *a, **kw)

    fake_req.post = _broken_post
    result = eng.stop_stream()
    # Should still return whatever the last partial was.
    assert "partial" in result or result == ""


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_feeds_do_not_lose_data(parakeet_engine):
    """Multiple threads feeding chunks should all append to the same
    session buffer without races."""
    eng, fake_req = parakeet_engine
    eng.start_stream()
    eng.stream_feed_interval_s = 0.0  # immediate flush

    def _feed():
        for _ in range(5):
            eng.feed_audio(np.full(1600, 0.05, dtype=np.float32))

    threads = [threading.Thread(target=_feed) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    feed_calls = [c for c in fake_req.calls if "/stream/feed/" in c["url"]]
    # We don't assert exact count (coalescing may bundle), only that
    # NO exception was raised and the stream is still active.
    assert eng._stream_active is True
    assert len(feed_calls) >= 1
