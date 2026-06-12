"""Tests for the streaming endpoints in ``kenningVoiceAudio/scripts/parakeet_server.py``.

We exercise the FastAPI app via ``starlette.testclient`` with the
NeMo-backed :class:`ParakeetHolder` replaced by a deterministic stub.
This lets us test the streaming protocol -- session lifecycle, buffer
accumulation, re-transcription, error paths -- without loading the
~700 MB NeMo model or requiring CUDA. The server module is loaded by
file path because it lives outside the importable Python package
tree.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Load the server module by file path (it lives in kenningVoiceAudio/scripts/)
# ---------------------------------------------------------------------------


_SERVER_PATH = (
    Path(__file__).resolve().parent.parent
    / "kenningVoiceAudio" / "scripts" / "parakeet_server.py"
)


@pytest.fixture(scope="module")
def server_module():
    spec = importlib.util.spec_from_file_location(
        "_parakeet_server_under_test", str(_SERVER_PATH),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _StubHolder:
    """ParakeetHolder stand-in. Returns a deterministic transcript
    derived from audio duration so tests can assert on transcript
    growth across feed calls."""

    def __init__(self):
        self.model_name = "stub-parakeet"
        self.device = "cpu"
        self.calls: list[float] = []  # audio_seconds per call

    def transcribe(self, audio: np.ndarray) -> str:
        audio_seconds = audio.size / 16000.0
        self.calls.append(audio_seconds)
        # Mimic Parakeet-style transcript that grows as more audio is
        # fed. Each 0.5 s of audio adds a token.
        n_tokens = max(1, int(audio_seconds / 0.5))
        return " ".join(["hello"] * n_tokens)


@pytest.fixture
def client_and_holder(server_module):
    holder = _StubHolder()
    # Reset session state between tests so previous sessions don't
    # leak into the next test's session count assertion.
    server_module._sessions.clear()
    server_module._holder = holder
    app = server_module.make_app(holder)
    return TestClient(app), holder, server_module


def _audio_bytes(seconds: float, sr: int = 16000) -> bytes:
    """Synthesize a deterministic float32 PCM chunk of the given duration."""
    n = int(seconds * sr)
    audio = np.zeros(n, dtype=np.float32)
    audio[::100] = 0.1  # sparse non-zero so it isn't all silence
    return audio.tobytes()


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_stream_start_returns_unique_id(client_and_holder):
    client, _holder, mod = client_and_holder
    r1 = client.post("/stream/start").json()
    r2 = client.post("/stream/start").json()
    assert "stream_id" in r1
    assert "stream_id" in r2
    assert r1["stream_id"] != r2["stream_id"]
    assert r1["sample_rate"] == 16000


def test_stream_start_creates_session_in_registry(client_and_holder):
    client, _holder, mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    assert sid in mod._sessions


def test_stream_stop_releases_session(client_and_holder):
    client, _holder, mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    client.post(f"/stream/stop/{sid}")
    assert sid not in mod._sessions


def test_stream_stop_unknown_id_returns_404(client_and_holder):
    client, _holder, _mod = client_and_holder
    r = client.post("/stream/stop/nonexistent")
    assert r.status_code == 404


def test_stream_feed_unknown_id_returns_404(client_and_holder):
    client, _holder, _mod = client_and_holder
    r = client.post("/stream/feed/nonexistent", content=_audio_bytes(0.5))
    assert r.status_code == 404


def test_stream_partial_unknown_id_returns_404(client_and_holder):
    client, _holder, _mod = client_and_holder
    r = client.get("/stream/partial/nonexistent")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Feed / partial / stop happy path
# ---------------------------------------------------------------------------


def test_feed_accumulates_audio_across_calls(client_and_holder):
    client, holder, mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]

    r1 = client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5)).json()
    r2 = client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5)).json()
    r3 = client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5)).json()

    assert r1["audio_seconds"] == pytest.approx(0.5, rel=0.01)
    assert r2["audio_seconds"] == pytest.approx(1.0, rel=0.01)
    assert r3["audio_seconds"] == pytest.approx(1.5, rel=0.01)
    # Each feed call triggers a transcribe (we re-transcribe accumulated buffer).
    assert len(holder.calls) == 3


def test_feed_returns_growing_partial_transcript(client_and_holder):
    """Stub transcribe returns more tokens as audio grows -- verify
    the partial transcript propagates back through the HTTP response."""
    client, _holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]

    r1 = client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5)).json()
    r2 = client.post(f"/stream/feed/{sid}", content=_audio_bytes(1.0)).json()
    r3 = client.post(f"/stream/feed/{sid}", content=_audio_bytes(1.5)).json()

    assert r1["partial"].split() == ["hello"]
    # After 1.5s total, stub returns 3 tokens.
    assert r2["partial"].count("hello") == 3
    # After 3.0s total, stub returns 6 tokens.
    assert r3["partial"].count("hello") == 6


def test_feed_empty_body_does_not_advance_buffer(client_and_holder):
    """Sending an empty body re-runs transcription but doesn't append
    audio -- useful for clients that just want to poll the current
    state via the same endpoint."""
    client, holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]

    client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5))
    first_calls = len(holder.calls)
    r = client.post(f"/stream/feed/{sid}", content=b"").json()

    assert r["audio_seconds"] == pytest.approx(0.5, rel=0.01)
    # Re-transcribe still ran (caller may have wanted a fresh read).
    assert len(holder.calls) == first_calls + 1


def test_partial_does_not_run_inference(client_and_holder):
    """``GET /stream/partial/{id}`` is a cheap query -- it doesn't
    re-run the model."""
    client, holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]

    client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5))
    calls_after_feed = len(holder.calls)

    for _ in range(5):
        client.get(f"/stream/partial/{sid}")
    # No additional transcribe calls.
    assert len(holder.calls) == calls_after_feed


def test_partial_returns_last_text(client_and_holder):
    client, _holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    client.post(f"/stream/feed/{sid}", content=_audio_bytes(1.0))

    p = client.get(f"/stream/partial/{sid}").json()
    assert p["partial"].count("hello") == 2  # 1.0 s / 0.5 s = 2 tokens
    assert p["audio_seconds"] == pytest.approx(1.0, rel=0.01)


def test_stop_returns_final_text(client_and_holder):
    client, holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    client.post(f"/stream/feed/{sid}", content=_audio_bytes(1.0))

    r = client.post(f"/stream/stop/{sid}").json()
    assert r["text"].count("hello") == 2
    assert r["audio_seconds"] == pytest.approx(1.0, rel=0.01)
    # Stop runs a fresh transcribe to finalize.
    assert len(holder.calls) >= 2  # feed + stop


def test_stop_on_empty_session_returns_empty_text(client_and_holder):
    client, holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    initial_calls = len(holder.calls)

    r = client.post(f"/stream/stop/{sid}").json()
    assert r["text"] == ""
    assert r["audio_seconds"] == 0.0
    # No transcribe call when there's nothing to transcribe.
    assert len(holder.calls) == initial_calls


def test_inference_ms_field_present(client_and_holder):
    client, _holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    r = client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5)).json()
    assert "inference_ms" in r
    assert isinstance(r["inference_ms"], (int, float))
    assert r["inference_ms"] >= 0


# ---------------------------------------------------------------------------
# Buffer caps + reaper
# ---------------------------------------------------------------------------


def test_buffer_cap_enforced(client_and_holder):
    """Sending more than _STREAM_MAX_SECONDS of audio in one call
    triggers a 413 + force-closes the session."""
    client, _holder, mod = client_and_holder
    # Temporarily shorten the cap so we don't have to generate 60 s of audio.
    original_cap = mod._STREAM_MAX_SECONDS
    mod._STREAM_MAX_SECONDS = 1.0
    try:
        sid = client.post("/stream/start").json()["stream_id"]
        r = client.post(
            f"/stream/feed/{sid}",
            content=_audio_bytes(1.5),
        )
        assert r.status_code == 413
        assert sid not in mod._sessions
    finally:
        mod._STREAM_MAX_SECONDS = original_cap


def test_expired_sessions_get_reaped(client_and_holder):
    """Sessions whose last_touched_at is older than the TTL get
    dropped on the next streaming call."""
    client, _holder, mod = client_and_holder
    # Force-expire by writing a fake old timestamp.
    sid = client.post("/stream/start").json()["stream_id"]
    sess = mod._sessions[sid]
    sess.last_touched_at = sess.last_touched_at - mod._STREAM_TTL_SECONDS - 10

    # Trigger reap by starting a new session.
    client.post("/stream/start")
    assert sid not in mod._sessions


def test_sessions_debug_endpoint_lists_active(client_and_holder):
    client, _holder, _mod = client_and_holder
    sids = [client.post("/stream/start").json()["stream_id"] for _ in range(3)]
    listing = client.get("/stream/sessions").json()
    assert listing["count"] == 3
    listed_ids = {s["stream_id"] for s in listing["sessions"]}
    assert listed_ids == set(sids)


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------


def test_feed_inference_failure_returns_500(client_and_holder):
    client, holder, _mod = client_and_holder

    def _boom(_audio):
        raise RuntimeError("simulated model crash")

    holder.transcribe = _boom
    sid = client.post("/stream/start").json()["stream_id"]
    r = client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5))
    assert r.status_code == 500


def test_stop_inference_failure_returns_partial(client_and_holder):
    """When stop()'s finalize transcribe fails, we return the last
    known partial rather than crash."""
    client, holder, _mod = client_and_holder
    sid = client.post("/stream/start").json()["stream_id"]
    client.post(f"/stream/feed/{sid}", content=_audio_bytes(0.5))
    # First feed has populated last_text; now break the next transcribe.

    def _boom(_audio):
        raise RuntimeError("simulated crash during stop")

    holder.transcribe = _boom
    r = client.post(f"/stream/stop/{sid}").json()
    assert "error" in r
    assert r["text"]  # the previously-cached partial
