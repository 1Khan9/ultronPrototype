"""Helper-model sidecar — Qwen2.5 CPU-only NL→action classifier.

Loopback HTTP service (mirrors scripts/twitch_guard_sidecar.py: 127.0.0.1 only,
parent-death deadman, fail-quiet) that loads a small Qwen2.5-0.5B/1.5B GGUF
(CPU) and classifies chat text into a CLOSED caller-supplied enum of economy
action types. Moderation actions are UNREACHABLE: the caller controls the
choices list and the sidecar never invents options outside it.

Fail-CLOSED: if the model is unavailable, /healthz reports ready=false and
/classify returns 503 -> the client returns None -> caller does not act.

Run:  python scripts/twitch_helper_sidecar.py [PORT]
Env:  KENNING_TWITCH_HELPER_PORT   (default 8776)
      KENNING_TWITCH_HELPER_MODEL   (path to GGUF, required)
      KENNING_TWITCH_HELPER_NCTX    (default 1024)
      KENNING_TWITCH_PARENT_PID     (parent watchdog PID)

ANTICHEAT: this script + llama_cpp live ONLY in the sidecar process.
The voice/relay process NEVER imports this — it uses the thin urllib client
in kenning.twitch.helper.HelperClient.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make the worktree importable so we can reuse sidecar_lock / sidecar_server.
_ROOT = Path(__file__).resolve().parent.parent
for _p in (_ROOT / "src", _ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import atexit  # noqa: E402

from kenning.subprocess import sidecar_lock  # noqa: E402
from kenning.subprocess.sidecar_server import SingletonThreadingHTTPServer  # noqa: E402

ROLE = "twitch_helper"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("KENNING_TWITCH_HELPER_PORT", "8776"))
MODEL = os.environ.get("KENNING_TWITCH_HELPER_MODEL", "")
NCTX = int(os.environ.get("KENNING_TWITCH_HELPER_NCTX", "1024"))

_llm = None
_load_error = ""


def _load() -> None:
    """Lazy-load the GGUF helper model. Never raises: a failure leaves _llm=None
    and _load_error set so /healthz reports not-ready (fail-CLOSED)."""
    global _llm, _load_error
    if _llm is not None:
        return
    if not MODEL or not Path(MODEL).exists():
        _load_error = f"helper model not found: {MODEL!r} (set KENNING_TWITCH_HELPER_MODEL)"
        print(f"[helper] WARN {_load_error}", flush=True)
        return
    try:
        from llama_cpp import Llama  # only present in .venv-twitch
        _llm = Llama(
            model_path=MODEL,
            n_ctx=NCTX,
            n_gpu_layers=0,   # CPU-only: helper must not compete with the main GPU
            verbose=False,
        )
        print(f"[helper] loaded {MODEL} n_ctx={NCTX} port={PORT} (CPU)", flush=True)
    except Exception as e:  # noqa: BLE001
        _load_error = f"llama_cpp load failed: {e}"
        print(f"[helper] WARN {_load_error}", flush=True)


def _classify(text: str, choices: list[str]) -> str:
    """Classify text into one of choices. Raises RuntimeError if model not loaded."""
    if _llm is None:
        raise RuntimeError("helper model not loaded")
    if not choices:
        raise ValueError("choices must be non-empty")

    choices_str = ", ".join(f'"{c}"' for c in choices)
    system_prompt = (
        "You are a command classifier for a Twitch economy game. "
        "Given the chat message, output ONLY the single most appropriate action "
        f"from this closed list: [{choices_str}]. "
        "If none fit, output the string \"none\". "
        "Output ONLY the action string, no explanation."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    out = _llm.create_chat_completion(
        messages=messages,
        max_tokens=32,
        temperature=0.0,
    )
    raw = (out["choices"][0]["message"]["content"] or "").strip().strip('"').strip("'")

    # Validate: must be one of the caller-supplied choices (fail-CLOSED otherwise).
    if raw in choices:
        return raw
    # Try casefold match as a fallback.
    raw_low = raw.casefold()
    for c in choices:
        if c.casefold() == raw_low:
            return c
    # Not in choices — fail-CLOSED: return a sentinel the client will reject.
    return "__invalid__"


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send(200, {
                "ready": _llm is not None,
                "model": MODEL,
                "error": _load_error,
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/classify":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"bad request: {e}"})
            return
        text = str(payload.get("text", ""))
        raw_choices = payload.get("choices", [])
        if not isinstance(raw_choices, list) or not raw_choices:
            self._send(400, {"error": "choices must be a non-empty list"})
            return
        choices = [str(c) for c in raw_choices]
        try:
            action = _classify(text, choices)
            self._send(200, {"action": action})
        except Exception as e:  # noqa: BLE001 — fail-CLOSED: 503
            self._send(503, {"error": f"helper unavailable: {e}"})

    def log_message(self, *args) -> None:  # noqa: ARG002
        return


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        pass
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            h = k.OpenProcess(0x1000, False, int(pid))
            if not h:
                return False
            code = wintypes.DWORD()
            ok = k.GetExitCodeProcess(h, ctypes.byref(code))
            k.CloseHandle(h)
            return (not ok) or code.value == 259
        except Exception:  # noqa: BLE001
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:  # noqa: BLE001
        return True


def _parent_watchdog() -> None:
    try:
        ppid = int(os.environ.get("KENNING_TWITCH_PARENT_PID", "0") or "0")
    except Exception:  # noqa: BLE001
        ppid = 0
    if ppid <= 0:
        ppid = os.getppid()
    if ppid <= 0:
        return
    while True:
        time.sleep(3.0)
        if not _pid_alive(ppid):
            sys.stderr.write(f"[helper] parent {ppid} gone -> self-terminating\n")
            sys.stderr.flush()
            os._exit(0)


def main() -> None:
    _load()  # best-effort; not-ready is reported via /healthz (fail-CLOSED)
    sidecar_lock.guard_singleton("127.0.0.1", PORT, ROLE)
    threading.Thread(target=_parent_watchdog, daemon=True, name="helper-parent-watchdog").start()
    server = SingletonThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    sidecar_lock.write_role(ROLE, os.getpid(), PORT)
    atexit.register(sidecar_lock.clear_role, ROLE)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        sidecar_lock.clear_role(ROLE)


if __name__ == "__main__":
    main()
