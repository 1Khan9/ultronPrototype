"""Tests for the local monitor (tee relay callouts to the user's own speakers).

Relay callouts normally play only on the mic B-bus + the OBS broadcast feed;
the monitor adds a parallel tee to the user's default output so they hear their
own callouts. It is gated by ``relay_speech.echo_to_user`` read LIVE per callout
(so the GUI toggle hot-applies). These tests cover:

* off (echo_to_user False) -> ``maybe_submit`` is a no-op, no device opened,
* on  -> the clip is submitted to the monitor sink (faked device),
* the target follows ``audio.output_device`` (resolved live),
* ``configure_from_config`` arms/releases the sink by the toggle,
* the sink is named "monitor" (distinct daemon thread / logs).

No real audio backend is touched: the resolver is monkeypatched and the sink
uses an injected fake stream.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from kenning.audio import monitor
from kenning.audio.broadcast import BroadcastSink


def _cfg(echo: bool, out_device=None):
    return SimpleNamespace(
        relay_speech=SimpleNamespace(echo_to_user=echo),
        audio=SimpleNamespace(output_device=out_device),
    )


def _install_fake_sink(monkeypatch, index=7):
    """Replace the shared sink with one whose resolver/stream never hit HW."""
    sink = BroadcastSink(
        resolver=lambda spec, kind: index,
        stream_factory=None,             # consumer not started in these asserts
        name="monitor",
    )
    monkeypatch.setattr(monitor, "_SINK", sink)
    monkeypatch.setattr(monitor, "_resolve_output_index", lambda out: index)
    return sink


def test_maybe_submit_noop_when_echo_off(monkeypatch):
    sink = _install_fake_sink(monkeypatch)
    monkeypatch.setattr("kenning.config.get_config", lambda: _cfg(echo=False))
    monitor.maybe_submit(np.ones(64, dtype=np.int16), 24000)
    assert sink._queue.qsize() == 0      # nothing enqueued
    assert sink.enabled is False         # device never configured/opened


def test_maybe_submit_tees_when_echo_on(monkeypatch):
    sink = _install_fake_sink(monkeypatch, index=11)
    monkeypatch.setattr("kenning.config.get_config", lambda: _cfg(echo=True))
    monitor.maybe_submit(np.full(64, 7, dtype=np.int16), 24000)
    assert sink._device_spec == 11       # pointed at the resolved output index
    assert sink._queue.qsize() == 1      # the clip was enqueued
    clip, sr = sink._queue.get_nowait()
    assert sr == 24000 and int(clip[0]) == 7


def test_maybe_submit_follows_output_device(monkeypatch):
    sink = BroadcastSink(resolver=lambda s, k: 3, name="monitor")
    monkeypatch.setattr(monitor, "_SINK", sink)
    seen = {}

    def _resolve(out):
        seen["out"] = out
        return 3

    monkeypatch.setattr(monitor, "_resolve_output_index", _resolve)
    monkeypatch.setattr("kenning.config.get_config",
                        lambda: _cfg(echo=True, out_device="Speakers"))
    monitor.maybe_submit(np.ones(8, dtype=np.int16), 24000)
    assert seen["out"] == "Speakers"     # the user's configured output, live


def test_configure_from_config_arms_and_releases(monkeypatch):
    sink = _install_fake_sink(monkeypatch, index=5)
    monkeypatch.setattr("kenning.config.get_config", lambda: _cfg(echo=True))
    monitor.configure_from_config()
    assert sink.enabled is True and sink._device_spec == 5
    monkeypatch.setattr("kenning.config.get_config", lambda: _cfg(echo=False))
    monitor.configure_from_config()
    assert sink.enabled is False
    sink.close()


def test_unresolvable_device_stays_off(monkeypatch):
    sink = _install_fake_sink(monkeypatch)
    monkeypatch.setattr(monitor, "_resolve_output_index", lambda out: None)
    monkeypatch.setattr("kenning.config.get_config", lambda: _cfg(echo=True))
    monitor.maybe_submit(np.ones(8, dtype=np.int16), 24000)
    assert sink._queue.qsize() == 0      # no device -> nothing enqueued


def test_sink_is_named_monitor():
    m = BroadcastSink(name="monitor")
    assert m._name == "monitor"
