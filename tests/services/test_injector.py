"""Tests for the dependency-injection primitives (OpenHands catalog T6)."""

from __future__ import annotations

import threading

import pytest

from kenning.services.injector import (
    Injector,
    InjectorRegistry,
    InjectorState,
    SingletonInjector,
    StreamInjector,
    get_injector_registry,
    install_default_injectors,
    reset_injector_registry_for_testing,
    set_injector_registry,
)


@pytest.fixture(autouse=True)
def _isolate_singleton():
    reset_injector_registry_for_testing()
    yield
    reset_injector_registry_for_testing()


# -- InjectorState --


def test_state_get_set_via_attribute_access():
    state = InjectorState()
    state.mode = "gaming"
    assert state.mode == "gaming"


def test_state_missing_attribute_raises():
    state = InjectorState()
    with pytest.raises(AttributeError):
        state.never_set


def test_state_get_with_default():
    state = InjectorState()
    assert state.get("missing") is None
    assert state.get("missing", "fallback") == "fallback"


def test_state_contains_operator():
    state = InjectorState()
    assert "mode" not in state
    state.mode = "x"
    assert "mode" in state


def test_state_update_bulk():
    state = InjectorState()
    state.update(mode="gaming", session_id="abc")
    assert state.mode == "gaming"
    assert state.session_id == "abc"


def test_state_initial_kwargs():
    state = InjectorState(mode="gaming", region="us")
    assert state.mode == "gaming"
    assert state.region == "us"


def test_state_snapshot_returns_copy():
    state = InjectorState(a=1)
    snap = state.snapshot()
    snap["a"] = 99
    assert state.a == 1


def test_state_thread_safe_under_concurrent_writes():
    state = InjectorState()
    errors = []

    def worker(i):
        try:
            for j in range(100):
                state.update(**{f"key_{i}_{j}": j})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2)
    assert not errors
    # All 400 entries should have landed.
    assert len(state.snapshot()) == 400


# -- Injector ABC --


def test_injector_abstract():
    with pytest.raises(TypeError):
        Injector()  # type: ignore[abstract]


def test_singleton_injector_caches_instance():
    counter = {"n": 0}

    def _build(_state):
        counter["n"] += 1
        return {"id": counter["n"]}

    injector = SingletonInjector(_build)
    state = InjectorState()
    a = injector.inject(state)
    b = injector.inject(state)
    assert a is b
    assert counter["n"] == 1


def test_singleton_injector_reset_rebuilds():
    counter = {"n": 0}

    def _build(_state):
        counter["n"] += 1
        return counter["n"]

    injector = SingletonInjector(_build)
    state = InjectorState()
    first = injector.inject(state)
    injector.reset()
    second = injector.inject(state)
    assert first == 1
    assert second == 2


def test_singleton_injector_context_yields_instance():
    injector = SingletonInjector(lambda _s: "service")
    with injector.context() as service:
        assert service == "service"


def test_stream_injector_first_yield_returned_by_inject():
    def _stream(_state):
        yield "first"
        yield "second"

    injector = StreamInjector(_stream)
    assert injector.inject(InjectorState()) == "first"


def test_stream_injector_context_runs_teardown():
    closed = []

    def _stream(_state):
        try:
            yield "service"
        finally:
            closed.append(True)

    injector = StreamInjector(_stream)
    with injector.context() as service:
        assert service == "service"
    assert closed == [True]


def test_stream_injector_yields_through_stream_method():
    def _stream(_state):
        yield 1
        yield 2
        yield 3

    injector = StreamInjector(_stream)
    values = list(injector.stream(InjectorState()))
    assert values == [1, 2, 3]


def test_custom_injector_uses_state():
    class _ModeAware(Injector[str]):
        def inject(self, state):
            return state.get("mode", "default")

    injector = _ModeAware()
    state = InjectorState(mode="gaming")
    assert injector.inject(state) == "gaming"
    assert injector.inject(InjectorState()) == "default"


def test_injector_context_uses_default_state():
    class _Service(Injector[str]):
        def inject(self, state):
            return state.get("mode", "standby")

    injector = _Service()
    with injector.context() as service:
        assert service == "standby"


def test_injector_context_propagates_external_state():
    class _Service(Injector[str]):
        def inject(self, state):
            return state.get("mode", "standby")

    injector = _Service()
    with injector.context(InjectorState(mode="gaming")) as service:
        assert service == "gaming"


# -- InjectorRegistry --


def test_registry_register_and_get():
    registry = InjectorRegistry()
    injector = SingletonInjector(lambda _s: "service")
    registry.register("stt", injector)
    assert registry.get("stt") is injector


