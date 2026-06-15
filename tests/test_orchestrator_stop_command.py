"""The always-on "Ultron, stop" gate (`_stop_watcher_enabled`).

The interrupt watcher that powers "Ultron, stop" must run whenever EITHER
general barge-in OR the dedicated stop command is enabled -- so "stop" stays
available even while ``BARGE_IN_ENABLED`` is held off for loopback hygiene.
It must also require the wake + audio infra so bare/test orchestrators never
spawn the watcher.
"""

import pytest

from kenning.pipeline import orchestrator as orch_mod
from kenning.pipeline.orchestrator import Orchestrator


def _orch(*, wake=object(), audio=object()) -> Orchestrator:
    o = Orchestrator.__new__(Orchestrator)
    if wake is not None:
        o.wake = wake
    if audio is not None:
        o.audio = audio
    return o


def _set(monkeypatch, *, barge_in: bool, stop: bool) -> None:
    monkeypatch.setattr(orch_mod.settings, "BARGE_IN_ENABLED", barge_in,
                        raising=False)
    monkeypatch.setattr(orch_mod.settings, "STOP_COMMAND_ENABLED", stop,
                        raising=False)


def test_stop_on_barge_off_runs_watcher(monkeypatch):
    """The new default: barge-in off, stop on -> watcher runs."""
    _set(monkeypatch, barge_in=False, stop=True)
    assert _orch()._stop_watcher_enabled() is True


def test_both_off_no_watcher(monkeypatch):
    _set(monkeypatch, barge_in=False, stop=False)
    assert _orch()._stop_watcher_enabled() is False


def test_barge_on_stop_off_runs_watcher(monkeypatch):
    _set(monkeypatch, barge_in=True, stop=False)
    assert _orch()._stop_watcher_enabled() is True


def test_missing_wake_never_runs(monkeypatch):
    _set(monkeypatch, barge_in=True, stop=True)
    assert _orch(wake=None)._stop_watcher_enabled() is False


def test_missing_audio_never_runs(monkeypatch):
    _set(monkeypatch, barge_in=True, stop=True)
    assert _orch(audio=None)._stop_watcher_enabled() is False


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
