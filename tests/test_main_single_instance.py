"""Entrypoint integration tests for the single-instance guard.

Importing ``kenning.__main__`` only imports modules -- no models load.
All seams are monkeypatched; nothing touches the repo's real
``data/`` lock.
"""

from __future__ import annotations

import pytest

import kenning.__main__ as m


@pytest.fixture(autouse=True)
def _quiet_entrypoint(monkeypatch):
    """Keep main() hermetic inside the sweep.

    The real ``configure_logging()`` installs the rotating FILE
    handler pointed at the live ``logs/kenning.log`` -- once installed
    it persists for the rest of the pytest process, adding synchronous
    disk I/O to every later logger call (this measurably broke the
    memory hot-path latency-budget test downstream) and writing sweep
    noise into the production log. Stdio reconfig is likewise skipped
    (pytest owns the capture streams).
    """
    monkeypatch.setattr(m, "configure_logging", lambda: None)
    monkeypatch.setattr(m, "_ensure_utf8_stdio", lambda: None)


class _Boom:
    def __init__(self) -> None:  # pragma: no cover - must not run
        raise AssertionError("Orchestrator must not be constructed")


class _FakeLock:
    def __init__(self) -> None:
        self.released = 0

    def release(self) -> None:
        self.released += 1


class _StubOrchestrator:
    run_raises: bool = False

    def __init__(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self) -> None:
        if self.run_raises:
            raise RuntimeError("boom")

    def shutdown(self) -> None:
        pass


def test_duplicate_exits_3_without_constructing_orchestrator(
    monkeypatch, capsys
):
    # __main__ imports the guard inside main(), so patch the SOURCE
    # module attributes.
    monkeypatch.setattr(
        "kenning.lifecycle.single_instance.acquire_single_instance_lock",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "kenning.lifecycle.single_instance.read_lock_metadata",
        lambda *a, **k: {"pid": 1234},
    )
    monkeypatch.setattr(m, "Orchestrator", _Boom)
    rc = m.main()
    assert rc == 3
    out = capsys.readouterr().out
    assert "1234" in out
    assert "already running" in out


def test_lock_released_in_finally_on_happy_path(monkeypatch):
    fake = _FakeLock()
    monkeypatch.setattr(
        "kenning.lifecycle.single_instance.acquire_single_instance_lock",
        lambda *a, **k: fake,
    )
    stub = _StubOrchestrator
    stub.run_raises = False
    monkeypatch.setattr(m, "Orchestrator", stub)
    monkeypatch.setattr(m.signal, "signal", lambda *_a, **_k: None)
    rc = m.main()
    assert rc == 0
    assert fake.released == 1


def test_lock_released_when_run_raises(monkeypatch):
    fake = _FakeLock()
    monkeypatch.setattr(
        "kenning.lifecycle.single_instance.acquire_single_instance_lock",
        lambda *a, **k: fake,
    )

    class _Raising(_StubOrchestrator):
        run_raises = True

    monkeypatch.setattr(m, "Orchestrator", _Raising)
    monkeypatch.setattr(m.signal, "signal", lambda *_a, **_k: None)
    rc = m.main()
    assert rc == 1
    assert fake.released == 1


def test_lock_released_on_missing_model(monkeypatch):
    fake = _FakeLock()
    monkeypatch.setattr(
        "kenning.lifecycle.single_instance.acquire_single_instance_lock",
        lambda *a, **k: fake,
    )

    class _MissingModel:
        def __init__(self) -> None:
            raise FileNotFoundError("model.gguf")

    monkeypatch.setattr(m, "Orchestrator", _MissingModel)
    rc = m.main()
    assert rc == 2
    assert fake.released == 1
