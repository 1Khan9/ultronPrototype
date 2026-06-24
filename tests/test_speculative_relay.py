"""Tests for the speculative-relay line path (2026-06-23 latency).

When the speculative transcript parses as a clean route-all relay callout, the
relay line is built DURING the end-of-turn silence wait (on the speculative-STT
daemon thread) and stashed; ``_maybe_handle_relay_speech`` consumes it instead
of running the LLM after the turn confirms -- overlapping the ~300ms build with
the ~400ms silence wait.

Bare orchestrator via ``object.__new__`` (no models). ``build_relay_line`` /
``match_relay_command`` / ``u1_llm_route_enabled`` / ``get_config`` are
monkeypatched so the cache + serialisation logic is tested in isolation.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

from kenning.pipeline.orchestrator import Orchestrator


def _bare_orch(llm=None):
    orch = object.__new__(Orchestrator)
    orch.llm = llm if llm is not None else object()
    orch._speculative_relay_lock = threading.Lock()
    orch._speculative_relay_done = threading.Event()
    orch._speculative_relay_done.set()
    orch._speculative_relay_text = None
    orch._speculative_relay_line = None
    orch._speculative_relay_invalidated = False
    orch._relay_recent_lines = None
    orch._current_raw_stt = None
    return orch


def _patch(monkeypatch, *, line="Push B.", is_command=True, route=True, enabled=True):
    import kenning.audio.relay_speech as rs
    import kenning.audio.command_normalizer as cn
    import kenning.config as kc
    monkeypatch.setattr(cn, "normalize_command", lambda t: t)  # identity -> stable key
    monkeypatch.setattr(rs, "u1_llm_route_enabled", lambda: route)
    monkeypatch.setattr(
        rs, "match_relay_command",
        lambda text, names=None: (SimpleNamespace(verbatim=False) if is_command else None))
    monkeypatch.setattr(rs, "build_relay_line", lambda *a, **k: line)
    monkeypatch.setattr(kc, "get_config", lambda: SimpleNamespace(
        relay_speech=SimpleNamespace(
            enabled=enabled, addressee_names=None, rephrase=True, max_line_chars=280)))


def test_build_then_consume(monkeypatch):
    _patch(monkeypatch)
    orch = _bare_orch()
    assert orch._run_speculative_relay("tell my team to push B") is True
    assert orch._take_speculative_relay("tell my team to push B") == "Push B."
    # consume-once: a second take returns None
    assert orch._take_speculative_relay("tell my team to push B") is None


def test_text_mismatch_falls_through(monkeypatch):
    _patch(monkeypatch)
    orch = _bare_orch()
    orch._run_speculative_relay("tell my team to push B")
    assert orch._take_speculative_relay("tell my team to rotate") is None


def test_invalidation_drops_the_line(monkeypatch):
    _patch(monkeypatch)
    orch = _bare_orch()
    orch._run_speculative_relay("tell my team to push B")
    orch._invalidate_speculative_relay()      # user resumed speaking
    assert orch._take_speculative_relay("tell my team to push B") is None


def test_skips_when_route_off(monkeypatch):
    _patch(monkeypatch, route=False)
    orch = _bare_orch()
    assert orch._run_speculative_relay("tell my team to push B") is False
    assert orch._take_speculative_relay("tell my team to push B") is None


def test_skips_non_relay_text(monkeypatch):
    _patch(monkeypatch, is_command=False)
    orch = _bare_orch()
    assert orch._run_speculative_relay("what's the weather like") is False


def test_done_event_serialises_consumer(monkeypatch):
    """While a build is in flight (done cleared) the consumer BLOCKS until the
    build sets the event -- the guarantee that keeps the speculative + main LLM
    calls from running concurrently (llama-cpp is not thread-safe)."""
    _patch(monkeypatch)
    orch = _bare_orch()
    orch._speculative_relay_done.clear()                 # simulate in-flight build
    orch._speculative_relay_text = "tell my team to push B"
    orch._speculative_relay_line = "Push B."
    released: list = []

    def _consumer():
        released.append(orch._take_speculative_relay("tell my team to push B"))

    t = threading.Thread(target=_consumer)
    t.start()
    t.join(timeout=0.3)
    assert t.is_alive()                                  # still blocked on the event
    orch._speculative_relay_done.set()                   # build "finished"
    t.join(timeout=2.0)
    assert released == ["Push B."]