def test_registry_register_rejects_non_injector():
    registry = InjectorRegistry()
    with pytest.raises(TypeError):
        registry.register("x", lambda s: None)  # type: ignore[arg-type]


def test_registry_unregister():
    registry = InjectorRegistry()
    injector = SingletonInjector(lambda _s: None)
    registry.register("x", injector)
    assert registry.unregister("x") is True
    assert registry.get("x") is None
    assert registry.unregister("x") is False


def test_registry_require_raises_on_missing():
    registry = InjectorRegistry()
    with pytest.raises(KeyError):
        registry.require("missing")


def test_registry_require_returns_registered():
    registry = InjectorRegistry()
    injector = SingletonInjector(lambda _s: None)
    registry.register("x", injector)
    assert registry.require("x") is injector


def test_registry_keys_sorted():
    registry = InjectorRegistry()
    registry.register("zeta", SingletonInjector(lambda _s: None))
    registry.register("alpha", SingletonInjector(lambda _s: None))
    assert registry.keys() == ["alpha", "zeta"]


def test_registry_clear():
    registry = InjectorRegistry()
    registry.register("a", SingletonInjector(lambda _s: None))
    registry.register("b", SingletonInjector(lambda _s: None))
    registry.clear()
    assert registry.keys() == []


def test_singleton_set_get_reset():
    registry = InjectorRegistry()
    set_injector_registry(registry)
    assert get_injector_registry() is registry
    reset_injector_registry_for_testing()
    assert get_injector_registry() is None


# -- install_default_injectors --


def test_install_default_registers_stt_and_tts():
    registry = install_default_injectors()
    keys = registry.keys()
    assert "stt" in keys
    assert "tts" in keys


def test_install_default_uses_provided_registry():
    custom = InjectorRegistry()
    returned = install_default_injectors(registry=custom)
    assert returned is custom


def test_install_default_accepts_explicit_injectors():
    custom_stt = SingletonInjector(lambda _s: "custom_stt")
    custom_tts = SingletonInjector(lambda _s: "custom_tts")
    registry = install_default_injectors(
        stt_injector=custom_stt,
        tts_injector=custom_tts,
    )
    assert registry.require("stt") is custom_stt
    assert registry.require("tts") is custom_tts


# -- Engine injector behaviour (without loading heavy deps) --


def test_stt_injector_mode_dispatch_uses_gaming():
    from kenning.services.engine_injectors import STTEngineInjector

    seen_modes = []

    def _standby(state):
        seen_modes.append("standby")
        return "standby_engine"

    def _gaming(state):
        seen_modes.append("gaming")
        return "gaming_engine"

    injector = STTEngineInjector(standby_factory=_standby, gaming_factory=_gaming)
    assert injector.inject(InjectorState()) == "standby_engine"
    assert injector.inject(InjectorState(mode="gaming")) == "gaming_engine"
    assert seen_modes == ["standby", "gaming"]


def test_stt_injector_gaming_factory_failure_falls_back(caplog):
    import logging
    caplog.set_level(logging.WARNING)
    from kenning.services.engine_injectors import STTEngineInjector

    def _bad_gaming(_state):
        raise RuntimeError("CUDA not available")

    def _standby(_state):
        return "standby"

    injector = STTEngineInjector(
        standby_factory=_standby,
        gaming_factory=_bad_gaming,
    )
    result = injector.inject(InjectorState(mode="gaming"))
    assert result == "standby"
    assert any("falling back to standby" in rec.message for rec in caplog.records)


def test_tts_injector_mode_dispatch():
    from kenning.services.engine_injectors import TTSEngineInjector

    injector = TTSEngineInjector(
        standby_factory=lambda _s: ("rvc", "standby_tts"),
        gaming_factory=lambda _s: (None, "gaming_tts"),
    )
    assert injector.inject(InjectorState()) == ("rvc", "standby_tts")
    assert injector.inject(InjectorState(mode="gaming")) == (None, "gaming_tts")


def test_resolve_mode_helper_default():
    from kenning.services.engine_injectors import _resolve_mode

    assert _resolve_mode(None) == "standby"
    assert _resolve_mode(InjectorState()) == "standby"
    assert _resolve_mode(InjectorState(mode="gaming")) == "gaming"
    assert _resolve_mode(InjectorState(mode="")) == "standby"


def test_build_helpers_return_injectors():
    from kenning.services import (
        build_stt_engine_injector,
        build_tts_engine_injector,
        STTEngineInjector,
        TTSEngineInjector,
    )

    assert isinstance(build_stt_engine_injector(), STTEngineInjector)
    assert isinstance(build_tts_engine_injector(), TTSEngineInjector)
