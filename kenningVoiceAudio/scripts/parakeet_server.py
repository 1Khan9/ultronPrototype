"""Parakeet TDT STT HTTP server.

Long-lived process living in the isolated ``.venv-parakeet`` venv.
Loads the NVIDIA Parakeet TDT model once, then serves transcription
requests over HTTP.

The Kenning orchestrator (in the main venv) talks to this server via
:mod:`src.kenning.transcription.parakeet_engine` (the client). HTTP keeps
the two venvs decoupled -- the main venv stays on numpy<2.0,
transformers 4.41.2, librosa 0.9.1 (pinned for the rest of the voice
stack), while NeMo in this venv can use its own newer versions.

Endpoints:

* ``GET /healthz`` -- ``{ok, model_loaded, model_name}``. Used by
  the client to wait for readiness on startup.

* ``POST /transcribe`` -- multipart form with field ``audio`` (raw
  WAV bytes, mono float32 or int16). Returns ``{text, audio_seconds,
  inference_ms}``.

* ``GET /info`` -- ``{model_name, device, sample_rate}``.

* ``POST /shutdown`` -- best-effort graceful exit.

Streaming endpoints (2026-05-22 -- re-transcribe pattern; see
:class:`StreamSession`):

* ``POST /stream/start`` -- ``{stream_id}``. Allocates a session.

* ``POST /stream/feed/{stream_id}`` -- raw bytes (mono float32, 16 kHz)
  in the request body. Appends to the session buffer and re-runs
  transcription on the accumulated audio. Returns ``{partial,
  audio_seconds, inference_ms}``. Idempotent on empty body.

* ``GET /stream/partial/{stream_id}`` -- returns ``{partial,
  audio_seconds}`` without feeding new audio. Cheap query for the
  current best transcript.

* ``POST /stream/stop/{stream_id}`` -- returns ``{text,
  audio_seconds, inference_ms}`` and releases the session.

The streaming pattern is "re-transcribe accumulated buffer" rather
than true cache-aware RNN-T streaming inference. Parakeet TDT on GPU
runs full inference in ~5-20 ms even on 10 s of audio, so the cost
of re-running each chunk is hidden in normal voice-loop latency.
This is dramatically simpler than NeMo's StreamingASR API (no
per-session encoder/decoder cache state to maintain) and the user-
visible behavior is identical.

Run:

    .venv-parakeet/Scripts/python.exe parakeet_server.py \\
        [--host 127.0.0.1] [--port 8771] \\
        [--model nvidia/parakeet-tdt-0.6b-v3] [--device cuda]
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("parakeet_server")


# ---------------------------------------------------------------------------
# Model holder
# ---------------------------------------------------------------------------


class ParakeetHolder:
    """Lazy NeMo model wrapper. Loads on construction; immutable
    afterwards."""

    def __init__(self, model_name: str, device: str) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            logger.info("Loading Parakeet model %s on %s ...",
                        self.model_name, self.device)
            t0 = time.monotonic()
            import nemo.collections.asr as nemo_asr
            self._model = nemo_asr.models.ASRModel.from_pretrained(
                model_name=self.model_name,
            )
            if hasattr(self._model, "to"):
                self._model = self._model.to(self.device)
            if hasattr(self._model, "freeze"):
                self._model.freeze()
            logger.info("Parakeet loaded in %.2fs",
                        time.monotonic() - t0)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        result = self._model.transcribe(audio=[audio], batch_size=1)
        if not result:
            return ""
        hyp = result[0]
        text = hyp.text if hasattr(hyp, "text") else str(hyp)
        return text.strip()


# ---------------------------------------------------------------------------
# Streaming sessions (re-transcribe accumulated buffer pattern)
# ---------------------------------------------------------------------------


# Maximum audio buffer per session (60 s). Anything longer almost
# certainly means a stalled stop call; the session is force-released to
# prevent unbounded growth.
_STREAM_MAX_SECONDS: float = 60.0
# Session TTL for inactivity-based garbage collection (90 s). Sessions
# that haven't been fed or queried in this window get reaped by the
# next streaming call.
_STREAM_TTL_SECONDS: float = 90.0


@dataclass
class StreamSession:
    """Per-session streaming state.

    The audio buffer accumulates as the client feeds chunks; each feed
    call re-runs full transcription on the accumulated buffer. State is
    plain numpy + a string -- no NeMo cache, no per-session model
    state, simple to reason about.
    """

    stream_id: str
    sample_rate: int = 16000
    audio: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=np.float32),
    )
    last_text: str = ""
    created_at: float = field(default_factory=time.monotonic)
    last_touched_at: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def audio_seconds(self) -> float:
        return float(self.audio.size) / max(self.sample_rate, 1)

    def append(self, chunk: np.ndarray) -> None:
        if chunk.size == 0:
            return
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32)
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1).astype(np.float32)
        self.audio = np.concatenate([self.audio, chunk])
        self.last_touched_at = time.monotonic()

    def touch(self) -> None:
        self.last_touched_at = time.monotonic()


_sessions: Dict[str, StreamSession] = {}
_sessions_lock = threading.Lock()


def _create_session() -> StreamSession:
    """Allocate a new streaming session. Also reaps expired sessions."""
    _reap_expired_sessions()
    sid = uuid.uuid4().hex
    sess = StreamSession(stream_id=sid)
    with _sessions_lock:
        _sessions[sid] = sess
    return sess


def _get_session(stream_id: str) -> StreamSession:
    with _sessions_lock:
        sess = _sessions.get(stream_id)
    if sess is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown stream_id: {stream_id}",
        )
    sess.touch()
    return sess


def _drop_session(stream_id: str) -> Optional[StreamSession]:
    with _sessions_lock:
        return _sessions.pop(stream_id, None)


def _reap_expired_sessions() -> int:
    """Drop sessions that haven't been touched in ``_STREAM_TTL_SECONDS``
    or have grown past ``_STREAM_MAX_SECONDS`` of audio."""
    now = time.monotonic()
    dropped: list[str] = []
    with _sessions_lock:
        for sid, sess in list(_sessions.items()):
            if (
                now - sess.last_touched_at > _STREAM_TTL_SECONDS
                or sess.audio_seconds > _STREAM_MAX_SECONDS
            ):
                dropped.append(sid)
                _sessions.pop(sid, None)
    if dropped:
        logger.info(
            "reaped %d expired stream session(s): %s",
            len(dropped), ", ".join(dropped[:3]) + ("..." if len(dropped) > 3 else ""),
        )
    return len(dropped)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


_holder: Optional[ParakeetHolder] = None
_shutdown_event = threading.Event()


def make_app(holder: ParakeetHolder) -> FastAPI:
    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {
            "ok": True,
            "model_loaded": holder._model is not None,
            "model_name": holder.model_name,
        }

    @app.get("/info")
    def info():
        sr = 16000
        return {
            "model_name": holder.model_name,
            "device": holder.device,
            "sample_rate": sr,
        }

    @app.post("/transcribe")
    async def transcribe(audio: UploadFile = File(...)):
        try:
            raw = await audio.read()
            audio_array, sr = sf.read(io.BytesIO(raw), dtype="float32",
                                       always_2d=False)
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1).astype("float32")
            if sr != 16000:
                # Parakeet expects 16 kHz. The Kenning pipeline already
                # standardises on 16 kHz so this should rarely fire.
                logger.warning("Audio at %d Hz; expected 16000 Hz", sr)
            t0 = time.monotonic()
            text = holder.transcribe(audio_array)
            inference_ms = (time.monotonic() - t0) * 1000
            return JSONResponse({
                "text": text,
                "audio_seconds": len(audio_array) / max(sr, 1),
                "inference_ms": inference_ms,
            })
        except Exception as e:
            logger.error("transcribe failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.post("/shutdown")
    def shutdown():
        _shutdown_event.set()
        return {"ok": True}

    # ----------------------------------------------------------------
    # Streaming endpoints
    # ----------------------------------------------------------------

    @app.post("/stream/start")
    def stream_start():
        sess = _create_session()
        return {"stream_id": sess.stream_id, "sample_rate": sess.sample_rate}

    @app.post("/stream/feed/{stream_id}")
    async def stream_feed(stream_id: str, request: Request):
        """Append raw float32 audio bytes (mono, 16 kHz) and re-run
        transcription on the accumulated buffer. Returns the latest
        partial transcript."""
        sess = _get_session(stream_id)
        try:
            raw = await request.body()
            if raw:
                # Body is raw float32 PCM at 16 kHz. The client always
                # sends this canonical layout to avoid having to negotiate.
                chunk = np.frombuffer(raw, dtype=np.float32)
                with sess.lock:
                    sess.append(chunk)
                    if sess.audio_seconds > _STREAM_MAX_SECONDS:
                        logger.warning(
                            "stream %s exceeded %.1fs cap; force-closing",
                            stream_id, _STREAM_MAX_SECONDS,
                        )
                        _drop_session(stream_id)
                        raise HTTPException(
                            status_code=413,
                            detail="stream exceeded max duration",
                        )
            # Re-transcribe whatever we have.
            with sess.lock:
                audio_snapshot = sess.audio
            if audio_snapshot.size == 0:
                return JSONResponse({
                    "partial": "",
                    "audio_seconds": 0.0,
                    "inference_ms": 0.0,
                })
            t0 = time.monotonic()
            text = _holder.transcribe(audio_snapshot)
            inference_ms = (time.monotonic() - t0) * 1000
            with sess.lock:
                sess.last_text = text
            return JSONResponse({
                "partial": text,
                "audio_seconds": sess.audio_seconds,
                "inference_ms": inference_ms,
            })
        except HTTPException:
            raise
        except Exception as e:
            logger.error("stream_feed failed: %s", e)
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get("/stream/partial/{stream_id}")
    def stream_partial(stream_id: str):
        """Return the latest partial without feeding new audio. Cheap
        to call repeatedly -- doesn't re-run inference."""
        sess = _get_session(stream_id)
        with sess.lock:
            return {
                "partial": sess.last_text,
                "audio_seconds": sess.audio_seconds,
            }

    @app.post("/stream/stop/{stream_id}")
    def stream_stop(stream_id: str):
        """Finalize transcription on the accumulated buffer + release
        the session. Returns the final transcript."""
        sess = _drop_session(stream_id)
        if sess is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown stream_id: {stream_id}",
            )
        with sess.lock:
            audio_snapshot = sess.audio
            audio_seconds = sess.audio_seconds
        if audio_snapshot.size == 0:
            return {
                "text": sess.last_text,
                "audio_seconds": 0.0,
                "inference_ms": 0.0,
            }
        t0 = time.monotonic()
        try:
            text = _holder.transcribe(audio_snapshot)
        except Exception as e:
            logger.error("stream_stop transcribe failed: %s", e)
            # Best-effort: return whatever partial we had.
            return {
                "text": sess.last_text,
                "audio_seconds": audio_seconds,
                "inference_ms": 0.0,
                "error": str(e),
            }
        inference_ms = (time.monotonic() - t0) * 1000
        return {
            "text": text,
            "audio_seconds": audio_seconds,
            "inference_ms": inference_ms,
        }

    @app.get("/stream/sessions")
    def stream_sessions():
        """Debug endpoint: list active streaming sessions."""
        with _sessions_lock:
            sessions_snapshot = [
                {
                    "stream_id": s.stream_id,
                    "audio_seconds": s.audio_seconds,
                    "age_seconds": time.monotonic() - s.created_at,
                    "last_touched_seconds_ago": time.monotonic() - s.last_touched_at,
                }
                for s in _sessions.values()
            ]
        return {"count": len(sessions_snapshot), "sessions": sessions_snapshot}

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--model", default="nvidia/parakeet-tdt-0.6b-v3")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    global _holder
    _holder = ParakeetHolder(args.model, args.device)
    app = make_app(_holder)

    config = uvicorn.Config(
        app, host=args.host, port=args.port, log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def watch_shutdown():
        _shutdown_event.wait()
        logger.info("Shutdown event received; stopping server.")
        server.should_exit = True

    t = threading.Thread(target=watch_shutdown, daemon=True)
    t.start()

    logger.info("Parakeet server listening on http://%s:%d",
                args.host, args.port)
    server.run()


if __name__ == "__main__":
    main()
