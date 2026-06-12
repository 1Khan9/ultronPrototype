"""Tests for the openclaw-clawhub T15 telemetry wiring in the
orchestrator (Batch A of the deferred-primitive wiring pass).

Uses Orchestrator.__new__ to exercise the helper methods without the
heavy voice-stack init (same pattern as test_conversational_ack.py).
Per docs/test_sweep_binding_rules.md: R1 (no raw mutation), R4 (no
network), R7 (order-independent), R11 (no voice-stack loading).
"""

from __future__ import annotations

import time
from typing import Any

import pytest


def _bare_orchestrator() -> Any:
    from kenning.pipeline.orchestrator import Orchestrator

    o = Orchestrator.__new__(Orchestrator)
    o._metrics_store = None
    o._last_search_payload = None
    return o


class _FakeStore:
    def __init__(self) -> None:
        self.events: list = []
        self.raises = False

    def record_event(self, event: Any) -> bool:
        if self.raises:
            raise RuntimeError("store boom")
        self.events.append(event)
        return True


# ---------------------------------------------------------------------------
# _latency_bucket
# ---------------------------------------------------------------------------


class TestLatencyBucket:
    def test_buckets(self) -> None:
        from kenning.pipeline.orchestrator import Orchestrator

        assert Orchestrator._latency_bucket(0) == "fast"
        assert Orchestrator._latency_bucket(499) == "fast"
        assert Orchestrator._latency_bucket(500) == "normal"
        assert Orchestrator._latency_bucket(1499) == "normal"
        assert Orchestrator._latency_bucket(1500) == "slow"
        assert Orchestrator._latency_bucket(4999) == "slow"
        assert Orchestrator._latency_bucket(5000) == "very_slow"
        assert Orchestrator._latency_bucket(60000) == "very_slow"

    def test_labels_are_leak_safe(self) -> None:
        # Every bucket label must be <= 12 chars so it passes the
        # telemetry raw-path leak check without a safe-key carve-out.
        from kenning.pipeline.orchestrator import Orchestrator

        for ms in (0, 600, 2000, 9000):
            assert len(Orchestrator._latency_bucket(ms)) <= 12


# ---------------------------------------------------------------------------
# _init_telemetry_store
# ---------------------------------------------------------------------------


class TestInitTelemetryStore:
    def test_returns_store(self) -> None:
        from kenning.observability.private_telemetry import PrivateMetricsStore

        o = _bare_orchestrator()
        store = o._init_telemetry_store()
        assert isinstance(store, PrivateMetricsStore)

    def test_fail_open_on_import_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import kenning.observability.private_telemetry as pt

        o = _bare_orchestrator()

        # Force the constructor to raise; the helper must swallow it.
        def boom(*a: Any, **k: Any) -> Any:
            raise RuntimeError("construction failed")

        monkeypatch.setattr(pt, "PrivateMetricsStore", boom)
        assert o._init_telemetry_store() is None


# ---------------------------------------------------------------------------
# _emit_turn_telemetry
# ---------------------------------------------------------------------------


class TestEmitTurnTelemetry:
    def test_noop_when_store_none(self) -> None:
        o = _bare_orchestrator()
        o._metrics_store = None
        # Must not raise.
        o._emit_turn_telemetry("conversational", time.monotonic(), errored=False)

    def test_emits_event_with_leak_safe_attributes(self) -> None:
        from kenning.observability.private_telemetry import _is_safe_attribute

        o = _bare_orchestrator()
        store = _FakeStore()
        o._metrics_store = store
        o._last_search_payload = None
        o._emit_turn_telemetry(
            "media_generation", time.monotonic() - 0.6, errored=False
        )
        assert len(store.events) == 1
        ev = store.events[0]
        assert ev.kind == "voice_turn"
        # Every attribute must pass the real telemetry leak check.
        for k, v in ev.attributes.items():
            assert _is_safe_attribute(k, v), (k, v)
        assert ev.attributes["category"] == "media_generation"
        assert ev.attributes["searched"] is False
        assert ev.attributes["outcome"] == "ok"
        assert isinstance(ev.attributes["latency_ms"], int)
        assert ev.attributes["tier"] in {"fast", "normal", "slow", "very_slow"}

    def test_searched_flag_reflects_payload(self) -> None:
        o = _bare_orchestrator()
        store = _FakeStore()
        o._metrics_store = store
        o._last_search_payload = object()  # non-None -> searched
        o._emit_turn_telemetry("conversational", time.monotonic(), errored=False)
        assert store.events[0].attributes["searched"] is True

    def test_errored_outcome(self) -> None:
        o = _bare_orchestrator()
        store = _FakeStore()
        o._metrics_store = store
        o._emit_turn_telemetry("conversational", time.monotonic(), errored=True)
        assert store.events[0].attributes["outcome"] == "error"

    def test_none_intent_becomes_none_string(self) -> None:
        o = _bare_orchestrator()
        store = _FakeStore()
        o._metrics_store = store
        o._emit_turn_telemetry(None, time.monotonic(), errored=False)
        assert store.events[0].attributes["category"] == "none"

    def test_fail_open_when_store_raises(self) -> None:
        o = _bare_orchestrator()
        store = _FakeStore()
        store.raises = True
        o._metrics_store = store
        # Must not propagate the store exception.
        o._emit_turn_telemetry("conversational", time.monotonic(), errored=False)

    def test_real_store_records_only_when_opted_in(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # End-to-end through the REAL store: with telemetry disabled
        # (default), record_event no-ops; with opt-in, it writes.
        from kenning.observability.private_telemetry import (
            PrivateMetricsStore,
            TELEMETRY_ENABLE_ENV,
        )

        events_file = tmp_path / "metrics.jsonl"
        o = _bare_orchestrator()
        o._metrics_store = PrivateMetricsStore(
            project_root=tmp_path, events_path=events_file
        )
        # Disabled (env unset) -> no file written.
        monkeypatch.delenv(TELEMETRY_ENABLE_ENV, raising=False)
        o._emit_turn_telemetry("conversational", time.monotonic(), errored=False)
        assert not events_file.exists() or events_file.read_text().strip() == ""
        # Opted in -> a row is written.
        monkeypatch.setenv(TELEMETRY_ENABLE_ENV, "opt-in")
        o._emit_turn_telemetry("conversational", time.monotonic(), errored=False)
        assert events_file.exists()
        assert events_file.read_text().strip() != ""
